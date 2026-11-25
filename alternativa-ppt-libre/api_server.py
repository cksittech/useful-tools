from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import common
from data import APP_NAME, GenerateRequest

app = FastAPI()

# Only the GitHub Pages copy and index.html opened as file:// (Origin "null") may call this;
# any other site open in the browser could otherwise drive this PC.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://cksittech.github.io", "null"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
def value_error_handler(_request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(common.GenerationError)
def generation_error_handler(_request: Request, exc: common.GenerationError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.post("/api/generate")
def generate(req: GenerateRequest):
    return {"markdown": common.generate_markdown(req.request, req.current)}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/who")
def who():
    return {"name": APP_NAME, "path": str(Path(__file__).parent.resolve())}
