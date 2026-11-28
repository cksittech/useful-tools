# Telar de Ideas
<details><summary><img src="https://flagcdn.com/w20/gb.png" alt="English"> English</summary>

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

Each `.py` file in `node_plugin/` is one node type. See [node_plugin/README.md](./node_plugin/README.md).

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

</details>
<details><summary><img src="https://flagcdn.com/w20/es.png" alt="Español"> Español (traducción automática)</summary>

Un editor de nodos y flujos de trabajo sin compilación, construido con React, MUI y React Flow y respaldado por un servidor FastAPI.
No hay empaquetador ni `npm install`: abra `index.html` directamente en el navegador.

Coloque nodos en el lienzo, conéctelos y ejecútelos. Un AI Node envía su prompt
completado a Codex y pasa la salida estructurada a los nodos siguientes.
Un flujo de trabajo guardado también se puede ejecutar como API.

## Requisitos

- Un navegador moderno
- Python 3.10+
- `fastapi`, `uvicorn`, `pydantic` y `openai-codex`, con `codex login` realizado una vez

```
pip install fastapi uvicorn pydantic openai-codex
```

## Uso

1. Inicie el servidor de la API en esta carpeta:

   ```
   $env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --reload --host 127.0.0.1 --port 9014
   ```

2. Abra `index.html` en el navegador.
3. Añada nodos desde el menú, conéctelos y ejecute el flujo de trabajo.

Si cambia el puerto, mantenga iguales `--port`, `api_port` en `config.json` y `CODEX_API_BASE` en `data.js`.

### Modelo de Codex

`codex_model` / `codex_reasoning_effort` en `config.json` se aplican a todos los trabajos de AI Node.
Establézcalos en `null` para usar `~/.codex/config.toml`.

### Generate Workflow

Menú > Workflow > "+ Generate Workflow": describa lo que debe hacer el flujo de trabajo y Codex lo construye
a partir de los Plugin Nodes, Group, Wrapper y los AI Nodes guardados (Structured Output; no se usan API Input/Response).
El servidor comprueba la respuesta con la verificación previa a la ejecución y devuelve los problemas a Codex, hasta 3 intentos en total.
El resultado se abre en el lienzo, sin guardar ni ejecutar; guárdelo con "+ Save Workflow".
Aquí Codex se ejecuta en un sandbox de solo lectura, por lo que generar nunca modifica archivos.

### Añadir tipos de nodo

Cada archivo `.py` en `node_plugin/` es un tipo de nodo. Consulte [node_plugin/README.md](./node_plugin/README.md).

## API

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| GET | `/who` | `{"name": "telar-de-ideas", "path": "<carpeta del servidor>"}` |
| GET, POST, PUT, DELETE | `/nodes`, `/workflows` | AI Nodes / flujos de trabajo guardados (lista, uno, crear, actualizar, eliminar) |
| GET | `/node-types` | Lista de tipos de nodo |
| POST | `/evaluate` | Vista en vivo del lienzo |
| POST, GET | `/codex/jobs` | Trabajos de Codex (iniciar, consultar, `.../stop`) |
| POST | `/workflows/generate` | `{"job_id"}`. Consulte `GET /codex/jobs/{id}`; salida = `{workflow, summary, issues, attempts}` |
| POST, GET | `/runs`, `/workflows/{id}/runs` | Ejecuciones de flujos de trabajo en el servidor (iniciar, consultar, `.../stop`) |
| GET | `/api/{name}` | Ejecuta un flujo de trabajo guardado por nombre y devuelve el cuerpo de su API Response. Parámetros de consulta = parámetros de API Input; cada petición inicia una ejecución |
| GET | `/api/{name}/spec` | Parámetros y campos del flujo de trabajo (igual que `GET /workflows/{id}/api`) |

## Estructura del proyecto

```
index.html      Interfaz de usuario
data.js         Constantes de la interfaz
common.js       Funciones auxiliares de la interfaz
api_server.py   Rutas de la API
common.py       Lógica del servidor (trabajos de Codex, evaluación del grafo, tipos de nodo, ejecuciones)
data.py         Constantes del servidor
config.json     Ajustes leídos por el servidor y la interfaz (puerto, intervalo de consulta, modelo de Codex)
node_plugin/    Tipos de nodo de plugin, un archivo .py por tipo
node_ai/        AI Nodes guardados (JSON, un archivo cada uno)
workflows/      Flujos de trabajo guardados (JSON, un archivo cada uno)
lib/            React, ReactDOM, MUI, React Flow, Babel y otros (incluidos, sin CDN)
tests/          Pruebas
```

## Tecnologías

