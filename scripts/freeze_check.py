"""Pre-submission freeze check (`make freeze`, spec/12 §12.9). Prints a PASS/FAIL table.

Usage: python scripts/freeze_check.py [--url https://<service>.onrender.com] [--skip-gates]
                                      [--any-branch]

Checks: git tree clean; current branch is main; gates (ruff, ruff format --check, mypy --strict
backend/app, pytest, Node tests); no secret-looking strings in tracked files; the README and docs
contain no unfilled <HOSTED URL> / <DEMO_PASSWORD> / <ADMIN_PASSWORD> except where PROGRESS.md
lists them (section "Allowed placeholders"); with --url, /healthz answers and reports the HEAD SHA.
Exit code 0 only if every row passes. `--skip-gates` and `--any-branch` are for trying the script on
a working branch; the rows are then marked SKIP and a freeze must not rely on them.

pytest needs TEST_DATABASE_URL (a scratch Postgres) for the database tests, otherwise they are skipped.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLACEHOLDERS = ("<HOSTED URL>", "<DEMO_PASSWORD>", "<ADMIN_PASSWORD>")
MAX_SCAN_BYTES = 2_000_000
HEALTHZ_TIMEOUT_S = 90  # a sleeping free instance takes about a minute to wake
HEALTHZ_RETRY_S = 5

# Patterns of real credentials (not names of variables). Kept narrow to avoid false alarms.
SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "Anthropic key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "GitHub token": re.compile(
        r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{36,}\b|github_pat_[A-Za-z0-9_]{40,}"
    ),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{20,}"),
    "Meta access token": re.compile(r"\bEAA[A-Za-z0-9]{100,}"),
    "Private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
}


@dataclass
class Row:
    name: str
    status: str  # PASS | FAIL | SKIP
    detail: str = ""


def run(cmd: list[str], timeout: int = 1800) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    return proc.returncode, (proc.stdout + proc.stderr)


def tail(text: str, n: int = 1) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return " | ".join(lines[-n:])[:200]


def git(*args: str) -> tuple[int, str]:
    return run(["git", *args])


def check_clean_tree() -> Row:
    code, out = git("status", "--porcelain")
    if code != 0:
        return Row("git tree clean", "FAIL", tail(out))
    dirty = [line for line in out.splitlines() if line.strip()]
    return Row(
        "git tree clean",
        "FAIL" if dirty else "PASS",
        f"{len(dirty)} changed paths" if dirty else "",
    )


def check_branch(any_branch: bool) -> Row:
    code, out = git("rev-parse", "--abbrev-ref", "HEAD")
    branch = out.strip()
    if code != 0:
        return Row("branch is main", "FAIL", tail(out))
    if branch == "main":
        return Row("branch is main", "PASS", branch)
    if any_branch:
        return Row("branch is main", "SKIP", f"on {branch} (--any-branch)")
    return Row("branch is main", "FAIL", f"on {branch}")


def check_gate(name: str, cmd: list[str]) -> Row:
    started = time.monotonic()
    code, out = run(cmd)
    took = f"{time.monotonic() - started:.0f}s"
    if code == 0:
        return Row(name, "PASS", took)
    return Row(name, "FAIL", f"exit {code}: {tail(out, 2)}")


def scan_text_for_secrets(text: str) -> list[str]:
    return [label for label, pat in SECRET_PATTERNS.items() if pat.search(text)]


def tracked_files() -> list[Path]:
    code, out = git("ls-files", "-z")
    if code != 0:
        return []
    return [REPO / p for p in out.split("\0") if p]


def check_secrets() -> Row:
    hits: list[str] = []
    scanned = 0
    me = Path(__file__).resolve()
    for path in tracked_files():
        try:
            if not path.is_file() or path.resolve() == me or path.stat().st_size > MAX_SCAN_BYTES:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:4096]:
            continue  # binary
        scanned += 1
        for label in scan_text_for_secrets(data.decode("utf-8", errors="ignore")):
            hits.append(f"{path.relative_to(REPO).as_posix()} ({label})")
    if hits:
        return Row("no secret-looking strings", "FAIL", "; ".join(hits[:5]))
    return Row("no secret-looking strings", "PASS", f"{scanned} tracked text files")


def allowed_placeholders(progress_text: str) -> dict[str, set[str]]:
    """Parses PROGRESS.md section 'Allowed placeholders': lines `- <TOKEN>: path, path`."""
    allowed: dict[str, set[str]] = {p: set() for p in PLACEHOLDERS}
    m = re.search(r"^#+\s*Allowed placeholders\s*$(.*?)(?=^#|\Z)", progress_text, re.M | re.S)
    if not m:
        return allowed
    for line in m.group(1).splitlines():
        lm = re.match(r"^\s*[-*]\s*`?(<[A-Z_ ]+>)`?\s*:\s*(.+)$", line)
        if lm and lm.group(1) in allowed:
            for path in re.findall(r"`?([\w./-]+\.md)`?", lm.group(2)):
                allowed[lm.group(1)].add(path)
    return allowed


def find_unfilled(docs: dict[str, str], allowed: dict[str, set[str]]) -> list[str]:
    bad = []
    for rel, text in sorted(docs.items()):
        for token in PLACEHOLDERS:
            if token in text and rel not in allowed.get(token, set()):
                bad.append(f"{rel} {token}")
    return bad


def check_doc_placeholders() -> Row:
    docs: dict[str, str] = {}
    for path in [REPO / "README.md", *sorted((REPO / "docs").rglob("*.md"))]:
        if path.is_file():
            docs[path.relative_to(REPO).as_posix()] = path.read_text(
                encoding="utf-8", errors="ignore"
            )
    progress = REPO / "PROGRESS.md"
    if not progress.is_file():
        return Row("docs placeholders listed", "FAIL", "PROGRESS.md missing")
    allowed = allowed_placeholders(progress.read_text(encoding="utf-8", errors="ignore"))
    bad = find_unfilled(docs, allowed)
    if bad:
        return Row(
            "docs placeholders listed", "FAIL", f"{len(bad)} unlisted: " + "; ".join(bad[:4])
        )
    used = sum(1 for text in docs.values() for t in PLACEHOLDERS if t in text)
    return Row("docs placeholders listed", "PASS", f"{used} uses, all listed in PROGRESS.md")


def fetch_healthz(url: str, timeout_s: float = HEALTHZ_TIMEOUT_S) -> tuple[int, dict[str, str]]:
    """GET <url>/healthz, retrying until it answers 200 or `timeout_s` passes (cold start)."""
    target = url.rstrip("/") + "/healthz"
    deadline = time.monotonic() + timeout_s
    last_status = 0
    while True:
        try:
            with urllib.request.urlopen(target, timeout=15) as resp:  # noqa: S310 (operator URL)
                last_status = resp.status
                if resp.status == 200:
                    return 200, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_status = exc.code
        except (urllib.error.URLError, OSError, ValueError):
            last_status = 0
        if time.monotonic() >= deadline:
            return last_status, {}
        time.sleep(HEALTHZ_RETRY_S)


def sha_matches(reported: str, head: str) -> bool:
    reported = reported.strip().lower()
    head = head.strip().lower()
    return len(reported) >= 7 and (head.startswith(reported) or reported.startswith(head))


def check_healthz(url: str | None) -> list[Row]:
    if not url:
        return [
            Row("/healthz responds", "SKIP", "no --url"),
            Row("deployed SHA is HEAD", "SKIP", "no --url"),
        ]
    status, body = fetch_healthz(url)
    if status != 200 or body.get("status") != "ok":
        return [
            Row("/healthz responds", "FAIL", f"status {status}"),
            Row("deployed SHA is HEAD", "SKIP", "healthz not ok"),
        ]
    code, head = git("rev-parse", "HEAD")
    reported = str(body.get("git_sha", ""))
    rows = [Row("/healthz responds", "PASS", f"200, git_sha={reported}")]
    if code == 0 and sha_matches(reported, head):
        rows.append(Row("deployed SHA is HEAD", "PASS", head.strip()[:10]))
    else:
        rows.append(
            Row("deployed SHA is HEAD", "FAIL", f"deployed {reported!r}, HEAD {head.strip()[:10]}")
        )
    return rows


def render_table(rows: list[Row]) -> str:
    width = max(len(r.name) for r in rows)
    lines = [f"{'CHECK'.ljust(width)}  RESULT  DETAIL", f"{'-' * width}  ------  ------"]
    lines += [f"{r.name.ljust(width)}  {r.status.ljust(6)}  {r.detail}" for r in rows]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--url", default=None, help="hosted base URL to probe (/healthz)")
    parser.add_argument(
        "--skip-gates", action="store_true", help="do not run ruff/mypy/pytest/node"
    )
    parser.add_argument("--any-branch", action="store_true", help="do not require branch main")
    args = parser.parse_args(argv)

    rows = [check_clean_tree(), check_branch(args.any_branch)]
    if args.skip_gates:
        rows += [
            Row(n, "SKIP", "--skip-gates")
            for n in ("ruff", "ruff format", "mypy", "pytest", "node tests")
        ]
    else:
        py = sys.executable
        rows += [
            check_gate("ruff", [py, "-m", "ruff", "check", "."]),
            check_gate("ruff format", [py, "-m", "ruff", "format", "--check", "."]),
            check_gate("mypy", [py, "-m", "mypy", "--strict", "backend/app"]),
            check_gate("pytest", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider"]),
            check_gate(
                "node tests",
                [
                    "node",
                    "--test",
                    *[str(p) for p in sorted((REPO / "backend/tests/js").glob("*.test.mjs"))],
                ],
            ),
        ]
    rows += [check_secrets(), check_doc_placeholders(), *check_healthz(args.url)]

    sys.stdout.write(render_table(rows) + "\n")
    failed = [r for r in rows if r.status == "FAIL"]
    skipped = [r for r in rows if r.status == "SKIP"]
    sys.stdout.write(
        f"\n{'FREEZE CHECK FAILED' if failed else 'FREEZE CHECK PASSED'}: "
        f"{len(rows) - len(failed) - len(skipped)} passed, {len(failed)} failed, {len(skipped)} skipped\n"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
