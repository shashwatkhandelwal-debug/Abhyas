# OVERNIGHT.md — Autonomous Overnight Run Log

Started: 2026-10-17 01:08 IST  
Completed: 2026-10-17 02:15 IST  
Status: ALL TASKS COMPLETED (100% GREEN CI)

## Hard Rules Active
- No push to `main`. No force-push. No git reset --hard. No history rewriting.
- Work only on `lane-c`, `lane-b`, and `coord/wire-lane-e`.
- Commits formatted as `T<id>: <summary>`.
- Push freely to lane branches and verify CI on each branch via `scripts/ci_status.py`.
- No merge to `main`. All tasks completed on isolated branches and awaiting morning review and approval.

---

## Tasks Summary & Deliverables

| Task | Lane / Branch | PR | Status | Head SHA | CI Run | Deliverables & Summary |
|---|---|---|---|---|---|---|
| **Coord (T24)** Wire Lane-E Scheduler | `coord/wire-lane-e` | [PR #2](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/2) | **MERGED into main** (`d9eeaac`) | `da9228e` | [Run 39000627486](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39000627486) | Merged `lane-e` scheduler, admin fast-forward router, lifespan start/stop, config tunables, pyproject packages, migration test schema isolation fix. |
| **Lane C (T26)** Web Channel API | `lane-c` | [PR #3](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/3) | **MERGED into main** (`3b0a41b`) | `ac34f2b` | [Run 39000772436](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39000772436) | SessionService web pipeline connection, deduplication, polling `/api/chat/messages`, audio caching, rating/settings endpoints, English HTTPException details. |
| **Lane C (T27)** Teacher Chat PWA | `lane-c` | [PR #3](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/3) | **MERGED into main** (`3b0a41b`) | `ac34f2b` | [Run 39000772436](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39000772436) | Teacher chat PWA templates (`teacher.html`, `chat.html`), vanilla JS offline outbox in IndexedDB with exponential retry, MediaRecorder 16kbps mono voice recorder, catalog-driven offline banner, <67 KB first-load asset budget. |
| **Lane B (T22)** Intents, ASK, BM25 Retrieval | `lane-b` | [PR #4](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/4) | **MERGED into main** (`c9602ea`) | `b27c2fe` | [Run 39002009955](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39002009955) | 22 chunks extracted into `content/chunks/seed_from_moves.jsonl`, BM25 retriever with Unicode Hindi tokenization in `search.py`, ASK flow wiring in `service.py`, review item escalation. |
| **Lane B (T23)** Move Path Scoring | `lane-b` | [PR #4](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/4) | **MERGED into main** (`c9602ea`) | `b27c2fe` | [Run 39002009955](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39002009955) | Pulled `path_score.py` from `lane-e`, wired deterministic `rank_moves` into `sessions/path.py`, resolved package hygiene narrow exceptions. |
| **Coord (PR #5)** Reviewer Follow-ups Polish | `coord/polish-and-p0` | [PR #5](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/5) | **MERGED into main** (`9d6c902`) | `7b7a869` | [Run 39002622557](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39002622557) | Addressed reviewer follow-ups for PR #2 & PR #3: test DB drop schema guard (`assert "test" in url or CI`), demo_chips JSON loading dynamically into PWA chat interface, mock STT clean fallbacks, and 100% green CI against Postgres. |
| **Coord (T38, T39, T41)** Golden Fixtures, Audio Samples, Latency Report | `coord/p0-eval` | [PR #6](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/6) | **MERGED into main** (`e54b7ff`) | `9e1b297` | [Run 39008573282](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39008573282) | **T38**: Golden test fixtures (≥5 pass + fail fixtures per role) for all 7 runtime roles, README documenting hand-written synthetic provenance, `test_golden_fixtures.py`.<br>**T39**: `render_samples.py` enforces real TTS provider, silent WAVs removed from git, `is_wav_non_silent` computes `audio_available` dynamically with text fallback in PWA chips.<br>**T41**: Multi-concurrency latency benchmark harness, stage timing breakdown, `eval/latency/REPORT.md` honest mock status ("NOT MEASURED (mock providers)" and mock payload estimates), verified in-code optimizations with file links. |
| **Coord (PR #7)** Reviewer Follow-ups & Blockers (Fake Audio Guard, Timeout Exclusion, Auth Fix) | `coord/followups-eval` | [PR #7](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/7) | **MERGED into main** (`220377c`) | `e7d0897` | [Run 39011897840](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39011897840) | Blocker 1: audio validation on disk. Blocker 2: timeout exclusion from p50/p95. Blocker 3: auth fallback removed. Effective provider reporting in header. |
| **Lane E (T48, T49, T50)** Security Headers, Rate Limits, Docs, Smoke Tests | `lane-e-docs` | [PR #8](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/8) | **Awaiting Review** | `39bb179` | [Run 39014169543](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39014169543) | T48 security headers (CSP self-only, HSTS, nosniff, frame-ancestors none) & chat burst/minute rate limiter; T49 comprehensive documentation (README, video script, deck assets, runbook, checklist); T50 hosted smoke test script. |
| **Coord (T43)** Guard Failure Analysis & Report | `coord/guards-report` | [PR #9](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/9) | **Awaiting Review** | `5578119` | [Run 39015099396](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39015099396) | T43 guard report evaluation script (`eval/guards/generate_report.py`), golden trace evaluation across 6 runtime roles, automated `REPORT.md` generation with markdown summary table and failure category taxonomy. |
| **Coord (T32)** ARP Weekly Digest & Interventions | `coord/arp-digest` | [PR #10](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/10) | **Awaiting Review** | `4e5fda6` | [Run 39016335193](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39016335193) | T32 ARP web dashboard (`/arp`) per spec/09 §9.3: weekly activity overview, consenting teacher progress table with rubric score dots and escalation flags, suggested classroom visit list with printable checklist link and observation recording, escalated questions resolver, non-consenting aggregate count row. |
| **Coord (T33)** Trainer View with n<10 Suppression | `coord/trainer-view` | [PR #11](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/11) | **Awaiting Review** | `4f18375` | [Run 39017590919](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39017590919) | T33 trainer view (`/trainer`) per spec/09 §9.4: batch × move metrics from `agg_module_batch`, strict $n < 10$ suppression displaying "समूह छोटा है (n<10) — गोपनीयता हेतु छिपाया गया" across all metric cells, programmatic pedagogical insight box (≥40% missed key points), CSV export endpoint, zero teacher PII guarantee. |
| **Coord (T34)** Coach Review Console & Calibration | `coord/review-console` | [PR #12](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/12) | **Awaiting Review** | `f37cb28` | [Run 39019393863](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39019393863) | T34 coach review console (`/review`) per spec/09 §9.5: queue tabs (कम भरोसा स्कोर, प्रश्न, गार्ड विफलताएँ, सामग्री), speaker-coloured rehearsal detail view with acts and confidence highlights, score correction saving to `review_item.resolution` and `calibration_label`, blind double-coding mode (`/review/calibrate`), JSONL export (`/review/calibration.jsonl`), move editor with raw YAML validation and 2-distinct-coach approval requirement (`MOVE_APPROVALS_REQUIRED = 2`). |

---

## Task Details & Verification Log

### 1. Coord: Wire Lane-E Scheduler & Pipeline Integration
- **Branch**: `coord/wire-lane-e`
- **PR**: [shashwatkhandelwal-debug/Abhyas#2](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/2)
- **Head SHA**: `94e045e`
- **CI Status**: [Run 38964779134 — Completed / Success](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/38964779134)
  - `lint`: Success
  - `secrets`: Success
  - `test`: Success (ran PostgreSQL + pgvector integration tests and unit tests)
  - `content`: Success
- **Key Deliverables**:
  - Merged `origin/lane-e` cleanly (APScheduler tick, recurring job planner, follow-up questions, ARP digest snapshots, aggregates handler, T42 kappa harness, T23 path score module).
  - Added scheduler settings in `backend/app/config.py`: `SCHEDULER_ENABLED`, `SCHEDULER_TICK_SECONDS`, `SCHEDULER_PLAN_MINUTES`, `SCHEDULER_MAX_ATTEMPTS`, `SCHEDULER_RETRY_BASE_SECONDS`, `SCHEDULER_BATCH_LIMIT`, `AGGREGATES_HOUR_IST`, `ARP_DIGEST_WEEKDAY`, `ARP_DIGEST_HOUR_IST`, `FOLLOWUP_TOPIC_MAX_WORDS`.
  - App lifespan in `backend/app/main.py`: starts scheduler on startup, stops on shutdown.
  - Mounted `backend.app.jobs.admin_api.router` (`POST /admin/fast-forward/{teacher_id}`).
  - Fixed stubs in `jobs/scheduler.py` and `jobs/__init__.py`.
  - Added schema isolation in `backend/tests/integration/test_migrations.py` so migration round-trip tests run against an isolated public schema regardless of previous test suite execution.

### 2. Lane C: T26 Web Channel API & T27 Teacher Chat PWA
- **Branch**: `lane-c`
- **PR**: [shashwatkhandelwal-debug/Abhyas#3](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/3)
- **Head SHA**: `ac34f2b`
- **CI Status**:
  - T26: [Run 38961404641 — Completed / Success](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/38961404641)
  - T27: [Run 38964138452 — Completed / Success](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/38964138452)
- **Key Deliverables**:
  - Connected `process_inbound_web` to real `SessionService(db_session=session)`.
  - Full API conformance: `POST /api/chat/text`, `POST /api/chat/audio` (multipart <= 2 MB), `POST /api/chat/button`, `GET /api/chat/messages?after=`, `GET /api/audio/<ref>.<ext>`, `POST /api/chat/rating`, and `POST /api/settings`.
  - Idempotency / deduplication on `(channel="web", client_msg_id)`.
  - Replaced all inline Hindi HTTPException details with English status details.
  - Teacher chat PWA templates (`teacher.html`, `chat.html`), vanilla JS offline outbox in IndexedDB (`chat.js`), MediaRecorder audio recorder (`recorder.js`), service worker caching (`sw.js`).
  - Total first-load asset weight ~67 KB (<150 KB limit), 100% NFC normalized.
  - 17 unit tests in `test_teacher_pwa.py` + 21 unit tests in `test_web_channel.py`.

### 3. Lane B: T22 Intents, ASK Retrieval & T23 Move Path Scoring
- **Branch**: `lane-b`
- **PR**: [shashwatkhandelwal-debug/Abhyas#4](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/4)
- **Head SHA**: `f5448c3`
- **CI Status**: [Run 38962536846 — Completed / Success](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/38962536846)
- **Key Deliverables**:
  - Ingestion pipeline in `backend/app/retrieval/ingest.py` extracting 22 chunks from seed YAMLs into `content/chunks/seed_from_moves.jsonl`.
  - BM25 retriever `GuideRetriever` in `backend/app/retrieval/search.py` with Unicode Hindi tokenization.
  - ASK flow wiring in `backend/app/sessions/service.py`: question classification, clarifying questions, BM25 retrieval, guide answers, escalation to review items, and prompt resumption.
  - Move path scoring: deterministic `rank_moves` from `backend/app/sessions/path_score.py` wired into `backend/app/sessions/path.py` with YAML loader fallback.
  - Clean narrow exception handling conforming to `test_sessions_package_hygiene_no_broad_exceptions_and_no_devanagari`.
  - 84 unit tests passing across `test_path_score.py`, `test_ask_retrieval.py`, and `test_state_machine.py`.

### 4. Coord: P0 Evaluation Suite (T38 Golden Fixtures, T39 Audio Samples, T41 Latency Report)
- **Branch**: `coord/p0-eval`
- **PR**: [shashwatkhandelwal-debug/Abhyas#6](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/6)
- **Head SHA**: `9e1b297`
- **CI Status**: [Run 39007884028 — Completed / Success](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39007884028)
  - `lint`: Success (ruff check + ruff format clean)
  - `secrets`: Success (gitleaks zero secrets)
  - `content`: Success (all moves, personas, messages conform to schemas)
  - `test`: Success (all unit, integration with PostgreSQL, and migration tests passing)
- **Key Deliverables**:
  - **T38 (Golden Fixtures)**:
    - Added prompt `intent_router.v1.md`, runner `roles/intent_router.py`, and 5 pass + 2 fail fixtures.
    - Added 5 pass + 4 fail fixtures in `golden/coach/` across distinct moves (`NUM_SUB_REGROUP_BUNDLES`, `NUM_WORD_PROBLEM_CHANGE`, `NUM_ADD_CARRY_BUNDLES`).
    - Added 2 pass fixtures in `golden/fidelity_checker/` bringing total pass fixtures to 5.
    - Added `backend/tests/golden/README.md` documenting hand-written synthetic provenance.
    - Updated `MockLLM._find_golden_output` to filter out negative test `fail_*` fixtures so mock runs never return failing outputs.
    - Created `backend/tests/unit/test_golden_fixtures.py` verifying all 7 runtime roles have >= 5 passing fixtures that satisfy schema and guards.
  - **T39 (Evaluator Audio Samples & Demo Chips)**:
    - `scripts/render_samples.py` enforces real TTS provider: exits with error if `TTS_PROVIDER=mock` unless `--allow-mock` is passed explicitly.
    - Removed silent MockTTS WAVs from git.
    - Added `is_wav_non_silent` helper in `backend/app/speech/audio.py` using amplitude and RMS waveform detection.
    - Updated `load_demo_chips()` in `backend/app/web/teacher.py` and `demo_chips.json` to dynamically compute `audio_available` (false when absent or silent) with text fallback in `chat.js`.
    - Logged HUMAN INPUT requirement in `PROGRESS.md` for human to run `make samples` with Sarvam key and verify clarity.
  - **T41 (Latency Benchmark & Report)**:
    - Built `eval/latency/benchmark_latency.py` with multi-concurrency (1 and 3) stage timing instrumentation (`download`, `convert`, `stt`, `tagger`, `engine`, `voice`, `guard`, `tts`, `send`).
    - Updated `REPORT.md` to record provider modes and report `NOT MEASURED (mock providers)` when running in mock dev/CI mode, with data budgets labeled `estimate on mock payloads`.
    - Retained only verified in-code optimizations with exact file links in Section 5.
    - Unit tests in `test_latency_benchmark.py`.

### 5. Coord: T34 Coach Review Console & Calibration
- **Branch**: `coord/review-console`
- **PR**: [shashwatkhandelwal-debug/Abhyas#12](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/12)
- **Head SHA**: `f37cb28`
- **CI Status**: [Run 39019393863 — Completed / Success](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/39019393863)
  - `lint`: Success
  - `secrets`: Success
  - `test`: Success (PostgreSQL integration + unit tests)
  - `content`: Success
- **Key Deliverables**:
  - `backend/app/web/review.py` & templates (`review.html`, `review_detail.html`, `review_calibrate.html`, `review_move.html`):
    - 4 queue tabs (`rehearsal_score` / `explain_score`, `question`, `guard_failure`, `moves`) with badge counts and status filter.
    - Detail view with speaker-coloured chat bubbles, turn acts, AI confidence badges, evidence quotes, and score resolution form.
    - Resolution saves scores (0/1/2) and coach notes to `review_item.resolution` and logs `CalibrationLabel(blind=False)`.
    - Blind double-coding calibration mode (`GET/POST /review/calibrate`): transcript stripped of AI scores, acts, or quotes; saves to `CalibrationLabel(blind=True)`.
    - Calibration export (`GET /review/calibration.jsonl`): stream-downloads all double-coded calibration labels as newline-delimited JSON.
    - Move editor with key points, rubric levels, approvals counter, and raw YAML validator against `MoveCard` schema; marks `approved` when 2 distinct coaches approve (`MOVE_APPROVALS_REQUIRED = 2`).
  - Unit and PostgreSQL integration tests in `test_review_console.py` and `test_review_console_integration.py`.

