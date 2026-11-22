# tests/test_runner.py
# common.WorkflowRunner against an in-memory host and a fake backend — run
# loop, cascade, Stop, Delay scenarios, plus seeded random workflows compared
# with tests/golden/runs.json (frozen from the former runner.js; TDI_UPDATE_GOLDEN=1 rewrites it).
# Run from the project root: python -m unittest discover -s tests -p "test_*.py"
import asyncio
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
from common import UNDEFINED  # noqa: E402
from test_graph import assert_golden, canonical  # noqa: E402

OUT = [{"key": "out_r", "name": "result", "valueType": "string", "enumValues": [], "description": "", "children": []}]


def node(id, type, **data):
    return {"id": id, "type": type, "x": 0, "y": 0, "data": data}


def tmpl(id, content="say hi"):
    return node(id, "template", content=content, outputs=OUT, outputValues={}, values={})


def graph_of(*nodes):
    return {n["id"]: n for n in nodes}


_edge_seq = [0]


def edge(frm, frm_port, to, to_port):
    _edge_seq[0] += 1
    return {"id": f"e{_edge_seq[0]}", "from": {"node": frm, "port": frm_port}, "to": {"node": to, "port": to_port}}


# Fake backend. job_plan(node_id, attempt_no) -> polls until done (None = never);
# output(node_id, attempt_no) -> Structured Output dict.
class FakeBackend:
    def __init__(self, job_plan=lambda nid, n: 1, output=lambda nid, n: {"result": "ok-" + nid}):
        self.job_plan = job_plan
        self.output = output
        self.creates, self.stops, self.moves, self.jobs = [], [], [], {}
        self.polls = 0

    async def create_job(self, body):
        job_id = f"job{len(self.creates) + 1}"
        self.creates.append(body)
        attempt_no = sum(1 for b in self.creates if b["node_id"] == body["node_id"])
        self.jobs[job_id] = {"nodeId": body["node_id"], "attempt": attempt_no, "left": self.job_plan(body["node_id"], attempt_no)}
        return {"job_id": job_id}

    async def get_job(self, job_id):
        self.polls += 1
        job = self.jobs[job_id]
        if job["left"] is None:
            return {"status": "running"}
        job["left"] -= 1
        if job["left"] > 0:
            return {"status": "running"}
        return {"status": "done", "output": self.output(job["nodeId"], job["attempt"]), "thread_id": "th-" + job["nodeId"]}

    async def stop_job(self, job_id):
        self.stops.append(job_id)

    async def move_folder(self, src, dst, operation_id):
        self.moves.append({"src": src, "dst": dst, "operation_id": operation_id})
        return {"ok": True, "merged": False}


# In-memory UI: get_nodes() always reflects every update_data immediately.
class Host:
    def __init__(self, nodes, edges):
        self.nodes, self.edges = nodes, edges
        self.logs, self.running, self.blocked = [], [], 0

    def get_nodes(self):
        return self.nodes

    def get_edges(self):
        return self.edges

    def update_data(self, node_id, patch):
        if node_id in self.nodes:
            self.nodes = common.with_data(self.nodes, node_id, patch)

    def apply_to_nodes(self, fn):
        self.nodes = fn(self.nodes)

    def log(self, node_id, message, level="info"):
        self.logs.append({"nodeId": node_id, "message": message, "level": level})

    def notify(self, message):
        pass

    def on_running_change(self, running):
        self.running.append(running)

    def on_run_blocked(self, count):
        self.blocked += 1

    def messages(self, node_id):
        return [l["message"] for l in self.logs if l["nodeId"] == node_id]

    def data(self, node_id):
        return self.nodes[node_id]["data"]


def new_runner(host, backend):
    return common.WorkflowRunner(host, backend, poll_interval_ms=5)


def value_of(host, node_id, port="out"):
    return common.evaluate_all(host.nodes, host.edges)["values"][node_id][port]


class RunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_result_flows_to_output_and_job_has_operation_id(self):
        srv = FakeBackend(job_plan=lambda nid, n: 2)
        host = Host(graph_of(tmpl("t"), node("s", "sink")), [edge("t", "out_r", "s", "in")])
        await new_runner(host, srv).run_workflow()
        self.assertEqual(host.data("t")["runStatus"], "done")
        self.assertEqual(value_of(host, "s"), "ok-t")
        self.assertTrue(srv.creates[0]["operation_id"])
        self.assertEqual(host.running, [True, False])

    async def test_pre_run_errors_block_without_backend(self):
        srv = FakeBackend()
        host = Host(graph_of(tmpl("t", "   ")), [])
        await new_runner(host, srv).run_workflow()
        self.assertEqual(host.blocked, 1)
        self.assertEqual(srv.creates, [])
        self.assertEqual(host.running, [])

    async def test_gate_each_queue_move_each_passing_member_once(self):
        srv = FakeBackend()
        nodes = graph_of(node("n1", "number", value="5"), node("n2", "number", value="9"), node("n3", "number", value="7"),
                         node("g", "gate", matchValue="5,7", matchMode="EACH"), node("q", "que", queue=[], inputCount=1),
                         node("d", "text", value="D:/dst"), node("m", "move"))
        edges = [edge("g", "value_out", "q", "in0"), edge("q", "out0", "m", "src"), edge("d", "out", "m", "dst")]
        for n in ("n1", "n2", "n3"):
            edges += [edge(n, "out", "g", "compare"), edge(n, "out", "g", "value")]
        host = Host(nodes, edges)
        await new_runner(host, srv).run_workflow()
        self.assertEqual([m["src"] for m in srv.moves], [5, 7])
        self.assertTrue(all(m["operation_id"].startswith("move:") for m in srv.moves))

    async def test_templates_finishing_together_each_reach_move_once(self):
        srv = FakeBackend(job_plan=lambda nid, n: 4 if nid == "t3" else 2)
        nodes = graph_of(tmpl("t1"), tmpl("t2"), tmpl("t3"), node("q", "que", queue=[], inputCount=1),
                         node("d", "text", value="D:/dst"), node("m", "move"))
        edges = [edge("t1", "out_r", "q", "in0"), edge("t2", "out_r", "q", "in0"), edge("t3", "out_r", "q", "in0"),
                 edge("q", "out0", "m", "src"), edge("d", "out", "m", "dst")]
        host = Host(nodes, edges)
        await new_runner(host, srv).run_workflow()
        self.assertEqual(sorted(m["src"] for m in srv.moves), ["ok-t1", "ok-t2", "ok-t3"])

    async def test_stop_mid_job(self):
        srv = FakeBackend(job_plan=lambda nid, n: None)
        nodes = graph_of(tmpl("t"), node("d", "text", value="D:/dst"), node("m", "move"))
        host = Host(nodes, [edge("t", "out_r", "m", "src"), edge("d", "out", "m", "dst")])
        runner = new_runner(host, srv)
        done = asyncio.ensure_future(runner.run_workflow())
        await asyncio.sleep(0.05)
        runner.stop_workflow()
        await done
        polls_at_stop = srv.polls
        await asyncio.sleep(0.05)
        self.assertEqual(srv.stops, ["job1"])
        self.assertEqual(srv.polls, polls_at_stop)
        self.assertEqual(host.data("t")["runStatus"], "stopped")
        self.assertEqual(srv.moves, [])
        self.assertTrue(any(l["message"].startswith("run stopped") for l in host.logs))
        self.assertTrue(runner.is_idle())

    async def test_wrapper_retries_until_condition_passes(self):
        srv = FakeBackend(output=lambda nid, n: {"result": "success" if n >= 2 else "fail"})
        nodes = graph_of(tmpl("t"), node("w", "wrapper", conditionGroups=[[{"key": "out_r", "op": "eq", "value": "success"}]], maxRetries=3),
                         node("s", "sink"))
        edges = [edge("w", "__wrapperRef", "t", "__trigger"), edge("w", "out_r", "s", "in")]
        host = Host(nodes, edges)
        await new_runner(host, srv).run_workflow()
        self.assertIs(host.data("w")["wrapperPassed"], True)
        self.assertEqual(host.data("w")["wrapperAttempt"], 1)
        self.assertEqual(value_of(host, "s"), "success")
        prev = host.data("t")["previousRun"]  # the attempt the retry replaced
        self.assertEqual((prev["runStatus"], prev["response"]["output"], prev["response"]["threadId"]), ("done", {"result": "fail"}, "th-t"))

    async def test_wrapper_unlimited_retries_until_condition_passes(self):
        srv = FakeBackend(output=lambda nid, n: {"result": "success" if n >= 8 else "fail"})
        nodes = graph_of(tmpl("t"), node("w", "wrapper", conditionGroups=[[{"key": "out_r", "op": "eq", "value": "success"}]],
                                          maxRetries=common.UNLIMITED_RETRIES))
        host = Host(nodes, [edge("w", "__wrapperRef", "t", "__trigger")])
        await new_runner(host, srv).run_workflow()
        self.assertIs(host.data("w")["wrapperPassed"], True)
        self.assertEqual(host.data("w")["wrapperAttempt"], 7)
        self.assertTrue(any(l["message"] == "conditions not met — retry 7/∞" for l in host.logs))

    async def test_wrapper_total_condition_sums_attempts(self):
        srv = FakeBackend(output=lambda nid, n: {"result": "4"})
        conds = [[{"key": "out_r", "op": "gte", "value": "10", "total": True}]]
        nodes = graph_of(tmpl("t"), node("w", "wrapper", conditionGroups=conds, maxRetries=5))
        host = Host(nodes, [edge("w", "__wrapperRef", "t", "__trigger")])
        await new_runner(host, srv).run_workflow()
        self.assertEqual(len(srv.creates), 3)  # 4 + 4 + 4 = 12 >= 10
        self.assertIs(host.data("w")["wrapperPassed"], True)
        self.assertEqual(host.data("w")["wrapperTotals"], {"out_r": 12})

    async def test_trigger_gated_node_is_skipped(self):
        srv = FakeBackend()
        nodes = graph_of(node("x", "text", value="no"), node("g", "gate", matchValue="yes"), tmpl("t"))
        host = Host(nodes, [edge("x", "out", "g", "compare"), edge("g", "out", "t", "__trigger")])
        await new_runner(host, srv).run_workflow()
        self.assertEqual(host.data("t")["runStatus"], "skipped")
        self.assertEqual(srv.creates, [])

    async def test_api_response_counts_as_produced_once_every_field_has_a_value(self):
        srv = FakeBackend(output=lambda nid, n: {"result": "R"})
        nodes = graph_of(node("i", "apiInput", params=[{"name": "q", "valueType": "string", "value": "hi"}]), tmpl("t", "ask {q}"),
                         node("r", "apiResponse", fields=["a", "b"]), node("r2", "apiResponse", fields=["a", "z"]))
        edges = [edge("i", "param:q", "t", "string:q"), edge("t", "out_r", "r", "field:a"), edge("i", "param:q", "r", "field:b"),
                 edge("t", "out_r", "r2", "field:a")]
        # Two API Response nodes is a pre-run error — check one at a time.
        host = Host({k: v for k, v in nodes.items() if k != "r2"}, edges[:3])
        await new_runner(host, srv).run_workflow()
        self.assertEqual(srv.creates[0]["prompt"], "ask hi")
        self.assertIs(host.data("r")["__ranPassed"], True)
        self.assertIs(host.data("i")["__ranPassed"], True)
        host = Host({k: v for k, v in nodes.items() if k != "r"}, edges[:2] + edges[3:])
        await new_runner(host, srv).run_workflow()
        self.assertIs(host.data("r2")["__ranPassed"], False)

    async def test_chained_templates_pass_values_and_schema(self):
        srv = FakeBackend(output=lambda nid, n: {"result": f"[{nid}]"})
        nodes = graph_of(node("x", "text", value="hello"), tmpl("a", "first {in}"), tmpl("b", "second {in}"), node("s", "sink"))
        edges = [edge("x", "out", "a", "string:in"), edge("a", "out_r", "b", "string:in"), edge("b", "out_r", "s", "in")]
        host = Host(nodes, edges)
        await new_runner(host, srv).run_workflow()
        self.assertEqual([c["prompt"] for c in srv.creates], ["first hello", "second [a]"])
        self.assertEqual(srv.creates[0]["output_schema"], {"type": "object", "properties": {"result": {"type": "string", "description": ""}},
                                                           "required": ["result"], "additionalProperties": False})
        self.assertEqual(value_of(host, "s"), "[b]")


