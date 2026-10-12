"""Unit tests for Claude output guards matching spec/05 §5.3–§5.10 and T09 acceptance criteria.

Acceptance criteria: >= 3 pass + >= 3 fail fixtures per guard.
"""

import pytest

from backend.app.llm.guards import (
    extract_numbers_from_text,
    guard_act_tagger,
    guard_child_line,
    guard_coach,
    guard_fidelity_checker,
    guard_guide_answerer,
    guard_intent_router,
    guard_page_ocr,
    guard_question_classifier,
    norm,
    normalize_hindi_text,
    substring_match,
)
from backend.app.llm.schemas import (
    ActTaggerOutput,
    CoachFeedbackOutput,
    FidelityCheckerOutput,
    GuideAnswererOutput,
    IntentRouterOutput,
    KeyPointEvaluation,
    PageOCROutput,
    QuestionClassifierOutput,
)
from backend.app.rule_engine.domain import (
    ChildResponse,
    ChildState,
    Problem,
    ResponseKind,
    TeachingAct,
)


# ── Text Normalization & Substring Match (§5.10) ─────────────────────────────
def test_norm_and_substring_match() -> None:
    assert norm("रवि, 52 में से 17 घटाओ!") == "रवि 52 में से 17 घटाओ"
    assert norm("५२ में से १७") == "52 में से 17"
    assert substring_match("52 में से 17", "रवि, 52 में से 17 घटाओ") is True
    assert substring_match("बंडल और तीली", "दस तीली का बंडल बनाओ") is False


# ── 1. guard_intent_router (§5.3) ────────────────────────────────────────────
@pytest.mark.parametrize(
    "intent,confidence",
    [
        ("answer_for_step", 0.95),
        ("question", 0.8),
        ("command_help", 1.0),
    ],
)
def test_guard_intent_router_pass(intent: str, confidence: float) -> None:
    output = IntentRouterOutput(intent=intent, confidence=confidence)  # type: ignore[arg-type]
    valid, msg = guard_intent_router(output)
    assert valid is True
    assert msg == "Valid"


@pytest.mark.parametrize(
    "intent,confidence",
    [
        ("invalid_intent", 0.8),
        ("question", -0.1),
        ("answer_for_step", 1.5),
    ],
)
def test_guard_intent_router_fail(intent: str, confidence: float) -> None:
    try:
        output = IntentRouterOutput.model_construct(intent=intent, confidence=confidence)  # type: ignore[arg-type]
    except Exception:
        return
    valid, msg = guard_intent_router(output)
    assert valid is False
    assert len(msg) > 0


# ── 2. guard_act_tagger (§5.4) ───────────────────────────────────────────────
def test_guard_act_tagger_pass_1() -> None:
    transcript = "रवि तुमने 52 में से 17 कैसे घटाया समझाओ"
    out = ActTaggerOutput(
        acts=[TeachingAct.ASK_TO_EXPLAIN],
        addressed_child="ravi",
        problem=None,
        quote="कैसे घटाया समझाओ",
    )
    valid, msg = guard_act_tagger(out, transcript, ["ravi", "priya", "aman"])
    assert valid is True
    assert msg == "Valid"


def test_guard_act_tagger_pass_2() -> None:
    transcript = "बच्चों 10-10 तीलियों के बंडल बनाकर गिनो"
    out = ActTaggerOutput(
        acts=[TeachingAct.CONCRETE_REPRESENTATION],
        addressed_child="all",
        problem=None,
        quote="10-10 तीलियों के बंडल बनाकर गिनो",
    )
    valid, msg = guard_act_tagger(out, transcript, ["ravi", "priya", "aman"])
    assert valid is True
    assert msg == "Valid"


def test_guard_act_tagger_pass_3() -> None:
    transcript = "अब सब 43 में से 27 घटाकर देखो"
    out = ActTaggerOutput(
        acts=[TeachingAct.GIVE_NEW_PROBLEM],
        addressed_child=None,
        problem=Problem(type="sub", a=43, b=27),
        quote="43 में से 27 घटाकर देखो",
    )
    valid, msg = guard_act_tagger(out, transcript, ["ravi", "priya", "aman"])
    assert valid is True
    assert msg == "Valid"


def test_guard_act_tagger_fail_too_many_acts() -> None:
    transcript = "रवि बताओ और बंडल बनाओ"
    out = ActTaggerOutput(
        acts=[
            TeachingAct.ASK_TO_EXPLAIN,
            TeachingAct.CONCRETE_REPRESENTATION,
            TeachingAct.PRAISE_EFFORT,
            TeachingAct.REPEAT_QUESTION,
            TeachingAct.CONTRAST_TWO_ANSWERS,
        ],
        addressed_child="ravi",
        problem=None,
        quote="",
    )
    valid, msg = guard_act_tagger(out, transcript, ["ravi"])
    assert valid is False
    assert "acts" in msg


