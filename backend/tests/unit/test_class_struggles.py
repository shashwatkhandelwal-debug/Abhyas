"""The closed class-struggle library (content/class_struggles.yaml) and its keyword matcher."""

from __future__ import annotations

import unicodedata

import pytest

from backend.app.class_profile.library import (
    ClassStruggle,
    citations,
    load_library,
    validate_library,
)
from backend.app.class_profile.matcher import clip_input, match_struggles
from backend.app.config import settings
from backend.app.sessions.path import load_all_move_cards

LIB = load_library()


def _moves() -> dict[str, set[str]]:
    return {c.id: set(c.misconceptions) | set(c.target_causes) for c in load_all_move_cards()}


def test_library_validates_against_moves_misconceptions_and_chunks() -> None:
    assert validate_library(LIB, _moves()) == []


def test_library_is_small_and_has_the_chips() -> None:
    assert 10 <= len(LIB.struggles) <= settings.STRUGGLE_LIBRARY_MAX
    assert settings.STRUGGLE_CHIPS_MIN <= len(LIB.chips()) <= settings.STRUGGLE_CHIPS_MAX
    assert len({s.id for s in LIB.struggles}) == len(LIB.struggles)


def test_validation_catches_unknown_ids() -> None:
    bad = LIB.model_copy(deep=True)
    bad.struggles[0] = bad.struggles[0].model_copy(update={"chunk_ids": ["nope:p001:001"]})
    bad.struggles[4] = bad.struggles[4].model_copy(
        update={"move_id": "NO_SUCH_MOVE", "misconception_ids": ["NO_SUCH"]}
    )
    errors = validate_library(bad, _moves())
    assert any("unknown chunk id" in e for e in errors)
    assert any("unknown move_id" in e for e in errors)


def test_validation_catches_misconception_from_another_move() -> None:
    bad = LIB.model_copy(deep=True)
    carry = next(i for i, s in enumerate(bad.struggles) if s.id == "NUM_ADD_CARRY")
    bad.struggles[carry] = bad.struggles[carry].model_copy(
        update={"misconception_ids": ["PV_REVERSAL"]}
    )
    assert any("is not in move" in e for e in validate_library(bad, _moves()))


def test_every_entry_is_complete_and_nfc() -> None:
    for s in [*LIB.struggles]:
        assert 2 <= len(s.triggers_hi) <= 3
        assert 1 <= len(s.chunk_ids) <= 2
        assert s.tip_hi and s.tip_en and s.label_hi and s.label_en
        for text in [s.label_hi, s.tip_hi, *s.triggers_hi, *s.keywords]:
            assert unicodedata.is_normalized("NFC", text)
        assert len(citations(s.chunk_ids)) == len(s.chunk_ids)


def test_four_moves_are_all_reachable_and_the_rest_say_no_practice_case() -> None:
    with_move = {s.move_id for s in LIB.struggles if s.move_id}
    assert with_move == set(_moves())
    assert any(not s.has_practice for s in LIB.struggles)


@pytest.mark.parametrize("entry", LIB.struggles, ids=lambda s: s.id)
def test_each_trigger_phrase_finds_its_own_entry_first(entry: ClassStruggle) -> None:
    for phrase in entry.triggers_hi:
        matches = match_struggles(phrase)
        assert matches, phrase
        assert matches[0].struggle_id == entry.id, (phrase, matches)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("हासिल भूल जाते हैं बच्चे", ["NUM_ADD_CARRY"]),
        ("carry bhool jate hain", ["NUM_ADD_CARRY"]),
        ("बच्चे घटाव में बंडल खोलना नहीं जानते", ["NUM_SUB_REGROUP"]),
        ("bacche matra wale shabd nahi padh paate", ["LIT_MATRA_DROP"]),
        ("बच्चे पढ़ तो लेते हैं पर समझते नहीं", ["LIT_COMPREHENSION"]),
        ("मेरे बच्चे मात्रा छोड़ देते हैं और अटक अटक कर पढ़ते हैं", ["LIT_MATRA_DROP", "LIT_AKSHAR_BY_AKSHAR"]),
    ],
)
def test_real_sentences(text: str, expected: list[str]) -> None:
    got = [m.struggle_id for m in match_struggles(text)]
    assert got[: len(expected)] == expected


def test_nothing_in_the_library_is_not_matched() -> None:
    for text in ["", "   ", "कुछ नहीं पता", "मौसम बहुत अच्छा है", "hello"]:
        assert match_struggles(text) == []


def test_matcher_caps_at_max_chosen_and_orders_best_first() -> None:
    text = "गिनती में गलती करते हैं, हासिल भूल जाते हैं, मात्रा छोड़कर पढ़ते हैं, वर्तनी भी कमज़ोर है"
    matches = match_struggles(text)
    assert len(matches) == settings.STRUGGLE_MAX_CHOSEN
    scores = [m.score for m in matches]
    assert scores == sorted(scores, reverse=True)
    positions = [m.first_position for m in matches if m.score == scores[0]]
    assert positions == sorted(positions)


def test_matcher_is_nfc_insensitive() -> None:
    decomposed = unicodedata.normalize("NFD", "बच्चे ज़्यादा-कम में उलझते हैं")
    assert [m.struggle_id for m in match_struggles(decomposed)] == ["NUM_COMPARE"]


def test_long_input_is_clipped() -> None:
    assert len(clip_input("क" * 5000)) == settings.STRUGGLE_INPUT_MAX_CHARS


def test_citation_label_names_source_and_page() -> None:
    cite = citations(["nipun_guidelines_2021:p088:082"])[0]
    assert cite.page == 86
    assert "पृ. 86" in cite.label_hi()
