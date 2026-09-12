# Supplied layered initial state on finalized geography

`finalized_supplied_layered_state_v1` connects the immutable geographic foundation to a newly owned layered thermodynamic state. Every geographic footprint receives an explicitly supplied water inventory and either whole-node enthalpy or equilibrium temperature plus liquid mass. The initializer binds those inputs to the captured physical coefficients, accounts for their conversion error, and submits the resulting state to the actual owner constructor.

The first fixed controls, fresh foundation integration and independent arithmetic audit pass. This establishes an initialization contract; it does not infer a glacier profile from annual temperature or ice thickness, perform spin-up, certify imported observations, advance time, or publish layered results into ordinary generation.

## Scientific basis

Temperature alone is insufficient at the melting point: states with different liquid fractions have the same temperature and different stored energy. Aschwanden et al. formulate mixture enthalpy using solid and liquid energy and recover temperature and liquid fraction from enthalpy and pressure. Their local-equilibrium formulation includes pressure-dependent melting. It supports the choice of energy and liquid inventory as state information; it does not validate this repository's simpler constant heat capacities, prescribed common freezing temperature, or warm-liquid extension.[^1]

PISM exposes initialization from enthalpy or temperature and liquid fraction, and its enthalpy converter checks thermodynamic consistency. Its ice-specific admissible range and tolerances are model choices. The local initializer therefore uses explicit tags and its own declared phase branches rather than silently choosing between overlapping fields or adopting another model's tolerances.[^2]

Supplying a state and deriving a state are separate modeling operations. PISM distinguishes interpolation and heuristic completion during bootstrapping from subsequent evolution. SICOPOLIS requires an explicit temperature initialization method alongside initial geometry, with choices including constant temperature, depth-dependent profiles and previous output. Neither model treats geometry alone as a unique thermal initial condition.[^3][^4]

Spin-up also has its own physical assumptions. The Community Firn Model first evolves density, temperature and other properties during spin-up, then starts the transient simulation with different forcing. GEMB identifies spin-up climatology, duration and vertical resolution as important sources of sensitivity. These studies support retaining profile provenance and defining any future equilibration procedure separately; they do not supply a universal spin-up duration or show that a manufactured profile represents observed ice.[^5][^6]

CTSM's soil/snow heat capacity includes the contributions of solids, liquid and ice; its unresolved-snow treatment adds capacity to the existing top layer. This motivates explicit constituent accounting. CTSM also documents additional thermal equilibration after adding excess ground ice. Neither result turns the repository's combined atmosphere/surface node into a resolved snow–air interface.[^7][^8]

## State and energy convention

The following equations describe the local model implemented in [finalized_layered_state.cpp](../cpp/src/engine/finalized_layered_state.cpp), with the interface declared in [finalized_layered_state.hpp](../cpp/src/engine/finalized_layered_state.hpp). They are a derivation for the repository's coefficients and coordinates, rather than a claim that the cited models use the identical closure.

| Operand | Meaning |
|---|---|
| A | Canonical geographic footprint, m² |
| W | Supplied water mass per complete footprint, kg/m² |
| H | Complete node enthalpy relative to the freezing reference, J/m² |
| C | Prescribed capacity outside the separately tracked phase-changing water reservoir, J/(m² K) |
| T, Tf | Absolute temperature and prescribed freezing temperature, K |
| l | Supplied liquid water mass per footprint, kg/m² |
| ci, cl, Lf | Solid/liquid specific heat capacities and latent heat |

Each active layer supplies W, positive density, positive conductivity, and exactly one state encoding. Deep storage supplies W, positive density and an energy encoding; it lies outside the thermal graph under the declared insulated boundary. Density determines thickness W/rho. It does not create a second inventory from independently inferred thickness.

Direct-enthalpy mode requires finite H and no temperature/liquid operands. H includes the background top capacity exactly once, and negative H is valid cold content. The implementation copies the supplied binary64 value, including signed zero, so this representation change is an identity with zero additional enthalpy error.

