"""Retrieval eval: recall@5 on eval/retrieval_questions.yaml and 'does not know' score check.

python eval/retrieval_recall.py [--verify-ground-truth] [--k 5]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.app.config import settings  # noqa: E402
from backend.app.retrieval.search import GuideRetriever  # noqa: E402

QUESTIONS = REPO / "eval" / "retrieval_questions.yaml"
CHUNKS = REPO / "content" / "chunks"


def load_questions() -> dict[str, Any]:
    data = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def ranges(q: dict[str, Any]) -> list[tuple[int, int]]:
    pages = q["pages"]
    if isinstance(pages[0], int):
        pages = [pages]
    return [(int(a), int(b)) for a, b in pages]


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def verify_ground_truth(questions: list[dict[str, Any]]) -> list[str]:
    """Each question's evidence regex must appear in a committed chunk inside its page range."""
    chunks: list[dict[str, Any]] = []
    for f in CHUNKS.glob("*.jsonl"):
        chunks += [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    bad = []
    for q in questions:
        for rng in ranges(q):
            ok = any(
                c.get("source_id") == q["source"]
                and overlaps(rng, (c["pdf_page_start"], c["pdf_page_end"]))
                and re.search(q["evidence"], c["text"])
                for c in chunks
            )
            if not ok:
                bad.append(f"{q['id']}{list(rng)}")
    return bad


async def evaluate(k: int) -> dict[str, Any]:
    data = load_questions()
    qs = data["questions"]
    retriever = GuideRetriever()
    hits = 0
    misses: list[str] = []
    pos_top: list[float] = []
    for q in qs:
        res = await retriever.retrieve(q["q"], top_k=k, min_score=0.0)
        hit = any(
            r.source == q["source"]
            and any(overlaps(rng, (r.page or 0, r.page_end or r.page or 0)) for rng in ranges(q))
            for r in res
        )
        hits += int(hit)
        if not hit:
            misses.append(q["id"])
        pos_top.append(res[0].similarity_score if res else 0.0)
    neg_top: list[float] = []
    for text in data["negative_questions"]:
        res = await retriever.retrieve(text, top_k=1, min_score=0.0)
        neg_top.append(res[0].similarity_score if res else 0.0)
    return {
        "k": k,
        "n": len(qs),
        "recall_at_k": hits / len(qs),
        "misses": misses,
        "min_score_threshold": settings.RETRIEVAL_MIN_SCORE,
        "answerable_top1_score": {
            "min": min(pos_top),
            "median": sorted(pos_top)[len(pos_top) // 2],
        },
        "negative_top1_score_max": max(neg_top),
        "negatives_below_threshold": sum(s < settings.RETRIEVAL_MIN_SCORE for s in neg_top),
        "answerable_below_threshold": sum(s < settings.RETRIEVAL_MIN_SCORE for s in pos_top),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--verify-ground-truth", action="store_true")
    args = ap.parse_args()
    if args.verify_ground_truth:
        bad = verify_ground_truth(load_questions()["questions"])
        print("ground truth unverified for:", bad or "none")
    print(json.dumps(asyncio.run(evaluate(args.k)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
