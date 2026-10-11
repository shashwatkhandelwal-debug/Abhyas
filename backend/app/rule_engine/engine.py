"""Pure Python deterministic rule engine strictly implementing spec/04 §4.4."""

import re
from typing import Any, Literal

from backend.app.config import settings
from backend.app.rule_engine.bugs import (
    get_rule_info,
    make_step,
    split_akshars,
    sub_smaller_from_larger,
)
from backend.app.rule_engine.child_state import TRANSITIONS
from backend.app.rule_engine.domain import (
    ChildResponse,
    ChildRuntime,
    ChildState,
    Domain,
    Move,
    Persona,
    Problem,
    ResponseKind,
    SceneState,
    Step,
    StepResult,
    TaggedTurn,
    TeachingAct,
)
from backend.app.rule_engine.transitions import ADVANCE


class RuleEngineResult:
    """Legacy result class maintained for backward compatibility."""

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
    """Legacy helper for backward-compatibility with older tests."""

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
        misconceptions = getattr(child, "misconceptions", [])
        primary_bug_id = misconceptions[0] if misconceptions else "SUB_SMALLER_FROM_LARGER"
        target_causes = getattr(self.move, "target_causes", []) if self.move else []
        is_target_misconception = primary_bug_id in target_causes

        new_state = current_state
        act_strs = [a.value for a in acts]
        child_name = getattr(child, "name_hi", getattr(child, "name", child.id))

        if TeachingAct.TELL_ANSWER.value in act_strs:
            return RuleEngineResult(
                child_id=child.id,
                child_name=child_name,
                answer=correct_answer,
                reasoning_steps=["teacher_told_answer"],
                prior_state=current_state,
                new_state=current_state,
                affect="echo",
                explanation_hint_hi=f"Haan ji, {correct_answer}!",
                numbers_involved=[correct_answer],
                is_parrot=True,
            )

        if is_target_misconception:
            for act_str in act_strs:
                if act_str in self.move.teaching_acts_effective:
                    transition_rule = TRANSITIONS.get(act_str)
                    if isinstance(transition_rule, dict) and current_state in transition_rule:
                        new_state = transition_rule[current_state]
                        break

        # Generate rule output
        if primary_bug_id == "SUB_SMALLER_FROM_LARGER" and len(problem_args) >= 2:
            prob = Problem(type="sub", a=problem_args[0], b=problem_args[1])
            bug_res = sub_smaller_from_larger(prob)
            ans = bug_res.answer
            numbers = [
                problem_args[0],
                problem_args[1],
                ans,
                problem_args[0] % 10,
                problem_args[1] % 10,
            ]
        else:
            ans = correct_answer
            numbers = [correct_answer]

        if new_state == ChildState.CORRECT:
            answer = correct_answer
            affect = "confident"
        elif new_state == ChildState.PARTIAL:
            answer = correct_answer
            affect = "tentative"
        elif new_state == ChildState.CAN_EXPLAIN:
            answer = ans
            affect = "explaining"
        else:
            answer = ans
            affect = "confident"

        return RuleEngineResult(
            child_id=child.id,
            child_name=child_name,
            answer=answer,
            reasoning_steps=["procedural_step"],
            prior_state=current_state,
            new_state=new_state,
            affect=affect,
            explanation_hint_hi="",
            numbers_involved=numbers,
            is_parrot=False,
        )


def _validate_problem(problem: Problem, domain: Domain) -> bool:
    """Validates problem constraints per spec/04 §4.4 Step 2."""
    if domain == Domain.NUMERACY:
        if problem.type == "sub":
            return (
                problem.a is not None
                and problem.b is not None
                and 10 <= problem.b < problem.a <= 99
            )
        if problem.type == "add":
            return (
                problem.a is not None
                and problem.b is not None
                and 10 <= problem.a <= 99
                and 10 <= problem.b <= 99
                and (problem.a + problem.b) <= 199
            )
        if problem.type == "place_value":
            return (
                problem.tens is not None
                and problem.ones is not None
                and 1 <= problem.tens <= 9
                and 0 <= problem.ones <= 9
            )
        return False

    if domain == Domain.LITERACY:
        if problem.type != "read_word" or not problem.word:
            return False
        akshars = split_akshars(problem.word)
        return 1 <= len(akshars) <= 4 and all(
            bool(re.search(r"[\u0900-\u097F]", ak)) for ak in akshars
        )

    return False


