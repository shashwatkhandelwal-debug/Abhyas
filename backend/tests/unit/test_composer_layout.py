"""The composer must stay on screen: pinned outside the scrolling chat, strips above it bounded.

These are structural checks on the template and the stylesheet. The geometry itself (input inside
the viewport at 360x640 and 412x915, keyboard open, both themes) is checked in a real browser by
scripts/composer_layout_check.py.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "app" / "web"
HTML = (WEB / "templates" / "teacher.html").read_text(encoding="utf-8")
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    """The declarations of the last rule whose selector list is exactly `selector`."""
    found = re.findall(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert found, selector
    return found[-1]


def test_input_and_controls_sit_outside_the_scrolling_region() -> None:
    chat_start = HTML.index('<main class="chat-messages"')
    chat_end = HTML.index("</main>")
    for marker in ('id="chat-input"', 'id="btn-mic"', 'id="btn-send"'):
        assert HTML.index(marker) > chat_end, marker
        assert not chat_start < HTML.index(marker) < chat_end
    assert HTML.index('class="composer-wrapper"') > chat_end


def test_chat_is_the_only_scrolling_region_of_a_fixed_shell() -> None:
    assert "overflow-y: auto" in _rule(".chat-messages")
    rule = _rule(".chat-page .app-container > .chat-messages")
    assert "flex: 1 1 auto" in rule
    assert re.search(r"min-height:\s*0", rule)
    assert "overflow: hidden" in _rule(".chat-page .app-container")
    shell = _rule(".chat-page")
    assert "position: fixed" in shell and "inset: 0" in shell
    assert "vh" not in shell  # the shell is the visible viewport, never a vh height


def test_every_zone_but_the_message_list_keeps_its_height() -> None:
    assert "flex: none" in _rule(".chat-page .app-container > *")
    assert "overflow: hidden" in _rule(".chat-page .app-container")


def test_dock_holds_actions_hint_and_composer_below_the_list() -> None:
    chat_end = HTML.index("</main>")
    dock = HTML.index('<div class="dock" id="dock">')
    assert dock > chat_end
    for marker in (
        'id="action-row"',
        'id="next-card"',
        'class="composer-wrapper"',
        'id="btn-suggest"',
    ):
        assert HTML.index(marker) > dock, marker
    assert "max-height: 56px" in _rule(".action-row")
    assert "max-height: 112px" in _rule(".action-row.few")
    assert "safe-area-inset-bottom" in _rule(".dock .composer-wrapper")


def test_suggestion_sheet_is_bounded_closed_and_above_the_dock() -> None:
    sheet = _rule(".sheet")
    assert "overflow-y: auto" in sheet and "bottom: 100%" in sheet
    assert re.search(r"max-height:\s*55dvh", sheet)
    assert re.search(r'<div class="sheet" id="sheet"[^>]* hidden>', HTML)
    assert re.search(
        r'<details class="sample-tray" id="sample-tray"\s*>', HTML
    )  # closed by default
    assert re.search(r'<details class="fast-track-tray" id="fast-track-tray">', HTML)
    assert re.search(r'<details class="sheet-sec" id="sheet-handbook" open>', HTML)
    sheet_html = HTML[HTML.index('id="sheet"') : HTML.index('id="action-row"')]
    for part in ("sheet-handbook", "sample-tray", "fast-track-tray", 'id="sheet-close"'):
        assert part in sheet_html, part
    assert 'class="helper-tray"' not in HTML


def test_keyboard_class_drops_the_optional_strips_and_the_keyboard_resizes_the_page() -> None:
    assert ".kb .demo-banner" in CSS and ".kb .next-card" in CSS and ".kb .sheet" in CSS
    assert ".kb.chat-page .scene-bar" in CSS
    assert "interactive-widget=resizes-content" in HTML
