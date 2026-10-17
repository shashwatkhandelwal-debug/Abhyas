"""T48 security pass: response headers and chat rate limiting."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from backend.app.auth.rate_limit import check_chat_rate_limit, reset_chat_rate_limits
from backend.app.config import settings


@pytest.mark.asyncio
async def test_security_headers_present(async_client: AsyncClient) -> None:
    response = await async_client.get("/healthz")
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "same-origin"
    assert "strict-transport-security" not in response.headers


@pytest.mark.asyncio
async def test_hsts_only_in_production(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    response = await async_client.get("/healthz")
    assert "max-age=31536000" in response.headers["strict-transport-security"]


def test_chat_rate_limit_blocks_after_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_chat_rate_limits()
    monkeypatch.setattr(settings, "CHAT_MAX_MESSAGES_PER_MINUTE", 2)
    check_chat_rate_limit("user-a")
    check_chat_rate_limit("user-a")
    with pytest.raises(HTTPException) as exc:
        check_chat_rate_limit("user-a")
    assert exc.value.status_code == 429
    check_chat_rate_limit("user-b")
    reset_chat_rate_limits()
