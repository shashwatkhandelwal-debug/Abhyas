# Bug hunt report (fix/fix3)

Phase 1 (FIND) ran on the real app in Docker with the real model. No app code was changed in phase 1.
Status columns are filled in at the end of phase 3.

## What ran

| Journey | Ran | Notes |
|---|---|---|
| A onboarding (8 variants: male/female x Hindi/English UI, name answers, consent, ARP code, 8 reply types) | yes, phone | Two earlier batches were discarded: shared demo state leaked between runs and two batches overlapped. The final batch was clean and sequential. |
| B rehearsals | partly, phone | Regrouping with Ravi (10 turns), Priya, Aman, Ravi as a male-teacher account; NUM_COMPARE (Ravi); LIT_LETTER_SOUND group scene; LIT_MATRA group scene (5 turns). Shorter than the 10 turns asked: the live-call cap (400) did not allow 10 turns for every child on every scene. Priya and Aman were only run on regrouping. |
| C Guide | yes, phone | 5 Hindi (4 answered, 1 honest "not in the documents"), 1 English chip path not reachable after `/lang/en` redirect (see B21), 1 off-topic, 1 injection (declined). |
| D demo logins and reset | yes, phone | demo1/2/3, three follow-up buttons on demo2, daily tip on/off on demo3, reset x3 per account. |
| E teacher features | yes, phone | class check-in walked through every topic, level and struggle option (no errors), my class, delete my data (found P0), my progress, language switch from the menu. Observation/visit note to the teacher: ARP form not exercised (no teacher-side message produced in the run). |
| F ARP, trainer, coach, admin pages, CSVs | yes, phone and desktop | No overflow, no console error, no 5xx. CSV headers and PII checked. |
| G robustness | yes, phone | anonymous hits, offline then online, slow 3G, double tap, two tabs, back button. The 10-minute idle step was not run. |
| H static sweep | yes | Both catalogs scanned for em dashes, scripts, raw codes, gender forms. |

Desktop (1366x768): only journey F was run on desktop in phase 1. Voice was not tested (verified by hand).
Live LLM calls used in phase 1: about 265 of 400 (counted as `llm_role` log lines).

## Bugs

Severity: P0 breaks a flow or leaks/destroys data, P1 a judge would notice in 15 minutes, P2 polish.