Equilibrium-temperature mode requires both T and l and excludes a simultaneous H. It requires finite T >= 0, W >= 0 and 0 <= l <= W. Below Tf all water is solid; above Tf all water is liquid; at Tf the explicit l selects the stored latent energy. Comparisons use the supplied binary64 operands exactly, with no snapping of nearby temperatures to Tf. The exact target on those operands is

\[
H^*=\begin{cases}
(C+Wc_i)(T-T_f), & T<T_f,\quad l=0,\\
lL_f, & T=T_f,\\
WL_f+(C+Wc_l)(T-T_f), & T>T_f,\quad l=W.
\end{cases}
\]

The context's combined surface/atmosphere C belongs only to the top active node. Interior and deep water use C=0. Supercooled liquid, superheated solid, pressure-dependent melting and nonequilibrium phase kinetics would require different model contracts.

For a sole W=0 top with positive C, l must be zero and the law becomes H=C(T−Tf). An empty deep W=C=0 record has no temperature; it may be represented as direct W=H=0 bookkeeping, with no error-ball coordinate. Tagged temperature for that empty deep record refuses instead of inventing Tf as its state.

Marine and lake cells have an additional restriction: they are sole W=0 sensible slabs with no positive deep water. Their context capacity already represents a prescribed sensible water slab plus atmosphere. Thus the downstream name `nonwater` means outside the separately tracked phase reservoir, not literally devoid of water. Keeping this slab out of W avoids double counting and makes explicit that initialization does not supply sea or lake ice.

The existing [column builder](../cpp/src/engine/layered_ice_column.cpp) also refuses an empty pure-water active layer, a dry top above additional active layers, and a dry top over positive deep inventory. The last rule is a current representation limitation, not a thermodynamic consequence of insulating the deep boundary.

## Canonical conversion and the shared error bound

Canonical W and matched context coefficients are retained unchanged. For tagged temperature, the implementation computes a represented binary64 candidate Hhat and an independent outward enclosure of the exact target H*. It retains the supplied operands, phase branch, represented intermediates, ideal enclosure and projection difference. Correct rounding of Hhat is not claimed or needed.

For each active or positive-deep coordinate k, let

\[
\Delta_k\supseteq\{\widehat H_k-H_k^*\},\qquad
D\ge\sum_k A_{i(k)}\sup|\Delta_k|,\qquad
E_0\ge E_{\mathrm{supplied}}+D.
\]

The implemented products, sum and final addition round outward. The inherited allowance is added once across the complete state. An all-direct-H request has D=0 and preserves the inherited allowance through the zero-addition shortcut. The corresponding area-weighted L1 statement is

\[
\sum_k A_{i(k)}\,|\widehat H_k-H_k^{\mathrm{reference}}|\le E_0,
\]

conditional on the supplied profile already satisfying its declared inherited bound at the canonical W and coefficients.

That condition is material. The initializer proves its own conversion arithmetic; it cannot establish the accuracy of imported observations or a supplied error estimate. Neither E0 nor D bounds uncertainty in W, density, geometry, conductance or physical closures. E_supplied=0 specifies an exact mathematical input under the chosen model, not an observation without uncertainty. Converting future extensive masses or measured thicknesses into W would need a separate mass-projection contract.

Graph diagnostics for rounded extensive totals, thickness and resistances remain separate from this coordinate projection charge. Canonical A, W and H define the modeled state. Charging their diagnostic extensive-product differences again would duplicate an error allowance without changing those state coordinates.

The actual owner constructor checks the complete final E0 against every active and positive-deep coordinate, including otherwise unchanged direct-H records. In exact notation the necessary physical floor is

\[
C_s=C+Wc_i>0,\quad C_l=C+Wc_l>0,\qquad
\widehat H_k-E_0/A_{i(k)}\ge -(C+Wc_i)T_f.
\]

The implementation uses outward E/A and H boxes and an upper bound on the floor. A local conversion charge is insufficient for this check: another layer's conversion can enlarge the common bound enough to invalidate a cold deep coordinate. Near absolute zero, a nonzero error radius or outward arithmetic slack can justify conservative refusal. The initializer never clips H, T or E to obtain admission.

