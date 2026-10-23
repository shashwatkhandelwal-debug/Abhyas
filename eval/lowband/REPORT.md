# First-Load Transfer Size Audit Report

**Environment**: `local, mock providers, mock DB, empty chat history`  
**Timestamp**: 2026-10-23 15:45:16 UTC  
**Status**: ✅ PASSED (Budget: < 150.0 KB)  

> Note: In the local test run, `/teacher` HTML is measured with mock providers, a mock DB, and an empty chat history, which represents a lower bound for the page size.

## 1. Executive Summary

- **Teacher Chat First-Load (HTML + CSS + JS)**: **32.22 KB** gzip (124.89 KB raw)
- **Total Asset Payload (All Offline Assets)**: **39.9 KB** gzip (147.74 KB raw)
- **Budget Headroom**: **25.11 KB** under the 150 KB ceiling (83.3% of budget)
- **Target Constraint**: Spec 09 §9.2 requires first-load payload < 150 KB excluding audio to ensure accessibility on low-cost Android smartphones over 2G/3G connections.

## 2. Asset Breakdown

| Asset Name | Path | Kind | Status | Raw Size (KB) | Gzip Size (KB) |
|---|---|---|---|---|---|
| `Login Page (HTML)` | `/login` | HTML | 200 | 7.15 KB | 2.19 KB |
| `Teacher Chat PWA (HTML)` | `/teacher` | HTML | 200 | 18.49 KB | 4.99 KB |
| `manifest.json` | `/manifest.json` | JSON | 200 | 0.5 KB | 0.29 KB |
| `ack.js` | `/static/ack.js` | JS | 200 | 1.07 KB | 0.56 KB |
| `app.css?v=dev-88692bfe` | `/static/app.css?v=dev-88692bfe` | CSS | 200 | 33.05 KB | 7.34 KB |
| `chat.js?v=dev-88692bfe` | `/static/chat.js?v=dev-88692bfe` | JS | 200 | 66.47 KB | 17.59 KB |
| `recorder.js?v=dev-88692bfe` | `/static/recorder.js?v=dev-88692bfe` | JS | 200 | 6.38 KB | 2.01 KB |
| `sw.js` | `/sw.js` | JS | 200 | 4.83 KB | 1.54 KB |
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
- Measured: 124.89 KB raw < 150.00 KB
