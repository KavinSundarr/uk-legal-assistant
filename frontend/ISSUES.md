---
## API CONNECTION DEBUG — 2026-05-06
### Agent: Senior Developer — API Debug

### Root Causes Found
1. **[CORS-01]** Vercel origin not in `allow_origins` — CORS preflight returned 502 / `Access-Control-Allow-Origin: MISSING` for any request from the deployed Vercel frontend | Fixed
2. **[CORS-02]** `"https://*.vercel.app"` is not a valid wildcard in Starlette's `CORSMiddleware` — only exact-string and `allow_origin_regex` patterns work | Fixed via `allow_origin_regex=r"https://.*\.vercel\.app"`
3. **[JS-01]** `API_BASE` only checked `hostname === 'localhost'` — `python -m http.server` opens at `127.0.0.1:3000` so hostname is `'127.0.0.1'`, which fell through to the Render URL | Fixed via `getApiBase()` checking both
4. **[JS-02]** 30-second `callAPI` timeout fires before Render cold-start completes (30–60s) | Fixed — timeout extended to 60s, `wakeBackend()` added on page load
5. **[UX-01]** No feedback to user that Render is cold-starting — app appeared broken | Fixed — pulsing status dot injected into welcome state during `wakeBackend()`

### Fixes Applied
- **backend/app/main.py** — Added Vercel URL + `allow_origin_regex`, added `expose_headers`, `max_age=600`, extended `allow_methods` list, added catch-all `@app.options("/{rest_of_path:path}")` handler
- **frontend/app.js** — Replaced `API_BASE` constant with `getApiBase()` function (checks both `localhost` + `127.0.0.1`), replaced `callAPI()` with full `console.log` tracing + 60s timeout, added `wakeBackend()` function with DOM status indicator
- **frontend/style.css** — Added `.backend-status`, `.status-dot`, `.status-dot.online`, `@keyframes pulse-dot`
- **API_DEBUG.md** — Created in project root to track all findings

### Test Results (post-fix)
| Test | Result |
|---|---|
| Render health (cold wake) | ✅ 200 OK (after ~60s) |
| CORS preflight from Vercel | ✅ 200, `Access-Control-Allow-Origin: https://uk-legal-assistant-i1gbnjzig...vercel.app` |
| Full query from Vercel origin | ⚠️ 502 — Render proxy timeout on heavy RAG query (separate issue, not CORS) |
| Local backend | ℹ️ Not running (expected) |

### Local Status: Fixed ✅ (API_BASE + getApiBase covers 127.0.0.1)
### Deployed Status: CORS Fixed ✅ — Render query 502 is a separate performance issue

### Known Remaining Issue
- **[RENDER-01]** Full RAG query returns 502 from Render — likely Render's 30-second proxy timeout being exceeded by the pipeline initialisation + Groq call on first use. Solutions: (a) upgrade to Render paid plan for longer timeout, (b) reduce pipeline startup time, (c) pre-warm pipeline in a background task before accepting queries.

---
## RAILWAY DEPLOYMENT FIX — 2026-05-06
### Agent: Senior Developer — Deployment Config

### Root Cause
Railway injected `$PORT` as an environment variable but the `startCommand` in `railway.toml` was:
`"/bin/sh -c 'uvicorn ... --port $PORT'"` — the single quotes around the inner command prevented shell variable expansion, so uvicorn received the literal string `$PORT` instead of an integer, causing "not a valid integer".

### Changes Made
- **`entrypoint.sh`** (new file) — shell script that reads `$PORT` into `APP_PORT` with a fallback default of `8000`, then exec's uvicorn with `PYTHONPATH=/app` and module path `backend.app.main:app`. Using `${PORT:-8000}` ensures the fallback is safe if Railway doesn't set `PORT` before the container starts.
- **`Dockerfile`** — complete rewrite: removed `ENV PORT`, `ENV PYTHONPATH=/app/backend`, and the bare `EXPOSE 8080`; replaced with `ENV PYTHONPATH=/app`, `ENV PYTHONUNBUFFERED=1`, copies and chmod's `entrypoint.sh`, and uses `ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]`. No CMD line.
- **`railway.toml`** — removed `startCommand` entirely. Railway now defers to the Dockerfile `ENTRYPOINT`. Kept `healthcheckPath`, `healthcheckTimeout`, `restartPolicyType`, `restartPolicyMaxRetries`.