def test_guard_act_tagger_fail_invalid_child() -> None:
    transcript = "सुरेश तुम बताओ"
    out = ActTaggerOutput(
        acts=[TeachingAct.REPEAT_QUESTION],
        addressed_child="suresh",
        problem=None,
        quote="",
    )
    valid, msg = guard_act_tagger(out, transcript, ["ravi", "priya", "aman"])
    assert valid is False
    assert "addressed_child" in msg


def test_guard_act_tagger_fail_quote_not_in_transcript() -> None:
    transcript = "रवि तुमने कैसे किया?"
    out = ActTaggerOutput(
        acts=[TeachingAct.ASK_TO_EXPLAIN],
        addressed_child="ravi",
        problem=None,
        quote="प्रिया तुम बताओ",
    )
    valid, msg = guard_act_tagger(out, transcript, ["ravi", "priya", "aman"])
    assert valid is False
    assert "quote" in msg


def test_guard_act_tagger_fail_problem_numbers_absent() -> None:
    transcript = "अब अगला सवाल करो"
    out = ActTaggerOutput(
        acts=[TeachingAct.GIVE_NEW_PROBLEM],
        addressed_child=None,
        problem=Problem(type="sub", a=99, b=45),
        quote="अगला सवाल करो",
    )
    valid, msg = guard_act_tagger(out, transcript, ["ravi", "priya", "aman"])
    assert valid is False
    assert "problem" in msg


# ── 3. guard_child_line (§5.5) ───────────────────────────────────────────────
def test_guard_child_line_pass_answer() -> None:
    resp = ChildResponse(
        persona_id="ravi",
        kind=ResponseKind.ANSWER,
        answer=24,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=43, b=27),
        allowed_numbers={24, 43, 27},
        forbidden={"16"},
    )
    valid, msg = guard_child_line("दीदी, 24 आया!", resp)
    assert valid is True
    assert msg == "Valid"


def test_guard_child_line_pass_silent() -> None:
    resp = ChildResponse(
        persona_id="priya",
        kind=ResponseKind.SILENT,
        answer=None,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="shy",
        item=Problem(type="sub", a=43, b=27),
    )
    valid, msg = guard_child_line("", resp)
    assert valid is True
    assert msg == "Valid"


def test_guard_child_line_pass_scaffolded() -> None:
    resp = ChildResponse(
        persona_id="ravi",
        kind=ResponseKind.SCAFFOLDED_CORRECT,
        answer=16,
        prior_state=ChildState.CAN_EXPLAIN,
        new_state=ChildState.PARTIAL,
        affect="encouraged",
        item=Problem(type="sub", a=43, b=27),
        allowed_numbers={1, 13, 7, 6, 3, 2, 16, 43, 27},
        forbidden={"24"},
    )
    line = "हम्म... 13 में से 7 घटाया तो 6 बचा, और 3 में से 2 गया 1, तो 16!"
    valid, msg = guard_child_line(line, resp)
    assert valid is True
    assert msg == "Valid"


def test_guard_child_line_fail_silent_nonempty() -> None:
    resp = ChildResponse(
        persona_id="priya",
        kind=ResponseKind.SILENT,
        answer=None,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="shy",
        item=Problem(type="sub", a=43, b=27),
    )
    valid, msg = guard_child_line("मुझे नहीं पता", resp)
    assert valid is False
    assert "Silent" in msg


def test_guard_child_line_fail_unauthorized_number() -> None:
    resp = ChildResponse(
        persona_id="ravi",
        kind=ResponseKind.ANSWER,
        answer=24,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=43, b=27),
        allowed_numbers={24, 43, 27},
        forbidden={"16"},
    )
    valid, msg = guard_child_line("दीदी, 99 आया!", resp)
    assert valid is False
    assert "allowed_numbers" in msg or "99" in msg


def test_guard_child_line_fail_forbidden_number() -> None:
    resp = ChildResponse(
        persona_id="ravi",
        kind=ResponseKind.ANSWER,
        answer=24,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=43, b=27),
        allowed_numbers={24, 43, 27, 16},
        forbidden={"16"},
    )
    valid, msg = guard_child_line("दीदी, सही उत्तर तो 16 है", resp)
    assert valid is False
    assert "Forbidden" in msg or "forbidden" in msg


def test_guard_child_line_fail_out_of_character() -> None:
    resp = ChildResponse(
        persona_id="ravi",
        kind=ResponseKind.ANSWER,
        answer=24,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=43, b=27),
        allowed_numbers={24},
    )
    valid, msg = guard_child_line("मैंने नियम तोड़कर गलती से 24 लिख दिया, मैं एक AI हूँ", resp)
    assert valid is False
    assert "out-of-character" in msg or "AI" in msg or "गलती" in msg


