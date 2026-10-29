"""Demo shortcuts tray: markup, catalogue titles and theme tokens (behaviour is in chat.test.mjs)."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
HTML = (ROOT / "backend/app/web/templates/teacher.html").read_text(encoding="utf-8")
CSS = (ROOT / "backend/app/web/static/app.css").read_text(encoding="utf-8")
JS = (ROOT / "backend/app/web/static/chat.js").read_text(encoding="utf-8")


def _msg(lang: str, key: str) -> str:
    data = yaml.safe_load((ROOT / f"content/messages_{lang}.yaml").read_text(encoding="utf-8"))
    return str(data[key]["text"])


def _tray() -> str:
    start = HTML.index('<details class="fast-track-tray"')
    return HTML[start : HTML.index("</details>", start)]


def test_tray_starts_collapsed() -> None:
    assert re.match(r'<details class="fast-track-tray" id="fast-track-tray">', _tray())


def test_only_chip_c_is_visible_and_enabled_in_the_served_markup() -> None:
    tray = _tray()
    for chip in ("a1", "a2", "b"):
        tag = re.search(rf'<button[^>]*id="ft-chip-{chip}"[^>]*>', tray)
        assert tag and " hidden" in tag.group(0) and " disabled" in tag.group(0), chip
    tag_c = re.search(r'<button[^>]*id="ft-chip-c"[^>]*>', tray)
    assert tag_c and " hidden" not in tag_c.group(0) and " disabled" not in tag_c.group(0)


def test_title_is_renamed_in_both_languages_and_hint_explains_the_wait() -> None:
    assert _msg("hi", "ui_fast_track_title") == "डेमो शॉर्टकट"
    assert _msg("en", "ui_fast_track_title") == "Demo shortcuts"
    assert "30" in _msg("hi", "ui_fast_track_hint")
    assert "30 seconds" in _msg("en", "ui_fast_track_hint")
    assert "ui_fast_track_hint" in _tray()


def test_tray_uses_the_app_theme_tokens_so_dark_mode_is_not_a_white_card() -> None:
    block = CSS[CSS.index(".fast-track-tray {") : CSS.index(".network-banner {")]
    for token in ("--surface", "--ink", "--border", "--muted", "--bg", "--brand"):
        assert f"var({token})" in block, token
    # tokens that do not exist in the stylesheet fall back to light-only colours
    for dead in ("--surface-2", "--text-muted", "--primary"):
        assert dead not in block
    assert "#FFF" not in block


def test_idle_delay_is_one_named_constant() -> None:
    assert re.search(r"^const FAST_TRACK_IDLE_MS = 30000;$", JS, re.M)
    assert JS.count("FAST_TRACK_IDLE_MS") == 2  # its definition and its one use
