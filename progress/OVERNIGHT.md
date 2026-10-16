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
| **Coord (T24)** Wire Lane-E Scheduler | `coord/wire-lane-e` | [PR #2](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/2) | **PASSED** (Ready for Review) | `b6d641d` | [Run 38960278394](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/38960278394) | Merged `lane-e` scheduler, admin fast-forward router, lifespan start/stop, config tunables, pyproject packages, migration test schema isolation fix. |
| **Lane C (T26)** Web Channel API | `lane-c` | [PR #3](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/3) | **PASSED** (Ready for Review) | `5fda935` | [Run 38961404641](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/38961404641) | SessionService web pipeline connection, deduplication, polling `/api/chat/messages`, audio caching, rating/settings endpoints, English HTTPException details. |
| **Lane C (T27)** Teacher Chat PWA | `lane-c` | [PR #3](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/3) | **PASSED** (Ready for Review) | `ac34f2b` | [Run 38964138452](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/38964138452) | Teacher chat PWA templates (`teacher.html`, `chat.html`), vanilla JS offline outbox in IndexedDB with exponential retry, MediaRecorder 16kbps mono voice recorder, catalog-driven offline banner, <67 KB first-load asset budget. |
| **Lane B (T22)** Intents, ASK, BM25 Retrieval | `lane-b` | [PR #4](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/4) | **PASSED** (Ready for Review) | `518ab7e` | [Run 38962536846](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/38962536846) | 22 chunks extracted into `content/chunks/seed_from_moves.jsonl`, BM25 retriever with Unicode Hindi tokenization in `search.py`, ASK flow wiring in `service.py`, review item escalation. |
| **Lane B (T23)** Move Path Scoring | `lane-b` | [PR #4](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/4) | **PASSED** (Ready for Review) | `f5448c3` | [Run 38962536846](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/38962536846) | Pulled `path_score.py` from `lane-e`, wired deterministic `rank_moves` into `sessions/path.py`, resolved package hygiene narrow exceptions. |

---

## Task Details & Verification Log

### 1. Coord: Wire Lane-E Scheduler & Pipeline Integration
- **Branch**: `coord/wire-lane-e`
- **PR**: [shashwatkhandelwal-debug/Abhyas#2](https://github.com/shashwatkhandelwal-debug/Abhyas/pull/2)
- **Head SHA**: `b6d641d`
- **CI Status**: [Run 38960278394 — Completed / Success](https://github.com/shashwatkhandelwal-debug/Abhyas/actions/runs/38960278394)
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
