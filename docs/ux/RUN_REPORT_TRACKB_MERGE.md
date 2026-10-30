# Run report: Track B merged into main

Merge commit `a100c96` ("Merge Track B: ..."), followed by one fix commit `38c8492`. Rollback tag `pre-trackb-merge` is on `cb42698`, the `main` and `origin/main` tip before the merge. Preconditions checked: `main` equalled `origin/main`, and `fix/flow-help-name-dash` was an ancestor of `main`.

## Conflict resolution
One conflict, `backend/app/web/templates/arp.html`, resolved as in `TRACKB_REPORT.md`: main's markup kept (`_dash_css.html`, `table-scroll`, CSV link row, `data-export="teachers"`, no dashes) and Track B's `support-line` added above the CSV row. The supportive badges, the visit-card support line and `_visit_checklist.html` merged cleanly.

Auto-merged files read and checked:
- `sessions/service.py`: Track B's changes are additive only. The flow-fix follow-up lead-in, quiet rule and help-question routing are intact. `web/teacher.py` offers the follow-up first, then the visit note, then today's focus. Fast start is wired at the learn step and in the button dispatch.
- Both message catalogs: Track B's blocks are appended, and the no-dash catalog test passes.
- `trainer.py` and `trainer.html`: the CSV routes from main remain, and the training-gap section and move card are added.

**Training-gap CSV is not wired.** The generic `/trainer/export/{table}.csv` reads `data-export` tables from the page. Using `training_gap_rows` needs a new route, which is more than a few lines, so it is left for later.

## Fix after the first gate
The first full run failed 2 tests (`test_csv_export.py::test_trainer_batches_csv_suppression_at_nine_and_ten`). The trainer fixture did not switch off the new training-gap section, so the page called the real query with a mock session. The fix was one line in the fixture, in commit `38c8492`, and the rerun is green.

## Gate (merged tree, tip `38c8492`)
Database server URL built from docker-compose.yml. Run through `scripts/pytest_fresh_db.py` on a fresh database, no `-q`, no other pytest running. Logs: `%TEMP%\trackb_merge_gate.log` (first run) and `trackb_merge_gate2.log` (second).

| Check | Result |
|---|---|
| Full pytest, first run | 2 failed, 2546 passed, 2 skipped (cause above) |
| Full pytest, rerun | 2548 passed, 2 skipped, 3 warnings in 966.91s |
| `ruff check .` | All checks passed |
| `mypy --strict backend/app scripts/keep_alive.py` | no issues, 195 files |
| Node tests (`chat`, `sw`) | 90 pass, 0 fail |
| `phone_layout_check.py` | 0 failing of 144 cells |
| `composer_layout_check.py` | 0 failure(s) |
| `dashboard_layout_check.py` | 0 failures |
| `check_first_load.py` | first load 130210 bytes, all assets 151331: PASS |
| `freeze_check.py --skip-gates --any-branch` | 4 passed, 0 failed (7 skipped) |
| No-dash catalog test (`PYTHONUTF8=1`) | passes in the full run |

The 2 skips are the frozen tab title and the evaluator-sample audio (a human input). A test or check run rewrites `eval/lowband/REPORT.md`; it was restored before the freeze check so the tree stays clean.

## Deploy
`render.yaml` has `autoDeploy: false`, so pushing deploys nothing. Deploy by hand when ready.

**Demo seed changed: yes.** `db/demo_data.py` adds the training-gap demo scenes and teacher turns for the cohort. `db/seed.py` opts `teacher.demo2` in to the daily tip. There is no schema change. The hosted demo needs the seed re-run once (`SEED_ON_BOOT` for one boot, or `make db-seed`) to show the new data. The shared logins are untouched.

## Rollback
- Undo the merge on main with a new commit: `git revert -m 1 a100c96` (also revert `38c8492` first, or let the revert conflict-check handle the test fix).
- Or inspect the previous state: `git checkout pre-trackb-merge` (detached).
