# Configuration Reference — every generation property, deep

Companion to [layers_reference.md](layers_reference.md). This documents every
property that shapes a generated world: what it controls, its type, default,
valid range, which layers/subsystems it moves, and its status/gaps.

The generation config is a single validated schema — `WorldConfig` in
[config.py](../src/magic_geo/config.py) — loaded from a YAML file
(`magic-geo generate --config <file>`). Every value below is verified against
that schema; ranges are the pydantic `Field` bounds, so anything outside them is
rejected at load time (`extra="forbid"` also rejects unknown keys, and
`allow_inf_nan=False` rejects `inf`/`nan`). Generate a starter file with
`magic-geo init-config`; the shipped seed is
[seed_config.yaml](../src/magic_geo/seed_config.yaml) and the reference earthlike
run is [configs/earthlike_seed.yaml](../configs/earthlike_seed.yaml).

## How configuration flows through generation

```text
config.yaml ──load_config──▶ WorldConfig (validated)
                               │  config_to_native() → dict
                               ▼
                     native engine (cpp/) ── tectonics → climate → hydrology → erosion
                               │            (geodynamic feedback loop, N erosion iterations)
                               ▼
                     world payload (cells + histories + models)
                               │
                               ▼
                     Python enrichers (soil, biomes, groundwater, resources,
                     human geography …) ── add the bulk of the ~450 layers
```

