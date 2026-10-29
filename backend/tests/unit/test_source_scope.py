"""National / state labels on sources: manifest, citation text, and the national tie-break.

Labels come from `content/sources/sources.yaml` and the message catalog; nothing is guessed, and a
source with no scope (the Abhyas move summaries) is cited without a label.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from backend.app.class_profile import checkin_flow, level_sorter
from backend.app.class_profile.library import CHUNKS_DIR, load_library
from backend.app.core.messages import get_catalog, get_message, reset_ui_lang, set_ui_lang
from backend.app.llm.roles.guide_answerer import format_guide_citation
from backend.app.retrieval import source_scope as ss
from backend.app.retrieval.search import GuideRetriever
from backend.app.sessions.state_machine import SessionContext

NATIONAL_IDS = {"nipun_guidelines_2021", "ncert_vidya_pravesh", "nishtha_fln"}
STATE_UP_IDS = {"up_ganit_sandarshika_c1", "up_bhasha_sandarshika_c1"}
MANIFEST = yaml.safe_load(ss.MANIFEST.read_text(encoding="utf-8"))


def test_every_source_in_the_manifest_has_a_scope() -> None:
    assert {e["id"] for e in MANIFEST} == NATIONAL_IDS | STATE_UP_IDS
    for e in MANIFEST:
        assert e["scope"] in ("national", "state"), e["id"]
        assert (e["scope"] == "state") == bool(e.get("state")), e["id"]
    assert {e["id"] for e in MANIFEST if e["scope"] == "national"} == NATIONAL_IDS
    assert {e["id"] for e in MANIFEST if e.get("state") == "UP"} == STATE_UP_IDS


def test_every_stored_chunk_source_is_labelled_or_is_an_abhyas_summary() -> None:
    unlabelled: set[str] = set()
    for f in CHUNKS_DIR.glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("move_id"):
                continue  # Abhyas move summaries are not an official source
            info = ss.scope_of_short(row.get("source_short_hi", ""))
            if info is None or not info.scope:
                unlabelled.add(row["chunk_id"].split(":")[0])
    assert unlabelled == set()


def test_labels_come_from_the_catalog() -> None:
    hi = get_catalog(lang="hi")
    assert hi.get("ask_source_scope_national") == "राष्ट्रीय"
    assert hi.get("ask_source_scope_state_UP") == "राज्य: उ.प्र."
    en = get_catalog(lang="en")
    assert en.get("ask_source_scope_national") == "National"
    assert en.get("ask_source_scope_state_UP") == "State: UP"
    for e in MANIFEST:
        assert ss.scope_label(ss.scope_of(e["id"]))


def test_a_state_without_catalog_text_or_an_unknown_source_has_no_label() -> None:
    assert ss.scope_label(None) == ""
    assert ss.scope_label(ss.SourceScope("x", "x", "state", "ZZ")) == ""
    assert ss.scope_label(ss.SourceScope("x", "x", "", "")) == ""
    assert ss.scope_of("no_such_source") is None


@pytest.mark.parametrize("ui", ["hi", "en"])
def test_citation_text_names_the_scope_in_hindi_beside_the_page(ui: str) -> None:
    token = set_ui_lang(ui)
    try:
        national = format_guide_citation("विद्या प्रवेश (NCERT)", 12)
        state = format_guide_citation("भाषा संदर्शिका कक्षा 1 (उ.प्र.)", 136)
        no_page = format_guide_citation("निष्ठा FLN")
        summary = format_guide_citation(get_message("ingest_summary_title"), 3)
    finally:
        reset_ui_lang(token)
    assert national.endswith("पृष्ठ 12 (राष्ट्रीय)")
    assert state.endswith("पृष्ठ 136 (राज्य: उ.प्र.)")
    assert no_page == "[निष्ठा FLN] (राष्ट्रीय)"
    assert summary.endswith("पृष्ठ 3") and "(" not in summary.split("पृष्ठ")[1]


def test_check_in_and_level_sorter_citations_carry_the_label() -> None:
    lib = load_library()
    s = next(x for x in lib.struggles if x.id == "NUM_COUNTING")
    ctx = SessionContext.model_construct(address_form="f", current_state=None)
    tip = checkin_flow.result_messages(ctx, s)[0]
    assert tip.citations and all(c.line_hi.endswith(")") for c in tip.citations)
    assert "(राष्ट्रीय)" in tip.text_hi and "(राज्य: उ.प्र.)" in tip.text_hi
    lines, cites = level_sorter._sources(["up_bhasha_sandarshika_c1:p138:305"], "f")
    assert "(राज्य: उ.प्र.)" in lines and cites[0].line_hi == lines


# ── retrieval tie-break ─────────────────────────────────────────────────────────────────────
def _write(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return path


def _row(cid: str, source: str, text: str) -> dict[str, object]:
    return {
        "chunk_id": cid,
        "source": source,
        "section": "",
        "text": text,
        "source_short_hi": "x",
        "page": 1,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("state_first", [True, False])
async def test_equal_scores_prefer_the_national_source(tmp_path: Path, state_first: bool) -> None:
    text = "बंडल और तीलियों से दहाई और इकाई समझाएँ"
    rows = [
        _row("up_ganit_sandarshika_c1:p001:001", "up_ganit_sandarshika_c1", text),
        _row("ncert_vidya_pravesh:p001:001", "ncert_vidya_pravesh", text),
    ]
    if not state_first:
        rows.reverse()
    r = GuideRetriever(chunks_file=_write(tmp_path / "c.jsonl", rows))
    hits = await r.retrieve("दहाई और इकाई बंडल", top_k=2)
    assert [h.source for h in hits] == ["ncert_vidya_pravesh", "up_ganit_sandarshika_c1"]
    assert hits[0].similarity_score == hits[1].similarity_score


@pytest.mark.asyncio
async def test_a_better_state_chunk_still_beats_a_national_one(tmp_path: Path) -> None:
    rows = [
        _row("ncert_vidya_pravesh:p001:001", "ncert_vidya_pravesh", "खेल और गीत की बातें"),
        _row(
            "up_ganit_sandarshika_c1:p001:001",
            "up_ganit_sandarshika_c1",
            "बंडल और तीलियों से दहाई और इकाई समझाएँ",
        ),
    ]
    r = GuideRetriever(chunks_file=_write(tmp_path / "c.jsonl", rows))
    hits = await r.retrieve("दहाई और इकाई बंडल", top_k=2)
    assert hits[0].source == "up_ganit_sandarshika_c1"


def test_national_rank_is_one_for_national_sources_only() -> None:
    assert [ss.national_rank(i) for i in sorted(NATIONAL_IDS)] == [1, 1, 1]
    assert [ss.national_rank(i) for i in sorted(STATE_UP_IDS)] == [0, 0]
    assert ss.national_rank("seed_from_moves") == 0 and ss.national_rank("") == 0


@pytest.mark.asyncio
async def test_order_is_deterministic_across_runs(tmp_path: Path) -> None:
    text = "गिनती में हर वस्तु को छुएँ"
    rows = [
        _row("up_bhasha_sandarshika_c1:p001:001", "up_bhasha_sandarshika_c1", text),
        _row("nipun_guidelines_2021:p001:001", "nipun_guidelines_2021", text),
        _row("ncert_vidya_pravesh:p001:001", "ncert_vidya_pravesh", text),
    ]
    r = GuideRetriever(chunks_file=_write(tmp_path / "c.jsonl", rows))
    first = [h.chunk_id for h in await r.retrieve("गिनती वस्तु छुएँ", top_k=3)]
    again = [h.chunk_id for h in await r.retrieve("गिनती वस्तु छुएँ", top_k=3)]
    assert first == again
    assert first[:2] == ["nipun_guidelines_2021:p001:001", "ncert_vidya_pravesh:p001:001"]
    assert first[2] == "up_bhasha_sandarshika_c1:p001:001"
