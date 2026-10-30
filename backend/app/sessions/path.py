"""Personal move path computation matching spec/08 §8.5 (T23)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import yaml

from backend.app.config import FLAGGED_MOVES
from backend.app.content_models import MoveCard
from backend.app.sessions.path_score import MoveFacts, TeacherFacts, rank_moves

logger = logging.getLogger("abhyas.sessions.path")

DEFAULT_INDUCTION_ORDER: list[str] = [
    "NUM_PLACE_VALUE_BUNDLES",
    "NUM_SUB_REGROUP_BUNDLES",
    "NUM_ADD_CARRY_BUNDLES",
    "LIT_MATRA_BLENDING",
]


@dataclass
class MovePathEntry:
    position: int
    move_id: str
    reason: str


def load_induction_order(induction_path: Path | str | None = None) -> list[str]:
    """Loads induction track order from yaml if available, falling back to default."""
    if induction_path is None:
        induction_path = Path(__file__).parents[3] / "content" / "induction_track.yaml"
    else:
        induction_path = Path(induction_path)

    if induction_path.is_file():
        try:
            data = yaml.safe_load(induction_path.read_text(encoding="utf-8"))
            if isinstance(data, list) and all(isinstance(x, str) for x in data):
                return data
        except (yaml.YAMLError, OSError) as exc:
            logger.warning("Failed to load induction track from %s: %s", induction_path, exc)

    return list(DEFAULT_INDUCTION_ORDER)


def move_card_to_facts(card: MoveCard) -> MoveFacts:
    """Extracts MoveFacts from a loaded MoveCard."""
    domain_val = card.domain.value if hasattr(card.domain, "value") else str(card.domain)
    return MoveFacts(
        id=card.id,
        domain=domain_val,
        sankul_month=card.sankul_month,
        effective_acts=frozenset(card.teaching_acts_effective),
        tags=frozenset(card.tags),
    )


def load_all_move_cards(moves_dir: Path | str | None = None) -> list[MoveCard]:
    """Loads all valid move cards from content/moves/."""
    if moves_dir is None:
        moves_dir = Path(__file__).parents[3] / "content" / "moves"
    else:
        moves_dir = Path(moves_dir)

    cards: list[MoveCard] = []
    if moves_dir.is_dir():
        for f in sorted(moves_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "id" in data:
                    cards.append(MoveCard.model_validate(data))
            except (yaml.YAMLError, OSError, ValueError, KeyError) as exc:
                logger.warning("Failed loading move card %s: %s", f, exc)
    return cards


def compute_move_path(
    teacher_id: UUID | str,
    first_year: bool = False,
    classes: list[int] | tuple[int, ...] | None = None,
    placement_used_tell_answer: bool = False,
    current_month: int = 10,
    done_moves_evidence: dict[str, int] | None = None,
    min_rubric_scores: dict[str, float] | None = None,
    matched_question_tags: set[str] | frozenset[str] | None = None,
    moves_dir: Path | str | None = None,
) -> list[MovePathEntry]:
    """Computes deterministic personal move path per spec/08 §8.5 via path_score.rank_moves."""
    teacher_facts = TeacherFacts(
        current_month=current_month,
        classes=tuple(classes or ()),
        placement_used_tell_answer=placement_used_tell_answer,
        done_evidence=done_moves_evidence or {},
        min_rubric=min_rubric_scores or {},
        question_tags=frozenset(matched_question_tags or ()),
    )

    # Track B scenes are practised on demand (check-in, set-up), never placed in the weekly path
    cards = [c for c in load_all_move_cards(moves_dir) if c.id not in FLAGGED_MOVES]
    if cards:
        move_facts = [move_card_to_facts(card) for card in cards]
    else:
        # Fallback defaults if move directory is missing
        move_facts = [
            MoveFacts(
                "NUM_PLACE_VALUE_BUNDLES",
                "numeracy",
                "September",
                frozenset({"ask_to_explain", "concrete_representation"}),
                frozenset({"place_value", "number_sense", "ganit"}),
            ),
            MoveFacts(
                "NUM_SUB_REGROUP_BUNDLES",
                "numeracy",
                "October",
                frozenset({"ask_to_explain", "concrete_representation"}),
                frozenset({"subtraction", "regrouping", "place_value", "ganit"}),
            ),
            MoveFacts(
                "NUM_ADD_CARRY_BUNDLES",
                "numeracy",
                "November",
                frozenset({"ask_to_explain", "concrete_representation"}),
                frozenset({"addition", "regrouping", "carry", "place_value", "ganit"}),
            ),
            MoveFacts(
                "LIT_MATRA_BLENDING",
                "literacy",
                "October",
                frozenset({"phonics_sound_out", "model_step_aloud"}),
                frozenset({"reading", "phonics", "matra", "blending", "bhasha"}),
            ),
        ]

    fixed_order = tuple(load_induction_order()) if first_year else None
    ranked = rank_moves(move_facts, teacher_facts, fixed_order=fixed_order)

    return [
        MovePathEntry(
            position=entry.position,
            move_id=entry.move_id,
            reason="; ".join(entry.reasons),
        )
        for entry in ranked
    ]


__all__ = [
    "MovePathEntry",
    "compute_move_path",
    "load_induction_order",
    "DEFAULT_INDUCTION_ORDER",
    "load_all_move_cards",
    "move_card_to_facts",
]
