"""Friendly bilingual error pages, cold-start page and failure-message catalog (overnight part 1)."""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.messages import get_message
from backend.app.main import app as real_app
from backend.app.web.errors import install_error_pages
from backend.app.web.teacher import router as teacher_router

REPO = Path(__file__).resolve().parents[3]
HTML = {"accept": "text/html,application/xhtml+xml"}


def _app() -> FastAPI:
    app = FastAPI()
    install_error_pages(app)
    app.include_router(teacher_router)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/api/boom")
    async def api_boom() -> None:
        raise RuntimeError("secret internal detail")

    return app


def test_404_page_is_bilingual_and_has_no_raw_error() -> None:
    res = TestClient(_app()).get("/no-such-page", headers=HTML)
    assert res.status_code == 404
    assert get_message("ui_error_404_title", lang="hi") in res.text
    assert get_message("ui_error_404_title", lang="en") in res.text
    assert "Not Found" not in res.text and "detail" not in res.text


def test_500_page_hides_the_stack_trace() -> None:
    res = TestClient(_app(), raise_server_exceptions=False).get("/boom", headers=HTML)
    assert res.status_code == 500
    assert get_message("ui_error_500_title", lang="hi") in res.text
    assert get_message("ui_error_500_body", lang="en") in res.text
    assert "secret internal detail" not in res.text and "Traceback" not in res.text


def test_api_callers_still_get_json_errors() -> None:
    client = TestClient(_app(), raise_server_exceptions=False)
    res = client.get("/api/boom", headers=HTML)
    assert res.status_code == 500
    assert res.headers["content-type"].startswith("application/json")
    assert "secret internal detail" not in res.text
    res = client.get("/api/nothing", headers={"accept": "application/json"})
    assert res.status_code == 404
    assert res.json() == {"detail": "Not Found"}


@pytest.mark.parametrize("status", [502, 503, 504])
def test_gateway_statuses_render_the_waking_page(status: int) -> None:
    app = _app()

    @app.get("/gateway")
    async def gateway() -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=status)

    res = TestClient(app).get("/gateway", headers=HTML)
    assert res.status_code == status
    assert get_message("ui_error_503_title", lang="hi") in res.text
    assert 'http-equiv="refresh"' in res.text


def test_waking_page_polls_health_and_is_bilingual() -> None:
    res = TestClient(_app()).get("/waking")
    assert res.status_code == 200
    assert "/healthz" in res.text
    assert get_message("ui_waking_body", lang="hi") in res.text
    assert get_message("ui_waking_body", lang="en") in res.text


def test_real_app_registers_error_pages() -> None:
    res = TestClient(real_app).get("/definitely-missing", headers=HTML)
    assert res.status_code == 404
    assert get_message("ui_error_404_title", lang="hi") in res.text


def test_every_page_template_loads_the_ack_script() -> None:
    templates = REPO / "backend/app/web/templates"
    for name in ("chat.html", "teacher.html", "admin.html", "arp.html", "trainer.html"):
        assert "_ack.html" in (templates / name).read_text("utf-8"), name
    assert "ack.js" in (REPO / "backend/app/auth/router.py").read_text("utf-8")


def test_failure_messages_exist_in_both_languages_with_a_next_step() -> None:
    keys = [
        "stt_failed",
        "stt_budget_type_please",
        "system_error_retry",
        "ui_chat_rec_unsupported",
        "ui_chat_rec_permission",
        "ui_chat_rec_no_mic",
        "ui_chat_rec_too_short",
        "ui_chat_send_failed_network",
        "ui_chat_send_failed_rejected",
        "ui_chat_cold_start",
        "ui_nav_waking",
    ]
    hi = yaml.safe_load((REPO / "content/messages_hi.yaml").read_text("utf-8"))
    en = yaml.safe_load((REPO / "content/messages_en.yaml").read_text("utf-8"))
    for key in keys:
        for catalog in (hi, en):
            entry = catalog[key]
            text = entry["text"] if isinstance(entry, dict) else entry
            assert text.strip() and unicodedata.is_normalized("NFC", text), key
    for key in ("ui_chat_cold_start", "ui_nav_waking", "ui_error_503_body", "ui_waking_body"):
        assert "एक मिनट" in hi[key]["text"], key
        assert "minute" in en[key]["text"], key
