"""Static checks for the chat acknowledgment UI: catalog coverage, contrast, motion, size."""

import re
from pathlib import Path

import yaml

from backend.app.web.teacher import CHAT_UI_PREFIX, STATIC_DIR

ROOT = Path(__file__).resolve().parents[3]
CATALOG = yaml.safe_load((ROOT / "content" / "messages_hi.yaml").read_text(encoding="utf-8"))
CHAT_JS = (STATIC_DIR / "chat.js").read_text(encoding="utf-8")
APP_CSS = (STATIC_DIR / "app.css").read_text(encoding="utf-8")
TEMPLATES = ROOT / "backend" / "app" / "web" / "templates"
CHAT_KEYS = {k for k in CATALOG if k.startswith(CHAT_UI_PREFIX)}

# Keys chat.js builds from a prefix at runtime: t(`ui_chat_msg_${st}`), t(`ui_chat_typing_${speaker}`)
DYNAMIC_KEYS = {
    "ui_chat_msg_sending",
    "ui_chat_msg_sent",
    "ui_chat_msg_failed",
    "ui_chat_typing_ravi",
    "ui_chat_typing_priya",
    "ui_chat_typing_aman",
}


def test_every_string_chat_js_uses_exists_in_the_catalog() -> None:
    literal = set(re.findall(r"""['"`](ui_[a-z0-9_]+)['"`]""", CHAT_JS))
    missing = (literal | DYNAMIC_KEYS) - set(CATALOG)
    assert not missing, f"chat.js references keys missing from messages_hi.yaml: {sorted(missing)}"
    # the dynamic-key families chat.js builds must be fully covered
    assert re.search(r"ui_chat_msg_\$\{", CHAT_JS) and re.search(r"ui_chat_typing_\$\{", CHAT_JS)


def test_no_unused_chat_strings_in_catalog() -> None:
    template_text = "".join(p.read_text(encoding="utf-8") for p in TEMPLATES.glob("*.html"))
    used = set(re.findall(r"""['"`](ui_chat_[a-z0-9_]+)['"`]""", CHAT_JS + template_text))
    used |= DYNAMIC_KEYS
    assert CHAT_KEYS <= used, f"unused ui_chat_* catalog keys: {sorted(CHAT_KEYS - used)}"


def test_new_ui_has_no_hardcoded_hindi_in_chat_js() -> None:
    """Hindi in chat.js is limited to the pre-existing literals (speaker labels, lite-mode label,
    'अभी' fallback); everything the acknowledgment UI shows comes from the catalog."""
    allowed = (
        "अभ्यास",
        "कोच",
        "आदर्श शिक्षिका",
        "रवि",
        "प्रिया",
        "अमन",
        "लाइट मोड",
        "चालू",
        "बंद",
        "अभी",
    )
    offenders: list[str] = []
    for line in CHAT_JS.splitlines():
        code = line.split("//", 1)[0] if not re.search(r"['\"`].*//", line) else line
        for literal in re.findall(r"""(['"`])((?:(?!\1).)*[\u0900-\u097F](?:(?!\1).)*)\1""", code):
            text = literal[1]
            stripped = text
            for word in allowed:
                stripped = stripped.replace(word, "")
            if re.search(r"[\u0900-\u097F]", stripped):
                offenders.append(text)
    assert not offenders, f"hardcoded Hindi in chat.js (move to messages_hi.yaml): {offenders}"


def _custom_props(block: str) -> dict[str, str]:
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9A-Fa-f]{6})\s*;", block))


def _themes() -> tuple[dict[str, str], dict[str, str]]:
    dark_blocks = re.findall(
        r"@media \(prefers-color-scheme: dark\)\s*\{\s*:root\s*\{(.*?)\}\s*\}", APP_CSS, re.S
    )
    light_css = re.sub(
        r"@media \(prefers-color-scheme: dark\)\s*\{\s*:root\s*\{.*?\}\s*\}",
        "",
        APP_CSS,
        flags=re.S,
    )
    light: dict[str, str] = {}
    for block in re.findall(r":root\s*\{(.*?)\}", light_css, re.S):
        light.update(_custom_props(block))
    dark = dict(light)
    for block in dark_blocks:
        dark.update(_custom_props(block))
    return light, dark


def _luminance(hex_color: str) -> float:
    rgb = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_status_text_contrast_is_at_least_4_5_in_light_and_dark() -> None:
    pairs = [
        ("--status-meta", "--bubble-in"),  # ticks, time, voice-note status line
        ("--status-meta", "--bubble-out"),
        ("--status-meta", "--surface"),
        ("--status-ink", "--status-bg"),  # reconnecting bar
        ("--status-ink", "--surface"),  # typing bubble
        ("--status-warn-ink", "--status-warn-bg"),  # cold-start bar, typing timeout
        ("--status-danger-ink", "--status-danger-bg"),  # notice bar, audio error
        ("--brand-ink", "--brand"),  # pressed chip, play button
    ]
    for name, theme in zip(("light", "dark"), _themes(), strict=True):
        for fg, bg in pairs:
            ratio = _contrast(theme[fg], theme[bg])
            assert ratio >= 4.5, f"{name}: {fg} on {bg} = {ratio:.2f}:1"
    # the white "!" on the failed-bubble badge
    for theme in _themes():
        assert _contrast("#FFFFFF", theme["--danger"]) >= 4.5


def test_source_excerpt_contrast_is_at_least_4_5_in_light_and_dark() -> None:
    """A1: cited-source excerpt and error panels meet WCAG AA contrast in both themes."""
    pairs = [
        ("--source-excerpt-ink", "--source-excerpt-bg"),
        ("--source-excerpt-note", "--source-excerpt-bg"),
        ("--source-error-ink", "--source-error-bg"),
    ]
    for name, theme in zip(("light", "dark"), _themes(), strict=True):
        for fg, bg in pairs:
            ratio = _contrast(theme[fg], theme[bg])
            assert ratio >= 4.5, f"{name}: {fg} on {bg} = {ratio:.2f}:1"


def test_reduced_motion_and_tap_targets() -> None:
    assert "@media (prefers-reduced-motion: reduce)" in APP_CSS
    reduced = APP_CSS.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert "animation-duration" in reduced and "transition-duration" in reduced
    # 44 px minimum: audio button, failed-bubble hit area (18 px glyph + 2 x 13 px inset)
    play = re.search(
        r"\.btn-play \{[^}]*min-width: (\d+)px;[^}]*min-height: (\d+)px", APP_CSS, re.S
    )
    assert play and int(play[1]) >= 44 and int(play[2]) >= 44
    assert "inset: -13px" in APP_CSS
    # one-off transitions in the acknowledgment UI stay under 300 ms
    ack_css = APP_CSS.split("Visible acknowledgment states", 1)[1]
    for seconds in re.findall(r"transition:[^;]*?([\d.]+)s", ack_css):
        assert float(seconds) < 0.3


def test_first_load_budget_still_met() -> None:
    sizes = [(STATIC_DIR / n).stat().st_size for n in ("chat.js", "recorder.js", "app.css")]
    html = (TEMPLATES / "teacher.html").stat().st_size
    assert sum(sizes) + html < 150 * 1024
