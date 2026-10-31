# README and open-source prep report

Branch `fix/readme`, from `main` (228a8ad, fix6 merged). Docs and hygiene only: no app code, static asset or service worker changed, except the password placeholders in `config.py` that were asked for. Not merged, not pushed.

## 1. Scan of the full history

540 commits, all branches and tags, 21 MB of patches, searched for key shapes (Anthropic, Google, Render, ElevenLabs-style, JWT, GitHub, AWS, Slack, Meta tokens), key-like variable assignments, database URLs with passwords, emails, phone numbers, local paths, and every file ever added (`.env`, `.db`, audio, PDFs, spreadsheets, archives).

**Nothing real was found.** The only key-shaped string is `sk-ant-test-real-key` in a test. Database URLs are local (`postgres:postgres`, `postgrespassword`) or `[PROJECT-REF]` placeholders. No `.env` was ever committed, only `.env.example`. No PDF, database or upload was ever committed. The one phone number is the test value `+919876543210`. `eval/user_testing/sessions.csv` is a header row.

**Decided with the owner and done here:**

| Item | Action |
|---|---|
| `WHATSAPP_VERIFY_TOKEN=abhyas_webhook_verify_token_secure` (in `.env.example` since the first commit) | Now `your_verify_token_here`. The owner checks Render and rotates if it was real. |
| Old defaults `abhyas-demo-2026`, `abhyas-admin-2026` | `config.py` defaults and `.env.example` are now `change-me-demo-password` and `change-me-admin-password`. Production still refuses to start with any of the four values. |
| OCR page cache of the UP guides (268 files) | `git rm`, and `content/sources/ocr_cache/` is git-ignored. Checked first: only `page_ocr.py` names the folder (the one-off ingest step, which also needs PDFs that are not in git) and its tests use a temp folder. Nothing needs it at runtime or in CI. |
| Local Windows user-profile paths | Removed from `eval/latency/REPORT.md` and `benchmark_latency.py` (relative links) and from `progress/lane-b.md`, `lane-c.md`. A `git grep` for the user name is now empty. |
| `.gitignore` | Added `*.db`, `*.sqlite`, `*.sqlite3`, `uploads/`, the OCR cache. (`.env*`, audio and `content/sources/*.pdf` were already covered.) |
| `Abhyas_Technical_Design.docx` | Opened (first version, from history): the hackathon design document naming the three team members, no emails, phones, paths, keys or URLs. It is not in the current tree (removed earlier), so there is nothing to remove. Left in history. |
| Author emails, history | Left alone, as decided. No rewrite, no branch deleted. |

**Things you should know:**
- `content/chunks/` holds chunks of all five sources: NIPUN Bharat (MoE), Vidya Pravesh and NISHTHA FLN (NCERT), and the two UP Samagra Shiksha guides, plus `seed_from_moves.jsonl` (ours). The decision was to keep the folder; the README's CONTENT_NOTICE names all five publishers and does not claim redistribution terms are cleared. `sources.yaml` says the same for each (`licence_note`).
- `LICENSE` now reads "Copyright (c) 2026 Team Asymptotes (Shashwat Khandelwal)", as instructed. It used to list Vedant Arora and Divyansh Agrawal as well, and the design document and the old README name all three. Say if you want them back.
- No vendored third-party files (fonts, minified JS, `node_modules`) are in the repository, so nothing conflicts with MIT.
- The dev defaults for `SESSION_SECRET`, `PHONE_HASH_SALT` and `PHONE_ENC_KEY` in `config.py` are fixed development strings (a Fernet key among them). Production refuses them; they protect nothing locally. Left as they are.

## 2. What was written

- `README.md` (rewritten): what Abhyas is, live URL and the cold-start note, credentials table, five sample inputs, how AI is used by layer with the rule-engine statement, external AI services table (model, use, file, env var, spend caps, honest Gemini note), privacy, offline behaviour, local setup, `.env.example` groups, tests, known limitations, licence and CONTENT_NOTICE. The old README had `TODO(human)` placeholders; they are gone. It also linked to judge-pack documents (`docs/JUDGE_QUICKSTART.md` and others); those files are untouched but no longer linked.
- `.env.example`: placeholders only (no real values existed in it).
- `LICENSE`: copyright line.

