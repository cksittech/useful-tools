# api_server.py
# FastAPI app: route definitions and per-request handling logic.
#
# Backs the Telar de Ideas app's Created Nodes: builds a prompt from
# {str}/<num>/[select] placeholders + a JSON Schema from output ports, sends
# both to Codex, returns the parsed Structured Output.
#
# Also runs whole workflows server-side (/runs).
#
# Start: $env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --reload --host 127.0.0.1 --port 9014
import json
import subprocess
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

import common
from data import (
    API_WAIT_PARAM,
    RUN_WAIT_MAX_SEC,
    CodexJobRequest,
    EvaluateRequest,
    MoveFolderRequest,
    NodeSaveRequest,
    OpenPathRequest,
    RunRequest,
    WorkflowSaveRequest,
)

app = FastAPI()

# Only the GitHub Pages copy and index.html opened as file:// (Origin "null") may call this;
# any other site open in the browser could otherwise drive Codex / folder moves on this PC.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://cksittech.github.io", "null"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Saved records (Created Node definitions / workflows) --------------------
# Both are CRUD over a JSON record store (common.list_records etc.) — one file
# per record. Only the folder and the stored fields differ.


# Path of an existing record, else 404.
def _existing_record_path(folder: Path, record_id: str, label: str) -> Path:
    path = folder / f"{record_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{label} not found.")
    return path


def _node_data(req: NodeSaveRequest) -> dict:
    name = req.name.strip()
    content = req.content.strip()
    if not name or not content:
        raise HTTPException(status_code=400, detail="Name and content are required.")
    return {"name": name, "content": content, "outputs": req.outputs}


def _workflow_data(req: WorkflowSaveRequest) -> dict:
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    return {"name": name, "nodes": req.nodes, "edges": req.edges, "pan": req.pan, "zoom": req.zoom}


@app.get("/nodes")
def list_nodes():
    return {"nodes": [
        {"id": rid, "name": d.get("name", rid), "content": d.get("content", ""), "outputs": d.get("outputs", [])}
        for rid, d in common.list_records(common.NODE_AI_DIR)
    ]}


@app.post("/nodes")
def create_node(req: NodeSaveRequest):
    data = _node_data(req)
    path = common.new_record_path(common.NODE_AI_DIR)
    common.write_record(path, data)
    return {"id": path.stem, **data}


@app.put("/nodes/{node_id}")
def update_node(node_id: str, req: NodeSaveRequest):
    data = _node_data(req)
    common.write_record(_existing_record_path(common.NODE_AI_DIR, node_id, "Node"), data)
    return {"id": node_id, **data}


@app.delete("/nodes/{node_id}")
def delete_node(node_id: str):
    _existing_record_path(common.NODE_AI_DIR, node_id, "Node").unlink()
    return {"ok": True}


@app.get("/workflows")
def list_workflows():
    return {"workflows": [
        {"id": rid, "name": d.get("name", rid), "node_count": len(d.get("nodes", {}))}
        for rid, d in common.list_records(common.WORKFLOWS_DIR)
    ]}


@app.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    path = _existing_record_path(common.WORKFLOWS_DIR, workflow_id, "Workflow")
    return {"id": workflow_id, **json.loads(path.read_text(encoding="utf-8"))}


@app.post("/workflows")
def create_workflow(req: WorkflowSaveRequest):
    data = _workflow_data(req)
    path = common.new_record_path(common.WORKFLOWS_DIR)
    common.write_record(path, data)
    return {"id": path.stem, **data}


@app.put("/workflows/{workflow_id}")
def update_workflow(workflow_id: str, req: WorkflowSaveRequest):
    data = _workflow_data(req)
    common.write_record(_existing_record_path(common.WORKFLOWS_DIR, workflow_id, "Workflow"), data)
    return {"id": workflow_id, **data}


@app.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: str):
    _existing_record_path(common.WORKFLOWS_DIR, workflow_id, "Workflow").unlink()
    return {"ok": True}


# --- Editor view ---------------------------------------------------------------
# Node types come from node_plugin/ (common.py "Node types"); the editor draws
# every type-specific part from these two.


@app.get("/node-types")
def list_node_types():
    return common.node_types_info()


@app.post("/evaluate")
def evaluate(req: EvaluateRequest):
    return common.editor_view(common.migrate_loaded_nodes(req.nodes), req.edges, req.running, req.run_state)


# --- Codex job execution -----------------------------------------------------
# Job state and the background runner itself live in common.py; this just
# validates the request, seeds the job entry, and hands off to a thread.


@app.post("/codex/jobs")
def create_codex_job(req: CodexJobRequest):
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required.")

    # A resend with the same operation_id gets the first call's job_id back.
    return common.start_codex_job(prompt, req.output_schema, req.node_id, req.operation_id)


@app.get("/codex/jobs")
def list_codex_jobs():
    with common.codex_jobs_lock:
        jobs = list(common.codex_jobs.values())
    jobs.sort(key=lambda j: j["started_at"], reverse=True)

    result = []
    for job in jobs:
        pub = common.serializable_job(job)
        pub["elapsed_seconds"] = time.time() - pub.pop("started_at")
        result.append(pub)
    return {"jobs": result}


