# Phone redesign log

Branch `feat/phone-redesign`, from `fix/hindi-polish` head a10d1f5. Tag `pre-phone-redesign` marks the start.

## R1: inventory (before any code change): DONE

Strips between the top bar and the composer, in DOM order: demo banner (demo mode), the open-able demo shortcuts tray (`details#fast-track-tray`, its open state kept in sessionStorage), network banner (empty unless offline or slow), scene bar (two rows), status slot, the message list, then `div.helper-tray` (check-in and level entry chips, handbook question chips, `details#sample-tray`), then `div#next-card` (hint plus suggested line), then `footer.composer-wrapper`. Quick replies are rendered inside each message row, so the newest buttons scroll with the list.

Heights and positioning that depend on `vh`: `body {min-height: 100vh }` (app.css line 67), `.app-container { min-height: 100vh }` (75), `.chat-page { height: 100vh; height: 100dvh }` (1556), `.helper-tray { max-height: min(34vh, 7.5rem) }` (1561), `.source-excerpt { max-height: 40vh }` (578) and `.start-main { min-height: 100vh }` (1603). `position: sticky`: `.chat-header` and `.composer-wrapper`. The real cause on a phone: `body { min-height: 100vh }` is the large viewport, so with the address bar showing the page was taller than the visible window and scrolled. The chat shell's `100dvh` did not stop that.

Keyboard handling: there is no `visualViewport` code in chat.js. Only the viewport meta `interactive-widget=resizes-content` and a `max-height: 560px` media query that hid the helper tray, demo banner and tray. So there was nothing to reuse; the new code adds one small handler.

Tests that assert layout: `backend/tests/unit/test_composer_layout.py` (structure of template and CSS), `test_fast_track_tray_markup.py` (tray markup, which still holds), `test_teacher_pwa.py` (sample tray markup and the 150 KB budget), `backend/tests/js/chat.test.mjs` (one tray-persistence test), e2e tests that find `.reply-chip`, and the two scripts `scripts/composer_layout_check.py` and the new `scripts/phone_layout_check.py`.

## R2: real-phone harness first: DONE

`scripts/phone_layout_check.py` (new): sizes 360x560, 360x640, 393x852, 412x915; deviceScaleFactor 2.75; touch and mobile; Android Chrome UA; variants `normal`, `toolbar` (visible height minus 56 px, with every `Nvh` in the served stylesheet rewritten to the large viewport, so vh is wrong the way it is on a real phone) and `keyboard` (visible height minus 250 px, input focused); dark and light. Checks per cell: input fully inside innerHeight and hit-testable, mic/send/suggest fully on screen and at least 44 px, every quick-reply button fully visible and at least 44 px tall (first button only for a sideways-scrolling row), message list at least 120 px (80 with keyboard), page not scrolling vertically or horizontally, sheet at most 55 percent of the window.
The mic, send, suggest and horizontal checks were added after I saw in a screenshot that the send button was pushed off the right edge; the table below for the BEFORE state was taken with the earlier version of the checks (input, buttons, list height, page scroll), so it can only under-report the old bug.

BEFORE (commit `pre-phone-redesign`): it reproduces the bug. In every `toolbar` cell the input sits below the visible window and the page scrolls.

| state | 360x560 normal | 360x560 toolbar | 360x560 keyboard | 360x640 normal | 360x640 toolbar | 360x640 keyboard | 393x852 normal | 393x852 toolbar | 393x852 keyboard | 412x915 normal | 412x915 toolbar | 412x915 keyboard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| start | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS |
| consent | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS |
| name | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS |
| learn | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS |
| checkin_module | PASS | FAIL(dl) | FAIL(dl) | PASS | FAIL(dl) | FAIL(dl) | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS |
| checkin_outcome | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS |
| sorter_range | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS |
| sorter_result | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS |
| scene_checkin | PASS | FAIL(dl) | PASS | FAIL(dl) | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS | PASS | FAIL(dl) | PASS |
| sheet_handbook | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sheet_samples | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sheet_tray | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
39 failing of 108 state/size/variant cells (a cell fails if dark or light fails)

## R3/R4: redesign and re-run: DONE

AFTER (final run on this branch, same harness with the extra checks):

| state | 360x560 normal | 360x560 toolbar | 360x560 keyboard | 360x640 normal | 360x640 toolbar | 360x640 keyboard | 393x852 normal | 393x852 toolbar | 393x852 keyboard | 412x915 normal | 412x915 toolbar | 412x915 keyboard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| start | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| consent | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| name | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| learn | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| checkin_module | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| checkin_outcome | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| sorter_range | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| sorter_result | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| scene_checkin | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| sheet_handbook | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| sheet_samples | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| sheet_tray | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
0 failing of 144 state/size/variant cells (a cell fails if dark or light fails)

Sheet cells in the `keyboard` variant are weak by design: opening the keyboard closes the sheet, so they show the closed state.
