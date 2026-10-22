"""chat.js must not render a second user bubble when the server copy of a message arrives.

Live bug: one tap on a sample chip showed two identical user bubbles with one POST. The
optimistic bubble is keyed by client_msg_id, the polled copy by the server id, and
/api/chat/messages did not return client_msg_id, so renderMessage could not match them.

Runs the real chat.js in Node's vm with a minimal DOM stub (skipped if node is absent).
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CHAT_JS = Path(__file__).parents[2] / "app" / "web" / "static" / "chat.js"
NODE = shutil.which("node")

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

class El {
  constructor(tag) {
    this.tagName = tag; this.children = []; this.id = ''; this.className = '';
    this.textContent = ''; this.innerHTML = ''; this.style = {}; this.attrs = {};
    this.scrollTop = 0; this.scrollHeight = 0;
    this.classList = { add() {}, remove() {}, toggle() {}, contains: () => false };
  }
  appendChild(c) { this.children.push(c); return c; }
  insertBefore(c) { this.children.push(c); return c; }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  addEventListener() {}
}
const container = new El('div');
container.id = 'chat-messages';
function findById(node, id) {
  for (const c of node.children) {
    if (c.id === id) return c;
    const hit = findById(c, id);
    if (hit) return hit;
  }
  return null;
}
const document = {
  getElementById: (id) => (id === 'chat-messages' ? container : findById(container, id)),
  createElement: (tag) => new El(tag),
  addEventListener() {}, querySelector: () => null, querySelectorAll: () => [],
};
const window = { AudioRecorder: class {}, addEventListener() {} };
const sandbox = {
  window, document, console,
  navigator: { onLine: true, serviceWorker: undefined },
  localStorage: { getItem: () => null, setItem() {} },
  crypto: { randomUUID: () => 'client-1' },
  setTimeout, clearTimeout,
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8') +
  '\n;globalThis.__t = { renderMessage, state, adoptServerMessageId:' +
  ' (typeof adoptServerMessageId === "function" ? adoptServerMessageId : () => {}) };',
  sandbox);
const { renderMessage, adoptServerMessageId, state } = sandbox.__t;
const rows = () => container.children.filter((c) => c.className.startsWith('msg-row'));
const result = {};

// Scenario A: poll returns the server copy (with client_msg_id) before the POST response
renderMessage({ client_msg_id: 'client-1', direction: 'in', kind: 'text', text: 'नमस्ते',
  created_at: '2026-10-21T10:00:00Z' }, true);
renderMessage({ id: 'server-1', client_msg_id: 'client-1', direction: 'in', kind: 'text',
  text: 'नमस्ते', created_at: '2026-10-21T10:00:00Z' });
result.pollFirstRows = rows().length;
result.rowIdAfterPoll = rows()[0].id;

// Scenario B: POST response arrives first (adopt), then the poll copy
renderMessage({ client_msg_id: 'client-2', direction: 'in', kind: 'text', text: 'दूसरा',
  created_at: '2026-10-21T10:01:00Z' }, true);
adoptServerMessageId('client-2', 'server-2');
renderMessage({ id: 'server-2', client_msg_id: 'client-2', direction: 'in', kind: 'text',
  text: 'दूसरा', created_at: '2026-10-21T10:01:00Z' });
result.totalRowsAfterB = rows().length;

// A bot reply is still rendered as its own bubble
renderMessage({ id: 'server-3', direction: 'out', kind: 'text', text: 'जवाब',
  created_at: '2026-10-21T10:01:05Z' });
result.totalRowsAfterReply = rows().length;
console.log(JSON.stringify(result));
"""


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_server_copy_of_optimistic_message_is_not_rendered_twice(tmp_path: Path) -> None:
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    assert NODE is not None
    proc = subprocess.run(
        [NODE, str(harness), str(CHAT_JS)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip().splitlines()[-1])

    assert result["pollFirstRows"] == 1, "poll copy rendered a second user bubble"
    assert result["rowIdAfterPoll"] == "msg-server-1"
    assert result["totalRowsAfterB"] == 2, "adopted bubble rendered again by the poll"
    assert result["totalRowsAfterReply"] == 3
