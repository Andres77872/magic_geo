# Topography, Isostasy and Thermal Subsidence

[Wiki home](../README.md) > Features

Surface elevation in magic-geo is not a single field that a noise generator writes once. It is composed at initialization from an isostatic equilibrium term plus a relative oceanic thermal-subsidence target plus seven procedural relief terms, then advanced every maturation step by an exactly-decomposed tectonic elevation change, then repeatedly re-datumed by a volume-constrained sea-level solve. This page documents each of those pieces against the source: the crust equilibrium relation, the continuity-adjusted Parsons–Sclater age-depth curve with its exact branch forms and explicit non-claims, the four-operand per-step decomposition and which single term is clamped, the binary64 round-trip serialization contract, the sea-level solver and its datum-shift primitive, the Python sea-level diagnostics enricher, and the independent replay validator. Every hedged claim in the source — "not physically time-calibrated", "no derivative continuity", "no absolute datum", "no realized thermal relief state" — is carried forward here unchanged.

## On this page

- [Where elevation is produced in the pipeline](#where-elevation-is-produced-in-the-pipeline)
- [Crust equilibrium elevation: the isostasy relation](#crust-equilibrium-elevation-the-isostasy-relation)
- [The oceanic-like predicate](#the-oceanic-like-predicate)
- [The oceanic age-depth thermal-subsidence curve](#the-oceanic-age-depth-thermal-subsidence-curve)
- [Initial elevation composition](#initial-elevation-composition)
- [Per-step tectonic elevation change decomposition](#per-step-tectonic-elevation-change-decomposition)
- [Applying the change to terrain](#applying-the-change-to-terrain)
- [Binary64 round-trip precision for these arrays](#binary64-round-trip-precision-for-these-arrays)
- [The quasi-static justification and its timescale-separation argument](#the-quasi-static-justification-and-its-timescale-separation-argument)
- [The sea-level solver and the datum-shift primitive](#the-sea-level-solver-and-the-datum-shift-primitive)
- [The sea-level diagnostics enricher](#the-sea-level-diagnostics-enricher)
- [Independent replay of the whole chain](#independent-replay-of-the-whole-chain)
- [Native test coverage](#native-test-coverage)
- [Working with these fields](#working-with-these-fields)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Where elevation is produced in the pipeline

Elevation is written and rewritten at five distinct points. The only complete stage ordering lives in `cpp/src/engine/pipeline.cpp`.

| Order | Call site | What it does to elevation |
|---|---|---|
| 1 | `derive_crust_and_topography(params, plates, cells, &earth.initial_oceanic_crust_age)` — `cpp/src/engine/pipeline.cpp:32` | Assigns crust category/thickness/density, builds the initial oceanic crust-age field, computes `initial_isostatic_elevation_m`, `thermal_subsidence_target_m`, the seven procedural relief terms, `initial_elevation_m`, and sets `elevation_m = initial_elevation_m` (`cpp/src/engine/tectonics.cpp:486-505`) |
| 2 | `initialize_sediment_interface(cell, "initial topography")` — `cpp/src/engine/tectonics.cpp:508-510` | Splits the opening surface into the canonical `bedrock_surface_elevation_m` + `sediment_thickness_m` pair (`cpp/src/engine/sediment_partition.cpp:91`) |
| 3 | `summarize_plate_motion_step(..., id=0, stage="initial_plate_domains", ...)` — `cpp/src/engine/pipeline.cpp:69-89` | Records the step-0 equilibrium checkpoint: `initial_isostatic_equilibrium_m` and `initial_thermal_subsidence_target_m` as both the "previous" and "post-process" operands, with all five change arrays exactly zero |
| 4 | `stabilize_numeric_depressions(...)` → `apply_sea_level(params, cells)` — `cpp/src/engine/hydrology.cpp:1140` | Shifts every cell's datum so that the selected connected marine component best-closes the configured water inventory (closure is interval-limited, not exact — see below); runs up to `NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES + 1 = 17` times per stabilization call (`cpp/src/engine/constants.hpp:55`, `cpp/src/engine/hydrology.cpp:1137-1141`) |
| 5 | `advance_plate_motion_and_crust(...)` then the combined commit inside `erode` — `cpp/src/engine/earth_system.cpp:930`, `cpp/src/engine/earth_system.cpp:1070-1080` | Produces `tectonic_elevation_change` per cell and applies it as the `vertical_displacement_m` operand of `apply_sediment_interface_material_change` |

Steps 4 and 5 repeat: `erode` runs `params.erosion_iterations` passes, each of which calls `advance_plate_motion_and_crust` and then `stabilize_numeric_depressions` (`cpp/src/engine/earth_system.cpp:928-938`). A final `cryosphere_coupling` stabilization runs after terminal glacial transport.

---

## Crust equilibrium elevation: the isostasy relation

`crust_equilibrium_elevation_m(thickness_km, density, oceanic)` is the single function that maps crust state to an isostatic equilibrium elevation. It is defined at `cpp/src/engine/tectonics.cpp:574-585`:

```cpp
double crust_equilibrium_elevation_m(double thickness_km, double density, bool oceanic) {
    if (oceanic) {
        return -OCEANIC_RIDGE_REFERENCE_DEPTH_M;
    }
    return CONTINENTAL_ISOSTATIC_FREEBOARD_M +
        CONTINENTAL_CRUST_THICKNESS_FREEBOARD_M_PER_KM * (
            thickness_km - CONTINENTAL_REFERENCE_CRUST_THICKNESS_KM
        ) -
        CONTINENTAL_CRUST_DENSITY_FREEBOARD_M_PER_G_CM3 * (
            density - CONTINENTAL_REFERENCE_CRUST_DENSITY_G_CM3
        );
}
```

Written out, for a non-oceanic-like cell:

```
E_iso(h, rho) = 500 + 12 * (h_km - 30) - 1800 * (rho_g_cm3 - 2.72)     [metres]
E_iso(oceanic_like) = -2500                                            [metres]
```

The serialized declarative form of this is `plate_kinematic_model.isostatic_equilibrium_formula = "oceanic_like?-2500:500+12*(crust_thickness_km-30)-1800*(crust_density_g_cm3-2.72)"` (mirrored in `src/magic_geo/oceanic_age_depth_validation.py:168-171`).

### Inputs and constants

| Symbol | Constant name | Value | Unit | Source |
|---|---|---|---|---|
| `h_km` | (input) `thickness_km` | per-cell | km | `cells[].crust_thickness_km`; per-step root `plate_motion_history[].crust_overlap_ledger.remapped_crust_thickness_km_by_cell` + `crust_thickness_process_change_km_by_cell` |
| `rho` | (input) `density` | per-cell | g/cm³ | `cells[].crust_density`; per-step root `remapped_crust_density_by_cell` + `crust_density_process_change_by_cell` |
| — | (input) `oceanic` | bool | — | `is_oceanic_crust_state(...)` at every per-step call site (`cpp/src/engine/tectonics.cpp:718-730`, `cpp/src/engine/tectonics.cpp:1090-1116`, `cpp/src/engine/tectonics.cpp:1577-1586`) |
| 500 | `CONTINENTAL_ISOSTATIC_FREEBOARD_M` | `500.0` | m | `cpp/src/engine/constants.hpp:27` |
| 30 | `CONTINENTAL_REFERENCE_CRUST_THICKNESS_KM` | `30.0` | km | `cpp/src/engine/constants.hpp:28` |
| 12 | `CONTINENTAL_CRUST_THICKNESS_FREEBOARD_M_PER_KM` | `12.0` | m/km | `cpp/src/engine/constants.hpp:29` |
| 2.72 | `CONTINENTAL_REFERENCE_CRUST_DENSITY_G_CM3` | `2.72` | g/cm³ | `cpp/src/engine/constants.hpp:30` |
| 1800 | `CONTINENTAL_CRUST_DENSITY_FREEBOARD_M_PER_G_CM3` | `1800.0` | m per g/cm³ | `cpp/src/engine/constants.hpp:31` |
| −2500 | `OCEANIC_RIDGE_REFERENCE_DEPTH_M` | `2500.0` | m | `cpp/src/engine/constants.hpp:36` |

The `OCEANIC_RIDGE_REFERENCE_DEPTH_M` comment in `cpp/src/engine/constants.hpp:32-36` states the rationale verbatim: *"Parsons and Sclater (1977) give 2500 m as the zero-age intercept of ocean-floor depth. Thermal subsidence is added separately by the age-depth target, so using a deeper baseline would count part of that depth twice."* This is why the oceanic branch of `crust_equilibrium_elevation_m` is a flat constant and carries no thickness or density dependence: the depth-versus-age signal is supplied entirely by the separate thermal target.

### Two distinct oceanic tests at initialization

`derive_crust_and_topography` computes `cell.initial_isostatic_elevation_m` using a **broad category test** `oceanic = crust_type == 0 || crust_type == 2 || crust_type == 3` (`cpp/src/engine/tectonics.cpp:425`, used at `cpp/src/engine/tectonics.cpp:436-446`), whereas the step-0 plate-motion operand `previous_local_isostatic_equilibrium_m` is computed by `crust_equilibrium_elevation_m` with `is_oceanic_crust_state(...)` (`cpp/src/engine/pipeline.cpp:46-60`). These are different predicates in code. Given the initial category state produced by `initial_crust_category_state` (`cpp/src/engine/tectonics.cpp:226-283`) — crust type 2 always paired with lithology 0, crust type 3 with thickness clamped to `[4.5, 14.0]` km and density fixed at 3.00 g/cm³, and initial oceanic ages bounded by `crust_age_ceiling_ma(params, INITIAL_OCEANIC_CRUST_MAX_AGE_MA=200.0)` (`cpp/src/engine/initial_oceanic_age.cpp:68-70`, `cpp/src/engine/constants.hpp:42`) — the two evaluate the same at initialization. They can diverge after the ordered crust process rules mutate thickness, density, or age.

---

## The oceanic-like predicate

`is_oceanic_crust_state` (`cpp/src/engine/tectonics.cpp:513-530`) is the shared gate for both the isostatic branch and the thermal target. It is a mixed categorical/numeric test:

| Crust type id | Name (`CRUST_NAMES`) | Rule | Result |
|---|---|---|---|
| 0 | `oceanic` | unconditional | `true` |
| 2 | `transitional` | `lithology == 0` (`basalt`) | `true` iff basalt |
| 3 | `volcanic_arc` | `age_ma <= 320.0 && thickness_km <= 18.0 && density >= 2.84` | conjunction of all three |
| 1, 4, 5, 6, 7, 8 | `continental`, `craton`, `orogen`, `rift_basin`, `sedimentary_basin`, `accreted_terrane` | falls through the `crust_type != 3` guard | `false` |

The serialized declarative form is `oceanic_age_depth_model.oceanic_like_predicate = "crust_type_0_or_crust_type_2_with_lithology_0_or_crust_type_3_with_age_le_320_ma_thickness_le_18_km_density_ge_2_84_g_cm3"` (`cpp/src/engine/process_serialization.cpp:3289-3290`).

The Python replay implements the exact same predicate in `is_oceanic_like_crust_state` (`src/magic_geo/oceanic_age_depth_validation.py:407-433`), and additionally models the predicate as *interval-valued* when replaying from round-trip serialized operands: `_predicate_options` (`src/magic_geo/oceanic_age_depth_validation.py:955-985`) returns `(True,)`, `(False,)`, or the ambiguous `(False, True)` when the reconstructed age/thickness/density error bounds straddle a threshold. That ambiguity handling exists only for crust type 3; types 0 and 2 are exact.

---

## The oceanic age-depth thermal-subsidence curve

The entire curve is one function, `oceanic_age_depth_thermal_subsidence_m(crust_age_ma, oceanic_like)`, in `cpp/src/engine/oceanic_age_depth.cpp:5-49`. It is the only place the curve is evaluated; every caller in `tectonics.cpp` and `pipeline.cpp` goes through it.

### Constants

| Constant | Value | Unit | Declared at |
|---|---|---|---|
| `OCEANIC_AGE_DEPTH_YOUNG_CUTOFF_MA` | `70.0` | Ma | `cpp/src/engine/internal.hpp:26` |
| `OCEANIC_AGE_DEPTH_YOUNG_COEFFICIENT_M_PER_SQRT_MA` | `350.0` | m·Ma^(−1/2) | `cpp/src/engine/internal.hpp:27-28` |
| `OCEANIC_AGE_DEPTH_OLD_EXPONENTIAL_SCALE_M` | `3200.0` | m | `cpp/src/engine/internal.hpp:29` |
| `OCEANIC_AGE_DEPTH_OLD_EFOLDING_TIME_MA` | `62.8` | Ma | `cpp/src/engine/internal.hpp:30` |
| `OCEANIC_AGE_DEPTH_TARGET_DIFFERENCE_GAIN` | `1.0` | dimensionless | `cpp/src/engine/internal.hpp:31-32` |

### The two branches, exactly as implemented

Let `S(t)` be the **positive, ridge-relative basement subsidence** in metres for age `t` in Ma. The branch switch is at `t <= 70.0` (an inclusive `<=`, `cpp/src/engine/oceanic_age_depth.cpp:19`).

**Young branch** (`0 <= t <= 70`):

```
S(t) = 350 * sqrt(t)
```

**Old branch** (`t > 70`):

```
S(t) = 350 * sqrt(70) + 3200 * ( exp(-70 / 62.8) - exp(-t / 62.8) )
```

The serialized formula strings match character-for-character (`cpp/src/engine/process_serialization.cpp:3283-3288`):

| Model key | Serialized value | Line |
|---|---|---|
| `young_relative_subsidence_formula` | `S_m=350*sqrt(t_ma)_for_0_le_t_ma_le_70` | `:3283-3284` |
| `old_relative_subsidence_formula` | `S_m=350*sqrt(70)+3200*(exp(-70/62.8)-exp(-t_ma/62.8))_for_t_ma_gt_70` | `:3285-3286` |
| `thermal_subsidence_sign_formula` | `thermal_subsidence_target_m=-S_m_for_oceanic_like_else_0` | `:3287-3288` |

### The C0-continuity offset

The published old-age shape in the repo's citation is a bare `3200 exp(-t/62.8)` decay. The implementation does **not** use it as an absolute depth. Instead it re-anchors the old branch to the young branch's value at the cutoff by writing the old branch as `S(70) + 3200 * (exp(-70/62.8) - exp(-t/62.8))`. Because the parenthesised term evaluates to exactly zero at `t = 70`, `S(70⁻) = S(70) = S(70⁺)` up to one ULP, and the branch is C0-continuous by construction.

Expressed as an additive offset relative to the raw `-3200 exp(-t/62.8)` shape, the constant is:

```
offset = 350 * sqrt(70) + 3200 * exp(-70 / 62.8)
       = 2928.3100928692643 + 1049.6965561681577
       = 3978.006649037422   [metres]
```

which is also the `t → ∞` asymptotic subsidence of the model.

The engine README states the claim boundary in one sentence (`cpp/src/engine/README.md:143-148`):

> Oceanic-like cells use a relative thermal-subsidence target based on the young `350 sqrt(t)` relation and old `3200 exp(-t / 62.8)` shape from [Parsons and Sclater (1977)](https://doi.org/10.1029/JB082i005p00803). The implementation changes branches at 70 Ma and offsets the old branch to enforce C0 value continuity; it does not claim derivative continuity or reproduce the paper's absolute-depth datum.

### The explicit non-claims

These are serialized as booleans inside `oceanic_age_depth_model` (`cpp/src/engine/process_serialization.cpp:3318-3343`) and mirrored verbatim in `src/magic_geo/oceanic_age_depth_validation.py:132-151`.

| Model key | Value | Meaning |
|---|---|---|
| `continuity_at_transition_resolved` | `true` | C0 value continuity at 70 Ma is asserted and tested |
| `derivative_continuity_at_transition_resolved` | **`false`** | No C1 slope continuity is claimed |
| `absolute_basement_depth_calibrated` | **`false`** | The curve is relative; the published absolute-depth datum is not reproduced |
| `authoritative_for_relative_thermal_subsidence_target_curve` | `true` | The one thing the module *is* authoritative for |
| `authoritative_for_realized_thermal_relief_component` | **`false`** | Realized relief is not attributed to this term |
| `realized_thermal_relief_state_tracked` | **`false`** | No separate realized-relief state variable exists |
| `thermal_relaxation_timescale_calibrated` | **`false`** | The relaxation timescale is not calibrated |
| `unapplied_thermal_tendency_residual_carried_forward` | **`false`** | Nothing is carried forward, because nothing is withheld |
| `unapplied_thermal_equilibrium_residual_zero_by_construction` | `true` | The full target difference is applied every step |
| `thermal_contribution_outside_bounded_dynamic_relief_clamp_resolved` | `true` | The thermal term never passes through the clamp |
| `thermal_contribution_to_tectonic_elevation_change_replayed` | `true` | Replayed by the Python validator |
| `physical_crust_creation_age_provenance` | **`false`** | Ages are procedural, not reconstructed creation ages |
| `ridge_age_distance_consistency` | **`false`** | No ridge-distance/age consistency claim |
| `thermal_structure_represented` | **`false`** | No thermal structure |
| `heat_flow_represented` | **`false`** | No heat flow |
| `dynamic_topography_represented` | **`false`** | No mantle-driven dynamic topography |
| `flexure_represented` | **`false`** | No flexural response |
| `physical_dynamics_represented` | **`false`** | No physical dynamics |

`authority_scope` is the string `relative_oceanic_thermal_subsidence_target_curve_only` (`cpp/src/engine/process_serialization.cpp:3264-3265`).

### The citation as the repo gives it

| Model key | Serialized value |
|---|---|
| `source_doi` | `10.1029/JB082i005p00803` |
| `source_relation_scope` | `parsons_sclater_1977_supplies_young_350_sqrt_t_relation_and_old_3200_exp_minus_t_over_62_8_shape` |
| `continuity_adjustment` | `implementation_switches_at_70_ma_and_adds_an_offset_to_the_old_branch_for_c0_value_continuity_not_c1_slope_continuity` |

The README renders the same DOI as [Parsons and Sclater (1977)](https://doi.org/10.1029/JB082i005p00803) (`cpp/src/engine/README.md:145`). Note the deliberate wording: the paper *supplies the relations*; the repo never claims to reproduce the paper's fitted absolute bathymetry.

### Sign, zero handling and guards

```cpp
if (!std::isfinite(crust_age_ma) || crust_age_ma < 0.0) {
    throw std::invalid_argument(
        "oceanic age-depth model requires a finite nonnegative crust age");
}
if (!oceanic_like) { return 0.0; }
...
if (!std::isfinite(relative_subsidence_m) || relative_subsidence_m < 0.0) {
    throw std::runtime_error(
        "oceanic age-depth model produced invalid relative subsidence");
}
if (relative_subsidence_m == 0.0) { return 0.0; }
return -relative_subsidence_m;
```

| Guard | Behaviour | Line |
|---|---|---|
| Non-finite or negative age | throws `std::invalid_argument` — checked **before** the `oceanic_like` short-circuit, so even a non-oceanic cell with a bad age throws | `cpp/src/engine/oceanic_age_depth.cpp:9-13` |
| `oceanic_like == false` | returns positive `0.0` | `cpp/src/engine/oceanic_age_depth.cpp:14-16` |
| Non-finite or negative computed subsidence | throws `std::runtime_error` | `cpp/src/engine/oceanic_age_depth.cpp:39-44` |
| Exactly zero subsidence (age 0) | returns `+0.0`, not `-0.0` — this explicit branch prevents a signed zero from reaching the serializer | `cpp/src/engine/oceanic_age_depth.cpp:45-47` |
| Otherwise | returns `-relative_subsidence_m` (nonpositive) | `cpp/src/engine/oceanic_age_depth.cpp:48` |

The signed-zero avoidance is directly asserted by the native test: `CHECK(!std::signbit(oceanic_age_depth_thermal_subsidence_m(0.0, true)))` (`cpp/tests/oceanic_age_depth_test.cpp:58`).

### Worked example: exact binary64 values

The Python validator pins seven fixed-age oracle values as **hex float literals** so they are independent of the implementation expression (`src/magic_geo/oceanic_age_depth_validation.py:222-230`). These are `S(t)`, the positive subsidence; the serialized `thermal_subsidence_target_m` is the negation.

| Age `t` (Ma) | Branch | `S(t)` (m) | Hex literal |
|---|---|---|---|
| `0.0` | young | `0.0` | `0x0.0p+0` |
| `20.0` | young | `1565.247584249853` | `0x1.874fd86b9c07ep+10` |
| `nextafter(70, -inf)` | young | `2928.310092869264` | `0x1.6e09ec47e186cp+11` |
| `70.0` | young (inclusive `<=`) | `2928.3100928692643` | `0x1.6e09ec47e186dp+11` |
| `nextafter(70, +inf)` | old | `2928.3100928692647` | `0x1.6e09ec47e186ep+11` |
| `100.0` | old | `3326.9807656214452` | `0x1.9fdf626e95a4cp+11` |
| `320.0` | old | `3958.4098803939855` | `0x1.eecd1dbd7cee1p+11` |

The three values around 70 Ma differ by exactly one ULP each — that is the C0 continuity, empirically. The slope, however, jumps:

```
d/dt [350 sqrt(t)] at t = 70⁻            = 175 / sqrt(70)          = 20.91650066335189 m/Ma
d/dt [-3200 exp(-t/62.8)] at t = 70⁺     = (3200/62.8) exp(-70/62.8) = 16.714913314779583 m/Ma
```

A ~4.2 m/Ma kink at the branch point. This is exactly why `derivative_continuity_at_transition_resolved` is `false` and why the native continuity test bounds each side with its own one-input-ULP derivative envelope rather than asserting slope equality (`cpp/tests/oceanic_age_depth_test.cpp:80-94`).

---

## Initial elevation composition

`derive_crust_and_topography` writes nine per-cell components and their sum (`cpp/src/engine/tectonics.cpp:486-495`). All nine are serialized on `cells[]`.

| Cell field | Formula in `derive_crust_and_topography` | Precision |
|---|---|---|
| `initial_isostatic_elevation_m` | `oceanic ? -2500 : 500 + 12*(h-30) - 1800*(rho-2.72)` (`:436-446`) | `surface_precision = max(10, float_precision)` |
| `thermal_subsidence_target_m` | `oceanic_age_depth_thermal_subsidence_m(crust_age_ma, oceanic_like)` (`:454-457`) | **`roundtrip_num`** (binary64 round-trip) |
| `initial_ridge_uplift_m` | `div * (oceanic ? 0.0 : 880.0) * relief_scale` (`:462`) | `surface_precision` |
| `initial_rift_subsidence_m` | `div * (oceanic ? 0.0 : -820.0) * relief_scale` (`:463`) | `surface_precision` |
| `initial_orogenic_uplift_m` | `(continental ? conv² * 20000 : conv * 1350) * relief_scale` (`:465-469`) | `surface_precision` |
| `initial_trench_subsidence_m` | `(oceanic ? -conv² * S_trench : -conv * 350) * relief_scale`, with `S_trench = 1400` for volcanic arc else `17000` (`:470-477`) | `surface_precision` |
| `initial_volcanic_uplift_m` | `((crust_type==3 ? 15000*conv² : 0) + 380*div) * relief_scale` (`:478-481`) | `surface_precision` |
| `initial_transform_fault_relief_m` | `-320 * trans` (`:482`) | `surface_precision` |
| `initial_secondary_roughness_m` | `(continental?520:180)*coherent_n2 + (oceanic?260:620)*n0 + 180*sin(9*lon + 4*lat)` (`:483-485`) | `surface_precision` |
| `initial_elevation_m` | the exact sum of the nine terms above, in that written order (`:495`) | `surface_precision` |

Supporting scalars:

| Name | Formula | Line |
|---|---|---|
| `relief_scale` | `clamp(1 / sqrt(max(0.08, gravity_g)), 0.55, 1.60)` | `cpp/src/engine/tectonics.cpp:294` |
| `tectonic_activity` | `clamp(internal_heat * sqrt(4.5 / max(0.05, geological_age_ga)), 0.25, 2.25)` | `cpp/src/engine/tectonics.cpp:295` |
| Trench scales | `OCEANIC_TRENCH_SUBSIDENCE_SCALE_M = 17000.0`, `VOLCANIC_ARC_TRENCH_SUBSIDENCE_SCALE_M = 1400.0` | `cpp/src/engine/constants.hpp:44-45` |
| Uplift scales | `CONTINENTAL_OROGEN_UPLIFT_SCALE_M = 20000.0`, `VOLCANIC_ARC_UPLIFT_SCALE_M = 15000.0` | `cpp/src/engine/constants.hpp:43, 46` |

The comment at `cpp/src/engine/tectonics.cpp:458-461` explains why the oceanic ridge/rift terms are zeroed: *"The published age-depth relation already includes the elevated zero-age ridge intercept. Adding a second oceanic ridge uplift would double-count that bathymetry; the continental divergent term remains a separate broad rift-shoulder proxy."*

Summary aggregates: `mean_initial_isostatic_elevation_m` and `mean_initial_elevation_m` reduce the corresponding `cells[]` fields (`cpp/src/engine/summary.cpp:429, 437, 2015, 2024`), while `mean_initial_thermal_subsidence_m` is reduced from `plate_motion_history[0].post_process_local_thermal_subsidence_target_m`, not from a cell field (`cpp/src/engine/summary.cpp:221-226, 2016`).

---

## Per-step tectonic elevation change decomposition

Every maturation transition calls `advance_plate_motion_and_crust` (`cpp/src/engine/tectonics.cpp:1050`), which returns a per-cell `tectonic_elevation_change` vector. That vector is built from four operands in the per-cell loop at `cpp/src/engine/tectonics.cpp:1577-1647`.

### The four terms

| # | Term | Formula | Clamped? | Lines |
|---|---|---|---|---|
| 1 | `isostatic_equilibrium_change_m` | `1.0 * (E_iso(new_state) − E_iso(previous_state))` | **No** | `cpp/src/engine/tectonics.cpp:1577-1623` |
| 2 | `thermal_equilibrium_change_m` | `1.0 * (S_target(new_age, new_oceanic_like) − S_target(previous))` | **No** | `cpp/src/engine/tectonics.cpp:1587-1603` |
| 3 | `unbounded_dynamic_relief_change_m` | `uplift_rate * 0.42 + boundary_change` | — (this is the pre-clamp value) | `cpp/src/engine/tectonics.cpp:1632-1634` |
| 4 | `bounded_dynamic_relief_change_m` | `clamp(term 3, -180.0, 220.0)` | **Yes — the only clamped term** | `cpp/src/engine/tectonics.cpp:1635-1639` |

### Composition

```cpp
const double equilibrium_change =
    isostatic_equilibrium_tendency_m + thermal_equilibrium_change;
...
const double delta = equilibrium_change + bounded_dynamic_relief_change;
tectonic_elevation_change[index] = delta;
cell.cumulative_tectonic_elevation_change_m += delta;
```

which is, associativity included as written:

```
tectonic_elevation_change_m_by_cell
    = ( isostatic_equilibrium_change_m + thermal_equilibrium_change_m )
      + bounded_dynamic_relief_change_m
```

The serialized declarative form is `plate_kinematic_model.tectonic_elevation_change_formula = "isostatic_equilibrium_change_m+thermal_equilibrium_change_m+bounded_dynamic_relief_change_m"` (`cpp/src/engine/process_serialization.cpp:2918-2919`), and the README states the same identity at `cpp/src/engine/README.md:154-156`.

### The clamp and its interval

| Constant | Value | Declared at | Serialized as |
|---|---|---|---|
| `TECTONIC_DYNAMIC_RELIEF_MINIMUM_CHANGE_M` | `-180.0` | `cpp/src/engine/internal.hpp:35` | `plate_kinematic_model.dynamic_relief_minimum_change_m` |
| `TECTONIC_DYNAMIC_RELIEF_MAXIMUM_CHANGE_M` | `220.0` | `cpp/src/engine/internal.hpp:36` | `plate_kinematic_model.dynamic_relief_maximum_change_m` |
| — | `clamp(unbounded_dynamic_relief_change_m,-180,220)` | — | `plate_kinematic_model.bounded_dynamic_relief_formula` |

Only `unbounded_dynamic_relief_change_m` passes through this interval. The source comment at `cpp/src/engine/tectonics.cpp:1624-1629` gives the reason verbatim:

> Isostatic relaxation is effectively complete on the nominal 5 Ma maturation interval, so equilibrium target changes must not share the empirical per-step relief clamp. Clipping the combined term used to leave kilometre-scale oceanic freeboard behind after a crust-state transition, with no carried residual. Only the heuristic dynamic relief increment remains bounded here.

The corresponding serialized flags are `equilibrium_target_difference_clamped = false` and `combined_tectonic_equilibrium_and_dynamic_clamp_present = false` (`cpp/src/engine/process_serialization.cpp:2902-2905`).

### The dynamic-relief formula in full

```
uplift_rate      = tectonic_uplift_scale
                 * tectonic_activity
                 * (1.5 * divergent + 8.5 * convergent + (crust_type == 3 ? 2.5 : 0.0))
                 * maturation_timestep_scale

boundary_change  = 80 * (convergent - previous_convergent)
                 + 55 * (divergent  - previous_divergent)
                 - 30 * (transform  - previous_transform)

unbounded_dynamic_relief_change_m = uplift_rate * 0.42 + boundary_change
bounded_dynamic_relief_change_m   = clamp(unbounded, -180, 220)
```

| Operand | Source | Line |
|---|---|---|
| `tectonic_uplift_scale` | `params.tectonic_uplift_scale`; config `erosion.tectonic_uplift_scale`, default `0.85`, range `[0, 10]` | `src/magic_geo/config.py:412-417` |
| `tectonic_activity` | `clamp(internal_heat * sqrt(4.5 / max(0.05, geological_age_ga)), 0.25, 2.25)`; exported as `plate_kinematic_model.tectonic_activity_index` | `cpp/src/engine/process_serialization.cpp:2878-2887` |
| `maturation_timestep_scale` | `params.maturation_timestep_ma / MATURATION_REFERENCE_TIMESTEP_MA` with `MATURATION_REFERENCE_TIMESTEP_MA = 5.0` | `cpp/src/engine/core.cpp:44-47`, `cpp/src/engine/constants.hpp:72` |
| `0.42` | `TECTONIC_UPLIFT_RATE_RESPONSE_FRACTION`; exported as `plate_kinematic_model.tectonic_uplift_rate_response_fraction` | `cpp/src/engine/internal.hpp:37`, `cpp/src/engine/process_serialization.cpp:2910-2911` |
| `convergent`/`divergent`/`transform` | `cell.boundary_convergent` etc., the **degree-normalized smoothed** per-cell forcing recomputed by `classify_boundaries` after the plate rotation | `cpp/src/engine/tectonics.cpp:1136`, `cpp/src/engine/tectonics.cpp:1267-1269` |
| `previous_*` | the same three fields captured **before** the rotation | `cpp/src/engine/tectonics.cpp:1117-1119` |

`cell.uplift_rate` is also written to `cells[].tectonic_uplift_rate_m_per_step` (`cpp/src/engine/tectonics.cpp:1611-1613`).

### The step-0 checkpoint

The first `plate_motion_history` record (`stage = "initial_plate_domains"`, `erosion_iteration = -1`) is constructed with `initial_zero_change_m` for all five change arrays and the same vector supplied as both the previous and post-process target (`cpp/src/engine/pipeline.cpp:69-89`). The declared semantics string is `initial_step_checkpoint_semantics = "previous_local_target_equals_post_process_initial_target_and_thermal_equilibrium_change_is_zero"` (`cpp/src/engine/process_serialization.cpp:3302-3303`), and both the C++ integration test (`cpp/tests/oceanic_age_depth_integration_test.cpp:440-447`) and the Python replay (`src/magic_geo/oceanic_age_depth_validation.py:1341-1358`) assert exact zeros and equality, not tolerances.

### Native self-checks inside `summarize_plate_motion_step`

Before writing the step record, `summarize_plate_motion_step` recomputes all four operands from the *current cell state* and raises if any recorded value differs by even one bit (`cpp/src/engine/tectonics.cpp:716-804`):

| Check | Exception message | Lines |
|---|---|---|
| `isostatic_equilibrium_change_m[i] != gain * (E_iso_post − E_iso_prev)` or non-finite | `plate-motion isostatic equilibrium change is non-finite or stale` | `:736-746` |
| `cell.thermal_subsidence_target_m != oceanic_age_depth_thermal_subsidence_m(cell.crust_age_ma, post_oceanic_like)` | `plate-motion thermal checkpoint is non-finite or stale` | `:754-761` |
| `thermal_equilibrium_change_m[i] != gain * (post − previous)` | `plate-motion thermal equilibrium change is non-finite or stale` | `:769-775` |
| `bounded_dynamic_relief_change_m[i] != clamp(unbounded[i], -180, 220)` | `plate-motion bounded dynamic relief change is non-finite or stale` | `:781-790` |
| `tectonic_elevation_change_m[i] != iso + thermal + bounded` | `plate-motion tectonic elevation change does not replay` | `:795-804` |

A symmetric guard runs at the *start* of `advance_plate_motion_and_crust`: the previous-step `cell.thermal_subsidence_target_m` must equal a freshly recomputed target for the previous crust state, or it throws `cell thermal subsidence is non-finite or stale before plate motion` (`cpp/src/engine/tectonics.cpp:1097-1108`). These are exact `!=` comparisons on binary64, not tolerance tests.

---

## Applying the change to terrain

`tectonic_elevation_change` is not written directly to `elevation_m`. It enters the combined terrain commit inside `erode` as the `vertical_displacement_m` argument of the checked interface primitive (`cpp/src/engine/earth_system.cpp:1070-1080`):

```cpp
apply_sediment_interface_material_change(
    cells[i],
    tectonic_elevation_change[i],                                    // vertical_displacement_m
    hillslope_bedrock_erosion_depth_m + fluvial_bedrock_erosion_depth_m,
    hillslope_alluvium_entrainment_depth_m + fluvial_alluvium_entrainment_depth_m,
    sediment_delta[i] + hillslope_deposition_depth_m[i],
    "hillslope/fluvial sediment interface"
);
```

The primitive (`cpp/src/engine/sediment_partition.cpp:155-230`) computes, in `long double`:

```
bedrock'  = bedrock + vertical_displacement - bedrock_erosion
sediment' = max(0, sediment - alluvium_entrainment + deposition)
elevation'= bedrock' + sediment'
```

and rejects entrainment beyond the opening mobile inventory (`cpp/src/engine/sediment_partition.cpp:187-192`). This is the engine invariant that surface elevation is *derived*, never independently written: see `cpp/src/engine/README.md:227-231` and the invariant at `cpp/src/engine/README.md:330-332`.

A separate provisional surface `next[i]` is also composed in the same iteration (`cpp/src/engine/earth_system.cpp:969-973`) as `elevation_m + tectonic_change − hillslope_production + hillslope_deposition`, then reduced by the stream-power depth; it feeds routing and accommodation only. Note the exported `cell.erosion_rate` is the unscaled 5 Ma reference response while only the applied `erosion_depth_m = stream * maturation_timestep_scale(params)` is integrated over the nominal step (`cpp/src/engine/earth_system.cpp:986-995`).

---

## Binary64 round-trip precision for these arrays

The engine deliberately splits serialization into a **display-precision** path and an **exact round-trip** path.

| Primitive | Format | Behaviour | Source |
|---|---|---|---|
| `num(value, precision)` | `std::fixed` with `precision` **decimal places** | display precision; drives `add_double` | `cpp/src/engine/core.cpp` |
| `roundtrip_num(value)` | `std::defaultfloat` with `std::numeric_limits<double>::max_digits10` (= 17) **significant digits** | recovers the original binary64 after JSON parse | `cpp/src/engine/numeric_serialization.cpp:5-16` |
| `roundtrip_double_array_json(values)` | array of `roundtrip_num` | same, elementwise | `cpp/src/engine/numeric_serialization.cpp:18-28` |

Both throw `attempted to serialize a non-finite simulation value` on NaN/Inf, so no non-finite value can reach the document.

### Which topography arrays are on the exact path

Every per-cell equilibrium and change array in `plate_motion_history[]` is emitted through `roundtrip_double_array_json` (`cpp/src/engine/process_serialization.cpp:4349-4384`):

| Array | Emitted by | Line |
|---|---|---|
| `tectonic_elevation_change_m_by_cell` | `roundtrip_double_array_json` | `:4349-4352` |
| `previous_local_isostatic_equilibrium_m` | `roundtrip_double_array_json` | `:4353-4356` |
| `post_process_local_isostatic_equilibrium_m` | `roundtrip_double_array_json` | `:4357-4360` |
| `isostatic_equilibrium_change_m` | `roundtrip_double_array_json` | `:4361-4364` |
| `previous_local_thermal_subsidence_target_m` | `roundtrip_double_array_json` | `:4365-4368` |
| `post_process_local_thermal_subsidence_target_m` | `roundtrip_double_array_json` | `:4369-4372` |
| `thermal_equilibrium_change_m` | `roundtrip_double_array_json` | `:4373-4376` |
| `unbounded_dynamic_relief_change_m` | `roundtrip_double_array_json` | `:4377-4380` |
| `bounded_dynamic_relief_change_m` | `roundtrip_double_array_json` | `:4381-4384` |
| `boundary_convergent_by_cell` / `boundary_divergent_by_cell` / `boundary_transform_by_cell` | `roundtrip_double_array_json` | `:4323-4328` |
| `crust_age_process_change_ma_by_cell` / `crust_thickness_process_change_km_by_cell` / `crust_density_process_change_by_cell` | `roundtrip_double_array_json` | `:4343-4348` |
| `crust_age_change_ma_by_cell` / `crust_thickness_change_km_by_cell` / `crust_density_change_by_cell` | `roundtrip_double_array_json` | `:4331-4336` |

On `cells[]`, six fields use `roundtrip_num` (`cpp/src/engine/entity_serialization.cpp:151-186`):

| Cell field | Line | Why |
|---|---|---|
| `crust_age_ma` | `:151` | replay operand for the age-depth curve |
| `crust_thickness_km` | `:152-153` | replay operand for the isostatic relation |
| `crust_density` | `:154-155` | replay operand for the isostatic relation |
| `thermal_subsidence_target_m` | `:160-161` | must equal the final `post_process_local_thermal_subsidence_target_m` bit-for-bit |
| `elevation_m` | `:185` | ocean-mask determinant |
| `water_depth_m` | `:186` | ocean-mask determinant |

The comment at `cpp/src/engine/entity_serialization.cpp:182-184` states the reason for the last two: *"These two fields jointly determine the discrete ocean mask. Fixed fractional formatting can collapse a one-ULP-below-sea-level water cell to signed zero and make the serialized mask unreplayable."*

### Why exactness is required, not merely nice

1. **The native checks are exact `!=` comparisons.** `summarize_plate_motion_step` refuses to record a step whose change arrays differ from a freshly recomputed value by a single bit (`cpp/src/engine/tectonics.cpp:736-804`). Any lossy serialization would make an externally-parsed document inconsistent with the invariant the engine itself enforces.
2. **The Python replay compares against binary64 forward-error bounds, not fitted epsilons.** `_operation_bound` (`src/magic_geo/oceanic_age_depth_validation.py:257-277`) derives its tolerance from `sys.float_info.epsilon`, the replay operation count, and `2 * math.ulp(scale)` for serialization rounding. If the serialized operands were truncated to `float_precision = 4` decimals, the parsed operand error would exceed that bound by many orders of magnitude and every cell would fail.
3. **The predicate is threshold-sensitive.** `is_oceanic_crust_state` compares against `320.0` Ma, `18.0` km, and `2.84` g/cm³. A truncated density of `2.8400` versus `2.83999999...` flips the branch and moves the target by `2500 m + S(t)`. The Python validator already has to model this as an ambiguity interval (`src/magic_geo/oceanic_age_depth_validation.py:971-985`); larger operand error would make the ambiguity unresolvable.
4. **The ocean mask is discrete.** `elevation_m` and `water_depth_m` decide `is_water`; the datum-shift path in `apply_sea_level` even nudges bedrock by one ULP to preserve a strict wet decision (`cpp/src/engine/ocean.cpp:251-269`).

The README states the contract at `cpp/src/engine/README.md:134-141` and notes it is *distinct* from the sediment interface's intentional 10-decimal canonical-state / 8-decimal replay-operand contract.

The MessagePack facade **transcodes the canonical JSON document** rather than re-serializing from the native doubles, precisely so every decimal-quantization boundary — including this one — is preserved (`cpp/src/engine/README.md:27-31`).

---

## The quasi-static justification and its timescale-separation argument

The operator applies the **full** local equilibrium target difference in a single maturation step, with gain exactly 1.0 and no relaxation fraction:

| Gain constant | Value | Declared at | Serialized as |
|---|---|---|---|
| `TECTONIC_ISOSTATIC_TARGET_DIFFERENCE_GAIN` | `1.0` | `cpp/src/engine/internal.hpp:33-34` | `plate_kinematic_model.isostatic_target_difference_gain` |
| `OCEANIC_AGE_DEPTH_TARGET_DIFFERENCE_GAIN` | `1.0` | `cpp/src/engine/internal.hpp:31-32` | `plate_kinematic_model.thermal_target_difference_gain`, `oceanic_age_depth_model.thermal_target_difference_gain` |

The justification the repo gives is a timescale-separation argument, serialized as a string:

| Model key | Serialized value | Line |
|---|---|---|
| `tectonic_equilibrium_adjustment_model` | `quasi_static_full_local_target_difference_plus_bounded_dynamic_relief_v1` | `cpp/src/engine/process_serialization.cpp:2888-2889` |
| `equilibrium_timescale_separation_basis` | `nominal_5_ma_reference_step_is_more_than_three_orders_of_magnitude_longer_than_3_to_4_ka_degree_2_to_20_viscoelastic_relaxation_estimates` | `cpp/src/engine/process_serialization.cpp:2890-2891` |
| `isostatic_relaxation_source_doi` | `10.1111/j.1365-246X.1971.tb01823.x` | `cpp/src/engine/process_serialization.cpp:2892-2893` |
| `isostatic_relaxation_reference_min_years` | `3000.0` | `cpp/src/engine/process_serialization.cpp:2894-2895` |
| `isostatic_relaxation_reference_max_years` | `4000.0` | `cpp/src/engine/process_serialization.cpp:2896-2897` |

The README renders the citation as [O'Connell (1971)](https://doi.org/10.1111/j.1365-246X.1971.tb01823.x) and states the caveat in the same sentence (`cpp/src/engine/README.md:158-165`):

> The quasi-static choice uses the timescale separation between the nominal 5 Ma reference interval and 3–4 ka degree-2-to-20 viscoelastic relaxation estimates from O'Connell (1971); it does not make the nominal interval or operator physically time-calibrated.

The caveat is machine-checkable, not just prose:

| Flag | Value | Location |
|---|---|---|
| `plate_kinematic_model.equilibrium_operator_physical_time_calibrated` | `false` | `cpp/src/engine/process_serialization.cpp:2903` |
| `oceanic_age_depth_model.thermal_relaxation_timescale_calibrated` | `false` | `cpp/src/engine/process_serialization.cpp:3326` |
| `oceanic_age_depth_model.realized_thermal_relief_state_tracked` | `false` | `cpp/src/engine/process_serialization.cpp:3325` |
| Every process-ledger record's `nominal_time_calibrated` and `physical_time_resolved` | `false` | shared nominal-time block, `cpp/src/engine/process_serialization.cpp:135` |

So: the argument justifies *why an instantaneous target-difference operator is not obviously wrong at 5 Ma*. It does not assert that 5 Ma is a physical duration, that the relaxation is calibrated, or that a realized-versus-target relief split exists anywhere in the state.

---

## The sea-level solver and the datum-shift primitive

`apply_sea_level(params, cells)` (`cpp/src/engine/ocean.cpp:5-275`) searches for a global sea level at which the **largest connected flooded component** holds `params.ocean_water_inventory_km3`, then shifts every cell's datum so the selected level becomes zero.

Closure is **not** guaranteed exact. The sweep only evaluates candidate levels at elevation-interval boundaries plus the analytic in-interval solution, and keeps whichever candidate minimises `abs(volume − target)` (`cpp/src/engine/ocean.cpp:102-125, 157-181`). When no interval admits the analytic solution the nearest interval endpoint is retained, and the residual is published as `sea_level_model.ocean_water_inventory_error_km3` / `ocean_water_inventory_error_fraction`. The `sea_level.ocean_inventory_closure` check therefore admits `max(0.01, abs(target) * 1e-9)` km³ of error (`src/magic_geo/geo_validation.py:1339`), not zero.

### The model contract

| `sea_level_model` key | Value | Line |
|---|---|---|
| `model_type` | `volume_constrained_connectivity_ocean_flood_v3` | `cpp/src/engine/process_serialization.cpp:3405` |
| `selection_rule` | `solve_largest_connected_ocean_cell_column_volume_across_elevation_intervals` | `:3406-3407` |
| `area_basis` | `native_cell_area_km2` | `:3408` |
| `volume_basis` | `sum_native_cell_area_times_water_depth` | `:3409` |
| `ocean_connectivity_enforced` | `true` | `:3458` |
| `disconnected_below_sea_level_cells_remain_land` | `true` | `:3459` |
| `sea_level_recomputed_each_erosion_stage` | `true` | `:3460` |
| `model_limitation` | `cell_column_volume_without_subcell_bathymetry_straits_or_exact_coast_polygons` | `:3461-3462` |

Every floating-point field in `sea_level_model` is emitted through `add_double` at `max_digits10` decimal places (still `std::fixed`, so this is display precision, not the `roundtrip_num` contract) — except `below_sea_level_land_area_km2`, which uses `params.float_precision` (`cpp/src/engine/process_serialization.cpp:3456-3457`). The counts (`target_ocean_cell_count`, `selected_ocean_cell_count`, `ocean_area_target_error_cell_count`, `connected_ocean_component_count`, `below_sea_level_land_cell_count`) are `add_int` and carry no precision argument.

### Algorithm

| Phase | What happens | Lines |
|---|---|---|
| Sort | Cells sorted ascending by `elevation_m`, ties broken by ascending `id` | `cpp/src/engine/ocean.cpp:11-18` |
| Area guard | Total positive area must be `> 0`, else `sea-level selection requires positive cell areas` | `:20-28` |
| Zero-inventory path | If `ocean_water_inventory_km3 <= 0`, sea level = `nextafter(lowest_elevation, -inf)`; every cell is datum-shifted, all water flags cleared | `:29-47` |
| Union-find sweep | Cells activated in elevation-tie groups; neighbours merged; component area and area-weighted elevation maintained incrementally | `:49-91`, `:126-141` |
| Largest-component tracking | Largest by area, ties broken by lowest member id | `:142-156` |
| Interval solve | For the current component: `solved = (target_km3 * 1000 + Σ area*elev) / Σ area`. Candidates considered are the interval lower bound `nextafter(elevation, +inf)`, the exact solved level when it lies in `[lower, next_elevation)`, and otherwise `nextafter(next_elevation, elevation)` | `:157-181` |
| Candidate scoring | Keeps the smallest `abs(volume − target)`; ties broken by lower sea level | `:102-125` |
| Early exit | The sweep breaks as soon as an exact in-interval solution is found | `:183-185` |
| Component rebuild | The selected flood elevation re-labels `below_level`, BFS finds the largest connected component (ties by lowest id) | `:188-231` |
| Consistency guard | Rebuilt area must match the swept area within `max(1e-6, area * 1e-12)`, else `connectivity-constrained sea-level reconstruction mismatch` | `:232-237` |
| Datum shift + flags | `shift_sediment_interface_datum(cell, -sea_level, "sea-level datum")`; `is_water` set from the selected component; `water_depth_m = is_water ? -elevation_m : 0`; `water_body = is_water ? 1 : 0`; `is_lake = false` | `:244-273` |
| Strict-depth tie fix | If a selected-ocean cell's composed `elevation_m` is not `< 0`, `bedrock_surface_elevation_m` is nudged to `nextafter(-sediment_thickness_m, -inf)` and the interface revalidated | `:251-269` |

The strict-depth tie comment (`cpp/src/engine/ocean.cpp:252-257`) explains it: the flood interval selects cells strictly below the level, but independently rounded bedrock and sediment operands can cancel back to signed zero when the datum is composed, so only the bedrock operand is moved one representable value down — *"without a finite empirical depth adjustment"*.

### The datum-shift primitive

`shift_sediment_interface_datum(cell, elevation_change_m, context)` (`cpp/src/engine/sediment_partition.cpp:123-153`) is the only path sea level uses to touch terrain:

| Property | Behaviour |
|---|---|
| Pre-check | `validate_sediment_interface(cell, context)` — rejects non-finite values, negative `sediment_thickness_m`, or a surface-closure residual beyond the forward-error bound |
| Shift | `bedrock' = bedrock + elevation_change_m`, computed in `long double` and range-checked by `checked_interface_value` |
| Mobile layer | `sediment_thickness_m` is **unchanged** |
| Surface | `elevation' = bedrock' + sediment_thickness_m`, rederived, never independently written |
| Post-check | `validate_interface_values(...)` re-runs the closure test |
| Non-finite shift | throws `<context> sediment-interface datum shift is nonfinite` |

The serialized contract in `sediment_interface_model` is `sea_level_datum_update = "bedrock_surface_elevation_m'=bedrock_surface_elevation_m-sea_level_adjustment_m;sediment_thickness_m'=sediment_thickness_m"` (`cpp/src/engine/process_serialization.cpp:1849-1850`).

The forward-error bound used by all interface checks is `max(absolute_floor, 128 * DBL_EPSILON * max(1, term_count) * (1 + |term_sum|))` with `absolute_floor = 1e-12` (`cpp/src/engine/sediment_partition.cpp:7-20, 60-77`).

### Where sea level is invoked

`apply_sea_level` is called once per pass of the stabilization loop, which runs up to `NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES + 1` times (`cpp/src/engine/hydrology.cpp:1137-1141`). Each call accumulates into `HydrologyStabilizationResult::sea_level_adjustment_m` and increments `sea_level_recompute_count`; both are serialized on each `earth_system_feedback_history[]` record — `sea_level_recompute_count` at `cpp/src/engine/process_serialization.cpp:2178` and `sea_level_adjustment_m` at `:2238-2239` (the latter at `max(10, precision)` decimals), alongside the `sea_level_recomputed` boolean at `:2168`. `label_marine_water_bodies` then re-classifies the water bodies: the largest connected water component becomes `continental_shelf` where `water_depth_m < 220.0` and `ocean` otherwise; every other water component becomes `inland_sea` (`cpp/src/engine/ocean.cpp:312-320`).

### Configuration inputs

| Config key | Default | Range | Role |
|---|---|---|---|
| `planet.ocean_water_inventory_km3` | `1_338_000_000.0` | `[0, 1e10]` | The solved constraint. `src/magic_geo/config.py:215-220` |
| `planet.ocean_fraction_target` | `0.70` | `[0, 0.95]` | **Diagnostic only** — it appears in `sea_level_model` as `ocean_fraction_target` and drives the `target_ocean_*` error diagnostics, but it is not the control variable. `src/magic_geo/config.py:209-214`, `cpp/src/engine/process_serialization.cpp:3353-3355, 3374-3375` |

---

## The sea-level diagnostics enricher

`enrich_world_with_sea_level_diagnostics(world)` (`src/magic_geo/sea_level_diagnostics.py:300-392`) is a **Python post-processing enricher**, not part of the native simulation. It runs in both generation paths: `src/magic_geo/api.py:203` (full world) and `src/magic_geo/api.py:318` (geo-only). It reads only `cells[]` and writes derived component records; it never mutates elevation, depth, or the water mask.

### Marine classification input

```python
MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
```
(`src/magic_geo/sea_level_diagnostics.py:8`). A cell is land iff `not cell["is_water"]` (`:19-20`), and marine iff its `water_body_type` is in that set (`:23-24`).

### Per-cell fields it adds

All five are initialized for every cell before any component walk (`src/magic_geo/sea_level_diagnostics.py:304-309`).

| Cell field | Initial value | Filled by |
|---|---|---|
| `landmass_id` | `-1` | land connected-component walk |
| `marine_region_id` | `-1` | marine connected-component walk |
| `marine_chokepoint_id` | `-1` | `_marine_chokepoints` (`:278`) |
| `continental_shelf_id` | `-1` | `continental_shelf`-only component walk |
| `island_class` | `"water"` if not land else `"unassigned"` | overwritten with the landmass record's class |

### Top-level arrays it adds

| World key | Record builder | Fields per record |
|---|---|---|
| `landmasses` | `_landmass_record` (`:95-128`) | `id`, `cell_ids`, `cell_count`, `area_km2`, `centroid_lat_deg`, `centroid_lon_deg`, `mean_elevation_m`, `max_elevation_m`, `coastal_cell_count`, `shoreline_neighbor_edge_count`, `island_class`, `dominant_biome`, `dominant_lithology` |
| `marine_regions` | `_marine_region_record` (`:131-171`) | `id`, `cell_ids`, `cell_count`, `area_km2`, `centroid_lat_deg`, `centroid_lon_deg`, `region_class`, `dominant_water_body_type`, `water_body_counts`, `mean_water_depth_m`, `max_water_depth_m`, `coastal_cell_count`, `adjacent_landmass_ids`, `connected_to_open_ocean` |
| `continental_shelves` | `_continental_shelf_record` (`:174-242`) | `id`, `cell_ids`, `cell_count`, `area_km2`, `centroid_lat_deg`, `centroid_lon_deg`, `mean_water_depth_m`, `max_water_depth_m`, `mean_sediment_thickness_m`, `coastal_cell_count`, `shelf_break_cell_count`, `shoreline_neighbor_edge_count`, `shelf_break_neighbor_edge_count`, `open_ocean_neighbor_edge_count`, `inland_sea_neighbor_edge_count`, `adjacent_landmass_ids`, `marine_region_ids` |
| `marine_chokepoints` | `_marine_chokepoints` (`:245-297`) | `id`, `cell_id`, `type`, `marine_region_id`, `water_body_type`, `lat_deg`, `lon_deg`, `water_depth_m`, `land_neighbor_edge_count`, `marine_neighbor_edge_count`, `constriction_index`, `width_proxy_km`, `adjacent_landmass_ids`, `adjacent_marine_region_ids` |

### Classification thresholds

| Rule | Threshold | Line |
|---|---|---|
| `island_class = "continent"` | `area_km2 >= 5_000_000.0` | `:86-87` |
| `island_class = "large_island"` | `area_km2 >= 500_000.0` | `:88-89` |
| `island_class = "island"` | `area_km2 >= 50_000.0` | `:90-91` |
| `island_class = "islet"` | otherwise | `:92` |
| `region_class = "open_ocean"` | component contains ≥1 `ocean` cell | `:153-154` |
| `region_class = "inland_sea"` | no `ocean` cell but ≥1 `inland_sea` cell | `:154` |
| `region_class = "continental_shelf"` | otherwise | `:154` |
| Chokepoint candidate | marine cell with `>= 2` land neighbours **and** `>= 2` marine neighbours | `:254-257` |
| Chokepoint kept | `len(adjacent_landmass_ids) >= 2` **or** `constriction >= 0.5` | `:266-267` |
| Chokepoint `type` | `"strait"` if `>= 2` distinct adjacent landmasses, else `"marine_narrows"` | `:275` |

`constriction_index = land_neighbors / max(1, total_neighbors)` (`:258`); `width_proxy_km = cell["mean_neighbor_edge_length_km"] / max(1, land_neighbors)` (`:276`) — note this reads a field written by an earlier geometry enricher, and falls back to `0.0` when absent.

### Summary keys it writes

Written into `world["summary"]` (`src/magic_geo/sea_level_diagnostics.py:363-386`); all rounded to 6 decimals where floating.

| Summary key | Definition |
|---|---|
| `landmass_count` | number of land components |
| `continent_landmass_count` | components with `island_class == "continent"` |
| `island_landmass_count` | components with `island_class != "continent"` |
| `largest_landmass_area_km2` | `max` over landmass areas, default `0.0` |
| `mean_landmass_area_km2` | mean landmass area, `0.0` when none |
| `marine_region_count` | number of marine components |
| `open_ocean_marine_region_count` | regions classed `open_ocean` |
| `inland_sea_marine_region_count` | regions classed `inland_sea` |
| `continental_shelf_marine_region_count` | regions classed `continental_shelf` |
| `largest_marine_region_area_km2` | `max` over marine-region areas |
| `continental_shelf_count` | number of shelf components |
| `continental_shelf_cell_count` | total shelf cells |
| `continental_shelf_total_area_km2` | summed shelf area |
| `largest_continental_shelf_area_km2` | `max` shelf area |
| `mean_continental_shelf_depth_m` | mean `water_depth_m` over `continental_shelf` cells, `0.0` when none |
| `continental_shelf_shoreline_edge_count` | summed `shoreline_neighbor_edge_count` |
| `continental_shelf_break_edge_count` | summed `shelf_break_neighbor_edge_count` |
| `marine_chokepoint_count` | number of chokepoints |
| `strait_chokepoint_count` | chokepoints typed `strait` |
| `mean_marine_chokepoint_constriction_index` | mean constriction, `0.0` when none |

**Name collision, deliberately flagged.** `extract_geo_metrics` (`src/magic_geo/geo_validation.py:339, 492`) also emits a metric called `continent_landmass_count`, but it is defined as `len(world["landmasses"])` — the **total** landmass count, not the `island_class == "continent"` subset written here at `src/magic_geo/sea_level_diagnostics.py:364`. The two values differ whenever any landmass is smaller than 5,000,000 km². Neither is consumed by `_validate_earthlike_profile` (`src/magic_geo/geo_validation.py:764-800`), whose envelope covers only `ocean_fraction`, `global_mean_temperature_c`, `mean_land_precipitation_mm_y`, `elevation_span_m`, `river_cell_fraction`, `ice_cell_fraction`, `calibration_pass_fraction`, `realism_evidence_coverage_fraction`, `applicable_realism_pass_fraction`, and `biome_diversity`. The summary key's own consumer is the world-consistency validator, which recomputes it from `landmasses` and fails on mismatch (`src/magic_geo/cli/commands/validate.py:9865, 9879-9881`).

`marine_regions` and `continental_shelves` are declared `required_outputs` of the `sea_level_ocean` layer contract (phase 5), which depends on `relief_bathymetry` and declares validator domains `sea_level`, `ocean_circulation`, `coastal_marine_landmass` (`src/magic_geo/geo_layer_contracts.py:113-132`). The contract's `evidence_class` is `volume_replay_with_diagnostic_circulation` and, like every layer, it hardcodes `empirical_realism_proven: False`.

---

## Independent replay of the whole chain

`validate_oceanic_age_depth(world)` (`src/magic_geo/oceanic_age_depth_validation.py:1176-1769`) is a strict, from-scratch replay. It is wired into `validate-geo` as the single check `tectonics.oceanic_age_depth_thermal_target_replay` (`src/magic_geo/geo_validation_physics.py:2599-2644`). It returns `{"passed": bool, "failures": [...], "metrics": {...}}`.

Model identifier: `MODEL = "continuity_adjusted_parsons_sclater_relative_basement_subsidence_v1"` (`src/magic_geo/oceanic_age_depth_validation.py:12`).

### Preconditions

| Gate | Rule | Line |
|---|---|---|
| Cell bound | `0 < len(cells) <= 200_000` | `:37, 676-679` |
| History bound | `0 < len(plate_motion_history) <= 251` | `:38, 680-684` |
| Kinematic cardinality | `configured_motion_step_count + 1 == len(history) == history_step_count` | `:697-712` |
| Array cardinality | Twenty step arrays and three ledger arrays must each have exactly `cell_count` entries | `:714-764` |
| Step ids | `step["id"] == step_index` | `:743-746` |
| Model schema | `set(oceanic_age_depth_model) == set(MODEL_LITERAL_VALUES)` — **exact key-set equality**, then per-field type-strict comparison (`is` for bools) | `:443-459` |
| Kinematic model | All 27 `KINEMATIC_EQUILIBRIUM_LITERAL_VALUES` present and equal (presence + equality, not key-set equality) | `:153-218, 462-476` |
| Timestep operands | `0 < nominal_timestep_ma <= 5.0` and `reference_timestep_ma == 5.0`; `maturation_timestep_scale` replayed as their quotient | `:478-502` |
| Tectonic activity | `clamp(internal_heat * sqrt(4.5 / max(0.05, geological_age_ga)), 0.25, 2.25)` replayed with an explicit libm ULP allowance | `:504-535` |
| Upstream root | `validate_crust_overlap_transport(world)["passed"] is True` — the replay refuses to run on an unvalidated crust-transport root | `:1254-1259` |

### The operand roots it accepts

The replay never reads `cells[].crust_age_ma` etc. as the formula root. It reconstructs post-process crust state per step from the overlap ledger plus the same-step process deltas (`_build_post_process_state`, `src/magic_geo/oceanic_age_depth_validation.py:788-952`):

```
age       = crust_overlap_ledger.remapped_crust_age_ma_by_cell      + crust_age_process_change_ma_by_cell
thickness = crust_overlap_ledger.remapped_crust_thickness_km_by_cell + crust_thickness_process_change_km_by_cell
density   = crust_overlap_ledger.remapped_crust_density_by_cell      + crust_density_process_change_by_cell
```

matching the serialized `authoritative_formula_root = "plate_motion_history_crust_overlap_remapped_numeric_state_plus_same_step_process_deltas_and_step_categorical_state"`. It then links each step to the previous via `crust_*_change_*_by_cell` and requires the link residual to stay inside `_reconstruction_bound` — an explicit 128-ULP cancellation envelope plus the arithmetic bound (`:768-785`), described in the source as *"scale-derived, not a fit epsilon"*.

The final `cells[].thermal_subsidence_target_m` must equal the last `post_process_local_thermal_subsidence_target_m` **exactly** (`==`, `:1656-1660`), and the final `cells[].crust_type` / `cells[].lithology` strings must match the enum names of the final step's categorical arrays (`:1661-1666`).

### What is checked, per cell per step

| # | Assertion | Tolerance basis | Line |
|---|---|---|---|
| 1 | `previous_local_isostatic_equilibrium_m` replays from the previous step's post-process state through the isostatic formula | propagated state bound + `_operation_bound(..., operation_count=6)` | `:1049-1119, 1380-1390` |
| 2 | `post_process_local_isostatic_equilibrium_m` replays from this step's state | same | `:1391-1401` |
| 3 | `previous_local_thermal_subsidence_target_m` replays, **forced to the same oceanic-like branch** the isostatic match selected | formula bound + age-error propagation | `:1402-1413` |
| 4 | `post_process_local_thermal_subsidence_target_m` replays, same branch coupling | same | `:1414-1425` |
| 5 | `thermal_change` must be nonpositive (`_match_thermal` asserts `actual <= 0.0`) | exact sign test | `:1031` |
| 6 | `isostatic_equilibrium_change_m == 1.0 * (post − previous)` | `_target_change_operation_bound` | `:1455-1471` |
| 7 | `thermal_equilibrium_change_m == 1.0 * (post − previous)` | `_target_change_operation_bound` | `:1473-1489` |
| 8 | `unbounded_dynamic_relief_change_m` replays from the full dynamic formula (step 0: must be exactly `0.0` with bound `0.0`) | `_operation_bound(..., operation_count=18)` | `:1122-1173, 1501-1523` |
| 9 | `bounded_dynamic_relief_change_m == min(220, max(-180, unbounded))` | **exact equality**, no tolerance | `:1532-1539` |
| 10 | `tectonic_elevation_change_m_by_cell == (iso + thermal) + bounded` | `_operation_bound(..., operation_count=2)` | `:1541-1565` |
| 11 | Boundary forcing arrays lie in `[0, 1]` | exact | `:1306-1312` |
| 12 | Step 0: previous == post for both targets, and all five change arrays exactly `0.0` | exact | `:1341-1358` |
| 13 | Step *n* > 0: `previous_*` arrays equal the previous step's `post_process_*` arrays by Python list equality | exact | `:1366-1375` |

### Reductions and telescoping

| Reduction | What it asserts | Line |
|---|---|---|
| Per-step ordered thermal formula reduction | `Σ post_thermal` (actual) vs `Σ post_thermal` (replayed) stays inside the accumulated element bounds plus a reduction bound over `2*(n−1)` operations | `:620-648, 1622-1633` |
| Global ordered formula reduction | same, across every step and cell | `:1731-1736` |
| Global ordered tendency reduction | same for `thermal_equilibrium_change_m` | `:1737-1740` |
| Isostatic telescoping | `Σ_steps isostatic_equilibrium_change_m[c]` must equal `final_post_isostatic[c] − initial_post_isostatic[c]` | `:1668-1694` |
| Thermal telescoping | `Σ_steps thermal_equilibrium_change_m[c]` must equal `final_post_thermal[c] − initial_post_thermal[c]` | `:1696-1722` |

Telescoping is the mechanical statement of "zero unapplied equilibrium residual": if any fraction of the target difference had been withheld or clamped, the per-step changes would not sum to the endpoint difference.

### Seven analytical checkpoints

`_validate_analytical_checkpoints` (`src/magic_geo/oceanic_age_depth_validation.py:552-581`) evaluates the curve at the seven hex-literal ages listed [above](#worked-example-exact-binary64-values), asserts monotonic non-decrease of `S(t)`, then asserts an **exact** C0 identity: `oceanic_relative_basement_subsidence_m(70.0) == 350*sqrt(70) + 3200*(exp(-70/62.8) - exp(-70/62.8))`, failing with `age-depth branches are not C0-continuous` (`:571-580`). The check's `expected` map pins `analytical_checkpoint_count: 7` (`src/magic_geo/geo_validation_physics.py:2618`).

### Declarative expectations attached to the check

`_append_check` records an `expected` map that enumerates both what is replayed and what is deliberately unresolved (`src/magic_geo/geo_validation_physics.py:2616-2642`). The `False` entries are: `authoritative_for_realized_thermal_relief_component`, `realized_thermal_relief_state_tracked`, `thermal_relaxation_timescale_calibrated`, `unapplied_thermal_tendency_residual_carried_forward`, `absolute_basement_depth_calibrated`, `physical_crust_creation_age_provenance`, `ridge_age_distance_consistency`, `thermal_structure_represented`, `heat_flow_represented`, `dynamic_topography_represented`, `flexure_represented`, `physical_dynamics_represented`. The check's own pass/fail comes solely from `oceanic_age_depth["passed"]`.

Two observability metrics are worth noting because they exist specifically to demonstrate the clamp separation (`src/magic_geo/oceanic_age_depth_validation.py:1582-1590`):

| Metric | Meaning |
|---|---|
| `equilibrium_change_exceeds_dynamic_clamp_cell_step_count` | count of `(cell, step)` pairs where `abs(iso + thermal) > 220` — i.e. equilibrium changes that would have been truncated had they shared the clamp |
| `tectonic_change_exceeds_dynamic_clamp_cell_step_count` | count of `(cell, step)` pairs where the composed total falls outside `[-180, 220]` |

### Related validators

| Check name (domain) | Module | Relation to this page |
|---|---|---|
| `conservative_crust_overlap_replay` (tectonics) | `src/magic_geo/crust_transport_validation.py` | Hard prerequisite — `validate_oceanic_age_depth` calls it and fails closed if it does not pass |
| `initial_oceanic_crust_age_graph_replay` (tectonics) | `src/magic_geo/initial_oceanic_crust_age_validation.py` | Replays the age field that feeds the curve at initialization |
| `bedrock_mobile_sediment_interface_replay` (sediment) | `src/magic_geo/sediment_interface_validation.py` | Replays final bedrock from initial terrain + tectonic displacement + bedrock-only erosion + **sea-level datum changes** |
| `sea_level.ocean_inventory_closure` | `src/magic_geo/geo_validation.py:1356-1375` | Reconstructs marine volume against `max(0.01, abs(target) * 1e-9)` km³ and requires `maximum_depth_plus_elevation_residual_m <= 1e-6` and zero nonnegative marine elevations |
| `sea_level.single_connected_ocean` | `src/magic_geo/geo_validation.py:1434-1442` | Requires marine water to be exactly the largest connected below-sea component and to match `sea_level_model` aggregates |

---

## Native test coverage

Two CTest targets cover this subsystem directly.

### `magic_geo_oceanic_age_depth` — `cpp/tests/oceanic_age_depth_test.cpp`

Links only `cpp/src/engine/oceanic_age_depth.cpp`, not the shared library.

| Function | Assertions |
|---|---|
| `analytic_checkpoints_match` (`:39-60`) | Seven ages (`0, 20, nextafter(70,0), 70, nextafter(70,+inf), 100, 320`) compared with **exact `==`** against an independently written expression using the same documented operation order — *"Exact equality catches a coefficient, branch, or continuity-offset change without a blanket tolerance."* Also asserts `S(0) == 0.0` and `!signbit` |
| `transition_is_c0_continuous_and_monotone` (`:62-108`) | Monotone ordering across the branch point; per-side continuity bounded by a one-input-ULP derivative envelope (`175/sqrt(70⁻)` and `(3200/62.8)·exp(−70/62.8)`) plus 8 output ULPs (young) / 16 output ULPs (old); then 1,280 quarter-Ma samples from 0.25 to 320 Ma must be finite and non-increasing |
| `non_oceanic_and_domain_guards_are_exact` (`:110-145`) | `oceanic_like == false` returns exactly `+0.0` at five ages; `DBL_MAX` age stays finite and negative; `-1.0`, `±inf`, and NaN all throw `std::invalid_argument` |

### `magic_geo_oceanic_age_depth_integration` — `cpp/tests/oceanic_age_depth_integration_test.cpp`

Links the shared library and generates a real 128-cell, 4-plate, 1-iteration geo world with seed 18491 on the CPU backend (`:145-159`). It then:

- Greps `oceanic_age_depth_model` for the model id, `authority_scope`, `continuity_at_transition_resolved: true`, `derivative_continuity_at_transition_resolved: false`, the sign formula, `thermal_target_difference_gain == 1.0`, and the application/root semantics strings (`:164-203`).
- Asserts twelve `false` flags and four `true` flags are present verbatim (`:204-229`).
- Asserts the deleted key `thermal_target_difference_tendency_m` does **not** appear anywhere in `plate_motion_history` (`:342-343`).
- For every step and cell, re-derives the four identities with **exact `==`**: `isostatic_change == post_iso − prev_iso`, `thermal_change == post − prev`, `bounded == clamp(unbounded, -180, 220)`, and `tectonic_change == iso + thermal + bounded` (`:425-436`).
- Requires the step-0 record to be all exact zeros and every later step's `previous_*` to equal the prior step's `post_*` (`:440-453`).
- Requires `saw_equilibrium_change_larger_than_dynamic_clamp` — at least one `(cell, step)` where `abs(iso + thermal) > 220.0` — so the test fails if the fixture never exercises the clamp separation (`:437-439, 456`).
- Requires the 128 `cells[].thermal_subsidence_target_m` values to equal the last step's `post_process_local_thermal_subsidence_target_m` array element-for-element (`:458-467`).

---

## Working with these fields

### Generate a geo-only world and read the decomposition

```python
from magic_geo.config import WorldConfig
from magic_geo.api import generate_geo_world

config = WorldConfig()
config.mesh.cell_count = 4096
config.erosion.iterations = 6
config.erosion.maturation_timestep_ma = 5.0
config.output.include_cells = True          # required by generate_geo_world

world = generate_geo_world(config)

step = world["plate_motion_history"][-1]
for cell_id in range(3):
    iso = step["isostatic_equilibrium_change_m"][cell_id]
    thermal = step["thermal_equilibrium_change_m"][cell_id]
    unbounded = step["unbounded_dynamic_relief_change_m"][cell_id]
    bounded = step["bounded_dynamic_relief_change_m"][cell_id]
    total = step["tectonic_elevation_change_m_by_cell"][cell_id]
    assert bounded == min(220.0, max(-180.0, unbounded))
    assert total == iso + thermal + bounded          # exact, both sides are binary64
    print(cell_id, iso, thermal, unbounded, bounded, total)
```

### Evaluate the published curve directly

```python
from magic_geo.oceanic_age_depth_validation import (
    ANALYTICAL_CHECKPOINTS_M,
    is_oceanic_like_crust_state,
    oceanic_relative_basement_subsidence_m,
)

# S(t) is positive; the serialized target is its negation for oceanic-like cells.
print(oceanic_relative_basement_subsidence_m(0.0))     # 0.0
print(oceanic_relative_basement_subsidence_m(20.0))    # 1565.247584249853
print(oceanic_relative_basement_subsidence_m(70.0))    # 2928.3100928692643
print(oceanic_relative_basement_subsidence_m(100.0))   # 3326.9807656214452

for age, oracle in ANALYTICAL_CHECKPOINTS_M:
    assert oceanic_relative_basement_subsidence_m(age) == oracle

# crust_type, lithology, age_ma, thickness_km, density_g_cm3
print(is_oceanic_like_crust_state(0, 0, 12.0, 7.0, 3.00))   # True  (oceanic)
print(is_oceanic_like_crust_state(2, 0, 12.0, 7.0, 3.00))   # True  (transitional basalt)
print(is_oceanic_like_crust_state(2, 3, 12.0, 7.0, 3.00))   # False (transitional sandstone)
print(is_oceanic_like_crust_state(3, 5, 12.0, 7.0, 3.00))   # True  (arc inside all bounds)
print(is_oceanic_like_crust_state(3, 5, 12.0, 7.0, 2.80))   # False (density < 2.84)
print(is_oceanic_like_crust_state(1, 1, 900.0, 40.0, 2.70)) # False (continental)
```

### Reproduce the isostatic relation

```python
def crust_equilibrium_elevation_m(thickness_km, density_g_cm3, oceanic_like):
    if oceanic_like:
        return -2500.0
    return 500.0 + 12.0 * (thickness_km - 30.0) - 1800.0 * (density_g_cm3 - 2.72)

assert crust_equilibrium_elevation_m(7.0, 3.00, True) == -2500.0
assert crust_equilibrium_elevation_m(30.0, 2.72, False) == 500.0
assert crust_equilibrium_elevation_m(45.0, 2.70, False) == 500.0 + 180.0 + 36.0
```

### Run the replay validator on its own

```python
from magic_geo.oceanic_age_depth_validation import validate_oceanic_age_depth

result = validate_oceanic_age_depth(world)
print(result["passed"])
print(result["metrics"]["analytical_checkpoint_count"])                       # 7
print(result["metrics"]["maximum_absolute_tectonic_application_residual_m"])
print(result["metrics"]["maximum_tectonic_application_binary64_bound_m"])
print(result["metrics"]["equilibrium_change_exceeds_dynamic_clamp_cell_step_count"])
for failure in result["failures"]:
    print(failure)
```

### Run the whole geo gate from the CLI

```bash
magic-geo generate --config configs/default.yaml --output build/world.json
magic-geo validate-geo --world build/world.json \
    --profile earthlike \
    --output build/geo_validation.json
```

Then pull just this check out of the report:

```bash
python3 - <<'PY'
import json
report = json.load(open("build/geo_validation.json"))
for check in report["checks"]:
    if check["name"] == "oceanic_age_depth_thermal_target_replay":
        print(check["status"], check["severity"])
        print(json.dumps(check["observed"], indent=2)[:2000])
PY
```

### Native tests

```bash
cmake -S . -B build && cmake --build build
ctest --test-dir build -R "magic_geo_oceanic_age_depth" --output-on-failure
```

### Inspect the sea-level contract and diagnostics

```python
model = world["sea_level_model"]
print(model["model_type"])                     # volume_constrained_connectivity_ocean_flood_v3
print(model["ocean_water_inventory_km3"], model["selected_ocean_volume_km3"])
print(model["ocean_water_inventory_error_km3"], model["ocean_water_inventory_error_fraction"])
print(model["connected_ocean_component_count"], model["below_sea_level_land_cell_count"])
print(model["model_limitation"])
# cell_column_volume_without_subcell_bathymetry_straits_or_exact_coast_polygons

print(world["summary"]["continent_landmass_count"],
      world["summary"]["continental_shelf_count"],
      world["summary"]["mean_continental_shelf_depth_m"],
      world["summary"]["strait_chokepoint_count"])
```

---

## Limitations and unresolved claims

### The cell-column shelf problem, in full

This is the single largest stated limitation of the elevation subsystem, and the repo states it in four independent places with consistent wording: `cpp/src/engine/README.md:167-175`, `README.md:352`, `docs/configuration_reference.md:87-96`, and `docs/geo_generation_maturation_deep_audit.md:266, 481`.

**The problem.** The sea-level solver floods **whole cells**. Each control volume carries exactly one scalar `elevation_m`, so flooding it is an all-or-nothing decision on the entire cell area. At the 4,096-cell Earth reference an equivalent-area cell is roughly **400 km across**. A real continental margin at that width contains land, shelf, shelf break, slope, rise, and abyssal plain simultaneously — the one scalar mixes all of them.

**Why "just lower the margin cells" is rejected.** Lowering a whole coastal cell to manufacture shelf area does not add shelf; it replaces the cell's unresolved land, shelf, slope, **and** deep-ocean portions with a single elevation. The configuration reference states flatly that this *"is not a supported tuning interpretation of either ocean parameter"* (`docs/configuration_reference.md:91-92`), and the audit repeats it as a prohibition: *"do not lower whole ~400 km cells to tune shelf area"* (`docs/geo_generation_maturation_deep_audit.md:481`).

**What is affected.** The `continental_shelf` classification in `label_marine_water_bodies` is a pure depth threshold — `water_depth_m < 220.0` on the largest connected water component (`cpp/src/engine/ocean.cpp:316`). Everything the Python enricher derives from it (`continental_shelves`, `continental_shelf_count`, `continental_shelf_total_area_km2`, `mean_continental_shelf_depth_m`, `shelf_break_*` counts, `marine_chokepoints` and `width_proxy_km`) inherits the same cell-column resolution. `strait`/`marine_narrows` detection is a neighbour-count heuristic on ~400 km cells, not a channel-width measurement.

**The stated next-architecture requirements.** Four requirements are named, consistently, across all sources:

| # | Requirement | Wording |
|---|---|---|
| 1 | Conservative subcell hypsometry | *"carry conservative subcell area–elevation distributions"* — an area–elevation distribution retained **inside** each coarse cell |
| 2 | Margin structure | *"margin shelf–slope–rise profiles"* within each coarse cell |
| 3 | Fractional flooding | *"flood fractional cell area/volume"* — flood fractions rather than cell centres, with exact subcell water volume and coastal fraction |
| 4 | Subcell connectivity | *"retain subcell narrow-channel connectivity"* / *"expose subcell strait connectivity and volume"* |

The audit adds a validation requirement: *"Validate coastline complexity and shelf-area/depth distributions at matched scale"* (`docs/geo_generation_maturation_deep_audit.md:481`).

**The citation and its status.** [Goswami et al. (2015)](https://doi.org/10.5194/gmd-8-2735-2015) is cited as *"the cited reference for combining plate cooling, sediment, and generalized continental margin structures"* — and immediately qualified: *"it is a design reference, not an implemented model claim"* (`cpp/src/engine/README.md:173-175`). Nothing from that architecture is implemented today.

### Other unresolved claims

| Claim | Status | Where declared |
|---|---|---|
| Derivative (C1) continuity at the 70 Ma branch point | **False.** A ~4.2 m/Ma slope discontinuity exists by construction | `oceanic_age_depth_model.derivative_continuity_at_transition_resolved` |
| Absolute basement depth / the paper's depth datum | **False.** The curve is relative only; `-2500 m` is a separate flat ridge intercept | `oceanic_age_depth_model.absolute_basement_depth_calibrated`, `cpp/src/engine/constants.hpp:32-36` |
| Realized thermal relief as a tracked state | **False.** Only the *target* and its differences exist; no realized-versus-target split is stored | `realized_thermal_relief_state_tracked`, `authoritative_for_realized_thermal_relief_component` |
| Calibrated thermal relaxation timescale | **False** | `thermal_relaxation_timescale_calibrated` |
| Physically time-calibrated equilibrium operator | **False.** The 3–4 ka / 5 Ma separation argument does **not** make the nominal interval physical | `plate_kinematic_model.equilibrium_operator_physical_time_calibrated`, `cpp/src/engine/README.md:158-165` |
| Nominal time calibration anywhere in the ledgers | **False** | `nominal_time_calibrated`, `physical_time_resolved` on every history record |
| Crust creation-age provenance / ridge-age-distance consistency | **False.** Initial ages come from `multi_source_nominal_ridge_graph_travel_time_v1` using one global nominal half-rate | `physical_crust_creation_age_provenance`, `ridge_age_distance_consistency`, `cpp/src/engine/README.md:115-132` |
| Thermal structure, heat flow, dynamic topography, flexure, physical dynamics | **All false** | five booleans in `oceanic_age_depth_model` |
| Subduction polarity behind the crust-state transitions that drive equilibrium changes | **Unknown.** The boundary ledger emits candidate subducting/overriding sides only; physical sides remain `unknown`, decision source `none`, confidence zero | `cpp/src/engine/README.md:205-226` |
| Mass provenance behind thickness/density changes that move the isostatic target | **False.** Ordered per-reason state-moment deltas are not physical fluxes | `tectonic_process_material_provenance_resolved`, `tectonic_process_source_sink_attribution_resolved` |
| The dynamic-relief term as physics | It is explicitly *"the heuristic dynamic relief increment"* and *"an empirical per-step relief clamp"* | `cpp/src/engine/tectonics.cpp:1624-1629` |
| `ocean_fraction_target` as a sea-level control | **It is not.** It is a diagnostic area reference; the solve is constrained by `ocean_water_inventory_km3` only | `README.md:352`, `src/magic_geo/config.py:209-214` |
| Exact ocean-inventory closure | **Not claimed.** The sweep only tests interval endpoints and the analytic in-interval level, keeps the smallest `abs(volume − target)`, and publishes the residual as `ocean_water_inventory_error_km3` | `cpp/src/engine/ocean.cpp:102-125, 157-181`, `src/magic_geo/geo_validation.py:1339` |
| Subcell bathymetry, straits, or exact coast polygons behind the marine mask | **Not represented.** Declared in the model contract itself | `sea_level_model.model_limitation = cell_column_volume_without_subcell_bathymetry_straits_or_exact_coast_polygons` |
| The configured ocean inventory as a total-water partition | **False.** It is an ocean allocation, not a partition across ocean, ice, groundwater, lakes and atmosphere | `GEO_MODEL_LIMITATIONS`, `src/magic_geo/geo_validation.py:31` |
| Layer-contract passage as empirical realism | **False for every layer.** `relief_bathymetry` and `sea_level_ocean` both hardcode `empirical_realism_proven: False` | `src/magic_geo/geo_layer_contracts.py` |
| Accelerator parity for crust transport (the upstream root of the equilibrium operands) | **False.** OpenCL/CUDA may only validate and discard a continuous-moment CSR shadow; CPU stays authoritative | `cpp/src/engine/README.md:294-303` |

The consolidated statement carried in every geo-validation report is `GEO_MODEL_LIMITATIONS[7]` (`src/magic_geo/geo_validation.py:36`), reproduced verbatim:

> the continuity-adjusted Parsons-Sclater relation is authoritative only for a relative oceanic thermal-subsidence target curve; full local thermal and isostatic equilibrium target differences now replay into terrain outside the bounded dynamic-relief clamp, but the quasi-static timescale separation is not a calibrated transient relaxation and the model does not separately track realized thermal relief or resolve absolute basement depth, heat flow or thermal structure, dynamic topography, flexure, or physical dynamics

### Documentation/source discrepancies observed

- `src/magic_geo/geo_validation_physics.py:2620` lists `"initial_thermal_aliases_replayed": True` in the check's `expected` map, but the metrics dictionary produced by `validate_oceanic_age_depth` uses the key `initial_thermal_checkpoint_replayed` (`src/magic_geo/oceanic_age_depth_validation.py:1218, 1725`). The `expected` map is declarative only — the check's pass/fail comes from `oceanic_age_depth["passed"]` — so this is a naming mismatch between the declared expectation and the reported observation, not a behavioural defect. Reported as observed; no fix is implied here.
- `cpp/src/engine/numeric_serialization.cpp` is not listed in the engine README's source-responsibility table (`cpp/src/engine/README.md:33-102`), even though it owns the `roundtrip_num` contract this page depends on.
- The key `continent_landmass_count` is used for two different quantities. `src/magic_geo/sea_level_diagnostics.py:364` writes `world["summary"]["continent_landmass_count"]` as the number of landmasses with `island_class == "continent"`; `extract_geo_metrics` writes a validation metric of the same name as `len(world["landmasses"])` (`src/magic_geo/geo_validation.py:492`). Both are correct against their own definitions; only the name is shared. Reported as observed; no fix is implied here.

---

## See also

- [Tectonics and Plates](tectonics-and-plates.md) — plate rotation, boundary classification, and the ordered crust process rules that move the equilibrium targets
- [Crust Transport and Forward Overlap](crust-transport-and-overlap.md) — the `crust_overlap_ledger` remapped state that is the authoritative operand root for every equilibrium replay
- [Plate Boundary Segment Ledger](plate-boundary-ledger.md) — exact directed segment kinematics and the explicitly unknown physical polarity
- [Crust Material Shadow and Dry-Rock Reservoirs](crust-material-and-reservoirs.md) — the non-authoritative mass shadow and three-reservoir counter-model
- [Mesh and Geometry](mesh-and-geometry.md) — control-volume areas and the ~400 km cell scale that bounds the shelf problem
- [Oceans, Currents and Coasts](oceans-and-coasts.md) — downstream consumers of the marine mask, shelves and chokepoints
- [Sediment, Routing and Stratigraphy](sediment-and-stratigraphy.md) — the bedrock/mobile interface primitive that applies the tectonic displacement
- [Erosion, Maturation and Landscape Evolution](erosion-and-maturation.md) — the maturation loop, the nominal timestep scale, and the combined terrain commit
- [Hydrology, Rivers and Lakes](hydrology-and-rivers.md) — the stabilization loop that re-invokes the sea-level solver
- [Native Engine (C++ Core)](../08-native-engine.md) — translation-unit responsibilities and stated invariants
- [World Document Schema](../10-world-schema.md) — full key inventory for `oceanic_age_depth_model`, `sea_level_model`, `plate_kinematic_model`, and `plate_motion_history[]`
- [Serialization and World Formats](../11-serialization.md) — `roundtrip_num` versus display precision and the MessagePack transcoding boundary
- [Validation](../12-validation.md) — how `tectonics.oceanic_age_depth_thermal_target_replay` and the `sea_level` domain checks compose into a report
- [Geo Validation Suite](../13-geo-validation-suite.md) — scenario matrix, determinism reruns, and paired physical responses
- [Calibration Against Real-Earth Data](../14-calibration.md) — external empirical targets including the Seton oceanic-age CDF
- [Configuration Reference](../05-configuration-reference.md) — `planet.ocean_water_inventory_km3`, `planet.ocean_fraction_target`, `erosion.maturation_timestep_ma`, `erosion.tectonic_uplift_scale`
- [Glossary](../21-glossary.md) — oceanic-like, quasi-static, nominal time, equilibrium target
