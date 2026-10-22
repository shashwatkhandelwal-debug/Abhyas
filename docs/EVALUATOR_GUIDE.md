# Evaluator guide (about one hour)

Abhyas is a voice-first practice partner for primary (Class 1–3) teachers, in Hindi. A teacher practises a
teaching move with three simulated children (Ravi, Priya, Aman) whose answers come from a rule engine, never
from the language model, and gets coach feedback on their own words.

- **Link:** `<HOSTED URL>` (Render free plan: if it has been idle, the first page takes **about a minute** to
  wake; open `<HOSTED URL>/healthz` first and wait for `"status": "ok"`).
- **Passwords:** `<DEMO_PASSWORD>` for the six demo logins and `<ADMIN_PASSWORD>` for `admin`. They are in the
  submission form, not in the repository. With `DEMO_MODE` on, the login page also shows the demo password.
- **Language:** the interface is Hindi by default. Use the **हिंदी / English** switch on the login page or in
  the chat menu (☰) to see the whole interface in English; the choice is remembered. The simulated
  children and the coach speak Hindi in both.
- **Resetting:** the three shared teacher logins are **reset to their starting state when you log out**
  (chat history, step in the weekly loop, scores and your answers are removed; the PWA also clears its local
  message cache). Use **Log out** between experiments. Other judges share these logins, so do not rely on
  anything surviving a logout.

## The seven logins

| Login | Password | Start here | What it shows |
|---|---|---|---|
| `teacher.demo1` | `<DEMO_PASSWORD>` | `/teacher` | **A new teacher.** Nothing done yet: the first message starts the welcome, the consent question (service use and score sharing, with a "more" button) and the short onboarding, then the first move. Tap the buttons or type/speak. |
| `teacher.demo2` | `<DEMO_PASSWORD>` | `/teacher` | **Mid-rehearsal.** Already in the REHEARSE step of "हासिल वाला घटाव" (subtraction with regrouping, 43 − 27). Use the three sample chips or type, e.g. "रवि, तुमने 43 में से 27 कैसे घटाया?": Ravi explains his own mistake and says 24, never 16. Finish the scene to get coach feedback (strength, one change, your exact words quoted) and the retry. |
| `teacher.demo3` | `<DEMO_PASSWORD>` | `/teacher` | **On the learning step of the next move**, after three completed moves. Only its **two buttons work** here ("समझ गई, आगे" / "Got it, next" to continue and "फिर से सुनें" / "Listen again" to replay); other typed text does not advance this step and gets a "did not understand" reply. This login has *not* agreed to share scores, so it never appears in the ARP digest or trainer counts. |
| `arp.demo` | `<DEMO_PASSWORD>` | `/arp` | **Cluster resource person**, cluster KNP-C01: weekly digest of *consenting* teachers only, questions escalated from the chat (answer them here), classroom-observation form. |
| `trainer.demo` | `<DEMO_PASSWORD>` | `/trainer` | **DIET/SCERT trainer**, district Kanpur Nagar: module × batch table (completion, most-missed key point, rubric and ladder distributions). Groups with fewer than 10 teachers are suppressed (batch KNP-B3 has 8 and shows the privacy notice); `/trainer/export.csv` follows the same rule. No teacher names appear. |
| `coach.demo` | `<DEMO_PASSWORD>` | `/review` | **Coach review console**: queue of AI scores and escalations that need a human look, per-item resolve, calibration labelling, move-card review. |
| `admin` | `<ADMIN_PASSWORD>` | `/admin` | **Admin dashboard**: latency, token use, guard results, scheduler jobs, WhatsApp templates and the demo controls (*Reset demo*, *fast-forward*). |

## A suggested hour

1. **teacher.demo2 (10 min).** Run the rehearsal with the sample chips (including the Hinglish "tell the
   answer" chip: Aman repeats the answer without understanding, which is the point). Notice that the same
   input always gets the same child behaviour. Finish, read the feedback, tap retry.
2. **teacher.demo1 (10 min).** Go through welcome and consent, then the learn step and explain-back. Try a
   voice note (the mic button: tap to start, tap again to send, or hold). If a provider key is missing the
   voice may be a mock; the admin dashboard shows the configured providers.
3. **Ask a question (5 min).** In `teacher.demo1` or `teacher.demo2` type a how-to question, for example "उल्टी गिनती करके
   घटाव कैसे सिखाएँ?" or "कविता पोस्टर पर कार्य कैसे करवाएँ?". The answer comes only from the ingested
   official documents and ends with a **citation chip** ("स्रोत: …, पृष्ठ N"). **Tap the chip** to read the
   excerpt it came from, with its PDF page. An off-topic question ("आज का क्रिकेट मैच कौन जीता?") is
   declined instead of answered.
4. **teacher.demo3 (3 min).** Try the learning step with its two buttons (and type something else to see that it does not advance).
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
  NIPUN Bharat Guidelines (English, 332 pp) and NCERT Vidya Pravesh (English, 56 pp) from their text layers, and
  the two **UP Samagra Shiksha Class 1 teacher guides in Hindi (Ganit, 112 pp; Bhasha, 156 pp)**, which were
  **read from page images by an AI OCR step** (their PDF text layers are unusable). The OCR was checked by eye
  on 10 random pages: about 0.2 % of words wrong (small spelling slips, and on two-column pages the reading
  order is sometimes mixed). 16 pages were skipped (covers, contents, a form, letter grids). Citations to these
  guides say the passage was machine-read. A human has not yet re-checked the OCR (`docs/ocr_samples/`).
- **Not in the sources.** The NISHTHA FLN package was not supplied and is not ingested. The Class 1 maths
  guide covers weeks 9–25 only and has **no** two-digit subtraction with regrouping, so the demo move
  "हासिल वाला घटाव" is not backed by an official page; the system says "not in my documents" rather than
  invent one.
- **Not verified here.** Latency on the free plan (cold start excluded), real Gemini/Sarvam speech quality on
  low-end phones, and the WhatsApp channel against live Meta accounts.

More: `README.md` (product and architecture), `content/sources/README.md` (sources and OCR figures),
`docs/DEPLOY.md` (hosting and log lines), `docs/worked_example_ravi.md` (the Ravi example step by step).
