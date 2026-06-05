"""Unit tests for FastAPI routes in api.main.

Routes tested (REQ-INFRA-001 API surface, REQ-INFRA-003 readiness):
  * GET /health           — 503 while loading, 200 when ready
  * GET /v1/models        — passthrough of adapter.list_models()
  * POST /v1/chat/completions — SSE streaming via adapter.chat_completion_stream

All requests carry ``Host: 127.0.0.1:8000`` so the localhost middleware
admits them. Middleware rejection tests live in test_middleware.py.

The adapter is replaced on app.state with an AsyncMock so we never touch
the real Ollama. The background readiness poller is also disabled
(create_app accepts start_poller=False) so tests stay deterministic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import ASGITransport

from api.main import create_app
from api.state import ReadinessState

LOCAL_HEADERS = {"Host": "127.0.0.1:8000"}


@pytest.fixture
def app():
    """A fresh app with the background poller disabled."""
    return create_app(start_poller=False)


@pytest.fixture
def mock_adapter(app):
    """Replace the live OllamaAdapter on app.state with an AsyncMock.

    ``chat_completion_stream`` is a plain ``MagicMock`` (not async): the
    real adapter method is an async generator, so calling it returns an
    async iterator directly without ``await``. AsyncMock would wrap the
    return value in a coroutine, breaking StreamingResponse.
    """
    adapter = AsyncMock()
    adapter.chat_completion_stream = MagicMock()
    app.state.adapter = adapter
    return adapter


async def _client(app):
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1:8000")


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


async def test_health_returns_503_while_loading(app, mock_adapter) -> None:
    # tracker starts in LOADING by default
    async with await _client(app) as client:
        response = await client.get("/health", headers=LOCAL_HEADERS)
    assert response.status_code == 503
    assert response.json() == {"status": "loading"}


async def test_health_returns_200_when_ready(app, mock_adapter) -> None:
    await app.state.readiness.mark_ready()
    async with await _client(app) as client:
        response = await client.get("/health", headers=LOCAL_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_health_does_not_call_adapter(app, mock_adapter) -> None:
    """/health is a pure-state check. Must NOT round-trip to Ollama."""
    async with await _client(app) as client:
        await client.get("/health", headers=LOCAL_HEADERS)
    mock_adapter.is_ready.assert_not_called()
    mock_adapter.list_models.assert_not_called()
    mock_adapter.chat_completion_stream.assert_not_called()


# ---------------------------------------------------------------------------
# /v1/models
# ---------------------------------------------------------------------------


async def test_list_models_returns_adapter_array(app, mock_adapter) -> None:
    mock_adapter.list_models.return_value = [
        {"name": "llama4:scout", "size": 67_000_000_000},
    ]
    async with await _client(app) as client:
        response = await client.get("/v1/models", headers=LOCAL_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"models": [{"name": "llama4:scout", "size": 67_000_000_000}]}
    mock_adapter.list_models.assert_awaited_once()


# ---------------------------------------------------------------------------
# /v1/chat/completions
# ---------------------------------------------------------------------------


async def _stream_chunks(*chunks: bytes):
    """Helper: build an async generator yielding the given byte chunks."""
    for c in chunks:
        yield c


async def test_chat_completions_streams_sse(app, mock_adapter) -> None:
    mock_adapter.chat_completion_stream.side_effect = lambda *a, **kw: _stream_chunks(
        b'data: {"message":{"content":"hi"},"done":false}\n\n',
        b"data: [DONE]\n\n",
    )
    async with await _client(app) as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={**LOCAL_HEADERS, "Content-Type": "application/json"},
            json={"model": "llama4:scout", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.content
    assert b"data: " in body
    assert body.endswith(b"data: [DONE]\n\n")
    mock_adapter.chat_completion_stream.assert_called_once()
    # The adapter received the messages array intact.
    call_kwargs = mock_adapter.chat_completion_stream.call_args
    args, kwargs = call_kwargs
    # Either positional or keyword — accept both.
    messages = kwargs.get("messages") or (args[0] if args else None)
    assert messages == [{"role": "user", "content": "hi"}]


# ---------------------------------------------------------------------------
# Upstream failure mapping — 502 Bad Gateway translation
# ---------------------------------------------------------------------------


async def test_list_models_endpoint_returns_502_on_ollama_unavailable(app, mock_adapter) -> None:
    """When the adapter raises OllamaUnavailable, /v1/models must return 502
    with a structured body — NOT a 500 traceback."""
    from api.inference import OllamaUnavailable

    mock_adapter.list_models.side_effect = OllamaUnavailable(503, "ollama overloaded")
    async with await _client(app) as client:
        response = await client.get("/v1/models", headers=LOCAL_HEADERS)
    assert response.status_code == 502
    payload = response.json()
    assert payload["error"] == "upstream model service unavailable"
    assert payload["upstream_status"] == 503


async def test_list_models_endpoint_returns_502_on_connect_error_unavailable(
    app, mock_adapter
) -> None:
    """upstream_status=None (connect/timeout) still maps to 502."""
    from api.inference import OllamaUnavailable

    mock_adapter.list_models.side_effect = OllamaUnavailable(None, "connection refused")
    async with await _client(app) as client:
        response = await client.get("/v1/models", headers=LOCAL_HEADERS)
    assert response.status_code == 502
    payload = response.json()
    assert payload["upstream_status"] is None


async def test_chat_completions_returns_502_when_pre_stream_fails(app, mock_adapter) -> None:
    """If chat_completion_stream raises OllamaUnavailable on its first
    iteration, the endpoint must return 502 JSON — NOT a StreamingResponse."""
    from api.inference import OllamaUnavailable

    async def _failing_stream(*args, **kwargs):
        raise OllamaUnavailable(503, "model busy")
        yield  # pragma: no cover — make this an async generator

    mock_adapter.chat_completion_stream.side_effect = lambda *a, **kw: _failing_stream()
    async with await _client(app) as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={**LOCAL_HEADERS, "Content-Type": "application/json"},
            json={"model": "llama4:scout", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 502
    assert not response.headers["content-type"].startswith("text/event-stream")
    payload = response.json()
    assert payload["error"] == "upstream model service unavailable"
    assert payload["upstream_status"] == 503


async def test_chat_completions_returns_502_on_pre_stream_connect_error(app, mock_adapter) -> None:
    """Connect-error pre-stream failure also returns 502 (upstream_status=None)."""
    from api.inference import OllamaUnavailable

    async def _failing_stream(*args, **kwargs):
        raise OllamaUnavailable(None, "ollama refused")
        yield  # pragma: no cover

    mock_adapter.chat_completion_stream.side_effect = lambda *a, **kw: _failing_stream()
    async with await _client(app) as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={**LOCAL_HEADERS, "Content-Type": "application/json"},
            json={"model": "llama4:scout", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 502
    assert response.json()["upstream_status"] is None


async def test_chat_completions_empty_generator_returns_done_sentinel(app, mock_adapter) -> None:
    """Edge case: a generator that yields nothing before StopAsyncIteration
    must still produce a clean SSE response with the [DONE] sentinel."""

    async def _empty_generator(*args, **kwargs):
        return
        yield  # pragma: no cover

    mock_adapter.chat_completion_stream.side_effect = lambda *a, **kw: _empty_generator()
    async with await _client(app) as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={**LOCAL_HEADERS, "Content-Type": "application/json"},
            json={"model": "llama4:scout", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.content == b"data: [DONE]\n\n"


async def test_chat_completions_forwards_model_override(app, mock_adapter) -> None:
    mock_adapter.chat_completion_stream.side_effect = lambda *a, **kw: _stream_chunks(
        b"data: [DONE]\n\n"
    )
    async with await _client(app) as client:
        await client.post(
            "/v1/chat/completions",
            headers={**LOCAL_HEADERS, "Content-Type": "application/json"},
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    args, kwargs = mock_adapter.chat_completion_stream.call_args
    forwarded_model = kwargs.get("model")
    assert forwarded_model == "llama3.2:3b"


# ---------------------------------------------------------------------------
# create_app wiring
# ---------------------------------------------------------------------------


def test_create_app_reads_env_for_model_override(monkeypatch) -> None:
    monkeypatch.setenv("MODEL", "llama3.2:1b")
    monkeypatch.setenv("OLLAMA_HOST", "http://other-host:11434")
    app = create_app(start_poller=False)
    assert app.state.adapter.model == "llama3.2:1b"
    assert app.state.adapter.base_url == "http://other-host:11434"


def test_create_app_initial_state_is_loading() -> None:
    app = create_app(start_poller=False)
    assert isinstance(app.state.readiness.current_state, type(app.state.readiness.current_state))
    # The tracker exists and starts LOADING — verify via the sentinel enum.
    assert app.state.readiness._state is ReadinessState.LOADING  # noqa: SLF001


# ---------------------------------------------------------------------------
# Readiness poller (background task)
# ---------------------------------------------------------------------------


async def test_readiness_poller_marks_ready_when_adapter_returns_true() -> None:
    """Poller flips the tracker exactly once and then exits."""
    from api.main import _readiness_poller
    from api.state import ReadinessState, ReadinessTracker

    adapter = AsyncMock()
    adapter.is_ready.return_value = True
    adapter.model = "test-model"
    tracker = ReadinessTracker()

    await _readiness_poller(adapter, tracker, interval_seconds=0.001)
    assert await tracker.current_state() is ReadinessState.READY


async def test_readiness_poller_retries_until_ready() -> None:
    """Poller keeps polling while adapter reports not-ready, then marks."""
    import asyncio

    from api.main import _readiness_poller
    from api.state import ReadinessState, ReadinessTracker

    adapter = AsyncMock()
    adapter.is_ready.side_effect = [False, False, True]
    adapter.model = "test-model"
    tracker = ReadinessTracker()

    await asyncio.wait_for(
        _readiness_poller(adapter, tracker, interval_seconds=0.001),
        timeout=2.0,
    )
    assert await tracker.current_state() is ReadinessState.READY
    assert adapter.is_ready.await_count == 3


async def test_readiness_poller_survives_adapter_exceptions() -> None:
    """A transient exception in adapter.is_ready must NOT kill the poller."""
    import asyncio

    from api.main import _readiness_poller
    from api.state import ReadinessState, ReadinessTracker

    adapter = AsyncMock()
    adapter.is_ready.side_effect = [RuntimeError("transient boom"), True]
    adapter.model = "test-model"
    tracker = ReadinessTracker()

    await asyncio.wait_for(
        _readiness_poller(adapter, tracker, interval_seconds=0.001),
        timeout=2.0,
    )
    assert await tracker.current_state() is ReadinessState.READY


# ---------------------------------------------------------------------------
# Lifespan (startup/shutdown) — exercises the asynccontextmanager body
# ---------------------------------------------------------------------------


async def test_lifespan_starts_and_cancels_poller() -> None:
    """With start_poller=True, the lifespan must spawn and cancel the task."""
    from unittest.mock import patch

    app = create_app(start_poller=True)
    # Replace adapter so the poller doesn't actually try to reach Ollama.
    fake_adapter = AsyncMock()
    fake_adapter.is_ready.return_value = False  # never goes ready
    fake_adapter.model = "fake"
    app.state.adapter = fake_adapter

    # Speed up the poller so the test exits fast.
    with patch("api.main.asyncio.sleep", new=AsyncMock(return_value=None)):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://127.0.0.1:8000"
        ) as client:
            response = await client.get("/health", headers=LOCAL_HEADERS)
        assert response.status_code == 503
    # Shutdown side of the lifespan ran; no exception escaped.


# ---------------------------------------------------------------------------
# Module-level __getattr__ — uvicorn import path
# ---------------------------------------------------------------------------


def test_module_attribute_app_returns_fastapi_instance(monkeypatch) -> None:
    """``import api.main; api.main.app`` must work for uvicorn."""
    import api.main as main_module

    # Reset the cached lazy app so the test is hermetic.
    monkeypatch.setattr(main_module, "_app", None)
    instance = main_module.app  # triggers __getattr__
    assert instance is not None
    assert instance.title == "Argus"


def test_module_getattr_raises_for_unknown_names() -> None:
    import api.main as main_module

    with pytest.raises(AttributeError):
        _ = main_module.does_not_exist  # type: ignore[attr-defined]
