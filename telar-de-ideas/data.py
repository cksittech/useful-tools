# data.py
# Definitions: API request models, node types/ports, placeholder patterns and run limits.

import re

from pydantic import BaseModel

# --- Request models --------------------------------------------------------------


# POST/PUT /nodes request body: one AI Node definition.
class NodeSaveRequest(BaseModel):
    name: str
    content: str
    outputs: list[dict] = []


# POST/PUT /workflows request body: the whole canvas (nodes, edges, viewport).
class WorkflowSaveRequest(BaseModel):
    name: str
    nodes: dict = {}
    edges: list[dict] = []
    pan: dict | None = None
    zoom: float | None = None


# POST /runs request body: a graph to run server-side as-is (the editor's
# current canvas — unlike POST /workflows/{id}/runs, which runs a saved one).
class RunRequest(BaseModel):
    nodes: dict = {}
    edges: list[dict] = []
    name: str | None = None
    # Set: retry just this AI Node (the editor's per-node Retry) instead
    # of running the whole workflow.
    retry_node_id: str | None = None


# POST /codex/jobs request body: a AI Node's filled prompt plus its
# output JSON Schema (built from the node's output ports).
class CodexJobRequest(BaseModel):
    prompt: str
    output_schema: dict | None = None
    node_id: str | None = None
    # Client-chosen idempotency key — a resend with the same key returns the
    # first call's job instead of starting a second one (common.run_once).
    operation_id: str | None = None


# POST /open-path request body: an OS path to reveal in File Explorer.
class OpenPathRequest(BaseModel):
    path: str


# POST /fs/move-folder request body: a Move node's source/destination pair.
class MoveFolderRequest(BaseModel):
    src: str
    dst: str
    # Same idempotency key as CodexJobRequest.operation_id.
    operation_id: str | None = None


# POST /evaluate request body: the editor's canvas, for its live view (common.editor_view).
class EvaluateRequest(BaseModel):
    nodes: dict = {}
    edges: list[dict] = []
    # The workflow loop is running (Gate's waiting border needs it).
    running: bool = False
    # The live run's per-node run state (snapshot "run_state"), for waiting reasons.
    run_state: dict = {}


# --- Node definitions --------------------------------------------------------------
# Per-type definitions live in node_plugin/ (one file per type, see common.py's
# "Node types"); these are the core's own ids and the layout defaults they share.
THREAD_ID_OUTPUT_KEY = "__thread_id"
# Wrapper maxRetries value meaning "retry until the conditions pass or Stop" (shown as ∞).
UNLIMITED_RETRIES = -1
TRIGGER_PORT_ID = "__trigger"
GROUP_REF_PORT_ID = "__ref"
WRAPPER_REF_PORT_ID = "__wrapperRef"

GROUP_MEMBER_TYPES = ("template", "wrapper")
WRAPPER_CONDITION_OPS = ["eq", "neq", "gt", "gte", "lt", "lte"]
# Query parameter POST /workflows/{id}/runs reserves for its wait time — not usable as a parameter name.
API_WAIT_PARAM = "wait"
# API Input's output port per parameter ("param:<name>") and the value types a parameter takes.
API_PARAM_PORT_PREFIX = "param:"
API_PARAM_VALUE_TYPES = ("string", "number")
# API Response's input port per body field ("field:<name>").
API_FIELD_PORT_PREFIX = "field:"

# A new node's body height (port rows add on top): S = one caption line,
# M = description + one status line/chip, L = live preview/chip list that grows during a run.
BODY_H_S, BODY_H_M, BODY_H_L = 40, 80, 120
# Header tint of a type that sets no COLOR — red for the core's, indigo for node_plugin/
# files (pale so the header's own Delete/Stop buttons stay visible); AI Node keeps its own teal.
DEFAULT_NODE_HEADER_COLOR = "#e57373"
PLUGIN_NODE_HEADER_COLOR = "#7986cb"
TEMPLATE_HEADER_COLOR = "#00acc1"


# --- Placeholders ----------------------------------------------------------------
# JS \s / String.prototype.trim whitespace set (Python's \s and str.strip differ).
JS_WS_CHARS = "\t\n\x0b\x0c\r   " + "".join(chr(c) for c in range(0x2000, 0x200B)) + "    　﻿"
_WS = "[" + re.escape(JS_WS_CHARS) + "]"
# {{a|b}} shuffle / <num> / {str} / [select], parsed by common.py. Keep in sync with data.js's PLACEHOLDER_RE.
PLACEHOLDER_RE = re.compile(
    r"\{\{([^{}]*\|[^{}]*)\}\}"
    + "|<" + _WS + "*([^<>]+?)" + _WS + "*>"
    + r"|\{" + _WS + r"*([^{}]+?)" + _WS + r"*\}"
    + r"|\[" + _WS + r"*([^\[\]]+?)" + _WS + r"*\]"
)
# Just the {{a|b|c}} shuffle (common.resolve_shuffle).
SHUFFLE_RE = re.compile(r"\{\{([^{}]*\|[^{}]*)\}\}")

# --- Idempotent operations (common.run_once) ---------------------------------------
# How long / how many first-call results are kept for replaying a resend.
OPERATION_TTL_SEC = 3600
OPERATION_MAX_ENTRIES = 2000

# --- Runs ------------------------------------------------------------------------
# Per-run log entries kept (oldest dropped first).
RUN_LOG_MAX = 2000
# Finished runs kept in memory for GET /runs/{id} (oldest dropped first).
RUNS_KEPT_MAX = 50
# How often a finished run_workflow() re-checks for pending Delays/Run Triggers.
IDLE_CHECK_SEC = 0.1
# Longest a POST /workflows/{id}/runs?wait= call blocks before answering with the run so far.
RUN_WAIT_MAX_SEC = 600
