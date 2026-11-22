# Delay: re-fires its signal data.seconds after its input fires. Timed by the run
# only, so mere wiring never starts a countdown; a newer signal replaces a wait still
# in progress (run state "token"), and a wait can outlive the workflow loop.
from common import UNDEFINED, is_number, jget, js_number_str, js_or, js_string, js_to_number, make_port, waiting_on_signal
from data import BODY_H_M

TYPE = "delay"
TITLE = "Delay"
INPUTS = [make_port("in", "signal", "trigger")]
OUTPUTS = [make_port("out", "signal", "trigger")]
DEFAULT_DATA = {"seconds": 3}
BODY_HEIGHT = BODY_H_M
SIGNAL_PORT = "in"
RESET = {"delayStatus": UNDEFINED, "__seq": 0}
FIELDS = [{"kind": "number", "key": "seconds", "label": "Wait (seconds)", "min": 0, "default": 3, "store": "number"}]


# out is a pulse counter (data.__seq) bumped when the wait ends — never the incoming
# signal itself. UNDEFINED (not 0) before the first: 0 is present, so anything wired
# here (Reset/Run Trigger/Stack) would see it as already signaled on every Run.
def evaluate(node, io):
    return {"out": js_or(jget(node["data"], "__seq"), UNDEFINED)}


def check_data(data, nerr):
    if "seconds" in data and not (is_number(data["seconds"]) and data["seconds"] >= 0):
        nerr("/data/seconds", "must be a number >= 0")


def check(node, chk):
    if not chk.wired(SIGNAL_PORT):
        chk.add("warning", f'"{chk.title()}" has no signal wired in — it never fires.')


def waiting(node, w):
    if jget(node["data"], "delayStatus") == "waiting":
        return [f"counting down {js_string(js_or(jget(node['data'], 'seconds'), 0))}s"]
    return waiting_on_signal(node, w)


# Not gated on the workflow running: a wait can still count down after the run ends.
def run_state(node, outs, running):
    status = jget(node["data"], "delayStatus")
    return {"running": status == "waiting", "passed": status == "done"}


def fire(node, ctx):
    r = ctx.runner
    seconds = js_to_number(jget(node["data"], "seconds"))
    seconds = max(0.0, 0.0 if seconds != seconds else seconds)
    run_id = r.active_run["id"]
    state = r.state(node["id"])
    token = state.get("token", 0) + 1
    state["token"] = token
    r.host.log(node["id"], f"waiting {js_number_str(seconds)}s")
    ctx.patch(node["id"], {"delayStatus": "waiting"})
    r.schedule(seconds, lambda: _relay(r, node["id"], run_id, token))


def _relay(r, node_id, run_id, token):
    if r.active_run["id"] != run_id or r.run_stopped():
        return
    if r.state(node_id).get("token") != token:
        return
    base = r.cascade_state or {}
    prev_seq = js_or(jget(base[node_id]["data"], "__seq"), 0) if node_id in base else 0
    patch = {"delayStatus": "done", "__seq": prev_seq + 1}
    r.host.log(node_id, "relayed signal", "success")
    r.host.update_data(node_id, patch)
    r.run_action_cascade({"nodeId": node_id, "patch": patch}, r.host.get_edges())


# A stopped run's wait never relays, so it no longer shows as waiting.
def on_stop(node):
    return {"delayStatus": UNDEFINED} if jget(node["data"], "delayStatus") == "waiting" else None


def body(node, view):
    data = node["data"]
    seconds = jget(data, "seconds")
    seconds = js_string(3 if seconds is UNDEFINED or seconds is None else seconds)
    out = [{"kind": "caption", "text": f"Relays the signal after {seconds}s (click to edit)"}]
    status = jget(data, "delayStatus")
    if status == "waiting":
        out.append({"kind": "chip", "label": f"Waiting {seconds}s…"})
    if status == "done":
        out.append({"kind": "caption", "color": "success", "text": "Signal relayed."})
    return out
