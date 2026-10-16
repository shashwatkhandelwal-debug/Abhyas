# Lane E Progress (T24 Scheduler & jobs)

Branch: `lane-e` (base: `main` d7f7ccd)

## Tasks
- [~] T24 Scheduler & jobs — code and tests written; **DB-backed tests not yet run** (see Verification)

## What was built (`backend/app/jobs/`, all new files; `scheduler.py` and `__init__.py` untouched)
- `schedule.py` — pure IST/UTC arithmetic: `next_daily_at`, `next_weekly_at`, `week_start_ist`, `retry_delay`, `truncate_words`.
- `tunables.py` — scheduler constants, read from `settings` when present, else defaults (see Requests).
- `handlers.py` — `followup_question`, `arp_digest` snapshot, `aggregates`; `plan_recurring_jobs`; `schedule_followup_for_question`; `record_followup_from_button`; `latest_arp_digest_snapshot`; `HANDLERS` registry.
- `tick.py` — `run_due_jobs` (one job per transaction, `FOR UPDATE SKIP LOCKED`, savepoint per handler, retry with backoff, `failed` after `SCHEDULER_MAX_ATTEMPTS`), `fast_forward_teacher`, `plan_jobs`, `build_scheduler` / `start_scheduler` (60 s tick + hourly idempotent planner).
- `admin_api.py` — `POST /admin/fast-forward/{teacher_id}` (admin role + CSRF), returns advanced count and per-job outcomes.
- Tests: `tests/unit/test_jobs_schedule.py`, `tests/integration/test_jobs_scheduler.py` (skipped unless `TEST_DATABASE_URL`).

## Decisions
- Recurring jobs are planned by an idempotent `plan_recurring_jobs` (dedupe on an IST-date `slot` in the payload), run at start and hourly, instead of a daily "planner" job row: no bootstrap row, restart-safe.
- Delivery is at-least-once: send is the last handler step; the `done` commit follows. A crash in between can repeat a message, never lose one.
- A job that no longer applies (no consent, already answered, bad payload, escalated question) becomes `cancelled` with `last_error="skipped: …"`, not `failed`.
- `arp_digest` builds the snapshot via the existing `reports.arp_digest.generate_arp_digest` (it owns consent filtering) and stores it in the job payload. **No WhatsApp send**: ARPs are `app_user` rows with no stored contact, and `Channel.send` takes a `Teacher`.
- Template name sent is the spec key `tpl_followup_question`; logging `template_send` is the channel's job (it knows whether the send happened).
- Channel resolution: web by default; WhatsApp only when `WHATSAPP_ENABLED`, via lazy import of `backend.app.channels.whatsapp.WhatsAppChannel` (lane C).

## Out of scope / deferred
- `retention_purge`: skipped (spec: only if cheap). It depends on how the consent-withdrawal and delete-account flows (lane C, T29) write `consent_log`; guessing would risk deleting data.
- `weekly_prompt`, `reminder`, `followup_try_in_class`: outside the simplified T24 scope.

## Verification
- Run here: `ruff check`, `ruff format --check` on all new files (clean); `mypy --strict` on `schedule.py` (clean) and in `--ignore-missing-imports` mode on the rest (only errors caused by uninstalled SQLAlchemy/FastAPI aliases).
- Executed offline: the 12 pure tests in `test_jobs_schedule.py`, plus the real `build_followup_messages` against the real `messages_hi.yaml` (template and freeform paths, buttons `हाँ` / `नहीं` / `अभी नहीं`).
- **Not run** (sandbox cannot install packages): the DB integration suite, the freezegun test, `mypy --strict` with real dependencies, and the full `make ci`. These need CI or a machine with `TEST_DATABASE_URL`.

## Requests for the coordinator
1. `config.py`: add `SCHEDULER_ENABLED`, `SCHEDULER_TICK_SECONDS`, `SCHEDULER_PLAN_MINUTES`, `SCHEDULER_MAX_ATTEMPTS`, `SCHEDULER_RETRY_BASE_SECONDS`, `SCHEDULER_BATCH_LIMIT`, `AGGREGATES_HOUR_IST`, `ARP_DIGEST_WEEKDAY`, `ARP_DIGEST_HOUR_IST`, `FOLLOWUP_TOPIC_MAX_WORDS` (defaults are in `jobs/tunables.py`).
2. `main.py`: `app.include_router(backend.app.jobs.admin_api.router)`, and in `lifespan` call `start_scheduler()` and `shutdown()` the returned scheduler on exit.
3. Remove the three unused stubs in `jobs/scheduler.py` (and their `__init__` exports) when convenient.
4. Hook points for lane B sessions: call `schedule_followup_for_question(session, question, now=…, move_id=…)` after an answered question; call `record_followup_from_button(session, teacher_id, button_id, now=…)` for inbound buttons `followup_yes|no|not_now` (returns False if not a follow-up button).
5. Lane C: `compute_aggregates_for_batch` must stay at `backend.app.jobs.aggregates` (signature `(session, batch_id, move_id) -> AggModuleBatch`); the aggregates job fails with a clear error until that file is merged. The `/arp` page (T32) can read `latest_arp_digest_snapshot(session, cluster_id)`.
6. ARP contact: if the ARP digest should go out on WhatsApp, a stored contact for `app_user` is needed.

## T42 kappa harness (offered to lane D; new files only, nothing in lane D's folders edited)
- `eval/calibration/kappa.py` — stdlib-only: `cohen_kappa` (unweighted / quadratic), `bootstrap_ci` (seeded percentile), `exact_agreement`, `confusion_matrix`, `pairwise_agreement` (AI vs each coach, coach vs coach), `criterion_agreement`, `render_report` (always states n; warns on n<20, kappa<0.70, undefined kappa).
- `backend/tests/unit/test_eval_kappa.py` — 14 tests, all passing here: textbook 2x2 (kappa 0.4), quadratic kappa vs the Fleiss-Cohen moment identity on random data, match with scikit-learn (unweighted and quadratic), undefined-kappa, deterministic bootstrap, pairwise on shared items, report honesty.
- `ruff` and `mypy --strict` clean on both.
- Not done: loading `calibration_label` / `rehearsal_score` rows (needs the real `scores` JSON shape from T34) and the `make eval-kappa` wiring; lane D's `evaluate_kappa.py` scaffold is untouched.
- Request: `from eval.calibration...` imports work under `python -m pytest` (CI) but not bare `pytest`; add `eval` to `[tool.setuptools] packages` or set pytest `pythonpath = ["."]` in `pyproject.toml`.

## T23: deterministic move-path scoring

- New pure module `backend/app/sessions/path_score.py` (spec/08 §8.5) plus `backend/tests/unit/test_path_score.py` (10 tests). No existing file touched; Lane B owns `sessions/` and can adopt `rank_moves` in `path.py`.
- Spec gaps resolved: a past `sankul_month` ranks 0 (due now); an unknown or missing month ranks 11; the class-1 bonus needs class 1 AND (literacy OR id starts `NUM_PLACE_VALUE`); ties break by month then move id; reasons are machine-readable codes, not Hindi.
- Verified: ruff format/check and mypy --strict clean; 10/10 tests pass offline by loading the module directly (the `sessions/__init__` import chain needs pydantic_settings, which this sandbox lacks). CI should run it normally.
- Request to Lane B: replace the hard-coded `DEFAULT_INDUCTION_ORDER` and `candidate_moves` table in `sessions/path.py` with `rank_moves(...)` fed from the published `MoveCard`s; `content/induction_track.yaml` does not exist yet.
