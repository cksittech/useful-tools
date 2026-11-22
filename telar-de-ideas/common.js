// common.js
// Editor-side helpers and api_server.py-calling functions used by index.html.
// Pure helpers only — no React, no component state. Everything node-type-specific
// (ports, values, checks, card bodies) is computed server-side (GET /node-types,
// POST /evaluate — see common.py "Node types").

function parseNamedPlaceholder(kind, raw) {
  const hashIdx = raw.indexOf('#');
  if (hashIdx === -1) return { kind, name: raw, defaultValue: kind === 'number' ? '0' : '' };
  return { kind, name: raw.slice(0, hashIdx).trim(), defaultValue: raw.slice(hashIdx + 1).trim() };
}
function parseSelectPlaceholder(raw) {
  const options = raw.split(',').map(o => o.trim());
  return { kind: 'select', name: raw, options, defaultValue: options[0] };
}
function matchPlaceholder(m) {
  if (m[1] !== undefined) return { kind: 'shuffle', name: m[1] };
  if (m[2] !== undefined) return parseNamedPlaceholder('number', m[2]);
  if (m[3] !== undefined) return parseNamedPlaceholder('string', m[3]);
  return parseSelectPlaceholder(m[4]);
}
// Extracts each unique placeholder (see PLACEHOLDER_RE in data.js) from text.
function extractPlaceholders(text) {
  const items = [];
  const seen = new Set();
  let m;
  PLACEHOLDER_RE.lastIndex = 0;
  while ((m = PLACEHOLDER_RE.exec(text || '')) !== null) {
    const { kind, name, defaultValue, options } = matchPlaceholder(m);
    if (kind === 'shuffle') continue;
    const key = `${kind}:${name}`;
    if (!seen.has(key)) {
      seen.add(key);
      items.push({ key, name, kind, defaultValue, options });
    }
  }
  return items;
}

// A Wrapper's linked Created Node: one edge from its WRAPPER_REF_PORT_ID to the
// node's TRIGGER_PORT_ID (onConnect keeps only one), so an id or undefined.
function wrapperLinkedNodeId(wrapperId, edges) {
  const e = edges.find(e => e.from.node === wrapperId && e.from.port === WRAPPER_REF_PORT_ID && e.to.port === TRIGGER_PORT_ID);
  return e ? e.to.node : undefined;
}

// --- Node types (GET /node-types) ---------------------------------------------
// typesByType: { type: info } from the server's list — see node_types_info, common.py.

// Clears every node's run results with its type's reset patch (unset fields are
// removed), leaving inputs alone — the Reset Results button.
function applyResetToNodes(prevNodes, typesByType) {
  const next = { ...prevNodes };
  Object.keys(next).forEach(id => {
    const node = next[id];
    const reset = (typesByType[node.type] || {}).reset;
    if (!reset || (!Object.keys(reset.set).length && !reset.unset.length)) return;
    const patch = { ...JSON.parse(JSON.stringify(reset.set)) };
    reset.unset.forEach(k => { patch[k] = undefined; });
    next[id] = { ...node, data: { ...node.data, ...patch } };
  });
  return next;
}

// Ports taking several incoming wires: the trigger port, and each type's
// multiInputs (Gate's compare/value, Queue's inN). Shared with onConnect.
function portAcceptsMultiple(node, portId, typesByType) {
  if (portId === TRIGGER_PORT_ID) return true;
  if (!node) return false;
  return ((typesByType[node.type] || {}).multiInputs || []).includes(portId);
}

// Edit-panel field (a node type's FIELDS widget) -> the data patch one edit makes:
// the value plus the field's alsoSet/alsoUnset side effects.
function fieldPatch(field, value) {
  const patch = { [field.key]: value, ...(field.alsoSet ? JSON.parse(JSON.stringify(field.alsoSet)) : null) };
  (field.alsoUnset || []).forEach(k => { patch[k] = undefined; });
  return patch;
}

// What a "number" field stores for the typed text: the text itself
// (store "string"), else a number clamped to min (integer: parseInt).
function numberFieldValue(field, text) {
  if (field.store === 'string') return text;
  let v = field.integer ? (parseInt(text, 10) || 0) : (Number(text) || 0);
  if (field.min !== undefined && field.min !== null) v = Math.max(field.min, v);
  return v;
}

