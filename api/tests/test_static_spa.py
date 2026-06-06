"""Unit tests for SPA static-file serving (SPEC-UI-001 backend delta).

The existing FastAPI ``api`` service serves the pre-built React SPA from
``web/dist`` via ``StaticFiles`` mounted at ``/``. These tests pin the two
invariants that make that safe:

  1. API-route precedence — the SPA catch-all is registered AFTER /health,
     /v1/models, /v1/chat/completions, so those paths NEVER resolve to
     index.html.
  2. Graceful absence — when web/dist does not exist (the hermetic test/dev
     case), the mount is skipped with a warning and the API still starts.

The SPA mount is also still subject to ``LocalhostOnlyMiddleware`` (the
localhost threat model is not weakened by adding the mount).

All tests are hermetic: a temporary ``web/dist`` with a stub index.html +
asset is created per-test and pointed at via the ``ARGUS_WEB_DIST`` override,
so no real Vite build is required.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import ASGITransport

from api.main import create_app

LOCAL_HEADERS = {"Host": "127.0.0.1:8000"}


@pytest.fixture
def dist_dir(tmp_path: Path) -> Path:
    """A stub ``web/dist`` with an index.html shell and a hashed asset."""
    dist = tmp_path / "web" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><head><title>Argus</title></head>"
        "<body><div id=root></div></body></html>",
        encoding="utf-8",
    )
    (dist / "assets" / "index-abc123.js").write_text("console.log('argus');", encoding="utf-8")
    return dist


@pytest.fixture
def app_with_spa(dist_dir: Path, monkeypatch):
    """App whose StaticFiles mount points at the stub dist via env override."""
    monkeypatch.setenv("ARGUS_WEB_DIST", str(dist_dir))
    return create_app(start_poller=False)


@pytest.fixture
def mock_adapter(app_with_spa):
    adapter = AsyncMock()
    adapter.chat_completion_stream = MagicMock()
    app_with_spa.state.adapter = adapter
    return adapter


async def _client(app):
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1:8000")


# ---------------------------------------------------------------------------
# API-route precedence — the critical ordering invariant
# ---------------------------------------------------------------------------


async def test_health_still_returns_json_not_index(app_with_spa, mock_adapter) -> None:
    """/health must return the readiness JSON, NOT the SPA index.html."""
    async with await _client(app_with_spa) as client:
        response = await client.get("/health", headers=LOCAL_HEADERS)
    assert response.status_code == 503
    assert response.json() == {"status": "loading"}
    assert not response.headers["content-type"].startswith("text/html")


async def test_health_ready_still_returns_json(app_with_spa, mock_adapter) -> None:
    await app_with_spa.state.readiness.mark_ready()
    async with await _client(app_with_spa) as client:
        response = await client.get("/health", headers=LOCAL_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_models_route_takes_precedence_over_spa(app_with_spa, mock_adapter) -> None:
    """/v1/models must route to the API handler, not the static catch-all."""
    mock_adapter.list_models.return_value = [{"name": "llama4:scout"}]
    async with await _client(app_with_spa) as client:
        response = await client.get("/v1/models", headers=LOCAL_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"models": [{"name": "llama4:scout"}]}
    mock_adapter.list_models.assert_awaited_once()


async def test_chat_completions_route_takes_precedence_over_spa(app_with_spa, mock_adapter) -> None:
    """POST /v1/chat/completions must reach the API handler, not the SPA."""

    async def _chunks(*args, **kwargs):
        yield b'data: {"message":{"content":"hi"},"done":false}\n\n'
        yield b"data: [DONE]\n\n"

    mock_adapter.chat_completion_stream.side_effect = lambda *a, **kw: _chunks()
    async with await _client(app_with_spa) as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={**LOCAL_HEADERS, "Content-Type": "application/json"},
            json={"model": "llama4:scout", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    mock_adapter.chat_completion_stream.assert_called_once()


# ---------------------------------------------------------------------------
# SPA serving
# ---------------------------------------------------------------------------


async def test_root_serves_index_html(app_with_spa, mock_adapter) -> None:
    async with await _client(app_with_spa) as client:
        response = await client.get("/", headers=LOCAL_HEADERS)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<div id=root>" in response.text


async def test_hashed_asset_is_served(app_with_spa, mock_adapter) -> None:
    async with await _client(app_with_spa) as client:
        response = await client.get("/assets/index-abc123.js", headers=LOCAL_HEADERS)
    assert response.status_code == 200
    assert "console.log('argus')" in response.text


async def test_unknown_non_api_path_returns_404_not_index(app_with_spa, mock_adapter) -> None:
    """Starlette ``StaticFiles(html=True)`` does NOT do catch-all SPA rewriting.

    html=True serves ``index.html`` only for the directory root ("/") and a
    ``404.html`` (if present) for misses — it does NOT serve index.html for an
    arbitrary unmatched deep path. So an unknown non-API path returns 404, and
    crucially it does NOT leak as one of the API JSON handlers. This is fine for
    the single-page demo slice (the SPA loads at "/"; there is no client-side
    deep-link router — see SPEC-UI-001 exclusions). This test pins that exact
    behavior so a future maintainer is not surprised, and confirms the path is
    handled by the static mount (404) rather than colliding with an API route.
    """
    async with await _client(app_with_spa) as client:
        response = await client.get("/some/client/route", headers=LOCAL_HEADERS)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Graceful absence — no web/dist on disk
# ---------------------------------------------------------------------------


async def test_app_starts_without_dist(monkeypatch, tmp_path, caplog) -> None:
    """When web/dist is absent the mount is skipped (with a warning) and the
    API still serves /health — the 103 existing tests run in exactly this
    no-dist state."""
    import logging

    missing = tmp_path / "definitely" / "missing" / "dist"
    monkeypatch.setenv("ARGUS_WEB_DIST", str(missing))
    caplog.set_level(logging.WARNING, logger="api.main")

    app = create_app(start_poller=False)
    adapter = AsyncMock()
    adapter.chat_completion_stream = MagicMock()
    app.state.adapter = adapter

    async with await _client(app) as client:
        response = await client.get("/health", headers=LOCAL_HEADERS)
    assert response.status_code == 503
    assert response.json() == {"status": "loading"}

    warnings = [
        r for r in caplog.records if "web/dist" in r.getMessage() or "SPA" in r.getMessage()
    ]
    assert warnings, "expected a warning when web/dist is absent"


async def test_root_returns_404_when_dist_absent(monkeypatch, tmp_path) -> None:
    """With no SPA mounted, '/' has no handler and returns 404 (not a crash)."""
    missing = tmp_path / "no" / "dist"
    monkeypatch.setenv("ARGUS_WEB_DIST", str(missing))
    app = create_app(start_poller=False)
    adapter = AsyncMock()
    adapter.chat_completion_stream = MagicMock()
    app.state.adapter = adapter
    async with await _client(app) as client:
        response = await client.get("/", headers=LOCAL_HEADERS)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Dist-path resolution — production (non-override) anchoring
# ---------------------------------------------------------------------------


def test_resolve_web_dist_default_is_anchored_to_repo_root(monkeypatch) -> None:
    """Without the env override, the dist path is anchored to <root>/web/dist
    (derived from api/main.py's location), NOT a CWD-relative 'web/dist' — so
    it resolves correctly regardless of the process working directory and
    matches where api/Dockerfile copies the bundle (/app/web/dist)."""
    from pathlib import Path

    from api.main import _resolve_web_dist

    monkeypatch.delenv("ARGUS_WEB_DIST", raising=False)
    resolved = _resolve_web_dist()
    assert resolved.is_absolute()
    assert resolved.name == "dist"
    assert resolved.parent.name == "web"
    # <root>/web/dist sits beside the <root>/api package directory.
    assert (resolved.parent.parent / "api").is_dir()
    # Anchored to api/main.py, not the process CWD.
    expected = Path(__import__("api.main", fromlist=["__file__"]).__file__)
    expected = expected.resolve().parent.parent / "web" / "dist"
    assert resolved == expected


def test_resolve_web_dist_honors_env_override(monkeypatch) -> None:
    from api.main import _resolve_web_dist

    monkeypatch.setenv("ARGUS_WEB_DIST", "/tmp/custom/dist")
    assert str(_resolve_web_dist()) == "/tmp/custom/dist"


# ---------------------------------------------------------------------------
# Middleware still applies to the SPA mount (threat model not weakened)
# ---------------------------------------------------------------------------


async def test_forged_host_rejected_on_spa_route(app_with_spa, mock_adapter) -> None:
    """A non-localhost Host header is still 403 on the SPA root — the
    LocalhostOnlyMiddleware wraps the static mount too."""
    async with await _client(app_with_spa) as client:
        response = await client.get("/", headers={"Host": "evil.example.com"})
    assert response.status_code == 403
    assert response.json()["error"] == "non-localhost host"


async def test_forged_origin_rejected_on_spa_route(app_with_spa, mock_adapter) -> None:
    async with await _client(app_with_spa) as client:
        response = await client.get(
            "/",
            headers={**LOCAL_HEADERS, "Origin": "http://evil.example.com"},
        )
    assert response.status_code == 403
    assert response.json()["error"] == "non-localhost origin"


async def test_forged_host_rejected_on_api_route_with_spa_mounted(
    app_with_spa, mock_adapter
) -> None:
    """Adding the SPA mount must not weaken API-route protection either."""
    async with await _client(app_with_spa) as client:
        response = await client.get("/v1/models", headers={"Host": "evil.example.com"})
    assert response.status_code == 403
    mock_adapter.list_models.assert_not_called()
