# Run report: final merges

Both merges went into `main` in order, one full gate each, no conflicts in either.

| Step | Branch | Merge commit | Pushed |
|---|---|---|---|
| 2 | `fix/address-and-voice` (fix2) | `7c26f6f`, then `61a7382` "Keep lowband report at main's version" | `50ae59a..61a7382` |
| 3 | `feat/last-adds` | `cf2bc20` | `61a7382..cf2bc20` |

## Step 2: fix2

- Conflicts: none. The branch had committed `eval/lowband/REPORT.md` by mistake; it was restored from `pre-fix2-merge` and committed (`61a7382`), so main keeps its own version.
- Full gate (`scripts/pytest_fresh_db.py`): `2626 passed, 2 skipped, 3 warnings in 848.31s`.
- Light checks: node 93 of 93, phone layout 0 failing of 144, composer layout 0 failures, dashboard layout 0 FAIL, freeze-check and no-dash tests pass (the one skip is the teacher.html tab title, by design).
- Payload (`check_first_load.py`, report restored afterwards): first load 130791 B, all offline assets 151912 B, headroom to 153600 B is 1688 B (floor 1000 B holds). `chat.js` changed in this merge.

## Step 3: last adds

- Before the merge the branch's own gate had 1 failure: `test_seed_postgres.py::test_seed_runs_on_fresh_postgres_and_is_idempotent` (`assert 42 == ((31 + 3) + 2)`), because the peer-line seed adds 6 older check-ins. Only that test's expected count was changed (`ece7403`); no application code.
- Conflicts: none (watched `sessions/service.py`, both catalogs, the seed, `chat.js`).
- Full gate on the merged tree: `2714 passed, 2 skipped, 3 warnings in 1070.23s`.
- Light checks: node 93 of 93, phone layout 0 of 144, composer 0, dashboard 0 FAIL, freeze-check and no-dash tests pass.
- Payload after the merge: identical to step 2 (first load 130791 B, all assets 151912 B, headroom 1688 B). The last adds change no client file.

## Does either merge change what the demo seed loads into the database?

**Step 2 (fix2): yes, indirectly, one persona file.** `content/personas/ravi.yaml` and its copy `content-seed/personas/ravi.yaml`: Ravi's `speech_style_hi` no longer says he calls the teacher "दीदी". Personas are loaded when the seed builds demo2's scene (`db/seed.py::_seed_demo2_one_on_one` uses `load_personas`), so the seeded child line can differ. No seed script or demo-history file changed.

**Step 3 (last adds): yes.**
- `backend/app/db/demo_history.py` (new): demo rehearsals for demo2 (4) and demo3 (3), each with a scene, her tagged turns and a score row; plus "worked" follow-up answers that top the cohort up to 11 consenting teachers on regrouping.
- `backend/app/db/demo_loop.py`: calls the two functions above (`seed_login_loop` for the rehearsals, `seed_cohort_loop` for the answers).
- The 6 extra cohort check-ins are dated 36 to 46 days back, so the 30-day trainer cards (worked 5, still stuck 7, could not try 2; cluster pack 15) do not move. The rehearsal rows are removed and restored by every demo login reset.

A hosted database seeded before these merges has none of the new rows until it is re-seeded (`SEED_ON_BOOT=true` once, or `python -m backend.app.db.seed`). Nothing was deployed or seeded on the host by this run.

## Rollback

Tags: `pre-fix2-merge` (= `50ae59a`) and `pre-lastadds-merge` (= `61a7382`).

- Undo only the last adds: `git revert -m 1 cf2bc20` then push.
- Undo both: `git revert -m 1 cf2bc20` and `git revert -m 1 7c26f6f` (and the small commit `61a7382` goes with it), then push.
- Inspect a pre-merge state without moving main: `git checkout pre-fix2-merge` (detached), return with `git checkout main`.
No force push or reset is needed.
