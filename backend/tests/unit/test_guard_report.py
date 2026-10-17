"""T43: guard event recorder and adversarial corpus."""

import json
from pathlib import Path

import pytest

from backend.app.config import settings
from backend.app.llm import guard_stats
from eval.guards.guard_report import corpus_section, live_section, load_events, run_corpus


def test_adversarial_corpus_matches_expectations() -> None:
    results = run_corpus()
    assert len(results) >= 8
    for case, blocked, reason in results:
        assert blocked == case.expect_blocked, f"{case.name}: {reason}"


def test_record_guard_event_writes_ring_and_jsonl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "events.jsonl"
    monkeypatch.setattr(settings, "GUARD_EVENT_LOG_PATH", str(log))
    guard_stats.clear()
    guard_stats.record_guard_event("child_voice", 0, False, "Number 16 not in allowed_numbers")
    guard_stats.record_guard_event("child_voice", 1, True, "Valid")
    events = guard_stats.snapshot()
    assert [e.passed for e in events] == [False, True]
    assert events[1].reason == ""
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["role"] == "child_voice"
    assert rows[0]["mock"] is True
    guard_stats.clear()


def test_live_section_splits_mock_and_reports_fallback(tmp_path: Path) -> None:
    base = {"at": "t", "role": "child_voice"}
    rows = [
        {**base, "attempt": 0, "passed": True, "reason": "", "mock": False},
        {**base, "attempt": 0, "passed": False, "reason": "x", "mock": False},
        {**base, "attempt": 1, "passed": False, "reason": "x", "mock": False},
        {**base, "attempt": 0, "passed": True, "reason": "", "mock": True},
    ]
    path = tmp_path / "e.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    text = "\n".join(live_section(load_events(path)))
    assert "Real providers" in text
    assert "Mock providers" in text
    assert "| child_voice | 2 | 50.0% | 0.0% | 50.0% |" in text


def test_live_section_without_events_says_no_data() -> None:
    assert "NO DATA YET" in "\n".join(live_section([]))


def test_corpus_section_lists_every_case() -> None:
    results = run_corpus()
    assert len(corpus_section(results)) > len(results)
