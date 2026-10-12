"""Question classifier role implementation matching spec/05 §5.8.

Classifies incoming teacher questions into pedagogy, classroom_management,
admin, or out_of_scope using Claude fast model (or MockLLM) with guard
validation, 1 retry, and deterministic fallback.
"""

from __future__ import annotations

import json
import logging
import unicodedata
from typing import Any

import httpx
from pydantic import ValidationError

from backend.app.config import settings
from backend.app.llm.client import LLMUnavailable, call_tool
from backend.app.llm.guards import guard_question_classifier
from backend.app.llm.prompts import load_prompt
from backend.app.llm.schemas import (
    QuestionClassificationResult,
    QuestionClassifierOutput,
)

logger = logging.getLogger("abhyas.llm.question_classifier")

PROMPT_VERSION = "v1"


def _deterministic_fallback(question: str) -> QuestionClassifierOutput:
    """Deterministic classification fallback on LLM or guard failure."""
    q_norm = unicodedata.normalize("NFC", question.strip())
    return QuestionClassifierOutput(
        category="pedagogy",
        needs_clarification=False,
        clarifying_question_hi="",
        search_query_hi=q_norm,
        confidence=0.0,
    )


async def classify_question(
    question: str,
) -> QuestionClassificationResult:
    """Classifies a teacher's free-form question (§5.8).

    Args:
        question: Teacher's question text in Hindi

    Returns:
        QuestionClassificationResult containing guarded classification output
    """
    clean_question = unicodedata.normalize("NFC", question.strip())
    if not clean_question:
        fb = QuestionClassifierOutput(
            category="pedagogy",
            needs_clarification=True,
            clarifying_question_hi="कृपया अपना सवाल थोड़ा विस्तार से पूछें।",
            search_query_hi="",
            confidence=0.0,
        )
        return QuestionClassificationResult(
            output=fb,
            guarded=True,
            guard_error=None,
            used_fallback=True,
        )

    prompt_template = load_prompt("question_classifier", PROMPT_VERSION)
    system_prompt = prompt_template.format(question=clean_question)

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": clean_question},
    ]

    for attempt in range(2):
        try:
            tool_input = await call_tool(
                role="question_classifier",
                model=settings.CLAUDE_MODEL_FAST,
                system=system_prompt,
                messages=messages,
                tool_name="question_classifier",
                input_schema=QuestionClassifierOutput.model_json_schema(),
                temperature=0.0,
                max_tokens=512,
                timeout_s=settings.LLM_TIMEOUT_SECONDS,
            )

            if (
                isinstance(tool_input, dict)
                and "input" in tool_input
                and isinstance(tool_input["input"], dict)
            ):
                tool_input = tool_input["input"]

            parsed = QuestionClassifierOutput.model_validate(tool_input)
            is_valid, error_msg = guard_question_classifier(parsed)

            if is_valid:
                return QuestionClassificationResult(
                    output=parsed,
                    guarded=True,
                    guard_error=None,
                    used_fallback=False,
                )

            logger.warning(
                "question_classifier guard failed on attempt %d: %s",
                attempt + 1,
                error_msg,
            )
            if attempt == 0:
                messages.append(
                    {
                        "role": "assistant",
                        "content": json.dumps(tool_input, ensure_ascii=False),
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your previous classification failed validation: {error_msg}. "
                            "Please fix it and return a valid question_classifier tool call."
                        ),
                    }
                )

        except (ValidationError, LLMUnavailable, httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.warning(
                "question_classifier call failed on attempt %d: %s",
                attempt + 1,
                exc,
            )
            if attempt == 0:
                continue

    logger.warning("question_classifier falling back to deterministic classification")
    fallback_output = _deterministic_fallback(clean_question)
    return QuestionClassificationResult(
        output=fallback_output,
        guarded=True,
        guard_error="Retries exhausted or LLM unavailable; used deterministic fallback",
        used_fallback=True,
    )


__all__ = [
    "classify_question",
]
