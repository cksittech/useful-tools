# Reset: on a new signal, clears every node's run results (the Reset Results button's
# effect, common.apply_reset_to_nodes).
from common import UNDEFINED, apply_reset_to_nodes, jget, make_port, waiting_on_signal, with_data
from data import BODY_H_M

TYPE = "reset"
TITLE = "Reset"
INPUTS = [make_port("signal", "signal", "trigger")]
BODY_HEIGHT = BODY_H_M
SIGNAL_PORT = "signal"
RESET = {"resetStatus": UNDEFINED}
waiting = waiting_on_signal


def check(node, chk):
    if not chk.wired(SIGNAL_PORT):
        chk.add("warning", f'"{chk.title()}" has no signal wired in — it never fires.')


def run_state(node, outs, running):
    return {"running": False, "passed": jget(node["data"], "resetStatus") == "done"}


def fire(node, ctx):
    ctx.runner.host.log(node["id"], "cleared every node’s run results")
    ctx.nodes = apply_reset_to_nodes(ctx.nodes)
    ctx.patch_working(node["id"], {"resetStatus": "done"})
    ctx.runner.host.apply_to_nodes(lambda prev: with_data(apply_reset_to_nodes(prev), node["id"], {"resetStatus": "done"}))


def body(node, view):
    out = [{"kind": "caption", "text": "Clears every node’s run results on signal"}]
    if jget(node["data"], "resetStatus") == "done":
        out.append({"kind": "caption", "color": "success", "text": "Results reset."})
    return out