def _select_responder(scene: SceneState, tagged: TaggedTurn) -> ChildRuntime:
    """Selects responding child strictly following spec/04 §4.4 Step 3."""
    # 3a. Addressed by name
    if tagged.addressed_child:
        for child in scene.children:
            if child.persona_id == tagged.addressed_child:
                return child

    # 3b. INVOLVE_PEER: next child after last_responder in roster order (skip silent)
    if TeachingAct.INVOLVE_PEER in tagged.acts and scene.last_responder:
        last_idx = -1
        for idx, child in enumerate(scene.children):
            if child.persona_id == scene.last_responder:
                last_idx = idx
                break
        if last_idx != -1:
            n = len(scene.children)
            # Search next in roster order, skipping silent children
            for offset in range(1, n):
                candidate = scene.children[(last_idx + offset) % n]
                if candidate.silent_turns == 0:
                    return candidate
            # If all next are silent, pick immediate next in roster order
            return scene.children[(last_idx + 1) % n]

    # 3c. "all" or None: priority confident -> distracted -> shy
    # Shy children are NEVER chosen unless directly addressed
    for temperament in ("confident", "distracted"):
        for child in scene.children:
            if (
                child.temperament == temperament
                and child.state < ChildState.CORRECT
                and child.silent_turns == 0
            ):
                return child

    # If none found (e.g. all non-shy are CORRECT or silent), return confident child or first
    for child in scene.children:
        if child.temperament == "confident":
            return child
    return scene.children[0]


