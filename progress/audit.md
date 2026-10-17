# Dependency Security Audit (T48, spec/12 §12.6)

Recorded: 2026-10-17
Source: GitHub Actions CI Job `audit` on run `39012794241` (Job ID: `117338685650`, PR #8 `lane-e-docs`)

## 1. Findings Summary

The `pip-audit --skip-editable` job reported **2 known vulnerabilities in 1 package**:

| Package | Installed Version | Advisory / Vulnerability ID | Severity | Fixed Version | Context / Notes |
|---|---|---|---|---|---|
| `setuptools` | `79.0.1` | `PYSEC-2026-3447` | Medium / High | `83.0.0` | GitHub Actions runner environment build tool dependency (`/opt/hostedtoolcache/Python/3.11.17/x64/lib/python3.11/site-packages`) |

## 2. Impact Analysis

- **Application Dependency**: `setuptools` is not declared as a direct runtime dependency in `pyproject.toml` (which uses modern standard packaging). It is pre-installed in the GitHub Actions runner Python toolcache.
- **Production Container**: The root `Dockerfile` builds a minimal production image without exposing setuptools build utilities in the live runtime.
- **Recommendation**: Upgrade `setuptools` in the CI workflow step before running `pip-audit`, or bump `setuptools>=83.0.0` in the build environment to clear the advisory. As per instructions, dependencies will not be bumped in `pyproject.toml` without prior reviewer approval.
