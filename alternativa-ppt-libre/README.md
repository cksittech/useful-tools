# Alternativa ppt Libre

A no-build MUI app for editing a slide deck as Markdown and as slides side by side, and for
saving and opening it as PPTX. Editing, saving and opening run in the browser. Only Markdown
generation (Codex) needs the small local API.

## Files

    index.html          UI (React components and state live only here)
    data.js             Constants, lookup tables, OOXML part templates and UI style objects. No functions
    common.js           Functions: Markdown <-> PPTX conversion, editing session, undo, browser storage,
                        editor helpers, generation API calls. No React, page DOM, or state
    api_server.py       Generation API entry point (route definitions only)
    common.py           Markdown generation with Codex
    data.py             Generation constants, prompts and request models. No functions
    config.json         Optional: {"codex_model": "...", "codex_reasoning_effort": "..."}
    lib/                External libraries (react / react-dom / material-ui / babel / jszip)
    tests/              test_convert.html + test_convert.js (browser tests), test_api.py (API tests)
    README.md           This file

## Start

Open index.html directly in the browser (Edge or Chrome). No server or install is needed except for Generate.

- Open: loads a .md / .txt or a .pptx saved by this app (its layout settings and background images come back with it).
- Save PPTX / Save MD: downloads the deck.
- Layout: placement, text styles, background and footer of each slide kind.
- Generate: writes the Markdown with Codex (needs the API below).
  - Revise current: rewrites the Markdown being written as asked; slides not mentioned stay as they are.
  - New draft: writes a new presentation in place of the current content.
  Both are one Undo step and keep the layout settings.

## Generation API (only for Generate)

Needs Python with `pip install fastapi uvicorn openai-codex` and `codex login` done once.
Start it in this folder:

    $env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --host 127.0.0.1 --port 9031

If you change the port, keep --port and API_BASE in data.js the same.

| Path | Returns | Notes |
|---|---|---|
| GET /health | {"status": "ok"} | Common. Every app has it |
| GET /who | {"name", "path"} | Common. Shows which app is using the port |
| POST /api/generate | {"markdown"} | Body {"request", "current"}; current = markdown to revise, null = new deck. 400 bad request, 502 Codex failed |

The markdown and the layout settings are kept in this browser (IndexedDB, database `alternativa-ppt-libre`)
and come back on the next visit. They do not move to other browsers or PCs and are lost when the
browser's site data is cleared, so save a PPTX to keep work.

## Tests

Open tests/test_convert.html in the browser. Every test runs on load and the result is listed.
The generation tests replace fetch, so the API does not need to be running.
The tests use the database `alternativa-ppt-libre-tests` and clear it at the end; the app's data is not touched
(pages opened from files share one storage area, so this separation matters).

API tests (no Codex call): `$env:PYTHONDONTWRITEBYTECODE = "1"; python -m unittest discover tests`

## Markdown

    # Title slide
    ## Chapter slide
    ### Normal slide
    #### Subheading
    Body text
    - Bullet          (indent deeper than the item above to nest it)
    1. Numbered

## Three-file split

| Role | Server | UI |
|---|---|---|
| Entry point / UI | api_server.py | index.html |
| Logic / functions | common.py | common.js |
| Constants / types | data.py | data.js |

Do not add new .py / .js files; put code in one of these. A long common file is fine.

## Dependency direction

    api_server.py -> common.py -> data.py
    index.html    -> common.js -> data.js

Never reference in the reverse direction.
- data.py / data.js: no functions, no references to other project files.
- common.py: does not import fastapi or api_server. It raises ValueError (400) and
  GenerationError (502); api_server converts them to HTTP status codes.
- The markdown rules in SYSTEM_PROMPT (data.py) must match parseMarkdown in common.js.
- common.js: no React, no page DOM, no state. What needs to live between calls (the session,
  the open database, background image URLs, block keys) is held by index.html and passed in.
- Exception: common.js uses DOMParser / XMLSerializer to read and write the XML parts inside the
  PPTX. These work on separate XML documents only; the page itself is never touched.
