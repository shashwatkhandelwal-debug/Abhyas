"""Intent router role implementation matching spec/05 §5.3.

Classifies incoming teacher messages when keyword intents do not match
and session is not in REHEARSE, using Claude fast model (or MockLLM)
with guard validation, 1 retry, and deterministic fallback.
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Any

from pydantic import ValidationError

from backend.app.config import settings
from backend.app.llm.client import LLMUnavailable, call_tool
from backend.app.llm.guard_stats import record_guard_event
from backend.app.llm.guards import guard_intent_router
from backend.app.llm.prompts import load_prompt
from backend.app.llm.schemas import IntentRouterOutput

logger = logging.getLogger("abhyas.llm.intent_router")

PROMPT_VERSION = "v1"


def fallback_intent_router(state: str) -> IntentRouterOutput:
    """Deterministic fallback matching spec/05 §5.3.

    `answer_for_step` for EXPLAIN_BACK/REFLECT, else `unclear` (send help menu).
    """
    clean_state = state.strip().upper()
    if clean_state in ("EXPLAIN_BACK", "REFLECT"):
        return IntentRouterOutput(intent="answer_for_step", confidence=0.0)
    return IntentRouterOutput(intent="unclear", confidence=0.0)


async def route_intent(
    text: str,
    *,
    state: str,
    state_description_hi: str = "",
    expected_input: str = "",
) -> IntentRouterOutput:
    """Routes an incoming teacher message when keyword matching did not resolve (§5.3).

    Args:
        text: Teacher's incoming message
        state: Current session state name
        state_description_hi: Hindi description of current state
        expected_input: Description of what the app expects at this state

    Returns:
        IntentRouterOutput containing the routed intent and confidence
    """
    clean_text = unicodedata.normalize("NFC", text.strip())
    if not clean_text:
        return fallback_intent_router(state)

    try:
        prompt_template = load_prompt("intent_router", version=PROMPT_VERSION)
    except FileNotFoundError:
        logger.error("Prompt template for intent_router.%s not found", PROMPT_VERSION)
        return fallback_intent_router(state)

    system_prompt = prompt_template.format(
        state=state,
        state_description_hi=state_description_hi,
        expected_input=expected_input,
        text=clean_text,
    )

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": f"Classify the following message:\n\n{clean_text}"}
    ]

    schema = IntentRouterOutput.model_json_schema()

    for attempt in range(settings.LLM_MAX_RETRIES + 1):
        try:
            tool_data = await call_tool(
                role="intent_router",
                model=settings.CLAUDE_MODEL_FAST,
                system=system_prompt,
                messages=messages,
                tool_name="intent_router",
                input_schema=schema,
                temperature=0.0,
                max_tokens=256,
                timeout_s=settings.LLM_TIMEOUT_SECONDS,
                prompt_version=PROMPT_VERSION,
            )
            output = IntentRouterOutput.model_validate(tool_data)
            is_valid, msg = guard_intent_router(output)
            record_guard_event("intent_router", attempt, is_valid, msg)
            if is_valid:
                # spec §5.3 guard: confidence < 0.5 -> treat as answer_for_step
                # if current state expects free speech (EXPLAIN_BACK, REFLECT), else unclear.
                if output.confidence < 0.5:
                    if state.strip().upper() in ("EXPLAIN_BACK", "REFLECT"):
                        return IntentRouterOutput(
                            intent="answer_for_step",
                            confidence=output.confidence,
                        )
                    return IntentRouterOutput(
                        intent="unclear",
                        confidence=output.confidence,
                    )
                return output

            logger.warning(
                "Guard check failed for intent_router (attempt %d): %s",
                attempt + 1,
                msg,
            )
            messages.append(
                {
                    "role": "user",
                    "content": f"Your previous output failed the guard: {msg}. Please correct it.",
                }
            )
        except (ValidationError, LLMUnavailable, TimeoutError, OSError) as exc:
            logger.warning(
                "Error calling intent_router (attempt %d): %s",
                attempt + 1,
                exc,
            )
            if attempt == settings.LLM_MAX_RETRIES:
                break
            messages.append(
                {
                    "role": "user",
                    "content": f"Your previous output was invalid: {exc}. Please return valid output.",
                }
            )

    logger.info("Using deterministic fallback for intent_router on state %s", state)
    return fallback_intent_router(state)
