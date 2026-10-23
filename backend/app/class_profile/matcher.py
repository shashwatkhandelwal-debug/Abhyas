"""Deterministic keyword matcher: a teacher's words -> ids from the closed struggle library.

This is the fallback behind the `class_struggle_classifier` role and the only thing that runs
with no API key. It reads NFC-normalised text, scores each library entry (a trigger phrase found
counts `STRUGGLE_PHRASE_WEIGHT`, most of its words `STRUGGLE_PARTIAL_PHRASE_WEIGHT`, a keyword `STRUGGLE_KEYWORD_WEIGHT`) and keeps the entries at or
above `STRUGGLE_MATCH_MIN_SCORE`, best first, at most `STRUGGLE_MAX_CHOSEN`.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from backend.app.class_profile.library import ClassStruggle, StruggleLibrary, load_library
from backend.app.config import settings
from backend.app.rehearsal.diagnosis import normalize_diagnosis_text
from backend.app.retrieval.search import index_terms, tokenize_hindi


class StruggleMatch(BaseModel):
    struggle_id: str
    score: int
    first_position: int


def clip_input(text: str) -> str:
    return (text or "")[: settings.STRUGGLE_INPUT_MAX_CHARS]


def _find(text_norm: str, keyword: str) -> int:
    """Index of the keyword in the text, or -1. Latin keywords match whole words only."""
    kw = normalize_diagnosis_text(keyword)
    if not kw:
        return -1
    if kw.isascii():
        m = re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text_norm)
        return m.start() if m else -1
    return text_norm.find(kw)


def _phrase_hit(text_norm: str, text_stems: set[str], phrase: str) -> tuple[int, int]:
    """(weight, position): the whole phrase, or most of its content words (stemmed), or nothing."""
    pos = _find(text_norm, phrase)
    if pos >= 0:
        return settings.STRUGGLE_PHRASE_WEIGHT, pos
    stems = index_terms(tokenize_hindi(phrase, filter_stopwords=True))
    if len(stems) < 2:
        return 0, -1
    found = [s for s in stems if s in text_stems]
    if len(found) / len(stems) < settings.STRUGGLE_PHRASE_TOKEN_COVERAGE:
        return 0, -1
    positions = [p for p in (text_norm.find(s) for s in found) if p >= 0]
    return settings.STRUGGLE_PARTIAL_PHRASE_WEIGHT, (min(positions) if positions else 0)


def _score(entry: ClassStruggle, text_norm: str, text_stems: set[str]) -> tuple[int, int]:
    score = 0
    positions: list[int] = []
    for phrase in entry.triggers_hi:
        weight, pos = _phrase_hit(text_norm, text_stems, phrase)
        if weight:
            score += weight
            positions.append(pos)
    for kw in entry.keywords:
        pos = _find(text_norm, kw)
        if pos >= 0:
            score += settings.STRUGGLE_KEYWORD_WEIGHT
            positions.append(pos)
    return score, (min(positions) if positions else 0)


def match_struggles(text: str, library: StruggleLibrary | None = None) -> list[StruggleMatch]:
    """Ordered matches (best score first; ties by who she mentioned first, then library order)."""
    lib = library or load_library()
    clean = clip_input(text)
    text_norm = normalize_diagnosis_text(clean)
    if not text_norm:
        return []
    text_stems = set(index_terms(tokenize_hindi(clean, filter_stopwords=True)))
    scored: list[tuple[int, int, int, str]] = []
    for order, entry in enumerate(lib.struggles):
        score, pos = _score(entry, text_norm, text_stems)
        if score >= settings.STRUGGLE_MATCH_MIN_SCORE:
            scored.append((-score, pos, order, entry.id))
    scored.sort()
    return [
        StruggleMatch(struggle_id=sid, score=-neg, first_position=pos)
        for neg, pos, _order, sid in scored[: settings.STRUGGLE_MAX_CHOSEN]
    ]
