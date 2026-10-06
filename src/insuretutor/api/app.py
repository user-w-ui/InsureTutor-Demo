"""One-process HTTP boundary for the existing Tutor and local static website."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from insuretutor.chat_models import ChatTurn, SearchProgress
from insuretutor.corpus import ROOT, Corpus
from insuretutor.generation import AgentGenerator, ModelConfig
from insuretutor.references import ChatResponse, with_references
from insuretutor.retrieval.embedding import sha256
from insuretutor.retrieval.hybrid import HybridRetriever
from insuretutor.sessions import SessionCapacityError
from insuretutor.tutor import Tutor

WEB = Path(__file__).parent.parent / "web"
PDF = ROOT / "raw data/source/FLEXI-ULife Prime Saver.pdf"
logger = logging.getLogger("insuretutor.api")


@dataclass
class Runtime:
    tutor: Tutor
    corpus: Corpus
    pdf_path: Path
    generator: AgentGenerator | None = None


def load_runtime() -> Runtime:
    retriever = HybridRetriever.from_local()
    source = retriever.corpus.provenance["source"]
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", source["source_id"]):
        raise ValueError("Invalid PDF source ID")
    if sha256(PDF) != source["source_pdf_sha256"]:
        raise ValueError("Source PDF hash mismatch")
    config = ModelConfig.from_env()
    generator = AgentGenerator.from_config(config) if config else None
    return Runtime(Tutor(retriever, generator), retriever.corpus, PDF, generator)


async def chat_events(
    runtime: Runtime, turn: ChatTurn, request_id: str, started: float, tasks: set
) -> AsyncGenerator[ServerSentEvent, None]:
    """Display-only progress, then the same validated response as /api/chat.

    The turn runs as its own task: a client disconnect stops these events but, as
    with /api/chat, the turn still completes, updates history and is logged.
    """
    queue: asyncio.Queue[ServerSentEvent] = asyncio.Queue()

    def elapsed() -> int:
        return round((time.perf_counter() - started) * 1000)

    def emit(event):
        queue.put_nowait(
            ServerSentEvent(
                event="search" if isinstance(event, SearchProgress) else "stage",
                data={**event.model_dump(exclude_none=True), "elapsed_ms": elapsed()},
            )
        )

    async def run():
        status = reason = None
        try:
            result = await runtime.tutor.answer(turn, progress=emit)
            response = with_references(result, runtime.corpus)
            status, reason = result.status, result.reason
            data = {"response": response.model_dump(mode="json"), "elapsed_ms": elapsed()}
            event = ServerSentEvent(event="final", data=data)
        except Exception as exc:  # noqa: BLE001 -- the stream already returned HTTP 200
            # Server-owned codes only; exception text may carry prompts or keys.
            code = "sessions_busy" if isinstance(exc, SessionCapacityError) else "internal_error"
            status, reason = "error", code
            data = {"code": code, "request_id": request_id, "elapsed_ms": elapsed()}
            event = ServerSentEvent(event="error", data=data)
        logger.info(
            "request=%s elapsed_ms=%.0f http=200 status=%s reason=%s stream=1",
            request_id,
            elapsed(),
            status,
            reason,
        )
        queue.put_nowait(event)

    task = asyncio.create_task(run())
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    while True:
        event = await queue.get()
        yield event
        if event.event in {"final", "error"}:
            return


def create_app(runtime_factory: Callable[[], Runtime] = load_runtime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            app.state.runtime = await asyncio.to_thread(runtime_factory)
            app.state.turn_tasks = set()  # Strong references for detached stream turns.
        except Exception:  # noqa: BLE001 -- redact startup configuration exceptions
            # Startup exceptions may carry configuration values or local paths.
            raise RuntimeError(
                "Runtime initialization failed; verify local artifacts/config"
            ) from None
        try:
            yield
        finally:
            if app.state.runtime.generator:
                await app.state.runtime.generator.close()

    app = FastAPI(title="InsureTutor", lifespan=lifespan, docs_url=None, redoc_url=None)

    def failure(request: Request, code: str, status: int):
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": code.replace("_", " "),
                    "request_id": getattr(request.state, "request_id", ""),
                }
            },
        )

    @app.middleware("http")
    async def request_metadata(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        request.state.started = started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 -- prevent payload-bearing exception logs
            response = failure(request, "internal_error", 500)
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            # Revalidate frontend assets after rebuilding the container.
            response.headers["Cache-Control"] = "no-cache"
        stream = request.url.path == "/api/chat/stream"
        if request.url.path == "/api/chat" or (stream and response.status_code != 200):
            # Accepted streams are logged by their turn task when it completes.
            logger.info(
                "request=%s elapsed_ms=%.0f http=%s status=%s reason=%s",
                request.state.request_id,
                (time.perf_counter() - started) * 1000,
                response.status_code,
                getattr(request.state, "answer_status", "error"),
                getattr(request.state, "answer_reason", None),
            )
        if request.url.path == "/api/chat" or stream:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, _exc):
        return failure(request, "invalid_input", 422)

    @app.exception_handler(SessionCapacityError)
    async def busy(request, _exc):
        return failure(request, "sessions_busy", 503)

    @app.exception_handler(HTTPException)
    async def http_failure(request, exc):
        return failure(
            request, "not_found" if exc.status_code == 404 else "request_failed", exc.status_code
        )

    @app.exception_handler(Exception)
    async def internal_failure(request, _exc):
        return failure(request, "internal_error", 500)

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(turn: ChatTurn, request: Request):
        runtime = request.app.state.runtime
        result = await runtime.tutor.answer(turn)
        response = with_references(result, runtime.corpus)
        request.state.answer_status, request.state.answer_reason = result.status, result.reason
        return response

    @app.post("/api/chat/stream", response_class=EventSourceResponse)
    async def chat_stream(turn: ChatTurn, request: Request):
        async for event in chat_events(
            request.app.state.runtime,
            turn,
            request.state.request_id,
            request.state.started,
            request.app.state.turn_tasks,
        ):
            yield event

    @app.get("/api/health")
    async def health(request: Request):
        runtime = request.app.state.runtime
        return {
            "ready": True,
            "retrieval_ready": True,
            "mode": "agent" if runtime.generator else "excerpts",
            "source_id": runtime.corpus.provenance["source"]["source_id"],
            "pdf_url": f"/sources/{runtime.corpus.provenance['source']['source_id']}.pdf",
        }

    @app.get("/sources/{source_id}.pdf")
    async def source_pdf(source_id: str, request: Request):
        runtime = request.app.state.runtime
        if source_id != runtime.corpus.provenance["source"]["source_id"]:
            raise HTTPException(404)
        return FileResponse(runtime.pdf_path, media_type="application/pdf")

    @app.get("/")
    async def index():
        return FileResponse(WEB / "index.html", media_type="text/html")

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app


app = create_app()


def main():
    import uvicorn

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    load_dotenv(ROOT / ".env", override=False)
    uvicorn.run(
        "insuretutor.api.app:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        workers=1,
        access_log=False,
    )


if __name__ == "__main__":
    main()
