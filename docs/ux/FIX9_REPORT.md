# FIX9 report

Branch `fix9`, from main `8811a45`. Fixes only, not merged. `offline.html`, `sw.js`, `chat.js` and `app.css` untouched. No code, seed, migration or content change.

## 1. /trainer/move/* card page

`trainer_move.html` used `var(--text, #1c1f1d)`. `--text` is not defined anywhere, so the dark fallback applied in both themes (1.08:1 on the dark background). Now `var(--ink)` for body text and `var(--muted)` for the source line (both already themed in `app.css`).

Ratios (computed from the theme values): light ink #1F2421 on #FAF7F2 14.75:1; dark ink #F0EDE8 on #141816 15.34:1; dark muted #A3ACA7 on #141816 7.69:1. Links keep the fix8 colours.

## 2. /review/calibrate bubbles

Bubbles had fixed light backgrounds with the page ink (light in dark theme): 1.01:1. In `review_calibrate.html` only:

- Light: bubble text fixed #1F2421 (13.4 to 14.0:1 on the four bubble backgrounds).
- Dark: bubble backgrounds #194D40 / #1B2F52 / #4A2236 / #33284F with text #F0EDE8 (8.3 to 11.6:1).
- Speaker tags: the old child colours were 4.19 to 4.42:1 on light bubbles, so they are now #1F58C0, #A8336A, #6444B0 (5.5 to 6.1:1); teacher tag #1F6F5C is 5.11:1. In dark the tags use the bubble text colour.

Not changed (out of scope): the other `--brand`-on-dark headings on this page, listed in the FIX8 sweep. They need an `app.css` change.

## 3. cluster_pack.py:108: test environment only, no change

Line 108 is `rows = (await session.execute(stmt)).all()`. The `await` is present and correct.

Evidence:
- The error appears only when `CLUSTER_PACK_ENABLED` is true (or `DEMO_MODE`, via `v2_enabled`). `CLUSTER_PACK_ENABLED=true pytest test_support_framing.py` reproduces `TypeError: 'coroutine' object is not iterable` at line 108. With the flag at its default (False) the file passes.
- `test_support_framing.py` gives `/arp` a `AsyncMock(spec=AsyncSession)` as the DB and mocks `build_arp_digest` but not `build_cluster_pack`. On an `AsyncMock`, `execute()` returns a mock whose `.all()` is itself an async mock, so it returns a coroutine. A real `AsyncSession` returns a `Result`.
- Against real Postgres (local pgvector, fresh DB) with `TEST_DATABASE_URL` set, `test_support_framing.py` and `test_cluster_pack_postgres.py` all pass (41 tests). That includes a cluster with exactly 10 consenting teachers (the one in the support-framing test), N and N+6 teachers, struggles reaching the threshold, and the ARP page rendering the pack.

So the ARP cluster meeting pack is not broken for 10 or more consenting teachers. The flag in the failing environment was on (probably `.env` or demo mode). If you want the unit test hermetic, mock `build_cluster_pack` or pin the flag off in that fixture; not done, as asked.

## Checks

- node tests: chat 82, idb 17, sw 22, all pass.
- ruff check: clean. mypy --strict: clean (203 files).
- `scripts/check_first_load.py`: PASS, 130,189 B first load, 152,587 B all offline assets (headroom 1,013 B), unchanged. Its rewrite of `eval/lowband/REPORT.md` was reverted.
- pytest unit, filtered to asset budget, first-load, js harness, dashboard, review, trainer, arp, calibration files: pass, except below.
- `test_speech_budget.py::test_speech_budget_tracker_limits` fails (`daily_spend` 30.0 vs 10.0). It fails identically on unmodified main here; not related to this change, not investigated.
- Contrast ratios above are computed from the CSS values, not from a browser sweep.
