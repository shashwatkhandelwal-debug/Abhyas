# AGENTS.md — Build instructions for the coding agent

You are building **Abhyas**, a voice-first practice partner for government primary (FLN, Classes 1–3) teachers in Hindi, for the AI for Foundational Learning Hackathon 2026 (Challenge 3: Teacher Support and Training), Team Asymptotes.

This build pack is the **single source of truth**. It supersedes `ARCHITECTURE.md`, `Abhyas_ARCHITECTURE.md` and the `.docx` already in the repo. Where the existing scaffold disagrees with this pack, change the scaffold.

## Hard deadline

- **Build-stage submission: 1 Nov 2026, 23:59 IST.** Target internal freeze **31 Oct 2026, 18:00 IST**.
- After submission: **no commits** to the submitted branch/tag. Evaluation runs on the frozen state.
- Evaluators get ~1 hour hands-on with a **hosted web link**, **test credentials for every role**, and **3–5 sample inputs**. They will test **low-connectivity behaviour**. Everything you build must serve that hour.

## Read order

1. `spec/01_product.md` — what, who, scope (IN / OUT)
2. `spec/02_architecture.md` — layers, components, repo layout, stack (pinned)
3. `spec/03_data_model.md` — schema, RLS, seed data
4. `spec/04_rule_engine.md` — **core IP**: deterministic AI children
5. `spec/05_llm_roles.md` — every Claude prompt, schema, guard, fallback
6. `spec/06_speech.md` — STT / TTS / audio pipeline
7. `spec/07_channels.md` — channel abstraction, WhatsApp Cloud API, web channel, HTTP API
8. `spec/08_conversation_flow.md` — state machine, intents, message catalog, templates, jobs
9. `spec/09_web_apps.md` — teacher web chat (PWA), ARP, trainer, coach review console, admin, auth
10. `spec/10_content.md` — move/persona formats, source ingestion, generation pipeline
11. `spec/11_eval_and_testing.md` — unit/integration tests, kappa, latency, realism, user-testing protocol
12. `spec/12_deploy_ops.md` — Render + Supabase, env vars, CI, freeze procedure
13. `spec/13_submission.md` — README, deck, video script, submission checklist
14. `spec/14_tasks.md` — **ordered task list with acceptance criteria. Work through it in order.**
15. `spec/15_human_inputs.md` — things only humans can provide; how to proceed without them

Seed data: `content-seed/` (moves, personas, Hindi message catalog, WhatsApp templates, eval samples). Copy into the repo locations given in `spec/10_content.md`.

## Working rules

1. **Work task by task from `spec/14_tasks.md`.** One task = one or more commits with message `T<id>: <summary>`. Do not start a task until its dependencies pass.
2. **A task is done only when its acceptance tests pass locally** (`make test`) and CI is green.
3. **Keep `PROGRESS.md` at repo root**: per task — status, date, what was built, deviations from spec, open issues. Update after every task.
4. **Never invent credentials, phone numbers, API keys, official document contents, page numbers or teacher data.** Where the spec says **HUMAN INPUT**, check `spec/15_human_inputs.md`: build against the mock/fallback described there, add a line to `PROGRESS.md › Blocked on humans`, and continue with the next task. Do not stall.
5. **Every external service has a mock** selected by env var. With an empty `.env`, `make dev` must run the full product end-to-end on mocks. Tests never call real external services.
6. **Children's answers come only from the rule engine.** No LLM ever decides what a simulated child answers. This is the product's central claim; tests enforce it.
7. **Every LLM output is schema-validated and guarded before use** (`spec/05_llm_roles.md`). On guard failure: one retry, then a deterministic template fallback. Log every failure.
8. **No secrets in git.** No real teacher data in git. `.env` is gitignored. CI runs a secret scanner.
9. **All thresholds and tunables live in `backend/app/config.py`.** No magic numbers elsewhere.
10. **Hindi text is NFC-normalised** at every boundary (input, content load, LLM output).
11. Code quality: Python 3.11, `ruff` + `mypy --strict` clean, pydantic v2 models at every boundary, type hints everywhere, async I/O.
12. **Front-end is server-rendered HTML + vanilla JS + one CSS file. No React, no build step.** Pages must stay light (< 150 KB first load excluding audio) for low-cost Android phones on 2G/3G.
13. When the spec is silent, choose the simplest option that keeps the demo reliable, record the decision in `PROGRESS.md › Decisions`, and move on.
14. If you find a contradiction inside this pack, the order of precedence is: `AGENTS.md` > `14_tasks.md` > the numbered spec file most specific to the topic.

## Commands the repo must support (create the Makefile)

| Command | Does |
|---|---|
| `make setup` | create venv, install deps (incl. dev), install pre-commit |
| `make dev` | run API + web + scheduler locally on port 8000 with mocks if keys absent (uses local Postgres+pgvector via docker compose — see 03) |
| `make db-up` / `make db-migrate` / `make db-seed` | start local Postgres+pgvector, apply Alembic migrations, load content + demo data |
| `make test` | ruff, mypy, pytest (unit + integration, mocks only) |
| `make test-live` | opt-in tests that hit real providers (skipped if keys absent) |
| `make eval-latency` / `make eval-kappa` / `make eval-realism` | eval scripts in `eval/` |
| `make content-validate` / `make content-publish` | content pipeline |
| `make samples` | render the evaluator sample voice notes into `eval/samples/audio/` |
| `make freeze` | run the freeze checklist script (`spec/12_deploy_ops.md`) |

## Definition of done for the whole build

- Hosted URL works for every role in the credentials table (`spec/13_submission.md`).
- A teacher can complete one full weekly loop (LEARN → EXPLAIN_BACK → MODEL → REHEARSE → FEEDBACK → RETRY → TRY_IN_CLASS → REFLECT → DONE) **by voice in Hindi** on the web channel, and the same on WhatsApp when credentials exist.
- The Ravi worked example and the tell-answer relapse test pass.
- p95 voice-in → voice-out latency < 20 s on the hosted deploy (report in `eval/latency/REPORT.md`).
- ARP digest and trainer view render with consent filtering and n<10 suppression.
- Low-network mode works and is documented in README.
- README, `.env.example`, AI-services list, LICENSE, sample inputs, demo video script all present.
