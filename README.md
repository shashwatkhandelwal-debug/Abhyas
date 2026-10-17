# Abhyas (अभ्यास)

> **A voice-first Hindi practice partner for government primary-school teachers.** Fifteen minutes a week, on WhatsApp or the web: learn one teaching move, then rehearse it with three simulated children whose mistakes are computed by a rule engine, not invented by an AI.

**AI for Foundational Learning Hackathon 2026 · Challenge 3: Teacher Support and Training · Team Asymptotes** (Shashwat Khandelwal, Vedant Arora, Divyansh Agrawal)

<!-- TODO(human): add the 30-second rehearsal GIF (docs/deck_assets/rehearsal.gif) once recorded (T51). -->

---

## 1. Try it

**Hosted app:** TODO(human): hosted URL.
**Demo video (≤ 3 min):** TODO(human): YouTube link.
**Fallback walkthrough (screen capture):** TODO(human): link.

| Role | Username | Password | What to try |
|---|---|---|---|
| Teacher (new) | `teacher.demo1` | in the submission form | Onboarding, then the first weekly loop |
| Teacher (mid-week) | `teacher.demo2` | in the submission form | Jump straight into a rehearsal with three children |
| Teacher (experienced) | `teacher.demo3` | in the submission form | Progress page, evidence ladder, ask a question |
| ARP (cluster mentor) | `arp.demo` | in the submission form | Weekly digest, visit list, answer an escalated question |
| Trainer (DIET) | `trainer.demo` | in the submission form | Module × batch view, n < 10 suppression (batch KNP-B3) |
| FLN coach | `coach.demo` | in the submission form | Review queue, blind calibration, move approval |
| Admin | `admin` | in the submission form | Latency, guardrail stats, fast-forward timers, reset demo |

WhatsApp: TODO(human): number and join instructions. Meta test numbers only accept pre-registered recipients, so evaluators who want WhatsApp should send their number through the form; everyone else can use the web chat, which runs the same conversation engine.

All demo data is synthetic and labelled "डेमो". No real teacher or child data is in this repository.

---

## 2. Sample inputs

Tappable chips in the web chat (demo mode) and listed in `eval/samples/samples.yaml`. Each is a Hindi teacher utterance with a stated expected result.

| # | Step | What the teacher says | What should happen |
|---|---|---|---|
| 1 | Rehearse | "रवि, तुमने 43 में से 27 कैसे घटाया? मुझे एक-एक कदम बताओ।" | Ravi explains his own bug ("3 में से 7 नहीं घटता, तो 7 में से 3 घटाया… 24"). He never says 16. |
| 2 | Rehearse | "सब लोग देखो, ये 4 बंडल और 3 खुली तीलियाँ हैं…" | Concrete representation to the whole class; children move to *partial* understanding. |
| 3 | Rehearse | "Aman, sahi answer 16 hai, yaad rakho." (Hinglish) | Aman parrots "16…?" without understanding; on the next problem he relapses to his bug. |
| 4 | Explain back | A one-minute explanation of the move | Fidelity score with quoted evidence; the reply names the one missing point. |
| 5 | Ask | A multigrade-classroom question | Answer ≤ 80 words citing a guide chunk, or escalation to the ARP. |

Audio versions of the samples are rendered with `make samples` (needs a Sarvam key). Without audio, the chips send the text.

---

## 3. How it works

```
INPUT            CONTEXT                 REASONING (Claude)        GUARDRAILS               EVALUATION            OUTPUT
voice note  ──►  session state,      ──► intent_router        ──►  JSON schema validate ──► latency log       ──► TTS voice reply
text        ──►  move card, rubric,  ──► act_tagger           ──►  number/answer guard  ──► guard-failure log ──► text (always)
button      ──►  child states,       ──► child_voice (renders ──►  quote-exists guard   ──► coach-vs-expert   ──► buttons
                 retrieved guide         rule-engine output)       sources ⊆ retrieved      kappa harness      ──► ARP digest
                 chunks (RAG),       ──► coach                ──►  length / tone guard  ──► realism ratings   ──► trainer view
                 teacher history     ──► fidelity_checker     ──►  confidence → human   ──► evidence ladder
                                     ──► guide_answerer            review queue
                 DETERMINISTIC: rule engine computes every child answer (no LLM)
```

- **Weekly loop:** learn → explain back → hear a model teacher → rehearse by voice → rubric feedback (one strength, one change, exact words to try) → retry → try in class → reflect.
- **Voice in, voice out:** Hindi and Hinglish speech is transcribed, the turn is processed, and the reply is spoken in a distinct voice per child. Audio is discarded after transcription; text is always shown.
- **Rule-engine principle.** Each child has a hidden state (misconception, partial, can-explain) and a bug rule taken from research on children's errors. When the teacher asks Ravi to explain 43 − 27, the engine computes that Ravi subtracts the smaller digit from the larger and answers 24. Claude is only asked to say that result in a seven-year-old's voice, and a guard blocks any line whose numbers the engine did not allow. Telling a child the answer produces a parrot, and the bug returns on the next problem, as in a real class.
- **Grounded answers:** teacher questions are answered from retrieved state-guide chunks (BM25 by default) with citations; low confidence escalates to the ARP.
- **Worked example:** `docs/worked_example_ravi.md`.

### AI services used

