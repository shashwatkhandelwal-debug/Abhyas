# Phase 2 — Parallel Development Lanes Architecture

This document defines the 4 isolated parallel development lanes for Abhyas, per `spec/14_tasks.md` and project governance.

## 1. Lane Ownership & Responsibilities

A lane edits **ONLY** its assigned folders and files. Any changes outside a lane's boundaries must be raised as a formal request to the coordinator in `LANES.md › Requests for the coordinator`.

| Lane | Branch | Worktree Path | Port | Scope | Tasks Owned | Folders Owned |
|---|---|---|---|---|---|---|
| **Lane A** (Core IP) | `lane-a` | `../abhyas-a` | 8001 | Pure deterministic rule engine, Hindi utilities, bug rules, output guards, prompting roles | T05, T06, T07, T09, T10, T11, T12, T13, T14 | `backend/app/rule_engine/**`<br>`backend/app/llm/**` (except `client.py`)<br>`content/act_examples_hi.yaml`<br>Their respective unit tests |
| **Lane B** (Pipeline) | `lane-b` | `../abhyas-b` | 8002 | Platform infrastructure, client connectors, speech engine, rehearsal orchestrator, session state machine, retrieval, scoring | T08, T15, T16, T17, T18, T19, T20, T21, T22, T23, T24 | `backend/app/llm/client.py`<br>`backend/app/speech/**`<br>`backend/app/core/**`<br>`backend/app/rehearsal/**`<br>`backend/app/sessions/**`<br>`backend/app/retrieval/**`<br>`backend/app/scoring/**`<br>`backend/app/jobs/**`<br>Their respective tests |
| **Lane C** (Web & Ops) | `lane-c` | `../abhyas-c` | 8003 | WhatsApp & Web channels, auth, teacher chat PWA, admin, review consoles, reports, Docker & deploy | T25, T26, T27, T28, T29, T30, T31, T32, T33, T34, T35, T36 | `backend/app/channels/**`<br>`backend/app/auth/**`<br>`backend/app/web/**`<br>`backend/app/privacy/**`<br>`backend/app/reports/**`<br>`backend/app/db/seed.py`<br>`backend/app/db/demo_data.py`<br>`Dockerfile`<br>`docker-compose.yml`<br>`render.yaml`<br>Their respective tests |
| **Lane D** (Content & Eval) | `lane-d` | `../abhyas-d` | 8004 | Teaching move YAMLs, persona cards, document chunking, retrieval evaluation, benchmark scripts, user testing | T37 (FIRST), then T38, T39, T40, T41, T42, T43, T44, T45, and drafts for T49 | `content/**` (except `act_examples_hi.yaml`)<br>`eval/**`<br>`docs/**`<br>`scripts/**`<br>`README.md`<br>`backend/tests/golden/**` |

---

## 2. Shared Files & Coordinator Ownership

The following files are **SHARED** and owned strictly by the **Coordinator**:
- `pyproject.toml`
- `backend/app/config.py`
- `backend/app/db/models.py`
- `backend/app/db/migrations/**`
- `backend/app/main.py`
- `Makefile`
- `.github/**`
- `PROGRESS.md`
- `AGENTS.md`
- `LANES.md`
- `spec/**`
- Tasks owned solely by Coordinator: **T46, T47, T48, T50, T51, T52**

### PR Rule (Enforced)
The coordinator **rejects any PR** that touches files outside the lane's assigned folders. If a lane requires a new dependency, a database model change, or a configuration constant, it must submit a request in `LANES.md › Requests for the coordinator`.

---

## 3. Quality Rules (Enforced on Every PR & Merge)

1. **Rule A (CI Parity)**: Every PR must pass `make ci` (`ruff check .`, `ruff format --check .`, `mypy --strict backend/app`, `pytest`, `content/tests`, secret scanning) locally and on GitHub Actions before the coordinator merges.
2. **Rule B (Test-First / Acceptance Strictness)**: No task is marked "done" without passing all acceptance tests listed in `spec/14_tasks.md` for that task. Tests are written FIRST or alongside, never after "it works".
3. **Rule C (Zero Lint / Type Suppressions)**: Zero `# type: ignore`, zero `# noqa`, and zero skipped tests are permitted without an explicit one-line justification in the code and in the corresponding `progress/lane-*.md`.
4. **Rule D (Periodic Self-Review)**: Each lane, after completing every 2 tasks, must perform a self-review by re-reading the corresponding spec sections line-by-line, documenting any discrepancy in `progress/lane-*.md`, and resolving it prior to proceeding.
5. **Rule E (Coverage Gates)**: Coverage gates from `spec/11_eval_and_testing.md` §11.1 are strictly enforced in CI:
   - `backend/app/rule_engine/`: **100%** line coverage.
   - `backend/app/llm/guards.py`: **≥ 95%** coverage.
   - Overall codebase: **≥ 80%** (starting at 60% baseline during foundational build).
6. **Rule F (Database Migration Gate)**: No lane may merge a PR touching database models or migrations (`backend/app/db/`) unless the real PostgreSQL CI job is 100% green.

---

## 4. Merge & Coordination Procedure

1. **Isolation**: Work happens strictly in each lane's worktree (`../abhyas-a` ... `../abhyas-d`) on its designated branch (`lane-a`, `lane-b`, etc.).
2. **Synchronization**:
   - Rebase or fast-forward from `main` regularly into lane branches (`git fetch origin && git merge --ff-only origin/main`).
   - PRs to `main` require a clean CI run on GitHub Actions before merging.
3. **Status Tracking**:
   - Update `progress/lane-<id>.md` after every task.
   - Root `PROGRESS.md` tracks consolidated multi-lane progress.

---

## 5. Requests for the coordinator

*(Lanes log requests for dependencies, schema adjustments, or shared file changes here)*
- None pending.
