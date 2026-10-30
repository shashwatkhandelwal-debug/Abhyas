# Run report: V3 merge into main

Run on 2026-10-30, local machine, in the main folder. Nothing was deployed and no Render or Supabase setting was touched. No real provider was called.

## Preflight

| Check | Result |
|---|---|
| Working tree | clean (the stale `eval/lowband/REPORT.md` change was restored first) |
| `git fetch origin` | ok |
| `main` and `origin/main` | both `1caa36f63516fbf036b6f660d20118b15c3c14f1` |
| `git merge-base --is-ancestor main feat/v3-challenge3` | exit code 0 |
| Branch head | `72c32f5020512fe8d489a38a662d8093490a4cf9` (6 commits: V1, V2, V3, V0, V4, FINAL) |
| `render.yaml` | `autoDeploy: false` |

`git diff --stat main...feat/v3-challenge3`: 40 files, 3858 insertions, 15 deletions. No change to `chat.js`, `app.css`, `teacher.html`, the rule engine, guards, login/auth or WhatsApp delivery. `backend/app/llm/roles/act_tagger.py` and `backend/tests/unit/test_act_tagger.py`: no diff. `backend/app/config.py`: 23 added lines only (the V3 flags, weights, windows and closed lists); no existing line changed.

## Merge

Safety tag `pre-v3-merge` points at `1caa36f`. Merge commit (`--no-ff`) on `main`: see the commit this file is committed on top of; its sha is printed in the final message. No conflicts. `git diff --stat feat/v3-challenge3 main` is empty, so the merged tree equals the branch tree already tested and the full gate was not run again.

## Gates (on merged main, local)

| Gate | Result |
|---|---|
| Full suite on the branch (fresh pgvector DB, port 5432), before the merge | `2245 passed, 1 skipped in 803.56s` (the skip is the evaluator-samples audio, a known HUMAN INPUT) |
| `ruff check .` | All checks passed |
| `mypy --strict backend/app scripts/keep_alive.py` | Success: no issues found in 185 source files |
| `node --test backend/tests/js/chat.test.mjs` | tests 77, pass 77, fail 0 |
| `python scripts/phone_layout_check.py` | 0 failing of 144 state/size/variant cells |
| `python scripts/composer_layout_check.py` | 0 failure(s) |
| `python scripts/check_first_load.py` | PASS; first load 130226 B, all assets 151363 B (unchanged from before the branch) |
| `pytest backend/tests/unit/test_freeze_check.py` | 11 passed |
| `alembic heads` | single head `b2d4f6a8c0e3` |

## What a deploy does

`autoDeploy` is false: nothing deploys by itself. When you deploy by hand, `scripts/start.sh` runs `alembic upgrade head` on every start. Migrations, in order:

1. `a1c3e5f7b9d2_add_class_followup`: tables `class_followup`, `class_followup_outcome`; column `teacher.tomorrow_focus_opt_in` (default false).
2. `b2d4f6a8c0e3_add_class_visit_observation`: table `class_visit_observation`.

Both are additive.

## Seed

Seeding runs only when `SEED_ON_BOOT=true` is set for a boot, or when `python -m backend.app.db.seed` is run by hand. The demo loop rows (demo2 follow-up due on every login, demo3 history, cohort follow-up answers and visit notes) are created only by that seed and by the per-login reset of the shared demo teachers, and only while `DEMO_MODE` is on. Until a seed has run with this code the trainer "reported vs observed" card and the pack are empty (they say so).

## Flags

`FOLLOWUP_ENABLED`, `OBSERVATION_ENABLED`, `ADAPTIVE_PATH_ENABLED`: default off, on in demo mode. Details in `docs/ux/V3_REPORT.md` and `docs/EVALUATOR_GUIDE.md`.

## Rollback

On `main`: `git revert -m 1 <merge sha>` (then push). The tag `pre-v3-merge` marks `main` before the merge. The new tables and column are unused by older code; to remove them, `alembic downgrade e9b1d3f5a7c2` (this drops the follow-up and visit data).

## Verified vs assumed

Verified, by the runs above: the gate lines, byte counts, single alembic head, branch ancestry, the diff scope.

Assumed or not run: the hosted site and a real deploy (the migrations on Render/Supabase), real Claude phrasing, live WhatsApp, any real phone, audio of the new messages. A second full-suite run on merged main was not done because the tree is identical to the tested branch. See `docs/ux/HUMAN_CHECKS.md` rows h to m and `docs/ux/PHONE_TEST_CHECKLIST.md` section J.
