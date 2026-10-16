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
from backend.app.config import settings
from backend.app.core.messages import get_message
from backend.app.db.models import AppUser, Message, Scene, Teacher
from backend.app.db.session import get_db_session
from backend.app.web.teacher import STATIC_DIR, templates
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
        assert 'id="board-problem"' in html
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
    template_files = [
        STATIC_DIR.parent / "templates" / "teacher.html",
        STATIC_DIR.parent / "templates" / "chat.html",
    ]

    all_files = [*static_files, *template_files]
    total_bytes = sum(os.path.getsize(f) for f in all_files if f.is_file())
    total_kb = total_bytes / 1024

    # Assert total budget is strictly less than 150 KB
    assert total_kb < 150.0, f"Assets exceed 150 KB budget: {total_kb:.2f} KB"
    assert total_kb < 90.0, (
        f"Expected assets to comfortably sit below 90 KB, got: {total_kb:.2f} KB"
    )


def test_nfc_normalization_for_pwa_assets() -> None:
    """All Hindi strings in templates, offline HTML, and client JS must be NFC normalized."""
    text_files = [
        STATIC_DIR.parent / "templates" / "teacher.html",
        STATIC_DIR.parent / "templates" / "chat.html",
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


# ── Review Item 5 Tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_teacher_chat_page_board_empty_without_scene(
    teacher_pwa_app: FastAPI,
) -> None:
    """Item 5: Board text is empty string when no scene is active."""
    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        res = await client.get("/teacher")
        assert res.status_code == 200
        # Board problem element exists but contains no text
        assert '<span class="board-problem" id="board-problem"></span>' in res.text
        # Hard-coded '52 − 17' or '52 - 17' must NOT appear on the board
        assert "बोर्ड: 52" not in res.text


@pytest.mark.asyncio
async def test_teacher_chat_page_board_shows_active_problem(
    teacher_pwa_app: FastAPI, mock_teacher_id: uuid.UUID, mock_teacher: Teacher
) -> None:
    """Item 5: Board shows active problem if set on active scene."""
    active_scene = Scene(
        id=uuid.uuid4(),
        teacher_id=mock_teacher_id,
        status="active",
        engine_state={"board_problem": "बोर्ड: 43 − 27"},
    )

    async def mock_db_with_scene() -> AsyncSession:
        db = AsyncMock(spec=AsyncSession)

        async def get_mock(entity: Any, ident: Any) -> Any:
            if entity is Teacher and ident == mock_teacher_id:
                return mock_teacher
            return None

        async def execute_mock(stmt: Any) -> Any:
            mock_res = MagicMock()
            str_stmt = str(stmt)
            if "FROM scene" in str_stmt:
                mock_res.scalar_one_or_none.return_value = active_scene
            elif "FROM message" in str_stmt:
                mock_res.scalars.return_value.all.return_value = []
            elif "FROM teacher" in str_stmt:
                mock_res.scalar_one_or_none.return_value = mock_teacher
            return mock_res

        db.get.side_effect = get_mock
        db.execute.side_effect = execute_mock
        return db

    teacher_pwa_app.dependency_overrides[get_db_session] = mock_db_with_scene

    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        res = await client.get("/teacher")
        assert res.status_code == 200
        assert '<span class="board-problem" id="board-problem">बोर्ड: 43 − 27</span>' in res.text


