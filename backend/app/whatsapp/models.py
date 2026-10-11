"""Pydantic models for WhatsApp incoming and outgoing payloads (§11)."""

from typing import Any

from pydantic import BaseModel, Field


class WhatsAppMedia(BaseModel):
    id: str
    mime_type: str | None = None
    sha256: str | None = None


class WhatsAppAudioMessage(BaseModel):
    id: str
    mime_type: str


class WhatsAppTextMessage(BaseModel):
    body: str


class WhatsAppInteractiveReply(BaseModel):
    id: str
    title: str


class WhatsAppMessage(BaseModel):
    from_: str = Field(alias="from")
    id: str
    timestamp: str
    type: str  # text | audio | interactive | button
    text: WhatsAppTextMessage | None = None
    audio: WhatsAppAudioMessage | None = None
    interactive: dict[str, Any] | None = None


class WhatsAppWebhookEntry(BaseModel):
    id: str
    changes: list[dict[str, Any]]


class WhatsAppWebhookPayload(BaseModel):
    object: str
    entry: list[WhatsAppWebhookEntry]
