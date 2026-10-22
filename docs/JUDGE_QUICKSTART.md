# Judge quickstart (one screen)

**Abhyas** is a voice-first practice partner for Class 1–3 teachers, in Hindi. The teacher rehearses a teaching
move with a simulated child. **A rule engine decides what the child answers; language models only phrase,
classify, coach and answer from cited documents.**

- **App:** `<HOSTED URL>` (placeholder, filled in the submission form) · **Health check:** `<HOSTED URL>/healthz`
- **Logins:** `teacher.demo1`, `teacher.demo2`, `teacher.demo3`, `arp.demo`, `trainer.demo`, `coach.demo` use
  `<DEMO_PASSWORD>`; `admin` uses `<ADMIN_PASSWORD>`. Both are in the submission form, not in the repository.
- **Language:** Hindi by default; the **हिंदी / English** switch on the login page and in the chat menu (☰)
  turns the interface into English. The children and the coach always speak Hindi.
- **Sample inputs to paste or speak:** `docs/SAMPLE_INPUTS.md`. **Full walkthrough:** `docs/EVALUATOR_GUIDE.md`.

## The first 5 minutes

1. Open `<HOSTED URL>/healthz` and wait for `{"status": "ok", ...}`. The free hosting plan sleeps when idle, so
   the first request can take **about a minute**; the pages say "the server is waking up" instead of failing.
2. Log in as `teacher.demo2` (mid-rehearsal with Ravi, problem 43 − 27). Tap a sample chip or send input 2 from
   `docs/SAMPLE_INPUTS.md` ("रवि, सही उत्तर 16 है…"): Ravi repeats 16 without understanding. Then send
   "अब नया सवाल: 61 में से 28।": he gets it wrong again (47). Nothing in the model decided that.
3. Send input 4 (the bundles move) to see him get to the right answer with help. Tap **end practice** (or let the
   scene finish) to get the coach's feedback with your own words quoted.
4. Type the how-to question (input 5): the answer ends with a citation chip; tap it to read the source page.
5. **Log out.** The three shared teacher logins reset to their starting state on logout.

## What to try per role

| Login | Page | Try |
|---|---|---|
| `teacher.demo1` | `/teacher` | New teacher: welcome, consent (service / score sharing), onboarding, first move, a voice note. |
| `teacher.demo2` | `/teacher` | The Ravi scene above; after feedback, retry and pick 1-1 or three children; say a diagnosis sentence (input 1). |
| `teacher.demo3` | `/teacher` | Learning step of the next module; only its two buttons advance it. Has not agreed to share scores. |
| `arp.demo` | `/arp` | Weekly digest of consenting teachers only; escalated questions to answer; observation form. |
| `trainer.demo` | `/trainer` | Module × batch table; groups under 10 teachers are suppressed (batch KNP-B3 has 8); CSV export. |
| `coach.demo` | `/review` | Queue of AI scores needing a human look; calibration labelling; move-card review. |
| `admin` | `/admin` | Latency, tokens, guard results, jobs, ratings; **Reset demo** (restores demo1–3 exactly as logout does). |

## What is simulated and what is real

- **Real:** the rule engine, the guards and fallbacks, the Claude calls (Haiku 5.5 for act tagging and the
  child's words, Sonnet 5.5 for the coach, the explain-back check and answers to questions), retrieval and
  citations over five ingested documents (NIPUN Bharat, NCERT Vidya Pravesh, NISHTHA FLN, two Hindi UP guides), consent and suppression rules, the outbox/PWA behaviour.
- **Simulated:** the children (they are not people); the ARP and trainer data (51 fictional teachers whose
  rehearsal scores came from running the real engine on scripted turns, labelled demo); speech is mock audio
  unless the deployment has Gemini/Sarvam keys; WhatsApp works only if Meta credentials were configured.
- **Machine-read sources:** the two Hindi UP guides were read from page images by an AI OCR step; citations say so.

## How to test low connectivity

1. Browser developer tools → Network → **Offline** (or airplane mode on a phone). The banner says you are offline;
   history and the offline checklist stay readable; a message you send waits in the outbox and sends by itself
   when you go online. If sending gives up, a red **!** appears: tap it to resend.
2. Throttle to **Slow 3G**: the page stays under 150 KB; the menu has **lite mode** (audio only on tap).
3. Cold start: a sleeping server shows the "waking up, about a minute" page and then opens by itself.

## If the app is slow

Wait about a minute after the first request, then reload. If a reply takes longer than a minute the chat says so;
tap the red **!** if one appears, or send the message again. If you see an error page, it says whether to retry;
`<HOSTED URL>/healthz` tells you whether the server is up.
