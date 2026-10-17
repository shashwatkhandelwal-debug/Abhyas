# First-Load Transfer Size Audit Report

**Environment**: `local, mock providers`  
**Timestamp**: 2026-10-17 12:49:27 UTC  
**Status**: ✅ PASSED (Budget: < 150.0 KB)  

## 1. Executive Summary

- **Teacher Chat First-Load (HTML + CSS + JS)**: **14.61 KB** gzip (55.61 KB raw)
- **Total Asset Payload (All Offline Assets)**: **21.05 KB** gzip (75.3 KB raw)
- **Budget Headroom**: **94.39 KB** under the 150 KB ceiling (37.1% of budget)
- **Target Constraint**: Spec 09 §9.2 requires first-load payload < 150 KB excluding audio to ensure accessibility on low-cost Android smartphones over 2G/3G connections.

## 2. Asset Breakdown

| Asset Name | Path | Kind | Status | Raw Size (KB) | Gzip Size (KB) |
|---|---|---|---|---|---|
| `Login Page (HTML)` | `/login` | HTML | 200 | 5.64 KB | 1.67 KB |
| `Teacher Chat PWA (HTML)` | `/teacher` | HTML | 200 | 9.83 KB | 3.26 KB |
| `manifest.json` | `/manifest.json` | JSON | 200 | 0.52 KB | 0.29 KB |
| `app.css` | `/static/app.css` | CSS | 200 | 19.0 KB | 3.93 KB |
| `chat.js` | `/static/chat.js` | JS | 200 | 21.59 KB | 5.53 KB |
| `recorder.js` | `/static/recorder.js` | JS | 200 | 4.66 KB | 1.59 KB |
| `sw.js` | `/static/sw.js` | JS | 200 | 3.38 KB | 1.1 KB |
| `sw.js` | `/sw.js` | JS | 200 | 3.38 KB | 1.1 KB |
| `offline.html` | `/offline.html` | HTML | 200 | 7.3 KB | 2.57 KB |

## 3. Low-Connectivity Verification Matrix

| Feature | Implementation | Verified |
|---|---|---|
| **Server-rendered HTML** | Jinja2 templates (`teacher.html`, `login.html`), no React or JS framework build step | Yes |
| **Single CSS bundle** | `/static/app.css` (4.0 KB gzip) containing all styles, typography, and responsive layouts | Yes |
| **Vanilla JS Client** | `/static/chat.js` (5.7 KB gzip) with IndexedDB outbox queue & auto-retry | Yes |
| **Voice Recorder** | `/static/recorder.js` (1.6 KB gzip) MediaRecorder 16 kbps mono recorder | Yes |
| **Service Worker** | `/static/sw.js` cache-first for static assets, LRU 30 audio cache, offline navigation fallback | Yes |
| **Offline Outbox** | Queues text and audio messages in IndexedDB `outbox` table during disconnects | Yes |
| **Offline Fallback Page** | `/offline.html` cached by Service Worker; displays last 50 cached messages & peer checklist | Yes |
| **Lite Mode (लाइट मोड)** | Hides audio autoplay; renders on-demand audio on tap to preserve 2G/3G data bundles | Yes |

## 4. Assertion

Assertion `total_first_load < 150 KB`: **✅ PASSED**
- Measured: 55.61 KB raw < 150.00 KB
