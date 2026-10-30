"""Unit tests for all 12 procedural bug rules and paired correct functions.

Exhaustively verifies every cell in the tables of spec/04 §4.2.
"""

import pytest

from backend.app.rule_engine.bugs import (
    BUG_REGISTRY,
    NotApplicable,
    add_carry_forgotten,
    add_carry_wrong_digit,
    add_correct,
    add_no_carry,
    akshar_by_akshar,
    first_akshar_guess,
    matra_drop,
    pv_bundle_as_one,
    pv_concat_spoken,
    pv_correct,
    pv_reversal,
    read_correct,
    sub_borrow_no_decrement,
    sub_correct,
    sub_smaller_from_larger,
    sub_write_zero_when_stuck,
)
from backend.app.rule_engine.domain import Problem


# ---------------------------------------------------------------------------
# Numeracy Subtraction (spec/04 §4.2 table 1)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("a", "b", "expected_correct"),
    [
        (52, 17, 35),
        (43, 27, 16),
        (61, 28, 33),
        (74, 39, 35),
    ],
)
def test_sub_correct(a: int, b: int, expected_correct: int) -> None:
    prob = Problem(type="sub", a=a, b=b)
    res = sub_correct(prob)
    assert res.answer == expected_correct
    assert res.rule_id == "CORRECT_SUB"
    assert len(res.steps) >= 3


@pytest.mark.parametrize(
    ("a", "b", "expected_answer"),
    [
        (52, 17, 45),
        (43, 27, 24),
        (61, 28, 47),
        (74, 39, 45),
    ],
)
def test_sub_smaller_from_larger(a: int, b: int, expected_answer: int) -> None:
    prob = Problem(type="sub", a=a, b=b)
    res = sub_smaller_from_larger(prob)
    assert res.answer == expected_answer
    assert res.rule_id == "SUB_SMALLER_FROM_LARGER"


@pytest.mark.parametrize(
    ("a", "b", "expected_answer"),
    [
        (52, 17, 45),
        (43, 27, 26),
        (61, 28, 43),
        (74, 39, 45),
    ],
)
def test_sub_borrow_no_decrement(a: int, b: int, expected_answer: int) -> None:
    prob = Problem(type="sub", a=a, b=b)
    res = sub_borrow_no_decrement(prob)
    assert res.answer == expected_answer
    assert res.rule_id == "SUB_BORROW_NO_DECREMENT"


@pytest.mark.parametrize(
    ("a", "b", "expected_answer"),
    [
        (52, 17, 40),
        (43, 27, 20),
        (61, 28, 40),
        (74, 39, 40),
    ],
)
def test_sub_write_zero_when_stuck(a: int, b: int, expected_answer: int) -> None:
    prob = Problem(type="sub", a=a, b=b)
    res = sub_write_zero_when_stuck(prob)
    assert res.answer == expected_answer
    assert res.rule_id == "SUB_WRITE_ZERO_WHEN_STUCK"


# ---------------------------------------------------------------------------
# Numeracy Addition (spec/04 §4.2 table 2)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("a", "b", "expected_correct"),
    [
        (38, 45, 83),
        (27, 48, 75),
        (56, 29, 85),
    ],
)
def test_add_correct(a: int, b: int, expected_correct: int) -> None:
    prob = Problem(type="add", a=a, b=b)
    res = add_correct(prob)
    assert res.answer == expected_correct
    assert res.rule_id == "CORRECT_ADD"


@pytest.mark.parametrize(
    ("a", "b", "expected_answer"),
    [
        (38, 45, 713),
        (27, 48, 615),
        (56, 29, 715),
    ],
)
def test_add_no_carry(a: int, b: int, expected_answer: int) -> None:
    prob = Problem(type="add", a=a, b=b)
    res = add_no_carry(prob)
    assert res.answer == expected_answer
    assert res.rule_id == "ADD_NO_CARRY"


@pytest.mark.parametrize(
    ("a", "b", "expected_answer"),
    [
        (38, 45, 73),
        (27, 48, 65),
        (56, 29, 75),
    ],
)
def test_add_carry_forgotten(a: int, b: int, expected_answer: int) -> None:
    prob = Problem(type="add", a=a, b=b)
    res = add_carry_forgotten(prob)
    assert res.answer == expected_answer
    assert res.rule_id == "ADD_CARRY_FORGOTTEN"


@pytest.mark.parametrize(
    ("a", "b", "expected_answer"),
    [
        (38, 45, 101),
        (27, 48, 111),
        (56, 29, 121),
    ],
)
def test_add_carry_wrong_digit(a: int, b: int, expected_answer: int) -> None:
    prob = Problem(type="add", a=a, b=b)
    res = add_carry_wrong_digit(prob)
    assert res.answer == expected_answer
    assert res.rule_id == "ADD_CARRY_WRONG_DIGIT"


# ---------------------------------------------------------------------------
# Place Value (spec/04 §4.2 table 3)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("tens", "ones", "expected_correct"),
    [
        (4, 7, 47),
        (3, 5, 35),
        (6, 2, 62),
    ],
)
def test_pv_correct(tens: int, ones: int, expected_correct: int) -> None:
    prob = Problem(type="place_value", tens=tens, ones=ones)
    res = pv_correct(prob)
    assert res.answer == expected_correct
    assert res.rule_id == "CORRECT_PV"


@pytest.mark.parametrize(
    ("tens", "ones", "expected_answer"),
    [
        (4, 7, 11),
        (3, 5, 8),
        (6, 2, 8),
    ],
)
def test_pv_bundle_as_one(tens: int, ones: int, expected_answer: int) -> None:
    prob = Problem(type="place_value", tens=tens, ones=ones)
    res = pv_bundle_as_one(prob)
    assert res.answer == expected_answer
    assert res.rule_id == "PV_BUNDLE_AS_ONE"


