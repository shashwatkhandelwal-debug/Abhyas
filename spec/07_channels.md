# 07 — Channels and HTTP API

Two channels share one brain (`ConversationService`). A teacher has a `preferred_channel`; outbound goes there. Web teachers are app_users with role teacher linked to a teacher row; WhatsApp teachers are created on first inbound.

## 7.1 Inbound pipeline (both channels)

```
receive → auth/verify → dedupe on (channel, channel_msg_id) → persist message(in, text|null)
→ 200/202 immediately → BackgroundTask: process_inbound()
process_inbound: [audio? download → to_wav16k → STT → discard audio] → set message.text = transcript
→ ConversationService.handle(inbound) → list[OutboundMessage] → channel.send() → persist message(out)
```
Per-teacher serialisation: an `asyncio.Lock` keyed by teacher_id (in-process dict; single instance deploy) so two quick voice notes are processed in order. If a second message arrives while a REHEARSE turn is processing, queue it.

## 7.2 WhatsApp Cloud API (`channels/whatsapp/`)

Direct Meta Cloud API (no BSP needed for the prototype; Gupshup/other BSP is a roadmap swap behind the same client). Graph base `https://graph.facebook.com/{WHATSAPP_GRAPH_VERSION}` (env, default `v23.0` — **verify the current version in Meta docs**). Auth: `Authorization: Bearer $WHATSAPP_ACCESS_TOKEN` (System User permanent token, HUMAN INPUT).

**Webhook** `GET /webhooks/whatsapp`: if `hub.mode == "subscribe"` and `hub.verify_token == WHATSAPP_VERIFY_TOKEN` → return `hub.challenge` as plain text, else 403.
**Webhook** `POST /webhooks/whatsapp`:
- Verify `X-Hub-Signature-256: sha256=<hex>` = HMAC-SHA256(`WHATSAPP_APP_SECRET`, raw body), constant-time compare; 401 on mismatch.
- Parse `entry[].changes[].value.messages[]`; ignore `statuses[]` (but log delivery failures).
- Message types: `text` (`text.body`), `audio` (`audio.id`, `audio.mime_type`, `audio.voice`), `interactive` (`button_reply.id`), `button` (template quick-reply payload). Others (image, sticker, location) → reply `unsupported_type`.
- `from` (wa_id) → E.164 → `phone_hash`; find or create teacher (`onboarding_state = NEW`), store encrypted number in `teacher_contact`. Update `last_inbound_at`.
- Always return 200 within 2 s (Meta retries otherwise); processing in background.

**Media download** (`media.py`): `GET /{media_id}` → `{url, mime_type}`; `GET url` with bearer → bytes (in memory). Max 16 MB.
**Media upload**: `POST /{WHATSAPP_PHONE_NUMBER_ID}/media` multipart `file` (audio/ogg; codecs=opus), `type=audio/ogg`, `messaging_product=whatsapp` → `id`. Cache media id per TTS cache key for 25 days (Meta media ids expire after ~30 days).

**Send** (`client.py`) `POST /{WHATSAPP_PHONE_NUMBER_ID}/messages`:
- text: `{"messaging_product":"whatsapp","to":E164,"type":"text","text":{"body": …}}` (≤ 4096 chars)
- audio: `{"type":"audio","audio":{"id": media_id}}` (if the API version supports a voice-note flag, set it so it renders as a voice message — verify docs)
- buttons: `{"type":"interactive","interactive":{"type":"button","body":{"text": …},"action":{"buttons":[{"type":"reply","reply":{"id": …,"title": ≤20 chars}}]}}}` (max 3)
- list (for > 3 options, e.g. classes taught): `interactive.type = "list"` with one section, ≤ 10 rows.
- template: `{"type":"template","template":{"name": …,"language":{"code":"hi"},"components":[{"type":"body","parameters":[{"type":"text","text": …}]}]}}`
- Order per turn: text → audio → buttons. Rate limit: token bucket 20 msg/s global; retry 429/5xx with backoff (0.5 s, 2 s, 8 s).

