"""Bug-hunt driver: drives the real app (Docker) with Playwright on phone and desktop viewports.

Output goes to %TEMP%/bughunt/<run>/ (never the repo): per step a screenshot, the full chat
transcript, console errors, HTTP >= 400 responses, response time, and the matching docker logs.

    python scripts/bughunt/bh.py <journey.json> [--view phone|desktop] [--run NAME]

A journey is a JSON list of steps:
  ["login", "teacher.demo1"]   ["say", "text"]   ["click", "button text"]   ["goto", "/path"]
  ["lang", "hi|en"]  ["logout"]  ["snap", "label"]  ["offline"]  ["online"]  ["reload"]  ["back"]
  ["wait", seconds]  ["dump"]    ["sheet"] (open the suggestions sheet)   ["throttle", "slow3g"]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = os.environ.get("BH_BASE", "http://localhost:8000")
PASSWORD = os.environ.get("BH_DEMO_PASSWORD", "abhyas-demo-2026")
OUT = Path(os.environ.get("TEMP", ".")) / "bughunt"
PHONE = {
    "viewport": {"width": 360, "height": 740},
    "is_mobile": True,
    "has_touch": True,
    "device_scale_factor": 2,
    "user_agent": (
        "Mozilla/5.0 (Linux; Android 12; SM-A125F) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
}
DESKTOP = {"viewport": {"width": 1366, "height": 768}}

DUMP_JS = """() => {
  const q = (s) => document.querySelector(s);
  const rows = [...document.querySelectorAll('#chat-messages .msg-row, #chat-messages .demo-divider')].map(r => {
    if (r.classList.contains('demo-divider')) return {kind: 'divider', text: r.innerText.trim()};
    return {
      kind: r.classList.contains('inbound') ? 'teacher' : 'app',
      speaker: (r.querySelector('.speaker-tag') || {}).innerText || '',
      text: (r.querySelector('.bubble') ? r.querySelector('.bubble').innerText : '').split(String.fromCharCode(10)).join(' / ').slice(0, 900),
      buttons: [...r.querySelectorAll('.reply-chip')].map(b => b.innerText.trim()),
      sources: [...r.querySelectorAll('.source-chip')].map(b => b.innerText.trim()),
      audio: !!r.querySelector('.bubble-audio, .btn-play'),
      time: ((r.querySelector('.bubble-time, time, .msg-time') || {}).innerText || ''),
      html_time: (r.innerText.match(/\\b\\d{1,2}:\\d{2}( ?[ap]m)?\\b/i) || [''])[0],
    };
  });
  const t = (s) => { const e = q(s); return e ? e.innerText.trim() : null; };
  return {
    url: location.pathname,
    rows,
    header_step: t('#header-step'), move: t('#header-move-title'),
    scene: {title: t('#sb-title'), turn: t('#sb-turn'), board: t('#sb-board'),
            hidden: (q('#scene-bar') || {hidden: true}).hidden},
    actions: [...document.querySelectorAll('#action-row button, #chat-messages .msg-row:last-of-type .reply-chip')].map(b => b.innerText.trim()),
    samples: [...document.querySelectorAll('#sample-list .demo-chip')].map(b => b.innerText.trim()),
    banner: t('#demo-banner span'), next: t('#next-text'),
    pending: (q('#pending-bubble') || {}).offsetParent !== null,
    input_visible: (() => { const i = q('#chat-input'); if (!i) return null;
      const r = i.getBoundingClientRect(); return r.bottom <= innerHeight && r.top >= 0; })(),
    body: document.body.innerText.slice(0, 3000),
  };
}"""


def docker_logs(since_iso: str) -> list[str]:
    out = subprocess.run(
        ["docker", "logs", "abhyas_app", "--since", since_iso],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    lines = (out.stdout + out.stderr).splitlines()
    keep = []
    for ln in lines:
        low = ln.lower()
        if "sqlalchemy.engine" in low:
            continue
        if any(k in low for k in ("warn", "error", "traceback", "guard", "fallback_used=true", "llm_role", "exception")):
            keep.append(ln[:400])
    return keep


def llm_calls_total() -> int:
    out = subprocess.run(
        ["docker", "logs", "abhyas_app"], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return sum(1 for ln in (out.stdout + out.stderr).splitlines() if "llm_role" in ln and "sqlalchemy" not in ln)


class Hunt:
    def __init__(self, run: str, view: str) -> None:
        self.dir = OUT / run
        self.dir.mkdir(parents=True, exist_ok=True)
        self.view = view
        self.n = 0
        self.console: list[str] = []
        self.bad: list[str] = []
        self.tr = open(self.dir / "transcript.md", "a", encoding="utf-8")
        self.seen_rows = 0
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch()
        self.ctx = self.browser.new_context(**(PHONE if view == "phone" else DESKTOP))
        self.page: Page = self.ctx.new_page()
        self.page.set_default_timeout(10000)
        self.page.on("console", lambda m: self.console.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        self.page.on("pageerror", lambda e: self.console.append(f"pageerror: {e}"))
        self.page.on("response", self._resp)

    def _resp(self, r) -> None:
        if r.status >= 400:
            self.bad.append(f"{r.status} {r.request.method} {r.url.replace(BASE, '')}")

    def log(self, s: str) -> None:
        self.tr.write(s + "\n")
        self.tr.flush()
        print(s)

    def snap(self, label: str) -> None:
        self.n += 1
        self.page.screenshot(path=str(self.dir / f"{self.n:03d}_{label[:30].replace('/', '_')}.png"))

    def dump_new(self, d: dict) -> None:
        rows = d["rows"]
        for r in rows[self.seen_rows:]:
            if r["kind"] == "divider":
                self.log(f"   --- {r['text']}")
                continue
            who = "TEACHER" if r["kind"] == "teacher" else f"APP[{r['speaker']}]"
            extra = f"  buttons={r['buttons']}" if r["buttons"] else ""
            extra += f"  sources={r['sources']}" if r["sources"] else ""
            self.log(f"   {who} ({r['html_time']}): {r['text']}{extra}")
        self.seen_rows = len(rows)

    def state(self) -> dict:
        return self.page.evaluate(DUMP_JS)

    def wait_idle(self, before: int, timeout: float = 90) -> float:
        t0 = time.time()
        last_change, last_n = time.time(), before
        while time.time() - t0 < timeout:
            time.sleep(0.4)
            try:
                d = self.state()
            except Exception:
                continue
            n = len(d["rows"])
            if n != last_n:
                last_n, last_change = n, time.time()
            if n > before + 1 and not d["pending"] and time.time() - last_change > 2.0:
                break
            if n > before and not d["pending"] and time.time() - last_change > 6.0:
                break
        return time.time() - t0

    # --- steps
    def login(self, user: str) -> None:
        p = self.page
        p.goto(f"{BASE}/login")
        p.fill("#username", user)
        p.fill("#password", PASSWORD)
        p.click("button[type=submit]")
        p.wait_for_load_state("networkidle")
        self.seen_rows = 0
        self.log(f"## login {user} -> {p.url.replace(BASE, '')}")
        self.after()

    def after(self) -> None:
        time.sleep(1.0)
        d = self.state()
        if d["banner"]:
            self.log(f"   BANNER: {d['banner']}")
        self.dump_new(d)
        if d["actions"]:
            self.log(f"   ACTIONS: {d['actions']}")
        self.snap("state")

    def say(self, text: str) -> None:
        p = self.page
        before = len(self.state()["rows"])
        t0 = time.time()
        p.fill("#chat-input", text)
        p.click("#btn-send")
        self.log(f"## say: {text[:120]!r}")
        secs = self.wait_idle(before)
        d = self.state()
        self.dump_new(d)
        self.log(f"   [{secs:.1f}s] step={d['header_step']} scene={d['scene']['title']}/{d['scene']['turn']}/{d['scene']['board']} input_visible={d['input_visible']} next={d['next']!r} actions={d['actions']} samples={d['samples']}")
        self.snap("say")

    def click(self, label: str) -> None:
        p = self.page
        before = len(self.state()["rows"])
        loc = p.locator(f".reply-chip:has-text('{label}'), .demo-chip:has-text('{label}'), .handbook-chip:has-text('{label}'), .ft-chip:has-text('{label}'), button:has-text('{label}'), a:has-text('{label}')").last
        loc.click()
        self.log(f"## click: {label!r}")
        secs = self.wait_idle(before, timeout=60)
        d = self.state()
        self.dump_new(d)
        self.log(f"   [{secs:.1f}s] step={d['header_step']} scene={d['scene']['title']}/{d['scene']['turn']}/{d['scene']['board']} actions={d['actions']} samples={d['samples']}")
        self.snap("click")

    def run(self, steps: list) -> None:
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        p = self.page
        for s in steps:
            op, *a = s
            try:
                if op == "login": self.login(a[0])
                elif op == "say": self.say(a[0])
                elif op == "click": self.click(a[0])
                elif op == "goto":
                    p.goto(BASE + a[0]); p.wait_for_load_state("networkidle"); self.seen_rows = 0
                    self.log(f"## goto {a[0]} -> {p.url.replace(BASE, '')} [{p.title()}]"); self.after()
                    self.log("   PAGE: " + self.state()["body"][:1500].replace("\n", " / "))
                elif op == "lang":
                    p.goto(f"{BASE}/lang/{a[0]}"); p.wait_for_load_state("networkidle"); self.seen_rows = 0
                    self.log(f"## lang {a[0]} -> {p.url.replace(BASE, '')}"); self.after()
                elif op == "logout":
                    p.goto(f"{BASE}/logout"); p.wait_for_load_state("networkidle"); self.log(f"## logout -> {p.url.replace(BASE, '')}")
                elif op == "module":
                    p.goto(f"{BASE}/teacher/modules"); p.wait_for_load_state("networkidle")
                    p.click(f"#module-{a[0]} button[type=submit]"); p.wait_for_load_state("networkidle")
                    time.sleep(2); self.seen_rows = 0
                    self.log(f"## module {a[0]} -> {p.url.replace(BASE, '')}"); self.after()
                elif op == "css":
                    before = len(self.state()["rows"]) if p.locator("#chat-messages").count() else 0
                    p.click(a[0]); p.wait_for_load_state("networkidle"); time.sleep(1.5)
                    self.log(f"## css click {a[0]} -> {p.url.replace(BASE, '')}"); self.after()
                elif op == "fill":
                    p.fill(a[0], a[1]); self.log(f"## fill {a[0]}={a[1]!r}")
                elif op == "snap": self.snap(a[0] if a else "snap"); self.log("## snap " + (a[0] if a else ""))
                elif op == "dump":
                    d = self.state(); self.log("   PAGE: " + d["body"][:2500].replace("\n", " / "))
                elif op == "sheet":
                    p.click("#btn-suggest"); time.sleep(0.6); self.snap("sheet")
                    self.log("   SHEET: " + p.inner_text("#sheet")[:1500].replace("\n", " / "))
                elif op == "closesheet":
                    p.click("#sheet-close"); time.sleep(0.3)
                elif op == "offline": self.ctx.set_offline(True); self.log("## offline")
                elif op == "online": self.ctx.set_offline(False); self.log("## online")
                elif op == "reload":
                    p.reload(); p.wait_for_load_state("networkidle"); self.seen_rows = 0; self.log("## reload"); self.after()
                elif op == "back":
                    p.go_back(); p.wait_for_load_state("networkidle"); self.seen_rows = 0; self.log(f"## back -> {p.url}"); self.after()
                elif op == "wait": time.sleep(float(a[0])); self.log(f"## waited {a[0]}s")
                elif op == "throttle":
                    cdp = self.ctx.new_cdp_session(p)
                    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 400, "downloadThroughput": 50_000, "uploadThroughput": 25_000})
                    self.log("## throttle slow3g")
                elif op == "unthrottle":
                    cdp = self.ctx.new_cdp_session(p)
                    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1})
                else:
                    self.log(f"!! unknown step {s}")
            except Exception as e:  # keep going; the failure is itself a finding
                self.log(f"!! STEP FAILED {s}: {type(e).__name__}: {str(e)[:300]}")
                try:
                    self.snap("FAILED")
                except Exception:
                    pass
        self.log(f"## CONSOLE ({len(self.console)}): {self.console[:20]}")
        self.log(f"## HTTP>=400 ({len(self.bad)}): {self.bad[:30]}")
        for ln in docker_logs(since):
            if "llm_role" in ln and "fallback_used=false" in ln:
                continue
            self.log("   LOG: " + ln)
        self.log(f"## llm_role lines so far (cumulative): {llm_calls_total()}")

    def close(self) -> None:
        self.tr.close()
        self.browser.close()
        self.pw.stop()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("journey")
    ap.add_argument("--view", default="phone")
    ap.add_argument("--run", default=None)
    ns = ap.parse_args()
    steps = json.loads(Path(ns.journey).read_text(encoding="utf-8-sig"))
    h = Hunt(ns.run or Path(ns.journey).stem + "_" + ns.view, ns.view)
    try:
        h.run(steps)
    finally:
        h.close()
