# Phone redesign report

Branch `feat/phone-redesign`, cut from `fix/hindi-polish` (tag `pre-phone-redesign` marks the start). Not merged, not deployed. The step-by-step log, with both layout tables, is `docs/ux/PHONE_REDESIGN_LOG.md`.

## Before and after

| | Before | After |
|---|---|---|
| Real-phone harness, 12 states x 4 sizes x 3 variants x dark and light | Reproduces the bug: with the browser toolbar showing, the input is below the visible window and the page scrolls in every state | 0 failing of 144 cells |
| Page scroll | The body was `min-height: 100vh` (the large viewport), so the page scrolled | `.chat-page` is `position: fixed; inset: 0`; only the message list scrolls |
| Strips above the composer | demo banner, open demo tray, network banner, two-row scene bar, helper tray (entry chips, handbook chips, sample line), hint bar | thin demo banner, one scene bar (wraps to at most two lines of pills), message list |
| Quick-reply buttons | inside each message row, scrolling with the list | the newest buttons are moved into one dock row above the input (single scrolling row, or up to two rows when there are 3 or fewer) |
| Handbook questions, sample lines, demo shortcuts, check-in and level-sorter entry chips | separate strips and an open tray | one bottom sheet opened by the "सुझाव" button; handbook questions open, the other sections folded; closed on every load |
| Hint text | separate bar, up to 3 lines | one line in the dock, wraps if long, hidden while the keyboard is open |

## What was removed or moved

- The helper tray and the demo tray left the main stack and now live in `#sheet`, which sits above the dock (`bottom: 100%`, at most 55 percent of the window, own scroll, close button, tap outside or Escape closes it).
- The tray's open state is no longer kept in the session, and the sample tray no longer opens by itself on desktop: the sheet is always closed on load (the spec asks for this).
- `.chat-page` no longer uses any `vh` height. The old `.helper-tray`, strip-sizing and short-window rules were deleted.
- New: `#dock`, `#action-row`, `#btn-suggest`, `#sheet`, `#sheet-close`, `#sheet-handbook`, new catalog keys `ui_chat_suggest` and `ui_sheet_close` (Hindi and English).
- Keyboard: there was no `visualViewport` code to reuse. `setupDock` adds one handler that sets a `kb` class when the visible height is under 420 px or has shrunk by more than 150 px. In that state the sheet, hint, demo banner and scene bar are hidden and the action row stays one scrolling row.

## Payload (`scripts/check_first_load.py`, exact bytes, all assets limit 153,600)

| | Before | After |
|---|---|---|
| all assets | 151,520 B (headroom 2,080 B) | 151,129 B (headroom 2,471 B) |
| first-load (chat page, css, js) | 130,383 B | 129,992 B |

Real headroom (measured minus about 500 B for the tray chips) is about 1,970 B, above the 1,000 B floor. The redesign first overshot the limit by 2,536 B. To get back under it, I did not touch behaviour. I compacted multi-line rules in `app.css` to single lines (about 1.9 KB) and converted `chat.js` indentation from two spaces to tabs (about 3 KB; there are no multi-line strings in it). These two whitespace changes make the diff for those files very large; the content is the same. The script now also prints exact bytes and headroom.

## Layout assertions I changed

- `backend/tests/unit/test_composer_layout.py`: rewrote four structural tests for the new shell (fixed shell, one flexible zone, dock contents, bounded closed sheet, `kb` rules); the input-outside-the-list test is unchanged.
- `backend/tests/js/chat.test.mjs`: the tray test now asserts the tray is not restored open and its state is not kept (spec: closed on every load). This is the one test that touches behaviour; the spec requires it.
- e2e tests: a new `open_sheet` helper in `backend/tests/e2e/conftest.py`; handbook chip, sample line and shortcut tests open the sheet first (a sent chip closes it, so it is reopened where needed). The sample-tray test no longer expects it to be open on desktop.
- `scripts/composer_layout_check.py`: relapse fixture label only (from the earlier fix).

## Verified (I ran these)

- `scripts/phone_layout_check.py`: 0 failing of 144 cells, final code.
- `node --test backend/tests/js/chat.test.mjs`: 77 pass.
- ruff check, mypy --strict (backend/app and keep_alive), freeze-check test, layout, PWA and tray unit tests: pass.
- Full gate (`scripts/pytest_fresh_db.py`, one run, log in %TEMP%) on the redesign commit: 2093 passed, 18 failed, 1 skipped. All 18 were e2e browser tests: chips inside the closed sheet (test setup), two real text-cut-off regressions (placeholder, hint ellipsis), and the demo banner and header Log out links, which I had hidden by mistake. I fixed those. After the fixes I re-ran the affected e2e files (cause-effect, demo helpers, handbook chips, journey, run5 artifacts): all pass in the final two runs (23 and 14 tests).
- Not run again after the fixes: the rest of the suite (unit, integration, other e2e). The CSS changed slightly after that full run (banner/header link rules, input padding, hint wrapping), so the final state has had the checks above but not a second full gate. Treat the full-suite status as assumed.

## Known limits and deviations

- The demo banner's Log out and dismiss are about 32 px tall (banner under 40 px is an existing test). The header Log out and the menu are 44 px or more. An invisible bigger hit area broke the clipping test, so I dropped it.
- Sheet cells in the `keyboard` variant only show the closed state, because opening the keyboard closes the sheet.
- The `toolbar` variant emulates a real address bar by rewriting `vh` in the served stylesheet. It matches how a phone behaves but is not a real phone.
- The screenshot folder keeps only the before/after subset in git (393x852 and 360x640, normal, dark and light, plus one toolbar pair). Many more screenshots from the harness runs sit untracked in `docs/ux/phone_redesign/`; I could not delete them under the rules.
- Scene bar: the group title is hidden when the window is 600 px tall or less (to keep the list at 120 px); the one-on-one strip label stays.

## What a human must check on a real phone

See section I of `docs/ux/PHONE_TEST_CHECKLIST.md`: input visible on every screen with Chrome's address bar showing, keyboard open and closed, sheet open and close, demo tray only inside the sheet, five log-out and log-in cycles, dark and light. Nothing here was run on a real device.
