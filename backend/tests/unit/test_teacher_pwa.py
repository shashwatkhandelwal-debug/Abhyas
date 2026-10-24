"""Unit tests for Teacher Chat PWA, templates, service worker, and asset budgets (spec/09 §9.2, T27)."""

import os
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient
from markupsafe import escape
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.guards import get_current_user
from backend.app.config import settings
from backend.app.core.messages import get_message
from backend.app.db.models import AppUser, Message, Scene, Teacher
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
        start_seen_at=datetime.now(UTC),  # past the one-time Start here screen
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
            created_at=datetime(2026, 10, 15, 10, 0, tzinfo=UTC),
        ),
        Message(
            id=uuid.uuid4(),
            teacher_id=mock_teacher_id,
            direction="in",
            channel="web",
            channel_msg_id="in-1",
            kind="text",
            text="हाँ, तैयार हूँ।",
            created_at=datetime(2026, 10, 15, 10, 1, tzinfo=UTC),
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
        assert 'id="header-move-title"' in html  # the move title and step follow her session
        assert 'id="header-step"' in html

        # The scene bar exists but is hidden, and no children are listed, outside a scene
        assert re.search(r'<section class="scene-bar" id="scene-bar"[^>]* hidden>', html)
        assert 'class="child-pill' not in html

        # Initial messages rendered server-side
        assert "नमस्ते! अभ्यास शुरू करें?" in html
        assert "हाँ, तैयार हूँ।" in html
        assert 'data-created-at="2026-10-15T10:00:00+00:00"' in html

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
    template_files = [STATIC_DIR.parent / "templates" / "teacher.html"]

    all_files = [*static_files, *template_files]
    total_bytes = sum(os.path.getsize(f) for f in all_files if f.is_file())
    total_kb = total_bytes / 1024

    # Assert total budget is strictly less than 150 KB
    assert total_kb < 150.0, f"Assets exceed 150 KB budget: {total_kb:.2f} KB"
    # This sums every static file and the chat template (the chat first load is teacher.html +
    # app.css + chat.js + recorder.js, far less gzipped).
    assert total_kb < 130.0, (
        f"Expected assets to comfortably sit below 130 KB, got: {total_kb:.2f} KB"
    )


def test_nfc_normalization_for_pwa_assets() -> None:
    """All Hindi strings in templates, offline HTML, and client JS must be NFC normalized."""
    text_files = [
        STATIC_DIR.parent / "templates" / "teacher.html",
        STATIC_DIR.parent / "templates" / "offline.html",
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


def _scene_state_json() -> dict[str, Any]:
    """A one-on-one scene on 43 - 27 with Ravi, as the page reads it from the scene row."""
    from backend.app.rule_engine.domain import ChildRuntime, Domain, Problem, SceneState

    problem = Problem(type="sub", a=43, b=27)
    return SceneState(
        move_id="NUM_SUB_REGROUP_BUNDLES",
        domain=Domain.NUMERACY,
        effective_acts=[],
        target_causes=[],
        items=[problem],
        current_item=problem,
        children=[
            ChildRuntime(
                persona_id="ravi", misconception="SUB_SMALLER_FROM_LARGER", temperament="confident"
            )
        ],
        one_on_one=True,
        max_turns=10,
    ).model_dump(mode="json")


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
        # The scene bar is hidden and its board card is empty
        assert re.search(r'<section class="scene-bar" id="scene-bar"[^>]* hidden>', res.text)
        assert 'id="sb-board"></span>' in res.text
        # Hard-coded '52 − 17' or '52 - 17' must NOT appear on the board
        assert "52 − 17" not in res.text


@pytest.mark.asyncio
async def test_teacher_chat_page_board_shows_active_problem(
    teacher_pwa_app: FastAPI, mock_teacher_id: uuid.UUID, mock_teacher: Teacher
) -> None:
    """Item 5: Board shows active problem if set on active scene."""
    active_scene = Scene(
        id=uuid.uuid4(),
        teacher_id=mock_teacher_id,
        status="active",
        engine_state=_scene_state_json(),
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
        assert 'id="sb-board">43 − 27</span>' in res.text
        assert not re.search(r'<section class="scene-bar" id="scene-bar"[^>]* hidden>', res.text)
        assert get_message("ui_scene_one_title", child=get_message("speaker_ravi")) in res.text
        assert get_message("ui_scene_turn", turn=0, max=10) in res.text
        assert 'class="child-pill' not in res.text  # one-on-one: only that child, no switcher


@pytest.mark.asyncio
async def test_sample_lines_show_in_demo_mode_only_folded_under_a_plain_title(
    teacher_pwa_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sample lines are a judge's helper: demo mode only, a plain title, a note on each line."""
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        res = await client.get("/teacher?demo=1")
        assert res.status_code == 200
        assert '<details class="sample-tray" id="sample-tray">' in res.text  # closed until opened
        assert "नमूना पंक्ति आज़माएँ: दबाकर भेजें" in res.text
        assert 'class="demo-chip"' in res.text and 'class="sample-note"' in res.text
        assert "ऐसा सवाल जो हैंडबुक में नहीं है" in res.text
        assert "हिंग्लिश" not in res.text and "Explain-back" not in res.text  # no jargon labels

    # DEMO_MODE off and a real speech provider: no sample lines at all
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "STT_PROVIDER", "sarvam")
    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        res_no_demo = await client.get("/teacher")
        assert res_no_demo.status_code == 200
        assert "sample-tray" not in res_no_demo.text and "demo-chip" not in res_no_demo.text


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
        assert 'id="header-move-title"' in html  # the move title and step follow her session
        assert 'id="header-step"' in html

        # The scene bar exists but is hidden, and no children are listed, outside a scene
        assert re.search(r'<section class="scene-bar" id="scene-bar"[^>]* hidden>', html)
        assert 'class="child-pill' not in html

        # Composer controls
        assert 'id="chat-input"' in html
        assert 'id="btn-mic"' in html
        assert 'id="btn-send"' in html
        assert 'id="recording-overlay"' in html

        # Offline banner with catalog data attribute
        assert 'id="network-banner"' in html
        assert "data-offline-text=" in html
        assert "आप ऑफ़लाइन हैं" in html


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
    assert "data-offline-text=\"{{ get_message('ui_offline_banner') }}\"" in teacher_template

    # Offline fallback page check
    offline_template = (STATIC_DIR.parent / "templates" / "offline.html").read_text(
        encoding="utf-8"
    )
    assert "ui_offline_notice" in offline_template  # text comes from the catalog, both languages
    assert "messages_cache" in offline_template


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

    # Constraints: 16kbps mono; auto-stop 60 s and discard < 1 s (REC_* in config.py override)
    assert "audioBitsPerSecond: 16000" in js_content
    assert "channelCount: 1" in js_content
    assert "echoCancellation: true" in js_content
    assert "noiseSuppression: true" in js_content
    assert "const REC_DEFAULTS = { maxSec: 60, minSec: 1 }" in js_content
    assert "this.maxDurationSec = c.maxSec" in js_content
    assert "this.minDurationSec = c.minSec" in js_content

    # Supported audio MIME types
    assert "'audio/webm;codecs=opus'" in js_content
    assert "'audio/mp4'" in js_content


def test_service_worker_contract() -> None:
    """sw.js fulfills caching, LRU 30 for audio, and offline fallback (spec/09 §9.2)."""
    sw_content = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")

    # Cache names
    assert "CACHE_NAME_STATIC = STATIC_CACHE_PREFIX + BUILD_VERSION" in sw_content
    assert "'abhyas-static-v1'" not in sw_content  # fixed name pinned returning browsers to old JS
    assert "CACHE_NAME_AUDIO = 'abhyas-audio-v1'" in sw_content

    # Audio LRU 30 items
    assert "MAX_AUDIO_CACHE_ITEMS = 30" in sw_content
    assert "url.pathname.startsWith('/api/audio/')" in sw_content

    # Static assets cache list
    assert "'/static/app.css?v=' + BUILD_VERSION" in sw_content
    assert "'/static/chat.js?v=' + BUILD_VERSION" in sw_content
    assert "'/static/recorder.js?v=' + BUILD_VERSION" in sw_content
    assert "'/static/manifest.json'" in sw_content
    assert "'/offline.html'" in sw_content

    # Offline navigation fallback
    assert "cachedOffline" in sw_content
    assert "'/offline.html'" in sw_content


@pytest.mark.asyncio
async def test_chat_page_serves_ui_strings_json_and_status_slots(teacher_pwa_app: FastAPI) -> None:
    """chat.js gets every ui_chat_* string as JSON, and the page has the slots it writes into."""
    import json
    import re

    from backend.app.core.messages import get_catalog
    from backend.app.web.teacher import CHAT_UI_PREFIX

    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        html = (await client.get("/teacher")).text
    match = re.search(r'<script type="application/json" id="ui-strings">(.*?)</script>', html, re.S)
    assert match, "ui-strings JSON block missing"
    strings = json.loads(match.group(1))
    assert {k: v for k, v in strings.items() if k.startswith(CHAT_UI_PREFIX)} == (
        get_catalog().texts_with_prefix(CHAT_UI_PREFIX)
    )
    assert strings["speaker_coach"] == "कोच" and strings["ui_time_just_now"] == "अभी"
    assert strings["ui_chat_cold_start"] == get_message("ui_chat_cold_start", lang="hi")
    for slot in ('id="status-bar"', 'id="sr-live"', 'id="pending-bubble"', 'id="rec-status"'):
        assert slot in html
    # the typing bubble starts generic; chat.js names the child (the strings are in the JSON above)
    assert '<span id="pending-text">जवाब आ रहा है…</span>' in html
    assert "function playAudioDirect" not in html  # the duplicate inline player is gone


@pytest.mark.asyncio
async def test_chat_page_shows_four_handbook_chips_when_idle(teacher_pwa_app: FastAPI) -> None:
    from backend.app.handbook.questions import chips_for

    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        html = (await client.get("/teacher")).text
    assert html.count('class="handbook-chip"') == settings.HANDBOOK_CHIPS_SHOWN == 4
    assert get_message("ui_handbook_title") in html
    assert 'data-autosend=""' in html
    # server-rendered: the four labels are today's questions (Hindi UI: the label is the question,
    # the script adds the ask keyword from data-prefix)
    from zoneinfo import ZoneInfo

    ist = ZoneInfo("Asia/Kolkata")
    today = chips_for(uuid.UUID(int=2), datetime.now(ist).date())
    assert f'data-prefix="{settings.HANDBOOK_ASK_PREFIX}"' in html
    for q in today:
        assert f'data-id="{q.id}">{q.hi}</button>' in html
    assert "data-text=" not in html.split('id="handbook-chips"')[1].split("</section>")[0]


@pytest.mark.asyncio
async def test_ask_parameter_sets_the_question_to_send_only_for_a_known_chip(
    teacher_pwa_app: FastAPI,
) -> None:
    from backend.app.handbook.questions import load_handbook_questions

    q = load_handbook_questions()[2]
    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        known = (await client.get(f"/teacher?ask={q.id}")).text
        unknown = (await client.get("/teacher?ask=not-a-question")).text
    assert f'data-autosend="{q.send_text()}"' in known
    assert 'data-autosend=""' in unknown


def test_handbook_chips_keep_the_page_light() -> None:
    """The chips are markup plus a few lines of script: the chat page budget (150 KB) still holds."""
    js = (STATIC_DIR / "chat.js").read_text(encoding="utf-8")
    assert "setupHandbookChips" in js and js.count("handleSendText(") >= 3
    assert not (STATIC_DIR / "handbook.js").exists()  # no extra script file


@pytest.mark.asyncio
async def test_english_chat_page_shows_english_chips_that_send_the_hindi_question(
    teacher_pwa_app: FastAPI,
) -> None:
    from backend.app.handbook.questions import chips_for
    from backend.app.web.ui_lang import LANG_COOKIE_NAME, UiLangMiddleware

    teacher_pwa_app.add_middleware(UiLangMiddleware)
    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        html = (await client.get("/teacher", cookies={LANG_COOKIE_NAME: "en"})).text
    section = html.split('id="handbook-chips"')[1].split("</section>")[0]
    assert "data-prefix" not in section  # no Hindi keyword in English chrome
    from zoneinfo import ZoneInfo

    ist = ZoneInfo("Asia/Kolkata")
    for q in chips_for(uuid.UUID(int=2), datetime.now(ist).date()):
        expected = f'data-id="{q.id}" data-text="{escape(q.send_text())}">{escape(q.en)}</button>'
        assert expected in section


@pytest.mark.asyncio
async def test_first_visit_goes_to_start_here_then_the_chat(
    teacher_pwa_app: FastAPI, mock_teacher: Teacher
) -> None:
    """A demo teacher who has not seen the Start here screen is sent there; ?s=1 and ?ask skip it."""
    mock_teacher.start_seen_at = None
    mock_teacher.consent_service = True
    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test", follow_redirects=False
    ) as client:
        first = await client.get("/teacher")
        assert first.status_code == 303 and first.headers["location"] == "/teacher/start"
        assert (await client.get("/teacher?s=1")).status_code == 200
        assert (await client.get("/teacher?ask=hb01")).status_code == 200
        page = (await client.get("/teacher/start")).text
        assert 'id="start-go"' in page and 'id="start-skip"' in page
        assert get_message("ui_start_button") in page


def test_start_here_is_short_and_plain_in_both_languages() -> None:
    """Three lines, one button, a skip link: under 80 words, no jargon."""
    for lang in ("hi", "en"):
        keys = ("ui_start_what", "ui_start_do", "ui_start_get", "ui_start_button", "ui_start_skip")
        words = sum(len(get_message(k, lang=lang).split()) for k in keys)
        assert words < 80, (lang, words)
        for jargon in ("rubric", "deliberate", "engine", "LLM", "FLN", "NIPUN"):
            assert all(jargon not in get_message(k, lang=lang) for k in keys)
