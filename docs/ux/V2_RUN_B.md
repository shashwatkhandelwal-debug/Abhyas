# V2 run B report (B0, B1, B2)

Branch `feat/v2-national`. Everything below is what I ran this session; anything not run is labelled "assumed".

## B0: neutral model-teacher label (commit `db03a48`)
- New catalog key `speaker_model_teacher_neutral` ("आदर्श शिक्षण" / "Model teacher"). `speaker_label()` and `chat_ui_strings()` (the JSON chat.js reads) now take the teacher's address form: female keeps "आदर्श शिक्षिका"; male, unset (None) or empty gets the neutral string. No client code changed (chat.js reads the string from the page JSON; the server template passes `address_form`).
- Test: `backend/tests/unit/test_model_teacher_label.py` (Hindi and English; f / m / None / "").

## B1: after-class check-in (commit `3bd269b`)
Flag `CLASS_CHECKIN_ENABLED` (default False); `v2_enabled(flag)` = flag or `DEMO_MODE`, so it is ON on the hosted demo site and OFF elsewhere unless set. Also added tunables `CHECKIN_MAX_BUTTONS=5` and `CHECKIN_DEDUPE_SECONDS=60` in `config.py`.

What it does (all deterministic, no LLM, no free text):
- Entry: a server-rendered chip in the chat helper tray (existing `.reply-chip` class, so no JS/CSS change) labelled "कक्षा के बाद: कैसा रहा?" / "After class: how did it go?", shown for onboarded teachers when there is no active scene; also a third button on the week-done message. Typing "कक्षा के बाद" / "after class" works too.
- Step 1 modules are derived from `content/class_struggles.yaml`: each `move_id` (subtraction/regrouping, addition with carry, place value/number writing, reading with matras) plus one "other maths topics" and one "other reading topics" module holding the struggles that have no move. Screen 1 has the four modules and a "more" button; screen 2 has the two others.
- Step 2: went well / some struggled / most struggled. Step 3: the module's closed struggle list (max 5 buttons per screen; "more" pages longer lists).
- Response: the struggle's stored tip (Hindi, or the English paraphrase in the English UI) plus one citation line and chip per stored handbook chunk (existing `format_guide_citation`). No English passage is shown in Hindi.
- Next buttons: "रवि के साथ अभ्यास" (opens the rehearsal set-up for the struggle's `move_id`) and "हैंडबुक से पूछें" when a move exists; otherwise an honest "अभी बना नहीं है" line and only the handbook button. The handbook button shows the existing ask prompt and puts the chat in the ASK state.
- Went well: one acknowledgement line, plus the next move in her path (the existing "अगला तरीका" button when she is in DONE, a plain line otherwise, nothing if no later move exists).
- Storage: table `class_checkin` (teacher_id, module_id, outcome, struggle_ids, created_at), alembic `e9b1d3f5a7c2` (single head, down_revision `c4e6a8b0d2f3`), model `ClassCheckin`; purge-on-delete and demo reset delete it. Idempotence: the flow clears its stage after saving (a second tap gets "यह कक्षा-जाँच दर्ज हो चुकी है"), and the repository also refuses an identical check-in inside `CHECKIN_DEDUPE_SECONDS`.
- Hint line above the composer: new `hint_checkin` branch in `next_action.py` while a check-in screen is open.

### Deviations and decisions (please read)
1. **Button limits.** `OutboundMessage.buttons` was capped at 3 and `Button.title_hi` at 20 characters. I raised the message cap to 5 (the WhatsApp channel already sends more than 3 as a list; the web renders all). Titles stay at 20, so the in-message entry button is "कक्षा के बाद: कैसा?" / "After class?"; the full requested label is used on the web chip. "रवि के साथ यह गलती अभ्यास करें" is split into the button "रवि के साथ अभ्यास" and the full sentence in the message above it.
2. **"6 of the 14 struggles have a move"**: the stored file has **7 with a move and 7 without** (the design note's own table lists seven). The test asserts 7/7.
3. **Catch-up option left out**, as instructed: I searched the stored chunks for absence / catch-up wording and found no chunk about children returning after absence (one unrelated hit), so no such option exists.
4. **"इस हफ्ते आज़माएँ" line left out**: neither `class_struggles.yaml` nor the move cards supply a "try this week" line for a struggle.
5. **Practice launch skips the learn step.** The rehearsal opens at its set-up (1-1 or three children). Module progress would otherwise mark "learn done" for that move; a context field `checkin_jump_move` prevents that (test included).
6. **demo2 lands inside the Ravi scene**, where the entry chip is deliberately not shown (and the start button is ignored mid-scene). I read "within 2 taps of landing in a scene-free state" as: from a scene-free state (demo2 after its scene, in DONE; demo3's landing LEARN step) the entry tap plus one module tap reaches the outcome screen. Tested for both profiles. Starting the check-in from inside demo2's seeded scene is not built.
7. The existing assertion `head_rev == "c4e6a8b0d2f3"` in `test_db_models.py` had to move to the new head; I kept the old link as an assertion about the new head's `down_revision` and kept every other chain assertion.
8. `FakeSessionRepository` (tests) got a `record_class_checkin` method.

### Not touched
Rule engine, guards, auth/login code, composer layout rules, `chat.js`, `app.css`, Render/Supabase settings; nothing deployed.

## B2: three mock check-ins through the real SessionService (Hindi UI)
Run by a throw-away script (kept in %TEMP%, not in the repo) that drives `SessionService.handle_inbound` with the in-memory repository, the same path as `backend/tests/unit/test_class_checkin.py`. Account profiles copy the seeded demo teachers (name, current move, struggles, path); demo2 is placed in its post-scene DONE state because the check-in is not offered inside a scene. Run 1 is the practice-launch run, run 2 the mapped-only run, run 3 the went-well path. Each "BOT:" block is one message; the bracketed lines are its buttons.

```
### Run 1: demo2 (she), struggle WITH a practice move, taps the practice button
(account profile: demo2, address_form=f, weekly state=DONE)

TEACHER taps: [कक्षा के बाद: कैसा रहा?]
BOT:
    कक्षा के बाद की जाँच: आज बच्चों के साथ किस विषय पर काम हुआ? नीचे से चुनिए।
    [दहाई-इकाई, संख्या]
    [हासिल वाला जोड़]
    [हासिल वाला घटाव]
    [मात्रा वाले शब्द]
    [और विषय देखें]

TEACHER taps: [हासिल वाला घटाव]
BOT:
    'हासिल वाला घटाव' में बच्चों के साथ कैसा रहा?
    [अच्छा रहा]
    [कुछ बच्चे अटके]
    [ज़्यादातर अटके]

TEACHER taps: [कुछ बच्चे अटके]
BOT:
    'हासिल वाला घटाव' में बच्चे कहाँ अटके? एक चुनिए।
    [हासिल वाला घटाव]

TEACHER taps: [हासिल वाला घटाव]
BOT:
    'हासिल वाला घटाव': पुस्तिका के आधार पर सुझाव:
    घटाव में पहले "बचे कितने" वाले सवाल ठोस चीज़ों से हल करवाएँ और बच्चों को अपने तरीके बनाने दें; मानक तरीका उसके बाद सिखाएँ।
    स्रोत: निपुण भारत दिशानिर्देश, पृष्ठ 281
    स्रोत: निष्ठा FLN, पृष्ठ 427
    दर्ज कर लिया गया। इसमें बच्चों की कोई जानकारी दर्ज नहीं होती।
    (citation chips: स्रोत: निपुण भारत दिशानिर्देश, पृष्ठ 281 | स्रोत: निष्ठा FLN, पृष्ठ 427)
BOT:
    इस दिक्कत के लिए अभ्यास का केस है: हासिल वाला घटाव: बंडल खोलकर। रवि के साथ यह गलती अभ्यास करें, या हैंडबुक से और पूछें।
    [रवि के साथ अभ्यास]
    [हैंडबुक से पूछें]

TEACHER taps: [रवि के साथ अभ्यास]
BOT:
    अब अभ्यास की बारी है। आप किसके साथ अभ्यास करेंगे? किसी एक बच्चे से अकेले बात करना सबसे अच्छा तरीका है।
    [1-1 बच्चे से बात]
    [तीन बच्चों के साथ]

stored: [('NUM_SUB_REGROUP_BUNDLES', 'some', ['NUM_SUB_REGROUP'])]
state after: REHEARSE_INTRO move: NUM_SUB_REGROUP_BUNDLES stage: choose_mode

### Run 2: demo2 (he), mapped-only struggle (tip and citations, no practice move)
(account profile: demo2, address_form=m, weekly state=DONE)

TEACHER taps: [कक्षा के बाद: कैसा रहा?]
BOT:
    कक्षा के बाद की जाँच: आज बच्चों के साथ किस विषय पर काम हुआ? नीचे से चुनिए।
    [दहाई-इकाई, संख्या]
    [हासिल वाला जोड़]
    [हासिल वाला घटाव]
    [मात्रा वाले शब्द]
    [और विषय देखें]

TEACHER taps: [और विषय देखें]
BOT:
    कक्षा के बाद की जाँच: आज बच्चों के साथ किस विषय पर काम हुआ? नीचे से चुनिए।
    [गणित के अन्य विषय]
    [भाषा के अन्य विषय]
    [और विषय देखें]

TEACHER taps: [गणित के अन्य विषय]
BOT:
    'गणित के अन्य विषय' में बच्चों के साथ कैसा रहा?
    [अच्छा रहा]
    [कुछ बच्चे अटके]
    [ज़्यादातर अटके]

TEACHER taps: [ज़्यादातर अटके]
BOT:
    'गणित के अन्य विषय' में बच्चे कहाँ अटके? एक चुनिए।
    [गिनती]
    [संख्याओं की तुलना]
    [कहानी वाले सवाल]
    [छोटे जोड़-घटाव]

TEACHER taps: [गिनती]
BOT:
    'गिनती': पुस्तिका के आधार पर सुझाव:
    गिनवाते समय हर चीज़ को छुआएँ या हटवाएँ, और पहले संख्या-नामों का क्रम पक्का करवाएँ। हर चीज़ के लिए एक ही संख्या बोली जाए।
    स्रोत: निपुण भारत दिशानिर्देश, पृष्ठ 85
    स्रोत: गणित संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 24
    दर्ज कर लिया गया। इसमें बच्चों की कोई जानकारी दर्ज नहीं होती।
    (citation chips: स्रोत: निपुण भारत दिशानिर्देश, पृष्ठ 85 | स्रोत: गणित संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 24)
BOT:
    इस दिक्कत के लिए अभ्यास का केस अभी बना नहीं है। आप हैंडबुक से पूछ सकते हैं।
    [हैंडबुक से पूछें]

stored: [('OTHER_numeracy', 'most', ['NUM_COUNTING'])]
state after: DONE move: NUM_SUB_REGROUP_BUNDLES stage: 

### Run 3: demo3 (she), went well, in the DONE state (so the next move is offered)
(account profile: demo3, address_form=f, weekly state=DONE)

TEACHER taps: [कक्षा के बाद: कैसा रहा?]
BOT:
    कक्षा के बाद की जाँच: आज बच्चों के साथ किस विषय पर काम हुआ? नीचे से चुनिए।
    [दहाई-इकाई, संख्या]
    [हासिल वाला जोड़]
    [हासिल वाला घटाव]
    [मात्रा वाले शब्द]
    [और विषय देखें]

TEACHER taps: [मात्रा वाले शब्द]
BOT:
    'मात्रा वाले शब्द' में बच्चों के साथ कैसा रहा?
    [अच्छा रहा]
    [कुछ बच्चे अटके]
    [ज़्यादातर अटके]

TEACHER taps: [अच्छा रहा]
BOT:
    ठीक है, दर्ज कर लिया: 'मात्रा वाले शब्द' में कक्षा का अभ्यास अच्छा रहा। इसमें बच्चों की कोई जानकारी दर्ज नहीं होती।
    आपके क्रम में अगला तरीका: हासिल वाला जोड़: 10 तीलियों का बंडल बनाकर।
    [अगला तरीका]

stored: [('LIT_MATRA_BLENDING', 'well', [])]
state after: DONE move: LIT_MATRA_BLENDING stage:
```

## Verification
Verified this session (ran it):
- `ruff check .` clean; `mypy --strict backend/app scripts/keep_alive.py` clean (172 files).
- `backend/tests/unit/test_class_checkin.py`: all pass (Hindi and English, flag on and off, she and he, demo2 and demo3 profiles, mapped-only struggle, rehearsal launch, double-tap idempotence, page chip).
- Whole `backend/tests/unit` + `content/tests` passed (exit 0) before the B1 commit.
- Postgres integration on fresh databases: new table + migration round trip (upgrade, downgrade to base, upgrade) + purge + demo reset (26 passed, 14 passed).
- Full gate: (gate still running when this was written; see below)

Assumed (not run): behaviour on the hosted Render site; WhatsApp delivery of the 5-option list (the code path exists, the Meta call is mocked in tests); real-browser behaviour of the server-rendered chip (it relies on the existing delegated `.reply-chip` click handler in chat.js, which I read but did not exercise in a browser); the production `DEMO_MODE` value.

## Payload (python scripts/check_first_load.py)
- Before any change this run: first load 127.63 KB raw / 30.49 KB gzip; all offline assets 148.28 KB raw / 37.71 KB gzip.
- After B0, after B1 and at the end: first load 127.7 KB raw / 30.5 KB gzip; offline assets 148.34 KB raw / 37.73 KB gzip (limit 150 KB, headroom about 1.66 KB). The script reports KB to two decimals, not exact bytes.
- No client file changed: `chat.js` 67,968 B, `app.css` 35,817 B, `recorder.js` 5,918 B, `ack.js` 1,097 B (file sizes). The +0.06 KB is the template and page-JSON change from B0.
- The check-in chip adds 312 B to the teacher HTML when shown (the measurement page is an un-onboarded teacher, so the chip is not in the measured number); headroom with the chip is about 1.35 KB, above the 1,000 B floor.
- `node --test backend/tests/js/chat.test.mjs` was not run: no client file changed.

## Undone / not built
- No ARP or trainer aggregate for check-ins (not asked for; if added later it must use n<10 suppression).
- Check-in start from inside a live scene (deviation 6).
