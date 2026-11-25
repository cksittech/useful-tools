import json
import logging
import re
import shutil
import subprocess
import tempfile
import textwrap
import threading
import time
from pathlib import Path

from openai_codex import ApprovalMode, Codex, Sandbox

from data import (
    ANSIBLE_OUTPUT_SCHEMA,
    ANSIBLE_PROMPT,
    APPENDIX_PATTERN,
    CODEX_MODEL,
    CODEX_REASONING_EFFORT,
    CODEX_STARTUP_MAX_ATTEMPTS,
    CODEX_STARTUP_RETRY_DELAY_SEC,
    GENERATED_FILE,
    GENERATED_SAVE_ATTEMPTS,
    GENERATED_SAVE_RETRY_SEC,
    PROMPT_FIELDS,
    FIELDS,
    FOOTER_PATTERN,
    MAX_TITLE_LINES,
    NUMBER_PATTERN,
    PDF_DIR,
    PDFTOTEXT_CANDIDATES,
    SNAPSHOT_DIR,
    SNAPSHOT_GLOBAL,
    SNAPSHOT_INDEX_FILE,
    STATUS_PATTERN,
    TOC_PATTERN,
)

_FOOTER_RE = re.compile(FOOTER_PATTERN)
_NUMBER_RE = re.compile(NUMBER_PATTERN)
_STATUS_RE = re.compile(STATUS_PATTERN)
_APPENDIX_RE = re.compile(APPENDIX_PATTERN)
_TOC_RE = re.compile(TOC_PATTERN)
_FIELD_RES = [
    (key, label, re.compile(r"^\s*" + re.escape(label) + r":\s*(.*)$")) for key, label in FIELDS
]

# path -> (mtime, parsed document)
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


# ---------------------------------------------------------------- PDF access

def _find_pdftotext() -> str:
    found = shutil.which("pdftotext")
    if found:
        return found
    for candidate in PDFTOTEXT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError("pdftotext not found. Install poppler or Git for Windows.")


def list_pdfs() -> list[str]:
    return sorted(p.name for p in PDF_DIR.glob("*.pdf"))


def _resolve_pdf(name: str) -> Path:
    path = (PDF_DIR / name).resolve()
    if path.parent != PDF_DIR or path.suffix.lower() != ".pdf" or not path.is_file():
        raise FileNotFoundError(name)
    return path


def _extract_pages(path: Path) -> list[list[str]]:
    """Return the PDF as pages of lines (layout preserved, page footers removed)."""
    proc = subprocess.run(
        [_find_pdftotext(), "-enc", "UTF-8", "-layout", str(path), "-"],
        capture_output=True,
        check=True,
    )
    text = proc.stdout.decode("utf-8", errors="replace").replace("\r", "")
    return [
        [line.rstrip() for line in page.split("\n") if not _FOOTER_RE.match(line)]
        for page in text.split("\f")
    ]


# ------------------------------------------------------------------- parsing

def _find_heading(lines: list[tuple[int, str]], profile_idx: int) -> tuple[int, str, str] | None:
    """Walk back from a 'Profile Applicability:' line to the numbered title above it.

    Returns (line index of the title, number, title text) or None.
    """
    end = profile_idx - 1
    while end >= 0 and not lines[end][1].strip():
        end -= 1
    for start in range(end, max(end - MAX_TITLE_LINES, -1), -1):
        text = lines[start][1]
        if not text.strip():
            return None
        m = _NUMBER_RE.match(text)
        if m:
            rest = " ".join([m.group(2).strip()] + [lines[k][1].strip() for k in range(start + 1, end + 1)])
            return start, m.group(1), rest
    return None