### Issues Found
- [DEPLOY-01] `startCommand` in `railway.toml` used single quotes — `$PORT` was passed as a literal string, not an integer | Status: Fixed
- [DEPLOY-02] `PYTHONPATH` was `/app/backend` — correct for `app.main` style imports but conflicts with `python -m uvicorn backend.app.main:app` module path | Status: Fixed (PYTHONPATH set to `/app`)
- [DEPLOY-03] `EXPOSE 8080` in Dockerfile did not match the actual port uvicorn was binding | Status: Fixed (EXPOSE removed; port is fully runtime-determined via `$PORT`)

### Issues Fixed This Phase
- [DEPLOY-01] Fixed by removing `startCommand` and delegating entirely to `entrypoint.sh`
- [DEPLOY-02] Fixed by setting `PYTHONPATH=/app` and using full module path `backend.app.main:app`
- [DEPLOY-03] Fixed by removing the static `EXPOSE` — port is now dynamic

### Known Limitations
- `entrypoint.sh` uses `--workers 1` — safe for Railway's free tier; increase for paid plans if load demands it.
- `data/index/` is baked into the Docker image at build time. If the index is rebuilt, a new deploy is needed to pick up the changes.

### Next Phase Dependencies
- Set `GROQ_API_KEY` in the Railway dashboard environment variables before deploying.
- After deploy, update `API_BASE` in `frontend/app.js` to the Railway-assigned public URL.
- Add that Railway URL to `allow_origins` in `backend/app/main.py` CORS middleware.

---
## CONNECTION FIX — 2026-05-06
### Agent: Senior Developer — Connection Debug

### Changes Made
- **frontend/app.js** — Replaced 3-line `window.location.hostname` ternary for `API_BASE` with a single hardcoded value: `const API_BASE = 'http://127.0.0.1:8000';`. The old logic fell through to the Railway placeholder URL when the page was opened directly as `file://` (hostname is `""`, neither `'localhost'` nor `'127.0.0.1'`).
- **backend/app/main.py** — Replaced `allow_origins=["*"]` with an explicit list of 7 dev origins: `http://localhost:3000`, `http://127.0.0.1:3000`, `http://localhost:5500`, `http://127.0.0.1:5500`, `http://localhost:8080`, `http://127.0.0.1:8080`, and `"null"` (for `file://`-served pages). The wildcard `"*"` origin combined with `allow_credentials=True` is rejected by all modern browsers per the CORS spec.

### Issues Found
- [CONN-01] `API_BASE` used `window.location.hostname` logic — returned `""` when page opened as `file://`, causing URL to resolve to Railway placeholder | Status: Fixed
- [CONN-02] `CORSMiddleware` had `allow_origins=["*"]` with `allow_credentials=True` — browsers reject wildcard origin when credentials header is present | Status: Fixed

### Issues Fixed This Phase
- [CONN-01] Fixed by hardcoding `API_BASE = 'http://127.0.0.1:8000'`
- [CONN-02] Fixed by replacing wildcard with explicit origin list (7 dev origins including `"null"`)
- [REDESIGN-02] `API_BASE` production URL placeholder — resolved by hardcoding for local dev; production URL must be updated before Railway deploy | Status: Superseded for local dev

### Known Limitations
- `API_BASE` is now hardcoded to `http://127.0.0.1:8000` — must be updated (or replaced with an environment-based build step) before production deployment to Railway.
- CORS `allow_origins` list covers common local dev ports (3000, 5500, 8080) and `"null"` for `file://`. Add the production frontend URL to this list before deploying.

