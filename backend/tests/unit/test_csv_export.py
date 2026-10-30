"""F7: CSV downloads of the dashboard tables, and the printable agenda page (mocks only)."""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import replace
from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.access import SUPPRESSION_MESSAGE
from backend.app.auth.guards import get_current_user
from backend.app.db.models import AppUser
from backend.app.db.session import get_db_session
from backend.app.reports.arp_digest import ARPDigestData, RubricDot, TeacherDigestRow
from backend.app.reports.module_progress import ModuleGroupRow
from backend.app.reports.trainer_aggregates import TrainerReport, TrainerRowView
from backend.app.sessions.training_rating import TrainingRatingSummary
from backend.app.web.arp import router as arp_router
from backend.app.web.csv_export import csv_text, tables_from_html
from backend.app.web.review import router as review_router
from backend.app.web.trainer import router as trainer_router

BOM = "﻿"


def user(role: str) -> AppUser:
    return AppUser(
        id=uuid.uuid4(),
        username=f"{role}.demo",
        role=role,
        cluster_id="KNP-C01",
        district="Kanpur Nagar",
        display_name=f"{role} demo",
        password_hash="hash",
    )


def make_app() -> FastAPI:
    app = FastAPI()
    for r in (arp_router, trainer_router, review_router):
        app.include_router(r)
    app.dependency_overrides[get_db_session] = lambda: AsyncMock(spec=AsyncSession)
    return app


def parse(res_text: str) -> list[list[str]]:
    assert res_text.startswith(BOM)
    return list(csv.reader(io.StringIO(res_text[1:])))


def digest(extra: int = 0) -> ARPDigestData:
    week = date(2026, 10, 19)
    rows = [
        TeacherDigestRow(
            teacher_id=str(uuid.uuid4()),
            name="अनीता शर्मा",
            school="SCH-KNP-01",
            move_id="NUM_SUB_REGROUP_BUNDLES",
            move_title="हासिल वाला घटाव",
            step_reached="REHEARSE",
            max_evidence_level=2,
            rubric_dots=[RubricDot("c1", 2, "dot-2"), RubricDot("c2", 1, "dot-1")],
            needs_help=True,
            avg_score=1.5,
        ),
        TeacherDigestRow(
            teacher_id=str(uuid.uuid4()),
            name="=रेखा",
            school="SCH-KNP-02",
            move_id="NUM_SUB_REGROUP_BUNDLES",
            move_title="हासिल वाला घटाव",
            step_reached="DONE",
            max_evidence_level=3,
            rubric_dots=[],
            needs_help=False,
            avg_score=None,
        ),
    ]
    rows += [
        replace(rows[0], teacher_id=str(uuid.uuid4()), name=f"शिक्षिका {i}") for i in range(extra)
    ]
    return ARPDigestData(
        cluster_id="KNP-C01",
        cluster_name="कानपुर नगर संकुल 01",
        selected_week_start=week,
        available_weeks=[week],
        total_teachers=5,
        active_teachers_count=2,
        completed_loops_count=1,
        moves_practised_count=1,
        consenting_teachers=rows,
        non_consenting_count=3,
        suggested_visits=[],
        escalated_questions=[],
    )


def modules(teachers: int, suppressed: bool) -> list[ModuleGroupRow]:
    row = ModuleGroupRow(
        module_id="NUM_SUB_REGROUP_BUNDLES",
        title_hi="हासिल वाला घटाव",
        label="pilot",
        teachers=teachers,
        passed=7,
        suppressed=suppressed,
    )
    row.steps = {"learn": 6, "diagnose": 5, "practise": 4, "check": 3}
    return [row]


@pytest.fixture
def arp_patches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.app.web.arp.build_arp_digest", AsyncMock(return_value=digest()))
    monkeypatch.setattr(
        "backend.app.web.arp.module_progress_summary",
        AsyncMock(return_value=modules(10, False)),
    )
    monkeypatch.setattr("backend.app.web.arp.pack_enabled", lambda: False)
    monkeypatch.setattr("backend.app.web.arp.visit_observation.enabled", lambda: False)


async def get(app: FastAPI, who: AppUser, path: str) -> tuple[int, str, dict[str, str]]:
    app.dependency_overrides[get_current_user] = lambda: who
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        res = await client.get(path)
    return res.status_code, res.content.decode("utf-8"), dict(res.headers)


