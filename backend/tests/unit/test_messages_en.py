"""English catalog parity and bilingual-UI hygiene (Hindi stays the default)."""

from __future__ import annotations

import re
import string
from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.app.core.messages import (
    get_message,
    get_ui_lang,
    normalize_lang,
    reset_ui_lang,
    set_ui_lang,
    texts_for_lang,
)

REPO = Path(__file__).resolve().parents[3]
HI: dict[str, Any] = yaml.safe_load((REPO / "content/messages_hi.yaml").read_text("utf-8"))
EN: dict[str, Any] = yaml.safe_load((REPO / "content/messages_en.yaml").read_text("utf-8"))
DEVANAGARI = re.compile("[ऀ-ॿ]")

# English entries that intentionally stay Hindi: words said to Hindi-speaking children, titles
# written into the Hindi content index at ingest time, and the Hindi language name itself.
KEEP_HINDI = {
    "coach_exact_words_contrast_math",
    "coach_exact_words_contrast_lit",
    "ingest_summary_title",
    "ingest_method_title",
    "ingest_key_points_title",
    "ui_lang_name_hi",
}


def _text(entry: Any) -> str:
    return str(entry["text"] if isinstance(entry, dict) else entry)


def _fields(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def test_every_hindi_key_exists_in_english_and_vice_versa() -> None:
    assert set(HI) - set(EN) == set(), f"missing in messages_en.yaml: {sorted(set(HI) - set(EN))}"
    assert set(EN) - set(HI) == set(), f"only in messages_en.yaml: {sorted(set(EN) - set(HI))}"
    assert len(EN) > 400


# English needs a pronoun for the child ("how he got this answer"); the Hindi line does not
ENGLISH_ONLY_FIELDS = {"fu_back_one": {"he"}}


def test_english_placeholders_match_hindi() -> None:
    bad = []
    for key, hi_entry in HI.items():
        want = _fields(_text(hi_entry))
        if isinstance(hi_entry, dict) and hi_entry.get("text_m"):
            assert _fields(str(hi_entry["text_m"])) == want, f"{key}: text_m differs from text"
        got = _fields(_text(EN[key]))
        got -= ENGLISH_ONLY_FIELDS.get(key, set())
        if want != got:
            bad.append((key, sorted(want), sorted(got)))
    assert not bad, f"placeholder mismatch (key, hindi, english): {bad}"


def test_english_texts_are_not_empty_and_have_no_stray_hindi() -> None:
    for key, entry in EN.items():
        text = _text(entry)
        assert text.strip(), key
        if key not in KEEP_HINDI:
            assert not DEVANAGARI.search(text), f"{key} still has Hindi: {text!r}"
    # the keep-list really is Hindi (so it cannot silently become a way to skip translation)
    for key in KEEP_HINDI:
        assert _text(EN[key]) == _text(HI[key])


def test_english_button_titles_fit_whatsapp_limit() -> None:
    for key, entry in EN.items():
        if key.startswith("btn_"):
            assert len(_text(entry)) <= 20, f"{key}: {_text(entry)!r} is over 20 characters"


def _used_keys() -> set[str]:
    used: set[str] = set()
    pattern = re.compile(
        r"""(?:get_message|load_catalog_message|\bm|\bt)\(\s*['"]([a-z][a-z0-9_]+)['"]"""
    )
    for path in [*(REPO / "backend/app").rglob("*.py"), *(REPO / "backend/app").rglob("*.html")]:
        used |= set(pattern.findall(path.read_text("utf-8")))
    for path in (REPO / "backend/app/web/static").glob("*.js"):
        used |= set(re.findall(r"""\bt\(\s*['"`]([a-z][a-z0-9_]+)['"`]""", path.read_text("utf-8")))
    return {k for k in used if k.startswith(("ui_", "speaker_", "btn_"))}


def test_every_key_the_app_references_exists_in_both_catalogs() -> None:
    used = _used_keys()
    assert len(used) > 150
    assert used - set(HI) == set(), f"not in messages_hi.yaml: {sorted(used - set(HI))}"
    assert used - set(EN) == set(), f"not in messages_en.yaml: {sorted(used - set(EN))}"


def test_templates_and_chat_js_have_no_hardcoded_hindi() -> None:
    offenders = []
    for path in (REPO / "backend/app/web/templates").glob("*.html"):
        if DEVANAGARI.search(path.read_text("utf-8")):
            offenders.append(path.name)
    assert not offenders, f"hardcoded Hindi in templates: {offenders}"
    for name in ("recorder.js", "sw.js"):
        assert not DEVANAGARI.search((REPO / "backend/app/web/static" / name).read_text("utf-8"))
    # chat.js keeps only the Hindi child names used to guess whom the teacher is addressing
    for line in (REPO / "backend/app/web/static/chat.js").read_text("utf-8").splitlines():
        if DEVANAGARI.search(line):
            assert line.strip().startswith(("ravi:", "priya:", "aman:", "//", "*")), line


def test_get_message_language_resolution() -> None:
    assert get_message("btn_yes") == "हाँ"
    assert get_message("btn_yes", lang="en") == "Yes"
    token = set_ui_lang("en")
    try:
        assert get_ui_lang() == "en"
        assert get_message("btn_yes") == "Yes"
        assert get_message("btn_yes", lang="hi") == "हाँ"
        # gender variants only exist in Hindi; English ignores address_form
        assert get_message("ask_classes", "m") == get_message("ask_classes", "f")
    finally:
        reset_ui_lang(token)
    assert get_ui_lang() == "hi"
    assert (
        normalize_lang("EN") == "en"
        and normalize_lang("fr") == "hi"
        and normalize_lang(None) == "hi"
    )


def test_texts_for_lang_overlays_english_on_hindi() -> None:
    hi = texts_for_lang("ui_chat_", "hi")
    en = texts_for_lang("ui_chat_", "en")
    assert set(hi) == set(en)
    assert en["ui_chat_msg_sent"] == "Sent" and hi["ui_chat_msg_sent"] == "भेज दिया"


@pytest.mark.parametrize(
    "key", ["ui_chat_translate", "ui_chat_translate_error", "ui_chat_translate_retry"]
)
def test_translate_control_strings_exist_in_both_languages(key: str) -> None:
    assert key in HI and key in EN
