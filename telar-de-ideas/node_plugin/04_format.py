# Format: data.content with its placeholders ({text} <number> [a,b,c], same syntax
# as AI Node) filled from one input each; an unwired one uses its default.
from common import UNDEFINED, extract_placeholders, fill_placeholders, is_present, jget, make_port, placeholder_inputs, waiting_on_inputs
from data import BODY_H_S

TYPE = "format"
TITLE = "Format"
OUTPUTS = [make_port("out", "value", "string")]
DEFAULT_DATA = {"content": ""}
BODY_HEIGHT = BODY_H_S
RAN_PASSED = True
FIELDS = [{"kind": "text", "key": "content", "multiline": True, "rows": 12,
           "helper": 'Placeholders: {text}  <number>  [option1,option2]  ("#" sets a default, e.g. <count#3>)'}]
waiting = waiting_on_inputs


def ports(node, nodes, edges):
    return {"inputs": placeholder_inputs(jget(node["data"], "content"))}


def evaluate(node, io):
    content = jget(node["data"], "content")
    resolved = {}
    # A wired placeholder is ready only once its value is present (else a pending
    # upstream like thread_id renders as a wrong string).
    all_wired_ready = True
    for p in extract_placeholders(content):
        from_edge = io.input(p["key"])
        if io.wired(p["key"]) and not is_present(from_edge):
            all_wired_ready = False
        resolved[p["key"]] = from_edge if from_edge is not UNDEFINED else p["defaultValue"]
    return {"out": fill_placeholders(content, resolved) if all_wired_ready else UNDEFINED}


def body(node, view):
    return [{"kind": "caption", "text": "Format template (click to edit)"}]
