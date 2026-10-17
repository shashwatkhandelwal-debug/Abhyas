#!/usr/bin/env python3
"""Standalone smoke test script for Abhyas deployments (spec/12 §12.9, T30).

Executes a 4-step end-to-end verification without requiring external secrets:
- Step 1: GET /healthz -> 200 OK and valid status ('ok')
- Step 2: GET /login -> extract CSRF token and cookie
- Step 3: POST /login with demo credentials (teacher.demo1 / DEMO_PASSWORD) -> redirect or 200, session cookie
- Step 4: POST /api/chat/text -> 202 Accepted
- Step 5: Prints formatted pass/fail summary and exits 0 on success, 1 on failure.

Usage:
    python scripts/smoke_test.py
    python scripts/smoke_test.py --base-url https://abhyas.onrender.com
    python scripts/smoke_test.py --base-url http://localhost:8000
"""

import argparse
import os
import re
import sys
import uuid
from typing import Any

import httpx

from backend.app.config import settings

CSRF_COOKIE_NAME = "abhyas_csrf"
SESSION_COOKIE_NAME = "abhyas_session"
CSRF_HEADER_NAME = "X-CSRF-Token"


def extract_csrf_token(html_text: str, cookies: httpx.Cookies) -> str | None:
    """Extracts CSRF token from either the HTML form input or the cookie."""
    patterns = [
        r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']',
        r'value=["\']([^"\']+)["\']\s+name=["\']csrf_token["\']',
    ]
    for pat in patterns:
        match = re.search(pat, html_text)
        if match:
            return match.group(1)

    return cookies.get(CSRF_COOKIE_NAME)


