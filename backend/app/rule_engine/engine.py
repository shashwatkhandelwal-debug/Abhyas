"""Pure Python deterministic rule engine (§5.1, §5.2).

Computes child answers, explanations, state changes, and affect.
Does NOT rely on LLM for mathematical logic or misconception rules.
"""

from typing import Any

from backend.app.rule_engine.child_state import TRANSITIONS, ChildState
from backend.app.rule_engine.domain import (
    Move,
    Persona,
    SceneState,
    StepResult,
    TaggedTurn,
    TeachingAct,
)
from backend.app.rule_engine.misconceptions import MISCONCEPTION_REGISTRY


class RuleEngineResult:
    def __init__(
        self,
        child_id: str,
        child_name: str,
        answer: Any,
        reasoning_steps: list[str],
        prior_state: ChildState,
        new_state: ChildState,
        affect: str,
        explanation_hint_hi: str,
        numbers_involved: list[Any],
        is_parrot: bool = False,
    ):
        self.child_id = child_id
        self.child_name = child_name
        self.answer = answer
        self.reasoning_steps = reasoning_steps
        self.prior_state = prior_state
        self.new_state = new_state
        self.affect = affect
        self.explanation_hint_hi = explanation_hint_hi
        self.numbers_involved = numbers_involved
        self.is_parrot = is_parrot

    def to_dict(self) -> dict[str, Any]:
        return {
            "child_id": self.child_id,
            "child_name": self.child_name,
            "answer": self.answer,
            "reasoning_steps": self.reasoning_steps,
            "prior_state": self.prior_state.name,
            "new_state": self.new_state.name,
            "affect": self.affect,
            "explanation_hint_hi": self.explanation_hint_hi,
            "numbers_involved": self.numbers_involved,
            "is_parrot": self.is_parrot,
        }


class RehearsalRuleEngine:
    def __init__(self, move: Move):
        self.move = move

    def evaluate_turn(
        self,
        child: Persona,
        current_state: ChildState,
        acts: list[TeachingAct],
        problem_args: tuple[Any, ...],
        correct_answer: Any,
        has_relapsed: bool = False,
    ) -> RuleEngineResult:
        """Evaluates a teacher turn deterministically against a child's misconception state."""
        # Check primary misconception
        primary_bug_id = child.misconceptions[0] if child.misconceptions else None
        is_target_misconception = primary_bug_id in self.move.target_causes

        # Determine state transition
        new_state = current_state
        affect = "neutral"

        act_strs = [a.value for a in acts]

        # Handle scolding affect
        if TeachingAct.SCOLD.value in act_strs:
            if child.temperament == "shy":
                affect = "silent_shy"
            else:
                affect = "confused"

        # Handle 'tell_answer' act -> PARROT behavior
        if TeachingAct.TELL_ANSWER.value in act_strs:
            return RuleEngineResult(
                child_id=child.id,
                child_name=child.name,
                answer=correct_answer,
                reasoning_steps=["teacher_told_answer"],
                prior_state=current_state,
                new_state=current_state,  # State does not truly advance
                affect="echo",
                explanation_hint_hi=f"Haan ji, {correct_answer}!",
                numbers_involved=[correct_answer],
                is_parrot=True,
            )

        # Evaluate pedagogical acts
        if is_target_misconception:
            for act_str in act_strs:
                if act_str in self.move.teaching_acts_effective:
                    transition_rule = TRANSITIONS.get(act_str)
                    if isinstance(transition_rule, dict):
                        if current_state in transition_rule:
                            new_state = transition_rule[current_state]
                            break

        # Generate rule-based answer & reasoning
        bug_fn = MISCONCEPTION_REGISTRY.get(primary_bug_id) if primary_bug_id else None

        if new_state == ChildState.CORRECT:
            answer = correct_answer
            reasoning_steps = ["understood_concept", "applied_scaffolding"]
            explanation_hint_hi = f"Ab samajh aaya! Uttar {correct_answer} hoga."
            numbers = [correct_answer]
            affect = "confident"
        elif new_state == ChildState.PARTIAL:
            # Partial understanding: correct on current scaffold, reveals intermediate progress
            answer = correct_answer
            reasoning_steps = ["assisted_with_concrete_bundles", "partial_breakdown"]
            explanation_hint_hi = f"Bundles gin kar dekha to {correct_answer} aaya."
            numbers = [correct_answer]
            affect = "tentative"
        elif new_state == ChildState.CAN_EXPLAIN:
            # Reveals the bug reasoning explicitly
            if bug_fn:
                bug_data = bug_fn(*problem_args)
                answer = bug_data["answer"]
                reasoning_steps = bug_data["reasoning_steps"]
                explanation_hint_hi = bug_data["explanation_hi"]
                numbers = bug_data["numbers_involved"]
            else:
                answer = "galat_uttar"
                reasoning_steps = ["misconception_unspecified"]
                explanation_hint_hi = "Maine aise socha tha."
                numbers = []
            affect = "explaining"
        else:  # MISCONCEPTION
            if bug_fn:
                bug_data = bug_fn(*problem_args)
                answer = bug_data["answer"]
                reasoning_steps = ["confident_misapplication"]
                explanation_hint_hi = f"Mera uttar {answer} hai!"
                numbers = bug_data["numbers_involved"]
            else:
                answer = "galat_uttar"
                reasoning_steps = ["confident_error"]
                explanation_hint_hi = "Mera uttar aa gaya."
                numbers = []
            affect = "confident"

        return RuleEngineResult(
            child_id=child.id,
            child_name=child.name,
            answer=answer,
            reasoning_steps=reasoning_steps,
            prior_state=current_state,
            new_state=new_state,
            affect=affect,
            explanation_hint_hi=explanation_hint_hi,
            numbers_involved=numbers,
            is_parrot=False,
        )


class RuleEngine:
    """Deterministic rule engine for interactive rehearsal scenes (spec/04 §4.4)."""

    def __init__(self, move: Move | None = None) -> None:
        self.move = move

    @staticmethod
    def step(scene: "SceneState", tagged: "TaggedTurn") -> "StepResult":
        """Advances scene state by one turn following the exact algorithm in spec/04 §4.4.

        Raises:
            NotImplementedError: Implemented by Lane A in task T07.
        """
        raise NotImplementedError("spec/04 §4.4 — RuleEngine.step owned by Lane A (T07)")
