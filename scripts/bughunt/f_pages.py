"""Journey F: ARP, trainer, coach, admin pages + CSV exports (no model calls)."""
import re, sys, time
sys.path.insert(0, "scripts/bughunt")
import bh

view = sys.argv[1] if len(sys.argv) > 1 else "phone"
h = bh.Hunt(f"F_pages_{view}", view)
p = h.page

def visit(url, label=None):
    r = p.goto(bh.BASE + url); p.wait_for_load_state("networkidle")
    h.log(f"## GET {url} -> {p.url.replace(bh.BASE,'')} status={r.status if r else '?'} title={p.title()!r}")
    body = p.inner_text("body")
    h.log("   BODY: " + body[:1800].replace("\n", " / "))
    h.snap(re.sub(r"[^A-Za-z0-9_]", "_", label or url.strip("/")) or "root")
    # horizontal overflow check
    ov = p.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    if ov > 0: h.log(f"   !! horizontal overflow {ov}px")
    return p.eval_on_selector_all("a[href]", "els=>els.map(e=>e.getAttribute('href'))")

def csv(url):
    r = h.ctx.request.get(bh.BASE + url)
    t = r.text()
    h.log(f"## CSV {url} status={r.status} type={r.headers.get('content-type')} bytes={len(t)}")
    h.log("   HEAD: " + "\n   ".join(t.splitlines()[:4]))
    pii = re.findall(r"\b[6-9]\d{9}\b|[\w.+-]+@[\w-]+\.\w+", t)
    h.log(f"   PII-like tokens: {pii[:5]}")

for user, pages in (("arp.demo", ["/arp"]), ("trainer.demo", ["/trainer"]), ("coach.demo", ["/review"]), ("admin", ["/admin"])):
    p.goto(bh.BASE + "/logout"); p.wait_for_load_state("networkidle")
    pw = "abhyas-admin-2026" if user == "admin" else bh.PASSWORD
    p.goto(bh.BASE + "/login"); p.fill("#username", user); p.fill("#password", pw); p.click("button[type=submit]"); p.wait_for_load_state("networkidle")
    h.log(f"##### LOGIN {user} -> {p.url.replace(bh.BASE,'')}")
    links = set()
    for pg in pages:
        for l in visit(pg): links.add(l)
    h.log(f"   LINKS: {sorted(l for l in links if l and not l.startswith('http'))[:40]}")
    for l in sorted(l for l in links if l and l.startswith('/') and l not in pages and not l.startswith('/logout') and not l.startswith('/lang') and '.csv' not in l and '.jsonl' not in l and 'export' not in l)[:12]:
        visit(l)
    for l in sorted(l for l in links if l and '.csv' in l)[:8]:
        csv(l)
h.log(f"## CONSOLE ({len(h.console)}): {h.console[:10]}")
h.log(f"## HTTP>=400 ({len(h.bad)}): {h.bad[:15]}")
h.close()
