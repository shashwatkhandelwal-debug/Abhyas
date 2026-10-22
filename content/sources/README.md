# Curricular sources (`content/sources/`)

The guide answers (`ASK`) and the "what the official document says" line in the learn step are
grounded in these documents. The PDFs are **not in git** (`content/sources/*.pdf` is ignored); what
is committed is the processed text in `content/chunks/*.jsonl` and `sources.yaml` (URL, sha256, date).

Rebuild: put the PDFs here, then `make content-ingest` (needs `ANTHROPIC_API_KEY` only for new
chunks; glosses already in the committed `.jsonl` are reused by text hash).

## What is and is not ingested (checked 2026-10-22)

| Source | Pages | Status | Why / result |
|---|---|---|---|
| `nipun_guidelines_2021` — NIPUN Bharat Guidelines (MoE), English | 332 | **ingested**: 294 chunks | 247 pages chunked. 85 skipped: blank/near-empty pages and the image-only annexure pages 289–325 (no text layer, no OCR). |
| `ncert_vidya_pravesh` — Vidya Pravesh (NCERT), English | 56 | **ingested**: 67 chunks | 49 pages chunked, 7 blank/near-empty skipped. |
| `up_ganit_sandarshika_c1` — UP Samagra Shiksha, Ganit, Class 1, Hindi | 112 | **NOT ingested** | Text layer uses a legacy non-Unicode Hindi font (private-use codepoints, e.g. `U+F072 U+F068` for "तीन"). 0.58 "Devanagari ratio" is from a few stray glyphs; the body text is unreadable. No OCR engine (Tesseract) is installed. |
| `up_bhasha_sandarshika_c1` — UP Samagra Shiksha, Bhasha, Class 1, Hindi | 156 | **NOT ingested** | Legacy Chanakya-style fonts: extracted text is Latin gibberish (`Hkk"kk f'k{k.k`), 0 Devanagari. No OCR engine installed. |
| `nishtha_fln` — NISHTHA FLN (NCERT), English | 618 | **NOT ingested** | File was not supplied. Known URL is in `sources.yaml`. |

So today every official excerpt the app can cite is **English**. Each chunk carries a one-line Hindi
gloss and 5–8 Hindi keywords (generated once offline with `claude-haiku-5-5`) so Hindi queries match
English text; the excerpt shown on tap is the original English with that Hindi summary above it.

To unlock the two Hindi guides: install Tesseract with the `hin` traineddata and re-run ingestion
(the existing OCR hook in `backend/app/retrieval/ingest.py` already expects it), or add a Kruti Dev /
Chanakya → Unicode converter and verify the output by eye on sampled pages before committing chunks.

## Chunk format (`content/chunks/<source_id>.jsonl`)

`chunk_id, source_id, title, short_hi, lang, pdf_page_start/end, printed_page_start/end, heading,
text, gloss_hi, keywords_hi` (plus `source`, `source_short_hi`, `section`, `page` kept for the older
loaders). 150–440 words, ~40 words of overlap, split at headings and page-aware.

- **Page numbers are PDF page indices** (what a PDF viewer shows). The printed page is stored when
  detected (NIPUN: printed = PDF − 2; Vidya Pravesh: printed = PDF − 10) and shown in the excerpt panel.
- Citation shown to teachers: `स्रोत: <short_hi>, पृष्ठ N`, tappable → `GET /api/source/<chunk_id>`.

## Gloss cost (one-off)

376 + 3 `claude-haiku-5-5` calls for 361 chunks: 518,098 input tokens, 125,141 output tokens
≈ **US$0.11** at $0.10 / $0.50 per million tokens.

## Grade 1 Maths guide: two-digit subtraction with regrouping — NOT covered

Checked by reading the guide's contents and weekly-objectives pages as images (text is unreadable).
The guide is a Class 1 weekly plan covering **weeks 9–25** only. Subtraction appears as: week 16
"1 से 9 तक की संख्याओं के घटाव" (printed pp. 42–45, PDF 44–47), week 17 "20 तक के घटाव" (printed
46–49), week 18 "20 तक का घटाव शाब्दिक प्रश्न; दो अंक की संख्या से एक अंक की संख्या" (printed 50–53,
PDF 52–55). Bundles of 10 appear in week 21 for **writing numbers up to 99**, not for subtraction.
There is no two-digit − two-digit subtraction with regrouping in these weeks; that is a Class 2
topic. The `NUM_SUB_REGROUP_BUNDLES` move card is therefore *not* backed by this guide, and the
retrieval eval contains no question targeting it. (Weeks 1–8 of the Class 1 plan are not in this volume.)

## Honest limits

- BM25 only (no embeddings). Romanised Hindi ("bachon ki bhasha") matches only through its English
  words; the question classifier's Hindi rewrite (`search_query_hi`) is what normally fixes this.
- `RETRIEVAL_MIN_SCORE` (0.10) is calibrated on 25 queries; retrieval alone rejects 6 of 10 off-topic
  ones, the answerer's confidence gate catches the rest. See `eval/retrieval_recall.py`.