@app.get("/codex/jobs/{job_id}")
def get_codex_job(job_id: str):
    pub = common.public_job(job_id)
    if pub is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return pub


@app.post("/codex/jobs/{job_id}/stop")
def stop_codex_job(job_id: str):
    # Also valid while the job is still starting — run_codex_job honors the
    # flag before the turn begins (common.request_stop).
    if not common.request_stop(job_id):
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"ok": True}


# --- Open in File Explorer ------------------------------------------------
# Link node hands an OS path here instead of file:// <a href> (which would
# open in the browser, not Explorer).


@app.post("/open-path")
def open_path(req: OpenPathRequest):
    path = Path(req.path).expanduser()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    if path.is_dir():
        subprocess.Popen(["explorer", str(path)])
    else:
        # /select, and the path must be one argv item with no space between
        # them, or explorer ignores the flag and just opens a new window.
        subprocess.Popen(["explorer", f"/select,{path}"])
    return {"ok": True}


# --- Move / rename folder -------------------------------------------------
# Validation and the rename/merge itself live in common.move_folder_checked();
# this maps its MoveError to the HTTP status.


@app.post("/fs/move-folder")
def move_folder(req: MoveFolderRequest):
    # The whole handler (validation included) runs once per operation_id —
    # a resend after a successful move would otherwise 404 on the now-gone src.
    try:
        return common.run_once(req.operation_id, lambda: common.move_folder_checked(req.src, req.dst))
    except common.MoveError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# --- Server-side workflow runs -------------------------------------------
# State lives in common.runs_by_id; async routes, so they run on the runs' event loop.
# Progress: GET /runs/{id}?since=<last log seq seen>.


@app.post("/runs")
async def create_run(req: RunRequest):
    run = common.start_run(common.migrate_loaded_nodes(req.nodes), req.edges, name=req.name, retry_node_id=req.retry_node_id)
    return run.snapshot()


def _saved_graph(workflow_id: str) -> tuple[dict, dict, list]:
    saved = json.loads(_existing_record_path(common.WORKFLOWS_DIR, workflow_id, "Workflow").read_text(encoding="utf-8"))
    return saved, common.migrate_loaded_nodes(saved.get("nodes", {})), saved.get("edges", [])


# The one saved workflow with this name; 404 if none, 409 if several share it.
def _workflow_id_by_name(name: str) -> str:
    ids = common.workflow_ids_named(name)
    if not ids:
        raise HTTPException(status_code=404, detail=f'No workflow is named "{name}".')
    if len(ids) > 1:
        raise HTTPException(status_code=409, detail=f'{len(ids)} workflows are named "{name}" ({", ".join(ids)}) — rename or delete all but one.')
    return ids[0]


# Runs the workflow as saved (its stored Created Node snapshots, not nodes/). The
# other query parameters fill its API Input; wait=N answers when the run ends or after N seconds.
async def _run_saved(workflow_id: str, request: Request, wait: float):
    saved, nodes, edges = _saved_graph(workflow_id)
    query = {k: v for k, v in request.query_params.items() if k != API_WAIT_PARAM}
    try:
        nodes = common.apply_api_inputs(nodes, query)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    run = common.start_run(nodes, edges, workflow_id=workflow_id, name=saved.get("name"))
    await common.wait_for_run(run, min(max(wait, 0), RUN_WAIT_MAX_SEC))
    return run.snapshot()


# What a run of this workflow takes and returns, plus any pre-run errors that would block it.
def _api_spec(workflow_id: str) -> dict:
    _, nodes, edges = _saved_graph(workflow_id)
    errors = [i["message"] for i in common.validate_workflow(nodes, edges) if i["level"] == "error"]
    return {"id": workflow_id, **common.api_contract(nodes), "errors": errors}


@app.post("/workflows/{workflow_id}/runs")
async def run_saved_workflow(workflow_id: str, request: Request, wait: float = 0):
    return await _run_saved(workflow_id, request, wait)


@app.get("/workflows/{workflow_id}/api")
async def workflow_api(workflow_id: str):
    return _api_spec(workflow_id)


# Same as the two above, with the workflow given by its name. Running is a GET
# (user's choice) so a URL alone runs it — every fetch of the URL starts a run.
@app.get("/api/{name}")
async def run_workflow_by_name(name: str, request: Request, wait: float = 0):
    return await _run_saved(_workflow_id_by_name(name), request, wait)


@app.get("/api/{name}/spec")
async def workflow_api_by_name(name: str):
    return _api_spec(_workflow_id_by_name(name))


@app.get("/runs")
async def list_runs():
    return {"runs": common.list_runs()}


@app.get("/runs/{run_id}")
async def get_run(run_id: str, since: int = 0):
    snap = common.get_run_snapshot(run_id, since)
    if snap is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return snap


@app.post("/runs/{run_id}/stop")
async def stop_run(run_id: str):
    if not common.stop_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found.")
    return {"ok": True}


@app.post("/runs/{run_id}/nodes/{node_id}/stop")
async def stop_run_node(run_id: str, node_id: str):
    if not common.stop_run_node(run_id, node_id):
        raise HTTPException(status_code=404, detail="Run not found.")
    return {"ok": True}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/who")
def who():
    return {"name": "telar-de-ideas", "path": str(Path(__file__).parent.resolve())}
