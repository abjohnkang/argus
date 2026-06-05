# syntax=docker/dockerfile:1.7
# Argus API container — Python 3.12 FastAPI backend for SPEC-INFRA-001.
#
# Layer ordering rationale:
#   1. Base image
#   2. WORKDIR
#   3. Copy api/requirements.txt FIRST so the pip install layer is cached
#      across source edits (deps change rarely, source changes often).
#   4. pip install
#   5. Copy api/ source last
#
# Runtime contract:
#   - Binds 0.0.0.0:8000 INSIDE the container. Host-side localhost
#     enforcement is provided by docker-compose port mapping
#     `127.0.0.1:${API_PORT:-8000}:8000` (REQ-INFRA-001 layer 1) and by
#     api/main.py LocalhostOnlyMiddleware (REQ-INFRA-005 layer 2).
#   - No development tooling (pytest, ruff, respx) is installed in the
#     image; only the runtime dependencies pinned in api/requirements.txt.

FROM python:3.12-slim

WORKDIR /app

# Reduce Python noise inside the container.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Step 1: install runtime dependencies (cached layer)
COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt

# Step 2: copy application source. api/tests/ is excluded by
# the project-root .dockerignore so test deps remain outside the image.
COPY api/ /app/api/

EXPOSE 8000

# uvicorn binds 0.0.0.0 inside the container — host-side 127.0.0.1
# enforcement is layered above (compose port mapping + middleware).
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
