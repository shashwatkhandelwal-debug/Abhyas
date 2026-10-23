// State-machine and DOM-effect tests for static/chat.js (run: node --test backend/tests/js).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { El, loadChat, catalogStrings } from './chat_harness.mjs';

const strings = catalogStrings();
const load = (opts = {}) => loadChat({ strings, ...opts });
const iso = (ms) => new Date(ms).toISOString();

// ── message bubble state machine ────────────────────────────────────────────
test('message state: sending -> sent | failed, failed -> retry -> sending, sent is final', () => {
  const { nextMsgState } = load();
  assert.equal(nextMsgState('sending', 'accepted'), 'sent');
  assert.equal(nextMsgState('sending', 'failed'), 'failed');
  assert.equal(nextMsgState('failed', 'retry'), 'sending');
  assert.equal(nextMsgState('failed', 'accepted'), 'sent'); // late success after giving up
  assert.equal(nextMsgState('sent', 'failed'), 'sent'); // a stale failure cannot undo delivery
  assert.equal(nextMsgState('sent', 'retry'), 'sent');
  assert.equal(nextMsgState('sending', 'retry'), 'sending');
});

test('optimistic bubble shows the clock, then the check once accepted', () => {
  const c = load();
  c.renderMessage({ client_msg_id: 'c1', direction: 'in', kind: 'text', text: 'नमस्ते', created_at: iso(c.clock.now) }, true);
  const icon = c.byId['status-c1'] || c.container.querySelector('#status-c1');
  assert.ok(icon.matches('.status-icon.sending'));
  assert.equal(icon.getAttribute('aria-label'), strings.ui_chat_msg_sending);
  c.setMessageState('c1', 'accepted');
  assert.ok(icon.matches('.status-icon.sent'));
  assert.equal(icon.textContent, '✓');
  assert.equal(icon.getAttribute('aria-label'), strings.ui_chat_msg_sent);
});

test('failed bubble is a red tap-to-retry button and retry goes back to the clock', () => {
  const c = load();
  c.renderMessage({ client_msg_id: 'c2', direction: 'in', kind: 'text', text: 'x', created_at: iso(c.clock.now) }, true);
  const icon = c.container.querySelector('#status-c2');
  c.failMessage('c2', 'network');
  assert.ok(icon.matches('.status-icon.failed'));
  assert.equal(icon.textContent, '!');
  assert.equal(icon.getAttribute('role'), 'button');
  assert.equal(icon.getAttribute('tabindex'), '0');
  assert.equal(icon.getAttribute('aria-label'), strings.ui_chat_msg_failed);
  c.setMessageState('c2', 'retry');
  assert.ok(icon.matches('.status-icon.sending'));
  assert.equal(icon.getAttribute('tabindex'), null);
});

// ── outbox: failed after MAX_AUTO_RETRIES, retry reuses the same client_msg_id ─
test('network failures retry with backoff, then show failed; tap retry resends the SAME client_msg_id', async () => {
  const c = load();
  c.net.handler = async () => ({ status: 503, ok: false, json: async () => ({}) });
  await c.handleSendText('अमन, सही उत्तर 16 है');
  await c.flush();
  const id = 'client-1';
  const icon = c.container.querySelector(`#status-${id}`);
  assert.ok(icon.matches('.status-icon.sending'));

  // attempt 1 happened inside handleSendText; walk through the backoff schedule
  for (let i = 0; i < c.MAX_AUTO_RETRIES + 1; i++) {
    await c.advance(c.BACKOFF_STEPS[Math.min(i, c.BACKOFF_STEPS.length - 1)] + 100);
    await c.flush();
  }
  assert.ok(icon.matches('.status-icon.failed'), `expected failed, got ${icon.className}`);
  const attempts = c.fetchCalls.filter((f) => f.url === '/api/chat/text');
  assert.equal(attempts.length, c.MAX_AUTO_RETRIES);
  assert.equal(c.state.failedIds.get(id), 'network');

  // the user taps "!" with the network back
  c.net.handler = async () => ({ status: 202, ok: true, json: async () => ({ message_id: 'srv-1' }) });
  await c.retryMessage(id);
  await c.flush();
  const last = JSON.parse(c.fetchCalls.at(-1).opts.body);
  assert.equal(last.client_msg_id, id);
  assert.ok(icon.matches('.status-icon.sent'));
  assert.equal(c.state.failedIds.has(id), false);
  assert.equal(c.rows().length, 1, 'retry must not create a second bubble');
});

