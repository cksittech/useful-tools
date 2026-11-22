# tests/test_backend.py
# Backend regression tests (stdlib unittest + FastAPI TestClient; Codex is faked).
# Run from the project root: python -m unittest discover -s tests -p "test_*.py"
import shutil
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import api_server  # noqa: E402
import common  # noqa: E402


class FakeTurn:
    def __init__(self, on_create=None):
        self.interrupted = False
        if on_create:
            on_create()

    def interrupt(self):
        self.interrupted = True

    def run(self):
        status = "interrupted" if self.interrupted else "completed"
        return SimpleNamespace(status=SimpleNamespace(value=status), duration_ms=1, final_response='{"a": 1}', error=None)


class FakeCodex:
    on_turn: Callable[[], object] | None = None  # hook run while thread.turn() builds the handle
    last_turn: FakeTurn | None = None
    calls = []  # (method, kwargs) per thread_start / turn
    last_prompt: str | None = None

    def thread_start(self, **kwargs):
        FakeCodex.calls.append(("thread_start", kwargs))

        def turn(prompt, output_schema=None, **kwargs):
            FakeCodex.calls.append(("turn", kwargs))
            FakeCodex.last_prompt = prompt
            FakeCodex.last_turn = FakeTurn(FakeCodex.on_turn)
            return FakeCodex.last_turn
        return SimpleNamespace(id="thread-1", turn=turn)

    def thread_archive(self, thread_id):
        pass

    def close(self):
        pass


class RunOnceTest(unittest.TestCase):
    def test_concurrent_duplicates_run_once(self):
        calls = []

        def work():
            calls.append(1)
            time.sleep(0.1)
            return {"n": len(calls)}

        results = []
        threads = [threading.Thread(target=lambda: results.append(common.run_once("op-dup", work))) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(calls), 1)
        self.assertEqual(results, [{"n": 1}] * 5)

    def test_error_is_replayed(self):
        def boom():
            raise ValueError("first failure")

        with self.assertRaises(ValueError):
            common.run_once("op-err", boom)
        with self.assertRaisesRegex(ValueError, "first failure"):
            common.run_once("op-err", lambda: "never runs")

    def test_no_id_always_runs(self):
        calls = []
        common.run_once(None, lambda: calls.append(1))
        common.run_once("", lambda: calls.append(1))
        self.assertEqual(len(calls), 2)


class ApiDedupTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api_server.app)
        self._orig_runner = common.run_codex_job
        common.run_codex_job = lambda *a: None  # job threads do nothing

    def tearDown(self):
        common.run_codex_job = self._orig_runner

    def test_codex_job_resend_returns_same_job(self):
        body = {"prompt": "hi", "operation_id": "job-op-1"}
        first = self.client.post("/codex/jobs", json=body).json()
        second = self.client.post("/codex/jobs", json=body).json()
        self.assertEqual(first, second)
        third = self.client.post("/codex/jobs", json={"prompt": "hi"}).json()
        self.assertNotEqual(first["job_id"], third["job_id"])

    def test_move_resend_replays_success_instead_of_404(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "src").mkdir()
            (tmp / "src" / "f.txt").write_text("x")
            body = {"src": str(tmp / "src"), "dst": str(tmp / "dst"), "operation_id": "move-op-1"}
            r1 = self.client.post("/fs/move-folder", json=body)
            r2 = self.client.post("/fs/move-folder", json=body)
            self.assertEqual((r1.status_code, r2.status_code), (200, 200))
            self.assertEqual(r1.json(), r2.json())
            self.assertTrue((tmp / "dst" / "f.txt").exists())
            r3 = self.client.post("/fs/move-folder", json={**body, "operation_id": "move-op-2"})
            self.assertEqual(r3.status_code, 404)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_stop_unknown_job_is_404(self):
        self.assertEqual(self.client.post("/codex/jobs/nope/stop").status_code, 404)


