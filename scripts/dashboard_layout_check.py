"""Do the ARP, trainer and coach dashboards fit a phone? (Chromium emulating Android, seeded data)

Starts the real app in a subprocess on a fresh, migrated and seeded scratch database (mock providers,
the same way backend/tests/e2e/conftest.py does), logs in as arp.demo, trainer.demo and coach.demo,
and at 360x640 and 412x915, dark and light, asserts for every page:

  * document.scrollingElement.scrollWidth <= window.innerWidth (no sideways page scroll)
  * the page heading (h1) lies fully inside the window and is not clipped
  * no text element outside a sideways-scrolling box (a `.table-scroll` table, the tab bar) sticks out of the window

    python scripts/dashboard_layout_check.py --server postgresql://postgres:postgrespassword@127.0.0.1:5432/postgres
    python scripts/dashboard_layout_check.py --server ... --shots docs/ux/dashboards --tag after-
    python scripts/dashboard_layout_check.py --server ... --pages arp --sizes 360x640

Prints a PASS/FAIL table and exits 1 on any FAIL. The scratch database is dropped at the end.
"""

from __future__ import annotations

import argparse
import codecs
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
DEMO_PASSWORD = "dash-demo-pass"
SIZES = ["360x640", "412x915"]
SCHEMES = ["dark", "light"]
UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36"
)
# page key -> (login, path)
PAGES = {
    "arp": ("arp.demo", "/arp"),
    "trainer": ("trainer.demo", "/trainer"),
    "coach": ("coach.demo", "/review"),
}
CHECK_JS = """
() => {
  const doc = document.scrollingElement;
  const h = document.querySelector('h1');
  const r = h ? h.getBoundingClientRect() : null;
  const inside = (el) => {
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      const ox = getComputedStyle(a).overflowX;
      if (ox === 'auto' || ox === 'scroll') return true;
    }
    return false;
  };
  const stick = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (inside(el)) continue;
    const b = el.getBoundingClientRect();
    if (b.width === 0 || b.height === 0) continue;
    if (b.right > window.innerWidth + 1 || b.left < -1) {
      const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
      if (own) stick.push((el.tagName + '.' + el.className).slice(0, 50));
    }
  }
  return {
    scrollWidth: doc.scrollWidth, innerWidth: window.innerWidth,
    h1: h ? {left: r.left, right: r.right, clipped: h.scrollWidth > h.clientWidth + 1,
             text: h.textContent.trim().slice(0, 40)} : null,
    stick: stick.slice(0, 5),
  };
}
"""


def _url(base: Any, db: str | None, driver: str) -> str:
    url = base.set(drivername=driver)
    if db is not None:
        url = url.set(database=db)
    return str(url.render_as_string(hide_password=False))


