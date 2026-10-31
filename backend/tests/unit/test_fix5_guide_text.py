"""fix5: no invisible gap in a Guide reply; source chips meet WCAG AA on the dark theme."""

from __future__ import annotations

import re
from pathlib import Path

from backend.app.core.outbound_text import tidy_blank_lines


def test_empty_bullets_and_invisible_lines_do_not_make_a_gap() -> None:
    text = "• एक\n• दो\n•\n​\n   \n-\n\nइस हफ्ते आज़माएँ: कुछ करें"
    assert tidy_blank_lines(text) == "• एक\n• दो\n\nइस हफ्ते आज़माएँ: कुछ करें"


def test_real_bullets_survive() -> None:
    assert tidy_blank_lines("- एक\n- दो") == "- एक\n- दो"


def _lum(hex_: str) -> float:
    c = [int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_dark_source_chip_contrast_is_at_least_aa() -> None:
    css = (Path(__file__).parents[2] / "app/web/static/app.css").read_text(encoding="utf-8")
    dark = re.search(r"prefers-color-scheme: dark\) \{ \.source-chip \{ color: (#\w+)", css)
    assert dark
    assert _ratio(dark.group(1), "#1E2421") >= 4.5  # chip text on the dark surface
    assert _ratio(dark.group(1), "#194D40") >= 4.5  # and on the dark bubble
