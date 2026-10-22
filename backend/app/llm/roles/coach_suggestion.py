"""coach_suggestion role: one tip after a scene, grounded in retrieved FLN excerpts.

Haiku, forced tool, schema-validated and guarded (the cited chunk must be in the retrieved set,
the tip must come from it), one retry. The deterministic fallback is to say nothing: no retrieval
support or a failed guard means no suggestion.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from backend.app.config import settings
from backend.app.llm.client import LLMUnavailable, call_tool, logged_role, mark_fallback
from backend.app.llm.guard_stats import record_guard_event
from backend.app.llm.guards import guard_coach_suggestion
from backend.app.llm.prompts import load_prompt
from backend.app.llm.schemas import CoachSuggestionOutput, RetrievedChunk

logger = logging.getLogger("abhyas.llm.coach_suggestion")

PROMPT_VERSION = "v1"
_EXCERPT_CHARS = 700


class SuggestionResult(BaseModel):
    suggestion_hi: str | None = None
    chunk: RetrievedChunk | None = None
    used_fallback: bool = False  # True when the answer is "no suggestion" after a failure


@logged_role("coach_suggestion", lambda: settings.CLAUDE_MODEL_FAST)
async def suggest_from_sources(
    move_title_hi: str, change_hi: str, chunks: list[RetrievedChunk]
) -> SuggestionResult:
    """A cited suggestion, or `suggestion_hi=None` (no support, nothing relevant, guard failure)."""
    if not chunks:
        return SuggestionResult()  # nothing retrieved: no suggestion, no LLM call
    system = load_prompt("coach_suggestion", PROMPT_VERSION).format(
        move_title_hi=move_title_hi,
        change_hi=change_hi,
        max_words=settings.COACH_SUGGESTION_MAX_WORDS,
        excerpts_block="\n\n".join(
            f"{c.chunk_id}: {c.section}\n{c.text[:_EXCERPT_CHARS]}" for c in chunks
        ),
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": "Give the suggestion."}]
    for attempt in range(2):
        try:
            tool_input = await call_tool(
                role="coach_suggestion",
                model=settings.CLAUDE_MODEL_FAST,
                system=system,
                messages=messages,
                tool_name="coach_suggestion",
                input_schema=CoachSuggestionOutput.model_json_schema(),
                temperature=0.2,
                max_tokens=400,
                timeout_s=settings.LLM_TIMEOUT_SECONDS,
            )
            parsed = CoachSuggestionOutput.model_validate(tool_input)
            if not parsed.suggestion_hi.strip() and not parsed.chunk_id.strip():
                return SuggestionResult()  # the model found nothing usable: say nothing
            ok, why = guard_coach_suggestion(parsed, chunks)
            record_guard_event("coach_suggestion", attempt, ok, why)
            if ok:
                chunk = next(c for c in chunks if c.chunk_id == parsed.chunk_id)
                return SuggestionResult(suggestion_hi=parsed.suggestion_hi.strip(), chunk=chunk)
            logger.warning("coach_suggestion guard failed (attempt %d): %s", attempt + 1, why)
            if attempt == 0:
                messages.append(
                    {"role": "assistant", "content": json.dumps(tool_input, ensure_ascii=False)}
                )
                messages.append(
                    {
                        "role": "user",
                        "content": f"That failed a check: {why}. Fix it or leave empty.",
                    }
                )
        except LLMUnavailable as exc:
            logger.warning("coach_suggestion unavailable: %s", exc)
            break
        except (ValidationError, httpx.HTTPError, json.JSONDecodeError, TimeoutError) as exc:
            logger.warning("coach_suggestion call failed (attempt %d): %s", attempt + 1, exc)
    mark_fallback()
    return SuggestionResult(used_fallback=True)


__all__ = ["SuggestionResult", "suggest_from_sources"]