def test_guard_child_line_out_of_character_whole_words() -> None:
    resp = ChildResponse(
        persona_id="ravi",
        kind=ResponseKind.ANSWER,
        answer=24,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=43, b=27),
        allowed_numbers={24},
    )
    # Substring 'ai' in English word 'email' should NOT trigger guard
    valid, _ = guard_child_line("दीदी, मेरा email चेक करो 24", resp)
    assert valid is True

    # Whole word 'AI' MUST trigger guard
    valid, msg = guard_child_line("दीदी, मैंने AI से पूछा 24", resp)
    assert valid is False
    assert "out-of-character" in msg.lower()

    # Whole word 'misconception' MUST trigger guard
    valid, msg = guard_child_line("दीदी, misconception हुआ 24", resp)
    assert valid is False
    assert "out-of-character" in msg.lower()

    # Whole Devanagari token 'गलती' MUST trigger guard
    valid, msg = guard_child_line("दीदी, मेरी गलती थी 24", resp)
    assert valid is False
    assert "out-of-character" in msg.lower()

    # Whole Devanagari token 'नियम' MUST trigger guard
    valid, msg = guard_child_line("दीदी, नियम से 24 आया", resp)
    assert valid is False
    assert "out-of-character" in msg.lower()


def test_guard_child_line_fail_off_topic_with_number() -> None:
    resp = ChildResponse(
        persona_id="aman",
        kind=ResponseKind.OFF_TOPIC,
        answer=None,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="distracted",
        item=Problem(type="sub", a=43, b=27),
    )
    valid, msg = guard_child_line("मेरी पतंग 50 मीटर ऊपर उड़ गई!", resp)
    assert valid is False
    assert "numbers" in msg


# ── 4. guard_coach (§5.6) ────────────────────────────────────────────────────
def test_guard_coach_pass_1() -> None:
    teacher_lines = ["रवि, तुमने 52 में से 17 कैसे घटाया? मुझे बताओ।"]
    fb = CoachFeedbackOutput(
        scores={"crit_explaining": 2, "crit_concrete": 0},
        evidence={"crit_explaining": "तुमने 52 में से 17 कैसे घटाया? मुझे बताओ।", "crit_concrete": ""},
        strength_hi="आपने रवि से उसका तरीका पूछा, जिससे उसकी सोच समझ में आई।",
        change_hi="अगली बार बंडल और तीली का उपयोग करके घटाव करवाइए।",
        exact_words_hi="10-10 तीलियों के बंडल बनाकर 52 तीलियाँ गिनो।",
        confidence=0.85,
    )
    valid, msg = guard_coach(fb, ["crit_explaining", "crit_concrete"], teacher_lines, False, 35)
    assert valid is True
    assert msg == "Valid"


def test_guard_coach_pass_2() -> None:
    teacher_lines = ["रवि, 43 में से 27 घटाकर बताओ।"]
    fb = CoachFeedbackOutput(
        scores={"c1": 0, "c2": 0},
        evidence={"c1": "", "c2": ""},
        strength_hi="आपने शांत भाव से कक्षा में सवाल प्रस्तुत किया।",
        change_hi="अगले कदम में बच्चों से पूछिए कि उन्होंने यह कैसे किया।",
        exact_words_hi="रवि, तुमने यह कैसे सोचा, मुझे समझाओ।",
        confidence=0.7,
    )
    valid, msg = guard_coach(fb, ["c1", "c2"], teacher_lines, False, 16)
    assert valid is True
    assert msg == "Valid"


def test_guard_coach_pass_3() -> None:
    teacher_lines = ["बहुत अच्छा! दोनों उत्तर बोर्ड पर रखकर देखो।"]
    fb = CoachFeedbackOutput(
        scores={"c_contrast": 2},
        evidence={"c_contrast": "दोनों उत्तर बोर्ड पर रखकर देखो।"},
        strength_hi="आपने दोनों उत्तरों की तुलना करवाकर सोचने का अवसर दिया।",
        change_hi="शांत बच्चों को भी अपनी बात कहने का मौका दीजिए।",
        exact_words_hi="प्रिया, तुम भी बताओ कि तुम्हारा क्या सोचना है।",
        confidence=0.9,
    )
    valid, msg = guard_coach(fb, ["c_contrast"], teacher_lines, True, 16)
    assert valid is True
    assert msg == "Valid"


def test_guard_coach_fail_missing_rubric_key() -> None:
    teacher_lines = ["बताओ कैसे किया?"]
    fb = CoachFeedbackOutput(
        scores={"c1": 2},
        evidence={"c1": "बताओ कैसे किया?"},
        strength_hi="आपने अच्छा पूछा।",
        change_hi="अगली बार तीलियाँ दिखाएँ।",
        exact_words_hi="कीलियाँ गिनो।",
        confidence=0.8,
    )
    valid, msg = guard_coach(fb, ["c1", "c2"], teacher_lines, False, 35)
    assert valid is False
    assert "criteria" in msg or "key" in msg


def test_guard_coach_fail_quote_not_in_teacher_transcript() -> None:
    teacher_lines = ["शाबाश रवि!"]
    fb = CoachFeedbackOutput(
        scores={"c1": 2},
        evidence={"c1": "45 आया!"},  # This is child line, not in teacher lines!
        strength_hi="आपने अच्छा काम किया।",
        change_hi="अगली बार बंडल लाएँ।",
        exact_words_hi="बंडल खोलो।",
        confidence=0.8,
    )
    valid, msg = guard_coach(fb, ["c1"], teacher_lines, False, 35)
    assert valid is False
    assert "evidence" in msg or "transcript" in msg


