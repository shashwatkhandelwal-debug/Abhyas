"""Channel protocol and base definitions (spec/02 §2.5, spec/07)."""

from typing import Protocol

from backend.app.core.types import OutboundMessage
from backend.app.db.models import Teacher


class Channel(Protocol):
    """Abstract channel protocol connecting brain to delivery networks (spec/02 §2.5)."""

    name: str

    async def send(self, teacher: Teacher, msgs: list[OutboundMessage]) -> None:
        """Sends a batch of outbound messages to the teacher via this channel."""
        ...

    async def can_send_freeform(self, teacher: Teacher) -> bool:
        """Checks if the 24-hour customer care window is active (always True for web)."""
        ...