| ID | Sev | Where | What the user sees | Expected | Root cause (file:line) | Fix plan |
|---|---|---|---|---|---|---|
| B02 | P0 | E, "delete my data" on teacher.demo1 | After "हाँ, मिटाएँ" the teacher and the login row are gone; the next login says "गलत यूज़रनेम या पासवर्ड" for every judge until a reseed | A shared demo account is reset, never deleted | `backend/app/web/teacher.py:890` calls `purge_teacher_data` for demo accounts | For shared demo teachers call the reset path (`reset_demo_teacher`) instead of purging; same confirmation page |
| B03 | P1 | G, anonymous GET /teacher, /arp, /trainer, /review, /admin | Raw JSON `{"detail":"Not authenticated"}` with HTTP 401 | A page request without a session goes to the login page | `backend/app/auth/guards.py:63` raises 401 for every route | For HTML navigation (Accept: text/html) answer with a redirect to `/login`; keep 401 JSON for API calls |
| B01 | P1 | A, address-form step | Typing "हाँ" (or anything but a button) picks the feminine form: "सुनील जी, आप कितने साल से पढ़ा रही हैं?", Ravi then says "दीदी" to a male teacher | Only the two buttons (or a clear male/female word) set the form; anything else re-asks | `backend/app/sessions/state_machine.py:1108-1112`, `else` branch defaults to "f" | Accept explicit tokens only, otherwise stay in the state and re-ask with the buttons |
| K1 | P1 | A and B, Ravi, Priya and Ravi (compare) | Ravi: "…तो 45!" then after the teacher tells the steps "…उत्तर 45!" (same line); in regrouping three identical lines; in compare an exact repeat; "आज बाहर बारिश हो रही है न?" gets the math line again | No near-repeat; if the teacher explained, the child reacts to it; off-topic gets a reaction | `backend/app/llm/roles/child_voice.py:~290` repeat check is exact equality only; no telling state | Normalised near-repeat check (>= 0.8), one retry then template; telling/explaining state with template lines; off-topic reaction |
| K2 | P1 | A, feedback after the 2 onboarding turns | Telling the procedure in turn 2 is not mentioned | A deterministic extra line | `backend/app/sessions/placement_feedback.py` only maps tagger acts; telling is untagged | Deterministic detector on later turns, extra catalog line (hi and en) |
| K3 | P1 | A, after feedback | The move name appears three times in a row ("So we will start with…", "Your first move is…", "This week's move…") | Name once, then the key points | `backend/app/sessions/service.py:2111-2133` sends feedback, `ready_first_move`, then `learn_intro` | Drop `ready_first_move` line when the feedback already names the move |
| K4 | P1 | A, Guide tip after onboarding; B, learn step official excerpt | "बच्चों के साथ घर पर गिनती की गतिविधियाँ करवाने के लिए अभिभावकों को…" for a bundles move; feminine verb for a male teacher; learn step on regrouping shows an excerpt about multiplication and division | On-topic tip, no home/parent passages, no feminine verb for male, none if nothing qualifies | `backend/app/sessions/service.py:576-655` (`_cited_tip`) takes whatever retrieval returns | Filter candidate chunks by move keywords, exclude home/parent passages, skip feminine reader verbs for male, no tip otherwise |
| K5 | P1 | D, all demo logins | Banner "डेमो: लॉगिन/लॉगआउट पर चैट रीसेट" says nothing about what the demo shows | One banner per demo account | `backend/app/web/teacher.py:95-99` one shared message | Per-account banner keys, hi and en |
| K6 | P1 | D, demo2 | Follow-up card ("कल आपने कक्षा के बाद बताया… काम किया / अब भी अटके हैं / आज़मा नहीं सके") appears between Ravi's seeded line and the rehearsal | Before the rehearsal block or after it ends | `backend/app/sessions/service.py:998-1020` offers on open; the seeded scene is not counted as `spoken` | Seed the card before the rehearsal messages (marked offered) |
| K7 | P1 | D, demo2/3 | Seeded bubbles "17:56", live ones "11:28 pm" (and the seeded time is UTC, 5.5 h behind) | One format everywhere | `backend/app/web/teacher.py:189-193` formats UTC 24-hour on the server; `chat.js:1182` formats live in the browser | Format every bubble in the browser from `data-created-at` |
| B07 | P1 | D, demo2 | Typing "मेरी प्रगति" inside the active scene is sent to Ravi as a teacher turn (the K5 banner asks the judge to open it) | The command opens my progress | scene turn capture runs before the my-progress intent | Recognise the exact command during a scene |
| B08 | P1 | D, demo3 "मेरी प्रगति" | "हासिल वाला घटाव: बंडल खोलकर (21/10)" reads as a score of 21 out of 10 | A date that reads as a date | `backend/app/class_profile/my_progress.py` formats dd/mm | Show "21 अक्टूबर" |
| B09 | P1 | E, delete page, male teacher | "क्या आप वाकई अपना सारा डेटा हटाना चाहती हैं?" | Masculine form ("चाहते हैं") | `delete.html` calls `get_message` without the teacher's address form (the catalog has `text_m`) | Pass the address form |
| B04 | P2 | A, name | Latin name in a Hindi sentence ("Riya जी"); "DEMO" accepted as a name | cosmetic | name step | left |
| B10 | P2 | Hindi UI | English glosses: "प्रगति (Progress)", "प्रमाण सीढ़ी (EVIDENCE LADDER)", "(RUBRIC SCORES)", "(KEY POINTS COVERED)"; ARP week "26 Oct 2026"; trainer "ज़िला: Kanpur Nagar" | Hindi only | catalog `ui_chat_menu_progress`, `ui_progress_*`; ARP date format; district name | remove glosses if time allows |
| B11 | P2 | trainer CSV | `export.csv` has English headers while the other CSVs have Hindi | one language | `backend/app/web/trainer.py` export | left |
| B12 | P2 | A, consent | Typed "Learn more" / "I agree" in the Hindi flow re-asks | accept | intents | left |
| B13 | P2 | LEARN step | A typed question without the "सवाल:" prefix gets "press the button" | by design (free text is the step's input; Guide is chips or the prefix) | n/a | left, documented |
| B14 | P2 | girl child grammar | "प्रिया ... सही करता है", "प्रिया असली कक्षा के बच्चे जैसा लगा?" | feminine for Priya | persona-neutral catalog strings | left |
| B15 | P2 | G, two tabs | A second tab did not show the first tab's new messages within 8 s | live update | polling | left |
| B16 | P2 | demo3 | Progress history is four regrouping attempts although three modules are "completed" | consistent story | demo seed | left |
| B17 | P2 | phone, 3-children scene | The suggestions sheet clips the "डेमो शॉर्टकट" block at the bottom | no clipping | sheet height | left |
| B18 | P2 | explain-back | "आपने 4 में से 0 मुख्य बातें कहीं" for a sensible literacy explanation | fairer scoring | fidelity checker output (model) | left |
| B19 | P2 | `/lang/hi` with no `next` while logged in | Goes to /login | stays on page | `ui_lang.py` default redirect | left |

## Status after phase 2 and 3

| ID | Status | Commit | Confirmed |
|---|---|---|---|
| B02 | FIXED | 70f2b6f | live (demo1 login works after "delete my data") + test (fails before) |
| B09 | FIXED | 70f2b6f | test |
| B03 | FIXED | 48e2e67 | test |
| B01 | FIXED | f80a4a2 | live (typed "हाँ" re-asked) + test |
| K1 | FIXED (passes the final live check, with caveats below) | 0aa8742, 1d41f38 | live: 0 near-repeats in 28 scene lines, highest similarity 0.79; the child reacts when the teacher tells the steps. Root cause: the Postgres scene store never saved the children's lines (previous line always empty); fixed, Postgres test fails before and passes after |
| K2, K3 | FIXED | 256dae9 | live + test |
| K4 | FIXED | 8cb5591 | live: no tip shown on place value (nothing qualified), on-topic tip and excerpt on subtraction; test |
| K5 | FIXED | 2428392 | live + test. Deviation: Hindi demo3 banner says 'समझ गई, आगे' (not "Got it, next") to avoid English in Hindi mode |
| K7 | FIXED | 0a2ca7b | live ("12:57 am" like live bubbles) + python and node tests |
| K6 | FIXED | 45a355b | live + integration tests. Demo seed changed: demo2 now has 6 messages (card first), counts updated in tests |
| B07, B08 | FIXED | 56830ab | live + tests |
| B04, B10 to B19 | P2-LEFT | | B10 is an intentional bilingual heading (a test asserts it); the rest are polish outside the shared flows |

## Gate (final)

Code did not change after the full run below (only `scripts/bughunt/k1_check.py`).

| Step | Result |
|---|---|
| Full `scripts/pytest_fresh_db.py` from a directory with no `.env` (log `%TEMP%\gate_final.log`) | 2735 passed, 7 failed, 2 skipped (854 s) |
| The same 4 files re-run from the repo folder | 47 passed. The 7 failures are directory artifacts: `alembic.ini` and `content/moves/*.yaml` are relative paths (`No 'script_location' key found`, `FileNotFoundError content/moves/...`). Names: `test_migrations.py::test_alembic_migrations_round_trip`, `::test_single_head_and_last_migration_steps_back_and_forward`, `test_db_models.py::test_alembic_migration_revisions_chain`, `test_one_on_one.py` (3 validator tests), `test_review_console.py::test_move_review_and_two_coach_approval` |
| Earlier full run from the repo folder (with the local `.env`) | 10 failed, 3 errors: 6 mine (payload line endings, Hindi literals in `tip_filter.py`, prewarm stub signature, coach suggestion test, K3 wording in the happy-path test, demo banner height in an e2e test), all fixed; 4 caused only by the local `.env` (3 support-framing tests and the production-config test): they pass without it |
| Phone layout check | 0 failing of 144 state/size/variant cells |
| Composer layout check | 0 failures |
| Dashboard layout check | 0 failures (12 of 12 PASS; needs `--server`) |
| `check_first_load.py` | PASS: first load 131,207 B, all assets 152,328 B, headroom to 153,600 = 1,272 B (>= 1,000); `eval/lowband/REPORT.md` restored |
| Freeze-check + no-dash tests | 80 passed, 1 skipped (the skip is an existing one: page bytes frozen) |
| `ruff check .` | clean |
| `mypy --strict backend/app` | no issues in 201 files |
| `ruff format --check .` | 8 files unformatted, all also unformatted on origin/main with the local ruff 0.16.5, none touched by this work |

No single run is fully green: from a directory without `.env` seven tests need the repo as working directory; from the repo folder four tests need an empty `.env`. Together every test passes.

Payload: my edits had made the working copies of `chat.js` and `teacher.html` CRLF, which pushed the assets 742 B over the ceiling; restored to LF, headroom 1,272 B. `git diff --numstat main...HEAD` shows no whole-file rewrite (largest change `service.py` +91/-38).

Banners: kept. On a 360 px phone they are 40 px (demo1) and 60 px (demo2, demo3), never clipped, with a 32x32 close button (`#demo-dismiss`), the input on screen and a message list of at least 428 px, in both languages; the phone layout check shows 0 failures.

Live model calls: K1 final check used 61 real calls (log lines at or above 150 ms) of the extra 120. Earlier phases counted 283 + 107 `llm_role` lines (the literal rule), about 14 per container start being the demo2 seed on the mock fallback.

Demo seed: changed. demo2 now has 6 messages with the follow-up card first (card + the 5 rehearsal messages); the seed and reset tests are updated.

RAM: the 5 GB gate was never reached (4.4 to 4.7 GB for 15 minutes), so only the K1 run was started first, as planned; no job was killed for memory in this last pass.


## K1 live verification (final code, real model)

Run: hunt stack rebuilt with the final code (`bab3d68`), phone viewport 360x740, 61 real model calls
(log lines at or above 150 ms; the 14 boot-time lines per start are the demo2 seed on the mock fallback,
11 to 31 ms). RAM never reached the 5 GB gate (4.4 to 4.7 GB for 15 minutes), so only this run was started,
as planned. Scoring: `scripts/bughunt/k1_check.py` uses the repo's own `is_near_repeat` plus the token
similarity (difflib ratio over core words, address word and fillers removed) against each child's
previous line. Threshold 0.8.

How to read the transcripts below: the driver re-prints the whole chat when a module opens, so in the
male Ravi run the first four entries ([01] to [04]) are the onboarding practice lines replayed, not scene
turns; the scene turns are [05] to [11]. In that run the engine ended the scene after the second repeat
of the same teacher line (the turn counter stayed at 6 of 10 and the screen moved to the feedback step),
so the last three planned turns (hands-on count, new problem, ask again) got no child line: 7 scene lines
for Ravi, not 10. Compare, Priya and Aman completed all 6 turns.

Result: **no near-repeat flagged (0 of 28 scene lines); highest similarity to a previous line 0.79
(Priya, [03])**, then 0.76, 0.72 (Ravi male [09]). When the teacher told the steps the child reacted to
them every time (Ravi male [06], [07], [10], [11]; compare [02]; Priya [02]; Aman [02]).

Caveats, stated plainly:
- Priya [03] at 0.79 and [04] at 0.76 are just under the threshold: she restates "13 से 7, 6 आया, 3 से 2,
  1 आया, 16" in four of her six lines (she has reached the correct method after the concrete move).
- The phrase "मुझे समझ नहीं आया, मैं तो अपने तरीके से ही करता हूँ" appears in about half of the lines of all
  four children. It is the example sentence in the old `_no_repeat_rule` prompt text, copied by the model.
  It never repeats back to back (similarity under 0.8) but it is formulaic. Left as P2: changing the prompt
  now would need another live check and gate.
- The compare scene answers a concrete-objects move with that same "I do it my way" phrase plus the old
  method (turns 3, 4, 6), which a teacher may find odd.

Before (phase 1, same bugs, before any fix), quoted from the phase 1 transcripts:
- Onboarding, male teacher: Ravi "सर, तो 7 में से 2 घटाया, 5 आया। 5 में से 1 घटाया, 4 आया। तो 45!" then, after
  the teacher dictated the steps, "सर, तो 7 में से 2 घटाया, 5 आया। 5 में से 1 घटाया, 4 आया। उत्तर 45!"
  (one word changed, the explanation ignored).
- Regrouping, female teacher: three identical lines in a row, "13 में से 7 घटाया, 6 आया। 3 में से 2 घटाया,
  1 आया। जवाब 16!", the second after the teacher dictated the steps; "आज बाहर बारिश हो रही है न?" got the
  same maths line back.
- Compare: "3 बंडल और 4 बंडल, 4 बंडल ज़्यादा, तो 41 बड़ा!" twice in a row, word for word.
- Intermediate run (before the scene-store fix): the same regrouping line three times in turns 2 to 4,
  because the Postgres scene store never saved the children's lines, so "previous line" was always empty.

After (full scored output, Hindi):

```
=== K1_ravi_male_phone.out
[01] teacher: 'रवि, 45 कैसे आया?'
     रवि: / सर, तो 7 में से 2 घटाया, 5 आया। 5 में से 1 घटाया, 4 आया। तो उत्तर 45 है। /   (sim to previous 0.00)
[02] teacher: 'रवि, बंडल और तीलियों से 52 बनाकर दिखाओ।'
     रवि: / सर, मुझे समझ नहीं आया, मैं तो अपने तरीके से ही करता हूँ। 12 में से 7 घटाया, 5 आया। 4 में से 1 घटाया, 3 आया। उत्तर 35 है। /   (sim to previous 0.52)
[03] teacher: 'रवि, बंडल और तीलियों से 52 बनाकर दिखाओ।'
     रवि: / सर, तो 7 में से 2 घटाया, 5 आया। 5 में से 1 घटाया, 4 आया। तो उत्तर 45 है। /   (sim to previous 0.52)
[04] teacher: 'रवि, बंडल और तीलियों से 52 बनाकर दिखाओ।'
     रवि: / सर, मुझे समझ नहीं आया, मैं तो अपने तरीके से ही करता हूँ। 12 में से 7 घटाया, 5 आया। 4 में से 1 घटाया, 3 आया। उत्तर 35 है। /   (sim to previous 0.52)
[05] teacher: 'रवि, तुमने यह कैसे किया? बताओ।'
     रवि: / सर, तो 7 में से 3 घटाया, 4 आया। 4 में से 2 घटाया, 2 आया। तो जवाब 24। /   (sim to previous 0.44)
[06] teacher: 'ऊपर 43 नीचे 27 लिखो, 13 में से 7 घटाओ, 3 में से 2 घटाओ, अब बताओ जवाब क्या है'
     रवि: / सर, मुझे समझ नहीं आया, मैं तो अपने तरीके से ही करता हूँ। /   (sim to previous 0.08)
[07] teacher: 'ऊपर 43 नीचे 27 लिखो, 13 में से 7 घटाओ, 3 में से 2 घटाओ, अब बताओ जवाब क्या है'
     रवि: / सर, ये तो उल्टा लग रहा है, मैं तो पहले वाला तरीका ही करूँगा। /   (sim to previous 0.11)
[08] teacher: 'रवि, बंडल और तीलियाँ लेकर 43 बनाओ, फिर 27 हटाओ।'
     रवि: / सर, 13 में से 7 घटाया, 6 आया। 3 में से 2 घटाया, 1 आया। तो जवाब 16। /   (sim to previous 0.00)
[09] teacher: 'रवि, अब बताओ, तुमने बंडल से कैसे किया?'
     रवि: / सर, बंडल वाला मुझे नहीं पता। मैं तो 13 में से 7 घटाया, 6 आया, 3 में से 2 घटाया, 1 आया, तो 16। /   (sim to previous 0.72)
[10] teacher: 'पहले 3 में से 7 नहीं हटता, इसलिए एक बंडल खोलो, 13 में से 7 घटाओ, फिर 3 में से 2 घटाओ, जवा
     रवि: / सर, बंडल मुझे समझ नहीं आया, मैं तो अपने तरीके से ही करता हूँ, 13 में से 7 गया, 6 बचा, 3 में से 2 गया, 1 बचा, 16 हुआ। /   (sim to previous 0.58)
[11] teacher: 'पहले 3 में से 7 नहीं हटता, इसलिए एक बंडल खोलो, 13 में से 7 घटाओ, फिर 3 में से 2 घटाओ, जवा
     रवि: / सर, बंडल वाला मैं नहीं करूँगा, मेरा तरीका सही है, जवाब 16 है। /   (sim to previous 0.16)
=== K1_compare_phone.out
[01] teacher: 'तुमने कैसे तय किया कि कौन-सी संख्या बड़ी है?'
     रवि: / दीदी, 9 और 1 में 9 बड़ा है। तो 39 बड़ा है! /   (sim to previous 0.00)
[02] teacher: 'पहले 3 और 4 दहाई के अंक देखो, 39 में 3 दहाई, 41 में 4 दहाई, इसलिए 41 बड़ा है।'
     रवि: / दीदी, हम्म… थोड़ा-सा समझ आया, पर आगे क्या करना है, पता नहीं। /   (sim to previous 0.00)
[03] teacher: 'बंडल और तीलियों से दोनों संख्याएँ बनाकर देखो।'
     रवि: / दीदी, मुझे समझ नहीं आया, मैं तो अपने तरीके से ही करता हूँ। 3 बंडल और 4 बंडल, 4 बंडल ज़्यादा, तो 41 बड़ा! /   (sim to previous 0.13)
[04] teacher: 'बंडल और तीलियों से दोनों संख्याएँ बनाकर देखो।'
     रवि: / दीदी, बंडल और तीलियों से मैं नहीं करता, मेरा तरीका सही है। 3 बंडल और 4 बंडल, 4 बंडल ज़्यादा, तो 41 बड़ा! /   (sim to previous 0.59)
[05] teacher: 'अब 38 और 41 में कौन बड़ा है?'
     रवि: / दीदी, 8 और 1 में 8 बड़ा है, तो 38 बड़ा! /   (sim to previous 0.14)
[06] teacher: 'रवि, तुमने यह कैसे सोचा?'
     रवि: / दीदी, मुझे समझ नहीं आया, मैं तो अपने तरीके से ही करता हूँ। 3 बंडल और 4 बंडल, 4 बंडल ज़्यादा, तो 41 बड़ा! /   (sim to previous 0.14)
=== K1_priya_phone.out
[01] teacher: 'प्रिया, तुमने कैसे सोचा? बताओ।'
     प्रिया: / दीदी… दीदी, 3 के आगे 1 लगाया, 13 में से 7 घटाया, 6 आया। 4 में से 2 घटाया, 2 आया, 26। /   (sim to previous 0.00)
[02] teacher: 'प्रिया, पहले 3 में से 7 नहीं हटता, बंडल खोलो, 13 में से 7 घटाओ, 3 में से 2 घटाओ।'
     प्रिया: / दीदी… मुझे समझ नहीं आया, मैं तो अपने तरीके से ही करती हूँ… 13 में से 7 घटाया, 6 आया। 3 में से 2 घटाया, 1 आया… 16। /   (sim to previous 0.53)
[03] teacher: 'प्रिया, बंडल और तीलियाँ लेकर बनाओ।'
     प्रिया: / दीदी… नहीं, दीदी… मैं तो ऐसे ही… 13 में से 7 घटाया, 6 आया। 3 में से 2 घटाया, 1 आया… 16। /   (sim to previous 0.79)
[04] teacher: 'प्रिया, बंडल और तीलियाँ लेकर बनाओ।'
     प्रिया: / हम्म… 13 में से 7 घटाया, 6 आया। 3 में से 2 घटाया, 1 आया। 16! /   (sim to previous 0.76)
[05] teacher: 'प्रिया, तुम्हारा तरीका क्या था?'
     प्रिया: / दीदी… मुझे समझ नहीं आया, मैं तो अपने तरीके से ही करती हूँ… 13 में से 7 घटाया, 6 आया… 3 में से 2, 1 आया… 16। /   (sim to previous 0.55)
[06] teacher: 'अब एक नया सवाल: 52 − 38।'
     प्रिया: / दीदी… मुझे समझ नहीं आया, मैं तो अपने तरीके से ही करती हूँ… 2 के आगे 1, 12 में से 8, 4 आया… 5 में से 3, 2 आया… 24। /   (sim to previous 0.67)
=== K1_aman_phone.out
[01] teacher: 'अमन, तुमने कैसे किया?'
     अमन: / दीदी, 3 में से 7 नहीं घटता... नहीं घटा तो 0 लिख दिया। 4 में से 2 घटाया, 2 आया... तो 20। /   (sim to previous 0.00)
[02] teacher: 'अमन, पहले 3 में से 7 नहीं हटता, बंडल खोलो, 13 में से 7 घटाओ, 3 में से 2 घटाओ।'
     अमन: / दीदी, बंडल मुझे समझ नहीं आया... मैं अपने तरीके से करता हूँ... 13 में से 7 घटाया, 6 आया। 3 में से 2 घटाया, 1 आया... तो 16। /   (sim to previous 0.36)
[03] teacher: 'अमन, बंडल और तीलियों से 43 बनाओ और 27 हटाओ।'
     अमन: / 3 में से 2 घटाया, 1 आया... तो 16। /   (sim to previous 0.47)
[04] teacher: 'अमन, बंडल और तीलियों से 43 बनाओ और 27 हटाओ।'
     अमन: / दीदी, बंडल... मुझे समझ नहीं आया... मैं तो अपने तरीके से करता हूँ... 13 में से 7 घटाया, 6 आया। 3 में से 2 घटाया, 1 आया... तो 16। /   (sim to previous 0.47)
[05] teacher: 'अमन, अपना तरीका बताओ।'
     अमन: / हम्म… 13 में से 7 घटाया, 6 आया। 3 में से 2 घटाया, 1 आया। 16! /   (sim to previous 0.62)
[06] teacher: 'अब एक नया सवाल: 61 − 24।'
     अमन: / दीदी, 1 में से 4 नहीं घटता... नहीं घटा तो 0 लिख दिया... 6 में से 2 घटाया, 4 आया... तो 40। /   (sim to previous 0.40)

NEAR-REPEATS: 0
```
