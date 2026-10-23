"""Deterministic answer for a handbook chip question when the answering model is unavailable.

Each chip question is tied to the chunk that answers it (`content/handbook_questions.yaml`). If the
guide answerer cannot run or fails its guard twice, the teacher still gets that chunk's stored Hindi
summary and its source page, so a chip never ends in "not found". Nothing is generated at runtime:
the summary was written once at ingestion and is shown as stored.
"""

from __future__ import annotations

import re
import unicodedata

from backend.app.config import settings
from backend.app.core.messages import get_message
from backend.app.core.types import Citation
from backend.app.handbook.questions import HandbookQuestion, load_handbook_questions
from backend.app.llm.roles.guide_answerer import citations_for_chunks, format_guide_citation
from backend.app.llm.schemas import RetrievedChunk
from backend.app.retrieval.search import GuideRetriever

_EDGES = re.compile(r"^[\s:\-?।.!]+|[\s:\-?।.!]+$")


def _clean(text: str) -> str:
    return _EDGES.sub("", unicodedata.normalize("NFC", text or "")).casefold()


def match_handbook_question(text: str) -> HandbookQuestion | None:
    """The chip question a typed or tapped text is (with or without the ask keyword), if any."""
    cleaned = _clean(text)
    prefix = _clean(settings.HANDBOOK_ASK_PREFIX)
    if prefix and cleaned.startswith(prefix):
        cleaned = _clean(cleaned[len(prefix) :])
    for q in load_handbook_questions():
        if _clean(q.hi) == cleaned:
            return q
    return None


def fallback_reply(
    question: HandbookQuestion, retriever: GuideRetriever, address_form: str
) -> tuple[str, list[Citation]] | None:
    """(text, citations) from the question's own chunk, or None if the chunk is unavailable."""
    stored = retriever.get_chunk(question.chunk_id)
    if not stored:
        return None
    summary = str(stored.get("gloss_hi") or "").strip()
    if not summary:
        return None
    chunk = RetrievedChunk(
        chunk_id=question.chunk_id,
        source_short_hi=str(stored.get("source_short_hi") or get_message("ingest_summary_title")),
        section=str(stored.get("section", "")),
        page=stored.get("page"),
        text=str(stored.get("text", "")),
        gloss_hi=summary,
    )
    cites = citations_for_chunks([chunk], address_form)
    line = format_guide_citation(chunk.source_short_hi, chunk.page, address_form=address_form)
    text = get_message("handbook_fallback", address_form, summary=summary, citation=line)
    return text, cites
