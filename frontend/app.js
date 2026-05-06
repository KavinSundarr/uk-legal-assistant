/* ═══════════════════════════════════════════════════════════════════════════
   UK Legal Assistant — app.js
   Option 2: Deep Navy + Warm Cream redesign
   Vanilla JS — no frameworks. Full state management + chat history.
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── API base URL ───────────────────────────────────────────────────────── */
const API_BASE = 'http://127.0.0.1:8000';

/* ── Application state ──────────────────────────────────────────────────── */
const state = {
  conversationId:   null,   // backend conversation ID
  selectedCategory: null,   // active legal category filter
  messages:         [],     // message log for current session
  isLoading:        false,  // true while awaiting API response
  chatHistory:      [],     // sidebar history entries
  lastQuery:        null,   // most recent query (for retry + history)
};

/* ── Category display names ─────────────────────────────────────────────── */
const CATEGORY_LABELS = {
  immigration: 'Immigration Law',
  driving:     'Driving Law',
  employment:  'Employment Law',
  housing:     'Housing Law',
  student:     'Student Law',
  healthcare:  'Healthcare',
  benefits:    'Benefits & Welfare',
  criminal:    'Criminal Law',
};

/* ── DOM references (populated by init) ────────────────────────────────── */
let dom = {};

/* ── Typing indicator DOM element reference ─────────────────────────────── */
let typingEl = null;

/* ═══════════════════════════════════════════════════════════════════════════
   INIT
   ═══════════════════════════════════════════════════════════════════════════ */

/** Boot the app once the DOM is ready */
document.addEventListener('DOMContentLoaded', init);

function init() {
  dom = {
    messages:          document.getElementById('messages'),
    welcomeState:      document.getElementById('welcomeState'),
    queryInput:        document.getElementById('queryInput'),
    sendBtn:           document.getElementById('sendBtn'),
    charCounter:       document.getElementById('charCounter'),
    historyList:       document.getElementById('historyList'),
    newChatBtn:        document.getElementById('newChatBtn'),
    chatCategoryLabel: document.getElementById('chatCategoryLabel'),
    clearCategoryBtn:  document.getElementById('clearCategoryBtn'),
    catItems:          document.querySelectorAll('.cat-item'),
    chips:             document.querySelectorAll('.chip'),
    hamburgerBtn:      document.getElementById('hamburgerBtn'),
    sidebar:           document.getElementById('sidebar'),
    sidebarOverlay:    document.getElementById('sidebarOverlay'),
  };

  loadFromSession();
  setupEventListeners();
  dom.queryInput.focus();
}

/* ═══════════════════════════════════════════════════════════════════════════
   EVENT LISTENERS
   ═══════════════════════════════════════════════════════════════════════════ */

