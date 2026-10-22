# Abhyas (अभ्यास)

> **A voice-first Hindi practice partner for government primary-school teachers.** Fifteen minutes a week, on WhatsApp or the web: learn one teaching move, then rehearse it with three simulated children whose mistakes are computed by a rule engine, not invented by an AI.

**AI for Foundational Learning Hackathon 2026 · Challenge 3: Teacher Support and Training · Team Asymptotes** (Shashwat Khandelwal, Vedant Arora, Divyansh Agrawal)

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
| Trainer (DIET) | `trainer.demo` | in the submission form | Module × batch view, $n < 10$ suppression (batch KNP-B3) |
| FLN coach | `coach.demo` | in the submission form | Review queue, blind calibration, move approval |
| Admin | `admin` | in the submission form | Latency, guardrail stats, fast-forward timers, reset demo |

WhatsApp: TODO(human): number and join instructions. Meta test numbers only accept pre-registered recipients, so evaluators who want WhatsApp should send their phone number through the submission form; everyone else can use the web chat, which runs the identical conversation engine and audio pipeline.

All demo data in the UI is synthetic and labelled "डेमो". No real teacher or child personal data is in this repository.

---

## 2. Sample inputs

Tappable chips in the web chat (demo mode) and listed in `eval/samples/samples.yaml`. Each is a Hindi teacher utterance with a stated expected result:

| # | Step | What the teacher says | What should happen |
|---|---|---|---|
| 1 | Rehearse | "रवि, तुमने 43 में से 27 कैसे घटाया? मुझे एक-एक कदम बताओ।" | Ravi explains his own bug ("3 में से 7 नहीं घटता, तो 7 में से 3 घटाया… 24"). He never says 16. |
| 2 | Rehearse | "सब लोग देखो, ये 4 बंडल और 3 खुली तीलियाँ हैं…" | Concrete representation to the whole class; children move to *partial* understanding. |
| 3 | Rehearse | "Aman, sahi answer 16 hai, yaad rakho." (Hinglish) | Aman parrots "16…?" without understanding; on the next problem he relapses to his bug. |
| 4 | Explain back | A one-minute explanation of the move | Fidelity score with quoted evidence; the reply names the one missing key point. |
| 5 | Ask | A multigrade-classroom question | Answer ≤ 80 words citing a guide excerpt, or escalation to the ARP. |

Audio versions of the samples can be rendered with `make samples` (requires `SARVAM_API_KEY`). Without audio, the chips send text directly.

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

- **Weekly loop:** `LEARN` → `EXPLAIN_BACK` → `MODEL` → `REHEARSE` → `FEEDBACK` → `RETRY` → `TRY_IN_CLASS` → `REFLECT` → `DONE`.
- **Voice in, voice out:** Hindi and Hinglish speech is transcribed via STT, the turn is processed, and the reply is synthesized in a distinct voice per child. Audio is discarded after transcription; text is always rendered.
- **Rule-engine principle:** Each simulated child has a hidden cognitive state (`misconception`, `partial`, `can_explain`) and a deterministic bug rule taken from research on primary numeracy errors. When the teacher asks Ravi to explain $43 - 27$, the deterministic rule engine computes that Ravi subtracts the smaller digit from the larger ($7 - 3 = 4$, $4 - 2 = 2$) and answers $24$. Claude is only asked to voice that exact result in a seven-year-old's speech register; an output guard rejects any generation whose numbers the engine did not allow. Telling a child the answer produces parrot behaviour, and the bug returns on the subsequent problem.
- **Grounded answers:** Teacher questions are answered only from excerpts of the official documents we have ingested (BM25 over 361 chunks; see section 8). Each answer carries `स्रोत: <document>, पृष्ठ N`; on the web the citation is a chip that opens the excerpt. If nothing clears the retrieval gate (`RETRIEVAL_MIN_SCORE` and at least two shared query terms), or confidence is low (< 0.60), or a guard fails, the bot says it did not find the answer in its documents and escalates to the ARP instead of guessing.
- **Hindi by default, English on request:** the UI text and system messages switch to English from the chat menu or the login page (kept per user). Children's lines and coach feedback stay Hindi; a *Translate* control under child / coach / guide bubbles shows an on-demand English translation (cached per message; the fast Claude model, guarded so numbers and names are kept).
- **Worked example:** See `docs/worked_example_ravi.md`.

### AI services used

