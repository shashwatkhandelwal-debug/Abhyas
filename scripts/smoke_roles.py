#!/usr/bin/env python3
"""Smoke test of every role on a seeded Abhyas instance (local or hosted).

Logs in as the three shared teachers, the ARP, the trainer, the coach and the admin, fetches each home
page and the pages added in the final push, and walks one short chat journey per teacher login. It
needs a seeded database and the demo passwords; it never prints a password. Exit code 0 only if every
step passes. Chat replies depend on the providers configured on the instance: with the mock LLM the
handbook chips answer from their stored summary, which is still a cited reply.

Usage:
    python scripts/smoke_roles.py --base-url http://localhost:8000 --demo-password ... --admin-password ...
    (or DEMO_PASSWORD / ADMIN_PASSWORD in the environment)
"""

from __future__ import annotations

import argparse
import html as html_lib
import os
import re
import sys
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx

CSRF_COOKIE = "abhyas_csrf"
CSRF_HEADER = "X-CSRF-Token"
REPLY_TIMEOUT_S = 90.0

Step = tuple[str, bool, str]


class Session:
    """One logged-in browser: cookies, CSRF header, and the small helpers the steps share."""

    def __init__(self, base_url: str) -> None:
        self.client = httpx.Client(base_url=base_url, follow_redirects=False, timeout=30.0)

    def login(self, username: str, password: str) -> httpx.Response:
        page = self.client.get("/login")
        match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        token = match.group(1) if match else self.client.cookies.get(CSRF_COOKIE, "")
        return self.client.post(
            "/login", data={"username": username, "password": password, "csrf_token": token}
        )

    def headers(self) -> dict[str, str]:
        return {CSRF_HEADER: self.client.cookies.get(CSRF_COOKIE, "")}

    def get(self, path: str) -> httpx.Response:
        return self.client.get(path)

    def post_form(self, path: str, data: dict[str, str] | None = None) -> httpx.Response:
        body = dict(data or {})
        body["csrf_token"] = self.client.cookies.get(CSRF_COOKIE, "")
        return self.client.post(path, data=body, headers=self.headers())

    def logout(self) -> httpx.Response:
        return self.client.get("/logout")

    def messages(self) -> list[dict[str, Any]]:
        data = self.client.get("/api/chat/messages").json()
        return list(data.get("messages", []))

    def pending(self) -> bool:
        return bool(self.client.get("/api/chat/messages").json().get("pending"))

    def say(self, text: str) -> list[dict[str, Any]]:
        """Sends text and returns the new messages once the reply has settled."""
        before = {m["id"] for m in self.messages()}
        resp = self.client.post(
            "/api/chat/text",
            json={"client_msg_id": str(uuid.uuid4()), "text": text},
            headers=self.headers(),
        )
        if resp.status_code != 202:
            raise RuntimeError(f"POST /api/chat/text -> {resp.status_code}: {resp.text[:120]}")
        deadline = time.monotonic() + REPLY_TIMEOUT_S
        while time.monotonic() < deadline:
            time.sleep(1.0)
            fresh = [m for m in self.messages() if m["id"] not in before]
            if any(m.get("direction") == "out" for m in fresh) and not self.pending():
                time.sleep(1.0)  # a reply may be sent as several bubbles
                return [m for m in self.messages() if m["id"] not in before]
        raise TimeoutError(f"no reply to {text[:30]!r} within {REPLY_TIMEOUT_S:.0f} s")


def run(name: str, fn: Callable[[], str], steps: list[Step]) -> bool:
    try:
        detail = fn()
        steps.append((name, True, detail))
        print(f"  PASS  {name}: {detail}")
        return True
    except Exception as exc:  # a failed assertion or an HTTP error: report it and go on
        steps.append((name, False, f"{type(exc).__name__}: {exc}"[:200]))
        print(f"  FAIL  {name}: {type(exc).__name__}: {exc}"[:260])
        return False


def ok_page(session: Session, path: str, *markers: str) -> str:
    resp = session.get(path)
    assert resp.status_code == 200, f"GET {path} -> {resp.status_code}"
    for marker in markers:
        assert marker in resp.text, f"{path}: missing {marker!r}"
    return f"{path} 200 ({len(resp.text) // 1024} KB)"


def teacher_chips(session: Session) -> list[str]:
    """The questions the four handbook chips on /teacher send (Hindi UI: label = question)."""
    page = session.get("/teacher").text
    found = re.findall(r'class="handbook-chip" data-id="[^"]+"[^>]*>([^<]+)</button>', page)
    return [html_lib.unescape(q).strip() for q in found]


