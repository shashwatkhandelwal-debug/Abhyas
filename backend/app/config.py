"""Application configuration and centralized threshold registry.

Strictly follows Section 18 of ARCHITECTURE.md:
All thresholds and configuration constants reside here - no magic numbers anywhere in the codebase.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server Environment
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    LOG_LEVEL: str = "INFO"

    # Database & Cache
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/abhyas"
    SYNC_DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/abhyas"
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM Settings (Anthropic Claude)
    ANTHROPIC_API_KEY: str = "mock-key-for-scaffold"
    CLAUDE_MODEL: str = "claude-3-7-sonnet-20250219"
    LLM_TIMEOUT_SECONDS: float = 8.0
    LLM_MAX_RETRIES: int = 1

    # WhatsApp Business Cloud API & BSP
    WHATSAPP_VERIFY_TOKEN: str = "abhyas_webhook_verify_token_secure"
    WHATSAPP_ACCESS_TOKEN: str = "mock_whatsapp_token"
    WHATSAPP_PHONE_NUMBER_ID: str = "mock_phone_id"
    WHATSAPP_APP_SECRET: str = "mock_secret"
    BSP_PROVIDER: Literal["gupshup", "meta_direct", "mock"] = "gupshup"
    BSP_API_KEY: str = "mock_bsp_key"

    # Speech Processing
    STT_PROVIDER: Literal["indic_conformer", "hosted_api", "mock"] = "mock"
    STT_ENDPOINT: str = "http://localhost:8001/transcribe"
    STT_API_KEY: str = ""

    TTS_PROVIDER: Literal["indic_parler_tts", "hosted_api", "mock"] = "mock"
    TTS_ENDPOINT: str = "http://localhost:8002/synthesize"
    TTS_API_KEY: str = ""

    # =========================================================================
    # Pedagogical & System Thresholds (Per ARCHITECTURE.md Specification)
    # =========================================================================
    # Latency: voice note in -> voice reply out < 20s for 95% of turns (§0, §15)
    LATENCY_P95_TARGET_MS: int = 20000

    # Coach confidence threshold: < 0.6 routes to expert review queue (§5.3, §8)
    COACH_CONFIDENCE_THRESHOLD: float = 0.60

    # Privacy & Reporting: suppress groups < 10 for DIET/SCERT trainer views (§0, §12, §13)
    AGGREGATION_SUPPRESSION_N: int = 10

    # Rehearsal turn budget: max 8 teacher turns per rehearsal scene (§5.2)
    MAX_TURNS_PER_REHEARSAL: int = 8

    # Rehearsal retries: maximum 3 rehearsal retries per teacher per week (§4)
    MAX_REHEARSAL_RETRIES_PER_WEEK: int = 3

    # Follow-up job delay for "Ask Any Time" questions: 2 days (§8)
    TWO_DAY_FOLLOWUP_HOURS: int = 48

    # Spoken audio durations (§0, §3.3)
    EXPLAIN_BACK_MAX_SECONDS: int = 60
    LEARN_AUDIO_MAX_SECONDS: int = 120

    # Output speech length guards (§5.1, §5.3, §8)
    MAX_CHILD_LINE_WORDS: int = 25
    MAX_COACH_FEEDBACK_WORDS: int = 60
    MAX_GUIDE_ANSWER_WORDS: int = 80

    # Coach evaluation calibration target (§5.3, §15)
    KAPPA_CALIBRATION_TARGET: float = 0.70


settings = Settings()