def test_guard_coach_fail_disrespectful_register() -> None:
    teacher_lines = ["रवि कैसे किया?"]
    fb = CoachFeedbackOutput(
        scores={"c1": 1},
        evidence={"c1": "रवि कैसे किया?"},
        strength_hi="तुमने अच्छा सवाल पूछा।",  # Disrespectful तुम/तुमने
        change_hi="अगली बार बंडल लाओ।",
        exact_words_hi="बंडल खोलो।",
        confidence=0.8,
    )
    valid, msg = guard_coach(fb, ["c1"], teacher_lines, False, 35)
    assert valid is False
    assert "register" in msg or "आप" in msg or "तुम" in msg


def test_guard_coach_fail_leaked_answer() -> None:
    teacher_lines = ["कैसे किया?"]
    fb = CoachFeedbackOutput(
        scores={"c1": 1},
        evidence={"c1": "कैसे किया?"},
        strength_hi="आपने बच्चे से पूछा।",
        change_hi="अगली बार उत्तर सीधे न बताएँ।",
        exact_words_hi="रवि, इसका सही उत्तर 35 है, लिख लो।",  # Leaks correct answer 35!
        confidence=0.8,
    )
    valid, msg = guard_coach(fb, ["c1"], teacher_lines, True, 35)
    assert valid is False
    assert "answer" in msg or "leak" in msg or "35" in msg


# ── 5. guard_fidelity_checker (§5.7) ─────────────────────────────────────────
def test_guard_fidelity_checker_pass_1() -> None:
    transcript = "मैंने पहले बच्चे से पूछा कैसे किया, फिर बंडल खोलकर तीलियाँ गिनवाईं।"
    out = FidelityCheckerOutput(
        points=[
            KeyPointEvaluation(id="kp1", status="covered", quote="बच्चे से पूछा कैसे किया"),
            KeyPointEvaluation(id="kp2", status="covered", quote="बंडल खोलकर तीलियाँ गिनवाईं"),
            KeyPointEvaluation(id="kp3", status="missing", quote=""),
        ],
        misconceptions=[],
        confidence=0.9,
    )
    valid, msg = guard_fidelity_checker(
        out, expected_point_ids=["kp1", "kp2", "kp3"], transcript=transcript
    )
    assert valid is True
    assert msg == "Valid"


def test_guard_fidelity_checker_pass_2() -> None:
    transcript = "मैंने केवल सवाल दोहराया।"
    out = FidelityCheckerOutput(
        points=[
            KeyPointEvaluation(id="kp1", status="missing", quote=""),
            KeyPointEvaluation(id="kp2", status="missing", quote=""),
        ],
        misconceptions=["अध्यापिका ने बंडल-तीली का उपयोग नहीं किया"],
        confidence=0.85,
    )
    valid, msg = guard_fidelity_checker(
        out, expected_point_ids=["kp1", "kp2"], transcript=transcript
    )
    assert valid is True
    assert msg == "Valid"


def test_guard_fidelity_checker_pass_3() -> None:
    transcript = "बच्चों को तीली दी पर पूरी बात नहीं बताई।"
    out = FidelityCheckerOutput(
        points=[
            KeyPointEvaluation(id="kp1", status="partial", quote="बच्चों को तीली दी"),
        ],
        misconceptions=[],
        confidence=0.75,
    )
    valid, msg = guard_fidelity_checker(out, expected_point_ids=["kp1"], transcript=transcript)
    assert valid is True
    assert msg == "Valid"


def test_guard_fidelity_checker_fail_missing_key_point() -> None:
    transcript = "मैंने पूछा"
    out = FidelityCheckerOutput(
        points=[
            KeyPointEvaluation(id="kp1", status="covered", quote="मैंने पूछा"),
        ],
        misconceptions=[],
        confidence=0.8,
    )
    valid, msg = guard_fidelity_checker(
        out, expected_point_ids=["kp1", "kp2"], transcript=transcript
    )
    assert valid is False
    assert "key point" in msg or "points" in msg


def test_guard_fidelity_checker_fail_quote_not_in_transcript() -> None:
    transcript = "मैंने केवल सवाल पूछा"
    out = FidelityCheckerOutput(
        points=[
            KeyPointEvaluation(id="kp1", status="covered", quote="बंडल खोलकर दिखाया"),
        ],
        misconceptions=[],
        confidence=0.8,
    )
    valid, msg = guard_fidelity_checker(out, expected_point_ids=["kp1"], transcript=transcript)
    assert valid is False
    assert "quote" in msg


def test_guard_fidelity_checker_fail_missing_status_with_quote() -> None:
    transcript = "मैंने पूछा"
    out = FidelityCheckerOutput(
        points=[
            KeyPointEvaluation(id="kp1", status="missing", quote="मैंने पूछा"),
        ],
        misconceptions=[],
        confidence=0.8,
    )
    valid, msg = guard_fidelity_checker(out, expected_point_ids=["kp1"], transcript=transcript)
    assert valid is False
    assert "missing" in msg or "quote" in msg


