"""Speech cost control, budget tracking, and usage limits (spec/06 §6.4).

Provides:
- STT / TTS cost calculation formulas in INR.
- Daily (SPEECH_DAILY_BUDGET_INR) and total (SPEECH_TOTAL_BUDGET_INR) budget guard.
- Aggressive caching and pre-warming helpers.
- Lite-mode fallback (text-only reply) when budget cap is reached.
"""

from __future__ import annotations

import datetime
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from backend.app.config import settings

if TYPE_CHECKING:
    from backend.app.speech.cache import TTSCache
    from backend.app.speech.tts import TTSProvider

logger = logging.getLogger("abhyas.speech.spend")


class SpeechBudgetExceededError(Exception):
    """Raised when speech synthesis or transcription exceeds configured INR budget cap."""

    pass


def calculate_stt_cost(duration_s: float) -> float:
    """Calculates STT cost in INR for audio duration in seconds (spec/06 §6.4).

    Billed in 15-second minimum increments (rounded up to nearest 15s).
    Formula: ceil(max(dur, 0) / 15) * (15 / 60) * settings.STT_COST_PER_MINUTE_INR.
    """
    if duration_s <= 0.0:
        return 0.0
    billed_seconds = math.ceil(duration_s / 15.0) * 15.0
    minutes = billed_seconds / 60.0
    return round(minutes * settings.STT_COST_PER_MINUTE_INR, 4)


def calculate_tts_cost(text: str) -> float:
    """Calculates TTS cost in INR for Hindi text (spec/06 §6.4).

    Formula: (len(text) / 1000.0) * settings.TTS_COST_PER_1000_CHARS_INR.
    """
    if not text:
        return 0.0
    return round((len(text) / 1000.0) * settings.TTS_COST_PER_1000_CHARS_INR, 4)


@dataclass
class SpeechBudgetTracker:
    """Tracks daily and total speech spend against configured INR budgets (spec/06 §6.4)."""

    daily_spend: float = 0.0
    total_spend: float = 0.0
    last_reset_date: datetime.date = field(default_factory=datetime.date.today)

    def _check_day_rollover(self) -> None:
        today = datetime.date.today()
        if today > self.last_reset_date:
            self.daily_spend = 0.0
            self.last_reset_date = today

    def can_spend(self, amount_inr: float) -> bool:
        """Checks if spending amount_inr is within daily and total budget caps."""
        self._check_day_rollover()
        if self.daily_spend + amount_inr > settings.SPEECH_DAILY_BUDGET_INR:
            return False
        if self.total_spend + amount_inr > settings.SPEECH_TOTAL_BUDGET_INR:
            return False
        return True

    def record_spend(self, amount_inr: float) -> None:
        """Records spend towards daily and total caps."""
        self._check_day_rollover()
        self.daily_spend = round(self.daily_spend + amount_inr, 4)
        self.total_spend = round(self.total_spend + amount_inr, 4)
        logger.info(
            "Speech spend recorded: +%.4f INR (daily: %.4f / %.1f, total: %.4f / %.1f)",
            amount_inr,
            self.daily_spend,
            settings.SPEECH_DAILY_BUDGET_INR,
            self.total_spend,
            settings.SPEECH_TOTAL_BUDGET_INR,
        )

    def check_and_record_stt(self, duration_s: float) -> float:
        """Verifies budget and records STT spend if live mode is enabled.

        Returns cost incurred (0.0 if not live).
        Raises SpeechBudgetExceededError if cap exceeded.
        """
        if not settings.SPEECH_PROVIDER_LIVE:
            return 0.0
        cost = calculate_stt_cost(duration_s)
        if not self.can_spend(cost):
            raise SpeechBudgetExceededError(
                f"STT spend {cost:.4f} INR exceeds budget (daily: {self.daily_spend:.2f}/{settings.SPEECH_DAILY_BUDGET_INR}, total: {self.total_spend:.2f}/{settings.SPEECH_TOTAL_BUDGET_INR})"
            )
        self.record_spend(cost)
        return cost

    def check_and_record_tts(self, text: str) -> float:
        """Verifies budget and records TTS spend if live mode is enabled.

        Returns cost incurred (0.0 if not live).
        Raises SpeechBudgetExceededError if cap exceeded.
        """
        if not settings.SPEECH_PROVIDER_LIVE:
            return 0.0
        cost = calculate_tts_cost(text)
        if not self.can_spend(cost):
            raise SpeechBudgetExceededError(
                f"TTS spend {cost:.4f} INR exceeds budget (daily: {self.daily_spend:.2f}/{settings.SPEECH_DAILY_BUDGET_INR}, total: {self.total_spend:.2f}/{settings.SPEECH_TOTAL_BUDGET_INR})"
            )
        self.record_spend(cost)
        return cost

    def reset(self) -> None:
        """Resets tracked daily and total spend (for tests and administrative reset)."""
        self.daily_spend = 0.0
        self.total_spend = 0.0
        self.last_reset_date = datetime.date.today()


