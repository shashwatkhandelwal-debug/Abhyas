"""Live child_voice check: real Haiku calls over real rule-engine responses.

Usage: python -m eval.child_voice_live [N]   (needs ANTHROPIC_API_KEY; never prints it)
Reports the fallback_used rate (template used) and the word-count distribution per kind.
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from backend.app.content_models import PersonaCard
from backend.app.llm.roles import child_voice as cv
from backend.app.rule_engine.domain import (
    ChildResponse,
    ChildRuntime,
    ChildState,
    Domain,
    Problem,
    ResponseKind,
    SceneState,
    TaggedTurn,
    TeachingAct,
)
from backend.app.rule_engine.engine import RuleEngine

ROOT = Path(__file__).resolve().parent.parent
A = TeachingAct
TURNS = [
    TaggedTurn(acts=[A.ASK_TO_EXPLAIN], addressed_child="ravi"),
    TaggedTurn(acts=[A.CONCRETE_REPRESENTATION], addressed_child="all"),
    TaggedTurn(acts=[A.ASK_TO_EXPLAIN], addressed_child="priya"),
    TaggedTurn(acts=[A.TELL_ANSWER], addressed_child="aman"),
    TaggedTurn(acts=[A.PROBE_SIMPLER_CASE], addressed_child="ravi"),
    TaggedTurn(acts=[A.MODEL_STEP_ALOUD], addressed_child="all"),
    TaggedTurn(acts=[A.ASK_TO_EXPLAIN], addressed_child="aman"),
    TaggedTurn(
        acts=[A.GIVE_NEW_PROBLEM], addressed_child="all", problem=Problem(type="sub", a=43, b=27)
    ),
    TaggedTurn(acts=[A.ASK_TO_EXPLAIN], addressed_child="ravi"),
    TaggedTurn(acts=[A.REPEAT_QUESTION], addressed_child="priya"),
]


def collect(limit: int) -> list[ChildResponse]:
    engine = RuleEngine()
    out: list[ChildResponse] = []
    for pair in [(52, 17), (43, 27), (61, 28), (74, 39), (85, 46)]:
        items = [Problem(type="sub", a=pair[0], b=pair[1]), Problem(type="sub", a=43, b=27)]
        kids = [
            ChildRuntime(
                persona_id="ravi",
                misconception="SUB_SMALLER_FROM_LARGER",
                temperament="confident",
                state=ChildState.MISCONCEPTION,
            ),
            ChildRuntime(
                persona_id="priya",
                misconception="SUB_BORROW_NO_DECREMENT",
                temperament="shy",
                state=ChildState.MISCONCEPTION,
            ),
            ChildRuntime(
                persona_id="aman",
                misconception="SUB_WRITE_ZERO_WHEN_STUCK",
                temperament="distracted",
                state=ChildState.MISCONCEPTION,
            ),
        ]
        scene = SceneState(
            move_id="NUM_SUB_REGROUP_BUNDLES",
            domain=Domain.NUMERACY,
            effective_acts=[
                A.ASK_TO_EXPLAIN,
                A.CONCRETE_REPRESENTATION,
                A.CONTRAST_TWO_ANSWERS,
                A.PROBE_SIMPLER_CASE,
            ],
            target_causes=["SUB_SMALLER_FROM_LARGER", "SUB_BORROW_NO_DECREMENT"],
            items=items,
            current_item=items[0],
            children=kids,
            max_turns=15,
        )
        for t in TURNS:
            if scene.ended:
                break
            for r in engine.step(scene, t).responses:
                if r.kind != ResponseKind.SILENT:
                    out.append(r)
    # spread over kinds: round-robin so every kind seen gets represented
    by_kind: dict[ResponseKind, list[ChildResponse]] = {}
    for r in out:
        by_kind.setdefault(r.kind, []).append(r)
    picked: list[ChildResponse] = []
    while len(picked) < limit and any(by_kind.values()):
        for k in list(by_kind):
            if by_kind[k] and len(picked) < limit:
                picked.append(by_kind[k].pop(0))
    return picked


async def main(n: int) -> None:
    personas = {
        p.stem: PersonaCard.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
        for p in (ROOT / "content" / "personas").glob("*.yaml")
    }
    fallback_flags: list[bool] = []
    events: list[tuple[int, bool, str]] = []
    orig_log = cv.log_role_call
    orig_guard = cv.record_guard_event
    cv.log_role_call = lambda role, model, started, fb: fallback_flags.append(fb)  # type: ignore[assignment]
    cv.record_guard_event = lambda role, attempt, ok, msg: events.append((attempt, ok, msg))  # type: ignore[assignment]
    rows: list[dict[str, Any]] = []
    try:
        for r in collect(n):
            fallback_flags.clear()
            events.clear()
            line = await cv.voice_child_line(r, personas[r.persona_id])
            rows.append(
                {
                    "kind": r.kind.value,
                    "persona": r.persona_id,
                    "fallback": fallback_flags[-1],
                    "words": len(line.split()),
                    "guard": [(a, ok, m) for a, ok, m in events],
                    "line": line,
                }
            )
    finally:
        cv.log_role_call = orig_log  # type: ignore[assignment]
        cv.record_guard_event = orig_guard  # type: ignore[assignment]
    for row in rows:
        print(
            f"{row['kind']:<18}{row['persona']:<6} fb={row['fallback']!s:<5} w={row['words']:<3} "
            f"guard={[(a, ok) for a, ok, _ in row['guard']]} | {row['line']}"
        )
        for a, ok, m in row["guard"]:
            if not ok:
                print(f"    attempt {a} failed: {m}")
    fb = sum(1 for r in rows if r["fallback"])
    print(f"\nN={len(rows)} fallback_used={fb} ({100 * fb / max(len(rows), 1):.0f}%)")
    print("kinds:", dict(Counter(r["kind"] for r in rows)))
    print("max words:", max((r["words"] for r in rows), default=0))


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 20))
