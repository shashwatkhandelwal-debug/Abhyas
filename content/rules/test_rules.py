"""Unit tests for content error rules."""

from content.rules.math_bugs import bug_add_no_carry, bug_sub_smaller_from_larger
from content.rules.reading_bugs import bug_matra_drop


def test_sub_smaller_from_larger():
    res = bug_sub_smaller_from_larger(52, 17)
    assert res["answer"] == 45
    assert 45 in res["tokens"]


def test_add_no_carry():
    res = bug_add_no_carry(28, 15)
    assert res["answer"] == 313
    assert 313 in res["tokens"]


def test_matra_drop():
    res = bug_matra_drop("किताब")
    assert res["answer"] == "कतब"
