"""Addition procedural bug rules matching spec/04 §4.2."""

from typing import Any

from backend.app.rule_engine.bugs.registry import NotApplicable, register_bug
from backend.app.rule_engine.bugs.templates import make_step
from backend.app.rule_engine.domain import BugOutput, Problem


def _unpack_add(problem: Problem) -> tuple[int, int, int, int, int, int]:
    """Validates and unpacks a two-digit addition problem."""
    if problem.type != "add":
        raise NotApplicable(f"Addition rule not applicable to problem type '{problem.type}'")
    if problem.a is None or problem.b is None:
        raise NotApplicable("Addition problem requires operands 'a' and 'b'")

    a, b = problem.a, problem.b
    ta, ua = a // 10, a % 10
    tb, ub = b // 10, b % 10
    return a, b, ta, ua, tb, ub


def add_correct(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Correct two-digit addition with carry regrouping (§4.2).

    Examples:
    38+45 -> 83
    27+48 -> 75
    56+29 -> 85
    """
    a, b, ta, ua, tb, ub = _unpack_add(problem)
    s = ua + ub
    s_u = s % 10
    carry = s // 10
    t = ta + tb + carry
    ans = int(problem.answer())

    steps = [
        make_step("ADD_UNITS", nums=[ua, ub, s], ua=ua, ub=ub, s=s),
    ]
    if carry > 0:
        steps.append(make_step("ADD_CARRY", nums=[s_u, 1], s_u=s_u))
        carry_txt = " और 1 हासिल"
    else:
        carry_txt = ""

    steps.append(
        make_step(
            "ADD_TENS",
            nums=[ta, tb, t] + ([1] if carry > 0 else []),
            ta=ta,
            tb=tb,
            carry_txt=carry_txt,
            t=t,
        )
    )
    steps.append(make_step("ANSWER", nums=[ans], answer=ans))
    return BugOutput(rule_id="CORRECT_ADD", answer=ans, steps=steps)


def add_no_carry(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Misconception: writes the full units sum, then tens sum to its left (§4.2).

    Examples:
    38+45 -> 713
    27+48 -> 615
    56+29 -> 715
    """
    a, b, ta, ua, tb, ub = _unpack_add(problem)
    s = ua + ub
    if s < 10:
        return add_correct(problem, context)

    t = ta + tb
    ans = int(f"{t}{s}")

    steps = [
        make_step("ADD_UNITS", nums=[ua, ub, s], ua=ua, ub=ub, s=s),
        make_step("ADD_WRITE_ALL", nums=[s], s=s),
        make_step("ADD_TENS", nums=[ta, tb, t], ta=ta, tb=tb, carry_txt="", t=t),
        make_step("ANSWER", nums=[ans], answer=ans),
    ]
    return BugOutput(rule_id="ADD_NO_CARRY", answer=ans, steps=steps)


def add_carry_forgotten(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Misconception: writes units digit, drops the carry (§4.2).

    Examples:
    38+45 -> 73
    27+48 -> 65
    56+29 -> 75
    """
    a, b, ta, ua, tb, ub = _unpack_add(problem)
    s = ua + ub
    if s < 10:
        return add_correct(problem, context)

    s_u = s % 10
    t = ta + tb  # drops carry!
    ans = t * 10 + s_u

    steps = [
        make_step("ADD_UNITS", nums=[ua, ub, s], ua=ua, ub=ub, s=s),
        make_step("ADD_DROP_CARRY", nums=[s, s_u], s=s, s_u=s_u),
        make_step("ADD_TENS", nums=[ta, tb, t], ta=ta, tb=tb, carry_txt="", t=t),
        make_step("ANSWER", nums=[ans], answer=ans),
    ]
    return BugOutput(rule_id="ADD_CARRY_FORGOTTEN", answer=ans, steps=steps)


def add_carry_wrong_digit(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Misconception: writes tens digit of units sum, carries units digit (§4.2).

    s = ua+ub >= 10 -> write s // 10, carry s % 10 -> tens = ta+tb+(s%10) -> answer = tens*10 + s//10.
    Examples:
    38+45: s=13 -> write 1, carry 3 -> 3+4+3=10 -> 101
    27+48: s=15 -> write 1, carry 5 -> 2+4+5=11 -> 111
    56+29: s=15 -> write 1, carry 5 -> 5+2+5=12 -> 121
    """
    a, b, ta, ua, tb, ub = _unpack_add(problem)
    s = ua + ub
    if s < 10:
        return add_correct(problem, context)

    s_t = s // 10
    s_u = s % 10
    t = ta + tb + s_u
    ans = t * 10 + s_t

    steps = [
        make_step("ADD_UNITS", nums=[ua, ub, s], ua=ua, ub=ub, s=s),
        make_step("ADD_WRONG_CARRY", nums=[s_t, s_u], s_t=s_t, s_u=s_u),
        make_step(
            "ADD_TENS",
            nums=[ta, tb, s_u, t],
            ta=ta,
            tb=tb,
            carry_txt=f" और {s_u} हासिल",
            t=t,
        ),
        make_step("ANSWER", nums=[ans], answer=ans),
    ]
    return BugOutput(rule_id="ADD_CARRY_WRONG_DIGIT", answer=ans, steps=steps)


# Register addition bugs
register_bug(
    rule_id="ADD_NO_CARRY",
    fn=add_no_carry,
    correct_fn=add_correct,
    kind="numeracy_add",
    problem_types=["add"],
    description_hi="इकाई का पूरा जोड़ नीचे लिखकर दहाई बगल में लिख देना",
    research_ref="VanLehn (1990)",
)

register_bug(
    rule_id="ADD_CARRY_FORGOTTEN",
    fn=add_carry_forgotten,
    correct_fn=add_correct,
    kind="numeracy_add",
    problem_types=["add"],
    description_hi="इकाई का जोड़ लिखकर हासिल जोड़ना भूल जाना",
    research_ref="Brown & Burton (1978); VanLehn (1990)",
)

register_bug(
    rule_id="ADD_CARRY_WRONG_DIGIT",
    fn=add_carry_wrong_digit,
    correct_fn=add_correct,
    kind="numeracy_add",
    problem_types=["add"],
    description_hi="इकाई के जोड़ की दहाई नीचे लिखकर इकाई को हासिल लगाना (उल्टा हासिल)",
    research_ref="Brown & Burton (1978)",
)
