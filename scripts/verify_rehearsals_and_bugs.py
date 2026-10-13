"""Verification script for rule engine bug outputs and seed move model rehearsals."""

from pathlib import Path

import yaml

from backend.app.content_models import MoveCard, PersonaCard
from backend.app.rule_engine.bugs.addition import (
    add_carry_forgotten,
    add_carry_wrong_digit,
    add_no_carry,
)
from backend.app.rule_engine.bugs.place_value import (
    pv_bundle_as_one,
    pv_concat_spoken,
    pv_reversal,
)
from backend.app.rule_engine.bugs.subtraction import (
    sub_borrow_no_decrement,
    sub_smaller_from_larger,
    sub_write_zero_when_stuck,
)
from backend.app.rule_engine.child_state import ChildState
from backend.app.rule_engine.domain import (
    ChildRuntime,
    Domain,
    Problem,
    SceneState,
    TaggedTurn,
    TeachingAct,
)
from backend.app.rule_engine.engine import RuleEngine


def verify_bug_rules() -> None:
    print("=== 1. Verifying Bug Rules on Seed Items ===")
    # 43 - 27
    prob_sub = Problem(type="sub", a=43, b=27)
    ans_sfl = sub_smaller_from_larger(prob_sub).answer
    ans_bnd = sub_borrow_no_decrement(prob_sub).answer
    ans_zwz = sub_write_zero_when_stuck(prob_sub).answer
    print(f"43-27 SUB_SMALLER_FROM_LARGER: {ans_sfl} (expected 24)")
    print(f"43-27 SUB_BORROW_NO_DECREMENT: {ans_bnd} (expected 26)")
    print(f"43-27 SUB_WRITE_ZERO_WHEN_STUCK: {ans_zwz} (expected 20)")
    assert ans_sfl == 24
    assert ans_bnd == 26
    assert ans_zwz == 20

    # 38 + 45
    prob_add = Problem(type="add", a=38, b=45)
    ans_acf = add_carry_forgotten(prob_add).answer
    ans_anc = add_no_carry(prob_add).answer
    ans_acw = add_carry_wrong_digit(prob_add).answer
    print(f"38+45 ADD_CARRY_FORGOTTEN: {ans_acf} (expected 73)")
    print(f"38+45 ADD_NO_CARRY: {ans_anc} (expected 713)")
    print(f"38+45 ADD_CARRY_WRONG_DIGIT: {ans_acw} (expected 101)")
    assert ans_acf == 73
    assert ans_anc == 713
    assert ans_acw == 101

    # place value (4, 7)
    prob_pv = Problem(type="place_value", tens=4, ones=7)
    ans_pvr = pv_reversal(prob_pv).answer
    ans_bao = pv_bundle_as_one(prob_pv).answer
    ans_pcs = pv_concat_spoken(prob_pv).answer
    print(f"place value (4,7) PV_REVERSAL: {ans_pvr} (expected 74)")
    print(f"place value (4,7) PV_BUNDLE_AS_ONE: {ans_bao} (expected 11)")
    print(f"place value (4,7) PV_CONCAT_SPOKEN: {ans_pcs} (expected 407)")
    assert ans_pvr == 74
    assert ans_bao == 11
    assert ans_pcs == 407
    print("All bug rule answers match expectations exactly!\n")


def load_personas() -> dict[str, PersonaCard]:
    personas = {}
    for p_file in (Path("content") / "personas").glob("*.yaml"):
        with open(p_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            p = PersonaCard.model_validate(data)
            personas[p.id] = p
    return personas


def verify_model_rehearsals() -> None:
    print("=== 2. Verifying 4 Seed Move Model Rehearsals ===")
    personas = load_personas()
    moves_dir = Path("content") / "moves"
    seed_move_files = [
        "NUM_SUB_REGROUP_BUNDLES.yaml",
        "NUM_ADD_CARRY_BUNDLES.yaml",
        "NUM_PLACE_VALUE_BUNDLES.yaml",
        "LIT_MATRA_BLENDING.yaml",
    ]

    for fname in seed_move_files:
        with open(moves_dir / fname, encoding="utf-8") as f:
            move_data = yaml.safe_load(f)
            move = MoveCard.model_validate(move_data)

        # Build items
        items: list[Problem] = []
        for raw_item in move.scenario.items:
            t = raw_item.get("type", "sub")
            items.append(
                Problem(
                    type=t,
                    a=raw_item.get("a"),
                    b=raw_item.get("b"),
                    tens=raw_item.get("tens"),
                    ones=raw_item.get("ones"),
                    word=raw_item.get("word"),
                )
            )

        # Build children
        children: list[ChildRuntime] = []
        for sc in move.scenario.children:
            p = personas.get(sc.persona_id)
            temperament = p.temperament if p else "confident"
            children.append(
                ChildRuntime(
                    persona_id=sc.persona_id,
                    misconception=sc.misconception,
                    temperament=temperament,
                    state=ChildState.MISCONCEPTION,
                )
            )

        # Domain
        domain = Domain.LITERACY if move.domain == "literacy" else Domain.NUMERACY
        effective_acts = [
            TeachingAct(a)
            for a in move.teaching_acts_effective
            if a in TeachingAct._value2member_map_
        ]

        scene = SceneState(
            move_id=move.id,
            domain=domain,
            effective_acts=effective_acts,
            target_causes=[c.misconception for c in children if c.misconception],
            items=items,
            current_item=items[0],
            children=children,
            max_turns=10,
        )

        print(f"Running model rehearsal for move: {move.id}")
        for i, turn in enumerate(move.model_rehearsal):
            if turn.speaker != "teacher":
                continue
            acts = [TeachingAct(a) for a in turn.acts if a in TeachingAct._value2member_map_]
            tagged = TaggedTurn(
                acts=acts,
                addressed_child=turn.addressed,
                item=turn.problem,
            )
            step_res = RuleEngine.step(scene, tagged)
            states_str = ", ".join(f"{c.persona_id}={c.state.name}" for c in scene.children)
            print(
                f"  Turn {i + 1} ({tagged.addressed_child}): [{states_str}], ended={step_res.ended} ({step_res.end_reason})"
            )

        all_corr = all(c.state == ChildState.CORRECT for c in scene.children)
        print(
            f"Result for {move.id}: all_correct={all_corr}, ended={scene.ended}, end_reason={scene.end_reason}"
        )
        assert all_corr or (scene.ended and scene.end_reason == "all_correct"), (
            f"Move {move.id} failed to reach all_correct!"
        )

    print("All 4 seed move model rehearsals successfully reached all_correct!\n")


if __name__ == "__main__":
    verify_bug_rules()
    verify_model_rehearsals()