@pytest.mark.parametrize(
    ("tens", "ones", "expected_answer"),
    [
        (4, 7, 407),
        (3, 5, 305),
        (6, 2, 602),
    ],
)
def test_pv_concat_spoken(tens: int, ones: int, expected_answer: int) -> None:
    prob = Problem(type="place_value", tens=tens, ones=ones)
    res = pv_concat_spoken(prob)
    assert res.answer == expected_answer
    assert res.rule_id == "PV_CONCAT_SPOKEN"


@pytest.mark.parametrize(
    ("tens", "ones", "expected_answer"),
    [
        (4, 7, 74),
        (3, 5, 53),
        (6, 2, 26),
    ],
)
def test_pv_reversal(tens: int, ones: int, expected_answer: int) -> None:
    prob = Problem(type="place_value", tens=tens, ones=ones)
    res = pv_reversal(prob)
    assert res.answer == expected_answer
    assert res.rule_id == "PV_REVERSAL"


# ---------------------------------------------------------------------------
# Literacy (spec/04 §4.2 table 4)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "word",
    ["मेला", "पानी", "किताब", "गुड़िया"],
)
def test_read_correct(word: str) -> None:
    prob = Problem(type="read_word", word=word)
    res = read_correct(prob)
    assert res.answer == word
    assert res.rule_id == "CORRECT_READ"


@pytest.mark.parametrize(
    ("word", "expected_bare"),
    [
        ("मेला", "मल"),
        ("पानी", "पन"),
        ("किताब", "कतब"),
        ("गुड़िया", "गड़य"),
    ],
)
def test_matra_drop(word: str, expected_bare: str) -> None:
    prob = Problem(type="read_word", word=word)
    res = matra_drop(prob)
    assert res.answer == expected_bare
    assert res.rule_id == "MATRA_DROP"


@pytest.mark.parametrize(
    ("word", "expected_guess"),
    [
        ("मेला", "मछली"),
        ("पानी", "पतंग"),
        ("किताब", "कमल"),
        ("गुड़िया", "गमला"),
    ],
)
def test_first_akshar_guess(word: str, expected_guess: str) -> None:
    prob = Problem(type="read_word", word=word)
    res = first_akshar_guess(prob)
    assert res.answer == expected_guess
    assert res.rule_id == "FIRST_AKSHAR_GUESS"


@pytest.mark.parametrize(
    ("word", "expected_joined"),
    [
        ("मेला", "मे - ला"),
        ("पानी", "पा - नी"),
        ("किताब", "कि - ता - ब"),
        ("गुड़िया", "गु - ड़ि - या"),
    ],
)
def test_akshar_by_akshar(word: str, expected_joined: str) -> None:
    prob = Problem(type="read_word", word=word)
    res = akshar_by_akshar(prob)
    assert res.answer == expected_joined
    assert res.rule_id == "AKSHAR_BY_AKSHAR"


# ---------------------------------------------------------------------------
# Registry and NotApplicable tests
# ---------------------------------------------------------------------------
def test_registry_size_and_metadata() -> None:
    """Exactly 12 procedural bug rules must be registered with complete metadata."""
    # the two Track B scene rules (CMP_ONES_FIRST, LETTER_NAME_FOR_SOUND) sit beside the original 12
    track_b = {"CMP_ONES_FIRST", "LETTER_NAME_FOR_SOUND"}
    assert len(set(BUG_REGISTRY) - track_b) == 12
    expected_ids = {
        "SUB_SMALLER_FROM_LARGER",
        "SUB_BORROW_NO_DECREMENT",
        "SUB_WRITE_ZERO_WHEN_STUCK",
        "ADD_NO_CARRY",
        "ADD_CARRY_FORGOTTEN",
        "ADD_CARRY_WRONG_DIGIT",
        "PV_BUNDLE_AS_ONE",
        "PV_CONCAT_SPOKEN",
        "PV_REVERSAL",
        "MATRA_DROP",
        "FIRST_AKSHAR_GUESS",
        "AKSHAR_BY_AKSHAR",
    }
    assert set(BUG_REGISTRY.keys()) - track_b == expected_ids
    for rule_id, info in BUG_REGISTRY.items():
        assert info.rule_id == rule_id
        assert callable(info.fn)
        assert callable(info.correct_fn)
        assert info.description_hi
        assert info.research_ref
        assert len(info.problem_types) >= 1


def test_not_applicable_exceptions() -> None:
    """Rules raise NotApplicable for mismatched problem types."""
    sub_prob = Problem(type="sub", a=52, b=17)
    add_prob = Problem(type="add", a=38, b=45)
    pv_prob = Problem(type="place_value", tens=4, ones=7)
    word_prob = Problem(type="read_word", word="मेला")

    with pytest.raises(NotApplicable):
        sub_smaller_from_larger(add_prob)
    with pytest.raises(NotApplicable):
        add_no_carry(sub_prob)
    with pytest.raises(NotApplicable):
        pv_bundle_as_one(word_prob)
    with pytest.raises(NotApplicable):
        matra_drop(pv_prob)


def test_no_regroup_needed_subtraction() -> None:
    """When sub bug does not manifest (no regrouping needed), returns correct answer."""
    # 58 - 12: 8 > 2, 5 > 1 -> 46
    prob = Problem(type="sub", a=58, b=12)
    res = sub_smaller_from_larger(prob)
    assert res.answer == 46
