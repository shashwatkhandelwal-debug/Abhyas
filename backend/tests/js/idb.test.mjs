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
