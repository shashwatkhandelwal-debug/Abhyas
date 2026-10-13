"""Place value procedural bug rules matching spec/04 §4.2."""

from typing import Any

from backend.app.rule_engine.bugs.registry import NotApplicable, register_bug
from backend.app.rule_engine.bugs.templates import make_step
from backend.app.rule_engine.domain import BugOutput, Problem


def _unpack_pv(problem: Problem) -> tuple[int, int]:
    """Validates and unpacks a place value problem (tens bundles, ones sticks)."""
    if problem.type != "place_value":
        raise NotApplicable(f"Place value rule not applicable to problem type '{problem.type}'")
    if problem.tens is None or problem.ones is None:
        raise NotApplicable("Place value problem requires 'tens' and 'ones'")
    return problem.tens, problem.ones


def pv_correct(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Correct place value: bundle of 10 tens plus ones (§4.2).

    Examples:
    (4,7) -> 47
    (3,5) -> 35
    (6,2) -> 62
    """
    tens, ones = _unpack_pv(problem)
    tens10 = tens * 10
    ans = int(problem.answer())

    steps = [
        make_step(
            "PV_BUNDLE_TEN",
            nums=[1, 10, tens, tens10],
            tens=tens,
            tens10=tens10,
        ),
        make_step("ANSWER", nums=[ans], answer=ans),
    ]
    return BugOutput(rule_id="CORRECT_PV", answer=ans, steps=steps)


def pv_bundle_as_one(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Misconception: counts each bundle as 1 unit (§4.2).

    Examples:
    (4,7) -> 4 + 7 = 11
    (3,5) -> 3 + 5 = 8
    (6,2) -> 6 + 2 = 8
    """
    tens, ones = _unpack_pv(problem)
    ans = tens + ones

    steps = [
        make_step(
            "PV_COUNT_BUNDLES",
            nums=[tens, ones],
            tens=tens,
            ones=ones,
        ),
        make_step("ANSWER", nums=[ans], answer=ans),
    ]
    return BugOutput(rule_id="PV_BUNDLE_AS_ONE", answer=ans, steps=steps)


def pv_concat_spoken(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Misconception: writes spoken multiple of 10 then appends ones (§4.2).

    Examples:
    (4,7) -> 407 (चालीस और सात -> 407)
    (3,5) -> 305 (तीस और पाँच -> 305)
    (6,2) -> 602 (साठ और दो -> 602)
    """
    tens, ones = _unpack_pv(problem)
    tens10 = tens * 10
    ans = int(f"{tens10}{ones}")

    steps = [
        make_step(
            "PV_BUNDLE_TEN",
            nums=[1, 10, tens, tens10],
            tens=tens,
            tens10=tens10,
        ),
        make_step(
            "PV_CONCAT",
            nums=[tens10, ones, ans],
            tens10=tens10,
            ones=ones,
            answer=ans,
        ),
        make_step("ANSWER", nums=[ans], answer=ans),
    ]
    return BugOutput(rule_id="PV_CONCAT_SPOKEN", answer=ans, steps=steps)


def pv_reversal(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Misconception: writes ones digit first then tens (§4.2).

    Examples:
    (4,7) -> 74
    (3,5) -> 53
    (6,2) -> 26
    """
    tens, ones = _unpack_pv(problem)
    ans = ones * 10 + tens

    steps = [
        make_step(
            "PV_REVERSE",
            nums=[ones, tens],
            ones=ones,
            tens=tens,
        ),
        make_step("ANSWER", nums=[ans], answer=ans),
    ]
    return BugOutput(rule_id="PV_REVERSAL", answer=ans, steps=steps)


# Register place value bugs
register_bug(
    rule_id="PV_BUNDLE_AS_ONE",
    fn=pv_bundle_as_one,
    correct_fn=pv_correct,
    kind="place_value",
    problem_types=["place_value"],
    description_hi="बंडल को 10 न मानकर 1 तीली की तरह गिनना",
    research_ref="ASER / NCERT FLN place-value studies",
)

register_bug(
    rule_id="PV_CONCAT_SPOKEN",
    fn=pv_concat_spoken,
    correct_fn=pv_correct,
    kind="place_value",
    problem_types=["place_value"],
    description_hi="बोली गई संख्या लिखकर इकाई जोड़ देना (40 और 7 -> 407)",
    research_ref="NCERT FLN Sandarshika; ASER",
)

register_bug(
    rule_id="PV_REVERSAL",
    fn=pv_reversal,
    correct_fn=pv_correct,
    kind="place_value",
    problem_types=["place_value"],
    description_hi="इकाई और दहाई के अंकों का स्थान उलट देना (4 और 7 -> 74)",
    research_ref="NCERT FLN Sandarshika",
)