## 3. What I verified by running it

On a clean `git clone` of this branch into a temp folder, a new venv, and a fresh database:

```
python -m venv .venv && . .venv/Scripts/activate
pip install -e ".[dev]"
docker exec abhyas_db psql -U postgres -c 'CREATE DATABASE abhyas_readme_check'
cp .env.example .env     # then edited: the two database URLs, DEMO_PASSWORD, ADMIN_PASSWORD
alembic upgrade head
python -m backend.app.db.seed          # 1157 chunks, demo users
uvicorn backend.app.main:app --port 8010
curl /healthz  /readyz                 # both {"status":"ok"}
python scripts/smoke_roles.py --base-url http://127.0.0.1:8010 --demo-password abhyas_admin_2026 --admin-password abhyas_admin_2026    # 42 of 42 steps passed
```

- **Five sample inputs**, sent as `teacher.demo2` and `teacher.demo3` through `/api/chat/text` on that local server (mock model, no keys): `52 - 17` gives Ravi's answer 45; `explain` gives Ravi's steps on 43 - 27 with his mistake (24); `delete my data` gives the confirm buttons; `सवाल: खिलौना आधारित शिक्षण का क्या महत्व है?` and `How do I teach place value to Class 1 children?` give a Guide answer. Hindi and English questions typed without the `सवाल:` prefix at the learn step got the "tap one of the two buttons" reminder, which the README says. Outputs from the real models on the hosted app were not checked.
- **Tests on the clean clone, no `.env`, `pymupdf` installed, no database:** `ruff check` clean, `mypy --strict` clean, Node 121 pass, `pytest` 2712 passed, 178 skipped (they need a database), 0 failed.
- **Payload.** No static asset or template changed on this branch (`git diff main -- backend/app/web` is empty). `check_first_load.py` says all assets 151951 B (main: 151937 B). The extra 14 B is the login page printing the longer placeholder password twice in this checkout; the hosted app prints its own `DEMO_PASSWORD`. The static files are byte-identical to main.

## 4. Could not verify, or found wrong

- **`docker compose up -d db` itself was not run.** A container named `abhyas_db` (same image) already runs on this machine, so I created the scratch database inside it instead. `make` is not installed here, so I ran the commands the Makefile targets wrap. Not checked on Linux or macOS.
- **The Makefile `db-up` target starts `infra/docker-compose.yml`, whose database password is `postgrespassword`, while `.env.example` and the root `docker-compose.yml` use `postgres`.** Following `make db-up` with the stock `.env.example` would fail to connect. The README uses `docker compose up -d db` at the repository root and says so. I did not touch the Makefile.
- **`pymupdf` is imported by `backend/tests/unit/test_page_ocr.py` but is not in `pyproject.toml`.** A fresh `pip install -e ".[dev]"` gives 4 errors in that file. The README tells readers to `pip install pymupdf` or skip the file.
- **The tests read `.env`.** With the `.env` from my setup steps (real passwords, empty `PHONE_ENC_KEY=`), `test_auth`, `test_config` and `test_whatsapp_channel` fail; without a `.env` they pass. The empty `PHONE_ENC_KEY=` copied from `.env.example` also makes the WhatsApp code raise "Fernet key must be 32 url-safe base64-encoded bytes". Stated in the README; not changed.
- **The hosted app was not touched.** Its admin password is not documented (it is `ADMIN_PASSWORD` there); the README says so instead of guessing. The hosted `DEMO_PASSWORD` must be `abhyas_admin_2026` for the credentials table to be true.
- The UP-guide and NCERT chunk licences are recorded in `sources.yaml` as "terms not recorded". That is the open legal question; nothing here resolves it.
