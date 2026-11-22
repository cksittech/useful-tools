// tests/run_client.test.js
// RunClient (common.js) against a fake api_server.py /runs: what it
// sends, and how snapshots are mirrored back onto the canvas.
const test = require('node:test');
const assert = require('node:assert/strict');
const { loadCommon, plain } = require('./load_common');

const C = loadCommon();
const wait = ms => new Promise(r => setTimeout(r, ms));

const node = (id, type, data = {}) => [id, { id, type, x: 0, y: 0, data }];
const graph = (...entries) => Object.fromEntries(entries);
const edge = (id, from, fromPort, to, toPort) => ({ id, from: { node: from, port: fromPort }, to: { node: to, port: toPort } });
const OUT = [{ key: 'out_r', name: 'result', valueType: 'string', enumValues: [], description: '', children: [] }];

// Fake server: each GET /runs/{id} answers the next scripted snapshot
// (the last one repeats). snapshot(): fills the boilerplate fields.
const snapshot = (over = {}) => ({ id: 'r1', status: 'running', workflow_running: true, run_state: {}, nodes: {}, logs: [], ...over });
function fakeServer(script) {
  const s = { starts: [], polls: [], stops: [], nodeStops: [] };
  let i = 0;
  C.__context.fetch = async (url, init = {}) => {
    const json = data => ({ ok: true, status: 200, json: async () => data });
    if (url.endsWith('/runs') && init.method === 'POST') { s.starts.push(JSON.parse(init.body)); return json(script[0]); }
    if (/\/runs\/[^/]+\/nodes\/[^/]+\/stop$/.test(url)) { s.nodeStops.push(url); return json({ ok: true }); }
    if (url.endsWith('/stop')) { s.stops.push(url); return json({ ok: true }); }
    if (url.includes('/runs/')) { s.polls.push(url); i = Math.min(i + 1, script.length - 1); return json(script[i]); }
    throw new Error('unexpected fetch ' + url);
  };
  return s;
}

function makeHost(nodes, edges = []) {
  const h = {
    nodes, edges, logs: [], toasts: [], running: [], live: [], blocked: 0,
    getNodes: () => h.nodes,
    getEdges: () => h.edges,
    updateData: (id, patch) => { if (h.nodes[id]) h.nodes = { ...h.nodes, [id]: { ...h.nodes[id], data: { ...h.nodes[id].data, ...patch } } }; },
    log: (nodeId, message, level) => h.logs.push({ nodeId, message, level, run: h.client.activeRun.id }),
    notify: msg => h.toasts.push(msg),
    onRunningChange: r => h.running.push(r),
    onRunBlocked: () => { h.blocked++; },
    onLiveChange: l => h.live.push(l),
  };
  h.client = new C.RunClient(h, { pollIntervalMs: 2 });
  return h;
}

test('sends the canvas, mirrors logs/data, and ends when the run does', async () => {
  const t = { content: 'hi', outputs: OUT, outputValues: {}, note: 'keep' };
  const srv = fakeServer([
    snapshot({ nodes: { t: { data: t } }, logs: [{ seq: 1, nodeId: null, message: 'run started', level: 'info' }] }),
    snapshot({ nodes: { t: { data: { ...t, runStatus: 'running' } } }, logs: [{ seq: 2, nodeId: 't', message: 'Codex job started', level: 'info' }] }),
    snapshot({ status: 'finished', workflow_running: false, nodes: { t: { data: { ...t, runStatus: 'done', outputValues: { out_r: 'ok' } } } },
      logs: [{ seq: 3, nodeId: 'm', message: 'Failed to move folder: x', level: 'error', notify: true }] }),
  ]);
  const host = makeHost(graph(node('t', 'template', t)));
  await host.client.runWorkflow();
  assert.deepEqual(Object.keys(srv.starts[0].nodes), ['t']);
  assert.equal(srv.starts[0].retry_node_id, null);
  assert.equal(host.nodes.t.data.runStatus, 'done');
  assert.deepEqual(plain(host.nodes.t.data.outputValues), { out_r: 'ok' });
  assert.deepEqual(plain(host.logs.map(l => [l.message, l.run])), [['run started', 1], ['Codex job started', 1], ['Failed to move folder: x', 1]]);
  assert.deepEqual(plain(host.toasts), ['Failed to move folder: x']);
  assert.deepEqual(plain(host.running), [true, false]);
  assert.deepEqual(plain(host.live), [true, false]);
  assert.ok(srv.polls.every(u => /since=\d+$/.test(u)));
  assert.ok(srv.polls[srv.polls.length - 1].endsWith('since=2'));
});

