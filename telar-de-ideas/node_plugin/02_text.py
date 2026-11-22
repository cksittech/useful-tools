# Text: a constant string. The card never shows it — some workflows keep sensitive text here.
from common import jget, js_or, make_port
from data import BODY_H_S

TYPE = "text"
TITLE = "Text"
OUTPUTS = [make_port("out", "value", "string")]
DEFAULT_DATA = {"value": ""}
BODY_HEIGHT = BODY_H_S
RAN_PASSED = True
FIELDS = [{"kind": "text", "key": "value", "multiline": True, "rows": 12}]


def evaluate(node, io):
    return {"out": js_or(jget(node["data"], "value"), "")}


def body(node, view):
    return [{"kind": "caption", "text": "Text value (click to edit)"}]
