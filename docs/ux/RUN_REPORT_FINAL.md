# Final run report (V2 runs C to G): M2 merge NOT done

**Status: main is at the M1 state (`8d6ce06`). The branch `feat/v2-national` holds everything from runs C to G and is pushed.**
M2 was not merged because the full gate failed twice on the same test and the run's rule is not to merge in that case.

## Why M2 stopped

| Gate | Result |
|---|---|
| C1, attempt 1 | 6 failed, 2080 passed, 1 skipped (strip label inside the title element a browser test reads; mocked ARP test consumed by my extra query). Fixed. |
| C1, rerun | **2087 passed, 1 skipped** (12:32) |
| M2, attempt 1 | 1 failed, 2086 passed, 1 skipped: `test_freeze_check.py::test_the_repo_itself_has_no_unlisted_placeholders`. Cause: the hosted-URL placeholder token in my new `docs/ux/PHONE_TEST_CHECKLIST.md`. Reworded. |
| M2, rerun | 1 failed, 2086 passed, 1 skipped: the same test. Cause: my own `docs/ux/OVERNIGHT_LOG.md` quoted the placeholder token while describing the first failure. |

Both causes are the same slip (a document I wrote contains a placeholder that `scripts/freeze_check.py` only allows in listed docs), so the rule applied. After the second failure I removed the token from the log and ran that test file on its own: it passes (11 tests). The full suite has **not** been run again, because the rule says not to continue after a second failure. All other 2086 tests passed in both M2 runs, and ruff, `mypy --strict`, the Node tests (77), the layout check and the payload check are green on the branch head.

**To finish the merge (a human decision):** run the full gate once on `feat/v2-national`, and if it is green, `git checkout main`, `git tag pre-v2-merge-2 main`, `git merge --no-ff feat/v2-national -m "Merge V2 runs C-G: child strip, level sorter, talk moves, state labels, cluster pack, judge docs"`, re-run the quick gate, push. `render.yaml` has `autoDeploy: false` and main is an ancestor of the branch, so the merge is clean.

## Items

| Item | Status | Notes |
|---|---|---|
| 0.2 drop gate logs | DONE | two tracked logs removed; `_stats_tmp.txt` was untracked, got committed by mistake once and was removed again |
| 0.3 check-in content integrity test | DONE | `test_checkin_content_integrity.py` |
| 0.4 feminine-form scan | DONE (report only) | no change needed; masculine few-shot examples **not** added (the tagger prompt slices the first 28 examples, so extra entries never reach it; needs a code change) |
| 0.5 M1 merge | DONE | `docs/ux/RUN_REPORT_M1.md`; main `317c942` (merge) and `8d6ce06` |
| C child strip | DONE | flag `CHILD_STRIP_ENABLED`; "stuck again" only after "getting it"; a told-answer relapse shows "stuck" (no record in saved state) |
| D level sorter | DONE | flag `LEVEL_SORTER_ENABLED`; activities from stored UP handbook chunks, multigrade line for reading only |
| E1 talk-move feedback | DONE | flag `TALK_MOVES_ENABLED`; from tagged acts, no model call |
| E2 national / state labels | DONE | no flag; tie-break only on equal scores; one existing citation test updated to expect the label |
| F cluster pack | DONE | flag `CLUSTER_PACK_ENABLED`; ARP (cluster) and trainer (district); demo ARP cluster is hidden by the n<10 rule on purpose |
| C1 checkpoint | DONE | 2087 passed, 1 skipped |
| G1 evaluator guide | DONE | demo hint messages: none added (login code off limits) |
| G2 keep-alive window | DONE | 2-9 Nov 2026, 18 Nov if shortlisted |
| G3 demo script | DONE | outputs from mock-path runs |
| G4 pitch notes | DONE | supplied evidence only; the mentor row is marked a design judgement |
| G5 QA sheet, PROGRESS | DONE | no kappa value |
| G6 screenshots | DONE for 5 of 6 | cluster pack page not capturable by the layout tool (database-backed page) |
| G7 phone checklist | DONE | |
| M2 | **NOT MERGED** | see above |

## Payload (bytes, all offline assets, limit 153,600)

Baseline 151,904 before run C; after the child strip 152,031; before the final trim 152,118; **now 151,520 (headroom 2,080)** after removing two long comments in `chat.js`, one in `app.css` and blank lines. The measuring script does not render the tray chips of an onboarded teacher: the level chip adds about 322 B to the page, the check-in chip a similar amount, so the real headroom is about 1,500 B. The served static files contain no carriage returns on this checkout, so the LF figure is the same.

## Flags and how to toggle

All default **off**, on in demo mode through `v2_enabled(flag)` (`flag or DEMO_MODE`): `CLASS_CHECKIN_ENABLED`, `CHILD_STRIP_ENABLED`, `LEVEL_SORTER_ENABLED`, `TALK_MOVES_ENABLED`, `CLUSTER_PACK_ENABLED`. Setting `DEMO_MODE=false` turns all off (and hides other demo-only screens); setting one flag to `true` turns that one on. These are environment settings; nothing was changed in Render.

## Migrations to expect on deploy

Run A/B's migration `e9b1d3f5a7c2` (table `class_checkin`) is already on main (M1) and runs automatically at container start (`alembic upgrade head` in `scripts/start.sh`). **Runs C to G add no migration.** Seeding runs only with `SEED_ON_BOOT=true`; the demo check-ins behind the cluster pack are created by the seed, so the trainer pack is empty until a seed has run with this code.

## Rollback

- M1 (already on main): `git revert -m 1 317c942` (the table stays; `alembic downgrade -1` steps it back).
- M2 (not merged): nothing to roll back. If merged later: `git revert -m 1 <merge sha>`.

## Verified versus assumed

Verified: the full suite on a fresh pgvector database (twice green apart from the placeholder test), lint, types, Node tests, layout at three phone sizes in both colour schemes, page weight, 22 PostgreSQL tests for the cluster pack, the seed idempotency test. Assumed or not run: any real phone, live Claude phrasing (all demo-script outputs are mock path), live WhatsApp, the hosted deployment, the final full suite after the last documentation edit.

## Open risks

- The act tagger on the hosted site may tag a line differently from the scripted tagger used in the demo script, so strip labels can differ.
- The two UP handbooks are machine-read; level-sorter pages are pointers to check.
- The demo ARP login shows the privacy message, not a pack; judges who expect a pack there should use the trainer login.
- Render free plan cold start (about a minute) and shared demo accounts.

## Only a human can

Deploy main by hand (autoDeploy is false); re-run the full gate and merge M2; phone tests (`docs/ux/PHONE_TEST_CHECKLIST.md`); real Claude and WhatsApp checks; UptimeRobot through 9 Nov (18 Nov if shortlisted); read the Hindi in `docs/ux/DEMO_SCRIPT.md`; review the masculine-form wording.
