# Gate: compare (several wires) is matched against data.matchValue (comma-separated
# candidates). AND/OR decide once every compare wire has arrived; EACH (Per-Wire)
# judges each wire on its own. signal fires while passing; value_out forwards value
# only then (EACH: split per compare source as 'value_out@<id>', see expand_edges).
from common import UNDEFINED, fmt_value, is_present, jget, js_or, js_string, js_strict_eq, js_trim, make_port, to_str
from data import BODY_H_L

TYPE = "gate"
TITLE = "Gate"
INPUTS = [make_port("compare", "compare", "any"), make_port("value", "value", "any")]
OUTPUTS = [make_port("out", "signal", "trigger"), make_port("value_out", "value (on pass)", "any")]
DEFAULT_DATA = {"matchValue": "", "matchMode": "AND"}
BODY_HEIGHT = BODY_H_L
MULTI_INPUTS = ("compare", "value")
READS_UNGATED = ("compare", "value")
# The last run's verdict (data.lastPass), not the live one, so Reset clears it.
RESET = {"lastPass": UNDEFINED}
MATCH_MODES = ("AND", "OR", "EACH")
FIELDS = [
    {"kind": "text", "key": "matchValue", "label": "Match value"},
    {"kind": "toggle", "key": "matchMode", "default": "AND",
     "options": [{"value": "AND", "label": "AND"}, {"value": "OR", "label": "OR"}, {"value": "EACH", "label": "Per-Wire"}]},
]


# Per-wire (EACH): each value_out edge becomes one edge per compare source, so a
# multi-wire port downstream (Queue's inN) gets one delivery per passing source.
def expand_edges(nodes, edges):
    out = []
    for e in edges:
        from_node = jget(nodes, e["from"]["node"])
        if (isinstance(from_node, dict) and from_node["type"] == TYPE
                and jget(from_node["data"], "matchMode") == "EACH" and e["from"]["port"] == "value_out"):
            seen = set()
            for ce in edges:
                if ce["to"]["node"] != e["from"]["node"] or ce["to"]["port"] != "compare":
                    continue
                if ce["from"]["node"] in seen:
                    continue
                seen.add(ce["from"]["node"])
                out.append({**e, "from": {"node": e["from"]["node"], "port": "value_out@" + ce["from"]["node"]},
                            "id": f"{js_string(jget(e, 'id'))}~{ce['from']['node']}"})
            continue
        out.append(e)
    return out


def _per_wire(io, pairs, candidates):
    return [{
        "from": p["from"],
        "fromTitle": js_or(io.title_of(p["from"]), p["from"]),
        "value": p["value"],
        "passed": is_present(p["value"]) and to_str(p["value"]) in candidates,
    } for p in pairs]


# out is UNDEFINED (not False) unless passing: signal inputs fire on is_present,
# and False is present. _pending = some compare wire hasn't arrived (waiting border).
def evaluate(node, io):
    data = node["data"]
    candidates = [js_trim(v) for v in to_str(jget(data, "matchValue")).split(",")]
    compare_pairs = io.inputs_by_source("compare")
    all_arrived = len(compare_pairs) > 0 and all(is_present(p["value"]) for p in compare_pairs)
    pending = len(compare_pairs) > 0 and not all_arrived
    if jget(data, "matchMode") == "EACH":
        value_by_source = {}
        for p in io.inputs_by_source("value"):
            value_by_source[p["from"]] = p["value"]
        wires = _per_wire(io, compare_pairs, candidates)
        passed = any(w["passed"] for w in wires)
        outs = {"out": True if passed else UNDEFINED, "_pass": passed, "_allArrived": all_arrived, "_pending": pending, "_perWire": wires}
        for w in wires:
            outs["value_out@" + w["from"]] = value_by_source.get(w["from"], UNDEFINED) if w["passed"] else UNDEFINED
        return outs
    wires = _per_wire(io, compare_pairs, candidates)
    if not all_arrived:
        passed = False
    elif jget(data, "matchMode") == "OR":
        passed = any(w["passed"] for w in wires)
    else:
        passed = all(w["passed"] for w in wires)
    # value takes several wires; the first present one wins.
    resolved_value = next((v for v in io.inputs("value") if is_present(v)), UNDEFINED)
    return {"out": True if passed else UNDEFINED, "_pass": passed, "_allArrived": all_arrived, "_pending": pending,
            "value_out": resolved_value if passed else UNDEFINED, "_perWire": wires}


def check_data(data, nerr):
    if "matchMode" in data and data["matchMode"] not in MATCH_MODES:
        nerr("/data/matchMode", "must be equal to one of the allowed values")


def check(node, chk):
    if not chk.wired("compare"):
        chk.add("warning", f'"{chk.title()}" has nothing wired into "compare" — it never passes.')


def waiting(node, w):
    if not jget(w.outs, "_pending"):
        return []
    missing = [js_string(p["fromTitle"]) for p in js_or(jget(w.outs, "_perWire"), []) if not is_present(p["value"])]
    return [f"compare: waiting on {', '.join(missing)}"]


def run_state(node, outs, running):
    return {"running": running and bool(jget(outs, "_pending")), "passed": jget(node["data"], "lastPass") is True}


# Records the verdict once every compare wire has arrived.
def settle(node, ctx):
    val = ctx.ev["values"].get(node["id"]) or {}
    if jget(val, "_pending"):
        return
    passed = jget(val, "_pass")
    if js_strict_eq(jget(node["data"], "lastPass"), passed):
        return
    ctx.runner.host.log(node["id"], "passed" if passed else "did not pass", "success" if passed else "warning")
    ctx.patch(node["id"], {"lastPass": passed})


def body(node, view):
    last_pass = jget(node["data"], "lastPass")
    out = [{"kind": "caption", "text": "Match settings (click to edit)"}]
    if last_pass is not UNDEFINED:
        out.append({"kind": "chip", "color": "success" if last_pass else "error", "icon": "CheckCircle" if last_pass else "Cancel",
                    "label": "Pass — signals true" if last_pass else "Blocked — signals false"})
    # Each compare wire's source, value and verdict (the chip above is only the combined one).
    out.append({"kind": "chips", "empty": "(no compare wires)", "items": [
        {"label": f"{js_string(w['fromTitle'])} ({w['from']}): {fmt_value(w['value'])}",
         "variant": "filled" if w["passed"] else "outlined", "color": "success" if w["passed"] else "default"}
        for w in js_or(jget(view.outs, "_perWire"), [])]})
    return out
