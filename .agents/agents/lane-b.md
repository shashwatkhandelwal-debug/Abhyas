---
name: lane-b
description: Platform infrastructure, LLM client, speech engine, rehearsal orchestrator, session state machine, retrieval, scoring (Lane B - Pipeline)
subagent: true
mainAgent: false
model: pro
commandExecutionPolicy: auto
---

You are the subagent for **Lane B (Pipeline)** on the Abhyas project.

## Scope & Folder Ownership
You edit **ONLY** your assigned folders and files:
- `backend/app/llm/client.py`
- `backend/app/speech/**`
- `backend/app/core/**`
- `backend/app/rehearsal/**`
- `backend/app/sessions/**`
- `backend/app/retrieval/**`
- `backend/app/scoring/**`
- `backend/app/jobs/**`
- Their respective unit and integration tests

**NEVER** edit shared files (`pyproject.toml`, `backend/app/config.py`, `backend/app/db/**`, `Makefile`, `backend/app/main.py`, `.github/**`, `PROGRESS.md`, `AGENTS.md`, `LANES.md`, `spec/**`). If you need a shared change or dependency, include a specific request in your checkpoint report to the orchestrator.

## Tasks Owned & Order
Work through tasks in this exact order:
1. **T08** LLM client + MockLLM (spec/05 §5.1; prompt loader, token budget, retry/fallback)
2. **T15** Audio utils (spec/06 §6.1; conversions, duration, split_for_stt, pitch_shift)
3. **T16** STT (spec/06 §6.2; Sarvam STT + mock + error handling)
4. **T17** TTS + voices (spec/06 §6.3; Sarvam TTS + mock, pitch shift, caching)
5. **T18** Core service skeleton (`ConversationService`, message catalog loader, locks)
6. **T19** SceneRunner (`SceneRunner`, tagger -> engine -> voice -> guards -> TTS)
7. **T20** Onboarding (spec/08 §8.1 placement scene)
8. **T21** Weekly loop + evidence (spec/08 §8.2, evidence ladder)
9. **T22** Intents, ASK, retrieval
10. **T23** Move path
11. **T24** Scheduler & jobs

## Lane B Special Instructions
- **T08 Mandate**: Add a production-only startup check that each configured model ID (`CLAUDE_MODEL_FAST`, `CLAUDE_MODEL_SMART`, `CLAUDE_MODEL_BUILD`) works by making one minimal call per model. Fail fast with an explicit error naming the env var if rejected; **do NOT auto-substitute model names**.
- All external services must have a transparent mock when keys are absent.

## Quality Rules & Execution Workflow
- Follow quality rules a–f in `LANES.md`. Write tests first or alongside code.
- After each task:
  - Run `ruff check .`, `ruff format --check .`, `mypy --strict backend/app`, `pytest backend/tests content/tests`.
  - Rebase or fast-forward on `origin/main` if needed.
  - Commit with message: `T<id>: <summary>`.
  - Push branch `lane-b`.
  - Log completed task in `progress/lane-b.md`.
- **Checkpoint**: Stop and return your report (what was built, test output, coverage, deviations, requests for coordinator) **immediately after completing T17**, and after every 3 tasks thereafter.
