"""Unit tests for scripts/freeze_check.py (the pieces that do not need a git repo or the gates)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from scripts import freeze_check as fc


def test_secret_scan_finds_key_shaped_strings_and_ignores_variable_names() -> None:
    # Built at run time so this file does not itself look like a leaked key
    fake_anthropic = "sk-" + "ant-" + "a" * 30
    fake_google = "AI" + "za" + "b" * 35
    fake_pem = "-----BEGIN " + "PRIVATE KEY-----"
    assert fc.scan_text_for_secrets(f"key = {fake_anthropic}") == ["Anthropic key"]
    assert fc.scan_text_for_secrets(fake_google) == ["Google API key"]
    assert fc.scan_text_for_secrets(fake_pem) == ["Private key block"]
    assert fc.scan_text_for_secrets("ANTHROPIC_API_KEY=\nGEMINI_API_KEY=your-key-here") == []
    assert fc.scan_text_for_secrets("sk-ant-short") == []


PROGRESS = """
# Notes
### Allowed placeholders
Some prose.

- `<HOSTED URL>`: docs/A.md, docs/B.md
- `<DEMO_PASSWORD>`: docs/A.md
## Next section
- `<ADMIN_PASSWORD>`: docs/C.md
"""


def test_allowed_placeholders_are_read_only_from_their_section() -> None:
    allowed = fc.allowed_placeholders(PROGRESS)
    assert allowed["<HOSTED URL>"] == {"docs/A.md", "docs/B.md"}
    assert allowed["<DEMO_PASSWORD>"] == {"docs/A.md"}
    assert allowed["<ADMIN_PASSWORD>"] == set()  # listed after the section ended


def test_unfilled_placeholders_outside_the_allowed_files_are_reported() -> None:
    allowed = fc.allowed_placeholders(PROGRESS)
    docs = {
        "docs/A.md": "open <HOSTED URL> with <DEMO_PASSWORD>",
        "docs/B.md": "<HOSTED URL> only",
        "README.md": "go to <HOSTED URL>",
        "docs/D.md": "admin <ADMIN_PASSWORD>",
    }
    assert fc.find_unfilled(docs, allowed) == [
        "README.md <HOSTED URL>",
        "docs/D.md <ADMIN_PASSWORD>",
    ]
    assert fc.find_unfilled({"docs/A.md": "all filled in"}, allowed) == []
    assert fc.allowed_placeholders("no section here")["<HOSTED URL>"] == set()


def test_the_repo_itself_has_no_unlisted_placeholders() -> None:
    assert fc.check_doc_placeholders().status == "PASS"


def test_sha_match_accepts_short_or_full_and_rejects_dev_or_other() -> None:
    head = "9e3c06a1b2c3d4e5f60718293a4b5c6d7e8f9012"
    assert fc.sha_matches("9e3c06a", head)
    assert fc.sha_matches(head, head)
    assert not fc.sha_matches("dev", head)
    assert not fc.sha_matches("abcdef1", head)
    assert not fc.sha_matches("", head)


class _Health(BaseHTTPRequestHandler):
    sha = "abcdef1234"
    ok = True

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz" and self.ok:
            body = json.dumps({"status": "ok", "git_sha": self.sha}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(503)
            self.end_headers()

    def log_message(self, *_a: Any) -> None:
        pass


def _serve(sha: str, ok: bool) -> tuple[HTTPServer, str]:
    handler = type("H", (_Health,), {"sha": sha, "ok": ok})
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def test_healthz_rows_pass_when_the_deployed_sha_is_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fc, "git", lambda *a: (0, "abcdef1234567890\n"))
    server, url = _serve("abcdef1234", True)
    try:
        rows = fc.check_healthz(url)
    finally:
        server.shutdown()
    assert [r.status for r in rows] == ["PASS", "PASS"]


def test_healthz_sha_mismatch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fc, "git", lambda *a: (0, "1111111111111111\n"))
    server, url = _serve("abcdef1234", True)
    try:
        rows = fc.check_healthz(url)
    finally:
        server.shutdown()
    assert [r.status for r in rows] == ["PASS", "FAIL"]


def test_healthz_down_fails_after_the_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fc, "HEALTHZ_TIMEOUT_S", 0)
    monkeypatch.setattr(fc, "fetch_healthz", lambda url, timeout_s=0: (503, {}))
    rows = fc.check_healthz("http://127.0.0.1:9")
    assert rows[0].status == "FAIL" and rows[1].status == "SKIP"


def test_without_url_the_healthz_rows_are_skipped() -> None:
    assert [r.status for r in fc.check_healthz(None)] == ["SKIP", "SKIP"]


def test_branch_and_tree_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fc, "git", lambda *a: (0, "main\n"))
    assert fc.check_branch(False).status == "PASS"
    monkeypatch.setattr(fc, "git", lambda *a: (0, "feat/x\n"))
    assert fc.check_branch(False).status == "FAIL"
    assert fc.check_branch(True).status == "SKIP"
    monkeypatch.setattr(fc, "git", lambda *a: (0, " M a.py\n?? b.py\n"))
    row = fc.check_clean_tree()
    assert row.status == "FAIL" and "2 changed" in row.detail
    monkeypatch.setattr(fc, "git", lambda *a: (0, ""))
    assert fc.check_clean_tree().status == "PASS"


def test_main_exit_code_and_table(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(fc, "git", lambda *a: (0, ""))
    monkeypatch.setattr(
        fc, "check_branch", lambda any_branch: fc.Row("branch is main", "PASS", "main")
    )
    monkeypatch.setattr(fc, "check_secrets", lambda: fc.Row("no secret-looking strings", "PASS"))
    monkeypatch.setattr(
        fc, "check_doc_placeholders", lambda: fc.Row("docs placeholders listed", "FAIL", "x")
    )
    assert fc.main(["--skip-gates"]) == 1
    out = capsys.readouterr().out
    assert "FREEZE CHECK FAILED" in out and "CHECK" in out and "PASS" in out
    monkeypatch.setattr(
        fc, "check_doc_placeholders", lambda: fc.Row("docs placeholders listed", "PASS")
    )
    assert fc.main(["--skip-gates"]) == 0
