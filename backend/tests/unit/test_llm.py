"""Unit tests for LLM client, MockLLM, token budget guard, and retry handling (T08)."""

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from anthropic import (
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
)
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from backend.app.config import settings
from backend.app.llm.client import (
    LLMUnavailable,
    MockLLM,
    ModelConfigurationError,
    TokenBudgetExceeded,
    TokenBudgetTracker,
    budget_tracker,
    call_tool,
    close_anthropic_client,
    get_anthropic_client,
    load_prompt,
    verify_configured_models,
    verify_production_models,
)


@pytest.fixture(autouse=True)
def _reset_anthropic_singleton() -> None:
    import backend.app.llm.client as client_mod

    client_mod._anthropic_client = None


@pytest.mark.asyncio
async def test_mock_llm_returns_golden() -> None:
    """MockLLM returns golden output when available for role."""
    mock = MockLLM()
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {"acts": {"type": "array"}},
    }
    result = await mock.call_tool(
        role="act_tagger",
        tool_name="tag_acts",
        input_schema=schema,
    )
    assert "acts" in result
    assert result["acts"] == ["ask_to_explain"]


@pytest.mark.asyncio
async def test_mock_llm_schema_fallback() -> None:
    """MockLLM generates valid default dictionary for unknown role."""
    mock = MockLLM()
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "score": {"type": "integer"},
            "tag": {"type": "string", "enum": ["A", "B"]},
            "active": {"type": "boolean"},
        },
    }
    result = await mock.call_tool(
        role="unknown_role_xyz",
        tool_name="test_tool",
        input_schema=schema,
    )
    assert result["score"] == 0
    assert result["tag"] == "A"
    assert result["active"] is False


def test_token_budget_tracker() -> None:
    """TokenBudgetTracker records consumption and triggers budget exceeded."""
    tracker = TokenBudgetTracker(daily_budget=1000)
    tracker.reset()
    assert tracker.is_exceeded() is False

    tracker.record_usage(input_tokens=400, output_tokens=200, cache_read_tokens=100)
    assert tracker.get_tokens_used_today() == 700
    assert tracker.is_exceeded() is False

    tracker.record_usage(input_tokens=300, output_tokens=100)
    assert tracker.get_tokens_used_today() == 1100
    assert tracker.is_exceeded() is True

    tracker.reset()
    assert tracker.get_tokens_used_today() == 0
    assert tracker.is_exceeded() is False


def test_load_prompt() -> None:
    """load_prompt correctly reads act_tagger.v1.md and caches it."""
    prompt = load_prompt("act_tagger", "v1")
    assert "Teaching-act taxonomy" in prompt

    # Verify prompt caching
    cached_prompt = load_prompt("act_tagger", "v1")
    assert cached_prompt == prompt

    # Verify missing prompt fallback
    missing_prompt = load_prompt("nonexistent_role_xyz", "v99")
    assert missing_prompt == ""


@pytest.mark.asyncio
async def test_call_tool_mock_mode() -> None:
    """call_tool executes via MockLLM when provider is mock."""
    with patch.object(settings, "LLM_PROVIDER", "mock"):
        result = await call_tool(
            role="intent_router",
            model="claude-haiku-5-5",
            system="system prompt",
            messages=[{"role": "user", "content": "नमस्ते"}],
            tool_name="route_intent",
            input_schema={"type": "object", "properties": {"intent": {"type": "string"}}},
        )
        assert result["intent"] == "answer_for_step"


@pytest.mark.asyncio
async def test_call_tool_token_budget_exceeded() -> None:
    """call_tool raises TokenBudgetExceeded when daily token budget is reached."""
    with (
        patch.object(settings, "LLM_PROVIDER", "anthropic"),
        patch.object(settings, "ANTHROPIC_API_KEY", "sk-ant-test"),
    ):
        budget_tracker.reset()
        budget_tracker.record_usage(
            input_tokens=settings.LLM_DAILY_TOKEN_BUDGET + 1, output_tokens=0
        )
        try:
            with pytest.raises(TokenBudgetExceeded):
                await call_tool(
                    role="act_tagger",
                    model="claude-haiku-5-5",
                    system="sys",
                    messages=[],
                    tool_name="tag",
                    input_schema={},
                )
        finally:
            budget_tracker.reset()


