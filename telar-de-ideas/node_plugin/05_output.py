# Output: shows the value wired in; a run's snapshot lists these as its "outputs".
# Type key is "sink" (renamed from "output" once; migrate_loaded_nodes maps old saves).
from common import fmt_value, jget, make_port, waiting_on_inputs
from data import BODY_H_L

TYPE = "sink"
TITLE = "Output"
INPUTS = [make_port("in", "value", "any")]
BODY_HEIGHT = BODY_H_L
RAN_PASSED = True
RUN_OUTPUT = True
waiting = waiting_on_inputs


def evaluate(node, io):
    return {"out": io.input("in")}


def body(node, view):
    return [{"kind": "value", "text": fmt_value(jget(view.outs, "out"))}]
