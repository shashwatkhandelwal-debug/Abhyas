"""Contract tests between llm/client.py and the installed anthropic SDK (live bug: temperature).

Render installed the latest anthropic, whose AsyncMessages.create() has no `temperature`
parameter, so every LLM call raised TypeError. These tests use the real installed SDK.
"""

import inspect
import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import anthropic
import pytest
from anthropic.resources.messages import AsyncMessages
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming

from backend.app.config import settings
from backend.app.llm import client as client_mod
from backend.app.llm.client import build_create_kwargs, call_tool

try:  # anthropic>=1.x ships its own httpx fork; MockTransport must come from it
    import httpx2 as sdk_httpx
except ImportError:  # pragma: no cover - older SDKs use httpx
    import httpx as sdk_httpx  # type: ignore[no-redef]

TEST_KEY = "test-anthropic-key"
BASE_URL = "https://anthropic.test"
TOOL_NAME = "emit_tags"
TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"acts": {"type": "array", "items": {"type": "string"}}},
    "required": ["acts"],
}


def _installed_create_params() -> set[str]:
    return set(inspect.signature(AsyncMessages.create).parameters) - {"self"}


def _sample_kwargs(temperature: float | None = 0.3) -> dict[str, Any]:
    return build_create_kwargs(
        model=settings.CLAUDE_MODEL_FAST,
        max_tokens=256,
        system_blocks=[{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": "नमस्ते"}],
        tools=[{"name": TOOL_NAME, "description": "d", "input_schema": TOOL_SCHEMA}],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        temperature=temperature,
    )


def test_create_kwargs_are_parameters_of_installed_sdk() -> None:
    params = _installed_create_params()
    kwargs = _sample_kwargs(temperature=0.3)
    unknown = sorted(set(kwargs) - params)
    assert unknown == [], f"anthropic {anthropic.__version__} create() rejects {unknown}"
    # temperature is sent only when this SDK version accepts it
    assert ("temperature" in kwargs) == ("temperature" in params)


def test_create_kwargs_are_keys_of_sdk_request_typeddict() -> None:
    allowed = (
        MessageCreateParamsNonStreaming.__required_keys__
        | MessageCreateParamsNonStreaming.__optional_keys__
    )
    assert set(_sample_kwargs()) <= allowed


@pytest.fixture
def mocked_sdk_client() -> Iterator[list[dict[str, Any]]]:
    """Real AsyncAnthropic over an httpx MockTransport; yields captured request bodies."""
    captured: list[dict[str, Any]] = []

    def handler(request: sdk_httpx.Request) -> sdk_httpx.Response:
        assert request.url.path == "/v1/messages"
        # anthropic 1.x sends x-api-key; 2.0 sends "Authorization: Bearer <key>"
        assert TEST_KEY in (
            request.headers.get("x-api-key"),
            request.headers.get("authorization", "").removeprefix("Bearer "),
        )
        body = json.loads(request.content)
        captured.append(body)
        return sdk_httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_test",
                        "name": TOOL_NAME,
                        "input": {"acts": ["ask_explain"]},
                    }
                ],
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 12, "output_tokens": 5},
            },
        )

    sdk_client = anthropic.AsyncAnthropic(
        api_key=TEST_KEY,
        base_url=BASE_URL,
        max_retries=0,
        http_client=sdk_httpx.AsyncClient(transport=sdk_httpx.MockTransport(handler)),
    )

    async def _no_db_usage() -> int:
        return 0

    with (
        patch.object(settings, "ANTHROPIC_API_KEY", TEST_KEY),
        patch.object(settings, "LLM_PROVIDER", "anthropic"),
        patch.object(client_mod, "_anthropic_client", sdk_client),
        patch.object(client_mod, "get_daily_token_usage_db", _no_db_usage),
    ):
        yield captured


@pytest.mark.asyncio
async def test_call_tool_sends_valid_request_body(mocked_sdk_client: list[dict[str, Any]]) -> None:
    result = await call_tool(
        role="act_tagger",
        model=settings.CLAUDE_MODEL_FAST,
        system="system prompt",
        messages=[{"role": "user", "content": "रवि, तुमने कैसे घटाया?"}],
        tool_name=TOOL_NAME,
        input_schema=TOOL_SCHEMA,
        temperature=0.0,
    )

    assert result == {"acts": ["ask_explain"]}
    assert len(mocked_sdk_client) == 1
    body = mocked_sdk_client[0]
    allowed = (
        MessageCreateParamsNonStreaming.__required_keys__
        | MessageCreateParamsNonStreaming.__optional_keys__
    )
    assert set(body) <= allowed, sorted(set(body) - allowed)
    if "temperature" not in _installed_create_params():
        assert "temperature" not in body
    assert body["model"] == settings.CLAUDE_MODEL_FAST
    assert body["max_tokens"] > 0
    assert body["system"] == [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
    assert body["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    assert body["tools"][0]["name"] == TOOL_NAME
    assert body["tools"][0]["input_schema"] == TOOL_SCHEMA
    assert body["messages"] == [{"role": "user", "content": "रवि, तुमने कैसे घटाया?"}]
