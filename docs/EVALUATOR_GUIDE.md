# Evaluator guide (about one hour)

Abhyas is a voice-first practice partner for primary (Class 1–3) teachers, in Hindi. A teacher practises a
teaching move with a simulated child (**one-on-one**, the main way) or with three children (Ravi, Priya, Aman)
whose answers come from a rule engine, never from the language model, and gets coach feedback on their own words.

- **Link:** `<HOSTED URL>` (Render free plan: if it has been idle, the first page takes **about a minute** to
  wake; open `<HOSTED URL>/healthz` first and wait for `"status": "ok"`).
- **Passwords:** `<DEMO_PASSWORD>` for the six demo logins and `<ADMIN_PASSWORD>` for `admin`. They are in the
  submission form, not in the repository. With `DEMO_MODE` on, the login page also shows the demo password.
- **Language:** the interface is Hindi by default. Use the **हिंदी / English** switch on the login page or in
  the chat menu (☰) to see the whole interface in English; the choice is remembered. The simulated
  children and the coach speak Hindi in both.
- **Resetting:** the three shared teacher logins are **reset to their starting state when you log out**
  (chat history, step in the weekly loop, scores and your answers are removed; demo2 returns to its one-on-one
  scene with Ravi and demo3 to its three completed modules; the PWA also clears its local message cache). The
  admin **Reset demo** button restores all three the same way. Use **Log out** between experiments. Other judges share these logins, so do not rely on
  anything surviving a logout. The login page carries the same warning ("Demo accounts are shared: pick one not in
  use; chats reset on login and logout"), and offers `teacher.demo1`, `teacher.demo2` and `teacher.demo3`, so two judges can each take a different one.

## 10-minute judge path

Three checkpoints, one account each. Log out between accounts (the three teacher logins reset on login and logout).

1. **The relapse (about 3 min, `teacher.demo2`).** Log in, open `/teacher`: you are already inside the one-on-one scene with Ravi (43 - 27).
   Tap the sample chip that tells the answer (the Hinglish "tell the answer" line) or type "उत्तर 16 होता है।". Ravi repeats it without
   understanding. Then type "अब ये करो: 61 में से 28।". Ravi gives the old mistake again and the strip beside him reads "अटका हुआ · फिर अटका".
   No language model decides what Ravi says; a fixed rule engine does.
2. **The check-in with a cited tip (about 3 min, `teacher.demo2`).** Tap **कक्षा के बाद: कैसा रहा?**, tap the first module "हासिल वाला घटाव",
   tap "ज़्यादातर अटके", tap "हासिल वाला घटाव". You get one tip from the handbook with two source chips ("स्रोत: ..., पृष्ठ N"); tap a chip to read the
   passage it came from. Nothing about any child is stored.
3. **The trainer view (about 3 min, `trainer.demo`).** Open `/trainer`. Scroll to **संकुल बैठक पैक** (the most-reported difficulty with a move to
   practise together) and to **शिक्षकों ने बताया बनाम भ्रमण में दिखा** (reported versus observed, with the caption that these are self-reported and
   observed counts, not learning outcomes). Groups below 10 teachers show the privacy message instead.

### Go deeper

- The follow-up the next school day: see "The regrouping thread" below (`teacher.demo2`).
- The ARP visit checklist (`arp.demo`) and the privacy case on the same page (7 consenting teachers of 12).
- The adaptive "why this next" line (`teacher.demo3`, after finishing a week).
- Level sorter, talk-move feedback, national and state labels: the table "New in V2" further down.
- Low connectivity: the last item of "A suggested hour".

## The regrouping thread

One demo story runs through five screens, all about **regrouping in subtraction** (हासिल वाला घटाव). All rows behind it are demo data and
are labelled that way; none belongs to a real teacher.

| Step | Account | Exact taps | What you should see |
|---|---|---|---|
| 1. Check-in | `teacher.demo2` | **कक्षा के बाद: कैसा रहा?**, first module, "ज़्यादातर अटके", "हासिल वाला घटाव". | The cited tip (two source chips). A follow-up is stored for the next school day. |
| 2. Follow-up | `teacher.demo2` | Log in (or reopen `/teacher`). `teacher.demo2` already has a check-in from yesterday and a follow-up that is due on every login. | A message at the end of the chat: "कल का अभ्यास कैसा रहा?" with three buttons: "काम किया", "अब भी अटके हैं", "आज़मा नहीं सके". "अब भी अटके हैं" gives a different source chip plus the practice button; "आज़मा नहीं सके" asks why with four buttons, and "कई कक्षाएँ साथ" points to the level sorter. A second tap says the answer is already saved. |
| 3. Observation | `arp.demo` | Open `/arp`, find **कक्षा-भ्रमण सूची**, tap "भ्रमण दर्ज करें: ..." for a teacher, tick talk moves, pick one next step, save. | A saved message. No free text, no child data. The practice to look for is the difficulty from that teacher's last check-in, if there is one. |
| 4. Trainer view | `trainer.demo` | Open `/trainer`, scroll to the pack and to **शिक्षकों ने बताया बनाम भ्रमण में दिखा**. | Regrouping at the top: 14 teachers answered the follow-up (worked 5, still stuck 7, could not try 2) and the practice was seen on 12 visits. The second row (addition with carrying) has no visit counts, so its observed cell is hidden under the 10 rule. |
| 5. Adaptive path | `teacher.demo3` | Finish the week (the literacy group scene, feedback, reflection, rating). | On the week-done message and on the next learn message, one line "क्यों अभी यह: ..." names why the next practice was chosen (demo3 has an older regrouping check-in answered "still stuck"). This takes the whole weekly loop, so allow time; the logic is covered by tests. |

Two judges on one account interfere with each other: logging in or out resets that demo teacher, and a second login wipes the first
judge's follow-up answers and chat. Pick an account nobody else is using.

### Flags and how to toggle them

Three settings flags control the new screens. They are environment settings on the host; this guide does not change them.

| Flag | What it controls | Default |
|---|---|---|
| `FOLLOWUP_ENABLED` | the next-school-day follow-up (steps 1 and 2) | off, on in demo mode |
| `OBSERVATION_ENABLED` | the ARP visit checklist and "reported versus observed" (steps 3 and 4) | off, on in demo mode |
| `ADAPTIVE_PATH_ENABLED` | the adaptive next practice and its "why" line (step 5) | off, on in demo mode |

`DEMO_MODE=true` turns all three on (and the other demo-only screens). To turn one on outside demo mode set it to `true`; to turn all off
set `DEMO_MODE=false` and leave the flags unset. With a flag off the screens are simply absent and the behaviour is the one before the flag existed.
The demo rows are created only by the seed (`SEED_ON_BOOT=true` or `python -m backend.app.db.seed`) and only in demo mode, so the trainer
cards are empty until a seed has run with this code.

## The seven logins

| Login | Password | Start here | What it shows |
|---|---|---|---|
| `teacher.demo1` | `<DEMO_PASSWORD>` | `/teacher` | **A new teacher.** Nothing done yet: the first message starts the welcome, the service consent question (with a "more" button; score sharing is asked later after first rehearsal) and the short onboarding, then the first move. Tap the buttons or type/speak. |
| `teacher.demo2` | `<DEMO_PASSWORD>` | `/teacher` | **Mid-rehearsal, one-on-one with Ravi.** Already inside a 1-1 scene of "हासिल वाला घटाव" (subtraction with regrouping, 43 − 27): the diagnosis is done and one question asked, so the header shows "रवि से 1-1 बात", the board (43 − 27), a progress cue ("अपना तरीका बता रहा है"), the turn counter (1/10) and an **end practice** button. Use the sample chips or type, e.g. "देखो, ये 4 बंडल और 3 खुली तीलियाँ हैं, 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो।" and then give a new problem ("अब 52 में से 17 करो"): the cue moves, and when Ravi gets the new problem right the scene ends. Finish the scene to get coach feedback (strength with your own words quoted, one change, an exact sentence) on the **one-on-one rubric**, and the retry. After the reflection step you are asked to **rate the training**: a 1–5 usefulness score (say or type it, or tap 1 / 3 / 5) and an optional one-line comment (voice or text, or *Skip*). |
| `teacher.demo3` | `<DEMO_PASSWORD>` | `/teacher` | **Three modules completed, on the learning step of the next weekly move** (reading matra words by blending letter sounds, `LIT_MATRA_BLENDING`). The chat already shows the learning-step message with its **two buttons**, labelled in Hindi: "समझ गई, आगे" (Got it, next: continues to the explain-back step) and "फिर से सुनें" (Listen again: repeats the step). Typing other text does not advance it; the reply reminds you of the two buttons. ☰ → **Modules** shows the three completed numeracy modules. This login has *not* agreed to share scores, so it never appears in the ARP digest or trainer counts. **Literacy group scene: 3 actions from the start:** (1) tap "समझ गई, आगे"; (2) send one sentence in your own words (the explain-back step); (3) tap the listen button ("सुनना चाहेंगी…" prompt, `btn_listen`). The group scene (Ravi, Priya, Aman; board word "मेला") then opens at turn 0/8; speak or type to the children, e.g. "प्रिया, बोर्ड पर क्या लिखा है? पढ़ो।", then say "बस" to end and get feedback (at least 3 teacher turns are needed for advice). |
| `arp.demo` | `<DEMO_PASSWORD>` | `/arp` | **Cluster resource person**, cluster KNP-C01: weekly digest of *consenting* teachers only, questions escalated from the chat (answer them here), classroom-observation form. The **Cluster meeting pack** card shows the privacy message here: this demo cluster has 7 consenting teachers, fewer than 10, so nothing is shown (correct, and on purpose: the same 7-of-12 split shows the small-group rule on the digest). To see a full pack, log in as `trainer.demo`. The demo check-ins behind it are labelled demo data, belong to the synthetic cohort teachers only (not the three shared logins) and exist only after a seed has run (`SEED_ON_BOOT=true` on a boot, or `python -m backend.app.db.seed`); a re-seed rebuilds them. |
| `trainer.demo` | `<DEMO_PASSWORD>` | `/trainer` | **DIET/SCERT trainer**, district Kanpur Nagar: module × batch table (completion, most-missed key point, rubric and ladder distributions). Also the **training ratings** card: average, count and latest comments from consenting teachers in the district (hidden below 10 ratings). Groups with fewer than 10 teachers are suppressed (batch KNP-B3 has 8 and shows the privacy notice); `/trainer/export.csv` follows the same rule. No teacher names appear. **Cluster meeting pack** card: the two most-reported difficulties, a move to practise together and a printable agenda (demo data, labelled). |
| `coach.demo` | `<DEMO_PASSWORD>` | `/review` | **Coach review console**: queue of AI scores and escalations that need a human look, per-item resolve, calibration labelling, move-card review. |
| `admin` | `<ADMIN_PASSWORD>` | `/admin` | **Admin dashboard**: latency, token use, guard results, scheduler jobs, WhatsApp templates, the **training ratings** card (all teachers, no suppression) and the demo controls (*Reset demo*, *fast-forward*). |

## Downloads (CSV) and the printable agenda

Every table on the three dashboards has a **डाउनलोड (CSV)** link (English: **Download (CSV)**) just above it. The file is exactly the table you see, with the same privacy rule: a group of fewer than 10 is exported as the privacy text, never as hidden numbers. UTF-8 with a byte-order mark, so Excel opens the Hindi correctly. File name: `abhyas_<view>_<table>_<date>.csv`.

| Login | Page | Download links |
|---|---|---|
| `arp.demo` | `/arp` | **Teachers** table (above the table; the module-progress table has its own link once the cluster has 10 consenting teachers). |
| `trainer.demo` | `/trainer` | **Module progress** table and the **batch x move** table (above it). The older `/trainer/export.csv` still works. |
| `coach.demo` | `/review` | The review-queue table on each tab, and the **moves** table on the content tab. Links and the free-text reason column are not exported. |

Each role can download only its own tables; another role gets a 403. Each export is logged (role, page, table, time) with no personal data.

The **meeting agenda** page (`/trainer/cluster-pack/print`, or `/arp/cluster-pack/print`) has a **डाउनलोड / प्रिंट** button at the top. It opens the phone's print dialog (save as PDF there). The demo-data label shows on screen and in the print.

## Shared accounts and the first visit

- **One judge per account.** `teacher.demo1`, `teacher.demo2` and `teacher.demo3` are shared logins with one state
  each. Two judges on the same account will interfere with each other's chat and scene. **Logging in or out resets that
  demo teacher** to its starting state, so a second person logging in wipes the first person's session. Pick one that is
  not in use.
- **First visit after idle.** On Render's free plan the service sleeps when idle. The first request can take roughly a
  minute (Render's documented free-tier behaviour is a 40–60 s spin-up; we did not time it on the hosted site, so treat
  "about 50 s" as an estimate). Open `<HOSTED URL>/healthz` first and wait for `"status": "ok"`. If the page is
  requested while the server is still waking, it says **"सर्वर जाग रहा है — इसमें करीब एक मिनट लग सकता है…"** and
  retries by itself. The service worker only helps **after** a first successful load (it then serves the shell and the
  last messages offline); it cannot make the very first cold start faster. A keep-alive pinger
  (`eval/KEEP_ALIVE.md`) is the recommended mitigation.

## The demo shortcuts tray (demo logins only)

On the demo teacher logins, a **"डेमो शॉर्टकट" / "Demo shortcuts"** tray sits above the chat (collapsed at first; tap it
to open, and it stays as you left it for the session). It gives one-tap inputs so you can test the core claim without
typing Hindi. Each chip sends the text as if you had said it. While a chip is in flight, all chips are locked (they
free up on the reply, on a failure, or after 90 s).

- **Chip C (handbook) is always there**, in every step and scene.
- **A1, A2 and B appear only after 30 seconds of no activity in a subtraction scene** (the board shows a subtraction
  such as 52 − 17). Typing, tapping any button, sending, recording, or a request in flight resets the 30 seconds and
  hides them again. They are never sent for you, and they do not appear during onboarding, consent, learn steps, or
  place-value, addition and literacy scenes. Until then the tray shows one line saying so.
- **Use `teacher.demo2` for the tray** (it starts inside the 43 − 27 subtraction practice). `teacher.demo1` is the onboarding
  flow (no scene yet, so only chip C), and `teacher.demo3` is a literacy move (also only chip C).

| Chip | Sends | What you should see |
|---|---|---|
| **A1: उत्तर बताना** | "रवि, सही उत्तर N है", N computed from the problem on the board | The teacher *tells the answer*. Ravi repeats it without understanding. Only in a subtraction scene. |
| **A2: नया सवाल (61-28)** | "अब 61 में से 28 घटाओ" | A new problem. The board changes to 61 − 28; Ravi answers it with his old mistake (47 for 61 − 28). |
| **B: बंडल-तीली सुधार** | "चलो {a} में से {b} फिर से करते हैं: देखो, … बंडल और … खुली तीलियाँ हैं, … तो एक बंडल खोलो।", built from the **current board** | Bundles-and-sticks scaffolding on the problem on the board (on 61 − 28, Ravi reaches 33). Only when regrouping is needed (units of the first number are smaller than units of the second). |
| **C: हैंडबुक सवाल (RAG)** | "सवाल: उल्टी गिनती करके घटाव कैसे सिखाएँ?" | A handbook answer with a source chip, not a child reply. |

To ask your own handbook question, start the message with **"सवाल:"**; without the prefix the
text is treated as something said to the child.

## Modules

Chat menu (☰) → **मॉड्यूल / Modules** (`/teacher/modules`) lists the three numeracy modules (subtraction with
regrouping first). Each has four steps: **learn → spot a child's confusion (1-1) → practise → check**. *Start*
opens the chat on the learn step; the 1-1 diagnosis and scene are the ones described above; after the coach
feedback, *Continue* asks one closing question in your own words, which a guarded model (with a keyword
fallback) checks against the module's key points. The page ticks each step as it is completed. `trainer.demo`
and `arp.demo` show a **Module progress** card (consenting teachers only, counts only, small groups hidden on
the trainer page); rows are labelled **Pilot** (real teachers) or **Demo (synthetic)** (the fictional cohort and
the shared demo logins). `teacher.demo3` starts with all three modules complete.

## After-class check-in ("कक्षा के बाद: कैसा रहा?")

A four-tap, closed-list check-in: module, how it went, which difficulty, one handbook tip with its source chip. No
typing and no language model; nothing about individual children is saved. It is on in demo mode for onboarded
teachers. The chip sits in the tray just above the composer (English UI: "After class: how did it go?").

- **`teacher.demo2` (inside the one-on-one scene with Ravi).** Tap the chip (1), tap "हासिल वाला घटाव" (2), tap "ज़्यादातर
  अटके" (3), tap "हासिल वाला घटाव" again for the difficulty (4). You get the tip and its citation chips and two
  buttons: **वापस अभ्यास पर** and "हैंडबुक से पूछें". The scene is only paused, not touched: "वापस अभ्यास पर" puts you
  back with Ravi ("अब वापस रवि के पास: अपनी अगली बात कहिए।") at the same turn and board. "It went well" ("अच्छा रहा") also ends
  with "वापस अभ्यास पर". Typing a sentence while a check-in is open counts as your next line to Ravi and drops the
  unfinished check-in. Practice is not offered from inside a scene, because it would replace the one you are in.
- **`teacher.demo3` (on the learn step, no scene).** Tap the chip, "मात्रा वाले शब्द", "कुछ बच्चे अटके", "मात्रा छूट जाना".
  The last screen offers **रवि के साथ अभ्यास**. Tapping it opens the practice for that move **directly at the setup
  of the rehearsal: the learn step is skipped** (you are asked to pick a child, then the scene starts).
- On **WhatsApp** a screen with more than 3 options cannot be 3 reply buttons (Meta limit; titles are cut to 20
  characters there). It is sent as one interactive list opened with the "विकल्प" button, so no option is dropped. The
  web chat shows up to 5 buttons with their full titles. The check-in chip itself is a web chat feature; on WhatsApp the
  check-in starts from the "After class" button on the week-done message or by typing "कक्षा के बाद" outside a scene.

## New in V2: what to try and the exact taps

All of these are on in demo mode. They are controlled by settings flags (all default **off** outside demo mode; `DEMO_MODE`
turns them on): `CLASS_CHECKIN_ENABLED`, `CHILD_STRIP_ENABLED`, `LEVEL_SORTER_ENABLED`, `TALK_MOVES_ENABLED`,
`CLUSTER_PACK_ENABLED`. To turn one off on a deployment, set `DEMO_MODE=false` and leave its flag unset (that turns all of
them off, and also hides the other demo-only screens); to turn one on outside demo mode set that flag to `true`. Flags are environment settings: this guide does not
change them. The national / state source labels have no flag.

| Feature | Account | Taps | What you see |
|---|---|---|---|
| **Child understanding strip** | `teacher.demo2` | Look at the scene bar; send a line asking Ravi how he did it, then a bundles-and-sticks line, then a new problem. | A label beside the child ("अटका हुआ", "समझ रहा है", "समझ गया") and "फिर अटका" if he slips on the new problem after "getting it". A child only *told* the answer shows "stuck", not "stuck again". |
| **Talk-move feedback** | `teacher.demo2` | Finish the scene ("बस"). | In the coach bubble, after the advice: "बच्चों से बात करने का तरीका", one strength and one next step, with your own words in the quote badge. Group scenes (use `teacher.demo3`'s literacy scene) show the same block without a quote. |
| **Level sorter** | `teacher.demo2` or `teacher.demo3` | Tray chip "कक्षा को स्तर के हिसाब से समूहों में बाँटें" (tap 1), "पढ़ना" or "गणित" (tap 2), then one range per level. | 2-3 groups, who to sit with first, one 10-minute activity per group with source chips; a multigrade line for reading only. Inside demo2's scene it pauses the scene and "वापस अभ्यास पर" returns. |
| **Check-in** | see the section above | | |
| **National / state labels** | any | Open any source chip text. | "(राष्ट्रीय)" for NCERT / NIPUN / NISHTHA, "(राज्य: उ.प्र.)" for the UP handbooks. |
| **Cluster meeting pack** | `trainer.demo` | Scroll to "संकुल बैठक पैक"; tap "छापने लायक एजेंडा खोलें". | Two difficulties with teacher counts, a move to practise together, a one-page agenda. Data is demo data and is labelled. `arp.demo` shows the privacy message instead (7 consenting teachers). |

Reminders: the first request after idle takes about 40-60 seconds on Render's free plan (open `/healthz` first), and two
judges on one account interfere with each other (logging in or out resets that teacher).

## Track B: two new practice scenes and five new screens (exact taps)

All of these are on in demo mode and controlled by settings flags (off outside demo mode; `DEMO_MODE=true` turns them on, and with
every flag off the app behaves as before). Flags: `SCENE_NUM_COMPARE_ENABLED`, `SCENE_LIT_LETTER_SOUND_ENABLED`,
`TRAINING_GAP_ENABLED`, `FOCUS_CARD_ENABLED`, `FAST_START_ENABLED`, `SUPPORT_FRAMING_ENABLED`, `OBSERVATION_TO_TEACHER_ENABLED`.
(`MODEL_AUDIO_ENABLED` exists but does nothing: no cached model-practice audio exists, see `docs/ux/TRACKB_LOG.md`.) The scenes are
reached from the check-in and the practice set-up, not from the weekly path, so the weekly loop is unchanged.

| Feature | Account | Taps | What you see |
|---|---|---|---|
| **Scene: comparing two-digit numbers** | `teacher.demo3` | Tray chip "कक्षा के बाद: कैसा रहा?"; on the module list tap "और विषय देखें" until "संख्याओं की तुलना" appears and tap it; "ज़्यादातर अटके"; "संख्याओं की तुलना"; read the cited tip; tap "रवि के साथ अभ्यास"; then "तीनों बच्चे" (or one child). | Board "39 और 41: कौन बड़ा?" (text only; no bundles drawing). Ravi says "39!". Type "रवि, तुमने कैसे तय किया कि 39 बड़ा है?": he explains "9 और 1 में 9 बड़ा है, तो 39 बड़ा". Type "सब लोग देखो, ये रहे 3 बंडल और 9 खुली तीलियाँ, यानी 39, और 4 बंडल और 1 तीली, यानी 41।": he now says 41 with the bundles. Hero beat: "रवि, सही उत्तर 41 है।" (he only repeats it), then "रवि, अब ये सवाल: 28 और 33, कौन बड़ा?": he says "28!" and the strip shows "अटका हुआ · फिर अटका". |
| **Scene: letter name versus letter sound** | `teacher.demo3` | Same check-in; module "अक्षर की ध्वनि"; "ज़्यादातर अटके"; "अक्षर और ध्वनि"; practice button. | Board word "बकरी". The children say "ब से बतख" (the chart name, not the sound). Type "रवि, तुमने इसे कैसे पढ़ा?", then "सब लोग, पहले अक्षर पर उँगली रखो और उसकी ध्वनि निकालो।", then "सब लोग, मैं करके दिखाती हूँ, मेरे साथ: ब, क, री, बकरी।". Hero beat: "रवि, सही उत्तर बकरी है।" then "रवि, अब शब्द कमल पढ़ो।": "क से कबूतर!". `teacher.demo2` is inside a scene, where the check-in only offers the way back, so use demo3. |
| **Where training is not landing** | `trainer.demo` | Open `/trainer`, scroll to "प्रशिक्षण कहाँ नहीं पहुँच रहा"; tap "कार्ड देखें" on a row. | Four moves, sorted by the largest gap. Per move and habit: share and count of teachers whose latest rehearsal still shows it (told the answer, did not ask how or why, did not name a child, did not use concrete objects). "स्थानीय मान" has 9 teachers, so every cell shows the privacy message. The caption says it is from simulated rehearsals, not classroom observation, and that it includes demo data. The card link opens the key points with their sources. |
| **Today's tip** | `teacher.demo3` | Open `/teacher`: the question "क्या हर दिन चैट खोलने पर एक छोटा सुझाव दिखाएँ?" appears. Tap "हाँ", then reload the page. | One "आज का सुझाव" message with one step and its source chip, buttons "अभ्यास करें", "हैंडबुक से पूछें", "बंद करें". At most one a day; "बंद करें" turns it off. `teacher.demo2` is seeded as opted in but is inside a scene it has started, so its tip waits until you end the scene ("बस") and reload. |
| **Straight to practice** | a new account, or `teacher.demo1` | During onboarding answer the experience question with "6-10 साल" (or "10+"), finish onboarding. | On the first learn message a third button "सीधे अभ्यास" and the line that you can start with practice and see the key points any time. Tap it: the practice set-up opens with "मुख्य बातें देखें" next to the mode buttons. Answer "2-5 साल" or "0-1" instead and the button is absent: model practice stays first. |
| **Support wording on the ARP page** | `arp.demo` | Open `/arp`. | Where a teacher used to be marked "मदद चाहिए" in red, the neutral "साथ में अभ्यास करें"; above the teacher list, the visit checklist and the visit list the line "ये शिक्षक अपनी मर्ज़ी से आपके साथ अंक साझा करते हैं। यह मूल्यांकन नहीं, सहयोग के लिए है।" |
| **The ARP's note reaches the teacher** | `arp.demo`, then `teacher.demo2` | As ARP: "भ्रमण दर्ज करें: डेमो शिक्षिका 2", tick talk moves, one next step, save. Then log in as `teacher.demo2` and open `/teacher`. | At the end of the thread: "आपके ARP ने देखा: ... एक बात आज़माएँ: ..." with one button "ठीक है". No score, no level; it changes nothing else. Tap "ठीक है" for a thank-you line. |

Not built: a school-setting question at onboarding (it needs a database change), and audio on the model practice.

## A suggested hour

1. **teacher.demo2 (10 min).** Continue the 1-1 scene with Ravi using the sample chips (including the Hinglish
   "tell the answer" chip: the child repeats the answer without understanding, which is the point, and
   relapses on a new problem). Notice that the same input always gets the same child behaviour. Finish, read
   the feedback, tap retry. After retry you choose again: **1-1 बच्चे से बात** (default) or **तीन बच्चों के साथ**.
   For 1-1 pick Ravi, Priya or Aman (each has a different mistake, not shown yet), then say what you think the
   child's mistake is (try the diagnosis chip, "उलझन पहचानें"): the app compares it with the child's real mistake
   (correct / partly / wrong, decided by fixed keyword rules, not by the language model) and then reveals it.
   Try a problem the children cannot handle ("रवि, 200 में से 120 घटाओ"): the child just says it is too big.
2. **teacher.demo1 (10 min).** Go through welcome and consent, then the learn step and explain-back. Try a
   voice note (the mic button: tap to start, tap again to send, or hold). If a provider key is missing the
   voice may be a mock; the admin dashboard shows the configured providers.
3. **Ask a question (5 min).** In `teacher.demo1` or `teacher.demo2` type a how-to question, for example "उल्टी गिनती करके
   घटाव कैसे सिखाएँ?" or "कविता पोस्टर पर कार्य कैसे करवाएँ?". The answer comes only from the ingested
   official documents and ends with a **citation chip** ("स्रोत: …, पृष्ठ N"). **Tap the chip** to read the
   excerpt it came from, with its PDF page. An off-topic question ("आज का क्रिकेट मैच कौन जीता?") is
   declined instead of answered.
4. **After-class check-in (3 min).** In `teacher.demo2` take the four taps above and use "वापस अभ्यास पर".
   Then `teacher.demo3` for the practice that skips the learn step. Then try the **level sorter** (2 min) and, as
   `trainer.demo`, the **cluster meeting pack** (2 min).
5. **teacher.demo3 (3 min).** The chat opens on the learning step: tap "फिर से सुनें" (listen again) or "समझ गई, आगे" (got it, next), and type something else to see the reminder of the two buttons.
6. **arp.demo, trainer.demo, coach.demo, admin (15 min).** Compare what each role sees. Log out of the teacher
   logins first if you want to see the reset.
7. **Low connectivity (5 min).** In the browser's developer tools set the network to Offline: the last
   messages and the learn summary stay readable and a message you send waits in the outbox, then sends by
   itself when you go online. The menu has a lite mode (audio plays only on tap). The first request after the
   service slept is slow by design of the free plan; the page says the server is waking up.

## What is real, what is simulated, what is missing

- **Simulated children.** Ravi, Priya and Aman are not people and not a free-running chatbot: a deterministic
  rule engine decides what each child answers (their misconceptions and how they change), and the language
  model only phrases the line, checked by guards, with a template fallback.
- **Synthetic cohort.** The ARP and trainer pages are filled by 51 fictional "demo" teachers whose rehearsal
  scores come from running the real engine on scripted turns. They are labelled demo and are not real teacher
  data. Real use of the demo logins adds to, and the logout reset removes from, the three shared teachers only.
- **Voice.** Speech in and out is real only when the service has speech keys (Gemini or Sarvam); otherwise it
  runs on mock audio. Children's voices are synthetic.
- **WhatsApp.** The same conversation exists on WhatsApp, but only if Meta credentials were configured for
  this deployment; assume the web app is the channel under test.
- **Official documents.** Answers are grounded in these ingested sources only:
  NIPUN Bharat Guidelines (English, 332 pp), NCERT Vidya Pravesh (English, 56 pp) and NISHTHA FLN (English,
  618 pp) from their text layers, and
  the two **UP Samagra Shiksha Class 1 teacher guides in Hindi (Ganit, 112 pp; Bhasha, 156 pp)**, which were
  **read from page images by an AI OCR step** (their PDF text layers are unusable). The OCR was checked by eye
  on 10 random pages: about 0.2 % of words wrong (small spelling slips, and on two-column pages the reading
  order is sometimes mixed). 16 pages were skipped (covers, contents, a form, letter grids). Citations to these
  guides say the passage was machine-read. A human has not yet re-checked the OCR (`docs/ocr_samples/`).
- **Not in the sources.** The Class 1 maths
  guide covers weeks 9–25 only and has **no** two-digit subtraction with regrouping, so the demo move
  "हासिल वाला घटाव" is not backed by an official page; the system says "not in my documents" rather than
  invent one.
- **Not verified here.** Latency on the free plan (cold start excluded; per-stage latency on a laptop is in
  `docs/PERFORMANCE.md`), real Gemini/Sarvam speech quality on low-end phones, and the WhatsApp channel against
  live Meta accounts. No coach has approved a move card, there is no kappa figure against coaches, and no real
  teacher has used the system (`docs/QA_SHEET.md`).

Judge pack: `docs/JUDGE_QUICKSTART.md` (one screen), `docs/SAMPLE_INPUTS.md` (five inputs with real outputs),
`docs/QA_SHEET.md`, `docs/HOW_ARE_WE_DIFFERENT.md`, `docs/PERFORMANCE.md`.

More: `README.md` (product and architecture), `content/sources/README.md` (sources and OCR figures),
`docs/DEPLOY.md` (hosting and log lines), `docs/worked_example_ravi.md` (the Ravi example step by step).