def _clean_block(block: list[str]) -> str:
    text = textwrap.dedent("\n".join(block)).strip("\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _split_fields(body: list[str]) -> list[dict]:
    """Cut a recommendation body into the defined fields, in their defined order."""
    fields: list[dict] = []
    current: dict | None = None
    next_field = 0
    for line in body:
        hit = None
        for i in range(next_field, len(_FIELD_RES)):
            m = _FIELD_RES[i][2].match(line)
            if m:
                hit = (i, m)
                break
        if hit:
            i, m = hit
            key, label, _ = _FIELD_RES[i]
            current = {"key": key, "label": label, "lines": []}
            fields.append(current)
            next_field = i + 1
            if m.group(1).strip():
                current["lines"].append(m.group(1).strip())
        elif current is not None:
            current["lines"].append(line)
    result = []
    for f in fields:
        text = _clean_block(f.pop("lines"))
        if f["key"] == "profile":
            text = "\n".join(re.sub(r"^[•\-\*\s]+", "", ln) for ln in text.split("\n") if ln.strip())
        result.append({**f, "text": text})
    return result


def _parse(pages: list[list[str]]) -> dict:
    lines = [(page_no, line) for page_no, page in enumerate(pages, 1) for line in page]

    # 1. Recommendations: a numbered title directly above "Profile Applicability:".
    recs = []
    for idx, (_, text) in enumerate(lines):
        if not _FIELD_RES[0][2].match(text):
            continue
        heading = _find_heading(lines, idx)
        if heading is None:
            continue
        start, number, title = heading
        m = _STATUS_RE.search(title)
        recs.append({
            "kind": "recommendation",
            "number": number,
            "title": _STATUS_RE.sub("", title).strip(),
            "status": m.group(1) if m else "",
            "page": lines[start][0],
            "_start": start,
            "_body": idx,
        })
    if not recs:
        return {"items": [], "recs": {}}

    # 2. Sections: a numbered line at the top of a page between the first and last recommendation.
    #    The range starts after the table of contents (lines ending in "..... 123").
    rec_starts = {r["_start"] for r in recs}
    toc_end = max(
        (i for i in range(recs[0]["_start"]) if _TOC_RE.search(lines[i][1])),
        default=-1,
    )
    first_page = lines[toc_end][0] + 1 if toc_end >= 0 else 1
    last_page = lines[recs[-1]["_start"]][0]
    #    A section heading is a numbered line whose number is an ancestor of the next recommendation.
    sections = []
    seen_numbers = set()
    next_rec = 0
    for idx, (page_no, text) in enumerate(lines):
        while next_rec < len(recs) and recs[next_rec]["_start"] <= idx:
            next_rec += 1
        if next_rec >= len(recs) or idx in rec_starts:
            continue
        if not (first_page <= page_no <= last_page):
            continue
        m = _NUMBER_RE.match(text)
        if not m or "..." in text or m.group(1) in seen_numbers:
            continue
        if recs[next_rec]["number"].startswith(m.group(1) + "."):
            seen_numbers.add(m.group(1))
            sections.append({
                "kind": "section",
                "number": m.group(1),
                "title": m.group(2).strip(),
                "status": "",
                "page": page_no,
                "_start": idx,
            })

    # 3. The body of each recommendation runs to the next heading (or the appendix).
    doc_end = len(lines)
    for idx in range(recs[-1]["_body"], len(lines)):
        if _APPENDIX_RE.match(lines[idx][1]):
            doc_end = idx
            break
    items = sorted(recs + sections, key=lambda x: x["_start"])
    by_number = {}
    for i, item in enumerate(items):
        end = items[i + 1]["_start"] if i + 1 < len(items) else doc_end
        if item["kind"] == "recommendation":
            body = [text for _, text in lines[item["_body"]:end]]
            by_number[item["number"]] = {
                "number": item["number"],
                "title": item["title"],
                "status": item["status"],
                "page": item["page"],
                "fields": _split_fields(body),
            }
        else:
            body = [text for _, text in lines[item["_start"] + 1:end]]
            item["intro"] = _clean_block(body)
    public = [
        {k: v for k, v in item.items() if not k.startswith("_")}
        for item in items
    ]
    for item in public:
        item["level"] = item["number"].count(".") + 1
    return {"items": public, "recs": by_number}


def _load(name: str) -> dict:
    path = _resolve_pdf(name)
    mtime = path.stat().st_mtime
    with _lock:
        cached = _cache.get(str(path))
        if cached and cached[0] == mtime:
            return cached[1]
        parsed = _parse(_extract_pages(path))
        _cache[str(path)] = (mtime, parsed)
        return parsed


# ----------------------------------------------------------------------- API

def list_items(name: str) -> list[dict]:
    return _load(name)["items"]


def get_recommendation(name: str, number: str) -> dict:
    recs = _load(name)["recs"]
    if number not in recs:
        raise KeyError(number)
    return recs[number]


# ------------------------------------------------- Ansible generation (Codex)
# One background job per (pdf, number): Codex() -> thread_start -> turn -> archive.
# Finished results are saved to GENERATED_FILE; running/failed state is memory only.

_jobs: dict[str, dict] = {}          # key -> {"status": "running" | "error", "error", "started_at"}
_jobs_lock = threading.Lock()
_codex_startup_lock = threading.Lock()
_generated_lock = threading.Lock()


def _job_key(pdf: str, number: str) -> str:
    return f"{pdf}::{number}"


# generated.json is loaded once and kept in memory. Status polls read memory only:
# on Windows, replacing a file fails while another handle has it open, so the
# server must not read the file while it is being replaced.
_generated: dict | None = None


def _generated_data() -> dict:
    """Caller must hold _generated_lock."""
    global _generated
    if _generated is None:
        try:
            _generated = json.loads(GENERATED_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _generated = {}
    return _generated


def _read_generated_entry(key: str) -> dict | None:
    with _generated_lock:
        return _generated_data().get(key)


def _write_generated(key: str, entry: dict) -> None:
    """Store in memory, then save the whole file. Saving is retried because an
    outside reader (editor, antivirus) can briefly lock generated.json; if it
    still fails, the entry stays in memory and goes out with the next save."""
    with _generated_lock:
        data = _generated_data()
        data[key] = entry
        if not _save_text(GENERATED_FILE, json.dumps(data, ensure_ascii=False, indent=2)):
            logging.warning("could not save %s (locked); kept in memory", GENERATED_FILE)


def _save_text(target: Path, text: str) -> bool:
    """Write via a temp file and replace; retried while another process holds target open."""
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(GENERATED_SAVE_ATTEMPTS):
        try:
            tmp.replace(target)
            return True
        except PermissionError:
            if attempt == GENERATED_SAVE_ATTEMPTS - 1:
                return False
            time.sleep(GENERATED_SAVE_RETRY_SEC)
    return False


def _build_prompt(pdf: str, rec: dict) -> str:
    fields = {f["key"]: f for f in rec["fields"]}
    body = "\n\n".join(
        f"### {fields[k]['label']}\n{fields[k]['text']}" for k in PROMPT_FIELDS if k in fields
    )
    return ANSIBLE_PROMPT.format(
        benchmark=Path(pdf).stem,
        number=rec["number"],
        title=rec["title"],
        status=rec["status"] or "unknown",
        body=body,
    )


def _start_codex_session() -> Codex:
    """Codex() starts its own app-server and can race on ~/.codex sqlite init; retry that."""
    last_error: Exception | None = None
    for _ in range(CODEX_STARTUP_MAX_ATTEMPTS):
        with _codex_startup_lock:
            try:
                return Codex()
            except Exception as e:
                if "state runtime" not in str(e).lower():
                    raise
                last_error = e
        time.sleep(CODEX_STARTUP_RETRY_DELAY_SEC)
    raise last_error


def _run_ansible_job(key: str, prompt: str) -> None:
    try:
        with _start_codex_session() as codex:
            thread = codex.thread_start(
                model=CODEX_MODEL,
                sandbox=Sandbox.read_only,
                approval_mode=ApprovalMode.deny_all,
                cwd=tempfile.gettempdir(),
            )
            try:
                result = thread.turn(
                    prompt,
                    output_schema=ANSIBLE_OUTPUT_SCHEMA,
                    model=CODEX_MODEL,
                    effort=CODEX_REASONING_EFFORT,
                ).run()
            finally:
                codex.thread_archive(thread.id)
        if not result.final_response:
            raise RuntimeError("Codex returned an empty response")
        output = json.loads(result.final_response)
        _write_generated(key, {
            "result": output,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": CODEX_MODEL,
        })
        with _jobs_lock:
            _jobs.pop(key, None)
    except Exception as e:
        with _jobs_lock:
            _jobs[key] = {"status": "error", "error": f"{type(e).__name__}: {e}"}
        return
    _refresh_snapshot(key.split("::", 1)[0])


def get_ansible(pdf: str, number: str) -> dict:
    key = _job_key(pdf, number)
    with _jobs_lock:
        job = dict(_jobs.get(key) or {})
    saved = _read_generated_entry(key)
    status = job.get("status") or ("done" if saved else "none")
    return {"status": status, "error": job.get("error"), "started_at": job.get("started_at"), **(saved or {})}


def start_ansible(pdf: str, number: str) -> dict:
    rec = get_recommendation(pdf, number)  # raises FileNotFoundError / KeyError
    key = _job_key(pdf, number)
    with _jobs_lock:
        if (_jobs.get(key) or {}).get("status") != "running":
            _jobs[key] = {"status": "running", "started_at": time.time()}
            threading.Thread(target=_run_ansible_job, args=(key, _build_prompt(pdf, rec)), daemon=True).start()
    return get_ansible(pdf, number)


# ------------------------------------------------------------------ Snapshot
# index.html reads these files when the API server is down, so PDFs and saved
# Ansible results stay viewable (Generate needs the server).
#   snapshot/index.js : window.CIS_SNAPSHOT.index = {pdfs, files, exported_at}
#   snapshot/<pdf>.js : window.CIS_SNAPSHOT.pdfs[pdf] = {items, recs, ansible}

_snapshot_lock = threading.Lock()
# A snapshot older than any of these is rebuilt at server start (parser or results changed).
_SNAPSHOT_DEPS = [Path(__file__), Path(__file__).with_name("data.py"), GENERATED_FILE]


def _snapshot_file(pdf: str) -> Path:
    return SNAPSHOT_DIR / (re.sub(r"[^A-Za-z0-9._-]", "_", pdf) + ".js")


def _snapshot_js(path: str, value) -> str:
    # ensure_ascii keeps the file plain ASCII, valid as JS regardless of page encoding.
    head = f"window.{SNAPSHOT_GLOBAL} = window.{SNAPSHOT_GLOBAL} || {{ pdfs: {{}} }};\n"
    return head + f"window.{SNAPSHOT_GLOBAL}{path} = {json.dumps(value, ensure_ascii=True)};\n"


def _parsed_for_snapshot(pdf: str) -> dict:
    """Parsed PDF without filling the in-memory cache (startup export walks every PDF)."""
    path = _resolve_pdf(pdf)
    with _lock:
        cached = _cache.get(str(path))
    if cached and cached[0] == path.stat().st_mtime:
        return cached[1]
    return _parse(_extract_pages(path))


def _write_snapshot(pdf: str) -> None:
    doc = _parsed_for_snapshot(pdf)
    prefix = pdf + "::"
    with _generated_lock:
        ansible = {k[len(prefix):]: v for k, v in _generated_data().items() if k.startswith(prefix)}
    data = {"items": doc["items"], "recs": doc["recs"], "ansible": ansible}
    with _snapshot_lock:
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        target = _snapshot_file(pdf)
        if not _save_text(target, _snapshot_js(f".pdfs[{json.dumps(pdf)}]", data)):
            logging.warning("could not save %s (locked)", target)


def _write_snapshot_index() -> None:
    files = {p: _snapshot_file(p).name for p in list_pdfs() if _snapshot_file(p).exists()}
    index = {"pdfs": list(files), "files": files, "exported_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    with _snapshot_lock:
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        _save_text(SNAPSHOT_DIR / SNAPSHOT_INDEX_FILE, _snapshot_js(".index", index))


def _refresh_snapshot(pdf: str) -> None:
    try:
        _write_snapshot(pdf)
        _write_snapshot_index()
    except Exception:
        logging.exception("snapshot refresh failed: %s", pdf)


def _snapshot_is_stale(pdf: str) -> bool:
    target = _snapshot_file(pdf)
    if not target.exists():
        return True
    deps = [_resolve_pdf(pdf), *(d for d in _SNAPSHOT_DEPS if d.exists())]
    return target.stat().st_mtime < max(d.stat().st_mtime for d in deps)


def _export_snapshots() -> None:
    for pdf in list_pdfs():
        try:
            if _snapshot_is_stale(pdf):
                _write_snapshot(pdf)
        except Exception:
            logging.exception("snapshot export failed: %s", pdf)
    _write_snapshot_index()


def start_snapshot_export() -> None:
    """Bring stale snapshots up to date in the background (about 3 s per PDF)."""
    threading.Thread(target=_export_snapshots, daemon=True).start()
