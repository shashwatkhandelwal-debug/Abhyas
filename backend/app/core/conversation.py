"""Channel-agnostic conversation coordinator service (spec/02 §2.5, spec/08, T18).

Coordinates inbound message processing, per-teacher concurrency locks,
speech-to-text decoding with graceful degradation, and outbound dispatch.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from backend.app.config import settings
from backend.app.core.locks import teacher_lock
from backend.app.core.messages import get_message
from backend.app.core.types import Button, InboundMessage, OutboundMessage
from backend.app.speech.audio import to_wav16k
from backend.app.speech.stt import STTProvider, get_stt_provider, normalize_transcript_text
from backend.app.speech.tts import TTSProvider, get_tts_provider

logger = logging.getLogger("abhyas.core.conversation")


class ConversationService:
    """Core channel-agnostic conversation coordinator (spec/02 §2.5)."""

    def __init__(
        self,
        stt_provider: STTProvider | None = None,
        tts_provider: TTSProvider | None = None,
        session_dispatcher: Callable[[InboundMessage], Awaitable[list[OutboundMessage]]]
        | None = None,
    ) -> None:
        self.stt = stt_provider or get_stt_provider()
        self.tts = tts_provider or get_tts_provider()
        self.session_dispatcher = session_dispatcher

    async def handle(self, inbound: InboundMessage) -> list[OutboundMessage]:
        """Handles an inbound message serialized per teacher lock (spec/02 §2.5)."""
        async with teacher_lock(inbound.teacher_id):
            return await self._handle_locked(inbound)

    async def _handle_locked(self, inbound: InboundMessage) -> list[OutboundMessage]:
        """Internal dispatch once teacher lock is acquired."""
        # 1. Process inbound audio if message kind is audio
        if inbound.kind == "audio":
            if not inbound.audio_bytes:
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi="आवाज़ नहीं मिली, कृपया फिर से बोलें या लिखकर भेजें।",
                    )
                ]

            try:
                wav16k = await to_wav16k(inbound.audio_bytes, mime=inbound.audio_mime)
                transcript = await self.stt.transcribe(wav16k)
            except Exception as exc:
                logger.warning("STT failed for inbound audio: %s", exc)
                # Graceful degradation (spec/02 §2.6): state unchanged, friendly Hindi prompt
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi="आवाज़ साफ़ नहीं आई, कृपया फिर से बोलें या लिखकर भेजें।",
                    )
                ]

            # Low confidence verification (spec/02 §2.6)
            if transcript.confidence < settings.STT_MIN_CONFIDENCE and transcript.text.strip():
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=f"क्या आपने '{transcript.text}' कहा?",
                        buttons=[
                            Button(id="confirm_yes", title_hi="हाँ, सही है"),
                            Button(id="confirm_no", title_hi="फिर से बोलूँगी"),
                        ],
                    )
                ]

            inbound.text = transcript.text
        elif inbound.text:
            inbound.text = normalize_transcript_text(inbound.text)

        # 2. Delegate to session dispatcher if registered (e.g. SceneRunner or State Machine)
        if self.session_dispatcher is not None:
            return await self.session_dispatcher(inbound)

        # 3. Default core responses (greeting / help / echo fallback)
        text_lower = (inbound.text or "").strip().lower()

        if inbound.button_id == "confirm_no":
            return [
                OutboundMessage(
                    kind="text",
                    text_hi="कोई बात नहीं। कृपया फिर से बोलें या लिखकर भेजें।",
                )
            ]

        if inbound.button_id == "confirm_yes":
            return [
                OutboundMessage(
                    kind="text",
                    text_hi="धन्यवाद! आगे बढ़ते हैं।",
                )
            ]

        # Stop words / exit
        if any(w in text_lower for w in ["बस", "रुको", "खत्म", "stop", "pause"]):
            return [
                OutboundMessage(
                    kind="text",
                    text_hi="अभ्यास यहीं रोक दिया गया है। जब चाहें दोबारा शुरू कर सकते हैं।",
                )
            ]

        # Help intent
        if any(w in text_lower for w in ["मदद", "help", "menu", "मेनू"]):
            return [
                OutboundMessage(
                    kind="text",
                    text_hi="अभ्यास में आपका स्वागत है। आप बोलकर या लिखकर जवाब दे सकते हैं।",
                )
            ]

        # Greeting intent
        if any(w in text_lower for w in ["नमस्ते", "hello", "hi", "शुरू"]):
            welcome_text = get_message("welcome")
            return [
                OutboundMessage(
                    kind="text",
                    text_hi=welcome_text,
                    speaker="abhyas",
                )
            ]

        # Default echo fallback
        reply_text = inbound.text or "नमस्ते! आपका संदेश मिला।"
        return [
            OutboundMessage(
                kind="text",
                text_hi=reply_text,
            )
        ]


__all__ = [
    "ConversationService",
]
