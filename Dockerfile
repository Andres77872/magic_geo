# syntax=docker/dockerfile:1
# All-in-one magic-geo image: C++ native core, Python CLI, and web workbench.
#
#   docker compose up --build          # web workbench on http://127.0.0.1:8642
#   docker compose run --rm magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.json
#
# See docs/docker_deployment.md for the full guide.

ARG PYTHON_VERSION=3.13

# --- Stage 1: build the native core and the platform wheel ------------------
FROM python:${PYTHON_VERSION}-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY CMakeLists.txt pyproject.toml setup.py MANIFEST.in README.md ./
COPY cpp ./cpp
COPY src ./src

# The CUDA backend needs an nvcc 12.8+ base image; the default builds the
# CPU/OpenMP core with the CUDA runtime stub (OpenCL stays a runtime dlopen).
ARG MAGIC_GEO_ENABLE_CUDA=OFF
RUN cmake -S . -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_TESTING=OFF \
        -DMAGIC_GEO_ENABLE_CUDA=${MAGIC_GEO_ENABLE_CUDA} \
    && cmake --build build --config Release -j"$(nproc)"

# setup.py loads the staged library and verifies the exported ABI symbols
# before tagging the wheel, so a broken native build fails here, not at runtime.
RUN pip wheel --no-deps --wheel-dir /wheels .

# --- Stage 2: runtime --------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim

# libgomp1 is the OpenMP runtime the native core links against.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=from=builder,source=/wheels,target=/wheels \
    pip install --no-cache-dir "$(echo /wheels/*.whl)[debug]"

# Match the default host user so a bind-mounted worlds directory stays writable.
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd --gid "${APP_GID}" magicgeo \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home magicgeo

# /app is the project root: web-workbench job inputs are confined to it and
# outputs to the workspace below it. Seed configs ship inside so the UI and
# CLI can reference them.
WORKDIR /app
COPY --chown=magicgeo:magicgeo configs ./configs
RUN mkdir -p /app/runs && chown -R magicgeo:magicgeo /app

USER magicgeo

ENV PYTHONUNBUFFERED=1 \
    MAGIC_GEO_HOST=0.0.0.0 \
    MAGIC_GEO_PORT=8642 \
    MAGIC_GEO_WORKSPACE=/app/runs

EXPOSE 8642

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('MAGIC_GEO_PORT', '8642') + '/api/status', timeout=4)"

ENTRYPOINT ["magic-geo"]
CMD ["serve"]
