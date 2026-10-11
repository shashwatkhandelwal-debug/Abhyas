# ABHYAS BUILD SPEC — FULL (all build-pack files concatenated)


---

## FILE: AGENTS.md

# AGENTS.md — Build instructions for the coding agent

You are building **Abhyas**, a voice-first practice partner for government primary (FLN, Classes 1–3) teachers in Hindi, for the AI for Foundational Learning Hackathon 2026 (Challenge 3: Teacher Support and Training), Team Asymptotes.

This build pack is the **single source of truth**. It supersedes `ARCHITECTURE.md`, `Abhyas_ARCHITECTURE.md` and the `.docx` already in the repo. Where the existing scaffold disagrees with this pack, change the scaffold.

## Hard deadline

- **Build-stage submission: 1 Nov 2026, 23:59 IST.** Target internal freeze **31 Oct 2026, 18:00 IST**.
- After submission: **no commits** to the submitted branch/tag. Evaluation runs on the frozen state.
- Evaluators get ~1 hour hands-on with a **hosted web link**, **test credentials for every role**, and **3–5 sample inputs**. They will test **low-connectivity behaviour**. Everything you build must serve that hour.

## Read order

1. `spec/01_product.md` — what, who, scope (IN / OUT)
2. `spec/02_architecture.md` — layers, components, repo layout, stack (pinned)
3. `spec/03_data_model.md` — schema, RLS, seed data
4. `spec/04_rule_engine.md` — **core IP**: deterministic AI children
5. `spec/05_llm_roles.md` — every Claude prompt, schema, guard, fallback
6. `spec/06_speech.md` — STT / TTS / audio pipeline
7. `spec/07_channels.md` — channel abstraction, WhatsApp Cloud API, web channel, HTTP API
8. `spec/08_conversation_flow.md` — state machine, intents, message catalog, templates, jobs
9. `spec/09_web_apps.md` — teacher web chat (PWA), ARP, trainer, coach review console, admin, auth
10. `spec/10_content.md` — move/persona formats, source ingestion, generation pipeline
11. `spec/11_eval_and_testing.md` — unit/integration tests, kappa, latency, realism, user-testing protocol
12. `spec/12_deploy_ops.md` — Render + Supabase, env vars, CI, freeze procedure
13. `spec/13_submission.md` — README, deck, video script, submission checklist
14. `spec/14_tasks.md` — **ordered task list with acceptance criteria. Work through it in order.**
15. `spec/15_human_inputs.md` — things only humans can provide; how to proceed without them

Seed data: `content-seed/` (moves, personas, Hindi message catalog, WhatsApp templates, eval samples). Copy into the repo locations given in `spec/10_content.md`.

## Working rules

1. **Work task by task from `spec/14_tasks.md`.** One task = one or more commits with message `T<id>: <summary>`. Do not start a task until its dependencies pass.
2. **A task is done only when its acceptance tests pass locally** (`make test`) and CI is green.
3. **Keep `PROGRESS.md` at repo root**: per task — status, date, what was built, deviations from spec, open issues. Update after every task.
4. **Never invent credentials, phone numbers, API keys, official document contents, page numbers or teacher data.** Where the spec says **HUMAN INPUT**, check `spec/15_human_inputs.md`: build against the mock/fallback described there, add a line to `PROGRESS.md › Blocked on humans`, and continue with the next task. Do not stall.
5. **Every external service has a mock** selected by env var. With an empty `.env`, `make dev` must run the full product end-to-end on mocks. Tests never call real external services.
6. **Children's answers come only from the rule engine.** No LLM ever decides what a simulated child answers. This is the product's central claim; tests enforce it.
7. **Every LLM output is schema-validated and guarded before use** (`spec/05_llm_roles.md`). On guard failure: one retry, then a deterministic template fallback. Log every failure.
8. **No secrets in git.** No real teacher data in git. `.env` is gitignored. CI runs a secret scanner.
9. **All thresholds and tunables live in `backend/app/config.py`.** No magic numbers elsewhere.
10. **Hindi text is NFC-normalised** at every boundary (input, content load, LLM output).
11. Code quality: Python 3.11, `ruff` + `mypy --strict` clean, pydantic v2 models at every boundary, type hints everywhere, async I/O.
12. **Front-end is server-rendered HTML + vanilla JS + one CSS file. No React, no build step.** Pages must stay light (< 150 KB first load excluding audio) for low-cost Android phones on 2G/3G.
13. When the spec is silent, choose the simplest option that keeps the demo reliable, record the decision in `PROGRESS.md › Decisions`, and move on.
14. If you find a contradiction inside this pack, the order of precedence is: `AGENTS.md` > `14_tasks.md` > the numbered spec file most specific to the topic.

## Commands the repo must support (create the Makefile)

| Command | Does |
|---|---|
| `make setup` | create venv, install deps (incl. dev), install pre-commit |
| `make dev` | run API + web + scheduler locally on port 8000 with mocks if keys absent (uses local Postgres+pgvector via docker compose — see 03) |
| `make db-up` / `make db-migrate` / `make db-seed` | start local Postgres+pgvector, apply Alembic migrations, load content + demo data |
| `make test` | ruff, mypy, pytest (unit + integration, mocks only) |
| `make test-live` | opt-in tests that hit real providers (skipped if keys absent) |
| `make eval-latency` / `make eval-kappa` / `make eval-realism` | eval scripts in `eval/` |
| `make content-validate` / `make content-publish` | content pipeline |
| `make samples` | render the evaluator sample voice notes into `eval/samples/audio/` |
| `make freeze` | run the freeze checklist script (`spec/12_deploy_ops.md`) |

## Definition of done for the whole build

- Hosted URL works for every role in the credentials table (`spec/13_submission.md`).
- A teacher can complete one full weekly loop (LEARN → EXPLAIN_BACK → MODEL → REHEARSE → FEEDBACK → RETRY → TRY_IN_CLASS → REFLECT → DONE) **by voice in Hindi** on the web channel, and the same on WhatsApp when credentials exist.
- The Ravi worked example and the tell-answer relapse test pass.
- p95 voice-in → voice-out latency < 20 s on the hosted deploy (report in `eval/latency/REPORT.md`).
- ARP digest and trainer view render with consent filtering and n<10 suppression.
- Low-network mode works and is documented in README.
- README, `.env.example`, AI-services list, LICENSE, sample inputs, demo video script all present.

---

## FILE: spec/01_product.md

# 01 — Product

## 1.1 Problem

Government primary teachers in UP and similar states receive FLN (NIPUN Bharat) training in short bursts (block/cluster trainings, monthly Shikshak Sankul meetings). Between trainings they have **no safe place to practise** the classroom moves they were taught (e.g. using bundles and sticks for regrouping, asking a child to explain a wrong answer instead of telling the answer). Training fidelity decays; trainers and ARPs (Academic Resource Persons) see **attendance**, not **adoption**.

## 1.2 Solution (one paragraph)

Abhyas is a **voice-first practice partner** reached over **WhatsApp** (and an equivalent light web chat). Each week a teacher, in ~15 minutes and in Hindi:

1. **Learns** one teaching move from the state FLN module (≤ 2-min voice note).
2. **Explains it back** in her own words (≤ 1-min voice note) → AI scores fidelity against the move's key points and tells her the one point she missed.
3. **Hears a model teacher** handle the scenario (optional).
4. **Rehearses** by voice with **three simulated children** whose mistakes are **computed by a deterministic rule engine** (Claude only turns the engine's answer into a natural child's line).
5. Gets **rubric feedback**: one strength, one change, exact words to try — every score backed by a quote from her own transcript — and **retries**.
6. **Tries it in class**: a peer runs a 5-minute checklist, or she answers 2 reflection questions.
7. Can **ask questions any time**; answers cite the state guides; low-confidence questions go to her ARP; a 2-day follow-up asks "did it work?".

Back-end outputs: an **evidence ladder** per teacher × move (rehearsed → self-reported → peer-observed → ARP-observed → children improved), a **weekly ARP digest** (consenting teachers only), and a **trainer view** for DIET/SCERT by module × batch (groups ≥ 10 only).

## 1.3 Why this is novel (keep these claims true in code)

| Claim | Where it's enforced |
|---|---|
| Simulated children make **realistic, persistent, research-based mistakes** — LLM role-play students are known to solve correctly or give in too quickly | `04_rule_engine.md`; guard in `05` rejects any child line containing an answer the engine didn't produce |
| Children only improve when the teacher uses a move that actually addresses the misconception; **telling the answer causes a parrot-then-relapse** | transition table + relapse test |
| Feedback is **evidence-cited** — every rubric score quotes the teacher's own words | coach guard |
| Measures **adoption, not attendance** | evidence ladder |
| Privacy by design — individual scores never go upward without consent; aggregates suppressed below n = 10 | `03` RLS + `09` + tests |

## 1.4 Users and roles

| Role | Who | Channel | Sees / does |
|---|---|---|---|
| `teacher` | Govt primary teacher, Classes 1–3, Hindi-speaking, low-cost Android, patchy data | WhatsApp (primary), web chat (PWA) | Weekly loop, ask questions, own progress |
| `arp` | Academic Resource Person for a cluster (~20–40 teachers) | Web + WhatsApp digest template | Weekly digest for **consenting** teachers in own cluster; log classroom observations; answer escalated questions |
| `trainer` | DIET/SCERT faculty | Web | Aggregates by module × batch; n<10 suppressed; no names |
| `coach` | FLN expert (content reviewer) | Web review console | Approve/edit moves; review low-confidence scores; answer queued questions |
| `admin` | Team | Web | Users, fast-forward timers (demo), cost/latency dashboards, content publish |

## 1.5 User constraints the design must respect

- **Voice first, Hindi/Hinglish.** Text accepted everywhere. All teacher-facing copy in simple Hindi (Devanagari). Hinglish (Roman) input must work.
- **~15 min/week.** Every step is skippable except consent.
- **Low-cost Android, 2G/3G, intermittent data.** Voice notes are Opus ~16 kbps (~120 KB/min). Web pages < 150 KB. Text always sent before (or with) audio so a dropped audio download never blocks progress.
- **Nothing to install** (WhatsApp) — web chat is a PWA, installable but optional.
- **Teacher dignity.** Feedback tone: respectful, colleague-to-colleague ("आपने…", never "तुमने…"). One strength first. Never shaming.
- **Children's privacy.** Class audio is **off by default**. Children are never scored or identified.

## 1.6 Scope for the 1 Nov build

### IN (must work on the hosted deploy)

- Web teacher chat with hold-to-record voice, text input, audio playback, buttons; low-network ("लाइट मोड") mode.
- WhatsApp channel on Meta Cloud API (works when credentials exist; mocked in tests; shown in demo video).
- Onboarding: consent → profile (3 questions) → short placement role-play → personal move order.
- Full weekly loop for **4 moves** (3 numeracy, 1 literacy) from `content-seed/moves/`.
- Rule engine with 12 bug rules (9 numeracy, 3 literacy), 3 personas, full transition table.
- Claude roles: intent_router, act_tagger, child_voice, coach, fidelity_checker, guide_answerer (runtime); move_generator, move_reviewer, model_teacher (build-time).
- STT/TTS via one hosted Indian provider + mocks; distinct child voices via pitch shift.
- Ask-any-time with retrieval over ingested guide chunks; ARP escalation; 2-day follow-up job.
- Evidence ladder; ARP digest page; trainer view with suppression; coach review console; admin page with fast-forward.
- Seeded **clearly-labelled demo data** for ARP/trainer views (synthetic teachers), plus real pilot data when available.
- Consent flows, data retention (audio deleted after transcription), cost log, latency log.
- Eval harness: kappa, latency, realism; user-testing protocol and evidence folder.
- README, LICENSE (MIT), `.env.example`, AI-services list, sample inputs, demo video script, deck outline.

### OUT (roadmap only — mention in deck, do not build)

- IVR / phone-call version for feature phones.
- Class-audio analysis of real lessons.
- Integration with state teacher platforms (DIKSHA, Prerna UP), Bhashini as default speech stack, VallamAI child assessment link (evidence level 5).
- Self-hosted GPU speech models.
- Languages beyond Hindi.

## 1.7 Success metrics (report honestly in `eval/`)

| Metric | Target |
|---|---|
| AI coach vs FLN coach agreement | quadratic-weighted kappa ≥ 0.7 (report actual n, even if small) |
| Explain-back scoring vs coach | kappa ≥ 0.7 |
| Realism of AI children (teacher rating) | mean ≥ 4/5 |
| Latency voice-in → voice-out | p95 < 20 s |
| Pilot engagement | ≥ 50% of pilot teachers complete one full loop |
| Guard failure rate (child_voice) | < 5% of turns reach template fallback |

---

## FILE: spec/02_architecture.md

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

---

## FILE: spec/03_data_model.md

# 03 — Data model

Postgres 15+ with `pgvector` and `pgcrypto`. Implement as SQLAlchemy 2 models + **one Alembic migration per task** that adds tables. Local dev uses docker compose Postgres (no SQLite).

## 3.1 Conventions

- PKs `uuid` default `gen_random_uuid()` unless stated. All timestamps `timestamptz` default `now()`.
- **No raw phone numbers stored.** `phone_hash = sha256(PHONE_HASH_SALT + E.164 number)`. The raw number is needed to *send* WhatsApp messages: store it **encrypted** in `teacher_contact.phone_enc` (Fernet, key `PHONE_ENC_KEY`) in a separate table that only the channel layer reads.
- **No audio stored**, ever. Transcripts only.
- Teacher-facing text stored NFC-normalised.
- Every LLM call logged in `llm_call` (no full prompt text for teacher content beyond the transcript already stored; store prompt version + token counts).

## 3.2 Schema (DDL — source of truth for the Alembic migrations)

```sql
create extension if not exists vector;
create extension if not exists pgcrypto;

-- ── Organisation ───────────────────────────────────────────────
create table batch (            -- a training batch (e.g. "Kanpur Nagar Oct-2026 NIPUN Ganit")
  id text primary key, name text not null, district text, block_id text, module text,
  created_at timestamptz default now());

create table cluster (id text primary key, name text not null, block_id text, district text);

create table app_user (          -- web logins: arp, trainer, coach, admin, and web teachers
  id uuid primary key default gen_random_uuid(),
  username text unique not null, password_hash text not null,
  role text not null check (role in ('teacher','arp','trainer','coach','admin')),
  display_name text, cluster_id text references cluster(id),   -- arp scope
  district text,                                                -- trainer scope
  teacher_id uuid,                                              -- set when role='teacher'
  is_demo boolean default false, created_at timestamptz default now());

create table teacher (
  id uuid primary key default gen_random_uuid(),
  phone_hash text unique,                    -- null for web-only demo teachers
  name text, school_id text, cluster_id text references cluster(id), block_id text, district text,
  batch_id text references batch(id),
  experience_band text check (experience_band in ('0-1','2-5','6-10','10+')),
  first_year boolean, classes int[],
  address_form text default 'f' check (address_form in ('f','m')),   -- grammatical gender for Hindi messages
  preferred_channel text default 'whatsapp' check (preferred_channel in ('whatsapp','web')),
  lite_mode boolean default false,           -- text-only replies
  consent_service boolean default false,     -- required to use the product
  consent_share_scores boolean default false,-- ARP may see individual scores
  consent_class_audio boolean default false, -- always false in this build
  consent_research boolean default false,    -- anonymised use in evaluation
  is_demo boolean default false,             -- synthetic, for ARP/trainer demo views
  onboarding_state text default 'NEW',
  last_inbound_at timestamptz, created_at timestamptz default now());

create table teacher_contact (
  teacher_id uuid primary key references teacher(id) on delete cascade,
  phone_enc bytea not null);

create table invite_code (code text primary key, cluster_id text references cluster(id), batch_id text references batch(id),
  district text, active boolean default true);

create table arp_assignment (arp_user_id uuid references app_user(id), cluster_id text references cluster(id),
  primary key (arp_user_id, cluster_id));

create table consent_log (id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id),
  field text not null, value boolean not null, channel text, text_version text, created_at timestamptz default now());

-- ── Content (published releases) ───────────────────────────────
create table content_release (id text primary key, notes text, published_by uuid references app_user(id),
  published_at timestamptz default now(), is_active boolean default false);
create table move (id text not null, release_id text references content_release(id), domain text not null,
  title_hi text not null, sankul_month text, status text not null check (status in ('draft','in_review','approved')),
  payload jsonb not null, approvals jsonb default '[]', primary key (id, release_id));
create table persona (id text not null, release_id text references content_release(id), payload jsonb not null,
  primary key (id, release_id));
create table bug_rule (id text primary key, kind text check (kind in ('math','reading')), code_ref text not null,
  description_hi text, research_ref text);

-- ── Sessions ───────────────────────────────────────────────────
create table session_state (
  teacher_id uuid references teacher(id) on delete cascade,
  week_start date not null,                -- Monday of the ISO week, or a "demo week" counter date
  move_id text not null,
  state text not null,                     -- see 08 state list
  prior_state text,                        -- for ASK interrupt resume
  rehearse_attempts int default 0,
  context jsonb default '{}',              -- free per-state data (pending confirm, last buttons, etc.)
  updated_at timestamptz default now(),
  primary key (teacher_id, week_start));

create table move_path (teacher_id uuid references teacher(id) on delete cascade, position int,
  move_id text, reason text, primary key (teacher_id, position));

create table scene (               -- one rehearsal attempt
  id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  move_id text, week_start date, attempt int, mode text default 'normal' check (mode in ('normal','placement','sankul')),
  engine_state jsonb not null,     -- serialised SceneState (04)
  status text default 'active' check (status in ('active','ended')),
  end_reason text, teacher_turns int default 0, started_at timestamptz default now(), ended_at timestamptz);

create table turn (
  id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  scene_id uuid references scene(id) on delete cascade, idx int,
  role text not null,              -- 'teacher' | persona id | 'system'
  transcript text, stt_confidence real,
  acts text[], addressed_child text, problem jsonb,
  rule_result jsonb, line_hi text, guard_status text,   -- 'pass' | 'retry_pass' | 'fallback'
  latency_ms int, stage_ms jsonb,  -- {"stt":..,"tagger":..,"engine":..,"voice":..,"tts":..,"send":..}
  created_at timestamptz default now());

create table message (             -- every inbound/outbound message (web history + audit). No audio bytes.
  id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  direction text check (direction in ('in','out')), channel text, channel_msg_id text,
  kind text, text text, audio_ref text, buttons jsonb, speaker text, template_name text,
  state_at text, created_at timestamptz default now(),
  unique (channel, channel_msg_id));

-- ── Scores & evidence ──────────────────────────────────────────
create table rehearsal_score (id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  scene_id uuid references scene(id), move_id text, attempt int,
  scores jsonb not null, evidence jsonb not null, strength_hi text, change_hi text, exact_words_hi text,
  confidence real, needs_review boolean default false, prompt_version text, model text,
  created_at timestamptz default now());

create table explain_score (id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  move_id text, transcript text, points jsonb not null, misconceptions text[], confidence real,
  needs_review boolean default false, prompt_version text, model text, created_at timestamptz default now());

create table adoption_evidence (id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  move_id text not null, level int not null check (level between 1 and 5),
  source text not null check (source in ('rehearsal','reflection','peer_checklist','arp_observation','child_check')),
  detail jsonb, created_by uuid, created_at timestamptz default now());

create table realism_rating (id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  scene_id uuid references scene(id), rating int check (rating between 1 and 5), created_at timestamptz default now());

-- ── Ask any time ──────────────────────────────────────────────
create table question (id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  text text not null, category text, clarifying_asked boolean default false,
  answer_hi text, source_ids text[], confidence real,
  status text not null check (status in ('answered','escalated','arp_answered','closed')),
  followup_at timestamptz, followup_result text, created_at timestamptz default now());

create table doc_chunk (id text primary key, source_id text not null, source_short_hi text, section text, page int,
  text text not null, tokens text[], embedding vector(1024), created_at timestamptz default now());
create index on doc_chunk using ivfflat (embedding vector_cosine_ops) with (lists = 50);

-- ── Review / ops ───────────────────────────────────────────────
create table review_item (id uuid primary key default gen_random_uuid(),
  kind text check (kind in ('rehearsal_score','explain_score','question','move','guard_failure')),
  ref_id text not null, reason text, status text default 'open' check (status in ('open','resolved')),
  resolution jsonb, resolved_by uuid, created_at timestamptz default now(), resolved_at timestamptz);

create table calibration_label (id uuid primary key default gen_random_uuid(), scene_id uuid references scene(id),
  explain_score_id uuid references explain_score(id), coach_user_id uuid references app_user(id),
  scores jsonb not null, note text, blind boolean default true, created_at timestamptz default now());

create table arp_observation (id uuid primary key default gen_random_uuid(), arp_user_id uuid references app_user(id),
  teacher_id uuid references teacher(id) on delete cascade, move_id text, checklist jsonb, notes text, observed_on date,
  created_at timestamptz default now());

create table scheduled_job (id uuid primary key default gen_random_uuid(), kind text not null, run_at timestamptz not null,
  payload jsonb, status text default 'pending' check (status in ('pending','done','failed','cancelled')),
  attempts int default 0, last_error text, created_at timestamptz default now());
create index on scheduled_job (status, run_at);

create table template_send (id uuid primary key default gen_random_uuid(), teacher_id uuid, template_name text,
  category text, est_cost_inr numeric(8,3), sent_at timestamptz default now());

create table llm_call (id uuid primary key default gen_random_uuid(), role text, prompt_version text, model text,
  input_tokens int, output_tokens int, cache_read_tokens int, latency_ms int, outcome text, -- ok|retry_ok|fallback|error
  created_at timestamptz default now());

create table tts_cache (key text primary key, voice text, text_hi text, mime text, bytes bytea, created_at timestamptz default now());
-- tts_cache holds SYNTHETIC audio only (our voices), never user audio.

-- ── Aggregates for trainer view (materialised by job) ──────────
create table agg_module_batch (batch_id text, move_id text, n_teachers int,
  explain_missing jsonb,       -- {kp_id: count}
  rubric_dist jsonb,           -- {criterion_id: {"0":n,"1":n,"2":n}}
  ladder_dist jsonb,           -- {"1":n,...,"5":n}
  active_rate real, computed_at timestamptz default now(), primary key (batch_id, move_id));
```

## 3.3 Access rules (enforce in the service layer AND test them; add Supabase RLS as defence in depth)

The app connects with a service role, so **authorisation is enforced in code** (`auth/guards.py` + query helpers). Every query that returns teacher-level data must go through a scoped helper:

| Role | Can read |
|---|---|
| teacher | own rows only |
| arp | teachers where `cluster_id ∈ own clusters`; **scores/transcripts only if `consent_share_scores = true`**; otherwise only: practised move (yes/no), asked-for-help flag, escalated questions (text only, no name if no consent → shown as "शिक्षक #<short hash>") |
| trainer | `agg_module_batch` rows only, filtered to own district; rows with `n_teachers < AGGREGATION_SUPPRESSION_N` rendered as "समूह छोटा है (n<10)" |
| coach | review_item, move drafts, anonymised transcripts attached to review items |
| admin | everything (demo/ops) |

Tests (in `tests/integration/test_access.py`): an ARP cannot fetch scores for a non-consenting teacher in own cluster; cannot fetch any teacher from another cluster; trainer endpoint never returns a group with n<10; no endpoint returns `teacher_contact`.

Supabase RLS (defence in depth): enable RLS on all tables; no anon policies (the app uses the service key server-side only). Document this in README.

## 3.4 Retention

- Audio: never persisted (assert in tests: no `bytes`/`bytea` column receives user audio; `tts_cache` writes only from TTS module).
- Transcripts: retained for the pilot; job `retention_purge` deletes `turn.transcript`, `message.text` for teachers who withdraw consent (within 24 h) and everything for teachers who send "मेरा डेटा हटाएँ" (delete-account flow, 08).

## 3.5 Seed data (`make db-seed`)

1. Content release `r2026.10-demo` from `content/moves/*.yaml` + `content/personas/*.yaml` (status as in file).
2. Bug rules registry rows from `rule_engine/bugs/registry.py`.
3. Doc chunks from `content/chunks/*.jsonl` (if present).
4. Demo users (passwords from env `DEMO_PASSWORD`, default `abhyas-demo-2026` in dev only):
   - `teacher.demo1`, `teacher.demo2`, `teacher.demo3` (role teacher; demo1 fresh/NEW, demo2 mid-week in REHEARSE, demo3 completed 3 moves)
   - `arp.demo` (cluster `KNP-C01`), `trainer.demo` (district Kanpur Nagar), `coach.demo`, `admin.demo`
5. **Synthetic demo cohort** (`db/demo_data.py`, `is_demo = true`, names prefixed "डेमो"): batches `KNP-B1` (25 teachers), `KNP-B2` (18), `KNP-B3` (8 — shows suppression); cluster `KNP-C01` has 12 of them, 7 consenting. Generate rehearsal/explain scores, evidence levels and questions with a fixed random seed so screenshots are reproducible. Every page showing demo data displays a banner "डेमो डेटा — वास्तविक शिक्षक नहीं".

---

## FILE: spec/04_rule_engine.md

# 04 — Rule engine (core IP)

**Principle: children's mistakes are computed, not improvised.** LLMs asked to play students tend to answer correctly or give in too fast (Markel et al., 2023, "GPTeach"; arXiv 2605.12748, 2026). So every simulated child's answer, reasoning steps and state change come from **pure, deterministic Python** in `backend/app/rule_engine/`. Claude only *voices* the result (05 › child_voice), and a guard rejects any line whose numbers/words the engine did not produce.

`rule_engine/` must not import anything outside itself (no DB, no LLM, no I/O). 100% branch coverage target.

## 4.1 Types

