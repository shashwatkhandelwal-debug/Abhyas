"""Speech cost control, budget tracking, and usage limits (spec/06 §6.4, CHANGES 254f622).

Persists speech spend into the speech_spend table in Postgres.
Survives application restarts by querying today's spend in IST (Asia/Kolkata)
and all-time spend against configured INR budgets.
Supports provider fallback: Sarvam cap reached -> Bhashini (if configured) -> lite mode.
Bhashini is free (records cost 0 INR).
"""

from __future__ import annotations

import datetime
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import func, select

from backend.app.config import settings
from backend.app.db.models import SpeechSpend
from backend.app.db.session import async_session_factory

if TYPE_CHECKING:
    from backend.app.speech.cache import TTSCache
    from backend.app.speech.tts import TTSProvider

logger = logging.getLogger("abhyas.speech.spend")

IST = ZoneInfo("Asia/Kolkata")


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


def calculate_gemini_stt_cost(duration_s: float) -> float:
    """Calculates Gemini STT cost in INR (per-minute rate, default 0.0)."""
    if duration_s <= 0.0:
        return 0.0
    return round((duration_s / 60.0) * settings.GEMINI_STT_COST_INR_PER_MIN, 4)


def calculate_gemini_tts_cost(text: str) -> float:
    """Calculates Gemini TTS cost in INR (per-1k-chars rate, default 0.0)."""
    if not text:
        return 0.0
    return round((len(text) / 1000.0) * settings.GEMINI_TTS_COST_INR_PER_1K_CHARS, 4)


@dataclass
class SpeechBudgetTracker:
    """Tracks daily (IST) and total speech spend against configured INR budgets."""

    daily_spend: float = 0.0
    total_spend: float = 0.0
    last_reset_date: datetime.date = field(
        default_factory=lambda: datetime.datetime.now(IST).date()
    )

    def _check_day_rollover(self) -> None:
        today_ist = datetime.datetime.now(IST).date()
        if today_ist > self.last_reset_date:
            self.daily_spend = 0.0
            self.last_reset_date = today_ist

    async def get_spend_totals_db(self) -> tuple[float, float] | None:
        """Queries Postgres for both daily and all-time speech spend in a single session."""
        if not settings.DATABASE_URL:
            return None
        try:
            now_ist = datetime.datetime.now(IST)
            start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
            start_utc = start_ist.astimezone(datetime.UTC)

            async with async_session_factory() as session:
                stmt_daily = select(func.coalesce(func.sum(SpeechSpend.cost_inr), 0.0)).where(
                    SpeechSpend.at >= start_utc
                )
                stmt_total = select(func.coalesce(func.sum(SpeechSpend.cost_inr), 0.0))
                res_daily = await session.execute(stmt_daily)
                daily_val = float(res_daily.scalar() or 0.0)
                res_total = await session.execute(stmt_total)
                total_val = float(res_total.scalar() or 0.0)
                await session.rollback()
                return daily_val, total_val
        except Exception as exc:
            logger.warning("Could not query speech spend from DB: %s", exc)
            return None

    async def get_daily_spend_db(self) -> float | None:
        """Queries Postgres for total spend incurred today in IST."""
        totals = await self.get_spend_totals_db()
        return totals[0] if totals is not None else None

    async def get_total_spend_db(self) -> float | None:
        """Queries Postgres for all-time speech spend."""
        totals = await self.get_spend_totals_db()
        return totals[1] if totals is not None else None

    async def can_spend(self, amount_inr: float) -> bool:
        """Checks if spending amount_inr is within daily and total budget caps in DB/memory."""
        # Query Postgres if available to ensure spend survives restarts (Item 1)
        totals = await self.get_spend_totals_db()
        daily_db = totals[0] if totals is not None else None
        total_db = totals[1] if totals is not None else None

        if settings.SPEECH_PROVIDER_LIVE:
            # In live mode: fails closed if DB query fails (no in-memory fallback)
            if daily_db is None or total_db is None:
                logger.error(
                    "Database spend query failed in live mode (daily=%s, total=%s). Failing closed.",
                    daily_db,
                    total_db,
                )
                return False
            current_daily = daily_db
            current_total = total_db
            self.daily_spend = current_daily
            self.total_spend = current_total
        else:
            if daily_db is not None and total_db is not None:
                current_daily = daily_db
                current_total = total_db
                self.daily_spend = current_daily
                self.total_spend = current_total
            else:
                self._check_day_rollover()
                current_daily = self.daily_spend
                current_total = self.total_spend

        if current_daily + amount_inr > settings.SPEECH_DAILY_BUDGET_INR:
            return False
        if current_total + amount_inr > settings.SPEECH_TOTAL_BUDGET_INR:
            return False
        return True

    async def record_spend(
        self,
        provider: str,
        kind: str,
        units: int,
        amount_inr: float,
    ) -> None:
        """Records spend in speech_spend table in Postgres and updates in-memory tracker."""
        # Bhashini is free: record cost 0 for it (Item 1)
        if provider.lower() == "bhashini":
            effective_cost = 0.0
        else:
            effective_cost = round(amount_inr, 4)

        # 1. Persist to Postgres speech_spend table
        try:
            async with async_session_factory() as session:
                record = SpeechSpend(
                    id=uuid4(),
                    at=datetime.datetime.now(datetime.UTC),
                    provider=provider,
                    kind=kind,
                    units=units,
                    cost_inr=effective_cost,
                )
                session.add(record)
                await session.commit()
        except Exception as exc:
            logger.error("Could not persist speech spend to DB: %s", exc)

        # 2. Update local tracker
        self._check_day_rollover()
        self.daily_spend = round(self.daily_spend + effective_cost, 4)
        self.total_spend = round(self.total_spend + effective_cost, 4)
        logger.info(
            "Speech spend recorded: [%s:%s] units=%d +%.4f INR (daily: %.4f / %.1f, total: %.4f / %.1f)",
            provider,
            kind,
            units,
            effective_cost,
            self.daily_spend,
            settings.SPEECH_DAILY_BUDGET_INR,
            self.total_spend,
            settings.SPEECH_TOTAL_BUDGET_INR,
        )

    async def check_and_record_stt(self, duration_s: float, provider: str = "sarvam") -> float:
        """Verifies budget and records STT spend if live mode is enabled."""
        if not settings.SPEECH_PROVIDER_LIVE:
            return 0.0
        if provider.lower() == "bhashini":
            await self.record_spend("bhashini", "stt", int(duration_s), 0.0)
            return 0.0

        if provider.lower() == "gemini":
            cost = calculate_gemini_stt_cost(duration_s)
        else:
            cost = calculate_stt_cost(duration_s)
        if not await self.can_spend(cost):
            raise SpeechBudgetExceededError(
                f"STT spend {cost:.4f} INR exceeds budget (daily: {self.daily_spend:.2f}/{settings.SPEECH_DAILY_BUDGET_INR}, total: {self.total_spend:.2f}/{settings.SPEECH_TOTAL_BUDGET_INR})"
            )
        await self.record_spend(provider, "stt", int(duration_s), cost)
        return cost

    async def check_and_record_tts(self, text: str, provider: str = "sarvam") -> float:
        """Verifies budget and records TTS spend if live mode is enabled."""
        if not settings.SPEECH_PROVIDER_LIVE:
            return 0.0
        if provider.lower() == "bhashini":
            await self.record_spend("bhashini", "tts", len(text), 0.0)
            return 0.0

        if provider.lower() == "gemini":
            cost = calculate_gemini_tts_cost(text)
        else:
            cost = calculate_tts_cost(text)
        if not await self.can_spend(cost):
            raise SpeechBudgetExceededError(
                f"TTS spend {cost:.4f} INR exceeds budget (daily: {self.daily_spend:.2f}/{settings.SPEECH_DAILY_BUDGET_INR}, total: {self.total_spend:.2f}/{settings.SPEECH_TOTAL_BUDGET_INR})"
            )
        await self.record_spend(provider, "tts", len(text), cost)
        return cost

    def reset(self) -> None:
        """Resets tracked daily and total spend in memory."""
        self.daily_spend = 0.0
        self.total_spend = 0.0
        self.last_reset_date = datetime.datetime.now(IST).date()


