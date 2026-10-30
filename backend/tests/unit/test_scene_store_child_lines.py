"""fix3 K1 root cause: the lines a child spoke survive the Postgres round trip.

The store kept only the rule engine's answers, so after a reload `previous_line` was always empty
and a child could repeat himself word for word in the live app (the in-memory store hid it).
"""

from __future__ import annotations

import json

from backend.app.rehearsal.scene_store import (
    ChildLineRecord,
    TurnRecord,
    _rule_result,
    _stored_lines,
    _stored_responses,
)


def _turn(lines: list[ChildLineRecord]) -> TurnRecord:
    return TurnRecord(
        turn_index=2, transcript="रवि, कैसे किया?", acts=["ask_to_explain"], child_lines=lines
    )


def test_child_lines_round_trip_through_the_jsonb_column() -> None:
    lines = [
        ChildLineRecord(
            persona_id="ravi", line_hi="सर, 13 में से 7 घटाया, 6 आया। जवाब 16!", voice_id="v1"
        ),
        ChildLineRecord(persona_id="aman", line_hi="सोलह…?", voice_id="v3"),
    ]
    stored = json.loads(json.dumps(_rule_result(_turn(lines)), ensure_ascii=False))  # JSONB
    back = _stored_lines(stored)
    assert [(c.persona_id, c.line_hi, c.voice_id) for c in back] == [
        (c.persona_id, c.line_hi, c.voice_id) for c in lines
    ]
    assert _stored_responses(stored) == []


def test_no_lines_and_no_responses_stores_nothing_and_old_rows_still_load() -> None:
    assert _rule_result(_turn([])) is None
    assert _stored_lines(None) == [] and _stored_lines({"child_responses": []}) == []
    assert _stored_lines({"child_lines": [{"bad": 1}]}) == []  # a malformed row never breaks a load
