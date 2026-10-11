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
- [ ] **T04 Content models & seed content** · Priority: P0 · Finish-by: 13 Oct
- [ ] **T05 Hindi utilities** · Priority: P0 · Finish-by: 13 Oct
- [ ] **T06 Bug rules** · Priority: P0 · Finish-by: 14 Oct
- [ ] **T07 Rule engine** · Priority: P0 · Finish-by: 15 Oct
- [ ] **T08 LLM client + MockLLM** · Priority: P0 · Finish-by: 14 Oct
- [ ] **T09 Guards** · Priority: P0 · Finish-by: 15 Oct
- [ ] **T10 act_tagger** · Priority: P0 · Finish-by: 16 Oct
- [ ] **T11 child_voice** · Priority: P0 · Finish-by: 16 Oct
- [ ] **T12 coach** · Priority: P0 · Finish-by: 17 Oct
- [ ] **T13 fidelity_checker** · Priority: P0 · Finish-by: 17 Oct
- [ ] **T14 intent_router, question_classifier, guide_answerer** · Priority: P1 · Finish-by: 20 Oct
- [ ] **T15 Audio utils** · Priority: P0 · Finish-by: 14 Oct
- [ ] **T16 STT** · Priority: P0 · Finish-by: 16 Oct
- [ ] **T17 TTS + voices** · Priority: P0 · Finish-by: 17 Oct
- [ ] **T18 Core service skeleton** · Priority: P0 · Finish-by: 16 Oct
- [ ] **T19 SceneRunner** · Priority: P0 · Finish-by: 18 Oct
- [ ] **T20 Onboarding** · Priority: P0 · Finish-by: 19 Oct
- [ ] **T21 Weekly loop + evidence** · Priority: P0 · Finish-by: 20 Oct
- [ ] **T22 Intents, ASK, retrieval** · Priority: P1 · Finish-by: 21 Oct
- [ ] **T23 Move path** · Priority: P1 · Finish-by: 21 Oct
- [ ] **T24 Scheduler & jobs** · Priority: P1 · Finish-by: 22 Oct
- [ ] **T25 Auth & demo users** · Priority: P0 · Finish-by: 17 Oct
- [ ] **T26 Web channel API** · Priority: P0 · Finish-by: 18 Oct
- [ ] **T27 Teacher chat PWA** · Priority: P0 · Finish-by: 20 Oct
- [ ] **T28 WhatsApp channel** · Priority: P0 code 21 Oct / P1 live · Finish-by: 21 Oct
- [ ] **T29 Progress, consent, delete** · Priority: P1 · Finish-by: 22 Oct
- [ ] **T30 First hosted deploy** · Priority: P0 · Finish-by: 18 Oct
- [ ] **T31 Demo data** · Priority: P1 · Finish-by: 22 Oct
- [ ] **T32 ARP digest** · Priority: P1 · Finish-by: 24 Oct
- [ ] **T33 Trainer view + aggregates** · Priority: P1 · Finish-by: 24 Oct
- [ ] **T34 Coach review console** · Priority: P1 · Finish-by: 25 Oct
- [ ] **T35 Admin** · Priority: P1 · Finish-by: 25 Oct
- [ ] **T36 Sankul mode** · Priority: P2 · Finish-by: 28 Oct
- [ ] **T37 User-testing kit** · Priority: P0 · Finish-by: 14 Oct
- [ ] **T38 Golden fixtures** · Priority: P0 · Finish-by: 17 Oct
- [ ] **T39 Evaluator samples** · Priority: P0 · Finish-by: 22 Oct
- [ ] **T40 Source ingestion** · Priority: P1 · Finish-by: 23 Oct
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