| Service | Used for | Model / product | Key | Without a key |
|---|---|---|---|---|
| Anthropic Claude (fast) | intent routing, act tagging, child voice, question classification | `claude-haiku-5-5` | `ANTHROPIC_API_KEY` | Mock LLM with deterministic fixtures |
| Anthropic Claude (smart) | coach feedback, explain-back fidelity, guide answers, content generation | `claude-sonnet-5-5` | `ANTHROPIC_API_KEY` | Mock LLM, deterministic feedback bank |
| Sarvam AI | Hindi speech-to-text and text-to-speech | `saaras:v4`, `bulbul:v3` | `SARVAM_API_KEY` | Mock STT/TTS, text box in web chat |
| Meta WhatsApp Cloud API | WhatsApp channel | Graph API | `WHATSAPP_*` | Channel disabled; mocked Graph API in tests |
| Voyage AI (optional) | dense retrieval | `voyage-multilingual-2` | `VOYAGE_API_KEY` | BM25 only (default) |

Every external service has a mock selected by environment variable. With an empty `.env` the whole product runs on mocks. Outputs from mock mode are labelled as such in the evaluation reports.

---

## 4. Guardrails

- Every Claude output is validated against a JSON schema before use.
- Child lines: numbers must be in the engine's allowed set, forbidden answers are rejected, the answer must appear, no out-of-character terms, length-capped. One retry, then a deterministic template line.
- Coach feedback: every cited quote must exist in the teacher's transcript; no praise for telling the answer; length and tone (आप, never तुम) checked.
- Guide answers: sources must be a subset of retrieved chunks; low confidence goes to human review.
- Code: `backend/app/llm/guards.py`. Every guard result is recorded (`backend/app/llm/guard_stats.py`).
- Report: `eval/guards/REPORT.md` (`make eval-guards`) with live pass, retry and fallback rates plus an adversarial test corpus.

---

## 5. Low connectivity and low-cost devices

| Part | Needs network? | Degrades to |
|---|---|---|
| Learn summary, peer checklist, last 50 messages | No (cached PWA) | none needed |
| Sending a voice note or text | Queued offline, sent automatically when back | Outbox with retry |
| Rehearsal replies | Yes (server AI) | Text-first replies; lite mode = no audio download |
| Audio playback | On tap in lite mode | Text always shown |
| WhatsApp channel | WhatsApp's own offline queue | Text fallback on audio failure |

Pages are server-rendered HTML with vanilla JS and one stylesheet; the first-load budget is 150 KB (measured in T47). Voice notes are recorded at 16 kbps mono.
Data per weekly loop and latency: see `eval/latency/REPORT.md`. TODO(human): copy the measured p50/p95 and MB/KB figures here after the hosted run (28–30 Oct). The report currently states which runs used mock providers.

---

## 6. Run locally

Prerequisites: Docker, Python 3.11, ffmpeg.

```bash
cp .env.example .env          # leave API keys empty to run on mocks
make setup db-up db-migrate db-seed dev
# open http://localhost:8000
```

Tests and checks: `make test` (ruff, mypy --strict, pytest; mocks only). Dependency audit: `make audit`.

---

## 7. Repository map

```
backend/app/
  main.py            FastAPI app, middleware, routers, scheduler lifespan
  config.py          every tunable and threshold
  rule_engine/       personas, bug rules, state transitions (no LLM)
  llm/               Claude client, role prompts, schemas, guards, guard_stats
  speech/            STT / TTS adapters, audio utilities
  sessions/          weekly state machine, scene runner, move-path scoring
  retrieval/         BM25 search over guide chunks
  scoring/           rubric scoring, evidence ladder
  channels/ whatsapp/ web/   channel adapters, chat API, teacher PWA
  reports/           ARP digest, trainer aggregates (n ≥ 10)
  jobs/              scheduler and job handlers
  auth/ privacy/ db/ security, consent, purge, models and migrations
content/             move cards, personas, Hindi message catalog, validators
eval/                latency, kappa calibration, guards, realism, user-testing kit, samples
docs/                deploy guide, runbook, video script, deck outline, WhatsApp setup
spec/                build specification
```

Evaluation reports: `eval/latency/REPORT.md`, `eval/guards/REPORT.md`, `eval/calibration/` (kappa harness), `eval/user_testing/` (protocol and findings).

---

## 8. Privacy

DPDP-aligned by design. Audio is not stored: it is transcribed in memory and discarded. Individual scores reach an ARP only with the teacher's consent. Trainer views show groups of at least ten teachers and suppress smaller ones. Children are never scored or identified; the simulated children are fictional. A teacher can view and delete their data from the app. Phone numbers are stored as salted hashes with an encrypted copy for sending. No secrets or real user data are in git (a secret scanner runs in CI).

---

## 9. Limitations

- Four seed moves (three numeracy, one literacy) and three personas. Content has not yet been through a full FLN-coach review; unreviewed moves carry a "समीक्षा में" label.
- Hindi and Hinglish only. Speech quality depends on the speech provider and on network quality.
- The rule engine models a small, research-based set of common errors, not every classroom error.
- Coach scoring agreement with human coaches is measured only on the sample size stated in the calibration report.
- User-testing results are limited to the sessions recorded in `eval/user_testing/`.
- WhatsApp live use needs Meta approval and registered recipients. The in-memory rate limit and the CSP (which still allows inline scripts) are noted in `PROGRESS.md`.

## 10. Roadmap

Pilot (Dec–Feb): 30–100 teachers with one DIET, 16 moves, kappa ≥ 0.7 on 100 double-coded rehearsals, a Sankul mode for monthly meetings. Next: IVR for feature phones, Bhashini or state speech stacks, three more languages, integration with state teacher apps and the ARP visit cycle, opt-in class-audio coaching owned by the school, and a link to child-outcome evidence through assessment partners.

---

## Licence

MIT. © 2026 Team Asymptotes. Built for the AI for Foundational Learning Hackathon 2026.
