"""Act Tagger role implementation matching spec/05 §5.4.

Tags teaching acts in teacher turns using Claude fast model (or MockLLM)
with a deterministic, rule_engine-independent keyword fallback.
"""

import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from backend.app.config import settings
from backend.app.llm.client import LLMUnavailable, call_tool
from backend.app.llm.guards import guard_act_tagger
from backend.app.llm.hindi_numbers import extract_numbers
from backend.app.llm.schemas import ActTaggerOutput
from backend.app.rule_engine.domain import Problem, TeachingAct

logger = logging.getLogger("abhyas.llm.act_tagger")

PROMPT_VERSION = "act_tagger.v1"

# Regex rules for deterministic keyword fallback (§5.4)
FALLBACK_PATTERNS: list[tuple[re.Pattern[str], TeachingAct]] = [
    (
        re.compile(r"क्यों|कैसे|बताओ|समझाओ|\bhow\b|\bwhy\b|\bexplain\b", re.IGNORECASE),
        TeachingAct.ASK_TO_EXPLAIN,
    ),
    (
        re.compile(
            r"बंडल|तीली|तीलियाँ|तीलियों|गड्डी|कंकड़|\bbundle\b|\bstick\b|गिनकर",
            re.IGNORECASE,
        ),
        TeachingAct.CONCRETE_REPRESENTATION,
    ),
    (
        re.compile(
            r"सही उत्तर|\banswer is\b|उत्तर \d+ है|उत्तर है",
            re.IGNORECASE,
        ),
        TeachingAct.TELL_ANSWER,
    ),
    (
        re.compile(
            r"शाबाश .* कोशिश|बहुत अच्छा कोशिश|अच्छी कोशिश|\bgood try\b|अच्छा सोचा|मेहनत अच्छी|तरीका अच्छा",
            re.IGNORECASE,
        ),
        TeachingAct.PRAISE_EFFORT,
    ),
    (
        re.compile(r"चुप|ध्यान दो|गलत है ना|इतना भी नहीं आता|चुपचाप", re.IGNORECASE),
        TeachingAct.SCOLD,
    ),
    (
        re.compile(r"ध्वनि|आवाज़ निकालो|अ-क्ष-र|अक्षर|मात्रा|मिलाकर पढ़ो", re.IGNORECASE),
        TeachingAct.PHONICS_SOUND_OUT,
    ),
    (
        re.compile(r"दोनों उत्तर|किसका सही|तुलना", re.IGNORECASE),
        TeachingAct.CONTRAST_TWO_ANSWERS,
    ),
    (
        re.compile(r"धीरे-धीरे करके देखो|मैं करके दिखाती|देखो मैं|मैं बताती", re.IGNORECASE),
        TeachingAct.MODEL_STEP_ALOUD,
    ),
    (
        re.compile(r"छोटी संख्या|पहले\s*\d+|पहले\s*[०-९]+|पहले\s*छोटी", re.IGNORECASE),
        TeachingAct.PROBE_SIMPLER_CASE,
    ),
    (
        re.compile(r"मदद करो|तुम समझाओ|आपस में", re.IGNORECASE),
        TeachingAct.INVOLVE_PEER,
    ),
    (
        re.compile(r"शाबाश|वेरी गुड|बहुत बढ़िया|बहुत अच्छा", re.IGNORECASE),
        TeachingAct.PRAISE_GENERIC,
    ),
    (
        re.compile(r"बारिश|घंटी|फीस|आधार कार्ड|बाहर देखो", re.IGNORECASE),
        TeachingAct.OFF_TASK,
    ),
    (
        re.compile(r"अगला सवाल|नया सवाल|स्लेट पर", re.IGNORECASE),
        TeachingAct.GIVE_NEW_PROBLEM,
    ),
]

NAME_TO_PERSONA_ID: dict[str, str] = {
    "रवि": "ravi",
    "ravi": "ravi",
    "प्रिया": "priya",
    "priya": "priya",
    "अमन": "aman",
    "aman": "aman",
}


