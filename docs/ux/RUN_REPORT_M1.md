# Merge M1 report: runs A and B into main

- Preflight: branch feat/v2-national, head bf5d7a6 before merge; main 62014e5 was an ancestor; fetch clean. Tag `pre-v2-merge-1` created on 62014e5.
- Merge commit: 317c942 (`git merge --no-ff`, no conflicts). `git diff --stat feat/v2-national main` is empty: merged tree == tested tree.
- Full gate (on the branch, fresh DB, compose pgvector :5432): `1909 passed, 1 skipped in 718.56s (0:11:58)`. The skip is test_evaluator_samples.py:79 (needs SARVAM_API_KEY audio).
- Quick gate on merged main: ruff clean, `mypy --strict backend/app scripts/keep_alive.py` clean (173 files), node chat tests 75/75, composer_layout_check.py 0 failures.
- Payload (CRLF Windows tree): all offline assets 151,904 B raw, limit 153,600 B, headroom 1,696 B (chat.js 67,968, app.css 35,817). No client file changed in runs A/B/B2.
- Deploy behaviour: `scripts/start.sh` runs `alembic upgrade head` on every container start, so migration `e9b1d3f5a7c2` (table `class_checkin`) is applied automatically on deploy. Seeding runs only if `SEED_ON_BOOT=true` (default false). `render.yaml` has `autoDeploy: false`: pushing main does not deploy; a manual deploy is needed.
- Rollback: `git revert -m 1 317c942` (the migration is not undone automatically; `alembic downgrade -1` steps it back).
