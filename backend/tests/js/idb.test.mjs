// IndexedDB self-healing and the "never an endless clock" guarantees of static/chat.js.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadChat, catalogStrings, makeIdbState } from './chat_harness.mjs';

const strings = catalogStrings();
const load = (opts = {}) => loadChat({ strings, ...opts });
const iso = (ms) => new Date(ms).toISOString();
const textPosts = (c) => c.fetchCalls.filter((f) => f.url === '/api/chat/text');
const accept = (c) => {
  c.net.handler = async () => ({ status: 200, ok: true, json: async () => ({ message_id: 'srv-1' }) });
};

test('DB_VERSION is 2', () => {
  assert.equal(load().DB_VERSION, 2);
});

test('a v1 database with no stores is healed and the outbox works', async () => {
  const idb = makeIdbState({ version: 1, stores: [] });
  const c = load({ idb });
  await c.saveToOutbox({ client_msg_id: 'a', kind: 'text', text: 'x', timestamp: 1 });
  assert.deepEqual(Object.keys(idb.data).sort(), ['messages_cache', 'outbox']);
  assert.equal(idb.data.outbox.size, 1, 'persisted in IndexedDB, not only in memory');
  assert.equal((await c.getPendingOutboxItems()).length, 1);
});

test('stores still missing after the upgrade are healed by one delete + reopen', async () => {
  const idb = makeIdbState({ version: 2, stores: [] });
  const c = load({ idb });
  await c.saveToOutbox({ client_msg_id: 'a', kind: 'text', text: 'x', timestamp: 1 });
  assert.equal(idb.deletes, 1);
  assert.equal(idb.data.outbox.size, 1);
});

test('a throwing outbox still sends over the network and the clock becomes the sent check', async () => {
  const idb = makeIdbState();
  idb.failStores.add('outbox');
  const c = load({ idb });
  accept(c);
  await c.handleSendText('नमस्ते');
  await c.flush();
  assert.equal(textPosts(c).length, 1);
  assert.equal([...c.state.msgStates.values()][0], 'sent');
});

test('a stuck browser database: the send still goes out after the open timeout', async () => {
  const idb = makeIdbState();
  idb.holdOpenForever = true;
  const c = load({ idb });
  accept(c);
  const sending = c.handleSendText('नमस्ते');
  await c.advance(2100);
  await sending;
  await c.flush();
  assert.equal(textPosts(c).length, 1);
});

test('a failed send shows the retry mark and tapping retry works with a broken outbox', async () => {
  const idb = makeIdbState();
  idb.failStores.add('outbox');
  const c = load({ idb });
  c.net.handler = async () => {
    throw new TypeError('Failed to fetch');
  };
  await c.handleSendText('नमस्ते');
  await c.advance(60000);
  const id = [...c.state.msgStates.keys()][0];
  assert.equal(c.state.msgStates.get(id), 'failed');
  accept(c);
  await c.retryMessage(id);
  await c.flush();
  assert.equal(c.state.msgStates.get(id), 'sent');
});

test('cache failures are non-fatal', async () => {
  const idb = makeIdbState();
  idb.failStores.add('messages_cache');
  const c = load({ idb });
  await c.cacheMessages([{ id: 'm1', created_at: iso(0) }]); // resolves, does not throw
  assert.equal(idb.data.messages_cache.size, 0);
  accept(c);
  await c.handleSendText('hi');
  await c.flush();
  assert.equal(textPosts(c).length, 1);
});

test('logout clears the stores (no delete), closes the connection, and the next login works', async () => {
  const idb = makeIdbState();
  const c = load({ idb });
  await c.saveToOutbox({ client_msg_id: 'a', kind: 'text', text: 'x', timestamp: 1 });
  await c.cacheMessages([{ id: 'm1', created_at: iso(0) }]);
  const p = c.clearLocalState();
  await c.flush();
  await p;
  assert.equal(idb.deletes, 0);
  assert.equal(idb.conns.size, 0, 'connection closed');
  assert.equal(idb.data.outbox.size + idb.data.messages_cache.size, 0);
  const next = load({ idb });
  accept(next);
  await next.handleSendText('hi');
  await next.flush();
  assert.equal(textPosts(next).length, 1);
  assert.equal(idb.data.outbox.size, 0, 'sent and removed');
});

test('another tab that never closes its connection does not break logout or the next open', async () => {
  const idb = makeIdbState();
  const c = load({ idb });
  await c.saveToOutbox({ client_msg_id: 'a', kind: 'text', text: 'x', timestamp: 1 });
  const otherTab = load({ idb });
  await otherTab.openDatabase();
  [...idb.conns].forEach((x) => (x.ignoreVersionChange = true));
  const p = c.clearLocalState();
  await c.flush();
  await p;
  assert.equal(idb.data.outbox.size, 0);
  const reopened = load({ idb });
  accept(reopened);
  await reopened.handleSendText('hi');
  await reopened.flush();
  assert.equal(textPosts(reopened).length, 1);
});

test('a blocked delete (broken stores, another tab holding the database) does not break the send', async () => {
  const idb = makeIdbState({ version: 2, stores: [] });
  const held = load({ idb }).sandbox.indexedDB.open('abhyas_chat_db', 2);
  held.onsuccess = () => [...idb.conns].forEach((x) => (x.ignoreVersionChange = true));
  const c = load({ idb });
  accept(c);
  const sending = c.handleSendText('hi');
  await c.advance(2100);
  await sending;
  await c.flush();
  assert.equal(textPosts(c).length, 1);
});

