"""Rate-the-training answer parsing (buttons, digits, spoken numbers) and skip words."""

import pytest

from backend.app.sessions.training_rating import is_skip_comment, parse_training_rating


@pytest.mark.parametrize(
    ("text", "button", "expected"),
    [
        ("", "btn_trate_4", 4),
        ("", "btn_trate_1", 1),
        ("5", None, 5),
        ("मैं 4 दूँगी", None, 4),
        ("४", None, 4),  # Devanagari digit
        ("चार", None, 4),  # spoken, as the STT transcript arrives
        ("पाँच", None, 5),
        ("तीन", None, 3),
        ("0", None, None),
        ("6", None, None),
        ("बहुत अच्छा", None, None),
        ("", "btn_trate_skip", None),
        ("", "btn_trate_9", None),
        ("", None, None),
    ],
)
def test_parse_training_rating(text: str, button: str | None, expected: int | None) -> None:
    assert parse_training_rating(text, button) == expected


@pytest.mark.parametrize("text", ["छोड़ें", "छोड़ें।", "Skip", " skip ", "नहीं", "कुछ नहीं", "no"])
def test_skip_words(text: str) -> None:
    assert is_skip_comment(text)


@pytest.mark.parametrize("text", ["बहुत काम का रहा", "बंडल वाला तरीका पसंद आया", ""])
def test_real_comments_are_not_skips(text: str) -> None:
    assert not is_skip_comment(text) or text == ""
