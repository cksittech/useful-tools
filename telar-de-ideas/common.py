# common.py
# Processing for api_server.py: saved records, Codex jobs, folder moves, graph
# evaluation and workflow runs. Definitions (models, node types, limits) are in data.py.

import asyncio
import copy
import importlib.util
import inspect
import json
import logging
import math
import random
import re
import shutil
import threading
import time
import uuid
from collections import OrderedDict
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from openai_codex import Codex

from data import (
    API_FIELD_PORT_PREFIX,
    API_PARAM_PORT_PREFIX,
    API_PARAM_VALUE_TYPES,
    API_WAIT_PARAM,
    BODY_H_L,
    BODY_H_M,
    BODY_H_S,
    DEFAULT_NODE_HEADER_COLOR,
    PLUGIN_NODE_HEADER_COLOR,
    GROUP_MEMBER_TYPES,
    GROUP_REF_PORT_ID,
    IDLE_CHECK_SEC,
    JS_WS_CHARS,
    OPERATION_MAX_ENTRIES,
    OPERATION_TTL_SEC,
    PLACEHOLDER_RE,
    RUN_LOG_MAX,
    RUNS_KEPT_MAX,
    SHUFFLE_RE,
    TEMPLATE_HEADER_COLOR,
    THREAD_ID_OUTPUT_KEY,
    UNLIMITED_RETRIES,
    TRIGGER_PORT_ID,
    WRAPPER_CONDITION_OPS,
    WRAPPER_REF_PORT_ID,
)

# Shared frontend/backend config file.
CONFIG_PATH = Path(__file__).parent / "config.json"


# Loads the shared config file as a dict.
def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


# Loaded once at import time so backend/frontend agree without editing both.
_config = load_config()

# Port api_server.py listens on. Keep in sync with CODEX_API_BASE in data.js.
API_PORT = _config["api_port"]
# Codex() spawns a `codex app-server` subprocess that initializes shared
# sqlite state under ~/.codex; concurrent Codex() calls can race that init
# and fail with "failed to initialize sqlite state runtime" — retry backstop.
CODEX_STARTUP_MAX_ATTEMPTS = _config["codex_startup_max_attempts"]
CODEX_STARTUP_RETRY_DELAY_SEC = _config["codex_startup_retry_delay_sec"]
# Caps concurrent Codex jobs within one server-side run.
MAX_CONCURRENT_RUNS = _config["max_concurrent_runs"]
# How often runs poll their Codex jobs and the editor polls a run
# (keep RUN_POLL_INTERVAL_MS in data.js in sync).
POLL_INTERVAL_MS = _config["poll_interval_ms"]
# Overrides ~/.codex/config.toml `model` / `model_reasoning_effort` for every
# job. Omit or null in config.json to fall back to the Codex CLI default.
CODEX_MODEL = _config.get("codex_model")
CODEX_REASONING_EFFORT = _config.get("codex_reasoning_effort")

# Isolated from the root logger's handlers/propagation.
logger = logging.getLogger("telar_de_ideas")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:\t%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


# --- AI Node definitions ----------------------------------------------------
# One JSON file per node under node_ai/, filename == id == save timestamp
# (YYYYMMDDHHMMSS).

NODE_AI_DIR = Path(__file__).resolve().parent / "node_ai"


# --- Workflows ---------------------------------------------------------------
# One JSON file per workflow (nodes + edges + viewport), same convention.

WORKFLOWS_DIR = Path(__file__).resolve().parent / "workflows"


# --- JSON record store (shared by node_ai/ and workflows/) ------------------
# id == filename stem == save timestamp; a same-second collision gets "_N".

