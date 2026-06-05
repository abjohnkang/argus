"""Thin adapter over the Ollama HTTP API (REQ-INFRA-003, REQ-INFRA-004).

@MX:ANCHOR: OllamaAdapter is the single boundary between Argus and the model
runtime. Every downstream feature (UI, agent tools, memory) talks to this
class — never to Ollama directly. When v2 swaps the runtime to llama.cpp or
vLLM, only this file changes; the rest of the codebase keeps working.
@MX:REASON: Runtime swap boundary; high future fan_in across downstream
features (UI client, agent orchestrator, retrieval). Pinning the contract
here is what makes the runtime change a single-file edit instead of a
codebase-wide refactor.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx

logger = logging.getLogger(__name__)


# @MX:ANCHOR: OllamaUnavailable is the domain-specific signal that the upstream
# model runtime is unreachable or returning 5xx. Route handlers translate this
# to HTTP 502 Bad Gateway instead of leaking httpx exceptions as opaque 500s.
# @MX:REASON: Cross-cutting failure boundary used by both list_models() and
# chat_completion_stream() pre-stream phases AND by both /v1/models and
# /v1/chat/completions route handlers — fan_in >= 4 and growing as more
# adapter methods are added.
class OllamaUnavailable(RuntimeError):
    """Upstream Ollama service is unreachable or returned 5xx.

    Carries the upstream HTTP status when available (None for connect/timeout
    errors where no response was received) and a short human-readable reason.
    """

    def __init__(self, upstream_status: int | None, reason: str) -> None:
        self.upstream_status = upstream_status
        self.reason = reason
        super().__init__(f"Ollama upstream unavailable ({upstream_status}): {reason}")


class OllamaAdapter:
    """HTTP client wrapper for Ollama (GET /api/tags, POST /api/chat).

    Construction is cheap; one ``OllamaAdapter`` is created per process at
    app-factory time and shared across requests. The adapter owns no
    long-lived ``httpx.AsyncClient`` — each call opens its own client so
    test fixtures (respx) intercept cleanly and we never leak a connection
    across event loops.
    """

    # Generous timeout because /api/chat may stream for tens of seconds on
    # a long completion. /api/tags is fast so it falls under the same cap.
    _DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url: str = base_url.rstrip("/")
        self.model: str = model

    async def is_ready(self) -> bool:
        """Return True iff Ollama responds 200 to /api/tags AND lists our model.

        Any transport error or non-200 status is treated as not-ready (not as
        a crash). This is what lets the background poller in ``api/main.py``
        survive Ollama still warming up at cold start.

        @MX:WARN: This path is also implicitly exercised during the initial
        model pull. A 32-67 GB Scout pull may take an hour over a slow link;
        callers MUST treat ``False`` as 'try again later', NEVER as 'restart
        Ollama'. The pull resume contract is owned by Ollama itself — we
        intentionally do NOT add wrapper retry logic that would defeat the
        native resume behavior.
        @MX:REASON: 32-67 GB pull at full Scout size; partial-state risk if
        interrupted; resume contract is Ollama-native; do not add wrapper
        retries that would re-trigger pulls from zero.
        """
        try:
            async with httpx.AsyncClient(timeout=self._DEFAULT_TIMEOUT) as client:
                response = await client.get(f"{self.base_url}/api/tags")
        except httpx.HTTPError as exc:
            logger.debug("ollama not reachable yet: %s", exc)
            return False
        if response.status_code != 200:
            return False
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return False
        models = payload.get("models", [])
        return any(m.get("name") == self.model for m in models)

    async def list_models(self) -> list[dict]:
        """Return the ``models`` array from Ollama /api/tags unchanged.

        Raises ``OllamaUnavailable`` when Ollama returns 5xx or the connection
        cannot be established (connect error / timeout). 4xx responses are
        re-raised unchanged via ``httpx.HTTPStatusError`` — those indicate a
        caller-side bug (e.g., wrong endpoint), not service unavailability.
        """
        try:
            async with httpx.AsyncClient(timeout=self._DEFAULT_TIMEOUT) as client:
                response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                raise OllamaUnavailable(exc.response.status_code, exc.response.text[:200]) from exc
            raise  # 4xx — propagate as the caller-side bug it is
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise OllamaUnavailable(None, str(exc)) from exc
        return response.json().get("models", [])

    async def chat_completion_stream(
        self, messages: list[dict], model: str | None = None
    ) -> AsyncIterator[bytes]:
        """Stream a chat completion as SSE bytes.

        Each Ollama NDJSON line on /api/chat (stream=true) is wrapped as a
        single ``data: <json>\\n\\n`` SSE frame. The stream terminates with
        the sentinel frame ``data: [DONE]\\n\\n`` so EventSource clients can
        cleanly close.

        ``model`` overrides the adapter default (REQ-INFRA-004 — caller-side
        model selection without rebuilding the adapter).

        Error contract (two phases):
          * Pre-stream (initial connect / first response): if Ollama returns
            5xx, or the connection cannot be established, raise
            ``OllamaUnavailable`` BEFORE yielding anything. The route handler
            catches this and returns 502 instead of a StreamingResponse.
          * Mid-stream (response was 200 but the connection breaks while
            iterating): yield a final error frame plus the ``[DONE]`` sentinel
            and swallow the exception. The async generator MUST NOT raise
            across the FastAPI boundary once streaming has begun, otherwise
            the client sees a truncated SSE response.
        """
        effective_model = model or self.model
        request_body = {
            "model": effective_model,
            "messages": messages,
            "stream": True,
        }

        # @MX:WARN: Two-phase error handling — pre-stream failures must raise
        # before yielding anything, mid-stream failures must yield an error
        # frame and swallow. Conflating the two phases produces opaque
        # truncated SSE responses to the client.
        # @MX:REASON: FastAPI cannot translate an exception raised mid-stream
        # into an HTTP error code — the response status has already been sent.
        # The only way to communicate failure mid-stream is in-band via SSE.
        client = httpx.AsyncClient(timeout=self._DEFAULT_TIMEOUT)
        stream_ctx = None
        response = None
        try:
            stream_ctx = client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=request_body,
            )
            try:
                response = await stream_ctx.__aenter__()
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                # Pre-stream failure: never got a response.
                raise OllamaUnavailable(None, str(exc)) from exc

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Pre-stream failure: server replied with 4xx/5xx.
                if exc.response.status_code >= 500:
                    raise OllamaUnavailable(
                        exc.response.status_code,
                        "upstream returned 5xx on /api/chat",
                    ) from exc
                raise  # 4xx — caller bug, propagate
        except BaseException:
            # Any pre-stream failure: tear down the stream context (if it was
            # entered) and the client, then re-raise so the route handler can
            # translate to 502.
            if response is not None and stream_ctx is not None:
                try:
                    await stream_ctx.__aexit__(None, None, None)
                except Exception:  # noqa: BLE001
                    pass
            await client.aclose()
            raise

        # We're inside the stream now — any error from here on must be
        # converted to an in-band SSE error frame, not raised.
        try:
            try:
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    # Pass the raw Ollama JSON through as the SSE data
                    # payload. Downstream consumers parse JSON themselves;
                    # we deliberately don't reshape it here.
                    yield f"data: {line}\n\n".encode()
            except Exception as exc:  # noqa: BLE001 — must not raise mid-stream
                logger.warning("ollama stream broken mid-flight: %s", exc)
                yield b'data: {"error": "upstream stream broken"}\n\n'
            finally:
                try:
                    await stream_ctx.__aexit__(None, None, None)
                except Exception:  # noqa: BLE001
                    pass
        finally:
            await client.aclose()
        yield b"data: [DONE]\n\n"
