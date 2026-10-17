"""Print arbitrary line range from GitHub Actions job log."""

import sys
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from ci_job_log import NoAuthRedirectHandler
from ci_status import get_github_token


def show_lines(job_id: str, start: int, end: int) -> None:
    repo = "shashwatkhandelwal-debug/Abhyas"
    url = f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/logs"
    token = get_github_token()
    headers = {"User-Agent": "Abhyas-CI-Checker"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(NoAuthRedirectHandler())
    with opener.open(req, timeout=30) as res:
        content = res.read().decode("utf-8", errors="replace")
        lines = content.splitlines()
        for idx in range(max(0, start), min(len(lines), end)):
            print(f"{idx}: {lines[idx]}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python scripts/ci_show_lines.py <job_id> <start> <end>")
        sys.exit(1)
    show_lines(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
