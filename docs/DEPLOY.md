# Deployment runbook: Render only (web service + Render Postgres)

Abhyas is hosted on **Render** alone: one Docker web service and one Render Postgres database. There is
no Supabase, no separate object store and no Redis. This page is the click path, the environment
variable names, what to look for in the logs, and what the free plan does to the demo.

Related: `spec/12_deploy_ops.md` (original design; it still mentions Starter + Supabase, and this page
supersedes it for the evaluation deployment), `docs/EVALUATOR_GUIDE.md` (what an evaluator sees),
`scripts/start.sh` (what runs at container start).

> **Free-plan facts that matter during evaluation** (details in §8)
> - The free Postgres **expires 30 days after it was created. This one expires on 2026-11-20.** After that the
>   database is gone: create a new one, point `DATABASE_URL` at it and redeploy with `SEED_ON_BOOT=true`.
> - The free web service **sleeps after about 15 minutes without traffic**; the next request cold-starts it
>   in **about a minute**. Open `/healthz` once before a demo.
> - Render's **health check path is `/healthz`** (returns `{"status": "ok", "git_sha": "..."}`).
> - The free plan has **no Shell**, so seeding and prewarming run from `scripts/start.sh` via
>   `SEED_ON_BOOT` and `PREWARM_ON_BOOT`.
> - `render.yaml` says `plan: free` to match this deployment, which was created by hand in the dashboard
>   (a comment in the file says so). It is a description, not what was applied: do not rely on a blueprint sync.

---

## 1. Create the database (Render Postgres, free)

1. Render Dashboard → **New +** → **PostgreSQL**.
2. **Name** `abhyas-db`, **Database** `abhyas`, **Region** `Singapore` (same region as the web service,
   so the *Internal* URL works), **PostgreSQL version** 16, **Instance type** `Free`.
3. Create it and wait until it shows **Available**. Note the creation date: the free database lasts
   30 days from this day.
4. Open the database page → **Connections** and copy the **Internal Database URL** (it looks like
   `postgresql://USER:PASSWORD@HOST/DBNAME`). Use the internal URL, not the external one: internal needs no
   SSL setup and only works from services in the same Render region.

There is nothing to enable by hand: the first Alembic migration runs `CREATE EXTENSION IF NOT EXISTS
vector` and `pgcrypto` itself, and every table is created by `alembic upgrade head` at container start.

## 2. Create the web service

1. **New +** → **Web Service** → connect the GitHub repository.
2. **Name** `abhyas`, **Region** `Singapore`, **Branch** `main` (or the freeze branch/tag),
   **Runtime** `Docker`, **Dockerfile Path** `./Dockerfile`, **Instance type** `Free`.
3. **Advanced** → **Health Check Path** `/healthz`. **Auto-Deploy** `No` (deploy by hand so nothing
   changes during evaluation).
4. Do not set a start command: the Dockerfile `CMD` runs `sh scripts/start.sh`
   (migrate → optional seed → optional background prewarm → single-worker uvicorn).

The app must stay at **one worker / one instance** (the conversation lock and the scheduler live in the
process).

## 3. Environment variables

Set them under the service's **Environment** tab. **Never commit values.** Names only here.

**Required for the service to start** (it refuses to boot in production without them):

| Name | Notes |
|---|---|
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | the Internal Database URL with the scheme changed to `postgresql+asyncpg://` |
| `ALEMBIC_DATABASE_URL` | same URL with plain `postgresql://` (optional: migrations fall back to `DATABASE_URL`) |
| `PUBLIC_BASE_URL` | the service's `https://….onrender.com` URL |
| `SESSION_SECRET`, `PHONE_HASH_SALT`, `PHONE_ENC_KEY` | random secrets; the dev defaults are rejected in production |
| `DEMO_PASSWORD`, `ADMIN_PASSWORD` | must differ from the built-in defaults; `DEMO_PASSWORD` is shared by the six demo logins, `ADMIN_PASSWORD` is for `admin` |
| `ANTHROPIC_API_KEY` | Claude key (without it the app would only run on mocks, which production refuses) |