@pytest.mark.asyncio
async def test_call_tool_successful_anthropic() -> None:
    """call_tool calls Anthropic client and returns extracted tool input."""
    mock_response = Message(
        id="msg_123",
        type="message",
        role="assistant",
        content=[
            TextBlock(type="text", text="Thinking..."),
            ToolUseBlock(
                type="tool_use",
                id="tool_1",
                name="test_tool",
                input={"status": "ok", "count": 42},
            ),
        ],
        model="claude-haiku-5-5",
        usage=Usage(input_tokens=100, output_tokens=50),
    )

    with (
        patch.object(settings, "LLM_PROVIDER", "anthropic"),
        patch.object(settings, "ANTHROPIC_API_KEY", "sk-ant-test"),
    ):
        with patch("anthropic.AsyncAnthropic") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            budget_tracker.reset()
            result = await call_tool(
                role="test_role",
                model="claude-haiku-5-5",
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
                tool_name="test_tool",
                input_schema={"properties": {"status": {"type": "string"}}},
            )
            assert result == {"status": "ok", "count": 42}
            assert budget_tracker.get_tokens_used_today() == 150
            budget_tracker.reset()


@pytest.mark.asyncio
async def test_call_tool_retry_on_timeout_success() -> None:
    """call_tool retries on timeout and succeeds on retry."""
    mock_response = Message(
        id="msg_124",
        type="message",
        role="assistant",
        content=[
            ToolUseBlock(
                type="tool_use",
                id="tool_2",
                name="test_tool",
                input={"recovered": True},
            )
        ],
        model="claude-haiku-5-5",
        usage=Usage(input_tokens=80, output_tokens=20),
    )

    fake_request = httpx.Request("POST", "https://api.anthropic.com")
    timeout_err = APITimeoutError(request=fake_request)

    with (
        patch.object(settings, "LLM_PROVIDER", "anthropic"),
        patch.object(settings, "ANTHROPIC_API_KEY", "sk-ant-test"),
    ):
        with patch("anthropic.AsyncAnthropic") as mock_client_cls:
            mock_client = AsyncMock()
            # Fails first, succeeds second
            mock_client.messages.create = AsyncMock(side_effect=[timeout_err, mock_response])
            mock_client_cls.return_value = mock_client

            budget_tracker.reset()
            result = await call_tool(
                role="test_role",
                model="claude-haiku-5-5",
                system="sys",
                messages=[],
                tool_name="test_tool",
                input_schema={},
            )
            assert result == {"recovered": True}
            assert mock_client.messages.create.call_count == 2
            budget_tracker.reset()


@pytest.mark.asyncio
async def test_call_tool_failure_after_max_retries() -> None:
    """call_tool raises LLMUnavailable after retry limit is exceeded."""
    fake_request = httpx.Request("POST", "https://api.anthropic.com")
    conn_err = APIConnectionError(request=fake_request)

    with (
        patch.object(settings, "LLM_PROVIDER", "anthropic"),
        patch.object(settings, "ANTHROPIC_API_KEY", "sk-ant-test"),
    ):
        with patch("anthropic.AsyncAnthropic") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(side_effect=conn_err)
            mock_client_cls.return_value = mock_client

            budget_tracker.reset()
            with pytest.raises(LLMUnavailable) as exc_info:
                await call_tool(
                    role="test_role",
                    model="claude-haiku-5-5",
                    system="sys",
                    messages=[],
                    tool_name="test_tool",
                    input_schema={},
                )
            assert "LLM call failed after retries" in str(exc_info.value)
            # 1 initial + 1 retry = 2 calls
            assert mock_client.messages.create.call_count == 2
            budget_tracker.reset()


