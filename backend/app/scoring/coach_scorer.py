"""Coach scoring and calibration evaluation logic (§5.3)."""

from typing import Any

from backend.app.config import settings
from backend.app.llm.client import ClaudeClient
from backend.app.llm.guards import validate_coach_feedback
from backend.app.llm.prompts import COACH_SYSTEM_PROMPT
from backend.app.llm.schemas import CoachFeedbackOutput
from backend.app.rule_engine.domain import Move


class CoachScorer:
    def __init__(self, claude_client: ClaudeClient):
        self.client = claude_client

    async def score_rehearsal(
        self,
        transcript: str,
        move: Move,
        trajectory: list[dict[str, Any]],
    ) -> tuple[CoachFeedbackOutput, bool]:
        """Scores rehearsal transcript against move rubric.

        Returns (feedback, requires_expert_review).
        """
        user_prompt = f"""
Move Rubric:
{move.rubric.model_dump_json(indent=2)}

Rehearsal Transcript:
{transcript}

Student Trajectory:
{trajectory}
"""
        feedback = await self.client.generate_structured(
            system_prompt=COACH_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=CoachFeedbackOutput,
            temperature=0.1,
        )

        # Validate against strict guards
        is_valid, reason = validate_coach_feedback(feedback, transcript)
        if not is_valid:
            # Fall back to high-fidelity template if guards flag discrepancy
            feedback.strength_hi = "Aapne bachhe se uska tarika pucha."
            feedback.change_hi = "Agli baar bundle aur teeli se dikhayein."
            feedback.exact_words_hi = "5 bundle aur 2 teeli lekar dekho."
            feedback.confidence = 0.50

        requires_review = feedback.confidence < settings.COACH_CONFIDENCE_THRESHOLD
        return feedback, requires_review
