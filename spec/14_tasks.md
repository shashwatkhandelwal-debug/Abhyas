# 14 — Ordered task list

Priority: **P0** = must ship for 1 Nov; **P1** = should ship; **P2** = only if ahead of schedule. If behind schedule on 25 Oct, drop remaining P2s, then simplify P1s (as noted per task) — never drop P0s, tests or the freeze.

"Accept" = acceptance criteria; the task is done only when all are true and `make test` is green. Target dates are finish-by dates (IST).

## Phase A — Foundation

**T01 Repo restructure** · P0 · 12 Oct
Refactor scaffold to 02 §2.4 layout. Delete duplicate spec files and .docx (pack replaces them; copy pack into `spec/`, `AGENTS.md` and `CLAUDE.md` at root). Add MIT `LICENSE`, `Makefile` (AGENTS.md commands; stubs ok for later targets), update `pyproject.toml` deps (add: apscheduler, rank-bm25, rapidfuzz, regex, passlib[bcrypt], itsdangerous, cryptography, python-multipart, pdfplumber, pypdf, respx, hypothesis, freezegun, playwright (dev), scikit-learn (dev/eval); remove arq, redis), `.pre-commit-config.yaml` (ruff, mypy, gitleaks), `.gitignore` (.env, content/sources/*.pdf, *.wav, *.ogg except eval/samples and content/audio), CI workflow (12 §12.6), `PROGRESS.md`.
Accept: CI green on an empty test; `make setup` works; tree matches layout.

**T02 Config** · P0 · 12 Oct — `config.py` with every env var from `.env.example` and every threshold named in this pack (grep the pack for UPPER_CASE names). Provider selection logs mocks in dev; fail-fast on missing secrets in production. Accept: unit test that production mode without `ANTHROPIC_API_KEY` raises.

**T03 Database** · P0 · 13 Oct — SQLAlchemy models + Alembic migration for **all** tables in 03 (incl. invite_code, calibration_label); async session; `db/seed.py` skeleton; docker compose db. Accept: `make db-up db-migrate` on empty DB; downgrade/upgrade round-trip test.

**T04 Content models & seed content** · P0 · 13 Oct — pydantic Move/Persona/Problem models (10 §10.2, 04 types), YAML loader, JSON Schema export, copy `content-seed/*` to `content/`, validator checks 1, 2, 5, 6, 7 (3 and 4 after T07). Accept: `make content-validate` passes on 4 seed moves.

## Phase B — Core IP (no LLM)

**T05 Hindi utilities** · P0 · 13 Oct — `llm/hindi_numbers.py` (extract_numbers, to_words 0–199), `guards.norm`, `rule_engine/bugs/akshar.py`. Accept: exhaustive 0–100 word tests; akshar cases in 04.

**T06 Bug rules** · P0 · 14 Oct — all 12 rules + correct functions + step templates + registry. Accept: every cell of the 04 §4.2 tables as parametrised tests.

**T07 Rule engine** · P0 · 15 Oct — types, transitions, `RuleEngine.step`, placement mode, serialisation; finish validator checks 3–4 (model rehearsal must end all CORRECT; fix seed YAML acts if needed and note in PROGRESS). Accept: all 14 tests in 04 §4.5; 100% line coverage of `rule_engine/`.

## Phase C — LLM roles

**T08 LLM client + MockLLM** · P0 · 14 Oct — 05 §5.1; `llm_call` logging; prompt loader with versions; daily token budget guard (12 §12.8). Accept: unit tests for retry/timeout/fallback using a fake transport.

**T09 Guards** · P0 · 15 Oct — all guards in 05. Accept: ≥ 3 pass + ≥ 3 fail fixtures per guard.

**T10 act_tagger** · P0 · 16 Oct — prompt v1 + `content/act_examples_hi.yaml` (≥ 28 examples) + keyword fallback + 8 golden fixtures. Accept: guard tests; fallback tagger tests on 15 sentences; `make test-live` ≥ 85% exact act-set match on 20 labelled teacher turns (labels written by the team in `tests/golden/act_tagger/labelled.jsonl`).

**T11 child_voice** · P0 · 16 Oct — prompt, guard wiring, template fallback. Accept: for every ResponseKind a golden good + bad fixture; live guard pass ≥ 90% on 30 engine outputs.

**T12 coach** · P0 · 17 Oct — prompt, guards, deterministic fallback from signal_acts/feedback_bank, review_item on low confidence. Accept: golden tests; fallback produces valid feedback for every seed move.

**T13 fidelity_checker** · P0 · 17 Oct — prompt, guards, reply composition, keyword fallback.

**T14 intent_router, question_classifier, guide_answerer** · P1 · 20 Oct — (simplify if late: skip classifier's clarifying question.)

## Phase D — Speech

**T15 Audio utils** · P0 · 14 Oct — 06 §6.1 with fixtures (OGG/Opus, WebM/Opus, MP4/AAC, 60 s WAV). Accept: conversions + split tests; no files left on disk (assert tmp dir empty).

**T16 STT** · P0 · 16 Oct — sarvam + mock (+ bhashini/google stubs). Accept: mock tests; live test on 5 samples.

**T17 TTS + voices** · P0 · 17 Oct — sarvam + mock, number-to-words, pitch shift, cache, pre-warm; voice audition script `scripts/audition_voices.py` writing candidates to `eval/voices/` for the team to choose. Accept: cache hit test; OGG output validated by ffprobe (codec opus, mono).

## Phase E — Conversation

**T18 Core service skeleton** · P0 · 16 Oct — types, `ConversationService`, message catalog loader (missing key → startup error), per-teacher locks.

**T19 SceneRunner** · P0 · 18 Oct — tagger → engine → voice → guard → TTS; scene persistence; stop words; stage timings. Accept: integration test runs the Ravi example end-to-end with MockLLM (child lines guarded) and stores turns.

**T20 Onboarding** · P0 · 19 Oct — 08 §8.1 incl. placement scene. Accept: table-driven tests.

**T21 Weekly loop + evidence** · P0 · 20 Oct — 08 §8.2, evidence ladder. Accept: 08 §8.8 tests incl. full happy path.

**T22 Intents, ASK, retrieval** · P1 · 21 Oct — 08 §8.3–8.4; BM25 search; `seed_from_moves.jsonl`; escalation. (Simplify if late: BM25 only, no dense.)

**T23 Move path** · P1 · 21 Oct — 08 §8.5. (Simplify: fixed induction order for everyone.)

**T24 Scheduler & jobs** · P1 · 22 Oct — 08 §8.6 + fast-forward + fake clock tests. (Simplify: only followup_question, arp_digest snapshot, aggregates.)

## Phase F — Channels & web

**T25 Auth & demo users** · P0 · 17 Oct — 09 §9.7, seed users, guards, CSRF, login rate limit.

**T26 Web channel API** · P0 · 18 Oct — 07 §7.3. Accept: idempotency + polling tests.

**T27 Teacher chat PWA** · P0 · 20 Oct — 09 §9.2 complete (recorder, outbox/IndexedDB, SW, offline page, lite mode, demo sample chips, child strip). Accept: Playwright test (Chromium, mobile viewport) sends text + a fake-mic audio (`--use-fake-device-for-media-stream --use-file-for-fake-audio-capture=<sample.wav>`) and sees a reply; offline test: go offline, send, go online → delivered once; Lighthouse ≥ 90 recorded.

**T28 WhatsApp channel** · P0 code 21 Oct / P1 live · 07 §7.2 + `docs/whatsapp_setup.md`. Accept: webhook tests with real payload shapes; respx-mocked Graph calls; window/template tests. Live: round trip on the team test number (HUMAN INPUT creds) — record in PROGRESS.

**T29 Progress, consent, delete** · P1 · 22 Oct.

## Phase G — Deploy early

**T30 First hosted deploy** · P0 · **18 Oct** — Dockerfile, compose, render.yaml, Supabase, real keys if available (else mocks), `/healthz` with GIT_SHA. Team and testers use this URL from now on. Accept: hosted login + a mock rehearsal works on a phone over mobile data.

## Phase H — Reports & consoles

**T31 Demo data** · P1 · 22 Oct — 03 §3.5 synthetic cohort, demo banner.
**T32 ARP digest** · P1 · 24 Oct — 09 §9.3 (simplify: sections 1, 2, 4).
**T33 Trainer view + aggregates** · P1 · 24 Oct — 09 §9.4 with suppression tests (this test is P0 even if the page is simplified).
**T34 Coach review console** · P1 · 25 Oct — 09 §9.5 (simplify: rehearsal review + blind calibration; move editor = raw YAML + approve).
**T35 Admin** · P1 · 25 Oct — 09 §9.6.
**T36 Sankul mode** · P2 · 28 Oct — 08 §8.7 (minimal version acceptable).

## Phase I — Content, evaluation, testing

**T37 User-testing kit** · P0 · **14 Oct** — `eval/user_testing/consent_form_hi.md`, `exit_questions_hi.md`, `sessions.csv` header, `observer_guide.md`, findings templates (11 §11.6). Hand to field lead immediately.
**T38 Golden fixtures** · P0 · 17 Oct — ≥ 5 per runtime role (05 §5.11).
**T39 Evaluator samples** · P0 · 22 Oct — `make samples`: render `eval/samples/samples.yaml` lines to audio with a non-child adult voice via TTS (or team recordings if provided in `eval/samples/recorded/`), expose as demo chips.
**T40 Source ingestion** · P1 · 23 Oct (when PDFs arrive) — 10 §10.4. Retrieval golden test.
**T41 Latency benchmark** · P0 · 24 Oct, re-run 30 Oct — 11 §11.3 on hosted deploy; optimise until p95 < 20 s (document what was changed).
**T42 Kappa harness** · P1 · 27 Oct — 11 §11.4; report with whatever n exists on 30 Oct.
**T43 Guard report** · P1 · 29 Oct — 11 §11.7.
**T44 Realism report + blind pairs** · P2 · 29 Oct — 11 §11.5 (rating summary part is P1).
**T45 Content pipeline (generate/review/publish)** · P2 · 29 Oct — 10 §10.5 (publish step alone is P1: release + TTS pre-warm).

## Phase J — Hardening & submission

**T46 Round-1 fixes** · P0 · 28 Oct — implement fixes from `round1_findings.md`; each fix commit references the finding id.
**T47 Low-network verification** · P0 · 28 Oct — Playwright with network throttling (Slow 3G profile) + offline toggling; measured data per loop → README table.
**T48 Security pass** · P0 · 29 Oct — headers (CSP self-only, HSTS, X-Content-Type-Options), CSRF, rate limits, auth on audio endpoint, webhook signature, secrets scan, dependency audit (`pip-audit`).
**T49 Docs** · P0 · 30 Oct — README (13 §13.1), `docs/video_script.md`, `docs/deck_outline.md` (+ diagram PNG/SVG exports in `docs/deck_assets/`), `docs/demo_runbook.md` (exact click path for the video and live demo, reset steps), `docs/whatsapp_setup.md`, `docs/submission_checklist.md`.
**T50 Hosted smoke tests** · P0 · 30 Oct — Playwright script against prod: every role logs in and loads its home; one rehearsal turn completes; trainer page shows suppression.
**T51 GIF & screenshots** · P1 · 30 Oct — README GIF, deck screenshots (mobile frame).
**T52 Freeze** · P0 · **31 Oct 18:00** — 12 §12.9. Then submit (humans).

## Daily routine for the agent

Start of day: pull, read `PROGRESS.md`, run `make test`. End of day: update PROGRESS (done, next, blocked-on-humans), push. Every second day from 18 Oct: redeploy to Render and run T50 smoke script.
