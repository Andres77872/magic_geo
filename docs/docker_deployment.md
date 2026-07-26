# Docker Deployment

The repository ships an all-in-one container image: the C++ native core is
compiled during the image build, the Python CLI and the web workbench are
installed on top, and one image serves every entry point. `docker compose up`
starts the browser workbench; `docker compose run` executes any CLI command
with the same image and the same persistent worlds directory.

## Quick start

```bash
cp .env.example .env      # adjust if needed; defaults work out of the box
mkdir -p worlds           # host directory that stores generated worlds
docker compose up --build -d
# web workbench: http://127.0.0.1:8642
```

Create the worlds directory yourself before the first `up` so it is owned by
your user; if Docker auto-creates it, it belongs to root and the non-root
container user cannot write worlds into it.

## Configuration: `.env`

Docker Compose reads `.env` automatically for `${...}` substitution in
`docker-compose.yml`. The Compose file explicitly injects only the runtime
settings consumed by the process; host paths and image build settings remain
Compose-only. `.env` is gitignored; `.env.example` is the tracked, documented
template.

| Variable | Default | Meaning |
| --- | --- | --- |
| `MAGIC_GEO_WORLDS_DIR` | `./worlds` | Host directory where worlds are saved. Bind-mounted into the container workspace, so worlds survive rebuilds. |
| `MAGIC_GEO_CONTAINER_WORKSPACE` | `/app/runs` | Absolute workspace path inside the container. Compose uses it for both the bind-mount target and the process's `MAGIC_GEO_WORKSPACE`. Must stay inside `/app`. |
| `MAGIC_GEO_HOST` | `0.0.0.0` | Bind address inside the container. Keep `0.0.0.0` in Docker so the published port can reach the server. |
| `MAGIC_GEO_PORT` | `8642` | Workbench port (bound inside the container and published on the host). |
| `MAGIC_GEO_PUBLISH_HOST` | `127.0.0.1` | Host interface the port is published on. The workbench has no authentication — keep loopback unless a trusted boundary or authenticating proxy protects it. |
| `MAGIC_GEO_PYTHON_VERSION` | `3.13` | Python slim-image version for both build stages. Build-time only. |
| `MAGIC_GEO_APP_UID` | `1000` | UID assigned to the non-root `magicgeo` image user. Build-time only; match `id -u` when needed for bind-mount permissions. |
| `MAGIC_GEO_APP_GID` | `1000` | GID assigned to the non-root `magicgeo` image group. Build-time only; match `id -g` when needed for bind-mount permissions. |
| `MAGIC_GEO_ENABLE_CUDA` | `OFF` | Build argument for the native CUDA backend (see below). |
| `MAGIC_GEO_NATIVE_LIBRARY` | empty | Optional container path overriding the native shared library loaded through `ctypes`. A non-empty path also needs a bind mount. |

Changing a build-time value requires `docker compose build` or
`docker compose up --build`. `MAGIC_GEO_CONTAINER_WORKSPACE` is intentionally
different from the CLI's `MAGIC_GEO_WORKSPACE`: a bare-metal value such as
`runs` must never become a relative Docker mount target.

Outside Docker, `MAGIC_GEO_WORKSPACE`, `MAGIC_GEO_HOST`, and `MAGIC_GEO_PORT`
back the `--workspace`, `--host`, and `--port` options (flags win):

```bash
MAGIC_GEO_WORKSPACE=runs MAGIC_GEO_HOST=127.0.0.1 magic-geo serve
```

## How worlds are persisted

Inside the container the project root is `/app` and the workspace defaults to
`/app/runs`. Compose bind-mounts `${MAGIC_GEO_WORLDS_DIR}` (host) onto
`${MAGIC_GEO_CONTAINER_WORKSPACE}` (container) and passes that target to the
process as `MAGIC_GEO_WORKSPACE`, so everything the workbench or CLI writes
under the workspace — worlds, browser-created configs, validation reports,
debug caches, renders — lands in the host directory and survives container
replacement.

The workbench's security model is unchanged in Docker: job inputs are confined
to the project root (`/app`, which includes the shipped `configs/` seeds) and
job outputs to the workspace. Point `MAGIC_GEO_WORKSPACE` somewhere else only
by changing `MAGIC_GEO_CONTAINER_WORKSPACE`, and only if the new path remains
inside `/app`.

## Running CLI commands in the container

The image entrypoint is the `magic-geo` CLI; `serve` is only the default
command. Any other subcommand works with the same image and volume:

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

Note that `docker compose run` starts a new container that shares the worlds
volume with the workbench service, so generated files land in the same
workspace. Run `export-debug` on a world to make it selectable in the
workbench's debug-cache picker.

## Image layout

- **Builder stage** (`python:3.13-slim` by default + `build-essential` +
  `cmake`):
  compiles `libmagic_geo_native.so` in Release mode with OpenMP, then builds
  the platform wheel. The wheel build loads the staged library and verifies
  its exported ABI symbols, so a broken native build fails the image build.
- **Runtime stage** (`python:3.13-slim` by default + `libgomp1`): installs the
  wheel with the `[debug]` extra (FastAPI, uvicorn, pyarrow, duckdb), runs as the
  non-root user `magicgeo` (UID/GID 1000 by default, overridable with the
  `MAGIC_GEO_APP_UID`/`MAGIC_GEO_APP_GID` Compose settings), and exposes a
  `HEALTHCHECK` against `/api/status`. `MAGIC_GEO_PYTHON_VERSION` selects the
  slim-image version for both stages.

## GPU notes

The default image builds the CPU/OpenMP core with the CUDA runtime stub. The
OpenCL backend is loaded through `dlopen` at runtime, so it activates when the
container has an OpenCL ICD and a device (e.g. `--device` /
`--gpus` plus the vendor runtime image or host libraries mounted in).

For the native CUDA backend, switch the builder stage's base image to a CUDA
12.8+ development image (e.g. `nvidia/cuda:12.8.0-devel-ubuntu24.04` with
Python installed), pass `MAGIC_GEO_ENABLE_CUDA=ON` (build arg, also read from
`.env` by Compose), and run the container with `--gpus all` /
`gpus: all`. See `docs/cuda_rtx5090_optimization.md` for architecture flags.

## Security

The web workbench is a trusted-local, single-user tool with no authentication
or user isolation. The compose file therefore publishes the port on
`127.0.0.1` by default even though the server binds `0.0.0.0` inside the
container's network namespace. To serve it beyond the local machine, front it
with an authenticating reverse proxy and set `MAGIC_GEO_PUBLISH_HOST`
deliberately.
