# tests/test_graph.py
# Graph logic (common.py + node_plugin/) against tests/golden/*.json: evaluation,
# validation, run helpers and the editor view, frozen from the editor's former JS
# implementation (edge cases, saved workflows, seeded random graphs).
# TDI_UPDATE_GOLDEN=1 rewrites them — review the diff before keeping it.
# Run from the project root: python -m unittest discover -s tests -p "test_*.py"
import json
import math
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import common  # noqa: E402

GOLDEN_DIR = ROOT / "tests" / "golden"
QUEUE = common.node_type("que")


# Tagged so JSON can't blur undefined vs null or number formatting.
def canonical(v):
    if v is common.UNDEFINED:
        return {"$undef": 1}
    if common.is_number(v):
        return {"$n": common.js_number_str(v)}
    if isinstance(v, (list, tuple)):
        return [canonical(x) for x in v]
    if isinstance(v, dict):
        return {k: canonical(x) for k, x in v.items()}
    return v


def _py_queue_latch(c):
    nodes = c["nodes"]
    state = {}
    frames = []
    for frame in c["frames"]:
        for nid, patch in frame.items():
            nodes = common.with_data(nodes, nid, patch)
        eff = common.expand_edges(nodes, c["edges"])
        ev = common.evaluate_all(nodes, c["edges"])
        out = {}
        for nid in common.js_keys(nodes):
            if nodes[nid]["type"] != "que":
                continue
            step = QUEUE.step_queue_latch(nodes[nid], eff, ev, state.get(nid))
            input_set = step.pop("inputSet")
            state[nid] = step
            out[nid] = {"inputSet": input_set, "latch": step}
        frames.append(out)
    return frames


# Waiting reasons, card border state and multi-wire ports — what the editor shows.
def _py_editor(c):
    nodes, edges = c["nodes"], c["edges"]
    ev = common.evaluate_all(nodes, edges)
    run_state = {nid: {"latch": latch} for nid, latch in c["latch"].items()}
    multi = {}
    for nid in common.js_keys(nodes):
        ids = [p["id"] for p in common.get_node_def(nodes[nid], nodes, edges)["inputs"]] + ["__trigger", "in9", "compare", "value"]
        multi[nid] = [p for p in ids if common.port_accepts_multiple(nodes[nid], p)]
    return {"waiting": common.compute_waiting_reasons(nodes, edges, ev, run_state),
            "runStates": common.compute_run_states(nodes, edges, ev, c["running"]), "multi": multi}


PY_OPS = {
    "validate": lambda c: common.validate_workflow(c["nodes"], c["edges"]),
    "runHelpers": lambda c: {
        "blocked": common.compute_trigger_blocked_nodes(c["nodes"], c["edges"]),
        "reset": common.apply_reset_to_nodes(c["nodes"]),
    },
    "levels": lambda c: common.node_levels_in_dependency_order(c["nodes"], c["edges"]),
    "queueLatch": _py_queue_latch,
    "values": lambda c: [{"format": common.format_run_output_value(v), "short": common.short_value(v, 8), "json": common.js_json_stringify(v)}
                         for v in c["values"]],
    "schema": lambda c: common.build_output_json_schema(c["fields"]),
    "wrapper": lambda c: common.wrapper_conditions_pass(c["groups"], c["outputValues"]),
}


def py_eval(case):
    try:
        if "op" in case:
            return canonical(PY_OPS[case["op"]](case))
        if "latch" in case:
            return canonical(_py_editor(case))
        nodes, edges = case["nodes"], case["edges"]
        return canonical({
            "evaluation": common.evaluate_all(nodes, edges),
            "edges": common.expand_edges(nodes, edges),
            "defs": {nid: common.get_node_def(nodes[nid], nodes, edges) for nid in common.js_keys(nodes)},
        })
    except Exception:
        return {"$error": True}


