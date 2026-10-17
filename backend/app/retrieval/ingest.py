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
import unicodedata
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


def clean_page_text(text: str) -> str:
    """Performs Unicode NFC normalization, de-hyphenation across linebreaks, and whitespace cleanup."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text)
    # De-hyphenate words broken across linebreaks (e.g. "गति-\nविधि" -> "गतिविधि")
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
        "अध्याय",
        "इकाई",
        "भाग",
        "पाठ",
        "चरण",
        "गतिविधि",
        "उद्देश्य",
        "दिशानिर्देश",
        "सिद्धांत",
        "निष्कर्ष",
    )

    def is_heading(para: str) -> bool:
        first_line = para.split("\n")[0].strip()
        if len(first_line) > 70:
            return False
        if first_line.startswith("#"):
            return True
        if any(first_line.startswith(kw) for kw in heading_keywords):
            return True
        return bool(re.match(r"^(\d+|[०-९]+)[\.\)]\s*", first_line))

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
) -> list[dict[str, Any]]:
    """Extracts text per page from a PDF with pypdf, detects garble, and chunks text."""
    if not pdf_path.exists():
        logger.warning("PDF file %s does not exist", pdf_path)
        return []

    import pypdf

    reader = pypdf.PdfReader(str(pdf_path))
    raw_pages: list[str] = []
    num_pages = len(reader.pages)
    if max_pages is not None:
        num_pages = min(num_pages, max_pages)

    for i in range(num_pages):
        page = reader.pages[i]
        page_text = page.extract_text() or ""
        raw_pages.append(page_text)

    # Check for garbled Hindi pages (potential legacy font issue)
    for i, page_text in enumerate(raw_pages):
        if lang == "hi" and is_hindi_garbled(page_text):
            logger.warning(
                "Garbled Hindi text detected on page %d of %s (Devanagari ratio < 0.3, possible legacy font)",
                i + 1,
                pdf_path.name,
            )

    # Header and footer suppression across pages
    suppressed_pages = suppress_repeated_headers_footers(raw_pages)

    all_chunks: list[dict[str, Any]] = []
    current_section = short_hi

    for i, page_raw in enumerate(suppressed_pages):
        page_num = i + 1
        cleaned = clean_page_text(page_raw)
        if not cleaned:
            continue
        page_chunks = chunk_text(
            text=cleaned,
            source_id=source_id,
            short_hi=short_hi,
            page=page_num,
            base_section=current_section,
        )
        if page_chunks:
            current_section = page_chunks[-1]["section"]
            all_chunks.extend(page_chunks)

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
) -> dict[str, list[dict[str, Any]]]:
    """Ingests all sources listed in sources.yaml.

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_seed_chunks()
    ingest_all_sources()
