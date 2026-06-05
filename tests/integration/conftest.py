"""Integration test fixtures for the Argus Docker stack.

These fixtures bring up the real two-service compose stack (`model` + `api`)
on a random loopback port using a tiny real model (`llama3.2:1b`, ~1 GB) so
the full cold-start contract (REQ-INFRA-001/002/003/004/005) is exercised
end-to-end. The session-scoped fixture caches across all tests in this
package; the named volume `argus_ollama_models` is intentionally kept on
teardown so subsequent local runs skip the model pull.

If the Docker daemon is unreachable, the entire integration session is
skipped via `pytest.skip` at fixture-collection time — these tests are not
hermetic and cannot run in a no-Docker environment.
"""

from __future__ import annotations

import os
import socket
import subprocess

import httpx
import pytest


def _docker_available() -> bool:
    """Probe the Docker daemon with a 5s ceiling.

    Returns True iff `docker info` succeeds within the timeout. Catches
    both timeouts (daemon hung) and FileNotFoundError (no `docker` CLI on
    PATH), since either condition makes the integration suite unrunnable.
    """
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _free_port() -> int:
    """Ask the OS for an unused loopback port and return it.

    Bind-then-close is the standard idiom — the kernel will not immediately
    re-assign the port, giving us a safe window to hand it to compose.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def docker_stack():
    """Session-scoped: launch the Argus stack with `llama3.2:1b`.

    Picks a random free port (parallel-run safety), overrides `MODEL` to
    the 1 GB test model, shortens the poll interval to 0.5s for snappier
    cold-start, and gives `run_server.sh` up to 900s to pull the model
    and report `/health` 200 on first run. Tears down with `docker compose
    down` but keeps the named volume so the pull is cached across runs.
    """
    if not _docker_available():
        pytest.skip("Docker daemon unavailable; integration tests require Docker")

    api_port = _free_port()
    env = {
        **os.environ,
        "MODEL": "llama3.2:1b",
        "API_PORT": str(api_port),
        "POLL_INTERVAL_SECONDS": "0.5",
        # Generous timeout — first run pulls ~1 GB over the network.
        "ARGUS_HEALTH_TIMEOUT": "900",
    }

    # `./run_server.sh` lives at the project root (per CLAUDE.md and the
    # 2026-06-04 path correction recorded in SPEC-INFRA-001 HISTORY). It is
    # idempotent: on a healthy stack it returns 0 quickly.
    result = subprocess.run(
        ["./run_server.sh"],
        env=env,
        capture_output=True,
        text=True,
        timeout=1000,
    )
    if result.returncode != 0:
        # Tear down any partial state before failing so the next session
        # starts clean.
        subprocess.run(
            ["docker", "compose", "down"],
            env=env,
            capture_output=True,
        )
        pytest.fail(
            f"run_server.sh exited {result.returncode}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    base_url = f"http://127.0.0.1:{api_port}"
    yield {"base_url": base_url, "api_port": api_port, "env": env}

    # Teardown: stop containers but KEEP the named volume so the model
    # pull is amortized across local runs.
    subprocess.run(
        ["docker", "compose", "down"],
        env=env,
        capture_output=True,
        timeout=60,
    )


@pytest.fixture(scope="session")
def http_client(docker_stack):
    """Reusable httpx.Client bound to the started stack's base URL.

    Generous default timeout (60s) accommodates the first chat request
    after a cold start, which can be slow on resource-constrained hosts.
    """
    with httpx.Client(base_url=docker_stack["base_url"], timeout=60.0) as client:
        yield client
