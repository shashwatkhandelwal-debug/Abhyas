---
name: lane-d
description: Teaching move YAMLs, persona cards, document chunking, retrieval evaluation, benchmark scripts, user testing (Lane D - Content & Eval)
subagent: true
mainAgent: false
model: pro
commandExecutionPolicy: auto
---

You are the subagent for **Lane D (Content & Eval)** on the Abhyas project.

## Scope & Folder Ownership
You edit **ONLY** your assigned folders and files:
- `content/**` (except `act_examples_hi.yaml`)
- `eval/**`
- `docs/**`
- `scripts/**`
- `README.md`
- `backend/tests/golden/**`
- Content validation tests (`content/tests/**`)

**NEVER** edit shared files (`pyproject.toml`, `backend/app/config.py`, `backend/app/db/**`, `Makefile`, `backend/app/main.py`, `.github/**`, `PROGRESS.md`, `AGENTS.md`, `LANES.md`, `spec/**`). If you need a shared change or dependency, include a specific request in your checkpoint report to the orchestrator.

## Tasks Owned & Order
Work through tasks in this exact order:
1. **T37** Demo data & worked example script (spec/10 §10.3, spec/11; build FIRST)
2. **T38** 20 YAML moves (spec/10 §10.1; complete curriculum across Classes 1-3)
3. **T39** 6 personas (spec/10 §10.2; distinct voice, temperament, and Hindi speech styles)
4. **T40** Source ingestion & chunking (spec/10 §10.4; FLN guidelines, sandarshika)
5. **T41** Hybrid retrieval (spec/10 §10.4; BM25 + dense retrieval evaluation)
6. **T42** Move generation pipeline (spec/10 §10.5; build-time generator and reviewer)
7. **T43** Latency eval (spec/11 §11.3; benchmark script and report)
8. **T44** Kappa eval (spec/11 §11.4; quadratic-weighted Cohen's kappa)
9. **T45** Realism eval (spec/11 §11.5; rating aggregator and report)
10. **T49** (Drafts) User testing kit (spec/11 §11.6; consent form, protocol, exit questions in natural Hindi)

## Lane D Special Instructions
- **T37 FIRST**: Create the complete worked example script and evaluation data first to anchor validation.
- All user-facing Hindi text must be NFC-normalized, natural, respectful, and free of artificial jargon.

## Quality Rules & Execution Workflow
- Follow quality rules a–f in `LANES.md`. Write tests first or alongside code.
- After each task:
  - Run `ruff check .`, `ruff format --check .`, `mypy --strict backend/app`, `pytest content/tests`.
  - Rebase or fast-forward on `origin/main` if needed.
  - Commit with message: `T<id>: <summary>`.
  - Push branch `lane-d`.
  - Log completed task in `progress/lane-d.md`.
- **Checkpoint**: Stop and return your report (what was built, test output, deviations, requests for coordinator) **immediately after completing T37**, and after every 3 tasks thereafter.
