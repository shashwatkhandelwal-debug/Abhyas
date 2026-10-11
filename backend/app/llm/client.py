"""Claude LLM Client wrapper interface and tool-forced caller (spec/05 §5.1).

Task T08 implements full Anthropic API calling, caching, and MockLLM.
"""

from typing import Any


class LLMUnavailable(Exception):
    """Raised when LLM call fails after retries."""

    pass


async def call_tool(
    role: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    tool_name: str,
    input_schema: dict[str, Any],
    temperature: float = 0.0,
    max_tokens: int = 1024,
    timeout_s: float = 8.0,
) -> dict[str, Any]:
    """Spec 05 §5.1: Call Claude Messages API with forced tool use.

    Implemented in task T08.
    """
    raise NotImplementedError("Spec 05 §5.1: Implemented in T08")
