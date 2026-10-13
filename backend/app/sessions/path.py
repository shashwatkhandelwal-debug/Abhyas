"""Personal move path computation matching spec/08 §8.5."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import yaml

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


def compute_move_path(
    teacher_id: UUID | str,
    first_year: bool = False,
    classes: list[int] | None = None,
    placement_used_tell_answer: bool = False,
    current_month: int = 10,
    done_moves_evidence: dict[str, int] | None = None,
    min_rubric_scores: dict[str, float] | None = None,
    matched_question_tags: set[str] | None = None,
) -> list[MovePathEntry]:
    """Computes deterministic personal move path per spec/08 §8.5.

    Deterministic score per move (lower = sooner):
    score = month_rank * 10
          - 15 if placement used tell_answer and move.effective has ask_to_explain
          - 10 if teacher.classes contains 1 and move.domain == literacy or move.id startswith NUM_PLACE_VALUE
          - 5 * (2 - min rubric score on this move's criteria in last attempt)
          - 8 if teacher asked a question whose category matched move.tags
          + 100 if move already DONE with evidence >= 2
    """
    classes_list = classes or []
    done_ev = done_moves_evidence or {}
    rubrics = min_rubric_scores or {}
    q_tags = matched_question_tags or set()

    if first_year:
        order = load_induction_order()
        return [
            MovePathEntry(
                position=i + 1,
                move_id=m_id,
                reason="first_year_teacher_induction_fixed_order",
            )
            for i, m_id in enumerate(order)
        ]

    candidate_moves = [
        {
            "id": "NUM_PLACE_VALUE_BUNDLES",
            "domain": "math",
            "sankul_month": 10,
            "has_ask_to_explain": True,
            "tags": {"place_value", "math", "concrete"},
        },
        {
            "id": "NUM_SUB_REGROUP_BUNDLES",
            "domain": "math",
            "sankul_month": 10,
            "has_ask_to_explain": True,
            "tags": {"subtraction", "math", "regrouping"},
        },
        {
            "id": "NUM_ADD_CARRY_BUNDLES",
            "domain": "math",
            "sankul_month": 11,
            "has_ask_to_explain": True,
            "tags": {"addition", "math", "carry"},
        },
        {
            "id": "LIT_MATRA_BLENDING",
            "domain": "literacy",
            "sankul_month": 11,
            "has_ask_to_explain": False,
            "tags": {"literacy", "matra", "phonics"},
        },
    ]

    scored: list[tuple[float, str, str]] = []

    for m in candidate_moves:
        move_id = str(m["id"])
        month_diff = max(0, int(str(m["sankul_month"])) - current_month)
        score = month_diff * 10.0
        reasons: list[str] = [f"month_priority: +{month_diff * 10}"]

        if placement_used_tell_answer and m["has_ask_to_explain"]:
            score -= 15.0
            reasons.append("placement_tell_answer_explanation_practice: -15")

        if 1 in classes_list and (
            m["domain"] == "literacy" or move_id.startswith("NUM_PLACE_VALUE")
        ):
            score -= 10.0
            reasons.append("grade_1_foundational_practice: -10")

        if move_id in rubrics:
            min_r = rubrics[move_id]
            delta = 5.0 * (2.0 - min_r)
            score -= delta
            reasons.append(f"prior_performance_improvement: -{delta:.1f}")

        tags = m["tags"]
        if isinstance(tags, set) and tags.intersection(q_tags):
            score -= 8.0
            reasons.append("matched_teacher_question: -8")

        if done_ev.get(move_id, 0) >= 2:
            score += 100.0
            reasons.append("previously_completed: +100")

        scored.append((score, move_id, "; ".join(reasons)))

    # Sort ascending by score
    scored.sort(key=lambda x: x[0])

    return [
        MovePathEntry(position=i + 1, move_id=m_id, reason=reason)
        for i, (_, m_id, reason) in enumerate(scored)
    ]


__all__ = [
    "MovePathEntry",
    "compute_move_path",
    "load_induction_order",
    "DEFAULT_INDUCTION_ORDER",
]
