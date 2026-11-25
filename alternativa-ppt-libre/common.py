# common.py
# Writing presentation markdown with Codex (server-side logic of the generation API).
# Definitions (prompts, limits, models) are in data.py. The app reads the result with
# parseMarkdown in common.js, so the text is returned as Codex wrote it (minus a code fence).

import json
import re

from data import (
    CODEX_APPROVAL_MODE,
    CODEX_MODEL,
    CODEX_REASONING_EFFORT,
    CODEX_SANDBOX,
    CONFIG_FILE,
    MAX_MARKDOWN_CHARS,
    MAX_REQUEST_CHARS,
    NEW_PROMPT,
    REVISE_PROMPT,
    SYSTEM_PROMPT,
)


# Codex could not write the markdown (not installed, not logged in, or the turn failed).
class GenerationError(RuntimeError):
    pass


# Settings from config.json ({} when the file is absent).
def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


# Removes a ``` fence the model may have wrapped the whole answer in.
def strip_code_fence(text: str) -> str:
    m = re.fullmatch(r"\s*```[\w-]*\n(.*?)\n?```\s*", text, re.DOTALL)
    return m.group(1) if m else text


# The user turn: a new deck, or a revision of current when it is given.
def build_prompt(request: str, current: str | None) -> str:
    request = request.strip()
    if not request:
        raise ValueError("Enter a request.")
    if len(request) > MAX_REQUEST_CHARS:
        raise ValueError(f"The request is too long (at most {MAX_REQUEST_CHARS} characters).")
    if current is None:
        return NEW_PROMPT.format(request=request)
    if not current.strip():
        raise ValueError("There is no markdown to revise.")
    if len(current) > MAX_MARKDOWN_CHARS:
        raise ValueError(f"The markdown is too long (at most {MAX_MARKDOWN_CHARS} characters).")
    return REVISE_PROMPT.format(request=request, markdown=current)


# Asks Codex for presentation markdown: a new deck, or current revised by the request.
def generate_markdown(request: str, current: str | None = None) -> str:
    prompt = build_prompt(request, current)
    try:
        from openai_codex import ApprovalMode, Codex, Sandbox
    except ImportError:
        raise GenerationError("Codex SDK is missing. Run pip install openai-codex.")
    config = load_config()
    model = config.get("codex_model", CODEX_MODEL)
    effort = config.get("codex_reasoning_effort", CODEX_REASONING_EFFORT)
    try:
        codex = Codex()
    except Exception as e:
        raise GenerationError(f"Cannot start Codex (check that you have run codex login): {e}")
    try:
        thread = codex.thread_start(
            model=model, ephemeral=True, developer_instructions=SYSTEM_PROMPT,
            sandbox=Sandbox(CODEX_SANDBOX), approval_mode=ApprovalMode(CODEX_APPROVAL_MODE),
        )
        result = thread.run(prompt, model=model, effort=effort)
    except Exception as e:
        raise GenerationError(f"Codex generation failed: {e}")
    finally:
        codex.close()
    if result.status.value != "completed" or not result.final_response:
        message = result.error.message if result.error is not None else result.status.value
        raise GenerationError(f"Codex generation failed: {message}")
    return strip_code_fence(result.final_response)
