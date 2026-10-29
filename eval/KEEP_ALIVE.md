# Evaluator Review Keep-Alive & Cold-Start Strategy

## 1. Context & Objective
During the AI for Foundational Learning Hackathon 2026 evaluation window (**2 Nov to 9 Nov 2026**; shortlist announced 10 Nov; finale 18 Nov), evaluators have ~1 hour hands-on testing time with the hosted deployment on Render. Free-tier cloud instances (Render Web Services) spin down after 15 minutes of inactivity, resulting in a 40–60 second cold-start spin-up latency if visited while dormant.

Our objective is **zero cold-start interruption** during evaluation, with transparent visual fallbacks if a spin-up ever occurs.

**The pinger must run through 9 Nov, and through 18 Nov if the team is shortlisted.** Start it before 2 Nov and do not stop it after submission day (1 Nov). The free Render database listed in `docs/DEPLOY.md` expires on 2026-11-20, two days after the finale: check it before 18 Nov.

---

## 2. Recommended Primary Keep-Alive: External Uptime Pinger
The recommended and most robust primary mechanism is a free external HTTP pinger (such as **UptimeRobot**, **BetterStack**, or **Cron-Job.org**):

- **Target URL**: `https://<hosted-app-domain>/healthz`
- **Method**: HTTP `GET`
- **Interval**: Every 5 minutes (300 seconds), well within Render's 15-minute idle limit.
- **Active window**: from before 2 Nov until 9 Nov 2026 (and until 18 Nov if shortlisted).
- **Expected Status**: `200 OK`
- **Why External?**:
  - An external monitoring service runs independently of local developer laptops or CI runners.
  - Generates zero cost and requires no server credentials.
  - Automatically records historical uptime and response time.

---

## 3. Secondary / Local Keep-Alive Script: `scripts/keep_alive.py`
Alongside external monitoring, `scripts/keep_alive.py` is maintained in the repository for:
- Pre-warming or sustaining the instance from a developer workstation during synchronous evaluation or live presentations.
- Running smoke checks via `python scripts/keep_alive.py --url <url> --once`.

### Usage
```bash
# Keep instance alive by pinging /healthz every 4 minutes (240s)
python scripts/keep_alive.py --url https://abhyas.onrender.com/healthz --interval 240

# Single health verification pulse
python scripts/keep_alive.py --url https://abhyas.onrender.com/healthz --once
```

---

## 4. Cold-Start Client UX & Resilience
If an evaluator accesses the application while the container is spinning up:
1. **PWA Shell Instant Render**: The HTML shell and UI assets render immediately from browser cache / service worker (under 150 KB budget).
2. **5-Second Waking Hint**: In `backend/app/web/static/chat.js` (`netInit`), if an initial poll or request does not respond within 5,000 ms, the UI automatically displays:
   - *"सर्वर जाग रहा है — इसमें करीब एक मिनट लग सकता है…"* (catalogue key `ui_chat_cold_start`: "The server is waking up; it can take about a minute")
3. **HTTP 502 / Spin-Up Handling**:
   - If Render returns an HTTP `502 Bad Gateway` or `503 Service Unavailable` while booting, the client keeps the waking hint active and retries transparently using exponential backoff without dropping the teacher's input or showing an ugly crash.
   - Once the first HTTP `200` response arrives, the waking hint immediately disappears and normal messaging resumes.
4. **Fast-Track Chip Locking**: Fast-Track chips are locked while any request is in flight and re-enable upon successful response, failure notification, or 90-second safety timeout, preventing double-tap race conditions during slow spin-ups.
