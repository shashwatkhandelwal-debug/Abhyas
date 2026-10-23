"""Fixtures for the browser tests: a real seeded server (mock providers) and headless Chromium.

The server is the real FastAPI app in a uvicorn subprocess on a fresh, migrated and seeded
Postgres database, so the demo accounts are exactly what a judge gets. Everything is skipped
without TEST_DATABASE_URL or a launchable Playwright Chromium. No test here calls an external
service: the LLM, speech and WhatsApp providers are mocks.
"""

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

playwright_sync = pytest.importorskip("playwright.sync_api")

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_PASSWORD = "e2e-demo-pass"
SEED_TIMEOUT_S = 600
MOBILE = {"width": 360, "height": 740}
DESKTOP = {"width": 1280, "height": 800}

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


def _url(db_name: str | None, driver: str) -> str:
    assert TEST_DATABASE_URL is not None
    url = make_url(TEST_DATABASE_URL).set(drivername=driver)
    if db_name is not None:
        url = url.set(database=db_name)
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def server() -> Iterator[str]:
    """Base URL of a seeded app (demo1 to demo3, ARP, trainer, coach, admin)."""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    db_name = f"abhyas_e2e_{uuid4().hex[:10]}"
    admin = create_engine(_url(None, "postgresql+psycopg2"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    proc: subprocess.Popen[bytes] | None = None
    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {
            **os.environ,
            "DATABASE_URL": _url(db_name, "postgresql+asyncpg"),
            "ALEMBIC_DATABASE_URL": _url(db_name, "postgresql"),
            "TEST_DATABASE_URL": _url(db_name, "postgresql"),
            "ENVIRONMENT": "development",
            "DEMO_MODE": "true",
            "DEMO_PASSWORD": DEMO_PASSWORD,
            "ANTHROPIC_API_KEY": "",
            "LLM_PROVIDER": "mock",
            "LLM_CALL_LOG_ENABLED": "false",
            "STT_PROVIDER": "mock",
            "TTS_PROVIDER": "mock",
            "STT_FALLBACK_PROVIDER": "none",
            "TTS_FALLBACK_PROVIDER": "none",
            "SPEECH_PROVIDER_LIVE": "false",
            "GEMINI_API_KEY": "",
            "SARVAM_API_KEY": "",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
        for args in (["-m", "alembic", "upgrade", "head"], ["-m", "backend.app.db.seed"]):
            done = subprocess.run(  # noqa: S603
                [sys.executable, *args],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=SEED_TIMEOUT_S,
            )
            assert done.returncode == 0, done.stderr[-1500:]
        proc = subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", str(port)],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                if httpx.get(f"{base}/healthz", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            raise RuntimeError("e2e server did not start")
        yield base
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(scope="session")
def browser() -> Iterator[Any]:
    pw = playwright_sync.sync_playwright().start()
    try:
        chromium = pw.chromium.launch()
    except Exception as exc:  # browser binary not installed
        pw.stop()
        pytest.skip(f"Playwright Chromium unavailable: {exc}")
    try:
        yield chromium
    finally:
        chromium.close()
        pw.stop()


class Teacher:
    """One logged-in browser context on the chat page, with console errors recorded."""

    def __init__(
        self,
        browser: Any,
        base: str,
        username: str,
        *,
        viewport: dict[str, int] = MOBILE,
        lang: str = "hi",
        scheme: str = "light",
    ) -> None:
        mobile = viewport["width"] < 500
        self.base = base
        self.context = browser.new_context(
            viewport=viewport,
            is_mobile=mobile,
            has_touch=mobile,
            color_scheme=scheme,
            locale="hi-IN" if lang == "hi" else "en-IN",
        )
        self.page = self.context.new_page()
        self.errors: list[str] = []
        self.page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        self.page.goto(f"{base}/login")
        self.page.fill("#username", username)
        self.page.fill("#password", DEMO_PASSWORD)
        self.page.click("button[type=submit]")
        self.page.wait_for_load_state("networkidle")
        assert "/login" not in self.page.url, "login failed"
        if lang == "en":
            self.page.goto(f"{base}/lang/en?next=/teacher")
            self.page.wait_for_load_state("networkidle")
        self.page.wait_for_selector("#chat-input")
        self.page.wait_for_timeout(600)  # chat.js has attached its handlers; first poll is in

    def close(self) -> None:
        self.context.close()


@pytest.fixture
def open_chat(browser: Any, server: str) -> Iterator[Any]:
    opened: list[Teacher] = []

    def make(username: str, **kwargs: Any) -> Teacher:
        teacher = Teacher(browser, server, username, **kwargs)
        opened.append(teacher)
        return teacher

    yield make
    for teacher in opened:
        teacher.close()
