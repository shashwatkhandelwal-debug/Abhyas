"""Scoring package exports."""

from backend.app.scoring.coach_scorer import CoachFeedback, score_rehearsal
from backend.app.scoring.fidelity_scorer import ExplainScoreResult, check_fidelity

__all__ = [
    "CoachFeedback",
    "score_rehearsal",
    "ExplainScoreResult",
    "check_fidelity",
]
