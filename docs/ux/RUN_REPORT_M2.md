# Run report M2: feat/v2-national merged into main

**Merge commit `e90b583`** (`--no-ff`), on top of M1 `8d6ce06`. Safety tag `pre-v2-merge-2` points at `8d6ce06`.

## Preflight
main = origin/main = `8d6ce06`; main was an ancestor of the branch; no conflicts. Branch head before the merge: `035543c`. All changes belong to the V2 areas (child strip, level sorter, talk moves, state labels, cluster pack, judge docs, tests, screenshots).

## What changed since the failed M2 attempt
- The placeholder test passes (11 tests alone and inside the full suite). No document needed a change.
- Child strip: a child who was only told the answer now shows "अटका हुआ · फिर अटका" after a new problem, read from the stored turn history (no engine, guard or schema change). Screenshots `docs/ux/v2/{dark,light}-strip_told.png`.
- Cluster pack: seed not extended (the demo ARP cluster is a deliberate 7-consenting-of-12 case); `docs/EVALUATOR_GUIDE.md` names `trainer.demo` for the full pack.
- `docs/ux/HUMAN_CHECKS.md` added.

## Gates
| Gate | Result |
|---|---|
| Full suite on the branch (fresh pgvector DB, port 5432) | `2095 passed, 1 skipped in 800.11s (0:13:20)` |
| After the merge | `git diff --stat feat/v2-national main` is empty, so the full suite was not run again |
| ruff, mypy --strict (178 files) | clean |
| node chat tests | 77 pass, 0 fail |
| composer layout check | 0 failures |
| Payload (offline assets) | 151,520 B of 153,600 B: measured headroom 2,080 B; real headroom about 1,580 B (tray chips are not rendered by the script) |

## What a deploy does
`render.yaml` has `autoDeploy: false`: nothing deploys by itself. The container runs `sh scripts/start.sh`, which runs `alembic upgrade head` on every start. **This merge adds no migration** (the class_checkin table came with M1). Seeding runs only when `SEED_ON_BOOT=true`. The cluster-pack demo check-ins are created by the seed, so the trainer pack is empty until a seed has run with this code.

## Rollback
`git revert -m 1 e90b583` (then push). M1 alone: `git revert -m 1 317c942`.

## Verified versus assumed
Verified: the suite, lint, types, Node tests, layout at three phone sizes in both colour schemes, payload. Assumed or not run: any real phone, live Claude phrasing, live WhatsApp, the hosted site, the build log of a real deploy. See `docs/ux/HUMAN_CHECKS.md`.