class StopTest(unittest.TestCase):
    def setUp(self):
        self._orig_codex = common.Codex
        common.Codex = FakeCodex
        FakeCodex.on_turn = None

    def tearDown(self):
        common.Codex = self._orig_codex

    def _new_job(self, job_id):
        with common.codex_jobs_lock:
            common.codex_jobs[job_id] = common.new_job_state(job_id, "p", None, None)

    def test_stop_before_turn_never_starts_codex(self):
        self._new_job("j-early")
        common.Codex = lambda: self.fail("Codex must not start after a stop")
        self.assertTrue(common.request_stop("j-early"))
        common.run_codex_job("j-early", "p", None)
        self.assertEqual(common.codex_jobs["j-early"]["status"], "stopped")

    def test_stop_arriving_while_turn_is_created_still_interrupts(self):
        self._new_job("j-race")
        # Stop lands after thread.turn() started but before the handle is published.
        FakeCodex.on_turn = lambda: common.request_stop("j-race")
        common.run_codex_job("j-race", "p", None)
        assert FakeCodex.last_turn is not None
        self.assertTrue(FakeCodex.last_turn.interrupted)
        self.assertEqual(common.codex_jobs["j-race"]["status"], "stopped")

    def test_normal_run_completes(self):
        self._new_job("j-ok")
        common.run_codex_job("j-ok", "p", {"type": "object"})
        job = common.codex_jobs["j-ok"]
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["output"], {"a": 1})

    def test_shuffle_resolved_only_at_send(self):
        self._new_job("j-shuffle")
        common.run_codex_job("j-shuffle", "x\n{{a|b}}", None)
        self.assertIn(FakeCodex.last_prompt, ("x\na\nb", "x\nb\na"))
        self.assertEqual(common.codex_jobs["j-shuffle"]["prompt"], "p")  # job keeps what it was created with

    def test_model_and_effort_come_from_config(self):
        FakeCodex.calls = []
        self._new_job("j-model")
        common.run_codex_job("j-model", "p", None)
        self.assertEqual(FakeCodex.calls, [
            ("thread_start", {"model": common.CODEX_MODEL}),
            ("turn", {"model": common.CODEX_MODEL, "effort": common.CODEX_REASONING_EFFORT}),
        ])


class RecordCrudTest(unittest.TestCase):
    # node_ai/ and workflows/ point at a temp dir — real saved files are never touched.
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (common.NODE_AI_DIR, common.WORKFLOWS_DIR)
        common.NODE_AI_DIR = self.tmp / "node_ai"
        common.WORKFLOWS_DIR = self.tmp / "workflows"
        self.client = TestClient(api_server.app)

    def tearDown(self):
        common.NODE_AI_DIR, common.WORKFLOWS_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_node_crud(self):
        c = self.client
        self.assertEqual(c.post("/nodes", json={"name": " ", "content": "x"}).status_code, 400)
        a = c.post("/nodes", json={"name": "A", "content": " hi ", "outputs": [{"key": "o"}]}).json()
        b = c.post("/nodes", json={"name": "B", "content": "yo"}).json()
        self.assertEqual(a["content"], "hi")
        self.assertNotEqual(a["id"], b["id"])  # same-second save gets a "_N" suffix
        self.assertEqual([n["id"] for n in c.get("/nodes").json()["nodes"]], sorted([a["id"], b["id"]], reverse=True))
        self.assertEqual(c.put(f"/nodes/{a['id']}", json={"name": "A2", "content": "hi"}).json()["name"], "A2")
        self.assertEqual(c.put("/nodes/nope", json={"name": "A", "content": "x"}).status_code, 404)
        self.assertEqual(c.delete(f"/nodes/{a['id']}").json(), {"ok": True})
        self.assertEqual(c.delete(f"/nodes/{a['id']}").status_code, 404)
        self.assertEqual([n["id"] for n in c.get("/nodes").json()["nodes"]], [b["id"]])

    def test_workflow_crud(self):
        c = self.client
        self.assertEqual(c.post("/workflows", json={"name": ""}).status_code, 400)
        w = c.post("/workflows", json={"name": "W", "nodes": {"n1": {}}, "edges": []}).json()
        (common.WORKFLOWS_DIR / "broken.json").write_text("{", encoding="utf-8")  # skipped by the list
        self.assertEqual(c.get("/workflows").json()["workflows"], [{"id": w["id"], "name": "W", "node_count": 1}])
        self.assertEqual(c.get(f"/workflows/{w['id']}").json()["nodes"], {"n1": {}})
        self.assertEqual(c.get("/workflows/nope").status_code, 404)
        self.assertEqual(c.put(f"/workflows/{w['id']}", json={"name": "W2", "zoom": 2}).json()["zoom"], 2)
        self.assertEqual(c.delete(f"/workflows/{w['id']}").json(), {"ok": True})
        self.assertEqual(c.get(f"/workflows/{w['id']}").status_code, 404)


class EditorApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api_server.app)

    def test_node_types(self):
        body = self.client.get("/node-types").json()
        self.assertEqual(body["errors"], [])
        delay = next(t for t in body["types"] if t["type"] == "delay")
        self.assertEqual((delay["title"], delay["defaultData"], delay["reset"]), ("Delay", {"seconds": 3}, {"set": {"__seq": 0}, "unset": ["delayStatus"]}))

    def test_evaluate(self):
        nodes = {"n": {"id": "n", "type": "number", "x": 0, "y": 0, "data": {"value": "2"}},
                 "o": {"id": "o", "type": "output", "x": 0, "y": 0, "data": {}}}  # pre-rename type, migrated
        edges = [{"id": "e", "from": {"node": "n", "port": "out"}, "to": {"node": "o", "port": "in"}}]
        view = self.client.post("/evaluate", json={"nodes": nodes, "edges": edges}).json()
        self.assertEqual(view["nodes"]["o"]["body"], [{"kind": "value", "text": "2"}])
        self.assertEqual(view["nodes"]["o"]["title"], "Output")
        self.assertEqual(view["issues"], [])


if __name__ == "__main__":
    unittest.main()
