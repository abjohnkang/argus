"""Unit tests for api.security — REQ-INFRA-005 header validation.

RED phase (TASK-003): all tests fail with NotImplementedError, proving the
tests exercise the stubs from TASK-002.

GREEN phase (TASK-004): real implementation lands and these tests pass.
"""

from __future__ import annotations

import pytest

from api.security import extract_origin_host, is_localhost_header

# ---------------------------------------------------------------------------
# is_localhost_header — accepted values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "127.0.0.1",
        "127.0.0.1:8000",
        "localhost",
        "localhost:8000",
        "LOCALHOST",  # case-insensitive
        "LocalHost:8000",  # mixed case
        "[::1]",
        "[::1]:8000",
        "localhost.",  # trailing dot tolerated
        "127.0.0.1.",  # trailing dot tolerated
    ],
)
def test_is_localhost_header_accepts(value: str) -> None:
    assert is_localhost_header(value) is True


# ---------------------------------------------------------------------------
# is_localhost_header — rejected values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "evil.example.com",
        "evil.example.com:8000",
        "0.0.0.0",
        "0.0.0.0:8000",
        "",
        "::ffff:127.0.0.1",  # IPv4-in-IPv6 form is REJECTED
        "192.168.1.10",  # private LAN address — still rejected
        "10.0.0.1",
        "127.0.0.2",  # only literal 127.0.0.1
        "host.docker.internal",
        "localhost.evil.com",  # subdomain attack
    ],
)
def test_is_localhost_header_rejects(value: str) -> None:
    assert is_localhost_header(value) is False


# ---------------------------------------------------------------------------
# extract_origin_host
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "origin, expected",
    [
        ("http://localhost", "localhost"),
        ("http://localhost:8000", "localhost"),
        ("https://127.0.0.1:8000", "127.0.0.1"),
        ("http://[::1]:8000", "[::1]"),
        ("http://EVIL.example.com", "evil.example.com"),  # lowercased
        ("http://evil.example.com:443/path", "evil.example.com"),
    ],
)
def test_extract_origin_host_parses(origin: str, expected: str) -> None:
    assert extract_origin_host(origin) == expected


@pytest.mark.parametrize("origin", ["", "not-a-url", "ftp://", "://no-scheme"])
def test_extract_origin_host_returns_empty_on_bad_input(origin: str) -> None:
    assert extract_origin_host(origin) == ""


# ---------------------------------------------------------------------------
# Defensive branches
# ---------------------------------------------------------------------------


def test_is_localhost_header_handles_malformed_ipv6_without_closing_bracket() -> None:
    """A bare '[' with no ']' must not crash; should return False (not localhost)."""
    assert is_localhost_header("[no-close") is False


def test_extract_origin_host_strips_brackets_and_lowercases_ipv6() -> None:
    """IPv6 origins must round-trip into a value is_localhost_header accepts."""
    host = extract_origin_host("http://[::1]:9999")
    assert host == "[::1]"
    assert is_localhost_header(host) is True


def test_extract_origin_host_returns_empty_when_url_has_only_scheme() -> None:
    """e.g. 'http://' parses but has no netloc / hostname."""
    assert extract_origin_host("http://") == ""