def start_server(server_url: str) -> tuple[str, Any, Any, str]:
    base = make_url(server_url)
    db = f"abhyas_dash_{uuid.uuid4().hex[:10]}"
    admin = create_engine(_url(base, None, "postgresql+psycopg2"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db}"'))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "DATABASE_URL": _url(base, db, "postgresql+asyncpg"),
        "ALEMBIC_DATABASE_URL": _url(base, db, "postgresql"),
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
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    for args in (["-m", "alembic", "upgrade", "head"], ["-m", "backend.app.db.seed"]):
        done = subprocess.run(  # noqa: S603
            [sys.executable, *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
        )
        if done.returncode != 0:
            raise RuntimeError(done.stderr[-1500:])
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            if httpx.get(f"{url}/healthz", timeout=2).status_code == 200:
                return url, proc, admin, db
        except httpx.HTTPError:
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError("server did not start")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--server", default=os.environ.get("TEST_DATABASE_URL", ""))
    parser.add_argument("--sizes", nargs="*", default=SIZES)
    parser.add_argument("--pages", nargs="*", default=list(PAGES))
    parser.add_argument("--shots", default="")
    parser.add_argument("--tag", default="")
    parser.add_argument("--lang", default="hi", choices=["hi", "en"])
    parser.add_argument("--csv", action="store_true", help="also download every CSV link once")
    parser.add_argument("--dump", default="", help="save each page's visible text here")
    args = parser.parse_args()
    if not args.server:
        print("give --server or set TEST_DATABASE_URL", file=sys.stderr)
        return 2
    from playwright.sync_api import sync_playwright

    url, proc, admin, db = start_server(args.server)
    rows: list[tuple[str, str, str, str, str]] = []
    downloads: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for key in args.pages:
                login, path = PAGES[key]
                for size in args.sizes:
                    width, height = (int(v) for v in size.split("x"))
                    for scheme in SCHEMES:
                        ctx = browser.new_context(
                            viewport={"width": width, "height": height},
                            device_scale_factor=2,
                            is_mobile=True,
                            has_touch=True,
                            user_agent=UA,
                            color_scheme=scheme,  # type: ignore[arg-type]
                        )
                        page = ctx.new_page()
                        page.goto(f"{url}/login")
                        page.fill("#username", login)
                        page.fill("#password", DEMO_PASSWORD)
                        page.click("button[type=submit]")
                        page.wait_for_load_state("networkidle")
                        if args.lang == "en":
                            page.goto(f"{url}/lang/en?next={path}")
                        else:
                            page.goto(f"{url}{path}")
                        page.wait_for_load_state("networkidle")
                        res = page.evaluate(CHECK_JS)
                        if args.dump:
                            Path(args.dump).mkdir(parents=True, exist_ok=True)
                            (Path(args.dump) / f"{key}-{args.lang}.txt").write_text(
                                page.inner_text("body"), encoding="utf-8"
                            )
                        problems: list[str] = []
                        if res["scrollWidth"] > res["innerWidth"]:
                            problems.append(
                                f"scrollWidth {res['scrollWidth']} > {res['innerWidth']}"
                            )
                        h1 = res["h1"]
                        if h1 is None:
                            problems.append("no h1")
                        elif h1["left"] < 0 or h1["right"] > res["innerWidth"] or h1["clipped"]:
                            problems.append(f"h1 cut ({h1['left']:.0f}..{h1['right']:.0f})")
                        if res["stick"]:
                            problems.append("sticks out: " + ", ".join(res["stick"]))
                        status = "FAIL" if problems else "PASS"
                        rows.append((key, size, scheme, status, "; ".join(problems)))
                        if args.shots:
                            out = Path(args.shots)
                            out.mkdir(parents=True, exist_ok=True)
                            page.screenshot(
                                path=str(out / f"{args.tag}{key}-{size}-{scheme}.png"),
                                full_page=False,
                            )
                        if args.csv and scheme == "light" and size == args.sizes[0]:
                            links = page.eval_on_selector_all(
                                "a.csv-link", "els => els.map(e => e.href)"
                            )
                            for href in links:
                                r = ctx.request.get(href)
                                body = r.body()
                                disposition = r.headers.get("content-disposition", "")
                                ok = (
                                    r.status == 200
                                    and body.startswith(codecs.BOM_UTF8)
                                    and disposition.startswith("attachment;")
                                )
                                lines = body.decode("utf-8").count(chr(10))
                                downloads.append(
                                    f"{'OK  ' if ok else 'FAIL'} {key} {href.split(url)[1]} "
                                    f"-> {r.status}, {lines} lines, {disposition}"
                                )
                        ctx.close()
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        admin.dispose()
    print("page    size     scheme  result  detail")
    for key, size, scheme, status, detail in rows:
        print(f"{key:<7} {size:<8} {scheme:<6}  {status:<6}  {detail}")
    for line in downloads:
        print(line)
    failed = any(r[3] == "FAIL" for r in rows) or any(d.startswith("FAIL") for d in downloads)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
