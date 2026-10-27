# Run report 4: merge of `feature/hackathon-polish` into `main`

No Anthropic API key was available and the Claude API was not called. Everything below was run this session unless it is marked
**assumed**.

## Preflight (no changes)

- `git status`: only `eval/lowband/REPORT.md` was modified (script noise). I ran `git restore eval/lowband/REPORT.md`
  and never committed it.
- `git fetch origin`: no errors. `origin` is `https://github.com/shashwatkhandelwal-debug/Abhyas.git`.
- `git rev-parse main origin/main`: both `896b96091d1cc0a0539cf0696cd8b9fd37c562ff`. `git rev-list --left-right --count
  main...origin/main` printed `0 0` (not ahead, not behind).
- `git merge-base --is-ancestor 7f699b4 main`: **exit 1**, so `main` did not contain the learn-content commits. I stopped, reported, and
  you decided to include them.
- The merge base of `main` and the feature branch was `896b960` (main's tip), so the merge was a clean non-fast-forward
  (`--no-ff`) with no possible conflict.

## Included commits that were not part of the sprint list

| Commit | Purpose |
|---|---|
| `b32d92a` fix(learn-content): key points in UI lang, single learn button, send suggest on tap, log child_voice latency | Learn-step content in the move cards (`content/` and `content-seed/` moves, `move.json` schema), one learn button (`btn_replay` hidden unless there is audio), suggestion chip sends on tap, and `child_voice_reply_latency` / `child_voice_turn_latency` INFO logging. 23 files. |
| `7f699b4` docs: record learn-content changes, user feedback rows C1-C4, and child-voice latency | `PROGRESS.md` notes only. |

`git show --stat` and `git diff --stat main...feature/hackathon-polish` (48 files) were reviewed before the merge. Every file
fell into learn-step content/UI, child-voice latency logging, or the sprint work. Nothing unrelated was found.
`b32d92a` also committed a regenerated `eval/lowband/REPORT.md` (already in history before this work).

Byte effect of `b32d92a` (git blob sizes, LF): `chat.js` 70,184 → 70,495 B (+311), `app.css` unchanged (34,743 B),
`teacher.html` 12,718 → 13,006 B (+288). **All sprint gates in this report ran with these two commits present.**

## Housekeeping

- `git worktree remove .wt/pre3`: removed.
- `git worktree remove .wt/s3`: first refused (modified files). The only change was `eval/lowband/REPORT.md`; I restored it there and
  re-ran the remove without `--force`. Git deregistered the worktree but **failed to delete the directory
  ("Permission denied", Windows lock)**, so an unregistered **`.wt/s3` directory is still on disk**. I did not delete it (rule). It
  holds no tracked content. Remove it by hand when no shell is inside it. `.wt/` is in the working tree, not tracked
  (`git status` clean).

## Docs commits (on the feature branch, before the merge)

- `4e0f670`: `docs/EVALUATOR_GUIDE.md` (shared accounts and interference, login/logout reset, cold start, the four Fast-Track chips,
  `सवाल:` prefix, the three actions to reach the literacy group scene on `teacher.demo3`) and `eval/KEEP_ALIVE.md`. KEEP_ALIVE
  already recommended an external pinger (UptimeRobot first) on `/healthz` every 5 minutes; I left that as is and only corrected its
  quoted waking message to the catalogue string `ui_chat_cold_start` ("सर्वर जाग रहा है — इसमें करीब एक मिनट लग सकता है").
- `4c40e10`: `PROGRESS.md` (new sprint section) and `docs/QA_SHEET.md` (tagger fix note; the `[UNVERIFIED]` items are untouched).
  No kappa value or curriculum codes were added.
- The cold start is described as 40-60 s (Render's free-tier behaviour). **Assumed:** we did not time the hosted site, so "about 50 s" is
  an estimate.

## Backups and merge

| Ref | Points at |
|---|---|
| `backup-main-pre-merge` (branch) | `896b96091d1cc0a0539cf0696cd8b9fd37c562ff` |
| `pre-hackathon-merge` (tag) | `896b96091d1cc0a0539cf0696cd8b9fd37c562ff` |
| `backup-feature-final` (branch) | `4c40e1099642a187ffbe18f69862575405a05cfc` |

`git merge --no-ff feature/hackathon-polish` into `main` gave merge commit **`2d7c740`**, with no conflicts. After the merge
`main` was 20 commits ahead of `origin/main` (19 feature commits plus the merge).

## Gates

| Gate | Feature branch (`4c40e10`) | Merged `main` (`2d7c740`) |
|---|---|---|
| `ruff check .` | All checks passed | All checks passed |
| `mypy --strict backend/app scripts/keep_alive.py` | no issues, 170 files | no issues, 170 files |
| `python -m pytest` (full, no live DB) | **1569 passed, 129 skipped** in 178.74 s | **1569 passed, 129 skipped** in 188.31 s |
| `node --test backend/tests/js/chat.test.mjs` | tests 66, pass 66, fail 0 | tests 66, pass 66, fail 0 |
| `scripts/check_first_load.py` | PASS: first load 127.59 KB / all assets 148.23 KB raw | PASS: first load 125.35 KB / all assets 145.99 KB raw |

(`pytest` was run with `-o addopts=""` so the totals line is printed. The 129 skips need `TEST_DATABASE_URL` or rendered audio.
`sw.test.mjs` was not part of the requested gates and was not run. `eval/lowband/REPORT.md` was not committed: I pointed the script's
`--report-path` at a scratch file.)

### Byte numbers (limit 153,600 B)

| Tree | All offline assets | Headroom as the script measures it | LF-equivalent headroom |
|---|---|---|---|
| feature branch, CRLF working tree | 151,790 B | 1,810 B | 4,106 B |
| merged `main`, LF working tree | 149,494 B | 4,106 B | 4,106 B |

- Teacher first-load bundle: 130,653 B on the branch (CRLF), 128,357 B on `main`.
- CRLF inflation, checked by counting `\r\n` per file: `chat.js` 2,087 + `recorder.js` 209 = **2,296 B** (you quoted 2,292 B). `sw.js` has
  143 CRLF lines but the difference between the two measurements is exactly 2,296 B, so it did not show up in the script's
  numbers. After the merge the static files have 0 CRLF lines (the working tree went to LF).
- LF-equivalent headroom is **4,106 B**, above the 1,000 B floor.
- Correction: I first computed the LF figure using 2,439 B (it included `sw.js`) and committed 4,249 B to `PROGRESS.md`; that is fixed in a
  follow-up commit on `main`.

## Deploy configuration (read only)

- `render.yaml`: `type: web`, `runtime: docker`, `plan: free`, **`autoDeploy: false`**, health check `/healthz`. It does not name a branch.
- `docs/DEPLOY.md` says the service was created by hand in the Render dashboard with **Branch `main` (or the freeze branch/tag)** and
  **Auto-Deploy No**, and that a deploy is a manual "Deploy latest commit".
- `.github/workflows/ci.yml` runs on pushes and PRs to `main` and has no deploy step (grep for "deploy" found nothing).
- **Conclusion:** pushing `main` should **not** deploy by itself; the repo says deploys are manual. The deployed branch is `main` per the docs.
  **Assumed unknown:** the live dashboard setting (I did not and cannot read Render from the repo).
- Pushing to `main` does trigger the GitHub Actions CI. I did not change any deploy setting.

## Rollback commands (not run)

```
git revert -m 1 2d7c740
# or, only if you decide to force:
git push origin backup-main-pre-merge:main     # requires force
```

## Not done / assumed

- Live Claude paths (tagger, coach, child voice) were not exercised; all tests and runs are on mocks and the keyword fallback.
- Hosted-site checks (cold start timing, latency, the tray in a real browser) were not done.
- `.wt/s3` directory still exists on disk (see Housekeeping). `ruff format --check` (whole repo), `scripts/freeze_check.py`, `sw.test.mjs` and the
  CI run were not run here; CI status after the push is **assumed**, not seen.