- [React](https://react.dev/), [MUI](https://mui.com/) y [React Flow](https://reactflow.dev/), cargados desde `lib/` mediante etiquetas `<script>`
- [Babel Standalone](https://babeljs.io/docs/babel-standalone) para JSX en el navegador
- [FastAPI](https://fastapi.tiangolo.com/) y [Uvicorn](https://www.uvicorn.org/)
- [Codex](https://github.com/openai/codex) mediante el SDK `openai-codex`

</details>
<details><summary><img src="https://flagcdn.com/w20/br.png" alt="Português"> Português (tradução automática)</summary>

Um editor de nós e fluxos de trabalho sem build, feito com React, MUI e React Flow e apoiado por um servidor FastAPI.
Não há bundler nem `npm install`: abra `index.html` diretamente no navegador.

Coloque nós na tela, conecte-os e execute-os. Um AI Node envia seu prompt
preenchido ao Codex e passa a saída estruturada para os próximos nós.
Um fluxo de trabalho salvo também pode ser executado como API.

## Requisitos

- Um navegador moderno
- Python 3.10+
- `fastapi`, `uvicorn`, `pydantic` e `openai-codex`, com `codex login` feito uma vez

```
pip install fastapi uvicorn pydantic openai-codex
```

## Uso

1. Inicie o servidor da API nesta pasta:

   ```
   $env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --reload --host 127.0.0.1 --port 9014
   ```

2. Abra `index.html` no navegador.
3. Adicione nós pelo menu, conecte-os e execute o fluxo de trabalho.

Se mudar a porta, mantenha iguais `--port`, `api_port` em `config.json` e `CODEX_API_BASE` em `data.js`.

### Modelo do Codex

`codex_model` / `codex_reasoning_effort` em `config.json` valem para todos os jobs de AI Node.
Defina-os como `null` para usar `~/.codex/config.toml`.

### Generate Workflow

Menu > Workflow > "+ Generate Workflow": descreva o que o fluxo de trabalho deve fazer, e o Codex o monta
a partir dos Plugin Nodes, Group, Wrapper e AI Nodes salvos (Structured Output; API Input/Response não são usados).
O servidor verifica a resposta com a checagem prévia à execução e devolve os problemas ao Codex, até 3 tentativas no total.
O resultado abre na tela, sem salvar nem executar; salve-o com "+ Save Workflow".
Aqui o Codex roda em um sandbox somente leitura, então gerar nunca altera arquivos.

### Adicionar tipos de nó

Cada arquivo `.py` em `node_plugin/` é um tipo de nó. Veja [node_plugin/README.md](./node_plugin/README.md).

## API

| Método | Caminho | Resposta |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| GET | `/who` | `{"name": "telar-de-ideas", "path": "<pasta do servidor>"}` |
| GET, POST, PUT, DELETE | `/nodes`, `/workflows` | AI Nodes / fluxos de trabalho salvos (lista, um, criar, atualizar, excluir) |
| GET | `/node-types` | Lista de tipos de nó |
| POST | `/evaluate` | Visualização ao vivo da tela |
| POST, GET | `/codex/jobs` | Jobs do Codex (iniciar, consultar, `.../stop`) |
| POST | `/workflows/generate` | `{"job_id"}`. Consulte `GET /codex/jobs/{id}`; saída = `{workflow, summary, issues, attempts}` |
| POST, GET | `/runs`, `/workflows/{id}/runs` | Execuções de fluxos de trabalho no servidor (iniciar, consultar, `.../stop`) |
| GET | `/api/{name}` | Executa um fluxo de trabalho salvo pelo nome e retorna o corpo da sua API Response. Query = parâmetros de API Input; cada requisição inicia uma execução |
| GET | `/api/{name}/spec` | Parâmetros e campos do fluxo de trabalho (igual a `GET /workflows/{id}/api`) |

## Estrutura do projeto

```
index.html      Interface
data.js         Constantes da interface
common.js       Funções auxiliares da interface
api_server.py   Rotas da API
common.py       Lógica do servidor (jobs do Codex, avaliação do grafo, tipos de nó, execuções)
data.py         Constantes do servidor
config.json     Configurações lidas pelo servidor e pela interface (porta, intervalo de consulta, modelo do Codex)
node_plugin/    Tipos de nó de plugin, um arquivo .py por tipo
node_ai/        AI Nodes salvos (JSON, um arquivo cada)
workflows/      Fluxos de trabalho salvos (JSON, um arquivo cada)
lib/            React, ReactDOM, MUI, React Flow, Babel e outros (incluídos, sem CDN)
tests/          Testes
```

## Tecnologias

- [React](https://react.dev/), [MUI](https://mui.com/) e [React Flow](https://reactflow.dev/), carregados de `lib/` por meio de tags `<script>`
- [Babel Standalone](https://babeljs.io/docs/babel-standalone) para JSX no navegador
- [FastAPI](https://fastapi.tiangolo.com/) e [Uvicorn](https://www.uvicorn.org/)
- [Codex](https://github.com/openai/codex) por meio do SDK `openai-codex`

</details>
