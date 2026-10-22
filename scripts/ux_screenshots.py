"""Capture the chat page in each acknowledgment state, before and after.

Renders backend/app/web/templates/teacher.html with the static files of a git ref ("before")
and of the working tree ("after"), serves them locally, mocks /api/* with Playwright routes and
drives the same scripted interactions against both, saving PNGs to docs/ux/{before,after}/.
The real chat.js / app.css run in real (system) Chrome; nothing is faked client-side.

    python scripts/ux_screenshots.py --before-ref origin/main

Needs: pip install playwright (already a dev dependency) and Google Chrome installed.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import tarfile
import tempfile
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import jinja2
from playwright.sync_api import Page, Route, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WEB = "backend/app/web"
WAV = (ROOT / "backend/tests/fixtures/audio/sample_5s.wav").read_bytes()
VIEWPORT = {"width": 390, "height": 780}
FLAGS = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]


def now_iso(delta: float = 0) -> str:
    return (datetime.now(UTC) + timedelta(seconds=delta)).isoformat()


# ── version sources ─────────────────────────────────────────────────────────
def export_ref(ref: str, dest: Path) -> Path:
    """git archive <ref> backend/app/web -> dest/backend/app/web"""
    data = subprocess.run(
        ["git", "archive", "--format=tar", ref, WEB], cwd=ROOT, capture_output=True, check=True
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data")
    return dest / WEB


def ui_strings() -> dict[str, str]:
    from backend.app.core.messages import get_catalog

    return get_catalog().texts_with_prefix("ui_chat_")


def render_page(web_dir: Path) -> str:
    from backend.app.core.messages import get_message

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(web_dir / "templates"), autoescape=True)
    env.globals["get_message"] = get_message
    history = [
        {
            "id": "h1", "direction": "out", "speaker": "abhyas", "audio_ref": None, "buttons": None,
            "text": "नमस्ते! आज हम रवि, प्रिया और अमन के साथ घटाव का अभ्यास करेंगे।",
            "created_at": now_iso(-300), "time_str": "9:00 am",
        },
        {
            "id": "h2", "direction": "in", "speaker": None, "audio_ref": None, "buttons": None,
            "text": "ठीक है, शुरू करते हैं।", "created_at": now_iso(-280), "time_str": "9:01 am",
        },
    ]  # fmt: skip
    return env.get_template("teacher.html").render(
        csrf_token="x", teacher_name="अनीता", move_title="दो अंकों की हासिल वाली घटाव",
        step_chip="चरण 4/7 · अभ्यास", board_problem="बोर्ड: 52 − 17", lite_mode=False,
        demo_mode=False, demo_banner_text="", demo_chips=[], initial_messages=history,
        ui_strings=ui_strings(),
    )  # fmt: skip


class Site(ThreadingHTTPServer):
    def __init__(self, web_dir: Path) -> None:
        self.html = render_page(web_dir).encode("utf-8")
        self.static = web_dir / "static"

        site = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: Any) -> None:
                pass

            def do_GET(self) -> None:
                path = urlparse(self.path).path
                if path in ("/", "/teacher", "/chat"):
                    body, ctype = site.html, "text/html; charset=utf-8"
                elif path.startswith("/static/") and (site.static / path[8:]).is_file():
                    f = site.static / path[8:]
                    body = f.read_bytes()
                    ctype = {".js": "text/javascript", ".css": "text/css"}.get(
                        f.suffix, "image/svg+xml"
                    )
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.end_headers()
                self.wfile.write(body)

        super().__init__(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/teacher"


# ── mocked backend ──────────────────────────────────────────────────────────
class Mock:
    def __init__(self) -> None:
        self.pending = False
        self.queue: list[dict[str, Any]] = []
        self.post_mode = "ok"  # ok | hold | abort | 502
        self.held_posts: list[Route] = []
        self.poll_hold = False
        self.held_polls: list[Route] = []
        self.last_client_id = ""
        self.bad_audio: set[str] = set()

    def handle(self, route: Route) -> None:
        req = route.request
        path = urlparse(req.url).path
        if path == "/api/chat/messages":
            if self.poll_hold:
                self.held_polls.append(route)
                return
            msgs, self.queue = self.queue, []
            route.fulfill(
                json={"messages": msgs, "pending": self.pending, "server_time": now_iso()}
            )
        elif path in ("/api/chat/text", "/api/chat/button", "/api/chat/audio"):
            body = req.post_data_buffer or b""
            match = re.search(rb'client_msg_id"?[:=\s"]+([\w-]{8,})', body)
            if match:
                self.last_client_id = match.group(1).decode()
            if self.post_mode == "hold":
                self.held_posts.append(route)
            elif self.post_mode == "abort":
                route.abort("connectionfailed")
            elif self.post_mode == "502":
                route.fulfill(status=502, body="Bad gateway")
            else:
                self.accept(route)
        elif path.startswith("/api/audio/"):
            ref = path.rsplit("/", 1)[1].split(".")[0]
            if ref in self.bad_audio:
                route.abort("failed")
            else:
                route.fulfill(body=WAV, content_type="audio/wav")
        else:
            route.fulfill(json={"ok": True})

    def accept(self, route: Route) -> None:
        route.fulfill(
            status=202, json={"message_id": f"srv-{uuid.uuid4().hex[:6]}", "status": "accepted"}
        )

    def release_posts(self) -> None:
        held, self.held_posts = self.held_posts, []
        for route in held:
            self.accept(route)

    def release_polls(self) -> None:
        held, self.held_polls = self.held_polls, []
        self.poll_hold = False
        for route in held:
            self.handle(route)

    def user_copy(self, text: str | None, kind: str = "text") -> dict[str, Any]:
        return {
            "id": f"srv-{self.last_client_id[:6]}", "client_msg_id": self.last_client_id,
            "direction": "in", "kind": kind, "text": text, "audio_ref": None, "buttons": None,
            "speaker": None, "created_at": now_iso(),
        }  # fmt: skip


def child_reply(mid: str, speaker: str, text: str, audio_ref: str | None = None) -> dict[str, Any]:
    return {
        "id": mid, "client_msg_id": None, "direction": "out", "kind": "text", "text": text,
        "audio_ref": audio_ref, "buttons": None, "speaker": speaker, "created_at": now_iso(),
    }  # fmt: skip


# ── scenarios ───────────────────────────────────────────────────────────────
class Run:
    def __init__(self, page: Page, mock: Mock, out: Path) -> None:
        self.page, self.mock, self.out = page, mock, out
        self.n = 0

    def shot(self, name: str) -> None:
        self.n += 1
        self.out.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(self.out / f"{self.n:02d}_{name}.png"))

    def send(self, text: str) -> None:
        self.page.fill("#chat-input", text)
        self.page.click("#btn-send")

    def wait(self, ms: int) -> None:
        self.page.wait_for_timeout(ms)


def scenario_send_and_reply(r: Run) -> None:
    """clock -> check + typing indicator -> reply with audio loading -> player -> playing."""
    m = r.mock
    m.post_mode = "hold"
    r.send("रवि, तुमने 52 में से 17 कैसे घटाया? बताओ।")
    r.wait(400)
    r.shot("sending_clock")

    m.post_mode = "ok"
    m.pending = True
    m.release_posts()
    r.wait(700)
    r.shot("sent_typing_indicator")

    m.queue = [
        m.user_copy("रवि, तुमने 52 में से 17 कैसे घटाया? बताओ।"),
        child_reply("r1", "ravi", "पैंतालीस! सात में से दो गया पाँच।"),
    ]
    r.wait(1900)
    r.shot("reply_audio_loading")

    m.pending = False
    m.queue = [child_reply("r1", "ravi", "पैंतालीस! सात में से दो गया पाँच।", audio_ref="ref1")]
    r.page.evaluate("triggerImmediatePoll()")
    r.wait(1300)
    r.shot("audio_playing_autoplay")  # newest child line autoplays once; bars animate

    teacher = child_reply("t1", "model_teacher", "देखिए, मैं ऐसे करके दिखाती हूँ।", audio_ref="ref2")
    m.queue = [teacher]
    r.page.evaluate("triggerImmediatePoll()")
    r.wait(900)
    r.shot("audio_ready_play_button")


def scenario_audio_error(r: Run) -> None:
    r.mock.bad_audio.add("broken")
    r.mock.queue = [child_reply("e1", "aman", "सोलह!", audio_ref="broken")]
    r.page.evaluate("triggerImmediatePoll()")
    r.wait(900)
    r.page.locator(".btn-play").last.click()
    r.wait(900)
    r.shot("audio_error_retry")


def scenario_failed(r: Run) -> None:
    """Network drops the POST: clock, then (after the retries) the red ! ; tapping it resends."""
    m = r.mock
    m.post_mode = "abort"
    r.send("अमन, सही उत्तर 16 है, याद रखो।")
    r.wait(8500)
    r.shot("failed_tap_to_retry")
    m.post_mode = "ok"
    sel = ".status-icon.failed" if r.page.locator(".status-icon.failed").count() else ".status-icon"
    r.page.locator(sel).last.click()
    r.wait(900)
    r.shot("after_retry_sent")


def scenario_chips(r: Run) -> None:
    m = r.mock
    m.queue = [
        {
            "id": "q1", "direction": "out", "kind": "text", "speaker": "abhyas", "audio_ref": None,
            "text": "अब क्या करें?", "created_at": now_iso(), "client_msg_id": None,
            "buttons": [{"id": "again", "title_hi": "फिर से अभ्यास"}, {"id": "next", "title_hi": "आगे बढ़ें"}],
        }
    ]  # fmt: skip
    r.page.evaluate("triggerImmediatePoll()")
    r.wait(900)
    r.shot("quick_replies")
    m.post_mode = "hold"
    r.page.locator(".reply-chip").first.click()
    r.page.locator(".reply-chip").first.click(force=True, timeout=1500)  # must do nothing
    r.wait(300)
    r.shot("chip_pressed_locked")
    m.post_mode = "ok"
    m.release_posts()


def scenario_mic(r: Run) -> None:
    """recording (pulsing dot, timer, cancel) -> uploading -> transcribing -> transcript."""
    m = r.mock
    mic = r.page.locator("#btn-mic")
    box = mic.bounding_box()
    assert box
    r.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    r.page.mouse.down()
    r.wait(2300)
    r.shot("mic_recording")
    m.post_mode = "hold"
    r.page.mouse.up()
    r.wait(700)
    r.shot("mic_uploading")
    m.post_mode = "ok"
    m.pending = True
    m.release_posts()
    r.wait(700)
    r.shot("mic_transcribing")
    transcript = "रवि, 52 में से 17 कैसे घटाया?"
    m.pending = False
    m.queue = [m.user_copy(transcript, kind="audio")]
    r.page.evaluate("triggerImmediatePoll()")
    r.wait(900)
    r.shot("mic_transcript_bubble")


def scenario_cold_and_offline(r: Run) -> None:
    m = r.mock
    m.poll_hold = True  # server "asleep": poll gets no answer
    r.page.evaluate("triggerImmediatePoll()")
    r.wait(5800)
    r.shot("cold_start_bar")
    m.release_polls()
    r.wait(700)
    r.shot("cold_start_cleared")
    r.page.context.set_offline(True)
    r.wait(800)
    r.shot("offline_banner")
    m.poll_hold = True
    r.page.context.set_offline(False)
    r.wait(700)
    r.shot("reconnecting")
    m.release_polls()


def scenario_typing_timeout(browser: Any, site: Site, out: Path) -> None:
    ctx = browser.new_context(viewport=VIEWPORT, locale="hi-IN")
    page = ctx.new_page()
    mock = Mock()
    page.route("**/api/**", mock.handle)
    page.clock.install()
    page.goto(site.url)
    run = Run(page, mock, out)
    run.n = 100
    mock.pending = True
    run.send("प्रिया, तुम बताओ?")
    page.clock.run_for(2000)
    page.clock.run_for(61000)
    page.wait_for_timeout(300)
    run.shot("typing_timeout_hint")
    ctx.close()


def run_version(label: str, web_dir: Path, outroot: Path, browser: Any) -> None:
    site = Site(web_dir)
    out = outroot / label
    for old in out.glob("*.png"):
        old.unlink()
    for name, fn, perms in (
        ("reply", scenario_send_and_reply, []),
        ("audio_error", scenario_audio_error, []),
        ("failed", scenario_failed, []),
        ("chips", scenario_chips, []),
        ("mic", scenario_mic, ["microphone"]),
        ("net", scenario_cold_and_offline, []),
    ):
        ctx = browser.new_context(viewport=VIEWPORT, locale="hi-IN", permissions=perms)
        page = ctx.new_page()
        mock = Mock()
        page.route("**/api/**", mock.handle)
        page.goto(site.url)
        page.wait_for_timeout(600)
        run = Run(page, mock, out)
        run.n = {"reply": 0, "audio_error": 10, "failed": 20, "chips": 30, "mic": 40, "net": 50}[
            name
        ]
        try:
            fn(run)
        except Exception as exc:  # a state the old UI cannot reach is simply not captured
            print(f"[{label}] scenario {name} stopped: {type(exc).__name__}: {str(exc)[:120]}")
        ctx.close()
    try:
        scenario_typing_timeout(browser, site, out)
    except Exception as exc:
        print(f"[{label}] typing_timeout stopped: {type(exc).__name__}: {str(exc)[:120]}")
    site.shutdown()
    print(f"[{label}] {len(list(out.glob('*.png')))} screenshots -> {out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before-ref", default="origin/main")
    parser.add_argument("--out", default=str(ROOT / "docs" / "ux"))
    args = parser.parse_args()
    outroot = Path(args.out)
    import sys

    sys.path.insert(0, str(ROOT))
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        before_web = export_ref(args.before_ref, Path(tmp))
        browser = p.chromium.launch(channel="chrome", headless=True, args=FLAGS)
        run_version("before", before_web, outroot, browser)
        run_version("after", ROOT / WEB, outroot, browser)
        browser.close()
    time.sleep(0.1)
    print(json.dumps({"out": str(outroot)}))


if __name__ == "__main__":
    main()
