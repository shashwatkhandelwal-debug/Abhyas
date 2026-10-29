"""Unit tests for rehearsal scene header and board manipulatives."""

from __future__ import annotations

from backend.app.rehearsal.header import manipulatives_dict, scene_header
from backend.app.rehearsal.scene_store import TurnRecord
from backend.app.rule_engine.child_state import ChildState
from backend.app.rule_engine.domain import (
    ChildResponse,
    ChildRuntime,
    Domain,
    Problem,
    ResponseKind,
    SceneState,
)


def _make_child(
    persona_id: str = "ravi",
    state: ChildState = ChildState.MISCONCEPTION,
    partial_item_key: str | None = None,
) -> ChildRuntime:
    return ChildRuntime(
        persona_id=persona_id,
        misconception="SUB_SMALLER_FROM_LARGER",
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
        target_causes=["SUB_SMALLER_FROM_LARGER"],
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


# ── child understanding strip (CHILD_STRIP_ENABLED) ──────────────────────────
import pytest  # noqa: E402

from backend.app.config import settings  # noqa: E402
from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang  # noqa: E402
from backend.app.rehearsal.header import child_strip_label  # noqa: E402
from backend.app.rule_engine.bugs.registry import get_rule_info  # noqa: E402

OLD_ITEM = Problem(type="sub", a=52, b=17)
NEW_ITEM = Problem(type="sub", a=43, b=27)


def _scene(children: list[ChildRuntime], item: Problem = NEW_ITEM, one: bool = False) -> SceneState:
    return SceneState(
        move_id="m_sub_borrow",
        domain=Domain.NUMERACY,
        effective_acts=["bundles_and_sticks"],
        target_causes=["SUB_SMALLER_FROM_LARGER"],
        items=[OLD_ITEM, NEW_ITEM],
        current_item=item,
        children=children,
        one_on_one=one,
    )


def _bug_answer(item: Problem) -> int | str | None:
    return get_rule_info("SUB_SMALLER_FROM_LARGER").fn(item, {"guess_lexicon": {}}).answer


@pytest.fixture
def strip_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CHILD_STRIP_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_MODE", False)


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest):  # type: ignore[no-untyped-def]
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


@pytest.mark.parametrize(
    ("state", "key"),
    [
        (ChildState.MISCONCEPTION, "stuck"),
        (ChildState.CAN_EXPLAIN, "stuck"),
        (ChildState.PARTIAL, "learning"),
        (ChildState.CORRECT, "got"),
    ],
)
@pytest.mark.parametrize(("persona", "g"), [("ravi", "m"), ("priya", "f"), ("aman", "m")])
def test_strip_label_for_every_state(
    strip_on: None, lang: str, state: ChildState, key: str, persona: str, g: str
) -> None:
    child = _make_child(persona, state, partial_item_key=OLD_ITEM.key())
    child.last_answer = None
    assert child_strip_label(child, _scene([child])) == get_message(f"ui_strip_{key}_{g}")


def test_group_header_carries_label_per_child(strip_on: None, lang: str) -> None:
    kids = [
        _make_child("ravi", ChildState.MISCONCEPTION),
        _make_child("priya", ChildState.PARTIAL, OLD_ITEM.key()),
        _make_child("aman", ChildState.CORRECT),
    ]
    header = scene_header(_scene(kids))
    assert header is not None
    labels = {c["id"]: c["label"] for c in header["children"]}
    assert labels == {
        "ravi": get_message("ui_strip_stuck_m"),
        "priya": get_message("ui_strip_learning_f"),
        "aman": get_message("ui_strip_got_m"),
    }
    assert [c["name"] for c in header["children"]] == [
        get_message("speaker_ravi"),
        get_message("speaker_priya"),
        get_message("speaker_aman"),
    ]


def test_relapse_marker_on_bug_answer_to_new_problem(strip_on: None, lang: str) -> None:
    ravi = _make_child("ravi", ChildState.PARTIAL, OLD_ITEM.key())
    ravi.last_answer = _bug_answer(NEW_ITEM)
    header = scene_header(_scene([ravi, _make_child("aman")]))
    assert header is not None
    ravi_label = header["children"][0]["label"]
    expected = f"{get_message('ui_strip_stuck_m')} · {get_message('ui_strip_relapse_m')}"
    assert ravi_label == expected  # bundles then relapse: stuck again, never also "getting it"
    assert get_message("ui_strip_learning_m") not in ravi_label
    assert "label" in header["children"][1]
    assert get_message("ui_strip_relapse_m") not in header["children"][1]["label"]


def test_no_relapse_when_correct_or_same_problem(strip_on: None) -> None:
    ravi = _make_child("ravi", ChildState.PARTIAL, OLD_ITEM.key())
    ravi.last_answer = 25  # the right answer for 52 - 17, not a bug answer on the new problem
    assert get_message("ui_strip_relapse_m") not in child_strip_label(ravi, _scene([ravi]))
    same = _make_child("ravi", ChildState.PARTIAL, NEW_ITEM.key())
    same.last_answer = _bug_answer(NEW_ITEM)  # partial_item_key == current item: not a relapse
    assert get_message("ui_strip_relapse_m") not in child_strip_label(same, _scene([same]))
    done = _make_child("ravi", ChildState.CORRECT, OLD_ITEM.key())
    done.last_answer = _bug_answer(NEW_ITEM)
    assert get_message("ui_strip_relapse_m") not in child_strip_label(done, _scene([done]))


