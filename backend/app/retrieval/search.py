"""Document chunk retrieval over state guides and practice library (§8, §10.4)."""

from __future__ import annotations

import json
import logging
import unicodedata
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from rank_bm25 import (  # type: ignore[import-untyped]  # rank_bm25 has no PEP 561 type stubs
    BM25Okapi,
)

from backend.app.core.messages import get_catalog, get_message
from backend.app.retrieval.ingest import (
    CATALOG_FILE,
    CHUNKS_DIR,
    SEED_CHUNKS_FILE,
    build_seed_chunks,
)

logger = logging.getLogger("abhyas.retrieval.search")

if CATALOG_FILE.exists():
    get_catalog(CATALOG_FILE)

_STOPWORDS_CACHE: frozenset[str] | None = None


def get_hindi_stopwords() -> frozenset[str]:
    """Loads Hindi stopwords from stopwords_hi.txt."""
    global _STOPWORDS_CACHE
    if _STOPWORDS_CACHE is None:
        stopwords_path = Path(__file__).resolve().parent / "stopwords_hi.txt"
        words: set[str] = set()
        if stopwords_path.exists():
            with open(stopwords_path, encoding="utf-8") as f:
                for line in f:
                    w = unicodedata.normalize("NFC", line.strip())
                    if w:
                        words.add(w)
        _STOPWORDS_CACHE = frozenset(words)
    return _STOPWORDS_CACHE


def tokenize_hindi(text: str, filter_stopwords: bool = False) -> list[str]:
    """Tokenize Hindi/Latin text via Unicode punctuation stripping and whitespace splitting."""
    if not text:
        return []
    norm = unicodedata.normalize("NFC", text)
    cleaned = "".join(
        " " if unicodedata.category(c).startswith("P") or c.isspace() else c for c in norm
    )
    tokens = [t.lower() for t in cleaned.split() if t]
    if filter_stopwords:
        sw = get_hindi_stopwords()
        tokens = [t for t in tokens if t not in sw]
    return tokens


class RetrievedChunk(BaseModel):
    chunk_id: str
    source: str
    section: str
    text: str
    similarity_score: float
    source_short_hi: str = Field(default_factory=lambda: get_message("ingest_summary_title"))
    page: int | None = None
    move_id: str = ""
    tags: list[str] = []


class GuideRetriever:
    """BM25 Okapi retriever over state FLN guides and practice library."""

    def __init__(
        self,
        chunks_file: Path | str | None = None,
        chunks_dir: Path | str | None = None,
        similarity_threshold: float = 0.0,
    ) -> None:
        self.chunks_file = Path(chunks_file) if chunks_file else None
        self.chunks_dir = Path(chunks_dir) if chunks_dir else CHUNKS_DIR
        self.similarity_threshold = similarity_threshold
        self._chunks: list[dict[str, Any]] = []
        self._bm25: BM25Okapi | None = None
        self._load_corpus()

    def _load_corpus(self) -> None:
        if self.chunks_file is not None:
            # Single file explicit mode
            if not self.chunks_file.exists():
                try:
                    build_seed_chunks(output_file=self.chunks_file)
                except (OSError, yaml.YAMLError, ValueError, KeyError) as e:
                    logger.warning("Failed to build seed chunks on init: %s", e)

            if self.chunks_file.exists():
                with open(self.chunks_file, encoding="utf-8") as f:
                    self._chunks = [json.loads(line) for line in f if line.strip()]
        else:
            # Multi-file directory mode: load all *.jsonl from chunks_dir
            if self.chunks_dir.exists():
                jsonl_files = sorted(self.chunks_dir.glob("*.jsonl"))
            else:
                jsonl_files = []

            if not jsonl_files:
                try:
                    build_seed_chunks(output_file=SEED_CHUNKS_FILE)
                    if SEED_CHUNKS_FILE.exists():
                        jsonl_files = [SEED_CHUNKS_FILE]
                except (OSError, yaml.YAMLError, ValueError, KeyError) as e:
                    logger.warning("Failed to build seed chunks on init: %s", e)

            chunks_list: list[dict[str, Any]] = []
            seen_chunk_ids: set[str] = set()
            for jf in jsonl_files:
                with open(jf, encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        chunk_data = json.loads(line)
                        c_id = chunk_data.get("chunk_id", "")
                        if c_id and c_id in seen_chunk_ids:
                            continue
                        seen_chunk_ids.add(c_id)
                        chunks_list.append(chunk_data)
            self._chunks = chunks_list

        if self._chunks:
            tokenized_corpus: list[list[str]] = []
            for c in self._chunks:
                if "tokens" in c and c["tokens"]:
                    tokenized_corpus.append(list(c["tokens"]))
                else:
                    tokens = tokenize_hindi(
                        f"{c.get('section', '')} {c.get('text', '')} {' '.join(c.get('tags', []))}",
                        filter_stopwords=True,
                    )
                    tokenized_corpus.append(tokens)
            self._bm25 = BM25Okapi(tokenized_corpus)
            for term, val in self._bm25.idf.items():
                if val <= 0.0:
                    self._bm25.idf[term] = 0.25

    async def retrieve(
        self,
        query_text: str,
        top_k: int = 5,
        min_score: float | None = None,
    ) -> list[RetrievedChunk]:
        """Performs BM25 search over chunks, returning top_k RetrievedChunk instances."""
        if not self._chunks or self._bm25 is None:
            return []

        tokens = tokenize_hindi(query_text, filter_stopwords=True)
        if not tokens:
            tokens = tokenize_hindi(query_text, filter_stopwords=False)
        if not tokens:
            return []

        scores = self._bm25.get_scores(tokens)

        # Theoretical max score for normalization: sum of (k1 + 1) * max(0, IDF(t))
        k1 = 1.5
        s_max = sum((k1 + 1) * max(0.0, float(self._bm25.idf.get(t, 0.0))) for t in tokens)

        threshold = min_score if min_score is not None else self.similarity_threshold

        scored_chunks: list[tuple[float, float, dict[str, Any]]] = []
        for raw_score, chunk in zip(scores, self._chunks, strict=True):
            raw_float = float(raw_score)
            if s_max > 0.0:
                norm_score = min(1.0, max(0.0, raw_float / s_max))
            else:
                norm_score = 0.0

            # Pass if above threshold (or if threshold is 0.0 and raw score > 0)
            if threshold > 0.0:
                if norm_score >= threshold:
                    scored_chunks.append((norm_score, raw_float, chunk))
            elif raw_float > 0.0:
                scored_chunks.append((norm_score, raw_float, chunk))

        scored_chunks.sort(key=lambda x: (x[0], x[1]), reverse=True)

        results: list[RetrievedChunk] = []
        for norm_score, _raw_score, chunk in scored_chunks[:top_k]:
            results.append(
                RetrievedChunk(
                    chunk_id=chunk["chunk_id"],
                    source=chunk.get("source", "seed_from_moves"),
                    section=chunk.get("section", ""),
                    page=chunk.get("page"),
                    text=chunk.get("text", ""),
                    similarity_score=round(norm_score, 4),
                    source_short_hi=chunk.get("source_short_hi")
                    or get_message("ingest_summary_title"),
                    move_id=chunk.get("move_id", ""),
                    tags=chunk.get("tags", []),
                )
            )
        return results


__all__ = ["RetrievedChunk", "GuideRetriever", "tokenize_hindi", "get_hindi_stopwords"]
