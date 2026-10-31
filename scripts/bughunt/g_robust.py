# ruff: noqa
"""Journey G: robustness (no model calls except none: uses 'मेरी प्रगति' which is rule-based)."""

import sys, time

sys.path.insert(0, "scripts/bughunt")
import bh

view = sys.argv[1] if len(sys.argv) > 1 else "phone"
idle = int(sys.argv[2]) if len(sys.argv) > 2 else 0
h = bh.Hunt(f"G_robust_{view}", view)
p = h.page
# 1. not logged in
for path in (
    "/teacher",
    "/arp",
    "/trainer",
    "/review",
    "/admin",
    "/teacher/progress",
    "/api/auth/me",
):
    r = p.goto(bh.BASE + path)
    h.log(f"## anon GET {path} -> {p.url.replace(bh.BASE, '')} status={r.status}")
# 2. login, first load, timing
h.run([["login", "teacher.demo3"], ["logout"], ["login", "teacher.demo3"], ["css", "#start-skip"]])
t0 = time.time()
p.reload()
p.wait_for_load_state("networkidle")
h.log(f"## reload time {time.time() - t0:.1f}s")
h.seen_rows = len(h.state()["rows"])
# 3. double tap send
before = len(h.state()["rows"])
p.fill("#chat-input", "मेरी प्रगति")
p.dblclick("#btn-send")
time.sleep(6)
d = h.state()
n_teacher = sum(1 for r in d["rows"][before:] if r["kind"] == "teacher")
n_app = sum(1 for r in d["rows"][before:] if r["kind"] == "app")
h.log(f"## double-tap send: new teacher bubbles={n_teacher} app bubbles={n_app}")
p.keyboard.press("Enter") if False else None
# 4. Enter key sends
p.fill("#chat-input", "मेरी प्रगति")
p.press("#chat-input", "Enter")
time.sleep(5)
d = h.state()
h.log(f"## Enter-key send: rows={len(d['rows'])} last={d['rows'][-1]['text'][:80]!r}")
# 5. offline then send then online
h.ctx.set_offline(True)
time.sleep(2)
h.log(f"## offline banner: {p.inner_text('#network-banner')!r}")
rows0 = len(h.state()["rows"])
p.fill("#chat-input", "मेरी प्रगति")
p.click("#btn-send")
time.sleep(3)
d = h.state()
h.log(
    f"## offline send: rows {rows0}->{len(d['rows'])} last={d['rows'][-1]['text'][:60]!r} status-bar={p.inner_text('#status-bar')[:100]!r}"
)
h.snap("offline_send")
r = None
try:
    p.reload()
    time.sleep(2)
    h.log(f"## offline reload -> title={p.title()!r} body={p.inner_text('body')[:200]!r}")
    h.snap("offline_reload")
except Exception as e:
    h.log(f"!! offline reload error: {str(e)[:160]}")
h.ctx.set_offline(False)
time.sleep(1)
p.goto(bh.BASE + "/teacher")
p.wait_for_load_state("networkidle")
time.sleep(8)
d = h.state()
h.log(
    f"## back online: rows={len(d['rows'])} last teacher/app: {[(r['kind'], r['text'][:40]) for r in d['rows'][-3:]]}"
)
h.snap("online_again")
# 6. slow 3G
cdp = h.ctx.new_cdp_session(p)
cdp.send(
    "Network.emulateNetworkConditions",
    {"offline": False, "latency": 400, "downloadThroughput": 50000, "uploadThroughput": 25000},
)
cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
t0 = time.time()
p.goto(bh.BASE + "/teacher")
p.wait_for_load_state("load")
h.log(f"## slow3g /teacher load={time.time() - t0:.1f}s")
rows0 = len(h.state()["rows"])
t0 = time.time()
p.fill("#chat-input", "मेरी प्रगति")
p.click("#btn-send")
h.wait_idle(rows0, timeout=60)
h.log(f"## slow3g send->reply {time.time() - t0:.1f}s")
cdp.send(
    "Network.emulateNetworkConditions",
    {"offline": False, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1},
)
cdp.send("Network.setCacheDisabled", {"cacheDisabled": False})
# 7. two tabs
p2 = h.ctx.new_page()
p2.goto(bh.BASE + "/teacher")
p2.wait_for_load_state("networkidle")
rows0 = len(h.state()["rows"])
p.fill("#chat-input", "मेरी प्रगति")
p.click("#btn-send")
time.sleep(7)
p2.reload()
p2.wait_for_load_state("networkidle")
n2 = p2.eval_on_selector_all("#chat-messages .msg-row", "e=>e.length")
h.log(f"## two tabs: tab1 rows={len(h.state()['rows'])} tab2(after reload) rows={n2}")
p2.fill("#chat-input", "मेरी प्रगति")
p2.click("#btn-send")
time.sleep(7)
time.sleep(8)
h.log(f"## two tabs: tab1 rows after tab2 send={len(h.state()['rows'])}")
p2.close()
# 8. idle then continue
if idle:
    h.log(f"## idle {idle}s")
    time.sleep(idle)
    rows0 = len(h.state()["rows"])
    p.fill("#chat-input", "मेरी प्रगति")
    p.click("#btn-send")
    h.wait_idle(rows0, timeout=60)
    d = h.state()
    h.log(
        f"## after idle: url={p.url.replace(bh.BASE, '')} rows={len(d['rows'])} last={d['rows'][-1]['text'][:60]!r}"
    )
    h.snap("after_idle")
# 9. back button
p.goto(bh.BASE + "/teacher/progress")
p.wait_for_load_state("networkidle")
p.go_back()
p.wait_for_load_state("networkidle")
h.log(f"## back -> {p.url.replace(bh.BASE, '')} rows={len(h.state()['rows'])}")
h.log(f"## CONSOLE ({len(h.console)}): {h.console[:10]}")
h.log(f"## HTTP>=400 ({len(h.bad)}): {h.bad[:15]}")
h.close()
