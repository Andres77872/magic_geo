# Geo Validation Suite

[Wiki home](./README.md) > Geo Validation Suite

The geo validation suite is the multi-scenario tier of geo-only validation: it generates a whole matrix of worlds from one base config plus per-scenario overrides, runs the full single-world geo validator on each, gates per-scenario metric envelopes, compares metrics *across* scenario pairs to require directional physical responses, reruns a configured scenario to test determinism, and — for scenarios that declare it — scores one world against a checksum-pinned bundle of Earth-reference empirical targets. It is implemented in `src/magic_geo/geo_validation_suite/` and driven by `magic-geo validate-geo-suite` (`src/magic_geo/cli/commands/validate_geo.py:91`). The repository deliberately keeps the *internal* verdict (structure, replay, conservation, determinism, paired response) separate from the *external* empirical verdict (Earth fit), and the checked-in state currently fails several external metrics; this page reports that state as the repository reports it. Nothing on this page upgrades a hedged claim: the suite proves that declared contracts and declared directional responses hold, not that the generator reproduces Earth.

## On this page

- [What the suite is, and how it differs from single-world validation](#what-the-suite-is-and-how-it-differs-from-single-world-validation)
- [Command surface](#command-surface)
- [Matrix file schema](#matrix-file-schema)
- [Commented matrix example](#commented-matrix-example)
- [Checked-in scenario inventory](#checked-in-scenario-inventory)
- [Paired cross-scenario relations](#paired-cross-scenario-relations)
- [Determinism rerun and the geo fingerprint](#determinism-rerun-and-the-geo-fingerprint)
- [The empirical target bundle](#the-empirical-target-bundle)
- [Suite report JSON structure](#suite-report-json-structure)
- [Markdown summary structure](#markdown-summary-structure)
- [Adding a new scenario or relation](#adding-a-new-scenario-or-relation)
- [Documented pass/fail state and known Earth-fit gaps](#documented-passfail-state-and-known-earth-fit-gaps)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## What the suite is, and how it differs from single-world validation

`validate-geo` (see [Validation](./12-validation.md)) takes **one already-generated world file** and answers "is this document internally coherent, does every replay reproduce, does every layer contract hold". `validate-geo-suite` **generates worlds itself** and answers a strictly larger set of questions that a single world cannot answer.

| Capability | `validate-geo` | `validate-geo-suite` |
|---|---|---|
| Input | a generated `.json`/`.mgeo` world (`--world`) | a base YAML config plus a scenario matrix (`--config`, `--matrix`) |
| Worlds involved | exactly one, supplied by the caller | one per scenario `repeat`, generated in-process by `generate_geo_world` (`evaluate.py:175`) |
| Per-world checks | the full geo validator + 14 layer contracts | the same, run per scenario member (`evaluate.py:210`) |
| Per-scenario metric envelopes | only the fixed `earthlike` profile bands | arbitrary declared `expectations` per scenario (`manifest.py:21`) |
| Cross-world comparison | none | `relations`: required directional responses between two named scenarios (`evaluate.py:83`) |
| Determinism | none | repeated generation compared by SHA-256 geo fingerprint (`evaluate.py:31`, `:215`) |
| External Earth fit | not evaluated (only the built-in 12-metric `calibration_pass_fraction` metric is read) | `empirical_calibration` per scenario, against a pinned target bundle (`evaluate.py:125`) |
| Report | `geo_world_validation_v1` | `geo_pipeline_validation_suite_v1` wrapping one `geo_world_validation_v1` summary per member |
| Civilization layers | out of declared scope | out of declared scope *and* stripped from the determinism fingerprint (`_constants.py:30`, `:114`) |

Three structural consequences are worth stating explicitly.

1. **The suite is a generator, not a linter.** Every scenario runs `generate_geo_world` (`src/magic_geo/api.py:287`), which skips native civilization simulation and sets `generation_scope = "geo_only"`. A matrix run therefore costs one full generation per repeat; the checked-in matrix is 21 scenarios with one `repeat: 2`, i.e. 22 generations.
2. **Metamorphic testing is the point.** A single world can be self-consistent and still be physically inert. Relations such as `snowball < earthlike_pair` on `global_mean_temperature_c` by at least 20 °C assert that the *model responds* to a forcing, which no single-world check can express.
3. **Internal and external verdicts are separated by construction.** `internal_validation_passed` and `empirical_calibration_passed` are distinct member fields (`evaluate.py:244`, `:246`), aggregated separately in `summary`, and rendered in separate markdown sections. The declared model limitation is verbatim: *"Earth empirical fit remains a separate calibration verdict from internal contract integrity"* (`src/magic_geo/geo_validation.py:40`).

Each member's per-world validation is the standard geo validator, so the same profile semantics apply. A scenario's `profile: earthlike` adds the nine range gates plus `biome_diversity` in the `earthlike_profile` domain (`geo_validation.py:764`): `ocean_fraction` 0.55–0.85, `global_mean_temperature_c` 8–22, `mean_land_precipitation_mm_y` 350–1800, `elevation_span_m` 8000–25000, `river_cell_fraction` 0.002–0.08, `ice_cell_fraction` 0.005–0.45, `calibration_pass_fraction` 0.75–1.0, `realism_evidence_coverage_fraction` 0.65–1.0, `applicable_realism_pass_fraction` 0.75–1.0, and `biome_class_count >= 6`. Scenarios that deliberately leave the Earth regime (waterworld, snowball, hothouse, …) use the default `generic` profile so those bands do not fire.

---

## Command surface

```bash
magic-geo validate-geo-suite \
  --config configs/earthlike_seed.yaml \
  --matrix configs/geo_validation_matrix.yaml \
  --output runs/geo_validation.json \
  --summary runs/geo_validation.md
```

| Flag | Type | Default | Required | Help (verbatim) |
|---|---|---|---|---|
| `--config`, `-c` | Path (`exists=True`) | `configs/earthlike_seed.yaml` | no | `Base YAML config path.` |
| `--matrix`, `-m` | Path (`exists=True`) | `configs/geo_validation_matrix.yaml` | no | `Geo scenario matrix with nested config overrides and paired gates.` |
| `--output`, `-o` | Path | `runs/geo_validation.json` | no | `Machine-readable suite report.` |
| `--summary` | Path \| None | `None` | no | `Optional Markdown suite report.` |

Defined at `src/magic_geo/cli/commands/validate_geo.py:91-114`. There are no other flags — no per-scenario filter, no severity policy switch, no `--fail-on-warnings` equivalent. Realism warnings are non-fatal inside the suite exactly as they are inside `validate-geo` without `--fail-on-warnings`; they surface as `realism_deviations` on the member and in a dedicated markdown section, and they do not change any verdict.

Progress is echoed per scenario as `[<index+1>/<count>] <scenario id>` via the `progress` callback (`validate_geo.py:120-122`, callback contract at `evaluate.py:176`).

| Exit code | Condition | Source |
|---|---|---|
| `0` | `report["passed"]` is true | `validate_geo.py:150` |
| `1` | `report["passed"]` is false — failed scenario members and/or failed relations; stderr lists `Failed scenarios:`, `Failed relations:`, and `Failed external empirical metrics:` | `validate_geo.py:150-169` |
| `2` | `GeoValidationSuiteError`, pydantic `ValidationError`, or `ValueError` raised while loading the config/manifest or evaluating the suite | `validate_geo.py:128-130` |
| `2` | Typer usage errors (missing/unknown option, `exists=True` path absent) | Click/Typer framework |

The report JSON is written **before** the verdict is checked (`validate_geo.py:131`), so a failing run still leaves a complete artifact. `write_json` creates parent directories and serializes with `indent=2, sort_keys=True, allow_nan=False` (`src/magic_geo/io/json_writer.py:10-15`).

Equivalent Python API (see [Python API](./07-python-api.md)):

```python
from pathlib import Path

from magic_geo.config import load_config
from magic_geo.geo_validation_suite import (
    evaluate_geo_validation_suite,
    load_geo_validation_manifest,
    write_geo_validation_suite_markdown,
)
from magic_geo.io import write_json

base_config = load_config(Path("configs/earthlike_seed.yaml"))
manifest = load_geo_validation_manifest(Path("configs/geo_validation_matrix.yaml"))
report = evaluate_geo_validation_suite(base_config, manifest)

write_json(Path("runs/geo_validation.json"), report)
write_geo_validation_suite_markdown(Path("runs/geo_validation.md"), report)
print(report["passed"], report["summary"]["scenario_pass_count"])
```

`evaluate_geo_validation_suite` also accepts `world_factory` (default `generate_geo_world`) and `progress` keyword arguments (`evaluate.py:171-177`); `world_factory` is the injection point used by the test suite.

The browser workbench exposes the same command as the **"Run geo validation suite"** job with fields `config`, `matrix` (required there), `output`, `summary` (`src/magic_geo/web_jobs.py:144-153`), and resolves the matrix's referenced target-bundle and derivation artifacts as indirect job inputs (`web_jobs.py:819`). See [Web Workbench](./15-web-workbench.md).

---

## Matrix file schema

Loaded by `load_geo_validation_manifest` (`src/magic_geo/geo_validation_suite/manifest.py:46`). Validation is **strict and closed at every level**: any unknown field anywhere raises `GeoValidationSuiteError` (a `ValueError` subclass, `errors.py:6`). Nothing is silently ignored.

### Root

| Field | Type | Required | Default | Constraint / meaning |
|---|---|---|---|---|
| `schema_version` | int | yes | — | Must equal `1` (`GEO_VALIDATION_SUITE_SCHEMA_VERSION`, `_constants.py:6`; check at `manifest.py:59`) |
| `name` | string | yes | — | Non-empty after strip; echoed as `report["name"]` and the markdown H1 |
| `scenarios` | list | yes | — | Non-empty; at most `MAX_SCENARIO_COUNT = 64` (`_constants.py:12`; check at `manifest.py:67`) |
| `relations` | list | no | `[]` | May be empty or omitted; then `response_validation_performed` is false |

Unknown root keys are rejected at `manifest.py:53-58`.

### Scenario

| Field | Type | Required | Default | Constraint / meaning |
|---|---|---|---|---|
| `id` | string | yes | — | Non-empty, unique across the matrix (`manifest.py:91-93`) |
| `description` | string | no | `""` | Stripped; carried into the member record only |
| `profile` | string | no | `"generic"` | Must be `generic` or `earthlike` (`manifest.py:94-96`); passed to `validate_geo_world` |
| `overrides` | object | no | `{}` | Deep-merged into the dumped base `WorldConfig` (`_helpers.py:74`) |
| `expectations` | object | no | `{}` | `{metric: {min?, max?}}`; see below |
| `empirical_calibration` | object \| null | no | `null` | External Earth-fit policy; see [The empirical target bundle](#the-empirical-target-bundle) |
| `repeat` | int | no | `1` | Must be an integer in `1..3` inclusive; booleans rejected (`manifest.py:100-102`) |
| `tags` | list of strings | no | `[]` | Deduplicated and sorted (`manifest.py:106`); purely informational — nothing filters on tags |

Unknown scenario keys are rejected at `manifest.py:77-90`.

**`overrides` merge rules** (`_helpers.py:74-88`), applied against `base_config.model_dump(mode="python")`:

| Rule | Behavior on violation |
|---|---|
| Every override key must already exist in the base config | `unknown config override '<dotted.path>'` |
| A key whose base value is a dict must be overridden with a dict | `config override '<path>' must be an object` |
| A key whose base value is a scalar must not be overridden with a dict | `config override '<path>' cannot be an object` |
| Scalars replace scalars; nested dicts recurse | — |

The merged mapping is then re-validated through `type(base_config).model_validate(...)`, so all normal config constraints still apply (`evaluate.py:194-196`); a failure raises `scenario '<id>' config is invalid: <pydantic error>`.

Additionally, the suite hard-errors before generating if a scenario's resolved config has `output.include_cells` falsy: `scenario '<id>' must keep output.include_cells=true for deep validation` (`evaluate.py:189-192`). Deep geo validation consumes per-cell state, so a cell-free scenario is refused rather than silently degraded.

**`expectations`** (`manifest.py:21-43`):

| Field | Type | Required | Constraint |
|---|---|---|---|
| `<metric name>` | object | — | Must be a non-empty object; keys restricted to `min` and `max` (`manifest.py:31`) |
| `min` | number | no | Finite; booleans rejected (`_helpers.py:18`) |
| `max` | number | no | Finite; if both present, `max >= min` or the range is rejected as inverted (`manifest.py:40`) |

Metric names are matched against `extract_geo_metrics(world)` (`geo_validation.py:339`). A metric that is absent, non-numeric, boolean, or non-finite fails the check — an unknown metric name is a **failing** expectation, not a skipped one (`evaluate.py:63-68`).

### Relation

| Field | Type | Required | Default | Constraint / meaning |
|---|---|---|---|---|
| `id` | string | yes | — | Non-empty, unique across relations (`manifest.py:148-150`) |
| `description` | string | no | `""` | Stripped; carried through to the result record |
| `left` | string | yes | — | Must name a known scenario (`manifest.py:153`) |
| `right` | string | yes | — | Must name a known scenario, and must differ from `left` (`manifest.py:155`) |
| `metric` | string | yes | — | Key looked up in each scenario's `extract_geo_metrics` map |
| `operator` | string | yes | — | One of `lt`, `le`, `gt`, `ge`, `eq` (`COMPARISON_OPERATORS`, `_constants.py:15`; check at `manifest.py:159`) |
| `minimum_difference` | number | no | `0.0` | Must be finite and `>= 0`; must be exactly `0` when `operator == "eq"` (`manifest.py:166-171`) |
| `tolerance` | number | no | `1.0e-9` | Must be finite and `>= 0` (`manifest.py:172-174`) |

Unknown relation keys are rejected at `manifest.py:134-147`.

**Operator semantics** (`evaluate.py:105-114`), with `left`/`right` being the metric values of the two scenarios:

| Operator | Passes when | Note |
|---|---|---|
| `lt` | `left < right` **and** `left <= right - minimum_difference + tolerance` | strict inequality *and* the margin |
| `le` | `left <= right - minimum_difference + tolerance` | margin only |
| `gt` | `left > right` **and** `left >= right + minimum_difference - tolerance` | strict inequality *and* the margin |
| `ge` | `left >= right + minimum_difference - tolerance` | margin only |
| `eq` | `abs(left - right) <= tolerance` | invariance gate; `minimum_difference` forced to 0 |

If either side is missing, boolean, or non-finite, the relation records `passed = false` and `difference = null` (`evaluate.py:90-97`). `difference` is always `left - right` when both sides are numeric.

The loader returns a normalized manifest `{schema_version, name, scenarios, relations}` with every default materialized (`manifest.py:188-193`). `evaluate_geo_validation_suite` refuses a manifest that was not produced by the loader by re-checking `schema_version` (`evaluate.py:178-179`).

---

## Commented matrix example

A minimal but complete matrix exercising every field, written against `configs/earthlike_seed.yaml` as the base config:

```yaml
# Root: exactly these four keys are accepted.
schema_version: 1                       # must be 1
name: my_custom_matrix_v1               # non-empty; appears in the report and markdown H1

scenarios:
  - id: reference                       # unique, non-empty
    description: Unmodified base configuration.
    profile: earthlike                  # generic | earthlike; default generic
    tags: [earth, canonical_reference]  # deduplicated + sorted; informational only
    # External Earth-fit policy. A relative path is resolved against THIS matrix
    # file's directory, not the working directory. This matrix is assumed to sit
    # at the repository root, so the checked-in bundle is reached via configs/.
    empirical_calibration:
      target_bundle: configs/geo_validation_earth_empirical_targets.json
      require_complete: true            # default true: every target metric must be observable
      require_all_passed: true          # default true: every target metric must be in range
    expectations:                       # metric -> {min?, max?}; both bounds optional
      applicable_realism_pass_fraction: {min: 1.0, max: 1.0}
      calibration_pass_fraction: {min: 1.0, max: 1.0}

  - id: control
    description: Smaller repeated control that also gates determinism.
    profile: earthlike
    repeat: 2                           # 1..3; >=2 enables the determinism rerun
    overrides:                          # deep-merged into the dumped base WorldConfig
      mesh:
        cell_count: 512                 # key must already exist in the base config
      erosion:
        iterations: 3
    expectations:
      ocean_fraction: {min: 0.50, max: 0.85}

  - id: cold_forcing
    description: Cold, weakly forced planet.
    # profile omitted -> generic, so the earthlike Earth-regime bands do not fire
    tags: [climate_regime, cold]
    overrides:
      mesh: {cell_count: 512}
      planet:
        stellar_luminosity: 0.55
        greenhouse_factor: 0.50
      climate:
        base_temperature_c: -10.0
      erosion: {iterations: 3}
    expectations:
      global_mean_temperature_c: {max: -15.0}   # max-only bound is legal

relations:
  - id: cold_forcing_reduces_temperature
    description: Reducing luminosity and greenhouse forcing must cool the planet.
    left: cold_forcing                  # must be a known, different scenario id
    operator: lt                        # lt | le | gt | ge | eq
    right: control
    metric: global_mean_temperature_c   # any extract_geo_metrics key
    minimum_difference: 20.0            # >= 0; required margin, in metric units
    # tolerance omitted -> 1.0e-9

  - id: control_area_matches_reference_scale
    left: cold_forcing
    operator: eq                        # equality relations require minimum_difference = 0
    right: control
    metric: surface_area_km2
    tolerance: 0.000001                 # widened invariance tolerance
```

Run it:

```bash
magic-geo validate-geo-suite \
  --config configs/earthlike_seed.yaml \
  --matrix my_custom_matrix.yaml \
  --output runs/my_matrix.json \
  --summary runs/my_matrix.md
```

---

## Checked-in scenario inventory

`configs/geo_validation_matrix.yaml` declares `name: geo_only_earth_and_diverse_planet_matrix_v1`, **21 scenarios and 26 relations**. The base config it is meant to run against is `configs/earthlike_seed.yaml`: seed `424242`, 4,096-cell `fibonacci_sphere` mesh with `neighbor_count: 7`, 14 plates, `erosion.iterations: 6`, `erosion.maturation_timestep_ma: 5.0`, `output.include_cells: true`.

Most scenarios shrink to `mesh.cell_count: 512`, `tectonics.plate_count: 10`, `erosion.iterations: 3` so the matrix stays runnable; only `earthlike_reference` uses the unmodified base config, and the timestep pair drops to 128 cells / 8 plates on a different seed.

| Scenario | What it varies (relative to the base config) | What it is meant to prove |
|---|---|---|
| `earthlike_reference` | nothing — unmodified checked-in 4,096-cell Earth-like config; `profile: earthlike`; the only scenario with `empirical_calibration`; expectations pin `applicable_realism_pass_fraction` and `calibration_pass_fraction` to exactly `[1.0, 1.0]` | The canonical Earth member: full internal validation at production resolution, plus the only external Earth-fit evaluation in the matrix |
| `earthlike_pair` | `mesh.cell_count: 512`, `plate_count: 10`, `erosion.iterations: 3`, `repeat: 2`; `profile: earthlike`; expectations on `ocean_fraction` 0.50–0.85, `global_mean_temperature_c` 8–22, `mean_land_precipitation_mm_y` 350–1800 | Serves two roles: the shared right-hand control for 12 of the 26 relations, and the matrix's only determinism rerun |
| `earth_seed_1` | `run.seed: 1` on the reduced Earth setup; `profile: earthlike` | Generative robustness: a different seed must still satisfy the Earth-like envelope |
| `earth_seed_2` | `run.seed: 2` | Same |
| `earth_seed_3` | `run.seed: 3` | Same — and currently the sole fatal core-validation failure in the documented run (see below) |
| `arid_landworld` | `planet.ocean_fraction_target: 0.0`, `planet.ocean_water_inventory_km3: 0.0`, `climate.precipitation_scale: 0.12`; expectations `ocean_fraction` exactly 0, `mean_land_precipitation_mm_y <= 180`, `mean_land_runoff_mm_y <= 100`, `desert_land_fraction >= 0.40`, `valid_river_sink_fraction` 0.95–1.0 | Zero-ocean edge case: absence of rivers is a *valid* outcome (reported `not_applicable`, not a vacuous pass), and terminal-sink validity must still hold for whatever drainage exists |
| `waterworld` | `planet.ocean_fraction_target: 0.95`, `ocean_water_inventory_km3: 5.0e9`; expectations `ocean_fraction` 0.98–1.0, `land_area_fraction` 0–0.02, `river_cell_fraction` 0–0.002 | Deep global-ocean edge case with essentially no terrestrial phenomena required |
| `snowball` | `planet.stellar_luminosity: 0.55`, `greenhouse_factor: 0.50`, `climate.base_temperature_c: -10.0`; expectations `global_mean_temperature_c <= -15`, `ice_cell_fraction >= 0.15` | Cold climate forcing propagates into temperature, moisture and ice |
| `hothouse` | `planet.stellar_luminosity: 1.60`, `greenhouse_factor: 1.70`, `climate.base_temperature_c: 35.0`; expectations `global_mean_temperature_c >= 40`, `ice_cell_fraction` 0–0.01 | Hot climate forcing propagates into temperature and removes ice |
| `low_obliquity` | `planet.axial_tilt_deg: 0.0`; expectation `mean_land_seasonal_temperature_range_c` 0–0.1 | Zero-obliquity control: no axial tilt must mean essentially no seasonal cycle |
| `high_obliquity` | `planet.axial_tilt_deg: 75.0`; expectation `mean_land_seasonal_temperature_range_c >= 35` | Obliquity drives seasonality, in the paired direction against `low_obliquity` |
| `thin_atmosphere` | `planet.gravity_g: 0.40`, `atmosphere_pressure_bar: 0.05`; expectations `global_mean_temperature_c <= 5`, `mean_land_precipitation_mm_y <= 650` | Low-gravity thin-atmosphere climate and hydrology response |
| `small_planet` | `planet.radius_km: 3000.0`, `gravity_g: 0.40`, `ocean_water_inventory_km3: 296600000.0`; no expectations | Planet-scale down-scaling with an area-scaled ocean inventory; the assertion is carried by the surface-area relation |
| `super_earth` | `planet.radius_km: 9500.0`, `gravity_g: 1.60`, `ocean_water_inventory_km3: 2975700000.0`; no expectations | Planet-scale up-scaling, likewise asserted by a relation |
| `geodesic_backend` | `mesh.backend: geodesic_icosahedron`, `mesh.cell_count: 642`; expectation `cell_count` exactly 642 | The non-uniform-area geodesic mesh honours its cell-count contract and passes the same natural-system replays as the Fibonacci backend |
| `stagnant_surface` | `tectonics.min_angular_speed: 0.0`, `max_angular_speed: 0.0`, `plate_motion_scale_deg_per_step: 0.0`, `erosion.iterations: 0`; expectations `simulation_stage_count` exactly 2, `plate_motion_transition_count` exactly 0 | The inert control for geodynamic relations: no plate motion, no iterative erosion, minimal stage ledger |
| `active_surface` | `tectonics.plate_motion_scale_deg_per_step: 4.0`, `planet.internal_heat: 1.8`, `geological_age_ga: 1.0`, `erosion.iterations: 6`, `erosion.tectonic_uplift_scale: 1.5`; expectations `simulation_stage_count` exactly 8, `plate_motion_transition_count` exactly 6, `mountain_convergent_alignment` 0.55–1.0 | A young, hot, rapidly moving and strongly eroding surface produces more stages, rotation, relief change and sediment than the stagnant control |
| `maturation_initial` | `mesh.cell_count: 512`, `plate_count: 10`, `erosion.iterations: 0` — identical to `maturation_evolved` except for the iteration count, and on the base seed; expectations `simulation_stage_count` 2, `plate_motion_transition_count` 0, `crust_evolved_cell_fraction` exactly 0, `plate_reassigned_cell_fraction` exactly 0 | Isolated-iteration control: with zero maturation iterations, crust state and plate assignment must be *untouched* |
| `maturation_evolved` | identical to `maturation_initial` except `erosion.iterations: 6`; expectations `simulation_stage_count` 8, `plate_motion_transition_count` 6, `crust_evolved_cell_fraction` 0.50–1.0, `plate_reassigned_cell_fraction` 0.01–1.0 | Changing *only* the iteration count evolves crust and reassigns plate domains — the coupled maturation loop actually does work |
| `maturation_timestep_coarse` | `run.seed: 20260711`, `mesh.cell_count: 128`, `plate_count: 8`, `erosion.iterations: 2`, `maturation_timestep_ma: 5.0`; expectations `maturation_timestep_ma` 5.0, `maturation_timestep_scale` 1.0, `nominal_maturation_duration_ma` 10.0 | Ten nominal Ma represented as 2 × 5 Ma reference-size transitions |
| `maturation_timestep_refined` | same seed/mesh/plates, `erosion.iterations: 4`, `maturation_timestep_ma: 2.5`; expectations `maturation_timestep_ma` 2.5, `maturation_timestep_scale` 0.5, `nominal_maturation_duration_ma` 10.0 | The same ten nominal Ma as 4 × 2.5 Ma transitions — the basis for the timestep-refinement invariance relations |

Note what the maturation-timestep pair does **not** claim. `nominal_maturation_duration_ma` is a *nominal* clock quantity; the declared model limitation is that *"the simulation clock orders procedural stages but has no calibrated physical duration"* (`geo_validation.py:29`). The refinement relations assert self-consistency of the nominal integration, not that 10 Ma of physical time elapsed.

---

## Paired cross-scenario relations

All 26 relations from `configs/geo_validation_matrix.yaml:335-516`. Every one compares `extract_geo_metrics` values of two already-generated members; the metric is looked up by name in each member's `metrics` map. `tolerance` is the default `1e-9` unless shown.

| Relation id | Left | Op | Right | Metric | Min difference | Required directional response |
|---|---|---|---|---|---:|---|
| `less_water_makes_less_ocean` | `arid_landworld` | `lt` | `earthlike_pair` | `ocean_fraction` | 0.40 | Removing the water inventory must reduce ocean fraction by at least 0.40 |
| `more_water_makes_more_ocean` | `waterworld` | `gt` | `earthlike_pair` | `ocean_fraction` | 0.10 | A 5×10⁹ km³ inventory must raise ocean fraction by at least 0.10 |
| `dry_forcing_reduces_precipitation` | `arid_landworld` | `lt` | `earthlike_pair` | `mean_land_precipitation_mm_y` | 300.0 | Precipitation scaling of 0.12 must cut mean land precipitation by ≥300 mm/y |
| `dry_forcing_reduces_runoff` | `arid_landworld` | `lt` | `earthlike_pair` | `mean_land_runoff_mm_y` | 150.0 | Reduced precipitation must propagate to ≥150 mm/y less runoff |
| `cold_forcing_reduces_temperature` | `snowball` | `lt` | `earthlike_pair` | `global_mean_temperature_c` | 20.0 | Lower luminosity + greenhouse must cool the planet by ≥20 °C |
| `cold_forcing_reduces_precipitation` | `snowball` | `lt` | `earthlike_pair` | `mean_land_precipitation_mm_y` | 300.0 | Cooling must reduce the moisture cycle by ≥300 mm/y |
| `cold_forcing_reduces_runoff` | `snowball` | `lt` | `earthlike_pair` | `mean_land_runoff_mm_y` | 150.0 | Cooling must reduce runoff by ≥150 mm/y |
| `hot_forcing_raises_temperature` | `hothouse` | `gt` | `earthlike_pair` | `global_mean_temperature_c` | 25.0 | Higher luminosity + greenhouse must warm the planet by ≥25 °C |
| `snowball_has_more_ice` | `snowball` | `gt` | `earthlike_pair` | `ice_cell_fraction` | 0.05 | Cold forcing must add ≥0.05 ice-cell fraction |
| `hothouse_has_less_ice` | `hothouse` | `lt` | `earthlike_pair` | `ice_cell_fraction` | 0.02 | Hot forcing must remove ≥0.02 ice-cell fraction |
| `high_tilt_increases_seasonality` | `high_obliquity` | `gt` | `low_obliquity` | `mean_land_seasonal_temperature_range_c` | 30.0 | 75° vs 0° obliquity must widen the mean land seasonal range by ≥30 °C |
| `small_planet_has_less_surface_area` | `small_planet` | `lt` | `earthlike_pair` | `surface_area_km2` | 1.0e8 | A 3,000 km radius must reduce surface area by ≥100,000,000 km² |
| `super_earth_has_more_surface_area` | `super_earth` | `gt` | `earthlike_pair` | `surface_area_km2` | 3.0e8 | A 9,500 km radius must add ≥300,000,000 km² |
| `active_surface_has_more_stages` | `active_surface` | `gt` | `stagnant_surface` | `simulation_stage_count` | 6.0 | Six erosion iterations must add ≥6 coupled stages over the inert control |
| `active_surface_has_more_plate_rotation` | `active_surface` | `gt` | `stagnant_surface` | `mean_plate_cumulative_rotation_deg` | 1.0 | Non-zero angular speeds must accumulate ≥1° more mean plate rotation |
| `active_surface_has_more_erosion_change` | `active_surface` | `gt` | `stagnant_surface` | `mean_erosion_iteration_elevation_change_m` | 1.0 | Active erosion must change elevation by ≥1 m more per erosion stage |
| `active_surface_mobilizes_more_sediment` | `active_surface` | `gt` | `stagnant_surface` | `sediment_gross_mobilization_volume_km3` | 1.0e6 | Active erosion must mobilize ≥1,000,000 km³ more gross sediment |
| `maturation_iterations_add_coupled_stages` | `maturation_evolved` | `gt` | `maturation_initial` | `simulation_stage_count` | 6.0 | Changing *only* `erosion.iterations` 0→6 must add ≥6 stages |
| `maturation_iterations_rotate_plates` | `maturation_evolved` | `gt` | `maturation_initial` | `mean_plate_cumulative_rotation_deg` | 1.0 | The same isolated change must accumulate ≥1° more plate rotation |
| `maturation_iterations_evolve_crust` | `maturation_evolved` | `gt` | `maturation_initial` | `crust_evolved_cell_fraction` | 0.50 | The same isolated change must evolve ≥50% more cells' crust state |
| `maturation_iterations_reassign_plate_domains` | `maturation_evolved` | `gt` | `maturation_initial` | `plate_reassigned_cell_fraction` | 0.01 | The same isolated change must reassign ≥1% more cells between plates |
| `maturation_iterations_mobilize_sediment` | `maturation_evolved` | `gt` | `maturation_initial` | `sediment_gross_mobilization_volume_km3` | 1.0e6 | The same isolated change must mobilize ≥1,000,000 km³ more sediment |
| `timestep_refinement_preserves_nominal_duration` | `maturation_timestep_refined` | `eq` | `maturation_timestep_coarse` | `nominal_maturation_duration_ma` | 0 (`tolerance: 1e-6`) | 4 × 2.5 Ma and 2 × 5 Ma must represent the *same* nominal horizon |
| `timestep_refinement_preserves_plate_rotation` | `maturation_timestep_refined` | `eq` | `maturation_timestep_coarse` | `mean_plate_cumulative_rotation_deg` | 0 (`tolerance: 1e-6`) | The integrated cumulative plate rotation must be invariant to timestep size |
| `timestep_refinement_uses_smaller_transitions` | `maturation_timestep_refined` | `lt` | `maturation_timestep_coarse` | `maturation_timestep_ma` | 2.5 | The refined member's per-transition step must actually be 2.5 Ma smaller |
| `timestep_refinement_adds_sampling_stages` | `maturation_timestep_refined` | `gt` | `maturation_timestep_coarse` | `simulation_stage_count` | 2.0 | Halving the step must add ≥2 temporal sampling stages over the same horizon |

Relation groupings by theme: water regime (3 relations plus 1 ocean-gain), climate forcing (4), ice response (2), obliquity/seasonality (1), planet scale (2), geodynamic activity (4), isolated maturation response (5), timestep refinement (4). The two `eq` relations at `tolerance: 1e-6` are the only *invariance* gates in the matrix — everything else asserts a signed change.

Each relation result in the report is the relation declaration plus `passed`, `left_value`, `right_value`, `difference`, and `message` — either `"paired scenario response is coherent"` or `"paired scenario response is missing or incoherent"` (`evaluate.py:115-122`).

---

## Determinism rerun and the geo fingerprint

Determinism is opt-in per scenario via `repeat`:

| Aspect | Behavior | Source |
|---|---|---|
| Generation count | `repeat` worlds are generated with the identical resolved config | `evaluate.py:199-206` |
| Fingerprint | each world reduced to `geo_fingerprint(world)` — a hex SHA-256 | `evaluate.py:31-52` |
| Validated world | only the **first** world is validated and metric-extracted | `evaluate.py:198`, `:210-211` |
| `determinism_tested` | `repeat >= 2` | `evaluate.py:215` |
| `deterministic` | `len(set(fingerprints)) == 1` when tested, otherwise `None` (tri-state) | `evaluate.py:216-218` |
| Verdict contribution | `internal_validation_passed` requires `deterministic is not False` — an untested (`None`) scenario is not penalized | `evaluate.py:219-223` |
| Reported | `geo_fingerprint_sha256` (first repeat) and `geo_fingerprint_sha256_by_repeat` (all repeats) | `evaluate.py:250-251` |

`geo_fingerprint` is deliberately a **natural-state-only** projection:

1. Every top-level key in `CIVILIZATION_TOP_LEVEL_FIELDS` (80 names, `_constants.py:30-111`) is dropped from the root.
2. Recursively, every nested dict key in `CIVILIZATION_TOP_LEVEL_FIELDS` **or** `CIVILIZATION_NESTED_FIELDS` (39 cell-level names such as `settlement_id`, `population`, `navigability_index`, `port_site_ids`, `_constants.py:114-154`) is dropped.
3. Non-finite floats are replaced by `{"nonfinite_float": str(value)}` so JSON encoding cannot fail — the encoder runs with `allow_nan=False` (`evaluate.py:51`).
4. The projection is serialized with `json.dumps(..., sort_keys=True, separators=(",", ":"))` and hashed with SHA-256.

Because `sort_keys=True`, key ordering differences do not change the fingerprint; any change to a natural field does. The civilization strip is defense in depth: `generate_geo_world` already removes native civilization outputs, so the strip matters mainly for injected `world_factory` implementations.

In the checked-in matrix exactly one scenario (`earthlike_pair`) sets `repeat: 2`, so `determinism_tested_scenario_count` is 1. Determinism of the other 20 scenarios is **not tested** by this matrix and must not be assumed from the report.

---

## The empirical target bundle

External Earth fit is configured per scenario. Only `earthlike_reference` configures it in the checked-in matrix.

### Scenario-level policy

`_normalize_empirical_calibration` (`empirical.py:682-715`):

| Field | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `target_bundle` | string path | yes | — | Resolved relative to the **matrix file's** directory when not absolute (`empirical.py:700-702`); loaded and fully validated at manifest-load time |
| `require_complete` | bool | no | `true` | Coverage policy: every declared target metric must be observable on the generated world |
| `require_all_passed` | bool | no | `true` | Fit policy: every declared target metric must be inside its range |

Unknown keys are rejected (`empirical.py:692-696`). The policy verdict is
`policy_passed = (complete or not require_complete) and (all_targets_passed or not require_all_passed)` (`evaluate.py:146-149`), where `all_targets_passed = complete and check_count > 0 and pass_count == check_count` (`evaluate.py:143`) — so a bundle whose metrics are all missing can never satisfy `require_all_passed`.

**Coverage and fit are independent verdicts.** A missing world metric scores `0.0`, counts as failed, and is additionally tracked in `external_calibration_missing_metric_count` / `missing_world_metrics`, so "we could not observe it" is never conflated with "we observed it and it was wrong" (`src/magic_geo/calibration/evaluate.py:424-434`, `:469-488`).

Scoring uses `score_range` (`calibration/evaluate.py:14-23`): `1.0` inside the range, otherwise `1 - distance/width` clamped to `[0, 1]`, with `width = max(1e-9, target_max - target_min)`. The score is diagnostic; `passed` is the strict `target_min <= value <= target_max` test.

### Bundle root schema

`_load_empirical_target_bundle` (`empirical.py:495`) accepts exactly these root keys (`empirical.py:505-512`):

| Field | Type | Required | Constraint |
|---|---|---|---|
| `schema_version` | int | yes | Must equal `1` (`EMPIRICAL_TARGET_BUNDLE_SCHEMA_VERSION`, `_constants.py:9`) |
| `name` | string | yes | Non-empty |
| `description` | string | no | Stripped; defaults to `""` |
| `derivation` | object | no | Provenance witnesses; defaults to `{}` |
| `sources` | object | yes | Non-empty map of source id → provenance object |
| `targets` | list | yes | Non-empty list of target objects |

The loader returns `{name, description, path, sha256, source_count, target_count, derivation, targets}` (`empirical.py:670-679`), where `sha256` is over the raw bundle bytes. In the report, `target_bundle` carries everything **except** `targets` (`evaluate.py:150-154`), so the report pins provenance without duplicating the target list.

### Source object

Restricted to 18 keys (`empirical.py:529-548`). `dataset`, `layer`, and `source` are required and must be non-empty strings; every other present key must also be a non-empty string.

| Key | Required | Note |
|---|---|---|
| `dataset` | yes | Human dataset name |
| `layer` | yes | Layer/product identifier within the dataset |
| `source` | yes | Local path or identifier of the pinned artifact |
| `source_format` | no | Reader/derivation format id |
| `source_url` | no | Canonical download URL |
| `source_archive_url` | no | Archive download URL |
| `source_version` | no | Dataset release |
| `source_license` | no | License statement |
| `source_license_url` | no | License URL |
| `source_acquired_on` | no | Acquisition marker |
| `source_citation` | no | Citation text |
| `source_doi` | no | DOI |
| `source_horizontal_crs` | no | Horizontal CRS |
| `source_geographic_coverage` | no | Coverage statement |
| `source_vertical_datum` | no | Vertical datum |
| `source_native_resolution` | no | Native resolution statement |
| `source_sha256` | no | Must be a 64-hex SHA-256; lower-cased (`empirical.py:568-578`) |
| `source_archive_sha256` | no | Same digest rule |

### Target object

Restricted to 14 keys (`empirical.py:584-599`). Each target is **expanded** with its source's full provenance before evaluation (`empirical.py:628-635`), so every check in the report carries dataset/layer/license/digest fields.

| Key | Type | Required | Constraint / meaning |
|---|---|---|---|
| `source_id` | string | yes | Must name a declared source (`empirical.py:613`) |
| `metric` | string | yes | World-side metric name; **unique across the bundle** (`empirical.py:616`) |
| `source_metric` | string | no | Defaults to `metric`; the derivation-side statistic name |
| `source_value` | number | yes | Finite; the derived reference value |
| `target_min` | number | yes | Finite |
| `target_max` | number | yes | Finite; `target_max >= target_min` or the range is rejected as inverted (`empirical.py:626`) |
| `tolerance_basis` | string | no | Free text; copied into the per-target check record (`calibration/evaluate.py:443-447`). The **suite** markdown does not render it — only the `calibrate` and `derive-targets` markdown writers do (`calibration/reports.py:37-38`, `:63-64`) |
| `source_statistic` | string | no | Statistic identifier |
| `source_processing` | string | no | Processing description |
| `source_variable_units` | string | no | Units statement |
| `source_sample_cell_count` | number | no | Numeric (parsed with `_finite`, `empirical.py:646-647`) |
| `source_sample_record_count` | number | no | Numeric |
| `source_sample_neighbor_count` | number | no | Numeric |
| `source_minimum_upstream_area_km2` | number | no | Numeric |

### Derivation witnesses

`_validated_empirical_derivation` (`empirical.py:368`) validates a specific subset of `derivation` and **carries any other keys through unvalidated**:

| Field | Type | Validation |
|---|---|---|
| `runtime_requires_raw_sources` | bool | Must be a boolean when present (`empirical.py:379-383`) |
| `tool` | string | Must be non-empty when present (`empirical.py:384-387`) |
| `source_manifests` | list of `{path, sha256}` | Non-empty; exact field set; unique paths; each artifact is **read from disk and its SHA-256 verified** (`empirical.py:390-452`) |
| `supplemental_target_derivations` | list of `{path, sha256, tool}` | Same rules plus a required `tool`; the bytes are retained for the Seton gate |
| any other key (e.g. `derived_on`) | — | Deep-copied through without validation |

Artifact paths are resolved relative to the **bundle file's** directory when not absolute (`empirical.py:424-426`). A missing artifact raises `... artifact is unavailable: <path>`; a digest mismatch raises `... SHA-256 mismatch: expected <a>, got <b>`. This means loading the matrix touches the filesystem and will fail closed if any witness has drifted.

### The Seton oceanic-age gate

A dedicated, fail-closed gate fires whenever the bundle mentions Seton in any of three ways (`empirical.py:454-491`): `seton_2020_oceanic_age` appears as a source id, **or** any target metric is `initial_oceanic_crust_age_area_weighted_mean_ma` / starts with `initial_oceanic_crust_age_area_weighted_cdf_le_`, **or** any supplemental derivation declares `tool == "scripts/derive_seton_oceanic_age_targets.py"`. When triggered it requires the source id to exist and **exactly one** matching supplemental derivation, then runs `_validate_seton_supplemental_derivation` (`empirical.py:22`), which cross-checks:

| Checked property | Required value / rule | Source |
|---|---|---|
| Artifact root fields | exactly `{schema_version, name, description, derivation, source, statistics}` | `empirical.py:38-49` |
| `schema_version` | `1` | `empirical.py:50` |
| `name` | `seton_2020_oceanic_crust_age_targets_v1` (`SETON_SUPPLEMENTAL_NAME`) | `_constants.py:21`, `empirical.py:52` |
| `derivation.accumulation` | `canonical_file_order_math_fsum_chunks_of_8192` | `empirical.py:71` |
| `derivation.cdf_rule` | `finite_source_age_ma_less_than_or_equal_to_threshold` | `empirical.py:72` |
| `derivation.runtime_requires_raw_sources` | `false` | `empirical.py:73` |
| `derivation.tool` | `scripts/derive_seton_oceanic_age_targets.py`, and must equal the bundle witness record's `tool` | `empirical.py:74`, `:90` |
| `derivation.weighting` | `longitude_endpoint_trapezoid_factor_times_exact_spherical_latitude_band_sine_difference` | `empirical.py:75-78` |
| Source metadata | 14 fields must match the bundle source exactly, and the bundle source's field set must be exactly the mapped set | `empirical.py:122-159` |
| `source_grid_dimensions` | exactly `[1801, 3601]` | `empirical.py:162` |
| `source_total_node_count` | must equal `1801 * 3601` | `empirical.py:170` |
| `source_finite_node_count` | `0 < finite <= total` | `empirical.py:178` |
| Finite age range | `min >= 0` and `max >= min` | `empirical.py:190` |
| `source_variable_units` | `Ma` | `empirical.py:198` |
| `source_processing` | must match a fixed canonical paragraph verbatim | `empirical.py:202-212` |
| `statistics.cdf_thresholds_ma` | integers, unique, exactly `SETON_CDF_THRESHOLDS_MA = (20, 40, …, 200)` | `_constants.py:27`, `empirical.py:236` |
| CDF values | one per threshold, finite, in `[0, 1]`, monotone non-decreasing | `empirical.py:245-261` |
| `area_weighted_mean_age_ma` | within the declared finite source-age range | `empirical.py:266` |
| Bundle Seton targets | exactly the mean metric plus one CDF metric per threshold — no missing, no extra, no duplicates | `empirical.py:271-293` |
| Per-target metadata | `source_metric`, `source_statistic`, `source_processing`, `source_variable_units`, `source_sample_record_count` (must equal the finite node count), and `source_value` (must equal the witnessed statistic exactly) | `empirical.py:295-365` |

This gate is why the checked-in bundle can be evaluated with `runtime_requires_raw_sources: false`: the multi-gigabyte Seton XYZ grid is not opened at validation time, but the derived statistics cannot be edited without breaking either the artifact digest or the semantic cross-check.

### Checked-in bundle: provenance datasets

`configs/geo_validation_earth_empirical_targets.json` declares `name: canonical_earth_empirical_targets_v2`, `schema_version: 1`, **7 sources and 22 targets**, with `derivation.runtime_requires_raw_sources: false` and `derivation.tool: "magic_geo.calibration.derive_calibration_targets plus the listed supplemental derivation"`.

| Source id | Dataset | Layer | `source_format` | Version | License summary |
|---|---|---|---|---|---|
| `natural_earth_110m` | Natural Earth | `ne_110m_land` | `shapefile` | 4.1.0 | Public domain |
| `etopo_2022` | NOAA ETOPO 2022 | `ice_surface_elevation_1deg_stride` | `opendap_ascii_grid` | ETOPO 2022 v1 | NOAA NCEI; not subject to US copyright |
| `worldclim_tavg` | WorldClim 2.1 | `monthly_average_temperature_1970_2000_10m` | `worldclim_geotiff_zip` | WorldClim 2.1 | Academic/non-commercial; redistribution needs permission |
| `worldclim_prec` | WorldClim 2.1 | `monthly_precipitation_1970_2000_10m` | `worldclim_geotiff_zip` | WorldClim 2.1 | Academic/non-commercial; redistribution needs permission |
| `hydrobasins_level3` | HydroBASINS | `standard_pfafstetter_level_3` | `hydrobasins_archive_catalog` | HydroBASINS v1.c | HydroSHEDS license; attribution required |
| `hydrorivers_v10` | HydroRIVERS | `global_exorheic_terminal_backbones_ge_1000000_km2` | `hydrorivers_shapefile_zip` | HydroRIVERS v1.0 | HydroSHEDS license; attribution required |
| `seton_2020_oceanic_age` | Seton et al. 2020 present-day oceanic crustal age | `age.2020.1.GeeK2007.6m.xyz` | `seton_2020_xyz_gridline_age` | release 2020.1, Gee & Kent 2007 timescale | CC BY 4.0 |

Every source carries a `source_sha256`; `natural_earth_110m` additionally carries `source_archive_sha256`. The bundle's `derivation` pins six source-manifest witnesses (`calibration_sources.natural_earth_110m.json`, `.etopo_2022_1deg.json`, `.worldclim_2_1_10m.json`, `.hydrobasins_level3.json`, `.hydrorivers_v10.json`, `.seton_2020_oceanic_age.json`) and one supplemental derivation (`calibration_targets.seton_2020_oceanic_age.json`, tool `scripts/derive_seton_oceanic_age_targets.py`). All seven declared digests match the checked-in files at the time of writing.

### Checked-in bundle: metric inventory

22 targets. `target_min`/`target_max` are reproduced exactly as declared.

| # | World metric | Source | `source_metric` | `source_value` | Target range | Tolerance basis (declared) |
|---:|---|---|---|---:|---|---|
| 1 | `coastal_land_fraction` | `natural_earth_110m` | `fibonacci_4096_coastal_land_fraction` | 0.484033613445 | [0.434033613445, 0.534033613445] | Absolute ±0.05 model-fit tolerance; not a confidence interval |
| 2 | `below_sea_level_surface_fraction` | `etopo_2022` | `fibonacci_ocean_fraction` | 0.708984375 | [0.688984375, 0.728984375] | Absolute ±0.02 |
| 3 | `mean_nonnegative_surface_elevation_m` | `etopo_2022` | `fibonacci_mean_land_elevation_m` | 796.973802769295 | [637.579042215436, 956.368563323154] | ±20 % |
| 4 | `surface_elevation_span_m` | `etopo_2022` | `fibonacci_hypsometric_span_m` | 14354.6447 | [12201.447995, 16507.841405] | ±15 % |
| 5 | `non_antarctic_endorheic_watershed_fraction` | `hydrobasins_level3` | `hydrobasins_endorheic_basin_fraction` | 0.119863013699 | [0.069863013699, 0.169863013699] | ±0.05; generated units are not a Pfafstetter hierarchy |
| 6 | `non_antarctic_endorheic_watershed_area_fraction` | `hydrobasins_level3` | `hydrobasins_endorheic_area_fraction` | 0.174952444749 | [0.094952444749, 0.254952444749] | ±0.08; HydroBASINS lumping and virtual endorheic links remain semantic limitations |
| 7 | `exorheic_watershed_backbone_hack_fitted_exponent` | `hydrorivers_v10` | `hydrorivers_hack_fitted_exponent` | 0.455213509131 | [0.255213509131, 0.655213509131] | Absolute ±0.2; coarse grid resolution is a model-fit limitation |
| 8 | `exorheic_watershed_backbone_hack_fitted_log_rmse` | `hydrorivers_v10` | `hydrorivers_hack_fitted_log_rmse` | 0.155416679619 | [0.0, 0.405416679619] | Physical floor 0 to source RMSE + 0.25 |
| 9 | `mean_land_annual_temperature_c` | `worldclim_tavg` | `fibonacci_mean_land_annual_temperature_c` | 9.365324663961 | [6.365324663961, 12.365324663961] | ±3 °C |
| 10 | `mean_land_annual_temperature_range_c` | `worldclim_tavg` | `fibonacci_mean_land_annual_temperature_range_c` | 19.542444335321 | [15.542444335321, 23.542444335321] | ±4 °C |
| 11 | `mean_land_precipitation_mm_y` | `worldclim_prec` | `fibonacci_mean_land_annual_precipitation_mm` | 774.665594855305 | [580.999196141479, 968.331993569132] | ±25 % |
| 12 | `initial_oceanic_crust_age_area_weighted_mean_ma` | `seton_2020_oceanic_age` | `seton_grid_area_weighted_mean_age_ma` | 62.84149091327 | [47.84149091327, 77.84149091327] | ±15 Ma; explicitly *not* a claim of local age-field agreement |
| 13 | `initial_oceanic_crust_age_area_weighted_cdf_le_20_ma` | `seton_2020_oceanic_age` | `seton_grid_area_weighted_cdf_le_20_ma` | 0.203730125937 | [0.143730125937, 0.263730125937] | ±0.06 distributional |
| 14 | `..._cdf_le_40_ma` | `seton_2020_oceanic_age` | `seton_grid_area_weighted_cdf_le_40_ma` | 0.394644471212 | [0.334644471212, 0.454644471212] | ±0.06 |
| 15 | `..._cdf_le_60_ma` | `seton_2020_oceanic_age` | `seton_grid_area_weighted_cdf_le_60_ma` | 0.538535310804 | [0.478535310804, 0.598535310804] | ±0.06 |
| 16 | `..._cdf_le_80_ma` | `seton_2020_oceanic_age` | `seton_grid_area_weighted_cdf_le_80_ma` | 0.668168555856 | [0.608168555856, 0.728168555856] | ±0.06 |
| 17 | `..._cdf_le_100_ma` | `seton_2020_oceanic_age` | `seton_grid_area_weighted_cdf_le_100_ma` | 0.764912127566 | [0.704912127566, 0.824912127566] | ±0.06 |
| 18 | `..._cdf_le_120_ma` | `seton_2020_oceanic_age` | `seton_grid_area_weighted_cdf_le_120_ma` | 0.867648508307 | [0.807648508307, 0.927648508307] | ±0.06 |
| 19 | `..._cdf_le_140_ma` | `seton_2020_oceanic_age` | `seton_grid_area_weighted_cdf_le_140_ma` | 0.934848912501 | [0.874848912501, 0.994848912501] | ±0.06 |
| 20 | `..._cdf_le_160_ma` | `seton_2020_oceanic_age` | `seton_grid_area_weighted_cdf_le_160_ma` | 0.977598316798 | [0.917598316798, 1.0] | ±0.06 clipped to the physical fraction range |
| 21 | `..._cdf_le_180_ma` | `seton_2020_oceanic_age` | `seton_grid_area_weighted_cdf_le_180_ma` | 0.994407372837 | [0.934407372837, 1.0] | ±0.06 clipped |
| 22 | `..._cdf_le_200_ma` | `seton_2020_oceanic_age` | `seton_grid_area_weighted_cdf_le_200_ma` | 0.999362742267 | [0.939362742267, 1.0] | ±0.06 clipped |

Two things to read carefully in this table. First, all 22 `tolerance_basis` strings in the bundle contain the clause *"not a statistical confidence interval"* — these are declared model-fit envelopes chosen by the repository, not derived uncertainty. (Target 12 goes further and adds *"and not a claim of local age-field agreement"*.) Second, target 11 declares `source_variable_units: "millimeters per month"` while its `source_processing` says monthly precipitation is *summed* per cell and the world metric is `mean_land_precipitation_mm_y`; the units string is reproduced verbatim from the source file and the discrepancy is not resolved in the bundle.

The world-side observables for these metrics are produced by `magic_geo.calibration.evaluate._world_metric_values` from `world["calibration_checks"]` plus cell-derived quantities — a different surface from `extract_geo_metrics`, which supplies scenario expectations and relations. See [Calibration Against Real-Earth Data](./14-calibration.md).

---

## Suite report JSON structure

Report type `geo_pipeline_validation_suite_v1`, schema version 1 (`evaluate.py:313-383`).

### Root

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | int | `1` |
| `report_type` | string | `"geo_pipeline_validation_suite_v1"` |
| `name` | string | The manifest `name` |
| `scope` | string | `GEO_VALIDATION_SCOPE` — the declared natural-system scope (`geo_validation.py:22`) |
| `excluded_scope` | string | `"civilization and all settlement, political, cultural, historical, demographic, economic, market, campaign, and language layers"` |
| `model_limitations` | list of 12 strings | `GEO_MODEL_LIMITATIONS` verbatim (`geo_validation.py:28-41`) |
| `passed` | bool | `all members passed AND all relations passed` (`evaluate.py:312`) |
| `summary` | object | See below |
| `empirical_calibration` | object | `{scope, configured_scenario_ids, failed_checks}` — `failed_checks` are per-scenario-tagged failing target checks |
| `members` | list | One per scenario, in matrix order |
| `relations` | list | One per relation, in matrix order |

### `summary`

| Field | Type | Meaning |
|---|---|---|
| `scenario_count` | int | Number of members |
| `scenario_pass_count` | int | Members with `passed == true` |
| `scenario_pass_fraction` | float | Rounded to 6 dp |
| `internal_scenario_pass_count` | int | Members with `internal_validation_passed == true` |
| `internal_scenario_pass_fraction` | float | Rounded to 6 dp |
| `relation_count` | int | Number of relations |
| `relation_pass_count` | int | Passing relations |
| `relation_pass_fraction` | float \| null | `null` when there are no relations |
| `response_validation_performed` | bool | Whether any relation ran |
| `determinism_tested_scenario_count` | int | Members with `repeat >= 2` |
| `deterministic_scenario_count` | int | Members with `deterministic is True` |
| `empirical_calibration_scenario_count` | int | Members that configured a bundle |
| `empirical_calibration_policy_pass_count` | int | Members whose bundle policy passed |
| `empirical_calibration_check_count` | int | Total target checks across configured members |
| `empirical_calibration_evaluated_metric_count` | int | Target checks whose world metric was observable |
| `empirical_calibration_pass_count` | int | Target checks in range |
| `empirical_calibration_missing_metric_count` | int | Target checks whose world metric was missing |
| `empirical_calibration_metric_coverage_fraction` | float \| null | evaluated / checks; `null` when no checks |
| `empirical_calibration_pass_fraction` | float \| null | passes / checks |
| `empirical_calibration_evaluated_pass_fraction` | float \| null | passes / evaluated |
| `all_internal_scenarios_passed` | bool | — |
| `all_empirical_calibrations_passed` | bool \| null | `null` when no member configured a bundle (tri-state) |
| `all_scenarios_passed` | bool | — |
| `all_relations_passed` | bool \| null | `null` when there are no relations (tri-state) |

The `null` tri-states are deliberate: "not configured" is reported as absence of evidence, never as a pass.

### Member record

| Field | Type | Meaning |
|---|---|---|
| `id`, `description`, `profile`, `tags`, `repeat` | — | Echoed from the normalized scenario |
| `passed` | bool | `internal_validation_passed and empirical_calibration_passed is not False` (`evaluate.py:232`) |
| `internal_validation_passed` | bool | `validation.passed` AND all expectation checks pass AND `deterministic is not False` (`evaluate.py:219`) |
| `empirical_calibration_configured` | bool | Whether a bundle was declared |
| `empirical_calibration_passed` | bool \| null | `null` when not configured |
| `empirical_calibration` | object \| null | Policy, coverage, full evaluation, and `failed_checks` |
| `determinism_tested` | bool | `repeat >= 2` |
| `deterministic` | bool \| null | `null` when not tested |
| `geo_fingerprint_sha256` | string | Fingerprint of the first repeat |
| `geo_fingerprint_sha256_by_repeat` | list of strings | One per repeat |
| `config` | object | The **fully resolved** config dumped with `mode="json"` — the exact configuration that generated the member |
| `metrics` | object | `extract_geo_metrics(first_world)` |
| `validation_summary` | object | The single-world report `summary`, including `check_count`, `passed_count`, `error_failure_count`, `warning_failure_count`, `not_applicable_count`, per-domain counts, and the four layer-contract counters (`geo_validation.py:2771-2780`) |
| `validation_failures` | list | Checks with `status == "failed"` and `severity == "error"` |
| `realism_deviations` | list | Checks with `status == "failed"` and `severity == "warning"` (the `realism_evidence` domain) |
| `not_applicable_realism_checks` | list of strings | Names of `realism_evidence` checks reported `not_applicable` |
| `expectation_checks` | list | `{id, scenario_id, metric, passed, observed, expected, message}` per declared expectation |

Note what the member does **not** carry: the full `checks` array and the full `layer_contracts` object from the single-world report are not embedded — only the summary plus the failing/warning subsets. For a complete per-check dump of one world, run `validate-geo --output` on that world separately.

### Empirical block (per member)

| Field | Meaning |
|---|---|
| `target_bundle` | Loaded bundle provenance minus `targets`: `name`, `description`, `path`, `sha256`, `source_count`, `target_count`, `derivation` |
| `policy` | `{require_complete, require_all_passed}` |
| `policy_passed` | The combined policy verdict |
| `coverage_complete` | `external_calibration_complete` from the calibration summary |
| `all_targets_passed` | `complete and check_count > 0 and pass_count == check_count` |
| `summary` | The 10-field calibration summary (`calibration/evaluate.py:470-485`) |
| `available_world_metrics` / `missing_world_metrics` | Sorted metric-name lists |
| `checks` | Per-target records: `id`, `dataset`, `layer`, `metric`, `source_metric`, `value`, `target_min`, `target_max`, `score`, `passed`, `missing_metric`, `source`, plus expanded `source_*` provenance and `tolerance_basis` |
| `failed_checks` | The subset of `checks` with `passed == false` |

A `CalibrationError` raised while evaluating a bundle is re-raised as `GeoValidationSuiteError` naming the scenario: `scenario '<id>' external empirical calibration failed: <detail>` (`evaluate.py:136-138`) — which the CLI turns into exit 2, not a soft failure.

---

## Markdown summary structure

Written by `write_geo_validation_suite_markdown` (`src/magic_geo/geo_validation_suite/report.py:9`) only when `--summary` is given. The document is fixed-order:

| Order | Section | Content | Source |
|---:|---|---|---|
| 1 | `# Geo Pipeline Validation: <name>` | H1 with the manifest name | `report.py:12` |
| 2 | Verdict block | `Overall verdict: **PASS/FAIL**`; declared scope; declared excluded scope; scenario counts; internal-gate counts; the external-calibration line (or `not configured`); paired-response counts (or `not run`) | `report.py:14-42` |
| 3 | `## Declared Model Limitations` | One bullet per `model_limitations` entry (12 in the checked-in build) | `report.py:44-46` |
| 4 | `## Scenario Results` | 13-column table: Scenario, Profile, Verdict, Internal gates, External empirical fit, Cells, Ocean, Temperature, Land precipitation, Evidence coverage, Internal diagnostic fit, Deviations, Determinism | `report.py:50-85` |
| 5 | `## External Empirical Calibration` | Only when at least one member configured a bundle. Per member: an H3, the bundle name and SHA-256, coverage `n/m`, fit `n/m`, policy PASS/FAIL, then a `Dataset / Metric / Observed / Target range / Score / Status` table with `MISSING` as a distinct status | `report.py:91-131` |
| 6 | `## Paired Physical Responses` | `Relation / Metric / Comparison / Difference / Verdict` table; comparison rendered as `left <op> right` | `report.py:132-148` |
| 7 | `## Internal Validation and Response Failures` | Only when something failed. Bullets for `scenario / domain.name: message`, for failed expectations with observed vs expected, and for failed relations with both values and the minimum difference | `report.py:149-172` |
| 8 | `## External Empirical Calibration Failures` | Only when non-empty. Bullets `scenario / dataset / metric: observed …, expected [min, max]` | `report.py:173-183` |
| 9 | `## Nonfatal Realism Deviations` | Only when non-empty. Bullets `scenario / name: observed …, expected …` — explicitly labelled non-fatal | `report.py:184-195` |

The Determinism column reads `not tested` when `determinism_tested` is false, so an untested scenario is never rendered as a determinism pass (`report.py:79-83`). The scenario table's `Internal diagnostic fit` column is `calibration_pass_fraction` — the **built-in 12-metric** internal comparison set (`CALIBRATION_EXPECTED_METRICS`, `geo_validation.py:43-58`), not the external bundle; the two are distinct verdicts sharing similar vocabulary.

---

## Adding a new scenario or relation

### A new scenario

1. **Pick an id and a profile.** Ids must be unique. Use `earthlike` only if the world is genuinely meant to satisfy the Earth-regime bands listed above; otherwise leave it at `generic` or the profile gates will fire spuriously.
2. **Write `overrides` against real config keys.** Every key must already exist in the base `WorldConfig` dump, and dict-vs-scalar shape must match. Consult [Configuration Reference](./05-configuration-reference.md). Keep `output.include_cells` true — the suite refuses the scenario otherwise (`evaluate.py:189`).
3. **Keep the run cheap.** Existing scenarios use 512 cells (128 for the timestep pair) precisely because each scenario is a full generation.
4. **Declare `expectations` only for metrics in `extract_geo_metrics`.** An unknown metric name silently becomes a failing check, not an error — verify names against `geo_validation.py:445-554`.
5. **Set `repeat: 2` (or 3) only if you want a determinism rerun**, remembering it multiplies generation cost.
6. **Add `empirical_calibration` only if the scenario is meant to be Earth-comparable.** The bundle path is relative to the matrix file, and loading it verifies every declared witness digest on disk.
7. **Validate by loading the matrix** before committing to a full run:

```bash
python -c "
from pathlib import Path
from magic_geo.geo_validation_suite import load_geo_validation_manifest
m = load_geo_validation_manifest(Path('configs/geo_validation_matrix.yaml'))
print(m['name'], len(m['scenarios']), 'scenarios', len(m['relations']), 'relations')
"
```

Any schema violation raises `GeoValidationSuiteError` with a message naming the scenario index or id.

### A new relation

1. **Both `left` and `right` must be declared scenarios and must differ.** Relations are validated after all scenarios are parsed, so ordering in the file does not matter.
2. **Choose the metric from `extract_geo_metrics`.** A metric present in only one member's map fails the relation rather than skipping it.
3. **Choose the operator deliberately.** `lt`/`gt` require strict inequality *plus* the margin; `le`/`ge` require only the margin. Use `eq` for invariance gates and give it an explicit `tolerance` — `minimum_difference` must then be 0.
4. **Set `minimum_difference` in metric units.** It is the physical magnitude you are willing to assert. Setting it to 0 with `lt`/`gt` degrades the relation to a bare sign test.
5. **Prefer a controlled pair.** The strongest relations in the checked-in matrix (`maturation_initial` vs `maturation_evolved`, `low_obliquity` vs `high_obliquity`, `maturation_timestep_coarse` vs `_refined`) change exactly one config knob, so the observed response is attributable.
6. **Beware the shared control.** Twelve of the 26 relations use `earthlike_pair` as `right`; changing that scenario's overrides shifts the reference point of all of them at once.

A single failing relation fails the whole report (`evaluate.py:312`) and produces exit 1, even if every scenario member passed.

---

## Documented pass/fail state and known Earth-fit gaps

The repository documents the state of the checked-in matrix in `README.md:234` and `docs/geo_generation_maturation_deep_audit.md:100-146`. This is a **recorded run**, not something re-measured by this page; the numbers below are quoted from those documents, and re-running the suite on different hardware, a different build, or a different base config can change them.

| Gate | Recorded result | Repository's interpretation |
|---|---|---|
| Scenario policies (internal and overall) | 19/21 PASS | Two members fail; see below |
| Layer contracts | 294/294 PASS | 14 contracts × 21 members; contract integrity, not empirical realism |
| Paired relations | 26/26 PASS | Water, climate, ice, planet scale, tectonic motion, erosion, isolated maturation, and nominal-timestep relations all show the required direction and magnitude |
| Determinism | 1/1 PASS | The one configured repeated scenario reproduced its fingerprint |
| Core validation aggregate | 3,029 pass, 1 fatal error, 7 warning deviations, 79 not applicable (3,116 total) | — |
| External metric coverage | 22/22 | No reference metric is silently missing |
| External metric fit | 17/22 FAIL | Five metrics outside their declared intervals; recorded as an explicit release blocker |

The two failing members:

| Member | Why it fails | Note |
|---|---|---|
| `earth_seed_3` | The sole fatal core-validation error: `ocean_fraction = 0.542985`, below the `earthlike` profile floor of `0.55` | A broad Earth-regime envelope violation, not a conservation or replay failure |
| `earthlike_reference` | **Zero** core validation failures. It fails its declared scenario expectation because the built-in 12-check `calibration_pass_fraction = 0.916667` is below the required `1.0`; separately, its external empirical policy is not all-pass | Two distinct verdicts happen to fail on the same member |

The five failing external metrics, as tabulated in `docs/geo_generation_maturation_deep_audit.md:138-144`:

| Failed metric | Observed | Accepted interval | Gap to nearest bound |
|---|---:|---|---|
| Natural Earth `coastal_land_fraction` | 0.350600 | 0.434034–0.534034 | 0.083434 low |
| ETOPO `below_sea_level_surface_fraction` | 0.610596 | 0.688984–0.728984 | 0.078389 low |
| ETOPO `mean_nonnegative_surface_elevation_m` | 1191.352558 | 637.579042–956.368563 | 234.983995 high |
| ETOPO `surface_elevation_span_m` | 17443.550463 | 12201.447995–16507.841405 | 935.709058 high |
| HydroBASINS `non_antarctic_endorheic_watershed_area_fraction` | 0.274942 | 0.094952–0.254952 | 0.019990 high |

The seventeen passing metrics are the HydroBASINS terminal-basin count fraction, both source-matched HydroRIVERS metrics, all three WorldClim metrics, and all eleven Seton mean/CDF metrics.

Read honestly, this says: the generated Earth-like reference is **too continental and too rugged** relative to Earth — less ocean area, less coastline, higher mean land elevation, a wider hypsometric span — while its climate fields, its river-network scaling exponent, and its initial oceanic-age distribution land inside their declared envelopes. The repository states this directly: *"Internal closure and replay therefore do not substitute for the remaining Earth-fit gaps"* (`README.md:234`), and, on whether Earth realism is demonstrated, *"No"* (`docs/geo_generation_maturation_deep_audit.md:22`).

Three further caveats the repository attaches to these numbers, carried forward unchanged:

- **One member is not validation.** *"one canonical member is not held-out or scale-independent validation"* (`deep_audit.md:22`). The passing 17/22 is seed- and resolution-specific evidence at 4,096 cells and seed 424242, not a generator-wide calibration claim.
- **The historical ensemble is not comparable.** The ten-member `calibrate-ensemble` matrix predates the expanded, semantically corrected 22-metric bundle and *"must not be compared as though it used the same 22-metric bundle"* (`README.md:473`).
- **A stated done-condition is unmet.** One of the audit's exit criteria is *"The 22/22 external Earth metrics pass on held-out seed/resolution ensembles, not just the canonical member"* (`deep_audit.md:518`) — currently unsatisfied on both counts.

---

## Limitations and unresolved claims

- **The suite proves declared contracts and declared responses, not physics.** A passing relation shows the model moved in the asserted direction by at least the asserted margin. It says nothing about whether the magnitude is physically correct, and the margins were chosen by the repository, not derived.
- **Earth realism is explicitly not demonstrated.** External fit is a separate verdict by design (`geo_validation.py:40`), it currently fails 5/22, and the repository's own answer to "is Earth realism demonstrated?" is "No".
- **Determinism is tested for one scenario only.** `determinism_tested_scenario_count` is 1 in the checked-in matrix. Determinism of the other 20 scenarios, of other backends, and of accelerator paths is not evidenced here. See [Compute Backends](./09-compute-backends.md) — accelerator parity is separately declared unresolved.
- **The nominal clock is not physical time.** `nominal_maturation_duration_ma`, `maturation_timestep_ma`, and `maturation_timestep_scale` are procedural bookkeeping. The declared limitation is that *"the simulation clock orders procedural stages but has no calibrated physical duration"*; the timestep relations therefore assert nominal self-consistency only.
- **All 12 `GEO_MODEL_LIMITATIONS` propagate into every suite report** (`evaluate.py:319`), including the unresolved subduction polarity and mass-provenance statements: the pair-wide overlap candidate crosswalk *"does not resolve a local fragment-to-segment link, physical polarity, allocation, material fate, slab transfer, or state mutation"*; the crust dry-rock reservoirs *"remain non-authoritative and do not resolve physical transfer bases, fate, solid volume, phase, mantle, slab, sediment coupling, or a physical global crust cycle"*; initial oceanic crust age *"does not reconstruct local flowlines, calibrated spreading, subduction sinks, convergence history, or physical seafloor creation and destruction"*. Passing the suite does not weaken any of these.
- **Layer contracts are not realism claims.** Every layer hardcodes `empirical_realism_proven: False`; the 294/294 figure is 14 structural contracts per member, not 294 physical validations.
- **Realism warnings never change a verdict inside the suite.** Unlike `validate-geo`, the suite has no `--fail-on-warnings`; `realism_deviations` are reported and ignored by the pass logic.
- **Only the first repeat is validated.** For `repeat >= 2`, checks, metrics, expectations, relations and empirical fit all come from repeat 0; the other repeats contribute only their fingerprints.
- **Members do not carry full check arrays.** `validation_failures` and `realism_deviations` are subsets; a complete per-check audit requires a separate `validate-geo --output` run on the specific world.
- **Bundle `derivation` is only partially closed.** Unknown keys inside `derivation` pass through unvalidated (`empirical.py:378`), unlike the manifest, source, and target objects, which reject unknown fields.
- **Bundle loading touches the filesystem.** Declared witness artifacts are read and hashed at manifest-load time, so a matrix that references a bundle is not portable without those artifacts, even though `runtime_requires_raw_sources: false` keeps the multi-gigabyte raw datasets out of the loop.
- **The `tolerance_basis` strings are declared engineering envelopes.** Every one of the 22 targets states in its own words that it is *not a statistical confidence interval*.
- **Coverage is not fit.** A metric can be missing (score 0, failed, counted as missing) or present-and-wrong; the report keeps these separate, and `require_complete` / `require_all_passed` gate them independently.
- **Recorded pass/fail figures are historical to a specific run.** They are reproduced here from `README.md` and `docs/geo_generation_maturation_deep_audit.md`; this page does not re-measure them.

---

## See also

- [Validation](./12-validation.md) — the single-world `validate-geo` and `validate` gates, check-record shape, realism evidence, and layer contracts
- [Calibration Against Real-Earth Data](./14-calibration.md) — `derive-targets`, `calibrate`, `calibrate-ensemble`, readers, samplers, and the world-side metric surface
- [CLI Reference](./06-cli-reference.md) — every command, flag, default, and exit code
- [Configuration Reference](./05-configuration-reference.md) — the `WorldConfig` keys that scenario `overrides` must address
- [Python API](./07-python-api.md) — `generate_geo_world`, `evaluate_geo_validation_suite`, and the manifest loader
- [Testing and Quality Gates](./18-testing.md) — where the suite sits among the Python and native test tiers
- [Web Workbench](./15-web-workbench.md) — running the suite as a browser job
- [Architecture](./04-architecture.md) — the pipeline the scenarios exercise
- [Tectonics and Plates](./features/tectonics-and-plates.md) — the plate-motion and rotation metrics used by the geodynamic relations
- [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) — the crust-evolution and plate-reassignment metrics used by the maturation relations
- [Climate and Atmosphere](./features/climate-and-atmosphere.md) — the temperature, precipitation and seasonality metrics used by the climate relations
- [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) — the maturation iteration/timestep semantics behind the refinement gates
- [Oceans, Currents and Coasts](./features/oceans-and-coasts.md) — ocean fraction and coastal-land-fraction context for the failing Earth-fit metrics
- [Glossary](./21-glossary.md) — terms used across these reports
