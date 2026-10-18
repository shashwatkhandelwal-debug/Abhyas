# PROGRESS.md — Abhyas Build Progress

## 1. Understanding

- **What we are building**: Abhyas is a voice-first practice partner for government primary school teachers (FLN, Classes 1–3) in Hindi, delivered over WhatsApp and an equivalent lightweight web PWA. Each week a teacher spends ~15 minutes practicing one high-leverage pedagogical move.
- **The Core Weekly Loop**: Teachers progress through structured steps: **LEARN** (≤2-min voice note + text summary) → **EXPLAIN_BACK** (≤1-min voice note scored against key points) → **MODEL** (demonstration by a model teacher) → **REHEARSE** (interactive role-play with 3 simulated children) → **FEEDBACK** (rubric-scored strength, change, exact words to try + retry option) → **TRY_IN_CLASS** (peer 5-minute checklist or self-reflection) → **DONE** (updates adoption evidence ladder). Free-form questions can be asked at any time (**ASK** interrupt flow).
- **The Core Rule (Core IP)**: Simulated children's answers, misconceptions, internal states, and transitions are **strictly computed by a pure, deterministic Python rule engine** (`backend/app/rule_engine/`). The LLM **never** decides what a child answers or whether a child improves. Claude only voices the line in natural Hindi, subject to strict output token/number guards that block any line not derived from the rule engine output.
- **Pedagogical Underpinnings & Transfer**: Based on procedural bug research (Brown & Burton, 1978; VanLehn, 1990). Telling the child the answer triggers a parrot response, followed by a guaranteed relapse on the next item, demonstrating the limits of didactic telling vs. conceptual scaffolding.
- **The Architectural Layers**:
  1. *Input*: Voice notes (OGG/Opus, WebM), text, quick-reply buttons via WhatsApp Cloud API or Web PWA.
  2. *Context*: Session state machine, move card, rubric, child states, teacher history, retrieved guide chunks.
  3. *Reasoning (Claude)*: `intent_router`, `act_tagger`, `child_voice`, `coach`, `fidelity_checker`, `guide_answerer` (runtime) + build-time content generation/review roles.
  4. *Guardrails*: Pydantic JSON schemas, token/number checks, transcript quote-verification, sources subset check, length/tone checks, confidence thresholds routing to human review.
  5. *Evaluation*: Automated test suites, quadratic-weighted Cohen's kappa harness, p95 latency logs, guard failure logs, realism ratings, 5-tier evidence ladder.
  6. *Output*: Natural TTS voice replies, text fallback, quick-reply buttons, ARP digest, DIET/SCERT trainer view.
- **Data & Privacy by Design**:
  - Raw audio is **never stored on disk or database**; converted in memory and discarded immediately post-transcription.
  - All teacher personal data is private by default (`consent_share_scores=false`). No individual teacher scores flow upward without explicit consent.
  - Upward trainer reporting (DIET/SCERT) strictly enforces aggregation suppression for any cohort/batch where $n < 10$.
  - Phone numbers are stored only as salted SHA-256 hashes for lookup, with encrypted raw numbers segregated in `teacher_contact` for WhatsApp dispatch.
- **Speech & Channel Integration**: Default hosted speech powered by Sarvam AI (`saaras:v4` STT, `bulbul:v3` TTS with pitch shifting for distinct child voices), with full mock fallbacks so the entire application runs end-to-end without external API keys. Direct Meta WhatsApp Cloud API integration with 24-hour service window enforcement (switching to approved utility templates outside the window).
- **Web App & Low-Connectivity Design**: Server-rendered Jinja2 + vanilla JS + single CSS file (<150 KB load). PWA with offline IndexedDB outbox queue, background sync retry, and a text-only "Light Mode" (लाइट मोड) designed for low-cost Android smartphones on patchy 2G/3G connections.
- **Hard Deadlines**:
  - Target internal feature freeze: **31 October 2026, 18:00 IST**.
  - Final build-stage submission: **1 November 2026, 23:59 IST**.
  - Post-submission: No further commits to the frozen submission tag; evaluation runs strictly on the frozen build.
- **What Evaluators Will Test**:
  - Live hosted web application on a mobile viewport (~1 hour hands-on session).
  - Test credentials across all 5 roles: `teacher` (new, mid-week, experienced), `arp`, `trainer`, `coach`, `admin`.
  - 3–5 pre-recorded sample voice inputs (chips in chat) to test voice loops without needing to speak Hindi.
  - Offline / low-connectivity degradation (outbox queuing, offline checklist, lite mode).
  - Validation of the core IP claims: Ravi worked example (`52 - 17 = 45`), relapse after tell-answer, quote-backed feedback, and $n < 10$ suppression on trainer dashboards.

---

## 2. Scaffold vs Spec Gap

A comprehensive audit comparing the current scaffold against `spec/02_architecture.md` §2.4 and `spec/14_tasks.md` T01 reveals the following files and folders that must be moved, renamed, deleted, or rewritten:

### Files / Folders to Delete
- `ARCHITECTURE.md` (root) — Superseeded by `spec/` build pack; to be deleted.
- `Abhyas_ARCHITECTURE.md` (root) — Redundant legacy specification; to be deleted.
- `Abhyas_Technical_Design.docx` (root) — Legacy Word document; to be deleted.
- `review-console/` (entire directory) — Review console moves into `backend/app/web/` (`templates/` and `review.py`).
- `trainer-view/` (entire directory) — Trainer view moves into `backend/app/web/` (`templates/` and `trainer.py`).
- `infra/Dockerfile.backend` — Consolidated into root `Dockerfile`.
- `infra/Dockerfile.worker` — Background tasks run inside FastAPI via `AsyncIOScheduler` / `BackgroundTasks`; separate worker container deleted.
- `infra/init-db.sql` — Replaced by standard Alembic migrations.

