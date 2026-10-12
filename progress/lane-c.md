# Lane C Progress (Operations & Analytics)

Branch: `lane-c`
Worktree: `../abhyas-c`
Port: 8003
Database: `abhyas_c` (waits for Docker Desktop)

## Tasks
- [x] T25 Auth & demo users (spec/09 §9.7, spec/14)
- [ ] T26 Web channel API (spec/07 §7.3)
- [ ] T27 Teacher chat PWA (spec/09 §9.2)
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
