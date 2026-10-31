# ruff: noqa
"""K1 check: for each child, list his lines in order and flag a near-repeat of his previous line.

    python -X utf8 scripts/bughunt/k1_check.py <out file> [...]

Reads the driver's .out transcripts (APP[<child>] lines, with the teacher line before each).
"""

import difflib
import re
import sys

from backend.app.config import settings
from backend.app.llm.roles.child_voice import _core_tokens, is_near_repeat

CHILD = re.compile(r"^   APP\[(रवि|प्रिया|अमन)\] \([^)]*\): \1 / +(.*?)( / +(बज रही है…|ऑडियो संदेश|अंग्रेज़ी में देखें).*)?$")
SAY = re.compile(r"^## say: (.*)$")


def sim(a: str, b: str) -> float:
    x, y = _core_tokens(a), _core_tokens(b)
    if not x or not y:
        return 1.0 if a.strip() == b.strip() else 0.0
    return difflib.SequenceMatcher(None, x, y).ratio()


bad_total = 0
for path in sys.argv[1:]:
    print(f"=== {path}")
    last: dict[str, str] = {}
    teacher = ""
    n = 0
    for ln in open(path, encoding="utf-8", errors="replace"):
        ln = ln.rstrip("\n")
        m = SAY.match(ln)
        if m:
            teacher = m.group(1)
            continue
        c = CHILD.match(ln)
        if not c:
            continue
        who, line = c.group(1), c.group(2).strip()
        n += 1
        prev = last.get(who)
        s = sim(line, prev) if prev else 0.0
        flag = ""
        if prev and (is_near_repeat(line, prev) or s >= settings.CHILD_REPEAT_SIMILARITY):
            flag = "  <<< NEAR-REPEAT"
            bad_total += 1
        print(f"[{n:02d}] teacher: {teacher[:90]}")
        print(f"     {who}: {line}   (sim to previous {s:.2f}){flag}")
        last[who] = line
print(f"\nNEAR-REPEATS: {bad_total}")
