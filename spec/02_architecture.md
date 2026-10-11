# 02 — Architecture

## 2.1 Layers (this is what evaluators score — keep it visible in code and docs)

```
INPUT            CONTEXT                 REASONING (Claude)        GUARDRAILS               EVALUATION            OUTPUT
voice note  ──►  session state,      ──► intent_router        ──►  JSON schema validate ──► latency log       ──► TTS voice reply
text        ──►  move card, rubric,  ──► act_tagger           ──►  number/answer guard  ──► guard-failure log ──► text (always)
button      ──►  child states,       ──► child_voice (renders ──►  quote-exists guard   ──► coach-vs-expert   ──► buttons
                 retrieved guide         rule-engine output)       sources ⊆ retrieved      kappa harness      ──► ARP digest
                 chunks (RAG),       ──► coach                ──►  length / tone guard  ──► realism ratings   ──► trainer view
                 teacher history     ──► fidelity_checker     ──►  confidence → human   ──► evidence ladder
                                     ──► guide_answerer            review queue
                 DETERMINISTIC: rule engine computes every child answer (no LLM)
```

## 2.2 Runtime data flow — one rehearsal turn

```
Teacher voice (OGG/Opus or WebM)  ──► Channel adapter (WhatsApp webhook | Web upload)
   └─► persist message (no audio), enqueue turn (BackgroundTask)
        └─► audio.normalize (ffmpeg → 16 kHz mono WAV, in memory) ──► STT ──► transcript (audio bytes discarded)
             └─► ConversationService.handle(inbound)  [loads session_state]
                  ├─ state == REHEARSE ─► SceneRunner.turn(transcript)
                  │     ├─► act_tagger (Claude Haiku, JSON) → {acts, addressed_child, problem, quote}
                  │     ├─► RuleEngine.step(scene, acts, addressed, problem)  → ChildResult(s)   [pure, deterministic]
                  │     ├─► child_voice (Claude Haiku, JSON) → line_hi  ──► guard ──► (retry once) ──► template fallback
                  │     ├─► TTS (child voice + pitch shift) → OGG/Opus
                  │     └─► persist turn (transcript, acts, rule_result, latency_ms)
                  └─ other states ─► StateMachine handlers (05/08)
        └─► Channel.send(text first, then audio, then buttons)
```

Latency budget (p95 target 20 s): STT ≤ 4 s · act_tagger ≤ 2.5 s · engine < 50 ms · child_voice ≤ 2.5 s · TTS ≤ 3 s · channel I/O ≤ 4 s · slack 4 s. Run act_tagger with **prompt caching** on the static system prompt. Start TTS as soon as the guard passes; send the text line immediately (before TTS) on the web channel.

## 2.3 Stack (pinned decisions — do not re-decide)

| Concern | Choice |
|---|---|
| Language | Python 3.11 |
| Web framework | FastAPI + Uvicorn (single service: API + server-rendered pages + webhook + scheduler) |
| Templates / front-end | Jinja2 + vanilla JS + one CSS file; PWA (manifest + service worker) for the teacher chat |
| DB | Supabase Postgres 15 + `pgvector`; SQLAlchemy 2 async (`asyncpg`) + Alembic. Local: docker compose `pgvector/pgvector:pg16` |
| Background work | FastAPI `BackgroundTasks` for per-message processing; **APScheduler (AsyncIOScheduler)** for timed jobs, backed by a `scheduled_job` table so restarts are safe. **No Redis.** Remove `arq`/`redis` deps from the scaffold |
| LLM | Anthropic Python SDK. Runtime fast roles: `claude-haiku-5-5`. Scoring roles: `claude-sonnet-5-5`. Build-time content: `claude-sonnet-5-5` (or `claude-opus-5-5` if credits allow). All via env vars. Structured output via **tool use with forced `tool_choice`** |
| Retrieval | BM25 (`rank_bm25`) over Hindi-tokenised chunks — always on. Optional dense vectors (`VOYAGE_API_KEY` → `voyage-multilingual-2`, 1024-d) stored in `pgvector`; hybrid = reciprocal rank fusion |
| STT | Adapter. Default hosted: **Sarvam AI** speech-to-text (`saarika`), `hi-IN`. Alternatives behind same interface: Bhashini, Google Cloud STT. Mock for tests |
| TTS | Adapter. Default hosted: **Sarvam AI** text-to-speech (`bulbul`), `hi-IN`. Child voices = adult/young speaker + ffmpeg pitch shift. Mock = pre-generated sine/beep WAV + text |
| Audio | `ffmpeg` binary (in Docker image) via `asyncio.create_subprocess_exec`; in-memory pipes; never write user audio to disk except tmpfs during conversion, deleted in `finally` |
| Hindi text | `indic-nlp-library` optional; required: `regex` (for `\X` grapheme clusters), `unicodedata` NFC, own number-word parser |
| Fuzzy matching | `rapidfuzz` |
| Auth (web) | Username + password (bcrypt via `passlib`), signed session cookie (`itsdangerous`), role-based route guards. Teachers on WhatsApp identified by **salted SHA-256 phone hash** |
| Hosting | Render (Docker web service, **Starter plan, not free** — free sleeps and evaluators would hit cold starts) + Supabase (free tier ok) |
| CI | GitHub Actions: ruff, mypy, pytest, gitleaks |
| Licence | MIT |