/** Wire up all interactive elements */
function setupEventListeners() {
  // Category selection
  dom.catItems.forEach(btn => {
    btn.addEventListener('click', () => selectCategory(btn.dataset.category));
  });

  // New chat
  dom.newChatBtn.addEventListener('click', startNewChat);

  // Send button
  dom.sendBtn.addEventListener('click', sendMessage);

  // Textarea: counter, auto-resize, button toggle
  dom.queryInput.addEventListener('input', () => {
    updateCharCounter();
    autoResize();
    toggleSendButton();
  });

  // Enter to send (Shift+Enter inserts newline)
  dom.queryInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!dom.sendBtn.disabled) sendMessage();
    }
  });

  // Welcome chips fill the input
  dom.chips.forEach(chip => {
    chip.addEventListener('click', () => fillInput(chip.dataset.q));
  });

  // Clear category filter
  dom.clearCategoryBtn.addEventListener('click', clearCategory);

  // Mobile hamburger toggle
  if (dom.hamburgerBtn) {
    dom.hamburgerBtn.addEventListener('click', toggleSidebar);
  }

  // Tap overlay to close sidebar on mobile
  if (dom.sidebarOverlay) {
    dom.sidebarOverlay.addEventListener('click', toggleSidebar);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   CATEGORY SELECTION
   ═══════════════════════════════════════════════════════════════════════════ */

/** Mark a category as active and update header + session storage */
function selectCategory(category) {
  state.selectedCategory = category;

  dom.catItems.forEach(btn => {
    const active = btn.dataset.category === category;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-pressed', active ? 'true' : 'false');
  });

  dom.chatCategoryLabel.textContent =
    `Filtering by: ${CATEGORY_LABELS[category] || category}`;
  dom.clearCategoryBtn.style.display = 'block';

  try { sessionStorage.setItem('uk-legal-category', category); } catch (_) {}
}

/** Remove the active category filter */
function clearCategory() {
  state.selectedCategory = null;
  dom.catItems.forEach(btn => {
    btn.classList.remove('active');
    btn.setAttribute('aria-pressed', 'false');
  });
  dom.chatCategoryLabel.textContent = 'Ask anything about UK law';
  dom.clearCategoryBtn.style.display = 'none';
  try { sessionStorage.removeItem('uk-legal-category'); } catch (_) {}
}

/* ═══════════════════════════════════════════════════════════════════════════
   NEW CHAT
   ═══════════════════════════════════════════════════════════════════════════ */

/** Archive the current conversation and reset to a blank chat */
function startNewChat() {
  // Save to sidebar history if conversation has messages
  if (state.messages.length > 0 && state.lastQuery) {
    saveToHistory(state.lastQuery, state.conversationId);
  }

  // Reset conversation state
  state.conversationId = null;
  state.messages       = [];
  state.lastQuery      = null;
  state.isLoading      = false;

  // Remove all message elements (keep welcome-state)
  Array.from(dom.messages.children).forEach(child => {
    if (!child.classList.contains('welcome-state')) child.remove();
  });

  // Remove any stray typing indicator
  hideTypingIndicator();

  // Re-show welcome state
  if (dom.welcomeState) dom.welcomeState.style.display = '';

  // Reset input
  dom.queryInput.value = '';
  updateCharCounter();
  autoResize();
  toggleSendButton();
  dom.queryInput.focus();

  // Close sidebar on mobile after starting new chat
  if (dom.sidebar && dom.sidebar.classList.contains('sidebar-open')) {
    toggleSidebar();
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   SEND MESSAGE
   ═══════════════════════════════════════════════════════════════════════════ */

/** Read input, call API, and render results */
async function sendMessage() {
  const query = dom.queryInput.value.trim();
  if (!query || state.isLoading) return;

  state.isLoading = true;
  state.lastQuery = query;

  // Clear + lock input
  dom.queryInput.value = '';
  updateCharCounter();
  autoResize();
  dom.sendBtn.disabled = true;

  // Dismiss welcome screen
  hideWelcomeState();

  // Render user bubble immediately
  addUserBubble(query);

  // Show animated typing dots
  showTypingIndicator();
  scrollToBottom();

  try {
    const payload = await callAPI(query);
    hideTypingIndicator();
    addAssistantBubble(payload);
  } catch (err) {
    hideTypingIndicator();
    showErrorBubble(err.message, query);
  } finally {
    state.isLoading = false;
    toggleSendButton();
    scrollToBottom();
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   API CALL
   ═══════════════════════════════════════════════════════════════════════════ */

/**
 * POST /law/query to the backend.
 * Includes category and conversation_id when available.
 * Times out after 30 seconds.
 */
async function callAPI(query) {
  const body = {
    query,
    limit: 5,
    ...(state.selectedCategory && { category:        state.selectedCategory }),
    ...(state.conversationId   && { conversation_id: state.conversationId }),
  };

  const controller = new AbortController();
  const timeoutId  = setTimeout(() => controller.abort(), 30_000);

  let res;
  try {
    res = await fetch(`${API_BASE}/law/query`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
      signal:  controller.signal,
    });
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('Request timed out after 30 seconds.');
    }
    throw new Error('Network error. Please check your connection and that the API server is running.');
  } finally {
    clearTimeout(timeoutId);
  }

  if (!res.ok) {
    let detail = `Server error (${res.status})`;
    try {
      const errBody = await res.json();
      detail = errBody.detail || errBody.error?.message || detail;
    } catch (_) {}
    throw new Error(detail);
  }

  const payload = await res.json();

  // Persist conversation_id for multi-turn dialogue
  if (payload.metadata?.conversation_id) {
    state.conversationId = payload.metadata.conversation_id;
  }

  return payload;
}

/* ═══════════════════════════════════════════════════════════════════════════
   MESSAGE RENDERING
   ═══════════════════════════════════════════════════════════════════════════ */

/** Create and append a right-aligned user message bubble */
function addUserBubble(text) {
  state.messages.push({ role: 'user', text });

  const wrapper = document.createElement('div');
  wrapper.className = 'msg-user-wrapper';
  wrapper.innerHTML = `
    <div class="msg-user">${escapeHtml(text)}</div>
    <div class="msg-time">${formatTimestamp()}</div>
  `;

  dom.messages.appendChild(wrapper);
}

/**
 * Create and append a full assistant bubble with:
 *   confidence badge, formatted answer, sources accordion, disclaimer
 */
function addAssistantBubble(payload) {
  const { data, metadata } = payload;
  state.messages.push({ role: 'assistant', data });

  const categoryBadge = data.legal_category
    ? `<span class="msg-category">${escapeHtml(data.legal_category)}</span>`
    : '';

  const latencyText = (metadata && typeof metadata.latency_ms === 'number')
    ? `<span class="msg-latency">· ${(metadata.latency_ms / 1000).toFixed(1)}s</span>`
    : '';

  const seekAdvice = data.seek_advice
    ? `<div class="disclaimer-block">
         <span class="disclaimer-icon" aria-hidden="true">⚠</span>
         ${escapeHtml(data.seek_advice)}
       </div>`
    : '';

  const wrapper = document.createElement('div');
  wrapper.className = 'msg-ai-wrapper';

  wrapper.innerHTML = `
    ${avatarSvg()}
    <div class="msg-ai-content">
      <div class="msg-ai-header">
        ${confidenceBadge(data.confidence)}
        <div class="msg-ai-meta">${categoryBadge}${latencyText}</div>
      </div>
      <div class="msg-ai">${formatAnswer(data.answer)}</div>
      ${buildSourcesHtml(data.sources)}
      ${seekAdvice}
      <div class="msg-time">${formatTimestamp()}</div>
    </div>
  `;

  // Wire up sources toggle after injection
  const toggleBtn = wrapper.querySelector('.sources-toggle');
  const sourcesEl = wrapper.querySelector('.sources-list');
  if (toggleBtn && sourcesEl) {
    toggleBtn.addEventListener('click', () =>
      toggleSources(toggleBtn, sourcesEl, data.sources.length)
    );
  }

  dom.messages.appendChild(wrapper);
}

/** Render the collapsible sources accordion HTML string */
function buildSourcesHtml(sources) {
  if (!sources || sources.length === 0) return '';

  const items = sources.map(src => {
    const domain  = safeDomain(src.url);
    const docName = escapeHtml(src.document || 'Legal document');
    const url     = escapeHtml(src.url);
    const relPct  = typeof src.relevance_score === 'number'
      ? Math.round(src.relevance_score * 100)
      : null;
    const relCls  = src.relevance_score >= 0.8 ? 'rel-high'
                  : src.relevance_score >= 0.5 ? 'rel-mid' : 'rel-low';
    const relBadge = relPct !== null
      ? `<span class="rel-badge ${relCls}">${relPct}%</span>`
      : '';

    return `
      <div class="source-card">
        <div class="source-card-top">
          <span class="source-doc">${docName}</span>
          ${relBadge}
        </div>
        <div class="source-card-bottom">
          <span class="source-domain">${escapeHtml(domain)}</span>
          <a href="${url}" target="_blank" rel="noopener noreferrer"
             class="source-link">View source →</a>
        </div>
      </div>`;
  }).join('');

  return `
    <div class="sources-section">
      <button class="sources-toggle" type="button" aria-expanded="false">
        <svg class="sources-chevron" viewBox="0 0 24 24" width="12" height="12"
             fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" aria-hidden="true">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
        <span class="sources-label">📄 View sources (${sources.length})</span>
      </button>
      <div class="sources-list" hidden>${items}</div>
    </div>`;
}

/* ── Confidence badge ─────────────────────────────────────────────────────── */

/** Return a small coloured dot + label badge for the given confidence level */
function confidenceBadge(level) {
  const map = {
    high:   { colour: '#27ae60', label: 'High confidence' },
    medium: { colour: '#e67e22', label: 'Review recommended' },
    low:    { colour: '#c0392b', label: 'Verify with official source' },
  };
  const { colour, label } = map[level] || map.low;
  return `
    <div class="conf-badge">
      <span class="conf-dot" style="background:${colour}" aria-hidden="true"></span>
      ${label}
    </div>`;
}

/* ── Scales of justice avatar SVG ─────────────────────────────────────────── */

/** Returns the avatar HTML (navy circle + gold scales SVG) */
function avatarSvg() {
  return `
    <div class="msg-avatar" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none"
           stroke="currentColor" stroke-width="1.5"
           stroke-linecap="round" stroke-linejoin="round">
        <line x1="12" y1="2"  x2="12" y2="20"/>
        <line x1="2"  y1="6"  x2="22" y2="6"/>
        <path d="M3 6l2 6H1l2-6z M3 12c0 1.4 1 2.5 2 2.5s2-1.1 2-2.5H3z"/>
        <path d="M19 6l2 6h-4l2-6z M17 12c0 1.4 1 2.5 2 2.5s2-1.1 2-2.5h-4z"/>
        <line x1="8" y1="20" x2="16" y2="20"/>
      </svg>
    </div>`;
}

/* ═══════════════════════════════════════════════════════════════════════════
   TYPING INDICATOR
   ═══════════════════════════════════════════════════════════════════════════ */

/** Append three animated dots to indicate the assistant is thinking */
function showTypingIndicator() {
  if (typingEl) return;
  typingEl = document.createElement('div');
  typingEl.className = 'msg-ai-wrapper';
  typingEl.setAttribute('aria-label', 'Assistant is thinking');
  typingEl.innerHTML = `
    ${avatarSvg()}
    <div class="msg-ai typing-bubble">
      <span class="dot"></span>
      <span class="dot"></span>
      <span class="dot"></span>
    </div>
  `;
  dom.messages.appendChild(typingEl);
}

/** Remove the typing indicator from the DOM */
function hideTypingIndicator() {
  if (typingEl) {
    typingEl.remove();
    typingEl = null;
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   ERROR BUBBLE
   ═══════════════════════════════════════════════════════════════════════════ */

/**
 * Show a red-bordered error message with a retry button.
 * Retry restores the original query to the input field.
 */
function showErrorBubble(message, originalQuery) {
  const wrapper = document.createElement('div');
  wrapper.className = 'msg-ai-wrapper';
  wrapper.innerHTML = `
    ${avatarSvg()}
    <div class="msg-ai error-bubble">
      <p><strong>⚠️ Unable to connect.</strong> ${escapeHtml(message)}</p>
      <button class="retry-btn" type="button">↺ Try again</button>
    </div>
  `;

  wrapper.querySelector('.retry-btn').addEventListener('click', () => {
    wrapper.remove();
    fillInput(originalQuery);
  });

  dom.messages.appendChild(wrapper);
}

/* ═══════════════════════════════════════════════════════════════════════════
   SOURCES TOGGLE
   ═══════════════════════════════════════════════════════════════════════════ */

/** Expand or collapse the sources list below an assistant bubble */
function toggleSources(button, sourcesEl, count) {
  const isHidden = sourcesEl.hidden;
  sourcesEl.hidden = !isHidden;
  button.setAttribute('aria-expanded', String(isHidden));

  const chevron = button.querySelector('.sources-chevron');
  if (chevron) chevron.style.transform = isHidden ? 'rotate(180deg)' : '';

  const label = button.querySelector('.sources-label');
  if (label) {
    label.textContent = `📄 ${isHidden ? 'Hide' : 'View'} sources (${count})`;
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   INPUT HELPERS
   ═══════════════════════════════════════════════════════════════════════════ */

/** Update the character counter and apply warning/danger classes */
function updateCharCounter() {
  const len = dom.queryInput.value.length;
  dom.charCounter.textContent = `${len} / 1000`;
  dom.charCounter.classList.toggle('warn', len >= 800 && len < 1000);
  dom.charCounter.classList.toggle('over', len >= 1000);
}

/** Expand the textarea height to fit content, capped at 120px */
function autoResize() {
  dom.queryInput.style.height = 'auto';
  dom.queryInput.style.height =
    Math.min(dom.queryInput.scrollHeight, 120) + 'px';
}

/** Enable send button only when input has ≥10 chars and not loading */
function toggleSendButton() {
  const len = dom.queryInput.value.trim().length;
  dom.sendBtn.disabled = len < 10 || state.isLoading;
}

/** Populate the textarea and activate the send button */
function fillInput(text) {
  dom.queryInput.value = text;
  updateCharCounter();
  autoResize();
  toggleSendButton();
  dom.queryInput.focus();
  dom.queryInput.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* ═══════════════════════════════════════════════════════════════════════════
   CHAT HISTORY (sidebar)
   ═══════════════════════════════════════════════════════════════════════════ */

/** Save a completed conversation to the sidebar history */
function saveToHistory(query, conversationId) {
  const item = {
    id:        conversationId || String(Date.now()),
    query,                                             // full text for refill
    label:     query.length > 55 ? query.slice(0, 55) + '…' : query,
    timestamp: new Date().toLocaleDateString('en-GB'),
  };
  state.chatHistory.unshift(item);
  if (state.chatHistory.length > 10) state.chatHistory.pop();

  try {
    sessionStorage.setItem('uk-legal-history', JSON.stringify(state.chatHistory));
  } catch (_) {}

  renderHistory();
}

/** Read persisted history and category from sessionStorage */
function loadFromSession() {
  try {
    const raw = sessionStorage.getItem('uk-legal-history');
    if (raw) {
      state.chatHistory = JSON.parse(raw);
      renderHistory();
    }
  } catch (_) {}

  // Restore category selection
  try {
    const cat = sessionStorage.getItem('uk-legal-category');
    if (cat) selectCategory(cat);
  } catch (_) {}
}

/** Render the sidebar history list */
function renderHistory() {
  if (!dom.historyList) return;

  if (state.chatHistory.length === 0) {
    dom.historyList.innerHTML =
      '<div class="history-empty">No previous chats yet</div>';
    return;
  }

  dom.historyList.innerHTML = '';
  state.chatHistory.forEach(item => {
    const el = document.createElement('div');
    el.className = 'history-item';
    el.title     = item.query;
    el.innerHTML = `
      <span class="history-query">${escapeHtml(item.label)}</span>
      <span class="history-date">${escapeHtml(item.timestamp)}</span>
    `;
    el.addEventListener('click', () => {
      startNewChat();
      fillInput(item.query); // restore full query to input
    });
    dom.historyList.appendChild(el);
  });
}

/* ═══════════════════════════════════════════════════════════════════════════
   TEXT FORMATTING
   ═══════════════════════════════════════════════════════════════════════════ */

/**
 * Convert plain LLM text to safe HTML:
 *   • Double newlines → paragraphs
 *   • **bold** → <strong>
 *   • [1][2] → styled citation badges
 *   • Bullet / numbered lists
 */
function formatAnswer(text) {
  if (!text) return '';

  return text.split(/\n{2,}/).map(block => {
    const lines = block.split('\n');

    // Bullet list
    if (lines.every(l => /^[-*•]\s/.test(l.trim()) || l.trim() === '')) {
      const items = lines
        .filter(l => l.trim())
        .map(l => `<li>${inlineFormat(l.replace(/^[-*•]\s+/, '').trim())}</li>`)
        .join('');
      return `<ul>${items}</ul>`;
    }

    // Numbered list
    if (lines.every(l => /^\d+[.)]\s/.test(l.trim()) || l.trim() === '')) {
      const items = lines
        .filter(l => l.trim())
        .map(l => `<li>${inlineFormat(l.replace(/^\d+[.)]\s+/, '').trim())}</li>`)
        .join('');
      return `<ol>${items}</ol>`;
    }

    // Normal paragraph
    return `<p>${lines.map(inlineFormat).join('<br>')}</p>`;
  }).join('');
}

/** Apply bold and citation styling within a single text line */
function inlineFormat(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[(\d+)\]/g,     '<span class="citation">$1</span>');
}

/* ═══════════════════════════════════════════════════════════════════════════
   UTILITIES
   ═══════════════════════════════════════════════════════════════════════════ */

/** Escape all HTML special characters to prevent XSS */
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Extract hostname from a URL, stripping www prefix */
function safeDomain(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); }
  catch (_) { return String(url); }
}

/** Return current time as HH:MM (24-hour, en-GB) */
function formatTimestamp() {
  return new Date().toLocaleTimeString('en-GB', {
    hour: '2-digit', minute: '2-digit',
  });
}

/** Smooth-scroll the messages container to show the latest message */
function scrollToBottom() {
  requestAnimationFrame(() => {
    dom.messages.scrollTop = dom.messages.scrollHeight;
  });
}

/** Hide the welcome state panel */
function hideWelcomeState() {
  if (dom.welcomeState && dom.welcomeState.style.display !== 'none') {
    dom.welcomeState.style.display = 'none';
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   MOBILE SIDEBAR
   ═══════════════════════════════════════════════════════════════════════════ */

/** Slide the sidebar in/out on mobile and toggle the overlay */
function toggleSidebar() {
  if (!dom.sidebar) return;
  const isOpen = dom.sidebar.classList.toggle('sidebar-open');
  if (dom.hamburgerBtn) {
    dom.hamburgerBtn.setAttribute('aria-expanded', String(isOpen));
  }
  if (dom.sidebarOverlay) {
    dom.sidebarOverlay.classList.toggle('active', isOpen);
  }
}
