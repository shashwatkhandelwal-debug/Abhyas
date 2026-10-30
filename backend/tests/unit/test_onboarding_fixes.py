"""fix3 K1, K2, K3 end to end on the mock model: the onboarding practice with Ravi.

The live transcript: Ravi is asked how he got 45, then the teacher dictates the procedure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from backend.app.core.messages import get_message
from backend.app.core.types import InboundMessage, OutboundMessage
from backend.app.llm.roles.child_voice import is_near_repeat
from backend.app.rehearsal.scene_store import InMemorySceneStore
from backend.app.sessions.service import SessionService
from backend.app.sessions.titles import move_title
from backend.tests.unit.test_state_machine import FakeSessionRepository

ASKED = "रवि, 45 कैसे आया?"
TOLD = "ऊपर 52 नीचे 17 लिखो, 12 में से 7 घटाओ, 4 में से 1 घटाओ, अब बताओ क्या आंसर है"


@pytest.fixture(autouse=True)
def _in_memory_scene_store(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.rehearsal import scene_runner as runner_module
    from backend.app.sessions import service as service_module

    store = InMemorySceneStore()
    monkeypatch.setattr(service_module, "scene_store", store)
    monkeypatch.setattr(runner_module, "scene_store", store)


def _inbound(
    teacher_id: Any, text: str | None = None, button_id: str | None = None
) -> InboundMessage:
    return InboundMessage(
        channel="web",
        channel_msg_id=f"msg-{uuid4().hex[:8]}",
        teacher_id=teacher_id,
        kind="button" if button_id else "text",
        text=text,
        button_id=button_id,
        received_at=datetime.now(UTC),
    )


def _texts(msgs: list[OutboundMessage]) -> list[str]:
    return [str(m.text_hi or "") for m in msgs]


async def _onboard(
    form: str, first: str, second: str
) -> tuple[list[OutboundMessage], list[OutboundMessage]]:
    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    t_id = uuid4()
    await service.handle_inbound(_inbound(t_id, text="सहमत हूँ", button_id="btn_agree"))
    await service.handle_inbound(_inbound(t_id, text="KNP-C01-B1"))
    await service.handle_inbound(_inbound(t_id, text="सुनील"))
    await service.handle_inbound(
        _inbound(t_id, button_id=f"btn_{'male' if form == 'm' else 'female'}")
    )
    await service.handle_inbound(_inbound(t_id, text="2-5 साल"))
    await service.handle_inbound(_inbound(t_id, text="2"))
    one = await service.handle_inbound(_inbound(t_id, text=first))
    two = await service.handle_inbound(_inbound(t_id, text=second))
    return one, two


@pytest.mark.asyncio
async def test_k1_k2_k3_the_live_transcript() -> None:
    one, two = await _onboard("m", ASKED, TOLD)
    ravi1 = next(m for m in one if m.speaker == "ravi")
    ravi2 = next(m for m in two if m.speaker == "ravi")
    # K1: the second Ravi line is not the first again, and he reacts to what he was told
    assert not is_near_repeat(str(ravi2.text_hi), str(ravi1.text_hi)), (
        ravi1.text_hi,
        ravi2.text_hi,
    )
    assert str(ravi2.text_hi).startswith("सर") and "दीदी" not in str(ravi2.text_hi)

    texts = _texts(two)
    # K2: the feedback says she then told the procedure
    assert any(get_message("placement_fb_told_later", "m") in t for t in texts), texts
    # K3: the move is named once (the feedback), not again in "first move" and "this week's move"
    title = move_title("NUM_PLACE_VALUE_BUNDLES")
    named = [t for t in texts if title in t]
    assert len(named) == 1, named
    assert not any("पहला तरीका है" in t for t in texts)
    assert any(get_message("learn_intro_announced", "m") in t for t in texts)


@pytest.mark.asyncio
async def test_k2_not_added_when_the_second_turn_is_a_question() -> None:
    _, two = await _onboard("f", ASKED, "रवि, बंडल लेकर 52 बनाओ।")
    assert not any(get_message("placement_fb_told_later", "f") in t for t in _texts(two))
