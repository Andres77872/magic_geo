#!/usr/bin/env bash
# Local workbench with an editable Python environment and source reload.
set -euo pipefail

dev_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
dev_build=true
dev_install=false
dev_reload=true
dev_server_args=()

while (($#)); do
    case "$1" in
        --no-build) dev_build=false ;;
        --install) dev_install=true ;;
        --no-reload) dev_reload=false ;;
        -h|--help)
            cat <<'HELP'
Usage: scripts/dev.sh [--no-build] [--install] [--no-reload] [uvicorn options]

Creates/reuses .venv, installs missing development dependencies, builds the
native core incrementally, and starts http://127.0.0.1:8642 with Python reload.
Run from any directory. Relative paths are anchored to the checkout.

  --no-build    Use an already built native library
  --install     Refresh the editable install and debug/test dependencies
  --no-reload   Keep long-running jobs alive while editing Python files
  --port 8765   Override the listening port (other uvicorn options also work)

Optional .env.local contains shell-compatible environment assignments.
Its values override the shell; command-line server options take precedence.
Copy .env.local.example to get started. Docker's .env is not loaded.

MAGIC_GEO_DEV_PYTHON     Python used to create the venv (default: python3)
MAGIC_GEO_DEV_VENV       Virtual environment directory (default: .venv)
MAGIC_GEO_DEV_BUILD_DIR  CMake build directory (default: build)
CMAKE_BUILD_PARALLEL_LEVEL controls build concurrency (default: 2).
All MAGIC_GEO runtime path, host, port and native-library settings apply.
HELP
            exit 0
            ;;
        --) shift; dev_server_args+=("$@"); break ;;
        *) dev_server_args+=("$1") ;;
    esac
    shift
done

cd -- "$dev_root"
if [[ -f .env.local ]]; then
    set -a
    # This is a local, shell-compatible settings file, like a service env file.
    source .env.local
    set +a
fi

dev_venv="${MAGIC_GEO_DEV_VENV:-$dev_root/.venv}"
dev_python="$dev_venv/bin/python"
if [[ ! -x "$dev_python" ]]; then
    printf 'Creating Python environment: %s\n' "$dev_venv"
    "${MAGIC_GEO_DEV_PYTHON:-python3}" -m venv "$dev_venv"
fi
"$dev_python" -c 'import sys; sys.exit("Python 3.11+ is required") if sys.version_info < (3, 11) else None'

# Keep both the server and its background CLI jobs on this checkout's source.
export PYTHONPATH="$dev_root/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1
if [[ "$dev_install" == true ]] || ! "$dev_python" -c \
    'import msgpack, pydantic, yaml, typer, pyarrow, duckdb, fastapi, uvicorn, watchfiles, pytest' \
    >/dev/null 2>&1; then
    printf 'Installing editable project and development dependencies…\n'
    "$dev_python" -m pip install -e '.[debug,test]'
fi

if [[ "$dev_build" == true && -z "${MAGIC_GEO_NATIVE_LIBRARY:-}" ]]; then
    if ! command -v cmake >/dev/null 2>&1; then
        printf 'CMake 3.20+ and a C++20 compiler are required; use --no-build with a prebuilt core.\n' >&2
        exit 1
    fi
    dev_build_dir="${MAGIC_GEO_DEV_BUILD_DIR:-$dev_root/build}"
    cmake -S "$dev_root" -B "$dev_build_dir" -DCMAKE_BUILD_TYPE=Release
    cmake --build "$dev_build_dir" --config Release --target magic_geo_native \
        --parallel "${CMAKE_BUILD_PARALLEL_LEVEL:-2}"
fi
"$dev_python" -c 'from magic_geo.api import backend_info; info = backend_info(); print("Native core ready: " + str(info.get("active_backend", "available")))'

dev_reload_args=()
if [[ "$dev_reload" == true ]]; then
    dev_reload_args=(--reload --reload-dir "$dev_root/src/magic_geo")
    printf 'Python edits restart the server and stop active jobs; use --no-reload for long runs.\n'
fi
printf 'UI edits appear on browser refresh. Stop the server with Ctrl+C.\n'
exec "$dev_python" -m uvicorn magic_geo.debug_server:create_app --factory \
    --host "${MAGIC_GEO_HOST:-127.0.0.1}" --port "${MAGIC_GEO_PORT:-8642}" \
    "${dev_reload_args[@]}" "${dev_server_args[@]}"
