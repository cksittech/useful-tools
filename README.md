# Useful Tools

A collection of small no-build web apps built with React and MUI.
There is no bundler and no `npm install`: open `index.html` directly in the browser.

The top page lists the tools as cards. Click a card to open that tool.

## Tools

| Tool | Description |
|---|---|
| [Telar de Ideas](telar-de-ideas/README.md) | Node/workflow editor: wire nodes to calculate, format, branch, move folders and call Codex |
| [Forja CIS-Ansible](forja-cis-ansible/README.md) | Browse CIS Benchmark recommendations from the PDF and generate apply / verify / rollback Ansible tasks with Codex |
| [Alternativa ppt Libre](alternativa-ppt-libre/README.md) | Edit Markdown and slides side by side, and save / open them as PPTX |

Each tool has its own README with requirements and usage. Some tools need a local API server.

## Requirements

- A modern browser
- For tools with an API server: Python 3.10+ (see each tool's README)

## Usage

1. Open `index.html` in the browser.
2. Click a tool's card.

## Project structure

```
index.html               Top page (tool cards)
images/                  Card images, one per tool
lib/                     React, ReactDOM, MUI, Babel for the top page (bundled, no CDN)
telar-de-ideas/          Telar de Ideas
forja-cis-ansible/       Forja CIS-Ansible
alternativa-ppt-libre/   Alternativa ppt Libre
```

## Tech stack

- [React](https://react.dev/) and [MUI](https://mui.com/), loaded from `lib/` via `<script>` tags
- [Babel Standalone](https://babeljs.io/docs/babel-standalone) for in-browser JSX
