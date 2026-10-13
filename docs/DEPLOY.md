# Production Deployment Guide: Render + Supabase

This document provides a click-by-click operational runbook for deploying **Abhyas** to production on Render and Supabase in compliance with `spec/12_deploy_ops.md`.

---

## 1. Supabase Setup (Database & Vector Store)

### 1.1 Create Project
1. Log in to [Supabase Console](https://supabase.com/dashboard).
2. Click **New Project** and select your organization.
3. Configure project details:
   - **Name**: `abhyas-prod`
   - **Database Password**: Generate a secure, 32+ character password. Store this securely in a password manager.
   - **Region**: **Mumbai (`ap-south-1`)** (critical: minimizes latency for Indian primary school users).
   - **Pricing Plan**: Free or Pro tier.
4. Click **Create new project** and wait 2–3 minutes for provisioning.

### 1.2 Enable Vector Extension (`pgvector`)
1. In the Supabase project dashboard, navigate to **Database** -> **Extensions**.
2. Search for `vector`.
3. Toggle the switch to **Active / Enable**, or execute via **SQL Editor**:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

### 1.3 Obtain Connection Strings
Under **Project Settings** -> **Database** -> **Connection string**:
1. **Session Pooler URL (for `DATABASE_URL`)**:
   - Select **URI** tab, mode **Session** (port 5432).
   - Prefix protocol with `postgresql+asyncpg://`:
     ```text
     postgresql+asyncpg://postgres.[PROJECT-REF]:[DB-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
     ```
   - This connection string is used by FastAPI's asynchronous SQLAlchemy engine (`asyncpg`).
2. **Direct Connection URL (for `ALEMBIC_DATABASE_URL`)**:
   - Select mode **Direct** (port 5432).
   - Format:
     ```text
     postgresql://postgres:[DB-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres
     ```
   - Direct connection bypasses connection pooler transactional locks during Alembic DDL migrations.

### 1.4 Enable Row Level Security (RLS)
The Abhyas backend interacts with Postgres via server-side credentials and does not expose direct client access to the Supabase data APIs.
Run the following in the **SQL Editor** after running migrations to ensure RLS is enabled on all tables:
```sql
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
        EXECUTE 'ALTER TABLE public.' || quote_ident(r.tablename) || ' ENABLE ROW LEVEL SECURITY;';
    END LOOP;
END $$;
```

---

## 2. Render Setup (Web Service)

### 2.1 Create Web Service
1. Log in to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **Web Service**.
3. Connect your GitHub repository (`Abhyas`).
4. In the service creation form:
   - **Name**: `abhyas`
   - **Region**: **Singapore (`singapore`)** (closest Render region to India).
   - **Branch**: `main` (or designated freeze tag/branch, e.g. `lane-c`).
   - **Runtime**: **Docker**.
   - **Dockerfile Path**: `./Dockerfile`
   - **Docker Context**: `.`
   - **Instance Type / Plan**: **Starter** ($7/mo — 512 MB RAM, 0.5 CPU, persistent execution without cold-start sleep).
   - **Auto-Deploy**: **No** (`false`). Set auto-deploy to manual to prevent unexpected updates during active evaluation and freeze windows.

### 2.2 Health Check Configuration
1. Expand **Advanced** settings.
2. In **Health Check Path**, enter:
   ```text
   /healthz
   ```
3. Render monitors this endpoint and will only route traffic after `/healthz` returns HTTP 200 `{"status": "ok", "git_sha": "..."}`.

### 2.3 Single-Worker Constraint (§12.2)
The application runs as a **single worker instance** (`--workers 1`) because the in-process conversation lock and session scheduler require a single process. Do not scale beyond 1 instance without deploying an external Redis queue.

### 2.4 Ingress Proxy & Forwarded Client IP
The container starts uvicorn with `--proxy-headers --forwarded-allow-ips="*"`.

**Why `--forwarded-allow-ips="*"` is safe on Render**:
Render provides an isolated container execution environment where Render's own ingress load balancer is the sole entrypoint. Render terminates TLS, strips untrusted client-supplied headers, and injects the authentic `X-Forwarded-For` client IP chain and `X-Forwarded-Proto` header.
In `ENVIRONMENT=production`, FastAPI's rate limiter directly inspects the first hop of `X-Forwarded-For` (`backend/app/auth/rate_limit.py`) to enforce the 5-attempt-per-minute login limit per client IP. Allowing forwarded headers from the ingress proxy ensures accurate client IP attribution without false-positive throttling across distinct users.

---

## 3. Environment Variables & Speech Configuration

### 3.1 Initial Zero-Key Deploy vs Live Speech Activation
- **Initial Deploy Boots Cleanly**: By default in `render.yaml`, `STT_PROVIDER=mock`, `TTS_PROVIDER=mock`, and `SPEECH_PROVIDER_LIVE=false`. This allows the initial production service to boot up and pass health checks immediately without failing fast on absent speech keys.
- **Activating Live Speech (Sarvam AI)**:
  Once `SARVAM_API_KEY` is obtained:
  1. Open the Render Dashboard -> Select **abhyas** -> **Environment**.
  2. Add `SARVAM_API_KEY` with your secret key.
  3. Change `STT_PROVIDER` to `sarvam`.
  4. Change `TTS_PROVIDER` to `sarvam`.
  5. Change `SPEECH_PROVIDER_LIVE` to `true`.
  6. Save changes; Render will redeploy with full Hindi STT and child-voice TTS enabled.

### 3.2 Environment Variables Checklist Table
Configure environment variables in **Render Dashboard** -> **Environment**.
Never commit real production credentials to Git.

| Variable Name | Description | Provider / Source | Required in Prod? |
|---|---|---|---|
| `ENVIRONMENT` | Must be set to `production` | Render configuration | **Yes** (`production`) |
| `PORT` | Listening port for web server | Render automatically sets `$PORT` | Render default (8000) |
| `LOG_LEVEL` | Log severity level (`INFO` in prod) | Application logging | Optional (default: `INFO`) |
| `PUBLIC_BASE_URL` | Public HTTPS URL of the service (e.g. `https://abhyas.onrender.com`) | Render service URL / Custom domain | **Yes** |
| `GIT_SHA` | Deployed git commit SHA | Render build / `RENDER_GIT_COMMIT` | Optional (default: `dev`) |
| `DATABASE_URL` | Supabase session pooler URI (`postgresql+asyncpg://...`) | Supabase Session Pooler | **Yes** |
| `ALEMBIC_DATABASE_URL` | Supabase direct connection URI (`postgresql://...`) | Supabase Direct Connection | **Yes** |
| `SESSION_SECRET` | 64-char random hex string for cookie signing (`token_hex(32)`) | System admin / secrets generator | **Yes** |
| `PHONE_HASH_SALT` | 32-char random hex string for anonymized phone hashes | System admin / secrets generator | **Yes** |
| `PHONE_ENC_KEY` | 32-byte Fernet encryption key (`Fernet.generate_key()`) | System admin / Fernet generator | **Yes** |
| `DEMO_PASSWORD` | Password for evaluation demo accounts (must NOT be default) | System admin | **Yes** (must rotate) |
| `ADMIN_PASSWORD` | Password for admin and coach consoles (must NOT be default) | System admin | **Yes** (must rotate) |
| `TRUSTED_PROXY_IPS` | Comma-separated trusted proxy IPs (dev/staging testing) | System admin | Optional (default: `127.0.0.1`) |
| `LLM_PROVIDER` | LLM engine (`anthropic`) | Architecture configuration | Optional (default: `anthropic`) |
| `ANTHROPIC_API_KEY` | Claude API secret key (`sk-ant-...`) | Anthropic Console | **Yes** |
| `CLAUDE_MODEL_FAST` | Haiku model ID for fast child responses | Anthropic | Optional (default: `claude-haiku-5-5`) |
| `CLAUDE_MODEL_SMART` | Sonnet model ID for coach feedback | Anthropic | Optional (default: `claude-sonnet-5-5`) |
| `CLAUDE_MODEL_BUILD` | Sonnet model ID for move generation | Anthropic | Optional (default: `claude-sonnet-5-5`) |
| `LLM_DAILY_TOKEN_BUDGET` | Daily token safety cap (default `3000000`) | Budget control | Optional |
| `STT_PROVIDER` | Speech-to-text provider (`mock` initial, `sarvam` live) | Architecture configuration | Optional (default: `mock`) |
| `TTS_PROVIDER` | Text-to-speech provider (`mock` initial, `sarvam` live) | Architecture configuration | Optional (default: `mock`) |
| `SPEECH_PROVIDER_LIVE` | Live speech switch (`false` initial, `true` when live) | Architecture configuration | Optional (default: `false`) |
| `SPEECH_DAILY_BUDGET_INR`| Daily speech budget cap in INR | Budget control | Optional (default: `50.0`) |
| `SPEECH_TOTAL_BUDGET_INR`| Total evaluation speech budget in INR | Budget control | Optional (default: `500.0`) |
| `SARVAM_API_KEY` | Sarvam AI API subscription key | Sarvam AI Dashboard | Required if live speech |
| `SARVAM_BASE_URL` | Sarvam API base URL | Sarvam AI | Optional (default: `https://api.sarvam.ai`) |
| `SARVAM_STT_MODEL` | Sarvam speech-to-text model | Sarvam AI | Optional (default: `saaras:v4`) |
| `SARVAM_TTS_MODEL` | Sarvam text-to-speech model | Sarvam AI | Optional (default: `bulbul:v3`) |
| `BHASHINI_USER_ID` | Bhashini fallback user ID | Bhashini ULCA | Optional |
| `BHASHINI_API_KEY` | Bhashini fallback API key | Bhashini ULCA | Optional |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path or JSON string for Google Cloud fallback STT | Google Cloud Console | Optional |
| `MOCK_STT_TEXT` | Fallback Devanagari text for testing | Development / Mock | Optional |
| `WHATSAPP_ENABLED` | Set `true` once Meta credentials are configured | Meta Cloud API | Optional (default: `false`) |
| `WHATSAPP_GRAPH_VERSION` | Graph API version | Meta Developers | Optional (default: `v23.0`) |
| `WHATSAPP_PHONE_NUMBER_ID` | Phone number ID for WhatsApp Business | Meta WhatsApp Manager | Optional (Required if WhatsApp enabled) |
| `WHATSAPP_ACCESS_TOKEN` | System User permanent access token | Meta Business Manager | Optional (Required if WhatsApp enabled) |
| `WHATSAPP_APP_SECRET` | App secret for HMAC-SHA256 signature verification | Meta App Dashboard | Optional (Required if WhatsApp enabled) |
| `WHATSAPP_VERIFY_TOKEN` | Webhook verification token challenge | User configured string | Optional (Required if WhatsApp enabled) |
| `WHATSAPP_DISPLAY_NUMBER` | Formatted phone number (e.g., `+91 98765 43210`) | Meta WhatsApp Manager | Optional |
| `WHATSAPP_UTILITY_COST_INR` | Per-conversation utility cost | Cost tracking | Optional (default: `0.12`) |
| `VOYAGE_API_KEY` | Dense embedding key for hybrid retrieval | Voyage AI | Optional |
| `VOYAGE_MODEL` | Multilingual embedding model | Voyage AI | Optional (default: `voyage-multilingual-2`) |
| `SERVE_IN_REVIEW_TO_DEMO` | Allow demo accounts to view cards under review | Product configuration | Optional (default: `true`) |
| `DEMO_MODE` | Enable demo chips and demo login switcher UI | Evaluation configuration | Optional (default: `true`) |
| `SENTRY_DSN` | Sentry DSN for production exception telemetry | Sentry.io | Optional |

---

## 4. Database Initialization & Seeding

When the container boots on Render, the Docker `CMD` automatically executes:
```bash
alembic upgrade head && uvicorn backend.app.main:app ...
```
To seed demo teachers, school metadata, and approved pedagogical moves:
1. Open the Render Dashboard -> Select **abhyas** -> Click **Shell**.
2. Run the database seed CLI:
   ```bash
   python -m backend.app.db.seed
   ```
3. Confirm that seed output completes with:
   ```text
   Seed completed: pedagogical content and demo cohort initialized.
   ```

---

## 5. Post-Deployment Smoke Test

Immediately after deployment is healthy on Render, run the standalone smoke test from any machine:

```bash
# Run against the deployed URL
python scripts/smoke_test.py --base-url https://abhyas.onrender.com
```

### Smoke Test Steps Executed:
1. **GET `/healthz`**: Validates HTTP 200 and matches deployed `git_sha`.
2. **GET `/login`**: Validates that Hindi login UI loads and `abhyas_csrf` cookie is set.
3. **POST `/login`**: Authenticates demo teacher (`teacher.demo1`) and verifies `abhyas_session` signed cookie.
4. **POST `/api/chat/text`**: Sends an inbound text message and validates HTTP 202 Accepted.
5. **Summary Report**: Prints detailed pass/fail table and exits `0` on success, `1` on failure.

### Manual Verification Checklist:
- Open `https://abhyas.onrender.com` in a mobile browser (Chrome / Safari):
  - Automatically redirects to `/login`.
  - Tap demo badge `शिक्षिका (नई): teacher.demo1`.
  - Tap **लॉगिन करें** -> redirects to `/teacher` PWA interface.
  - Send a sample voice or text message -> verify child voice response and Hindi transcript bubble.