test('only fields the run changed are written back; local edits survive', async () => {
  fakeServer([
    snapshot({ nodes: { x: { data: { value: 'a' } }, d: { data: { seconds: 3 } } } }),
    snapshot({ status: 'finished', workflow_running: false, nodes: { x: { data: { value: 'a', __ranPassed: true } }, d: { data: { seconds: 3 } } } }),
  ]);
  const host = makeHost(graph(node('x', 'text', { value: 'a' }), node('d', 'delay', { seconds: 3, delayStatus: 'waiting' })));
  const done = host.client.runWorkflow();
  host.updateData('x', { value: 'edited meanwhile' });
  await done;
  assert.equal(host.nodes.x.data.value, 'edited meanwhile');
  assert.equal(host.nodes.x.data.__ranPassed, true);
  // delayStatus was sent but the run's snapshot no longer has it -> cleared.
  assert.equal(host.nodes.d.data.delayStatus, undefined);
});

test('a run the server blocks (pre-run errors) ends at once and opens the check', async () => {
  const srv = fakeServer([snapshot({ status: 'blocked', workflow_running: false, run_state: { q: { latch: {} } },
    logs: [{ seq: 1, nodeId: null, message: 'run blocked — 1 pre-run error(s)', level: 'error' }] })]);
  const host = makeHost(graph(node('t', 'template', { content: '  ', outputs: OUT })));
  await host.client.runWorkflow();
  assert.equal(srv.starts.length, 1);
  assert.equal(srv.polls.length, 0);
  assert.equal(host.blocked, 1);
  assert.deepEqual(plain(host.logs.map(l => l.message)), ['run blocked — 1 pre-run error(s)']);
  assert.deepEqual(plain(host.client.runState), { q: { latch: {} } });
  assert.deepEqual(plain(host.live), [true, false]);
});

test('stop/node stop hit the live run; retry sends retry_node_id', async () => {
  const srv = fakeServer([snapshot(), snapshot(), snapshot({ status: 'stopped', workflow_running: false })]);
  const host = makeHost(graph(node('t', 'template', { content: 'hi', outputs: OUT })));
  const done = host.client.runWorkflow();
  await wait(1);
  host.client.stopNode('t');
  host.client.stopWorkflow();
  await done;
  await wait(5);
  assert.deepEqual(plain(srv.stops), ['http://127.0.0.1:9014/runs/r1/stop']);
  assert.deepEqual(plain(srv.nodeStops), ['http://127.0.0.1:9014/runs/r1/nodes/t/stop']);

  const srv2 = fakeServer([snapshot({ workflow_running: false }), snapshot({ status: 'finished', workflow_running: false })]);
  host.client.retryNode('t');
  await wait(20);
  assert.equal(srv2.starts[0].retry_node_id, 't');
});

test('gives up after repeated poll failures', async () => {
  fakeServer([snapshot()]);
  const host = makeHost(graph(node('t', 'template', { content: 'hi', outputs: OUT })));
  const orig = C.__context.fetch;
  let first = true;
  C.__context.fetch = async (url, init) => {
    if (first) { first = false; return orig(url, init); }
    throw new TypeError('Failed to fetch');
  };
  await host.client.runWorkflow();
  assert.ok(host.logs.some(l => l.message.startsWith('lost contact with the run')));
  assert.equal(host.client.isRunning, false);
});
