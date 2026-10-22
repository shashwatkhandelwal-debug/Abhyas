"""Headless-Chromium end-to-end test of the chat microphone against the real server.

Starts the real FastAPI app (uvicorn subprocess, mock STT/TTS/LLM, fresh migrated Postgres),
logs in through the login form and drives the mic button in Chromium with fake media devices:
tap to start / tap to stop, hold-to-talk, cancel, too-short discard, and the Hindi messages for
denied permission, no microphone and an insecure page. Skipped without TEST_DATABASE_URL or a
launchable Playwright Chromium.
"""

import asyncio
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
import yaml
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.auth.passwords import hash_password
from backend.app.config import settings
from backend.app.db.models import AppUser, Teacher

playwright_sync = pytest.importorskip("playwright.sync_api")

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
REPO_ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "e2e-voice-pass"
USERNAME = "e2e.voice"
FAKE_MIC = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set (runs in CI with real pgvector/pgvector:pg16)",
)


def _msg(key: str) -> str:
    cat = yaml.safe_load((REPO_ROOT / "content/messages_hi.yaml").read_text(encoding="utf-8"))
    return str(cat[key]["text"])


def _url(db_name: str | None, driver: str) -> str:
    assert TEST_DATABASE_URL is not None
    url = make_url(TEST_DATABASE_URL).set(drivername=driver)
    if db_name is not None:
        url = url.set(database=db_name)
    return url.render_as_string(hide_password=False)


async def _seed_teacher(db_name: str) -> None:
    engine = create_async_engine(_url(db_name, "postgresql+asyncpg"), poolclass=NullPool)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        teacher = Teacher(id=uuid4(), name="वॉइस टेस्ट", preferred_channel="web")
        s.add(teacher)
        await s.flush()
        s.add(
            AppUser(
                id=uuid4(),
                username=USERNAME,
                role="teacher",
                teacher_id=teacher.id,
                password_hash=hash_password(PASSWORD),
                display_name="वॉइस टेस्ट",
            )
        )
        await s.commit()
    await engine.dispose()


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    db_name = f"abhyas_e2e_{uuid4().hex[:10]}"
    admin = create_engine(_url(None, "postgresql+psycopg2"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    proc: subprocess.Popen[bytes] | None = None
    try:
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "backend/app/db/migrations"))
        cfg.set_main_option("sqlalchemy.url", _url(db_name, "postgresql"))
        command.upgrade(cfg, "head")
        asyncio.run(_seed_teacher(db_name))

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {
            **os.environ,
            "DATABASE_URL": _url(db_name, "postgresql+asyncpg"),
            "ALEMBIC_DATABASE_URL": _url(db_name, "postgresql"),
            "ENVIRONMENT": "development",
            "ANTHROPIC_API_KEY": "",
            "LLM_PROVIDER": "mock",
            "STT_PROVIDER": "mock",
            "TTS_PROVIDER": "mock",
            "STT_FALLBACK_PROVIDER": "none",
            "TTS_FALLBACK_PROVIDER": "none",
            "SPEECH_PROVIDER_LIVE": "false",
            "GEMINI_API_KEY": "",
            "SARVAM_API_KEY": "",
        }
        proc = subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", str(port)],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 60
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


class Chat:
    """A logged-in chat page with console error capture and request recording."""

    def __init__(self, page: Any, base: str) -> None:
        self.page = page
        self.base = base
        self.errors: list[str] = []
        self.audio_posts: list[Any] = []
        page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        page.on(
            "console",
            lambda m: (
                self.errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None
            ),
        )
        page.on(
            "request",
            lambda r: self.audio_posts.append(r) if r.url.endswith("/api/chat/audio") else None,
        )

    def open(self) -> None:
        self.page.goto(f"{self.base}/chat")
        self.page.wait_for_selector("#btn-mic")
        self.page.wait_for_timeout(
            1000
        )  # let chat.js attach its handlers and the first poll settle

    def tap_mic(self) -> None:
        box = self.page.locator("#btn-mic").bounding_box()
        assert box is not None
        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        self.page.mouse.down()
        self.page.mouse.up()

    def overlay_active(self) -> bool:
        return bool(self.page.locator("#recording-overlay.active").count())

    def notice(self) -> str:
        return self.page.locator("#status-bar").inner_text()


