"""Fidelity scoring for 'Explain it back' voice note (§6)."""

from backend.app.config import settings
from backend.app.llm.client import ClaudeClient
from backend.app.llm.guards import validate_fidelity_check
from backend.app.llm.prompts import FIDELITY_CHECKER_SYSTEM_PROMPT
from backend.app.llm.schemas import FidelityCheckerOutput
from backend.app.rule_engine.domain import Move


class FidelityScorer:
    def __init__(self, claude_client: ClaudeClient):
        self.client = claude_client

    async def score_explanation(
        self,
        explanation_transcript: str,
        move: Move,
    ) -> tuple[FidelityCheckerOutput, bool]:
        """Evaluates whether the 1-minute voice explanation covers the key points."""
        key_points_json = [kp.model_dump() for kp in move.key_points]
        user_prompt = f"""
Key Points to Cover:
{key_points_json}

Teacher's Spoken Explanation:
{explanation_transcript}
"""
        result = await self.client.generate_structured(
            system_prompt=FIDELITY_CHECKER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=FidelityCheckerOutput,
            temperature=0.1,
        )

        is_valid, _ = validate_fidelity_check(result, explanation_transcript)
        requires_review = (not is_valid) or (result.confidence < settings.COACH_CONFIDENCE_THRESHOLD)

        return result, requires_review
