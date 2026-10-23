/**
 * Abhyas Chat Application (spec/09 §9.2).
 * Features:
 * - IndexedDB Outbox with retry backoff (2, 4, 8s) and a visible failed state (tap to retry)
 * - Message deduplication with client_msg_id
 * - Polling (1.5s while pending, 20s while idle)
 * - Visible acknowledgment for every action: bubble states, typing indicator, audio states,
 *   mic flow, pressed/locked chips, cold-start / reconnecting status bar
 * - Lite mode toggle & audio playback
 *
 * All Hindi shown by the acknowledgment UI comes from content/messages_hi.yaml (ui_chat_*),
 * delivered as JSON in #ui-strings. The state machines below are pure so they can be tested
 * under Node (backend/tests/js).
 */

// ── IndexedDB Storage ───────────────────────────────────────────────────────
const DB_NAME = 'abhyas_chat_db';
const DB_VERSION = 1;
const STORE_OUTBOX = 'outbox';
const STORE_MESSAGES = 'messages_cache';

// ── Tunables (UI feedback timings) ──────────────────────────────────────────
const TYPING_TIMEOUT_MS = 60000; // give up the typing indicator, show the Hindi failure hint
const COLD_START_HINT_MS = 5000; // no response for this long -> "server is waking up"
const AUDIO_WAIT_MS = 25000; // how long a spoken reply may wait for its audio before text-only
const CHIP_CONFIRM_MS = 1400; // how long a tapped chip shows its inline ✓
const MAX_AUTO_RETRIES = 3; // network/5xx attempts before a bubble shows the red "!"
const BACKOFF_STEPS = [2000, 4000, 8000, 16000, 30000];

