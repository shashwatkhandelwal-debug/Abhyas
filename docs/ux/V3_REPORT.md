# V3 report: Challenge 3 completion features

Branch `feat/v3-challenge3`, cut from `main` at `1caa36f`. Nothing was merged to `main` and nothing was deployed. No real provider was called (mocks only). No Render or Supabase setting was touched.

## Tasks

| Task | Status | Commit | Notes |
|---|---|---|---|
| V1 Follow-up loop | DONE | `1cd09f9` | Offer on chat open, three closed options, four closed reasons, deterministic replies, outcome stored once, tomorrow's-focus builder (pure, nothing sent). |
| V2 ARP checklist and reported vs observed | DONE | `b014383` | Server-rendered closed form on the ARP page, trainer card with the 10 rule. The seeded demo observations (V2c) are in V0. |
| V1-checkpoint full gate | DONE | tested at `b014383` | `2200 passed, 1 skipped in 806.57s`. |
| V3 Adaptive path | DONE | `1a5f54c` | Pure chooser, "why this next" line inside existing messages. |
| V0 Connected demo wiring | DONE | `37a669d` | `db/demo_loop.py`; demo2, demo3, cohort and visit notes; existing accounts only. |
| V4 Evaluator material | DONE | `5206065` | Guide, demo script, phone and human checks, pilot measurement plan. |
| FINAL | DONE | this commit | Gate below. |

No task was BLOCKED. No client file (`chat.js`, `app.css`, `teacher.html`), rule engine, guard, auth or WhatsApp delivery file was changed.

## Gate (final)

| Check | Result |
|---|---|
| `python scripts/pytest_fresh_db.py --server <local 5432>` | `2245 passed, 1 skipped in 803.56s (0:13:23)`; the skip is the evaluator-samples audio (HUMAN INPUT, as before) |
| `ruff check .` | All checks passed |
| `mypy --strict backend/app scripts/keep_alive.py` | Success: no issues found in 185 source files |
| `pytest backend/tests/unit/test_freeze_check.py` | 11 passed |
| `node --test backend/tests/js/chat.test.mjs` | tests 77, pass 77, fail 0 |
| `python scripts/phone_layout_check.py` | 0 failing of 144 cells |
| `python scripts/composer_layout_check.py` | 0 failure(s) |
| `python scripts/check_first_load.py` | PASS; first load 130226 B, all assets 151363 B, equal to the start of the run |

The full gate ran while three files (`config.py`, `act_tagger.py`, `test_act_tagger.py`) carried whitespace-only reformatting from a formatter run; they were put back to their committed content afterwards and the unit tests for them re-run (pass). The whitespace-only claim is from the diff, not from a second full run.

## Migrations to expect on deploy (names and order)

`scripts/start.sh` runs `alembic upgrade head` on every start. Head before this branch: `e9b1d3f5a7c2`. Single head after.

1. `a1c3e5f7b9d2_add_class_followup` (revises `e9b1d3f5a7c2`): tables `class_followup`, `class_followup_outcome`; column `teacher.tomorrow_focus_opt_in` (boolean, default false).
2. `b2d4f6a8c0e3_add_class_visit_observation` (revises `a1c3e5f7b9d2`): table `class_visit_observation`.

Both are additive; upgrade, downgrade and re-upgrade are tested on a fresh PostgreSQL (`test_migrations.py`).

## Flags and how to toggle them

Environment settings, each default off, each on in demo mode (`DEMO_MODE`, default true): `FOLLOWUP_ENABLED`, `OBSERVATION_ENABLED`, `ADAPTIVE_PATH_ENABLED`. To turn all off on a host set `DEMO_MODE=false` and leave the flags unset; to turn one on outside demo mode set it to `true`. Other tunables (weights, windows, closed lists) are in `backend/app/config.py`.

## Seed behaviour (when it runs)

- The demo loop rows are created only by `python -m backend.app.db.seed` (and so only when `SEED_ON_BOOT=true` on a boot) and by the per-login reset of `teacher.demo2` and `teacher.demo3` (login, logout, and the end of the seed). They are created only when `DEMO_MODE` is on (tested).
- demo2 gets a check-in from yesterday and a follow-up due today (relative to now), unanswered, on every reset. demo3 gets an older check-in answered "still stuck". The synthetic cohort gets follow-up answers for its seeded check-ins and visit notes for 12 teachers on regrouping.
- Every such row is marked demo (`is_demo`) and belongs to a demo teacher. A re-seed deletes and re-creates them. Visit notes a judge records as `arp.demo` on cohort teachers stay until the next re-seed.
- Until a seed has run with this code the trainer cards are empty (they say so).

## Rollback notes

- Code: revert the five task commits (or the merge commit once merged). With the flags unset and `DEMO_MODE=false` the new screens are absent and behaviour is the one before this branch.
- Database: the new tables and column are unused by older code and can stay. To remove them, `alembic downgrade e9b1d3f5a7c2` (drops the three new tables and the column, losing any follow-up or visit data).
- Demo rows: re-run the seed to rebuild them; the per-login reset restores demo2 and demo3.

## Findings worth knowing

- Existing behaviour, unchanged: at DONE the "next move" tap restarts the same move (the state machine does not advance `current_move_id`). With the adaptive flag on and some history, the tap now opens the chosen practice; with no history it behaves as before.
- The "still stuck" reply gives a different source (the struggle's second stored chunk) rather than a second tip text, because a struggle stores one tip. With one stored chunk it repeats the tip and says so; with none it says the material is not available yet.
- The follow-up is offered when the web chat opens; WhatsApp has no such event, so there it is not offered (see `docs/ux/V3_LOG.md`, V1e).
- The opt-in for tomorrow's focus has no screen (a settings control would need a page this build does not change), and nothing sends it.
- `scripts/check_first_load.py` rewrites the tracked `eval/lowband/REPORT.md`; that file was left modified and is not committed.
- A single `rm -rf` was issued on a temp path that did not exist (nothing deleted); recorded in `V3_LOG.md`.

## Verified vs assumed

Verified (run): the gate lines above, the new unit tests (follow-up 58, adaptive 36, visit form 16), the Postgres tests (visit and trainer 14, demo loop 9, migrations), the existing e2e directory and seed/reset tests after V0, payload bytes.

Assumed or not run: the hosted site, a real deploy (`alembic upgrade head` on Render/Supabase), real Claude phrasing, live WhatsApp (caps are tested on the planner, not live), any real phone, audio of the new messages, the whitespace-only claim for the three reformatted files.

## Only a human can verify on a real phone

See `docs/ux/PHONE_TEST_CHECKLIST.md` section J and `docs/ux/HUMAN_CHECKS.md` rows h to m: the follow-up buttons and reasons above the keyboard at 360 px, the ARP form with one thumb, the trainer card read aloud, the "why this next" line in the week-done message (needs a whole week), the wording as a teacher and an ARP would judge it, and WhatsApp reply-button and list behaviour with a real number.