@pytest.mark.asyncio
async def test_teacher_chat_page_chips_load_when_demo_mode_true(
    teacher_pwa_app: FastAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Item 5: Chips load from demo_chips.json only when DEMO_MODE=True."""
    import json
    from pathlib import Path

    sample_chips = [
        {
            "id": "c1",
            "chip_label": "रवि से पूछें",
            "text_hi": "रवि, तुमने 43 में से 27 कैसे घटाया?",
            "audio_available": False,
        },
        {
            "id": "c2",
            "chip_label": "बंडल दिखाएँ",
            "text_hi": "ये 4 बंडल हैं।",
            "audio_available": True,
        },
    ]

    chips_file = Path("eval/samples/demo_chips.json")
    chips_file.parent.mkdir(parents=True, exist_ok=True)
    created_temp_file = False
    if not chips_file.exists():
        chips_file.write_text(json.dumps(sample_chips, ensure_ascii=False), encoding="utf-8")
        created_temp_file = True

    try:
        # Case 1: DEMO_MODE=True -> chips rendered
        monkeypatch.setattr(settings, "DEMO_MODE", True)
        async with AsyncClient(
            transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
        ) as client:
            res = await client.get("/teacher?demo=1")
            assert res.status_code == 200
            assert "रवि से पूछें" in res.text
            assert 'data-audio-available="false"' in res.text
            # Hard-coded chips must not be present
            assert "रवि, 52 में 2 में से 7 क्यों नहीं घट सकता?" not in res.text

        # Case 2: DEMO_MODE=False -> no chips rendered
        monkeypatch.setattr(settings, "DEMO_MODE", False)
        async with AsyncClient(
            transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
        ) as client:
            res_no_demo = await client.get("/teacher")
            assert res_no_demo.status_code == 200
            assert "रवि से पूछें" not in res_no_demo.text
    finally:
        if created_temp_file and chips_file.exists():
            chips_file.unlink()


@pytest.mark.asyncio
async def test_teacher_chat_page_no_chips_when_json_missing(
    teacher_pwa_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 5: Render no chips if demo_chips.json is missing even if DEMO_MODE=True."""
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    # Point load_demo_chips to a non-existent file
    from backend.app.web import teacher as teacher_mod

    monkeypatch.setattr(teacher_mod, "load_demo_chips", lambda: [])

    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        res = await client.get("/teacher?demo=1")
        assert res.status_code == 200
        assert "demo-chip" not in res.text


# ── T27 PWA, Offline & Template Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_chat_alias_page(teacher_pwa_app: FastAPI) -> None:
    """GET /chat serves the same teacher chat PWA interface (§9.2, T27)."""
    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        res = await client.get("/chat")
        assert res.status_code == 200
        html = res.text

        # Core header & branding elements
        assert "अभ्यास" in html
        assert "दो अंकों की हासिल वाली घटाव" in html
        assert "चरण 4/7 · अभ्यास" in html

        # Rehearse child strip with 3 children
        assert 'id="board-problem"' in html
        assert "रवि" in html
        assert "प्रिया" in html
        assert "अमन" in html

        # Composer controls
        assert 'id="chat-input"' in html
        assert 'id="btn-mic"' in html
        assert 'id="btn-send"' in html
        assert 'id="recording-overlay"' in html

        # Offline banner with catalog data attribute
        assert 'id="network-banner"' in html
        assert "data-offline-text=" in html
        assert "आप ऑफ़लाइन हैं" in html


def test_chat_html_template_renders_directly() -> None:
    """chat.html template renders cleanly with Jinja context (§9.2, T27)."""
    template = templates.get_template("chat.html")
    context = {
        "teacher_name": "शिक्षिका सुमित्रा",
        "csrf_token": "test-csrf-token",
        "move_title": "दो अंकों की घटाव",
        "step_chip": "चरण 4/7 · अभ्यास",
        "board_problem": "बोर्ड: 52 − 17",
        "demo_mode": False,
        "is_online": True,
        "lite_mode": False,
        "initial_messages": [
            {
                "id": "1",
                "direction": "out",
                "kind": "text",
                "text": "नमस्ते!",
                "speaker": "abhyas",
                "time_str": "10:00",
            }
        ],
    }
    rendered = template.render(context)
    assert "अभ्यास" in rendered
    assert "शिक्षिका सुमित्रा" in rendered
    assert "दो अंकों की घटाव" in rendered
    assert "चरण 4/7 · अभ्यास" in rendered
    assert "बोर्ड: 52 − 17" in rendered
    assert "रवि" in rendered
    assert "प्रिया" in rendered
    assert "अमन" in rendered
    assert "नमस्ते!" in rendered
    assert 'id="chat-input"' in rendered
    assert 'id="btn-mic"' in rendered
    assert 'id="btn-send"' in rendered
    assert "data-offline-text=" in rendered


def test_offline_banner_text_and_catalog() -> None:
    """Offline banner text is from message catalog and includes 'आप ऑफ़लाइन हैं' (§9.2, T27)."""
    banner_text = get_message("ui_offline_banner")
    short_text = get_message("ui_offline_short")

    assert "आप ऑफ़लाइन हैं" in banner_text
    assert short_text == "आप ऑफ़लाइन हैं"

    # Template data attributes check
    teacher_template = (STATIC_DIR.parent / "templates" / "teacher.html").read_text(
        encoding="utf-8"
    )
    chat_template = (STATIC_DIR.parent / "templates" / "chat.html").read_text(encoding="utf-8")
    assert "data-offline-text=\"{{ get_message('ui_offline_banner') }}\"" in teacher_template
    assert "data-offline-text=\"{{ get_message('ui_offline_banner') }}\"" in chat_template

    # Offline fallback page check
    offline_page = (STATIC_DIR / "offline.html").read_text(encoding="utf-8")
    assert "आप ऑफ़लाइन हैं" in offline_page
    assert "messages_cache" in offline_page


def test_client_chat_js_contract() -> None:
    """chat.js fulfills outbox, IndexedDB, retry backoff, and polling contracts (spec/09 §9.2)."""
    js_content = (STATIC_DIR / "chat.js").read_text(encoding="utf-8")

    # IndexedDB configuration
    assert "const DB_NAME = 'abhyas_chat_db'" in js_content
    assert "const STORE_OUTBOX = 'outbox'" in js_content
    assert "const STORE_MESSAGES = 'messages_cache'" in js_content
    assert "keyPath: 'client_msg_id'" in js_content
    assert "keyPath: 'id'" in js_content

    # Retry backoff steps (2, 4, 8, 16, 30s)
    assert "BACKOFF_STEPS = [2000, 4000, 8000, 16000, 30000]" in js_content

    # Polling delays: 1.5s when pending, 20s when idle
    assert "state.isPending ? 1500 : 20000" in js_content

    # API endpoints
    assert "'/api/chat/text'" in js_content
    assert "'/api/chat/button'" in js_content
    assert "'/api/chat/audio'" in js_content
    assert "'/api/chat/messages'" in js_content
    assert "'/api/settings'" in js_content

    # Network listeners
    assert "window.addEventListener('online', updateOnlineStatus)" in js_content
    assert "window.addEventListener('offline', updateOnlineStatus)" in js_content
    assert "data-offline-text" in js_content


def test_client_recorder_js_contract() -> None:
    """recorder.js fulfills audio recording constraints (spec/09 §9.2)."""
    js_content = (STATIC_DIR / "recorder.js").read_text(encoding="utf-8")

    # Audio recorder class definition
    assert "class AudioRecorder" in js_content

    # Constraints: 16kbps mono, max 90s, min 0.7s discard
    assert "audioBitsPerSecond: 16000" in js_content
    assert "channelCount: 1" in js_content
    assert "echoCancellation: true" in js_content
    assert "noiseSuppression: true" in js_content
    assert "this.maxDurationSec = 90" in js_content
    assert "this.minDurationSec = 0.7" in js_content

    # Supported audio MIME types
    assert "'audio/webm;codecs=opus'" in js_content
    assert "'audio/mp4'" in js_content


def test_service_worker_contract() -> None:
    """sw.js fulfills caching, LRU 30 for audio, and offline fallback (spec/09 §9.2)."""
    sw_content = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")

    # Cache names
    assert "CACHE_NAME_STATIC = 'abhyas-static-v1'" in sw_content
    assert "CACHE_NAME_AUDIO = 'abhyas-audio-v1'" in sw_content

    # Audio LRU 30 items
    assert "MAX_AUDIO_CACHE_ITEMS = 30" in sw_content
    assert "url.pathname.startsWith('/api/audio/')" in sw_content

    # Static assets cache list
    assert "'/static/app.css'" in sw_content
    assert "'/static/chat.js'" in sw_content
    assert "'/static/recorder.js'" in sw_content
    assert "'/static/manifest.json'" in sw_content
    assert "'/offline.html'" in sw_content

    # Offline navigation fallback
    assert "cachedOffline" in sw_content
    assert "'/offline.html'" in sw_content
