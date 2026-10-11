"""Unit tests for Devanagari Akshar splitter matching spec/04 §4.2."""

import pytest

from backend.app.rule_engine.bugs.akshar import (
    join_akshars,
    split_akshars,
    strip_matras,
)


@pytest.mark.parametrize(
    ("word", "expected_akshars"),
    [
        ("किताब", ["कि", "ता", "ब"]),
        ("गुड़िया", ["गु", "ड़ि", "या"]),
        ("विद्यालय", ["वि", "द्या", "ल", "य"]),
        ("आम", ["आ", "म"]),
        ("संतरा", ["सं", "त", "रा"]),
        ("मेला", ["मे", "ला"]),
        ("पानी", ["पा", "नी"]),
        ("मछली", ["म", "छ", "ली"]),
        ("पतंग", ["प", "तं", "ग"]),
        ("कमल", ["क", "म", "ल"]),
        ("गमला", ["ग", "म", "ला"]),
        ("बच्चा", ["ब", "च्चा"]),
        ("नमस्ते", ["न", "म", "स्ते"]),
    ],
)
def test_split_akshars_spec_cases(word: str, expected_akshars: list[str]) -> None:
    """Verify exact akshar splits specified in spec/04 §4.2."""
    assert split_akshars(word) == expected_akshars


def test_join_akshars():
    """Verify join_akshars with ' - ' separator for AKSHAR_BY_AKSHAR bug."""
    assert join_akshars(["मे", "ला"]) == "मे - ला"
    assert join_akshars(["पा", "नी"]) == "पा - नी"
    assert join_akshars(["कि", "ता", "ब"]) == "कि - ता - ब"
    assert join_akshars(["गु", "ड़ि", "या"]) == "गु - ड़ि - या"


@pytest.mark.parametrize(
    ("word", "expected_bare"),
    [
        ("मेला", "मल"),
        ("पानी", "पन"),
        ("किताब", "कतब"),
        ("गुड़िया", "गड़य"),
        ("संतरा", "सतर"),
    ],
)
def test_strip_matras(word: str, expected_bare: str) -> None:
    """Verify matra dropping matches table in spec/04 §4.2."""
    assert strip_matras(word) == expected_bare