The nine config sections map onto the pipeline: `planet`/`mesh` set the stage,
`tectonics`/`climate`/`hydrology`/`erosion` drive the feedback loop that produces
the physical layers, and `compute`/`output` are operational. The Python enrichers
that add most layers are **not** individually configurable — they read the
generated physical state and run with fixed internal parameters (a documented
gap; see [Status & gaps](#status--gaps)).

## Reading the tables

- **Range** is the accepted interval. `(a, b)` is exclusive, `[a, b]` inclusive
  (matching pydantic `gt`/`lt` vs `ge`/`le`). Choices are shown for enums.
- **Affects** names the layer domains (see the layers reference) most directly
  moved by the property. Because the model is a coupled feedback loop, almost
  everything eventually touches elevation and climate; the column lists the
  first-order effect.

---

## `run` — run identity

| Property | Type | Default | Range | What it controls | Affects |
| --- | --- | --- | --- | --- | --- |
| `seed` | int | `424242` | `[0, 2⁶⁴−1]` | Master RNG seed. Every stochastic step derives from it, so a fixed seed + fixed thread count is bit-reproducible. | Everything (determinism). |
| `name` | str | `earthlike_mvp` | any string | World name, echoed into the payload and the debugger's world-info header. | Metadata only. |

---

## `planet` — planetary parameters

Sets the physical stage. These twelve values are snapshotted verbatim into
`planet_parameters` in the payload ([planet_parameters.py](../src/magic_geo/planet_parameters.py))
and read by both the native engine and the Python enrichers; several are
converted to absolute units on the fly (e.g. `gravity_g` × 9.80665 m/s²).

| Property | Type | Default | Range | What it controls | Affects |
| --- | --- | --- | --- | --- | --- |
| `radius_km` | float | `6371.0` | `(100, 100000]` | Planet radius. Scales all areas/distances (`area_km2`, channel lengths, sediment volumes) and the elevation→radial mapping. | geometry, hydrology, sediment |
| `gravity_g` | float | `1.0` | `(0.05, 5.0)` | Surface gravity relative to Earth. Enters ice-flow driving stress, hydraulic and isostatic calculations. | cryosphere, hydrology, tectonics |
| `day_length_hours` | float | `24.0` | `(1, 10000]` | Rotation period. Drives Coriolis strength → wind/current deflection and circulation-cell structure. | climate, ocean |
| `axial_tilt_deg` | float | `23.5` | `[0, 90]` | Obliquity. Sets seasonal insolation amplitude and the latitude of the seasonal swing. | climate (seasonality), cryosphere |
| `orbital_eccentricity` | float | `0.016` | `[0, 1)` | Orbit ellipticity. Modulates seasonal insolation asymmetry. | climate |
| `stellar_luminosity` | float | `1.0` | `(0.01, 100]` | Incident stellar flux relative to Sol. Scales the whole energy balance and baseline temperatures. | climate, cryosphere |
| `atmosphere_pressure_bar` | float | `1.0` | `[0, 1000]` | Surface pressure. Influences lapse/heat capacity and the energy balance. | climate |
| `greenhouse_factor` | float | `1.0` | `[0, 100]` | Greenhouse trapping multiplier. Directly sets `greenhouse_trapping_w_m2` and equilibrium temperatures. | climate |
| `ocean_fraction_target` | float | `0.70` | `[0, 0.95]` | Target fraction of surface below sea level; the sea-level solve aims for it. | geomorphology, ocean, hydrology |
| `ocean_water_inventory_km3` | float | `1.338e9` | `[0, 1e10]` | Total ocean water budget. Bounds sea level and the hydrologic water inventory. | ocean, water_budget |
| `internal_heat` | float | `1.0` | `[0, 100]` | Internal heat flow relative to Earth. Scales tectonic vigour and volcanic/geothermal potential. | tectonics, resources |
| `geological_age_ga` | float | `4.5` | `[0.01, 100]` | Planet age in billions of years. Sets crust-age ceilings and maturity of geologic systems. | tectonics, resources |

> **Cross-checks:** the `geo_validation` suite (`magic-geo validate-geo`) asserts
> the generated world stays Earth-like for the default planet; the planet-scaling
> tests ([tests/test_planet_scaling.py](../tests/test_planet_scaling.py)) assert
> radius/gravity actually move areas and stresses. Non-default planets are valid
> but only lightly covered — see gaps.

---

## `mesh` — spatial discretisation

| Property | Type | Default | Range | What it controls | Affects |
| --- | --- | --- | --- | --- | --- |
| `backend` | enum | `fibonacci_sphere` | `fibonacci_sphere`, `geodesic_icosahedron` | Cell tessellation. Fibonacci gives near-uniform areas; geodesic gives icosahedral structure. Recorded as `mesh_backend`. | geometry (all) |
| `cell_count` | int | `4096` | `[128, 200000]` | Number of cells = spatial resolution. The earthlike reference uses 32,768. Drives runtime and file size roughly linearly. | Everything (resolution) |
| `neighbor_count` | int | `7` | `[4, 16]` | Target adjacency degree per cell. Sets flow-routing and diffusion connectivity. | hydrology, sediment, geometry |

> **Constraint:** `plate_count` must be `< cell_count` (validated in `WorldConfig`).

---

## `tectonics` — plates & solid earth

Drives the deepest layer of the feedback loop; the `initial_*` tectonic layers
are the first-stage snapshot of its output.

| Property | Type | Default | Range | What it controls | Affects |
| --- | --- | --- | --- | --- | --- |
| `plate_count` | int | `14` | `[2, 256]` | Number of tectonic plates (must be `< cell_count`). Sets `plate_id` cardinality and boundary density. | tectonics, geomorphology |
| `continental_plate_fraction` | float | `0.38` | `[0, 1]` | Fraction of plates seeded continental. Biases land distribution. | tectonics, geomorphology |
| `continental_crust_fraction_target` | float | `0.34` | `[0, 0.95]` | Target share of continental crust area; the crust solve aims for it. | tectonics, geomorphology |
| `min_angular_speed` | float | `0.03` | `[0, 100]` | Lower bound on plate rotation speed (must be `≤ max`). Sets minimum boundary activity. | tectonics |
| `max_angular_speed` | float | `0.95` | `[0, 100]` | Upper bound on plate rotation speed. Sets peak convergence/divergence and orogenic uplift. | tectonics, geomorphology |
| `boundary_smoothing_steps` | int | `5` | `[0, 32]` | Smoothing iterations on plate boundaries. Higher = cleaner, less crenulated boundaries. | tectonics |
| `plate_motion_scale_deg_per_step` | float | `2.0` | `[0, 10]` | Degrees of plate motion applied per feedback step. Sets how fast crust transports and ages spatially. | tectonics |
| `oceanic_crust_aging_ma_per_step` | float | `5.0` | `[0, 50]` | Ma of oceanic-crust aging per step. Sets the `crust_age_ma` gradient from ridge to trench. | tectonics |

---

## `climate` — climate drivers

| Property | Type | Default | Range | What it controls | Affects |
| --- | --- | --- | --- | --- | --- |
| `months` | enum | `12` | `12` | Months in the seasonal cycle. Fixed at 12 (the monthly layers are 12-long). | climate, water_budget |
| `lapse_rate_c_per_km` | float | `6.5` | `[0, 15]` | Temperature drop per km of elevation. Sets mountain cooling → `temperature_c`, snowlines, biomes. | climate, cryosphere, ecology |
| `base_temperature_c` | float | `15.0` | `[−100, 100]` | Global mean sea-level temperature anchor. Shifts the whole climate. | climate (all) |
| `precipitation_scale` | float | `1.0` | `[0, 10]` | Global precipitation multiplier. Scales `precipitation_mm_y` → runoff, rivers, biomes. | water_budget, hydrology, ecology |
| `subtropical_drying_strength` | float | `0.65` | `[0, 0.9]` | Strength of subtropical (desert-belt) drying. Sets aridity of the horse latitudes. | climate, water_budget, ecology |

> Note the shipped earthlike config sets `precipitation_scale: 0.8` (drier than
> the schema default of 1.0).

---

## `hydrology` — routing policy

| Property | Type | Default | Range | What it controls | Affects |
| --- | --- | --- | --- | --- | --- |
| `river_percentile` | float | `0.92` | `[0.50, 0.995]` | Flow-accumulation percentile above which a cell is a river. Sets `is_river` density and network extent. | hydrology |
| `preserve_geologic_depressions` | bool | `true` | — | Whether real closed basins are preserved (endorheic) vs filled. Sets `depression_policy`, `is_closed_basin`, and the depression-fill history behaviour. | hydrology |

---

## `erosion` — landscape evolution

The feedback loop runs `iterations` erosion passes; these coefficients set the
stream-power law and hillslope diffusion that carve the final elevation.

| Property | Type | Default | Range | What it controls | Affects |
| --- | --- | --- | --- | --- | --- |
| `iterations` | int | `6` | `[0, 250]` | Number of erosion/feedback iterations. More = more mature landscapes; `0` disables erosion. Drives the stage count of the histories. | geomorphology, hydrology, sediment |
| `stream_power_coefficient` | float | `7.5` | `[0, 1000]` | Overall erosivity K in the stream-power law. Scales river incision. | hydrology, sediment |
| `drainage_exponent` | float | `0.5` | `[0, 2]` | Exponent m on drainage area in stream power (E ∝ Aᵐ Sⁿ). | hydrology, sediment |
| `slope_exponent` | float | `1.0` | `[0, 3]` | Exponent n on slope in stream power. | hydrology, sediment |
| `hillslope_diffusion` | float | `0.055` | `[0, 1]` | Hillslope sediment-diffusion coefficient. Smooths ridges, sets `hillslope_sediment_*`. | sediment, geomorphology |
| `tectonic_uplift_scale` | float | `0.85` | `[0, 10]` | Multiplier on tectonic uplift fed into each erosion step. Balances uplift against incision. | geomorphology, tectonics |

---

## `compute` — execution backend (operational)

Does not change *what* is generated, only *how* it is computed — except that
threading currently affects reproducibility (see gaps).

| Property | Type | Default | Range | What it controls | Affects |
| --- | --- | --- | --- | --- | --- |
| `backend` | enum | `auto` | `auto`, `cpu`, `opencl` | Compute backend. `auto` picks OpenCL if available, else CPU. | Performance (+ determinism, see gaps) |
| `threads` | int | `0` | `[0, 1024]` | CPU thread count; `0` = auto. | Performance, **determinism** |
| `opencl_prefer_gpu` | bool | `true` | — | Prefer GPU over CPU OpenCL devices when backend resolves to OpenCL. | Performance |

---

## `output` — payload shape (operational)

| Property | Type | Default | Range | What it controls | Affects |
| --- | --- | --- | --- | --- | --- |
| `include_cells` | bool | `true` | — | Whether per-cell arrays are written. **Required for the debugger** (`export-debug` errors without cells). | Debug cache availability |
| `float_precision` | int | `4` | `[0, 8]` | Decimal places for floats in the JSON payload. Trades file size against precision. | Payload size/precision |

---

## Other configuration surfaces (not generation)

These configure the analysis commands, not world generation, and produce no
layers:

- **Calibration** (`magic-geo calibrate` / `calibrate-ensemble`): `configs/calibration_sources.*.json`
  point at real-world datasets (ETOPO, WorldClim, HydroBASINS/RIVERS, Natural Earth);
  `configs/calibration_ensemble.r1.json` defines an ensemble sweep. Fetch scripts
  live in [scripts/](../scripts). These tune the empirical targets, not a run.
- **Geo-validation** (`magic-geo validate-geo` / `validate-geo-suite`):
  `configs/geo_validation_matrix.yaml` and `configs/geo_validation_earth_empirical_targets.json`
  define the physical-plausibility target bands the generated world is checked against.
- **Validation** (`magic-geo validate`): schema/consistency checks on a payload; no config.

---

## Status & gaps

**Coverage.** All 43 generation properties across 9 sections are validated by the
`WorldConfig` schema with explicit bounds; unknown keys and non-finite values are
rejected at load. Every property is documented above with its first-order effect.

**Gaps and caveats:**

- **Enricher parameters are not configurable.** The Python enrichers that produce
  the majority of layers (soils, biomes, groundwater, resources, reefs, human
  geography, …) run with fixed internal constants. Only the physical drivers
  (`planet`/`tectonics`/`climate`/`hydrology`/`erosion`) are exposed. Tuning a
  biome threshold or an aquifer index means editing the module, not the config.
- **Determinism vs threads (known regression).** Output currently varies with
  `compute.threads` / `OMP_NUM_THREADS` (documented in [debugger.md](debugger.md));
  a fixed thread count is bit-stable, but different counts differ. `seed` alone is
  not sufficient for reproducibility until this is fixed.
- **Non-Earth planets are lightly validated.** The schema permits extreme planets
  (tiny radius, high luminosity, etc.), and planet-scaling tests confirm the knobs
  move outputs, but the geo-validation target bands are Earth-tuned, so exotic
  configs are not asserted physically plausible.
- **`config_to_native` passes the whole dict through.** The native engine reads
  the sections it knows; there is no per-field "was this consumed?" report, so a
  property that a given backend ignores fails silently rather than warning.
- **No config-driven enable/disable of subsystems.** Every enricher always runs
  (given `include_cells`); you cannot switch off, say, the petroleum or dynasty
  models to shrink the payload. `erosion.iterations: 0` is the one coarse off-switch
  (disables the erosion/feedback passes).

To change a generation behaviour that isn't exposed here, the knob lives in the
producing module (see the **Produced by** lists in
[layers_reference.md](layers_reference.md)), not in the config schema.
