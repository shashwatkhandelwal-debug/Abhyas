# Lane C Progress (Operations & Analytics)

Branch: `lane-c`
Worktree: `../abhyas-c`
Port: 8003
Database: `abhyas_c` (waits for Docker Desktop)

## Tasks
- [x] T25 Auth & demo users (spec/09 §9.7, spec/14)
- [x] T26 Web channel API (spec/07 §7.3)
- [x] T27 Teacher chat PWA (spec/09 §9.2)
- [ ] T28 WhatsApp channel (spec/07 §7.2)
- [ ] T29 Progress, consent, delete (spec/09 §9.2)
- [ ] T30 First hosted deploy (spec/14)
- [ ] T31 Demo data (spec/03 §3.5)
- [ ] T32 ARP digest (spec/09 §9.3)
- [ ] T33 Trainer view + aggregates (spec/09 §9.4)
- [ ] T34 Coach review console (spec/09 §9.5)
- [ ] T35 Admin console (spec/09 §9.6)
- [ ] T36 Sankul mode (spec/08 §8.7)

## Deviations from spec
None.

## Self-Reviews
- T25 completed: Passlib/bcrypt password hashing, signed HttpOnly sessions (itsdangerous, 12h expiry), role route guards for teacher/arp/trainer/coach/admin, sliding window login rate limiter (5/min/IP), double-submit cookie CSRF protection, demo seed users across all 5 roles in `seed.py`.
- T26 completed: WebChannel protocol compliance, inbound message deduplication / idempotency on client_msg_id, per-teacher asyncio.Lock serialisation, pending status polling indicator, audio multipart with 2 MB limit, audio caching endpoint with private immutable header, realism rating endpoint, settings update endpoint.
- T27 completed: Jinja2 teacher chat template (`teacher.html`), single CSS (`app.css`), vanilla JS chat client with IndexedDB outbox queue (`chat.js`), MediaRecorder audio recorder with 16kbps mono and 90s/0.7s bounds (`recorder.js`), service worker with static cache and LRU 30 audio cache (`sw.js`), standalone PWA manifest (`manifest.json`), offline fallback page with cached 50 messages and try-in-class peer checklist (`offline.html`), lite mode toggle, and demo sample chips. Total uncompressed asset budget: 56.7 KB (comfortably below 150 KB limit).
- Self-Review (T25 & T26 against spec/09 §9.7 and spec/07 §7.3): All endpoints adhere strictly to spec specifications, schemas, error codes, and NFC Hindi normalization.
