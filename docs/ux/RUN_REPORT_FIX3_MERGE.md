# Run report: fix3 merge into main

Merge commit: `b55bee4` ("Merge fix3: bug hunt fixes (P0 demo delete, repeats, address, banners, tips)"),
`--no-ff` of `fix/fix3` (`ae6c78b`) into `main` (was `221b047`). No conflicts. Pushed to `origin/main`.
Not deployed.

## Checks before the merge

- Address words: every child line quoted in the K1 transcripts in `docs/ux/BUGHUNT_REPORT.md` was
  checked against the teacher's gender: 29 lines, 0 mismatches. The male-teacher Ravi run uses only
  "सर" (11 of 11 lines), the three female-teacher runs (compare, Priya, Aman) only "दीदी" (15 of 18
  lines; the other 3 have no address word).
- Correction to the bug hunt report: the K1 section says "0 of 28 scene lines". The correct count is 25
  scene lines (Ravi male 7, compare 6, Priya 6, Aman 6; the first 4 lines of the Ravi male transcript are
  the onboarding practice replayed by the driver). The result is unchanged: 0 near-repeats, highest
  similarity 0.79. `ae6c78b` was not amended.

## Clean gate

Run from a detached worktree of the merged `main` in `%TEMP%\gate_main`, no `.env` there,
`PYTHONPATH` set to that folder (`backend.app.config` imported from the worktree).

| Step | Result |
|---|---|
| `scripts/pytest_fresh_db.py` (no `-q`, log `%TEMP%\gate_merge.log`) | 2759 passed, 2 skipped, 0 failed (933 s) |
| `check_first_load.py` | PASS: first load 131,207 B, all assets 152,328 B, headroom to 153,600 = 1,272 B (>= 1,000); `eval/lowband/REPORT.md` restored |
| Node tests (`chat.test.mjs`, `sw.test.mjs`) | 94 passed, 0 failed |
| Phone layout check | 0 failing of 144 cells |
| Composer layout check | 0 failures |
| Dashboard layout check | 12 of 12 PASS, 0 failures |
| Freeze-check + no-dash tests | 80 passed, 1 skipped (existing skip: page bytes frozen) |

The two pytest skips are existing ones (`test_dash_free.py:123`, `test_evaluator_samples.py:79`).
`ruff check` and `mypy --strict` were clean on the branch before the merge and the merge changed no code.

## What the merge contains

Bug hunt fixes B01, B02, B03, B07, B08, B09 and K1 to K7 (see `docs/ux/BUGHUNT_REPORT.md`), the
`scripts/bughunt` driver and journeys, and the bug hunt report and log.

## Demo seed changed: action needed once

demo2 now has 6 messages with the follow-up card first (the card plus the 5 seeded rehearsal messages,
card older than the rehearsal block, already marked offered). The shared demo accounts only pick this up
when the demo data is reseeded: set `SEED_ON_BOOT=true` for one deploy (or use the admin "Reset demo"), as in
`docs/DEPLOY.md`. A demo login or logout also resets that teacher to the seeded state.

No schema change, no new dependency, no new environment variable.

## Rollback

- Tag `pre-fix3-merge` points at the old main (`221b047`).
- Undo the merge without rewriting history: `git revert -m 1 b55bee4` on `main`, then push. (If this report
  commit and later commits are on top, revert still works; resolve any conflict in the report files.)
- To look at the old state: `git checkout pre-fix3-merge`.
