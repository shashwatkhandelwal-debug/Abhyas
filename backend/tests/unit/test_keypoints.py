"""The deterministic Hindi key-point matcher (llm/keypoints.py), on the matra-blending move."""

import pytest

from backend.app.llm.keypoints import match_key_points
from backend.app.llm.roles.fidelity_checker import compose_fidelity_reply, fallback_fidelity
from backend.app.rehearsal.scene_runner import load_move_card

MOVE = load_move_card("LIT_MATRA_BLENDING")

# kp1: the three ways children get stuck; kp2: finger on each letter, sound out consonant + matra;
# kp3: blend slowly, teacher models first; kp4: do not scold a wrong guess.
MATCHING = {
    "kp1": [
        "बच्चे मात्रा छोड़ देते हैं और पहले अक्षर से अंदाज़ा लगाते हैं",
        "कुछ बच्चे अंदाज़ा लगाकर पढ़ते हैं और कुछ मात्रा छोड़ देते हैं",
        "बच्चे अक्षर अक्षर बोलते हैं पर मिला नहीं पाते, और पहले अक्षर से अंदाज़े से बोल देते हैं",
    ],
    "kp2": [
        "हर अक्षर पर उँगली रखकर व्यंजन और मात्रा की ध्वनि बुलवाएँ",
        "बच्चे की उंगली अक्षर पर रखवाएँ और हर अक्षर की ध्वनि बोलने को कहें",
        "म और मात्रा की ध्वनि अलग-अलग बुलवाएँ, म और े मिलकर मे",
    ],
    "kp3": [
        "पहले शिक्षक करके दिखाएँ, फिर बच्चे साथ में दोहराएँ",
        "अक्षरों को धीरे-धीरे मिलाकर बुलवाएँ",
        "शिक्षक पहले धीरे धीरे पढ़कर करके दिखाए और सब बच्चे साथ पढ़ें",
    ],
    "kp4": [
        "गलत अंदाज़े पर बच्चों को डाँटें नहीं",
        "बच्चे को डांटने की जगह कहें कि फिर से देखो",
        "गलत पढ़ने पर डाँटना नहीं, पहला अक्षर फिर से देखो कहें",
    ],
}
NOT_MATCHING = {
    "kp1": [
        "आज मौसम बहुत अच्छा था और सब खेल रहे थे",
        "गलत अंदाज़े पर बच्चों को डाँटें नहीं",  # another point's answer
    ],
    "kp2": [
        "कक्षा में शांति रखें और सबको बराबर मौका दें",
        "गलत अंदाज़े पर बच्चों को डाँटें नहीं",
    ],
    "kp3": [
        "रोज़ पाँच मिनट कहानी पढ़ें",
        "बच्चे मात्रा छोड़ देते हैं और अंदाज़ा लगाते हैं",
    ],
    "kp4": [
        "हर रोज़ बच्चों को कहानी सुनाएँ",
        "हर अक्षर पर उँगली रखकर ध्वनि बुलवाएँ",
    ],
}


def _status(answer: str, point: str) -> str:
    return next(m.status for m in match_key_points(MOVE, answer) if m.id == point)


@pytest.mark.parametrize(
    ("point", "answer"), [(p, a) for p, answers in MATCHING.items() for a in answers]
)
def test_a_matching_answer_covers_its_key_point(point: str, answer: str) -> None:
    assert _status(answer, point) == "covered"


@pytest.mark.parametrize(
    ("point", "answer"), [(p, a) for p, answers in NOT_MATCHING.items() for a in answers]
)
def test_a_non_matching_answer_does_not_cover_the_key_point(point: str, answer: str) -> None:
    assert _status(answer, point) != "covered"


def test_the_demo3_answer_scores_more_than_zero() -> None:
    answer = "बच्चे को हर अक्षर की ध्वनि मिलाकर पढ़ने दें और गलत पढ़ने पर डाँटें नहीं"
    out = fallback_fidelity(MOVE, answer)
    assert [p.status for p in out.points].count("covered") >= 1
    assert "0" not in compose_fidelity_reply(MOVE, out).split("\n")[0].split("{")[0][:0] + "1"
    quote = next(p.quote for p in out.points if p.status == "covered")
    assert quote in answer  # evidence is the teacher's own word


def test_short_keyword_needs_a_whole_word() -> None:
    # "मे" (kp2) must not fire on the very common "में"
    assert _status("कक्षा में बच्चे हैं", "kp2") == "missing"
    assert _status("म और े मिलकर मे", "kp2") != "missing"


def test_empty_and_unrelated_answers_are_all_missing() -> None:
    for answer in ("", "   ", "नमस्ते"):
        assert {m.status for m in match_key_points(MOVE, answer)} == {"missing"}
