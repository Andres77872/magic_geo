# Configuration Reference — every generation property, deep

Companion to [layers_reference.md](layers_reference.md) and the
[YAML/helper API guide](configuration_helpers.md). This documents every
property that shapes a generated world: what it controls, its type, default,
valid range, which layers/subsystems it moves, and its status/gaps.

The generation config is a single validated schema — `WorldConfig` in
[config.py](../src/magic_geo/config.py) — loaded from a YAML file
(`magic-geo generate --config <file>`). Every value below is verified against
that schema; ranges are the pydantic `Field` bounds, so anything outside them is
rejected at load time (`extra="forbid"` also rejects unknown keys,
`allow_inf_nan=False` rejects `inf`/`nan`, and the YAML loader rejects duplicate
mapping keys). All sections and fields have defaults, so even `{}` is valid;
omitted values come from the neutral schema defaults, not from the Earth-like
file. Generate the curated Earth-like starter with
`magic-geo init-config --profile earthlike`; the checked-in reference is
[configs/earthlike_seed.yaml](../configs/earthlike_seed.yaml). Nine
complete exploratory presets and their research/selection guidance are indexed
in the [example seed gallery](example_seed_gallery.md).

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
| `name` | str | `earthlike_mvp` | 1–256 Unicode characters; well-formed UTF-8, ≤1024 bytes, no NUL | World name, echoed into the payload and the debugger's world-info header. The encoding constraints preserve it exactly across the native C ABI. | Metadata only. |

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
| `ocean_fraction_target` | float | `0.70` | `[0, 0.95]` | Diagnostic area reference only. It does **not** drive the sea-level solve. | validation, ocean diagnostics |
| `ocean_water_inventory_km3` | float | `1.338e9` | `[0, 1e10]` | Ocean water volume used by the connected cell-column sea-level solve. It is not a closed total-water inventory across ice, lakes, groundwater, soil, and atmosphere. | ocean, water_budget |
| `internal_heat` | float | `1.0` | `[0, 100]` | Internal heat flow relative to Earth. Scales tectonic vigour and volcanic/geothermal potential. | tectonics, resources |
| `geological_age_ga` | float | `4.5` | `[0.01, 100]` | Planet age in billions of years. Sets crust-age ceilings and maturity of geologic systems. | tectonics, resources |

