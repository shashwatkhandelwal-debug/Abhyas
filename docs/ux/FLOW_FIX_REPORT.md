# Flow fix report (branch fix/flow-help-name-dash)

Built from main at 81a2f41. One commit per task, except F6 and F7 which share one (their template and catalog edits overlap). Per-task detail is in `docs/ux/FLOW_FIX_LOG.md`. Nothing was merged or deployed.

## Status per task

| Task | Status | Notes |
|---|---|---|
| F1 Follow-up flow | DONE | Lead-in from the stored check-in; shown first on landing; never after she has sent a line to the scene in the last 6 hours; never twice in a day; every answer ends with a next step and a button. |
| F2 Questions to the app | DONE | `core/help_question.py` (deterministic), `SessionService._help_reply`; scene state untouched. |
| F3 Name extraction | DONE | `core/name_extract.py`, 46 tests; asks again when it is not a name. |
| F4 No em dashes | DONE | Table in the log; normalizer `core/outbound_text.py`; catalog test with an allow-list. |
| F5 Docs | DONE | Phone checklist J1 to J3, J9 to J11; demo script. |
| F6 Dashboards on a phone | DONE | 12 of 12 cells pass (was 1 of 12). Raw state codes mapped to labels. |
| F7 Downloads | DONE | CSV per table, agenda print button, logging, tests, docs. |

## Mock transcripts (SessionService mock, rule engine live, act tagger scripted)

```
=== A. demo2 lands in the Ravi scene with a due follow-up ===
TEACHER opens the chat
  BOT[app]: कल आपने कक्षा के बाद बताया था कि 'हासिल वाला घटाव' में ज़्यादातर बच्चे अटके। आज अभ्यास कैसा रहा? 'हासिल वाला घटाव' के लिए जो तरीका आज़माना था, उसके बारे में एक बटन दबाइए।
        buttons: [काम किया] [अब भी अटके हैं] [आज़मा नहीं सके]
TEACHER taps [काम किया]
  BOT[app]: ठीक है, दर्ज कर लिया: 'हासिल वाला घटाव' में यह तरीका काम किया।
  BOT[app]: अब वापस रवि के पास: बोर्ड पर 43 − 27 है। रवि से पूछिए कि उसने यह कैसे किया।
        buttons: [वापस अभ्यास पर]
TEACHER taps [वापस अभ्यास पर]
  BOT[app]: अब वापस रवि के पास: अपनी अगली बात कहिए।
=== B. mid-scene: a question to the app ===
TEACHER: तुमने कैसे किया?
  BOT[ravi]: दीदी, तो 7 में से 3 घटाया, 4 आया। फिर 4 में से 2 घटाया, 2 आया। तो जवाब 24 है!
TEACHER: Ab kya karien ?
  BOT[coach]: रवि के साथ आगे बढ़ें: कोई ठोस चीज़ से समझाएँ, फिर एक नया सवाल दें। अभ्यास पूरा करने के लिए 'बस' लिखें।
  (scene teacher turns before=1 after=1; no reply from Ravi)

```

Name step, input "मेरा नाम रिया है।":

```
before: STORED NAME: 'मेरा नाम रिया है।'   then  आपको कैसे संबोधित करें? [शिक्षिका] [शिक्षक]
after:  STORED NAME: 'रिया'                 then  आपको कैसे संबोधित करें? [शिक्षिका] [शिक्षक]
long sentence or markup: nothing stored, bot says "सिर्फ़ अपना नाम लिखिए, जैसे: रिया।"
```

## F6 and F7

- Screenshots (`docs/ux/dashboards/`): `arp-360x640-dark-before.png`, `arp-360x640-dark-after.png`, `trainer-360x640-light-after.png`, `coach-412x915-dark-after.png`.
- Layout check: `scripts/dashboard_layout_check.py` (scratch seeded database, arp.demo, trainer.demo, coach.demo, 360x640 and 412x915, dark and light): before 11 of 12 FAIL, after 12 of 12 PASS. With `--csv` it also downloaded every link on the pages: all returned 200 with a BOM and an attachment header.
- Endpoints added (same role dependency as the page): `GET /arp/export/{table}.csv` (teachers, module_progress), `GET /trainer/export/{table}.csv` (batches, module_progress), `GET /review/export/{table}.csv` (items, moves). Agenda page `cluster_pack_print.html` got a print button.
- Tests: `test_csv_export.py`, `test_dashboard_labels.py`, `test_dash_free.py`, `test_help_question.py`, `test_name_extract.py`, `test_flow_followup.py`.

## Decisions and deviations

- The follow-up is the newest message in the thread; it is not re-ordered ahead of an older scene prompt. The demo logins start from an empty thread plus the seeded scene, so there it comes first.
- "She has started talking in the scene" is the time of her last line sent to a scene (`scene_line_at`, 6 hours, `FOLLOWUP_SCENE_QUIET_HOURS`). A first version used the number of scene turns and the last inbound time; both are non-empty in the seeded demo2, so they hid the follow-up from the very demo it was written for. The integration tests caught it.
- Help questions are not intercepted at steps that take a free line (first hello, delete confirm, handbook ask, rating comment, class and skill asks).
- Coach CSV leaves out the free-text reason column and the action links. Class struggles, teaching skills, training ratings, reported-vs-observed, pack cards and the visit form are not HTML tables and have no download.
- F4: `teacher.html` keeps its tab-title dash (byte-frozen page), `sources.yaml` is source text; both are on the allow-list. `auth/access.py` changed only the text of the suppression message constant, no auth logic.
- Em-dash placeholders "—" for empty values became "-" in the ARP, trainer and coach tables.
- `eval/lowband/REPORT.md` is rewritten by `check_first_load.py` on every run; it was never committed here.
- First-load bytes: 130226 before, 130210 after (16 bytes fewer, catalog strings lost dashes). No static file changed.

## Verified and assumed

Verified (run here):
- `ruff check .`, `mypy --strict backend/app scripts/keep_alive.py`: clean.
- Full gate through `scripts/pytest_fresh_db.py` (no `-q`; log `%TEMP%ull_gate2.log`): 2452 passed, 2 skipped (no audio samples on disk; the teacher.html dash allow-list), 0 failed, 13 min 58 s. A first full run had 4 failures, all caused by my changes (the print page now has one script; the follow-up was hidden for the seeded demo2). Both were fixed and the whole gate was run again.
- `node --test backend/tests/js/chat.test.mjs`: 77 passed.
- `scripts/phone_layout_check.py`: 0 failing of 144 cells. `scripts/composer_layout_check.py`: 0 failures.
- `scripts/check_first_load.py`: PASS, 130210 bytes first load.
- Dashboard layout and CSV download smoke on a real seeded server (above).
- Freeze-check test before and after each docs change.

Assumed, not run: the live site (Render), a real Android phone, WhatsApp delivery and button rendering (caps checked in unit tests only), real Claude phrasing, real voice.
