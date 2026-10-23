"""Her class choice -> her path and her practice scenes (deterministic, no LLM).

- `order_path`: moves that practise one of her struggles come first, in her order; everything else
  keeps its earlier relative order. Each row's `reason` remembers `base_pos=N` (where it stood
  before she chose), so clearing her choice puts the path back.
- `because`: the struggle behind a move ("chosen because your class struggles with ...").
- `focus_child`: the child in a move's scene who makes the mistake that matches her top struggle.

Nothing here touches what a child answers: that stays with the rule engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from backend.app.class_profile.library import ClassStruggle, StruggleLibrary, load_library
from backend.app.content_models import MoveCard
from backend.app.core.messages import get_ui_lang

if (
    TYPE_CHECKING
):  # imported lazily: sessions/__init__ imports the service, which imports this module
    from backend.app.sessions.path import MovePathEntry

_BASE_POS = re.compile(r"(?:^|; )base_pos=(\d+)")


@dataclass(frozen=True)
class FocusChild:
    persona_id: str
    misconception_id: str
    struggle: ClassStruggle


def label_of(struggle: ClassStruggle) -> str:
    return struggle.label_en if get_ui_lang() == "en" else struggle.label_hi


def because(
    move_id: str, struggle_ids: list[str], lib: StruggleLibrary | None = None
) -> ClassStruggle | None:
    """The highest-priority struggle of hers that this move practises, if any."""
    lib = lib or load_library()
    for sid in struggle_ids:
        s = lib.get(sid)
        if s is not None and s.move_id == move_id:
            return s
    return None


def struggle_moves(
    struggle_ids: list[str], lib: StruggleLibrary | None = None
) -> list[tuple[str, str]]:
    """(move_id, struggle_id) in her order, one row per move (its first struggle)."""
    lib = lib or load_library()
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for sid in struggle_ids:
        s = lib.get(sid)
        if s is not None and s.move_id and s.move_id not in seen:
            seen.add(s.move_id)
            out.append((s.move_id, sid))
    return out


def focus_child(
    move: MoveCard, struggle_ids: list[str], lib: StruggleLibrary | None = None
) -> FocusChild | None:
    """The scene child whose misconception is the first one of her struggles that the move has."""
    lib = lib or load_library()
    for sid in struggle_ids:
        s = lib.get(sid)
        if s is None or s.move_id != move.id:
            continue
        for mid in s.misconception_ids:
            for child in move.scenario.children:
                if child.misconception == mid:
                    return FocusChild(child.persona_id, mid, s)
    return None


def rubric_scores_skill(move_id: str, skill_ids: list[str]) -> bool:
    """Does this move's one-on-one rubric have a criterion for one of the skills she chose?"""
    from backend.app.rehearsal.scene_runner import load_move_card

    try:
        move = load_move_card(move_id)
    except (FileNotFoundError, KeyError, ValueError):
        return False
    if move.rubric_one_on_one is None:
        return False
    criteria = {c.id for c in move.rubric_one_on_one.criteria}
    return any(sid in criteria for sid in skill_ids)


def _base_pos(entry: MovePathEntry) -> int:
    m = _BASE_POS.search(entry.reason)
    return int(m.group(1)) if m else entry.position


def _strip_class_tags(reason: str) -> str:
    parts = [
        p
        for p in (x.strip() for x in reason.split(";"))
        if p and not p.startswith(("base_pos=", "matches_class_struggle="))
    ]
    return "; ".join(parts)


def order_path(
    entries: list[MovePathEntry],
    struggle_ids: list[str],
    *,
    done_moves: frozenset[str] = frozenset(),
    lib: StruggleLibrary | None = None,
    skill_ids: list[str] | None = None,
) -> list[MovePathEntry]:
    """Struggle moves first (her order, skipping moves she has already completed), then the rest.

    Among the rest, moves whose one-on-one rubric scores a skill she chose to improve come before
    the others (each group keeps its earlier order). With no struggles and no skills the original
    order is restored from `base_pos`. Positions are renumbered.
    """
    lib = lib or load_library()
    base = sorted(entries, key=lambda e: (_base_pos(e), e.position))
    wanted = [(m, s) for m, s in struggle_moves(struggle_ids, lib) if m not in done_moves]
    front_ids = [m for m, _ in wanted if any(e.move_id == m for e in base)]
    why = dict(wanted)
    front = [next(e for e in base if e.move_id == m) for m in front_ids]
    rest = [e for e in base if e.move_id not in set(front_ids)]
    if skill_ids:
        rest = [e for e in rest if rubric_scores_skill(e.move_id, skill_ids)] + [
            e for e in rest if not rubric_scores_skill(e.move_id, skill_ids)
        ]
    out: list[MovePathEntry] = []
    for pos, e in enumerate(front + rest, start=1):
        core = _strip_class_tags(e.reason)
        tags = [f"base_pos={_base_pos(e)}"]
        if e.move_id in why:
            tags.append(f"matches_class_struggle={why[e.move_id]}")
        out.append(replace(e, position=pos, reason="; ".join([core, *tags] if core else tags)))
    return out


__all__ = [
    "FocusChild",
    "because",
    "focus_child",
    "label_of",
    "order_path",
    "rubric_scores_skill",
    "struggle_moves",
]
