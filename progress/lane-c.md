# Lane C Progress (Web & Ops: Channels, Auth, PWA, Reports, Deploy)

Branch: `lane-c`
Worktree: `C:\Users\ASUS\Downloads\abhyas-lane-c`
Port: 8003
Database: `abhyas_c` (waits for Docker Desktop)

## Tasks
- [x] T25 Auth & demo users (spec/09 §9.7, spec/14)
- [x] T26 Web channel API (spec/07 §7.3)
- [x] T27 Teacher chat PWA (spec/09 §9.2)
- [ ] T28 WhatsApp channel (spec/07 §7.2)
- [ ] T30 First hosted deploy (Render + Supabase, target 18 Oct — P0)
- [x] T29 Progress, consent, delete (spec/03 §3.3)
- [x] T31 Demo data (spec/03 §3.5; synthetic cohort, demo banner)
- [ ] T32 ARP digest (spec/09 §9.3; consent filter, n<10 suppression)
- [ ] T33 Trainer view + aggregates (spec/09 §9.4; suppression tests P0)
- [ ] T34 Coach review console (spec/09 §9.5)
- [ ] T35 Admin (spec/09 §9.6)
- [ ] T36 Sankul mode (spec/08 §8.7; P2 only if ahead)

## Checkpoints
- After T27 (stop and report)
- After T30 (stop and report)
- Every 3 tasks otherwise

## Deviations from spec
None.

## Self-Reviews
- T25 completed: Passlib/bcrypt password hashing, signed HttpOnly sessions (itsdangerous, 12h expiry), role route guards for teacher/arp/trainer/coach/admin, sliding window login rate limiter (5/min/IP), double-submit cookie CSRF protection, demo seed users across all 5 roles in `seed.py`.
- T26 completed: WebChannel protocol compliance, inbound message deduplication / idempotency on client_msg_id, per-teacher asyncio.Lock serialisation, pending status polling indicator, audio multipart with 2 MB limit, audio caching endpoint with private immutable header, realism rating endpoint, settings update endpoint. Connected `process_inbound_web` to real `SessionService(db_session=session)` from `backend/app/sessions/service.py` (`await session_service.handle_inbound(inbound)`), removed inline Hindi in HTTPException details to English, and added full end-to-end integration tests for text submission -> background processing -> polling, duplicate message deduplication, audio upload with MockSTT transcription, button press dispatch, and real onboarding turn flow.
- T27 completed: Jinja2 teacher chat template (`teacher.html`), single CSS (`app.css`), vanilla JS chat client with IndexedDB outbox queue (`chat.js`), MediaRecorder audio recorder with 16kbps mono and 90s/0.7s bounds (`recorder.js`), service worker with static cache and LRU 30 audio cache (`sw.js`), standalone PWA manifest (`manifest.json`), offline fallback page with cached 50 messages and try-in-class peer checklist (`offline.html`), lite mode toggle, and demo sample chips. Total uncompressed asset budget: 56.7 KB (comfortably below 150 KB limit).
- T31 completed: Synthetic demo cohort generator (`backend/app/db/demo_data.py`), 3-batch demonstration with suppression for n<10, deterministic PRNG seed 42, strict model='mock' honesty, and demo banner.
- T29 completed: Teacher progress page (`/teacher/progress`), 5-step evidence ladder, inline percentage score bars, explain-back key points status, consent toggling (`POST /teacher/consent`), deletion confirmation dialog (`GET /teacher/delete`), and full GDPR/DPDP purge (`POST /teacher/delete`).

### Data Deletion Semantics (spec/03 §3.3 vs spec/08 §8.1)
- `SessionRepository.purge_teacher_data(teacher_id)` (spec/08 §8.1 chat-based delete): Deletes chat turns, messages, and scores, resetting the teacher's session state in place so the teacher can restart conversational practice with 'नमस्ते' without losing their registered profile/account.
- `privacy.purge.purge_teacher_data(db, teacher_id)` (spec/03 §3.3 web / account deletion): Full permanent GDPR/DPDP-style purge. Cascades across all teacher records, scenes, turns, rehearsal scores, realism ratings, calibration labels, explain scores, adoption evidence ladder entries, ARP observations, session state, move path, scheduled jobs (with teacher or question payload), review items (tied to teacher or questions), messages, template send history, consent logs, teacher contact information, teacher profile, and linked AppUser account.
