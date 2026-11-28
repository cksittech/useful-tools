# Forja CIS-Ansible
<details><summary><img src="https://flagcdn.com/w20/gb.png" alt="English"> English</summary>

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
`snapshot/` and `generated.json` are built from them, so they are not included either: `generated.json` is created on the first generation.

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

</details>
<details><summary><img src="https://flagcdn.com/w20/es.png" alt="Español"> Español (traducción automática)</summary>

"Forja" significa "forge" en inglés: esta aplicación forja tareas de Ansible a partir de los CIS Benchmarks.

Una aplicación web sin compilación, construida con React y MUI y respaldada por un pequeño servidor FastAPI.
No hay empaquetador ni `npm install`: abra `index.html` directamente en el navegador.

Elija un PDF de CIS Benchmark de la carpeta `documents/`, recorra sus recomendaciones
(p. ej. 1.1.1.5) agrupadas por sección y vea la seleccionada dividida en los
campos definidos en "Recommendation Definitions" (Profile Applicability, Description,
Rationale, Impact, Audit, Remediation, Default Value, References, CIS Controls,
Additional Information).

El panel de detalle tiene dos pestañas: Details (los campos del PDF) y Ansible. El botón
"Generate" de la pestaña Ansible pide a Codex tres listas de tareas, cada una en su propio cuadro
con un botón Copy: remediation (aplicar), verification (auditar) y rollback (deshacer).

## PDFs de CIS Benchmark (aporte los suyos)

No se incluye ningún PDF: CIS no permite alojar sus Benchmarks fuera de CIS en ningún formato.
Descargue los que necesite desde https://www.cisecurity.org/cis-benchmarks y colóquelos en
`documents/`. Están bajo la licencia CC BY-NC-SA 4.0 (solo uso no comercial).
`snapshot/` y `generated.json` se generan a partir de ellos, por lo que tampoco se incluyen: `generated.json` se crea con la primera generación.

## Requisitos

- Un navegador moderno
- Python 3.10+
- `fastapi`, `uvicorn` y `openai-codex`, con `codex login` realizado una vez
- `pdftotext` (poppler). Git for Windows lo incluye en
  `C:\Program Files\Git\mingw64\bin\pdftotext.exe`, que se usa cuando no está en el PATH.

```
pip install fastapi uvicorn openai-codex
```

## Uso

1. Coloque los PDFs de CIS Benchmark en `documents/`.
2. Inicie el servidor de la API en esta carpeta:

   ```
   $env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --reload --host 127.0.0.1 --port 9032
   ```

3. Abra `index.html` en el navegador.
4. Elija un PDF y una recomendación. En la pestaña Ansible, haga clic en **Generate**.

La generación tarda alrededor de un minuto. Codex se ejecuta en solo lectura y con las aprobaciones denegadas.
Los resultados se guardan en `generated.json` y se vuelven a mostrar más tarde.
Cada PDF se analiza una vez en el primer uso y se guarda en memoria (RHEL 9: unos 3 s).

Sin el servidor de la API, la página lee los PDFs y los resultados guardados desde `snapshot/`;
solo se desactiva Generate, con una nota junto al botón. El servidor mantiene `snapshot/` actualizado.

## API

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| GET | `/who` | `{"name": "forja-cis-ansible", "path": "<carpeta del servidor>"}` |
| GET | `/api/pdfs` | `{"pdfs": [name]}`: PDFs en `documents/` |
| GET | `/api/items?pdf=` | `{"items": [{kind, number, title, status, page, level, intro?}]}`. kind = section / recommendation, page = página del PDF |
| GET | `/api/recommendation?pdf=&number=` | `{number, title, status, page, fields: [{key, label, text}]}`. Campos en el orden definido; los que faltan se omiten |
| GET | `/api/ansible?pdf=&number=` | `{status, error, started_at, result?, generated_at?, model?}`. status = none / running / done / error; result = `{remediation_tasks, verification_tasks, rollback_tasks, notes}` |
| POST | `/api/ansible` | Igual que GET. Cuerpo `{pdf, number}`. Inicia un trabajo de Codex en segundo plano (no hace nada si ya hay uno en curso) |

## Estructura del proyecto

```
index.html      Interfaz de usuario
data.js         Constantes de la interfaz
common.js       Funciones auxiliares de la interfaz
api_server.py   Rutas de la API
common.py       Lógica del servidor
data.py         Constantes del servidor
documents/      PDFs de CIS Benchmark (entrada; no incluidos, ver arriba)
generated.json  Datos guardados: tareas de Ansible generadas, con la clave "<pdf>::<number>"
snapshot/       Datos guardados: PDFs analizados y resultados por PDF, para ver sin el servidor de la API
lib/            React, ReactDOM, MUI, Babel (incluidos, sin CDN)
```

## Tecnologías

