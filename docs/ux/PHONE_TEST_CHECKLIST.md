# Phone test checklist (for a human, on a real Android phone)

Nothing in the build run could open a phone browser. Everything below is what a person should tick on the **hosted
site**, in Chrome on a phone, once the build is deployed by hand. Record failures with a screenshot and the time.
Mark an item "not testable on web" only where it says so. Passwords are in the submission form.

Before you start: open the hosted site address followed by `/healthz` and wait for `"status": "ok"` (a cold start takes about a minute on
Render's free plan). Use one phone per judge account; two people on one login reset each other.

## A. Fresh logins

| # | Login | Steps | Expected |
|---|---|---|---|
| A1 | `teacher.demo1` | Log in. | The welcome starts; the **input bar is visible and not under the keyboard**; the consent question shows its buttons ("हाँ" / "अभी नहीं" style, and "more"), all tappable without scrolling. |
| A2 | `teacher.demo1` | Choose **"he" (पुरुष)** at the form-of-address question, finish onboarding. | Model-teacher label and hints say **"सर"** where the she form says "दीदी/मैडम"; no feminine-only wording about you. |
| A3 | `teacher.demo2` | Log in. | The chat opens inside the one-on-one scene with Ravi; scene bar shows the board (43 − 27) and a label beside Ravi's name ("अटका हुआ"). |
| A4 | `teacher.demo3` | Log in. | The learning step is shown with two buttons; ☰ → Modules shows three completed modules. |
| A5 | `trainer.demo` | Log in at `/login`. | `/trainer` loads; the **संकुल बैठक पैक** card shows two struggles with "N शिक्षक", a "demo data" label, and a link to the printable agenda. |
| A6 | `arp.demo` | Log in. | `/arp` loads; the pack card shows the **privacy message** (this cluster has 7 consenting teachers, fewer than 10): this is correct. |

## B. Log-out and log-in, five times

For `teacher.demo2`: log out, log in, repeat five times.
- Each time the chat starts again inside the Ravi scene at turn 1, with no earlier messages from the last round.
- No error page and no "server waking" page after the first load.
- Typing in the input bar still works after every round.

## C. Layout on the phone

- [ ] The **input bar and the mic and send buttons are fully visible** with the keyboard closed and open (portrait).
- [ ] The **consent buttons** (A1) are visible and tappable.
- [ ] The **demo shortcuts tray is collapsed** on first load and opens when tapped.
- [ ] The scene bar does not hide the chat: with three children, labels may wrap to a second line but the chat area stays readable.
- [ ] Dark mode and light mode both readable (Android: Settings, Display).
- [ ] First load feels light on mobile data (the page is under 150 KB).

## D. After-class check-in

On `teacher.demo2` (inside the scene):
1. Open the tray and tap **"कक्षा के बाद: कैसा रहा?"**. Expected: a topic question with up to 5 buttons.
2. Tap "हासिल वाला घटाव", then "ज़्यादातर अटके", then "हासिल वाला घटाव". Expected: a tip with source chips ending "(राष्ट्रीय)" and the buttons **"वापस अभ्यास पर"** and "हैंडबुक से पूछें".
3. Tap "वापस अभ्यास पर". Expected: back with Ravi at the same turn and board.

On `teacher.demo3` (no scene): chip, "मात्रा वाले शब्द", "कुछ बच्चे अटके", "मात्रा छूट जाना". Expected: the last screen offers **"रवि के साथ अभ्यास"**; tapping it opens the practice **without the learn step** (you are asked to pick a child).

- [ ] **Mapped-only struggle:** on `teacher.demo3` choose "गणित के अन्य विषय", "कुछ बच्चे अटके", "गिनती". Expected: a tip with citations and the line that **there is no practice case yet**, with only "हैंडबुक से पूछें" (no practice button).

## E. Level sorter

On `teacher.demo3`: tap **"कक्षा को स्तर के हिसाब से समूहों में बाँटें"**, "पढ़ना", then 6-10, 11-20, 1-5, 0.
Expected: three groups; "सबसे पहले समूह 1 के साथ बैठें"; one 10-minute activity per group with source chips ending "(राज्य: उ.प्र.)"; a line about classes 1 and 2 sharing a room. Repeat with "गणित": no multigrade line. Try all four at 0: a message says no groups could be made and offers to start again. No child name is asked anywhere.

## F. Practice and feedback

On `teacher.demo2`:
- [ ] Send "रवि, तुमने यह कैसे किया? एक-एक कदम बताओ।", then a bundles-and-sticks line, then a new problem. The label beside Ravi changes ("अटका हुआ", "समझ रहा है", and "फिर अटका" if he slips).
- [ ] Say "बस". The coach bubble shows your own words in a **quote badge** and, below the advice, "बच्चों से बात करने का तरीका" with one strength and one next step.
- [ ] Tap a source chip: the excerpt opens.

## G. Cluster pack

`trainer.demo`: open "छापने लायक एजेंडा खोलें". Expected: one page, four timed rows, no buttons or scripts, no teacher names; the browser's print preview fits one page. `arp.demo`: the same link shows the privacy message, no agenda.

## H. Low connectivity

Turn on airplane mode in the chat: the offline banner appears, a message you send waits and goes out when you reconnect. Lite mode (☰) plays audio only on tap.

## I. Phone screen layout (real Android phone, Chrome)

Do these on a real phone, not desktop emulation, with Chrome's address bar showing (do not scroll the page first):
- [ ] On every screen (start, consent, name, learn, check-in module, check-in outcome, level sorter, a scene) the text box, "सुझाव", mic and send buttons are all on screen, and scrolling the message list never hides them.
- [ ] The page itself never scrolls; only the message list does.
- [ ] Quick-reply buttons sit in one row just above the text box. With more buttons than fit, the row scrolls sideways and the first button is visible.
- [ ] Tap the text box: the keyboard opens, the text box stays just above it, and the message list is still at least a few lines tall. Close the keyboard: the layout returns.
- [ ] Tap "सुझाव": one sheet opens above the text box (at most about half the screen) with handbook questions open and sample lines and the demo shortcuts collapsed. The text box stays visible below it. The close button and tapping outside the sheet both close it.
- [ ] The demo shortcuts tray exists only inside this sheet, and sample lines and handbook questions too (no separate strips above the text box).
- [ ] Five cycles of log out and log in: the sheet and every section inside it start closed (handbook questions open) each time.
- [ ] Dark and light themes both show readable text and all buttons at least thumb size.

## J. Follow-up, visit checklist, reported vs observed, adaptive path (V3)

Needs the hosted site seeded with this code (`SEED_ON_BOOT=true` once, or the seed command). All of it is demo data.

| # | Taps | Expected |
|---|---|---|
| J1 | Log in as `teacher.demo2`, open the chat. | At the end of the thread a message "कल का अभ्यास कैसा रहा? ..." with 3 buttons: "काम किया", "अब भी अटके हैं", "आज़मा नहीं सके". Header, scene bar and input stay fully on screen. |
| J2 | Tap "काम किया". Tap it again. | First tap: one short acknowledgement, no praise words. Second tap: "यह जवाब दर्ज हो चुका है।" and nothing else. |
| J3 | Log out, log in again, tap "अब भी अटके हैं". | A different source chip than the check-in tip (tap it: the passage opens), then "रवि के साथ अभ्यास" and "हैंडबुक से पूछें". |
| J4 | Log out, log in, tap "आज़मा नहीं सके", then "कई कक्षाएँ साथ". | Four reason buttons (all fit on screen, titles not cut). Then a line about "स्तर से समूह बनाएँ" with that button. Nothing shaming. |
| J5 | Log in as `arp.demo`, open `/arp`, scroll to **कक्षा-भ्रमण सूची**. Tap one teacher, tick two talk moves, pick one next step, save. | A closed form with no text box. After saving, the page reloads with "कक्षा-भ्रमण दर्ज हो गया।". Tap targets are at least finger size at 360 px. |
| J6 | Log in as `trainer.demo`, scroll to **शिक्षकों ने बताया बनाम भ्रमण में दिखा**. | Two rows with "बताया: काम किया ..., अब भी अटके ..., आज़मा नहीं सके ..." and, for the first, "भ्रमण में अभ्यास दिखा: 12 बार"; the second row says the visit count is hidden. The caption says these are not learning outcomes. A "डेमो डेटा" label is visible. |
| J7 | Log in as `teacher.demo3`, finish the week to the week-done message. | One line "क्यों अभी यह: ..." inside the week-done message (no new strip). After the "next" tap, the same line leads the learn message. |
| J8 | Switch the interface to English on each of the above. | The same screens in English, no Hindi left in buttons, button titles not cut. |

## Not testable on web

- WhatsApp reply buttons (3 max) and the interactive list (more than 3 options); the check-in start from "After class" on the week-done message.
- Real voice quality (needs speech keys on the deployment) and any real Claude phrasing.
- Meta delivery, templates and the 24-hour window.
