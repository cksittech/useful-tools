from pathlib import Path

from pydantic import BaseModel

APP_NAME = "forja-cis-ansible"

# Folder that holds the CIS Benchmark PDFs.
PDF_DIR = Path(__file__).resolve().parent / "documents"

# Used when pdftotext is not on PATH (e.g. uvicorn started from PowerShell).
PDFTOTEXT_CANDIDATES = [
    r"C:\Program Files\Git\mingw64\bin\pdftotext.exe",
    r"C:\Program Files (x86)\Git\mingw64\bin\pdftotext.exe",
]

# Recommendation fields in the order the benchmark defines them
# (see "Recommendation Definitions" in each PDF).
# keep keys in sync with MONOSPACE_FIELDS in data.js
FIELDS = [
    ("profile", "Profile Applicability"),
    ("description", "Description"),
    ("rationale", "Rationale"),
    ("impact", "Impact"),
    ("audit", "Audit"),
    ("remediation", "Remediation"),
    ("default_value", "Default Value"),
    ("references", "References"),
    ("cis_controls", "CIS Controls"),
    ("additional_information", "Additional Information"),
]

# Regexes used by the parser.
FOOTER_PATTERN = r"^\s*Page \d+\s*$"
NUMBER_PATTERN = r"^(\d+(?:\.\d+)*)\s+(\S.*)$"
STATUS_PATTERN = r"\s*\((Automated|Manual)\)\s*$"
APPENDIX_PATTERN = r"^Appendix\b"
TOC_PATTERN = r"\.{5,}\s*\d+\s*$"

# How many lines a wrapped recommendation title may span.
MAX_TITLE_LINES = 4

# --- Codex (Ansible task generation) ------------------------------------------------

# Set either to None to fall back to the Codex CLI's own default (~/.codex/config.toml).
CODEX_MODEL = "gpt-6.1-sol"
CODEX_REASONING_EFFORT = "medium"

# Codex() construction is retried on the sqlite "state runtime" startup race.
CODEX_STARTUP_MAX_ATTEMPTS = 3
CODEX_STARTUP_RETRY_DELAY_SEC = 1.5

# Generated results, keyed by "<pdf>::<number>". Survives server restarts.
GENERATED_FILE = Path(__file__).resolve().parent / "generated.json"
# Saving generated.json is retried while another process holds it open (Windows).
GENERATED_SAVE_ATTEMPTS = 10
GENERATED_SAVE_RETRY_SEC = 0.5

# Snapshot for viewing without the API server: parsed PDFs + saved Ansible results,
# written as .js data files that index.html loads with <script> (works from file://).
# Refreshed in the background at server start and after each generation.
SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshot"
SNAPSHOT_INDEX_FILE = "index.js"
# keep in sync with SNAPSHOT_GLOBAL in data.js
SNAPSHOT_GLOBAL = "CIS_SNAPSHOT"

# Fields sent to Codex as source material (References / CIS Controls are left out).
PROMPT_FIELDS = ["description", "rationale", "impact", "audit", "remediation", "default_value", "additional_information"]

# keep task-list keys in sync with ANSIBLE_BLOCKS in data.js
ANSIBLE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "remediation_tasks": {"type": "string"},
        "verification_tasks": {"type": "string"},
        "rollback_tasks": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": ["remediation_tasks", "verification_tasks", "rollback_tasks", "notes"],
    "additionalProperties": False,
}

ANSIBLE_PROMPT = """You are writing Ansible tasks that implement one CIS Benchmark recommendation.

Benchmark: {benchmark}
Recommendation: {number} {title} ({status})

The recommendation text extracted from the PDF follows. Treat it as the specification.
{body}

Write three Ansible task lists (YAML lists of tasks, no play header, no hosts, no roles):

Choose the Ansible approach that fits the benchmark's target:
- Linux hosts: ansible.builtin.*, ansible.posix.*, community.general.*; become: true where root is required.
- Windows / Group Policy (e.g. browser or editor policies): ansible.windows.*, community.windows.*
  (registry-based policy values via ansible.windows.win_regedit).
- Cloud services (AWS): amazon.aws.* / community.aws.*, run against localhost with API credentials.
- SaaS / REST-managed platforms (e.g. GitHub, GitLab): ansible.builtin.uri against the documented API,
  run against localhost with a token variable.
- Applications (Docker, PostgreSQL, MongoDB, ...): their collections (community.docker.*,
  community.postgresql.*, community.mongodb.*) or the host-level modules above.
Use only modules, options and API endpoints that really exist; never invent them.
Put environment-specific values (names, IDs, tokens, regions, allow-lists) in clearly named variables.
If part of the recommendation cannot be automated (organizational process, human review),
automate what can be applied/checked and explain the rest in notes. If nothing can be automated,
return a task list containing a single ansible.builtin.debug task that states the manual step.

1. remediation_tasks: tasks that apply the setting described in Remediation.
   - Idempotent; safe to run repeatedly.
   - Use fully qualified module names.
   - Prefer dedicated modules over shell/command. When shell/command is unavoidable,
     set changed_when / failed_when correctly.
2. verification_tasks: tasks that check the system complies, following the Audit procedure.
   - Must not change the system: changed_when: false, and safe under --check
     (check_mode: false on read-only commands).
   - Finish with ansible.builtin.assert tasks whose fail_msg says what is wrong.
   - If the Audit says a state is also a pass (e.g. module not present at all), treat it as a pass.
3. rollback_tasks: tasks that undo remediation_tasks.
   - Return the setting to the Default Value stated in the text; if none is stated, to the product's
     default (typically: remove the files, lines, registry values or policies the remediation added,
     re-enable what it disabled).
   - Idempotent; only revert what remediation_tasks changed.
   - If reverting is impossible or meaningless (e.g. deleted data, a manual organizational step),
     return a single ansible.builtin.debug task explaining why, and say so in notes.

Jinja conditions (when / changed_when / failed_when / assert that) must use Ansible tests after "is",
such as "is search(...)", "is match(...)" or "is regex(...)". Never put a filter after "is"
(e.g. "is regex_search(...)" is invalid and fails at runtime).

Prefix every task name with "{number} | ".
Do not touch anything outside this recommendation. Do not read or modify any files; answer from the text above.

notes: short notes in Japanese for the operator (target/connection to run against, prerequisites,
required collections, reboot needs, variables to set, manual parts, what rollback cannot restore).
Empty string if none.
"""


# POST /api/ansible body.
class AnsibleRequest(BaseModel):
    pdf: str
    number: str
