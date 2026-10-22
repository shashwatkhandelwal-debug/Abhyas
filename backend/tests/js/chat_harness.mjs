// Loads the real static/chat.js into a Node vm with a small DOM, IndexedDB, timer and
// fetch stub, so the state machines and their DOM effects can be tested without a browser.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export const CHAT_JS = path.join(here, '../../app/web/static/chat.js');
export const CATALOG = path.join(here, '../../../content/messages_hi.yaml');

// ── minimal DOM ─────────────────────────────────────────────────────────────
function parseCompound(sel) {
  // supports: tag, .class, #id, [attr], [attr="v"] and combinations of those
  const out = { tag: null, classes: [], id: null, attrs: [] };
  const re = /([#.][\w-]+)|\[([\w-]+)(?:="([^"]*)")?\]|^([\w-]+)/g;
  let m;
  while ((m = re.exec(sel))) {
    if (m[1] && m[1][0] === '.') out.classes.push(m[1].slice(1));
    else if (m[1]) out.id = m[1].slice(1);
    else if (m[2]) out.attrs.push([m[2], m[3]]);
    else if (m[4]) out.tag = m[4];
  }
  return out;
}

export class El {
  constructor(tag) {
    this.tagName = (tag || 'div').toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.attrs = {};
    this.dataset = {};
    this.style = {};
    this.textContent = '';
    this.innerHTML = '';
    this.hidden = false;
    this.disabled = false;
    this.id = '';
    this.scrollTop = 0;
    this.scrollHeight = 0;
    this._cls = new Set();
    const self = this;
    this.classList = {
      add: (...c) => c.forEach((x) => self._cls.add(x)),
      remove: (...c) => c.forEach((x) => self._cls.delete(x)),
      toggle: (c, force) => {
        const on = force === undefined ? !self._cls.has(c) : force;
        on ? self._cls.add(c) : self._cls.delete(c);
        return on;
      },
      contains: (c) => self._cls.has(c),
    };
  }
  get className() {
    return [...this._cls].join(' ');
  }
  set className(v) {
    this._cls = new Set(String(v).split(/\s+/).filter(Boolean));
  }
  appendChild(c) {
    if (c.parentNode) c.parentNode.removeChild(c);
    c.parentNode = this;
    this.children.push(c);
    return c;
  }
  insertBefore(c, ref) {
    if (c.parentNode) c.parentNode.removeChild(c);
    c.parentNode = this;
    const i = ref ? this.children.indexOf(ref) : -1;
    if (i === -1) this.children.push(c);
    else this.children.splice(i, 0, c);
    return c;
  }
  remove() {
    if (this.parentNode) this.parentNode.removeChild(this);
  }
  removeChild(c) {
    const i = this.children.indexOf(c);
    if (i !== -1) this.children.splice(i, 1);
    c.parentNode = null;
    return c;
  }
  replaceChild(n, o) {
    this.insertBefore(n, o);
    this.removeChild(o);
    return o;
  }
  setAttribute(k, v) {
    this.attrs[k] = String(v);
  }
  getAttribute(k) {
    return k in this.attrs ? this.attrs[k] : null;
  }
  removeAttribute(k) {
    delete this.attrs[k];
  }
  addEventListener(type, fn) {
    (this._listeners ||= {})[type] = fn;
  }
  matches(sel) {
    return sel.split(',').some((part) => {
      const c = parseCompound(part.trim());
      return (
        (!c.tag || c.tag.toUpperCase() === this.tagName) &&
        c.classes.every((x) => this._cls.has(x)) &&
        (!c.id || c.id === this.id) &&
        c.attrs.every(([k, v]) => k in this.attrs && (v === undefined || this.attrs[k] === v))
      );
    });
  }
  closest(sel) {
    for (let n = this; n; n = n.parentNode) if (n.matches && n.matches(sel)) return n;
    return null;
  }
  querySelectorAll(sel) {
    const out = [];
    const walk = (n) => {
      for (const c of n.children) {
        if (c.matches(sel)) out.push(c);
        walk(c);
      }
    };
    walk(this);
    return out;
  }
  querySelector(sel) {
    return this.querySelectorAll(sel)[0] || null;
  }
}
// `instanceof Element` in chat.js
export const ElementCtor = El;

// ── fake IndexedDB (outbox + messages_cache) ────────────────────────────────
function makeIndexedDB() {
  const stores = { outbox: new Map(), messages_cache: new Map() };
  const keyPaths = { outbox: 'client_msg_id', messages_cache: 'id' };
  const later = (fn) => queueMicrotask(fn);
  const db = {
    objectStoreNames: { contains: () => true },
    transaction(names) {
      const tx = { oncomplete: null, onerror: null };
      const name = names[0];
      const store = stores[name];
      const done = () => later(() => tx.oncomplete && tx.oncomplete());
      tx.objectStore = () => ({
        put(item) {
          store.set(item[keyPaths[name]], structuredClone(item));
          done();
        },
        delete(key) {
          store.delete(key);
          done();
        },
        getAll() {
          const req = { result: null, onsuccess: null };
          later(() => {
            req.result = [...store.values()].map((v) => structuredClone(v));
            req.onsuccess && req.onsuccess();
          });
          return req;
        },
      });
      return tx;
    },
  };
  return {
    stores,
    open() {
      const req = { result: db, onsuccess: null, onerror: null, onupgradeneeded: null };
      later(() => req.onsuccess && req.onsuccess());
      return req;
    },
  };
}

// ── harness ─────────────────────────────────────────────────────────────────
export function loadChat({ strings = {}, online = true } = {}) {
  const body = new El('body');
  const byId = {};
  const add = (id, tag = 'div', parent = body) => {
    const el = new El(tag);
    el.id = id;
    parent.appendChild(el);
    byId[id] = el;
    return el;
  };
  const container = add('chat-messages', 'main');
  const pending = add('pending-bubble', 'div', container);
  pending.className = 'pending-bubble';
  add('pending-text', 'span', pending);
  add('status-bar');
  byId['status-bar'].hidden = true;
  add('sr-live');
  add('chat-input', 'input');

  const findById = (node, id) => {
    for (const c of node.children) {
      if (c.id === id) return c;
      const hit = findById(c, id);
      if (hit) return hit;
    }
    return null;
  };

  // controllable clock + timers
  const clock = { now: 1_700_000_000_000 };
  const timers = [];
  let timerSeq = 0;
  const fakeSetTimeout = (fn, ms = 0) => {
    const t = { id: ++timerSeq, at: clock.now + ms, fn, every: null };
    timers.push(t);
    return t.id;
  };
  const fakeSetInterval = (fn, ms) => {
    const t = { id: ++timerSeq, at: clock.now + ms, fn, every: ms };
    timers.push(t);
    return t.id;
  };
  const clearTimer = (id) => {
    const i = timers.findIndex((t) => t.id === id);
    if (i !== -1) timers.splice(i, 1);
  };
  async function advance(ms) {
    const end = clock.now + ms;
    for (;;) {
      timers.sort((a, b) => a.at - b.at);
      const next = timers[0];
      if (!next || next.at > end) break;
      clock.now = next.at;
      if (next.every) next.at += next.every;
      else timers.shift();
      next.fn();
      await flush();
    }
    clock.now = end;
  }
  const flush = async () => {
    for (let i = 0; i < 8; i++) await new Promise((r) => setImmediate(r));
  };

  class FakeDate extends Date {
    static now() {
      return clock.now;
    }
    constructor(...a) {
      super(...(a.length ? a : [clock.now]));
    }
  }

  const fetchCalls = [];
  const net = { handler: async () => ({ status: 200, ok: true, json: async () => ({}) }) };

  class FakeAudio {
    constructor() {
      this.handlers = {};
      this.paused = true;
      this.ended = false;
      this.playResult = FakeAudio.playResult;
      FakeAudio.instances.push(this);
    }
    addEventListener(t, fn) {
      this.handlers[t] = fn;
    }
    fire(t) {
      this.handlers[t] && this.handlers[t]();
    }
    play() {
      return this.playResult === 'ok' ? Promise.resolve() : Promise.reject(new Error('blocked'));
    }
    pause() {
      this.fire('pause');
    }
    load() {}
  }
  FakeAudio.instances = [];
  FakeAudio.playResult = 'ok'; // set to 'blocked' to simulate the browser refusing autoplay

  const documentListeners = {};
  const document = {
    getElementById: (id) => byId[id] || findById(body, id),
    createElement: (tag) => new El(tag),
    addEventListener: (t, fn) => (documentListeners[t] = fn),
    querySelector: (s) => (s.startsWith('meta') ? null : body.querySelector(s)),
    querySelectorAll: (s) => body.querySelectorAll(s),
    cookie: '',
  };
  const navigator = { onLine: online, serviceWorker: undefined };
  const window = { AudioRecorder: class {}, addEventListener() {}, confirm: () => true };
  let uuid = 0;
  const sandbox = {
    window,
    document,
    navigator,
    console: { log() {}, warn() {}, error() {} },
    Element: El,
    Audio: FakeAudio,
    Date: FakeDate,
    indexedDB: makeIndexedDB(),
    localStorage: { getItem: () => null, setItem() {} },
    crypto: { randomUUID: () => `client-${++uuid}` },
    FormData: class {
      append() {}
    },
    structuredClone,
    setTimeout: fakeSetTimeout,
    clearTimeout: clearTimer,
    setInterval: fakeSetInterval,
    clearInterval: clearTimer,
    fetch: async (url, opts) => {
      fetchCalls.push({ url, opts });
      return net.handler(url, opts);
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(CHAT_JS, 'utf8'), sandbox, { filename: 'chat.js' });
  const api = vm.runInContext(
    `({ nextMsgState, typingNext, TYPING_OFF, guessSpeaker, audioNext, micNext, netNext, formatTimer,
        state, t, setUiStrings, renderMessage, setMessageState, failMessage, retryMessage,
        typingEvent, renderTyping, netFetch, netEvent, buildAudioWrap, attachAudioRef, lockChips,
        drainOutbox, handleSendText, handleSendAudio, setMicPhase, onAudioButton, expectsAudio,
        TYPING_TIMEOUT_MS, COLD_START_HINT_MS, AUDIO_WAIT_MS, MAX_AUTO_RETRIES, BACKOFF_STEPS,
        pollMessages, updateOnlineStatus, upgradeServerAudio,
        toggleTranslation, buildTranslateControl, TRANSLATABLE_SPEAKERS, getSpeakerLabel,
        renderSceneHeader, setupSceneEnd, recorderErrorText, toggleLiteMode, flashStatus })`,
    sandbox
  );
  api.setUiStrings(strings);
  return {
    ...api,
    sandbox,
    byId,
    container,
    clock,
    advance,
    flush,
    fetchCalls,
    net,
    FakeAudio,
    navigator,
    documentListeners,
    rows: () => container.children.filter((c) => c.className.includes('msg-row')),
  };
}

// Reads ui_chat_* strings from the real catalog so tests use the shipped Hindi.
export function catalogStrings() {
  const out = {};
  for (const line of fs.readFileSync(CATALOG, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^((?:ui|speaker)_[a-z0-9_]+): \{text: "(.*?)"(?:, text_m: ".*?")?, audio: false\}/);
    if (m) out[m[1]] = m[2];
  }
  return out;
}
