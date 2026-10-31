# Judge quickstart (one screen)

**Abhyas** is a voice-first practice partner for Class 1–3 teachers, in Hindi. The teacher rehearses a teaching
move with a simulated child. **A rule engine decides what the child answers; language models only phrase,
classify, coach and answer from cited documents.**

- **App:** `<HOSTED URL>` (placeholder, filled in the submission form) · **Health check:** `<HOSTED URL>/healthz`
- **Logins:** `teacher.demo1`, `teacher.demo2`, `teacher.demo3`, `arp.demo`, `trainer.demo`, `coach.demo` use
  `<DEMO_PASSWORD>`; `admin` uses `<ADMIN_PASSWORD>`. Both are in the submission form, not in the repository. With `DEMO_MODE` on (the default) the
  login page also shows the demo password and buttons that fill in the usernames (not the admin password).
- **Shared accounts:** the demo logins are shared by everyone who tests at the same time. The login page says so: **pick an account that is not in use; chats reset on login and logout.** If a chat looks as though someone else is in it, log out and pick another account (`teacher.demo1`, `teacher.demo2` and `teacher.demo3` are all offered on the login page).
- **Language:** Hindi by default; the **हिंदी / English** switch on the login page and in the chat menu (☰)
  turns the interface into English. The children and the coach always speak Hindi.
- **Sample inputs to paste or speak:** `docs/SAMPLE_INPUTS.md`. **Full walkthrough:** `docs/EVALUATOR_GUIDE.md`.

## The first 5 minutes

1. Open `<HOSTED URL>/healthz` and wait for `{"status": "ok", ...}`. The free hosting plan sleeps when idle, so
   the first request can take **about a minute**; the login page says "the server is waking up" instead of failing.
2. Log in as `teacher.demo2` (mid-rehearsal with Ravi, problem 43 − 27). Tap a sample chip or send input 2 from
   `docs/SAMPLE_INPUTS.md` ("रवि, सही उत्तर 16 है…"): Ravi repeats 16 without understanding. Then send
   "अब नया सवाल: 61 में से 28।": he gets it wrong again (47). Nothing in the model decided that.
3. Send input 4 (the bundles move) to see him get to the right answer with help. Tap **end practice** (or let the
   scene finish) to get the coach's feedback with your own words quoted.
4. Type the how-to question (input 5), or tap one of the four **हैंडबुक से पूछें** chips under the text box (on `teacher.demo1` and `teacher.demo3`; `teacher.demo2` starts inside a scene, so its chips are on the Modules page): the answer ends with a citation chip; tap it to read the source page.
5. **Try "My class" (about 2 minutes).** Log in as `teacher.demo1`, open the menu (☰) and tap **मेरी कक्षा**
   (or type it in the chat). Say or type where your class struggles, e.g. input 6 in `docs/SAMPLE_INPUTS.md`
   ("बच्चे हासिल वाले जोड़ में हासिल भूल जाते हैं और गिनती भी कमज़ोर है"), or tick up to three chips. Confirm what it
   understood. You get, for each struggle, a short tip with the page it comes from, and either the practice move
   for it or the honest line "there is no practice case for this yet". Then open **Modules**: the move for your
   struggle is first and says "आपकी कक्षा के लिए चुना गया…". In a one-on-one practice the child who makes your
   class's mistake is starred, and the coach's feedback ends with a line linking it to your class. `teacher.demo3`
   already has a class choice (matra words, addition with carry) so you can see the result without typing.
   Right after you confirm, Abhyas asks **what you want to get better at** (input 9 in `docs/SAMPLE_INPUTS.md`: say
   "बच्चों से यह पूछना कि उन्होंने कैसे किया", or give a number from the list); at most two skills are kept, and in the next
   one-on-one practice the coach's feedback starts with your skill. `teacher.demo3` has one seeded (`asks_to_explain`).
6. **Log out.** The three shared teacher logins reset to their starting state on logout, including "My class".

## What to try per role

| Login | Page | Try |
|---|---|---|
| `teacher.demo1` | `/teacher` | New teacher: welcome, service consent, onboarding (score sharing is asked after first rehearsal feedback), first move, a voice note. No class choice yet: set one with **मेरी कक्षा** (step 5). |
| `teacher.demo2` | `/teacher` | The Ravi scene above; after feedback, retry and pick 1-1 or three children; say a diagnosis sentence (input 1). |
| `teacher.demo3` | `/teacher` | Opens on a learning step with two buttons ("समझ गई, आगे" / "फिर से सुनें"); typing gets a reminder of them. Has not agreed to share scores. Has a seeded class choice (matra words, addition with carry): the learning step says why it was chosen, and **Modules** / **मेरी कक्षा** show it. |
| `arp.demo` | `/arp` | Weekly digest of consenting teachers only; escalated questions to answer; observation form. |
| `trainer.demo` | `/trainer` | Module × batch table; groups under 10 teachers are suppressed (batch KNP-B3 has 8); CSV export. A **common class struggles** card counts what consenting teachers chose in "My class" (nothing is shown below 10 teachers). |
| `coach.demo` | `/review` | Queue of AI scores needing a human look; calibration labelling; move-card review. |
| `admin` | `/admin` | Latency, tokens, guard results, jobs, ratings; **Reset demo** (restores demo1–3 exactly as logout does). |

## What is simulated and what is real

- **Real:** the rule engine, the guards and fallbacks, the Claude calls (Haiku 5.5 for act tagging and the
  child's words, Sonnet 5.5 for the coach, the explain-back check and answers to questions), retrieval and
  citations over five ingested documents (NIPUN Bharat, NCERT Vidya Pravesh, NISHTHA FLN, two Hindi UP guides), consent and suppression rules, the outbox/PWA behaviour, and "My class": a closed list of 14 class struggles (`content/class_struggles.yaml`) mapped to what those documents say (`docs/FLN_TRAINING_MAP.md`), understood by a Haiku classifier that can only pick from the list, with a keyword fallback.
- **Practice cases:** 7 of the 14 listed struggles have a practice scene (served by 4 move cards: place value, addition with carry, subtraction with regrouping, matra blending); for the other 7 "My class" gives the handbook tip with its page and says there is no practice case yet. The class list was built and labelled by us from the documents, not by teachers.
- **Simulated:** the children (they are not people); the ARP and trainer data (51 fictional teachers whose
  rehearsal scores came from running the real engine on scripted turns, labelled demo); speech is mock audio
  unless the deployment has Gemini/Sarvam keys; WhatsApp works only if Meta credentials were configured.
- **Machine-read sources:** the two Hindi UP guides were read from page images by an AI OCR step; citations say so.

## How to test low connectivity

1. Browser developer tools → Network → **Offline** (or airplane mode on a phone). The banner says you are offline;
   history and the offline checklist stay readable; a message you send waits in the outbox and sends by itself
   when you go online. If sending gives up, a red **!** appears: tap it to resend.
2. Throttle to **Slow 3G**: the page stays under 150 KB; the menu has **lite mode** (audio only on tap).
3. Cold start: the first load of the login page after the server slept shows a "waking up, about a minute" page and then
   opens by itself (a browser that has never opened the app gets the hosting service's own waiting page instead). After that the app never shows that notice again: it retries quietly (about 30 s) and, only if the
   server still does not answer, shows a plain "server not reachable, reload" page.

## If the app is slow

Wait about a minute after the first request, then reload. If a reply takes longer than a minute the chat says so;
tap the red **!** if one appears, or send the message again. If you see an error page, it says whether to retry;
`<HOSTED URL>/healthz` tells you whether the server is up.
