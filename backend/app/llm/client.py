"""Claude LLM Client wrapper interface and tool-forced caller (spec/05 §5.1).

Task T08 implements full Anthropic API calling, caching, and MockLLM.
"""

from typing import Any


class LLMUnavailable(Exception):
    """Raised when LLM call fails after retries (spec/05 §5.1)."""

    pass


class MockLLM:
    """Mock LLM returning golden outputs or schema defaults (spec/05 §5.1).

    Selected when ANTHROPIC_API_KEY is empty or LLM_PROVIDER=mock.
    Full fixture loader implemented by Lane B in task T08.
    """

    def __init__(self, golden_dir: str | None = None) -> None:
        self.golden_dir = golden_dir

    async def call_tool(
        self,
        role: str,
        tool_name: str,
        input_schema: dict[str, Any],
        system: str = "",
        messages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Returns mock golden dictionary conforming to input_schema."""
        # Simple schema-valid mock return default
        return {}


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

    Uses Anthropic Messages API with tools=[{name, description, input_schema}]
    and tool_choice={"type": "tool", "name": tool_name}; returns the tool input dict.
    Implemented by Lane B in task T08.
    """
    raise NotImplementedError("spec/05 §5.1 — call_tool owned by Lane B (T08)")
