"""Math procedural bug functions (§5.2, §10)."""

from typing import Any


def bug_sub_smaller_from_larger(top: int, bottom: int) -> dict[str, Any]:
    """When top digit is smaller than bottom digit, subtracts top from bottom.
    
    Example: 52 - 17 -> |2-7|=5, 5-1=4 -> 45
    """
    top_u, top_t = top % 10, (top // 10) % 10
    bot_u, bot_t = bottom % 10, (bottom // 10) % 10

    diff_u = abs(top_u - bot_u)
    diff_t = abs(top_t - bot_t)
    res = diff_t * 10 + diff_u

    return {
        "rule_id": "SUB_SMALLER_FROM_LARGER",
        "answer": res,
        "tokens": [top, bottom, top_u, bot_u, diff_u, diff_t, res],
        "explanation": f"{top_u} mein se {bot_u} nahi ghatata, to {bot_u} mein se {top_u} kiya.",
    }


def bug_add_no_carry(a: int, b: int) -> dict[str, Any]:
    """Writes side-by-side digit sums without regrouping."""
    a_u, a_t = a % 10, (a // 10) % 10
    b_u, b_t = b % 10, (b // 10) % 10

    sum_u = a_u + b_u
    sum_t = a_t + b_t
    res = int(f"{sum_t}{sum_u}")

    return {
        "rule_id": "ADD_NO_CARRY",
        "answer": res,
        "tokens": [a, b, sum_u, sum_t, res],
        "explanation": f"{a_u}+{b_u}={sum_u} aur {a_t}+{b_t}={sum_t}.",
    }
