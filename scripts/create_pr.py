"""Script to open a GitHub Pull Request to trigger CI.

Usage:
    python scripts/create_pr.py <head_branch> <title>
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
# Rule C justification: scripts/ directory is not an installed package; sys.path modified before local import
from ci_status import get_github_token  # noqa: E402


def create_pr(head_branch: str, title: str, base: str = "main") -> None:
    repo = "shashwatkhandelwal-debug/Abhyas"
    url = f"https://api.github.com/repos/{repo}/pulls"
    token = get_github_token()
    headers = {
        "User-Agent": "Abhyas-CI-Checker",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = json.dumps({"title": title, "head": head_branch, "base": base, "body": title}).encode(
        "utf-8"
    )
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            res_data = json.loads(res.read().decode())
            print(f"Created PR #{res_data.get('number')}: {res_data.get('html_url')}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if "already exists" in body.lower():
            print(f"PR already exists for {head_branch}: {body}")
        else:
            print(f"HTTPError {e.code}: {body}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/create_pr.py <head_branch> <title>")
        sys.exit(1)
    create_pr(sys.argv[1], sys.argv[2])
