# Quickstart

[Wiki home](./README.md) > Quickstart

This is a hands-on first hour with `magic-geo`: create a configuration, generate a full planet, read every artifact the generator emits, render two maps, run the consistency gate, generate the natural-geography-only variant, and open the local web workbench. Every command below is the real CLI surface as implemented in `src/magic_geo/cli/commands/`, and every default is quoted from the source that defines it. Where the repository does not publish a number, this page says so instead of inventing one; where a number is a single local observation rather than a project benchmark, it is labeled as such.

## On this page

- [Step 0: prerequisites and sanity check](#step-0-prerequisites-and-sanity-check)
- [Step 1: create a config](#step-1-create-a-config)
- [Step 2: generate a full world](#step-2-generate-a-full-world)
- [Step 3: inspect the outputs](#step-3-inspect-the-outputs)
- [Step 4: render an SVG and a raster](#step-4-render-an-svg-and-a-raster)
- [Step 5: run validate](#step-5-run-validate)
- [Step 6: run a geo-only generation](#step-6-run-a-geo-only-generation)
- [Step 7: start the web workbench](#step-7-start-the-web-workbench)
- [Fast smoke-run recipe](#fast-smoke-run-recipe)
- [Runtime and size expectations](#runtime-and-size-expectations)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [What to read next](#what-to-read-next)
- [See also](#see-also)

---

## Step 0: prerequisites and sanity check

The Python layer owns configuration, validation, orchestration, and file output; the heavy planet generation runs in a C++ shared library loaded through `ctypes` (`README.md:3-11`). You therefore need both halves working before anything else.

| Requirement | Constraint | Where it is stated |
|---|---|---|
| Python | `>=3.11` | `pyproject.toml:10` |
| CMake | 3.20+ | `README.md:18` |
| C++ compiler | C++20 | `README.md:18` |
| OpenMP | used when found | `README.md:18-19` |
| CUDA toolkit | 12.8+ enables the GPU backend; otherwise the build falls back to the CPU core with a CUDA runtime stub | `README.md:19-20` |
| Runtime deps | `msgpack>=1.1,<2`, `pydantic>=2.10`, `PyYAML>=6.0.2`, `typer>=0.16.0` | `pyproject.toml:11-16` |
| `debug` extra (workbench, debug cache, map PNG export) | `pyarrow>=19`, `duckdb>=1.2`, `fastapi>=0.115`, `uvicorn[standard]>=0.34` | `pyproject.toml:18-24` |
| `rerun-sdk` | not part of any declared extra; only `export-rerun` needs it | `src/magic_geo/cli/commands/export.py:218-221` |

```bash
python -m pip install -e .   # Python CLI + library (editable)
cmake -S . -B build          # configure the C++ simulation core
cmake --build build          # stages libmagic_geo_native.so into src/magic_geo/
magic-geo backend            # verify the native core loads
```

The console entry point is `magic-geo = "magic_geo.cli:main"` (`pyproject.toml:31`), which calls `main()` in `src/magic_geo/cli/__init__.py:22`. The Typer app is created with `no_args_is_help=True` and the help string `"Causal planet generator CLI."` (`src/magic_geo/cli/_app.py:13`). There is **no `@app.callback`**, so there are no global options beyond Typer's built-in `--install-completion`, `--show-completion`, and `--help`. The order commands appear in `--help` is fixed by the import order in `src/magic_geo/cli/commands/__init__.py:8-15`.

`magic-geo backend` prints `json.dumps(backend_info(), indent=2, sort_keys=True)` and takes no options (`src/magic_geo/cli/commands/config.py:52-55`). It is the fastest proof that the native library is staged and loadable. On the checkout used to write this page it emitted 178 keys; the ones worth reading first:

| Backend key | Observed value (this host) | Meaning |
|---|---|---|
| `active_backend` | `cpu` | Backend actually selected |
| `backend_scope` | `accelerated_native_kernels_not_end_to_end_pipeline` | Acceleration covers named kernels, not the whole pipeline |
| `backend_selection_reason` | `capability-only probe; no generation is active` | Probe mode, before any mesh size is known |
| `cuda_available` / `cuda_compiled` | `False` / `False` | Runtime stub build |
| `opencl_available` | `True` | A qualifying OpenCL platform was found |
| `cuda_auto_min_cell_count` | `8192` | Automatic CUDA offload threshold in actual cells |
| `opencl_auto_min_cell_count` | `32768` | Automatic OpenCL offload threshold in actual cells |
| `crust_overlap_accelerator_complete_parity_demonstrated` | `False` | Complete accelerator parity is explicitly **false** |
| `crust_overlap_geometry_and_csr_authoritative_backend` | `cpu` | Authoritative forward overlap runs on CPU |

Those last two are not incidental. The README states the position directly: geometry, coverage, membership classes, categories, and production state remain CPU-authoritative, and *complete accelerator parity is explicitly false* (`README.md:306-315`). Treat a GPU-enabled build as an optimization of specific kernels, not as an equivalent execution path.

---

## Step 1: create a config

`init-config` writes a validated, editable YAML file (`src/magic_geo/cli/commands/config.py:16-49`).

| Flag | Type | Default | Required | Help text (verbatim) |
|---|---|---|---|---|
| `--output`, `-o` | Path | `magic-geo.yaml` | no | `New YAML config path.` |
| `--profile`, `-p` | str | `earthlike` | no | `Built-in starting profile: default, earthlike, or smoke.` |
| `--set` | str, repeatable | none | no | `Override section.field=YAML_VALUE; repeat for multiple fields.` |
| `--force` | bool flag (no `--no-force`) | `False` | no | `Overwrite the target file.` |

The three registered profiles are defined in `src/magic_geo/config.py`:

| Profile | Description (verbatim from `_PROFILE_DESCRIPTIONS`) | Overrides applied on top of schema defaults |
|---|---|---|
| `default` | `Prescribed seasonal energy model with neutral physical inputs.` | none (`{}`) |
| `earthlike` | `4,096-cell Earth reference inputs for the seasonal model; new climate calibration is not established.` | `tectonics.plate_motion_scale_deg_per_step: 4.0`, `climate.precipitation_scale: 0.8` |
| `smoke` | `Small deterministic CPU seasonal configuration for integration checks.` | `run.name: smoke`, `mesh.cell_count: 128`, `tectonics.plate_count: 8`, `tectonics.plate_motion_scale_deg_per_step: 4.0`, `climate.precipitation_scale: 0.8`, `erosion.iterations: 1`, `compute.backend: cpu`, `compute.threads: 1` |

A configuration document has **9 sections with 43 fields plus the required root `config_version: 2`**. `WorldConfig()` deliberately constructs a current seasonal model. Every YAML document must explicitly supply the exact integer version; empty or unversioned files receive migration errors. `configs/earthlike_seed.yaml` materializes all fields of the `earthlike` profile. Temperature comes from the seasonal energy solution with `climate.reference_infrared_optical_depth`, not from the retired imposed-mean/lapse controls. See the [configuration reference](05-configuration-reference.md) for physical meaning and migration limits.

```bash
# Option A: use the checked-in Earth-like reference verbatim
#   configs/earthlike_seed.yaml

# Option B: generate your own, with typed overrides
magic-geo init-config \
  --profile earthlike \
  --set mesh.cell_count=512 \
  --set run.name=quickstart \
  --output runs/configs/quickstart.yaml
# -> Wrote runs/configs/quickstart.yaml | profile=earthlike
```

Notes that will save you time later:

| Behavior | Detail | Source |
|---|---|---|
| Override syntax | `section.field=YAML_VALUE`, split on the **first** `=` only; the value is parsed by `yaml.safe_load`, so `false`/`512`/`0.8`/`geodesic_icosahedron` all get their natural YAML types | `src/magic_geo/config.py:665` |
| Whole sections cannot be replaced | An override path that resolves to a dict raises `unknown configuration override '<path>'` | `src/magic_geo/config.py:738`, `:746` (in `apply_config_overrides`, `:710`) |
| Unknown keys rejected | Every model sets `extra="forbid"` | `src/magic_geo/config.py` model configs |
| NaN/Inf rejected | Every model sets `allow_inf_nan=False` | same |
| Duplicate YAML keys rejected | `_UniqueKeySafeLoader` raises rather than applying last-wins | `src/magic_geo/config.py:85-89` |
| Empty/unversioned YAML document | Rejected with required-version and migration guidance; the minimal document is `config_version: 2` | `src/magic_geo/config.py` |
| Cross-field rule | `tectonics.plate_count` must be `< mesh.cell_count` | `src/magic_geo/config.py:501` |
| Write safety | Atomic same-directory temp file, re-parsed for validation before commit; without `--force` it publishes with `os.link()` so a racing writer causes `FileExistsError` instead of a silent clobber | `src/magic_geo/config.py:800` |
| Overwrite without `--force` | Exits **2** with `<path> already exists; pass --force to overwrite` (re-raised as `typer.BadParameter`) | `src/magic_geo/cli/commands/config.py:47-48` |

The two resolution knobs you will reach for first:

| Field | Default | Range | Source |
|---|---|---|---|
| `mesh.cell_count` | `4096` | `ge=128`, `le=200000` | `src/magic_geo/config.py:244` |
| `erosion.iterations` | `6` | `ge=0`, `le=250` | `src/magic_geo/config.py:376` |
| `erosion.maturation_timestep_ma` | `5.0` | `gt=0.0`, `le=5.0` | `src/magic_geo/config.py:382` |

---

## Step 2: generate a full world

```bash
magic-geo generate \
  --config configs/earthlike_seed.yaml \
  --output runs/earthlike/world.json \
  --summary runs/earthlike/summary.md \
  --cells-csv runs/earthlike/cells.csv
```

Full option table (`src/magic_geo/cli/commands/generate.py:18-45`):

| Flag | Type | Default | Required | Help text (verbatim) |
|---|---|---|---|---|
| `--config`, `-c` | Path (`exists=True`) | `magic-geo.yaml` | no | `YAML config path.` |
| `--output`, `-o` | Path | `runs/world.json` | no | `World .json or fast .mgeo output path.` |
| `--summary` | Path or none | none | no | `Optional Markdown summary path.` |
| `--cells-csv` | Path or none | none | no | `Optional cell CSV path.` |
| `--cells` | int, `min=128` | none | no | `Override mesh.cell_count for smoke runs.` |
| `--geo-only` | bool flag (no negative form) | `False` | no | `Generate only natural geography enrichments; omit civilization, settlement, and history layers.` |
| `--format` | str | `auto` | no | `World serialization: auto (from suffix), json, or mgeo.` |

There are no positional arguments anywhere in this CLI — every parameter is a `typer.Option`.

### What the two console lines mean

```
Generating world | scope=full_world cells=4096
Wrote runs/earthlike/world.json | scope=full_world cells=4096 plates=14 ocean=0.608 rivers=90 elapsed=18.4s
```

| Line | Stream | Emitted at | Contents |
|---|---|---|---|
| `Generating world \| scope=… cells=…` | **stderr** (`err=True`) | before generation | `scope` is `geo_only` when `--geo-only` is set, else `full_world` (`generate.py:61-66`); `cells` is the post-override `mesh.cell_count` |
| `Wrote <path> \| scope=… cells=… plates=… ocean=… rivers=… elapsed=…s` | stdout | after all writes | fields read from `world["summary"]`: `cell_count`, `plate_count`, `ocean_fraction` (3 dp), `river_count`; `elapsed` is `time.monotonic()` measured from before generation to after the world, summary, and CSV are written (`generate.py:62`, `generate.py:84-90`) |

Because `elapsed` brackets the file writes, it is an end-to-end figure, not isolated simulation time.

### Serialization format selection

| `--format` | Behavior | Source |
|---|---|---|
| `auto` (default) | `mgeo` when the output suffix is in `{.mgeo, .mgpack, .msgpack, .mpk}`, else JSON | `src/magic_geo/serialization.py:35`, `:544` |
| `json` | Forces `json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)` | `src/magic_geo/io/json_writer.py:10-15` |
| `mgeo` | Forces the versioned MessagePack container (magic bytes `MGEO\r\n\x1a\n`), written atomically via a `.{name}.{hex}.tmp` file plus `fsync` and `os.replace` | `src/magic_geo/serialization.py:28`, `:475-529` |
| anything else | stderr `--format must be auto, json, or mgeo`, exit **2** | `generate.py:57-59` |

On read, `auto` sniffs the magic bytes rather than the suffix (`src/magic_geo/serialization.py:576-581`), so every consuming command accepts either format regardless of what you named the file.

One asymmetry worth knowing: `generate` writes with `validate_model=False` on the hot path because the generation pipeline owns the object and its JSON-value invariants (`generate.py:76-78`), while every CLI command that *reads* a world uses strict model validation (`src/magic_geo/cli/_app.py:18-20`).

### Exit codes for `generate`

| Exit | Cause | Source |
|---|---|---|
| 0 | success | — |
| 2 | config load failure (`OSError`, `ValidationError`, `ValueError`) | `generate.py:53-55` |
| 2 | `--format` not in `{auto, json, mgeo}` | `generate.py:57-59` |
| 2 | generation raised `RuntimeError` or `ValueError` | `generate.py:73-75` |
| 2 | Typer/Click usage errors: missing option, `--config` path does not exist, `--cells` below 128 | framework |

`generate` never exits 1.

---

## Step 3: inspect the outputs

Three artifacts, three writers, three very different jobs:

| Artifact | Flag | Default | Writer | Format |
|---|---|---|---|---|
| World document | `--output`, `-o` | `runs/world.json` | `write_world` (`src/magic_geo/serialization.py:532`) | JSON or `.mgeo` |
| Summary Markdown | `--summary` | not written unless requested | `write_summary_markdown` (`src/magic_geo/io/summary_markdown.py:9`) | Markdown |
| Cells CSV | `--cells-csv` | not written unless requested | `write_cells_csv` (`src/magic_geo/io/cells_csv.py:11`) | CSV |

All three writers `mkdir(parents=True, exist_ok=True)` their parent directory first.

### 3a. The world document

This is the authoritative artifact. Everything else on this page is a projection of it.

Observed shape of a full 512-cell world generated from `configs/earthlike_seed.yaml`:

| Level | Count observed |
|---|---|
| Top-level keys | 191 |
| `summary` keys | 1,293 |
| `backend` keys | 178 |
| Keys per entry in `cells` | 419 |
| `schema_version` | `2` (matches `CURRENT_WORLD_SCHEMA_VERSION`, `src/magic_geo/serialization.py:27`) |

The spine you will actually navigate first:

| Top-level key | What it holds | Reference |
|---|---|---|
| `schema_version` | integer `2`; `validate` rejects anything else before running any other check | `src/magic_geo/cli/commands/validate.py:100-122` |
| `name` | `run.name` from the config (default `earthlike_mvp`) | `src/magic_geo/config.py:135-140` |
| `summary` | high-level validation metrics and counts | `README.md:340` |
| `cells` | per-cell state; present only when `output.include_cells` is true | `src/magic_geo/config.py:446` |
| `backend` | the same probe dictionary `magic-geo backend` prints, but recorded for the actual run | `src/magic_geo/api.py:179-182` |
| `planet_parameters`, `planet_realism_checks` | generated planet-parameter snapshot plus v0 automatic realism checks | `README.md:341` |
| `simulation_clock`, `earth_system_feedback_history` | the native `coupled_geodynamic_stage_clock_v12` ledger | `README.md:342` |
| `mesh_backend`, `cell_area_model`, `mesh_lod`, `spherical_spatial_index` | mesh identity, control-volume area model, `cube_quadtree_v0` LOD index, `healpix_s2_compat_v0` index | `README.md:286` |
| `plate_kinematic_model`, `plate_motion_history`, `plates` | plate domains, per-step overlap ledgers, boundary segments | `README.md:347-348` |
| `sea_level_model` | `volume_constrained_connectivity_ocean_flood_v3` | `README.md:352` |
| `climate_model`, `hydrologic_water_budget_model`/`_history` | equilibrium climate and the causal land water-budget partition | `README.md:343-344` |
| `crust_material_shadow_model`/`_history`, `crust_dry_rock_accounting_model`/`_history` | always-emitted, explicitly **non-authoritative** audit ledger and counter-model | `README.md:350-351` |
| `settlements`, `routes`, `political_regions`, `cultures`, `historical_events`, `market_*` … | the civilization stack; absent in geo-only worlds | `src/magic_geo/api.py:86-104` |

Two epistemic markers to internalize immediately, because they recur throughout the schema:

- `crust_material_shadow_*` and `crust_dry_rock_accounting_*` are **audit ledgers, not state**. The model deliberately keeps `authoritative_for_cell_state`, physical source/sink and material-provenance resolution, solid volume, phase, mass-weighted age, upper-mantle, subducted-slab, and global crust-cycle conservation flags **false** (`README.md:350`). Their unresolved adjustments disclose where current rules lack physical endpoints; they do not supply those endpoints.
- Boundary-segment kinematics are **nominal**. The reported km/Ma scale is `radius_km * reference_motion_scale_deg_per_reference_step * pi/180 / 5 Ma` — "nominal, not an observed or calibrated plate speed" — and physical subduction polarity, slab selection/geometry/transfer, and material fate remain unresolved (`README.md:348`).

Reading the document from Python:

```python
from magic_geo.io import read_world

world = read_world("runs/earthlike/world.json")   # strict model validation by default
print(world["schema_version"], world["summary"]["cell_count"])
```

`read_world` sniffs JSON vs `.mgeo` from content, enforces `DEFAULT_MAX_WORLD_FILE_BYTES = 2 GiB` (`src/magic_geo/serialization.py:39`), and validates the value model unless you pass `validate_model=False`.

### 3b. The summary Markdown

`write_summary_markdown` is **not** a dump of the `summary` dict. It is a curated ordered filter plus count sections and the backend probe (`src/magic_geo/io/summary_markdown.py`). The following table records the earlier 512-cell artifact; its key counts and source line numbers are historical, not the current schema.

| Part | How it is produced | Observed on a 512-cell full world |
|---|---|---|
| `# <name>` | `world.get("name", "magic-geo world")` (`:15`) | `# earthlike_mvp` |
| `## Summary` | one `- \`key\`: value` bullet for each of the then **1,243** curated keys, emitted only `if key in summary` (`:20-1266`) | all 1,243 present |
| Count sections | 35 candidate section names (`boundary_counts` … `natural_frontier_type_counts`), each rendered as its own `## <section>` heading with sorted `key: value` bullets, and **skipped entirely when empty** (`:1268-1309`) | 35 of 35 rendered |
| `## Backend` | every `world["backend"]` key, sorted (`:1311-1313`) | 178 bullets |
| Total | — | 37 `##` headings, 1,629 bullets, 73,743 bytes |

Because the curated list is a filter, the Markdown is a strict subset of `summary`: 1,243 of 1,293 keys appeared in the observed run. If a metric you need is missing from the Markdown, read it from the world document, not from here.

The earlier artifact's opening bullets show its model identity block, which identifies the versions that produced it. Abridged — the real file has no gaps, and `…` below marks omitted intervening bullets:

```
- `seed`: 424242
- `mesh_backend`: fibonacci_sphere
- `cell_area_model`: spherical_voronoi_control_volume_v1
- `cell_count`: 512
- `output_float_precision`: 4
- `depression_routing_model`: raw_downhill_sink_units_with_priority_flood_spill_corridors_v1
- `depression_geology_model`: raw_sink_cell_crust_or_active_boundary_v1
- `numeric_depression_correction_model`: bounded_mass_conserving_breach_or_zero_material_temporary_lake_with_coupled_recomputation_v3
…
- `hydrologic_water_budget_model`: causal_land_climate_loss_partition_v1
…
- `river_extraction_model`: flow_accumulation_percentile_on_conditioned_hydrologic_surface_v1
```

In that export, the first five bullets (`seed` through `output_float_precision`) headed the curated list; the remaining identity block followed the depression, hydrologic-surface, water-budget, and river-extraction model names in source order. Consult the current writer for the current selection of summary keys.

### 3c. The cells CSV

`write_cells_csv` writes an ordered projection of `world["cells"]` using `csv.DictWriter(fieldnames=…, extrasaction="ignore")` (`src/magic_geo/io/cells_csv.py`). The header starts with the curated column list and appends any missing settlement, surface-applicability, and human-estimate support fields in a deterministic order. It is the same for full and geo-only worlds at a given software version; use the emitted header rather than a fixed column count.

The writer also creates a schema sidecar: `cells.csv` produces `cells.csv.schema.json`. Its `magic_geo_cell_csv_estimate_profile_v1` payload records the exact `columns`, `column_types`, `availability_fields`, scope, and model declarations. This describes the export; it does not independently validate the estimates.

| Property | Current behavior | Consequence |
|---|---|---|
| Columns | Curated list plus deduplicated support/applicability additions | Read the header or sidecar `columns` for the exact order |
| Rows | One CSV record per cell, plus the header | An empty `cells` list produces a header-only CSV |
| Extra cell keys | Dropped (`extrasaction="ignore"`) | Use the world document for fields outside the projection |
| Missing or null cell values | Both written as empty fields | Consult availability flags and model declarations; JSON distinguishes a missing key from explicit `null` |
| Boolean values | `True` / `False` | The sidecar records these lexical values and column types |
| `species_guild_scores` | Compact JSON object text within a CSV field | Parse that field as JSON rather than treating it as a scalar |
| Linked records | Not included in this cell projection | Resource deposits, histories, and other record families require JSON or record exports |

A numeric zero is preserved. For settlement v3, interpret `settlement_score` together with `settlement_climate_supported`, `is_water`, and `is_lake`: water/lake zero is structural, supported terrestrial zero is known, and unsupported terrestrial zero is the retained unavailable sentinel. Existing ecology and agriculture contracts also retain their declared zero sentinels and support flags. New derived human estimates use null plus their own typed support or availability fields; do not convert their blank CSV fields into zero. Missing legacy flags remain undeclared. The native seasonal coefficient and annual-budget columns are blank in explicit legacy-climate output, while current native seasonal output leaves retired post-hoc energy and bleaching estimates blank.

The earlier 512-cell measurement below had 419 keys per cell against the former 397 columns, with **22 cell fields then present only in the world document**. It predates the ecology support additions:

| Historically omitted cell field | Reason omitted in that export |
|---|---|
| `neighbors`, `cell_adjacency_edge_ids`, `control_volume_edge_neighbor_ids` | variable-length ID lists |
| `boundary_ring`, `control_volume_vertices_3d`, `position_3d`, `normal_3d` | vector/polygon geometry |
| `mesh_lod_tile_ids`, `mesh_lod_codes`, `mesh_lod_face_id` | per-level LOD lists |
| `temperature_monthly_c`, `precipitation_monthly_mm`, `wind_monthly_east`, `wind_monthly_north` | 12-element monthly arrays |
| `area_km2`, `is_water`, `fertility`, `soil_depth_m`, `bedrock_surface_elevation_m` | scalars simply not in the curated list |
| `boundary_convergent`, `boundary_divergent`, `boundary_transform` | boundary flags not in the curated list |

This is a historical omission list: for example, `is_water` is now included. For fields absent from the current sidecar's `columns`, use the world document, the debug cache (Step 7), or `export-debug`'s cell-details JSONL sidecar.

### Earlier observed artifact sizes (512-cell full world)

These measurements predate the ecology and settlement/social availability additions and the CSV schema sidecar. They describe the original artifacts, not current output sizes or column counts.

| File | Bytes | Shape |
|---|---|---|
| `world.json` | 61,966,781 | 191 top-level keys |
| `summary.md` | 73,743 | 37 headings / 1,629 bullets |
| `cells.csv` | 1,295,539 | 397 columns × 513 lines |

---

## Step 4: render an SVG and a raster

Both renderers are pure-Python, dependency-free, and read the world through the same strict loader (`src/magic_geo/cli/commands/render.py:41`, `:82`).

```bash
magic-geo render \
  --world runs/earthlike/world.json \
  --output runs/earthlike/world.svg \
  --projection mollweide --labels

magic-geo render-raster \
  --world runs/earthlike/world.json \
  --output runs/earthlike/world.ppm \
  --projection mollweide
```

### `render` (SVG)

| Flag | Type | Default | Required | Help text (verbatim) |
|---|---|---|---|---|
| `--world`, `-w` | Path (`exists=True`) | — | **yes** | `Generated .json or .mgeo world.` |
| `--output`, `-o` | Path | `runs/world.svg` | no | `SVG map output path.` |
| `--width` | int, `320..6400` | `1600` | no | `SVG width in pixels.` |
| `--height` | int, `160..3200` | `800` | no | `SVG height in pixels.` |
| `--projection` | str | `equirectangular` | no | `SVG projection: equirectangular, mollweide, or orthographic.` |
| `--labels` / `--no-labels` | bool | `False` | no | `Render settlement labels.` |
| `--max-cells` | int, `min=128` | none | no | `Optional maximum cells to render for low-detail maps.` |
| `--contours` / `--no-contours` | bool | `True` | no | `Render symbolic elevation contour layer.` |
| `--contour-interval` | float, `min=50.0` | `500.0` | no | `Contour interval in meters when contours are enabled.` |

### `render-raster` (PPM)

| Flag | Type | Default | Required | Help text (verbatim) |
|---|---|---|---|---|
| `--world`, `-w` | Path (`exists=True`) | — | **yes** | `Generated .json or .mgeo world.` |
| `--output`, `-o` | Path | `runs/world.ppm` | no | `PPM raster map output path.` |
| `--width` | int, `320..6400` | `1600` | no | `Raster width in pixels.` |
| `--height` | int, `160..3200` | `800` | no | `Raster height in pixels.` |
| `--projection` | str | `equirectangular` | no | `Raster projection: equirectangular, mollweide, or orthographic.` |
| `--max-cells` | int, `min=128` | none | no | `Optional maximum cells to render for low-detail rasters.` |
| `--texture` / `--no-texture` | bool | `True` | no | `Apply deterministic terrain texture.` |

### Projections and drawing model

| Projection | Implementation | Notes |
|---|---|---|
| `equirectangular` | direct lat/lon to pixel (`svg_map.py:152-153`, `raster_map.py:141-142`) | lines spanning more than `width * 0.55` are dropped as antimeridian wrap artifacts (`svg_map.py:263`, `raster_map.py:214`) |
| `mollweide` | 8-iteration Newton solve for the auxiliary angle (`svg_map.py:165-176`) | same solver in both renderers |
| `orthographic` | hemisphere projection; the far hemisphere returns `None` and is skipped (`svg_map.py:156-164`) | SVG adds a globe disc outline; the raster darkens pixels outside the disc |
| unknown value | `ValueError(f"unknown projection: {projection}")` → CLI exit **2** | `svg_map.py:31-32`, `render.py:54-56` |

Both normalize the input with `.lower().replace("_", "-")` before the membership test (`svg_map.py:30`, `raster_map.py:25`). In practice only the lowercasing has any effect: all three accepted names — `equirectangular`, `mollweide`, `orthographic` — are single words containing neither `_` nor `-`, so the substitution admits no additional spellings. `Mollweide` works; `equi_rectangular` does not.

Layer order actually drawn:

| Order | SVG (`svg_map.py`) | Raster (`raster_map.py`) |
|---|---|---|
| 1 | background rect `#173b56`, plus globe disc for orthographic | background RGB `(23, 59, 86)`, plus outside-disc darkening for orthographic |
| 2 | one `<circle class="terrain-cell">` per rendered cell, styled by `terrain_style` | one anti-aliased disc per rendered cell, colored by `terrain_rgb` |
| 3 | contour segments between land neighbors crossing each level (`--contours`) | *no contour layer* |
| 4 | route lines between settlement cells | route lines between settlement cells |
| 5 | sacred-area triangles, ruin squares | *not drawn* |
| 6 | settlement circles sized by `score` | settlement discs with a dark halo |
| 7 | up to 24 highest-scoring settlement labels (`--labels`) | *no labels* |

Both compute a per-cell "relief" as the cell's elevation minus the mean of its `neighbors` elevations, clamped at zero, and shade by it. The raster additionally applies a deterministic per-cell-ID hash noise when `--texture` is on (`raster_map.py:71-74`, `:133-137`) — this is a texture, not a subcell terrain model.

### `--max-cells` is naive stride slicing

```python
stride = max(1, math.ceil(len(cells) / max_cells))
render_cells = cells[::stride]
```

(`svg_map.py:182-184`, `raster_map.py:222-224`.) It ignores the `cube_quadtree_v0` mesh LOD index entirely; `docs/gui_debug_visualization_research.md` calls this out explicitly. Use it for speed, not for a spatially faithful decimation.

### Output formats

| Renderer | Container | Notes |
|---|---|---|
| `render` | SVG 1.1 text, with `data-projection`, `data-renderer="terrain-v1"`, `data-contours` attributes on the root element and a `<title>` derived from `world["name"]` | plain text; diffable |
| `render-raster` | Binary PPM `P6`, with the comment line `# magic-geo raster-terrain-v1 projection=<p> texture=<bool>` | size is exactly `header + width*height*3` bytes |

Observed on the 512-cell world at the default 1600×800 in `mollweide`: SVG 275,339 bytes; PPM 3,840,080 bytes (80-byte header + 3,840,000 pixel bytes).

Neither renderer exits 1. Failures are exit 2: a bad world file through `_load_world_for_cli` (`_app.py:16-23`) or a `ValueError` from the writer (`render.py:54-56`, `:93-95`).

---

## Step 5: run validate

```bash
magic-geo validate --world runs/earthlike/world.json
```

This is the full world-consistency gate. Its **entire** signature is one required option (`src/magic_geo/cli/commands/validate.py:92-94`):

| Flag | Type | Default | Required | Help text (verbatim) |
|---|---|---|---|---|
| `--world`, `-w` | Path (`exists=True`) | — | **yes** | `Generated .json or .mgeo world.` |

There are no per-domain toggles, no `--output`, no report file, and no severity policy switch. Output is `OK` on stdout, or one `FAIL <message>` line per failure on stderr.

### Two-phase structure

| Phase | Checks | Behavior |
|---|---|---|
| Early gate (`validate.py:100-122`) | `schema_version != 2`; retired schema fields present; `configured_planet_radius_km` / `surface_gravity_m_s2` raise | 3 `failures.append(...)` sites; prints the failures and **exits 1 immediately**, masking every other diagnostic |
| Main body (`validate.py:124-22333`) | 1,086 `failures.append(...)` sites plus the delegated validators, in a single 22,333-line command | all run unconditionally; exit 1 if any failure accumulated |

If you ever see only schema/planet failures, run the fix and re-run — the rest of the report was never produced.

### Exit codes

| Exit | Meaning |
|---|---|
| 0 | `OK` |
| 1 | early gate tripped, or any accumulated failure |
| 2 | world file could not be loaded or model-validated (`Invalid world file: <exc>`, `_app.py:21-23`) |

### What it delegates

The command imports 19 names from `src/magic_geo/cli/validators/` (`validate.py:68-88`) — 18 validator functions covering hydrology, rivers, sediment, settlement, political, navigability, ports, and corridors, plus the shared `_nominal_time_record_valid` helper — and a further set of top-level `magic_geo.*_validation` modules for crust overlap/transport, oceanic age-depth, initial oceanic crust age, plate boundary edges, crust material shadow, sediment interfaces, and the human/cultural/historical replay block (imported at `validate.py:15-45`). Package docstring contract: those validators are pure functions returning `list[str]`; **none of them raise or exit**.

### The narrower gate: `validate-geo`

For natural systems only:

```bash
magic-geo validate-geo \
  --world runs/earthlike/geo-world.json \
  --profile earthlike \
  --output runs/earthlike/geo-validation.json
# -> OK geo | checks=160 errors=0 warnings=0 not_applicable=1
```

| Flag | Type | Default | Required | Help text (verbatim) |
|---|---|---|---|---|
| `--world`, `-w` | Path (`exists=True`) | — | **yes** | `Generated .json or .mgeo world.` |
| `--profile` | str | `generic` | no | `Natural-system validation profile: generic or earthlike.` |
| `--output`, `-o` | Path | none | no | `Optional machine-readable validation report.` |
| `--fail-on-warnings` / `--allow-warnings` | bool | `False` | no | `Treat failed evidence-backed realism diagnostics as fatal.` |

`validate-geo` deliberately ignores settlements, routes, ports, politics, cultures, history, population, economy, markets, campaigns, and language (`README.md:217`). The report it writes carries that exclusion in its own payload; the observed report from a 512-cell geo world had these top-level keys: `checks`, `excluded_scope`, `layer_contracts`, `metrics`, `model_limitations`, `passed`, `profile`, `report_type` (`geo_world_validation_v1`), `requested_policy`, `schema_version` (`1`), `scope`, `summary`. Absent rivers, deltas, currents, or biomes are reported as `not_applicable` rather than receiving a vacuous perfect score (`README.md:217`).

Exit 1 when `report["passed"]` is false **or** any failed check has `severity == "error"` (or any failed check at all under `--fail-on-warnings`) — `validate_geo.py:55-61`, `:87-88`. Exit 2 for an unknown `--profile` (`validate_geo.py:50-52`).

---

## Step 6: run a geo-only generation

```bash
magic-geo generate \
  --geo-only \
  --config configs/earthlike_seed.yaml \
  --output runs/earthlike/geo-world.json
```

`--geo-only` routes to `generate_geo_world` instead of `generate_world` (`generate.py:68-72`). This is **not** a post-filter on a full world; it is a different native call plus a different, shorter enrichment sequence.

### What differs, precisely

| Aspect | `generate_world` | `generate_geo_world` |
|---|---|---|
| Native entry point | Current seasonal config: `native.generate_seasonal_world`; explicit legacy config: `native.generate_world` | Corresponding `native.generate_seasonal_geo_world` or `native.generate_geo_world`; civilization simulation is skipped natively |
| Placeholder cleanup | Full human records remain available to their consumers | `_strip_native_civilization_outputs` removes native human placeholders before natural enrichment |
| Scope marker | No `generation_scope` key added by this API | `world["generation_scope"] = "geo_only"` |
| `output.include_cells` | May be false; native cells are retained through the full enrichment sequence, then cleared for output | Must be true, otherwise `ValueError` |
| Enrichment scope | Shared physical/ecosystem/resource stages plus human transport, land use, society, and history | Shared natural stages with their declared geo scope; no human enrichment sequence |
| Graph/boundary enrichers | Full graph diagnostics and boundary geometry | Physical-only graph diagnostics and boundary geometry |
| Extra output | — | `geo_evolution_provenance` |

The current sequences and stripping sets are defined in `src/magic_geo/api.py`. The sets include the shared native-social registries from `src/magic_geo/native_social_public_validation.py`; they are not inferred from a field-name heuristic.

| Stripping set | What it removes |
|---|---|
| `NATIVE_CIVILIZATION_TOP_LEVEL_FIELDS` | Native human collections such as settlements, routes, cultures, populations, and snapshots; model declarations in `NATIVE_SOCIAL_PUBLIC_MODELS`, including `native_social_availability_model`; and the `native_social_availability` envelope |
| `NATIVE_CIVILIZATION_CELL_FIELDS` | `culture_region_id`, `language_region_id`, `political_region_id`, `settlement_score`, `settlement_climate_supported`, and `settlement_climate_temperature_c` |
| `NATIVE_CIVILIZATION_SUMMARY_FIELDS` | Native human counts/estimates and model mirrors, plus recorded-count and availability fields in `RECORDED_SUMMARY_FIELDS`, including `native_social_summary_availability` |

Geo-only absence is an explicit scope boundary, not an available zero-valued human estimate. Current seasonal geo resource deposits and commodities retain their material records, but full economic access/viability is unavailable in that scope: the corresponding values are null with false support. Separately named geographic accessibility/viability baselines remain numeric. The natural resource stages still apply their own biological support rules; geo scope does not make unsupported biological estimates available.

### Measured difference on a 512-cell run (same config, same seed)

This earlier measurement predates the ecology and settlement/social availability additions. The recorded sizes and field counts below describe the original artifacts. Current full and geo-only exports share a header whose exact columns are recorded in the CSV schema sidecar.

| Measure | Full world | Geo-only world | Delta |
|---|---|---|---|
| Top-level keys | 191 | 113 | net −78 (80 removed, 2 added) |
| `summary` keys | 1,293 | 974 | −319 |
| Keys per cell | 419 | 388 | −31 |
| `generation_scope` | absent | `geo_only` | — |
| `geo_evolution_provenance` | absent | present | — |
| Summary Markdown headings | 37 | 33 | −4 |
| CSV columns | 397 | 397 | unchanged (31 columns become empty strings) |
| `world.json` bytes | 61,966,781 | 62,422,716 | **+456 KB** |
| `summary.md` bytes | 73,743 | 58,956 | −14.8 KB |
| `cells.csv` bytes | 1,295,539 | 1,235,109 | −60 KB |
| CLI `elapsed` | 2.6 s | 2.6 s | ~0 |

The counter-intuitive result is real and worth remembering: **geo-only is not automatically a smaller world document.** In the observed run the added `geo_evolution_provenance` registry plus the extra physical-boundary/graph products more than offset the 80 removed civilization families. Geo-only is a *scope* switch (and a validation-surface switch), not a size optimization. Use `--cells` for size.

In that recorded comparison, the 80 removed top-level families covered the civilization stack: settlements, routes and corridors, ports, navigability, borders and political regions, territorial snapshots, cultures and language regions, phonology, historical eras/events, dynasties and cadet branches, population and economy histories, demographic and firm agents, logistics networks, market clearing/orders/exchanges/prices/inventories, campaign plans/movements/fronts/engagements, land-use and mining/agricultural zones, natural frontiers, worldbuilding realism checks, and the `trade_route_graph` / `political_region_graph` exports.

### `geo_evolution_provenance` and the time caveat

The registry that only geo-only worlds carry is `geo_evolution_provenance_registry_v2`. Observed scalar fields from a 512-cell geo world:

| Field | Observed value |
|---|---|
| `model_type` | `geo_evolution_provenance_registry_v2` |
| `generation_scope` | `geo_only` |
| `family_count` | 20 |
| `native_state_history_family_count` | 7 |
| `diagnostic_trajectory_family_count` | 13 |
| `nominal_time_model` | `configured_maturation_timestep_nominal_elapsed_time_v1` |
| `nominal_time_basis` | `configured_maturation_timestep_ma_per_erosion_transition_v1` |
| `nominal_time_source_parameter` | `erosion.maturation_timestep_ma` |
| `nominal_timestep_ma` | `5.0` |
| `final_nominal_elapsed_time_ma` | `30.0` |
| `nominal_time_coordinate_available` | `true` |
| **`nominal_time_calibrated`** | **`false`** |
| **`physical_time_resolved`** | **`false`** |

Read those last two literally. `final_nominal_elapsed_time_ma: 30.0` is `erosion.iterations` (6) × `erosion.maturation_timestep_ma` (5.0). It is a nominal bookkeeping coordinate. The clock explicitly keeps physical-time, process-rate calibration, absolute-age, and timestep-convergence claims **false** (`README.md:342`), and the age-depth model likewise states that the interval and operator "are not calibrated physical time" (`README.md:346`). Do not present "30 Ma of evolution" as a physical duration.

### When to use which

| Use `--geo-only` when | Use a full world when |
|---|---|
| You are iterating on tectonics, climate, hydrology, sediment, cryosphere, soils, biomes, or resources | You need settlements, routes, politics, cultures, history, population, economy, markets, or campaigns |
| You want `validate-geo` / `validate-geo-suite` to be the relevant gate | You want the full `validate` gate |
| You want the `geo_evolution_provenance` registry | You want the SVG/raster settlement, route, sacred-area, and ruin layers to draw anything |

A geo-only world renders fine, but `svg_map`/`raster_map` read `world.get("settlements", [])` and `world.get("routes", [])` (`svg_map.py:25-28`), which are simply absent — so those layers are empty and `--labels` produces nothing.

---

## Step 7: start the web workbench

```bash
python -m pip install -e '.[debug]'
magic-geo serve
# Serving web workbench with automatic workspace cache discovery
# (Config and Operations remain available) at http://127.0.0.1:8642
```

| Flag | Type | Default | Env var | Help text (verbatim) |
|---|---|---|---|---|
| `--debug-dir`, `-d` | Path (`exists=True`, dir only) | none | — | `Optional cache from export-debug; auto-loads <workspace>/debug when present.` |
| `--workspace` | Path | `runs` | `MAGIC_GEO_WORKSPACE` | `Directory for browser-created configs, worlds, reports, and exports.` |
| `--host` | str | `127.0.0.1` | `MAGIC_GEO_HOST` | `Bind address.` |
| `--port` | int, `1..65535` | `8642` | `MAGIC_GEO_PORT` | `Bind port.` |

Source: `src/magic_geo/cli/commands/serve.py:13-47`. Flags beat env vars, env vars beat defaults (Typer `envvar` semantics). Startup rules:

| Rule | Behavior | Source |
|---|---|---|
| Workspace containment | resolved against `Path.cwd()`; must satisfy `relative_to(project_root)` or exit **2** with `Web workspace must stay inside <root>` | `serve.py:50-63` |
| Explicit `-d` | must contain `manifest.json`, else exit **2** | `serve.py:70-75` |
| Automatic cache | `<workspace>/debug` is used only when `<workspace>/debug/manifest.json` is a file | `serve.py:64-69` |
| Invalid automatic cache | warns `Ignoring invalid automatic cache …` and restarts cacheless rather than failing | `serve.py:85-96` |
| Missing web deps | exit **2** with `pip install 'magic-geo[debug]'` | `serve.py:80-82` |
| Normal operation | blocks in `uvicorn.run(log_level="warning")` and never returns | `serve.py:109-114` |

`serve` works before any world exists (`README.md:59`).

### The first tour

Five tabs, hash-routed (`src/magic_geo/debug_ui/index.html:18-23`). Their left-to-right order in the tab bar is **Map, Data, Config, Operations, API**, and Map is the active tab on load; the table below is ordered by the sequence to *work* through on a first run, not by tab position:

| Visit order | Tab | Panel id | First thing to do |
|---|---|---|---|
| 1 | **Config** | `#view-config` | Pick a profile, edit the YAML in the textarea, press **Validate YAML**, then **Save configuration**. The browser default save name is `web-config.yaml` (`src/magic_geo/debug_server.py:844`) into `<workspace>/configs`. |
| 2 | **Operations** | `#view-operations` | Select **Generate world**, confirm the fields, press **Start job**. Every operation is a typed background job that runs `sys.executable -m magic_geo <command> …` — the argv is fixed and typed, never shell-evaluated. |
| 3 | **Map** | `#view-map` | Once the job finishes, the prepared cache is selected automatically and the globe renders `cells/elevation_m`. |
| 4 | **Data** | `#view-data` | Browse `overview / scalars / skipped / layers / cells / stages / families / sections` with an "Open raw JSON ↗" link to the exact revision-pinned API URL. |
| 5 | **API** | `#view-api` | Backend probe panel plus the embedded Swagger UI at `/api/docs`. |

The `generate` job form defaults (`src/magic_geo/web_jobs.py:110-125`):

| Field | Flag | Default | Notes |
|---|---|---|---|
| YAML config | `--config` | `runs/configs/world.yaml` | matches the Config view's default saved path |
| World file | `--output` | `runs/world.json` | |
| Markdown summary | `--summary` | unset | |
| Cells CSV | `--cells-csv` | unset | |
| Cell count override | `--cells` | unset, `minimum=128` | |
| Natural geography only | `--geo-only` | `false` | |
| World serialization | `--format` | `auto` | `auto` / `json` / `mgeo` |
| **Prepare browser cache** | *(no CLI flag)* | `true` | runs `export-debug` after generation and selects the cache |
| **Browser cache directory** | *(no CLI flag)* | `runs/debug` | |
| **Include ParaView VTU** | *(no CLI flag)* | `false` | |

Map view controls worth trying immediately:

| Control | Keys | Effect |
|---|---|---|
| Projection | `1` / `2` / `3` | Globe, Equirect, Mollweide (morphs between them) |
| Overlays | `w` / `b` / `g` | Wireframe, Plate boundaries, Graticule |
| Stage scrubbing | `,` / `.` | Step the stage slider for `*_stage` layers |
| Layer search | `/` | Filters by source, name, role, unit, family, description, category names |
| Layer docs card | `d` | Toggles the curated description panel |
| Close inspector | `Esc` | |
| Export | buttons | **Export PNG** and **Prompt .md** — the browser counterparts of `magic-geo export-debug-map` |

### Doing the same thing from the CLI

If you would rather not run a server, `export-debug` produces the identical cache:

```bash
magic-geo export-debug --world runs/earthlike/world.json --output runs/earthlike/debug --no-vtu
# -> Wrote runs/earthlike/debug | layers=438 stage_histories=2 families=120
#    mesh_vertices=3572 mesh_triangles=3060
```

| Flag | Type | Default | Help text (verbatim) |
|---|---|---|---|
| `--world`, `-w` | Path (`exists=True`), required | — | `Generated .json or .mgeo world.` |
| `--output`, `-o` | Path | `<world dir>/debug` | `Debug cache directory (default: <world dir>/debug).` |
| `--vtu` / `--no-vtu` | bool | `True` | `Also emit ParaView .vtu stage files and world.pvd.` |
| `--elevation-exaggeration` | float, `min=1.0` | `30.0` | `Radial elevation exaggeration for .vtu geometry.` |

Note the default-path asymmetry the README calls out (`README.md:64-68`): CLI `export-debug` with no `--output` writes `<world parent>/debug`, while the browser's prepared cache and browser `export-debug` default to `<workspace>/debug`.

### Security posture

The workbench is a trusted-local, single-user tool with **no authentication, no authorization, no per-user isolation, and no TLS** (`README.md:87-89`, `docs/debugger.md`). Anyone who can reach the port can read workspace data and submit or cancel jobs. Keep the default loopback binding, or front it with a trusted network boundary and an authenticating reverse proxy. The containment measures that do exist — workspace confinement, component-aware `relative_to` path checks, reserved `.magic-geo-web`, staged-and-validated cache publication, fingerprint-verified artifact downloads, and fixed subprocess argv — are containment, not a tenant boundary.

---

## Fast smoke-run recipe

```bash
magic-geo generate --config configs/earthlike_seed.yaml --cells 512 --output /tmp/world.json
```

That is the README's own smoke recipe (`README.md:35`). Two equivalent alternatives:

```bash
# 1. The registered smoke profile: 128 cells, 8 plates, 1 erosion iteration, single-threaded CPU
magic-geo init-config --profile smoke --output runs/configs/smoke.yaml
magic-geo generate --config runs/configs/smoke.yaml --output runs/smoke/world.json

# 2. Geo-only preview of a seed preset at reduced resolution
magic-geo generate --geo-only --config configs/seeds/pelagic_archipelago.yaml \
  --cells 512 --output runs/pelagic-preview.json
```

`--cells` rewrites `mesh.cell_count` and then re-validates the **entire** model (`generate.py:49-52`), so cross-field rules still apply — in particular `tectonics.plate_count` must stay below the new cell count (`config.py:501`). The floor is 128 in both the CLI (`generate.py:29`) and the schema (`config.py:244`).

### What fidelity you lose

| Fidelity dimension | What happens at low cell counts | Evidence |
|---|---|---|
| Spatial resolution | Cell area scales as `surface_area / cell_count`. Observed `mean_cell_area_km2` at 512 cells on an Earth-sized planet: **996,220 km²**, i.e. an equal-area circle roughly 1,100 km across. At 4,096 cells the README puts the figure at "roughly 400 km across". | observed `summary.mean_cell_area_km2`; `README.md:352` |
| Coastlines and shelves | The README is explicit: at 4,096 cells "lowering an entire margin cell to manufacture shelf area would replace both its land and deep-ocean portions with one elevation and is not a defensible correction". The required next architecture is conservative subcell hypsometry, which does not exist yet. Halving resolution makes this strictly worse. | `README.md:352` |
| River and basin statistics | The Hack-exponent fit only uses basins at or above `HACK_FIT_MINIMUM_BASIN_AREA_KM2 = 1,000,000 km²` (`src/magic_geo/scaling.py:8`). At 512 cells a qualifying basin is only ~1 cell, so the fit is dominated by a handful of samples. Observed `river_count`: 3 at 128 cells, 14 at 512, 90 at 4,096 — same seed, same config. | `src/magic_geo/scaling.py:8`, observed CLI output |
| Ocean fraction stability | Same config and seed, different meshes: `ocean=0.547` at 128 cells, `0.629` at 512, `0.608` at 4,096. Sea level is solved from a fixed water inventory against the mesh's own hypsometry, so ocean area is resolution-dependent. | observed CLI output; `README.md:352` |
| Mesh LOD depth | `max_level = clamp(ceil(log4(cell_count / 6)), 1, 6)` (`src/magic_geo/mesh_lod.py:14`), so a small mesh gets a shallow quadtree and fewer `level_summaries`. | `src/magic_geo/mesh_lod.py:14,77` |
| Accelerator eligibility | Automatic CUDA offload begins at 8,192 actual cells and uncalibrated CUDA/OpenCL at 32,768 (`cuda_auto_min_cell_count`, `opencl_auto_min_cell_count`, confirmed by the probe; `README.md:303-305`). Below those thresholds you always get the CPU reference path — which is deterministic, and is why the `smoke` profile pins `compute.backend: cpu`. | backend probe; `README.md:303-305` |
| Erosion history depth | The `smoke` profile also drops `erosion.iterations` to 1, so `earth_system_feedback_history`, `plate_motion_history`, and every stage ledger have one transition instead of six. Stage-scrubbing in the workbench becomes trivial. | `src/magic_geo/config.py:519-528` |
| Independent replay coverage | The bounded O(N²) Python polygon-intersection counter-implementation for crust overlap is capped at 1,024 cells; scaling it to the 4,096-cell reference is an open validation-evidence blocker. So the *strongest* independent evidence exists only at small meshes, while the reference resolution has weaker independent coverage. | `README.md:347` |

What you keep: determinism (same seed + same config + same cell count = same world), the full model chain, and every schema contract — `validate` and `validate-geo` run identically at 128 cells and at 4,096.

---

## Runtime and size expectations

**The repository does not publish a runtime-or-size table indexed by cell count.** Neither `README.md` nor any file under `docs/` contains one. What the repository *does* publish is a single-machine serialization benchmark at one resolution, plus test-suite runtimes.

### Published measurement (repository source)

From `docs/serialization_review.md:167-178` — one warm-cache run against a local, untracked `runs/earthlike/world.json` (the document's 4,096-cell reference artifact, `serialization_review.md:38`), on an Intel Core i5-14400F with Python 3.13.14 and msgpack 1.2.1. The document states plainly that these are "evidence for this machine, not CI thresholds":

| Trusted generated-world operation | JSON | `.mgeo` | Improvement |
|---|---:|---:|---:|
| File size | 387,454,418 B | 192,978,786 B | 50.2% smaller |
| Save | 2.503 s | 0.639 s | 3.92x faster |
| Load | 2.068 s | 0.796 s | 2.60x faster |

Peak process RSS for that full comparison plus a semantic digest was about 1.353 GB (`docs/serialization_review.md:186`).

Published test-suite runtimes (`README.md:238-245`, `:266-269`): full pytest suite ~29 min; `-m "not slow"` ~13 min; `-m "slow"` ~16 min; `--cov` ~2 h; 13 native CTest tests ~5 s.

### Single local observation (not a project benchmark)

Because a first-hour reader needs *some* sense of scale, the table below records one run of each command on the checkout used to write this page: Intel Core i5-14400F (16 threads), Python 3.13.14, `compute.backend: auto` resolving to `cpu`, `configs/earthlike_seed.yaml` with only `--cells` varied. These are **one warm run each, on one machine, against a staged native library older than the checked-out HEAD** — not a benchmark, not a threshold, and not reproducible across hosts. Do not cite them as project figures.

| Cells | `generate` `elapsed=` (full world, JSON) | `world.json` bytes | `validate` wall time | Notes |
|---:|---:|---:|---:|---|
| 128 | 0.8 s | 22,025,056 | 1.0 s | `ocean=0.547 rivers=3` |
| 512 | 2.6 s | 61,966,781 | 3.5 s | `ocean=0.629 rivers=14` |
| 4,096 | 18.4 s | 384,779,654 | 16.7 s | `ocean=0.608 rivers=90`; see the validate caveat below |

Related earlier single observations at 512 and 4,096 cells (before the ecology support additions):

| Operation | Observation |
|---|---|
| `generate --geo-only`, 512 cells | 2.6 s, `geo-world.json` 62,422,716 B |
| `generate --output *.mgeo`, 4,096 cells | 15.8 s, 191,492,463 B (vs 384,779,654 B JSON from the same config) |
| `--summary`, 512 cells | 73,743 B (full) / 58,956 B (geo-only) |
| `--cells-csv`, 512 cells | 1,295,539 B (full) / 1,235,109 B (geo-only), 397 columns either way |
| `render` (1600×800 mollweide, labels), 512 cells | 275,339 B SVG |
| `render-raster` (1600×800 mollweide), 512 cells | 3,840,080 B PPM |
| `export-debug --no-vtu`, 512 cells | 2.0 s, 32 MB on disk, `layers=438 stage_histories=2 families=120 mesh_vertices=3572 mesh_triangles=3060` |
| `validate-geo --profile earthlike`, 512-cell geo world | `checks=160 errors=0 warnings=0 not_applicable=1` |

Rule of thumb the observations support, and nothing stronger: world-document bytes and generation time both grow faster than linearly in cell count over 128 → 4,096, and `.mgeo` roughly halves the bytes. Anything more precise than that would be extrapolation.

---

## Limitations and unresolved claims

- **The physical time coordinate is not calibrated.** `geo_evolution_provenance` reports `nominal_time_calibrated: false` and `physical_time_resolved: false` (observed), and the simulation clock "explicitly keeps physical-time, process-rate calibration, absolute-age, and timestep-convergence claims false" (`README.md:342`). `final_nominal_elapsed_time_ma` is `erosion.iterations × erosion.maturation_timestep_ma`, a bookkeeping product.
- **Plate speeds are nominal.** The boundary-segment km/Ma scale is derived from `radius_km * reference_motion_scale_deg_per_reference_step * pi/180 / 5 Ma` and is "nominal, not an observed or calibrated plate speed" (`README.md:348`).
- **Subduction polarity is unresolved.** An oceanic-like side is recorded only as a *candidate* subducting side; the physical fields remain explicitly `unknown` wherever convergence is active, with source `none` and zero confidence. Physical polarity, slab selection/geometry/transfer, and material fate remain unresolved (`README.md:348`).
- **Mass provenance is unresolved.** `crust_material_shadow_*` is an always-emitted non-authoritative Phase-S audit ledger, and `crust_dry_rock_accounting_*` is a non-authoritative numerical counter-model whose exchange capacity "is explicitly uncalibrated and is not an estimate of mantle mass"; every transfer has `physical_basis_resolved: false`, and the slab tables are empty (`README.md:350-351`). Accounting closure is not physical provenance.
- **Accelerator parity is explicitly false.** The continuous-moment accelerator result is a *shadow*: it is reconciled against CPU CSR moments and then discarded. Geometry, coverage, membership classes, categories, and production state remain CPU-authoritative, and `crust_overlap_accelerator_complete_parity_demonstrated` is `false` in the backend probe (`README.md:306-315`, observed probe output).
- **Sea level is an ocean allocation, not a water-budget partition.** `volume_constrained_connectivity_ocean_flood_v3` allocates a configured inventory to the connected ocean; it is not a partition of total planetary water among ocean, ice, groundwater, lakes, and atmosphere, and `ocean_fraction_target` is a diagnostic area reference rather than the sea-level control (`README.md:352`).
- **Coarse-cell coastlines are a known architectural limit.** Conservative subcell hypsometry — area–elevation distributions and margin shelf–slope–rise profiles inside each coarse cell, with fractional flooding and subcell strait connectivity — is named as the *required next architecture*, not as something implemented (`README.md:352`).
- **Internal closure does not substitute for Earth fit.** The README's own suite report records 17/22 external empirical metrics passing, with failures in Natural Earth coastal land fraction, all three ETOPO relief metrics, and HydroBASINS non-Antarctic endorheic watershed area fraction, and states directly: "Internal closure and replay therefore do not substitute for the remaining Earth-fit gaps" (`README.md:234`).
- **`render --max-cells` is naive stride slicing.** It ignores the `cube_quadtree_v0` LOD index entirely (`svg_map.py:182-184`, `raster_map.py:222-224`; also called out in `docs/gui_debug_visualization_research.md`). The mesh LOD index itself is generation-time enrichment that no viewer currently consumes.
- **The `validate` early gate masks everything else.** A schema-version mismatch, a retired schema field, or an invalid planet parameter exits 1 before any other diagnostic runs (`validate.py:100-122`). An `OK`-free run with only schema failures is not a statement about the rest of the world.
- **Observed on this checkout, unreconciled:** running `magic-geo validate` on a freshly generated **4,096-cell** `configs/earthlike_seed.yaml` world produced exit 1 with `FAIL plate kinematic model or motion history invalid` and `FAIL crust ages exceed configured geological age` (`validate.py:6070`, `:6072`), while 128-cell and 512-cell worlds from the same config passed with `OK`. The staged `libmagic_geo_native.so` on this checkout was older than the checked-out HEAD commit, so a stale native library is a plausible cause; the README separately states the canonical Earth "has no core validation failure" (`README.md:234`). Treat this as a local observation and a reason to rebuild the native core after pulling — not as expected behavior. See [Troubleshooting and FAQ](./22-troubleshooting.md).
- **Runtime figures in this page's "single local observation" table are not project benchmarks.** The repository publishes no runtime-by-cell-count table; the only published performance evidence is the one-machine serialization comparison in `docs/serialization_review.md:167-186`.

---

## What to read next

| If you want to… | Read | Why |
|---|---|---|
| Understand every configuration field, range, and cross-field rule | [Configuration Reference](./05-configuration-reference.md) | All 9 sections and 44 leaf fields with constraints and descriptions |
| See every subcommand, flag, default, and exit code | [CLI Reference](./06-cli-reference.md) | The 15 subcommands and their complete option tables |
| Get the build right, including CUDA/OpenCL | [Installation and Build](./02-installation-and-build.md) | CMake, wheel policy, native library staging |
| Know what is actually in the world document | [World Document Schema](./10-world-schema.md) | Top-level families, cell fields, model contracts |
| Choose between JSON and `.mgeo`, or read worlds from Python | [Serialization and World Formats](./11-serialization.md), [Python API](./07-python-api.md) | Container format, safety limits, `read_world`/`write_world` |
| Understand what `validate` actually checks | [Validation](./12-validation.md) | The two-phase gate and the delegated validator families |
| Run the geo scenario matrix and paired response gates | [Geo Validation Suite](./13-geo-validation-suite.md) | `validate-geo-suite`, scenarios, relations, empirical fit |
| Compare a world against real Earth data | [Calibration Against Real-Earth Data](./14-calibration.md) | `derive-targets`, `calibrate`, `calibrate-ensemble` |
| Go deeper in the browser | [Web Workbench](./15-web-workbench.md), [Debug Exports and Visualization](./16-debug-and-visualization.md) | API routes, job system, debug cache layout, Rerun/ParaView |
| Make better maps | [Rendering and Map Output](./17-rendering.md) | Palettes, projections, contour layer, PPM/SVG internals |
| Pick a starting planet other than Earth | [Example Seeds and Presets](./20-seed-gallery.md) | The nine `configs/seeds/*.yaml` presets |
| Understand how the pieces fit together | [Architecture](./04-architecture.md), [Native Engine (C++ Core)](./08-native-engine.md) | Python/native boundary, module ownership |
| Fix something that went wrong | [Troubleshooting and FAQ](./22-troubleshooting.md) | Native library staleness, missing extras, cache errors |

---

## See also

- [Project Overview](./01-overview.md)
- [Installation and Build](./02-installation-and-build.md)
- [Architecture](./04-architecture.md)
- [Configuration Reference](./05-configuration-reference.md)
- [CLI Reference](./06-cli-reference.md)
- [Python API](./07-python-api.md)
- [Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md)
- [World Document Schema](./10-world-schema.md)
- [Serialization and World Formats](./11-serialization.md)
- [Validation](./12-validation.md)
- [Geo Validation Suite](./13-geo-validation-suite.md)
- [Web Workbench](./15-web-workbench.md)
- [Debug Exports and Visualization](./16-debug-and-visualization.md)
- [Rendering and Map Output](./17-rendering.md)
- [Docker Deployment](./19-docker-deployment.md)
- [Example Seeds and Presets](./20-seed-gallery.md)
- [Glossary](./21-glossary.md)
- [Troubleshooting and FAQ](./22-troubleshooting.md)
- [Mesh and Geometry](./features/mesh-and-geometry.md)
- [Tectonics and Plates](./features/tectonics-and-plates.md)
- [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md)
- [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md)
- [Climate and Atmosphere](./features/climate-and-atmosphere.md)
- [Settlements, Routes and Corridors](./features/settlements-and-routes.md)