| Service | Used for | Model / product | Key | Without a key |
|---|---|---|---|---|
| Anthropic Claude (fast) | intent routing, act tagging, child voice, question classification, on-demand English translation; one-off Hindi glosses for source chunks (offline, ≈US$0.11) | `claude-haiku-5-5` | `ANTHROPIC_API_KEY` | Mock LLM with deterministic fixtures (translation shows a demo placeholder) |
| Anthropic Claude (smart) | coach feedback, explain-back fidelity, guide answers, content generation | `claude-sonnet-5-5` | `ANTHROPIC_API_KEY` | Mock LLM, deterministic feedback bank |
| Sarvam AI | Hindi speech-to-text and text-to-speech | `saaras:v4`, `bulbul:v3` | `SARVAM_API_KEY` | Mock STT/TTS, text box in web chat |
| Meta WhatsApp Cloud API | WhatsApp channel | Graph API | `WHATSAPP_*` | Channel disabled; mocked Graph API in tests |
| Voyage AI (optional) | dense retrieval | `voyage-multilingual-2` | `VOYAGE_API_KEY` | BM25 sparse search (default) |

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
- **Teaching Moves:** 4 approved foundational moves implemented (`content/moves/`):
  - `NUM_SUB_REGROUP_BUNDLES`: Subtraction with regrouping using ten-sticks.
  - `NUM_ADD_CARRY_BUNDLES`: Addition with bundle-making.
  - `NUM_PLACE_VALUE_BUNDLES`: Tens and ones representation.
  - `LIT_MATRA_BLENDING`: Hindi akshar grid and matra blending.
- **Official source documents** (`content/sources/README.md` has the full table and limits):
  - **Ingested and searchable:** NIPUN Bharat Guidelines (MoE, 332 pp) and NCERT Vidya Pravesh (56 pp), both English — 361 chunks in `content/chunks/`, each with page span, a one-line Hindi gloss and Hindi keywords so Hindi questions match English text. Recall@5 on 20 Hindi/Hinglish teacher questions: **0.95** through the production retrieval gate (0.90 raw BM25); 15 of 20 off-topic questions are already rejected by that gate and the rest by the classifier / answerer (`make eval-retrieval`, `eval/guide_e2e_live.py`).
  - **Supplied but NOT ingested:** the two UP Samagra Shiksha Sandarshikas (Ganit and Bhasha, Class 1, Hindi). Their PDFs use legacy non-Unicode fonts and no OCR engine is available, so their text is unreadable. The Grade 1 Ganit guide covers subtraction only up to 20 (weeks 16–18); two-digit subtraction with regrouping is not in it.
  - **Not supplied:** NISHTHA FLN.
  - The move cards' `module_ref` still point at `up_ganit_sandarshika_c1` (`verified: false`); those cards are not backed by an ingested page.

---

## 9. Evaluation & Cost Reports

- **Cost per Teacher:**
  - Run the cost report generator:
    ```bash
    make eval-cost
    ```
    This reads actual LLM token consumption and speech spend from the database, producing `eval/cost/REPORT.md`.
  - **Hosted Production Cost:** `TODO(human)` from the hosted evaluator run (current figures in report reflect synthetic mock/unit test runs only).
- **Latency Benchmark:**
  - Run the latency harness:
    ```bash
    make eval-latency
    ```
    This measures turn-by-turn processing stages, writing `eval/latency/REPORT.md`.
  - Hosted p95 target is < 20 s; actual latency depends on network transit time and external provider status.
- **Calibration (Inter-Rater Reliability):**
  - Coach agreement with human experts is evaluated in `eval/calibration/` using Cohen's kappa ($\kappa$).

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
```

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
  retrieval/         BM25 search over guide chunks, OCR pipeline
  scoring/           Rubric scoring, evidence ladder
  channels/          Channel adapters: whatsapp/ and web/ (chat API, teacher PWA)
  reports/           ARP digest, trainer aggregates (n ≥ 10 suppression)
  jobs/              Scheduler, background follow-ups, retention purges
  auth/ privacy/ db/ Security, password hashing, Fernet encryption, models and migrations
content/             Move YAMLs, persona cards, Hindi message catalog, sources manifest
eval/                Latency harness, cost report, kappa calibration, guards, samples
docs/                Deployment runbook, video script, deck outline, WhatsApp setup
spec/                Build specification (single source of truth)
```

---

## 12. Limitations & Next Steps

- **Curricular Scope:** Currently includes 4 seed moves across foundational numeracy and literacy. Unreviewed moves carry a "समीक्षा में" label.
- **Language Coverage:** Hindi and Hinglish speech only. Dialectal variations (Awadhi, Bhojpuri) may experience higher ASR error rates, mitigated by text fallback chips.
- **Rule Engine Boundaries:** The rule engine models research-backed foundational errors; it does not simulate every idiosyncratic classroom mistake.
- **WhatsApp Channel:** Live WhatsApp delivery requires Meta Business verification and template pre-approval. Evaluators can experience the full voice and text experience on the web channel.

---

## Licence

MIT. © 2026 Team Asymptotes. Built for the AI for Foundational Learning Hackathon 2026.