**Speech** (all optional; with the defaults STT/TTS are mocks):
`STT_PROVIDER`, `TTS_PROVIDER`, `STT_FALLBACK_PROVIDER`, `TTS_FALLBACK_PROVIDER`, `SPEECH_PROVIDER_LIVE`,
`GEMINI_API_KEY`, `SARVAM_API_KEY`, `SPEECH_DAILY_BUDGET_INR`, `SPEECH_TOTAL_BUDGET_INR`.

**Gemini rate limits (free-tier quota).** To survive a quota error during the judges' hour, set
`STT_PROVIDER=gemini`, `TTS_PROVIDER=gemini`, `STT_FALLBACK_PROVIDER=sarvam`, `TTS_FALLBACK_PROVIDER=sarvam` and both
keys. A Gemini answer of HTTP 429 (or a quota / `RESOURCE_EXHAUSTED` body) makes the call fall back to Sarvam at once and
Gemini is skipped for `SPEECH_RATE_LIMIT_COOLDOWN_S` (60 s), so the next voice notes do not each pay for a failed call. If
Sarvam fails too, a voice note gets the Hindi reply "the voice service is not available right now, please type your
message" (`stt_unavailable_type_please`) and a child's line is sent as text without audio. Without the fallback variables
the chain does not exist (`none` is the default) and a quota error goes straight to that "please type" reply.
A provider named in any of the four `*_PROVIDER` variables needs its key, or startup fails.

**Boot helpers** (both default to `false`): `SEED_ON_BOOT`, `PREWARM_ON_BOOT` (§5).

Others (`DEMO_MODE`, `LOG_LEVEL`, WhatsApp, Voyage, Sentry, model ids…) are in the reference table in §9.

## 4. First deploy

1. Create the database (§1), then the service (§2), then fill in the environment (§3). Set
   `SEED_ON_BOOT=true` for this first deploy (and `PREWARM_ON_BOOT=true` only if a TTS key is set).
2. **Manual Deploy** → *Deploy latest commit*. The first build takes several minutes (ffmpeg, Python deps).
3. Watch **Logs**; a healthy first boot prints, in order:
   - Alembic lines ending in `Running upgrade … -> <head>` (or nothing new on later boots);
   - `start.sh: seeding demo data (SEED_ON_BOOT=true)`, then `Starting database seed` and finally
     `Successfully seeded demo users, teachers, clusters, synthetic cohort, and doc chunks.`;
   - with prewarm on: `start.sh: prewarming TTS audio in the background (PREWARM_ON_BOOT=true)`;
   - `Uvicorn running on http://0.0.0.0:…`, and Render marks the service **Live** once `/healthz` returns 200.
4. A failed seed does not stop startup: you will see `start.sh: ERROR: demo data seed failed; continuing
   startup` plus the traceback above it. Fix the cause and redeploy.
5. Open `https://<service>.onrender.com/healthz` (expect `"status": "ok"` and the deployed `git_sha`), then
   log in as `teacher.demo1` and run `python scripts/smoke_test.py --base-url https://<service>.onrender.com`.
6. Set `SEED_ON_BOOT` back to `false` (saving the variable redeploys). Leave it `false` afterwards: the
   seed is idempotent but takes time at every cold start.

## 5. Boot helpers: `SEED_ON_BOOT` and `PREWARM_ON_BOOT`

| Variable | What it does | When to use |
|---|---|---|
| `SEED_ON_BOOT=true` | Runs `python -m backend.app.db.seed` after the migrations and before uvicorn starts. Creates clusters, batches, invite codes, the demo logins, the synthetic 51-teacher cohort and the retrieval chunks; re-applies `DEMO_PASSWORD` and `ADMIN_PASSWORD`. Idempotent. | First deploy, after a new database, after changing the demo password. |
| `PREWARM_ON_BOOT=true` | Starts `python scripts/prewarm_tts.py` **in the background** (it does not delay uvicorn) to synthesize the demo's fixed Hindi lines into the TTS cache in Postgres. Skips lines already cached (cache keys include the provider name), waits `PREWARM_REQUEST_INTERVAL_SECONDS` between provider calls, stops after `PREWARM_MAX_SYNTH_PER_RUN` new clips (the next boot continues) and respects `SPEECH_DAILY_BUDGET_INR` / `SPEECH_TOTAL_BUDGET_INR`. With mock TTS it logs "no-op" and does nothing. | After the TTS keys are set, once per new database. |

