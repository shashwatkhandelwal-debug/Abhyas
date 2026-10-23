// Behavioural tests for the service worker (run: node --test backend/tests/js).
// sw.js is evaluated in a vm sandbox with a minimal in-memory Cache Storage.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const SW_SOURCE = fs.readFileSync(path.join(here, '../../app/web/static/sw.js'), 'utf8');

class FakeResponse {
  constructor(body, init = {}) {
    this.body = body;
    this.status = init.status ?? 200;
  }
  clone() {
    return new FakeResponse(this.body, { status: this.status });
  }
}

class FakeRequest {
  constructor(url, init = {}) {
    this.url = url.startsWith('http') ? url : `https://abhyas.test${url}`;
    this.mode = init.mode ?? 'no-cors';
    this.headers = { get: () => null };
  }
}

function makeCaches() {
  const store = new Map();
  const keyOf = (req) => (typeof req === 'string' ? new URL(req, 'https://abhyas.test').href : req.url);
  const makeCache = (map) => ({
    async match(req) {
      return map.get(keyOf(req));
    },
    async put(req, res) {
      map.set(keyOf(req), res);
    },
    async addAll(reqs) {
      for (const r of reqs) map.set(keyOf(r), new FakeResponse(`precached:${keyOf(r)}`));
    },
    async keys() {
      return [...map.keys()].map((u) => ({ url: u }));
    },
    async delete(req) {
      return map.delete(keyOf(req));
    },
  });
  return {
    store,
    async open(name) {
      if (!store.has(name)) store.set(name, new Map());
      return makeCache(store.get(name));
    },
    async keys() {
      return [...store.keys()];
    },
    async delete(name) {
      return store.delete(name);
    },
    async match(req) {
      for (const map of store.values()) {
        const hit = map.get(keyOf(req));
        if (hit) return hit;
      }
      return undefined;
    },
  };
}

function loadSw({ version = 'abc123-deadbeef', fetchImpl }) {
  const listeners = {};
  const caches = makeCaches();
  const self = {
    addEventListener: (type, fn) => (listeners[type] = fn),
    skipWaiting: () => {},
    clients: { claim: () => {} },
  };
  const sandbox = {
    self,
    caches,
    fetch: fetchImpl ?? (async () => new FakeResponse('network')),
    Request: FakeRequest,
    Response: FakeResponse,
    URL,
    Promise,
    console,
  };
  vm.runInNewContext(SW_SOURCE.replaceAll('__BUILD_VERSION__', version), sandbox);

  const dispatch = async (type, event = {}) => {
    let pending;
    const ev = { ...event, waitUntil: (p) => (pending = p), respondWith: (p) => (pending = p) };
    listeners[type](ev);
    return pending === undefined ? undefined : await pending;
  };
  return { caches, dispatch, version };
}

const fetchEvent = (url) => ({ request: new FakeRequest(url) });
const settle = () => new Promise((r) => setImmediate(r));

test('cache name carries the build version', async () => {
  const { caches, dispatch } = loadSw({ version: 'v9-cafe0001' });
  await dispatch('install');
  assert.deepEqual(await caches.keys(), ['abhyas-static-v9-cafe0001']);
});

test('install precaches bypassing the HTTP cache', async () => {
  assert.match(SW_SOURCE, /cache:\s*'reload'/);
});

test('install precaches the build-stamped asset URLs that pages of this build ask for', async () => {
  const { caches, dispatch } = loadSw({ version: 'v9-cafe0001' });
  await dispatch('install');
  const urls = (await (await caches.open('abhyas-static-v9-cafe0001')).keys()).map((k) => k.url);
  for (const name of ['chat.js', 'app.css', 'recorder.js']) {
    assert.ok(urls.includes(`https://abhyas.test/static/${name}?v=v9-cafe0001`), name);
  }
});

test('a page of a new build never gets an older chat.js, even from the old cache', async () => {
  // Yesterday's worker cached chat.js by its bare URL. Today's page asks for ?v=<today>, a URL
  // that cache has never seen, so stale-while-revalidate has nothing stale to serve.
  let network = 'chat.js TODAY';
  const { caches, dispatch } = loadSw({ version: 'today-1', fetchImpl: async () => new FakeResponse(network) });
  const old = await caches.open('abhyas-static-yesterday-0');
  await old.put('/static/chat.js', new FakeResponse('chat.js YESTERDAY'));
  const served = await dispatch('fetch', fetchEvent('/static/chat.js?v=today-1'));
  assert.equal(served.body, 'chat.js TODAY');
});

