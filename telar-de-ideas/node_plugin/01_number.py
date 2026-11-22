# Number: a constant. data.value is kept as typed (a string) and parsed on read.
from common import jget, make_port, to_number
from data import BODY_H_S

TYPE = "number"
TITLE = "Number"
OUTPUTS = [make_port("out", "value", "number")]
DEFAULT_DATA = {"value": "0"}
BODY_HEIGHT = BODY_H_S
RAN_PASSED = True
FIELDS = [{"kind": "number", "key": "value", "label": "Value", "store": "string"}]


def evaluate(node, io):
    return {"out": to_number(jget(node["data"], "value"))}


def body(node, view):
    return [{"kind": "caption", "text": "Number value (click to edit)"}]