The prewarm covers **90 lines (7,394 characters)**: 13 catalog prompts (welcome, consent, name, placement,
explain-back, try-in-class, escalation, coach scene-end), 26 move lines (learn scripts and the scripted model
rehearsal), 24 persona off-topic lines (Ravi, Priya, Aman, with the "सर" variants) and 27 engine template
child lines. Lines the LLM writes (live child voice, coach feedback with the teacher's own words, guide
answers) cannot be predicted and are not prewarmed. Prewarm progress is in the log with the prefix
`prewarm:`; the last line reads `TTS Pre-warming Complete: provider=… targets=… synthesized=…
already_cached=… skipped_budget=… tts_calls=… cost=… INR` (`tts_calls` is the total number of TTS provider
requests this run made). Running it by hand (a paid instance with Shell): `python scripts/prewarm_tts.py`
(`--dry-run` to count only, `--no-demo-lines` for catalog + learn scripts only).

## 6. Redeploying

- **Code change**: push to the deployed branch, then **Manual Deploy** → *Deploy latest commit*. Render builds a
  new image and swaps it in when `/healthz` is OK. Migrations run at start; the database is kept.
- **Env change**: saving a variable restarts the service.
- **Reseed / reset demo data**: set `SEED_ON_BOOT=true`, deploy, check the log line, set it back to `false`.
  Logging out of `teacher.demo1/2/3` also resets that teacher; the admin console has a *Reset demo* button.
- **Rollback**: Render → **Events** / **Deploys** → pick the previous deploy → **Rollback**. Migrations are not
  reversed, so only roll back across a migration if it was additive.
- **Freeze**: after the submission freeze make no deploys that change the commit (`spec/12_deploy_ops.md`).

## 7. Reading the logs

Render → service → **Logs** (filter with the search box). Lines are plain `key=value` text.

| Line | Meaning | What to do |
|---|---|---|
| `llm_role role=<r> model=<m> latency_ms=<n> fallback_used=<true\|false>` | One line per Claude role call (`act_tagger`, `child_voice`, `coach`, `fidelity_checker`, `guide_answerer`, `intent_router`, `question_classifier`, `translator`). `fallback_used=true` means the model output failed its schema or guard twice (or the call failed) and the deterministic template was used instead. | Occasional `true` is by design. If one role is `true` for most calls, check `ANTHROPIC_API_KEY`, the model ids and the quota; `latency_ms` shows slow roles. |
| `<role> guard failed (attempt N): <reason>` | The first or second guard rejection that precedes a fallback. | The reason names the rule (for example a child line that said a forbidden number). |
| `coach_fallback reason=<r> move=<MOVE_ID>` | The coach feedback was built from the move card's feedback bank instead of by the model. `reason` is `guard_failed` (output failed the guard twice), `llm_unavailable` (no key / provider error) or `call_or_validation_error` (call or schema error). Only acts evidenced in the teacher's own words are credited. | `llm_unavailable` right after a deploy means the Anthropic key is missing or invalid. The feedback is still shown to the teacher and queued for coach review. |
| `web_stt_failed reason=<r> message_id=<id>` | A web voice note produced no transcript: `reason=stt_failed` (empty transcript), `stt_unavailable_type_please` (every STT provider failed or is rate limited) or `stt_budget_type_please` (speech budget reached). The teacher got the matching Hindi "speak again or type" / "please type" reply. | Check the STT key and `STT_PROVIDER`; `STT failed for web voice note …` just above has the provider error. Budget: raise `SPEECH_DAILY_BUDGET_INR` or wait for the next IST day. |
| `page_ocr_failed …` | Only from the offline OCR tool, never from the service. | n/a |
| `Production startup failed: required secrets missing or insecure: …` | The service refused to boot; the list names the missing variables. | Set them (§3) and redeploy. |
| `start.sh: ERROR: demo data seed failed; continuing startup` | The seed raised; the app is up without demo data. | Read the traceback above it. |

Counts are also in the admin console (`/admin`: latency, token use, guard results, scheduler jobs).

## 8. What the free plan does

