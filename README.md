# magic-geo

Procedural planet generation with a C++20 simulation core, a Python API and CLI,
and a local web workbench.

Generate spherical worlds with tectonics, terrain, seasonal climate, rivers,
lakes, groundwater, ice, soils, biomes and resources. Full generation adds
settlements, routes, territories, cultures and history; `--geo-only` keeps natural
geography. Worlds can be saved as JSON or binary MessagePack-based `.mgeo` files.

![The magic-geo workbench showing a globe colored by biome](src/magic_geo/debug_ui/assets/workbench-map.webp)

The physical and ecological models are still under development. The `earthlike`
profile supplies Earth reference inputs; it is **not calibrated for the current
seasonal climate model**. See the [current simulation review](docs/current_simulation_review_status.md)
for verified behavior and remaining limitations.

## Quick start

Requires Python 3.11+, CMake 3.20+ and a C++20 compiler. Run these commands from
the repository root in a Bash-compatible shell:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DMAGIC_GEO_ENABLE_CUDA=OFF
cmake --build build --config Release --target magic_geo_native --parallel 2
magic-geo backend
```

This builds the CPU core and stages its shared library beside the Python package.
OpenMP is used when available. CUDA 12.8+ is optional; see
[compute backends](docs/wiki/09-compute-backends.md) for GPU setup. Build the
Release native library before packaging a wheel.

Generate, validate and render a small 128-cell world:

```bash
magic-geo generate --config configs/seasonal_smoke.yaml \
  --output runs/smoke/world.json \
  --summary runs/smoke/summary.md --cells-csv runs/smoke/cells.csv
magic-geo validate --world runs/smoke/world.json
magic-geo render --world runs/smoke/world.json \
  --output runs/smoke/world.svg --projection mollweide --labels
```

Use an output suffix of `.mgeo` for binary serialization. Commands that read
worlds accept both formats. For natural geography only:

```bash
magic-geo generate --geo-only --config configs/seasonal_smoke.yaml \
  --output runs/smoke/geo-world.mgeo
magic-geo validate-geo --world runs/smoke/geo-world.mgeo
```

## Configuration

Create a YAML configuration from the `default`, `earthlike` or `smoke` profile.
Repeat `--set section.field=value` to apply typed overrides:

```bash
magic-geo init-config --profile earthlike \
  --set mesh.cell_count=512 --output runs/configs/my-world.yaml
magic-geo generate --config runs/configs/my-world.yaml --output runs/my-world.json
```

YAML files require `config_version: 2`; unknown fields and duplicate keys are
rejected. Unversioned files require migration. `magic-geo init-config` without
options writes an Earth-reference template to `magic-geo.yaml`, the default
input for `generate`.

Nine additional presets live in [`configs/seeds`](configs/seeds). See the
[seed gallery](docs/example_seed_gallery.md) for their intended scenarios and
limitations, and the [configuration helpers](docs/configuration_helpers.md)
for parsing, validation and overrides.

## Python API

```python
from pathlib import Path

from magic_geo import load_config
from magic_geo.api import generate_world
from magic_geo.io import write_world

config = load_config("configs/seasonal_smoke.yaml")
world = generate_world(config)
write_world(Path("runs/python/world.mgeo"), world)
```

Use `generate_geo_world(config)` for natural geography only; it requires
`output.include_cells: true`. `WorldConfig()` and `create_config(profile,
overrides)` also construct configurations directly. See the
[Python API reference](docs/wiki/07-python-api.md).

## Web workbench

After building the native core, install the optional web dependencies and start
the server:

```bash
python -m pip install -e '.[debug]'
magic-geo serve
```

Open <http://127.0.0.1:8642> to configure worlds, run background jobs, explore
layers on globe or flat maps, and inspect exported records. API documentation
is available at `/api/docs`.

- `--workspace <dir>` selects storage for browser-created files (default: `runs`).
- `--host` and `--port` change the listening address. These and `--workspace`
  also accept `MAGIC_GEO_HOST`, `MAGIC_GEO_PORT` and `MAGIC_GEO_WORKSPACE`.
- `-d <cache>` opens an existing `export-debug` cache.

For development, `./scripts/dev.sh` creates or reuses `.venv`, installs missing
dependencies, builds the core and starts the workbench with Python reload.
Use `--no-reload` for long jobs; reload stops active jobs. Refresh the browser
after UI edits and restart the script after C++ changes.

The workbench has no authentication or user isolation. Keep its default loopback
binding unless a trusted network boundary or authenticating proxy protects it.
See the [workbench guide](docs/debug_ui_guide.md) and
[runtime storage guide](docs/runtime_storage.md).

## Docker

```bash
cp .env.example .env
mkdir -p worlds
docker compose up --build -d
```

Open <http://127.0.0.1:8642>. By default, generated files persist in `./worlds`
on the host, mounted at `/app/runs` in the container. Configure paths, ports
and the container UID/GID in `.env` before building. The same image runs CLI
commands:

```bash
docker compose run --rm magic-geo generate \
  --config configs/seasonal_smoke.yaml --output runs/world.json
```

See [Docker deployment](docs/docker_deployment.md) for storage, GPU setup and
network configuration.

## Development and testing

```bash
python -m pip install -e '.[test,debug]'
python -m pytest -m "not slow"
python -m pytest                         # includes exhaustive CLI validation
cmake --build build --config Release --parallel 2
ctest --test-dir build -C Release --output-on-failure
```

The native tests require CMake's `BUILD_TESTING=ON` (the default). Python coverage
is available with `python -m pytest --cov --cov-report=term-missing`; it does not
measure the C++ core. See the [testing guide](docs/wiki/18-testing.md).

## Documentation

- [Wiki index](docs/wiki/README.md): overview, architecture and reference guides.
- [Configuration reference](docs/wiki/05-configuration-reference.md) and
  [CLI reference](docs/wiki/06-cli-reference.md).
- [World schema](docs/wiki/10-world-schema.md),
  [layer reference](docs/layers_reference.md) and
  [serialization](docs/wiki/11-serialization.md).
- [Validation](docs/wiki/12-validation.md) and
  [empirical calibration](docs/wiki/14-calibration.md).
- [Native engine modules](cpp/src/engine/README.md) and
  [seasonal climate integration](docs/seasonal_climate_native_integration.md).
