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


def test_chat_scrolls_inside_itself_and_keeps_a_floor() -> None:
    assert "overflow-y: auto" in _rule(".chat-messages")
    rule = _rule(".chat-page .app-container > .chat-messages")
    assert "flex: 1 1 auto" in rule
    assert re.search(r"min-height:\s*6rem", rule)
    assert "overflow: hidden" in _rule(".chat-page .app-container")


def test_header_and_composer_never_shrink_and_strips_between_them_do() -> None:
    assert "flex: none" in _rule(
        ".chat-page .app-container > .chat-header, .chat-page .app-container > .composer-wrapper"
    )
    strips = _rule(".chat-page .app-container > *")
    assert "flex: 0 1 auto" in strips
    assert "min-height: 0" in strips
    assert "overflow-y: auto" in strips


def test_suggestion_area_is_bounded_and_scrolls_inside_itself() -> None:
    tray = _rule(".helper-tray")
    assert "overflow-y: auto" in tray
    assert re.search(r"max-height:\s*min\(34vh,\s*7\.5rem\)", tray)
    # the handbook chips and the sample line are single scrolling rows
    assert (
        "overflow-x: auto" in _rule(".sample-list,\n.handbook-chips") or "overflow-x: auto" in CSS
    )
    assert '<details class="sample-tray"' in HTML  # collapsible, closed by default
    assert re.search(r'<details class="sample-tray" id="sample-tray"\s*>', HTML)


def test_short_viewports_drop_the_optional_strips_and_the_keyboard_resizes_the_page() -> None:
    media = re.search(r"@media \(max-height: 560px\) \{([^}]*)\}", CSS)
    assert media
    for selector in (".helper-tray", ".demo-banner", ".fast-track-tray"):
        assert selector in media.group(1)
    assert "interactive-widget=resizes-content" in HTML
    assert "height: 100vh; height: 100dvh" in _rule(".chat-page")