test('a 4xx rejection fails immediately without retry spam', async () => {
  const c = load();
  c.net.handler = async () => ({ status: 403, ok: false, json: async () => ({}) });
  await c.handleSendText('hello');
  await c.flush();
  assert.ok(c.container.querySelector('#status-client-1').matches('.failed'));
  assert.equal(c.fetchCalls.filter((f) => f.url === '/api/chat/text').length, 1);
});

// ── typing indicator ────────────────────────────────────────────────────────
test('typing state machine transitions', () => {
  const { typingNext: next, TYPING_OFF: off, TYPING_TIMEOUT_MS: LIMIT } = load();
  const shown = next(off, { type: 'accepted', speaker: 'ravi', now: 1000 });
  assert.deepEqual([shown.visible, shown.speaker, shown.timedOut], [true, 'ravi', false]);

  assert.equal(next(shown, { type: 'tick', now: 1000 + LIMIT - 1 }), shown, 'not yet');
  const timed = next(shown, { type: 'tick', now: 1000 + LIMIT });
  assert.equal(timed.timedOut, true);
  assert.equal(next(timed, { type: 'pending', now: 99999 }), timed, 'poll keeps the failure hint');

  const replied = next(shown, { type: 'reply', now: 2000 });
  assert.equal(replied.visible, false);
  assert.equal(next(replied, { type: 'pending', now: 2100 }), replied, 'audio-rendering tail must not re-show it');
  assert.equal(next(replied, { type: 'idle', now: 2200 }), off);

  const fresh = next(off, { type: 'pending', now: 5 });
  assert.equal(fresh.visible, true, 'reload while a turn is in flight shows it');
  assert.equal(next(fresh, { type: 'idle', now: 6 }), off);
  const again = next(timed, { type: 'accepted', speaker: null, now: 7 });
  assert.deepEqual([again.visible, again.timedOut], [true, false]);
});

test('guessSpeaker finds the child being addressed', () => {
  const { guessSpeaker } = load();
  assert.equal(guessSpeaker('रवि, तुमने कैसे किया?'), 'ravi');
  assert.equal(guessSpeaker('Aman, sahi answer 16 hai'), 'aman');
  assert.equal(guessSpeaker('प्रिया और अमन'), 'priya');
  assert.equal(guessSpeaker('बच्चों, ध्यान दो'), null);
});

test('typing bubble: named speaker, then 60 s failure hint, hidden on reply', async () => {
  const c = load();
  const bubble = c.byId['pending-bubble'];
  const label = c.byId['pending-text'];
  c.typingEvent({ type: 'accepted', speaker: 'priya' });
  assert.ok(bubble.matches('.pending-bubble.active'));
  assert.equal(label.textContent, strings.ui_chat_typing_priya);
  assert.equal(bubble.getAttribute('aria-busy'), 'true');

  await c.advance(c.TYPING_TIMEOUT_MS + 1000);
  assert.ok(bubble.matches('.timeout'));
  assert.equal(label.textContent, strings.ui_chat_typing_timeout);

  c.typingEvent({ type: 'accepted', speaker: null });
  assert.equal(label.textContent, strings.ui_chat_typing_generic);
  c.typingEvent({ type: 'reply' });
  assert.equal(bubble.matches('.active'), false);
  assert.equal(c.state.typingTimer, null, 'interval is cleaned up');
});

test('new bubbles render above the typing indicator', () => {
  const c = load();
  c.typingEvent({ type: 'accepted', speaker: 'ravi' });
  c.renderMessage({ id: 's1', direction: 'out', speaker: 'abhyas', text: 'हाँ', created_at: iso(c.clock.now) });
  const kids = c.container.children;
  assert.equal(kids.at(-1).id, 'pending-bubble');
  assert.equal(kids.at(-2).id, 'msg-s1');
});

// ── poll + accept race ──────────────────────────────────────────────────────
test('a poll that left before the POST was accepted cannot hide the typing indicator', async () => {
  const c = load();
  let release;
  const gate = new Promise((r) => (release = r));
  c.net.handler = (url) => {
    if (url.startsWith('/api/chat/messages')) {
      return gate.then(() => ({ status: 200, ok: true, json: async () => ({ messages: [], pending: false, server_time: iso(c.clock.now) }) }));
    }
    return Promise.resolve({ status: 202, ok: true, json: async () => ({ message_id: 'srv' }) });
  };
  const polling = c.pollMessages(); // started before the accept
  await c.flush();
  c.clock.now += 50;
  await c.handleSendText('रवि, बताओ');
  await c.flush();
  assert.equal(c.state.typing.visible, true);
  release();
  await polling;
  await c.flush();
  await c.flush();
  assert.equal(c.state.typing.visible, true, 'stale pending=false ignored');
  assert.equal(c.state.isPending, true, 'keeps the fast poll cadence');
});

