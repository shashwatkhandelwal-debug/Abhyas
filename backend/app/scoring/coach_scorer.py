"""Coach rubric scoring interface (spec/05 §5.6, spec/14 T12)."""

from typing import Any

from pydantic import BaseModel


class CoachFeedback(BaseModel):
    scores: dict[str, int]
    evidence: dict[str, str]
    strength_hi: str
    change_hi: str
    exact_words_hi: str
    confidence: float


async def score_rehearsal(
    move_payload: dict[str, Any],
    scene_transcript: list[dict[str, Any]],
    attempt: int = 1,
) -> CoachFeedback:
    """Evaluates rehearsal transcript against move rubric. Implemented in T12."""
    raise NotImplementedError("Spec 05 §5.6: Implemented in T12")
