"""Core message types shared across channels and conversation service (spec/02 §2.5)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    """Normalized inbound message from any channel (spec/02 §2.5, spec/07 §7.1)."""

    channel: Literal["whatsapp", "web"]
    channel_msg_id: str  # idempotency key
    teacher_id: UUID
    kind: Literal["text", "audio", "button"]
    text: str | None = None  # for text, or transcript after STT
    button_id: str | None = None
    audio_bytes: bytes | None = Field(default=None, exclude=True)  # never persisted
    audio_mime: str | None = None
    received_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class Button(BaseModel):
    """Quick-reply button option (title <= 20 chars for WhatsApp limit) (spec/02 §2.5)."""

    id: str
    title_hi: str = Field(max_length=20)


class Citation(BaseModel):
    """Source reference attached to a guide answer; tappable on the web channel."""

    chunk_id: str
    source_short_hi: str
    page: int | None = None
    line_hi: str  # the formatted "स्रोत: …, पृष्ठ N" line as it appears in text_hi


class OutboundMessage(BaseModel):
    """Normalized outbound message dispatched to preferred channel (spec/02 §2.5, spec/07 §7.1)."""

    kind: Literal["text", "audio", "buttons", "template"]
    text_hi: str | None = None
    audio_ref: str | None = None  # cache key of TTS audio
    buttons: list[Button] = Field(default_factory=list, max_length=3)
    template_name: str | None = None
    template_params: list[str] = Field(default_factory=list)
    speaker: str | None = None  # "abhyas" | persona id | "model_teacher" | "coach"
    message_id: UUID | None = None
    already_persisted: bool = False
    citations: list[Citation] = Field(default_factory=list)