**24-hour window** (`sessions/window.py`): `can_send_freeform = now - teacher.last_inbound_at < 24h`. Business-initiated messages outside the window **must** be an approved template (`content/whatsapp_templates.yaml`). Log each template send in `template_send` with `est_cost_inr = WHATSAPP_UTILITY_COST_INR` (config, 0.12 — verify current Meta India rate). Tests: inside window → freeform; outside → template; template not approved (`approved: false` in YAML) → skip send, log, show on admin page.

**Test number setup** (HUMAN, documented in `docs/whatsapp_setup.md` which the agent writes): Meta developer app → WhatsApp product → test number → add up to 5 recipient numbers → permanent token via System User → webhook URL `https://<host>/webhooks/whatsapp` + verify token → subscribe `messages` field → create templates (Hindi, Utility) from the YAML → wait for approval.

## 7.3 Web channel (`channels/web.py` + `web/teacher.py` + `static/chat.js`)

Outbound messages are written to `message` (direction out); the client fetches them. **Polling, not websockets/SSE** (robust on flaky mobile networks, works through any proxy).

- `POST /api/chat/text` `{client_msg_id, text}` → 202 `{message_id}`
- `POST /api/chat/audio` multipart `{client_msg_id, file}` (webm/opus, ogg/opus or mp4/aac from MediaRecorder; ≤ 2 MB) → 202
- `POST /api/chat/button` `{client_msg_id, button_id}` → 202
- `GET /api/chat/messages?after=<message_id>` → `{messages: [...], pending: bool}`; client polls every 1.5 s while `pending` (a turn is processing for this teacher), else every 20 s, and immediately after any send.
- `GET /api/audio/<audio_ref>.<ogg|mp3>` → cached synthetic audio (auth required; `Cache-Control: private, max-age=31536000, immutable`).
- `POST /api/chat/rating` `{scene_id, rating}` (realism 1–5)
- `POST /api/settings` `{lite_mode}`

`client_msg_id` is a UUID generated in the browser; the server dedupes, so the client can blindly retry on network errors (outbox in IndexedDB — see 09).

## 7.4 Full HTTP route table

| Method & path | Role | Purpose |
|---|---|---|
| `GET /` | public | landing: what Abhyas is, login button, "WhatsApp पर जुड़ें" QR/link (if number configured) |
| `GET/POST /login`, `POST /logout` | public | session cookie |
| `GET /healthz` | public | `{"ok":true,"db":true,"version":GIT_SHA}` |
| `GET /teacher` | teacher | chat PWA |
| `GET /teacher/progress` | teacher | own evidence ladder per move, scores history, consent settings, "delete my data" |
| `GET /arp` | arp | weekly digest (cluster) |
| `GET /arp/teacher/{id}` | arp | consenting teacher detail; 403 otherwise |
| `POST /arp/observation` | arp | log classroom observation (evidence level 4) |
| `POST /arp/question/{id}/answer` | arp | answer escalated question → sent to teacher |
| `GET /trainer` | trainer | module × batch aggregates with suppression |
| `GET /trainer/export.csv` | trainer | same aggregates CSV (suppressed rows blank) |
| `GET /review` | coach | review queue: low-confidence scores, escalated questions, guard failures |
| `POST /review/{id}` | coach | resolve (corrected scores → stored as calibration labels) |
| `GET /review/moves`, `GET/POST /review/moves/{id}` | coach | view/edit YAML (form + raw), approve (2 approvals → approved) |
| `GET /admin` | admin | latency p50/p95, LLM fallback rates, template sends & cost, guard failures, scheduled jobs |
| `POST /admin/fast-forward/{teacher_id}` | admin | run that teacher's pending scheduled jobs now (demo) |
| `POST /admin/reset-demo` | admin | restore demo teachers to seeded state |
| `POST /admin/publish` | admin | publish content release |
| `GET/POST /webhooks/whatsapp` | Meta | 7.2 |
| `/api/chat/*`, `/api/audio/*`, `/api/settings` | teacher | 7.3 |

All HTML pages: CSRF token on POST forms (double-submit cookie). Rate-limit login (5/min/IP).
