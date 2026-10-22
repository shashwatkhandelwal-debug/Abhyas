"""End-of-week "rate the training": answer parsing and the aggregate shown to trainer and admin.

After REFLECT the teacher is asked for one 1-5 rating of how useful the session was and an optional
one-line comment (typed or spoken; speech arrives here already transcribed). Stored in
``training_rating`` (not the realism rating, which asks about the simulated children).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.core.intents import Intent
from backend.app.core.messages import get_message
from backend.app.db.models import Teacher, TrainingRating
from backend.app.llm.hindi_numbers import extract_numbers

RATING_BUTTON_PREFIX = "btn_trate_"
SKIP_BUTTON_ID = "btn_trate_skip"
_SKIP_WORDS_KEY = "rate_training_skip_words"  # comma-separated, in both catalogs
_TRAILING_PUNCTUATION = ".!?" + chr(0x0964)  # chr(0x0964) is the Devanagari danda


def parse_training_rating(text: str, button_id: str | None) -> int | None:
    """1-5 from a rating button, a typed digit or a spoken number word; None if unclear."""
    if button_id and button_id.startswith(RATING_BUTTON_PREFIX) and button_id != SKIP_BUTTON_ID:
        tail = button_id[len(RATING_BUTTON_PREFIX) :]
        return int(tail) if tail.isdigit() and 1 <= int(tail) <= 5 else None
    numbers = extract_numbers(text or "")
    if numbers and 1 <= numbers[0] <= 5:
        return numbers[0]
    return None


# A reply that is really a command: the rating/comment prompt must never trap the teacher.
RATING_ESCAPE_INTENTS: frozenset[Intent] = frozenset(
    {
        Intent.HELP,
        Intent.NEXT,
        Intent.PROGRESS,
        Intent.LITE_TOGGLE,
        Intent.CONSENT,
        Intent.ASK,
        Intent.REPEAT,
        Intent.ADMIN,
        Intent.RETRY,
        Intent.DELETE,
    }
)
_LANGUAGE_WORDS_KEY = "rate_training_language_words"  # comma-separated, in both catalogs


def _language_words() -> frozenset[str]:
    words: set[str] = set()
    for lang in ("hi", "en"):
        raw = get_message(_LANGUAGE_WORDS_KEY, lang=lang)
        words.update(
            unicodedata.normalize("NFC", w).strip().lower() for w in raw.split(",") if w.strip()
        )
    return frozenset(words)


def is_language_command(text: str) -> bool:
    cleaned = unicodedata.normalize("NFC", text).strip().strip(_TRAILING_PUNCTUATION).strip()
    return cleaned.lower() in _language_words()


def is_rating_escape(intent: Intent | None, text: str) -> bool:
    """True if a rating/comment-stage reply is a known command, to be processed normally."""
    return (intent is not None and intent in RATING_ESCAPE_INTENTS) or is_language_command(text)


def _skip_words() -> frozenset[str]:
    """Words that mean "no comment", from both language catalogs (a teacher may use either)."""
    words: set[str] = {"-"}
    for lang in ("hi", "en"):
        raw = get_message(_SKIP_WORDS_KEY, lang=lang)
        words.update(
            unicodedata.normalize("NFC", w).strip().lower() for w in raw.split(",") if w.strip()
        )
    return frozenset(words)


def is_skip_comment(text: str) -> bool:
    cleaned = unicodedata.normalize("NFC", text).strip().strip(_TRAILING_PUNCTUATION).strip()
    return cleaned.lower() in _skip_words()


@dataclass
class RatingComment:
    rating: int
    comment: str
    created_at: datetime


@dataclass
class TrainingRatingSummary:
    count: int
    average: float | None
    distribution: dict[int, int] = field(default_factory=dict)
    latest_comments: list[RatingComment] = field(default_factory=list)
    suppressed: bool = False  # n below AGGREGATION_SUPPRESSION_N: only the count is shown


async def training_rating_summary(
    session: AsyncSession,
    *,
    district: str | None = None,
    consenting_only: bool = False,
    suppress_below: int | None = None,
) -> TrainingRatingSummary:
    """Average, count, 1-5 distribution and latest comments, without any teacher identity.

    ``district`` limits to teachers of that district, ``consenting_only`` to teachers who agreed to
    share scores (the trainer view uses both), ``suppress_below`` hides average/distribution/comments
    when fewer ratings than that exist (the n<10 rule).
    """
    base = select(TrainingRating).join(Teacher, Teacher.id == TrainingRating.teacher_id)
    if district is not None:
        base = base.where(Teacher.district == district)
    if consenting_only:
        base = base.where(Teacher.consent_share_scores.is_(True))
    sub = base.subquery()

    count = int((await session.execute(select(func.count()).select_from(sub))).scalar_one())
    if count == 0:
        return TrainingRatingSummary(count=0, average=None)
    if suppress_below is not None and count < suppress_below:
        return TrainingRatingSummary(count=count, average=None, suppressed=True)

    average = (await session.execute(select(func.avg(sub.c.rating)))).scalar_one()
    rows = (await session.execute(select(sub.c.rating, func.count()).group_by(sub.c.rating))).all()
    latest = (
        await session.execute(
            select(sub.c.rating, sub.c.comment, sub.c.created_at)
            .where(sub.c.comment.is_not(None), sub.c.comment != "")
            .order_by(sub.c.created_at.desc())
            .limit(settings.TRAINING_RATING_RECENT_COMMENTS)
        )
    ).all()
    return TrainingRatingSummary(
        count=count,
        average=round(float(average), 2),
        distribution={int(r): int(n) for r, n in rows},
        latest_comments=[RatingComment(int(r), str(c), at) for r, c, at in latest],
    )
