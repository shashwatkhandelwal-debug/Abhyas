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
| `up_ganit_sandarshika_c1` — UP Samagra Shiksha, Ganit, Class 1, Hindi | 112 | **ingested via OCR**: 168 chunks (`ocr: true`) | Legacy non-Unicode font, so every page was read from its image (see below). 6 pages skipped: 2 near-empty covers, 3 flagged unreliable (PDF 4 a teacher-tracker form, 5 blank/picture, 7 contents), 1 letter grid. |
| `up_bhasha_sandarshika_c1` — UP Samagra Shiksha, Bhasha, Class 1, Hindi | 156 | **ingested via OCR**: 325 chunks (`ocr: true`) | Legacy Chanakya-style fonts, so every page was read from its image (see below). 10 pages skipped: 2 near-empty, 2 flagged unreliable (PDF 6, 9), 6 letter-grid pages (146–151). |
| `nishtha_fln` — NISHTHA FLN (NCERT), English | 618 | **NOT ingested** | File was not supplied. Known URL is in `sources.yaml`. |

The two NIPUN/NCERT sources are **English**: each chunk carries a one-line Hindi gloss and 5–8 Hindi
keywords (generated once offline with `claude-haiku-5-5`) so Hindi queries match English text; the
excerpt shown on tap is the original English with that Hindi summary above it. The two UP guides are
Hindi and OCR'd (next section); their excerpts carry a note that the text was machine-read.

## OCR of the two UP Hindi guides (done 2026-10-22)

Their text layers are unusable (legacy fonts), so `backend/app/retrieval/page_ocr.py` renders every
page with PyMuPDF (grayscale PNG, longest edge 1568 px) and reads it with `claude-haiku-5-5` vision
(`page_ocr` role: schema-validated, `guard_page_ocr` Devanagari ratio ≥ 0.60, one retry). Results are
cached by page-image hash in `content/sources/ocr_cache/` (committed), so a re-run costs nothing;
`make content-ingest` then chunks the cached text like any other source.

| | Ganit (112 pp) | Bhasha (156 pp) | Total |
|---|---|---|---|
| API calls | 109 (+3 test pages) | 156 | 268 |
| Input tokens | 369,510 (+9,810) | 516,660 | 895,980 |
| Output tokens | 152,630 (+6,131) | 305,137 | 463,898 |
| Cost @ US$0.10 / $0.50 per M tokens | $0.1133 (+$0.0040) | $0.2042 | **≈ US$0.32** of the US$1.50 cap |

(The worst-case estimate before the run, assuming 3,000 output tokens a page, was US$0.48.) The
retrieval eval then used the real Haiku classifier and Sonnet answerer on the 30 off-topic/negative
questions (about 50 calls, an estimated ≤ US$0.25, not metered).

**Quality, measured by eye, not against ground truth.** `eval/ocr_samples.py` saved 10 random pages
(seed 2026; 5 per guide) as image + OCR text pairs in `docs/ocr_samples/`. I compared all ten against
their images: about 2,900 words, **6 word errors ≈ 0.2 % word error rate** (rough 95 % interval
0.1–0.5 %; ten pages is a small sample and I am not an independent reader). The errors are small
substitutions: `रिमीडियल` read as `रिमेडियल` (×2), `चिह्नित` as `चिन्हित` (×2), `संदर्शिका` as `संदर्भिका`,
`बच्चे` as `बचे`. Numbers and tables were read correctly. Known weaknesses:

- **Column order.** On two-column pages the model sometimes interleaves the blocks (2 of the 10 pages:
  a continuation line appears before its section). Words are right, the reading order is not, so an
  excerpt can read oddly; retrieval is unaffected.
- **Source artefacts.** A few lines are printed in the wrong font in the PDF itself (e.g. `तैयारी :
  fjehfM;y dh xfrfof/k lanf'kZdk ls ns[ksaA`, legacy font for "रिमीडियल की गतिविधि संदर्शिका से
  देखें"). The OCR copies them; `strip_legacy_font_runs` drops such Latin runs before chunking.
- **Skipped pages (16 of 268):** blank covers, a tracker form and a contents page whose digit/Latin-heavy text fails the
  Devanagari guard (Ganit PDF 4, 7), two pages the model returned nothing usable for (Ganit 5, Bhasha 9),
  Bhasha PDF 6 (ratio 0.58), and 7 letter-grid pages (tables of single akshars).
- No second OCR engine was available to cross-check, and the 10-page sample was not re-read by a
  native Hindi speaker. **A human should open `docs/ocr_samples/README.md` and confirm the error rate.**

Page numbers in citations are PDF page indices; the printed page is PDF − 2 in both guides.

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

Checked by reading the guide's contents and weekly-objectives pages as images; the OCR'd text now agrees.
The guide is a Class 1 weekly plan covering **weeks 9–25** only. Subtraction appears as: week 16
"1 से 9 तक की संख्याओं के घटाव" (printed pp. 42–45, PDF 44–47), week 17 "20 तक के घटाव" (printed
46–49), week 18 "20 तक का घटाव शाब्दिक प्रश्न; दो अंक की संख्या से एक अंक की संख्या" (printed 50–53,
PDF 52–55). Bundles of 10 appear in week 21 for **writing numbers up to 99**, not for subtraction.
There is no two-digit − two-digit subtraction with regrouping in these weeks; that is a Class 2
topic. The `NUM_SUB_REGROUP_BUNDLES` move card is therefore *not* backed by this guide, and the
retrieval eval contains no question targeting it. (Weeks 1–8 of the Class 1 plan are not in this volume.)

## Honest limits

- The OCR'd guides make Hindi questions share everyday words with the corpus, so the *deterministic* retrieval
  gate alone now rejects **12 of 20** off-topic questions (it was 15 of 20 on the English-only corpus). End to end
  the result is unchanged: real classifier + gate + answerer 20/20 not answered (19 out_of_scope, 1 admin canned
  reply), classifier bypassed 20/20 (12 at the gate, 8 by the answerer), negatives 10/10. Recall@5 on the 30
  questions is 0.93 (28/30; misses q16, q20), including 10 new Hindi questions on the UP guides, all hit.

- BM25 only (no embeddings). Romanised Hindi ("bachon ki bhasha") matches only through its English
  words; the question classifier's Hindi rewrite (`search_query_hi`) is what normally fixes this.
- Retrieval gate (`GuideRetriever.retrieve_supported`): `RETRIEVAL_MIN_SCORE` (0.10) **and** a chunk must
  share `RETRIEVAL_MIN_MATCHED_TERMS` (2) distinct non-stopword query terms. On the 20 off-topic questions
  in `eval/retrieval_questions.yaml` the score gate alone rejected 7; with the term gate 15 are rejected
  (9 of the 10 older negatives). The classifier (out_of_scope) and the answerer (confidence, citation and
  overlap guards) reject the rest. See `eval/retrieval_recall.py` and `eval/guide_e2e_live.py`.