### Dependencies & Configuration to Remove / Replace
- `arq` and `redis` dependencies in `pyproject.toml` — Spec explicitly states: "No Redis. Remove arq/redis deps from the scaffold. Single service using FastAPI BackgroundTasks and AsyncIOScheduler backed by DB."
- Current `backend/alembic.ini` — Move to repo root `alembic.ini`.
- Current `backend/app/config.py` — Complete rewrite to implement all configuration keys and thresholds specified across `spec/` and `.env.example` (no magic numbers).
- Current `backend/app/db/models.py` — Rewrite to match the complete DDL in `spec/03_data_model.md` §3.2 (adding `batch`, `cluster`, `app_user`, `teacher_contact`, `invite_code`, `arp_assignment`, `consent_log`, `content_release`, `bug_rule`, `move_path`, `scene`, `message`, `realism_rating`, `calibration_label`, `arp_observation`, `scheduled_job`, `template_send`, `llm_call`, `tts_cache`, `agg_module_batch`).

### Files / Folders to Move or Reorganize
- `content/rules/*.py` (`math_bugs.py`, `reading_bugs.py`) → Move to `backend/app/rule_engine/bugs/` (`math.py`, `reading.py`, `registry.py`, `akshar.py`).
- Seed content from `content-seed/`:
  - `content-seed/moves/*.yaml` → `content/moves/`
  - `content-seed/personas/*.yaml` → `content/personas/`
  - `content-seed/messages_hi.yaml` → `content/messages_hi.yaml`
  - `content-seed/whatsapp_templates.yaml` → `content/whatsapp_templates.yaml`
  - `content-seed/eval_samples.yaml` → `eval/samples/samples.yaml`

### New Modules & Packages Required by Spec §2.4
- `backend/app/deps.py` — Dependency injection for DB session, current user, provider adapters.
- `backend/app/logging.py` — Structured JSON logging with request IDs and PII redaction.
- `backend/app/core/` — `conversation.py` (channel-agnostic brain), `intents.py`, `messages.py`, `types.py` (`InboundMessage`, `OutboundMessage`, `Button`).
- `backend/app/channels/` — `base.py` (Channel protocol), `web.py` (polling API + state store), `whatsapp/` (`client.py`, `webhook.py`, `security.py`, `templates.py`, `media.py`).
- `backend/app/rehearsal/` — `scene_runner.py` (orchestrates tagger → engine → voice → guards → TTS), `scene_store.py`.
- `backend/app/llm/hindi_numbers.py` — Number extractor & converter for Arabic digits, Devanagari numerals, and Hindi words (0–100+).
- `backend/app/privacy/` — `consent.py`, `retention.py`, `hashing.py` (salted SHA-256 and Fernet encryption).
- `backend/app/auth/` — `passwords.py`, `sessions.py`, `guards.py` (role-based route guards).
- `backend/app/web/` — Unified web layer: routers (`teacher.py`, `arp.py`, `trainer.py`, `review.py`, `admin.py`, `api.py`), Jinja2 templates, and static assets (`chat.js`, `recorder.js`, `sw.js`, `manifest.json`, `app.css`).
- Root configuration: `Makefile`, `LICENSE` (MIT), `.pre-commit-config.yaml`, `.gitleaks.toml`, `.github/workflows/ci.yml`.

---

## 3. Task Plan (T01–T52)

