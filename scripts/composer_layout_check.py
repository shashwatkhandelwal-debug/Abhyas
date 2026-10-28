"""Check that the chat composer (input, mic, send) and the quick replies stay on screen.

Boots the real app (mock DB / mock providers, as scripts/check_first_load.py does), opens /teacher in
Chromium at several phone sizes in both colour schemes, feeds the page the start screen, the consent
step, a learn step and a subtraction scene through the poll endpoint, and asserts that the input,
mic and send buttons are fully inside the viewport and that the last quick reply is reachable.

    python scripts/composer_layout_check.py                  # assert only
    python scripts/composer_layout_check.py --shots docs/ux  # also write screenshots
    python scripts/composer_layout_check.py --sizes 360x640 --keyboard 300

Needs: pip install playwright && playwright install chromium (or Google Chrome installed).
It is not part of `make test` because it needs a browser; run it by hand before a freeze.
Exit code 1 when any check fails.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SIZES = ["360x640", "393x852", "412x915"]
BROWSER_CHROME_OFFSET = 56  # height lost to a visible Android address bar
MIN_CHAT_PX = 90  # the chat region keeps at least 6rem (CSS floor) so a bubble stays readable


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def msg(
    mid: str, text: str, buttons: list[dict[str, str]] | None = None, speaker: str = "abhyas"
) -> dict[str, Any]:
    return {
        "id": mid, "client_msg_id": None, "direction": "out", "kind": "text", "text": text,
        "audio_ref": None, "buttons": buttons, "speaker": speaker, "citations": None,
        "created_at": now_iso(),
    }  # fmt: skip


def build_scenarios() -> dict[str, dict[str, Any]]:
    from backend.app.core.messages import get_message
    from backend.app.rehearsal.header import board_text
    from backend.app.rule_engine.domain import Problem
    from backend.app.web.chat_view import build_view

    consent_text = (
        get_message("consent_service")
        if _has("consent_service")
        else (
            "Abhyas stores your practice so that it can help you. You can leave at any time. "
            "Do you agree? " * 3
        )
    )
    agree = [
        {
            "id": "btn_agree",
            "title_hi": get_message("btn_agree") if _has("btn_agree") else "सहमत हूँ",
        },
        {"id": "btn_more", "title_hi": "और जानें"},
    ]
    item = Problem(type="sub", a=52, b=17)
    scene = {
        "mode": "group", "turn": 1, "max_turns": 6, "turn_label": get_message("ui_scene_turn", turn=1, max=6),
        "board": board_text(item), "item": {"type": "sub", "a": 52, "b": 17, "tens": None, "ones": None, "word": None},
        "manipulatives": {"bundles": 5, "sticks": 2, "regrouped": False, "aria_label": "5 बंडल और 2 तीलियाँ"},
        "title": get_message("ui_scene_group_title"),
        "children": [{"id": c, "name": get_message(f"speaker_{c}")} for c in ("ravi", "priya", "aman")],
    }  # fmt: skip
    ready = "READY"
    return {
        "start": {
            "messages": [],
            "scene": None,
            "view": build_view(onboarding="NEW", move_id="m01", state="LEARN", started=False, with_samples=True),
        },
        "consent": {
            "messages": [msg("c1", consent_text, agree)],
            "scene": None,
            "view": build_view(onboarding="SHARE_CONSENT", move_id="m01", state="LEARN", with_samples=True),
        },
        "learn": {
            "messages": [msg("l1", "Step 1. " + get_message("ui_step_1") * 6, [{"id": "btn_next", "title_hi": "आगे बढ़ें"}, {"id": "btn_replay", "title_hi": "फिर से सुनें"}])],
            "scene": None,
            "view": build_view(onboarding=ready, move_id="m01", state="LEARN", with_samples=True),
        },
        "scene": {
            "messages": [msg("s1", "रवि: मैं 52 में से 17 घटाता हूँ।", None, "ravi")],
            "scene": scene,
            "view": build_view(
                onboarding=ready, move_id="m01", state="REHEARSE", context={"rehearse_stage": "scene"},
                live_scene=scene, with_samples=True,
            ),
        },
    }  # fmt: skip


def _has(key: str) -> bool:
    from backend.app.core.messages import get_message

    try:
        return bool(get_message(key))
    except Exception:
        return False


class Server:
    def __init__(self) -> None:
        from backend.app.auth.guards import get_current_user
        from backend.app.db.models import AppUser, Teacher
        from backend.app.db.session import get_db_session
        from backend.app.main import app
        from backend.app.web import teacher as teacher_mod

        self.scenarios = build_scenarios()
        self.current = "start"
        tid = uuid.UUID("00000000-0000-0000-0000-000000000002")
        t = Teacher(id=tid, name="डेमो शिक्षिका 2", preferred_channel="web", lite_mode=False)
        u = AppUser(id=uuid.uuid4(), username="teacher.demo2", role="teacher", teacher_id=tid,
                    display_name="डेमो शिक्षिका 2", password_hash="x")  # fmt: skip

        async def session() -> Any:
            db = AsyncMock()

            async def get(entity: Any, ident: Any) -> Any:
                return t if entity is Teacher else u if entity is AppUser else None

            async def execute(stmt: Any) -> Any:
                r = MagicMock()
                r.scalars.return_value.all.return_value = []
                r.scalar_one_or_none.return_value = u if "app_user" in str(stmt) else t
                return r

            db.get.side_effect = get
            db.execute.side_effect = execute
            return db

        async def fake_view(*_a: Any, **_k: Any) -> dict[str, Any]:
            view: dict[str, Any] = self.scenarios[self.current]["view"]
            return view

        app.dependency_overrides[get_db_session] = session
        app.dependency_overrides[get_current_user] = lambda: u
        setattr(teacher_mod, "load_chat_view", fake_view)  # noqa: B010
        cfg = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
        self.server = uvicorn.Server(cfg)
        threading.Thread(target=self.server.run, daemon=True).start()
        while not self.server.started:
            time.sleep(0.05)
        port = self.server.servers[0].sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{port}/teacher"

    def stop(self) -> None:
        self.server.should_exit = True


def measure(page: Any, vw: int, vh: int) -> dict[str, Any]:
    result: dict[str, Any] = page.evaluate(
        """([vw, vh]) => {
          const box = (e) => { const b = e.getBoundingClientRect();
            return {top: b.top, bottom: b.bottom, left: b.left, right: b.right, h: b.height}; };
          const r = (sel) => { const e = document.querySelector(sel); return e ? box(e) : null; };
          const chat = document.getElementById('chat-messages');
          chat.scrollTop = chat.scrollHeight;
          const cb = box(chat);
          const chips = [...document.querySelectorAll('.quick-replies .reply-chip')].map((e) => {
            const b = box(e); const x = (b.left + b.right) / 2, y = (b.top + b.bottom) / 2;
            const hit = document.elementFromPoint(x, y);
            return {text: e.textContent.trim(), top: b.top, bottom: b.bottom,
                    inChat: b.top >= cb.top - 1 && b.bottom <= cb.bottom + 1,
                    tappable: hit === e || e.contains(hit)};
          });
          return {input: r('#chat-input'), mic: r('#btn-mic'), send: r('#btn-send'), chat: cb, chips};
        }""",
        [vw, vh],
    )
    return result


def check(name: str, m: dict[str, Any], vh: int, vw: int) -> list[str]:
    bad: list[str] = []
    for k in ("input", "mic", "send"):
        b = m[k]
        if b is None:
            bad.append(f"{name}: #{k} missing")
        elif b["top"] < 0 or b["bottom"] > vh + 0.5 or b["left"] < 0 or b["right"] > vw + 0.5:
            bad.append(
                f"{name}: {k} box {b['top']:.0f}-{b['bottom']:.0f} outside viewport height {vh}"
            )
    chips = m["chips"]
    if chips:
        last = chips[-1]  # the chat is scrolled to its end: the newest buttons must be showing
        if not (last["inChat"] and last["tappable"]):
            bad.append(f"{name}: last quick reply {last['text']!r} not visible/tappable: {last}")
    if m["chat"] and m["chat"]["h"] < MIN_CHAT_PX:
        bad.append(f"{name}: chat area only {m['chat']['h']:.0f}px tall")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", nargs="*", default=SIZES)
    ap.add_argument("--shots", default="")
    ap.add_argument(
        "--keyboard",
        type=int,
        default=0,
        help="shrink the viewport by this many px (soft keyboard)",
    )
    ap.add_argument("--scenarios", nargs="*", default=["start", "consent", "learn", "scene"])
    ap.add_argument("--tag", default="")
    ap.add_argument(
        "--open-tray", action="store_true", help="open the demo shortcuts tray before measuring"
    )
    ap.add_argument(
        "--wait-idle", type=int, default=0, help="seconds to sit idle first (30+ shows A1/A2/B)"
    )
    ap.add_argument(
        "--inject-css", default="", help="extra CSS applied after load (to test what-if layouts)"
    )
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    srv = Server()
    failures: list[str] = []
    out = Path(args.shots) if args.shots else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception:
                browser = p.chromium.launch(channel="chrome")
            for size in args.sizes:
                w, h = (int(x) for x in size.split("x"))
                vh = h - BROWSER_CHROME_OFFSET - args.keyboard
                for scheme in ("dark", "light"):
                    ctx = browser.new_context(
                        viewport={"width": w, "height": vh},
                        color_scheme=scheme,
                        is_mobile=True,
                        service_workers="block",
                        has_touch=True,
                        device_scale_factor=2,
                    )
                    page = ctx.new_page()
                    for name in args.scenarios:
                        srv.current = name
                        sc = srv.scenarios[name]
                        page.unroute("**/api/chat/messages**")
                        page.route(
                            "**/api/chat/messages**",
                            lambda route, _req=None, sc=sc: route.fulfill(
                                json={
                                    "messages": sc["messages"],
                                    "pending": False,
                                    "scene": sc["scene"],
                                    "view": sc["view"],
                                    "server_time": now_iso(),
                                }
                            ),
                        )
                        page.goto(srv.url, wait_until="load")
                        page.wait_for_timeout(900)
                        if args.open_tray:
                            page.evaluate("document.getElementById('fast-track-tray').open = true")
                        if args.wait_idle:
                            page.wait_for_timeout(args.wait_idle * 1000)
                        if args.inject_css:
                            page.add_style_tag(content=args.inject_css)
                        label = f"{size}-{scheme}-{name}" + (
                            f"-kb{args.keyboard}" if args.keyboard else ""
                        )
                        m = measure(page, w, vh)
                        bad = check(label, m, vh, w)
                        failures += bad
                        ib = round(m["input"]["bottom"]) if m["input"] else None
                        ch = round(m["chat"]["h"]) if m["chat"] else None
                        status = "FAIL" if bad else "ok  "
                        print(f"{status} {label} input.bottom={ib} vh={vh} chat_h={ch}")
                        for b in bad:
                            print("   ", b)
                        if out:
                            page.screenshot(path=str(out / f"{args.tag}{label}.png"))
                    ctx.close()
            browser.close()
    finally:
        srv.stop()
    print(f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