The builder separately requires finite latent storage and initial temperature evaluation, with strictly positive outward solid and liquid capacities. This can reject mathematically finite extreme inputs. In particular, a subnormal water capacity may leave a representable enthalpy conversion but make the existing reciprocal-based interval temperature evaluation overflow. Such a request retains its completed conversion evidence and refuses; the initializer does not silently weaken the graph's arithmetic contract.

## Geographic binding and atomic admission

The [geographic foundation](geographic_foundation_calendar_research.md) is an early immutable boundary after final hydrologic stabilization, before the last grounded-state overwrite and downstream natural/social derivation. Its [initialization method](../cpp/src/engine/finalized_layered_foundation.cpp) obtains the enthalpy context and routing graph from the same private source and invokes the factory. It advances no layered physical time and does not finish ordinary generation.

The factory requires equal context, routing and observed revisions, plus both `context.matches(observed, params)` and `routing.matches(observed)`. Revision equality alone is insufficient. The [context](../cpp/src/engine/finalized_enthalpy_context.cpp) binds geometry, original climate/soil and lake spill/fill operands; the [routing graph](../cpp/src/engine/seasonal_liquid_routing.cpp) also binds receivers, conditioned surfaces and routing classes. The receipt retains the union of those actual observed operands. Original climate remains source provenance and is not substituted for supplied H or T.

Profiles cover every geographic cell exactly once through a complete permutation. Request order defines local columns; active layer IDs remain complete and ordered. For local column i mapped to geographic p[i], A, C and emissivity come from context[p[i]]. Horizontal edge endpoints are transformed by the inverse permutation, returned to canonical endpoint order and sorted while retaining each conductance. The owner rechecks canonical area and actual geographic adjacency.

Initial absorbed shortwave is an explicitly named S=0 unforced placeholder. It is neither an insolation estimate nor a forcing interval. A later thermal request still needs its own authenticated forcing and clock operands.

Admission returns a newly constructed owner and its immutable snapshot together. Its revision is zero, and forcing, consumed-event and pending-parcel histories are empty. An explicit start time does not restore transaction history. The retained context, routing graph and owner remain owned after the geographic foundation is destroyed. Initialization itself leaves the foundation and its publication flags unchanged.

Raw profile, layer, identifier and geographic geometry caps precede rich input retention. Completed conversions and canonical input are retained before the one owner-construction attempt so later refusals remain inspectable. Work distinguishes a started constructor from a completed return; a failed constructor's exact internal build count is not invented. A refusal returns no usable private owner or final snapshot.

The complete receipt has a JSON wire-size cap. If a constructed owner's receipt exceeds it, the owner is discarded and fixed exempt failure metadata retains the observed work. This is a retained-wire contract, not a bound on transient encoding allocations, all structured objects or process RSS. The separate owner history and private-retention contracts continue to apply.

## Qualification

The fixed [driver](../cpp/tests/finalized_layered_state_test.cpp) passes **204 checks over 63 requests: 11 accepted states and 52 refusals**. It uses one new 12-cell geodesic mesh, actual context coefficients and one routing capture, with manufactured water constants and explicitly supplied profiles. Coverage includes direct bits, cold/plateau/hot conversion, permutations, inconsistent phases, wet/dry/empty-deep rules, shared-E admission, overflow/underflow, source changes and bounded refusal retention. The 20 owner-constructor starts yield 12 completed returns; one returned owner is then discarded by the receipt cap. The eight failed constructors retain their attempted-call evidence without claiming observed internal graph counts. Every returned constructor records one graph build and zero physical advancement.

The shared-E control reaches the actual owner's `uncertain_physical_domain` gate. Exact rational inspection identifies only the intended unchanged geographic-cell-3 deep coordinate as crossing its physical floor. The subnormal control retains a nonzero enthalpy-projection defect before the existing graph evaluation refuses its reciprocal-capacity arithmetic. Neither control changes its inputs or acceptance expectation after outcomes.