@pytest.mark.asyncio
async def test_arp_teachers_csv_equals_the_page(arp_patches: None) -> None:
    app = make_app()
    who = user("arp")
    code, page, _ = await get(app, who, "/arp")
    assert code == 200 and 'href="/arp/export/teachers.csv' in page
    on_screen = tables_from_html(page)["teachers"]
    code, body, headers = await get(app, who, "/arp/export/teachers.csv")
    assert code == 200
    rows = parse(body)
    assert rows[0] == on_screen[0]  # the same header row
    assert rows[1][:2] == ["अनीता शर्मा", "SCH-KNP-01"]
    assert rows[1][3] != "REHEARSE" and rows[1][5] == "2 1"  # a label, and the rubric scores
    assert rows[2][0] == "'=रेखा"  # a spreadsheet never reads a name as a formula
    assert rows[-1][0].startswith("3") or "3" in rows[-1][0]  # the non-consenting count row
    assert len(rows) == len(on_screen)


@pytest.mark.asyncio
async def test_headers_bom_filename_and_hindi_intact(arp_patches: None) -> None:
    app = make_app()
    code, body, headers = await get(app, user("arp"), "/arp/export/teachers.csv")
    assert code == 200
    assert body.startswith(BOM) and "हासिल वाला घटाव" in body
    assert headers["content-type"].startswith("text/csv")
    disposition = headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert re.search(r'filename="abhyas_arp_teachers_\d{4}-\d{2}-\d{2}\.csv"', disposition)
    raw = body.encode("utf-8")
    assert raw.startswith(b"\xef\xbb\xbf")


@pytest.mark.asyncio
@pytest.mark.parametrize(("teachers", "suppressed"), [(9, True), (10, False)])
async def test_module_progress_csv_suppresses_at_nine_and_shows_at_ten(
    monkeypatch: pytest.MonkeyPatch, arp_patches: None, teachers: int, suppressed: bool
) -> None:
    monkeypatch.setattr(
        "backend.app.web.arp.module_progress_summary",
        AsyncMock(return_value=modules(teachers, suppressed)),
    )
    # the module table is on the ARP page from 10 consenting teachers
    monkeypatch.setattr("backend.app.web.arp.build_arp_digest", AsyncMock(return_value=digest(8)))
    app = make_app()
    code, body, _ = await get(app, user("arp"), "/arp/export/module_progress.csv")
    assert code == 200
    rows = parse(body)
    data = rows[1]
    assert data[2] == str(teachers)
    if suppressed:
        assert data[3:8] == [SUPPRESSION_MESSAGE] * 5  # the text in every hidden column
        assert not any(c in ("6", "5", "4", "3", "7") for c in data[3:])
    else:
        assert data[3:8] == ["6", "5", "4", "3", "7"]


def trainer_report(n: int, suppressed: bool) -> TrainerReport:
    return TrainerReport(
        district="Kanpur Nagar",
        batches=[],
        moves=[],
        selected_batch_id=None,
        selected_move_id=None,
        rows=[
            TrainerRowView(
                batch_id="KNP-B1",
                batch_name="बैच 1",
                move_id="NUM_SUB_REGROUP_BUNDLES",
                move_title="हासिल वाला घटाव",
                n_teachers=n,
                suppressed=suppressed,
                pct_completed="64%",
                most_missed_point="तीलियाँ खोलना",
                rubric_svg="<svg><title>x</title></svg>",
                ladder_summary="L1: 4 · L2: 6",
                rubric_avg=1.4,
                ladder_counts=None,
            )
        ],
        insight_text=None,
    )


@pytest.fixture
def trainer_patches(monkeypatch: pytest.MonkeyPatch) -> None:
    base = "backend.app.web.trainer."
    monkeypatch.setattr(
        base + "build_trainer_report", AsyncMock(return_value=trainer_report(10, False))
    )
    monkeypatch.setattr(
        base + "training_rating_summary",
        AsyncMock(return_value=TrainingRatingSummary(count=0, average=None)),
    )
    monkeypatch.setattr(
        base + "module_progress_summary", AsyncMock(return_value=modules(10, False))
    )
    monkeypatch.setattr(base + "class_struggle_summary", AsyncMock(return_value=[]))
    monkeypatch.setattr(base + "teaching_skill_summary", AsyncMock(return_value=[]))
    monkeypatch.setattr(base + "pack_enabled", lambda: False)
    monkeypatch.setattr(base + "visit_observation.enabled", lambda: False)


