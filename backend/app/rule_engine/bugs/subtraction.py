"""Subtraction procedural bug rules matching spec/04 §4.2."""

from typing import Any

from backend.app.rule_engine.bugs.registry import NotApplicable, register_bug
from backend.app.rule_engine.bugs.templates import make_step
from backend.app.rule_engine.domain import BugOutput, Problem, Step


def _unpack_sub(problem: Problem) -> tuple[int, int, int, int, int, int]:
    """Validates and unpacks a two-digit subtraction problem."""
    if problem.type != "sub":
        raise NotApplicable(f"Subtraction rule not applicable to problem type '{problem.type}'")
    if problem.a is None or problem.b is None:
        raise NotApplicable("Subtraction problem requires operands 'a' and 'b'")

    a, b = problem.a, problem.b
    t_top, u_top = a // 10, a % 10
    t_bot, u_bot = b // 10, b % 10
    return a, b, t_top, u_top, t_bot, u_bot


def sub_correct(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Correct two-digit subtraction with regrouping (§4.2).

    Examples:
    52-17 -> 35
    43-27 -> 16
    61-28 -> 33
    74-39 -> 35
    """
    a, b, t_top, u_top, t_bot, u_bot = _unpack_sub(problem)
    ans = a - b

    steps: list[Step] = []
    if u_top < u_bot:
        # Regrouping
        u_new = u_top + 10
        t_left = t_top - 1
        d_u = u_new - u_bot
        d_t = t_left - t_bot

        steps.append(make_step("SUB_CANNOT", nums=[u_top, u_bot], u_top=u_top, u_bot=u_bot))
        steps.append(
            make_step(
                "REGROUP_OPEN_BUNDLE",
                nums=[1, u_new, t_left],
                u_new=u_new,
                t_left=t_left,
            )
        )
        steps.append(
            make_step("SUB_TENS", nums=[t_left, t_bot, d_t], t_top=t_left, t_bot=t_bot, d_t=d_t)
        )
    else:
        # No regrouping needed
        d_u = u_top - u_bot
        d_t = t_top - t_bot
        steps.append(
            make_step(
                "SUB_UNITS_NORMAL", nums=[u_top, u_bot, d_u], u_top=u_top, u_bot=u_bot, d_u=d_u
            )
        )
        steps.append(
            make_step("SUB_TENS", nums=[t_top, t_bot, d_t], t_top=t_top, t_bot=t_bot, d_t=d_t)
        )

    steps.append(make_step("ANSWER", nums=[ans], answer=ans))
    return BugOutput(rule_id="CORRECT_SUB", answer=ans, steps=steps)


def sub_smaller_from_larger(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Misconception: each column: larger digit − smaller digit (§4.2).

    Examples:
    52-17 -> 45
    43-27 -> 24
    61-28 -> 47
    74-39 -> 45
    """
    a, b, t_top, u_top, t_bot, u_bot = _unpack_sub(problem)
    if u_top >= u_bot:
        # Bug does not manifest
        return sub_correct(problem, context)

    d_u = u_bot - u_top
    d_t = abs(t_top - t_bot)
    ans = d_t * 10 + d_u

    steps = [
        make_step("SUB_CANNOT", nums=[u_top, u_bot], u_top=u_top, u_bot=u_bot),
        make_step("SUB_SWAP", nums=[u_bot, u_top, d_u], u_bot=u_bot, u_top=u_top, d_u=d_u),
        make_step("SUB_TENS", nums=[t_top, t_bot, d_t], t_top=t_top, t_bot=t_bot, d_t=d_t),
        make_step("ANSWER", nums=[ans], answer=ans),
    ]
    return BugOutput(rule_id="SUB_SMALLER_FROM_LARGER", answer=ans, steps=steps)


def sub_borrow_no_decrement(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Misconception: adds 10 to units, forgets to reduce tens (§4.2).

    Examples:
    52-17 -> 45
    43-27 -> 26
    61-28 -> 43
    74-39 -> 45
    """
    a, b, t_top, u_top, t_bot, u_bot = _unpack_sub(problem)
    if u_top >= u_bot:
        return sub_correct(problem, context)

    u_new = u_top + 10
    d_u = u_new - u_bot
    d_t = t_top - t_bot  # forgets to decrement tens
    ans = d_t * 10 + d_u

    steps = [
        make_step("SUB_CANNOT", nums=[u_top, u_bot], u_top=u_top, u_bot=u_bot),
        make_step(
            "BORROW_NO_DEC",
            nums=[u_top, 1, u_new, u_bot, d_u],
            u_top=u_top,
            u_new=u_new,
            u_bot=u_bot,
            d_u=d_u,
        ),
        make_step("SUB_TENS", nums=[t_top, t_bot, d_t], t_top=t_top, t_bot=t_bot, d_t=d_t),
        make_step("ANSWER", nums=[ans], answer=ans),
    ]
    return BugOutput(rule_id="SUB_BORROW_NO_DECREMENT", answer=ans, steps=steps)


def sub_write_zero_when_stuck(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Misconception: if top units < bottom units, writes 0 in units; tens subtracted normally (§4.2).

    Examples:
    52-17 -> 40
    43-27 -> 20
    61-28 -> 40
    74-39 -> 40
    """
    a, b, t_top, u_top, t_bot, u_bot = _unpack_sub(problem)
    if u_top >= u_bot:
        return sub_correct(problem, context)

    d_u = 0
    d_t = t_top - t_bot
    ans = d_t * 10 + d_u

    steps = [
        make_step("SUB_CANNOT", nums=[u_top, u_bot], u_top=u_top, u_bot=u_bot),
        make_step("WRITE_ZERO", nums=[0]),
        make_step("SUB_TENS", nums=[t_top, t_bot, d_t], t_top=t_top, t_bot=t_bot, d_t=d_t),
        make_step("ANSWER", nums=[ans], answer=ans),
    ]
    return BugOutput(rule_id="SUB_WRITE_ZERO_WHEN_STUCK", answer=ans, steps=steps)


# Register subtraction bugs
register_bug(
    rule_id="SUB_SMALLER_FROM_LARGER",
    fn=sub_smaller_from_larger,
    correct_fn=sub_correct,
    kind="numeracy_sub",
    problem_types=["sub"],
    description_hi="छोटे अंक को बड़े अंक में से घटा देना (उल्टा घटाव)",
    research_ref="Brown & Burton (1978); VanLehn (1990)",
)

register_bug(
    rule_id="SUB_BORROW_NO_DECREMENT",
    fn=sub_borrow_no_decrement,
    correct_fn=sub_correct,
    kind="numeracy_sub",
    problem_types=["sub"],
    description_hi="इकाई में हासिल जोड़ा पर दहाई से 1 घटाना भूल गया",
    research_ref="Brown & Burton (1978); VanLehn (1990)",
)

register_bug(
    rule_id="SUB_WRITE_ZERO_WHEN_STUCK",
    fn=sub_write_zero_when_stuck,
    correct_fn=sub_correct,
    kind="numeracy_sub",
    problem_types=["sub"],
    description_hi="इकाई न घटने पर 0 लिख देना",
    research_ref="VanLehn (1990)",
)