def delay_graph(seconds):
    return Host(graph_of(node("x", "text", value="go"), node("q", "que", queue=[], inputCount=1),
                         node("d", "delay", seconds=seconds), node("st", "stack", values=["a", "b"])),
                [edge("x", "out", "q", "in0"), edge("q", "signal", "d", "in"), edge("d", "out", "st", "pop")])


class DelayTest(unittest.IsolatedAsyncioTestCase):
    async def test_delay_relays_then_stack_pops(self):
        host = delay_graph(0.03)
        runner = new_runner(host, FakeBackend())
        await runner.run_workflow()
        self.assertEqual(host.data("d")["delayStatus"], "waiting")
        self.assertFalse(runner.is_idle())
        await asyncio.sleep(0.15)
        self.assertEqual(host.data("d")["delayStatus"], "done")
        self.assertEqual(host.data("st")["__stack"], ["b"])
        self.assertTrue(runner.is_idle())

    async def test_stop_after_run_cancels_pending_delay(self):
        host = delay_graph(0.05)
        runner = new_runner(host, FakeBackend())
        await runner.run_workflow()
        runner.stop_workflow()
        self.assertIs(host.data("d")["delayStatus"], UNDEFINED)
        self.assertTrue(runner.is_idle())
        await asyncio.sleep(0.15)
        self.assertNotIn("__stack", host.data("st"))
        self.assertNotIn("relayed signal", host.messages("d"))

    async def test_earlier_runs_delay_never_fires_into_newer_run(self):
        host = delay_graph(0.06)
        runner = new_runner(host, FakeBackend())
        await runner.run_workflow()
        await asyncio.sleep(0.01)
        host.update_data("d", {"seconds": 0.3})
        await runner.run_workflow()
        await asyncio.sleep(0.12)
        self.assertNotIn("__stack", host.data("st"))
        runner.stop_workflow()

    async def test_run_trigger_ignored_while_running_and_reset_clears(self):
        nodes = graph_of(node("x", "text", value="go"), node("q", "que", queue=[], inputCount=1),
                         node("rt", "runtrigger"), node("r", "reset"), node("g", "gate", matchValue="go", lastPass=True))
        edges = [edge("x", "out", "q", "in0"), edge("q", "signal", "rt", "signal"), edge("q", "signal", "r", "signal"), edge("x", "out", "g", "compare")]
        host = Host(nodes, edges)
        runner = new_runner(host, FakeBackend())
        await runner.run_workflow()
        await asyncio.sleep(0.02)
        self.assertEqual(host.running, [True, False])
        self.assertEqual(host.data("rt")["runTriggerStatus"], "done")
        self.assertEqual(host.data("r")["resetStatus"], "done")


