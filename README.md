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
- **Rule-engine principle:** Each child has a hidden state (misconception, partial, can-explain) and a bug rule taken from research on children's errors. When the teacher asks Ravi to explain 43 − 27, the engine computes that Ravi subtracts the smaller digit from the larger and answers 24. Claude is only asked to say that result in a seven-year-old's voice, and a guard blocks any line whose numbers the engine did not allow. Telling a child the answer produces a parrot, and the bug returns on the next problem, as in a real class.
- **Grounded answers:** Teacher questions are answered from retrieved state-guide chunks (BM25 by default) with citations; low confidence escalates to the ARP.
- **Worked example:** `docs/worked_example_ravi.md`.

### Official Ingested Sources & Curricular Coverage

Abhyas grounds teacher Q&A and pedagogical moves in registered official government foundational learning curricula:

| Source ID | Official Document Title | Publishing Authority | Official Government Source URL |
|---|---|---|---|
| `nipun_guidelines_2021` | NIPUN Bharat Guidelines | Ministry of Education (MoE), GoI | `https://www.education.gov.in/sites/default/files/nipun_bharat_guidelines.pdf` |
| `up_ganit_sandarshika_c2` | UP FLN Teacher Guide Ganit (Class 2) | SCERT Uttar Pradesh | `https://scertup.gov.in/fln_teacher_guide_math_c2.pdf` |
| `up_bhasha_sandarshika_c1` | UP FLN Teacher Guide Bhasha (Class 1) | SCERT Uttar Pradesh | `https://scertup.gov.in/fln_teacher_guide_hindi_c1.pdf` |
| `ncert_vidya_pravesh` | Vidya Pravesh Guidelines | NCERT | `https://ncert.nic.in/pdf/vidya_pravesh_guidelines.pdf` |
| `ncert_fln_learning_outcomes` | FLN Learning Outcomes | NCERT | `https://ncert.nic.in/pdf/fln_learning_outcomes.pdf` |

**Seeded Move Cards (`content/moves/`):**
1. `NUM_PLACE_VALUE`: Place value with 10-bundles and loose sticks (Class 1–2).
2. `NUM_ADD_CARRY`: Addition with carry-over regrouping using concrete bundles (Class 2).
3. `NUM_SUB_REGROUP`: Two-digit subtraction with regrouping and bundles (Class 2).
4. `LIT_MATRA_BLENDING`: Two-letter word decoding with vowel matras (Class 1).

*Ingestion Status Note:* Official URLs, metadata, and spot-check reports (`eval/sources/<source_id>_spotcheck.md`) are verified in the repository. Full-text indexing of the multi-hundred-page state guides is supported via `pdfplumber` + Tesseract 5 / Surya OCR fallback with confidence filtering (pages $< 0.40$ dropped). Ingestion of official raw PDF binaries is ready and pending formal state departmental sign-off per HUMAN INPUT H7.

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

## 4. Cost per Teacher

All pricing tunables live in `backend/app/config.py` with published sources and as-of dates. Costs are computed dynamically via `make eval-cost` (`eval/cost/cost_report.py`).

### Unit Pricing Assumptions

