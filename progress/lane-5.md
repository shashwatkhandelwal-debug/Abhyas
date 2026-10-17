# Lane 5 Progress — README, Judging Criteria, Scale Roadmap & Data Protection (Task T65)

## 1. Overview
Lane 5 updates the project documentation (`README.md`) to reflect the complete end-to-end implementation built across all lanes, adhering strictly to judging criteria, transparency requirements, and factual claims without unverified or synthetic evidence.

## 2. Ingested Official Sources & Curricular Coverage
- **Government Portals Registered**: Documented 5 official foundational learning curricula registered in `content/sources/sources.yaml` with official government URLs:
  1. `nipun_guidelines_2021`: MoE NIPUN Bharat Guidelines (`education.gov.in`)
  2. `up_ganit_sandarshika_c2`: UP SCERT FLN Teacher Guide Class 2 Mathematics (`scertup.gov.in`)
  3. `up_bhasha_sandarshika_c1`: UP SCERT FLN Teacher Guide Class 1 Hindi / Language (`scertup.gov.in`)
  4. `ncert_vidya_pravesh`: NCERT Three-Month School Preparation Module (`ncert.nic.in`)
  5. `ncert_fln_learning_outcomes`: NCERT FLN Learning Outcomes (`ncert.nic.in`)
- **Seeded Move Cards**:
  - `NUM_PLACE_VALUE`: Place value with 10-bundles and loose sticks (Class 1–2).
  - `NUM_ADD_CARRY`: Addition with carry-over regrouping using concrete bundles (Class 2).
  - `NUM_SUB_REGROUP`: Two-digit subtraction with regrouping (Class 2).
  - `LIT_MATRA_BLENDING`: Two-letter word decoding with vowel matras (Class 1).
- **Ingestion Status Note**: Documents that official PDF URLs and spot-checks (`eval/sources/<source_id>_spotcheck.md`) are verified; full-text indexing with Tesseract 5 / Surya OCR fallback is ready, while raw official PDF byte ingestion awaits state sign-off per HUMAN INPUT H7.

## 3. Cost per Teacher Breakdown (from Lane 1)
All unit prices are cited with published vendor pricing links and October 2026 as-of dates:
- **Claude Haiku 5.5**: $0.10 in / $0.50 out / $0.01 cache read per MTok.
- **Claude Sonnet 5.5**: $2.00 in / $10.00 out / $0.10 cache read per MTok.
- **Sarvam STT (`saaras:v4`)**: ₹30.00 per audio hour (~₹0.50/min).
- **Sarvam TTS (`bulbul:v3`)**: ₹30.00 per 10,000 characters.
- **USD/INR Exchange Rate**: 88.00 (labelled assumption; to update before state deployment).
- **Computed Cost per Completed Weekly Loop**:
  - Teacher STT (~4.5 min): ₹2.25
  - Child & Coach TTS (~3,500 chars): ₹10.50
  - Haiku LLM (12 calls): ₹0.18 ($0.002)
  - Sonnet LLM (3 calls): ₹2.73 ($0.031)
  - **Total per Completed Loop**: **₹15.66 (~$0.178)**
  - **Total per Month (4 loops / teacher)**: **₹62.64 (~$0.712)**
  - *Lite Mode (text-first, on-tap audio)*: **₹5.16 (~$0.059)** per loop.

## 4. Hosting & Scale Roadmap
- **Pilot Architecture (Today)**:
  - Render Singapore (`aws-0-ap-southeast-1`) container runtime.
  - Supabase Singapore (`aws-0-ap-southeast-1.pooler.supabase.com:5432`) PostgreSQL 16 + pgvector accessed via Session Pooler.
  - Singapore host rationale: Direct undersea fibre connection to Indian telecom gateways (Mumbai/Chennai), maintaining ~35–45 ms round-trip latency to ensure interactive < 4.5s voice turnaround.
- **Indian Sovereign Production Path (Roadmap)**:
  - AWS Asia-Pacific Mumbai (`ap-south-1`) or National Informatics Centre (NIC) MeghRaj Government Cloud for strict zero-data-egress compliance.
  - On-premise **Bhashini ULCA** speech models (IndicConformer ASR and IndicTTS) hosted on state GPU infrastructure, eliminating per-minute commercial SaaS fees.
  - Private Indic LLMs deployed on state NIC cloud.

## 5. Privacy & DPDP Act 2023 Compliance
- **Section 16 (Protection of Children)**: Teachers practice exclusively with synthetic, simulated children (Ravi, Aman, Meena). No actual minors or classroom students are ever recorded or identified. Section 16 parental consent obligations are not triggered.
- **Ephemeral Audio**: Teacher voice notes are transcribed in memory and discarded immediately; raw audio is never persisted.
- **PII Cryptography**: Phone numbers are stored as salted SHA-256 hashes (`phone_hash`) with AES-GCM encryption (`phone_enc`) for outbound messaging only.
- **Consent Gates & Suppression**: Mentor (ARP) visibility requires teacher opt-in; trainer dashboards enforce $n \ge 10$ suppression on small batches.

## 6. Limitations & Technical Realities
- **Turn Latency**: Documented per-stage budget: STT (~800–1,200 ms), reasoning + parallel child voicing (~400–800 ms), database commit (< 50 ms), TTS audio synthesis (~1,200–2,000 ms attached asynchronously). Total turnaround: ~2.5–4.5s.
- **Dialectal Diversity**: Notes that regional Hindi dialects (Bhojpuri, Awadhi, Bundelkhandi) may exhibit higher STT WER, mitigated by fuzzy phoneme matching and text fallback chips.