// ── audio bubble ────────────────────────────────────────────────────────────
test('audio state machine', () => {
  const { audioNext: n } = load();
  assert.equal(n('loading', 'ready'), 'ready');
  assert.equal(n('loading', 'giveup'), 'none');
  assert.equal(n('ready', 'play'), 'loading');
  assert.equal(n('loading', 'playing'), 'playing');
  assert.equal(n('playing', 'waiting'), 'loading');
  assert.equal(n('playing', 'ended'), 'ready');
  assert.equal(n('playing', 'pause'), 'ready');
  assert.equal(n('playing', 'error'), 'error');
  assert.equal(n('error', 'retry'), 'loading');
  assert.equal(n('error', 'playing'), 'error');
});

test('spoken reply shows "आवाज़ आ रही है…" with no player, then a player when the file lands', () => {
  const c = load();
  const base = { id: 'r1', direction: 'out', speaker: 'ravi', kind: 'text', text: 'पैंतालीस!', created_at: iso(c.clock.now) };
  c.renderMessage(base);
  const wrap = c.container.querySelector('.bubble-audio');
  assert.ok(wrap, 'placeholder rendered');
  assert.equal(wrap.getAttribute('data-audio-state'), 'loading');
  assert.equal(wrap.getAttribute('data-has-audio'), 'false');
  assert.equal(wrap._btn.disabled, true, 'never a dead play button');
  assert.equal(wrap._label.textContent, strings.ui_chat_audio_loading);

  c.renderMessage({ ...base, audio_ref: 'abc' }); // text-first, audio attached later
  assert.equal(c.container.querySelectorAll('.bubble-audio').length, 1);
  assert.equal(wrap.getAttribute('data-audio-state'), 'ready');
  assert.equal(wrap._btn.disabled, false);
  assert.equal(wrap._label.textContent, strings.ui_chat_audio_ready);
});

test('audio that never arrives drops the placeholder (text stays, no dead player)', async () => {
  const c = load();
  c.renderMessage({ id: 'r2', direction: 'out', speaker: 'aman', text: 'ठीक है', created_at: iso(c.clock.now) });
  assert.equal(c.container.querySelectorAll('.bubble-audio').length, 1);
  await c.advance(c.AUDIO_WAIT_MS + 100);
  assert.equal(c.container.querySelectorAll('.bubble-audio').length, 0);
  assert.equal(c.container.querySelectorAll('.bubble-text').length, 1);
});

test('no audio placeholder for history, coach text, or lite mode', () => {
  const c = load();
  c.renderMessage({ id: 'h1', direction: 'out', speaker: 'ravi', text: 'पुराना', created_at: iso(c.clock.now - 10 * 60_000) });
  c.renderMessage({ id: 'h2', direction: 'out', speaker: 'coach', text: 'फीडबैक', created_at: iso(c.clock.now) });
  assert.equal(c.container.querySelectorAll('.bubble-audio').length, 0);
  c.state.liteMode = true;
  c.renderMessage({ id: 'h3', direction: 'out', speaker: 'ravi', text: 'लाइट', created_at: iso(c.clock.now) });
  assert.equal(c.container.querySelectorAll('.bubble-audio').length, 0);
});

test('player: tap -> loading -> playing -> error -> tap retries', async () => {
  const c = load();
  c.renderMessage({ id: 'p1', direction: 'out', speaker: 'abhyas', text: 'सुनो', audio_ref: 'ref1', created_at: iso(c.clock.now) });
  const wrap = c.container.querySelector('.bubble-audio');
  assert.equal(wrap.getAttribute('data-audio-state'), 'ready');
  c.onAudioButton(wrap);
  assert.equal(wrap.getAttribute('data-audio-state'), 'loading');
  const audio = c.FakeAudio.instances.at(-1);
  audio.fire('playing');
  assert.equal(wrap.getAttribute('data-audio-state'), 'playing');
  assert.equal(wrap._label.textContent, strings.ui_chat_audio_playing);
  audio.fire('error');
  assert.equal(wrap.getAttribute('data-audio-state'), 'error');
  assert.equal(wrap._label.textContent, strings.ui_chat_audio_error);
  assert.equal(wrap._btn.getAttribute('aria-label'), strings.ui_chat_audio_retry);
  c.onAudioButton(wrap);
  assert.equal(wrap.getAttribute('data-audio-state'), 'loading');
  audio.fire('playing');
  audio.fire('ended');
  assert.equal(wrap.getAttribute('data-audio-state'), 'ready');
});

