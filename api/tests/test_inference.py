"""Unit tests for api.inference.OllamaAdapter.

All HTTP traffic to Ollama is intercepted via respx — no real network calls.
Covers:
  * is_ready() — true iff GET /api/tags returns 200 AND lists our model
  * list_models() — passthrough of /api/tags 'models' array
  * chat_completion_stream() — SSE framing, terminator, model override
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from api.inference import OllamaAdapter, OllamaUnavailable

BASE_URL = "http://model:11434"
DEFAULT_MODEL = "llama4:scout"


# ---------------------------------------------------------------------------
# is_ready
# ---------------------------------------------------------------------------


@respx.mock
async def test_is_ready_true_when_model_listed() -> None:
    respx.get(f"{BASE_URL}/api/tags").mock(
        return_value=httpx.Response(
            200,
            json={"models": [{"name": "llama4:scout", "size": 67_000_000_000}]},
        )
    )
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    assert await adapter.is_ready() is True


@respx.mock
async def test_is_ready_false_when_model_missing() -> None:
    respx.get(f"{BASE_URL}/api/tags").mock(
        return_value=httpx.Response(
            200,
            json={"models": [{"name": "llama3.2:3b", "size": 2_000_000_000}]},
        )
    )
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    assert await adapter.is_ready() is False


@respx.mock
async def test_is_ready_false_when_models_list_empty() -> None:
    respx.get(f"{BASE_URL}/api/tags").mock(return_value=httpx.Response(200, json={"models": []}))
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    assert await adapter.is_ready() is False


@respx.mock
async def test_is_ready_false_on_http_error() -> None:
    """Ollama still warming up, not yet listening — treat as not-ready, not crash."""
    respx.get(f"{BASE_URL}/api/tags").mock(side_effect=httpx.ConnectError("refused"))
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    assert await adapter.is_ready() is False


@respx.mock
async def test_is_ready_false_on_5xx() -> None:
    respx.get(f"{BASE_URL}/api/tags").mock(return_value=httpx.Response(500, json={"error": "boom"}))
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    assert await adapter.is_ready() is False


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------


@respx.mock
async def test_list_models_returns_array_unchanged() -> None:
    models = [
        {"name": "llama4:scout", "size": 67_000_000_000},
        {"name": "llama3.2:3b", "size": 2_000_000_000},
    ]
    respx.get(f"{BASE_URL}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": models})
    )
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    result = await adapter.list_models()
    assert result == models


@respx.mock
async def test_list_models_returns_empty_list_when_none_resident() -> None:
    respx.get(f"{BASE_URL}/api/tags").mock(return_value=httpx.Response(200, json={"models": []}))
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    assert await adapter.list_models() == []


# ---------------------------------------------------------------------------
# chat_completion_stream
# ---------------------------------------------------------------------------


def _ollama_chunk(content: str, done: bool = False) -> bytes:
    """Build one NDJSON line as Ollama emits on POST /api/chat (stream=true)."""
    return (
        json.dumps({"message": {"role": "assistant", "content": content}, "done": done}) + "\n"
    ).encode()


@respx.mock
async def test_chat_completion_stream_emits_sse_frames_and_done() -> None:
    body = _ollama_chunk("hello", done=False) + _ollama_chunk(" world", done=True)
    respx.post(f"{BASE_URL}/api/chat").mock(return_value=httpx.Response(200, content=body))
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    messages = [{"role": "user", "content": "say hi"}]

    chunks: list[bytes] = []
    async for chunk in adapter.chat_completion_stream(messages):
        chunks.append(chunk)

    joined = b"".join(chunks)
    # Each Ollama NDJSON line becomes one SSE 'data:' frame.
    assert b"data: " in joined
    assert b"hello" in joined
    assert b" world" in joined
    # Terminates with the SSE done sentinel.
    assert joined.endswith(b"data: [DONE]\n\n")


@respx.mock
async def test_chat_completion_stream_uses_model_override_when_provided() -> None:
    """If the caller supplies model=, the adapter MUST forward that instead of
    the default. REQ-INFRA-004 evidence."""
    route = respx.post(f"{BASE_URL}/api/chat").mock(
        return_value=httpx.Response(200, content=_ollama_chunk("ok", done=True))
    )
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)

    async for _ in adapter.chat_completion_stream(
        [{"role": "user", "content": "hi"}], model="llama3.2:3b"
    ):
        pass

    assert route.called
    sent_body = json.loads(route.calls.last.request.content)
    assert sent_body["model"] == "llama3.2:3b"
    assert sent_body["stream"] is True
    assert sent_body["messages"] == [{"role": "user", "content": "hi"}]


@respx.mock
async def test_chat_completion_stream_falls_back_to_default_model() -> None:
    route = respx.post(f"{BASE_URL}/api/chat").mock(
        return_value=httpx.Response(200, content=_ollama_chunk("ok", done=True))
    )
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)

    async for _ in adapter.chat_completion_stream([{"role": "user", "content": "hi"}]):
        pass

    sent_body = json.loads(route.calls.last.request.content)
    assert sent_body["model"] == DEFAULT_MODEL


@respx.mock
async def test_adapter_respects_model_env_via_constructor() -> None:
    """REQ-INFRA-004: the MODEL env var flows in via constructor and is what
    is_ready/chat default to. No code change required to swap."""
    respx.get(f"{BASE_URL}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "llama3.2:3b", "size": 0}]})
    )
    adapter = OllamaAdapter(BASE_URL, "llama3.2:3b")
    assert await adapter.is_ready() is True
    assert adapter.model == "llama3.2:3b"


def test_adapter_strips_trailing_slash_from_base_url() -> None:
    adapter = OllamaAdapter("http://model:11434/", DEFAULT_MODEL)
    assert adapter.base_url == "http://model:11434"


@pytest.mark.parametrize("base", ["http://model:11434", "http://model:11434/"])
def test_adapter_constructor_normalises_base(base: str) -> None:
    adapter = OllamaAdapter(base, DEFAULT_MODEL)
    assert not adapter.base_url.endswith("/")


# ---------------------------------------------------------------------------
# Defensive branches
# ---------------------------------------------------------------------------


@respx.mock
async def test_is_ready_false_when_response_body_is_not_json() -> None:
    """Ollama returned 200 but the body is unparseable — treat as not-ready."""
    respx.get(f"{BASE_URL}/api/tags").mock(
        return_value=httpx.Response(200, content=b"not json at all")
    )
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    assert await adapter.is_ready() is False


# ---------------------------------------------------------------------------
# Upstream failure mapping — WARNING-1 (list_models) and WARNING-2 (chat stream)
# ---------------------------------------------------------------------------


@respx.mock
async def test_list_models_maps_ollama_5xx_to_ollama_unavailable() -> None:
    """5xx from Ollama must surface as OllamaUnavailable carrying the status."""
    respx.get(f"{BASE_URL}/api/tags").mock(
        return_value=httpx.Response(503, text="service overloaded")
    )
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    with pytest.raises(OllamaUnavailable) as exc_info:
        await adapter.list_models()
    assert exc_info.value.upstream_status == 503
    assert "service overloaded" in exc_info.value.reason


@respx.mock
async def test_list_models_maps_connect_error_to_ollama_unavailable() -> None:
    """ConnectError must surface as OllamaUnavailable with upstream_status=None."""
    respx.get(f"{BASE_URL}/api/tags").mock(side_effect=httpx.ConnectError("refused"))
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    with pytest.raises(OllamaUnavailable) as exc_info:
        await adapter.list_models()
    assert exc_info.value.upstream_status is None
    assert "refused" in exc_info.value.reason


@respx.mock
async def test_list_models_maps_timeout_to_ollama_unavailable() -> None:
    """TimeoutException must also map to OllamaUnavailable with None status."""
    respx.get(f"{BASE_URL}/api/tags").mock(side_effect=httpx.ReadTimeout("slow"))
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    with pytest.raises(OllamaUnavailable) as exc_info:
        await adapter.list_models()
    assert exc_info.value.upstream_status is None


@respx.mock
async def test_list_models_4xx_propagates_unchanged() -> None:
    """4xx is a caller-side bug, NOT service unavailability — propagate as-is."""
    respx.get(f"{BASE_URL}/api/tags").mock(
        return_value=httpx.Response(404, json={"error": "not found"})
    )
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await adapter.list_models()
    # Specifically NOT OllamaUnavailable.
    assert not isinstance(exc_info.value, OllamaUnavailable)
    assert exc_info.value.response.status_code == 404


@respx.mock
async def test_chat_completion_stream_pre_stream_5xx_raises_ollama_unavailable() -> None:
    """Pre-stream 5xx must raise OllamaUnavailable before any yield."""
    respx.post(f"{BASE_URL}/api/chat").mock(return_value=httpx.Response(503, text="model busy"))
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    gen = adapter.chat_completion_stream([{"role": "user", "content": "hi"}])
    with pytest.raises(OllamaUnavailable) as exc_info:
        await gen.__anext__()
    assert exc_info.value.upstream_status == 503


@respx.mock
async def test_chat_completion_stream_pre_stream_connect_error_raises_ollama_unavailable() -> None:
    """Pre-stream connect error must raise OllamaUnavailable before any yield."""
    respx.post(f"{BASE_URL}/api/chat").mock(side_effect=httpx.ConnectError("refused"))
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    gen = adapter.chat_completion_stream([{"role": "user", "content": "hi"}])
    with pytest.raises(OllamaUnavailable) as exc_info:
        await gen.__anext__()
    assert exc_info.value.upstream_status is None


@respx.mock
async def test_chat_completion_stream_mid_stream_error_yields_error_frame() -> None:
    """If the stream breaks mid-flight (after 200 OK), the generator MUST yield
    an in-band error frame followed by [DONE] — never raise across the
    FastAPI boundary, otherwise the client gets a truncated SSE response."""

    # Use a custom byte stream that raises partway through iteration.
    class BrokenByteStream:
        def __init__(self) -> None:
            self._chunks = [_ollama_chunk("hello", done=False)]
            self._idx = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._idx < len(self._chunks):
                chunk = self._chunks[self._idx]
                self._idx += 1
                return chunk
            raise httpx.ReadError("connection reset by peer")

        async def aclose(self) -> None:
            return None

    respx.post(f"{BASE_URL}/api/chat").mock(
        return_value=httpx.Response(200, stream=BrokenByteStream())
    )
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)

    chunks: list[bytes] = []
    async for chunk in adapter.chat_completion_stream([{"role": "user", "content": "x"}]):
        chunks.append(chunk)

    joined = b"".join(chunks)
    # First chunk delivered normally.
    assert b"hello" in joined
    # An in-band error frame appears.
    assert b'data: {"error": "upstream stream broken"}\n\n' in joined
    # And the stream terminates cleanly with the [DONE] sentinel.
    assert joined.endswith(b"data: [DONE]\n\n")


@respx.mock
async def test_chat_completion_stream_4xx_pre_stream_propagates_unchanged() -> None:
    """4xx during the pre-stream phase is a caller-side bug — propagate the
    httpx.HTTPStatusError, do NOT wrap as OllamaUnavailable."""
    respx.post(f"{BASE_URL}/api/chat").mock(
        return_value=httpx.Response(400, json={"error": "bad request"})
    )
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    gen = adapter.chat_completion_stream([{"role": "user", "content": "hi"}])
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await gen.__anext__()
    assert not isinstance(exc_info.value, OllamaUnavailable)
    assert exc_info.value.response.status_code == 400


@respx.mock
async def test_chat_completion_stream_skips_blank_lines() -> None:
    """Ollama keep-alive newlines between NDJSON records must be skipped, not
    forwarded as empty SSE frames."""
    body = (
        b"\n"  # leading blank
        + _ollama_chunk("hi", done=False)
        + b"\n"  # blank between
        + _ollama_chunk("there", done=True)
    )
    respx.post(f"{BASE_URL}/api/chat").mock(return_value=httpx.Response(200, content=body))
    adapter = OllamaAdapter(BASE_URL, DEFAULT_MODEL)
    chunks: list[bytes] = []
    async for chunk in adapter.chat_completion_stream([{"role": "user", "content": "x"}]):
        chunks.append(chunk)
    # No empty "data: \n\n" frames (would be 7 bytes).
    assert all(len(c) > len(b"data: \n\n") for c in chunks if c != b"data: [DONE]\n\n")
    assert b"hi" in b"".join(chunks)
    assert b"there" in b"".join(chunks)