class RuleEngine:
    """Deterministic rule engine for interactive rehearsal scenes (spec/04 §4.4)."""

    def __init__(self, move: Move | None = None) -> None:
        self.move = move

    @staticmethod
    def step(scene: SceneState, tagged: TaggedTurn) -> StepResult:
        """Advances scene state by one turn following the exact algorithm in spec/04 §4.4."""
        # 1. Turn count
        scene.teacher_turns += 1

        # 2. New item handling
        deferred_item_switch: Problem | None = None
        if tagged.problem is not None:
            is_valid = _validate_problem(tagged.problem, scene.domain)
            if not is_valid:
                # Invalid -> main response CONFUSED from responder, no state change
                responder = _select_responder(scene, tagged)
                confused_resp = ChildResponse(
                    persona_id=responder.persona_id,
                    kind=ResponseKind.CONFUSED,
                    answer=None,
                    correct_answer=None,
                    steps=[],
                    prior_state=responder.state,
                    new_state=responder.state,
                    affect="neutral",
                    item=scene.current_item,
                    allowed_numbers=set(),
                    allowed_words=set(),
                    forbidden=set(),
                )
                responder.turns_since_addressed = 0
                responder.history.append((scene.teacher_turns, responder.state))
                scene.last_responder = responder.persona_id
                for c in scene.children:
                    if c.persona_id != responder.persona_id:
                        c.turns_since_addressed += 1
                return StepResult(
                    responses=[confused_resp], ended=scene.ended, end_reason=scene.end_reason
                )

            # Valid problem
            if TeachingAct.TELL_ANSWER in tagged.acts:
                deferred_item_switch = tagged.problem
            else:
                scene.current_item = tagged.problem

            if TeachingAct.GIVE_NEW_PROBLEM not in tagged.acts:
                tagged.acts.append(TeachingAct.GIVE_NEW_PROBLEM)

        elif TeachingAct.GIVE_NEW_PROBLEM in tagged.acts and tagged.problem is None:
            if scene.items:
                scene.item_idx = (scene.item_idx + 1) % len(scene.items)
                scene.current_item = scene.items[scene.item_idx]

        # 3. Select Responder
        responder = _select_responder(scene, tagged)
        prior_state = responder.state

        # 4. Whole-class acts: if addressed_child == "all"
        whole_class_acts = {
            TeachingAct.CONCRETE_REPRESENTATION,
            TeachingAct.MODEL_STEP_ALOUD,
            TeachingAct.PHONICS_SOUND_OUT,
        }
        if tagged.addressed_child == "all":
            for act in tagged.acts:
                if act in whole_class_acts and act in scene.effective_acts:
                    for child in scene.children:
                        if child.silent_turns == 0 and child.misconception in scene.target_causes:
                            act_trans = ADVANCE.get(act, {})
                            if child.state in act_trans:
                                nxt = act_trans[child.state]
                                if nxt > child.state:
                                    if (
                                        nxt == ChildState.PARTIAL
                                        and child.state < ChildState.PARTIAL
                                    ):
                                        child.partial_item_key = scene.current_item.key()
                                    child.state = nxt

        # 5. Silence check
        affect: Literal["neutral", "confident", "encouraged", "upset", "shy", "distracted"] = (
            "confident" if responder.temperament == "confident" else "neutral"
        )
        if TeachingAct.PRAISE_EFFORT in tagged.acts:
            affect = "encouraged"
            responder.silent_turns = 0
        elif responder.silent_turns > 0:
            responder.silent_turns -= 1
            silent_resp = ChildResponse(
                persona_id=responder.persona_id,
                kind=ResponseKind.SILENT,
                answer=None,
                correct_answer=None,
                steps=[],
                prior_state=prior_state,
                new_state=responder.state,
                affect="shy",
                item=scene.current_item,
                allowed_numbers=set(),
                allowed_words=set(),
                forbidden=set(),
            )
            # Bookkeeping
            responder.turns_since_addressed = 0
            responder.last_answer = None
            responder.history.append((scene.teacher_turns, responder.state))
            scene.last_responder = responder.persona_id
            for c in scene.children:
                if c.persona_id != responder.persona_id:
                    c.turns_since_addressed += 1
            return StepResult(
                responses=[silent_resp], ended=scene.ended, end_reason=scene.end_reason
            )

        # 6. Responder transition
        effective = set(tagged.acts) & set(scene.effective_acts)
        is_target_cause = responder.misconception in scene.target_causes

        if TeachingAct.SCOLD in tagged.acts:
            if responder.temperament == "shy":
                responder.silent_turns = getattr(settings, "SHY_SILENT_TURNS", 1)
                scold_silent_resp = ChildResponse(
                    persona_id=responder.persona_id,
                    kind=ResponseKind.SILENT,
                    answer=None,
                    correct_answer=None,
                    steps=[],
                    prior_state=prior_state,
                    new_state=responder.state,
                    affect="shy",
                    item=scene.current_item,
                    allowed_numbers=set(),
                    allowed_words=set(),
                    forbidden=set(),
                )
                responder.turns_since_addressed = 0
                responder.last_answer = None
                responder.history.append((scene.teacher_turns, responder.state))
                scene.last_responder = responder.persona_id
                for c in scene.children:
                    if c.persona_id != responder.persona_id:
                        c.turns_since_addressed += 1
                return StepResult(
                    responses=[scold_silent_resp], ended=scene.ended, end_reason=scene.end_reason
                )
            else:
                affect = "upset"
                new_state = responder.state
        else:
            if is_target_cause and effective:
                candidate_states = [responder.state]
                for act in effective:
                    if act in ADVANCE and responder.state in ADVANCE[act]:
                        candidate_states.append(ADVANCE[act][responder.state])
                new_state = max(candidate_states)
            else:
                new_state = responder.state

            if new_state == ChildState.PARTIAL and prior_state < ChildState.PARTIAL:
                responder.partial_item_key = scene.current_item.key()
            responder.state = new_state

        # 7. Answer computation
        rule_info = get_rule_info(responder.misconception)
        context = {"guess_lexicon": getattr(scene, "guess_lexicon", {})}
        bug_out = rule_info.fn(scene.current_item, context)
        corr_out = rule_info.correct_fn(scene.current_item, context)

        kind: ResponseKind
        answer: int | str | None
        steps: list[Step]

        if TeachingAct.TELL_ANSWER in tagged.acts and new_state == prior_state:
            kind = ResponseKind.PARROT
            answer = corr_out.answer
            steps = []
            responder.state = prior_state
            new_state = prior_state
        elif TeachingAct.OFF_TASK in tagged.acts and responder.temperament == "distracted":
            kind = ResponseKind.OFF_TOPIC
            answer = None
            steps = []
            affect = "distracted"
        elif new_state == ChildState.MISCONCEPTION:
            kind = ResponseKind.ANSWER
            answer = bug_out.answer
            steps = [
                make_step(
                    "ANSWER",
                    nums=[bug_out.answer] if isinstance(bug_out.answer, int) else [],
                    words=[str(bug_out.answer)],
                    answer=bug_out.answer,
                )
            ]
        elif new_state == ChildState.CAN_EXPLAIN:
            kind = ResponseKind.EXPLAIN_BUG
            answer = bug_out.answer
            steps = bug_out.steps
        elif new_state == ChildState.PARTIAL:
            if scene.current_item.key() != responder.partial_item_key and len(effective) == 0:
                kind = ResponseKind.RELAPSE
                answer = bug_out.answer
                steps = bug_out.steps
            else:
                kind = ResponseKind.SCAFFOLDED_CORRECT
                answer = corr_out.answer
                steps = corr_out.steps
                if scene.current_item.key() != responder.partial_item_key and len(effective) > 0:
                    responder.partial_item_key = scene.current_item.key()
        else:  # ChildState.CORRECT
            kind = ResponseKind.CORRECT_EXPLAINED
            answer = corr_out.answer
            steps = corr_out.steps

        # 3d. INVOLVE_PEER listener advancing rule
        if TeachingAct.INVOLVE_PEER in tagged.acts and responder.state == ChildState.CORRECT:
            if TeachingAct.INVOLVE_PEER in scene.effective_acts:
                for peer in scene.children:
                    if (
                        peer.persona_id != responder.persona_id
                        and peer.state == ChildState.CAN_EXPLAIN
                        and peer.silent_turns == 0
                        and peer.misconception in scene.target_causes
                    ):
                        peer.state = ChildState.PARTIAL
                        peer.partial_item_key = scene.current_item.key()

        # 8. Allowed and forbidden sets
        allowed_numbers: set[int] = {1}
        if scene.current_item.a is not None:
            allowed_numbers.add(scene.current_item.a)
        if scene.current_item.b is not None:
            allowed_numbers.add(scene.current_item.b)
        if scene.current_item.tens is not None:
            allowed_numbers.add(scene.current_item.tens)
            allowed_numbers.add(10)
        if scene.current_item.ones is not None:
            allowed_numbers.add(scene.current_item.ones)
        if isinstance(answer, int):
            allowed_numbers.add(answer)
        for st in steps:
            for n in st.nums:
                allowed_numbers.add(n)

        forbidden: set[str] = set()
        if kind in (ResponseKind.ANSWER, ResponseKind.EXPLAIN_BUG, ResponseKind.RELAPSE):
            if str(corr_out.answer) != str(answer):
                forbidden.add(str(corr_out.answer))

        allowed_words: set[str] = set()
        if isinstance(answer, str):
            for tok in answer.split():
                allowed_words.add(tok)
        for st in steps:
            for w in st.words:
                allowed_words.add(w)

        main_resp = ChildResponse(
            persona_id=responder.persona_id,
            kind=kind,
            answer=answer,
            correct_answer=corr_out.answer,
            steps=steps,
            prior_state=prior_state,
            new_state=responder.state,
            affect=affect,
            item=scene.current_item,
            allowed_numbers=allowed_numbers,
            allowed_words=allowed_words,
            forbidden=forbidden,
        )

        responses: list[ChildResponse] = [main_resp]

        # 9. Bookkeeping
        responder.turns_since_addressed = 0
        responder.last_answer = answer
        responder.history.append((scene.teacher_turns, responder.state))
        scene.last_responder = responder.persona_id

        for c in scene.children:
            if c.persona_id != responder.persona_id:
                c.turns_since_addressed += 1

        if deferred_item_switch is not None:
            scene.current_item = deferred_item_switch

        # 10. Distracted interjection (max one per turn)
        for c in scene.children:
            if (
                c.persona_id != responder.persona_id
                and c.temperament == "distracted"
                and c.turns_since_addressed >= 3
            ):
                interject = ChildResponse(
                    persona_id=c.persona_id,
                    kind=ResponseKind.INTERJECT,
                    answer=None,
                    correct_answer=None,
                    steps=[],
                    prior_state=c.state,
                    new_state=c.state,
                    affect="distracted",
                    item=scene.current_item,
                    allowed_numbers=set(),
                    allowed_words=set(),
                    forbidden=set(),
                )
                responses.append(interject)
                c.turns_since_addressed = 0
                break

        # 11. End conditions
        if len(scene.children) == 1:
            # Placement mode: 2 teacher turns then end
            if scene.teacher_turns >= 2:
                scene.ended = True
                scene.end_reason = "turn_limit"
        else:
            if all(c.state == ChildState.CORRECT for c in scene.children):
                scene.ended = True
                scene.end_reason = "all_correct"
            elif scene.teacher_turns >= getattr(settings, "MAX_TURNS_PER_REHEARSAL", 8):
                scene.ended = True
                scene.end_reason = "turn_limit"

        return StepResult(responses=responses, ended=scene.ended, end_reason=scene.end_reason)
