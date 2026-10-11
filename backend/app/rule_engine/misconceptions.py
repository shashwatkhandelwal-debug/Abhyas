"""Procedural bug rules for maths and literacy errors (§5.2).

Deterministic implementations following Brown & Burton (1978).
"""

from collections.abc import Callable
from typing import Any


def sub_smaller_from_larger(a: int, b: int) -> dict[str, Any]:
    """Misconception: When top digit is smaller than bottom digit, subtract smaller from larger.

    Example: 52 - 17
    Units: 2 < 7 -> child does 7 - 2 = 5
    Tens: 5 - 1 = 4
    Result: 45
    Reasoning steps: ["2 mein se 7 nahi hota", "7 mein se 2 kiya = 5", "5 mein se 1 gaya = 4"]
    """
    a_units = a % 10
    a_tens = (a // 10) % 10
    b_units = b % 10
    b_tens = (b // 10) % 10

    res_units = abs(a_units - b_units)
    res_tens = abs(a_tens - b_tens)
    result = res_tens * 10 + res_units

    return {
        "rule_id": "SUB_SMALLER_FROM_LARGER",
        "answer": result,
        "numbers_involved": [a, b, a_units, b_units, res_units, res_tens, result],
        "reasoning_steps": [
            f"{a_units} mein se {b_units} nahi ghat-ta",
            f"{b_units} mein se {a_units} ghata kar {res_units} likha",
            f"{a_tens} mein se {b_tens} gaya to {res_tens} bacha",
        ],
        "explanation_hi": f"{a_units} mein se {b_units} nahi hota, to {b_units} mein se {a_units} kiya. {result}!",
    }


def add_no_carry(a: int, b: int) -> dict[str, Any]:
    """Misconception: Writes the full sum of digits side-by-side without regrouping.

    Example: 28 + 15 -> 8+5=13, 2+1=3 -> 313
    """
    a_units = a % 10
    a_tens = (a // 10) % 10
    b_units = b % 10
    b_tens = (b // 10) % 10

    unit_sum = a_units + b_units
    tens_sum = a_tens + b_tens
    result_str = f"{tens_sum}{unit_sum}"
    result = int(result_str)

    return {
        "rule_id": "ADD_NO_CARRY",
        "answer": result,
        "numbers_involved": [a, b, unit_sum, tens_sum, result],
        "reasoning_steps": [
            f"{a_units} aur {b_units} mila kar {unit_sum}",
            f"{a_tens} aur {b_tens} mila kar {tens_sum}",
        ],
        "explanation_hi": f"{a_units} aur {b_units} joda to {unit_sum}, aur {a_tens} aur {b_tens} joda to {tens_sum}. {result}!",
    }


def matra_drop(word: str) -> dict[str, Any]:
    """Literacy bug: Drops vowel signs (matras), reading only root consonants."""
    matras = ["ा", "ि", "ी", "ु", "ू", "े", "ै", "ो", "ौ", "ं", "ः"]
    clean_word = "".join(ch for ch in word if ch not in matras)
    return {
        "rule_id": "MATRA_DROP",
        "answer": clean_word,
        "numbers_involved": [],
        "reasoning_steps": ["matra chhod di", "keval akshar padha"],
        "explanation_hi": f"Yeh matra bina {clean_word} hai",
    }


# Misconception registry
MISCONCEPTION_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {
    "SUB_SMALLER_FROM_LARGER": sub_smaller_from_larger,
    "ADD_NO_CARRY": add_no_carry,
    "MATRA_DROP": matra_drop,
}
