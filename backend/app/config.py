"""Application configuration and centralized threshold registry.

Strictly follows AGENTS.md, spec/02_architecture.md, and all spec files:
- All thresholds and configuration constants reside here - no magic numbers anywhere else.
- Provider selection logs mocks in development; fail-fast on missing secrets in production.
"""

import logging
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("abhyas.config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Server & Environment ──────────────────────────────────────────────
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    LOG_LEVEL: str = "INFO"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    GIT_SHA: str = "dev"

    # ── Database ─────────────────────────────────────────────────────────
    # Supabase session pooler in prod; docker compose locally
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/abhyas"
    ALEMBIC_DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/abhyas"

    # ── Security & Authentication ────────────────────────────────────────
    SESSION_SECRET: str = (
        "dev_session_secret_change_in_production_min_64_chars_length_required_here"
    )
    PHONE_HASH_SALT: str = "dev_phone_hash_salt_32_chars_ok"
    PHONE_ENC_KEY: str = "P5sUu77tT3i8_R1m2tZ_7lqf4xL6D-0K0A5vG4J-7-8="
    DEMO_PASSWORD: str = "abhyas-demo-2026"
    ADMIN_PASSWORD: str = "abhyas-admin-2026"
    TRUSTED_PROXY_IPS: str = "127.0.0.1"
    MAX_LOGIN_ATTEMPTS_PER_MINUTE: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 60
    CHAT_MAX_MESSAGES_PER_MINUTE: int = 20
    CHAT_RATE_LIMIT_WINDOW_SECONDS: int = 60

    # ── Claude (Anthropic) — H1 ──────────────────────────────────────────
    LLM_PROVIDER: Literal["anthropic", "mock"] = "anthropic"
    LLM_CALL_LOG_ENABLED: bool = True
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL_FAST: str = "claude-haiku-5-5"
    CLAUDE_MODEL_SMART: str = "claude-sonnet-5-5"
    CLAUDE_MODEL_BUILD: str = "claude-sonnet-5-5"
    LLM_DAILY_TOKEN_BUDGET: int = 3_000_000
    LLM_TIMEOUT_SECONDS: float = 8.0
    LLM_BUILD_TIMEOUT_SECONDS: float = 60.0
    LLM_MAX_RETRIES: int = 1

    # ── Speech (STT / TTS / Audio) — H2 ──────────────────────────────────
    STT_PROVIDER: Literal["sarvam", "bhashini", "google", "mock"] = "sarvam"
    TTS_PROVIDER: Literal["sarvam", "mock"] = "sarvam"
    SARVAM_API_KEY: str = ""
    SARVAM_BASE_URL: str = "https://api.sarvam.ai"
    SARVAM_STT_MODEL: str = "saaras:v4"
    SARVAM_TTS_MODEL: str = "bulbul:v3"
    BHASHINI_USER_ID: str = ""
    BHASHINI_API_KEY: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    MOCK_STT_TEXT: str = "रवि, 52 में से 17 कैसे घटाया? बताओ।"
    STT_TIMEOUT_S: float = 8.0
    STT_MIN_CONFIDENCE: float = 0.50
    MAX_INBOUND_AUDIO_S: int = 90
    EXPLAIN_BACK_MAX_SECONDS: int = 60
    REHEARSE_TURN_MAX_S: int = 30
    LEARN_AUDIO_MAX_SECONDS: int = 120
    SPEECH_PROVIDER_LIVE: bool = False
    SPEECH_DAILY_BUDGET_INR: float = 50.0
    SPEECH_TOTAL_BUDGET_INR: float = 500.0
    STT_COST_PER_MINUTE_INR: float = 0.50
    TTS_COST_PER_1000_CHARS_INR: float = 3.0

    # ── WhatsApp Cloud API (Meta) — H4/H5 ────────────────────────────────
    WHATSAPP_ENABLED: bool = False
    WHATSAPP_GRAPH_VERSION: str = "v23.0"
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "abhyas_webhook_verify_token"
    WHATSAPP_DISPLAY_NUMBER: str = ""
    WHATSAPP_UTILITY_COST_INR: float = 0.12

    # ── Retrieval (Dense Vectors & Hybrid Search) — H16 ──────────────────
    VOYAGE_API_KEY: str = ""
    VOYAGE_MODEL: str = "voyage-multilingual-2"
    RETRIEVAL_TOP_K: int = 5
    RETRIEVAL_MIN_SCORE: float = 0.25
    QUOTE_FUZZY_MIN: float = 90.0

    # ── Pedagogical & Rule Engine Thresholds ──────────────────────────────
    MAX_TURNS_PER_REHEARSAL: int = 8
    SHY_SILENT_TURNS: int = 1
    MAX_REHEARSAL_RETRIES_PER_WEEK: int = 3
    COACH_CONFIDENCE_THRESHOLD: float = 0.60
    FIDELITY_CONFIDENCE_THRESHOLD: float = 0.60
    GUIDE_CONFIDENCE_THRESHOLD: float = 0.60
    MAX_CHILD_LINE_WORDS: int = 25
    MAX_COACH_FEEDBACK_WORDS: int = 60
    MAX_GUIDE_ANSWER_WORDS: int = 80
    MOVE_APPROVALS_REQUIRED: int = 2
    KAPPA_CALIBRATION_TARGET: float = 0.70

    # ── Reporting & Privacy Thresholds ────────────────────────────────────
    AGGREGATION_SUPPRESSION_N: int = 10
    LATENCY_P95_TARGET_MS: int = 20_000
    TWO_DAY_FOLLOWUP_HOURS: int = 48
    REMINDER_AFTER_HOURS: int = 72

    # ── Scheduler & Jobs — T24 ───────────────────────────────────────────
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_TICK_SECONDS: int = 60
    SCHEDULER_PLAN_MINUTES: int = 60
    SCHEDULER_MAX_ATTEMPTS: int = 3
    SCHEDULER_RETRY_BASE_SECONDS: int = 60
    SCHEDULER_BATCH_LIMIT: int = 25
    AGGREGATES_HOUR_IST: int = 2
    ARP_DIGEST_WEEKDAY: int = 5  # Saturday
    ARP_DIGEST_HOUR_IST: int = 17
    FOLLOWUP_TOPIC_MAX_WORDS: int = 6

    # ── Demo / Evaluation & Observability ────────────────────────────────
    SERVE_IN_REVIEW_TO_DEMO: bool = True
    DEMO_MODE: bool = True
    SENTRY_DSN: str = ""

    @model_validator(mode="after")
    def validate_production_and_mocks(self) -> "Settings":
        # 1. Fail-fast in production if required secrets are missing
        if self.ENVIRONMENT == "production":
            missing: list[str] = []
            if not self.ANTHROPIC_API_KEY and self.LLM_PROVIDER == "anthropic":
                missing.append("ANTHROPIC_API_KEY")
            if not self.SARVAM_API_KEY and (
                self.STT_PROVIDER == "sarvam" or self.TTS_PROVIDER == "sarvam"
            ):
                missing.append("SARVAM_API_KEY")
            if self.WHATSAPP_ENABLED:
                if not self.WHATSAPP_ACCESS_TOKEN:
                    missing.append("WHATSAPP_ACCESS_TOKEN")
                if not self.WHATSAPP_PHONE_NUMBER_ID:
                    missing.append("WHATSAPP_PHONE_NUMBER_ID")
                if not self.WHATSAPP_APP_SECRET:
                    missing.append("WHATSAPP_APP_SECRET")
            if self.DEMO_PASSWORD == "abhyas-demo-2026":
                missing.append("DEMO_PASSWORD (must rotate in production)")
            if not self.SESSION_SECRET or self.SESSION_SECRET.startswith("dev_"):
                missing.append("SESSION_SECRET")
            if not self.PHONE_HASH_SALT or self.PHONE_HASH_SALT.startswith("dev_"):
                missing.append("PHONE_HASH_SALT")
            if (
                not self.PHONE_ENC_KEY
                or self.PHONE_ENC_KEY == "P5sUu77tT3i8_R1m2tZ_7lqf4xL6D-0K0A5vG4J-7-8="
            ):
                missing.append("PHONE_ENC_KEY")
            if not self.ADMIN_PASSWORD or self.ADMIN_PASSWORD == "abhyas-admin-2026":
                missing.append("ADMIN_PASSWORD")

            if missing:
                err_msg = (
                    f"Production startup failed: required secrets missing or insecure: {', '.join(missing)}. "
                    "Provide these environment variables before starting in production."
                )
                logger.critical(err_msg)
                raise ValueError(err_msg)

        # 2. In development or test, log active mocks for absent keys
        else:
            if not self.ANTHROPIC_API_KEY:
                logger.info("MOCK MODE active: ANTHROPIC_API_KEY empty -> LLM using MockLLM")
            if not self.SARVAM_API_KEY:
                logger.info("MOCK MODE active: SARVAM_API_KEY empty -> STT/TTS using mock audio")
            if not self.VOYAGE_API_KEY:
                logger.info("BM25 ONLY active: VOYAGE_API_KEY empty -> Dense retrieval skipped")

        return self


# Global singleton settings
settings = Settings()
