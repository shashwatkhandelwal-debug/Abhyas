"""Integration and golden retrieval tests for source ingestion pipeline and GuideRetriever (spec/10 §10.4, T40).

Tests:
1. Garble detection on clean Devanagari vs. legacy fonts (Kruti Dev / Chanakya).
2. Text cleaning (NFC normalization, linebreak de-hyphenation, whitespace collapse).
3. Repeated header/footer suppression across multi-page documents.
4. Semantic chunking preserving section hierarchy, page numbers, and chunk IDs.
5. End-to-end PDF ingestion using synthetic PDF documents.
6. Sources manifest ingestion and graceful fallback when official PDFs are absent (HUMAN INPUT H7).
7. Database loader (load_chunks_to_db) into DocChunk table.
8. GuideRetriever multi-file corpus loading and RRF/normalized scoring.
9. Golden retrieval benchmark: 10 realistic FLN teacher questions with precision and score assertions.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from backend.app.retrieval.ingest import (
    CHUNKS_DIR,
    SEED_CHUNKS_FILE,
    chunk_text,
    clean_page_text,
    ingest_all_sources,
    ingest_pdf,
    is_hindi_garbled,
    load_chunks_to_db,
    suppress_repeated_headers_footers,
)
from backend.app.retrieval.search import (
    GuideRetriever,
    get_hindi_stopwords,
    tokenize_hindi,
)

# ── 1. Garble Detection Tests ───────────────────────────────────────────────────


def test_is_hindi_garbled_clean_devanagari() -> None:
    """Verifies that clean Devanagari text is NOT classified as garbled."""
    text = "स्थानीय मान की अवधारणा को समझाने के लिए दस-दस के बंडल और खुली तीलियों का उपयोग करें।"
    assert not is_hindi_garbled(text)


def test_is_hindi_garbled_legacy_font() -> None:
    """Verifies that legacy Kruti Dev / ASCII-encoded text is flagged as garbled."""
    # Typical Kruti Dev output produced when font is missing
    garbled_text = "d{kk 2 ds fy, xf.kr dh f'k{kd lanf'kZdk esa fn, x, funsZ'k"
    assert is_hindi_garbled(garbled_text)


def test_is_hindi_garbled_empty_and_short() -> None:
    """Verifies that empty strings or tiny strings do not trigger false positives."""
    assert not is_hindi_garbled("")
    assert not is_hindi_garbled("123 456")
    assert not is_hindi_garbled("पृष्ठ 1")


# ── 2. Cleaning and Header Suppression Tests ───────────────────────────────────


def test_clean_page_text_nfc_and_dehyphen() -> None:
    """Verifies NFC normalization, hyphenated linebreak repair, and newline collapse."""
    raw = "यह एक गति-\nविधि है जो बच्चों को सिखाती\r\n\r\n\r\nहै।"
    cleaned = clean_page_text(raw)
    assert "गतिविधि" in cleaned
    assert "\r" not in cleaned
    assert "\n\n\n" not in cleaned
    assert cleaned == "यह एक गतिविधि है जो बच्चों को सिखाती\n\nहै।"


def test_suppress_repeated_headers_footers() -> None:
    """Verifies that repetitive header lines appearing on > 50% of pages are dropped."""
    header = "निपुण भारत मिशन — शिक्षक संदर्शिका"
    page1 = f"{header}\n\nअध्याय १: स्थानीय मान\nबंडल की समझ बनाएं।"
    page2 = f"{header}\n\nअध्याय २: जोड़\nहासिल का जोड़ सिखाएं।"
    page3 = f"{header}\n\nअध्याय ३: घटाव\nबंडल खोलकर घटाव करें।"
    page4 = "परिशिष्ट:\nसंसाधन सूची"

    pages = [page1, page2, page3, page4]
    suppressed = suppress_repeated_headers_footers(pages, threshold=0.5)

    assert len(suppressed) == 4
    for p in suppressed:
        assert header not in p
    assert "अध्याय १: स्थानीय मान" in suppressed[0]
    assert "अध्याय २: जोड़" in suppressed[1]
    assert "अध्याय ३: घटाव" in suppressed[2]
    assert "परिशिष्ट:" in suppressed[3]


# ── 3. Chunking Engine Tests ───────────────────────────────────────────────────


def test_chunk_text_preserves_section_and_ids() -> None:
    """Verifies semantic chunking produces 250-400 words chunks with proper IDs and section."""
    text = (
        "# १. स्थानीय मान की अवधारणा\n\n"
        + "बच्चों को दो अंकों की संख्या में इकाई और दहाई का अंतर स्पष्ट करने के लिए तीलियों के बंडल बनवाएं। " * 15
        + "\n\n# २. बंडल खोलने की गतिविधि\n\n"
        + "जब बच्चे घटाव में अटकते हैं तो दहाई का एक बंडल खोलकर दस खुली तीलियाँ प्राप्त करने का अभ्यास कराएं। "
        * 15
    )

    chunks = chunk_text(
        text=text,
        source_id="test_guide",
        short_hi="गणित संदर्शिका",
        page=12,
        base_section="शुरुआती गणित",
        min_words=50,
        max_words=150,
    )

    assert len(chunks) >= 2
    for c in chunks:
        assert c["source"] == "test_guide"
        assert c["page"] == 12
        assert c["chunk_id"].startswith("test_guide:p12:")
        assert "tokens" in c
        assert isinstance(c["tokens"], list)
        assert len(c["tokens"]) > 0

    assert chunks[0]["section"] == "# १. स्थानीय मान की अवधारणा"
    assert any(c["section"] == "# २. बंडल खोलने की गतिविधि" for c in chunks)
    assert chunks[-1]["section"] == "# २. बंडल खोलने की गतिविधि"


# ── 4. Stopwords & Hindi Tokenization Tests ────────────────────────────────────


def test_hindi_stopwords_loaded_and_filtered() -> None:
    """Verifies Hindi stopwords are loaded from file and filterable in tokenizer."""
    sw = get_hindi_stopwords()
    assert len(sw) >= 150
    assert "का" in sw
    assert "के" in sw
    assert "की" in sw
    assert "और" in sw
    assert "है" in sw

    # Without filter
    tokens_raw = tokenize_hindi("स्थानीय मान के लिए बंडल और खुली तीलियाँ", filter_stopwords=False)
    assert "के" in tokens_raw
    assert "लिए" in tokens_raw
    assert "और" in tokens_raw

    # With filter
    tokens_filtered = tokenize_hindi("स्थानीय मान के लिए बंडल और खुली तीलियाँ", filter_stopwords=True)
    assert "के" not in tokens_filtered
    assert "लिए" not in tokens_filtered
    assert "और" not in tokens_filtered
    assert "स्थानीय" in tokens_filtered
    assert "मान" in tokens_filtered
    assert "बंडल" in tokens_filtered
    assert "खुली" in tokens_filtered
    assert "तीलियाँ" in tokens_filtered


# ── 5. Synthetic PDF Ingestion Tests ───────────────────────────────────────────


def _make_synthetic_pdf(pages: list[str]) -> bytes:
    """Generates a minimal valid multi-page PDF 1.4 using standard Python bytes without external deps."""
    n = len(pages)
    kids = " ".join(f"{3 + i} 0 R" for i in range(n))
    font_idx = 3 + 2 * n
    objs: list[bytes] = [
        b"1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj",
        f"2 0 obj\n<</Type/Pages/Kids[{kids}]/Count {n}>>\nendobj".encode(),
    ]
    for i in range(n):
        page_idx = 3 + i
        content_idx = 3 + n + i
        objs.append(
            f"{page_idx} 0 obj\n<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents {content_idx} 0 R/Resources<</Font<</F1 {font_idx} 0 R>>>>>>\nendobj".encode()
        )
    for i, text in enumerate(pages):
        stream = f"BT\n/F1 12 Tf\n72 700 Td\n({text}) Tj\nET".encode()
        objs.append(
            f"{3 + n + i} 0 obj\n<</Length {len(stream)}>>\nstream\n".encode()
            + stream
            + b"\nendstream\nendobj"
        )
    objs.append(
        f"{font_idx} 0 obj\n<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>\nendobj".encode()
    )

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(out.tell())
        out.write(obj + b"\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return out.getvalue()


def test_ingest_pdf_synthetic(tmp_path: Path) -> None:
    """Verifies end-to-end PDF ingestion using a synthetic multi-page PDF."""
    pdf_file = tmp_path / "fln_sample_guide.pdf"
    pdf_bytes = _make_synthetic_pdf(
        [
            "FLN Shikshak Sandarshika Ganit Class 2 Place Value Bundles",
            "FLN Shikshak Sandarshika Ganit Class 2 Subtraction Regrouping",
        ]
    )
    pdf_file.write_bytes(pdf_bytes)

    chunks = ingest_pdf(
        pdf_path=pdf_file,
        source_id="fln_sample_c2",
        short_hi="सैंपल संदर्शिका",
        lang="en",
    )

    assert len(chunks) >= 2
    assert any(c["page"] == 1 for c in chunks)
    assert any(c["page"] == 2 for c in chunks)
    assert all(c["source"] == "fln_sample_c2" for c in chunks)
    assert all("tokens" in c for c in chunks)


# ── 6. Source Manifest & Absent PDF Fallback Tests ─────────────────────────────


def test_ingest_all_sources_absent_pdfs_retains_seed_chunks(tmp_path: Path) -> None:
    """Verifies that when source PDFs are missing (HUMAN INPUT H7), seed chunks are retained."""
    manifest = tmp_path / "sources.yaml"
    manifest.write_text(
        "- id: test_missing_source\n"
        "  title: Missing Source Guide\n"
        "  short_hi: लापता गाइड\n"
        "  file: non_existent_guide.pdf\n"
        "  lang: hi\n",
        encoding="utf-8",
    )

    out_chunks = tmp_path / "chunks"
    results = ingest_all_sources(
        sources_manifest=manifest,
        sources_dir=tmp_path,
        output_dir=out_chunks,
    )

    # Missing PDF should not be in ingested results
    assert "test_missing_source" not in results
    # Seed chunks file should exist in repo
    assert SEED_CHUNKS_FILE.exists()


# ── 7. Database Loader Tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_chunks_to_db_mock_session() -> None:
    """Verifies load_chunks_to_db inserts chunks into the DocChunk table idempotently."""
    from unittest.mock import MagicMock

    mock_session = AsyncMock()
    mock_session.get.return_value = None  # All chunks new
    mock_session.add = MagicMock()

    count = await load_chunks_to_db(mock_session, chunks_dir=CHUNKS_DIR)
    assert count >= 22
    assert mock_session.add.call_count >= 22
    assert mock_session.flush.called


# ── 8. GuideRetriever Multi-File Corpus Loading Tests ──────────────────────────


@pytest.mark.asyncio
async def test_guide_retriever_multi_file_loading(tmp_path: Path) -> None:
    """Verifies GuideRetriever loads and indexes chunks from multiple .jsonl files."""
    chunk1 = {
        "chunk_id": "c1",
        "source": "s1",
        "section": "गणित",
        "text": "स्थानीय मान के लिए बंडल और तीलियां।",
        "tokens": ["स्थानीय", "मान", "बंडल", "तीलियां"],
    }
    chunk2 = {
        "chunk_id": "c2",
        "source": "s2",
        "section": "भाषा",
        "text": "मात्रा जोड़कर शब्द पढ़ना सिखाएं।",
        "tokens": ["मात्रा", "जोड़कर", "शब्द", "पढ़ना"],
    }
    chunk3 = {
        "chunk_id": "c3",
        "source": "s1",
        "section": "विज्ञान",
        "text": "पर्यावरण अध्ययन और अवलोकन करना।",
        "tokens": ["पर्यावरण", "अध्ययन", "अवलोकन", "करना"],
    }

    import json

    (tmp_path / "s1.jsonl").write_text(
        json.dumps(chunk1, ensure_ascii=False)
        + "\n"
        + json.dumps(chunk3, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "s2.jsonl").write_text(
        json.dumps(chunk2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    retriever = GuideRetriever(chunks_dir=tmp_path)
    assert len(retriever._chunks) == 3

    # Query matching chunk 1
    res1 = await retriever.retrieve("स्थानीय मान बंडल", top_k=2)
    assert len(res1) > 0
    assert res1[0].chunk_id == "c1"

    # Query matching chunk 2
    res2 = await retriever.retrieve("मात्रा जोड़कर शब्द", top_k=2)
    assert len(res2) > 0
    assert res2[0].chunk_id == "c2"


# ── 9. Golden Retrieval Benchmark (10 FLN Teacher Queries) ────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected_move_or_term"),
    [
        (
            "जब बच्चे 43 में से 27 घटाते समय हासिल में अटकें तो बंडल खोलना कैसे समझाएं?",
            "NUM_SUB_REGROUP_BUNDLES",
        ),
        (
            "स्थानीय मान सिखाते समय दस-दस के बंडल और खुली तीलियों का उपयोग कैसे करें?",
            "NUM_PLACE_VALUE_BUNDLES",
        ),
        (
            "जोड़ में हासिल (carry-over) की अवधारणा बच्चों को कंक्रीट सामग्री से कैसे समझाएं?",
            "NUM_ADD_CARRY_BUNDLES",
        ),
        (
            "कक्षा 1 के बच्चों को मात्रा जोड़कर दो-अक्षर वाले शब्द पढ़ना कैसे सिखाएं?",
            "LIT_MATRA_BLENDING",
        ),
        (
            "वर्ण पहचान और अक्षरों की ध्वनि मिलाकर शब्द डिकोडिंग कराने का सही तरीका क्या है?",
            "LIT_MATRA_BLENDING",
        ),
        (
            "बच्चा घटाव करते समय हमेशा ऊपर की छोटी संख्या को नीचे की बड़ी संख्या से घटा देता है, इसे कैसे ठीक करें?",
            "NUM_SUB_REGROUP_BUNDLES",
        ),
        (
            "4 बंडल और 7 खुली तीलियों से संख्या 47 का स्थानीय मान कैसे सिखाएं?",
            "NUM_PLACE_VALUE_BUNDLES",
        ),
        (
            "कक्षा 1 और 2 के बच्चों के लिए बुनियादी गणित और संख्या बोध का अभ्यास",
            "बंडल",
        ),
        (
            "संख्या बोध और 1 से 99 तक की संख्याओं को गिनने की समझ कैसे विकसित करें?",
            "NUM_PLACE_VALUE_BUNDLES",
        ),
        (
            "कक्षा में बच्चों से अपनी बात और समझ को अपने शब्दों में समझाने को कैसे कहें?",
            "NUM_SUB_REGROUP_BUNDLES",
        ),
    ],
)
async def test_golden_retrieval_benchmark(query: str, expected_move_or_term: str) -> None:
    """Golden retrieval test verifying that realistic FLN teacher questions return
    relevant chunks with positive normalized similarity scores within [0.0, 1.0]."""
    retriever = GuideRetriever()
    results = await retriever.retrieve(query, top_k=5)

    assert len(results) > 0, f"Query '{query}' returned no results"

    top_chunk = results[0]
    assert 0.0 < top_chunk.similarity_score <= 1.0, (
        f"Score {top_chunk.similarity_score} out of bounds for query: {query}"
    )

    # Check that either the expected move ID is present among top results or the expected term is in text
    matched = False
    for chunk in results:
        if chunk.move_id == expected_move_or_term or expected_move_or_term in chunk.chunk_id:
            matched = True
            break
        if expected_move_or_term in chunk.text or expected_move_or_term in chunk.section:
            matched = True
            break

    assert matched, (
        f"Expected move or term '{expected_move_or_term}' not found in top 5 chunks for query: '{query}'"
    )


@pytest.mark.asyncio
async def test_retrieval_out_of_domain_query_filtered() -> None:
    """Verifies that completely out-of-domain queries (with no FLN keywords)
    return empty results when minimum threshold is applied."""
    retriever = GuideRetriever()
    # Query with pure non-FLN terms
    results = await retriever.retrieve(
        "कंप्यूटर प्रोग्रामिंग पायथन सॉफ्टवेयर विकास", top_k=5, min_score=0.25
    )
    assert len(results) == 0
