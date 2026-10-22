"""Translator role: on-demand English translation of a Hindi bubble (child / coach / guide).

Uses the fast Claude model with forced tool use. Every output is schema-validated and guarded
(`guard_translation`: numbers kept, no Hindi left, plausible length); one retry with the failure
named, then `TranslationUnavailable` so the UI can show an inline error with a retry button.
Nothing here decides what a child says; it only renders an existing line in English.
"""

from __future__ import annotations

import json
import logging
import unicodedata
from typing import Any

import httpx
from pydantic import ValidationError

from backend.app.config import settings
from backend.app.llm.client import LLMUnavailable, call_tool, logged_role
from backend.app.llm.guard_stats import record_guard_event
from backend.app.llm.guards import guard_translation
from backend.app.llm.prompts import load_prompt
from backend.app.llm.schemas import TranslationOutput

logger = logging.getLogger("abhyas.llm.translator")

PROMPT_VERSION = "v1"


class TranslationUnavailable(Exception):
    """The LLM could not produce a guarded translation (unavailable, or the guard failed twice)."""


@logged_role("translator", lambda: settings.CLAUDE_MODEL_FAST)
async def translate_to_english(text_hi: str) -> str:
    """English translation of `text_hi`, or raises `TranslationUnavailable`."""
    source = unicodedata.normalize("NFC", text_hi.strip())
    if not source:
        raise TranslationUnavailable("empty source text")
    system_prompt = load_prompt("translator", PROMPT_VERSION)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": f"<text>\n{source}\n</text>"},
    ]
    last_error = "no attempt made"
    for attempt in range(2):
        try:
            tool_input = await call_tool(
                role="translator",
                model=settings.CLAUDE_MODEL_FAST,
                system=system_prompt,
                messages=messages,
                tool_name="translator",
                input_schema=TranslationOutput.model_json_schema(),
                max_tokens=settings.TRANSLATE_MAX_OUTPUT_TOKENS,
                timeout_s=settings.LLM_TIMEOUT_SECONDS,
                prompt_version=PROMPT_VERSION,
            )
            parsed = TranslationOutput.model_validate(tool_input)
        except LLMUnavailable as exc:
            logger.warning("translator LLM unavailable: %s", exc)
            raise TranslationUnavailable("llm unavailable") from exc
        except (ValidationError, httpx.HTTPError, json.JSONDecodeError, TimeoutError) as exc:
            last_error = f"call failed: {type(exc).__name__}"
            logger.warning("translator call failed on attempt %d: %s", attempt + 1, last_error)
            continue
        ok, reason = guard_translation(source, parsed.text_en)
        record_guard_event("translator", attempt, ok, reason)
        if ok:
            return unicodedata.normalize("NFC", parsed.text_en.strip())
        last_error = reason
        logger.warning("translator guard failed on attempt %d: %s", attempt + 1, reason)
        messages.append(
            {"role": "assistant", "content": json.dumps(tool_input, ensure_ascii=False)}
        )
        messages.append(
            {
                "role": "user",
                "content": f"Your translation failed validation: {reason}. Fix it and return "
                "only the translator tool call.",
            }
        )
    raise TranslationUnavailable(last_error)


__all__ = ["TranslationUnavailable", "translate_to_english"]