// ── CSRF Protection ────────────────────────────────────────────────────────
function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && meta.content) {
    return meta.content;
  }
  const match = document.cookie.match(/(?:^|;\s*)abhyas_csrf=([^;]+)/);
  if (match) {
    return decodeURIComponent(match[1]);
  }
  return '';
}
window.getCsrfToken = getCsrfToken;

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE_OUTBOX)) {
        db.createObjectStore(STORE_OUTBOX, { keyPath: 'client_msg_id' });
      }
      if (!db.objectStoreNames.contains(STORE_MESSAGES)) {
        db.createObjectStore(STORE_MESSAGES, { keyPath: 'id' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function saveToOutbox(item) {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([STORE_OUTBOX], 'readwrite');
    tx.objectStore(STORE_OUTBOX).put(item);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function removeFromOutbox(clientMsgId) {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([STORE_OUTBOX], 'readwrite');
    tx.objectStore(STORE_OUTBOX).delete(clientMsgId);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function getPendingOutboxItems() {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([STORE_OUTBOX], 'readonly');
    const req = tx.objectStore(STORE_OUTBOX).getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

async function cacheMessages(msgs) {
  if (!msgs || msgs.length === 0) return;
  const db = await openDatabase();
  const tx = db.transaction([STORE_MESSAGES], 'readwrite');
  const store = tx.objectStore(STORE_MESSAGES);
  for (const m of msgs) {
    store.put(m);
  }
}

async function getCachedMessages() {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([STORE_MESSAGES], 'readonly');
    const req = tx.objectStore(STORE_MESSAGES).getAll();
    req.onsuccess = () => {
      const res = req.result || [];
      res.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
      resolve(res.slice(-50));
    };
    req.onerror = () => reject(req.error);
  });
}

// ── Logout: wipe this browser's chat state so the next login never sees stale bubbles ──────
const LOGOUT_CLEAR_TIMEOUT_MS = 1500; // never let a stuck IndexedDB delete block the logout

function deleteChatDatabase() {
  return new Promise((resolve) => {
    try {
      const req = indexedDB.deleteDatabase(DB_NAME); // outbox + rendered-message cache
      req.onsuccess = () => resolve();
      req.onerror = () => resolve();
      req.onblocked = () => resolve();
    } catch (e) {
      resolve();
    }
  });
}

async function clearLocalState() {
  const wipes = [deleteChatDatabase()];
  if (window.caches) {
    wipes.push(caches.delete('abhyas-audio-v1').catch(() => false)); // played voice replies
  }
  await Promise.race([
    Promise.all(wipes),
    new Promise((resolve) => setTimeout(resolve, LOGOUT_CLEAR_TIMEOUT_MS)),
  ]);
}
window.clearLocalState = clearLocalState;

function setupLogoutCleanup() {
  document.addEventListener('click', (e) => {
    const link = e.target && e.target.closest ? e.target.closest('a[href="/logout"]') : null;
    if (!link) return;
    e.preventDefault();
    clearLocalState().finally(() => {
      window.location.href = '/logout';
    });
  });
}

// ── Localised strings (catalog keys ui_chat_*, served as JSON in the page) ───
let UI = {};

function setUiStrings(obj) {
  UI = obj || {};
}

function loadUiStrings() {
  const el = document.getElementById('ui-strings');
  if (!el) return;
  try {
    setUiStrings(JSON.parse(el.textContent));
  } catch (e) {
    console.warn('ui-strings JSON unreadable', e);
  }
}

function fillTemplate(str, vars) {
  let out = str;
  for (const k in vars || {}) out = out.split('{' + k + '}').join(String(vars[k]));
  return out;
}

// Returns '' (never an English fallback) for an unknown key; a pytest keeps keys and catalog in sync.
function t(key, vars) {
  const s = UI[key];
  return s === undefined ? '' : fillTemplate(s, vars);
}

// ── Pure state machines ─────────────────────────────────────────────────────
// Message bubble: sending -> sent | failed; failed -> (tap) sending. `sent` is final.
const MSG_SENDING = 'sending';
const MSG_SENT = 'sent';
const MSG_FAILED = 'failed';

function nextMsgState(cur, ev) {
  switch (ev) {
    case 'accepted':
      return MSG_SENT;
    case 'failed':
      return cur === MSG_SENT ? MSG_SENT : MSG_FAILED;
    case 'retry':
      return cur === MSG_FAILED ? MSG_SENDING : cur;
    default:
      return cur;
  }
}

// Typing indicator. `replied` stops the indicator coming back for the audio-rendering tail
// of a turn whose text already arrived (server `pending` stays true until TTS is done).
const TYPING_OFF = Object.freeze({ visible: false, timedOut: false, replied: false, speaker: null, label: null, since: 0 });

function typingNext(st, ev) {
  switch (ev.type) {
    case 'accepted': // a POST was accepted, or the teacher just tapped send (`label` = what we are doing)
      return {
        visible: true,
        timedOut: false,
        replied: false,
        speaker: ev.speaker || null,
        label: ev.label || (st.visible ? st.label : null),
        since: ev.now,
      };
    case 'pending': // poll says the server is still working
      if (st.visible || st.replied) return st;
      return { visible: true, timedOut: false, replied: false, speaker: st.speaker, label: null, since: ev.now };
    case 'reply': // a new bot bubble rendered
      return st.visible || !st.replied ? { ...TYPING_OFF, replied: true } : st;
    case 'idle': // poll says nothing is pending
      return st.visible || st.replied ? TYPING_OFF : st;
    case 'tick':
      if (st.visible && !st.timedOut && ev.now - st.since >= TYPING_TIMEOUT_MS) {
        return { ...st, timedOut: true };
      }
      return st;
    default:
      return st;
  }
}

const SPEAKER_NAMES = {
  ravi: ['रवि', 'ravi'],
  priya: ['प्रिया', 'priya'],
  aman: ['अमन', 'aman'],
};

// Which child the teacher is talking to (earliest name in the text), or null.
function guessSpeaker(text) {
  const s = (text || '').toLowerCase();
  let best = null;
  let bestAt = Infinity;
  for (const id in SPEAKER_NAMES) {
    for (const name of SPEAKER_NAMES[id]) {
      const at = s.indexOf(name);
      if (at !== -1 && at < bestAt) {
        best = id;
        bestAt = at;
      }
    }
  }
  return best;
}

// Audio bubble. `loading` = waiting for the audio file to exist, or buffering after a tap.
function audioNext(cur, ev) {
  switch (cur) {
    case 'loading':
      if (ev === 'ready') return 'ready';
      if (ev === 'giveup') return 'none';
      if (ev === 'playing') return 'playing';
      if (ev === 'pause') return 'ready';
      if (ev === 'error') return 'error';
      return cur;
    case 'ready':
      if (ev === 'play') return 'loading';
      if (ev === 'playing') return 'playing';
      if (ev === 'error') return 'error';
      return cur;
    case 'playing':
      if (ev === 'pause' || ev === 'ended') return 'ready';
      if (ev === 'waiting') return 'loading';
      if (ev === 'error') return 'error';
      return cur;
    case 'error':
      return ev === 'retry' ? 'loading' : cur;
    default:
      return cur;
  }
}

// Mic / voice note: idle -> recording -> uploading -> transcribing -> done
function micNext(cur, ev) {
  switch (cur) {
    case 'idle':
      return ev === 'start' ? 'recording' : cur;
    case 'recording':
      if (ev === 'stop') return 'uploading';
      if (ev === 'cancel' || ev === 'denied') return 'idle';
      return cur;
    case 'uploading':
      if (ev === 'accepted') return 'transcribing';
      if (ev === 'failed') return 'failed';
      return cur;
    case 'transcribing':
      if (ev === 'transcript') return 'done';
      if (ev === 'failed') return 'failed';
      return cur;
    case 'failed':
      return ev === 'retry' ? 'uploading' : cur;
    default:
      return cur;
  }
}

// Connection status bar: ok | cold (server waking / unreachable) | offline | reconnecting
function netNext(cur, ev) {
  switch (ev) {
    case 'success':
      return 'ok';
    case 'slow':
      return cur === 'ok' ? 'cold' : cur;
    case 'fail':
      return cur === 'ok' ? 'cold' : cur;
    case 'offline':
      return 'offline';
    case 'online':
      return cur === 'offline' ? 'reconnecting' : cur;
    default:
      return cur;
  }
}

function formatTimer(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

// Recorder limits come from the server (REC_* in config.py) through #rec-config.
const REC_CONFIG = (() => {
  try {
    const el = document.getElementById('rec-config');
    return el ? JSON.parse(el.textContent) : {};
  } catch (err) {
    return {};
  }
})();
const REC_HOLD_MS = REC_CONFIG.holdMs || 400; // press longer than this = hold-to-talk

// ── State Management ────────────────────────────────────────────────────────
const state = {
  lastMessageId: null,
  isPending: false,
  pollTimer: null,
  liteMode: false,
  isRecording: false,
  mic: 'idle',
  recorder: new window.AudioRecorder(REC_CONFIG),
  outboxRunning: false,
  drainAgain: false,
  renderedMsgIds: new Set(),
  playedAudioRefs: new Set(),
  autoPlayDone: false,
  lastAudioPollAt: null,
  lastMessageCreated: null,
  msgStates: new Map(), // client_msg_id -> sending | sent | failed
  hintDone: null, // key of the what-to-do line she has already acted on
  failedIds: new Map(), // client_msg_id -> 'network' | 'rejected'
  rows: new Map(), // client_msg_id | server id -> bubble row element
  typing: TYPING_OFF,
  typingTimer: null,
  net: 'ok',
  serverSkewMs: 0, // server clock minus client clock, from poll responses
  lastAcceptedAt: 0, // when a POST was last accepted (guards against stale poll replies)
};

function isChildSpeaker(speaker) {
  return speaker === 'ravi' || speaker === 'priya' || speaker === 'aman';
}

function rmAttr(el, name) {
  if (el.removeAttribute) el.removeAttribute(name);
}

function announce(text) {
  const live = document.getElementById('sr-live');
  if (live && text) live.textContent = text;
}

// ── Connection status (cold start / reconnecting) ───────────────────────────
function renderNetStatus() {
  const bar = document.getElementById('status-bar');
  if (!bar) return;
  const key = state.net === 'cold' ? 'ui_chat_cold_start' : state.net === 'reconnecting' ? 'ui_chat_reconnecting' : '';
  if (key) {
    bar.textContent = t(key);
    bar.className = `status-bar ${state.net}`;
    bar.hidden = false;
  } else {
    bar.textContent = '';
    bar.className = 'status-bar';
    bar.hidden = true;
  }
}

function netEvent(ev) {
  const next = netNext(state.net, ev);
  if (next === state.net) return;
  state.net = next;
  renderNetStatus();
}

// fetch() that reports to the status bar: no answer for COLD_START_HINT_MS shows the
// "server is waking up" hint; any successful response (or a 5xx while waking) updates it.
async function netFetch(url, opts) {
  const timer = setTimeout(() => netEvent('slow'), COLD_START_HINT_MS);
  try {
    const res = await fetch(url, opts);
    clearTimeout(timer);
    netEvent(res.status >= 500 ? 'fail' : 'success');
    return res;
  } catch (err) {
    clearTimeout(timer);
    netEvent(navigator.onLine ? 'fail' : 'offline');
    throw err;
  }
}

// ── Message bubble state ────────────────────────────────────────────────────
function paintStatus(el, st, clientMsgId) {
  el.className = `status-icon ${st}`;
  el.setAttribute('data-state', st);
  el.setAttribute('data-client-id', clientMsgId);
  el.textContent = st === MSG_SENT ? '✓' : st === MSG_FAILED ? '!' : '';
  el.setAttribute('aria-label', t(`ui_chat_msg_${st}`));
  if (st === MSG_FAILED) {
    el.setAttribute('role', 'button');
    el.setAttribute('tabindex', '0');
  } else {
    el.setAttribute('role', 'img');
    rmAttr(el, 'tabindex');
  }
}

function setMessageState(clientMsgId, ev) {
  const cur = state.msgStates.get(clientMsgId) || MSG_SENDING;
  const next = nextMsgState(cur, ev);
  state.msgStates.set(clientMsgId, next);
  const el = document.getElementById(`status-${clientMsgId}`);
  if (el) paintStatus(el, next, clientMsgId);
  return next;
}

// Kept for the render path: a polled/adopted copy of an optimistic bubble means "accepted".
function updateMessageStatus(clientMsgId) {
  setMessageState(clientMsgId, 'accepted');
}

function failMessage(clientMsgId, reason) {
  state.failedIds.set(clientMsgId, reason);
  setMessageState(clientMsgId, 'failed');
  typingEvent({ type: 'idle' }); // nothing is coming for a message that never arrived
  setMicPhase(clientMsgId, 'failed');
  flashStatus(failureNoticeText(reason));
}

// What the teacher is told when a send gives up: network (kept on the phone, tap ! later) vs
// rejected by the server (refresh or type instead).
function failureNoticeText(reason) {
  return reason === 'network' ? t('ui_chat_send_failed_network') : t('ui_chat_send_failed_rejected');
}

async function retryMessage(clientMsgId) {
  if (!state.failedIds.has(clientMsgId)) return;
  state.failedIds.delete(clientMsgId);
  setMessageState(clientMsgId, 'retry');
  setMicPhase(clientMsgId, 'retry');
  const items = await getPendingOutboxItems();
  const item = items.find((i) => i.client_msg_id === clientMsgId);
  if (!item) {
    failMessage(clientMsgId, 'rejected');
    return;
  }
  item.retryCount = 0;
  item.nextAttemptAt = 0;
  await saveToOutbox(item); // same client_msg_id: the server dedupes if the first try did land
  drainOutbox();
}

// ── Voice note phases (uploading -> transcribing -> transcript) ─────────────
function setMicPhase(clientMsgId, ev) {
  const row = state.rows.get(clientMsgId);
  if (!row || !row._phaseEl) return;
  const next = micNext(row._micPhase, ev);
  if (next === row._micPhase) return;
  row._micPhase = next;
  row.setAttribute('data-phase', next);
  const key = next === 'uploading' ? 'ui_chat_rec_uploading' : next === 'transcribing' ? 'ui_chat_rec_transcribing' : '';
  row._phaseEl.textContent = key ? t(key) : '';
}

function applyTranscript(row, text) {
  if (!row || !row._phaseEl || row._micPhase === 'done' || !text) return;
  row._micPhase = 'done';
  row.setAttribute('data-phase', 'done');
  row._phaseEl.textContent = '';
  if (row._textEl) row._textEl.textContent = text;
}

// ── Typing indicator ────────────────────────────────────────────────────────
function typingLabel(speaker) {
  return t(`ui_chat_typing_${speaker}`) || t('ui_chat_typing_generic');
}

function renderTyping() {
  const bubble = document.getElementById('pending-bubble');
  const label = document.getElementById('pending-text');
  const st = state.typing;
  if (bubble) {
    bubble.className = `pending-bubble${st.visible ? ' active' : ''}${st.timedOut ? ' timeout' : ''}`;
    bubble.setAttribute('aria-busy', st.visible && !st.timedOut ? 'true' : 'false');
  }
  if (label) label.textContent = st.timedOut ? t('ui_chat_typing_timeout') : st.label || typingLabel(st.speaker);
  if (st.visible) scrollChatToEnd();
  if (st.visible && !st.timedOut && !state.typingTimer) {
    state.typingTimer = setInterval(() => typingEvent({ type: 'tick' }), 1000);
  } else if ((!st.visible || st.timedOut) && state.typingTimer) {
    clearInterval(state.typingTimer);
    state.typingTimer = null;
  }
}

function typingEvent(ev) {
  const next = typingNext(state.typing, { ...ev, now: Date.now() });
  if (next === state.typing) return;
  state.typing = next;
  renderTyping();
}

// ── Outbox Drainer & Backoff Retrier ────────────────────────────────────────
function audioFileName(blob) {
  const type = (blob && blob.type) || '';
  if (type.includes('mp4')) return 'voice.m4a';
  if (type.includes('webm')) return 'voice.webm';
  return 'voice.audio';
}

async function sendOutboxItem(item) {
  const csrfToken = getCsrfToken();
  const jsonHeaders = { 'Content-Type': 'application/json' };
  if (csrfToken) {
    jsonHeaders['x-csrf-token'] = csrfToken;
  }

  let resp = null;
  if (item.kind === 'text') {
    resp = await netFetch('/api/chat/text', {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify({ client_msg_id: item.client_msg_id, text: item.text }),
    });
  } else if (item.kind === 'button') {
    resp = await netFetch('/api/chat/button', {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify({ client_msg_id: item.client_msg_id, button_id: item.button_id }),
    });
  } else if (item.kind === 'audio' && item.audioBlob) {
    const form = new FormData();
    form.append('client_msg_id', item.client_msg_id);
    form.append('file', item.audioBlob, audioFileName(item.audioBlob));
    const audioHeaders = {};
    if (csrfToken) {
      audioHeaders['x-csrf-token'] = csrfToken;
    }
    resp = await netFetch('/api/chat/audio', { method: 'POST', headers: audioHeaders, body: form });
  }

  if (!resp) return { outcome: 'rejected' };
  if (resp.status >= 200 && resp.status < 300) {
    const body = await resp.json().catch(() => null);
    return { outcome: 'accepted', body };
  }
  // 4xx (other than timeout / rate-limit) will not succeed by retrying the same request
  if (resp.status >= 400 && resp.status < 500 && resp.status !== 408 && resp.status !== 429) {
    return { outcome: 'rejected' };
  }
  return { outcome: 'retry' };
}

async function drainOnce() {
  let wakeAt = 0;
  const items = await getPendingOutboxItems();
  items.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
  for (const item of items) {
    const id = item.client_msg_id;
    if (!navigator.onLine) break;
    if (state.failedIds.has(id)) continue;
    if (item.nextAttemptAt && item.nextAttemptAt > Date.now()) {
      wakeAt = wakeAt ? Math.min(wakeAt, item.nextAttemptAt) : item.nextAttemptAt;
      continue;
    }

    const startTime = Date.now();
    let result;
    try {
      result = await sendOutboxItem(item);
    } catch (err) {
      console.warn('Upload error for item', id, err);
      result = { outcome: 'retry' };
    }
    if (Date.now() - startTime > 8000) {
      showSlowNetworkWarning();
    }

    if (result.outcome === 'accepted') {
      if (result.body && result.body.message_id) {
        adoptServerMessageId(id, result.body.message_id);
      }
      await removeFromOutbox(id);
      setMessageState(id, 'accepted');
      setMicPhase(id, 'accepted');
      typingEvent({ type: 'accepted', speaker: item.kind === 'text' ? guessSpeaker(item.text) : null });
      // The server now owes a reply: poll at the fast cadence until it says it is done
      state.lastAcceptedAt = Date.now();
      state.isPending = true;
      scheduleNextPoll();
    } else if (result.outcome === 'rejected') {
      failMessage(id, 'rejected');
    } else {
      item.retryCount = (item.retryCount || 0) + 1;
      if (item.retryCount >= MAX_AUTO_RETRIES) {
        await saveToOutbox(item);
        failMessage(id, 'network');
      } else {
        item.nextAttemptAt = Date.now() + BACKOFF_STEPS[Math.min(item.retryCount - 1, BACKOFF_STEPS.length - 1)];
        await saveToOutbox(item);
        wakeAt = wakeAt ? Math.min(wakeAt, item.nextAttemptAt) : item.nextAttemptAt;
      }
    }
  }
  return wakeAt;
}

async function drainOutbox() {
  if (state.outboxRunning) {
    state.drainAgain = true; // an item was queued mid-run: go round again
    return;
  }
  if (!navigator.onLine) return;
  state.outboxRunning = true;
  let wakeAt = 0;
  try {
    do {
      state.drainAgain = false;
      wakeAt = await drainOnce();
    } while (state.drainAgain && navigator.onLine);
  } finally {
    state.outboxRunning = false;
  }
  if (wakeAt) setTimeout(drainOutbox, Math.max(0, wakeAt - Date.now()) + 50);
}

// ── Scrolling: the thread is the one scrolling part of the page ──────────────
function scrollChatToEnd() {
  const container = document.getElementById('chat-messages');
  if (container) container.scrollTop = container.scrollHeight;
}

// After new bubbles: show their end, unless that would push the first one's top out of sight
// (a long answer is read from its first line).
function scrollChatToNew(firstRow) {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  container.scrollTop = container.scrollHeight;
  if (!firstRow || typeof firstRow.getBoundingClientRect !== 'function') return;
  const offset = firstRow.getBoundingClientRect().top - container.getBoundingClientRect().top;
  if (offset < 0) container.scrollTop += offset - 8;
}

// ── Polling Loop (§7.3) ─────────────────────────────────────────────────────
// Scene bar: every field comes from the server (title, turn, board, who can be addressed)
function addressChild(name) {
  const input = document.getElementById('chat-input');
  if (!input || !name) return;
  if (!input.value.startsWith(name)) input.value = `${name}, ${input.value}`;
  if (input.focus) input.focus();
}

function renderSceneHeader(sc) {
  const bar = document.getElementById('scene-bar');
  if (!bar) return;
  bar.hidden = !sc;
  if (!sc) return;
  const set = (id, text) => {
    const el = document.getElementById(id);
    if (el && el.textContent !== text) el.textContent = text;
  };
  set('sb-title', sc.title);
  set('sb-turn', sc.turn_label);
  set('sb-board', sc.board);
  const kids = document.getElementById('sb-children');
  if (!kids) return;
  const list = sc.children || [];
  const ids = list.map((c) => c.id).join(',');
  if (kids.dataset.ids !== ids) {
    kids.dataset.ids = ids;
    while (kids.children.length) kids.removeChild(kids.children[0]);
    list.forEach((c) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = `child-pill ${c.id}`;
      b.setAttribute('data-name', c.name);
      b.textContent = c.name;
      kids.appendChild(b);
    });
  }
  kids.hidden = list.length === 0;
}

// What to do now: hidden once she has sent something in this step (until the guidance changes)
function renderHint(h) {
  const card = document.getElementById('next-card');
  if (!card) return;
  if (!h || state.hintDone === h.key) {
    card.hidden = true;
    return;
  }
  card.hidden = false;
  card.setAttribute('data-key', h.key);
  const text = document.getElementById('next-text');
  if (text && text.textContent !== h.text) text.textContent = h.text;
  const suggest = document.getElementById('next-suggest');
  if (suggest) {
    suggest.hidden = !h.suggest;
    if (suggest.textContent !== (h.suggest || '')) suggest.textContent = h.suggest || '';
  }
}

function hintSent() {
  const card = document.getElementById('next-card');
  if (!card || card.hidden) return;
  state.hintDone = card.getAttribute('data-key');
  card.hidden = true;
}

// Header: the move title and "Step 4 of 7: Practice" follow the weekly loop
function applyView(view) {
  if (!view) return;
  renderHint(view.hint);
  renderSamples(view.samples);
  const title = document.getElementById('header-move-title');
  if (title && title.textContent !== view.move_title) title.textContent = view.move_title;
  const step = document.getElementById('header-step');
  if (step && step.textContent !== view.step_label) step.textContent = view.step_label;
}

function setupSceneEnd() {
  const btn = document.getElementById('sh-end');
  if (!btn) return;
  btn.addEventListener('click', () => {
    if (!window.confirm(t('ui_chat_scene_end_confirm'))) return;
    handleSendText(t('ui_chat_scene_stop_word'));
  });
}

async function pollMessages() {
  if (!navigator.onLine) return;

  try {
    const startTime = Date.now();
    let url = '/api/chat/messages';
    const params = [];
    if (state.lastMessageId) {
      params.push(`after=${encodeURIComponent(state.lastMessageId)}`);
    }
    if (state.lastAudioPollAt) {
      params.push(`audio_since=${encodeURIComponent(state.lastAudioPollAt)}`);
    }
    if (params.length > 0) {
      url += `?${params.join('&')}`;
    }

    const res = await netFetch(url);
    const duration = Date.now() - startTime;
    if (duration > 8000) {
      showSlowNetworkWarning();
    }

    if (res.ok) {
      const data = await res.json();
      if (data.server_time) {
        state.lastAudioPollAt = data.server_time;
        const skew = Date.parse(data.server_time) - Date.now();
        if (!Number.isNaN(skew)) state.serverSkewMs = skew;
      }
      // A poll that left before the last POST was accepted cannot say whether that turn is done,
      // and neither can any poll while a message is still on its way
      const stale = startTime <= state.lastAcceptedAt || [...state.msgStates.values()].includes(MSG_SENDING);
      state.isPending = data.pending || stale;

      let gotReply = false;
      let firstNewReply = null;
      if (data.messages && data.messages.length > 0) {
        for (const msg of data.messages) {
          const isNew = renderMessage(msg);
          if (isNew && msg.direction === 'out') {
            gotReply = true;
            firstNewReply = firstNewReply || state.rows.get(msg.id) || null;
          }
          if (!state.lastMessageCreated || (msg.created_at && msg.created_at >= state.lastMessageCreated)) {
            state.lastMessageId = msg.id;
            state.lastMessageCreated = msg.created_at;
          }
        }
        await cacheMessages(data.messages);
      }
      if (gotReply) {
        typingEvent({ type: 'reply' });
        scrollChatToNew(firstNewReply);
      }
      if (!stale) typingEvent({ type: data.pending ? 'pending' : 'idle' });
      renderSceneHeader(data.scene || null);
      applyView(data.view);
    }
  } catch (err) {
    console.warn('Poll error:', err);
  } finally {
    scheduleNextPoll();
  }
}

function scheduleNextPoll() {
  if (state.pollTimer) clearTimeout(state.pollTimer);
  // 1.5s while pending, else 20s (§7.3)
  const delay = state.isPending ? 1500 : 20000;
  state.pollTimer = setTimeout(pollMessages, delay);
}

function triggerImmediatePoll() {
  if (state.pollTimer) clearTimeout(state.pollTimer);
  pollMessages();
}

// ── Audio bubble ────────────────────────────────────────────────────────────
function setAudioState(wrap, st) {
  if (st === 'none') {
    // audio never arrived: leave the text bubble on its own, no dead player
    if (wrap._giveupTimer) clearTimeout(wrap._giveupTimer);
    if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
    wrap._audioState = 'none';
    return;
  }
  wrap._audioState = st;
  wrap.setAttribute('data-audio-state', st);
  const hasRef = !!wrap._ref;
  wrap.setAttribute('data-has-audio', hasRef ? 'true' : 'false');
  wrap._btn.disabled = !hasRef;
  const labels = {
    loading: t('ui_chat_audio_loading'),
    ready: t('ui_chat_audio_ready'),
    playing: t('ui_chat_audio_playing'),
    error: t('ui_chat_audio_error'),
  };
  wrap._label.textContent = labels[st] || '';
  const btnLabel = {
    ready: t('ui_chat_audio_play'),
    playing: t('ui_chat_audio_pause'),
    loading: t('ui_chat_audio_pause'),
    error: t('ui_chat_audio_retry'),
  };
  wrap._btn.setAttribute('aria-label', btnLabel[st] || '');
}

function transitionAudio(wrap, ev) {
  const next = audioNext(wrap._audioState, ev);
  if (next !== wrap._audioState) setAudioState(wrap, next);
}

function getAudioEl(wrap) {
  if (wrap._audio) return wrap._audio;
  const a = new Audio();
  a.preload = state.liteMode ? 'none' : 'metadata';
  a.src = `/api/audio/${encodeURIComponent(wrap._ref)}.ogg`;
  a.addEventListener('playing', () => transitionAudio(wrap, 'playing'));
  a.addEventListener('waiting', () => transitionAudio(wrap, 'waiting'));
  a.addEventListener('pause', () => {
    if (!a.ended) transitionAudio(wrap, 'pause');
  });
  a.addEventListener('ended', () => transitionAudio(wrap, 'ended'));
  a.addEventListener('error', () => transitionAudio(wrap, 'error'));
  wrap._audio = a;
  return a;
}

function startAudio(wrap, silentFail) {
  const a = getAudioEl(wrap);
  const ev = wrap._audioState === 'error' ? 'retry' : 'play';
  if (ev === 'retry') a.load();
  transitionAudio(wrap, ev);
  a.play().catch(() => transitionAudio(wrap, silentFail ? 'pause' : 'error'));
}

function onAudioButton(wrap) {
  const st = wrap._audioState;
  if (st === 'playing' || st === 'loading') {
    if (wrap._audio) wrap._audio.pause();
    return;
  }
  if ((st === 'ready' || st === 'error') && wrap._ref) startAudio(wrap, false);
}

// One builder for every audio bubble: waiting (no file yet), ready, playing, error.
function buildAudioWrap(audioRef, initialState) {
  const wrap = document.createElement('div');
  wrap.className = 'bubble-audio';

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn-play';
  const bars = document.createElement('span');
  bars.className = 'bars';
  bars.setAttribute('aria-hidden', 'true');
  for (let i = 0; i < 3; i++) bars.appendChild(document.createElement('i'));
  btn.appendChild(bars);

  const label = document.createElement('span');
  label.className = 'audio-duration';

  wrap.appendChild(btn);
  wrap.appendChild(label);
  wrap._btn = btn;
  wrap._label = label;
  wrap._ref = audioRef || null;
  wrap._audio = null;
  btn.onclick = () => onAudioButton(wrap);
  setAudioState(wrap, initialState);
  return wrap;
}

// The file for a text-first reply has landed: turn the "आवाज़ आ रही है…" placeholder into a player.
function attachAudioRef(wrap, audioRef, autoplay) {
  if (wrap._giveupTimer) clearTimeout(wrap._giveupTimer);
  wrap._ref = audioRef;
  setAudioState(wrap, 'ready');
  if (autoplay && !state.liteMode && !state.autoPlayDone) {
    state.autoPlayDone = true;
    setTimeout(() => startAudio(wrap, true), 300);
  }
}

// Server-rendered history bubbles carry a bare ▶ button: swap in the stateful player.
function upgradeServerAudio() {
  document.querySelectorAll('.bubble-audio').forEach((el) => {
    const btn = el.querySelector('.btn-play[data-audio-ref]');
    if (!btn || !el.parentNode) return;
    el.parentNode.replaceChild(buildAudioWrap(btn.getAttribute('data-audio-ref'), 'ready'), el);
  });
}

// ── UI Rendering ────────────────────────────────────────────────────────────
// The optimistic bubble is keyed by client_msg_id; the server copy of the same
// message (POST response / poll) carries the server id. Re-key the bubble so the
// polled copy is recognised instead of being rendered as a second bubble.
function adoptServerMessageId(clientMsgId, serverId) {
  if (!clientMsgId || !serverId || clientMsgId === serverId) return;
  if (!state.renderedMsgIds.has(clientMsgId)) return;
  state.renderedMsgIds.add(serverId);
  const row = document.getElementById(`msg-${clientMsgId}`) || state.rows.get(clientMsgId);
  if (row) {
    row.id = `msg-${serverId}`;
    state.rows.set(serverId, row);
  }
}

// A spoken reply (child / model teacher) whose audio is being synthesised right now.
function expectsAudio(msg) {
  if (msg.direction !== 'out' || msg.audio_ref || state.liteMode) return false;
  if (!isChildSpeaker(msg.speaker) && msg.speaker !== 'model_teacher') return false;
  const created = Date.parse(msg.created_at);
  if (Number.isNaN(created)) return false;
  return Date.now() + state.serverSkewMs - created < AUDIO_WAIT_MS;
}

// Returns true when a new bubble was added (false for a re-sent copy of an existing one).
function renderMessage(msg, isLocalOptimistic = false) {
  if (msg.id && msg.client_msg_id && state.renderedMsgIds.has(msg.client_msg_id)) {
    adoptServerMessageId(msg.client_msg_id, msg.id);
    updateMessageStatus(msg.client_msg_id);
  }
  const msgKey = msg.id || msg.client_msg_id;
  if (state.renderedMsgIds.has(msgKey)) {
    const existing = state.rows.get(msgKey) || (msg.client_msg_id && state.rows.get(msg.client_msg_id));
    if (existing && msg.text) applyTranscript(existing, msg.text);
    // Text-first delivery support: attach audio to a previously rendered text bubble
    if (existing && msg.audio_ref && existing._audioWrap) {
      if (!existing._audioWrap._ref) {
        attachAudioRef(existing._audioWrap, msg.audio_ref, isChildSpeaker(msg.speaker) && existing._fresh);
      }
    } else if (existing && msg.audio_ref && !existing._audioWrap && existing._bubble) {
      const wrap = buildAudioWrap(msg.audio_ref, 'ready');
      existing._audioWrap = wrap;
      existing._bubble.insertBefore(wrap, existing._meta);
    }
    return false;
  }
  state.renderedMsgIds.add(msgKey);

  const container = document.getElementById('chat-messages');
  if (!container) return false;

  const row = document.createElement('div');
  row.className = `msg-row ${msg.direction === 'in' ? 'inbound' : 'outbound'}`;
  row.id = `msg-${msgKey}`;
  state.rows.set(msgKey, row);
  if (msg.client_msg_id) state.rows.set(msg.client_msg_id, row);

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  row._bubble = bubble;

  // Speaker Tag (bot messages)
  if (msg.direction === 'out' && msg.speaker) {
    const speakerEl = document.createElement('div');
    speakerEl.className = `speaker-tag ${msg.speaker.toLowerCase()}`;
    speakerEl.textContent = getSpeakerLabel(msg.speaker);
    bubble.appendChild(speakerEl);
  }

  // Text Content
  if (msg.text || msg.awaitingTranscript) {
    const textEl = document.createElement('p');
    textEl.className = 'bubble-text';
    textEl.textContent = msg.text || '';
    bubble.appendChild(textEl);
    row._textEl = textEl;
  }

  // Voice note being uploaded / transcribed: one-line Hindi status under the label
  if (msg.awaitingTranscript) {
    const phaseEl = document.createElement('p');
    phaseEl.className = 'bubble-phase';
    phaseEl.setAttribute('role', 'status');
    bubble.appendChild(phaseEl);
    row._phaseEl = phaseEl;
    row._micPhase = 'uploading';
    row.setAttribute('data-phase', 'uploading');
    phaseEl.textContent = t('ui_chat_rec_uploading');
  } else if (msg.direction === 'in' && msg.kind === 'audio' && !msg.text && !isLocalOptimistic) {
    // a voice note from history/poll whose transcript has not landed yet
    const phaseEl = document.createElement('p');
    phaseEl.className = 'bubble-phase';
    phaseEl.setAttribute('role', 'status');
    phaseEl.textContent = t('ui_chat_rec_transcribing');
    const textEl = document.createElement('p');
    textEl.className = 'bubble-text';
    bubble.appendChild(textEl);
    bubble.appendChild(phaseEl);
    row._textEl = textEl;
    row._phaseEl = phaseEl;
    row._micPhase = 'transcribing';
    row.setAttribute('data-phase', 'transcribing');
  }

  // Audio player, or a "voice is coming" placeholder while the reply's audio is synthesised
  if (msg.audio_ref || expectsAudio(msg)) {
    const wrap = buildAudioWrap(msg.audio_ref || null, msg.audio_ref ? 'ready' : 'loading');
    row._audioWrap = wrap;
    row._fresh = !msg.audio_ref;
    bubble.appendChild(wrap);
    if (!msg.audio_ref) {
      wrap._giveupTimer = setTimeout(() => transitionAudio(wrap, 'giveup'), AUDIO_WAIT_MS);
    } else if (!state.liteMode && !state.autoPlayDone && isChildSpeaker(msg.speaker)) {
      // Auto-play newest child line once in normal mode if not played
      state.autoPlayDone = true;
      setTimeout(() => startAudio(wrap, true), 300);
    }
  }

  if (msg.citations && msg.citations.length > 0) {
    const sources = document.createElement('div');
    sources.className = 'bubble-sources';
    msg.citations.forEach((c) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'source-chip';
      chip.dataset.chunkId = c.chunk_id;
      chip.setAttribute('aria-expanded', 'false');
      chip.textContent = c.line_hi;
      sources.appendChild(chip);
    });
    bubble.appendChild(sources);
  }

  // On-demand English translation under child / coach / guide bubbles
  if (msg.direction === 'out' && msg.id && msg.text && TRANSLATABLE_SPEAKERS.has(msg.speaker)) {
    bubble.appendChild(buildTranslateControl(msg.id));
  }

  // Metadata / Status Tick
  const meta = document.createElement('div');
  meta.className = 'bubble-meta';
  row._meta = meta;
  const timeEl = document.createElement('span');
  timeEl.textContent = msg.created_at
    ? new Date(msg.created_at).toLocaleTimeString('hi-IN', { hour: '2-digit', minute: '2-digit' })
    : t('ui_time_just_now');
  meta.appendChild(timeEl);
  const statusEl = document.createElement('span');
  const statusKey = msg.client_msg_id || msg.id;
  statusEl.id = `status-${statusKey}`;
  if (msg.direction === 'in') {
    const initial = isLocalOptimistic ? MSG_SENDING : MSG_SENT;
    state.msgStates.set(statusKey, initial);
    paintStatus(statusEl, initial, statusKey);
  } else {
    statusEl.className = 'status-icon';
  }
  meta.appendChild(statusEl);
  bubble.appendChild(meta);

  row.appendChild(bubble);

  // Quick-reply Buttons (chips under last bot message)
  if (msg.direction === 'out' && msg.buttons && msg.buttons.length > 0) {
    const qrContainer = document.createElement('div');
    qrContainer.className = 'quick-replies';
    msg.buttons.forEach((btn) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'reply-chip';
      chip.textContent = btn.title_hi;
      chip.onclick = () => {
        if (chip.disabled) return;
        lockChips(qrContainer, chip);
        handleSendButton(btn.id, btn.title_hi);
      };
      qrContainer.appendChild(chip);
    });
    row.appendChild(qrContainer);
  }

  const pendingEl = document.getElementById('pending-bubble');
  if (pendingEl && pendingEl.parentNode === container) {
    container.insertBefore(row, pendingEl); // new bubbles stay above the typing indicator
  } else {
    container.appendChild(row);
  }
  scrollChatToEnd();
  return true;
}

// ── On-demand translation: "Translate" under child / coach / guide bubbles ─────
// The Hindi stays; the English text appears below it. The server caches per (message, 'en').
const TRANSLATABLE_SPEAKERS = new Set(['ravi', 'priya', 'aman', 'coach', 'guide', 'model_teacher']);

function buildTranslateControl(messageId) {
  const wrap = document.createElement('div');
  wrap.className = 'translate-wrap';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'translate-btn';
  btn.dataset.messageId = messageId;
  btn.textContent = t('ui_chat_translate');
  wrap.appendChild(btn);
  return wrap;
}

async function toggleTranslation(btn) {
  const wrap = btn.closest('.translate-wrap');
  if (!wrap || btn.disabled) return;
  const shown = wrap.querySelector('.bubble-translation');
  const oldErr = wrap.querySelector('.translate-error');
  if (oldErr) oldErr.remove();
  if (shown) {
    shown.remove();
    btn.textContent = t('ui_chat_translate');
    return;
  }
  btn.disabled = true;
  btn.setAttribute('aria-busy', 'true');
  btn.textContent = t('ui_chat_translate_loading');
  try {
    const headers = { 'Content-Type': 'application/json' };
    const csrfToken = getCsrfToken();
    if (csrfToken) headers['x-csrf-token'] = csrfToken;
    const res = await netFetch('/api/chat/translate', {
      method: 'POST',
      headers,
      credentials: 'same-origin',
      body: JSON.stringify({ message_id: btn.dataset.messageId }),
    });
    if (!res.ok) {
      const err = new Error(`translate ${res.status}`);
      err.status = res.status;
      throw err;
    }
    const data = await res.json();
    const out = document.createElement('p');
    out.className = 'bubble-translation';
    out.lang = 'en';
    out.setAttribute('aria-label', t('ui_chat_translation_label'));
    out.textContent = data.text;
    wrap.appendChild(out);
    btn.textContent = t('ui_chat_translate_hide');
  } catch (e) {
    const msg = document.createElement('p');
    msg.className = 'translate-error';
    msg.setAttribute('role', 'alert');
    msg.textContent = e && e.status === 429 ? t('ui_chat_translate_limit') : t('ui_chat_translate_error');
    wrap.appendChild(msg);
    btn.textContent = t('ui_chat_translate_retry');
  } finally {
    btn.disabled = false;
    btn.removeAttribute('aria-busy');
  }
}

document.addEventListener('click', (ev) => {
  const btn = ev.target instanceof Element ? ev.target.closest('.translate-btn') : null;
  if (btn) toggleTranslation(btn);
});

// ── Source citations: tap the chip to read the excerpt behind an answer ───────
function buildExcerptPanel(src) {
  const panel = document.createElement('div');
  panel.className = 'source-excerpt';
  panel.setAttribute('role', 'region');
  const head = document.createElement('p');
  head.className = 'source-excerpt-head';
  const pageBits = [t('ui_chat_source_page', { page: src.page })];
  if (src.printed_page) pageBits.push(t('ui_chat_source_printed', { page: src.printed_page }));
  head.textContent = `${src.source_short_hi} · ${pageBits.join(' · ')}`;
  panel.appendChild(head);
  if (src.heading) {
    const h = document.createElement('p');
    h.className = 'source-excerpt-heading';
    h.textContent = src.heading;
    panel.appendChild(h);
  }
  if (src.gloss_hi) {
    const g = document.createElement('p');
    g.className = 'source-excerpt-gloss';
    g.textContent = `${t('ui_chat_source_summary')}: ${src.gloss_hi}`;
    panel.appendChild(g);
  }
  const body = document.createElement('p');
  body.className = 'source-excerpt-text';
  if (src.lang === 'en') body.lang = 'en';
  body.textContent = src.text;
  panel.appendChild(body);
  if (src.lang === 'en') {
    const note = document.createElement('p');
    note.className = 'source-excerpt-note';
    note.textContent = t('ui_chat_source_original_en');
    panel.appendChild(note);
  }
  if (src.ocr) {
    const ocrNote = document.createElement('p');
    ocrNote.className = 'source-excerpt-note';
    ocrNote.textContent = t('ui_chat_source_ocr');
    panel.appendChild(ocrNote);
  }
  return panel;
}

async function toggleSourceExcerpt(chip) {
  const holder = chip.closest('.bubble-sources');
  if (!holder) return;
  const open = holder.querySelector('.source-excerpt');
  const err = holder.querySelector('.source-error');
  if (err) err.remove();
  if (open && open.dataset.chunkId === chip.dataset.chunkId) {
    open.remove();
    chip.setAttribute('aria-expanded', 'false');
    return;
  }
  if (open) open.remove();
  holder.querySelectorAll('.source-chip').forEach((c) => c.setAttribute('aria-expanded', 'false'));
  chip.disabled = true;
  chip.setAttribute('aria-busy', 'true');
  try {
    const res = await netFetch(`/api/source/${encodeURIComponent(chip.dataset.chunkId)}`, {
      credentials: 'same-origin',
    });
    if (!res.ok) throw new Error(`source ${res.status}`);
    const panel = buildExcerptPanel(await res.json());
    panel.dataset.chunkId = chip.dataset.chunkId;
    holder.appendChild(panel);
    chip.setAttribute('aria-expanded', 'true');
  } catch (e) {
    const msg = document.createElement('p');
    msg.className = 'source-error';
    msg.setAttribute('role', 'alert');
    msg.textContent = t('ui_chat_source_error');
    holder.appendChild(msg);
  } finally {
    chip.disabled = false;
    chip.removeAttribute('aria-busy');
  }
}

document.addEventListener('click', (ev) => {
  const chip = ev.target instanceof Element ? ev.target.closest('.source-chip') : null;
  if (chip) toggleSourceExcerpt(chip);
});

// Speaker display names come from the catalog (speaker_<id>), in the user's UI language.
function getSpeakerLabel(speaker) {
  return t(`speaker_${speaker}`) || speaker;
}

function recorderErrorText(code, detail) {
  if (code === 'unsupported') return t('ui_chat_rec_unsupported');
  if (code === 'insecure') return t('ui_chat_rec_insecure');
  if (code === 'permission') return t('ui_chat_rec_permission');
  if (code === 'no_mic') return t('ui_chat_rec_no_mic');
  if (code === 'busy') return t('ui_chat_rec_busy');
  return t('ui_chat_rec_start_failed', { error: detail || t('ui_chat_rec_unknown_error') });
}

// ── Chips: pressed state, locked while the request runs, inline ✓ ────────────
function lockChips(container, chip) {
  container.querySelectorAll('.reply-chip').forEach((c) => {
    c.disabled = true;
    c.setAttribute('aria-busy', 'true');
  });
  chip.classList.add('pressed');
  announce(t('ui_chat_chip_done'));
}

// ── Sending Handlers ────────────────────────────────────────────────────────
// `typingLabel` (optional): what the typing bubble says at once, before the server has answered.
async function handleSendText(text, typingLabel = null) {
  if (!text || !text.trim()) return null;
  hintSent();
  const clientMsgId = crypto.randomUUID();
  const cleanText = text.trim();

  // 1. Clear the input first (synchronously): a second tap/Enter cannot resend the same text
  const input = document.getElementById('chat-input');
  if (input) input.value = '';

  // 2. Optimistic render in UI (clock until the POST is accepted)
  const optimisticMsg = {
    client_msg_id: clientMsgId,
    direction: 'in',
    kind: 'text',
    text: cleanText,
    created_at: new Date().toISOString(),
  };
  renderMessage(optimisticMsg, true);
  if (typingLabel) typingEvent({ type: 'accepted', label: typingLabel });

  // 3. Save to IndexedDB Outbox
  await saveToOutbox({
    client_msg_id: clientMsgId,
    kind: 'text',
    text: cleanText,
    timestamp: Date.now(),
    retryCount: 0,
  });

  // 4. Trigger Outbox upload & fast poll
  drainOutbox();
  triggerImmediatePoll();
  return clientMsgId;
}

async function handleSendButton(buttonId, buttonTitle) {
  hintSent();
  const clientMsgId = crypto.randomUUID();

  // Optimistic render
  const optimisticMsg = {
    client_msg_id: clientMsgId,
    direction: 'in',
    kind: 'button',
    text: buttonTitle,
    created_at: new Date().toISOString(),
  };
  renderMessage(optimisticMsg, true);

  // Save to Outbox
  await saveToOutbox({
    client_msg_id: clientMsgId,
    kind: 'button',
    button_id: buttonId,
    timestamp: Date.now(),
    retryCount: 0,
  });

  drainOutbox();
  triggerImmediatePoll();
}

async function handleSendAudio(audioBlob, durationSec) {
  hintSent();
  const clientMsgId = crypto.randomUUID();

  // Optimistic render: voice-note label + "uploading…" line (becomes the transcript later)
  const optimisticMsg = {
    client_msg_id: clientMsgId,
    direction: 'in',
    kind: 'audio',
    text: t('ui_chat_voice_note', { sec: Math.round(durationSec) }),
    awaitingTranscript: true,
    created_at: new Date().toISOString(),
  };
  renderMessage(optimisticMsg, true);

  // Save to Outbox
  await saveToOutbox({
    client_msg_id: clientMsgId,
    kind: 'audio',
    audioBlob: audioBlob,
    timestamp: Date.now(),
    retryCount: 0,
  });

  drainOutbox();
  triggerImmediatePoll();
}

// ── Network & Offline Handling ──────────────────────────────────────────────
function updateOnlineStatus() {
  const banner = document.getElementById('network-banner');

  if (!navigator.onLine) {
    netEvent('offline');
    if (!banner) return;
    banner.className = 'network-banner offline';
    const offlineMsg = banner.getAttribute('data-offline-text');
    if (offlineMsg) {
      banner.textContent = offlineMsg;
      banner.style.display = 'block';
    } else {
      console.warn('Network banner element missing data-offline-text attribute');
    }
  } else {
    netEvent('online'); // offline -> "reconnecting…" until the next request succeeds
    if (banner) {
      banner.className = 'network-banner';
      banner.textContent = '';
      banner.style.display = 'none';
    }
    // Bubbles that gave up for lack of network try again now
    for (const [id, reason] of [...state.failedIds]) {
      if (reason === 'network') retryMessage(id);
    }
    drainOutbox();
    triggerImmediatePoll();
  }
}

function showSlowNetworkWarning() {
  const banner = document.getElementById('network-banner');
  if (!banner || !navigator.onLine) return;
  banner.className = 'network-banner slow';
  const slowMsg = banner.getAttribute('data-slow-text');
  if (slowMsg) {
    banner.textContent = slowMsg;
    banner.style.display = 'block';
  } else {
    console.warn('Network banner element missing data-slow-text attribute');
  }
}

// ── Lite Mode Toggle (§9.2) ─────────────────────────────────────────────────
async function toggleLiteMode(forceValue = null) {
  const target = forceValue !== null ? forceValue : !state.liteMode;
  state.liteMode = target;

  try {
    localStorage.setItem('abhyas_lite_mode', target ? 'true' : 'false');
  } catch (e) {
    // ignore storage quota / sandbox errors
  }

  const btn = document.getElementById('lite-mode-menu-btn');
  if (btn) {
    btn.textContent = target ? t('ui_chat_lite_on') : t('ui_chat_lite_off');
  }

  try {
    const csrfToken = getCsrfToken();
    const headers = { 'Content-Type': 'application/json' };
    if (csrfToken) {
      headers['x-csrf-token'] = csrfToken;
    }
    await netFetch('/api/settings', {
      method: 'POST',
      headers,
      body: JSON.stringify({ lite_mode: target }),
    });
  } catch (err) {
    console.warn('Failed to persist lite_mode setting', err);
    flashStatus(t('ui_chat_lite_save_failed'));
  }
}
window.toggleLiteMode = toggleLiteMode;

// ── Mic UI Interaction ──────────────────────────────────────────────────────
// Two ways to record, one button:
//   tap  (press < REC_HOLD_MS): recording starts; tap the big Stop/Send button to send.
//   hold (press >= REC_HOLD_MS): walkie-talkie style, the recording is sent on release.
// Cancel discards. The recorder auto-stops and sends at REC_MAX_SECONDS.
function setupMicEvents() {
  const micBtn = document.getElementById('btn-mic');
  const overlay = document.getElementById('recording-overlay');
  const timerEl = document.getElementById('recording-timer');
  const cancelBtn = document.getElementById('btn-cancel-rec');
  const stopBtn = document.getElementById('btn-stop-rec');
  const recStatus = document.getElementById('rec-status');
  if (!micBtn) return;

  let pressedAt = 0;
  let holdTimer = null;
  const maxLabel = formatTimer(state.recorder.maxDurationSec);

  const setStatus = (key) => {
    if (recStatus) recStatus.textContent = t(key);
  };

  const stopRecUI = () => {
    clearTimeout(holdTimer);
    holdTimer = null;
    pressedAt = 0;
    state.isRecording = false;
    micBtn.classList.remove('recording');
    micBtn.setAttribute('aria-pressed', 'false');
    if (overlay) overlay.classList.remove('active');
    if (timerEl) timerEl.textContent = '0:00';
  };

  const startRec = () => {
    if (state.isRecording) return;
    state.isRecording = true;
    state.mic = micNext(state.mic, 'start');
    micBtn.classList.add('recording');
    micBtn.setAttribute('aria-pressed', 'true');
    setStatus('ui_chat_rec_recording_tap');
    if (timerEl) timerEl.textContent = `0:00 / ${maxLabel}`;
    if (overlay) overlay.classList.add('active');

    state.recorder.start({
      onTick: (sec) => {
        if (timerEl) timerEl.textContent = `${formatTimer(sec)} / ${maxLabel}`;
      },
      onComplete: (blob, durationSec, reason) => {
        state.mic = micNext(state.mic, 'stop');
        stopRecUI();
        if (reason === 'auto') flashStatus(t('ui_chat_rec_auto_sent'));
        handleSendAudio(blob, durationSec).finally(() => {
          state.mic = 'idle';
        });
      },
      onTooShort: () => {
        state.mic = micNext(state.mic, 'cancel');
        stopRecUI();
        flashStatus(t('ui_chat_rec_too_short'));
      },
      onError: (code, detail) => {
        state.mic = micNext(state.mic, 'denied');
        stopRecUI();
        flashStatus(recorderErrorText(code, detail));
      },
    });
  };

  const stopAndSend = () => {
    clearTimeout(holdTimer);
    state.recorder.stop();
  };

  const cancelRec = () => {
    state.recorder.cancel();
    state.mic = micNext(state.mic, 'cancel');
    stopRecUI();
  };

  // Pointer events cover mouse, touch and pen. Capturing the pointer keeps pointerup coming to
  // the mic button after the overlay appears on top of it.
  micBtn.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    e.preventDefault();
    if (state.isRecording) return;
    try {
      micBtn.setPointerCapture(e.pointerId);
    } catch (err) {
      /* capture is best-effort */
    }
    pressedAt = Date.now();
    startRec();
    holdTimer = setTimeout(() => {
      setStatus('ui_chat_rec_recording');
    }, REC_HOLD_MS);
  });

  const onRelease = () => {
    if (!pressedAt || !state.isRecording) return;
    const heldMs = Date.now() - pressedAt;
    pressedAt = 0;
    clearTimeout(holdTimer);
    if (heldMs >= REC_HOLD_MS) {
      stopAndSend(); // hold-to-talk: release sends
    } else {
      // quick tap: keep recording until Stop/Send
      setStatus('ui_chat_rec_recording_tap');
    }
  };
  micBtn.addEventListener('pointerup', onRelease);
  micBtn.addEventListener('pointercancel', onRelease);

  // Keyboard / assistive tech activate the button with a click event that has no pointer
  micBtn.addEventListener('click', (e) => {
    if (e.detail === 0 && !state.isRecording) startRec();
  });

  if (stopBtn) stopBtn.addEventListener('click', stopAndSend);
  if (cancelBtn) cancelBtn.addEventListener('click', cancelRec);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && state.isRecording) cancelRec();
  });
}