- **Sleep and cold start.** After ~15 minutes without requests the instance spins down. The next request
  waits about a minute while the container starts (migrations, optional seed). The chat shows a "server is
  waking up, about a minute" hint after 5 seconds and keeps the message in its outbox; it is sent when the
  server answers. Other pages show an "Opening…" bar at once and the same hint after 4 seconds; if the host
  answers 502/503/504 while booting, the service worker shows `/waking` (Hindi + English), which polls
  `/healthz` and reloads by itself. Browsers never get a raw error: 404, 500 and 503 render bilingual pages
  (`backend/app/web/errors.py`). The very first request, before any page of ours has loaded, is answered by
  Render itself. Hit `/healthz` before a demo.
- **Scheduler.** The scheduler (ARP digest on Saturday 17:00 IST, follow-ups, aggregates at 02:00 IST) runs
  inside the web process, so jobs due while the service sleeps run late, when it next wakes.
- **Memory.** 512 MB. Measured on a Windows development machine (`docs/PERFORMANCE.md`, 2026-10-22), the
  app plus the 1,157-chunk retrieval index is about 188 MB resident and 193 MB after one scene. Render's own
  figure has not been measured here.
- **No Shell, no persistent disk.** Anything that must survive a restart lives in Postgres (the TTS cache
  included). Use `SEED_ON_BOOT` / `PREWARM_ON_BOOT` instead of a Shell.
- **Free Postgres lifetime.** 30 days from creation, then it is deleted (check Render's current expiry and grace-period
  policy; it is not verified here). **This database expires on 2026-11-20**, which may fall inside the evaluation window: either
  upgrade the database to a paid instance before then, or create a new free one, update `DATABASE_URL`
  (and `ALEMBIC_DATABASE_URL`), redeploy with `SEED_ON_BOOT=true` and `PREWARM_ON_BOOT=true`, and tell the
  evaluators that real (non-demo) teacher data from the old database is lost.

## 9. Environment variable reference

Configure in **Render Dashboard → Environment**. Never commit real credentials.

