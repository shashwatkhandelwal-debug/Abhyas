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


@pytest.fixture
def browser() -> Iterator[Any]:
    """Headless Chromium for one test. Not wider than that: a started sync Playwright leaves an
    event loop running in the thread, which breaks every async test that runs after it."""
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
        self.context.add_init_script(NAV_PROBE)
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


def tap_reply(page: Any, text: str, timeout: int = 20_000) -> None:
    """Taps the newest enabled quick-reply chip whose label contains `text`."""
    chip = page.locator(".reply-chip:not([disabled])", has_text=text).last
    chip.wait_for(timeout=timeout)
    chip.click()
    page.wait_for_function(
        "() => !document.querySelector('#pending-bubble.active')", timeout=timeout
    )
    page.wait_for_timeout(1500)  # the reply bubble is rendered by the next poll


# Elements in `selector` whose text is cut off (clipped horizontally or vertically)
CLIPPED = """(selector) => [...document.querySelectorAll(selector)]
  .filter((el) => el.offsetParent !== null
    && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1))
  .map((el) => (el.id || el.className || el.tagName) + ': ' + el.textContent.trim().slice(0, 40))"""


# Visible text that is cut off: a leaf element clipped by its own box (overflow or ellipsis), an
# element running off the screen's edge (outside a row that scrolls by design), or an input
# placeholder wider than its field.
CUT_OFF = """() => {
  const out = [];
  const vw = document.documentElement.clientWidth;
  const hiddenAncestor = (el) => el.closest('[hidden], .sr-only, details:not([open]) > :not(summary)');
  for (const el of document.querySelectorAll('body *')) {
    if (el.matches('script, style, svg, svg *, option') || hiddenAncestor(el)) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const label = (el.id || el.className || el.tagName) + ': ' + (el.textContent || '').trim().slice(0, 30);
    if (el.tagName === 'INPUT' && el.placeholder) {
      const probe = document.createElement('span');
      probe.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;font:' + cs.font;
      probe.textContent = el.placeholder;
      document.body.appendChild(probe);
      const need = probe.getBoundingClientRect().width;
      probe.remove();
      const room = el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      if (need > room + 1) out.push('placeholder: ' + el.placeholder);
      continue;
    }
    if (el.children.length || !(el.textContent || '').trim()) continue;
    if (cs.overflowX !== 'visible' && el.scrollWidth > el.clientWidth + 1) out.push('clipped x ' + label);
    if (cs.overflowY !== 'visible' && el.scrollHeight > el.clientHeight + 1) out.push('clipped y ' + label);
    if (cs.textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth) out.push('ellipsis ' + label);
    const r = el.getBoundingClientRect();
    if (r.width > 0 && !el.closest('.handbook-chips, .sample-list') && (r.right > vw + 1 || r.left < -1)) {
      out.push('off screen ' + label);
    }
  }
  return out;
}"""

# Records when a link tap showed the "Opening..." bar, across the page load it starts
NAV_PROBE = """
document.addEventListener('click', () => sessionStorage.setItem('probe_click', String(Date.now())), true);
new MutationObserver(() => {
  if (document.querySelector('.nav-ack:not([hidden])') && !sessionStorage.getItem('probe_ack')) {
    sessionStorage.setItem('probe_ack', String(Date.now()));
  }
}).observe(document, { childList: true, subtree: true, attributes: true });
"""
RESPONSE_MS = 300


def tap_and_expect(
    page: Any, tap: Any, predicate: str, arg: Any = None, ms: int = RESPONSE_MS
) -> None:
    """Runs `tap()`, then requires `predicate` to hold within `ms` (a visible response)."""
    tap()
    page.wait_for_function(predicate, arg=arg, timeout=ms)


def link_acks_within(page: Any, tap: Any, url_glob: str, ms: int = RESPONSE_MS) -> None:
    """A link tap must show the "Opening..." bar (or already be on the next page) within `ms`."""
    page.evaluate(
        "sessionStorage.removeItem('probe_click'); sessionStorage.removeItem('probe_ack')"
    )
    tap()
    page.wait_for_url(url_glob, timeout=15_000)
    page.wait_for_load_state("domcontentloaded")
    gap = page.evaluate(
        "() => { const c = +sessionStorage.getItem('probe_click'), a = +sessionStorage.getItem('probe_ack');"
        " return (c && a) ? a - c : -1; }"
    )
    assert 0 <= gap <= ms, f"the tap showed nothing within {ms} ms (gap {gap})"
