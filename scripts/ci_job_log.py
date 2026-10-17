"""Fetches GitHub Actions job logs for debugging CI failures.

Usage:
    python scripts/ci_job_log.py <job_id>
"""

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ci_status import get_github_token  # noqa: E402


class NoAuthRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request:
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req and "Authorization" in new_req.headers:
            del new_req.headers["Authorization"]
        return new_req


def fetch_job_log(job_id: str) -> None:
    repo = "shashwatkhandelwal-debug/Abhyas"
    url = f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/logs"
    token = get_github_token()
    headers = {"User-Agent": "Abhyas-CI-Checker"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url,
        headers=headers,
    )
    opener = urllib.request.build_opener(NoAuthRedirectHandler())
    try:
        with opener.open(req, timeout=30) as res:
            content = res.read().decode("utf-8", errors="replace")
            lines = content.splitlines()
            print(f"=== Job {job_id} Log ({len(lines)} lines total) ===")
            keyword = sys.argv[2].lower() if len(sys.argv) > 2 else None
            fail_idx = -1
            for i, line in enumerate(lines):
                if "short test summary info" in line.lower() or "=== failures ===" in line.lower():
                    fail_idx = i
                    break
            if keyword:
                matching_indices = [i for i, line in enumerate(lines) if keyword in line.lower()]
                print(f"--- Found {len(matching_indices)} occurrences of '{keyword}' ---")
                for idx in matching_indices[:3]:
                    s = max(0, idx - 5)
                    e = min(len(lines), idx + 25)
                    print(f"\n--- Context lines {s}-{e} ---")
                    for line in lines[s:e]:
                        print(line)
            elif fail_idx != -1:
                start = max(0, fail_idx - 10)
                end = min(len(lines), fail_idx + 80)
                print(f"--- Found Failure Section (lines {start}-{end}) ---")
                for line in lines[start:end]:
                    print(line)
            else:
                for line in lines[-80:]:
                    print(line)
    except Exception as e:
        print(f"Error fetching job log: {e}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/ci_job_log.py <job_id>")
        sys.exit(1)
    fetch_job_log(sys.argv[1])