The water-inventory solve floods one scalar elevation per control volume. At the
4,096-cell Earth reference, an equivalent-area cell is roughly 400 km across;
lowering a whole coastal cell to add continental-shelf area would therefore
replace its unresolved land, shelf, slope, and deep-ocean portions with one
elevation. That is not a supported tuning interpretation of either ocean
parameter. The planned remedy is conservative subcell hypsometry: per-cell
area–elevation distributions plus margin shelf–slope–rise profiles, fractional
flooding/volume, and subcell narrow-channel connectivity. See
[Goswami et al. (2015)](https://doi.org/10.5194/gmd-8-2735-2015) for a relevant
bathymetric reconstruction architecture.

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
| `cell_count` | int | `4096` | `[128, 200000]` | Requested spatial resolution. The canonical Earth validation reference (and the shipped `configs/earthlike_seed.yaml`) uses 4,096 cells. A geodesic mesh rounds the request to a realizable `10·frequency²+2` vertex count. | Everything (resolution) |
| `neighbor_count` | int | `7` | `[4, 16]` | Target degree of the Fibonacci process-stencil graph used by climate, hydrology, and sediment operators. It does not change the exact spherical Voronoi control-volume topology. The geodesic backend derives its process stencil from primal triangle edges. | hydrology, sediment |

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
| `min_angular_speed` | float | `0.03` | `[0, 100]` | Lower bound on the procedural intrinsic plate angular-speed index (must be `≤ max`). It contributes to boundary activity but is not calibrated in degrees/Myr. | tectonics |
| `max_angular_speed` | float | `0.95` | `[0, 100]` | Upper bound on the procedural intrinsic plate angular-speed index. It sets peak proxy convergence/divergence and uplift forcing but is not a physical plate-rate bound. | tectonics, geomorphology |
| `boundary_smoothing_steps` | int | `5` | `[0, 32]` | Smoothing iterations on plate boundaries. Higher = cleaner, less crenulated boundaries. | tectonics |
| `plate_motion_scale_deg_per_step` | float | `2.0` | `[0, 10]` | Plate displacement multiplier at the 5 Ma reference step. The applied displacement is scaled by `erosion.maturation_timestep_ma / 5`; the exact segment ledger also uses `radius_km * value * pi/180 / 5 Ma` to label nominal km/Ma velocities. Both remain heuristic kinematic scales, not calibrated angular velocities or physical speeds. | tectonics |
| `oceanic_crust_aging_ma_per_step` | float | `5.0` | `[0, 50]` | Quiet-oceanic-crust age increment at the 5 Ma reference step. The applied increment is scaled by `erosion.maturation_timestep_ma / 5`. | tectonics |

The always-emitted `initial_oceanic_crust_age_model` is a fixed procedural
contract, not another tunable parameter. Positive-rate direct divergent
segments whose provisional sides are both oceanic-like seed both endpoint cells
at zero age. The implementation computes one segment-length-weighted nominal
full spreading rate, halves it, and runs deterministic multi-source Dijkstra on
great-circle edge lengths over the oceanic-like neighbor graph. Reachable ages
are graph travel time clamped to the procedural ceiling; an oceanic component
without an active-ridge path receives that ceiling with an explicit unresolved
status. The round-trip `initial_oceanic_crust_age_ledger` contains exact and
unclamped ages, status, predecessor, origin seed, eligible segments, ridge seeds,
rate operands, area-weighted summaries, and inclusive CDF values at 20 Ma
increments through 200 Ma. The identity-overlap initial checkpoint at
`plate_motion_history[0].crust_overlap_ledger.remapped_crust_age_ma_by_cell`
carries all-cell initial crust age and matches this ledger on oceanic-like
cells. One global nominal rate, graph adjacency in place of flowlines, and
missing convergence/subduction and crust-creation/destruction history mean this
is not a physical seafloor-age reconstruction.

The always-emitted `oceanic_age_depth_model` is also fixed. For oceanic-like
states its relative subsidence target is `-350 sqrt(age_ma)` m through 70 Ma,
then `-[350 sqrt(70) + 3200(exp(-70/62.8) -
exp(-age_ma/62.8))]` m. The old branch uses the Parsons–Sclater exponential shape
but is offset at the 70 Ma switch to enforce value continuity; derivative
continuity and the paper's absolute-depth datum are not claimed. Every plate
snapshot records old/new local isostatic equilibria, old/new thermal targets,
their full gain-1 differences, unbounded and bounded dynamic relief, and total
tectonic elevation change. Isostatic and thermal equilibrium changes are applied
outside the clamp; only the dynamic-relief term is clamped to `[-180, 220]` m.
`thermal_equilibrium_change_m` is the sole serialized thermal-change array, and
the total is exactly
`isostatic_equilibrium_change_m + thermal_equilibrium_change_m +
bounded_dynamic_relief_change_m`. Independent replay verifies every operand,
the dynamic formula/clamp, application, total composition, and zero unapplied
equilibrium residual. Three-to-four-kiloyear viscoelastic relaxation estimates
from [O'Connell (1971)](https://doi.org/10.1111/j.1365-246X.1971.tb01823.x)
motivate treating equilibrium changes as quasi-static relative to the nominal
5 Ma reference step, but neither the step nor the operator is calibrated
physical time. A separate realized thermal-relief state, absolute basement
depth, sediment loading, thermal structure/heat flow, dynamic topography,
flexure, and physical dynamics remain unresolved.

The always-emitted `plate_boundary_segment_model` is not another configuration
switch. For each `plate_motion_history` snapshot it selects every cross-plate
reciprocal control-volume segment, keeps distinct physical segments even when a
geodesic cell pair shares more than one, assigns the lower cell ID as the left
side, and orients the record along that cell's counter-clockwise edge. Strict
validation independently replays high-precision plate-center evolution,
nearest-center assignments, Euler axes/speeds, reciprocal geometry, nominal
rates, intrinsic strengths and classes, and the same-step remapped pre-process
crust state on both sides. A remapped cell with both zero age and zero thickness
has no available opening crust volume; its categorical/density fallback must not
be interpreted as matter. Thresholded normal convergence is independent of the
dominant boundary class, so oblique transform-dominant segments can remain
candidate-eligible. The oceanic-like predicate supplies only candidate
subducting/overriding sides where convergence is active. Physical sides remain
explicitly unknown, with source `none` and confidence zero; GPGIM left/right
input would name the overriding side, but its feature direction must first be
aligned to the canonical segment before choosing the opposite subducting side.
The smoothed cell forcing drives the crust/relief rules and does not consume
this ledger; physical polarity,
slab geometry/selection/transfer, material fate, physical time, and plate-speed
calibration remain false. See the [deep scientific
audit](geo_generation_maturation_deep_audit.md) for the evidence and physical
references.

The always-emitted `crust_overlap_candidate_fate_model` is likewise diagnostic,
not a configuration switch. It groups all same-step boundary segments by a
persistent unordered plate-pair ID and emits one row for every overlap
membership class with multiplicity at least two. A binary class can receive
candidate contributor roles only when its two source-snapshot plate IDs are
distinct, that pair exists in the boundary snapshot, the destination is an
endpoint of at least one pair segment, and all pair segments supply uniform
evidence. Contributor roles are global membership-class CSR indices. Classes
with higher multiplicity and every absent, nonincident, mixed, conflicting, or
unavailable case remain wholly unresolved. Current physical polarity is
explicitly unknown, so generated candidates can use only unanimous
unique-oceanic-side heuristics. Pair consensus and endpoint incidence do not
resolve a local atom/fragment-to-segment link, connected topology, allocation,
physical fate, slab state/transfer, swept area, or state mutation.
The mapping is authoritative only for these deterministic serialized diagnostic
rows; it is physically non-authoritative and non-authoritative for allocation.
Per-cell/global overlap-excess operands and all five candidate-area
totals/residual use general-format `max_digits10` binary64 round-trip
serialization, with finite operation/operand-count replay bounds instead of a
blanket absolute or relative tolerance.

---

## `climate` — climate drivers

| Property | Type | Default | Range | What it controls | Affects |
| --- | --- | --- | --- | --- | --- |
| `months` | enum | `12` | `12` | Months in the seasonal cycle. Fixed at 12 (the monthly layers are 12-long). | climate, water_budget |
| `lapse_rate_c_per_km` | float | `6.5` | `[0, 15]` | Temperature drop per km of elevation. Sets mountain cooling → `temperature_c`, snowlines, biomes. | climate, cryosphere, ecology |
| `base_temperature_c` | float | `15.0` | `[−100, 100]` | Global mean sea-level temperature anchor. Shifts the whole climate. | climate (all) |
| `precipitation_scale` | float | `1.0` | `[0, 10]` | Global precipitation multiplier. `0` is an exact dry boundary and near-zero positive values remain proportional; negative empirical precipitation combinations clamp to zero before the thermal-moisture multiplier and monthly partitioning. Scales precipitation → runoff, rivers, and biomes. | water_budget, hydrology, ecology |
| `subtropical_drying_strength` | float | `0.65` | `[0, 0.9]` | Strength of subtropical (desert-belt) drying. Sets aridity of the horse latitudes. | climate, water_budget, ecology |

> Note the shipped earthlike config sets `precipitation_scale: 0.8` (drier than
> the schema default of 1.0).

---

## `hydrology` — routing policy

| Property | Type | Default | Range | What it controls | Affects |
| --- | --- | --- | --- | --- | --- |
| `river_percentile` | float | `0.92` | `[0.50, 0.995]` | Flow-accumulation percentile above which a cell is a river. Sets `is_river` density and network extent. | hydrology |
| `preserve_geologic_depressions` | bool | `true` | — | Whether geologic closed basins remain preserved and endorheic rather than entering numerical-depression correction. Sets `depression_policy`, `is_closed_basin`, and correction-ledger behavior. | hydrology |

---

## `erosion` — landscape evolution

The feedback loop runs `iterations` coupled maturation transitions. Continuous
mutations are scaled against the shipped 5 Ma reference interval. The exported
clock records that nominal coordinate, but it remains explicitly uncalibrated:
the coefficients are procedural reference-step responses rather than a complete
dimensioned landscape-evolution system.

| Property | Type | Default | Range | What it controls | Affects |
| --- | --- | --- | --- | --- | --- |
| `iterations` | int | `6` | `[0, 250]` | Number of erosion/feedback iterations. More = more mature landscapes; `0` disables erosion. Drives the stage count of the histories. | geomorphology, hydrology, sediment |
| `maturation_timestep_ma` | float | `5.0` | `(0, 5]` | Nominal Ma represented by each coupled transition. Values below 5 refine the reference step and rescale selected continuous tectonic, crustal, hillslope, and fluvial-incision responses; remap/event impulses and endpoint operators retain separate semantics. Values above 5 are rejected because the explicit operators do not yet implement stable coarse-step subcycling. This is not calibrated physical time. | tectonics, geomorphology, sediment, provenance |
| `stream_power_coefficient` | float | `7.5` | `[0, 1000]` | Overall erosivity K in the reference-step stream-power response. Applied incision multiplies the response by `maturation_timestep_ma / 5`; the exported `erosion_rate` remains reference-normalized so downstream diagnostics do not change merely because the timestep is refined. | hydrology, sediment |
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
| `backend` | enum | `auto` | `auto`, `cpu`, `opencl`, `cuda` | Compute backend. `auto` plans from the actual generated cell count: eligible CUDA is preferred at its calibrated threshold, then qualifying non-CPU OpenCL, then CPU. Explicit accelerator modes fail rather than silently changing semantics. The v3 exact spherical crust-overlap transport is CPU-authoritative for every backend; an active accelerator only computes, validates, reports, and discards a continuous-moment CSR shadow. | Performance (+ determinism, see gaps) |
| `threads` | int | `0` | `[0, 1024]` | CPU thread count; `0` = auto. | Performance, **determinism** |
| `opencl_prefer_gpu` | bool | `true` | — | Prefer GPU over CPU OpenCL devices when backend resolves to OpenCL. | Performance |

---

## `output` — payload shape (operational)

| Property | Type | Default | Range | What it controls | Affects |
| --- | --- | --- | --- | --- | --- |
| `include_cells` | bool | `true` | — | Whether per-cell arrays are written. **Required for the debugger** (`export-debug` errors without cells). | Debug cache availability |
| `float_precision` | int | `4` | `[0, 8]` | Decimal places for general/display floats in the JSON payload. Replay-critical crust, equilibrium, boundary, transport, elevation, and water-depth roots override this with general-format `max_digits10` binary64 round-trip serialization; the sediment interface separately retains its declared 10-decimal canonical-state and 8-decimal replay-operand contract. | Payload size/precision |

---

## Other configuration surfaces (not generation)

These configure the analysis commands, not world generation, and produce no
layers:

- **Calibration** (`magic-geo calibrate` / `calibrate-ensemble`):
  `configs/calibration_sources.*.json` point at real-world datasets (ETOPO,
  WorldClim, HydroBASINS/RIVERS, Natural Earth, and the Seton 2020 oceanic-age
  grid); `configs/calibration_ensemble.r1.json` defines an ensemble sweep. Fetch
  and derivation scripts live in [scripts/](../scripts). The HydroRIVERS source
  comparison selects exorheic backbone outlets with `NEXT_DOWN = 0`,
  `ENDORHEIC = 0`, and `ORD_CLAS = 1` before its upstream-area floor. The
  generated comparison now requires explicit `is_endorheic = false` and
  `outlet_type = ocean` semantics, a positive main-channel backbone length,
  and the same catchment-area floor; absent semantics fail coverage rather than
  falling back to the old all-terminal population. The checked Seton
  targets—mean age plus 20–200 Ma inclusive CDF values—are repository
  derivations from the checksum-pinned grid, not values quoted from the paper;
  the grid is validation evidence and is not consumed by generation. These
  files tune empirical targets, not a run.
- **Geo-validation** (`magic-geo validate-geo` / `validate-geo-suite`):
  `configs/geo_validation_matrix.yaml` and `configs/geo_validation_earth_empirical_targets.json`
  define the physical-plausibility target bands the generated world is checked against.
- **Validation** (`magic-geo validate`): schema/consistency checks on a payload; no config.

---

## Status & gaps

**Coverage.** All 44 generation properties across 9 sections are validated by the
`WorldConfig` schema with explicit bounds; unknown keys and non-finite values are
rejected at load. Every property is documented above with its first-order effect.

**Gaps and caveats:**

- **Enricher parameters are not configurable.** The Python enrichers that produce
  the majority of layers (soils, biomes, groundwater, resources, reefs, human
  geography, …) run with fixed internal constants. Only the physical drivers
  (`planet`/`tectonics`/`climate`/`hydrology`/`erosion`) are exposed. Tuning a
  biome threshold or an aquifer index means editing the module, not the config.
- **Determinism vs threads (known regression).** Output currently varies with
  `compute.threads` / `OMP_NUM_THREADS` (documented in the
  [reproducibility checklist](configuration_helpers.md#reproducibility-checklist));
  a fixed thread count is bit-stable, but different counts differ. `seed` alone is
  not sufficient for reproducibility until this is fixed.
- **Non-Earth planets are lightly validated.** The schema permits extreme planets
  (tiny radius, high luminosity, etc.), and planet-scaling tests confirm the knobs
  move outputs, but the geo-validation target bands are Earth-tuned, so exotic
  configs are not asserted physically plausible.
- **The maturation clock is nominal, not physical.** Timestep refinement now
  rescales continuous reference-step mutations and histories carry interval
  coordinates. Crust motion now uses conservative first-order spherical overlap,
  retains coalesced area classes keyed by each sorted contributing-source set,
  and exposes ordered per-reason positive/negative/net state-moment changes.
  A membership-area class can combine disconnected arrangement pieces; it does
  not resolve connected topology or fate. A separate exact directed reciprocal
  control-volume segment ledger now resolves local unsmoothed kinematic evidence,
  but only as intrinsic indices and nominal km/Ma values. Its oceanic-side result
  is a candidate, not physical subduction polarity, slab selection, or fate. The
  diagnostic overlap-class crosswalk completely partitions overlap excess into
  conservative pair-wide candidate/unknown buckets, but it does not allocate
  material or resolve a local segment link. The
  smoothed cell forcing is separate and is not driven by the
  ledger. Those records are not physical material-reservoir
  provenance; the current moving-domain diagnostic does not support convergence.
  Continuous CSR moments now have a bounded discarded-output accelerator shadow,
  but device execution on this host, spherical geometry, coverage/classes,
  categories, production state, and complete accelerator parity remain pending.
  Hillslope transport still lacks native shared-edge geometry, coefficients are not dimensionally calibrated,
  and the terminal cryosphere pass is a bulk operator. The payload therefore
  keeps `physical_time_resolved: false`.
- **Crust material provenance remains an always-on shadow audit, not a
  configurable physical model.** `crust_material_shadow_model` and its history
  persist sparse dry-rock mass origin packets through source-normalized overlap
  allocation and expose ordered rule-implied additions/removals. The last edge
  receives each source packet's arithmetic remainder; the difference from the
  raw overlap density-weighted scalar is serialized as a geometry residual, not
  treated as matter. There is no configuration switch because this state is
  non-authoritative audit evidence. Metadata deliberately keeps cell-state
  authority, physical source/sink and material-provenance resolution, solid
  volume, phase, mass-weighted age, upper mantle, subducted slab, and global
  crust-cycle conservation false. Configuring tectonic activity changes the
  unresolved adjustment record; it does not turn that audit into physical
  provenance.
- **Finite dry-rock accounting is a numerical counter-model, not a resolved
  mantle/slab cycle.** `crust_dry_rock_accounting_model` and its history are
  always emitted; there is no configuration switch. They close the shadow
  rule requests across surface basement, an upper-mantle exchange
  counter-reserve, and plate-owned slab tables. Packet keys are
  `(origin_domain_id, origin_kind_id, origin_plate_id)` and packet tables use
  owner-offset CSR. The finite `76 km * 3.08 g/cm3` capacity is an uncalibrated
  numerical surface-state envelope, not an estimate of upper-mantle mass.
  Transfers replay rule-derived proxy compensations and every transfer declares
  `physical_basis_resolved: false`; surface sinks are proportional, while
  mantle withdrawals consume the initial exchange reserve first and then the
  largest lowest-key packet. Every cell has instantaneous access to the same
  spatially unresolved global exchange pool; origin-key packets stay distinct,
  but mantle transport is not resolved. Slab tables remain empty. Cell-state
  authority, physical source/sink and provenance resolution, solid volume, phase,
  mass-weighted age, sediment coupling, coverage fate, subduction polarity,
  and physical upper-mantle/slab claims remain false. The measured 4,096-cell,
  seven-step accounting reference remains far below incremental fail-closed
  limits of 1,024 packets per surface owner, 1,000,000 live reservoir packets,
  and 1,000,000 transfers per step. Exact limits and observed peaks are
  serialized; the final reference peaks are 22 packets for one surface owner,
  22,145 live packets, and 5,896 transfers in one step. They are numerical
  memory-safety limits, not physical flux or reservoir-capacity limits. The
  geometry-stable 4,096-cell, seven-step reference coalesces `3,503,886` raw
  arrangement atoms to `111,022` membership-area classes (about `31.6x`), with
  at most 14 per destination. At the historical pre-initial-age/expanded-round-trip
  checkpoint, its exact boundary/candidate, thermal-target, and sediment audit
  payload was `178,764,102` uncompressed JSON bytes and direct-native-process
  maximum RSS was `371,176` KB; current payload size/RSS has not been remeasured.
- **Per-cell sediment source partitions are audit depths, not mass or
  provenance records.** Hillslope, fluvial, and glacial history stages emit
  cell-ID-indexed `source_production_depth_m_by_cell`,
  `alluvium_entrainment_depth_m_by_cell`, and
  `bedrock_erosion_depth_m_by_cell`. Native aggregation reconstructs the stage
  volumes with `depth_m * area_km2 / 1000`. The arrays expose where the
  alluvium-first partition was applied, but both
  `source_partition_audit_is_mass_claim` and
  `source_partition_audit_is_provenance_claim` remain false.
- **Surface relief now has an explicit bedrock/mobile-sediment interface, but
  no new configuration switch.** The always-emitted `sediment_interface_model`
  declares `bedrock_surface_elevation_m` and `sediment_thickness_m` canonical;
  `elevation_m` is derived as their sum. “Bedrock surface” means the top of
  nonmobile bedrock below the mobile layer, not the Moho or demonstrated
  stratigraphic basement. Initialization subtracts mobile thickness from the
  opening surface. Tectonic displacement and bedrock erosion change the bedrock
  surface; alluvium entrainment and deposition change mobile thickness; a
  sea-level datum adjustment shifts bedrock elevation without changing mobile
  thickness. These checked operations cover hillslope/fluvial, applied numeric
  breach, glacial, and sea-level paths. Independent validation reconstructs the
  final bedrock surface and mobile thickness from initial terrain and the linked
  histories before checking `elevation = bedrock + sediment`, so colluding
  final-field mutations do not pass. Each fluvial stage now emits a complete
  cell-ID-indexed routing-input snapshot at round-trip precision. Replay derives
  the acyclic active-step order, routing environment, capacity branches, marine
  fraction, terminal footprint (including targets with no active routing step),
  proportional allocation, and stage totals from that snapshot; selected
  numeric-breach deposition capacity and target depths are also derived rather
  than accepted as output witnesses. Canonical interface fields retain 10
  decimal places and every
  replay operand retains at least 8, independently of the general
  `output.float_precision`; metadata exposes both precision floors and the
  decimal-quantization forward-error model. This is a geometric interface only.
  Dry-rock mass, sediment density, porosity, compaction, grain provenance, and
  chemical weathering all remain explicitly unresolved. See [SPACE
  1.0](https://gmd.copernicus.org/articles/10/4577/2017/)
  for the coupled alluvium/bedrock distinction and [Paola and Voller
  (2005)](https://doi.org/10.1029/2004JF000274) for the additional terms needed
  for sediment mass and stratigraphic conservation.
- **Native marshaling is explicit, but behavioural consumption is not
  reported.** `config_to_native` returns the nine validated sections and
  `native.py` projects every current field into versioned ctypes structs. There
  is still no per-field runtime evidence report proving which downstream model
  changed, so a valid knob with no material effect would require tests or output
  comparison to detect.
- **No config-driven enable/disable of subsystems.** Every enricher always runs
  (given `include_cells`); you cannot switch off, say, the petroleum or dynasty
  models to shrink the payload. `erosion.iterations: 0` is the one coarse off-switch
  (disables the erosion/feedback passes).

To change a generation behaviour that isn't exposed here, the knob lives in the
producing module (see the **Produced by** lists in
[layers_reference.md](layers_reference.md)), not in the config schema.
