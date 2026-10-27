"""Unit tests for rehearsal scene header and board manipulatives."""

from __future__ import annotations

from backend.app.rehearsal.header import manipulatives_dict, scene_header
from backend.app.rule_engine.child_state import ChildState
from backend.app.rule_engine.domain import ChildRuntime, Domain, Problem, SceneState


def _make_child(
    persona_id: str = "ravi",
    state: ChildState = ChildState.MISCONCEPTION,
    partial_item_key: str | None = None,
) -> ChildRuntime:
    return ChildRuntime(
        persona_id=persona_id,
        misconception="sub_smaller_from_larger",
        temperament="confident",
        state=state,
        partial_item_key=partial_item_key,
    )


def test_manipulatives_43_minus_27_before_and_after_regroup() -> None:
    """Case 1: 43 - 27 (3 < 7 requires borrow).

    Initial: 4 bundles, 3 sticks, regrouped=False.
    After PARTIAL on sub:43-27: 3 bundles, 13 sticks, regrouped=True.
    """
    prob = Problem(type="sub", a=43, b=27)
    child = _make_child("ravi", ChildState.MISCONCEPTION)

    # Initial state
    m_init = manipulatives_dict(prob, [child])
    assert m_init is not None
    assert m_init["bundles"] == 4
    assert m_init["sticks"] == 3
    assert m_init["regrouped"] is False
    assert m_init["aria_label"] == "4 बंडल और 3 तीलियाँ"

    # After teacher explains regrouping: child enters PARTIAL
    child_partial = _make_child("ravi", ChildState.PARTIAL, partial_item_key="sub:43-27")
    m_regrouped = manipulatives_dict(prob, [child_partial])
    assert m_regrouped is not None
    assert m_regrouped["bundles"] == 3
    assert m_regrouped["sticks"] == 13
    assert m_regrouped["regrouped"] is True
    assert m_regrouped["aria_label"] == "3 बंडल और 13 तीलियाँ (1 बंडल खुला)"


def test_manipulatives_61_minus_28() -> None:
    """Case 2: 61 - 28 (1 < 8 requires borrow)."""
    prob = Problem(type="sub", a=61, b=28)
    child = _make_child("ravi", ChildState.MISCONCEPTION)

    m_init = manipulatives_dict(prob, [child])
    assert m_init is not None
    assert m_init["bundles"] == 6
    assert m_init["sticks"] == 1
    assert m_init["regrouped"] is False

    child_partial = _make_child("ravi", ChildState.PARTIAL, partial_item_key="sub:61-28")
    m_regrouped = manipulatives_dict(prob, [child_partial])
    assert m_regrouped is not None
    assert m_regrouped["bundles"] == 5
    assert m_regrouped["sticks"] == 11
    assert m_regrouped["regrouped"] is True


def test_manipulatives_58_minus_23_no_regroup_needed() -> None:
    """Case 3: 58 - 23 (8 >= 3 no borrow needed).

    Regroup state must stay False even if a child is in PARTIAL state.
    """
    prob = Problem(type="sub", a=58, b=23)
    child = _make_child("ravi", ChildState.PARTIAL, partial_item_key="sub:58-23")

    m = manipulatives_dict(prob, [child])
    assert m is not None
    assert m["bundles"] == 5
    assert m["sticks"] == 8
    assert m["regrouped"] is False
    assert m["aria_label"] == "5 बंडल और 8 तीलियाँ"


def test_manipulatives_80_minus_35() -> None:
    """Case 4: 80 - 35 (0 < 5 requires borrow from 8 tens)."""
    prob = Problem(type="sub", a=80, b=35)
    child = _make_child("ravi", ChildState.MISCONCEPTION)

    m_init = manipulatives_dict(prob, [child])
    assert m_init is not None
    assert m_init["bundles"] == 8
    assert m_init["sticks"] == 0
    assert m_init["regrouped"] is False

    child_partial = _make_child("ravi", ChildState.PARTIAL, partial_item_key="sub:80-35")
    m_regrouped = manipulatives_dict(prob, [child_partial])
    assert m_regrouped is not None
    assert m_regrouped["bundles"] == 7
    assert m_regrouped["sticks"] == 10
    assert m_regrouped["regrouped"] is True
    assert m_regrouped["aria_label"] == "7 बंडल और 10 तीलियाँ (1 बंडल खुला)"


def test_manipulatives_reset_on_problem_change() -> None:
    """Case 5: Problem changes after regrouping.

    Child reached PARTIAL on 43-27. When moving to 61-28, regrouped must be False.
    """
    prob1 = Problem(type="sub", a=43, b=27)
    prob2 = Problem(type="sub", a=61, b=28)
    child = _make_child("ravi", ChildState.PARTIAL, partial_item_key="sub:43-27")

    # On prob1 it is regrouped
    m1 = manipulatives_dict(prob1, [child])
    assert m1 is not None and m1["regrouped"] is True

    # On prob2 it is NOT regrouped
    m2 = manipulatives_dict(prob2, [child])
    assert m2 is not None
    assert m2["bundles"] == 6
    assert m2["sticks"] == 1
    assert m2["regrouped"] is False


def test_manipulatives_non_subtraction_and_three_digits() -> None:
    """Case 6: Non-subtraction and a >= 100 produce None."""
    # a >= 100
    assert manipulatives_dict(Problem(type="sub", a=143, b=27)) is None

    # Addition
    assert manipulatives_dict(Problem(type="add", a=43, b=27)) is None

    # Place value
    assert manipulatives_dict(Problem(type="place_value", tens=4, ones=3)) is None

    # Literacy
    assert manipulatives_dict(Problem(type="read_word", word="मेला")) is None


def test_scene_header_includes_manipulatives() -> None:
    """Verify scene_header includes manipulatives in its returned dictionary."""
    scene = SceneState(
        move_id="m_sub_borrow",
        domain=Domain.NUMERACY,
        effective_acts=["bundles_and_sticks"],
        target_causes=["sub_smaller_from_larger"],
        items=[Problem(type="sub", a=43, b=27)],
        current_item=Problem(type="sub", a=43, b=27),
        children=[_make_child("ravi")],
        one_on_one=True,
    )
    header = scene_header(scene)
    assert header is not None
    assert header["board"] == "43 − 27"
    assert "manipulatives" in header
    assert header["manipulatives"] == {
        "bundles": 4,
        "sticks": 3,
        "regrouped": False,
        "aria_label": "4 बंडल और 3 तीलियाँ",
    }
