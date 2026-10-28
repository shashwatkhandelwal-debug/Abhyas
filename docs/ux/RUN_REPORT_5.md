# Run report 5: composer visibility, demo shortcuts tray, handbook fallback, first feedback

Branch `fix/composer-and-tray` (from `main` 4fdb62e). Commits: T1 ee2cbee, T2 75b925a, T3 bbf1e6c, T1b 4bc725a, T5 65f6f81.
Everything below was run in this session unless marked **assumed**. No Anthropic API call was made. Real Android
Chrome was not available: all browser results are Chromium (Playwright 1.62) emulating phone viewports.

## Task 1: input bar always visible

**Reproduction** (`scripts/composer_layout_check.py`, real app + mock providers, dark and light, address-bar height
56 px removed, keyboard emulated by shrinking the viewport; screenshots in `docs/ux/before_task1/`):

| size | no keyboard | keyboard open (-250 px) |
|---|---|---|
| 360x640 | input on screen, chat only 80 to 81 px tall | **input, mic and send pushed below the viewport** (start and scene); chat 32 px |
| 393x852 | fine | fine |
| 412x915 | fine | chat 106 px on the start screen |

The exact Android report (input missing with no keyboard) did not reproduce at these sizes; the same mechanism shows
at 360x640 as a collapsed chat and, with the keyboard up, as a missing composer. Larger Android font scaling, which
I did not emulate, would make it worse (**assumed**).

**Cause.** `app.css` had `.chat-page .app-container > * { flex: none }`: every strip above the chat (header, demo
banner, tray, network banner, scene bar, helper tray up to 34vh, hint card) refused to shrink, and the chat was the
only shrinkable item (`min-height: 0`). When the strips summed to more than the viewport the composer, last in the
column, was pushed past the bottom of an `overflow: hidden` page. Evidence: with the tray hidden by injected CSS,
360x640 gives chat 201 px instead of 81 px. Comparison with 896b960 (git show, no checkout): that block, the
helper-tray rule and the 560 px media query are identical there; the difference is the open tray added by the Step 3
commit dda0af9 (about 120 px of non-shrinking chrome). Step 0 to 2 (manipulatives, quote badge) and b32d92a
(suggest-on-tap) did not change the layout rules. So: latent flaw, triggered by the tray.

**Fix.** Header and composer are `flex: none`; every strip between them is `flex: 0 1 auto; min-height: 0;
overflow-y: auto`; the chat is `flex: 1 1 0; min-height: 6rem` and scrolls inside itself; the helper tray is bounded
to `min(34vh, 7.5rem)` (handbook row and sample row are single scrolling rows, the sample list is a closed
`<details>`); the tray, banner and helpers disappear below 560 px of height; `interactive-widget=resizes-content` on
the chat page's viewport meta makes the keyboard shrink the page (height stays `100vh` then `100dvh`). **T1b**:
my first version used `flex: 1 1 auto` for the chat, which squeezed the scene bar and hint card even with room; the
e2e clip checks caught it and `flex: 1 1 0` fixed it.

**Tests.** `backend/tests/unit/test_composer_layout.py` (input outside the scrolling region, chat floor, strips
shrink, bounded suggestion area, keyboard meta). `scripts/composer_layout_check.py` fails when input, mic or send is
outside the viewport, when the newest quick reply is not inside the chat region or not tappable, or when the chat is
under 90 px; run by hand (needs Chromium, not part of `make test`):
`python scripts/composer_layout_check.py [--keyboard 250] [--shots docs/ux]`. Result after the fix: 0 failures at
360x640, 393x852, 412x915, both themes, start / consent / learn / scene, with and without a 250 px keyboard. After
screenshots: `docs/ux/task1_after/`.
Limits: the keyboard is emulated by viewport height, not by a real soft keyboard; with a 250 px keyboard at 360x640
the hint card is squeezed to a scrolling strip (still reachable).

## Task 2: demo shortcuts tray