```python
class Domain(str, Enum): NUMERACY = "numeracy"; LITERACY = "literacy"

class Problem(BaseModel):                      # an item the children work on
    type: Literal["sub", "add", "place_value", "read_word"]
    a: int | None = None                       # sub/add: a − b or a + b (two-digit)
    b: int | None = None
    tens: int | None = None                    # place_value: bundles of 10
    ones: int | None = None                    #              loose sticks
    word: str | None = None                    # read_word (Devanagari, NFC)
    def key(self) -> str: ...                  # stable id e.g. "sub:52-17", "pv:4-7", "word:मेला"

class Step(BaseModel):                         # one reasoning step, engine-rendered
    code: str                                  # e.g. "SUB_CANNOT", "SUB_SWAP", "REGROUP_OPEN_BUNDLE"
    nums: list[int] = []                       # every number mentioned in this step
    words: list[str] = []                      # every Hindi word token that must appear (literacy)
    text_hi: str                               # rendered template (digits as Arabic numerals)

class BugOutput(BaseModel):
    rule_id: str
    answer: int | str
    steps: list[Step]

class ChildState(IntEnum):
    MISCONCEPTION = 0   # applies bug, confident, no explanation
    CAN_EXPLAIN   = 1   # still wrong, explains steps (reveals the bug)
    PARTIAL       = 2   # correct with scaffold on the current item; may relapse on a new item
    CORRECT       = 3   # correct and explains why, on any item

class ChildRuntime(BaseModel):
    persona_id: str
    misconception: str                         # bug rule id assigned by the scenario
    temperament: Literal["confident", "shy", "distracted"]
    state: ChildState = ChildState.MISCONCEPTION
    partial_item_key: str | None = None        # item on which PARTIAL was reached
    silent_turns: int = 0
    turns_since_addressed: int = 0
    last_answer: int | str | None = None
    history: list[tuple[int, ChildState]] = [] # (teacher_turn_idx, state) trajectory

class SceneState(BaseModel):
    move_id: str
    domain: Domain
    effective_acts: list[str]                  # from move.teaching_acts_effective
    target_causes: list[str]
    items: list[Problem]                       # scenario items (in order)
    item_idx: int = 0
    current_item: Problem
    children: list[ChildRuntime]               # exactly 3 in normal mode, 1 in placement mode
    teacher_turns: int = 0
    last_responder: str | None = None
    ended: bool = False
    end_reason: str | None = None

class TaggedTurn(BaseModel):                   # from act_tagger (05), validated
    acts: list[TeachingAct]
    addressed_child: str | None                # persona id | "all" | None
    problem: Problem | None                    # if the teacher posed a new item

class ResponseKind(str, Enum):
    ANSWER = "answer"                          # MISCONCEPTION: bug answer, no steps
    EXPLAIN_BUG = "explain_bug"                # CAN_EXPLAIN: bug answer + bug steps
    SCAFFOLDED_CORRECT = "scaffolded_correct"  # PARTIAL: correct answer, hesitant, correct steps
    RELAPSE = "relapse"                        # PARTIAL on a new item without support: bug again
    CORRECT_EXPLAINED = "correct_explained"    # CORRECT
    PARROT = "parrot"                          # repeats the told answer, no understanding
    SILENT = "silent"                          # shy child after scolding
    OFF_TOPIC = "off_topic"                    # distracted child
    INTERJECT = "interject"                    # unprompted distracted interjection
    CONFUSED = "confused"                      # teacher posed an out-of-scope problem

class ChildResponse(BaseModel):
    persona_id: str
    kind: ResponseKind
    answer: int | str | None
    correct_answer: int | str | None
    steps: list[Step]
    prior_state: ChildState
    new_state: ChildState
    affect: Literal["neutral", "confident", "encouraged", "upset", "shy", "distracted"]
    item: Problem
    allowed_numbers: set[int]                  # for the guard
    allowed_words: set[str]
    forbidden: set[str]                        # tokens that must NOT appear (e.g. correct answer)

class StepResult(BaseModel):
    responses: list[ChildResponse]             # 1 main + at most 1 INTERJECT
    ended: bool
    end_reason: Literal["all_correct", "turn_limit", "teacher_stop"] | None
```

## 4.2 Bug rules (`rule_engine/bugs/`)

Each rule: `def rule(problem: Problem) -> BugOutput` and a paired `correct(problem) -> BugOutput`. Registry maps id → (fn, kind, applicable problem types, description_hi, research_ref). Rules raise `NotApplicable` for wrong problem types. All arithmetic is column-wise on two-digit numbers (`10 ≤ b < a ≤ 99` for sub; `10 ≤ a, b ≤ 99` for add).

Research base for the bug families (cite in deck and `description` field): Brown & Burton (1978) and VanLehn (1990) procedural-bug studies for multi-digit subtraction/addition; Indian evidence on place-value errors from ASER and NCERT FLN materials; Hindi reading errors (matra omission, guessing from first akshar, akshar-by-akshar non-blending) from NIPUN Bharat / Pratham reading-level guidance. **HUMAN INPUT:** the FLN mentor confirms these are common in UP classrooms.

### Numeracy

| Rule id | Behaviour | 52−17 | 43−27 | 61−28 | 74−39 |
|---|---|---|---|---|---|
| (correct) | regroup | **35** | **16** | **33** | **35** |
| `SUB_SMALLER_FROM_LARGER` | each column: larger digit − smaller digit | 45 | 24 | 47 | 45 |
| `SUB_BORROW_NO_DECREMENT` | adds 10 to units, forgets to reduce tens | 45 | 26 | 43 | 45 |
| `SUB_WRITE_ZERO_WHEN_STUCK` | if top units < bottom units, writes 0 in units; tens subtracted normally | 40 | 20 | 40 | 40 |

| Rule id | Behaviour | 38+45 | 27+48 | 56+29 |
|---|---|---|---|---|
| (correct) | carry | **83** | **75** | **85** |
| `ADD_NO_CARRY` | writes the full units sum, then tens sum to its left | 713 | 615 | 715 |
| `ADD_CARRY_FORGOTTEN` | writes units digit, drops the carry | 73 | 65 | 75 |
| `ADD_CARRY_WRONG_DIGIT` | writes the tens digit of the units sum, carries the units digit | 101 | 111 | 121 |

Note `ADD_NO_CARRY`: answer is the integer formed by concatenating `str(ta+tb)` and `str(ua+ub)` (e.g. 7 and 13 → 713).
`ADD_CARRY_WRONG_DIGIT`: units sum s = ua+ub ≥ 10 → write s // 10, carry s % 10 → tens = ta+tb+(s%10) → answer = tens*10 + s//10 (38+45: s=13 → write 1, carry 3 → 3+4+3=10 → 101).

| Rule id (place value; item = tens bundles, ones sticks; question "कुल कितनी तीलियाँ?") | (4,7) | (3,5) | (6,2) |
|---|---|---|---|
| (correct) | **47** | **35** | **62** |
| `PV_BUNDLE_AS_ONE` — counts each bundle as 1 | 11 | 8 | 8 |
| `PV_CONCAT_SPOKEN` — writes "चालीस" as 40 then appends 7 → 407 | 407 | 305 | 602 |
| `PV_REVERSAL` — writes ones digit first | 74 | 53 | 26 |

When a bug does not manifest on an item (e.g. sub with no regrouping), the rule returns the correct answer with the child's normal steps; responses still work and the guard allows the correct number because it equals the bug answer.

### Literacy (item = a word)

| Rule id | Behaviour | मेला | पानी | किताब | गुड़िया |
|---|---|---|---|---|---|
| (correct) | reads the word, blends | मेला | पानी | किताब | गुड़िया |
| `MATRA_DROP` | drops all dependent vowel signs and ं ँ ः | मल | पन | कतब | गड़य |
| `FIRST_AKSHAR_GUESS` | reads first akshar, guesses a familiar word starting with the same base consonant from `guess_lexicon` (move YAML); if the guess equals the word, uses the 2nd entry | मछली | पतंग | कमल | गमला |
| `AKSHAR_BY_AKSHAR` | sounds each akshar separately, cannot blend; answer = aksharas joined by " - " | मे - ला | पा - नी | कि - ता - ब | गु - ड़ि - या |

**Akshar splitter** (`bugs/akshar.py`, own implementation — do not rely on `\X`): an akshar = (independent vowel | consonant [+ nukta] (+ virama + consonant [+ nukta])*) + optional dependent vowel sign + optional (ं|ँ|ः). Test on: किताब→[कि,ता,ब], गुड़िया→[गु,ड़ि,या], विद्यालय→[वि,द्या,ल,य], आम→[आ,म], संतरा→[सं,त,रा].

### Step templates (engine-rendered, Hindi, Arabic digits)

Implement as a dict `STEP_TEMPLATES[code] -> str.format(**vars)`; all numbers placed in `Step.nums`. Minimum set:

| code | text_hi template | used by |
|---|---|---|
| `SUB_CANNOT` | `{u_top} में से {u_bot} नहीं घटता` | all sub bugs, correct |
| `SUB_SWAP` | `तो {u_bot} में से {u_top} घटाया, {d_u} आया` | SMALLER_FROM_LARGER |
| `SUB_TENS` | `{t_top} में से {t_bot} घटाया, {d_t} आया` | all sub |
| `REGROUP_OPEN_BUNDLE` | `एक बंडल खोला, {u_new} तीलियाँ हो गईं, {t_left} बंडल बचे` | correct sub |
| `BORROW_NO_DEC` | `{u_top} के आगे 1 लगाया, {u_new} में से {u_bot} घटाया, {d_u} आया` | BORROW_NO_DECREMENT |
| `WRITE_ZERO` | `नहीं घटा तो 0 लिख दिया` | WRITE_ZERO_WHEN_STUCK |
| `ADD_UNITS` | `{ua} और {ub} जोड़े, {s} आया` | add |
| `ADD_WRITE_ALL` | `{s} पूरा नीचे लिख दिया` | NO_CARRY |
| `ADD_DROP_CARRY` | `{s} में से {s_u} लिखा` | CARRY_FORGOTTEN |
| `ADD_CARRY` | `{s_u} लिखा, 1 हासिल ऊपर रखा` | correct add |
| `ADD_WRONG_CARRY` | `{s_t} लिखा, {s_u} हासिल ऊपर रखा` | CARRY_WRONG_DIGIT |
| `ADD_TENS` | `{ta} और {tb}{carry_txt} जोड़े, {t} आया` | add |
| `PV_COUNT_BUNDLES` | `{tens} बंडल और {ones} तीलियाँ, सब गिनीं` | pv |
| `PV_BUNDLE_TEN` | `एक बंडल में 10 तीलियाँ, तो {tens} बंडल में {tens10}` | correct pv |
| `PV_CONCAT` | `{tens10} और {ones}, तो {answer} लिखा` | CONCAT_SPOKEN |
| `PV_REVERSE` | `पहले {ones} लिखा फिर {tens}` | REVERSAL |
| `READ_AKSHARS` | `{aksharas}` (words = aksharas) | AKSHAR_BY_AKSHAR, correct read |
| `READ_NO_MATRA` | `{bare}` | MATRA_DROP |
| `READ_GUESS` | `{first} से {guess}` | FIRST_AKSHAR_GUESS |
| `ANSWER` | `{answer}` | all |

## 4.3 Transition table (`rule_engine/transitions.py`)

```python
ADVANCE: dict[TeachingAct, dict[ChildState, ChildState]] = {
    ASK_TO_EXPLAIN:          {MISCONCEPTION: CAN_EXPLAIN},
    CONCRETE_REPRESENTATION: {MISCONCEPTION: PARTIAL, CAN_EXPLAIN: PARTIAL},
    PROBE_WITH_SIMPLER_CASE: {CAN_EXPLAIN: PARTIAL},
    PHONICS_SOUND_OUT:       {MISCONCEPTION: PARTIAL, CAN_EXPLAIN: PARTIAL},
    CONTRAST_TWO_ANSWERS:    {PARTIAL: CORRECT},
    MODEL_STEP_ALOUD:        {PARTIAL: CORRECT},
    INVOLVE_PEER:            {CAN_EXPLAIN: PARTIAL},   # only when the peer who explains is CORRECT (see rule 3d)
}
NON_ADVANCING = {TELL_ANSWER, REPEAT_QUESTION, PRAISE_EFFORT, PRAISE_GENERIC, SCOLD, OFF_TASK, GIVE_NEW_PROBLEM}
```

Add `GIVE_NEW_PROBLEM = "give_new_problem"` to the `TeachingAct` taxonomy (14 acts total).

## 4.4 `RuleEngine.step(scene, tagged) -> StepResult` — exact algorithm

Deterministic. Same inputs → same outputs. No randomness anywhere.

1. **Turn count.** `scene.teacher_turns += 1`.
2. **New item.** If `tagged.problem` is not None:
   - validate: type matches scene domain; sub `10 ≤ b < a ≤ 99`; add `10 ≤ a,b ≤ 99` and `a+b ≤ 199`; pv `1 ≤ tens ≤ 9, 0 ≤ ones ≤ 9`; word: 1–4 aksharas Devanagari only.
   - valid → `scene.current_item = problem`; implicitly add `GIVE_NEW_PROBLEM` to acts.
   - invalid → main response `CONFUSED` from the responder (step 3), no state changes; go to step 8.
   - If `TELL_ANSWER` is also in acts, the PARROT response uses the item **before** the switch, and the new item becomes current at the end of this turn (so the relapse shows on the next turn).
   - If `GIVE_NEW_PROBLEM` is in acts but `problem` is None → advance `item_idx` (wrap) and set `current_item = items[item_idx]`.
3. **Responder.**
   a. `addressed_child` is a valid persona id → that child.
   b. else if `INVOLVE_PEER` in acts and `last_responder` set → next child after `last_responder` in roster order (skip silent).
   c. else (`"all"` or None) → first child, in priority order **confident → distracted → shy**, whose state < CORRECT and silent_turns == 0; **shy children are never chosen unless directly addressed**; if none, the confident child.
   d. `INVOLVE_PEER` advancing rule: applies to every *listening* child in CAN_EXPLAIN only if the responder's state is CORRECT after this turn.
4. **Whole-class acts.** If `addressed_child == "all"` and act ∈ {CONCRETE_REPRESENTATION, MODEL_STEP_ALOUD, PHONICS_SOUND_OUT} → apply that act's transition to **every** non-silent child whose misconception ∈ target_causes and act ∈ effective_acts (listeners update silently; set their `partial_item_key` when they reach PARTIAL); responder answers.
5. **Silence (checked before any transition).**
   - If `PRAISE_EFFORT` in acts → affect `encouraged`; set responder `silent_turns = 0`.
   - Else if responder `silent_turns > 0` → decrement, response `SILENT`, answer None, **no state change**; go to step 8.
6. **Responder transition.**
   - `effective = set(tagged.acts) ∩ set(scene.effective_acts)` (a child improves only through acts the move says address its cause, **and** only if `child.misconception ∈ scene.target_causes`).
   - If `SCOLD` in acts → no advancement this turn; if temperament == shy → set `silent_turns = SHY_SILENT_TURNS` (config, 1), response `SILENT` for this turn, go to step 8; else affect `upset` and continue to step 7 with state unchanged.
   - Else `new_state = max([state] + [ADVANCE[a].get(state, state) for a in effective if a in ADVANCE])` — **at most one table lookup per act from the current state** (no chaining within a turn).
   - If new_state == PARTIAL and prior < PARTIAL → `partial_item_key = current_item.key()`.
7. **Answer.** By (new) state:
   - `TELL_ANSWER` in acts and new_state == prior_state → `PARROT`: answer = correct, steps = [], **state unchanged**.
   - `OFF_TASK` in acts and temperament == distracted → `OFF_TOPIC` (answer None).
   - MISCONCEPTION → `ANSWER`: bug answer, steps [] (only `ANSWER` step).
   - CAN_EXPLAIN → `EXPLAIN_BUG`: bug answer + bug steps.
   - PARTIAL → if `current_item.key() != partial_item_key` and `effective` is empty → `RELAPSE` (bug answer + bug steps); else `SCAFFOLDED_CORRECT` (correct + correct steps); when SCAFFOLDED_CORRECT on a new item with effective support, set `partial_item_key` to the new item.
   - CORRECT → `CORRECT_EXPLAINED`: correct + correct steps.
   - `REPEAT_QUESTION` only → same kind/answer as last time (recomputation gives the same result by determinism).
8. **Allowed / forbidden sets** (for the guard):
   - `allowed_numbers` = operands (a, b or tens, ones, 10) ∪ {answer if int} ∪ all `step.nums` ∪ {1} (for "एक बंडल"/"1 हासिल").
   - `forbidden` = {str(correct_answer)} if kind ∈ {ANSWER, EXPLAIN_BUG, RELAPSE} and correct ≠ bug answer; for literacy, forbidden = {correct word} likewise.
   - `allowed_words` (literacy) = answer tokens ∪ step words.
9. **Bookkeeping.** responder `turns_since_addressed = 0`, `last_answer = answer`, append `(turn, state)` to history; `scene.last_responder = responder`. Every other child: `turns_since_addressed += 1`.
10. **Distracted interjection.** If any distracted non-responder has `turns_since_addressed ≥ DISTRACTED_INTERJECT_AFTER` (config, 3) → append one `INTERJECT` response for that child and reset its counter. Max one per turn.
11. **End.** all children CORRECT → `all_correct`; else `teacher_turns ≥ MAX_TURNS_PER_REHEARSAL` (8) → `turn_limit`. (`teacher_stop` is set by the caller when the transcript matches a stop word: बस, रुको, stop, खत्म.)

Placement mode: 1 child (Ravi, `SUB_SMALLER_FROM_LARGER`, item 52−17), 2 teacher turns, then end. Record which acts the teacher used (feeds `sessions/path.py`).

## 4.5 Required tests (`backend/tests/unit/test_rule_engine.py`, `test_bugs.py`, `test_akshar.py`)

1. **Every table cell in 4.2** as a parametrised test (bug answers + correct answers).
2. **Ravi worked example (spec-mandated):** scene for `NUM_SUB_REGROUP_BUNDLES`, Ravi = `SUB_SMALLER_FROM_LARGER`, item 52−17.
   - Turn 1: acts [ASK_TO_EXPLAIN], addressed ravi → kind EXPLAIN_BUG, answer 45, new_state CAN_EXPLAIN, `{2, 7, 5, 1, 4, 45} ⊆ allowed_numbers`, `"35" ∈ forbidden`.
   - Turn 2: acts [CONCRETE_REPRESENTATION], addressed ravi → SCAFFOLDED_CORRECT, answer 35, state PARTIAL.
   - Turn 3: acts [CONTRAST_TWO_ANSWERS] → CORRECT_EXPLAINED, state CORRECT.
3. **Relapse after tell:** Ravi MISCONCEPTION, item 52−17, acts [TELL_ANSWER] → PARROT answer 35, state stays MISCONCEPTION. Next turn problem 43−27, acts [] addressed ravi → ANSWER 24.
4. **PARTIAL relapse:** Ravi PARTIAL on 52−17; problem 61−28 with acts [] → RELAPSE 47; same but acts [CONCRETE_REPRESENTATION] → SCAFFOLDED_CORRECT 33.
5. **Ineffective acts never advance:** for move with effective = {ASK_TO_EXPLAIN, CONCRETE_REPRESENTATION, CONTRAST_TWO_ANSWERS, PROBE_WITH_SIMPLER_CASE}, act MODEL_STEP_ALOUD on a PARTIAL child → stays PARTIAL.
6. **Shy/scold:** turn 1 Priya (shy) addressed + SCOLD → SILENT, `silent_turns = 1`. Turn 2 addressed with [ASK_TO_EXPLAIN] → SILENT (counter → 0), no state change. Turn 3 addressed with [ASK_TO_EXPLAIN] → EXPLAIN_BUG. Variant: turn 2 with [PRAISE_EFFORT, ASK_TO_EXPLAIN] → silence cleared, EXPLAIN_BUG, affect encouraged.
7. **Shy never auto-selected:** addressed "all" with Ravi CORRECT, Aman CORRECT, Priya MISCONCEPTION → responder is Ravi (confident fallback), not Priya.
8. **Distracted interjection:** Aman not addressed for 3 turns → INTERJECT appended on turn 3.
9. **Whole-class concrete representation:** addressed "all" + CONCRETE_REPRESENTATION → all non-silent children move to PARTIAL.
10. **Determinism:** run a 8-turn scripted scene twice → identical serialised results.
11. **Property test (hypothesis):** for random act sequences drawn from NON_ADVANCING ∪ {acts not in effective}, no child ever reaches PARTIAL/CORRECT, and every non-PARROT answer equals the bug answer.
12. **Scene end:** all CORRECT → ended all_correct; 8 turns → turn_limit.
13. **Literacy:** all four words × three bugs; akshar splitter cases in 4.2.
14. **Serialisation:** `SceneState` round-trips through JSON (stored in `scene.engine_state`).

---

## FILE: spec/05_llm_roles.md

# 05 — Claude roles, prompts, schemas, guards

All Claude calls go through `llm/client.py`. Each role lives in `llm/roles/<role>.py` and exposes one async function returning a validated pydantic object **or** a deterministic fallback. Prompts live in `llm/prompts/<role>.v1.md` and are loaded at startup; the version string is logged per call.

## 5.1 Client (`llm/client.py`)

```python
async def call_tool(
    role: str, model: str, system: str, messages: list[dict],
    tool_name: str, input_schema: dict,            # JSON Schema from the pydantic model
    temperature: float, max_tokens: int, timeout_s: float,
) -> dict: ...
```

- Uses Anthropic Messages API with `tools=[{name, description, input_schema}]` and `tool_choice={"type": "tool", "name": tool_name}`; returns the tool `input` dict.
- `system` is passed as a content block with `cache_control: {"type": "ephemeral"}` (prompt caching for the static role prompt + move card).
- Timeout `LLM_TIMEOUT_SECONDS` (8 s runtime roles, 60 s build-time). On timeout/5xx/overload: **one** retry (`LLM_MAX_RETRIES = 1`), then raise `LLMUnavailable`.
- Logs a row to `llm_call` (role, prompt_version, model, tokens incl. cache reads, latency, outcome).
- `MockLLM` (selected when `ANTHROPIC_API_KEY` is empty or `LLM_PROVIDER=mock`) returns golden outputs from `backend/tests/golden/<role>/*.json` keyed by a hash of the input, or a schema-valid default. **The whole product must run end-to-end on MockLLM.**

Model routing (env):

| Env var | Default | Roles |
|---|---|---|
| `CLAUDE_MODEL_FAST` | `claude-haiku-5-5` | intent_router, act_tagger, child_voice, question_classifier |
| `CLAUDE_MODEL_SMART` | `claude-sonnet-5-5` | coach, fidelity_checker, guide_answerer |
| `CLAUDE_MODEL_BUILD` | `claude-sonnet-5-5` | move_generator, move_reviewer, model_teacher, page_ocr |

Temperatures: scoring/tagging roles 0.0; child_voice 0.4; guide_answerer 0.2; build-time 0.3.

## 5.2 Role contract pattern (every runtime role)

```
build_input()  →  call_tool()  →  pydantic.validate  →  guard(input, output)
     ↘ on ValidationError / GuardError: retry once with the error message appended ("Your previous output failed: <reason>. Fix it.")
     ↘ on second failure or LLMUnavailable: fallback() (deterministic), log guard_failure (+ review_item if role is scoring)
```

Guard functions live in `llm/guards.py`, are pure, and are unit-tested with good/bad fixtures.

---

## 5.3 `intent_router` (fast) — what did the teacher mean?

Called only when keyword intents (08 › 8.3) don't match and the state is not REHEARSE (in REHEARSE, everything is talk-to-children unless a keyword/button says otherwise).

**Output schema**
```json
{"intent": "answer_for_step | question | command_next | command_skip | command_repeat | command_help | smalltalk | unclear",
 "confidence": 0.0}
```
**Guard:** enum valid. `confidence < 0.5` → treat as `answer_for_step` if the current state expects free speech (EXPLAIN_BACK, REFLECT), else `unclear`.
**Fallback:** `answer_for_step` for EXPLAIN_BACK/REFLECT, else `unclear` (send help menu).

**Prompt `intent_router.v1.md`**
```
You route messages from a Hindi-speaking government primary-school teacher using Abhyas, a practice app.
The teacher is currently at step: {state} — {state_description_hi}.
The app expects at this step: {expected_input}.

Classify the teacher's latest message (Hindi, Hinglish or English; it may be a speech-to-text transcript with errors):
- answer_for_step: she is doing what this step expects (explaining the move, answering reflection questions, giving profile info).
- question: she is asking a question about teaching, her classroom, children, materials, or admin.
- command_next / command_skip / command_repeat / command_help: she wants to move on, skip, hear again, or get help.
- smalltalk: greetings, thanks, unrelated chat.
- unclear: you cannot tell.
Return only the tool call.
```

---

## 5.4 `act_tagger` (fast) — what teaching acts did the teacher use?

**Input:** transcript of one teacher turn; scene context (move title, current item, children names + ids + their last line), act taxonomy with Hindi examples.

**Output schema**
```json
{"acts": ["ask_to_explain", "..."],
 "addressed_child": "ravi | priya | aman | all | null",
 "problem": {"type": "sub|add|place_value|read_word", "a": 0, "b": 0, "tens": 0, "ones": 0, "word": ""} ,
 "quote": "exact substring of the transcript that shows the main act"}
```
`problem` is null unless the teacher poses a *new* item.

**Guards:** every act ∈ taxonomy (14 values); ≤ 4 acts; `addressed_child` ∈ scene persona ids ∪ {"all", null}; `quote` is a normalised substring (5.10) of the transcript or empty; if `problem` present, its numbers/word appear in the transcript (digits, Devanagari digits or Hindi number words — use `hindi_numbers.py`).
**Fallback:** keyword tagger (`rule_engine` independent, in `llm/roles/act_tagger.py`): regex over normalised transcript —
`क्यों|कैसे|बताओ|समझाओ|how|why|explain` → ask_to_explain; `बंडल|तीली|गड्डी|bundle|stick` → concrete_representation; `सही उत्तर .* है|answer is|उत्तर \d+ है` → tell_answer; `शाबाश|बहुत अच्छा कोशिश|good try` → praise_effort; `चुप|ध्यान दो|गलत है ना` (harsh) → scold; `ध्वनि|आवाज़ निकालो|अ-क्ष-र` → phonics_sound_out; `दोनों उत्तर|किसका सही` → contrast_answers; `धीरे-धीरे करके देखो|मैं करके दिखाती` → model_step_aloud; `छोटी संख्या|पहले \d+ से` → probe_simpler_case; child name match → addressed_child. If nothing matches → `repeat_question`.

