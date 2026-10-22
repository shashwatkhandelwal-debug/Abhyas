"""Part 5.2: the coach's optional tip comes only from retrieved FLN excerpts, with a citation."""

import re
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from test_state_machine import FakeSessionRepository

from backend.app.config import settings
from backend.app.llm.guards import guard_coach_suggestion
from backend.app.llm.roles.coach_suggestion import suggest_from_sources
from backend.app.llm.schemas import CoachSuggestionOutput, RetrievedChunk
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.sessions.service import SessionService

CHUNK = RetrievedChunk(
    chunk_id="nishtha_fln-1",
    source_short_hi="निष्ठा FLN",
    section="Toy based pedagogy",
    page=405,
    text="Teachers can use toys and low cost materials so that children handle objects and count "
    "them in groups of 10. Children explain what they did.",
    gloss_hi="खिलौनों और सामग्री से गिनती",
    keywords_hi=["खिलौना", "गिनती"],
)


def out(text: str, chunk_id: str = "nishtha_fln-1") -> CoachSuggestionOutput:
    return CoachSuggestionOutput(suggestion_hi=text, chunk_id=chunk_id)


GOOD = "आप बच्चों को toys और सामग्री देकर 10 की टोली में गिनवाइए और बताने दीजिए।"


def test_guard_accepts_a_grounded_tip() -> None:
    assert guard_coach_suggestion(out(GOOD), [CHUNK])[0]


@pytest.mark.parametrize(
    ("output", "why"),
    [
        (out(GOOD, "someone-else"), "not in the retrieved set"),
        (out(""), "Empty"),
        (out("आप toys " + "शब्द " * 40), "exceeds"),
        (out("तुम बच्चों को toys और सामग्री से गिनवाओ"), "Disrespectful"),
        (out("आप toys और सामग्री से 99 बार गिनवाइए"), "Unauthorized number"),
        (out("आप कक्षा में रंगीन चार्ट लगाइए"), "not grounded"),
    ],
)
def test_guard_rejects(output: CoachSuggestionOutput, why: str) -> None:
    ok, reason = guard_coach_suggestion(output, [CHUNK])
    assert not ok and why in reason


@pytest.mark.asyncio
async def test_no_retrieval_support_means_no_suggestion_and_no_llm_call() -> None:
    with patch("backend.app.llm.roles.coach_suggestion.call_tool", new_callable=AsyncMock) as ct:
        res = await suggest_from_sources("m", "c", [])
    ct.assert_not_called()
    assert res.suggestion_hi is None and res.chunk is None


@pytest.mark.asyncio
async def test_valid_output_is_returned_with_its_chunk() -> None:
    payload = {"suggestion_hi": GOOD, "chunk_id": "nishtha_fln-1"}
    with patch("backend.app.llm.roles.coach_suggestion.call_tool", new_callable=AsyncMock) as ct:
        ct.return_value = payload
        res = await suggest_from_sources("m", "c", [CHUNK])
    assert res.suggestion_hi == GOOD and res.chunk is not None and not res.used_fallback


@pytest.mark.asyncio
async def test_a_chunk_that_was_not_retrieved_is_retried_once_then_omitted() -> None:
    bad = {"suggestion_hi": GOOD, "chunk_id": "invented"}
    with patch("backend.app.llm.roles.coach_suggestion.call_tool", new_callable=AsyncMock) as ct:
        ct.return_value = bad
        res = await suggest_from_sources("m", "c", [CHUNK])
    assert ct.call_count == 2
    assert res.suggestion_hi is None and res.used_fallback


@pytest.mark.asyncio
async def test_empty_model_answer_means_nothing_to_say() -> None:
    with patch("backend.app.llm.roles.coach_suggestion.call_tool", new_callable=AsyncMock) as ct:
        ct.return_value = {"suggestion_hi": "", "chunk_id": ""}
        res = await suggest_from_sources("m", "c", [CHUNK])
    assert ct.call_count == 1 and res.suggestion_hi is None and not res.used_fallback


@pytest.mark.asyncio
async def test_service_adds_a_tappable_citation_only_for_a_retrieved_nishtha_chunk() -> None:
    service = SessionService(repository=FakeSessionRepository())
    move = load_move_card("NUM_SUB_REGROUP_BUNDLES")

    async def fake_call(**kw: Any) -> dict[str, Any]:
        system = kw["system"]
        chunk_id = re.search(r"(nishtha_fln:p\d+:\d+):", system)
        assert chunk_id, "only NISHTHA excerpts are offered"
        body = system.split(chunk_id.group(0), 1)[1].split("\n\n")[0]
        tip = "आप " + " ".join(body.split()[1:14])
        return {"suggestion_hi": tip, "chunk_id": chunk_id.group(1)}

    with patch("backend.app.llm.roles.coach_suggestion.call_tool", fake_call):
        msg = await service._source_suggestion(
            move, "खिलौना आधारित शिक्षण (toy based pedagogy) से गिनती करवाइए", "f"
        )
    assert msg is not None and msg.citations
    assert msg.citations[0].chunk_id.startswith("nishtha_fln")
    assert msg.citations[0].line_hi in (msg.text_hi or "")
    chunk = service.retriever.get_chunk(msg.citations[0].chunk_id)
    assert chunk is not None and chunk["source_id"] == settings.COACH_SUGGESTION_SOURCE_ID


@pytest.mark.asyncio
async def test_service_says_nothing_when_the_model_is_unavailable() -> None:
    service = SessionService(repository=FakeSessionRepository())
    move = load_move_card("NUM_SUB_REGROUP_BUNDLES")
    # the mock LLM returns an empty suggestion: nothing is added
    assert await service._source_suggestion(move, "बंडल गिनवाइए", "f") is None
