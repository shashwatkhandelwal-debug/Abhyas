"""Starter questions for "Ask the handbook" and the per-teacher, per-day choice of four.

The questions live in ``content/handbook_questions.yaml``; each names the chunk that answers it
(validated by a test through the BM25 retriever). Tapping a chip sends the Hindi question through
the normal chat text path, so it is retrieved, answered and guarded like any typed question.
"""

from __future__ import annotations

import functools
import hashlib
import random
import unicodedata
from datetime import date
from pathlib import Path
from uuid import UUID

import yaml
from pydantic import BaseModel

from backend.app.config import settings

HANDBOOK_QUESTIONS_FILE = (
    Path(__file__).resolve().parents[3] / "content" / "handbook_questions.yaml"
)


class HandbookQuestion(BaseModel):
    id: str
    hi: str
    en: str
    chunk_id: str

    def label(self, lang: str) -> str:
        return self.en if lang == "en" else self.hi

    def send_text(self) -> str:
        """What the chip sends: the ask keyword plus the Hindi question."""
        return f"{settings.HANDBOOK_ASK_PREFIX} {self.hi}"


@functools.lru_cache(maxsize=1)
def load_handbook_questions() -> tuple[HandbookQuestion, ...]:
    raw = yaml.safe_load(HANDBOOK_QUESTIONS_FILE.read_text(encoding="utf-8"))
    questions = tuple(
        HandbookQuestion(
            id=str(q["id"]),
            hi=unicodedata.normalize("NFC", str(q["hi"])),
            en=str(q["en"]),
            chunk_id=str(q["chunk_id"]),
        )
        for q in raw["questions"]
    )
    ids = [q.id for q in questions]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate handbook question ids")
    return questions


def chips_for(teacher_id: UUID | str, day: date) -> list[HandbookQuestion]:
    """The same four questions all day for one teacher; a different four tomorrow."""
    questions = load_handbook_questions()
    seed = hashlib.sha256(f"{teacher_id}:{day.isoformat()}".encode()).digest()
    picked = random.Random(seed).sample(
        list(questions), k=min(settings.HANDBOOK_CHIPS_SHOWN, len(questions))
    )
    return picked


def chip_by_index(teacher_id: UUID | str, day: date, index: int) -> HandbookQuestion | None:
    chips = chips_for(teacher_id, day)
    return chips[index] if 0 <= index < len(chips) else None


def question_by_id(question_id: str) -> HandbookQuestion | None:
    return next((q for q in load_handbook_questions() if q.id == question_id), None)


def chip_views(teacher_id: UUID | str, day: date, lang: str) -> list[dict[str, str]]:
    """Today's chips as plain dicts for the templates: id, label (UI language), text to send."""
    return [
        {"id": q.id, "label": q.label(lang), "send": q.send_text()}
        for q in chips_for(teacher_id, day)
    ]
