# First-Load Transfer Size Audit Report

**Environment**: `local, mock providers, mock DB, empty chat history`  
**Timestamp**: 2026-10-23 13:29:44 UTC  
**Status**: ✅ PASSED (Budget: < 150.0 KB)  

> Note: In the local test run, `/teacher` HTML is measured with mock providers, a mock DB, and an empty chat history, which represents a lower bound for the page size.

## 1. Executive Summary

- **Teacher Chat First-Load (HTML + CSS + JS)**: **32.28 KB** gzip (124.34 KB raw)
- **Total Asset Payload (All Offline Assets)**: **40.12 KB** gzip (147.63 KB raw)
- **Budget Headroom**: **25.66 KB** under the 150 KB ceiling (82.9% of budget)
- **Target Constraint**: Spec 09 §9.2 requires first-load payload < 150 KB excluding audio to ensure accessibility on low-cost Android smartphones over 2G/3G connections.

## 2. Asset Breakdown

| Asset Name | Path | Kind | Status | Raw Size (KB) | Gzip Size (KB) |
|---|---|---|---|---|---|
| `Login Page (HTML)` | `/login` | HTML | 200 | 7.15 KB | 2.19 KB |
| `Teacher Chat PWA (HTML)` | `/teacher` | HTML | 200 | 18.53 KB | 4.99 KB |
| `manifest.json` | `/manifest.json` | JSON | 200 | 0.5 KB | 0.29 KB |
| `ack.js` | `/static/ack.js` | JS | 200 | 1.07 KB | 0.56 KB |
| `app.css?v=dev-082acd32` | `/static/app.css?v=dev-082acd32` | CSS | 200 | 32.3 KB | 7.29 KB |
| `chat.js?v=dev-082acd32` | `/static/chat.js?v=dev-082acd32` | JS | 200 | 66.46 KB | 17.6 KB |
| `recorder.js?v=dev-082acd32` | `/static/recorder.js?v=dev-082acd32` | JS | 200 | 6.54 KB | 2.1 KB |
| `sw.js` | `/sw.js` | JS | 200 | 5.27 KB | 1.71 KB |
| `offline.html` | `/offline.html` | HTML | 200 | 9.8 KB | 3.38 KB |

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
- Measured: 124.34 KB raw < 150.00 KB
