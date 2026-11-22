# Queue: a FIFO of input sets with data.inputCount slots. During a run each input
# latches; once every slot holds a value the set is queued, and the front set is
# delivered on out0..outN with a signal pulse (data.__seq).
import re

from common import UNDEFINED, is_int, is_present, jget, jidx, js_or, make_port, same_value, short_value
from data import BODY_H_L

TYPE = "que"
TITLE = "Queue"
# Slot count range — tied to the fixed in0..in4/out0..out4 ports.
MIN_INPUTS = 1
MAX_INPUTS = 5
INPUTS = [make_port(f"in{i}", f"value {i + 1}", "any") for i in range(MAX_INPUTS)]
OUTPUTS = [make_port(f"out{i}", f"value {i + 1}", "any") for i in range(MAX_INPUTS)] + [make_port("signal", "trigger", "trigger")]
DEFAULT_DATA = {"queue": [], "inputCount": MAX_INPUTS}
BODY_HEIGHT = BODY_H_L
MULTI_INPUTS = tuple(f"in{i}" for i in range(MAX_INPUTS))
RUNNABLE = True
RESET = {"queue": [], "__dequeuedValues": UNDEFINED, "__seq": 0}
# Changing the slot count starts the buffer over (old sets no longer match).
FIELDS = [{"kind": "select", "key": "inputCount", "default": MAX_INPUTS,
           "options": [{"value": n, "label": f"{n} inputs"} for n in range(MIN_INPUTS, MAX_INPUTS + 1)],
           "alsoSet": {"queue": [], "__seq": 0}, "alsoUnset": ["__dequeuedValues"]}]


def queue_input_count(data):
    return min(MAX_INPUTS, max(MIN_INPUTS, js_or(jget(data, "inputCount"), MAX_INPUTS)))


# Inputs/value outputs sliced to the slot count, plus the trigger output.
def ports(node, nodes, edges):
    n = int(queue_input_count(node["data"]))
    return {"inputs": INPUTS[:n], "outputs": OUTPUTS[:n] + [OUTPUTS[MAX_INPUTS]]}


# out0..out4/signal are run state (last delivered set + pulse counter, UNDEFINED —
# not 0 — before the first, or it would look already signaled); _liveInputs only
# previews each slot's latest wired value.
def evaluate(node, io):
    data = node["data"]
    dq = js_or(jget(data, "__dequeuedValues"), [])
    live_inputs = []
    for i in range(MAX_INPUTS):
        vals = [v for v in io.inputs(f"in{i}") if is_present(v)]
        live_inputs.append(vals[-1] if vals else UNDEFINED)
    outs = {f"out{i}": jidx(dq, i) for i in range(MAX_INPUTS)}
    outs["signal"] = js_or(jget(data, "__seq"), UNDEFINED)
    outs["_liveInputs"] = live_inputs
    return outs


def check_data(data, nerr):
    if "inputCount" in data and not (is_int(data["inputCount"]) and MIN_INPUTS <= data["inputCount"] <= MAX_INPUTS):
        nerr("/data/inputCount", f"must be an integer in [{MIN_INPUTS}, {MAX_INPUTS}]")
    if "queue" in data and not isinstance(data["queue"], list):
        nerr("/data/queue", "must be array")


def check(node, chk):
    for i in range(int(queue_input_count(node["data"]))):
        p = f"in{i}"
        if not chk.wired(p):
            chk.add("warning", f'"{chk.title()}" input "{chk.port_label(p)}" is not wired — it will never enqueue.')


def waiting(node, w):
    latch = (w.state.get("latch") or {}).get("portLatch") or {}
    missing = [f"in{i}" for i in range(int(queue_input_count(node["data"]))) if not is_present(latch.get(f"in{i}", UNDEFINED))]
    return [f"not yet received: {', '.join(w.input_label(p) for p in missing)}"] if missing else []


# A fanned-in wire's source: the Per-wire Gate source for 'value_out@<id>', else the node.
def fan_in_source_key(e):
    m = re.fullmatch(r"value_out@(.+)", e["from"]["port"], re.S)
    return m.group(1) if m else e["from"]["node"]


