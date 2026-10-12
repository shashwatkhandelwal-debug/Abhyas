"""Unit tests for Teacher Chat PWA, templates, service worker, and asset budgets (spec/09 §9.2, T27)."""

import os
import unicodedata
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.guards import get_current_user
from backend.app.db.models import AppUser, Message, Teacher
from backend.app.db.session import get_db_session
from backend.app.web.teacher import STATIC_DIR
from backend.app.web.teacher import router as teacher_router

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_teacher_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
def mock_teacher(mock_teacher_id: uuid.UUID) -> Teacher:
    return Teacher(
        id=mock_teacher_id,
        name="डेमो शिक्षिका 2 (अनीता)",
        preferred_channel="web",
        lite_mode=False,
    )


@pytest.fixture
def teacher_pwa_app(mock_teacher_id: uuid.UUID, mock_teacher: Teacher) -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(teacher_router)

    teacher_user = AppUser(
        id=uuid.uuid4(),
        username="teacher.demo2",
        role="teacher",
        teacher_id=mock_teacher_id,
        display_name="डेमो शिक्षिका 2",
        password_hash="hash",
    )

    messages = [
        Message(
            id=uuid.uuid4(),
            teacher_id=mock_teacher_id,
            direction="out",
            channel="web",
            channel_msg_id="out-1",
            kind="text",
            text="नमस्ते! अभ्यास शुरू करें?",
            speaker="abhyas",
        ),
        Message(
            id=uuid.uuid4(),
            teacher_id=mock_teacher_id,
            direction="in",
            channel="web",
            channel_msg_id="in-1",
            kind="text",
            text="हाँ, तैयार हूँ।",
        ),
    ]

    async def mock_get_user() -> AppUser:
        return teacher_user

    async def mock_session() -> AsyncSession:
        db = AsyncMock(spec=AsyncSession)

        async def get_mock(entity: Any, ident: Any) -> Any:
            if entity is Teacher and ident == mock_teacher_id:
                return mock_teacher
            return None

        async def execute_mock(stmt: Any) -> Any:
            mock_res = MagicMock()
            mock_res.scalars.return_value.all.return_value = messages
            mock_res.scalar_one_or_none.return_value = mock_teacher
            return mock_res

        db.get.side_effect = get_mock
        db.execute.side_effect = execute_mock
        return db

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_db_session] = mock_session

    return app


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_teacher_chat_page(teacher_pwa_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        res = await client.get("/teacher")
        assert res.status_code == 200
        html = res.text

        # Core header & branding elements (§9.2)
        assert "अभ्यास" in html
        assert "दो अंकों की हासिल वाली घटाव" in html
        assert "चरण 4/7 · अभ्यास" in html

        # Rehearse child strip
        assert "बोर्ड: 52 − 17" in html
        assert "रवि" in html
        assert "प्रिया" in html
        assert "अमन" in html

        # Initial messages rendered server-side
        assert "नमस्ते! अभ्यास शुरू करें?" in html
        assert "हाँ, तैयार हूँ।" in html

        # Composer controls
        assert 'id="chat-input"' in html
        assert 'id="btn-mic"' in html
        assert 'id="btn-send"' in html
        assert 'id="recording-overlay"' in html

        # Static script imports
        assert "/static/app.css" in html
        assert "/static/recorder.js" in html
        assert "/static/chat.js" in html


@pytest.mark.asyncio
async def test_teacher_chat_role_guard(teacher_pwa_app: FastAPI) -> None:
    arp_user = AppUser(
        id=uuid.uuid4(),
        username="arp.demo",
        role="arp",
        display_name="ARP रमेश",
        password_hash="hash",
    )

    teacher_pwa_app.dependency_overrides[get_current_user] = lambda: arp_user

    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        res = await client.get("/teacher")
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_manifest_endpoint(teacher_pwa_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        res = await client.get("/manifest.json")
        assert res.status_code == 200
        assert "application/manifest+json" in res.headers.get("content-type", "")
        data = res.json()
        assert data["name"] == "अभ्यास"
        assert data["short_name"] == "Abhyas"
        assert data["display"] == "standalone"
        assert data["theme_color"] == "#1F6F5C"


@pytest.mark.asyncio
async def test_service_worker_endpoint(teacher_pwa_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        res = await client.get("/sw.js")
        assert res.status_code == 200
        assert "javascript" in res.headers.get("content-type", "")
        # Header required for root scope (§9.2)
        assert res.headers.get("Service-Worker-Allowed") == "/"
        content = res.text
        assert "CACHE_NAME_STATIC" in content
        assert "offline.html" in content


@pytest.mark.asyncio
async def test_offline_page_endpoint(teacher_pwa_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        res = await client.get("/offline.html")
        assert res.status_code == 200
        html = res.text
        assert "ऑफ़लाइन" in html
        assert "कक्षा-अभ्यास चेकलिस्ट" in html
        assert "52 − 17" in html
        assert "messages_cache" in html


def test_asset_budget_under_150kb() -> None:
    """Strict performance budget test: HTML + CSS + JS < 150 KB uncompressed (spec/09 §9, §9.2)."""
    static_files = list(STATIC_DIR.glob("*"))
    template_file = STATIC_DIR.parent / "templates" / "teacher.html"

    all_files = [*static_files, template_file]
    total_bytes = sum(os.path.getsize(f) for f in all_files if f.is_file())
    total_kb = total_bytes / 1024

    # Assert total budget is strictly less than 150 KB
    assert total_kb < 150.0, f"Assets exceed 150 KB budget: {total_kb:.2f} KB"
    assert total_kb < 80.0, (
        f"Expected assets to comfortably sit below 80 KB, got: {total_kb:.2f} KB"
    )


def test_nfc_normalization_for_pwa_assets() -> None:
    """All Hindi strings in templates, offline HTML, and client JS must be NFC normalized."""
    text_files = [
        STATIC_DIR.parent / "templates" / "teacher.html",
        STATIC_DIR / "offline.html",
        STATIC_DIR / "chat.js",
        STATIC_DIR / "recorder.js",
        STATIC_DIR / "manifest.json",
        STATIC_DIR / "app.css",
    ]

    for path in text_files:
        content = path.read_text(encoding="utf-8")
        normalized = unicodedata.normalize("NFC", content)
        assert content == normalized, f"File {path.name} contains non-NFC normalized text"