Done as specified: collapsed by default, state kept in `sessionStorage`; title "डेमो शॉर्टकट" / "Demo shortcuts"; the
title was unreadable because the tray used tokens that do not exist (`--surface-2`, `--text-muted`, `--primary`),
so in dark mode a white card carried pale text; it now uses the app tokens. Chip C always visible and enabled.
A1/A2/B are hidden and disabled unless a subtraction scene (board `a` < 100) is active **and** `FAST_TRACK_IDLE_MS`
(30000, one constant) passed with no activity. Activity: any click, send (text, button, audio), typing, starting a
recording; a pending reply, outbox drain, recording or in-flight chip also postpone it. Timer starts when a
subtraction scene appears, cleared at scene end, page hide, pagehide, logout; paused while hidden. Never auto-sent.
One hint line shows while they are away (`ui_fast_track_hint`, both languages). 90 s cap, in-flight lock, offline
path unchanged. A side finding: the old code kept A1/B enabled after a scene ended (stale board text); now the gate
uses the scene header only.
Tests: 10 Fast-Track tests in `chat.test.mjs` with fake timers (0 s / 29 s / 30 s, activity reset, non-subtraction,
onboarding/no scene, a >= 100, units rule, scene end, hide/visible, pending, lock, 90 s) and
`test_fast_track_tray_markup.py`. Existing tests that assumed immediate availability and were updated: the A1 test,
the B test and the "disable on tap, re-enable" test (all three in `chat.test.mjs`); `test_fast_track_permutations.py`
unchanged and passing. Screenshots `docs/ux/task2/` (collapsed, open, and after 31 s idle in a scene, both themes).
Note: a mid-edit slip converted two escaped Hindi strings in `chat.js` into raw Devanagari; the repo's own guard
`test_templates_and_chat_js_have_no_hardcoded_hindi` caught it and they are back to `\u` escapes (identical to main).

## Task 3: handbook fallback

Code: `backend/app/handbook/fallback.py` using catalog key `handbook_fallback`. **I could not reproduce an English
passage.** Run before changing anything: Hindi UI gives the Hindi lead-in, the stored Hindi summary and the Hindi
citation; English UI gives the English lead-in plus the Hindi summary and citation. `fallback_reply` never reads the
chunk's English `text`; the English original is only returned by `/api/source/...`, the source-chip drawer. The
English passage the report describes is therefore most likely that drawer being opened, or a different deployed
data set (**assumed**, not checked on the hosted site). Content-only changes made: both catalogs now say the summary
is the handbook's own and end with a line sending the reader to the source chip (`मूल अंश पढ़ने के लिए नीचे स्रोत दबाएँ।` /
"Tap the source below to read the original passage."); the English lead-in says the summary is in Hindi.
Test `test_handbook_fallback_language.py`: 10 questions x hi/en (lead-in from the catalog, stored summary, citation,
no original text, length), and the chat flow end to end in both languages. Retriever and guards untouched.

## Task 4: specific first feedback (investigation only, no change)

"Very good! Now I know where to start for you." is catalog key `placement_done` (`content/messages_hi.yaml` line 54,
`messages_en.yaml` line 20), appended by `backend/app/sessions/service.py` around line 1383 in the
`PLACEMENT -> READY` branch. That branch runs two scene turns and sends the child's reply plus this fixed text. The
scene's coach feedback (`coach_feedback()` with evidence quotes, `service.py` ~1739) exists only in the weekly
REHEARSE end-of-scene branch; the onboarding branch never calls it (no coach call, no `MIN_TURNS` check, and it has no
move rubric: `current_move_id` is set only after placement). Making it quote the teacher needs code in the service
(assemble turns/acts, call the coach with a rubric or a short placement rubric, pass a `{quote}` placeholder), so by
the brief I changed nothing. Options: (a) add `placement_done_quote` and pass the teacher's first placement line,
verified as a substring of the transcript (smallest change); (b) run the real coach with the onboarding scene; (c)
leave as is. **Separate finding that matters for the demo:** the live feedback bubble is created without
`speaker="coach"` (`service.py` ~1854), and `chat.js` only draws the quote badge for coach-speaker messages. In the
real flow the «quote» therefore shows as plain text (0 badges on the page in both themes). The badge itself works
(harness screenshot below). One-line fix in `service.py`, but it changes the speaker label and translate button on
that bubble, so left for a decision.

## Task 5: verification artifacts

Run with real Postgres (`pgserver`) and the seeded app, mock providers: `backend/tests/e2e/test_e2e_run5_artifacts.py`
(`RUN5_SHOTS_DIR=docs/ux/task5`). Boards: before regroup "4 बंडल और 3 तीलियाँ", after "3 बंडल और 13 तीलियाँ (1 बंडल खुला)".

