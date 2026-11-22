# Run Trigger: starts a new run on a signal. Titled "Run Trigger" so it isn't
# mistaken for the toolbar's Run button.
from common import UNDEFINED, jget, make_port, waiting_on_signal
from data import BODY_H_M

TYPE = "runtrigger"
TITLE = "Run Trigger"
INPUTS = [make_port("signal", "signal", "trigger")]
BODY_HEIGHT = BODY_H_M
SIGNAL_PORT = "signal"
RESET = {"runTriggerStatus": UNDEFINED}
waiting = waiting_on_signal


def check(node, chk):
    if not chk.wired(SIGNAL_PORT):
        chk.add("warning", f'"{chk.title()}" has no signal wired in — it never fires.')


def run_state(node, outs, running):
    return {"running": False, "passed": jget(node["data"], "runTriggerStatus") == "done"}


def fire(node, ctx):
    ctx.runner.host.log(node["id"], "requested a new run")
    ctx.patch(node["id"], {"runTriggerStatus": "done"})
    # Not awaited: run_workflow's own cascade would wait on this one's lock.
    ctx.runner.spawn(ctx.runner.run_workflow())


def body(node, view):
    out = [{"kind": "caption", "text": "Runs the whole workflow on signal"}]
    if jget(node["data"], "runTriggerStatus") == "done":
        out.append({"kind": "caption", "color": "success", "text": "Run started."})
    return out
