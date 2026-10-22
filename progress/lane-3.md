# Lane 3 Progress — Official Source Ingestion, OCR Pipeline & Citations (Task T64)

## 1. Overview
Lane 3 implements the official government document ingestion pipeline, OCR fallback for garbled legacy fonts or scanned pages, Devanagari typography spot-check verification, and guide citation formatting in compliance with `spec/10_content.md` §10.4 and `spec/05_llm_roles.md` §5.8.

## 2. Official Sources Registry & Policy Compliance
- **Government-Only Sources**: Registered 5 official foundational learning documents in `content/sources/sources.yaml`:
  1. `nipun_guidelines_2021`: MoE NIPUN Bharat Guidelines (`education.gov.in`)
  2. `up_ganit_sandarshika_c1`: UP Basic Shiksha Parishad Ganit Class 2 Sandarshika (`scertup.gov.in`)
  3. `up_bhasha_sandarshika_c1`: UP Basic Shiksha Parishad Bhasha Class 1 Sandarshika (`scertup.gov.in`)
  4. `ncert_vidya_pravesh`: NCERT Vidya Pravesh Guidelines (`ncert.nic.in`)
  5. `ncert_fln_learning_outcomes`: NCERT FLN Learning Outcomes (`ncert.nic.in`)
- **Metadata Fields**: Every registered source documents `url`, `sha256` (`TODO(human)` pending raw PDF download per H7), `as_of_date`, `lang`, and `licence_note`.
- **Git Hygiene**: `content/sources/*.pdf` is strictly gitignored; raw PDFs are never committed to the repository.

## 3. Ingestion Pipeline & OCR Architecture

### 1. Dual-Layer Text Extraction
- Primary extractor: `pdfplumber` for precise Unicode text extraction and layout preservation.
- Fallback extractor: `pypdf` when `pdfplumber` cannot open or parse specific streams.

### 2. Hindi Legibility & Font Garble Detection
- `is_hindi_garbled`: Identifies legacy ASCII-mapped fonts (Kruti Dev, Chanakya, APS) where alphabetic characters exist but the Devanagari character ratio is $< 0.3$.
- `is_page_text_poor`: Flags pages with empty text layers, garbled legacy fonts, or high replacement character counts ($> 15\%$).

### 3. OCR Engine & Confidence Filtering
- `run_ocr_on_page`:
  - When text layer is poor, renders page image at 300 dpi and executes Tesseract 5 (`hin+eng`) with word-level confidence averaging.
  - Supports optional Surya OCR engine.
  - Drops pages where `confidence < confidence_threshold` (default 0.40) and logs a warning with page number and confidence.
- Headless CI mock support: `set_ocr_mock_handler` allows unit/integration tests to test OCR logic deterministically without requiring external C-binaries on system PATH.

### 4. CLI Signature
`python -m backend.app.retrieval.ingest --source <id> [--ocr tesseract|surya] [--confidence-threshold 0.4] [--all] [--no-spotcheck]`
- Builds `content/chunks/seed_from_moves.jsonl` from move cards.
- Ingests registered official documents and writes `content/chunks/<source_id>.jsonl`.

### 5. Typographic Spot-Check Generation
- `generate_spotcheck_markdown` generates `eval/sources/<source_id>_spotcheck.md` evaluating up to 10 sample pages:
  - Compares original extracted text snippet vs. NFC normalized and cleaned text.
  - Automatically assesses Devanagari typography:
    - Unicode NFC normalization consistency.
    - Absence of orphaned dependent vowel signs (matras).
    - Absence of uncombined trailing viramas (halants).
    - Status classification: `PASS` (Clean: Conjuncts and matras rendered correctly), `REVIEW` (Anomalies), or `DROPPED`. App code retains zero Devanagari literals in accordance with package hygiene rules.

### 6. Guide Citation Formatting
- `format_guide_citation`: Formats bracketed citations in standard `[source, p. XX]` format.
- Catalog template: Added `ask_source_citation: "[{source}, p. {page}]"` to `content/messages_hi.yaml`.
- `compose_guide_reply` generates `स्रोत: {source}, पृष्ठ {page}` from `ask_source_line`.

## 4. Unused Prompt Note: `page_ocr.v1.md`
- `backend/app/llm/prompts/page_ocr.v1.md` is an authored reference prompt for Vision LLM single-page transcription.
- **Why it is not wired into automated ingestion**: Multi-hundred-page state teacher guides (150–300 pages each) would consume millions of Sonnet tokens and introduce non-deterministic latency. Automated ingestion strictly uses local deterministic extractors (`pdfplumber` + Tesseract 5 / Surya OCR). `page_ocr.v1.md` is retained for manual, single-page human evaluation only.

## 5. Verification & Testing
- PR #27 Head SHA: `7752c1b`
- GitHub Actions CI Run: `39066252291` (All 5 jobs passed: `audit`, `content`, `lint`, `secrets`, `test`).
- `backend/tests/integration/test_retrieval.py` (25/25 tests passing):
  - `test_ingest_synthetic_pdf_hindi_phrase_with_ocr_fallback`: Builds synthetic PDF, tests OCR fallback on poor text layer, verifies chunk extraction of known Hindi phrase, and validates spot-check markdown generation.
  - `test_ingest_pdf_drops_low_confidence_ocr_pages`: Verifies that pages with confidence $< 0.40$ are dropped and logged with warning via `patch`.
  - `test_guide_citations_format_and_real_chunk_pages`: Verifies `[source, p. XX]` bracketed citations, None page fallback, and catalog `ask_source_line` formatting.
- `backend/tests/unit/test_guide_answerer.py` (10/10 tests passing):
  - Verifies answer composition, quote guarding, and source deduplication.
- `backend/tests/unit/test_state_machine.py` (66/66 tests passing, including `test_sessions_package_hygiene_no_broad_exceptions_and_no_devanagari`).
