# Forja CIS-Ansible

"Forja" is Spanish for "forge": this app forges Ansible tasks from CIS Benchmarks.

A no-build web app built with React and MUI, backed by a small FastAPI server.
There is no bundler and no `npm install`: open `index.html` directly in the browser.

Pick a CIS Benchmark PDF from the `documents/` folder, browse its recommendations
(e.g. 1.1.1.5) grouped by section, and view a selected one split into the
fields defined in "Recommendation Definitions" (Profile Applicability, Description,
Rationale, Impact, Audit, Remediation, Default Value, References, CIS Controls,
Additional Information).

The detail pane has two tabs: Details (the PDF fields) and Ansible. The Ansible tab's
"Generate" button asks Codex for three task lists, each shown in its own box
with a Copy button: remediation (apply), verification (audit) and rollback (undo).

## CIS Benchmark PDFs (bring your own)

No PDFs are included: CIS does not allow hosting its Benchmarks outside CIS in any format.
Download the ones you need from https://www.cisecurity.org/cis-benchmarks and put them in
`documents/`. They are licensed under CC BY-NC-SA 4.0 (non-commercial use only).
`snapshot/` and `generated.json` are built from them, so they start empty as well.

## Requirements

- A modern browser
- Python 3.10+
- `fastapi`, `uvicorn` and `openai-codex`, with `codex login` done once
- `pdftotext` (poppler). Git for Windows ships it at
  `C:\Program Files\Git\mingw64\bin\pdftotext.exe`, which is used when it is not on PATH.

```
pip install fastapi uvicorn openai-codex
```

## Usage

1. Put CIS Benchmark PDFs in `documents/`.
2. Start the API server in this folder:

   ```
   $env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --reload --host 127.0.0.1 --port 9032
   ```

3. Open `index.html` in the browser.
4. Pick a PDF and a recommendation. In the Ansible tab, click **Generate**.

Generation takes about a minute. Codex runs read-only with approvals denied.
Results are saved to `generated.json` and shown again later.
Each PDF is parsed once on first use and cached in memory (RHEL 9: about 3 s).

Without the API server, the page reads PDFs and saved results from `snapshot/` instead;
only Generate is disabled, with a note next to the button. The server keeps `snapshot/` up to date.

## API

| Method | Path | Response |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| GET | `/who` | `{"name": "forja-cis-ansible", "path": "<server folder>"}` |
| GET | `/api/pdfs` | `{"pdfs": [name]}`: PDFs in `documents/` |
| GET | `/api/items?pdf=` | `{"items": [{kind, number, title, status, page, level, intro?}]}`. kind = section / recommendation, page = PDF page |
| GET | `/api/recommendation?pdf=&number=` | `{number, title, status, page, fields: [{key, label, text}]}`. Fields in the defined order; missing ones are omitted |
| GET | `/api/ansible?pdf=&number=` | `{status, error, started_at, result?, generated_at?, model?}`. status = none / running / done / error; result = `{remediation_tasks, verification_tasks, rollback_tasks, notes}` |
| POST | `/api/ansible` | Same as GET. Body `{pdf, number}`. Starts a Codex job in the background (no-op if one is running) |

## Project structure

```
index.html      UI
data.js         UI constants
common.js       UI helper functions
api_server.py   API routes
common.py       Server logic
data.py         Server constants
documents/      CIS Benchmark PDFs (input; not included, see above)
generated.json  Saved data: generated Ansible tasks, keyed by "<pdf>::<number>"
snapshot/       Saved data: parsed PDFs and results per PDF, for viewing without the API server
lib/            React, ReactDOM, MUI, Babel (bundled, no CDN)
```

## Tech stack

- [React](https://react.dev/) and [MUI](https://mui.com/), loaded from `lib/` via `<script>` tags
- [Babel Standalone](https://babeljs.io/docs/babel-standalone) for in-browser JSX
- [FastAPI](https://fastapi.tiangolo.com/) and [Uvicorn](https://www.uvicorn.org/)
- [Codex](https://github.com/openai/codex) via the `openai-codex` SDK
- `pdftotext` from [Poppler](https://poppler.freedesktop.org/)
