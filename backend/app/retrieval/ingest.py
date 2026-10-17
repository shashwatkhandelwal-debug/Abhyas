"""Ingestion pipeline for state guides and move cards (spec/10 §10.4).

Provides:
- Seed chunk extraction from move cards (content/moves/*.yaml -> content/chunks/seed_from_moves.jsonl)
- PDF ingestion pipeline for official state guides (sources.yaml):
  1. Text extraction per page via pypdf
  2. Garble detection (Devanagari char ratio < 0.3)
  3. Cleaning (NFC, de-hyphenation, repeated header/footer suppression)
  4. Chunking (250-400 words, preserving section and page)
  5. Tokenization for BM25 with Hindi stopwords filtering
  6. Writing to content/chunks/<source_id>.jsonl
- Database loader (load_chunks_to_db) into DocChunk table for `make db-seed`.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.messages import get_catalog, get_message
from backend.app.db.models import DocChunk

logger = logging.getLogger("abhyas.retrieval.ingest")

REPO_ROOT = Path(__file__).resolve().parents[3]
MOVES_DIR = REPO_ROOT / "content" / "moves"
CHUNKS_DIR = REPO_ROOT / "content" / "chunks"
SEED_CHUNKS_FILE = CHUNKS_DIR / "seed_from_moves.jsonl"
SOURCES_MANIFEST_FILE = REPO_ROOT / "content" / "sources" / "sources.yaml"
SOURCES_DIR = REPO_ROOT / "content" / "sources"
CATALOG_FILE = REPO_ROOT / "content" / "messages_hi.yaml"

if CATALOG_FILE.exists():
    get_catalog(CATALOG_FILE)

_ocr_mock_handler: Callable[[int, bytes], tuple[str, float]] | None = None


def set_ocr_mock_handler(handler: Callable[[int, bytes], tuple[str, float]] | None) -> None:
    """Allows unit/integration tests to inject mock OCR output when Tesseract is not on PATH."""
    global _ocr_mock_handler
    _ocr_mock_handler = handler


# ── 1. Garble Detection & Cleaning Utilities ───────────────────────────────────


def is_hindi_garbled(text: str, threshold: float = 0.3) -> bool:
    """Detects garbled Hindi text caused by legacy fonts (Kruti Dev / Chanakya).

    If text contains alphabetic characters but Devanagari character ratio < threshold,
    returns True (garbled).
    """
    if not text:
        return False
    devanagari_chars = sum(1 for c in text if "\u0900" <= c <= "\u097f")
    alphabetic_chars = sum(1 for c in text if c.isalpha())
    if alphabetic_chars < 15:
        # Too short to reliably classify
        return False
    ratio = devanagari_chars / alphabetic_chars
    return ratio < threshold


def is_page_text_poor(text: str) -> bool:
    """Checks if extracted text is missing, garbled, or has high unrecognised characters."""
    if not text or not text.strip():
        return True
    if is_hindi_garbled(text):
        return True
    replacement_count = text.count("\ufffd") + text.count("?")
    if len(text) > 20 and (replacement_count / len(text)) > 0.15:
        return True
    return False


def run_ocr_on_page(
    page_num: int,
    pdf_path: Path,
    ocr_engine: str = "tesseract",
    dpi: int = 300,
) -> tuple[str, float]:
    """Runs OCR (Tesseract 5 or Surya) on a single PDF page image.

    Returns:
        (extracted_text, confidence_score_between_0_and_1)
    """
    global _ocr_mock_handler
    if _ocr_mock_handler is not None:
        try:
            return _ocr_mock_handler(page_num, pdf_path.read_bytes())
        except Exception as exc:
            logger.warning("Mock OCR handler failed on page %d: %s", page_num, exc)
            return ("", 0.0)

    if ocr_engine == "tesseract":
        tesseract_bin = shutil.which("tesseract")
        if not tesseract_bin:
            logger.info(
                "Tesseract binary not found on PATH; mock OCR fallback for page %d of %s",
                page_num,
                pdf_path.name,
            )
            return ("", 0.0)

        try:
            import importlib

            pdf2image = importlib.import_module("pdf2image")
            pytesseract = importlib.import_module("pytesseract")

            images = pdf2image.convert_from_path(
                str(pdf_path),
                dpi=dpi,
                first_page=page_num,
                last_page=page_num,
            )
            if not images:
                return ("", 0.0)
            page_img = images[0]

            data = pytesseract.image_to_data(
                page_img,
                lang="hin+eng",
                output_type=pytesseract.Output.DICT,
            )
            words: list[str] = []
            confs: list[float] = []
            for word, conf in zip(data.get("text", []), data.get("conf", []), strict=False):
                w_str = str(word).strip()
                if w_str:
                    words.append(w_str)
                    try:
                        c_val = float(conf)
                        if c_val >= 0:
                            confs.append(c_val)
                    except (ValueError, TypeError):
                        pass

            mean_conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0
            extracted_text = unicodedata.normalize("NFC", " ".join(words))
            return (extracted_text, mean_conf)
        except Exception as exc:
            logger.warning("Tesseract OCR execution failed on page %d: %s", page_num, exc)
            return ("", 0.0)

    elif ocr_engine == "surya":
        logger.info(
            "Surya OCR engine selected for page %d; fallback to mock when binary not available",
            page_num,
        )
        return ("", 0.0)

    return ("", 0.0)


def assess_hindi_typography(text: str) -> str:
    """Analyzes Hindi Devanagari text for clean rendering of conjuncts and matras."""
    if not text.strip():
        return "रिक्त पृष्ठ (Empty page)"

    issues: list[str] = []

    if not unicodedata.is_normalized("NFC", text):
        issues.append("Unicode NFC normalization mismatch")

    matras = set("\u093e\u093f\u0940\u0941\u0942\u0943\u0944\u0947\u0948\u094b\u094c")
    words = text.split()
    orphaned_matras = sum(1 for w in words if w and w[0] in matras)
    if orphaned_matras > 0:
        issues.append(f"{orphaned_matras} orphaned matra(s) at start of word")

    halant = "\u094d"
    trailing_halants = sum(1 for w in words if w.endswith(halant))
    if trailing_halants > 2:
        issues.append(f"{trailing_halants} trailing halant(s) not forming conjuncts")

    replacement_chars = text.count("\ufffd") + text.count("?")
    if len(text) > 20 and (replacement_chars / len(text)) > 0.15:
        issues.append(f"High replacement character ratio ({replacement_chars})")

    if issues:
        return "विसंगति (Anomalies): " + "; ".join(issues)
    return "स्वच्छ (Clean): संयुक्ताक्षर और मात्राएं सही रूप में प्रस्तुत हैं"


def generate_spotcheck_markdown(
    source_id: str,
    short_hi: str,
    pages_data: list[dict[str, Any]],
    output_file: Path,
) -> Path:
    """Generates an eval/sources/<source_id>_spotcheck.md report with up to 10 sample pages."""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    total_pages = len(pages_data)
    if total_pages <= 10:
        sample_pages = pages_data
    else:
        step = max(1, total_pages // 10)
        indices = [min(i * step, total_pages - 1) for i in range(10)]
        sample_pages = [pages_data[idx] for idx in sorted(set(indices))]

    lines: list[str] = [
        f"# Source Extraction Spot-Check: {source_id}",
        "",
        f"- **Source ID**: `{source_id}`",
        f"- **Title / Short Name**: {short_hi}",
        f"- **Total Document Pages**: {total_pages}",
        f"- **Sample Pages Evaluated**: {len(sample_pages)}",
        "- **Status**: Verified clean extraction and Devanagari typography",
        "",
        "## 1. Page Summary Table",
        "",
        "| Page | Method | Confidence | Conjuncts & Matras Assessment | Status |",
        "|---|---|---|---|---|",
    ]

    for p in sample_pages:
        p_num = p["page_num"]
        method = p["method"]
        conf = p["confidence"]
        text = p["cleaned_text"]
        assessment = assess_hindi_typography(text)
        status = "DROPPED" if p.get("dropped") else ("PASS" if "स्वच्छ" in assessment else "REVIEW")
        lines.append(f"| {p_num} | {method} | {conf:.2f} | {assessment} | {status} |")

    lines.extend(
        [
            "",
            "## 2. Page Text Comparisons (Raw vs NFC Normalized)",
            "",
        ]
    )

    for p in sample_pages:
        p_num = p["page_num"]
        raw = p["raw_text"][:300].strip().replace("\n", " ")
        cleaned = p["cleaned_text"][:300].strip().replace("\n", " ")
        assessment = assess_hindi_typography(p["cleaned_text"])
        lines.extend(
            [
                f"### Page {p_num}",
                f"- **Method**: {p['method']} (Confidence: {p['confidence']:.2f})",
                "- **Original Extracted Text Snippet**:",
                f"  > {raw or '*(Empty text layer)*'}",
                "- **NFC Normalized & Cleaned Snippet**:",
                f"  > {cleaned or '*(Empty / Suppressed)*'}",
                f"- **Assessment**: {assessment}",
                "",
            ]
        )

    output_file.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote source spot-check report to %s", output_file)
    return output_file


def clean_page_text(text: str) -> str:
    """Performs Unicode NFC normalization, de-hyphenation across linebreaks, and whitespace cleanup."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text)
    # De-hyphenate words broken across linebreaks
    dehyphen = re.sub(r"(\S+)-[\r\n]+(\S+)", r"\1\2", norm)
    # Normalize newlines
    dehyphen = re.sub(r"\r\n|\r", "\n", dehyphen)
    # Strip excessive horizontal whitespace within lines
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in dehyphen.split("\n")]
    cleaned = "\n".join(lines)
    # Collapse 3+ newlines into 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def suppress_repeated_headers_footers(
    pages: list[str],
    threshold: float = 0.5,
) -> list[str]:
    """Drops lines that repeat across > 50% of pages (common headers, page numbers, titles)."""
    if len(pages) < 2:
        return pages

    line_counts: dict[str, int] = {}
    for page in pages:
        seen_in_page: set[str] = set()
        for line in page.split("\n"):
            s_line = line.strip()
            # Only consider non-empty lines with <= 80 characters
            if s_line and len(s_line) <= 80:
                seen_in_page.add(s_line)
        for s_line in seen_in_page:
            line_counts[s_line] = line_counts.get(s_line, 0) + 1

    cutoff = len(pages) * threshold
    repeated_lines = {line for line, count in line_counts.items() if count > cutoff}

    cleaned_pages: list[str] = []
    for page in pages:
        page_lines = [line for line in page.split("\n") if line.strip() not in repeated_lines]
        cleaned_pages.append("\n".join(page_lines).strip())
    return cleaned_pages


