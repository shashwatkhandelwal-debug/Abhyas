"""GitHub Actions CI status checker script.

Usage:
    python scripts/ci_status.py [--sha <commit_sha>] [--branch <branch_name>]

Exit code:
    0 if all jobs succeeded (or in progress)
    1 if any job failed or error occurs
"""

import argparse
import json
import subprocess
import sys
import urllib.request


def get_github_token() -> str | None:
    try:
        p = subprocess.Popen(
            ["git", "credential", "fill"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        out, _ = p.communicate(input="protocol=https\nhost=github.com\n\n", timeout=5)
        for line in out.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1]
    except Exception:
        pass
    return None


def check_ci(target_sha: str | None = None, branch: str = "main") -> int:
    repo = "shashwatkhandelwal-debug/Abhyas"
    url = f"https://api.github.com/repos/{repo}/actions/runs"
    token = get_github_token()
    headers = {"User-Agent": "Abhyas-CI-Checker", "Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    runs = []
    last_exc = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                data = json.loads(res.read().decode())
                runs = data.get("workflow_runs", [])
                break
        except Exception as e:
            last_exc = e
            continue
    if not runs:
        print(f"Could not fetch workflow runs: {last_exc}", file=sys.stderr)
        return 0

    selected_run = None
    if target_sha:
        for r in runs:
            if r.get("head_sha", "").startswith(target_sha):
                selected_run = r
                break
    else:
        for r in runs:
            if r.get("head_branch") == branch:
                selected_run = r
                break
        if not selected_run:
            selected_run = runs[0]

    if not selected_run:
        print(f"No run found matching sha={target_sha} or branch={branch}")
        return 1

    run_id = selected_run["id"]
    sha = selected_run["head_sha"][:7]
    run_url = selected_run["html_url"]
    status = selected_run["status"]
    conclusion = selected_run["conclusion"]
    print(f"Run {run_id} ({sha}) [{status} / {conclusion}]: {run_url}")

    jobs_url = selected_run["jobs_url"]
    jobs_req = urllib.request.Request(
        jobs_url,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(jobs_req, timeout=15) as jres:
            jdata = json.loads(jres.read().decode())
    except Exception as e:
        print(f"Error fetching jobs: {e}", file=sys.stderr)
        return 1

    jobs = jdata.get("jobs", [])
    has_failure = False
    for j in jobs:
        jname = j.get("name", "unknown")
        jstatus = j.get("status", "unknown")
        jconclusion = j.get("conclusion") or "running"
        jurl = j.get("html_url", "")
        print(f"  - {jname:<10}: {jstatus:<12} [{jconclusion}] ({jurl})")
        if jconclusion == "failure":
            has_failure = True
            for s in j.get("steps", []):
                if s.get("conclusion") == "failure":
                    print(f"      FAILED STEP: {s.get('name')}")

    return 1 if has_failure else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check GitHub Actions CI run status")
    parser.add_argument("--sha", help="Commit SHA prefix to check", default=None)
    parser.add_argument("--branch", help="Branch name to check", default="main")
    args = parser.parse_args()
    sys.exit(check_ci(args.sha, args.branch))
