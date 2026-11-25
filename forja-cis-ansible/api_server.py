from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import common
from data import APP_NAME, AnsibleRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    common.start_snapshot_export()
    yield


app = FastAPI(lifespan=lifespan)

# Only the GitHub Pages copy and index.html opened as file:// (Origin "null") may call this;
# any other site open in the browser could otherwise drive this PC.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://cksittech.github.io", "null"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/pdfs")
def pdfs():
    return {"pdfs": common.list_pdfs()}


@app.get("/api/items")
def items(pdf: str):
    try:
        return {"items": common.list_items(pdf)}
    except FileNotFoundError:
        raise HTTPException(404, f"PDF not found: {pdf}")
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@app.get("/api/recommendation")
def recommendation(pdf: str, number: str):
    try:
        return common.get_recommendation(pdf, number)
    except FileNotFoundError:
        raise HTTPException(404, f"PDF not found: {pdf}")
    except KeyError:
        raise HTTPException(404, f"Recommendation not found: {number}")
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@app.get("/api/ansible")
def ansible_status(pdf: str, number: str):
    return common.get_ansible(pdf, number)


@app.post("/api/ansible")
def ansible_start(req: AnsibleRequest):
    try:
        return common.start_ansible(req.pdf, req.number)
    except FileNotFoundError:
        raise HTTPException(404, f"PDF not found: {req.pdf}")
    except KeyError:
        raise HTTPException(404, f"Recommendation not found: {req.number}")
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/who")
def who():
    return {"name": APP_NAME, "path": str(Path(__file__).parent.resolve())}
