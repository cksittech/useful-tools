# Forja CIS-Ansible

"Forja" is Spanish for "forge": this app forges Ansible tasks from CIS Benchmarks.

A no-build MUI app: open index.html directly in the browser.
Pick a CIS Benchmark PDF from the documents/ folder, browse its recommendations
(e.g. 1.1.1.5) grouped by section, and view a selected one split into the
fields defined in "Recommendation Definitions" (Profile Applicability, Description,
Rationale, Impact, Audit, Remediation, Default Value, References, CIS Controls,
Additional Information).

## CIS Benchmark PDFs (bring your own)

No PDFs are included: CIS does not allow hosting its Benchmarks outside CIS in any format.
Download the ones you need from https://www.cisecurity.org/cis-benchmarks and put them in
documents/. They are licensed under CC BY-NC-SA 4.0 (non-commercial use only).
snapshot/ and generated.json are built from them, so they start empty as well.

## Overview

Requires `pdftotext` (poppler). Git for Windows ships it at
`C:\Program Files\Git\mingw64\bin\pdftotext.exe`, which is used when it is not on PATH.
The detail pane has two tabs: Details (the PDF fields) and Ansible. The Ansible tab's
"Generate" button asks Codex (openai_codex SDK) for three task lists, each shown in its own box
with a Copy button: remediation (apply), verification (audit) and rollback (undo).
Codex runs read-only with approvals denied.
Generation takes about a minute; results are saved to generated.json and shown again later.
Model / effort / prompt are in data.py (CODEX_MODEL, CODEX_REASONING_EFFORT, ANSIBLE_PROMPT).

Each PDF is parsed once on first use and cached in memory (RHEL 9: about 3 s).

Without the API server: the page checks GET /health every 5 s. While it fails, PDFs and
saved Ansible results are read from snapshot/ instead (only Generate is disabled, with a
note next to the button). The server keeps snapshot/ up to date: at start it rebuilds stale
files in the background (21 PDFs: about 30 s), and after each generation it rewrites
that PDF's file. The snapshot files are .js data (loaded with <script>, which works from
file://), not code.

## Files

    index.html      UI (React components and state live only here)
    data.js         UI constants (API_BASE, etc.). No functions
    common.js       UI functions (api(), etc.). No React, DOM, or state
    api_server.py   API entry point (route definitions only)
    common.py       Server logic
    data.py         Server constants and request models. No functions
    documents/      CIS Benchmark PDFs (input; not included, see above)
    lib/            External libraries (react / react-dom / material-ui / babel)
    generated.json  Saved data: generated Ansible tasks, keyed by "<pdf>::<number>"
    snapshot/       Saved data: parsed PDFs + generated.json per PDF, for viewing without the API server
    README.md       This file

## Start

    $env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --reload --host 127.0.0.1 --port 9032

Then open index.html directly in the browser.

## API

| Path | Returns | Notes |
|---|---|---|
| GET /health | {"status": "ok"} | Common. Every app has it |
| GET /who | {"name", "path"} | Common. Shows which app is using the port |
| GET /api/pdfs | {"pdfs": [name]} | PDFs in documents/ |
| GET /api/items?pdf= | {"items": [{kind, number, title, status, page, level, intro?}]} | kind = section / recommendation. page = PDF page |
| GET /api/recommendation?pdf=&number= | {number, title, status, page, fields: [{key, label, text}]} | Fields in the defined order; missing ones are omitted |
| GET /api/ansible?pdf=&number= | {status, error, started_at, result?, generated_at?, model?} | status = none / running / done / error. result = {remediation_tasks, verification_tasks, rollback_tasks, notes} |
| POST /api/ansible | same as GET | Body {pdf, number}. Starts a Codex job in the background (no-op if one is running) |

## Three-file split

| Role | Server | UI |
|---|---|---|
| Entry point / UI | api_server.py | index.html |
| Logic / functions | common.py | common.js |
| Constants / types | data.py | data.js |

- Do not add new .py / .js files; put code in one of these three. A long common file is fine.
- Besides these, only lib/, tests/, saved data, and config.json belong in the folder.

## Dependency direction

    api_server.py -> common.py -> data.py
    index.html    -> common.js -> data.js

Never reference in the reverse direction.
- data.py / data.js: no functions, no references to other project files.
- common.py: do not import fastapi or api_server. Raise plain exceptions (ValueError, etc.);
  api_server converts them to HTTP status codes.
- common.js: do not touch React, the DOM, or state.
- When the server and UI share a value, write it in both data.py and data.js
  with a "keep in sync with ..." comment.
