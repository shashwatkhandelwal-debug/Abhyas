"""CSV downloads of the tables on the ARP, trainer and coach pages.

The CSV is cut out of the page's own HTML: the export route renders the same page, with the same
role check and the same data (so the same n<10 suppression), and copies every
`<table data-export="NAME">` out of it. What the page shows is exactly what the file holds. A cell
marked `data-csv-skip` (links, free text) is left out; a cell with `data-csv="..."` exports that
value instead of its text (for example the rubric dots). A cell spanning several columns repeats
the suppression text in each of them, never a hidden number.

The file is UTF-8 with a byte-order mark (Excel opens Hindi correctly), served as an attachment
named abhyas_<view>_<table>_<YYYY-MM-DD>.csv. Each export is logged (role, view, table, time), with
no personal data.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Response, status

from backend.app.auth.access import SUPPRESSION_MESSAGE

logger = logging.getLogger("abhyas.export")
IST = ZoneInfo("Asia/Kolkata")
BOM = "﻿"
_SAFE_NAME = re.compile(r"^[a-z0-9_]+$")
_FORMULA_START = ("=", "+", "@")


class _Tables(HTMLParser):
    """Collects the `data-export` tables: name -> rows of cell text."""

    def __init__(self, repeat_text: str) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: dict[str, list[list[str]]] = {}
        self._repeat = repeat_text
        self._name: str | None = None
        self._depth = 0
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._cell_attrs: dict[str, str | None] = {}
        self._hidden = 0  # inside <script>, <style> or <svg>

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            if self._name is not None:
                self._depth += 1
            elif attributes.get("data-export"):
                self._name = str(attributes["data-export"])
                self._depth = 1
                self.tables[self._name] = []
            return
        if self._name is None:
            return
        if tag in ("script", "style", "svg"):
            self._hidden += 1
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            self._cell_attrs = attributes
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self._name is None:
            return
        if tag in ("script", "style", "svg"):
            self._hidden = max(0, self._hidden - 1)
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._end_cell()
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.tables[self._name].append(self._row)
            self._row = None
        elif tag == "table":
            self._depth -= 1
            if self._depth == 0:
                self._name = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None and not self._hidden:
            self._cell.append(data)

    def _end_cell(self) -> None:
        assert self._cell is not None and self._row is not None
        attributes = self._cell_attrs
        cell, self._cell = self._cell, None
        if "data-csv-skip" in attributes:
            return
        override = attributes.get("data-csv")
        text = " ".join((override if override is not None else "".join(cell)).split())
        try:
            span = max(1, int(attributes.get("colspan") or 1))
        except ValueError:
            span = 1
        self._row.append(text)
        self._row.extend([text if text == self._repeat else ""] * (span - 1))


def tables_from_html(html: str) -> dict[str, list[list[str]]]:
    """Every `data-export` table of a rendered page: name -> rows (header row first)."""
    parser = _Tables(SUPPRESSION_MESSAGE)
    parser.feed(html)
    parser.close()
    return parser.tables


def _safe_cell(text: str) -> str:
    """A cell that a spreadsheet would read as a formula gets a leading apostrophe."""
    if text.startswith(_FORMULA_START) or (
        text.startswith("-") and len(text) > 1 and not text[1:].replace(".", "").isdigit()
    ):
        return "'" + text
    return text


def csv_text(rows: list[list[str]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    for row in rows:
        writer.writerow([_safe_cell(c) for c in row])
    return BOM + out.getvalue()


def export_response(*, role: str, view: str, table: str, html: str) -> Response:
    """The CSV attachment for one table of a rendered page, or 404 when the page has no such table."""
    if not _SAFE_NAME.match(table):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    rows = tables_from_html(html).get(table)
    if rows is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    today = datetime.now(IST).strftime("%Y-%m-%d")
    logger.info(
        "csv_export role=%s view=%s table=%s at=%s",
        role,
        view,
        table,
        datetime.now(UTC).isoformat(timespec="seconds"),
    )
    return Response(
        content=csv_text(rows).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="abhyas_{view}_{table}_{today}.csv"',
            "Cache-Control": "no-store",
        },
    )


__all__ = ["csv_text", "export_response", "tables_from_html"]
