"""End-to-end integration tests for the Argus Docker stack.

All tests in this module are marked `integration` and require Docker plus
a network path capable of pulling `llama3.2:1b` (~1 GB) on first run.
They are skipped automatically when Docker is unavailable (see
``conftest.py``).

Coverage map (REQ -> test):
- REQ-INFRA-001 (loopback bind)       -> test_port_bound_to_loopback_only
- REQ-INFRA-002 (idempotent restart)  -> test_idempotent_restart
- REQ-INFRA-002 (port-in-use failure) -> test_run_server_exits_2_when_port_in_use
- REQ-INFRA-003 (health 200 when ready) -> test_health_eventually_200
- REQ-INFRA-004 (MODEL override)      -> test_model_override_lists_llama32
- REQ-INFRA-005 (forged Host 403)     -> test_forged_host_rejected
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess

import httpx
import pytest

pytestmark = pytest.mark.integration


def test_health_eventually_200(http_client: httpx.Client) -> None:
    """REQ-INFRA-003: after the cold-start fixture completes, /health is 200.

    The fixture already blocked on `run_server.sh` until /health returned
    200, so this test is a thin sanity check on the live stack — but it
    also verifies the body shape contractually demanded by the SPEC
    (`{"status": "ready"}`).
    """
    response = http_client.get("/health", timeout=60.0)
    assert (
        response.status_code == 200
    ), f"expected 200 ready, got {response.status_code}: {response.text}"
    assert response.json() == {"status": "ready"}


def test_port_bound_to_loopback_only(docker_stack: dict) -> None:
    """REQ-INFRA-001: the API port is bound only on 127.0.0.1, never 0.0.0.0.

    Uses `lsof` to inspect listening sockets for the assigned port. If
    `lsof` is not installed (e.g., minimal CI containers), skip — the
    docker-compose.yml host mapping `127.0.0.1:PORT:PORT` already enforces
    this at the kernel level, but this test verifies it on the running
    system.
    """
    if shutil.which("lsof") is None:
        pytest.skip("lsof not installed; cannot verify socket bind interface")

    api_port = docker_stack["api_port"]
    result = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{api_port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    # lsof exits 1 when no matching socket is found. If the stack is up
    # and bound, we expect exit 0 with at least one matching row.
    assert result.returncode == 0, (
        f"lsof found no listener on port {api_port}: "
        f"stdout={result.stdout} stderr={result.stderr}"
    )

    output = result.stdout
    assert f"127.0.0.1:{api_port}" in output, f"expected 127.0.0.1:{api_port} bind, got: {output}"
    assert (
        f"*:{api_port}" not in output
    ), f"wildcard bind detected (*:{api_port}) — REQ-INFRA-001 violation: {output}"
    assert (
        f"0.0.0.0:{api_port}" not in output
    ), f"0.0.0.0 bind detected — REQ-INFRA-001 violation: {output}"


def test_model_override_lists_llama32(http_client: httpx.Client) -> None:
    """REQ-INFRA-004: MODEL=llama3.2:1b override surfaces in /v1/models.

    The fixture exports MODEL=llama3.2:1b before invoking run_server.sh,
    so the running stack should advertise that model and NOT the default
    `llama4:scout`.
    """
    response = http_client.get("/v1/models", timeout=60.0)
    assert (
        response.status_code == 200
    ), f"expected 200 from /v1/models, got {response.status_code}: {response.text}"

    body_text = response.text
    assert (
        "llama3.2:1b" in body_text
    ), f"expected llama3.2:1b in /v1/models response, got: {body_text}"
    assert (
        "llama4:scout" not in body_text
    ), f"unexpected llama4:scout in /v1/models response: {body_text}"


def test_forged_host_rejected(docker_stack: dict) -> None:
    """REQ-INFRA-005: a non-localhost Host header is rejected with 403.

    Bypasses the session http_client (which has the correct base_url and
    therefore the correct Host header) and sends a fresh request with a
    forged Host header to the same loopback port. The middleware must
    reject this with 403 without invoking the model adapter.
    """
    api_port = docker_stack["api_port"]
    with httpx.Client(timeout=60.0) as fresh_client:
        response = fresh_client.get(
            f"http://127.0.0.1:{api_port}/health",
            headers={"Host": "evil.example.com"},
        )

    assert (
        response.status_code == 403
    ), f"expected 403 for forged Host, got {response.status_code}: {response.text}"

    # The response body should indicate the rejection reason. The middleware
    # returns either {"error": "non-localhost host", ...} or similar — accept
    # any mention of "host" or "localhost" (case-insensitive) as evidence
    # that the rejection was intentional and not an accidental 403 from
    # somewhere else.
    body_lower = response.text.lower()
    assert (
        "host" in body_lower or "localhost" in body_lower
    ), f"403 body does not indicate localhost rejection reason: {response.text}"


def test_idempotent_restart(docker_stack: dict) -> None:
    """REQ-INFRA-002 idempotency clause: re-invoking run_server.sh is a no-op.

    The fixture already started the stack once. Running run_server.sh
    again with the same env should exit 0 quickly (no recreate, no
    re-pull) and /health should still respond 200.
    """
    env = docker_stack["env"]

    result = subprocess.run(
        ["./run_server.sh"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"second run_server.sh invocation failed with exit {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )

    # /health must still be 200 ready after the idempotent restart.
    base_url = docker_stack["base_url"]
    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        response = client.get("/health")
    assert response.status_code == 200, (
        f"/health regressed after idempotent restart: " f"{response.status_code} {response.text}"
    )
    assert response.json() == {"status": "ready"}


def test_run_server_exits_2_when_port_in_use():
    """Edge Case 2: ./run_server.sh detects port conflict and exits cleanly.

    REQ-INFRA-002 failure path. We bind a socket on 127.0.0.1:<port>, then
    invoke ./run_server.sh with API_PORT=<port>. The script's pre-flight
    lsof check should detect the conflict and exit 2 with a clear message
    including the API_PORT override hint.
    """
    # Skip if Docker daemon is unavailable (script exits 1 on Docker check
    # BEFORE reaching the port check).
    docker_info = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
    if docker_info.returncode != 0:
        pytest.skip("Docker daemon unavailable; script exits 1 on Docker check before port check")

    # Skip if lsof is unavailable (script silently skips port check without it).
    if shutil.which("lsof") is None:
        pytest.skip("lsof not on PATH; run_server.sh skips port check without it")

    # Pick a free port and immediately bind to it so it appears 'in use'.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        blocked_port = blocker.getsockname()[1]

        env = {**os.environ, "API_PORT": str(blocked_port)}
        result = subprocess.run(
            ["./run_server.sh"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    # Verify: exit code 2, stderr contains the port and the override hint.
    assert result.returncode == 2, (
        f"expected exit 2 on port conflict, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert (
        str(blocked_port) in result.stderr
    ), f"stderr should reference the blocked port {blocked_port}\nstderr: {result.stderr}"
    assert (
        "API_PORT" in result.stderr
    ), f"stderr should mention the API_PORT override hint\nstderr: {result.stderr}"
