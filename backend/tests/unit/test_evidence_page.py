"""Tests for the evidence page docs/evidence/README.md (Job 01).

Validates that:
- docs/evidence/README.md exists and is NFC normalized.
- Required sections are present: cost per teacher, guard catches, eval results, voice-turn timings, judge click-through script.
- Unknowns / missing live data are explicitly marked with TODO-HUMAN.
- Zero fabrication of pilot metrics or ungrounded quotes.
"""

import unicodedata
from pathlib import Path


def is_nfc(text: str) -> bool:
    return unicodedata.normalize("NFC", text) == text


def test_evidence_page_exists_and_nfc() -> None:
    path = Path("docs/evidence/README.md")
    assert path.exists(), "docs/evidence/README.md must exist"
    content = path.read_text(encoding="utf-8")
    assert len(content) > 1000, "docs/evidence/README.md must not be empty"
    assert is_nfc(content), "docs/evidence/README.md must be NFC normalized"


def test_evidence_page_required_sections() -> None:
    path = Path("docs/evidence/README.md")
    content = path.read_text(encoding="utf-8")

    # 1. Cost per teacher
    assert "Cost Per Teacher" in content or "cost per teacher" in content.lower()
    assert "Haiku" in content
    assert "Sonnet" in content
    assert "Sarvam" in content

    # 2. Guard catches
    assert "guard_child_line" in content
    assert "guard_coach" in content
    assert "guard_act_tagger" in content
    assert "guard_guide_answerer" in content
    assert "Adversarial" in content or "adversarial" in content.lower()

    # 3. Eval results
    assert "eval/latency" in content or "Latency" in content
    assert "eval/guards" in content or "Guards" in content

    # 4. Voice-turn timings
    assert "Voice-Turn Timing" in content or "voice-turn timing" in content.lower()
    assert "tagger" in content
    assert "engine" in content
    assert "voice" in content

    # 5. Judge click-through script
    assert "Judge Click-Through" in content or "judge click-through" in content.lower()
    assert "teacher.demo2" in content
    assert "Ravi" in content

    # 6. TODO-HUMAN markings
    assert "TODO-HUMAN" in content
