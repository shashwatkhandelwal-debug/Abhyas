# fix4 report

Branch `fix/fix4`, from `main` (a8c78d1). Fixes only. Not merged, not deployed.

Source: a live walkthrough of the deployed app as demo1, demo2, demo3, ARP and trainer.
Status words: **fixed** (changed, with a test or a run that shows it), **fixed, not reproduced** (changed on
the most likely cause; the symptom did not show up locally), **not fixed**.

## Summary

| Item | Status |
|---|---|
| P0 IndexedDB empty-store failure | fixed |
| P0 "server is waking up" only at the very start | fixed |
| P0 SW "Offline: Abhyas" while online | fixed |
| P0 keepalive workflow | fixed (runs only once the workflow is on the default branch) |
| P0 Log out on the trainer page | fixed |
| P0 coach.demo needs two submits | fixed, not reproduced |
| P1 key-point matcher | fixed |
| P1 child formula phrase | fixed |
| P2 "they" -> "he" | fixed (for Ravi, Priya and Aman) |
| P2 coach class-link line | fixed |
| P2 "Demo starts here" divider | fixed |
| P2 demo3 pending "daily tip" question | fixed |
| P2 demo banner at step 6 | fixed |
| P2 rating chips 1-5 | fixed |
| P2 free-text question to the Guide | fixed (outside a running scene; inside a scene it was already routed) |
| P2 Guide blank gap and English label | fixed |
| P2 n<10 message language, bare "—", counts vs cluster pack | fixed |

## Evidence per item

### P0 IndexedDB empty-store failure (chat.js)
- **Cause found:** `offline.html` opened `abhyas_chat_db` at version 1. In a browser with no database yet, that creates an empty v1 database (no stores); `chat.js` then opened v1 with no upgrade, so every outbox and cache call threw. The logout `deleteDatabase` also raced with the next open.
- `DB_VERSION` is 2; `onupgradeneeded` creates `outbox` and `messages_cache` only if missing; after every open both stores are checked, and if one is missing the database is closed, deleted and reopened once. The open has a 2 s timeout and a 30 s pause, so a stuck browser database cannot hang a send.
- Outbox and cache failures are non-fatal: a failing outbox keeps the item in memory and sends over the network; a failed send shows the red "!" (tap to retry), never an endless clock.
- Logout closes the connection and clears both stores in place (no `deleteDatabase` unless the stores are broken). `progress.html`'s own logout handler (it also deleted the database) and `offline.html` were changed the same way; `offline.html` now opens v2 and aborts the upgrade, so it can never create an empty database.
- Tests: `backend/tests/js/idb.test.mjs` (11 tests, fake IndexedDB with versions, failing stores, blocked delete, a held-open second tab, a database that never answers): v1 with no stores is healed; a throwing outbox still sends; logout then reopen works; a blocked delete does not break the next open. Node: 110 pass.
- Browser: `backend/tests/e2e/test_e2e_fix4.py` on the local Docker app: demo1 -> demo2 -> demo3 login/logout 3 times, a second tab, and "delete my data" on demo2. Each send must leave the clock; the stores are checked after every login. 12 of 12 pass.

### P0 "server is waking up"
- Places found by grep: `/login` and every page with `_ack.html` (the "Opening..." bar turned into the waking text after 4 s, `ack.js`), `chat.js` (status bar after 5 s, `ui_chat_cold_start`), `sw.js` (the `/waking` page on 502/503/504), `errors.py` (the 503 page said "waking up"), and the `/waking` page.
- Now: the waking page is shown only by the service worker on the very first load of `/login` (or `/`) with no referrer, and only if the server has not answered in 3 s; it polls `/healthz` and opens the app by itself. Nowhere else. `ack.js` only shows "Opening..."; the chat status bar only shows "reconnecting" after being offline; the app's own 503 page now says "busy, reopen in a minute". Elsewhere the SW retries quietly (1, 2, 4, 8, 15 s, about 30 s), then shows a plain "server not reachable" page. Catalog keys `ui_chat_cold_start` and `ui_nav_waking` were removed.
- Tests: `sw.test.mjs` (18) and `chat.test.mjs` (a server silent for 60 s and a 502 show nothing in the chat).
- **"Offline: Abhyas" while online:** the SW served `/offline.html` on any failed navigation fetch (a stale keep-alive connection after idle is enough, for example on a Skip form POST). It now serves it only when `navigator.onLine` is false. A POST is replayed only when it got no answer at all; a 503 answer to a POST is not replayed. I could not make the original one-off happen locally; this is the cause the code allows.
- `.github/workflows/keepalive.yml`: GET `https://abhyas-vjh5.onrender.com/healthz` every 5 minutes (also manual). GitHub runs scheduled workflows from the default branch only, so it starts after the merge. `/healthz` returns a static dict (status, git sha): no LLM, no DB, nothing heavy.
- `docs/EVALUATOR_GUIDE.md` and `docs/JUDGE_QUICKSTART.md` describe the new behaviour.

### P0 Login and logout buttons
- Trainer page: Log out added (same markup and style as ARP). Test `test_one_submit_logs_in_and_lands_on_the_role_page_with_a_logout_button` checks a visible `a[href="/logout"]` on the teacher, ARP, trainer and coach pages (coach, admin and sub-pages already had one).
- **coach.demo needing two submits: not reproduced.** Playwright with one submit for teacher.demo1/2/3, arp.demo, trainer.demo and coach.demo, and for coach.demo after each of teacher, ARP and trainer with the service worker active: all land on the right page after the first submit, on a fresh local server and on the Docker app. I found no redirect loop, late cookie or double-submit guard in `login()` or `/review`. The most likely cause is the same transient failure as the "Offline" page (the login POST failing once and the old service worker answering with the offline page); the retry change covers it. **Not confirmed against the hosted app.** Tests added for every demo role with a single submit.