## 2.4 Repository layout (target — refactor the scaffold to this)

```
abhyas/
├── AGENTS.md  CLAUDE.md(→ copy of AGENTS.md)  PROGRESS.md  README.md  LICENSE  Makefile
├── spec/                         # this build pack
├── .env.example  pyproject.toml  alembic.ini  .pre-commit-config.yaml  .gitleaks.toml
├── .github/workflows/ci.yml
├── backend/
│   ├── app/
│   │   ├── main.py               # app factory, routers, lifespan (scheduler start/stop, content load)
│   │   ├── config.py             # Settings + every threshold
│   │   ├── deps.py               # DI: db session, current_user, providers
│   │   ├── logging.py            # structured JSON logs, request ids, PII scrubbing
│   │   ├── core/
│   │   │   ├── conversation.py   # ConversationService.handle(inbound) — channel-agnostic brain
│   │   │   ├── intents.py        # keyword intents + intent_router call
│   │   │   ├── messages.py       # Hindi message catalog loader (content/messages_hi.yaml)
│   │   │   └── types.py          # InboundMessage, OutboundMessage, Button
│   │   ├── channels/
│   │   │   ├── base.py           # Channel protocol
│   │   │   ├── web.py            # WebChannel (writes outbound to DB; client polls/SSE)
│   │   │   └── whatsapp/         # client.py, webhook.py, security.py, templates.py, media.py
│   │   ├── speech/               # audio.py (ffmpeg), stt.py, tts.py, voices.py, cache.py
│   │   ├── sessions/             # state_machine.py, handlers/*.py, placement.py, path.py, window.py (24 h rule)
│   │   ├── rehearsal/            # scene_runner.py (tagger → engine → voice → tts), scene_store.py
│   │   ├── rule_engine/          # PURE: no I/O, no LLM. states.py, transitions.py, engine.py, problems.py,
│   │   │   └── bugs/             #   math.py, reading.py, registry.py, akshar.py
│   │   ├── llm/
│   │   │   ├── client.py         # Anthropic wrapper: timeout, retry, tool-forced JSON, caching, call log
│   │   │   ├── roles/            # one module per role: build messages, call, validate, guard, fallback
│   │   │   ├── prompts/          # <role>.v<N>.md  (versioned prompt text; loaded at startup)
│   │   │   ├── schemas.py        # pydantic output models per role
│   │   │   ├── guards.py         # all guard functions (pure)
│   │   │   └── hindi_numbers.py  # Devanagari digits + Hindi number words 0–100 ↔ int
│   │   ├── retrieval/            # ingest.py (PDF → chunks), bm25.py, dense.py, search.py
│   │   ├── scoring/              # coach.py, fidelity.py, evidence.py
│   │   ├── reports/              # arp_digest.py, trainer.py (aggregates + suppression)
│   │   ├── jobs/                 # scheduler.py, handlers.py (weekly_prompt, followup, reminder, digest, retention)
│   │   ├── privacy/              # consent.py, retention.py, hashing.py
│   │   ├── auth/                 # passwords.py, sessions.py, guards.py
│   │   ├── web/                  # routers: teacher.py, arp.py, trainer.py, review.py, admin.py, api.py
│   │   │   ├── templates/        # Jinja2
│   │   │   └── static/           # app.css, chat.js, recorder.js, sw.js, manifest.json, icons, cached audio
│   │   └── db/                   # base.py, models.py, session.py, migrations/ (Alembic), seed.py, demo_data.py
│   └── tests/                    # unit/, integration/, golden/ (LLM golden outputs), fixtures/
├── content/
│   ├── moves/*.yaml  personas/*.yaml  messages_hi.yaml  whatsapp_templates.yaml
│   ├── schemas/*.json            # JSON Schema for move, persona (generated from pydantic)
│   ├── sources/                  # HUMAN INPUT: official PDFs (gitignored if licence unclear) + sources.yaml manifest
│   ├── chunks/                   # ingested guide chunks (jsonl), committed
│   └── pipeline/                 # generate.py, validate.py, review.py, publish.py
├── eval/
│   ├── calibration/  latency/  realism/  samples/  user_testing/   # each with README + scripts + REPORT.md
├── infra/  Dockerfile  docker-compose.yml  render.yaml
└── docs/  deck_outline.md  video_script.md  demo_runbook.md
```

