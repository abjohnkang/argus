"""FastAPI application factory for Argus.

Wires the three v1 routes (/health, /v1/models, /v1/chat/completions),
constructs the Ollama adapter from environment variables at factory time,
and starts a background poller that flips ``ReadinessTracker`` from
LOADING to READY once Ollama reports the configured model is resident.

@MX:NOTE: Readiness state machine — REQ-INFRA-003 contract.
/health returns 503 {"status":"loading"} until the background poller calls
``tracker.mark_ready()``, after which it returns 200 {"status":"ready"}.
Do NOT collapse this into a single boolean "is_up" check: the loading
state is part of the cold-start UX (Scenario 2 in acceptance.md). Adding
a third state requires amending SPEC-INFRA-001 REQ-INFRA-003 first.

@MX:NOTE: LocalhostOnlyMiddleware below enforces REQ-INFRA-005. The v1
threat model is intentionally a two-layer defense:
  1. Docker port mapping 127.0.0.1:8000:8000 in docker-compose.yml — the
     kernel never accepts a connection from a non-loopback interface.
  2. This middleware rejects any request whose Host or Origin header
     points outside localhost — protects against DNS rebinding and a
     misconfigured reverse proxy bypassing layer 1.
There is NO bearer-token auth in v1 by design; layers 1+2 together are
the v1 threat model. Adding bearer auth requires amending the SPEC.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.inference import OllamaAdapter, OllamaUnavailable
from api.security import extract_origin_host, is_localhost_header
from api.state import ReadinessState, ReadinessTracker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Request models — inline per scope rules (no separate models.py module)
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None
    stream: bool = True


# ---------------------------------------------------------------------------
# Middleware (REQ-INFRA-005) — see @MX:NOTE above for threat model context
# ---------------------------------------------------------------------------


class LocalhostOnlyMiddleware(BaseHTTPMiddleware):
    """Reject any request whose Host or Origin header is not localhost.

    Pure header inspection — no DNS, no socket peek. The two helper
    functions in ``api.security`` are the single source of truth for what
    counts as 'localhost'.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        host_header = request.headers.get("host", "")
        if not is_localhost_header(host_header):
            logger.warning(
                "rejected non-localhost request: host=%s path=%s",
                host_header,
                request.url.path,
            )
            return JSONResponse(
                status_code=403,
                content={"error": "non-localhost host", "host": host_header},
            )

        origin_header = request.headers.get("origin")
        if origin_header:
            origin_host = extract_origin_host(origin_header)
            if not is_localhost_header(origin_host):
                logger.warning(
                    "rejected non-localhost request: origin=%s path=%s",
                    origin_header,
                    request.url.path,
                )
                return JSONResponse(
                    status_code=403,
                    content={"error": "non-localhost origin", "origin": origin_header},
                )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Background readiness poller
# ---------------------------------------------------------------------------


async def _readiness_poller(
    adapter: OllamaAdapter,
    tracker: ReadinessTracker,
    interval_seconds: float,
) -> None:
    """Poll the adapter until it reports ready, then mark the tracker."""
    while True:
        try:
            if await adapter.is_ready():
                await tracker.mark_ready()
                logger.info("model %s is ready", adapter.model)
                return
        except Exception as exc:  # noqa: BLE001 — never let poller die
            logger.warning("readiness poll failed: %s", exc)
        await asyncio.sleep(interval_seconds)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(*, start_poller: bool = True) -> FastAPI:
    """Build a FastAPI app, wired to a fresh adapter + tracker.

    ``start_poller=False`` is for unit tests — they replace the adapter on
    app.state and don't want a background coroutine racing them.
    """
    ollama_host = os.environ.get("OLLAMA_HOST", "http://model:11434")
    model = os.environ.get("MODEL", "llama4:scout")
    poll_interval = float(os.environ.get("POLL_INTERVAL_SECONDS", "2.0"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        poller_task: asyncio.Task | None = None
        if start_poller:
            poller_task = asyncio.create_task(
                _readiness_poller(app.state.adapter, app.state.readiness, poll_interval)
            )
        try:
            yield
        finally:
            if poller_task is not None:
                poller_task.cancel()
                try:
                    await poller_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

    app = FastAPI(title="Argus", version="0.1.0", lifespan=lifespan)
    app.state.adapter = OllamaAdapter(base_url=ollama_host, model=model)
    app.state.readiness = ReadinessTracker()
    app.add_middleware(LocalhostOnlyMiddleware)

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/health")
    async def health() -> JSONResponse:
        state = await app.state.readiness.current_state()
        if state is ReadinessState.READY:
            return JSONResponse(status_code=200, content={"status": "ready"})
        return JSONResponse(status_code=503, content={"status": "loading"})

    @app.get("/v1/models")
    async def list_models() -> JSONResponse:
        try:
            models = await app.state.adapter.list_models()
        except OllamaUnavailable as exc:
            # Upstream Ollama is unreachable or returned 5xx — surface as a
            # 502 Bad Gateway so callers can distinguish 'argus broken' from
            # 'model service broken'.
            logger.warning(
                "ollama unavailable on /v1/models: status=%s reason=%s",
                exc.upstream_status,
                exc.reason,
            )
            return JSONResponse(
                status_code=502,
                content={
                    "error": "upstream model service unavailable",
                    "upstream_status": exc.upstream_status,
                },
            )
        return JSONResponse(status_code=200, content={"models": models})

    @app.post("/v1/chat/completions")
    async def chat_completions(body: ChatCompletionRequest):
        messages = [m.model_dump() for m in body.messages]
        # @MX:NOTE: We must drive the async generator past its pre-stream
        # phase BEFORE returning StreamingResponse. Otherwise an
        # OllamaUnavailable raised during the pre-stream phase would surface
        # as an exception inside Starlette's streaming machinery — too late
        # to translate into a 502 status code.
        stream = app.state.adapter.chat_completion_stream(messages, model=body.model)
        try:
            first_chunk = await stream.__anext__()
        except OllamaUnavailable as exc:
            logger.warning(
                "ollama unavailable on /v1/chat/completions pre-stream: " "status=%s reason=%s",
                exc.upstream_status,
                exc.reason,
            )
            return JSONResponse(
                status_code=502,
                content={
                    "error": "upstream model service unavailable",
                    "upstream_status": exc.upstream_status,
                },
            )
        except StopAsyncIteration:
            # Generator produced no chunks at all — empty stream. Send just
            # the [DONE] sentinel so the client sees a clean termination.
            async def _empty_stream():
                yield b"data: [DONE]\n\n"

            return StreamingResponse(_empty_stream(), media_type="text/event-stream")

        async def _streamed():
            yield first_chunk
            async for chunk in stream:
                yield chunk

        return StreamingResponse(_streamed(), media_type="text/event-stream")

    return app


# Module-level app for ``uvicorn api.main:app`` invocation. Lazily built so
# importing the module under test doesn't spin up a poller.
_app: FastAPI | None = None


def __getattr__(name: str):
    """Lazy ``app`` attribute — uvicorn's import path stays clean."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
