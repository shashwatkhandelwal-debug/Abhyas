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

test('a poll that comes back while the message is still on its way cannot hide the typing label', async () => {
  const c = load({ strings: { ui_chat_typing_handbook: 'Looking in the handbook…' } });
  let acceptPost;
  const posted = new Promise((r) => (acceptPost = r));
  c.net.handler = (url) =>
    url.startsWith('/api/chat/messages')
      ? Promise.resolve({ status: 200, ok: true, json: async () => ({ messages: [], pending: false }) })
      : posted.then(() => ({ status: 202, ok: true, json: async () => ({ message_id: 'srv' }) }));
  await c.handleSendText('सवाल: कुछ', 'Looking in the handbook…');
  await c.flush(); // the immediate poll answers "nothing pending" before the POST is accepted
  assert.equal(c.state.typing.visible, true);
  assert.equal(c.byId['pending-text'].textContent, 'Looking in the handbook…');
  acceptPost();
  await c.flush();
  assert.equal(c.state.typing.label, 'Looking in the handbook…', 'label kept through the accept');
});

test('a message that fails to send clears the typing label it started', async () => {
  const c = load({ strings: { ui_chat_typing_handbook: 'Looking in the handbook…' } });
  c.net.handler = async () => ({ status: 403, ok: false, json: async () => ({}) });
  await c.handleSendText('सवाल: कुछ', 'Looking in the handbook…');
  await c.flush();
  assert.equal(c.state.typing.visible, false);
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

const CHIP_STRINGS = {
  ui_chat_msg_sending: 'Sending…',
  ui_chat_msg_sent: 'Sent',
  ui_chat_typing_handbook: 'Looking in the handbook…',
};

test('handbook chip tap: question bubble and typing label at once, Sending… then a tick, then back', async () => {
  const c = load({ strings: CHIP_STRINGS });
  c.net.handler = async (url) =>
    url.startsWith('/api/chat/messages')
      ? { status: 200, ok: true, json: async () => ({ pending: true, messages: [] }) }
      : { status: 202, ok: true, json: async () => ({ message_id: 'srv-1' }) };
  const chips = addHandbookChips(c, [{ label: 'पहला प्रश्न?' }, { label: 'दूसरा प्रश्न?' }]);
  c.setupHandbookChips();
  chips[0].onclick();
  chips[1].onclick(); // a second tap while the first is sending is ignored
  assert.ok(chips.every((x) => x.disabled));
  // before any network answer: the question bubble, the chip's "Sending…" and the typing label
  assert.equal(chips[0].textContent, 'Sending…');
  assert.equal(c.rows().length, 1, 'one bubble: the question');
  assert.equal(c.byId['pending-text'].textContent, 'Looking in the handbook…');
  assert.ok(c.byId['pending-bubble'].classList.contains('active'));
  await c.flush();
  const posts = c.fetchCalls.filter((f) => f.url === '/api/chat/text');
  assert.equal(posts.length, 1);
  assert.equal(JSON.parse(posts[0].opts.body).text, 'सवाल: पहला प्रश्न?');
  await c.advance(300); // accepted: a tick on the chip
  assert.equal(chips[0].textContent, '✓ Sent');
  assert.ok(chips[0].classList.contains('sent'));
  assert.equal(c.byId['pending-text'].textContent, 'Looking in the handbook…', 'label survives the accept');
  await c.advance(2000);
  assert.equal(chips[0].textContent, 'पहला प्रश्न?');
  assert.ok(chips.every((x) => !x.disabled));
});

test('handbook chip: a send that never leaves the phone re-enables the chip and clears nothing wrongly', async () => {
  const c = load({ strings: CHIP_STRINGS, online: false });
  const chips = addHandbookChips(c, [{ label: 'पहला प्रश्न?' }]);
  c.setupHandbookChips();
  chips[0].onclick();
  await c.advance(9000); // offline: the settle wait gives up after CHIP_SETTLE_MAX_MS
  assert.equal(chips[0].textContent, 'पहला प्रश्न?');
  assert.ok(!chips[0].disabled);
  assert.equal(c.rows().length, 1, 'the question stays as a bubble with its clock');
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

// ── scene bar ───────────────────────────────────────────────────────────────
function withSceneBar(c) {
  const mk = (id, tag = 'div') => {
    const el = new El(tag);
    el.id = id;
    c.sandbox.document.getElementById('chat-input').parentNode.appendChild(el);
    c.byId[id] = el;
    return el;
  };
  const els = {
    bar: mk('scene-bar'),
    title: mk('sb-title'),
    turn: mk('sb-turn'),
    board: mk('sb-board'),
    manip: mk('sb-manipulatives', 'span'),
    kids: mk('sb-children'),
    end: mk('sh-end'),
    input: c.sandbox.document.getElementById('chat-input'),
  };
  els.bar.hidden = true;
  els.input.value = '';
  return els;
}

const SCENE = {
  mode: 'one_on_one', child_id: 'ravi', child_name: 'रवि', title: 'रवि से आमने-सामने बात',
  board: '43 − 27', turn_label: 'आपकी बारी 2/10', turn: 2, max_turns: 10, children: [],
};
const GROUP = {
  mode: 'group', title: 'तीनों बच्चों के साथ', board: '52 − 17', turn_label: 'आपकी बारी 1/8', turn: 1, max_turns: 8,
  children: [{ id: 'ravi', name: 'रवि' }, { id: 'priya', name: 'प्रिया' }, { id: 'aman', name: 'अमन' }],
};

test('one-on-one scene bar: title, board and turn; no children to switch to, nothing about the child inside', () => {
  const c = load();
  const h = withSceneBar(c);
  c.renderSceneHeader(SCENE);
  assert.equal(h.bar.hidden, false);
  assert.equal(h.title.textContent, 'रवि से आमने-सामने बात');
  assert.equal(h.board.textContent, '43 − 27');
  assert.equal(h.turn.textContent, 'आपकी बारी 2/10');
  assert.equal(h.kids.hidden, true);
  assert.equal(h.kids.children.length, 0);
});

test('group scene bar lists the three children; a name tap puts the name in the input', () => {
  const c = load();
  const h = withSceneBar(c);
  c.renderSceneHeader(GROUP);
  assert.equal(h.kids.hidden, false);
  assert.deepEqual(h.kids.children.map((k) => k.textContent), ['रवि', 'प्रिया', 'अमन']);
  c.addressChild('प्रिया');
  assert.equal(h.input.value, 'प्रिया, ');
  c.addressChild('प्रिया'); // already addressed: not doubled
  assert.equal(h.input.value, 'प्रिया, ');
  h.input.value = 'तुमने कैसे किया?';
  c.addressChild('अमन');
  assert.equal(h.input.value, 'अमन, तुमने कैसे किया?');
  c.renderSceneHeader(SCENE); // a one-on-one scene follows: the children go away
  assert.equal(h.kids.hidden, true);
  assert.equal(h.kids.children.length, 0);
});

test('scene bar disappears when no scene is running', () => {
  const c = load();
  const h = withSceneBar(c);
  c.renderSceneHeader(SCENE);
  c.renderSceneHeader(null);
  assert.equal(h.bar.hidden, true);
});

test('the poll drives the scene bar and the step header; typing and message handling are untouched', async () => {
  const c = load();
  const h = withSceneBar(c);
  const title = c.sandbox.document.createElement('span');
  title.id = 'header-move-title';
  c.container.parentNode.appendChild(title);
  const step = c.sandbox.document.createElement('span');
  step.id = 'header-step';
  c.container.parentNode.appendChild(step);
  const view = { move_title: 'हासिल वाला घटाव: बंडल खोलकर', step_label: 'चरण 4 / 7: अभ्यास' };
  c.net.handler = async () => ({
    status: 200, ok: true,
    json: async () => ({ messages: [], pending: false, scene: SCENE, view, server_time: new Date(c.clock.now).toISOString() }),
  });
  await c.pollMessages();
  assert.equal(h.bar.hidden, false);
  assert.equal(h.title.textContent, SCENE.title);
  assert.equal(title.textContent, view.move_title);
  assert.equal(step.textContent, view.step_label);
  c.net.handler = async () => ({ status: 200, ok: true, json: async () => ({ messages: [], pending: false, scene: null }) });
  await c.pollMessages();
  assert.equal(h.bar.hidden, true);
});

test('end-practice button asks for confirmation, then sends the stop word as a message', async () => {
  const c = load();
  const h = withSceneBar(c);
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

// ── what to do now ──────────────────────────────────────────────────────────
function withNextCard(c) {
  const mk = (id, tag = 'div') => {
    const el = new El(tag);
    el.id = id;
    c.sandbox.document.getElementById('chat-input').parentNode.appendChild(el);
    c.byId[id] = el;
    return el;
  };
  const els = { card: mk('next-card'), text: mk('next-text', 'span'), suggest: mk('next-suggest', 'button') };
  els.card.hidden = true;
  c.sandbox.document.getElementById('chat-input').value = '';
  return els;
}

const HINT = { key: 'hint_scene_one', text: 'रवि से पूछें कि उसने यह कैसे किया।', suggest: 'रवि, तुमने 43 में से 27 कैसे घटाया?' };

test('the what-to-do line shows its text and a suggested line', () => {
  const c = load();
  const n = withNextCard(c);
  c.renderHint(HINT);
  assert.equal(n.card.hidden, false);
  assert.equal(n.text.textContent, HINT.text);
  assert.equal(n.suggest.hidden, false);
  assert.equal(n.suggest.textContent, HINT.suggest);
  c.renderHint({ key: 'hint_learn', text: 'इसे पढ़ें', suggest: null });
  assert.equal(n.suggest.hidden, true);
  c.renderHint(null);
  assert.equal(n.card.hidden, true);
});

test('tapping the suggested line sends on tap like sample chips', async () => {
  const c = load();
  const n = withNextCard(c);
  c.net.handler = async () => ({ status: 202, ok: true, json: async () => ({ message_id: 'srv' }) });
  c.renderHint(HINT);
  c.documentListeners.click({ target: n.suggest });
  await c.flush();
  const textCalls = c.fetchCalls.filter((f) => f.url === '/api/chat/text');
  assert.equal(textCalls.length, 1);
  assert.deepEqual(JSON.parse(textCalls[0].opts.body).text, HINT.suggest);
  assert.equal(n.card.hidden, true);
});

test('once she has sent something the line stays hidden until the guidance changes', async () => {
  const c = load();
  const n = withNextCard(c);
  c.net.handler = async () => ({ status: 202, ok: true, json: async () => ({ message_id: 'srv' }) });
  c.renderHint(HINT);
  await c.handleSendText('रवि, तुमने कैसे किया?');
  assert.equal(n.card.hidden, true, 'hidden at once on send');
  c.renderHint(HINT); // the next poll still says the same thing
  assert.equal(n.card.hidden, true, 'stays hidden for the same key');
  c.renderHint({ key: 'hint_feedback', text: 'सुझाव पढ़ें।', suggest: null });
  assert.equal(n.card.hidden, false, 'a new step shows its own line');
});

test('a button tap or a voice note also counts as sending', async () => {
  const c = load();
  const n = withNextCard(c);
  c.net.handler = async () => ({ status: 202, ok: true, json: async () => ({ message_id: 'srv' }) });
  c.renderHint({ key: 'hint_learn', text: 'इसे पढ़ें', suggest: null });
  c.hintSent();
  assert.equal(n.card.hidden, true);
  c.renderHint({ key: 'hint_learn', text: 'इसे पढ़ें', suggest: null });
  assert.equal(n.card.hidden, true);
});

test('the poll carries the line: shown, then replaced by the next step\'s', async () => {
  const c = load();
  const n = withNextCard(c);
  const reply = (hint) => async () => ({
    status: 200, ok: true,
    json: async () => ({ messages: [], pending: false, scene: null, view: { move_title: 'x', step_label: 'y', hint } }),
  });
  c.net.handler = reply(HINT);
  await c.pollMessages();
  assert.equal(n.text.textContent, HINT.text);
  c.net.handler = reply(null);
  await c.pollMessages();
  assert.equal(n.card.hidden, true);
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

test('slow network banner does NOT appear on slow first load alone', () => {
  const c = load();
  const banner = c.byId['network-banner'];
  // First load: request latency > 8000ms (e.g. server cold start)
  c.recordRequestLatency(9500);
  assert.equal(c.isSlowNetwork(), false);
  assert.equal(banner.classList.contains('slow'), false);
  assert.equal(banner.style.display || 'none', 'none');
});

test('slow network banner appears on genuinely slow network (3 slow requests or connection effectiveType 2g/saveData)', () => {
  const c = load();
  const banner = c.byId['network-banner'];

  // Case 1: Across several requests (> 8000ms across 3 subsequent requests)
  c.recordRequestLatency(9500); // request 1: first load, ignored
  c.recordRequestLatency(8500); // request 2: slow 1
  assert.equal(c.isSlowNetwork(), false);
  c.recordRequestLatency(8500); // request 3: slow 2
  assert.equal(c.isSlowNetwork(), false);
  c.recordRequestLatency(9000); // request 4: slow 3 -> threshold reached!
  assert.equal(c.isSlowNetwork(), true);
  assert.ok(banner.classList.contains('slow'));
  assert.equal(banner.style.display, 'block');

  // Fast request resets consecutive slow count
  c.recordRequestLatency(300);
  assert.equal(c.state.slowRequestCount, 0);

  // Case 2: navigator.connection 2g / slow-2g or saveData
  c.navigator.connection = { effectiveType: '2g', saveData: false };
  assert.equal(c.isSlowNetwork(), true);
  c.recordRequestLatency(200); // even with fast latency, connection is 2g
  assert.ok(banner.classList.contains('slow'));

  c.navigator.connection = { effectiveType: '4g', saveData: true };
  assert.equal(c.isSlowNetwork(), true);
});


test('btn_replay is hidden unless audio is attached to the message', async () => {
  const c = load();
  const msgNoAudio = {
    id: 'msg-1',
    direction: 'out',
    kind: 'buttons',
    text: 'तरीका सीखें',
    audio_ref: null,
    buttons: [
      { id: 'btn_understood', title_hi: 'समझ गई, आगे' },
      { id: 'btn_replay', title_hi: 'फिर से सुनें' },
    ],
  };
  c.renderMessage(msgNoAudio);
  const chipsNoAudio = c.sandbox.document.querySelectorAll('.reply-chip');
  assert.equal(chipsNoAudio.length, 1);
  assert.equal(chipsNoAudio[0].textContent, 'समझ गई, आगे');

  const msgWithAudio = {
    id: 'msg-2',
    direction: 'out',
    kind: 'buttons',
    text: 'तरीका सीखें',
    audio_ref: 'audio_123',
    buttons: [
      { id: 'btn_understood', title_hi: 'समझ गई, आगे' },
      { id: 'btn_replay', title_hi: 'फिर से सुनें' },
    ],
  };
  c.renderMessage(msgWithAudio);
  const allChips = c.sandbox.document.querySelectorAll('.reply-chip');
  // 1 from first message + 2 from second message = 3
  assert.equal(allChips.length, 3);
});

// ── coach evidence quote badge ──────────────────────────────────────────────
test('coach evidence quote badge strips prefix and displays badge', () => {
  const c = load();
  const text = 'शानदार! आपके शब्द: «रवि, 10 के बंडल बनाओ» से बच्चे को समझ आया।';
  c.renderMessage({
    id: 'coach-1',
    direction: 'out',
    speaker: 'coach',
    text: text,
  });
  const row = c.container.querySelector('#msg-coach-1');
  const badge = row.querySelector('.evidence-quote-badge');
  assert.ok(badge, 'Badge should be present');
  const tag = badge.querySelector('.quote-tag');
  assert.equal(tag.textContent, strings.ui_chat_quote_tag || 'आपकी कही बात');
  const content = badge.querySelector('.quote-content');
  assert.equal(content.textContent, '«रवि, 10 के बंडल बनाओ»');

  // Verify "आपके शब्द:" was stripped and not duplicated in bubble text before badge
  const textEl = row.querySelector('.bubble-text');
  assert.ok(!textEl.textContent.includes('आपके शब्द:'), 'Preceding prefix should be consumed');
});

test('coach evidence quote badge escapes XSS payloads like <img onerror=...>', () => {
  const c = load();
  const text = 'बहुत बढ़िया! आपके शब्द: «रवि, <img onerror=alert(1)> बंडल बनाओ» सही थे।';
  c.renderMessage({
    id: 'coach-2',
    direction: 'out',
    speaker: 'coach',
    text: text,
  });
  const row = c.container.querySelector('#msg-coach-2');
  const badge = row.querySelector('.evidence-quote-badge');
  assert.ok(badge);
  const content = badge.querySelector('.quote-content');
  assert.equal(content.textContent, '«रवि, <img onerror=alert(1)> बंडल बनाओ»');
  assert.equal(row.querySelector('img'), null, 'No <img> tag should be created in the DOM');
});

test('coach evidence quote preserves newlines and citation chips', () => {
  const c = load();
  const text = 'लाइन 1\nलाइन 2 आपके शब्द: «बंडल बनाओ»\nलाइन 3';
  c.renderMessage({
    id: 'coach-3',
    direction: 'out',
    speaker: 'coach',
    text: text,
    citations: [{ chunk_id: 'c1', line_hi: 'हैंडबुक पृष्ठ 24' }],
  });
  const row = c.container.querySelector('#msg-coach-3');
  const textEl = row.querySelector('.bubble-text');
  assert.ok(textEl.textContent.includes('\n'), 'Newlines must be preserved in text content');
  const chip = row.querySelector('.source-chip');
  assert.ok(chip, 'Citation chip must be rendered');
  assert.equal(chip.textContent, 'हैंडबुक पृष्ठ 24');
});

test('evidence quote badge only applies to coach messages', () => {
  const c = load();
  const text = 'मैं कहता हूँ «रवि, सही उत्तर 16 है»';
  c.renderMessage({
    id: 'child-1',
    direction: 'out',
    speaker: 'ravi',
    text: text,
  });
  const row = c.container.querySelector('#msg-child-1');
  const badge = row.querySelector('.evidence-quote-badge');
  assert.equal(badge, null, 'Non-coach messages must NOT have quote badge');
});

// ── board manipulatives ─────────────────────────────────────────────────────
test('board manipulatives render drawn bundles and sticks with aria-label', () => {
  const c = load();
  const h = withSceneBar(c);
  c.renderSceneHeader({
    ...SCENE,
    manipulatives: {
      bundles: 4,
      sticks: 3,
      regrouped: false,
      aria_label: '4 बंडल और 3 तीलियाँ',
    },
  });
  assert.equal(h.manip.hidden, false);
  assert.equal(h.manip.getAttribute('role'), 'img');
  assert.equal(h.manip.getAttribute('aria-label'), '4 बंडल और 3 तीलियाँ');
  const bundles = h.manip.querySelectorAll('.drawn-bundle');
  const sticks = h.manip.querySelectorAll('.drawn-stick');
  assert.equal(bundles.length, 4);
  assert.equal(sticks.length, 3);
  assert.equal(h.manip.classList.contains('regrouped'), false);
});

test('board manipulatives render regrouped state (unpacked bundle into 10 sticks)', () => {
  const c = load();
  const h = withSceneBar(c);
  c.renderSceneHeader({
    ...SCENE,
    manipulatives: {
      bundles: 3,
      sticks: 13,
      regrouped: true,
      aria_label: '3 बंडल और 13 तीलियाँ (1 बंडल खुला)',
    },
  });
  assert.equal(h.manip.hidden, false);
  assert.equal(h.manip.getAttribute('aria-label'), '3 बंडल और 13 तीलियाँ (1 बंडल खुला)');
  const bundles = h.manip.querySelectorAll('.drawn-bundle');
  const sticks = h.manip.querySelectorAll('.drawn-stick');
  assert.equal(bundles.length, 3);
  assert.equal(sticks.length, 13);
  assert.equal(h.manip.classList.contains('regrouped'), true);
});

test('board manipulatives hide when problem has no manipulatives (null)', () => {
  const c = load();
  const h = withSceneBar(c);
  c.renderSceneHeader({
    ...SCENE,
    manipulatives: null,
  });
  assert.equal(h.manip.hidden, true);
});

// ── evaluator fast-track tray ───────────────────────────────────────────────
function withFastTrackTray(c) {
  const doc = c.sandbox.document;
  const mk = (id, tag = 'button') => {
    const el = doc.createElement(tag);
    el.id = id;
    c.byId[id] = el;
    return el;
  };
  const tray = doc.createElement('details');
  tray.className = 'fast-track-tray';
  tray.id = 'fast-track-tray';
  tray.open = true;
  c.byId['fast-track-tray'] = tray;

  const a1 = mk('ft-chip-a1');
  a1.className = 'ft-chip';
  a1.dataset.action = 'a1';
  a1.disabled = true;

  const a2 = mk('ft-chip-a2');
  a2.className = 'ft-chip';
  a2.dataset.action = 'a2';
  a2.dataset.text = 'अब 61 में से 28 घटाओ';

  const b = mk('ft-chip-b');
  b.className = 'ft-chip';
  b.dataset.action = 'b';
  b.dataset.text = 'चलो 43 में से 27 फिर से करते हैं: देखो, 4 बंडल और 3 खुली तीलियाँ हैं, 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो।';

  const ch_c = mk('ft-chip-c');
  ch_c.className = 'ft-chip';
  ch_c.dataset.action = 'c';
  ch_c.dataset.text = 'सवाल: उल्टी गिनती करके घटाव कैसे सिखाएँ?';

  tray.appendChild(a1);
  tray.appendChild(a2);
  tray.appendChild(b);
  tray.appendChild(ch_c);
  return { tray, a1, a2, b, c: ch_c };
}

test('Fast-Track chip A1 computes dynamic answer from subtraction problem and disables when not subtraction', () => {
  const c = load();
  const t = withFastTrackTray(c);

  // 1. Subtraction 43 - 27
  c.renderSceneHeader({
    ...SCENE,
    item: { type: 'sub', a: 43, b: 27 },
  });
  assert.equal(c.getChipA1Text(), 'रवि, सही उत्तर 16 है');
  assert.equal(t.a1.disabled, false);
  assert.equal(t.a1.dataset.text, 'रवि, सही उत्तर 16 है');

  // 2. Subtraction 61 - 28
  c.renderSceneHeader({
    ...SCENE,
    item: { type: 'sub', a: 61, b: 28 },
  });
  assert.equal(c.getChipA1Text(), 'रवि, सही उत्तर 33 है');
  assert.equal(t.a1.disabled, false);

  // 3. Subtraction 80 - 35
  c.renderSceneHeader({
    ...SCENE,
    item: { type: 'sub', a: 80, b: 35 },
  });
  assert.equal(c.getChipA1Text(), 'रवि, सही उत्तर 45 है');
  assert.equal(t.a1.disabled, false);

  // 4. Non-subtraction problem (e.g. addition, place_value or literacy)
  c.renderSceneHeader({
    ...SCENE,
    item: { type: 'add', a: 28, b: 15 },
  });
  assert.equal(c.getChipA1Text(), null);
  assert.equal(t.a1.disabled, true);
  assert.equal(t.a1.dataset.text, undefined);
});

test('Fast-Track chips disable on tap, re-enable on reply or failure or 90s timeout', async () => {
  const c = load();
  const t = withFastTrackTray(c);
  const activeScene = {
    ...SCENE,
    item: { type: 'sub', a: 43, b: 27 },
  };
  c.net.handler = async () => ({
    status: 200,
    ok: true,
    json: async () => ({ messages: [], pending: false, scene: activeScene }),
  });
  c.renderSceneHeader(activeScene);
  c.setupFastTrackTray();

  // Tap chip A1
  t.tray._listeners.click({ target: t.a1 });
  await c.flush();
  assert.equal(t.a1.disabled, true);
  assert.equal(t.a2.disabled, true);
  assert.equal(t.b.disabled, true);
  assert.equal(t.c.disabled, true);

  // Outbound reply lands -> re-enables chips
  c.renderMessage({ id: 'msg-reply-1', direction: 'out', speaker: 'ravi', text: '16... ?' });
  c.enableFastTrackChips();
  assert.equal(t.a1.disabled, false);
  assert.equal(t.a2.disabled, false);
  assert.equal(t.b.disabled, false);
  assert.equal(t.c.disabled, false);

  // Tap chip A2
  t.tray._listeners.click({ target: t.a2 });
  await c.flush();
  assert.equal(t.a1.disabled, true);
  assert.equal(t.a2.disabled, true);

  // Failure occurs -> re-enables chips
  c.failMessage('dummy-id', 'network');
  assert.equal(t.a1.disabled, false);
  assert.equal(t.a2.disabled, false);

  // Tap chip B, test 90s hard-cap timeout
  t.tray._listeners.click({ target: t.b });
  await c.flush();
  assert.equal(t.b.disabled, true);
  await c.advance(90001);
  assert.equal(t.b.disabled, false);
});