# ── 6. guard_question_classifier (§5.8) ──────────────────────────────────────
def test_guard_question_classifier_pass_1() -> None:
    out = QuestionClassifierOutput(
        category="pedagogy",
        needs_clarification=False,
        clarifying_question_hi="",
        search_query_hi="गणित में हासिल का घटाव",
        confidence=0.9,
    )
    valid, msg = guard_question_classifier(out)
    assert valid is True
    assert msg == "Valid"


def test_guard_question_classifier_pass_2() -> None:
    out = QuestionClassifierOutput(
        category="classroom_management",
        needs_clarification=True,
        clarifying_question_hi="आपकी कक्षा में कितने बच्चे शांत रहते हैं?",
        search_query_hi="कक्षा प्रबंधन शांत बच्चे",
        confidence=0.8,
    )
    valid, msg = guard_question_classifier(out)
    assert valid is True
    assert msg == "Valid"


def test_guard_question_classifier_pass_3() -> None:
    out = QuestionClassifierOutput(
        category="out_of_scope",
        needs_clarification=False,
        clarifying_question_hi="",
        search_query_hi="",
        confidence=0.95,
    )
    valid, msg = guard_question_classifier(out)
    assert valid is True
    assert msg == "Valid"


def test_guard_question_classifier_fail_clarification_empty() -> None:
    out = QuestionClassifierOutput(
        category="pedagogy",
        needs_clarification=True,
        clarifying_question_hi="",
        search_query_hi="घटाव",
        confidence=0.7,
    )
    valid, msg = guard_question_classifier(out)
    assert valid is False
    assert "clarifying_question" in msg


def test_guard_question_classifier_fail_clarification_too_long() -> None:
    long_q = "क्या आप मुझे यह विस्तार से बता सकते हैं कि आपकी कक्षा के बच्चे किस तरह से तीलियों का उपयोग करते हैं और क्यों वे ऐसा नहीं कर पाते हैं?"
    out = QuestionClassifierOutput(
        category="pedagogy",
        needs_clarification=True,
        clarifying_question_hi=long_q,
        search_query_hi="घटाव",
        confidence=0.7,
    )
    valid, msg = guard_question_classifier(out)
    assert valid is False
    assert "words" in msg or "long" in msg


def test_guard_question_classifier_fail_missing_search_query() -> None:
    out = QuestionClassifierOutput(
        category="pedagogy",
        needs_clarification=False,
        clarifying_question_hi="",
        search_query_hi="",
        confidence=0.8,
    )
    valid, msg = guard_question_classifier(out)
    assert valid is False
    assert "search_query" in msg


# ── 7. guard_guide_answerer (§5.8) ───────────────────────────────────────────
def test_guard_guide_answerer_pass_1() -> None:
    chunks_text = "कक्षा 2 में 10-10 के बंडल बनाकर 52 संख्या सिखाई जाती है।"
    out = GuideAnswererOutput(
        answer_hi="आप बच्चों को 10-10 तीलियों के बंडल बनाकर 52 संख्या सिखा सकती हैं।",
        source_ids=["chunk-1"],
        try_this_week_hi="कक्षा में तीलियों के बंडल बनवाएँ।",
        confidence=0.85,
    )
    valid, msg = guard_guide_answerer(out, ["chunk-1", "chunk-2"], chunks_text)
    assert valid is True
    assert msg == "Valid"


def test_guard_guide_answerer_pass_2() -> None:
    chunks_text = "बच्चों को खेल-खेल में वर्णमाला सिखाएँ।"
    out = GuideAnswererOutput(
        answer_hi="आप बच्चों के साथ वर्णमाला का खेल खेल सकती हैं।",
        source_ids=["chunk-a"],
        try_this_week_hi="अक्षर कार्ड से खेलें।",
        confidence=0.9,
    )
    valid, msg = guard_guide_answerer(out, ["chunk-a"], chunks_text)
    assert valid is True
    assert msg == "Valid"


def test_guard_guide_answerer_pass_3() -> None:
    chunks_text = "प्राथमिक स्तर पर गणित अभ्यास के 5 मुख्य चरण हैं।"
    out = GuideAnswererOutput(
        answer_hi="आपके लिए यह समझना उपयोगी होगा कि गणित के 5 चरण होते हैं।",
        source_ids=["c1", "c2"],
        try_this_week_hi="पहला चरण लागू करें।",
        confidence=0.8,
    )
    valid, msg = guard_guide_answerer(out, ["c1", "c2", "c3"], chunks_text)
    assert valid is True
    assert msg == "Valid"


def test_guard_guide_answerer_fail_empty_sources() -> None:
    out = GuideAnswererOutput(
        answer_hi="आप ऐसा कर सकती हैं।",
        source_ids=[],
        try_this_week_hi="",
        confidence=0.8,
    )
    valid, msg = guard_guide_answerer(out, ["c1"], "कुछ जानकारी")
    assert valid is False
    assert "source" in msg


