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
    # Teacher turns a scene needs before the coach gives feedback (shorter scenes offer continue/skip)
    MIN_TURNS_FOR_COACH_GROUP: int = 3
    MIN_TURNS_FOR_COACH_ONE_ON_ONE: int = 2
    # Login skips a demo reset done this recently when nothing was written since (double login)
    DEMO_RESET_DEBOUNCE_SECONDS: int = 60
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
    # After a provider answers 429 / quota exceeded, calls skip it for this long and go
    # straight to the fallback (no failed call and no wasted seconds per voice note)
    SPEECH_RATE_LIMIT_COOLDOWN_S: int = 60
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

    # ── "Ask the handbook" chips (content/handbook_questions.yaml) ───────────
    HANDBOOK_QUESTIONS_MIN: int = 8
    HANDBOOK_QUESTIONS_MAX: int = 12
    HANDBOOK_CHIPS_SHOWN: int = 4  # chosen per teacher per day, deterministic
    HANDBOOK_VALIDATION_TOP_K: int = 5  # each question's chunk must be in the BM25 top K
    HANDBOOK_ASK_PREFIX: str = "सवाल:"  # the ask keyword a chip puts before its question
    # A tip on each module's learning step uses the same gates as the coach's source suggestion
    HANDBOOK_TIP_POOL: int = 60
    HANDBOOK_TIP_CANDIDATES: int = 3

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
    # "What do you want to get better at?" (content/teaching_skills.yaml)
    TEACHING_SKILLS_MAX: int = 2  # most skills a teacher keeps
    TEACHING_SKILL_CLASSIFIER_MIN_CONFIDENCE: float = 0.50
    TEACHING_SKILL_CLASSIFIER_MAX_TOKENS: int = 192
    SKILL_PROGRESS_MIN_SCENES: int = 2  # scenes scored on a skill before before/after is shown
    SKILL_LEVEL_MAX: int = 2  # rubric levels run 0..2
    CLASS_HELPED_MAX_UNCLEAR: int = (
        1  # unclear replies to "did it help your class?" before moving on
    )

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

    # ── V2 features (each ON in demo mode, OFF by default otherwise: see `v2_enabled`) ──
    CLASS_CHECKIN_ENABLED: bool = False  # "After class: how did it go?" closed-list check-in
    CHECKIN_MAX_BUTTONS: int = 5  # WEB cap: most buttons on one check-in screen ("more" counts)
    WEB_BUTTON_TITLE_MAX: int = 40  # web chat: longest button title kept as written
    WHATSAPP_REPLY_BUTTONS_MAX: int = 3  # Meta limit: reply buttons in one message
    WHATSAPP_BUTTON_TITLE_MAX: int = 20  # Meta limit: reply-button / list-row title length
    WHATSAPP_LIST_ROWS_MAX: int = 10  # Meta limit: rows in one interactive list
    CHECKIN_DEDUPE_SECONDS: int = 60  # the same check-in inside this window is stored once
    LEVEL_SORTER_ENABLED: bool = False  # "Group my class by level": counts per level -> 2-3 groups
    LEVEL_BUCKET_COUNTS: dict[str, int] = {  # tapped range -> the count used to size groups
        "0": 0,
        "1_5": 3,
        "6_10": 8,
        "11_20": 15,
        "20p": 25,
    }
    LEVEL_MAX_GROUPS: int = 3  # most groups the sorter proposes (adjacent small levels merge)
    LEVEL_ACTIVITY_MINUTES: int = 10  # length of the one activity shown per group
    TALK_MOVES_ENABLED: bool = False  # coach feedback adds a talk-move line from the tagged acts
    CLUSTER_PACK_ENABLED: bool = False  # ARP/trainer "Cluster meeting pack" from check-in counts
    CLUSTER_PACK_WINDOW_DAYS: int = 30  # check-ins counted: the last this many days
    CLUSTER_PACK_TOP: int = 2  # struggles named in the pack

    # ── V3 features (same pattern: ON in demo mode, OFF otherwise) ──
    FOLLOWUP_ENABLED: bool = False  # next-school-day "how did the practice go?" after a struggle
    FOLLOWUP_MAX_AGE_DAYS: int = 7  # a follow-up due longer ago than this is no longer offered
    FOLLOWUP_SCHOOL_DAYS: tuple[int, ...] = (0, 1, 2, 3, 4, 5)  # weekday numbers, Monday to Saturday
    OBSERVATION_ENABLED: bool = False  # ARP visit checklist and "reported vs observed"
    ADAPTIVE_PATH_ENABLED: bool = False  # next practice chosen from check-ins and follow-ups
    ADAPTIVE_MOST_WEIGHT: int = 3  # a "most struggled" check-in
    ADAPTIVE_SOME_WEIGHT: int = 1  # a "some struggled" check-in
    ADAPTIVE_STUCK_WEIGHT: int = 2  # a follow-up "still stuck"
    ADAPTIVE_WORKED_WEIGHT: int = 2  # a follow-up "worked" lowers the score by this much
    ADAPTIVE_HISTORY_DAYS: int = 30  # check-ins and follow-ups older than this are ignored
    ADAPTIVE_NEW_TEACHER_BANDS: tuple[str, ...] = ("0-1",)  # experience bands that get model practice first
    OBSERVATION_WINDOW_DAYS: int = 30  # observations and follow-ups counted in "reported vs observed"
    OBSERVATION_ROWS_MAX: int = 3  # struggles shown in "reported vs observed"
    OBSERVATION_TALK_MOVES: tuple[str, ...] = ("named_child", "why_how", "not_told", "think_time")
    OBSERVATION_NEXT_STEPS: tuple[str, ...] = (
        "ask_named",
        "ask_why",
        "hold_answer",
        "wait_time",
        "repeat",
    )
    CLUSTER_PACK_AGENDA_MINUTES: tuple[int, int, int, int] = (5, 15, 10, 5)  # share, practise, read, plan
    CHILD_STRIP_ENABLED: bool = (
        False  # scene bar shows each child's state label (stuck / getting it / got it)
    )

    # ── Track B features (same pattern: ON in demo mode, OFF otherwise) ──
    SCENE_NUM_COMPARE_ENABLED: bool = False  # practice scene: comparing two-digit numbers
    COMPARE_MIN_OPERAND: int = 1  # smallest number the teacher may pose in the comparing scene
    SCENE_LIT_LETTER_SOUND_ENABLED: bool = False  # practice scene: confusable Hindi letter sounds
    TRAINING_GAP_ENABLED: bool = False  # trainer view: "Where training is not landing"
    TRAINING_GAP_WINDOW_DAYS: int = 30  # rehearsals counted: the last this many days
    FOCUS_CARD_ENABLED: bool = False  # "आज का सुझाव": one cited step when an opted-in teacher opens the chat
    FOCUS_OFFER_INTERVAL_DAYS: int = 7  # the opt-in is offered at most once in this many days
    FAST_START_ENABLED: bool = False  # experienced teachers may go straight to practice
    FAST_START_BANDS: tuple[str, ...] = ("6-10", "10+")  # experience bands offered the shortcut
    MODEL_AUDIO_ENABLED: bool = False  # model-practice message carries cached audio when it exists

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


def v2_enabled(flag: bool) -> bool:
    """A v2 feature flag is on when set, or in demo mode (the hosted judge-facing site)."""
    return bool(flag or settings.DEMO_MODE)


# Track B practice scenes: the move card always exists on disk (content and tests read it), but
# the scene is offered (check-in practice button, move path) only while its flag is on.
FLAGGED_MOVES: dict[str, str] = {
    "NUM_COMPARE_BUNDLES": "SCENE_NUM_COMPARE_ENABLED",
    "LIT_LETTER_SOUND_PAIRS": "SCENE_LIT_LETTER_SOUND_ENABLED",
}


def move_offered(move_id: str | None) -> bool:
    """False for a flag-gated Track B move whose flag is off; True for every other move."""
    flag = FLAGGED_MOVES.get(move_id or "")
    return True if flag is None else v2_enabled(bool(getattr(settings, flag)))