One fresh geographic foundation with seed 424289, 128 cells, eight plates, zero erosion iterations, one CPU thread and a 7 m lake slab cap passes **all six integration checks**. It contains 80 marine cells, three lake cells and 45 dry cells. Reversed geographic IDs produce 173 active layers: land W=[2,3] kg/m² at T=[250,255] K, wet W=0 at T=280 K, all with explicit zero liquid mass. The conversion allowance is **182,122,143.81915367 J** across the complete planetary footprint; adding the supplied 1 J with outward rounding gives E0=**182,122,144.8191537 J**, within the unchanged 10¹² J budget. This is a conservative arithmetic allowance for the prescribed initial state, not measured climate or glacier error. Source state and publication flags remain unchanged, and both the receipt and owner survive destruction of the foundation.

The first frozen independent Fraction reader passes **358,333 structural, binding and arithmetic assertions over 619 retained conversion records**, including the 12 accepted initializations. It binds the exact inventory, source mutations, phase operands, canonical graph inputs, nominal operation order, projection enclosures, common error charge, exact domain floors, mapping and work routes. It does not independently rebuild context physics, graph geometry/conductances, builder outward representability or full receipt wire size, and it proves no differential-equation or original-profile accuracy claim. These assertion counts and native checks measure different scopes and should not be added as independent scientific coverage.

The full native library and new target build in an isolated CPU tree with empty build stderr. All 195 C++/CMake source pins and the reader remain unchanged after first outcomes; the installed library remains `fa17d36b6759b88b524ddcbd822eb025b6454d6356fe585f799fedd11b949731`. The [portable evidence package](../runs/finalized-layered-state-review/README.md) retains complete sources, the fixed protocol, first successful producer/audit outputs, earlier compiler-only setup failures and independent reviews. There is one new foundation execution and no layered thermal, material, calendar or completed-world execution; foundation generation still performs its existing upstream physical work. No historical scientific qualification was rerun.

## Remaining production dependencies

Initialization removes one missing handoff: a final geographic source can now be paired with an explicit canonical thermodynamic profile and submitted to owner admission. The following dependencies remain separate:

| Dependency | Required production contract |
|---|---|
| Profile provenance | Declare how W, density, conductivity and thermal state are obtained, what their supplied uncertainty means, and whether any separate spin-up has converged. Annual diagnostics are not an implicit replacement. |
| Complete forcing and sources | Bind the complete forcing calendar, material inputs, source identities, substep/retry limits and global error shares before evolution; initialization's S=0 supplies none of these. |
| Material delivery | Select physical drainage/refill/export and recipient policies. Existing prescribed same-owner parcel absorption preserves saved energy but does not establish hydrologic destination authority or cross-owner delivery acknowledgment. |
| Domain and topology | Preserve top background capacity, canonical mass scope, phase availability and the shared E bound through complete ablation, topology changes and retained deep storage. Unsupported topology must remain a typed refusal. |
| Full-horizon retention | Admit complete attempts, proofs, forcing/source histories, work and live/storage resources without dropping intervals, coefficients or failed diagnostics. Enough bytes does not imply numerical completion. |
| Publication and descendants | Assign one authoritative writer for evolved temperature, phase, grounded inventory and runoff diagnostics; publish them atomically against the captured source and derive every dependent natural/social output from that accepted state. |

The [proposed full-horizon storage plan](layered_full_horizon_storage_plan.md) is a distinct future implementation contract. Shared forcing and normalized snapshots do not eliminate full SDIRK/BE proof retention. Its proposed external store, lossless representation, complete pre-work capacity reservation and bounded read views must be implemented and qualified separately; initialization does not admit an annual run or change the existing history cap.

The current combined top node also remains a coarse physical closure. Resolving a separate snow–air boundary, pressure-dependent phase behavior, firn densification, water percolation or atmosphere feedback requires additional modeling and validation. Successful initialization alone cannot authenticate these missing mechanisms or make late legacy descendants consistent with an evolved layered state.

## Sources

Primary publications and official model documentation below support the scientific distinctions. Local implementation claims refer to the linked repository files and the [layered thermal model](layered_ice_thermal_research.md), [material evolution](layered_material_evolution_research.md), [geographic foundation](geographic_foundation_calendar_research.md) and [owner storage](layered_calendar_storage_review.md) documents. Online documentation was consulted on 12 September 2026; documentation versions and model-specific restrictions are not adopted as local defaults.

