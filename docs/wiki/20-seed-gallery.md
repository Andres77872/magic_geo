# Example Seeds and Presets

[Wiki home](./README.md) > Example Seeds and Presets

The repository ships nine complete world presets in `configs/seeds/` plus the Earth-like reference `configs/earthlike_seed.yaml`. Each one is a standalone `WorldConfig` document that sets **all 44 leaf properties across all nine sections explicitly**, so a premise is inspectable without cross-referencing schema defaults and so schema drift breaks a test rather than silently changing a world. This page enumerates every property of every preset, derives the configuration-level physical forcings the engine actually computes from those numbers, and records the audited outcomes and known failure boundaries exactly as the repository records them. Nothing here upgrades a hedged claim: the audited observations are reference observations at one mesh resolution, not stable acceptance bands, and exotic presets are schema-valid but only lightly calibrated.

## On this page

- [Presets, profiles, and why every seed is explicit](#presets-profiles-and-why-every-seed-is-explicit)
- [How to run any seed](#how-to-run-any-seed)
- [Comparison matrix](#comparison-matrix)
- [Derived regime diagnostics](#derived-regime-diagnostics)
- [continental_realm](#continental_realm)
- [glasswind_desert](#glasswind_desert)
- [pelagic_archipelago](#pelagic_archipelago)
- [cryogenic_slushball](#cryogenic_slushball)
- [young_volcanic](#young_volcanic)
- [verdant_hothouse](#verdant_hothouse)
- [solstice_extreme](#solstice_extreme)
- [ironroot_super_earth](#ironroot_super_earth)
- [oldstone_stagnant](#oldstone_stagnant)
- [earthlike_seed (the reference configuration)](#earthlike_seed-the-reference-configuration)
- [Choosing a starting seed](#choosing-a-starting-seed)
- [Deriving your own preset](#deriving-your-own-preset)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Presets, profiles, and why every seed is explicit

There are two distinct mechanisms in this project that people call "presets", and they are not the same thing.

| Mechanism | Where it lives | How it is selected | Mutable by users | Count |
| --- | --- | --- | --- | --- |
| **Code-registered profile** | `_PROFILE_OVERRIDES` in `src/magic_geo/config.py:513`, described by `_PROFILE_DESCRIPTIONS` at `src/magic_geo/config.py:507` | `create_config("earthlike")` in the Python API; `magic-geo init-config --profile earthlike` (`src/magic_geo/cli/commands/config.py:21`) | No — editing requires a source change | 3 |
| **Shipped seed YAML** | `configs/seeds/*.yaml` and `configs/earthlike_seed.yaml` | `magic-geo generate --config <path>`; `load_config(path)` at `src/magic_geo/config.py:829` | Yes — copy the file and edit | 9 + 1 |

### The three code-registered profiles

`list_config_profiles()` (`src/magic_geo/config.py:704`) returns the stable tuple `("default", "earthlike", "smoke")`. A profile is applied as dotted-path overrides on top of a bare `WorldConfig()` by `create_config()` (`src/magic_geo/config.py:754`), so a profile is defined entirely by its **deltas from schema defaults**.

| Profile | Description string (`config.py:507`) | Deltas from schema defaults |
| --- | --- | --- |
| `default` | "Schema defaults suitable as a neutral editable starting point." | none (`{}`) |
| `earthlike` | "Calibrated 4,096-cell Earth-like reference configuration." | `tectonics.plate_motion_scale_deg_per_step` 2.0 → 4.0; `climate.precipitation_scale` 1.0 → 0.8 |
| `smoke` | "Small deterministic CPU configuration for fast integration checks." | `run.name` → `"smoke"`; `mesh.cell_count` → 128; `tectonics.plate_count` → 8; `tectonics.plate_motion_scale_deg_per_step` → 4.0; `climate.precipitation_scale` → 0.8; `erosion.iterations` → 1; `compute.backend` → `"cpu"`; `compute.threads` → 1 |

An unknown profile name raises `ConfigError` with `source="<profile>"` and the message `unknown configuration profile {profile!r}; choose one of: default, earthlike, smoke` (`src/magic_geo/config.py:760`).

### The shipped seeds are data, not profiles

`configs/seeds/*.yaml` are **not** registered in `_PROFILE_OVERRIDES` and cannot be selected by name from the CLI or API. They are ordinary configuration documents that you pass by path. They are also **not installed as package data**: `[tool.setuptools.package-data]` at `pyproject.toml:36` lists only the native library and the debug UI, while `MANIFEST.in:6` (`recursive-include configs *.json *.yaml`) puts them in the source distribution. This is why the README describes them as available "In a source checkout" (`README.md:147`).

### Why every seed sets all 44 properties

An omitted YAML key silently takes the `WorldConfig` schema default, and an empty document is exactly equivalent to the `default` profile (`src/magic_geo/config.py:612` pipeline). The gallery deliberately refuses that convenience:

| Reason | Evidence |
| --- | --- |
| A premise is readable from one file, with no mental diff against defaults | `docs/example_seed_gallery.md:3-7` |
| Schema drift becomes visible in a test instead of silently re-defaulting a world | `tests/test_config.py:66` and `:69-73` assert every seed's section set equals `set(WorldConfig.model_fields)` and every section's key set equals that section model's `model_fields` |
| Reviewability and reproducibility of a checked-in world premise | `docs/example_seed_gallery.md:177` |
| Named worlds must be distinguishable | `tests/test_config.py:81-82` asserts all nine `run.name` and all nine `run.seed` values are unique; `:75` asserts `run.name == path.stem` |
| Portable deterministic replay | `tests/test_config.py:76-78` asserts every seed uses `compute.backend == "cpu"`, `compute.threads == 1`, and `output.include_cells is True` |

The 44 count is the number of leaf fields in the schema: `run` 2, `planet` 12, `mesh` 3, `tectonics` 8, `climate` 5, `hydrology` 2, `erosion` 7, `compute` 3, `output` 2. Section classes are declared at `src/magic_geo/config.py:124` (`RunConfig`), `:156` (`PlanetConfig`), `:235` (`MeshConfig`), `:258` (`TectonicsConfig`), `:319` (`ClimateConfig`), `:354` (`HydrologyConfig`), `:371` (`ErosionConfig`), `:420` (`ComputeConfig`), `:441` (`OutputConfig`), with the root `WorldConfig` at `:458`. Every model sets `extra="forbid"` and `allow_inf_nan=False`, so an unknown key or a `.nan` value in a copied seed is a hard validation error, not a warning.

### What a seed cannot do

A seed biases the causal generator. It cannot request a named continent, an exact coastline, a city, a faction, a landmark, or a story outcome (`docs/example_seed_gallery.md:9-12`). `run.seed` selects a deterministic realization of the configured regime; it does not guarantee that a desired archipelago, inland sea, or supercontinent appears (`docs/example_seed_gallery.md:134-137`).

---

## How to run any seed

Every seed is run by path. The command surface below is exactly as implemented in `src/magic_geo/cli/commands/generate.py:18`.

| Flag | Short | Type | Default | Meaning |
| --- | --- | --- | --- | --- |
| `--config` | `-c` | existing path | `magic-geo.yaml` | YAML config path |
| `--output` | `-o` | path | `runs/world.json` | World `.json` or fast `.mgeo` output path |
| `--summary` | — | path | none | Optional Markdown summary path |
| `--cells-csv` | — | path | none | Optional cell CSV path |
| `--cells` | — | int, `min=128` | none | Override `mesh.cell_count` for smoke runs |
| `--geo-only` | — | flag | off | Generate only natural geography enrichments; omit civilization, settlement, and history layers |
| `--format` | — | `auto` \| `json` \| `mgeo` | `auto` | World serialization; `auto` selects from the output suffix |

Full-resolution run at the seed's declared mesh:

```bash
magic-geo generate \
  --config configs/seeds/continental_realm.yaml \
  --output runs/continental_realm/world.json \
  --summary runs/continental_realm/summary.md
```

Fast geo-only preview. `--cells` rewrites `mesh.cell_count` and re-validates the whole document (`generate.py:49-52`), so the plate-density rule at `src/magic_geo/config.py:500` still applies:

```bash
magic-geo generate \
  --geo-only \
  --config configs/seeds/continental_realm.yaml \
  --cells 512 \
  --output runs/continental_realm/geo-world-512.json
```

Validate an exotic world with the profile-appropriate gate (`src/magic_geo/cli/commands/validate_geo.py:23`; `--profile` accepts only `generic` or `earthlike`, enforced at `:50`):

```bash
magic-geo validate-geo \
  --world runs/continental_realm/geo-world-512.json \
  --profile generic \
  --output runs/continental_realm/geo-validation.json
```

Two mesh facts matter when you use `--cells`:

- `fibonacci_sphere` produces **exactly** `cell_count` cells (`cpp/src/engine/mesh.cpp:776`).
- `geodesic_icosahedron` rounds **up** to the nearest realizable subdivision. `geodesic_frequency_for_target` at `cpp/src/engine/mesh.cpp:840` computes `F = max(1, ceil(sqrt(max(0, (max(12, cell_count) - 2) / 10)) - 1e-9))` — the epsilon keeps an exactly realizable request from being pushed to the next frequency by floating-point error — and the mesh has `10·F² + 2` cells. So a requested 512 becomes 642 (`F = 8`), 2048 becomes 2252 (`F = 15`), and the declared 2562 of `continental_realm` is exact (`F = 16`). `docs/example_seed_gallery.md:25-26` states the 512 → 642 case.

All nine gallery seeds pin `compute.backend: cpu` and `compute.threads: 1` because output currently varies with `compute.threads` / `OMP_NUM_THREADS`: a fixed thread count is bit-stable, but different counts differ, and `seed` alone is not sufficient for reproducibility until that is fixed (`docs/configuration_reference.md:328-332`; `docs/example_seed_gallery.md:36-38`). Change those values when throughput matters more than exact replay. Note that `configs/earthlike_seed.yaml` does **not** pin threads — it keeps `backend: auto`, `threads: 0`.

---

## Comparison matrix

One row per shipped seed, one column per configuration property, split by section for readability. `earthlike_seed` is included as the reference row. All values are transcribed from the checked-in YAML.

### Identity and mesh

| Seed | `run.seed` | `run.name` | `mesh.backend` | `mesh.cell_count` | Realized cells | `mesh.neighbor_count` |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| `continental_realm` | 12051001 | continental_realm | geodesic_icosahedron | 2562 | 2562 (`F`=16) | 7 |
| `glasswind_desert` | 12051002 | glasswind_desert | fibonacci_sphere | 2048 | 2048 | 7 |
| `pelagic_archipelago` | 12051003 | pelagic_archipelago | fibonacci_sphere | 2048 | 2048 | 7 |
| `cryogenic_slushball` | 12051004 | cryogenic_slushball | fibonacci_sphere | 2048 | 2048 | 7 |
| `young_volcanic` | 12051005 | young_volcanic | fibonacci_sphere | 2048 | 2048 | 7 |
| `verdant_hothouse` | 12051006 | verdant_hothouse | fibonacci_sphere | 2048 | 2048 | 7 |
| `solstice_extreme` | 12051007 | solstice_extreme | fibonacci_sphere | 2048 | 2048 | 7 |
| `ironroot_super_earth` | 12051008 | ironroot_super_earth | fibonacci_sphere | 2048 | 2048 | **8** |
| `oldstone_stagnant` | 12051009 | oldstone_stagnant | fibonacci_sphere | 2048 | 2048 | 7 |
| `earthlike_seed` | 424242 | earthlike_mvp | fibonacci_sphere | 4096 | 4096 | 7 |

`mesh.neighbor_count` is read only by the Fibonacci builder (`cpp/src/engine/mesh.cpp:790`, the single reference in the mesh module). A geodesic mesh derives its stencil from triangle edges, so the field remains explicit in `continental_realm` for completeness but does not tune that backend the same way (`docs/example_seed_gallery.md:143-145`).

### Planet — size, rotation, orbit

| Seed | `radius_km` | `gravity_g` | `day_length_hours` | `axial_tilt_deg` | `orbital_eccentricity` |
| --- | ---: | ---: | ---: | ---: | ---: |
| `continental_realm` | 6371.0 | 1.00 | 24.0 | 23.5 | 0.016 |
| `glasswind_desert` | 5600.0 | 0.82 | 30.0 | 18.0 | 0.05 |
| `pelagic_archipelago` | 6200.0 | 0.95 | 20.0 | 17.0 | 0.02 |
| `cryogenic_slushball` | 6371.0 | 1.00 | 22.0 | 12.0 | 0.01 |
| `young_volcanic` | 4800.0 | 0.75 | 18.0 | 9.0 | 0.12 |
| `verdant_hothouse` | 6800.0 | 1.05 | 28.0 | 12.0 | 0.01 |
| `solstice_extreme` | 6371.0 | 1.00 | 30.0 | **75.0** | 0.08 |
| `ironroot_super_earth` | **9500.0** | **1.60** | 30.0 | 20.0 | 0.02 |
| `oldstone_stagnant` | 6000.0 | 0.90 | 36.0 | 8.0 | 0.02 |
| `earthlike_seed` | 6371.0 | 1.00 | 24.0 | 23.5 | 0.016 |

### Planet — energy, water, interior

| Seed | `stellar_luminosity` | `atmosphere_pressure_bar` | `greenhouse_factor` | `ocean_fraction_target` | `ocean_water_inventory_km3` | `internal_heat` | `geological_age_ga` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `continental_realm` | 1.00 | 1.00 | 1.00 | 0.58 | 850,000,000 | 1.00 | 4.8 |
| `glasswind_desert` | 1.10 | 0.70 | 1.05 | 0.00 | **0** | 0.75 | 5.6 |
| `pelagic_archipelago` | 1.02 | 1.25 | 1.08 | 0.88 | 2,500,000,000 | 1.20 | 3.6 |
| `cryogenic_slushball` | **0.55** | 0.90 | **0.50** | 0.72 | 1,450,000,000 | 0.90 | 4.2 |
| `young_volcanic` | 1.35 | 1.40 | 1.50 | 0.25 | 200,000,000 | **2.50** | **0.80** |
| `verdant_hothouse` | 1.25 | 1.80 | **1.55** | 0.76 | 1,600,000,000 | 1.20 | 3.8 |
| `solstice_extreme` | 0.98 | 1.10 | 1.00 | 0.66 | 1,100,000,000 | 1.00 | 4.5 |
| `ironroot_super_earth` | 1.00 | 1.80 | 1.05 | 0.70 | **3,020,000,000** | 1.30 | 5.0 |
| `oldstone_stagnant` | 0.90 | 0.80 | 0.85 | 0.45 | 430,000,000 | **0.10** | **9.50** |
| `earthlike_seed` | 1.00 | 1.00 | 1.00 | 0.70 | 1,338,000,000 | 1.00 | 4.5 |

`ocean_water_inventory_km3`, **not** `ocean_fraction_target`, drives the sea-level flood solve: `apply_sea_level` at `cpp/src/engine/ocean.cpp:5` reads `params.ocean_water_inventory_km3` into `target_volume_km3` at `:29` and searches connected components for a sea level whose flooded volume matches. `ocean_fraction_target` is only a diagnostic comparison value: the native engine range-checks it to `[0, 0.95]` (`cpp/src/engine/core.cpp:340-341`), echoes it back into the serialized params (`cpp/src/engine/world_serialization.cpp:34`) and into the summary as `target_ocean_fraction` (`cpp/src/engine/summary.cpp:1624`), and uses it in `sea_level_model_json` to compute target-versus-realized diagnostics (`cpp/src/engine/process_serialization.cpp:3348`, clamped to `[0, 0.98]` at `:3354` and `:3375`). No code path feeds it into the flood solve, so the realized fraction will differ and can change with mesh resolution (`docs/example_seed_gallery.md:131-133`).

A zero inventory takes a dedicated branch: sea level is set below the minimum cell elevation and every cell is forced to `is_water = false`, `water_depth_m = 0`, `is_lake = false` (`cpp/src/engine/ocean.cpp:30-45`). That is what makes `glasswind_desert` an ocean-free world by construction rather than by tuning.

### Tectonics

| Seed | `plate_count` | `continental_plate_fraction` | `continental_crust_fraction_target` | `min_angular_speed` | `max_angular_speed` | `boundary_smoothing_steps` | `plate_motion_scale_deg_per_step` | `oceanic_crust_aging_ma_per_step` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `continental_realm` | 12 | 0.58 | 0.52 | 0.03 | 0.85 | 7 | 3.0 | 5.0 |
| `glasswind_desert` | 8 | 0.78 | 0.72 | 0.01 | 0.45 | 8 | 1.5 | 3.0 |
| `pelagic_archipelago` | 24 | 0.28 | **0.18** | 0.08 | 1.15 | 3 | 4.0 | 6.0 |
| `cryogenic_slushball` | 12 | 0.40 | 0.34 | 0.02 | 0.70 | 6 | 2.5 | 5.0 |
| `young_volcanic` | **28** | 0.30 | 0.24 | 0.30 | **1.80** | **2** | **4.5** | **8.0** |
| `verdant_hothouse` | 16 | 0.38 | 0.30 | 0.05 | 1.05 | 5 | 3.5 | 5.0 |
| `solstice_extreme` | 14 | 0.44 | 0.40 | 0.03 | 0.90 | 5 | 3.0 | 5.0 |
| `ironroot_super_earth` | 20 | 0.42 | 0.36 | 0.03 | 0.90 | 6 | 2.5 | 5.0 |
| `oldstone_stagnant` | **6** | 0.70 | **0.65** | **0.0** | **0.0** | **12** | **0.0** | **0.0** |
| `earthlike_seed` | 14 | 0.38 | 0.34 | 0.03 | 0.95 | 5 | 4.0 | 5.0 |

### Climate and hydrology

| Seed | `months` | `lapse_rate_c_per_km` | `base_temperature_c` | `precipitation_scale` | `subtropical_drying_strength` | `river_percentile` | `preserve_geologic_depressions` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `continental_realm` | 12 | 6.5 | 14.0 | 1.00 | 0.60 | 0.90 | true |
| `glasswind_desert` | 12 | 7.5 | 32.0 | **0.08** | **0.88** | **0.97** | true |
| `pelagic_archipelago` | 12 | 6.0 | 18.0 | 1.40 | 0.45 | 0.88 | true |
| `cryogenic_slushball` | 12 | 6.5 | **−10.0** | 0.60 | 0.45 | 0.94 | true |
| `young_volcanic` | 12 | 7.0 | 32.0 | 0.50 | 0.70 | 0.93 | true |
| `verdant_hothouse` | 12 | **5.5** | 30.0 | **1.80** | **0.30** | **0.86** | **false** |
| `solstice_extreme` | 12 | 6.5 | 12.0 | 1.00 | 0.55 | 0.92 | true |
| `ironroot_super_earth` | 12 | 6.0 | 14.0 | 1.10 | 0.60 | 0.91 | true |
| `oldstone_stagnant` | 12 | 6.5 | 8.0 | 0.65 | 0.72 | 0.94 | true |
| `earthlike_seed` | 12 | 6.5 | 15.0 | 0.80 | 0.65 | 0.92 | true |

`climate.months` is `Literal[12]` (`src/magic_geo/config.py:324`) — twelve is the only accepted value, for every world. `river_percentile` is clamped to `[0.5, 0.999]` and used as an index into the sorted flow-accumulation array (`cpp/src/engine/hydrology.cpp:712`). `preserve_geologic_depressions` gates whether a sink that is a geologic depression is kept instead of being routed out (`cpp/src/engine/hydrology.cpp:556`); `verdant_hothouse` is the only seed that turns it off, and `tests/test_config.py:105-110` asserts that both polarities are represented in the catalog.

### Erosion

| Seed | `iterations` | `maturation_timestep_ma` | `stream_power_coefficient` | `drainage_exponent` | `slope_exponent` | `hillslope_diffusion` | `tectonic_uplift_scale` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `continental_realm` | 6 | 5.0 | 7.5 | 0.50 | 1.0 | 0.055 | 1.00 |
| `glasswind_desert` | **4** | 5.0 | **3.0** | 0.45 | 1.0 | **0.025** | 0.55 |
| `pelagic_archipelago` | 6 | 5.0 | 9.0 | 0.50 | 1.1 | 0.070 | 1.15 |
| `cryogenic_slushball` | 5 | 5.0 | 4.5 | 0.50 | 1.0 | 0.040 | 0.75 |
| `young_volcanic` | 6 | **2.5** | 10.0 | 0.55 | **1.2** | 0.080 | **2.00** |
| `verdant_hothouse` | 7 | 4.0 | **11.0** | 0.55 | 1.1 | 0.085 | 1.10 |
| `solstice_extreme` | 6 | 5.0 | 7.5 | 0.50 | 1.0 | 0.055 | 0.90 |
| `ironroot_super_earth` | 6 | 5.0 | 8.0 | 0.50 | 1.0 | 0.050 | 1.00 |
| `oldstone_stagnant` | **10** | 3.0 | 9.0 | 0.50 | 1.0 | **0.100** | **0.00** |
| `earthlike_seed` | 6 | 5.0 | 7.5 | 0.50 | 1.0 | 0.055 | 0.85 |

### Fields that are constant across all nine gallery seeds

| Property | Value in all nine seeds | Value in `earthlike_seed` | Why |
| --- | --- | --- | --- |
| `climate.months` | 12 | 12 | `Literal[12]`; not configurable (`config.py:324`) |
| `compute.backend` | `cpu` | `auto` | Portable deterministic replay (`tests/test_config.py:76`) |
| `compute.threads` | 1 | 0 | Bit-stability at a fixed thread count (`tests/test_config.py:77`; `docs/configuration_reference.md:328-332`) |
| `compute.opencl_prefer_gpu` | `true` | `true` | Inert while `backend: cpu`; kept explicit for completeness |
| `output.include_cells` | `true` | `true` | Enrichers, validation, and the debugger all need per-cell state (`docs/example_seed_gallery.md:140-142`) |
| `output.float_precision` | 4 | 4 | General JSON decimal precision; replay-critical fields use higher fixed floors (`config.py:450`) |

---

## Derived regime diagnostics

These are not configuration fields. They are the configuration-level scalars the native engine computes from the planet and climate numbers above, reproduced here so a preset's regime can be read quantitatively. Every formula is transcribed from source; the values are computed from the checked-in YAML.

| Quantity | Formula | Source |
| --- | --- | --- |
| Stellar temperature forcing (°C) | `38.0 · (L^0.25 − 1)` | `cpp/src/engine/core.cpp:9`, constant `CLIMATE_STELLAR_TEMPERATURE_RESPONSE_C = 38.0` at `cpp/src/engine/constants.hpp:14` |
| Greenhouse temperature forcing (°C) | `11.0 · (G − 1)` | `cpp/src/engine/core.cpp:14`, constant at `constants.hpp:15` |
| Pressure temperature adjustment (°C) | `4.5 · ln(max(0.01, p))` | `cpp/src/engine/climate.cpp:257` |
| Thermal moisture capacity factor | `clamp(exp(0.04 · (T_base − 15 + stellar + greenhouse)), 0.35, 2.25)` | `cpp/src/engine/core.cpp:26`; constants at `constants.hpp:16,20,21,22` |
| Pressure precipitation factor | `clamp(p^0.35, 0.35, 1.85)` | `cpp/src/engine/climate.cpp:258` |
| Gravity precipitation factor | `clamp(1.08 − 0.10 · (g − 1), 0.65, 1.35)` | `cpp/src/engine/climate.cpp:259` |
| Tectonic activity | `clamp(internal_heat · sqrt(4.5 / max(0.05, age_Ga)), 0.25, 2.25)` | `cpp/src/engine/tectonics.cpp:19`, `:294-295`, `:1213` |
| Gravity relief scale | `clamp(1 / sqrt(max(0.08, g)), 0.55, 1.60)` | `cpp/src/engine/tectonics.cpp:294` |
| Rotation band shift (deg) | `clamp((day_hours − 24) / 24 · 5, −7, 9)` | `cpp/src/engine/climate.cpp:266` |
| Eccentricity season factor | `1 + 1.8 · clamp(e, 0, 0.8)` | `cpp/src/engine/climate.cpp:267` |
| Seasonal amplitude multiplier | `(tilt / 23.5) · eccentricity_season_factor` | `cpp/src/engine/climate.cpp:403-404` |

### Computed values per seed

| Seed | Stellar °C | Greenhouse °C | Pressure °C | Thermal-mean anchor °C | Moisture factor | Global precip gain | Tectonic activity | Relief scale | Season multiplier | Band shift ° |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `continental_realm` | 0.000 | 0.00 | 0.000 | 14.00 | 0.961 | 1.038 | 0.968 | 1.000 | 1.029 | 0.00 |
| `glasswind_desert` | +0.916 | +0.55 | −1.605 | 31.86 | 2.093 | **0.162** | 0.672 | 1.104 | 0.835 | +1.25 |
| `pelagic_archipelago` | +0.189 | +0.88 | +1.004 | 20.07 | 1.177 | 1.933 | 1.342 | 1.026 | 0.749 | −0.83 |
| `cryogenic_slushball` | **−5.275** | **−5.50** | −0.474 | **−21.25** | **0.350** (floor) | 0.219 | 0.932 | 1.000 | 0.520 | −0.42 |
| `young_volcanic` | +2.961 | +5.50 | +1.514 | 41.97 | 2.250 (ceiling) | 1.398 | **2.250** (ceiling) | 1.155 | 0.466 | −1.25 |
| `verdant_hothouse` | +2.180 | +6.05 | +2.645 | 40.88 | 2.250 (ceiling) | **5.348** | 1.306 | 0.976 | 0.520 | +0.83 |
| `solstice_extreme` | −0.191 | 0.00 | +0.429 | 12.24 | 0.880 | 0.983 | 1.000 | 1.000 | **3.651** | +1.25 |
| `ironroot_super_earth` | 0.000 | +0.55 | +2.645 | 17.20 | 0.982 | 1.354 | 1.233 | **0.791** | 0.882 | +1.25 |
| `oldstone_stagnant` | −0.988 | −1.65 | −1.004 | 4.36 | 0.680 | 0.446 | **0.250** (floor) | 1.054 | 0.353 | +2.50 |
| `earthlike_seed` | 0.000 | 0.00 | 0.000 | 15.00 | 1.000 | 0.864 | 1.000 | 1.000 | 1.029 | 0.00 |

"Thermal-mean anchor" is `base_temperature_c + stellar + greenhouse + pressure`, the four configuration-level terms that enter every cell's monthly temperature identically at `cpp/src/engine/climate.cpp:405-408`. "Global precip gain" is `precipitation_scale × pressure_precip_factor × gravity_precip_factor × thermal_moisture_capacity_factor`, the four configuration-level multipliers applied to every cell at `cpp/src/engine/climate.cpp:460-463` and `:470-471`; per-cell spatial factors (orographic, rain shadow, ocean current, advected moisture, circulation, subtropical drying, monsoon) multiply on top and are not included, and water cells take an additional flat 1.20 at `:459` that land cells do not.

The anchor column matches the audited global mean temperature of every seed to within 0.1 °C (compare with the audit table below). That agreement is an emergent property of how the field is assembled — the latitude term carries an area-mean offset `47/(3+1)` at `climate.cpp:382-386` and the area-weighted local adjustment is subtracted back out at `climate.cpp:289` and `:408` — and is reported here as an observation on these ten configurations, not as a guaranteed invariant of the model.

### Audited outcomes at declared resolution

Reference observations recorded in `docs/example_seed_gallery.md:63-73`. Each exact checked-in seed was generated with `generate_geo_world` at its declared resolution and passed through the `generic` geo validator; all nine complete all 14 layer-contract families (`src/magic_geo/geo_layer_contracts.py:26` declares exactly 14 contracts) with zero validation errors. Warnings are nonfatal realism observations. **These are reference observations, not stable acceptance bands for edited parameters or future engine versions** (`docs/example_seed_gallery.md:60-61`).

| Seed | Cells | Ocean fraction | Mean °C | Land precip mm/y | Defining generated evidence | Generic result |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `continental_realm` | 2,562 | 0.340 | 14.0 | 932 | 6 landmasses; 33.0% forest land; 19.0 °C seasonal land range | 14/14 layers, 0 warnings |
| `glasswind_desert` | 2,048 | 0.000 | 31.9 | 94 | 87.5% desert land; no rivers; one landmass | 14/14 layers, 2 warnings |
| `pelagic_archipelago` | 2,048 | 0.916 | 20.1 | 3,317 | 10 landmasses in the remaining 8.4% land area | 14/14 layers, 1 warning |
| `cryogenic_slushball` | 2,048 | 0.616 | −21.2 | 268 | 24.4% ice cells; no forest/desert land | 14/14 layers, 2 warnings |
| `young_volcanic` | 2,048 | 0.240 | 42.0 | 1,174 | 326 volcanic-arc cells; 286 high-seismic-hazard cells; 7 landmasses | 14/14 layers, 2 warnings |
| `verdant_hothouse` | 2,048 | 0.655 | 40.9 | 7,338 | 81.0% forest land; no desert land; 4.9% river cells | 14/14 layers, 0 warnings |
| `solstice_extreme` | 2,048 | 0.468 | 12.2 | 1,071 | 43.7 °C mean seasonal land-temperature range | 14/14 layers, 0 warnings |
| `ironroot_super_earth` | 2,048 | 0.578 | 17.2 | 1,612 | 10 landmasses; 42.0% forest land | 14/14 layers, 0 warnings |
| `oldstone_stagnant` | 2,048 | 0.257 | 4.4 | 358 | 40.3% desert land; 10.4% ice cells; zero configured plate motion | 14/14 layers, 2 warnings |

Note the gap between `ocean_fraction_target` and the realized ocean fraction — `continental_realm` targets 0.58 and realizes 0.340, `oldstone_stagnant` targets 0.45 and realizes 0.257. That is expected: the target is diagnostic only, and the inventory does the work.

### The `earthlike` validation envelope, and why `generic` is the right profile here

`magic-geo validate-geo --profile earthlike` adds a fixed envelope (`_validate_earthlike_profile`, `src/magic_geo/geo_validation.py:764-800`) that most gallery presets are designed to violate.

| Metric | Earth-like accepted range | Seeds that clearly fall outside (from the audit above) |
| --- | --- | --- |
| `ocean_fraction` | 0.55 – 0.85 | `glasswind_desert` 0.000, `continental_realm` 0.340, `young_volcanic` 0.240, `oldstone_stagnant` 0.257, `pelagic_archipelago` 0.916, `solstice_extreme` 0.468 |
| `global_mean_temperature_c` | 8.0 – 22.0 | `glasswind_desert` 31.9, `cryogenic_slushball` −21.2, `young_volcanic` 42.0, `verdant_hothouse` 40.9, `oldstone_stagnant` 4.4 |
| `mean_land_precipitation_mm_y` | 350.0 – 1800.0 | `glasswind_desert` 94, `cryogenic_slushball` 268, `pelagic_archipelago` 3,317, `verdant_hothouse` 7,338 |
| `elevation_span_m` | 8000.0 – 25000.0 | not measured in the published audit table |
| `river_cell_fraction` | 0.002 – 0.08 | `glasswind_desert` has no rivers |
| `ice_cell_fraction` | 0.005 – 0.45 | not measured for every seed in the published audit table |
| `calibration_pass_fraction` | 0.75 – 1.0 | not measured in the published audit table |
| `realism_evidence_coverage_fraction` | 0.65 – 1.0 | not measured in the published audit table |
| `applicable_realism_pass_fraction` | 0.75 – 1.0 | not measured in the published audit table |
| `biome_class_count` | ≥ 6 | `cryogenic_slushball` reports no forest and no desert land; count not published |

`--profile generic` skips this block entirely (`src/magic_geo/geo_validation.py:2728-2729`) and keeps only the contract, replay, conservation, and evidence-backed realism checks. The gallery states plainly that the `earthlike` profile is intentionally inappropriate for most gallery presets (`docs/example_seed_gallery.md:165-166`).

---

## continental_realm

**Design intent.** A temperate, land-rich campaign world: broad continents, inland basins, mountain corridors, and navigable coasts, suitable for epic-fantasy or long-campaign geography (`configs/seeds/continental_realm.yaml:1-3`; `docs/example_seed_gallery.md:44`).

**Regime explored.** Earth-like energy balance with a *water-poor* hydrosphere. It is also the catalog's only demonstration of the alternative tessellation: `geodesic_icosahedron` rather than `fibonacci_sphere`. `tests/test_config.py:90-93` asserts the catalog spans both mesh backends, and this seed is the reason.

| Property | Value | vs. `earthlike_seed` | Why it creates the regime |
| --- | --- | --- | --- |
| `mesh.backend` | `geodesic_icosahedron` | `fibonacci_sphere` | Triangle-derived stencil instead of a k-nearest Fibonacci stencil (`cpp/src/engine/mesh.cpp:890`) |
| `mesh.cell_count` | 2562 | 4096 | Exactly realizable at frequency 16 (`10·16²+2`), so no silent rounding (`mesh.cpp:840`) |
| `planet.ocean_water_inventory_km3` | 850,000,000 | 1,338,000,000 | ~64% of the Earth-like inventory; the flood solve reaches a lower sea level, leaving more continent above water (`cpp/src/engine/ocean.cpp:29`) |
| `planet.ocean_fraction_target` | 0.58 | 0.70 | Diagnostic only; realized 0.340 |
| `tectonics.plate_count` | 12 | 14 | Fewer, broader domains → larger coherent landmasses |
| `tectonics.continental_plate_fraction` | 0.58 | 0.38 | 58% of plate seeds get a continental bias (`cpp/src/engine/tectonics.cpp:23-26`) |
| `tectonics.continental_crust_fraction_target` | 0.52 | 0.34 | Half the surface area targeted as continental crust |
| `tectonics.boundary_smoothing_steps` | 7 | 5 | Smoother, less fragmented plate outlines → cleaner natural frontiers |
| `tectonics.plate_motion_scale_deg_per_step` | 3.0 | 4.0 | Slightly calmer transport than the reference |
| `climate.base_temperature_c` | 14.0 | 15.0 | With `L = G = p = 1.0`, all three forcings are exactly zero, so the anchor is 14.0 °C |
| `climate.precipitation_scale` | 1.0 | 0.8 | Schema-default rainfall; combined gain 1.038 |
| `hydrology.river_percentile` | 0.90 | 0.92 | Lower threshold → more cells classified as rivers → more navigable water (`cpp/src/engine/hydrology.cpp:712`) |
| `erosion.tectonic_uplift_scale` | 1.0 | 0.85 | Preserves mountain passes and relief for route-finding |

**Expected outcomes.** 2,562 cells, ocean fraction 0.340, global mean 14.0 °C, 932 mm/y land precipitation, 6 landmasses, 33.0% forest land, 19.0 °C seasonal land range. Generic validation: 14/14 layer contracts, 0 warnings — the cleanest result in the catalog alongside `verdant_hothouse`, `solstice_extreme`, and `ironroot_super_earth` (`docs/example_seed_gallery.md:65`). What to inspect: major watersheds, inland basins, mountain passes, long routes, ports, and natural frontiers (`docs/example_seed_gallery.md:44`).

**Known limitations.** Realized ocean fraction (0.340) is far from the declared target (0.58) — the target does not steer the solve. Because this is the only geodesic seed, a `--cells` override is honored exactly only when it is already of the form `10·F²+2`; anything else rounds up, so requesting 512 yields 642 cells. `mesh.neighbor_count: 7` is present for schema completeness but does not tune the geodesic stencil (`docs/example_seed_gallery.md:143-145`).

```bash
magic-geo generate \
  --config configs/seeds/continental_realm.yaml \
  --output runs/continental_realm/world.json \
  --summary runs/continental_realm/summary.md
```

---

## glasswind_desert

**Design intent.** A hot desert world with **no standing ocean at all**. The file's own header states this is the closest the current schema can get to the familiar water-scarcity planet archetype, and that it does not model twin stars, sand seas, or subsurface water reserves (`configs/seeds/glasswind_desert.yaml:1-3`).

**Regime explored.** Total hydrological scarcity as a *structural* condition rather than a tuned one: with `ocean_water_inventory_km3: 0.0`, `apply_sea_level` takes the zero-inventory branch and no cell is water (`cpp/src/engine/ocean.cpp:30-45`).

| Property | Value | vs. `earthlike_seed` | Why it creates the regime |
| --- | --- | --- | --- |
| `planet.ocean_water_inventory_km3` | **0.0** | 1,338,000,000 | Triggers the explicit zero-ocean datum branch; every cell becomes land (`cpp/src/engine/ocean.cpp:30-45`) |
| `planet.ocean_fraction_target` | 0.0 | 0.70 | Kept consistent with the inventory so the diagnostic comparison is meaningful |
| `climate.precipitation_scale` | **0.08** | 0.8 | A 10× cut on the Earth-like reference (12.5× below the schema default of 1.0); drives the combined precipitation gain to 0.162, the lowest in the catalog |
| `climate.subtropical_drying_strength` | **0.88** | 0.65 | Near the schema ceiling of 0.9 (`config.py:346`); the drying factor floors at 0.25 (`constants.hpp:9`), so subtropical belts lose up to 75% of rainfall |
| `climate.base_temperature_c` | 32.0 | 15.0 | With `L=1.10`, `G=1.05`, `p=0.70`, the anchor lands at 31.86 °C |
| `climate.lapse_rate_c_per_km` | 7.5 | 6.5 | Steeper lapse → sharper highland/lowland thermal contrast |
| `planet.atmosphere_pressure_bar` | 0.70 | 1.0 | Thin air: −1.605 °C pressure term and a 0.883 pressure precipitation factor |
| `planet.gravity_g` | 0.82 | 1.0 | Relief scale 1.104 — slightly exaggerated topography |
| `planet.internal_heat` | 0.75 | 1.0 | Tectonic activity 0.672; a quiet, old crust |
| `planet.geological_age_ga` | 5.6 | 4.5 | Older than Earth; further damps activity |
| `tectonics.plate_count` | **8** | 14 | "Eight broad domains retain active transport and pass full replay at the declared resolution without changing the desert climate premise" (`configs/seeds/glasswind_desert.yaml:28-30`) |
| `tectonics.continental_crust_fraction_target` | 0.72 | 0.34 | An almost entirely continental surface, consistent with no ocean basins |
| `hydrology.river_percentile` | **0.97** | 0.92 | Highest in the catalog; only the very top of the flow-accumulation distribution can register as river |
| `erosion.iterations` | 4 | 6 | Fewer maturation transitions; a landscape that is not deeply reworked |
| `erosion.stream_power_coefficient` | 3.0 | 7.5 | Weak fluvial incision — there is little water to incise with |
| `erosion.hillslope_diffusion` | 0.025 | 0.055 | Minimal hillslope smoothing; sharp, unrelaxed relief |

**Expected outcomes.** 2,048 cells, ocean fraction 0.000, global mean 31.9 °C, 94 mm/y land precipitation, 87.5% desert land, **no rivers**, one landmass. Generic validation: 14/14 layer contracts, 2 warnings (`docs/example_seed_gallery.md:66`). What to inspect: desert coverage, dry basins, rare water nodes, sparse settlement, and route dependence (`docs/example_seed_gallery.md:45`).

**Known limitations.** The desert example has **one star** in the current energy model and **no explicit deep-aquifer inventory** (`docs/example_seed_gallery.md:150`). The plate count is a knife edge: schema validity is weaker than simulation validity — the exact desert preset passes with eight plates, but nearby plate counts and seeds can fail current crust-transport replay (`docs/example_seed_gallery.md:81-84`). Re-run generic validation after changing this control. The absence of rivers means every river/lake-derived downstream layer is exercised in its empty-population path, which the validator treats as `not_applicable`, never as a successful realism observation.

```bash
magic-geo generate \
  --config configs/seeds/glasswind_desert.yaml \
  --output runs/glasswind_desert/world.json \
  --summary runs/glasswind_desert/summary.md
```

---

## pelagic_archipelago

**Design intent.** A stormy maritime and island world. A large ocean inventory, low continental-crust target, many plates, and strong rainfall favor scattered highlands, maritime routes, island ports, reefs, and short river systems (`configs/seeds/pelagic_archipelago.yaml:1-3`).

**Regime explored.** Land as the exception. The audited world puts **10 landmasses inside just 8.4% land area** — a fragmentation regime rather than a continental one.

| Property | Value | vs. `earthlike_seed` | Why it creates the regime |
| --- | --- | --- | --- |
| `planet.ocean_water_inventory_km3` | 2,500,000,000 | 1,338,000,000 | ~1.9× Earth-like water on a slightly smaller planet; the flood solve reaches a much higher sea level |
| `planet.radius_km` | 6200.0 | 6371.0 | Slightly smaller surface for that inventory to cover |
| `tectonics.continental_crust_fraction_target` | **0.18** | 0.34 | Lowest in the catalog; `tests/test_config.py:147-153` asserts the catalog minimum is ≤ 0.20 |
| `tectonics.plate_count` | 24 | 14 | Many small domains → many separate highland cores |
| `tectonics.boundary_smoothing_steps` | 3 | 5 | Deliberately ragged boundaries → complex coastlines, straits, and bays |
| `tectonics.max_angular_speed` | 1.15 | 0.95 | Above the Earth-like ceiling; more boundary activity per step |
| `tectonics.plate_motion_scale_deg_per_step` | 4.0 | 4.0 | Matches the Earth-like reference rate |
| `tectonics.oceanic_crust_aging_ma_per_step` | 6.0 | 5.0 | Faster quiet-crust ageing on a mostly oceanic surface |
| `climate.precipitation_scale` | 1.40 | 0.8 | Storm-belt rainfall; combined gain 1.933 |
| `climate.subtropical_drying_strength` | 0.45 | 0.65 | Weak dry belts — few permanent deserts on an ocean world |
| `planet.atmosphere_pressure_bar` | 1.25 | 1.0 | +1.004 °C and a 1.081 precipitation factor |
| `planet.day_length_hours` | 20.0 | 24.0 | Fast rotation: band shift −0.83°, rotation wind factor 1.20 (`cpp/src/engine/climate.cpp:29,266`) |
| `planet.internal_heat` / `geological_age_ga` | 1.20 / 3.6 | 1.0 / 4.5 | Tectonic activity 1.342 — a young, active ocean floor |
| `hydrology.river_percentile` | 0.88 | 0.92 | Low threshold so that short island drainages still register |
| `erosion.stream_power_coefficient` | 9.0 | 7.5 | Vigorous incision under high rainfall |
| `erosion.slope_exponent` | 1.1 | 1.0 | Steeper slopes erode disproportionately — island relief is quickly cut |
| `erosion.tectonic_uplift_scale` | 1.15 | 0.85 | Keeps arcs and islands emergent against that erosion |

**Expected outcomes.** 2,048 cells, ocean fraction 0.916, global mean 20.1 °C, 3,317 mm/y land precipitation, 10 landmasses in 8.4% land area. Generic validation: 14/14 layer contracts, 1 warning (`docs/example_seed_gallery.md:67`). What to inspect: island count, protected bays, straits, reefs, short rivers, ports, and maritime routes (`docs/example_seed_gallery.md:46`).

**Known limitations.** Island counts, narrow straits, and even the realized ocean fraction are strongly resolution sensitive — a 512-cell preview will not have the same island inventory as the 2,048-cell run (`docs/example_seed_gallery.md:162-164`). At 0.916 ocean fraction this seed sits just outside the `earthlike` profile band of 0.55–0.85, so `--profile earthlike` is the wrong gate.

```bash
magic-geo generate \
  --config configs/seeds/pelagic_archipelago.yaml \
  --output runs/pelagic_archipelago/world.json \
  --summary runs/pelagic_archipelago/summary.md
```

---

## cryogenic_slushball

**Design intent.** An ice-dominated survival setting built on the snowball/slushball climate archetype. The file header is explicit that reduced stellar forcing and greenhouse trapping are the primary controls, and that **liquid refugia are possible and should be inspected after generation** (`configs/seeds/cryogenic_slushball.yaml:1-3`).

**Regime explored.** Cold as an energy-balance outcome, not a temperature override. Every one of the three temperature terms is pushed negative simultaneously.

| Property | Value | vs. `earthlike_seed` | Why it creates the regime |
| --- | --- | --- | --- |
| `planet.stellar_luminosity` | **0.55** | 1.0 | −5.275 °C via `38·(0.55^0.25 − 1)`; `tests/test_config.py:100` asserts < 0.60 |
| `planet.greenhouse_factor` | **0.50** | 1.0 | −5.50 °C via `11·(0.50 − 1)` |
| `planet.atmosphere_pressure_bar` | 0.90 | 1.0 | −0.474 °C |
| `climate.base_temperature_c` | **−10.0** | 15.0 | `tests/test_config.py:101` asserts ≤ −10.0; total anchor −21.25 °C |
| `climate.precipitation_scale` | 0.60 | 0.8 | Combined gain 0.219 — the moisture capacity factor is pinned at its 0.35 floor (`constants.hpp:21`), an intentional cold-world limiter |
| `climate.subtropical_drying_strength` | 0.45 | 0.65 | Weak dry belts; aridity here is thermal, not circulatory |
| `planet.axial_tilt_deg` | 12.0 | 23.5 | Season multiplier 0.520 — mild seasonality, so ice does not seasonally collapse |
| `planet.orbital_eccentricity` | 0.01 | 0.016 | Near-circular orbit; no eccentricity-driven relief from the cold |
| `planet.ocean_water_inventory_km3` | 1,450,000,000 | 1,338,000,000 | Slightly *more* water than Earth-like — the premise is frozen water, not absent water |
| `tectonics.plate_count` | 12 | 14 | Modest fragmentation |
| `erosion.iterations` | 5 | 6 | Fewer transitions on a landscape where fluvial work is limited |
| `erosion.stream_power_coefficient` | 4.5 | 7.5 | Weak incision under low liquid throughput |
| `erosion.hillslope_diffusion` | 0.040 | 0.055 | Reduced hillslope relaxation |
| `erosion.tectonic_uplift_scale` | 0.75 | 0.85 | Slightly subdued uplift |

**Expected outcomes.** 2,048 cells, ocean fraction 0.616, global mean −21.2 °C, 268 mm/y land precipitation, 24.4% ice cells, **no forest and no desert land**. Generic validation: 14/14 layer contracts, 2 warnings (`docs/example_seed_gallery.md:68`). What to inspect: ice extent, liquid refugia, tundra, glacial landforms, meltwater, and cold-water ports (`docs/example_seed_gallery.md:47`).

**Known limitations.** The gallery deliberately keeps this example more nuanced than its name: NASA climate studies describe partially open-ocean "slushball" outcomes, and the preset is written to allow refugia rather than force a hard snowball (`docs/example_seed_gallery.md:122-127`). The moisture capacity factor is clamped at its floor, so pushing the world colder will not reduce precipitation further through that channel. With no forest and no desert land, biome-class diversity is low; the `earthlike` profile requires ≥ 6 biome classes (`src/magic_geo/geo_validation.py:791-800`) and is not an appropriate gate here.

```bash
magic-geo generate \
  --config configs/seeds/cryogenic_slushball.yaml \
  --output runs/cryogenic_slushball/world.json \
  --summary runs/cryogenic_slushball/summary.md
```

---

## young_volcanic

**Design intent.** A small, young, geologically violent frontier world. The file header states plainly that internal heat, dense plate boundaries, fast procedural motion, and uplift **proxy** volcanic and high-relief terrain, and that the generator does not currently simulate exposed lava (`configs/seeds/young_volcanic.yaml:1-3`).

**Regime explored.** Maximum tectonic forcing. `internal_heat: 2.50` with `geological_age_ga: 0.80` gives a raw activity index of 5.93, which the engine **clamps to the ceiling of 2.25** (`cpp/src/engine/tectonics.cpp:19`). This is the only seed that saturates that clamp.

| Property | Value | vs. `earthlike_seed` | Why it creates the regime |
| --- | --- | --- | --- |
| `planet.internal_heat` | **2.50** | 1.0 | `tests/test_config.py:119` asserts ≥ 2.0; drives activity to the 2.25 ceiling |
| `planet.geological_age_ga` | **0.80** | 4.5 | `tests/test_config.py:118` asserts ≤ 1.0; the `sqrt(4.5/age)` term amplifies activity further |
| `planet.radius_km` | 4800.0 | 6371.0 | Smallest planet in the catalog; boundaries are dense per unit area |
| `planet.gravity_g` | 0.75 | 1.0 | Relief scale 1.155 — the highest topographic amplification in the catalog |
| `planet.orbital_eccentricity` | **0.12** | 0.016 | Catalog maximum; `tests/test_config.py:139-142` asserts ≥ 0.10 |
| `tectonics.plate_count` | **28** | 14 | Catalog maximum; a dense boundary network |
| `tectonics.min_angular_speed` | **0.30** | 0.03 | 10× the Earth-like floor — even the slowest plate is moving |
| `tectonics.max_angular_speed` | **1.80** | 0.95 | Catalog maximum |
| `tectonics.boundary_smoothing_steps` | **2** | 5 | Catalog minimum (`tests/test_config.py:161-164` asserts ≤ 2); raw, jagged boundaries |
| `tectonics.plate_motion_scale_deg_per_step` | 4.5 | 4.0 | Fast procedural transport |
| `tectonics.oceanic_crust_aging_ma_per_step` | 8.0 | 5.0 | Catalog maximum |
| `planet.ocean_water_inventory_km3` | 200,000,000 | 1,338,000,000 | Scarce water on a small planet; realized ocean fraction 0.240 |
| `planet.greenhouse_factor` / `stellar_luminosity` | 1.50 / 1.35 | 1.0 / 1.0 | +5.50 °C and +2.96 °C; anchor 41.97 °C |
| `climate.precipitation_scale` | 0.50 | 0.8 | Hot but not wet — the moisture factor is already at its 2.25 ceiling |
| `erosion.iterations` | **6** | 6 | Six *refined* steps retain an active surface while staying inside the engine's finite dry-rock accounting envelope at the declared resolution (`configs/seeds/young_volcanic.yaml:49-51`) |
| `erosion.maturation_timestep_ma` | **2.5** | 5.0 | Refined timestep: half the reference interval per transition |
| `erosion.tectonic_uplift_scale` | **2.00** | 0.85 | Catalog maximum (`tests/test_config.py:193-196` asserts ≥ 2.0) |
| `erosion.slope_exponent` | 1.2 | 1.0 | Steep terrain erodes hardest, sharpening arcs |

**Expected outcomes.** 2,048 cells, ocean fraction 0.240, global mean 42.0 °C, 1,174 mm/y land precipitation, 326 volcanic-arc cells, 286 high-seismic-hazard cells, 7 landmasses. Generic validation: 14/14 layer contracts, 2 warnings (`docs/example_seed_gallery.md:69`). What to inspect: boundary density, relief, volcanic proxies, arc resources, hazards, and constrained routes (`docs/example_seed_gallery.md:48`).

**Known limitations.** The volcanic example uses heat, motion, uplift, and resource **proxies**; it does not simulate exposed lava (`docs/example_seed_gallery.md:148-150`). Its erosion iteration count is a hard boundary, not a preference: the volcanic preset passes at six refined maturation steps; **seven generates but fails a material-shadow replay, and eight exceeds the current accounting envelope** (`docs/example_seed_gallery.md:84-86`). `tests/test_config.py:120` pins `iterations == 6` for exactly this reason. The tectonic activity index is clamped at 2.25, so raising `internal_heat` above the current value changes nothing through that channel.

```bash
magic-geo generate \
  --config configs/seeds/young_volcanic.yaml \
  --output runs/young_volcanic/world.json \
  --summary runs/young_volcanic/summary.md
```

---

## verdant_hothouse

**Design intent.** A hot, wet jungle, wetland, and river world. Strong greenhouse forcing, a dense atmosphere, abundant ocean water, and weak subtropical drying encourage broad humid biomes, wetlands, large rivers, and vigorous erosion (`configs/seeds/verdant_hothouse.yaml:1-3`).

**Regime explored.** Maximum hydrological throughput. The combined configuration-level precipitation gain is **5.348**, more than six times the Earth-like reference (0.864) and 33× the desert preset.

| Property | Value | vs. `earthlike_seed` | Why it creates the regime |
| --- | --- | --- | --- |
| `climate.precipitation_scale` | **1.80** | 0.8 | `tests/test_config.py:102` asserts > 1.5; the single largest contributor to the gain |
| `planet.greenhouse_factor` | **1.55** | 1.0 | `tests/test_config.py:103` asserts > 1.4; +6.05 °C, the largest greenhouse term in the catalog |
| `planet.atmosphere_pressure_bar` | 1.80 | 1.0 | +2.645 °C and a 1.228 precipitation factor |
| `planet.stellar_luminosity` | 1.25 | 1.0 | +2.180 °C; total anchor 40.88 °C, which saturates the moisture factor at its 2.25 ceiling |
| `climate.subtropical_drying_strength` | **0.30** | 0.65 | Weakest drying in the catalog — the dry-belt suppression that creates deserts is largely switched off |
| `climate.lapse_rate_c_per_km` | **5.5** | 6.5 | Catalog minimum; `tests/test_config.py:176-180` asserts the catalog lapse spread is ≥ 2.0 |
| `hydrology.preserve_geologic_depressions` | **false** | true | The **only** seed that fills closed basins, deliberately, "to favor connected through-drainage" (`configs/seeds/verdant_hothouse.yaml:46-47`); asserted at `tests/test_config.py:104` |
| `hydrology.river_percentile` | **0.86** | 0.92 | Catalog minimum (`tests/test_config.py:181-184`); the most permissive river classification |
| `planet.ocean_water_inventory_km3` | 1,600,000,000 | 1,338,000,000 | Abundant water on a 6,800 km planet |
| `planet.axial_tilt_deg` | 12.0 | 23.5 | Season multiplier 0.520 — a perennially wet world, not a monsoonal one |
| `erosion.iterations` | 7 | 6 | An extra maturation transition to work the landscape |
| `erosion.maturation_timestep_ma` | 4.0 | 5.0 | Slightly refined interval |
| `erosion.stream_power_coefficient` | **11.0** | 7.5 | Catalog maximum; extreme fluvial incision under extreme rainfall |
| `erosion.hillslope_diffusion` | 0.085 | 0.055 | High diffusion — rounded, deeply weathered slopes |
| `erosion.tectonic_uplift_scale` | 1.10 | 0.85 | Enough uplift to keep relief against that incision |

**Expected outcomes.** 2,048 cells, ocean fraction 0.655, global mean 40.9 °C, **7,338 mm/y land precipitation**, 81.0% forest land, **no desert land**, 4.9% river cells. Generic validation: 14/14 layer contracts, 0 warnings (`docs/example_seed_gallery.md:70`). What to inspect: forest and wetland coverage, connected drainage, large rivers, floodplains, and river ports (`docs/example_seed_gallery.md:49`).

**Known limitations.** The moisture capacity factor is already saturated at its 2.25 ceiling, so raising `base_temperature_c` or `greenhouse_factor` further will not increase precipitation through that channel — only `precipitation_scale`, pressure, and gravity still move it. `preserve_geologic_depressions: false` removes geologic closed basins by design, so this seed is a poor choice if endorheic basins matter to your setting. Its 4.9% river-cell fraction sits inside the `earthlike` band (0.002–0.08) but its 40.9 °C mean and 7,338 mm/y precipitation are far outside; use `--profile generic`.

```bash
magic-geo generate \
  --config configs/seeds/verdant_hothouse.yaml \
  --output runs/verdant_hothouse/world.json \
  --summary runs/verdant_hothouse/summary.md
```

---

## solstice_extreme

**Design intent.** A severe but *regular* seasonal world. The file header names the 75-degree axial tilt as the defining control and states that this is **not** a model of irregular or multi-year fantasy seasons, because the engine always uses twelve months (`configs/seeds/solstice_extreme.yaml:1-3`).

**Regime explored.** Seasonality as the dominant deliberate variable. The energy-balance parameters are near Earth-like — radius 6371 km, gravity 1.0, luminosity 0.98, greenhouse 1.0 — so the anchor stays close to the reference while the seasonal amplitude term is multiplied by 3.651. The audited 43.7 °C seasonal land-temperature range is not attributable to obliquity and eccentricity alone: this seed also runs a 30-hour day, 1.10 bar, a 12.0 °C base temperature, and a more continental plate mix, and the continentality term multiplies the same seasonal amplitude (`cpp/src/engine/climate.cpp:403`). The isolation is a design intent, not a measured attribution.

| Property | Value | vs. `earthlike_seed` | Why it creates the regime |
| --- | --- | --- | --- |
| `planet.axial_tilt_deg` | **75.0** | 23.5 | `tests/test_config.py:111` asserts ≥ 70.0. Seasonal amplitude scales linearly as `tilt/23.5 = 3.191` (`cpp/src/engine/climate.cpp:403-404`) |
| `planet.orbital_eccentricity` | 0.08 | 0.016 | `1 + 1.8·0.08 = 1.144` multiplies the seasonal amplitude again → total season multiplier **3.651** (`climate.cpp:267`) |
| `planet.day_length_hours` | 30.0 | 24.0 | Band shift +1.25°: the subtropical and mid-latitude precipitation bands migrate poleward (`climate.cpp:266`) |
| `planet.ocean_water_inventory_km3` | 1,100,000,000 | 1,338,000,000 | "This volume closes exactly in the connected-ocean solve at 2,048 cells" (`configs/seeds/solstice_extreme.yaml:18`); asserted at `tests/test_config.py:122-125` |
| `planet.radius_km` / `gravity_g` / `geological_age_ga` | 6371.0 / 1.0 / 4.5 | identical | Deliberately Earth-like so obliquity is the isolated variable |
| `planet.stellar_luminosity` / `greenhouse_factor` | 0.98 / 1.0 | 1.0 / 1.0 | Near-zero forcing; anchor 12.24 °C |
| `climate.base_temperature_c` | 12.0 | 15.0 | Slightly cool so that seasonal swings cross freezing in both directions |
| `tectonics.*` | 14 plates, 0.44/0.40 crust, 3.0 deg/step | 14 plates, 0.38/0.34, 4.0 | Mildly more continental than Earth-like; continents amplify seasonality via the continentality term (`climate.cpp:403`) |
| `erosion.*` | Earth-like except uplift 0.90 | uplift 0.85 | Kept near-reference so the seasonal signal is not confounded |

**Expected outcomes.** 2,048 cells, ocean fraction 0.468, global mean 12.2 °C, 1,071 mm/y land precipitation, **43.7 °C mean seasonal land-temperature range**. Generic validation: 14/14 layer contracts, 0 warnings (`docs/example_seed_gallery.md:71`). What to inspect: monthly temperature range, shifting ice, seasonal water stress, and biome ecotones (`docs/example_seed_gallery.md:50`).

**Known limitations.** The seasonal example **always has twelve months and cannot reproduce irregular multi-year seasons** (`docs/example_seed_gallery.md:148-150`; `climate.months` is `Literal[12]` at `config.py:324`). The ocean inventory is one of the three values the gallery flags as sitting on a solvable connectivity interval: several superficially similar volumes generated a world but failed ocean-inventory closure (`docs/example_seed_gallery.md:77-80`). Changing `ocean_water_inventory_km3` or `mesh.cell_count` here requires re-running generic validation. Note also that the seasonal amplitude term uses `tilt/23.5` unclamped, while the related `axial_wind_factor` is clamped to `[0.12, 2.4]` (`climate.cpp:395`) — the wind response saturates before the temperature response does.

```bash
magic-geo generate \
  --config configs/seeds/solstice_extreme.yaml \
  --output runs/solstice_extreme/world.json \
  --summary runs/solstice_extreme/summary.md
```

---

## ironroot_super_earth

**Design intent.** A high-gravity super-Earth campaign world. The file header states that radius, gravity, ocean inventory, and atmospheric pressure are scaled together, and that exotic planets are supported by the schema but are **less calibrated than the Earth reference** (`configs/seeds/ironroot_super_earth.yaml:1-3`).

**Regime explored.** Planetary scaling. This is the catalog's test of whether areas, distances, relief, and transport respond coherently when the planet itself is much larger and heavier.

| Property | Value | vs. `earthlike_seed` | Why it creates the regime |
| --- | --- | --- | --- |
| `planet.radius_km` | **9500.0** | 6371.0 | `tests/test_config.py:113` asserts ≥ 9,000; surface area scales as `r²`, so ≈ 2.22× Earth-like |
| `planet.gravity_g` | **1.60** | 1.0 | `tests/test_config.py:112` asserts ≥ 1.5. Relief scale `1/sqrt(1.6) = 0.791` — topography is actively suppressed (`cpp/src/engine/tectonics.cpp:294`). Gravity precipitation factor 1.020 (`climate.cpp:259`) |
| `planet.ocean_water_inventory_km3` | **3,020,000,000** | 1,338,000,000 | The nearby 3.02e9 value lies on a solvable connected-ocean interval at the declared mesh; the simple Earth-area scaling fell inside a connectivity jump (`configs/seeds/ironroot_super_earth.yaml:18-19`). Pinned exactly at `tests/test_config.py:114-117` |
| `planet.atmosphere_pressure_bar` | 1.80 | 1.0 | Dense atmosphere on a high-gravity body: +2.645 °C, precipitation factor 1.228 |
| `mesh.neighbor_count` | **8** | 7 | The **only** seed that departs from 7; `tests/test_config.py:143-146` asserts the catalog set is exactly `{7, 8}`. A wider process stencil on a larger sphere |
| `tectonics.plate_count` | 20 | 14 | More plates for a much larger surface |
| `tectonics.plate_motion_scale_deg_per_step` | 2.5 | 4.0 | A degree of arc is a far longer distance here, so the angular rate is reduced |
| `planet.internal_heat` / `geological_age_ga` | 1.30 / 5.0 | 1.0 / 4.5 | Tectonic activity 1.233 — a large body retaining heat while being older than Earth |
| `climate.base_temperature_c` | 14.0 | 15.0 | Anchor 17.20 °C once pressure and greenhouse are added |
| `climate.precipitation_scale` | 1.10 | 0.8 | Combined gain 1.354 |
| `erosion.hillslope_diffusion` | 0.050 | 0.055 | Slightly reduced diffusion against already-suppressed relief |
| `erosion.tectonic_uplift_scale` | 1.00 | 0.85 | Extra uplift to offset the 0.791 gravity relief scale |

**Expected outcomes.** 2,048 cells, ocean fraction 0.578, global mean 17.2 °C (equal to the derived anchor at the precision the audit reports; see the caveat under the diagnostics table), 1,612 mm/y land precipitation, 10 landmasses, 42.0% forest land. Generic validation: 14/14 layer contracts, 0 warnings (`docs/example_seed_gallery.md:72`). What to inspect: area and distance scaling, relief response, transport distances, hydrology, and high-gravity diagnostics (`docs/example_seed_gallery.md:51`).

**Known limitations.** Non-Earth planets are schema-valid but only lightly calibrated: the schema permits extreme planets and planet-scaling tests confirm the knobs move outputs, but the geo-validation target bands are Earth-tuned, so exotic configs are **not asserted physically plausible** (`docs/configuration_reference.md:333-336`; `docs/example_seed_gallery.md:146-147`). At 2,048 cells on a 9,500 km radius, each control volume covers roughly 2.2× the area of an Earth-radius cell at the same count — spatial resolution per km² is correspondingly coarser than the other seeds. The ocean inventory is one of the three flagged connectivity-sensitive values; changing it or the mesh requires re-validation (`docs/example_seed_gallery.md:77-80`).

```bash
magic-geo generate \
  --config configs/seeds/ironroot_super_earth.yaml \
  --output runs/ironroot_super_earth/world.json \
  --summary runs/ironroot_super_earth/summary.md
```

---

## oldstone_stagnant

**Design intent.** An ancient, tectonically stagnant world. Zero procedural plate motion, weak internal heat, broad continental crust, and a longer refined erosion run favor worn relief, old interiors, closed basins, and sparse young mountains (`configs/seeds/oldstone_stagnant.yaml:1-3`).

**Regime explored.** The tectonic null case. This is the only seed that sets **all four motion controls to exactly zero** — `min_angular_speed`, `max_angular_speed`, `plate_motion_scale_deg_per_step`, and `oceanic_crust_aging_ma_per_step` — plus `tectonic_uplift_scale: 0.0`. Erosion runs without any competing uplift.

| Property | Value | vs. `earthlike_seed` | Why it creates the regime |
| --- | --- | --- | --- |
| `tectonics.min_angular_speed` | **0.0** | 0.03 | No plate rotates |
| `tectonics.max_angular_speed` | **0.0** | 0.95 | Pinned at `tests/test_config.py:130` |
| `tectonics.plate_motion_scale_deg_per_step` | **0.0** | 4.0 | Pinned at `tests/test_config.py:131-134`; no procedural transport |
| `tectonics.oceanic_crust_aging_ma_per_step` | **0.0** | 5.0 | Catalog minimum, asserted exactly 0.0 at `tests/test_config.py:169-175` |
| `erosion.tectonic_uplift_scale` | **0.0** | 0.85 | Catalog minimum, asserted exactly 0.0 at `tests/test_config.py:189-192`. Erosion is unopposed |
| `planet.internal_heat` | **0.10** | 1.0 | Raw activity `0.10·sqrt(4.5/9.5) = 0.069`, **clamped up to the 0.25 floor** (`cpp/src/engine/tectonics.cpp:19`) |
| `planet.geological_age_ga` | **9.50** | 4.5 | More than twice Earth's age; caps crust age and geologic maturity (`config.py:227`) |
| `tectonics.plate_count` | **6** | 14 | Catalog minimum; a few enormous, immobile domains |
| `tectonics.continental_crust_fraction_target` | **0.65** | 0.34 | `tests/test_config.py:154-160` asserts the catalog maximum is ≥ 0.65 |
| `tectonics.boundary_smoothing_steps` | **12** | 5 | Catalog maximum (`tests/test_config.py:165-168` asserts ≥ 12); maximally relaxed boundary outlines |
| `planet.ocean_water_inventory_km3` | 430,000,000 | 1,338,000,000 | "The lower inventory closes exactly in this worn, land-heavy basin geometry" (`configs/seeds/oldstone_stagnant.yaml:18`); pinned at `tests/test_config.py:126-129` |
| `planet.day_length_hours` | **36.0** | 24.0 | Catalog maximum; band shift +2.50°, rotation wind factor 0.667 — sluggish circulation |
| `planet.axial_tilt_deg` | 8.0 | 23.5 | Season multiplier 0.353, the lowest in the catalog |
| `climate.precipitation_scale` | 0.65 | 0.8 | Combined gain 0.446 |
| `climate.subtropical_drying_strength` | 0.72 | 0.65 | Strong dry belts on a land-heavy world |
| `erosion.iterations` | **10** | 6 | Catalog maximum; the longest maturation run |
| `erosion.maturation_timestep_ma` | 3.0 | 5.0 | Refined interval — 10 steps of 3.0 Ma rather than 6 of 5.0 |
| `erosion.hillslope_diffusion` | **0.100** | 0.055 | Catalog maximum; heavy hillslope relaxation, the signature of worn terrain |
| `erosion.stream_power_coefficient` | 9.0 | 7.5 | Strong incision, with nothing rebuilding the relief |

**Expected outcomes.** 2,048 cells, ocean fraction 0.257, global mean 4.4 °C, 358 mm/y land precipitation, 40.3% desert land, 10.4% ice cells, zero configured plate motion. Generic validation: 14/14 layer contracts, 2 warnings (`docs/example_seed_gallery.md:73`). What to inspect: worn relief, mature drainage, closed basins, old interiors, sedimentary resources, and sparse young mountains (`docs/example_seed_gallery.md:52`).

**Known limitations.** The tectonic activity index is clamped **up** to 0.25, so this world is not fully inert even at `internal_heat: 0.10` — the floor is a numerical guard, not a physical claim. The ocean inventory is the third of the three connectivity-sensitive values the gallery flags (`docs/example_seed_gallery.md:77-80`). `tectonics` and `erosion.maturation_timestep_ma` are procedural controls with nominal time labels, **not calibrated plate velocities or geological clocks** (`docs/example_seed_gallery.md:138-139`), so "9.5 Ga of stagnation" is a narrative label on a procedural configuration, not a simulated duration.

```bash
magic-geo generate \
  --config configs/seeds/oldstone_stagnant.yaml \
  --output runs/oldstone_stagnant/world.json \
  --summary runs/oldstone_stagnant/summary.md
```

---

## earthlike_seed (the reference configuration)

**Design intent.** The canonical Earth reference and the default base config for the geo validation suite. `configs/earthlike_seed.yaml` is a materialized copy of the code-registered `earthlike` profile: it equals `WorldConfig()` schema defaults plus exactly the two profile deltas.

| Property | Value | Schema default | Note |
| --- | --- | --- | --- |
| `tectonics.plate_motion_scale_deg_per_step` | **4.0** | 2.0 | The `earthlike` profile delta (`config.py:513-518`) |
| `climate.precipitation_scale` | **0.8** | 1.0 | The `earthlike` profile delta |
| every other field | schema default | schema default | Including `mesh.cell_count: 4096`, `tectonics.plate_count: 14`, `run.seed: 424242`, `compute.backend: auto`, `compute.threads: 0` |

`tests/test_config.py:238-240` pins `run.seed == 424242`, `mesh.backend == "fibonacci_sphere"`, and `mesh.cell_count == 4096`, and `tests/test_config.py:265` asserts `load_config(Path("configs/earthlike_seed.yaml")) == create_config("earthlike")` — the file and the profile are the same document.

**Regime explored.** Earth-like energy balance and hydrosphere at 4,096 cells. It is the only shipped file where the `earthlike` validation profile is the intended gate rather than the wrong one.

**Where it is used by default.**

| Consumer | Default | Source |
| --- | --- | --- |
| `magic-geo validate-geo-suite --config` | `configs/earthlike_seed.yaml` | `src/magic_geo/cli/commands/validate_geo.py:96` |
| `magic-geo init-config --profile` | `earthlike` (writes the same values to `magic-geo.yaml`) | `src/magic_geo/cli/commands/config.py:21-28` |

**Expected outcomes.** Not included in the nine-seed declared-resolution audit table, which covers only `configs/seeds/*.yaml`. Its behavior is instead exercised by the geo validation suite; see [Geo Validation Suite](./13-geo-validation-suite.md).

**Known limitations.** Unlike the nine gallery seeds it does **not** pin `compute.backend: cpu` / `compute.threads: 1`, so a run of this file on a multi-core host is subject to the documented thread-count determinism regression (`docs/configuration_reference.md:328-332`). Earth empirical fit remains a separate calibration verdict from internal contract integrity (`src/magic_geo/geo_validation.py:40`), so passing `--profile earthlike` is not a claim that the generated world reproduces Earth.

```bash
magic-geo generate \
  --config configs/earthlike_seed.yaml \
  --output runs/earthlike/world.json \
  --summary runs/earthlike/summary.md

magic-geo validate-geo \
  --world runs/earthlike/world.json \
  --profile earthlike
```

For a deterministic run of this file, override the compute settings on a copy:

```bash
magic-geo init-config \
  --profile earthlike \
  --set compute.backend=cpu \
  --set compute.threads=1 \
  --output my-earthlike.yaml
```

---

## Choosing a starting seed

Start from the axis you actually care about, not from the name.

| If your premise is about… | Start from | Because |
| --- | --- | --- |
| Broad continents, overland travel, frontiers | `continental_realm` | A reduced 850-million-km³ inventory on an Earth-radius planet, plus the highest continental-crust target (0.52) among the temperate seeds; also your only geodesic-mesh example |
| Absolute water scarcity | `glasswind_desert` | Zero inventory takes a dedicated no-ocean branch; 0.162 precipitation gain; 0.97 river percentile |
| Islands, straits, maritime trade | `pelagic_archipelago` | 0.18 continental-crust target with 24 plates; 0.916 realized ocean |
| Cold, ice, survival | `cryogenic_slushball` | All three temperature forcings pushed negative simultaneously; 24.4% ice cells |
| Hazard, relief, geologic youth | `young_volcanic` | Saturates the tectonic activity clamp; 28 plates; 2.0 uplift scale |
| Rain, rivers, jungle, wetlands | `verdant_hothouse` | 5.348 precipitation gain; the only seed that fills closed basins |
| Seasonal extremity as a story engine | `solstice_extreme` | 75° tilt with everything else near-Earth, so the seasonal signal is isolated |
| Planetary scale and gravity | `ironroot_super_earth` | 9,500 km, 1.6 g, wider 8-neighbour stencil, suppressed relief |
| Deep time, worn terrain, closed basins | `oldstone_stagnant` | Zero motion, zero uplift, 10 refined erosion steps, 0.10 heat |
| A calibrated Earth baseline to diff against | `earthlike_seed` | The only file where `--profile earthlike` is the right gate |

### The selection workflow the gallery prescribes

Treat the YAML as a **regime**, then review generated evidence before naming the world (`docs/example_seed_gallery.md:152-168`):

1. Generate a 512-cell geo-only preview for several `run.seed` values.
2. Compare ocean/land fraction, biome coverage, ice, river and lake networks, landmass count, relief, and climate seasonality.
3. Inspect paths and edges: navigable rivers, coasts, passes, deserts, glaciers, and chokepoints.
4. Generate the best candidates at the declared resolution. Coastlines, narrow straits, island counts, and even realized ocean fraction are resolution sensitive.
5. Run `magic-geo validate-geo --profile generic` on exotic worlds. The `earthlike` profile is intentionally inappropriate for most gallery presets.
6. Only then select settlements, factions, hazards, and landmarks from the generated causal evidence.

A concrete sweep over four realizations of one regime, using only implemented flags:

```bash
for s in 12051003 700001 700002 700003; do
  magic-geo init-config \
    --profile default \
    --set run.seed=$s \
    --output /tmp/pelagic-$s.yaml \
    --force
done
```

That writes profile-derived files, not seed-derived ones. To sweep a *shipped seed*, copy it and edit `run.seed` per copy — `init-config` can only start from the three code-registered profiles (`src/magic_geo/cli/commands/config.py:40-43`):

```bash
for s in 12051003 700001 700002 700003; do
  sed "s/^  seed: .*/  seed: $s/" configs/seeds/pelagic_archipelago.yaml > /tmp/pelagic-$s.yaml
  magic-geo generate \
    --geo-only \
    --config /tmp/pelagic-$s.yaml \
    --cells 512 \
    --output runs/sweep/pelagic-$s.json
  magic-geo validate-geo --world runs/sweep/pelagic-$s.json --profile generic
done
```

The `generate` command echoes `cells`, `plates`, `ocean`, `rivers`, and elapsed time on completion — read from `world["summary"]`'s `cell_count`, `plate_count`, `ocean_fraction`, and `river_count` keys (`src/magic_geo/cli/commands/generate.py:83-89`) — which is enough to triage a sweep before opening any world file.

---

## Deriving your own preset

### Route A — copy a shipped seed (recommended for exotic regimes)

`configs/seeds-local/` is not a tracked directory; create it first, because `cp` will not. (`write_config` in Route B does create missing parents, `src/magic_geo/config.py:806`.)

```bash
mkdir -p configs/seeds-local
cp configs/seeds/oldstone_stagnant.yaml configs/seeds-local/my_world.yaml
```

Then edit. Rules that bite:

| Rule | Where enforced | Message |
| --- | --- | --- |
| Unknown keys are rejected | `extra="forbid"` on every model | pydantic `extra_forbidden` |
| `nan` / `inf` / `-inf` rejected on every float | `allow_inf_nan=False` on every model | validation error |
| Duplicate YAML keys rejected (no last-wins) | `_UniqueKeySafeLoader._construct_unique_mapping`, `src/magic_geo/config.py:89` | `invalid YAML: … found duplicate key …` with 1-based line/column |
| Root must be a mapping | `src/magic_geo/config.py:612` pipeline | `config root must be a YAML mapping` |
| `tectonics.plate_count < mesh.cell_count` | `validate_plate_density`, `src/magic_geo/config.py:500` | `plate_count must be smaller than mesh.cell_count` |
| `max_angular_speed >= min_angular_speed` | `validate_speeds`, `src/magic_geo/config.py:313` | `max_angular_speed must be >= min_angular_speed` |
| `run.name` must be 1–256 characters, NUL-free, UTF-8 encodable, and ≤ 1024 UTF-8 bytes | `min_length=1` / `max_length=256` on the field (`src/magic_geo/config.py:135-140`) bind first; then `validate_name_for_native_boundary` (decorator at `:142`, body at `:144-153`) | pydantic `string_too_long`, then e.g. `name must be at most 1024 UTF-8 bytes` |
| YAML complexity caps | `_check_yaml_complexity`, `src/magic_geo/config.py:557` | > 20,000 events, > 64 nesting levels, or > 64 aliases |

If you keep the "all 44 explicit" convention, your file will also survive a schema addition visibly (the load will fail with the missing-section mismatch rather than silently defaulting), which is the whole point of the convention.

### Route B — start from a code-registered profile

```bash
magic-geo init-config \
  --profile default \
  --set mesh.cell_count=2048 \
  --set tectonics.plate_count=18 \
  --set climate.precipitation_scale=1.35 \
  --set compute.backend=cpu \
  --set compute.threads=1 \
  --output configs/seeds-local/my_world.yaml
```

`--set` takes `section.field=YAML_VALUE`, repeatable, split on the **first** `=` only, with the value parsed by `yaml.safe_load` — so `false` is a bool, `128` an int, `0.8` a float, `"128"` a string (`parse_config_overrides`, `src/magic_geo/config.py:665`). Only two-part dotted paths resolve, since the schema is exactly two levels deep; replacing a whole section is rejected with `unknown configuration override '<path>'` (`apply_config_overrides`, `src/magic_geo/config.py:710`).

`write_config` (`src/magic_geo/config.py:800`) publishes atomically: it writes a hidden same-directory temp file, **re-parses exactly the bytes that will be committed**, then `os.link`s (no `--force`) or `os.replace`s (`--force`) into place, and always removes the temp file. Without `--force`, an existing target — or a concurrent writer that created it after the check — raises `FileExistsError("… already exists; pass --force to overwrite")`. Readers never observe a partial or invalid file.

Note that `init-config` output is a complete serialization: `dump_config_yaml` (`src/magic_geo/config.py:653`) dumps `model_dump(mode="python")` with `sort_keys=False`, so declaration order is preserved and every field is present. Route B therefore also produces an "all 44 explicit" file.

### Route C — Python

```python
from pathlib import Path
from magic_geo.config import create_config, write_config
from magic_geo.api import generate_geo_world

config = create_config(
    "earthlike",
    {
        "run.name": "my_world",
        "run.seed": 700042,
        "mesh.cell_count": 2048,
        "tectonics.continental_crust_fraction_target": 0.48,
        "climate.precipitation_scale": 1.2,
        "compute.backend": "cpu",
        "compute.threads": 1,
    },
)
write_config(Path("configs/seeds-local/my_world.yaml"), config, force=True)
world = generate_geo_world(config)
print(world["summary"]["ocean_fraction"], world["summary"]["river_count"])
```

### Checklist before you call a derived preset done

| Step | Command / check | Why |
| --- | --- | --- |
| 1. Load cleanly | `magic-geo generate --config <file> --geo-only --cells 512 --output /tmp/p.json` | Catches schema, cross-field, and YAML errors immediately |
| 2. Validate generically | `magic-geo validate-geo --world /tmp/p.json --profile generic` | Contract, replay, and conservation integrity — this is the gate that catches crust-transport and material-shadow replay failures |
| 3. Re-validate at declared resolution | repeat 1–2 without `--cells` | Ocean fraction, island counts, and coastlines are resolution sensitive |
| 4. Re-validate after touching coupled controls | any change to `plate_count`, `erosion.iterations`, `maturation_timestep_ma`, `ocean_water_inventory_km3`, or `mesh.cell_count` | The gallery documents concrete failures at nearby values of exactly these knobs (`docs/example_seed_gallery.md:75-86`) |
| 5. Pin determinism if you will replay | `compute.backend: cpu`, `compute.threads: 1` | A fixed thread count is bit-stable; different counts differ (`docs/configuration_reference.md:328-332`) |

### The two nonlinear boundaries you will hit

Reproduced from `docs/example_seed_gallery.md:75-86`:

- **Connected-ocean flooding has topology jumps.** The Super-Earth, solstice, and oldstone inventories use nearby round values that reconstruct exactly at the declared mesh; several superficially similar volumes generated a world but failed ocean-inventory closure. The mechanism is visible in `apply_sea_level`: the solver sweeps flood elevations, merging connected components, and accepts an exact solution only when the solved sea level falls inside the current elevation interval (`cpp/src/engine/ocean.cpp:160-183`); otherwise it keeps the best-error candidate.
- **Schema validity is weaker than simulation validity.** The exact desert preset passes with eight plates, but nearby plate counts and seeds can fail current crust-transport replay. The volcanic preset passes at six refined maturation steps; seven generates but fails a material-shadow replay, and eight exceeds the current accounting envelope.

---

## Limitations and unresolved claims

- **The presets are exploratory worldbuilding regimes, not calibrated replicas or predictions.** They use broad archetypes with original names, seeds, and parameter combinations; they do not reproduce franchise geography or lore, and they are not predictions of real exoplanets (`docs/example_seed_gallery.md:9-12`, `:96-99`).
- **The audited numbers are reference observations, not acceptance bands.** They are values from one generation at one declared resolution and are explicitly "not stable acceptance bands for edited parameters or future engine versions" (`docs/example_seed_gallery.md:60-61`).
- **`ocean_fraction_target` does not steer anything.** It is a diagnostic comparison value; the realized fraction differs and changes with mesh resolution (`docs/example_seed_gallery.md:131-133`). Every gallery seed with a nonzero water inventory shows a gap between the two; only `glasswind_desert`, whose target and inventory are both zero, has none.
- **The maturation clock is nominal, not physical.** `tectonics` and `erosion.maturation_timestep_ma` are procedural controls with nominal time labels, not calibrated plate velocities or geological clocks (`docs/example_seed_gallery.md:138-139`). The engine's own limitation list states that "the simulation clock orders procedural stages but has no calibrated physical duration" (`src/magic_geo/geo_validation.py:29`).
- **Non-Earth planets are lightly validated.** The schema permits extreme planets and planet-scaling tests confirm the knobs move outputs, but the geo-validation target bands are Earth-tuned, so exotic configs are not asserted physically plausible (`docs/configuration_reference.md:333-336`).
- **Determinism depends on a fixed thread count.** Output currently varies with `compute.threads` / `OMP_NUM_THREADS`; `seed` alone is not sufficient for reproducibility until this is fixed (`docs/configuration_reference.md:328-332`). The nine gallery seeds pin `cpu`/`1` for this reason; `earthlike_seed.yaml` does not.
- **Enricher parameters are not configurable.** The Python enrichers that produce most layers (soils, biomes, groundwater, resources, reefs, human geography) run with fixed internal constants; only the physical drivers are exposed (`docs/configuration_reference.md:323-327`). No seed can tune a biome threshold.
- **The volcanic preset does not simulate exposed lava**, the seasonal preset **cannot reproduce irregular multi-year seasons** (twelve months always), and the desert preset has **one star** and **no explicit deep-aquifer inventory** (`docs/example_seed_gallery.md:146-150`).
- **Standing engine-level unresolved claims apply to every seed.** From `GEO_MODEL_LIMITATIONS` (`src/magic_geo/geo_validation.py:28-41`), carried forward without softening: the diagnostic atmosphere is not a three-dimensional mass-conserving circulation solver; the configured ocean inventory is not a closed total-water partition across ocean, ice, groundwater, lakes, and atmosphere; first-order conservative crust overlap is diffusive, CPU-authoritative, and guarded by a 16,384-fragment local arrangement cap without exhaustive worst-case proof, while an accelerator may validate and discard only a continuous-moment CSR shadow — geometry, categories, production state, complete parity, and device-lane evidence remain unresolved; the overlap candidate crosswalk does not resolve a local fragment-to-segment link, physical polarity, allocation, material fate, slab transfer, or state mutation; post-transport tectonic rules expose ordered per-reason state-moment changes but not physical reservoir, material-provenance, energy, or phase source/sink fluxes; initial oceanic-like crust age does not reconstruct local flowlines, calibrated spreading, subduction sinks, convergence history, or physical seafloor creation and destruction; persistent dry-rock packets and the finite counter-model remain non-authoritative; ecosystem, species, wildfire, and resource layers are diagnostic index models rather than calibrated population or process solvers; and Earth empirical fit remains a separate calibration verdict from internal contract integrity.
- **Some derived numbers on this page are computed, not measured.** The "Derived regime diagnostics" table is evaluated from the checked-in YAML using formulas transcribed from `cpp/src/engine/core.cpp`, `climate.cpp`, `tectonics.cpp`, and `constants.hpp`. That the thermal-mean anchor matches the audited global mean within 0.1 °C for all nine seeds is an observation on these configurations, not a proven invariant of the model.
- **Not verified in source for this page:** `elevation_span_m`, `calibration_pass_fraction`, `realism_evidence_coverage_fraction`, `applicable_realism_pass_fraction`, and per-seed biome-class counts are not published in the gallery audit table, so their pass/fail status against the `earthlike` envelope is unknown here. The specific text of the 1–2 nonfatal warnings recorded for `glasswind_desert`, `pelagic_archipelago`, `cryogenic_slushball`, `young_volcanic`, and `oldstone_stagnant` is not recorded in the source documents.

---

## See also

- [Configuration Reference](./05-configuration-reference.md) — the complete 44-field schema, constraints, and profile mechanics
- [CLI Reference](./06-cli-reference.md) — every `magic-geo` command and flag
- [Quickstart](./03-quickstart.md) — first generation run end to end
- [Python API](./07-python-api.md) — `create_config`, `load_config`, `generate_world`, `generate_geo_world`
- [Validation](./12-validation.md) — `validate` and `validate-geo`, the `generic` and `earthlike` profiles
- [Geo Validation Suite](./13-geo-validation-suite.md) — the multi-scenario matrix built on `configs/earthlike_seed.yaml`
- [Calibration Against Real-Earth Data](./14-calibration.md) — why Earth fit is a separate verdict
- [Mesh and Geometry](./features/mesh-and-geometry.md) — Fibonacci vs. geodesic backends and the `10·F²+2` rounding
- [Tectonics and Plates](./features/tectonics-and-plates.md) — plate count, angular speeds, boundary smoothing, activity clamp
- [Oceans, Currents and Coasts](./features/oceans-and-coasts.md) — the connected-ocean sea-level solve and its topology jumps
- [Climate and Atmosphere](./features/climate-and-atmosphere.md) — stellar, greenhouse, pressure, and seasonal forcing terms
- [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) — `river_percentile` and `preserve_geologic_depressions`
- [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) — iterations, refined timesteps, and the accounting envelope
- [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md) — the gravity relief scale
- [Troubleshooting and FAQ](./22-troubleshooting.md) — ocean-inventory closure failures and replay errors
- [Glossary](./21-glossary.md) — regime, profile, preset, layer contract
