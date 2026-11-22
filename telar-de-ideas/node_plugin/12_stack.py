# Stack: outputs the front of data.values; each pop signal drops that front element
# (into data.__stack, the popped copy). __stack is deliberately not cleared by Reset:
# a Stack/Reset/Delay/Run Trigger loop fires Reset from the same pulse that pops the
# Stack, so a rewind there would re-derive every pop from the original list and the
# loop could never get past its second item. Editing the list (or Start Over) refills it.
from common import UNDEFINED, jget, jidx, js_truthy, make_port, short_value
from data import BODY_H_M

TYPE = "stack"
TITLE = "Stack"
INPUTS = [make_port("pop", "signal", "trigger")]
OUTPUTS = [make_port("out", "value", "string")]
DEFAULT_DATA = {"values": [""]}
BODY_HEIGHT = BODY_H_M
RAN_PASSED = True
SIGNAL_PORT = "pop"


def _configured(data):
    values = jget(data, "values")
    return values if js_truthy(values) and len(values) else [""]


# __stack once popped, else the configured list; the top is index 0.
def _current(data):
    stack = jget(data, "__stack")
    return stack if stack is not UNDEFINED else _configured(data)


def evaluate(node, io):
    return {"out": jidx(_current(node["data"]), 0)}


def check_data(data, nerr):
    if "values" in data and not (isinstance(data["values"], list) and all(isinstance(v, str) for v in data["values"])):
        nerr("/data/values", "must be an array of strings")


def fire(node, ctx):
    nxt = _current(node["data"])[1:]
    ctx.runner.host.log(node["id"], f'popped — top is now "{short_value(nxt[0], 40)}"' if nxt else "popped — now empty")
    ctx.patch(node["id"], {"__stack": nxt})


def fields(node):
    data = node["data"]
    out = []
    if jget(data, "__stack") is not UNDEFINED:
        out.append({"kind": "button", "label": f"Start Over ({len(data['__stack'])}/{len(_configured(data))} left)",
                    "color": "warning", "unset": ["__stack"]})
    out.append({"kind": "list", "key": "values", "addLabel": "+ Add String", "keepOne": True, "alsoUnset": ["__stack"]})
    return out


# Counts only (values stay private, like Text).
def body(node, view):
    configured = len(_configured(node["data"]))
    stack = jget(node["data"], "__stack")
    remaining = len(stack) if stack is not UNDEFINED else configured
    return [{"kind": "caption", "text": "Strings (click to edit)"},
            {"kind": "chip", "label": f"Remaining: {remaining}/{configured}", "color": "default" if remaining > 0 else "error"}]
