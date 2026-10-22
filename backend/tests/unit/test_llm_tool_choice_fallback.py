"""Models that reject forced tool_choice (claude-sonnet-5-5) must still return tool output."""

import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import anthropic
import pytest

from backend.app.config import settings
from backend.app.llm import client as client_mod
from backend.app.llm.client import call_tool

try:
    import httpx2 as sdk_httpx
except ImportError:  # pragma: no cover
    import httpx as sdk_httpx  # type: ignore[no-redef]

TOOL = "emit_tags"
SCHEMA: dict[str, Any] = {"type": "object", "properties": {"acts": {"type": "array"}}}
REJECTING = "claude-sonnet-5-5"


@pytest.fixture
def bodies() -> Iterator[list[dict[str, Any]]]:
    captured: list[dict[str, Any]] = []

    def handler(request: sdk_httpx.Request) -> sdk_httpx.Response:
        body = json.loads(request.content)
        captured.append(body)
        if body["model"] == REJECTING and body["tool_choice"]["type"] in ("tool", "any"):
            return sdk_httpx.Response(
                400,
                json={
                    "type": "error",
                    "error": {
                        "type": "invalid_request_error",
                        "message": 'tool_choice: type "tool" and "any" are not supported '
                        f"for this model ({REJECTING})",
                    },
                },
            )
        return sdk_httpx.Response(
            200,
            json={
                "id": "m",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": [
                    {"type": "tool_use", "id": "t", "name": TOOL, "input": {"acts": ["x"]}}
                ],
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    sdk = anthropic.AsyncAnthropic(
        api_key="k",
        base_url="https://anthropic.test",
        max_retries=0,
        http_client=sdk_httpx.AsyncClient(transport=sdk_httpx.MockTransport(handler)),
    )

    async def _usage() -> int:
        return 0

    with (
        patch.object(settings, "ANTHROPIC_API_KEY", "k"),
        patch.object(settings, "LLM_PROVIDER", "anthropic"),
        patch.object(client_mod, "_anthropic_client", sdk),
        patch.object(client_mod, "get_daily_token_usage_db", _usage),
        patch.object(client_mod, "_MODELS_WITHOUT_FORCED_TOOL_CHOICE", set()),
    ):
        yield captured


async def _call(model: str) -> dict[str, Any]:
    return await call_tool(
        role="coach",
        model=model,
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        tool_name=TOOL,
        input_schema=SCHEMA,
    )


@pytest.mark.asyncio
async def test_sonnet_retries_with_auto_and_remembers(bodies: list[dict[str, Any]]) -> None:
    assert await _call(REJECTING) == {"acts": ["x"]}
    assert [b["tool_choice"]["type"] for b in bodies] == ["tool", "auto"]
    assert "ONLY by calling" in bodies[1]["system"][-1]["text"]
    # preamble text + adaptive thinking ate the budget in production: headroom, thinking off
    assert bodies[1]["max_tokens"] == bodies[0]["max_tokens"] + 512
    assert bodies[1]["thinking"] == {"type": "between_tools"}
    assert "thinking" not in bodies[0]
    # second call goes straight to auto: no wasted 400
    await _call(REJECTING)
    assert [b["tool_choice"]["type"] for b in bodies][2:] == ["auto"]


@pytest.mark.asyncio
async def test_haiku_keeps_forced_tool_choice(bodies: list[dict[str, Any]]) -> None:
    await _call(settings.CLAUDE_MODEL_FAST)
    assert bodies[0]["tool_choice"] == {"type": "tool", "name": TOOL}
    assert len(bodies) == 1