# [(id, data)] newest first; unreadable files are skipped.
def list_records(folder: Path) -> list[tuple[str, dict]]:
    folder.mkdir(parents=True, exist_ok=True)
    records = []
    for path in sorted(folder.glob("*.json"), reverse=True):
        try:
            records.append((path.stem, json.loads(path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return records


# Unused path for a new record in folder (id = its stem).
def new_record_path(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{time.strftime('%Y%m%d%H%M%S')}.json"
    counter = 1
    while path.exists():
        path = folder / f"{time.strftime('%Y%m%d%H%M%S')}_{counter}.json"
        counter += 1
    return path


# Ids of the saved workflows named exactly `name`, newest first.
def workflow_ids_named(name: str) -> list[str]:
    return [rid for rid, d in list_records(WORKFLOWS_DIR) if d.get("name") == name]


def write_record(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# --- Codex job execution -----------------------------------------------------
# In-memory only — no on-disk persistence, so job history is lost on
# restart (a job still starting/running when the server dies is simply gone).

codex_jobs: dict[str, dict] = {}

# Guards codex_jobs across background threads.
codex_jobs_lock = threading.Lock()


# Fresh state for a new Codex job, as stored in codex_jobs.
def new_job_state(job_id: str, prompt: str, output_schema: dict | None, node_id: str | None) -> dict:
    return {
        "id": job_id,
        "prompt": prompt,
        "output_schema": output_schema,
        "node_id": node_id,
        "status": "starting",
        "error": None,
        "duration_ms": None,
        "response": None,
        "output": None,
        "thread_id": None,
        "turn_handle": None,
        # Set by POST /codex/jobs/{id}/stop; honored even before the turn
        # exists (run_codex_job checks it at each startup step).
        "stop_requested": False,
        "started_at": time.time(),
    }


# Marks a stop: interrupts the live turn if there is one, else leaves the flag
# for run_codex_job to act on. Returns False for an unknown job id.
def request_stop(job_id: str) -> bool:
    with codex_jobs_lock:
        job = codex_jobs.get(job_id)
        if job is None:
            return False
        job["stop_requested"] = True
        turn_handle = job.get("turn_handle")
    if turn_handle is not None:
        turn_handle.interrupt()
    return True


def _stop_requested(job_id: str) -> bool:
    with codex_jobs_lock:
        return codex_jobs[job_id]["stop_requested"]


def _mark_stopped_before_turn(job_id: str) -> None:
    with codex_jobs_lock:
        job = codex_jobs[job_id]
        job["status"] = "stopped"
        job["error"] = "Stopped before the turn started."


# Job dict safe to return over the API (drops the non-serializable
# in-memory TurnHandle).
def serializable_job(job: dict) -> dict:
    pub = dict(job)
    pub.pop("turn_handle", None)
    return pub


# GET /codex/jobs/{id}'s view of one job (+ elapsed_seconds), or None if unknown.
def public_job(job_id: str) -> dict | None:
    with codex_jobs_lock:
        job = codex_jobs.get(job_id)
        if job is None:
            return None
        pub = serializable_job(job)
    pub["elapsed_seconds"] = time.time() - pub.pop("started_at")
    return pub


# Seeds a job entry and runs it on a daemon thread, once per operation_id (a
# resend gets the first call's job back). Shared by POST /codex/jobs and
# server-side runs. `prompt` must already be stripped and non-empty.
def start_codex_job(prompt: str, output_schema: dict | None, node_id: str | None, operation_id: str | None) -> dict:
    def start():
        job_id = str(uuid.uuid4())
        with codex_jobs_lock:
            codex_jobs[job_id] = new_job_state(job_id, prompt, output_schema, node_id)
        threading.Thread(target=run_codex_job, args=(job_id, prompt, output_schema), daemon=True).start()
        return {"job_id": job_id}

    return run_once(operation_id, start)


# Serializes Codex() construction across threads — see CODEX_STARTUP_MAX_ATTEMPTS.
_codex_startup_lock = threading.Lock()


def _is_transient_startup_error(exc: Exception) -> bool:
    return "state runtime" in str(exc).lower()


def _start_codex_session() -> Codex:
    last_error: Exception | None = None
    for _ in range(CODEX_STARTUP_MAX_ATTEMPTS):
        with _codex_startup_lock:
            try:
                return Codex()
            except Exception as e:
                if not _is_transient_startup_error(e):
                    raise
                last_error = e
        time.sleep(CODEX_STARTUP_RETRY_DELAY_SEC)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Codex session failed to start (no attempts were made).")


# Background-thread target for POST /codex/jobs. Runs one Codex turn to
# completion/failure/interruption, updating codex_jobs throughout for polling clients.
def run_codex_job(job_id: str, prompt: str, output_schema: dict | None) -> None:
    with codex_jobs_lock:
        codex_jobs[job_id]["status"] = "running"

    try:
        if _stop_requested(job_id):
            _mark_stopped_before_turn(job_id)
            return
        codex = _start_codex_session()
        try:
            if _stop_requested(job_id):
                _mark_stopped_before_turn(job_id)
                return
            thread = codex.thread_start(model=CODEX_MODEL)
            with codex_jobs_lock:
                codex_jobs[job_id]["thread_id"] = thread.id
            try:
                turn_handle = thread.turn(
                    resolve_shuffle(prompt), output_schema=output_schema or None,
                    model=CODEX_MODEL, effort=CODEX_REASONING_EFFORT,
                )
                # Publishing the handle and reading the flag under one lock
                # means either request_stop sees the handle or we see the flag.
                with codex_jobs_lock:
                    codex_jobs[job_id]["turn_handle"] = turn_handle
                    stop_now = codex_jobs[job_id]["stop_requested"]
                if stop_now:
                    turn_handle.interrupt()

                result = turn_handle.run()
                with codex_jobs_lock:
                    job = codex_jobs[job_id]
                    if result.status.value == "failed":
                        job["status"] = "error"
                    elif result.status.value == "interrupted":
                        job["status"] = "stopped"
                    else:
                        job["status"] = "done"
                    job["duration_ms"] = result.duration_ms
                    job["response"] = result.final_response
                    if result.error is not None:
                        job["error"] = result.error.message

                    if job["status"] == "done" and output_schema:
                        try:
                            job["output"] = json.loads(result.final_response) if result.final_response else None
                        except Exception as parse_err:
                            job["status"] = "error"
                            job["error"] = f"Structured output was not valid JSON: {parse_err}"
                            job["output"] = None
            finally:
                codex.thread_archive(thread.id)
        finally:
            codex.close()
    except Exception as e:
        with codex_jobs_lock:
            job = codex_jobs[job_id]
            job["status"] = "error"
            job["error"] = str(e)
    finally:
        with codex_jobs_lock:
            codex_jobs[job_id]["turn_handle"] = None


# --- Idempotent operations ---------------------------------------------------
# run_once(): one execution per client operation_id. A resend (network retry,
# double submit) waits for / replays the first call's result or exception
# instead of doing the work twice. In-memory, like codex_jobs.

_operations: "OrderedDict[str, dict]" = OrderedDict()
_operations_lock = threading.Lock()


def _prune_operations_locked() -> None:
    cutoff = time.time() - OPERATION_TTL_SEC
    while _operations:
        _, oldest = next(iter(_operations.items()))
        # Never drop an in-flight entry — a waiter is still blocked on it.
        if not oldest["event"].is_set():
            break
        if oldest["at"] >= cutoff and len(_operations) <= OPERATION_MAX_ENTRIES:
            break
        _operations.popitem(last=False)


def run_once(operation_id: str | None, fn):
    if not operation_id:
        return fn()
    with _operations_lock:
        _prune_operations_locked()
        entry = _operations.get(operation_id)
        is_owner = entry is None
        if is_owner:
            entry = {"event": threading.Event(), "result": None, "error": None, "at": time.time()}
            _operations[operation_id] = entry
    if not is_owner:
        logger.info("Duplicate operation %s — replaying the first result.", operation_id)
        entry["event"].wait()
        if entry["error"] is not None:
            raise entry["error"]
        return entry["result"]
    try:
        entry["result"] = fn()
        return entry["result"]
    except Exception as e:
        entry["error"] = e
        raise
    finally:
        entry["event"].set()


# --- Move / rename folder -----------------------------------------------------
# do_move(): plain rename if dst doesn't exist, else recursive merge (a
# per-item conflict lets the moved item win — same as a manual Explorer
# drag-and-drop merge-and-replace).

def _merge_folder_into(src: Path, dst: Path) -> None:
    for child in list(src.iterdir()):
        target = dst / child.name
        if target.exists():
            if child.is_dir() and target.is_dir():
                # Recursion empties + rmdir's `child` itself; no extra rmdir here.
                _merge_folder_into(child, target)
            else:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                shutil.move(str(child), str(target))
        else:
            shutil.move(str(child), str(target))
    src.rmdir()


# Moves src to dst. Returns True if merged, False if plain rename. Caller
# validates src/dst first.
def do_move(src: Path, dst: Path) -> bool:
    merged = dst.exists()
    if merged:
        _merge_folder_into(src, dst)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    return merged


# A rejected or failed move; status_code is what POST /fs/move-folder answers.
class MoveError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


# Validated do_move — shared by POST /fs/move-folder and Move nodes in runs.
# Returns {"ok": True, "merged": bool}; raises MoveError.
def move_folder_checked(src_path: str, dst_path: str) -> dict:
    src = Path(src_path)
    dst = Path(dst_path)

    if not src.exists():
        raise MoveError(404, f"Source folder not found: {src}")
    if not src.is_dir():
        raise MoveError(400, f"Source is not a folder: {src}")

    src_r = src.resolve()
    dst_r = dst.resolve()
    if dst_r == src_r:
        raise MoveError(400, "Source and destination are the same path.")
    if src_r in dst_r.parents:
        raise MoveError(400, "Destination cannot be inside the source folder.")

    if dst.exists() and not dst.is_dir():
        raise MoveError(400, f"Destination exists and is not a folder: {dst}")

    try:
        merged = do_move(src, dst)
    except Exception as e:
        raise MoveError(500, str(e))

    return {"ok": True, "merged": merged}


# --- Graph evaluation ---------------------------------------------------------------
# The editor's former JS implementation is frozen in tests/golden/*.json, so JS
# semantics are kept (undefined vs null, truthiness, String(number), Object.keys
# order) — node type files in node_plugin/ use these helpers too.

# JS `undefined`, distinct from None (= JSON null), which must not count as missing.
class _Undefined:
    __slots__ = ()

    def __repr__(self):
        return "UNDEFINED"

    def __bool__(self):
        return False

    # A singleton: callers test `is UNDEFINED`, so copies must be itself.
    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self


UNDEFINED = _Undefined()


# --- JS semantics helpers --------------------------------------------------------


# obj[key] with JS's missing-key -> undefined (and undefined/null obj -> undefined).
# Typed Any: the value is whatever the JSON held, so callers branch on it themselves.
def jget(obj, key) -> Any:
    if isinstance(obj, dict) and key in obj:
        return obj[key]
    return UNDEFINED


def jidx(lst, i) -> Any:
    if isinstance(lst, list) and 0 <= i < len(lst):
        return lst[i]
    return UNDEFINED


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def js_truthy(v):
    if v is UNDEFINED or v is None:
        return False
    if isinstance(v, bool):
        return v
    if is_number(v):
        return not (v == 0 or (isinstance(v, float) and math.isnan(v)))
    if isinstance(v, str):
        return v != ""
    return True


def js_or(a, b) -> Any:
    return a if js_truthy(a) else b


def js_trim(s):
    return s.strip(JS_WS_CHARS)


# Number::toString (ECMA-262 Number.prototype.toString, radix 10).
def js_number_str(n):
    if isinstance(n, int):
        if abs(n) < 10 ** 21:
            return str(n)
        n = float(n)
    if math.isnan(n):
        return "NaN"
    if math.isinf(n):
        return "Infinity" if n > 0 else "-Infinity"
    if n == 0:
        return "0"
    sign = "-" if n < 0 else ""
    _, digits, exp = Decimal(repr(abs(n))).as_tuple()
    s = "".join(map(str, digits)).rstrip("0") or "0"
    k = len(s)
    point = int(exp) + len(digits)  # value = 0.s × 10^point (exp is an int for finite n)
    if k <= point <= 21:
        return sign + s + "0" * (point - k)
    if 0 < point <= 21:
        return sign + s[:point] + "." + s[point:]
    if -6 < point <= 0:
        return sign + "0." + "0" * (-point) + s
    e = point - 1
    mant = s if k == 1 else s[0] + "." + s[1:]
    return sign + mant + "e" + ("+" if e >= 0 else "-") + str(abs(e))


def js_string(v):
    if v is UNDEFINED:
        return "undefined"
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if is_number(v):
        return js_number_str(v)
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return ",".join("" if x is UNDEFINED or x is None else js_string(x) for x in v)
    return "[object Object]"


_FLOAT_PREFIX_RE = re.compile(r"[+-]?(?:Infinity|(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)")


def js_parse_float(v):
    m = _FLOAT_PREFIX_RE.match(js_string(v).lstrip(JS_WS_CHARS))
    return float(m.group(0)) if m else math.nan


# Object.keys order: array-index-like keys first (ascending), then insertion order.
def js_keys(obj):
    index_keys, other = [], []
    for k in obj:
        if re.fullmatch(r"0|[1-9][0-9]*", k) and int(k) < 2 ** 32 - 1:
            index_keys.append(k)
        else:
            other.append(k)
    return sorted(index_keys, key=int) + other


# --- Value helpers -------------------------------------------------------------


# A value only counts as "actually arrived" once it's neither missing nor blank —
# an unconnected port and a port resolving to "" are both "not present".
def is_present(v):
    return v is not UNDEFINED and v is not None and not (isinstance(v, str) and v == "")


# A value as the editor shows it (6 decimals at most; missing/blank spelled out).
def fmt_value(v):
    if v is UNDEFINED or v is None:
        return "(unconnected)"
    if is_number(v):
        scaled = v * 1e6
        # Math.round: halves round up, unlike Python's round().
        return js_number_str(math.floor(scaled + 0.5) / 1e6 if math.isfinite(scaled) else scaled / 1e6)
    if v == "":
        return "(empty string)"
    return js_string(v)


def to_number(v):
    if v is UNDEFINED or v is None or (isinstance(v, str) and v == ""):
        return 0.0
    n = float(v) if is_number(v) else js_parse_float(v)
    return 0.0 if math.isnan(n) else n


def to_str(v):
    return "" if v is UNDEFINED or v is None else js_string(v)


def _parse_named_placeholder(kind, raw):
    hash_idx = raw.find("#")
    if hash_idx == -1:
        return {"kind": kind, "name": raw, "defaultValue": "0" if kind == "number" else ""}
    return {"kind": kind, "name": js_trim(raw[:hash_idx]), "defaultValue": js_trim(raw[hash_idx + 1:])}


def _parse_select_placeholder(raw):
    options = [js_trim(o) for o in raw.split(",")]
    return {"kind": "select", "name": raw, "options": options, "defaultValue": options[0]}


def _match_placeholder(m):
    if m.group(1) is not None:
        return {"kind": "shuffle", "name": m.group(1)}
    if m.group(2) is not None:
        return _parse_named_placeholder("number", m.group(2))
    if m.group(3) is not None:
        return _parse_named_placeholder("string", m.group(3))
    return _parse_select_placeholder(m.group(4))


def extract_placeholders(text):
    items = []
    seen = set()
    for m in PLACEHOLDER_RE.finditer(js_string(js_or(text, ""))):
        p = _match_placeholder(m)
        if p["kind"] == "shuffle":
            continue
        key = f"{p['kind']}:{p['name']}"
        if key not in seen:
            seen.add(key)
            items.append({"key": key, "name": p["name"], "kind": p["kind"], "defaultValue": p["defaultValue"], "options": p.get("options", UNDEFINED)})
    return items


def fill_placeholders(text, values_by_key):
    def repl(m):
        p = _match_placeholder(m)
        v = jget(values_by_key or {}, f"{p['kind']}:{p['name']}")
        return js_string(v) if v is not UNDEFINED else m.group(0)
    return PLACEHOLDER_RE.sub(repl, js_string(js_or(text, "")))


# "{{a|b|c}}" is no field (never filled, so it reaches the job's prompt as is): each
# send to Codex shuffles its "|" parts and joins them with newlines. Parts aren't
# trimmed, so "{{  - a|  - b}}" stays a bullet list (SHUFFLE_RE in data.py).


def resolve_shuffle(text: str) -> str:
    def repl(m):
        parts = m.group(1).split("|")
        random.shuffle(parts)
        return "\n".join(parts)
    return SHUFFLE_RE.sub(repl, text)


# --- Group / Wrapper -------------------------------------------------------------


def _node_type(nodes, node_id):
    node = jget(nodes, node_id)
    return node["type"] if isinstance(node, dict) else UNDEFINED


def group_member_ids(group_id, edges):
    return [e["to"]["node"] for e in edges
            if e["from"]["node"] == group_id and e["from"]["port"] == GROUP_REF_PORT_ID and e["to"]["port"] == TRIGGER_PORT_ID]


def wrapper_linked_node_id(wrapper_id, edges):
    for e in edges:
        if e["from"]["node"] == wrapper_id and e["from"]["port"] == WRAPPER_REF_PORT_ID and e["to"]["port"] == TRIGGER_PORT_ID:
            return e["to"]["node"]
    return UNDEFINED


def wrapper_outputs_ready(node):
    groups = js_or(jget(node["data"], "conditionGroups"), [])
    return len(groups) == 0 or jget(node["data"], "wrapperPassed") is True


def _edge_with(e, frm, to, edge_id):
    return {**e, "from": frm, "to": to, "id": edge_id}


def expand_group_edges(nodes, edges):
    def member_ends(node_id, port, side):
        node = jget(nodes, node_id)
        if not isinstance(node, dict) or node["type"] != "group":
            return None
        if side == "from" and port == GROUP_REF_PORT_ID:
            return None
        key = "outputs" if side == "from" else "inputs"
        ends = []
        for mid in group_member_ids(node_id, edges):
            if _node_type(nodes, mid) not in GROUP_MEMBER_TYPES:
                continue
            p = next((p for p in get_node_def(nodes[mid], nodes, edges)[key] if p["label"] == port), None)
            if p:
                ends.append({"node": mid, "port": p["id"]})
        return ends

    out = []
    for e in edges:
        froms = member_ends(e["from"]["node"], e["from"]["port"], "from")
        tos = member_ends(e["to"]["node"], e["to"]["port"], "to")
        if froms is None and tos is None:
            out.append(e)
            continue
        for frm in (froms if froms is not None else [e["from"]]):
            for to in (tos if tos is not None else [e["to"]]):
                eid = f"{js_string(jget(e, 'id'))}~{frm['node']}:{frm['port']}>{to['node']}:{to['port']}"
                out.append(_edge_with(e, frm, to, eid))
    return out


def expand_wrapper_edges(nodes, edges):
    def real_end(node_id, port, side, bypass_gate):
        node = jget(nodes, node_id)
        if not isinstance(node, dict) or node["type"] != "wrapper":
            return None
        if side == "from" and port == WRAPPER_REF_PORT_ID:
            return None
        if side == "from" and not bypass_gate and not wrapper_outputs_ready(node):
            return None
        linked_id = wrapper_linked_node_id(node_id, edges)
        if linked_id is UNDEFINED or _node_type(nodes, linked_id) != "template":
            return None
        return {"node": linked_id, "port": port}

    out = []
    for e in edges:
        # A type's READS_UNGATED inputs (Gate's compare/value) read through the Wrapper's
        # gate: the Gate judges on its own, and gating it would leave a never-passing
        # node's compare wire unresolved forever (AND/OR would both just wait).
        bypass_gate = e["to"]["port"] in getattr(node_type(_node_type(nodes, e["to"]["node"])), "READS_UNGATED", ())
        frm = real_end(e["from"]["node"], e["from"]["port"], "from", bypass_gate)
        to = real_end(e["to"]["node"], e["to"]["port"], "to", False)
        if frm is None and to is None:
            out.append(e)
            continue
        real_from = frm or e["from"]
        real_to = to or e["to"]
        eid = f"{js_string(jget(e, 'id'))}~w:{real_from['node']}:{real_from['port']}>{real_to['node']}:{real_to['port']}"
        out.append(_edge_with(e, real_from, real_to, eid))
    return out


# The one edge-expansion pipeline — evaluation, runs and waiting reasons all use
# this, never their own copy (the old browser runner once expanded only Group
# edges itself, so Per-wire Gate edges stayed unsplit and Queue silently received
# nothing). Afterwards every edge is between two real node ports. Order: Group,
# then Wrapper, then each type's own expand_edges in registry order — Wrapper must
# come before Per-wire Gate (a Gate's compare can be fed through a Wrapper; skipping
# it keys the compare wiring by the Wrapper's id while the Gate keys
# 'value_out@<id>' by the linked AI Node's id, so they never match), and
# both after Group (compare's real member wiring only exists then).
def expand_edges(nodes, edges):
    edges = expand_group_edges(nodes, edges)
    edges = expand_wrapper_edges(nodes, edges)
    for spec in node_types().values():
        fn = getattr(spec, "expand_edges", None)
        if fn:
            edges = fn(nodes, edges)
    return edges


# --- Node definitions ------------------------------------------------------------


def make_port(id, label, type):
    return {"id": id, "label": label, "type": type}


def port_type_for_field(field):
    vt = jget(field, "valueType")
    if vt in ("number", "integer"):
        return "number"
    if vt == "array":
        return "any"
    return "string"


def _merge_ports_by_label(member_defs, side):
    order = []
    by_label = {}
    for d in member_defs:
        for p in d.get(side) or []:
            existing = by_label.get(p["label"])
            if existing is None:
                by_label[p["label"]] = {"id": p["label"], "label": p["label"], "type": p["type"]}
                order.append(p["label"])
            elif existing["type"] != p["type"]:
                existing["type"] = "any"
    return [by_label[label] for label in order]


# Members are AI Nodes or Wrappers only (a Group has no trigger port, so no
# nesting); one merged port per label shared by its members, so one wire is
# sugar for wiring each member (expand_group_edges).
def _group_ports(node, nodes, edges):
    member_ids = [i for i in group_member_ids(node["id"], edges) if _node_type(nodes, i) in GROUP_MEMBER_TYPES]
    member_defs = [get_node_def(nodes[i], nodes, edges) for i in member_ids]
    return {
        "title": js_or(jget(node["data"], "title"), "Group"),
        "inputs": _merge_ports_by_label(member_defs, "inputs"),
        "outputs": _merge_ports_by_label(member_defs, "outputs"),
    }


# The linked AI Node's ports verbatim; none while unlinked.
def _wrapper_ports(node, nodes, edges):
    linked_id = wrapper_linked_node_id(node["id"], edges)
    linked = nodes[linked_id] if linked_id is not UNDEFINED and _node_type(nodes, linked_id) == "template" else None
    linked_def = get_node_def(linked, nodes, edges) if linked else None
    return {
        "title": js_or(jget(node["data"], "title"), "Wrapper"),
        "inputs": linked_def["inputs"] if linked_def else [],
        "outputs": linked_def["outputs"] if linked_def else [],
    }


# One input per placeholder of `content` (AI Node, Format).
def placeholder_inputs(content):
    return [{"id": p["key"], "label": p["name"], "type": "number" if p["kind"] == "number" else "string"}
            for p in extract_placeholders(content)]


def _template_ports(node, nodes, edges):
    data = node["data"]
    return {
        "title": js_or(jget(data, "title"), "AI Node"),
        "inputs": placeholder_inputs(jget(data, "content")),
        "outputs": [make_port(THREAD_ID_OUTPUT_KEY, "thread_id", "string")]
        + [make_port(jget(o, "key"), jget(o, "name"), port_type_for_field(o)) for o in js_or(jget(data, "outputs"), [])],
    }


# {"title", "inputs", "outputs"}: the type's static TITLE/INPUTS/OUTPUTS, overridden
# by its ports() (which only Group/Wrapper need nodes/edges for). An unknown type
# (e.g. a removed node type file) gets an empty stub.
def get_node_def(node, nodes=None, edges=None):
    spec = node_type(node["type"])
    if spec is None:
        return {"title": node["type"], "inputs": [], "outputs": []}
    d = {"title": getattr(spec, "TITLE", node["type"]), "inputs": getattr(spec, "INPUTS", []), "outputs": getattr(spec, "OUTPUTS", [])}
    ports = getattr(spec, "ports", None)
    if ports:
        d.update(ports(node, nodes or {}, edges or []))
    return d


# --- evaluate_all ----------------------------------------------------------------


# Evaluates every node to {portId: value} with its type's evaluate(node, io):
# {"values", "errors" (nodes caught in a cycle), "paramValues" (AI Nodes)}.
# Side-effect-free — it's both the editor's live view and what runs read.
def evaluate_all(nodes, edges):
    edges = expand_edges(nodes, edges)
    values = {}
    errors = {}
    param_values = {}
    state = {}
    # Last edge per target wins, like the JS object assignment.
    edge_by_target = {}
    for e in edges:
        edge_by_target[e["to"]["node"] + ":" + e["to"]["port"]] = e

    def read(e, node_id):
        if state.get(e["from"]["node"]) == 1:
            errors[node_id] = True
            return UNDEFINED
        outs = eval_node(e["from"]["node"])
        return jget(outs, e["from"]["port"]) if outs is not UNDEFINED else UNDEFINED

    def get_input(node_id, port_id):
        e = edge_by_target.get(node_id + ":" + port_id)
        return read(e, node_id) if e else UNDEFINED

    def get_inputs(node_id, port_id):
        return [read(e, node_id) for e in edges if e["to"]["node"] == node_id and e["to"]["port"] == port_id]

    def get_inputs_by_source(node_id, port_id):
        return [{"from": e["from"]["node"], "value": read(e, node_id)}
                for e in edges if e["to"]["node"] == node_id and e["to"]["port"] == port_id]

    # What a type's evaluate(node, io) reads its own inputs through.
    class IO:
        def __init__(self, node_id):
            self.node_id = node_id
            self.nodes = nodes
            # Expanded (real port to real port).
            self.edges = edges

        # The value wired into `port` (UNDEFINED if unwired). One wire per port;
        # the multi-wire variants below give one value per wire.
        def input(self, port):
            return get_input(self.node_id, port)

        def inputs(self, port):
            return get_inputs(self.node_id, port)

        # [{"from": source node id, "value"}] per wire into `port`.
        def inputs_by_source(self, port):
            return get_inputs_by_source(self.node_id, port)

        def wired(self, port):
            return (self.node_id + ":" + port) in edge_by_target

        # Another node's title (UNDEFINED for a missing node).
        def title_of(self, node_id):
            src = jget(nodes, node_id)
            return get_node_def(src, nodes, edges)["title"] if isinstance(src, dict) else UNDEFINED

        # AI Node only: its resolved placeholder values (evaluate_all's "paramValues").
        def set_param_values(self, resolved):
            param_values[self.node_id] = resolved

    def eval_node(node_id):
        if state.get(node_id) == 2:
            return values[node_id]
        node = jget(nodes, node_id)
        if not isinstance(node, dict):
            return UNDEFINED
        state[node_id] = 1
        evaluate = getattr(node_type(node["type"]), "evaluate", None)
        outs = evaluate(node, IO(node_id)) if evaluate else {}
        state[node_id] = 2
        values[node_id] = outs
        return outs

    for node_id in js_keys(nodes):
        eval_node(node_id)
    return {"values": values, "errors": errors, "paramValues": param_values}


# --- Run-time helpers (WorkflowRunner) ------------------------------------------------


def js_strict_eq(a, b):
    # a === b: no cross-type equality (1 !== true), NaN !== NaN, objects by identity.
    if a is UNDEFINED or b is UNDEFINED or a is None or b is None:
        return a is b
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if is_number(a) and is_number(b):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    return a is b


def same_value(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(js_strict_eq(x, y) for x, y in zip(a, b))
    return js_strict_eq(a, b)


_JSON_ESCAPES = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _json_quote(s):
    return '"' + "".join(_JSON_ESCAPES.get(c) or (f"\\u{ord(c):04x}" if ord(c) < 0x20 else c) for c in s) + '"'


# JSON.stringify (no indent). Top-level undefined -> UNDEFINED, like JS.
def js_json_stringify(v):
    return UNDEFINED if v is UNDEFINED else _json(v)


# JSON.stringify of a defined value (undefined only reaches here as an array slot -> null).
def _json(v) -> str:
    if v is UNDEFINED or v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if is_number(v):
        return "null" if isinstance(v, float) and (math.isnan(v) or math.isinf(v)) else js_number_str(v)
    if isinstance(v, str):
        return _json_quote(v)
    if isinstance(v, list):
        return "[" + ",".join(_json(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(_json_quote(k) + ":" + _json(v[k]) for k in js_keys(v) if v[k] is not UNDEFINED) + "}"
    return "null"


def format_run_output_value(v):
    if v is UNDEFINED or v is None:
        return ""
    if isinstance(v, str):
        return v
    return _json(v)


def short_value(v, max_len=60):
    s = format_run_output_value(v)
    return s[: max_len - 1] + "…" if len(s) > max_len else s


# The value wired into a node's port, read from an evaluate_all result.
def resolve_wired_input(edges, ev, node_id, port_id):
    e = next((e for e in edges if e["to"]["node"] == node_id and e["to"]["port"] == port_id), None)
    return jget(ev["values"].get(e["from"]["node"]) or {}, e["from"]["port"]) if e else UNDEFINED


def wrapper_condition_matches(cond, raw_value):
    op = jget(cond, "op")
    if op in ("gt", "gte", "lt", "lte"):
        actual = to_number(raw_value)
        target = to_number(jget(cond, "value"))
        return {"gt": actual > target, "gte": actual >= target, "lt": actual < target, "lte": actual <= target}[op]
    candidates = [js_trim(v) for v in to_str(jget(cond, "value")).split(",")]
    is_match = to_str(raw_value) in candidates
    return not is_match if op == "neq" else is_match


# A condition with "total": true compares the sum of its field over the Wrapper's
# attempts so far (first run + retries; data.wrapperTotals) instead of the latest value.
def wrapper_condition_value(cond, output_values, totals=None):
    key = jget(cond, "key")
    if jget(cond, "total") is True:
        return _format_total(js_or(jget(totals or {}, key), 0))
    return jget(output_values or {}, key)


def _format_total(n):
    return int(n) if float(n).is_integer() else n


# totals plus this attempt's value of every field some "total" condition reads.
def add_wrapper_totals(condition_groups, totals, output_values):
    keys = {jget(c, "key") for g in js_or(condition_groups, []) for c in g if jget(c, "total") is True}
    out = dict(totals or {})
    for key in sorted(keys):
        out[key] = _format_total(to_number(js_or(jget(out, key), 0)) + to_number(jget(output_values or {}, key)))
    return out


def wrapper_conditions_pass(condition_groups, output_values, totals=None):
    groups = js_or(condition_groups, [])
    if len(groups) == 0:
        return True
    return any(len(group) > 0 and all(wrapper_condition_matches(c, wrapper_condition_value(c, output_values, totals)) for c in group)
               for group in groups)


# Run-result fields a Reset clears (Reset Results button and Reset nodes alike):
# the type's RESET (UNDEFINED = drop the field), plus __ranPassed for RAN_PASSED
# types; None for a type with none.
def reset_patch_for_node(node):
    spec = node_type(node["type"])
    if spec is None:
        return None
    patch = copy.deepcopy(getattr(spec, "RESET", None) or {})
    if getattr(spec, "RAN_PASSED", False):
        patch["__ranPassed"] = UNDEFINED
    return patch or None


def with_data(nodes, node_id, patch):
    # {...nodes, [id]: {...node, data: {...node.data, ...patch}}}
    node = nodes[node_id]
    return {**nodes, node_id: {**node, "data": {**node["data"], **patch}}}


def apply_reset_to_nodes(prev_nodes):
    nxt = dict(prev_nodes)
    for node_id in js_keys(nxt):
        patch = reset_patch_for_node(nxt[node_id])
        if patch:
            nxt = with_data(nxt, node_id, patch)
    return nxt


def _build_field_json_schema(field):
    vt = jget(field, "valueType")
    desc = js_or(jget(field, "description"), "")
    if vt == "enum":
        return {"type": "string", "enum": [v for v in js_or(jget(field, "enumValues"), []) if not (isinstance(v, str) and v == "")], "description": desc}
    if vt == "array":
        return {"type": "array", "description": desc, "items": build_output_json_schema(jget(field, "children"))}
    return {"type": js_or(vt, "string"), "description": desc}


def build_output_json_schema(fields):
    properties = {}
    required = []
    for f in js_or(fields, []):
        name = jget(f, "name")
        if not js_truthy(name):
            continue
        properties[name] = _build_field_json_schema(f)
        required.append(name)
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


# Kahn's algorithm, one round per level: the order run_workflow runs AI Nodes in.
def node_levels_in_dependency_order(nodes, edges):
    keys = js_keys(nodes)
    adj = {k: [] for k in keys}
    indegree = {k: 0 for k in keys}
    for e in edges:
        if e["from"]["node"] not in adj or e["to"]["node"] not in indegree:
            continue
        adj[e["from"]["node"]].append(e["to"]["node"])
        indegree[e["to"]["node"]] += 1
    remaining = list(keys)
    levels = []
    while remaining:
        level = [k for k in remaining if indegree[k] == 0]
        # A cycle leaves nothing at indegree 0 — release whatever's left.
        if not level:
            level = list(remaining)
        for k in level:
            remaining.remove(k)
            for nxt in adj[k]:
                indegree[nxt] -= 1
        levels.append(level)
    return levels


# Node ids (in first-seen order) whose trigger port is wired but not truthy.
def compute_trigger_blocked_nodes(nodes, edges):
    ev = evaluate_all(nodes, edges)
    blocked = []
    for e in edges:
        if e["to"]["port"] != TRIGGER_PORT_ID:
            continue
        if e["from"]["port"] in (GROUP_REF_PORT_ID, WRAPPER_REF_PORT_ID):
            continue
        signal = jget(ev["values"].get(e["from"]["node"]) or {}, e["from"]["port"])
        if not js_truthy(signal) and e["to"]["node"] not in blocked:
            blocked.append(e["to"]["node"])
    return blocked


# Saved nodes predating the "output" -> "sink" type rename.
def migrate_loaded_nodes(loaded_nodes):
    return {k: ({**n, "type": "sink"} if n.get("type") == "output" else n) for k, n in (loaded_nodes or {}).items()}


# --- Pre-run validation -------------------------------------------------------------
# validate_workflow() -> [{level, kind: 'schema'|'graph', message, nodeId?, edgeId?, fix?}].
# Errors block a run (the editor shows them live too). fix 'removeEdge' = the wire is
# ignored at run time, safe to drop. Schema messages keep ajv's wording (the editor's
# former JSON Schema check).


def is_int(v):
    return is_number(v) and math.isfinite(v) and float(v).is_integer()


def _check_template_data(data, nerr):
    if "content" not in data:
        nerr("/data", "must have required property 'content'")
    elif not isinstance(data["content"], str):
        nerr("/data/content", "must be string")
    if "outputs" in data and not isinstance(data["outputs"], list):
        nerr("/data/outputs", "must be array")


def _check_wrapper_data(data, nerr):
    if "maxRetries" in data and not (is_int(data["maxRetries"]) and data["maxRetries"] >= UNLIMITED_RETRIES):
        nerr("/data/maxRetries", f"must be an integer >= {UNLIMITED_RETRIES}")
    groups = data.get("conditionGroups", UNDEFINED)
    if groups is UNDEFINED:
        return
    if not isinstance(groups, list):
        nerr("/data/conditionGroups", "must be array")
        return
    for gi, group in enumerate(groups):
        if not isinstance(group, list):
            nerr(f"/data/conditionGroups/{gi}", "must be array")
            continue
        for ci, cond in enumerate(group):
            cpath = f"/data/conditionGroups/{gi}/{ci}"
            if not isinstance(cond, dict):
                nerr(cpath, "must be object")
                continue
            for key in ("key", "op"):
                if key not in cond:
                    nerr(cpath, f"must have required property '{key}'")
            if "key" in cond and not isinstance(cond["key"], str):
                nerr(cpath + "/key", "must be string")
            if "op" in cond and cond["op"] not in WRAPPER_CONDITION_OPS:
                nerr(cpath + "/op", "must be equal to one of the allowed values")
            if "total" in cond and not isinstance(cond["total"], bool):
                nerr(cpath + "/total", "must be boolean")


def _schema_issues(workflow):
    issues = []

    def err(path, message, node_id=UNDEFINED, edge_id=UNDEFINED):
        issues.append({"level": "error", "kind": "schema", "message": f"{path or '(root)'} {message}", "nodeId": node_id, "edgeId": edge_id})

    def nonempty_str(v):
        return isinstance(v, str) and len(v) >= 1

    nodes = workflow["nodes"]
    edges = workflow["edges"]
    if not isinstance(nodes, dict):
        err("/nodes", "must be object")
    else:
        for nid, node in nodes.items():
            def nerr(sub, message, _path=f"/nodes/{nid}", _nid=nid):
                err(_path + sub, message, node_id=_nid)

            if not isinstance(node, dict):
                nerr("", "must be object")
                continue
            for key in ("id", "type", "x", "y", "data"):
                if key not in node:
                    nerr("", f"must have required property '{key}'")
            if "id" in node and not nonempty_str(node["id"]):
                nerr("/id", "must be a non-empty string")
            if "type" in node and not (isinstance(node["type"], str) and node["type"] in node_types()):
                nerr("/type", "must be equal to one of the allowed values")
            for key in ("x", "y"):
                if key in node and not is_number(node[key]):
                    nerr(f"/{key}", "must be number")
            for key in ("width", "bodyHeight"):
                if key in node and not (is_number(node[key]) and node[key] > 0):
                    nerr(f"/{key}", "must be a number > 0")
            data = node.get("data", UNDEFINED)
            if data is not UNDEFINED and not isinstance(data, dict):
                nerr("/data", "must be object")
            check_data = getattr(node_type(node.get("type")), "check_data", None)
            if isinstance(data, dict) and check_data:
                check_data(data, nerr)

    if not isinstance(edges, list):
        err("/edges", "must be array")
    else:
        for i, e in enumerate(edges):
            path = f"/edges/{i}"
            if not isinstance(e, dict):
                err(path, "must be object")
                continue
            edge_id = e["id"] if isinstance(e.get("id"), str) else UNDEFINED
            for key in ("id", "from", "to"):
                if key not in e:
                    err(path, f"must have required property '{key}'", edge_id=edge_id)
            if "id" in e and not nonempty_str(e["id"]):
                err(path + "/id", "must be a non-empty string", edge_id=edge_id)
            for side in ("from", "to"):
                if side not in e:
                    continue
                end = e[side]
                if not isinstance(end, dict):
                    err(f"{path}/{side}", "must be object", edge_id=edge_id)
                    continue
                for key in ("node", "port"):
                    if key not in end:
                        err(f"{path}/{side}", f"must have required property '{key}'", edge_id=edge_id)
                    elif not nonempty_str(end[key]):
                        err(f"{path}/{side}/{key}", "must be a non-empty string", edge_id=edge_id)
    return issues


# Ports taking several incoming wires: the trigger port, and each type's MULTI_INPUTS.
def port_accepts_multiple(node, port_id):
    if port_id == TRIGGER_PORT_ID:
        return True
    if not node:
        return False
    return port_id in getattr(node_type(node["type"]), "MULTI_INPUTS", ())


# Real port ids a node exposes on one side, including the core's header/ref dots.
def _node_port_ids(node, nodes, edges, side):
    d = get_node_def(node, nodes, edges)
    spec = node_type(node["type"])
    ids = [p["id"] for p in (d["inputs"] if side == "in" else d["outputs"])]
    return ids + list(getattr(spec, "EXTRA_INPUTS" if side == "in" else "EXTRA_OUTPUTS", ()))


def _graph_issues(nodes, edges):
    issues = []

    def add(level, message, **ref):
        issues.append({"level": level, "kind": "graph", "message": message, **ref})

    def title(node):
        return js_string(get_node_def(node, nodes, edges)["title"])

    def port_label(node, port_id):
        p = next((p for p in get_node_def(node, nodes, edges)["inputs"] if p["id"] == port_id), None)
        return js_string(p["label"]) if p else port_id

    # What a type's check(node, chk) reports through, bound to that node.
    class Check:
        def __init__(self, node):
            self.node = node
            self.nodes = nodes
            self.edges = edges

        def add(self, level, message):
            add(level, message, nodeId=self.node["id"])

        # Quoted-ready display title of this node (or another one).
        def title(self, other=None):
            return title(other or self.node)

        def port_label(self, port_id):
            return port_label(self.node, port_id)

        def wired(self, port_id):
            return any(e["to"]["node"] == self.node["id"] and e["to"]["port"] == port_id for e in edges)

        def wired_out(self, port_id):
            return any(e["from"]["node"] == self.node["id"] and e["from"]["port"] == port_id for e in edges)

        # How many nodes of type t the workflow has.
        def count(self, t):
            return sum(1 for n in nodes.values() if n["type"] == t)

    for key in js_keys(nodes):
        if nodes[key]["id"] != key:
            add("error", f'Node key "{key}" does not match its id "{nodes[key]["id"]}".', nodeId=key)

    seen_edge_ids = set()
    wires_by_target = {}
    for e in edges:
        eid = e["id"]
        if eid in seen_edge_ids:
            add("error", f'Duplicate wire id "{eid}".', edgeId=eid)
        seen_edge_ids.add(eid)
        from_node = nodes.get(e["from"]["node"])
        to_node = nodes.get(e["to"]["node"])
        if not from_node or not to_node:
            missing = e["from"]["node"] if not from_node else e["to"]["node"]
            add("warning", f'Wire {eid} points at a missing node "{missing}" — ignored at run time.',
                edgeId=eid, nodeId=e["from"]["node"] if from_node else e["to"]["node"] if to_node else UNDEFINED, fix="removeEdge")
            continue
        if e["from"]["port"] not in _node_port_ids(from_node, nodes, edges, "out"):
            add("warning", f'"{title(from_node)}" has no output port "{e["from"]["port"]}" any more — wire {eid} is ignored at run time.',
                edgeId=eid, nodeId=from_node["id"], fix="removeEdge")
        if e["to"]["port"] not in _node_port_ids(to_node, nodes, edges, "in"):
            add("warning", f'"{title(to_node)}" has no input port "{e["to"]["port"]}" any more — wire {eid} is ignored at run time.',
                edgeId=eid, nodeId=to_node["id"], fix="removeEdge")
            continue
        wires_by_target.setdefault(e["to"]["node"] + ":" + e["to"]["port"], []).append(e)
    for lst in wires_by_target.values():
        node = nodes[lst[0]["to"]["node"]]
        port = lst[0]["to"]["port"]
        if len(lst) > 1 and not port_accepts_multiple(node, port):
            add("error", f'"{title(node)}" input "{port_label(node, port)}" has {len(lst)} wires but takes only one.', nodeId=node["id"])

    for key in js_keys(nodes):
        node = nodes[key]
        check = getattr(node_type(node["type"]), "check", None)
        if check:
            check(node, Check(node))
    return issues


def validate_workflow(nodes, edges):
    schema = _schema_issues({"nodes": nodes, "edges": edges})
    # Graph checks dereference node/edge fields freely — skip them on malformed input.
    if any(i["level"] == "error" for i in schema):
        return schema
    return schema + _graph_issues(nodes, edges)


# --- API contract (POST /workflows/{id}/runs) ----------------------------------------
# The workflow's API Input / API Response node (core types below) — one of each per
# workflow, as validated.


def _api_node(nodes, t):
    return next((k for k in js_keys(nodes) if nodes[k].get("type") == t), None)


# {"inputs": [{"name", "type", "default"}], "response": [field, ...] | None}.
def api_contract(nodes):
    input_id, response_id = _api_node(nodes, "apiInput"), _api_node(nodes, "apiResponse")
    params = _api_params(nodes[input_id].get("data") or {}) if input_id else []
    return {"inputs": [{"name": p["name"], "type": p["valueType"], "default": None if p["value"] is UNDEFINED else p["value"]}
                       for p in params],
            "response": _api_fields(nodes[response_id].get("data") or {}) if response_id else None}


# Returns nodes with each query value as its API Input parameter's value. ValueError
# (shown to the caller) on an unknown or missing parameter, or a non-number for a number one.
def apply_api_inputs(nodes, query):
    input_id = _api_node(nodes, "apiInput")
    params = _api_params(nodes[input_id].get("data") or {}) if input_id else []
    names = [p["name"] for p in params]
    unknown = [k for k in query if k not in names]
    if unknown:
        raise ValueError(f"Unknown parameter(s): {', '.join(unknown)}. This workflow takes: {', '.join(names) or '(none)'}.")
    # Blank/reserved names are pre-run errors, reported when the run is blocked.
    missing = [n for n in dict.fromkeys(names) if n and n != API_WAIT_PARAM and n not in query]
    if missing:
        raise ValueError(f"Missing parameter(s): {', '.join(missing)}.")
    if input_id is None:
        return nodes
    return with_data(nodes, input_id, _api_apply(nodes[input_id]["data"], query))


# --- Node types ---------------------------------------------------------------------
# One node type per file in node_plugin/ (loaded in file name order, which is also
# the order of the add-node menu's Plugin Node list; "_"-prefixed files are skipped —
# _template.py is the starting point for a new one), plus the core's AI Node /
# Group / Wrapper / API Input / API Response below (the menu's Default Node list).
# A file is a plain module; everything but TYPE is optional:
#   TYPE, TITLE, INPUTS, OUTPUTS (make_port lists), DEFAULT_DATA, BODY_HEIGHT, COLOR
#   ports(node, nodes, edges) -> {"inputs"?, "outputs"?, "title"?}  ports from data
#   evaluate(node, io) -> {port id: value}  live value of each output (side-effect-free)
#   MULTI_INPUTS       input ports that take several wires
#   READS_UNGATED      inputs read through a Wrapper's not-yet-passed gate
#   expand_edges(nodes, edges) -> edges  rewrites this type's edges before evaluation
#   check_data(data, nerr)  shape checks; check(node, chk)  wiring checks (pre-run)
#   waiting(node, w) -> [line]  why it hasn't fired yet (hourglass tooltip)
#   RAN_PASSED, ran_passed(node, outs)  "produced a value" is its run outcome
#   run_state(node, outs, running) -> {"running", "passed"}  card border
#   RESET              data patch Reset clears (UNDEFINED drops a field)
#   settle(node, ctx), fire(node, ctx), SIGNAL_PORT, on_stop(node) -> patch  runs
#   RUNNABLE           the Run button needs a node of such a type
#   body(node, view) -> [widget]   card body;  FIELDS / fields(node) -> [widget]  edit panel
#   RUN_OUTPUT         its "out" is listed in a run's outputs (Output)
# Widgets (rendered by index.html): body — caption, chip, chips, value, pairs,
# path, open, error, alert; fields — text, number, select, toggle, list, records,
# button, caption. See node_plugin/_template.py for their keys.

NODE_PLUGIN_DIR = Path(__file__).resolve().parent / "node_plugin"

_node_types: dict | None = None
_node_types_lock = threading.Lock()
# "file: error" for each file that failed to load (GET /node-types shows them).
node_type_load_errors: list[str] = []


def _load_node_types():
    types = {}
    errors = []
    for path in sorted(NODE_PLUGIN_DIR.glob("*.py"), key=lambda p: p.name):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"node_plugin.{path.stem}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            t = getattr(module, "TYPE", None)
            if not isinstance(t, str) or not t:
                raise ValueError("TYPE is not set")
            if t in types or t in CORE_NODE_TYPES:
                raise ValueError(f'type "{t}" is already defined')
            types[t] = module
        except Exception as e:
            errors.append(f"{path.name}: {e}")
            logger.error("Node type file %s failed to load: %s", path.name, e)
    types.update(CORE_NODE_TYPES)
    node_type_load_errors[:] = errors
    return types


# {type: definition}, in menu order. Loaded on first use (node type files import
# from this module, so they can't load while it's still importing).
def node_types():
    global _node_types
    if _node_types is None:
        with _node_types_lock:
            if _node_types is None:
                _node_types = _load_node_types()
    return _node_types


def node_type(t):
    return node_types().get(t) if isinstance(t, str) else None


# --- Core node types: AI Node (template), Group, Wrapper, API Input/Response ---------


def _template_evaluate(node, io):
    data = node["data"]
    resolved = {}
    node_values = jget(data, "values")
    for p in extract_placeholders(jget(data, "content")):
        from_edge = io.input(p["key"])
        if from_edge is not UNDEFINED:
            resolved[p["key"]] = from_edge
        elif js_truthy(node_values) and jget(node_values, p["key"]) is not UNDEFINED:
            resolved[p["key"]] = node_values[p["key"]]
        else:
            resolved[p["key"]] = p["defaultValue"]
    io.set_param_values(resolved)
    # threadId is known (and shown in the header) mid-run; the port only carries it once the run is done.
    done = jget(data, "runStatus") == "done"
    outs = {THREAD_ID_OUTPUT_KEY: js_or(jget(data, "threadId"), "") if done else ""}
    ov = js_or(jget(data, "outputValues"), {})
    for o in js_or(jget(data, "outputs"), []):
        key = js_string(jget(o, "key"))
        v = jget(ov, key)
        outs[key] = v if v is not UNDEFINED else ""
    return outs


def _template_check(node, chk):
    if not js_trim(to_str(jget(node["data"], "content"))):
        chk.add("error", f'"{chk.title()}" has empty content — nothing to send to Codex.')


def _template_waiting(node, w):
    return ["trigger: upstream signal has not passed"] if w.blocked else []


def _template_run_state(node, outs, running):
    status = jget(node["data"], "runStatus")
    return {"running": status in ("running", "starting"), "passed": status == "done"}


# Params/outputs aren't shown — the port rows carry their names, and full detail
# (prompt, schema, raw response) is the header's View button.
def _template_body(node, view):
    status = jget(node["data"], "runStatus")
    if status not in ("done", "skipped", "error", "stopped"):
        return []
    body = []
    if status == "done":
        body.append({"kind": "chip", "color": "success", "icon": "CheckCircle", "label": "Done"})
    if status == "skipped":
        body.append({"kind": "chip", "label": "Skipped"})
    if status in ("error", "stopped", "skipped"):
        body.append({"kind": "alert", "severity": "warning" if status == "skipped" else "error",
                     "text": to_str(js_or(jget(node["data"], "runError"), status))})
    return body


def _group_check(node, chk):
    if not group_member_ids(node["id"], chk.edges):
        chk.add("warning", f'"{chk.title()}" has no members.')


# Members are wired on canvas (Ref dot -> a AI Node's trigger dot); count only.
def _group_body(node, view):
    count = len(group_member_ids(node["id"], view.edges))
    return [{"kind": "caption", "text": f"{count} member{'' if count == 1 else 's'}" if count else "No members — drag from the Ref dot below"}]


def _wrapper_linked(node, nodes, edges):
    linked_id = wrapper_linked_node_id(node["id"], edges)
    return nodes.get(linked_id) if linked_id is not UNDEFINED else None


def _wrapper_check(node, chk):
    linked = _wrapper_linked(node, chk.nodes, chk.edges)
    if not linked or linked["type"] != "template":
        chk.add("warning", f'"{chk.title()}" is not linked to an AI Node.')
        return
    keys = [jget(o, "key") for o in js_or(jget(linked["data"], "outputs"), [])]
    for group in js_or(jget(node["data"], "conditionGroups"), []):
        for cond in group:
            if cond["key"] not in keys:
                chk.add("warning", f'"{chk.title()}" has a condition on an output "{cond["key"]}" that "{chk.title(linked)}" no longer has.')


# Which condition group fails, and on what — once the linked node finished without passing.
def _wrapper_waiting(node, w):
    groups = js_or(jget(node["data"], "conditionGroups"), [])
    linked = _wrapper_linked(node, w.nodes, w.edges)
    finished = linked is not None and jget(linked["data"], "runStatus") in ("done", "error", "stopped")
    if not groups or not finished or jget(node["data"], "wrapperPassed") is True:
        return []
    ov = js_or(jget(linked["data"], "outputValues"), {})
    totals = js_or(jget(node["data"], "wrapperTotals"), {})

    def name_of(key):
        o = next((o for o in js_or(jget(linked["data"], "outputs"), []) if jget(o, "key") == key), {})
        return js_or(jget(o, "name"), key)

    lines = []
    for gi, group in enumerate(groups):
        failing = [c for c in group if not wrapper_condition_matches(c, wrapper_condition_value(c, ov, totals))]
        if group and failing:
            parts = []
            for c in failing:
                got = wrapper_condition_value(c, ov, totals)
                label = ("total " if jget(c, "total") is True else "") + js_string(name_of(jget(c, "key")))
                parts.append(f"{label} {js_string(jget(c, 'op'))} {js_string(jget(c, 'value'))} "
                             f"(got {js_json_stringify(None if got is UNDEFINED else got)})")
            lines.append(f"group {gi + 1} unmet: {' AND '.join(parts)}")
    return lines


def _retries_label(max_retries):
    return "∞" if max_retries == UNLIMITED_RETRIES else js_string(max_retries)


def _wrapper_body(node, view):
    data = node["data"]
    groups = js_or(jget(data, "conditionGroups"), [])
    condition_count = sum(len(g) for g in groups)
    max_retries = jget(data, "maxRetries")
    max_retries = 3 if max_retries is UNDEFINED or max_retries is None else max_retries
    linked = _wrapper_linked(node, view.nodes, view.edges)
    body = [{"kind": "caption", "text": f"Wrapping: {js_string(view.title_of(linked['id']))}" if linked else "Not linked — drag from the Ref dot below"}]
    if groups:
        body.append({"kind": "caption", "text": f"{len(groups)} OR-group{'' if len(groups) == 1 else 's'}, "
                                                f"{condition_count} condition{'' if condition_count == 1 else 's'}"})
    attempt = jget(data, "wrapperAttempt")
    if is_number(attempt) and attempt > 0:
        body.append({"kind": "chip", "label": f"Attempt {js_string(attempt)}/{_retries_label(max_retries)}"})
    totals = jget(data, "wrapperTotals")
    if isinstance(totals, dict) and linked:
        names = {jget(o, "key"): jget(o, "name") for o in js_or(jget(linked["data"], "outputs"), [])}
        for key, total in totals.items():
            body.append({"kind": "chip", "label": f"Total {js_string(js_or(names.get(key), key))}: {js_string(total)}"})
    passed = jget(data, "wrapperPassed")
    if passed is not UNDEFINED:
        body.append({"kind": "chip", "color": "success" if passed else "error", "icon": "CheckCircle" if passed else "Cancel",
                     "label": "Condition satisfied" if passed else "Condition not met (retries exhausted)"})
    return body


# API Input: data.params = [{name, valueType: string|number, value}], one output port
# each ("param:<name>"); a call's query parameter replaces value (the test value an
# editor run uses). Every parameter is required. Prefix / types: data.py.


# Parameters with names trimmed, in order (blanks and repeats kept — check reports them).
def _api_params(data):
    params = jget(data, "params")
    if not isinstance(params, list):
        return []
    return [{"name": js_trim(to_str(jget(p, "name"))), "valueType": "number" if jget(p, "valueType") == "number" else "string",
             "value": jget(p, "value")} for p in params]


def _api_query_number(name, text):
    try:
        n = float(text)
    except ValueError:
        n = math.nan
    if not math.isfinite(n):
        raise ValueError(f'Parameter "{name}" must be a number.')
    return int(n) if n.is_integer() else n


# data patch with each query value (text) as its parameter's value, numbers parsed.
def _api_apply(data, query):
    filled = []
    for raw, p in zip(data["params"], _api_params(data)):
        if not isinstance(raw, dict) or p["name"] not in query:
            filled.append(raw)
            continue
        text = query[p["name"]]
        filled.append({**raw, "value": _api_query_number(p["name"], text) if p["valueType"] == "number" else text})
    return {"params": filled}


def _api_input_ports(node, nodes, edges):
    return {"outputs": [make_port(API_PARAM_PORT_PREFIX + p["name"], p["name"], p["valueType"]) for p in _api_params(node["data"])]}


def _api_input_evaluate(node, io):
    return {API_PARAM_PORT_PREFIX + p["name"]: to_number(p["value"]) if p["valueType"] == "number" else js_or(p["value"], "")
            for p in _api_params(node["data"])}


# "Produced" once every parameter has a value.
def _api_input_ran_passed(node, outs):
    return bool(outs) and all(is_present(v) for v in outs.values())


def _check_api_input_data(data, nerr):
    if "params" in data and not isinstance(data["params"], list):
        nerr("/data/params", "must be array")
    for i, p in enumerate(data["params"] if isinstance(data.get("params"), list) else []):
        ppath = f"/data/params/{i}"
        if not isinstance(p, dict):
            nerr(ppath, "must be object")
            continue
        if "name" in p and not isinstance(p["name"], str):
            nerr(ppath + "/name", "must be string")
        if "valueType" in p and p["valueType"] not in API_PARAM_VALUE_TYPES:
            nerr(ppath + "/valueType", "must be equal to one of the allowed values")


def _api_input_check(node, chk):
    count = chk.count("apiInput")
    if count > 1:
        chk.add("error", f"Only one API Input node is allowed (found {count}).")
    names = [p["name"] for p in _api_params(node["data"])]
    if not names:
        chk.add("warning", f'"{chk.title()}" has no parameters.')
    for i, name in enumerate(names):
        if not name:
            chk.add("error", f'"{chk.title()}" has a parameter with no name.')
        elif names.index(name) != i:
            chk.add("error", f'"{chk.title()}" parameter "{name}" is listed more than once.')
        elif name == API_WAIT_PARAM:
            chk.add("error", f'"{chk.title()}" parameter name "{name}" is reserved for the API\'s wait time.')
        elif not chk.wired_out(API_PARAM_PORT_PREFIX + name):
            chk.add("warning", f'"{chk.title()}" parameter "{name}" is not wired — its value is never used.')


# Count only — names are on the ports, test values stay private (like Text).
def _api_input_body(node, view):
    n = len(_api_params(node["data"]))
    if not n:
        return [{"kind": "caption", "color": "error", "text": "No parameters (click to edit)"}]
    return [{"kind": "caption", "text": f"{n} query parameter{'' if n == 1 else 's'} (click to edit)"}]


# API Response: one input per data.fields entry ("field:<name>"); its out is the
# {field: value} body an API call returns. Prefix: data.py.


# Field names, trimmed, in order (blanks and repeats kept — check reports them; a repeat shares one port).
def _api_fields(data):
    fields = jget(data, "fields")
    return [js_trim(to_str(f)) for f in fields] if isinstance(fields, list) else []


def _api_response_ports(node, nodes, edges):
    return {"inputs": [make_port(API_FIELD_PORT_PREFIX + f, f, "any") for f in _api_fields(node["data"])]}


def _api_response_evaluate(node, io):
    return {"out": {f: io.input(API_FIELD_PORT_PREFIX + f) for f in _api_fields(node["data"])}}


# "Produced" once every field has a value.
def _api_response_ran_passed(node, outs):
    out = jget(outs, "out")
    return bool(out) and all(is_present(v) for v in out.values())


def _check_api_response_data(data, nerr):
    if "fields" in data and not (isinstance(data["fields"], list) and all(isinstance(f, str) for f in data["fields"])):
        nerr("/data/fields", "must be an array of strings")


def _api_response_check(node, chk):
    count = chk.count("apiResponse")
    if count > 1:
        chk.add("error", f"Only one API Response node is allowed (found {count}).")
    fields = _api_fields(node["data"])
    if not fields:
        chk.add("warning", f'"{chk.title()}" has no fields — API calls get an empty response.')
    for i, f in enumerate(fields):
        if not f:
            chk.add("error", f'"{chk.title()}" has a field with no name.')
        elif fields.index(f) != i:
            chk.add("error", f'"{chk.title()}" field "{f}" is listed more than once.')
        elif not chk.wired(API_FIELD_PORT_PREFIX + f):
            chk.add("warning", f'"{chk.title()}" field "{f}" is not wired — it will always be null.')


# The response body as of now, one line per field.
def _api_response_body(node, view):
    fields = _api_fields(node["data"])
    if not fields:
        return [{"kind": "caption", "text": "No fields (click to edit)"}]
    out = jget(view.outs, "out")
    out = out if isinstance(out, dict) else {}
    return [{"kind": "pairs", "rows": [{"name": f or "(no name)", "value": fmt_value(jget(out, f))} for f in fields]}]


CORE_NODE_TYPES = {
    # AI Node: a Template Manager prompt run through Codex. Placed from the
    # menu's AI Node section, not the Default Node list (MENU False).
    "template": SimpleNamespace(
        TYPE="template", TITLE="AI Node", COLOR=TEMPLATE_HEADER_COLOR, MENU=False, RUNNABLE=True,
        EXTRA_INPUTS=(TRIGGER_PORT_ID,), ports=_template_ports, evaluate=_template_evaluate,
        check_data=_check_template_data, check=_template_check, waiting=_template_waiting,
        run_state=_template_run_state, body=_template_body,
        RESET={"runStatus": UNDEFINED, "runError": None, "threadId": None, "jobId": None, "lastRequest": None,
               "lastResponse": None, "outputValues": {}, "previousRun": UNDEFINED},
    ),
    # Ports and membership both come from the wiring (group_member_ids), never data.
    "group": SimpleNamespace(
        TYPE="group", TITLE="Group", BODY_HEIGHT=BODY_H_M, EXTRA_OUTPUTS=(GROUP_REF_PORT_ID,),
        ports=_group_ports, check=_group_check, body=_group_body,
    ),
    # Relays one linked AI Node's ports 1:1; its outputs come through only once
    # the conditions pass (wrapper_outputs_ready). data.conditionGroups = OR of groups,
    # each an AND of {key, op, value} rows (WRAPPER_CONDITION_OPS). Until a group holds,
    # the runner re-runs the node (up to data.maxRetries times). Edited by index.html's
    # own form (CUSTOM_FORM).
    "wrapper": SimpleNamespace(
        TYPE="wrapper", TITLE="Wrapper", BODY_HEIGHT=BODY_H_L, DEFAULT_DATA={"conditionGroups": [], "maxRetries": 3},
        EXTRA_INPUTS=(TRIGGER_PORT_ID,), EXTRA_OUTPUTS=(WRAPPER_REF_PORT_ID,), CUSTOM_FORM="wrapper",
        ports=_wrapper_ports, check_data=_check_wrapper_data, check=_wrapper_check, waiting=_wrapper_waiting,
        body=_wrapper_body, RESET={"wrapperAttempt": 0, "wrapperPassed": UNDEFINED, "wrapperTotals": UNDEFINED},
    ),
    # The workflow's API (POST /workflows/{id}/runs): api_contract / apply_api_inputs /
    # Run.response read these two directly. Renaming a parameter or field renames its
    # port, so a wire on the old name is left dangling (the pre-run check flags it).
    "apiInput": SimpleNamespace(
        TYPE="apiInput", TITLE="API Input", BODY_HEIGHT=BODY_H_S, RAN_PASSED=True,
        DEFAULT_DATA={"params": [{"name": "", "valueType": "string", "value": ""}]},
        ports=_api_input_ports, evaluate=_api_input_evaluate, ran_passed=_api_input_ran_passed,
        check_data=_check_api_input_data, check=_api_input_check, body=_api_input_body,
        FIELDS=[
            {"kind": "caption", "text": "Each parameter is an output port and a required query parameter of the API call."},
            {"kind": "records", "key": "params", "addLabel": "+ Add Parameter", "newItem": {"name": "", "valueType": "string", "value": ""}, "fields": [
                {"kind": "text", "key": "name", "label": "Name"},
                {"kind": "toggle", "key": "valueType", "default": "string", "options": [{"value": "string", "label": "Text"}, {"value": "number", "label": "Number"}]},
                {"kind": "text", "key": "value", "label": "Test value", "multiline": True, "helper": "Used when run from the editor"},
            ]},
        ],
    ),
    "apiResponse": SimpleNamespace(
        TYPE="apiResponse", TITLE="API Response", BODY_HEIGHT=BODY_H_L, RAN_PASSED=True, DEFAULT_DATA={"fields": ["result"]},
        ports=_api_response_ports, evaluate=_api_response_evaluate, ran_passed=_api_response_ran_passed,
        check_data=_check_api_response_data, check=_api_response_check, body=_api_response_body,
        FIELDS=[
            {"kind": "caption", "text": "Each field is an input port and a key in the API response."},
            {"kind": "list", "key": "fields", "placeholder": "field name", "addLabel": "+ Add Field"},
        ],
    ),
}


# --- Editor view (GET /node-types, POST /evaluate) -----------------------------------
# The editor draws everything type-specific from these two: the type list once,
# then this per canvas change (ports, card body, edit fields, border, issues).


# Static per-type info: what adding a node, the menu, Reset Results and onConnect need.
def node_types_info():
    types = []
    for t, spec in node_types().items():
        reset = reset_patch_for_node({"type": t}) or {}
        plugin = t not in CORE_NODE_TYPES
        types.append({
            "type": t, "title": getattr(spec, "TITLE", t),
            "color": getattr(spec, "COLOR", PLUGIN_NODE_HEADER_COLOR if plugin else DEFAULT_NODE_HEADER_COLOR),
            "inputs": getattr(spec, "INPUTS", []), "outputs": getattr(spec, "OUTPUTS", []),
            "defaultData": getattr(spec, "DEFAULT_DATA", {}), "defaultBodyHeight": getattr(spec, "BODY_HEIGHT", BODY_H_M),
            "multiInputs": list(getattr(spec, "MULTI_INPUTS", ())),
            "reset": {"set": {k: v for k, v in reset.items() if v is not UNDEFINED}, "unset": [k for k, v in reset.items() if v is UNDEFINED]},
            "runnable": getattr(spec, "RUNNABLE", False), "menu": getattr(spec, "MENU", True), "plugin": plugin,
            "customForm": getattr(spec, "CUSTOM_FORM", None),
        })
    return to_jsonable({"types": types, "errors": node_type_load_errors})


# What a type's waiting(node, w) reads.
class _WaitingView:
    def __init__(self, node, nodes, edges, eff, ev, run_state, blocked):
        self.node = node
        self.nodes = nodes
        self.edges = edges
        # This node's evaluate_all outputs.
        self.outs = ev["values"].get(node["id"]) or {}
        # Its run_state entry (WorkflowRunner.state) from the live run, else {}.
        self.state = (run_state or {}).get(node["id"]) or {}
        # AI Node: its trigger is wired but not passing.
        self.blocked = blocked
        self._eff = eff
        self._ev = ev

    def input_ids(self):
        return [p["id"] for p in get_node_def(self.node, self.nodes, self.edges)["inputs"]]

    def input_label(self, port_id):
        p = next((p for p in get_node_def(self.node, self.nodes, self.edges)["inputs"] if p["id"] == port_id), None)
        return js_string(p["label"]) if p else port_id

    # Of port_ids, those wired with no wire carrying a present value yet.
    def unarrived(self, port_ids):
        out = []
        for p in port_ids:
            wires = [e for e in self._eff if e["to"]["node"] == self.node["id"] and e["to"]["port"] == p]
            if wires and not any(is_present(jget(self._ev["values"].get(e["from"]["node"]) or {}, e["from"]["port"])) for e in wires):
                out.append(p)
        return out


# A waiting(node, w) for types that act once every wired input has a value.
def waiting_on_inputs(node, w):
    missing = w.unarrived(w.input_ids())
    return [f"not yet received: {', '.join(w.input_label(p) for p in missing)}"] if missing else []


# A waiting(node, w) for types fired by a signal on their SIGNAL_PORT.
def waiting_on_signal(node, w):
    port = getattr(node_type(node["type"]), "SIGNAL_PORT", "signal")
    return ["signal: not fired yet"] if w.unarrived([port]) else []


# {node_id: [line]}: why a node hasn't fired yet. run_state = the live run's "run_state".
def compute_waiting_reasons(nodes, edges, ev, run_state):
    eff = expand_edges(nodes, edges)
    blocked = compute_trigger_blocked_nodes(nodes, edges)
    reasons = {}
    for key in js_keys(nodes):
        node = nodes[key]
        waiting = getattr(node_type(node["type"]), "waiting", None)
        lines = waiting(node, _WaitingView(node, nodes, edges, eff, ev, run_state, node["id"] in blocked)) if waiting else None
        if lines:
            reasons.setdefault(node["id"], []).extend(lines)
    return reasons


# Card border per node: running (red, blinking) / passed (green) — from a real run's
# results, never the live evaluation alone. Wrappers then mirror their linked node's
# running, Groups roll up their members (a Group can hold Wrappers, never Groups).
def compute_run_states(nodes, edges, ev, running):
    by_id = {}
    for key in js_keys(nodes):
        node = nodes[key]
        spec = node_type(node["type"])
        fn = getattr(spec, "run_state", None)
        outs = ev["values"].get(node["id"]) or {}
        if fn:
            st = fn(node, outs, running)
        elif getattr(spec, "RAN_PASSED", False):
            st = {"running": False, "passed": jget(node["data"], "__ranPassed") is True}
        else:
            st = {"running": False, "passed": False}
        by_id[node["id"]] = {"running": bool(st["running"]), "passed": bool(st["passed"])}
    for key in js_keys(nodes):
        node = nodes[key]
        if node["type"] == "wrapper":
            linked_id = wrapper_linked_node_id(node["id"], edges)
            linked = by_id.get(linked_id) if linked_id is not UNDEFINED else None
            by_id[node["id"]] = {"running": bool(linked and linked["running"]), "passed": jget(node["data"], "wrapperPassed") is True}
    for key in js_keys(nodes):
        node = nodes[key]
        if node["type"] == "group":
            members = [by_id[i] for i in group_member_ids(node["id"], edges) if i in by_id]
            by_id[node["id"]] = {"running": any(m["running"] for m in members),
                                 "passed": len(members) > 0 and all(m["passed"] for m in members)}
    return by_id


# What a type's body(node, view) reads.
class _BodyView:
    def __init__(self, node, nodes, edges, ev):
        self.nodes = nodes
        self.edges = edges
        # This node's evaluate_all outputs.
        self.outs = ev["values"].get(node["id"]) or {}

    def title_of(self, node_id):
        n = self.nodes.get(node_id)
        return get_node_def(n, self.nodes, self.edges)["title"] if n else node_id


def _node_fields(spec, node):
    fn = getattr(spec, "fields", None)
    return fn(node) if fn else getattr(spec, "FIELDS", [])


# POST /evaluate: {"nodes": {id: {title, inputs, outputs, body, fields, running,
# passed, hasError, waiting}}, "issues": [...], "connected": ["node:port:in|out", ...]}.
def editor_view(nodes, edges, running=False, run_state=None):
    # A failing node type file must not take the whole view down (the editor would
    # read that as the server being gone).
    try:
        issues = validate_workflow(nodes, edges)
    except Exception as e:
        logger.warning("editor_view could not validate: %s", e)
        issues = [{"level": "error", "kind": "graph", "message": f"Pre-run check failed: {e}"}]
    try:
        ev = evaluate_all(nodes, edges)
        run_states = compute_run_states(nodes, edges, ev, running)
        waiting = compute_waiting_reasons(nodes, edges, ev, run_state)
    except Exception as e:
        # Only malformed input (already a schema error above) gets here.
        logger.warning("editor_view could not evaluate: %s", e)
        ev, run_states, waiting = {"values": {}, "errors": {}}, {}, {}
    view = {}
    for key in js_keys(nodes):
        node = nodes[key]
        if not isinstance(node, dict) or not isinstance(node.get("data"), dict):
            continue
        spec = node_type(node.get("type"))
        try:
            d = get_node_def(node, nodes, edges)
            body_fn = getattr(spec, "body", None)
            body = body_fn(node, _BodyView(node, nodes, edges, ev)) if body_fn else []
            fields = _node_fields(spec, node)
        except Exception as e:
            logger.warning("editor_view: node %s: %s", key, e)
            d, body, fields = {"title": node.get("type"), "inputs": [], "outputs": []}, [{"kind": "error", "text": str(e)}], []
        st = run_states.get(node.get("id"), {"running": False, "passed": False})
        view[key] = {**d, "body": body, "fields": fields, "running": st["running"], "passed": st["passed"],
                     "hasError": bool(ev["errors"].get(key)), "waiting": waiting.get(node.get("id"), [])}
    connected = set()
    try:
        for e in [*edges, *expand_group_edges(nodes, edges)]:
            connected.add(f"{e['from']['node']}:{e['from']['port']}:out")
            connected.add(f"{e['to']['node']}:{e['to']['port']}:in")
    except Exception:
        pass
    return to_jsonable({"nodes": view, "issues": issues, "connected": sorted(connected)})


# --- Workflow runner ----------------------------------------------------------------
# WorkflowRunner: one workflow run's control. Talks to the outside only through:
#   host:    get_nodes(), get_edges(), update_data(id, patch), apply_to_nodes(fn),
#            log(node_id, msg, level), notify(msg), on_running_change(bool),
#            on_run_blocked(count)
#   backend: async create_job(body) -> {"job_id"}, get_job(job_id) -> job dict,
#            stop_job(job_id), move_folder(src, dst, operation_id) -> {"merged"}
#            (raise on failure)

class AbortError(Exception):
    pass


# AbortController + AbortSignal in one: abort() is idempotent and runs callbacks.
class AbortController:
    def __init__(self):
        self.aborted = False
        self._event = asyncio.Event()
        self._callbacks = []

    def abort(self):
        if self.aborted:
            return
        self.aborted = True
        self._event.set()
        for cb in self._callbacks:
            cb()

    def on_abort(self, cb):
        self._callbacks.append(cb)


# Sleeps ms; raises AbortError as soon as `signal` aborts.
async def abortable_sleep(ms, signal=None):
    if signal is None:
        await asyncio.sleep(ms / 1000)
        return
    if signal.aborted:
        raise AbortError()
    try:
        await asyncio.wait_for(signal._event.wait(), timeout=ms / 1000)
    except asyncio.TimeoutError:
        return
    raise AbortError()


def new_operation_id():
    return str(uuid.uuid4())


# Number(v) — only what Delay's seconds needs (number or numeric string).
def js_to_number(v):
    if v is UNDEFINED:
        return float("nan")
    if v is None or v is False:
        return 0.0
    if v is True:
        return 1.0
    if is_number(v):
        return float(v)
    if isinstance(v, str):
        s = js_trim(v)
        if s == "":
            return 0.0
        if re.fullmatch(r"[+-]?(Infinity|([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?)", s):
            return float(s)
        if re.fullmatch(r"0[xX][0-9a-fA-F]+", s):
            return float(int(s, 16))
    return float("nan")


# --- Cascade ------------------------------------------------------------------------
# After each change a run re-settles the graph: per pass, every type's settle(node,
# ctx) (record verdicts, latch inputs — off one evaluation, ctx.ev), then its
# fire(node, ctx) (side effects, off a fresh evaluation, ctx.ev2), both in registry
# order. A type with SIGNAL_PORT fires only on a new value there (deduped per run).


# RAN_PASSED types: data.__ranPassed = the node produced a value (the type's
# ran_passed(node, outs), else its "out" is present) — the card's passed border.
def settle_ran_passed(node, ctx):
    outs = ctx.ev["values"].get(node["id"]) or {}
    ran_passed_fn = getattr(node_type(node["type"]), "ran_passed", None)
    ran_passed = ran_passed_fn(node, outs) if ran_passed_fn else is_present(jget(outs, "out"))
    if not js_strict_eq(jget(node["data"], "__ranPassed"), ran_passed):
        ctx.patch(node["id"], {"__ranPassed": ran_passed})


# What settle/fire get: ctx.runner (its host, backend, state(node_id)), ctx.nodes
# (this cascade's working copy), ctx.eff_edges (expanded), ctx.ev / ctx.ev2.


class _CascadeContext:
    def __init__(self, runner, nodes, eff_edges):
        self.runner = runner
        self.nodes = nodes
        self.eff_edges = eff_edges
        # evaluate_all results before / after the settle phase (set per pass).
        self.ev: dict = {}
        self.ev2: dict = {}
        self.changed = False

    # Working copy only (this cascade's later handlers/passes see it).
    def patch_working(self, node_id, patch):
        if node_id in self.nodes:
            self.nodes = with_data(self.nodes, node_id, patch)

    # UI state and working copy alike.
    def patch(self, node_id, patch):
        self.runner.host.update_data(node_id, patch)
        self.patch_working(node_id, patch)


class WorkflowRunner:
    def __init__(self, host, backend, poll_interval_ms=1500, max_concurrent_runs=10):
        self.host = host
        self.backend = backend
        self.poll_interval_ms = poll_interval_ms
        self.max_concurrent_runs = max_concurrent_runs
        self.is_running = False
        self.stop_requested = False
        self.run_no = 0
        self.active_run = {"id": 0, "key": None, "controller": None}
        self.running_job_ids = set()
        self.attempts = {}
        self._cascade_lock = asyncio.Lock()
        self.cascade_state = None
        # Fire-and-forget tasks and pending Delay timers — is_idle() reads both.
        self._tasks = set()
        self._timers = set()
        self.reset_run_state()

    # Per-node scratch state for this run (node types keep their latches, timers'
    # tokens, last fired signal here); cleared when a run starts. JSON-able, since
    # the run snapshot carries it as "run_state" for the editor's waiting reasons.
    def reset_run_state(self):
        self.run_state = {}

    def state(self, node_id):
        return self.run_state.setdefault(node_id, {})

    def run_stopped(self):
        controller = self.active_run["controller"]
        return bool(controller) and controller.aborted

    def spawn(self, coro):
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    # A fire-and-forget task's failure would otherwise vanish.
    def _task_done(self, task):
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            self.host.log(None, f"internal error: {task.exception()}", "error")

    # Calls fn() after `seconds`; is_idle() waits for it. fn must check for itself
    # that its run is still current (active_run["id"]) and not stopped.
    def schedule(self, seconds, fn):
        loop = asyncio.get_running_loop()

        def fire():
            self._timers.discard(handle)
            fn()

        # setTimeout treats a delay past 2^31-1 ms as ~0 — same here.
        handle = loop.call_later(seconds if seconds * 1000 <= 2147483647 else 0.001, fire)
        self._timers.add(handle)

    # Nothing left that could change state (a stopped run's timers no-op — see schedule).
    def is_idle(self):
        return not self.is_running and not self._tasks and (not self._timers or self.run_stopped())

    async def run_workflow(self):
        if self.is_running:
            return
        pre_run_errors = [i for i in validate_workflow(self.host.get_nodes(), self.host.get_edges()) if i["level"] == "error"]
        if pre_run_errors:
            self.host.log(None, f"run blocked — {len(pre_run_errors)} pre-run error(s)", "error")
            self.host.on_run_blocked(len(pre_run_errors))
            return
        self.is_running = True
        self.stop_requested = False
        self.run_no += 1
        run_controller = AbortController()
        self.active_run = {"id": self.run_no, "key": new_operation_id(), "controller": run_controller}
        self.host.on_running_change(True)
        started_at = time.monotonic()
        self.host.log(None, "run started")
        self.reset_run_state()
        self._cascade_lock = asyncio.Lock()
        try:
            working_nodes = self.host.get_nodes()
            working_edges = self.host.get_edges()
            cleared = {}
            for node_id in js_keys(working_nodes):
                node = working_nodes[node_id]
                if node["type"] == "template":
                    cleared[node_id] = {"threadId": None, "outputValues": {}}
                if node["type"] == "wrapper":
                    cleared[node_id] = {"wrapperAttempt": 0, "wrapperPassed": UNDEFINED, "wrapperTotals": UNDEFINED}
            for node_id, patch in cleared.items():
                self.host.update_data(node_id, patch)
            for node_id, patch in cleared.items():
                working_nodes = with_data(working_nodes, node_id, patch)
            self.cascade_state = working_nodes
            working_nodes = await self.run_action_cascade(None, working_edges)
            levels = node_levels_in_dependency_order(working_nodes, working_edges)
            for level in levels:
                if self.stop_requested:
                    break
                template_ids = [i for i in level if working_nodes[i]["type"] == "template"]

                async def run_one(node_id):
                    if self.stop_requested:
                        return
                    if node_id in compute_trigger_blocked_nodes(self.cascade_state, working_edges):
                        self.host.update_data(node_id, {"runStatus": "skipped", "runError": "Waiting on trigger — upstream Gate did not pass."})
                        self.host.log(node_id, "skipped — trigger signal has not passed", "warning")
                        return
                    outcome = await self.run_template_node_wrapped(node_id, self.cascade_state, working_edges)
                    if run_controller.aborted:
                        return
                    patches = []
                    if outcome["result"]:
                        patches.append({"nodeId": node_id, "patch": {"outputValues": outcome["result"]["outputValues"], "threadId": outcome["result"]["threadId"], "runStatus": "done"}})
                    if outcome["wrapperPatch"]:
                        patches.append(outcome["wrapperPatch"])
                    await self.run_action_cascade(patches or None, working_edges)

                await _run_with_concurrency_limit(template_ids, self.max_concurrent_runs, run_one)
        finally:
            self.is_running = False
            self.host.on_running_change(False)
            secs = f"{time.monotonic() - started_at:.1f}"
            self.host.log(None, f"run stopped after {secs}s" if self.stop_requested else f"run finished in {secs}s",
                          "warning" if self.stop_requested else "success")

    def _stop_job_soon(self, job_id):
        async def go():
            try:
                await self.backend.stop_job(job_id)
            except Exception:
                pass
        self.spawn(go())

    def stop_workflow(self):
        self.stop_requested = True
        for job_id in list(self.running_job_ids):
            self._stop_job_soon(job_id)
        controller = self.active_run["controller"]
        if controller and not controller.aborted:
            controller.abort()
            if not self.is_running:
                self.host.log(None, "stopped pending Delays", "warning")
        nodes = self.host.get_nodes()
        for node_id in js_keys(nodes):
            on_stop = getattr(node_type(nodes[node_id]["type"]), "on_stop", None)
            patch = on_stop(nodes[node_id]) if on_stop else None
            if patch:
                self.host.update_data(node_id, patch)

    def stop_node(self, node_id):
        attempt = self.attempts.get(node_id)
        if not attempt:
            return
        if attempt["jobId"]:
            self._stop_job_soon(attempt["jobId"])
        attempt["controller"].abort()

    def retry_node(self, node_id):
        node = self.host.get_nodes().get(node_id)
        if not node or self.is_running:
            return
        if jget(node["data"], "runStatus") in ("running", "starting"):
            return
        self.stop_requested = False
        self.spawn(self.run_template_node_wrapped(node_id))

    def begin_attempt(self, node_id):
        prev = self.attempts.get(node_id)
        if prev:
            prev["controller"].abort()
            if prev["jobId"]:
                self._stop_job_soon(prev["jobId"])
        controller = AbortController()
        run = self.active_run
        if self.is_running and run["controller"]:
            if run["controller"].aborted:
                controller.abort()
            else:
                run["controller"].on_abort(controller.abort)
        attempt = {"controller": controller, "jobId": None}
        self.attempts[node_id] = attempt
        return attempt

    async def run_template_node(self, node_id, nodes_snapshot=None, edges_snapshot=None):
        host = self.host
        working_nodes = nodes_snapshot or host.get_nodes()
        working_edges = edges_snapshot or host.get_edges()
        node = working_nodes.get(node_id)
        if not node or node["type"] != "template":
            return None

        fresh_eval = evaluate_all(working_nodes, working_edges)
        resolved_params = fresh_eval["paramValues"].get(node_id) or {}
        prompt = js_trim(fill_placeholders(jget(node["data"], "content"), resolved_params))
        output_fields = js_or(jget(node["data"], "outputs"), [])
        schema = build_output_json_schema(output_fields)

        if not prompt:
            host.update_data(node_id, {"runStatus": "error", "runError": "Node content is empty — nothing to send."})
            host.log(node_id, "content is empty — nothing to send", "error")
            return None

        attempt = self.begin_attempt(node_id)
        signal = attempt["controller"]

        def is_current():
            return self.attempts.get(node_id) is attempt

        def write(patch):
            if is_current():
                host.update_data(node_id, patch)

        def log(message, level="info"):
            if is_current():
                host.log(node_id, message, level)

        # The attempt being replaced (if it ever ran) stays viewable as previousRun (Node Details).
        current = jget(host.get_nodes().get(node_id) or {}, "data")
        previous = {}
        if js_truthy(jget(current, "lastRequest")):
            previous = {"previousRun": {"runStatus": js_or(jget(current, "runStatus"), None), "runError": js_or(jget(current, "runError"), None),
                                        "response": js_or(jget(current, "lastResponse"), None)}}
        host.update_data(node_id, {
            "runStatus": "running", "runError": None, "threadId": None, "jobId": None,
            "lastRequest": {"prompt": prompt, "outputSchema": schema},
            "lastResponse": None, "outputValues": {}, **previous,
        })
        log("Codex job started")

        try:
            created = await self.backend.create_job({"prompt": prompt, "output_schema": schema, "node_id": node_id, "operation_id": new_operation_id()})
            job_id = created["job_id"]
            attempt["jobId"] = job_id
            self.running_job_ids.add(job_id)
            if signal.aborted:
                self._stop_job_soon(job_id)
                raise AbortError()
            write({"jobId": job_id})

            while True:
                await abortable_sleep(self.poll_interval_ms, signal)
                if signal.aborted:
                    raise AbortError()
                job = await self.backend.get_job(job_id)
                if not is_current():
                    return None
                if js_truthy(job.get("thread_id")):
                    write({"threadId": job["thread_id"]})
                status = job.get("status")
                if status in ("starting", "running"):
                    continue
                last_response = {"raw": js_or(job.get("response"), None), "output": js_or(job.get("output"), None),
                                 "status": status, "error": js_or(job.get("error"), None), "threadId": js_or(job.get("thread_id"), None)}
                if status == "done":
                    output = js_or(job.get("output"), {})
                    output_values = {}
                    for o in output_fields:
                        output_values[o["key"]] = format_run_output_value(jget(output, o["name"]))
                    write({"outputValues": output_values, "runStatus": "done", "runError": None, "lastResponse": last_response})
                    log("done", "success")
                    return {"outputValues": output_values, "threadId": js_or(job.get("thread_id"), None)}
                write({"runStatus": js_or(status, "error"), "runError": js_or(job.get("error"), "The job did not complete successfully."), "lastResponse": last_response})
                log(f"{js_string(js_or(status, 'error'))}: {js_string(js_or(job.get('error'), 'the job did not complete successfully'))}",
                    "warning" if status == "stopped" else "error")
                return None
        except AbortError:
            write({"runStatus": "stopped", "runError": "Stopped."})
            log("stopped", "warning")
            return None
        except Exception as e:
            write({"runStatus": "error", "runError": str(e)})
            log(f"error: {e}", "error")
            return None
        finally:
            if attempt["jobId"]:
                self.running_job_ids.discard(attempt["jobId"])
            if is_current():
                del self.attempts[node_id]

    async def run_template_node_wrapped(self, node_id, nodes_snapshot=None, edges_snapshot=None):
        host = self.host
        working_nodes = nodes_snapshot or host.get_nodes()
        working_edges = edges_snapshot or host.get_edges()
        wrapper = next((working_nodes[k] for k in js_keys(working_nodes)
                        if working_nodes[k]["type"] == "wrapper" and wrapper_linked_node_id(k, working_edges) == node_id), None)

        result = await self.run_template_node(node_id, nodes_snapshot, edges_snapshot)
        if not wrapper:
            return {"result": result, "wrapperPatch": None}

        condition_groups = js_or(jget(wrapper["data"], "conditionGroups"), [])
        max_retries = js_or(jget(wrapper["data"], "maxRetries"), 0)
        unlimited = max_retries == UNLIMITED_RETRIES
        max_retries = max(0, max_retries)
        attempt = 0
        totals = add_wrapper_totals(condition_groups, {}, result["outputValues"] if result else {})
        passed = bool(result) and wrapper_conditions_pass(condition_groups, result["outputValues"], totals)
        if totals:
            host.update_data(wrapper["id"], {"wrapperTotals": totals})
        while not passed and (unlimited or attempt < max_retries) and not self.stop_requested:
            attempt += 1
            host.log(wrapper["id"], f"conditions not met — retry {attempt}/{'∞' if unlimited else max_retries}", "warning")
            host.update_data(wrapper["id"], {"wrapperAttempt": attempt})
            result = await self.run_template_node(node_id, nodes_snapshot, edges_snapshot)
            if result:
                totals = add_wrapper_totals(condition_groups, totals, result["outputValues"])
                if totals:
                    host.update_data(wrapper["id"], {"wrapperTotals": totals})
            passed = bool(result) and wrapper_conditions_pass(condition_groups, result["outputValues"], totals)
        if condition_groups:
            host.log(wrapper["id"], "conditions met" if passed else "conditions not met — giving up", "success" if passed else "error")
        done_patch = {"wrapperPassed": passed, "wrapperAttempt": attempt, **({"wrapperTotals": totals} if totals else {})}
        host.update_data(wrapper["id"], done_patch)
        return {"result": result, "wrapperPatch": {"nodeId": wrapper["id"], "patch": done_patch}}

    # Serialized through one lock per run, each call building on the previous
    # call's result (cascade_state). Returns a task; awaiting it is optional.
    def run_action_cascade(self, self_patch, edges_snapshot):
        lock = self._cascade_lock

        async def run():
            async with lock:
                base = self.cascade_state
                patches = self_patch if isinstance(self_patch, list) else ([self_patch] if self_patch else [])
                for p in patches:
                    if p["nodeId"] in base:
                        base = with_data(base, p["nodeId"], p["patch"])
                result = await self._run_action_cascade_impl(base, edges_snapshot)
                self.cascade_state = result
                return result

        return self.spawn(run())

    async def _run_action_cascade_impl(self, nodes_snapshot, edges_snapshot):
        ctx = _CascadeContext(self, nodes_snapshot, expand_edges(nodes_snapshot, edges_snapshot))
        for _ in range(10):
            if self.run_stopped():
                break
            ctx.changed = False
            ctx.ev = evaluate_all(ctx.nodes, edges_snapshot)
            await self._apply_handlers("settle", ctx)
            ctx.ev2 = evaluate_all(ctx.nodes, edges_snapshot)
            if await self._apply_handlers("fire", ctx):
                break
            if not ctx.changed:
                break
        return ctx.nodes

    # Returns True when a stop cut the fire phase short.
    async def _apply_handlers(self, phase, ctx):
        for t, spec in node_types().items():
            handlers = [getattr(spec, phase, None)]
            if phase == "settle" and getattr(spec, "RAN_PASSED", False):
                handlers.insert(0, settle_ran_passed)
            for run in filter(None, handlers):
                for node in [ctx.nodes[k] for k in js_keys(ctx.nodes)]:
                    if node["type"] != t:
                        continue
                    if phase == "fire" and self.run_stopped():
                        return True
                    signal_port = getattr(spec, "SIGNAL_PORT", None) if phase == "fire" else None
                    if signal_port:
                        if not self._fresh_signal(node, signal_port, ctx):
                            continue
                        ctx.changed = True
                    pending = run(node, ctx)
                    if inspect.isawaitable(pending):
                        await pending
        return False

    def _fresh_signal(self, node, port_id, ctx):
        sig = resolve_wired_input(ctx.eff_edges, ctx.ev2, node["id"], port_id)
        if not is_present(sig):
            return False
        key = js_json_stringify(sig)
        state = self.state(node["id"])
        if state.get("lastSignal") == key:
            return False
        state["lastSignal"] = key
        return True


# At most `limit` workers, each pulling the next item as soon as it's free.
async def _run_with_concurrency_limit(items, limit, worker):
    queue = list(items)

    async def drain():
        while queue:
            await worker(queue.pop(0))

    await asyncio.gather(*(drain() for _ in range(min(limit, len(items)))))


# --- Server-side runs ---------------------------------------------------------------
# One WorkflowRunner per run on the event loop, its node state and log served to
# GET /runs/{id}. In memory only: a server restart drops every run.

RUN_POLL_INTERVAL_MS = POLL_INTERVAL_MS

# Every Move node across all runs goes through this — two runs moving the
# same folders at once would otherwise race on the filesystem.
_move_lock = threading.Lock()

# run id -> Run, oldest first; finished runs past RUNS_KEPT_MAX are dropped.
runs_by_id: dict[str, "Run"] = {}


# JSON-safe copy: UNDEFINED keys dropped (list slots -> null, like
# JSON.stringify), non-finite numbers -> null.
def to_jsonable(v):
    if isinstance(v, dict):
        return {k: to_jsonable(x) for k, x in v.items() if x is not UNDEFINED}
    if isinstance(v, list):
        return [None if x is UNDEFINED else to_jsonable(x) for x in v]
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return None if v is UNDEFINED else v


# WorkflowRunner's backend: Codex jobs and folder moves, in this process.
class InProcessBackend:
    async def create_job(self, body):
        return start_codex_job(body["prompt"], body["output_schema"], body["node_id"], body["operation_id"])

    async def get_job(self, job_id):
        job = public_job(job_id)
        if job is None:
            raise RuntimeError("Failed to poll job (404)")
        return job

    async def stop_job(self, job_id):
        request_stop(job_id)

    async def move_folder(self, src, dst, operation_id):
        if not isinstance(src, str) or not isinstance(dst, str):
            raise RuntimeError("Source and destination must be text.")

        def work():
            with _move_lock:
                return run_once(operation_id, lambda: move_folder_checked(src, dst))

        try:
            return await asyncio.to_thread(work)
        except MoveError as e:
            raise RuntimeError(e.detail) from None


# WorkflowRunner's host: the run's own node state (no UI) plus its log.
class RunHost:
    def __init__(self, nodes, edges):
        self.nodes = nodes
        self.edges = edges
        self.logs = []
        self.log_seq = 0
        self.blocked_count = 0

    def get_nodes(self):
        return self.nodes

    def get_edges(self):
        return self.edges

    def update_data(self, node_id, patch):
        if node_id in self.nodes:
            self.nodes = with_data(self.nodes, node_id, patch)

    def apply_to_nodes(self, fn):
        self.nodes = fn(self.nodes)

    def log(self, node_id, message, level="info", notify=False):
        self.log_seq += 1
        entry = {"seq": self.log_seq, "at": time.time(), "nodeId": node_id, "message": message, "level": level}
        if notify:
            entry["notify"] = True
        self.logs.append(entry)
        if len(self.logs) > RUN_LOG_MAX:
            del self.logs[: len(self.logs) - RUN_LOG_MAX]

    # The editor shows these as a toast.
    def notify(self, message):
        self.log(None, message, "error", notify=True)

    def on_running_change(self, running):
        pass

    def on_run_blocked(self, count):
        self.blocked_count = count


class Run:
    def __init__(self, nodes, edges, workflow_id, name, retry_node_id=None):
        self.id = f"{time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        self.workflow_id = workflow_id
        self.name = name
        # running -> finished | stopped | blocked (pre-run errors) | error
        self.status = "running"
        self.error = None
        self.created_at = time.time()
        self.finished_at = None
        self.stop_requested = False
        # Set: this run is one AI Node's manual retry, not a whole workflow run.
        self.retry_node_id = retry_node_id
        self.host = RunHost(nodes, edges)
        self.runner = WorkflowRunner(self.host, InProcessBackend(), poll_interval_ms=RUN_POLL_INTERVAL_MS,
                                     max_concurrent_runs=MAX_CONCURRENT_RUNS)
        self.task: asyncio.Task | None = None

    def summary(self):
        return {"id": self.id, "workflow_id": self.workflow_id, "name": self.name, "status": self.status,
                "error": self.error, "created_at": self.created_at, "finished_at": self.finished_at}

    # The API Response node's {field: value} (its "out") as of now (no value -> null); None without one.
    def response(self):
        nodes, edges = self.host.nodes, self.host.edges
        node_id = _api_node(nodes, "apiResponse")
        if node_id is None:
            return None
        try:
            body = jget(evaluate_all(nodes, edges)["values"].get(node_id) or {}, "out")
        except Exception:
            body = {}
        return {f: (None if v is UNDEFINED else to_jsonable(v)) for f, v in (body or {}).items()}

    # Values of the RUN_OUTPUT types' nodes (Output) as of now: {node_id: {"title", "value"}}.
    def outputs(self):
        nodes, edges = self.host.nodes, self.host.edges
        try:
            values = evaluate_all(nodes, edges)["values"]
        except Exception:
            return {}
        return {nid: {"title": get_node_def(n, nodes, edges)["title"], "value": to_jsonable(jget(values.get(nid) or {}, "out"))}
                for nid, n in nodes.items() if getattr(node_type(n.get("type")), "RUN_OUTPUT", False)}

    # workflow_running: run_workflow() is in progress or about to start (False
    # while only Delays are pending, and for a retry run).
    def snapshot(self, since=0):
        workflow_running = self.runner.is_running or (self.status == "running" and not self.retry_node_id and self.runner.run_no == 0
                                                      and not self.host.blocked_count)
        return {**self.summary(), "workflow_running": workflow_running, "run_state": to_jsonable(self.runner.run_state),
                "nodes": to_jsonable(self.host.nodes), "outputs": self.outputs(), "response": self.response(),
                "logs": [l for l in self.host.logs if l["seq"] > since]}


def _drop_old_runs():
    finished = [rid for rid, r in runs_by_id.items() if r.status != "running"]
    for rid in finished[: max(0, len(finished) - RUNS_KEPT_MAX)]:
        del runs_by_id[rid]


async def _supervise(run):
    try:
        if run.retry_node_id:
            run.runner.retry_node(run.retry_node_id)
        else:
            await run.runner.run_workflow()
        # Delay timers / Run Trigger re-runs can outlive the first run_workflow().
        while not run.runner.is_idle():
            await asyncio.sleep(IDLE_CHECK_SEC)
        if run.runner.run_no == 0 and run.host.blocked_count:
            run.status = "blocked"
        else:
            run.status = "stopped" if run.stop_requested else "finished"
    except Exception as e:
        run.status = "error"
        run.error = str(e)
        run.host.log(None, f"run failed: {e}", "error")
    finally:
        run.finished_at = time.time()
        _drop_old_runs()


# Must be called on the event loop (an async route).
def start_run(nodes, edges, workflow_id=None, name=None, retry_node_id=None):
    run = Run(nodes, edges, workflow_id, name, retry_node_id)
    runs_by_id[run.id] = run
    run.task = asyncio.get_running_loop().create_task(_supervise(run))
    return run


# Waits up to `timeout` seconds for the run to end (it keeps going if not).
async def wait_for_run(run, timeout):
    if timeout > 0 and run.task is not None:
        await asyncio.wait({run.task}, timeout=timeout)


def get_run_snapshot(run_id, since=0):
    run = runs_by_id.get(run_id)
    return run.snapshot(since) if run else None


# Newest first (runs_by_id is in creation order).
def list_runs():
    return [r.summary() for r in reversed(runs_by_id.values())]


# False for an unknown run; a no-op for one that already ended.
def stop_run(run_id):
    run = runs_by_id.get(run_id)
    if run is None:
        return False
    if run.status == "running":
        run.stop_requested = True
        run.runner.stop_workflow()
    return True


def stop_run_node(run_id, node_id):
    run = runs_by_id.get(run_id)
    if run is None:
        return False
    run.runner.stop_node(node_id)
    return True
