"""Unit tests for Devanagari digits and Hindi numbers (spec/05 §5.10, spec/14 T05).

Acceptance criteria:
- Exhaustive 0-100 word tests (every single integer 0..100)
- to_words 0-199
- extract_numbers on Arabic, Devanagari, Hindi words, and Roman Hinglish
"""

import pytest

from backend.app.llm.guards import norm, substring_match
from backend.app.llm.hindi_numbers import (
    HINDI_NUMBER_WORDS_0_TO_100,
    extract_numbers,
    to_words,
)


@pytest.mark.parametrize("n", list(range(101)))
def test_exhaustive_0_to_100_to_words(n: int) -> None:
    """Every single number from 0 to 100 must have a non-empty canonical Hindi word."""
    word = to_words(n)
    assert isinstance(word, str)
    assert len(word) > 0
    assert word == HINDI_NUMBER_WORDS_0_TO_100[n]


@pytest.mark.parametrize("n", list(range(101)))
def test_exhaustive_0_to_100_extract_numbers(n: int) -> None:
    """Every single canonical Hindi word from 0 to 100 must be extracted back to its integer."""
    word = to_words(n)
    extracted = extract_numbers(f"बच्चे ने {word} बोला")
    assert n in extracted


@pytest.mark.parametrize(
    ("n", "expected_words"),
    [
        (101, "एक सौ एक"),
        (105, "एक सौ पाँच"),
        (115, "एक सौ पंद्रह"),
        (120, "एक सौ बीस"),
        (135, "एक सौ पैंतीस"),
        (145, "एक सौ पैंतालीस"),
        (150, "एक सौ पचास"),
        (175, "एक सौ पचहत्तर"),
        (199, "एक सौ निन्यानवे"),
    ],
)
def test_to_words_101_to_199(n: int, expected_words: str) -> None:
    """Verify numbers 101 to 199 conversion to Hindi words."""
    assert to_words(n) == expected_words


def test_to_words_bounds() -> None:
    """Verify boundary checks for to_words (0 to 199)."""
    with pytest.raises(ValueError):
        to_words(-1)
    with pytest.raises(ValueError):
        to_words(200)


def test_extract_numbers_arabic_and_devanagari() -> None:
    """Verify Arabic and Devanagari digits."""
    text_arabic = "52 mein se 17 ghataya to 45 aaya"
    assert extract_numbers(text_arabic) == [52, 17, 45]

    text_deva = "५२ में से १७ घटाया तो ४५ आया"
    assert extract_numbers(text_deva) == [52, 17, 45]


def test_extract_numbers_hindi_words_and_variants() -> None:
    """Verify Hindi words with spelling variants."""
    text = "बावन में से सत्रह घटाया तो पैंतालीस आया"
    assert extract_numbers(text) == [52, 17, 45]

    # Variants: पांच (5), छः (6), पन्द्रह (15)
    assert extract_numbers("पांच और छः मिलाकर ग्यारह") == [5, 6, 11]
    assert extract_numbers("पन्द्रह तीलियाँ") == [15]


def test_extract_numbers_roman_hinglish() -> None:
    """Verify Romanized numbers used in transcripts and chat."""
    assert extract_numbers("paintalis aaya") == [45]
    assert extract_numbers("paintees bache") == [35]
    assert extract_numbers("baawan minus satrah") == [52, 17]


def test_guards_norm() -> None:
    """Verify spec/05 §5.10 text normalization."""
    # NFC, lowercase, Devanagari digits to Arabic, punctuation stripped, whitespace collapsed
    raw = "  ५२ में से  १७ घटाया, तो ४५ आया!  "
    expected = "52 में से 17 घटाया तो 45 आया"
    assert norm(raw) == expected

    # ZWJ/ZWNJ removal
    raw_zwj = "क\u200cख\u200dग"
    assert norm(raw_zwj) == "कखग"


def test_guards_substring_match() -> None:
    """Verify substring and fuzzy quote matching."""
    source = "रवि, 52 में से 17 कैसे घटाया? समझाओ।"
    quote = "52 में से 17 कैसे घटाया"
    assert substring_match(quote, source)
    # With minor typo or extra word in Devanagari:
    typo_quote = "52 में से 17 कैसे घटाया जी"
    assert substring_match(typo_quote, source)
    assert not substring_match("पूरी तरह से अलग बात", source)
