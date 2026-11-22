# Calc: a op b (unwired inputs count as 0; x/0 and an unknown op give NaN).
import math

from common import jget, make_port, to_number
from data import BODY_H_S

TYPE = "calc"
TITLE = "Calc"
INPUTS = [make_port("a", "a", "number"), make_port("b", "b", "number")]
OUTPUTS = [make_port("out", "result", "number")]
DEFAULT_DATA = {"op": "+"}
BODY_HEIGHT = BODY_H_S
RAN_PASSED = True
FIELDS = [{"kind": "select", "key": "op", "options": [
    {"value": "+", "label": "+ Add"}, {"value": "-", "label": "− Subtract"},
    {"value": "*", "label": "× Multiply"}, {"value": "/", "label": "÷ Divide"},
]}]


def evaluate(node, io):
    a = to_number(io.input("a"))
    b = to_number(io.input("b"))
    op = jget(node["data"], "op")
    if op == "+":
        result = a + b
    elif op == "-":
        result = a - b
    elif op == "*":
        result = a * b
    elif op == "/":
        result = math.nan if b == 0 else a / b
    else:
        result = math.nan
    return {"out": result}


def body(node, view):
    return [{"kind": "caption", "text": "Operation (click to edit)"}]
