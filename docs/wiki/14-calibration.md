# Calibration Against Real-Earth Data

[Wiki home](./README.md) > Calibration

External calibration is the one subsystem in magic-geo that compares a generated world against measurements of the real Earth; the geo-validation suite does not reimplement it, it imports the same scorer (`evaluate_calibration_targets`) for its empirical bundle (`src/magic_geo/geo_validation_suite/evaluate.py:14`, `:134`). The command-line workflow here is deliberately split in three: `derive-targets` reads checksum-pinned reference datasets and emits numeric target ranges, `calibrate` scores one generated world against a target bundle, and `calibrate-ensemble` sweeps a seed x mesh-resolution matrix and aggregates the same scoring across members. Everything in this page is *external* fit: it is a separate verdict from internal contract integrity, replay closure, and layer contracts, and the repository states that explicitly (`src/magic_geo/geo_validation.py:40` — "Earth empirical fit remains a separate calibration verdict from internal contract integrity"). Every tolerance shipped in this repository is declared as a model-fit tolerance, never as a statistical confidence interval.

## On this page

- [Concept and scope](#concept-and-scope)
- [The three commands and how they chain](#the-three-commands-and-how-they-chain)
- [Source-config schema (`derive-targets` input)](#source-config-schema-derive-targets-input)
- [Supported datasets, fetch scripts and provenance](#supported-datasets-fetch-scripts-and-provenance)
- [The pipeline module by module](#the-pipeline-module-by-module)
- [Target bundle schemas](#target-bundle-schemas)
- [World-side metrics: definition, units, tolerance model](#world-side-metrics-definition-units-tolerance-model)
- [The built-in 12-check native calibration set](#the-built-in-12-check-native-calibration-set)
- [Coverage versus fit and the policy flags](#coverage-versus-fit-and-the-policy-flags)
- [Calibration report schema](#calibration-report-schema)
- [`calibrate-ensemble`](#calibrate-ensemble)
- [Worked end-to-end example](#worked-end-to-end-example)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

## Concept and scope

The calibration package answers one question: *given a numeric range derived from a real Earth dataset, does the corresponding observable of a generated world fall inside it, and if not, how far outside?*

Three ideas structure the whole subsystem.

1. **Targets are derived, not asserted.** A target range is produced by running a declared statistic over a checksum-pinned local file. `derive_calibration_targets` re-hashes the file at derivation time and refuses to proceed on a SHA-256 mismatch (`src/magic_geo/calibration/_helpers.py:94-126`). The tolerance that widens the derived value into a range is a declared policy field, carried forward verbatim as `tolerance_basis` text into the target, into every check, and into both Markdown reports.
2. **Scale matching is explicit.** Most real datasets are far finer than a 4,096-cell world. Rather than resampling the world up, the reference dataset is sampled *down* onto the same Fibonacci sphere the generator uses (`_fibonacci_points`, `src/magic_geo/calibration/_helpers.py:265-275`), so the two sides of the comparison see comparable spatial support. The sampling mesh identity is recorded as `source_sampling_mesh: fibonacci_sphere_v1`.
3. **Coverage and fit are independent verdicts.** A metric the world does not expose scores `0.0` and counts as failed, but it is also tracked separately as a *missing* metric, and the CLI exposes two orthogonal gates for the two failure modes.

Errors are a single type, `CalibrationError(ValueError)` (`src/magic_geo/calibration/errors.py:6-7`), and the package is strictly layered so imports only point downwards: `errors -> _helpers -> readers -> sampling -> derive`, with `evaluate` and `reports` independent (`src/magic_geo/calibration/__init__.py:4-5`).

What calibration is **not**: it is not a validation gate on internal consistency (that is [Validation](./12-validation.md) and the [Geo Validation Suite](./13-geo-validation-suite.md)), it is not a claim that any generated field is physically correct, and it never re-derives the world. It reads a serialized world document and a JSON target list.

## The three commands and how they chain

All three commands live in `src/magic_geo/cli/commands/calibrate.py`.

| Command | Defined at | Reads | Writes | Chain position |
| --- | --- | --- | --- | --- |
| `derive-targets` | `calibrate.py:202-233` | a source manifest (`--sources`) plus the local dataset files it names | derived target bundle JSON (`--output`, default `runs/calibration_targets.json`), optional Markdown (`--summary`) | 1. Turns raw datasets into target ranges. Requires the raw data locally. |
| `calibrate` | `calibrate.py:32-91` | a generated world (`--world`) and a target bundle (`--targets`) | calibration report JSON (`--output`, default `runs/calibration.json`), optional Markdown | 2. Scores one world. Does **not** need the raw datasets. |
| `calibrate-ensemble` | `calibrate.py:94-199` | a base YAML config (`--config`), a member matrix (`--matrix`), one or more target bundles (repeatable `--targets`) | ensemble report JSON (`--output`, default `runs/calibration_ensemble.json`), optional Markdown | 3. Generates N worlds itself and applies step 2 to each. |

The chain is: fetch script -> `derive-targets` -> target bundle JSON -> (`calibrate` on one world) or (`calibrate-ensemble` over a matrix). The derived bundle is the hand-off artifact; because it embeds `source_value`, `target_min`, `target_max` and full provenance, downstream scoring never opens the raw dataset again. The checked-in Earth bundle records this explicitly as `derivation.runtime_requires_raw_sources: false` (`configs/geo_validation_earth_empirical_targets.json`).

Full option tables for all three commands are in the [CLI Reference](./06-cli-reference.md). The calibration-specific behaviours are:

| Flag | Command | Default | Effect |
| --- | --- | --- | --- |
| `--sources` / `-s` | `derive-targets` | required | JSON source manifest; `path`, `dbf_path`, `prj_path` inside it resolve relative to the manifest file (`src/magic_geo/calibration/sources.py:16-39`). |
| `--targets` / `-t` | `calibrate` | required, single | Target bundle JSON. |
| `--targets` / `-t` | `calibrate-ensemble` | required, repeatable | Multiple bundles are concatenated; duplicate `metric` values across bundles are rejected (`src/magic_geo/ensemble_calibration.py:106-107`). |
| `--matrix` / `-m` | `calibrate-ensemble` | required | Ensemble member manifest, SHA-256 pinned into the report (`calibrate.py:169`). |
| `--summary` | all three | `None` | Markdown twin of the JSON report. |
| `--require-all-metrics` / `--allow-missing-metrics` | `calibrate`, `calibrate-ensemble` | `False` | Coverage gate. |
| `--require-all-passed` / `--allow-fit-failures` | `calibrate`, `calibrate-ensemble` | `False` | Fit gate. |

Exit codes: `2` for a malformed manifest/bundle (`CalibrationError` or `json.JSONDecodeError`, `calibrate.py:67-69`, `:174-176`, `:221-223`) and for the shared world loader (`src/magic_geo/cli/_app.py:16-23`); `calibrate-ensemble` additionally maps pydantic `ValidationError` and any other `ValueError` — a bad base config or a member config that fails re-validation — to `2` (`calibrate.py:174`). Exit `1` is only for a policy failure, always **after** the report has been written (`calibrate.py:71`, `:81-91`).

## Source-config schema (`derive-targets` input)

A source manifest is a JSON object with an optional free-text `description` and a `sources` list; a bare JSON list is also accepted (`src/magic_geo/calibration/_helpers.py:29-37`). Each entry is one derived target. `load_calibration_sources` resolves the three path-valued fields relative to the manifest's own directory before handing the list to `derive_calibration_targets` (`src/magic_geo/calibration/sources.py:16-39`).

### Core fields

| Field | Type | Required | Default | Meaning / source |
| --- | --- | --- | --- | --- |
| `dataset` | non-empty string | yes | — | Free-text dataset name, copied to the target and to every check (`derive.py:69`). |
| `layer` | non-empty string | yes | — | Free-text layer name within the dataset (`derive.py:70`). |
| `metric` | non-empty string | yes | — | Source-side metric name; becomes `source_metric` on the target (`derive.py:71`). |
| `world_metric` | non-empty string | no | falls back to `metric` | The world observable this target is scored against; becomes `metric` on the target (`derive.py:72`). |
| `path` | non-empty string | yes | — | Dataset file; must exist or `CalibrationError` (`derive.py:73-75`). Resolved relative to the manifest. |
| `format` | string | no | inferred from suffix | Lower-cased. Suffix inference: `.asc`/`.ascii` -> `esri_ascii_grid`, `.geojson`/`.json` -> `geojson`, `.shp` -> `shapefile`; anything else raises (`derive.py:24-35`). |
| `statistic` | string | no | `mean` | Lower-cased; selects the reader/sampler branch (see the dispatch table below) (`derive.py:77`). |

### Statistic-specific fields

| Field | Type | Required for | Default | Meaning / source |
| --- | --- | --- | --- | --- |
| `property` | string | GeoJSON with a non-`feature_count` statistic; optional for shapefiles | — | Numeric attribute to read. For shapefiles it switches reading to the DBF (`readers.py:420-425`) and is echoed as `source_property`, plus `source_dbf` (`derive.py:184-187`). |
| `dbf_path` | string | no | the shapefile path with its suffix replaced by `.dbf` (`Path.with_suffix`) | Explicit DBF sidecar (`readers.py:207-211`). |
| `geometry_metric` | string | no | `length_km` | Shapefile geometry reduction; accepted values `length_km`, `area_km2`, `point_count`, `part_count`, with aliases `length`, `total_length_km`, `area`, `total_area_km2`, `points`, `parts` (`readers.py:429-440`). Echoed as `source_geometry_metric`. |
| `coordinate_system` | string | no | inferred | Vector CRS override; normalized to `geographic` or `projected_m` through explicit alias sets (`_helpers.py:352-400`). |
| `prj_path` | string | no | the shapefile path with its suffix replaced by `.prj` (`_helpers.py:431-435`) | Explicit `.prj`; if declared and missing, that is an error (`_helpers.py:453-454`). If absent and no `.prj` exists, `geographic` is assumed (`_helpers.py:455`). |
| `variable` | string | OPeNDAP and WorldClim branches | `z` (relief), `prec`/`tavg` (WorldClim) | OPeNDAP grid variable must match `[A-Za-z_][A-Za-z0-9_]*` (`readers.py:451`). WorldClim variable must equal the one implied by the statistic (`sampling.py:143-150`). |
| `fill_value` | float | no | `-99999.0` | OPeNDAP relief fill sentinel; hitting it at a sampled Fibonacci point is an error (`sampling.py:89`, `:95-96`). |
| `value_scale` | float | no | `1.0` | WorldClim linear rescale (`sampling.py:151`). |
| `value_offset` | float | no | `0.0` | WorldClim linear offset (`sampling.py:152`). |
| `sample_cell_count` | int | no | `4096` | Fibonacci sample points; minimum 128 (`sampling.py:18-21`, `:81-83`, `:140-142`). |
| `sample_neighbor_count` | int | no | `7` | Coastal statistic only; must be >= 4 and < `sample_cell_count` (`sampling.py:22-25`). |
| `minimum_upstream_area_km2` | float | HydroRIVERS branch | `HACK_FIT_MINIMUM_BASIN_AREA_KM2` = `1000000.0` | Must equal that constant within `1e-4` or derivation raises (`derive.py:113-122`, `src/magic_geo/scaling.py:8`). |

### Tolerance fields

| Field | Type | Required | Default | Meaning / source |
| --- | --- | --- | --- | --- |
| `target_min` + `target_max` | float, float | no (both or neither) | — | Explicit range; wins over every tolerance field (`derive.py:152-154`). |
| `tolerance_abs` | float | no | — | Absolute half-width. If `tolerance_fraction` is also present, the effective tolerance is `max(tolerance_abs, abs(value) * tolerance_fraction)` (`derive.py:156-159`). |
| `tolerance_fraction` | float | no | `0.05` when `tolerance_abs` is absent | Relative half-width (`derive.py:160-161`). The 5 % default applies only when neither explicit bounds nor `tolerance_abs` are given. |
| `tolerance_basis` | non-empty string | no | — | Free text describing what the tolerance means. Carried into the target, into checks, and into both Markdown reports (`derive.py:190-191`, `evaluate.py:443-447`, `reports.py:37-38`, `:63-64`). |

Range construction is `value +/- tolerance`, then `value`, `target_min`, `target_max` are all rounded to 12 decimals; an inverted range or a non-finite derived value raises (`derive.py:149-169`).

### Provenance fields

Fifteen optional string fields are recognised as provenance and copied verbatim (`_SOURCE_PROVENANCE_FIELDS`, `src/magic_geo/calibration/_constants.py:43-59`): `source_url`, `source_archive_url`, `source_version`, `source_license`, `source_license_url`, `source_acquired_on`, `source_citation`, `source_doi`, `source_horizontal_crs`, `source_geographic_coverage`, `source_vertical_datum`, `source_native_resolution`, `source_processing`, `source_temporal_coverage`, `source_variable_units`. Each must be a non-empty string. `source_acquired_on` must parse as ISO `YYYY-MM-DD` (`_helpers.py:112-117`).

Two digest fields are validated separately (`_helpers.py:96-125`):

| Field | Validation |
| --- | --- |
| `source_sha256` | Must match `^[0-9a-fA-F]{64}$` and must equal the actual SHA-256 of `path`; otherwise the derivation aborts. |
| `source_archive_sha256` | Must match the same pattern; lower-cased and recorded, but not itself verified against a file by `derive.py`. |

The actual file digest is always computed and emitted as `source_sha256` on the target, whether or not the manifest declared one.

### Statistic dispatch

| `statistic` | Required `format` (accepted aliases) | Normalised `source_format` | Implementation |
| --- | --- | --- | --- |
| `fibonacci_coastal_land_fraction` | `shapefile`, `esri_shapefile`, `shp` | `shapefile` | `sampling.py:14-73` |
| `fibonacci_ocean_fraction`, `fibonacci_mean_land_elevation_m`, `fibonacci_hypsometric_span_m` | `opendap_ascii_grid`, `opendap_ascii`, `dap_ascii` | `opendap_ascii_grid` | `sampling.py:76-132` |
| `fibonacci_mean_land_annual_temperature_c`, `fibonacci_mean_land_annual_temperature_range_c`, `fibonacci_mean_land_annual_precipitation_mm` | `worldclim_geotiff_zip`, `geotiff_zip` | `worldclim_geotiff_zip` | `sampling.py:135-213` |
| `hydrobasins_endorheic_basin_fraction`, `hydrobasins_endorheic_area_fraction` | `hydrobasins_archive_catalog`, `hydrobasins_catalog` | `hydrobasins_archive_catalog` | `readers.py:566-687` |
| `hydrorivers_hack_fitted_exponent`, `hydrorivers_hack_fitted_log_rmse` | `hydrorivers_shapefile_zip`, `hydrorivers_archive` | `hydrorivers_shapefile_zip` | `readers.py:690-811` |
| `feature_count` | `geojson`/`featurecollection` or `shapefile`/`esri_shapefile`/`shp` | as given | `readers.py:76-77`, `:416-418` |
| `count`, `min`, `max`, `mean`, `sum`, `p05`, `p50`, `p95`, `fraction_positive`, `fraction_nonzero` | `esri_ascii_grid`/`ascii_grid`/`asc`, `geojson`/`featurecollection`, `shapefile`/`esri_shapefile`/`shp` | as normalised by `_source_values` | `_helpers.py:140-163` |

Anything else raises `unsupported calibration statistic '<name>'` or `unsupported calibration source format '<format>'`.

The `format` column is enforced only for the sampler and archive statistics (`derive.py:80-128` raises when the declared format is outside the accepted set). `feature_count` and the ten generic statistics go through `_source_values`, which accepts any of the three generic formats, so `feature_count` against an `esri_ascii_grid` is accepted by the reader dispatch and then reduced as `values[0]` — the first raster cell, not a feature count. Treat the `format` column for those two rows as the meaningful combinations, not as a validated constraint.

`p05`/`p50`/`p95` use linear interpolation between order statistics (`_helpers.py:129-137`). `fraction_positive` counts `value > 0.0`; `fraction_nonzero` counts `value != 0.0`.

## Supported datasets, fetch scripts and provenance

Seven source manifests are checked in under `configs/`. Five fetch scripts live under `scripts/` (there is no fetch script for the Seton manifest); all are `#!/usr/bin/env bash` with `set -euo pipefail`, download with `curl -L -fS`, verify with `sha256sum --check --status`, and install under `<repo>/calibration_data/<name>/`.

| Dataset | Fetch script | What it provides | Metrics derived (`source_metric` -> `world_metric`) | Licence / provenance note as stated in the repo |
| --- | --- | --- | --- | --- |
| Synthetic contract fixtures (`configs/calibration_fixtures/*.asc`, wired by `configs/calibration_sources.example.json`) | none — the four grids are checked in | Four tiny ESRI ASCII grids (5x2, 3x2, 10x2, 5x2) with `NODATA_value -9999` | `mean_ocean_mask_fraction` -> `ocean_fraction`; `mean_temperature_c` -> `global_mean_temperature_c`; `mean_river_mask_fraction` -> `river_cell_fraction`; `mean_coastal_land_mask_fraction` -> `coastal_land_fraction` | "Synthetic contract fixtures only; replace these grids with real ETOPO, WorldClim, HydroSHEDS, and Natural Earth-derived artifacts for empirical calibration." |
| Natural Earth 110m physical land (`ne_110m_land`), `configs/calibration_sources.natural_earth_110m.json` | `scripts/fetch_natural_earth_110m.sh` | Global coastline polygons at 1:110m. Downloads `ne_110m_land.zip` to a `mktemp -d`, verifies archive SHA-256 `1926c621...`, unzips, re-verifies `ne_110m_land.shp` SHA-256 `8689e693...`, and asserts `ne_110m_land.VERSION.txt == 4.1.0` | `fibonacci_4096_coastal_land_fraction` -> `coastal_land_fraction` | `source_license`: "Public domain"; `source_version`: `4.1.0`; `source_license_url`: `https://www.naturalearthdata.com/about/terms-of-use/` |
| NOAA ETOPO 2022 v1 (1-degree OPeNDAP stride), `configs/calibration_sources.etopo_2022_1deg.json` | `scripts/fetch_etopo_2022_1deg.sh` | 60-arc-second ice-surface elevation subsampled through an NGDC THREDDS OPeNDAP ASCII query `z[30:60:10770][30:60:21570]` (`--globoff` for the brackets), SHA-256 `b7d41164...` | `fibonacci_ocean_fraction` -> `below_sea_level_surface_fraction`; `fibonacci_mean_land_elevation_m` -> `mean_nonnegative_surface_elevation_m`; `fibonacci_hypsometric_span_m` -> `surface_elevation_span_m` | `source_license`: "Produced by NOAA NCEI; not subject to copyright protection within the United States."; `source_doi`: `10.25921/fd45-gt74`; `source_vertical_datum`: "EGM2008 height (EPSG:3855)" |
| WorldClim 2.1 10-arc-minute monthly normals, `configs/calibration_sources.worldclim_2_1_10m.json` | `scripts/fetch_worldclim_2_1_10m.sh` | `wc2.1_10m_tavg.zip` (SHA-256 `5e567dcf...`) and `wc2.1_10m_prec.zip` (SHA-256 `1090f578...`), each 12 monthly GeoTIFFs | `fibonacci_mean_land_annual_temperature_c` -> `mean_land_annual_temperature_c`; `fibonacci_mean_land_annual_temperature_range_c` -> `mean_land_annual_temperature_range_c`; `fibonacci_mean_land_annual_precipitation_mm` -> `mean_land_precipitation_mm_y` | `source_license`: "Academic and other non-commercial use; redistribution and commercial use require prior permission."; the manifest description adds "Downloaded data remain ignored and are not redistributed."; the script prints the same notice before downloading |
| HydroBASINS v1.c standard Pfafstetter level 3, `configs/calibration_sources.hydrobasins_level3.json` + `configs/hydrobasins_level3_catalog.json` | `scripts/fetch_hydrobasins_level3.sh` | Nine regional ZIPs (`af ar as au eu gr na sa si`), each with its own pinned SHA-256; the catalog re-verifies each archive and computes a combined region-ordered digest | `hydrobasins_endorheic_basin_fraction` -> `non_antarctic_endorheic_watershed_fraction`; `hydrobasins_endorheic_area_fraction` -> `non_antarctic_endorheic_watershed_area_fraction` | `source_license`: "Freely available for scientific, educational, and commercial use under the HydroSHEDS license agreement; attribution and license terms apply."; `source_doi`: `10.1002/hyp.9740`; the script prints the licence line and the TechDoc URL before fetching |
| HydroRIVERS v1.0 global shapefile archive, `configs/calibration_sources.hydrorivers_v10.json` | `scripts/fetch_hydrorivers_v10.sh` | `HydroRIVERS_v10_shp.zip`, SHA-256 `0cf9e363...`. The only resumable fetcher: it skips when the existing archive already verifies, otherwise downloads to `.part` under an `rm -f` EXIT trap and atomically `mv`s | `hydrorivers_hack_fitted_exponent` -> `exorheic_watershed_backbone_hack_fitted_exponent`; `hydrorivers_hack_fitted_log_rmse` -> `exorheic_watershed_backbone_hack_fitted_log_rmse` | Same HydroSHEDS licence text and DOI as HydroBASINS; `source_geographic_coverage`: "Near-global land excluding Antarctica; source quality is lower north of 60 degrees north" |
| Seton et al. 2020 present-day oceanic crustal age, `configs/calibration_sources.seton_2020_oceanic_age.json` | **no fetch script exists in this repository**; the pinned URL is recorded in the manifest | 6 arc-minute gridline XYZ, grid dimensions `[1801, 3601]`, SHA-256 `56ed93be...`. Not consumable by `derive-targets` (the manifest declares no `metric`/`statistic`, so derivation fails at `derive.py:71`); it is the input manifest for `scripts/derive_seton_oceanic_age_targets.py` | `seton_grid_area_weighted_mean_age_ma` -> `initial_oceanic_crust_age_area_weighted_mean_ma`, plus 10 `seton_grid_area_weighted_cdf_le_{20..200}_ma` -> `initial_oceanic_crust_age_area_weighted_cdf_le_{20..200}_ma` | `source_license`: "Creative Commons Attribution 4.0 International"; `source_doi`: `10.1029/2020GC009214`. The derived artifact states: "Repository-derived spherical-grid statistics from the checksum-pinned Seton et al. 2020 age grid; the CDF ordinates are not values published in the paper." |

### The Seton side-channel

`scripts/derive_seton_oceanic_age_targets.py` is a standalone witness tool, not part of the `magic_geo.calibration` package. It streams the XYZ file line by line, hashing as it goes, and enforces:

| Check | Value | Location |
| --- | --- | --- |
| Canonical row order | `longitude == -180.0 + 0.1*i`, `latitude == 90.0 - 0.1*j`, `abs_tol=5e-10` | `scripts/derive_seton_oceanic_age_targets.py:93-99` |
| Row count | `EXPECTED_ROW_COUNT = 1801 * 3601` = 6,485,401 | `:15`, `:146-147` |
| Finite-age node count | `EXPECTED_FINITE_COUNT = 3_189_443` | `:16`, `:148-149` |
| Source digest | must equal the manifest's `source_sha256` | `:140-145` |
| Area weight | longitude endpoint trapezoid factor (`0.5` at index 0 and 3600) times exact spherical latitude-band `sin(north) - sin(south)` | `:110-116` |
| Accumulation | `math.fsum` over chunks of `CHUNK_SIZE = 8192` | `:17`, `:40-56` |

Its output (`configs/calibration_targets.seton_2020_oceanic_age.json`) records `area_weighted_mean_age_ma = 62.84149091327` and ten `area_weighted_cdf_le_threshold` ordinates. That file is a *statistics* artifact, not a target bundle: it has no `targets` list, so `magic-geo calibrate --targets` on it fails with `calibration targets must be a list or an object with a 'targets' list` (exit 2). Its values are folded into the empirical bundle by hand, and the geo-validation suite gates that fold with a dedicated Seton check (`src/magic_geo/geo_validation_suite/empirical.py:22-367`, reached from the Seton gate at `:454-492` and invoked at `:484-491`).

## The pipeline module by module

### `_constants.py` (59 lines)

Holds the statistic name sets that drive dispatch (`_FIBONACCI_COASTAL_STATISTIC`, `_FIBONACCI_RELIEF_STATISTICS`, `_FIBONACCI_WORLDCLIM_STATISTICS`, `_HYDROBASINS_STATISTICS`, `_HYDRORIVERS_STATISTICS`), the SHA-256 regex `_SHA256_PATTERN`, the 15-field `_SOURCE_PROVENANCE_FIELDS` tuple, and `_HYDROBASINS_GENERATED_MIN_CENTROID_LAT_DEG = -60.0` — the Antarctica exclusion latitude applied to the *generated* side so it matches HydroBASINS coverage.

### `errors.py` (7 lines)

`CalibrationError(ValueError)`, "Raised when a calibration target file is malformed."

### `sources.py` (39 lines)

`load_calibration_targets(path)` -> `_target_items` over parsed JSON. `load_calibration_sources(path)` -> `_source_items`, then rewrites `path`, `dbf_path`, `prj_path` to be manifest-relative when they are not absolute.

### `_helpers.py` (455 lines)

| Group | Functions | Notes |
| --- | --- | --- |
| Coercion | `_target_items`, `_source_items`, `_target_float`, `_target_text`, `_optional_float`, `_optional_int` | `_target_float` rejects non-finite; `_optional_int` rejects `bool`, non-integral floats, and strings that do not round-trip. |
| Provenance | `_file_sha256` (1 MiB chunks), `_source_provenance` | See the digest table above. |
| Statistics | `_percentile`, `_numeric_statistic` | The ten generic statistics. |
| Spherical / planar geometry | `_haversine_km` (radius 6371.0 km), `_projected_ring_area_km2`, `_geographic_ring_area_km2` (scale factors 111.320 km/deg longitude at the ring's mean latitude, 110.574 km/deg latitude), `_segment_length_km`, `_ring_area_km2` | The projected variants assume metres and divide by 1e6 / 1000. |
| Vector topology | `_part_ranges`, `_point_in_ring` (ray crossing), `_point_in_polygon_feature` (bbox reject, then parity over all rings) | A feature without a bounding box or `polygon_parts` is an error. |
| Sampling mesh | `_fibonacci_points(n)`, `_symmetric_nearest_neighbors(points, k)`, `_masked_component_sizes` | `_fibonacci_points` uses golden angle `pi*(3 - sqrt(5))` and `z = 1 - 2*(i + 0.5)/n`, returning `(x, y, z, lon_deg, lat_deg)`. Neighbour sets are symmetrised: after a k-nearest pass by dot product, every link is added in both directions, so degree can exceed k. |
| OPeNDAP text | `_comma_separated_floats`, `_next_nonempty_line`, `_nearest_coordinate_index` (bisect, ties go to the lower index) | |
| CRS | `_normalize_vector_coordinate_system`, `_coordinate_system_from_prj_text`, `_prj_path_for_shapefile`, `_coordinate_system_for_vector` | Explicit `coordinate_system` wins; else a `.prj` is parsed; else `geographic`. `EPSG:3857` -> `projected_m`, `EPSG:4326` -> `geographic`, otherwise `PROJCS`/`GEOGCS` plus unit keywords decide. |

### `readers.py` (811 lines)

| Reader | Input | Guarantees enforced |
| --- | --- | --- |
| `_read_esri_ascii_grid` (`:23-68`) | ESRI ASCII grid | Requires `ncols`/`nrows`; the raw value count must equal `ncols*nrows`; `NODATA_value` (default `-9999`) values are dropped from the returned list but still counted; empty result is an error. UTF-8 with latin-1 fallback. |
| `_read_geojson_values` (`:71-95`) | GeoJSON FeatureCollection | `feature_count` returns `[len(features)]`; otherwise `property` is mandatory and must be numeric. |
| `_read_shapefile_records` (`:98-204`) | `.shp` | Hand-written parser. File code `9994`, version `1000`; length header must fit the file; mixed shape types rejected; supported types are 1 (point), 3 (polyline), 5 (polygon), 8 (multipoint); null shapes (type 0) skipped; trailing bytes rejected. Emits per-feature `shape_type`, `point_count`, `part_count`, `length_km`, `area_km2`, and for polygons `bbox` and `polygon_parts`. |
| `_dbf_path_for_shapefile` (`:207-211`) | — | `dbf_path` when declared, else the shapefile path with its suffix replaced by `.dbf`. |
| `_read_dbf_numeric_columns_from_bytes` (`:214-308`) | DBF bytes | Field widths must sum to the record length; requested fields must exist and be type `N` or `F`; deletion flag must be `b" "` or `b"*"`; `require_complete_records=True` makes a blank cell fatal. |
| `_iter_dbf_numeric_records` (`:319-408`) | DBF stream | Streaming variant used for the multi-gigabyte HydroRIVERS table; blanks are always fatal here. |
| `_read_shapefile_values` (`:415-444`) | `.shp` | `feature_count`, else DBF `property`, else a geometry metric. |
| `_read_opendap_ascii_grid` (`:447-515`) | OPeNDAP ASCII | Variable must be an identifier; grid header `var.var[rows][cols]`; rows must appear in order; `rows*cols <= 5_000_000`; `var.lat[...]` and `var.lon[...]` must match the grid dimensions and be strictly increasing. |
| `_worldclim_monthly_samples` (`:518-563`) | WorldClim ZIP | `@lru_cache(maxsize=8)` keyed on path, SHA-256, variable, cell count, scale, offset — the digest is in the key so a replaced archive cannot reuse stale samples. Exactly one member per `_<var>_<MM>.tif`; member size in `(0, 64 MiB]`; all twelve months must share a `grid_signature` (width, height, origin, pixel size). Values are `value*scale + offset`; out-of-raster, nodata and non-finite samples become `None` (`src/magic_geo/geotiff.py:366-399`). |
| `_hydrobasins_catalog_summary` (`:566-673`) | catalog JSON | `pfafstetter_level` in 1..12; regions unique; every archive re-hashed against its declared SHA-256; exactly one DBF per ZIP, size in `(0, 64 MiB]`; `ENDO` must be one of `0.0/1.0/2.0`; `SUB_AREA` must be finite and positive. Returns basin counts, endorheic counts, areas, fractions, per-region digests and a combined digest built from region names and digests in sorted order. |
| `_hydrorivers_archive_summary` (`:690-796`) | HydroRIVERS ZIP | `@lru_cache(maxsize=4)`. Exactly one DBF, size in `(0, 2 GiB]`. Streams `NEXT_DOWN, ENDORHEIC, ORD_CLAS, UPLAND_SKM, DIST_UP_KM`; rejects negative/non-integral `NEXT_DOWN`, `ENDORHEIC` outside `{0,1}`, non-integral or `<1` `ORD_CLAS`, negative areas or distances. Selection is `NEXT_DOWN == 0`, then `ENDORHEIC == 0`, then `ORD_CLAS == 1`, then `UPLAND_SKM >= minimum` and `DIST_UP_KM > 0`. Requires at least 3 observations spanning at least 2 distinct areas. Model identifiers: `fit_model = ordinary_least_squares_log_length_on_log_upstream_area_v1`, `network_selection = next_down_zero_endorheic_zero_order_class_one_with_minimum_upstream_area_v2`. |

### `sampling.py` (213 lines)

| Sampler | Output value | Emitted `source_*` sampling metadata |
| --- | --- | --- |
| `_fibonacci_coastal_land_fraction` (`:14-73`) | coastal land cells / land cells, where a coastal land cell is a land cell with at least one symmetric one-hop water neighbour | `source_sampling_mesh`, `source_sample_cell_count`, `source_sample_neighbor_count`, `source_sample_land_cell_count`, `source_sample_land_fraction`, `source_sample_water_cell_count`, `source_sample_coastal_land_cell_count`, `source_sample_land_component_count`, `source_sample_largest_land_component_cell_count`, `source_sample_largest_land_component_fraction`, `source_sample_land_water_edge_count`, `source_coast_definition = land_cell_with_symmetric_one_hop_water_neighbor` |
| `_fibonacci_relief_statistic` (`:76-132`) | one of `ocean_cell_count/cell_count`, mean of elevations `>= 0`, `max - min` over all samples | `source_sampling_mesh`, `source_sample_cell_count`, grid latitude/longitude counts, min/max, step, and the sample land/ocean counts, ocean fraction, mean land elevation, min/max elevation, hypsometric span |
| `_fibonacci_worldclim_statistic` (`:135-213`) | mean over complete-12-month land cells of, respectively, the annual mean, the annual sum, or the per-cell monthly max-min | `source_sampling_mesh`, `source_sample_cell_count`, `source_sample_complete_land_cell_count`, `source_sample_complete_land_fraction`, `source_sample_excluded_cell_count`, `source_sample_month_count`, grid width/height/origin/pixel size, `source_sample_min_value`, `source_sample_max_value`, plus the variable-specific mean fields |

Guards: the relief sampler requires a genuinely global grid (`latitudes[0] <= -80`, `latitudes[-1] >= 80`, `longitudes[0] <= -170`, `longitudes[-1] >= 170`, `sampling.py:86`) and both land and ocean samples; the coastal sampler requires a polygon shapefile in geographic coordinates and both land and water cells; the WorldClim sampler requires at least one cell with all twelve months present.

### `derive.py` (247 lines)

`derive_calibration_targets(sources)` loops over sources and, per source: resolves dataset/layer/metric/world_metric/path, computes `statistic`, computes provenance (which re-hashes the file), dispatches to a sampler or `_source_values`, reduces generic list values through `_numeric_statistic`, checks finiteness, builds the tolerance range, rounds to 12 decimals, and emits both a target record and a source summary. Shapefile coordinate metadata is attached only when the statistic is not `feature_count` and no `property` was given (`derive.py:57-61`, `:131-135`).

### `evaluate.py` (489 lines)

`score_range(value, min, max)` (`:14-23`) returns `1.0` inside the range, otherwise `max(0.0, min(1.0, 1 - distance/width))` with `width = max(1e-9, target_max - target_min)`. Non-finite inputs and inverted ranges raise. The native engine implements the identical formula in `cpp/src/engine/history.cpp:959-966`.

`_world_metric_values(world)` (`:26-403`) builds the observable map from five independent sources, cross-checking rather than trusting:

1. `world["calibration_checks"]` — every entry with a string `metric` and a `value` (`:28-44`). Duplicate metrics with different values are an error.
2. Cell elevations (`:46-79`) — `below_sea_level_surface_fraction`, `mean_nonnegative_surface_elevation_m`, `surface_elevation_span_m`. `elevation_m` must be present on all cells or none. A serialized value conflicting with the cell-derived one by more than `0.001` is an error.
3. `world["initial_oceanic_crust_age_ledger"]` (`:81-202`) — the mean age and ten CDF ordinates are **re-derived** from per-cell ages, statuses and areas and cross-checked against the serialized summaries: thresholds must be exactly `[20 … 200]`, statuses must be in `range(5)` (status `0` = non-oceanic and is excluded), the recorded mean must match within `1e-9` and each recorded CDF ordinate within `1e-12`.
4. Land climate cells (`:204-240`) — `mean_land_annual_temperature_c`, `mean_land_annual_temperature_range_c`, `mean_land_precipitation_mm_y`, each averaged over non-water cells; land cells require exactly twelve `temperature_monthly_c` entries.
5. `world["watersheds"]` (`:242-402`) — endorheic fractions, the non-Antarctic coverage-restricted fractions, and two power-law fits. `is_endorheic` must be boolean, `outlet_type` a non-empty string, and `(outlet_type == "ocean") == is_endorheic` is rejected as a conflict.

`evaluate_calibration_targets(world, targets)` (`:406-489`) scores each target, copies every `source_*` key except `source_metric` from the target into the check, and returns the report described below.

### `reports.py` (70 lines)

`write_calibration_markdown` renders `# Calibration Report`, a `## Summary` bullet list over the ten summary keys in a fixed order, then one `## Checks` bullet per check with status `pass`/`fail`/`missing`, value, target interval, score, the `source_metric` mapping when it differs, and any of `source_version`, `source_sha256`, `tolerance_basis`. `write_target_derivation_markdown` renders `# Calibration Target Derivation`, a `## Summary` over the four derivation keys, then a `## Targets` bullet per target carrying `source_value`, the target interval, the resolved `source` path and the same three provenance fields — there is no status column, because a derivation has nothing to pass or fail. Both `mkdir -p` the parent directory; summary keys absent from the report are skipped rather than printed as `None`.

## Target bundle schemas

Two different JSON shapes exist, and they are **not interchangeable**.

### 1. Derived target bundle — the `derive-targets` output, the `calibrate --targets` input

`load_calibration_targets` accepts either a bare JSON list of objects or an object with a `targets` list (`_helpers.py:18-26`).

Top-level output of `derive_calibration_targets` (`derive.py:238-247`):

| Field | Type | Meaning |
| --- | --- | --- |
| `summary.derived_target_count` | int | Number of targets emitted. |
| `summary.source_count` | int | Number of source summaries. |
| `summary.mapped_target_count` | int | Targets whose `source_metric` differs from `metric`. |
| `summary.unique_world_metric_count` | int | Distinct `metric` values. |
| `targets` | list | Target records (below). |
| `source_summaries` | list | Per-source derivation record (below). |

Per-target record (`derive.py:171-191`):

| Field | Always present | Meaning |
| --- | --- | --- |
| `dataset`, `layer` | yes | Free-text identity; both are **required** by `evaluate_calibration_targets`. |
| `metric` | yes | World-side observable name. |
| `source_metric` | yes | Source-side statistic name. |
| `target_min`, `target_max` | yes | Inclusive range, rounded to 12 decimals. |
| `source` | yes | Resolved dataset path as a string. |
| `source_format` | yes | Normalised format identifier. |
| `source_statistic` | yes | The lower-cased `statistic`. |
| `source_value` | yes | The derived statistic, rounded to 12 decimals. |
| `source_sha256` | yes | Actual digest of the dataset file. |
| `source_archive_sha256` | when declared | Lower-cased declared archive digest. |
| any of `_SOURCE_PROVENANCE_FIELDS` | when declared | Verbatim. |
| sampling metadata (`source_sample_*`, `source_grid_*`, `source_sampling_mesh`, `source_coast_definition`, HydroBASINS/HydroRIVERS `source_*` summary fields) | statistic-dependent | Verbatim from the sampler/reader. |
| `source_coordinate_system`, `source_prj` | shapefile geometry statistics only | CRS resolution result. |
| `source_property`, `source_dbf` | when `property` given | Attribute name and DBF path. |
| `source_geometry_metric` | when given | Geometry reduction. |
| `tolerance_basis` | when given | Verbatim policy text. |

Per-source summary (`derive.py:213-236`) repeats `dataset`, `layer`, `metric` (source-side), `world_metric`, `path`, `format`, `statistic`, `value`, `sample_count`, `sha256`, the provenance fields, `source_archive_sha256`, and — with the `source_` prefix stripped — the sampling metadata (`sampling_mesh`, `sample_cell_count`, …), plus `coordinate_system`, `prj_path`, `property`, `dbf_path`, `geometry_metric`, `tolerance_basis` where applicable. `sample_count` is `source_sample_record_count`, else `source_sample_cell_count`, else the raw value-list length.

### 2. Empirical target bundle — the geo-validation-suite format

`configs/geo_validation_earth_empirical_targets.json` (`canonical_earth_empirical_targets_v2`, schema version 1, 7 sources, 22 targets) uses a normalised `sources` map plus targets that reference it by `source_id`. It is loaded by `src/magic_geo/geo_validation_suite/empirical.py:495-679` with strict unknown-field rejection, and the loader expands each target with its source's provenance before scoring.

| Level | Allowed fields |
| --- | --- |
| root | exactly `schema_version` (must be 1), `name`, `description`, `derivation`, `sources`, `targets` |
| `sources[<id>]` | `dataset`, `layer`, `source` (all three required), plus optional `source_format`, `source_url`, `source_archive_url`, `source_version`, `source_license`, `source_license_url`, `source_acquired_on`, `source_citation`, `source_doi`, `source_horizontal_crs`, `source_geographic_coverage`, `source_vertical_datum`, `source_native_resolution`, `source_sha256`, `source_archive_sha256` |
| `targets[i]` | `source_id`, `metric` (unique across the bundle), `source_metric`, `source_value`, `target_min`, `target_max`, `tolerance_basis`, `source_statistic`, `source_processing`, `source_variable_units`, `source_sample_cell_count`, `source_sample_record_count`, `source_sample_neighbor_count`, `source_minimum_upstream_area_km2` |
| `derivation` | `tool`, `derived_on`, `runtime_requires_raw_sources`, `source_manifests[{path, sha256}]`, `supplemental_target_derivations[{path, sha256, tool}]` — every declared artifact is read and SHA-256-verified at load time |

Because the raw targets in this bundle carry no `dataset`/`layer` (they inherit them from the source map at load time), passing this file straight to `magic-geo calibrate --targets` fails with `calibration target missing 'dataset'` and exit code 2. Use the suite (`magic-geo validate-geo-suite`) for this bundle; see [Geo Validation Suite](./13-geo-validation-suite.md).

## World-side metrics: definition, units, tolerance model

### Observables `evaluate` can extract from a world

A 512-cell world generated from `configs/earthlike_seed.yaml` exposes all 39 of these (read from the `available_world_metrics` array of its report). The set is **not** a fixed schema: `_world_metric_values` only emits what the world document actually supports, so a world without `elevation_m` on its cells, without an `initial_oceanic_crust_age_ledger`, without `centroid_lat_deg` on its watersheds, or without enough large ocean-outlet watersheds yields a shorter list. Always read `available_world_metrics` from the report rather than assuming this table.

| Metric | Definition | Units | Origin |
| --- | --- | --- | --- |
| `ocean_fraction` | water area / total area, falling back to water-cell count / cell count when total area is 0 | fraction | native check 0 |
| `mean_land_elevation_m` | mean `elevation_m` over non-water cells | m | native check 1 |
| `hypsometric_span_m` | `max(elevation_m) - min(elevation_m)` over all cells | m | native check 2 |
| `global_mean_temperature_c` | mean `temperature_c` over all cells | degC | native check 3 |
| `mean_land_precipitation_mm_y` | mean `precipitation_mm_y` over non-water cells | mm/y | native check 4 *and* re-derived from cells (`evaluate.py:231`); the two must agree within `0.001` |
| `mean_monthly_temperature_range_c` | mean over all cells of `max(temperature_monthly_c) - min(temperature_monthly_c)` | degC | native check 5 |
| `river_cell_fraction` | river land cells / land cells | fraction | native check 6 |
| `endorheic_watershed_fraction` | endorheic watersheds / watersheds | fraction | native check 7 *and* re-derived from `watersheds` (`evaluate.py:315`); must agree within `0.001` |
| `desert_land_fraction` | land cells with biome id 9 or 10, over land cells | fraction | native check 8 |
| `ice_land_fraction` | land cells with biome id 3 or `ice_thickness_m > 25.0`, over land cells | fraction | native check 9 |
| `forest_land_fraction` | land cells with biome id 5, 6, 12 or 13, over land cells | fraction | native check 10 |
| `coastal_land_fraction` | land cells with at least one water neighbour, over land cells | fraction | native check 11 |
| `below_sea_level_surface_fraction` | cells with `elevation_m < 0`, over all cells | fraction | cells (`evaluate.py:68-70`) |
| `mean_nonnegative_surface_elevation_m` | mean `elevation_m` over cells with `elevation_m >= 0` | m | cells (`evaluate.py:71-73`) |
| `surface_elevation_span_m` | `max(elevation_m) - min(elevation_m)` | m | cells (`evaluate.py:74`) |
| `initial_oceanic_crust_age_area_weighted_mean_ma` | area-weighted mean of `age_ma_by_cell` over cells whose ledger status is non-zero | Ma | oceanic-age ledger, re-derived and cross-checked (`evaluate.py:160-193`) |
| `initial_oceanic_crust_age_area_weighted_cdf_le_{20,40,60,80,100,120,140,160,180,200}_ma` | area-weighted fraction of non-zero-status cells with `age <= threshold` | fraction | oceanic-age ledger (`evaluate.py:164-202`) |
| `mean_land_annual_temperature_c` | mean over non-water cells of the 12-month mean of `temperature_monthly_c` | degC | cells (`evaluate.py:227`) |
| `mean_land_annual_temperature_range_c` | mean over non-water cells of per-cell `max - min` of `temperature_monthly_c` | degC | cells (`evaluate.py:228-230`) |
| `endorheic_watershed_area_fraction` | endorheic watershed area / total watershed area | fraction | watersheds (`evaluate.py:316`) |
| `non_antarctic_endorheic_watershed_fraction` | same as above by count, restricted to watersheds with `centroid_lat_deg >= -60.0` | fraction | watersheds (`evaluate.py:333-348`) |
| `non_antarctic_endorheic_watershed_area_fraction` | same restriction, by area | fraction | watersheds (`evaluate.py:349-351`) |
| `watershed_hack_fitted_exponent` | OLS exponent of `main_channel_length_km` vs `area_km2` in log space, over all watersheds with `area_km2 >= 1e6` and positive channel length | dimensionless | `fit_power_law` (`src/magic_geo/scaling.py:19-60`) |
| `watershed_hack_fitted_coefficient` | `exp(intercept)` from the same fit | km / km^(2*exponent) | same |
| `watershed_hack_fitted_log_rmse` | natural-log RMS residual of the same fit | dimensionless | same |
| `watershed_hack_fitted_observation_count` | number of observations in that fit | count | same |
| `exorheic_watershed_backbone_hack_fitted_exponent` | same fit restricted to `is_endorheic == False` and `outlet_type == "ocean"` | dimensionless | `evaluate.py:299-308`, `:371-393` |
| `exorheic_watershed_backbone_hack_fitted_coefficient` | as above | km / km^(2*exponent) | same |
| `exorheic_watershed_backbone_hack_fitted_log_rmse` | as above | dimensionless | same |
| `exorheic_watershed_backbone_hack_fitted_observation_count` | as above | count | same |

The power-law fit needs at least 2 observations and `variance_x > 1e-12`; otherwise it falls back to `fallback_exponent = 0.6` (`src/magic_geo/scaling.py:43-47`). The exorheic fit is only emitted when there are at least 2 observations spanning at least 2 distinct areas (`evaluate.py:367-370`).

### Tolerance model per checked-in external target

These are the tolerances declared in the checked-in source manifests, and the resulting ranges in `configs/geo_validation_earth_empirical_targets.json`.

| World metric | Dataset | Tolerance model | Derived `source_value` | Resulting range |
| --- | --- | --- | --- | --- |
| `coastal_land_fraction` | Natural Earth 110m | `tolerance_abs: 0.05` | 0.484033613445 | [0.434033613445, 0.534033613445] |
| `below_sea_level_surface_fraction` | ETOPO 2022 | `tolerance_abs: 0.02` | 0.708984375 | [0.688984375, 0.728984375] |
| `mean_nonnegative_surface_elevation_m` | ETOPO 2022 | `tolerance_fraction: 0.20` | 796.973802769295 | [637.579042215436, 956.368563323154] |
| `surface_elevation_span_m` | ETOPO 2022 | `tolerance_fraction: 0.15` | 14354.6447 | [12201.447995, 16507.841405] |
| `mean_land_annual_temperature_c` | WorldClim 2.1 tavg | `tolerance_abs: 3.0` | 9.365324663961 | [6.365324663961, 12.365324663961] |
| `mean_land_annual_temperature_range_c` | WorldClim 2.1 tavg | `tolerance_abs: 4.0` | 19.542444335321 | [15.542444335321, 23.542444335321] |
| `mean_land_precipitation_mm_y` | WorldClim 2.1 prec | `tolerance_fraction: 0.25` | 774.665594855305 | [580.999196141479, 968.331993569132] |
| `non_antarctic_endorheic_watershed_fraction` | HydroBASINS L3 | `tolerance_abs: 0.05` | 0.119863013699 | [0.069863013699, 0.169863013699] |
| `non_antarctic_endorheic_watershed_area_fraction` | HydroBASINS L3 | `tolerance_abs: 0.08` | 0.174952444749 | [0.094952444749, 0.254952444749] |
| `exorheic_watershed_backbone_hack_fitted_exponent` | HydroRIVERS v1.0 | `tolerance_abs: 0.2` | 0.455213509131 | [0.255213509131, 0.655213509131] |
| `exorheic_watershed_backbone_hack_fitted_log_rmse` | HydroRIVERS v1.0 | explicit `target_min: 0.0`, `target_max: 0.405416679619` (source RMSE + 0.25) | 0.155416679619 | [0.0, 0.405416679619] |
| `initial_oceanic_crust_age_area_weighted_mean_ma` | Seton 2020 | +/- 15 Ma (encoded as explicit bounds in the empirical bundle) | 62.84149091327 | [47.84149091327, 77.84149091327] |
| `initial_oceanic_crust_age_area_weighted_cdf_le_{20..200}_ma` | Seton 2020 | +/- 0.06 fraction, clipped at 1.0 for the 160/180/200 Ma ordinates | 0.2037…0.9994 | e.g. [0.143730125937, 0.263730125937] at 20 Ma; [0.939362742267, 1.0] at 200 Ma |

Every one of these carries a `tolerance_basis` string that says, in the repository's own words, that it is a model-fit tolerance and "not a statistical confidence interval". The HydroBASINS and HydroRIVERS bases additionally record semantic caveats verbatim: generated terminal watersheds "are not a Pfafstetter hierarchy", "HydroBASINS lumping and virtual endorheic connections remain semantic limitations", and "coarse grid resolution remains a model-fit limitation". The Seton mean-age basis records that its tolerance is "not a claim of local age-field agreement".

## The built-in 12-check native calibration set

Separate from external calibration, the native engine emits `world["calibration_checks"]` — twelve broad Earth-like range checks computed inside `generate_calibration_checks` (`cpp/src/engine/history.cpp:990-1088`) and serialized by `calibration_checks_json` (`cpp/src/engine/process_serialization.cpp:4417-4436`). Their names come from three fixed arrays (`cpp/src/engine/schema_names.hpp:102-115`). `evaluate.py` reads them as observables, so an external target whose `world_metric` is one of these names is comparing against a value the engine already computed.

| id | dataset | layer | metric | Built-in range |
| ---: | --- | --- | --- | --- |
| 0 | `ETOPO_reference_range` | `relief_bathymetry` | `ocean_fraction` | [0.55, 0.78] |
| 1 | `ETOPO_reference_range` | `relief_bathymetry` | `mean_land_elevation_m` | [120.0, 1800.0] |
| 2 | `ETOPO_reference_range` | `relief_bathymetry` | `hypsometric_span_m` | [3500.0, 17000.0] |
| 3 | `WorldClim_reference_range` | `climate` | `global_mean_temperature_c` | [-5.0, 28.0] |
| 4 | `WorldClim_reference_range` | `climate` | `mean_land_precipitation_mm_y` | [250.0, 2300.0] |
| 5 | `WorldClim_reference_range` | `climate` | `mean_monthly_temperature_range_c` | [2.0, 38.0] |
| 6 | `HydroSHEDS_reference_range` | `hydrology` | `river_cell_fraction` | [0.005, 0.14] |
| 7 | `HydroSHEDS_reference_range` | `hydrology` | `endorheic_watershed_fraction` | [0.0, 0.55] |
| 8 | `WorldClim_reference_range` | `biomes` | `desert_land_fraction` | [0.04, 0.48] |
| 9 | `WorldClim_reference_range` | `biomes` | `ice_land_fraction` | [0.0, 0.38] |
| 10 | `WorldClim_reference_range` | `biomes` | `forest_land_fraction` | [0.08, 0.58] |
| 11 | `NaturalEarth_reference_range` | `cartography` | `coastal_land_fraction` | [0.03, 0.48] |

Each serialized check carries `id`, `dataset`, `layer`, `metric`, `passed`, `value`, `target_min`, `target_max`, `score`. The dataset names are labels for the *provenance of the range*, not evidence that any dataset was read at generation time — the bounds are hardcoded constants. `validate-geo` cross-checks that exactly this metric set is present through `CALIBRATION_EXPECTED_METRICS` (`src/magic_geo/geo_validation.py:43-58`) and the `earth_calibration.built_in_calibration_integrity` check (`:2698-2699`).

## Coverage versus fit and the policy flags

The two failure modes are deliberately kept apart.

| Concept | Question | Failure looks like | Summary fields |
| --- | --- | --- | --- |
| **Coverage** | Does the world even expose the metric a target names? | `missing_metric: true`, `value: null`, `score: 0.0`, `passed: false`, and the metric name added to `missing_world_metrics` | `external_calibration_missing_metric_count`, `external_calibration_evaluated_metric_count`, `external_calibration_metric_coverage_fraction`, `external_calibration_complete` |
| **Fit** | Does the exposed value land inside the target range? | `missing_metric: false`, `passed: false`, `0.0 <= score < 1.0` | `external_calibration_pass_count`, `external_calibration_pass_fraction`, `external_calibration_evaluated_pass_fraction`, `external_mean_calibration_score`, `external_mean_evaluated_calibration_score` |

The `*_evaluated_*` variants divide by the evaluated count rather than the total, so they measure fit among metrics that actually exist. The unqualified `pass_fraction` and `mean_calibration_score` divide by the total, so missing metrics drag them down: a bundle with half its metrics missing can never exceed `pass_fraction = 0.5`.

`calibrate` policy (`src/magic_geo/cli/commands/calibrate.py:81-91`):

| Flag | Trigger | Message | Exit |
| --- | --- | --- | --- |
| `--require-all-metrics` | `external_calibration_complete` is false — either a metric is missing or there were zero targets | `Calibration coverage incomplete; missing world metrics: …` or `; no calibration targets were evaluated` | 1 |
| `--require-all-passed` | any check has `passed: false`, **or** `checks` is empty | `Calibration fit failed; failed metrics: …` or `; no calibration targets` | 1 |
| default (`--allow-missing-metrics --allow-fit-failures`) | never | — | 0 |

`calibrate-ensemble` spells the same two flags but gates on the whole-matrix roll-ups, not on one report, and its messages differ (`calibrate.py:188-199`):

| Flag | Trigger | Message | Exit |
| --- | --- | --- | --- |
| `--require-all-metrics` | `summary.reference_matrix_complete` is false — i.e. `all_members_complete` over the implicit `all` scope | `Calibration ensemble coverage incomplete` (no metric list) | 1 |
| `--require-all-passed` | `summary.reference_matrix_all_passed` is false | `Calibration ensemble fit failed; failed members: …` — member ids, not metric names | 1 |
| default | never | — | 0 |

Both gates run *after* `write_json(output, report)` and after the optional Markdown, so the evidence is always on disk even when the command exits nonzero. The repository uses this asymmetry deliberately: datasets whose fit currently fails are still exercised under coverage-only gating so the failing evidence is preserved rather than suppressed.

## Calibration report schema

Written by `write_json` (`src/magic_geo/io/json_writer.py:10-15`): `indent=2`, `sort_keys=True`, `allow_nan=False`.

### Top level

| Field | Type | Meaning |
| --- | --- | --- |
| `summary` | object | Ten aggregate fields, below. |
| `available_world_metrics` | sorted list of strings | Every observable `_world_metric_values` could extract from this world. Useful for diagnosing a missing metric. |
| `missing_world_metrics` | sorted list of strings | Target metrics not present in the world. |
| `checks` | list | One record per target, in target order. |

### `summary`

| Field | Type | Definition |
| --- | --- | --- |
| `external_calibration_check_count` | int | `len(checks)`. |
| `external_calibration_evaluated_metric_count` | int | `check_count - missing_count`. |
| `external_calibration_pass_count` | int | Checks with `passed: true`. |
| `external_calibration_missing_metric_count` | int | Checks with `missing_metric: true`. |
| `external_calibration_metric_coverage_fraction` | float, 6 dp | `evaluated / count`, or `0.0` when count is 0. |
| `external_calibration_pass_fraction` | float, 6 dp | `pass / count`, or `0.0`. |
| `external_calibration_evaluated_pass_fraction` | float, 6 dp | `pass / evaluated`, or `0.0`. |
| `external_mean_calibration_score` | float, 6 dp | `sum(score) / count`, or `0.0`. |
| `external_mean_evaluated_calibration_score` | float, 6 dp | `sum(score) / evaluated`, or `0.0`. |
| `external_calibration_complete` | bool | `missing_count == 0 and count > 0`. |

### `checks[i]`

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | int | Sequential index, equal to the target's position. |
| `dataset`, `layer` | string | Copied from the target; both are mandatory on the target. |
| `metric` | string | World-side observable name. |
| `source_metric` | string | Source-side name; falls back to `metric` when the target omits it. |
| `value` | float or `null` | The world observable, `null` when missing. |
| `target_min`, `target_max` | float | Inclusive bounds. |
| `score` | float, 6 dp | `score_range(value, min, max)`, or `0.0` when missing. |
| `passed` | bool | `target_min <= value <= target_max`; `false` when missing. |
| `missing_metric` | bool | Whether the world lacked the metric. |
| `source` | string | `target["source"]`, defaulting to the literal `"external_target"`. |
| every `source_*` key on the target except `source_metric` | varies | Verbatim pass-through: `source_sha256`, `source_format`, `source_statistic`, `source_value`, `source_url`, `source_license`, sampling metadata, etc. |
| `tolerance_basis` | string | Present only when the target declared it. |

## `calibrate-ensemble`

`src/magic_geo/ensemble_calibration.py`, schema version 1, report type `calibration_ensemble_v1`, at most `MAX_ENSEMBLE_MEMBER_COUNT = 256` members (`:15-17`).

### What it sweeps

Exactly two coordinates. For each member, the base `WorldConfig` is dumped, `run.seed` and `mesh.cell_count` are replaced, and the config is re-validated before generation (`:244-247`). Nothing else about the config varies, so the ensemble measures **seed x mesh-resolution** sensitivity of the calibration metrics and nothing more.

Manifest schema (`load_calibration_ensemble_manifest`, `:27-91`):

| Field | Type | Constraint |
| --- | --- | --- |
| `schema_version` | int | must equal 1 |
| `name` | non-empty string | — |
| `members` | non-empty list, <= 256 | — |
| `members[i].id` | non-empty string | unique across the manifest |
| `members[i].seed` | int | `0 <= seed <= 2**64 - 1`, `bool` rejected |
| `members[i].cell_count` | int | `>= 128`, `bool` rejected |
| `members[i].groups` | list of non-empty strings | de-duplicated and sorted; the name `all` is reserved |
| — | — | the `(seed, cell_count)` pair must be unique across members |

Targets are normalised before use (`_normalized_targets`, `:94-121`): non-empty, each an object with non-empty `metric`, `dataset`, `layer`, finite numeric `target_min`/`target_max`, non-inverted, and `metric` unique across *all* supplied bundles.

The checked-in matrix `configs/calibration_ensemble.r1.json` (`r1_empirical_seed_resolution_matrix_v1`) has 10 members: a 5-seed sweep at 4,096 cells (seeds 1–5, group `seed_sweep`) and a 5-resolution sweep at seed 424242 over 512/1024/2048/4096/8192 (group `resolution_sweep`), with `seed_424242_cells_4096` belonging to both groups.

### How it aggregates

Every member is scored with the same `evaluate_calibration_targets`. A member is `complete` when `external_calibration_complete` is true, and `all_targets_passed` when it is complete, has at least one check, and every check passed (`:256-259`).

Three roll-up levels, computed by `_scope_summary` (`:202-223`) for the implicit scope `all` and once per named group:

| Roll-up | Fields |
| --- | --- |
| Scope | `name`, `member_ids`, `member_count`, `complete_member_count`, `complete_member_fraction`, `all_targets_passed_member_count`, `all_targets_passed_member_fraction`, `all_members_complete`, `all_members_passed`, `datasets`, `metrics` |
| Per-dataset (`_dataset_results`, `:159-199`) | `dataset`, `metrics` (list of metric names, first-appearance order), `target_count`, `member_count`, `complete_member_count`, `coverage_fraction`, `all_metrics_passed_member_count`, `all_metrics_passed_member_fraction` |
| Per-metric (`_metric_results`, `:124-156`) | `metric`, `dataset`, `layer`, `target_min`, `target_max`, `member_count`, `evaluated_member_count`, `coverage_fraction`, `pass_count`, `pass_fraction`, `value_min`, `value_max`, `value_mean` (12 dp, `null` when no member evaluated it) |

### Report contents

| Field | Meaning |
| --- | --- |
| `schema_version` | `1` |
| `report_type` | `calibration_ensemble_v1` |
| `name` | manifest `name` |
| `provenance.base_config_sha256` | SHA-256 of the canonical JSON dump of the base config (`sort_keys=True`, compact separators) (`:298-308`) |
| `provenance.matrix_sha256` | SHA-256 of the `--matrix` file bytes (`calibrate.py:169`) |
| `provenance.target_bundles[]` | `{name, sha256, target_count}` per `--targets` bundle (`calibrate.py:150-156`) |
| `base_config` | `{name, seed, mesh_backend, cell_count}` of the **base** config, not of any member |
| `summary` | `member_count`, `group_count`, `target_count`, `dataset_count`, `complete_member_count`, `complete_member_fraction`, `all_targets_passed_member_count`, `all_targets_passed_member_fraction`, `reference_matrix_complete`, `reference_matrix_all_passed` |
| `members[]` | `id`, `seed`, `requested_cell_count`, `generated_cell_count` (from `world.summary.cell_count`), `mesh_backend` (from `world.mesh_backend`), `groups` (always prefixed with `all`), `complete`, `all_targets_passed`, `target_count`, `pass_count`, `pass_fraction`, `mean_score`, `missing_world_metrics`, `checks` (the full per-target check list) |
| `datasets[]`, `metrics[]` | the `all`-scope roll-ups |
| `groups[]` | one full scope summary per named group, each with its own `datasets` and `metrics` |

Progress is echoed per member as `[i/N] <id> seed=<seed> cells=<cells>` (`calibrate.py:158-162`). A `RuntimeError` from generation is rewrapped as `CalibrationError: calibration ensemble member '<id>' generation failed: …` (`:250-253`).

`write_calibration_ensemble_markdown` (`:340-413`) renders four sections: `## Summary` (the ten summary keys as bullets), `## Members` (8 columns), `## Dataset Fit` (7 columns, one block per scope starting with `all`), and `## Metric Fit` (9 columns).

## Worked end-to-end example

Everything below was executed against this repository. The synthetic fixtures are used so the example needs no network access; substitute a real manifest and its fetch script for an empirical run.

### 0. Fetch a real dataset (optional for this example)

```bash
bash scripts/fetch_natural_earth_110m.sh
bash scripts/fetch_etopo_2022_1deg.sh
bash scripts/fetch_worldclim_2_1_10m.sh
bash scripts/fetch_hydrobasins_level3.sh
bash scripts/fetch_hydrorivers_v10.sh
```

Each installs under `calibration_data/<name>/` and verifies pinned SHA-256 digests; a mismatch aborts the script.

### 1. Generate a world

```bash
magic-geo generate \
  --config configs/earthlike_seed.yaml \
  --cells 512 \
  --output runs/w512.json
```

```
Generating world | scope=full_world cells=512
Wrote runs/w512.json | scope=full_world cells=512 plates=14 ocean=0.629 rivers=14 elapsed=2.6s
```

### 2. Derive targets

```bash
magic-geo derive-targets \
  --sources configs/calibration_sources.example.json \
  --output runs/fixture_targets.json \
  --summary runs/fixture_targets.md
```

```
Wrote runs/fixture_targets.json | targets=4 sources=4
```

The four fixture grids reduce as follows (all with `statistic: mean`, ESRI ASCII, `-9999` dropped):

| Fixture | Non-NODATA values | `source_value` | Tolerance | Range |
| --- | --- | ---: | --- | --- |
| `etopo_ocean_mask.asc` (5x2) | 10 | 0.7 | `tolerance_abs: 0.1` | [0.6, 0.8] |
| `worldclim_temperature.asc` (3x2) | 5 | 14.0 | `tolerance_abs: 1.0` | [13.0, 15.0] |
| `hydrosheds_river_mask.asc` (10x2) | 20 | 0.05 | `tolerance_abs: 0.03` | [0.02, 0.08] |
| `natural_earth_coastal_land_mask.asc` (5x2) | 10 | 0.4 | `tolerance_abs: 0.1` | [0.3, 0.5] |

One emitted target, verbatim:

```json
{
  "dataset": "contract_fixture_etopo",
  "layer": "ocean_mask",
  "metric": "ocean_fraction",
  "source": "configs/calibration_fixtures/etopo_ocean_mask.asc",
  "source_format": "esri_ascii_grid",
  "source_metric": "mean_ocean_mask_fraction",
  "source_sha256": "ae3ed694858d8aca7b064269217e664ff51aa838e945cef8b739360482851da8",
  "source_statistic": "mean",
  "source_value": 0.7,
  "target_max": 0.8,
  "target_min": 0.6
}
```

and the corresponding `summary`:

```json
{
  "derived_target_count": 4,
  "mapped_target_count": 4,
  "source_count": 4,
  "unique_world_metric_count": 4
}
```

### 3. Score the world

```bash
magic-geo calibrate \
  --world runs/w512.json \
  --targets runs/fixture_targets.json \
  --output runs/fixture_calibration.json \
  --summary runs/fixture_calibration.md \
  --require-all-metrics
```

```
Wrote runs/fixture_calibration.json | checks=4 coverage=1.000 pass_fraction=0.500
```

Exit code `0`: coverage is complete, and `--require-all-passed` was not requested. The report's summary:

```json
{
  "external_calibration_check_count": 4,
  "external_calibration_complete": true,
  "external_calibration_evaluated_metric_count": 4,
  "external_calibration_evaluated_pass_fraction": 0.5,
  "external_calibration_metric_coverage_fraction": 1.0,
  "external_calibration_missing_metric_count": 0,
  "external_calibration_pass_count": 2,
  "external_calibration_pass_fraction": 0.5,
  "external_mean_calibration_score": 0.907775,
  "external_mean_evaluated_calibration_score": 0.907775
}
```

The four checks, read from `runs/fixture_calibration.md`:

| Metric | Dataset / layer | Value | Target | Score | Status |
| --- | --- | ---: | --- | ---: | --- |
| `ocean_fraction` | `contract_fixture_etopo` / `ocean_mask` | 0.629 | [0.6, 0.8] | 1.0 | pass |
| `global_mean_temperature_c` | `contract_fixture_worldclim` / `annual_temperature` | 15.0008 | [13.0, 15.0] | 0.9996 | fail |
| `river_cell_fraction` | `contract_fixture_hydrosheds` / `river_mask` | 0.0737 | [0.02, 0.08] | 1.0 | pass |
| `coastal_land_fraction` | `contract_fixture_natural_earth` / `coastal_land_mask` | 0.5737 | [0.3, 0.5] | 0.6315 | fail |

The temperature check illustrates the score model exactly: the value overshoots the upper bound by `0.0008` against a range width of `2.0`, so the score is `1 - 0.0008/2.0 = 0.9996` — a near-perfect *score* on a *failed* check. Score is a distance measure, not a verdict.

Adding `--require-all-passed` to the same invocation would write the identical report and then exit `1` with `Calibration fit failed; failed metrics: global_mean_temperature_c, coastal_land_fraction`.

### 4. Sweep seeds and resolutions

```bash
cat > runs/mini_matrix.json <<'EOF'
{
  "schema_version": 1,
  "name": "wiki_example_matrix_v1",
  "members": [
    {"id": "seed_1_cells_256", "seed": 1, "cell_count": 256, "groups": ["seed_sweep"]},
    {"id": "seed_2_cells_256", "seed": 2, "cell_count": 256, "groups": ["seed_sweep"]},
    {"id": "seed_1_cells_512", "seed": 1, "cell_count": 512, "groups": ["resolution_sweep"]}
  ]
}
EOF

magic-geo calibrate-ensemble \
  --config configs/earthlike_seed.yaml \
  --matrix runs/mini_matrix.json \
  --targets runs/fixture_targets.json \
  --output runs/mini_ensemble.json \
  --summary runs/mini_ensemble.md
```

```
[1/3] seed_1_cells_256 seed=1 cells=256
[2/3] seed_2_cells_256 seed=2 cells=256
[3/3] seed_1_cells_512 seed=1 cells=512
Wrote runs/mini_ensemble.json | members=3 coverage=1.000 all_passed=0.000
```

Report summary and provenance:

```json
{
  "summary": {
    "member_count": 3, "group_count": 2, "target_count": 4, "dataset_count": 4,
    "complete_member_count": 3, "complete_member_fraction": 1.0,
    "all_targets_passed_member_count": 0, "all_targets_passed_member_fraction": 0.0,
    "reference_matrix_complete": true, "reference_matrix_all_passed": false
  },
  "provenance": {
    "base_config_sha256": "32c836893a38bd152c3fdbe156683a4d3baa5f34aed3ab46aefb849f3dbe1b9f",
    "matrix_sha256": "71e74fccd58fe9f848736d3fdbb5d1df50ec03ac76340a1c6ffc117af347834c",
    "target_bundles": [
      {"name": "fixture_targets.json", "sha256": "ba0e36...", "target_count": 4}
    ]
  },
  "base_config": {"cell_count": 4096, "mesh_backend": "fibonacci_sphere", "name": "earthlike_mvp", "seed": 424242}
}
```

Note that `base_config` echoes the *unmodified* base (4,096 cells, seed 424242) even though no member used those values — it is provenance for what was mutated, not a description of any member.

The `## Metric Fit` table from `runs/mini_ensemble.md`:

| Metric | Dataset | Members | Evaluated | Passed | Pass fraction | Min | Mean | Max |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ocean_fraction | contract_fixture_etopo | 3 | 3 | 3 | 1.000000 | 0.6442 | 0.6783 | 0.7225 |
| global_mean_temperature_c | contract_fixture_worldclim | 3 | 3 | 0 | 0.000000 | 15.0002 | 15.0033 | 15.0055 |
| river_cell_fraction | contract_fixture_hydrosheds | 3 | 3 | 2 | 0.666667 | 0.0495 | 0.062733333333 | 0.0824 |
| coastal_land_fraction | contract_fixture_natural_earth | 3 | 3 | 0 | 0.000000 | 0.6429 | 0.7134 | 0.8353 |

This is exactly what the ensemble is for: `ocean_fraction` passes for every member, `global_mean_temperature_c` fails for every member by a hair, and `river_cell_fraction` straddles the boundary — a distinction invisible from any single `calibrate` run.

## Limitations and unresolved claims

- **External fit is a separate verdict from internal integrity, and it currently fails.** The README states the current status of the authoritative Earth run: the 22-metric checked-in bundle has coverage complete at 22/22 and fit at 17/22, with failures at Natural Earth coastal land fraction, all three ETOPO relief metrics, and HydroBASINS non-Antarctic endorheic watershed area fraction. The same passage records that "Internal closure and replay therefore do not substitute for the remaining Earth-fit gaps." Passing internal validation says nothing about Earth fit, and vice versa.
- **Every tolerance is a declared model-fit tolerance, not a confidence interval.** This wording appears in the `tolerance_basis` of every checked-in target. No target in this repository carries a statistical uncertainty derived from the source data.
- **The built-in 12-check set is not evidence of dataset comparison.** Its `dataset` labels (`ETOPO_reference_range`, `WorldClim_reference_range`, `HydroSHEDS_reference_range`, `NaturalEarth_reference_range`) name the provenance of hardcoded bounds in `cpp/src/engine/history.cpp:1059-1086`; no dataset is read at generation time.
- **HydroBASINS comparison is not a Pfafstetter equivalence.** The manifest states that "Generated terminal watersheds are resolution-dependent and are not a fully equivalent Pfafstetter hierarchy; the count comparison is therefore a coarse model-fit diagnostic, while the summed-area fraction is less sensitive to polygon subdivision", and that "HydroBASINS lumping and virtual endorheic connections remain semantic limitations". The Antarctica exclusion (`centroid_lat_deg >= -60.0`) is a coverage approximation applied to the generated side, not a reproduction of HydroBASINS' own extent.
- **HydroRIVERS comparison is a coarse-network comparison.** Its `tolerance_basis` records that "coarse grid resolution remains a model-fit limitation". The generated side independently selects ocean-outlet, explicitly non-endorheic watershed backbones over the same area floor; the two selections are analogous, not identical.
- **Seton oceanic-age targets are repository-derived, not published values.** The derived artifact says so explicitly: "the CDF ordinates are not values published in the paper". The mean-age tolerance basis adds that it is "not a claim of local age-field agreement" — the comparison is distributional only. Whatever the age comparison shows, it does not resolve subduction polarity or mass provenance, which the tectonics replays keep marked as unknown; see [Tectonics and Plates](./features/tectonics-and-plates.md) and [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md).
- **Physical time is not calibrated.** Age-based metrics are expressed in Ma because the source datasets are, but the evolution-provenance registry records `physical_time_resolved: False` and `nominal_time_calibrated: False`. A matching age distribution is not evidence that the generator's time axis is physical.
- **Scale matching is an approximation, not an equivalence.** Sampling ETOPO or WorldClim at 4,096 Fibonacci points is nearest-coordinate lookup (`_nearest_coordinate_index`), not area-weighted aggregation. `_geographic_ring_area_km2` uses a flat degrees-to-kilometres scaling at the ring's mean latitude, not a spherical polygon area. The coastal statistic depends on `sample_neighbor_count` and on the symmetrised-kNN adjacency, which is a graph analogue of coastline topology rather than a measured coastline.
- **Missing metrics score zero.** A `score` of `0.0` can mean "far outside the range" or "the world does not have this metric at all"; only `missing_metric` distinguishes them. Never average scores across a report without checking coverage first.
- **The ensemble varies only two coordinates.** `calibrate-ensemble` mutates `run.seed` and `mesh.cell_count` and nothing else, so it bounds seed and resolution sensitivity only. It is not a parameter study of the climate, tectonic, or erosion configuration.
- **Determinism is not tested by calibration.** Unlike the geo validation suite, neither `calibrate` nor `calibrate-ensemble` repeats a generation to compare fingerprints. Reproducibility of the reports themselves depends on generation determinism established elsewhere; see [Testing and Quality Gates](./18-testing.md).
- **`docs/r1_status_audit.md` is a historical snapshot.** Its calibration numbers were measured against the v32 world and `rotating_voronoi_plate_domains_v2` and are explicitly preserved unrewritten; do not read them as current fit.
- **The two bundle formats are not interchangeable, and nothing in the CLI says so.** Passing `configs/geo_validation_earth_empirical_targets.json` to `magic-geo calibrate --targets` fails with `calibration target missing 'dataset'`; passing `configs/calibration_targets.seton_2020_oceanic_age.json` fails with `calibration targets must be a list or an object with a 'targets' list`. Both exit `2`.

## See also

- [CLI Reference](./06-cli-reference.md) — full option, exit-code and default-path tables for `calibrate`, `calibrate-ensemble` and `derive-targets`
- [Validation](./12-validation.md) — the full world-consistency gate, including the `calibration_checks` tail assertions
- [Geo Validation Suite](./13-geo-validation-suite.md) — the empirical target bundle, the Seton supplemental-derivation gate, and per-scenario `empirical_calibration` policy
- [Configuration Reference](./05-configuration-reference.md) — `run.seed` and `mesh.cell_count`, the only two fields the ensemble mutates
- [World Document Schema](./10-world-schema.md) — `calibration_checks`, `watersheds`, `initial_oceanic_crust_age_ledger` and the cell fields the metrics are derived from
- [Python API](./07-python-api.md) — calling `derive_calibration_targets`, `evaluate_calibration_targets` and `evaluate_calibration_ensemble` directly
- [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) — watershed records, endorheic classification and Hack-law fits
- [Tectonics and Plates](./features/tectonics-and-plates.md) — the initial oceanic crust age ledger behind the Seton comparison
- [Climate and Atmosphere](./features/climate-and-atmosphere.md) — the monthly temperature and precipitation fields behind the WorldClim comparison
- [Oceans, Currents and Coasts](./features/oceans-and-coasts.md) — the coastal-cell definition behind the Natural Earth comparison
- [Testing and Quality Gates](./18-testing.md) — `tests/test_calibration.py` and `tests/test_ensemble_calibration.py`
- [Glossary](./21-glossary.md) — coverage, fit, tolerance basis, model-fit tolerance