// A short notice in the slim status bar (e.g. microphone denied), replaced by the next net event.
function flashStatus(text) {
  const bar = document.getElementById('status-bar');
  if (!bar || !text) return;
  bar.textContent = text;
  bar.className = 'status-bar notice';
  bar.hidden = false;
  setTimeout(renderNetStatus, 6000);
}

// ── Sample lines (demo): one delegated handler, the list follows the step she is on ──
const SAMPLE_BOX_ID = 'sample-list';

function setupDemoChips() {
  const box = document.getElementById(SAMPLE_BOX_ID);
  const tray = document.getElementById('sample-tray');
  // Open on a wide screen, folded on a phone (the sample lines are a judge's helper)
  if (tray && window.matchMedia && window.matchMedia('(min-width: 641px)').matches) tray.open = true;
  if (!box) return;
  let busy = false;
  box.addEventListener('click', async (e) => {
    const c = e.target && e.target.closest ? e.target.closest('.demo-chip') : null;
    if (!c || busy) return;
    busy = true; // locked while the sample loads: no double sends
    c.classList.add('pressed');
    announce(t('ui_chat_chip_done'));
    try {
      const id = c.getAttribute('data-id');
      const text = c.getAttribute('data-text') || c.textContent.trim();
      if (c.getAttribute('data-audio-available') === 'true' && id) {
        try {
          const res = await netFetch(`/api/demo-sample/${id}.wav`);
          if (res.ok) {
            await handleSendAudio(await res.blob(), 4);
            return;
          }
        } catch (err) {
          console.warn('Failed to load demo sample audio, falling back to text:', err);
        }
      }
      await handleSendText(text);
    } finally {
      busy = false;
      setTimeout(() => c.classList.remove('pressed'), CHIP_CONFIRM_MS);
    }
  });
}

