"""fix11: the trainer batch table must not squeeze the move-name column (CSS rules in the template)."""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "app" / "web" / "templates"
HTML = (TEMPLATES / "trainer.html").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", HTML)
    assert m, f"missing CSS rule {selector}"
    return m.group(1)


def test_move_column_has_min_width_and_wraps() -> None:
    body = _rule("table.data-table td.move-cell")
    assert "min-width: 12rem" in body
    assert "word-break" not in body and "overflow: hidden" not in body
    assert 'class="move-cell"' in HTML


def test_batch_column_min_width_and_nowrap_code() -> None:
    assert "min-width: 9rem" in _rule("table.data-table td.batch-cell")
    assert "white-space: nowrap" in _rule("table.data-table td.batch-cell strong")


def test_table_scrolls_instead_of_squeezing() -> None:
    assert 'class="table-card table-scroll"' in HTML
    assert "overflow-x: auto" in (TEMPLATES / "_dash_css.html").read_text(encoding="utf-8")
    assert "min-width: 0" in _rule(".table-scroll table.data-table")
    narrow = HTML.split("@media (max-width: 1099px)", 1)[1]
    assert re.search(r"min-width:\s*(\d+)rem", narrow.split("}", 1)[0])


def test_misconception_text_light_red_in_dark_only() -> None:
    assert "color: #9B1C1C" in _rule("table.data-table td.missed-cell")
    dark = HTML.split("@media (prefers-color-scheme: dark)", 1)[1]
    assert "td.missed-cell { color: #ffb4a8; }" in dark
    assert 'class="missed-cell"' in HTML


def test_missed_cell_max_width_and_ladder_wraps() -> None:
    assert "max-width: 14rem" in _rule("table.data-table td.missed-cell")
    assert "flex-wrap: wrap" in _rule(".ladder-tags")
    assert 'class="ladder-tag"' in HTML


def test_empty_states_use_i18n_not_hardcoded() -> None:
    assert "ui_trainer_no_misconception" in HTML
    assert "ui_trainer_no_scores" in HTML
    assert "No misconception flagged" not in HTML and "कोई भ्रांति" not in HTML
    from backend.app.core.messages import get_message  # noqa: PLC0415

    assert get_message("ui_trainer_no_misconception")
    assert get_message("ui_trainer_no_scores")