- **Claude Haiku 5.5:** \$0.10 input / \$0.50 output / \$0.01 prompt cache read per million tokens (prompts up to 100k). Source: [Anthropic Pricing](https://platform.claude.com/docs/en/about-claude/pricing) (Oct 2026).
- **Claude Sonnet 5.5:** \$2.00 input / \$10.00 output / \$0.10 prompt cache read per million tokens. Source: [Anthropic Pricing](https://platform.claude.com/docs/en/about-claude/pricing) (Oct 2026).
- **Sarvam AI STT (`saaras:v4`):** ₹30.00 per hour of audio (~₹0.50 per minute). Source: [Sarvam AI Pricing](https://docs.sarvam.ai/api-reference-docs/pricing) (Oct 2026).
- **Sarvam AI TTS (`bulbul:v3`):** ₹30.00 per 10,000 characters. Source: [Sarvam AI Pricing](https://docs.sarvam.ai/api-reference-docs/pricing) (Oct 2026).
- **Exchange Rate:** USD to INR assumed at 88.00 (labelled assumption; update before live state deployment).

### Cost per Completed Weekly Loop (`SessionState == DONE`)

A typical weekly practice cycle consists of 1 explain-back voice note, 6–8 rehearsal voice turns with 3 simulated children, 1 reflection turn, and 1 rubric evaluation:

| Pipeline Component | Usage Volume per Completed Loop | Cost (INR) | Cost (USD) |
|---|---|---|---|
| **Teacher STT (Sarvam `saaras:v4`)** | ~4.5 minutes audio | ₹2.25 | \$0.026 |
| **Child & Coach TTS (Sarvam `bulbul:v3`)** | ~3,500 characters | ₹10.50 | \$0.119 |
| **Fast LLM (Claude Haiku 5.5)** | ~12 calls (15,000 in / 1,200 out tokens) | ₹0.18 | \$0.002 |
| **Smart LLM (Claude Sonnet 5.5)** | ~3 calls (8,000 in / 1,500 out tokens) | ₹2.73 | \$0.031 |
| **Total per Completed Weekly Loop** | **1 full weekly practice loop** | **₹15.66** | **\$0.178** |
| **Monthly Cost per Active Teacher** | **4 weekly loops per month** | **₹62.64** | **\$0.712** |

*In Lite Mode (no automatic audio download):* Teacher voice input is transcribed, but replies are text-first, reducing weekly loop cost to **₹5.16 (~$0.059)** per teacher.

---

## 5. Guardrails

- Every Claude output is validated against a Pydantic JSON schema before use.
- **Child lines:** Numbers must be strictly in the rule engine's allowed set; forbidden answers are rejected; the target number must appear; no out-of-character terms; length-capped. On failure: one LLM retry, then a deterministic fallback line from the message catalog.
- **Coach feedback:** Every cited quote must exist verbatim in the teacher's rehearsal transcript; praise for telling the answer is rejected; length and honorific tone (आप, never तुम) are strictly enforced.
- **Guide answers:** Cited sources must be an exact subset of retrieved chunks; low confidence answers automatically escalate to the ARP queue.
- **Code:** `backend/app/llm/guards.py`. Every guard attempt and fallback is recorded (`backend/app/llm/guard_stats.py`).
- **Report:** `eval/guards/REPORT.md` (`make eval-guards`) tracks live pass, retry, and fallback rates alongside an adversarial test suite.

---

## 6. Low Connectivity and Low-Cost Devices

| Part | Needs network? | Degrades to |
|---|---|---|
| Learn summary, peer checklist, last 50 messages | No (cached Service Worker PWA) | Fully functional offline |
| Sending a voice note or text | Queued offline, sent automatically when back | IndexedDB Outbox with automatic background retry |
| Rehearsal replies | Yes (server AI) | Text-first replies; lite mode = on-tap audio download |
| Audio playback | On tap in lite mode | Text always displayed |
| WhatsApp channel | WhatsApp's native offline queue | Text fallback on audio failure |

- **Asset Budget:** Server-rendered HTML with vanilla JS and one stylesheet; first-load size is kept under 150 KB (measured in `eval/lowband/REPORT.md`).
- **Audio Compression:** Voice notes recorded in browser using WebM/Opus or OGG/Opus at 16 kbps mono.
- **Data per Weekly Loop:** Normal mode ~1.2 MB total data / Lite mode ~180 KB total data. Detailed latency breakdown is logged in `eval/latency/REPORT.md`.

---

## 7. Hosting & Infrastructure: Today vs. Scale Roadmap

### Pilot Deployment (Today)
- **Application & API:** Render Singapore (`aws-0-ap-southeast-1` region, free/starter container tier).
- **Database:** Supabase Singapore (`aws-0-ap-southeast-1.pooler.supabase.com:5432`), PostgreSQL 16 + `pgvector` accessed via port 5432 Session Pooler (plain `postgresql://` connection string).
- **Why Singapore for Pilot?** Singapore offers Render container hosting coupled with direct undersea fibre connectivity to Indian telecom routes (Mumbai/Chennai), maintaining a low network round-trip time (~35–45 ms). This avoids trans-Pacific US routing delays while preserving sub-4.5s voice turnarounds.

### Production Scale Roadmap (Indian Sovereign Deployment)
- **Compute & Cloud:** Migration to AWS Asia-Pacific Mumbai (`ap-south-1`) or National Informatics Centre (NIC) MeghRaj Government Cloud, eliminating cross-border data transit.
- **Database:** Dedicated PostgreSQL + pgvector cluster hosted in Mumbai (AWS RDS or NIC state datacenter).
- **Sovereign Speech & Language Stack:** Integration with **Bhashini ULCA** (Universal Language Contribution API) for on-premise ASR and TTS. Hosting fine-tuned IndicConformer and IndicTTS models on state-managed GPU infrastructure replaces variable per-minute commercial SaaS fees with fixed server infrastructure costs.
- **Sovereign LLMs:** Quantized Indic LLM deployments (e.g. fine-tuned Llama 3.3 Indic / Sarvam-1) on state cloud for privacy-isolated, zero-egress reasoning.

---

## 8. Privacy & Data Protection (DPDP Act 2023 Compliance)

Abhyas is designed from the ground up to adhere to the **Digital Personal Data Protection (DPDP) Act 2023**:

1. **Section 16 Compliance (Protection of Children):**
   - Teachers practice exclusively with **simulated, fictional child personas** (Ravi, Aman, Meena) whose responses are generated by deterministic code.
   - **No real students, classrooms, or minors are ever recorded, identified, or tracked.** As no personal data of children is processed, Section 16 parental consent requirements are not triggered.
2. **Ephemeral Voice Processing:**
   - Teacher audio is held transiently in memory, transcribed via STT, and immediately discarded. Raw audio recordings are never persisted on disk or in the database.
3. **Cryptographic PII Safeguards:**
   - Teacher phone numbers are salted and hashed using SHA-256 (`phone_hash`) for database indexes.
   - Reversible phone numbers are stored as AES-256-GCM encrypted strings (`phone_enc`), used strictly for outbound WhatsApp delivery.
4. **Consent-Gated Oversight & Aggregation:**
   - Teacher rehearsal scores reach mentors (ARPs) only when the teacher grants explicit opt-in (`consent_share_scores == True`).
   - District and cluster trainer views enforce **$n \ge 10$ suppression**: any school cohort or training batch with fewer than 10 teachers displays aggregate statistics only, redacting individual teacher records.
5. **Right to Erasure & Review:**
   - Teachers can inspect their stored profile, download practice histories, or permanently purge their data via `/profile/delete`.

---

## 9. Run locally

Prerequisites: Docker, Python 3.11, ffmpeg.

```bash
cp .env.example .env          # leave API keys empty to run on mocks
make setup db-up db-migrate db-seed dev
# open http://localhost:8000
```

Tests and checks: `make test` (ruff, mypy --strict, pytest; mocks only). Dependency audit: `make audit`.

---

## 10. Repository map

```
backend/app/
  main.py            FastAPI app, middleware, routers, scheduler lifespan
  config.py          every tunable, threshold, and pricing assumption
  rule_engine/       personas, bug rules, state transitions (no LLM)
  llm/               Claude client, role prompts, schemas, guards, guard_stats
  speech/            STT / TTS adapters, audio utilities
  sessions/          weekly state machine, scene runner, move-path scoring
  retrieval/         BM25 search over guide chunks, OCR fallback, spot-checks
  scoring/           rubric scoring, evidence ladder
  channels/ whatsapp/ web/   channel adapters, chat API, teacher PWA
  reports/           ARP digest, trainer aggregates (n ≥ 10)
  jobs/              scheduler, background jobs, retention purges
  auth/ privacy/ db/ security, consent, purge, models and migrations
content/             move cards, personas, Hindi message catalog, sources manifest
eval/                latency, cost, kappa calibration, guards, realism, samples
docs/                deploy guide, runbook, video script, deck outline, WhatsApp setup
spec/                build specification
```

Evaluation reports: `eval/latency/REPORT.md`, `eval/cost/REPORT.md`, `eval/guards/REPORT.md`, `eval/calibration/` (kappa harness), `eval/user_testing/` (protocol and findings).

---

## 11. Limitations & Technical Realities

- **Voice Latency Breakdown:**
  - End-to-end voice turn takes ~2.5–4.5s on hosted infrastructure:
    - Sarvam STT: ~800–1,200 ms.
    - Intent routing & parallel child voicing (Haiku 5.5): ~400–800 ms.
    - Database commit & text-first delivery: < 50 ms (teacher sees text reply immediately).
    - Sarvam TTS (`bulbul:v3`): ~1,200–2,000 ms attached asynchronously.
  - While comfortably below the 20s competition threshold, 2G network drops can increase client-side audio upload/download durations.
- **Dialectal & Accent Variability:**
  - Speech models are tuned on standard Khariboli / Hindi and Hinglish. Strong regional dialects (Bhojpuri, Awadhi, Bundelkhandi) can experience increased Word Error Rate (WER) on technical mathematical phrases. Mitigated through fuzzy phoneme matching and text fallback chips.
- **Curricular Breadth:**
  - Currently seeds 4 high-leverage foundational moves across numeracy and literacy. Expanding to the full 16-move annual curriculum requires completing state review ("समीक्षा में" label).
- **Official PDF Ingestion (H7):**
  - Source URLs and metadata are verified; full automated ingestion and spot-check tooling is validated. Ingestion of live official state PDF files awaits formal state department data-sharing sign-off (HUMAN INPUT H7).

---

## 12. Roadmap

- **Phase 1: District Pilot (Dec 2026 – Feb 2027):** 50–100 teachers across one UP district (DIET Kanpur Nagar), 16 weekly moves, double-coded coach calibration (target $\kappa \ge 0.70$).
- **Phase 2: Bhashini & State Cloud Migration (Q2 2027):** Replace commercial SaaS speech APIs with Bhashini ULCA models hosted on NIC cloud; deploy dedicated on-premise PostgreSQL cluster in AWS Mumbai / NIC.
- **Phase 3: Multi-Language & IVR Support (Q3 2027):** Expand to Marathi, Gujarati, and Telugu; introduce interactive voice response (IVR) for basic feature phones without WhatsApp/web connectivity.

---

## Licence

MIT. © 2026 Team Asymptotes. Built for the AI for Foundational Learning Hackathon 2026.
