"""Real-phone layout check for the teacher chat: is the input always on screen, never behind a scroll?

Drives the real app (mock DB and providers, via scripts/composer_layout_check.py) in Chromium emulating
an Android phone (Chrome user agent, deviceScaleFactor 2.75, touch). Three window variants per size:

  normal    visible window height = the phone's height
  toolbar   visible height is 56 px smaller (browser address bar showing) while CSS large-viewport
            values (vh) still equal the full height, as on a real phone; done by rewriting `Nvh` in the
            served stylesheet to the large viewport, so dvh/svh/innerHeight stay the visible values
  keyboard  visible height is 250 px smaller, input focused

For every state, size, variant and colour scheme it asserts: the input is fully inside innerHeight and
hit-testable at its centre; every quick-reply button is fully visible and at least 44 px tall (the first
one only, if the row scrolls sideways); the message list is at least 120 px tall (80 with the keyboard);
the page itself does not scroll. Sheet states click the suggestions button (`#btn-suggest`), open one
section, and also check the sheet is at most 55 percent of the window; they report N/A on a build with no
sheet.

    python scripts/phone_layout_check.py                      # prints the PASS/FAIL table
    python scripts/phone_layout_check.py --shots docs/ux/phone_redesign --tag before-
    python scripts/phone_layout_check.py --sizes 360x640 --states start consent
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import composer_layout_check as clc  # noqa: E402

SIZES = ["360x560", "360x640", "393x852", "412x915"]
VARIANTS = ["normal", "toolbar", "keyboard"]
TOOLBAR_PX = 56
KEYBOARD_PX = 250
MIN_LIST_PX = 120
MIN_LIST_KB_PX = 80
MIN_TAP_PX = 44
SHEET_MAX_FRACTION = 0.55
UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36"
)
SHEET_SECTIONS = {  # state -> id of the one <details> left open
    "sheet_handbook": "sheet-handbook",
    "sheet_samples": "sample-tray",
    "sheet_tray": "fast-track-tray",
}
# state -> scenario key in build_scenarios()/extra scenarios
STATES = {
    "start": "start",
    "consent": "consent",
    "name": "name",
    "learn": "learn",
    "checkin_module": "checkin_module",
    "checkin_outcome": "checkin_tip",
    "sorter_range": "sorter_range",
    "sorter_result": "sorter",
    "scene_checkin": "checkin_scene",
    "sheet_handbook": "learn",
    "sheet_samples": "learn",
    "sheet_tray": "learn",
}


def extra_scenarios(base: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    from backend.app.class_profile import checkin_flow, level_sorter
    from backend.app.class_profile.library import load_library
    from backend.app.core.messages import get_message
    from backend.app.sessions.state_machine import SessionContext, SessionStateEnum
    from backend.app.web.chat_view import build_view

    ctx = SessionContext.model_construct(
        address_form="f", current_state=SessionStateEnum.DONE, checkin_page=0, checkin_stage=""
    )
    module = checkin_flow._module_screen(ctx, load_library(), key="chk_module_ask")
    sctx = SessionContext.model_construct(
        address_form="f", current_state=SessionStateEnum.DONE, level_subject="reading", level_idx=1
    )
    content = level_sorter.load_content()
    count = level_sorter._count_screen(sctx, content)
    return {
        "name": {
            "messages": [clc.msg("n1", get_message("ask_name"))],
            "scene": None,
            "view": build_view(
                onboarding="PROFILE_NAME", move_id="m01", state="LEARN", with_samples=True
            ),
        },
        "checkin_module": {
            "messages": [clc._wire(module, "cm1")],
            "scene": None,
            "view": build_view(onboarding="READY", move_id="m01", state="DONE", with_samples=True),
        },
        "sorter_range": {
            "messages": [clc._wire(count, "sr1")],
            "scene": None,
            "view": build_view(onboarding="READY", move_id="m01", state="DONE", with_samples=True),
        },
    }


MEASURE_JS = """([kb, sheetOpen]) => {
  const box = (e) => { const b = e.getBoundingClientRect();
    return {top: b.top, bottom: b.bottom, left: b.left, right: b.right, h: b.height}; };
  const vh = window.innerHeight, vw = window.innerWidth;
  const input = document.getElementById('chat-input');
  const list = document.getElementById('chat-messages');
  if (list) list.scrollTop = list.scrollHeight;
  const out = {vh, vw, problems: []};
  const bad = (m) => out.problems.push(m);
  if (!input) { bad('no #chat-input'); return out; }
  const ib = box(input);
  const visible = (b) => b.top >= -0.5 && b.bottom <= vh + 0.5 && b.left >= -0.5 && b.right <= vw + 0.5;
  if (!visible(ib)) bad(`input ${ib.top.toFixed(0)}-${ib.bottom.toFixed(0)} not inside height ${vh}`);
  else {
    const hit = document.elementFromPoint((ib.left + ib.right) / 2, (ib.top + ib.bottom) / 2);
    const wrap = input.closest('.composer-wrapper, #dock, .composer-form');
    if (!(hit === input || (wrap && wrap.contains(hit)))) bad('input centre is covered by another element');
  }
  ['btn-mic', 'btn-send', 'btn-suggest'].forEach((id) => {
    const e = document.getElementById(id);
    if (!e) return;
    const b = box(e);
    if (!visible(b)) bad(`#${id} not fully on screen (${b.left.toFixed(0)}-${b.right.toFixed(0)} of ${vw})`);
    if (b.h < ${MIN_TAP_PX} - 0.5 || b.right - b.left < ${MIN_TAP_PX} - 0.5) bad(`#${id} smaller than ${MIN_TAP_PX}px`);
  });
  if (document.documentElement.scrollWidth > vw + 1) bad(`page is ${document.documentElement.scrollWidth}px wide in ${vw}`);
  const row = document.getElementById('action-row');
  let chips;
  if (row) chips = [...row.querySelectorAll('.reply-chip')];
  else {
    const q = [...document.querySelectorAll('.quick-replies')].pop();
    chips = q ? [...q.querySelectorAll('.reply-chip')] : [];
  }
  const scrolls = row ? row.scrollWidth > row.clientWidth + 1 : false;
  chips.forEach((c, i) => {
    if (scrolls && i > 0) return;
    const b = box(c);
    if (!visible(b)) bad(`button "${c.textContent.trim().slice(0, 18)}" not fully on screen (${b.top.toFixed(0)}-${b.bottom.toFixed(0)}, ${b.left.toFixed(0)}-${b.right.toFixed(0)})`);
    else {
      const lb = list ? box(list) : null;
      if (!row && lb && (b.top < lb.top - 1 || b.bottom > lb.bottom + 1)) bad(`button "${c.textContent.trim().slice(0, 18)}" clipped by the message list`);
      const hit = document.elementFromPoint((b.left + b.right) / 2, (b.top + b.bottom) / 2);
      if (!(hit === c || c.contains(hit))) bad(`button "${c.textContent.trim().slice(0, 18)}" covered`);
    }
    if (b.h < ${MIN_TAP_PX} - 0.5) bad(`button "${c.textContent.trim().slice(0, 18)}" only ${b.h.toFixed(0)}px tall`);
  });
  const lh = list ? box(list).h : 0;
  const minList = kb ? ${MIN_LIST_KB_PX} : ${MIN_LIST_PX};
  if (lh < minList) bad(`message list only ${lh.toFixed(0)}px tall (need ${minList})`);
  const sh = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);
  if (sh > vh + 1) bad(`page scrolls: scrollHeight ${sh} > ${vh}`);
  if (sheetOpen) {
    const sheet = document.getElementById('sheet');
    if (!sheet || sheet.hidden) bad('sheet not open');
    else if (box(sheet).h > vh * ${SHEET_MAX_FRACTION} + 1) bad(`sheet ${box(sheet).h.toFixed(0)}px > ${SHEET_MAX_FRACTION * 100}% of ${vh}`);
  }
  return out;
}"""
MEASURE_JS = MEASURE_JS.replace("${MIN_TAP_PX}", str(MIN_TAP_PX))
MEASURE_JS = MEASURE_JS.replace("${MIN_LIST_KB_PX}", str(MIN_LIST_KB_PX))
MEASURE_JS = MEASURE_JS.replace("${MIN_LIST_PX}", str(MIN_LIST_PX))
MEASURE_JS = MEASURE_JS.replace("${SHEET_MAX_FRACTION}", str(SHEET_MAX_FRACTION))
MEASURE_JS = MEASURE_JS.replace("${SHEET_MAX_FRACTION * 100}", str(int(SHEET_MAX_FRACTION * 100)))


def large_viewport_css(css: str, extra_px: int) -> str:
    """Make `Nvh` mean the large viewport (visible + toolbar); dvh/svh keep the visible value."""
    return re.sub(
        r"(?<![\w.])(\d+(?:\.\d+)?)vh\b",
        lambda m: f"calc({m.group(1)} * (100vh + {extra_px}px) / 100)",
        css,
    )


def run_one(page: Any, srv: Any, state: str, variant: str) -> list[str] | None:
    """Problems for one loaded state; None means the state does not exist on this build."""
    srv.current = STATES[state]
    sc = srv.scenarios[STATES[state]]
    page.unroute("**/api/chat/messages**")
    page.route(
        "**/api/chat/messages**",
        lambda route, _r=None, sc=sc: route.fulfill(
            json={
                "messages": sc["messages"], "pending": False, "scene": sc["scene"],
                "view": sc["view"], "server_time": clc.now_iso(),
            }
        ),
    )  # fmt: skip
    page.goto(srv.url, wait_until="load")
    page.wait_for_timeout(700)
    if variant == "keyboard":
        page.focus("#chat-input")
        page.wait_for_timeout(300)
    sheet_open = state in SHEET_SECTIONS
    if sheet_open:
        if page.query_selector("#btn-suggest") is None:
            return None
        page.click("#btn-suggest")
        page.wait_for_timeout(250)
        want = SHEET_SECTIONS[state]
        page.evaluate(
            """(want) => document.querySelectorAll('#sheet details').forEach((d) => {
                 d.open = d.id === want; })""",
            want,
        )
        page.wait_for_timeout(150)
    res = page.evaluate(MEASURE_JS, [variant == "keyboard", sheet_open])
    problems: list[str] = res["problems"]
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", nargs="*", default=SIZES)
    ap.add_argument("--variants", nargs="*", default=VARIANTS)
    ap.add_argument("--states", nargs="*", default=list(STATES))
    ap.add_argument("--shots", default="")
    ap.add_argument("--tag", default="")
    ap.add_argument("--verbose", action="store_true", help="print every failing reason")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    srv = clc.Server()
    srv.scenarios.update(extra_scenarios(srv.scenarios))
    out = Path(args.shots) if args.shots else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    # results[(state, size, variant)] = {scheme: problems or None}
    results: dict[tuple[str, str, str], dict[str, list[str] | None]] = {}
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception:
                browser = p.chromium.launch(channel="chrome")
            for size in args.sizes:
                w, h = (int(x) for x in size.split("x"))
                for variant in args.variants:
                    vis_h = h - (TOOLBAR_PX if variant == "toolbar" else 0)
                    vis_h -= KEYBOARD_PX if variant == "keyboard" else 0
                    for scheme in ("dark", "light"):
                        ctx = browser.new_context(
                            viewport={"width": w, "height": vis_h}, color_scheme=scheme,
                            is_mobile=True, has_touch=True, device_scale_factor=2.75,
                            user_agent=UA, service_workers="block",
                        )  # fmt: skip
                        if variant == "toolbar":

                            def fix(route: Any) -> None:
                                resp = route.fetch()
                                route.fulfill(
                                    response=resp,
                                    body=large_viewport_css(resp.text(), TOOLBAR_PX),
                                )

                            ctx.route("**/static/app.css*", fix)
                        page = ctx.new_page()
                        for state in args.states:
                            problems = run_one(page, srv, state, variant)
                            results.setdefault((state, size, variant), {})[scheme] = problems
                            if out:
                                shot = f"{args.tag}{size}-{variant}-{scheme}-{state}.png"
                                page.screenshot(path=str(out / shot))
                        ctx.close()
            browser.close()
    finally:
        srv.stop()
    return report(results, args)


def cell(r: dict[str, list[str] | None]) -> str:
    vals = [r.get("dark"), r.get("light")]
    if all(v is None for v in vals):
        return "n/a"
    failed = [s for s, v in zip(("d", "l"), vals, strict=True) if v]
    return "PASS" if not failed else "FAIL(" + "".join(failed) + ")"


def report(results: dict[tuple[str, str, str], dict[str, list[str] | None]], args: Any) -> int:
    cols = [(s, v) for s in args.sizes for v in args.variants]
    print("| state | " + " | ".join(f"{s} {v}" for s, v in cols) + " |")
    print("|---|" + "---|" * len(cols))
    fails = 0
    total = 0
    for state in args.states:
        row = []
        for s, v in cols:
            c = cell(results.get((state, s, v), {}))
            row.append(c)
            if c != "n/a":
                total += 1
                fails += c != "PASS"
        print(f"| {state} | " + " | ".join(row) + " |")
    print(
        f"\n{fails} failing of {total} state/size/variant cells (a cell fails if dark or light fails)"
    )
    shown: set[str] = set()
    for (state, s, v), r in sorted(results.items()):
        for scheme, probs in r.items():
            for pr in probs or []:
                key = f"{state}: {pr}"
                if args.verbose or key not in shown:
                    shown.add(key)
                    print(f"  FAIL {state} {s} {v} {scheme}: {pr}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
