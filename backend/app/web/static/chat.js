/**
 * Abhyas Chat Application (spec/09 §9.2).
 * Features:
 * - IndexedDB Outbox with retry backoff (2, 4, 8, 16, 30s)
 * - Message deduplication with client_msg_id
 * - Polling (1.5s while pending, 20s while idle)
 * - Network banner (offline & slow connection alerts)
 * - Lite mode toggle & audio playback
 * - Children rehearsal strip & typing indicators
 */

// ── IndexedDB Storage ───────────────────────────────────────────────────────
const DB_NAME = 'abhyas_chat_db';
const DB_VERSION = 1;
const STORE_OUTBOX = 'outbox';
const STORE_MESSAGES = 'messages_cache';

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

// ── State Management ────────────────────────────────────────────────────────
const state = {
  lastMessageId: null,
  isPending: false,
  pollTimer: null,
  liteMode: false,
  isRecording: false,
  recorder: new window.AudioRecorder(),
  outboxRunning: false,
  renderedMsgIds: new Set(),
  playedAudioRefs: new Set(),
  autoPlayDone: false,
  lastAudioPollAt: null,
  lastMessageCreated: null,
};

// ── Outbox Drainer & Backoff Retrier ────────────────────────────────────────
const BACKOFF_STEPS = [2000, 4000, 8000, 16000, 30000];

async function drainOutbox() {
  if (state.outboxRunning || !navigator.onLine) return;
  state.outboxRunning = true;

  try {
    const items = await getPendingOutboxItems();
    for (const item of items) {
      if (!navigator.onLine) break;

      const retryCount = item.retryCount || 0;
      let success = false;

      try {
        const startTime = Date.now();
        let resp;

        const csrfToken = getCsrfToken();
        const jsonHeaders = { 'Content-Type': 'application/json' };
        if (csrfToken) {
          jsonHeaders['x-csrf-token'] = csrfToken;
        }

        if (item.kind === 'text') {
          resp = await fetch('/api/chat/text', {
            method: 'POST',
            headers: jsonHeaders,
            body: JSON.stringify({ client_msg_id: item.client_msg_id, text: item.text }),
          });
        } else if (item.kind === 'button') {
          resp = await fetch('/api/chat/button', {
            method: 'POST',
            headers: jsonHeaders,
            body: JSON.stringify({ client_msg_id: item.client_msg_id, button_id: item.button_id }),
          });
        } else if (item.kind === 'audio' && item.audioBlob) {
          const form = new FormData();
          form.append('client_msg_id', item.client_msg_id);
          form.append('file', item.audioBlob, 'voice.webm');
          const audioHeaders = {};
          if (csrfToken) {
            audioHeaders['x-csrf-token'] = csrfToken;
          }
          resp = await fetch('/api/chat/audio', {
            method: 'POST',
            headers: audioHeaders,
            body: form,
          });
        }

        const duration = Date.now() - startTime;
        if (duration > 8000) {
          showSlowNetworkWarning();
        }

        if (resp && resp.status >= 200 && resp.status < 300) {
          success = true;
          const body = await resp.json().catch(() => null);
          if (body && body.message_id) {
            adoptServerMessageId(item.client_msg_id, body.message_id);
          }
          await removeFromOutbox(item.client_msg_id);
          updateMessageStatus(item.client_msg_id, '✓');
        }
      } catch (err) {
        console.warn('Upload error for item', item.client_msg_id, err);
      }

      if (!success) {
        item.retryCount = retryCount + 1;
        const delay = BACKOFF_STEPS[Math.min(retryCount, BACKOFF_STEPS.length - 1)];
        await saveToOutbox(item);
        // Pause briefly before next retry
        await new Promise((r) => setTimeout(r, delay));
      }
    }
  } finally {
    state.outboxRunning = false;
  }
}

