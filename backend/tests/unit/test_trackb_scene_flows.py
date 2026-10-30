"""Three full mock scenes per Track B move, through the real SessionService path.

The act tagger is the repo's keyword fallback (no LLM, no network); the children's answers come
only from the rule engine; lines are the deterministic templates. Run with `-s` to print the
transcripts that go into docs/ux/TRACKB_REPORT.md.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from test_one_on_one_flow import Harness
from test_state_machine import FakeSessionRepository

from backend.app.core.messages import get_message
from backend.app.llm.roles.act_tagger import fallback_tag_act
from backend.app.rehearsal.scene_runner import SceneRunner
from backend.app.rehearsal.scene_store import InMemorySceneStore
from backend.app.rule_engine.domain import ChildState, ResponseKind
from backend.app.sessions.service import SessionService


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> Callable[[], Harness]:
    async def tag(**kwargs: Any) -> Any:
        return fallback_tag_act(
            transcript=kwargs["transcript"],
            scene_persona_ids=kwargs["scene_persona_ids"],
            current_item=kwargs.get("current_item"),
        )

    store = InMemorySceneStore()
    monkeypatch.setattr("backend.app.sessions.service.scene_store", store)
    monkeypatch.setattr("backend.app.rehearsal.scene_runner.tag_act", tag)
    monkeypatch.setattr("backend.app.rehearsal.stt_hints.scene_store", store)

    def make() -> Harness:
        runner = SceneRunner(store=store)  # type: ignore[arg-type]
        service = SessionService(repository=FakeSessionRepository(), scene_runner=runner)
        return Harness(service, store, [])

    return make


def show(title: str, teacher: str, out: list[Any]) -> None:
    print(f"\n[{title}]\nटीचर: {teacher}")
    for m in out:
        who = m.speaker or "-"
        print(f"  {who}: {(m.text_hi or '').strip()}")


async def run_lines(h: Harness, title: str, lines: list[str]) -> list[list[Any]]:
    outs = []
    for line in lines:
        out = await h.say(line)
        show(title, line, out)
        outs.append(out)
    return outs


async def last_kinds(h: Harness) -> dict[str, ResponseKind]:
    scene = await h.scene()
    assert scene is not None
    turn = scene.turns[-1]
    return {r.persona_id: r.kind for r in turn.child_responses}


async def open_group(h: Harness, move_id: str) -> None:
    await h.start(move_id)
    await h.say(button="btn_listen")
    if move_id.startswith("NUM_"):
        await h.say(button="btn_rehearse_group")


def children(h: Harness) -> list[Any]:
    return []


@pytest.mark.asyncio
async def test_compare_scene_1_ask_how_then_bundles_then_contrast(
    harness: Callable[[], Harness],
) -> None:
    h = harness()
    await open_group(h, "NUM_COMPARE_BUNDLES")
    await run_lines(
        h,
        "तुलना 1",
        [
            "रवि, तुमने कैसे तय किया कि 39 बड़ा है?",
            "सब लोग देखो, ये रहे 3 बंडल और 9 खुली तीलियाँ, यानी 39, और 4 बंडल और 1 तीली, यानी 41।",
            "अमन, दोनों उत्तर 39 और 41 की तुलना करो, किसके बंडल ज़्यादा हैं?",
        ],
    )
    scene = await h.scene()
    states = {c.persona_id: c.state for c in scene.scene_state.children}
    assert states["aman"] == ChildState.CORRECT
    assert states["ravi"] == ChildState.PARTIAL


@pytest.mark.asyncio
async def test_compare_scene_2_told_answer_then_relapse(
    harness: Callable[[], Harness],
) -> None:
    h = harness()
    await open_group(h, "NUM_COMPARE_BUNDLES")
    outs = await run_lines(
        h,
        "तुलना 2",
        [
            "रवि, सही उत्तर 41 है।",
            "रवि, अब ये सवाल: 28 और 33, कौन बड़ा?",
        ],
    )
    assert "28" in (outs[1][0].text_hi or "")
    kinds = await last_kinds(h)
    assert kinds["ravi"] == ResponseKind.ANSWER
    scene = await h.scene()
    strip_stuck = get_message("ui_strip_stuck_m")
    from backend.app.rehearsal.header import scene_header

    header = scene_header(scene.scene_state, turns=scene.turns)
    assert header is not None
    ravi = next(c for c in header["children"] if c["id"] == "ravi")
    assert strip_stuck in ravi["label"] and get_message("ui_strip_relapse_m") in ravi["label"]


@pytest.mark.asyncio
async def test_compare_scene_3_bundles_then_new_pair_relapses(
    harness: Callable[[], Harness],
) -> None:
    h = harness()
    await open_group(h, "NUM_COMPARE_BUNDLES")
    await run_lines(
        h,
        "तुलना 3",
        [
            "सब लोग देखो, 3 बंडल और 9 तीलियाँ, और 4 बंडल और 1 तीली।",
            "रवि, अब ये सवाल: 47 और 52, कौन बड़ा?",
        ],
    )
    kinds = await last_kinds(h)
    assert kinds["ravi"] == ResponseKind.RELAPSE


@pytest.mark.asyncio
async def test_letter_scene_1_ask_then_sound_out_then_blend(
    harness: Callable[[], Harness],
) -> None:
    h = harness()
    await open_group(h, "LIT_LETTER_SOUND_PAIRS")
    await run_lines(
        h,
        "ध्वनि 1",
        [
            "रवि, तुमने इसे कैसे पढ़ा?",
            "सब लोग, पहले अक्षर पर उँगली रखो और उसकी ध्वनि निकालो।",
            "सब लोग, मैं करके दिखाती हूँ, मेरे साथ: ब, क, री, बकरी।",
        ],
    )
    assert await h.scene() is None  # all three children got it: the scene ended


@pytest.mark.asyncio
async def test_letter_scene_2_told_word_then_new_word_misread(
    harness: Callable[[], Harness],
) -> None:
    h = harness()
    await open_group(h, "LIT_LETTER_SOUND_PAIRS")
    outs = await run_lines(h, "ध्वनि 2", ["रवि, सही उत्तर बकरी है।", "रवि, अब शब्द कमल पढ़ो।"])
    assert "कबूतर" in (outs[1][0].text_hi or "")
    kinds = await last_kinds(h)
    assert kinds["ravi"] == ResponseKind.ANSWER


@pytest.mark.asyncio
async def test_letter_scene_3_sound_out_then_new_word_relapses(
    harness: Callable[[], Harness],
) -> None:
    h = harness()
    await open_group(h, "LIT_LETTER_SOUND_PAIRS")
    await run_lines(
        h,
        "ध्वनि 3",
        [
            "सब लोग, पहले अक्षर की ध्वनि निकालो।",
            "रवि, अब शब्द गमला पढ़ो।",
        ],
    )
    kinds = await last_kinds(h)
    assert kinds["ravi"] == ResponseKind.RELAPSE
