// tests/load_common.js
// Loads data.js + common.js (plain browser scripts, no exports) into one vm
// context, same load order as index.html's <head>.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.join(__dirname, '..');

function loadCommon() {
  // Browser globals common.js uses at call time; tests can replace e.g. `fetch` via C.__context.
  const ctx = vm.createContext({ console, setTimeout, clearTimeout, crypto, AbortController, fetch: undefined });
  for (const file of ['data.js', 'common.js']) {
    vm.runInContext(fs.readFileSync(path.join(ROOT, file), 'utf8'), ctx, { filename: file });
  }
  // Top-level const/function names resolve through the context's own scope.
  return new Proxy({}, { get: (_, name) => (name === '__context' ? ctx : vm.runInContext(String(name), ctx)) });
}

// vm-realm objects fail assert.deepStrictEqual's prototype check — clone into this realm first.
const plain = v => structuredClone(v);

module.exports = { loadCommon, plain };
