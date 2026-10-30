"""F6b: no raw state or role codes on the dashboards, in Hindi and in English."""

from __future__ import annotations

import re
import uuid
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from test_csv_export import digest, make_app, modules, user

from backend.app.auth.guards import get_current_user
from backend.app.core.messages import get_message, has_message, reset_ui_lang, set_ui_lang
from backend.app.sessions.state_machine import SessionStateEnum
from backend.app.web.csv_export import tables_from_html

STATES = [s.value for s in SessionStateEnum] + ["NEW"]
RAW_STATE = re.compile(r"\b(" + "|".join(sorted(STATES, key=len, reverse=True)) + r")\b")


@pytest.mark.parametrize("lang", ["hi", "en"])
def test_every_state_has_a_short_label_in_both_languages(lang: str) -> None:
    for state in STATES:
        key = f"ui_step_state_{state}"
        assert has_message(key), key
        label = get_message(key, lang=lang)
        assert label and not RAW_STATE.search(label), (key, label)


def test_rehearse_reads_practice() -> None:
    assert get_message("ui_step_state_REHEARSE", lang="hi") == "अभ्यास"
    assert get_message("ui_step_state_REHEARSE", lang="en") == "Practice"


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["hi", "en"])
async def test_arp_page_shows_no_raw_state_code(monkeypatch: pytest.MonkeyPatch, lang: str) -> None:
    base = digest()
    rows = [
        replace(base.consenting_teachers[0], teacher_id=str(uuid.uuid4()), step_reached=state)
        for state in STATES
    ]
    page_digest = replace(base, consenting_teachers=rows, non_consenting_count=0)
    monkeypatch.setattr("backend.app.web.arp.build_arp_digest", AsyncMock(return_value=page_digest))
    monkeypatch.setattr(
        "backend.app.web.arp.module_progress_summary", AsyncMock(return_value=modules(10, False))
    )
    monkeypatch.setattr("backend.app.web.arp.pack_enabled", lambda: False)
    monkeypatch.setattr("backend.app.web.arp.visit_observation.enabled", lambda: False)
    app = make_app()
    app.dependency_overrides[get_current_user] = lambda: user("arp")
    token = set_ui_lang(lang)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            res = await client.get("/arp")
    finally:
        reset_ui_lang(token)
    assert res.status_code == 200
    table = tables_from_html(res.text)["teachers"]
    cells = {cell for row in table[1:] for cell in row}
    assert not any(RAW_STATE.search(c) for c in cells), sorted(cells)
    assert get_message("ui_step_state_REHEARSE", lang=lang) in cells
