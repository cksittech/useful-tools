const API_BASE = 'http://127.0.0.1:9032';

// Fields shown in monospace (code / tables). keep keys in sync with FIELDS in data.py
// ('ansible' is UI-only: the generated Ansible task blocks)
const MONOSPACE_FIELDS = ['audit', 'remediation', 'cis_controls', 'ansible'];

// How often to poll a running Codex generation.
const ANSIBLE_POLL_MS = 2000;

// localStorage key for the last selected PDF.
const LAST_PDF_KEY = 'forja-cis-ansible:last-pdf';

// Ansible tab: one box per generated task list. keep keys in sync with ANSIBLE_OUTPUT_SCHEMA in data.py
const ANSIBLE_BLOCKS = [
  { key: 'remediation_tasks', label: 'Remediation tasks (apply)' },
  { key: 'verification_tasks', label: 'Verification tasks (audit)' },
  { key: 'rollback_tasks', label: 'Rollback tasks (undo)' },
];

// Detail pane tabs.
const DETAIL_TABS = [
  { value: 'details', label: 'Details' },
  { value: 'ansible', label: 'Ansible' },
];

// How long the Copy button shows "Copied".
const COPIED_MS = 1500;

// How often to check that the API server is reachable (GET /health).
const HEALTH_POLL_MS = 5000;

// Snapshot read while the API server is down (written by the server into snapshot/).
// keep in sync with SNAPSHOT_DIR / SNAPSHOT_INDEX_FILE / SNAPSHOT_GLOBAL in data.py
const SNAPSHOT_DIR = 'snapshot';
const SNAPSHOT_INDEX_FILE = 'index.js';
const SNAPSHOT_GLOBAL = 'CIS_SNAPSHOT';

// Shown next to the Generate button while the API server is down.
const API_DOWN_NOTE = `API server (${API_BASE}) is not reachable: generation is disabled. Showing saved data.`;

// Shown when the API server is down and no snapshot exists yet.
const NO_SNAPSHOT_MESSAGE =
  'API server is not reachable and no saved data (snapshot/) exists yet. ' +
  'Put CIS Benchmark PDFs in documents/, then start the API server in this folder: ' +
  '$env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --reload --host 127.0.0.1 --port ' + new URL(API_BASE).port;
