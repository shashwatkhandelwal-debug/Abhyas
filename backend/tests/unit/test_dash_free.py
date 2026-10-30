"""F4: no em or en dashes in our own text, and the normalizer on outgoing bot text."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.app.core.outbound_text import clean_text, normalize_outbound
from backend.app.core.types import Button, Citation, OutboundMessage

EM, EN = "—", "–"
ROOT = Path(__file__).resolve().parents[3]


def test_em_dash_separator_becomes_a_comma() -> None:
    assert clean_text(f"आप ऑफ़लाइन हैं {EM} इंटरनेट नहीं है") == "आप ऑफ़लाइन हैं, इंटरनेट नहीं है"
    assert clean_text(f"Hello {EM}your partner") == "Hello, your partner"
    assert clean_text(f"a{EM}b") == "a, b"


def test_en_dash_separator_becomes_a_comma() -> None:
    assert clean_text(f"slow {EN} turn on lite mode") == "slow, turn on lite mode"


def test_teachers_verbatim_words_inside_guillemets_are_untouched() -> None:
    text = f"आपके शब्द: «पहले अक्षर जोड़ती हूँ{EM}क... म... ल»"
    assert clean_text(text) == text
    assert clean_text(f"«a {EM} b» {EM} next") == f"«a {EM} b», next"


def test_digit_ranges_are_untouched() -> None:
    assert clean_text(f"Classes 1{EN}3 {EM} all") == f"Classes 1{EN}3, all"
    assert clean_text(f"कक्षा 1{EN}3") == f"कक्षा 1{EN}3"


def test_the_minus_sign_is_untouched() -> None:
    assert clean_text("बोर्ड पर 43 − 27 है") == "बोर्ड पर 43 − 27 है"
    assert clean_text(f"43 − 27 {EM} कैसे?") == "43 − 27, कैसे?"


def test_syllable_hyphens_and_word_hyphens_are_untouched() -> None:
    assert clean_text("मे - ला पढ़ो") == "मे - ला पढ़ो"
    assert clean_text("अभ्यास-साथी") == "अभ्यास-साथी"


def test_citation_lines_are_untouched() -> None:
    cite_line = f"स्रोत: निपुण {EN} भारत, पृष्ठ 4"
    cite = Citation(chunk_id="c1", source_short_hi="निपुण", page=4, line_hi=cite_line)
    msg = OutboundMessage(kind="text", text_hi=f"सुझाव {EM} बंडल से करें\n{cite_line}", citations=[cite])
    normalize_outbound([msg])
    assert msg.text_hi == f"सुझाव, बंडल से करें\n{cite_line}"
    assert (msg.text_hi or "").replace(cite_line, "").strip() == "सुझाव, बंडल से करें"


def test_no_dangling_comma_and_no_doubled_punctuation() -> None:
    assert clean_text(f"ठीक है {EM}") == "ठीक है"
    assert clean_text(f"ठीक है। {EM} आगे") == "ठीक है। आगे"
    assert clean_text(f"{EM} पहला बिंदु") == "पहला बिंदु"


def test_is_idempotent_and_leaves_clean_text_alone() -> None:
    once = clean_text(f"a {EM} b")
    assert clean_text(once) == once
    assert clean_text("कोई डैश नहीं") == "कोई डैश नहीं"


def test_button_titles_are_cleaned_too() -> None:
    m = OutboundMessage(
        kind="buttons", text_hi="x", buttons=[Button(id="b", title_hi=f"हाँ {EM} आगे")]
    )
    normalize_outbound([m])
    assert m.buttons[0].title_hi == "हाँ, आगे"


# Our own files stay dash-free. Files that may keep a dash, with the reason:
ALLOW = {
    "content/sources/sources.yaml": "titles of source documents",
    "backend/app/web/templates/teacher.html": "tab title of the teacher chat (page bytes frozen)",
}


def _rel(paths: list[Path]) -> list[str]:
    return [str(p.relative_to(ROOT)).replace("\\", "/") for p in paths]


OWN_FILES = sorted(
    {
        "content/messages_hi.yaml",
        "content/messages_en.yaml",
        "content/whatsapp_templates.yaml",
        "content/class_struggles.yaml",
        "content/act_examples_hi.yaml",
        "content/level_sorter.yaml",
        "content/handbook_questions.yaml",
        "content/teaching_skills.yaml",
        *_rel(list((ROOT / "content/moves").glob("*.yaml"))),
        *_rel(list((ROOT / "content/personas").glob("*.yaml"))),
        *_rel(list((ROOT / "backend/app/llm/prompts").glob("*.md"))),
        *_rel(list((ROOT / "backend/app/web/templates").glob("*.html"))),
    }
)


def _dash_lines(path: Path) -> list[str]:
    found: list[str] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#") or re.search(r"\{#.*#\}", line):
            continue  # comments are not shown to anyone
        stripped = re.sub(rf"(?<=\d){EN}(?=\d)", "", line)  # a dash between digits is a range
        if EM in stripped or EN in stripped:
            found.append(f"{n}: {line.strip()[:80]}")
    return found


@pytest.mark.parametrize("rel", OWN_FILES)
def test_our_own_text_has_no_em_or_en_dashes(rel: str) -> None:
    path = ROOT / rel
    if not path.exists():
        pytest.skip(f"{rel} not present")
    if rel in ALLOW:
        pytest.skip(ALLOW[rel])
    assert _dash_lines(path) == []


def test_every_model_prompt_that_writes_user_text_forbids_dashes() -> None:
    roles = ("coach", "coach_suggestion", "module_check", "translator", "guide_answerer")
    for role in (*roles, "child_voice"):
        text = (ROOT / f"backend/app/llm/prompts/{role}.v1.md").read_text(encoding="utf-8")
        assert "Never use em dashes or en dashes" in text, role
