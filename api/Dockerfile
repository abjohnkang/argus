# syntax=docker/dockerfile:1.7
# Argus API container — Python 3.12 FastAPI backend for SPEC-INFRA-001,
# now also serving the SPEC-UI-001 React SPA from /app/web/dist.
#
# @MX:NOTE: Multi-stage build. The `web-build` stage below uses node:20-slim
# to run `vite build` and produce web/dist. Node appears in the BUILD STAGE
# ONLY — it is never installed in the python:3.12-slim runtime stage. The
# runtime image gains exactly one new thing: the static web/dist bundle copied
# via `COPY --from=web-build`. This preserves the no-Node-at-runtime stance
# (REQ-UI-001 / SPEC-UI-001 §6): Vite is a build-time step, there is no
# production Node runtime and no new container.
#
# Build context: the api service builds with `context: .` (repo root, see
# docker-compose.yml), so both `web/` (for the build stage) and `api/` (for
# the runtime stage) are reachable. `.dockerignore` excludes web/node_modules
# and web/dist so the Node stage installs/builds fresh.
#
# Layer ordering rationale (runtime stage):
#   1. Base image
#   2. WORKDIR
#   3. Copy api/requirements.txt FIRST so the pip install layer is cached
#      across source edits (deps change rarely, source changes often).
#   4. pip install
#   5. Copy api/ source last
#   6. Copy the pre-built web/dist from the web-build stage
#
# Runtime contract:
#   - Binds 0.0.0.0:8000 INSIDE the container. Host-side localhost
#     enforcement is provided by docker-compose port mapping
#     `127.0.0.1:${API_PORT:-8000}:8000` (REQ-INFRA-001 layer 1) and by
#     api/main.py LocalhostOnlyMiddleware (REQ-INFRA-005 layer 2).
#   - No development tooling (pytest, ruff, respx) is installed in the
#     image; only the runtime dependencies pinned in api/requirements.txt.

# ---------------------------------------------------------------------------
# Stage 1: build the React SPA bundle (Node is build-time only).
# ---------------------------------------------------------------------------
FROM node:20-slim AS web-build

WORKDIR /web

# Copy manifests first so `npm ci` caches across web/src edits.
COPY web/package.json web/package-lock.json ./
RUN npm ci

# Copy the rest of the frontend source and build to /web/dist.
COPY web/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: python runtime — FastAPI backend + serve the built SPA.
# ---------------------------------------------------------------------------
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

# Step 3: copy the pre-built SPA bundle from the web-build stage. This MUST
# land at /app/web/dist — api/main.py's _resolve_web_dist() resolves to
# <project_root>/web/dist where project_root is the parent of the api/
# package (= WORKDIR /app), so the StaticFiles mount points exactly here.
COPY --from=web-build /web/dist /app/web/dist

EXPOSE 8000

# uvicorn binds 0.0.0.0 inside the container — host-side 127.0.0.1
# enforcement is layered above (compose port mapping + middleware).
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
