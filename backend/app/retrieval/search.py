"""Document chunk retrieval over state guides and practice library (§8, §10.4)."""

from __future__ import annotations

import json
import logging
import unicodedata
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from backend.app.retrieval.ingest import SEED_CHUNKS_FILE, build_seed_chunks

logger = logging.getLogger("abhyas.retrieval.search")


def tokenize_hindi(text: str) -> list[str]:
    """Tokenize Hindi/Latin text via Unicode punctuation stripping and whitespace splitting."""
    if not text:
        return []
    norm = unicodedata.normalize("NFC", text)
    cleaned = "".join(
        " " if unicodedata.category(c).startswith("P") or c.isspace() else c for c in norm
    )
    return [t.lower() for t in cleaned.split() if t]


class RetrievedChunk(BaseModel):
    chunk_id: str
    source: str
    section: str
    text: str
    similarity_score: float
    source_short_hi: str = "अभ्यास मूव सारांश"
    move_id: str = ""
    tags: list[str] = []


class GuideRetriever:
    """BM25 Okapi retriever over state FLN guides and practice library."""

    def __init__(
        self,
        chunks_file: Path | str | None = None,
        similarity_threshold: float = 0.0,
    ) -> None:
        self.chunks_file = Path(chunks_file) if chunks_file else SEED_CHUNKS_FILE
        self.similarity_threshold = similarity_threshold
        self._chunks: list[dict[str, Any]] = []
        self._bm25: BM25Okapi | None = None
        self._load_corpus()

    def _load_corpus(self) -> None:
        if not self.chunks_file.exists():
            try:
                build_seed_chunks(output_file=self.chunks_file)
            except Exception as e:
                logger.warning("Failed to build seed chunks on init: %s", e)

        if self.chunks_file.exists():
            with open(self.chunks_file, encoding="utf-8") as f:
                self._chunks = [json.loads(line) for line in f if line.strip()]

        if self._chunks:
            tokenized_corpus: list[list[str]] = [
                tokenize_hindi(
                    f"{c.get('section', '')} {c.get('text', '')} {' '.join(c.get('tags', []))}"
                )
                for c in self._chunks
            ]
            self._bm25 = BM25Okapi(tokenized_corpus)

    async def retrieve(self, query_text: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Performs BM25 search over chunks, returning top_k RetrievedChunk instances."""
        if not self._chunks or self._bm25 is None:
            return []

        tokens = tokenize_hindi(query_text)
        if not tokens:
            return []

        scores = self._bm25.get_scores(tokens)
        scored_chunks: list[tuple[float, dict[str, Any]]] = [
            (float(score), chunk)
            for score, chunk in zip(scores, self._chunks, strict=True)
            if score > self.similarity_threshold
        ]

        scored_chunks.sort(key=lambda x: x[0], reverse=True)

        results: list[RetrievedChunk] = []
        for score, chunk in scored_chunks[:top_k]:
            results.append(
                RetrievedChunk(
                    chunk_id=chunk["chunk_id"],
                    source=chunk.get("source", "seed_from_moves"),
                    section=chunk.get("section", ""),
                    text=chunk.get("text", ""),
                    similarity_score=round(score, 4),
                    source_short_hi=chunk.get("source_short_hi", "अभ्यास मूव सारांश"),
                    move_id=chunk.get("move_id", ""),
                    tags=chunk.get("tags", []),
                )
            )
        return results


__all__ = ["RetrievedChunk", "GuideRetriever", "tokenize_hindi"]
