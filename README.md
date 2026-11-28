# Useful Tools
<details><summary><img src="https://flagcdn.com/w20/gb.png" alt="English"> English</summary>

A collection of small no-build web apps built with React and MUI.
There is no bundler and no `npm install`: open `index.html` directly in the browser.

The top page shows one tool at a time, with its name, description and screenshot, and moves to the next one every 7 seconds. Pick a tool from the list on the left to show it right away.

## Tools

| Tool | Description |
|---|---|
| [Telar de Ideas](./telar-de-ideas/) | A workflow editor: wire nodes to calculate, format, branch, move folders and call Codex. |
| [Forja CIS-Ansible](./forja-cis-ansible/) | Browse CIS Benchmark recommendations from the PDF and generate apply, verify and rollback Ansible tasks with Codex. |
| [Alternativa ppt Libre](./alternativa-ppt-libre/) | A slide editor: edit Markdown and slides side by side, and save and open them as PPTX. |

Each tool's README describes its requirements and usage. Some tools need a local API server.

## Requirements

- A modern browser
- For tools with an API server: Python 3.10+ (see each tool's README)

## Usage

1. Open `index.html` in the browser.
2. Pick a tool from the list on the left.
3. Click `./open` to open that tool.

## Project structure

```
index.html               Top page
images/                  Screenshots, one per tool
lib/                     GSAP for the top page (bundled, no CDN)
telar-de-ideas/          Telar de Ideas
forja-cis-ansible/       Forja CIS-Ansible
alternativa-ppt-libre/   Alternativa ppt Libre
```

## Tech stack

- [React](https://react.dev/) and [MUI](https://mui.com/), loaded from `lib/` via `<script>` tags
- [Babel Standalone](https://babeljs.io/docs/babel-standalone) for in-browser JSX
- [GSAP](https://gsap.com/) for the top page animation

## License

[MIT](./LICENSE). The libraries bundled in the `lib/` folders keep their own licenses; see [THIRD-PARTY-NOTICES.md](./THIRD-PARTY-NOTICES.md).

</details>
<details><summary><img src="https://flagcdn.com/w20/es.png" alt="Español"> Español (traducción automática)</summary>

Una colección de pequeñas aplicaciones web sin compilación, construidas con React y MUI.
No hay empaquetador ni `npm install`: abra `index.html` directamente en el navegador.

La página principal muestra una herramienta a la vez, con su nombre, su descripción y una captura de pantalla, y pasa a la siguiente cada 7 segundos. Elija una herramienta en la lista de la izquierda para mostrarla de inmediato.

## Herramientas

| Herramienta | Descripción |
|---|---|
| [Telar de Ideas](./telar-de-ideas/) | Un editor de flujos de trabajo: conecte nodos para calcular, dar formato, ramificar, mover carpetas y llamar a Codex. |
| [Forja CIS-Ansible](./forja-cis-ansible/) | Consulte las recomendaciones de CIS Benchmark desde el PDF y genere con Codex tareas de Ansible para aplicar, verificar y revertir. |
| [Alternativa ppt Libre](./alternativa-ppt-libre/) | Un editor de diapositivas: edite Markdown y diapositivas lado a lado, y guárdelas y ábralas como PPTX. |

El README de cada herramienta describe sus requisitos y su uso. Algunas herramientas necesitan un servidor de API local.

## Requisitos

- Un navegador moderno
- Para las herramientas con servidor de API: Python 3.10+ (consulte el README de cada herramienta)

## Uso

1. Abra `index.html` en el navegador.
2. Elija una herramienta en la lista de la izquierda.
3. Haga clic en `./open` para abrir esa herramienta.

## Estructura del proyecto

```
index.html               Página principal
images/                  Capturas de pantalla, una por herramienta
lib/                     GSAP para la página principal (incluido, sin CDN)
telar-de-ideas/          Telar de Ideas
forja-cis-ansible/       Forja CIS-Ansible
alternativa-ppt-libre/   Alternativa ppt Libre
```

## Tecnologías

- [React](https://react.dev/) y [MUI](https://mui.com/), cargados desde `lib/` mediante etiquetas `<script>`
- [Babel Standalone](https://babeljs.io/docs/babel-standalone) para JSX en el navegador
- [GSAP](https://gsap.com/) para la animación de la página principal

## Licencia

[MIT](./LICENSE). Las bibliotecas incluidas en las carpetas `lib/` mantienen sus propias licencias; consulte [THIRD-PARTY-NOTICES.md](./THIRD-PARTY-NOTICES.md).

</details>
<details><summary><img src="https://flagcdn.com/w20/br.png" alt="Português"> Português (tradução automática)</summary>

Uma coleção de pequenos aplicativos web sem build, feitos com React e MUI.
Não há bundler nem `npm install`: abra `index.html` diretamente no navegador.

A página inicial mostra uma ferramenta por vez, com o nome, a descrição e uma captura de tela, e passa para a próxima a cada 7 segundos. Escolha uma ferramenta na lista à esquerda para mostrá-la na hora.

## Ferramentas

| Ferramenta | Descrição |
|---|---|
| [Telar de Ideas](./telar-de-ideas/) | Um editor de fluxos de trabalho: conecte nós para calcular, formatar, ramificar, mover pastas e chamar o Codex. |
| [Forja CIS-Ansible](./forja-cis-ansible/) | Consulte as recomendações do CIS Benchmark a partir do PDF e gere com o Codex tarefas Ansible de aplicação, verificação e reversão. |
| [Alternativa ppt Libre](./alternativa-ppt-libre/) | Um editor de slides: edite Markdown e slides lado a lado, e salve e abra como PPTX. |

O README de cada ferramenta descreve os requisitos e o uso. Algumas ferramentas precisam de um servidor de API local.

## Requisitos

- Um navegador moderno
- Para ferramentas com servidor de API: Python 3.10+ (veja o README de cada ferramenta)

## Uso

1. Abra `index.html` no navegador.
2. Escolha uma ferramenta na lista à esquerda.
3. Clique em `./open` para abrir a ferramenta.

## Estrutura do projeto

```
index.html               Página inicial
images/                  Capturas de tela, uma por ferramenta
lib/                     GSAP para a página inicial (incluído, sem CDN)
telar-de-ideas/          Telar de Ideas
forja-cis-ansible/       Forja CIS-Ansible
alternativa-ppt-libre/   Alternativa ppt Libre
```

## Tecnologias

- [React](https://react.dev/) e [MUI](https://mui.com/), carregados de `lib/` por meio de tags `<script>`
- [Babel Standalone](https://babeljs.io/docs/babel-standalone) para JSX no navegador
- [GSAP](https://gsap.com/) para a animação da página inicial

## Licença

[MIT](./LICENSE). As bibliotecas incluídas nas pastas `lib/` mantêm suas próprias licenças; veja [THIRD-PARTY-NOTICES.md](./THIRD-PARTY-NOTICES.md).

</details>
