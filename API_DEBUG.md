# API Debug Session — 2026-05-06

## Environment
- Frontend local: http://localhost:3000
- Frontend deployed: https://uk-legal-assistant-i1gbnjzig-kavinsundarrs-projects.vercel.app
- Backend deployed: https://uk-legal-assistant.onrender.com
- Backend local: http://127.0.0.1:8000

## Issues Found

### [BUG-01] CORS — Vercel origin completely missing from allow_origins
- **File**: backend/app/main.py
- **Detail**: allow_origins contained only localhost variants and "null".
  No Vercel URL was present. Browser CORS preflight from Vercel returned
  502 with Access-Control-Allow-Origin: MISSING.
- **Status**: Fixed

### [BUG-02] Render free tier cold start exceeds 30s callAPI timeout
- **File**: frontend/app.js
- **Detail**: Render spins down after ~15 min inactivity. Cold start takes
  30-60 seconds. The existing AbortController timeout of 30s fires before
  Render is ready, causing "Network error" on first request.
- **Status**: Fixed — wakeBackend() on page load + timeout extended to 60s

### [BUG-03] API_BASE missing 127.0.0.1 check
- **File**: frontend/app.js
- **Detail**: Only checked hostname === 'localhost'. Serving via
  `python -m http.server` opens at http://127.0.0.1:3000 —
  hostname is '127.0.0.1', falls through to Render URL.
- **Status**: Fixed — getApiBase() checks both localhost and 127.0.0.1

### [BUG-04] No backend status feedback on page load
- **File**: frontend/app.js / style.css
- **Detail**: User sees no indication that Render is waking up.
  First-time users think the app is broken when it's just cold-starting.
- **Status**: Fixed — wakeBackend() adds a pulsing status dot to welcome state

## Fixes Applied

1. backend/app/main.py — Added Vercel URLs + allow_origin_regex for
   *.vercel.app pattern + OPTIONS catch-all handler + expose_headers + max_age
2. frontend/app.js — Replaced API_BASE with getApiBase(), replaced callAPI()
   with full console logging, added wakeBackend() with DOM status indicator,
   extended timeout to 60s
3. frontend/style.css — Added .backend-status, .status-dot, pulse-dot keyframes

## Test Results

| Test                        | Before fix | After fix |
|-----------------------------|------------|-----------|
| Render health (cold)        | Timeout    | 200 OK (after ~60s wake) |
| CORS preflight from Vercel  | 502 / MISSING | — (pending redeploy) |
| Query from Vercel           | Blocked    | — (pending redeploy) |
| Local backend               | N/A        | N/A (not running) |

## Status
- Fixes committed and pushed to GitHub.
- Backend redeploy on Render will pick up CORS changes automatically on next push.
- Local: Start backend with `start_dev.bat`, open http://localhost:3000.
- Deployed: Vercel frontend will connect once Render redeploys with CORS fix.
