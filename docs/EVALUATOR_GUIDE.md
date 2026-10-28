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

## The seven logins

| Login | Password | Start here | What it shows |
|---|---|---|---|
| `teacher.demo1` | `<DEMO_PASSWORD>` | `/teacher` | **A new teacher.** Nothing done yet: the first message starts the welcome, the service consent question (with a "more" button; score sharing is asked later after first rehearsal) and the short onboarding, then the first move. Tap the buttons or type/speak. |
| `teacher.demo2` | `<DEMO_PASSWORD>` | `/teacher` | **Mid-rehearsal, one-on-one with Ravi.** Already inside a 1-1 scene of "हासिल वाला घटाव" (subtraction with regrouping, 43 − 27): the diagnosis is done and one question asked, so the header shows "रवि से 1-1 बात", the board (43 − 27), a progress cue ("अपना तरीका बता रहा है"), the turn counter (1/10) and an **end practice** button. Use the sample chips or type, e.g. "देखो, ये 4 बंडल और 3 खुली तीलियाँ हैं, 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो।" and then give a new problem ("अब 52 में से 17 करो"): the cue moves, and when Ravi gets the new problem right the scene ends. Finish the scene to get coach feedback (strength with your own words quoted, one change, an exact sentence) on the **one-on-one rubric**, and the retry. After the reflection step you are asked to **rate the training**: a 1–5 usefulness score (say or type it, or tap 1 / 3 / 5) and an optional one-line comment (voice or text, or *Skip*). |
| `teacher.demo3` | `<DEMO_PASSWORD>` | `/teacher` | **Three modules completed, on the learning step of the next weekly move** (reading matra words by blending letter sounds, `LIT_MATRA_BLENDING`). The chat already shows the learning-step message with its **two buttons**, labelled in Hindi: "समझ गई, आगे" (Got it, next: continues to the explain-back step) and "फिर से सुनें" (Listen again: repeats the step). Typing other text does not advance it; the reply reminds you of the two buttons. ☰ → **Modules** shows the three completed numeracy modules. This login has *not* agreed to share scores, so it never appears in the ARP digest or trainer counts. **Literacy group scene: 3 actions from the start:** (1) tap "समझ गई, आगे"; (2) send one sentence in your own words (the explain-back step); (3) tap the listen button ("सुनना चाहेंगी…" prompt, `btn_listen`). The group scene (Ravi, Priya, Aman; board word "मेला") then opens at turn 0/8; speak or type to the children, e.g. "प्रिया, बोर्ड पर क्या लिखा है? पढ़ो।", then say "बस" to end and get feedback (at least 3 teacher turns are needed for advice). |
| `arp.demo` | `<DEMO_PASSWORD>` | `/arp` | **Cluster resource person**, cluster KNP-C01: weekly digest of *consenting* teachers only, questions escalated from the chat (answer them here), classroom-observation form. |
| `trainer.demo` | `<DEMO_PASSWORD>` | `/trainer` | **DIET/SCERT trainer**, district Kanpur Nagar: module × batch table (completion, most-missed key point, rubric and ladder distributions). Also the **training ratings** card: average, count and latest comments from consenting teachers in the district (hidden below 10 ratings). Groups with fewer than 10 teachers are suppressed (batch KNP-B3 has 8 and shows the privacy notice); `/trainer/export.csv` follows the same rule. No teacher names appear. |
| `coach.demo` | `<DEMO_PASSWORD>` | `/review` | **Coach review console**: queue of AI scores and escalations that need a human look, per-item resolve, calibration labelling, move-card review. |
| `admin` | `<ADMIN_PASSWORD>` | `/admin` | **Admin dashboard**: latency, token use, guard results, scheduler jobs, WhatsApp templates, the **training ratings** card (all teachers, no suppression) and the demo controls (*Reset demo*, *fast-forward*). |

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
4. **teacher.demo3 (3 min).** The chat opens on the learning step: tap "फिर से सुनें" (listen again) or "समझ गई, आगे" (got it, next), and type something else to see the reminder of the two buttons.
5. **arp.demo, trainer.demo, coach.demo, admin (15 min).** Compare what each role sees. Log out of the teacher
   logins first if you want to see the reset.
6. **Low connectivity (5 min).** In the browser's developer tools set the network to Offline: the last
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
