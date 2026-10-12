"""Unit tests for act_tagger role, keyword fallback tagger, act examples, and golden fixtures.

Strictly follows spec/05 §5.4 and T10 acceptance criteria:
- Prompt v1 verification
- content/act_examples_hi.yaml (>= 28 examples across 14 acts, including Ravi example)
- Keyword fallback tagger tested on >= 15 sentences
- 8 golden fixtures verified against guard_act_tagger
- Labelled turns evaluation
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.llm.guards import guard_act_tagger
from backend.app.llm.roles.act_tagger import (
    fallback_tag_act,
    format_act_examples_block,
    load_act_examples,
    tag_act,
)
from backend.app.llm.schemas import ActTaggerOutput
from backend.app.rule_engine.domain import Problem, TeachingAct


# ── 1. Content: act_examples_hi.yaml Verification ────────────────────────────
def test_act_examples_content() -> None:
    examples = load_act_examples()
    assert len(examples) >= 28, f"Expected >= 28 examples, got {len(examples)}"

    # Check all 14 acts are represented with >= 2 examples
    act_counts: dict[str, int] = {}
    for ex in examples:
        act_val = ex["act"]
        act_counts[act_val] = act_counts.get(act_val, 0) + 1

    for act in TeachingAct:
        assert act.value in act_counts, f"Missing teaching act in examples: {act.value}"
        assert act_counts[act.value] >= 2, (
            f"Act {act.value} has {act_counts[act.value]} examples, expected >= 2"
        )

    # Verify Ravi worked example is included
    ravi_examples = [
        ex
        for ex in examples
        if ex.get("addressed_child") == "ravi" and "52" in ex.get("teacher_line_hi", "")
    ]
    assert len(ravi_examples) >= 1, "Ravi worked example missing from act_examples_hi.yaml"


def test_format_act_examples_block() -> None:
    examples = load_act_examples()
    block = format_act_examples_block(examples[:4])
    assert len(block) > 0
    assert "Teacher:" in block
    assert "Output:" in block


# ── 2. Fallback Tagger: >= 15 Sentences Test Suite ───────────────────────────
FALLBACK_15_TEST_CASES = [
    # 1. ask_to_explain
    (
        "रवि तुमने 52 में से 17 कैसे घटाया समझाओ।",
        TeachingAct.ASK_TO_EXPLAIN,
        "ravi",
    ),
    # 2. concrete_representation
    (
        "बच्चों 10-10 तीलियों के बंडल बनाकर गिनो।",
        TeachingAct.CONCRETE_REPRESENTATION,
        "all",
    ),
    # 3. probe_simpler_case
    (
        "रवि पहले 12 में से 7 करके दिखाओ।",
        TeachingAct.PROBE_SIMPLER_CASE,
        "ravi",
    ),
    # 4. contrast_answers
    (
        "दोनों उत्तर बोर्ड पर रखकर देखो किसका सही है।",
        TeachingAct.CONTRAST_TWO_ANSWERS,
        None,
    ),
    # 5. model_step_aloud
    (
        "देखो मैं करके दिखाती हूँ, पहले बंडल खोलेंगे।",
        TeachingAct.MODEL_STEP_ALOUD,
        None,
    ),
    # 6. tell_answer
    (
        "रवि सही उत्तर 35 है, लिख लो।",
        TeachingAct.TELL_ANSWER,
        "ravi",
    ),
    # 7. praise_effort
    (
        "शाबाश रवि तुमने बहुत अच्छी कोशिश की!",
        TeachingAct.PRAISE_EFFORT,
        "ravi",
    ),
    # 8. scold
    (
        "इतना भी नहीं आता, चुपचाप बैठो!",
        TeachingAct.SCOLD,
        None,
    ),
    # 9. phonics_sound_out
    (
        "अक्षरों की आवाज़ निकालो, म... े... ला...",
        TeachingAct.PHONICS_SOUND_OUT,
        None,
    ),
    # 10. involve_peer
    (
        "अमन तुम रवि की मदद करो और समझाओ।",
        TeachingAct.INVOLVE_PEER,
        "aman",
    ),
    # 11. praise_generic
    (
        "शाबाश बच्चों बहुत अच्छा!",
        TeachingAct.PRAISE_GENERIC,
        "all",
    ),
    # 12. off_task
    (
        "अरे बाहर देखो बारिश शुरू हो गई है।",
        TeachingAct.OFF_TASK,
        None,
    ),
    # 13. give_new_problem with numbers
    (
        "अब सब बच्चे 43 में से 27 घटाकर दिखाओ।",
        TeachingAct.GIVE_NEW_PROBLEM,
        "all",
    ),
    # 14. repeat_question (unmatched utterance)
    (
        "अब आगे क्या होगा?",
        TeachingAct.REPEAT_QUESTION,
        None,
    ),
    # 15. priya addressing with ask_to_explain
    (
        "प्रिया तुमने 35 उत्तर कैसे सोचा मुझे बताओ।",
        TeachingAct.ASK_TO_EXPLAIN,
        "priya",
    ),
    # 16. multiple acts (praise + concrete)
    (
        "शाबाश! तीलियों के बंडल बनाओ।",
        TeachingAct.CONCRETE_REPRESENTATION,
        None,
    ),
]


@pytest.mark.parametrize("sentence,expected_act,expected_child", FALLBACK_15_TEST_CASES)
def test_fallback_tag_act_15_sentences(
    sentence: str,
    expected_act: TeachingAct,
    expected_child: str | None,
) -> None:
    res = fallback_tag_act(sentence)
    assert expected_act in res.acts
    assert res.addressed_child == expected_child
    # Validate result passes output guard
    valid, msg = guard_act_tagger(res, sentence, ["ravi", "priya", "aman"])
    assert valid is True, f"Guard failed on fallback output: {msg}"


def test_fallback_tag_act_problem_extraction() -> None:
    sentence = "सब बच्चे 52 में से 17 घटाकर अपनी कॉपी में लिखो।"
    res = fallback_tag_act(sentence)
    assert TeachingAct.GIVE_NEW_PROBLEM in res.acts
    assert res.problem is not None
    assert res.problem.a == 52
    assert res.problem.b == 17
    valid, msg = guard_act_tagger(res, sentence, ["ravi", "priya", "aman"])
    assert valid is True


# ── 3. Golden Fixtures Verification ──────────────────────────────────────────
def test_golden_fixtures_validity() -> None:
    golden_dir = Path(__file__).resolve().parent.parent / "golden" / "act_tagger"
    assert golden_dir.exists(), f"Golden directory not found: {golden_dir}"

    json_files = sorted(golden_dir.glob("*.json"))
    assert len(json_files) >= 8, f"Expected >= 8 golden fixtures, found {len(json_files)}"

    for fixture_path in json_files:
        content = json.loads(fixture_path.read_text(encoding="utf-8"))
        assert content.get("role") == "act_tagger"
        inp = content["input"]
        out = content["output"]

        output_model = ActTaggerOutput.model_validate(out)
        valid, msg = guard_act_tagger(
            output_model,
            inp["transcript"],
            inp["scene_persona_ids"],
        )
        assert valid is True, f"Golden fixture {fixture_path.name} failed guard check: {msg}"


# ── 4. Labelled Evaluation Dataset Verification ──────────────────────────────
def test_labelled_evaluation_dataset() -> None:
    labelled_path = (
        Path(__file__).resolve().parent.parent / "golden" / "act_tagger" / "labelled.jsonl"
    )
    assert labelled_path.exists(), "labelled.jsonl not found"

    lines = [
        line.strip()
        for line in labelled_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 20, f"Expected 20 labelled turns, got {len(lines)}"

    matches = 0
    for line in lines:
        data = json.loads(line)
        transcript = data["transcript"]
        expected_acts = set(data["expected_acts"])
        res = fallback_tag_act(transcript)
        res_acts = {a.value for a in res.acts}

        # Check if the primary expected act is matched
        if expected_acts.intersection(res_acts):
            matches += 1

    accuracy = matches / len(lines)
    assert accuracy >= 0.85, f"Fallback tagger accuracy {accuracy:.2f} < 0.85 on labelled dataset"


# ── 5. tag_act Async Role Contract & Fallback ────────────────────────────────
@pytest.mark.asyncio
async def test_tag_act_fallback_on_client_unavailable() -> None:
    # When call_tool is unconfigured / raises NotImplementedError, tag_act must fallback gracefully
    res = await tag_act(
        transcript="रवि तुमने 52 में से 17 कैसे घटाया? मुझे समझाओ।",
        move_title_hi="हासिल वाला घटाव",
        current_item_text="52 - 17",
        children_list="ravi, priya, aman",
        scene_persona_ids=["ravi", "priya", "aman"],
    )
    assert isinstance(res, ActTaggerOutput)
    assert TeachingAct.ASK_TO_EXPLAIN in res.acts
    assert res.addressed_child == "ravi"
    valid, msg = guard_act_tagger(
        res,
        "रवि तुमने 52 में से 17 कैसे घटाया? मुझे समझाओ।",
        ["ravi", "priya", "aman"],
    )
    assert valid is True


@pytest.mark.asyncio
async def test_tag_act_success_with_mock_call_tool() -> None:
    mock_payload = {
        "acts": ["ask_to_explain"],
        "addressed_child": "ravi",
        "problem": None,
        "quote": "कैसे घटाया",
    }
    with patch("backend.app.llm.roles.act_tagger.call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_payload
        res = await tag_act(
            transcript="रवि तुमने कैसे घटाया?",
            move_title_hi="हासिल वाला घटाव",
            current_item_text="52 - 17",
            children_list="ravi",
            scene_persona_ids=["ravi"],
        )
        assert res.acts == [TeachingAct.ASK_TO_EXPLAIN]
        assert res.addressed_child == "ravi"
        assert res.quote == "कैसे घटाया"
        assert mock_call.call_count == 1


@pytest.mark.asyncio
async def test_tag_act_guard_failure_retry_then_success() -> None:
    # First attempt has hallucinated quote -> guard fails
    bad_payload = {
        "acts": ["ask_to_explain"],
        "addressed_child": "ravi",
        "problem": None,
        "quote": "यह कोट ट्रांसक्रिप्ट में नहीं है",
    }
    good_payload = {
        "acts": ["ask_to_explain"],
        "addressed_child": "ravi",
        "problem": None,
        "quote": "समझाओ",
    }
    with patch("backend.app.llm.roles.act_tagger.call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [bad_payload, good_payload]
        res = await tag_act(
            transcript="रवि मुझे समझाओ।",
            move_title_hi="हासिल वाला घटाव",
            current_item_text="52 - 17",
            children_list="ravi",
            scene_persona_ids=["ravi"],
        )
        assert res.acts == [TeachingAct.ASK_TO_EXPLAIN]
        assert res.quote == "समझाओ"
        assert mock_call.call_count == 2


def test_load_act_examples_nonexistent_and_invalid(tmp_path: Path) -> None:
    with patch("backend.app.llm.roles.act_tagger.Path") as mock_path:
        mock_p = (
            mock_path.return_value.resolve.return_value.parent.parent.parent.parent.parent
            / "content"
            / "act_examples_hi.yaml"
        )
        mock_p.exists.return_value = False
        assert load_act_examples() == []


@pytest.mark.asyncio
async def test_tag_act_missing_prompt_template() -> None:
    with patch("backend.app.llm.roles.act_tagger.Path") as mock_path:
        mock_p = (
            mock_path.return_value.resolve.return_value.parent.parent
            / "prompts"
            / "act_tagger.v1.md"
        )
        mock_p.exists.return_value = False
        res = await tag_act(
            transcript="रवि तुमने कैसे किया?",
            move_title_hi="हासिल घटाव",
            current_item_text="52 - 17",
            children_list="ravi",
            scene_persona_ids=["ravi"],
        )
        assert res.acts == [TeachingAct.ASK_TO_EXPLAIN]


def test_feedback_items_and_evaluator_samples() -> None:
    """Verify all 5 test sentences from user feedback + 5 evaluator samples (items 3-8)."""
    # 1. TELL_ANSWER fallback: stated answer vs question
    # "रवि, सही उत्तर क्या है?" must NOT be tell_answer (expect ask_to_explain or repeat_question)
    res_q = fallback_tag_act("रवि, सही उत्तर क्या है?")
    assert TeachingAct.TELL_ANSWER not in res_q.acts
    assert res_q.addressed_child == "ravi"
    assert any(
        act in res_q.acts for act in (TeachingAct.ASK_TO_EXPLAIN, TeachingAct.REPEAT_QUESTION)
    )

    # "Ravi, answer 16 hai" MUST be tell_answer (evaluator sample s3)
    res_s3_short = fallback_tag_act("Ravi, answer 16 hai")
    assert TeachingAct.TELL_ANSWER in res_s3_short.acts
    assert res_s3_short.addressed_child == "ravi"

    # 2. SCOLD fallback: remove "ध्यान दो"
    # "प्रिया, ध्यान दो, 43 में से 27 कैसे करोगी?" → ask_to_explain (+ give_new_problem), not scold
    res_scold_neutral = fallback_tag_act("प्रिया, ध्यान दो, 43 में से 27 कैसे करोगी?")
    assert TeachingAct.SCOLD not in res_scold_neutral.acts
    assert TeachingAct.ASK_TO_EXPLAIN in res_scold_neutral.acts
    assert res_scold_neutral.addressed_child == "priya"

    # 3. Problem detection in fallback:
    # "अमन, अब 61 में से 28 करो" → problem sub 61/28 + give_new_problem
    res_sub = fallback_tag_act("अमन, अब 61 में से 28 करो")
    assert res_sub.problem is not None
    assert res_sub.problem.type == "sub"
    assert res_sub.problem.a == 61
    assert res_sub.problem.b == 28
    assert TeachingAct.GIVE_NEW_PROBLEM in res_sub.acts
    assert res_sub.addressed_child == "aman"

    # "सब लोग देखो, 38 और 45 जोड़ो" → add 38/45, addressed all
    res_add = fallback_tag_act("सब लोग देखो, 38 और 45 जोड़ो")
    assert res_add.problem is not None
    assert res_add.problem.type == "add"
    assert res_add.problem.a == 38
    assert res_add.problem.b == 45
    assert TeachingAct.GIVE_NEW_PROBLEM in res_add.acts
    assert res_add.addressed_child == "all"

    # Evaluator samples from eval/samples/samples.yaml:
    # s1: "रवि, तुमने 43 में से 27 कैसे घटाया? मुझे एक-एक कदम बताओ।"
    s1_text = "रवि, तुमने 43 में से 27 कैसे घटाया? मुझे एक-एक कदम बताओ।"
    res_s1 = fallback_tag_act(s1_text)
    assert TeachingAct.ASK_TO_EXPLAIN in res_s1.acts
    assert res_s1.addressed_child == "ravi"

    # s2: "सब लोग देखो, ये 4 बंडल और 3 खुली तीलियाँ हैं। 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलते हैं। अब कितनी तीलियाँ हुईं?"
    s2_text = (
        "सब लोग देखो, ये 4 बंडल और 3 खुली तीलियाँ हैं। "
        "3 में से 7 नहीं निकलतीं, तो एक बंडल खोलते हैं। अब कितनी तीलियाँ हुईं?"
    )
    current_item_sub = Problem(type="sub", a=43, b=27)
    res_s2 = fallback_tag_act(s2_text, current_item=current_item_sub)
    assert TeachingAct.CONCRETE_REPRESENTATION in res_s2.acts
    assert res_s2.addressed_child == "all"
    assert res_s2.problem is None

    # s3: "Aman, sahi answer 16 hai, yaad rakho."
    s3_text = "Aman, sahi answer 16 hai, yaad rakho."
    res_s3 = fallback_tag_act(s3_text)
    assert TeachingAct.TELL_ANSWER in res_s3.acts
    assert res_s3.addressed_child == "aman"

    # s4: "इस तरीके में सबसे पहले बच्चे से पूछना है कि उसने कैसे घटाया। फिर दस-दस तीलियों के बंडल से संख्या बनवानी है, और जब इकाई में कम हो तो एक बंडल खोलना है। उत्तर खुद नहीं बताना।"
    s4_text = (
        "इस तरीके में सबसे पहले बच्चे से पूछना है कि उसने कैसे घटाया। "
        "फिर दस-दस तीलियों के बंडल से संख्या बनवानी है, और जब इकाई में कम हो "
        "तो एक बंडल खोलना है। उत्तर खुद नहीं बताना।"
    )
    res_s4 = fallback_tag_act(s4_text)
    assert any(
        act in res_s4.acts
        for act in (TeachingAct.CONCRETE_REPRESENTATION, TeachingAct.ASK_TO_EXPLAIN)
    )

    # s5: "मेरी कक्षा में पहली और दूसरी कक्षा के बच्चे साथ बैठते हैं। हासिल वाला घटाव दोनों को एक साथ कैसे कराऊँ?"
    s5_text = (
        "मेरी कक्षा में पहली और दूसरी कक्षा के बच्चे साथ बैठते हैं। हासिल वाला घटाव दोनों को एक साथ कैसे कराऊँ?"
    )
    res_s5 = fallback_tag_act(s5_text)
    assert TeachingAct.ASK_TO_EXPLAIN in res_s5.acts
