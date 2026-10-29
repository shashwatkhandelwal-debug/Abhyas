"""National / state label of each source document (from `content/sources/sources.yaml`).

`scope: national` is a central-government source (NCERT, NIPUN Bharat, NISHTHA); `scope: state`
with `state: <code>` is a state pack (the UP handbooks). The label shown beside a citation comes
from the message catalog (`ask_source_scope_national`, `ask_source_scope_state_<code>`), so adding a
state is a manifest entry plus two catalog lines. A source with no scope gets no label (never a
guess). Used for citation text and as a deterministic retrieval tie-break (national first).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from backend.app.core.messages import get_catalog

MANIFEST = Path(__file__).resolve().parents[3] / "content" / "sources" / "sources.yaml"
NATIONAL = "national"
STATE = "state"


@dataclass(frozen=True)
class SourceScope:
    source_id: str
    short_hi: str
    scope: str  # "national" | "state" | ""
    state: str  # state code for a state pack, else ""


@lru_cache(maxsize=1)
def _manifest() -> tuple[dict[str, SourceScope], dict[str, SourceScope]]:
    by_id: dict[str, SourceScope] = {}
    by_short: dict[str, SourceScope] = {}
    entries = yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or []
    for e in entries:
        info = SourceScope(
            source_id=str(e["id"]),
            short_hi=str(e.get("short_hi", "")),
            scope=str(e.get("scope", "")),
            state=str(e.get("state", "")),
        )
        by_id[info.source_id] = info
        if info.short_hi:
            by_short[info.short_hi] = info
    return by_id, by_short


def scope_of(source_id: str) -> SourceScope | None:
    return _manifest()[0].get(source_id)


def scope_of_short(source_short_hi: str) -> SourceScope | None:
    """Look a source up by its short Hindi name (what a stored chunk and a citation carry)."""
    return _manifest()[1].get(source_short_hi)


def is_national(source_id: str) -> bool:
    info = scope_of(source_id)
    return info is not None and info.scope == NATIONAL


def national_rank(source_id: str) -> int:
    """1 for a national source, else 0: the retrieval tie-break (equal scores, national first)."""
    return 1 if is_national(source_id) else 0


def scope_label(info: SourceScope | None) -> str:
    """The catalog text for a source's scope in the current language ("" when there is none)."""
    if info is None:
        return ""
    if info.scope == NATIONAL:
        key = "ask_source_scope_national"
    elif info.scope == STATE and info.state:
        key = f"ask_source_scope_state_{info.state}"
    else:
        return ""
    # citation lines are Hindi in every UI language (the source names are), so the label is too
    catalog = get_catalog(lang="hi")
    return catalog.get(key) if catalog.has(key) else ""


__all__ = [
    "SourceScope",
    "is_national",
    "national_rank",
    "scope_label",
    "scope_of",
    "scope_of_short",
]
