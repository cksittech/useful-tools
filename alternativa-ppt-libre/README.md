# Alternativa ppt Libre
<details><summary><img src="https://flagcdn.com/w20/gb.png" alt="English"> English</summary>

A no-build web app built with React and MUI for editing a slide deck as Markdown and as slides
side by side, and for saving and opening it as PPTX.
There is no bundler and no `npm install`: open `index.html` directly in the browser.

Editing, saving and opening run in the browser. Only Markdown generation (Codex) needs the small local API.

## Requirements

- Edge or Chrome
- For Generate only: Python 3.10+ and the Python packages in `requirements.txt` (`fastapi`, `uvicorn`, `openai-codex` and their dependencies), with `codex login` done once

```
pip install -r requirements.txt
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
requirements.txt  Python dependencies (pinned)
lib/            React, ReactDOM, MUI, Babel, JSZip (bundled, no CDN)
tests/          Tests
```

## Tech stack

- [React](https://react.dev/) and [MUI](https://mui.com/), loaded from `lib/` via `<script>` tags
- [Babel Standalone](https://babeljs.io/docs/babel-standalone) for in-browser JSX
- [JSZip](https://stuk.github.io/jszip/) for reading and writing PPTX
- [FastAPI](https://fastapi.tiangolo.com/) and [Uvicorn](https://www.uvicorn.org/)
- [Codex](https://github.com/openai/codex) via the `openai-codex` SDK

</details>
<details><summary><img src="https://flagcdn.com/w20/es.png" alt="Español"> Español (traducción automática)</summary>

Una aplicación web sin compilación, construida con React y MUI, para editar una presentación como Markdown y como diapositivas
lado a lado, y para guardarla y abrirla como PPTX.
No hay empaquetador ni `npm install`: abra `index.html` directamente en el navegador.

La edición, el guardado y la apertura se ejecutan en el navegador. Solo la generación de Markdown (Codex) necesita la pequeña API local.

## Requisitos

- Edge o Chrome
- Solo para Generate: Python 3.10+ y los paquetes de Python en `requirements.txt` (`fastapi`, `uvicorn`, `openai-codex` y sus dependencias), con `codex login` realizado una vez

```
pip install -r requirements.txt
```

## Uso

1. Abra `index.html` en el navegador.
2. Escriba Markdown a la izquierda; las diapositivas se actualizan a la derecha.

- **Open**: carga un `.md` / `.txt` o un `.pptx` guardado por esta aplicación (vuelven con él sus ajustes de diseño e imágenes de fondo).
- **Save PPTX** / **Save MD**: descarga la presentación.
- **Layout**: posición, estilos de texto, fondo y pie de página de cada tipo de diapositiva.
- **Generate**: escribe el Markdown con Codex (necesita el servidor de la API de abajo).
  - Revise current: reescribe el Markdown actual según lo pedido; las diapositivas no mencionadas quedan igual.
  - New draft: escribe una presentación nueva en lugar del contenido actual.
  - Ambos son un solo paso de Undo y conservan los ajustes de diseño.

Para usar Generate, inicie el servidor de la API en esta carpeta:

```
$env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --host 127.0.0.1 --port 9031
```

Si cambia el puerto, mantenga iguales `--port` y `API_BASE` en `data.js`.
El modelo de Codex se puede definir en un `config.json` opcional: `{"codex_model": "...", "codex_reasoning_effort": "..."}`.

El Markdown y los ajustes de diseño se guardan en este navegador (IndexedDB, base de datos `alternativa-ppt-libre`)
y vuelven en la próxima visita. No pasan a otros navegadores ni a otros PCs y se pierden al borrar
los datos del sitio del navegador, así que guarde un PPTX para conservar el trabajo.

### Markdown

```
# Diapositiva de título
## Diapositiva de capítulo
### Diapositiva normal
#### Subtítulo
Texto del cuerpo
- Viñeta          (sangre más que el elemento anterior para anidarla)
1. Numerado
```

## API

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| GET | `/who` | `{"name": "alternativa-ppt-libre", "path": "<carpeta del servidor>"}` |
| POST | `/api/generate` | `{"markdown"}`. Cuerpo `{"request", "current"}`; current = Markdown que se revisa, `null` = presentación nueva. 400 petición incorrecta, 502 fallo de Codex |

## Estructura del proyecto

```
index.html      Interfaz de usuario
data.js         Constantes de la interfaz, plantillas de partes OOXML y objetos de estilo
common.js       Conversión Markdown <-> PPTX, sesión de edición, deshacer, almacenamiento del navegador, llamadas a la API de generación
api_server.py   Rutas de la API
common.py       Generación de Markdown con Codex
data.py         Constantes y prompts del servidor
requirements.txt  Dependencias de Python (versiones fijadas)
lib/            React, ReactDOM, MUI, Babel, JSZip (incluidos, sin CDN)
tests/          Pruebas
```

## Tecnologías

- [React](https://react.dev/) y [MUI](https://mui.com/), cargados desde `lib/` mediante etiquetas `<script>`
- [Babel Standalone](https://babeljs.io/docs/babel-standalone) para JSX en el navegador
- [JSZip](https://stuk.github.io/jszip/) para leer y escribir PPTX
- [FastAPI](https://fastapi.tiangolo.com/) y [Uvicorn](https://www.uvicorn.org/)
- [Codex](https://github.com/openai/codex) mediante el SDK `openai-codex`

</details>
<details><summary><img src="https://flagcdn.com/w20/br.png" alt="Português"> Português (tradução automática)</summary>

Um aplicativo web sem build, feito com React e MUI, para editar uma apresentação como Markdown e como slides
lado a lado, e para salvá-la e abri-la como PPTX.
Não há bundler nem `npm install`: abra `index.html` diretamente no navegador.

Edição, salvamento e abertura rodam no navegador. Apenas a geração de Markdown (Codex) precisa da pequena API local.

## Requisitos

- Edge ou Chrome
- Apenas para Generate: Python 3.10+ e os pacotes Python em `requirements.txt` (`fastapi`, `uvicorn`, `openai-codex` e suas dependências), com `codex login` feito uma vez

```
pip install -r requirements.txt
```

## Uso

1. Abra `index.html` no navegador.
2. Escreva Markdown à esquerda; os slides são atualizados à direita.

- **Open**: carrega um `.md` / `.txt` ou um `.pptx` salvo por este aplicativo (as configurações de layout e as imagens de fundo voltam junto).
- **Save PPTX** / **Save MD**: baixa a apresentação.
- **Layout**: posição, estilos de texto, fundo e rodapé de cada tipo de slide.
- **Generate**: escreve o Markdown com o Codex (precisa do servidor da API abaixo).
  - Revise current: reescreve o Markdown atual conforme o pedido; os slides não mencionados ficam como estão.
  - New draft: escreve uma nova apresentação no lugar do conteúdo atual.
  - Ambos são um único passo de Undo e mantêm as configurações de layout.

Para usar o Generate, inicie o servidor da API nesta pasta:

```
$env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --host 127.0.0.1 --port 9031
```

Se mudar a porta, mantenha iguais `--port` e `API_BASE` em `data.js`.
O modelo do Codex pode ser definido em um `config.json` opcional: `{"codex_model": "...", "codex_reasoning_effort": "..."}`.

O Markdown e as configurações de layout ficam neste navegador (IndexedDB, banco de dados `alternativa-ppt-libre`)
e voltam na próxima visita. Eles não passam para outros navegadores ou PCs e se perdem quando os
dados do site no navegador são apagados, então salve um PPTX para guardar o trabalho.

### Markdown

```
# Slide de título
## Slide de capítulo
### Slide normal
#### Subtítulo
Texto do corpo
- Marcador        (recue mais que o item acima para aninhá-lo)
1. Numerado
```

## API

| Método | Caminho | Resposta |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| GET | `/who` | `{"name": "alternativa-ppt-libre", "path": "<pasta do servidor>"}` |
| POST | `/api/generate` | `{"markdown"}`. Corpo `{"request", "current"}`; current = Markdown a revisar, `null` = nova apresentação. 400 requisição inválida, 502 falha do Codex |

## Estrutura do projeto

```
index.html      Interface
data.js         Constantes da interface, modelos de partes OOXML e objetos de estilo
common.js       Conversão Markdown <-> PPTX, sessão de edição, desfazer, armazenamento do navegador, chamadas à API de geração
api_server.py   Rotas da API
common.py       Geração de Markdown com o Codex
data.py         Constantes e prompts do servidor
requirements.txt  Dependências Python (versões fixadas)
lib/            React, ReactDOM, MUI, Babel, JSZip (incluídos, sem CDN)
tests/          Testes
```

## Tecnologias

- [React](https://react.dev/) e [MUI](https://mui.com/), carregados de `lib/` por meio de tags `<script>`
- [Babel Standalone](https://babeljs.io/docs/babel-standalone) para JSX no navegador
- [JSZip](https://stuk.github.io/jszip/) para ler e escrever PPTX
- [FastAPI](https://fastapi.tiangolo.com/) e [Uvicorn](https://www.uvicorn.org/)
- [Codex](https://github.com/openai/codex) por meio do SDK `openai-codex`

</details>
