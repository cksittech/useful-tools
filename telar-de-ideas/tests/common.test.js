// tests/common.test.js
// Regression tests for common.js's editor helpers (graph logic itself is
// server-side — tests/test_graph.py). Run from the project root: node --test tests/*.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const { loadCommon, plain } = require('./load_common');

const C = loadCommon();

// Shaped like GET /node-types' entries (only the fields these helpers read).
const TYPES = {
  que: { multiInputs: ['in0', 'in1'], reset: { set: { queue: [], __seq: 0 }, unset: ['__dequeuedValues'] } },
  text: { multiInputs: [], reset: { set: {}, unset: ['__ranPassed'] } },
  group: { multiInputs: [], reset: { set: {}, unset: [] } },
};

test('applyResetToNodes: set fields, drop unset ones, leave other data and types alone', () => {
  const nodes = {
    q: { id: 'q', type: 'que', data: { inputCount: 2, queue: [['a']], __seq: 3, __dequeuedValues: ['a'] } },
    t: { id: 't', type: 'text', data: { value: 'x', __ranPassed: true } },
    g: { id: 'g', type: 'group', data: { title: 'G' } },
    u: { id: 'u', type: 'unknown', data: { a: 1 } },
  };
  const next = C.applyResetToNodes(nodes, TYPES);
  assert.deepEqual(plain(next.q.data), { inputCount: 2, queue: [], __seq: 0, __dequeuedValues: undefined });
  assert.ok('__ranPassed' in next.t.data && next.t.data.__ranPassed === undefined);
  assert.equal(next.g, nodes.g);
  assert.equal(next.u, nodes.u);
  // Each node gets its own copy of the reset values.
  next.q.data.queue.push('x');
  assert.deepEqual(plain(TYPES.que.reset.set.queue), []);
});

test('portAcceptsMultiple: trigger port always, else the type\'s multiInputs', () => {
  const q = { id: 'q', type: 'que', data: {} };
  assert.equal(C.portAcceptsMultiple(q, 'in1', TYPES), true);
  assert.equal(C.portAcceptsMultiple(q, 'in4', TYPES), false);
  assert.equal(C.portAcceptsMultiple({ type: 'text' }, '__trigger', TYPES), true);
  assert.equal(C.portAcceptsMultiple(undefined, 'in0', TYPES), false);
  assert.equal(C.portAcceptsMultiple({ type: 'unknown' }, 'in0', TYPES), false);
});

test('fieldPatch / numberFieldValue: an edit\'s side effects and stored value', () => {
  const field = { key: 'inputCount', alsoSet: { queue: [], __seq: 0 }, alsoUnset: ['__dequeuedValues'] };
  assert.deepEqual(plain(C.fieldPatch(field, 3)), { inputCount: 3, queue: [], __seq: 0, __dequeuedValues: undefined });
  assert.equal(C.numberFieldValue({ store: 'string' }, ' 3.5'), ' 3.5');
  assert.equal(C.numberFieldValue({ min: 0 }, '-2'), 0);
  assert.equal(C.numberFieldValue({ min: 0 }, 'abc'), 0);
  assert.equal(C.numberFieldValue({ integer: true }, '2.7'), 2);
});

test('extractPlaceholders: kinds, defaults, first occurrence only', () => {
  const items = plain(C.extractPlaceholders('{ a # hi } <n#4> [x, y] {a#other} <n>'));
  assert.deepEqual(items.map(p => [p.key, p.defaultValue]), [['string:a', 'hi'], ['number:n', '4'], ['select:x, y', 'x']]);
  assert.deepEqual(plain(C.extractPlaceholders('{{a|{b}}} {{c}}')).map(p => p.key), ['string:b', 'string:c']);
});

test('gridAlignedBodyHeight: whole card is a grid multiple for any row count', () => {
  for (const rows of [1, 2, 3, 6]) {
    const chrome = 2 * C.NODE_BORDER + C.HEADER_H + rows * C.PORT_ROW_H + C.NODE_FOOTER_H;
    for (const body of [undefined, 0, 40, 41, 56, 120, 190]) {
      const h = C.gridAlignedBodyHeight(body, rows);
      assert.equal((chrome + h) % C.GRID_SIZE, 0, `rows=${rows} body=${body}`);
      assert.ok(h >= Math.max(C.MIN_BODY_HEIGHT, body || 0), `rows=${rows} body=${body} never shrinks`);
      assert.ok(h < Math.max(C.MIN_BODY_HEIGHT, body || 0) + C.GRID_SIZE);
    }
  }
});
