# Alternativa ppt Libre

A no-build web app built with React and MUI for editing a slide deck as Markdown and as slides
side by side, and for saving and opening it as PPTX.
There is no bundler and no `npm install`: open `index.html` directly in the browser.

Editing, saving and opening run in the browser. Only Markdown generation (Codex) needs the small local API.

## Requirements

- Edge or Chrome
- For Generate only: Python 3.10+, `fastapi`, `uvicorn` and `openai-codex`, with `codex login` done once

```
pip install fastapi uvicorn openai-codex
```

## Usage

1. Open `index.html` in the browser.
2. Write Markdown on the left; the slides update on the right.

- **Open**: loads a `.md` / `.txt` or a `.pptx` saved by this app (its layout settings and background images come back with it).
- **Save PPTX** / **Save MD**: downloads the deck.
- **Layout**: placement, text styles, background and footer of each slide kind.
- **Generate**: writes the Markdown with Codex (needs the API server below).
  - Revise current: rewrites the Markdown being written as asked; slides not mentioned stay as they are.
  - New draft: writes a new presentation in place of the current content.
  - Both are one Undo step and keep the layout settings.

To use Generate, start the API server in this folder:

```
$env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --host 127.0.0.1 --port 9031
```

If you change the port, keep `--port` and `API_BASE` in `data.js` the same.
The Codex model can be set in an optional `config.json`: `{"codex_model": "...", "codex_reasoning_effort": "..."}`.

The Markdown and the layout settings are kept in this browser (IndexedDB, database `alternativa-ppt-libre`)
and come back on the next visit. They do not move to other browsers or PCs and are lost when the
browser's site data is cleared, so save a PPTX to keep work.

### Markdown

```
# Title slide
## Chapter slide
### Normal slide
#### Subheading
Body text
- Bullet          (indent deeper than the item above to nest it)
1. Numbered
```

## API

| Method | Path | Response |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| GET | `/who` | `{"name": "alternativa-ppt-libre", "path": "<server folder>"}` |
| POST | `/api/generate` | `{"markdown"}`. Body `{"request", "current"}`; current = Markdown to revise, `null` = new deck. 400 bad request, 502 Codex failed |

## Project structure

```
index.html      UI
data.js         UI constants, OOXML part templates and style objects
common.js       Markdown <-> PPTX conversion, editing session, undo, browser storage, generation API calls
api_server.py   API routes
common.py       Markdown generation with Codex
data.py         Server constants and prompts
lib/            React, ReactDOM, MUI, Babel, JSZip (bundled, no CDN)
tests/          Tests
```

## Tech stack

- [React](https://react.dev/) and [MUI](https://mui.com/), loaded from `lib/` via `<script>` tags
- [Babel Standalone](https://babeljs.io/docs/babel-standalone) for in-browser JSX
- [JSZip](https://stuk.github.io/jszip/) for reading and writing PPTX
- [FastAPI](https://fastapi.tiangolo.com/) and [Uvicorn](https://www.uvicorn.org/)
- [Codex](https://github.com/openai/codex) via the `openai-codex` SDK
