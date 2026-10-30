"""Procedural bug rules package exports matching spec/04 §4.2."""

from backend.app.rule_engine.bugs.addition import (
    add_carry_forgotten,
    add_carry_wrong_digit,
    add_correct,
    add_no_carry,
)
from backend.app.rule_engine.bugs.akshar import (
    join_akshars,
    split_akshars,
    strip_matras,
)
from backend.app.rule_engine.bugs.compare import cmp_correct, cmp_ones_first
from backend.app.rule_engine.bugs.letter_sound import letter_name_for_sound
from backend.app.rule_engine.bugs.literacy import (
    akshar_by_akshar,
    first_akshar_guess,
    matra_drop,
    read_correct,
)
from backend.app.rule_engine.bugs.place_value import (
    pv_bundle_as_one,
    pv_concat_spoken,
    pv_correct,
    pv_reversal,
)
from backend.app.rule_engine.bugs.registry import (
    BUG_REGISTRY,
    NotApplicable,
    RuleInfo,
    get_rule_info,
    register_bug,
)
from backend.app.rule_engine.bugs.subtraction import (
    sub_borrow_no_decrement,
    sub_correct,
    sub_smaller_from_larger,
    sub_write_zero_when_stuck,
)
from backend.app.rule_engine.bugs.templates import (
    STEP_TEMPLATES,
    make_step,
)

__all__ = [
    # Subtraction
    "sub_correct",
    "sub_smaller_from_larger",
    "sub_borrow_no_decrement",
    "sub_write_zero_when_stuck",
    # Addition
    "add_correct",
    "add_no_carry",
    "add_carry_forgotten",
    "add_carry_wrong_digit",
    # Place Value
    "pv_correct",
    "pv_bundle_as_one",
    "pv_concat_spoken",
    "pv_reversal",
    # Comparing numbers
    "cmp_correct",
    "cmp_ones_first",
    # Literacy
    "letter_name_for_sound",
    "read_correct",
    "matra_drop",
    "first_akshar_guess",
    "akshar_by_akshar",
    # Akshar utils
    "split_akshars",
    "join_akshars",
    "strip_matras",
    # Registry & Exceptions
    "BUG_REGISTRY",
    "RuleInfo",
    "get_rule_info",
    "register_bug",
    "NotApplicable",
    # Templates
    "STEP_TEMPLATES",
    "make_step",
]