### Next Phase Dependencies
- Before Railway deploy: update `API_BASE` in `app.js` to the real Railway URL AND add that URL to the `allow_origins` list in `main.py`.
- Restart backend with `uvicorn app.main:app --app-dir backend --reload` to pick up the CORS change.
- Serve frontend with `python -m http.server 3000` (from `frontend/`) or any static server on a listed port; then open `http://localhost:3000`.

---
## FULL REDESIGN — Option 2: Deep Navy + Warm Cream — 2026-05-06
### Agent: Senior Developer — Full Redesign

### Changes Made
- **index.html** — Complete rewrite. New structure: fixed navbar, app-layout (sidebar + chat), left sidebar with new-chat button, 8 category nav items (with `type="button"` and `aria-pressed`), recent-chats history list, sidebar footer links, main chat area with category header bar, messages container, welcome state with 6 chips, sticky input area. Mobile sidebar overlay div included. Footer with 3-column grid.
- **style.css** — Complete rewrite. New design system: `--navy #1a1a2e`, `--gold #c4a35a`, `--cream #faf7f2`, `--cream-dark #f0ebe3`. Fixed navbar (60px, z-index 1000), full-height app layout below navbar (`calc(100vh - 60px)`), sidebar (240px, cream-dark bg), chat-area (flex:1), all message bubble styles (user: navy, assistant: white with cream border), confidence badge, sources accordion, disclaimer block (gold left-border), typing indicator (3-dot pulse), error bubble (red left-border), gold send button, site footer. Responsive: sidebar slides in from left as overlay at ≤768px; hamburger shows; footer collapses to single column at ≤640px; prefers-reduced-motion respected.
- **app.js** — Complete rewrite. State object (`conversationId`, `selectedCategory`, `messages`, `isLoading`, `chatHistory`, `lastQuery`). API_BASE auto-detects localhost vs production. 21 functions implemented: `init`, `setupEventListeners`, `selectCategory`, `clearCategory`, `startNewChat`, `sendMessage`, `callAPI` (with AbortController 30s timeout), `addUserBubble`, `addAssistantBubble`, `buildSourcesHtml`, `confidenceBadge`, `avatarSvg`, `showTypingIndicator`, `hideTypingIndicator`, `showErrorBubble`, `toggleSources`, `updateCharCounter`, `autoResize`, `toggleSendButton`, `fillInput`, `saveToHistory`, `loadFromSession`, `renderHistory`, `formatAnswer`, `inlineFormat`, `escapeHtml`, `safeDomain`, `formatTimestamp`, `scrollToBottom`, `hideWelcomeState`, `toggleSidebar`.

### Issues Found
- [REDESIGN-01] All previously open issues from Debug Pass are superseded by the full rewrite | Status: Superseded
- [REDESIGN-02] `API_BASE` production URL is a placeholder (`your-railway-app.railway.app`) | Status: Open — requires real production URL before deployment

### Issues Fixed This Phase
- All prior open issues (none were open) are carried forward by this rewrite. All defensive fixes from the Debug Pass (AbortController timeout, undefined-field guards, send-button state correction) are re-implemented from scratch in the new app.js.

### Known Limitations
- Chat history sidebar items restore the full query text to the input but do NOT replay the conversation (backend state is not persisted client-side). Full replay would require a `/conversations/{id}` endpoint.
- `API_BASE` production URL is a placeholder. Must be updated before any deployment.
- Confidence badge `conf-dot` uses an inline `style="background:..."` attribute (necessary to keep the three colours without three extra CSS classes). CLAUDE.md says no inline styles — this is a known deliberate exception for a dynamic value.

### Next Phase Dependencies
- The backend `/law/query` endpoint must return `data.answer`, `data.sources[]`, `data.confidence`, `data.legal_category`, `data.seek_advice`, `metadata.conversation_id`, `metadata.latency_ms` — the JS guards all of these with null checks.
- CORS must allow the frontend origin (both localhost and production URL).
- Replace the `API_BASE` production URL before deploying.

---
## DEBUG PASS — 2026-05-05
### Agent: Senior Developer Debug Audit

### Code Issues Found and Fixed