def test_guard_guide_answerer_fail_uncited_source() -> None:
    out = GuideAnswererOutput(
        answer_hi="आप ऐसा कर सकती हैं।",
        source_ids=["hallucinated-chunk"],
        try_this_week_hi="",
        confidence=0.8,
    )
    valid, msg = guard_guide_answerer(out, ["c1", "c2"], "कुछ जानकारी")
    assert valid is False
    assert "source" in msg or "hallucinated" in msg


def test_guard_guide_answerer_fail_unauthorized_number() -> None:
    chunks_text = "कक्षा में तीलियाँ गिनवाएँ।"
    out = GuideAnswererOutput(
        answer_hi="आप बच्चों को 99 तीलियाँ गिनने के लिए कहें।",  # 99 not in chunks_text!
        source_ids=["c1"],
        try_this_week_hi="",
        confidence=0.8,
    )
    valid, msg = guard_guide_answerer(out, ["c1"], chunks_text)
    assert valid is False
    assert "number" in msg or "99" in msg


def test_guard_guide_answerer_fail_disrespectful_register() -> None:
    chunks_text = "तीलियाँ गिनवाएँ।"
    out = GuideAnswererOutput(
        answer_hi="तुम बच्चों को तीलियाँ गिनने को कहो।",  # Disrespectful तुम
        source_ids=["c1"],
        try_this_week_hi="",
        confidence=0.8,
    )
    valid, msg = guard_guide_answerer(out, ["c1"], chunks_text)
    assert valid is False
    assert "register" in msg or "आप" in msg or "तुम" in msg


# ── 8. guard_page_ocr (§5.9) ─────────────────────────────────────────────────
def test_guard_page_ocr_pass_1() -> None:
    out = PageOCROutput(text_hi="प्राथमिक स्तर पर मूलभूत साक्षरता एवं संख्या ज्ञान")
    valid, msg = guard_page_ocr(out)
    assert valid is True
    assert msg == "Valid"


def test_guard_page_ocr_pass_2() -> None:
    out = PageOCROutput(text_hi="कक्षा 2 के बच्चों के लिए कार्यपुस्तिका - अभ्यास 12")
    valid, msg = guard_page_ocr(out)
    assert valid is True
    assert msg == "Valid"


def test_guard_page_ocr_pass_3() -> None:
    out = PageOCROutput(text_hi="निपुण भारत मिशन के अंतर्गत FLN संदर्शिका")
    valid, msg = guard_page_ocr(out)
    assert valid is True
    assert msg == "Valid"


def test_guard_page_ocr_fail_english_text() -> None:
    out = PageOCROutput(text_hi="This is completely in English language without Hindi.")
    valid, msg = guard_page_ocr(out)
    assert valid is False
    assert "Devanagari" in msg or "ratio" in msg


def test_guard_page_ocr_fail_garbled_ascii() -> None:
    out = PageOCROutput(text_hi="12345 %^&* @#$ kjahsdkja hsdkjh")
    valid, msg = guard_page_ocr(out)
    assert valid is False
    assert "Devanagari" in msg or "ratio" in msg


def test_guard_page_ocr_fail_empty() -> None:
    out = PageOCROutput(text_hi="")
    valid, msg = guard_page_ocr(out)
    assert valid is False
    assert "empty" in msg or "Devanagari" in msg


# ── Additional Edge & Branch Coverage Tests ──────────────────────────────────
def test_norm_empty_and_helpers() -> None:
    assert norm("") == ""
    assert substring_match("", "source text") is True
    assert normalize_hindi_text("  नमस्ते  ") == "नमस्ते"
    assert extract_numbers_from_text("रवि ने 42 कहा") == [42]


def test_guard_act_tagger_empty_acts() -> None:
    out = ActTaggerOutput.model_construct(
        acts=[],
        addressed_child="ravi",
        problem=None,
        quote="",
    )
    valid, msg = guard_act_tagger(out, "रवि बताओ", ["ravi"])
    assert valid is False
    assert "At least one act" in msg