# One cascade pass of the input latch. A single-wire port latches a new value when
# it changes; fanned-in ports latch one complete row per source. inputSet: the set
# to enqueue when the latch changed and every port holds a value, else None.
def step_queue_latch(node, edges, ev, state):
    prev = state or {}
    ports_ = [f"in{i}" for i in range(int(queue_input_count(node["data"])))]
    latch = dict(prev.get("portLatch") or {})
    source_latch = dict(prev.get("sourceLatch") or {})
    edge_prev = dict(prev.get("edgePrev") or {})

    def value_of(e):
        return jget(ev["values"].get(e["from"]["node"]) or {}, e["from"]["port"])

    latch_changed = False
    edges_by_port = {p: [e for e in edges if e["to"]["node"] == node["id"] and e["to"]["port"] == p] for p in ports_}
    fixed_ports = [p for p in ports_ if len(edges_by_port[p]) <= 1]
    fanned_ports = [p for p in ports_ if len(edges_by_port[p]) > 1]

    for port_id in fixed_ports:
        for e in edges_by_port[port_id]:
            val = value_of(e)
            if not is_present(val):
                continue
            edge_is_new = e["id"] not in edge_prev
            edge_prev_val = edge_prev.get(e["id"], UNDEFINED)
            edge_prev[e["id"]] = val
            if (edge_is_new or not same_value(val, edge_prev_val)) and not same_value(val, latch.get(port_id, UNDEFINED)):
                latch[port_id] = val
                latch_changed = True

    if fanned_ports:
        sources = []
        for p in fanned_ports:
            for e in edges_by_port[p]:
                src = fan_in_source_key(e)
                if src not in sources:
                    sources.append(src)
        for src in sources:
            row_vals = {}
            complete = True
            for p in fanned_ports:
                e = next((fe for fe in edges_by_port[p] if fan_in_source_key(fe) == src), None)
                val = value_of(e) if e else UNDEFINED
                if not is_present(val):
                    complete = False
                row_vals[p] = val
            if not complete:
                continue
            prev_row = source_latch.get(src)
            if prev_row and not any(not same_value(row_vals[p], prev_row.get(p, UNDEFINED)) for p in fanned_ports):
                continue
            source_latch[src] = row_vals
            for p in fanned_ports:
                latch[p] = row_vals[p]
            latch_changed = True
            break

    should_enqueue = latch_changed and all(is_present(latch.get(p, UNDEFINED)) for p in ports_)
    return {"portLatch": latch, "sourceLatch": source_latch, "edgePrev": edge_prev,
            "inputSet": [latch.get(p, UNDEFINED) for p in ports_] if should_enqueue else None}


# Latches inputs, queues a complete set, and delivers the front one (Move reads
# the delivered set from run state "delivered").
def settle(node, ctx):
    r = ctx.runner
    state = r.state(node["id"])
    step = step_queue_latch(node, ctx.eff_edges, ctx.ev, state.get("latch"))
    input_set = step.pop("inputSet")
    state["latch"] = step

    current_queue = js_or(jget(node["data"], "queue"), [])
    queue_after = [*current_queue, input_set] if input_set else current_queue
    if input_set:
        r.host.log(node["id"], f"enqueued [{', '.join(short_value(v, 40) for v in input_set)}]")
    if len(queue_after) == 0:
        return
    front, rest = queue_after[0], queue_after[1:]
    r.host.log(node["id"], f"delivered [{', '.join(short_value(v, 40) for v in front)}] — {len(rest)} left", "success")
    ctx.changed = True
    ctx.patch(node["id"], {"queue": rest, "__dequeuedValues": front, "__seq": js_or(jget(node["data"], "__seq"), 0) + 1})
    state["delivered"] = front


# Queued count, plus which slots still lack a value (so a forgotten slot doesn't look like a hang).
def body(node, view):
    queue_len = len(js_or(jget(node["data"], "queue"), []))
    live = js_or(jget(view.outs, "_liveInputs"), [])
    missing = [f"value {i + 1}" for i in range(int(queue_input_count(node["data"]))) if not is_present(jidx(live, i))]
    chips = [{"label": f"Queued: {queue_len}", "color": "warning" if queue_len > 0 else "default"}]
    if missing:
        chips.append({"label": f"Waiting: {', '.join(missing)}", "color": "error", "variant": "outlined"})
    return [{"kind": "caption", "text": "Slot count (click to edit)"}, {"kind": "chips", "items": chips}]