test('autoplay blocked by the browser leaves a normal ready player (no error shown)', async () => {
  const c = load();
  c.FakeAudio.playResult = 'blocked';
  c.renderMessage({ id: 'a1', direction: 'out', speaker: 'ravi', text: 'हाँ', audio_ref: 'refA', created_at: iso(c.clock.now) });
  const wrap = c.container.querySelector('.bubble-audio');
  await c.advance(400); // autoplay timer fires, play() rejects
  assert.ok(c.FakeAudio.instances.length >= 1, 'autoplay attempted');
  assert.equal(wrap.getAttribute('data-audio-state'), 'ready');
});

test('autoplay that works moves the bubble to loading until the browser reports playing', async () => {
  const c = load();
  c.renderMessage({ id: 'a2', direction: 'out', speaker: 'ravi', text: 'हाँ', audio_ref: 'refB', created_at: iso(c.clock.now) });
  const wrap = c.container.querySelector('.bubble-audio');
  await c.advance(400);
  assert.equal(wrap.getAttribute('data-audio-state'), 'loading');
  c.FakeAudio.instances.at(-1).fire('playing');
  assert.equal(wrap.getAttribute('data-audio-state'), 'playing');
});

// ── mic flow ────────────────────────────────────────────────────────────────
test('mic state machine: idle -> recording -> uploading -> transcribing -> done', () => {
  const { micNext: n } = load();
  assert.equal(n('idle', 'start'), 'recording');
  assert.equal(n('recording', 'cancel'), 'idle');
  assert.equal(n('recording', 'denied'), 'idle');
  assert.equal(n('recording', 'stop'), 'uploading');
  assert.equal(n('uploading', 'accepted'), 'transcribing');
  assert.equal(n('transcribing', 'transcript'), 'done');
  assert.equal(n('uploading', 'failed'), 'failed');
  assert.equal(n('failed', 'retry'), 'uploading');
});

test('timer formats mm:ss', () => {
  const { formatTimer } = load();
  assert.equal(formatTimer(0), '0:00');
  assert.equal(formatTimer(9.9), '0:09');
  assert.equal(formatTimer(65), '1:05');
});

test('voice note bubble: uploading -> transcribing -> transcript replaces it, one bubble', async () => {
  const c = load();
  c.net.handler = async () => ({ status: 202, ok: true, json: async () => ({ message_id: 'srv-a' }) });
  await c.handleSendAudio({ size: 10 }, 4);
  await c.flush();
  const row = c.rows()[0];
  assert.equal(row._phaseEl.textContent, strings.ui_chat_rec_transcribing, 'POST accepted -> transcribing');
  assert.equal(row._textEl.textContent, strings.ui_chat_voice_note.replace('{sec}', '4'));

  c.renderMessage({ id: 'srv-a', client_msg_id: 'client-1', direction: 'in', kind: 'audio', text: null, created_at: iso(c.clock.now) });
  assert.equal(row._phaseEl.textContent, strings.ui_chat_rec_transcribing, 'server copy without transcript yet');
  c.renderMessage({ id: 'srv-a', client_msg_id: 'client-1', direction: 'in', kind: 'audio', text: 'रवि, 52 में से 17 कैसे घटाया?', created_at: iso(c.clock.now) });
  assert.equal(row._textEl.textContent, 'रवि, 52 में से 17 कैसे घटाया?');
  assert.equal(row._phaseEl.textContent, '');
  assert.equal(row.getAttribute('data-phase'), 'done');
  assert.equal(c.rows().length, 1);
});

test('voice note POST failure shows the red ! and clears the status line', async () => {
  const c = load();
  c.net.handler = async () => ({ status: 413, ok: false, json: async () => ({}) });
  await c.handleSendAudio({ size: 10 }, 3);
  await c.flush();
  const row = c.rows()[0];
  assert.ok(c.container.querySelector('#status-client-1').matches('.failed'));
  assert.equal(row._phaseEl.textContent, '');
});

