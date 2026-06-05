"""Unit tests for api.state — REQ-INFRA-003 readiness state machine.

The tracker is a tiny finite state machine: LOADING -> READY. Once READY it
stays READY. Concurrent ``mark_ready`` calls are safe.
"""

from __future__ import annotations

import asyncio

import pytest

from api.state import ReadinessState, ReadinessTracker


async def test_initial_state_is_loading() -> None:
    tracker = ReadinessTracker()
    assert await tracker.current_state() is ReadinessState.LOADING


async def test_mark_ready_transitions_to_ready() -> None:
    tracker = ReadinessTracker()
    await tracker.mark_ready()
    assert await tracker.current_state() is ReadinessState.READY


async def test_mark_ready_is_idempotent() -> None:
    tracker = ReadinessTracker()
    await tracker.mark_ready()
    await tracker.mark_ready()  # second call is a no-op
    await tracker.mark_ready()  # and a third
    assert await tracker.current_state() is ReadinessState.READY


async def test_concurrent_mark_ready_is_safe() -> None:
    """Fire many concurrent mark_ready coroutines; final state must be READY
    and no exception should escape (asyncio.Lock serialises the writes)."""
    tracker = ReadinessTracker()
    await asyncio.gather(*(tracker.mark_ready() for _ in range(50)))
    assert await tracker.current_state() is ReadinessState.READY


def test_state_enum_has_exactly_two_members() -> None:
    """Guard against accidental state proliferation — REQ-INFRA-003 is a
    strict two-state machine."""
    assert {m.name for m in ReadinessState} == {"LOADING", "READY"}


def test_state_enum_values_are_strings() -> None:
    """Values are stable strings so /health JSON serialization stays trivial."""
    assert ReadinessState.LOADING.value == "loading"
    assert ReadinessState.READY.value == "ready"


@pytest.mark.parametrize("repeat", [1, 5])
async def test_current_state_is_safe_to_call_repeatedly(repeat: int) -> None:
    tracker = ReadinessTracker()
    for _ in range(repeat):
        assert await tracker.current_state() is ReadinessState.LOADING
