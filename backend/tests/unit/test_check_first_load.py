"""Unit tests for check_first_load.py (spec/09 §9.2, spec/14 T47)."""

import pytest

from scripts.check_first_load import (
    AssetMeasurement,
    _extract_asset_paths,
    generate_report,
    measure_first_load,
)


def test_extract_asset_paths_finds_css_js_manifest() -> None:
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <link rel="stylesheet" href="/static/app.css">
        <link rel="manifest" href="/manifest.json">
        <link rel="icon" href="/favicon.ico">
    </head>
    <body>
        <script src="/static/chat.js"></script>
        <script src="/static/recorder.js"></script>
        <script src="https://external.cdn/bundle.js"></script>
    </body>
    </html>
    """
    paths = _extract_asset_paths(html)
    assert "/static/app.css" in paths
    assert "/manifest.json" in paths
    assert "/static/chat.js" in paths
    assert "/static/recorder.js" in paths
    assert "/favicon.ico" not in paths
    assert "https://external.cdn/bundle.js" not in paths


@pytest.mark.asyncio
async def test_measure_first_load_under_150kb() -> None:
    measurements, summary = await measure_first_load()
    assert len(measurements) >= 5
    assert summary["passed"] is True
    assert summary["teacher_bundle_raw_kb"] < 150.0
    assert summary["all_assets_raw_kb"] < 150.0


def test_generate_report_structure() -> None:
    measurements = [
        AssetMeasurement(
            name="Teacher Chat (HTML)",
            path="/teacher",
            kind="HTML",
            raw_bytes=10000,
            gzip_bytes=3000,
            status_code=200,
        ),
        AssetMeasurement(
            name="app.css",
            path="/static/app.css",
            kind="CSS",
            raw_bytes=20000,
            gzip_bytes=4000,
            status_code=200,
        ),
    ]
    summary = {
        "teacher_bundle_raw_bytes": 30000,
        "teacher_bundle_gzip_bytes": 7000,
        "teacher_bundle_raw_kb": 29.3,
        "teacher_bundle_gzip_kb": 6.84,
        "all_assets_raw_bytes": 30000,
        "all_assets_gzip_bytes": 7000,
        "all_assets_raw_kb": 29.3,
        "all_assets_gzip_kb": 6.84,
        "budget_limit_kb": 150.0,
        "passed": True,
    }
    report = generate_report(measurements, summary, label="local, mock providers")
    assert "# First-Load Transfer Size Audit Report" in report
    assert "local, mock providers" in report
    assert "✅ PASSED" in report
    assert "| `app.css` | `/static/app.css` | CSS | 200 |" in report
