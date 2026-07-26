# Docker Deployment

[Wiki home](./README.md) > Operations

magic-geo ships a single all-in-one container image: the C++ native core is compiled inside a builder stage, a platform wheel is produced and ABI-checked, and a slim runtime stage installs that wheel with the `[debug]` extra so the same image serves the web workbench (`ENTRYPOINT ["magic-geo"]`, `CMD ["serve"]`) and every other CLI subcommand. Configuration is a small `.env` file that Compose reads for `${...}` substitution in `docker-compose.yml`; the service explicitly injects only the four runtime values it consumes. This page walks the `Dockerfile` and `docker-compose.yml` line by line, enumerates every setting and who actually consumes it, explains the bind-mount persistence model, and records exactly which GPU claims are and are not backed by the repository.

## On this page

- [What the image contains](#what-the-image-contains)
- [Stage 1: builder — native core and platform wheel](#stage-1-builder--native-core-and-platform-wheel)
- [Stage 2: runtime image](#stage-2-runtime-image)
- [Build context and `.dockerignore`](#build-context-and-dockerignore)
- [The Compose service, line by line](#the-compose-service-line-by-line)
- [`.env` reference](#env-reference)
- [Persistence model](#persistence-model)
- [Running arbitrary CLI subcommands through the same image](#running-arbitrary-cli-subcommands-through-the-same-image)
- [Loopback-only publication and the security model](#loopback-only-publication-and-the-security-model)
- [GPU passthrough: what is and is not verified](#gpu-passthrough-what-is-and-is-not-verified)
- [Image size and build-time expectations](#image-size-and-build-time-expectations)
- [Operations troubleshooting](#operations-troubleshooting)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## What the image contains

The image is declared by `Dockerfile` (74 lines) and is a two-stage multi-stage build. Both stages use the same base, parameterised once at the top:

```dockerfile
# Dockerfile:1
# syntax=docker/dockerfile:1
# Dockerfile:9
ARG PYTHON_VERSION=3.13
```

| Ingredient | Where it comes from | Source |
| --- | --- | --- |
| Base image (both stages) | `python:${PYTHON_VERSION}-slim`, default `3.13` | `Dockerfile:9`, `:12`, `:38` |
| Build toolchain (builder only) | `build-essential`, `cmake` via apt, lists removed afterwards | `Dockerfile:14-16` |
| `libmagic_geo_native.so` | Compiled in the builder from `cpp/` + `CMakeLists.txt`, `CMAKE_BUILD_TYPE=Release`, `BUILD_TESTING=OFF` | `Dockerfile:27-31` |
| Platform wheel `magic_geo-0.1.0-py3-none-<platform>.whl` | `pip wheel --no-deps --wheel-dir /wheels .` in the builder | `Dockerfile:35`, `setup.py:43-45` |
| Python runtime deps | Wheel deps: `msgpack>=1.1,<2`, `pydantic>=2.10`, `PyYAML>=6.0.2`, `typer>=0.16.0` | `pyproject.toml:11-16` |
| Web workbench deps | `[debug]` extra: `pyarrow>=19`, `duckdb>=1.2`, `fastapi>=0.115`, `uvicorn[standard]>=0.34` | `pyproject.toml:18-24`, `Dockerfile:45-46` |
| OpenMP runtime | `libgomp1` via apt in the runtime stage | `Dockerfile:41-43` |
| Seed configurations | `configs/` copied to `/app/configs`, owned by `magicgeo` | `Dockerfile:58` |
| Workspace directory | `/app/runs`, created and chowned before `USER` switch | `Dockerfile:59` |
| Console script | `magic-geo = "magic_geo.cli:main"` from the installed wheel | `pyproject.toml:30-31` |
| Static workbench UI | `debug_ui/*.html|css|js` + `debug_ui/vendor/*.js` package data inside the wheel | `pyproject.toml:41-44` |

What is **not** in the image: no CUDA toolkit, no OpenCL ICD loader, no test suite, no `docs/`, no `scripts/`, no host-built binaries. Those exclusions are deliberate and enforced by the `COPY` list (`Dockerfile:20-22`) and `.dockerignore`.

---

## Stage 1: builder — native core and platform wheel

```dockerfile
# Dockerfile:11-35
FROM python:${PYTHON_VERSION}-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY CMakeLists.txt pyproject.toml setup.py MANIFEST.in README.md ./
COPY cpp ./cpp
COPY src ./src

ARG MAGIC_GEO_ENABLE_CUDA=OFF
RUN cmake -S . -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_TESTING=OFF \
        -DMAGIC_GEO_ENABLE_CUDA=${MAGIC_GEO_ENABLE_CUDA} \
    && cmake --build build --config Release -j"$(nproc)"

RUN pip wheel --no-deps --wheel-dir /wheels .
```

| Line | Instruction | Why it is there |
| --- | --- | --- |
| `Dockerfile:12` | `FROM python:${PYTHON_VERSION}-slim AS builder` | Named stage; the runtime stage mounts `/wheels` from it rather than `COPY --from`, so nothing from the toolchain layer is retained. |
| `Dockerfile:14-16` | apt install `build-essential cmake`, then `rm -rf /var/lib/apt/lists/*` | The only build-time system dependencies. `CMakeLists.txt:1` requires CMake ≥ 3.20 and the C++ standard is fixed at 20 (`CMakeLists.txt:76-78`). |
| `Dockerfile:18` | `WORKDIR /build` | Build tree root; distinct from the runtime `/app`. |
| `Dockerfile:20` | `COPY CMakeLists.txt pyproject.toml setup.py MANIFEST.in README.md ./` | Exactly the files the PEP 517 build needs. `README.md` is copied because `pyproject.toml:9` declares it as the readme, so omitting it would fail metadata generation. |
| `Dockerfile:21` | `COPY cpp ./cpp` | All native sources and headers for `magic_geo_native`. |
| `Dockerfile:22` | `COPY src ./src` | The Python package. It is also the **staging target** for the compiled library — see below. |
| `Dockerfile:26` | `ARG MAGIC_GEO_ENABLE_CUDA=OFF` | Overrides the CMake option default, which is `ON` (`CMakeLists.txt:7-11`). The image build deliberately flips it off. |
| `Dockerfile:27-31` | `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DMAGIC_GEO_ENABLE_CUDA=…` then `cmake --build build --config Release -j"$(nproc)"` | `BUILD_TESTING=OFF` skips the entire CTest block (`CMakeLists.txt:223`), so **no native test runs during the image build**. Parallelism is `nproc` of the build host. |
| `Dockerfile:35` | `pip wheel --no-deps --wheel-dir /wheels .` | Produces exactly one wheel into `/wheels`. `--no-deps` means no runtime dependency wheels are built here; they are resolved in the runtime stage. |

### Where the compiled library goes

`CMakeLists.txt:83-88` defines:

```cmake
set(
  MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY
  "${CMAKE_CURRENT_SOURCE_DIR}/src/magic_geo"
  CACHE PATH
  "Directory for the native shared library"
)
```

so the Release build stages `libmagic_geo_native.so` directly into `/build/src/magic_geo/`, beside the Python package. `pyproject.toml:36-45` lists that filename as package data, which is how the shared library ends up **inside the wheel**. This is the single link between the CMake build and the Python packaging step; there is no separate copy instruction in the `Dockerfile`.

### The ABI gate

The `Dockerfile` comment at `:33-34` states the intent:

> `setup.py` loads the staged library and verifies the exported ABI symbols before tagging the wheel, so a broken native build fails here, not at runtime.

`setup.py:47-74` implements it. `PlatformWheel.run()`:

1. Resolves the platform-appropriate name (`libmagic_geo_native.so` on Linux, `setup.py:19-26`).
2. Raises `RuntimeError(f"cannot build a wheel without {native_path}; build the native Release target with CMake first")` if it is missing (`setup.py:50-54`).
3. `ctypes.CDLL`s it and resolves seven symbols — `magic_geo_backend_info_json`, `magic_geo_generate_json_v3`, `magic_geo_generate_geo_json_v3`, `magic_geo_generate_msgpack_v3`, `magic_geo_generate_geo_msgpack_v3`, `magic_geo_free_string`, `magic_geo_free_buffer` (`setup.py:57-65`).
4. On `OSError`/`AttributeError` raises `RuntimeError(f"the staged native core is incompatible with this build host or package: {native_path}: {exc}")` (`setup.py:67-71`).

Consequences for the image build: a native build that compiles but exports the wrong ABI fails at `Dockerfile:35`, not at first container start. The wheel is also tagged `("py3", "none", platform)` with `root_is_pure = False` (`setup.py:39-45`), i.e. Python-ABI-independent (the boundary is `ctypes`) but OS/architecture-specific — so an image built on one architecture cannot be run on another.

### CUDA in the builder

`MAGIC_GEO_ENABLE_CUDA` is only a CMake option here. The shipped builder base (`python:3.13-slim`) contains no `nvcc`, so even `MAGIC_GEO_ENABLE_CUDA=ON` takes the "compiler not found" branch:

```cmake
# CMakeLists.txt:64-66
  else()
    message(STATUS "magic-geo CUDA backend: compiler not found; building runtime stub")
  endif()
```

and `MAGIC_GEO_CUDA_SOURCE` stays `cpp/src/cuda_compute_stub.cpp` (`CMakeLists.txt:19`). This is a **STATUS message, not a warning or an error** — the build succeeds and silently produces a stub. The GPU notes in `docs/docker_deployment.md` state that a real CUDA image requires switching the builder base to a CUDA 12.8+ development image.

---

## Stage 2: runtime image

```dockerfile
# Dockerfile:37-74
FROM python:${PYTHON_VERSION}-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=from=builder,source=/wheels,target=/wheels \
    pip install --no-cache-dir "$(echo /wheels/*.whl)[debug]"

ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd --gid "${APP_GID}" magicgeo \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home magicgeo

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
```

| Line | Instruction | Notes |
| --- | --- | --- |
| `Dockerfile:38` | Fresh `python:${PYTHON_VERSION}-slim` | No compiler, no CMake, no `cpp/` sources in the final image. |
| `Dockerfile:40-43` | `libgomp1` | The `Dockerfile` comment states it is "the OpenMP runtime the native core links against". OpenMP is optional at build time (`find_package(OpenMP)`, `CMakeLists.txt:80`); when found, the target links `OpenMP::OpenMP_CXX` and defines `MAGIC_GEO_HAS_OPENMP=1`. |
| `Dockerfile:45-46` | `RUN --mount=from=builder,source=/wheels,target=/wheels pip install --no-cache-dir "$(echo /wheels/*.whl)[debug]"` | A BuildKit bind mount, not a `COPY` — the wheel never becomes a layer in the final image. `[debug]` pulls pyarrow/duckdb/fastapi/uvicorn (`pyproject.toml:19-24`), which is what makes `magic-geo serve` and `export-debug` work. The `$(echo …)` glob assumes exactly one wheel in `/wheels`, which `--no-deps` at `Dockerfile:35` guarantees. |
| `Dockerfile:49-52` | `ARG APP_UID=1000` / `ARG APP_GID=1000`, `groupadd` + `useradd --create-home magicgeo` | The comment at `:48` states the reason: "Match the default host user so a bind-mounted worlds directory stays writable." Override both build args when your host UID/GID differ. |
| `Dockerfile:57` | `WORKDIR /app` | `/app` becomes the container's cwd, and therefore the workbench's **project root** — `create_app` computes `root = Path.cwd().resolve()` when no explicit `project_root` is given (`debug_server.py:885`). |
| `Dockerfile:58` | `COPY --chown=magicgeo:magicgeo configs ./configs` | Ships `configs/earthlike_seed.yaml`, `configs/geo_validation_matrix.yaml`, the nine `configs/seeds/*.yaml` presets, the calibration source manifests, and `configs/calibration_fixtures/`. These live *inside* the image, not on the volume. |
| `Dockerfile:59` | `mkdir -p /app/runs && chown -R magicgeo:magicgeo /app` | Creates the default workspace and hands `/app` to the non-root user. |
| `Dockerfile:61` | `USER magicgeo` | Everything after this — including the entrypoint — runs unprivileged. |
| `Dockerfile:63-66` | `ENV PYTHONUNBUFFERED=1`, `MAGIC_GEO_HOST=0.0.0.0`, `MAGIC_GEO_PORT=8642`, `MAGIC_GEO_WORKSPACE=/app/runs` | Baked defaults; Compose's explicit `environment` values or `-e` override them. `PYTHONUNBUFFERED=1` makes `docker logs` show CLI output promptly. |
| `Dockerfile:68` | `EXPOSE 8642` | Documentation only; Compose does the actual publication. Note this is the literal `8642`, not `${MAGIC_GEO_PORT}` — changing the port does not change the `EXPOSE` metadata. |
| `Dockerfile:70-71` | `HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3` calling `urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('MAGIC_GEO_PORT', '8642') + '/api/status', timeout=4)` | Probes the workbench's own status route from inside the container. `/api/status` is defined at `debug_server.py:928-938` and is always available, including with no debug cache selected. `urlopen` raises on non-2xx, so any error status marks the container unhealthy. |
| `Dockerfile:73-74` | `ENTRYPOINT ["magic-geo"]`, `CMD ["serve"]` | The entrypoint is the CLI itself; `serve` is only the default argument, which is what makes `docker compose run --rm magic-geo <subcommand>` work. |

### Why the healthcheck depends on `MAGIC_GEO_HOST`

The healthcheck connects to `127.0.0.1` *inside* the container's network namespace. `serve` binds `--host`, defaulting to `127.0.0.1` in the CLI (`cli/commands/serve.py:34-37`) but forced to `0.0.0.0` by the image ENV. Both values keep the loopback probe working; a bind address that excludes loopback would make the container report unhealthy even while serving.

---

## Build context and `.dockerignore`

`.dockerignore` (40 lines) shapes what BuildKit uploads. The builder only `COPY`s seven paths — five root files (`CMakeLists.txt`, `pyproject.toml`, `setup.py`, `MANIFEST.in`, `README.md`) plus `cpp/` and `src/` (`Dockerfile:20-22`) — so most entries exist to keep the context small and to prevent host artifacts from leaking.

| Group | Patterns | Source | Rationale (from the file's own comments) |
| --- | --- | --- | --- |
| VCS / IDE / agent state | `.git`, `.idea`, `.claude`, `.agents`, `.codex` | `.dockerignore:2-6` | "Version control, IDE, and agent state." |
| Local environments and caches | `.venv`, `__pycache__/`, `**/__pycache__`, `*.py[cod]`, `*.egg-info/` | `.dockerignore:9-13` | Host virtualenv and byte-compiled artifacts. |
| Host build trees | `build/`, `cmake-build-*/` | `.dockerignore:16-17` | "the image builds the native core itself." |
| Staged host binaries | `src/magic_geo/libmagic_geo_native.so`, `src/magic_geo/magic_geo_native.dll`, `src/magic_geo/libmagic_geo_native.dylib` | `.dockerignore:20-22` | "Staged host binaries must never leak into the image build." Critical: `COPY src ./src` would otherwise ship a host-compiled `.so` that the in-container CMake build then overwrites — or worse, one that survives and gets ABI-checked instead of the freshly built library. |
| Generated outputs and datasets | `runs/`, `worlds/`, `calibration_data/` | `.dockerignore:25-27` | Worlds and downloaded empirical datasets stay on the host. |
| Deployment files | `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env`, `.env.example` | `.dockerignore:30-34` | Prevents secrets in `.env` from entering the image and avoids self-inclusion. |
| Not needed inside the image | `docs/`, `tests/`, `scripts/`, `r1.md` | `.dockerignore:37-40` | The runtime image is not a development environment. |

Note the asymmetry with `MANIFEST.in`, which recursive-includes `docs/*.md`, `scripts`, and `tests/*.py` for source distributions. Those are sdist inputs; the Docker build uses a PEP 517 wheel build from the copied tree, so their absence does not affect the image.

---

## The Compose service, line by line

`docker-compose.yml` is 37 lines and defines exactly one service.

```yaml
# docker-compose.yml:12-37
services:
  magic-geo:
    build:
      context: .
      args:
        PYTHON_VERSION: ${MAGIC_GEO_PYTHON_VERSION:-3.13}
        MAGIC_GEO_ENABLE_CUDA: ${MAGIC_GEO_ENABLE_CUDA:-OFF}
        APP_UID: ${MAGIC_GEO_APP_UID:-1000}
        APP_GID: ${MAGIC_GEO_APP_GID:-1000}
    image: magic-geo:latest
    container_name: magic-geo
    environment:
      MAGIC_GEO_HOST: ${MAGIC_GEO_HOST:-0.0.0.0}
      MAGIC_GEO_PORT: ${MAGIC_GEO_PORT:-8642}
      MAGIC_GEO_WORKSPACE: ${MAGIC_GEO_CONTAINER_WORKSPACE:-/app/runs}
      MAGIC_GEO_NATIVE_LIBRARY: ${MAGIC_GEO_NATIVE_LIBRARY:-}
    ports:
      - "${MAGIC_GEO_PUBLISH_HOST:-127.0.0.1}:${MAGIC_GEO_PORT:-8642}:${MAGIC_GEO_PORT:-8642}"
    volumes:
      - "${MAGIC_GEO_WORLDS_DIR:-./worlds}:${MAGIC_GEO_CONTAINER_WORKSPACE:-/app/runs}"
    restart: unless-stopped
```

| Line | Key | What it does | Failure/behaviour notes |
| --- | --- | --- | --- |
| `:13` | service name `magic-geo` | The name used in every `docker compose run/exec` example. | — |
| `:14-15` | `build.context: .` | Repository root is the build context; no `dockerfile:` key, so the default `./Dockerfile` is used. | Everything in `.dockerignore` is excluded from the upload. |
| `:16-20` | `build.args` | Maps the `.env`-facing Python version, CUDA switch and app UID/GID to the Dockerfile's four build args. | Build args are **only** consumed at build time. Changing one requires `docker compose build` or `up --build`. |
| `:21` | `image: magic-geo:latest` | Names the built image, and is also the image `docker compose run` reuses. | A fixed tag: rebuilding replaces `latest` in place; there is no versioned tag scheme in the repo. |
| `:22` | `container_name: magic-geo` | Pins the long-running workbench container's name. | `docs/docker_deployment.md` uses it for `docker compose exec magic-geo bash`. |
| `:23-29` | `environment` | Injects only host, port, container workspace and optional native-library override. Compose assigns `MAGIC_GEO_CONTAINER_WORKSPACE` to the process-facing `MAGIC_GEO_WORKSPACE`. | Build settings and the host bind source are not leaked into the container. Empty `MAGIC_GEO_NATIVE_LIBRARY` selects the bundled library. |
| `:30-34` | `ports` | Publishes the same configured port on the selected host interface and inside the container. | The server receives the same port at `:27`, and the healthcheck reads it from the environment, so the three values cannot drift. The default host interface is loopback. |
| `:35-36` | `volumes` | Bind-mounts `MAGIC_GEO_WORLDS_DIR` on the host at `MAGIC_GEO_CONTAINER_WORKSPACE` in the container. | The container target defaults to the absolute path `/app/runs`; bare-metal `MAGIC_GEO_WORKSPACE=runs` cannot accidentally turn it into an invalid relative mount. |
| `:37` | `restart: unless-stopped` | Restarts the workbench after a crash or daemon restart, but not after an explicit `docker compose stop`. | It reacts to exit, not to the healthcheck; an unhealthy-but-running container is not restarted. |

There is **no** `deploy.resources.reservations.devices`, no `gpus:` key, and no `devices:` key in the compose file. GPU access is not wired up by default — see [GPU passthrough](#gpu-passthrough-what-is-and-is-not-verified).

### Quick start

```bash
cp .env.example .env      # adjust if needed; defaults work out of the box
mkdir -p worlds           # host directory that stores generated worlds
docker compose up --build -d
# web workbench: http://127.0.0.1:8642
```

Create `worlds/` yourself before the first `up`: if Docker auto-creates it, it belongs to root and the non-root container user cannot write into it, as the quick-start guide also warns.

---

## `.env` reference

`.env` is gitignored (`.gitignore:13-14`); `.env.example` is the tracked, documented template. Copy it and edit.

| Variable | Default | Meaning | Consumed by |
| --- | --- | --- | --- |
| `MAGIC_GEO_WORLDS_DIR` | `./worlds` (`.env.example:20`) | Host directory that persists generated worlds, configs, reports, and exports. Relative paths resolve against the Compose project directory. | **Compose only** — volume source (`docker-compose.yml:36`). No Python source reads it. |
| `MAGIC_GEO_CONTAINER_WORKSPACE` | `/app/runs` (`.env.example:27`) | Absolute bind-mount target inside the container. Must remain under `/app`. Its distinct name prevents a bare-metal relative workspace from becoming a Docker mount target. | Compose uses it twice: as runtime `MAGIC_GEO_WORKSPACE` (`docker-compose.yml:28`) and the volume target (`:36`). |
| `MAGIC_GEO_HOST` | `0.0.0.0` (`.env.example:36`) | Bind address inside the container. `0.0.0.0` is required so the published port can reach it. | Compose injects it at `docker-compose.yml:26`; `serve --host` reads it (`cli/commands/serve.py:34-37`). |
| `MAGIC_GEO_PORT` | `8642` (`.env.example:39`) | Port the workbench listens on and Compose publishes. | Runtime environment (`docker-compose.yml:27`), both sides of the port mapping (`:34`), `serve --port` (`cli/commands/serve.py:38-47`) and the image healthcheck (`Dockerfile:71`). |
| `MAGIC_GEO_PUBLISH_HOST` | `127.0.0.1` (`.env.example:44`) | Host interface Docker publishes. Keep loopback unless an authenticating boundary protects the workbench. | **Compose only** — host-interface part of `docker-compose.yml:34`. |
| `MAGIC_GEO_PYTHON_VERSION` | `3.13` (`.env.example:52`) | Python slim-image version used by both stages. | Compose maps it to Dockerfile `ARG PYTHON_VERSION` (`docker-compose.yml:17`, `Dockerfile:9`). |
| `MAGIC_GEO_APP_UID` | `1000` (`.env.example:57`) | UID of the non-root `magicgeo` image user. Match `id -u` when host bind permissions require it. | Compose maps it to Dockerfile `ARG APP_UID` (`docker-compose.yml:19`, `Dockerfile:49`). |
| `MAGIC_GEO_APP_GID` | `1000` (`.env.example:58`) | GID of the non-root `magicgeo` image group. Match `id -g` when needed. | Compose maps it to Dockerfile `ARG APP_GID` (`docker-compose.yml:20`, `Dockerfile:50`). |
| `MAGIC_GEO_ENABLE_CUDA` | `OFF` (`.env.example:63`) | CMake switch selecting the portable CPU/OpenMP build or attempting the CUDA backend. The shipped Python builder has no `nvcc`, so `ON` alone still builds the stub. | Compose build arg (`docker-compose.yml:18`) forwarded to CMake (`Dockerfile:26-30`). |
| `MAGIC_GEO_NATIVE_LIBRARY` | empty (`.env.example:72`) | Optional container path overriding the wheel-bundled library. A non-empty value also needs a bind mount. | Compose injects it at `docker-compose.yml:29`; `native._library_path()` reads it (`src/magic_geo/native.py:110-118`). |

The template therefore covers every Compose substitution and every runtime override that the service injects. Build settings are not present in the runtime environment. The image also retains safe `ENV` defaults for host, port and workspace (`Dockerfile:63-66`), while Compose repeats them explicitly to keep port, mount and process configuration coupled even when `.env` is absent.

### The same variables outside Docker

`--workspace`, `--host` and `--port` are typer options with `envvar=` bindings, so **explicit flags win over the environment** (`cli/commands/serve.py:30`, `:36`, `:42`). `.env.example` is Docker-oriented; for a local process set the CLI variables directly:

```bash
MAGIC_GEO_WORKSPACE=runs MAGIC_GEO_HOST=127.0.0.1 magic-geo serve
```

`MAGIC_GEO_CONTAINER_WORKSPACE` is Compose-only and is not read by the Python CLI. Bare metal, `MAGIC_GEO_WORKSPACE=/app/runs` would usually be wrong because the workspace must resolve inside the process's cwd (`cli/commands/serve.py:50-63`); use an in-repo path such as `runs`.

---

## Persistence model

Inside the container the project root is `/app` (`Dockerfile:57`) and the workspace defaults to `/app/runs` (`Dockerfile:66`). Compose bind-mounts `${MAGIC_GEO_WORLDS_DIR}` at `${MAGIC_GEO_CONTAINER_WORKSPACE}` and passes that same target to the process as `MAGIC_GEO_WORKSPACE` (`docker-compose.yml:28,36`), so everything written under the workspace lands in the host directory and survives container replacement.

| Container path | Persisted? | What lives there | Source |
| --- | --- | --- | --- |
| `/app/runs` (= default `${MAGIC_GEO_CONTAINER_WORKSPACE}`) | **Yes** — bind-mounted from `${MAGIC_GEO_WORLDS_DIR}` | Generated worlds, browser-created configs, validation/calibration reports, renders, debug caches | `docker-compose.yml:28,36`, `Dockerfile:59,66` |
| `/app/runs/configs` | Yes (inside the mount) | Workbench "Save config" target — `target_dir = jobs.workspace / "configs"` (`debug_server.py:1020`) | `debug_server.py:1020` |
| `/app/runs/debug` | Yes (inside the mount) | Default debug-cache location auto-selected by `serve` when it contains `manifest.json` | `cli/commands/serve.py:64-69` |
| `/app/runs/.magic-geo-web/artifacts/<job_id>/…` | Yes (inside the mount) | Reserved job-manager directory holding immutable per-job artifact snapshots | `web_jobs.py:429-441` |
| `/app/configs` | **No** — baked into the image layer | Shipped seed configs, calibration source manifests, `calibration_fixtures/`, `seeds/` | `Dockerfile:58` |
| `/app` (other files) | No | Anything a CLI run writes outside `runs/`, e.g. `magic-geo init-config` with its default `magic-geo.yaml` output path (`cli/commands/config.py:17-20`) | — |
| `/home/magicgeo` | No | The container user's home, created by `useradd --create-home` | `Dockerfile:52` |
| Python site-packages | No | The installed wheel and `[debug]` dependencies | `Dockerfile:46` |

### How worlds survive a rebuild

The persistence guarantee has nothing to do with image layers. `docker compose up --build` produces a new `magic-geo:latest` and replaces the container; the host directory named by `MAGIC_GEO_WORLDS_DIR` is untouched and is re-mounted at the same container path. Concretely:

```bash
docker compose run --rm magic-geo generate \
  --config configs/earthlike_seed.yaml --output runs/world.json
# -> /app/runs/world.json -> ./worlds/world.json on the host

docker compose build --no-cache        # full rebuild of the native core and wheel
docker compose up -d                   # new container, same bind mount
docker compose run --rm magic-geo validate --world runs/world.json
# the world written before the rebuild is still there
```

The things that do **not** survive a rebuild are the image-resident paths: an edited `/app/configs/earthlike_seed.yaml` or a config written to `/app/magic-geo.yaml` is gone. Save configs under `runs/` (which is what the workbench's Config view does by default) if they must persist.

### Ownership

The bind mount masks the image's `/app/runs` (created and chowned at `Dockerfile:59`) with the host directory's ownership. The container runs as UID/GID 1000 by default (`Dockerfile:49-52`), matching the typical first-created Linux user. If your host user differs, set the documented Compose values before rebuilding:

```bash
MAGIC_GEO_APP_UID="$(id -u)" MAGIC_GEO_APP_GID="$(id -g)" \
  docker compose build
```

The equivalent raw Docker build args remain `APP_UID` and `APP_GID`.

### Workspace confinement still applies inside the container

The workbench's filesystem policy is unchanged by Docker: job **inputs** are confined to the project root `/app` — which includes the shipped `configs/` seeds — and job **outputs** to the workspace. `JobManager.__init__` re-applies the rule independently of the CLI, raising `ValueError("web workspace must be inside the project directory")` when it is violated (`web_jobs.py:421-427`), and reserves `<workspace>/.magic-geo-web/` (`web_jobs.py:429-441`). Set `MAGIC_GEO_CONTAINER_WORKSPACE` only to an absolute path under `/app`; Compose automatically keeps the mount target and runtime workspace identical.

---

## Running arbitrary CLI subcommands through the same image

`ENTRYPOINT ["magic-geo"]` with `CMD ["serve"]` (`Dockerfile:73-74`) means any argument list you pass to `docker compose run` replaces `serve` and becomes CLI arguments. The shorter deployment guide states the same contract: the image entrypoint is the CLI and `serve` is only its default command.

```bash
# one-off generation into the persistent worlds directory
docker compose run --rm magic-geo generate \
  --config configs/earthlike_seed.yaml --output runs/world.json

# backend/capability report
docker compose run --rm magic-geo backend

# validation against a generated world
docker compose run --rm magic-geo validate-geo \
  --world runs/world.json --output runs/geo_validation.json

# shell inside the running workbench container
docker compose exec magic-geo bash   # (entrypoint bypass: docker compose exec is not affected)
```

`docker compose run` starts a **new** container that shares the worlds volume with the workbench service, so generated files land in the same workspace; run `export-debug` on a world to make it selectable in the workbench's debug-cache picker.

Every registered subcommand is reachable this way. The complete set, as registered by `@app.command(...)`:

| Subcommand | Module | Notes for container use |
| --- | --- | --- |
| `generate` | `cli/commands/generate.py:18` | `--config` has `exists=True` and defaults to `magic-geo.yaml`, which does **not** exist in the image — always pass `--config configs/…`. `--output` defaults to `runs/world.json`, i.e. inside the mount. |
| `validate` | `cli/commands/validate.py:91` | — |
| `validate-geo` | `cli/commands/validate_geo.py:23` | — |
| `validate-geo-suite` | `cli/commands/validate_geo.py:91` | `configs/geo_validation_matrix.yaml` ships in the image. |
| `calibrate` | `cli/commands/calibrate.py:32` | Needs target bundles; empirical datasets live in host `calibration_data/`, which is **not** mounted by default. |
| `calibrate-ensemble` | `cli/commands/calibrate.py:94` | Same caveat. |
| `derive-targets` | `cli/commands/calibrate.py:202` | Reads a `--sources` JSON manifest. The real-dataset manifests (`configs/calibration_sources.etopo_2022_1deg.json`, `…worldclim_2_1_10m.json`, `…hydrorivers_v10.json`, `…hydrobasins_level3.json`, `…natural_earth_110m.json`, `…seton_2020_oceanic_age.json`) reference `calibration_data/` paths that are absent from the image; `configs/calibration_sources.example.json` points at the shipped `configs/calibration_fixtures/` synthetic grids and does run in the container. |
| `render` | `cli/commands/render.py:14` | SVG output; write under `runs/`. |
| `render-raster` | `cli/commands/render.py:60` | PPM output; write under `runs/`. |
| `export-debug` | `cli/commands/export.py:164` | With no `--output` it derives `<world parent>/debug` — for `runs/world.json` that is `runs/debug`, which `serve` then auto-selects (`cli/commands/serve.py:64-69`). |
| `export-debug-map` | `cli/commands/export.py:13` | Consumes an existing debug cache, not a world: `--debug-dir` defaults to `runs/debug` with `exists=True` (`cli/commands/export.py:15-24`). The renderer writes PNG plus a `.gpt-image-prompt.md` from the standard library, but it imports `debug_server` for `_DebugCache` (`debug_map_export.py:27`), which imports `duckdb` and `fastapi` at module scope (`debug_server.py:26-29`) — so it still needs the `[debug]` extra the image installs. |
| `export-rerun` | `cli/commands/export.py:208` | Requires the optional `rerun` package, which is **not** in the `[debug]` extra (`pyproject.toml:18-24`) and therefore not installed in the image. |
| `init-config` | `cli/commands/config.py:16` | Default `--output magic-geo.yaml` is written to `/app` and is lost with the container; pass `--output runs/<name>.yaml`. |
| `backend` | `cli/commands/config.py:52` | Prints `json.dumps(backend_info(), indent=2, sort_keys=True)` — the fastest way to confirm what the image's native core actually supports. |
| `serve` | `cli/commands/serve.py:13` | The `CMD` default. |

To run the workbench with a non-default subcommand *and* published ports you must use the service container (`docker compose up`); `docker compose run` is intended for one-off CLI work, and the compose file does not configure port publication for one-off runs.

---

## Loopback-only publication and the security model

The compose port mapping is host-interface-qualified:

```yaml
# docker-compose.yml:30-34
    ports:
      # The workbench has no authentication; the default publishes only on
      # loopback. Set MAGIC_GEO_PUBLISH_HOST=0.0.0.0 only behind a trusted
      # network boundary or authenticating reverse proxy.
      - "${MAGIC_GEO_PUBLISH_HOST:-127.0.0.1}:${MAGIC_GEO_PORT:-8642}:${MAGIC_GEO_PORT:-8642}"
```

Two different bind addresses are in play and they are not interchangeable:

| Address | Scope | Default | Effect of changing it |
| --- | --- | --- | --- |
| `MAGIC_GEO_HOST` | Inside the container's network namespace, passed to uvicorn via `serve --host` (`cli/commands/serve.py:109-114`) | `0.0.0.0` | Setting `127.0.0.1` inside Docker makes the server unreachable from the published port; the healthcheck (which also uses loopback) would still pass. |
| `MAGIC_GEO_PUBLISH_HOST` | The **host** interface Docker publishes on | `127.0.0.1` | Setting `0.0.0.0` exposes an unauthenticated application to every network the host is on. |

`docs/docker_deployment.md` states the model plainly:

> The web workbench is a trusted-local, single-user tool with no authentication or user isolation. The compose file therefore publishes the port on `127.0.0.1` by default even though the server binds `0.0.0.0` inside the container's network namespace. To serve it beyond the local machine, front it with an authenticating reverse proxy and set `MAGIC_GEO_PUBLISH_HOST` deliberately.

### What an unauthenticated reachable port grants

The workbench's own security documentation describes its boundaries as containment measures, **not** a tenant boundary. Anyone who can reach the port can, without credentials:

- read every table, layer, cell record, stage history, family, and model section of the selected debug cache (`/api/manifest`, `/api/catalog`, `/api/layer/*`, `/api/cell/*`, `/api/section/*`);
- enumerate and select any debug cache under the workspace (`/api/worlds`, `/api/worlds/select`);
- **submit background jobs** that run `sys.executable -m magic_geo …` subprocesses inside the container (`POST /api/jobs`), and cancel them;
- write files into the workspace — which is the bind-mounted host directory — via any job with an output path, and via `POST /api/config/save`;
- download per-job artifact snapshots.

The mitigations that do exist are path-containment and input-typing measures: component-aware `Path.relative_to` confinement rather than string prefixes, inputs confined to the project root and outputs to the workspace, a reserved `.magic-geo-web` directory, a restricted config-name regex with symlink rejection, a 1,000,000-byte cap on submitted YAML, DuckDB identifier quoting for column names, and a fixed non-shell subprocess argv. None of these authenticate the caller.

### Exposing it safely

If you must reach it from elsewhere, keep `MAGIC_GEO_PUBLISH_HOST=127.0.0.1` and terminate authentication in a reverse proxy on the same host, or place the whole deployment behind a trusted network boundary before changing the publish host. The repository does not ship a proxy configuration, a TLS setup, or any authentication middleware, and none of `docker-compose.yml`, `Dockerfile`, or `.env.example` references one.

---

## GPU passthrough: what is and is not verified

### What the default image does

`docs/docker_deployment.md`:

> The default image builds the CPU/OpenMP core with the CUDA runtime stub. The OpenCL backend is loaded through `dlopen` at runtime, so it activates when the container has an OpenCL ICD and a device (e.g. `--device` / `--gpus` plus the vendor runtime image or host libraries mounted in).

The `dlopen` claim is verifiable in the native source — `cpp/src/opencl_compute.cpp:162-164` tries `libOpenCL.so.1` and then `libOpenCL.so`, so OpenCL is never a build-time dependency. But the runtime stage installs only `libgomp1` (`Dockerfile:41-43`): **the default image contains no OpenCL ICD loader**, so `dlopen` will fail there unless one is installed or mounted in. Neither `docker-compose.yml` nor `Dockerfile` provides devices, an ICD, or a vendor runtime.

### What a CUDA image would require

`docs/docker_deployment.md`:

> For the native CUDA backend, switch the builder stage's base image to a CUDA 12.8+ development image (e.g. `nvidia/cuda:12.8.0-devel-ubuntu24.04` with Python installed), pass `MAGIC_GEO_ENABLE_CUDA=ON` (build arg, also read from `.env` by Compose), and run the container with `--gpus all` / `gpus: all`.

| Step | Status in this repository |
| --- | --- |
| Set `MAGIC_GEO_ENABLE_CUDA=ON` in `.env` | Supported and wired end-to-end (`.env.example:63` → `docker-compose.yml:18` → `Dockerfile:26` → `-DMAGIC_GEO_ENABLE_CUDA`). |
| Builder base image swap to a CUDA devel image | **Not implemented.** `Dockerfile:12` is hard-coded to `python:${PYTHON_VERSION}-slim`; the change is described in prose only. There is no build arg for the base image. |
| Runtime stage CUDA driver/runtime | Not needed for `libcudart` (CUDA targets set `CUDA_RUNTIME_LIBRARY Static`), but a compatible NVIDIA kernel driver is still required — `docs/cuda_rtx5090_optimization.md:62-66` is explicit that "static `cudart` does not bundle the driver". |
| `gpus: all` in the compose file | **Absent.** `docker-compose.yml` has no GPU reservation of any kind; you must add it yourself or use `docker run --gpus all`. |
| OpenCL ICD in the runtime image | **Absent** (`Dockerfile:41-43` installs `libgomp1` only). |
| Any verification that a GPU-enabled image builds or runs | **None.** The Docker contract test is static and CPU-oriented; `docs/docker_deployment.md` records no GPU container run. |

Treat the entire GPU-container path as documented intent that is **not verified in source**.

### The accelerator claims that are explicitly unresolved

Even outside Docker, the repository is deliberate about what acceleration does and does not mean. The backend telemetry emitted by `backend_info()` — reachable in the container with `docker compose run --rm magic-geo backend` — carries these fixed strings and flags:

| Telemetry key | Value | Source |
| --- | --- | --- |
| `backend_scope` | `"accelerated_native_kernels_not_end_to_end_pipeline"` | `cpp/src/opencl_compute.cpp:2064-2065` |
| `crust_transport_execution_backend` | `"cpu"` | `cpp/src/opencl_compute.cpp:2070-2071` |
| `crust_overlap_continuous_shadow_only` | `true` | `cpp/src/opencl_compute.cpp:2130` |
| `crust_overlap_continuous_shadow_authoritative` | `false` | `cpp/src/opencl_compute.cpp:2136` |
| `crust_overlap_continuous_shadow_result_used_for_state` | `false` | `cpp/src/opencl_compute.cpp:2142` |
| `crust_overlap_accelerator_geometry_parity_demonstrated` | `false` | `cpp/src/opencl_compute.cpp:2148` |
| `crust_overlap_accelerator_coverage_membership_parity_demonstrated` | `false` | `cpp/src/opencl_compute.cpp:2154` |
| `crust_overlap_accelerator_categorical_parity_demonstrated` | `false` | `cpp/src/opencl_compute.cpp:2160` |
| `crust_overlap_accelerator_complete_parity_demonstrated` | `false` | `cpp/src/opencl_compute.cpp:2166` |
| `crust_overlap_accelerator_state_authoritative` | `false` | `cpp/src/opencl_compute.cpp:2172` |
| `cuda_compiled` | `true` only when `MAGIC_GEO_HAS_CUDA` was defined at compile time | `cpp/src/opencl_compute.cpp:2354-2359` |
| `opencl_available` | `qualifying_device_count > 0` from the runtime probe | `cpp/src/opencl_compute.cpp:2570` |

`docs/cuda_rtx5090_optimization.md:7-17` states the boundary directly: production v3 crust transport "now runs authoritatively on CPU for `cpu`, `opencl`, and `cuda` backends", the historical CUDA nearest-source kernel "has since been removed", and "authoritative GPU transport, complete-ledger parity, and new crossover calibration remain pending". What ships on the accelerator path is a diagnostic-only continuous-moment shadow reduction whose "device results are reconciled and discarded, never used as state." Adding a GPU to the container therefore does not make the simulation GPU-authoritative.

### Verifying what you actually got

```bash
docker compose run --rm magic-geo backend
```

Read `native_core`, `openmp_enabled`, `openmp_max_threads` (`cpp/src/opencl_compute.cpp:2036-2046`), `cuda_compiled` (`:2359`), `cuda_capability_status` (`:2361-2366`, one of `not_probed` / `not_compiled` / `available` / `unavailable`), `cuda_error` (`:2372`), and `opencl_available` / `opencl_error` (`:2570-2571`). In a default image expect `cuda_compiled: false` and `opencl_available: false`; anything else means your image or runtime differs from the shipped definition.

---

## Image size and build-time expectations

**The repository states no image size and no build-time figure.** `Dockerfile`, `docker-compose.yml`, `.env.example` and `docs/docker_deployment.md` contain no MB/GB numbers and no wall-clock estimates (verified by search). Any figure you have seen elsewhere is not sourced from this repository, and none is asserted here.

What the source *does* determine about build cost:

| Factor | Source | Effect |
| --- | --- | --- |
| Native compilation is the dominant step | `Dockerfile:27-31` builds `magic_geo_native` from `cpp/src/c_api.cpp`, `cpp/src/engine.cpp`, 28 `cpp/src/engine/*.cpp` units, the CUDA source-or-stub, `cpp/src/crust_overlap_shadow.cpp`, and `cpp/src/opencl_compute.cpp` (`CMakeLists.txt:94-…`) | Scales with `nproc`; the build uses `-j"$(nproc)"`. |
| Tests are skipped | `-DBUILD_TESTING=OFF` (`Dockerfile:29`) gates the whole CTest block (`CMakeLists.txt:223`) | No test executables are compiled or run during the image build. |
| Build toolchain is discarded | Builder stage output reaches the runtime only through a BuildKit `--mount` of `/wheels` (`Dockerfile:45-46`) | `build-essential`, `cmake`, the CMake build tree, and the wheel file are all absent from the final image. |
| The `[debug]` extra is heavyweight | `pyarrow>=19`, `duckdb>=1.2`, `fastapi>=0.115`, `uvicorn[standard]>=0.34` (`pyproject.toml:19-24`) | These wheels are the largest Python contribution to the runtime layer. |
| Both stages need network | `pip wheel` performs a PEP 517 build resolving `setuptools>=70.1` (`pyproject.toml:1-3`); the runtime `pip install` has no `--no-deps` (`Dockerfile:46`) | Offline builds are not supported by the shipped definition. |

---

## Operations troubleshooting

| Symptom | Likely cause | Where to look | Fix |
| --- | --- | --- | --- |
| Container starts, but the workbench cannot write worlds; permission errors in `docker compose logs` | `worlds/` was auto-created by Docker and is owned by root, while the container runs as UID 1000 | `docs/docker_deployment.md`, `Dockerfile:49-52` | Create `worlds/` as your user before the first `up`; or set `MAGIC_GEO_APP_UID="$(id -u)"` and `MAGIC_GEO_APP_GID="$(id -g)"`, then rebuild. |
| `Web workspace must stay inside /app: <path>` and exit code 2 | `MAGIC_GEO_CONTAINER_WORKSPACE` points outside the container project root | `docker-compose.yml:28,36`, `cli/commands/serve.py:50-63` | Keep the setting at an absolute path under `/app` (default `/app/runs`). Compose keeps the mount and runtime workspace coupled. |
| Docker rejects the volume target as relative | `MAGIC_GEO_CONTAINER_WORKSPACE` was set to a host-style value such as `runs` | `.env.example:22-27`, `docker-compose.yml:36` | Use an absolute container path under `/app`. For bare metal, set the separate `MAGIC_GEO_WORKSPACE=runs` variable directly on the local process. |
| Port 8642 unreachable from the host even though the container is up | `MAGIC_GEO_HOST` was set to `127.0.0.1` inside the container | `.env.example:33-36`, `cli/commands/serve.py:34-37` | Keep `MAGIC_GEO_HOST=0.0.0.0` in Docker; restrict exposure with `MAGIC_GEO_PUBLISH_HOST` instead. |
| Changed `MAGIC_GEO_PORT`, but the old port is still active | The existing container has not been recreated with the new Compose environment and mapping | `docker-compose.yml:27,34`, `Dockerfile:70-71` | Run `docker compose up -d` to recreate it. The runtime port, published target and healthcheck then use the same value. |
| Container reports `unhealthy` | `/api/status` unreachable within the 4 s `urlopen` timeout, or an error status; server not yet up within the 15 s start period | `Dockerfile:70-71`, `debug_server.py:928-938` | `docker compose logs magic-geo`; check the uvicorn startup line `Serving web workbench … at http://<host>:<port>` (`cli/commands/serve.py:108`). |
| `Serving requires the optional debug dependencies: pip install 'magic-geo[debug]'` and exit 2 | The wheel was installed without the `[debug]` extra | `cli/commands/serve.py:76-82`, `Dockerfile:46` | Rebuild the image; the shipped `Dockerfile` already installs `[debug]`. |
| `Ignoring invalid automatic cache <dir>: <error>` at startup | `<workspace>/debug` exists but its manifest or a referenced file is invalid | `cli/commands/serve.py:83-99` | Non-fatal — the server restarts cacheless and Config/Operations/Backend/jobs stay usable. Re-run `export-debug`. |
| `No manifest.json in <dir>; choose an export-debug cache or omit -d` and exit 2 | Explicit `-d` pointed at a directory without a cache manifest | `cli/commands/serve.py:70-75` | Point `-d` at a real `export-debug` output, or omit it for auto-discovery. |
| `MAGIC_GEO_ENABLE_CUDA=ON` in `.env`, but `backend` still reports `cuda_compiled: false` | The shipped builder base has no `nvcc`, so CMake logs `compiler not found; building runtime stub` and the build still succeeds | `CMakeLists.txt:64-66`, `:19`, `Dockerfile:12` | Switch the builder stage to a CUDA 12.8+ devel base image as described in the deployment guide — the `.env` flag alone is not sufficient. |
| Changed `MAGIC_GEO_ENABLE_CUDA` but nothing changed | Build args are only applied at build time | `docker-compose.yml:16-20` | Re-run with `docker compose up --build` (or `docker compose build --no-cache`). |
| `magic-geo backend` reports `opencl_available: false` inside the container | The runtime image installs `libgomp1` only, so `dlopen("libOpenCL.so.1")` / `dlopen("libOpenCL.so")` finds nothing | `Dockerfile:41-43`, `cpp/src/opencl_compute.cpp:162-164` | Install or mount a vendor ICD and expose a device; not configured by the shipped compose file. |
| `docker compose run --rm magic-geo generate` fails immediately with a missing-file error on `--config` | `--config` defaults to `magic-geo.yaml` with `exists=True`, and that file is not in the image | `cli/commands/generate.py:20-22` | Always pass `--config configs/earthlike_seed.yaml` (or another shipped/`runs/`-resident config). |
| `export-rerun` exits 2 asking for `pip install rerun-sdk` | `rerun` is an optional dependency and is not part of the `[debug]` extra installed in the image | `pyproject.toml:18-24`, `cli/commands/export.py:208` | Install `rerun-sdk` in a derived image, or run `export-rerun` outside the container. |
| `RuntimeError: MAGIC_GEO_NATIVE_LIBRARY does not name a file: <path>` | The override names a host path that does not exist inside the container | `src/magic_geo/native.py:110-118` | Leave `MAGIC_GEO_NATIVE_LIBRARY=` empty for the bundled library, or add a bind mount for the override path. |
| Calibration commands fail on missing empirical datasets | `calibration_data/` is `.dockerignore`d and not mounted | `.dockerignore:25-27` | Add an explicit read-only bind mount for `calibration_data/`, or run calibration outside the container. |
| Config edits under `/app/configs` disappear | `configs/` is an image layer, not the volume | `Dockerfile:58` | Save configs under `runs/` (the workbench's Config view already defaults to `<workspace>/configs`). |
| Image rebuilt but Python still loads an old native core | The host `src/magic_geo/*.so` cannot leak in — it is `.dockerignore`d — so this indicates a stale image, not a stale library | `.dockerignore:20-22` | `docker compose build --no-cache`; confirm with `docker compose run --rm magic-geo backend`. |

---

## Limitations and unresolved claims

- **Automated Docker coverage is static, not daemon-backed.** `tests/test_docker_configuration.py` locks the `.env.example`/Compose variable surface, absolute container workspace, coupled workspace/volume and port mapping, explicit runtime environment, non-root image user, and healthcheck route. The suite does not build an image or start a Docker daemon; an actual build and smoke run remain release/integration checks.
- **The GPU container path is prose, not implementation.** `Dockerfile:12` hard-codes `python:${PYTHON_VERSION}-slim` for the builder, `docker-compose.yml` declares no GPU reservation or device, and the runtime stage installs no OpenCL ICD. The GPU section of `docs/docker_deployment.md` describes what you would have to change; nothing in the repository verifies that a CUDA-enabled image builds, runs, or produces correct output. Mark this as not verified in source.
- **Acceleration is explicitly not end-to-end and not authoritative.** Backend telemetry hard-codes `backend_scope = "accelerated_native_kernels_not_end_to_end_pipeline"` (`cpp/src/opencl_compute.cpp:2064-2065`) and `crust_transport_execution_backend = "cpu"` (`:2070-2071`), and every accelerator parity flag — geometry, coverage-membership, categorical, and complete — is hard-coded `false` (`:2148`, `:2154`, `:2160`, `:2166`), as is `crust_overlap_accelerator_state_authoritative` (`:2172`). The device-side continuous-moment shadow is diagnostic only: its "device results are reconciled and discarded, never used as state" (`docs/cuda_rtx5090_optimization.md:7-17`). Attaching a GPU to the container does not change any of this.
- **`MAGIC_GEO_ENABLE_CUDA=ON` fails open, not closed.** With no `nvcc` in the builder, CMake emits a `STATUS` message and builds `cuda_compute_stub.cpp` (`CMakeLists.txt:19`, `:64-66`). The image build succeeds and produces a stub; there is no error to alert you.
- **No image size or build-duration figures exist in the repository.** None is asserted here.
- **No authentication, authorization, TLS, or per-user isolation exists at any layer of the deployment.** The loopback publish default (`docker-compose.yml:34`) is the only barrier the repository provides, and it is a network-placement choice, not an access control. `docs/docker_deployment.md` describes the workbench as "a trusted-local, single-user tool".
- **The single-wheel glob is unguarded.** `"$(echo /wheels/*.whl)[debug]"` (`Dockerfile:46`) expands to whitespace-separated paths if `/wheels` ever contains more than one wheel. `--no-deps` at `Dockerfile:35` is what keeps that from happening; the `Dockerfile` does not otherwise assert it.
- **`EXPOSE 8642` is a literal.** It does not track `MAGIC_GEO_PORT` (`Dockerfile:68`). This is metadata only and does not affect the Compose publication, but tooling that reads exposed ports will report `8642` regardless of configuration.
- **`restart: unless-stopped` does not react to health.** An unhealthy container that has not exited is not restarted (`docker-compose.yml:37`).
- **Relative-path resolution for `MAGIC_GEO_WORLDS_DIR` is delegated to Compose.** `.env.example:16-20` documents resolution against the Compose project directory; the repository does not perform a separate preflight check of the resulting host path.
- **Multi-architecture images are out of scope.** The wheel is tagged OS/architecture-specific (`setup.py:43-45`), so the image is valid only for the architecture it was built on. No cross-build or `buildx` configuration ships with the repository.

---

## See also

- [Installation and Build](./02-installation-and-build.md) — bare-metal CMake and wheel workflow, the native library discovery order, and build-type isolation.
- [Quickstart](./03-quickstart.md) — the shortest path from a fresh checkout to a generated world.
- [Configuration Reference](./05-configuration-reference.md) — the YAML schema the shipped `configs/` seeds instantiate.
- [CLI Reference](./06-cli-reference.md) — every subcommand reachable through the image entrypoint, with full flag tables.
- [Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md) — backend selection, the telemetry keys quoted above, and the authoritative-vs-shadow boundary.
- [Native Engine (C++ Core)](./08-native-engine.md) — what the builder stage actually compiles and the ABI the wheel gate checks.
- [Web Workbench](./15-web-workbench.md) — the server the container runs by default, its routes, job system, and filesystem policy.
- [Debug Exports and Visualization](./16-debug-and-visualization.md) — `export-debug` caches, which are what the workbench's picker lists from the mounted workspace.
- [Testing and Quality Gates](./18-testing.md) — the suite that `BUILD_TESTING=OFF` skips during the image build.
- [Troubleshooting and FAQ](./22-troubleshooting.md) — non-container failure modes.