// The poll carries the samples that make sense now (null outside demo mode: leave the list alone)
function renderSamples(list) {
  const box = document.getElementById(SAMPLE_BOX_ID);
  if (!box || !Array.isArray(list)) return;
  const sig = list.map((c) => `${c.id}|${c.text}|${c.label}`).join('\n');
  if (box.dataset.sig === sig) return;
  box.dataset.sig = sig;
  while (box.children.length) box.removeChild(box.children[0]);
  list.forEach((c) => {
    const item = document.createElement('div');
    item.className = 'sample-item';
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'demo-chip';
    b.setAttribute('data-id', c.id);
    b.setAttribute('data-text', c.text);
    b.setAttribute('data-audio-available', c.audio ? 'true' : 'false');
    b.textContent = c.label;
    const note = document.createElement('span');
    note.className = 'sample-note';
    note.textContent = c.note;
    item.appendChild(b);
    item.appendChild(note);
    box.appendChild(item);
  });
}

// ── Demo banner: one small line, dismissed for the session ──────────────────
function setupDemoBanner() {
  const banner = document.getElementById('demo-banner');
  if (!banner) return;
  let gone = false;
  try {
    gone = sessionStorage.getItem('abhyas_demo_banner') === 'off';
  } catch (e) {}
  banner.hidden = gone;
  const btn = document.getElementById('demo-dismiss');
  if (btn)
    btn.addEventListener('click', () => {
      banner.hidden = true;
      try {
        sessionStorage.setItem('abhyas_demo_banner', 'off');
      } catch (e) {}
    });
}

