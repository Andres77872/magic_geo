# Configuration Reference

[Wiki home](./README.md) > Configuration Reference

Every magic-geo generation run is driven by a single validated YAML document whose authoritative schema is `WorldConfig` in `src/magic_geo/config.py`. There are nine sections with 43 leaf properties plus the required root `config_version: 2`; there are no hidden knobs, no environment-variable fallbacks for physical parameters, and no per-enricher configuration. This page enumerates all 44 properties with their real types, defaults, and pydantic bounds, explains what each one physically means and which pipeline stage consumes it, and then documents the profile system, the `--set` override grammar, YAML strictness, the JSON Schema export, atomic validated writes, and the config-to-native marshaling boundary.

## On this page

- [Document structure and a complete example](#document-structure-and-a-complete-example)
- [How a config reaches the engine](#how-a-config-reaches-the-engine)
- [`run` — run identity](#run--run-identity)
- [`planet` — bulk planetary properties](#planet--bulk-planetary-properties)
- [`mesh` — spherical discretisation](#mesh--spherical-discretisation)
- [`tectonics` — plates and solid earth](#tectonics--plates-and-solid-earth)
- [`climate` — temperature and precipitation drivers](#climate--temperature-and-precipitation-drivers)
- [`hydrology` — routing and river classification](#hydrology--routing-and-river-classification)
- [`erosion` — landscape maturation](#erosion--landscape-maturation)
- [`compute` — execution backend](#compute--execution-backend)
- [`output` — payload shape and numeric formatting](#output--payload-shape-and-numeric-formatting)
- [Cross-field validators](#cross-field-validators)
- [The profile system](#the-profile-system)
- [The `--set` override syntax](#the---set-override-syntax)
- [YAML strictness and complexity limits](#yaml-strictness-and-complexity-limits)
- [JSON Schema export](#json-schema-export)
- [Atomic validated writes](#atomic-validated-writes)
- [Config-to-native mapping](#config-to-native-mapping)
- [Other configuration surfaces that are not generation config](#other-configuration-surfaces-that-are-not-generation-config)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Document structure and a complete example

The document root must be a YAML **mapping** (`src/magic_geo/config.py`). Its keys are `config_version` and the nine section names, in the declaration order of `WorldConfig` (`src/magic_geo/config.py`):

```text
run → planet → mesh → tectonics → climate → hydrology → erosion → compute → output
```

Every section field has a default, but YAML documents require the exact integer `config_version: 2`. The minimal valid document is `config_version: 2`. Empty, unversioned, old-version and future-version documents receive source-aware migration errors; they cannot silently acquire new physical semantics. `WorldConfig()` deliberately constructs a new seasonal configuration, while `SeasonalWorldConfig` requires its version even in direct construction.

The checked-in Earth-like reference is `configs/earthlike_seed.yaml`. It is a fully materialized copy of the `earthlike` profile — `create_config("earthlike") == load_config("configs/earthlike_seed.yaml")` holds exactly.

```yaml
# configs/earthlike_seed.yaml — all 43 section fields and the document version
config_version: 2
run:
  seed: 424242
  name: earthlike_mvp

planet:
  radius_km: 6371.0
  gravity_g: 1.0
  day_length_hours: 24.0
  axial_tilt_deg: 23.5
  orbital_eccentricity: 0.016
  stellar_luminosity: 1.0
  atmosphere_pressure_bar: 1.0
  greenhouse_factor: 1.0
  ocean_fraction_target: 0.70
  ocean_water_inventory_km3: 1338000000.0
  internal_heat: 1.0
  geological_age_ga: 4.5

mesh:
  backend: fibonacci_sphere
  cell_count: 4096
  neighbor_count: 7

tectonics:
  plate_count: 14
  continental_plate_fraction: 0.38
  continental_crust_fraction_target: 0.34
  min_angular_speed: 0.03
  max_angular_speed: 0.95
  boundary_smoothing_steps: 5
  plate_motion_scale_deg_per_step: 4.0
  oceanic_crust_aging_ma_per_step: 5.0

climate:
  months: 12
  reference_infrared_optical_depth: 1.0
  precipitation_scale: 0.8
  subtropical_drying_strength: 0.65

hydrology:
  river_percentile: 0.92
  preserve_geologic_depressions: true

erosion:
  iterations: 6
  maturation_timestep_ma: 5.0
  stream_power_coefficient: 7.5
  drainage_exponent: 0.5
  slope_exponent: 1.0
  hillslope_diffusion: 0.055
  tectonic_uplift_scale: 0.85

compute:
  backend: auto
  threads: 0
  opencl_prefer_gpu: true

output:
  include_cells: true
  float_precision: 4
```

Generate from it:

```bash
magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.json
```

Or create a fresh copy anywhere:

```bash
magic-geo init-config --profile earthlike --output runs/configs/world.yaml
magic-geo generate --config runs/configs/world.yaml --output runs/world.json
```

### Reading the range column

Ranges below are the literal pydantic `Field` bounds. `[a, b]` is inclusive (`ge`/`le`); `(a, b)` is exclusive (`gt`/`lt`); mixed forms such as `(100, 100000]` mean `gt=100.0, le=100000.0`. Every model carries `model_config = ConfigDict(extra="forbid", allow_inf_nan=False)`, so unknown keys are rejected and `.nan` / `.inf` / `-.inf` are rejected on every float field.

---

## How a config reaches the engine

```text
YAML file
  │ load_config()                     src/magic_geo/config.py
  ▼
WorldConfig (validated pydantic model) src/magic_geo/config.py
  │ config_to_native() → model_dump(mode="json")   src/magic_geo/config.py
  ▼
_native_seasonal_config() → NativeConfigV4 ctypes struct
  │ magic_geo_generate_msgpack_v4 / _json_v4
  ▼
C++ params_from_c_config → magic_geo::Params       cpp/src/c_api.cpp:13
  │ validate_params() re-checks every bound         cpp/src/engine/core.cpp:239
  ▼
simulate_world_impl(): mesh → plates → boundaries → crust/topography →
  initial climate+hydrology → erode() × iterations → cryosphere → landforms →
  (optional society)                                cpp/src/engine/pipeline.cpp
  ▼
world payload  →  Python enrichers                 src/magic_geo/api.py:195
```

The native engine re-validates every numeric bound independently in `validate_params` (`cpp/src/engine/core.cpp:239`–`432`), with the same numeric thresholds as the pydantic schema. Two constraints exist only on the native side: `plate_count` is additionally checked against the *generated* mesh size in `cpp/src/engine/pipeline.cpp:13`, and `compute_backend` is range-checked in `validate_compute_options` (`cpp/src/engine/core.cpp:233`).

---

## `run` — run identity

Model: `RunConfig`, `src/magic_geo/config.py`. Section description: "Run identity and deterministic seed settings."

| Property | Type | Default | Valid range / choices | Description |
| --- | --- | --- | --- | --- |
| `seed` | int | `424242` | `[0, 18446744073709551615]` (`MAX_SEED` = 2⁶⁴−1, `src/magic_geo/config.py`) | Unsigned 64-bit master seed used by every deterministic random process. |
| `name` | str | `"earthlike_mvp"` | 1–256 characters; additionally must contain no NUL, be UTF-8 encodable, and be ≤ 1024 UTF-8 bytes | Human-readable world name recorded in generated payload metadata. |

### `run.seed`

**What it is.** The single 64-bit entropy source for the whole generator. It is declared at `src/magic_geo/config.py` with `ge=0, le=MAX_SEED`, and marshals to a `c_uint64` (`src/magic_geo/native.py:49`).

**Where it is consumed.** Only in the tectonic seeding stage. `generate_plates` uses `std::mt19937_64 rng(params.seed ^ 0xC0FFEEULL)` (`cpp/src/engine/tectonics.cpp:15`) to draw each plate's crust bias and angular speed; `choose_plate_seeds` uses `rng(params.seed ^ 0xBAD5EEDULL)` (`cpp/src/engine/tectonics.cpp:42`); and the crust/topography derivation draws per-cell values with `signed_noise(params.seed, i, salt)` at `cpp/src/engine/tectonics.cpp:300`, `:303`, `:368`, and `:373`, and with `hash01(params.seed, i, salt)` at `:396` and `:432` (both helpers are defined at `cpp/src/engine/core.cpp:132` and `:136`). It is then echoed verbatim into the payload summary at `cpp/src/engine/summary.cpp:1319`. `params.seed` appears nowhere else in `cpp/src/` beyond the C-ABI copy in `cpp/src/c_api.cpp:15`. Every later stage — mesh construction, climate, hydrology, erosion, cryosphere, all Python enrichers — is a deterministic function of state, not of the seed directly.

**How changes propagate.** Changing the seed re-rolls plate centres, plate crust classes, plate angular speeds, and the per-cell lithology/density/age hashes. Because plates set boundaries, boundaries set uplift and crust type, and crust type sets elevation, a seed change is a complete re-roll of the world: coastlines, mountain belts, river networks, biomes, and every downstream civilization layer move. There is no way to perturb a world "slightly" through the seed.

**Interactions.** The seed does **not** by itself guarantee reproducibility: output currently varies with `compute.threads` and `OMP_NUM_THREADS` (see [Limitations](#limitations-and-unresolved-claims)). A fixed seed *plus* a fixed thread count is bit-stable in practice; a fixed seed alone is not sufficient provenance.

**Tuning.** There is no "low" or "high" seed. Treat it as an opaque label. Sweep it (as `configs/geo_validation_matrix.yaml` does with its `seed_sweep` scenarios) when you want to test that a configuration produces plausible worlds robustly rather than by luck.

### `run.name`

**What it is.** A metadata label. Declared at `src/magic_geo/config.py` with `min_length=1, max_length=256`, then narrowed by the `validate_name_for_native_boundary` field validator (`src/magic_geo/config.py`), which rejects three things with these exact messages:

| Condition | Message |
| --- | --- |
| contains `\x00` | `name must not contain NUL characters` |
| not UTF-8 encodable | `name must be well-formed Unicode encodable as UTF-8` |
| more than 1024 UTF-8 bytes | `name must be at most 1024 UTF-8 bytes` |

**Where it is consumed.** It crosses the C ABI as a `c_char_p` produced by `str(run["name"]).encode("utf-8")` (`src/magic_geo/native.py:293`), which is exactly why NUL is banned — a NUL byte would truncate the string at the boundary. On the C side a null pointer falls back to the literal `"world"` (`cpp/src/c_api.cpp:16`). It is written to the payload once, at `cpp/src/engine/world_serialization.cpp:50`.

**How changes propagate.** Not at all, physically. `name` never enters the RNG, never reaches an operator, and does not affect determinism. It only labels the payload and the debugger's world-info header.

**Interactions.** The 256-character limit and the 1024-byte limit are independent: a 256-character string of 4-byte code points is 1024 bytes and is accepted; 257 characters is rejected by `max_length` first.

**Tuning.** Use a short, stable, filesystem-friendly identifier that you also use for the artifact directory. A long name costs nothing; an unstable name destroys your ability to correlate runs.

---

## `planet` — bulk planetary properties

Model: `PlanetConfig`, `src/magic_geo/config.py`. Section description: "Planet size, gravity, orbit, atmosphere, water, heat, and age."

These twelve values are also duplicated as a literal default table in `PLANET_PARAMETER_DEFAULTS` (`src/magic_geo/planet_parameters.py:10`), which is snapshotted into the payload as the top-level `planet_parameters` object. `api.py` asserts the native engine reproduced that snapshot exactly before any enricher runs (`_require_configured_planet_snapshot`, `src/magic_geo/api.py:185`) — a mismatch raises `native planet_parameters do not match the configured planet snapshot`.

| Property | Type | Default | Valid range / choices | Description |
| --- | --- | --- | --- | --- |
| `radius_km` | float | `6371.0` | `(100.0, 100000.0]` | Mean planetary radius in kilometres; scales all surface areas and distances. |
| `gravity_g` | float | `1.0` | `(0.05, 5.0)` | Surface gravity relative to Earth gravity; affects ice, fluids, and isostasy. |
| `day_length_hours` | float | `24.0` | `(1.0, 10000.0]` | Rotation period in hours; controls Coriolis forcing and circulation structure. |
| `axial_tilt_deg` | float | `23.5` | `[0.0, 90.0]` | Axial obliquity in degrees; controls the strength of seasonal insolation. |
| `orbital_eccentricity` | float | `0.016` | `[0.0, 1.0)` | Orbital eccentricity; modulates seasonal star-distance asymmetry. |
| `stellar_luminosity` | float | `1.0` | `(0.01, 100.0]` | Incident stellar luminosity relative to the Sun; sets global climate forcing. |
| `atmosphere_pressure_bar` | float | `1.0` | `[0.0, 1000.0]` | Mean surface atmospheric pressure in bar; affects the climate energy balance. |
| `greenhouse_factor` | float | `1.0` | `[0.0, 100.0]` | Dimensionless greenhouse trapping multiplier used by the climate model. |
| `ocean_fraction_target` | float | `0.70` | `[0.0, 0.95]` | Diagnostic target fraction of surface area covered by ocean. |
| `ocean_water_inventory_km3` | float | `1338000000.0` | `[0.0, 10000000000.0]` | Connected-ocean water inventory in cubic kilometres used by sea-level solving. |
| `internal_heat` | float | `1.0` | `[0.0, 100.0]` | Internal heat flow relative to Earth; scales tectonic and geothermal activity. |
| `geological_age_ga` | float | `4.5` | `[0.01, 100.0]` | Planet age in billions of years; bounds crust age and geologic maturity. |

### `planet.radius_km`

**What it is.** The mean spherical radius. Declared at `src/magic_geo/config.py`.

**Where it is consumed.** It is the conversion factor from the unit sphere to physical units. `build_fibonacci_mesh` multiplies each control volume's solid angle by `radius_km²` to obtain `area_km2` (`cpp/src/engine/mesh.cpp:823`); the same conversion runs for the geodesic backend. From there it reaches crust transport (`cpp/src/engine/crust_transport.cpp`), plate boundary segment geometry and nominal km/Ma velocity labelling (`cpp/src/engine/plate_boundary_segments.cpp`), water feature geometry (`cpp/src/engine/water_features.cpp`), and settlement spacing (`cpp/src/engine/settlements.cpp`). On the Python side, twelve modules read it through `planet_radius_km(world)` (`src/magic_geo/planet_parameters.py:73`): `cell_geometry.py`, `hydrology_dynamics.py`, `sediment_routing.py`, `river_channel_morphology.py`, `river_network_evolution.py`, `watershed_diagnostics.py`, `ocean_circulation.py`, `cryosphere_flow.py`, `route_corridors.py`, `logistics_history.py`, `petroleum_migration.py`, and `campaign_operations_validation.py`. The strict reader `_positive_world_parameter` (`src/magic_geo/planet_parameters.py:49`) requires the value to be present, non-bool numeric, finite and `> 0`, otherwise it raises `planet_parameters.radius_km must be finite and positive` (`src/magic_geo/planet_parameters.py:69`).

**How changes propagate.** Radius is quadratic in area and linear in distance. Doubling `radius_km` at fixed `cell_count` quadruples every cell's `area_km2` and doubles every inter-cell distance, so sediment volumes (`depth_m * area_km2 / 1000`), channel lengths, catchment areas, and route lengths all move — while the number of degrees of freedom stays the same. The effective resolution *degrades* with radius unless you raise `mesh.cell_count` together with it.

**Interactions.** Radius is strongly coupled to `ocean_water_inventory_km3`: the volume that floods a given fraction of the surface scales with surface area, i.e. with `radius_km²`. `configs/seeds/ironroot_super_earth.yaml` is the worked example — at `radius_km: 9500.0` it uses `ocean_water_inventory_km3: 3020000000.0` and its own comment records that naive Earth-area scaling "fell inside a connectivity jump", so the value had to be chosen on a solvable interval instead.

**Tuning.** Low (say 3000 km) gives a small world where a 4,096-cell mesh resolves fine detail and ocean basins close with modest inventories. High (say 10000 km) gives large cells, coarse coastlines, and requires re-solving the water inventory. Earth-reference target bands are not a calibration claim for changed radius or the new seasonal climate.

### `planet.gravity_g`

**What it is.** Surface gravity as a multiple of Earth's. Declared at `src/magic_geo/config.py` with `gt=0.05, lt=5.0` (both bounds strict).

**Where it is consumed.** In the native engine it enters the crust/topography relief scale: `relief_scale = clamp(1.0 / sqrt(max(0.08, gravity_g)), 0.55, 1.60)` (`cpp/src/engine/tectonics.cpp:294`), and the precipitation multiplier `gravity_precip_factor = clamp(1.08 - 0.10 * (gravity_g - 1.0), 0.65, 1.35)` (`cpp/src/engine/climate.cpp:259`). On the Python side it is converted to absolute units by `surface_gravity_m_s2(world) = gravity_g * 9.80665` (`src/magic_geo/planet_parameters.py:85`) and read by `cryosphere_flow.py` (ice driving stress) and `river_hydraulics.py`.

**How changes propagate.** Higher gravity flattens relief (`relief_scale` shrinks as `1/√g`), slightly dries the climate, increases ice driving stress, and raises hydraulic forces in river channels. Lower gravity does the opposite: taller mountains, marginally wetter, slower ice.

**Interactions.** Both native couplings are clamped, so the physical response saturates well inside the schema range: `relief_scale` is pinned at 0.55 for `g ≳ 3.3` and at 1.60 for `g ≲ 0.39`; `gravity_precip_factor` saturates at `g ≈ 5.3` and `g ≈ -1.7`, i.e. it never saturates inside the allowed interval.

**Tuning.** Low (0.5–0.8) reads as a small, high-relief world. High (1.3–2.0) reads as a compressed, subdued super-Earth. Beyond roughly 3.3 the relief response stops changing at all, which makes very high gravity a poor lever.

### `planet.day_length_hours`

**What it is.** The rotation period in hours. Declared at `src/magic_geo/config.py` with `gt=1.0, le=MAX_DAY_LENGTH_HOURS` (10000.0, `src/magic_geo/config.py`).

**Where it is consumed.** Entirely in `cpp/src/engine/climate.cpp`. It parameterizes the prevailing wind field (`prevailing_wind_components(cell.lat, params.day_length_hours)`, `cpp/src/engine/climate.cpp:110` and `:302`), the ocean current field (`ocean_current_components(...)`, `cpp/src/engine/climate.cpp:273` and `:365`), and the circulation-band displacement `rotation_band_shift = clamp((day_length_hours - 24.0) / 24.0 * 5.0, -7.0, 9.0)` (`cpp/src/engine/climate.cpp:266`).

**How changes propagate.** It is the Coriolis proxy. A fast rotator narrows and multiplies the circulation cells; a slow rotator widens them and shifts the band structure poleward via `rotation_band_shift`. Because circulation sets the precipitation belts, this then moves deserts, rainforests, runoff, river discharge, biomes and — through the erosion loop — the drainage pattern.

**Interactions.** The band shift is clamped asymmetrically: −7 (reached at ≈ −9.6 h, unreachable) and +9 (reached at 67.2 h). Beyond ~67 h, further slowing has no additional band-shift effect, though the wind and current field functions still see the raw value.

**Tuning.** Low (12–20 h) gives a banded, zonal, Jupiter-ish circulation feel. Default 24 h is the Earth reference input. High (30–48 h) widens the Hadley-like belt and pushes the dry latitudes; `configs/seeds/oldstone_stagnant.yaml` uses 36 h, `configs/seeds/glasswind_desert.yaml` and `configs/seeds/solstice_extreme.yaml` use 30 h. Values in the hundreds or thousands of hours are inside the schema but far outside anything calibrated.

### `planet.axial_tilt_deg`

Obliquity in degrees, range `[0, 90]`, default 23.5. The native orbital/insolation calculation uses it to obtain solar declination and daily mean incident flux at each cell latitude. Temperature follows the periodic radiation, storage and transport solution. A zero tilt does not suppress distance-driven seasonal forcing on an eccentric orbit. Empirical wind seasonality still uses its separately bounded tilt factor in `climate.cpp`; those winds do not supply the conservative thermal transport graph.

### `planet.orbital_eccentricity`

Orbit ellipticity, range `[0, 1)`, default 0.016. The native solar calculation solves orbital position and inverse-square stellar distance through the year, with twelve equal elapsed-time export months. The seasonal energy producer does not clamp eccentricity to 0.8. Near-parabolic cases can require more work or fail explicitly if numerical accuracy or representability cannot be maintained. The empirical wind modifier retains its separate 0.8 clamp; it must not be confused with orbital forcing. See [native climate integration](../seasonal_climate_native_integration.md) for independent-check scope.

### `planet.stellar_luminosity`

Incident stellar flux relative to the Sun, range `(0.01, 100]`, default 1. It multiplies incoming radiation in the native energy model. The producer computes absorbed shortwave radiation with prescribed albedo 0.3 and solves temperature against outgoing longwave radiation, storage and horizontal heat convergence. It does not add a quarter-power Celsius offset. Rainfall uses the solved global area/time mean temperature through the empirical factor `clamp(exp(0.04 * (mean_temperature_c - 15)), 0.35, 2.25)`; 15°C is a rainfall reference, not an imposed temperature.

### `planet.atmosphere_pressure_bar`

Area-weighted mean surface pressure in bar, range `[0, 1000]`, default 1. Normalized hydrostatic columns preserve this mean across the terrain. Local pressure determines atmospheric heat capacity `1004 * p / g`, the pressure/gravity scaling of gray opacity, and thermal transport diffusivity `2.2e6 * atmospheric_heat_capacity`. The hydrostatic reference profile is prescribed at 288.15 K; it is not a solved vertical atmosphere. Exactly zero pressure gives zero atmospheric storage, opacity, atmospheric heat transport and rainfall. The prescribed land/marine slab still stores heat. Nonzero pressure also enters a separate bounded empirical rainfall factor.

### `planet.greenhouse_factor`

Dimensionless reference-opacity multiplier, range `[0, 100]`, default 1. Local optical depth is `tau_ref * greenhouse_factor * (p / 100000 Pa) * (9.80665 m/s² / g)`, and effective longwave emissivity is `1 / (1 + 0.75 * optical_depth)`. Higher opacity changes the energy solution; it is not a fixed Celsius increment. Zero opacity gives emissivity 1 while leaving the slab and atmospheric storage and transport otherwise present. Pressure and gravity therefore interact with this control. These are prescribed gray coefficients, without spectral radiation, evolving composition, cloud, water-vapour or ice feedback. Accepted schema bounds are not a claim of physical applicability or Earth calibration.

### `planet.ocean_fraction_target`

**What it is.** A **diagnostic** target area fraction, not a driver. Declared at `src/magic_geo/config.py`, `[0, 0.95]`.

**Where it is consumed.** Only in reporting. `sea_level_model_json` computes `target_ocean_cell_count = round(clamp(ocean_fraction_target, 0, 0.98) * cell_count)` and `target_ocean_area_km2 = clamp(...) * surface_area_km2`, and serializes the raw value (`cpp/src/engine/process_serialization.cpp:3354`, `:3375`, `:3413`). The summary emits it as `target_ocean_fraction` (`cpp/src/engine/summary.cpp:1624`). It never appears in `apply_sea_level` (`cpp/src/engine/ocean.cpp`).

**How changes propagate.** It does not. Changing it moves the reported target and the target-vs-actual residuals in the sea-level diagnostics; it does not move a single cell's water state.

**Interactions.** The knob that actually determines how much of the surface is ocean is `ocean_water_inventory_km3`. Set `ocean_fraction_target` to what you *expect*, then adjust the inventory until the achieved fraction matches; the residual is your feedback signal. Note the internal clamp is 0.98 while the schema ceiling is 0.95, so the clamp is never active from a validated config.

**Tuning.** Low (0.0, `glasswind_desert`) declares a dry-world expectation. High (0.88, `pelagic_archipelago`) declares an ocean-world expectation. Treat it as documentation plus a validation reference, never as a control.

### `planet.ocean_water_inventory_km3`

**What it is.** The volume of water available to the connected-ocean sea-level solve. Declared at `src/magic_geo/config.py`, `[0, 1e10]`, default `1.338e9` (Earth's ocean volume).

**Where it is consumed.** `apply_sea_level` reads it as `target_volume_km3` (`cpp/src/engine/ocean.cpp:29`) and solves for the sea level whose largest connected water component holds that volume, using a union-find sweep over cells sorted by elevation. A value of `0.0` (or anything `≤ 0`) takes an explicit dry branch: the datum is set just below the lowest cell, every cell is marked non-water with zero depth, and the sediment interface datum is shifted with the reason `"zero-ocean sea-level datum"` (`cpp/src/engine/ocean.cpp:30`–`47`). The achieved volume and the absolute residual against the target are reported at `cpp/src/engine/summary.cpp:1625`–`1630`. The model type is `volume_constrained_connectivity_ocean_flood_v3` (`cpp/src/engine/process_serialization.cpp:3405`).

**How changes propagate.** This is the single most consequential planet knob after radius. It sets sea level, which sets land/ocean masks, which sets continentality, which sets climate, which sets runoff, which sets rivers, which sets erosion, which feeds back into topography. It also sets shelf area, port viability, and every coastal and maritime layer.

**Interactions.** Strongly coupled to `radius_km` (surface area scales as `r²`), to `tectonics.continental_crust_fraction_target` (how much high-standing crust exists to flood around), and to the mesh resolution. Three seed presets carry explicit comments about this coupling: `ironroot_super_earth` records that Earth-area scaling landed inside a connectivity jump and 3.02e9 km³ was chosen instead; `solstice_extreme` notes 1.1e9 km³ "closes exactly in the connected-ocean solve at 2,048 cells"; `oldstone_stagnant` notes 4.3e8 km³ "closes exactly in this worn, land-heavy basin geometry". Expect to re-solve the inventory whenever you change radius, mesh size, or crust fractions.

**Tuning.** Low (2e8, `young_volcanic`; 4.3e8, `oldstone_stagnant`) leaves broad land and possibly disconnected seas. Default 1.338e9 with default radius gives an Earth-like ocean. High (2.5e9, `pelagic_archipelago`) gives a scattered-island world. **Do not** interpret this parameter as a shelf-area control: at 4,096 cells an equivalent-area cell is roughly 400 km across, so lowering one coastal cell replaces its unresolved land/shelf/slope/deep-ocean structure with a single elevation. Subcell hypsometry is not implemented.

### `planet.internal_heat`

**What it is.** Internal heat flow relative to Earth. Declared at `src/magic_geo/config.py`, `[0, 100]`.

**Where it is consumed.** It is one of the two inputs to the tectonic activity index used across `cpp/src/engine/tectonics.cpp`:

```text
tectonic_activity = clamp(internal_heat * sqrt(4.5 / max(0.05, geological_age_ga)), 0.25, 2.25)
```

(`cpp/src/engine/tectonics.cpp:19`, repeated at `:295` and `:1214`.) That index scales every plate's `angular_speed` (`cpp/src/engine/tectonics.cpp:31`), the volcanic potential index (`:496`), and the uplift rate (`:502`, `:1611`). It also drives geothermal heat flow via `clamp(internal_heat * (age_heat + boundary_heat), 18.0, 240.0)` (`cpp/src/engine/tectonics.cpp:1825`).

**How changes propagate.** Higher internal heat means faster plates, more boundary activity, more uplift, higher volcanic potential, and hotter geothermal gradients — which then feed the resource and ore-genesis enrichers. Lower heat produces a quiescent, worn planet.

**Interactions.** It is *multiplied* by `sqrt(4.5 / geological_age_ga)`, so age and heat are not independent: an old planet (`geological_age_ga: 9.5`) attenuates heat by `sqrt(4.5/9.5) ≈ 0.688`. The product is clamped to `[0.25, 2.25]`, so `internal_heat` values above ~2.25 (at default age) do nothing extra, and values below ~0.25 cannot quiet the planet further. `configs/seeds/oldstone_stagnant.yaml` reaches its stagnant premise not by heat alone (`internal_heat: 0.10`, which clamps to 0.25) but by also setting all three motion parameters to zero.

**Tuning.** Low (0.1–0.75) plus high age gives worn interiors. Default 1.0 is Earth. High (2.5, `young_volcanic`) saturates the activity clamp at 2.25 when combined with a young age. Because of the clamp, this is a *bounded* knob; use `tectonics.tectonic_uplift_scale` if you need unbounded uplift forcing.

### `planet.geological_age_ga`

**What it is.** Planet age in billions of years. Declared at `src/magic_geo/config.py`, `[0.01, 100]`.

**Where it is consumed.** Two distinct roles. First, it attenuates tectonic activity through `sqrt(4.5 / max(0.05, geological_age_ga))` (`cpp/src/engine/tectonics.cpp:19`). Second, it bounds crust age: `crust_age_ceiling_ma(params, model_ceiling) = max(0, min(model_ceiling, geological_age_ga * 1000))` (`cpp/src/engine/core.cpp:39`–`42`), and it scales the initial crust-age draw `450.0 + 900.0 * geological_age_ga * hash01(seed, i, 41)` (`cpp/src/engine/tectonics.cpp:432`). Like every planet parameter it is subject to the strict positive-and-finite reader on the Python side (`src/magic_geo/planet_parameters.py:49`, required `> 0`).

**How changes propagate.** A young planet is hot (high activity multiplier), with young, thin, low-age crust; an old planet is quiet with an aged crust ceiling. Crust age then flows into the oceanic age-depth subsidence target and the thermal-subsidence history, and into resource maturity.

**Interactions.** The `max(0.05, ...)` guard means ages below 0.05 Ga behave as 0.05 Ga in the activity term (the schema floor is 0.01). Together with `internal_heat` it is one half of a product that is clamped to `[0.25, 2.25]`.

**Tuning.** Low (0.8, `young_volcanic`) boosts activity by `sqrt(4.5/0.8) ≈ 2.37` and caps crust age at 800 Ma. Default 4.5 is Earth. High (9.5, `oldstone_stagnant`) attenuates activity by `sqrt(4.5/9.5) ≈ 0.69` and permits very old crust. Note that `geological_age_ga` and `internal_heat` are the two axes of the same activity scalar — moving both in the same direction saturates the clamp quickly.

---

## `mesh` — spherical discretisation

Model: `MeshConfig`, `src/magic_geo/config.py`. Section description: "Spherical mesh backend, resolution, and process-neighbour settings."

| Property | Type | Default | Valid range / choices | Description |
| --- | --- | --- | --- | --- |
| `backend` | enum (str) | `"fibonacci_sphere"` | `fibonacci_sphere`, `geodesic_icosahedron` | Spherical mesh construction algorithm used for world control volumes. |
| `cell_count` | int | `4096` | `[128, 200000]` | Requested number of spherical cells; controls spatial resolution and cost. |
| `neighbor_count` | int | `7` | `[4, 16]` | Target process-stencil neighbour count for the Fibonacci mesh backend. |

### `mesh.backend`

**What it is.** The tessellation algorithm. Declared at `src/magic_geo/config.py` as a two-value `Literal`.

**Where it is consumed.** It is marshalled to an integer via `MESH_BACKEND_IDS = {"fibonacci_sphere": 0, "geodesic_icosahedron": 1}` (`src/magic_geo/native.py:17`) into the `mesh_backend` field of `NativeConfigV1` (`src/magic_geo/native.py:64`). `build_mesh` dispatches on it at `cpp/src/engine/mesh.cpp:1048`; `validate_params` rejects any other integer with `unknown mesh backend` (`cpp/src/engine/core.cpp:290`). The name is echoed back through `mesh_backend_name` (`cpp/src/engine/core.cpp:104`) and the control-volume model is named accordingly: `spherical_voronoi_control_volume_v1` for Fibonacci, `spherical_barycentric_control_volume_v2` for geodesic (`cpp/src/engine/core.cpp:115`).

**How changes propagate.** Fibonacci builds a near-uniform-area point set with a k-nearest-neighbour process stencil and exact spherical Voronoi control volumes (`cpp/src/engine/mesh.cpp:776`). Geodesic subdivides an icosahedron, derives adjacency from primal triangle edges, and builds barycentric control volumes (`cpp/src/engine/mesh.cpp:890`). The two produce structurally different neighbour graphs, so the same seed and the same `cell_count` give different worlds.

**Interactions.** `neighbor_count` is only read by the Fibonacci path. `cell_count` is an exact request on the Fibonacci path and a *rounded target* on the geodesic path (see below).

**Tuning.** Use `fibonacci_sphere` (the default) for the Earth reference inputs and exact control over cell count. Use `geodesic_icosahedron` when you want the icosahedral structure and can accept a snapped resolution; `configs/seeds/continental_realm.yaml` is the shipped example, and it picks `cell_count: 2562` precisely because that is an exact geodesic count.

### `mesh.cell_count`

**What it is.** The requested number of control volumes. Declared at `src/magic_geo/config.py`, `[128, 200000]`.

**Where it is consumed.** On the Fibonacci path it is the exact number of cells built (`cpp/src/engine/mesh.cpp:777`). On the geodesic path it is a target: `geodesic_frequency_for_target(cell_count) = max(1, ceil(sqrt(max(0, (max(12, cell_count) - 2) / 10)) - 1e-9))` (`cpp/src/engine/mesh.cpp:840`), and the realized mesh has `10·f² + 2` vertices:

| Requested `cell_count` | Geodesic frequency | Realized cells |
| --- | --- | --- |
| 128 | 4 | 162 |
| 512 | 8 | 642 |
| 1024 | 11 | 1212 |
| 2048 | 15 | 2252 |
| 2562 | 16 | 2562 |
| 4096 | 21 | 4412 |
| 10242 | 32 | 10242 |
| 40962 | 64 | 40962 |

`validate_params` re-checks `[128, 200000]` at `cpp/src/engine/core.cpp:287`.

**How changes propagate.** Resolution touches everything. It sets the number of degrees of freedom in every field, the granularity of coastlines and drainage, the length of every per-cell array in the payload, and the runtime and memory cost. It also sets the effective spatial scale together with `radius_km`: at 4,096 cells on an Earth-radius sphere an equivalent-area cell is roughly 400 km across.

**Interactions.** `tectonics.plate_count` must be strictly smaller (validated in Python at `src/magic_geo/config.py` against the *requested* count, and in the native pipeline at `cpp/src/engine/pipeline.cpp:13` against the *generated* count — which differ on the geodesic path). It also interacts with `compute.backend: auto`: acceleration thresholds are evaluated against the *actual* generated cell count (`ensure_auto_backend`, `cpp/src/opencl_compute.cpp:952`), with 8,192 cells for a CUDA sm_120 device, 32,768 for an uncalibrated CUDA device, and 32,768 for OpenCL (`cpp/src/opencl_compute.cpp:99`–`101`). Sea-level connectivity is resolution-sensitive: seed presets note that a working `ocean_water_inventory_km3` is tied to a declared mesh size.

**Tuning.** Low (128–512) is the smoke/CI regime — `smoke` uses 128 and the CLI exposes `--cells` on `generate` (min 128) for exactly this (`src/magic_geo/cli/commands/generate.py:28`). Default 4,096 is the canonical Earth validation reference. High (16k–200k) gives detailed coastlines and drainage at superlinear cost and payload size, and is the only regime where accelerators are selected automatically.

### `mesh.neighbor_count`

**What it is.** The target degree of the process-stencil graph. Declared at `src/magic_geo/config.py`, `[4, 16]`.

**Where it is consumed.** Exactly once, in `build_fibonacci_mesh`: `const int k = params.neighbor_count;` then `cells[i].neighbors = index.nearest_neighbor_ids(i, k)` (`cpp/src/engine/mesh.cpp:790`–`794`). The graph is then symmetrized — every `j` in `i`'s list gets `i` appended if missing (`cpp/src/engine/mesh.cpp:807`–`814`) — so realized degrees can exceed `k`. Range-checked natively at `cpp/src/engine/core.cpp:302`.

**How changes propagate.** The stencil is what climate advection, hydrologic flow routing, sediment transport, and smoothing operators walk. A denser stencil smooths fields more aggressively per iteration and creates more candidate flow directions; a sparser one produces more angular, more channelized structure.

**Interactions.** It is **not** the control-volume topology. The exact spherical Voronoi control volumes are built independently (`build_fibonacci_control_volume`, `cpp/src/engine/mesh.cpp:820`), so `neighbor_count` does not change `area_km2` or the partition validation. It has **no effect at all** when `backend: geodesic_icosahedron`, which derives adjacency from primal triangle edges (`add_geodesic_edge`, `cpp/src/engine/mesh.cpp:869`).

**Tuning.** Default 7 approximates the natural degree of a Voronoi tessellation of a sphere. Low (4–5) gives sparse, angular routing. High (10–16) gives smoother fields and denser boundary contacts at extra per-iteration cost. `configs/seeds/ironroot_super_earth.yaml` is the only shipped preset that deviates, at 8.

---

## `tectonics` — plates and solid earth

Model: `TectonicsConfig`, `src/magic_geo/config.py`. Section description: "Plate count, crust allocation, motion, and boundary smoothing."

| Property | Type | Default | Valid range / choices | Description |
| --- | --- | --- | --- | --- |
| `plate_count` | int | `14` | `[2, 256]`, and strictly `< mesh.cell_count` | Number of tectonic plates; must remain smaller than mesh.cell_count. |
| `continental_plate_fraction` | float | `0.38` | `[0.0, 1.0]` | Fraction of plate seeds assigned a continental bias. |
| `continental_crust_fraction_target` | float | `0.34` | `[0.0, 0.95]` | Target fraction of surface control-volume area assigned continental crust. |
| `min_angular_speed` | float | `0.03` | `[0.0, 100.0]`, and `≤ max_angular_speed` | Minimum procedural plate angular-speed index; must not exceed the maximum. |
| `max_angular_speed` | float | `0.95` | `[0.0, 100.0]`, and `≥ min_angular_speed` | Maximum procedural plate angular-speed index used for boundary activity. |
| `boundary_smoothing_steps` | int | `5` | `[0, 32]` | Number of deterministic plate-boundary label smoothing iterations. |
| `plate_motion_scale_deg_per_step` | float | `2.0` | `[0.0, 10.0]` | Plate displacement scale in degrees per five-million-year reference step. |
| `oceanic_crust_aging_ma_per_step` | float | `5.0` | `[0.0, 50.0]` | Quiet oceanic-crust ageing in Ma per five-million-year reference step. |

### `tectonics.plate_count`

**What it is.** The number of rigid plate domains. Declared at `src/magic_geo/config.py`, `[2, 256]`.

**Where it is consumed.** `generate_plates` allocates exactly this many plates (`cpp/src/engine/tectonics.cpp:18`–`20`); `choose_plate_seeds` draws that many distinct seed cells (`cpp/src/engine/tectonics.cpp:46`); every cell is then assigned to its nearest plate centre. It also bounds the plate-origin key space that the dry-rock accounting counter-model validates every packet against — `origin_plate_id >= plate_count` is rejected in `validate_packet_key` (`cpp/src/engine/crust_reservoir.cpp:43`–`48`). The native pipeline enforces `plate_count < generated cell count` and throws `plate_count must be smaller than generated mesh cell count` otherwise (`cpp/src/engine/pipeline.cpp:13`).

**How changes propagate.** Plate count sets boundary density. More plates means more boundary length per unit area, hence more convergence/divergence forcing, more mountain belts and ridges, and a more fragmented land distribution. Fewer plates means broad interiors, long quiet regions, and a few very large orogens.

**Interactions.** Hard constraint against `mesh.cell_count` (`src/magic_geo/config.py`). Also interacts with `boundary_smoothing_steps`: at high plate counts on a coarse mesh, boundaries are only a few cells wide and heavy smoothing can erase them.

**Tuning.** Low (6, `oldstone_stagnant`; 8, `glasswind_desert` and the `smoke` profile) gives broad, stable domains. Default 14 is the Earth-like reference. High (24, `pelagic_archipelago`; 28, `young_volcanic`) gives dense boundaries and a shattered, high-relief surface.

### `tectonics.continental_plate_fraction`

**What it is.** The probability that a plate is seeded with a continental bias. Declared at `src/magic_geo/config.py`, `[0, 1]`.

**Where it is consumed.** In `generate_plates`, as a threshold on a uniform draw: `if (draw < continental_plate_fraction) { … continental … } else if (draw < continental_plate_fraction + 0.22) { … }` (`cpp/src/engine/tectonics.cpp:23`–`25`). Note the second branch adds a fixed 0.22 band, so the class assignment is a three-way split, not a binary one.

**How changes propagate.** It biases *which plates* are continental, and therefore where continental crust tends to cluster. Because plates are large, this controls the **spatial arrangement** of land — a few big continents versus many scattered ones.

**Interactions.** This is distinct from `continental_crust_fraction_target`, which controls **how much** continental crust exists by area. Setting a high plate fraction with a low area target produces many nominally continental plates with thin continental cores; the inverse produces a few very large landmasses. The `+ 0.22` band means values above 0.78 leave no room for the third class.

**Tuning.** Low (0.28–0.30, `pelagic_archipelago`, `young_volcanic`) scatters land. Default 0.38 is Earth-like. High (0.70–0.78, `oldstone_stagnant`, `glasswind_desert`) makes most plates continental and yields consolidated supercontinent-like arrangements.

### `tectonics.continental_crust_fraction_target`

**What it is.** The target share of total surface control-volume **area** assigned continental crust. Declared at `src/magic_geo/config.py`, `[0, 0.95]`.

**Where it is consumed.** In the crust/topography derivation, converted to a cell count: `static_cast<int>(llround(continental_crust_fraction_target * n))` (`cpp/src/engine/tectonics.cpp:342`), which the crust allocator aims for. Range-checked natively at `cpp/src/engine/core.cpp:382`.

**How changes propagate.** Continental crust is thicker and less dense than oceanic crust, so it stands higher after isostatic equilibrium. Raising the target raises the fraction of high-standing crust, which — at fixed water inventory — raises the ocean's flooded fraction of the *remaining* low crust and changes the land/ocean mask, coastline length, and shelf structure.

**Interactions.** This is the strongest partner of `ocean_water_inventory_km3`. Change one and the achieved ocean fraction moves; the three shipped land-rich presets (`continental_realm` at 0.52, `oldstone_stagnant` at 0.65, `glasswind_desert` at 0.72) all pair a high crust target with a reduced water inventory. It is also distinct from `continental_plate_fraction` (arrangement, not amount).

**Tuning.** Low (0.18, `pelagic_archipelago`; 0.24, `young_volcanic`) gives an ocean world with island arcs. Default 0.34 is Earth-like. High (0.65–0.72) gives a land-dominated world where the ocean occupies only the deepest basins.

### `tectonics.min_angular_speed`

**What it is.** The lower bound of the procedural intrinsic plate angular-speed **index**. Declared at `src/magic_geo/config.py`, `[0, 100]`.

**Where it is consumed.** Each plate draws `angular_speed = (min_angular_speed + (max_angular_speed - min_angular_speed) * uniform) * tectonic_activity` (`cpp/src/engine/tectonics.cpp:31`–`32`).

**How changes propagate.** It guarantees a floor on plate mobility. Raising it removes the possibility of a nearly-stationary plate, so every boundary carries some convergence/divergence forcing and no plate interior stays fully quiet.

**Interactions.** It is multiplied by the clamped `tectonic_activity` index (from `internal_heat` and `geological_age_ga`), and the resulting `angular_speed` is later multiplied by `plate_motion_scale_deg_per_step` and the timestep scale to obtain an actual rotation (`cpp/src/engine/tectonics.cpp:1127`–`1128`). The cross-field validator `validate_speeds` (`src/magic_geo/config.py`) rejects `max_angular_speed < min_angular_speed` with `max_angular_speed must be >= min_angular_speed`; the native side repeats this at `cpp/src/engine/core.cpp:364`–`366`.

**Tuning.** Low (0.0–0.02) permits nearly-frozen plates; `oldstone_stagnant` sets both bounds to `0.0` for a fully stagnant premise. Default 0.03 is a light floor. High (0.30, `young_volcanic`) forces universal motion. This is **not** calibrated in degrees per million years — it is a dimensionless index.

### `tectonics.max_angular_speed`

**What it is.** The upper bound of the same procedural index. Declared at `src/magic_geo/config.py`, `[0, 100]`.

**Where it is consumed.** Same draw as above (`cpp/src/engine/tectonics.cpp:31`–`32`).

**How changes propagate.** It sets the ceiling on plate mobility and therefore on peak proxy convergence/divergence, which is what drives ridge, rift, orogen, trench, and volcanic terms in the initial elevation (`cpp/src/engine/tectonics.cpp:495`) and the uplift rate (`:502`).

**Interactions.** Same clamped `tectonic_activity` multiplier, same `plate_motion_scale_deg_per_step` product, same cross-field validator. Note that `angular_speed` can exceed `max_angular_speed` after the activity multiplier, since `tectonic_activity` reaches 2.25.

**Tuning.** Low (0.45, `glasswind_desert`; 0.70, `cryogenic_slushball`) keeps boundaries mild. Default 0.95 is Earth-like. High (1.15, `pelagic_archipelago`; 1.80, `young_volcanic`) produces vigorous boundaries and dramatic relief. It is explicitly **not** a physical plate-rate bound.

### `tectonics.boundary_smoothing_steps`

**What it is.** The number of deterministic label-smoothing iterations applied to the boundary forcing fields. Declared at `src/magic_geo/config.py`, `[0, 32]`.

**Where it is consumed.** In `classify_boundaries`, to smooth the convergence, divergence, and transform fields. The engine first offers the three fields to `try_accelerated_smooth_three_fields(cells, conv, div, trans, boundary_smoothing_steps, 0.58, 0.58, 0.62, …)` (`cpp/src/engine/tectonics.cpp:163`–`174`); if that declines, the CPU fallback runs `smooth_field(cells, conv, boundary_smoothing_steps, 0.58)`, `smooth_field(cells, div, …, 0.58)`, and `smooth_field(cells, trans, …, 0.62)` (`cpp/src/engine/tectonics.cpp:180`–`182`). Both paths use the same iteration count and weights; note the transform field uses a different weight from the other two.

**How changes propagate.** Smoothing widens and softens boundary forcing. Low values produce crenulated, one-cell-wide, sharply contrasting boundaries; high values produce broad, diffuse orogenic belts and gentler ridges. Because the smoothed fields drive uplift and crust rules, this changes mountain-belt width and the sharpness of every downstream contrast.

**Interactions.** Interacts with `mesh.cell_count` and `mesh.neighbor_count` — smoothing operates on the process stencil, so a denser stencil smooths further per iteration. At high `plate_count` on a coarse mesh, heavy smoothing can blend adjacent boundaries together.

**Tuning.** Low (2, `young_volcanic`; 3, `pelagic_archipelago`) gives sharp, violent boundaries. Default 5 is the reference. High (8, `glasswind_desert`; 12, `oldstone_stagnant`) gives broad, worn belts appropriate to a quiet planet. `0` disables smoothing entirely.

### `tectonics.plate_motion_scale_deg_per_step`

**What it is.** The displacement multiplier at the 5 Ma reference step. Declared at `src/magic_geo/config.py`, `[0, 10]`.

**Where it is consumed.** In `advance_plate_motion_and_crust`: `rotation_deg = plate.angular_speed * plate_motion_scale_deg_per_step * timestep_scale`, applied by rotating the plate centre about its Euler axis (`cpp/src/engine/tectonics.cpp:1127`–`1131`). `timestep_scale` is `maturation_timestep_ma / 5.0` (`cpp/src/engine/core.cpp:44`, with `MATURATION_REFERENCE_TIMESTEP_MA = 5.0` at `cpp/src/engine/constants.hpp:72`). The plate boundary segment ledger also uses it to label nominal km/Ma velocities (`cpp/src/engine/plate_boundary_segments.cpp`).

**How changes propagate.** It sets how far plates actually move per erosion iteration, hence how much crust is transported, how much overlap is generated, how much the boundary geometry evolves, and how much cumulative rotation accrues. It is the main driver of the crust transport, overlap, and material-shadow histories.

**Interactions.** Multiplied by the per-plate `angular_speed` (itself the product of the min/max draw and `tectonic_activity`) and by `erosion.maturation_timestep_ma / 5`. It only has an effect when `erosion.iterations > 0`. Both the `earthlike` and `smoke` profiles raise it from the schema default of 2.0 to **4.0**.

**Tuning.** `0.0` freezes plate motion entirely (`oldstone_stagnant`). Low (1.5, `glasswind_desert`) gives slow drift. The profile value 4.0 is retained from the previous Earth reference inputs. High (4.5, `young_volcanic`) is aggressive. This remains a heuristic kinematic scale, **not** a calibrated angular velocity, and the derived km/Ma labels are nominal.

### `tectonics.oceanic_crust_aging_ma_per_step`

**What it is.** The age increment applied to quiet oceanic crust at the 5 Ma reference step. Declared at `src/magic_geo/config.py`, `[0, 50]`.

**Where it is consumed.** Only inside the quiet-oceanic branch of the crust process: when a cell is old-oceanic and both divergence and convergence are below 0.10, `crust_age += oceanic_crust_aging_ma_per_step * timestep_scale * quiet_fraction`, where `quiet_fraction = clamp(1.0 - max(div, conv) / 0.10, 0, 1)` (`cpp/src/engine/tectonics.cpp:1327`–`1331`). The reason code is `CRUST_PROCESS_QUIET_OCEANIC_AGING`.

**How changes propagate.** Crust age drives the oceanic age–depth subsidence target (`-350·√age` m through 70 Ma, then a Parsons–Sclater-shaped branch offset for value continuity, `cpp/src/engine/oceanic_age_depth.cpp`), so faster ageing deepens quiet ocean basins over the run and changes the achieved ocean volume and hypsometry.

**Interactions.** Scaled by `erosion.maturation_timestep_ma / 5` and gated by the boundary forcing thresholds, so it applies only to genuinely quiet interiors. It is bounded above by `crust_age_ceiling_ma`, which is `min(model ceiling, geological_age_ga * 1000)` (`cpp/src/engine/core.cpp:39`).

**Tuning.** `0.0` freezes quiet-crust ageing (`oldstone_stagnant`). Default 5.0 makes one reference step advance one step's worth of age. High (6.0, `pelagic_archipelago`; 8.0, `young_volcanic`) ages seafloor faster than wall-clock steps, deepening basins sooner.

---

## `climate` — temperature and precipitation drivers

The current `ClimateConfig` is the strict `SeasonalClimateConfig` in `src/magic_geo/seasonal_config.py`.

| Property | Type | Default | Valid range | Meaning |
| --- | --- | --- | --- | --- |
| `months` | integer literal | `12` | exactly integer `12` | Twelve equal elapsed-time export months. |
| `reference_infrared_optical_depth` | float | `1.0` | finite, nonnegative | Gray optical depth at one bar and Earth gravity before greenhouse scaling. |
| `precipitation_scale` | float | `1.0` | `[0, 10]` | Empirical rainfall multiplier; zero is an exact dry boundary. |
| `subtropical_drying_strength` | float | `0.65` | `[0, 0.9]` | Empirical descending-air drying strength. |

### `climate.months`

Fixed to the integer 12. The native solution exports monthly mean temperature and monthly means of `T⁴`, radiation, storage and transport together with thirteen boundary temperatures. Monthly temperatures are not a fitted cosine. Boolean, string and floating-point lookalikes for `months` are rejected.

### `climate.reference_infrared_optical_depth`

Finite nonnegative gray optical depth at one bar and Earth gravity, default 1. It combines with local pressure, gravity and `planet.greenhouse_factor` as described above. There is no arbitrary finite upper bound; unrepresentable coefficients or failure to converge produce generation errors. The shipped scenarios explicitly use 1 as a declared baseline, not a fit to their former imposed mean temperatures.

The retired `climate.base_temperature_c` and `climate.lapse_rate_c_per_km` fields are rejected individually with migration guidance. Remove them and choose opacity under its physical meaning; no equivalent automatic conversion exists. Elevation affects hydrostatic columns and associated thermal coefficients, but a free lapse correction is not added to the solved surface temperature. The explicit Python `LegacyWorldConfig` and old C ABI versions preserve old-model behavior for compatibility callers.

### `climate.precipitation_scale`

**What it is.** A global multiplier on annual precipitation. Declared at `src/magic_geo/config.py`, `[0, 10]`.

**Where it is consumed.** In the annual precipitation product: `annual *= precipitation_scale * pressure_precip_factor * gravity_precip_factor * orographic_factor * rain_shadow_factor * ocean_current_moisture_factor * advected_moisture_factor * circulation_precip_factor * subtropical_drying_factor * monsoon_precipitation_factor` (`cpp/src/engine/climate.cpp:460`–`463`). The result is clamped at zero (`max(0.0, annual)`, `cpp/src/engine/climate.cpp:468`) before being divided across the twelve months, and only then is the thermal-moisture capacity factor applied (`cpp/src/engine/climate.cpp:469`+).

**How changes propagate.** Precipitation drives runoff, which drives flow accumulation, which drives river classification and the stream-power incision term, which drives topography, which feeds back into orography and precipitation. It also sets soil moisture, biome classification, wetlands, lakes, and agricultural potential in the enrichers.

**Interactions.** `0.0` is an exact dry boundary — every cell gets zero precipitation, so there is no runoff and no fluvial incision, regardless of `erosion.stream_power_coefficient`. Because it multiplies a sum that can be negative (the empirical latitudinal combination at `cpp/src/engine/climate.cpp:451` includes `-610 * subtropic`), the zero clamp happens after scaling, so near-zero positive values stay proportional instead of crossing a discontinuous floor. Both the `earthlike` and `smoke` profiles set it to **0.8**, drier than the schema default.

**Tuning.** Very low (0.08, `glasswind_desert`) with high `subtropical_drying_strength` is the desert-world recipe. Low (0.5–0.65, `young_volcanic`, `cryogenic_slushball`, `oldstone_stagnant`) gives arid worlds. The profile value 0.8 is retained from the previous inputs; seasonal climate calibration is not established. High (1.4, `pelagic_archipelago`; 1.8, `verdant_hothouse`) gives a wet world with large rivers and vigorous incision.

### `climate.subtropical_drying_strength`

**What it is.** The intensity of the descending-air dry belts. Declared at `src/magic_geo/config.py`, `[0, 0.9]` — note the ceiling is 0.9, not 1.0.

**Where it is consumed.** As the subtropical drying factor:

```text
subtropical_drying_factor = clamp(
    1.0 - subtropical_drying_strength * subtropic * (1.0 + 0.15 * cold_current_drying_index),
    CLIMATE_SUBTROPICAL_DRYING_MIN_FACTOR, 1.0)
```

(`cpp/src/engine/climate.cpp:453`–`458`), where `cold_current_drying_index = clamp(-current_temp / 4.5, 0, 1)` (`:452`) couples cold offshore currents into the drying. The factor then multiplies annual precipitation at `cpp/src/engine/climate.cpp:460`–`463`. Range-checked natively at `cpp/src/engine/core.cpp:391`.

**How changes propagate.** It carves the horse-latitude desert belts. Raising it deepens and widens the subtropical arid zones, which removes runoff there, suppresses river formation, and pushes desert biomes; because the erosion loop is coupled, those regions also stop incising and retain more relief.

**Interactions.** The `0.9` ceiling plus the internal minimum factor means the belts can never be made perfectly dry by this knob alone. It multiplies rather than replaces `precipitation_scale`, so the desert recipe is both: `glasswind_desert` uses `precipitation_scale: 0.08` **and** `subtropical_drying_strength: 0.88`. The cold-current term means the effect is stronger on west-facing coasts with cold currents.

**Tuning.** Low (0.30, `verdant_hothouse`; 0.45, `pelagic_archipelago` and `cryogenic_slushball`) gives a wet, weakly banded world with continuous vegetation. Default 0.65 gives Earth-like desert belts. High (0.72–0.88, `oldstone_stagnant`, `glasswind_desert`) gives pronounced global desert bands.

---

## `hydrology` — routing and river classification

Model: `HydrologyConfig`, `src/magic_geo/config.py`. Section description: "River classification and closed-basin routing policy."

| Property | Type | Default | Valid range / choices | Description |
| --- | --- | --- | --- | --- |
| `river_percentile` | float | `0.92` | `[0.50, 0.995]` | Flow-accumulation percentile threshold used to classify river cells. |
| `preserve_geologic_depressions` | bool | `true` | `true`, `false` | Keep geologic closed basins instead of filling every depression to an outlet. |

### `hydrology.river_percentile`

**What it is.** The percentile of the sorted flow-accumulation distribution above which a land cell is labelled a river. Declared at `src/magic_geo/config.py`, `[0.50, 0.995]`.

**Where it is consumed.** In the river classification step: `idx = clamp(river_percentile, 0.5, 0.999) * (accum.size() - 1)` over the sorted accumulation array (`cpp/src/engine/hydrology.cpp:712`). The same clamped expression is recomputed for summary diagnostics (`cpp/src/engine/summary.cpp:1300`–`1307`), and the raw value is echoed as the summary key `river_extraction_percentile` with at least six decimals (`cpp/src/engine/summary.cpp:1356`–`1357`), alongside `river_extraction_model` = `flow_accumulation_percentile_on_conditioned_hydrologic_surface_v1` and the derived `river_flow_accumulation_threshold`. Range-checked natively at `cpp/src/engine/core.cpp:403`.

**How changes propagate.** It is a **classification** threshold, not a physical one. It does not change flow routing, flow accumulation, discharge, or erosion — those are computed first. It changes which cells carry `is_river`, and therefore river count, network extent and connectivity, and every downstream layer that keys off river presence: navigability, port siting, route corridors, settlement placement, and riverine political boundaries.

**Interactions.** Because it is a percentile of the *land, positive-accumulation* population, its absolute meaning shifts with `mesh.cell_count`, `precipitation_scale`, and the land fraction. A 0.92 threshold on a wet, land-rich world yields far more absolute river cells than the same threshold on a dry ocean world. The internal clamp is `[0.5, 0.999]`, slightly wider than the schema's `[0.50, 0.995]`, so the clamp never binds from a validated config.

**Tuning.** Low (0.86, `verdant_hothouse`; 0.88, `pelagic_archipelago`) gives a dense, capillary network — good for wet worlds and for maximum route/settlement connectivity. Default 0.92 is the reference. High (0.94–0.97, `oldstone_stagnant`, `cryogenic_slushball`, `glasswind_desert`) gives only major trunk rivers, appropriate to arid worlds.

### `hydrology.preserve_geologic_depressions`

**What it is.** The closed-basin policy. Declared at `src/magic_geo/config.py`, default `true`.

**Where it is consumed.** In depression handling: a sink is treated as a preserved geologic depression only when `preserve_geologic_depressions && is_geologic_depression(sink_cell)` (`cpp/src/engine/hydrology.cpp:556`). When true, qualifying sinks stay endorheic instead of entering numeric-depression correction; when false, depressions are filled toward an outlet.

**How changes propagate.** It sets `depression_policy`, `is_closed_basin`, and the contents of the numeric-depression correction ledger and the hydrologic water-budget history. Preserved basins become terminal lakes and saline basins, alter the lake-overflow history, and change which watersheds are endorheic — which in turn changes catchment-area statistics, sediment terminal footprints, and the exorheic/endorheic split used by calibration against HydroBASINS/HydroRIVERS.

**Interactions.** Its effect is largest on worlds with strong closed-basin topography (low water inventory, high continental crust). `configs/seeds/verdant_hothouse.yaml` is the only shipped preset that sets it `false`, with the inline comment "Fill closed basins in this preset to favor connected through-drainage."

**Tuning.** `true` (default) is the physically richer choice: it produces Dead-Sea/Caspian-style terminal basins and preserves the distinction between numerical artefacts and genuine geology. `false` produces a fully through-drained surface where every land cell routes to the sea — simpler networks, more connected rivers, no endorheic lakes.

---

## `erosion` — landscape maturation

Model: `ErosionConfig`, `src/magic_geo/config.py`. Section description: "Landscape maturation timestep, incision, diffusion, and uplift settings."

The loop this section controls is `erode(...)` in `cpp/src/engine/earth_system.cpp:928`. Each iteration advances plate motion and crust, transports hillslope sediment, applies stream-power incision, routes fluvial sediment, and records a feedback and plate-motion history entry.

| Property | Type | Default | Valid range / choices | Description |
| --- | --- | --- | --- | --- |
| `iterations` | int | `6` | `[0, 250]` | Number of coupled tectonic, climate, hydrology, and erosion transitions. |
| `maturation_timestep_ma` | float | `5.0` | `(0.0, 5.0]` | Nominal millions of years represented by each maturation transition. |
| `stream_power_coefficient` | float | `7.5` | `[0.0, 1000.0]` | Reference-step stream-power incision coefficient. |
| `drainage_exponent` | float | `0.5` | `[0.0, 2.0]` | Drainage-area exponent in the stream-power erosion relation. |
| `slope_exponent` | float | `1.0` | `[0.0, 3.0]` | Terrain-slope exponent in the stream-power erosion relation. |
| `hillslope_diffusion` | float | `0.055` | `[0.0, 1.0]` | Reference hillslope sediment-diffusion coefficient. |
| `tectonic_uplift_scale` | float | `0.85` | `[0.0, 10.0]` | Dimensionless multiplier on tectonic uplift supplied to landscape maturation. |

### `erosion.iterations`

**What it is.** The number of coupled maturation transitions. Declared at `src/magic_geo/config.py`, `[0, 250]`.

**Where it is consumed.** The loop bound: `for (int iter = 0; iter < params.erosion_iterations; ++iter)` (`cpp/src/engine/earth_system.cpp:928`). It also determines the length of the plate-motion, feedback, sediment-routing, hillslope-transport, crust-material-shadow, and dry-rock-accounting histories (`cpp/src/engine/process_serialization.cpp` references `erosion_iterations` in twelve places). Range-checked natively at `cpp/src/engine/core.cpp:406`.

**How changes propagate.** More iterations means more accumulated plate displacement, more crust transport and overlap, more incision, more sediment routed, deeper valleys, more mature drainage networks, and larger histories in the payload. Runtime and payload size scale roughly linearly with it.

**Interactions.** Total nominal model time is `iterations × maturation_timestep_ma` — but see the caveat below: this is a nominal coordinate, not calibrated physical time. `iterations: 0` is the single coarse off-switch for the whole feedback loop: no plate motion is applied, no incision runs, and only the initial tectonic/climate/hydrology snapshot plus the terminal cryosphere pass survive. Total dry-rock accounting load also grows with iterations; `configs/seeds/young_volcanic.yaml` carries an explicit comment that six steps keep it "inside the engine's finite dry-rock accounting envelope at the declared resolution".

**Tuning.** `0` is a tectonics-only preview. `1` is the `smoke` profile — fast CI runs. Default `6` is the Earth-like reference. High (`7`, `verdant_hothouse`; `10`, `oldstone_stagnant`) gives worn, mature landscapes at proportionally higher cost. Values near the 250 ceiling produce enormous histories.

### `erosion.maturation_timestep_ma`

**What it is.** The nominal millions of years each transition represents. Declared at `src/magic_geo/config.py` with `gt=0.0, le=5.0` — refinement below 5 Ma is allowed, coarsening above it is **rejected**.

**Where it is consumed.** Through a single scale factor `maturation_timestep_scale(params) = maturation_timestep_ma / MATURATION_REFERENCE_TIMESTEP_MA` where the reference is 5.0 (`cpp/src/engine/core.cpp:44`–`46`, `cpp/src/engine/constants.hpp:72`). That scale multiplies: plate rotation (`cpp/src/engine/tectonics.cpp:1128`), quiet oceanic crust ageing (`:1329`), the uplift rate (`:502`, `:1611`), the hillslope effective diffusivity (`cpp/src/engine/earth_system.cpp:361`), and the applied fluvial incision depth (`cpp/src/engine/earth_system.cpp:987`). Fractional per-step responses are converted through `timestep_scaled_fraction`, which uses `-expm1(scale · log1p(-fraction))` so that repeated sub-steps compose correctly rather than summing linearly (`cpp/src/engine/core.cpp:48`–`64`). Natively re-checked with `maturation_timestep_ma <= 0.0 || > 5.0` at `cpp/src/engine/core.cpp:388`.

**How changes propagate.** Refining the step (say to 2.5 Ma) halves the continuous mutation applied per iteration, so you need twice the iterations for the same nominal elapsed time — but the *sequence* of remap and event impulses doubles, so the result is not identical. Crucially, `cell.erosion_rate` is deliberately kept as the **5 Ma reference response**, not the applied depth (`cpp/src/engine/earth_system.cpp:988`–`993`, with an inline comment explaining that otherwise "merely refining dt changes soils, ecosystems, land use, and resource diagnostics by construction").

**Interactions.** Multiplies with `plate_motion_scale_deg_per_step`, `oceanic_crust_aging_ma_per_step`, `tectonic_uplift_scale`, `hillslope_diffusion`, and `stream_power_coefficient` — every one of the continuous forcings. Pair a refined step with more `iterations` if you want comparable maturity.

**Tuning.** Default 5.0 is the shipped reference step. Refine to 4.0 (`verdant_hothouse`), 3.0 (`oldstone_stagnant`), or 2.5 (`young_volcanic`) when large per-step displacements produce unstable or implausible geometry. Values above 5.0 are rejected because the explicit operators do not implement stable coarse-step subcycling. **This is not calibrated physical time**; the payload keeps `physical_time_resolved: false`.

### `erosion.stream_power_coefficient`

**What it is.** The erodibility coefficient K of the stream-power incision law. Declared at `src/magic_geo/config.py`, `[0, 1000]`.

**Where it is consumed.** In the incision term:

```text
stream = stream_power_coefficient * erodability * pow(acc_norm, drainage_exponent)
                                  * pow(max(0, slope * 900.0), slope_exponent)
erosion_depth_m = stream * maturation_timestep_scale(params)
cell.erosion_rate = stream          // reference-normalized, not the applied depth
```

(`cpp/src/engine/earth_system.cpp:984`–`993`), where `erodability = 1.0 / lithology_resistance(cell.lithology)` and `acc_norm = clamp(flow_accumulation / acc_scale, 0.0, 3.0)` with `acc_scale` the 95th percentile of land accumulation (`cpp/src/engine/earth_system.cpp:946`). Range-checked natively at `cpp/src/engine/core.cpp:410`.

**How changes propagate.** It is the master erosivity knob. Raising it deepens valleys, lowers ridges faster, produces more sediment (which is then routed and deposited), flattens relief over the run, and increases the sediment thickness recorded in the sediment interface. Lowering it preserves tectonic relief.

**Interactions.** It competes directly with `tectonic_uplift_scale` — the landscape's steady state is roughly where uplift balances incision. It is inert wherever there is no runoff, so `precipitation_scale: 0.0` neutralizes it. Water cells are skipped entirely (`erosion_rate = 0`, `cpp/src/engine/earth_system.cpp:975`). It multiplies with the timestep scale for the *applied* depth but not for the *reported* rate.

**Tuning.** Low (3.0, `glasswind_desert`; 4.5, `cryogenic_slushball`) preserves relief on dry or cold worlds. Default 7.5 is the reference. High (9.0–11.0, `pelagic_archipelago`, `oldstone_stagnant`, `verdant_hothouse`) carves deep, mature valleys. `0.0` disables fluvial incision while leaving hillslope diffusion active.

### `erosion.drainage_exponent`

**What it is.** The exponent m on normalized drainage area in `E ∝ Aᵐ Sⁿ`. Declared at `src/magic_geo/config.py`, `[0, 2]`.

**Where it is consumed.** `pow(acc_norm, drainage_exponent)` at `cpp/src/engine/earth_system.cpp:985`, where `acc_norm` is flow accumulation normalized by the 95th percentile and clamped to `[0, 3]`.

**How changes propagate.** It sets how strongly big rivers out-erode small ones. High m concentrates incision in trunk channels, producing deep main valleys with preserved interfluves; low m spreads incision evenly, producing broad, uniformly lowered surfaces. Because m shapes the concavity of the longitudinal profile, it also shapes the χ/slope–area relation that the calibration suite compares against HydroRIVERS.

**Interactions.** Only the *ratio* m/n controls channel concavity; the absolute pair plus K controls rate. Because `acc_norm` is clamped at 3.0, exponents above ~1 saturate quickly for the largest channels. `drainage_exponent: 0.0` makes incision independent of discharge, which produces a slope-only landscape.

**Tuning.** Default 0.5 with `slope_exponent: 1.0` gives m/n = 0.5, the classical bedrock-river concavity. Slightly lower (0.45, `glasswind_desert`) flattens the discharge dependence for an arid world; slightly higher (0.55, `verdant_hothouse`, `young_volcanic`) sharpens trunk-channel dominance. Values approaching 2.0 are inside the schema but far outside the calibrated regime.

### `erosion.slope_exponent`

**What it is.** The exponent n on slope in `E ∝ Aᵐ Sⁿ`. Declared at `src/magic_geo/config.py`, `[0, 3]`.

**Where it is consumed.** `pow(max(0.0, slope * 900.0), slope_exponent)` at `cpp/src/engine/earth_system.cpp:985`, where `slope` is the hydrologic flow slope toward the downstream cell (`cpp/src/engine/earth_system.cpp:980`) and 900.0 is a fixed internal scale factor.

**How changes propagate.** It sets how sharply erosion responds to steepness. n = 1 is linear; n > 1 makes steep sections erode disproportionately, which sharpens knickpoint propagation and accelerates the destruction of high relief; n < 1 lets steep terrain survive longer.

**Interactions.** With `drainage_exponent` it sets the equilibrium channel concavity m/n. With `stream_power_coefficient` it sets the rate. Because the slope is multiplied by 900 before exponentiation, the effective sensitivity to n is large — a slope of 0.01 becomes 9.0, so `n = 1.2` versus `n = 1.0` is a factor of ≈ 1.55 at that slope.

**Tuning.** Default 1.0 is the reference. Slightly higher (1.1, `pelagic_archipelago` and `verdant_hothouse`; 1.2, `young_volcanic`) suits high-relief, tectonically active worlds where you want rapid knickpoint retreat. `0.0` removes slope dependence entirely, producing accumulation-only incision.

### `erosion.hillslope_diffusion`

**What it is.** The hillslope sediment-diffusion coefficient. Declared at `src/magic_geo/config.py`, `[0, 1]`.

**Where it is consumed.** In `transport_hillslope_sediment`, per source→target neighbour pair with a positive elevation drop:

```text
effective_diffusivity = min(HILLSLOPE_MAX_EFFECTIVE_DIFFUSIVITY,
                            max(0, hillslope_diffusion) * maturation_timestep_scale(params)
                            / max(1e-12, lithology_resistance(source.lithology)))
```

(`cpp/src/engine/earth_system.cpp:358`–`363`), followed by a depth proportional to `effective_diffusivity * elevation_drop_m` divided across the source's neighbours (`cpp/src/engine/earth_system.cpp:369`+). Water cells and non-positive drops are skipped (`cpp/src/engine/earth_system.cpp:354`). Range-checked natively at `cpp/src/engine/core.cpp:421`.

**How changes propagate.** Diffusion rounds ridges and fills hollows. Raising it smooths the surface, converts sharp crests into convex hilltops, and feeds the hillslope sediment production/deposition ledgers. It is the counterpart to fluvial incision: incision cuts channels, diffusion degrades the divides between them.

**Interactions.** Scaled by the timestep, divided by lithology resistance (so soft lithologies diffuse faster), and capped by an internal maximum effective diffusivity — so very large configured values saturate. It works even when `precipitation_scale: 0.0`, making it the only surface-lowering process on a dry world.

**Tuning.** Low (0.025, `glasswind_desert`; 0.040, `cryogenic_slushball`) preserves angular relief. Default 0.055 is the reference. High (0.070–0.10, `pelagic_archipelago`, `verdant_hothouse`, `young_volcanic`, `oldstone_stagnant`) gives rounded, worn topography. `0.0` disables hillslope transport entirely — note the code short-circuits when `effective_diffusivity <= 0` (`cpp/src/engine/earth_system.cpp:364`).

### `erosion.tectonic_uplift_scale`

**What it is.** A dimensionless multiplier on the uplift supplied to maturation. Declared at `src/magic_geo/config.py`, `[0, 10]`.

**Where it is consumed.** In the uplift rate, both at initial crust derivation and at each motion step:

```text
cell.uplift_rate = tectonic_uplift_scale * tectonic_activity
                 * (1.5·divergence + 8.5·convergence + (crust_type == 3 ? 2.5 : 0.0))
                 * maturation_timestep_scale(params)
```

(`cpp/src/engine/tectonics.cpp:502` and `:1611`). Note that convergence is weighted 5.7× more heavily than divergence, and crust type 3 gets a fixed additive term. Range-checked natively at `cpp/src/engine/core.cpp:424`.

**How changes propagate.** Uplift is the source term that erosion consumes. Raising it builds and sustains mountains against incision; lowering it lets the landscape decay toward base level. It also determines the tectonic elevation change recorded per motion step, which feeds the crust transport and dry-rock accounting ledgers.

**Interactions.** It multiplies the clamped `tectonic_activity` index (from `internal_heat` and `geological_age_ga`) and the boundary forcing fields (from `min_angular_speed`, `max_angular_speed`, `plate_motion_scale_deg_per_step`, and `boundary_smoothing_steps`). Because activity is clamped at 2.25, `tectonic_uplift_scale` is the only *unbounded* uplift lever in the schema — which is why `young_volcanic` uses 2.0 here rather than relying on `internal_heat: 2.50` alone. It balances against `stream_power_coefficient`.

**Tuning.** `0.0` is the stagnant case (`oldstone_stagnant`, paired with zero plate motion) — no new relief is created and erosion monotonically wears the surface down. Low (0.55, `glasswind_desert`; 0.75, `cryogenic_slushball`) gives subdued relief. Default 0.85 is the Earth-like reference. High (1.10–2.0, `verdant_hothouse`, `pelagic_archipelago`, `young_volcanic`) gives dramatic, actively rising mountain belts.

---

## `compute` — execution backend

Model: `ComputeConfig`, `src/magic_geo/config.py`. Section description: "Native execution backend and worker scheduling preferences."

This section is operational: it changes *how* the world is computed, not *what* is generated — with the important exception that thread count currently affects reproducibility.

| Property | Type | Default | Valid range / choices | Description |
| --- | --- | --- | --- | --- |
| `backend` | enum (str) | `"auto"` | `auto`, `cpu`, `opencl`, `cuda` | Requested compute backend; explicit accelerator choices fail if unavailable. |
| `threads` | int | `0` | `[0, 1024]` (`MAX_COMPUTE_THREADS`, `src/magic_geo/config.py`) | CPU worker-thread count; zero asks the runtime to select automatically. |
| `opencl_prefer_gpu` | bool | `true` | `true`, `false` | Prefer a qualifying GPU when selecting among available OpenCL devices. |

### `compute.backend`

**What it is.** The requested execution backend. Declared at `src/magic_geo/config.py` as a four-value `Literal`.

**Where it is consumed.** Mapped to an integer by `COMPUTE_BACKEND_IDS = {"auto": 0, "cpu": 1, "opencl": 2, "cuda": 3}` (`src/magic_geo/native.py:22`) into `NativeConfigV2.compute_backend` (`src/magic_geo/native.py:97`), which maps to `CConfigV2.compute_backend`. `validate_compute_options` rejects anything outside `[0, 3]` with `compute_backend must be auto, cpu, opencl, or cuda` (`cpp/src/engine/core.cpp:233`–`236`). Selection happens in `ComputeSession::Impl` (`cpp/src/opencl_compute.cpp:807`):

| Value | Behaviour |
| --- | --- |
| `cpu` (1) | Immediately selects CPU; CUDA and OpenCL probes are skipped (`cpp/src/opencl_compute.cpp:815`–`819`). |
| `auto` (0) | Selection is **deferred** until the actual mesh size is known, then resolved in `ensure_auto_backend` (`cpp/src/opencl_compute.cpp:952`). |
| `cuda` (3) | Probes and initializes CUDA; on failure throws `explicit CUDA backend requested but initialization failed: …` (`cpp/src/opencl_compute.cpp:835`–`837`). |
| `opencl` (2) | Probes OpenCL; on failure throws `explicit OpenCL backend requested but initialization failed: …` (`cpp/src/opencl_compute.cpp:941`–`944`). |

The `auto` thresholds are evaluated against the **actual generated cell count**, using the constants at `cpp/src/opencl_compute.cpp:99`–`101`:

| Constant | Value | Meaning |
| --- | --- | --- |
| `CUDA_SM_120_AUTO_MIN_CELL_COUNT` | `8192` | Minimum actual cells before an sm_120 CUDA device is auto-selected. |
| `CUDA_UNCALIBRATED_AUTO_MIN_CELL_COUNT` | `32768` | Conservative minimum for a non-sm_120 FP64 CUDA device. |
| `OPENCL_AUTO_MIN_CELL_COUNT` | `32768` | Minimum actual cells before OpenCL is auto-selected. |

Below every applicable threshold, `auto` selects CPU with the reason "automatic acceleration is below the evidence-based actual-mesh thresholds; CUDA/OpenCL probes skipped" (`cpp/src/opencl_compute.cpp:967`–`972`).

**How changes propagate.** It changes performance, and it changes the reported selection reason in the backend telemetry. It does not change the authoritative simulation semantics: the v3 exact spherical crust-overlap transport is CPU-authoritative for every backend, and an active accelerator only computes, validates, reports, and then **discards** a continuous-moment CSR shadow.

**Interactions.** Strongly coupled to `mesh.cell_count`, because the auto thresholds are cell-count thresholds. Also interacts with `threads` (OpenMP still governs the CPU-authoritative work) and with `opencl_prefer_gpu` (device ranking when OpenCL is selected).

**Tuning.** Use `cpu` for reproducible CI and small meshes — the `smoke` profile does. Use `auto` (the default) for general work; it will not silently offload a small mesh. Use `opencl` or `cuda` only when you want a hard failure if the accelerator is unavailable, rather than a silent CPU fallback.

### `compute.threads`

**What it is.** The OpenMP worker-thread count. Declared at `src/magic_geo/config.py`, `[0, 1024]`, `0` meaning "let the runtime decide".

**Where it is consumed.** Through `ScopedThreadConfiguration` (`cpp/src/engine/core.cpp:213`–`223`), constructed at the top of each of the four public generation entry points (`cpp/src/engine.cpp:22`, `:33`, `:44`, `:57`). If `requested_threads > 0` it records `omp_get_max_threads()`, calls `omp_set_num_threads(requested_threads)`, and restores the previous value in the destructor (`cpp/src/engine/core.cpp:225`–`231`). When `_OPENMP` is not defined the argument is discarded. Range-checked at `cpp/src/engine/core.cpp:427`.

**How changes propagate.** It changes wall-clock time on the parallel loops — mesh neighbour search and control-volume construction (`cpp/src/engine/mesh.cpp:792`, `:817`), the per-cell erosion pass (`cpp/src/engine/earth_system.cpp:966`), and other `#pragma omp parallel for` regions. **It also currently changes the output.** This is a known regression, not a design intent: a fixed thread count is bit-stable, but different counts produce different worlds.

**Interactions.** `threads: 0` defers to `OMP_NUM_THREADS` or the OpenMP default, which means the *environment* becomes part of your generation provenance. If you care about reproducibility, pin an explicit non-zero value and record it beside the artifact.

**Tuning.** `1` is the reproducible choice — every shipped seed preset and the `smoke` profile use it. `0` (the default) is the fastest general-purpose choice. Any explicit value between 2 and 1024 pins parallelism deterministically for that count only.

### `compute.opencl_prefer_gpu`

**What it is.** A device-ranking preference. Declared at `src/magic_geo/config.py`, default `true`.

**Where it is consumed.** Marshalled to `NativeConfigV2.opencl_prefer_gpu` as `1`/`0` (`src/magic_geo/native.py:338`), read into `ComputeOptions::opencl_prefer_gpu` and stored as `prefer_gpu` in the compute session (`cpp/src/opencl_compute.cpp:814`), then echoed into the backend telemetry JSON (`cpp/src/opencl_compute.cpp:2325`). The `ComputeOptions` declaration notes it is "Retained for ABI compatibility and OpenCL device ranking" and that automatic mode tries a qualifying native CUDA device before OpenCL (`cpp/include/magic_geo/native.hpp:76`–`77`).

**How changes propagate.** Only through OpenCL device selection ordering. It has no effect when the resolved backend is CPU or native CUDA.

**Interactions.** Meaningful only when `backend` resolves to `opencl`, i.e. either explicitly requested or auto-selected at ≥ 32,768 actual cells with a qualifying non-CPU OpenCL device present.

**Tuning.** Leave it `true` unless you are deliberately benchmarking an OpenCL CPU device against the native CPU path.

---

## `output` — payload shape and numeric formatting

Model: `OutputConfig`, `src/magic_geo/config.py`. Section description: "Payload detail and general floating-point output formatting."

| Property | Type | Default | Valid range / choices | Description |
| --- | --- | --- | --- | --- |
| `include_cells` | bool | `true` | `true`, `false` | Include per-cell state required by enrichers, validation, and the debugger. |
| `float_precision` | int | `4` | `[0, 8]` | General JSON decimal precision; replay-critical fields use higher fixed floors. |

### `output.include_cells`

**What it is.** Whether the per-cell arrays are serialized into the payload. Declared at `src/magic_geo/config.py`, default `true`.

**Where it is consumed.** The low-level native API marshals the flag to `1`/`0` and the native serializer emits `cells: []` when disabled. The public full-world API requests cells internally, completes every enrichment, and clears the cells array at the output boundary when disabled. It does not modify the caller's configuration.

**How changes propagate.** Turning it off shrinks the payload dramatically and leaves only summaries, histories, and models. It also breaks most downstream consumers: `generate_geo_world` raises `generate_geo_world requires output.include_cells=true because natural enrichers and layer validation consume per-cell state` (`src/magic_geo/api.py:295`–`300`), and the debug exporter raises `world payload has no cells; generate with output.include_cells enabled` (`src/magic_geo/debug_export.py:833`).

**Interactions.** Hard requirement for `generate_geo_world` / `magic-geo generate --geo-only`, for `magic-geo export-debug`, for meaningful cell CSV export, and for the layer validators. `generate_world` preserves all other records and summaries exactly when cells are omitted; their cell IDs still require the complete payload for validation and spatial inspection. This option does not reduce enrichment work or its peak memory.

**Tuning.** Keep it `true`. Set it `false` only for a summary-only run where you want the histories and models without the per-cell arrays, and accept that the debugger, geo-only API, and validators are unavailable for that payload.

### `output.float_precision`

**What it is.** The default number of decimal places for general/display floats. Declared at `src/magic_geo/config.py`, `[0, 8]`.

**Where it is consumed.** It is threaded through the serializers as the `precision` argument of `add_double` (`cpp/src/engine/core.cpp:206`) and of the per-collection JSON builders. `params.float_precision` is referenced 165 times in `cpp/src/engine/summary.cpp`, 36 times in `cpp/src/engine/world_serialization.cpp` (which calls no `add_double` directly — it forwards the precision into `plates_json`, `watersheds_json`, `lake_basins_json`, `coastal_features_json`, `ice_sheets_json` and their siblings), and 20 times in `cpp/src/engine/process_serialization.cpp`. Range-checked at `cpp/src/engine/core.cpp:430`. Because the MessagePack path is produced by `json_to_messagepack(serialize_world(...))` (`cpp/src/engine.cpp:46`, `:59`), the same precision governs both `.json` and `.mgeo` outputs.

**How changes propagate.** It trades payload size against display precision for *general* fields only. It is deliberately **not** a global precision control:

| Category | Precision policy |
| --- | --- |
| General/display floats | `output.float_precision` |
| Replay-critical crust, equilibrium, boundary, transport, elevation, water-depth roots | general-format `max_digits10` binary64 round-trip, independent of the config |
| Sediment interface canonical state | 10 decimal places, independent of the config |
| Sediment replay operands | at least 8 decimal places, independent of the config |
| Selected fields with a floor | `max(6, float_precision)` — e.g. the emitted `river_extraction_percentile` at `cpp/src/engine/summary.cpp:1357` and `target_ocean_water_inventory_km3` at `cpp/src/engine/summary.cpp:1626` |

**Interactions.** Because replay-critical roots override it, lowering `float_precision` does **not** break independent replay validation — it only degrades human-facing summary values. Raising it does not improve replay fidelity either, since those fields already round-trip.

**Tuning.** Default 4 is the reference. `0` produces integer-looking display values and the smallest payload. `8` maximizes display precision at the cost of payload size. If you need exact values, read the replay-critical fields, not the general ones.

---

## Cross-field validators

Two validators run after field-level validation and produce distinct error shapes.

| Validator | Location | Condition | Message | Reported path |
| --- | --- | --- | --- | --- |
| `TectonicsConfig.validate_speeds` | `src/magic_geo/config.py` | `max_angular_speed < min_angular_speed` | `max_angular_speed must be >= min_angular_speed` | `tectonics` |
| `WorldConfig.validate_plate_density` | `src/magic_geo/config.py` | `tectonics.plate_count >= mesh.cell_count` | `plate_count must be smaller than mesh.cell_count` | `<root>` |

```console
$ magic-geo init-config --profile default \
    --set mesh.cell_count=200 --set tectonics.plate_count=200 -o /tmp/x.yaml
Invalid value: <overrides>: configuration validation failed:
  - <root>: Value error, plate_count must be smaller than mesh.cell_count
```

The native engine repeats both checks independently, but with its own message wording: angular speeds at `cpp/src/engine/core.cpp:363`–`372`, which throws the single combined string `angular speeds must be between 0 and 100 and max_angular_speed must be >= min_angular_speed`; plate count against the requested cell count at `cpp/src/engine/core.cpp:294`–`301` (`plate_count must be between 2 and 256 and smaller than cell_count`); and plate count against the **generated** mesh size at `cpp/src/engine/pipeline.cpp:13` (`plate_count must be smaller than generated mesh cell count`). The second native check matters on the geodesic backend, where the realized cell count differs from the requested one.

---

## The profile system

Profiles are explicit **starting points**, not hidden defaults applied by the loader. They are defined by two parallel dictionaries, `_PROFILE_DESCRIPTIONS` (`src/magic_geo/config.py`) and `_PROFILE_OVERRIDES` (`src/magic_geo/config.py`), and enumerated in stable order by `list_config_profiles()` (`src/magic_geo/config.py`), which returns `("default", "earthlike", "smoke")`.

`create_config(profile, overrides)` (`src/magic_geo/config.py`) builds a bare `WorldConfig()`, applies the profile's dotted overrides with `source=f"<profile:{name}>"`, then applies the caller's overrides with the default `source="<overrides>"`. An unknown name raises:

```text
<profile>: unknown configuration profile 'nope'; choose one of: default, earthlike, smoke
```

### Profile diff table

Only fields that differ from the schema defaults are listed; every other field takes its `WorldConfig` default.

| Property | Schema default | `default` | `earthlike` | `smoke` |
| --- | --- | --- | --- | --- |
| `run.name` | `earthlike_mvp` | `earthlike_mvp` | `earthlike_mvp` | **`smoke`** |
| `mesh.cell_count` | `4096` | `4096` | `4096` | **`128`** |
| `tectonics.plate_count` | `14` | `14` | `14` | **`8`** |
| `tectonics.plate_motion_scale_deg_per_step` | `2.0` | `2.0` | **`4.0`** | **`4.0`** |
| `climate.precipitation_scale` | `1.0` | `1.0` | **`0.8`** | **`0.8`** |
| `erosion.iterations` | `6` | `6` | `6` | **`1`** |
| `compute.backend` | `auto` | `auto` | `auto` | **`cpu`** |
| `compute.threads` | `0` | `0` | `0` | **`1`** |

| Profile | Description string (`src/magic_geo/config.py`) | Override count |
| --- | --- | --- |
| `default` | "Prescribed seasonal energy model with neutral physical inputs." | 0 |
| `earthlike` | "4,096-cell Earth reference inputs for the seasonal model; new climate calibration is not established." | 2 |
| `smoke` | "Small deterministic CPU seasonal configuration for integration checks." | 8 |

### Profile facts worth knowing

- **Every YAML document requires `config_version: 2`.** Empty or unversioned documents are rejected; `WorldConfig()` and `create_config()` deliberately create new version-2 inputs.
- **`magic-geo init-config` defaults to `--profile earthlike`** (`src/magic_geo/cli/commands/config.py:28`), while the Python `create_config()` defaults to `"default"` (`src/magic_geo/config.py`). The web UI also reports `earthlike` as its default (`src/magic_geo/debug_server.py:965`).
- **`configs/earthlike_seed.yaml` is exactly the `earthlike` profile**, materialized with all 43 section fields and the version spelled out.
- **`configs/seeds/*.yaml` are data files, not registered profiles.** The nine presets (`continental_realm`, `cryogenic_slushball`, `glasswind_desert`, `ironroot_super_earth`, `oldstone_stagnant`, `pelagic_archipelago`, `solstice_extreme`, `verdant_hothouse`, `young_volcanic`) cannot be named with `--profile`; pass them with `--config`.
- **Materialize, do not reference.** A profile name is not generation provenance; treat a later profile revision as a new input and save the complete YAML beside the artifacts.

```bash
# List profile names from Python
python -c "from magic_geo import list_config_profiles; print(list_config_profiles())"
# ('default', 'earthlike', 'smoke')

# Materialize each one
magic-geo init-config --profile default   --output runs/configs/neutral.yaml
magic-geo init-config --profile earthlike --output runs/configs/earth.yaml
magic-geo init-config --profile smoke     --output runs/configs/smoke.yaml
```

---

## The `--set` override syntax

`--set` is exposed on exactly one command, `magic-geo init-config` (`src/magic_geo/cli/commands/config.py:32`). It is repeatable and its values are parsed by `parse_config_overrides` (`src/magic_geo/config.py`), then applied by `apply_config_overrides` (`src/magic_geo/config.py`) through `create_config`.

```bash
magic-geo init-config \
  --profile earthlike \
  --set run.name='large ocean world' \
  --set mesh.cell_count=8192 \
  --set mesh.backend=geodesic_icosahedron \
  --set planet.ocean_water_inventory_km3=1800000000 \
  --set hydrology.preserve_geologic_depressions=false \
  --set compute.backend=cpu \
  --set compute.threads=1 \
  --output runs/configs/ocean.yaml
```

### Grammar

| Rule | Behaviour | Source |
| --- | --- | --- |
| Form | `section.field=YAML_VALUE` | `src/magic_geo/config.py` |
| Split | on the **first** `=` only, so values may contain `=` | `assignment.split("=", 1)`, `src/magic_geo/config.py` |
| Path whitespace | stripped | `path.strip()`, `src/magic_geo/config.py` |
| Value whitespace | **not** stripped — passed verbatim to YAML | `src/magic_geo/config.py` |
| Depth | traversal supports arbitrary depth, but the schema is exactly two levels, so every valid path is `section.field` | `src/magic_geo/config.py` |
| Ordering | insertion order is preserved and applied in that order | `dict` in `src/magic_geo/config.py`, iteration at `:723` |
| Mutation | each value is `deepcopy`d; the input model and caller mapping are never mutated | `src/magic_geo/config.py` |
| Revalidation | the entire document is re-validated after all overrides, so cross-field constraints still apply | `_validate_config_data`, `src/magic_geo/config.py` |

### Type coercion rules

The value is passed to `yaml.safe_load`, so YAML scalar rules apply exactly:

| Written | Parsed as | Python type |
| --- | --- | --- |
| `128` | `128` | `int` |
| `0.8` | `0.8` | `float` |
| `1.0e+9` | `1000000000.0` | `float` |
| `1e9` | `"1e9"` | `str` — PyYAML's YAML 1.1 float resolver needs both a decimal point and a signed exponent, so `1e9`, `1.0e9`, and `1e+9` all stay strings (strict numeric fields reject these strings) |
| `true` / `false` | `True` / `False` | `bool` |
| `geodesic_icosahedron` | `"geodesic_icosahedron"` | `str` |
| `'large ocean world'` | `"large ocean world"` | `str` |
| `"128"` | `"128"` | `str` (quoted, so not an int) |
| `null` or an empty value | `None` | `NoneType` |
| `[a, b]` | `["a", "b"]` | `list` |
| `{k: v}` | `{"k": "v"}` | `dict` |

Strict validation rejects numeric strings, floats for integer fields and booleans for numeric fields. An integer is accepted for a float field. Shell quotes delimit arguments and are not retained automatically: to actually test a YAML numeric string, include literal quotes in the value. YAML 1.1 still parses `yes` as boolean `True`; prefer canonical `true` / `false`.

### Error cases

`parse_config_overrides` errors, all `ConfigError` with `source="<override>"` (except where noted):

| Trigger | Message |
| --- | --- |
| Non-string item, or no `=` present | `override 'mesh.cell_count' must use section.field=value` |
| Empty path after strip (e.g. `=5`) | `override path cannot be empty` |
| Same path given twice | `duplicate configuration override 'mesh.cell_count'` |
| Value fails the YAML complexity pre-pass | the underlying `ConfigError` is re-raised unchanged, with `source="<override:{path}>"` |
| Value fails `yaml.safe_load` | `<override:mesh.cell_count>:1:4: invalid YAML: expected the node content, but found '<stream end>'` (real output for `mesh.cell_count=[1,`) |

`apply_config_overrides` errors, all `ConfigError` with the caller's `source` (default `"<overrides>"`):

| Trigger | Message |
| --- | --- |
| Non-string key | `override paths must be strings` |
| Fewer than two dotted parts (`seed`, `mesh`) or any empty part (`a.`, `.b`, `a..b`) | `override path 'seed' must identify a dotted field` |
| An intermediate part is missing or is not a mapping | `unknown configuration override 'nope.x'` |
| The leaf does not exist | `unknown configuration override 'mesh.nope'` |
| The leaf resolves to a nested mapping | `unknown configuration override '<path>'` (defensive; unreachable in the current two-level schema, where whole-section paths are caught by the dotted-field rule first) |

Every one of these makes the CLI exit with status 2 via `typer.BadParameter` (`src/magic_geo/cli/commands/config.py:47`–`48`).

### Programmatic equivalent

```python
from magic_geo import apply_config_overrides, create_config, parse_config_overrides

overrides = parse_config_overrides([
    "mesh.cell_count=512",
    "hydrology.preserve_geologic_depressions=false",
])
config = create_config("smoke", overrides)

# Returns a new validated model; `config` is unchanged.
variant = apply_config_overrides(
    config,
    {"planet.axial_tilt_deg": 40.0},
    source="experiment overrides",
)
```

---

## YAML strictness and complexity limits

`parse_config_yaml(text, *, source="<string>")` (`src/magic_geo/config.py`) runs a fixed five-stage pipeline. Every failure is a `ConfigError` (a `ValueError` subclass, `src/magic_geo/config.py`) whose `str()` is `"{source}[:{line}[:{column}]]: {message}"` and whose `.to_dict()` (`src/magic_geo/config.py`) is JSON-safe.

### Stage 1 — UTF-8 well-formedness

`text.encode("utf-8")` inside `_check_yaml_complexity` (`src/magic_geo/config.py`). A `UnicodeEncodeError` becomes `YAML text must be well-formed UTF-8 Unicode`.

### Stage 2 — complexity pre-pass

`_check_yaml_complexity` (`src/magic_geo/config.py`) streams `yaml.parse` **events** before any object is constructed, so a malicious document is rejected before it can allocate. The three numeric limits are module constants:

| Limit | Constant | Value | Message on violation | Source |
| --- | --- | --- | --- | --- |
| Total parse events | `MAX_YAML_EVENTS` | `20000` | `YAML exceeds the 20000 event complexity limit` | `src/magic_geo/config.py`, check at `:570` |
| Collection nesting depth | `MAX_YAML_NESTING_DEPTH` | `64` | `YAML nesting exceeds the 64-level limit` | `src/magic_geo/config.py`, check at `:577` |
| Alias references | `MAX_YAML_ALIASES` | `64` | `YAML exceeds the 64 alias limit` | `src/magic_geo/config.py`, check at `:586` |

The alias cap is the billion-laughs defence. A `yaml.MarkedYAMLError` here becomes `invalid YAML: {problem}` with **one-based** `line = mark.line + 1` and `column = mark.column + 1` (`src/magic_geo/config.py`); `yaml.YAMLError`, `RecursionError`, `MemoryError`, `ValueError`, and `OverflowError` become `invalid or excessively complex YAML: {exc}` (`src/magic_geo/config.py`). Because this pass emits events only, duplicate keys are **not** detected here.

There is **no byte-size cap on the YAML text in `config.py` itself**. The 1,000,000-byte cap is imposed only by the web workbench (`_MAX_CONFIG_BYTES`, `src/magic_geo/debug_server.py:45`, enforced in `_check_web_yaml_size` at `:861` with HTTP 413). File and Python paths are bounded only indirectly, by the 20,000-event limit.

### Stage 3 — strict loading

Loading uses `_UniqueKeySafeLoader` (`src/magic_geo/config.py`), a `yaml.SafeLoader` subclass whose default mapping constructor is replaced by `_construct_unique_mapping` (`src/magic_geo/config.py`, registered at `:118`):

| Condition | Raised as | Surfaces as |
| --- | --- | --- |
| Duplicate mapping key | `ConstructorError("while constructing a mapping", …, f"found duplicate key {key!r}")` (`src/magic_geo/config.py`) | `w.yaml:3:3: invalid YAML: found duplicate key 'seed'` |
| Unhashable key (a list or mapping used as a key) | `ConstructorError(… "found an unhashable mapping key")` (`src/magic_geo/config.py`) | `invalid YAML: found an unhashable mapping key` |
| Arbitrary Python object tags | blocked by the `SafeLoader` base | `invalid YAML: …` |

PyYAML's default last-wins duplicate-key behaviour is deliberately disabled. Both constructor errors are `MarkedYAMLError`s, so they carry one-based line/column.

```python
>>> from magic_geo import parse_config_yaml, ConfigError
>>> try:
...     parse_config_yaml("run:\n  seed: 1\n  seed: 2\n", source="world.yaml")
... except ConfigError as error:
...     print(error.to_dict())
{'message': "invalid YAML: found duplicate key 'seed'", 'source': 'world.yaml',
 'issues': [], 'line': 3, 'column': 3}
```

### Stage 4 — root shape

`None` (an empty document) becomes `{}` and then fails the required-version check (`src/magic_geo/config.py`). A non-mapping root is rejected with `config root must be a YAML mapping` and a single structured issue `{"path": "<root>", "location": [], "message": "config root must be a YAML mapping", "type": "mapping_type"}` (`src/magic_geo/config.py`).

### Stage 5 — model validation

`_validate_config_data` first requires `config_version`, then calls `WorldConfig.model_validate(..., strict=True)` (`src/magic_geo/config.py`). A pydantic `ValidationError` is reshaped by `_config_validation_error` (`src/magic_geo/config.py`) using `exc.errors(include_url=False, include_context=False, include_input=False)`. The message is `configuration validation failed:` followed by one `  - {path}: {msg}` line per issue, and `.issues` carries `{path, location, message, type}` per issue with `path` dotted or `<root>`.

| Rejection | Cause | Example message |
| --- | --- | --- |
| Unknown property | `extra="forbid"` on every model | `mesh.bogus: Extra inputs are not permitted` |
| Non-finite float | `allow_inf_nan=False` on every model | `planet.radius_km: Input should be a finite number` |
| Out-of-range value | `Field` bound | `mesh.cell_count: Input should be greater than or equal to 128` |
| Cross-section constraint | `WorldConfig.validate_plate_density` | `<root>: Value error, plate_count must be smaller than mesh.cell_count` |
| Intra-section constraint | `TectonicsConfig.validate_speeds` | `tectonics: Value error, max_angular_speed must be >= min_angular_speed` |

### `load_config` exception contract

`load_config` (`src/magic_geo/config.py`) calls `Path(path).read_text(encoding="utf-8")` and deliberately **does not** wrap it. `FileNotFoundError`, `PermissionError`, `IsADirectoryError`, and `UnicodeDecodeError` propagate untouched (documented at `src/magic_geo/config.py`). `ConfigError` is reserved for YAML-syntax and model-validation failures that occur after bytes were successfully read. The error `source` is the stringified path, so CLI and web clients get file-anchored `path:line:column` diagnostics.

### `dump_config_yaml`

`dump_config_yaml` (`src/magic_geo/config.py`) is `yaml.safe_dump(config.model_dump(mode="python"), allow_unicode=True, default_flow_style=False, sort_keys=False, width=100)`. Consequences: schema section and field order is preserved (not alphabetized), output is block style, Unicode is emitted literally rather than escaped, lines wrap at 100 columns, no anchors or aliases are produced, and comments from the input file are **not** preserved.

---

## JSON Schema export

`config_schema()` returns the current model schema with `$id` `urn:magic-geo:schema:world-config:v2` and `x-magic-geo.schema_version: 2`. Its `required` array includes `config_version`, whose property is integer `const: 2`. Nine section properties reference `Seasonal*Config` definitions through `$ref`; sibling descriptions must also be preserved. The root version is a scalar, not a section model. `x-magic-geo.section_order` includes all declared root fields, and `profiles` carries the complete current values for each profile.

```python
from magic_geo import config_schema

schema = config_schema()
assert schema['properties']['config_version']['const'] == 2
mesh_ref = schema['properties']['mesh']['$ref'].split('/')[-1]
print(schema['$defs'][mesh_ref]['properties']['cell_count'])
```

Fields retain descriptions, defaults, numeric bounds and enum/const declarations. API clients should follow `$ref` and use the schema instead of hard-coding the section definition names. The workbench serves this document at `GET /api/config/schema`, uses version-2 templates and validates saved YAML through the same strict parser. Server validation is authoritative.

---

## Atomic validated writes

`write_config(path, config, *, force=False)` (`src/magic_geo/config.py`) is the only supported way to publish a config file. Its steps:

| Step | Action | Source |
| --- | --- | --- |
| 1 | Early guard: if the target exists and `force` is false, raise `FileExistsError(f"{target} already exists; pass --force to overwrite")` | `src/magic_geo/config.py` |
| 2 | `target.parent.mkdir(parents=True, exist_ok=True)` | `:806` |
| 3 | Create a temp file **in the same directory** named `.{target.name}.{uuid4().hex}.tmp` — hidden, collision-free, and on the same filesystem so link/replace stay atomic | `:807` |
| 4 | Write `dump_config_yaml(config)` as UTF-8 | `:809` |
| 5 | **Read the temp file back and re-parse it** with `parse_config_yaml(..., source=str(temporary))` — validating exactly the bytes that will be committed, not the in-memory model | `:811` |
| 6a | `force=True`: `os.replace(temporary, target)` — atomic overwrite | `:812`–`813` |
| 6b | `force=False`: `os.link(temporary, target)` — atomic same-directory hard-link create that **fails if a concurrent writer created the target after step 1**; the `FileExistsError` is re-raised with the same message, then the temp is unlinked | `:815`–`823` |
| 7 | `finally`: unlink the temp file if it still exists — no debris on any error path (a no-op after a successful `replace`, which consumes it) | `:824`–`826` |

Net guarantees: readers never observe a partial or invalid file; a no-force write cannot clobber a racing creator; and a file that fails its own read-back validation is never published. It does **not** promise power-loss durability, because it does not fsync the file or the parent directory.

```python
from pathlib import Path
from magic_geo import create_config, write_config

write_config(Path("runs/configs/world.yaml"), create_config("earthlike"))
write_config(Path("runs/configs/world.yaml"), create_config("smoke"), force=True)
```

The web workbench layers additional path constraints on top of `write_config` at `POST /api/config/save` (`src/magic_geo/debug_server.py:1007`): the name must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` and not be `.` or `..` (`src/magic_geo/debug_server.py:46`, `:1010`), otherwise HTTP 422; a `.yaml` suffix is appended unless the name already ends in `.yaml` or `.yml`; the target directory must be `<workspace>/configs`, neither the directory nor the target file may be a symlink, and both must resolve inside the workspace; and an existing name without `force: true` returns HTTP 409.

---

## Config-to-native mapping

`config_to_native(config)` preserves the version and all named values in a JSON-compatible model mapping. The API selects V4 for current `WorldConfig` / `SeasonalWorldConfig`; the low-level native entry points also dispatch any mapping containing `config_version` through strict seasonal validation. No obsolete Celsius value is converted to opacity.

`_native_seasonal_config` revalidates the input before constructing the standalone `NativeConfigV4`. It carries 43 fields, with fixed-width `c_int32` integral controls, `c_uint64` seed, UTF-8 name and binary64 floating controls. `config_version` selects the document contract and is not a C struct field. Booleans become exactly 0 or 1; backend enums retain their declared IDs. The [ABI migration record](../seasonal_climate_migration_plan.md#implemented-standalone-v4-layout) lists every field and checked offset. On the tested 64-bit ABI V4 has size 312 and alignment 8; coincident size with V2 does not imply compatible layout.

The seasonal loader requires all four full/geography JSON/MessagePack V4 symbols. A missing symbol produces a rebuild error; it does not downgrade to V3. `serialization="auto"` selects MessagePack. Each buffer is freed with its matching native free function, including decoding and validation failures.

Before returning, Python checks the world schema, planet snapshot, exact seasonal model identities, retained forcing/edge/cell budget arrays and configured physical inputs. It then independently audits native radiation, coefficients, transport, storage and balance. Full internal cell data remains present until dependent enrichers finish; final output omission happens afterward. Annual energy enrichment preserves solved temperatures and the certificate. This audit does not reconstruct unexported solver trajectories or independently derive the orbital nodes and geometric edges.

`LegacyWorldConfig` is an explicit Python compatibility type. Old CConfig/V2/V3 layouts remain unchanged at the tested 304/312/320 bytes, and old adapters explicitly select their original temperature model. Unversioned YAML is rejected; file loading never selects this compatibility path.

---

## Other configuration surfaces that are not generation config

These files configure analysis commands. They are **not** `WorldConfig` documents and they produce no layers.

| Surface | Files | Loaded by | Purpose |
| --- | --- | --- | --- |
| Geo-validation matrix | `configs/geo_validation_matrix.yaml` | `magic-geo validate-geo-suite --matrix` (option declared at `src/magic_geo/cli/commands/validate_geo.py:100`, default at `:105`, loaded by `load_geo_validation_manifest` at `:118`) | Scenario list with a `profile` name plus **nested** section/field `overrides` (not dotted paths) and expectation bands. |
| Empirical targets | `configs/geo_validation_earth_empirical_targets.json` | the same suite | Earth-tuned physical-plausibility target bands. |
| Calibration sources | `configs/calibration_sources.*.json` (ETOPO 2022, WorldClim 2.1, HydroBASINS L3, HydroRIVERS v1.0, Natural Earth 110m, Seton 2020 oceanic age) | `magic-geo calibrate` | Point at real-world datasets. |
| Calibration ensemble | `configs/calibration_ensemble.r1.json` | `magic-geo calibrate-ensemble` (command at `src/magic_geo/cli/commands/calibrate.py:94`, manifest loaded at `:144`) | Defines a seed/resolution sweep on top of a base `WorldConfig`. |
| Calibration targets | `configs/calibration_targets.seton_2020_oceanic_age.json` | `magic-geo calibrate` | Repository-derived targets from a checksum-pinned grid — validation evidence, not generation input. |

Note the differing override syntax: the CLI `--set` and the Python helpers use **dotted** paths (`mesh.cell_count`), while the geo-validation matrix uses **nested** mappings:

```yaml
# configs/geo_validation_matrix.yaml — nested, not dotted
- id: earthlike_pair
  profile: earthlike
  overrides:
    mesh:
      cell_count: 512
    tectonics:
      plate_count: 10
    erosion:
      iterations: 3
```

The CLI also exposes one ad-hoc generation override outside the config file: `magic-geo generate --cells N` (min 128) mutates `mesh.cell_count` on the dumped model and re-validates the whole document (`src/magic_geo/cli/commands/generate.py:28`, applied at `:49`–`52`).

---

## Limitations and unresolved claims

These carry forward the repository's own explicit hedges. Do not upgrade them.

- **Determinism is not guaranteed across thread counts.** Output currently varies with `compute.threads` and `OMP_NUM_THREADS`. A fixed thread count is bit-stable; different counts differ. `run.seed` alone is therefore **not** sufficient generation provenance.
- **The maturation clock is nominal, not calibrated physical time.** `erosion.maturation_timestep_ma` refines continuous reference-step mutations and the histories carry interval coordinates, but the coefficients are procedural reference-step responses rather than a dimensioned landscape-evolution system. The payload keeps `physical_time_resolved: false`.
- **Plate speeds are indices, not velocities.** `min_angular_speed`, `max_angular_speed`, and `plate_motion_scale_deg_per_step` are heuristic kinematic scales. The km/Ma labels emitted by the plate boundary segment ledger are nominal, and plate-speed calibration remains false.
- **Subduction polarity is explicitly unknown.** The boundary segment ledger supplies only *candidate* subducting/overriding sides where convergence is active; physical sides remain unknown with source `none` and confidence zero. Physical polarity, slab geometry/selection/transfer, and material fate remain false.
- **Crust material provenance is a non-authoritative shadow audit.** `crust_material_shadow_model` is always emitted and has **no configuration switch** because it is audit evidence, not a physical model. Cell-state authority, physical source/sink resolution, solid volume, phase, mass-weighted age, upper mantle, subducted slab, and global crust-cycle conservation are all explicitly false. Tuning tectonic activity changes the unresolved adjustment record; it does not turn the audit into provenance.
- **Finite dry-rock accounting is a numerical counter-model.** `crust_dry_rock_accounting_model` is always emitted and has no configuration switch. Its `76 km × 3.08 g/cm³` capacity is an uncalibrated numerical surface-state envelope, not an estimate of upper-mantle mass; every transfer declares `physical_basis_resolved: false`; slab tables remain empty. Its packet/transfer limits are memory-safety limits, not physical flux limits.
- **Accelerator parity is incomplete.** The v3 exact spherical crust-overlap transport is CPU-authoritative for every value of `compute.backend`. An active accelerator computes, validates, reports, and then **discards** a continuous-moment CSR shadow. Device execution on this host, spherical geometry, coverage/classes, categories, production state, and complete accelerator parity remain pending.
- **Per-cell sediment source partitions are audit depths.** Both `source_partition_audit_is_mass_claim` and `source_partition_audit_is_provenance_claim` remain false. The sediment interface is a geometric interface only; dry-rock mass, sediment density, porosity, compaction, grain provenance, and chemical weathering are unresolved.
- **`ocean_fraction_target` does not drive anything.** It is a diagnostic reference. It is also not a supported shelf-area control: at 4,096 cells an equivalent-area cell is roughly 400 km across, so a single cell's elevation cannot represent land, shelf, slope, and deep ocean separately. Conservative subcell hypsometry is planned but not implemented.
- **Non-Earth planets are lightly validated.** The schema permits extreme planets, and planet-scaling tests confirm the knobs move outputs, but the geo-validation target bands are Earth-tuned. Exotic configurations are valid, not asserted physically plausible.
- **Enricher parameters are not configurable.** The Python enrichers that produce the majority of the layer catalogue (439 layers in the checked-in 4,096-cell full-scope reference — soils, biomes, groundwater, resources, reefs, human geography) run with fixed internal constants. Only the physical drivers in `planet`, `mesh`, `tectonics`, `climate`, `hydrology`, and `erosion` are exposed. Changing a biome threshold means editing the module.
- **No subsystem enable/disable switches.** Every enricher always runs when cells are present. `erosion.iterations: 0` is the only coarse off-switch, and `--geo-only` (which strips civilization layers) is a CLI/API flag, not a config property.
- **Per-field behavioural evidence is not reported.** `config_to_native` marshals every current field into the versioned structs, but there is no per-field runtime evidence report proving which downstream model changed. A valid knob with no material effect would require tests or output comparison to detect.
- **Defaults and bounds are duplicated across three languages.** `PlanetConfig`, `PLANET_PARAMETER_DEFAULTS`, and `magic_geo::Params` each encode the same twelve planet defaults independently, and every pydantic bound is re-implemented in `validate_params`. They must be kept in sync by hand.
- **`write_config` is atomic, not durable.** It guarantees readers never see a partial file, but it does not fsync the file or the parent directory, so it makes no power-loss durability promise.

---

## See also

- [Quickstart](./03-quickstart.md) — the shortest path from `init-config` to a generated world.
- [CLI Reference](./06-cli-reference.md) — full flag surface for `init-config`, `generate`, `validate-geo`, and `calibrate`.
- [Python API](./07-python-api.md) — `create_config`, `apply_config_overrides`, `parse_config_yaml`, `write_config`, `config_schema`.
- [Architecture](./04-architecture.md) — how the nine sections map onto the generation pipeline.
- [Native Engine (C++ Core)](./08-native-engine.md) — `Params`, `CConfigV1/V2/V3`, and `validate_params`.
- [Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md) — the `compute` section's selection policy and thresholds.
- [Example Seeds and Presets](./20-seed-gallery.md) — the nine `configs/seeds/*.yaml` worlds and their parameter rationales.
- [Validation](./12-validation.md) and [Geo Validation Suite](./13-geo-validation-suite.md) — the matrix and target-band files.
- [Calibration Against Real-Earth Data](./14-calibration.md) — the `configs/calibration_*.json` surfaces.
- [Web Workbench](./15-web-workbench.md) — the `/api/config/*` endpoints and the browser YAML editor.
- [Mesh and Geometry](./features/mesh-and-geometry.md) — what `mesh.backend`, `cell_count`, and `neighbor_count` actually build.
- [Tectonics and Plates](./features/tectonics-and-plates.md) — the consumers of the `tectonics` section.
- [Climate and Atmosphere](./features/climate-and-atmosphere.md) — the consumers of `climate` and the `planet` forcing terms.
- [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) — `river_percentile` and depression policy in context.
- [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) — the `erosion` loop in detail.
- [Oceans, Currents and Coasts](./features/oceans-and-coasts.md) — the connected-ocean sea-level solve driven by `ocean_water_inventory_km3`.
- [Glossary](./21-glossary.md) and [Troubleshooting and FAQ](./22-troubleshooting.md).
