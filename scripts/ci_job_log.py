"""Fetches GitHub Actions job logs for debugging CI failures.

Usage:
    python scripts/ci_job_log.py <job_id>
"""

from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).parent))
from ci_status import get_github_token


class NoAuthRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
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
            if keyword:
                matching_lines = [line for line in lines if keyword in line.lower()]
                print(f"--- Found {len(matching_lines)} lines matching '{keyword}' ---")
                for line in matching_lines[:30]:
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
