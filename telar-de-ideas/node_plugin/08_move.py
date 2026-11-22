# Move: during a run, moves the src folder to dst once both are present (a merge
# if dst exists). Each src -> dst pair moves once per run. No output port.
import re

from common import UNDEFINED, is_present, jget, jidx, js_string, make_port, waiting_on_inputs
from data import BODY_H_M

TYPE = "move"
TITLE = "Move"
INPUTS = [make_port("src", "source folder", "any"), make_port("dst", "destination folder", "any")]
BODY_HEIGHT = BODY_H_M
RUNNABLE = True
RESET = {"moveStatus": None, "moveMerged": None, "moveError": None}
waiting = waiting_on_inputs


# No downstream port — src/dst only let the waiting reasons see what arrived.
def evaluate(node, io):
    return {"src": io.input("src"), "dst": io.input("dst")}


def check(node, chk):
    for p in ("src", "dst"):
        if not chk.wired(p):
            chk.add("warning", f'"{chk.title()}" input "{chk.port_label(p)}" is not wired — it will never move.')


def run_state(node, outs, running):
    return {"running": False, "passed": jget(node["data"], "moveStatus") == "done"}


# An input fed by a Queue's outN only counts if that Queue delivered THIS run.
def _resolve_input(ctx, node_id, port_id):
    edge = next((e for e in ctx.eff_edges if e["to"]["node"] == node_id and e["to"]["port"] == port_id), None)
    if not edge:
        return UNDEFINED
    from_node = ctx.nodes.get(edge["from"]["node"])
    m = re.fullmatch(r"out([0-4])", edge["from"]["port"]) if from_node and from_node["type"] == "que" else None
    if m:
        delivered = ctx.runner.state(edge["from"]["node"]).get("delivered")
        return jidx(delivered, int(m.group(1))) if delivered else UNDEFINED
    return jget(ctx.ev2["values"].get(edge["from"]["node"]) or {}, edge["from"]["port"])


async def fire(node, ctx):
    r = ctx.runner
    src = _resolve_input(ctx, node["id"], "src")
    dst = _resolve_input(ctx, node["id"], "dst")
    if not is_present(src) or not is_present(dst):
        return
    key = js_string(src) + " -> " + js_string(dst)
    state = r.state(node["id"])
    if state.get("lastMove") == key:
        return
    state["lastMove"] = key
    ctx.changed = True
    host = r.host
    node_id = node["id"]
    host.update_data(node_id, {"moveStatus": "moving", "moveError": None})
    try:
        result = await r.backend.move_folder(src, dst, f"move:{r.active_run['key']}:{node_id}:{key}")
        merged = bool(result.get("merged"))
        host.update_data(node_id, {"moveStatus": "done", "moveMerged": merged, "moveError": None})
        host.log(node_id, f"moved {js_string(src)} → {js_string(dst)}{' (merged)' if merged else ''}", "success")
    except Exception as e:
        message = str(e)
        host.update_data(node_id, {"moveStatus": "error", "moveError": message})
        host.log(node_id, f"move {js_string(src)} → {js_string(dst)} failed: {message}", "error")
        host.notify(f"Failed to move folder: {message}")


# The last run's outcome only (no live preview — Move acts only during a run).
def body(node, view):
    data = node["data"]
    out = [{"kind": "caption", "text": "Moves source into destination on run"}]
    status = jget(data, "moveStatus")
    if status == "moving":
        out.append({"kind": "chip", "label": "Moving…"})
    if status == "done":
        out.append({"kind": "caption", "color": "success", "text": "Merged into the existing folder." if jget(data, "moveMerged") else "Moved."})
    if jget(data, "moveError"):
        out.append({"kind": "error", "text": js_string(jget(data, "moveError"))})
    return out
