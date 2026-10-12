"""Pytest configuration for content tests."""

import sys
from pathlib import Path

# Ensure repository root is on sys.path for content test suite
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
