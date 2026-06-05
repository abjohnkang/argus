"""Readiness state machine for the /health endpoint (REQ-INFRA-003).

A tiny finite state machine with exactly two states: ``LOADING`` and
``READY``. Once ``mark_ready()`` succeeds, subsequent calls are no-ops. The
state is guarded by an ``asyncio.Lock`` so concurrent transitions are safe.

@MX:NOTE: The state machine is intentionally two-state. Future enhancements
(e.g. an ERROR state) must amend SPEC-INFRA-001 first — see
.moai/specs/SPEC-INFRA-001/spec.md REQ-INFRA-003.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum


class ReadinessState(StrEnum):
    """Lifecycle states of the model runtime as observed by /health."""

    LOADING = "loading"
    READY = "ready"


class ReadinessTracker:
    """Concurrency-safe wrapper around the readiness state.

    The tracker starts in ``LOADING``. The background poller in
    ``api/main.py`` calls :meth:`mark_ready` once Ollama reports the model
    is resident. The transition is one-way and idempotent.
    """

    def __init__(self) -> None:
        self._state: ReadinessState = ReadinessState.LOADING
        self._lock: asyncio.Lock = asyncio.Lock()

    async def current_state(self) -> ReadinessState:
        """Return the current state under the lock (cheap, never blocks)."""
        async with self._lock:
            return self._state

    async def mark_ready(self) -> None:
        """Transition LOADING -> READY. Idempotent: already-READY is a no-op."""
        async with self._lock:
            if self._state is ReadinessState.READY:
                return
            self._state = ReadinessState.READY