test('activate deletes old static caches (including the legacy fixed name) but keeps audio', async () => {
  const { caches, dispatch } = loadSw({ version: 'new-1' });
  for (const n of ['abhyas-static-v1', 'abhyas-static-old-2', 'abhyas-static-new-1', 'abhyas-audio-v1', 'other-app']) {
    await caches.open(n);
  }
  await dispatch('activate');
  assert.deepEqual((await caches.keys()).sort(), ['abhyas-audio-v1', 'abhyas-static-new-1']);
});

test('js is stale-while-revalidate: cached copy served, cache refreshed for next load', async () => {
  let network = 'chat.js NEW';
  const { caches, dispatch } = loadSw({
    version: 'a-1',
    fetchImpl: async () => new FakeResponse(network),
  });
  const cache = await caches.open('abhyas-static-a-1');
  await cache.put('/static/chat.js', new FakeResponse('chat.js OLD'));

  const first = await dispatch('fetch', fetchEvent('/static/chat.js'));
  assert.equal(first.body, 'chat.js OLD');
  await settle();
  const second = await dispatch('fetch', fetchEvent('/static/chat.js'));
  assert.equal(second.body, 'chat.js NEW');

  network = 'chat.js NEWER';
  assert.equal((await dispatch('fetch', fetchEvent('/static/chat.js'))).body, 'chat.js NEW');
});

test('css is stale-while-revalidate too', async () => {
  const { caches, dispatch } = loadSw({ version: 'a-1', fetchImpl: async () => new FakeResponse('css NEW') });
  const cache = await caches.open('abhyas-static-a-1');
  await cache.put('/static/app.css', new FakeResponse('css OLD'));
  assert.equal((await dispatch('fetch', fetchEvent('/static/app.css'))).body, 'css OLD');
  await settle();
  assert.equal((await dispatch('fetch', fetchEvent('/static/app.css'))).body, 'css NEW');
});

test('uncached js goes to the network and is stored', async () => {
  const { caches, dispatch } = loadSw({ version: 'a-1', fetchImpl: async () => new FakeResponse('fresh') });
  const res = await dispatch('fetch', fetchEvent('/static/recorder.js'));
  assert.equal(res.body, 'fresh');
  const cache = await caches.open('abhyas-static-a-1');
  assert.equal((await cache.match('/static/recorder.js')).body, 'fresh');
});

test('offline with a cached js still serves it and does not throw', async () => {
  const { caches, dispatch } = loadSw({
    version: 'a-1',
    fetchImpl: async () => {
      throw new TypeError('network down');
    },
  });
  const cache = await caches.open('abhyas-static-a-1');
  await cache.put('/static/chat.js', new FakeResponse('cached'));
  assert.equal((await dispatch('fetch', fetchEvent('/static/chat.js'))).body, 'cached');
  await settle();
});

test('non-script static assets stay cache-first', async () => {
  let hits = 0;
  const { caches, dispatch } = loadSw({
    version: 'a-1',
    fetchImpl: async () => {
      hits += 1;
      return new FakeResponse('net');
    },
  });
  const cache = await caches.open('abhyas-static-a-1');
  await cache.put('/static/manifest.json', new FakeResponse('cached manifest'));
  assert.equal((await dispatch('fetch', fetchEvent('/static/manifest.json'))).body, 'cached manifest');
  assert.equal(hits, 0);
});

// ── navigation fallbacks ────────────────────────────────────────────────────
test('navigation while the host answers 503 shows the cached waking page', async () => {
  const { dispatch } = loadSw({ fetchImpl: async () => new FakeResponse('render-503', { status: 503 }) });
  await dispatch('install');
  const res = await dispatch('fetch', { request: new FakeRequest('/teacher', { mode: 'navigate' }) });
  assert.equal(res.body, 'precached:https://abhyas.test/waking');
});

test('navigation with no network at all shows the offline page', async () => {
  const { dispatch } = loadSw({
    fetchImpl: async () => {
      throw new TypeError('Failed to fetch');
    },
  });
  await dispatch('install');
  const res = await dispatch('fetch', { request: new FakeRequest('/teacher', { mode: 'navigate' }) });
  assert.equal(res.body, 'precached:https://abhyas.test/offline.html');
});

test('a normal page response passes through untouched', async () => {
  const { dispatch } = loadSw({ fetchImpl: async () => new FakeResponse('page', { status: 200 }) });
  await dispatch('install');
  const res = await dispatch('fetch', { request: new FakeRequest('/teacher', { mode: 'navigate' }) });
  assert.equal(res.body, 'page');
});
