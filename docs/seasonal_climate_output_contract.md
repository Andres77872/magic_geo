# Native seasonal climate output contract and Python migration

**Status: native generation, C ABI V4, explicit version-2 Python/YAML access, independent certificate validation and atomic annual aggregation are implemented.** Inventory date: 2026-09-09. The [native integration record](seasonal_climate_native_integration.md) identifies interfaces and test scope. Current Python/C++ defaults, built-in profiles and workbench templates now select the seasonal model. All YAML requires exact integer version 2; old C ABI versions and explicit `LegacyWorldConfig` preserve their original model. Broad default-scenario acceptance remains under review.

The integration constraints and numerical evidence are in [research §7](seasonal_energy_balance_model_research.md#7-native-integration-map-and-temperature-contract-migration) and [research §11](seasonal_energy_balance_model_research.md#11-adaptive-methods-at-the-same-monthly-verification-gate). Configuration and default-profile migration are tracked separately in [the migration plan](seasonal_climate_migration_plan.md). Sections 1–4 describe native evidence; section 5 describes implemented Python aggregation, and section 6 records consumer dispatch. Unexported trajectory and geometric-edge reconstruction remain outside the serialized certificate's verification scope.

## 1. Ownership and state lifetime

The native solver must own the coefficients, forcing, accepted trajectory and budgets that produce temperature. Python may verify or aggregate that evidence, but must not replace it with a different radiation model.

`EarthSystemState::climate_cache` owns a final `PrescribedSeasonalClimate`: actual column inputs, conservative transport edges, prescribed solar interval schedule, accepted thermal partition/method/options, monthly solution and convergence evidence. It replaces the retained state only after a successful solve. Any relevant input change requires a new solve; a completed earlier terrain-correction pass is not evidence for the final surface.

The state must survive the last numeric-depression stabilization and glacial terrain mutation through world serialization. A repeated `compute_climate` call solves a new periodic boundary-value problem for that pass; it is not the next year of an ongoing transient simulation. Geometry caches may survive unchanged topology, but coefficient-dependent storage, opacity and conductances need invalidation when their inputs change.

[`world_serialization.cpp::serialize_world`](../cpp/src/engine/world_serialization.cpp) dispatches the explicit seasonal selection to metadata and budget serializers receiving the retained state. Only legacy selection calls `climate_model_json(params)`; that helper rejects seasonal selection. Seasonal rainfall's multiplier and reported mean are derived from the retained solution, while the legacy helper retains its original `Params` interpretation.

Store source classifications used at solve time, such as the marine mask and prescribed material class. Final lake/ice/biome labels are not substitutes for those inputs. The initial prescribed-coefficient model must declare which surface feedbacks it omits. If a later coupled model changes those assumptions, version its input snapshot and replay contract accordingly.

## 2. Minimum evidence layout

One canonical native-owned record per cell avoids independent copies of the same physical budget. Existing cell-level scalar layers may mirror derived annual values, with validation enforcing that correspondence.

| Native location | Required content |
| --- | --- |
| `climate_model` | New temperature/model identifier; explicit physical parameter meanings; precipitation dependency on the solved climate; distinction from the legacy latitude/mean-centering model. |
| `climate_energy_model` | Budget schema/version; native ownership; radiation/coefficient formulas and constants; coefficient-source policy; method identifier; calendar/year and monthly durations; solar quadrature version and `forcing_refinement_level`; solver/periodic tolerances; accepted effective solver options; achieved phase/annual-flux residuals; local/monthly adaptive verification results and their limitations. |
| `climate_energy_forcing_intervals` | Ordered shared parent intervals: month index, duration in seconds, declination in radians, effective inverse-square distance factor, and accepted physical thermal subdivision count. Preserve source and thermal refinements separately. |
| `climate_energy_transport_edges` | Unique undirected pairs with first/second cell IDs and conductance in W/K. These expose the actual conservative graph without requiring a validator to import native construction code. |
| `climate_energy_balance_records` | Unique `cell_id`; native latitude in radians, area in m², heat capacity in J/m²/K, effective TOA albedo and effective longwave coefficient; captured coefficient-source classification; 13 monthly boundary temperatures in K; 12 mean temperatures in K and mean fourth powers in K⁴; monthly ASR, OLR, transport convergence, storage tendency, physical residual and numerical allowance. |
| Existing `cells[].temperature_c` and `temperature_monthly_c` | Annual and monthly temperatures derived from the accepted native means, retained as the downstream consumer interface. They must not be overwritten by Python diagnostics. |

The effective longwave coefficient must be distinguished from a material's surface emissivity. For the proposed gray law, `I=σT⁴/(1+3τ/4)`; record the actual opacity mapping and coefficient. If surface emissivity is separately introduced, its convention must appear consistently in the producer and replay.

Column coefficients are authoritative inputs to the solve, but their declaration is not sufficient proof of correct physical construction. A separate independent coefficient check should reconstruct them from the versioned policy, explicit physical controls and captured source state. Never reconstruct solved albedo from later biome/cloud/ice diagnostics. Never use ocean-fraction targets or default areas in place of actual geometry and the accepted marine mask.

Mean `T³` can be retained for solver diagnostics and the periodic preconditioner. It is not required for the final monthly physical-budget identities. Per-substep stage temperatures are likewise not mandatory in the compact output if independent forward replay reconstructs them; exporting every stage for every cell would be a much larger optional audit artifact.

## 3. Monthly identities and their limits

For each month of duration `Δt`, let `A_i`, `C_i`, `α_i`, `ε_i` and symmetric `G_ij` be fixed over the cycle. Let `T̄_i` and `overline(T_i⁴)` use the accepted method's quadrature. Independent monthly checks are:

\[
\mathrm{ASR}_{i,m}=(1-\alpha_i)\frac{\sum_{k\in m}h_k S_{i,k}}{\Delta t_m},
\qquad
\mathrm{OLR}_{i,m}=\epsilon_i\sigma\overline{T_i^4}_m,
\]

\[
H_{i,m}=\frac{1}{A_i}\sum_jG_{ij}(\overline{T_j}_m-\overline{T_i}_m),
\qquad
S^{\mathrm{storage}}_{i,m}=C_i\frac{T_{i,m+1}-T_{i,m}}{\Delta t_m},
\]

\[
r_{i,m}=S^{\mathrm{storage}}_{i,m}-(\mathrm{ASR}_{i,m}-\mathrm{OLR}_{i,m}+H_{i,m}).
\]

The transport identity follows because the fixed graph operator is linear and both cells use the same accepted time quadrature. It does not apply to independently selected per-cell step methods or a temperature-dependent conductance without further evidence.

Check unique IDs and complete coverage, finite positive areas/capacities/durations, valid coefficient ranges, nonnegative temperatures/moments, positive edge conductances, no duplicate/self edges, contiguous boundaries, mean-moment convexity, and exact parent-fluence accounting within justified arithmetic bounds. The source sum must use the accepted parent intervals, including unequal durations.

Global transport must cancel separately from global radiation/storage. Annual quantities are duration-weighted sums of monthly budgets, with physical area weighting for planetary means. At a periodic solution, check both the phase-boundary temperature difference and actual integrated annual net heating. Small temperature change alone can conceal substantial heating when capacity is enormous. Do not normalize insolation or re-center temperatures to obtain closure.

**These monthly identities prove consistency of the published ledger, not the complete integrator trajectory.** Coordinated changes to a moment and its radiation field could pass a monthly identity. Exact BE/TR-BDF2 replay additionally requires independently forward-integrating from the published initial phase under the declared coefficients, source nodes, method and fixed partition, then comparing boundaries, moments and every flux. Use separate formulas/implementation rather than importing the producer's solver.

BE uses its accepted endpoint quadrature. TR-BDF2 uses its declared stage weights, with `γ=2−sqrt(2)` for the implemented candidate. Step-doubling acceptance must correspond to the same physical half steps used in shooting and serialization. Reject-stage work must not enter any physical integral. A partition or method change requires a fresh periodic solve and reset correction history.

Numerical uncertainty is not a balancing heat source. Preserve the actual signed residual, and separately report propagated solver/representation allowances. An independent validator must not accept arbitrary inflated producer tolerances as proof; derive its allowance from the declared numerical policy and replayed quantities. Monthly refinement differences are an observed convergence criterion, not by themselves a certificate of absolute error below floating-point uncertainty.

## 4. Precision and actual astronomical forcing

[`entity_serialization.cpp::cells_json`](../cpp/src/engine/entity_serialization.cpp) currently formats annual and monthly Celsius temperatures using `output.float_precision`. That setting is unsuitable for native energy witnesses. With `C≈2e11 J/m²/K`, rounding a monthly boundary by `5e−5 K` changes reconstructed storage by several W/m², far exceeding the solver's ordinary tolerance.

Use round-trip double serialization for all authoritative temperatures in K, moments, boundaries, coefficients, conductances, source nodes, durations, residuals and allowances, independent of display precision. The existing [`numeric_serialization.cpp`](../cpp/src/engine/numeric_serialization.cpp) helpers provide this convention. Preserve it through JSON and MessagePack. If rounded display aliases remain, label their precision and compare them under an explicit rounding rule; do not use them for energy replay.

[`SolarOrbitForcing`](../cpp/src/engine/solar_insolation.hpp) exposes both a Python-compatible monthly API and a separate physical integration interval schedule. The latter obeys angular and elapsed-time limits and now has an explicit `integration_refinement_level`. The new output must describe the schedule actually used by the thermal solve. Recomputing monthly source terms through the existing post-hoc monthly API is not evidence that the same parent fluences were used.

Each shared interval node and the native latitude can reconstruct its prescribed sunlight with the declared daily-mean formula, stellar luminosity and solar constant. Multiplication by the captured albedo gives ASR. This avoids serializing an interval-by-cell sunlight array. Independently verify the node schedule against the orbital parameters and quadrature convention as a separate check, so a self-consistent but incorrect source schedule is detectable.

The independent review replayed about 20,000 exported nodes across ordinary and near-parabolic eccentricities through Python's daily-mean geometry with bit-identical flux at the tested latitude. This verifies the compact-node interface, not compatibility with the old monthly quadrature. Following the native near-apoapsis precision correction, its integrated monthly distance factors can differ from the deliberately unchanged legacy monthly factors by about `1.27e−7` relatively. The independent high-precision oracle is [`scripts/research/solar_orbit_reference.py`](../scripts/research/solar_orbit_reference.py). Publish the actual latitude in radians as an authoritative coefficient input; display-degree conversion should not define the replay geometry.

Thermal children retain their parent's mean sunlight; their durations must cover the parent without omission. Astronomical refinement recomputes parent nodes/fluences and is a separate accuracy dimension. Record both refinements. Do not silently apply the old diagnostic's luminosity floor of 0.01 to native forcing.

## 5. Strict Python dispatch and existing collisions

[`api.py::_enrich_physical_foundation`](../src/magic_geo/api.py) currently runs ocean circulation, continentality and seasonal diagnostics before `enrich_world_with_climate_energy_balance`. The latter must dispatch on explicit known model/version identifiers:

- Legacy temperature model: retain its legacy post-hoc diagnostic and existing replay under the matching declaration.
- Native seasonal model: require complete native evidence, preserve it, and compute summaries/mirrors from that evidence.
- Missing, inconsistent or unsupported native model/evidence: fail explicitly. Do not silently invoke the legacy diagnostic to fill missing native fields.

The dispatch in [`climate_energy.py`](../src/magic_geo/climate_energy.py) sends native envelopes to [`native_climate_energy.py`](../src/magic_geo/native_climate_energy.py). Complete independent budget validation occurs before any mutation. Partial/unknown native envelopes, undeclared existing native mirrors and known legacy energy aliases are rejected. The native model, forcing, edges, records, climate declarations and temperature aliases retain both identity and value. Idempotent repetition is allowed only under the exact separate `native_climate_energy_enrichment_model` declaration.

Native cell mirrors are `effective_toa_albedo`, `effective_longwave_emissivity`, `annual_absorbed_shortwave_w_m2`, `annual_emitted_longwave_w_m2`, `annual_net_radiative_flux_w_m2`, `annual_horizontal_heat_convergence_w_m2`, `annual_net_heating_w_m2`, `annual_heat_storage_tendency_w_m2`, `annual_energy_balance_residual_w_m2`, `annual_mean_abs_energy_balance_residual_w_m2` and `annual_mean_energy_balance_numerical_allowance_w_m2`. Annual fluxes use actual native monthly durations. Signed net radiation is ASR−OLR; net heating additionally includes horizontal convergence; the residual is storage−net heating. The numerical allowance remains a tolerance, never a heat source.

Every mirror has a `cell_count_mean_{field}` and `area_weighted_mean_{field}` summary. Three additional fields are `native_climate_energy_record_count`, `native_climate_energy_total_area_m2` and `native_climate_energy_year_duration_seconds`. Extended-precision accumulation avoids intermediate finite-product overflow and loss of small signed budgets during extreme cancellation; unrepresentable final output fails before commit. The CSV appends all 11 fields after the existing 407 columns, and Markdown includes all 25 summaries. Missing legacy fields remain blank rather than becoming zero.

For legacy payloads, the same function continues to write annual insolation, albedo, ASR, OLR, greenhouse trapping, net balance, equilibrium-temperature diagnostics, stress, model metadata and per-cell records. Its `_surface_albedo` depends on final biome, ice, water/lake classification, temperature, precipitation, aridity, vertical motion and elevation. `_greenhouse_effect_c` also depends on humidity, current moisture, evaporation and water/ice diagnostics. These are not the prescribed coefficients that produced the new native temperature.

| Existing field | New-model collision / required policy |
| --- | --- |
| `surface_albedo_index` | Current post-hoc surface/cloud mixture must not overwrite solved effective TOA albedo. Prefer an explicit native coefficient name such as `effective_toa_albedo`; keep any later diagnostic separately named. |
| `absorbed_shortwave_w_m2`, `outgoing_longwave_w_m2` | Annual mirrors must be time means of the accepted monthly/source budgets. In particular, OLR is proportional to mean `T⁴`, not the fourth power of annual mean temperature. |
| `greenhouse_trapping_w_m2` | Opacity already reduces effective OLR. Adding this old positive source to new ASR−OLR would double-count greenhouse effects. A counterfactual longwave-reduction diagnostic needs a separate definition/name. |
| `net_radiative_balance_w_m2` | For the new model this is ASR−OLR, distinct from net heating including transport and from the residual after storage. Version the interpretation. |
| `energy_balance_residual_c` | Currently temperature disagreement with a post-hoc equilibrium. Never reuse it for a solved W/m² equation residual. |
| `radiative_equilibrium_temperature_c`, `no_greenhouse_equilibrium_temperature_c` | Static counterfactual diagnostics are not the periodic transported solution. Remove them from the new solver record's mandatory schema or retain them only in a separately declared diagnostic. |
| `climate_energy_stress_index` | Currently disagreement with the post-hoc model, not numerical convergence or physical seasonal stress. Its downstream consumers require explicit migration. |

Legacy [`reef_diagnostics.py`](../src/magic_geo/reef_diagnostics.py) and [`wildfire_disturbance.py`](../src/magic_geo/wildfire_disturbance.py) branches retain `climate_energy_stress_index`. Explicit native branches now omit that input without substituting a numerical residual: native wildfire removes its 0.06 stress contribution without renormalization; native reef removes the entire unsupported bleaching proxy and declares that estimate unavailable. The [ecology note](seasonal_climate_ecology_migration.md) gives exact versions, equations, tests and remaining limitations.

Annual summaries should retain declared count-based compatibility means separately from physical-area means. Add transport, storage and actual residual aggregates under unambiguous names. Do not carry old greenhouse-source or Celsius-mismatch summary requirements into the new physical-budget contract.

## 6. Validator and presentation migration surface

The native branch is now implemented in the physics replay, full CLI preflight and geo contract checks below. Native physical replay runs before any legacy eager consumer, and optional annual mirrors receive an independent exact-rational replay after the certificate passes. That second check allows raw native state but rejects undeclared, incomplete or tampered mirrors/metadata, using fixed binary64-roundoff comparisons independent of native solver allowances. The imposed-mean-temperature check is explicitly not applicable to the native model. Unknown/mixed identities are failures, not compatibility fallbacks.

The actual full public version-2 world passes the CLI consistency gate. Its geo-only companion passes the generic `validate-geo` gate with 151 checks, no errors/warnings and three not-applicable checks. Use the full validator for full worlds and `validate-geo` for natural-only scope; missing human layers are not supplied as placeholders.

| Source | Existing assumption to replace or dispatch |
| --- | --- |
| [`geo_validation_physics.py::_validate_climate_energy`](../src/magic_geo/geo_validation_physics.py) | Exact legacy model-dictionary equality; separate insolation/albedo/greenhouse calculation; fixed emissivity 0.96; legacy annual field/record/summary replay. Add an independently implemented native-budget branch and reject unknown versions. |
| [`geo_validation.py`](../src/magic_geo/geo_validation.py) climate checks | Old temperature model/mean identity and records requiring greenhouse trapping plus a Celsius residual. Gate these checks by model and validate native evidence coverage separately. |
| [`cli/commands/validate.py`](../src/magic_geo/cli/commands/validate.py) temperature-model block | Requires base temperature, lapse and old thermal-moisture metadata; reconstructs the old formula. Dispatch to the new equation and solved precipitation dependency. |
| Same CLI, later climate-energy record block | Independently requires the old summary/record fields and cell mirrors, even if the physics validator changes. Migrate this block too, or it will reject correct native budgets. |
| [`geo_layer_contracts.py`](../src/magic_geo/geo_layer_contracts.py) | Requires climate-energy records for the natural climate layer. Preserve truthful availability and method-appropriate evidence requirements. |
| [`io/cells_csv.py`](../src/magic_geo/io/cells_csv.py), [`io/summary_markdown.py`](../src/magic_geo/io/summary_markdown.py), [`debug_ui/layer_docs.js`](../src/magic_geo/debug_ui/layer_docs.js) | Names and descriptions currently mix legacy surface, greenhouse-source and diagnostic-equilibrium meanings. Add the native budget fields and update descriptions with model/version semantics. |

The public full-world Python API already forces native cells to be included while enriching, then applies the caller's output suppression afterward. Keep this prerequisite behavior. Direct native summary-only output must declare when per-cell replay evidence is omitted; unavailable evidence cannot produce a successful full replay verdict.

## 7. Circular and stale dependency checks

Temperature drives precipitation/evaporation, which influence later aridity and biome diagnostics. Feeding those diagnostics back into the claimed original albedo or opacity would introduce an undeclared climate fixed point. Lakes are reconstructed after runoff/routing; final ice and biome diagnostics are also downstream of climate. Their final values cannot prove which coefficients were used earlier.

The existing current-temperature descriptor is an additive empirical term in the old model. Do not add it after the new conservative thermal solve; retain it only as a clearly defined circulation diagnostic unless its heat transfer is explicitly represented in the solved graph. Likewise, the new solved mean used by an empirical rainfall factor must be computed before rainfall consumers, and serialized from the same accepted state.

Integration tests should verify that later lake/ice/biome diagnostic mutations cannot change stored native coefficients or budgets, while a change in the actual marine/material/geometry input does trigger a new solve. Tamper independently with source nodes, coefficients, edge conductances, boundary temperatures, moments, fluxes, allowances, metadata and summaries. Test JSON/MessagePack and low display precision, both integrators, rejected-step isolation, area-weighted cancellation, initial-guess independence and missing/unknown-model refusal. Those checks establish the contract; they do not resolve unmodeled lake/ice feedback or broader physical applicability.
