"""Update PR base branch."""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ci_status import get_github_token  # noqa: E402


def update_base(pr_num: int, base: str) -> None:
    repo = "shashwatkhandelwal-debug/Abhyas"
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}"
    token = get_github_token()
    headers = {
        "User-Agent": "Abhyas-CI-Checker",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps({"base": base}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="PATCH")
    with urllib.request.urlopen(req, timeout=30) as res:
        res_data = json.loads(res.read().decode())
        print(f"Updated PR #{pr_num} base to {res_data.get('base', {}).get('ref')}")


if __name__ == "__main__":
    update_base(int(sys.argv[1]), sys.argv[2])
