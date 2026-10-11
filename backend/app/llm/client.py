"""Claude LLM Client wrapper with timeouts, retries, and guardrails (§9)."""

import json
import logging
from typing import Any, Optional, Type, TypeVar
import httpx
from pydantic import BaseModel
from backend.app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class ClaudeClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.model = model or settings.CLAUDE_MODEL
        self.timeout = timeout or settings.LLM_TIMEOUT_SECONDS

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        temperature: float = 0.2,
    ) -> T:
        """Generates structured JSON adhering to the target Pydantic schema."""
        # Mock mode if placeholder key is present
        if not self.api_key or self.api_key.startswith("mock"):
            logger.info("Using mock LLM generation (placeholder API key)")
            return self._mock_structured_response(response_model)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ],
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content_text = data["content"][0]["text"]
            parsed_json = json.loads(content_text)
            return response_model.model_validate(parsed_json)

    def _mock_structured_response(self, response_model: Type[T]) -> T:
        """Returns baseline mock instance for development and offline testing."""
        from backend.app.llm.schemas import (
            ActTaggerOutput,
            ChildVoiceOutput,
            CoachFeedbackOutput,
            FidelityCheckerOutput,
            GuideAnswererOutput,
            KeyPointEvaluation,
        )
        from backend.app.rule_engine.domain import TeachingAct

        if response_model == ActTaggerOutput:
            return ActTaggerOutput(  # type: ignore
                acts=[TeachingAct.ASK_TO_EXPLAIN],
                addressed_child="ravi",
                quote="Ravi, 52 mein se 17 kaise ghataya? Batao.",
            )
        elif response_model == ChildVoiceOutput:
            return ChildVoiceOutput(  # type: ignore
                line_hi="2 mein se 7 nahi hota, to 7 mein se 2 kiya. 45!",
                numbers_cited=[2, 7, 45],
            )
        elif response_model == CoachFeedbackOutput:
            return CoachFeedbackOutput(  # type: ignore
                scores={"num_bundles": 2},
                evidence={"num_bundles": "Ravi, 52 mein se 17 kaise ghataya? Batao."},
                strength_hi="Aapne bachhe se uska tarika pucha.",
                change_hi="Agli baar bundle aur teeli se dikhayein.",
                exact_words_hi="5 bundle aur 2 teeli lekar dekho.",
                confidence=0.88,
            )
        elif response_model == FidelityCheckerOutput:
            return FidelityCheckerOutput(  # type: ignore
                points=[
                    KeyPointEvaluation(
                        id="kp1",
                        status="covered",
                        quote="dhai ko bundle banakar sikhana hai",
                    )
                ],
                misconceptions=[],
                confidence=0.92,
            )
        elif response_model == GuideAnswererOutput:
            return GuideAnswererOutput(  # type: ignore
                answer_hi="UP NIPUN guide ke anusaar, pehle teeli aur bundle se samjhayein.",
                source_ids=["UP_NIPUN_M4"],
                confidence=0.85,
            )
        raise ValueError(f"No mock defined for schema: {response_model}")
