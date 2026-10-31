"""fix4: the stock "मुझे समझ नहीं आया, मैं तो अपने तरीके से ही करता/करती हूँ" line is gone.

It came from the example sentence in the child_voice prompt and showed up in about half of the
children's lines, even after a concrete question about a letter or a matra.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.llm.guards import guard_child_line
from backend.app.llm.roles.child_voice import _no_repeat_rule, voice_child_line
from backend.tests.unit.test_child_k1 import FIRST, PERSONA, _resp

PHRASES = [
    "मुझे समझ नहीं आया, मैं तो अपने तरीके से ही करता हूँ",
    "मुझे समझ नहीं आया, मैं तो अपने तरीके से ही करती हूँ।",
    "सर, मैं तो अपने तरीके से करता हूँ, 45।",
    "मैं तो अपने ही तरीके से करती हूँ, 45।",
]


@pytest.mark.parametrize("line", PHRASES)
def test_guard_rejects_the_stock_phrase(line: str) -> None:
    ok, why = guard_child_line(line, _resp())
    assert not ok
    assert "banned" in why


def test_guard_still_accepts_an_ordinary_line() -> None:
    ok, why = guard_child_line("सर, 7 में से 2 घटाया, 5 आया, तो 45!", _resp())
    assert ok, why


def test_prompt_text_no_longer_carries_the_example() -> None:
    rule = _no_repeat_rule(FIRST)
    assert "तरीके" not in rule
    assert "concrete question" in rule
    prompt = Path("backend/app/llm/prompts/child_voice.v1.md").read_text(encoding="utf-8")
    assert "तरीके" not in prompt


@pytest.mark.asyncio
async def test_a_model_that_returns_the_phrase_never_reaches_the_teacher() -> None:
    stock = "मुझे समझ नहीं आया, मैं तो अपने तरीके से ही करता हूँ। 45"
    with patch(
        "backend.app.llm.roles.child_voice.call_tool", new=AsyncMock(return_value={"line_hi": stock})
    ):
        line = await voice_child_line(_resp(), PERSONA, address_form="m", previous_line=None)
    assert "अपने तरीके" not in line
