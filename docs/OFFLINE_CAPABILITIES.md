# Offline Capabilities and Network Resilience

This document honestly describes what works offline, what requires an active internet connection, and how Abhyas handles low-connectivity environments (such as rural 2G/3G networks in Uttar Pradesh and Madhya Pradesh).

---

## 1. Executive Summary

| Capability | Offline (No Internet) | Low Network (Slow 2G/3G) | Full Broadband / 4G |
| :--- | :---: | :---: | :---: |
| **Classroom Practice Checklist** | **Full (Saved locally)** | Full | Full |
| **View Past Rehearsals & Coach Feedback** | **Full (Cached in IndexedDB)** | Full | Full |
| **View Past Guide (मार्गदर्शिका) Answers** | **Full (Cached in IndexedDB)** | Full | Full |
| **Play Previously Cached Voice Notes** | **Full (Up to 30 clips in SW cache)** | Full | Full |
| **Draft Teacher Turns (Outbox)** | **Queued locally in IndexedDB** | Auto-retry on backoff | Instant delivery |
| **New Simulated Child Responses** | Requires Server | Handled via exponential backoff | Real-time |
| **New Voice STT Transcription** | Requires Server | Handled via retry queue | Real-time (~2.5s) |
| **New LLM Feedback & Scoring** | Requires Server | Handled via retry queue | Real-time (~3-4s) |
| **New Guide Questions (RAG + LLM)** | Requires Server | Handled via retry queue | Real-time (~3s) |

---

## 2. What Works Offline (Honest Scope)

When a teacher loses internet access or visits a classroom in a low-connectivity area, the Progressive Web App (PWA) automatically serves `/offline.html` from the Service Worker cache:

1. **Classroom Teaching Move Checklist (`offline.html`)**:
   - The 4 core pedagogical steps for foundational numeracy/literacy practice (e.g. concrete materials, regrouping bundles, asking checking questions, peer observation) are fully interactive.
   - Checkbox states (`chk1` to `chk4`) are persisted in the browser's `localStorage` (`abhyas_chk_<id>`).
   - Teachers can check off steps in real-time during class without needing cellular data.

2. **Saved Rehearsal Transcripts & Coach Feedback**:
   - The browser maintains an IndexedDB store (`abhyas_chat_db` -> `messages_cache`).
   - Teachers can filter by **"सहेजे गए अभ्यास" (Saved Rehearsals)** to review earlier simulated child dialogues (Ravi, Priya, Aman) and Coach feedback advice before beginning their lesson.
   - Displays clean human speaker labels in Hindi or English (never internal database IDs or button keys).

3. **Cached Guide (मार्गदर्शिका) Answers**:
   - Teachers can filter by **"मार्गदर्शिका प्रश्नोत्तर" (Guide Q&A)** to re-read earlier pedagogical guidance on FLN competencies.

4. **Offline Outbox (`messages_outbox`)**:
   - If a teacher types or records an audio turn while disconnected, `chat.js` places the message into IndexedDB `messages_outbox`.
   - The client UI displays an offline indicator (`ui_offline_banner`).
   - Upon reconnecting (`window.addEventListener('online')`), the outbox is automatically flushed and synced with the server in chronological order.

5. **Audio Cache**:
   - The Service Worker (`sw.js`) intercepts requests to `/api/audio/*` and keeps an LRU cache of the last 30 played audio files (`abhyas-audio-v1`).
   - Previously listened audio turns can be re-played even if connectivity is interrupted.

---

## 3. What Does NOT Work Offline (Honest Scope)

Abhyas does **not** run on-device machine learning or on-device LLMs. The following core AI features strictly require server connectivity:

1. **Voice Speech-to-Text (STT)**:
   - Voice audio is transcribed using the cloud Sarvam AI STT API (`saaras:v2`).
   - When offline, audio cannot be converted to text until network connectivity is restored.

2. **Simulated Child Response Generation**:
   - Simulated children (Ravi, Priya, Aman) are governed by the deterministic state machine and rule engine on the FastAPI backend (`backend/app/rule_engine/`).
   - Children's answers cannot be generated locally without reaching the backend.

3. **Coach Feedback & Rubric Scoring**:
   - Pedagogical coaching analysis, empathy scoring, and scaffolding generation rely on Claude Sonnet/Haiku models hosted by Anthropic.
   - Real-time coaching prompts require server execution.

4. **New Guide Questions**:
   - Vector similarity search (`pgvector` cosine distance over NIPUN Bharat sandarshikas) and synthesis require the backend PostgreSQL database.

---

## 4. Technical Architecture for Low-Connectivity Environments

### 4.1 Service Worker (`backend/app/web/static/sw.js`)
- **Static Asset Cache**: Cache-first strategy for `/static/app.css`, `/static/chat.js`, `/static/recorder.js`, and `/static/manifest.json`.
- **Navigation Fallback**: Navigation requests use network-first with exponential backoff:
  ```javascript
  const NAV_BACKOFF_MS = [1000, 2000, 4000, 8000, 15000];
  ```
  If all retries fail or the device is offline, `sw.js` returns `/offline.html` from `CACHE_NAME_STATIC`.

### 4.2 Data Consumption & Lite Mode
- **Zero Build / Tiny Footprint**: Server-rendered HTML with vanilla JavaScript and a single CSS file. Initial payload is < 150 KB.
- **Lite Mode (कम डेटा मोड)**:
  - Accessible via toggle in the Teacher PWA header.
  - Automatically suppresses audio autoplay, streaming only text turns.
  - Reduces session data consumption from ~3.5 MB per rehearsal to < 100 KB, allowing smooth practice on 2G connections.