speech_budget = SpeechBudgetTracker()


async def prewarm_fixed_audio(
    tts: TTSProvider | None = None,
    cache: TTSCache | None = None,
    catalog_path: Path | str | None = None,
    extra_lines: list[tuple[str, str]] | None = None,
) -> list[str]:
    """Pre-warms TTS audio cache for static messages in messages_hi.yaml and extra lines (spec/06 §6.4).

    Synthesizes fixed messages where audio: true using the configured or mock TTS provider,
    ensuring live production sessions hit the cache with zero latency and 0 INR spend.
    Returns list of cache keys generated/verified.
    """
    from backend.app.speech.cache import compute_cache_key, tts_cache
    from backend.app.speech.tts import get_tts_provider
    from backend.app.speech.voices import get_voice

    active_tts = tts or get_tts_provider()
    active_cache = cache or tts_cache

    if catalog_path is None:
        catalog_path = Path(__file__).parents[3] / "content" / "messages_hi.yaml"
    else:
        catalog_path = Path(catalog_path)

    keys_prewarmed: list[str] = []
    default_voice = get_voice("abhyas")

    # 1. Load catalog messages marked audio: true
    if catalog_path.is_file():
        try:
            with open(catalog_path, encoding="utf-8") as f:
                data: dict[str, Any] = yaml.safe_load(f) or {}

            for _msg_key, val in data.items():
                if not isinstance(val, dict):
                    continue
                if not val.get("audio"):
                    continue

                for field_name in ("text", "text_m"):
                    text_content = val.get(field_name)
                    if not text_content or not isinstance(text_content, str):
                        continue
                    # Skip templated lines with placeholders (e.g., {name})
                    if "{" in text_content and "}" in text_content:
                        continue

                    ckey = compute_cache_key(
                        text_content, default_voice.provider_speaker, default_voice
                    )
                    if not active_cache.has(ckey, "wav"):
                        wav_bytes = await active_tts.synthesize(text_content, default_voice)
                        if wav_bytes:
                            await active_cache.put_wav(ckey, wav_bytes)
                    keys_prewarmed.append(ckey)
        except Exception as exc:
            logger.warning("Error reading message catalog for prewarming: %s", exc)

    # 2. Prewarm any extra lines (e.g. learn scripts, model rehearsal lines)
    if extra_lines:
        for voice_id, line in extra_lines:
            voice = get_voice(voice_id)
            ckey = compute_cache_key(line, voice.provider_speaker, voice)
            if not active_cache.has(ckey, "wav"):
                wav_bytes = await active_tts.synthesize(line, voice)
                if wav_bytes:
                    await active_cache.put_wav(ckey, wav_bytes)
            keys_prewarmed.append(ckey)

    return keys_prewarmed


__all__ = [
    "SpeechBudgetExceededError",
    "calculate_stt_cost",
    "calculate_tts_cost",
    "SpeechBudgetTracker",
    "speech_budget",
    "prewarm_fixed_audio",
]
