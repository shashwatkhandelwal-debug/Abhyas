# First-Load Transfer Size Audit Report

**Environment**: `local, mock providers, mock DB, empty chat history`  
**Timestamp**: 2026-10-17 16:21:46 UTC  
**Status**: ✅ PASSED (Budget: < 150.0 KB)  

> Note: In the local test run, `/teacher` HTML is measured with mock providers, a mock DB, and an empty chat history, which represents a lower bound for the page size.

## 1. Executive Summary

- **Teacher Chat First-Load (HTML + CSS + JS)**: **15.4 KB** gzip (58.84 KB raw)
- **Total Asset Payload (All Offline Assets)**: **21.84 KB** gzip (78.54 KB raw)
- **Budget Headroom**: **91.16 KB** under the 150 KB ceiling (39.2% of budget)
- **Target Constraint**: Spec 09 §9.2 requires first-load payload < 150 KB excluding audio to ensure accessibility on low-cost Android smartphones over 2G/3G connections.

## 2. Asset Breakdown

| Asset Name | Path | Kind | Status | Raw Size (KB) | Gzip Size (KB) |
|---|---|---|---|---|---|
| `Login Page (HTML)` | `/login` | HTML | 200 | 5.64 KB | 1.68 KB |
| `Teacher Chat PWA (HTML)` | `/teacher` | HTML | 200 | 9.83 KB | 3.27 KB |
| `manifest.json` | `/manifest.json` | JSON | 200 | 0.52 KB | 0.29 KB |
| `app.css` | `/static/app.css` | CSS | 200 | 19.0 KB | 3.93 KB |
| `chat.js` | `/static/chat.js` | JS | 200 | 24.83 KB | 6.31 KB |
| `recorder.js` | `/static/recorder.js` | JS | 200 | 4.66 KB | 1.59 KB |
| `sw.js` | `/static/sw.js` | JS | 200 | 3.38 KB | 1.1 KB |
| `sw.js` | `/sw.js` | JS | 200 | 3.38 KB | 1.1 KB |
| `offline.html` | `/offline.html` | HTML | 200 | 7.3 KB | 2.57 KB |

## 3. Low-Connectivity Verification Matrix

| Feature | Implementation | Status |
|---|---|---|
| **Server-rendered HTML** | Jinja2 templates (`teacher.html`, `login.html`), no React or JS framework build step | Measured |
| **Single CSS bundle** | `/static/app.css` containing all styles, typography, and responsive layouts | Measured |
| **Vanilla JS Client** | `/static/chat.js` with IndexedDB outbox queue & auto-retry | Measured |
| **Voice Recorder** | `/static/recorder.js` MediaRecorder 16 kbps mono recorder | Measured |
| **Service Worker** | `/static/sw.js` cache-first for static assets, LRU 30 audio cache, offline navigation fallback | Code present (not exercised) |
| **Offline Outbox** | Queues text and audio messages in IndexedDB `outbox` table during disconnects | Code present (not exercised) |
| **Offline Fallback Page** | `/offline.html` cached by Service Worker; displays last 50 cached messages & peer checklist | Code present (not exercised) |
| **Lite Mode (लाइट मोड)** | Hides audio autoplay; renders on-demand audio on tap to preserve 2G/3G data bundles | Code present (not exercised) |

## 4. Assertion

Assertion `total_first_load < 150 KB`: **✅ PASSED**
- Measured: 58.84 KB raw < 150.00 KB
