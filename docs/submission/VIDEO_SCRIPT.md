# Demo video script (3 minutes)

**Format:** screen recording of the hosted app with a voice-over, public link (YouTube unlisted or public). The
submission asks the video to cover: the **challenge addressed**, a **UI walkthrough**, **key features** and **ease-of-use
features**. The timings below add up to 3:00. Record in one take per segment, then cut.

**Before recording (checklist)**
- Hosted app at `<HOSTED URL>`: open `<HOSTED URL>/healthz` and wait for `"status": "ok"` (the free plan sleeps).
- Demo accounts are shared and reset on login and logout, so record when nobody else is testing. Use `teacher.demo2`
  for segments 2 to 4, `teacher.demo1` for segment 5, `trainer.demo` for segment 7. The password is `<DEMO_PASSWORD>`;
  do not show the `admin` password anywhere. Crop or blur the password field on the login page.
- Phone-width browser window (about 400 px wide) so the chat looks like it will on a phone, plus a second window at
  laptop width for the trainer page.
- A microphone that works; speak the Hindi lines naturally. Keep the speech provider keys set on the deployment so the
  reply audio is real (with mock audio the voice says so; use the typed chips instead and say they are typed).
- No real children, no classroom B-roll with identifiable children, no real teacher names. All data on screen is
  labelled demo. Team photo goes on the closing card (**needs a person**).

---

## Timeline

| Time | Segment | On screen (exact clicks) | Voice-over |
|---|---|---|---|
| 0:00-0:15 | **1. The challenge** | Title card: "Abhyas: practice for Class 1-3 teachers". Cut to the login page at `<HOSTED URL>` | "Teachers are trained in teaching moves but almost never get to practise them, and trainers see attendance, not what changed in class. This is Challenge 3, teacher support and training. Abhyas gives a teacher fifteen minutes a week of voice practice in Hindi." |
| 0:15-0:30 | **2. Login and language** | On the login page tap the **English** switch and back to **हिंदी**; tap the `teacher.demo2` fill-in button; log in | "It opens in Hindi, with an English switch. These demo accounts are shared and reset when you log out." |
| 0:30-1:05 | **3. A practice scene** | Chat opens on the one-on-one scene with Ravi (43 - 27). Hold the mic and say "रवि, तुमने 43 में से 27 कैसे घटाया? एक-एक कदम बताओ।" Wait for Ravi's reply (text, then audio). Then send "रवि, सही उत्तर 16 है, इसे याद कर लो।" and then "अब नया सवाल: 61 में से 28।" | "Ravi has a real misconception: he subtracts the smaller digit from the larger. He explains his mistake and says 24. If I just tell him the answer, he repeats it, and on the next problem he makes the same mistake again: 47. A fixed rule engine decides what he answers. The AI model only phrases the sentence, and a guard rejects any number the engine did not choose." |
| 1:05-1:35 | **4. Coach feedback** | Tap the end-practice button, confirm. Scroll the feedback message slowly: the line about the skill the teacher chose, the strength, the one thing to change, the exact sentence to say. Then the tip with its source chip; tap the chip so the passage opens | "The coach quotes the teacher's own words, names one thing to change and gives the exact sentence to say next time. A tip comes from the official documents, with the page. Every AI output is checked by code first; if a check fails twice, a fixed template is used." |
| 1:35-2:05 | **5. Her class, her skill, the handbook** | Log out, log in as `teacher.demo1`. Menu (three dots) > **मेरी कक्षा**; say "बच्चे हासिल वाले जोड़ में हासिल भूल जाते हैं और गिनती भी कमज़ोर है"; tap **हाँ**; when asked what she wants to get better at, say "बच्चे से पूछना कि उसने कैसे किया" (or the number 1) and confirm. Open **Modules** and point to "आपकी कक्षा के लिए चुना गया". Back in the chat tap one "हैंडबुक से पूछें" chip and show the cited answer | "She tells us where her class struggles and what she wants to get better at, from closed lists we wrote, so nothing is invented. Her module moves to the top, and the coach leads with her skill. Handbook questions are answered only from five official documents, with the source and the page." |
| 2:05-2:30 | **6. Ease of use on a weak connection** | Browser developer tools > Network > Slow 3G; menu > **lite mode**; then switch to Offline, type a message, show the waiting clock; go online and show it send itself. Optionally show the "server is waking up" page | "The page stays under 150 kilobytes. Lite mode plays audio only when tapped. Offline, a message waits in an outbox and sends by itself when the connection returns. Voice and AI answers need the connection, and the app says so." |
| 2:30-2:50 | **7. What the trainer sees** | Log in as `trainer.demo` (second window). Scroll to the module table: point to the suppressed batch and the notice; show the class-struggles and skills cards | "The ARP sees only teachers who agreed to share. The trainer sees counts, never names, and any group under ten is hidden." |
| 2:50-3:00 | **8. Close** | Closing card: team names, hosted link, repository link, team photo (**needs a person**) | "No real teacher has used it yet, and we say so; the roadmap is the first mentor sessions, a coach review, and a real-phone test. Abhyas: practice before the classroom." |

---

## Shot list (what to capture, in order)

1. Title card (static, 3 s).
2. Login page: language switch tapped twice; demo-account note visible ("Demo accounts are shared: pick one not in use;
   chats reset on login and logout").
3. Chat, `teacher.demo2`: header "रवि से 1-1 बात" and the board 43 - 27 visible; mic held; "recording" status;
   transcript appears; Ravi's reply.
4. Chat: the two follow-up messages and Ravi's repeated answer (16, then 47). Zoom on the numbers.
5. End-practice confirm dialog; the feedback header; the message with the skill lead line; the tip and source chip; the
   opened passage with its page.
6. `teacher.demo1`: menu > My class; the voice sentence; the confirm buttons; the saved message with sources; the skill
   question and answer.
7. Modules page: the "chosen for your class" line and the handbook chips.
8. Handbook chip tapped; answer with "From the FLN training package" and the source chip.
9. DevTools Network panel on Slow 3G with the chat loading; lite mode toggled; Offline banner; message with the clock;
   reconnect and the check mark.
10. Trainer page: module table with the suppressed row; the class-struggles card; the skills card.
11. Closing card.

## Voice-over notes

- Keep each sentence short; the segment lengths above include pauses for the reply audio.
- Say "simulated child" and "rule engine" at least once; say "no real teacher has used it yet".
- Do not claim a latency number or an accuracy number in the video: none has been measured on the hosted site.
- Subtitles: add English subtitles over the Hindi lines (the judges may not read Hindi).
- If the speech service is down while recording, use the typed sample chips and say "typed" in the voice-over; do not
  fake audio.

## After recording

1. Upload, set to public or unlisted, and put the link in `README.md` section 1 and in the submission form (**needs a person**).
2. Also record a 2 to 3 minute screen capture of the same flow as the fallback walkthrough.
