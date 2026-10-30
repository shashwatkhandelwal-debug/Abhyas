"""fix3 K4: the handbook tip and excerpt shown with a move are on topic, not about the home, and
never a feminine verb to a male teacher."""

from __future__ import annotations

import pytest

from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.sessions import tip_filter as tf
from backend.app.sessions.service import SessionService
from backend.tests.unit.test_state_machine import FakeSessionRepository

HOME = "बच्चों के साथ घर पर गिनती की गतिविधियाँ करवाने के लिए अभिभावकों को प्रोत्साहित करें।"
MULTIPLY = "यह अंश बताता है कि गुणा और भाग की क्षमता कब विकसित होती है और जोड़-घटाव कैसे जुड़ते हैं।"
GOOD = "बंडल और खुली तीलियों से संख्या बनवाएँ ताकि बच्चे स्थानीय मान देख सकें।"


def test_home_and_parent_passages_do_not_qualify() -> None:
    move = load_move_card("NUM_PLACE_VALUE_BUNDLES")
    assert tf.is_home_passage(HOME)
    assert not tf.chunk_qualifies(move, HOME + " बंडल")
    assert tf.chunk_qualifies(move, GOOD)


def test_overview_of_other_topics_does_not_qualify_for_subtraction() -> None:
    move = load_move_card("NUM_SUB_REGROUP_BUNDLES")
    assert not tf.chunk_qualifies(move, MULTIPLY)  # the live off-topic excerpt (multiplication)
    assert tf.chunk_qualifies(move, "यह अंश संख्या और संक्रियाओं (जोड़ और घटाव) की समझ पर है।")


def test_feminine_verbs_are_dropped_for_a_male_teacher_only() -> None:
    tip = "आप ठोस सामग्री से गतिविधि करवा सकती हैं।"
    assert tf.has_feminine_reader_verb(tip)
    assert not tf.tip_text_qualifies(tip, "m")
    assert tf.tip_text_qualifies(tip, "f")
    assert tf.tip_text_qualifies("आप ठोस सामग्री से गतिविधि करवा सकते हैं।", "m")
    assert not tf.tip_text_qualifies(HOME, "f")


@pytest.mark.asyncio
@pytest.mark.parametrize("move_id", ["NUM_PLACE_VALUE_BUNDLES", "NUM_SUB_REGROUP_BUNDLES"])
async def test_learn_step_never_shows_a_home_tip_or_feminine_verb_to_a_male_teacher(
    move_id: str,
) -> None:
    service = SessionService(repository=FakeSessionRepository())
    move = load_move_card(move_id)
    text, cites = await service._learn_intro(move, "m")
    assert not tf.is_home_passage(text)
    assert not tf.has_feminine_reader_verb(text)
    for c in cites:  # whatever is shown is a real, on-topic passage
        assert c.line_hi.startswith("स्रोत: ")
