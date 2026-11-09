"""Tests for user testing kit, evaluator samples, and Ravi worked example script (spec/10 §10.3, spec/11 §11.6, T37)."""

import csv
import re
import unicodedata
from pathlib import Path

import yaml


def is_nfc(text: str) -> bool:
    return text == unicodedata.normalize("NFC", text)


def test_eval_samples_yaml_validity() -> None:
    """Evaluator samples must have 3-5 items with required fields."""
    samples_file = Path("eval/samples/samples.yaml")
    assert samples_file.exists(), "eval/samples/samples.yaml must exist"

    with open(samples_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "samples" in data
    samples = data["samples"]
    assert 3 <= len(samples) <= 5, f"Expected 3-5 samples, got {len(samples)}"

    for s in samples:
        assert "id" in s
        assert "step" in s
        assert "text_hi" in s
        assert "expect" in s
        assert is_nfc(s["text_hi"]), f"Sample {s['id']} text_hi is not NFC normalized"


def test_consent_form_hi_contents() -> None:
    """Consent form must be simple everyday Hindi, <=250 words, unticked checkboxes."""
    consent_file = Path("eval/user_testing/consent_form_hi.md")
    assert consent_file.exists(), "eval/user_testing/consent_form_hi.md must exist"

    text = consent_file.read_text(encoding="utf-8")
    assert is_nfc(text), "Consent form text must be NFC normalized"
    assert re.search(r"[\u0900-\u097F]", text), "Consent form must contain Hindi/Devanagari text"

    # All checkboxes must be unticked
    assert "[x]" not in text, "All checkboxes must be unticked '[ ]'"
    assert "[ ]" in text, "Checkboxes must be present as '[ ]'"

    # Must contain spoken script and contact line
    assert "मौखिक सहमति" in text, "Must contain spoken consent section"
    assert "प्रश्नों के लिए संपर्क" in text, "Must contain contact line"

    # Must not contain English jargon
    for jargon in ["Deterministic Rule Engine", "DPDP Compliant", "Transcripts", "Think-Aloud"]:
        assert jargon not in text, f"Consent form must not contain jargon '{jargon}'"

    # Max ~250 words
    word_count = len(text.split())
    assert word_count <= 260, f"Consent form exceeds word limit (~250 words): got {word_count}"


def test_exit_questions_hi_contents() -> None:
    """Exit questions must include 1-5 realism, usefulness, adoption, and 5-item SUS-lite."""
    exit_file = Path("eval/user_testing/exit_questions_hi.md")
    assert exit_file.exists(), "eval/user_testing/exit_questions_hi.md must exist"

    text = exit_file.read_text(encoding="utf-8")
    assert is_nfc(text), "Exit questions text must be NFC normalized"

    # Realism question
    assert "बच्चे असली कक्षा जैसे लगे" in text or "यथार्थवाद" in text
    # 5-item SUS-lite presence
    assert "SUS" in text or "सुगमता" in text
    assert "सरल" in text


def test_observer_guide_contents() -> None:
    """Observer guide must define protocol and zero-PII logging."""
    guide_file = Path("eval/user_testing/observer_guide.md")
    assert guide_file.exists(), "eval/user_testing/observer_guide.md must exist"

    text = guide_file.read_text(encoding="utf-8")
    assert is_nfc(text), "Observer guide text must be NFC normalized"
    assert "sessions.csv" in text


def test_sessions_csv_header_and_no_premature_data() -> None:
    """sessions.csv must have proper headers and NO data rows until REAL_DATA_STARTED exists."""
    csv_file = Path("eval/user_testing/sessions.csv")
    marker_file = Path("eval/user_testing/REAL_DATA_STARTED")
    assert csv_file.exists(), "eval/user_testing/sessions.csv must exist"

    with open(csv_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        assert "session_id" in fieldnames
        assert "round" in fieldnames
        assert "date" in fieldnames
        assert "realism_rating" in fieldnames
        assert "usefulness_rating" in fieldnames

        rows = list(reader)
        if not marker_file.exists():
            assert len(rows) == 0, (
                f"sessions.csv must be header-only before REAL_DATA_STARTED is created. "
                f"Found {len(rows)} data rows."
            )
        else:
            for row in rows:
                assert re.match(r"^T-[A-Z0-9]+-[0-9]+$", row["session_id"])
                rating = int(row["realism_rating"])
                assert 1 <= rating <= 5


def test_round_findings_templates_have_no_premature_digits() -> None:
    """Findings templates must not contain digits in metrics tables until REAL_DATA_STARTED exists."""
    r1_file = Path("eval/user_testing/round1_findings.md")
    r2_file = Path("eval/user_testing/round2_findings.md")
    marker_file = Path("eval/user_testing/REAL_DATA_STARTED")
    assert r1_file.exists(), "eval/user_testing/round1_findings.md must exist"
    assert r2_file.exists(), "eval/user_testing/round2_findings.md must exist"

    r1_text = r1_file.read_text(encoding="utf-8")
    r2_text = r2_file.read_text(encoding="utf-8")
    assert is_nfc(r1_text) and is_nfc(r2_text)

    if not marker_file.exists():
        # Check metrics tables in both files
        for f_name, text in [("round1_findings.md", r1_text), ("round2_findings.md", r2_text)]:
            table_lines = [
                line
                for line in text.splitlines()
                if line.strip().startswith("|") and not line.strip().startswith("|:")
            ]
            # Exclude header line of markdown tables
            data_lines = [
                line for line in table_lines if "मुद्दा" not in line and "मीट्रिक" not in line
            ]
            for line in data_lines:
                # Except table numbering like "| 1 |" or "| 2 |", data cells must not contain metrics digits
                cells = [c.strip() for c in line.split("|")[1:-1]]
                # The metric data cells are from column index 1 onwards
                data_cells = cells[1:] if len(cells) > 1 else cells
                for cell in data_cells:
                    assert not re.search(r"\d", cell), (
                        f"Premature metric digits found in {f_name} before REAL_DATA_STARTED: {cell}"
                    )


def test_ravi_worked_example_document() -> None:
    """docs/worked_example_ravi.md must document the full Ravi walkthrough & relapse test."""
    doc_file = Path("docs/worked_example_ravi.md")
    assert doc_file.exists(), "docs/worked_example_ravi.md must exist"

    text = doc_file.read_text(encoding="utf-8")
    assert is_nfc(text), "docs/worked_example_ravi.md must be NFC normalized"
    assert "SUB_SMALLER_FROM_LARGER" in text
    assert "ask_to_explain" in text
    assert "concrete_representation" in text
    assert "contrast_answers" in text
    assert "tell_answer" in text
    assert "PARROT" in text or "RELAPSE" in text


# Keys where the bot speaks in its own (female) voice — text_m not needed.
_BOT_SELF_REFERENCE_ALLOWLIST = frozenset(
    [
        "ask_escalated",  # "बताती हूँ" — bot self
        "ask_out_of_scope",  # "कर सकती हूँ" — bot self
        "unclear",  # "समझ नहीं पाई" — bot self
        "unsupported_type",  # "समझ सकती हूँ" — bot self
        "child_silent",  # child described → uses text_boy, not text_m
        "speaker_model_teacher",  # label "आदर्श शिक्षिका" — fixed label
    ]
)

_FEMININE_PATTERN = re.compile(
    r"रही\b|सकती\b|चाहती\b|\bगई\b|थीं\b|ूँगी\b|ाऊँगी\b|पाई\b|पहुँचीं\b|चाहेंगी\b|चाहेंगी\b"
)


def test_messages_hi_gender_coverage() -> None:
    """Every teacher-addressed message containing feminine verb endings must have text_m.
    Bot self-reference keys (where the bot's female voice is correct) are allowlisted.
    """
    catalog_file = Path("content/messages_hi.yaml")
    assert catalog_file.exists(), "content/messages_hi.yaml must exist"

    with open(catalog_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    missing_text_m: list[str] = []
    for key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        if key in _BOT_SELF_REFERENCE_ALLOWLIST:
            continue
        text = entry.get("text", "")
        if isinstance(text, str) and _FEMININE_PATTERN.search(text):
            if "text_m" not in entry:
                missing_text_m.append(key)

    assert not missing_text_m, (
        f"These message keys have feminine verb endings but no text_m: {missing_text_m}"
    )
