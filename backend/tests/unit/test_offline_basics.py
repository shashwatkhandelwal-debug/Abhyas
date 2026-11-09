"""Unit tests for offline basics and service-worker caching (spec/09 §9.2, Job 06)."""

from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient

from backend.app.core.messages import get_message
from backend.app.web.teacher import router as teacher_router

STATIC_DIR = Path("backend/app/web/static")


@pytest.fixture
def offline_app() -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(teacher_router)
    return app


@pytest.mark.asyncio
async def test_offline_page_rendering_and_encoding(offline_app: FastAPI) -> None:
    """Verifies /offline.html renders 200, is valid UTF-8, and contains zero null bytes."""
    async with AsyncClient(
        transport=ASGITransport(app=offline_app), base_url="http://test"
    ) as client:
        res = await client.get("/offline.html")
    assert res.status_code == 200
    assert "\x00" not in res.text, "offline.html must never contain raw null bytes"
    assert "abhyas_chat_db" in res.text
    assert "messages_cache" in res.text


@pytest.mark.asyncio
async def test_offline_page_has_checklist_and_filter_tabs(offline_app: FastAPI) -> None:
    """Verifies /offline.html contains classroom checklist and tabs for all/rehearsal/guide."""
    async with AsyncClient(
        transport=ASGITransport(app=offline_app), base_url="http://test"
    ) as client:
        html = (await client.get("/offline.html")).text

    # Checklist elements
    for i in range(1, 5):
        assert f'id="chk{i}"' in html
        assert f"saveCheck({i})" in html

    # History filter tabs
    assert 'id="tab-all"' in html
    assert 'id="tab-rehearsal"' in html
    assert 'id="tab-guide"' in html
    assert "setFilter('rehearsal')" in html
    assert "setFilter('guide')" in html


@pytest.mark.asyncio
async def test_offline_page_has_honest_capabilities_disclosure(offline_app: FastAPI) -> None:
    """Verifies /offline.html explicitly documents what works offline vs requires internet."""
    async with AsyncClient(
        transport=ASGITransport(app=offline_app), base_url="http://test"
    ) as client:
        html = (await client.get("/offline.html")).text

    # Capabilities heading & labels in both languages
    hi_available = get_message("ui_offline_capabilities_available", lang="hi")
    assert hi_available in html or "ui_offline_capabilities_available" in html

    hi_required = get_message("ui_offline_capabilities_required", lang="hi")
    assert hi_required in html or "ui_offline_capabilities_required" in html


def test_service_worker_caches_offline_page() -> None:
    """Verifies sw.js registers /offline.html in static assets and navigation fallback."""
    sw_path = Path("backend/app/web/static/sw.js")
    assert sw_path.exists()
    content = sw_path.read_text(encoding="utf-8")
    assert "'/offline.html'" in content
    assert "cached('/offline.html')" in content


def test_offline_message_catalog_keys_complete() -> None:
    """Verifies that all offline UI keys exist in both Hindi and English catalogs."""
    keys = [
        "ui_offline_banner",
        "ui_offline_short",
        "ui_offline_title",
        "ui_offline_retry",
        "ui_offline_notice",
        "ui_offline_checklist_badge",
        "ui_offline_checklist_title",
        "ui_offline_checklist_intro",
        "ui_offline_chk1_label",
        "ui_offline_chk1_text",
        "ui_offline_chk2_label",
        "ui_offline_chk2_text",
        "ui_offline_chk3_label",
        "ui_offline_chk3_text",
        "ui_offline_chk4_label",
        "ui_offline_chk4_text",
        "ui_offline_history_title",
        "ui_offline_history_loading",
        "ui_offline_history_empty",
        "ui_offline_history_failed",
        "ui_offline_tab_all",
        "ui_offline_tab_rehearsal",
        "ui_offline_tab_guide",
        "ui_offline_capabilities_heading",
        "ui_offline_capabilities_available",
        "ui_offline_capabilities_required",
    ]
    with open("content/messages_hi.yaml", encoding="utf-8") as f:
        hi_catalog = yaml.safe_load(f)
    with open("content/messages_en.yaml", encoding="utf-8") as f:
        en_catalog = yaml.safe_load(f)

    for k in keys:
        assert k in hi_catalog, f"Key {k} missing from messages_hi.yaml"
        assert k in en_catalog, f"Key {k} missing from messages_en.yaml"
