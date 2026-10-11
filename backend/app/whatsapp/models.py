"""Pydantic models for WhatsApp incoming and outgoing payloads (§11)."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class WhatsAppMedia(BaseModel):
    id: str
    mime_type: Optional[str] = None
    sha256: Optional[str] = None


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
    text: Optional[WhatsAppTextMessage] = None
    audio: Optional[WhatsAppAudioMessage] = None
    interactive: Optional[dict[str, Any]] = None


class WhatsAppWebhookEntry(BaseModel):
    id: str
    changes: list[dict[str, Any]]


class WhatsAppWebhookPayload(BaseModel):
    object: str
    entry: list[WhatsAppWebhookEntry]
