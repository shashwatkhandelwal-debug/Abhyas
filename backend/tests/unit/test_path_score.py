"""Tests for deterministic move-path scoring (spec/08 §8.5, T23)."""

import pytest

from backend.app.sessions.path_score import (
    MoveFacts,
    TeacherFacts,
    month_number,
    month_rank,
    rank_moves,
    score_move,
)


def move(
    move_id: str,
    domain: str = "numeracy",
    month: str | None = "October",
    acts: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
) -> MoveFacts:
    return MoveFacts(move_id, domain, month, frozenset(acts), frozenset(tags))


def test_month_parsing_and_rank() -> None:
    assert month_number("September") == 9
    assert month_number(" october ") == 10
    assert month_number("Smarch") is None and month_number(None) is None
    assert month_rank("October", 10) == 0
    assert month_rank("November", 10) == 1
    assert month_rank("September", 10) == 0  # past month is due now
    assert month_rank(None, 10) == 11
    with pytest.raises(ValueError):
        month_rank("October", 13)


def test_base_score_is_month_rank_times_ten() -> None:
    teacher = TeacherFacts(current_month=10)
    assert score_move(move("A", month="October"), teacher) == (0, ("month_rank=0",))
    assert score_move(move("B", month="December"), teacher)[0] == 20


def test_tell_answer_bonus_needs_ask_to_explain() -> None:
    teacher = TeacherFacts(current_month=10, placement_used_tell_answer=True)
    assert score_move(move("A", acts=("ask_to_explain",)), teacher)[0] == -15
    assert score_move(move("B", acts=("model_step_aloud",)), teacher)[0] == 0
    assert score_move(move("C", acts=("ask_to_explain",)), TeacherFacts(current_month=10))[0] == 0


def test_class_one_bonus_for_literacy_or_place_value_only() -> None:
    teacher = TeacherFacts(current_month=10, classes=(1, 2))
    assert score_move(move("LIT_X", domain="literacy"), teacher)[0] == -10
    assert score_move(move("NUM_PLACE_VALUE_BUNDLES"), teacher)[0] == -10
    assert score_move(move("NUM_SUB_REGROUP_BUNDLES"), teacher)[0] == 0
    assert (
        score_move(move("LIT_X", domain="literacy"), TeacherFacts(current_month=10, classes=(2,)))[
            0
        ]
        == 0
    )


def test_weak_rubric_only_applies_to_done_moves() -> None:
    weak = TeacherFacts(current_month=10, done_evidence={"A": 1}, min_rubric={"A": 0})
    assert score_move(move("A"), weak)[0] == -10  # 5 * (2 - 0)
    mid = TeacherFacts(current_month=10, done_evidence={"A": 1}, min_rubric={"A": 1})
    assert score_move(move("A"), mid)[0] == -5
    strong = TeacherFacts(current_month=10, done_evidence={"A": 1}, min_rubric={"A": 2})
    assert score_move(move("A"), strong)[0] == 0
    not_done = TeacherFacts(current_month=10, min_rubric={"A": 0})
    assert score_move(move("A"), not_done)[0] == 0


def test_question_tag_bonus_and_done_penalty() -> None:
    teacher = TeacherFacts(
        current_month=10, question_tags=frozenset({"subtraction"}), done_evidence={"B": 2}
    )
    assert score_move(move("A", tags=("subtraction",)), teacher)[0] == -8
    score, reasons = score_move(move("B"), teacher)
    assert score == 100 and "already_done" in reasons
    low = TeacherFacts(current_month=10, done_evidence={"B": 1})
    assert score_move(move("B"), low)[0] == 0  # evidence 1 is not "done enough"


def test_worked_example_ordering() -> None:
    moves = [
        move("NUM_PLACE_VALUE_BUNDLES", acts=("ask_to_explain",), tags=("place_value",)),
        move("NUM_SUB_REGROUP_BUNDLES", month="October", acts=("ask_to_explain",)),
        move("NUM_ADD_CARRY_BUNDLES", month="November"),
        move("LIT_MATRA_BLENDING", domain="literacy", month="November"),
    ]
    teacher = TeacherFacts(
        current_month=10,
        classes=(1,),
        placement_used_tell_answer=True,
        done_evidence={"NUM_PLACE_VALUE_BUNDLES": 2},
    )
    path = rank_moves(moves, teacher)
    assert [e.move_id for e in path] == [
        "NUM_SUB_REGROUP_BUNDLES",  # 0 - 15
        "LIT_MATRA_BLENDING",  # 10 - 10
        "NUM_ADD_CARRY_BUNDLES",  # 10
        "NUM_PLACE_VALUE_BUNDLES",  # 0 - 15 - 10 + 100
    ]
    assert [e.position for e in path] == [1, 2, 3, 4]


def test_ties_break_by_month_then_id_and_are_deterministic() -> None:
    moves = [move("B_MOVE", month="October"), move("A_MOVE", month="October")]
    teacher = TeacherFacts(current_month=10)
    first = rank_moves(moves, teacher)
    assert [e.move_id for e in first] == ["A_MOVE", "B_MOVE"]
    assert first == rank_moves(list(reversed(moves)), teacher)


def test_fixed_order_pins_first_year_moves_and_skips_unknown_ids() -> None:
    moves = [move("A", month="October"), move("B", month="November"), move("C", month="December")]
    path = rank_moves(moves, TeacherFacts(current_month=10), fixed_order=["C", "MISSING", "B", "C"])
    assert [e.move_id for e in path] == ["C", "B", "A"]
    assert path[0].reasons[0] == "first_year_induction_order"
    assert "first_year_induction_order" not in path[2].reasons


def test_exclude_removes_moves() -> None:
    path = rank_moves([move("A"), move("B")], TeacherFacts(current_month=10), exclude=["A"])
    assert [e.move_id for e in path] == ["B"]
