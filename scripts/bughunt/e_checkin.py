"""Journey E1: walk the class check-in through every topic x level x struggle option (buttons only)."""
import sys, time
sys.path.insert(0, "scripts/bughunt")
import bh

view = sys.argv[1] if len(sys.argv) > 1 else "phone"
h = bh.Hunt(f"E_checkin_{view}", view)
h.run([["login", "teacher.demo3"], ["logout"], ["login", "teacher.demo3"], ["css", "#start-skip"]])

def chips():
    return h.state()["actions"]

def start():
    h.page.click("#btn-suggest"); time.sleep(0.5)
    h.page.click("[data-btn-id=btn_chk_start]"); time.sleep(2.5)
    h.snap("checkin")

topics = None
done = set()
for topic_i in range(4):
    for level_i in (0, 1, 2):
        start()
        topics = chips()
        topic = topics[topic_i]
        h.log(f"### topic {topic_i}: {topic}")
        h.click(topic)
        levels = chips()
        level = levels[level_i]
        h.log(f"### level: {level}")
        h.click(level)
        opts = chips()
        h.log(f"### options after level: {opts}")
        if level_i == 0 or not opts:
            continue
        for o in opts[:6]:
            key = (topic, level, o)
            if key in done:
                continue
            done.add(key)
            # re-walk to this point for each option
            start(); h.click(topic); h.click(level)
            h.log(f"### struggle option: {o}")
            h.click(o)
            h.log(f"### after option actions: {chips()}")
h.log(f"## CONSOLE ({len(h.console)}): {h.console[:10]}")
h.log(f"## HTTP>=400 ({len(h.bad)}): {h.bad[:10]}")
h.close()
