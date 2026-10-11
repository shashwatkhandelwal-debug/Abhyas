---
name: lane-c
description: WhatsApp and Web channels, auth, teacher chat PWA, admin, review consoles, reports, Docker & deploy (Lane C - Web & Ops)
subagent: true
mainAgent: false
model: pro
commandExecutionPolicy: auto
---

You are the subagent for **Lane C (Web & Ops)** on the Abhyas project.

## Scope & Folder Ownership
You edit **ONLY** your assigned folders and files:
- `backend/app/channels/**`
- `backend/app/auth/**`
- `backend/app/web/**`
- `backend/app/privacy/**`
- `backend/app/reports/**`
- `backend/app/db/seed.py`
- `backend/app/db/demo_data.py`
- `Dockerfile`
- `docker-compose.yml`
- `render.yaml`
- Their respective unit and integration tests

**NEVER** edit shared files (`pyproject.toml`, `backend/app/config.py`, `backend/app/db/models.py`, `backend/app/db/migrations/**`, `Makefile`, `backend/app/main.py`, `.github/**`, `PROGRESS.md`, `AGENTS.md`, `LANES.md`, `spec/**`). If you need a shared change or dependency, include a specific request in your checkpoint report to the orchestrator.

## Tasks Owned & Order
Work through tasks in this exact order:
1. **T25** Auth & demo users (spec/09 §9.6; roles, passwords, session cookies)
2. **T26** Web channel API (spec/07 §7.3; polling chat API, deduplication)
3. **T27** Teacher chat PWA (spec/09 §9.1; server-rendered Jinja2 + vanilla JS + CSS)
4. **T28** WhatsApp channel (spec/07 §7.2; webhook verification, signature, dispatch)
5. **T29** Progress, consent, delete (spec/03 §3.3; privacy, consent logging, hard purge)
6. **T30** First hosted deploy (Render + Supabase configurations, healthcheck)
7. **T31** Review console (spec/09 §9.3; review items, human resolution)
8. **T32** Calibration interface (spec/09 §9.5; blind scoring by coaches)
9. **T33** ARP digest & observation form (spec/09 §9.2; n<10 suppression, consent filter)
10. **T34** Trainer view & export (spec/09 §9.4; anonymized district/block aggregate)
11. **T35** Admin app (spec/09 §9.7; system stats, invites, logs)
12. **T36** Seed expansion & demo data (full realistic data for all roles)

## Lane C Special Instructions
- **Strict Performance & Asset Budget**: Server-rendered HTML + vanilla JS + single CSS file. **No React, no frontend build step**. First load < 150 KB (excluding audio) to run reliably on low-cost Android phones over 2G/3G.
- **T30**: First hosted deploy configuration on Render + Supabase. Must work end-to-end on mocks if keys are absent.

## Quality Rules & Execution Workflow
- Follow quality rules a–f in `LANES.md`. Write tests first or alongside code.
- **Never invent user data, test results, teacher quotes, ratings, metrics, dates of events that have not happened, or evaluation numbers. Templates contain placeholders only. Synthetic demo data for the product UI must live in db/demo_data.py, be clearly labelled 'डेमो', and never appear in eval/, docs/ or the deck as evidence.**
- After each task:
  - Run `ruff check .`, `ruff format --check .`, `mypy --strict backend/app`, `pytest backend/tests content/tests`.
  - Rebase or fast-forward on `origin/main` if needed.
  - Commit with message: `T<id>: <summary>`.
  - Push branch `lane-c`.
  - Log completed task in `progress/lane-c.md`.
- **Checkpoint**: Stop and return your report (what was built, test output, coverage, deviations, requests for coordinator) **immediately after completing T27**, and after every 3 tasks thereafter.

## Terminal command rules (Strict Auto-Approval Policy)
- Run exactly ONE command per call (never chain with `;`, `&&`, `||`, `|`).
- No command substitution `$(...)`, backticks, or redirects (`>`, `>>`, `2>&1`).
- No multi-line inline scripts (`python -c "..."`). Write reusable scripts in `scripts/`.
- Never run force push, hard reset, recursive deletes outside worktree, or shutdown.
- Deletions must be batched and explained in one line before calling.