def teacher_steps(base: str, username: str, password: str, steps: list[Step]) -> None:
    print(f"\n{username}")
    s = Session(base)
    run(f"{username}: login", lambda: _login(s, username, password), steps)
    run(f"{username}: /teacher", lambda: ok_page(s, "/teacher", 'id="chat-input"'), steps)
    # four chips on every chat page, inside a scene too (a question there is answered and the
    # reply says how to go back)
    run(
        f"{username}: handbook chips on the chat page (four)",
        lambda: _count(teacher_chips(s), 4),
        steps,
    )
    run(f"{username}: what-to-do line and step header", lambda: _next_card(s), steps)
    run(
        f"{username}: /teacher/modules with chip links",
        lambda: ok_page(s, "/teacher/modules", 'href="/teacher?ask=hb'),
        steps,
    )
    run(
        f"{username}: /teacher/class with the skills section",
        lambda: ok_page(s, "/teacher/class", 'id="class-skills"', 'name="skill"'),
        steps,
    )
    run(f"{username}: /teacher/progress", lambda: ok_page(s, "/teacher/progress"), steps)
    if username == "teacher.demo1":
        run(f"{username}: first message answered", lambda: _first_message(s), steps)
    if username == "teacher.demo2":
        run(f"{username}: scene header and board", lambda: _scene_page(s), steps)
        run(f"{username}: a teaching sentence gets a reply", lambda: _teach(s), steps)
    if username == "teacher.demo3":
        run(f"{username}: seeded class choice and skill on the page", lambda: _demo3_seed(s), steps)
        run(f"{username}: a handbook chip answers with a citation", lambda: _chip(s), steps)
        run(f"{username}: My class then a skill, by chat", lambda: _class_and_skill(s), steps)
    run(f"{username}: logout", lambda: _logout(s), steps)
    if username == "teacher.demo3":
        run(f"{username}: logout reset the choice", lambda: _demo3_reset(base, password), steps)


def _login(s: Session, username: str, password: str) -> str:
    resp = s.login(username, password)
    assert resp.status_code in (200, 302, 303), f"login -> {resp.status_code}"
    assert s.client.cookies.get("abhyas_session"), "no session cookie"
    return f"HTTP {resp.status_code}"


def _count(items: list[str], expected: int) -> str:
    assert len(items) == expected, f"expected {expected}, found {len(items)}"
    return f"{len(items)} chips"


def _first_message(s: Session) -> str:
    reply = s.say("नमस्ते")
    assert any(m.get("direction") == "out" and m.get("text") for m in reply), "no reply"
    return f"{len([m for m in reply if m.get('direction') == 'out'])} reply bubble(s)"


def _next_card(s: Session) -> str:
    """Every chat page says what to do now and which step of seven she is on."""
    page = s.get("/teacher").text
    card = re.search(r'id="next-card"[^>]*>(.*?)</div>', page, re.S)
    assert card is not None and 'id="next-text">' in card.group(1), "no what-to-do line"
    text = re.search(r'id="next-text">([^<]+)<', page)
    assert text is not None and text.group(1).strip(), "the what-to-do line is empty"
    step = re.search(r'id="header-step">([^<]*)<', page)
    assert step is not None, "no step header"
    return f"{html_lib.unescape(text.group(1)).strip()[:48]} | {step.group(1).strip()}"


def _scene_page(s: Session) -> str:
    page = s.get("/teacher").text
    assert 'id="scene-bar"' in page and " hidden" not in page.split('id="scene-bar"')[1][:80]
    assert 'id="sb-board">43' in page and "27" in page, "board 43 - 27 not in the scene bar"
    assert page.count('class="board-problem"') == 1, "the problem must be shown once"
    assert "child-pill" not in page, "a one-on-one scene lists only that child"
    return "one-on-one bar: title, turn and one board card"


def _teach(s: Session) -> str:
    reply = s.say("रवि, तुमने 43 में से 27 कैसे घटाया? एक-एक कदम बताओ।")
    out = [m for m in reply if m.get("direction") == "out" and m.get("text")]
    assert out, "no child reply"
    return f"{len(out)} reply bubble(s): {str(out[0].get('text'))[:40]}"


def _demo3_seed(s: Session) -> str:
    page = s.get("/teacher/class").text
    assert 'data-struggle="LIT_MATRA_DROP"' in page and 'data-struggle="NUM_ADD_CARRY"' in page
    assert 'data-skill="asks_to_explain"' in page
    return "LIT_MATRA_DROP, NUM_ADD_CARRY and asks_to_explain are shown"


def _chip(s: Session) -> str:
    chips = teacher_chips(s)
    assert chips, "no chips"
    reply = s.say(f"सवाल: {chips[0]}")
    answers = [m for m in reply if m.get("direction") == "out" and m.get("citations")]
    assert answers, "the answer carries no citation"
    text = str(answers[0].get("text"))
    # the web channel shows the source as a tappable chip, so the line is in `citations`
    cites = answers[0]["citations"]
    assert all("स्रोत" in c["line_hi"] and c.get("page") for c in cites), cites
    for phrase in ("नहीं मिला", "ARP से पूछकर"):
        assert phrase not in text, f"'not found' reply: {phrase}"
    return f"cited answer, {len(cites)} citation(s): {cites[0]['line_hi']}"