// ── Ask the handbook chips: a tap sends the question through the normal text path ──
// The chip says "Sending…", then a tick; the question bubble and a "Looking in the handbook…"
// typing bubble show at once. One question at a time; the chips come back when the send settles.
const CHIP_SETTLE_MAX_MS = 8000;

function whenSettled(clientMsgId, maxMs) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    const poll = () => {
      const st = state.msgStates.get(clientMsgId);
      if ((st && st !== MSG_SENDING) || Date.now() - t0 >= maxMs) resolve(st || MSG_SENDING);
      else setTimeout(poll, 100);
    };
    poll();
  });
}

function setupHandbookChips() {
  const sec = document.getElementById('handbook-chips');
  const prefix = (sec && sec.getAttribute('data-prefix')) || '';
  const chips = document.querySelectorAll('.handbook-chip[data-id]');
  const busy = (b) => chips.forEach((c) => (c.disabled = b));
  chips.forEach((c) => {
    c.onclick = async () => {
      if (c.disabled) return;
      busy(true); // one question at a time. Hindi UI: the label is the question; English: data-text
      const label = c.textContent;
      c.classList.add('sending');
      c.textContent = t('ui_chat_msg_sending');
      try {
        const id = await handleSendText(
          c.getAttribute('data-text') || `${prefix} ${label.trim()}`,
          t('ui_chat_typing_handbook')
        );
        const st = id ? await whenSettled(id, CHIP_SETTLE_MAX_MS) : MSG_FAILED;
        c.classList.remove('sending');
        if (st === MSG_SENT) {
          c.classList.add('sent');
          c.textContent = `✓ ${t('ui_chat_msg_sent')}`;
          await new Promise((r) => setTimeout(r, CHIP_CONFIRM_MS));
        }
      } finally {
        c.classList.remove('sending', 'sent');
        c.textContent = label;
        busy(false);
      }
    };
  });
  const auto = sec && sec.getAttribute('data-autosend'); // ?ask=hb03 from Modules
  if (auto) {
    try {
      history.replaceState(null, '', location.pathname);
    } catch (e) {}
    handleSendText(auto, t('ui_chat_typing_handbook'));
  }
}