**Prompt `act_tagger.v1.md`**
```
You label what a teacher did in ONE turn of a classroom role-play. Three simulated Class 2 children are in the scene.
You do NOT decide how children respond. You ONLY label the teacher's turn.

Move being practised: {move_title_hi}
Current problem on the board: {current_item_text}
Children: {children_list}   (id, name, last thing they said)

Teaching-act taxonomy (use only these ids):
- ask_to_explain: asks a child HOW/WHY they got their answer ("कैसे किया?", "समझाओ", "बताओ तुमने क्या सोचा")
- concrete_representation: uses or asks to use bundles/sticks/objects/fingers/drawings ("10-10 तीलियों के बंडल", "गिनकर देखो")
- probe_simpler_case: gives an easier related problem to test understanding ("पहले 12 में से 7 करके दिखाओ")
- contrast_answers: puts two answers side by side and asks which is right / why ("रवि ने 45 कहा, प्रिया ने 35 — किसका सही?")
- model_step_aloud: teacher demonstrates the procedure step by step aloud
- tell_answer: teacher states the correct answer herself
- repeat_question: repeats or rephrases the same question without new support
- praise_effort: praises the child's effort or thinking ("अच्छा सोचा", "कोशिश बढ़िया थी")
- praise_generic: generic praise without content ("शाबाश", "वेरी गुड")
- scold: harsh or shaming words ("इतना भी नहीं आता?", "चुप रहो")
- involve_peer: asks another child to respond to / explain to a classmate
- phonics_sound_out: asks to sound out letters/aksharas or blends them aloud ("म-े… मे, ला… मेला")
- off_task: talk unrelated to the lesson
- give_new_problem: poses a new problem/word
Rules:
1. A turn can contain several acts; list all that clearly apply (max 4), most important first.
2. addressed_child: the child spoken to by name or clear reference; "all" if addressing the class; null if unclear.
3. If the teacher poses a new item, fill "problem" exactly from her words (numbers may be spoken in Hindi words: "बावन" = 52). Otherwise null.
4. quote: copy the exact words from the transcript that show the most important act.
5. The transcript comes from speech recognition and may contain errors. Be charitable but do not invent acts.
```
Include in the system prompt (cached) 2 worked examples per act from `content/act_examples_hi.yaml` (agent writes ~30 examples; include the Ravi example).

---

## 5.5 `child_voice` (fast) — render the engine's result as one child's line

**Input:** persona (name, age 7, temperament, `speech_style_hi`, `off_topic_lines_hi`), `ChildResponse` (kind, answer, steps with `text_hi`, affect, item), last 4 lines of the scene.

**Output schema**
```json
{"line_hi": "string"}
```

**Guards (`guard_child_line`)** — all must pass:
1. Length: 1–`MAX_CHILD_LINE_WORDS` (25) words; SILENT kind → must be empty string (we render "(प्रिया चुप है)" ourselves).
2. **Numbers:** extract every number in the line (Arabic digits, Devanagari digits ०-९, Hindi number words 0–100 such as "पैंतालीस", "पैंतीस", "बावन", "सत्रह", and "एक/दो/तीन…"). Every number ∈ `allowed_numbers`. For ANSWER/EXPLAIN_BUG/RELAPSE/SCAFFOLDED_CORRECT/CORRECT_EXPLAINED/PARROT the `answer` must appear.
3. **Forbidden:** no token in `forbidden` appears (e.g. the correct answer 35 while the child is in misconception) — check digits and number words.
4. **Literacy:** the answer string (e.g. "मल", "मछली", "मे - ला" — hyphens/spaces normalised) appears; the correct word does not appear when forbidden.
5. Stays in character: reject lines containing "AI", "assistant", more than 3 consecutive English words, or the words "गलती", "misconception", "rule", "नियम".
6. OFF_TOPIC / INTERJECT: contains no numbers at all.

**Fallback (`template_line`)**: deterministic from the response:
- ANSWER → `"{answer}!"`; EXPLAIN_BUG / RELAPSE / SCAFFOLDED_CORRECT / CORRECT_EXPLAINED → join `steps[*].text_hi` with "। " then `"। {answer}!"`; PARROT → `"{answer}… ?"`; SILENT → `""`; OFF_TOPIC/INTERJECT → `persona.off_topic_lines_hi[turn_idx % len]`; CONFUSED → `"दीदी, ये तो बहुत बड़ा है… समझ नहीं आया।"`. Prefix "हम्म… " for SCAFFOLDED_CORRECT.

**Prompt `child_voice.v1.md`**
```
You voice ONE line spoken by a 7-year-old child in a government primary school in Uttar Pradesh, in simple spoken Hindi (Devanagari).
You are an actor reading a script: the CONTENT of what the child says is already decided by a rule engine. You only choose natural words.

Child: {name} — temperament: {temperament}. Style: {speech_style_hi}. Affect now: {affect}.
What the child says this turn (kind = {kind}):
- answer: {answer}
- reasoning steps to express (in this order, may be shortened, keep every number): {steps_text}

Hard rules:
1. Use ONLY these numbers: {allowed_numbers}. You MUST say the answer {answer}. NEVER say {forbidden}.
2. At most 25 words. One or two short sentences. Address the teacher as "{teacher_address}".   # "दीदी"/"मैडम" if address_form f, "सर" if m (persona off-topic lines get the same substitution in code)
3. kind=answer: just the answer, confidently, no explanation.
   kind=explain_bug: explain the steps as if they are obviously right (the child believes them).
   kind=relapse: same as explain_bug (the child forgot what was taught).
   kind=scaffolded_correct: hesitant, thinking aloud, arrives at the answer.
   kind=correct_explained: confident and explains why.
   kind=parrot: just repeats the answer with a questioning tone, no reasoning.
   kind=off_topic / interject: one short unrelated childlike remark, no numbers.
4. Shy children speak very little. Distracted children may trail off. Confident children speak fast.
5. Never correct yourself beyond what the steps say. Never mention rules, mistakes, AI, or learning.
Return only the tool call.
```

---

## 5.6 `coach` (smart) — rubric feedback after a scene

**Input:** move (title, rubric criteria with level descriptors, `teaching_acts_effective`), full scene transcript as numbered lines (`T1 teacher: …`, `T1 ravi: …`), act tags per teacher turn, child state trajectories, attempt number, previous attempt's `change_hi` (if retry).

**Output schema**
```json
{"scores": {"<criterion_id>": 0},
 "evidence": {"<criterion_id>": "exact teacher quote or '' if score is 0 for absence"},
 "strength_hi": "one sentence",
 "change_hi": "one sentence",
 "exact_words_hi": "a sentence the teacher can literally say next time",
 "improved_since_last": true,
 "confidence": 0.0}
```

**Guards:** keys of `scores` == rubric criterion ids exactly; values ∈ {0,1,2}; for every score > 0 the evidence is a normalised substring (5.10) of a **teacher** line; strength/change/exact_words each a single sentence (≤ 1 "।"/"." inside, excluding the end) and the three together ≤ `MAX_COACH_FEEDBACK_WORDS` (60) words; respectful register (must use "आप"/"आपने", must not use "तुम"/"तुमने"); `exact_words_hi` must not contain the correct answer to the current item if the move's rubric rewards not telling the answer.
**Confidence:** `< COACH_CONFIDENCE_THRESHOLD` (0.6) → still send (with lighter framing message `coach_low_conf_prefix`), set `needs_review`, create `review_item`.
**Fallback (deterministic coach):** score each criterion from act tags: criterion has `signal_acts` in the move YAML (e.g. `crit_explaining: [ask_to_explain]`) → 2 if a signal act occurred and the target child advanced, 1 if occurred without advancement, 0 otherwise; strength/change/exact_words from the move's `feedback_bank` keyed by criterion. Mark `confidence = 0.3`, `needs_review = true`.

**Prompt `coach.v1.md`**
```
You are an experienced, kind FLN (foundational literacy and numeracy) coach in Uttar Pradesh giving feedback to a government primary teacher, colleague to colleague, in simple Hindi. The teacher just rehearsed a teaching move with three simulated children.

Move: {move_title_hi}
What good practice looks like (the effective acts for this move): {effective_acts_hi}
Rubric (score each criterion 0, 1 or 2 using the descriptors):
{rubric_block}

Transcript (teacher turns are labelled "teacher"; child lines were generated by a rule engine and are realistic):
{transcript}
Teaching acts detected per teacher turn: {acts_block}
How each child's understanding changed: {trajectory_block}
{retry_block}   # e.g. "Last attempt you asked her to change: …. Say whether she did."

Instructions:
1. Score every criterion. For each score above 0, copy the teacher's EXACT words as evidence (from teacher lines only).
2. strength_hi: ONE specific thing she did well, quoting or pointing to her words. Start with "आपने…".
3. change_hi: ONE most important change for the next attempt. Concrete, not generic.
4. exact_words_hi: ONE sentence she can literally say to the child next time, in natural classroom Hindi.
5. Total of the three sentences ≤ 60 words. Respectful "आप" register. Never shame. No English jargon.
6. confidence: your confidence that the scores match what an expert FLN coach would give (0–1). Lower it if the transcript is short, garbled, or ambiguous.
```

---

## 5.7 `fidelity_checker` (smart) — explain-it-back scoring

**Input:** move key points (`id`, `text_hi`, `must_have`), the teacher's explanation transcript.

**Output schema**
```json
{"points": [{"id": "kp1", "status": "covered|partial|missing", "quote": ""}],
 "misconceptions": ["short Hindi description of anything she said that contradicts the module"],
 "confidence": 0.0}
```
**Guards:** one entry per key point id, no extras; `covered|partial` require a quote that is a normalised substring of the transcript (fuzzy ≥ 90, 5.10); `missing` requires empty quote; misconceptions ≤ 3, each ≤ 25 words.
**Reply composition (code, not LLM):** "धन्यवाद! आपने {n_covered} में से {n_total} मुख्य बातें कहीं।" + if any must_have missing: "एक बात और याद रखें: {first missing must_have text_hi}" + if misconception: "ध्यान दें: {misconceptions[0]}".
**Fallback:** keyword overlap per key point (each key point has `keywords_hi` in YAML; ≥ 50% present → covered, ≥ 25% → partial), confidence 0.3, needs_review.

**Prompt `fidelity_checker.v1.md`**
```
A government primary teacher has just listened to a 2-minute explanation of a teaching move and explained it back in her own words (speech-to-text transcript, may contain recognition errors).
Judge, for each key point below, whether she covered it (same meaning, own words are fine), partially covered it, or missed it.
Key points:
{key_points_block}
Teacher's explanation:
"""{transcript}"""
Rules: For covered/partial, copy the exact words from her explanation that show it. Do not give credit for vague statements. List any statement that contradicts the key points as a misconception (Hindi, short). confidence: 0–1.
```

---

## 5.8 `question_classifier` (fast) + `guide_answerer` (smart) — Ask any time

**question_classifier output**
```json
{"category": "pedagogy | classroom_management | admin | out_of_scope",
 "needs_clarification": false,
 "clarifying_question_hi": "",
 "search_query_hi": "short Hindi keyword query for the guides",
 "confidence": 0.0}
```
Guard: if `needs_clarification` then `clarifying_question_hi` non-empty and ≤ 20 words; ask at most **one** clarifying question per question thread (`question.clarifying_asked`).
out_of_scope → polite canned reply (`ask_out_of_scope`), no retrieval. admin → canned "यह जानकारी आपके BEO/ARP कार्यालय से मिलेगी" + escalate to ARP.

**guide_answerer input:** question, category, top-k (`RETRIEVAL_TOP_K` = 5) chunks with ids, source short names, section, page.
**Output schema**
```json
{"answer_hi": "", "source_ids": ["chunk-id"], "try_this_week_hi": "", "confidence": 0.0}
```
**Guards:** `source_ids` non-empty and ⊆ retrieved ids; answer ≤ `MAX_GUIDE_ANSWER_WORDS` (80) words; no numbers/claims of policy unless present in a cited chunk (heuristic: every number in answer appears in a cited chunk); respectful register.
**Escalation:** if no chunk scores ≥ `RETRIEVAL_MIN_SCORE` or confidence < `GUIDE_CONFIDENCE_THRESHOLD` (0.6) or guard fails twice → reply `ask_escalated` ("मैं आपके ARP से पूछकर बताती हूँ…"), create `review_item(kind='question')`, add to ARP digest.
**Reply composition:** answer + "स्रोत: {source_short_hi}, पृष्ठ {page}" + try_this_week + schedule follow-up job at +48 h.

**Prompt `guide_answerer.v1.md`**
```
You answer a government primary teacher's question using ONLY the official guide excerpts below. Answer in simple, respectful Hindi (आप), ≤ 80 words, practical, for a real classroom with few materials, multi-grade classes and irregular attendance.
If the excerpts do not contain the answer, set confidence below 0.4 and say so briefly — do not invent.
Question ({category}): {question}
Excerpts:
{chunks_block}   # [chunk-id] (source, section, page): text
Return: answer_hi; source_ids you actually used; try_this_week_hi = one small action she can try this week (≤ 20 words); confidence.
```

---

## 5.9 Build-time roles (content pipeline, 10)

| Role | Input | Output | Guard |
|---|---|---|---|
| `move_generator` | source chunks for one topic, move schema, an approved example move | full move YAML as JSON (schema in 10) | JSON Schema valid; every key point has `source_chunk_ids` ⊆ given; scenario items computed by rule engine (validator recomputes); Hindi NFC; lengths |
| `move_reviewer` | generated move + source chunks + rubric for content quality | `{issues: [{field, severity, note_hi}], approve_recommendation}` | schema |
| `model_teacher` | move, scenario, persona list | `model_rehearsal` script lines (teacher lines + act ids); **child lines are then generated by running the rule engine + child_voice**, never by this role | teacher lines' acts must be effective acts; script ends with all children CORRECT when run through the engine |
| `page_ocr` | page image (PNG) of a Hindi PDF whose text layer is garbled (legacy fonts like Kruti Dev) | `{text_hi}` | Devanagari ratio ≥ 0.6 |

Prompts for these: write them in `llm/prompts/` following the same style; include the approved seed move `NUM_SUB_REGROUP_BUNDLES` as the few-shot example.

## 5.10 Text normalisation for guards (`llm/guards.py › norm`)

`norm(s)`: NFC → lowercase Latin → Devanagari digits → Arabic → strip punctuation `।,.!?;:"'()-–—` → collapse whitespace → remove nukta variants (ड़→ड़ canonical) → remove zero-width joiners.
Substring check: `norm(quote) in norm(source)`; if false, `rapidfuzz.fuzz.partial_ratio(norm(quote), norm(source)) ≥ QUOTE_FUZZY_MIN` (90).

`hindi_numbers.py`: `extract_numbers(text) -> list[int]` handling Arabic digits, Devanagari digits, and Hindi number words 0–100 (full table: शून्य, एक, दो, तीन, चार, पाँच/पांच, छह/छः, सात, आठ, नौ, दस, ग्यारह, बारह, तेरह, चौदह, पंद्रह/पन्द्रह, सोलह, सत्रह, अठारह, उन्नीस, बीस, इक्कीस … निन्यानवे, सौ — include common spelling variants and Roman Hinglish: "paintalis", "paintees", "baawan", "satrah", etc. for the numbers used in seed content at least). Exhaustively unit-test 0–100 Devanagari words.

## 5.11 Golden tests (`backend/tests/golden/`)

For each runtime role, ≥ 5 input→output JSON fixtures (written by hand, checked by a team member) used by MockLLM and by `test_guards.py` (good outputs pass, deliberately bad variants fail with the expected guard). `make test-live` re-runs the inputs against real Claude and asserts guard pass rate ≥ 90%.

---

## FILE: spec/06_speech.md

# 06 — Speech (STT, TTS, audio)

## 6.1 Audio pipeline (`speech/audio.py`)

All conversions via `ffmpeg` subprocess, stdin/stdout pipes. If a temp file is unavoidable, use `tempfile` under `/dev/shm` and delete in `finally`. **Never persist teacher audio.**

| Function | ffmpeg | Use |
|---|---|---|
| `to_wav16k(bytes, mime) -> bytes` | `-i pipe:0 -ac 1 -ar 16000 -f wav pipe:1` | STT input (from OGG/Opus WhatsApp, WebM/Opus or MP4/AAC browser) |
| `duration_s(bytes) -> float` | `ffprobe` | enforce limits |
| `split_for_stt(wav, max_s=25) -> list[bytes]` | `silencedetect=noise=-35dB:d=0.4` then cut at the silence nearest ≤ 25 s; hard cut if none | Sarvam REST is for clips < 30 s; explain-back is up to 60 s |
| `to_ogg_opus(wav) -> bytes` | `-c:a libopus -b:a 24k -ac 1 -ar 48000 -application voip -f ogg` | WhatsApp voice reply (WhatsApp requires OGG with Opus codec, mono) |
| `to_web(wav) -> bytes` | same OGG/Opus; plus `to_mp3(wav)` (`-b:a 32k`) fallback for Safari/iOS | web chat playback |
| `pitch_shift(wav, factor) -> wav` | `-af asetrate=22050*{f},aresample=22050,atempo={1/f}` | child voices |

Limits (config): `MAX_INBOUND_AUDIO_S = 90`, `EXPLAIN_BACK_MAX_SECONDS = 60` (soft: transcribe up to 90 s, tell her next time keep it to 1 min), `REHEARSE_TURN_MAX_S = 30`. Reject > 90 s with message `audio_too_long`.

## 6.2 STT (`speech/stt.py`)

```python
class Transcript(BaseModel): text: str; confidence: float; language: str | None; provider: str; ms: int
class STTProvider(Protocol):
    async def transcribe(self, wav16k: bytes, lang: str = "hi-IN", keyterms: list[str] = []) -> Transcript: ...
```

Providers (select by `STT_PROVIDER`):

1. **`sarvam`** (default for hosted demo). `POST https://api.sarvam.ai/speech-to-text`, header `api-subscription-key: $SARVAM_API_KEY`, multipart: `file` (wav), `model` = `$SARVAM_STT_MODEL` (default `saaras:v4`), `language_code=hi-IN`, `keyterms` = JSON array (≤ 50): persona names (रवि, प्रिया, अमन), move vocabulary (बंडल, तीली, हासिल, दहाई, इकाई, मात्रा, अक्षर), and the current item's numbers as Hindi words. Response `transcript`. Confidence: Sarvam returns `language_probability` only when auto-detecting; set `confidence = 0.9` when transcript non-empty and contains ≥ 1 Devanagari/Latin word, else 0.0. For split clips: call in parallel (`asyncio.gather`), join with space.
   **Verify the current API reference at https://docs.sarvam.ai before coding** (field names and model ids change). Keep all provider-specific strings in this one module.
2. **`bhashini`** (roadmap / optional): ULCA pipeline API (ASR `hi`). Implement only if a key is available (HUMAN INPUT); stub raising `ProviderNotConfigured` otherwise.
3. **`google`** (optional): Cloud Speech-to-Text v2 `hi-IN`. Stub unless key.
4. **`mock`**: returns the `text` stored alongside test audio fixtures (`tests/fixtures/audio/*.json`), or, for unknown audio, `MOCK_STT_TEXT` env (default the Ravi turn "रवि, 52 में से 17 कैसे घटाया? बताओ।"). The **web channel in mock mode also offers a text box** so evaluators/devs can type what they "said".

Error handling: timeout `STT_TIMEOUT_S = 8` per clip; one retry; then `STTUnavailable` → state unchanged, message `stt_failed`.
Low confidence (`< STT_MIN_CONFIDENCE`, 0.5) or < 2 words → confirm flow (08).
Text normalisation of transcripts: NFC, collapse whitespace; keep original numerals.

## 6.3 TTS (`speech/tts.py`, `speech/voices.py`)

```python
class TTSProvider(Protocol):
    async def synthesize(self, text_hi: str, voice: VoiceSpec) -> bytes: ...   # returns WAV 22.05 kHz mono
class VoiceSpec(BaseModel): provider_speaker: str; model: str; pace: float = 1.0; pitch_factor: float = 1.0
```

**Voices** (`content/voices.yaml`, loaded at startup; provider speaker ids are config, verify against Sarvam docs):

| voice id | Role | Sarvam model / speaker (default) | pace | pitch_factor (ffmpeg) |
|---|---|---|---|---|
| `abhyas` | system narrator / learn scripts | `bulbul:v3` / `ritu` | 0.95 | 1.0 |
| `coach` | feedback | `bulbul:v3` / `neha` | 0.95 | 1.0 |
| `model_teacher` | model rehearsal teacher | `bulbul:v3` / `pooja` | 1.0 | 1.0 |
| `child_ravi` | confident boy | `bulbul:v3` / `aayan` | 1.15 | 1.22 |
| `child_priya` | shy girl | `bulbul:v3` / `suhani` | 0.9 | 1.18 |
| `child_aman` | distracted boy | `bulbul:v3` / `soham` | 1.05 | 1.25 |

Pick final speakers by ear in task T15 (Vedant): generate the same line in 6–8 candidate speakers, choose 3 clearly distinct child-like voices, record choice in `PROGRESS.md`.

Provider `sarvam`: `POST https://api.sarvam.ai/text-to-speech`, header `api-subscription-key`, JSON `{text, language_code: "hi-IN", model, speaker, pace, speech_sample_rate: 22050}`; response `audios[0]` base64 WAV. Text limit: chunk at sentence boundaries if > 1500 chars (learn scripts) and concatenate WAVs with ffmpeg `concat`.
Numbers: before TTS, convert Arabic digits in child lines to Hindi number words (`hindi_numbers.to_words`) so "45" is spoken "पैंतालीस", not "four five".
Provider `mock`: returns a short silent/beep WAV whose length ∝ text length (so latency and players work).

**Cache** (`speech/cache.py`): key = sha256(voice_id + provider_speaker + model + pace + pitch + NFC text). Store final OGG and MP3 in `tts_cache`. Pre-warm at startup / on content publish: all learn scripts, model rehearsal lines, every message in `messages_hi.yaml` that has `audio: true`, and child template fallback lines for the seed items.

**Pre-recorded audio** (preferred over TTS for fixed prompts, HUMAN INPUT optional): if `content/audio/<key>.ogg` exists for a message key or learn script, use it instead of TTS. Name: `learn_<move_id>.ogg`, `msg_<message_key>.ogg`.

## 6.4 Latency instrumentation

Wrap each stage with a timer; store `turn.stage_ms` = `{download, convert, stt, tagger, engine, voice, guard, tts, upload, send}` and `latency_ms` = inbound received → last outbound sent. Expose p50/p95 on the admin page and via `eval/latency/benchmark_latency.py`.

Optimisations to implement:
- send the child's **text line immediately** on the web channel (before TTS) — perceived latency.
- run TTS for the child line and the template audio for "next" buttons in parallel.
- warm the Anthropic client and HTTP connection pools at startup (`httpx.AsyncClient` with keep-alive).
- prompt caching on act_tagger and child_voice system prompts.

---

## FILE: spec/07_channels.md

# 07 — Channels and HTTP API

Two channels share one brain (`ConversationService`). A teacher has a `preferred_channel`; outbound goes there. Web teachers are app_users with role teacher linked to a teacher row; WhatsApp teachers are created on first inbound.

## 7.1 Inbound pipeline (both channels)

```
receive → auth/verify → dedupe on (channel, channel_msg_id) → persist message(in, text|null)
→ 200/202 immediately → BackgroundTask: process_inbound()
process_inbound: [audio? download → to_wav16k → STT → discard audio] → set message.text = transcript
→ ConversationService.handle(inbound) → list[OutboundMessage] → channel.send() → persist message(out)
```
Per-teacher serialisation: an `asyncio.Lock` keyed by teacher_id (in-process dict; single instance deploy) so two quick voice notes are processed in order. If a second message arrives while a REHEARSE turn is processing, queue it.

## 7.2 WhatsApp Cloud API (`channels/whatsapp/`)

Direct Meta Cloud API (no BSP needed for the prototype; Gupshup/other BSP is a roadmap swap behind the same client). Graph base `https://graph.facebook.com/{WHATSAPP_GRAPH_VERSION}` (env, default `v23.0` — **verify the current version in Meta docs**). Auth: `Authorization: Bearer $WHATSAPP_ACCESS_TOKEN` (System User permanent token, HUMAN INPUT).

**Webhook** `GET /webhooks/whatsapp`: if `hub.mode == "subscribe"` and `hub.verify_token == WHATSAPP_VERIFY_TOKEN` → return `hub.challenge` as plain text, else 403.
**Webhook** `POST /webhooks/whatsapp`:
- Verify `X-Hub-Signature-256: sha256=<hex>` = HMAC-SHA256(`WHATSAPP_APP_SECRET`, raw body), constant-time compare; 401 on mismatch.
- Parse `entry[].changes[].value.messages[]`; ignore `statuses[]` (but log delivery failures).
- Message types: `text` (`text.body`), `audio` (`audio.id`, `audio.mime_type`, `audio.voice`), `interactive` (`button_reply.id`), `button` (template quick-reply payload). Others (image, sticker, location) → reply `unsupported_type`.
- `from` (wa_id) → E.164 → `phone_hash`; find or create teacher (`onboarding_state = NEW`), store encrypted number in `teacher_contact`. Update `last_inbound_at`.
- Always return 200 within 2 s (Meta retries otherwise); processing in background.

**Media download** (`media.py`): `GET /{media_id}` → `{url, mime_type}`; `GET url` with bearer → bytes (in memory). Max 16 MB.
**Media upload**: `POST /{WHATSAPP_PHONE_NUMBER_ID}/media` multipart `file` (audio/ogg; codecs=opus), `type=audio/ogg`, `messaging_product=whatsapp` → `id`. Cache media id per TTS cache key for 25 days (Meta media ids expire after ~30 days).

**Send** (`client.py`) `POST /{WHATSAPP_PHONE_NUMBER_ID}/messages`:
- text: `{"messaging_product":"whatsapp","to":E164,"type":"text","text":{"body": …}}` (≤ 4096 chars)
- audio: `{"type":"audio","audio":{"id": media_id}}` (if the API version supports a voice-note flag, set it so it renders as a voice message — verify docs)
- buttons: `{"type":"interactive","interactive":{"type":"button","body":{"text": …},"action":{"buttons":[{"type":"reply","reply":{"id": …,"title": ≤20 chars}}]}}}` (max 3)
- list (for > 3 options, e.g. classes taught): `interactive.type = "list"` with one section, ≤ 10 rows.
- template: `{"type":"template","template":{"name": …,"language":{"code":"hi"},"components":[{"type":"body","parameters":[{"type":"text","text": …}]}]}}`
- Order per turn: text → audio → buttons. Rate limit: token bucket 20 msg/s global; retry 429/5xx with backoff (0.5 s, 2 s, 8 s).

**24-hour window** (`sessions/window.py`): `can_send_freeform = now - teacher.last_inbound_at < 24h`. Business-initiated messages outside the window **must** be an approved template (`content/whatsapp_templates.yaml`). Log each template send in `template_send` with `est_cost_inr = WHATSAPP_UTILITY_COST_INR` (config, 0.12 — verify current Meta India rate). Tests: inside window → freeform; outside → template; template not approved (`approved: false` in YAML) → skip send, log, show on admin page.

