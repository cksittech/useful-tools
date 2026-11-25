# data.py
# Constants and request models of the generation API. No functions.

from pathlib import Path

from pydantic import BaseModel

APP_NAME = "alternativa-ppt-libre"

# Optional settings file ({"codex_model": "...", "codex_reasoning_effort": "..."}).
CONFIG_FILE = Path(__file__).parent / "config.json"

# Codex model / reasoning effort used to write the markdown; None = the Codex CLI default
# (~/.codex/config.toml). config.json "codex_model" / "codex_reasoning_effort" override them.
CODEX_MODEL = None
CODEX_REASONING_EFFORT = None

# The writing turn only produces text: no file access, no approvals.
CODEX_SANDBOX = "read-only"
CODEX_APPROVAL_MODE = "deny_all"

# Longest request text and current markdown accepted (characters).
MAX_REQUEST_CHARS = 20000
MAX_MARKDOWN_CHARS = 200000

# Rules of the markdown the app reads. Keep in sync with parseMarkdown in common.js.
SYSTEM_PROMPT = """You write presentation slides as markdown for a slide app.
Output only the markdown: no preface, no explanation, no code fence.

Slide rules:
- "# Heading" starts the title slide (normally only the first slide). Lines under it are the subtitle.
- "## Heading" starts a chapter divider slide. One short line under it is allowed.
- "### Heading" starts a normal slide.
- "#### Heading" is a subheading inside a normal slide.
- "- item" is a bullet and "1. item" a numbered item. Nest an item by indenting it under the
  text of the item above (2 spaces under "- ", 3 spaces under "1. "). Use at most 3 levels.
- Any other line is body text. Keep body text short.
- A text line that would start with "#", "-", "*", "+" or "1." must start with a backslash ("\\- 5 days").
- Do not use tables, images, links, code, bold or italic, horizontal rules or "#####".
- A normal slide must fit on one slide: about 3 to 6 bullets.
"""

# User turn for a new deck. {request}: what the user asked for.
NEW_PROMPT = """Write a new presentation for this request.
Write in the language of the request.

Request:
{request}
"""

# User turn for revising the deck being written. {request}: what to change; {markdown}: the deck now.
REVISE_PROMPT = """Revise the presentation below according to the request and output the whole revised markdown.
Keep every slide, line and order the request does not ask to change exactly as it is.
Write new text in the language of the presentation.

Request:
{request}

Current presentation:
{markdown}
"""


# POST /api/generate: what to write; current is the markdown to revise (None = write a new deck).
class GenerateRequest(BaseModel):
    request: str
    current: str | None = None