@pytest.mark.asyncio
async def test_call_tool_5xx_retry() -> None:
    """call_tool retries on 500 server error."""
    fake_request = httpx.Request("POST", "https://api.anthropic.com")
    fake_response = httpx.Response(500, request=fake_request)
    server_err = InternalServerError("Internal server error", response=fake_response, body=None)

    mock_response = Message(
        id="msg_125",
        type="message",
        role="assistant",
        content=[
            ToolUseBlock(
                type="tool_use",
                id="tool_3",
                name="test_tool",
                input={"ok_after_500": True},
            )
        ],
        model="claude-haiku-5-5",
        usage=Usage(input_tokens=10, output_tokens=5),
    )

    with (
        patch.object(settings, "LLM_PROVIDER", "anthropic"),
        patch.object(settings, "ANTHROPIC_API_KEY", "sk-ant-test"),
    ):
        with patch("anthropic.AsyncAnthropic") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(side_effect=[server_err, mock_response])
            mock_client_cls.return_value = mock_client

            budget_tracker.reset()
            result = await call_tool(
                role="test_role",
                model="claude-haiku-5-5",
                system="sys",
                messages=[],
                tool_name="test_tool",
                input_schema={},
            )
            assert result == {"ok_after_500": True}
            assert mock_client.messages.create.call_count == 2
            budget_tracker.reset()


@pytest.mark.asyncio
async def test_verify_models_skips_in_development() -> None:
    """verify_configured_models is a no-op in non-production environments."""
    with patch.object(settings, "ENVIRONMENT", "development"):
        results = await verify_configured_models()
        assert results == {}


@pytest.mark.asyncio
async def test_verify_models_production_success() -> None:
    """verify_configured_models succeeds when all models respond."""
    mock_response = Message(
        id="msg_ping",
        type="message",
        role="assistant",
        content=[TextBlock(type="text", text="pong")],
        model="claude-haiku-5-5",
        usage=Usage(input_tokens=1, output_tokens=1),
    )

    with (
        patch.object(settings, "ENVIRONMENT", "production"),
        patch.object(settings, "ANTHROPIC_API_KEY", "sk-ant-valid-key"),
        patch.object(settings, "CLAUDE_MODEL_FAST", "claude-haiku-5-5"),
        patch.object(settings, "CLAUDE_MODEL_SMART", "claude-sonnet-5-5"),
        patch.object(settings, "CLAUDE_MODEL_BUILD", "claude-sonnet-5-5"),
    ):
        with patch("anthropic.AsyncAnthropic") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            results = await verify_configured_models()
            assert results["CLAUDE_MODEL_FAST"] is True
            assert results["CLAUDE_MODEL_SMART"] is True
            assert results["CLAUDE_MODEL_BUILD"] is True
            # Two unique model IDs were tested
            assert mock_client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_verify_models_missing_api_key_production() -> None:
    """verify_configured_models fails fast if ANTHROPIC_API_KEY is missing in prod."""
    with (
        patch.object(settings, "ENVIRONMENT", "production"),
        patch.object(settings, "ANTHROPIC_API_KEY", ""),
    ):
        with pytest.raises(ModelConfigurationError) as exc_info:
            await verify_configured_models()
        assert "ANTHROPIC_API_KEY" in str(exc_info.value)


@pytest.mark.asyncio
async def test_verify_models_fast_rejected() -> None:
    """verify_configured_models fails fast naming CLAUDE_MODEL_FAST when rejected."""
    assert verify_production_models is verify_configured_models
    fake_request = httpx.Request("POST", "https://api.anthropic.com")
    fake_response = httpx.Response(404, request=fake_request)
    not_found_err = NotFoundError("Model not found", response=fake_response, body=None)

    with (
        patch.object(settings, "ENVIRONMENT", "production"),
        patch.object(settings, "ANTHROPIC_API_KEY", "sk-ant-test"),
        patch.object(settings, "CLAUDE_MODEL_FAST", "invalid-fast-model"),
    ):
        with patch("anthropic.AsyncAnthropic") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(side_effect=not_found_err)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ModelConfigurationError) as exc_info:
                await verify_configured_models()
            assert "CLAUDE_MODEL_FAST" in str(exc_info.value)
            assert "invalid-fast-model" in str(exc_info.value)


