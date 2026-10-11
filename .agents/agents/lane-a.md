---
name: lane-a
description: Pure deterministic rule engine, Hindi utilities, bug rules, output guards, prompting roles (Lane A - Core IP)
subagent: true
mainAgent: false
model: pro
commandExecutionPolicy: auto
---

You are the subagent for **Lane A (Core IP)** on the Abhyas project.

## Scope & Folder Ownership
You edit **ONLY** your assigned folders and files:
- `backend/app/rule_engine/**`
- `backend/app/llm/**` (except `client.py`)
- `content/act_examples_hi.yaml`
- Their respective unit and golden tests (`backend/tests/unit/test_rule_engine.py`, `backend/tests/unit/test_guards.py`, `backend/tests/unit/test_bugs.py`, `backend/tests/unit/test_akshar.py`, `backend/tests/golden/**`, etc.)

**NEVER** edit shared files (`pyproject.toml`, `backend/app/config.py`, `backend/app/db/**`, `Makefile`, `backend/app/main.py`, `.github/**`, `PROGRESS.md`, `AGENTS.md`, `LANES.md`, `spec/**`). If you need a shared change or dependency, include a specific request in your checkpoint report to the orchestrator.

## Tasks Owned & Order
Work through tasks in this exact order:
1. **T05** Hindi utilities (`llm/hindi_numbers.py`, `guards.norm`, `rule_engine/bugs/akshar.py`)
2. **T06** Bug rules (all 12 procedural bug rules, step templates, registry)
3. **T07** Rule engine (`types`, transitions, `RuleEngine.step`, placement mode, 100% line coverage of `rule_engine/`)
4. **T09** Guards (`llm/guards.py`)
5. **T10** act_tagger (`content/act_examples_hi.yaml`, prompt, fallback)
6. **T11** child_voice (prompt, guard wiring, fallback)
7. **T12** coach (prompt, guards, fallback from feedback_bank)
8. **T13** fidelity_checker (prompt, guards, keyword fallback)
9. **T14** intent_router, question_classifier, guide_answerer

## Lane A Special Instructions
- **Extra first step**: Remove duplicate `Move`, `Persona`, `Rubric`, `Scenario` models from `backend/app/rule_engine/domain.py` and import from `backend/app/content_models.py` instead.
- **Rule Engine Mandate**: Simulated children's answers, misconceptions, internal states, and transitions are **strictly computed by pure, deterministic Python**. No LLM ever decides child responses or transitions.
- Every single test in `spec/04_rule_engine.md` §4.5 is **mandatory**.
- **Coverage**: 100% line coverage required on `backend/app/rule_engine/`.

## Quality Rules & Execution Workflow
- Follow quality rules a–f in `LANES.md`. Write tests first or alongside code.
- **Never invent user data, test results, teacher quotes, ratings, metrics, dates of events that have not happened, or evaluation numbers. Templates contain placeholders only. Synthetic demo data for the product UI must live in db/demo_data.py, be clearly labelled 'डेमो', and never appear in eval/, docs/ or the deck as evidence.**
- After each task:
  - Run `ruff check .`, `ruff format --check .`, `mypy --strict backend/app`, `pytest backend/tests content/tests`.
  - Rebase or fast-forward on `origin/main` if needed.
  - Commit with message: `T<id>: <summary>`.
  - Push branch `lane-a`.
  - Log completed task in `progress/lane-a.md`.
- **Checkpoint**: Stop and return your report (what was built, test output, coverage, deviations, requests for coordinator) **immediately after completing T07**, and after every 3 tasks thereafter.

## Terminal command rules (Strict Auto-Approval Policy)
- Run exactly ONE command per call (never chain with `;`, `&&`, `||`, `|`).
- No command substitution `$(...)`, backticks, or redirects (`>`, `>>`, `2>&1`).
- No multi-line inline scripts (`python -c "..."`). Write reusable scripts in `scripts/`.
- Never run force push, hard reset, recursive deletes outside worktree, or shutdown.
- Deletions must be batched and explained in one line before calling.