def test_guard_act_tagger_problem_variations() -> None:
    # Problem with b absent
    out_b = ActTaggerOutput(
        acts=[TeachingAct.GIVE_NEW_PROBLEM],
        addressed_child=None,
        problem=Problem(type="sub", a=43, b=99),
        quote="43 में से घटाओ",
    )
    valid_b, msg_b = guard_act_tagger(out_b, "43 में से घटाओ", ["ravi"])
    assert valid_b is False
    assert "problem number b=99" in msg_b

    # Problem with tens absent
    out_tens = ActTaggerOutput(
        acts=[TeachingAct.GIVE_NEW_PROBLEM],
        addressed_child=None,
        problem=Problem(type="place_value", tens=5, ones=2),
        quote="2 तीलियाँ लो",
    )
    valid_tens, msg_tens = guard_act_tagger(out_tens, "2 तीलियाँ लो", ["ravi"])
    assert valid_tens is False
    assert "problem tens=5" in msg_tens

    # Problem with ones absent
    out_ones = ActTaggerOutput(
        acts=[TeachingAct.GIVE_NEW_PROBLEM],
        addressed_child=None,
        problem=Problem(type="place_value", tens=5, ones=2),
        quote="5 बंडल लो",
    )
    valid_ones, msg_ones = guard_act_tagger(out_ones, "5 बंडल लो", ["ravi"])
    assert valid_ones is False
    assert "problem ones=2" in msg_ones

    # Problem with word absent
    out_w_absent = ActTaggerOutput(
        acts=[TeachingAct.GIVE_NEW_PROBLEM],
        addressed_child=None,
        problem=Problem(type="read_word", word="किताब"),
        quote="मेला पढ़ो",
    )
    valid_w, msg_w = guard_act_tagger(out_w_absent, "मेला पढ़ो", ["ravi"])
    assert valid_w is False
    assert "problem word 'किताब'" in msg_w

    # Problem with word present
    out_w_present = ActTaggerOutput(
        acts=[TeachingAct.GIVE_NEW_PROBLEM],
        addressed_child=None,
        problem=Problem(type="read_word", word="मेला"),
        quote="मेला पढ़ो",
    )
    valid_wp, msg_wp = guard_act_tagger(out_w_present, "मेला पढ़ो", ["ravi"])
    assert valid_wp is True
    assert msg_wp == "Valid"


def test_guard_child_line_additional_branches() -> None:
    resp = ChildResponse(
        persona_id="ravi",
        kind=ResponseKind.ANSWER,
        answer=24,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=43, b=27),
        allowed_numbers={24, 43, 27},
        forbidden={"16", "गलतउत्तर"},
    )
    # Empty line for non-silent
    valid_empty, msg_empty = guard_child_line("", resp)
    assert valid_empty is False
    assert "empty" in msg_empty

    # Too long line (> 25 words)
    long_line = "दीदी " + "उत्तर " * 30 + "24"
    valid_long, msg_long = guard_child_line(long_line, resp)
    assert valid_long is False
    assert "max word count" in msg_long

    # Excessive English words (> 3 words)
    eng_line = "hello my dear teacher friends 24"
    valid_eng, msg_eng = guard_child_line(eng_line, resp)
    assert valid_eng is False
    assert "English words" in msg_eng

    # Forbidden text token
    valid_forb_txt, msg_forb_txt = guard_child_line("दीदी, यह तो गलतउत्तर है 24", resp)
    assert valid_forb_txt is False
    assert "Forbidden token" in msg_forb_txt

    # Literacy string answer pass & fail
    resp_lit = ChildResponse(
        persona_id="priya",
        kind=ResponseKind.ANSWER,
        answer="मे - ला",
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.CAN_EXPLAIN,
        affect="shy",
        item=Problem(type="read_word", word="मेला"),
        allowed_numbers=set(),
    )
    valid_lit_p, msg_lit_p = guard_child_line("मे - ला", resp_lit)
    assert valid_lit_p is True
    assert msg_lit_p == "Valid"

    valid_lit_f, msg_lit_f = guard_child_line("कमल", resp_lit)
    assert valid_lit_f is False
    assert "Literacy answer" in msg_lit_f


def test_guard_coach_additional_branches() -> None:
    teacher_lines = ["बहुत अच्छा! आपने सवाल पूछा।"]
    # Invalid score value
    fb_score = CoachFeedbackOutput.model_construct(
        scores={"c1": 3},  # invalid score
        evidence={"c1": "बहुत अच्छा!"},
        strength_hi="आपने अच्छा काम किया।",
        change_hi="अगली बार बंडल लाएँ।",
        exact_words_hi="बंडल गिनो।",
        confidence=0.8,
    )
    valid_sc, msg_sc = guard_coach(fb_score, ["c1"], teacher_lines, False, 10)
    assert valid_sc is False
    assert "Score for c1 must be in {0, 1, 2}" in msg_sc

    # Score > 0 with empty evidence quote
    fb_no_quote = CoachFeedbackOutput(
        scores={"c1": 1},
        evidence={"c1": ""},
        strength_hi="आपने अच्छा काम किया।",
        change_hi="अगली बार बंडल लाएँ।",
        exact_words_hi="बंडल गिनो।",
        confidence=0.8,
    )
    valid_nq, msg_nq = guard_coach(fb_no_quote, ["c1"], teacher_lines, False, 10)
    assert valid_nq is False
    assert "Evidence quote missing" in msg_nq

    # Word budget exceeded (> 60 words)
    fb_words = CoachFeedbackOutput(
        scores={"c1": 1},
        evidence={"c1": "बहुत अच्छा!"},
        strength_hi="आपने " + "शब्द " * 65,
        change_hi="अगली बार बंडल लाएँ।",
        exact_words_hi="बंडल गिनो।",
        confidence=0.8,
    )
    valid_wb, msg_wb = guard_coach(fb_words, ["c1"], teacher_lines, False, 10)
    assert valid_wb is False
    assert "exceeds word budget" in msg_wb

    # Multi-sentence inside sentence
    fb_multi = CoachFeedbackOutput(
        scores={"c1": 1},
        evidence={"c1": "बहुत अच्छा!"},
        strength_hi="आपने अच्छा किया। आपने तीलियाँ दीं। आपने बच्चों से पूछा।",
        change_hi="अगली बार बंडल लाएँ।",
        exact_words_hi="बंडल गिनो।",
        confidence=0.8,
    )
    valid_ms, msg_ms = guard_coach(fb_multi, ["c1"], teacher_lines, False, 10)
    assert valid_ms is False
    assert "must be a single sentence" in msg_ms

    # Leaked string answer in exact_words_hi
    fb_leak_str = CoachFeedbackOutput(
        scores={"c1": 1},
        evidence={"c1": "बहुत अच्छा!"},
        strength_hi="आपने अच्छा काम किया।",
        change_hi="अगली बार बंडल लाएँ।",
        exact_words_hi="कमल बोलो।",
        confidence=0.8,
    )
    valid_ls, msg_ls = guard_coach(fb_leak_str, ["c1"], teacher_lines, True, "कमल")
    assert valid_ls is False
    assert "leaked correct answer" in msg_ls

    # Confidence out of bounds
    fb_conf = CoachFeedbackOutput.model_construct(
        scores={"c1": 1},
        evidence={"c1": "बहुत अच्छा!"},
        strength_hi="आपने अच्छा काम किया।",
        change_hi="अगली बार बंडल लाएँ।",
        exact_words_hi="बंडल गिनो।",
        confidence=1.5,
    )
    valid_cf, msg_cf = guard_coach(fb_conf, ["c1"], teacher_lines, False, 10)
    assert valid_cf is False
    assert "Confidence out of bounds" in msg_cf


