"""The model-practice speaker label follows the teacher's address form (neutral unless feminine)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.web.teacher import chat_ui_strings
from backend.app.web.ui_lang import speaker_label

TEMPLATE = Path(__file__).resolve().parents[2] / "app" / "web" / "templates" / "teacher.html"


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest) -> str:
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


def test_feminine_keeps_the_current_wording(lang: str) -> None:
    expected = "आदर्श शिक्षिका" if lang == "hi" else "Model teacher"
    assert speaker_label("model_teacher", "f") == expected
    assert chat_ui_strings("f")["speaker_model_teacher"] == expected


@pytest.mark.parametrize("form", ["m", None, ""])
def test_masculine_or_unset_gets_the_neutral_label(lang: str, form: str | None) -> None:
    label = speaker_label("model_teacher", form)
    assert label == get_message("speaker_model_teacher_neutral")
    assert chat_ui_strings(form)["speaker_model_teacher"] == label
    if lang == "hi":
        assert label == "आदर्श शिक्षण"
        assert "शिक्षिका" not in label


def test_other_speakers_are_unchanged(lang: str) -> None:
    for speaker in ("coach", "abhyas", "ravi"):
        assert speaker_label(speaker, "m") == speaker_label(speaker, "f")


def test_template_passes_the_address_form() -> None:
    assert "speaker_label(msg.speaker, address_form)" in TEMPLATE.read_text(encoding="utf-8")
