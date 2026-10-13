"""Scheduler tunables (spec/08 §8.6, T24).

AGENTS.md rule 9 wants every tunable in `config.py`, which the coordinator owns.
Until the fields below are added there (see PR notes / LANES.md request), each
value is read from `settings` when present and otherwise falls back to the
default declared here, so adding the setting later changes nothing but the
source of truth.
"""

from __future__ import annotations

from typing import Final

from backend.app.config import settings


def _int(name: str, default: int) -> int:
    return int(getattr(settings, name, default))


def _bool(name: str, default: bool) -> bool:
    return bool(getattr(settings, name, default))


SCHEDULER_ENABLED: Final = _bool("SCHEDULER_ENABLED", True)
SCHEDULER_TICK_SECONDS: Final = _int("SCHEDULER_TICK_SECONDS", 60)
SCHEDULER_PLAN_MINUTES: Final = _int("SCHEDULER_PLAN_MINUTES", 60)
SCHEDULER_MAX_ATTEMPTS: Final = _int("SCHEDULER_MAX_ATTEMPTS", 3)
SCHEDULER_RETRY_BASE_SECONDS: Final = _int("SCHEDULER_RETRY_BASE_SECONDS", 60)
SCHEDULER_BATCH_LIMIT: Final = _int("SCHEDULER_BATCH_LIMIT", 25)

AGGREGATES_HOUR_IST: Final = _int("AGGREGATES_HOUR_IST", 2)
ARP_DIGEST_WEEKDAY: Final = _int("ARP_DIGEST_WEEKDAY", 5)  # Saturday
ARP_DIGEST_HOUR_IST: Final = _int("ARP_DIGEST_HOUR_IST", 17)

FOLLOWUP_TOPIC_MAX_WORDS: Final = _int("FOLLOWUP_TOPIC_MAX_WORDS", 6)
FOLLOWUP_HOURS: Final = _int("TWO_DAY_FOLLOWUP_HOURS", 48)
