"""The closed library of class-level struggles (content/class_struggles.yaml).

Everything a teacher can pick, say or have stored in "My class" is an id from this file. Hindi
text is NFC-normalised at load (AGENTS.md rule 10). `validate_library` is what the content test
and `make content-validate` run: every move, misconception and chunk id has to exist.
"""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from backend.app.config import settings

CONTENT_DIR = Path(__file__).resolve().parents[3] / "content"
LIBRARY_PATH = CONTENT_DIR / "class_struggles.yaml"
CHUNKS_DIR = CONTENT_DIR / "chunks"


def _nfc(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value).strip()
    if isinstance(value, list):
        return [_nfc(v) for v in value]
    return value


class ClassStruggle(BaseModel):
    id: str
    domain: str
    label_hi: str
    label_en: str
    chip_hi: str = ""
    chip_en: str = ""
    triggers_hi: list[str] = Field(min_length=2, max_length=3)
    keywords: list[str] = Field(default_factory=list)
    misconception_ids: list[str] = Field(default_factory=list)
    move_id: str | None = None
    chunk_ids: list[str] = Field(min_length=1, max_length=2)
    tip_hi: str
    tip_en: str

    _normalise = field_validator(
        "label_hi",
        "chip_hi",
        "triggers_hi",
        "keywords",
        "tip_hi",
        mode="after",
    )(_nfc)

    @property
    def has_practice(self) -> bool:
        return self.move_id is not None


class OtherEntry(BaseModel):
    label_hi: str
    label_en: str
    chip_hi: str
    chip_en: str
    chunk_ids: list[str] = Field(min_length=1, max_length=2)
    tip_hi: str
    tip_en: str

    _normalise = field_validator("label_hi", "chip_hi", "tip_hi", mode="after")(_nfc)


class StruggleLibrary(BaseModel):
    struggles: list[ClassStruggle]
    other: OtherEntry

    def ids(self) -> list[str]:
        return [s.id for s in self.struggles]

    def get(self, struggle_id: str) -> ClassStruggle | None:
        return next((s for s in self.struggles if s.id == struggle_id), None)

    def chips(self) -> list[ClassStruggle]:
        return [s for s in self.struggles if s.chip_hi]

    def for_misconception(self, misconception_id: str) -> list[ClassStruggle]:
        return [s for s in self.struggles if misconception_id in s.misconception_ids]


@lru_cache(maxsize=4)
def load_library(path: str | None = None) -> StruggleLibrary:
    source = Path(path) if path else LIBRARY_PATH
    return StruggleLibrary.model_validate(yaml.safe_load(source.read_text(encoding="utf-8")))


class Citation(BaseModel):
    chunk_id: str
    source_short_hi: str
    title: str
    page: int | None
    ocr: bool = False

    def label_hi(self) -> str:
        page = f", पृ. {self.page}" if self.page else ""
        return f"{self.source_short_hi}{page}"


@lru_cache(maxsize=1)
def _chunk_index() -> dict[str, Citation]:
    index: dict[str, Citation] = {}
    for f in sorted(CHUNKS_DIR.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            page = row.get("printed_page_start") or row.get("pdf_page_start") or row.get("page")
            index[row["chunk_id"]] = Citation(
                chunk_id=row["chunk_id"],
                source_short_hi=unicodedata.normalize("NFC", row.get("source_short_hi", "")),
                title=row.get("title", ""),
                page=page,
                ocr=bool(row.get("ocr")),
            )
    return index


def citations(chunk_ids: list[str]) -> list[Citation]:
    """Citations for the chunk ids that exist (an unknown id is skipped, never invented)."""
    index = _chunk_index()
    return [index[c] for c in chunk_ids if c in index]


def validate_library(lib: StruggleLibrary, moves: dict[str, set[str]]) -> list[str]:
    """Problems found; empty = valid. `moves` maps move_id -> the ids it can practise."""
    errors: list[str] = []
    index = _chunk_index()
    seen: set[str] = set()
    for s in lib.struggles:
        if s.id in seen:
            errors.append(f"{s.id}: duplicate id")
        seen.add(s.id)
        if s.domain not in {"numeracy", "literacy"}:
            errors.append(f"{s.id}: bad domain {s.domain!r}")
        if s.move_id is not None and s.move_id not in moves:
            errors.append(f"{s.id}: unknown move_id {s.move_id!r}")
        if s.misconception_ids and s.move_id is None:
            errors.append(f"{s.id}: misconception_ids without a move_id")
        for mid in s.misconception_ids:
            if s.move_id in moves and mid not in moves[s.move_id]:
                errors.append(f"{s.id}: misconception {mid!r} is not in move {s.move_id}")
        if s.move_id is not None and not s.misconception_ids:
            errors.append(f"{s.id}: move_id without misconception_ids")
        if not s.keywords:
            errors.append(f"{s.id}: no keywords")
    for owner, ids in [(s.id, s.chunk_ids) for s in lib.struggles] + [
        ("other", lib.other.chunk_ids)
    ]:
        for cid in ids:
            if cid not in index:
                errors.append(f"{owner}: unknown chunk id {cid!r}")
    if not settings.STRUGGLE_CHIPS_MIN <= len(lib.chips()) <= settings.STRUGGLE_CHIPS_MAX:
        errors.append(f"expected {settings.STRUGGLE_CHIPS_MIN}-{settings.STRUGGLE_CHIPS_MAX} chips")
    if len(lib.struggles) > settings.STRUGGLE_LIBRARY_MAX:
        errors.append(
            f"library has {len(lib.struggles)} entries (max {settings.STRUGGLE_LIBRARY_MAX})"
        )
    return errors
