"""Registry of procedural bug rules matching spec/04 §4.2."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from backend.app.rule_engine.domain import BugOutput, Problem


class NotApplicable(ValueError):
    """Raised when a bug rule is called on an incompatible problem type."""

    pass


@dataclass(frozen=True)
class RuleInfo:
    """Metadata and execution bindings for a procedural bug rule."""

    rule_id: str
    fn: Callable[[Problem, dict[str, Any] | None], BugOutput]
    correct_fn: Callable[[Problem, dict[str, Any] | None], BugOutput]
    kind: str  # "numeracy_sub", "numeracy_add", "place_value", "literacy"
    problem_types: list[str]  # ["sub"], ["add"], ["place_value"], ["read_word"]
    description_hi: str
    research_ref: str


BUG_REGISTRY: dict[str, RuleInfo] = {}


def register_bug(
    rule_id: str,
    fn: Callable[[Problem, dict[str, Any] | None], BugOutput],
    correct_fn: Callable[[Problem, dict[str, Any] | None], BugOutput],
    kind: str,
    problem_types: list[str],
    description_hi: str,
    research_ref: str,
) -> None:
    """Registers a bug rule in the global bug registry."""
    BUG_REGISTRY[rule_id] = RuleInfo(
        rule_id=rule_id,
        fn=fn,
        correct_fn=correct_fn,
        kind=kind,
        problem_types=problem_types,
        description_hi=description_hi,
        research_ref=research_ref,
    )


def get_rule_info(rule_id: str) -> RuleInfo:
    """Retrieves RuleInfo for given rule_id, raising KeyError if not found."""
    if rule_id not in BUG_REGISTRY:
        raise KeyError(f"Unknown bug rule id: '{rule_id}'")
    return BUG_REGISTRY[rule_id]
