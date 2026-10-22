"""Diagnosis step of a one-on-one scene: did the teacher spot the child's mistake?

The teacher says (voice or text) what they think the child's mistake is. This module compares
that with the scene's true misconception id and returns the verdict **deterministically**
(Hindi / Hinglish / English keyword sets from the move card). An LLM role may classify free text
to a misconception id when keywords are silent or ambiguous, but it only supplies an id: the
verdict (correct / partly / wrong) is always computed here.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from backend.app.content_models import MoveCard
from backend.app.llm.roles.diagnosis_classifier import classify_diagnosis


class Verdict(StrEnum):
    CORRECT = "correct"
    PARTLY = "partly"
    WRONG = "wrong"


Reason = Literal[
    "empty",
    "keyword_match",
    "classifier_match",
    "ambiguous",
    "other_misconception",
    "topic_only",
    "no_match",
]


class DiagnosisResult(BaseModel):
    verdict: Verdict
    true_misconception: str
    matched_misconception: str | None = None
    reason: Reason
    text: str = ""
    used_classifier: bool = False


_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_PUNCT = re.compile(r"[^\w\s+\-ऀ-ॿ]", re.UNICODE)  # keeps matras and viramas
# Danda and double danda sit in the Devanagari block but are punctuation
_DANDA = re.compile(r"[।॥]")


def normalize_diagnosis_text(text: str) -> str:
    """NFC, lowercase, Devanagari digits to ASCII, punctuation dropped, spaces collapsed."""
    cleaned = unicodedata.normalize("NFC", text or "").lower().translate(_DEVANAGARI_DIGITS)
    cleaned = _DANDA.sub(" ", cleaned)
    cleaned = _PUNCT.sub(" ", cleaned.replace("−", "-").replace("–", "-"))
    return re.sub(r"\s+", " ", cleaned).strip()


def _contains(text_norm: str, keyword: str) -> bool:
    kw = normalize_diagnosis_text(keyword)
    if not kw:
        return False
    if kw.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text_norm) is not None
    return kw in text_norm


def keyword_hits(text: str, keywords: list[str]) -> int:
    """Number of distinct keywords (each spelling variant counts once) found in the text."""
    text_norm = normalize_diagnosis_text(text)
    return sum(1 for kw in keywords if _contains(text_norm, kw))


def misconception_hits(move: MoveCard, text: str) -> dict[str, int]:
    return {mid: keyword_hits(text, mc.keywords) for mid, mc in move.misconceptions.items()}


def topic_hit(move: MoveCard, text: str) -> bool:
    return keyword_hits(text, move.diagnosis_topic_keywords) > 0


def _keyword_candidate(hits: dict[str, int]) -> tuple[str | None, list[str]]:
    """The single best-matching id, plus every id tied at the top (empty if no hit at all)."""
    top = max(hits.values(), default=0)
    if top == 0:
        return None, []
    leaders = [mid for mid, n in hits.items() if n == top]
    return (leaders[0] if len(leaders) == 1 else None), leaders


def judge_diagnosis(
    text: str,
    move: MoveCard,
    true_misconception: str,
    classified_id: str | None = None,
) -> DiagnosisResult:
    """Deterministic verdict. `classified_id` (from the LLM role) only names a candidate."""
    clean = unicodedata.normalize("NFC", text or "").strip()
    if not normalize_diagnosis_text(clean):
        return DiagnosisResult(
            verdict=Verdict.WRONG, true_misconception=true_misconception, reason="empty", text=clean
        )

    hits = misconception_hits(move, clean)
    keyword_id, leaders = _keyword_candidate(hits)
    candidate: str | None
    reason: Reason
    if keyword_id is not None:
        candidate, reason = keyword_id, "keyword_match"
    elif classified_id is not None and classified_id in move.misconceptions:
        candidate, reason = classified_id, "classifier_match"
    else:
        candidate, reason = None, ("ambiguous" if leaders else "no_match")

    def result(verdict: Verdict, matched: str | None, why: Reason) -> DiagnosisResult:
        return DiagnosisResult(
            verdict=verdict,
            true_misconception=true_misconception,
            matched_misconception=matched,
            reason=why,
            text=clean,
            used_classifier=reason == "classifier_match" and matched == candidate,
        )

    if candidate == true_misconception:
        return result(Verdict.CORRECT, candidate, reason)
    if hits.get(true_misconception, 0) > 0:
        # Named the true mistake, but alongside others (hedging) or outweighed by another one
        return result(
            Verdict.PARTLY, candidate, "ambiguous" if candidate is None else "other_misconception"
        )
    if candidate is not None:
        return result(Verdict.WRONG, candidate, "other_misconception")
    if topic_hit(move, clean):
        return result(Verdict.PARTLY, None, "topic_only")
    return result(Verdict.WRONG, None, "no_match")


async def diagnose(text: str, move: MoveCard, true_misconception: str) -> DiagnosisResult:
    """Keywords first; the classifier role is asked only when the keywords cannot name one id."""
    clean = unicodedata.normalize("NFC", text or "").strip()
    if not normalize_diagnosis_text(clean):
        return judge_diagnosis(clean, move, true_misconception)
    keyword_id, _ = _keyword_candidate(misconception_hits(move, clean))
    classified: str | None = None
    if keyword_id is None:
        candidates = {mid: mc.label_hi for mid, mc in move.misconceptions.items()}
        classified = await classify_diagnosis(clean, candidates)
    return judge_diagnosis(clean, move, true_misconception, classified_id=classified)
