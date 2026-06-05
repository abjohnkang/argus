"""Localhost-only header validation helpers (REQ-INFRA-005).

Pure functions only. No DNS resolution, no network I/O. The two functions in
this module are the single source of truth for "is this request coming from
localhost?" — they are consumed by ``LocalhostOnlyMiddleware`` in
``api/main.py``.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# Canonical localhost hostnames. Comparison is case-insensitive on the
# hostname and tolerates a trailing dot. Anything else (including the
# IPv4-in-IPv6 mapped form ``::ffff:127.0.0.1``) is rejected — only the
# literal IPv6 loopback ``[::1]`` is accepted. This is intentional: we want
# the rejection set to be small and explicit (REQ-INFRA-005).
_LOCALHOST_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "[::1]"})


def _strip_port(value: str) -> str:
    """Return ``value`` without a trailing ``:port`` suffix.

    Handles three shapes:
      * ``host:port``                 -> ``host``
      * ``[ipv6]:port``               -> ``[ipv6]``
      * ``[ipv6]`` (no port)          -> ``[ipv6]``
      * ``host`` (no port)            -> ``host``
    """
    if value.startswith("["):
        # IPv6 literal — port (if any) comes after the closing bracket.
        close = value.find("]")
        if close == -1:
            return value  # malformed; let downstream reject
        host = value[: close + 1]
        return host
    # IPv4 / hostname: split on the LAST colon to be robust, but since we
    # don't accept bare IPv6 here, a single rsplit on ':' is sufficient.
    if value.count(":") == 1:
        return value.split(":", 1)[0]
    return value


def is_localhost_header(value: str) -> bool:
    """Return True iff ``value`` is a localhost host header value.

    Accepted (case-insensitive on hostname): ``127.0.0.1``, ``localhost``,
    ``[::1]``. Optional ``:port`` suffix and trailing dot are tolerated.

    Notably rejected: ``0.0.0.0``, ``::ffff:127.0.0.1`` (IPv4-in-IPv6 mapped
    form is NOT accepted — only the literal IPv6 loopback ``[::1]``), and
    any external hostname.
    """
    if not value:
        return False
    host = _strip_port(value)
    # Tolerate a single trailing dot ("localhost." == "localhost").
    if host.endswith(".") and not host.endswith("]."):
        host = host[:-1]
    return host.lower() in _LOCALHOST_HOSTS


def extract_origin_host(origin: str) -> str:
    """Return the lowercased host component of an Origin URL.

    Strips scheme and any port. Returns empty string if the origin cannot be
    parsed or has no host component.

    For IPv6 origins (``http://[::1]:8000``) the returned host includes the
    surrounding brackets (``[::1]``) so that the result is directly
    comparable with :func:`is_localhost_header`.
    """
    if not origin:
        return ""
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return ""
    if not parsed.scheme or not parsed.netloc:
        return ""
    # urlsplit().hostname strips brackets from IPv6; re-wrap them so that
    # the result composes with is_localhost_header without special casing.
    hostname = parsed.hostname
    if hostname is None:
        return ""
    if ":" in hostname and not hostname.startswith("["):
        # IPv6 literal — urlsplit returns the address without brackets.
        return f"[{hostname.lower()}]"
    return hostname.lower()
