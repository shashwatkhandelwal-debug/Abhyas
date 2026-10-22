"""Official-source chunks, retrieval eval floor, tappable citations and the source endpoint."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.app.auth.guards import get_current_user
from backend.app.channels.web import WebChannel
from backend.app.config import settings
from backend.app.core.types import Citation, OutboundMessage
from backend.app.db.models import AppUser, Message, Teacher
from backend.app.llm.roles.guide_answerer import answer_guide_question
from backend.app.llm.schemas import RetrievedChunk
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.retrieval.search import get_guide_retriever
from backend.app.sessions.service import SessionService
from backend.app.web.chat_api import router as chat_router
from backend.tests.unit.test_state_machine import FakeSessionRepository

REPO = Path(__file__).resolve().parents[3]
CHUNKS = REPO / "content" / "chunks"
OFFICIAL_SOURCES = ("nipun_guidelines_2021", "ncert_vidya_pravesh")


def _official_chunks() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sid in OFFICIAL_SOURCES:
        for line in (CHUNKS / f"{sid}.jsonl").read_text(encoding="utf-8").splitlines():
            out.append(json.loads(line))
    return out


def test_official_chunks_have_required_fields_and_sane_pages() -> None:
    chunks = _official_chunks()
    assert len(chunks) > 300
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids))
    for c in chunks:
        for key in ("source_id", "title", "short_hi", "lang", "heading", "text", "gloss_hi"):
            assert c[key], (c["chunk_id"], key)
        assert 1 <= c["pdf_page_start"] <= c["pdf_page_end"] <= 400
        assert 5 <= len(c["keywords_hi"]) <= 8
        assert any("ऀ" <= ch <= "ॿ" for ch in c["gloss_hi"])
        assert 100 <= len(c["text"].split()) <= 460


def test_sources_manifest_is_resolved() -> None:
    entries = yaml.safe_load((REPO / "content" / "sources" / "sources.yaml").read_text("utf-8"))
    ids = {e["id"] for e in entries}
    assert "up_ganit_sandarshika_c1" in ids
    assert "up_ganit_sandarshika_c2" not in ids
    assert "ncert_fln_learning_outcomes" not in ids
    raw = (REPO / "content" / "sources" / "sources.yaml").read_text("utf-8")
    assert "TODO(human)" not in raw
    for e in entries:
        if e["ingest"]:
            assert e["url"].startswith("https://") and len(e["sha256"]) == 64
            assert (CHUNKS / f"{e['id']}.jsonl").exists()
        else:
            assert e["ingest_note"]


def test_no_pdfs_are_tracked_by_git() -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")
    out = subprocess.run(
        ["git", "ls-files", "*.pdf"], cwd=REPO, capture_output=True, text=True, check=False
    )
    assert out.stdout.strip() == ""


def _load_eval() -> Any:
    spec = importlib.util.spec_from_file_location(
        "retrieval_recall", REPO / "eval/retrieval_recall.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RECALL_AT_5_FLOOR = 0.85  # measured 0.95 on 20 questions; floor leaves room for one more miss


def test_retrieval_recall_at_5_floor_and_ground_truth() -> None:
    ev = _load_eval()
    assert ev.verify_ground_truth(ev.load_questions()["questions"]) == []
    res = asyncio.run(ev.evaluate(5))
    assert res["n"] == 20
    assert res["recall_at_k"] >= RECALL_AT_5_FLOOR, res["misses"]
    # every answerable question clears the bar the answerer uses, most off-topic ones do not
    assert res["answerable_below_threshold"] == 0
    assert res["negatives_below_threshold"] >= 5


async def test_not_in_sources_answer_is_honest_and_escalates() -> None:
    weak = [
        RetrievedChunk(
            chunk_id="x", source_short_hi="निपुण भारत दिशानिर्देश", page=3, text="t", score=0.01
        )
    ]
    res = await answer_guide_question(question="कोई सवाल", category="pedagogy", chunks=weak)
    assert res.escalated and res.no_sources
    assert "अपने सरकारी दस्तावेज़ों में नहीं मिला" in res.answer_text_hi
    assert settings.RETRIEVAL_MIN_SCORE > 0.01


async def test_learn_intro_links_best_official_excerpt() -> None:
    service = SessionService(repository=FakeSessionRepository())
    move = load_move_card("NUM_SUB_REGROUP_BUNDLES")
    text, cites = await service._learn_intro(move, "f")
    assert cites, "subtraction/regrouping move should get an official excerpt"
    assert cites[0].line_hi.startswith("स्रोत: ")
    assert cites[0].line_hi in text
    chunk = get_guide_retriever().get_chunk(cites[0].chunk_id)
    assert chunk is not None and not chunk.get("move_id")


async def test_web_channel_persists_citations_and_strips_line_from_bubble() -> None:
    line = "स्रोत: निपुण भारत दिशानिर्देश, पृष्ठ 88"
    msg = OutboundMessage(
        kind="text",
        text_hi=f"जवाब यहाँ।\n\n{line}",
        citations=[
            Citation(
                chunk_id="nipun_guidelines_2021:p088:070",
                source_short_hi="निपुण भारत दिशानिर्देश",
                page=88,
                line_hi=line,
            )
        ],
    )
    added: list[Message] = []
    session = MagicMock()
    session.add = added.append
    session.commit = AsyncMock()
    teacher = Teacher(id=uuid.uuid4(), name="t", preferred_channel="web")
    await WebChannel().send(teacher, [msg], session=session)
    assert added[0].text == "जवाब यहाँ।"
    assert added[0].citations and added[0].citations[0]["page"] == 88


def _app(user: AppUser | None) -> FastAPI:
    app = FastAPI()
    app.include_router(chat_router)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return app


async def test_source_endpoint_returns_excerpt_for_logged_in_user() -> None:
    user = AppUser(
        id=uuid.uuid4(), username="t", role="teacher", teacher_id=uuid.uuid4(), password_hash="x"
    )
    cid = _official_chunks()[40]["chunk_id"]
    async with AsyncClient(transport=ASGITransport(app=_app(user)), base_url="http://t") as c:
        ok = await c.get(f"/api/source/{cid}")
        missing = await c.get("/api/source/nope:p001:001")
    assert ok.status_code == 200
    body = ok.json()
    assert body["chunk_id"] == cid and body["text"] and body["page"] and body["gloss_hi"]
    assert missing.status_code == 404


async def test_source_endpoint_requires_auth() -> None:
    cid = _official_chunks()[0]["chunk_id"]
    async with AsyncClient(transport=ASGITransport(app=_app(None)), base_url="http://t") as c:
        resp = await c.get(f"/api/source/{cid}")
    assert resp.status_code in (401, 403)
