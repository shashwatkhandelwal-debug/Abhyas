# Abhyas build pack

Everything a coding agent needs to build the Abhyas prototype for the 1 Nov 2026 build-stage submission.

**How to use**
1. Copy this whole folder into the root of the `Abhyas` repo (it adds `AGENTS.md`, `CLAUDE.md`, `spec/`, `content-seed/`, `.env.example`).
2. Tell the agent: *"Read AGENTS.md and follow it. Start with T01 in spec/14_tasks.md."*
3. Humans work through `spec/15_human_inputs.md` in parallel (API keys, WhatsApp, PDFs, coach review, teacher testing).

If your agent accepts only one file, give it `ABHYAS_BUILD_SPEC_FULL.md` (all files concatenated) instead.

| File | Contents |
|---|---|
| `AGENTS.md` (= `CLAUDE.md`) | entry point: rules, read order, commands, definition of done |
| `spec/01_product.md` | problem, solution, roles, constraints, scope IN/OUT, metrics |
| `spec/02_architecture.md` | layers, data flow, latency budget, pinned stack, repo layout, interfaces, failure behaviour |
| `spec/03_data_model.md` | full Postgres DDL, access rules, retention, seed + synthetic demo data |
| `spec/04_rule_engine.md` | deterministic AI children: 12 bug rules, transition table, exact step algorithm, required tests |
| `spec/05_llm_roles.md` | Claude client, 6 runtime + 4 build-time roles: prompts, schemas, guards, fallbacks |
| `spec/06_speech.md` | ffmpeg pipeline, Sarvam STT/TTS adapters, child voices, cache, latency instrumentation |
| `spec/07_channels.md` | WhatsApp Cloud API, web channel, full HTTP route table |
| `spec/08_conversation_flow.md` | onboarding + weekly state machines, intents, ASK, move path, scheduled jobs |
| `spec/09_web_apps.md` | teacher PWA (offline outbox, lite mode), ARP, trainer, coach console, admin, auth |
| `spec/10_content.md` | move/persona schema, validator, source ingestion, generation pipeline |
| `spec/11_eval_and_testing.md` | test suites, latency, kappa, realism, user-testing protocol, guard report |
| `spec/12_deploy_ops.md` | Docker, Render, Supabase, CI, cost guard, freeze procedure |
| `spec/13_submission.md` | README structure, credentials table, video script, deck outline, checklist |
| `spec/14_tasks.md` | 52 ordered tasks with priorities, dates, acceptance criteria |
| `spec/15_human_inputs.md` | what only the team can provide, owners, deadlines, fallbacks |
| `content-seed/moves/*.yaml` | 4 draft moves (subtraction, addition, place value, matra reading) — need coach review |
| `content-seed/personas/*.yaml` | Ravi (confident), Priya (shy), Aman (distracted) |
| `content-seed/messages_hi.yaml` | every Hindi string the product says |
| `content-seed/whatsapp_templates.yaml` | 6 utility templates to submit to Meta |
| `content-seed/eval_samples.yaml` | the 5 evaluator sample inputs |
| `.env.example` | every environment variable |
