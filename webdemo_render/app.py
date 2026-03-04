from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import random
import sys
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import Client as LLM_Client
from starlette.requests import Request

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from graph.graph import I2OGraph  # noqa: E402
from graph.state import GraphState  # noqa: E402

load_dotenv()

ALLOWED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
EXAMPLES_DIR = Path(__file__).resolve().parent / "example_images"


@dataclass
class JobState:
    status: str = "queued"
    events: list[dict[str, Any]] = field(default_factory=list)
    result: list[dict[str, Any]] | None = None
    error: str | None = None
    done: bool = False
    version: int = 0
    condition: threading.Condition = field(default_factory=threading.Condition)

    def add_event(self, event_type: str, payload: dict[str, Any]) -> None:
        with self.condition:
            self.events.append({"type": event_type, "payload": payload})
            self.version += 1
            self.condition.notify_all()

    def mark_done(self, status: str) -> None:
        with self.condition:
            self.status = status
            self.done = True
            self.version += 1
            self.condition.notify_all()

    def wait_for_change(self, known_version: int, timeout: float = 15.0) -> None:
        with self.condition:
            if self.version == known_version and not self.done:
                self.condition.wait(timeout=timeout)


class TraceWriter(io.TextIOBase):
    def __init__(self, on_line: Any) -> None:
        self._on_line = on_line
        self._buffer = ""

    def write(self, data: str) -> int:
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            cleaned = line.strip()
            if cleaned:
                self._on_line(cleaned)
        return len(data)

    def flush(self) -> None:
        if self._buffer.strip():
            self._on_line(self._buffer.strip())
        self._buffer = ""


app = FastAPI(title="image2offer web demo")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
    name="static",
)
app.mount(
    "/examples",
    StaticFiles(directory=str(EXAMPLES_DIR), check_dir=False),
    name="examples",
)

jobs: dict[str, JobState] = {}
jobs_lock = threading.Lock()


def _emit_status(job: JobState, status: str, message: str) -> None:
    job.status = status
    job.add_event("status", {"status": status, "message": message})


def _run_pipeline_job(job_id: str, image_bytes: bytes, image_mime_type: str, offer_country: str) -> None:
    with jobs_lock:
        job = jobs[job_id]

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        job.error = "OPENAI_API_KEY is not configured."
        job.add_event("error", {"message": job.error})
        job.mark_done("error")
        return

    _emit_status(job, "running", "Initializing model client...")
    openai_client = LLM_Client(api_key=api_key)
    graph = I2OGraph(
        llm_client=openai_client,
        CHECK_IMAGE_BEFORE_RUN=True,
        SEARCH_PRODUCT_IMAGE_ONLINE=False,
    )
    initial_state = GraphState(
        messages=[],
        warnings=[],
        product_image_urls=[],
        image=image_bytes,
        image_mime_type=image_mime_type,
        offer_country=offer_country,
        image_check_model_name="gpt-5-nano",
        image_decoding_model_name="gpt-5-mini",
        product_enrichment_model_name="gpt-4o",
        product_image_search_model_name="gpt-4o",
        final_offer_composition_model_name="gpt-5-mini",
    )

    def on_trace_line(line: str) -> None:
        job.add_event("trace", {"message": line})

    trace_writer = TraceWriter(on_trace_line)
    try:
        _emit_status(job, "running", "Running image2offer flow...")
        with contextlib.redirect_stdout(trace_writer):
            final_state = graph.invoke(initial_state)
            trace_writer.flush()
        final_offers_info = final_state.get("final_offers_info", [])
        job.result = final_offers_info
        job.add_event("result", {"result": final_offers_info})
        job.mark_done("success")
    except Exception as exc:
        error_detail = f"{type(exc).__name__}: {exc}"
        job.error = error_detail
        job.add_event("trace", {"message": traceback.format_exc()})
        job.add_event("error", {"message": error_detail})
        job.mark_done("error")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/examples/random")
async def random_example() -> dict[str, str]:
    if not EXAMPLES_DIR.exists():
        raise HTTPException(status_code=404, detail="Examples folder not found.")

    candidates = [
        path for path in EXAMPLES_DIR.iterdir() if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS
    ]
    if not candidates:
        raise HTTPException(status_code=404, detail="No example images found.")

    selected = random.choice(candidates)
    return {"url": f"/examples/{selected.name}", "filename": selected.name}


@app.post("/api/jobs")
async def create_job(
    image: UploadFile = File(...),
    offer_country: str = "unknown",
) -> dict[str, Any]:
    if image.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type.")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 10MB limit.")

    job_id = uuid.uuid4().hex
    job_state = JobState()
    job_state.add_event("status", {"status": "queued", "message": "Job queued."})
    with jobs_lock:
        jobs[job_id] = job_state

    worker = threading.Thread(
        target=_run_pipeline_job,
        args=(job_id, image_bytes, image.content_type or "image/png", offer_country),
        daemon=True,
    )
    worker.start()
    return {"job_id": job_id}


def _to_sse(event_type: str, payload: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/api/jobs/{job_id}/events")
async def stream_job_events(job_id: str) -> StreamingResponse:
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    async def event_generator() -> Any:
        cursor = 0
        seen_version = job.version
        while True:
            if cursor < len(job.events):
                event = job.events[cursor]
                cursor += 1
                yield _to_sse(event["type"], event["payload"])
                continue

            if job.done:
                break

            await asyncio.to_thread(job.wait_for_change, seen_version, 10.0)
            seen_version = job.version
            if cursor >= len(job.events) and not job.done:
                yield ": keepalive\n\n"

        if job.done and job.error:
            yield _to_sse("status", {"status": "error", "message": job.error})
        elif job.done:
            yield _to_sse("status", {"status": "success", "message": "Job finished."})

    return StreamingResponse(event_generator(), media_type="text/event-stream")