| Variable Name | Description | Provider / Source | Required in Prod? |
|---|---|---|---|
| `ENVIRONMENT` | Must be set to `production` | Render configuration | **Yes** (`production`) |
| `PORT` | Listening port for web server | Render automatically sets `$PORT` | Render default (8000) |
| `LOG_LEVEL` | Log severity level (`INFO` in prod) | Application logging | Optional (default: `INFO`) |
| `PUBLIC_BASE_URL` | Public HTTPS URL of the service | Render service URL / custom domain | **Yes** |
| `GIT_SHA` | Deployed git commit SHA (returned by `/healthz`) | Render build / `RENDER_GIT_COMMIT` | Optional (default: `dev`) |
| `DATABASE_URL` | Render Postgres Internal URL, `postgresql+asyncpg://…` | Render Postgres → Connections | **Yes** |
| `ALEMBIC_DATABASE_URL` | Same database, plain `postgresql://…` (falls back to `DATABASE_URL`) | Render Postgres → Connections | Recommended |
| `SESSION_SECRET` | 64-char random hex string for cookie signing | System admin / secrets generator | **Yes** |
| `PHONE_HASH_SALT` | Random string for anonymized phone hashes | System admin / secrets generator | **Yes** |
| `PHONE_ENC_KEY` | 32-byte Fernet key | System admin / Fernet generator | **Yes** |
| `DEMO_PASSWORD` | Password of the six demo logins (must NOT be default) | System admin | **Yes** (must rotate) |
| `ADMIN_PASSWORD` | Password of the `admin` login (must NOT be default) | System admin | **Yes** (must rotate) |
| `TRUSTED_PROXY_IPS` | Comma-separated trusted proxy IPs (dev/staging testing) | System admin | Optional |
| `LLM_PROVIDER` | LLM engine (`anthropic`) | Architecture configuration | Optional |
| `ANTHROPIC_API_KEY` | Claude API key | Anthropic Console | **Yes** |
| `CLAUDE_MODEL_FAST` / `CLAUDE_MODEL_SMART` / `CLAUDE_MODEL_BUILD` | Model ids per role family | Anthropic | Optional |
| `LLM_DAILY_TOKEN_BUDGET` | Daily token safety cap | Budget control | Optional |
| `STT_PROVIDER` / `TTS_PROVIDER` | Speech providers (`mock`, `sarvam`, `gemini`) | Architecture configuration | Optional (default: `mock`) |
| `STT_FALLBACK_PROVIDER` / `TTS_FALLBACK_PROVIDER` | Provider tried when the primary fails (`none`, `sarvam`, `gemini`, …; `mock` rejected in prod) | Architecture configuration | Optional (default: `none`) |
| `SPEECH_PROVIDER_LIVE` | Live speech switch (fails closed on a DB error when `true`) | Architecture configuration | Optional (default: `false`) |
| `SPEECH_DAILY_BUDGET_INR` / `SPEECH_TOTAL_BUDGET_INR` | Speech budget caps in INR | Budget control | Optional |
| `GEMINI_API_KEY` | Gemini API key | Google AI Studio | If `gemini` is a primary or fallback provider |
| `GEMINI_BASE_URL`, `GEMINI_STT_MODEL`, `GEMINI_TTS_MODEL`, `GEMINI_TTS_VOICE_F`, `GEMINI_TTS_VOICE_M` | Gemini endpoint, models and voices | Google | Optional |
| `GEMINI_STT_COST_INR_PER_MIN`, `GEMINI_TTS_COST_INR_PER_1K_CHARS` | Cost recorded in `speech_spend` | Budget control | Optional |
| `SARVAM_API_KEY` | Sarvam AI key | Sarvam dashboard | If `sarvam` is a primary or fallback provider |
| `SARVAM_BASE_URL`, `SARVAM_STT_MODEL`, `SARVAM_TTS_MODEL` | Sarvam endpoint and models | Sarvam AI | Optional |
| `BHASHINI_USER_ID`, `BHASHINI_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS` | Extra STT/TTS fallbacks | Bhashini / Google Cloud | Optional |
| `MOCK_STT_TEXT` | Transcript returned by the mock STT | Development | Optional |
| `WHATSAPP_ENABLED`, `WHATSAPP_GRAPH_VERSION`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_DISPLAY_NUMBER`, `WHATSAPP_UTILITY_COST_INR` | WhatsApp Cloud API (see `docs/whatsapp_setup.md`); token, phone-number id and app secret are required once enabled | Meta | Optional |
| `VOYAGE_API_KEY`, `VOYAGE_MODEL` | Dense embeddings (BM25 is used when absent) | Voyage AI | Optional |
| `SERVE_IN_REVIEW_TO_DEMO` | Let demo accounts see move cards still in review | Product configuration | Optional (default: `true`) |
| `DEMO_MODE` | Demo chips, login demo card, demo banners | Evaluation configuration | Optional (default: `true`) |
| `SENTRY_DSN` | Sentry DSN | Sentry.io | Optional |
| `SEED_ON_BOOT` | Seed demo data in `scripts/start.sh` (§5) | Render configuration | Optional (default: `false`) |
| `PREWARM_ON_BOOT` | Background TTS prewarm in `scripts/start.sh` (§5) | Render configuration | Optional (default: `false`) |
| `PREWARM_REQUEST_INTERVAL_SECONDS`, `PREWARM_MAX_SYNTH_PER_RUN` | Pace and per-boot cap of the prewarm | Budget control | Optional |

## 10. Smoke test

```bash
python scripts/smoke_test.py --base-url https://<service>.onrender.com
```

It checks `GET /healthz` (HTTP 200 and `git_sha`), `GET /login` (Hindi UI, CSRF cookie), `POST /login` as
`teacher.demo1` (signed session cookie) and `POST /api/chat/text` (HTTP 202), prints a pass/fail table and exits
`0`/`1`. Manually, on a phone: open the site → tap a demo badge → log in → send a text or voice message.
The first request after a sleep takes about a minute.

## 11. Source documents and OCR (offline, not part of the service)

The service reads only the committed `content/chunks/*.jsonl`. They are built on a developer machine:
`make content-ingest` chunks the PDFs in `content/sources/`; the two UP Hindi guides (legacy fonts) are first
read from page images by `python -m backend.app.retrieval.page_ocr --source <id>` (Claude Haiku vision, cached
by image hash in `content/sources/ocr_cache/`, hard cap `OCR_BUDGET_USD`). No Tesseract or Surya is used. See
`content/sources/README.md` for what was ingested and the measured OCR error rate.