- [x] **T01 Repo restructure** · Priority: P0 · Finish-by: 12 Oct
- [x] **T02 Config** · Priority: P0 · Finish-by: 12 Oct
- [x] **T03 Database** · Priority: P0 · Finish-by: 13 Oct
- [x] **T04 Content models & seed content** · Priority: P0 · Finish-by: 13 Oct
- [x] **T05 Hindi utilities** · Priority: P0 · Finish-by: 13 Oct (completed via Lane A)
- [x] **T06 Bug rules** · Priority: P0 · Finish-by: 14 Oct (completed via Lane A)
- [x] **T07 Rule engine** · Priority: P0 · Finish-by: 15 Oct (completed via Lane A)
- [x] **T08 LLM client + MockLLM** · Priority: P0 · Finish-by: 14 Oct (completed via Lane B)
- [x] **T09 Guards** · Priority: P0 · Finish-by: 15 Oct (completed via Lane A)
- [x] **T10 act_tagger** · Priority: P0 · Finish-by: 16 Oct (completed via Lane A)
- [x] **T11 child_voice** · Priority: P0 · Finish-by: 16 Oct (completed via Lane A)
- [x] **T12 coach** · Priority: P0 · Finish-by: 17 Oct (completed via Lane A)
- [x] **T13 fidelity_checker** · Priority: P0 · Finish-by: 17 Oct (completed via Lane A)
- [x] **T14 intent_router, question_classifier, guide_answerer** · Priority: P1 · Finish-by: 20 Oct (completed via Lane A)
- [x] **T15 Audio utils** · Priority: P0 · Finish-by: 14 Oct (completed via Lane B)
- [x] **T16 STT** · Priority: P0 · Finish-by: 16 Oct (completed via Lane B)
- [x] **T17 TTS + voices** · Priority: P0 · Finish-by: 17 Oct (completed via Lane B)
- [x] **T18 Core service skeleton** · Priority: P0 · Finish-by: 16 Oct (completed via Lane B)
- [x] **T19 SceneRunner** · Priority: P0 · Finish-by: 18 Oct (completed via Lane B)
- [x] **T20 Onboarding & Weekly State Machine** · Priority: P0 · Finish-by: 19 Oct (completed via Lane B)
- [x] **T21 Weekly loop + evidence** · Priority: P0 · Finish-by: 20 Oct (completed via Lane B)
- [ ] **T22 Intents, ASK, retrieval** · Priority: P1 · Finish-by: 21 Oct
- [ ] **T23 Move path** · Priority: P1 · Finish-by: 21 Oct
- [ ] **T24 Scheduler & jobs** · Priority: P1 · Finish-by: 22 Oct
- [x] **T25 Auth & demo users** · Priority: P0 · Finish-by: 17 Oct (completed via Lane C)
- [ ] **T26 Web channel API** · Priority: P0 · Finish-by: 18 Oct
- [ ] **T27 Teacher chat PWA** · Priority: P0 · Finish-by: 20 Oct
- [x] **T28 WhatsApp channel** · Priority: P0 code 21 Oct / P1 live · Finish-by: 21 Oct (PR #14, CI green)
- [x] **T29 Progress, consent, delete** · Priority: P1 · Finish-by: 22 Oct (completed via Lane C)
- [x] **T30 First hosted deploy** · Priority: P0 · Finish-by: 18 Oct (completed 13 Oct via Lane C)
- [x] **T31 Demo data** · Priority: P1 · Finish-by: 22 Oct (completed via Lane C)
- [ ] **T32 ARP digest** · Priority: P1 · Finish-by: 24 Oct
- [ ] **T33 Trainer view + aggregates** · Priority: P1 · Finish-by: 24 Oct
- [ ] **T34 Coach review console** · Priority: P1 · Finish-by: 25 Oct
- [ ] **T35 Admin** · Priority: P1 · Finish-by: 25 Oct
- [ ] **T36 Sankul mode** · Priority: P2 · Finish-by: 28 Oct
- [x] **T37 User-testing kit** · Priority: P0 · Finish-by: 14 Oct (completed 11 Oct via Lane D)
- [ ] **T38 Golden fixtures** · Priority: P0 · Finish-by: 17 Oct
- [ ] **T39 Evaluator samples** · Priority: P0 · Finish-by: 22 Oct
- [x] **T40 Source ingestion** · Priority: P1 · Finish-by: 23 Oct (completed 17 Oct)
- [ ] **T41 Latency benchmark** · Priority: P0 · Finish-by: 24 Oct (re-run 30 Oct)
- [ ] **T42 Kappa harness** · Priority: P1 · Finish-by: 27 Oct
- [ ] **T43 Guard report** · Priority: P1 · Finish-by: 29 Oct
- [ ] **T44 Realism report + blind pairs** · Priority: P2 · Finish-by: 29 Oct
- [ ] **T45 Content pipeline (generate/review/publish)** · Priority: P2 · Finish-by: 29 Oct
- [ ] **T46 Round-1 fixes** · Priority: P0 · Finish-by: 28 Oct
- [ ] **T47 Low-network verification** · Priority: P0 · Finish-by: 28 Oct
- [ ] **T48 Security pass** · Priority: P0 · Finish-by: 29 Oct
- [ ] **T49 Docs** · Priority: P0 · Finish-by: 30 Oct
- [ ] **T50 Hosted smoke tests** · Priority: P0 · Finish-by: 30 Oct
- [ ] **T51 GIF & screenshots** · Priority: P1 · Finish-by: 30 Oct
- [ ] **T52 Freeze** · Priority: P0 · Finish-by: 31 Oct 18:00 IST

---

## 4. Blocked on Humans (H1–H17)

All items from `spec/15_human_inputs.md` are currently open:

- [ ] **H1: Anthropic API key** — Hackathon Claude credits (USD 500). Owner: Shashwat. Needed by: 14 Oct. Fallback: MockLLM; live tests skipped. (Status: OPEN)
- [ ] **H2: Sarvam AI API key** — STT/TTS provider credentials. Owner: Vedant. Needed by: 15 Oct. Fallback: Mock STT/TTS; text box in web chat. (Status: OPEN)
- [ ] **H3: Choice of 3 child voices + narrator/coach/model-teacher voices** — Listen to audition files in `eval/voices/`. Owner: Vedant. Needed by: 18 Oct. Fallback: Defaults in `spec/06_speech.md` §6.3. (Status: OPEN)
- [ ] **H4: Meta WhatsApp setup** — Developer app, test number, phone number ID, permanent token, app secret, verify token, 5 recipient numbers. Owner: Shashwat. Needed by: 19 Oct. Fallback: WhatsApp channel tested with mocked Graph API. (Status: OPEN)
- [ ] **H5: WhatsApp template approval** — Submit templates from `content/whatsapp_templates.yaml` in Meta Manager. Owner: Shashwat. Needed by: 20 Oct. Fallback: Templates marked `approved: false`; outside-window sends skipped and logged. (Status: OPEN)
- [ ] **H6: Render account + Supabase project** — Cloud deployment & billing setup (Render Starter plan). Owner: Shashwat. Needed by: 17 Oct. Fallback: Local Docker environment. (Status: OPEN)
- [ ] **H7: Official source PDFs** — NIPUN Bharat guidelines, UP Shikshak Sandarshika (Ganit C2, Bhasha C1), NCERT Vidya Pravesh. Owner: Divyansh. Needed by: 20 Oct. Fallback: Seed chunks from `seed_from_moves.jsonl`; `module_ref.verified: false`. (Status: OPEN)
- [ ] **H8: FLN coach / education mentor review** — Review of 4 seed moves (key points, rubric, scenario realism, bug list). Owner: Divyansh + team. Needed by: 22 Oct. Fallback: Moves remain `in_review`; demo serves them with "समीक्षा में" badge. (Status: OPEN)
- [ ] **H9: 2 coaches for blind double-coding** — Double-code ≥ 20 rehearsal transcripts for kappa calibration. Owner: Divyansh. Needed by: 29 Oct. Fallback: Kappa report notes sample size and limitation honestly. (Status: OPEN)
- [ ] **H10: 5–10 teachers for user testing** — Two rounds (Round 1 by 24 Oct, Round 2 by 29 Oct) with informed consent. Owner: Divyansh. Needed by: 24 / 29 Oct. Fallback: Cannot be faked; report actual findings. (Status: OPEN)
- [ ] **H11: Pre-recorded learn scripts** — Optional audio in real teacher's voice (`content/audio/learn_<move>.ogg`). Owner: Any team member. Needed by: 25 Oct. Fallback: TTS narrator. (Status: OPEN)
- [ ] **H12: Evaluator GitHub IDs** — Organiser-provided handles for evaluator repo access. Owner: Shashwat. Needed by: 31 Oct. Fallback: Public GitHub repository. (Status: OPEN)
- [ ] **H13: Demo passwords** — Rotate `DEMO_PASSWORD` on Render for submission form. Owner: Shashwat. Needed by: 31 Oct. Fallback: Dev default (never used in production). (Status: OPEN)
- [ ] **H14: Demo video & presentation deck** — 3-minute YouTube recording and PPTX deck. Owner: Whole team. Needed by: 31 Oct. Fallback: Agent provides script, slide outlines, screenshots, and diagrams. (Status: OPEN)
- [ ] **H15: Sample voice notes** — Native Hindi recordings of `eval/samples/samples.yaml` lines. Owner: Any team member. Needed by: 22 Oct. Fallback: TTS-synthesized audio samples. (Status: OPEN)
- [ ] **H16: Voyage AI key** — Optional dense vector retrieval embeddings. Owner: —. Needed by: —. Fallback: BM25 keyword retrieval. (Status: OPEN)
- [ ] **H17: Open-source licence decision** — Confirm MIT licence (+USD 250 credit bonus). Owner: Team. Needed by: 12 Oct. Fallback: MIT licence. (Status: OPEN)

---

## 5. Decisions

1. **Model name validation in T08 (no auto-substitution)**: Per user instruction, do not auto-substitute model names. In T08, add a startup check (production mode only) that makes one minimal test call per configured model. If a model ID is rejected, fail fast with a clear error explicitly naming the environment variable to change (`CLAUDE_MODEL_FAST`, `CLAUDE_MODEL_SMART`, or `CLAUDE_MODEL_BUILD`).
2. **Typed stubs for modules rewritten in later tasks**: Modules scheduled for deep redesign in later tasks (e.g. `rule_engine/engine.py`, `rule_engine/misconceptions.py`, `sessions/state_machine.py`, `sessions/manager.py`, `scoring/*`, `reports/*`, `llm/guards.py`, `speech/*`) are maintained with strict types matching spec interfaces. Obsolete tests and partial ad-hoc legacy logic are removed to keep `make ci` and `mypy --strict` 100% green without fake implementations.
3. **Phase 2 Development Lanes & DB Migration Verification in CI**: Phase 2 parallel worktrees (`../abhyas-a` through `../abhyas-d`) configured with isolated ports (8001–8004), per-lane `.env`, and tracking in `progress/lane-*.md`. Full database migration round-trip (`alembic upgrade head -> downgrade base -> upgrade head`) and all 31 tables + `vector` and `pgcrypto` extensions verified against real `pgvector/pgvector:pg16` in GitHub Actions CI with 100% green status across all jobs (`lint`, `secrets`, `content`, `test`). Merging DB code requires a green CI real-Postgres test run. Lane A and Lane D start immediately without local DB; Lanes B and C await local Docker startup for local DB operations.

---

## 6. Questions / Contradictions

1. **`spec/02_architecture.md` §2.3 vs §2.4 on `alembic.ini` location**:
   - Section 2.3 states root layout contains `alembic.ini` (`abhyas/alembic.ini`).
   - Section 2.4 tree lists `alembic.ini` at repo root, while current scaffold has `backend/alembic.ini`.
   - *Resolution for T01*: Move `alembic.ini` to the repository root configured to target `backend/app/db/migrations`.
2. **`spec/03_data_model.md` §3.2 vs `spec/09_web_apps.md` §9.5 on `calibration_label` schema**:
   - In `03_data_model.md`, `calibration_label` table includes `(scene_id, explain_score_id, coach_user_id, scores, note, blind, created_at)`.
   - In `09_web_apps.md` §9.5, the note says "(add to migration)".
   - *Resolution for T03*: Include `calibration_label` and `invite_code` directly in the initial comprehensive migration in T03.
3. **`spec/05_llm_roles.md` §5.1 model names vs current Anthropic API strings**:
   - Spec refers to `claude-haiku-5-5` and `claude-sonnet-5-5`. The `.env.example` sets defaults to `CLAUDE_MODEL_FAST=claude-haiku-5-5` and `CLAUDE_MODEL_SMART=claude-sonnet-5-5`.
   - *Resolution per User Approval*: Do not auto-substitute model names. In T08, add a startup check (production only) that makes one minimal call per configured model; if rejected, fail fast with a clear error naming the env var to change. Record in Decisions #1.

---

## 7. Commands that prompted

*(List commands that required manual approval with command text and reason)*
- `git worktree add ../abhyas-lane-a lane-a; git worktree add ../abhyas-lane-d lane-d` (chained with semicolon)
- `git -C ../abhyas-lane-a merge --ff-only origin/main; git -C ../abhyas-lane-d merge --ff-only origin/main` (chained with semicolon)
- `git worktree remove --force ../abhyas-a ../abhyas-b ../abhyas-c ../abhyas-d` (batch removal)

---

## Blocked on humans

1. **Evaluator Sample Voice Notes (T39, H15)**: Human must run `make samples` locally with a real `SARVAM_API_KEY` in `.env` (or record human voice notes in `eval/samples/recorded/`), listen to all 5 rendered audio files to confirm speech clarity and non-silence, and commit the valid WAVs to `eval/samples/audio/`. In the interim, demo chips in the chat PWA dynamically fall back to sending reference Hindi text.
2. **Hosted Latency Benchmark (T41 re-run)**: Authoritative latency benchmark against the live hosted deployment with real API keys scheduled for the pre-submission feature freeze on 30 Oct.

---

## 8. Current Status & Active Lanes

### STOPPED AT:
- **Main Branch**: Merged PR #1, PR #2 (`d9eeaac`), PR #3 (`3b0a41b`), PR #4 (`c9602ea`), PR #5 (`9d6c902`), and PR #6 (`e54b7ff`).
  - **Full CI Green across all 4 workflows** (`secrets`, `lint`, `content`, `test`):
    - Real PostgreSQL testing in GitHub Actions CI with live `pgvector/pgvector:pg16` container.
    - Code quality: `ruff check` clean, `ruff format --check` clean, `mypy --strict backend/app` clean across all 106 source files.
- **Coord Evaluation Suite (PR #6, `coord/p0-eval` APPROVED and MERGED into main at `e54b7ff`)**:
  - **T38 (Golden Fixtures)**: Golden test fixtures (≥5 pass + fail fixtures per role) for all 7 runtime roles (`act_tagger`, `child_voice`, `coach`, `fidelity_checker`, `guide_answerer`, `question_classifier`, `intent_router`). Added `intent_router` role runner and filtered out fail fixtures in MockLLM output selection. Comprehensive unit verification suite in `test_golden_fixtures.py`.
  - **T39 (Evaluator Audio Samples & Demo Chips)**: `scripts/render_samples.py` requiring real TTS API keys or explicit `--allow-mock`. Removed silent MockTTS audio from git and added `is_wav_non_silent` waveform verification. Demo chips dynamically fall back to text when audio is absent/silent.
  - **T41 (Latency Benchmark & Report)**: Multi-concurrency latency benchmark harness, stage timing breakdown, `eval/latency/REPORT.md`.
- **Reviewer Follow-ups & Blocker Resolutions (Branch `coord/followups-eval`, PR #7)**:
  - Follow-up (a): `get_effective_provider()` displays effective runtime provider in report header (e.g. `mock (no ANTHROPIC_API_KEY)`), resolving configured vs effective contradictions.
  - Follow-up (b) / Blocker 1 (Fake audio guard): In `--url` HTTP mode, verified all 5 evaluator sample inputs have valid, non-silent WAV files on disk via `is_wav_non_silent`; exits non-zero with `"run 'make samples' first"` if any are missing or silent. Local simulation mode uses labelled payload (`b"RIFF_MOCK_SIMULATION_PAYLOAD"`).
  - Follow-up (b) / Blocker 2 (Timeout exclusion & turn completion): Added `ok: bool` and `error_msg` to `TurnMeasurement`. Excluded failed or timed-out turns from percentile calculations (p50, p95). Table 1 reports `{completed_turns}/{total_turns} completed`. If any turn times out or errors, report status and compliance are marked `FAILED`. HTTP polling loop verifies `not pending` and presence of outbound message before concluding turn.
  - Follow-up (b) / Blocker 3 (Auth fallback elimination): Removed fallback to primary `username` when logging in `teacher.demoN` workers during concurrency 3 benchmarking; raises error immediately to avoid lock contention and artificial latency spikes.
  - Follow-up (c): In Table 4, data budget formats low estimates in KB (`**7.6 KB** (estimate on mock payloads)`) to eliminate "0.00 MB" display.
  - Enhanced unit tests in `test_latency_benchmark.py` (7 tests passing) testing effective provider detection, report formatting, timeout exclusion from p95, and `--url` missing audio validation.
- **Lane C Completed & Merged**:
  - T31 Demo Data Cohort, T29 Teacher Progress & Purge, T25 Auth & Demo Users, T30 First Hosted Deploy.
  - T26 Web Channel API & T27 Teacher Chat PWA.
- **Lane B Completed & Merged**:
  - T18 Core Service Skeleton, T19 SceneRunner, T20 Onboarding & Weekly State Machine, T21 Weekly Loop & Evidence.
  - T22 Intents, ASK, BM25 Retrieval & T23 Move Path Scoring.
- **Lane E Completed & Merged**:
  - T24 Scheduler, jobs, aggregates & ARP digest.
- **Coord & Feature Lanes (Overnight Run 3)**:
  - **Step 0**: Guardrails report generated (`eval/guards/REPORT.md`, 8/8 adversarial child-line probes blocked) and CI audit documented (`progress/audit.md`); PR #9 (`coord/guards-report`) opened with 100% green CI.
  - **T32 (ARP Digest)**: DB-backed ARP digest engine (`build_arp_digest`), privacy-by-design consent separation (`अन्य N शिक्षक (स्कोर साझा नहीं)`), suggested visits list with printable observation checklist, `ARPObservation` + L4 `AdoptionEvidence` flow, escalated question answer flow queueing outbound teacher messages, Jinja2 template with `@media print`, 3 unit tests and 5 PostgreSQL integration tests. Branch `coord/arp-digest`.
  - **T33 (Trainer View `/trainer`)**: Built trainer view backed by `AggModuleBatch` with district/batch/move filters, deterministic insight box for missed key points >= 40%, inline SVG stacked rubric bars, adoption evidence ladder distribution, strict $n < 10$ suppression (`समूह छोटा है (n<10) — गोपनीयता हेतु छिपाया गया`), and CSV export with matching privacy enforcement. Zero teacher PII exposed anywhere. Unit and integration tests passing. Branch `coord/trainer-view` ([PR #11](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/11), 100% Green CI on Run 39017590919).

- **Autonomous Night 3 Branches Awaiting Review**:
  - **PR #8 (`lane-e-docs`)**: T48 security headers (CSP, HSTS) & rate limits, T49 comprehensive documentation, T50 hosted smoke tests. CI run 39014169543 green on `39bb179`.
  - **PR #9 (`coord/guards-report`)**: T43 guard report evaluation pipeline (`eval/guards/generate_report.py`). CI run 39015099396 green on `5578119`.
  - **PR #10 (`coord/arp-digest`)**: T32 ARP dashboard (`/arp`) with consenting teacher table, visit list, question resolver. CI run 39016335193 green on `4e5fda6`.
  - **PR #11 (`coord/trainer-view`)**: T33 Trainer view (`/trainer`) with strict $n<10$ suppression and missed key-points insight. CI run 39017590919 green on `4f18375`.
  - **PR #12 (`coord/review-console`)**: T34 Coach review console (`/review`) with queue tabs, blind calibration, JSONL export, and 2-coach move approval. CI run 39019393863 green on `f37cb28`.
  - **PR #13 (`coord/admin`)**: T35 Admin operations dashboard (`/admin`) with latency p50/p95 by stage, turn activity, guard metrics, LLM token consumption, WhatsApp template sends & costs, scheduled jobs, and demo controls. CI run 39021127576 green on `8b58b6d`.

- **T40 (Source Ingestion Pipeline Completed, PR #15)**:
  - Hindi stopwords catalog (`stopwords_hi.txt` with 174 NFC-normalized common words).
  - Enhanced tokenizer with stopword filtering (`tokenize_hindi(filter_stopwords=True)`).
  - Robust garble detection (`is_hindi_garbled` flagging non-Devanagari text ratio < 0.3 on Hindi pages, identifying corrupted legacy fonts like Kruti Dev/Chanakya).
  - Page cleaning (`clean_page_text` with NFC normalization, linebreak de-hyphenation, newline collapse).
  - Multi-page header/footer suppression (`suppress_repeated_headers_footers` across > 50% of pages).
  - Semantic chunker (`chunk_text` with 250-400 words chunks preserving section headings and page IDs `<source_id>:p<page>:<n>`).
  - PDF ingestion engine (`ingest_pdf` via `pypdf`/`pdfplumber`).
  - Sources manifest loader (`ingest_all_sources` checking `content/sources/sources.yaml`, logging clear notice when PDFs are absent under HUMAN INPUT H7, and retaining seed chunks).
  - Database chunk loader (`load_chunks_to_db` into `DocChunk` table, integrated into `seed_database()` for `make db-seed`).
  - Enhanced `GuideRetriever` supporting multi-file chunk directory loading, normalized BM25 scoring with theoretical max IDF denominator, and positive IDF floor for small corpora.
  - Golden retrieval test suite in `backend/tests/integration/test_retrieval.py` (22 tests passing) testing garble detection, text cleaning, header suppression, synthetic PDF ingestion, DB loading, multi-file corpus loading, and 10 realistic FLN teacher questions with precision and score bounds.
  - *Limitation / Status note*: `backend/app/llm/prompts/page_ocr.v1.md` prompt is authored and checked in, but Vision LLM OCR fallback is not wired into the automated ingestion pipeline (pure text-layer extraction via `pypdf`/`pdfplumber` is used; garbled legacy font pages log clear warning).

### NEXT (Autonomous Overnight Queue):
1. **T42 (Kappa Evaluation Harness)** · Priority: P1 (spec/11 §11.4, quadratic-weighted Cohen's kappa calculation for coach rubric scoring vs expert ratings).
2. **T48 (Security & Privacy Pass)** · Priority: P0 (spec/12, spec/14, CSP headers, rate-limiting, audit verification).
3. **T49 (Docs & Freeze)** · Priority: P0 (spec/13, submission checklist, sample inputs, demo script).

### T48 Security pass (lane-e-docs)
- Added `SecurityHeadersMiddleware` (CSP, nosniff, X-Frame-Options DENY, Referrer-Policy, Permissions-Policy, HSTS in production). **Deviation:** CSP keeps `'unsafe-inline'` for script/style because templates use inline scripts, `onclick` handlers and style attributes; all other directives are same-origin. Removing it needs templates moved to external JS (post-submission).
- Per-user chat send limit (`CHAT_MAX_MESSAGES_PER_MINUTE`, default 20) on /api/chat/text, /audio, /button; in-memory, per instance.
- Audio upload now reads at most `MAX_AUDIO_BYTES + 1` bytes before rejecting.
- CI `audit` job runs `pip-audit` (advisory, `continue-on-error`).
- Verified unchanged: CSRF double-submit with `hmac.compare_digest`, WhatsApp HMAC-SHA256 with constant-time compare and 503 when secret unset, login limit 5/min/IP, audio endpoint requires login.
- Open: audio refs are not scoped to the owning teacher (any logged-in user holding a ref can fetch it; refs are content hashes); WhatsApp dedupe set `_PROCESSED_MESSAGE_IDS` is in-memory and unbounded; `onclick="...'{{ btn.id }}'"` interpolates content strings into JS (content is repo-controlled, not user input).

### T43 Guard report (lane-e-docs)
- `backend/app/llm/guard_stats.py` records every guard result (role, attempt, passed, reason, mock flag) from all 7 LLM roles; ring buffer in memory, optional JSONL via `GUARD_EVENT_LOG_PATH`. No teacher text is stored.
- `make eval-guards [EVENTS=file.jsonl]` writes `eval/guards/REPORT.md`: live stats split real vs mock, plus a 10-case adversarial corpus run through the real `guard_child_line` (clearly labelled as test cases, not traffic).
- Needs a human/agy step: run `make eval-guards` once and commit the generated REPORT.md; re-run with real events after the hosted T41 run (28–30 Oct). Fallbacks from an unavailable LLM are not guard events (see `llm_call.outcome`).

### RUN 4 Coordination, Merges, and Hardening
- **Step 1 PR Merges Completed (All CI Green on `main` at `1134d71`)**:
  - Merged #8 (`lane-e-docs` -> `ab0f0af`), #9 (`coord/guards-report` -> `a9ae0fe`), #14 (`coord/whatsapp` -> `ba1cf73`), #10 (`coord/arp-digest` -> `81787c5`), #11 (`coord/trainer-view` -> `5767c16`), #12 (`coord/review-console` -> `ce1fddf`), #13 (`coord/admin` -> `04b6aa1`), #15 (`coord/ingestion` -> `4fe9191`), and #17 (`coord/hardening` -> `1134d71`).
  - All CI jobs green on main.
- **PR #19 (`coord/nits`) — Merged to main at `d48b70e`**:
  - Addressed carry-over nits for #11 (ladder_counts defaults on empty dist, dropped unused district_summary), #12 (whitelisted calibrate score keys against rubric criteria), #15 (removed duplicate stopwords_hi.txt; documented page_ocr.v1.md vision prompt is not automated), #17 (verified no double-firing handlers; verified coach/arp audio bypass; documented /chat and /teacher both render teacher.html), WhatsApp follow-ups (_PROCESSED_MESSAGE_IDS bounded LRU cache, teacher auto-creation rate limit 10/min, ARP answer WhatsApp dispatch, IST-date observed_on), and admin credential docs.
  - Head SHA: `4bcf5f2`, CI Run `39048051782` (100% success).
- **PR #16 (`coord/t24-jobs`) — Merged to main at `8adb8ed`**:
  - Merged main. Wired `schedule_reminder` on unfinished weekly steps (IST-slot deduped), lowered `FOLLOWUP_TRY_IN_CLASS_HOURS` from 72 to 48, resilient week rollover querying latest SessionState, wrapped schedule operations in `begin_nested()` savepoints, narrowed load_move_card exception handling. Added 4 unit tests.
  - Head SHA: `06d423e`, CI Run `39048766813` (100% success).
- **PR #18 (`coord/low-network`) — Merged to main at `bedf657`**:
  - Merged main. Wrapped `dependency_overrides` cleanup in `finally` in `check_first_load.py`; added login status checks and non-login redirect assertions in `--url` mode; updated report table status to "Code present (not exercised)" for unexercised PWA features and "Measured" for bundle sizes; labelled local run as lower bound with mock DB and empty chat history; rendered `data-created-at` from server templates (`teacher.html`, `chat.html`) and updated `chat.js` `initRenderedMessagesFromDom()` to read it without inventing timestamps; updated unit test assertions.
  - Head SHA: `4bc58f4`, CI Run `39049496081` (100% success).

### Rule C Follow-ups (`rule-c`) — Merged to main at `9510638`
- **web/arp.py Exception & Undelivered Message Handling (Rule C)**:
  - Justification: `wa_channel.send` can raise network, HTTP, or phone decryption errors (`httpx.HTTPError`, `ValueError`, etc.) when communicating with external Meta Graph API; caught with in-code one-line Rule C comment to prevent failing the ARP answer transaction if external delivery fails.
  - Eliminated phantom delivered message creation: if WhatsApp dispatch fails, error is logged and no fallback `Message` row is added to the database, ensuring undelivered messages are not marked as delivered.
  - Confirmed and tested that `wa_channel.send(session=db)` delivers and persists exactly one `Message` row on success, with no duplicate added by `arp.py`.
  - Confirmed and tested that unapproved template `abhyas_arp_answer` outside the 24h window logs a warning and skips cleanly without exception or phantom message persistence.
  - Added 3 unit tests in `test_arp_digest.py` (all 10/10 passing). Head SHA: `7193b10`, CI Run `39051660751` (100% success).

### ARP Delivery Fallback & Notification (`arp-delivery`)
- **post_arp_answer Fallback & Notification**:
  - When WhatsApp delivery raises or template is unapproved outside 24h window, question status remains `arp_answered` and review item `resolved`.
  - Redirects ARP to `/arp?saved=1&msg=ans_wa_fail`, rendering new catalog message `ui_arp_answer_saved_wa_undelivered` from `messages_hi.yaml` ("उत्तर सुरक्षित हो गया है, लेकिन WhatsApp पर नहीं भेजा जा सका। शिक्षक इसे ऐप में देख सकते हैं।", no feminine markers).
  - Stores answer as a `Message` row on channel `"web"` so teacher sees it when logging into the app; never stores an undelivered WhatsApp row.
  - Added unit tests in `test_arp_digest.py` verifying `ans_wa_fail` redirect, flash message rendering, and web fallback Message row creation (11/11 tests passing).

### T24 Jobs Review Fixes (`coord/t24-jobs`)
- **Reminder Wiring**: Wired `schedule_reminder` in `SessionService._sync_context_to_db` within `begin_nested()` savepoint whenever a teacher in `READY` onboarding state leaves a weekly step unfinished (`current_state != DONE`). Deduped by IST date slot.
- **Tunables alignment**: Updated `FOLLOWUP_TRY_IN_CLASS_HOURS` from 72 to 48 in `config.py` and `tunables.py` matching spec/08 §8.5 (48-hour follow-up).
- **Week Rollover Resilience**: Updated `handle_followup_try_in_class` to query the latest `SessionState` for the teacher ordered by `week_start.desc()` instead of strictly matching the current week, supporting Fri->Mon week rollover without skipping.
- **Savepoint Isolation**: Wrapped `schedule_followup_try_in_class` in `async with self.repo.session.begin_nested():` at both retry limit and continue transition points in `service.py`, preventing transaction failure poisoning on scheduler error.
- **Rule C Exception Narrowing**: Narrowed exception around `load_move_card` in `handle_followup_try_in_class` to `(FileNotFoundError, ValueError, OSError)`.
- **Unit Tests**: Added unit tests in `test_job_handlers.py` verifying reminder scheduling on unfinished steps, omission on DONE, Fri->Mon rollover follow-up, and 48-hour default tunable.

### Carry-over Review Nits & Hardening (`coord/nits`)
- **#11 (Trainer View)**: `ladder_counts` safely handles empty `ladder_dist` by emitting keys 1..5 as 0; dropped unused `district_summary` from `TrainerReport`.
- **#12 (Review Console)**: Whitelisted `POST /review/calibrate` score keys to move rubric criterion IDs, validating 0-2 bounds and rejecting unknown keys with 400 Bad Request; removed hardcoded fallback criteria (`accuracy`, `bundle_opening`, `contrast`) from `review_item_detail`.
- **#15 (Source Ingestion)**: Removed duplicate `retrieval/stopwords_hi.txt` via `git rm` (retained `backend/app/retrieval/stopwords_hi.txt`); noted that `page_ocr.v1.md` is authored but OCR vision fallback is not wired to automated pipeline.
- **#17 (Hardening Verification)**: Verified `chat.js` handles dynamic closures and server-rendered data attributes without event double-firing; verified `coach`/`arp` bypass teacher audio ownership checks; confirmed `/chat` and `/teacher` routes both render `teacher.html` (`chat.html` retained as identical copy for test backwards compatibility).
- **#14 Follow-ups (WhatsApp Channel)**:
  - Bounded `_PROCESSED_MESSAGE_IDS` using an LRU `BoundedSet` governed by `WHATSAPP_PROCESSED_CACHE_SIZE` in `config.py`.
  - Added in-memory sliding-window rate limiting for teacher auto-creation from unknown numbers governed by `WHATSAPP_TEACHER_CREATION_RATE_LIMIT_PER_MINUTE` in `config.py`.
  - Routed ARP answers in `post_arp_answer` for teachers with `preferred_channel == "whatsapp"` through `WhatsAppChannel.send` using template `abhyas_arp_answer`.
  - Updated ARP observation date recording to use IST date (`datetime.now(IST).date()`).
- **README.md**: Updated admin username from `admin.demo` to `admin` in credentials table to align with `spec/13_submission.md`.

### Deploy Fixes (`deploy-fixes`)
- **scripts/smoke_test.py**: Added `--password` CLI argument and fallback to `os.environ.get("DEMO_PASSWORD")` and `settings.DEMO_PASSWORD`; eliminated hardcoded `"abhyas-demo-2026"` password string from test execution. Added unit tests in `test_health.py` for explicit password argument, `DEMO_PASSWORD` environment variable, and settings fallback (12/12 passing).
- **backend/app/db/seed.py**: Sanitized log output by removing `DEMO_PASSWORD` formatting from `logger.info("Starting database seed")`.
- **docs/DEPLOY.md**: Updated §1.3 and Table 2 for `ALEMBIC_DATABASE_URL` to specify Supabase Session Pooler URI on port 5432 (`postgresql://...`) instead of the direct connection host (`db.[PROJECT-REF].supabase.co`), documenting that Supabase direct host defaults to IPv6 which causes connection failures on platforms without IPv6 routing (such as Render or standard Docker).
- **.env.example**: Updated local `DATABASE_URL` and `ALEMBIC_DATABASE_URL` default passwords from `postgres` to `postgrespassword` to match `infra/docker-compose.yml`.

### Small Fixes (`small-fixes` — T60)
- **web/arp.py**: Wrapped `wa_channel.send` in `async with db.begin_nested():` savepoint in `post_arp_answer`. If WhatsApp send fails mid-write, the nested transaction rolls back, preventing outer session transaction poisoning, and the web channel fallback `Message` row is stored and committed cleanly.
- **backend/tests/unit/test_arp_digest.py**: Added `test_arp_post_answer_whatsapp_mid_write_failure_still_stores_web_fallback` verifying savepoint invocation and web message fallback persistence on mid-write dispatch failures (12/12 passing).
- **backend/tests/unit/test_review_console.py**: Updated admin username from legacy `admin.demo` to `admin` across approval and authorization tests to align with `spec/13_submission.md` credentials table (10/10 passing).
- **docs/DEPLOY.md & README.md**: Re-read end-to-end; verified admin credentials (`admin`), run commands (`make setup db-up db-migrate db-seed dev`, `python scripts/smoke_test.py`, `make eval-guards`, etc.) are consistent with Makefile and scripts.

### Cost Evaluation Reporting (`cost-report` — T61)
- **backend/app/config.py**: Added Claude and Sarvam pricing tunables with source URLs and as-of dates (2026-10):
  - Haiku 5.5: $0.10 input / $0.50 output / $0.01 cache read per MTok (`HAIKU_INPUT_USD_PER_MTOK`, `HAIKU_OUTPUT_USD_PER_MTOK`, `HAIKU_CACHE_READ_USD_PER_MTOK`).
  - Sonnet 5.5: $2.00 input / $10.00 output / $0.10 cache read per MTok (`SONNET_INPUT_USD_PER_MTOK`, `SONNET_OUTPUT_USD_PER_MTOK`, `SONNET_CACHE_READ_USD_PER_MTOK`).
  - Sarvam STT: ₹30 per hour / ₹0.50 per min (`STT_COST_PER_HOUR_INR`, `STT_COST_PER_MINUTE_INR`).
  - Sarvam TTS: ₹30 per 10K chars / ₹3.00 per 1K chars (`TTS_COST_PER_10K_CHARS_INR`, `TTS_COST_PER_1000_CHARS_INR`).
  - `USD_TO_INR`: default 88.0, labelled "assumption, update before submission".
- **eval/cost/cost_report.py**: Implemented CLI and calculation engine reading `llm_call` and `speech_spend` rows. Computes total spend, cost per teacher, cost per completed weekly loop (`SessionState.state == "DONE"`), daily spend, and model breakdown. Outputs `eval/cost/REPORT.md`. Excludes mock rows unless `--include-mock` is specified, labelling report as `local/mock`.
- **Makefile**: Added `eval-cost` target to run `python eval/cost/cost_report.py`.
- **backend/tests/unit/test_cost_report.py**: Added unit tests for Haiku/Sonnet token pricing calculations, end-to-end metrics computation on fixture data, mock mode filtering, and Markdown report formatting (4/4 passing).

### T64 Official Source Ingestion, OCR Pipeline & Spot-Checks (`sources-ocr`)
- **Official Government Sources Registry**:
  - Registered 5 official government documents in `content/sources/sources.yaml` with titles, publishers, as-of dates, licence notes, and unverified URLs set to `url: "TODO(human)"`.
  - Confirmed `content/sources/*.pdf` is strictly gitignored.
- **Dual-Layer Extraction & Optional OCR Pipeline**:
  - Primary extractor: `pdfplumber` with fallback to `pypdf`.
  - Heavyweight OCR packages (`pdfplumber`, `pytesseract`, `pdf2image`) configured as optional extra `ocr = ["pdfplumber>=0.10.4", "pytesseract", "pdf2image"]` in `pyproject.toml`. Documented installation via `pip install -e ".[ocr]"` and Tesseract with `hin.traineddata` (and Surya OCR alternative) in `docs/DEPLOY.md`.
  - Hindi font legibility heuristic (`is_page_text_poor`, `is_hindi_garbled`): detects missing text layers, legacy font ASCII corruption, and high replacement character ratios ($> 15\%$).
  - Automatic OCR execution: Renders 300 dpi page images via poppler/pdf2image and runs Tesseract 5 (`hin+eng`) with word-level confidence calculation.
  - Low-confidence dropping: Drops pages with confidence $< 0.40$ (configurable via `--confidence-threshold`), logging clear warnings.
  - Mock OCR harness: Added `set_ocr_mock_handler` for deterministic CI execution without requiring external C-binaries on system PATH.
- **CLI Support**:
  - `python -m backend.app.retrieval.ingest --source <id> [--ocr tesseract|surya] [--confidence-threshold 0.4] [--all] [--no-spotcheck]`
- **Typographic Spot-Check Generation**:
  - Automatically produces `eval/sources/<source_id>_spotcheck.md` evaluating up to 10 sample pages per document.
  - Deleted unverified sample spot-check `eval/sources/fln_sample_c2_spotcheck.md`.
  - Inspects Unicode NFC normalization, absence of orphaned matras, and trailing viramas/halants.
- **Guide Citation Formatting**:
  - Updated `format_guide_citation` to catch specific exceptions `(KeyError, ValueError, TypeError)` conforming to Rule C.
  - Uses standard Hindi catalog abbreviation `पृ.` (`ask_source_page_abbrev`) from `content/messages_hi.yaml` without inline Hindi.
  - Wired into `compose_guide_reply` in `backend/app/llm/roles/guide_answerer.py`.
- **Unused Prompt Note**:
  - `backend/app/llm/prompts/page_ocr.v1.md` is an authored reference prompt for Vision LLM single-page transcription. It is intentionally **not wired into the automated ingestion pipeline** because processing multi-hundred-page state teacher guides via Claude Sonnet Vision would incur prohibitive token expenses and non-deterministic latency. Automated ingestion uses deterministic local extractors (`pdfplumber` + Tesseract 5 / Surya OCR). `page_ocr.v1.md` is preserved for manual single-page reference only.

