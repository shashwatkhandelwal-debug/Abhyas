"""Simulate all 4 seed moves' model rehearsals through RuleEngine.step."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))

import yaml

from backend.app.rule_engine.domain import (
    ChildRuntime,
    ChildState,
    Domain,
    Problem,
    SceneState,
    TaggedTurn,
    TeachingAct,
)
from backend.app.rule_engine.engine import RuleEngine

MOVES_DIR = Path("content-seed/moves")
PERSONAS_DIR = Path("content-seed/personas")


def load_personas() -> dict[str, dict]:
    personas = {}
    for p_file in PERSONAS_DIR.glob("*.yaml"):
        with open(p_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            personas[data["id"]] = data
    return personas


def run_model_rehearsal(move_file: Path, personas: dict[str, dict]) -> dict:
    with open(move_file, encoding="utf-8") as f:
        move = yaml.safe_load(f)

    domain = Domain.NUMERACY if move["domain"] == "numeracy" else Domain.LITERACY
    scenario = move["scenario"]
    items = [Problem(**it) for it in scenario["items"]]
    children = []
    for c_spec in scenario["children"]:
        p_data = personas[c_spec["persona_id"]]
        children.append(
            ChildRuntime(
                persona_id=c_spec["persona_id"],
                misconception=c_spec["misconception"],
                temperament=p_data["temperament"],
                state=ChildState.MISCONCEPTION,
            )
        )

    scene = SceneState(
        move_id=move["id"],
        domain=domain,
        effective_acts=move["teaching_acts_effective"],
        target_causes=move["target_causes"],
        items=items,
        current_item=items[0],
        children=children,
        guess_lexicon=scenario.get("guess_lexicon", {}),
    )

    rehearsal = move["model_rehearsal"]
    turn_results = []
    for turn_idx, turn in enumerate(rehearsal, 1):
        if turn.get("speaker") != "teacher":
            continue
        acts = [TeachingAct(a) for a in turn.get("acts", [])]
        addressed = turn.get("addressed")
        prob = Problem(**turn["problem"]) if "problem" in turn and turn["problem"] else None
        tagged = TaggedTurn(acts=acts, addressed_child=addressed, problem=prob)
        res = RuleEngine.step(scene, tagged)
        turn_results.append(
            {
                "turn_index": turn.get("turn_index", turn_idx),
                "acts": [a.value for a in acts],
                "addressed": addressed,
                "ended": res.ended,
                "end_reason": res.end_reason,
                "child_states": {c.persona_id: c.state.name for c in scene.children},
            }
        )

    all_correct = all(c.state == ChildState.CORRECT for c in scene.children)
    return {
        "move_id": move["id"],
        "turns_count": len(turn_results),
        "ended": scene.ended,
        "end_reason": scene.end_reason,
        "all_correct": all_correct,
        "final_states": {c.persona_id: c.state.name for c in scene.children},
        "turns": turn_results,
    }


def main() -> None:
    personas = load_personas()
    moves = [
        "NUM_SUB_REGROUP_BUNDLES.yaml",
        "NUM_ADD_CARRY_BUNDLES.yaml",
        "NUM_PLACE_VALUE_BUNDLES.yaml",
        "LIT_MATRA_BLENDING.yaml",
    ]
    for m in moves:
        res = run_model_rehearsal(MOVES_DIR / m, personas)
        print(f"=== {res['move_id']} ===")
        print(
            f"Ended: {res['ended']}, End Reason: {res['end_reason']}, All Correct: {res['all_correct']}"
        )
        print(f"Final States: {res['final_states']}")
        for t in res["turns"]:
            print(f"  Turn {t['turn_index']} ({t['addressed']}, {t['acts']}): {t['child_states']}")
        print()


if __name__ == "__main__":
    main()
