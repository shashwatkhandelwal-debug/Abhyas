"""Ingestion pipeline for state guides and move cards (spec/10 §10.4).

Generates content/chunks/seed_from_moves.jsonl from seed moves (content/moves/*.yaml).
"""

from __future__ import annotations

import json
import logging
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from backend.app.core.messages import get_catalog, get_message

logger = logging.getLogger("abhyas.retrieval.ingest")

REPO_ROOT = Path(__file__).resolve().parents[3]
MOVES_DIR = REPO_ROOT / "content" / "moves"
CHUNKS_DIR = REPO_ROOT / "content" / "chunks"
SEED_CHUNKS_FILE = CHUNKS_DIR / "seed_from_moves.jsonl"
CATALOG_FILE = REPO_ROOT / "content" / "messages_hi.yaml"
if CATALOG_FILE.exists():
    get_catalog(CATALOG_FILE)


def extract_chunks_from_move(move_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extracts learn script and key points into standard chunk dictionaries."""
    move_id = str(move_data.get("id", ""))
    title_hi = unicodedata.normalize("NFC", str(move_data.get("title_hi", "")))
    tags = list(move_data.get("tags", []))
    module_ref = move_data.get("module_ref", {}) or {}
    source_id = str(module_ref.get("source_id", "abhyas_move_card"))
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
        chunks.append(
            {
                "chunk_id": f"{move_id}_learn",
                "source": source_id,
                "source_short_hi": summary_title,
                "section": f"{base_section}: {method_title}",
                "text": norm_text,
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
        chunks.append(
            {
                "chunk_id": f"{move_id}_{kp_id}",
                "source": source_id,
                "source_short_hi": summary_title,
                "section": f"{base_section}: {key_points_title} ({kp_id})",
                "text": norm_kp_text,
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_seed_chunks()
