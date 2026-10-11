# 12 — Deployment, environment, CI, freeze

## 12.1 Environments

| Env | Where | Providers |
|---|---|---|
| local | `make dev` + docker compose Postgres | mocks unless keys in `.env` |
| test/CI | GitHub Actions + Postgres service | mocks only |
| prod (evaluation) | Render web service (Docker, **Starter** plan, Singapore region — closest to India) + Supabase (Mumbai `ap-south-1`) | real: Claude, Sarvam, WhatsApp |

## 12.2 Docker (`Dockerfile` at repo root)

- `python:3.11-slim`; `apt-get install -y ffmpeg poppler-utils` (pdftoppm for OCR ingest); non-root user; `pip install .`; `CMD alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --workers 1`.
- **Single worker/instance** (in-process scheduler and per-teacher locks assume one process). Document this limit + the scale-out plan (Redis-backed queue, separate worker) in README roadmap.
- `docker-compose.yml`: `db` (pgvector/pgvector:pg16, port 5432), `app` (build ., env_file .env, depends_on db).

## 12.3 Render (`render.yaml` blueprint)

```yaml
services:
  - type: web
    name: abhyas
    runtime: docker
    plan: starter
    region: singapore
    healthCheckPath: /healthz
    autoDeploy: false          # deploy deliberately; freeze = stop deploying
    envVars:                   # values set in the Render dashboard (HUMAN INPUT), never in git
      - key: DATABASE_URL
        sync: false
      # … every key from .env.example with sync: false
```
Custom domain optional. HTTPS automatic (required by Meta webhooks and by `getUserMedia` mic access).

## 12.4 Supabase

- New project (Mumbai). Enable `vector` extension. Use the **session pooler** connection string for `DATABASE_URL` (`postgresql+asyncpg://…`), direct connection for Alembic if pooler blocks DDL.
- Enable RLS on all tables with no policies (app uses server-side connection; anon key unused). Daily backups (default).

## 12.5 Environment variables (`.env.example` — commit this, with empty secrets)

See `.env.example` at the build-pack root (copy to repo root, replacing the scaffold's). Every variable is documented with a comment; the app fails fast at startup in `ENVIRONMENT=production` if a required secret is missing, and logs which providers are mocked in dev.

## 12.6 CI (`.github/workflows/ci.yml`)

Jobs: `lint` (ruff, mypy), `test` (pytest with Postgres service, coverage gate), `content` (`make content-validate`), `secrets` (gitleaks action). Required to pass before merge to `main`. Branch flow: feature branches `t<id>-<slug>` → PR → main. Agent may push directly to `main` only if no human reviewer is configured; otherwise open PRs.

## 12.7 Observability

- Structured JSON logs (request id, teacher id hash prefix, state, stage timings); never log transcripts at INFO in prod (DEBUG only), never log phone numbers or tokens.
- `/admin` metrics (09 §9.6). Optional Sentry (`SENTRY_DSN`) if provided.

## 12.8 Cost guard

- `LLM_DAILY_TOKEN_BUDGET` (config): if exceeded, roles switch to deterministic fallbacks and admin page shows a red banner. Protects the hackathon credits during the evaluation window.
- Rate limit per teacher: 60 inbound messages/hour.

## 12.9 Freeze procedure (`make freeze` runs `scripts/freeze_check.py`)

Checks and prints a pass/fail list:
1. `main` CI green; working tree clean.
2. `.env` not tracked; gitleaks clean; no files > 5 MB except allowed audio samples.
3. README has: setup, run locally, `.env.example` reference, AI services list, credentials table placeholder, low-network table, known limitations.
4. LICENSE present (MIT).
5. `/healthz` on prod returns the same `GIT_SHA` as HEAD.
6. Every demo login works on prod (scripted login + GET role home page → 200).
7. Sample inputs present in `eval/samples/` and playable.
8. Latency report updated within 48 h.
Then: create annotated tag `submission-2026-11-01` on HEAD, push tag, set Render to deploy that commit, **disable auto-deploy**, and record the tag + SHA in `PROGRESS.md`. After this point **no commits to `main`** until results; continue work for the finale on branch `finale`.

Evaluator access: grant read access to the Tech4Dev evaluator GitHub IDs (HUMAN INPUT: they'll be shared by organisers) — repo is public already, but add them as collaborators if asked.