demo2 (subtraction; one regroup line, then "बस"), identical in light and dark:
```
आपके अभ्यास पर सुझाव:
आपने ठोस चीज़ (बंडल और तीलियाँ) इस्तेमाल की, इसलिए रवि को दिखा कि कहाँ क्या करना है।
(यह सुझाव एक विशेषज्ञ भी देखेंगे।)
👍 आपने बच्चे से उसका तरीका पूछा, इससे उसकी असली उलझन सामने आई। आपके शब्द: «रवि, तुमने 43 में से 27 कैसे घटाया? मुझे एक-एक कदम बताओ।»
🔁 उत्तर बताने के बजाय दो उत्तर सामने रखकर पूछिए कि कौन-सा सही है।
🗣️ अगली बार ऐसे कहकर देखें: "तुमने पहले एक उत्तर कहा था, अब तीलियाँ गिनकर दूसरा आया। कौन-सा ठीक है, और क्यों?"
रवि असली कक्षा के बच्चे जैसा लगा? 1 (बिल्कुल नहीं) से 5 (बिल्कुल वैसा ही) चुनें।
```
demo3 (literacy; 3 lines to Ravi, Priya, Aman, then "बस"):
```
आपके अभ्यास पर सुझाव:
आपने रवि से समझाने को कहा, इसलिए उसका अपना तरीका सामने आया।
(यह सुझाव एक विशेषज्ञ भी देखेंगे।)
👍 अभी आपके शब्दों में इस अभ्यास की कोई ख़ास बात साफ़ नहीं दिखी; नीचे का सुझाव आज़माकर दोबारा कोशिश करें।
🔁 पूरा शब्द दोहरवाने के बजाय पहले अक्षर पर उँगली रखवाकर उसकी ध्वनि बुलवाइए।
🗣️ अगली बार ऐसे कहकर देखें: "अमन, पहले अक्षर पर उँगली रखो। म पर कौन-सी मात्रा है? बोलो, म… ए… मे।"
आपकी कक्षा की दिक्कत (मात्रा छोड़ देते हैं या मात्रा वाले शब्द नहीं पढ़ पाते) इस अभ्यास में अमन की गलती से जुड़ी है। कक्षा में भी इसी तरह पहले बच्चे से उसका तरीका पूछिए, फिर ठोस चीज़ों से दिखाइए।
ये बच्चे असली कक्षा के बच्चों जैसे लगे? 1 (बिल्कुल नहीं) से 5 (बिल्कुल वैसे ही) चुनें।
```
Screenshots (393x852, `docs/ux/task5/`): `board_before_regroup_{light,dark}.png`, `board_after_regroup_{light,dark}.png`,
`coach_feedback_quote_badge_{light,dark}.png` (live feedback, **no badge**: see Task 4 finding),
`coach_quote_badge_harness_393x852-{light,dark}-coach.png` (the same sentence delivered as a coach-speaker message
through a mocked poll: the badge renders; this is a harness injection, not live output).
The demo3 feedback's thumbs-up line says no standout point was found, which is weak for a first impression; not changed.

## Gates, payload, environment

Gates at the end: `ruff check .` clean; `mypy --strict backend/app scripts/keep_alive.py` clean (170 files); `node --test chat.test.mjs` 73 pass, 0 fail; full `pytest -q` with `TEST_DATABASE_URL` on the local pgserver Postgres (so the e2e and integration tests ran): no failures, 2 skips (destructive migration test refuses database `postgres`; no sample audio on disk). My `tail` cut off the final `N passed` line, so I have no exact total. Numbers: first-load all-assets payload before 149,446 B (4,154 B
headroom to 153,600), after T1 149,833, after T2/T3/T1b 151,796 B (**1,804 B headroom**; limit for stopping was 1,000).
The working tree here is LF (`.gitattributes`), not CRLF, so LF-equivalent equals measured. Teacher first load 130,659 B.
`eval/lowband/REPORT.md` is regenerated by `check_first_load.py` and was not committed.
A local Postgres from `pgserver` in `%TEMP%\abhyas_pg_run5` is still running on 127.0.0.1:55068 (I did not stop it).

## Not done / undone

- Task 4 change: deliberately not made (needs service code).
- Quote badge in the live flow: not fixed (see above).
- Real Android device, real soft keyboard, hosted site, Render: not tested (**assumed**).
- Untracked scratch left in the working tree because deletes were forbidden: `docs/ux/_scratch_unused/` (duplicate
  screenshots), `backend/tests/js/_dbg.mjs` and `.tmp_fasttrack_tests.mjs.txt` (both one-line stubs); all three are
  excluded locally through `.git/info/exclude`, not committed.

## Follow-up: quote badge on the live path, pytest summary, handbook check

