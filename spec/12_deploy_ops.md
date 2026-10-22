# 12 — Deployment, environment, CI, freeze

This file describes the setup that is actually deployed. The click path, the full variable reference and the
log lines to watch are in `docs/DEPLOY.md`; where the two differ, `docs/DEPLOY.md` is the more detailed one.
(Earlier drafts of this spec described a Starter plan and Supabase; neither is used.)

## 12.1 Environments

| Env | Where | Providers |
|---|---|---|
| local | `make dev` + docker compose Postgres (pgvector) | mocks unless keys in `.env` |
| test/CI | GitHub Actions + a Postgres service | mocks only |
| prod (evaluation) | One Render **web service** (Docker, **Free** plan, Singapore) + one Render **Postgres** (Free, same region, internal URL) | Claude; speech and WhatsApp only if keys are set (otherwise mock speech) |

No Supabase, no object store and no Redis. Everything that must survive a restart (including the TTS cache)
lives in Render Postgres. The `vector` and `pgcrypto` extensions are created by the first Alembic migration.

Free-plan facts that shape the demo (details in `docs/DEPLOY.md` §8):
- The web service sleeps after about 15 minutes idle; the next request cold-starts in about a minute. The PWA
  and the service worker show a "server is waking up" state (`/waking`) instead of a blank page.
- The free Postgres is deleted 30 days after creation (the current one expires on 2026-11-20): create a new one,
  update `DATABASE_URL` and redeploy with `SEED_ON_BOOT=true`.
- No Shell and no persistent disk: seeding and TTS prewarming run from the container start script.
- 512 MB of memory; the app plus the retrieval index measured about 190 MB on a development machine
  (`docs/PERFORMANCE.md`; not measured on Render).

## 12.2 Docker (`Dockerfile` at repo root)

- `python:3.11-slim`, ffmpeg and poppler-utils installed, non-root user, `pip install .`,
  `CMD ["sh", "scripts/start.sh"]`.
- `scripts/start.sh`: `alembic upgrade head`; if `SEED_ON_BOOT=true` run `python -m backend.app.db.seed` (a failed
  seed is logged and the service still starts); if `PREWARM_ON_BOOT=true` start `scripts/prewarm_tts.py` in the
  background; then `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT --proxy-headers
  --forwarded-allow-ips="*" --workers 1`.
- **Single worker and single instance**: the scheduler and the per-teacher conversation locks live in the process.
  The scale-out plan (shared lock, job queue, separate worker) is in the README.
- `docker-compose.yml`: `db` (pgvector/pgvector:pg16, port 5432) and `app` (build ., env_file .env).

## 12.3 Render (`render.yaml`)

`render.yaml` describes the web service with `plan: free`, `region: singapore`, `healthCheckPath: /healthz` and
`autoDeploy: false`, with every secret as `sync: false`. The evaluation service itself was created by hand in the
dashboard (a comment in the file says so), so the file documents the setup rather than driving it. Deploy by
hand (Manual Deploy) so that nothing changes during evaluation. HTTPS is automatic, which Meta webhooks and
`getUserMedia` (microphone) need.

## 12.4 Database (Render Postgres)

- Free instance, Postgres 16, region Singapore (same as the service), **Internal Database URL** with the scheme
  changed to `postgresql+asyncpg://` for `DATABASE_URL` and plain `postgresql://` for `ALEMBIC_DATABASE_URL`.
- The application connects server-side only; there are no per-row policies. Free instances have no backups: the
  demo data can always be rebuilt with `SEED_ON_BOOT=true`; real teacher data would be lost with the database.

## 12.5 Environment variables

`.env.example` (committed, empty secrets) lists every variable with a comment; `docs/DEPLOY.md` §3 and §9 say which
ones Render needs. In `ENVIRONMENT=production` the app refuses to start if a required secret is missing or still
a development default (`SESSION_SECRET`, `PHONE_HASH_SALT`, `PHONE_ENC_KEY`, `DEMO_PASSWORD`, `ADMIN_PASSWORD`,
`DATABASE_URL`, `PUBLIC_BASE_URL`, `ANTHROPIC_API_KEY`) or a provider is named without its key. In dev it logs which
providers are mocked.

## 12.6 CI (`.github/workflows/ci.yml`)

Jobs: `lint` (ruff check, ruff format --check, mypy), `test` (pytest with a Postgres service), `content`
(content validation) and `secrets` (gitleaks). They run on push and pull request. Work happens on feature
branches and reaches `main` through a pull request. Node tests (`node --test backend/tests/js/*.test.mjs`) are run
locally by `scripts/freeze_check.py`.

## 12.7 Observability

- Plain `key=value` log lines (see `docs/DEPLOY.md` §7), notably `llm_role role=… latency_ms=… fallback_used=…`
  for every model call; never phone numbers or tokens, and transcripts only at DEBUG.
- `/admin` shows latency, token use, guard results and scheduler jobs. Optional Sentry (`SENTRY_DSN`).

## 12.8 Cost and abuse guards

- `LLM_DAILY_TOKEN_BUDGET`: when exceeded the model roles switch to their deterministic fallbacks.
- `SPEECH_DAILY_BUDGET_INR` and `SPEECH_TOTAL_BUDGET_INR` cap speech spend.
- Rate limits in `config.py`: chat sends per user (`CHAT_MAX_MESSAGES_PER_MINUTE`), translations, and **failed**
  logins per (IP, username) and per IP (`MAX_LOGIN_ATTEMPTS_PER_MINUTE`, `MAX_LOGIN_FAILURES_PER_IP_PER_MINUTE`).

## 12.9 Freeze procedure (`make freeze` runs `scripts/freeze_check.py`)

`python scripts/freeze_check.py [--url https://<service>.onrender.com] [--skip-gates]` prints a PASS/FAIL table for:
1. working tree clean and current branch is `main`;
2. gates: ruff check, ruff format --check, mypy --strict backend/app, pytest, Node tests;
3. no secret-looking strings (API-key patterns) in tracked files;
4. the docs contain no unfilled `<HOSTED URL>`, `<DEMO_PASSWORD>` or `<ADMIN_PASSWORD>` outside the places listed in
   `PROGRESS.md` ("Placeholders still needing a person");
5. with `--url`: `/healthz` answers 200 and its `git_sha` matches the local HEAD.

By hand, after it passes: confirm every demo login works on the hosted URL, regenerate the latency report
against it (`python eval/latency/benchmark_latency.py --url <URL>`), create the annotated tag
`submission-2026-11-01` on HEAD and push it, point Render at that commit with auto-deploy off, and record the tag
and SHA in `PROGRESS.md`. After this point there are no commits to the submitted branch; continue on another
branch if needed.
