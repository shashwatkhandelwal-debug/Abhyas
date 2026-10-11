"""Channel-agnostic conversation coordinator service (spec/02 §2.5, spec/08).

Task T18 implements full dispatch, state progression, and catalog wiring.
"""

from backend.app.core.types import InboundMessage, OutboundMessage


class ConversationService:
    """Core channel-agnostic conversation coordinator (spec/02 §2.5)."""

    async def handle(self, inbound: InboundMessage) -> list[OutboundMessage]:
        """Handles an inbound message and returns outbound responses.

        Raises:
            NotImplementedError: Owned by Lane B in task T18.
        """
        raise NotImplementedError("spec/02 §2.5 — ConversationService.handle owned by Lane B (T18)")