// ── chips ───────────────────────────────────────────────────────────────────
test('quick-reply chips lock after one tap: a double tap sends once, chip shows pressed', () => {
  const c = load();
  let sent = 0;
  c.sandbox.handleSendButton = () => {
    sent += 1;
  };
  c.renderMessage({
    id: 'q1', direction: 'out', speaker: 'abhyas', text: 'चुनें', created_at: iso(c.clock.now),
    buttons: [{ id: 'yes', title_hi: 'हाँ' }, { id: 'no', title_hi: 'नहीं' }],
  });
  const chips = c.container.querySelectorAll('.reply-chip');
  chips[0].onclick();
  chips[0].onclick();
  chips[1].onclick();
  assert.equal(sent, 1);
  assert.ok(chips.every((x) => x.disabled));
  assert.ok(chips[0].matches('.pressed'));
  assert.equal(chips[1].matches('.pressed'), false);
  assert.equal(c.byId['sr-live'].textContent, strings.ui_chat_chip_done);
});

// ── Ask the handbook chips ──────────────────────────────────────────────────
function addHandbookChips(c, chips) {
  const body = c.container.parentNode;
  const section = c.sandbox.document.createElement('section');
  section.id = 'handbook-chips';
  section.setAttribute('data-prefix', 'सवाल:');
  body.appendChild(section);
  return chips.map(({ label, ask }, i) => {
    const b = c.sandbox.document.createElement('button');
    b.className = 'handbook-chip';
    b.setAttribute('data-id', `hb0${i + 1}`);
    if (ask) b.setAttribute('data-text', ask);
    b.textContent = label;
    body.appendChild(b);
    return b;
  });
}

test('handbook chip tap sends its question as typed text, once, and re-enables afterwards', async () => {
  const c = load();
  c.net.handler = async () => ({ status: 202, ok: true, json: async () => ({ message_id: 'srv-1' }) });
  const chips = addHandbookChips(c, [{ label: 'पहला प्रश्न?' }, { label: 'दूसरा प्रश्न?' }]);
  c.setupHandbookChips();
  chips[0].onclick();
  chips[1].onclick(); // a second tap while the first is sending is ignored
  assert.ok(chips.every((x) => x.disabled));
  await c.flush();
  const posts = c.fetchCalls.filter((f) => f.url === '/api/chat/text');
  assert.equal(posts.length, 1);
  assert.equal(JSON.parse(posts[0].opts.body).text, 'सवाल: पहला प्रश्न?');
  assert.equal(c.rows().length, 1, 'one bubble: the question');
  assert.ok(chips.every((x) => !x.disabled));
});

test('English UI chip sends the Hindi question from data-text, not its English label', async () => {
  const c = load();
  c.net.handler = async () => ({ status: 202, ok: true, json: async () => ({ message_id: 'srv-1' }) });
  const [chip] = addHandbookChips(c, [{ label: 'What is reading fluency?', ask: 'सवाल: रवानगी क्या है?' }]);
  c.setupHandbookChips();
  chip.onclick();
  await c.flush();
  const posts = c.fetchCalls.filter((f) => f.url === '/api/chat/text');
  assert.equal(posts.length, 1);
  assert.equal(JSON.parse(posts[0].opts.body).text, 'सवाल: रवानगी क्या है?');
});

test('arriving with ?ask sends that handbook question once; no autosend section sends nothing', async () => {
  const none = load();
  none.setupHandbookChips();
  await none.flush();
  assert.equal(none.fetchCalls.filter((f) => f.url === '/api/chat/text').length, 0);

  const c = load();
  c.net.handler = async () => ({ status: 202, ok: true, json: async () => ({ message_id: 'srv-1' }) });
  const section = c.sandbox.document.createElement('section');
  section.id = 'handbook-chips';
  section.setAttribute('data-autosend', 'सवाल: बच्चों को कहानी कैसे सुनाएँ?');
  c.container.parentNode.appendChild(section);
  c.setupHandbookChips();
  await c.flush();
  const posts = c.fetchCalls.filter((f) => f.url === '/api/chat/text');
  assert.equal(posts.length, 1);
  assert.equal(JSON.parse(posts[0].opts.body).text, 'सवाल: बच्चों को कहानी कैसे सुनाएँ?');
});

