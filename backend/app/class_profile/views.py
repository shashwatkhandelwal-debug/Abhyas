"""Template-ready views of the class-struggle library (the "My class" page and cards)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.class_profile.library import (
    ClassStruggle,
    StruggleLibrary,
    citations,
    load_library,
)
from backend.app.core.messages import get_ui_lang
from backend.app.rehearsal.scene_runner import load_move_card


@dataclass(frozen=True)
class StruggleView:
    id: str
    label: str
    chip: str
    tip: str
    practice_title: str | None  # None = no practice case yet
    source: str
    ocr: bool


def struggle_view(s: ClassStruggle) -> StruggleView:
    en = get_ui_lang() == "en"
    cites = citations(s.chunk_ids)
    first = cites[0] if cites else None
    return StruggleView(
        id=s.id,
        label=s.label_en if en else s.label_hi,
        chip=(s.chip_en if en else s.chip_hi) or (s.label_en if en else s.label_hi),
        tip=s.tip_en if en else s.tip_hi,
        practice_title=load_move_card(s.move_id).title_hi if s.move_id else None,
        source=first.label_hi() if first else "",
        ocr=bool(first and first.ocr),
    )


def views_for(ids: list[str], lib: StruggleLibrary | None = None) -> list[StruggleView]:
    lib = lib or load_library()
    return [struggle_view(s) for sid in ids if (s := lib.get(sid)) is not None]


def chip_views(lib: StruggleLibrary | None = None) -> list[StruggleView]:
    lib = lib or load_library()
    return [struggle_view(s) for s in lib.chips()]
