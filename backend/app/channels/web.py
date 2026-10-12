"""Web channel implementation and inbound processing pipeline (spec/07 §7.1, §7.3).

Provides:
- WebChannel conforming to Channel protocol
- Inbound message processing pipeline with per-teacher asyncio.Lock serialisation
- Pending task state tracker for client polling
- Pluggable ConversationService hook for testing
"""

import asyncio
import logging
import unicodedata
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.conversation import ConversationService
from backend.app.core.types import InboundMessage, OutboundMessage
from backend.app.db.models import Message, Teacher
from backend.app.db.session import async_session_factory
from backend.app.speech.stt import get_stt_provider

logger = logging.getLogger("abhyas.channels.web")

# ── Per-teacher Locks & Pending Status Tracking (§7.1, §7.3) ───────────────
_teacher_locks: dict[uuid.UUID, asyncio.Lock] = {}
_teacher_pending_count: dict[uuid.UUID, int] = defaultdict(int)
_state_lock = asyncio.Lock()


def get_teacher_lock(teacher_id: uuid.UUID) -> asyncio.Lock:
    """Returns or creates the serialisation lock for a teacher (§7.1)."""
    if teacher_id not in _teacher_locks:
        _teacher_locks[teacher_id] = asyncio.Lock()
    return _teacher_locks[teacher_id]


def is_teacher_pending(teacher_id: uuid.UUID) -> bool:
    """Returns True if a background turn is currently queued/processing for this teacher (§7.3)."""
    return _teacher_pending_count.get(teacher_id, 0) > 0


def mark_teacher_pending(teacher_id: uuid.UUID) -> None:
    """Increments the pending task count for a teacher."""
    _teacher_pending_count[teacher_id] += 1


def unmark_teacher_pending(teacher_id: uuid.UUID) -> None:
    """Decrements the pending task count for a teacher."""
    if _teacher_pending_count.get(teacher_id, 0) > 0:
        _teacher_pending_count[teacher_id] -= 1
        if _teacher_pending_count[teacher_id] == 0:
            _teacher_pending_count.pop(teacher_id, None)


def reset_web_channel_state() -> None:
    """Resets in-memory locks and pending counters (used in tests)."""
    _teacher_locks.clear()
    _teacher_pending_count.clear()


# ── Pluggable Conversation Service Hook ─────────────────────────────────────
_conversation_service_factory: Callable[[], ConversationService] = ConversationService


def get_conversation_service() -> ConversationService:
    """Returns active ConversationService instance."""
    return _conversation_service_factory()


def set_conversation_service_factory(factory: Callable[[], ConversationService]) -> None:
    """Overrides ConversationService factory for tests."""
    global _conversation_service_factory
    _conversation_service_factory = factory


# ── WebChannel Class (§7.3) ──────────────────────────────────────────────────


class WebChannel:
    """Web channel implementation persisting outbound messages for polling clients."""

    name: str = "web"

    async def send(
        self,
        teacher: Teacher,
        msgs: list[OutboundMessage],
        session: AsyncSession | None = None,
    ) -> None:
        """Persists outbound messages to the database for retrieval by the web client."""
        if not msgs:
            return

        async def _persist(s: AsyncSession) -> None:
            for msg in msgs:
                db_msg = Message(
                    id=uuid.uuid4(),
                    teacher_id=teacher.id,
                    direction="out",
                    channel="web",
                    channel_msg_id=str(uuid.uuid4()),
                    kind=msg.kind,
                    text=unicodedata.normalize("NFC", msg.text_hi) if msg.text_hi else None,
                    audio_ref=msg.audio_ref,
                    buttons=[b.model_dump() for b in msg.buttons] if msg.buttons else None,
                    speaker=msg.speaker,
                    template_name=msg.template_name,
                    created_at=datetime.now(UTC),
                )
                s.add(db_msg)
            await s.commit()

        if session is not None:
            await _persist(session)
        else:
            async with async_session_factory() as new_session:
                await _persist(new_session)

    async def can_send_freeform(self, teacher: Teacher) -> bool:
        """Web channel has no 24-hour window restriction (§7.3)."""
        return True


# ── Background Inbound Pipeline Processor (§7.1, §7.3) ───────────────────────


async def process_inbound_web(
    teacher_id: uuid.UUID,
    message_id: uuid.UUID,
    kind: Literal["text", "audio", "button"],
    text: str | None = None,
    audio_bytes: bytes | None = None,
    button_id: str | None = None,
) -> None:
    """Asynchronously processes inbound web message under per-teacher serialisation lock.

    Pipeline:
    1. Acquire teacher lock
    2. STT if audio
    3. Update inbound Message row with transcript
    4. Call ConversationService.handle()
    5. Dispatch outbounds via WebChannel.send()
    6. Release lock and update pending indicator
    """
    try:
        lock = get_teacher_lock(teacher_id)
        async with lock:
            async with async_session_factory() as session:
                teacher = await session.get(Teacher, teacher_id)
                if not teacher:
                    logger.error("Teacher %s not found for inbound processing", teacher_id)
                    return

                final_text = text

                # Step 2: STT if audio
                if kind == "audio" and audio_bytes:
                    stt = get_stt_provider()
                    transcript = await stt.transcribe(audio_bytes)
                    final_text = unicodedata.normalize("NFC", transcript.text)
                    db_msg = await session.get(Message, message_id)
                    if db_msg:
                        db_msg.text = final_text
                        await session.commit()

                # Step 3: Button payload handling
                elif kind == "button" and button_id:
                    final_text = button_id
                    db_msg = await session.get(Message, message_id)
                    if db_msg and not db_msg.text:
                        db_msg.text = button_id
                        await session.commit()

                # Step 4: Dispatch to ConversationService
                inbound = InboundMessage(
                    channel="web",
                    channel_msg_id=str(message_id),
                    teacher_id=teacher_id,
                    kind=kind,
                    text=final_text,
                    button_id=button_id,
                    received_at=datetime.now(UTC),
                )

                conv_service = get_conversation_service()
                try:
                    outbounds = await conv_service.handle(inbound)
                except NotImplementedError:
                    logger.info("ConversationService.handle pending implementation in Lane B (T18)")
                    outbounds = []

                # Step 5: Send outbounds via WebChannel
                if outbounds:
                    web_channel = WebChannel()
                    await web_channel.send(teacher, outbounds, session=session)

    except Exception:
        logger.exception(
            "Error in process_inbound_web for teacher %s msg %s", teacher_id, message_id
        )
    finally:
        unmark_teacher_pending(teacher_id)