# --- golden runs ----------------------------------------------------------------------


# Answers exactly like the fake server tests/golden/runs.json was recorded with.
class FakePlanBackend:
    def __init__(self, plan):
        self.plan = plan
        self.creates, self.moves, self.jobs = [], [], {}

    async def create_job(self, body):
        attempt = sum(1 for c in self.creates if c["node_id"] == body["node_id"])
        steps = self.plan.get(body["node_id"]) or [{"polls": 1, "status": "done", "output": {}}]
        step = steps[min(attempt, len(steps) - 1)]
        job_id = f"{body['node_id']}#{attempt + 1}"
        self.creates.append({"node_id": body["node_id"], "prompt": body["prompt"], "output_schema": body["output_schema"]})
        self.jobs[job_id] = {"step": step, "left": step["polls"], "nodeId": body["node_id"]}
        return {"job_id": job_id}

    async def get_job(self, job_id):
        job = self.jobs[job_id]
        job["left"] -= 1
        if job["left"] > 0:
            return {"status": "running", "thread_id": "th-" + job["nodeId"]}
        step = job["step"]
        return {"status": step["status"], "output": step.get("output"), "error": step.get("error"), "thread_id": "th-" + job["nodeId"]}

    async def stop_job(self, job_id):
        pass

    async def move_folder(self, src, dst, operation_id):
        self.moves.append([src, dst])
        if "fail" in common.js_string(src):
            raise RuntimeError("refused")
        return {"ok": True, "merged": "merge" in common.js_string(dst)}


def py_run(case):
    async def go():
        host = Host(case["nodes"], case["edges"])
        backend = FakePlanBackend(case["plan"])
        await common.WorkflowRunner(host, backend, poll_interval_ms=1).run_workflow()
        logs = [[l["nodeId"], l["message"], l["level"]] for l in host.logs
                if not l["message"].startswith(("run finished in ", "run stopped after "))]
        return {"nodes": {nid: host.nodes[nid]["data"] for nid in common.js_keys(host.nodes)},
                "creates": backend.creates, "moves": backend.moves, "logs": logs}
    try:
        return canonical(asyncio.run(go()))
    except Exception as e:
        return {"$error": repr(e)}


OUT2 = OUT + [{"key": "out_n", "name": "count", "valueType": "integer", "enumValues": [], "description": "", "children": []}]


