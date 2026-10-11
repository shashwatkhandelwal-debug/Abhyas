"""Procedural bug rules for maths and literacy errors (§5.2).

Deterministic implementations following Brown & Burton (1978).
"""

from collections.abc import Callable
from typing import Any

from backend.app.rule_engine.bugs import (
    add_no_carry as _bug_add_no_carry,
)
from backend.app.rule_engine.bugs import (
    matra_drop as _bug_matra_drop,
)
from backend.app.rule_engine.bugs import (
    sub_smaller_from_larger as _bug_sub_smaller_from_larger,
)
from backend.app.rule_engine.domain import Problem


def sub_smaller_from_larger(a: int, b: int) -> dict[str, Any]:
    prob = Problem(type="sub", a=a, b=b)
    res = _bug_sub_smaller_from_larger(prob)
    a_units, a_tens = a % 10, (a // 10) % 10
    b_units, b_tens = b % 10, (b // 10) % 10
    res_units = abs(a_units - b_units)
    res_tens = abs(a_tens - b_tens)
    return {
        "rule_id": res.rule_id,
        "answer": res.answer,
        "numbers_involved": [a, b, a_units, b_units, res_units, res_tens, res.answer],
        "reasoning_steps": [s.text_hi for s in res.steps],
        "explanation_hi": f"{a_units} mein se {b_units} nahi hota, to {b_units} mein se {a_units} kiya. {res.answer}!",
    }


def add_no_carry(a: int, b: int) -> dict[str, Any]:
    prob = Problem(type="add", a=a, b=b)
    res = _bug_add_no_carry(prob)
    a_units, a_tens = a % 10, (a // 10) % 10
    b_units, b_tens = b % 10, (b // 10) % 10
    return {
        "rule_id": res.rule_id,
        "answer": res.answer,
        "numbers_involved": [a, b, a_units + b_units, a_tens + b_tens, res.answer],
        "reasoning_steps": [s.text_hi for s in res.steps],
        "explanation_hi": f"{a_units} aur {b_units} joda, {res.answer}!",
    }


def matra_drop(word: str) -> dict[str, Any]:
    prob = Problem(type="read_word", word=word)
    res = _bug_matra_drop(prob)
    return {
        "rule_id": res.rule_id,
        "answer": res.answer,
        "numbers_involved": [],
        "reasoning_steps": [s.text_hi for s in res.steps],
        "explanation_hi": f"Yeh matra bina {res.answer} hai",
    }


MISCONCEPTION_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {
    "SUB_SMALLER_FROM_LARGER": sub_smaller_from_larger,
    "ADD_NO_CARRY": add_no_carry,
    "MATRA_DROP": matra_drop,
}