### P1 Key-point matcher
- `backend/app/llm/keypoints.py` (new): a keyword counts when an answer word starts with it (inflections: डाँट -> डाँटें, अंदाज़ा -> अंदाज़े); very short keywords need a whole word ("मे" no longer fires on "में"); each keyword is weighted by how few key points of the move list it. Covered at 0.40, partial at 0.15 (both in config).
- The demo3 answer now scores 1 of 4 (the "do not scold" point is covered, two points partial). Tests: `test_keypoints.py`, 3 matching and 2 non-matching answers for each of the 4 key points of LIT_MATRA_BLENDING.
- Known limit: "डाँटें" without "नहीं" also matches (no negation handling). Only the matra move has per-point tests.

### P1 Child formula phrase
- The example sentence is gone from the no-repeat rule and the prompt; the prompt now says to answer the teacher's concrete question. `CHILD_BANNED_PHRASES` (config) is checked in `guard_child_line` (4 variants tested).
- K1 re-run on the rebuilt Docker app (mock LLM, template path), journeys `K1_ravi_male`, `K1_compare`, `K1_priya`, `K1_aman`, phone view: **0 near-repeats, 0 lines with the phrase.** A first run found 2 near-repeats: the engine's fixed "too big" line said twice in a row. It now has a second wording and alternates (`test_child_formula_phrase.py`). The live-model path was not run (no keys); only the guard and prompt tests cover it.

### P2
- **"they" -> "he":** `fu_back_one` uses a per-child pronoun (Ravi he, Priya she, Aman he; config). Other English lines still say "they" for children (`hint_scene_one`, `rehearse_one_start` and others); not changed.
- **Coach class link:** says "same as X's mistake" only if X made it in this scene (explain_bug or relapse), otherwise a general line; no "real objects" for literacy moves (4 texts, 2 languages). **"One language per feedback block": not fixed.** In an English UI the coach text from the model is Hindi and the templates are English; I could not tell what mixing you saw and did not translate model output.
- **Demo divider:** removed (template, catalog keys, CSS; e2e test updated).
- **demo3 pending tip question:** it was not seeded; it was generated when the chat opened. Demo accounts on the learn step no longer get it (`offer_focus`); it appears later as before.
- **Demo banner:** the instruction applies up to a step (demo1 4, demo2 6, demo3 1, config); past it the banner shows the plain demo line, on load and live as the step changes.
- **Rating chips:** the question now carries 1 to 5 chips; a second message "or choose what next" carries Retry/Continue; a tap saves and says thanks (a typed digit still works). Test in `test_one_on_one_flow.py`.
- **Free-text question:** first-person how-to questions (English and Hindi, "what should I do...") go to the Guide at any step except inside answer flows (check-in, level, rating, class, skills, closing check, diagnosis, scene, delete confirm), where free text is an answer. `test_ask_anywhere.py`.
- **Guide answers:** at most one blank line in every outbound text; a generated (Hindi) answer gets the Hindi source label. The stored-summary fallback keeps its UI-language lead-in and label (an existing test pins that design).
- **n<10:** `suppression_message()` follows the UI language, in page context and in table cells; CSV export recognises both. Trainer "Common class struggles" and "What teachers want to get better at" show "Hidden: fewer than 10 teachers" instead of "—". The seed gave the cohort teachers check-ins but no class struggles or skills, so those cards were empty while the cluster pack counted them; the seed now sets both for the same teachers. Counts are of teachers with a struggle recorded, so they can be a little below the pack's 15 and 11 (those also include "went well" check-ins).

## Gates (clean detached worktree of the last commit, no `.env`)

| Check | Result |
|---|---|
| `pytest_fresh_db.py` (all of `backend/tests`, fresh Postgres) | exit 0 |
| Node tests | 110 pass, 0 fail |
| `phone_layout_check.py` | 0 failing of 144 state/size/variant cells |
| `composer_layout_check.py` | 0 failures |
| `dashboard_layout_check.py` (ARP, trainer, coach) | 0 FAIL |
| `check_first_load.py` | first load 130,636 B; all assets 151,655 B; **headroom 1,945 B** (main: 1,272 B); `eval/lowband/REPORT.md` restored, not committed |
| `freeze_check.py --skip-gates --any-branch` | passed (clean tree, no secrets, placeholders listed); gates are the rows above |
| no-dash tests | part of the pytest run |
| `ruff check .`, `mypy --strict backend/app` | clean |

`ruff format --check .` fails on 15 files that were already unformatted on `main`; the files I added or changed are formatted.
A first gate run failed 8 tests, all caused by my changes (ask-anywhere inside answer flows, a new placeholder, Hindi text in `sw.js`, a missing masculine variant, the banner and focus-offer tests). They are fixed and the gate was re-run as above.

## To do after the merge
- Re-seed the hosted app so the cohort teachers get class struggles and skills (the seed runs on boot with `SEED_ON_BOOT`).
- The keepalive workflow only runs once it is on the default branch.
- Check on the hosted app: coach.demo with a single submit, and the first Skip click after idle (neither reproduced here).