// ── connection status bar ───────────────────────────────────────────────────
test('net state machine', () => {
  const { netNext: n } = load();
  assert.equal(n('ok', 'slow'), 'cold');
  assert.equal(n('cold', 'success'), 'ok');
  assert.equal(n('ok', 'fail'), 'cold');
  assert.equal(n('ok', 'offline'), 'offline');
  assert.equal(n('offline', 'online'), 'reconnecting');
  assert.equal(n('reconnecting', 'fail'), 'reconnecting');
  assert.equal(n('reconnecting', 'success'), 'ok');
  assert.equal(n('ok', 'online'), 'ok');
});

test('cold start: no answer for 5 s shows the waking hint, first success hides it', async () => {
  const c = load();
  const bar = c.byId['status-bar'];
  let answer;
  c.net.handler = () => new Promise((r) => (answer = r));
  const req = c.netFetch('/api/chat/messages');
  await c.advance(c.COLD_START_HINT_MS - 100);
  assert.equal(bar.hidden, true, 'not before 5 s');
  await c.advance(200);
  assert.equal(bar.hidden, false);
  assert.equal(bar.textContent, strings.ui_chat_cold_start);
  answer({ status: 200, ok: true });
  await req;
  assert.equal(bar.hidden, true);
});

test('a 502 while the server wakes keeps the hint up; the next 200 clears it', async () => {
  const c = load();
  const bar = c.byId['status-bar'];
  c.net.handler = async () => ({ status: 502, ok: false });
  await c.netFetch('/x');
  assert.equal(bar.hidden, false);
  c.net.handler = async () => ({ status: 200, ok: true });
  await c.netFetch('/x');
  assert.equal(bar.hidden, true);
});

test('offline -> online shows "reconnecting" until a request succeeds', async () => {
  const c = load();
  const bar = c.byId['status-bar'];
  c.navigator.onLine = false;
  c.updateOnlineStatus();
  assert.equal(c.state.net, 'offline');
  c.navigator.onLine = true;
  c.net.handler = async () => ({ status: 200, ok: true, json: async () => ({ messages: [], pending: false }) });
  c.updateOnlineStatus();
  assert.equal(c.state.net, 'reconnecting');
  assert.equal(bar.textContent, strings.ui_chat_reconnecting);
  await c.flush();
  assert.equal(c.state.net, 'ok', 'immediate poll succeeded');
  assert.equal(bar.hidden, true);
});

test('network exception while online is treated as the server being unreachable', async () => {
  const c = load();
  c.net.handler = async () => {
    throw new TypeError('Failed to fetch');
  };
  await assert.rejects(c.netFetch('/x'));
  assert.equal(c.state.net, 'cold');
});

// ── on-demand translation under child / coach / guide bubbles ───────────────
const outMsg = (over = {}) => ({
  id: 'm-1',
  direction: 'out',
  kind: 'text',
  speaker: 'coach',
  text: 'आपने बच्चे से पूछा, बहुत अच्छा।',
  created_at: iso(0),
  ...over,
});

test('translate control appears under child, coach and guide bubbles only', () => {
  const c = load();
  for (const [i, sp] of ['ravi', 'priya', 'aman', 'coach', 'guide', 'model_teacher', 'abhyas'].entries()) {
    c.renderMessage(outMsg({ id: `m-${i}`, speaker: sp }));
  }
  const withBtn = c.container.querySelectorAll('.translate-btn').length;
  assert.equal(withBtn, 6); // everything except the system speaker "abhyas"
  assert.equal(c.container.querySelectorAll('.translate-btn')[0].textContent, strings.ui_chat_translate);
  c.renderMessage(outMsg({ id: 'in-1', direction: 'in', speaker: undefined }), true);
  assert.equal(c.container.querySelectorAll('.translate-btn').length, 6); // never under the teacher's own message
});

