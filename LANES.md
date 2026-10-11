# Phase 2 — Parallel Development Lanes Architecture

This document defines the 4 isolated parallel development lanes for Abhyas, per `spec/14_tasks.md` and project governance.

## 1. Lane Ownership & Responsibilities

| Lane | Branch | Worktree Path | Port | Scope / Phase | Primary Specs | Tasks Owned | DB Required |
|---|---|---|---|---|---|---|---|
| **Lane A** | `lane-a` | `../abhyas-a` | 8001 | Core IP (Rule Engine, Hindi Utils, Bug Rules) | `04_rule_engine.md`, `05_llm_roles.md` §5.2 | T05, T06, T07 | No (pure deterministic algorithms) |
| **Lane B** | `lane-b` | `../abhyas-b` | 8002 | Platform & Channels (LLM Client, Speech, WhatsApp, Web App, Auth, Session DB) | `03`, `05` (roles), `06`, `07`, `08`, `09` | T08, T09–T14, T15–T17, T18–T22, T25–T29 | Yes (docker compose Postgres) |
| **Lane C** | `lane-c` | `../abhyas-c` | 8003 | Operations & Analytics (Review Console, ARP Digest, Trainer View, Scoring, Jobs) | `03`, `08` §8.9, `09` §9.3–§9.6, `12` | T23–T24, T30–T37 | Yes (docker compose Postgres) |
| **Lane D** | `lane-d` | `../abhyas-d` | 8004 | Content, Evaluation & Documentation (YAML Moves, RAG, Evals, CI Freeze) | `01`, `10`, `11`, `12`, `13` | T38–T52 | No (uses mock services and offline scripts) |

---

## 2. Quality Rules (Enforced on Every PR & Merge)

1. **Rule A (CI Parity)**: Every PR must pass `make ci` (`ruff check .`, `ruff format --check .`, `mypy --strict backend/app`, `pytest`, `content/tests`, secret scanning) locally and on GitHub Actions before the coordinator merges.
2. **Rule B (Test-First / Acceptance Strictness)**: No task is marked "done" without passing all acceptance tests listed in `spec/14_tasks.md` for that task. Tests are written FIRST or alongside, never after "it works".
3. **Rule C (Zero Lint / Type Suppressions)**: Zero `# type: ignore`, zero `# noqa`, and zero skipped tests are permitted without a explicit one-line justification in the code and in the corresponding `progress/lane-*.md`.
4. **Rule D (Periodic Self-Review)**: Each lane, after completing every 2 tasks, must perform a self-review by re-reading the corresponding spec sections line-by-line, documenting any discrepancy in `progress/lane-*.md`, and resolving it prior to proceeding.
5. **Rule E (Coverage Gates)**: Coverage gates from `spec/11_eval_and_testing.md` §11.1 are strictly enforced in CI:
   - `backend/app/rule_engine/`: **100%** line coverage.
   - `backend/app/llm/guards.py`: **≥ 95%** coverage.
   - Overall codebase: **≥ 80%** (starting at 60% baseline during foundational build).
6. **Rule F (Database Migration Gate)**: No lane may merge a PR touching database models or migrations (`backend/app/db/`) unless the real PostgreSQL CI job is 100% green.

---

## 3. Merge & Coordination Procedure

1. **Isolation**: Work happens strictly in each lane's worktree (`../abhyas-a` ... `../abhyas-d`) on its designated branch (`lane-a`, `lane-b`, etc.).
2. **Independent Databases**:
   - Lane A: SQLite / memory / mock only (no DB required).
   - Lane B: Database `abhyas_b`.
   - Lane C: Database `abhyas_c`.
   - Lane D: Database `abhyas_d`.
3. **Synchronization**:
   - Rebase or merge from `main` regularly into lane branches (`git fetch origin && git merge origin/main`).
   - PRs to `main` require a clean CI run on GitHub Actions before merging.
4. **Status Tracking**:
   - Update `progress/lane-<id>.md` after every task.
   - Root `PROGRESS.md` tracks consolidated multi-lane progress.
