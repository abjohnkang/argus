"""Argus FastAPI backend — localhost-only HTTP API for Llama 4 inference.

@MX:NOTE: SPEC-INFRA-001 — see .moai/specs/SPEC-INFRA-001/spec.md for the full
runtime-foundation contract. This package owns the HTTP surface; the model
runtime lives in a separate Docker service (Ollama).
"""

__version__ = "0.1.0"