@pytest.mark.asyncio
@pytest.mark.parametrize(("n", "suppressed"), [(9, True), (10, False)])
async def test_trainer_batches_csv_suppression_at_nine_and_ten(
    monkeypatch: pytest.MonkeyPatch, trainer_patches: None, n: int, suppressed: bool
) -> None:
    monkeypatch.setattr(
        "backend.app.web.trainer.build_trainer_report",
        AsyncMock(return_value=trainer_report(n, suppressed)),
    )
    app = make_app()
    who = user("trainer")
    code, page, _ = await get(app, who, "/trainer")
    assert code == 200 and 'href="/trainer/export/batches.csv' in page
    code, body, headers = await get(app, who, "/trainer/export/batches.csv")
    assert code == 200
    assert re.search(
        r"abhyas_trainer_batches_\d{4}-\d{2}-\d{2}\.csv", headers["content-disposition"]
    )
    row = parse(body)[1]
    assert row[2] == str(n)
    if suppressed:
        assert row[3:7] == [SUPPRESSION_MESSAGE] * 4
        assert "64%" not in body and "1.4" not in body and "तीलियाँ" not in body
    else:
        assert row[3:] == ["64%", "तीलियाँ खोलना", "1.4", "L1: 4 · L2: 6"]


@pytest.mark.asyncio
async def test_each_role_downloads_only_its_own_views(
    arp_patches: None, trainer_patches: None
) -> None:
    app = make_app()
    paths = {
        "arp": "/arp/export/teachers.csv",
        "trainer": "/trainer/export/batches.csv",
        "coach": "/review/export/items.csv",
    }
    for role in ("teacher", "arp", "trainer", "coach"):
        for owner, path in paths.items():
            if role == owner:
                continue
            code, _, _ = await get(app, user(role), path)
            assert code == 403, (role, path, code)
    code, _, _ = await get(app, user("arp"), "/arp/export/nope.csv")
    assert code == 404
    code, _, _ = await get(app, user("arp"), "/arp/export/..%2Fteachers.csv")
    assert code in (404, 422)


def test_parser_skips_marked_cells_and_expands_colspan() -> None:
    html = (
        '<table data-export="t"><thead><tr><th>A</th><th data-csv-skip>link</th><th>B</th></tr></thead>'
        '<tbody><tr><td>x &amp; y</td><td data-csv-skip><a href="/z">go</a></td><td data-csv="9">7</td></tr>'
        f'<tr><td colspan="3">{SUPPRESSION_MESSAGE.replace("<", "&lt;")}</td></tr></tbody></table>'
        "<table><tr><td>not exported</td></tr></table>"
    )
    tables = tables_from_html(html)
    assert list(tables) == ["t"]
    assert tables["t"][0] == ["A", "B"]
    assert tables["t"][1] == ["x & y", "9"]
    assert tables["t"][2] == [SUPPRESSION_MESSAGE] * 3
    assert csv_text(tables["t"]).startswith(BOM)


# ── the printable agenda ────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_agenda_page_has_the_print_button_and_the_demo_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.reports.cluster_pack import ClusterPack

    pack = ClusterPack(
        n_teachers=12,
        window_days=14,
        suppressed=False,
        includes_demo=True,
        all_demo=True,
        items=[],
    )
    monkeypatch.setattr("backend.app.web.arp.pack_enabled", lambda: True)
    monkeypatch.setattr("backend.app.web.arp.build_cluster_pack", AsyncMock(return_value=pack))
    app = make_app()
    code, page, _ = await get(app, user("arp"), "/arp/cluster-pack/print")
    assert code == 200
    assert 'id="pack-print-btn"' in page and "window.print()" in page
    assert "डाउनलोड / प्रिंट" in page
    assert 'id="pack-print-demo"' in page
    assert "@media print" in page and ".print-btn" in page
    assert not re.search(r"\.demo\s*\{[^}]*display:\s*none", page)  # the label also prints