**Test number setup** (HUMAN, documented in `docs/whatsapp_setup.md` which the agent writes): Meta developer app → WhatsApp product → test number → add up to 5 recipient numbers → permanent token via System User → webhook URL `https://<host>/webhooks/whatsapp` + verify token → subscribe `messages` field → create templates (Hindi, Utility) from the YAML → wait for approval.

## 7.3 Web channel (`channels/web.py` + `web/teacher.py` + `static/chat.js`)

Outbound messages are written to `message` (direction out); the client fetches them. **Polling, not websockets/SSE** (robust on flaky mobile networks, works through any proxy).

- `POST /api/chat/text` `{client_msg_id, text}` → 202 `{message_id}`
- `POST /api/chat/audio` multipart `{client_msg_id, file}` (webm/opus, ogg/opus or mp4/aac from MediaRecorder; ≤ 2 MB) → 202
- `POST /api/chat/button` `{client_msg_id, button_id}` → 202
- `GET /api/chat/messages?after=<message_id>` → `{messages: [...], pending: bool}`; client polls every 1.5 s while `pending` (a turn is processing for this teacher), else every 20 s, and immediately after any send.
- `GET /api/audio/<audio_ref>.<ogg|mp3>` → cached synthetic audio (auth required; `Cache-Control: private, max-age=31536000, immutable`).
- `POST /api/chat/rating` `{scene_id, rating}` (realism 1–5)
- `POST /api/settings` `{lite_mode}`

`client_msg_id` is a UUID generated in the browser; the server dedupes, so the client can blindly retry on network errors (outbox in IndexedDB — see 09).

## 7.4 Full HTTP route table

| Method & path | Role | Purpose |
|---|---|---|
| `GET /` | public | landing: what Abhyas is, login button, "WhatsApp पर जुड़ें" QR/link (if number configured) |
| `GET/POST /login`, `POST /logout` | public | session cookie |
| `GET /healthz` | public | `{"ok":true,"db":true,"version":GIT_SHA}` |
| `GET /teacher` | teacher | chat PWA |
| `GET /teacher/progress` | teacher | own evidence ladder per move, scores history, consent settings, "delete my data" |
| `GET /arp` | arp | weekly digest (cluster) |
| `GET /arp/teacher/{id}` | arp | consenting teacher detail; 403 otherwise |
| `POST /arp/observation` | arp | log classroom observation (evidence level 4) |
| `POST /arp/question/{id}/answer` | arp | answer escalated question → sent to teacher |
| `GET /trainer` | trainer | module × batch aggregates with suppression |
| `GET /trainer/export.csv` | trainer | same aggregates CSV (suppressed rows blank) |
| `GET /review` | coach | review queue: low-confidence scores, escalated questions, guard failures |
| `POST /review/{id}` | coach | resolve (corrected scores → stored as calibration labels) |
| `GET /review/moves`, `GET/POST /review/moves/{id}` | coach | view/edit YAML (form + raw), approve (2 approvals → approved) |
| `GET /admin` | admin | latency p50/p95, LLM fallback rates, template sends & cost, guard failures, scheduled jobs |
| `POST /admin/fast-forward/{teacher_id}` | admin | run that teacher's pending scheduled jobs now (demo) |
| `POST /admin/reset-demo` | admin | restore demo teachers to seeded state |
| `POST /admin/publish` | admin | publish content release |
| `GET/POST /webhooks/whatsapp` | Meta | 7.2 |
| `/api/chat/*`, `/api/audio/*`, `/api/settings` | teacher | 7.3 |

All HTML pages: CSRF token on POST forms (double-submit cookie). Rate-limit login (5/min/IP).

---

## FILE: spec/08_conversation_flow.md

# 08 — Conversation flow, state machine, intents, jobs

All teacher-facing strings come from `content/messages_hi.yaml` (seed: `content-seed/messages_hi.yaml`) by key. Never hard-code Hindi text in Python. Message keys referenced below in `monospace`.

## 8.1 Onboarding (`teacher.onboarding_state`)

