"""Script to merge a GitHub Pull Request after CI passes.

Usage:
    python scripts/merge_pr.py <pr_number> <commit_title>
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Rule C justification: scripts/ directory is not an installed package; sys.path modified before local import
sys.path.insert(0, str(Path(__file__).parent))
from ci_status import get_github_token  # noqa: E402


def merge_pr(pr_number: int, commit_title: str) -> bool:
    repo = "shashwatkhandelwal-debug/Abhyas"
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/merge"
    token = get_github_token()
    headers = {
        "User-Agent": "Abhyas-CI-Checker",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = json.dumps(
        {
            "commit_title": commit_title,
            "merge_method": "merge",
        }
    ).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            res_data = json.loads(res.read().decode())
            print(
                f"Merged PR #{pr_number}: {res_data.get('message', 'Success')} (SHA: {res_data.get('sha')})"
            )
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"HTTPError {e.code}: {body}", file=sys.stderr)
        return False


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/merge_pr.py <pr_number> <commit_title>")
        sys.exit(1)
    success = merge_pr(int(sys.argv[1]), sys.argv[2])
    sys.exit(0 if success else 1)