// ── Delegated Event Handlers for Server-Rendered Buttons ──────────────────
document.addEventListener('click', (e) => {
  const target = e.target;
  if (!target || !(target instanceof Element)) return;

  const failed = target.closest('.status-icon.failed');
  if (failed) {
    const id = failed.getAttribute('data-client-id');
    if (id) retryMessage(id);
    return;
  }

  if (target.closest('#next-suggest')) {
    const input = document.getElementById('chat-input');
    if (input) {
      input.value = target.closest('#next-suggest').textContent.trim();
      if (input.focus) input.focus();
    }
    return;
  }

  const childPill = target.closest('.child-pill[data-name]');
  if (childPill) {
    addressChild(childPill.getAttribute('data-name'));
    return;
  }

  const replyChip = target.closest('.reply-chip[data-btn-id]');
  if (replyChip) {
    if (replyChip.disabled) return;
    const btnId = replyChip.getAttribute('data-btn-id');
    const btnTitle = replyChip.getAttribute('data-btn-title') || replyChip.textContent.trim();
    if (btnId) {
      const group = replyChip.closest('.quick-replies');
      if (group) lockChips(group, replyChip);
      handleSendButton(btnId, btnTitle);
    }
    return;
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const target = e.target;
  if (!target || !(target instanceof Element)) return;
  const failed = target.closest('.status-icon.failed');
  if (failed) {
    e.preventDefault();
    const id = failed.getAttribute('data-client-id');
    if (id) retryMessage(id);
  }
});

// ── Service Worker Registration ────────────────────────────────────────────
function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker
      .register('/sw.js')
      .then((reg) => console.log('ServiceWorker registered with scope:', reg.scope))
      .catch((err) => console.warn('ServiceWorker registration failed:', err));
  }
}