test('logout while the outbox is memory-only still empties it', async () => {
  const idb = makeIdbState();
  idb.failStores.add('outbox');
  const c = load({ idb });
  await c.saveToOutbox({ client_msg_id: 'a', kind: 'text', text: 'x', timestamp: 1 });
  assert.equal((await c.getPendingOutboxItems()).length, 1);
  const p = c.clearLocalState();
  await c.flush();
  await p;
  assert.equal((await c.getPendingOutboxItems()).length, 0);
});

// ── fix6: one browser, two accounts ────────────────────────────────────────────────────────
const asUser = (id) => `abhyas_session=x; abhyas_uid=${id}`;
const listFor = async (c) => JSON.stringify((await c.getPendingOutboxItems()).map((i) => i.client_msg_id));

test('fix6: rows are tagged with the account and the outbox reads only its own', async () => {
  const idb = makeIdbState();
  const demo2 = load({ idb, cookie: asUser('u-demo2') });
  await demo2.saveToOutbox({ client_msg_id: 'd2', kind: 'text', text: 'x', timestamp: 1 });
  await demo2.cacheMessages([{ id: 'm-d2', created_at: iso(0), text: 'demo2 only' }]);
  assert.equal(idb.data.outbox.get('d2').uid, 'u-demo2');
  assert.equal(idb.data.messages_cache.get('m-d2').uid, 'u-demo2');
  const demo1 = load({ idb, cookie: asUser('u-demo1') }); // same IndexedDB, other account
  assert.equal(await listFor(demo1), '[]');
  assert.equal(await listFor(demo2), '["d2"]');
});

test('fix6: demo2 chats, logs out, demo1 logs in on the same browser: nothing of demo2 is left', async () => {
  const idb = makeIdbState();
  const storage = new Map();
  const demo2 = load({ idb, storage, cookie: asUser('u-demo2') });
  await demo2.syncAccount();
  await demo2.cacheMessages([{ id: 'm1', created_at: iso(0), text: 'demo2 chat' }]);
  await demo2.saveToOutbox({ client_msg_id: 'd2', kind: 'text', text: 'x', timestamp: 1 });
  await demo2.clearLocalState(); // every logout path ends here
  assert.equal(idb.data.messages_cache.size + idb.data.outbox.size, 0);
  assert.equal(storage.has('abhyas_uid'), false);
  const demo1 = load({ idb, storage, cookie: asUser('u-demo1') });
  await demo1.syncAccount();
  await demo1.cacheMessages([{ id: 'm2', created_at: iso(1), text: 'demo1 chat' }]);
  assert.equal(JSON.stringify([...idb.data.messages_cache.values()].map((m) => m.text)), '["demo1 chat"]');
  assert.equal(storage.get('abhyas_uid'), 'u-demo1');
});

test('fix6: a different account found at page load (no logout seen, e.g. session expiry) clears both stores', async () => {
  const idb = makeIdbState();
  const storage = new Map();
  const demo2 = load({ idb, storage, cookie: asUser('u-demo2') });
  await demo2.syncAccount();
  await demo2.cacheMessages([{ id: 'm1', created_at: iso(0), text: 'demo2 chat' }]);
  await demo2.saveToOutbox({ client_msg_id: 'd2', kind: 'text', text: 'x', timestamp: 1 });
  const demo1 = load({ idb, storage, cookie: asUser('u-demo1') });
  await demo1.syncAccount();
  assert.equal(idb.data.messages_cache.size + idb.data.outbox.size, 0);
  assert.equal(storage.get('abhyas_uid'), 'u-demo1');
});

test('fix6: the same account reloading keeps its stores', async () => {
  const idb = makeIdbState();
  const storage = new Map();
  const first = load({ idb, storage, cookie: asUser('u-demo2') });
  await first.syncAccount();
  await first.cacheMessages([{ id: 'm1', created_at: iso(0), text: 'mine' }]);
  const again = load({ idb, storage, cookie: asUser('u-demo2') });
  await again.syncAccount();
  assert.equal(idb.data.messages_cache.size, 1);
});

test('fix6: a 401 from the server (session over) wipes the local copy and goes to /login', async () => {
  const idb = makeIdbState();
  const storage = new Map();
  const c = load({ idb, storage, cookie: asUser('u-demo2') });
  await c.syncAccount();
  await c.cacheMessages([{ id: 'm1', created_at: iso(0), text: 'mine' }]);
  c.net.handler = async () => ({ status: 401, ok: false, json: async () => ({}) });
  await c.netFetch('/api/chat/poll');
  await c.advance(2000);
  assert.equal(idb.data.messages_cache.size, 0);
  assert.equal(storage.has('abhyas_uid'), false);
  assert.equal(c.sandbox.window.location.href, '/login');
});

test('fix6: another account at page load also drops the cached audio of the first one', async () => {
  const deleted = [];
  const storage = new Map();
  const wipe = (c) => (c.sandbox.window.caches = c.sandbox.caches = { delete: async (n) => (deleted.push(n), true) });
  const demo2 = load({ storage, cookie: asUser('u-demo2') });
  wipe(demo2);
  await demo2.syncAccount();
  deleted.length = 0;
  const demo1 = load({ storage, cookie: asUser('u-demo1') });
  wipe(demo1);
  await demo1.syncAccount();
  assert.deepEqual([...deleted], ['abhyas-audio-v1']);
});