function snapToGrid(v) { return Math.round(v / GRID_SIZE) * GRID_SIZE; }

// Rendered body height that rounds the whole card up to a GRID_SIZE
// multiple, so a grid-snapped node's bottom edge lands on the grid too
// regardless of its port-row count (PORT_ROW_H isn't a grid multiple).
function gridAlignedBodyHeight(bodyHeight, rowCount) {
  const chrome = 2 * NODE_BORDER + HEADER_H + rowCount * PORT_ROW_H + NODE_FOOTER_H;
  const total = Math.ceil((chrome + Math.max(MIN_BODY_HEIGHT, bodyHeight || 0)) / GRID_SIZE) * GRID_SIZE;
  return total - chrome;
}

// Invisible resize strips along a node's edges/corners. Side strips start below
// the port rows (rowsBottom) so they don't steal the ports' mousedown.
function makeResizeHandles(rowsBottom) {
  return [
    { dir: 'n', cursor: 'ns-resize', sx: { top: -RESIZE_EDGE / 2, left: RESIZE_CORNER, right: RESIZE_CORNER, height: RESIZE_EDGE } },
    { dir: 's', cursor: 'ns-resize', sx: { bottom: -RESIZE_EDGE / 2, left: RESIZE_CORNER, right: RESIZE_CORNER, height: RESIZE_EDGE } },
    { dir: 'w', cursor: 'ew-resize', sx: { left: -RESIZE_EDGE / 2, top: rowsBottom, bottom: RESIZE_CORNER, width: RESIZE_EDGE } },
    { dir: 'e', cursor: 'ew-resize', sx: { right: -RESIZE_EDGE / 2, top: rowsBottom, bottom: RESIZE_CORNER, width: RESIZE_EDGE } },
    { dir: 'nw', cursor: 'nwse-resize', sx: { top: -RESIZE_EDGE / 2, left: -RESIZE_EDGE / 2, width: RESIZE_CORNER, height: RESIZE_CORNER } },
    { dir: 'ne', cursor: 'nesw-resize', sx: { top: -RESIZE_EDGE / 2, right: -RESIZE_EDGE / 2, width: RESIZE_CORNER, height: RESIZE_CORNER } },
    { dir: 'sw', cursor: 'nesw-resize', sx: { bottom: -RESIZE_EDGE / 2, left: -RESIZE_EDGE / 2, width: RESIZE_CORNER, height: RESIZE_CORNER } },
    { dir: 'se', cursor: 'nwse-resize', sx: { bottom: -RESIZE_EDGE / 2, right: -RESIZE_EDGE / 2, width: RESIZE_CORNER, height: RESIZE_CORNER } },
  ];
}

function newOutputKey() {
  return 'out_' + Math.random().toString(36).slice(2, 8);
}
// Output schema field, recursively nestable (only under valueType "array").
// Only top-level fields become node output ports; nested fields describe
// each array item's JSON Schema shape.
function makeOutputField(overrides) {
  return {
    key: newOutputKey(), name: '', valueType: 'string',
    enumValues: [], description: '', children: [],
    ...overrides,
  };
}
// Backfills fields missing on templates saved before the schema editor
// existed (they only had key/name/defaultValue).
function normalizeOutputField(o) {
  return {
    key: o.key || newOutputKey(),
    name: o.name || '',
    valueType: o.valueType || 'string',
    enumValues: o.enumValues || [],
    description: o.description || '',
    children: (o.children || []).map(normalizeOutputField),
  };
}
function blankDraft() {
  return { id: null, name: '', content: '', outputs: [makeOutputField({})] };
}

function arrayFieldShade(depth) {
  return ARRAY_FIELD_SHADES[Math.min(depth, ARRAY_FIELD_SHADES.length - 1)];
}

// Remaps nodes saved before the Output node's type key was renamed from
// "output" to "sink" (see node_plugin/05_output.py), so older saves keep working.
function migrateLoadedNodes(loadedNodes) {
  const out = {};
  Object.keys(loadedNodes || {}).forEach(id => {
    const node = loadedNodes[id];
    out[id] = node.type === 'output' ? { ...node, type: 'sink' } : node;
  });
  return out;
}

// --- api_server.py-calling functions ---------------------------------------
// Thin request wrappers only — no component state. Callers (index.html)
// own all setState/updateData side effects around these.

