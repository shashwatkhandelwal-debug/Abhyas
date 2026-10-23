"""Build stamp for the shipped static files (service worker cache name and asset URLs)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from backend.app.config import settings

STATIC_DIR = Path(__file__).resolve().parent / "static"

SW_VERSIONED_ASSETS = ("sw.js", "chat.js", "recorder.js", "app.css", "manifest.json")


def sw_build_version() -> str:
    """Cache-busting id: deploy SHA plus a digest of the shipped static files.

    The digest keeps the version moving when GIT_SHA is unset ("dev") or stale, so a changed
    chat.js can never be served from a cache named after an older build. The same id is put in
    the asset URLs (`/static/chat.js?v=<id>`), so a page from a new build never asks for a file
    by a URL an older build's cache (service worker or browser) already holds.
    """
    digest = hashlib.sha1(usedforsecurity=False)
    for name in SW_VERSIONED_ASSETS:
        path = STATIC_DIR / name
        if path.is_file():
            digest.update(path.read_bytes())
    sha = re.sub(r"[^A-Za-z0-9]", "", settings.GIT_SHA)[:12] or "dev"
    return f"{sha}-{digest.hexdigest()[:8]}"
