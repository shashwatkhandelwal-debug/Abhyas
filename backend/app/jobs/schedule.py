"""Pure scheduling arithmetic for background jobs (spec/08 §8.6, T24).

No third-party imports: everything here is deterministic given `now`, so it is
trivially testable with a fixed clock. India observes no DST, so IST is a fixed
UTC+05:30 offset and no tz database is required.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from typing import Final

IST: Final = timezone(timedelta(hours=5, minutes=30), "IST")

MONDAY: Final = 0
SATURDAY: Final = 5

_MAX_RETRY_DELAY: Final = timedelta(hours=1)


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("naive datetime is not allowed; pass a timezone-aware value")
    return value


def to_ist(value: datetime) -> datetime:
    """Converts an aware datetime to IST."""
    return _require_aware(value).astimezone(IST)


def next_daily_at(now: datetime, hour: int, minute: int = 0) -> datetime:
    """Next HH:MM IST strictly after `now`, returned in UTC."""
    local = to_ist(now)
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)


def next_weekly_at(now: datetime, weekday: int, hour: int, minute: int = 0) -> datetime:
    """Next `weekday` (Mon=0) at HH:MM IST strictly after `now`, returned in UTC."""
    if not 0 <= weekday <= 6:
        raise ValueError("weekday must be 0 (Monday) to 6 (Sunday)")
    local = to_ist(now)
    days_ahead = (weekday - local.weekday()) % 7
    candidate = (local + timedelta(days=days_ahead)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    if candidate <= local:
        candidate += timedelta(days=7)
    return candidate.astimezone(UTC)


def week_start_ist(now: datetime) -> date:
    """Monday of the IST calendar week containing `now` (matches session_state.week_start)."""
    local = to_ist(now)
    return local.date() - timedelta(days=local.weekday())


def retry_delay(attempts: int, base_seconds: int) -> timedelta:
    """Exponential backoff after the given number of attempts, capped at one hour."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    delay = timedelta(seconds=base_seconds * 2 ** (attempts - 1))
    return min(delay, _MAX_RETRY_DELAY)


def truncate_words(text: str, max_words: int) -> str:
    """First `max_words` whitespace-separated words, never splitting inside a word."""
    if max_words < 1:
        raise ValueError("max_words must be >= 1")
    return " ".join(text.split()[:max_words])