# Compares compute(case) with tests/golden/<name>.json's frozen results (or,
# with TDI_UPDATE_GOLDEN=1, rewrites them — review the diff before keeping it).
def assert_golden(testcase, name, compute):
    path = GOLDEN_DIR / f"{name}.json"
    golden = json.loads(path.read_text(encoding="utf-8"))
    if os.environ.get("TDI_UPDATE_GOLDEN"):
        golden["expected"] = [compute(c) for c in golden["cases"]]
        path.write_text(json.dumps(golden, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        return
    for i, (c, want) in enumerate(zip(golden["cases"], golden["expected"])):
        got = compute(c)
        if got != want:
            testcase.fail(f"{name}[{i}] differs from golden\ncase: {json.dumps(c, ensure_ascii=False)[:3000]}\n"
                          f"want: {json.dumps(want, ensure_ascii=False)[:3000]}\ngot: {json.dumps(got, ensure_ascii=False)[:3000]}")


def node(id, type, **data):
    return {"id": id, "type": type, "x": 0, "y": 0, "data": data}


def edge(id, frm, frm_port, to, to_port):
    return {"id": id, "from": {"node": frm, "port": frm_port}, "to": {"node": to, "port": to_port}}


def graph(*nodes):
    return {n["id"]: n for n in nodes}


class GoldenTest(unittest.TestCase):
    def test_evaluate(self):
        assert_golden(self, "evaluate", py_eval)

    def test_validate(self):
        assert_golden(self, "validate", py_eval)

    def test_run_helpers(self):
        assert_golden(self, "run_helpers", py_eval)

    def test_wrapper_conditions(self):
        assert_golden(self, "wrapper_conditions", py_eval)

    def test_editor(self):
        assert_golden(self, "editor", py_eval)

    def test_queue_latch(self):
        assert_golden(self, "queue_latch", py_eval)

    def test_levels(self):
        assert_golden(self, "levels", py_eval)

    def test_value_formatting_and_output_schema(self):
        assert_golden(self, "values_schema", py_eval)


class EvaluationTest(unittest.TestCase):
    def test_thread_id_port_waits_for_done(self):
        for status, want in (("running", ""), ("stopped", ""), ("error", ""), ("done", "th-1")):
            nodes = {"t": node("t", "template", content="x", threadId="th-1", runStatus=status)}
            self.assertEqual(common.evaluate_all(nodes, [])["values"]["t"][common.THREAD_ID_OUTPUT_KEY], want, status)

    def test_is_present(self):
        self.assertTrue(common.is_present(0))
        self.assertTrue(common.is_present(False))
        for v in (common.UNDEFINED, None, ""):
            self.assertFalse(common.is_present(v))

    def test_gate_and_or_hold_verdict_until_every_compare_wire_arrives(self):
        def gate(t2, mode):
            nodes = graph(node("t1", "text", value="5"), node("t2", "text", value=t2), node("g", "gate", matchValue="5", matchMode=mode))
            edges = [edge("e1", "t1", "out", "g", "compare"), edge("e2", "t2", "out", "g", "compare")]
            return common.evaluate_all(nodes, edges)["values"]["g"]
        pending = gate("", "OR")
        self.assertEqual((pending["_pending"], pending["_pass"]), (True, False))
        self.assertIs(pending["out"], common.UNDEFINED)  # not False — False is present, it would fire consumers
        self.assertTrue(gate("x", "OR")["_pass"])
        self.assertFalse(gate("x", "AND")["_pass"])
        self.assertTrue(gate("5", "AND")["_pass"])

    def test_gate_each_splits_value_out_per_compare_source(self):
        nodes = graph(node("n1", "number", value="5"), node("n2", "number", value="9"), node("n3", "number", value="7"),
                      node("g", "gate", matchValue="5,7", matchMode="EACH"), node("s", "sink"))
        edges = [e for i, n in enumerate(("n1", "n2", "n3"))
                 for e in (edge(f"c{i}", n, "out", "g", "compare"), edge(f"v{i}", n, "out", "g", "value"))]
        edges.append(edge("vo", "g", "value_out", "s", "in"))
        expanded = [e["from"]["port"] for e in common.expand_edges(nodes, edges) if e["from"]["node"] == "g"]
        self.assertEqual(expanded, ["value_out@n1", "value_out@n2", "value_out@n3"])
        g = common.evaluate_all(nodes, edges)["values"]["g"]
        self.assertEqual((g["value_out@n1"], g["value_out@n2"], g["value_out@n3"]), (5.0, common.UNDEFINED, 7.0))
        self.assertNotIn("value_out", g)

    def test_delay_and_queue_signal_undefined_before_first_pulse(self):
        v = common.evaluate_all(graph(node("d", "delay", seconds=1), node("q", "que", queue=[])), [])["values"]
        self.assertIs(v["d"]["out"], common.UNDEFINED)
        self.assertIs(v["q"]["signal"], common.UNDEFINED)

    # Group(G) -> Wrapper(W) -> Created Node(T): exercises the full expansion order.
    def test_group_wrapper_gate_expansion_keys_value_out_by_linked_node(self):
        nodes = graph(node("T", "template", content="x", outputs=[{"key": "out_r", "name": "result"}], outputValues={"out_r": "ok"}),
                      node("W", "wrapper", conditionGroups=[]), node("G", "group"),
                      node("g", "gate", matchValue="ok", matchMode="EACH"), node("s", "sink"))
        edges = [edge("r1", "W", "__wrapperRef", "T", "__trigger"), edge("r2", "G", "__ref", "W", "__trigger"),
                 edge("e1", "G", "result", "g", "compare"), edge("e2", "G", "result", "g", "value"), edge("vo", "g", "value_out", "s", "in")]
        eff = common.expand_edges(nodes, edges)
        self.assertEqual(next(e for e in eff if e["to"]["node"] == "s")["from"]["port"], "value_out@T")
        self.assertFalse(any(e["from"]["node"] == "G" and e["from"]["port"] == "result" for e in eff))
        v = common.evaluate_all(nodes, edges)["values"]
        self.assertEqual((v["g"]["value_out@T"], v["s"]["out"]), ("ok", "ok"))

    def test_wrapper_gates_outputs_but_not_a_gate_compare(self):
        nodes = graph(node("T", "template", content="x", outputs=[{"key": "out_r", "name": "result"}], outputValues={"out_r": "ok"}),
                      node("W", "wrapper", conditionGroups=[[{"key": "out_r", "op": "eq", "value": "ok"}]]), node("s", "sink"),
                      node("g", "gate", matchValue="ok", matchMode="AND"))
        edges = [edge("r", "W", "__wrapperRef", "T", "__trigger"), edge("e1", "W", "out_r", "s", "in"), edge("e2", "W", "out_r", "g", "compare")]
        before = common.evaluate_all(nodes, edges)["values"]
        self.assertIs(before["s"]["out"], common.UNDEFINED)
        self.assertTrue(before["g"]["_pass"])
        nodes["W"]["data"]["wrapperPassed"] = True
        self.assertEqual(common.evaluate_all(nodes, edges)["values"]["s"]["out"], "ok")

    def test_fmt_value(self):
        cases = [(common.UNDEFINED, "(unconnected)"), (None, "(unconnected)"), ("", "(empty string)"), (1 / 3, "0.333333"),
                 (2.5e-6, "0.000003"), (-2.5e-6, "-0.000002"),(math.inf, "Infinity"), (1e303, "Infinity"), (True, "true"), ("x", "x")]
        for v, want in cases:
            self.assertEqual(common.fmt_value(v), want, v)


class ValidationTest(unittest.TestCase):
    def issues(self, nodes, edges):
        return common.validate_workflow(nodes, edges)

    def test_well_wired_graph_has_no_issues(self):
        self.assertEqual(self.issues(graph(node("t", "text", value="a"), node("s", "sink")), [edge("e", "t", "out", "s", "in")]), [])

    def test_malformed_shapes_are_schema_errors_tied_to_the_node(self):
        nodes = graph(node("g", "gate", matchMode="XOR"), {"id": "b", "type": "nope", "x": 0, "y": 0, "data": {}})
        issues = self.issues(nodes, [{"id": "e1", "from": {"node": "g"}, "to": {"node": "b", "port": "in"}}])
        self.assertTrue(all(i["kind"] == "schema" and i["level"] == "error" for i in issues))
        self.assertTrue(any(i["nodeId"] == "g" and "matchMode" in i["message"] for i in issues))
        self.assertTrue(any(i["nodeId"] == "b" and "type" in i["message"] for i in issues))
        self.assertTrue(any(i["edgeId"] == "e1" for i in issues))

    def test_wires_to_missing_nodes_or_ports_are_removable_warnings(self):
        nodes = graph(node("f", "format", content="{a}"), node("t", "text", value="x"))
        issues = self.issues(nodes, [edge("w1", "t", "out", "f", "string:gone"), edge("w2", "t", "out", "ghost", "in")])
        self.assertFalse([i for i in issues if i["level"] == "error"])
        self.assertEqual(sorted(i["edgeId"] for i in issues if i.get("fix") == "removeEdge"), ["w1", "w2"])

    def test_several_wires_into_a_single_wire_port(self):
        nodes = graph(node("a", "text", value="1"), node("b", "text", value="2"), node("s", "sink"), node("g", "gate", matchValue="1"))
        bad = self.issues(nodes, [edge("1", "a", "out", "s", "in"), edge("2", "b", "out", "s", "in"), edge("3", "a", "out", "g", "compare")])
        self.assertEqual([i["nodeId"] for i in bad if i["level"] == "error"], ["s"])
        ok = self.issues(nodes, [edge("1", "a", "out", "g", "compare"), edge("2", "b", "out", "g", "compare"), edge("3", "a", "out", "s", "in")])
        self.assertFalse([i for i in ok if i["level"] == "error"])

    def test_waiting_reasons(self):
        nodes = graph(node("a", "text", value="x"), node("b", "text", value=""), node("g", "gate", matchValue="x", matchMode="AND"),
                      node("q", "que", inputCount=2), node("src", "text", value="C:/a"), node("dst", "text", value=""), node("m", "move"))
        edges = [edge("1", "a", "out", "g", "compare"), edge("2", "b", "out", "g", "compare"),
                 edge("3", "src", "out", "m", "src"), edge("4", "dst", "out", "m", "dst")]
        r = common.compute_waiting_reasons(nodes, edges, common.evaluate_all(nodes, edges), {"q": {"latch": {"portLatch": {"in0": "v"}}}})
        self.assertEqual(r["g"], ["compare: waiting on Text"])
        self.assertEqual(r["q"], ["not yet received: value 2"])
        self.assertEqual(r["m"], ["not yet received: destination folder"])
        self.assertNotIn("a", r)


class EditorViewTest(unittest.TestCase):
    def test_wrapper_total_condition(self):
        cond = {"key": "k", "op": "gte", "value": "10", "total": True}
        self.assertFalse(common.wrapper_conditions_pass([[cond]], {"k": "9"}, {}))
        totals = common.add_wrapper_totals([[cond]], {"k": 6}, {"k": "4"})
        self.assertEqual(totals, {"k": 10})
        self.assertTrue(common.wrapper_conditions_pass([[cond]], {"k": "4"}, totals))
        self.assertFalse(common.wrapper_conditions_pass([[{**cond, "total": False}]], {"k": "4"}, totals))
        bad = node("w", "wrapper", conditionGroups=[[{**cond, "total": "yes"}]])
        self.assertTrue(any("total must be boolean" in i["message"] for i in common.validate_workflow({"w": bad}, [])))

    def test_wrapper_unlimited_retries(self):
        def issues(v):
            return [i["message"] for i in common.validate_workflow({"w": node("w", "wrapper", maxRetries=v)}, []) if "maxRetries" in i["message"]]
        self.assertEqual(issues(common.UNLIMITED_RETRIES), [])
        self.assertNotEqual(issues(-2), [])
        w = node("w", "wrapper", maxRetries=common.UNLIMITED_RETRIES, wrapperAttempt=2)
        body = common.editor_view({"w": w}, [])["nodes"]["w"]["body"]
        self.assertIn("Attempt 2/∞", [b.get("label") for b in body])

    def test_node_types_info_lists_files_in_name_order_then_core(self):
        info = common.node_types_info()
        self.assertEqual(info["errors"], [])
        types = [t["type"] for t in info["types"]]
        self.assertEqual(types[:3], ["number", "text", "calc"])
        self.assertEqual(types[-5:], ["template", "group", "wrapper", "apiInput", "apiResponse"])
        que = next(t for t in info["types"] if t["type"] == "que")
        self.assertEqual(que["multiInputs"], ["in0", "in1", "in2", "in3", "in4"])
        self.assertEqual(que["reset"], {"set": {"queue": [], "__seq": 0}, "unset": ["__dequeuedValues"]})
        self.assertFalse(next(t for t in info["types"] if t["type"] == "template")["menu"])
        self.assertEqual([t["type"] for t in info["types"] if not t["plugin"]],
                         ["template", "group", "wrapper", "apiInput", "apiResponse"])
        json.dumps(info)  # JSON-able as is

    def test_editor_view(self):
        nodes = graph(node("t", "text", value="hi"), node("f", "format", content="{a} <n>"), node("s", "sink"),
                      node("g", "gate", matchValue="hi", lastPass=True))
        edges = [edge("e1", "t", "out", "f", "string:a"), edge("e2", "f", "out", "s", "in"), edge("e3", "t", "out", "g", "compare")]
        view = common.editor_view(nodes, edges, running=False)
        json.dumps(view)
        self.assertEqual([p["id"] for p in view["nodes"]["f"]["inputs"]], ["string:a", "number:n"])
        self.assertEqual(view["nodes"]["s"]["body"], [{"kind": "value", "text": "hi 0"}])
        self.assertTrue(view["nodes"]["g"]["passed"])
        self.assertEqual(view["nodes"]["g"]["body"][2]["items"][0]["label"], "Text (t): hi")
        self.assertEqual(view["nodes"]["t"]["fields"][0]["key"], "value")
        self.assertIn("f:string:a:in", view["connected"])
        self.assertEqual(view["issues"], [])

    def test_editor_view_survives_malformed_nodes(self):
        view = common.editor_view({"x": {"id": "x", "type": "text"}}, [])
        self.assertTrue(view["issues"])


class NodeTypeLoaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (common.NODE_PLUGIN_DIR, common._node_types)

    def tearDown(self):
        common.NODE_PLUGIN_DIR, common._node_types = self._orig
        common.node_types()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def load(self, files):
        for name, text in files.items():
            (self.tmp / name).write_text(text, encoding="utf-8")
        common.NODE_PLUGIN_DIR = self.tmp
        common._node_types = None
        return common.node_types()

    def test_dropping_a_file_adds_a_type(self):
        types = self.load({
            "20_double.py": "from common import make_port\nTYPE = 'double'\nINPUTS = [make_port('in', 'x', 'number')]\n"
                            "OUTPUTS = [make_port('out', '2x', 'number')]\nRAN_PASSED = True\n"
                            "def evaluate(node, io):\n    from common import to_number\n    return {'out': 2 * to_number(io.input('in'))}\n",
            "10_first.py": "TYPE = 'first'\n",
            "_ignored.py": "TYPE = 'ignored'\n",
        })
        self.assertEqual(list(types)[:2], ["first", "double"])
        self.assertNotIn("ignored", types)
        nodes = graph(node("n", "number", value="4"), node("d", "double"))
        # Only the temp folder's types exist now — so "number" is an unknown type here.
        self.assertEqual(common.evaluate_all(nodes, [edge("e", "n", "out", "d", "in")])["values"]["d"]["out"], 0)
        self.assertEqual(common.reset_patch_for_node(node("d", "double")), {"__ranPassed": common.UNDEFINED})

    def test_the_template_file_works_as_a_node_type(self):
        files = {p.name: p.read_text(encoding="utf-8") for p in self._orig[0].glob("[!_]*.py")}
        files["50_upper.py"] = (self._orig[0] / "_template.py").read_text(encoding="utf-8")
        types = self.load(files)
        self.assertEqual(list(types)[-6:], ["upper", "template", "group", "wrapper", "apiInput", "apiResponse"])
        nodes = graph(node("t", "text", value="Hi"), node("u", "upper", mode="upper"), node("l", "upper", mode="lower"))
        edges = [edge("e1", "t", "out", "u", "in"), edge("e2", "t", "out", "l", "in")]
        view = common.editor_view(nodes, edges)
        self.assertEqual((view["nodes"]["u"]["body"][1]["text"], view["nodes"]["l"]["body"][1]["text"]), ("HI", "hi"))
        self.assertEqual(view["nodes"]["u"]["fields"][0]["key"], "mode")
        self.assertEqual(view["issues"], [])
        self.assertEqual(common.node_types_info()["errors"], [])

    def test_a_raising_type_file_shows_as_an_error_not_a_failed_view(self):
        types = self.load({"1_bad_hooks.py": "TYPE = 'bad'\ndef check(node, chk):\n    raise RuntimeError('check boom')\n"
                                             "def body(node, view):\n    raise RuntimeError('body boom')\n"})
        self.assertIn("bad", types)
        view = common.editor_view({"b": node("b", "bad")}, [])
        self.assertEqual(view["issues"][0]["message"], "Pre-run check failed: check boom")
        self.assertEqual(view["nodes"]["b"]["body"], [{"kind": "error", "text": "body boom"}])

    def test_broken_or_duplicate_files_are_reported_not_fatal(self):
        types = self.load({"1_bad.py": "raise RuntimeError('boom')\n", "2_dup.py": "TYPE = 'group'\n", "3_none.py": "X = 1\n"})
        self.assertEqual(set(types), {"template", "group", "wrapper", "apiInput", "apiResponse"})
        errors = common.node_types_info()["errors"]
        self.assertEqual([e.split(":")[0] for e in errors], ["1_bad.py", "2_dup.py", "3_none.py"])


class RunHelpersTest(unittest.TestCase):
    def test_shuffle_placeholder(self):
        text = "{{  - a|  - {who}|  - c}} {who} <n>"
        self.assertEqual([p["key"] for p in common.extract_placeholders(text)], ["string:who", "number:n"])
        filled = common.fill_placeholders(text, {"string:who": "b", "number:n": "1"})
        self.assertEqual(filled, "{{  - a|  - b|  - c}} b 1")
        outs = {common.resolve_shuffle("{{  - a|  - b|  - c}}") for _ in range(50)}
        self.assertGreater(len(outs), 1)
        for s in outs:
            self.assertEqual(sorted(s.split("\n")), ["  - a", "  - b", "  - c"])
        self.assertEqual(common.resolve_shuffle("{{x}} {a|b"), "{{x}} {a|b")

    def test_resolve_wired_input(self):
        edges = [edge("e1", "a", "out", "r", "signal")]
        self.assertEqual(common.resolve_wired_input(edges, {"values": {"a": {"out": 0}}}, "r", "signal"), 0)
        self.assertIs(common.resolve_wired_input(edges, {"values": {"a": {"out": 0}}}, "r", "other"), common.UNDEFINED)

    def test_fan_in_source_key(self):
        self.assertEqual(QUEUE.fan_in_source_key(edge("e", "g", "value_out@n7", "q", "in0")), "n7")
        self.assertEqual(QUEUE.fan_in_source_key(edge("e", "q1", "out0", "q", "in0")), "q1")

    def run_queue(self, q, edges, passes):
        state, enqueued = None, []
        for values in passes:
            step = QUEUE.step_queue_latch(q, edges, {"values": values}, state)
            input_set = step.pop("inputSet")
            state = step
            if input_set:
                enqueued.append(input_set)
        return enqueued

    def test_queue_fixed_ports_enqueue_once_all_present(self):
        q = node("q", "que", inputCount=2)
        edges = [edge("e1", "a", "out", "q", "in0"), edge("e2", "b", "out", "q", "in1")]
        enq = self.run_queue(q, edges, [
            {"a": {"out": "x"}, "b": {"out": common.UNDEFINED}},
            {"a": {"out": "x"}, "b": {"out": 0}},  # 0 is a real value
            {"a": {"out": "x"}, "b": {"out": 0}},
            {"a": {"out": "y"}, "b": {"out": 0}},
        ])
        self.assertEqual(enq, [["x", 0], ["y", 0]])

    def test_queue_fanned_ports_take_turns_without_mixing_sources(self):
        q = node("q", "que", inputCount=2)
        edges = [edge("e1", "A", "out0", "q", "in0"), edge("e2", "A", "out1", "q", "in1"),
                 edge("e3", "B", "out0", "q", "in0"), edge("e4", "B", "out1", "q", "in1")]
        both = {"A": {"out0": "A", "out1": "a1"}, "B": {"out0": "B", "out1": "b1"}}
        fresh = {"A": {"out0": "A", "out1": "a2"}, "B": {"out0": "B", "out1": "b2"}}
        enq = self.run_queue(q, edges, [{"A": {"out0": "A", "out1": "a1"}, "B": {"out0": "B", "out1": common.UNDEFINED}},
                                        both, both, fresh, fresh, fresh])
        self.assertEqual(enq, [["A", "a1"], ["B", "b1"], ["A", "a2"], ["B", "b2"]])

    def test_queue_fan_in_from_per_wire_gate(self):
        q = node("q", "que", inputCount=1)
        edges = [edge("vo~" + m, "g", "value_out@" + m, "q", "in0") for m in ("m1", "m2", "m3")]
        vals = {"g": {"value_out@m1": "p1", "value_out@m2": "p2", "value_out@m3": "p3"}}
        self.assertEqual(self.run_queue(q, edges, [vals] * 4), [["p1"], ["p2"], ["p3"]])

    def test_levels_release_a_cycle(self):
        nodes = {i: node(i, "number") for i in ("a", "b", "c")}
        levels = common.node_levels_in_dependency_order(nodes, [edge("e1", "a", "out", "b", "x"), edge("e2", "b", "out", "a", "x")])
        self.assertEqual(levels, [["c"], ["a", "b"]])

    def test_short_value(self):
        self.assertEqual(common.short_value("abc"), "abc")
        self.assertEqual(common.short_value({"a": 1}), '{"a":1}')
        self.assertEqual(common.short_value("x" * 100, 10), "xxxxxxxxx…")


class JsSemanticsTest(unittest.TestCase):
    def test_number_to_string(self):
        cases = {1.0: "1", -0.0: "0", 0.1 + 0.2: "0.30000000000000004", 1e21: "1e+21", 1e-7: "1e-7", 1e-6: "0.000001",
                 123.456: "123.456", 1.5e300: "1.5e+300", math.nan: "NaN", -math.inf: "-Infinity", 2 ** 60: "1152921504606846976"}
        for n, want in cases.items():
            self.assertEqual(common.js_number_str(n), want, n)

    def test_json_stringify_non_finite(self):
        self.assertEqual(common.js_json_stringify([math.nan, math.inf]), "[null,null]")

    def test_undefined_is_not_null(self):
        nodes = {"m": node("m", "template", content="{a}", values={"string:a": None}, outputs=[], outputValues={})}
        res = common.evaluate_all(nodes, [])
        self.assertIsNone(res["paramValues"]["m"]["string:a"])

    def test_undefined_survives_copies(self):
        import copy
        self.assertIs(copy.deepcopy({"a": common.UNDEFINED})["a"], common.UNDEFINED)


if __name__ == "__main__":
    unittest.main()
