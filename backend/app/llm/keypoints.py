"""Deterministic Hindi key-point matcher (spec/05 §5.7 fallback, also used for the demo seed).

A keyword counts when a word of the answer *starts with* it, so Hindi inflections match
(डाँट -> डाँटें, मिला -> मिलाकर, मात्रा -> मात्राएँ); very short keywords must match a whole word, so
"मे" does not fire on "में". A keyword that belongs to one key point of the move says more than one
shared by several, so each keyword is weighted 1 / (number of key points that list it).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Literal

from backend.app.config import settings
from backend.app.content_models import MoveCard
from backend.app.llm.guards import norm

NUKTA = "़"
CHANDRABINDU = "ँ"
ANUSVARA = "ं"
TRAILING_SIGNS = "ािीेो"  # ा ि ी े ो


def fold(text: str) -> str:
    """Guard normalisation plus spelling variants that teachers type interchangeably."""
    return norm(unicodedata.normalize("NFC", text)).replace(NUKTA, "").replace(CHANDRABINDU, ANUSVARA)


@dataclass(frozen=True)
class KeyPointMatch:
    id: str
    status: Literal["covered", "partial", "missing"]
    quote: str
    score: float


def _hit(keyword: str, words: list[tuple[str, str]]) -> str | None:
    """The words of the answer (as written) that matched `keyword`, or None.

    `words` pairs each word as typed with its folded form.
    """
    if len(keyword) >= settings.KEYPOINT_MIN_STEM_CHARS + 2 and keyword[-1] in TRAILING_SIGNS:
        keyword = keyword[:-1]  # अंदाज़ा also matches अंदाज़े, मात्रा matches मात्राएँ
    parts = keyword.split()
    if len(parts) == 1 and len(keyword) < settings.KEYPOINT_MIN_STEM_CHARS:
        return next((raw for raw, f in words if f == keyword), None)
    for i in range(len(words) - len(parts) + 1):
        window = words[i : i + len(parts)]
        if all(f == p for (_, f), p in zip(window[:-1], parts[:-1])) and window[-1][1].startswith(
            parts[-1]
        ):
            return " ".join(raw for raw, _ in window)
    return None


def match_key_points(move: MoveCard, transcript: str) -> list[KeyPointMatch]:
    """One verdict per key point of `move`, from the keywords in `keywords_hi`."""
    answer = [(raw, f) for raw in transcript.split() if (f := fold(raw))]
    keywords = {kp.id: [k for k in (fold(w) for w in kp.keywords_hi) if k] for kp in move.key_points}
    shared: dict[str, int] = {}
    for words in keywords.values():
        for word in set(words):
            shared[word] = shared.get(word, 0) + 1
    out: list[KeyPointMatch] = []
    for kp in move.key_points:
        words = keywords[kp.id]
        total = sum(1 / shared[w] for w in words)
        hits = [(w, _hit(w, answer)) for w in words]
        found = [(w, q) for w, q in hits if q]
        score = sum(1 / shared[w] for w, _ in found) / total if total else 0.0
        status: Literal["covered", "partial", "missing"]
        if score >= settings.KEYPOINT_COVERED_SCORE:
            status = "covered"
        elif score >= settings.KEYPOINT_PARTIAL_SCORE:
            status = "partial"
        else:
            status = "missing"
        quote = found[0][1] if found and status != "missing" else ""
        out.append(KeyPointMatch(id=kp.id, status=status, quote=quote or "", score=round(score, 3)))
    return out