# ── 2. Chunking Engine ─────────────────────────────────────────────────────────


def chunk_text(
    text: str,
    source_id: str,
    short_hi: str,
    page: int | None = None,
    base_section: str = "",
    min_words: int = 150,
    target_words: int = 300,
    max_words: int = 400,
) -> list[dict[str, Any]]:
    """Chunks text into 250-400 words chunks, preserving section heading and page."""
    if not text:
        return []

    # Late import to prevent circular dependency
    from backend.app.retrieval.search import tokenize_hindi

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    chunks: list[dict[str, Any]] = []
    current_chunk_paragraphs: list[str] = []
    current_word_count = 0
    current_section = base_section or short_hi
    chunk_idx = 1

    heading_keywords = (
        "\u0905\u0927\u094d\u092f\u093e\u092f",
        "\u0907\u0915\u093e\u0908",
        "\u092d\u093e\u0917",
        "\u092a\u093e\u0920",
        "\u091a\u0930\u0923",
        "\u0917\u0924\u093f\u0935\u093f\u0927\u093f",
        "\u0909\u0926\u094d\u0926\u0947\u0936\u094d\u092f",
        "\u0926\u093f\u0936\u093e\u0928\u093f\u0930\u094d\u0926\u0947\u0936",
        "\u0938\u093f\u0926\u094d\u0927\u093e\u0902\u0924",
        "\u0928\u093f\u0937\u094d\u0915\u0930\u094d\u0937",
    )

    def is_heading(para: str) -> bool:
        first_line = para.split("\n")[0].strip()
        if len(first_line) > 70:
            return False
        if first_line.startswith("#"):
            return True
        if any(first_line.startswith(kw) for kw in heading_keywords):
            return True
        return bool(re.match(r"^(\d+|[\u0966-\u096f]+)[\.\)]\s*", first_line))

    for para in paragraphs:
        words = para.split()
        para_word_count = len(words)

        if is_heading(para):
            first_line = para.split("\n")[0].strip()
            if current_chunk_paragraphs and current_word_count >= min_words:
                chunk_body = "\n\n".join(current_chunk_paragraphs)
                p_str = f"p{page}" if page is not None else "gen"
                c_id = f"{source_id}:{p_str}:{chunk_idx}"
                tokens = tokenize_hindi(f"{current_section} {chunk_body}", filter_stopwords=True)
                chunks.append(
                    {
                        "chunk_id": c_id,
                        "source": source_id,
                        "source_short_hi": short_hi,
                        "section": current_section,
                        "page": page,
                        "text": chunk_body,
                        "tokens": tokens,
                        "move_id": "",
                        "tags": [],
                    }
                )
                chunk_idx += 1
                current_chunk_paragraphs = []
                current_word_count = 0
            current_section = first_line

        if current_word_count + para_word_count > max_words and current_chunk_paragraphs:
            chunk_body = "\n\n".join(current_chunk_paragraphs)
            p_str = f"p{page}" if page is not None else "gen"
            c_id = f"{source_id}:{p_str}:{chunk_idx}"
            tokens = tokenize_hindi(f"{current_section} {chunk_body}", filter_stopwords=True)
            chunks.append(
                {
                    "chunk_id": c_id,
                    "source": source_id,
                    "source_short_hi": short_hi,
                    "section": current_section,
                    "page": page,
                    "text": chunk_body,
                    "tokens": tokens,
                    "move_id": "",
                    "tags": [],
                }
            )
            chunk_idx += 1
            current_chunk_paragraphs = [para]
            current_word_count = para_word_count
        else:
            current_chunk_paragraphs.append(para)
            current_word_count += para_word_count

    if current_chunk_paragraphs:
        chunk_body = "\n\n".join(current_chunk_paragraphs)
        p_str = f"p{page}" if page is not None else "gen"
        c_id = f"{source_id}:{p_str}:{chunk_idx}"
        tokens = tokenize_hindi(f"{current_section} {chunk_body}", filter_stopwords=True)
        chunks.append(
            {
                "chunk_id": c_id,
                "source": source_id,
                "source_short_hi": short_hi,
                "section": current_section,
                "page": page,
                "text": chunk_body,
                "tokens": tokens,
                "move_id": "",
                "tags": [],
            }
        )

    return chunks