def run_smoke_test(
    base_url: str,
    client: httpx.Client | None = None,
    password: str | None = None,
) -> bool:
    """Executes the 4 smoke test steps against base_url."""
    effective_password = password or os.environ.get("DEMO_PASSWORD") or settings.DEMO_PASSWORD
    base_url = base_url.rstrip("/")
    print("=" * 60)
    print("Abhyas Deployment Smoke Test")
    print(f"Target URL: {base_url}")
    print("=" * 60)

    steps: list[tuple[str, bool, str]] = []

    close_client = False
    if client is None:
        client = httpx.Client(base_url=base_url, follow_redirects=False, timeout=15.0)
        close_client = True

    all_passed = False
    try:
        # Step 1: GET /healthz -> 200 OK and valid status
        print("\n[Step 1/4] Checking liveness probe (GET /healthz)...")
        try:
            r1 = client.get("/healthz")
            if r1.status_code == 200 and r1.json().get("status") == "ok":
                git_sha = r1.json().get("git_sha", "unknown")
                msg = f"HTTP {r1.status_code} OK (git_sha: {git_sha})"
                print(f"  PASS: {msg}")
                steps.append(("GET /healthz", True, msg))
            else:
                msg = f"Unexpected response: HTTP {r1.status_code}, Body: {r1.text[:200]}"
                print(f"  FAIL: {msg}")
                steps.append(("GET /healthz", False, msg))
                return False
        except Exception as exc:
            msg = f"Connection error: {exc}"
            print(f"  FAIL: {msg}")
            steps.append(("GET /healthz", False, msg))
            return False

        # Step 2: GET /login -> extract CSRF token and cookie
        print("\n[Step 2/4] Fetching login page and CSRF token (GET /login)...")
        csrf_token: str | None = None
        try:
            r2 = client.get("/login")
            csrf_token = extract_csrf_token(r2.text, client.cookies)
            csrf_cookie = client.cookies.get(CSRF_COOKIE_NAME)

            if r2.status_code == 200 and csrf_token and csrf_cookie:
                msg = f"HTTP 200 OK (CSRF cookie & token acquired: {csrf_token[:8]}...)"
                print(f"  PASS: {msg}")
                steps.append(("GET /login (CSRF)", True, msg))
            else:
                msg = (
                    f"HTTP {r2.status_code}, csrf_token={bool(csrf_token)}, "
                    f"csrf_cookie={bool(csrf_cookie)}"
                )
                print(f"  FAIL: {msg}")
                steps.append(("GET /login (CSRF)", False, msg))
                return False
        except Exception as exc:
            msg = f"Error: {exc}"
            print(f"  FAIL: {msg}")
            steps.append(("GET /login (CSRF)", False, msg))
            return False

        # Step 3: POST /login with demo credentials
        print("\n[Step 3/4] Authenticating demo teacher (POST /login)...")
        try:
            login_data = {
                "username": "teacher.demo1",
                "password": effective_password,
                "csrf_token": csrf_token,
            }
            r3 = client.post("/login", data=login_data)
            session_cookie = client.cookies.get(SESSION_COOKIE_NAME)

            if r3.status_code in (200, 302, 303) and session_cookie:
                redirect_loc = r3.headers.get("location", "N/A")
                msg = (
                    f"HTTP {r3.status_code} (Redirect: {redirect_loc}, "
                    f"Session cookie acquired: {session_cookie[:8]}...)"
                )
                print(f"  PASS: {msg}")
                steps.append(("POST /login", True, msg))
            else:
                msg = (
                    f"HTTP {r3.status_code}, session_cookie={bool(session_cookie)}, "
                    f"Body: {r3.text[:200]}"
                )
                print(f"  FAIL: {msg}")
                steps.append(("POST /login", False, msg))
                return False
        except Exception as exc:
            msg = f"Error: {exc}"
            print(f"  FAIL: {msg}")
            steps.append(("POST /login", False, msg))
            return False

        # Step 4: POST /api/chat/text -> 202 Accepted
        print("\n[Step 4/4] Sending inbound chat message (POST /api/chat/text)...")
        try:
            chat_headers = {
                CSRF_HEADER_NAME: csrf_token or "",
                "Content-Type": "application/json",
            }
            chat_payload = {
                "client_msg_id": str(uuid.uuid4()),
                "text": "नमस्ते, मैं अभ्यास शुरू करना चाहती हूँ।",
            }
            r4 = client.post("/api/chat/text", json=chat_payload, headers=chat_headers)
            if r4.status_code == 202:
                resp_data: dict[str, Any] = {}
                if r4.headers.get("content-type", "").startswith("application/json"):
                    resp_data = r4.json()
                msg = f"HTTP 202 Accepted (Message ID: {resp_data.get('message_id', 'N/A')})"
                print(f"  PASS: {msg}")
                steps.append(("POST /api/chat/text", True, msg))
            else:
                msg = f"HTTP {r4.status_code}, Body: {r4.text[:200]}"
                print(f"  FAIL: {msg}")
                steps.append(("POST /api/chat/text", False, msg))
                return False
        except Exception as exc:
            msg = f"Error: {exc}"
            print(f"  FAIL: {msg}")
            steps.append(("POST /api/chat/text", False, msg))
            return False

        all_passed = True
        return True

    finally:
        if close_client:
            client.close()

        # Step 5: Prints formatted pass/fail summary
        print("\n" + "=" * 60)
        print("Smoke Test Summary")
        print("=" * 60)
        passed_count = sum(1 for _, p, _ in steps if p)
        for name, passed, detail in steps:
            status_str = "PASS" if passed else "FAIL"
            print(f"[{status_str:4s}] {name:25s} - {detail}")

        if all_passed and len(steps) == 4:
            print("\nResult: ALL SMOKE TESTS PASSED (Deployment is healthy).")
        else:
            print(f"\nResult: SMOKE TESTS FAILED ({passed_count}/{len(steps)} passed).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run post-deployment smoke tests against an Abhyas instance."
    )
    default_url = os.environ.get("APP_BASE_URL", "http://localhost:8000")
    parser.add_argument(
        "--base-url",
        default=default_url,
        help=f"Base URL of Abhyas instance (default: {default_url})",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Password for demo user (default: env DEMO_PASSWORD or settings.DEMO_PASSWORD)",
    )
    args = parser.parse_args()

    success = run_smoke_test(base_url=args.base_url, password=args.password)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
