"""Pytest configuration and test fixtures."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["WHATSAPP_ACCESS_TOKEN"] = "mock_whatsapp_token"
os.environ["STT_PROVIDER"] = "mock"
os.environ["TTS_PROVIDER"] = "mock"
os.environ["LLM_CALL_LOG_ENABLED"] = "false"

from backend.app.config import settings
from backend.app.main import app

settings.LLM_CALL_LOG_ENABLED = False


@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def _reset_speech_rate_limits():
    """A 429 in one test starts a cool-down for that provider; it must not outlive the test."""
    from backend.app.speech import stt, tts

    stt.reset_rate_limits()
    tts.reset_rate_limits()
    yield
    stt.reset_rate_limits()
    tts.reset_rate_limits()


@pytest.fixture(autouse=True)
def _reset_chat_rate_limits():
    from backend.app.auth.rate_limit import reset_chat_rate_limits

    reset_chat_rate_limits()
    yield
    reset_chat_rate_limits()