1. Aschwanden, A., Bueler, E., Khroulev, C., and Blatter, H. [“An enthalpy formulation for glaciers and ice sheets.”](https://iacweb.ethz.ch/doc/publications/andy3.pdf) *Journal of Glaciology*, 58(209), 441–457, 2012. DOI: 10.3189/2012JoG11J088. Section 2, equations 4–11: state variables and local-equilibrium interpretation.
2. PISM authors. [EnthalpyModel initialization API](https://www.pism.io/doxygen/classpism_1_1energy_1_1EnthalpyModel.html) and [EnthalpyConverter::enthalpy](https://www.pism.io/doxygen/classpism_1_1EnthalpyConverter_a03cc5817bb07623518436fe8c7d759f2.html). Official generated API documentation, undated. Supported input representations and converter restrictions.
3. PISM authors. [“Bootstrapping.”](https://www.pism.io/docs/manual/initialization/bootstrapping.html) Official model manual, online version. Distinction between input completion, heuristic initialization and subsequent evolution.
4. SICOPOLIS authors. [“6.2. Initial conditions.”](https://sicopolis.readthedocs.io/en/latest/modelling_choices/initial_conditions.html) Official documentation, online version. Independent geometry and thermal-profile initialization choices.
5. Stevens, C. M., et al. [“The Community Firn Model (CFM) v1.0.”](https://gmd.copernicus.org/articles/13/4355/2020/) *Geoscientific Model Development*, 13, 4355–4377, 2020. DOI: 10.5194/gmd-13-4355-2020. Sections 2.1 and 3.1: spin-up, transient forcing and profile assumptions.
6. Gardner, A. S., Schlegel, N.-J., and Larour, E. [“Glacier Energy and Mass Balance (GEMB): a model of firn processes for cryosphere research.”](https://gmd.copernicus.org/articles/16/2277/2023/) *Geoscientific Model Development*, 16, 2277–2302, 2023. DOI: 10.5194/gmd-16-2277-2023. Spin-up dependence and vertical-resolution sensitivity.
7. CTSM authors. [“2.6. Soil and Snow Temperatures.”](https://escomp.github.io/CTSM/tech_note/Soil_Snow_Temperatures/CLM50_Tech_Note_Soil_Snow_Temperatures.html) *CLM5 Technical Note*, official online documentation. Equations 2.6.88–2.6.92: constituent heat capacities and unresolved snow.
8. CTSM authors. [“Running with excess ground ice.”](https://escomp.github.io/CTSM/users_guide/running-special-cases/Running-with-excess-ground-ice.html) Official user guide, online version. Initializing added ground ice and thermal equilibration.

[^1]: Aschwanden et al. (2012), [section 2 and equations 4–11](https://iacweb.ethz.ch/doc/publications/andy3.pdf).
[^2]: PISM, [energy initialization](https://www.pism.io/doxygen/classpism_1_1energy_1_1EnthalpyModel.html) and [equilibrium converter](https://www.pism.io/doxygen/classpism_1_1EnthalpyConverter_a03cc5817bb07623518436fe8c7d759f2.html).
[^3]: PISM, [bootstrapping](https://www.pism.io/docs/manual/initialization/bootstrapping.html).
[^4]: SICOPOLIS, [initial conditions](https://sicopolis.readthedocs.io/en/latest/modelling_choices/initial_conditions.html).
[^5]: Stevens et al. (2020), [CFM workflow and applications](https://gmd.copernicus.org/articles/13/4355/2020/).
[^6]: Gardner et al. (2023), [GEMB model and sensitivities](https://gmd.copernicus.org/articles/16/2277/2023/).
[^7]: CTSM, [soil/snow heat-capacity equations](https://escomp.github.io/CTSM/tech_note/Soil_Snow_Temperatures/CLM50_Tech_Note_Soil_Snow_Temperatures.html).
[^8]: CTSM, [excess-ground-ice initialization](https://escomp.github.io/CTSM/users_guide/running-special-cases/Running-with-excess-ground-ice.html).