speech_budget = SpeechBudgetTracker()


async def prewarm_fixed_audio(
    tts: TTSProvider | None = None,
    cache: TTSCache | None = None,
    catalog_path: Path | str | None = None,
    extra_lines: list[tuple[str, str]] | None = None,
) -> list[str]:
    """Pre-warms TTS audio cache via explicit script/action (never automatic on startup, Item 3)."""
    from backend.app.speech.audio import to_wav
    from backend.app.speech.cache import tts_cache
    from backend.app.speech.tts import get_tts_provider, tts_cache_key
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
                    if "{" in text_content and "}" in text_content:
                        continue

                    ckey = tts_cache_key(active_tts, text_content, default_voice)
                    if not await active_cache.has(ckey, "wav"):
                        synth_res = await active_tts.synthesize(text_content, default_voice)
                        if synth_res.audio:
                            wav_audio = (
                                synth_res.audio
                                if synth_res.fmt == "wav"
                                else await to_wav(synth_res.audio, fmt=synth_res.fmt)
                            )
                            # Store under the key of the provider that actually synthesized
                            ckey = synth_res.cache_key
                            await active_cache.put_wav(ckey, wav_audio)
                    keys_prewarmed.append(ckey)
        except Exception as exc:
            logger.warning("Error reading message catalog for prewarming: %s", exc)

    # 2. Prewarm any extra lines
    if extra_lines:
        for voice_id, line in extra_lines:
            voice = get_voice(voice_id)
            ckey = tts_cache_key(active_tts, line, voice)
            if not await active_cache.has(ckey, "wav"):
                synth_res = await active_tts.synthesize(line, voice)
                if synth_res.audio:
                    wav_audio = (
                        synth_res.audio
                        if synth_res.fmt == "wav"
                        else await to_wav(synth_res.audio, fmt=synth_res.fmt)
                    )
                    ckey = synth_res.cache_key
                    await active_cache.put_wav(ckey, wav_audio)
            keys_prewarmed.append(ckey)

    return keys_prewarmed


__all__ = [
    "SpeechBudgetExceededError",
    "calculate_stt_cost",
    "calculate_tts_cost",
    "calculate_gemini_stt_cost",
    "calculate_gemini_tts_cost",
    "SpeechBudgetTracker",
    "speech_budget",
    "prewarm_fixed_audio",
]
