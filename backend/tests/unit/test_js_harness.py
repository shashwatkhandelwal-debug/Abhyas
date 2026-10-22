"""Runs the Node test files under backend/tests/js (service worker, chat.js state machines).

The JS is vanilla with no build step, so `node --test` is the whole harness. Skipped where
Node is not installed (CI installs it; see .github/workflows).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

JS_DIR = Path(__file__).resolve().parent.parent / "js"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_node_suite_passes() -> None:
    files = sorted(str(p) for p in JS_DIR.glob("*.test.mjs"))
    assert files, "no JS test files found"
    result = subprocess.run(  # noqa: S603
        [str(NODE), "--test", *files],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