test('translate: posts the message id, shows English under the Hindi, second tap hides it', async () => {
  const c = load();
  c.net.handler = async () => ({ status: 200, ok: true, json: async () => ({ text: 'You asked the child. Very good.', cached: false }) });
  c.renderMessage(outMsg());
  const btn = c.container.querySelector('.translate-btn');
  await c.toggleTranslation(btn);
  const call = c.fetchCalls.find((f) => f.url === '/api/chat/translate');
  assert.ok(call, 'translate endpoint called');
  assert.equal(JSON.parse(call.opts.body).message_id, 'm-1');
  const shown = c.container.querySelector('.bubble-translation');
  assert.equal(shown.textContent, 'You asked the child. Very good.');
  assert.equal(shown.lang, 'en');
  assert.equal(btn.textContent, strings.ui_chat_translate_hide);
  assert.equal(c.container.querySelector('.bubble-text').textContent, 'आपने बच्चे से पूछा, बहुत अच्छा।'); // Hindi untouched
  await c.toggleTranslation(btn); // hide: no second request
  assert.equal(c.container.querySelector('.bubble-translation'), null);
  assert.equal(c.fetchCalls.filter((f) => f.url === '/api/chat/translate').length, 1);
});

test('translate: failure shows an inline error with a retry label, then succeeds on retry', async () => {
  const c = load();
  let calls = 0;
  c.net.handler = async () => {
    calls += 1;
    return calls === 1
      ? { status: 502, ok: false, json: async () => ({}) }
      : { status: 200, ok: true, json: async () => ({ text: 'Well done.' }) };
  };
  c.renderMessage(outMsg());
  const btn = c.container.querySelector('.translate-btn');
  await c.toggleTranslation(btn);
  const err = c.container.querySelector('.translate-error');
  assert.equal(err.textContent, strings.ui_chat_translate_error);
  assert.equal(err.getAttribute('role'), 'alert');
  assert.equal(btn.textContent, strings.ui_chat_translate_retry);
  assert.equal(btn.disabled, false);
  await c.toggleTranslation(btn);
  assert.equal(c.container.querySelector('.translate-error'), null);
  assert.equal(c.container.querySelector('.bubble-translation').textContent, 'Well done.');
});

test('translate: a rate-limit response gets its own message', async () => {
  const c = load();
  c.net.handler = async () => ({ status: 429, ok: false, json: async () => ({}) });
  c.renderMessage(outMsg());
  await c.toggleTranslation(c.container.querySelector('.translate-btn'));
  assert.equal(c.container.querySelector('.translate-error').textContent, strings.ui_chat_translate_limit);
});

// ── one-on-one header ───────────────────────────────────────────────────────
function withSceneHeader(c) {
  const mk = (id, parent) => {
    const el = new El('div');
    el.id = id;
    (parent || c.sandbox.document.getElementById('chat-input').parentNode).appendChild(el);
    c.byId[id] = el;
    return el;
  };
  const els = {
    header: mk('scene-header'),
    strip: mk('rehearse-strip'),
    child: mk('sh-child'),
    board: mk('sh-board'),
    turn: mk('sh-turn'),
    steps: mk('sh-steps'),
    cue: mk('sh-cue-text'),
    end: mk('sh-end'),
  };
  els.header.hidden = true;
  return els;
}

const SCENE = {
  mode: 'one_on_one', child_id: 'ravi', child_name: 'रवि', board: '43 − 27',
  turn_label: 'बारी 2/10', cue: 'अपना तरीका बता रहा है', cue_state: 1, turn: 2, max_turns: 10,
};

test('one-on-one header: child, board, turn and engine cue are shown; the group strip is hidden', () => {
  const c = load();
  const h = withSceneHeader(c);
  c.renderSceneHeader(SCENE);
  assert.equal(h.header.hidden, false);
  assert.equal(h.strip.hidden, true);
  assert.equal(h.child.textContent, 'रवि');
  assert.ok(h.child.className.includes('ravi'));
  assert.equal(h.board.textContent, '43 − 27');
  assert.equal(h.turn.textContent, 'बारी 2/10');
  assert.equal(h.cue.textContent, 'अपना तरीका बता रहा है');
  assert.equal(h.steps.dataset.filled, '2'); // cue_state 1 -> two of four steps
  c.renderSceneHeader({ ...SCENE, cue_state: -1, cue: 'पहले उलझन पहचानिए' });
  assert.equal(h.steps.dataset.filled, '0'); // diagnosing: nothing filled yet
  c.renderSceneHeader({ ...SCENE, cue_state: 3 });
  assert.equal(h.steps.dataset.filled, '4');
});

test('one-on-one header disappears when there is no one-on-one scene', () => {
  const c = load();
  const h = withSceneHeader(c);
  c.renderSceneHeader(SCENE);
  c.renderSceneHeader(null);
  assert.equal(h.header.hidden, true);
  assert.equal(h.strip.hidden, false);
});

