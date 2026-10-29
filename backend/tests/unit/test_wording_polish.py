"""Wording that lives in our own yaml, not in chunk summaries from the source documents."""

from __future__ import annotations

from pathlib import Path

CONTENT = Path(__file__).resolve().parents[3] / "content"
OWN_FILES = ["class_struggles.yaml", "level_sorter.yaml", "messages_hi.yaml"]


def test_own_strings_avoid_the_rejected_words() -> None:
    for name in OWN_FILES:
        text = (CONTENT / name).read_text(encoding="utf-8")
        assert "रिमीडियल" not in text, name
        assert "छुआएँ" not in text, name


def test_counting_tip_ends_with_an_imperative() -> None:
    from backend.app.class_profile.library import load_library

    struggle = load_library().get("NUM_COUNTING")
    assert struggle is not None
    assert "छूकर" in struggle.tip_hi
    assert struggle.tip_hi.endswith("एक ही संख्या बोलें।")
