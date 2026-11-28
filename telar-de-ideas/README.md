# Telar de Ideas

A no-build node/workflow editor built with React, MUI and React Flow, backed by a FastAPI server.
There is no bundler and no `npm install`: open `index.html` directly in the browser.

Place nodes on the canvas, wire them, and run them. An AI Node sends its filled
prompt to Codex and passes the structured output on to the next nodes.
A saved workflow can also be run as an API.

## Requirements

- A modern browser
- Python 3.10+
- `fastapi`, `uvicorn`, `pydantic` and `openai-codex`, with `codex login` done once

```
pip install fastapi uvicorn pydantic openai-codex
```

## Usage

1. Start the API server in this folder:

   ```
   $env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --reload --host 127.0.0.1 --port 9014
   ```

2. Open `index.html` in the browser.
3. Add nodes from the menu, wire them, and run the workflow.

If you change the port, keep `--port`, `api_port` in `config.json` and `CODEX_API_BASE` in `data.js` the same.

### Codex model

`codex_model` / `codex_reasoning_effort` in `config.json` apply to every AI Node job.
Set them to `null` to fall back to `~/.codex/config.toml`.

### Generate Workflow

Menu > Workflow > "+ Generate Workflow": describe what the workflow should do, and Codex builds it
from the Plugin Nodes, Group, Wrapper and saved AI Nodes (Structured Output; API Input/Response are not used).
The server checks the answer with the pre-run check and sends problems back to Codex, up to 3 tries in all.
The result opens on the canvas, not saved and not run; save it with "+ Save Workflow".
Codex runs with a read-only sandbox here, so generating never changes files.

### Adding node types

Each `.py` file in `node_plugin/` is one node type. See [node_plugin/README.md](node_plugin/README.md).

## API

| Method | Path | Response |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| GET | `/who` | `{"name": "telar-de-ideas", "path": "<server folder>"}` |
| GET, POST, PUT, DELETE | `/nodes`, `/workflows` | Saved AI Nodes / workflows (list, one, create, update, delete) |
| GET | `/node-types` | Node type list |
| POST | `/evaluate` | Canvas live view |
| POST, GET | `/codex/jobs` | Codex jobs (start, poll, `.../stop`) |
| POST | `/workflows/generate` | `{"job_id"}`. Poll `GET /codex/jobs/{id}`; output = `{workflow, summary, issues, attempts}` |
| POST, GET | `/runs`, `/workflows/{id}/runs` | Server-side workflow runs (start, poll, `.../stop`) |
| GET | `/api/{name}` | Runs a saved workflow by name and returns its API Response body. Query = API Input params; every fetch starts a run |
| GET | `/api/{name}/spec` | The workflow's parameters and fields (same as `GET /workflows/{id}/api`) |

## Project structure

```
index.html      UI
data.js         UI constants
common.js       UI helper functions
api_server.py   API routes
common.py       Server logic (Codex jobs, graph evaluation, node types, workflow runs)
data.py         Server constants
config.json     Settings read by both the server and the UI (port, poll interval, Codex model)
node_plugin/    Plugin node types, one .py file per type
node_ai/        Saved AI Nodes (JSON, one file each)
workflows/      Saved workflows (JSON, one file each)
lib/            React, ReactDOM, MUI, React Flow, Babel and others (bundled, no CDN)
tests/          Tests
```

## Tech stack

- [React](https://react.dev/), [MUI](https://mui.com/) and [React Flow](https://reactflow.dev/), loaded from `lib/` via `<script>` tags
- [Babel Standalone](https://babeljs.io/docs/babel-standalone) for in-browser JSX
- [FastAPI](https://fastapi.tiangolo.com/) and [Uvicorn](https://www.uvicorn.org/)
- [Codex](https://github.com/openai/codex) via the `openai-codex` SDK
