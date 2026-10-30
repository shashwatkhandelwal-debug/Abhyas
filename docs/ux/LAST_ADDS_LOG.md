# Last adds log

Branch `feat/last-adds`, cut from `main` at `50ae59a` (worktree `abhyas-last-adds`; the brief named the main folder, which keeps `main` checked out, so a new worktree was used and `PYTHONPATH` pointed at it; the config path check printed a path inside the worktree before any test ran).

Payload (no client file changed by this build): first load 130210 B, all offline assets 151331 B, limit 153600, measured with `scripts/check_first_load.py --report-path <temp>` so the tracked `eval/lowband/REPORT.md` is not touched.

## Decisions

- "मेरी प्रगति" already existed as `btn_progress` (a one-line stub in the DONE state). With `MY_PROGRESS_ENABLED` the same button and the typed words open the new message on the LEARN, MODEL, FEEDBACK and DONE screens only; inside a scene, a rating, a check-in or any free-answer step the words keep their old meaning. Flag off: the stub as before.
- Entry buttons: it was already in the week-done and follow-up closing buttons; this build adds it as a third button at the end of practice feedback (flag on only), so feedback shows "फिर से अभ्यास", "आगे बढ़ें", "मेरी प्रगति".
- The closing buttons follow the screen she is on: FEEDBACK keeps retry and continue, DONE gives next move, practice and the check-in entry (3 at most), other screens give their own help buttons plus `btn_mp_practice` ("अभ्यास करें", 11 characters, opens that move's practice).
- A "rehearsal" is a stored `rehearsal_score` row (retries count). Facts come from the teacher turns of its scene: asked how or why (`ask_to_explain`), told the answer (`tell_answer`), concrete objects (`concrete_representation`), named a child (group scenes only, an addressed child other than "all"). The trend compares the earliest and latest rehearsal of the move she practised most recently twice or more (read from her last 20 rows). Different moves only: it says a comparison needs the same move and gives the strength and step from her latest practice. Her own words are never quoted.
- Peer line scope uses `Teacher.consent_share_scores`, the same consent the dashboards use, excludes the asking teacher, and keeps demo and real teachers apart (a real teacher can never see a demo count). The limit is `AGGREGATION_SUPPRESSION_N` (10).
- Peer line placement: before the closing buttons so a screen never ends on the line. After "still stuck" and, for "could not try", after the reason is chosen (the reason question comes first and has no line). Not after "worked".
- Demo history for L1d lives in `db/demo_history.py` (new), called from `seed_login_loop` so the demo reset removes anything a session adds and restores exactly these rows (ids outside the cohort prefixes `0004` and `0005`).
- Demo "worked" answers for L2b: the cohort is topped up to 11 consenting teachers with a "worked" answer on regrouping. Those rows are dated 36 to 46 days back, which is inside the 60-day peer window but outside the 30-day windows of the cluster pack and "reported vs observed", so the numbers on those cards did not move (worked 5, still stuck 7, could not try 2 among consenting teachers in the last 30 days, checked on a seeded scratch database).

## Tasks

| Task | Status | Notes |
|---|---|---|
| L1 My progress | DONE | `class_profile/my_progress.py`, `sessions/rehearsal_view.py`, `SessionRepository.rehearsal_history`, handler 1d in `sessions/service.py`, catalog keys `mp_*` and `btn_mp_practice` (hi and en), seed in `db/demo_history.py`; 32 unit tests, 3 privacy tests, Postgres tests on a seeded database |
| L2 Peer line | DONE | `class_profile/peer_worked.py`, `SessionRepository.peer_worked_teachers`, `_with_peer_line` in the service, catalog key `pw_line`, cohort top-up in the seed; 44 unit tests (scope rule, fallback, n below 10, consent, window, demo and real kept apart, she is not counted, both languages, flag off), Postgres tests |
| L3 Docs | DONE | `docs/EVALUATOR_GUIDE.md` (new section with taps per account), `docs/ux/PHONE_TEST_CHECKLIST.md` (section L); freeze-check test 11 passed before and after |

Note on commits: the two features share plumbing (`config.py`, `repository.py`, `service.py`, `demo_loop.py`, the fake repository and the two catalog files). Those shared files are in the L1 commit; the files that belong to L2 alone (`peer_worked.py`, its tests) are in the L2 commit.
