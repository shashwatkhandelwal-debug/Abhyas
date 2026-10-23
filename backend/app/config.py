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
    # Render Postgres (internal URL, postgresql+asyncpg://) in prod; docker compose locally
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
    # Logout resets the shared demo teachers; rows younger than this are session-made, older are seed
    DEMO_RESET_SEED_MIN_AGE_HOURS: int = 24
    TRUSTED_PROXY_IPS: str = "127.0.0.1"
    MAX_LOGIN_ATTEMPTS_PER_MINUTE: int = 5  # failed attempts per (IP, username) per window
    MAX_LOGIN_FAILURES_PER_IP_PER_MINUTE: int = 30  # failed attempts per IP across usernames
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
    # Pricing as-of 2026-10: https://platform.claude.com/docs/en/about-claude/pricing
    HAIKU_INPUT_USD_PER_MTOK: float = 0.10
    HAIKU_OUTPUT_USD_PER_MTOK: float = 0.50
    HAIKU_CACHE_READ_USD_PER_MTOK: float = 0.01
    SONNET_INPUT_USD_PER_MTOK: float = 2.0
    SONNET_OUTPUT_USD_PER_MTOK: float = 10.0
    SONNET_CACHE_READ_USD_PER_MTOK: float = 0.10
    USD_TO_INR: float = 88.0  # assumption, update before submission
    LLM_DAILY_TOKEN_BUDGET: int = 3_000_000
    LLM_TIMEOUT_SECONDS: float = 8.0
    LLM_BUILD_TIMEOUT_SECONDS: float = 60.0
    LLM_MAX_RETRIES: int = 1
    # Devanagari costs ~4 tokens/word plus tool-call overhead: a 25-word child line needs
    # ~110 output tokens, so 128 truncated to {} (spec/05 role budgets live here).
    LLM_MAX_TOKENS_CEILING: int = 1024
    # With tool_choice=auto, claude-sonnet-5-5 writes a short text preamble before the tool call
    # (measured 650-770 output tokens for the coach vs 1024 max_tokens); give it headroom.
    LLM_AUTO_TOOL_CHOICE_TOKEN_HEADROOM: int = 512
    ACT_TAGGER_MAX_TOKENS: int = 512
    CHILD_VOICE_MAX_TOKENS: int = 384
    GUARD_EVENT_RING_SIZE: int = 2000
    GUARD_EVENT_REASON_MAX_CHARS: int = 200
    GUARD_EVENT_LOG_PATH: str = ""

    # ── Speech (STT / TTS / Audio) — H2 ──────────────────────────────────
    STT_PROVIDER: Literal["sarvam", "bhashini", "google", "gemini", "mock"] = "sarvam"
    TTS_PROVIDER: Literal["sarvam", "gemini", "mock"] = "sarvam"
    # Tried when the primary raises STTUnavailable / TTSUnavailable; "none" disables the chain
    STT_FALLBACK_PROVIDER: Literal["sarvam", "bhashini", "google", "gemini", "mock", "none"] = (
        "none"
    )
    TTS_FALLBACK_PROVIDER: Literal["sarvam", "gemini", "mock", "none"] = "none"
    GEMINI_API_KEY: str = ""
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    GEMINI_STT_MODEL: str = "gemini-3.8-flash"
    GEMINI_TTS_MODEL: str = "gemini-3.8-flash-tts"
    GEMINI_TTS_VOICE_F: str = "Kore"
    GEMINI_TTS_VOICE_M: str = "Puck"
    # Inline request limit is 20 MB total; cap the base64 audio payload below it
    GEMINI_STT_MAX_BYTES: int = 18_000_000
    GEMINI_STT_MAX_KEYTERMS: int = 50
    GEMINI_STT_COST_INR_PER_MIN: float = 0.0
    GEMINI_TTS_COST_INR_PER_1K_CHARS: float = 0.0
    SARVAM_API_KEY: str = ""
    SARVAM_BASE_URL: str = "https://api.sarvam.ai"
    SARVAM_STT_MODEL: str = "saaras:v4"
    SARVAM_TTS_MODEL: str = "bulbul:v3"
    BHASHINI_USER_ID: str = ""
    BHASHINI_API_KEY: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    MOCK_STT_TEXT: str = "रवि, 52 में से 17 कैसे घटाया? बताओ।"
    STT_TIMEOUT_S: float = 8.0
    # Retries per speech provider call; a primary with a fallback configured gets 0
    SPEECH_MAX_RETRIES: int = 1
    STT_MIN_CONFIDENCE: float = 0.50
    # Web voice recorder (static/recorder.js reads these through #rec-config)
    REC_MAX_SECONDS: int = 60  # auto-stop and send
    REC_MIN_SECONDS: float = 1.0  # shorter recordings are discarded with a hint
    REC_HOLD_MS: int = 400  # press longer than this = hold-to-talk, shorter = tap-to-toggle
    MAX_INBOUND_AUDIO_S: int = 90
    EXPLAIN_BACK_MAX_SECONDS: int = 60
    REHEARSE_TURN_MAX_S: int = 30
    LEARN_AUDIO_MAX_SECONDS: int = 120
    SPEECH_PROVIDER_LIVE: bool = False
    # First-boot voice prewarm (scripts/start.sh -> scripts/prewarm_tts.py, background process)
    PREWARM_ON_BOOT: bool = False
    PREWARM_REQUEST_INTERVAL_SECONDS: float = 7.0  # stays under ~10 requests/min
    PREWARM_MAX_SYNTH_PER_RUN: int = 100  # new clips per boot; the next boot continues
    SPEECH_DAILY_BUDGET_INR: float = 50.0
    SPEECH_TOTAL_BUDGET_INR: float = 500.0
    # Pricing as-of 2026-10: https://docs.sarvam.ai/api-reference-docs/pricing
    STT_COST_PER_HOUR_INR: float = 30.0
    STT_COST_PER_MINUTE_INR: float = 0.50
    TTS_COST_PER_10K_CHARS_INR: float = 30.0
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
    WHATSAPP_PROCESSED_CACHE_SIZE: int = 10_000
    WHATSAPP_TEACHER_CREATION_RATE_LIMIT_PER_MINUTE: int = 10

    # ── Retrieval (Dense Vectors & Hybrid Search) — H16 ──────────────────
    VOYAGE_API_KEY: str = ""
    VOYAGE_MODEL: str = "voyage-multilingual-2"
    RETRIEVAL_TOP_K: int = 5
    # Calibrated on eval/retrieval_questions.yaml: every answerable question scored >= 0.119, 6 of 10
    # off-topic ones scored < 0.10 (the rest are caught by GUIDE_CONFIDENCE_THRESHOLD in the answerer).
    RETRIEVAL_MIN_SCORE: float = 0.10
    # A chunk is only usable if it shares at least this many distinct (non-stopword) query terms.
    # One shared word ("school", "online", "phone") is how off-topic questions used to leak through
    # the score gate; on-topic questions in eval/retrieval_questions.yaml share >= 2 terms with a
    # relevant chunk (every one that retrieval gets right; recall@5 unchanged at 0.90). A query that
    # has a single content term only needs that one.
    RETRIEVAL_MIN_MATCHED_TERMS: int = 2
    QUOTE_FUZZY_MIN: float = 90.0
    # Source-PDF chunking (offline, make content-ingest)
    CHUNK_MIN_WORDS: int = 150
    CHUNK_TARGET_WORDS: int = 300
    CHUNK_MAX_WORDS: int = 400
    CHUNK_OVERLAP_WORDS: int = 40
    # Page OCR for legacy-font Hindi guides (offline, `python -m backend.app.retrieval.page_ocr`)
    OCR_MAX_IMAGE_EDGE_PX: int = 1568  # longest edge sent to the vision model (no further resize)
    OCR_MAX_OUTPUT_TOKENS: int = 3000
    OCR_CONCURRENCY: int = 4
    OCR_BUDGET_USD: float = 1.50  # hard cap per run; the run aborts before exceeding it
    # claude-haiku-5-5 list price, USD per million tokens (same rates as the Hindi gloss cost
    # reported in content/sources/README.md)
    OCR_PRICE_INPUT_USD_PER_MTOK: float = 0.10
    OCR_PRICE_OUTPUT_USD_PER_MTOK: float = 0.50
    OCR_MAX_ILLEGIBLE_MARKS: int = 6  # pages with more [?] marks than this are flagged unreliable

    # ── On-demand English translation of bubbles ─────────────────────────
    TRANSLATE_MAX_REQUESTS_PER_MINUTE: int = 10
    TRANSLATE_RATE_LIMIT_WINDOW_SECONDS: int = 60
    TRANSLATE_MAX_DEVANAGARI_RATIO: float = 0.05
    TRANSLATE_MIN_WORD_RATIO: float = 0.3
    TRANSLATE_MAX_WORD_RATIO: float = 3.0
    TRANSLATE_MAX_SOURCE_CHARS: int = 2000
    TRANSLATE_MAX_OUTPUT_TOKENS: int = 1500  # Devanagari-heavy sources cost many tokens

    # ── "My class": class-level struggles (content/class_struggles.yaml) ────
    STRUGGLE_MAX_CHOSEN: int = 3  # most struggles a teacher keeps, ordered
    STRUGGLE_LIBRARY_MAX: int = 14  # the library stays small and closed
    STRUGGLE_CHIPS_MIN: int = 8
    STRUGGLE_CHIPS_MAX: int = 10
    STRUGGLE_PHRASE_TOKEN_COVERAGE: float = (
        0.66  # share of a trigger phrase's words that must appear
    )
    STRUGGLE_INPUT_MAX_CHARS: int = 400  # longer free text is cut before matching or classifying
    STRUGGLE_PHRASE_WEIGHT: int = 3  # a whole trigger phrase found in her words
    STRUGGLE_PARTIAL_PHRASE_WEIGHT: int = (
        1  # most of a trigger phrase's words found (not the phrase)
    )
    STRUGGLE_KEYWORD_WEIGHT: int = 2  # a keyword / stem found in her words
    STRUGGLE_MATCH_MIN_SCORE: int = 2  # below this the keyword matcher says "no match"
    STRUGGLE_CLASSIFIER_MIN_CONFIDENCE: float = 0.50
    STRUGGLE_CLASSIFIER_MAX_TOKENS: int = 256

    # ── Pedagogical & Rule Engine Thresholds ──────────────────────────────
    MAX_TURNS_PER_REHEARSAL: int = 8
    MAX_TURNS_ONE_ON_ONE: int = 10  # one child, teacher-led diagnose / teach / check
    SHY_SILENT_TURNS: int = 1
    MAX_REHEARSAL_RETRIES_PER_WEEK: int = 3
    COACH_CONFIDENCE_THRESHOLD: float = 0.60
    FIDELITY_CONFIDENCE_THRESHOLD: float = 0.60
    GUIDE_CONFIDENCE_THRESHOLD: float = 0.60
    MAX_CHILD_LINE_WORDS: int = 25
    # Lines that voice 2-3 reasoning steps (explain_bug, relapse, scaffolded_correct,
    # correct_explained) must carry opener + steps (~20 words, measured on regroup items) +
    # the answer; 25 forced truncation that dropped the answer. 30 words is ~10-12 s of child TTS
    # at ~2.5 words/s, still short enough for a rehearsal turn.
    MAX_CHILD_LINE_WORDS_EXPLAIN: int = 30
    MAX_DISTRACTIONS_PER_SCENE: int = 1
    # Everyday things a distracted child may mention ONLY in an engine-chosen off-topic / interject
    # line; a child answering the lesson must not (the live 1-1 run showed the model adding
    # "अरे मेरा बस्ता..." to explanations, which defeats MAX_DISTRACTIONS_PER_SCENE).
    CHILD_DISTRACTION_WORDS: tuple[str, ...] = (
        "बस्ता",
        "पेंसिल",
        "तितली",
        "चिड़िया",
        "पतंग",
        "खिड़की",
        "बंदर",
        "चप्पल",
        "मेहमान",
        "मिड-डे",
        "टिफिन",
        "गेंद",
        "कुत्ता",
        "बिल्ली",
        "आसमान",
    )
    # Problems the simulated children can handle (the rule engine answers CONFUSED outside it).
    PROBLEM_MIN_OPERAND: int = 10
    PROBLEM_MAX_OPERAND: int = 99
    PROBLEM_MAX_SUM: int = 199
    PROBLEM_MAX_TENS: int = 9
    PROBLEM_MAX_ONES: int = 9
    PROBLEM_MAX_WORD_AKSHARS: int = 4
    MAX_COACH_FEEDBACK_WORDS: int = 60
    COACH_QUOTE_MAX_WORDS: int = 12  # words of the teacher's own line quoted back in feedback
    MAX_GUIDE_ANSWER_WORDS: int = 80
    # A guide answer must share at least this many distinct content terms with the excerpts it
    # cites (excerpt text, heading and Hindi gloss/keywords); otherwise it is not grounded in them.
    GUIDE_MIN_ANSWER_OVERLAP_TERMS: int = 2
    COACH_SUGGESTION_MAX_WORDS: int = 35
    # Modules offered in the picker (a module is a move card with a one-on-one rubric)
    MODULE_IDS: tuple[str, ...] = (
        "NUM_SUB_REGROUP_BUNDLES",
        "NUM_ADD_CARRY_BUNDLES",
        "NUM_PLACE_VALUE_BUNDLES",
    )
    MODULE_CHECK_REPLY_MAX_WORDS: int = 40
    MODULE_CHECK_PASS_MUST_HAVE: int = 2  # must-have key points the closing answer must show
    MODULE_CHECK_MIN_ANSWER_WORDS: int = 4
    COACH_SUGGESTION_SOURCE_ID: str = "nishtha_fln"  # the FLN training package grounds the tip
    COACH_SUGGESTION_CANDIDATES: int = 3
    COACH_SUGGESTION_POOL: int = 60  # retrieved before keeping only the FLN package's chunks
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
    FOLLOWUP_TRY_IN_CLASS_HOURS: int = 48
    RETENTION_PURGE_HOUR_IST: int = 3
    DATA_RETENTION_DAYS: int = 90

    # ── "Rate the training" after REFLECT ────────────────────────────────
    TRAINING_COMMENT_MAX_CHARS: int = 200
    # Unclear replies to the 1-5 rating prompt tolerated before the rating is skipped.
    TRAINING_RATING_MAX_UNCLEAR: int = 1
    TRAINING_RATING_RECENT_COMMENTS: int = 5  # latest comments shown in trainer/admin views

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
            speech_providers = {
                self.STT_PROVIDER,
                self.TTS_PROVIDER,
                self.STT_FALLBACK_PROVIDER,
                self.TTS_FALLBACK_PROVIDER,
            }
            if not self.SARVAM_API_KEY and "sarvam" in speech_providers:
                missing.append("SARVAM_API_KEY")
            if not self.GEMINI_API_KEY and "gemini" in speech_providers:
                missing.append("GEMINI_API_KEY")
            if self.STT_FALLBACK_PROVIDER == "mock":
                missing.append("STT_FALLBACK_PROVIDER (mock not allowed in production)")
            if self.TTS_FALLBACK_PROVIDER == "mock":
                missing.append("TTS_FALLBACK_PROVIDER (mock not allowed in production)")
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
            if not self.GEMINI_API_KEY:
                logger.info(
                    "MOCK MODE active: GEMINI_API_KEY empty -> Gemini STT/TTS using mock audio"
                )
            if not self.VOYAGE_API_KEY:
                logger.info("BM25 ONLY active: VOYAGE_API_KEY empty -> Dense retrieval skipped")

        return self


# Global singleton settings
settings = Settings()