// ── DOM Message Seeding & Offline Cache Population ─────────────────────────
function initRenderedMessagesFromDom() {
  const container = document.getElementById('chat-messages');
  if (!container) return;

  const rows = container.querySelectorAll('.msg-row');
  const cachedBatch = [];

  rows.forEach((row) => {
    const rawId = row.id ? row.id.replace(/^msg-/, '') : null;
    if (rawId) {
      state.renderedMsgIds.add(rawId);
      state.lastMessageId = rawId;
      state.rows.set(rawId, row);

      const textEl = row.querySelector('.bubble-text');
      const speakerEl = row.querySelector('.speaker-tag');
      const isOut = row.classList.contains('outbound');
      const createdAtAttr = row.getAttribute('data-created-at');
      const createdAt = createdAtAttr && createdAtAttr.trim() ? createdAtAttr.trim() : null;

      cachedBatch.push({
        id: rawId,
        direction: isOut ? 'out' : 'in',
        speaker: speakerEl ? speakerEl.textContent.trim() : null,
        text: textEl ? textEl.textContent.trim() : '',
        created_at: createdAt,
      });
    }
  });

  if (cachedBatch.length > 0) {
    cacheMessages(cachedBatch).catch((err) => console.warn('Cache initial msgs error:', err));
  }
}

