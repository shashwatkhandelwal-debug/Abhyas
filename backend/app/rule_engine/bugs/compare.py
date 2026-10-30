"""Comparing two-digit numbers: the "ones first" procedural bug (Track B scene NUM_COMPARE).

The child looks at the ones digits first and calls the number with the bigger ones digit the
bigger number (39 against 41: 9 is more than 1, so 39). The correct method compares the tens
(bundles) first and looks at the ones only when the tens are equal.
"""

from typing import Any

from backend.app.rule_engine.bugs.registry import NotApplicable, register_bug
from backend.app.rule_engine.bugs.templates import make_step
from backend.app.rule_engine.domain import BugOutput, Problem, Step


def _unpack_compare(problem: Problem) -> tuple[int, int]:
    if problem.type != "compare":
        raise NotApplicable(f"Comparison rule not applicable to problem type '{problem.type}'")
    if problem.a is None or problem.b is None:
        raise NotApplicable("Comparison problem requires operands 'a' and 'b'")
    return problem.a, problem.b


def cmp_correct(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Tens (bundles) first; the ones only when the tens are equal.

    Examples:
    39 vs 41 -> 41
    52 vs 57 -> 57
    7 vs 41 -> 41
    """
    a, b = _unpack_compare(problem)
    ans = max(a, b)
    t_a, t_b, u_a, u_b = a // 10, b // 10, a % 10, b % 10
    steps: list[Step] = []
    if a == b:
        steps.append(make_step("CMP_EQUAL", nums=[a], a=a))
    elif t_a != t_b:
        t_big = max(t_a, t_b)
        steps.append(
            make_step(
                "CMP_TENS_FIRST",
                nums=[t_a, t_b, t_big, ans],
                t_a=t_a,
                t_b=t_b,
                t_big=t_big,
                big=ans,
            )
        )
    else:
        u_big = max(u_a, u_b)
        steps.append(make_step("CMP_TENS_SAME", nums=[t_a], t=t_a))
        steps.append(
            make_step(
                "CMP_ONES_AFTER",
                nums=[u_a, u_b, u_big, ans],
                u_a=u_a,
                u_b=u_b,
                u_big=u_big,
                big=ans,
            )
        )
    steps.append(make_step("ANSWER", nums=[ans], answer=ans))
    return BugOutput(rule_id="CORRECT_CMP", answer=ans, steps=steps)


def cmp_ones_first(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Misconception: the bigger ones digit makes the bigger number.

    Manifests whenever the ones digits differ and point at the smaller number. Otherwise (equal
    numbers, equal ones, or ones that happen to agree with the tens) the answer is the correct one.

    Examples:
    39 vs 41 -> 39
    28 vs 33 -> 28
    7 vs 41 -> 7
    42 vs 47 -> 47 (the bug does not show)
    """
    a, b = _unpack_compare(problem)
    u_a, u_b = a % 10, b % 10
    if a == b or u_a == u_b:
        return cmp_correct(problem, context)
    ans = a if u_a > u_b else b
    if ans == max(a, b):
        return cmp_correct(problem, context)
    steps = [
        make_step(
            "CMP_ONES_FIRST",
            nums=[u_a, u_b, max(u_a, u_b), ans],
            u_a=u_a,
            u_b=u_b,
            u_big=max(u_a, u_b),
            big=ans,
        ),
        make_step("ANSWER", nums=[ans], answer=ans),
    ]
    return BugOutput(rule_id="CMP_ONES_FIRST", answer=ans, steps=steps)


register_bug(
    rule_id="CMP_ONES_FIRST",
    fn=cmp_ones_first,
    correct_fn=cmp_correct,
    kind="numeracy_cmp",
    problem_types=["compare"],
    description_hi="पहले इकाई देखकर बड़ी संख्या तय करना (दहाई नहीं देखना)",
    research_ref="Brown & Burton (1978): procedural bug; place-value comparison literature",
)