def _class_and_skill(s: Session) -> str:
    s.say("मेरी कक्षा")
    s.say("1")  # the first chip
    s.say("हाँ")
    ask = s.say("1")  # the first skill
    assert any("हाँ" in str(m.get("buttons")) or m.get("buttons") for m in ask), "no confirm"
    s.say("हाँ")
    page = s.get("/teacher/class").text
    assert 'data-skill="asks_to_explain"' in page, "skill not saved"
    return "class choice saved, skill saved"


def _logout(s: Session) -> str:
    resp = s.logout()
    assert resp.status_code in (200, 302, 303), f"logout -> {resp.status_code}"
    return f"HTTP {resp.status_code}"


def _demo3_reset(base: str, password: str) -> str:
    s = Session(base)
    assert s.login("teacher.demo3", password).status_code in (200, 302, 303)
    page = s.get("/teacher/class").text
    assert 'data-struggle="LIT_MATRA_DROP"' in page and 'data-skill="asks_to_explain"' in page
    s.logout()
    return "back to LIT_MATRA_DROP, NUM_ADD_CARRY and asks_to_explain"


def role_steps(base: str, demo_password: str, admin_password: str, steps: list[Step]) -> None:
    print("\narp.demo")
    arp = Session(base)
    run("arp.demo: login", lambda: _login(arp, "arp.demo", demo_password), steps)
    run(
        "arp.demo: /arp digest with the escalated demo question",
        lambda: ok_page(arp, "/arp", "डेमो: मेरी कक्षा में कक्षा 1 और 2"),
        steps,
    )
    print("\ntrainer.demo")
    tr = Session(base)
    run("trainer.demo: login", lambda: _login(tr, "trainer.demo", demo_password), steps)
    run(
        "trainer.demo: /trainer with the class and skills cards",
        lambda: ok_page(tr, "/trainer", 'id="class-struggles"', 'id="teaching-skills"'),
        steps,
    )
    print("\ncoach.demo")
    coach = Session(base)
    run("coach.demo: login", lambda: _login(coach, "coach.demo", demo_password), steps)
    run("coach.demo: /review lists a small queue", lambda: _queue(coach), steps)
    print("\nadmin")
    admin = Session(base)
    run("admin: login", lambda: _login(admin, "admin", admin_password), steps)
    run("admin: /admin", lambda: ok_page(admin, "/admin", "reset-demo"), steps)
    run("admin: reset demo", lambda: _admin_reset(admin), steps)


def _queue(coach: Session) -> str:
    resp = coach.get("/review")
    assert resp.status_code == 200, f"GET /review -> {resp.status_code}"
    items = re.findall(r'href="/review/items/[0-9a-f-]{36}"', resp.text)
    assert 3 <= len(items) <= 8, f"{len(items)} items in the open scores list"
    return f"{len(items)} open score items (questions are a separate tab)"


def _admin_reset(admin: Session) -> str:
    resp = admin.post_form("/admin/reset-demo")
    assert resp.status_code in (200, 302, 303), f"reset -> {resp.status_code}"
    assert "reset_ok" in resp.headers.get("location", "reset_ok")
    return f"HTTP {resp.status_code}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test every role on a seeded instance.")
    parser.add_argument(
        "--base-url", default=os.environ.get("APP_BASE_URL", "http://localhost:8000")
    )
    parser.add_argument("--demo-password", default=os.environ.get("DEMO_PASSWORD", ""))
    parser.add_argument("--admin-password", default=os.environ.get("ADMIN_PASSWORD", ""))
    args = parser.parse_args()
    if not args.demo_password or not args.admin_password:
        print("Give --demo-password and --admin-password (or DEMO_PASSWORD / ADMIN_PASSWORD).")
        return 2
    base = args.base_url.rstrip("/")
    steps: list[Step] = []
    print(f"Target: {base}")
    anon = Session(base)
    run(
        "healthz",
        lambda: (
            f"{anon.get('/healthz').json().get('status')} sha={anon.get('/healthz').json().get('git_sha', '?')}"
        ),
        steps,
    )
    run("login page note", lambda: _login_note(anon), steps)
    for username in ("teacher.demo1", "teacher.demo2", "teacher.demo3"):
        teacher_steps(base, username, args.demo_password, steps)
    role_steps(base, args.demo_password, args.admin_password, steps)
    failed = [s for s in steps if not s[1]]
    print(f"\n{len(steps) - len(failed)} of {len(steps)} steps passed.")
    for name, _ok, detail in failed:
        print(f"FAILED: {name}: {detail}")
    return 1 if failed else 0


def _login_note(anon: Session) -> str:
    page = anon.get("/login").text
    assert 'role="note"' in page and "fillCreds('teacher.demo3')" in page
    return "shared-accounts note and three teacher buttons"


if __name__ == "__main__":
    sys.exit(main())