Run on the same branch. Everything here was run in this session unless marked **assumed**.

### 1a. Real SessionService path, "बस" at the end
`backend/tests/unit/test_coach_feedback_speaker.py` drives `SessionService` (in-memory scene store and fake repository,
mock LLM, scripted act tagger; the children's answers still come from the rule engine). Payloads before the fix
(`speaker`, text), subtraction (demo2 flow: ask to explain, concrete representation, "बस"):
```
#0 kind=text speaker='coach' 'चलिए, अब फीडबैक देखते हैं।'
#1 kind=text speaker=None    'आपके अभ्यास पर सुझाव:'
#2 kind=text speaker=None    'आपने ठोस चीज़ (बंडल और तीलियाँ) इस्तेमाल की, ... \n\n(यह सुझाव एक विशेषज्ञ भी देखेंगे।)\n\n👍 आपने बच्चे से उसका तरीका पूछा, ... आपके शब्द: «रवि, तुमने 43 में से 27 कैसे घटाया? मुझे एक-एक कदम बताओ।»\n🔁 ...\n🗣️ ...'
#3 kind=buttons speaker=None 'रवि असली कक्षा के बच्चे जैसा लगा? 1 ... चुनें।'
#4 kind=buttons speaker=None 'क्या आप अपने अभ्यास के अंक अपने ARP से साझा करना चाहती हैं? ...'
```
So on the real path the «quote» (`coach_quote_suffix`) is in bubble #2, which had no speaker. Literacy (group scene, LIT_MATRA_BLENDING):
same five messages, bubble #2 is `speaker=None` and has **no «quote»**: `coach.py` adds the quote only for one-on-one scenes
(`one_on_one and strength_is_evidenced`), so a group or literacy scene never has a badge, by existing design. I did not change that.

### 1b. The change and what else it does in the UI
`service.py`: the advice bubble is now `OutboundMessage(..., speaker="coach")`. Header line and the buttons stay `None`.
For that one bubble the UI now also: shows the amber "कोच" speaker tag above it (server-rendered on reload and by
`chat.js` when live); shows the "अंग्रेज़ी में देखें" translate button (coach is in `TRANSLATABLE_SPEAKERS`; the endpoint
limit is 2000 characters, this text is about 600; the translation call uses the LLM, not exercised here); draws the badge.
No audio change (coach text has no audio ref and autoplay is for children only), no change to ARP or trainer views
(nothing filters on speaker, by grep), no change on WhatsApp (the speaker is only stored). One cosmetic side effect found
by reading `offline.html`: the offline page prints the raw speaker word ("coach") above cached messages, so this bubble now
gets that label offline too, as the other coach bubbles already do (**assumed**, not rendered).

### 1c. Tests
Backend (`test_coach_feedback_speaker.py`, 2 tests): the only bubble with « » is `speaker == "coach"` and contains
`coach_quote_suffix` for the teacher's line; header and buttons have no speaker; the literacy feedback has no quote and only
the advice bubble is coach. JS (`chat.test.mjs`, 2 new tests, 75 pass): the exact live text with `speaker: 'coach'` gets the
badge, prefix consumed, other lines kept; the same text with `speaker: null` gets no badge; the existing XSS, newline and
"non-coach has no badge" tests still pass. The e2e artifact test now asserts at least one badge on the live page.

### 1d. Screenshots from the real path (not injected)
`docs/ux/task5/coach_feedback_quote_badge_{light,dark}.png` and the board images were re-rendered by
`test_e2e_run5_artifacts.py` on the seeded Postgres app at 393x852: "quote badges on the page: 1" in both themes.
The two earlier harness-injected files (`coach_quote_badge_harness_*`) are still in the folder (deletes were forbidden);
ignore them. A flaky wait in that test (board header arrives with the next poll) was fixed.

### 2. Full pytest
The earlier run had no summary line because `pyproject.toml` already has `addopts = "-ra -q"` and I added a second `-q`.
This run uses no extra flags and a local pgserver Postgres in `TEST_DATABASE_URL` (the shared `postgres` database, which the
earlier runs had already written to). Exact final line of `python -m pytest`:

    9 failed, 1725 passed, 2 skipped in 1744.86s (0:29:04)

The 9 failures: 5 integration tests (admin, review console, trainer role guard, 2 WhatsApp send tests) hit
`UniqueViolationError ... teacher_phone_hash_key`, i.e. rows left in the reused database by my earlier runs; 4 e2e tests
(`test_sample_lines_are_folded...`, `test_chip_tap_shows_question_typing_and_cited_answer[demo1-en-desktop]`,
`test_learn_step_says_what_to_tap[en]`, `test_skip_opens_the_chat_and_a_new_login_shows_the_screen_again`) timed out after 30 s
waiting for `#chat-input`. I re-ran exactly those 9 plus their files on a fresh database `abhyas_test_fresh`: `31 passed in 147.80s`,
no failures. So they pass in isolation; the integration failures are explained by the reused database, but I have **no proven
cause for the 4 e2e timeouts** (they passed earlier in the same session too, at the first e2e run and in the artifact runs; I
suspect load during the 29-minute run, **assumed**). Skips (2): the destructive migration test refuses a database named `postgres`;
no sample audio on disk. Honest reading: the suite is not clean in one single run on this machine, it is clean on a fresh database
file-by-file for the affected tests.

### 3. Layout check and payload
`composer_layout_check.py` (3 sizes x dark/light x start/consent/learn/scene): 0 failures, and 0 failures with `--keyboard 250`.
`check_first_load.py`: teacher first load 127.6 KB (130,659 B), all assets 148.24 KB = 151,796 B, headroom to 153,600 B =
1,804 B (the stop line is 1,000 B). No JS/CSS changed in this follow-up, so the bytes equal the earlier run. The working tree
is LF, so LF-equivalent equals measured.

### 4. Does any path render the English original passage inline?
No path I found does, by default. `fallback_reply` (`backend/app/handbook/fallback.py`) builds the text from the stored Hindi gloss only:
```python
summary = str(stored.get("gloss_hi") or "").strip()      # returns None when empty
...
text = get_message("handbook_fallback", address_form, summary=summary, citation=line)
```
The chunk's English `text` goes into `RetrievedChunk(text=...)`, used for the LLM prompt, the guards and the citation record, never into
message text. The other message builders use `gloss_hi` (`learn_reference`, `_learn_tip`) or guarded `*_hi` model output
(`compose_guide_reply` uses `answer.answer_hi`; `_source_suggestion` uses `suggestion_hi`). The original English passage
is returned only by `GET /api/source/{chunk_id}` (`chat_api.py`, field `text`). It opens on a tap or click on a `.source-chip` button
under a bubble: `chat.js` has `document.addEventListener('click', ...closest('.source-chip') -> toggleSourceExcerpt(chip))`, which fetches
`/api/source/<chunk_id>` and appends the panel (Hindi summary first, then the English passage with the note "This passage is in English,
from the original document."). A second tap closes it. So the long English passage you saw is, as far as I can tell, that panel having been
opened, or a data set I do not have (**assumed**: I did not look at the hosted site). The test `test_handbook_fallback_language.py` already
asserts the original is absent from the fallback in both languages.

### Verified vs assumed, undone
- Verified (run): items 1a to 1d, 3 and 4 above; Chromium emulation only.
- Assumed: translate button behaviour with a real LLM, the offline page label, anything on real Android or the hosted site.
- Not done: no change to when the coach quotes (group and literacy scenes still have no quote); `placement_done` untouched.
- Leftovers (deletes forbidden): `docs/ux/task5/coach_quote_badge_harness_*` and the earlier scratch items listed above.

## Follow-up 2: the e2e timeouts, their cause, and a reliable full run

### The four tests (from the 29-minute run)
1. `test_e2e_demo_helpers.py::test_sample_lines_are_folded_on_a_phone_open_on_a_desktop_and_plainly_labelled`
2. `test_e2e_handbook_chips.py::test_chip_tap_shows_question_typing_and_cited_answer[demo1-en-desktop]`
3. `test_e2e_next_action.py::test_learn_step_says_what_to_tap[en]`
4. `test_e2e_start_here.py::test_skip_opens_the_chat_and_a_new_login_shows_the_screen_again`

### Isolated, 5 runs each, fresh database per run (`scripts/pytest_fresh_db.py`, plus the e2e fixture's own database)
All 20 passed: test 1: 48.05, 46.04, 46.57, 45.35, 44.96 s; test 2: 41.48, 44.75, 45.55, 47.59, 45.32 s;
test 3: 39.89, 40.32, 40.66, 40.90, 41.73 s; test 4: 38.28, 36.63, 36.86, 36.09, 36.53 s (each run is mostly the
server's migrate-and-seed). So these tests do not fail alone.

### Whole e2e directory on fresh databases: flaky, and not because of this branch
Branch before the fix (4 runs): `4 failed, 35 passed`; `3 failed, 36 passed`; `6 failed, 33 passed`; `8 failed, 31 passed`.
`main` (git worktree of 4fdb62e, no checkout, its own tests): `6 failed, 30 passed in 450.32s` and `8 failed, 28 passed in 441.78s`.
Different tests fail each time (the same families: `[en]` learn step, handbook chips en-desktop, start-here, demo1 journey,
scene header en-mobile). Main flakes as much as the branch, so the layout change is not the cause.

### What the page looked like at the timeout (E2E_DIAG_DIR captures in `docs/ux/e2e_diag/run_a|run_b`)
- 3 timeouts waiting for `#chat-input`: URL `/teacher/start`, readyState complete, viewport 360x740 or 1280x800,
  `#chat-input` not in the DOM, no failed network requests, no page errors. The page is the one-time Start here screen,
  not a broken chat. No layout question arises.
- The other failures: URL `/teacher` (the chat) when the test expected the Start screen; `#chat-input` in the DOM with box
  top 680, bottom 728 in a 740 px viewport, i.e. fully on screen. The strips-shrinking layout is not involved.

### Cause (checked)
The login handler resets a shared demo account (`_reset_demo_teacher`) but the session dependency commits only after the
response has been sent (FastAPI 0.121 runs yield-dependency exit code after the response). The browser follows the 303 and
asks for `/teacher` before that commit lands, so it reads the pre-reset rows (Start screen shown when it should not be, or
not shown when it should). Measured on a live seeded server with a script (login, tap Start, log in again, immediately GET
`/teacher`; the script is not in the repo): **17 of 25 stale before the fix, 0 of 25 after**. Under load (other processes,
slow machine) the window gets wider, which is why the failures vary and were more frequent in long runs. This is an app bug
that also existed on main, and a judge who logs out and back in quickly could meet it (**assumed** for the hosted site).

### Fix
`backend/app/auth/router.py`: `_reset_demo_teacher` now calls `await db.commit()` right after the reset (login and logout),
inside the existing try/except, so the redirect target sees the reset. Regression test
`test_demo_reset_commits_before_redirect.py` (fails without the line, passes with it). No test assertion was changed.
After the fix, the whole e2e directory twice on fresh databases: `39 passed in 312.72s` and `39 passed in 313.50s`.

### Reliable full run
`python scripts/pytest_fresh_db.py --server postgresql://USER:PASS@HOST:PORT/postgres` creates `abhyas_test_<random>`, exports
it as `TEST_DATABASE_URL`, runs `python -m pytest -p no:cacheprovider <args>` and drops the database afterwards (the browser
tests also create and drop their own). Pass extra pytest args after the server (`backend/tests/e2e`). Do not add `-q`:
`pyproject.toml` already has `-ra -q`, and a second `-q` removes the summary line. The earlier 5 integration failures
(`teacher_phone_hash_key`) were a reused database; this wrapper prevents that. For E2E diagnostics set `E2E_DIAG_DIR=some/dir`
(screenshot, layout state JSON and the server log are written there on a failure).

### Gates (end of this round, fresh database)
- `ruff check .`: `All checks passed!`
- `mypy --strict backend/app scripts/keep_alive.py`: `Success: no issues found in 170 source files`
- `python scripts/pytest_fresh_db.py --server ...` (full): `1739 passed, 1 skipped in 1583.24s (0:26:23)` (skip: no sample audio on disk)
- `node --test backend/tests/js/chat.test.mjs`: `tests 75`, `pass 75`, `fail 0`
- `python scripts/composer_layout_check.py`: `0 failure(s)`; with `--keyboard 250`: `0 failure(s)`
- `python scripts/check_first_load.py`: `Teacher Chat First-Load: 127.63 KB raw / 30.49 KB gzip`, `All Offline Assets: 148.28 KB raw / 37.71 KB gzip`,
  `Status: PASS (< 150 KB)`; exact bytes: teacher bundle 130,697; all assets 151,834; headroom to 153,600 = 1,766 B (LF equals measured;
  no JS or CSS changed this round, the 38 B difference from before is the rendered page).

### Left over / not done
- The git worktree of main stays at `%TEMP%\abhyas_main_wt` (removal is a delete, not done); the local Postgres from `pgserver` is still running on 127.0.0.1:55068.
- `docs/ux/e2e_diag/*/server.log` (6 MB each) is not committed. Real devices and the hosted site were not tested.
