"""24-hour customer care window calculation (spec/02 §2.4, spec/07 §7.2).

Meta WhatsApp Cloud API enforces a 24-hour service window:
- Inbound from user opens or refreshes a 24-hour window from teacher.last_inbound_at.
- Within 24 hours: Freeform messages (text, audio, interactive buttons/lists) may be sent.
- Beyond 24 hours: Only pre-approved Utility/Authentication templates may be sent.
- Web channel is exempt (can_send_freeform always True).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

WINDOW_DURATION_HOURS: Final = 24


def is_within_24h_window(
    last_inbound_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Checks whether the teacher is inside the active 24-hour WhatsApp customer care window."""
    if last_inbound_at is None:
        return False

    current_time = now if now is not None else datetime.now(UTC)

    # Ensure timezone awareness matches
    if last_inbound_at.tzinfo is None and current_time.tzinfo is not None:
        last_inbound_at = last_inbound_at.replace(tzinfo=UTC)
    elif last_inbound_at.tzinfo is not None and current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)

    elapsed = current_time - last_inbound_at
    if elapsed < timedelta(0):
        # Clock skew / future timestamp: treat as inside window
        return True

    return elapsed < timedelta(hours=WINDOW_DURATION_HOURS)
