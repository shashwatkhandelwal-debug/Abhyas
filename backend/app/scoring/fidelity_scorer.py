"""Fidelity checker interface (spec/05 §5.7, spec/14 T13)."""

from typing import Any

from pydantic import BaseModel


class ExplainScoreResult(BaseModel):
    points: dict[str, bool]
    misconceptions: list[str]
    confidence: float


async def check_fidelity(
    move_payload: dict[str, Any],
    teacher_explanation: str,
) -> ExplainScoreResult:
    """Checks teacher explain-back audio transcript. Implemented in T13."""
    raise NotImplementedError("Spec 05 §5.7: Implemented in T13")