async function fetchNodeTypes() {
  const res = await fetch(`${CODEX_API_BASE}/node-types`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// The canvas's live view (common.py editor_view). runState = the live run's
// snapshot "run_state" (waiting reasons).
async function evaluateRequest(nodes, edges, running, runState) {
  const res = await fetch(`${CODEX_API_BASE}/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nodes, edges, running, run_state: runState || {} }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function fetchNodeList() {
  const res = await fetch(`${CODEX_API_BASE}/nodes`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function saveNodeRequest(id, body) {
  const res = await fetch(
    id ? `${CODEX_API_BASE}/nodes/${id}` : `${CODEX_API_BASE}/nodes`,
    { method: id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  );
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status} ${detail}`.trim());
  }
  return res.json();
}

async function deleteNodeRequest(id) {
  const res = await fetch(`${CODEX_API_BASE}/nodes/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

async function fetchWorkflowList() {
  const res = await fetch(`${CODEX_API_BASE}/workflows`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function fetchWorkflowById(id) {
  const res = await fetch(`${CODEX_API_BASE}/workflows/${id}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function saveWorkflowRequest(id, body) {
  const res = await fetch(
    id ? `${CODEX_API_BASE}/workflows/${id}` : `${CODEX_API_BASE}/workflows`,
    { method: id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function deleteWorkflowRequest(id) {
  const res = await fetch(`${CODEX_API_BASE}/workflows/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

// --- Server-side runs (api_server.py /runs, see RunClient below) ---
// Each resolves to the run's snapshot (GET /runs/{id} shape).
async function startRunRequest(body) {
  const res = await fetch(`${CODEX_API_BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function fetchRunRequest(runId, since) {
  const res = await fetch(`${CODEX_API_BASE}/runs/${runId}?since=${since}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// Best-effort — callers don't check the result (RunClient).
async function stopRunRequest(runId) {
  await fetch(`${CODEX_API_BASE}/runs/${runId}/stop`, { method: 'POST' });
}

async function stopRunNodeRequest(runId, nodeId) {
  await fetch(`${CODEX_API_BASE}/runs/${runId}/nodes/${nodeId}/stop`, { method: 'POST' });
}

async function openPathRequest(path) {
  const res = await fetch(`${CODEX_API_BASE}/open-path`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  if (!res.ok) {
    // FastAPI's HTTPException bodies are {"detail": "..."}.
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body && body.detail) detail = body.detail;
    } catch (e) { /* not JSON */ }
    throw new Error(detail);
  }
}

// --- Run client (RunClient) ---------------------------------------------------
// Editor side of a run. The workflow itself runs server-side (api_server.py
// /runs -> common.py); this only starts/stops it and mirrors what it
// does back onto the canvas by polling GET /runs/{id}. No React, no DOM;
// talks to the UI only through `host`:
//   getNodes(), getEdges()    current canvas (sent as the run's graph)
//   updateData(id, patch)     merge into one node's data
//   log(nodeId, msg, level)   run history (nodeId null = workflow-level)
//   notify(msg)               error toast
//   onRunningChange(bool)     the workflow loop started / ended
//   onRunBlocked()            the server's pre-run check found errors
//   onLiveChange(bool)        optional: a server run is alive (also while only Delays are left)

// Changed/removed `data` fields between two snapshots of one node, as a
// patch (removed -> undefined), or null if nothing changed.
function dataPatch(prev, next) {
  const patch = {};
  let changed = false;
  Object.keys(next).forEach(k => {
    if (JSON.stringify(next[k]) !== JSON.stringify(prev[k])) { patch[k] = next[k]; changed = true; }
  });
  Object.keys(prev).forEach(k => {
    if (!(k in next)) { patch[k] = undefined; changed = true; }
  });
  return changed ? patch : null;
}

function dataById(nodes) {
  return Object.fromEntries(Object.keys(nodes).map(id => [id, nodes[id].data || {}]));
}

class RunClient {
  constructor(host, options = {}) {
    this.host = host;
    this.pollIntervalMs = options.pollIntervalMs || RUN_POLL_INTERVAL_MS;
    this.isRunning = false;        // mirrors the server's workflow_running
    this.activeRun = { id: 0 };    // run number in the history log (one per "run started")
    this.runState = {};            // latest snapshot's run_state (POST /evaluate's waiting reasons)
    // The live server run: { id, baseline (node data as of the last
    // snapshot), since (last log seq seen), failures, done }.
    this.remote = null;
  }

  // The server runs the pre-run check (a blocked run ends at once, status "blocked").
  async runWorkflow() {
    if (this.isRunning) return;
    await this.start(this.host.getNodes(), this.host.getEdges(), null);
  }

  // Single-node manual retry — only between runs.
  retryNode(nodeId) {
    const node = this.host.getNodes()[nodeId];
    if (!node || this.isRunning) return;
    if (node.data.runStatus === 'running' || node.data.runStatus === 'starting') return;
    this.start(this.host.getNodes(), this.host.getEdges(), nodeId);
  }

  // Also valid after the workflow loop ended while Delays are still pending.
  stopWorkflow() {
    if (this.remote) stopRunRequest(this.remote.id).catch(() => {});
  }

  stopNode(nodeId) {
    if (this.remote) stopRunNodeRequest(this.remote.id, nodeId).catch(() => {});
  }

  async start(nodes, edges, retryNodeId) {
    // A previous run still alive (only its Delays left) is stopped, so its
    // timers can't fire into this one.
    if (this.remote) {
      stopRunRequest(this.remote.id).catch(() => {});
      this.finish(this.remote);
    }
    // What the server sees: JSON drops undefined fields, so the baseline must too.
    const sent = JSON.parse(JSON.stringify({ nodes, edges }));
    let snap;
    try {
      snap = await startRunRequest({ nodes: sent.nodes, edges: sent.edges, retry_node_id: retryNodeId });
    } catch (e) {
      this.host.log(null, `run failed to start: ${e && e.message ? e.message : e}`, 'error');
      this.host.notify(`Failed to start the run — is api_server.py running on ${CODEX_API_BASE}? (${e && e.message ? e.message : e})`);
      return;
    }
    const remote = { id: snap.id, baseline: dataById(sent.nodes), since: 0, failures: 0, done: false };
    this.remote = remote;
    if (this.host.onLiveChange) this.host.onLiveChange(true);
    this.apply(remote, snap);
    while (!remote.done) {
      await new Promise(resolve => setTimeout(resolve, this.pollIntervalMs));
      if (remote.done) break;
      let next;
      try {
        next = await fetchRunRequest(remote.id, remote.since);
        remote.failures = 0;
      } catch (e) {
        if (++remote.failures >= RUN_POLL_MAX_FAILURES) {
          this.host.log(null, `lost contact with the run: ${e && e.message ? e.message : e}`, 'error');
          this.finish(remote);
        }
        continue;
      }
      this.apply(remote, next);
    }
  }

  // Mirrors one snapshot: new log lines, then only the node data the run
  // itself changed since the previous snapshot — so canvas edits made in the
  // meantime (other fields, other nodes) survive.
  apply(remote, snap) {
    if (remote.done) return;
    this.runState = snap.run_state || {};
    (snap.logs || []).forEach(l => {
      remote.since = Math.max(remote.since, l.seq);
      if (l.nodeId === null && l.message === 'run started') this.activeRun = { id: this.activeRun.id + 1 };
      this.host.log(l.nodeId, l.message, l.level);
      if (l.notify) this.host.notify(l.message);
    });
    Object.keys(snap.nodes || {}).forEach(id => {
      const data = snap.nodes[id].data || {};
      const patch = dataPatch(remote.baseline[id] || {}, data);
      remote.baseline[id] = data;
      if (patch) this.host.updateData(id, patch);
    });
    this.setRunning(!!snap.workflow_running);
    if (snap.status === 'running') return;
    if (snap.status === 'blocked') this.host.onRunBlocked();
    if (snap.status === 'error') this.host.notify(`Run failed: ${snap.error}`);
    this.finish(remote);
  }

  finish(remote) {
    remote.done = true;
    if (this.remote !== remote) return;
    this.remote = null;
    this.setRunning(false);
    if (this.host.onLiveChange) this.host.onLiveChange(false);
  }

  setRunning(running) {
    if (this.isRunning === running) return;
    this.isRunning = running;
    this.host.onRunningChange(running);
  }
}