@pytest.mark.asyncio
async def test_verify_models_smart_rejected() -> None:
    """verify_configured_models fails fast naming CLAUDE_MODEL_SMART when rejected."""
    fake_request = httpx.Request("POST", "https://api.anthropic.com")
    fake_response = httpx.Response(400, request=fake_request)
    bad_req_err = BadRequestError("Model does not exist", response=fake_response, body=None)

    mock_ok = Message(
        id="msg_ok",
        type="message",
        role="assistant",
        content=[TextBlock(type="text", text="pong")],
        model="claude-haiku-5-5",
        usage=Usage(input_tokens=1, output_tokens=1),
    )

    with (
        patch.object(settings, "ENVIRONMENT", "production"),
        patch.object(settings, "ANTHROPIC_API_KEY", "sk-ant-test"),
        patch.object(settings, "CLAUDE_MODEL_FAST", "claude-haiku-5-5"),
        patch.object(settings, "CLAUDE_MODEL_SMART", "invalid-smart-model"),
        patch.object(settings, "CLAUDE_MODEL_BUILD", "claude-sonnet-5-5"),
    ):
        with patch("anthropic.AsyncAnthropic") as mock_client_cls:
            mock_client = AsyncMock()
            # Fast succeeds, smart fails
            mock_client.messages.create = AsyncMock(side_effect=[mock_ok, bad_req_err])
            mock_client_cls.return_value = mock_client

            with pytest.raises(ModelConfigurationError) as exc_info:
                await verify_configured_models()
            assert "CLAUDE_MODEL_SMART" in str(exc_info.value)
            assert "invalid-smart-model" in str(exc_info.value)


@pytest.mark.asyncio
async def test_verify_models_build_rejected() -> None:
    """verify_configured_models fails fast naming CLAUDE_MODEL_BUILD when rejected."""
    fake_request = httpx.Request("POST", "https://api.anthropic.com")
    fake_response = httpx.Response(404, request=fake_request)
    not_found_err = NotFoundError("Model not found", response=fake_response, body=None)

    mock_ok = Message(
        id="msg_ok",
        type="message",
        role="assistant",
        content=[TextBlock(type="text", text="pong")],
        model="claude-haiku-5-5",
        usage=Usage(input_tokens=1, output_tokens=1),
    )

    with (
        patch.object(settings, "ENVIRONMENT", "production"),
        patch.object(settings, "ANTHROPIC_API_KEY", "sk-ant-test"),
        patch.object(settings, "CLAUDE_MODEL_FAST", "claude-haiku-5-5"),
        patch.object(settings, "CLAUDE_MODEL_SMART", "claude-sonnet-5-5"),
        patch.object(settings, "CLAUDE_MODEL_BUILD", "invalid-build-model"),
    ):
        with patch("anthropic.AsyncAnthropic") as mock_client_cls:
            mock_client = AsyncMock()
            # Fast succeeds, smart succeeds, build fails
            mock_client.messages.create = AsyncMock(side_effect=[mock_ok, mock_ok, not_found_err])
            mock_client_cls.return_value = mock_client

            with pytest.raises(ModelConfigurationError) as exc_info:
                await verify_configured_models()
            assert "CLAUDE_MODEL_BUILD" in str(exc_info.value)
            assert "invalid-build-model" in str(exc_info.value)


@pytest.mark.asyncio
async def test_shared_anthropic_client() -> None:
    """get_anthropic_client returns shared singleton and close_anthropic_client cleans up."""
    client1 = get_anthropic_client()
    client2 = get_anthropic_client()
    assert client1 is client2
    await close_anthropic_client()
