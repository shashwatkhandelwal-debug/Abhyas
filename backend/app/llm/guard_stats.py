"""Guard outcome recorder (T43, spec/11 §11.7).

Every role guard call reports (role, attempt, passed, reason). Events are kept in a bounded
in-memory ring and, when GUARD_EVENT_LOG_PATH is set, appended to a JSONL file. Event text
holds only the guard reason and the role, never teacher audio or transcripts.
"""

import json
import logging
import threading
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from backend.app.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_events: deque["GuardEvent"] = deque(maxlen=settings.GUARD_EVENT_RING_SIZE)


@dataclass(frozen=True)
class GuardEvent:
    at: str
    role: str
    attempt: int
    passed: bool
    reason: str
    mock: bool


def record_guard_event(role: str, attempt: int, passed: bool, reason: str) -> None:
    """Records one guard result; attempt is 0 for the first pass and 1 for the retry."""
    event = GuardEvent(
        at=datetime.now(UTC).isoformat(),
        role=role,
        attempt=attempt,
        passed=passed,
        reason="" if passed else reason[: settings.GUARD_EVENT_REASON_MAX_CHARS],
        mock=settings.LLM_PROVIDER == "mock" or not settings.ANTHROPIC_API_KEY,
    )
    with _lock:
        _events.append(event)
    if settings.GUARD_EVENT_LOG_PATH:
        try:
            path = Path(settings.GUARD_EVENT_LOG_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Guard event log write failed: %s", exc)


def snapshot() -> list[GuardEvent]:
    """Returns a copy of the in-memory events, oldest first."""
    with _lock:
        return list(_events)


def clear() -> None:
    """Clears the in-memory ring (tests)."""
    with _lock:
        _events.clear()
