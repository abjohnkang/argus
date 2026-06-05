"""Unit tests for LocalhostOnlyMiddleware (REQ-INFRA-005).

Every rejected request MUST:
  * return HTTP 403
  * include the offending header value in the JSON body
  * NOT invoke any adapter method (verified via AsyncMock.assert_not_called)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import ASGITransport

from api.main import create_app

LOCAL_HEADERS = {"Host": "127.0.0.1:8000"}


@pytest.fixture
def app():
    return create_app(start_poller=False)


@pytest.fixture
def mock_adapter(app):
    adapter = AsyncMock()
    adapter.chat_completion_stream = MagicMock()
    app.state.adapter = adapter
    return adapter


async def _client(app):
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1:8000")


# ---------------------------------------------------------------------------
# Host header rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_host",
    ["evil.example.com", "evil.example.com:8000", "0.0.0.0", "192.168.1.10", ""],
)
async def test_forged_host_returns_403(app, mock_adapter, bad_host) -> None:
    async with await _client(app) as client:
        response = await client.get("/v1/models", headers={"Host": bad_host})
    assert response.status_code == 403
    body = response.json()
    assert body["error"] == "non-localhost host"
    assert body["host"] == bad_host


async def test_forged_host_does_not_invoke_adapter(app, mock_adapter) -> None:
    """The middleware MUST short-circuit before the route runs — the most
    important invariant of REQ-INFRA-005."""
    async with await _client(app) as client:
        await client.get("/v1/models", headers={"Host": "evil.example.com"})
        await client.post(
            "/v1/chat/completions",
            headers={"Host": "evil.example.com", "Content-Type": "application/json"},
            json={"model": "x", "messages": [{"role": "user", "content": "hi"}]},
        )
    mock_adapter.list_models.assert_not_called()
    mock_adapter.chat_completion_stream.assert_not_called()
    mock_adapter.is_ready.assert_not_called()


async def test_forged_host_on_health_returns_403(app, mock_adapter) -> None:
    """Even /health (cheapest endpoint) is gated — no information leak."""
    async with await _client(app) as client:
        response = await client.get("/health", headers={"Host": "evil.example.com"})
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Origin header rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_origin",
    [
        "http://evil.example.com",
        "https://evil.example.com:443",
        "http://192.168.1.10",
    ],
)
async def test_forged_origin_returns_403(app, mock_adapter, bad_origin) -> None:
    async with await _client(app) as client:
        response = await client.get(
            "/v1/models",
            headers={**LOCAL_HEADERS, "Origin": bad_origin},
        )
    assert response.status_code == 403
    body = response.json()
    assert body["error"] == "non-localhost origin"
    assert body["origin"] == bad_origin


async def test_forged_origin_does_not_invoke_adapter(app, mock_adapter) -> None:
    async with await _client(app) as client:
        await client.get(
            "/v1/models",
            headers={**LOCAL_HEADERS, "Origin": "http://evil.example.com"},
        )
    mock_adapter.list_models.assert_not_called()


# ---------------------------------------------------------------------------
# Happy path — localhost requests pass through
# ---------------------------------------------------------------------------


async def test_localhost_request_passes_middleware(app, mock_adapter) -> None:
    mock_adapter.list_models.return_value = []
    async with await _client(app) as client:
        response = await client.get("/v1/models", headers=LOCAL_HEADERS)
    assert response.status_code == 200
    mock_adapter.list_models.assert_awaited_once()


async def test_localhost_origin_is_allowed(app, mock_adapter) -> None:
    mock_adapter.list_models.return_value = []
    async with await _client(app) as client:
        response = await client.get(
            "/v1/models",
            headers={**LOCAL_HEADERS, "Origin": "http://localhost:8000"},
        )
    assert response.status_code == 200


@pytest.mark.parametrize("ok_host", ["127.0.0.1", "127.0.0.1:8000", "localhost", "[::1]:8000"])
async def test_each_localhost_form_is_admitted(app, mock_adapter, ok_host) -> None:
    mock_adapter.list_models.return_value = []
    async with await _client(app) as client:
        response = await client.get("/v1/models", headers={"Host": ok_host})
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Logging side effect (smoke test — log message must mention the header)
# ---------------------------------------------------------------------------


async def test_rejection_is_logged(app, mock_adapter, caplog) -> None:
    import logging

    caplog.set_level(logging.WARNING, logger="api.main")
    async with await _client(app) as client:
        await client.get("/v1/models", headers={"Host": "evil.example.com"})
    rejection_logs = [rec for rec in caplog.records if "rejected non-localhost" in rec.getMessage()]
    assert rejection_logs, "expected at least one rejection log line"
    assert "evil.example.com" in rejection_logs[0].getMessage()
