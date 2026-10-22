"""Document chunk retrieval over state guides and practice library (§8, §10.4)."""

from __future__ import annotations

import functools
import json
import logging
import math
import unicodedata
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from rank_bm25 import (  # type: ignore[import-untyped]  # rank_bm25 has no PEP 561 type stubs
    BM25Okapi,
)

from backend.app.config import settings
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


_HI_SUFFIXES = (
    "\u093f\u092f\u094b\u0902",
    "\u093e\u0913\u0902",
    "\u093e\u090f\u0901",
    "\u093e\u090f\u0902",
    "\u094b\u0902",
    "\u0947\u0902",
    "\u0940\u0902",
    "\u0947",
    "\u0940",
    "\u093e",
)  # inflectional endings
_MIN_STEM = 3
_GLOSS_WEIGHT = 2  # Hindi gloss/keywords are repeated so they are not drowned by long English text


def index_term(token: str) -> str:
    """Light Hindi normalisation applied identically to chunks and queries.

    Drops the nukta, folds chandrabindu into anusvara and strips common inflectional endings
    (plural/oblique/singular forms collapse to one stem) so inflected Hindi matches the gloss/keywords. Latin tokens
    and numbers are untouched.
    """
    if not any("\u0900" <= c <= "\u097f" for c in token):
        return token
    t = token.replace("\u093c", "").replace("\u0901", "\u0902")
    for suf in _HI_SUFFIXES:
        if t.endswith(suf) and len(t) - len(suf) >= _MIN_STEM:
            return t[: -len(suf)]
    return t


def index_terms(tokens: list[str]) -> list[str]:
    return [index_term(t) for t in tokens]


class RetrievedChunk(BaseModel):
    chunk_id: str
    source: str
    section: str
    text: str
    similarity_score: float
    source_short_hi: str = Field(default_factory=lambda: get_message("ingest_summary_title"))
    page: int | None = None
    page_end: int | None = None
    printed_page: int | None = None
    gloss_hi: str = ""
    keywords_hi: list[str] = []
    move_id: str = ""
    tags: list[str] = []
    matched_terms: int = 0  # distinct query terms found in this chunk (retrieval gate)


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
        self._by_id: dict[str, dict[str, Any]] | None = None
        self._doc_terms: list[frozenset[str]] = []
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
                if c.get("tokens"):
                    tokens = list(c["tokens"])
                else:
                    tokens = tokenize_hindi(
                        f"{c.get('section', '')} {c.get('text', '')} {' '.join(c.get('tags', []))}",
                        filter_stopwords=True,
                    )
                hindi = tokenize_hindi(
                    f"{c.get('gloss_hi', '')} {' '.join(c.get('keywords_hi', []))}",
                    filter_stopwords=True,
                )
                terms = index_terms(tokens + hindi * _GLOSS_WEIGHT)
                tokenized_corpus.append(terms)
                self._doc_terms.append(frozenset(terms))
            self._bm25 = BM25Okapi(tokenized_corpus)
            for term, val in self._bm25.idf.items():
                if val <= 0.0:
                    self._bm25.idf[term] = 0.25

    async def retrieve(
        self,
        query_text: str,
        top_k: int = 5,
        min_score: float | None = None,
        official_only: bool = False,
        min_matched_terms: int = 0,
    ) -> list[RetrievedChunk]:
        """Performs BM25 search over chunks, returning top_k RetrievedChunk instances.

        min_matched_terms > 0 drops chunks sharing fewer distinct query terms than that (capped
        at the number of distinct query terms, so a one-word question needs one match).
        """
        if not self._chunks or self._bm25 is None:
            return []

        tokens = tokenize_hindi(query_text, filter_stopwords=True)
        if not tokens:
            tokens = tokenize_hindi(query_text, filter_stopwords=False)
        if not tokens:
            return []

        tokens = index_terms(tokens)
        scores = self._bm25.get_scores(tokens)
        query_terms = set(tokens)
        required_terms = min(min_matched_terms, len(query_terms))

        # Best case per query term is (k1 + 1) * idf. Terms absent from the corpus count at the
        # unseen-term idf, so off-topic queries (most words unmatched) score low instead of
        # being normalised only over the few words that happen to match.
        k1 = 1.5
        n_docs = len(self._chunks)
        unseen_idf = math.log(2 * n_docs + 1)
        s_max = sum(
            (k1 + 1) * (max(0.0, float(self._bm25.idf[t])) if t in self._bm25.idf else unseen_idf)
            for t in tokens
        )

        threshold = min_score if min_score is not None else self.similarity_threshold

        scored_chunks: list[tuple[float, float, dict[str, Any]]] = []
        matched_by_id: dict[str, int] = {}
        for raw_score, chunk, doc_terms in zip(scores, self._chunks, self._doc_terms, strict=True):
            if official_only and chunk.get("move_id"):
                continue  # skip Abhyas move-card summaries; keep source-document excerpts
            raw_float = float(raw_score)
            n_matched = len(query_terms & doc_terms)
            if n_matched < required_terms:
                continue
            matched_by_id[chunk["chunk_id"]] = n_matched
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
                    page_end=chunk.get("pdf_page_end"),
                    printed_page=chunk.get("printed_page_start"),
                    gloss_hi=chunk.get("gloss_hi", ""),
                    text=chunk.get("text", ""),
                    similarity_score=round(norm_score, 4),
                    source_short_hi=chunk.get("source_short_hi")
                    or get_message("ingest_summary_title"),
                    keywords_hi=chunk.get("keywords_hi", []),
                    move_id=chunk.get("move_id", ""),
                    tags=chunk.get("tags", []),
                    matched_terms=matched_by_id.get(chunk["chunk_id"], 0),
                )
            )
        return results

    async def retrieve_supported(self, query_text: str) -> list[RetrievedChunk]:
        """Chunks good enough to answer from: score gate plus the matched-terms gate."""
        return await self.retrieve(
            query_text,
            top_k=settings.RETRIEVAL_TOP_K,
            min_score=settings.RETRIEVAL_MIN_SCORE,
            min_matched_terms=settings.RETRIEVAL_MIN_MATCHED_TERMS,
        )

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """Full stored chunk record by id (for the tappable source excerpt)."""
        if self._by_id is None:
            self._by_id = {c["chunk_id"]: c for c in self._chunks if c.get("chunk_id")}
        return self._by_id.get(chunk_id)


@functools.lru_cache(maxsize=1)
def get_guide_retriever() -> GuideRetriever:
    """Process-wide retriever: the BM25 index is built once, not per request."""
    return GuideRetriever()


__all__ = [
    "RetrievedChunk",
    "GuideRetriever",
    "get_guide_retriever",
    "tokenize_hindi",
    "get_hindi_stopwords",
]