def test_one_on_one_header_carries_strip_label_and_relapse(strip_on: None, lang: str) -> None:
    ravi = _make_child("ravi", ChildState.PARTIAL, OLD_ITEM.key())
    ravi.last_answer = _bug_answer(NEW_ITEM)
    header = scene_header(_scene([ravi], one=True))
    assert header is not None
    assert header["title"] == get_message("ui_scene_one_title", child=get_message("speaker_ravi"))
    assert header["strip_label"].endswith(get_message("ui_strip_relapse_m"))
    priya = _make_child("priya", ChildState.CORRECT)
    header = scene_header(_scene([priya], one=True))
    assert header is not None
    assert header["strip_label"] == get_message("ui_strip_got_f")


def test_flag_off_header_has_no_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CHILD_STRIP_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    kids = [_make_child("ravi"), _make_child("priya")]
    header = scene_header(_scene(kids))
    assert header is not None
    assert all("label" not in c for c in header["children"])
    one = scene_header(_scene([_make_child("ravi")], one=True))
    assert one is not None
    assert one["title"] == get_message("ui_scene_one_title", child=get_message("speaker_ravi"))
    assert "strip_label" not in one


def test_flag_on_by_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CHILD_STRIP_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    header = scene_header(_scene([_make_child("ravi"), _make_child("priya")]))
    assert header is not None
    assert all("label" in c for c in header["children"])


def _resp(
    persona: str, kind: ResponseKind, item: Problem, answer: int | None = None
) -> ChildResponse:
    return ChildResponse(
        persona_id=persona,
        kind=kind,
        answer=answer,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="neutral",
        item=item,
    )


def _turn(idx: int, *responses: ChildResponse) -> TurnRecord:
    return TurnRecord(
        turn_index=idx,
        transcript="x",
        acts=[],
        addressed_child=None,
        child_responses=list(responses),
    )


def _told_history(persona: str = "ravi") -> list[TurnRecord]:
    return [
        _turn(1, _resp(persona, ResponseKind.PARROT, OLD_ITEM, 35)),
        _turn(2, _resp(persona, ResponseKind.ANSWER, NEW_ITEM, _bug_answer(NEW_ITEM))),  # type: ignore[arg-type]
    ]


def _stuck_on_new(persona: str = "ravi") -> ChildRuntime:
    child = _make_child(persona)
    child.last_answer = _bug_answer(NEW_ITEM)
    return child


def test_told_answer_then_new_problem_shows_marker(strip_on: None, lang: str) -> None:
    ravi = _stuck_on_new()
    label = child_strip_label(ravi, _scene([ravi]), _told_history())
    assert label == f"{get_message('ui_strip_stuck_m')} · {get_message('ui_strip_relapse_m')}"
    assert get_message("ui_strip_learning_m") not in label
    assert get_message("ui_strip_relapse_m") not in child_strip_label(ravi, _scene([ravi]))
    header = scene_header(_scene([ravi], one=True), True, _told_history())
    assert header is not None
    assert header["strip_label"].endswith(get_message("ui_strip_relapse_m"))


def test_told_answer_then_scaffold_then_correct_shows_got_it(strip_on: None, lang: str) -> None:
    ravi = _make_child("ravi", ChildState.CORRECT, NEW_ITEM.key())
    ravi.last_answer = 16
    history = [
        *_told_history(),
        _turn(3, _resp("ravi", ResponseKind.SCAFFOLDED_CORRECT, NEW_ITEM, 16)),
    ]
    assert child_strip_label(ravi, _scene([ravi]), history) == get_message("ui_strip_got_m")


def test_told_marker_only_for_the_child_who_was_told(strip_on: None) -> None:
    ravi, aman = _stuck_on_new("ravi"), _stuck_on_new("aman")
    header = scene_header(_scene([ravi, aman]), True, _told_history("ravi"))
    assert header is not None
    marker = get_message("ui_strip_relapse_m")
    assert marker in header["children"][0]["label"]
    assert marker not in header["children"][1]["label"]


def test_told_answer_without_a_new_problem_shows_plain_stuck(strip_on: None) -> None:
    ravi = _make_child("ravi")
    ravi.last_answer = 35
    history = [_turn(1, _resp("ravi", ResponseKind.PARROT, NEW_ITEM, 16))]
    assert child_strip_label(ravi, _scene([ravi]), history) == get_message("ui_strip_stuck_m")


def test_told_marker_hidden_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CHILD_STRIP_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    header = scene_header(_scene([_stuck_on_new()], one=True), True, _told_history())
    assert header is not None
    assert "strip_label" not in header
