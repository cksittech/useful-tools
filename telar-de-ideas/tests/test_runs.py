# tests/test_runs.py
# Server-side runs over HTTP (POST /runs, /workflows/{id}/runs, GET/stop
# /runs/{id}) with Codex faked at common.run_codex_job and workflows/
# redirected to a temp dir. TestClient is used as a context manager so one
# event loop outlives each request — runs are tasks on it.
# Run from the project root: python -m unittest discover -s tests -p "test_*.py"
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import api_server  # noqa: E402
import common  # noqa: E402

OUT = [{"key": "out_r", "name": "result", "valueType": "string", "enumValues": [], "description": "", "children": []}]


def node(id, type, **data):
    return {"id": id, "type": type, "x": 0, "y": 0, "data": data}


def edge(id, frm, frm_port, to, to_port):
    return {"id": id, "from": {"node": frm, "port": frm_port}, "to": {"node": to, "port": to_port}}


def text_to_template_to_output(prompt="summarize {text}"):
    nodes = {"x": node("x", "text", value="hello"),
             "t": node("t", "template", content=prompt, outputs=OUT, outputValues={}, values={}),
             "s": node("s", "sink")}
    return nodes, [edge("e1", "x", "out", "t", "string:text"), edge("e2", "t", "out_r", "s", "in")]


# Thread target standing in for common.run_codex_job. hang=True: runs until stopped.
def fake_codex_job(hang=False):
    def run(job_id, prompt, output_schema):
        with common.codex_jobs_lock:
            common.codex_jobs[job_id].update(status="running", thread_id="th-" + job_id[:4])
        while hang:
            with common.codex_jobs_lock:
                if common.codex_jobs[job_id]["stop_requested"]:
                    common.codex_jobs[job_id].update(status="stopped", error="Stopped.")
                    return
            time.sleep(0.01)
        with common.codex_jobs_lock:
            common.codex_jobs[job_id].update(status="done", response="{}", output={"result": "ok:" + prompt})
    return run


class RunsApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (common.run_codex_job, common.WORKFLOWS_DIR, common.RUN_POLL_INTERVAL_MS, common.RUNS_KEPT_MAX)
        common.run_codex_job = fake_codex_job()
        common.WORKFLOWS_DIR = self.tmp / "workflows"
        common.RUN_POLL_INTERVAL_MS = 10
        common.runs_by_id.clear()
        self.client = TestClient(api_server.app).__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        common.run_codex_job, common.WORKFLOWS_DIR, common.RUN_POLL_INTERVAL_MS, common.RUNS_KEPT_MAX = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def wait_done(self, run_id, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            snap = self.client.get(f"/runs/{run_id}").json()
            if snap["status"] != "running":
                return snap
            time.sleep(0.02)
        self.fail(f"run {run_id} still running")

    def test_run_graph_to_completion(self):
        nodes, edges = text_to_template_to_output()
        started = self.client.post("/runs", json={"nodes": nodes, "edges": edges, "name": "adhoc"}).json()
        self.assertEqual(started["status"], "running")
        self.assertTrue(started["workflow_running"])  # even before the run task got its first turn
        snap = self.wait_done(started["id"])
        self.assertEqual(snap["status"], "finished")
        self.assertFalse(snap["workflow_running"])
        self.assertEqual(snap["outputs"], {"s": {"title": "Output", "value": "ok:summarize hello"}})
        self.assertEqual(snap["nodes"]["t"]["data"]["runStatus"], "done")
        self.assertEqual(snap["nodes"]["t"]["data"]["lastRequest"]["prompt"], "summarize hello")
        self.assertTrue(any(l["message"].startswith("run finished") for l in snap["logs"]))
        last_seq = snap["logs"][-1]["seq"]
        self.assertEqual(self.client.get(f"/runs/{started['id']}?since={last_seq}").json()["logs"], [])
        self.assertEqual(self.client.get("/runs").json()["runs"][0]["id"], started["id"])

    def test_run_saved_workflow_uses_saved_snapshot(self):
        nodes, edges = text_to_template_to_output("saved prompt {text}")
        wf = self.client.post("/workflows", json={"name": "WF", "nodes": nodes, "edges": edges}).json()
        started = self.client.post(f"/workflows/{wf['id']}/runs").json()
        snap = self.wait_done(started["id"])
        self.assertEqual((snap["status"], snap["workflow_id"], snap["name"]), ("finished", wf["id"], "WF"))
        self.assertEqual(snap["outputs"]["s"]["value"], "ok:saved prompt hello")
        self.assertEqual(self.client.post("/workflows/nope/runs").status_code, 404)

    def test_pre_run_errors_block(self):
        nodes = {"t": node("t", "template", content="  ", outputs=OUT)}
        snap = self.wait_done(self.client.post("/runs", json={"nodes": nodes, "edges": []}).json()["id"])
        self.assertEqual(snap["status"], "blocked")
        self.assertTrue(any("pre-run error" in l["message"] for l in snap["logs"]))

    def test_stop_mid_job(self):
        common.run_codex_job = fake_codex_job(hang=True)
        nodes, edges = text_to_template_to_output()
        run_id = self.client.post("/runs", json={"nodes": nodes, "edges": edges}).json()["id"]
        deadline = time.time() + 5
        while self.client.get(f"/runs/{run_id}").json()["nodes"]["t"]["data"].get("runStatus") != "running":
            self.assertLess(time.time(), deadline)
            time.sleep(0.02)
        self.assertEqual(self.client.post(f"/runs/{run_id}/stop").json(), {"ok": True})
        snap = self.wait_done(run_id)
        self.assertEqual(snap["status"], "stopped")
        self.assertEqual(snap["nodes"]["t"]["data"]["runStatus"], "stopped")
        job_id = snap["nodes"]["t"]["data"]["jobId"]
        deadline = time.time() + 5
        while self.client.get(f"/codex/jobs/{job_id}").json()["status"] != "stopped":
            self.assertLess(time.time(), deadline)
            time.sleep(0.02)
        self.assertEqual(self.client.post(f"/runs/{run_id}/stop").status_code, 200)  # already ended: no-op

    def test_move_node_moves_folder_in_process(self):
        (self.tmp / "src").mkdir()
        (self.tmp / "src" / "f.txt").write_text("x")
        nodes = {"a": node("a", "text", value=str(self.tmp / "src")), "b": node("b", "text", value=str(self.tmp / "dst")),
                 "m": node("m", "move")}
        edges = [edge("e1", "a", "out", "m", "src"), edge("e2", "b", "out", "m", "dst")]
        snap = self.wait_done(self.client.post("/runs", json={"nodes": nodes, "edges": edges}).json()["id"])
        self.assertEqual(snap["nodes"]["m"]["data"]["moveStatus"], "done")
        self.assertTrue((self.tmp / "dst" / "f.txt").exists())

    def test_retry_runs_only_that_node(self):
        nodes, edges = text_to_template_to_output()
        nodes["t2"] = node("t2", "template", content="other", outputs=OUT, outputValues={})
        started = self.client.post("/runs", json={"nodes": nodes, "edges": edges, "retry_node_id": "t"}).json()
        self.assertFalse(started["workflow_running"])
        snap = self.wait_done(started["id"])
        self.assertEqual(snap["status"], "finished")
        self.assertEqual(snap["nodes"]["t"]["data"]["runStatus"], "done")
        self.assertNotIn("runStatus", snap["nodes"]["t2"]["data"])
        self.assertFalse(any(l["message"] == "run started" for l in snap["logs"]))

    def test_failed_move_is_flagged_as_toast(self):
        nodes = {"a": node("a", "text", value=str(self.tmp / "missing")), "b": node("b", "text", value=str(self.tmp / "dst")),
                 "m": node("m", "move")}
        edges = [edge("e1", "a", "out", "m", "src"), edge("e2", "b", "out", "m", "dst")]
        snap = self.wait_done(self.client.post("/runs", json={"nodes": nodes, "edges": edges}).json()["id"])
        self.assertEqual(snap["nodes"]["m"]["data"]["moveStatus"], "error")
        toasts = [l for l in snap["logs"] if l.get("notify")]
        self.assertEqual(len(toasts), 1)
        self.assertTrue(toasts[0]["message"].startswith("Failed to move folder: Source folder not found"))

    def test_run_state_is_exposed(self):
        nodes = {"x": node("x", "text", value="go"), "q": node("q", "que", queue=[], inputCount=1)}
        snap = self.wait_done(self.client.post("/runs", json={"nodes": nodes, "edges": [edge("e1", "x", "out", "q", "in0")]}).json()["id"])
        self.assertEqual(snap["run_state"]["q"]["latch"]["portLatch"], {"in0": "go"})
        self.assertEqual(snap["run_state"]["q"]["delivered"], ["go"])

    def test_delay_keeps_run_open_until_relayed(self):
        nodes = {"x": node("x", "text", value="go"), "q": node("q", "que", queue=[], inputCount=1),
                 "d": node("d", "delay", seconds=0.2), "st": node("st", "stack", values=["a", "b"])}
        edges = [edge("e1", "x", "out", "q", "in0"), edge("e2", "q", "signal", "d", "in"), edge("e3", "d", "out", "st", "pop")]
        run_id = self.client.post("/runs", json={"nodes": nodes, "edges": edges}).json()["id"]
        time.sleep(0.1)
        self.assertEqual(self.client.get(f"/runs/{run_id}").json()["status"], "running")
        snap = self.wait_done(run_id)
        self.assertEqual(snap["status"], "finished")
        self.assertEqual(snap["nodes"]["st"]["data"]["__stack"], ["b"])

    def test_only_the_newest_finished_runs_are_kept(self):
        common.RUNS_KEPT_MAX = 2
        nodes, edges = text_to_template_to_output()
        ids = [self.wait_done(self.client.post("/runs", json={"nodes": nodes, "edges": edges}).json()["id"])["id"] for _ in range(3)]
        self.assertEqual(self.client.get(f"/runs/{ids[0]}").status_code, 404)
        self.assertEqual([r["id"] for r in self.client.get("/runs").json()["runs"]], ids[:0:-1])

    # Parameters topic (Text, test value "dogs") and n (Number, test value "2") feed a
    # AI Node; the API Response returns its result plus the raw topic.
    def save_api_workflow(self):
        params = [{"name": "topic", "valueType": "string", "value": "dogs"}, {"name": "n", "valueType": "number", "value": "2"}]
        nodes = {"i": node("i", "apiInput", params=params),
                 "t": node("t", "template", content="about {topic} x<n>", outputs=OUT, outputValues={}, values={}),
                 "r": node("r", "apiResponse", fields=["summary", "echo", "unwired"])}
        edges = [edge("e1", "i", "param:topic", "t", "string:topic"), edge("e2", "i", "param:n", "t", "number:n"),
                 edge("e3", "t", "out_r", "r", "field:summary"), edge("e4", "i", "param:topic", "r", "field:echo")]
        return self.client.post("/workflows", json={"name": "API", "nodes": nodes, "edges": edges}).json()["id"]

    def test_api_contract(self):
        wf = self.save_api_workflow()
        api = self.client.get(f"/workflows/{wf}/api").json()
        self.assertEqual(api["inputs"], [{"name": "topic", "type": "string", "default": "dogs"},
                                         {"name": "n", "type": "number", "default": "2"}])
        self.assertEqual((api["response"], api["errors"]), (["summary", "echo", "unwired"], []))

    def test_api_run_with_query_parameters_and_wait(self):
        wf = self.save_api_workflow()
        snap = self.client.post(f"/workflows/{wf}/runs", params={"topic": "café", "n": "3", "wait": "5"}).json()
        self.assertEqual(snap["status"], "finished")
        self.assertEqual(snap["response"], {"summary": "ok:about café x3", "echo": "café", "unwired": None})
        self.assertIs(snap["nodes"]["r"]["data"]["__ranPassed"], False)  # "unwired" never got a value
        self.assertIs(snap["nodes"]["i"]["data"]["__ranPassed"], True)
        self.assertEqual([p["value"] for p in snap["nodes"]["i"]["data"]["params"]], ["café", 3])  # Number parsed
        snap = self.client.post(f"/workflows/{wf}/runs", params={"topic": "owls", "n": "2.5", "wait": "5"}).json()
        self.assertEqual(snap["response"]["summary"], "ok:about owls x2.5")

    def test_api_by_workflow_name(self):
        wf = self.save_api_workflow()
        self.assertEqual(self.client.get("/api/API/spec").json()["id"], wf)
        snap = self.client.get("/api/API", params={"topic": "naïve", "n": "1", "wait": "5"}).json()
        self.assertEqual((snap["workflow_id"], snap["response"]["summary"]), (wf, "ok:about naïve x1"))
        self.assertEqual(self.client.get("/api/API").status_code, 400)  # parameters still required
        self.assertEqual(self.client.post("/api/API", params={"topic": "naïve", "n": "1"}).status_code, 405)  # GET only
        for path in ("/api/nope", "/api/nope/spec"):
            r = self.client.get(path)
            self.assertEqual((r.status_code, r.json()["detail"]), (404, 'No workflow is named "nope".'))
        nodes, edges = text_to_template_to_output()
        self.client.post("/workflows", json={"name": "Résumé v2", "nodes": nodes, "edges": edges})
        snap = self.client.get("/api/Résumé v2", params={"wait": "5"}).json()  # non-ASCII / space, URL-encoded
        self.assertEqual(snap["status"], "finished")
        self.client.post("/workflows", json={"name": "API", "nodes": nodes, "edges": edges})
        self.assertEqual(self.client.get("/api/API", params={"topic": "x", "n": "1"}).status_code, 409)
        self.assertEqual(self.client.get("/api/API/spec").status_code, 409)

    def test_api_parameter_errors_are_400(self):
        wf = self.save_api_workflow()
        cases = [({}, "Missing parameter(s): topic, n."),
                 ({"topic": "a"}, "Missing parameter(s): n."),
                 ({"topic": "a", "n": "1", "zzz": "1"}, "Unknown parameter(s): zzz. This workflow takes: topic, n."),
                 ({"topic": "a", "n": "3x"}, 'Parameter "n" must be a number.'),
                 ({"topic": "a", "n": "inf"}, 'Parameter "n" must be a number.')]
        for params, detail in cases:
            r = self.client.post(f"/workflows/{wf}/runs", params=params)
            self.assertEqual((r.status_code, r.json()["detail"]), (400, detail), params)
        self.assertEqual(self.client.get("/runs").json()["runs"], [])  # nothing started

    def test_run_without_api_nodes_has_no_response(self):
        nodes, edges = text_to_template_to_output()
        wf = self.client.post("/workflows", json={"name": "Plain", "nodes": nodes, "edges": edges}).json()["id"]
        snap = self.client.post(f"/workflows/{wf}/runs?wait=5").json()
        self.assertEqual((snap["status"], snap["response"]), ("finished", None))

    def test_unknown_run_is_404(self):
        self.assertEqual(self.client.get("/runs/nope").status_code, 404)
        self.assertEqual(self.client.post("/runs/nope/stop").status_code, 404)


class MoveFolderSharedTest(unittest.TestCase):
    def test_errors_map_to_status(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            with self.assertRaises(common.MoveError) as ctx:
                common.move_folder_checked(str(tmp / "missing"), str(tmp / "d"))
            self.assertEqual(ctx.exception.status_code, 404)
            (tmp / "s").mkdir()
            with self.assertRaises(common.MoveError) as ctx:
                common.move_folder_checked(str(tmp / "s"), str(tmp / "s" / "inner"))
            self.assertEqual(ctx.exception.status_code, 400)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
