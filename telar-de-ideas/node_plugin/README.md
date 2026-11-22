# Adding a node type

Each `.py` file in this folder is one node type.
Drop a file here and restart api_server.py; a button for it appears under "Plugin Node" in the menu.

## Steps

1. Copy `_template.py` and save it as `NN_name.py` (e.g. `16_upper.py`).
   - The menu lists types in file-name order; the leading number sets the position.
   - Files whose names start with `_` are not loaded.
2. Change `TYPE` to a name no other type uses, then write the ports and logic.
3. Restart api_server.py.
   - If it was started with `--reload`, saving the file restarts it automatically.
   - A restart stops any running workflow, so save while nothing is running.
4. Reload the browser; the new node appears in the menu.

## What a file defines

Only `TYPE` is required. Write only what the type needs.

| Name | Purpose |
|---|---|
| `TYPE` | Type name stored in saved workflows. Never change it once used (saved workflows would no longer load). |
| `TITLE`, `INPUTS`, `OUTPUTS` | Display name and ports |
| `DEFAULT_DATA`, `BODY_HEIGHT` | Data and card height when the node is added |
| `evaluate(node, io)` | Output port values. Called on every edit, so no side effects (file operations etc.). |
| `FIELDS` | Edit panel shown when the node is selected |
| `body(node, view)` | What the card body shows |
| `check(node, chk)` | Pre-run checks (e.g. warnings for missing wires) |
| `fire` / `settle` | Behavior during a run (side effects go here) |

How to write each one and the available building blocks are described in the comments of `_template.py`.
The full list is under the "Node types" heading in common.py. Existing files (`01_number.py` etc.) are also good examples.

## Troubleshooting

- A file with an error is skipped, and the menu shows "Node type file failed to load — file name: reason" in red
  under the Plugin Node buttons. Other nodes and the server keep working.
- If two files use the same `TYPE`, the one loaded later fails with an error.

## Types not in this folder

- AI Node, Group and Wrapper rewire other nodes' edges and ports, so they live in the core of common.py.
- API Input and API Response are the entry and exit of running a workflow as an API
  (`POST /workflows/{id}/runs`), so they are in the core as well.
