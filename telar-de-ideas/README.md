# Telar de Ideas

Folder: telar-de-ideas (also the name GET /who returns).

A no-build node/workflow editor: open index.html directly in the browser.
Place nodes on the canvas, wire them, and run them. An AI Node sends its filled
prompt to Codex and passes the structured output on to the next nodes.
Built on the UtilToolApp template (..\..\template).

## Files

    index.html      UI in JSX, compiled in the browser by babel (React components and state live only here)
    data.js         UI constants (CODEX_API_BASE, colors, layout). No functions
    common.js       UI functions (placeholder parsing, api calls, RunClient). No React, DOM, or state
    api_server.py   API entry point (route definitions and request checks only)
    common.py       Server logic (Codex jobs, graph evaluation, node types, workflow runs)
    data.py         Server constants, placeholder patterns and request models. No functions
    config.json     Settings read by both the server and the UI (port, poll interval, Codex model)
    node_plugin/    Plugin node types, one .py file per type (see node_plugin/README.md)
    node_ai/        Saved AI Nodes (JSON, one file each)
    workflows/      Saved workflows (JSON, one file each)
    lib/            External libraries (react / react-dom / material-ui / reactflow / icons / babel)
    tests/          python -m unittest discover -s tests / node --test tests/*.test.js
    README.md       This file

## Start

    pip install fastapi uvicorn pydantic openai-codex
    $env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --reload --host 127.0.0.1 --port 9014

Then open index.html directly in the browser.
If you change the port, keep --port, config.json's api_port and data.js's CODEX_API_BASE the same.

## Codex model

config.json's codex_model / codex_reasoning_effort apply to every AI Node job.
Set them to null to fall back to ~/.codex/config.toml.

## Generate Workflow

Menu > Workflow > "+ Generate Workflow": describe what the workflow should do, and Codex builds it
from the Plugin Nodes, Group, Wrapper and saved AI Nodes (Structured Output; API Input/Response are not used).
The server checks the answer with the pre-run check and sends problems back to Codex, up to 3 tries in all.
The result opens on the canvas, not saved and not run; save it with "+ Save Workflow".
Codex runs with a read-only sandbox here, so generating never changes files.

## API

| Path | Returns | Notes |
|---|---|---|
| GET /health | {"status": "ok"} | Common. Every app has it |
| GET /who | {"name", "path"} | Common. Shows which app is using the port |
| /nodes, /workflows | saved AI Nodes / workflows | GET list, GET one, POST, PUT, DELETE |
| GET /node-types, POST /evaluate | node type list / canvas live view | What the editor draws |
| /codex/jobs | Codex jobs | POST start, GET poll, POST .../stop |
| POST /workflows/generate | {"job_id"} | Generate Workflow. Poll GET /codex/jobs/{id}; output = {workflow, summary, issues, attempts} |
| /runs, /workflows/{id}/runs | server-side workflow runs | POST start, GET poll, POST .../stop |
| GET /api/{name} | the run (its API Response body) | Runs a saved workflow by name; every fetch starts a run. Query = API Input params |
| GET /api/{name}/spec | the workflow's parameters and fields | Same as GET /workflows/{id}/api |

## Three-file split

| Role | Server | UI |
|---|---|---|
| Entry point / UI | api_server.py | index.html |
| Logic / functions | common.py | common.js |
| Constants / types | data.py | data.js |

- Do not add new .py / .js files; put code in one of these three. A long common file is fine
  (split it with `# --- Section ---` headings).
- The one exception is node_plugin/, so that a node type can be added by dropping in a file.
- Besides these, only lib/, tests/, saved data (node_ai/, workflows/) and config.json belong in the folder.

## Dependency direction

    api_server.py -> common.py -> data.py
    index.html    -> common.js -> data.js
    node_plugin/*.py -> common.py, data.py

Never reference in the reverse direction.
- data.py / data.js: no functions, no references to other project files.
- common.py: do not import fastapi or api_server. Raise plain exceptions (ValueError, etc.);
  api_server converts them to HTTP status codes.
- common.js: do not touch React, the DOM, or state.
- When the server and UI share a value, write it in both places with a "keep in sync with ..." comment.