# Records the size of every audio file the page uploads (Playwright cannot read FormData bodies)
RECORD_UPLOADS = """
const _fetch = window.fetch.bind(window);
window.__uploads = [];
window.fetch = (input, init) => {
  const body = init && init.body;
  if (body instanceof FormData && body.get('file')) window.__uploads.push(body.get('file').size);
  return _fetch(input, init);
};
"""


@pytest.fixture(scope="module")
def auth_state(server: str) -> dict[str, Any]:
    """Logs in once (the login endpoint allows 5 attempts a minute) and reuses the cookies."""
    pw = playwright_sync.sync_playwright().start()
    try:
        browser = pw.chromium.launch(args=FAKE_MIC)
    except Exception as exc:  # browser binary not installed
        pw.stop()
        pytest.skip(f"Playwright Chromium unavailable: {exc}")
    try:
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(f"{server}/login")
        page.fill("#username", USERNAME)
        page.fill("#password", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")
        assert "/login" not in page.url
        return dict(ctx.storage_state())
    finally:
        browser.close()
        pw.stop()


@pytest.fixture
def chat_factory(server: str, auth_state: dict[str, Any]) -> Iterator[Any]:
    opened: list[Any] = []

    def make(init_script: str | None = None) -> Chat:
        pw = playwright_sync.sync_playwright().start()
        browser = pw.chromium.launch(args=FAKE_MIC)
        ctx = browser.new_context(
            storage_state=auth_state,
            permissions=["microphone"],
            viewport={"width": 390, "height": 780},
        )
        ctx.add_init_script(RECORD_UPLOADS)
        if init_script:
            ctx.add_init_script(init_script)
        opened.append((pw, browser))
        chat = Chat(ctx.new_page(), server)
        chat.open()
        return chat

    yield make
    for pw, browser in opened:
        browser.close()
        pw.stop()


def test_tap_to_start_tap_to_stop_sends_audio_and_shows_transcript(chat_factory: Any) -> None:
    chat = chat_factory()
    chat.tap_mic()
    chat.page.wait_for_selector("#recording-overlay.active")
    assert chat.page.locator("#btn-stop-rec").is_visible()
    assert chat.page.locator("#btn-cancel-rec").is_visible()
    chat.page.wait_for_timeout(1500)  # past the 1 s minimum
    with chat.page.expect_response("**/api/chat/audio") as resp_info:
        chat.page.click("#btn-stop-rec")
    resp = resp_info.value
    assert resp.status == 202
    assert chat.page.evaluate("window.__uploads")[0] > 1000  # a real recording, not 0 bytes
    chat.page.wait_for_selector(
        f".msg-row.inbound .bubble-text:has-text('{settings.MOCK_STT_TEXT}')"
    )
    assert not chat.overlay_active()
    assert chat.errors == []


def test_hold_to_talk_sends_on_release(chat_factory: Any) -> None:
    chat = chat_factory()
    box = chat.page.locator("#btn-mic").bounding_box()
    assert box is not None
    chat.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    with chat.page.expect_response("**/api/chat/audio") as resp_info:
        chat.page.mouse.down()
        chat.page.wait_for_selector("#recording-overlay.active")
        chat.page.wait_for_timeout(1600)  # > REC_HOLD_MS and > REC_MIN_SECONDS
        chat.page.mouse.up()
    assert resp_info.value.status == 202
    chat.page.wait_for_selector(
        f".msg-row.inbound .bubble-text:has-text('{settings.MOCK_STT_TEXT}')"
    )
    assert chat.errors == []


def test_cancel_discards_and_sends_nothing(chat_factory: Any) -> None:
    chat = chat_factory()
    chat.tap_mic()
    chat.page.wait_for_selector("#recording-overlay.active")
    chat.page.wait_for_timeout(1300)
    chat.page.click("#btn-cancel-rec")
    chat.page.wait_for_timeout(1500)
    assert chat.audio_posts == []
    assert not chat.overlay_active()
    assert chat.errors == []


def test_recording_shorter_than_one_second_is_discarded_with_hint(chat_factory: Any) -> None:
    chat = chat_factory()
    chat.tap_mic()
    chat.page.wait_for_selector("#recording-overlay.active")
    chat.page.click("#btn-stop-rec")  # immediately: well under REC_MIN_SECONDS
    chat.page.wait_for_selector("#status-bar.notice:not([hidden])")
    assert chat.notice() == _msg("ui_chat_rec_too_short")
    assert chat.audio_posts == []
    assert not chat.overlay_active()


def test_recording_auto_stops_and_sends_at_the_maximum(chat_factory: Any) -> None:
    chat = chat_factory()
    chat.page.evaluate("state.recorder.maxDurationSec = 2")  # same code path as 60 s, just shorter
    with chat.page.expect_response("**/api/chat/audio", timeout=15000) as resp_info:
        chat.tap_mic()
    assert resp_info.value.status == 202
    assert chat.notice() == _msg("ui_chat_rec_auto_sent")


@pytest.mark.parametrize(
    ("scenario", "key"),
    [
        ("denied", "ui_chat_rec_permission"),
        ("no_mic", "ui_chat_rec_no_mic"),
        ("insecure", "ui_chat_rec_insecure"),
    ],
)
def test_specific_hindi_messages_when_the_mic_cannot_start(
    chat_factory: Any, scenario: str, key: str
) -> None:
    scripts = {
        "denied": "navigator.mediaDevices.getUserMedia = () => Promise.reject("
        "new DOMException('denied', 'NotAllowedError'));",
        "no_mic": "navigator.mediaDevices.getUserMedia = () => Promise.reject("
        "new DOMException('none', 'NotFoundError'));",
        "insecure": "Object.defineProperty(window, 'isSecureContext', {value: false});",
    }
    chat = chat_factory(init_script=scripts[scenario])
    chat.tap_mic()
    chat.page.wait_for_selector("#status-bar.notice:not([hidden])")
    assert chat.notice() == _msg(key)
    assert chat.audio_posts == []
    assert not chat.overlay_active()


RECORD_WITH_MIME = """async (mime) => {
  if (mime && !MediaRecorder.isTypeSupported(mime)) return null;
  const stream = await navigator.mediaDevices.getUserMedia({audio: true});
  const opts = mime ? {mimeType: mime, audioBitsPerSecond: 16000} : {audioBitsPerSecond: 16000};
  const rec = new MediaRecorder(stream, opts);
  const chunks = [];
  rec.ondataavailable = (e) => chunks.push(e.data);
  const done = new Promise((r) => (rec.onstop = r));
  rec.start(250);
  await new Promise((r) => setTimeout(r, 1500));
  rec.stop();
  await done;
  stream.getTracks().forEach((t) => t.stop());
  const bytes = new Uint8Array(await new Blob(chunks).arrayBuffer());
  let s = '';
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}"""


@pytest.mark.parametrize("mime", ["audio/webm;codecs=opus", "audio/mp4", ""])
def test_every_recorder_mime_type_converts_with_to_wav16k(chat_factory: Any, mime: str) -> None:
    """The three MediaRecorder choices in recorder.js must be accepted by the server's ffmpeg."""
    import base64
    from concurrent.futures import ThreadPoolExecutor

    from backend.app.speech.audio import duration_s, to_wav16k

    chat = chat_factory()
    encoded = chat.page.evaluate(RECORD_WITH_MIME, mime)
    if encoded is None:
        pytest.skip(f"this Chromium cannot record {mime!r}")
    data = base64.b64decode(encoded)

    async def convert() -> tuple[bytes, float]:
        wav = await to_wav16k(data)
        return wav, await duration_s(wav)

    with ThreadPoolExecutor(max_workers=1) as pool:  # Playwright's loop owns this thread
        wav, seconds = pool.submit(asyncio.run, convert()).result(timeout=30)
    assert wav[:4] == b"RIFF"
    assert 1.0 < seconds < 2.5