- [React](https://react.dev/) y [MUI](https://mui.com/), cargados desde `lib/` mediante etiquetas `<script>`
- [Babel Standalone](https://babeljs.io/docs/babel-standalone) para JSX en el navegador
- [FastAPI](https://fastapi.tiangolo.com/) y [Uvicorn](https://www.uvicorn.org/)
- [Codex](https://github.com/openai/codex) mediante el SDK `openai-codex`
- `pdftotext` de [Poppler](https://poppler.freedesktop.org/)

</details>
<details><summary><img src="https://flagcdn.com/w20/br.png" alt="Português"> Português (tradução automática)</summary>

"Forja" significa "forja" em espanhol ("forge" em inglês): este aplicativo forja tarefas Ansible a partir dos CIS Benchmarks.

Um aplicativo web sem build, feito com React e MUI e apoiado por um pequeno servidor FastAPI.
Não há bundler nem `npm install`: abra `index.html` diretamente no navegador.

Escolha um PDF do CIS Benchmark na pasta `documents/`, navegue pelas recomendações
(ex.: 1.1.1.5) agrupadas por seção e veja a selecionada dividida nos
campos definidos em "Recommendation Definitions" (Profile Applicability, Description,
Rationale, Impact, Audit, Remediation, Default Value, References, CIS Controls,
Additional Information).

O painel de detalhes tem duas abas: Details (os campos do PDF) e Ansible. O botão
"Generate" da aba Ansible pede ao Codex três listas de tarefas, cada uma em sua própria caixa
com um botão Copy: remediation (aplicar), verification (auditar) e rollback (desfazer).

## PDFs do CIS Benchmark (traga os seus)

Nenhum PDF está incluído: o CIS não permite hospedar seus Benchmarks fora do CIS em nenhum formato.
Baixe os que precisar em https://www.cisecurity.org/cis-benchmarks e coloque-os em
`documents/`. Eles são licenciados sob CC BY-NC-SA 4.0 (somente uso não comercial).
`snapshot/` e `generated.json` são gerados a partir deles, então também não são incluídos: `generated.json` é criado na primeira geração.

## Requisitos

- Um navegador moderno
- Python 3.10+
- `fastapi`, `uvicorn` e `openai-codex`, com `codex login` feito uma vez
- `pdftotext` (poppler). O Git for Windows o inclui em
  `C:\Program Files\Git\mingw64\bin\pdftotext.exe`, que é usado quando ele não está no PATH.

```
pip install fastapi uvicorn openai-codex
```

## Uso

1. Coloque os PDFs do CIS Benchmark em `documents/`.
2. Inicie o servidor da API nesta pasta:

   ```
   $env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --reload --host 127.0.0.1 --port 9032
   ```

3. Abra `index.html` no navegador.
4. Escolha um PDF e uma recomendação. Na aba Ansible, clique em **Generate**.

A geração leva cerca de um minuto. O Codex roda somente leitura e com aprovações negadas.
Os resultados são salvos em `generated.json` e exibidos novamente depois.
Cada PDF é analisado uma vez no primeiro uso e mantido em memória (RHEL 9: cerca de 3 s).

Sem o servidor da API, a página lê os PDFs e os resultados salvos de `snapshot/`;
apenas o Generate fica desativado, com um aviso ao lado do botão. O servidor mantém `snapshot/` atualizado.

## API

| Método | Caminho | Resposta |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| GET | `/who` | `{"name": "forja-cis-ansible", "path": "<pasta do servidor>"}` |
| GET | `/api/pdfs` | `{"pdfs": [name]}`: PDFs em `documents/` |
| GET | `/api/items?pdf=` | `{"items": [{kind, number, title, status, page, level, intro?}]}`. kind = section / recommendation, page = página do PDF |
| GET | `/api/recommendation?pdf=&number=` | `{number, title, status, page, fields: [{key, label, text}]}`. Campos na ordem definida; os ausentes são omitidos |
| GET | `/api/ansible?pdf=&number=` | `{status, error, started_at, result?, generated_at?, model?}`. status = none / running / done / error; result = `{remediation_tasks, verification_tasks, rollback_tasks, notes}` |
| POST | `/api/ansible` | Igual ao GET. Corpo `{pdf, number}`. Inicia um job do Codex em segundo plano (não faz nada se já houver um em execução) |

## Estrutura do projeto

```
index.html      Interface
data.js         Constantes da interface
common.js       Funções auxiliares da interface
api_server.py   Rotas da API
common.py       Lógica do servidor
data.py         Constantes do servidor
documents/      PDFs do CIS Benchmark (entrada; não incluídos, veja acima)
generated.json  Dados salvos: tarefas Ansible geradas, com a chave "<pdf>::<number>"
snapshot/       Dados salvos: PDFs analisados e resultados por PDF, para ver sem o servidor da API
lib/            React, ReactDOM, MUI, Babel (incluídos, sem CDN)
```

## Tecnologias

- [React](https://react.dev/) e [MUI](https://mui.com/), carregados de `lib/` por meio de tags `<script>`
- [Babel Standalone](https://babeljs.io/docs/babel-standalone) para JSX no navegador
- [FastAPI](https://fastapi.tiangolo.com/) e [Uvicorn](https://www.uvicorn.org/)
- [Codex](https://github.com/openai/codex) por meio do SDK `openai-codex`
- `pdftotext` do [Poppler](https://poppler.freedesktop.org/)

</details>
