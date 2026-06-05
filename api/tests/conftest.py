"""Shared pytest fixtures for api/ unit tests.

All tests here are hermetic: no real network, no Docker. The respx library is
used at the httpx boundary to mock Ollama HTTP calls in TASK-008/TASK-009.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def ollama_base_url() -> str:
    """Default Ollama base URL used across hermetic tests."""
    return "http://model:11434"


@pytest.fixture
def default_model() -> str:
    """Default model tag used across hermetic tests."""
    return "llama4:scout"