// ── Polling Loop (§7.3) ─────────────────────────────────────────────────────
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

    const res = await fetch(url);
    const duration = Date.now() - startTime;
    if (duration > 8000) {
      showSlowNetworkWarning();
    }

    if (res.ok) {
      const data = await res.json();
      if (data.server_time) {
        state.lastAudioPollAt = data.server_time;
      }
      state.isPending = data.pending;
      updatePendingIndicator(data.pending);

      if (data.messages && data.messages.length > 0) {
        for (const msg of data.messages) {
          renderMessage(msg);
          if (!state.lastMessageCreated || (msg.created_at && msg.created_at >= state.lastMessageCreated)) {
            state.lastMessageId = msg.id;
            state.lastMessageCreated = msg.created_at;
          }
        }
        await cacheMessages(data.messages);
      }
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

// ── UI Rendering ────────────────────────────────────────────────────────────
// The optimistic bubble is keyed by client_msg_id; the server copy of the same
// message (POST response / poll) carries the server id. Re-key the bubble so the
// polled copy is recognised instead of being rendered as a second bubble.
function adoptServerMessageId(clientMsgId, serverId) {
  if (!clientMsgId || !serverId || clientMsgId === serverId) return;
  if (!state.renderedMsgIds.has(clientMsgId)) return;
  state.renderedMsgIds.add(serverId);
  const row = document.getElementById(`msg-${clientMsgId}`);
  if (row) row.id = `msg-${serverId}`;
}

function renderMessage(msg, isLocalOptimistic = false) {
  if (msg.id && msg.client_msg_id && state.renderedMsgIds.has(msg.client_msg_id)) {
    adoptServerMessageId(msg.client_msg_id, msg.id);
    updateMessageStatus(msg.client_msg_id, '✓');
  }
  const msgKey = msg.id || msg.client_msg_id;
  if (state.renderedMsgIds.has(msgKey)) {
    // Text-first delivery support: attach audio to previously rendered text bubble
    if (msg.audio_ref) {
      const existingRow = document.getElementById(`msg-${msgKey}`);
      if (existingRow && !existingRow.querySelector('.bubble-audio')) {
        const bubble = existingRow.querySelector('.bubble');
        if (bubble) {
          const audioWrap = document.createElement('div');
          audioWrap.className = 'bubble-audio';

          const playBtn = document.createElement('button');
          playBtn.className = 'btn-play';
          playBtn.setAttribute('aria-label', 'आवाज़ सुनें');
          playBtn.innerHTML = '▶';

          const audioEl = document.createElement('audio');
          audioEl.preload = state.liteMode ? 'none' : 'metadata';
          audioEl.src = `/api/audio/${encodeURIComponent(msg.audio_ref)}.ogg`;

          playBtn.onclick = () => {
            if (audioEl.paused) {
              audioEl.play().catch(console.error);
              playBtn.innerHTML = '⏸';
            } else {
              audioEl.pause();
              playBtn.innerHTML = '▶';
            }
          };
          audioEl.onended = () => {
            playBtn.innerHTML = '▶';
          };

          const label = document.createElement('span');
          label.className = 'audio-duration';
          label.textContent = 'ऑडियो संदेश';

          audioWrap.appendChild(playBtn);
          audioWrap.appendChild(label);
          audioWrap.appendChild(audioEl);

          const meta = bubble.querySelector('.bubble-meta');
          if (meta) {
            bubble.insertBefore(audioWrap, meta);
          } else {
            bubble.appendChild(audioWrap);
          }
        }
      }
    }
    return;
  }
  state.renderedMsgIds.add(msgKey);

  const container = document.getElementById('chat-messages');
  if (!container) return;

  const row = document.createElement('div');
  row.className = `msg-row ${msg.direction === 'in' ? 'inbound' : 'outbound'}`;
  row.id = `msg-${msg.id || msg.client_msg_id}`;

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  // Speaker Tag (bot messages)
  if (msg.direction === 'out' && msg.speaker) {
    const speakerEl = document.createElement('div');
    speakerEl.className = `speaker-tag ${msg.speaker.toLowerCase()}`;
    speakerEl.textContent = getSpeakerHindiLabel(msg.speaker);
    bubble.appendChild(speakerEl);
  }

  // Text Content
  if (msg.text) {
    const textEl = document.createElement('p');
    textEl.className = 'bubble-text';
    textEl.textContent = msg.text;
    bubble.appendChild(textEl);
  }

  // Audio Player (if audio_ref exists)
  if (msg.audio_ref) {
    const audioWrap = document.createElement('div');
    audioWrap.className = 'bubble-audio';

    const playBtn = document.createElement('button');
    playBtn.className = 'btn-play';
    playBtn.setAttribute('aria-label', 'आवाज़ सुनें');
    playBtn.innerHTML = '▶';

    const audioEl = document.createElement('audio');
    audioEl.preload = state.liteMode ? 'none' : 'metadata';
    audioEl.src = `/api/audio/${encodeURIComponent(msg.audio_ref)}.ogg`;

    playBtn.onclick = () => {
      if (audioEl.paused) {
        audioEl.play().catch(console.error);
        playBtn.innerHTML = '⏸';
      } else {
        audioEl.pause();
        playBtn.innerHTML = '▶';
      }
    };
    audioEl.onended = () => {
      playBtn.innerHTML = '▶';
    };

    const label = document.createElement('span');
    label.className = 'audio-duration';
    label.textContent = 'ऑडियो संदेश';

    audioWrap.appendChild(playBtn);
    audioWrap.appendChild(label);
    audioWrap.appendChild(audioEl);
    bubble.appendChild(audioWrap);

    // Auto-play newest child line once in normal mode if not played
    if (!state.liteMode && !state.autoPlayDone && isChildSpeaker(msg.speaker)) {
      state.autoPlayDone = true;
      setTimeout(() => {
        audioEl.play().catch(() => {
          // Browser gesture block, gracefully silent
        });
      }, 300);
    }
  }

  // Metadata / Status Tick
  const meta = document.createElement('div');
  meta.className = 'bubble-meta';
  const timeStr = msg.created_at
    ? new Date(msg.created_at).toLocaleTimeString('hi-IN', { hour: '2-digit', minute: '2-digit' })
    : 'अभी';
  meta.innerHTML = `<span>${timeStr}</span> <span class="status-icon" id="status-${msg.client_msg_id || msg.id}">${isLocalOptimistic ? '⏱' : (msg.direction === 'in' ? '✓' : '')}</span>`;
  bubble.appendChild(meta);

  row.appendChild(bubble);

  // Quick-reply Buttons (chips under last bot message)
  if (msg.direction === 'out' && msg.buttons && msg.buttons.length > 0) {
    const qrContainer = document.createElement('div');
    qrContainer.className = 'quick-replies';
    msg.buttons.forEach((btn) => {
      const chip = document.createElement('button');
      chip.className = 'reply-chip';
      chip.textContent = btn.title_hi;
      chip.onclick = () => {
        qrContainer.querySelectorAll('.reply-chip').forEach((c) => (c.disabled = true));
        handleSendButton(btn.id, btn.title_hi);
      };
      qrContainer.appendChild(chip);
    });
    row.appendChild(qrContainer);
  }

  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
}

function updateMessageStatus(clientMsgId, statusIcon) {
  const el = document.getElementById(`status-${clientMsgId}`);
  if (el) {
    el.textContent = statusIcon;
  }
}

function updatePendingIndicator(pending) {
  const bubble = document.getElementById('pending-bubble');
  if (bubble) {
    if (pending) {
      bubble.classList.add('active');
    } else {
      bubble.classList.remove('active');
    }
  }
}

function getSpeakerHindiLabel(speaker) {
  const map = {
    abhyas: 'अभ्यास',
    coach: 'कोच',
    model_teacher: 'आदर्श शिक्षिका',
    ravi: 'रवि',
    priya: 'प्रिया',
    aman: 'अमन',
  };
  return map[speaker] || speaker;
}

function isChildSpeaker(speaker) {
  return speaker === 'ravi' || speaker === 'priya' || speaker === 'aman';
}

// ── Sending Handlers ────────────────────────────────────────────────────────
async function handleSendText(text) {
  if (!text || !text.trim()) return;
  const clientMsgId = crypto.randomUUID();
  const cleanText = text.trim();

  // 1. Optimistic render in UI
  const optimisticMsg = {
    client_msg_id: clientMsgId,
    direction: 'in',
    kind: 'text',
    text: cleanText,
    created_at: new Date().toISOString(),
  };
  renderMessage(optimisticMsg, true);

  // 2. Save to IndexedDB Outbox
  await saveToOutbox({
    client_msg_id: clientMsgId,
    kind: 'text',
    text: cleanText,
    timestamp: Date.now(),
    retryCount: 0,
  });

  // 3. Clear input
  const input = document.getElementById('chat-input');
  if (input) input.value = '';

  // 4. Trigger Outbox upload & fast poll
  drainOutbox();
  triggerImmediatePoll();
}

async function handleSendButton(buttonId, buttonTitle) {
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
  const clientMsgId = crypto.randomUUID();

  // Optimistic render
  const optimisticMsg = {
    client_msg_id: clientMsgId,
    direction: 'in',
    kind: 'audio',
    text: '🎤 वॉयस नोट (' + Math.round(durationSec) + 's)',
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
  if (!banner) return;

  if (!navigator.onLine) {
    banner.className = 'network-banner offline';
    const offlineMsg = banner.getAttribute('data-offline-text');
    if (offlineMsg) {
      banner.textContent = offlineMsg;
      banner.style.display = 'block';
    } else {
      console.warn('Network banner element missing data-offline-text attribute');
    }
  } else {
    banner.className = 'network-banner';
    banner.textContent = '';
    banner.style.display = 'none';
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
    btn.textContent = target ? 'लाइट मोड: चालू ✓' : 'लाइट मोड: बंद';
  }

  try {
    const csrfToken = getCsrfToken();
    const headers = { 'Content-Type': 'application/json' };
    if (csrfToken) {
      headers['x-csrf-token'] = csrfToken;
    }
    await fetch('/api/settings', {
      method: 'POST',
      headers,
      body: JSON.stringify({ lite_mode: target }),
    });
  } catch (err) {
    console.warn('Failed to persist lite_mode setting', err);
  }
}
window.toggleLiteMode = toggleLiteMode;

// ── Mic UI Interaction ──────────────────────────────────────────────────────
function setupMicEvents() {
  const micBtn = document.getElementById('btn-mic');
  const overlay = document.getElementById('recording-overlay');
  const timerEl = document.getElementById('recording-timer');
  const cancelBtn = document.getElementById('btn-cancel-rec');
  if (!micBtn) return;

  let isHeld = false;

  const startRec = () => {
    if (state.isRecording) return;
    state.isRecording = true;
    micBtn.classList.add('recording');
    if (overlay) overlay.classList.add('active');

    state.recorder.start(
      (sec) => {
        if (timerEl) {
          const m = Math.floor(sec / 60);
          const s = Math.floor(sec % 60);
          timerEl.textContent = `${m}:${s < 10 ? '0' : ''}${s}`;
        }
      },
      (blob, durationSec) => {
        stopRecUI();
        handleSendAudio(blob, durationSec);
      },
      (errMsg) => {
        stopRecUI();
        alert(errMsg);
      }
    );
  };

  const stopRecUI = () => {
    state.isRecording = false;
    micBtn.classList.remove('recording');
    if (overlay) overlay.classList.remove('active');
    if (timerEl) timerEl.textContent = '0:00';
  };

  // Touch and Mouse support (Hold-to-record & Tap accessibility)
  micBtn.addEventListener('mousedown', () => {
    isHeld = true;
    startRec();
  });

  window.addEventListener('mouseup', () => {
    if (isHeld && state.isRecording) {
      isHeld = false;
      state.recorder.stop();
    }
  });

  micBtn.addEventListener('touchstart', (e) => {
    e.preventDefault();
    isHeld = true;
    startRec();
  });

  window.addEventListener('touchend', () => {
    if (isHeld && state.isRecording) {
      isHeld = false;
      state.recorder.stop();
    }
  });

  if (cancelBtn) {
    cancelBtn.onclick = () => {
      isHeld = false;
      state.recorder.cancel();
      stopRecUI();
    };
  }
}

// ── Demo Chip Handler ───────────────────────────────────────────────────────
function setupDemoChips() {
  const chips = document.querySelectorAll('.demo-chip');
  chips.forEach((c) => {
    c.onclick = async () => {
      const id = c.getAttribute('data-id');
      const audioAvailable = c.getAttribute('data-audio-available') === 'true';
      const text = c.getAttribute('data-text') || c.textContent.trim();
      if (audioAvailable && id) {
        try {
          const res = await fetch(`/api/demo-sample/${id}.wav`);
          if (res.ok) {
            const blob = await res.blob();
            await handleSendAudio(blob, 4);
            return;
          }
        } catch (err) {
          console.warn('Failed to load demo sample audio, falling back to text:', err);
        }
      }
      handleSendText(text);
    };
  });
}

// ── Delegated Event Handlers for Server-Rendered Buttons ──────────────────
function playAudioDirect(btn, audioRef) {
  let audio = btn._audio;
  if (!audio) {
    audio = new Audio('/api/audio/' + encodeURIComponent(audioRef) + '.ogg');
    btn._audio = audio;
    audio.onended = () => {
      btn.innerHTML = '▶';
    };
  }
  if (audio.paused) {
    audio.play().catch(console.error);
    btn.innerHTML = '⏸';
  } else {
    audio.pause();
    btn.innerHTML = '▶';
  }
}
window.playAudioDirect = playAudioDirect;

document.addEventListener('click', (e) => {
  const target = e.target;
  if (!target || !(target instanceof Element)) return;

  const playBtn = target.closest('.btn-play[data-audio-ref]');
  if (playBtn) {
    const audioRef = playBtn.getAttribute('data-audio-ref');
    if (audioRef) {
      playAudioDirect(playBtn, audioRef);
    }
    return;
  }

  const replyChip = target.closest('.reply-chip[data-btn-id]');
  if (replyChip) {
    const btnId = replyChip.getAttribute('data-btn-id');
    const btnTitle = replyChip.getAttribute('data-btn-title') || replyChip.textContent.trim();
    if (btnId) {
      handleSendButton(btnId, btnTitle);
    }
    return;
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

  if (liteBtn && liteBtn.textContent.includes('चालू')) {
    state.liteMode = true;
  } else if (savedLite) {
    state.liteMode = true;
    if (liteBtn) {
      liteBtn.textContent = 'लाइट मोड: चालू ✓';
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

  // 5. Register SW
  registerServiceWorker();

  // 6. Seed rendered messages into IndexedDB & state
  initRenderedMessagesFromDom();

  // 7. Initial poll and outbox drain
  await drainOutbox();
  pollMessages();
});
