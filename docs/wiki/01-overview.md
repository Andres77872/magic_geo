# Project Overview

[Wiki home](./README.md) > Project Overview

`magic-geo` is a causal planet generator: a Python orchestration layer wrapping a C++20 simulation core that derives every world layer from the physical state produced by the layer before it, rather than compositing independent noise fields. It exposes three equivalent front doors (CLI, Python API, local web workbench), two generation scopes (full world, and `--geo-only` for natural systems only), and a deliberately conservative epistemic contract in which authoritative simulation state, non-authoritative audit shadows, and explicitly unresolved physical claims are separated in the serialized output itself. This page is the conceptual entry point for the whole wiki: what the project is, how responsibility is split, what every feature domain maps to, and how to read any output honestly.

## On this page

- [What magic-geo is](#what-magic-geo-is)
- [The causal-generation philosophy](#the-causal-generation-philosophy)
- [Three equivalent entry points](#three-equivalent-entry-points)
- [Two generation scopes: full world and geo-only](#two-generation-scopes-full-world-and-geo-only)
- [Division of responsibility: Python orchestration vs C++ simulation core](#division-of-responsibility-python-orchestration-vs-c-simulation-core)
- [Feature-domain map](#feature-domain-map)
- [The epistemic stance](#the-epistemic-stance)
- [Key quantitative facts](#key-quantitative-facts)
- [Reading paths](#reading-paths)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## What magic-geo is

`magic-geo` takes a single YAML configuration document — 44 validated properties across 9 sections — and produces one self-describing world document (JSON, or the MessagePack-framed `.mgeo` format) containing a spherical cell mesh and every derived physical, ecological, and (optionally) human-geographic layer, together with the process ledgers that record how each layer was produced.

The problem it solves is not "make a pretty map". It is: **produce a world whose every feature has a traceable physical antecedent, and whose output document states exactly which of its claims are replayable facts and which are procedural conveniences.** That second half is unusual and is the reason the codebase carries so much validation machinery.

Three structural commitments follow from that goal:

| Commitment | Where it lives | Consequence |
|---|---|---|
| The world is a **sphere of control volumes**, not a raster image | `cpp/src/engine/mesh.cpp`, `build_mesh` at `cpp/src/engine/pipeline.cpp:12` | No projection artifacts or polar singularities in the simulation; `area_km2` is replayed from stored counter-clockwise `control_volume_vertices_3d` and all cells close to `4*pi*radius^2` |
| Every layer is **derived**, in a fixed order, from prior state | `cpp/src/engine/pipeline.cpp` is the only complete stage ordering (`simulate_world_impl`, lines 6–266) | Reordering stages changes results; the engine README lists "Preserve pipeline order" as invariant #1 (`cpp/src/engine/README.md:328`) |
| Outputs carry **explicit epistemic flags** | `cpp/src/engine/process_serialization.cpp`, `cpp/src/engine/crust_reservoir_serialization.cpp` | 136 hard-coded `false` resolution/calibration flags across 96 distinct flag names are emitted into the world document |

A minimal end-to-end run:

```bash
python -m pip install -e .   # Python CLI + library (editable)
cmake -S . -B build          # configure the C++ simulation core
cmake --build build          # stages libmagic_geo_native.so into src/magic_geo/
magic-geo backend            # verify the native core loads (prints backend info)
magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.json
```

The browser UI is local and self-hosted; it does not upload worlds or configs to an external service (`README.md:13-14`).

---

## The causal-generation philosophy

"Causal" here has a precise operational meaning in this codebase: a stage may only read state that an earlier stage wrote, and the mutation it performs is recorded in a ledger that an independent replay implementation can reproduce from the serialized operands alone.

### The dependency chain, as actually executed

`simulate_world_impl` (`cpp/src/engine/pipeline.cpp:6`) runs this fixed sequence. Every entry mutates the shared `Cell` vector that later entries consume.

| # | Line(s) | Call | What it establishes |
|---|---|---|---|
| 1 | `pipeline.cpp:12` | `build_mesh(params)` | Cell positions, areas, neighbor graph, control-volume vertices |
| 2 | `pipeline.cpp:13-15` | guard | Throws `plate_count must be smaller than generated mesh cell count` |
| 3 | `pipeline.cpp:17` | `generate_plates(params)` | Euler axes, angular speeds, continental/oceanic bias |
| 4 | `pipeline.cpp:18-21` | `choose_plate_seeds(...)` | Deterministic seed cell per plate |
| 5 | `pipeline.cpp:24-29` | inline loop | `plate.initial_center` / `plate.center` from seed cell positions |
| 6 | `pipeline.cpp:30` | `assign_plates(...)` | Nearest-center plate ID per cell |
| 7 | `pipeline.cpp:31` | `classify_boundaries(...)` | Divergent/convergent/transform flags + smoothed forcing |
| 8 | `pipeline.cpp:32-37` | `derive_crust_and_topography(...)` | Crust type, lithology, thickness, density, initial oceanic crust age, thermal subsidence targets, initial elevation and sediment interface |
| 9 | `pipeline.cpp:38-41` | `build_identity_crust_transport_plan(...)` | Identity (no-motion) transport plan for the step-0 checkpoint |
| 10 | `pipeline.cpp:42-64` | `is_oceanic_crust_state` + `crust_equilibrium_elevation_m` loop | Initial isostatic-equilibrium and thermal-target operand vectors |
| 11 | `pipeline.cpp:69-89` | `summarize_plate_motion_step(..., "initial_plate_domains", ...)` | First `plate_motion_history` record — the identity-overlap initial checkpoint |
| 12 | `pipeline.cpp:90-96` | `initialize_crust_material_shadow(...)` | Opening packet table of the non-authoritative dry-rock mass shadow |
| 13 | `pipeline.cpp:97-105` | `initialize_crust_dry_rock_accounting(...)` | Three-reservoir counter-model + initial upper-mantle exchange counter-reserve |
| 14 | `pipeline.cpp:107-116` | `stabilize_numeric_depressions(..., "initial_climate_hydrology", ...)` | First sea-level / marine-labelling / climate / water-budget / flow-routing pass |
| 15 | `pipeline.cpp:117-133` | `summarize_feedback_step(...)` | First `earth_system_feedback_history` entry |
| 16 | `pipeline.cpp:135-147` | `erode(...)` | The maturation loop, `erosion.iterations` passes (see below) |
| 17 | `pipeline.cpp:149-150` | `capture_feedback_reference(...)` | `pre_cryosphere_reference` snapshot |
| 18 | `pipeline.cpp:151` | `derive_cryosphere_state(...)` | Glaciers, ice thickness, snowline |
| 19 | `pipeline.cpp:152-156` | `transport_glacial_sediment(...)` | Terminal glacial erosion/deposition through the shared material primitive |
| 20 | `pipeline.cpp:157-166` | `stabilize_numeric_depressions(..., "cryosphere_coupling", ...)` | Re-solves sea level / climate / hydrology after glacial transport |
| 21 | `pipeline.cpp:167` | `derive_cryosphere_state(...)` (second call) | Terminal cryosphere recomputed on the stabilized terrain |
| 22 | `pipeline.cpp:168-184` | `summarize_feedback_step(..., cryosphere_applied=true, ...)` | Final feedback record |
| 23 | `pipeline.cpp:186` | `summarize_plates(...)` | Per-plate aggregates |
| 24 | `pipeline.cpp:187` | `derive_soils_biomes_resources(...)` | Soils, biomes, resources |
| 25 | `pipeline.cpp:188` | `derive_landforms(...)` | Landform classification |
| 26 | `pipeline.cpp:189` | `generate_ice_sheets(...)` | `natural.ice_sheets` |
| 27 | `pipeline.cpp:190` | `generate_lake_basins(...)` | `natural.lake_basins` |
| 28 | `pipeline.cpp:191` | `generate_watersheds(...)` | `natural.watersheds` |
| 29 | `pipeline.cpp:192` | `generate_coastal_features(...)` | `natural.coastal_features` |
| 30 | `pipeline.cpp:193` | `generate_sedimentary_basins(...)` | `natural.sedimentary_basins` |
| 31 | `pipeline.cpp:194-197` | `generate_stratigraphic_columns(...)` | `natural.stratigraphic_columns` |
| 32 | `pipeline.cpp:199-260` | civilization block (**full-world path only**) | Settlements → routes → political regions → borders → trade → cultures → history → population → conflicts → dynasties → territorial snapshots |
| 33 | `pipeline.cpp:261-264` | `generate_calibration_checks(cells, watersheds)` | `world.calibration_checks` — runs on **both** scopes |

### What "derived, not painted" means concretely

- Rivers are not drawn: they are the high-percentile tail of a flow-accumulation field computed over a Priority-Flood-conditioned routing DEM (`cpp/src/engine/hydrology.cpp`), thresholded by `hydrology.river_percentile` (default `0.92`, `src/magic_geo/config.py:359`).
- Mountains are not stamped: elevation change per maturation step is exactly `isostatic_equilibrium_change_m + thermal_equilibrium_change_m + bounded_dynamic_relief_change_m`, and only `unbounded_dynamic_relief_change_m` is clamped, to `[-180, 220]` m (`cpp/src/engine/README.md:150-156`).
- Initial seafloor age is not a random draw: it is `multi_source_nominal_ridge_graph_travel_time_v1`, a deterministic multi-source Dijkstra from ridge-seeded cells over the oceanic-like neighbor graph (`cpp/src/engine/initial_oceanic_age.cpp`, described at `cpp/src/engine/README.md:115-132`).
- Settlements are not scattered: they are non-water local maxima of a native suitability score above `0.48`, with deterministic spherical separation (`README.md:371`).

### The maturation loop

Inside `erode` (`cpp/src/engine/earth_system.cpp:914`), each of the `erosion.iterations` passes runs, in order: plate motion and crust evolution → flow-accumulation percentile scale → hillslope transport → stream-power incision → fluvial sediment routing → a **single** combined `apply_sediment_interface_material_change` commit per cell → sediment-interface closure and source-partition audits → history append → depression stabilization → feedback summary (`cpp/src/engine/earth_system.cpp:1131` appends exactly one feedback record per iteration).

Worked example with schema defaults (`erosion.iterations = 6`, `src/magic_geo/config.py:376`):

| Ledger | Length | Why |
|---|---|---|
| `plate_motion_history` | `iterations + 1` = **7** | 1 initial checkpoint (`pipeline.cpp:69`) + 1 per erosion iteration |
| `earth_system_feedback_history` | `iterations + 2` = **8** | initial climate/hydrology + 1 per iteration + terminal `cryosphere_coupling` |

This matches the published reference figures: the "geometry-stable 4,096-cell, seven-step reference" and "seven-snapshot reference" (`README.md:347`, `README.md:348`), and "all eight feedback stages" (`README.md:400`).

The nominal timestep `erosion.maturation_timestep_ma` (default `5.0`, range `(0, 5]`, `src/magic_geo/config.py:382`) scales selected continuous responses — plate displacement, quiet-crust aging, bounded relaxations, uplift tendency, hillslope transport, applied stream incision — while event/remap impulses, equilibrium state-difference corrections, routing partitions, and terminal cryosphere coupling retain separate semantics (`README.md:342`). **It is not calibrated physical time.**

---

## Three equivalent entry points

All three drive the same `magic_geo.api` functions, which in turn call the same `magic_geo.native` ctypes bridge into `libmagic_geo_native.so`.

| Entry point | Invocation | Implementation | Scope control | Notes |
|---|---|---|---|---|
| CLI | `magic-geo <command>` | Typer app; facade at `src/magic_geo/cli/__init__.py`, commands in `src/magic_geo/cli/commands/` | `--geo-only` flag (`src/magic_geo/cli/commands/generate.py:30-36`) | 15 commands; `python -m magic_geo` is equivalent |
| Python API | `from magic_geo.api import generate_world, generate_geo_world` | `src/magic_geo/api.py:195` and `:287` | choose the function | Returns the world as a plain `dict[str, Any]` |
| Web workbench | `magic-geo serve` → `http://127.0.0.1:8642` | `src/magic_geo/cli/commands/serve.py`, FastAPI app from `src/magic_geo/debug_server.py` | `geo_only` boolean job field (`src/magic_geo/web_jobs.py:120`) | 11 typed background job kinds + 4 "equivalent" views |

### CLI surface (all 15 registered commands)

| Command | Module | Purpose |
|---|---|---|
| `init-config` | `cli/commands/config.py` | Write a profile-based YAML config (defaults to `--profile earthlike`, output `magic-geo.yaml`) |
| `backend` | `cli/commands/config.py` | Print native backend and OpenCL probe information; verifies the shared library loads |
| `generate` | `cli/commands/generate.py` | Generate a world; `--geo-only`, `--cells`, `--format`, `--summary`, `--cells-csv` |
| `validate` | `cli/commands/validate.py` | Full structural + replay validation over all layers |
| `validate-geo` | `cli/commands/validate_geo.py` | Natural-systems-only deep validation with `--profile generic\|earthlike` |
| `validate-geo-suite` | `cli/commands/validate_geo.py` | Scenario-matrix suite with cross-scenario paired relations |
| `calibrate` | `cli/commands/calibrate.py` | Score one world against an external target bundle |
| `calibrate-ensemble` | `cli/commands/calibrate.py` | Seed × mesh-resolution sweep against shared targets |
| `derive-targets` | `cli/commands/calibrate.py` | Derive target ranges from local source artifacts |
| `render` | `cli/commands/render.py` | SVG map (`equirectangular`, `mollweide`, `orthographic`) |
| `render-raster` | `cli/commands/render.py` | Dependency-free PPM raster |
| `export-debug` | `cli/commands/export.py` | Parquet/Arrow debug cache for the workbench |
| `export-debug-map` | `cli/commands/export.py` | Layer reference map from a debug cache |
| `export-rerun` | `cli/commands/export.py` | Rerun SDK export (optional dependency) |
| `serve` | `cli/commands/serve.py` | Local web workbench |

### Python API surface

`magic_geo/__init__.py` re-exports **only** the configuration helpers (`ConfigError`, `WorldConfig`, `apply_config_overrides`, `config_schema`, `create_config`, `dump_config_yaml`, `list_config_profiles`, `load_config`, `parse_config_overrides`, `parse_config_yaml`, `write_config`; `src/magic_geo/__init__.py:19-31`). Generation lives in `magic_geo.api`:

| Symbol | Signature | Source |
|---|---|---|
| `generate_world` | `(config: WorldConfig) -> dict[str, Any]` | `src/magic_geo/api.py:195` |
| `generate_geo_world` | `(config: WorldConfig) -> dict[str, Any]` | `src/magic_geo/api.py:287` |
| `generate_from_file` | `(path: Path) -> dict[str, Any]` | `src/magic_geo/api.py:378` |
| `generate_geo_from_file` | `(path: Path) -> dict[str, Any]` | `src/magic_geo/api.py:384` |
| `backend_info` | `() -> dict[str, Any]` | `src/magic_geo/api.py:179` |

A copy-pasteable integration example:

```python
from pathlib import Path

from magic_geo.api import backend_info, generate_geo_world, generate_world
from magic_geo.config import create_config, load_config
from magic_geo.io import write_cells_csv, write_summary_markdown, write_world

print(backend_info()["selected_backend"])          # native compute backend telemetry

# 1) Programmatic config from a named profile plus dotted overrides.
config = create_config("earthlike", {"mesh.cell_count": 1024, "erosion.iterations": 2})

# 2) Full world (natural + civilization layers).
world = generate_world(config)
write_world(Path("runs/world.json"), world)
write_summary_markdown(Path("runs/summary.md"), world)
write_cells_csv(Path("runs/cells.csv"), world)      # 397-column flat cell table

# 3) Natural-systems-only world from the same config object.
geo = generate_geo_world(config)
assert geo["generation_scope"] == "geo_only"
assert "generation_scope" not in world                # full worlds carry no scope key

# 4) Or load YAML straight from disk.
world_from_yaml = generate_world(load_config(Path("configs/earthlike_seed.yaml")))
```

`create_config` raises `ConfigError` for an unknown profile; `load_config` deliberately lets `FileNotFoundError`, `PermissionError`, `IsADirectoryError`, and `UnicodeDecodeError` propagate untouched and reserves `ConfigError` for YAML-syntax and model-validation failures (`src/magic_geo/config.py:829`).

### Web workbench job catalog

`_OPERATIONS` (`src/magic_geo/web_jobs.py:109-243`) declares exactly 11 typed job schemas — `generate`, `validate`, `validate-geo`, `validate-geo-suite`, `calibrate`, `calibrate-ensemble`, `derive-targets`, `render`, `render-raster`, `export-debug`, `export-rerun` — and `_EQUIVALENT_OPERATIONS` (`src/magic_geo/web_jobs.py:246-274`) records four commands served by dedicated views instead of background jobs: `init-config` (Config view / `/api/config`), `backend` (`/api/backend`), `export-debug-map` (Map view Export controls), and `serve` (the running process itself).

The workbench binds `127.0.0.1:8642` by default and reads `MAGIC_GEO_WORKSPACE`, `MAGIC_GEO_HOST`, `MAGIC_GEO_PORT` as envvar fallbacks (`src/magic_geo/cli/commands/serve.py:25-46`); explicit flags win. The resolved workspace must stay inside the project root or `serve` exits 2. **It is a trusted-local, single-user tool with no authentication or user isolation** (`README.md:87-89`).

---

## Two generation scopes: full world and geo-only

The scope split happens twice: once in C++ (skip the civilization stages), once in Python (strip the retained placeholder fields, then run a different enricher order).

### Native divergence

`simulate_world(params)` calls `simulate_world_impl(params, true)`; `simulate_geo_world(params)` calls `simulate_world_impl(params, false)` (`cpp/src/engine/pipeline.cpp:268-274`). The guarded block is `if (include_society)` at `pipeline.cpp:199`, spanning lines 199–260. Geo-only executes stages 1–31 identically and leaves every `SocietyArtifacts` member default-constructed.

Stages skipped by `--geo-only`, in native order:

| Line | Call | Produces |
|---|---|---|
| `pipeline.cpp:200` | `generate_settlements` | `society.settlements` |
| `pipeline.cpp:201` | `generate_routes` | `society.routes` |
| `pipeline.cpp:202` | `generate_political_regions` | `society.political_regions` |
| `pipeline.cpp:208` | `generate_border_segments` | `society.borders` |
| `pipeline.cpp:209` | `generate_trade_flows` | `society.trade_flows` |
| `pipeline.cpp:214` | `generate_cultural_layers` | cultures, languages, sacred areas, ruins |
| `pipeline.cpp:222` | `generate_historical_layers` | historical eras, events |
| `pipeline.cpp:230` | `generate_population_regions` | `society.population_regions` |
| `pipeline.cpp:235` | `generate_conflicts` | `society.conflicts` |
| `pipeline.cpp:243` | `generate_dynasties` | `society.dynasties` |
| `pipeline.cpp:250` | `generate_territorial_snapshots` | `society.territorial_snapshots` |

`generate_calibration_checks` at `pipeline.cpp:261` runs on **both** paths — it depends only on cells and watersheds.

### Python divergence

| Aspect | `generate_world` (`api.py:195`) | `generate_geo_world` (`api.py:287`) |
|---|---|---|
| Precondition | none beyond config validity | raises `ValueError` if `not config.output.include_cells` (`api.py:296-300`) |
| Native call | `native_generate_world` | `native_generate_geo_world` |
| Planet gate | `_require_configured_planet_snapshot` (`api.py:185`) | same |
| Placeholder strip | none | `_strip_native_civilization_outputs` (`api.py:269`) before any enricher |
| Scope marker | **none** — no `generation_scope` key is written | `world["generation_scope"] = "geo_only"` (`api.py:305`) |
| Enricher calls | 66 | 48 |

`_strip_native_civilization_outputs` removes three frozensets, because the native serializer keeps stable empty/default civilization schema fields and mixed natural models must take their documented no-human branches rather than reading empty lists as data (`api.py:83-85`):

| Frozenset | Count | Target | Examples |
|---|---|---|---|
| `NATIVE_CIVILIZATION_TOP_LEVEL_FIELDS` (`api.py:86`) | 15 | `world` | `borders`, `conflicts`, `cultures`, `dynasties`, `historical_eras`, `historical_events`, `language_regions`, `political_regions`, `population_regions`, `routes`, `ruins`, `sacred_areas`, `settlements`, `territorial_snapshots`, `trade_flows` |
| `NATIVE_CIVILIZATION_CELL_FIELDS` (`api.py:106`) | 4 | every cell dict | `culture_region_id`, `language_region_id`, `political_region_id`, `settlement_score` |
| `NATIVE_CIVILIZATION_SUMMARY_FIELDS` (`api.py:115`) | 58 | `world["summary"]` | `settlement_count`, `route_count`, `political_region_count`, `estimated_world_population`, `mean_conflict_intensity`, … |

`settlement_score` is the load-bearing cell field: seven enrichers read it per cell with a `0.0` default — `aquifer_resources.py:107`, `ecosystem_dynamics.py:57`, `resource_dynamics.py:83`, `wildfire_disturbance.py:104`, `navigability_diagnostics.py:106`, `land_use_zones.py:94`, and `port_sites.py:103` — so removing it forces the natural baseline branch rather than a "civilization exists but is empty" branch. (`route_corridors.py` is full-world-only and reads the `settlements`/`routes` records directly, not this cell field.)

### Enricher scope partition

69 distinct `enrich_world_with_*` functions are imported in `src/magic_geo/api.py:6-80`. They partition exactly:

| Set | Count | Membership |
|---|---|---|
| Shared (both scopes) | 45 | `66 − 21` and `48 − 3` both yield 45 |
| Full-world only | 21 | `settlement_route_models`, `political_geography_models`, `cultural_geography_models`, `historical_geography_model`, `civilization_geography_models`, `territorial_geography_model`, `navigability_diagnostics`, `port_sites`, `route_corridors`, `land_use_zones`, `natural_frontiers`, `worldbuilding_realism`, `population_history`, `economy_history`, `dynasty_genealogy`, `logistics_history`, `demographic_agents`, `market_clearing`, `graph_diagnostics`, `boundary_geometry`, `phonology_history` |
| Geo-only | 3 | `physical_graph_diagnostics`, `physical_boundary_geometry`, `geo_evolution_provenance` |
| **Total distinct** | **69** | `45 + 21 + 3` |

`graph_diagnostics` and `boundary_geometry` are supersets: each calls its `physical_*` counterpart first and then adds the civilization graphs/segments (`src/magic_geo/graph_diagnostics.py`, `src/magic_geo/boundary_geometry.py`).

### Ordering deltas beyond omission

The geo-only sequence is not merely the full sequence with 21 calls deleted; it is reordered so that natural dependencies are satisfied without civilization inputs (`api.py:307-374`, whose section comments name each block):

| Change | Full-world position | Geo-only position |
|---|---|---|
| Geology / tectonic zones / faults move **before** sea level and ocean circulation | 7–9 | 4–6 |
| `hydrology_realism` runs **before** `sediment_routing_history` | after (17 vs 16) | before (16 vs 17) |
| `permafrost_diagnostics` + `glacial_landforms` move **before** `biome_diagnostics` | after (26–27 vs 25) | before (25–26 vs 27) |
| `karst_diagnostics` joins the water-systems block instead of trailing `route_corridors` | 45 | 36 |
| Graph/boundary products become their `physical_*` variants | 64–65 | 46–47 |
| `geo_evolution_provenance` appended | — | 48 |

### Choosing a scope

```bash
# Full world: natural systems + settlements, politics, cultures, history, economy.
magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.json

# Natural systems only.
magic-geo generate --geo-only --config configs/earthlike_seed.yaml --output runs/geo-world.json

# Geo-only worlds are the input for the deep natural-systems validator.
magic-geo validate-geo --world runs/geo-world.json --profile earthlike --output runs/geo-validation.json
```

`validate-geo` deliberately ignores settlements, routes, ports, politics, cultures, history, population, economy, markets, campaigns, and language (`README.md:217`). It also accepts a full world; the `coupled_maturation` layer contract then drops the `geo_evolution_provenance` output and the `evolution_provenance` domain, recording that in `scope_specific_omissions` (`src/magic_geo/geo_layer_contracts.py`).

---

## Division of responsibility: Python orchestration vs C++ simulation core

```text
YAML config
  -> Python config validation        (pydantic, 44 properties, extra="forbid", allow_inf_nan=False)
  -> ctypes marshalling              (NativeConfigV3 = V2 + maturation_timestep_ma)
  -> C++ native simulation core      (mesh, tectonics, ocean/climate/hydrology, erosion, environment)
  -> serialize_world                 (canonical JSON; optional strict JSON->MessagePack transcode)
  -> Python schema gate              (schema_version == 2, no retired fields, planet snapshot match)
  -> Python enrichers                (66 full-world / 48 geo-only)
  -> JSON / .mgeo / CSV / Markdown / SVG / PPM / Parquet artifacts
```

| Responsibility | Owner | Evidence |
|---|---|---|
| Config schema, validation, YAML safety, profiles, overrides | Python | `src/magic_geo/config.py` (843 lines) |
| ABI marshalling and return-trip schema gate | Python | `src/magic_geo/native.py`; `_require_current_world_schema` |
| Mesh, plates, crust, topography, ocean, climate, hydrology, erosion, cryosphere, soils, biomes, resources | C++ | `cpp/src/engine/*.cpp` |
| Settlements, routes, politics, cultures, history, population, conflicts, dynasties, territorial snapshots | C++ | `cpp/src/engine/settlements.cpp`, `civilization.cpp`, `history.cpp` |
| Canonical serialization and key order | C++ | `cpp/src/engine/world_serialization.cpp` (`schema_version` emitted as `2` at line 49) |
| Diagnostics, derived indices, graphs, histories, model declarations | Python enrichers | 69 `enrich_world_with_*` functions across 67 modules under `src/magic_geo/` (`graph_diagnostics.py` and `boundary_geometry.py` each export two) |
| Logistics networks, market clearing, campaign operations | Python only | `README.md:10-11`; `logistics_history.py`, `market_clearing.py` |
| Validation, calibration, ensembles, reports | Python | `geo_validation*.py`, `calibration/`, `geo_validation_suite/`, 25 `*_validation*.py` modules |
| Rendering, CSV/Markdown/debug/Rerun export | Python | `src/magic_geo/io/`, `debug_export.py`, `debug_map_export.py`, `debug_rerun.py` |
| Compute backend selection and telemetry | C++ | `cpp/src/opencl_compute.cpp`, `cuda_compute.cu` / `cuda_compute_stub.cpp` |

### The boundary itself

The C ABI exposes 10 `extern "C"` symbols declared in `cpp/include/magic_geo/native.hpp:165-190` and defined in `cpp/src/c_api.cpp`: `magic_geo_backend_info_json`, `magic_geo_generate_json` (v1), `magic_geo_generate_json_v2`, `magic_geo_generate_json_v3`, `magic_geo_generate_geo_json_v2`, `magic_geo_generate_geo_json_v3`, `magic_geo_generate_msgpack_v3`, `magic_geo_generate_geo_msgpack_v3`, `magic_geo_free_string`, `magic_geo_free_buffer` (there is no v1 geo entry point). Python **only ever calls the v3 entry points**; `_load_library()` in `src/magic_geo/native.py` resolves exactly seven symbols and re-raises an `AttributeError` as `RuntimeError("native library does not expose the current V3 JSON and MessagePack ABI; rebuild magic_geo_native from the current source tree")`.

| Config struct | Definition | Fields | Adds |
|---|---|---|---|
| `CConfig` (v1) | `cpp/include/magic_geo/native.hpp` | 41 | baseline; frozen at `sizeof == 304`, `alignof == 8` on LP64 by `static_assert` in `cpp/tests/c_api_v1_layout.hpp:64-65` |
| `CConfigV2` | same | 43 | `compute_backend` (0=auto, 1=cpu, 2=opencl, 3=cuda), `opencl_prefer_gpu` |
| `CConfigV3` | same | 44 | `maturation_timestep_ma` |

That `41 + 2 + 1 = 44` is exactly the leaf-field count of `WorldConfig`. The unversioned C++ `generate_world_json(const Params&)` overload and the v1 C entry point **always use CPU** (`cpp/src/engine/README.md:343-344`).

`config_to_native(config)` (`src/magic_geo/config.py:840`) is a one-liner: `return config.model_dump(mode="json")` — no renames at that layer. Renames happen in `native._native_config()`, which flattens the 9 sections and applies these transforms:

| YAML path | Native field | Transform |
|---|---|---|
| `erosion.iterations` | `erosion_iterations` | renamed |
| `mesh.backend` | `mesh_backend` | renamed + enum→int via `MESH_BACKEND_IDS = {"fibonacci_sphere": 0, "geodesic_icosahedron": 1}` |
| `compute.backend` | `compute_backend` | renamed + enum→int via `COMPUTE_BACKEND_IDS = {"auto": 0, "cpu": 1, "opencl": 2, "cuda": 3}` |
| `run.name` | `name` (`c_char_p`) | `str(...).encode("utf-8")` — the reason `RunConfig` bans NUL and caps at 1024 UTF-8 bytes (`src/magic_geo/config.py:142-153`) |
| `hydrology.preserve_geologic_depressions`, `compute.opencl_prefer_gpu`, `output.include_cells` | same names (`c_int`) | `bool` → `1`/`0` |

### The return-trip gate

Before any enricher runs, `_require_current_world_schema` (`src/magic_geo/native.py`) enforces:

1. `schema_version` is `type(...) is int` (rejecting `bool`) and equals `CURRENT_WORLD_SCHEMA_VERSION` (`= 2`, `src/magic_geo/serialization.py:27`), else `RuntimeError(... "rebuild magic_geo_native from the current source tree")`.
2. `retired_world_schema_fields(payload)` is empty.
3. `planet_parameters` is a dict covering all of `PLANET_PARAMETER_DEFAULTS` (12 keys), each value non-`bool` numeric, `float`-convertible without `OverflowError`, finite, and strictly `> 0.0` for `radius_km`, `gravity_g`, `geological_age_ga`.

Then `api._require_configured_planet_snapshot` raises `RuntimeError("native planet_parameters do not match the configured planet snapshot")` if the returned snapshot disagrees with `planet_parameter_snapshot(config.planet)` (`src/magic_geo/api.py:185-192`). `enrich_world_with_planet_realism(world, config.planet)` re-checks the same identity a second time.

MessagePack transport is hardened: `msgpack.unpackb(..., raw=False, use_list=True, strict_map_key=True, ext_hook=_reject_msgpack_extension, max_bin_len=0, max_ext_len=0, ...)` — bin and ext types are forbidden outright, and the zero-copy `memoryview` over native memory is released **before** `magic_geo_free_buffer`.

### Backend selection is generation-scoped and truthful

`compute.backend` accepts `auto`, `cpu`, `opencl`, `cuda` (`src/magic_geo/config.py:425`). The engine invariant "Preserve backend truthfulness" (`cpp/src/engine/README.md:348-355`) requires that `cpu` never initializes or probes CUDA or OpenCL, that below-threshold `auto` CPU selection is not reported as a fallback, that explicit `opencl`/`cuda` never silently fall back, and that `auto` never selects a CPU OpenCL device. Automatic eligibility uses the **generated** mesh size, not the requested one:

| Constant | Value | Source |
|---|---|---|
| `OPENCL_AUTO_MIN_CELL_COUNT` | 32768 | `cpp/src/opencl_compute.cpp:99` |
| `CUDA_SM_120_AUTO_MIN_CELL_COUNT` | 8192 | `cpp/src/opencl_compute.cpp:100` |
| `CUDA_UNCALIBRATED_AUTO_MIN_CELL_COUNT` | 32768 | `cpp/src/opencl_compute.cpp:101` |

Authoritative forward spherical crust overlap **executes on CPU** and reports that scope explicitly in backend telemetry; on an active accelerator a separately named shadow kernel reduces the exact CPU CSR into continuous moments, validates against finite operation-derived bounds, records telemetry, and **discards** the result. Complete accelerator parity is explicitly false, and the documented build host has no device-run evidence for the shadow (`README.md:306-315`, `cpp/src/engine/README.md:294-303`).

---

## Feature-domain map

Every domain below has a dedicated wiki page. The table names the authoritative native translation unit(s) and the Python modules that add diagnostics on top.

| Domain page | Native TU(s) | Python enricher / validator modules | Scope |
|---|---|---|---|
| [Mesh and Geometry](./features/mesh-and-geometry.md) | `cpp/src/engine/mesh.cpp` | `mesh_lod.py`, `spherical_index.py`, `cell_geometry.py`, `control_volume_geometry.py` | both |
| [Tectonics and Plates](./features/tectonics-and-plates.md) | `cpp/src/engine/tectonics.cpp` | `tectonic_zones.py`, `fault_systems.py`, `geology_realism.py` | both |
| [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md) | `cpp/src/engine/plate_boundary_segments.cpp` | `plate_boundary_edge_validation.py` | both |
| [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) | `cpp/src/engine/crust_transport.cpp`, `crust_overlap_candidate_fate.cpp` | `crust_transport_validation.py`, `crust_overlap_candidate_fate_validation.py`, `crust_process_validation.py`, `crust_coverage_geometry_replay.py` | both |
| [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) | `cpp/src/engine/crust_material.cpp`, `crust_reservoir.cpp`, `crust_reservoir_serialization.cpp` | `crust_material_shadow_validation.py`, `crust_dry_rock_accounting_validation.py` | both |
| [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md) | `cpp/src/engine/oceanic_age_depth.cpp`, `initial_oceanic_age.cpp`, `tectonics.cpp` | `oceanic_age_depth_validation.py`, `initial_oceanic_crust_age_validation.py` | both |
| [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) | `cpp/src/engine/earth_system.cpp` | `geo_evolution_provenance.py` | both |
| [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) | `cpp/src/engine/sediment_partition.cpp`, `earth_system.cpp`, `environment.cpp` | `sediment_routing.py`, `sediment_dynamics.py`, `sequence_stratigraphy.py`, `sediment_interface_validation.py`, `sediment_source_partition_validation.py` | both |
| [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) | `cpp/src/engine/hydrology.cpp`, `water_features.cpp` | `hydrology_dynamics.py`, `watershed_diagnostics.py`, `hydrology_realism.py`, `hydrology_budget.py`, `river_network_evolution.py`, `river_channel_morphology.py`, `river_hydraulics.py` | both |
| [Groundwater, Aquifers and Karst](./features/groundwater-and-karst.md) | (derived; no dedicated TU) | `aquifer_resources.py`, `groundwater_flow.py`, `karst_diagnostics.py`, `wetland_diagnostics.py` | both |
| [Climate and Atmosphere](./features/climate-and-atmosphere.md) | `cpp/src/engine/climate.cpp` | `climate_continentality.py`, `climate_dynamics.py`, `climate_energy.py`, `climate_realism.py` | both |
| [Oceans, Currents and Coasts](./features/oceans-and-coasts.md) | `cpp/src/engine/ocean.cpp`, `environment.cpp` | `sea_level_diagnostics.py`, `ocean_circulation.py`, `reef_diagnostics.py` | both |
| [Cryosphere](./features/cryosphere.md) | `cpp/src/engine/environment.cpp` | `cryosphere_dynamics.py`, `cryosphere_stability.py`, `cryosphere_flow.py`, `permafrost_diagnostics.py`, `glacial_landforms.py` | both |
| [Soils and Weathering](./features/soils.md) | `cpp/src/engine/environment.cpp` | `soil_dynamics.py` | both |
| [Biomes, Ecosystems and Disturbance](./features/biomes-and-ecology.md) | `cpp/src/engine/environment.cpp` | `biome_dynamics.py`, `biome_ecotones.py`, `biome_realism.py`, `ecosystem_dynamics.py`, `species_ranges.py`, `wildfire_disturbance.py` | both |
| [Resources and Economic Geology](./features/resources-and-economic-geology.md) | `cpp/src/engine/environment.cpp` | `resource_dynamics.py`, `ore_genesis.py`, `sedimentary_resource_systems.py`, `petroleum_migration.py`, `commodity_resources.py` | both |
| [Settlements, Routes and Corridors](./features/settlements-and-routes.md) | `cpp/src/engine/settlements.cpp` | `settlement_routes.py`, `navigability_diagnostics.py`, `port_sites.py`, `route_corridors.py`, `land_use_zones.py` | full world only |
| [Political, Cultural and Linguistic Geography](./features/political-and-cultural-geography.md) | `cpp/src/engine/civilization.cpp` | `political_geography.py`, `cultural_geography.py`, `natural_frontiers.py`, `phonology_history.py`, `worldbuilding_realism.py` | full world only |
| [History, Demography, Economy and Markets](./features/history-demography-and-economy.md) | `cpp/src/engine/history.cpp` | `historical_geography.py`, `civilization_geography.py`, `territorial_geography.py`, `history_dynamics.py`, `economy_dynamics.py`, `dynasty_genealogy.py`, `logistics_history.py`, `demographic_agents.py`, `market_clearing.py` | full world only |

Note the asymmetry: `navigability_diagnostics`, `port_sites`, `route_corridors`, and `land_use_zones` are physically-grounded models that nonetheless only run in full-world scope. Their physical inputs (channel geometry, hydraulics, coastal depth, soils) exist in geo-only worlds, but the enrichers are not called there; the geo-only sequence stops at `karst_diagnostics` for the water block (`api.py:355`).

---

## The epistemic stance

This is the part of `magic-geo` that most affects how you should read any output. The codebase maintains **three tiers of claim**, and the world document itself tells you which tier a value belongs to.

### Tier 1 — Authoritative state

State that later stages read and that the serialized document is the record of. Mutating it changes the world.

| Authoritative object | Owner | Contract |
|---|---|---|
| Cell geometry (`position_3d`, `control_volume_vertices_3d`, `area_km2`) | `mesh.cpp` | `area_km2` replays from the stored counter-clockwise vertices; all cells close to `4*pi*radius^2` (`README.md:286`) |
| `bedrock_surface_elevation_m` + nonnegative `sediment_thickness_m` | `sediment_partition.cpp` | The **only** canonical geometric interface; `elevation_m` is *derived* as their sum. Mutation code must go through the checked helpers and must not independently mutate all three fields (`cpp/src/engine/README.md:330-332`) |
| Forward spherical crust overlap CSR | `crust_transport.cpp` | CPU-authoritative; geometry, coverage, membership classes, categories, and production state never leave the CPU |
| Plate-boundary segment geometry and direct unsmoothed Euler kinematics | `plate_boundary_segments.cpp` | Authoritative for segment identity/geometry/kinematics only |
| Sea-level solution and marine connectivity | `ocean.cpp` | `volume_constrained_connectivity_ocean_flood_v3`, solved against `planet.ocean_water_inventory_km3` |

Replay-critical numeric state is **not** truncated to `output.float_precision`. Initial/final cell crust age, thickness, and density; remapped crust roots; boundary forcing, transport, process-change, equilibrium, dynamic-relief, and tectonic-change arrays; and final elevation/water depth use general-format `max_digits10` serialization and recover the original binary64 after JSON parsing (`cpp/src/engine/README.md:134-141`). This is distinct from the sediment interface's 10-decimal canonical-state / 8-decimal replay-operand contract.

### Tier 2 — Non-authoritative shadows and counter-models

Ledgers that are computed *alongside* authoritative state, that never feed back into it, and that exist so you can see where the physics is incomplete.

| Shadow | Model name | What it is | What it is explicitly not |
|---|---|---|---|
| Crust material shadow | `persistent_sparse_surface_crust_mass_shadow_v1` (`crust_material.cpp`) | Persistent sparse dry-rock mass packets keyed by immutable origin kind / plate / reason, advected over the normalized overlap CSR with final-edge remainder | `authoritative_for_cell_state`, `physical_source_sink_resolved`, `material_provenance_resolved`, `solid_volume_resolved`, `phase_resolved`, `mass_weighted_age_resolved`, `upper_mantle_exchange_reservoir_resolved`, `subducted_slab_reservoir_resolved` are all emitted `false` (`cpp/src/engine/process_serialization.cpp:206-213`) |
| Dry-rock reservoir accounting | `finite_three_reservoir_dry_rock_accounting_v1` (`crust_reservoir.cpp`) | Surface basement + one global upper-mantle exchange counter-reserve + plate-owned slab tables; ordered rule-derived proxy transfers | Every transfer emits `physical_basis_resolved` from a per-transfer array that is asserted zero (`crust_reservoir.cpp:765`, `:919`); slab tables stay empty; `capacity_geophysically_calibrated`, `mantle_spatial_transport_resolved`, `global_crust_cycle_mass_conservation_resolved`, `coverage_membership_fate_resolved`, `subduction_polarity_resolved` are `false` (`crust_reservoir_serialization.cpp:135-192`) |
| Accelerator overlap shadow | `cpp/src/crust_overlap_shadow.cpp` | FP64 continuous-moment reduction over the exact CPU CSR, bounds-checked, telemetered, then **discarded** | Complete accelerator parity is false; CPU remains authoritative for geometry, coverage, classes, categories, and production state |
| Overlap candidate-fate crosswalk | `sparse_membership_class_to_uniform_boundary_plate_pair_candidate_v1` (`crust_overlap_candidate_fate.cpp`) | Diagnostic partition of overlap excess into boundary plate-pair candidate rows | `physical_polarity_resolved`, `physical_material_fate_resolved`, `slab_selection_resolved`, `slab_transfer_resolved`, `local_segment_link_resolved`, `connected_atom_topology_resolved`, `local_fragment_topology_resolved` are `false` (`process_serialization.cpp:3239-3252`) |
| Source-partition depth audits | hillslope / fluvial / glacial `*_by_cell` arrays | Depth and bulk-volume witnesses reconstructing stage totals as `depth_m * area_km2 / 1000` | `source_partition_audit_is_mass_claim` and `source_partition_audit_is_provenance_claim` are `false` (`process_serialization.cpp:1165-1166`, `:1478-1479`) |
| Python enricher histories | `*_histories`, `*_records`, `*_diagnostics` | Post-hoc diagnostic trajectories over already-final native state | Classified as `posthoc_diagnostic_trajectory` (not `native_state_mutation_ledger`) by `geo_evolution_provenance.py` |

### Tier 3 — Explicitly unresolved physical claims

The engine emits a large vocabulary of boolean flags whose value is hard-coded `false`. Counting every `add_bool(..., "<name>", false)` call site across `cpp/src/engine/` (including the multi-line ones a single-line grep misses) yields **136 emissions of 96 distinct flag names**, all of them in exactly two translation units: `process_serialization.cpp` (119) and `crust_reservoir_serialization.cpp` (17). Representative families:

| Family | Example flags | Emitted at |
|---|---|---|
| Physical time and rate calibration | `physical_time_resolved` (9×), `nominal_time_calibrated` (4×), `process_rate_calibration_resolved`, `absolute_geological_age_resolved`, `time_step_convergence_demonstrated` (5×), `equilibrium_operator_physical_time_calibrated` | `process_serialization.cpp:158-159`, `:2083-2086`, `:2686-2688`, `:2903` |
| Subduction polarity and slab fate | `physical_subduction_polarity_resolved`, `physical_slab_geometry_resolved`, `slab_selection_resolved`, `slab_transfer_resolved`, `physical_material_fate_resolved`, `physical_polarity_resolved` | `process_serialization.cpp:3140-3144`, `:3239-3245` |
| Mass, provenance and phase | `dry_rock_mass_resolved`, `sediment_density_resolved`, `porosity_resolved`, `compaction_resolved`, `grain_provenance_resolved`, `chemical_weathering_resolved`, `material_provenance_resolved`, `solid_volume_resolved`, `phase_resolved`, `mass_weighted_age_resolved` | `process_serialization.cpp:1860-1865`, `:1982-1988`, `:206-213` |
| Seafloor creation history | `physical_seafloor_creation_resolved`, `spreading_rate_calibrated`, `local_spreading_rates_resolved`, `ridge_flowlines_resolved`, `subduction_sink_history_resolved`, `convergence_history_resolved` | `process_serialization.cpp:2497-2502` |
| Plate velocity | `physical_plate_velocity_calibrated` | `process_serialization.cpp:3137` |
| Thermal / bathymetric | `derivative_continuity_at_transition_resolved`, `thermal_relaxation_timescale_calibrated`, `absolute_basement_depth_calibrated` | `process_serialization.cpp:3320`, `:3326`, `:3336` |
| Climate / channel geometry | `transient_climate_resolved`, `subcell_channel_geometry_resolved`, `grain_size_resolved`, `shared_boundary_geometry_resolved` | `process_serialization.cpp:444`, `:1489`, `:1487`, `:1189` |

On the Python side, `geo_layer_contracts.py:433` hardcodes `"empirical_realism_proven": False` on **every** one of the 14 layer contracts, and `geo_evolution_provenance.py` refuses to accept a registry unless `physical_time_resolved` and `nominal_time_calibrated` are both `False` (`geo_evolution_provenance.py:175-180`, `:192-200`, `:259-262`).

### Why this matters when reading any output

1. **A passing validation is not a physical claim.** A layer contract passes when its declared outputs exist with the right kind, every declared validator domain supplied at least one check, all dependencies passed, at least one passing check exists, and there are zero error-severity failures — and it still reports `empirical_realism_proven: False`. Internal closure is orthogonal to Earth fit; `GEO_MODEL_LIMITATIONS[11]` states this outright: *"Earth empirical fit remains a separate calibration verdict from internal contract integrity"* (`src/magic_geo/geo_validation.py:40`).
2. **Accounting closure is not conservation.** The three-reservoir counter-model closes global, per-origin, and per-reservoir arithmetic — but that is accounting closure, not physical provenance or a mass/energy/phase-balanced crust cycle (`README.md:351`).
3. **Ledgers named after physical processes may not be physical.** `crust_overlap_candidate_fate_ledger` names candidate subducting/overriding sides, but the physical sides are literally serialized as `unknown` with decision source `none` and zero confidence wherever convergence is active (`README.md:348`).
4. **Nominal km/Ma is not a plate speed.** The boundary ledger's km/Ma scale is `radius_km * plate_motion_scale_deg_per_step * pi/180 / 5 Ma` — a nominal reference-step scale, not an observed or calibrated velocity (`cpp/src/engine/README.md:193-198`).
5. **Absent phenomena are `not_applicable`, not perfect.** Validation records `status: "not_applicable"` with `passed: False` for phenomena a scenario simply does not have (no rivers on a land world), so absence never earns a vacuous perfect score (`README.md:217`; `_check` at `src/magic_geo/geo_validation.py:271-296`).
6. **Accelerator results are never authoritative.** Even when a GPU is active, the overlap shadow's output is validated against bounds and discarded; the documented host has no device-run evidence for it at all.

### Fail-closed operational caps (numerical, not physical)

| Cap | Value | Meaning |
|---|---|---|
| Control-volume segments per cell | 64 | malformed-geometry / resource guard |
| Reciprocal mesh segments per cell | 8 | same |
| Packets per surface owner | 1,024 | memory-safety limit |
| Packets across live reservoirs | 1,000,000 | memory-safety limit |
| Transfers per step | 1,000,000 | memory-safety limit |
| Local overlap arrangement atoms | 16,384 | declared in model metadata; lacks exhaustive worst-case proof |

Source: `cpp/src/engine/README.md:188-191`, `:321-324`; `README.md:347`, `:351`. These are explicitly **numerical memory-safety limits, not physical flux or reservoir-capacity limits.**

---

## Key quantitative facts

Every number here was counted or read from the source tree at the cited location.

### Configuration

| Fact | Value | Source |
|---|---|---|
| Config sections | 9 (`run`, `planet`, `mesh`, `tectonics`, `climate`, `hydrology`, `erosion`, `compute`, `output`) | `src/magic_geo/config.py:463-498` |
| Leaf properties | **44** (run 2, planet 12, mesh 3, tectonics 8, climate 5, hydrology 2, erosion 7, compute 3, output 2) | `src/magic_geo/config.py:124-456`; matches `README.md:139` "all 44 fields" |
| Named profiles | 3 — `default`, `earthlike`, `smoke` | `src/magic_geo/config.py:507-529` |
| Example seed presets | 9 YAML files under `configs/seeds/` | directory listing; `README.md:147-151` |
| Model config on every section | `extra="forbid"`, `allow_inf_nan=False` | unknown keys and `nan`/`inf` rejected everywhere |
| YAML safety caps | 20,000 parse events, 64 nesting levels, 64 aliases | `MAX_YAML_EVENTS`/`MAX_YAML_NESTING_DEPTH`/`MAX_YAML_ALIASES`, `src/magic_geo/config.py:34-36` |

Profile deltas (descriptions at `src/magic_geo/config.py:507-511`, overrides at `:513-529`):

| Profile | Description | Overrides vs. schema default |
|---|---|---|
| `default` | "Schema defaults suitable as a neutral editable starting point." | none |
| `earthlike` | "Calibrated 4,096-cell Earth-like reference configuration." | `tectonics.plate_motion_scale_deg_per_step` → 4.0; `climate.precipitation_scale` → 0.8 |
| `smoke` | "Small deterministic CPU configuration for fast integration checks." | `run.name` → `"smoke"`; `mesh.cell_count` → 128; `tectonics.plate_count` → 8; `tectonics.plate_motion_scale_deg_per_step` → 4.0; `climate.precipitation_scale` → 0.8; `erosion.iterations` → 1; `compute.backend` → `"cpu"`; `compute.threads` → 1 |

### Enrichment

| Fact | Value | Source |
|---|---|---|
| Distinct enrichers imported | **69** | `src/magic_geo/api.py:6-80` |
| Calls in `generate_world` | **66** | `src/magic_geo/api.py:200-265` |
| Calls in `generate_geo_world` | **48** | `src/magic_geo/api.py:308-374` |
| Shared by both | 45 | `66 − 21 = 48 − 3 = 45` |
| Full-world-only | 21 | see scope table above |
| Geo-only-only | 3 | `physical_graph_diagnostics`, `physical_boundary_geometry`, `geo_evolution_provenance` |

### Native engine

| Fact | Value | Source |
|---|---|---|
| Translation units compiled into `magic_geo_native` | **33** | `CMakeLists.txt:94-129` |
| — of which under `cpp/src/engine/` | **28** | same |
| — of which under `cpp/src/` | 5 (`c_api.cpp`, `engine.cpp`, `crust_overlap_shadow.cpp`, `opencl_compute.cpp`, plus `${MAGIC_GEO_CUDA_SOURCE}` = `cuda_compute.cu` or `cuda_compute_stub.cpp`) | same |
| Exported `extern "C"` symbols | 10 | `cpp/include/magic_geo/native.hpp:165-190`, defined in `cpp/src/c_api.cpp` |
| C++ symbols Python resolves | 7 (v3 JSON + v3 MessagePack + geo variants + backend info + two free functions) | `src/magic_geo/native.py` `_load_library` |
| World schema version | 2 | `cpp/src/engine/world_serialization.cpp:49`; `src/magic_geo/serialization.py:27` |
| Top-level serializer keys emitted by `serialize_world` | **57** | `cpp/src/engine/world_serialization.cpp:49-289` (`schema_version` … `cells`) |
| Hard-coded `false` resolution flags | 136 emissions, 96 distinct names | `cpp/src/engine/process_serialization.cpp` (119) + `crust_reservoir_serialization.cpp` (17) |

### Validation

| Fact | Value | Source |
|---|---|---|
| `validate-geo` profiles | 2 — `generic`, `earthlike` | `src/magic_geo/geo_validation.py`; unknown profile emits a failing `contract.known_validation_profile` check rather than raising |
| Declared model limitations in every report | **12** | `GEO_MODEL_LIMITATIONS`, `src/magic_geo/geo_validation.py:28-41` |
| Distinct check domains | **31** = 16 (top-level) + 14 (subsystems) + 1 (`evolution_provenance`) | `geo_validation.py`, `geo_validation_subsystems.py:2873-2887`, `geo_evolution_provenance.py:368` |
| Physics replay checks | **13** | `geo_validation_physics.py` — domains `tectonics` (8), `simulation` (2), `sediment` (2), `climate` (1) |
| Natural subsystem validators | **13** (+ `natural_pipeline` root domain) | `geo_validation_subsystems.py:2850-2887` |
| Layer contracts | **14**, phases 0–13 | `GEO_LAYER_CONTRACTS`, `src/magic_geo/geo_layer_contracts.py:26-300` |
| Realism families | **5** | `REALISM_FAMILIES`, `geo_validation.py:75-81` |
| Built-in Earth calibration metrics | **12** | `CALIBRATION_EXPECTED_METRICS`, `geo_validation.py:43-58` |
| Standalone replay/validation modules | 25 `*_validation*.py` + `crust_coverage_geometry_replay.py` | `src/magic_geo/` listing |
| CLI per-domain validators | 8 (`corridors`, `hydrology`, `navigability`, `political`, `ports`, `rivers`, `sediment`, `settlement`) + `_shared` | `src/magic_geo/cli/validators/` |

Check-record shape, identical across `geo_validation._check` (`:271`), `geo_validation_subsystems._add` (`:31`), and `geo_validation_physics._append_check` (`:95`):

| Key | Type | Semantics |
|---|---|---|
| `id` | `int` | sequential index, re-numbered after subsystem composition |
| `domain` | `str` | one of the 31 domains |
| `name` | `str` | check identifier within the domain |
| `status` | `"passed" \| "failed" \| "not_applicable"` | `passed=None` → `not_applicable` |
| `passed` | `bool` | `True` only when `status == "passed"` |
| `severity` | `"error" \| "warning"` | `warning` is reserved for `domain="realism_evidence"` |
| `message`, `observed`, `expected`, `evidence` | `str` / `Any` / `Any` / `dict` | human text plus machine operands |

Only `status == "failed" and severity == "error"` fails a report; `--fail-on-warnings` promotes realism-evidence deviations to fatal.

The 14 layer contracts, in phase order: `planet_parameters` (0), `spherical_mesh` (1), `plate_tectonics` (2), `crust_lithology` (3), `relief_bathymetry` (4), `sea_level_ocean` (5), `climate_atmosphere` (6), `hydrology` (7), `erosion_sediment` (8), `cryosphere` (9), `soils_pedogenesis` (10), `biomes_ecosystems` (11), `natural_resources` (12), `coupled_maturation` (13) — `src/magic_geo/geo_layer_contracts.py:28-286`.

### Suites and calibration

| Fact | Value | Source |
|---|---|---|
| Geo validation matrix scenarios | **21** | `configs/geo_validation_matrix.yaml` |
| Cross-scenario paired relations | **26** | same |
| Earth empirical target bundle | `canonical_earth_empirical_targets_v2`: 7 sources, **22 targets** | `configs/geo_validation_earth_empirical_targets.json` |
| Calibration ensemble members | 10 (5-seed sweep @ 4096 cells + 5-resolution sweep @ seed 424242) | `configs/calibration_ensemble.r1.json` |
| CSV export columns | **397** | `src/magic_geo/io/cells_csv.py` `fieldnames` |

Reported Earth fit for the authoritative seed: coverage complete at 22/22, fit 17/22. Failing: Natural Earth coastal land fraction, all three ETOPO relief metrics, and HydroBASINS non-Antarctic endorheic watershed area fraction. Passing: HydroBASINS endorheic count, both HydroRIVERS metrics, all three WorldClim metrics, all eleven Seton age-distribution metrics (`README.md:473`).

### Tests

| Suite | Count | Source |
|---|---|---|
| Python test modules | **87** | `tests/test_*.py` |
| Python test classes | 356 top-level (272 deriving from `TestCase`) | `tests/` |
| Python test methods (`def test_*`) | **1,871** | `tests/` |
| Native CTest registrations | **14** declared, from 13 executables (`magic_geo_native_api_test` registers twice) | `CMakeLists.txt` `add_test` blocks |
| Native tests on a typical non-CUDA 64-bit build | **13** | `magic_geo_cuda_compute` is gated on `MAGIC_GEO_CUDA_ENABLED`; matches `README.md:268` "13 native tests, ~5 s" |

Declared CTest names: `magic_geo_c_api_v1_client`, `magic_geo_crust_overlap_candidate_fate`, `magic_geo_crust_overlap_shadow`, `magic_geo_crust_reservoir`, `magic_geo_crust_reservoir_integration`, `magic_geo_cuda_compute`, `magic_geo_fibonacci_knn_reference`, `magic_geo_initial_oceanic_age`, `magic_geo_native_api`, `magic_geo_oceanic_age_depth`, `magic_geo_oceanic_age_depth_integration`, `magic_geo_plate_boundary_segments`, `magic_geo_sediment_partition`, `magic_geo_serialization_roundtrip`.

Python suite runtimes quoted by the project: full suite ~29 min; `-m "not slow"` ~13 min; `-m "slow"` ~16 min; `--cov` ~2 h (`README.md:238-245`). Coverage measures Python only — the C++ core never appears in a coverage report (`README.md:256-258`).

---

## Reading paths

Four ordered sequences. Each assumes you have read this page.

### 1. Worldbuilder — "I just want worlds"

You care about producing good-looking, internally coherent planets and rendering them. You do not need the replay machinery.

| # | Page | Why |
|---|---|---|
| 1 | [Installation and Build](./02-installation-and-build.md) | Get `libmagic_geo_native.so` staged; `magic-geo backend` must succeed before anything else works |
| 2 | [Quickstart](./03-quickstart.md) | First world end to end |
| 3 | [Example Seeds and Presets](./20-seed-gallery.md) | The 9 checked-in presets and what each is tuned for |
| 4 | [Configuration Reference](./05-configuration-reference.md) | The 44 knobs, their ranges, and which ones actually change the look of a world |
| 5 | [CLI Reference](./06-cli-reference.md) | `generate`, `render`, `render-raster` options in full |
| 6 | [Rendering and Map Output](./17-rendering.md) | Projections, contours, labels, `--max-cells` sampling |
| 7 | [Web Workbench](./15-web-workbench.md) | Iterate on configs and inspect layers without touching a terminal |
| 8 | [Troubleshooting and FAQ](./22-troubleshooting.md) | When the native library will not load or a run is too slow |
| 9 | [Glossary](./21-glossary.md) | Decode field names when browsing an exported world |

Skip: the crust ledgers, validation internals, and calibration. Do read the [epistemic stance](#the-epistemic-stance) section above before quoting any generated number as physically meaningful.

### 2. Integrator — "I am embedding the Python API"

You call `generate_world` / `generate_geo_world` from your own service or pipeline and consume the returned dict.

| # | Page | Why |
|---|---|---|
| 1 | [Installation and Build](./02-installation-and-build.md) | Wheel/ABI staging rules; a locally produced `linux_x86_64` tag is **not** a manylinux portability claim |
| 2 | [Python API](./07-python-api.md) | The 5 functions in `magic_geo.api`, the `magic_geo.__init__` config re-exports, and exception contracts |
| 3 | [Configuration Reference](./05-configuration-reference.md) | `WorldConfig`, `create_config`, `apply_config_overrides`, `config_schema` (`$id = urn:magic-geo:schema:world-config:v1`) |
| 4 | [World Document Schema](./10-world-schema.md) | Every top-level key and per-cell field you will consume |
| 5 | [Serialization and World Formats](./11-serialization.md) | JSON vs `.mgeo`; `write_world`/`read_world`; the `MGEO` header and safety limits |
| 6 | [Compute Backends](./09-compute-backends.md) | `compute.backend`, `compute.threads`, and the generation-scoped OpenMP thread policy |
| 7 | [Validation](./12-validation.md) | Wire `validate` / `validate-geo` into CI so a bad upgrade fails loudly |
| 8 | [Docker Deployment](./19-docker-deployment.md) | The all-in-one image and `.env` reference if you deploy rather than embed |
| 9 | [Troubleshooting and FAQ](./22-troubleshooting.md) | ABI mismatch, schema-version, and planet-snapshot errors |

Integrator gotchas established above: `magic_geo/__init__.py` does **not** export `generate_world`; `generate_geo_world` raises `ValueError` unless `output.include_cells` is true; a full world has no `generation_scope` key at all; and the native library is re-loaded on every public `magic_geo.native` call (there is no module-level cache).

### 3. Contributor — "I am extending the simulation"

You are adding or changing a stage in the C++ core or a Python enricher.

| # | Page | Why |
|---|---|---|
| 1 | [Architecture](./04-architecture.md) | The simulation/result/serialization boundary and `GeneratedWorld` handoff |
| 2 | [Native Engine (C++ Core)](./08-native-engine.md) | Per-TU ownership, `internal.hpp` privacy, and the full invariant list |
| 3 | [Compute Backends](./09-compute-backends.md) | Backend truthfulness rules you must not break |
| 4 | [World Document Schema](./10-world-schema.md) | Where a new field belongs and what key order it must preserve |
| 5 | [Validation](./12-validation.md) + [Geo Validation Suite](./13-geo-validation-suite.md) | Every new stage needs a replay validator and, usually, a layer-contract domain |
| 6 | [Testing and Quality Gates](./18-testing.md) | 1,871 Python test methods and the CTest registrations you must keep green |
| 7 | [Debug Exports and Visualization](./16-debug-and-visualization.md) | Inspect intermediate state while iterating |
| 8 | The feature page for the domain you are touching | see the [feature-domain map](#feature-domain-map) |

The nine binding invariants from `cpp/src/engine/README.md:326-359`, condensed:

| # | Invariant |
|---|---|
| 1 | Preserve pipeline order — later stages consume fields earlier stages wrote |
| 2 | Preserve the sediment-interface authority boundary — mutate the two canonical fields through the checked helpers and *derive* `elevation_m` |
| 3 | Preserve plate-boundary evidence boundaries — geometry and direct kinematics authoritative; nominal km/Ma uncalibrated; polarity explicitly unknown; the ledger must not be described as driving smoothed cell forcing or slab transfers |
| 4 | Preserve RNG consumption, OpenMP schedules, floating-point expression order, serializer key order, and precision unless a schema/behavior change is intended |
| 5 | Keep v1 `CConfig` / v2 `CConfigV2` field order, types, and 64-bit sizes stable; `Params` may grow only at the tail |
| 6 | Keep all declared public symbols visible and all `magic_geo::detail` symbols hidden |
| 7 | Preserve backend truthfulness (see the compute table above) |
| 8 | Explicit OpenMP thread counts are generation-scoped and restore the caller's prior ICV on every exit; `threads=0` leaves host policy untouched |
| 9 | New domain stages belong before `serialize_world`; serializers must be read-only over `GeneratedWorld` |

Layout drift is caught at compile time: `cpp/tests/c_api_v1_client_test.cpp` compiles against the frozen `cpp/tests/c_api_v1_layout.hpp` **without including the current header** (`cpp/src/engine/README.md:362-363`).

### 4. Scientist — "I am auditing the physics"

You want to know exactly which claims are supported by replayable evidence and which are procedural.

| # | Page | Why |
|---|---|---|
| 1 | This page's [epistemic stance](#the-epistemic-stance) | The three-tier model and the `false`-flag vocabulary |
| 2 | [Validation](./12-validation.md) | Check-record shape, the 31 domains, the 14 layer contracts, and what "contract passed" does and does not assert |
| 3 | [Geo Validation Suite](./13-geo-validation-suite.md) | 21 scenarios, 26 paired relations, determinism reruns via `geo_fingerprint` SHA-256 |
| 4 | [Calibration Against Real-Earth Data](./14-calibration.md) | The 22-metric bundle, coverage-vs-fit separation, and the 5 currently failing metrics |
| 5 | [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md) | Parsons–Sclater branch, C0 continuity, the `[-180, 220]` m clamp, and what "quasi-static" does not buy |
| 6 | [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md) | Why convergence plus an oceanic-side predicate does not resolve polarity |
| 7 | [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) | First-order diffusive overlap, the 16,384-atom cap, and the unproven worst case |
| 8 | [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) | Accounting closure vs. physical conservation |
| 9 | [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) | Bulk reference volume vs. dry-rock mass; why density, porosity, and compaction still block a mass claim |
| 10 | [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) | Nominal timestep semantics and the lack of demonstrated timestep convergence |
| 11 | [Native Engine (C++ Core)](./08-native-engine.md) | Where each contract is enforced in code |
| 12 | [Compute Backends](./09-compute-backends.md) | The discarded accelerator shadow and the absence of device-run evidence on the documented host |

Start every audit by reading `GEO_MODEL_LIMITATIONS` (`src/magic_geo/geo_validation.py:28-41`) — those 12 strings are copied verbatim into every `validate-geo` report and into every suite report, and they are the project's own statement of what it does not claim.

---

## Limitations and unresolved claims

Carried forward from the project's own declarations. These are not caveats added by this wiki; they are enforced by tests and serialized into every world.

| # | Limitation (from `GEO_MODEL_LIMITATIONS`, `src/magic_geo/geo_validation.py:29-40`) |
|---|---|
| 1 | The simulation clock orders procedural stages but has **no calibrated physical duration**. |
| 2 | The diagnostic atmosphere is **not** a three-dimensional mass-conserving circulation solver. |
| 3 | Configured ocean inventory is **not** a closed total-water partition across ocean, ice, groundwater, lakes, and atmosphere. |
| 4 | First-order conservative crust overlap is **diffusive**, CPU-authoritative, and guarded by a 16,384-fragment local arrangement cap **without exhaustive worst-case proof**; an accelerator may validate and discard only a continuous-moment CSR shadow, while geometry, categories, production state, complete parity, and device-lane evidence remain unresolved. |
| 5 | The pair-wide overlap candidate crosswalk accounts for every excess class but does **not** resolve a local fragment-to-segment link, physical polarity, allocation, material fate, slab transfer, or state mutation. |
| 6 | Post-transport tectonic rules expose ordered per-reason positive, negative, and net state-moment changes, but **not** physical reservoir, material-provenance, energy, or phase source/sink fluxes. |
| 7 | Initial oceanic-like crust age is a replayable multi-source ridge-distance graph field using one globally averaged nominal half-spreading rate; it does **not** reconstruct local flowlines, calibrated spreading, subduction sinks, convergence history, or physical seafloor creation and destruction. |
| 8 | The continuity-adjusted Parsons–Sclater relation is authoritative only for a **relative** oceanic thermal-subsidence target curve; the quasi-static timescale separation is not a calibrated transient relaxation, and realized thermal relief, absolute basement depth, heat flow/thermal structure, dynamic topography, flexure, and physical dynamics remain unresolved. |
| 9 | Persistent surface-crust dry-rock packets and the finite surface/exchange/empty-slab counter-model close **numerical** transport and rule-derived proxy compensation accounting, but remain non-authoritative and do not resolve physical transfer bases, fate, solid volume, phase, mantle, slab, sediment coupling, or a physical global crust cycle. |
| 10 | The bedrock surface and mobile-sediment thickness form an explicit canonical geometric interface and hillslope, fluvial, glacial, and numeric-breach updates replay, but bulk reference-volume closure still does **not** resolve dry-rock mass, sediment density, porosity, compaction, grain provenance, or chemical weathering. |
| 11 | Ecosystem, species, wildfire, and resource layers are **diagnostic index models**, not calibrated population or process solvers. |
| 12 | Earth empirical fit remains a **separate calibration verdict** from internal contract integrity. |

Additional overview-level caveats verified in source:

- **`empirical_realism_proven` is hardcoded `False` on all 14 layer contracts** (`src/magic_geo/geo_layer_contracts.py:433`). No contract, however green, asserts realism.
- **Bathymetry is cell-column, not subcell.** At 4,096 cells an Earth-sized cell is roughly 400 km across, so one scalar elevation mixes land, shelf, slope, and deep ocean. Lowering a whole margin cell to manufacture shelf area is explicitly "not a defensible correction"; conservative subcell hypsometry is named as the required next architecture (`cpp/src/engine/README.md:167-175`, `README.md:352`).
- **Geodesic bent dual boundaries are not yet multi-segment polylines** in the `cell_adjacency_edges` schema; the process-stencil `neighbors` graph and `cell_adjacency_edges` remain separate stencil/diagnostic structures (`README.md:286`).
- **Independent O(N²) geometry replay is capped at 1,024 cells.** Scaling that pair discovery to the 4,096-cell reference is an open validation-evidence blocker (`README.md:347`).
- **The accelerator overlap shadow has no device-run evidence on the documented host** — only CPU/stub integration and pure reconciliation logic are verified there (`cpp/src/engine/README.md:300-303`).
- **Coverage reports measure Python only.** The C++ core in `libmagic_geo_native.so` never appears (`README.md:256-258`).
- **The web workbench has no authentication or user isolation.** Keep the default loopback binding unless a trusted network boundary or authenticating reverse proxy protects it (`README.md:87-89`).
- **Numerical examples labeled `v32` in the project README are historical snapshots** from before the exact-control-volume/v3 transport change and must be regenerated before use as current benchmarks (`README.md:324-327`). Payload size and RSS figures for the 4,096-cell reference have not been remeasured since that checkpoint.
- **The historical ten-member calibration ensemble predates the Seton expansion** and the source-matched HydroRIVERS metrics; it is not current v3 evidence and must not be compared as though it used the same 22-metric bundle (`README.md:473`).

---

## See also

- [Installation and Build](./02-installation-and-build.md) — prerequisites, CMake options, wheel/ABI staging
- [Quickstart](./03-quickstart.md) — first world in five commands
- [Architecture](./04-architecture.md) — layer boundaries and data flow in depth
- [Configuration Reference](./05-configuration-reference.md) — all 44 properties with ranges and descriptions
- [CLI Reference](./06-cli-reference.md) — all 15 commands and every flag
- [Python API](./07-python-api.md) — embedding surface and exception contracts
- [Native Engine (C++ Core)](./08-native-engine.md) — per-TU ownership, ABI, invariants
- [Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md) — selection, thresholds, telemetry
- [World Document Schema](./10-world-schema.md) — every serialized key
- [Serialization and World Formats](./11-serialization.md) — JSON and `.mgeo`
- [Validation](./12-validation.md) — domains, contracts, replay validators
- [Geo Validation Suite](./13-geo-validation-suite.md) — scenario matrix and paired relations
- [Calibration Against Real-Earth Data](./14-calibration.md) — target bundles, coverage vs. fit
- [Web Workbench](./15-web-workbench.md) — the local browser tool
- [Debug Exports and Visualization](./16-debug-and-visualization.md) — caches, maps, Rerun
- [Rendering and Map Output](./17-rendering.md) — SVG and raster maps
- [Testing and Quality Gates](./18-testing.md) — Python and native suites
- [Docker Deployment](./19-docker-deployment.md) — all-in-one image
- [Example Seeds and Presets](./20-seed-gallery.md) — the nine checked-in worlds
- [Glossary](./21-glossary.md) — terminology and field-name decoder
- [Troubleshooting and FAQ](./22-troubleshooting.md) — common failures
- Feature pages: [Mesh and Geometry](./features/mesh-and-geometry.md) · [Tectonics and Plates](./features/tectonics-and-plates.md) · [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md) · [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) · [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) · [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md) · [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) · [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) · [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) · [Groundwater, Aquifers and Karst](./features/groundwater-and-karst.md) · [Climate and Atmosphere](./features/climate-and-atmosphere.md) · [Oceans, Currents and Coasts](./features/oceans-and-coasts.md) · [Cryosphere](./features/cryosphere.md) · [Soils and Weathering](./features/soils.md) · [Biomes, Ecosystems and Disturbance](./features/biomes-and-ecology.md) · [Resources and Economic Geology](./features/resources-and-economic-geology.md) · [Settlements, Routes and Corridors](./features/settlements-and-routes.md) · [Political, Cultural and Linguistic Geography](./features/political-and-cultural-geography.md) · [History, Demography, Economy and Markets](./features/history-demography-and-economy.md)
