"""fix4: a first-person how-to question goes to the Guide from any step, not to "did not understand"."""

import pytest

from backend.app.core.intents import Intent, match_intent

QUESTIONS = [
    "What should I do if a child cannot add numbers with carry?",
    "How do I teach matras to a slow reader?",
    "बच्चा हासिल वाला जोड़ नहीं कर पाता, मैं क्या करूँ?",
    "मैं बच्चों को घटाव कैसे सिखाऊँ",
    "Can I use stones instead of sticks?",
]
NOT_QUESTIONS = [
    "तुमने कैसे किया? एक-एक कदम बताओ।",  # a line to a child
    "Ravi, how did you get 45?",
    "देखो, ये बंडल हैं, इन्हें गिनो",
    "ठीक है",
]


@pytest.mark.parametrize("text", QUESTIONS)
def test_how_to_questions_reach_the_guide_at_any_step(text: str) -> None:
    assert match_intent(text, ask_anywhere=True) == Intent.ASK


@pytest.mark.parametrize("text", QUESTIONS)
def test_without_the_flag_they_are_left_alone(text: str) -> None:
    assert match_intent(text) is None


@pytest.mark.parametrize("text", NOT_QUESTIONS)
def test_lines_to_a_child_and_plain_replies_are_not_questions_to_the_app(text: str) -> None:
    assert match_intent(text, ask_anywhere=True) != Intent.ASK