# How tests/golden/runs.json's cases were generated (kept for new cases). A random but runnable workflow: Text -> Created Nodes (chained), Gates on
# their results (signal -> trigger, value_out -> Queue -> Move), Group/Wrapper
# around some of them, Stack/Reset/Run Trigger on Queue signals. No Delay —
# its wall-clock timers aren't comparable across the two event loops.
def random_run_case(rng):
    nodes, edges, plan = {}, [], {}
    seq = [0]

    def add(n):
        nodes[n["id"]] = n
        return n["id"]

    def wire(a, ap, b, bp):
        seq[0] += 1
        edges.append({"id": f"e{seq[0]}", "from": {"node": a, "port": ap}, "to": {"node": b, "port": bp}})

    texts = [add(node(f"x{i}", "text", value=rng.choice(["hello", "ok", "5", "fail/dir", "D:/dst", "D:/merge"]))) for i in range(rng.randint(1, 3))]
    templates = []
    for i in range(rng.randint(1, 5)):
        tid = add(node(f"t{i}", "template", content=rng.choice(["do {a}", "do {a} and {b}", "plain task", "<n#2> {a}"]),
                       outputs=OUT2[: rng.randint(1, 2)], outputValues={}, values={}))
        for p in common.extract_placeholders(nodes[tid]["data"]["content"]):
            if rng.random() < 0.8:
                src = rng.choice(texts + templates)
                wire(src, "out" if src.startswith("x") else rng.choice(["out_r", "__thread_id"]), tid, p["key"])
        # Distinct poll counts per node keep completion order deterministic on both sides.
        plan[tid] = [{"polls": 2 * i + 1 + 10 * k, "status": rng.choice(["done", "done", "done", "error"]),
                      "output": {"result": rng.choice(["ok", "ng", "5", "D:/src", "fail"]), "count": rng.choice([1, 2, 3])},
                      "error": "boom"} for k in range(3)]
        templates.append(tid)
    for i in range(rng.randint(0, 2)):
        gid = add(node(f"g{i}", "gate", matchValue=rng.choice(["ok", "ok,5", "ng"]), matchMode=rng.choice(["AND", "OR", "EACH"])))
        for t in rng.sample(templates, rng.randint(1, len(templates))):
            wire(t, "out_r", gid, "compare")
            if rng.random() < 0.7:
                wire(t, "out_r", gid, "value")
        if rng.random() < 0.4:
            tid = add(node(f"tg{i}", "template", content="gated", outputs=OUT, outputValues={}))
            plan[tid] = [{"polls": 30 + i, "status": "done", "output": {"result": "gated-ok"}}]
            wire(gid, "out", tid, "__trigger")
            templates.append(tid)
        if rng.random() < 0.8:
            qid = add(node(f"q{i}", "que", queue=[], inputCount=1))
            wire(gid, "value_out", qid, "in0")
            mid = add(node(f"m{i}", "move"))
            wire(qid, "out0", mid, "src")
            wire(rng.choice(texts), "out", mid, "dst")
            extra = rng.choice([None, "stack", "reset", "runtrigger", "sink"])
            if extra == "stack":
                wire(qid, "signal", add(node(f"st{i}", "stack", values=["a", "b", "c"])), "pop")
            elif extra:
                wire(qid, "signal", add(node(f"{extra[:2]}{i}", extra)), "signal" if extra != "sink" else "in")
    if len(templates) >= 2 and rng.random() < 0.4:
        grp = add(node("grp", "group"))
        for t in rng.sample(templates, 2):
            wire(grp, "__ref", t, "__trigger")
        wire(grp, "result", add(node("gs", "sink")), "in")
    if rng.random() < 0.5:
        t = rng.choice(templates)
        if not any(e["to"]["node"] == t and e["to"]["port"] == "__trigger" for e in edges):
            wid = add(node("w", "wrapper", conditionGroups=rng.choice([[], [[{"key": "out_r", "op": "eq", "value": "ok"}]]]),
                           maxRetries=rng.choice([0, 1, 2])))
            wire(wid, "__wrapperRef", t, "__trigger")
            wire(wid, "out_r", add(node("ws", "sink")), "in")
            plan[t] = [{**plan[t][0], "output": {"result": "ng", "count": 1}}, {**plan[t][1], "status": "done", "output": {"result": "ok", "count": 2}}]
    for t in templates:
        if rng.random() < 0.5:
            wire(t, "out_r", add(node(f"s_{t}", "sink")), "in")
    if rng.random() < 0.3:
        fan = add(node("qf", "que", queue=[], inputCount=1))
        for t in rng.sample(templates, min(len(templates), 3)):
            wire(t, "out_r", fan, "in0")
        wire(fan, "out0", add(node("mf", "move")), "src")
        wire(rng.choice(texts), "out", "mf", "dst")
    return {"nodes": nodes, "edges": edges, "plan": plan}


class GoldenRunTest(unittest.TestCase):
    def test_random_workflows_match_golden(self):
        assert_golden(self, "runs", py_run)


if __name__ == "__main__":
    unittest.main()
