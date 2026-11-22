# Starting point for a new node type: copy to "NN_name.py" (NN = menu position,
# files load in name order; "_"-prefixed files are skipped) and restart
# api_server.py (--reload restarts it by itself). Everything but TYPE is optional —
# delete what the type doesn't need. Full contract: common.py "Node types".
#
# This example: Upper — the wired text in upper (or lower) case.
from common import UNDEFINED, fmt_value, is_present, jget, make_port, to_str, waiting_on_inputs
from data import BODY_H_S

# Saved in workflows — never rename it once used.
TYPE = "upper"
TITLE = "Upper"
# make_port(id, label, type): type is "string" | "number" | "any" | "trigger".
INPUTS = [make_port("in", "text", "string")]
OUTPUTS = [make_port("out", "result", "string")]
# A new node's data, and its starting body height (BODY_H_S/M/L).
DEFAULT_DATA = {"mode": "upper"}
BODY_HEIGHT = BODY_H_S
# COLOR = "#7986cb"            header color (default: the Plugin Node indigo)
# MULTI_INPUTS = ("in",)       inputs that take several wires (io.inputs reads them)
# RUNNABLE = True              Run is enabled by a node of this type alone
# RESET = {"myStatus": UNDEFINED}   data the Reset button / Reset node clears

# "Produced a value" is its run outcome: green border once out is present
# (override with ran_passed(node, outs) -> bool). Reset clears it.
RAN_PASSED = True

# Edit panel (shown when the node is selected). Widgets:
#   {"kind": "text", "key", "label"?, "placeholder"?, "multiline"?, "rows"?, "helper"?}
#   {"kind": "number", "key", "label"?, "min"?, "integer"?, "default"?, "store": "number" | "string"}
#   {"kind": "select" | "toggle", "key", "options": [{"value", "label"}], "default"?}
#   {"kind": "list", "key", "placeholder"?, "addLabel"?, "keepOne"?}        list of strings
#   {"kind": "records", "key", "fields": [text/number/select/toggle], "newItem", "addLabel"?}
#   {"kind": "button", "label", "set"?: {...}, "unset"?: [...], "color"?}
#   {"kind": "caption", "text"}
# Any value field may add "alsoSet": {...} / "alsoUnset": [...] (other data it resets).
# Or define fields(node) -> [widget] when the form depends on the node's data.
FIELDS = [
    {"kind": "toggle", "key": "mode", "default": "upper",
     "options": [{"value": "upper", "label": "UPPER"}, {"value": "lower", "label": "lower"}]},
]


# Its ports from data, when they aren't fixed (Format: one input per placeholder):
# def ports(node, nodes, edges):
#     return {"inputs": [...], "outputs": [...]}


# The live value of each output port — must be side-effect-free (it runs on every
# edit). io.input(port) is the wired value (UNDEFINED if unwired); also io.inputs,
# io.inputs_by_source, io.wired. Extra "_keys" are fine (body/waiting can read them).
def evaluate(node, io):
    value = io.input("in")
    if not is_present(value):
        return {"out": UNDEFINED}
    text = to_str(value)
    return {"out": text.upper() if jget(node["data"], "mode") != "lower" else text.lower()}


# Pre-run checks: check_data(data, nerr) for the data's shape (nerr(path, message)
# is an error), check(node, chk) for wiring (chk.add("warning" | "error", message)).
def check(node, chk):
    if not chk.wired("in"):
        chk.add("warning", f'"{chk.title()}" has nothing wired into "text".')


# Hourglass tooltip during a run: why it hasn't produced anything yet.
waiting = waiting_on_inputs


# Card body. Widgets:
#   {"kind": "caption", "text", "color"?: "error" | "success"}
#   {"kind": "chip", "label", "color"?, "variant"?: "outlined", "icon"?}   (MUI Chip)
#   {"kind": "chips", "items": [chip...], "empty"?}
#   {"kind": "value", "text"}          dark value box (like Output)
#   {"kind": "pairs", "rows": [{"name", "value"}]}
#   {"kind": "path", "text"?, "empty"?}, {"kind": "open", "label", "path"}   (like Link)
#   {"kind": "error", "text"}, {"kind": "alert", "severity", "text"}
# view.outs = this node's evaluate() result.
def body(node, view):
    return [{"kind": "caption", "text": "Changes the text's case (click to edit)"},
            {"kind": "value", "text": fmt_value(jget(view.outs, "out"))}]


# Run-time behavior (side effects belong here, not in evaluate):
#   SIGNAL_PORT = "signal"; def fire(node, ctx): ...   runs on each new signal there
#   def settle(node, ctx): ...                          runs on every cascade pass
#   ctx.patch(node["id"], {...}) updates its data; ctx.runner.host.log(node["id"], "msg");
#   ctx.runner.state(node["id"]) is a per-run dict (shown to waiting() as w.state).
#   def run_state(node, outs, running): return {"running": ..., "passed": ...}
#   def on_stop(node): return {...} or None             data patch when Stop is pressed