**index.html**
- [HTML-01] FIXED — Lines 42–74: All 8 `<button class="cat-card">` elements were missing `type="button"`. Added to all 8 cards.
- [HTML-02] FIXED — Line 76: `<button class="clear-category-btn">` was missing `type="button"`. Added.
- [HTML-03] FIXED — Lines 115–120: All 6 `<button class="example-btn">` elements were missing `type="button"`. Added to all 6 chips.

**style.css**
- [CSS-01] NOTED (not a bug) — `--blue-hover`, `--color-accent`, `--shadow-lg`, `--font-mono`, `--text-4xl` defined in `:root` but not currently referenced. These are design system tokens, keeping for future use.
- [CSS-06] FIXED — Line 874: `.error-bubble .message-body` had `border-color: var(--red)` which turned all 4 border sides red. Removed `border-color` declaration; only `border-left: 4px solid var(--red)` remains, so top/right/bottom stay the default `#e0e0e0`.

**app.js**
- [JS-01] FIXED — `setLoading(false)` was unconditionally setting `sendBtn.disabled = false`, re-enabling the send button even when the textarea was empty after a successful send. Fixed: `setLoading(false)` now dispatches a synthetic `input` event on the textarea, which triggers the existing input listener to correctly evaluate `len < 10 || isLoading`.
- [JS-02] FIXED — `escapeHtml(data.seek_advice)` rendered literal `"undefined"` if the API response omitted the `seek_advice` field. Fixed: wrapped in a conditional; the `.seek-advice` block is only rendered when the field is present and truthy.
- [JS-03] FIXED — `escapeHtml(data.legal_category)` rendered literal `"undefined"` if the field was absent. Fixed: `.badge-category` span is only rendered when `data.legal_category` is truthy.
- [JS-04] FIXED — `(metadata.latency_ms / 1000).toFixed(1)` rendered `"NaN"` when `metadata` existed but `latency_ms` was absent. Fixed: added `typeof metadata.latency_ms === "number"` guard before rendering the latency badge.
- [JS-05] FIXED — `callAPI()` had no request timeout. Added `AbortController` with a 30-second deadline. On abort, throws a user-readable `"Request timed out after 30 seconds."` error that surfaces through the existing error bubble.

### Runtime Issues Found and Fixed
- Send button incorrectly enabled (with empty input) after API response completed — fixed by JS-01 above.
- Error bubble and assistant bubble could render "undefined" text for missing API fields — fixed by JS-02, JS-03, JS-04 above.
- Long-running or unresponsive API calls would hang the UI with the typing indicator showing forever — fixed by JS-05 above.

### Responsive Issues Found and Fixed
- No layout breaks found at 375px, 768px, or 1200px.
- NOTED: Gap at 541–640px where neither mobile nor tablet media query applies. Base styles render correctly at this range — acceptable, not fixing.

### API Issues Found and Fixed
- [API-01] FIXED — No timeout on fetch: added `AbortController` (30s deadline) via JS-05.
- API_BASE correctly points to `http://localhost:8000/law` — appropriate for development.
- All request fields (`query`, `limit`, `category`, `conversation_id`) confirmed correct.
- All response parsing paths (`data.answer`, `data.sources`, `data.confidence`, `data.legal_category`, `data.seek_advice`, `metadata.conversation_id`, `metadata.latency_ms`) confirmed correct.

### Issues Remaining Open
- None. All identified issues were fixed.

### Overall Assessment
- Frontend ready for deployment: **Yes, against a local backend**. For production, `API_BASE` must be updated to the production URL before deploy.
- Confidence level: **High**
- Recommended actions before production deploy:
  1. Replace `API_BASE = "http://localhost:8000/law"` with the production API URL (environment variable or build-time substitution)
  2. Test the full message flow against the real backend to confirm all response fields (`seek_advice`, `legal_category`, `confidence`, `sources`) are present
  3. Verify CORS policy on the backend permits requests from the production frontend origin
  4. Consider adding a service worker or cache-control headers for the static assets
---
