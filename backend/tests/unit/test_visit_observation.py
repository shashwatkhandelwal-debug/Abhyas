"""The ARP class-visit checklist form: only closed lists get through (no database needed)."""

from __future__ import annotations

import pytest

from backend.app.config import settings, v2_enabled
from backend.app.core.messages import get_message
from backend.app.web import visit_observation as vo

DASHES = ("—", "–")


def test_a_valid_form_is_parsed() -> None:
    parsed = vo.parse_form(["named_child", "think_time"], "ask_why", "1")
    assert parsed.talk_moves == ("named_child", "think_time")
    assert parsed.next_step == "ask_why" and parsed.practice_seen is True


def test_no_talk_move_ticked_is_allowed_but_a_next_step_is_required() -> None:
    assert vo.parse_form([], "repeat", None).talk_moves == ()
    with pytest.raises(vo.VisitFormError):
        vo.parse_form(["named_child"], None, None)


@pytest.mark.parametrize("bad", ["", "free text", "ASK_WHY", "ask_why; drop table"])
def test_a_next_step_outside_the_list_is_rejected(bad: str) -> None:
    with pytest.raises(vo.VisitFormError):
        vo.parse_form([], bad, None)


@pytest.mark.parametrize("bad", ["", "invented_move", "named_child "])
def test_a_talk_move_outside_the_list_is_rejected(bad: str) -> None:
    with pytest.raises(vo.VisitFormError):
        vo.parse_form(["named_child", bad], "repeat", None)


def test_a_move_ticked_twice_counts_once() -> None:
    assert vo.parse_form(["why_how", "why_how"], "repeat", None).talk_moves == ("why_how",)


def test_practice_seen_is_only_true_for_the_one_value() -> None:
    assert vo.parse_form([], "repeat", "0").practice_seen is False
    assert vo.parse_form([], "repeat", "yes").practice_seen is False


def test_the_closed_lists_are_the_four_talk_moves_and_five_next_steps() -> None:
    assert settings.OBSERVATION_TALK_MOVES == ("named_child", "why_how", "not_told", "think_time")
    assert len(settings.OBSERVATION_NEXT_STEPS) == 5


@pytest.mark.parametrize("lang", ["hi", "en"])
def test_every_label_exists_in_both_languages_without_dashes(lang: str) -> None:
    keys = [f"ui_visit_talk_{m}" for m in settings.OBSERVATION_TALK_MOVES]
    keys += [f"ui_visit_next_{n}" for n in settings.OBSERVATION_NEXT_STEPS]
    keys += ["ui_visit_title", "ui_visit_desc", "ui_visit_open", "ui_visit_talk_head"]
    keys += ["ui_visit_practice_head", "ui_visit_practice_seen", "ui_visit_practice_none"]
    keys += ["ui_visit_next_head", "ui_visit_save", "ui_visit_saved", "ui_visit_none"]
    keys += ["ui_rvo_title", "ui_rvo_caption", "ui_rvo_none", "ui_rvo_few", "ui_rvo_row"]
    keys += ["ui_rvo_reported", "ui_rvo_observed", "ui_rvo_observed_hidden"]
    keys += ["ui_rvo_demo_all", "ui_rvo_demo_some"]
    for key in keys:
        text = get_message(key, lang=lang)
        assert text and not any(d in text for d in DASHES), key


def test_the_caption_says_these_are_not_learning_outcomes() -> None:
    assert "not learning outcomes" in get_message("ui_rvo_caption", lang="en")
    assert "सीखने के नतीजे नहीं" in get_message("ui_rvo_caption", lang="hi")


def test_flag_pattern_on_in_demo_mode_off_otherwise(monkeypatch: pytest.MonkeyPatch) -> None:
    assert settings.model_fields["OBSERVATION_ENABLED"].default is False
    monkeypatch.setattr(settings, "OBSERVATION_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    assert vo.enabled() and v2_enabled(False)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    assert not vo.enabled()