// ── Initialization ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  loadUiStrings();

  // 1. Online / Offline listeners
  window.addEventListener('online', updateOnlineStatus);
  window.addEventListener('offline', updateOnlineStatus);
  updateOnlineStatus();

  // 2. Sync Lite Mode from button or localStorage
  const liteBtn = document.getElementById('lite-mode-menu-btn');
  let savedLite = false;
  try {
    savedLite = localStorage.getItem('abhyas_lite_mode') === 'true';
  } catch (e) {}

  if (liteBtn && liteBtn.textContent.trim() === t('ui_chat_lite_on')) {
    state.liteMode = true;
  } else if (savedLite) {
    state.liteMode = true;
    if (liteBtn) {
      liteBtn.textContent = t('ui_chat_lite_on');
    }
  }

  // 3. Form submission
  const form = document.getElementById('composer-form');
  const input = document.getElementById('chat-input');
  if (form && input) {
    form.onsubmit = (e) => {
      e.preventDefault();
      handleSendText(input.value);
    };
  }

  // 4. Setup Mic & Demo Chips
  setupMicEvents();
  setupDemoChips();
  setupDemoBanner();
  setupHandbookChips();
  setupSceneEnd();

  setupLogoutCleanup();

  // 5. Register SW
  registerServiceWorker();

  // 6. Seed rendered messages into IndexedDB & state; give history audio the stateful player
  initRenderedMessagesFromDom();
  upgradeServerAudio();
  scrollChatToEnd();
  window.addEventListener('load', scrollChatToEnd);

  // 7. Initial poll and outbox drain
  await drainOutbox();
  pollMessages();
});
