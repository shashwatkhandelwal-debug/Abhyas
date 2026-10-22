"""End-to-end guide check with REAL models: classifier (Haiku) -> retrieval gate -> answerer (Sonnet).

python -m eval.guide_e2e_live [--sets on,off,neg] [--force-pedagogy]

Per question the outcome is one of: answered (document-grounded answer + citation),
not_in_sources (retrieval gate or answerer said it is not in the documents), out_of_scope,
admin (canned replies), escalated (answer guard failed -> ARP).
--force-pedagogy skips the classifier (category=pedagogy) to test the retrieval gate and the
answerer alone, i.e. what happens when the classifier lets an off-topic question through.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from backend.app.llm.roles.guide_answerer import answer_guide_question
from backend.app.llm.roles.question_classifier import classify_question
from backend.app.llm.schemas import RetrievedChunk
from backend.app.retrieval.search import get_guide_retriever

ROOT = Path(__file__).resolve().parent.parent


def load_sets() -> dict[str, list[str]]:
    d = yaml.safe_load((ROOT / "eval/retrieval_questions.yaml").read_text(encoding="utf-8"))
    return {
        "on": [q["q"] for q in d["questions"]],
        "off": [q["q"] for q in d["offtopic_questions"]],
        "neg": list(d["negative_questions"]),
    }


async def run_one(question: str, force_pedagogy: bool) -> dict[str, Any]:
    category, query = "pedagogy", question
    if not force_pedagogy:
        cls = await classify_question(question)
        category = cls.output.category
        query = cls.output.search_query_hi or question
        if category in ("out_of_scope", "admin"):
            return {"outcome": category, "category": category, "chunks": 0, "answer": ""}
    hits = await get_guide_retriever().retrieve_supported(query)
    if not hits:
        return {
            "outcome": "not_in_sources",
            "category": category,
            "chunks": 0,
            "answer": "",
            "stage": "retrieval_gate",
        }
    chunks = [
        RetrievedChunk(
            chunk_id=c.chunk_id,
            source_short_hi=c.source_short_hi,
            section=c.section,
            page=c.page,
            text=c.text,
            gloss_hi=c.gloss_hi,
            keywords_hi=c.keywords_hi,
            score=c.similarity_score,
        )
        for c in hits
    ]
    res = await answer_guide_question(question=question, category=category, chunks=chunks)
    if res.no_sources:
        outcome, stage = "not_in_sources", "answerer"
    elif res.escalated or res.used_fallback:
        outcome, stage = "escalated", "answerer_guard"
    else:
        outcome, stage = "answered", "answerer"
    return {
        "outcome": outcome,
        "category": category,
        "chunks": len(hits),
        "stage": stage,
        "answer": res.answer_text_hi,
        "cited": [c.chunk_id for c in res.sources_cited],
        "confidence": res.output.confidence,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="on,off,neg")
    ap.add_argument("--force-pedagogy", action="store_true")
    ap.add_argument("--show", action="store_true", help="print every answer")
    args = ap.parse_args()
    logging.disable(logging.CRITICAL)
    sets = load_sets()
    for name in args.sets.split(","):
        qs = sets[name]
        results = [await run_one(q, args.force_pedagogy) for q in qs]
        tally = Counter(r["outcome"] for r in results)
        print(f"\n== {name} ({len(qs)}) force_pedagogy={args.force_pedagogy}: {dict(tally)}")
        stages = Counter(r.get("stage", r["outcome"]) for r in results)
        print("   by stage:", dict(stages))
        for q, r in zip(qs, results, strict=True):
            on_topic = name == "on"
            bad = (r["outcome"] != "answered") if on_topic else (r["outcome"] == "answered")
            if bad or args.show:
                print(f"   {'!!' if bad else '  '} {r['outcome']:<15} {q[:60]}")
                if r["outcome"] == "answered" and (bad or args.show):
                    print("       ", r["answer"][:240].replace("\n", " "))


if __name__ == "__main__":
    asyncio.run(main())
