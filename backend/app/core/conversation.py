"""Channel-agnostic conversation coordinator service (spec/02 §2.5, spec/08, T18).

Coordinates inbound message processing, per-teacher concurrency locks,
speech-to-text decoding with graceful degradation, and outbound dispatch.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from backend.app.config import settings
from backend.app.core.intents import Intent, match_intent
from backend.app.core.locks import teacher_lock
from backend.app.core.messages import get_message
from backend.app.core.types import Button, InboundMessage, OutboundMessage
from backend.app.rehearsal.scene_store import scene_store
from backend.app.speech.audio import to_wav16k
from backend.app.speech.spend import SpeechBudgetExceededError
from backend.app.speech.stt import STTProvider, get_stt_provider, normalize_transcript_text
from backend.app.speech.tts import TTSProvider, get_tts_provider

logger = logging.getLogger("abhyas.core.conversation")


class ConversationService:
    """Core channel-agnostic conversation coordinator (spec/02 §2.5, CHANGES 254f622)."""

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
        self._pending_transcripts: dict[UUID, str] = {}

    async def handle(self, inbound: InboundMessage) -> list[OutboundMessage]:
        """Handles an inbound message serialized per teacher lock (spec/02 §2.5)."""
        async with teacher_lock(inbound.teacher_id):
            return await self._handle_locked(inbound)

    async def _handle_locked(self, inbound: InboundMessage) -> list[OutboundMessage]:
        """Internal dispatch once teacher lock is acquired."""
        address_form: str = str(inbound.metadata.get("address_form", "f"))

        # 1. Handle pending low-confidence transcript confirmation (CHANGES 254f622 Item 7)
        if inbound.teacher_id in self._pending_transcripts:
            pending_text = self._pending_transcripts[inbound.teacher_id]
            intent = match_intent(inbound.text, in_rehearsal=False, button_id=inbound.button_id)
            if intent == Intent.CONFIRM_YES or inbound.button_id == "confirm_yes":
                del self._pending_transcripts[inbound.teacher_id]
                inbound.text = pending_text
                inbound.button_id = None
                inbound.kind = "text"
            elif (
                intent in (Intent.CONFIRM_NO, Intent.REPEAT)
                or inbound.button_id == "confirm_no"
                or (
                    inbound.text
                    and any(w in inbound.text for w in ["फिर से", "नहीं", "nahi", "no", "गलत"])
                )
            ):
                del self._pending_transcripts[inbound.teacher_id]
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message("stt_failed", address_form),
                    )
                ]
            else:
                del self._pending_transcripts[inbound.teacher_id]

        # 2. Process inbound audio if message kind is audio
        if inbound.kind == "audio":
            if not inbound.audio_bytes:
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message("stt_failed", address_form),
                    )
                ]

            try:
                wav16k = await to_wav16k(inbound.audio_bytes, mime=inbound.audio_mime)
                transcript = await self.stt.transcribe(wav16k)
            except SpeechBudgetExceededError:
                # CHANGES 254f622 Item 2: STT cap caught in ConversationService replying with stt_budget_type_please
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message("stt_budget_type_please", address_form),
                    )
                ]
            except Exception as exc:
                logger.warning("STT failed for inbound audio: %s", exc)
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message("stt_failed", address_form),
                    )
                ]

            # Low confidence verification (spec/08 §8.3, CHANGES 254f622 Item 7)
            if transcript.confidence < settings.STT_MIN_CONFIDENCE and transcript.text.strip():
                # In REHEARSE state: skip confirm and flag turn low_conf
                active_scene = scene_store.get_active_for_teacher(inbound.teacher_id)
                in_rehearsal = (active_scene is not None and active_scene.active) or (
                    inbound.metadata.get("state") == "REHEARSE"
                )

                if in_rehearsal:
                    inbound.text = transcript.text
                    inbound.metadata["low_conf"] = True
                else:
                    self._pending_transcripts[inbound.teacher_id] = transcript.text
                    confirm_text = get_message("stt_confirm", address_form, text=transcript.text)
                    return [
                        OutboundMessage(
                            kind="buttons",
                            text_hi=confirm_text,
                            buttons=[
                                Button(id="confirm_yes", title_hi="हाँ"),
                                Button(id="confirm_no", title_hi="फिर से बोलूँगी"),
                            ],
                        )
                    ]
            else:
                inbound.text = transcript.text
        elif inbound.text:
            inbound.text = normalize_transcript_text(inbound.text)

        # 3. Delegate to session dispatcher if registered
        if self.session_dispatcher is not None:
            return await self.session_dispatcher(inbound)

        # Fail fast in production if session_dispatcher is None (CHANGES 254f622 Item 9)
        if settings.ENVIRONMENT == "production":
            raise RuntimeError("ConversationService requires a session_dispatcher in production")

        # 4. Standalone dev/test responses (CHANGES 254f622 Item 8: NO hard-coded Hindi!)
        intent = match_intent(inbound.text, in_rehearsal=False, button_id=inbound.button_id)

        if intent == Intent.GREETING:
            return [
                OutboundMessage(
                    kind="text",
                    text_hi=get_message("welcome", address_form),
                    speaker="abhyas",
                )
            ]

        if intent == Intent.HELP:
            return [
                OutboundMessage(
                    kind="text",
                    text_hi=get_message("help_menu", address_form),
                    speaker="abhyas",
                )
            ]

        if intent == Intent.STOP_SCENE:
            return [
                OutboundMessage(
                    kind="text",
                    text_hi=get_message("scene_ended_neutral", address_form),
                    speaker="coach",
                )
            ]

        # No echo fallback: return catalog unclear message
        return [
            OutboundMessage(
                kind="text",
                text_hi=get_message("unclear", address_form),
                speaker="abhyas",
            )
        ]


__all__ = [
    "ConversationService",
]