test('the poll drives the header; typing and message handling are untouched', async () => {
  const c = load();
  const h = withSceneHeader(c);
  c.net.handler = async () => ({
    status: 200, ok: true,
    json: async () => ({ messages: [], pending: false, scene: SCENE, server_time: new Date(c.clock.now).toISOString() }),
  });
  await c.pollMessages();
  assert.equal(h.header.hidden, false);
  assert.equal(h.cue.textContent, SCENE.cue);
  c.net.handler = async () => ({ status: 200, ok: true, json: async () => ({ messages: [], pending: false, scene: null }) });
  await c.pollMessages();
  assert.equal(h.header.hidden, true);
});

test('end-practice button asks for confirmation, then sends the stop word as a message', async () => {
  const c = load();
  const h = withSceneHeader(c);
  c.setupSceneEnd();
  const sent = [];
  c.net.handler = async (url, opts) => {
    sent.push(url);
    return { status: 202, ok: true, json: async () => ({ message_id: 'x', status: 'accepted' }) };
  };
  c.sandbox.window.confirm = () => false;
  h.end._listeners.click();
  await c.flush();
  assert.equal(c.fetchCalls.filter((f) => String(f.url).includes('/chat/text')).length, 0);
  c.sandbox.window.confirm = () => true;
  h.end._listeners.click();
  await c.flush();
  const textPosts = c.fetchCalls.filter((f) => String(f.url).includes('/chat/text'));
  assert.equal(textPosts.length, 1);
  assert.equal(JSON.parse(textPosts[0].opts.body).text, c.t('ui_chat_scene_stop_word'));
});

// ── failure paths: each gives a specific message with a next step ───────────
test('every recorder failure code has its own Hindi message and none is empty', () => {
  const c = load();
  const codes = ['unsupported', 'insecure', 'permission', 'no_mic', 'busy', 'start_failed'];
  const texts = codes.map((code) => c.recorderErrorText(code, 'boom'));
  for (const text of texts) assert.ok(text && !text.includes('undefined'), text);
  assert.equal(new Set(texts).size, codes.length, 'messages must be distinct');
  assert.ok(texts[2].includes('अनुमति'), 'permission message talks about permission');
  // blocked / unsupported / no microphone all tell the teacher they can type instead
  for (const i of [0, 1, 2, 3]) assert.ok(texts[i].includes('लिख'), `next step missing: ${texts[i]}`);
  assert.ok(texts[5].includes('boom'), 'start failure shows the detail');
});

test('gave up sending on the network: status bar says the message is kept, tap ! to resend', async () => {
  const c = load();
  c.net.handler = async () => ({ status: 503, ok: false, json: async () => ({}) });
  await c.handleSendText('नमस्ते');
  await c.flush();
  for (let i = 0; i < c.MAX_AUTO_RETRIES + 1 && !c.state.failedIds.size; i++) {
    await c.advance(c.BACKOFF_STEPS[Math.min(i, c.BACKOFF_STEPS.length - 1)] + 100);
    await c.flush();
  }
  assert.equal(c.state.failedIds.get('client-1'), 'network');
  const bar = c.byId['status-bar'];
  assert.equal(bar.hidden, false);
  assert.equal(bar.textContent, strings.ui_chat_send_failed_network);
});

test('a server rejection tells the teacher to refresh or type instead', async () => {
  const c = load();
  c.net.handler = async () => ({ status: 403, ok: false, json: async () => ({}) });
  await c.handleSendText('नमस्ते');
  await c.flush();
  assert.equal(c.byId['status-bar'].textContent, strings.ui_chat_send_failed_rejected);
});

test('a voice note that fails to upload also shows the failure notice', async () => {
  const c = load();
  c.net.handler = async () => ({ status: 413, ok: false, json: async () => ({}) });
  await c.handleSendAudio({ size: 10 }, 3);
  await c.flush();
  assert.equal(c.byId['status-bar'].textContent, strings.ui_chat_send_failed_rejected);
});

test('lite mode that cannot reach the server says so instead of failing silently', async () => {
  const c = load();
  c.net.handler = async () => {
    throw new Error('offline');
  };
  await c.toggleLiteMode(true);
  assert.equal(c.byId['status-bar'].textContent, strings.ui_chat_lite_save_failed);
});

test('the voice-too-short message tells the teacher how long to speak', () => {
  assert.ok(strings.ui_chat_rec_too_short.includes('1 सेकंड'));
});
