# Abhyas (अभ्यास)

> **A voice-first Hindi practice partner for government primary-school teachers.** Fifteen minutes a week, on WhatsApp or the web: learn one teaching move, then rehearse it one-on-one with a simulated child (or with three) whose mistakes are computed by a rule engine, not invented by an AI.

**AI for Foundational Learning Hackathon 2026 · Challenge 3: Teacher Support and Training · Team Asymptotes** (Shashwat Khandelwal, Vedant Arora, Divyansh Agrawal)

---

## 1. Try it

**Hosted app:** TODO(human): hosted URL (set after the Render deploy).  
**Demo video (≤ 3 min):** TODO(human): YouTube link (recorded by the team).  
**Fallback walkthrough (screen capture):** TODO(human): link (recorded by the team).  
**Team photo:** TODO(human): add to `docs/deck_assets/` (a person must supply it).  

**For judges:** `docs/JUDGE_QUICKSTART.md` (one screen), `docs/SAMPLE_INPUTS.md` (five inputs with the real outputs), `docs/EVALUATOR_GUIDE.md` (the hour in detail), `docs/QA_SHEET.md` (hard questions with honest answers), `docs/HOW_ARE_WE_DIFFERENT.md`, `docs/PERFORMANCE.md` (measured numbers).  

| Role | Username | Password | What to try |
|---|---|---|---|
| Teacher (new) | `teacher.demo1` | in the submission form | Onboarding, then the first weekly loop |
| Teacher (mid-week) | `teacher.demo2` | in the submission form | Already one-on-one with Ravi (43 − 27): continue the scene, get coach feedback, retry, diagnose a child |
| Teacher (experienced) | `teacher.demo3` | in the submission form | Learning step of the next module (three modules done), progress page, ask a question |
| ARP (cluster mentor) | `arp.demo` | in the submission form | Weekly digest, visit list, answer an escalated question |
| Trainer (DIET) | `trainer.demo` | in the submission form | Module × batch view, $n < 10$ suppression (batch KNP-B3) |
| FLN coach | `coach.demo` | in the submission form | Review queue, calibration labelling, move-card review (the four cards are still `in_review`) |
| Admin | `admin` | in the submission form | Latency, guardrail stats, fast-forward timers, reset demo |

Demo accounts are shared by everyone testing at the same time: the login page says "pick one not in use; chats reset on login and logout". The three shared teacher logins are reset to their starting state when you log out (the admin *Reset demo* button does the same). The free hosting plan sleeps when idle: the first request can take about a minute, and the pages say so.

