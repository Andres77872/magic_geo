# Climate and Atmosphere

[Wiki home](../README.md) > Features

The climate system is a **deterministic equilibrium diagnostic**, not a transient atmospheric solver. A single native function, `compute_climate` (`cpp/src/engine/climate.cpp:251`), derives a twelve-month temperature, precipitation and wind climatology from the planetary parameter snapshot, the current elevation/water field, and a set of latitude-band circulation kernels; four Python enrichers then add continentality, a monthly humidity-storage history with Köppen–Geiger classification, a zero-dimensional radiation budget, and six Earth-analogue plausibility checks. The serialized `climate_model` block declares its own limits verbatim — `mass_conserving_atmosphere: false`, `transient_climate_resolved: false`, and `model_limitation: "equilibrium_diagnostic_climate_without_mass_conserving_three_dimensional_atmosphere"` (`cpp/src/engine/process_serialization.cpp:443-446`) — and this page never upgrades those hedges.

## On this page

- [Where climate runs in the pipeline](#where-climate-runs-in-the-pipeline)
- [The planetary parameter snapshot](#the-planetary-parameter-snapshot)
- [The twelve-month structure and why `months` is a fixed literal](#the-twelve-month-structure-and-why-months-is-a-fixed-literal)
- [Base temperature, the latitude gradient and the area-mean normalization](#base-temperature-the-latitude-gradient-and-the-area-mean-normalization)
- [Lapse rate and the elevation correction](#lapse-rate-and-the-elevation-correction)
- [Stellar luminosity, greenhouse factor and pressure forcing](#stellar-luminosity-greenhouse-factor-and-pressure-forcing)
- [Seasonality: axial tilt, eccentricity and the monsoon term](#seasonality-axial-tilt-eccentricity-and-the-monsoon-term)
- [Atmospheric circulation cells and the subtropical drying strength](#atmospheric-circulation-cells-and-the-subtropical-drying-strength)
- [Prevailing winds and the upwind cache](#prevailing-winds-and-the-upwind-cache)
- [Moisture transport, fetch and orographic effects](#moisture-transport-fetch-and-orographic-effects)
- [Precipitation assembly: the full multiplier chain](#precipitation-assembly-the-full-multiplier-chain)
- [Ocean currents and coastal climate](#ocean-currents-and-coastal-climate)
- [The surface vapour budget](#the-surface-vapour-budget)
- [Serialized per-cell climate fields](#serialized-per-cell-climate-fields)
- [The `climate_model` declaration block](#the-climate_model-declaration-block)
- [Continentality](#continentality)
- [The seasonal climate history record](#the-seasonal-climate-history-record)
- [Climate classification outputs](#climate-classification-outputs)
- [Energy-balance records and insolation](#energy-balance-records-and-insolation)
- [Realism checks: climate and planet regimes](#realism-checks-climate-and-planet-regimes)
- [Validation checks and the layer contract](#validation-checks-and-the-layer-contract)
- [Climate and planet configuration reference](#climate-and-planet-configuration-reference)
- [Worked examples](#worked-examples)
- [Running climate-relevant checks](#running-climate-relevant-checks)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Where climate runs in the pipeline

`compute_climate` has exactly **one** call site in the whole engine: inside the stabilization loop of `stabilize_numeric_depressions` (`cpp/src/engine/hydrology.cpp:1143`). It is never called directly by `pipeline.cpp`.

Each pass of that loop runs, in this fixed order (`hydrology.cpp:1137-1155`):

| Order | Call | Effect |
|---|---|---|
| 1 | `apply_sea_level(params, cells)` | volume-constrained sea-level solve; shifts the sediment-interface datum |
| 2 | `label_marine_water_bodies(cells)` | recomputes `is_water`, `water_body`, marine connectivity |
| 3 | **`compute_climate(params, cells)`** | rewrites every climate field from the new land/sea mask and elevation |
| 4 | `compute_hydrologic_water_budget(...)` | PET, AET, infiltration, runoff from the new climate |
| 5 | `compute_flow_and_rivers(params, cells)` | priority-flood, drainage, river classification |

The loop index runs `0 .. NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES` inclusive, with `NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES = 16` (`cpp/src/engine/constants.hpp:55`), so a single stabilization call performs **at most 17 climate recomputations** and throws `"numeric depression correction did not converge within the bounded pass count"` (`hydrology.cpp:1177-1178`) if candidates remain at the last pass. The realized count per stage is serialized as `climate_recompute_count` on each feedback record (`process_serialization.cpp:2179`) and aggregated as `summary.simulation_clock_climate_recompute_count` (`summary.cpp:1373`).

`stabilize_numeric_depressions` itself is invoked from exactly three call sites — two in `cpp/src/engine/pipeline.cpp` and one in `cpp/src/engine/earth_system.cpp`:

| Stage label | Where | When |
|---|---|---|
| `initial_climate_hydrology` | `pipeline.cpp:107-116` | once, immediately after crust/topography derivation and the identity transport checkpoint |
| `erosion_iteration` | inside `erode`, `cpp/src/engine/earth_system.cpp:1122-1130` | once per maturation iteration, after transport is committed |
| `cryosphere_coupling` | `pipeline.cpp:157-166` | once, after glacial sediment transport, before the terminal cryosphere pass |

Climate is therefore fully **recomputed from scratch** every time relief or the shoreline changes. Nothing about climate is carried forward between stages — there is no atmospheric state vector, no spin-up, and no memory. The `earth_system_feedback_history` records the magnitude of the change between consecutive stages as `mean_abs_temperature_change_c_from_previous_stage` and `mean_abs_precipitation_change_mm_y_from_previous_stage` (`process_serialization.cpp:2398-2401`, computed at `earth_system.cpp:250-284`); those are the only quantities that describe climate *evolution*, and they are stage-indexed differences, not a calibrated time series.

## The planetary parameter snapshot

The twelve planet properties are frozen into the world document at the very top level as `planet_parameters`, emitted with round-trip (`max_digits10`) precision by `planet_parameters_json` (`cpp/src/engine/world_serialization.cpp:23-40`, attached at `:51`). The Python mirror `PLANET_PARAMETER_DEFAULTS` (`src/magic_geo/planet_parameters.py:10-23`) is a duplicated literal of the same twelve keys in the same order and must be kept in sync with `PlanetConfig` manually.

Both `magic_geo.api.generate_world` and `generate_geo_world` gate on this snapshot before any enricher runs: `_require_configured_planet_snapshot` raises `RuntimeError("native planet_parameters do not match the configured planet snapshot")` on any mismatch (`src/magic_geo/api.py:185-192`, called at `:199` and `:303`). `enrich_world_with_planet_realism` re-checks it independently and raises `ValueError("world planet_parameters must match the configured planet snapshot")` (`src/magic_geo/planet_realism.py:82-85`).

How each planet property enters the climate computation:

| Property | Default | Enters climate at | Effect |
|---|---|---|---|
| `radius_km` | `6371.0` | `climate.cpp:199` | converts angular neighbour separation to kilometres in the humidity-transport walk; sets `upwind_ocean_fetch_km` scale and the per-step moisture pickup `clamp(distance_km / 620, 0.10, 0.46)` |
| `gravity_g` | `1.0` | `climate.cpp:259` | `gravity_precip_factor = clamp(1.08 - 0.10 * (gravity_g - 1.0), 0.65, 1.35)` — a global precipitation multiplier only |
| `day_length_hours` | `24.0` | `climate.cpp:29`, `:230`, `:266` | wind `rotation = clamp(24 / max(1, day_length), 0.35, 2.6)`; current `rotation = clamp(24 / max(1, day_length), 0.45, 2.4)` applied as `sqrt(rotation)`; `rotation_band_shift = clamp((day_length - 24) / 24 * 5, -7, 9)` moves the subtropical and midlatitude circulation centres |
| `axial_tilt_deg` | `23.5` | `climate.cpp:395`, `:403` | `seasonal_amp ∝ (axial_tilt_deg / 23.5)`; `axial_wind_factor = clamp(axial_tilt_deg / 23.5, 0.12, 2.4) × eccentricity_season_factor` drives the monsoon wind reversal. Also drives the exact solar declination in the Python daily-mean geometry (`insolation.py`) |
| `orbital_eccentricity` | `0.016` | `climate.cpp:267` | `eccentricity_season_factor = 1.0 + 1.8 * clamp(orbital_eccentricity, 0.0, 0.8)`, a **symmetric amplitude multiplier** on the seasonal cycle. In Python it sets orbital distance and Keplerian seasonal speed; equal-time daily means are integrated within each month (`insolation.py`) |
| `stellar_luminosity` | `1.0` | `core.cpp:9-12` | `climate_stellar_temperature_forcing_c = 38.0 × (L^0.25 − 1.0)`, a uniform temperature offset. Also scales `SOLAR_CONSTANT_W_M2 = 1361.0` in the energy records |
| `atmosphere_pressure_bar` | `1.0` | `climate.cpp:256-258` | `pressure_temp_adj = 4.5 × ln(max(0.01, P))` (uniform temperature offset) and `pressure_precip_factor = clamp(P^0.35, 0.35, 1.85)`. Also `sqrt(P)` scales the Python greenhouse effect (`climate_energy.py`) |
| `greenhouse_factor` | `1.0` | `core.cpp:14-17` | `climate_greenhouse_temperature_forcing_c = 11.0 × (G − 1.0)`, a uniform temperature offset; multiplies the Python greenhouse term |
| `ocean_fraction_target` | `0.70` | — | not read by `compute_climate`, and **not** an input to the sea-level solve either — `apply_sea_level` (`cpp/src/engine/ocean.cpp:5`) constrains on `ocean_water_inventory_km3` alone. It is a reported target: echoed into `sea_level_model_json` and `summary.target_ocean_fraction`, and scored by the `surface_water_inventory` planet-realism check |
| `ocean_water_inventory_km3` | `1338000000.0` | — | not read by `compute_climate`; sets the sea-level solve, which determines the land/sea mask climate then reads |
| `internal_heat` | `1.0` | — | not read by any climate code path |
| `geological_age_ga` | `4.5` | — | not read by any climate code path |

Two of the twelve (`internal_heat`, `geological_age_ga`) have **no climate coupling at all**, and `ocean_fraction_target` has none either — it is a diagnostic target, never a solver input. `ocean_water_inventory_km3` is the only one of the four that couples indirectly, through the shoreline that `apply_sea_level` produces before climate runs.

## The twelve-month structure and why `months` is a fixed literal

`months` is not a tunable resolution knob. It is pinned to `12` at four independent layers:

| Layer | Enforcement | Location |
|---|---|---|
| Config schema | `months: Literal[12] = Field(12, ...)` — any other value is a pydantic validation error | `src/magic_geo/config.py:324-327` |
| Native validation | `if (params.months != 12) throw std::runtime_error("months must be exactly 12")` | `cpp/src/engine/core.cpp:376-377` |
| Native storage | `std::array<double, 12>` for `temperature_monthly_c`, `precipitation_monthly_mm`, `wind_monthly_east`, `wind_monthly_north` | `cpp/src/engine/types/core.hpp:104-109` |
| Python consumers | `_monthly_values` substitutes a flat fallback unless `len(values) == 12`; the Köppen summer/winter index sets are hard-coded month indices | `src/magic_geo/climate_dynamics.py:47-51`, `:91-93` |

The storage layer is the load-bearing reason. `compute_climate` writes `cell.temperature_monthly_c[month]` for `month < params.months` (`climate.cpp:401`, `:473-474`), so any `params.months > 12` would index past a fixed twelve-element `std::array`. The `validate_params` guard is what makes that unreachable: it is called by all four public entry points — `generate_world_json`, `generate_geo_world_json`, `generate_world_msgpack`, `generate_geo_world_msgpack` (`cpp/src/engine.cpp:21`, `:32`, `:43`, `:56`) — before simulation begins.

The validators enforce the same literal downstream: `climate.monthly_annual_climate_closure` requires exactly 12 finite values in each of the four monthly arrays and requires the annual scalars to reconstruct from them within `1.0e-3 °C` and `1.0e-2 mm/y` (`src/magic_geo/geo_validation.py:1444-1483`); `seasonal_climate.seasonal_history_grouping_and_aggregates` requires `len(steps) == 12` and `[step["month"] for step in steps] == list(range(1, 13))` (`src/magic_geo/geo_validation_subsystems.py:480-484`).

`enrich_world_with_climate_energy_balance` reads `month_count = len(cells[0]["temperature_monthly_c"])` and falls back to `12` if that is not a list or is empty (`src/magic_geo/climate_energy.py`). Its insolation series is written generically over `month_count`. In practice it is always 12.

The native temperature cycle peaks at index 6. Python insolation uses a circular-orbit northern solstice at index 5.5, with periapsis at index 0 and a fixed solar longitude of −75° there. On eccentric orbits Kepler's equation determines the changing seasonal speed. The two calendars remain independently specified; the diagnostic does not force native temperature.

## Base temperature, the latitude gradient and the area-mean normalization

The temperature model is declared as `area_mean_normalized_latitude_centered_local_adjustments_v3` (`process_serialization.cpp:381`) and it is built so that **`base_temperature_c` is the global area-mean surface temperature after all local adjustments**, not the equatorial or sea-level value. The serialized `base_temperature_interpretation` says exactly that: `post_centered_local_adjustment_global_area_mean_c` (`:384`).

Two normalizations achieve it.

**1. The latitude term is offset by its own analytic area mean.** The latitude profile is (`climate.cpp:382-389`):

```
latitude_temperature_area_mean_offset_c = CLIMATE_LATITUDE_TEMPERATURE_GRADIENT_C
                                        / (CLIMATE_LATITUDE_TEMPERATURE_EXPONENT + 1.0)

latitude_temp = base_temperature_c
              + latitude_temperature_area_mean_offset_c
              - CLIMATE_LATITUDE_TEMPERATURE_GRADIENT_C * pow(sin(|lat|),
                                                              CLIMATE_LATITUDE_TEMPERATURE_EXPONENT)
```

with `CLIMATE_LATITUDE_TEMPERATURE_GRADIENT_C = 47.0` and `CLIMATE_LATITUDE_TEMPERATURE_EXPONENT = 3.0` (`cpp/src/engine/constants.hpp:7-8`), giving an offset of `47.0 / 4.0 = 11.75 °C`.

The offset is exactly the continuous area mean of the gradient term. On a sphere the area element is proportional to `cos(lat) dlat`, so

```
⟨sin^n|lat|⟩_area = ∫₀^{π/2} sinⁿ(θ) cos(θ) dθ / ∫₀^{π/2} cos(θ) dθ = 1 / (n + 1)
```

which for `n = 3` is `1/4`. Hence `⟨47·sin³|lat|⟩ = 11.75`, and the two terms cancel in the area mean. The equator gets `base + 11.75 °C`; the pole gets `base + 11.75 − 47 = base − 35.25 °C`; the full pole-to-equator span is a fixed `47 °C` regardless of any other setting.

**2. Local adjustments are area-centred.** Before the parallel per-cell loop, `compute_climate` runs a serial pre-pass over every cell (`climate.cpp:270-291`) accumulating

```
local_adjustment = -lapse
                 + (is_water ? CLIMATE_MARINE_ANNUAL_TEMPERATURE_OFFSET_C : 0.0)
                 + current_temp
```

area-weighted by `max(0, area_km2)`, producing `local_temperature_adjustment_area_mean`. That mean is then **subtracted from every monthly temperature** (`climate.cpp:405-408`). The serialized declaration flags this as `local_temperature_adjustments_area_centered: true` with `local_temperature_centering_scope: "elevation_lapse_ocean_current"` (`process_serialization.cpp:440-442`).

`CLIMATE_MARINE_ANNUAL_TEMPERATURE_OFFSET_C = 0.0` (`constants.hpp:10`), so the marine branch of the local adjustment is currently **inert** — it contributes zero in both the pre-pass and the monthly loop. It is still serialized as `marine_annual_temperature_offset_c` in `climate_model`.

The full monthly temperature is therefore (`climate.cpp:405-408`):

```
temp = latitude_temp
     + climate_stellar_temperature_forcing_c
     + climate_greenhouse_temperature_forcing_c
     + 4.5 * ln(max(0.01, atmosphere_pressure_bar))
     + seasonal_amp * season
     - lapse
     + (is_water ? 0.0 : 0.0)
     + current_temp
     - local_temperature_adjustment_area_mean
```

and `cell.temperature_c` is the arithmetic mean over the twelve months (`climate.cpp:477`). Because `Σ_{m=0}^{11} cos(2π(m − 6)/12) = 0` exactly, the seasonal term cancels in the annual mean at every cell.

The consequence is an **exact identity** that the validation suite asserts:

```
area-weighted mean of temperature_c
  = base_temperature_c
  + 38.0 * (stellar_luminosity^0.25 - 1.0)
  + 11.0 * (greenhouse_factor - 1.0)
  + 4.5 * ln(max(0.01, atmosphere_pressure_bar))
```

`climate.configured_global_temperature_response` re-derives that right-hand side from `climate_model.base_temperature_c` and `planet_parameters`, and requires the observed area-weighted mean to match within `0.35 °C` (`src/magic_geo/geo_validation.py:1484-1504`). The source does not annotate why the tolerance is `0.35 °C`; the mechanical reason slack is needed at all is that a discrete mesh only approximates the continuous `⟨sin³|lat|⟩ = 1/4` area mean, so read it as a sampling allowance rather than a physical uncertainty.

## Lapse rate and the elevation correction

The elevation correction is a one-sided dry lapse applied to positive elevation only (`climate.cpp:280-281` in the pre-pass, `:390` in the main loop):

```
lapse = max(0.0, elevation_m) * lapse_rate_c_per_km / 1000.0
```

Points below sea level receive **no** warming — `max(0.0, ...)` clamps the correction to zero rather than inverting it. The default `lapse_rate_c_per_km = 6.5` gives `−6.5 °C/km`; the configurable range is `[0.0, 15.0]` (`config.py:328-333`, native guard `core.cpp:394-395`).

Two properties follow:

- The lapse is computed against `elevation_m`, which is the **derived** surface (bedrock surface + mobile sediment thickness). It therefore changes on every maturation iteration as erosion, deposition and tectonic displacement move the surface — which is precisely why climate is recomputed inside the stabilization loop rather than once.
- Because the lapse enters `local_adjustment`, raising `lapse_rate_c_per_km` cools high ground *and* warms everything else, since the area-mean of the (now larger) lapse is subtracted globally. The global area-mean stays pinned to `base_temperature_c` plus the three uniform forcings, by construction. Tuning the lapse rate changes the **relief-driven temperature contrast**, not the planetary mean.

The `orographic_factor` term of `vertical_velocity_index` is the only other place relief enters the atmospheric fields directly (`climate.cpp:344`); precipitation relief enters separately through `local_relief` (`climate.cpp:15-25`, used at `:417`).

## Stellar luminosity, greenhouse factor and pressure forcing

Three uniform (latitude-independent, cell-independent) temperature offsets are computed once per `compute_climate` call:

| Forcing | Formula | Constant | Source |
|---|---|---|---|
| Stellar | `38.0 * (stellar_luminosity^0.25 - 1.0)` | `CLIMATE_STELLAR_TEMPERATURE_RESPONSE_C = 38.0` | `constants.hpp:14`, `core.cpp:9-12` |
| Greenhouse | `11.0 * (greenhouse_factor - 1.0)` | `CLIMATE_GREENHOUSE_TEMPERATURE_RESPONSE_C = 11.0` | `constants.hpp:15`, `core.cpp:14-17` |
| Pressure | `4.5 * ln(max(0.01, atmosphere_pressure_bar))` | inline literal `4.5` | `climate.cpp:256-257` |

The `L^0.25` exponent mirrors radiative-equilibrium scaling, but the `38.0 °C` coefficient is a **procedural response magnitude, not a derived sensitivity** — nothing in the source claims it is calibrated. The greenhouse coupling is strictly linear in `greenhouse_factor` with an `11.0 °C` per unit response, and `greenhouse_factor = 0` gives `−11 °C` rather than a bare-rock equilibrium.

These same two forcings (but **not** the pressure term) also drive the global precipitation moisture-capacity multiplier (`core.cpp:19-38`):

```
climate_thermal_moisture_temperature_anomaly_c
  = base_temperature_c
  - CLIMATE_THERMAL_MOISTURE_REFERENCE_BASE_TEMPERATURE_C     // 15.0
  + climate_stellar_temperature_forcing_c
  + climate_greenhouse_temperature_forcing_c

climate_thermal_moisture_capacity_factor
  = clamp(exp(clamp(0.04 * anomaly, ln(0.35), ln(2.25))), 0.35, 2.25)
```

| Constant | Value | Source |
|---|---|---|
| `CLIMATE_THERMAL_MOISTURE_REFERENCE_BASE_TEMPERATURE_C` | `15.0` | `constants.hpp:16` |
| `CLIMATE_THERMAL_MOISTURE_RESPONSE_PER_C` | `0.04` | `constants.hpp:20` |
| `CLIMATE_THERMAL_MOISTURE_MIN_FACTOR` | `0.35` | `constants.hpp:21` |
| `CLIMATE_THERMAL_MOISTURE_MAX_FACTOR` | `2.25` | `constants.hpp:22` |

The in-source comment is explicit that the `4 %/°C` response is *deliberately weaker* than saturation-vapour-pressure scaling "because global precipitation is also energy and circulation limited", and that the bounds "keep extreme configured worlds finite without erasing cold/hot ordering" (`constants.hpp:17-19`). The serialized declaration flags it `thermal_moisture_capacity_limitation: "diagnostic_global_scaling_without_explicit_atmospheric_water_mass_or_energy_balance"` (`process_serialization.cpp:436-437`).

Note the asymmetry: **atmospheric pressure changes temperature but not the moisture-capacity anomaly.** A thin-atmosphere world gets colder through `4.5·ln(P)` and drier through `pressure_precip_factor = clamp(P^0.35, 0.35, 1.85)`, but its `thermal_moisture_capacity_factor` is unaffected.

## Seasonality: axial tilt, eccentricity and the monsoon term

The native seasonal amplitude is (`climate.cpp:403-404`):

```
seasonal_amp = (9.0 + 16.0 * continentality)
             * (axial_tilt_deg / 23.5)
             * eccentricity_season_factor
             * sin(lat)

eccentricity_season_factor = 1.0 + 1.8 * clamp(orbital_eccentricity, 0.0, 0.8)
```

with `continentality = 1 − oceanity` and `oceanity = exp(−ocean_distance_hops / 7.5)` (`climate.cpp:324-325`).

| Property | Behaviour |
|---|---|
| Tilt scaling | Strictly linear in `axial_tilt_deg / 23.5`, unbounded upward within the configured `[0, 90]` range. `axial_tilt_deg = 0` zeroes `seasonal_amp`, so the **temperature** cycle vanishes everywhere — but *not* the whole seasonal signal: the monsoon precipitation factor has no tilt term at all, and `axial_wind_factor` is floored at `0.12`, so monthly precipitation and monthly winds still vary |
| Eccentricity | Enters only as a symmetric amplitude multiplier `1 + 1.8·e`, capped at `e = 0.8`. It does **not** produce a perihelion/aphelion asymmetry in the native temperature field — that asymmetry appears only in the Python insolation series |
| Latitude | `sin(lat)` — antisymmetric, so hemispheres are exactly out of phase, and the equator has a strictly zero native seasonal temperature cycle |
| Continentality | Amplitude ranges from `9.0 °C` at a fully maritime cell (`oceanity = 1`) to `25.0 °C` at a fully continental one (`oceanity = 0`), before tilt and eccentricity scaling |

The monsoon term modulates precipitation and wind rather than temperature (`climate.cpp:418-427`):

```
hemisphere_season          = season * (lat >= 0 ? 1.0 : -1.0)
monsoon_band               = exp(-lat_abs_deg² / (2 * 28²))
monsoon_surface_exposure   = is_water ? 0.30 : 0.70 + 0.30 * continentality
monsoon                    = 1.60 * hemisphere_season * monsoon_surface_exposure * monsoon_band
monsoon_precipitation_factor = clamp(1.0 + monsoon, 0.08, 1.92)
monsoon_wind               = clamp(season * axial_wind_factor * continentality * monsoon_band, -1.25, 1.25)
axial_wind_factor          = clamp(axial_tilt_deg / 23.5, 0.12, 2.4) * eccentricity_season_factor
```

| Constant | Value | Source |
|---|---|---|
| `CLIMATE_SEASONAL_MONSOON_PRECIPITATION_STRENGTH` | `1.60` | `constants.hpp:11` |
| `CLIMATE_SEASONAL_MONSOON_PRECIPITATION_MIN_FACTOR` | `0.08` | `constants.hpp:12` |
| `CLIMATE_SEASONAL_MONSOON_PRECIPITATION_MAX_FACTOR` | `1.92` | `constants.hpp:13` |

Monthly wind vectors are assembled from the annual prevailing wind plus the monsoon reversal and an oceanity/longitude term (`climate.cpp:428-442`):

```
raw_wind_east  = wind_east - 1.12 * monsoon_wind * wind_east + 0.18 * oceanity * season * sin(lon)
raw_wind_north = wind_north + 0.76 * monsoon_wind * (lat >= 0 ? 1 : -1) + 0.12 * oceanity * season * cos(lon)
monthly_wind_speed = clamp(0.72 + 0.20 * oceanity + 0.16 * |monsoon_wind| + 0.10 * |wind_divergence_index|, 0.42, 1.15)
wind_monthly_{east,north} = clamp(raw / |raw| * monthly_wind_speed, -1.0, 1.0)
```

The `−1.12 × monsoon_wind × wind_east` coefficient exceeds 1, so a strong monsoon can flip the east component's sign — that is how a seasonal reversal is produced. Two annual diagnostics summarize it (`climate.cpp:447-450`, `:479-484`):

- `mean_seasonal_wind_speed` — the mean of the twelve monthly vector magnitudes.
- `seasonal_wind_reversal_index` — the mean of `clamp((1 − cos∠(monthly, annual)) / 2, 0, 1)`; `0` means every month aligns with the annual prevailing wind, `1` means every month is fully reversed.

## Atmospheric circulation cells and the subtropical drying strength

Four latitude-band Gaussian kernels drive the circulation diagnostics (`climate.cpp:326-331`). Their centres shift with rotation rate:

```
rotation_band_shift = clamp((day_length_hours - 24.0) / 24.0 * 5.0, -7.0, 9.0)
subtropical_center  = 30.0 + rotation_band_shift
midlatitude_center  = 55.0 + 0.5 * rotation_band_shift
```

| Kernel | Centre (deg) | σ (deg) | Expression |
|---|---|---|---|
| `tropical_ascent` | `0.0` | `13.0` | `exp(-lat²/(2·13²))` |
| `subtropical_high` | `subtropical_center` | `9.5` | `exp(-(lat - c)²/(2·9.5²))` |
| `subpolar_low` | `midlatitude_center` | `11.0` | `exp(-(lat - c)²/(2·11²))` |
| `polar_high` | `82.0` (fixed) | `12.0` | `exp(-(lat - 82)²/(2·12²))` |

The discrete `atmospheric_cell` label is assigned by a separate cascade (`climate.cpp:332-340`), with names from `ATMOSPHERIC_CELL_NAMES` (`cpp/src/engine/schema_names.hpp:31-33`):

| Index | Serialized name | Condition (evaluated in order) |
|---|---|---|
| `0` | `tropical_ascent` | `\|lat\| < 18.0` |
| `1` | `subtropical_high` | `\|\|lat\| − subtropical_center\| < 14.0` |
| `2` | `midlatitude_westerly` | `\|lat\| < 66.0` |
| `3` | `polar_cell` | otherwise |

Because the cascade is ordered and the second test is centred on a *shifted* centre, the band edges are not identical to the kernel centres, and on a slowly rotating world (`rotation_band_shift = +9`) the subtropical test window is `[25°, 53°]` while the tropical test still cuts at `18°`.

The three continuous circulation indices (`climate.cpp:341-364`):

| Field | Formula | Range |
|---|---|---|
| `vertical_velocity_index` | `clamp(0.58·trop + 0.36·subpolar − 0.46·subtrop − 0.24·polar + 0.16·max(0, orographic_factor − 1), −1, 1)` | `[−1, 1]`, positive = ascent |
| `wind_divergence_index` | `clamp(0.54·subtrop + 0.30·polar − 0.46·trop − 0.34·subpolar, −1, 1)` | `[−1, 1]`, positive = divergence |
| `surface_pressure_anomaly_hpa` | `clamp(10.5·wind_divergence_index − 3.0·vertical_velocity_index, −22, 22)` | `[−22, 22]` hPa |

and the resulting precipitation modifier:

```
circulation_precip_factor = clamp(1.0 + 0.22 * max(0, vertical_velocity_index)
                                      - 0.18 * max(0, wind_divergence_index), 0.66, 1.26)
```

**Subtropical drying** is a separate, explicitly configurable mechanism applied inside the monthly loop (`climate.cpp:452-458`). It uses its own Gaussian (centre `30 + rotation_band_shift`, σ = 10), not the `subtropical_high` kernel above:

```
cold_current_drying_index = clamp(-ocean_current_temperature_c / 4.5, 0.0, 1.0)
subtropical_drying_factor = clamp(1.0 - subtropical_drying_strength
                                        * subtropic
                                        * (1.0 + 0.15 * cold_current_drying_index),
                                  CLIMATE_SUBTROPICAL_DRYING_MIN_FACTOR, 1.0)
```

with `CLIMATE_SUBTROPICAL_DRYING_MIN_FACTOR = 0.25` (`constants.hpp:9`). At the default `subtropical_drying_strength = 0.65`, a cell exactly on the subtropical centre with a neutral current gets a `0.35×` precipitation multiplier; with a fully cold current (`ocean_current_temperature_c = −4.5`) the multiplier becomes `1 − 0.65·1·1.15 = 0.2525`, just above the `0.25` floor. The configured range is `[0.0, 0.9]` (`config.py:346-351`, native guard `core.cpp:391-392`).

## Prevailing winds and the upwind cache

The annual prevailing wind depends only on latitude band, hemisphere and rotation rate (`climate.cpp:27-42`):

| `\|lat\|` band | `east` (pre-scale) | `north` (northern hemisphere) | `north` (southern) |
|---|---|---|---|
| `< 30°` | `-1.00` | `-0.22` | `+0.22` |
| `30° – 60°` | `+1.00` | `+0.16` | `-0.16` |
| `≥ 60°` | `-0.75` | `-0.18` | `+0.18` |

`east` is then multiplied by `rotation = clamp(24.0 / max(1.0, day_length_hours), 0.35, 2.6)` and the pair is normalized to unit length. The sign pattern (negative-east in the tropics and polar cap, positive-east in midlatitudes) is consistent with trade-easterly / westerly / polar-easterly structure, but it is hard-coded, not derived. The `day_length_hours` config description calls this "Coriolis forcing" (`config.py:177`); no Coriolis term is computed anywhere — `rotation` is the bare ratio `24 / day_length_hours`, clamped. A fast-rotating world (short day) increases `rotation` and therefore makes the zonal component dominate the meridional one after normalization.

Because there are exactly three bands × two hemispheres, there are `PREVAILING_WIND_REGIME_COUNT = 6` distinct wind vectors on any mesh (`climate.cpp:44`, regime index `2·band + hemisphere` at `:47-57`). `build_prevailing_wind_upwind_cache` (`climate.cpp:94-133`) exploits this: for each of the 6 regimes and each cell it precomputes the single best-aligned upwind neighbour once, in an OpenMP `collapse(2)` loop, and every later path step reads the cache.

`upwind_neighbor_for_wind` (`climate.cpp:59-78`) selects the neighbour whose *outgoing* direction best matches the wind, in a local tangent frame:

```
dx = wrap_angle(cell.lon - source.lon) * cos(cell.lat)
dy = cell.lat - source.lat
alignment = (dx/|d|) * wind_east + (dy/|d|) * wind_north
```

The comparison is a strict `>`, so ties are resolved by neighbour ordering. The in-source comment records the reasoning: "Geometry is immutable during `compute_climate`. Reusing this strict-`>` result preserves neighbor-order ties while avoiding a rescan per path step" (`climate.cpp:115-116`). The argument is that `upwind_neighbor_for_wind` is a pure function of geometry and the regime wind, both of which are fixed for the duration of a call — but the codebase asserts no cached-versus-uncached parity result, so treat this as a documented rationale rather than a proven equivalence.

## Moisture transport, fetch and orographic effects

Two distinct orographic mechanisms exist and must not be conflated.

**1. The single-step orographic and rain-shadow factors** (`climate.cpp:135-151`) look only at the immediate upwind neighbour:

```
if (upwind < 0 || best_alignment < 0.12) return {1.0, 1.0};
climb   = max(0, elevation - upwind_elevation)
descent = max(0, upwind_elevation - elevation)
orographic_factor  = clamp(1.0 + 0.42 * clamp(climb / 1600, 0, 1) * alignment, 0.70, 1.45)
rain_shadow_factor = clamp(1.0 - 0.48 * clamp(descent / 1800, 0, 1) * alignment, 0.48, 1.00)
```

Both default to `1.0` when the wind is poorly aligned (`alignment < 0.12`). The serialized clamp bounds are `[0.70, 1.45]` and `[0.48, 1.00]`, but neither outer bound is reachable: `alignment` is a dot product of unit vectors so `alignment ≤ 1`, which caps `orographic_factor` at `1 + 0.42 = 1.42` (a 42 % enhancement) and floors `rain_shadow_factor` at `1 − 0.48 = 0.52` (a 48 % suppression). The clamps are non-binding guards, not the realized extremes.

**2. The multi-step humidity transport walk** (`humidity_transport_along_wind`, `climate.cpp:159-226`) marches upwind for a bounded number of hops:

```
max_steps = clamp(cell_count / 256 + 10, 10, MAX_HUMIDITY_TRANSPORT_STEPS)   // MAX = 34
parcel    = is_water ? 0.72 : 0.08
fetch_km  = is_water ? 120.0 : 0.0
decay     = 1.0
```

Per step (stop conditions: no upwind neighbour, `alignment < 0.10`, or a revisit of an already-visited cell):

| Source cell kind | Effect |
|---|---|
| `is_water`, `water_body == 1` (ocean) | `source_strength = 1.00` |
| `is_water`, `water_body == 2` (continental shelf) | `source_strength = 0.82` |
| `is_water`, other (`inland_sea`) | `source_strength = 0.68` |
| any of the above | `fetch_km += distance_km * source_strength * decay`; `parcel += decay * source_strength * clamp(distance_km / 620, 0.10, 0.46)` |
| `is_lake` or `water_body ∈ {4, 5}` (fresh lake / saline basin) | `parcel += 0.12 * decay` — no fetch contribution |
| land | `parcel *= 0.93` |

Then, for every step regardless of kind:

```
rainout += decay * clamp(climb / 2600, 0.0, 1.2)
parcel  *= 1.0 - 0.18 * clamp(climb / 2600, 0.0, 1.0)
parcel  *= 1.0 - 0.04 * clamp(descent / 2200, 0.0, 1.0)
decay   *= 0.88
```

with `distance_km = max(1.0, angular_distance(source, target) * radius_km)` — the only place `radius_km` enters climate. The results:

```
upwind_ocean_fetch_km   = fetch_km
humidity_transport_index = clamp(parcel / (1.0 + 0.18 * rainout), 0.0, 1.35)
advected_moisture_factor = clamp(0.82 + 0.28 * humidity_transport_index, 0.70, 1.20)
```

Note that `humidity_transport_index` is bounded at `1.35`, above the `[0, 1]` range that several downstream consumers assume — `climate_continentality.py:197` and `climate.cpp:497` both explicitly `clamp(..., 0, 1)` before use.

The visited-set is a fixed `std::array<int, MAX_HUMIDITY_TRANSPORT_STEPS + 1>` scanned linearly (`climate.cpp:177`, `:187-196`), so the walk is allocation-free and the cycle guard is exact.

## Precipitation assembly: the full multiplier chain

Inside the monthly loop, a latitude/oceanity/relief base is computed and then multiplied by ten factors (`climate.cpp:410-472`). The base uses its own Gaussians, distinct from the circulation kernels:

| Base kernel | Centre | σ | Coefficient |
|---|---|---|---|
| `equator` | `0°` | `18` | `+1450` |
| `mid` | `55 + 0.5·rotation_band_shift` | `13` | `+680` |
| `subtropic` | `30 + rotation_band_shift` | `10` | `−610` |

```
relief = clamp(local_relief(cells, i) / 2200.0, 0.0, 1.0)
annual = 170.0 + 1450.0*equator + 680.0*mid - 610.0*subtropic + 560.0*oceanity + 320.0*relief
annual *= is_water ? 1.20 : 1.0
```

`local_relief` (`climate.cpp:15-25`) is `max(0, elevation − mean(neighbour elevations))` — a positive-only local prominence, zero for cells with no neighbours.

Then the multiplier chain, in exactly this source order (`climate.cpp:460-463`):

| # | Factor | Range | Source |
|---|---|---|---|
| 1 | `precipitation_scale` | `[0.0, 10.0]` config | `config.py:340-345` |
| 2 | `pressure_precip_factor = clamp(P^0.35, 0.35, 1.85)` | `[0.35, 1.85]` | `climate.cpp:258` |
| 3 | `gravity_precip_factor = clamp(1.08 − 0.10·(g − 1), 0.65, 1.35)` | `[0.65, 1.35]` | `climate.cpp:259` |
| 4 | `orographic_factor` | `[0.70, 1.45]` | `climate.cpp:148,150` |
| 5 | `rain_shadow_factor` | `[0.48, 1.00]` | `climate.cpp:149,150` |
| 6 | `ocean_current_moisture_factor` | `[0.72, 1.28]` | `climate.cpp:375-379` |
| 7 | `advected_moisture_factor` | `[0.70, 1.20]` | `climate.cpp:224` |
| 8 | `circulation_precip_factor` | `[0.66, 1.26]` | `climate.cpp:359-364` |
| 9 | `subtropical_drying_factor` | `[0.25, 1.00]` | `climate.cpp:453-458` |
| 10 | `monsoon_precipitation_factor` | `[0.08, 1.92]` | `climate.cpp:422-426` |

Finally (`climate.cpp:464-472`):

```
monthly_precip = max(0.0, annual) / months
if (thermal_moisture_capacity_factor != 1.0) monthly_precip *= thermal_moisture_capacity_factor
```

Two behaviours are declared explicitly in `climate_model` and are worth stating precisely:

- `negative_precipitation_behavior: "clamped_to_zero_before_thermal_moisture_multiplier"` (`process_serialization.cpp:396-397`). The `−610·subtropic` term can make the raw sum negative; the in-source comment says "Negative empirical combinations are nonphysical and clamp to zero. Near-zero positive forcing remains near zero instead of crossing a discontinuous minimum-rainfall branch" (`climate.cpp:464-466`). There is **no** minimum-rainfall floor.
- `zero_precipitation_scale_behavior: "exact_zero_monthly_and_annual_precipitation"` (`:398-399`). `precipitation_scale = 0` produces exactly `0.0` in every month and in `precipitation_mm_y`, which is a clean dry boundary for tests.

`cell.precipitation_mm_y` is the **sum** of the twelve monthly values (`climate.cpp:475`, `:478`), not their mean — this is why the monthly-closure validator tests `|precipitation_mm_y − Σ monthly| ≤ 1.0e-2` while it tests `|temperature_c − mean(monthly)| ≤ 1.0e-3`.

## Ocean currents and coastal climate

The ocean-current vector field is a fixed latitude/longitude analytic pattern with a rotation-rate scaling on the zonal component (`climate.cpp:228-249`):

| `\|lat\|` band | `east` (pre-scale) | `north` |
|---|---|---|
| `< 12°` | `-1.00` | `0.16 · sin(lon)` |
| `12° – 35°` | `-0.72` | `(lat ≥ 0 ? +0.42 : −0.42) · sin(lon)` |
| `35° – 62°` | `+0.86` | `(lat ≥ 0 ? −0.34 : +0.34) · cos(lon)` |
| `≥ 62°` | `-0.42` | `lat ≥ 0 ? −0.22 : +0.22` |

`east` is multiplied by `sqrt(clamp(24 / max(1, day_length_hours), 0.45, 2.4))` and the pair is normalized. The `sin(lon)` / `cos(lon)` factors give the gyre-like meridional alternation with longitude; there is no basin geometry input.

Three derived fields (`climate.cpp:365-379`), all attenuated by `oceanity = exp(−ocean_distance_hops / 7.5)` so the influence decays inland:

```
ocean_current_east  = current.east  * oceanity
ocean_current_north = current.north * oceanity
poleward_current    = lat >= 0 ? current.north : -current.north
ocean_current_temperature_c = oceanity * clamp(3.8 * poleward_current
                                             + 1.2 * cos(lat) * sin(lon), -4.5, 4.5)
ocean_current_moisture_factor = clamp(1.0 + oceanity * (0.045 * max(0, ct)
                                                      - 0.035 * max(0, -ct)), 0.72, 1.28)
```

The temperature anomaly is bounded to `±4.5 °C` before the oceanity attenuation. It feeds three consumers:

1. The monthly temperature directly, as `current_temp` (`climate.cpp:407`) — but it is also part of `local_adjustment`, so its **area mean is removed globally** and only the spatial pattern survives.
2. The subtropical drying factor, through `cold_current_drying_index = clamp(−ct / 4.5, 0, 1)`, so cold currents deepen the subtropical dry belt by up to a further 15 % (`climate.cpp:452-457`).
3. The Python radiative equilibrium, as `equilibrium_c += ocean_current_temperature_c * 0.35` (`climate_energy.py`).

The moisture factor is deliberately asymmetric: warm anomalies add `0.045` per °C, cold anomalies subtract only `0.035` per °C. Both `cold_current_coastal_drying` and `warm_current_climate_moderation` realism checks read this field (see below).

`ocean_distance` (`cpp/src/engine/ocean.cpp:323-349`) is an unweighted BFS in **neighbour hops**, seeded from every `is_water` cell, with unreachable cells assigned the cell count `n`. So `oceanity` is a hop-count decay, not a kilometre decay — on a coarse mesh one hop is a much larger physical distance than on a fine one, which makes `oceanity` (and therefore `continentality`, `seasonal_amp` and the `+560·oceanity` precipitation term) **mesh-resolution dependent**. The Python `distance_to_marine_water_km` field is the great-circle counterpart and does not share this property.

## The surface vapour budget

After the monthly loop, six annual moisture diagnostics are written per cell (`climate.cpp:485-514`):

```
pet = max(0.0, temperature_c + 8.0) * 31.0
```

matching `HYDROLOGIC_PET_TEMPERATURE_OFFSET_C = 8.0` and `HYDROLOGIC_PET_SCALE_MM_Y_PER_C = 31.0` (`constants.hpp:48-49`), though written as inline literals here.

| Field | Formula | Notes |
|---|---|---|
| `vapor_evaporation_mm_y` | water (`water_body ∈ {1,2,3}`): `760 + 28·max(0,T) + 90·ocean_current_moisture_factor`; land: `min(max(0,P)·clamp(0.38 + 0.22·oceanity, 0.28, 0.72), pet·clamp(0.42 + 0.24·humidity_transport_index, 0.25, 0.86))`; then `clamp(·, 0, 2400)` | lakes (`water_body ∈ {4,5}`) fall into the **else** branch of the `water_evaporation` ternary, i.e. `0.0`, but the final selector is `cell.is_water` (`climate.cpp:493`), so a lake cell with `is_water == true` receives `0.0` rather than the land expression |
| `precipitation_recycling_fraction` | `clamp((is_water ? 0.06 : 0.12) + 0.34·continentality + 0.14·clamp(hti,0,1) + 0.08·clamp(oro−1, 0, 0.6), 0.03, is_water ? 0.22 : 0.68)` | upper bound differs by surface type |
| `moisture_convergence_mm_y` | `max(0, P − min(P, vapor_evaporation·recycling_fraction))` | the imported (non-recycled) share of annual precipitation |
| `orographic_rainout_mm_y` | `P · clamp(0.46·max(0, oro−1) + 0.18·max(0, 1−shadow), 0, 0.55)` | at most 55 % of annual precipitation |
| `vapor_deficit_mm_y` | `max(0, pet − P)` | |
| `vapor_budget_residual_mm_y` | `P − (recycled_source + moisture_convergence_mm_y)` | |

The residual is an **identity by construction**: `recycled_source = min(P, ...) ≤ P`, so `moisture_convergence = P − recycled_source` exactly and the residual is zero in exact arithmetic. `summary.mean_abs_vapor_budget_residual_mm_y` (`summary.cpp:2061-2062`) therefore measures floating-point closure of an algebraic rearrangement, **not** physical conservation of atmospheric water. The `climate_model` declaration is consistent: `mass_conserving_atmosphere: false`.

## Serialized per-cell climate fields

Written by `cells_json` (`cpp/src/engine/entity_serialization.cpp:189-217`) at the configured `output.float_precision` (default 4). Complete list, in serialization order:

| Field | Type | Range / units | Produced at | Meaning |
|---|---|---|---|---|
| `temperature_c` | double | °C | `climate.cpp:477` | mean of the twelve monthly values |
| `temperature_monthly_c` | double[12] | °C | `climate.cpp:473` | monthly surface temperature |
| `precipitation_mm_y` | double | mm/y, `≥ 0` | `climate.cpp:478` | **sum** of the twelve monthly values |
| `precipitation_monthly_mm` | double[12] | mm, `≥ 0` | `climate.cpp:474` | monthly precipitation |
| `wind_east` | double | unit vector component | `climate.cpp:304` | annual prevailing wind, east component |
| `wind_north` | double | unit vector component | `climate.cpp:305` | annual prevailing wind, north component |
| `wind_monthly_east` | double[12] | `[−1, 1]` | `climate.cpp:441` | monthly wind, east component |
| `wind_monthly_north` | double[12] | `[−1, 1]` | `climate.cpp:442` | monthly wind, north component |
| `mean_seasonal_wind_speed` | double | `≤ 1.15` index | `climate.cpp:479` | mean monthly wind magnitude. The per-month speed is clamped to `[0.42, 1.15]`, but the expression starts at `0.72` with only non-negative addends, so the `0.42` floor is unreachable |
| `seasonal_wind_reversal_index` | double | `[0, 1]` | `climate.cpp:480-484` | `0` = no reversal, `1` = fully reversed every month |
| `atmospheric_cell` | string | one of 4 names | `climate.cpp:332-340` | `tropical_ascent` / `subtropical_high` / `midlatitude_westerly` / `polar_cell` |
| `surface_pressure_anomaly_hpa` | double | `[−22, 22]` hPa | `climate.cpp:354-358` | diagnostic pressure anomaly |
| `vertical_velocity_index` | double | `[−1, 1]` | `climate.cpp:341-347` | positive = ascent |
| `wind_divergence_index` | double | `[−1, 1]` | `climate.cpp:348-353` | positive = divergence |
| `ocean_current_east` | double | unit component × oceanity | `climate.cpp:366` | current vector, east |
| `ocean_current_north` | double | unit component × oceanity | `climate.cpp:367` | current vector, north |
| `ocean_current_temperature_c` | double | `[−4.5, 4.5]` × oceanity | `climate.cpp:374` | current thermal anomaly |
| `ocean_current_moisture_factor` | double | `[0.72, 1.28]` | `climate.cpp:375-379` | current-driven precipitation multiplier |
| `humidity_transport_index` | double | `[0, 1.35]` | `climate.cpp:320` | advected moisture parcel index |
| `upwind_ocean_fetch_km` | double | km, `≥ 0` | `climate.cpp:321` | decayed upwind over-water path length |
| `advected_moisture_factor` | double | `[0.70, 1.20]` | `climate.cpp:322` | precipitation multiplier from transport |
| `orographic_factor` | double | `[0.70, 1.45]` | `climate.cpp:311` | single-step upslope enhancement |
| `rain_shadow_factor` | double | `[0.48, 1.00]` | `climate.cpp:312` | single-step downslope suppression |
| `vapor_evaporation_mm_y` | double | `[0, 2400]` mm/y | `climate.cpp:493` | annual surface evaporation |
| `moisture_convergence_mm_y` | double | mm/y, `≥ 0` | `climate.cpp:506` | imported (non-recycled) precipitation |
| `orographic_rainout_mm_y` | double | `≤ 0.55 × P` | `climate.cpp:507-512` | orographically attributed rainfall |
| `precipitation_recycling_fraction` | double | `[0.03, 0.68]` | `climate.cpp:494-501` | local-evaporation share of precipitation |
| `vapor_deficit_mm_y` | double | mm/y, `≥ 0` | `climate.cpp:513` | `max(0, PET − P)` |
| `vapor_budget_residual_mm_y` | double | mm/y, `≈ 0` | `climate.cpp:514` | algebraic residual of the recycling identity |

Global aggregates written into `summary` by `summary_json` (`cpp/src/engine/summary.cpp:2028-2068`):

| Summary key | Definition |
|---|---|
| `mean_orographic_factor`, `mean_rain_shadow_factor` | per-cell means |
| `rain_shadowed_land_fraction` | land cells with `rain_shadow_factor < 0.86`, over land count (`summary.cpp:508-510`) |
| `mean_humidity_transport_index`, `mean_upwind_ocean_fetch_km`, `mean_advected_moisture_factor` | per-cell means |
| `atmospheric_cell_counts` | map of the four band names → cell counts (`summary.cpp:2038`) |
| `mean_surface_pressure_anomaly_hpa`, `mean_vertical_velocity_index`, `mean_wind_divergence_index` | per-cell means |
| `mean_seasonal_wind_speed`, `mean_seasonal_wind_reversal_index` | per-cell means |
| `ascending_air_fraction` | cells with `vertical_velocity_index > 0.12`, over all cells (`summary.cpp:511-513`) |
| `mean_vapor_evaporation_mm_y`, `mean_moisture_convergence_mm_y`, `mean_orographic_rainout_mm_y`, `mean_precipitation_recycling_fraction`, `mean_vapor_deficit_mm_y` | per-cell means |
| `mean_abs_vapor_budget_residual_mm_y` | mean of `\|vapor_budget_residual_mm_y\|` |
| `mean_ocean_current_strength`, `mean_ocean_current_temperature_c`, `mean_ocean_current_moisture_factor` | per-cell means |

## The `climate_model` declaration block

`climate_model_json` (`cpp/src/engine/process_serialization.cpp:369-449`) emits a 39-key read-only declaration at world top level, attached by `serialize_world` at `cpp/src/engine/world_serialization.cpp:86`. Numeric values use `precision = max(6, params.float_precision)`.

| Key | Value / source | Kind |
|---|---|---|
| `model_type` | `"equilibrium_latitude_circulation_climate_v5"` | declaration |
| `temperature_model` | `"area_mean_normalized_latitude_centered_local_adjustments_v3"` | declaration |
| `precipitation_model` | `"bounded_thermal_moisture_circulation_orography_wind_transport_v3"` | declaration |
| `base_temperature_interpretation` | `"post_centered_local_adjustment_global_area_mean_c"` | declaration |
| `base_temperature_c` | `params.base_temperature_c` | echoed config |
| `latitude_temperature_gradient_c` | `47.0` | constant |
| `latitude_temperature_exponent` | `3.0` | constant |
| `latitude_temperature_area_mean_offset_c` | `47.0 / 4.0 = 11.75` | derived |
| `lapse_rate_c_per_km` | `params.lapse_rate_c_per_km` | echoed config |
| `marine_annual_temperature_offset_c` | `0.0` | constant (currently inert) |
| `precipitation_scale` | `params.precipitation_scale` | echoed config |
| `negative_precipitation_behavior` | `"clamped_to_zero_before_thermal_moisture_multiplier"` | declaration |
| `zero_precipitation_scale_behavior` | `"exact_zero_monthly_and_annual_precipitation"` | declaration |
| `subtropical_drying_strength` | `params.subtropical_drying_strength` | echoed config |
| `subtropical_drying_min_factor` | `0.25` | constant |
| `seasonal_monsoon_precipitation_strength` | `1.60` | constant |
| `seasonal_monsoon_precipitation_min_factor` | `0.08` | constant |
| `seasonal_monsoon_precipitation_max_factor` | `1.92` | constant |
| `thermal_moisture_capacity_model` | `"bounded_exponential_global_temperature_anomaly_v1"` | declaration |
| `thermal_moisture_capacity_scope` | `"global_monthly_precipitation_multiplier"` | declaration |
| `thermal_moisture_capacity_temperature_anomaly_basis` | `"base_temperature_plus_stellar_and_greenhouse_forcing_relative_to_earth_reference"` | declaration |
| `thermal_moisture_capacity_reference_base_temperature_c` | `15.0` | constant |
| `thermal_moisture_capacity_reference_stellar_luminosity` | `1.0` | constant |
| `thermal_moisture_capacity_reference_greenhouse_factor` | `1.0` | constant |
| `thermal_moisture_capacity_stellar_temperature_response_c` | `38.0` | constant |
| `thermal_moisture_capacity_greenhouse_temperature_response_c` | `11.0` | constant |
| `thermal_moisture_capacity_temperature_response_per_c` | `0.04` | constant |
| `thermal_moisture_capacity_min_factor` | `0.35` | constant |
| `thermal_moisture_capacity_max_factor` | `2.25` | constant |
| `thermal_moisture_capacity_temperature_anomaly_c` | computed for this run | derived |
| `thermal_moisture_capacity_factor` | computed for this run | derived |
| `thermal_moisture_capacity_limitation` | `"diagnostic_global_scaling_without_explicit_atmospheric_water_mass_or_energy_balance"` | **limitation** |
| `configured_month_count` | `params.months` (always 12) | echoed config |
| `latitude_temperature_area_normalized` | `true` | assertion |
| `local_temperature_adjustments_area_centered` | `true` | assertion |
| `local_temperature_centering_scope` | `"elevation_lapse_ocean_current"` | declaration |
| `mass_conserving_atmosphere` | `false` | **negative claim** |
| `transient_climate_resolved` | `false` | **negative claim** |
| `model_limitation` | `"equilibrium_diagnostic_climate_without_mass_conserving_three_dimensional_atmosphere"` | **limitation** |

## Continentality

`enrich_world_with_climate_continentality` (`src/magic_geo/climate_continentality.py:178-241`) runs early — position 6 in `generate_world`, position 9 in `generate_geo_world` (`src/magic_geo/api.py:205`, `:322`) — because several later enrichers read its outputs.

It performs a **multi-source Dijkstra** over the cell graph seeded from every marine cell (`_nearest_marine_distances`, `:86-107`). `MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}` (`:9`); if no marine cell exists it falls back to all `is_water` cells (`:90-92`). Edge lengths come from `world["cell_adjacency_edges"][].great_circle_distance_km` when available, otherwise from each cell's `mean_neighbor_edge_length_km` (`_distance_graph`, `:62-83`). Unreachable cells receive the largest finite distance found (`:106-107`).

| Cell field | Formula | Range |
|---|---|---|
| `distance_to_marine_water_km` | Dijkstra distance, `≥ 0` | km |
| `continentality_index` | `clamp(0.58·clamp(d/3000) + 0.30·clamp(ΔT_monthly/34) + 0.12·(1 − clamp(hti)))`; marine cells additionally `min(·, 0.18)` | `[0, 1]` |
| `oceanic_humidity_availability_index` | `clamp(0.36·exp(−d/1200) + 0.30·clamp(fetch/2500) + 0.20·clamp((advected − 0.65)/0.85) + 0.14·clamp(hti))`; marine cells additionally `max(·, 0.75)` | `[0, 1]` |
| `marine_influence_class` | see below | 5 classes |
| `climate_continentality_region_id` | connected-component id over same-class neighbours | `≥ 0` |

`_marine_influence_class` (`:110-119`) is an ordered cascade:

| Class | Condition |
|---|---|
| `marine` | `water_body_type ∈ MARINE_WATER_TYPES` |
| `coastal` | `distance ≤ 250 km` **or** `continentality < 0.24` |
| `maritime_influenced` | `distance ≤ 1000 km` **or** `continentality < 0.45` |
| `interior` | `distance ≤ 2500 km` **or** `continentality < 0.68` |
| `continental_core` | otherwise |

Regions are BFS connected components of equal-class neighbours, seeded from the lowest remaining cell id for determinism (`_connected_regions`, `:148-175`). Each `climate_continentality_regions[]` record carries `id`, `region_class`, sorted `cell_ids`, `cell_count`, `area_km2`, `centroid_lat_deg`, `centroid_lon_deg`, `mean_distance_to_marine_water_km`, `mean_continentality_index`, `mean_oceanic_humidity_availability_index`, `mean_temperature_range_c`, `mean_precipitation_mm_y`, `land_cell_count`, `marine_cell_count` and `dominant_atmospheric_cell` (`_region_record`, `:122-145`).

Summary keys added: `mean_distance_to_marine_water_km`, `mean_continentality_index`, `max_continentality_index`, `high_continentality_cell_count` (`≥ 0.65`), `mean_oceanic_humidity_availability_index`, `low_oceanic_humidity_availability_cell_count` (`≤ 0.25`), `marine_influence_class_counts`, `climate_continentality_region_count`, `continental_core_region_count`, `maritime_influence_region_count` (`:228-239`).

Note the deliberate divergence: this `continentality_index` is a **different quantity** from the native `continentality = 1 − exp(−hops/7.5)` used inside `compute_climate`. The native one is a hop-count decay used to set seasonal amplitude and the oceanity precipitation term; the Python one is a great-circle-distance blend that also folds in the monthly temperature range and the humidity transport index. They are not required to agree and nothing asserts that they do.

## The seasonal climate history record

`enrich_world_with_seasonal_climate_history` (`src/magic_geo/climate_dynamics.py:178-398`) does two things: it writes four per-cell seasonality fields plus a Köppen class, and it builds one 12-step humidity-storage budget **per `atmospheric_cell` group** (not per cell).

Per-cell fields (`_cell_seasonality`, `:149-175`):

| Field | Formula | Range |
|---|---|---|
| `seasonal_precipitation_range_mm` | `max(monthly) − min(monthly)` | mm |
| `seasonal_aridity_index` | `clamp(Σ max(0, E_m − P_m) / max(1, P_annual + E_annual))` | `[0, 1]` |
| `cell_monsoon_index` | `clamp(range / max(1, P_annual))` | `[0, 1]` |
| `seasonal_humidity_regime` | ordered cascade below | 5 values |
| `climate_class` | `classify_koppen_geiger(cell)` | 30 codes |

Monthly evaporation is *disaggregated* from the annual scalar `vapor_evaporation_mm_y` using temperature weights `max(0.05, 1 + T_m/35)` normalized to sum to 1 (`_temperature_evaporation_weights`, `:61-66`). There is no independently simulated monthly evaporation field.

The regime cascade (`:165-174`):

| Regime | Condition (first match wins) |
|---|---|
| `arid_seasonal` | `P_annual ≤ 150 mm` **or** `seasonal_aridity ≥ 0.65` |
| `monsoonal` | `monsoon_index ≥ 0.22` **and** `max(monthly) ≥ 1.65 × mean(monthly)` |
| `winter_wet` | wettest month in the hemisphere's winter set **and** `monsoon_index ≥ 0.12` |
| `summer_wet` | wettest month in the hemisphere's summer set **and** `monsoon_index ≥ 0.12` |
| `humid_stable` | otherwise |

Summer/winter month sets are `{6,7,8}` / `{12,1,2}` for the northern hemisphere and swapped for the southern (`:163-164`), using 1-based month numbers.

### `climate_seasonal_histories[]` field table

One record per distinct `atmospheric_cell` value present in the mesh, sorted by name (`:221`).

| Field | Type | Meaning |
|---|---|---|
| `id` | int | sequential index |
| `atmospheric_cell` | string | the group's band name |
| `cell_count` | int | number of cells in the group |
| `time_step_count` | int | always `12` |
| `annual_precipitation_mm` | float | Σ of step `precipitation_mm` |
| `annual_evaporation_mm` | float | Σ of step `evaporation_mm` |
| `annual_moisture_convergence_mm` | float | Σ of step `moisture_convergence_mm` |
| `annual_humidity_export_mm` | float | Σ of step `humidity_export_mm` |
| `annual_vapor_deficit_mm` | float | Σ of step `vapor_deficit_mm` |
| `max_humidity_storage_mm` | float | maximum end-of-month storage across the 12 steps |
| `mean_temperature_c` | float | mean of the 12 step temperatures |
| `wettest_month` | int | 1-based index of the wettest step |
| `driest_month` | int | 1-based index of the driest step |
| `seasonal_precipitation_range_mm` | float | `max − min` of step precipitation |
| `monsoon_index` | float | `clamp(range / max(1, annual))` |
| `max_drying_risk` | float | maximum step `drying_risk` |
| `steps` | list[12] | see below |

### `climate_seasonal_histories[].steps[]` field table

| Field | Type | Meaning |
|---|---|---|
| `month` | int | 1–12 |
| `mean_temperature_c` | float | group mean of `temperature_monthly_c[m]` |
| `precipitation_mm` | float | group mean of `max(0, precipitation_monthly_mm[m])` |
| `start_humidity_storage_mm` | float | carried from the previous step's end storage; `0.0` at month 1 |
| `evaporation_mm` | float | group mean of `vapor_evaporation_mm_y × weight[m]` |
| `moisture_convergence_mm` | float | group mean of `moisture_convergence_mm_y / 12` |
| `vapor_deficit_mm` | float | `max(0, precipitation − (start + evaporation + convergence))` |
| `humidity_export_mm` | float | `surplus × export_fraction` |
| `end_humidity_storage_mm` | float | `surplus − humidity_export_mm` |
| `humidity_budget_residual_mm` | float | `start + E + C + deficit − P − export − end` |
| `mean_wind_east` | float | group mean of `wind_monthly_east[m]` |
| `mean_wind_north` | float | group mean of `wind_monthly_north[m]` |
| `mean_wind_speed_index` | float | group mean of the monthly wind magnitude |
| `mean_vertical_motion_index` | float | group mean of `vertical_velocity_index` (annual field, repeated) |
| `mean_divergence_index` | float | group mean of `wind_divergence_index` (annual field, repeated) |
| `drying_risk` | float | `clamp(vapor_deficit / max(1, P + E))` |

The budget recurrence (`:279-294`):

```
raw_available   = start_storage + evaporation + convergence
vapor_deficit   = max(0, precipitation - raw_available)
surplus         = max(0, raw_available - precipitation)
export_fraction = clamp(0.42 + max(0, divergence) * 0.22 + wind_speed * 0.08, 0.25, 0.82)
humidity_export = surplus * export_fraction
end_storage     = surplus - humidity_export
```

`humidity_budget_residual_mm` is again **zero by construction** — the `vapor_deficit` term is defined exactly as the shortfall, so the identity closes algebraically. `summary.climate_seasonal_mean_abs_residual_mm` therefore reports floating-point closure only. The validator `seasonal_climate.seasonal_history_grouping_and_aggregates` checks 12-step coverage, month sequencing, storage continuity between consecutive steps (`|start_m − end_{m−1}| ≤ 2.0e-3`), non-negativity of the five flux fields, `[0,1]` bounds on `drying_risk` and `monsoon_index`, exact aggregate sums (`≤ 2.0e-3`), one record per atmospheric group, and four summary mirrors — `climate_seasonal_history_count`, `climate_seasonal_step_count`, `climate_seasonal_total_precipitation_mm`, `climate_seasonal_total_evaporation_mm` (`src/magic_geo/geo_validation_subsystems.py:456-533`).

Summary keys added by this enricher (`climate_dynamics.py:378-397`): `climate_seasonal_history_count`, `climate_seasonal_step_count`, `seasonal_humidity_regime_counts`, `climate_class_count`, `climate_class_counts`, `climate_main_class_counts`, `seasonal_aridity_cell_fraction` (cells with `seasonal_aridity_index ≥ 0.45`), `mean_cell_monsoon_index`, `mean_cell_seasonal_aridity_index`, `climate_seasonal_total_precipitation_mm`, `climate_seasonal_total_evaporation_mm`, `climate_seasonal_total_moisture_convergence_mm`, `climate_seasonal_total_humidity_export_mm`, `climate_seasonal_total_vapor_deficit_mm`, `climate_seasonal_mean_abs_residual_mm`, `max_climate_humidity_storage_mm`, `max_climate_monsoon_index`.

## Climate classification outputs

`classify_koppen_geiger` (`src/magic_geo/climate_dynamics.py:69-146`) implements a Köppen–Geiger cascade over the generated twelve-month climatology.

Aridity threshold selection (`:98-104`), using hemisphere-dependent summer index sets `{3,4,5,6,7,8}` (northern) / `{0,1,2,9,10,11}` (southern):

| Condition | Threshold |
|---|---|
| summer precipitation ≥ 70 % of annual | `20·T_annual + 280` |
| winter precipitation ≥ 70 % of annual | `20·T_annual` |
| otherwise | `20·T_annual + 140` |

then `max(0, threshold)`. If `P_annual < threshold`: `B` + (`W` if `P < 0.5·threshold` else `S`) + (`h` if `T_annual ≥ 18` else `k`).

Otherwise the cascade continues:

| Test | Result |
|---|---|
| `min(T_m) ≥ 18` | `Af` if `min(P_m) ≥ 60`; `Am` if `min(P_m) ≥ 100 − P_annual/25`; else `Aw` |
| `max(T_m) < 10` | `ET` if `max(T_m) > 0`, else `EF` |
| — | main class `C` if `min(T_m) > 0`, else `D` |
| winter > summer precip **and** `min(summer) < 40` **and** `min(summer) < max(winter)/3` | precipitation code `s` |
| summer ≥ winter precip **and** `min(winter) < max(summer)/10` | precipitation code `w` |
| otherwise | precipitation code `f` |
| `max(T_m) ≥ 22` | temperature code `a` |
| `≥ 4` months above `10 °C` | temperature code `b` |
| main class `D` and `min(T_m) ≤ −38` | temperature code `d` |
| otherwise | temperature code `c` |

`CLIMATE_CLASS_NAMES` (`:9-40`) maps all 30 codes to descriptive names (`Af → tropical_rainforest`, …, `EF → polar_frost`).

The `climate_classification` world object (`:361-377`):

| Key | Value |
|---|---|
| `classification_type` | `"koppen_geiger_beck_2018_v0"` |
| `monthly_temperature_field` | `"temperature_monthly_c"` |
| `monthly_precipitation_field` | `"precipitation_monthly_mm"` |
| `temperate_cold_threshold_c` | `0.0` |
| `arid_class_precedence` | `true` |
| `includes_water_cells` | `true` |
| `confidence_resolved` | **`false`** |
| `classification_limitation` | `"single_generated_monthly_climatology_without_observational_ensemble"` |
| `available_class_count` | `30` (length of `CLIMATE_CLASS_NAMES`) |
| `generated_class_count` | distinct classes actually produced |
| `classified_cell_count` | `len(cells)` |
| `legend` | 30 `{code, name}` entries, sorted by code |

`includes_water_cells: true` is significant — ocean and lake cells receive Köppen classes exactly like land cells, so `climate_class_counts` is not a land-only distribution. `confidence_resolved: false` is the explicit statement that no per-cell classification confidence is claimed.

The validator requires every generated `climate_class` to appear in the legend, requires the three counts to be exact, and requires `summary.climate_class_counts` / `summary.climate_class_count` to mirror the cell-derived counter (`geo_validation_subsystems.py:535-564`).

## Energy-balance records and insolation

`enrich_world_with_climate_energy_balance(world, planet)` receives `config.planet` in both generation paths. When called directly without `planet`, it reads `world["planet_parameters"]`; missing individual parameters retain Earth defaults. This diagnostic uses final climate, ice and surface categories and does not mutate native temperature.

Physical constants (`:8-10`):

| Constant | Value |
|---|---|
| `SOLAR_CONSTANT_W_M2` | `1361.0` |
| `STEFAN_BOLTZMANN_W_M2_K4` | `5.670374419e-8` |
| `SURFACE_LONGWAVE_EMISSIVITY` | `0.96` |

### The monthly insolation series

`insolation.py` now computes monthly means of daily-mean top-of-atmosphere flux. Kepler's equation `E − e sin(E) = M` locates equal-time month boundaries. Midpoint integration in true anomaly uses the exact Jacobian `(a/r)² dM = dν/sqrt(1−e²)` and maximum angular step `2π/768`, avoiding a missed periapsis peak even for accepted eccentricities close to one. Solar declination is `asin(sin(tilt) sin(solar_longitude))`.

For latitude φ, declination δ and sunset hour angle H₀, the complete-rotation mean is:

```text
Q = S₀ L (a/r)² [H₀ sin(φ) sin(δ) + cos(φ) cos(δ) sin(H₀)] / π
```

The polar day/night branches handle the poles without dividing by `tan(φ)`. There is no extra `/4` on this local flux; `S₀ L / (4 sqrt(1 − e²))` is the global annual mean, independently checked by area integration. Polar night is dark and high obliquity can give the poles a larger annual solar input than the equator.

`climate_energy_model` records the algorithm and angular resolution, equal-time calendar, fixed −75° solar longitude at periapsis, implicit 1 AU semimajor axis, and explicit lack of coupling to native temperature. The graybody equilibrium and outgoing radiation both use emissivity 0.96, eliminating a spurious flux residual at zero-greenhouse equilibrium. Albedo and greenhouse diagnostics remain empirical and do not close the coupled climate energy budget. See the [scientific review](../../simulation_coherence_research.md) for sources, analytical benchmarks, and limitations.

### Surface albedo

`_surface_albedo` checks thick ice first, then marine or standing lake water, then land cover. It adds empirical scattering/cloud terms and applicable brightening terms. Open lake water receives no land-only aridity or snow brightening; a dry salt flat has `is_lake = false`.

| Condition (first match) | Base | Regime |
|---|---|---|
| `is_lake` (or marine water with an inland-water category), after the thick-ice check | `0.10` | `lake_water` |
| `is_water` and `water_body_type == "continental_shelf"` | `0.08` | `shallow_ocean` |
| `is_water` otherwise | `0.065` | `open_ocean` |
| `ice_thickness_m > 20` or `biome == "ice_cap"` | `0.58 + clamp(ice/2500)·0.12` | `ice_albedo` |
| `biome ∈ {tundra, alpine}` | `0.34` if `T < −2` else `0.28` | `cold_sparse_cover` |
| `biome ∈ {hot_desert, cold_desert}` | `0.36` / `0.32` | `arid_high_albedo` |
| `biome ∈ {savanna, temperate_grassland, mediterranean_scrub}` | `0.21` | `seasonal_grassland` |
| `"forest" in biome` | `0.12` if `tropical_rainforest` else `0.14` | `forest_canopy` |
| otherwise | `0.22` | `mixed_land` |

| Additive term | Formula |
|---|---|
| `air_scattering` | `0.055` (constant) |
| `cloud_albedo` | `clamp(P/2800)·0.055 + max(0, vertical_velocity_index)·0.018` |
| `dry_brightening` | `seasonal_aridity_index · 0.035` (land only) |
| `snow_brightening` | `0.08` if land and `T < −3` and `P ≥ 250`, else `0` |
| `elevation_brightening` | `clamp((elev − 2600)/2600)·0.035` if `elev > 2600`, else `0` |

Total is clamped to `[0.04, 0.86]`.

### The greenhouse term

`_greenhouse_effect_c` (`:76-87`):

```
humidity   = clamp(0.35·hti + 0.25·(ocean_current_moisture_factor − 0.72)/0.56
                 + 0.25·clamp(P/2600) + 0.15·clamp(vapor_evaporation/1500))
greenhouse = max(0, (13.5 + 8.0·humidity + (1.5 if is_water else 0)
                          - 2.5·seasonal_aridity - 3.0·clamp(ice/1800))
                    × greenhouse_factor × sqrt(pressure_bar))
```

### Per-record and per-cell energy fields

Each cell receives 15 mirrored fields (`:181-195`) and one record is appended to `world["climate_energy_balance_records"]` (`:212-242`) carrying the same values plus provenance.

| Field | Formula | Present on |
|---|---|---|
| `top_of_atmosphere_insolation_w_m2` | `mean(monthly)` | cell + record |
| `surface_albedo_index` | `_surface_albedo` | cell + record |
| `absorbed_shortwave_w_m2` | `top × (1 − albedo)` | cell + record |
| `outgoing_longwave_w_m2` | `0.96 σ · max(1.0, T_observed + 273.15)⁴` | cell + record |
| `greenhouse_trapping_w_m2` | `max(0, 0.96 σ (T_eq + 273.15)⁴ − absorbed)` | cell + record |
| `net_radiative_balance_w_m2` | `absorbed + trapping − outgoing` | cell + record |
| `no_greenhouse_equilibrium_temperature_c` | `(absorbed/(0.96 σ))^0.25 − 273.15`; when `absorbed ≤ 0` the producer sets the Kelvin term to `0.0`, so the field becomes `−273.15` (not `0.0`) | cell + record |
| `radiative_equilibrium_temperature_c` | `no_greenhouse_c + greenhouse_c + 0.35·ocean_current_temperature_c` | cell + record |
| `energy_balance_residual_c` | `T_observed − T_equilibrium` | cell + record |
| `climate_energy_stress_index` | `clamp(\|residual\|/28 + \|net\|/220)` | cell + record |
| `surface_albedo_regime` | one of 9 regime names | cell + record |
| `seasonal_insolation_range_w_m2` | `max(monthly) − min(monthly)` | cell + record |
| `orbital_insolation_variability_index` | `clamp(range / max(1, top))` | cell + record |
| `peak_seasonal_insolation_w_m2` | `max(monthly)` | cell + record |
| `low_seasonal_insolation_w_m2` | `min(monthly)` | cell + record |
| `id`, `cell_id`, `latitude_deg`, `biome`, `water_body_type` | provenance | record only |
| `stellar_luminosity_factor`, `planetary_greenhouse_factor`, `atmosphere_pressure_bar`, `orbital_eccentricity`, `mean_orbital_distance_factor` | planet provenance | record only |
| `temperature_c` | the simulated temperature this record was scored against | record only |
| `monthly_top_of_atmosphere_insolation_w_m2` | the full 12-value series | record only |

All values are `round(..., 6)`.

### What closure these records actually assert

**They do not assert energy closure.** `net_radiative_balance_w_m2` is generally non-zero, and it is *supposed* to be: `outgoing_longwave_w_m2` uses the **simulated** `temperature_c` while `greenhouse_trapping_w_m2` is defined from the **diagnosed equilibrium** temperature. The three terms are related by the definitional identity `net = absorbed + trapping − outgoing`, which is a rearrangement, not a conservation law.

What is asserted is **independent numerical and algebraic replay**. `climate.climate_energy_balance_replay` (`_validate_climate_energy`, `src/magic_geo/geo_validation_physics.py`) re-derives, for every cell, the entire chain — `_seasonal_insolation_series`, `_surface_albedo`, `_greenhouse_effect_c`, absorbed, no-greenhouse equilibrium, equilibrium, outgoing, trapping, net, residual and stress — from `planet_parameters` and the serialized cell state, and requires agreement to `absolute=1.1e-6, relative=2e-12` on:

- each of the 12 monthly insolation values;
- all 21 numeric record fields — every entry of the validator's `expected` map except the monthly list and the `surface_albedo_regime` string (`geo_validation_physics.py`);
- 14 **cell mirrors** (the cell copy of each record field);
- `surface_albedo_regime` on both the record and the cell;
- exactly one record per cell, with sequential `id` and unique `cell_id`;
- `biome` and `water_body_type` staleness against the live cell;
- non-negativity of the 7 flux fields and `[0, 1]` bounds on `surface_albedo_index`, `orbital_insolation_variability_index` and `climate_energy_stress_index`;
- the original summary aggregates and `surface_albedo_regime_counts`, plus complete-area flux means and area-coverage metadata.

Greenhouse trapping is evaluated without subtracting nearly equal large fluxes. With zero-greenhouse Kelvin temperature `N`, known thermal increment `dT`, and `d = max(dT, 1 − N)` for the existing 1 K floor, the producer computes `max(0, εσ d (2N+d) [N²+(N+d)²])`. The independent validator expands `(N+d)⁴−N⁴` binomially. This is algebraically the same graybody difference and gives exactly zero trapping when the thermal increment is zero and the floor is inactive.

There is one magnitude-conditioned replay allowance: net flux may subtract very large parent terms, so its absolute tolerance is `max(1.1e-6, 16 × ulp(max(absorbed, trapping, outgoing)))`, using independently replayed finite values. Stress receives the corresponding allowance divided by 220. Arithmetic and area-weighted summaries use their respective mean allowance. Other tolerances remain unchanged. Near-parabolic, high-luminosity tests require exact/near-equilibrium replay and reject alterations larger than this numerical allowance; this does not change any physical calibration threshold.

At zero absorbed sunlight the no-greenhouse reference is −273.15 °C. Polar night can make individual months dark; zero obliquity at the exact pole also has zero annual geometrical insolation (up to floating-point trigonometric error). This is a local radiative reference without heat transport.

A second, lighter check, `climate.climate_energy_record_coverage` (`src/magic_geo/geo_validation.py:2100-2121`), requires every cell to have exactly one record with six finite required fields whose `temperature_c` matches the cell within `1.0e-3`.

Summary keys written (`climate_energy.py`): `climate_energy_balance_record_count`, `mean_top_of_atmosphere_insolation_w_m2`, `mean_surface_albedo_index`, `mean_absorbed_shortwave_w_m2`, `mean_outgoing_longwave_w_m2`, `mean_greenhouse_trapping_w_m2`, `mean_net_radiative_balance_w_m2`, `mean_abs_energy_balance_residual_c`, `mean_climate_energy_stress_index`, `mean_seasonal_insolation_range_w_m2`, `mean_orbital_insolation_variability_index`, `mean_peak_seasonal_insolation_w_m2`, `mean_low_seasonal_insolation_w_m2`, `mean_orbital_distance_factor`, `orbital_eccentricity`, `high_climate_energy_stress_cell_count` (`stress ≥ 0.65`), `surface_albedo_regime_counts`.

The high-stress count uses the published six-decimal stress values. For example, raw stress `0.6499996` exports as `0.650000` and counts as high stress. Independent replay first validates each published stress within its numerical tolerance, then requires an exact integer count from those values.

Those `mean_*` fields retain their arithmetic cell-count weighting. For a spatial flux mean, use the separately named `area_weighted_mean_top_of_atmosphere_insolation_w_m2`, `area_weighted_mean_absorbed_shortwave_w_m2`, `area_weighted_mean_outgoing_longwave_w_m2`, `area_weighted_mean_greenhouse_trapping_w_m2`, and `area_weighted_mean_net_radiative_balance_w_m2`. Each is `sum(flux × area / represented_area)` over all cells. The producer normalizes weights before multiplication to avoid unnecessary overflow; these means use the exported six-decimal flux records.

`climate_energy_valid_area_cell_count` counts finite positive numeric areas, excluding booleans. `climate_energy_represented_area_km2` sums those valid areas and is `null` if their sum overflows. `climate_energy_area_weighted_summary_available` is true only when every cell has a valid area and the sum is finite. Otherwise all five spatial means are `null`; partial coverage never substitutes an unweighted or partial-area mean. The model declaration records both weighting conventions, while `global_energy_conservation_resolved` remains false.

## Realism checks: climate and planet regimes

Both families produce `{id, domain, name, question, metric, value, target_min, target_max, score, passed, evidence}` records. They are **warning-severity** diagnostics in `validate-geo` (domain `realism_evidence`), promotable to fatal with `--fail-on-warnings`.

### `climate_realism_checks` — six checks

`enrich_world_with_climate_realism` (`src/magic_geo/climate_realism.py:77-280`). All values are clamped to `[0,1]`; `score` uses `_score_range` (`:14-19`): `1.0` inside the target band, else `clamp(1 − distance/width)`.

| Name | Question | Metric | Value formula | Target |
|---|---|---|---|---|
| `subtropical_dry_belt` | Are there relatively dry belts near 30 degrees latitude? | `subtropical_precipitation_deficit_index` | `clamp(1 − P̄(20°–35° land) / max(1, P̄(≤12° land ∪ 40°–60° land)))` | `[0.15, 1.0]` |
| `equatorial_ocean_humidity` | Are ocean-influenced equatorial cells humid when oceans exist? | `equatorial_ocean_humidity_index` | mean of `clamp(0.55·clamp(P/900) + 0.25·clamp(hti) + 0.20·clamp(advected))` over `\|lat\| ≤ 12°` cells that are water, have `fetch > 500 km`, or border water | `[0.55, 1.0]` |
| `orographic_rain_shadow` | Do rain-shadow cells tend to be dry relative to generated land climate? | `fraction_rain_shadow_cells_drier_than_land_mean` | fraction of land cells with `rain_shadow_factor ≤ 0.90` that also have `P ≤ P̄_land` **or** `seasonal_aridity_index ≥ 0.35` | `[0.45, 1.0]` |
| `continental_interior_extremes` | Are continental interiors more seasonally extreme than maritime margins? | `continentality_temperature_range_index` | `clamp(0.5 + (ΔT̄_interior − ΔT̄_coastal)/20)` | `[0.40, 1.0]` |
| `cold_current_coastal_drying` | Do cold currents reduce coastal moisture availability? | `cold_current_moisture_deficit_index` | `clamp((moisturē_warm − moisturē_cold)/0.12)` over coastal land with `ocean_current_temperature_c ≤ −0.25` / `≥ +0.25` | `[0.20, 1.0]` |
| `warm_current_climate_moderation` | Do warm currents soften coastal climates and raise moisture availability? | `warm_current_moderation_index` | `clamp(0.5·clamp(Δmoisture/0.12) + 0.5·clamp((ΔT̄_cold − ΔT̄_warm)/6))` | `[0.20, 1.0]` |

Every one of these six **returns `1.0` when its candidate set is empty** (`:94-98`, `:114-118`, `:126-136`, `:142-146`, `:161-165`, `:169-173`). That is exactly the failure mode the deep validator was written to catch: `REALISM_EVIDENCE_REQUIREMENTS` (`src/magic_geo/geo_validation.py:134+`) declares which evidence counters each check must carry, and `REALISM_EVIDENCE_MINIMUM_COUNTS` requires each of them to be `≥ 3` for climate checks (`:210-223`). A check whose evidence counters fall below the minimum is reported as `not_applicable`, not as a pass. The in-source comment states the intent: "These checks currently report a perfect score when their candidate set is empty. Deep validation treats that state as not-applicable instead of positive evidence" (`geo_validation.py:132-133`).

Required evidence counters per climate check:

| Check | Required evidence keys | Minimum each |
|---|---|---|
| `subtropical_dry_belt` | `subtropical_land_cell_count`, `reference_land_cell_count` | 3 |
| `equatorial_ocean_humidity` | `equatorial_ocean_influenced_cell_count` | 3 |
| `orographic_rain_shadow` | `rain_shadow_candidate_cell_count` | 3 |
| `continental_interior_extremes` | `interior_land_cell_count`, `coastal_land_cell_count` | 3 |
| `cold_current_coastal_drying` | `cold_current_coastal_cell_count`, `warm_current_coastal_cell_count` | 3 |
| `warm_current_climate_moderation` | `cold_current_coastal_cell_count`, `warm_current_coastal_cell_count` | 3 |

Summary keys: `subtropical_dry_belt_index`, `equatorial_ocean_humidity_index`, `orographic_rain_shadow_index`, `continentality_temperature_range_index`, `cold_current_coastal_drying_index`, `warm_current_moderation_index`, `climate_realism_check_count`, `climate_realism_pass_count`, `climate_realism_pass_fraction`, `mean_climate_realism_score` (`climate_realism.py:270-279`).

### `planet_realism_checks` — four checks

`enrich_world_with_planet_realism` (`src/magic_geo/planet_realism.py:79-219`). It first re-derives `planet_parameter_snapshot(planet)` and raises `ValueError("world planet_parameters must match the configured planet snapshot")` on mismatch (`:80-85`) — a hard gate, not a scored check.

Scoring uses two helpers: `_range_score(value, lower, upper, outer_lower, outer_upper)` gives `1.0` inside `[lower, upper]` and a linear ramp to `0` at the outer bounds (`:71-76`); `_score_range` is used for the check-record score (`:33-39`).

| Name | Question | Metric | Composite value | Target |
|---|---|---|---|---|
| `liquid_water_temperature_window` | Does the global temperature regime allow liquid water? | `temperature_and_surface_water_liquid_water_index` | `0.46·range_score(T̄, −5, 30, −55, 70) + 0.38·frac(−5 ≤ T ≤ 40) + 0.16·frac(is_water or is_lake)` | `[0.55, 1.0]` |
| `atmosphere_gravity_stability` | Does gravity allow a stable atmosphere for the configured pressure? | `gravity_pressure_stability_index` | `0.55·range_score(g, 0.45, 2.2, 0.08, 4.5) + 0.45·range_score(log₁₀ P, log₁₀ 0.1, log₁₀ 5.0, −4.0, 1.3)` | `[0.60, 1.0]` |
| `rotation_circulation_plausibility` | Does rotation allow plausible atmospheric circulation cells? | `day_length_and_atmospheric_band_plausibility_index` | `0.55·range_score(day_length, 8, 48, 1, 120) + 0.45·clamp(populated_band_count / 4)` | `[0.65, 1.0]` |
| `surface_water_inventory` | Does the water inventory allow oceans, seas, lakes, or a coherent arid world? | `surface_water_inventory_match_index` | `0.62·volume_match + 0.20·fraction_match + 0.18·clamp(non-land water-body-type diversity / 3)` | `[0.70, 1.0]` |

Details worth knowing:

- `rotation_circulation_plausibility` reads `summary.atmospheric_cell_counts` — the native band histogram — and scores `populated_band_count / 4`. A world where only two of the four bands are populated caps this term at `0.5` regardless of rotation rate (`:113-118`).
- `ocean_match_score = clamp(1 − |ocean_fraction − target|/0.25)`, with a special dry-world branch: when `target_ocean_fraction < 0.05` it is raised to `max(·, clamp(1 − ocean_fraction/0.1))` so a deliberately arid world is not punished (`:128-130`).
- `ocean_volume_match_score` is `clamp(1 − |actual − target|/target)` when `target > 0`, else `clamp(1 − actual/1e6)` (`:131-136`).

Summary keys: `global_liquid_water_temperature_index`, `atmosphere_gravity_stability_index`, `rotation_circulation_plausibility_index`, `surface_water_inventory_index`, `planet_realism_check_count`, `planet_realism_pass_count`, `planet_realism_pass_fraction`, `mean_planet_realism_score` (`:211-218`).

## Validation checks and the layer contract

### Checks in domain `climate`

| Check | Source | Assertion |
|---|---|---|
| `monthly_annual_climate_closure` | `geo_validation.py:1469-1483` | four monthly arrays each have exactly 12 finite values; `\|temperature_c − mean(monthly)\| ≤ 1.0e-3`; `\|precipitation_mm_y − Σ monthly\| ≤ 1.0e-2` |
| `configured_global_temperature_response` | `geo_validation.py:1496-1504` | area-weighted mean of `temperature_c` matches `base + 38(L^0.25−1) + 11(G−1) + 4.5 ln(P)` within `0.35 °C` |
| `climate_energy_record_coverage` | `geo_validation.py:2110-2122` | one finite energy record per cell, tied to the cell's `temperature_c` within `1.0e-3` |
| `climate_energy_balance_replay` | `geo_validation_physics.py:1605-1629` | full producer-equation replay of every insolation, albedo, greenhouse, longwave, net, stress, cell mirror and aggregate at `1.1e-6` absolute plus `2e-12` relative |

### Checks in domain `seasonal_climate`

| Check | Source | Assertion |
|---|---|---|
| `seasonal_history_grouping_and_aggregates` | `geo_validation_subsystems.py:525-533` | one 12-month history per atmospheric-cell group, sequential ids, storage continuity, non-negative fluxes, exact annual sums, four summary mirrors |
| `classification_and_continentality_sources` | `geo_validation_subsystems.py:595-603` | legend-backed classes, exact classification counts, non-overlapping continentality regions with exact cell/area mirrors and an exact assignment inverse |

### The `climate_atmosphere` layer contract

Phase 6 of the 14-layer audit (`src/magic_geo/geo_layer_contracts.py:133-149`):

| Field | Value |
|---|---|
| `id` | `climate_atmosphere` |
| `phase` | `6` |
| `name` | `"Climate, energy, circulation, moisture, and classification"` |
| `dependencies` | `("sea_level_ocean", "relief_bathymetry")` |
| `required_outputs` | `climate_model` (dict), `climate_energy_balance_records` (nonempty_list), `climate_seasonal_histories` (nonempty_list), `climate_classification` (dict), `climate_continentality_regions` (list), `climate_realism_checks` (list) |
| `validator_domains` | `("climate", "seasonal_climate")` |
| `temporal_class` | `"equilibrium_climatology_not_transient_weather"` |
| `evidence_class` | `"formula_replay_and_partial_external_climatology"` |
| `empirical_realism_proven` | **`false`** — a literal, hardcoded for every layer in the report builder (`geo_layer_contracts.py:433`), never computed |

`contract_passed` means: the six outputs exist with the right kind, both validator domains supplied at least one check, both dependencies passed, at least one passing check exists, and there are zero error-severity failures among the layer's checks. It is explicitly **not** an empirical-realism claim.

### `earthlike` profile envelopes and the calibration checks

The `earthlike` validation profile range-gates three climate-relevant metrics (`geo_validation.py:770-774`, inside the nine-metric `ranges` map at `:768-778`):

| Metric | Envelope |
|---|---|
| `global_mean_temperature_c` | `[8.0, 22.0]` |
| `mean_land_precipitation_mm_y` | `[350.0, 1800.0]` |
| `ice_cell_fraction` | `[0.005, 0.45]` |

The native `generate_calibration_checks` (`cpp/src/engine/history.cpp:990-1088`) emits three climate-layer entries against `WorldClim_reference_range` (`CALIBRATION_DATASET_NAMES[1]`, `CALIBRATION_LAYER_NAMES[1] == "climate"`, `schema_names.hpp:102-115`):

| Metric index | Metric name | Value | Target range |
|---|---|---|---|
| `3` | `global_mean_temperature_c` | `Σ temperature_c / cell_count` (unweighted) | `[−5.0, 28.0]` |
| `4` | `mean_land_precipitation_mm_y` | `Σ_land precipitation_mm_y / land_count` | `[250.0, 2300.0]` |
| `5` | `mean_monthly_temperature_range_c` | `Σ (max − min of temperature_monthly_c) / cell_count` | `[2.0, 38.0]` |

Note that metric 3 is a **plain cell mean**, while `extract_geo_metrics["global_mean_temperature_c"]` (`geo_validation.py:458`) is an **area-weighted** mean. The two agree only for meshes with uniform cell areas.

### Cross-scenario climate relations in the validation suite

`configs/geo_validation_matrix.yaml` defines 21 scenarios and 26 paired relations in total; seven of the scenarios and nine of the relations are climate-driven. Only the climate-relevant overrides and expectations are listed — every scenario below also sets `mesh.cell_count: 512`, `tectonics.plate_count: 10` and `erosion.iterations: 3`:

| Scenario | Overrides | Expectations |
|---|---|---|
| `arid_landworld` | `ocean_fraction_target: 0.0`, `ocean_water_inventory_km3: 0.0`, `precipitation_scale: 0.12` | `ocean_fraction ∈ [0,0]`, `mean_land_precipitation_mm_y ≤ 180`, `mean_land_runoff_mm_y ≤ 100`, `desert_land_fraction ≥ 0.40` |
| `waterworld` | `ocean_fraction_target: 0.95`, `ocean_water_inventory_km3: 5e9` | `ocean_fraction ≥ 0.98` |
| `snowball` | `stellar_luminosity: 0.55`, `greenhouse_factor: 0.50`, `base_temperature_c: −10.0` | `global_mean_temperature_c ≤ −15`, `ice_cell_fraction ≥ 0.15` |
| `hothouse` | `stellar_luminosity: 1.60`, `greenhouse_factor: 1.70`, `base_temperature_c: 35.0` | `global_mean_temperature_c ≥ 40`, `ice_cell_fraction ≤ 0.01` |
| `low_obliquity` | `axial_tilt_deg: 0.0` | `mean_land_seasonal_temperature_range_c ∈ [0.0, 0.1]` |
| `high_obliquity` | `axial_tilt_deg: 75.0` | `mean_land_seasonal_temperature_range_c ≥ 35.0` |
| `thin_atmosphere` | `gravity_g: 0.40`, `atmosphere_pressure_bar: 0.05` | `global_mean_temperature_c ≤ 5.0`, `mean_land_precipitation_mm_y ≤ 650` |

| Relation | Comparison | Minimum difference |
|---|---|---|
| `dry_forcing_reduces_precipitation` | `arid_landworld < earthlike_pair` on `mean_land_precipitation_mm_y` | `300.0` |
| `dry_forcing_reduces_runoff` | `arid_landworld < earthlike_pair` on `mean_land_runoff_mm_y` | `150.0` |
| `cold_forcing_reduces_temperature` | `snowball < earthlike_pair` on `global_mean_temperature_c` | `20.0` |
| `cold_forcing_reduces_precipitation` | `snowball < earthlike_pair` on `mean_land_precipitation_mm_y` | `300.0` |
| `cold_forcing_reduces_runoff` | `snowball < earthlike_pair` on `mean_land_runoff_mm_y` | `150.0` |
| `hot_forcing_raises_temperature` | `hothouse > earthlike_pair` on `global_mean_temperature_c` | `25.0` |
| `snowball_has_more_ice` | `snowball > earthlike_pair` on `ice_cell_fraction` | `0.05` |
| `hothouse_has_less_ice` | `hothouse < earthlike_pair` on `ice_cell_fraction` | `0.02` |
| `high_tilt_increases_seasonality` | `high_obliquity > low_obliquity` on `mean_land_seasonal_temperature_range_c` | `30.0` |

The `low_obliquity` expectation `mean_land_seasonal_temperature_range_c ≤ 0.1` is a direct consequence of `seasonal_amp ∝ (axial_tilt_deg / 23.5)` going to exactly zero at `axial_tilt_deg = 0`; the residual `0.1 °C` slack is numerical, since nothing else in the monthly temperature varies with month.

## Climate and planet configuration reference

### `climate` section

| Key | Type | Default | Range | Physical meaning | Tuning guidance |
|---|---|---|---|---|---|
| `months` | `Literal[12]` | `12` | only `12` | Number of monthly climate samples per year | Not tunable. `config.py:324`; native guard `core.cpp:376-377`; fixed 12-element `std::array` storage |
| `lapse_rate_c_per_km` | float | `6.5` | `[0.0, 15.0]` | Dry lapse applied to positive elevation only | Controls the *relief* temperature contrast, not the planetary mean (the area-mean lapse is subtracted globally). Raise for sharper alpine/tundra bands; `0.0` removes elevation from temperature entirely. `config.py:328` |
| `base_temperature_c` | float | `15.0` | `[−100.0, 100.0]` | **Global area-mean surface temperature after all local adjustments** | The single most direct climate control. It is *not* an equatorial or sea-level value; the equator sits at `base + 11.75 °C` and the pole at `base − 35.25 °C`. Also shifts `thermal_moisture_capacity_factor` via the `15.0 °C` reference. `config.py:334` |
| `precipitation_scale` | float | `1.0` | `[0.0, 10.0]` | Global precipitation multiplier, applied before the thermal-moisture factor | `0.0` gives *exact* zero precipitation everywhere — a clean dry boundary for tests. The `earthlike` and `smoke` profiles both set `0.8`. `config.py:340` |
| `subtropical_drying_strength` | float | `0.65` | `[0.0, 0.9]` | Strength of the descending-air dry belts near 30° (shifted by rotation rate) | At `0.65` a band-centre cell keeps 35 % of its base precipitation; a fully cold current pushes it to the `0.25` floor. Lower it for a more uniformly wet world; raise it toward `0.9` for pronounced desert belts. `config.py:346` |

### `planet` section (climate-relevant subset, all 12 listed)

| Key | Type | Default | Range | Physical meaning | Tuning guidance |
|---|---|---|---|---|---|
| `radius_km` | float | `6371.0` | `(100.0, 100000.0]` | Mean planetary radius | Scales all surface areas/distances; in climate it only converts angular neighbour separation to km in the humidity-transport walk, so a larger planet gets longer `upwind_ocean_fetch_km` per hop. `config.py:161` |
| `gravity_g` | float | `1.0` | `(0.05, 5.0)` | Surface gravity relative to Earth | Climate coupling is a single multiplier `clamp(1.08 − 0.10(g−1), 0.65, 1.35)`; low gravity is slightly *wetter* in this model. `config.py:167` |
| `day_length_hours` | float | `24.0` | `(1.0, 10000.0]` | Rotation period | Three effects: zonal wind strength, zonal current strength (`sqrt`), and `rotation_band_shift` which moves the subtropical/midlatitude centres by up to `+9°` (slow) or `−7°` (fast). Also scored by `rotation_circulation_plausibility` with an ideal window of `[8, 48] h`. `config.py:173` |
| `axial_tilt_deg` | float | `23.5` | `[0.0, 90.0]` | Axial obliquity | Linear control on seasonal amplitude and monsoon wind strength; `0.0` gives a *perfectly* seasonless native temperature field. The suite pairs `0.0` against `75.0` and requires a `≥ 30 °C` seasonal-range difference. `config.py:179` |
| `orbital_eccentricity` | float | `0.016` | `[0.0, 1.0)` | Orbital eccentricity | Enters the native model only as a symmetric amplitude multiplier `1 + 1.8·clamp(e, 0, 0.8)` — no perihelion asymmetry. In the energy records it drives a genuine `1/d²` monthly cycle. `config.py:185` |
| `stellar_luminosity` | float | `1.0` | `(0.01, 100.0]` | Incident stellar luminosity relative to the Sun | `38.0·(L^0.25 − 1)` °C uniform offset **and** scales `SOLAR_CONSTANT_W_M2` in the radiation budget. Combine with `greenhouse_factor` and `base_temperature_c` for regime shifts. `config.py:191` |
| `atmosphere_pressure_bar` | float | `1.0` | `[0.0, 1000.0]` | Mean surface pressure | `4.5·ln(max(0.01, P))` °C offset and `clamp(P^0.35, 0.35, 1.85)` precipitation factor; `sqrt(P)` scales the Python greenhouse. It does **not** enter the thermal-moisture anomaly. `P = 0.05` gives `−13.48 °C` and `0.350×` precipitation. `config.py:197` |
| `greenhouse_factor` | float | `1.0` | `[0.0, 100.0]` | Greenhouse trapping multiplier | `11.0·(G − 1)` °C uniform offset; also multiplies the entire Python greenhouse term. `G = 0` gives `−11 °C` and a zero greenhouse effect in the energy records. `config.py:203` |
| `ocean_fraction_target` | float | `0.70` | `[0.0, 0.95]` | Diagnostic ocean-cover target | Not read by `compute_climate`. Scored by `surface_water_inventory` with a dedicated arid-world branch below `0.05`. `config.py:209` |
| `ocean_water_inventory_km3` | float | `1338000000.0` | `[0.0, 1e10]` | Connected-ocean water volume | Sets the sea-level solve, which sets the land/sea mask climate reads. The dominant term (weight `0.62`) in `surface_water_inventory_match_index`. `config.py:215` |
| `internal_heat` | float | `1.0` | `[0.0, 100.0]` | Internal heat flow relative to Earth | **No climate coupling.** Tectonic/geothermal only. `config.py:221` |
| `geological_age_ga` | float | `4.5` | `[0.01, 100.0]` | Planet age | **No climate coupling.** Bounds crust age. `config.py:227` |

Additional constraints: every config model sets `extra="forbid"` and `allow_inf_nan=False`, so unknown keys and `nan`/`inf` are rejected at parse time.

## Worked examples

### 1. Predicting the global mean temperature from configuration alone

Because the temperature field is area-mean normalized, the global mean is fully determined by four numbers. Using the four suite scenarios:

| Scenario | `base_temperature_c` | `L` | `G` | `P` (bar) | Stellar term | Greenhouse term | Pressure term | Predicted area-mean |
|---|---|---|---|---|---|---|---|---|
| default / `earthlike` | `15.0` | `1.0` | `1.0` | `1.0` | `0.000` | `0.000` | `0.000` | **`15.000 °C`** |
| `hothouse` | `35.0` | `1.60` | `1.70` | `1.0` | `+4.738` | `+7.700` | `0.000` | **`47.438 °C`** |
| `snowball` | `−10.0` | `0.55` | `0.50` | `1.0` | `−5.275` | `−5.500` | `0.000` | **`−20.775 °C`** |
| `thin_atmosphere` | `15.0` | `1.0` | `1.0` | `0.05` | `0.000` | `0.000` | `−13.481` | **`+1.519 °C`** |

Each satisfies its declared expectation (`≥ 40`, `≤ −15`, `≤ 5.0` respectively), and `climate.configured_global_temperature_response` asserts the same identity to `0.35 °C`.

The corresponding thermal-moisture capacity factors (which do **not** see pressure):

| Scenario | Anomaly (°C) | `0.04 × anomaly` | Clamp bounds `[ln 0.35, ln 2.25] = [−1.0498, 0.8109]` | Factor |
|---|---|---|---|---|
| default | `0.000` | `0.0000` | inside | `1.000` |
| `hothouse` | `+32.438` | `1.2975` | clamped to `0.8109` | `2.250` (max) |
| `snowball` | `−35.775` | `−1.4310` | clamped to `−1.0498` | `0.350` (min) |
| `thin_atmosphere` | `0.000` | `0.0000` | inside | `1.000` |

So `thin_atmosphere`'s precipitation reduction comes entirely from `pressure_precip_factor = clamp(0.05^0.35, 0.35, 1.85) = 0.3505` (barely above the floor) combined with `gravity_precip_factor = clamp(1.08 − 0.10(0.40 − 1.0), 0.65, 1.35) = 1.14` — a net `0.3995×`, which is what keeps `mean_land_precipitation_mm_y ≤ 650`.

### 2. Reading one energy-balance record

Take an equatorial open-ocean cell on the default configuration with `precipitation_mm_y = 2000`, `vertical_velocity_index = 0.5`, `humidity_transport_index = 1.0`, `ocean_current_moisture_factor = 1.05`, `vapor_evaporation_mm_y = 1200`, `seasonal_aridity_index = 0.05`, `ocean_current_temperature_c = 1.0`, `temperature_c = 27.0`.

For `lat = 0°`, `L = 1`, `tilt = 23.5°`, and `e = 0.016`, the new astronomical series varies with both declination and orbital distance. The equator receives less daily-mean sunlight at solstice than at equinox; this effect was absent from the old affine approximation.

| Quantity | Current value |
|---|---:|
| Annual TOA insolation | 415.501676 W/m² |
| Maximum monthly TOA | 437.358494 W/m² |
| Minimum monthly TOA | 388.091739 W/m² |
| Monthly range | 49.266755 W/m² |
| Mean inverse-square distance factor | 1.000128 |
| Albedo proxy | 0.168286 |
| Absorbed shortwave | 345.578680 W/m² |
| No-greenhouse graybody reference | 9.120825 °C |
| Empirical radiative equilibrium | 30.822858 °C |
| Outgoing longwave at the supplied 27 °C | 441.810833 W/m² |
| Greenhouse trapping diagnostic | 119.174316 W/m² |
| Net radiative balance diagnostic | +22.942163 W/m² |
| Temperature residual | −3.822858 °C |
| Stress index | 0.240813 |

These values come from `enrich_world_with_climate_energy_balance` on the stated cell. The flux residual compares the supplied native temperature with the diagnosed equilibrium; replay verifies that comparison, rather than requiring zero for arbitrary supplied temperature. For zero greenhouse and current anomaly, supplying the graybody equilibrium now makes both residuals zero.

### 3. Obliquity and the seasonal insolation range

The astronomical series at `lat = 45°` with the other default parameters gives:

| `axial_tilt_deg` | Mean TOA (W/m²) | Monthly range (W/m²) |
|---|---:|---:|
| `0.0` | 306.372 | 19.391 |
| `23.5` | 306.948 | 349.884 |
| `75.0` | 364.691 | 867.702 |

At zero obliquity the remaining range comes from orbital distance. Higher tilt changes both the annual latitude distribution and seasonal illumination. Native temperature still uses its separate amplitude model; these numbers should not be read as dynamically coupled seasonal temperature predictions.

## Running climate-relevant checks

Generate an Earth-like reference world and validate it against the `earthlike` envelope:

```bash
magic-geo init-config --profile earthlike --output magic-geo.yaml
magic-geo generate --config magic-geo.yaml --output runs/world.json --geo-only
magic-geo validate-geo --world runs/world.json --profile earthlike
```

`--world` / `-w` is a required option, not a positional argument, and `--profile` accepts only `generic` (the default) or `earthlike`.

Promote realism-evidence warnings (which is where the six climate checks live) to hard failures:

```bash
magic-geo validate-geo --world runs/world.json --profile earthlike --fail-on-warnings
```

Run the full cross-scenario matrix, which includes `snowball`, `hothouse`, `low_obliquity`, `high_obliquity`, `thin_atmosphere`, `arid_landworld` and `waterworld` plus their paired relations. The scenario file is passed with `--matrix` / `-m` (it defaults to this same path) and the base config with `--config` / `-c`:

```bash
magic-geo validate-geo-suite \
  --config configs/earthlike_seed.yaml \
  --matrix configs/geo_validation_matrix.yaml \
  --output runs/geo_validation.json
```

To bake one value into a config file, `init-config` takes repeatable `--set section.field=YAML_VALUE` overrides (`magic-geo init-config --profile earthlike --set climate.subtropical_drying_strength=0.9 --output dry.yaml`). To sweep a control in-process instead, `apply_config_overrides` takes the same dotted paths as a mapping:

```bash
python - <<'PY'
from magic_geo.config import create_config, apply_config_overrides
from magic_geo.api import generate_geo_world

base = create_config("earthlike")
for strength in (0.0, 0.45, 0.65, 0.9):
    config = apply_config_overrides(
        base, {"climate.subtropical_drying_strength": strength, "mesh.cell_count": 512}
    )
    world = generate_geo_world(config)
    summary = world["summary"]
    print(strength, summary["subtropical_dry_belt_index"], summary["mean_climate_realism_score"])
PY
```

Inspect the declaration block and the derived thermal-moisture factor of a generated world:

```bash
python -c "
import json
world = json.load(open('runs/world.json'))
m = world['climate_model']
for key in ('model_type', 'base_temperature_interpretation',
            'thermal_moisture_capacity_temperature_anomaly_c',
            'thermal_moisture_capacity_factor',
            'mass_conserving_atmosphere', 'transient_climate_resolved',
            'model_limitation'):
    print(f'{key}: {m[key]}')
"
```

## Limitations and unresolved claims

- **The atmosphere is not mass-conserving and weather is not resolved.** `climate_model` serializes `mass_conserving_atmosphere: false` and `transient_climate_resolved: false`, with `model_limitation: "equilibrium_diagnostic_climate_without_mass_conserving_three_dimensional_atmosphere"` (`cpp/src/engine/process_serialization.cpp:443-446`). The `climate_atmosphere` layer contract records `temporal_class: "equilibrium_climatology_not_transient_weather"` (`src/magic_geo/geo_layer_contracts.py:147`). This is one of the twelve declared `GEO_MODEL_LIMITATIONS`: "the diagnostic atmosphere is not a three-dimensional mass-conserving circulation solver" (`src/magic_geo/geo_validation.py:30`).
- **There is no dynamics.** Winds, circulation cells, vertical velocity, divergence, surface pressure and ocean currents are all analytic functions of latitude, longitude and rotation rate. Nothing is advected, no momentum equation is solved, and no field depends on any other field's gradient except through the fixed local relief and upwind-neighbour terms.
- **The vapour budget residuals are algebraic identities, not conservation tests.** Both `vapor_budget_residual_mm_y` (`climate.cpp:514`) and `humidity_budget_residual_mm` (`climate_dynamics.py:286-294`) are constructed so that they are zero by definition; the reported means measure floating-point closure only. `thermal_moisture_capacity_limitation` states the corresponding scope limit: `"diagnostic_global_scaling_without_explicit_atmospheric_water_mass_or_energy_balance"`.
- **The energy-balance records assert replay, not energy closure.** `net_radiative_balance_w_m2` is routinely non-zero because `outgoing_longwave_w_m2` uses the simulated temperature while `greenhouse_trapping_w_m2` uses the diagnosed equilibrium temperature. The replay validator (`geo_validation_physics.py`) proves the arithmetic reproduces; it makes no claim that the surface is in radiative balance.
- **Astronomical sunlight is calculated, but native climate remains uncoupled.** The daily zenith integral and Kepler-weighted month integration resolve polar night and high-obliquity forcing. They assume rotation averaging, an implicit 1 AU orbit, and fixed periapsis phase; orbital motion during a day and transient heat transport are unresolved. The energy model declares these limitations.
- **The native seasonal temperature and solar calendar are separate.** The native temperature proxy peaks at month index 6 through `cos(2π(month − 6)/12)` (`climate.cpp:402`). The Python insolation diagnostic integrates equal-duration months using Kepler orbital time, with periapsis at month-zero center and a fixed solar longitude there. Its circular-orbit northern summer solstice is at index 5.5; eccentric orbits change the solstice timing in elapsed time. Native monthly temperatures do not consume this solar forcing, so agreement between those seasonal curves is not guaranteed.
- **Eccentricity produces no seasonal asymmetry in the native temperature field.** It enters only as the symmetric multiplier `1 + 1.8·clamp(e, 0, 0.8)` (`climate.cpp:267`). A genuine perihelion/aphelion asymmetry exists only in the Python insolation series.
- **`oceanity` and `continentality` are mesh-resolution dependent.** They derive from `exp(−ocean_distance_hops / 7.5)` where the distance is an unweighted neighbour-hop BFS (`cpp/src/engine/ocean.cpp:323-349`). One hop covers a different physical distance at 512 cells than at 8,192, so seasonal amplitude, the `+560·oceanity` precipitation term, recycling fraction and land evaporation all shift with mesh resolution. The Python `distance_to_marine_water_km` is the great-circle counterpart and is *not* used by the native model.
- **Two different "continentality" quantities coexist** — the native hop-decay used inside `compute_climate` and the Python `continentality_index` blend (`climate_continentality.py:200`). They are not required to agree and no check compares them.
- **Coefficients are procedural response magnitudes, not calibrated sensitivities.** `38.0 °C` per stellar-luminosity quarter power, `11.0 °C` per greenhouse unit, `4.5 °C` per natural log of bar, `47.0 °C` pole-to-equator gradient with exponent `3.0`, and the whole precipitation base `170 + 1450·equator + 680·mid − 610·subtropic + 560·oceanity + 320·relief` are chosen constants. The only external Earth comparison is the separate calibration verdict, and the suite states that "Earth empirical fit remains a separate calibration verdict from internal contract integrity" (`geo_validation.py:40`).
- **`CLIMATE_MARINE_ANNUAL_TEMPERATURE_OFFSET_C = 0.0` makes the marine temperature branch inert.** The land/sea thermal contrast in the current model comes only from `oceanity` acting on seasonal amplitude and from `ocean_current_temperature_c`, not from a direct marine offset — even though `marine_annual_temperature_offset_c` is still serialized as a model parameter.
- **The six climate realism checks return a perfect score on empty candidate sets.** Each falls back to `1.0` when its filter matches nothing (`climate_realism.py:94-98`, `:114-118`, `:126-136`, `:142-146`, `:161-165`, `:169-173`). The deep validator compensates by demoting them to `not_applicable` when their declared evidence counters fall below `3` (`geo_validation.py:132-133`, `:210-223`), but the raw `climate_realism_checks` array read on its own will over-report.
- **`climate_classification.confidence_resolved` is `false`** and the classification is labelled `"single_generated_monthly_climatology_without_observational_ensemble"` (`climate_dynamics.py:8`, `:368-369`). Water cells are classified alongside land (`includes_water_cells: true`), so class-count distributions are not land-only.
- **`empirical_realism_proven: false` on every layer contract**, including `climate_atmosphere`. It is a hardcoded literal (`src/magic_geo/geo_layer_contracts.py:433`), not a computed verdict. Passing the contract means outputs exist, dependencies passed and no error-severity check failed — nothing more.
- **Physical time is unresolved.** Climate is recomputed at each coupled stage, but the simulation clock "orders procedural stages but has no calibrated physical duration" (`geo_validation.py:29`), and every nominal-time field carries `physical_time_resolved: false` / `nominal_time_calibrated: false`. The feedback record's `mean_abs_temperature_change_c_from_previous_stage` is a stage-indexed difference, not a rate.
- **`internal_heat` and `geological_age_ga` have no climate coupling at all**, despite being part of the planetary parameter snapshot that the climate layer contract depends on.
- **The two `global_mean_temperature_c` definitions differ.** The native calibration check uses a plain cell mean (`cpp/src/engine/history.cpp:1070`); `extract_geo_metrics` uses an area-weighted mean (`geo_validation.py:458`). They coincide only on uniform-area meshes.

## See also

- [Oceans, Currents and Coasts](oceans-and-coasts.md) — the sea-level solve and marine labelling that run immediately before every climate recomputation, and the `ocean_circulation` enricher that turns the current field into a transport graph
- [Hydrology, Rivers and Lakes](hydrology-and-rivers.md) — the water budget and drainage stages that consume `temperature_c`, `precipitation_mm_y` and `vapor_evaporation_mm_y` in the same stabilization pass
- [Cryosphere: Ice Sheets, Glaciers and Permafrost](cryosphere.md) — the consumer of monthly temperature and the source of `ice_thickness_m` that feeds the albedo regime
- [Biomes, Ecosystems and Disturbance](biomes-and-ecology.md) — the Thornthwaite-style water balance and biome assignment built on this climatology
- [Soils and Weathering](soils.md) — pedogenesis driven by `precipitation_mm_y`, `temperature_c` and `seasonal_aridity_index`
- [Topography, Isostasy and Thermal Subsidence](topography-and-isostasy.md) — the elevation field the lapse rate and orographic factors read
- [Erosion, Maturation and Landscape Evolution](erosion-and-maturation.md) — the maturation loop that triggers each climate recomputation
- [Configuration Reference](../05-configuration-reference.md) — the full 44-leaf-field schema across nine sections, profiles and override syntax
- [CLI Reference](../06-cli-reference.md) — `generate`, `validate-geo`, `validate-geo-suite`, `calibrate`
- [Python API](../07-python-api.md) — `generate_world` / `generate_geo_world` and the enricher call order
- [Native Engine (C++ Core)](../08-native-engine.md) — translation units, stage ordering and declared invariants
- [World Document Schema](../10-world-schema.md) — the full key inventory for `climate_model`, `climate_energy_balance_records[]` and `climate_seasonal_histories[]`
- [Validation](../12-validation.md) — how the `climate` and `seasonal_climate` domains compose into the geo report
- [Geo Validation Suite](../13-geo-validation-suite.md) — the scenario matrix and paired-relation machinery
- [Calibration Against Real-Earth Data](../14-calibration.md) — the WorldClim-derived temperature and precipitation targets
- [Glossary](../21-glossary.md)
