"""Modules: the three numeracy moves as learn -> diagnose a child (1-1) -> practise -> check.

The module id is the move id. Progress lives in `module_progress` (one row per teacher and
module); this file holds the registry and the pure helpers the picker page and the dashboards use.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from backend.app.config import settings
from backend.app.content_models import MoveCard
from backend.app.rehearsal.scene_runner import load_move_card

STEP_LEARN = "learn"
STEP_DIAGNOSE = "diagnose"
STEP_PRACTISE = "practise"
STEP_CHECK = "check"
MODULE_STEPS: tuple[str, ...] = (STEP_LEARN, STEP_DIAGNOSE, STEP_PRACTISE, STEP_CHECK)

CHECK_IDLE = ""
CHECK_ASKING = "asking"
CHECK_DONE = "done"


def module_ids() -> list[str]:
    """Module ids in picker order (subtraction with regrouping first)."""
    return list(settings.MODULE_IDS)


def module_card(module_id: str) -> MoveCard:
    return load_move_card(module_id)


@dataclass(frozen=True)
class ModuleView:
    module_id: str
    title_hi: str
    summary_hi: str
    done: dict[str, bool]
    check_passed: bool | None
    diagnose_verdict: str | None
    because: str = ""  # her class struggle this module practises ("" = none chosen)

    @property
    def steps_done(self) -> int:
        return sum(self.done.values())

    @property
    def complete(self) -> bool:
        return all(self.done.values())

    @property
    def next_step(self) -> str | None:
        return next((s for s in MODULE_STEPS if not self.done[s]), None)


def step_flags(row: Any | None) -> dict[str, bool]:
    """Which steps a `module_progress` row (or None) has completed."""
    if row is None:
        return dict.fromkeys(MODULE_STEPS, False)
    return {
        STEP_LEARN: row.learn_done_at is not None,
        STEP_DIAGNOSE: row.diagnose_done_at is not None,
        STEP_PRACTISE: row.practise_done_at is not None,
        STEP_CHECK: row.check_done_at is not None,
    }


def module_views(
    rows: Mapping[str, Any], struggle_ids: list[str] | None = None
) -> list[ModuleView]:
    """One view per module for the picker, from {module_id: progress row}.

    Modules that practise one of her class struggles come first (her order) and carry the reason.
    """
    from backend.app.class_profile import personalise

    wanted = [m for m, _ in personalise.struggle_moves(struggle_ids or [])]
    ordered = [m for m in wanted if m in module_ids()] + [
        m for m in module_ids() if m not in wanted
    ]
    views: list[ModuleView] = []
    for mid in ordered:
        card = module_card(mid)
        row = rows.get(mid)
        reason = personalise.because(mid, struggle_ids or [])
        views.append(
            ModuleView(
                module_id=mid,
                title_hi=card.title_hi,
                summary_hi=card.summary_hi,
                done=step_flags(row),
                check_passed=None if row is None else row.check_passed,
                diagnose_verdict=None if row is None else row.diagnose_verdict,
                because=personalise.label_of(reason) if reason is not None else "",
            )
        )
    return views
