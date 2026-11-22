// data.js
// Constants and lookup tables used by index.html.

// Codex backend (api_server.py). Keep in sync with config.json's api_port.
const CODEX_API_BASE = 'http://127.0.0.1:9014';
// How often a server-side run (GET /runs/{id}) is polled while it's live.
// Keep in sync with config.json's poll_interval_ms.
const RUN_POLL_INTERVAL_MS = 500;
// Consecutive failed polls before the editor gives up on a run (server gone).
const RUN_POLL_MAX_FAILURES = 5;
// Folder a Created Node's thread-id link opens via /open-path ("~" is expanded there).
// Keep in sync with config.json's generated_images_dir.
const GENERATED_IMAGES_DIR = '~/.codex/generated_images/';
// Canvas edits settle this long before the server re-evaluates (POST /evaluate);
// moving/resizing nodes never triggers one.
const EVALUATE_DELAY_MS = 150;
// While api_server.py is unreachable, how often the editor tries it again.
const SERVER_RETRY_MS = 2000;

// Run history panel keeps only the newest this-many events.
const RUN_LOG_MAX = 500;

// ---- layout constants ----
const NODE_WIDTH = 240;
const HEADER_H = 36;
const PORT_ROW_H = 26;
const DOT_SIZE = 14;
// Move/resize snap to this grid (matches the canvas's dot spacing).
const GRID_SIZE = 20;
// Floating node edit panel (top-right of the canvas).
const EDIT_PANEL_WIDTH = 340;
const MIN_NODE_WIDTH = 180;
const MIN_BODY_HEIGHT = 40;
// Card chrome outside the header/port rows/body: border (each side) and the
// bottom run-progress strip (4px bar + 8px margin). See gridAlignedBodyHeight.
const NODE_BORDER = 2;
const NODE_FOOTER_H = 12;
// Resize hit-area sizes (px) for a node's invisible edge/corner strips.
const RESIZE_EDGE = 7, RESIZE_CORNER = 14;

// Port/edge colors: orange once wired, grey while not, regardless of
// declared/runtime value type.
const PORT_CONNECTED_COLOR = '#ff9800';
const PORT_UNCONNECTED_COLOR = '#9e9e9e';
// Menu button accents: Default Node red, Plugin Node indigo (darker shades of data.py's
// header colors); Created Node teal (keep in sync with data.py's TEMPLATE_HEADER_COLOR).
// Card header colors come from each node type (GET /node-types).
const DEFAULT_NODE_COLOR = '#d32f2f';
const PLUGIN_NODE_COLOR = '#303f9f';
const TEMPLATE_COLOR = '#00acc1';

// Every Created Node's free thread_id output port. "__" keeps it out of the
// way of user-defined keys (always "out_...").
const THREAD_ID_OUTPUT_KEY = '__thread_id';
// Wrapper maxRetries value shown as ∞ (one step below 0); mirrors data.py's UNLIMITED_RETRIES.
const UNLIMITED_RETRIES = -1;
// Created Node's header control-input port for a Gate signal — see
// compute_trigger_blocked_nodes in common.py. Only Created Node has this.
const TRIGGER_PORT_ID = '__trigger';
const TRIGGER_COLOR = '#9c27b0';
// Group's Ref port: wired into a Created Node's TRIGGER_PORT_ID, makes it a
// member (group_member_ids, common.py). Carries no signal; colored apart from TRIGGER_COLOR.
const GROUP_REF_PORT_ID = '__ref';
const GROUP_REF_COLOR = '#607d8b';
// Wrapper's Ref port: same as Group's, but links exactly one Created Node (wrapperLinkedNodeId).
const WRAPPER_REF_PORT_ID = '__wrapperRef';
const WRAPPER_REF_COLOR = '#3f51b5';

// Created Node placeholder syntax (Template Manager's preview, a new node's
// default values): {name} = string ("#" default: {name#default}), <name> = number
// (same "#default"), [a,b,c] = select (first = default), {{a|b|c}} = no field: its
// parts are shuffled into lines on each send (common.py's resolve_shuffle). Order
// avoids <a>/{a} and {{a|b}}/{a|b} clashes. Keep in sync with data.py's PLACEHOLDER_RE.
const PLACEHOLDER_RE = /\{\{([^{}]*\|[^{}]*)\}\}|<\s*([^<>]+?)\s*>|\{\s*([^{}]+?)\s*\}|\[\s*([^\[\]]+?)\s*\]/g;

// Wrapper condition operators (keep in sync with data.py) and their labels in the Wrapper edit form.
const WRAPPER_CONDITION_OPS = ['eq', 'neq', 'gt', 'gte', 'lt', 'lte'];
const WRAPPER_OP_LABELS = { eq: '=', neq: '≠', gt: '>', gte: '≥', lt: '<', lte: '≤' };

// A template node's body only shows a small status chip/alert (full detail
// is one click away), so it needs far less default room than the rest.
const TEMPLATE_DEFAULT_BODY_HEIGHT = 90;

// Depth-based background shades for nested array output-schema fields
// (TemplateManagerDialog's OutputFieldEditor).
const ARRAY_FIELD_SHADES = ['grey.50', 'grey.200', 'grey.400'];
