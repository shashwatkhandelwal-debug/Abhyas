"""Part 3/4: the one-on-one flow through SessionService (mode, child, diagnosis, scene, coach).

Runs on the in-memory scene store and the fake repository. The act tagger is scripted so each
test controls exactly which teaching acts the engine sees (the children's answers still come only
from the rule engine).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from test_state_machine import FakeSessionRepository

from backend.app.core.messages import get_message
from backend.app.core.types import InboundMessage, OutboundMessage
from backend.app.llm.guards import find_placeholder_leak
from backend.app.llm.schemas import ActTaggerOutput
from backend.app.rehearsal.header import scene_header
from backend.app.rehearsal.scene_runner import SceneRunner, load_move_card
from backend.app.rehearsal.scene_store import InMemorySceneStore
from backend.app.rule_engine.domain import ChildState, Problem, ResponseKind, TeachingAct
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum

Script = list[tuple[list[TeachingAct], str | None, Problem | None]]


def inbound(
    teacher_id: UUID, text: str | None = None, button_id: str | None = None
) -> InboundMessage:
    return InboundMessage(
        channel="whatsapp",
        channel_msg_id=f"m-{uuid4().hex[:8]}",
        teacher_id=teacher_id,
        kind="button" if button_id else "text",
        text=text,
        button_id=button_id,
        received_at=datetime.now(UTC),
    )


def texts(out: list[OutboundMessage]) -> str:
    return "\n".join(m.text_hi or "" for m in out)


class Harness:
    def __init__(self, service: SessionService, store: InMemorySceneStore, script: Script) -> None:
        self.service = service
        self.store = store
        self.script = script
        self.teacher_id = uuid4()

    async def start(self, move_id: str) -> None:
        ctx = await self.service.get_or_create_context(self.teacher_id)
        ctx.onboarding_state = OnboardingStateEnum.READY
        ctx.current_move_id = move_id
        ctx.current_state = SessionStateEnum.MODEL
        ctx.name = "परीक्षण"
        await self.service._sync_context_to_db(ctx, self.teacher_id)

    async def say(
        self, text: str | None = None, button: str | None = None
    ) -> list[OutboundMessage]:
        return await self.service.handle_inbound(inbound(self.teacher_id, text, button))

    async def ctx(self) -> Any:
        return await self.service.get_or_create_context(self.teacher_id)

    async def scene(self) -> Any:
        return await self.store.get_active_for_teacher(self.teacher_id)

    async def setup(self, move_id: str, child: str, diagnosis: str) -> list[OutboundMessage]:
        """MODEL -> mode prompt -> 1-1 -> child -> diagnosis. Returns the diagnosis reply."""
        await self.start(move_id)
        out = await self.say(button="btn_listen")
        assert out[-1].text_hi == get_message("rehearse_mode_prompt", "f")
        assert [b.id for b in out[-1].buttons or []] == ["btn_rehearse_one", "btn_rehearse_group"]
        out = await self.say(button="btn_rehearse_one")
        assert [b.id for b in out[0].buttons or []] == [
            "btn_child_ravi",
            "btn_child_priya",
            "btn_child_aman",
        ]
        await self.say(button=f"btn_child_{child}")
        return await self.say(diagnosis)


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> Callable[[], Harness]:
    script: Script = []

    async def fake_tag_act(**kwargs: Any) -> ActTaggerOutput:
        acts, addressed, problem = script.pop(0)
        return ActTaggerOutput(acts=acts, addressed_child=addressed, problem=problem)

    store = InMemorySceneStore()
    monkeypatch.setattr("backend.app.sessions.service.scene_store", store)
    monkeypatch.setattr("backend.app.rehearsal.scene_runner.tag_act", fake_tag_act)
    monkeypatch.setattr("backend.app.rehearsal.stt_hints.scene_store", store)

    def make() -> Harness:
        runner = SceneRunner(store=store)  # type: ignore[arg-type]
        service = SessionService(repository=FakeSessionRepository(), scene_runner=runner)
        return Harness(service, store, script)

    return make


A = TeachingAct

# move, child, correct diagnosis, new problem used for the check
CASES = [
    (
        "NUM_SUB_REGROUP_BUNDLES",
        "ravi",
        "उल्टा घटा दिया, छोटी में से बड़ी",
        Problem(type="sub", a=52, b=17),
    ),
    (
        "NUM_SUB_REGROUP_BUNDLES",
        "priya",
        "बंडल खोला पर दहाई में से 1 कम नहीं किया",
        Problem(type="sub", a=61, b=28),
    ),
    ("NUM_ADD_CARRY_BUNDLES", "ravi", "हासिल जोड़ना भूल गया", Problem(type="add", a=27, b=48)),
    ("NUM_ADD_CARRY_BUNDLES", "aman", "गलत हासिल लिया, 3 हासिल", Problem(type="add", a=56, b=29)),
    (
        "NUM_PLACE_VALUE_BUNDLES",
        "ravi",
        "अंक उल्टे लिख दिए",
        Problem(type="place_value", tens=3, ones=5),
    ),
    (
        "NUM_PLACE_VALUE_BUNDLES",
        "priya",
        "बंडल को 1 गिना",
        Problem(type="place_value", tens=6, ones=2),
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("move_id", "child", "diagnosis", "new_problem"), CASES)
async def test_one_on_one_end_to_end(
    harness: Callable[[], Harness],
    move_id: str,
    child: str,
    diagnosis: str,
    new_problem: Problem,
) -> None:
    h = harness()
    reply = await h.setup(move_id, child, diagnosis)

    # the diagnosis was spotted; the misconception is revealed only now
    ctx = await h.ctx()
    assert ctx.diagnosis["verdict"] == "correct" and not ctx.diagnosis["skipped"]
    assert reply[0].text_hi == get_message(
        "diag_result_correct",
        "f",
        reveal=load_move_card(move_id)
        .misconceptions[ctx.diagnosis["true_misconception"]]
        .reveal_hi.format(child=get_message(f"speaker_{child}")),
    )
    scene = await h.scene()
    assert scene.scene_state.one_on_one and not scene.scene_state.diagnosing

    # diagnose -> probe -> concrete aid -> contrast -> new problem
    h.script += [
        ([A.ASK_TO_EXPLAIN], None, None),
        ([A.CONCRETE_REPRESENTATION], None, None),
        ([A.CONTRAST_TWO_ANSWERS], None, None),
        ([A.GIVE_NEW_PROBLEM], None, new_problem),
    ]
    states: list[ChildState] = []
    for line in (
        "तुमने कैसे किया? एक-एक कदम बताओ।",
        "देखो, ये बंडल और तीलियाँ हैं। इन्हें गिनकर दिखाओ।",
        "तुमने पहले कुछ और कहा था, अब ये आया। कौन-सा सही है और क्यों?",
        "अब ये नया सवाल खुद करो।",
    ):
        out = await h.say(line)
        scene = await h.scene() or (await h.store.get(next(iter(h.store._scenes))))
        states.append(scene.scene_state.children[0].state)
        for m in out:
            assert find_placeholder_leak(m.text_hi or "") is None
    assert states == [
        ChildState.CAN_EXPLAIN,
        ChildState.PARTIAL,
        ChildState.CORRECT,
        ChildState.CORRECT,
    ]

    # the scene ended (correct on the new problem), the coach used the one-on-one rubric
    ctx = await h.ctx()
    assert ctx.current_state == SessionStateEnum.FEEDBACK
    (score,) = h.service.repo._rehearsal_scores
    assert set(score.scores) == {
        "asks_to_explain",
        "does_not_tell_answer",
        "uses_concrete_representation",
        "probes_with_followup",
        "checks_on_new_problem",
    }
    assert score.evidence == {"mode": "one_on_one", "diagnosis_verdict": "correct"}
    assert score.scores["asks_to_explain"] >= 1 and score.scores["checks_on_new_problem"] >= 1
    assert "«" in score.strength_hi  # quotes the teacher's own words (deterministic fallback)
    assert ctx.rehearse_stage == ""


@pytest.mark.asyncio
async def test_tell_the_answer_is_parroted_and_relapse_on_a_new_item(
    harness: Callable[[], Harness],
) -> None:
    h = harness()
    await h.setup("NUM_SUB_REGROUP_BUNDLES", "ravi", "उल्टा घटा दिया")
    h.script += [
        ([A.TELL_ANSWER], None, None),
        ([A.ASK_TO_EXPLAIN], None, None),
        ([A.CONCRETE_REPRESENTATION], None, None),
        ([A.GIVE_NEW_PROBLEM], None, Problem(type="sub", a=61, b=28)),
    ]
    await h.say("उत्तर 16 होता है।")
    scene = await h.scene()
    turn = scene.turns[-1]
    assert turn.child_responses[0].kind == ResponseKind.PARROT
    assert scene.scene_state.children[0].state == ChildState.MISCONCEPTION  # told, not taught

    await h.say("तुमने कैसे किया?")
    await h.say("बंडल खोलकर गिनो।")
    assert (await h.scene()).scene_state.children[0].state == ChildState.PARTIAL
    await h.say("अब ये करो।")
    scene = await h.scene()
    assert scene.turns[-1].child_responses[0].kind == ResponseKind.RELAPSE
    assert scene.scene_state.children[0].state == ChildState.PARTIAL  # no free pass


@pytest.mark.asyncio
async def test_out_of_scope_problem_makes_the_child_confused_without_a_placeholder(
    harness: Callable[[], Harness],
) -> None:
    h = harness()
    await h.setup("NUM_SUB_REGROUP_BUNDLES", "ravi", "उल्टा घटा दिया")
    h.script += [([A.GIVE_NEW_PROBLEM], "ravi", Problem(type="sub", a=200, b=120))]
    out = await h.say("रवि, 200 में से 120 घटाओ।")
    scene = await h.scene()
    response = scene.turns[-1].child_responses[0]
    assert response.kind == ResponseKind.CONFUSED and response.answer is None
    assert scene.scene_state.current_item.key() == "sub:43-27"
    spoken = texts(out)
    assert spoken.strip()
    for forbidden in ("None", "none", "null", "{", "}"):
        assert forbidden not in spoken


@pytest.mark.asyncio
async def test_mode_group_keeps_the_three_children_scene(harness: Callable[[], Harness]) -> None:
    h = harness()
    await h.start("NUM_SUB_REGROUP_BUNDLES")
    await h.say(button="btn_listen")
    out = await h.say(button="btn_rehearse_group")
    assert "बच्चों" in texts(out)
    scene = await h.scene()
    assert not scene.scene_state.one_on_one and len(scene.scene_state.children) == 3
    assert scene_header(scene.scene_state) is None


@pytest.mark.asyncio
async def test_unclear_replies_re_ask_and_never_trap(harness: Callable[[], Harness]) -> None:
    h = harness()
    await h.start("NUM_SUB_REGROUP_BUNDLES")
    await h.say(button="btn_listen")
    out = await h.say("पता नहीं")
    assert out[0].text_hi == get_message("rehearse_mode_unclear", "f")
    assert [b.id for b in out[0].buttons or []] == ["btn_rehearse_one", "btn_rehearse_group"]
    await h.say(button="btn_rehearse_one")
    out = await h.say("कोई भी")
    assert out[0].text_hi == get_message("rehearse_child_unclear", "f")
    out = await h.say("रवि")  # typed name works like the button
    assert (await h.scene()).scene_state.children[0].persona_id == "ravi"
    # empty diagnosis: asked again, with Skip
    out = await h.say("...")
    assert out[0].buttons and out[0].buttons[0].id == "btn_skip"
    # skipping reveals the misconception and starts the scene
    out = await h.say(button="btn_skip")
    ctx = await h.ctx()
    assert ctx.diagnosis["skipped"] and ctx.rehearse_stage == "scene"
    assert texts(out).count("24") >= 1  # reveal mentions how 24 came about


@pytest.mark.asyncio
async def test_verdicts_partly_and_wrong_use_their_messages(harness: Callable[[], Harness]) -> None:
    for diagnosis, verdict in (("इकाई में घटाव गलत किया", "partly"), ("मौसम अच्छा है", "wrong")):
        h = harness()
        out = await h.setup("NUM_SUB_REGROUP_BUNDLES", "ravi", diagnosis)
        assert (await h.ctx()).diagnosis["verdict"] == verdict
        assert out[0].text_hi is not None and out[0].text_hi.startswith(
            get_message(f"diag_result_{verdict}", "f", reveal="X").split("X")[0]
        )


@pytest.mark.asyncio
async def test_end_button_before_the_scene_returns_to_the_mode_choice(
    harness: Callable[[], Harness],
) -> None:
    h = harness()
    await h.start("NUM_SUB_REGROUP_BUNDLES")
    await h.say(button="btn_listen")
    await h.say(button="btn_rehearse_one")
    await h.say(button="btn_child_priya")
    assert (await h.scene()) is not None
    out = await h.say("बस")
    assert out[-1].text_hi == get_message("rehearse_mode_prompt", "f")
    assert await h.scene() is None
    assert (await h.ctx()).rehearse_stage == "choose_mode"


@pytest.mark.asyncio
async def test_header_state_comes_from_the_engine(harness: Callable[[], Harness]) -> None:
    h = harness()
    await h.setup("NUM_SUB_REGROUP_BUNDLES", "ravi", "उल्टा घटा दिया")
    scene = await h.scene()
    header = scene_header(scene.scene_state)
    assert header is not None
    assert header["child_id"] == "ravi" and header["child_name"] == get_message("speaker_ravi")
    assert header["cue_state"] == 0 and header["turn"] == 0 and header["max_turns"] == 10
    h.script.append(([A.ASK_TO_EXPLAIN], None, None))
    await h.say("तुमने कैसे किया?")
    scene = await h.scene()
    header = scene_header(scene.scene_state)
    assert header is not None
    assert header["cue_state"] == int(ChildState.CAN_EXPLAIN) and header["turn"] == 1
    assert header["turn_label"] == get_message("ui_scene_turn", "f", turn=1, max=10)
    # no header for an ended scene
    assert scene_header(scene.scene_state, active=False) is None