def test_guard_fidelity_checker_additional_branches() -> None:
    transcript = "मैंने समझाया"
    # Covered without quote
    out_no_quote = FidelityCheckerOutput(
        points=[KeyPointEvaluation(id="kp1", status="covered", quote="")],
        misconceptions=[],
        confidence=0.8,
    )
    valid_nq, msg_nq = guard_fidelity_checker(
        out_no_quote, expected_point_ids=["kp1"], transcript=transcript
    )
    assert valid_nq is False
    assert "without supporting quote" in msg_nq

    # More than 3 misconceptions
    out_too_many_m = FidelityCheckerOutput(
        points=[KeyPointEvaluation(id="kp1", status="covered", quote="मैंने समझाया")],
        misconceptions=["गलती 1", "गलती 2", "गलती 3", "गलती 4"],
        confidence=0.8,
    )
    valid_tm, msg_tm = guard_fidelity_checker(
        out_too_many_m, expected_point_ids=["kp1"], transcript=transcript
    )
    assert valid_tm is False
    assert "Too many misconceptions" in msg_tm

    # Misconception > 25 words
    out_long_m = FidelityCheckerOutput(
        points=[KeyPointEvaluation(id="kp1", status="covered", quote="मैंने समझाया")],
        misconceptions=["गलती " * 30],
        confidence=0.8,
    )
    valid_lm, msg_lm = guard_fidelity_checker(
        out_long_m, expected_point_ids=["kp1"], transcript=transcript
    )
    assert valid_lm is False
    assert "Misconception exceeds 25 words" in msg_lm

    # Confidence out of bounds
    out_conf = FidelityCheckerOutput.model_construct(
        points=[KeyPointEvaluation(id="kp1", status="covered", quote="मैंने समझाया")],
        misconceptions=[],
        confidence=-0.1,
    )
    valid_cf, msg_cf = guard_fidelity_checker(
        out_conf, expected_point_ids=["kp1"], transcript=transcript
    )
    assert valid_cf is False
    assert "Confidence out of bounds" in msg_cf


def test_guard_question_classifier_additional_branches() -> None:
    out_conf = QuestionClassifierOutput.model_construct(
        category="pedagogy",
        needs_clarification=False,
        clarifying_question_hi="",
        search_query_hi="घटाव",
        confidence=1.5,
    )
    valid, msg = guard_question_classifier(out_conf)
    assert valid is False
    assert "Confidence out of bounds" in msg


def test_guard_guide_answerer_additional_branches() -> None:
    # Word budget exceeded (> 80 words)
    out_long = GuideAnswererOutput(
        answer_hi="आप " + "शब्द " * 85,
        source_ids=["c1"],
        try_this_week_hi="",
        confidence=0.8,
    )
    valid_w, msg_w = guard_guide_answerer(out_long, ["c1"], "शब्द")
    assert valid_w is False
    assert "exceeds maximum word budget" in msg_w

    # Confidence out of bounds
    out_conf = GuideAnswererOutput.model_construct(
        answer_hi="आप समझें।",
        source_ids=["c1"],
        try_this_week_hi="",
        confidence=-0.5,
    )
    valid_cf, msg_cf = guard_guide_answerer(out_conf, ["c1"], "कुछ जानकारी")
    assert valid_cf is False
    assert "Confidence out of bounds" in msg_cf
