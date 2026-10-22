"""One real call per Sonnet role (coach, fidelity_checker, guide_answerer). Key stays in env."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import yaml

from backend.app.config import settings
from backend.app.content_models import MoveCard
from backend.app.llm import client as llm_client
from backend.app.llm.roles.coach import coach_feedback
from backend.app.llm.roles.fidelity_checker import check_fidelity
from backend.app.llm.roles.guide_answerer import answer_guide_question
from backend.app.llm.schemas import RetrievedChunk, SceneTurn
from backend.app.rule_engine.domain import ChildState, TeachingAct

ROOT = Path(__file__).resolve().parent.parent


async def main() -> None:
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    print("models:", settings.CLAUDE_MODEL_SMART, "| provider:", settings.LLM_PROVIDER)
    move = MoveCard.model_validate(
        yaml.safe_load((ROOT / "content/moves/NUM_SUB_REGROUP_BUNDLES.yaml").read_text("utf-8"))
    )

    turns = [
        SceneTurn(speaker="teacher", text_hi="रवि, तुमने 43 में से 27 कैसे घटाया? मुझे समझाओ।"),
        SceneTurn(speaker="ravi", text_hi="3 में से 7 नहीं घटता तो 7 में से 3 घटाया, 4 आया। 24!"),
        SceneTurn(speaker="teacher", text_hi="चलो बंडल और तीलियाँ लेकर बनाते हैं, 43 दिखाओ।"),
    ]
    res = await coach_feedback(
        move=move,
        turns=turns,
        acts=[[TeachingAct.ASK_TO_EXPLAIN], [TeachingAct.CONCRETE_REPRESENTATION]],
        trajectories={"ravi": [ChildState.MISCONCEPTION, ChildState.CAN_EXPLAIN]},
        target_child_id="ravi",
        current_item_answer=16,
    )
    print("\n[coach] used_fallback =", res.used_fallback, "| confidence =", res.feedback.confidence)
    print("  scores:", res.feedback.scores)
    print("  strength:", res.feedback.strength_hi)
    print("  change:", res.feedback.change_hi)

    fid = await check_fidelity(
        move,
        "इस तरीके में बच्चे से पहले पूछते हैं कि उसने कैसे किया, फिर बंडल और तीलियों से दिखाते हैं।",
    )
    print("\n[fidelity_checker] used_fallback =", fid.used_fallback)
    print("  reply:", fid.reply_hi[:200])

    chunk = RetrievedChunk(
        chunk_id="demo-1",
        source_short_hi="निपुण भारत दिशानिर्देश",
        section="गिनती",
        page=12,
        text="बच्चों से पूछें कि उन्होंने उत्तर कैसे निकाला। ठोस वस्तुओं जैसे तीलियों का प्रयोग करें।",
        score=0.5,
    )
    ans = await answer_guide_question(
        question="बच्चे को घटाव समझाने के लिए क्या करें?",
        category="pedagogy",
        chunks=[chunk],
    )
    print("\n[guide_answerer] used_fallback =", ans.used_fallback, "| escalated =", ans.escalated)
    print("  ", ans.answer_text_hi[:300])
    print(
        "\nforced-tool_choice-rejecting models learned:",
        llm_client._MODELS_WITHOUT_FORCED_TOOL_CHOICE,
    )


if __name__ == "__main__":
    asyncio.run(main())
