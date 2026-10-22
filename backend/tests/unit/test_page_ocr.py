"""page_ocr: cache by image hash, budget stop, guard handling and OCR text clean-up (no network)."""

import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from backend.app.retrieval import page_ocr

HINDI_PAGE = "## घटाव\n" + " ".join(["बच्चों को बंडल खोलकर घटाव समझाएँ।"] * 12)


def _make_pdf(path: Path, pages: int = 2) -> None:
    pymupdf: Any = importlib.import_module("pymupdf")
    doc = pymupdf.open()
    for n in range(pages):
        page = doc.new_page(width=300, height=400)
        page.insert_text((50, 100 + n * 20), f"page {n}")  # different pixels per page
    doc.save(str(path))


class _FakeClient:
    def __init__(self, text: str, in_tok: int = 3000, out_tok: int = 1500) -> None:
        self.calls = 0
        self._text, self._in, self._out = text, in_tok, out_tok
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **_kw: Any) -> Any:
        self.calls += 1
        block = SimpleNamespace(
            type="tool_use",
            input={"text_hi": self._text, "printed_page": 7, "legibility": "clear"},
        )
        usage = SimpleNamespace(input_tokens=self._in, output_tokens=self._out)
        return SimpleNamespace(content=[block], usage=usage)


@pytest.fixture
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    _make_pdf(tmp_path / "guide.pdf")
    monkeypatch.setattr(page_ocr, "SOURCES_DIR", tmp_path)
    monkeypatch.setattr(page_ocr, "CACHE_DIR", tmp_path / "ocr_cache")
    return {"id": "guide_x", "file": "guide.pdf"}


def _patch_client(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> None:
    monkeypatch.setattr(page_ocr.anthropic, "AsyncAnthropic", lambda **_k: client)


async def test_second_run_is_served_from_the_hash_cache(
    source: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _FakeClient(HINDI_PAGE)
    _patch_client(monkeypatch, client)
    first, _ = await page_ocr.run_ocr(source)
    assert (first.pages_called, first.pages_cached, client.calls) == (2, 0, 2)
    assert first.input_tokens == 6000 and first.output_tokens == 3000
    assert first.cost_usd == pytest.approx(6000 * 0.10e-6 + 3000 * 0.50e-6)

    second, pages = await page_ocr.run_ocr(source)
    assert (second.pages_called, second.pages_cached, client.calls) == (0, 2, 2)
    assert second.cost_usd == 0.0 and all(p.from_cache for p in pages)


async def test_run_stops_before_exceeding_the_budget(
    source: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _FakeClient(HINDI_PAGE)
    _patch_client(monkeypatch, client)
    report, _ = await page_ocr.run_ocr(source, budget_usd=0.00001)
    assert report.stopped_for_budget and report.pages_called == 0 and client.calls == 0


async def test_non_devanagari_output_is_flagged_unreliable(
    source: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(monkeypatch, _FakeClient("fjehfM;y dh xfrfof/k lanf'kZdk ls ns[ksaA " * 10))
    report, pages = await page_ocr.run_ocr(source)
    assert report.pages_unreliable == 2 and not any(p.guard_ok for p in pages)


async def test_load_ocr_pages_needs_the_cache_then_builds_lines(
    source: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(FileNotFoundError):
        page_ocr.load_ocr_pages(source)
    _patch_client(monkeypatch, _FakeClient(HINDI_PAGE))
    await page_ocr.run_ocr(source)
    pages = page_ocr.load_ocr_pages(source)
    assert [p.pdf_page for p in pages] == [1, 2] and pages[0].printed == 7
    assert pages[0].lines[0].heading and pages[0].lines[0].text == "घटाव"
    assert not pages[0].skipped


def test_legacy_font_runs_are_dropped_but_real_english_kept() -> None:
    line, dropped = page_ocr.strip_legacy_font_runs(
        "तैयारी : fjehfM;y dh xfrfof/k lanf'kZdk ls ns[ksaA"
    )
    assert line == "तैयारी :" and dropped == 6
    assert page_ocr.strip_legacy_font_runs("Count on पद्धति से जोड़") == ("Count on पद्धति से जोड़", 0)


def test_letter_grid_pages_are_detected() -> None:
    assert page_ocr.is_letter_grid("## ग्रिड-4\nल | ली | स | सी\nप | पी | ब | बी")
    assert not page_ocr.is_letter_grid(HINDI_PAGE)