def load_act_examples() -> list[dict[str, Any]]:
    """Loads worked examples from content/act_examples_hi.yaml."""
    base_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
    examples_path = base_dir / "content" / "act_examples_hi.yaml"
    if not examples_path.exists():
        return []
    with open(examples_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
        if isinstance(data, list):
            return data
    return []


def format_act_examples_block(examples: Sequence[dict[str, Any]]) -> str:
    """Formats act examples into a readable block for prompt injection."""
    blocks: list[str] = []
    for ex in examples:
        act = ex.get("act", "")
        line = ex.get("teacher_line_hi", "")
        quote = ex.get("quote", "")
        child = ex.get("addressed_child") or "null"
        blocks.append(
            f'- Teacher: "{line}"\n'
            f'  Output: acts=["{act}"], addressed_child="{child}", quote="{quote}"'
        )
    return "\n".join(blocks)


def fallback_tag_act(
    transcript: str,
    scene_persona_ids: list[str] | None = None,
    current_item: Problem | None = None,
) -> ActTaggerOutput:
    """Rule-engine-independent keyword fallback tagger (spec/05 §5.4).

    Runs regular expressions over normalized transcript to detect acts,
    identifies addressed children, extracts new problems if posed,
    and returns a guaranteed valid ActTaggerOutput.
    """
    clean_text = transcript.strip()

    # 1. Detect acts
    acts: list[TeachingAct] = []
    matched_quote: str = ""

    for pattern, act in FALLBACK_PATTERNS:
        match = pattern.search(clean_text)
        if match:
            if act not in acts:
                acts.append(act)
                if not matched_quote:
                    matched_quote = match.group(0)

    # Check for new problem posed via numbers
    nums = extract_numbers(clean_text)
    problem: Problem | None = None
    if len(nums) >= 2 and any(k in clean_text for k in ["घटा", "कम", "माइनस"]):
        problem = Problem(type="sub", a=nums[0], b=nums[1])
        if TeachingAct.GIVE_NEW_PROBLEM not in acts:
            acts.append(TeachingAct.GIVE_NEW_PROBLEM)
            if not matched_quote:
                matched_quote = clean_text[:40]

    # If no act matched, default to repeat_question per spec
    if not acts:
        acts.append(TeachingAct.REPEAT_QUESTION)
        matched_quote = clean_text[:30]

    # Max 4 acts
    acts = acts[:4]

    # 2. Addressed child
    addressed_child: str | None = None
    if any(
        k in clean_text
        for k in ["बच्चों", "सब बच्चे", "सब लोग", "सभी बच्चे", "तुम दोनों", "दोनों बच्चे", "all"]
    ):
        addressed_child = "all"
    else:
        # Check against persona IDs and names in order of appearance
        valid_ids = scene_persona_ids or ["ravi", "priya", "aman"]
        found_children: list[tuple[int, str]] = []
        for name_token, persona_id in NAME_TO_PERSONA_ID.items():
            idx = clean_text.lower().find(name_token)
            if idx != -1 and persona_id in valid_ids:
                found_children.append((idx, persona_id))
        if found_children:
            found_children.sort(key=lambda x: x[0])
            addressed_child = found_children[0][1]

    # 3. Quote must be a substring of transcript
    quote = matched_quote if matched_quote in clean_text else ""

    return ActTaggerOutput(
        acts=acts,
        addressed_child=addressed_child,
        problem=problem,
        quote=quote,
    )


async def tag_act(
    transcript: str,
    move_title_hi: str,
    current_item_text: str,
    children_list: str,
    scene_persona_ids: list[str],
    current_item: Problem | None = None,
) -> ActTaggerOutput:
    """Invokes Claude fast model to tag teacher turn acts, with guard and fallback.

    Strictly implements spec/05 §5.2 role contract pattern:
    build_input -> call_tool -> validate -> guard -> retry once on error -> fallback.
    """
    # 1. Build prompt
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / f"{PROMPT_VERSION}.md"
    if prompt_path.exists():
        system_template = prompt_path.read_text(encoding="utf-8")
    else:
        system_template = "You label teacher acts. Return tool call."

    examples = load_act_examples()
    examples_block = format_act_examples_block(examples[:28])

    system_prompt = system_template.format(
        move_title_hi=move_title_hi,
        current_item_text=current_item_text,
        children_list=children_list,
        act_examples_block=examples_block,
    )

    user_message = f'Teacher turn transcript:\n"""{transcript}"""'
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    # 2. Attempt LLM call with retry per §5.2
    for attempt in range(2):
        try:
            tool_input = await call_tool(
                role="act_tagger",
                model=settings.CLAUDE_MODEL_FAST,
                system=system_prompt,
                messages=messages,
                tool_name="tag_acts",
                input_schema=ActTaggerOutput.model_json_schema(),
                temperature=0.0,
                max_tokens=256,
                timeout_s=settings.LLM_TIMEOUT_SECONDS,
            )

            parsed = ActTaggerOutput.model_validate(tool_input)
            is_valid, err_msg = guard_act_tagger(parsed, transcript, scene_persona_ids)
            if is_valid:
                return parsed

            logger.warning("act_tagger guard failed (attempt %d): %s", attempt + 1, err_msg)
            if attempt == 0:
                messages.append(
                    {
                        "role": "user",
                        "content": f"Your previous output failed guard check: {err_msg}. Fix it and try again.",
                    }
                )
        except (LLMUnavailable, NotImplementedError, Exception) as exc:
            logger.warning("act_tagger LLM call failed (attempt %d): %s", attempt + 1, exc)
            if attempt == 1:
                break

    # 3. Deterministic fallback
    logger.info("Using keyword fallback tagger for teacher turn")
    return fallback_tag_act(
        transcript=transcript,
        scene_persona_ids=scene_persona_ids,
        current_item=current_item,
    )
