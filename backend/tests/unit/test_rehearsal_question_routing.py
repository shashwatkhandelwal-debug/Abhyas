"""During a rehearsal, a how-to question to the app goes to the guide, not to the children."""

import pytest

from backend.app.core.intents import Intent, is_pedagogy_question_for_app, match_intent

APP_QUESTIONS = [
    # the exact production message that Ravi wrongly answered
    "दो अलग ... बच्चे साथ बैठते हैं। हासिल वाला घटाव दोनों को एक साथ कैसे कराऊँ?",
    "रवि को कैसे समझाऊँ?",
    "मैं हासिल वाला घटाव कैसे सिखाऊँ",
    "Ravi ko subtraction kaise samjhaun?",
    "mixed level bacchon ko ek saath kaise padhaun",
    "How do I teach regrouping to two kids together?",
]

TEACHING_TURNS = [
    "रवि, तुमने 43 में से 27 कैसे घटाया?",
    "रवि से तरीका पूछें",
    "तुमने कैसे किया? मुझे समझाओ",
    "बंडल खोलकर दिखाओ, कैसे बना 43?",
    "प्रिया, तुम बताओ यह कैसे होगा?",
    "Ravi, tumne kaise kiya?",
    "How did you get 24?",
    "अब तीलियाँ गिनो और बताओ।",
    "मैं बंडल दिखाती हूँ, तुम गिनो",
    "बस",
]


@pytest.mark.parametrize("text", APP_QUESTIONS)
def test_app_question_routes_to_ask_in_rehearsal(text: str) -> None:
    assert match_intent(text, in_rehearsal=True) == Intent.ASK
    assert is_pedagogy_question_for_app(text)


@pytest.mark.parametrize("text", APP_QUESTIONS)
def test_app_question_outside_rehearsal_is_untouched(text: str) -> None:
    assert match_intent(text, in_rehearsal=False) is None


@pytest.mark.parametrize("text", TEACHING_TURNS)
def test_teaching_turns_stay_in_the_scene(text: str) -> None:
    assert match_intent(text, in_rehearsal=True) != Intent.ASK
    assert not is_pedagogy_question_for_app(text)