WhatsApp: TODO(human): number and join instructions (needs the team's Meta test number). Meta test numbers only accept pre-registered recipients, so evaluators who want WhatsApp should send their phone number through the submission form; everyone else can use the web chat, which runs the identical conversation engine and audio pipeline.

All demo data in the UI is synthetic and labelled "डेमो". No real teacher or child personal data is in this repository.

---

## 2. Sample inputs

Tappable chips in the web chat (demo mode, listed in `eval/samples/samples.yaml`). Five ready-to-paste inputs
with the **actual outputs of the engine** (diagnosis, "tell the answer", an out-of-range problem, a good move,
a how-to question) are in `docs/SAMPLE_INPUTS.md`. The chips:

| # | Step | What the teacher says | What should happen |
|---|---|---|---|
| 1 | Rehearse | "रवि, तुमने 43 में से 27 कैसे घटाया? मुझे एक-एक कदम बताओ।" | Ravi explains his own bug (7 − 3 = 4, 4 − 2 = 2) and answers 24. He never says 16. |
| 2 | Diagnose | "इसने 3 में से 7 नहीं घटा पाया, तो उल्टा करके 7 में से 3 घटा दिया।" | The app compares the sentence with the child's real mistake (correct / partly / wrong, fixed keyword rules) and then reveals it. |
| 3 | Rehearse | "Sahi answer 16 hai, yaad rakho." (Hinglish) | The child parrots "16" without understanding; on the next problem the bug returns. |
| 4 | Explain back | A one-minute explanation of the move | Fidelity score with quoted evidence; the reply names the one missing key point. |
| 5 | Ask | A multigrade-classroom question | Answer citing a guide excerpt (source and page), or "not in my documents" / escalation to the ARP. |

Audio versions of the chips can be rendered with `make samples` (requires `SARVAM_API_KEY`); none are committed yet,
so the chips send text.

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

- **One-on-one first:** the main rehearsal is one teacher with one child (Ravi, Priya or Aman, each with a different hidden mistake): the teacher can first say what they think the mistake is (the diagnosis verdict is decided by fixed keyword rules), then work with the child, then get feedback on a one-on-one rubric. A three-children scene is also available. Modules (`/teacher/modules`) group learn → diagnose → practise → check for the three numeracy moves.
- **My class (optional, 2 minutes):** the teacher says where her class struggles (voice, text or a chip, `/teacher/class` or the chat command "मेरी कक्षा"); it is matched to a closed list of 14 class struggles tied to cited pages of the FLN training (`content/class_struggles.yaml`, `docs/FLN_TRAINING_MAP.md`). It reorders her path, labels module cards "chosen because…", stars the matching child in the scene and asks "did it help your class?" afterwards. Children's answers still come only from the rule engine.
- **Weekly loop:** `LEARN` → `EXPLAIN_BACK` → `MODEL` → `REHEARSE` → `FEEDBACK` → `RETRY` → `TRY_IN_CLASS` → `REFLECT` → `DONE`.
- **Voice in, voice out:** Hindi and Hinglish speech is transcribed via STT, the turn is processed, and the reply is synthesized in a distinct voice per child. Audio is discarded after transcription; text is always rendered.
- **Rule-engine principle:** Each simulated child has a hidden cognitive state (`misconception`, `partial`, `can_explain`) and a deterministic bug rule taken from research on primary numeracy errors. When the teacher asks Ravi to explain $43 - 27$, the deterministic rule engine computes that Ravi subtracts the smaller digit from the larger ($7 - 3 = 4$, $4 - 2 = 2$) and answers $24$. Claude is only asked to voice that exact result in a seven-year-old's speech register; an output guard rejects any generation whose numbers the engine did not allow. Telling a child the answer produces parrot behaviour, and the bug returns on the subsequent problem.
- **Grounded answers:** Teacher questions are answered only from excerpts of the official documents we have ingested (BM25 over 1,157 chunks from five documents; see section 8). Each answer carries `स्रोत: <document>, पृष्ठ N`; on the web the citation is a chip that opens the excerpt. If nothing clears the retrieval gate (`RETRIEVAL_MIN_SCORE` and at least two shared query terms), or confidence is low (< 0.60), or a guard fails, the bot says it did not find the answer in its documents and escalates to the ARP instead of guessing.
- **Hindi by default, English on request:** the UI text and system messages switch to English from the chat menu or the login page (kept per user). Children's lines and coach feedback stay Hindi; a *Translate* control under child / coach / guide bubbles shows an on-demand English translation (cached per message; the fast Claude model, guarded so numbers and names are kept).
- **Worked example:** See `docs/worked_example_ravi.md`.

### AI services used

| Service | Used for | Model / product | Key | Without a key |
|---|---|---|---|---|
| Anthropic Claude (fast) | intent routing, act tagging, child voice, question classification, diagnosis classification (only for unclear text), class-struggle classification ("My class": picks only ids from a closed list of 14, keyword fallback), module check, source-based coach suggestion, on-demand English translation; offline: Hindi glosses for source chunks and OCR of two Hindi guides | `claude-haiku-5-5` | `ANTHROPIC_API_KEY` | Mock LLM with deterministic fixtures (translation shows a demo placeholder) |
| Anthropic Claude (smart) | coach feedback, explain-back fidelity, guide answers, content generation | `claude-sonnet-5-5` | `ANTHROPIC_API_KEY` | Mock LLM, deterministic feedback bank |
| Sarvam AI | Hindi speech-to-text and text-to-speech | `saaras:v4`, `bulbul:v3` | `SARVAM_API_KEY` | Mock STT/TTS, text box in web chat |
| Meta WhatsApp Cloud API | WhatsApp channel | Graph API | `WHATSAPP_*` | Channel disabled; mocked Graph API in tests |
| Voyage AI (optional, not used) | dense retrieval | `voyage-multilingual-2` | `VOYAGE_API_KEY` | BM25 sparse search (the only retrieval in use) |

Every external service has a mock selected by environment variable. With an empty `.env` the entire product runs locally on mocks (`make dev`).

---

## 4. Guardrails

- Every Claude response is validated against a strict Pydantic JSON schema before use.
- **Child utterances:** All numbers must belong to the rule engine's permitted set, forbidden answers are blocked, the target error answer must appear, out-of-character academic terms are rejected, and word counts are strictly capped. One automated retry, followed by a deterministic catalog template fallback.
- **Coach feedback:** Every quoted teacher phrase must exist in the actual conversation transcript (verified by fuzzy substring matching); praise for merely telling the answer is disallowed; respectful register (आप, never तुम) is enforced.
- **Guide answers:** Cited sources must be an exact subset of retrieved chunk IDs; ungrounded policy numbers are forbidden; low confidence routes to human review.
- Code: `backend/app/llm/guards.py`. Every guard check, retry, and fallback event is recorded in `backend/app/llm/guard_stats.py`.
- Automated test report: `eval/guards/REPORT.md` (`make eval-guards`).

---

## 5. Low connectivity and low-cost devices

| Component | Needs network? | Offline / Low-bandwidth behaviour |
|---|---|---|
| Learn summary, peer checklist, last 50 messages | No (cached PWA) | Stored locally in IndexedDB / ServiceWorker cache |
| Sending a voice note or text | Queued offline | IndexedDB outbox with automated background retry on reconnect |
| Rehearsal responses | Yes (server AI) | Text-first delivery (text renders first; audio attaches when ready) |
| Audio playback | On demand in lite mode | Lite mode skips automatic audio download; text is always displayed |
| WhatsApp channel | WhatsApp queue | WhatsApp client offline retry; text fallback if media download fails |

Front-end pages are server-rendered HTML with vanilla JavaScript and a single CSS file. First-load budget is strictly under 150 KB excluding audio. Audio recordings use compressed WebM/OGG Opus at ~16 kbps mono.

---

## 6. Privacy & Data Protection (DPDP Act 2023 Posture)

Abhyas implements explicit data-minimisation and privacy safeguards, noting the following real-world architectural posture:

1. **Simulated Children (No Child Data Collected):**
   - Teachers practice exclusively with three fictional, simulated child personas (Ravi, Aman, Priya).
   - No real children's data is collected; the children are simulated.
2. **Cross-Border Inference (DPDP Section 16 Transfer Rules):**
   - Live speech transcription (Sarvam AI) and language reasoning (Anthropic Claude) utilize cloud APIs hosted outside local school servers. Teacher voice notes and prompt texts are transferred across borders for transient inference under commercial agreements.
3. **Ephemeral Audio Storage:**
   - Raw teacher voice notes are held transiently in server memory during transcription and discarded. Audio bytes are not stored on disk or in the database.
4. **PII Cryptography:**
   - Teacher phone numbers are hashed using salted SHA-256 (`phone_hash`) for database indexes and login lookup.
   - Reversible phone numbers for WhatsApp delivery are encrypted at rest using **Fernet symmetric encryption** (`cryptography.fernet.Fernet`, AES-128-CBC with PKCS7 padding and HMAC-SHA256 authentication). Reversible keys are never stored in git.
   - Synthesized child audio references (`audio_ref`) are deterministic SHA-256 cache keys (`hashlib.sha256`) of normalized text and voice parameters, protected by session ownership checks on `/api/audio/{audio_ref}.ogg`.
5. **Consent & Aggregation:**
   - Individual teacher rehearsal scores and fidelity metrics reach mentors (ARPs) only when the teacher explicitly opts in (`consent_share_scores == True`).
   - District and trainer consoles enforce **$n < 10$ suppression**: any school cohort or training batch with fewer than 10 teachers displays aggregate statistics only, redacting individual teacher records.
6. **Data Retention & Right to Erasure:**
   - Automated retention purge job deletes inactive session transcripts after `DATA_RETENTION_DAYS` (default: 90 days).
   - Teachers can inspect their profile or permanently purge their account and data via `GET/POST /teacher/delete` (`backend/app/web/teacher.py`).
7. **Legal Notice:**
   - A complete statutory compliance audit against the DPDP Act 2023 rules is a human legal task.

---

## 7. Scaling Path & Architecture Limits

- **Current Implementation:**
  - The application runs as a **single-instance service** (`--workers 1`) using an in-process asyncio job scheduler (`apscheduler.schedulers.asyncio.AsyncIOScheduler`) and in-memory conversation locks (`TeacherLockManager` in `backend/app/core/locks.py`).
  - This architecture avoids distributed lock overhead and split-brain states.
- **Production Scaling Path:**
  - **Shared Lock Manager:** Replace the in-process conversation lock with a Redis distributed lock (`redlock` / `aioredis`).
  - **Distributed Job Worker:** Decouple APScheduler from the web server process; run background workers using Celery or Arq backed by Redis or PostgreSQL.
  - **Database & Pooling:** Connect multiple stateless API worker instances to Supabase / RDS PostgreSQL via Supabase's session pooler (port 5432).
  - **Static & Media Delivery:** Serve cached synthetic audio assets through a CDN (Cloudflare or CloudFront) backed by S3 / Supabase Storage.

---

## 8. Content & Retrieval Status

- **Personas:** 3 simulated child personas implemented (`content/personas/`):
  - **Ravi (रवि):** Confident (`temperament: confident`).
  - **Aman (अमन):** Distracted (`temperament: distracted`).
  - **Priya (प्रिया):** Shy (`temperament: shy`).
  *(Bug rules belong to teaching moves, not personas; each move defines which bug rules apply to children during rehearsal.)*
- **Teaching Moves:** 4 moves implemented (`content/moves/`), all with `status: in_review` (no coach has approved a card yet; the UI labels them "समीक्षा में"):
  - `NUM_SUB_REGROUP_BUNDLES`: Subtraction with regrouping using ten-sticks.
  - `NUM_ADD_CARRY_BUNDLES`: Addition with bundle-making.
  - `NUM_PLACE_VALUE_BUNDLES`: Tens and ones representation.
  - `LIT_MATRA_BLENDING`: Hindi akshar grid and matra blending (group scene only; the three numeracy moves also have a one-on-one rubric).
- **Official source documents** (`content/sources/README.md` has the table, page counts and limits): five are ingested and searchable, **1,157 chunks** in `content/chunks/` (including a few seed chunks):
  - NIPUN Bharat Guidelines (MoE, 332 pp), NCERT Vidya Pravesh (56 pp) and NISHTHA FLN (NCERT, 618 pp), all English; each chunk carries a page span, a one-line Hindi gloss and Hindi keywords so Hindi questions match English text.
  - The two UP Samagra Shiksha Class 1 teacher guides (Ganit 112 pp, Bhasha 156 pp, Hindi) use legacy fonts, so they were **read from page images by an AI OCR step** (about 0.2 % of words wrong on 10 pages checked by eye; no human re-check yet; `docs/ocr_samples/`). Their citations say the passage was machine-read.
  - The Class 1 Ganit guide has no two-digit subtraction with regrouping, so the demo move `NUM_SUB_REGROUP_BUNDLES` is not backed by an official page and its `module_ref` stays `verified: false`; the system answers "not in my documents" rather than invent a citation.
  - Retrieval, measured 2026-10-22 (`docs/PERFORMANCE.md`): recall@5 **0.90** on 40 Hindi/Hinglish teacher questions (0.825 against the original single-source labels); with real models **20/20** off-topic and **10/10** negative questions are not answered (the retrieval gate alone rejects 12/20 and 8/10).

---

## 9. Evaluation & Cost Reports

Measured numbers, with date, git SHA and where they were measured, are in `docs/PERFORMANCE.md`; they were
taken on a developer laptop, **not** on the hosted service, and without speech.

- **Latency per stage** (`python -m eval.measure_latency`, real Claude models, 10 scenes / 41 turns): p50 / p95 in ms: act tagger 1385 / 2396, rule engine 0.1 / 0.2, child voice 1236 / 1938, coach feedback 6966 / 15216; 0 of 92 model calls used the deterministic fallback. The target (voice-in to voice-out p95 < 20 s on the hosted deployment) is **not yet measured**; `eval/latency/REPORT.md` is a mock-provider run and `python eval/latency/benchmark_latency.py --url <hosted URL>` is the command for the hosted run.
- **Memory:** 193 MB peak resident with the full index and one scene (Windows laptop; Render free has 512 MB; not measured there).
- **Cost:** about US$0.125 of Claude spend for 10 rehearsal scenes including coach feedback (`eval/one_on_one/LIVE_REPORT.md`), i.e. about US$0.0125 a scene. Speech cost and hosted cost per teacher are not measured: `make eval-cost` reads them from the database after a hosted run (`eval/cost/REPORT.md` is currently empty).
- **Guard results:** ten real-model scenes had 0 word-cap violations and 0 placeholder leaks (`eval/one_on_one/LIVE_REPORT.md`); adversarial guard cases are in `eval/guards/REPORT.md` (`make eval-guards`).
- **Calibration (inter-rater reliability):** the kappa harness is in `eval/calibration/` (Cohen's kappa); **no coach double-coding has been done yet, so there is no kappa figure**. The same is true of the teacher realism survey and user testing (`eval/user_testing/` holds blank templates).

---

## 10. Run locally

Prerequisites: Docker, Python 3.11, ffmpeg.

```bash
# 1. Setup environment and install dependencies (including dev)
cp .env.example .env          # leave API keys empty to run on mocks
make setup

# 2. Start PostgreSQL + pgvector and run migrations
make db-up
make db-migrate
make db-seed

# 3. Start local development server on port 8000
make dev
# Open http://localhost:8000 in your browser
```

Tests and code quality checks:
```bash
make test                     # runs ruff, mypy --strict, pytest (mocks only)
make audit                    # dependency vulnerability scan
node --test backend/tests/js/*.test.mjs   # service worker and chat.js behaviour
```

The database-backed tests (`backend/tests/integration/`) need a Postgres with pgvector; set `TEST_DATABASE_URL` to a scratch database (CI uses `pgvector/pgvector:pg16`) or they are skipped.

---

## 11. Repository map

```
backend/app/
  main.py            FastAPI app, middleware, router mounts, lifespan
  config.py          Every tunable, threshold, and pricing assumption
  rule_engine/       Personas, bug rules, state transitions (deterministic, no LLM)
  llm/               Claude client, prompts, schemas, guards, guard_stats
  speech/            STT / TTS adapters, audio utilities, synthesis cache
  sessions/          Weekly state machine, scene runner, move scoring
  retrieval/         BM25 search over guide chunks, source ingest, OCR pipeline
  rehearsal/         Scene runner and store, one-on-one diagnosis, STT hints
  web/               Teacher chat/PWA, ARP, trainer, coach review, admin, error pages
  scoring/           Rubric scoring, evidence ladder
  channels/          Channel adapters: whatsapp/ and web/ (chat API, teacher PWA)
  reports/           ARP digest, trainer aggregates (n ≥ 10 suppression)
  jobs/              Scheduler, background follow-ups, retention purges
  auth/ privacy/ db/ Security, password hashing, Fernet encryption, models and migrations
content/             Move YAMLs, persona cards, Hindi message catalog, sources manifest
eval/                Latency and memory measurements, cost report, kappa calibration, guards, retrieval recall, live scene runs, samples
docs/                Judge pack, deployment runbook, performance numbers, video script, deck outline, WhatsApp setup
spec/                Build specification (single source of truth)
```

---

## 12. Limitations & Next Steps

- **Curricular Scope:** 4 moves across foundational numeracy and literacy, all still awaiting coach approval (they carry a "समीक्षा में" label).
- **Evidence:** no real teacher has used the system, and there is no measured agreement with coaches, realism rating or hosted latency yet (see section 9).
- **Language Coverage:** Hindi and Hinglish speech only. Dialectal variations (Awadhi, Bhojpuri) may experience higher ASR error rates, mitigated by text fallback chips.
- **Rule Engine Boundaries:** The rule engine models research-backed foundational errors; it does not simulate every idiosyncratic classroom mistake.
- **WhatsApp Channel:** Live WhatsApp delivery requires Meta Business verification and template pre-approval. Evaluators can experience the full voice and text experience on the web channel.

---

## Licence

MIT. © 2026 Team Asymptotes. Built for the AI for Foundational Learning Hackathon 2026.