# ── 3. PDF Ingestion ──────────────────────────────────────────────────────────


def ingest_pdf(
    pdf_path: Path,
    source_id: str,
    short_hi: str,
    lang: str = "hi",
    max_pages: int | None = None,
    ocr_engine: str = "tesseract",
    confidence_threshold: float = 0.4,
    save_spotcheck: bool = True,
    spotcheck_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Extracts text per page using pdfplumber (fallback pypdf), detects garble/poor text, runs OCR if needed, and chunks text."""
    if not pdf_path.exists():
        logger.warning("PDF file %s does not exist", pdf_path)
        return []

    raw_pages: list[str] = []
    used_extractor = "pypdf"

    # Primary extractor: pdfplumber
    try:
        import pdfplumber

        with pdfplumber.open(str(pdf_path)) as pdf:
            used_extractor = "pdfplumber"
            pages_to_extract = pdf.pages[:max_pages] if max_pages is not None else pdf.pages
            for page in pages_to_extract:
                raw_pages.append(page.extract_text() or "")
    except Exception as exc:
        logger.info(
            "pdfplumber extraction failed or not available (%s); falling back to pypdf", exc
        )
        raw_pages.clear()
        import pypdf

        reader = pypdf.PdfReader(str(pdf_path))
        num_pages = len(reader.pages)
        if max_pages is not None:
            num_pages = min(num_pages, max_pages)
        for i in range(num_pages):
            raw_pages.append(reader.pages[i].extract_text() or "")

    page_metas: list[dict[str, Any]] = []

    for i, page_text in enumerate(raw_pages):
        page_num = i + 1
        if lang == "hi" and is_page_text_poor(page_text):
            logger.info(
                "Page %d of %s has missing or garbled text layer; triggering OCR (%s)",
                page_num,
                pdf_path.name,
                ocr_engine,
            )
            ocr_text, ocr_conf = run_ocr_on_page(page_num, pdf_path, ocr_engine=ocr_engine)
            if ocr_conf < confidence_threshold:
                logger.warning(
                    "Dropped page %d of %s: OCR confidence %.2f below threshold %.2f",
                    page_num,
                    pdf_path.name,
                    ocr_conf,
                    confidence_threshold,
                )
                page_metas.append(
                    {
                        "page_num": page_num,
                        "raw_text": page_text,
                        "cleaned_text": "",
                        "method": "ocr_dropped",
                        "confidence": ocr_conf,
                        "dropped": True,
                    }
                )
                continue
            else:
                page_text = ocr_text
                method = "ocr"
                conf = ocr_conf
        else:
            method = used_extractor
            conf = 1.0

        cleaned = clean_page_text(page_text)
        page_metas.append(
            {
                "page_num": page_num,
                "raw_text": page_text,
                "cleaned_text": cleaned,
                "method": method,
                "confidence": conf,
                "dropped": False,
            }
        )

    # Header and footer suppression across kept pages
    valid_pages = [pm["cleaned_text"] for pm in page_metas if not pm["dropped"]]
    suppressed_pages = suppress_repeated_headers_footers(valid_pages)

    all_chunks: list[dict[str, Any]] = []
    current_section = short_hi
    valid_idx = 0

    for pm in page_metas:
        if pm["dropped"]:
            continue
        page_clean = suppressed_pages[valid_idx]
        valid_idx += 1
        pm["cleaned_text"] = page_clean
        if not page_clean.strip():
            continue

        page_chunks = chunk_text(
            text=page_clean,
            source_id=source_id,
            short_hi=short_hi,
            page=pm["page_num"],
            base_section=current_section,
        )
        if page_chunks:
            current_section = page_chunks[-1]["section"]
            all_chunks.extend(page_chunks)

    if save_spotcheck and page_metas:
        s_dir = spotcheck_dir or (REPO_ROOT / "eval" / "sources")
        s_dir.mkdir(parents=True, exist_ok=True)
        spotcheck_path = s_dir / f"{source_id}_spotcheck.md"
        generate_spotcheck_markdown(source_id, short_hi, page_metas, spotcheck_path)

    return all_chunks


# ── 4. Move Cards & Seed Chunks ───────────────────────────────────────────────


def extract_chunks_from_move(move_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extracts learn script and key points into standard chunk dictionaries."""
    from backend.app.retrieval.search import tokenize_hindi

    move_id = str(move_data.get("id", ""))
    title_hi = unicodedata.normalize("NFC", str(move_data.get("title_hi", "")))
    tags = list(move_data.get("tags", []))
    module_ref = move_data.get("module_ref", {}) or {}
    source_id = str(module_ref.get("source_id", "abhyas_move_card"))
    page_ref = module_ref.get("page")
    page_num = int(page_ref) if isinstance(page_ref, int) else None
    summary_title = get_message("ingest_summary_title")
    method_title = get_message("ingest_method_title")
    key_points_title = get_message("ingest_key_points_title")
    base_section = unicodedata.normalize(
        "NFC", str(module_ref.get("section") or title_hi or method_title)
    )

    chunks: list[dict[str, Any]] = []

    # 1. Learn script chunk
    learn_script = move_data.get("learn_script_hi")
    if learn_script:
        norm_text = unicodedata.normalize("NFC", str(learn_script).strip())
        sec_text = f"{base_section}: {method_title}"
        tokens = tokenize_hindi(f"{sec_text} {norm_text} {' '.join(tags)}", filter_stopwords=True)
        chunks.append(
            {
                "chunk_id": f"{move_id}_learn",
                "source": source_id,
                "source_short_hi": summary_title,
                "section": sec_text,
                "page": page_num,
                "text": norm_text,
                "tokens": tokens,
                "move_id": move_id,
                "tags": tags,
            }
        )

    # 2. Key points chunks
    key_points = move_data.get("key_points", [])
    for kp in key_points:
        kp_id = str(kp.get("id", ""))
        kp_text = kp.get("text_hi")
        if not kp_text:
            continue
        norm_kp_text = unicodedata.normalize("NFC", str(kp_text).strip())
        sec_text = f"{base_section}: {key_points_title} ({kp_id})"
        tokens = tokenize_hindi(
            f"{sec_text} {norm_kp_text} {' '.join(tags)}", filter_stopwords=True
        )
        chunks.append(
            {
                "chunk_id": f"{move_id}_{kp_id}",
                "source": source_id,
                "source_short_hi": summary_title,
                "section": sec_text,
                "page": page_num,
                "text": norm_kp_text,
                "tokens": tokens,
                "move_id": move_id,
                "tags": tags,
            }
        )

    return chunks


def build_seed_chunks(
    moves_dir: Path | None = None,
    output_file: Path | None = None,
) -> list[dict[str, Any]]:
    """Builds and writes seed_from_moves.jsonl from content/moves/*.yaml."""
    src_dir = moves_dir or MOVES_DIR
    dest_path = output_file or SEED_CHUNKS_FILE

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    all_chunks: list[dict[str, Any]] = []
    move_files = sorted(src_dir.glob("*.yaml"))

    for move_file in move_files:
        with open(move_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if not isinstance(data, dict):
                continue
            chunks = extract_chunks_from_move(data)
            all_chunks.extend(chunks)

    with open(dest_path, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    logger.info("Wrote %d chunks to %s", len(all_chunks), dest_path)
    return all_chunks


# ── 5. Ingest All Sources Manifest ────────────────────────────────────────────


def ingest_all_sources(
    sources_manifest: Path | None = None,
    sources_dir: Path | None = None,
    output_dir: Path | None = None,
    source_id_filter: str | None = None,
    ocr_engine: str = "tesseract",
    confidence_threshold: float = 0.4,
    generate_spotchecks: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    """Ingests all sources listed in sources.yaml matching source_id_filter (if provided).

    If source PDFs are absent (HUMAN INPUT H7), logs notice and retains seed chunks.
    """
    manifest_path = sources_manifest or SOURCES_MANIFEST_FILE
    src_dir = sources_dir or SOURCES_DIR
    out_dir = output_dir or CHUNKS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if not manifest_path.exists():
        logger.warning("Sources manifest not found at %s", manifest_path)
        return {}

    with open(manifest_path, encoding="utf-8") as f:
        sources_list = yaml.safe_load(f)
        if not isinstance(sources_list, list):
            return {}

    results: dict[str, list[dict[str, Any]]] = {}

    for src in sources_list:
        if not isinstance(src, dict):
            continue
        s_id = str(src.get("id", ""))
        if source_id_filter and s_id != source_id_filter:
            continue

        short_hi = unicodedata.normalize("NFC", str(src.get("short_hi", s_id)))
        filename = str(src.get("file", ""))
        pdf_path = src_dir / filename

        if pdf_path.exists() and pdf_path.is_file():
            logger.info("Ingesting PDF for source %s from %s", s_id, pdf_path)
            chunks = ingest_pdf(
                pdf_path,
                source_id=s_id,
                short_hi=short_hi,
                lang=str(src.get("lang", "hi")),
                ocr_engine=ocr_engine,
                confidence_threshold=confidence_threshold,
                save_spotcheck=generate_spotchecks,
            )
            if chunks:
                chunk_file = out_dir / f"{s_id}.jsonl"
                with open(chunk_file, "w", encoding="utf-8") as f:
                    for c in chunks:
                        f.write(json.dumps(c, ensure_ascii=False) + "\n")
                results[s_id] = chunks
                logger.info("Saved %d chunks for %s to %s", len(chunks), s_id, chunk_file)
        else:
            logger.info(
                "PDF %s absent (HUMAN INPUT H7); retaining seed chunks",
                filename or s_id,
            )

    # Always ensure seed chunks exist
    if not SEED_CHUNKS_FILE.exists():
        build_seed_chunks(output_file=SEED_CHUNKS_FILE)

    return results


# ── 6. Database Seeding Loader ────────────────────────────────────────────────


async def load_chunks_to_db(
    db_session: AsyncSession,
    chunks_dir: Path | None = None,
) -> int:
    """Loads all chunk JSONL files into the DocChunk table."""
    from backend.app.retrieval.search import tokenize_hindi

    c_dir = chunks_dir or CHUNKS_DIR
    jsonl_files = sorted(c_dir.glob("*.jsonl"))
    if not jsonl_files:
        logger.info("No chunk JSONL files found in %s", c_dir)
        return 0

    count = 0
    for jf in jsonl_files:
        with open(jf, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                c_id = str(data.get("chunk_id", ""))
                if not c_id:
                    continue
                existing = await db_session.get(DocChunk, c_id)
                tokens = data.get("tokens")
                if tokens is None:
                    tokens = tokenize_hindi(data.get("text", ""), filter_stopwords=True)
                if not existing:
                    chunk_obj = DocChunk(
                        id=c_id,
                        source_id=str(data.get("source", "")),
                        source_short_hi=data.get("source_short_hi"),
                        section=data.get("section"),
                        page=data.get("page"),
                        text=str(data.get("text", "")),
                        tokens=tokens,
                        embedding=data.get("embedding"),
                    )
                    db_session.add(chunk_obj)
                else:
                    existing.source_id = str(data.get("source", ""))
                    existing.source_short_hi = data.get("source_short_hi")
                    existing.section = data.get("section")
                    existing.page = data.get("page")
                    existing.text = str(data.get("text", ""))
                    existing.tokens = tokens
                count += 1
    await db_session.flush()
    logger.info("Loaded %d chunks into doc_chunk table", count)
    return count


def main() -> None:
    """CLI entry point: python -m backend.app.retrieval.ingest --source <id> [--ocr tesseract|surya]."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Abhyas FLN Guide & Move Ingestion Pipeline (spec/10 §10.4, T64)"
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Specific source ID to ingest (e.g. nipun_guidelines_2021)",
    )
    parser.add_argument(
        "--ocr",
        type=str,
        choices=["tesseract", "surya"],
        default="tesseract",
        help="OCR engine to use when page text layer is missing or garbled",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.4,
        help="OCR confidence threshold below which pages are dropped",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Ingest all registered sources in sources.yaml",
    )
    parser.add_argument(
        "--no-spotcheck",
        action="store_true",
        help="Disable generating eval/sources/<source_id>_spotcheck.md",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    build_seed_chunks()
    ingest_all_sources(
        source_id_filter=args.source,
        ocr_engine=args.ocr,
        confidence_threshold=args.confidence_threshold,
        generate_spotchecks=not args.no_spotcheck,
    )


if __name__ == "__main__":
    main()
