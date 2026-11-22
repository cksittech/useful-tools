# Link: data.pathTemplate with "{value}" replaced by the wired value — a literal OS
# path (no URL-encoding, which would mangle backslashes), opened in File Explorer.
from common import UNDEFINED, jget, js_or, js_string, make_port, to_str, waiting_on_inputs
from data import BODY_H_L

TYPE = "link"
TITLE = "Link"
INPUTS = [make_port("in", "value", "any")]
# "~" is expanded by /open-path.
DEFAULT_DATA = {"pathTemplate": "~/.codex/generated_images/{value}"}
BODY_HEIGHT = BODY_H_L
RAN_PASSED = True
FIELDS = [{"kind": "text", "key": "pathTemplate", "label": "File path template"}]
waiting = waiting_on_inputs


def evaluate(node, io):
    return {"out": io.input("in")}


def body(node, view):
    value = jget(view.outs, "out")
    out = [{"kind": "caption", "text": "Path template (click to edit)"}]
    if value is UNDEFINED:
        out.append({"kind": "path", "empty": "(unconnected)"})
    else:
        path = js_string(js_or(jget(node["data"], "pathTemplate"), "")).replace("{value}", to_str(value))
        out.append({"kind": "path", "text": path})
        out.append({"kind": "open", "label": "Open in File Explorer", "path": path})
    # Set by the editor when opening failed.
    open_error = jget(node["data"], "openError")
    if open_error:
        out.append({"kind": "error", "text": to_str(open_error)})
    return out