| State | Bot sends | Expected input → next |
|---|---|---|
| `NEW` | `welcome` (+ audio) + `consent_service` text + buttons [`btn_agree` सहमत हूँ] [`btn_more` और जानें] [`btn_decline` नहीं] | agree → log consent → `JOIN_CODE`; more → `consent_details` then same buttons; decline → `consent_declined`, stay `NEW` |
| `JOIN_CODE` | `ask_join_code` ("आपके ARP ने जो कोड दिया है, वह भेजें। कोड नहीं है तो 'नहीं' लिखें।") | valid code (`invite_code` table → cluster_id, batch_id, district) → `PROFILE_NAME`; "नहीं" → unassigned cluster `UNASSIGNED` → `PROFILE_NAME`. Web demo users skip (pre-mapped) |
| `PROFILE_NAME` | `ask_name` | any text/voice → store first 40 chars → `PROFILE_ADDRESS` |
| `PROFILE_ADDRESS` | `ask_address_form` ("आपको कैसे संबोधित करें?") + buttons [शिक्षिका] [शिक्षक] | → `teacher.address_form` f/m (selects `text_m` message variants) → `PROFILE_EXPERIENCE` |
| `PROFILE_EXPERIENCE` | `ask_experience` + list [0-1 साल, 2-5, 6-10, 10+] | choice → `experience_band`, `first_year = (0-1)` → `PROFILE_CLASSES` |
| `PROFILE_CLASSES` | `ask_classes` + list [कक्षा 1, कक्षा 2, कक्षा 3, कक्षा 1-2, कक्षा 2-3, कक्षा 1-3] | → `classes` → `SHARE_CONSENT` |
| `SHARE_CONSENT` | `consent_share_scores` + buttons [हाँ] [नहीं] | → log → `PLACEMENT_INTRO` |
| `PLACEMENT_INTRO` | `placement_intro` (+ Ravi's first line: "45!" via engine/voice for 52−17) | voice/text → `PLACEMENT` turn 1 |
| `PLACEMENT` | 2 teacher turns with Ravi only (engine placement mode) | after turn 2 → `placement_done` (no score shown, warm message) → compute move path → `READY` |
| `READY` | `ready_first_move` | starts weekly loop at `LEARN` immediately |

Add table `invite_code(code text pk, cluster_id, batch_id, district, active bool)` to the migration; seed `KNP-C01-B1`, `KNP-C01-B2`, `DEMO`.

## 8.2 Weekly loop (`session_state.state`)

| State | On enter (bot sends) | Inputs & transitions |
|---|---|---|
| `LEARN` | `learn_intro` with move title; learn script audio (pre-recorded or TTS, ≤ 2 min) + **text summary** (key points as 4–6 short lines) ; buttons [`btn_understood` समझ गई, आगे] [`btn_replay` फिर से सुनें] | understood → `EXPLAIN_BACK`; replay → resend audio |
| `EXPLAIN_BACK` | `explain_back_prompt` ("अब 1 मिनट में अपने शब्दों में बताइए: इस तरीके में सबसे ज़रूरी क्या है?") ; buttons [`btn_skip` छोड़ें] | voice/text → fidelity_checker → reply (05 §5.7) → `MODEL`; skip → `MODEL` |
| `MODEL` | `model_offer` ; buttons [`btn_listen` सुनें] [`btn_skip` छोड़ें] | listen → send model rehearsal: text transcript (one message, speaker-labelled) + one concatenated audio (voices per speaker) → then `REHEARSE_INTRO`; skip → `REHEARSE_INTRO` |
| `REHEARSE_INTRO` | `rehearse_intro` (scene: class, problem on board, "जब तैयार हों, बच्चों से बात करना शुरू करें। खत्म करने के लिए 'बस' बोलें।") + each child's opening line (engine MISCONCEPTION answers, voiced) | first voice/text → `REHEARSE` (that input is turn 1) |
| `REHEARSE` | — | each input = one teacher turn → SceneRunner (02 §2.2) → child line(s). Stop word / scene end → `FEEDBACK`. Keyword question prefix ("सवाल:", "प्रश्न:") → ASK |
| `FEEDBACK` | coach output: text (strength, change, exact words) + coach audio; if low confidence prefix `coach_low_conf_prefix`; then realism rating list (1–5) ; buttons [`btn_retry` फिर से अभ्यास] [`btn_continue` आगे बढ़ें] | retry (if `rehearse_attempts < MAX_REHEARSAL_RETRIES_PER_WEEK` (3)) → new scene → `REHEARSE_INTRO`; else `retry_limit` → continue; continue → `TRY_IN_CLASS`. Rating → `realism_rating` |
| `TRY_IN_CLASS` | `try_in_class` + peer checklist (numbered) + 2 reflection questions ; buttons [`btn_peer` साथी ने देखा] [`btn_self` खुद बताऊँगी] [`btn_later` बाद में] ; schedule `followup_try_in_class` +72 h | peer → `REFLECT_PEER`; self → `REFLECT_SELF`; later → stay (reminder job) |
| `REFLECT_PEER` | each checklist item with [हाँ] [नहीं] buttons, one at a time | after last → evidence level 3 → `DONE` |
| `REFLECT_SELF` | reflection Q1, then Q2 (voice/text) | after Q2 → evidence level 2 → `DONE` |
| `DONE` | `week_done` summary (evidence level reached, next move title) ; buttons [`btn_next_move` अगला तरीका] [`btn_progress` मेरी प्रगति] | next move: starts next week's move now (demo-friendly) |

**Evidence:** completing `REHEARSE` (scene ended with ≥ 3 teacher turns) → level 1. Higher levels from REFLECT / ARP observation. `adoption_evidence` keeps all rows; views show the max level per teacher × move.

**Resume rule:** any inbound after > 6 h of inactivity in a mid-week state → `resume_prompt` ("आप {state_name_hi} पर थीं। आगे बढ़ें?") + buttons [आगे बढ़ें] [शुरू से].

## 8.3 Intents (checked in this order, `core/intents.py`)

1. **Button id** → direct.
2. **Global keywords** (normalised, whole-message or prefix match):

| Intent | Keywords (Hindi / Hinglish / English) | Effect |
|---|---|---|
| help | मदद, help, menu, मेनू | `help_menu` (list: आगे बढ़ें, प्रश्न पूछें, मेरी प्रगति, लाइट मोड, सहमति बदलें) |
| stop_scene | बस, रुको, खत्म, stop, bas (REHEARSE only) | end scene → FEEDBACK |
| next | आगे, अगला, शुरू, next, start, aage, shuru | advance where allowed (template quick-reply payloads "शुरू"/"आगे" land here) |
| skip | छोड़ें, skip, chhodo | skip skippable step |
| repeat | फिर से, दोबारा, repeat, phir se | resend last bot prompt |
| ask | सवाल, प्रश्न, question, sawal (+ optional text) | ASK flow |
| lite_toggle | लाइट मोड, lite | toggle `lite_mode` (text-only replies) |
| progress | प्रगति, progress | progress summary |
| consent | सहमति, consent | consent settings flow |
| delete | मेरा डेटा हटाएँ, delete my data | confirm → purge → `data_deleted` |

3. **State-specific expectation:** in `EXPLAIN_BACK`, `REFLECT_SELF`, `PROFILE_NAME`, `PLACEMENT`, `REHEARSE` the input is taken as the step's answer **without** calling intent_router (REHEARSE: always a teacher turn).
4. Otherwise → `intent_router` (05 §5.3).

STT low confidence (06) → `stt_confirm` "मैंने सुना: '{text}'. सही है?" [हाँ] [फिर से बोलूँगी] — except in REHEARSE where low-confidence turns proceed but are flagged in the transcript.

## 8.4 ASK flow

`prior_state = state; state = ASK` → question_classifier → (optional one clarifying question → wait) → retrieval → guide_answerer or escalation (05 §5.8) → send answer → `ask_resume` + re-send prior state's prompt → `state = prior_state`. Questions during onboarding are answered then onboarding resumes.

## 8.5 Personal move path (`sessions/path.py`)

Deterministic score per move (lower = sooner), recomputed after placement and after each week:
```
score = month_rank(move.sankul_month vs current month; current month = 0, next = 1, …)*10
      − 15 if placement used tell_answer and move.effective has ask_to_explain
      − 10 if teacher.classes contains 1 and move.domain == literacy or move.id startswith NUM_PLACE_VALUE
      − 5 * (2 − min rubric score on this move's criteria in last attempt)   # revisit weak moves (only for moves already done)
      − 8 if teacher asked a question whose category matched move.tags
      + 100 if move already DONE with evidence ≥ 2
first_year teachers: fixed induction order from content/induction_track.yaml (seed: place value → subtraction → addition → reading)
```
Store top order in `move_path` with `reason` text.

## 8.6 Scheduled jobs (`jobs/`)

APScheduler interval tick every 60 s pulls due rows from `scheduled_job` (status pending, run_at ≤ now) with `FOR UPDATE SKIP LOCKED`; cron-style recurring jobs are created by a daily "planner" job.

| Kind | When | Action |
|---|---|---|
| `weekly_prompt` | Monday 09:00 IST per active teacher in `DONE` or with no session this week | create session_state for next move in path (`LEARN`); send `tpl_weekly_move` template if outside window else freeform `weekly_move` |
| `reminder` | 72 h after last state change if not `DONE` (max 1 per week) | `tpl_reminder` / `reminder` |
| `followup_question` | +48 h after an answered question | `tpl_followup_question` "क्या {topic} वाला सुझाव काम आया?" [हाँ] [नहीं] [अभी नहीं] → `question.followup_result`; "हाँ" → evidence level 2 for linked move if any |
| `followup_try_in_class` | +72 h after entering TRY_IN_CLASS | `tpl_try_in_class_followup` |
| `arp_digest` | Saturday 17:00 IST per ARP | build digest snapshot; send `tpl_arp_digest` with link `/arp` |
| `aggregates` | nightly 02:00 IST | recompute `agg_module_batch` |
| `retention_purge` | nightly 03:00 IST | 3.4 |

`POST /admin/fast-forward/{teacher_id}` sets that teacher's pending jobs `run_at = now()` and ticks immediately. Tests use a fake clock (`freezegun` or injected `Clock`).

## 8.7 Sankul mode (minimal in this build)

ARP page has "संकुल अभ्यास शुरू करें" → generates a 6-char session code; any teacher who sends `संकुल <code>` joins a shared scene (mode `sankul`) for the month's move where turns from any member's phone drive one scene; the ARP's page shows the live transcript. If time is short (see 14), implement as: ARP starts a scene from the web on one phone (normal web chat logged in as ARP with role-play enabled) and logs one observation per attending teacher. Mark which version shipped in `PROGRESS.md`.

## 8.8 State machine tests (`tests/unit/test_state_machine.py`)

- Every (state, input-kind/intent) pair in 8.1–8.4 → expected next state and message keys (table-driven, 100% transition coverage; generate the table from the state machine definition and assert every edge is exercised).
- ASK from every weekly state resumes the same state and re-sends its prompt.
- Retry limit enforced at 3.
- 24-h window: weekly_prompt uses template when `last_inbound_at` > 24 h ago, freeform otherwise.
- Delete flow purges and the next inbound starts at `NEW`.
- Full happy path run (MockLLM, MockSTT text inputs) from `NEW` to `DONE` in one test, asserting evidence level 2 or 3 recorded.

---

## FILE: spec/09_web_apps.md

# 09 — Web apps (teacher PWA, ARP, trainer, coach review, admin)

Server-rendered Jinja2 + vanilla JS + one `app.css`. No framework, no build step, no external fonts/CDNs (fonts: system stack `"Noto Sans Devanagari", "Mukta", system-ui, sans-serif`; ship Noto Sans Devanagari subset WOFF2 locally only if < 60 KB). All UI text in Hindi from `messages_hi.yaml` (admin/coach pages may be English+Hindi).

Performance budget per page: HTML+CSS+JS < 150 KB uncompressed, < 50 KB gzipped; no image > 20 KB; works on Chrome Android 80+ and Safari iOS 14+. Lighthouse mobile performance ≥ 90 on `/teacher` (record score in `PROGRESS.md`).

## 9.1 Visual design

- Calm, warm, trustworthy. Palette tokens on `:root`: `--bg #FAF7F2`, `--surface #FFFFFF`, `--ink #1F2421`, `--muted #5E6662`, `--brand #1F6F5C` (deep green), `--brand-ink #FFFFFF`, `--accent #E0A100` (marigold), `--child-ravi #2F6FDE`, `--child-priya #C2417A`, `--child-aman #7A5AC8`, `--danger #B3261E`; dark-mode variants under `prefers-color-scheme: dark`.
- Base font 17 px, line-height 1.6 (Devanagari needs height); tap targets ≥ 48 px; contrast AA.
- Logo: simple wordmark "अभ्यास" + small chalk-line icon (inline SVG, original).

## 9.2 Teacher chat (`/teacher`) — WhatsApp-like, built for bad networks

Layout (mobile first, max-width 640 px centred on desktop):
- **Header:** "अभ्यास" · this week's move title · step chip (e.g. "चरण 4/7 · अभ्यास") · menu (प्रगति, लाइट मोड, सहमति, मदद, लॉग आउट).
- **Message list:** bubbles. Bot bubbles show speaker avatar/colour chip (अभ्यास, कोच, आदर्श शिक्षिका, रवि, प्रिया, अमन). Each bot bubble always shows **text**; if audio exists, a compact play button with duration; audio is fetched **only when tapped** in lite mode, or auto-preloaded (`preload="none"` then fetch on visibility) in normal mode. Auto-play the newest child line once (user gesture permitting).
- **Buttons:** rendered as chips under the last bot message; disabled after use.
- **Composer:** large **hold-to-record mic** (also tap-to-start/tap-to-stop mode for accessibility), live timer, slide-to-cancel; text field; send. During REHEARSE a strip above the composer shows the 3 children (name + colour + who spoke last) and the problem on the board. Children's internal states are **not** shown during the scene (avoids gaming); the state trajectory ("रवि: ग़लत तरीका → समझाया → सही") is revealed in FEEDBACK.
- **Pending indicator:** after sending, a typing bubble "रवि सोच रहा है…" (speaker = expected responder unknown → generic "बच्चे सोच रहे हैं…").
- **Network banner:** offline → "इंटरनेट नहीं है — संदेश भेजे जाने के लिए रखे गए हैं" ; slow (> 8 s for a request) → suggests लाइट मोड.

Recording (`static/recorder.js`): `MediaRecorder` with `audio/webm;codecs=opus` (Chrome/Android) or `audio/mp4` (Safari); `audioBitsPerSecond: 16000`; mono constraints `{channelCount: 1, echoCancellation: true, noiseSuppression: true}`; max 90 s (auto-stop), min 0.7 s (discard). Show mic-permission help in Hindi if denied.

**Outbox** (`static/chat.js`): every outgoing item (text/audio blob/button) gets `client_msg_id` and is stored in IndexedDB before upload; uploader retries with backoff (2, 4, 8, 16, 30 s…) until 2xx; shows clock icon → single tick (server accepted) → reply arrives. Survives page reloads. This is the "works on patchy networks" story — demo it.

**Service worker** (`static/sw.js`): cache-first for static assets and for `/api/audio/*` already played (LRU 30 items); network-first for HTML; offline fallback page `offline.html` that still shows the last 50 messages from IndexedDB and this week's learn summary + peer checklist (so the **try-in-class checklist works fully offline**).
**Manifest:** name "अभ्यास", short_name "Abhyas", theme `--brand`, icons 192/512 (simple SVG→PNG generated by script), `display: standalone`.

**Mock-mode helpers** (only when `STT_PROVIDER=mock` or `?demo=1`): under the mic, a "बोलने की जगह लिखें" hint and the 3–5 evaluator sample inputs as tappable chips that send the sample audio file (from `eval/samples/audio/`) — so evaluators can test voice without speaking Hindi.

`/teacher/progress`: per move cards: title, evidence ladder (5 steps, filled up to max level, Hindi labels: अभ्यास किया · स्वयं बताया · साथी ने देखा · ARP ने देखा · बच्चों में सुधार), rubric score history (small inline bars, no chart lib), explain-back points covered. Consent toggles (share with ARP, research). "मेरा डेटा हटाएँ" (confirm dialog page, not JS `confirm()`).

## 9.3 ARP digest (`/arp`)

Header: cluster name, week selector (last 6 weeks), banner if demo data.
Sections:
1. **इस सप्ताह** — counts: active teachers, completed loops, moves practised (no names needed).
2. **कौन अभ्यास कर रहा है** — table of consenting teachers: name, school, this week's move, step reached, max evidence, last rehearsal rubric (0–2 per criterion as dots), "मदद चाहिए" flag (low score or escalated question). Non-consenting teachers appear only as an aggregate count row "अन्य N शिक्षक (स्कोर साझा नहीं)".
3. **सुझाई गई कक्षा-भ्रमण सूची** — consenting teachers with lowest scores on the month's move, with the move's peer checklist link (printable) and "अवलोकन दर्ज करें" form (checklist yes/no + notes) → `arp_observation` + evidence level 4.
4. **अनुत्तरित प्रश्न** — escalated questions (teacher shown only if consenting, else "शिक्षक #ab12"); answer box → sent to teacher via channel (template if outside window) and stored; resolves review item.
5. **संकुल अभ्यास** — start Sankul session (8.7).
Print stylesheet for the visit list.

## 9.4 Trainer view (`/trainer`)

Filters: district (fixed to own), module/move, batch. Content (all from `agg_module_batch`):
- Table rows = batch × move: n teachers, % completed loop, explain-back: **most often missed key point** (text), rubric distribution per criterion (stacked mini-bars as inline SVG, 0/1/2), evidence ladder distribution (1–5).
- Rows with `n < 10`: all metric cells replaced by "समूह छोटा है (n<10) — गोपनीयता हेतु छिपाया गया".
- Insight box (computed in code, not LLM): "बैच KNP-B1 में 64% शिक्षक 'बंडल खोलना' वाला बिंदु छोड़ रहे हैं — अगली ट्रेनिंग में इस पर 10 मिनट दें।" from the top missed key point per move where rate ≥ 40%.
- CSV export (same suppression).
No names, no teacher-level data, anywhere on trainer routes (test).

## 9.5 Coach review console (`/review`)

- Queue tabs: कम भरोसे वाले स्कोर (rehearsal/explain with needs_review), ARP को भेजे प्रश्न (read-only mirror), गार्ड विफलताएँ (child line fallbacks with the rejected LLM output and reason), सामग्री (moves).
- Rehearsal review item page: transcript (speaker-coloured), act tags per turn, AI scores + evidence quotes highlighted in the transcript, editable corrected scores (0/1/2 per criterion) + note → saved to `review_item.resolution` and **appended to `eval/calibration` labels** (export button `GET /review/calibration.jsonl`).
- Move editor: form view of key points, rubric, scenario, scripts, checklist; raw YAML tab with server-side schema validation; "मंज़ूरी दें" records approval `{user, at}`; status → `approved` when 2 distinct coaches approve (config `MOVE_APPROVALS_REQUIRED = 2`; demo allows `coach.demo` + `admin.demo`).
- Blind double-coding mode for calibration: `/review/calibrate` shows a random rehearsal transcript **without** AI scores; coach scores it; stored separately (`calibration_label` table: scene_id, coach_user_id, scores, created_at — add to migration).

## 9.6 Admin (`/admin`)

Cards: latency p50/p95 last 24 h & 7 d (by stage), turns count, guard pass/retry/fallback %, LLM calls by role & tokens, template sends & est. cost this week, scheduled jobs (pending/failed), content release active, demo controls (reset demo teachers, fast-forward a teacher, toggle mock providers read-only display). Simple tables, no chart library.

## 9.7 Auth

- `/login` username + password; session cookie `abhyas_session` (signed, HttpOnly, Secure in prod, SameSite=Lax, 12 h).
- Route guards by role (`auth/guards.py`): decorator/dependency `require_role("arp")`. Admin can view all pages.
- Credentials for evaluators listed in README (13). Passwords from env `DEMO_PASSWORD`; **change before submission** and put in the submission form, not in git.

## 9.8 Accessibility & language

- `lang="hi"` on html; all controls labelled; audio has text equivalent (always); no information by colour alone (children also have name labels).
- Every teacher-facing page readable at 200% zoom without horizontal scroll.

---

## FILE: spec/10_content.md

# 10 — Content: moves, personas, sources, pipeline

## 10.1 Files and locations

| Repo path | From build pack | Notes |
|---|---|---|
| `content/moves/<MOVE_ID>.yaml` | `content-seed/moves/*.yaml` | 4 seed moves, status `in_review` until coaches approve |
| `content/personas/<id>.yaml` | `content-seed/personas/*.yaml` | Ravi, Priya, Aman |
| `content/messages_hi.yaml` | `content-seed/messages_hi.yaml` | every teacher-facing string |
| `content/whatsapp_templates.yaml` | `content-seed/whatsapp_templates.yaml` | utility templates to submit to Meta |
| `content/voices.yaml` | (write from 06 §6.3 table) | |
| `content/induction_track.yaml` | `[NUM_PLACE_VALUE_BUNDLES, NUM_SUB_REGROUP_BUNDLES, NUM_ADD_CARRY_BUNDLES, LIT_MATRA_BLENDING]` | first-year order |
| `content/act_examples_hi.yaml` | agent writes ≥ 2 examples per act (05 §5.4) | reviewed by a team member |
| `content/sources/sources.yaml` | manifest (10.4) | PDFs themselves: HUMAN INPUT |
| `content/chunks/*.jsonl` | produced by ingest | committed |
| `content/audio/*.ogg` | optional pre-recorded | HUMAN INPUT |
| `eval/samples/samples.yaml` | `content-seed/eval_samples.yaml` | evaluator sample inputs |

## 10.2 Move schema (pydantic in `backend/app/content_models.py`; export JSON Schema to `content/schemas/move.json`)

```yaml
id: NUM_SUB_REGROUP_BUNDLES           # ^[A-Z]{3}_[A-Z0-9_]+$
version: 1
status: draft | in_review | approved
domain: numeracy | literacy
grade: [2]
title_hi: str                         # ≤ 60 chars
summary_hi: str                       # 1–2 sentences
tags: [subtraction, regrouping]       # for path matching with question categories
module_ref:                           # HUMAN INPUT: confirm against the actual state module
  source_id: str                      # → sources.yaml id
  section: str
  page: int | null
  verified: false                     # coach sets true after checking the page
sankul_month: October | null
key_points:                           # 4–6
  - id: kp1
    text_hi: str
    must_have: bool
    keywords_hi: [str]                # fallback scorer
    source_chunk_ids: [str]           # traceability (pipeline fills; seed may be [])
teaching_acts_effective: [ask_to_explain, concrete_representation, ...]   # ⊆ taxonomy
target_causes: [SUB_SMALLER_FROM_LARGER, ...]                              # ⊆ bug registry
rubric:
  criteria:                           # 3–5
    - id: crit_explain
      text_hi: str
      levels: {0: str, 1: str, 2: str}
      signal_acts: [ask_to_explain]   # deterministic fallback coach: present → ≥1
      negative_acts: []               # e.g. [tell_answer]: present → score 0 for this criterion
feedback_bank:                        # deterministic fallback coach, per criterion
  crit_explain:
    strength_hi: str
    change_hi: str
    exact_words_hi: str
learn_script_hi: str                  # spoken ≤ 2 min (≈ 230–260 words)
learn_summary_hi: [str]               # 4–6 short lines shown as text
scenario:
  intro_hi: str                       # board/class description read at REHEARSE_INTRO
  items:                              # Problem objects (04); first item is the opening item
    - {type: sub, a: 52, b: 17}
  children:                           # exactly 3 in this order
    - {persona_id: ravi,  misconception: SUB_SMALLER_FROM_LARGER}
    - {persona_id: priya, misconception: SUB_BORROW_NO_DECREMENT}
    - {persona_id: aman,  misconception: SUB_WRITE_ZERO_WHEN_STUCK}
  guess_lexicon: {}                   # literacy only: base consonant → [words]
model_rehearsal:                      # teacher lines + acts; child lines GENERATED by engine+voice at publish
  - {speaker: teacher, text_hi: str, acts: [ask_to_explain], addressed: ravi, problem: null}
peer_checklist: [str]                 # 4–6 yes/no items observable in 5 minutes
reflection_questions: [str, str]
approvals: []                         # [{user, at}]
```

## 10.3 Validator (`content/pipeline/validate.py`, `make content-validate`) — CI runs it

For every move file:
1. Schema valid; Hindi fields NFC; no Latin-only `_hi` fields.
2. `teaching_acts_effective ⊆ taxonomy`; `target_causes ⊆ registry`; every scenario child's misconception ∈ target_causes; persona ids exist.
3. Every scenario item is valid for the domain (04 §4.4 step 2) **and** every child's bug produces a **wrong** answer on the first item (so the opening scene shows 3 distinct visible mistakes) — warn if two children give the same wrong answer.
4. **Model rehearsal check:** run the rule engine over `model_rehearsal` teacher lines (using their declared acts) → all 3 children must end CORRECT within the script; produce the child lines via engine + template_line (no LLM in validation) and write `model_rehearsal_rendered` to the published payload.
5. Rubric: 3–5 criteria, levels 0/1/2 present, `signal_acts ⊆ teaching_acts_effective ∪ {praise_effort, involve_peer}`, `negative_acts ⊆ taxonomy`; feedback_bank has every criterion.
6. Learn script word count 150–300; key points 4–6 with ≥ 2 `must_have`.
7. `module_ref.source_id` exists in `sources.yaml` (warning only if `verified: false`).

## 10.4 Sources & ingestion (`content/sources/sources.yaml`, `retrieval/ingest.py`)

```yaml
- id: nipun_guidelines_2021
  title: "NIPUN Bharat — Guidelines for Implementation (MoE, 2021)"
  short_hi: "निपुण भारत दिशानिर्देश"
  file: nipun_bharat_guidelines.pdf        # HUMAN INPUT: place file
  lang: hi | en
  licence_note: "Government of India publication — used for non-commercial educational purposes"
- id: up_ganit_sandarshika_c2              # UP Basic Shiksha teacher guide (Shikshak Sandarshika), Maths, Class 2
- id: up_bhasha_sandarshika_c1             # Hindi language teacher guide, Class 1
- id: ncert_vidya_pravesh
- id: ncert_fln_learning_outcomes
```
**HUMAN INPUT:** download the actual PDFs (state SCERT/Basic Shiksha portal, MoE, NCERT) and the hackathon's provided resource list; fill `file`, confirm titles. Commit PDFs only if the licence allows; otherwise gitignore `content/sources/*.pdf` and commit only `content/chunks/`.

Ingest steps:
1. Extract text per page with `pypdf`/`pdfplumber`.
2. **Garble detection:** if Devanagari char ratio < 0.3 on a page that should be Hindi (legacy Kruti Dev/Chanakya fonts produce Latin gibberish) → render page to PNG (`pdftoppm -r 150`) → `page_ocr` Claude role (05 §5.9) → text.
3. Clean: NFC, de-hyphenate, drop headers/footers repeated on > 50% of pages.
4. Chunk: 250–400 words, split on headings/paragraphs, keep `section` (nearest heading) and `page`. id = `<source_id>:p<page>:<n>`.
5. Tokenise for BM25: NFC, strip punctuation, lowercase Latin, split whitespace, drop Hindi stopwords (`retrieval/stopwords_hi.txt`, agent writes ~150 common words), store `tokens`.
6. Optional embeddings (Voyage) → `embedding`.
7. Write `content/chunks/<source_id>.jsonl`; `make db-seed` loads them.

Retrieval (`retrieval/search.py`): BM25 top 20 (+ dense top 20 if enabled) → RRF (k = 60) → top `RETRIEVAL_TOP_K` (5) with normalised score; `RETRIEVAL_MIN_SCORE` threshold on BM25 normalised score (calibrate on 20 sample questions in T40; start 0.25). Golden retrieval test: 10 sample questions → expected source ids in top 5 (`tests/integration/test_retrieval.py`, uses committed chunks; skip if none).

Until real sources are ingested, seed `content/chunks/seed_from_moves.jsonl` from the 4 seed moves' learn scripts and key points (source_short_hi "अभ्यास मूव कार्ड", clearly not presented as an official guide) so ASK works end-to-end; replace when PDFs arrive.

## 10.5 Generation pipeline (`content/pipeline/`, for moves 5+; seed moves are hand-written)

`make content-generate TOPIC="…" SOURCE=<id>` → `generate.py` retrieves chunks for the topic → `move_generator` → YAML draft (status draft) → `validate.py` → `review.py` runs `move_reviewer` and writes `<id>.review.md` → coaches edit/approve in `/review/moves` → `make content-publish` creates a `content_release`, renders model rehearsal child lines, pre-warms TTS cache, marks release active.

Only `approved` moves are served to real (non-demo) teachers. Demo teachers may get `in_review` moves (flag `SERVE_IN_REVIEW_TO_DEMO=true`). The UI marks unapproved moves with "समीक्षा में" for transparency.

## 10.6 Personas (`content/personas/*.yaml`)

```yaml
id: ravi
name_hi: रवि
age: 7
temperament: confident
voice_id: child_ravi
speech_style_hi: "जल्दी और पूरे भरोसे से बोलता है, छोटे वाक्य, 'दीदी' कहकर बात करता है"
off_topic_lines_hi: [...]           # ≥ 4, no numbers
```

---

## FILE: spec/11_eval_and_testing.md

# 11 — Testing and evaluation

## 11.1 Automated tests (`make test`, CI on every push)

| Suite | Location | Must cover |
|---|---|---|
| Rule engine | `tests/unit/test_rule_engine.py`, `test_bugs.py`, `test_akshar.py` | 04 §4.5 (all 14 items) |
| Guards | `tests/unit/test_guards.py`, `test_hindi_numbers.py` | every guard: ≥ 3 pass + ≥ 3 fail fixtures; numbers 0–100 in words |
| LLM roles | `tests/unit/test_roles_*.py` | validate → guard → retry → fallback path, using MockLLM returning bad then good / bad then bad |
| State machine | `tests/unit/test_state_machine.py` | 08 §8.8 |
| Channels | `tests/integration/test_whatsapp_webhook.py` | verify GET challenge; bad signature 401; good signature 200 + background processing; dedupe; text/audio/button parsing (fixtures of real Meta payload shapes); outbound payload shapes; 24-h window/template choice |
| Web API | `tests/integration/test_web_chat.py` | text/audio/button send, idempotent retry with same client_msg_id, polling returns replies, auth required |
| Access control | `tests/integration/test_access.py` | 03 §3.3 |
| Reports | `tests/integration/test_reports.py` | n<10 suppression (exactly 9 → suppressed, 10 → shown); ARP digest excludes non-consenting scores; trainer pages contain no teacher names (grep rendered HTML for demo names) |
| Privacy | `tests/integration/test_privacy.py` | no inbound audio bytes reach DB (spy on session.add for bytes in non-tts tables); delete-my-data purges; consent withdrawal hides from ARP |
| Speech | `tests/unit/test_audio.py` | ffmpeg conversions on fixture OGG/WebM/MP4; split_for_stt on a 60 s fixture → chunks ≤ 25 s |
| Retrieval | `tests/integration/test_retrieval.py` | 10.4 |
| E2E | `tests/e2e/test_full_week.py` | NEW → DONE on web channel with mocks; same via WhatsApp webhook payloads with mocked Graph API (respx) |
| Content | `make content-validate` | 10.3 |

Coverage gate: `rule_engine/` 100% lines, `llm/guards.py` ≥ 95%, overall ≥ 80%.
Test DB: docker Postgres in CI (`services: postgres: image pgvector/pgvector:pg16`); each test in a transaction rolled back.

## 11.2 Live tests (`make test-live`, not in CI)

Skipped unless keys present. Real Claude on golden inputs (guard pass ≥ 90%), Sarvam STT on the 5 sample audios (word overlap with reference text ≥ 70%), Sarvam TTS returns playable audio, WhatsApp send to the team's test recipient.

## 11.3 Latency (`eval/latency/benchmark_latency.py` → `eval/latency/REPORT.md`)

- Drives the **hosted** deploy via the web API with the 5 sample audio files, 20 rehearsal turns each, concurrency 1 and 3.
- Reports p50/p95/max end-to-end and per stage (from `turn.stage_ms`), guard fallback rate, and a pass/fail vs 20 s.
- Also report on-device data cost: bytes uploaded/downloaded per full weekly loop (measure via API responses) — target < 2 MB normal, < 300 KB lite mode.

## 11.4 Coach calibration (`eval/calibration/`)

- `export_scenes.py`: exports N rehearsal transcripts (pilot + team role-plays) as anonymised JSONL.
- Coaches label blind in `/review/calibrate` (9.5); `make eval-kappa` computes per criterion: **quadratic-weighted Cohen's kappa** (sklearn `cohen_kappa_score(weights="quadratic")`) AI vs each coach and coach vs coach, with bootstrap 95% CI, plus exact-agreement %. Same for explain-back point statuses (unweighted kappa over covered/partial/missing).
- Report `eval/calibration/REPORT.md`: n, kappas, confusion matrices, examples of disagreements, what we changed in the prompt as a result (versioned prompt diff). **Report honestly even if n is small or kappa < 0.7.**
- Target for 1 Nov: ≥ 20 double-coded rehearsals (team-generated role-plays + pilot). Target for finale: ≥ 50.

## 11.5 Realism (`eval/realism/`)

- In-product rating after each scene (1–5 list). `make eval-realism` → mean, distribution, n, by persona and by move; free-text comments from user testing.
- Blind realism check (optional, strong evidence): 10 short exchanges, 5 engine-driven and 5 from a plain "pretend to be a child" LLM prompt; teachers guess which feels like their classroom children and rate realism. Script `realism/blind_pairs.py` generates both sets; the plain-LLM baseline uses `claude-haiku-5-5` with a naive prompt. This directly evidences the core innovation claim.

## 11.6 User testing protocol (`eval/user_testing/`) — scored under "proof of testing and refinement"

Owner: field lead (Divyansh). Two rounds.

**Recruit:** 5–10 government primary teachers (Classes 1–3, Hindi-medium) via personal networks / an NGO / ARP; at least 2 in-person observations. Adults, informed consent (`consent_form_hi.md` — agent writes; covers: purpose, what is recorded (transcripts only, no audio kept), voluntary, withdraw anytime, anonymised use in hackathon submission). **No children involved.**

**Session (30–40 min):**
1. Onboard on own phone (WhatsApp or web link).
2. Complete one weekly loop for `NUM_SUB_REGROUP_BUNDLES` (or move of her class).
3. Think-aloud during rehearsal; observer notes confusions.
4. Exit questions (`exit_questions_hi.md`): realism 1–5 ("बच्चे असली कक्षा जैसे लगे?"), usefulness 1–5, would use weekly (yes/maybe/no), time taken, hardest step, one thing to change; 5-item SUS-lite in Hindi.
5. Log into `eval/user_testing/sessions.csv` (anonymised id, date, device, network, channel, completion, timings, ratings, top quotes) — **no names/phones in git**.

**Round 1** (by 24 Oct) → `round1_findings.md`: top 5 issues, severity, decision (fix / won't fix / roadmap).
**Fixes** (25–28 Oct) → each linked to a commit.
**Round 2** (by 29 Oct) → `round2_findings.md`, before/after table (completion rate, avg time, realism, confusions).
**Deck page "User inputs and testing"** is generated from these files (13).

## 11.7 Guardrail evaluation (for the "AI use & technical strength" slide)

`eval/guards/REPORT.md` (`make eval-guards`): over all logged turns — child_voice first-pass guard pass %, retry pass %, fallback %, top rejection reasons with examples (e.g. "LLM said 35 while Ravi is in misconception — blocked"); coach evidence-quote failures; guide answer escalation rate. Include 3 concrete blocked examples in the deck.

---

## FILE: spec/12_deploy_ops.md

# 12 — Deployment, environment, CI, freeze

## 12.1 Environments

| Env | Where | Providers |
|---|---|---|
| local | `make dev` + docker compose Postgres | mocks unless keys in `.env` |
| test/CI | GitHub Actions + Postgres service | mocks only |
| prod (evaluation) | Render web service (Docker, **Starter** plan, Singapore region — closest to India) + Supabase (Mumbai `ap-south-1`) | real: Claude, Sarvam, WhatsApp |

## 12.2 Docker (`Dockerfile` at repo root)

- `python:3.11-slim`; `apt-get install -y ffmpeg poppler-utils` (pdftoppm for OCR ingest); non-root user; `pip install .`; `CMD alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --workers 1`.
- **Single worker/instance** (in-process scheduler and per-teacher locks assume one process). Document this limit + the scale-out plan (Redis-backed queue, separate worker) in README roadmap.
- `docker-compose.yml`: `db` (pgvector/pgvector:pg16, port 5432), `app` (build ., env_file .env, depends_on db).

## 12.3 Render (`render.yaml` blueprint)

```yaml
services:
  - type: web
    name: abhyas
    runtime: docker
    plan: starter
    region: singapore
    healthCheckPath: /healthz
    autoDeploy: false          # deploy deliberately; freeze = stop deploying
    envVars:                   # values set in the Render dashboard (HUMAN INPUT), never in git
      - key: DATABASE_URL
        sync: false
      # … every key from .env.example with sync: false
```
Custom domain optional. HTTPS automatic (required by Meta webhooks and by `getUserMedia` mic access).

## 12.4 Supabase

- New project (Mumbai). Enable `vector` extension. Use the **session pooler** connection string for `DATABASE_URL` (`postgresql+asyncpg://…`), direct connection for Alembic if pooler blocks DDL.
- Enable RLS on all tables with no policies (app uses server-side connection; anon key unused). Daily backups (default).

## 12.5 Environment variables (`.env.example` — commit this, with empty secrets)

See `.env.example` at the build-pack root (copy to repo root, replacing the scaffold's). Every variable is documented with a comment; the app fails fast at startup in `ENVIRONMENT=production` if a required secret is missing, and logs which providers are mocked in dev.

## 12.6 CI (`.github/workflows/ci.yml`)

Jobs: `lint` (ruff, mypy), `test` (pytest with Postgres service, coverage gate), `content` (`make content-validate`), `secrets` (gitleaks action). Required to pass before merge to `main`. Branch flow: feature branches `t<id>-<slug>` → PR → main. Agent may push directly to `main` only if no human reviewer is configured; otherwise open PRs.

## 12.7 Observability

- Structured JSON logs (request id, teacher id hash prefix, state, stage timings); never log transcripts at INFO in prod (DEBUG only), never log phone numbers or tokens.
- `/admin` metrics (09 §9.6). Optional Sentry (`SENTRY_DSN`) if provided.

## 12.8 Cost guard

- `LLM_DAILY_TOKEN_BUDGET` (config): if exceeded, roles switch to deterministic fallbacks and admin page shows a red banner. Protects the hackathon credits during the evaluation window.
- Rate limit per teacher: 60 inbound messages/hour.

## 12.9 Freeze procedure (`make freeze` runs `scripts/freeze_check.py`)

Checks and prints a pass/fail list:
1. `main` CI green; working tree clean.
2. `.env` not tracked; gitleaks clean; no files > 5 MB except allowed audio samples.
3. README has: setup, run locally, `.env.example` reference, AI services list, credentials table placeholder, low-network table, known limitations.
4. LICENSE present (MIT).
5. `/healthz` on prod returns the same `GIT_SHA` as HEAD.
6. Every demo login works on prod (scripted login + GET role home page → 200).
7. Sample inputs present in `eval/samples/` and playable.
8. Latency report updated within 48 h.
Then: create annotated tag `submission-2026-11-01` on HEAD, push tag, set Render to deploy that commit, **disable auto-deploy**, and record the tag + SHA in `PROGRESS.md`. After this point **no commits to `main`** until results; continue work for the finale on branch `finale`.

Evaluator access: grant read access to the Tech4Dev evaluator GitHub IDs (HUMAN INPUT: they'll be shared by organisers) — repo is public already, but add them as collaborators if asked.

---

## FILE: spec/13_submission.md

# 13 — Submission deliverables (Build stage, due 1 Nov 2026 23:59 IST)

Required by the organisers: (1) testable hosted link + any software needed, (2) source repo, (3) public YouTube demo video, judges watch only the first 3 minutes, (4) short PowerPoint deck. Tech-flow guidance adds: test credentials for every role, 3–5 sample inputs, what works offline/low network, 2–3 min fallback video, README with setup/run/.env.example, list of every external AI service and where keys are needed, no secrets, no real user data, no commits after deadline.

Build-stage scoring: Efficacy & user-centricity 35 · Effective AI use & technical strength 30 · Innovation 25 · Future roadmap 10.

## 13.1 README.md (agent writes; structure fixed)

1. **Abhyas — अभ्यास** one-line pitch + 30-second GIF of a rehearsal (record in T52).
2. **Try it** — hosted URL; **credentials table**:

| Role | Username | Password | What to try |
|---|---|---|---|
| Teacher (new) | teacher.demo1 | (in submission form) | onboarding → first weekly loop |
| Teacher (mid-week) | teacher.demo2 | … | jump straight into rehearsal with 3 children |
| Teacher (experienced) | teacher.demo3 | … | progress page, evidence ladder, ask a question |
| ARP | arp.demo | … | weekly digest, visit list, answer escalated question |
| Trainer (DIET) | trainer.demo | … | module × batch view, n<10 suppression (batch KNP-B3) |
| FLN coach | coach.demo | … | review queue, blind calibration, move approval |
| Admin | admin.demo | … | latency, guardrail stats, fast-forward timers, reset demo |
WhatsApp: number + join instructions (Meta test numbers only accept pre-registered recipients — evaluators who want WhatsApp send their number via the form; otherwise watch the video section).
3. **Sample inputs** (3–5) with what to expect — from `eval/samples/samples.yaml`; buttons for these exist in the chat in demo mode.
4. **How it works** — the layered diagram (02 §2.1) as an image + 6 bullets; the rule-engine principle in 3 sentences with the Ravi example.
5. **AI services used** table: Claude (`claude-haiku-5-5`: intent, act tagging, child voice; `claude-sonnet-5-5`: coach, fidelity, guide answers, content generation) — key `ANTHROPIC_API_KEY`; Sarvam AI STT/TTS — `SARVAM_API_KEY`; Meta WhatsApp Cloud API — `WHATSAPP_*`; optional Voyage embeddings — `VOYAGE_API_KEY`. State which run in mock mode without keys.
6. **Guardrails** — list with links to `llm/guards.py` and `eval/guards/REPORT.md`.
7. **Low connectivity & low-cost devices** table:

| Part | Needs network? | Degrades to |
|---|---|---|
| Learn summary, peer checklist, last 50 messages | No (cached PWA) | — |
| Sending a voice note / text | Queued offline, auto-sent when back | outbox with retry |
| Rehearsal replies | Yes (server AI) | text-first replies; lite mode = no audio download |
| Audio playback | On tap in lite mode | text always shown |
| WhatsApp channel | WhatsApp's own offline queue | text fallback on audio failure |
Data per weekly loop: measured X MB normal / Y KB lite (from latency report).
8. **Run locally** — prerequisites (Docker, Python 3.11, ffmpeg), `cp .env.example .env`, `make setup db-up db-migrate db-seed dev`, open `http://localhost:8000`; all providers mocked by default.
9. **Repository map**, **tests** (`make test`), **evaluation reports** links.
10. **Privacy** — DPDP-aligned summary (no audio stored, consent gates, n≥10, children never scored).
11. **Limitations (honest)** and **Roadmap** (13.4).
12. **Licence** MIT · Team Asymptotes · hackathon attribution.

## 13.2 Demo video (YouTube, public/unlisted-public, ≤ 3:00) — `docs/video_script.md`

| Time | Visual | Voice-over (English with Hindi on screen, or Hindi with English subtitles — team choice) |
|---|---|---|
| 0:00–0:15 | Teacher in a real classroom / B-roll; text "Trainings end. Practice doesn't happen." | Problem: FLN moves are taught in a training hall, never practised; trainers see attendance, not adoption. |
| 0:15–0:30 | Phone: WhatsApp chat opens, learn voice note | Abhyas: 15 minutes a week, voice, Hindi, on WhatsApp. |
| 0:30–1:30 | **Rehearsal** — board shows 43 − 27; Ravi says 24, Priya 26, Aman 20; teacher says "रवि, 43 में से 27 कैसे घटाया?"; Ravi: "3 में से 7 नहीं घटता, तो 7 में से 3 घटाया… 24!"; teacher uses bundles; Priya shy; teacher tells answer to Aman → Aman parrots then relapses on next problem | Children's mistakes are computed by a rule engine from research on children's errors; Claude only voices them; a guard blocks any line the engine didn't produce. Telling the answer doesn't work — just like a real class. |
| 1:30–1:55 | Feedback screen: strength / change / exact words with highlighted quote; retry improves | Evidence-cited feedback; retry. |
| 1:55–2:15 | Explain-back score + ask a question with cited guide + ARP escalation | |
| 2:15–2:35 | ARP digest (consenting only), trainer view with n<10 suppressed | Adoption, not attendance; privacy by design. |
| 2:35–2:50 | User testing: photos (with consent, no children), 2 quotes, before/after numbers | Tested with N teachers, what we changed. |
| 2:50–3:00 | Lite mode on a cheap phone; logo; link | Works on low-cost phones and patchy data. |

Also record a separate 2–3 min **fallback walkthrough of the hosted web app** (screen capture) linked in README.

## 13.3 Short deck (PowerPoint, ~8–10 slides) — `docs/deck_outline.md`

Make it with the team's deck tool; the agent writes the outline + speaker notes + exports diagrams/screenshots into `docs/deck_assets/`.

1. Title, team, challenge 3 (teacher support & training).
2. **AI/LLM usage in layers** — the 02 §2.1 diagram; table of the 6 runtime Claude roles: where called, what it does, model, guard.
3. **Core innovation**: deterministic misconception engine + LLM voice; Ravi example; transition table snippet; blind realism result (11.5) if done.
4. **Guardrails**: schema validation, number/answer guard, quote-exists guard, sources ⊆ retrieved, confidence → human review queue, deterministic fallbacks; 3 real blocked examples + rates from `eval/guards/REPORT.md`.
5. **Evaluation**: kappa vs coaches (n, value, CI), latency p50/p95, realism mean — honest.
6. **Real scenarios**: low-connectivity table, data per week, low-cost Android, WhatsApp-first, voice in Hindi/Hinglish, 15 min/week; what needs network, what degrades.
7–8. **User inputs & testing**: who, how many, 2 rounds, top findings, what changed (before/after), quotes.
9. **Future roadmap**: IVR for feature phones; Bhashini + more languages; integration with DIKSHA/Prerna and the monthly Shikshak Sankul cycle; DIET/SCERT dashboards; class-audio coaching (opt-in, school-owned); child-outcome link (evidence level 5) via assessment partners; content pipeline scaled with SCERT coaches; cost per teacher per year.
10. Privacy & safety (DPDP), ask.

## 13.4 Roadmap content (README + deck)

Near term (pilot, Dec–Feb): 30–100 teachers with one DIET; 16 moves; kappa ≥ 0.7 on 100 double-coded rehearsals; Sankul mode in monthly meetings. Mid term: IVR channel, Bhashini/State speech stack, 3 more languages, integration with state teacher apps, child-outcome evidence. Systems: ARP digest feeds existing mentoring visit apps; trainer view aligned to SCERT module structure.

## 13.5 Submission checklist (`docs/submission_checklist.md` — tick in PROGRESS.md)

- [ ] Hosted URL live, freeze tag deployed, `/healthz` SHA matches tag
- [ ] All 7 demo logins work; passwords rotated and entered in the form only
- [ ] 3–5 sample inputs listed + playable
- [ ] README complete (13.1)
- [ ] `.env.example`, LICENSE, no secrets (gitleaks), no real user data in repo
- [ ] YouTube video public, ≤ 3:00, link in README and form
- [ ] Fallback walkthrough video
- [ ] Deck (PPTX) uploaded
- [ ] Evaluator GitHub IDs added (if provided)
- [ ] Submitted **31 Oct** (a day early), confirmation screenshot saved

---

## FILE: spec/14_tasks.md

# 14 — Ordered task list

Priority: **P0** = must ship for 1 Nov; **P1** = should ship; **P2** = only if ahead of schedule. If behind schedule on 25 Oct, drop remaining P2s, then simplify P1s (as noted per task) — never drop P0s, tests or the freeze.

"Accept" = acceptance criteria; the task is done only when all are true and `make test` is green. Target dates are finish-by dates (IST).

## Phase A — Foundation

**T01 Repo restructure** · P0 · 12 Oct
Refactor scaffold to 02 §2.4 layout. Delete duplicate spec files and .docx (pack replaces them; copy pack into `spec/`, `AGENTS.md` and `CLAUDE.md` at root). Add MIT `LICENSE`, `Makefile` (AGENTS.md commands; stubs ok for later targets), update `pyproject.toml` deps (add: apscheduler, rank-bm25, rapidfuzz, regex, passlib[bcrypt], itsdangerous, cryptography, python-multipart, pdfplumber, pypdf, respx, hypothesis, freezegun, playwright (dev), scikit-learn (dev/eval); remove arq, redis), `.pre-commit-config.yaml` (ruff, mypy, gitleaks), `.gitignore` (.env, content/sources/*.pdf, *.wav, *.ogg except eval/samples and content/audio), CI workflow (12 §12.6), `PROGRESS.md`.
Accept: CI green on an empty test; `make setup` works; tree matches layout.

**T02 Config** · P0 · 12 Oct — `config.py` with every env var from `.env.example` and every threshold named in this pack (grep the pack for UPPER_CASE names). Provider selection logs mocks in dev; fail-fast on missing secrets in production. Accept: unit test that production mode without `ANTHROPIC_API_KEY` raises.

**T03 Database** · P0 · 13 Oct — SQLAlchemy models + Alembic migration for **all** tables in 03 (incl. invite_code, calibration_label); async session; `db/seed.py` skeleton; docker compose db. Accept: `make db-up db-migrate` on empty DB; downgrade/upgrade round-trip test.

**T04 Content models & seed content** · P0 · 13 Oct — pydantic Move/Persona/Problem models (10 §10.2, 04 types), YAML loader, JSON Schema export, copy `content-seed/*` to `content/`, validator checks 1, 2, 5, 6, 7 (3 and 4 after T07). Accept: `make content-validate` passes on 4 seed moves.

## Phase B — Core IP (no LLM)

**T05 Hindi utilities** · P0 · 13 Oct — `llm/hindi_numbers.py` (extract_numbers, to_words 0–199), `guards.norm`, `rule_engine/bugs/akshar.py`. Accept: exhaustive 0–100 word tests; akshar cases in 04.

**T06 Bug rules** · P0 · 14 Oct — all 12 rules + correct functions + step templates + registry. Accept: every cell of the 04 §4.2 tables as parametrised tests.

**T07 Rule engine** · P0 · 15 Oct — types, transitions, `RuleEngine.step`, placement mode, serialisation; finish validator checks 3–4 (model rehearsal must end all CORRECT; fix seed YAML acts if needed and note in PROGRESS). Accept: all 14 tests in 04 §4.5; 100% line coverage of `rule_engine/`.

## Phase C — LLM roles

**T08 LLM client + MockLLM** · P0 · 14 Oct — 05 §5.1; `llm_call` logging; prompt loader with versions; daily token budget guard (12 §12.8). Accept: unit tests for retry/timeout/fallback using a fake transport.

**T09 Guards** · P0 · 15 Oct — all guards in 05. Accept: ≥ 3 pass + ≥ 3 fail fixtures per guard.

**T10 act_tagger** · P0 · 16 Oct — prompt v1 + `content/act_examples_hi.yaml` (≥ 28 examples) + keyword fallback + 8 golden fixtures. Accept: guard tests; fallback tagger tests on 15 sentences; `make test-live` ≥ 85% exact act-set match on 20 labelled teacher turns (labels written by the team in `tests/golden/act_tagger/labelled.jsonl`).

**T11 child_voice** · P0 · 16 Oct — prompt, guard wiring, template fallback. Accept: for every ResponseKind a golden good + bad fixture; live guard pass ≥ 90% on 30 engine outputs.

**T12 coach** · P0 · 17 Oct — prompt, guards, deterministic fallback from signal_acts/feedback_bank, review_item on low confidence. Accept: golden tests; fallback produces valid feedback for every seed move.

**T13 fidelity_checker** · P0 · 17 Oct — prompt, guards, reply composition, keyword fallback.

**T14 intent_router, question_classifier, guide_answerer** · P1 · 20 Oct — (simplify if late: skip classifier's clarifying question.)

## Phase D — Speech

**T15 Audio utils** · P0 · 14 Oct — 06 §6.1 with fixtures (OGG/Opus, WebM/Opus, MP4/AAC, 60 s WAV). Accept: conversions + split tests; no files left on disk (assert tmp dir empty).

**T16 STT** · P0 · 16 Oct — sarvam + mock (+ bhashini/google stubs). Accept: mock tests; live test on 5 samples.

**T17 TTS + voices** · P0 · 17 Oct — sarvam + mock, number-to-words, pitch shift, cache, pre-warm; voice audition script `scripts/audition_voices.py` writing candidates to `eval/voices/` for the team to choose. Accept: cache hit test; OGG output validated by ffprobe (codec opus, mono).

## Phase E — Conversation

**T18 Core service skeleton** · P0 · 16 Oct — types, `ConversationService`, message catalog loader (missing key → startup error), per-teacher locks.

**T19 SceneRunner** · P0 · 18 Oct — tagger → engine → voice → guard → TTS; scene persistence; stop words; stage timings. Accept: integration test runs the Ravi example end-to-end with MockLLM (child lines guarded) and stores turns.

**T20 Onboarding** · P0 · 19 Oct — 08 §8.1 incl. placement scene. Accept: table-driven tests.

**T21 Weekly loop + evidence** · P0 · 20 Oct — 08 §8.2, evidence ladder. Accept: 08 §8.8 tests incl. full happy path.

**T22 Intents, ASK, retrieval** · P1 · 21 Oct — 08 §8.3–8.4; BM25 search; `seed_from_moves.jsonl`; escalation. (Simplify if late: BM25 only, no dense.)

**T23 Move path** · P1 · 21 Oct — 08 §8.5. (Simplify: fixed induction order for everyone.)

**T24 Scheduler & jobs** · P1 · 22 Oct — 08 §8.6 + fast-forward + fake clock tests. (Simplify: only followup_question, arp_digest snapshot, aggregates.)

## Phase F — Channels & web

**T25 Auth & demo users** · P0 · 17 Oct — 09 §9.7, seed users, guards, CSRF, login rate limit.

**T26 Web channel API** · P0 · 18 Oct — 07 §7.3. Accept: idempotency + polling tests.

**T27 Teacher chat PWA** · P0 · 20 Oct — 09 §9.2 complete (recorder, outbox/IndexedDB, SW, offline page, lite mode, demo sample chips, child strip). Accept: Playwright test (Chromium, mobile viewport) sends text + a fake-mic audio (`--use-fake-device-for-media-stream --use-file-for-fake-audio-capture=<sample.wav>`) and sees a reply; offline test: go offline, send, go online → delivered once; Lighthouse ≥ 90 recorded.

**T28 WhatsApp channel** · P0 code 21 Oct / P1 live · 07 §7.2 + `docs/whatsapp_setup.md`. Accept: webhook tests with real payload shapes; respx-mocked Graph calls; window/template tests. Live: round trip on the team test number (HUMAN INPUT creds) — record in PROGRESS.

**T29 Progress, consent, delete** · P1 · 22 Oct.

## Phase G — Deploy early

**T30 First hosted deploy** · P0 · **18 Oct** — Dockerfile, compose, render.yaml, Supabase, real keys if available (else mocks), `/healthz` with GIT_SHA. Team and testers use this URL from now on. Accept: hosted login + a mock rehearsal works on a phone over mobile data.

## Phase H — Reports & consoles

**T31 Demo data** · P1 · 22 Oct — 03 §3.5 synthetic cohort, demo banner.
**T32 ARP digest** · P1 · 24 Oct — 09 §9.3 (simplify: sections 1, 2, 4).
**T33 Trainer view + aggregates** · P1 · 24 Oct — 09 §9.4 with suppression tests (this test is P0 even if the page is simplified).
**T34 Coach review console** · P1 · 25 Oct — 09 §9.5 (simplify: rehearsal review + blind calibration; move editor = raw YAML + approve).
**T35 Admin** · P1 · 25 Oct — 09 §9.6.
**T36 Sankul mode** · P2 · 28 Oct — 08 §8.7 (minimal version acceptable).

## Phase I — Content, evaluation, testing

**T37 User-testing kit** · P0 · **14 Oct** — `eval/user_testing/consent_form_hi.md`, `exit_questions_hi.md`, `sessions.csv` header, `observer_guide.md`, findings templates (11 §11.6). Hand to field lead immediately.
**T38 Golden fixtures** · P0 · 17 Oct — ≥ 5 per runtime role (05 §5.11).
**T39 Evaluator samples** · P0 · 22 Oct — `make samples`: render `eval/samples/samples.yaml` lines to audio with a non-child adult voice via TTS (or team recordings if provided in `eval/samples/recorded/`), expose as demo chips.
**T40 Source ingestion** · P1 · 23 Oct (when PDFs arrive) — 10 §10.4. Retrieval golden test.
**T41 Latency benchmark** · P0 · 24 Oct, re-run 30 Oct — 11 §11.3 on hosted deploy; optimise until p95 < 20 s (document what was changed).
**T42 Kappa harness** · P1 · 27 Oct — 11 §11.4; report with whatever n exists on 30 Oct.
**T43 Guard report** · P1 · 29 Oct — 11 §11.7.
**T44 Realism report + blind pairs** · P2 · 29 Oct — 11 §11.5 (rating summary part is P1).
**T45 Content pipeline (generate/review/publish)** · P2 · 29 Oct — 10 §10.5 (publish step alone is P1: release + TTS pre-warm).

## Phase J — Hardening & submission

**T46 Round-1 fixes** · P0 · 28 Oct — implement fixes from `round1_findings.md`; each fix commit references the finding id.
**T47 Low-network verification** · P0 · 28 Oct — Playwright with network throttling (Slow 3G profile) + offline toggling; measured data per loop → README table.
**T48 Security pass** · P0 · 29 Oct — headers (CSP self-only, HSTS, X-Content-Type-Options), CSRF, rate limits, auth on audio endpoint, webhook signature, secrets scan, dependency audit (`pip-audit`).
**T49 Docs** · P0 · 30 Oct — README (13 §13.1), `docs/video_script.md`, `docs/deck_outline.md` (+ diagram PNG/SVG exports in `docs/deck_assets/`), `docs/demo_runbook.md` (exact click path for the video and live demo, reset steps), `docs/whatsapp_setup.md`, `docs/submission_checklist.md`.
**T50 Hosted smoke tests** · P0 · 30 Oct — Playwright script against prod: every role logs in and loads its home; one rehearsal turn completes; trainer page shows suppression.
**T51 GIF & screenshots** · P1 · 30 Oct — README GIF, deck screenshots (mobile frame).
**T52 Freeze** · P0 · **31 Oct 18:00** — 12 §12.9. Then submit (humans).

## Daily routine for the agent

Start of day: pull, read `PROGRESS.md`, run `make test`. End of day: update PROGRESS (done, next, blocked-on-humans), push. Every second day from 18 Oct: redeploy to Render and run T50 smoke script.

---

## FILE: spec/15_human_inputs.md

# 15 — Human inputs (the agent must not invent these)

For each item: what is needed, who, by when, and what the agent does meanwhile. The agent lists open items under `PROGRESS.md › Blocked on humans` and keeps building against the fallback.

| # | Input | Owner (suggested) | Needed by | Agent fallback meanwhile |
|---|---|---|---|---|
| H1 | **Anthropic API key** from the hackathon's Claude credits (USD 500) | Shashwat | 14 Oct | MockLLM; live tests skipped |
| H2 | **Sarvam AI API key** (or chosen STT/TTS provider + key) | Vedant | 15 Oct | Mock STT/TTS; text box in web chat |
| H3 | **Choice of 3 child voices + narrator/coach/model-teacher voices** (listen to `eval/voices/` audition files) | Vedant | 18 Oct | defaults in 06 §6.3 |
| H4 | **Meta WhatsApp**: developer app, test number, phone number id, permanent token, app secret, verify token, 5 registered recipient numbers | Shashwat | 19 Oct | WhatsApp channel tested with mocked Graph API only |
| H5 | **WhatsApp template approval** — submit templates from `content/whatsapp_templates.yaml` (Utility, Hindi) | Shashwat | submit by 20 Oct | templates marked `approved: false`; outside-window sends skipped & logged |
| H6 | **Render account + Supabase project** (billing for Render Starter) | Shashwat | 17 Oct | local docker only |
| H7 | **Official source PDFs**: NIPUN Bharat guidelines; UP Shikshak Sandarshika (Ganit Class 2, Bhasha Class 1); NCERT Vidya Pravesh / FLN materials; hackathon resource list | Divyansh | 20 Oct | `seed_from_moves.jsonl` chunks; `module_ref.verified: false` |
| H8 | **FLN coach / education mentor review** of the 4 seed moves (key points, rubric, scenario realism, bug list "common in UP classrooms?") — book the hackathon **education mentor** session for this | Divyansh + team | 22 Oct | moves stay `in_review`; demo serves them with "समीक्षा में" label |
| H9 | **2 coaches (or 1 coach + 1 trained team member) for blind double-coding** ≥ 20 rehearsals | Divyansh | 29 Oct | kappa report states n and limitation |
| H10 | **5–10 teachers for user testing**, two rounds (by 24 Oct, by 29 Oct), with signed/recorded consent | Divyansh | 24 / 29 Oct | — (cannot be faked; report what happened) |
| H11 | Optional **pre-recorded learn scripts** in a real teacher's voice (`content/audio/learn_<move>.ogg`) | any | 25 Oct | TTS narrator |
| H12 | **Evaluator GitHub IDs** (from organisers) | Shashwat | 31 Oct | repo is public |
| H13 | **Demo passwords** for the submission form (rotate `DEMO_PASSWORD` on Render) | Shashwat | 31 Oct | dev default (never used in prod) |
| H14 | **Demo video** recording + YouTube upload; **deck** (PPTX) from `docs/deck_outline.md` | whole team | 31 Oct | agent supplies script, outline, screenshots, diagrams |
| H15 | **Sample voice notes** recorded by a Hindi-speaking teammate reading `eval/samples/samples.yaml` lines (more realistic than TTS for STT testing) | any | 22 Oct | TTS-rendered samples |
| H16 | Optional Voyage AI key (dense retrieval) | — | — | BM25 only |
| H17 | Decision: open-source licence MIT (default) — confirms the +USD 250 credits open-source bonus | team | 12 Oct | MIT |

Never commit: real phone numbers, teacher names, transcripts from real teachers, API keys, the `.env` file, signed consent forms.

---

## FILE: .env.example

```
# ── Abhyas environment (copy to .env; never commit .env) ─────────────────
# Empty provider keys ⇒ that provider runs in MOCK mode (dev only). Production fails fast if required keys are empty.

ENVIRONMENT=development            # development | test | production
PORT=8000
LOG_LEVEL=INFO
PUBLIC_BASE_URL=http://localhost:8000
GIT_SHA=dev                        # set by Render build (RENDER_GIT_COMMIT)

# Database (Supabase session pooler in prod; docker compose locally)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/abhyas
ALEMBIC_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/abhyas

# Security
SESSION_SECRET=                    # 64 random hex chars
PHONE_HASH_SALT=                   # 32 random hex chars
PHONE_ENC_KEY=                     # Fernet key: python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
DEMO_PASSWORD=abhyas-demo-2026     # dev default; ROTATE in production (H13)

# Claude (Anthropic) — H1
LLM_PROVIDER=anthropic             # anthropic | mock
ANTHROPIC_API_KEY=
CLAUDE_MODEL_FAST=claude-haiku-5-5
CLAUDE_MODEL_SMART=claude-sonnet-5-5
CLAUDE_MODEL_BUILD=claude-sonnet-5-5
LLM_DAILY_TOKEN_BUDGET=3000000

# Speech — H2
STT_PROVIDER=sarvam                # sarvam | bhashini | google | mock
TTS_PROVIDER=sarvam                # sarvam | mock
SARVAM_API_KEY=
SARVAM_BASE_URL=https://api.sarvam.ai
SARVAM_STT_MODEL=saaras:v4
SARVAM_TTS_MODEL=bulbul:v3
BHASHINI_USER_ID=
BHASHINI_API_KEY=
GOOGLE_APPLICATION_CREDENTIALS=
MOCK_STT_TEXT=रवि, 52 में से 17 कैसे घटाया? बताओ।

# WhatsApp Cloud API (Meta) — H4/H5
WHATSAPP_ENABLED=false
WHATSAPP_GRAPH_VERSION=v23.0       # verify current version in Meta docs
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_APP_SECRET=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_DISPLAY_NUMBER=           # shown on landing page, e.g. +1 555 …
WHATSAPP_UTILITY_COST_INR=0.12     # verify current Meta India utility rate

# Retrieval (optional dense vectors) — H16
VOYAGE_API_KEY=
VOYAGE_MODEL=voyage-multilingual-2

# Demo / evaluation
SERVE_IN_REVIEW_TO_DEMO=true
DEMO_MODE=true                     # shows sample chips + demo banners

# Optional
SENTRY_DSN=
```

---

## FILE: content-seed/personas/aman.yaml

```
id: aman
name_hi: अमन
age: 7
temperament: distracted
voice_id: child_aman
speech_style_hi: "चंचल, बीच में दूसरी बातें करने लगता है, वाक्य अधूरे छोड़ देता है, फिर लौट आता है"
off_topic_lines_hi:
  - "दीदी, बाहर बंदर आया है!"
  - "दीदी, कल मेरे घर मेहमान आए थे!"
  - "दीदी, मेरी चप्पल टूट गई।"
  - "दीदी, आज मिड-डे मील में क्या है?"
```

---

## FILE: content-seed/personas/priya.yaml

```
id: priya
name_hi: प्रिया
age: 7
temperament: shy
voice_id: child_priya
speech_style_hi: "धीमी आवाज़, हिचकिचाते हुए, आधे वाक्य, 'मैडम…' से शुरू करती है; डाँट पड़ने पर चुप हो जाती है"
off_topic_lines_hi:
  - "मैडम… मेरी कॉपी घर पर रह गई।"
  - "मैडम… पानी पी लूँ?"
  - "मैडम… मुझे नहीं पता…"
  - "मैडम… रवि मेरी रबर ले गया।"
```

---

## FILE: content-seed/personas/ravi.yaml

```
id: ravi
name_hi: रवि
age: 7
temperament: confident
voice_id: child_ravi
speech_style_hi: "जल्दी और पूरे भरोसे से बोलता है, छोटे वाक्य, 'दीदी' कहकर बात करता है, अपने उत्तर पर अड़ा रहता है"
off_topic_lines_hi:
  - "दीदी, आज खेल का पीरियड होगा?"
  - "दीदी, मेरे पास नई पेंसिल है!"
  - "दीदी, मैं सबसे पहले बताऊँगा!"
  - "दीदी, छुट्टी कब होगी?"
```

---

## FILE: content-seed/moves/LIT_MATRA_BLENDING.yaml

```
# DRAFT — needs FLN coach review (H8) and module_ref verification (H7).
id: LIT_MATRA_BLENDING
version: 1
status: in_review
domain: literacy
grade: [1, 2]
title_hi: "मात्रा वाले शब्द: अक्षर की ध्वनि मिलाकर पढ़ना"
summary_hi: "बच्चे को अक्षर और मात्रा की ध्वनि अलग-अलग बोलकर फिर मिलाकर पूरा शब्द पढ़ना सिखाएँ; अंदाज़े से पढ़ने पर उसे रोकें नहीं, ध्वनि पर लौटाएँ।"
tags: [reading, phonics, matra, blending, bhasha]
module_ref:
  source_id: up_bhasha_sandarshika_c1
  section: "मात्रा और शब्द पठन"
  page: null
  verified: false
sankul_month: October

key_points:
  - id: kp1
    text_hi: "बच्चे तीन तरह से अटकते हैं: मात्रा छोड़ देते हैं (मेला को 'मल'), पहले अक्षर से अंदाज़ा लगाते हैं (मेला को 'मछली'), या अक्षर-अक्षर बोलते हैं पर मिला नहीं पाते ('मे… ला')।"
    must_have: true
    keywords_hi: [मात्रा, अंदाज़ा, मिला, अक्षर, छोड़]
    source_chunk_ids: []
  - id: kp2
    text_hi: "हर अक्षर पर उँगली रखकर पहले व्यंजन और मात्रा की ध्वनि बुलवाएँ: म + े = मे।"
    must_have: true
    keywords_hi: [उँगली, ध्वनि, मात्रा, मे]
    source_chunk_ids: []
  - id: kp3
    text_hi: "फिर धीरे-धीरे अक्षरों को मिलाकर बुलवाएँ: मे… ला… मेला। पहले शिक्षक करके दिखाएँ, फिर बच्चे साथ में।"
    must_have: true
    keywords_hi: [मिला, धीरे, करके दिखा, साथ]
    source_chunk_ids: []
  - id: kp4
    text_hi: "अंदाज़े से गलत पढ़ने पर डाँटें नहीं; कहें 'पहला अक्षर फिर से देखो, कौन-सी मात्रा है?'"
    must_have: false
    keywords_hi: [डाँट, फिर से देखो, मात्रा]
    source_chunk_ids: []

teaching_acts_effective: [phonics_sound_out, model_step_aloud, contrast_answers, ask_to_explain, involve_peer]
target_causes: [AKSHAR_BY_AKSHAR, FIRST_AKSHAR_GUESS, MATRA_DROP]

rubric:
  criteria:
    - id: crit_sound_out
      text_hi: "अक्षर और मात्रा की ध्वनि बुलवाना"
      levels: {0: "ध्वनि पर काम नहीं किया", 1: "पूरा शब्द दोहरवाया, ध्वनि नहीं", 2: "हर अक्षर-मात्रा की ध्वनि अलग बुलवाई"}
      signal_acts: [phonics_sound_out]
      negative_acts: []
    - id: crit_blend_model
      text_hi: "मिलाकर पढ़ना करके दिखाना"
      levels: {0: "नहीं दिखाया", 1: "शब्द पढ़कर सुना दिया", 2: "धीरे-धीरे मिलाकर दिखाया और बच्चों से साथ में करवाया"}
      signal_acts: [model_step_aloud]
      negative_acts: []
    - id: crit_no_telling
      text_hi: "शब्द बताने के बजाय बच्चे को पढ़ने देना"
      levels: {0: "शब्द खुद बता दिया", 1: "न बताया, न जाँच करवाई", 2: "बच्चे से फिर से ध्वनि मिलवाकर खुद पढ़वाया"}
      signal_acts: [phonics_sound_out, contrast_answers, involve_peer]
      negative_acts: [tell_answer, scold]

feedback_bank:
  crit_sound_out:
    strength_hi: "आपने अक्षर और मात्रा की ध्वनि अलग-अलग बुलवाई।"
    change_hi: "पूरा शब्द दोहरवाने के बजाय पहले अक्षर पर उँगली रखवाकर उसकी ध्वनि बुलवाइए।"
    exact_words_hi: "अमन, पहले अक्षर पर उँगली रखो। म पर कौन-सी मात्रा है? बोलो, म… ए… मे।"
  crit_blend_model:
    strength_hi: "आपने मिलाकर पढ़ना धीरे-धीरे करके दिखाया।"
    change_hi: "शब्द पढ़कर सुनाने से पहले धीरे-धीरे ध्वनियाँ मिलाकर दिखाइए, फिर बच्चों से साथ में करवाइए।"
    exact_words_hi: "मेरे साथ बोलो: मे… ला… मे-ला… मेला!"
  crit_no_telling:
    strength_hi: "आपने शब्द खुद नहीं बताया, बच्चे को पढ़ने दिया।"
    change_hi: "बच्चा अंदाज़ा लगाए तो उसे पहले अक्षर पर लौटाइए, शब्द मत बताइए।"
    exact_words_hi: "प्रिया, मछली नहीं, पहला अक्षर फिर से देखो। उस पर कौन-सी मात्रा है?"

learn_script_hi: >-
  नमस्ते! इस हफ्ते हम मात्रा वाले शब्द पढ़ना सिखाने का एक तरीका सीखेंगे। जब बच्चे 'मेला' पढ़ते हैं, तो कुछ मात्रा छोड़कर
  'मल' पढ़ते हैं। कुछ पहला अक्षर देखकर अंदाज़ा लगाते हैं और 'मछली' कह देते हैं। कुछ 'मे… ला' अलग-अलग बोलते हैं पर
  मिलाकर नहीं पढ़ पाते। पहला कदम: बच्चे से हर अक्षर पर उँगली रखवाइए और ध्वनि बुलवाइए: म और ए की मात्रा, मे। ल और आ
  की मात्रा, ला। दूसरा कदम: आप खुद धीरे-धीरे मिलाकर दिखाइए: मे… ला… मेला। फिर बच्चों से साथ में बुलवाइए। तीसरा कदम:
  अगर बच्चा अंदाज़ा लगाए, तो डाँटिए नहीं और शब्द भी मत बताइए। कहिए, पहला अक्षर फिर से देखो, कौन-सी मात्रा है?
  अब आप यह तरीका अपने शब्दों में बताइए, फिर तीन बच्चों के साथ अभ्यास करेंगे।
learn_summary_hi:
  - "1. तीन अटकनें: मात्रा छोड़ना (मल), अंदाज़ा (मछली), मिला न पाना (मे… ला)"
  - "2. उँगली रखकर ध्वनि: म + े = मे, ल + ा = ला"
  - "3. करके दिखाएँ: मे… ला… मेला, फिर साथ में"
  - "4. अंदाज़े पर डाँटें नहीं, शब्द न बताएँ — पहले अक्षर पर लौटाएँ"

scenario:
  intro_hi: "कक्षा 1। बोर्ड पर शब्द लिखा है: मेला। रवि, प्रिया और अमन ने उसे पढ़ने की कोशिश की है। अब आप उनसे बात करें।"
  items:
    - {type: read_word, word: "मेला"}
    - {type: read_word, word: "पानी"}
    - {type: read_word, word: "किताब"}
    - {type: read_word, word: "गुड़िया"}
  children:
    - {persona_id: ravi,  misconception: AKSHAR_BY_AKSHAR}     # मे - ला
    - {persona_id: priya, misconception: FIRST_AKSHAR_GUESS}   # मछली
    - {persona_id: aman,  misconception: MATRA_DROP}           # मल
  guess_lexicon:
    म: [मछली, मटर]
    प: [पतंग, पत्ता]
    क: [कमल, कलम]
    ग: [गमला, गाय]
    न: [नल, नाव]
    ब: [बतख, बस]
    र: [रथ, रस्सी]
    स: [सड़क, सेब]
    ल: [लट्टू, लड्डू]
    ट: [टमाटर, टोपी]
    च: [चमचा, चिड़िया]
    आ: [आम, आग]

model_rehearsal:
  - {speaker: teacher, text_hi: "रवि, शाबाश कोशिश की। अब उँगली रखकर बोलो: म… ए… मे। फिर ल… आ… ला।", acts: [phonics_sound_out, praise_effort], addressed: ravi, problem: null}
  - {speaker: teacher, text_hi: "प्रिया, पहला अक्षर फिर से देखो। म पर कौन-सी मात्रा है? धीरे से उसकी आवाज़ निकालो।", acts: [phonics_sound_out], addressed: priya, problem: null}
  - {speaker: teacher, text_hi: "अमन, म के ऊपर ये मात्रा देखो। म… ए… मे। बोलो।", acts: [phonics_sound_out], addressed: aman, problem: null}
  - {speaker: teacher, text_hi: "अब सब मेरे साथ धीरे-धीरे मिलाओ: मे… ला… मे-ला… मेला!", acts: [model_step_aloud], addressed: all, problem: null}

peer_checklist:
  - "शिक्षक ने बच्चों से अक्षर पर उँगली रखवाई।"
  - "अक्षर और मात्रा की ध्वनि अलग-अलग बुलवाई गई।"
  - "शिक्षक ने धीरे-धीरे मिलाकर पढ़ना करके दिखाया।"
  - "अंदाज़ा लगाने वाले बच्चे को डाँटा नहीं गया और शब्द नहीं बताया गया।"
reflection_questions:
  - "आपकी कक्षा में तीनों में से कौन-सी अटकन सबसे आम है?"
  - "ध्वनि मिलाकर पढ़वाने पर किस बच्चे में बदलाव दिखा?"
approvals: []
```

---

## FILE: content-seed/moves/NUM_ADD_CARRY_BUNDLES.yaml

```
# DRAFT — needs FLN coach review (H8) and module_ref verification (H7).
id: NUM_ADD_CARRY_BUNDLES
version: 1
status: in_review
domain: numeracy
grade: [2]
title_hi: "हासिल वाला जोड़: 10 तीलियों का बंडल बनाकर"
summary_hi: "जब इकाई का जोड़ 10 या उससे ज़्यादा हो, तो 10 तीलियों का नया बंडल बनवाएँ और उसे दहाई में जोड़ें।"
tags: [addition, regrouping, carry, place_value, ganit]
module_ref:
  source_id: up_ganit_sandarshika_c2
  section: "जोड़ (हासिल सहित)"
  page: null
  verified: false
sankul_month: November

key_points:
  - id: kp1
    text_hi: "38 + 45 में इकाई का जोड़ 13 आता है। बच्चे अक्सर 13 पूरा लिख देते हैं या हासिल भूल जाते हैं। पहले बच्चे से उसका तरीका पूछें।"
    must_have: true
    keywords_hi: [पूछें, तरीका, 13, हासिल, भूल]
    source_chunk_ids: []
  - id: kp2
    text_hi: "दोनों संख्याएँ बंडल-तीली से बनवाएँ: 38 = 3 बंडल 8 तीलियाँ, 45 = 4 बंडल 5 तीलियाँ।"
    must_have: true
    keywords_hi: [बंडल, तीली, बनवा, दहाई, इकाई]
    source_chunk_ids: []
  - id: kp3
    text_hi: "खुली तीलियाँ मिलाने पर 13 हो जाती हैं। इनमें से 10 का एक नया बंडल बाँधें: अब 3 खुली तीलियाँ और 1 नया बंडल।"
    must_have: true
    keywords_hi: [10, नया बंडल, बाँध, 13, 3]
    source_chunk_ids: []
  - id: kp4
    text_hi: "नया बंडल बाकी बंडलों में मिलाएँ: 3 + 4 + 1 = 8 बंडल। उत्तर 8 बंडल और 3 तीलियाँ, यानी 83।"
    must_have: false
    keywords_hi: [8 बंडल, 83, मिलाएँ]
    source_chunk_ids: []
  - id: kp5
    text_hi: "उत्तर खुद न बताएँ; बच्चों के अलग-अलग उत्तरों की तुलना करवाएँ।"
    must_have: true
    keywords_hi: [न बताएँ, तुलना, उत्तर]
    source_chunk_ids: []

teaching_acts_effective: [ask_to_explain, concrete_representation, probe_simpler_case, contrast_answers, model_step_aloud, involve_peer]
target_causes: [ADD_CARRY_FORGOTTEN, ADD_NO_CARRY, ADD_CARRY_WRONG_DIGIT]

rubric:
  criteria:
    - id: crit_explain
      text_hi: "बच्चे से उसका तरीका पूछना"
      levels: {0: "तरीका नहीं पूछा", 1: "पूछा पर सुना नहीं", 2: "पूछा और बच्चे के कदम सुने"}
      signal_acts: [ask_to_explain]
      negative_acts: []
    - id: crit_concrete
      text_hi: "10 तीलियों का नया बंडल बनवाना"
      levels: {0: "केवल अंकों में", 1: "तीलियाँ गिनवाईं पर बंडल नहीं बनवाया", 2: "13 में से 10 का नया बंडल बनवाया और दहाई में मिलवाया"}
      signal_acts: [concrete_representation, model_step_aloud, probe_simpler_case]
      negative_acts: []
    - id: crit_no_telling
      text_hi: "उत्तर बताने के बजाय तुलना करवाना"
      levels: {0: "उत्तर खुद बताया", 1: "उत्तर नहीं बताया पर तुलना नहीं करवाई", 2: "अलग-अलग उत्तरों की तुलना करवाई"}
      signal_acts: [contrast_answers, involve_peer]
      negative_acts: [tell_answer]

feedback_bank:
  crit_explain:
    strength_hi: "आपने बच्चे से पूछा कि उसने कैसे जोड़ा, इससे उसकी गलती की वजह दिखी।"
    change_hi: "अगली बार उत्तर जाँचने से पहले बच्चे से उसका हर कदम सुनिए।"
    exact_words_hi: "रवि, 8 और 5 जोड़कर तुम्हें क्या मिला, और फिर तुमने क्या लिखा?"
  crit_concrete:
    strength_hi: "आपने तीलियों से जोड़ करवाया, बच्चों ने गिनकर देखा।"
    change_hi: "13 तीलियों में से 10 का नया बंडल बँधवाइए, फिर उसे बंडलों में मिलवाइए।"
    exact_words_hi: "इन 13 तीलियों में से 10 गिनकर एक बंडल बाँधो। अब कितने बंडल हो गए?"
  crit_no_telling:
    strength_hi: "आपने उत्तर नहीं बताया, बच्चों को खुद सोचने दिया।"
    change_hi: "दो अलग उत्तर सामने रखकर पूछिए कि तीलियों से कौन-सा सही निकलता है।"
    exact_words_hi: "प्रिया ने 713 कहा, रवि ने 73। बंडल गिनकर बताओ, असल में कितनी तीलियाँ हैं?"

learn_script_hi: >-
  नमस्ते! इस हफ्ते हम हासिल वाला जोड़ सीखेंगे। 38 और 45 जोड़ते समय इकाई में 8 और 5 मिलकर 13 होते हैं। कुछ बच्चे 13 पूरा
  नीचे लिख देते हैं और उत्तर 713 बना देते हैं। कुछ 3 लिखते हैं और हासिल भूल जाते हैं, तो उत्तर 73 आता है। कुछ उल्टा
  1 लिखकर 3 ऊपर ले जाते हैं। पहला कदम: बच्चे से पूछिए, तुमने कैसे जोड़ा? दूसरा कदम: दोनों संख्याएँ बंडल और तीलियों से
  बनवाइए। 38 यानी 3 बंडल और 8 तीलियाँ, 45 यानी 4 बंडल और 5 तीलियाँ। खुली तीलियाँ मिलाइए, 13 हो गईं। अब पूछिए, क्या
  इनमें से एक बंडल बन सकता है? 10 तीलियाँ गिनकर नया बंडल बाँधिए। 3 तीलियाँ खुली बचीं। अब बंडल गिनिए: 3 और 4 और यह
  नया 1, कुल 8 बंडल। उत्तर 8 बंडल और 3 तीलियाँ, यानी 83। तीसरा कदम: उत्तर खुद न बताइए, बच्चों के उत्तरों की तुलना
  करवाइए। अब आप यह तरीका अपने शब्दों में बताइए।
learn_summary_hi:
  - "1. बच्चे से पूछें: तुमने कैसे जोड़ा?"
  - "2. 38 = 3 बंडल + 8 तीलियाँ, 45 = 4 बंडल + 5 तीलियाँ"
  - "3. 8 + 5 = 13 तीलियाँ → 10 का नया बंडल → 3 तीलियाँ बचीं"
  - "4. 3 + 4 + 1 = 8 बंडल → 83"
  - "5. उत्तर न बताएँ, तुलना करवाएँ"

scenario:
  intro_hi: "कक्षा 2। बोर्ड पर लिखा है: 38 + 45। रवि, प्रिया और अमन ने अपने उत्तर बताए हैं। अब आप उनसे बात करें।"
  items:
    - {type: add, a: 38, b: 45}
    - {type: add, a: 27, b: 48}
    - {type: add, a: 56, b: 29}
  children:
    - {persona_id: ravi,  misconception: ADD_CARRY_FORGOTTEN}     # 73
    - {persona_id: priya, misconception: ADD_NO_CARRY}            # 713
    - {persona_id: aman,  misconception: ADD_CARRY_WRONG_DIGIT}   # 101
  guess_lexicon: {}

model_rehearsal:
  - {speaker: teacher, text_hi: "रवि, तुमने 38 और 45 कैसे जोड़े? पहले इकाई में क्या किया?", acts: [ask_to_explain], addressed: ravi, problem: null}
  - {speaker: teacher, text_hi: "प्रिया, तुम्हारी कोशिश अच्छी है। बताओ, 713 कैसे आया?", acts: [ask_to_explain, praise_effort], addressed: priya, problem: null}
  - {speaker: teacher, text_hi: "सब देखो: 3 बंडल 8 तीलियाँ और 4 बंडल 5 तीलियाँ। खुली तीलियाँ मिलाओ, 13 हुईं। इनमें से 10 का एक नया बंडल बाँधते हैं।", acts: [concrete_representation], addressed: all, problem: null}
  - {speaker: teacher, text_hi: "अमन, तुमने 101 कहा था, रवि अब 83 कह रहा है। बंडल गिनकर बताओ, कौन सही है?", acts: [contrast_answers], addressed: aman, problem: null}
  - {speaker: teacher, text_hi: "प्रिया, 713 और 83, तीलियाँ गिनकर कौन-सा सही निकलता है?", acts: [contrast_answers], addressed: priya, problem: null}
  - {speaker: teacher, text_hi: "रवि, तुमने 73 कहा था। नया बंडल कहाँ गया? अब बताओ, 73 या 83?", acts: [contrast_answers], addressed: ravi, problem: null}

peer_checklist:
  - "शिक्षक ने बच्चे से पूछा कि उसने कैसे जोड़ा।"
  - "दोनों संख्याएँ बंडल-तीली या चित्र से बनाई गईं।"
  - "10 खुली तीलियों का नया बंडल बनवाया गया।"
  - "शिक्षक ने उत्तर खुद नहीं बताया।"
reflection_questions:
  - "नया बंडल बनाते समय बच्चों ने क्या कहा या किया?"
  - "किस गलती वाले बच्चे को सबसे ज़्यादा मदद चाहिए थी?"
approvals: []
```

---

## FILE: content-seed/moves/NUM_PLACE_VALUE_BUNDLES.yaml

```
# DRAFT — needs FLN coach review (H8) and module_ref verification (H7).
id: NUM_PLACE_VALUE_BUNDLES
version: 1
status: in_review
domain: numeracy
grade: [1, 2]
title_hi: "स्थानीय मान: बंडल और खुली तीलियों से संख्या"
summary_hi: "बंडल (दहाई) और खुली तीलियों (इकाई) से दो अंकों की संख्या बनवाएँ और बच्चे से पूछें कि उसने संख्या कैसे लिखी।"
tags: [place_value, number_sense, ganit]
module_ref:
  source_id: up_ganit_sandarshika_c2
  section: "स्थानीय मान (दहाई-इकाई)"
  page: null
  verified: false
sankul_month: September

key_points:
  - id: kp1
    text_hi: "एक बंडल में 10 तीलियाँ होती हैं; बच्चे से खुद गिनकर बंडल बनवाएँ ताकि वह जाने कि एक बंडल 10 के बराबर है।"
    must_have: true
    keywords_hi: [बंडल, 10, गिन, बराबर]
    source_chunk_ids: []
  - id: kp2
    text_hi: "4 बंडल और 7 तीलियाँ = 40 और 7 = 47। बंडल दहाई के घर में, खुली तीलियाँ इकाई के घर में।"
    must_have: true
    keywords_hi: [दहाई, इकाई, घर, 47, 40]
    source_chunk_ids: []
  - id: kp3
    text_hi: "आम गलतियाँ: बंडल को 1 गिनना (11), 'चालीस-सात' सुनकर 407 लिखना, या अंक उल्टे लिखना (74)। बच्चे से पूछें कि उसने कैसे लिखा।"
    must_have: true
    keywords_hi: [गलती, 407, 74, 11, पूछें]
    source_chunk_ids: []
  - id: kp4
    text_hi: "बच्चे से बोलकर गिनवाएँ: 10, 20, 30, 40 … फिर 41 से 47 तक।"
    must_have: false
    keywords_hi: [10, 20, 30, 40, गिनवाएँ]
    source_chunk_ids: []

teaching_acts_effective: [ask_to_explain, concrete_representation, model_step_aloud, contrast_answers, involve_peer]
target_causes: [PV_REVERSAL, PV_BUNDLE_AS_ONE, PV_CONCAT_SPOKEN]

rubric:
  criteria:
    - id: crit_explain
      text_hi: "बच्चे से उसका तरीका पूछना"
      levels: {0: "नहीं पूछा", 1: "पूछा पर आगे नहीं बढ़ीं", 2: "पूछा और उसके उत्तर के आधार पर अगला सवाल किया"}
      signal_acts: [ask_to_explain]
      negative_acts: []
    - id: crit_concrete
      text_hi: "बंडल को 10 के रूप में गिनवाना"
      levels: {0: "केवल अंक", 1: "बंडल दिखाए पर 10-10 करके नहीं गिनवाया", 2: "10, 20, 30, 40 गिनवाया और फिर खुली तीलियाँ"}
      signal_acts: [concrete_representation, model_step_aloud]
      negative_acts: []
    - id: crit_no_telling
      text_hi: "उत्तरों की तुलना करवाना"
      levels: {0: "उत्तर बताया", 1: "न बताया न तुलना करवाई", 2: "अलग उत्तरों की तुलना करवाई"}
      signal_acts: [contrast_answers, involve_peer]
      negative_acts: [tell_answer]

feedback_bank:
  crit_explain:
    strength_hi: "आपने बच्चे से पूछा कि उसने संख्या कैसे लिखी।"
    change_hi: "बच्चे के उत्तर के बाद पूछिए कि उसने पहले कौन-सा अंक लिखा और क्यों।"
    exact_words_hi: "अमन, तुमने 407 कैसे लिखा? पहले क्या लिखा, फिर क्या?"
  crit_concrete:
    strength_hi: "आपने बंडल और तीलियाँ दिखाकर संख्या बनवाई।"
    change_hi: "बंडल को 10-10 करके बोलकर गिनवाइए: 10, 20, 30, 40।"
    exact_words_hi: "चलो बंडल गिनें: 10, 20, 30, 40। अब खुली तीलियाँ जोड़ो: 41, 42 … कितनी हुईं?"
  crit_no_telling:
    strength_hi: "आपने उत्तर नहीं बताया।"
    change_hi: "दो बच्चों के उत्तर साथ रखकर पूछिए कि तीलियाँ गिनकर कौन-सा सही है।"
    exact_words_hi: "प्रिया ने 11 कहा और रवि ने 47। गिनकर देखो, कौन सही है?"

learn_script_hi: >-
  नमस्ते! इस हफ्ते का तरीका है: बंडल और खुली तीलियों से संख्या समझाना। बच्चे से 10 तीलियाँ गिनवाकर एक बंडल बँधवाइए,
  ताकि उसे पता चले कि एक बंडल यानी 10। अब मेज़ पर 4 बंडल और 7 खुली तीलियाँ रखिए और पूछिए, कुल कितनी तीलियाँ हैं?
  कुछ बच्चे हर बंडल को 1 गिनते हैं और 11 कहते हैं। कुछ 'चालीस' और 'सात' सुनकर 407 लिख देते हैं। कुछ अंक उल्टे लिखकर
  74 बना देते हैं। सबसे पहले बच्चे से पूछिए: तुमने कैसे गिना या कैसे लिखा? फिर बंडलों को 10-10 करके बोलकर गिनवाइए:
  10, 20, 30, 40। फिर खुली तीलियाँ: 41, 42, 43 से 47 तक। बताइए कि बंडल दहाई के घर में जाते हैं और खुली तीलियाँ इकाई
  के घर में। उत्तर खुद न बताइए; अलग-अलग उत्तरों की तुलना करवाइए। अब आप यह तरीका अपने शब्दों में बताइए।
learn_summary_hi:
  - "1. 10 तीलियाँ गिनकर एक बंडल बँधवाएँ"
  - "2. 4 बंडल + 7 तीलियाँ = 47 (दहाई में 4, इकाई में 7)"
  - "3. गलतियाँ: 11, 407, 74 — बच्चे से तरीका पूछें"
  - "4. बोलकर गिनवाएँ: 10, 20, 30, 40, 41 … 47"
  - "5. उत्तर न बताएँ, तुलना करवाएँ"

scenario:
  intro_hi: "कक्षा 1-2। मेज़ पर 4 बंडल (हर बंडल में 10 तीलियाँ) और 7 खुली तीलियाँ हैं। सवाल: कुल कितनी तीलियाँ हैं? रवि, प्रिया और अमन ने उत्तर बताए हैं।"
  items:
    - {type: place_value, tens: 4, ones: 7}
    - {type: place_value, tens: 3, ones: 5}
    - {type: place_value, tens: 6, ones: 2}
  children:
    - {persona_id: ravi,  misconception: PV_REVERSAL}        # 74
    - {persona_id: priya, misconception: PV_BUNDLE_AS_ONE}   # 11
    - {persona_id: aman,  misconception: PV_CONCAT_SPOKEN}   # 407
  guess_lexicon: {}

model_rehearsal:
  - {speaker: teacher, text_hi: "रवि, तुमने 74 कैसे लिखा? पहले कौन-सा अंक लिखा?", acts: [ask_to_explain], addressed: ravi, problem: null}
  - {speaker: teacher, text_hi: "प्रिया, अच्छा, धीरे से बताओ, तुमने कैसे गिना?", acts: [ask_to_explain, praise_effort], addressed: priya, problem: null}
  - {speaker: teacher, text_hi: "सब मेरे साथ गिनो। हर बंडल में 10 तीलियाँ: 10, 20, 30, 40। अब खुली तीलियाँ: 41, 42, 43, 44, 45, 46, 47।", acts: [model_step_aloud, concrete_representation], addressed: all, problem: null}
  - {speaker: teacher, text_hi: "अमन, तुमने 407 कहा था और अभी हमने गिनकर 47 पाया। कौन-सा सही है?", acts: [contrast_answers], addressed: aman, problem: null}
  - {speaker: teacher, text_hi: "प्रिया, 11 या 47? बंडल में कितनी तीलियाँ थीं?", acts: [contrast_answers], addressed: priya, problem: null}
  - {speaker: teacher, text_hi: "रवि, 74 और 47 में से कौन-सा सही है? दहाई के घर में कितने बंडल हैं?", acts: [contrast_answers], addressed: ravi, problem: null}

peer_checklist:
  - "बच्चों ने 10 तीलियाँ गिनकर बंडल बनाया या बंडल को 10 गिना।"
  - "शिक्षक ने बच्चे से पूछा कि उसने संख्या कैसे लिखी।"
  - "बंडलों को 10, 20, 30 … बोलकर गिना गया।"
  - "शिक्षक ने उत्तर खुद नहीं बताया।"
reflection_questions:
  - "किस गलती (11, 407 या 74) वाले बच्चे आपकी कक्षा में ज़्यादा हैं?"
  - "10-10 गिनवाने पर बच्चों ने क्या किया?"
approvals: []
```

---

## FILE: content-seed/moves/NUM_SUB_REGROUP_BUNDLES.yaml

```
# DRAFT — written by the team for the prototype. Needs FLN coach review (HUMAN INPUT H8) and
# verification of module_ref against the actual UP teacher guide (H7) before status: approved.
id: NUM_SUB_REGROUP_BUNDLES
version: 1
status: in_review
domain: numeracy
grade: [2]
title_hi: "हासिल वाला घटाव: बंडल खोलकर"
summary_hi: "जब इकाई में ऊपर की संख्या छोटी हो, तो बच्चे से उसका तरीका पूछें और 10-10 तीलियों के बंडल खोलकर घटाव समझाएँ।"
tags: [subtraction, regrouping, place_value, ganit]
module_ref:
  source_id: up_ganit_sandarshika_c2
  section: "घटाव (हासिल सहित)"
  page: null
  verified: false
sankul_month: October

key_points:
  - id: kp1
    text_hi: "जब इकाई में ऊपर की संख्या छोटी हो, तो बच्चे अक्सर बड़ी संख्या में से छोटी घटा देते हैं। सबसे पहले बच्चे से पूछें कि उसने कैसे किया।"
    must_have: true
    keywords_hi: [पूछें, कैसे, तरीका, बड़ी, छोटी, उल्टा]
    source_chunk_ids: []
  - id: kp2
    text_hi: "10-10 तीलियों के बंडल से संख्या बनवाएँ: 43 यानी 4 बंडल और 3 खुली तीलियाँ।"
    must_have: true
    keywords_hi: [बंडल, तीली, दहाई, इकाई, 10]
    source_chunk_ids: []
  - id: kp3
    text_hi: "3 तीलियों में से 7 नहीं निकलतीं, इसलिए एक बंडल खोलें: अब 13 खुली तीलियाँ और 3 बंडल हैं।"
    must_have: true
    keywords_hi: [खोल, बंडल, 13, हासिल, उधार]
    source_chunk_ids: []
  - id: kp4
    text_hi: "खुली तीलियों में से 7 और बंडलों में से 2 हटाएँ; बचा 1 बंडल और 6 तीलियाँ, यानी 16।"
    must_have: false
    keywords_hi: [हटाएँ, बचा, गिन, 16]
    source_chunk_ids: []
  - id: kp5
    text_hi: "उत्तर खुद न बताएँ। दो उत्तरों की तुलना करवाएँ और बच्चे को ही सही उत्तर तक पहुँचने दें।"
    must_have: true
    keywords_hi: [न बताएँ, तुलना, दोनों, खुद, सोच]
    source_chunk_ids: []

teaching_acts_effective: [ask_to_explain, concrete_representation, probe_simpler_case, contrast_answers, model_step_aloud, involve_peer]
target_causes: [SUB_SMALLER_FROM_LARGER, SUB_BORROW_NO_DECREMENT, SUB_WRITE_ZERO_WHEN_STUCK]

rubric:
  criteria:
    - id: crit_explain
      text_hi: "बच्चे से उसका तरीका पूछना"
      levels:
        0: "बच्चे का तरीका नहीं पूछा"
        1: "पूछा, पर केवल 'गलत है' कहकर आगे बढ़ गईं"
        2: "बच्चे से पूछा कि उसने कैसे घटाया और उसकी बात सुनी"
      signal_acts: [ask_to_explain]
      negative_acts: []
    - id: crit_concrete
      text_hi: "बंडल और तीलियों का उपयोग"
      levels:
        0: "केवल अंकों में समझाया"
        1: "तीलियों का ज़िक्र किया, पर बंडल खोलकर नहीं दिखाया"
        2: "संख्या बंडल-तीली से बनवाई और बंडल खोलकर 13 तीलियाँ दिखाईं"
      signal_acts: [concrete_representation, probe_simpler_case]
      negative_acts: []
    - id: crit_no_telling
      text_hi: "उत्तर बताने के बजाय बच्चे को सोचने देना"
      levels:
        0: "सही उत्तर खुद बता दिया"
        1: "उत्तर नहीं बताया, पर बच्चे से तुलना या जाँच नहीं करवाई"
        2: "दो उत्तरों की तुलना करवाई या साथी बच्चे से समझवाया"
      signal_acts: [contrast_answers, involve_peer]
      negative_acts: [tell_answer]
    - id: crit_all_children
      text_hi: "सभी बच्चों को शामिल करना (शांत बच्चे सहित)"
      levels:
        0: "केवल एक बच्चे से बात की"
        1: "दो बच्चों से बात की"
        2: "तीनों बच्चों से बात की, शांत बच्ची को भी प्रोत्साहित किया"
      signal_acts: [involve_peer, praise_effort]
      negative_acts: [scold]

feedback_bank:
  crit_explain:
    strength_hi: "आपने बच्चे से उसका तरीका पूछा, इससे उसकी असली उलझन सामने आई।"
    change_hi: "अगली बार 'गलत है' कहने से पहले बच्चे से पूछिए कि उसने कैसे घटाया।"
    exact_words_hi: "रवि, तुमने 43 में से 27 कैसे घटाया? मुझे एक-एक कदम बताओ।"
  crit_concrete:
    strength_hi: "आपने बंडल और तीलियों से संख्या बनवाई, यह बच्चों को दिखता है।"
    change_hi: "अगली बार बंडल खोलकर गिनवाइए कि अब कितनी खुली तीलियाँ हो गईं।"
    exact_words_hi: "3 तीलियों में से 7 नहीं निकलतीं, तो एक बंडल खोलो। अब गिनो, कितनी तीलियाँ हुईं?"
  crit_no_telling:
    strength_hi: "आपने उत्तर खुद नहीं बताया, बच्चों को सोचने का मौका दिया।"
    change_hi: "उत्तर बताने के बजाय दो उत्तर सामने रखकर पूछिए कि कौन-सा सही है।"
    exact_words_hi: "रवि ने 24 कहा और प्रिया ने 16। तीलियाँ गिनकर बताओ, कौन-सा सही है?"
  crit_all_children:
    strength_hi: "आपने तीनों बच्चों को बातचीत में शामिल किया।"
    change_hi: "शांत बच्ची प्रिया का नाम लेकर उसे धीरे से बोलने का मौका दीजिए।"
    exact_words_hi: "प्रिया, तुम्हारा तरीका भी सुनना है। धीरे से बताओ, कोई बात नहीं।"

learn_script_hi: >-
  नमस्ते! इस हफ्ते हम हासिल वाले घटाव पर एक तरीका सीखेंगे। जब बच्चे 43 में से 27 घटाते हैं, तो कई बच्चे इकाई में
  3 में से 7 नहीं घटा पाते और 7 में से 3 घटा देते हैं। उनका उत्तर आता है 24। कुछ बच्चे 13 में से 7 तो करते हैं,
  पर दहाई में 4 को 3 करना भूल जाते हैं। ये गलतियाँ लापरवाही नहीं हैं, बच्चे के मन में एक नियम बैठा होता है।
  इसलिए सबसे पहला कदम है: बच्चे से पूछिए, तुमने कैसे किया? जब बच्चा अपना तरीका बताता है, तब पता चलता है कि उलझन कहाँ है।
  दूसरा कदम: 10-10 तीलियों के बंडल लीजिए। 43 बनवाइए: 4 बंडल और 3 खुली तीलियाँ। अब पूछिए, 3 तीलियों में से 7 कैसे
  निकालें? बच्चे खुद कहेंगे, नहीं निकलेंगी। तब एक बंडल खोलिए। अब 13 खुली तीलियाँ और 3 बंडल हैं। 13 में से 7 हटाइए,
  6 बचीं। 3 बंडल में से 2 हटाइए, 1 बचा। कुल 1 बंडल और 6 तीलियाँ, यानी 16। तीसरा कदम: उत्तर खुद मत बताइए। दो उत्तर
  सामने रखिए, 24 और 16, और पूछिए कौन-सा सही है और क्यों। और ध्यान रखिए, कक्षा का शांत बच्चा भी बोले।
  अब आप यह तरीका अपने शब्दों में बताइए, फिर तीन बच्चों के साथ अभ्यास करेंगे।
learn_summary_hi:
  - "1. पहले बच्चे से पूछें: तुमने कैसे घटाया?"
  - "2. संख्या बंडल-तीली से बनवाएँ: 43 = 4 बंडल + 3 तीलियाँ"
  - "3. 3 में से 7 नहीं निकलतीं → एक बंडल खोलें → 13 तीलियाँ, 3 बंडल"
  - "4. 13 − 7 = 6, 3 − 2 = 1 → 16"
  - "5. उत्तर न बताएँ, दो उत्तरों की तुलना करवाएँ"
  - "6. शांत बच्चे को भी मौका दें"

scenario:
  intro_hi: "कक्षा 2। बोर्ड पर लिखा है: 43 − 27। आपके सामने तीन बच्चे हैं: रवि, प्रिया और अमन। तीनों ने अपना उत्तर बताया है। अब आप उनसे बात करें।"
  items:
    - {type: sub, a: 43, b: 27}
    - {type: sub, a: 61, b: 28}
    - {type: sub, a: 52, b: 17}
    - {type: sub, a: 74, b: 39}
  children:
    - {persona_id: ravi,  misconception: SUB_SMALLER_FROM_LARGER}     # 43−27 → 24
    - {persona_id: priya, misconception: SUB_BORROW_NO_DECREMENT}     # 43−27 → 26
    - {persona_id: aman,  misconception: SUB_WRITE_ZERO_WHEN_STUCK}   # 43−27 → 20
  guess_lexicon: {}

model_rehearsal:
  - speaker: teacher
    text_hi: "रवि, तुमने 43 में से 27 कैसे घटाया? मुझे एक-एक कदम बताओ।"
    acts: [ask_to_explain]
    addressed: ravi
    problem: null
  - speaker: teacher
    text_hi: "प्रिया, अच्छा सोचा तुमने। धीरे से बताओ, तुमने कैसे किया?"
    acts: [ask_to_explain, praise_effort]
    addressed: priya
    problem: null
  - speaker: teacher
    text_hi: "सब लोग देखो। ये रहे 4 बंडल और 3 खुली तीलियाँ, यानी 43। 3 तीलियों में से 7 कैसे निकालें? चलो, एक बंडल खोलते हैं।"
    acts: [concrete_representation]
    addressed: all
    problem: null
  - speaker: teacher
    text_hi: "अमन, रवि ने पहले 24 कहा था और अब तीलियाँ गिनकर 16 कह रहा है। कौन-सा सही है, और क्यों?"
    acts: [contrast_answers]
    addressed: aman
    problem: null
  - speaker: teacher
    text_hi: "प्रिया, तुमने 26 कहा था। बंडल खोलने के बाद कितने बंडल बचे थे? तो 26 सही है या 16?"
    acts: [contrast_answers]
    addressed: priya
    problem: null
  - speaker: teacher
    text_hi: "रवि, अब तुम बताओ, 24 और 16 में से कौन-सा ठीक है?"
    acts: [contrast_answers]
    addressed: ravi
    problem: null

peer_checklist:
  - "शिक्षक ने कम से कम एक बच्चे से पूछा कि उसने कैसे घटाया।"
  - "बच्चों ने बंडल-तीली (या चित्र) से संख्या बनाई।"
  - "बंडल खोलकर खुली तीलियाँ गिनवाई गईं।"
  - "शिक्षक ने सही उत्तर खुद नहीं बताया।"
  - "कम से कम एक शांत बच्चे ने बोलकर बताया।"
reflection_questions:
  - "बंडल खोलते समय बच्चों को सबसे ज़्यादा उलझन कहाँ हुई?"
  - "किस बच्चे ने अपना तरीका बताया, और उससे आपको क्या पता चला?"
approvals: []
```

---

## FILE: content-seed/messages_hi.yaml

```
# Teacher-facing message catalog. Keys referenced in spec/08. Placeholders in {braces}.
# audio: true → also sent as voice (narrator voice "abhyas") unless lite_mode. Keep sentences short and respectful (आप).
# Button titles must be ≤ 20 characters (WhatsApp limit).
# GENDER: texts below use feminine verb forms (most FLN teachers addressed are women). Teachers choose
# शिक्षिका/शिक्षक at onboarding (teacher.address_form = f|m). For every key whose text has gendered verbs
# (रही हैं, चाहती, थीं, पहुँचीं, बताऊँगी, गई, पाई, सकती …), the agent adds a `text_m` variant
# (रहे हैं, चाहते, थे, पहुँचे, बताऊँगा, गया …). messages.py picks text_m when address_form == "m".
# A test asserts every key containing a feminine marker has text_m.

# ── Onboarding ───────────────────────────────────────────────
welcome:
  text: "नमस्ते! मैं अभ्यास हूँ — आपकी अभ्यास-साथी। हर हफ्ते लगभग 15 मिनट में हम कक्षा का एक तरीका सीखेंगे, और तीन बच्चों के साथ बोलकर उसका अभ्यास करेंगे।"
  audio: true
consent_service:
  text: "शुरू करने से पहले: आपकी आवाज़ को लिखित रूप में बदलकर आवाज़ तुरंत मिटा दी जाती है। आपके अंक केवल आपको दिखेंगे, जब तक आप स्वयं ARP के साथ साझा करने की अनुमति न दें। आप कभी भी 'मेरा डेटा हटाएँ' लिखकर सब कुछ मिटा सकती हैं। क्या आप सहमत हैं?"
  audio: true
consent_details:
  text: "हम क्या रखते हैं: आपका नाम, कक्षा, अनुभव, आपकी बातों का लिखित रूप और अभ्यास के अंक। हम क्या नहीं रखते: आपकी आवाज़ की रिकॉर्डिंग, बच्चों की कोई जानकारी। ट्रेनर (DIET/SCERT) को केवल 10 या उससे ज़्यादा शिक्षकों के समूह के कुल आँकड़े दिखते हैं, किसी का नाम नहीं।"
  audio: false
consent_declined:
  text: "कोई बात नहीं। जब भी आप शुरू करना चाहें, 'नमस्ते' लिखकर भेजें।"
  audio: false
ask_join_code:
  text: "आपके ARP ने जो कोड दिया है, वह भेजें। कोड नहीं है तो 'नहीं' लिखें।"
  audio: false
join_code_invalid:
  text: "यह कोड नहीं मिला। कृपया फिर से भेजें, या 'नहीं' लिखें।"
  audio: false
ask_name:
  text: "आपका नाम क्या है?"
  audio: true
ask_address_form:
  text: "आपको कैसे संबोधित करें?"
  audio: false
btn_female: {text: "शिक्षिका", audio: false}
btn_male: {text: "शिक्षक", audio: false}
ask_experience:
  text: "{name} जी, आप कितने साल से पढ़ा रही हैं?"
  audio: false
ask_classes:
  text: "आप इस साल कौन-सी कक्षा पढ़ाती हैं?"
  audio: false
consent_share_scores:
  text: "क्या आप चाहती हैं कि आपके ARP आपके अभ्यास के अंक देख सकें, ताकि वे कक्षा-भ्रमण में आपकी मदद कर सकें? आप इसे कभी भी बदल सकती हैं।"
  audio: false
placement_intro:
  text: "चलिए, एक छोटा-सा अभ्यास करते हैं। यह कोई परीक्षा नहीं है। बोर्ड पर लिखा है: 52 − 17। कक्षा 2 का रवि कहता है: '45!' आप रवि से वैसे ही बात कीजिए जैसे कक्षा में करती हैं — बोलकर या लिखकर।"
  audio: true
placement_done:
  text: "बहुत अच्छा! अब मुझे पता है कि आपके लिए कहाँ से शुरू करें।"
  audio: true
ready_first_move:
  text: "आपका पहला तरीका है: {move_title}। चलिए शुरू करते हैं!"
  audio: true

# ── Weekly loop ───────────────────────────────────────────────
learn_intro:
  text: "इस हफ्ते का तरीका: {move_title}। पहले 2 मिनट की यह आवाज़ सुनिए। मुख्य बातें नीचे लिखी हैं:"
  audio: false
explain_back_prompt:
  text: "अब 1 मिनट में अपने शब्दों में बताइए: इस तरीके में सबसे ज़रूरी क्या है? बोलकर या लिखकर भेजें।"
  audio: true
explain_back_reply:
  text: "धन्यवाद! आपने {covered} में से {total} मुख्य बातें कहीं।"
  audio: true
explain_back_missing:
  text: "एक बात और याद रखें: {point}"
  audio: true
explain_back_misconception:
  text: "ध्यान दें: {note}"
  audio: false
model_offer:
  text: "क्या आप सुनना चाहेंगी कि एक शिक्षिका इन्हीं तीन बच्चों के साथ यह तरीका कैसे करती हैं? (लगभग 1 मिनट)"
  audio: false
model_header:
  text: "आदर्श अभ्यास:"
  audio: false
rehearse_intro:
  text: "{scene_intro} जब तैयार हों, बच्चों से बोलना शुरू करें। किसी बच्चे का नाम लेकर बात करें। खत्म करने के लिए 'बस' बोलें।"
  audio: true
child_silent:
  text: "({name} चुप है और नीचे देख रही है।)"
  audio: false
thinking:
  text: "बच्चे सोच रहे हैं…"
  audio: false
scene_turn_limit:
  text: "अभ्यास का समय पूरा हुआ।"
  audio: false
scene_all_correct:
  text: "वाह! तीनों बच्चे समझ गए।"
  audio: true
feedback_header:
  text: "आपके अभ्यास पर सुझाव:"
  audio: false
feedback_body:
  text: "👍 {strength}\n🔁 {change}\n🗣️ अगली बार ऐसे कहकर देखें: \"{exact_words}\""
  audio: true
feedback_trajectory:
  text: "बच्चों में बदलाव: {trajectory}"
  audio: false
coach_low_conf_prefix:
  text: "(यह सुझाव एक विशेषज्ञ भी देखेंगे।)"
  audio: false
realism_prompt:
  text: "ये बच्चे असली कक्षा के बच्चों जैसे लगे? 1 (बिल्कुल नहीं) से 5 (बिल्कुल वैसे ही) चुनें।"
  audio: false
retry_limit:
  text: "इस हफ्ते के 3 अभ्यास पूरे हो गए। अब कक्षा में आज़माने की बारी है!"
  audio: false
try_in_class:
  text: "अब यह तरीका अपनी कक्षा में आज़माइए। किसी साथी शिक्षक से 5 मिनट देखने को कहें और यह सूची भरवाएँ:"
  audio: true
try_in_class_reflect:
  text: "या खुद इन 2 सवालों के जवाब दें:"
  audio: false
peer_item:
  text: "साथी की सूची ({i}/{n}): {item}"
  audio: false
reflect_q:
  text: "सवाल {i}: {question}"
  audio: true
week_done:
  text: "शाबाश {name} जी! इस हफ्ते आप '{level_name}' तक पहुँचीं। अगला तरीका: {next_move_title}।"
  audio: true
evidence_level_1: {text: "अभ्यास किया", audio: false}
evidence_level_2: {text: "स्वयं बताया", audio: false}
evidence_level_3: {text: "साथी ने देखा", audio: false}
evidence_level_4: {text: "ARP ने देखा", audio: false}
evidence_level_5: {text: "बच्चों में सुधार", audio: false}
resume_prompt:
  text: "आप '{state_name}' पर थीं। आगे बढ़ें?"
  audio: false
weekly_move:
  text: "नमस्ते {name} जी! इस हफ्ते का नया तरीका तैयार है: {move_title}। शुरू करें?"
  audio: true
reminder:
  text: "{name} जी, आपका इस हफ्ते का अभ्यास बाकी है। 10 मिनट निकालें?"
  audio: false

# ── Ask any time ─────────────────────────────────────────────
ask_prompt:
  text: "अपना सवाल बोलकर या लिखकर भेजें।"
  audio: false
ask_clarify_prefix:
  text: "एक बात बताइए:"
  audio: false
ask_source_line:
  text: "स्रोत: {source}{page_part}"
  audio: false
ask_try_this_week:
  text: "इस हफ्ते आज़माएँ: {tip}"
  audio: false
ask_escalated:
  text: "अच्छा सवाल है। इसका पक्का जवाब मैं आपके ARP से पूछकर बताती हूँ।"
  audio: true
ask_out_of_scope:
  text: "माफ़ कीजिए, मैं कक्षा 1-3 की पढ़ाई और कक्षा से जुड़े सवालों में ही मदद कर सकती हूँ।"
  audio: false
ask_admin:
  text: "यह जानकारी आपके BEO या ARP कार्यालय से मिलेगी। मैंने आपका सवाल ARP तक पहुँचा दिया है।"
  audio: false
ask_resume:
  text: "चलिए, जहाँ थे वहीं से आगे बढ़ते हैं।"
  audio: false
followup_question:
  text: "{name} जी, आपने '{topic}' के बारे में पूछा था। क्या सुझाव काम आया?"
  audio: false
arp_answer_delivered:
  text: "आपके सवाल का जवाब आपके ARP ने भेजा है: {answer}"
  audio: true

# ── System / errors / settings ───────────────────────────────
help_menu:
  text: "आप क्या करना चाहेंगी?"
  audio: false
stt_failed:
  text: "आवाज़ साफ़ नहीं आई। कृपया फिर से बोलें या लिखकर भेजें।"
  audio: false
stt_confirm:
  text: "मैंने सुना: \"{text}\" — सही है?"
  audio: false
audio_too_long:
  text: "यह संदेश बहुत लंबा है। कृपया 1 मिनट से छोटा भेजें।"
  audio: false
unsupported_type:
  text: "मैं अभी केवल आवाज़ और लिखे संदेश समझ सकती हूँ।"
  audio: false
unclear:
  text: "माफ़ कीजिए, मैं समझ नहीं पाई। 'मदद' लिखकर विकल्प देखें।"
  audio: false
lite_on:
  text: "लाइट मोड चालू: अब केवल लिखे संदेश आएँगे, आवाज़ नहीं। इससे डेटा बचेगा।"
  audio: false
lite_off:
  text: "लाइट मोड बंद: अब आवाज़ वाले संदेश भी आएँगे।"
  audio: false
progress_summary:
  text: "आपकी प्रगति: {n_done} तरीके पूरे। {lines}"
  audio: false
consent_menu:
  text: "ARP के साथ अंक साझा करना: {share_state}। बदलना चाहेंगी?"
  audio: false
delete_confirm:
  text: "क्या आप सच में अपना सारा डेटा मिटाना चाहती हैं? यह वापस नहीं आएगा।"
  audio: false
data_deleted:
  text: "आपका सारा डेटा मिटा दिया गया है। धन्यवाद। फिर से शुरू करने के लिए 'नमस्ते' भेजें।"
  audio: false
rate_limited:
  text: "बहुत सारे संदेश आ गए हैं, थोड़ी देर बाद फिर कोशिश करें।"
  audio: false

# ── Buttons (≤ 20 chars) ─────────────────────────────────────
btn_agree: {text: "सहमत हूँ", audio: false}
btn_more: {text: "और जानें", audio: false}
btn_decline: {text: "नहीं", audio: false}
btn_yes: {text: "हाँ", audio: false}
btn_no: {text: "नहीं", audio: false}
btn_understood: {text: "समझ गई, आगे", audio: false}
btn_replay: {text: "फिर से सुनें", audio: false}
btn_skip: {text: "छोड़ें", audio: false}
btn_listen: {text: "सुनें", audio: false}
btn_retry: {text: "फिर से अभ्यास", audio: false}
btn_continue: {text: "आगे बढ़ें", audio: false}
btn_peer: {text: "साथी ने देखा", audio: false}
btn_self: {text: "खुद बताऊँगी", audio: false}
btn_later: {text: "बाद में", audio: false}
btn_next_move: {text: "अगला तरीका", audio: false}
btn_progress: {text: "मेरी प्रगति", audio: false}
btn_ask: {text: "प्रश्न पूछें", audio: false}
btn_confirm_ok: {text: "हाँ, सही है", audio: false}
btn_confirm_redo: {text: "फिर से बोलूँगी", audio: false}
btn_restart: {text: "शुरू से", audio: false}
btn_not_now: {text: "अभी नहीं", audio: false}
btn_lite: {text: "लाइट मोड", audio: false}

# ── Web UI labels ────────────────────────────────────────────
ui_app_name: {text: "अभ्यास", audio: false}
ui_hold_to_talk: {text: "बोलने के लिए दबाकर रखें", audio: false}
ui_type_here: {text: "यहाँ लिखें…", audio: false}
ui_type_instead: {text: "बोलने की जगह लिखें", audio: false}
ui_offline_banner: {text: "इंटरनेट नहीं है — संदेश भेजे जाने के लिए रखे गए हैं", audio: false}
ui_slow_banner: {text: "नेटवर्क धीमा है — लाइट मोड चालू करें?", audio: false}
ui_mic_denied: {text: "माइक की अनुमति नहीं मिली। ब्राउज़र की सेटिंग में माइक चालू करें, या लिखकर भेजें।", audio: false}
ui_demo_banner: {text: "डेमो डेटा — वास्तविक शिक्षक नहीं", audio: false}
ui_in_review: {text: "समीक्षा में", audio: false}
ui_suppressed: {text: "समूह छोटा है (n<10) — गोपनीयता हेतु छिपाया गया", audio: false}
ui_samples_title: {text: "नमूना आवाज़ें (मूल्यांकन हेतु)", audio: false}
ui_logout: {text: "लॉग आउट", audio: false}
ui_delete_data: {text: "मेरा डेटा हटाएँ", audio: false}

# ── Speaker labels ───────────────────────────────────────────
speaker_abhyas: {text: "अभ्यास", audio: false}
speaker_coach: {text: "कोच", audio: false}
speaker_model_teacher: {text: "आदर्श शिक्षिका", audio: false}
speaker_teacher: {text: "आप", audio: false}

# ── State names (for resume prompt) ──────────────────────────
state_LEARN: {text: "सीखना", audio: false}
state_EXPLAIN_BACK: {text: "अपने शब्दों में बताना", audio: false}
state_MODEL: {text: "आदर्श अभ्यास सुनना", audio: false}
state_REHEARSE_INTRO: {text: "बच्चों के साथ अभ्यास", audio: false}
state_REHEARSE: {text: "बच्चों के साथ अभ्यास", audio: false}
state_FEEDBACK: {text: "सुझाव", audio: false}
state_TRY_IN_CLASS: {text: "कक्षा में आज़माना", audio: false}
state_REFLECT_PEER: {text: "साथी की सूची", audio: false}
state_REFLECT_SELF: {text: "अपने अनुभव बताना", audio: false}
```

---

## FILE: content-seed/whatsapp_templates.yaml

```
# WhatsApp message templates (category: UTILITY, language: hi). Submit in Meta WhatsApp Manager (HUMAN INPUT H5).
# Variables are positional {{1}}, {{2}} as Meta requires. Keep wording factual/transactional (utility, not marketing),
# otherwise Meta may re-categorise as MARKETING (higher cost). Set approved: true once Meta approves.
templates:
  - name: abhyas_weekly_move
    key: tpl_weekly_move
    category: UTILITY
    language: hi
    body: "नमस्ते {{1}} जी, अभ्यास में आपका इस हफ्ते का तरीका तैयार है: {{2}}। शुरू करने के लिए 'शुरू' लिखें।"
    example: ["सुनीता", "हासिल वाला घटाव: बंडल खोलकर"]
    buttons: [{type: QUICK_REPLY, text: "शुरू"}]
    approved: false
  - name: abhyas_reminder
    key: tpl_reminder
    category: UTILITY
    language: hi
    body: "{{1}} जी, अभ्यास में आपका इस हफ्ते का अभ्यास '{{2}}' अभी बाकी है। जारी रखने के लिए 'आगे' लिखें।"
    example: ["सुनीता", "बच्चों के साथ अभ्यास"]
    buttons: [{type: QUICK_REPLY, text: "आगे"}]
    approved: false
  - name: abhyas_followup_question
    key: tpl_followup_question
    category: UTILITY
    language: hi
    body: "{{1}} जी, आपने अभ्यास में '{{2}}' के बारे में पूछा था। क्या दिया गया सुझाव आपकी कक्षा में काम आया?"
    example: ["सुनीता", "दो कक्षाएँ साथ में पढ़ाना"]
    buttons: [{type: QUICK_REPLY, text: "हाँ"}, {type: QUICK_REPLY, text: "नहीं"}, {type: QUICK_REPLY, text: "अभी नहीं"}]
    approved: false
  - name: abhyas_try_in_class_followup
    key: tpl_try_in_class_followup
    category: UTILITY
    language: hi
    body: "{{1}} जी, क्या आपने '{{2}}' वाला तरीका अपनी कक्षा में आज़माया? जवाब देने के लिए नीचे चुनें।"
    example: ["सुनीता", "हासिल वाला घटाव"]
    buttons: [{type: QUICK_REPLY, text: "साथी ने देखा"}, {type: QUICK_REPLY, text: "खुद बताऊँगी"}, {type: QUICK_REPLY, text: "बाद में"}]
    approved: false
  - name: abhyas_arp_digest
    key: tpl_arp_digest
    category: UTILITY
    language: hi
    body: "नमस्ते {{1}} जी, संकुल {{2}} की इस हफ्ते की अभ्यास रिपोर्ट तैयार है: {{3}} शिक्षकों ने अभ्यास किया, {{4}} प्रश्न आपके उत्तर की प्रतीक्षा में हैं। रिपोर्ट देखें: {{5}}"
    example: ["राजेश", "KNP-C01", "9", "2", "https://example.org/arp"]
    buttons: []
    approved: false
  - name: abhyas_arp_answer
    key: tpl_arp_answer
    category: UTILITY
    language: hi
    body: "{{1}} जी, आपके प्रश्न का उत्तर आपके ARP ने भेजा है: {{2}}"
    example: ["सुनीता", "बहु-कक्षा में पहले बड़ी कक्षा को अभ्यास देकर छोटी कक्षा के साथ बंडल वाली गतिविधि करें।"]
    buttons: []
    approved: false
```

---

## FILE: content-seed/eval_samples.yaml

```
# Evaluator sample inputs (3–5 required by the organisers). Rendered to audio by `make samples`
# (TTS adult teacher voice, or real recordings in eval/samples/recorded/<id>.ogg — preferred, HUMAN INPUT H15).
# Shown as tappable chips in the teacher chat in demo mode, and listed in README with expected behaviour.
samples:
  - id: s1_ask_ravi
    step: REHEARSE (move NUM_SUB_REGROUP_BUNDLES, any demo teacher in rehearsal)
    text_hi: "रवि, तुमने 43 में से 27 कैसे घटाया? मुझे एक-एक कदम बताओ।"
    expect: "Act tagged ask_to_explain → Ravi moves to CAN_EXPLAIN and explains his bug: '3 में से 7 नहीं घटता, तो 7 में से 3 घटाया… 24!' (never says 16)."
  - id: s2_bundles_all
    step: REHEARSE
    text_hi: "सब लोग देखो, ये 4 बंडल और 3 खुली तीलियाँ हैं। 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलते हैं। अब कितनी तीलियाँ हुईं?"
    expect: "concrete_representation to the whole class → all children reach PARTIAL; Ravi answers 16 hesitantly; Aman may interject off-topic."
  - id: s3_tell_answer_hinglish
    step: REHEARSE
    text_hi: "Aman, sahi answer 16 hai, yaad rakho."
    expect: "Hinglish handled. tell_answer → Aman parrots '16…?' without understanding (state unchanged). If the evaluator then says 'अमन, अब 61 में से 28 करो', Aman relapses to his bug (40). Coach later scores 'no telling' = 0 and suggests contrasting answers."
  - id: s4_explain_back
    step: EXPLAIN_BACK
    text_hi: "इस तरीके में सबसे पहले बच्चे से पूछना है कि उसने कैसे घटाया। फिर दस-दस तीलियों के बंडल से संख्या बनवानी है, और जब इकाई में कम हो तो एक बंडल खोलना है। उत्तर खुद नहीं बताना।"
    expect: "Fidelity: kp1, kp2, kp3, kp5 covered with quotes; kp4 missing → reply names the one missing point."
  - id: s5_question_multigrade
    step: any (ASK)
    text_hi: "मेरी कक्षा में पहली और दूसरी कक्षा के बच्चे साथ बैठते हैं। हासिल वाला घटाव दोनों को एक साथ कैसे कराऊँ?"
    expect: "Classified classroom_management → answer ≤ 80 words citing a source chunk + one thing to try this week; if no good chunk, escalated to ARP (visible on arp.demo)."
```
