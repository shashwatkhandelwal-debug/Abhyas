"""The demo's hero beat: ask how, tell the answer, Ravi parrots, new problem, the strip shows the relapse."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from test_one_on_one_flow import A, Harness, harness, texts  # noqa: F401  (harness is a fixture)

from backend.app.config import settings
from backend.app.core.messages import get_message
from backend.app.rehearsal.header import scene_header
from backend.app.rule_engine.domain import Problem

NEW = Problem(type="sub", a=61, b=28)


@pytest.mark.asyncio
async def test_hero_beat_strip_reads_stuck_again(
    harness: Callable[[], Harness],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CHILD_STRIP_ENABLED", True)
    h = harness()
    await h.setup("NUM_SUB_REGROUP_BUNDLES", "ravi", "उल्टा घटा दिया, छोटी में से बड़ी")
    h.script += [
        ([A.ASK_TO_EXPLAIN], None, None),
        ([A.TELL_ANSWER], None, None),
        ([A.GIVE_NEW_PROBLEM], None, NEW),
        ([], None, None),
    ]
    lines = {
        "asks how": "तुमने यह कैसे किया?",
        "tells the answer": "सही उत्तर 16 है।",
        "gives a new problem": "अब 61 में से 28 घटाओ।",
    }
    stuck_again = f"{get_message('ui_strip_stuck_m')} · {get_message('ui_strip_relapse_m')}"
    labels: list[str] = []
    for step, said in lines.items():
        out = await h.say(said)
        scene = await h.scene()
        header = scene_header(scene.scene_state, True, scene.turns)
        assert header is not None
        labels.append(header["strip_label"])
        print(f"\n--- teacher {step}\n{texts(out)}\nSTRIP: {header['strip_label']}")
    feedback = texts(await h.say("बस"))
    print("--- teacher says बस", feedback, sep="\n")
    told = get_message("coach_outcome_told", "f", child=get_message("speaker_ravi"))
    assert labels[-1] == stuck_again
    assert told in feedback
    assert get_message("ui_strip_learning_m") not in labels[-1]