Delete top-level `review-console/` and `trainer-view/` (merged into `backend/app/web/`). Move `content/rules/*.py` into `backend/app/rule_engine/bugs/`. Keep one spec: delete `ARCHITECTURE.md`, `Abhyas_ARCHITECTURE.md` and the `.docx` from the repo (the build pack replaces them).

## 2.5 Module contracts (key interfaces)

```python
# core/types.py
class InboundMessage(BaseModel):
    channel: Literal["whatsapp", "web"]
    channel_msg_id: str              # idempotency key
    teacher_id: UUID
    kind: Literal["text", "audio", "button"]
    text: str | None = None          # for text, or transcript after STT
    button_id: str | None = None
    audio_bytes: bytes | None = Field(default=None, exclude=True)  # never persisted
    audio_mime: str | None = None
    received_at: datetime

class Button(BaseModel): id: str; title_hi: str    # title ≤ 20 chars (WhatsApp limit)

class OutboundMessage(BaseModel):
    kind: Literal["text", "audio", "buttons", "template"]
    text_hi: str | None = None
    audio_ref: str | None = None     # cache key of TTS audio
    buttons: list[Button] = []       # ≤ 3
    template_name: str | None = None
    template_params: list[str] = []
    speaker: str | None = None       # "abhyas" | persona id | "model_teacher" | "coach"

# channels/base.py
class Channel(Protocol):
    name: str
    async def send(self, teacher: Teacher, msgs: list[OutboundMessage]) -> None: ...
    async def can_send_freeform(self, teacher: Teacher) -> bool: ...   # 24-h window (always True for web)

# core/conversation.py
class ConversationService:
    async def handle(self, inbound: InboundMessage) -> list[OutboundMessage]: ...
```

`ConversationService` never imports a channel. Channels never import session logic. The rule engine imports nothing outside `rule_engine/`.

## 2.6 Failure behaviour (graceful degradation)

| Failure | Behaviour |
|---|---|
| STT fails / timeout | reply text: "आवाज़ साफ़ नहीं आई, कृपया फिर से बोलें या लिखकर भेजें।" — state unchanged |
| STT confidence < `STT_MIN_CONFIDENCE` | echo transcript and ask confirm with buttons [हाँ, सही है] [फिर से बोलूँगी] |
| Claude timeout/error | one retry; then template fallback for that role (05); log `llm_fallback` |
| TTS fails | send text only; mark `audio_failed`; never block the turn |
| WhatsApp send fails | retry with exponential backoff (3 tries); then log + admin dashboard alert |
| DB unavailable | 503 to webhook (Meta retries); web shows offline banner |
| Retrieval returns nothing above threshold | escalate to ARP queue; tell teacher so |
