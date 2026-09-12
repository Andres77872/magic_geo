# Seasonal thermal mesh and finite liquid routing

Seasonal glacier ablation needs a model of surface and subsurface ice, a practical time integrator, and a single conserved path from precipitation to retained water and downstream delivery. The current annual glacier diagnostic supplies none of those by itself. This review adds a represented SDIRK2 mesh integrator with a quadratic residual certificate and a finite-mass router on immutable terrain. Both are explicit internal components. Generated-world ablation, owner dispatch to the new integrator, and downstream seasonal publication remain unfinished.

The implementation is supported by two source reviews, a separate symbolic numerical review, fixed native controls, and independent arithmetic implementations. The arithmetic readers were written by the primary implementer; they are separate implementations, not independent-person implementation reviews. The original failed thermal control, its exact-constant correction, and a subsequent reader mutation-test correction are retained in the [evidence package](../runs/seasonal-mesh-routing-review/README.md). No closed annual or historical six-hour experiment was repeated.

## Physical state must precede integration

The annual constructor creates diagnostic ice only below −3 °C annual temperature, while its ablation expression requires temperature above −1.5 °C. Its thickness is therefore a static annual proxy with an unreachable positive-ablation branch for the ice it creates. A prescribed initialization may use that proxy only with an explicit origin, density, coverage, and temperature profile. It is not conserved historical ice or an equilibrium state.

The present mesh temperature law is

\[
T(H,W)=T_f+\frac{\min(H,0)}{C+Wc_i}+\frac{\max(H-WL_f,0)}{C+Wc_l}.
\]

Here C includes the prescribed mineral or water slab and combined atmosphere. W is additional retained water. Loading a kilometer of cold glacier ice into this single W makes the whole kilometer share the surface/atmosphere temperature and sensible heat capacity. With a uniform subfreezing initialization, all that cold content must warm before any modeled melting occurs. This observation is conditional: an initialization already at H=0 lies on the melting plateau and can melt immediately. Choosing H=0 solely to avoid the problem changes the initial thermal state.

The recommended next physical model owns snow/firn, thermally resolved upper ice, deeper ice, and exported water separately. Each resolved layer carries mass and enthalpy; vertical exchanges carry equal and opposite energy. Surface heat acts at the top. Deep ice must remain in a conserved inventory with an explicit lower boundary and remapping policy. Clipping W to an arbitrary active depth would lose mass and energy.

Layered conduction is a physical distinction, not just an implementation preference. CTSM resolves separate snow/soil temperatures and interface heat fluxes using layer thermal resistance. Its special treatment of very thin snow does not justify assigning an entire glacier one temperature.[^1] Glacier snow/firn energy models also distinguish retained liquid, refreezing, and runoff; particular layer counts and depths are model choices, not universal defaults.[^2] Spatial glacier enthalpy formulations likewise require surface and basal conditions and explicit phase/drainage assumptions.[^3]

A minimal extension could retain the current combined atmosphere/surface approximation only at a top thermal node, with separate underlying ice nodes. That would still be a coarse climate closure, not a resolved glacier surface energy balance. The atmospheric capacity must not be replicated at every depth. Pure ice layers also need Cbase=0 with W>0, whereas the current solver requires positive C and uses S/C in its physical upper bound. Layer admission, empty-layer removal, sources, remapping, and error propagation need new treatment before this extension is valid. No arbitrary small mineral capacity has been inserted to bypass that requirement.

## Why backward Euler needed a different certificate and endpoint

More residual leaves can tighten an enclosure but cannot remove the numerical method's leading time error. For the exact scalar problem H'=a−λH and an exact backward-Euler endpoint H1, the residual of the exact straight line between endpoints integrates to

\[
U=\tfrac12 |H_1-a/\lambda|\lambda^2h^2.
\]

Uniform rectangular residual leaves over this linear mode multiply the value by 1+1/N. Increasing N from 32 to 64 therefore makes only a small change; the first-order accumulated error remains. With a duration-proportional annual quota bh/T, the example gives a step restriction of order 2b/(T λ |q|), where q is the endpoint net heat rate. The source review's illustrative 3340 J/m² annual budget produces a seconds-scale restriction for its declared scalar constants. That is an analytic illustration, not a measured production-year workload.

The new component changes the endpoint proposal and the reconstruction together. It uses two physical backward-Euler resolvents as a represented SDIRK2 proposal. Let g be the fixed binary64 coefficient `0x1.2bec333018867p-2`, a=fl(g h), and beta=fl((1−g) h). The first stage starts from H0 with duration a. The second stage starts from the represented base

\[
B_i=\operatorname{fl}\left(H_{0i}+\operatorname{fl}(\beta f_{1i}^{raw})\right),
\]

where f1raw is the midpoint of the first-stage outward field enclosure. It then uses the same duration a. Each stage must independently pass its physical-domain and algebraic residual checks. A nonphysical second-stage base refuses; it is never clipped into the physical region.

The fixed coefficient is close to the irrational SDIRK2 coefficient but is not exactly that coefficient. The receipt therefore retains the actual durations and outward bridges for a+beta−h, the represented second-order coefficient defect, and B−[H0+beta F(Y1)]. These are diagnostic method-formation bridges. They are already included in the final ODE residual and must not be charged again.

The two backward-Euler calls share the original scalar-evaluation and sweep limits. Each retains one deliberately untightened linear residual leaf and its complete original receipt. Those internal leaves count as actual work. They are not additional pieces of the physical time interval and their endpoint-error bounds are not summed into the new certificate. The total retained outer polynomial coefficient reservation is separately capped.

## Quadratic reconstruction and the endpoint guarantee

The final endpoint is the actual raw second-stage state H1. The exact quadratic curve uses H0, H1, and a raw initial heat vector f0raw. Its Bernstein coefficients over the complete unit interval are

\[
[H_0,\ H_0+\tfrac12 h f_0^{raw},\ H_1].
\]

Uniform dyadic de Casteljau subdivision encloses this one exact curve. It does not define independently rounded curve endpoints. Every leaf must prove that the full enthalpy curve is above the physical floor. Constant point polynomials preserve the exact subdivision identity. That identity was added after the first run exposed unnecessary outward widening below the floor for stationary absolute zero; general curves and coefficients are not clipped.

Where a leaf remains in one phase, temperature is an affine function of enthalpy or a constant plateau. Its polynomial has degree at most two; fourth-power emission has degree at most eight, and each symmetric transport edge contributes equal and opposite polynomial heat. Across a phase boundary the implementation uses a degree-zero temperature interval envelope for the affected component. That envelope is a pointwise bound, not a claim that the physical temperature follows one polynomial through the phase change.

On each leaf's unit coordinate s, form

\[
R_i(s)=\frac{dH_i}{ds}-\frac{h}{N}F_i(H(s)).
\]

Bernstein basis functions are nonnegative and integrate to 1/(d+1). If the residual coefficient intervals are r0,…,rd, then the integral of |R| is bounded by the mean of their absolute maxima. This retains the algebraic cancellation between curve derivative and heat flow on smooth branches. For phase-range envelopes the same pointwise inequality remains valid, although it can be wider. The receipt retains the enthalpy, temperature, branch, and residual coefficient arrays plus component and area-weighted bounds.

For the prescribed fixed-W positive graph, temperature is monotone in enthalpy, radiation is dissipative on the physical domain, and one symmetric exchange contributes opposite signs at its two endpoints. The area-weighted L1 contraction argument bounds the actual endpoint error by the integrated residual. The resulting U is in joules:

\[
\sum_i A_i |H_i^{true}(h)-H_{1i}|\le U.
\]

This guarantee is from the canonical point start under the fixed prescribed forcing and parameters. It does not establish original precipitation/forcing accuracy, per-cell independent contraction, gross melt/refreeze, annual glacier accuracy, or a multilayer glacier model. Numerical stage and tableau formation defects are included exactly once through the actual reconstructed endpoint path.

## Fixed thermal qualification and corrections

The final unchanged-input qualification passes **105 checks**. It makes 15 outer calls, 23 internal BE calls, and one separate BE comparison call. Eight outer requests accept; seven refuse as specified. Nine requests complete a quadratic certificate, including the intentionally too-tight endpoint refusal. There are zero world, annual, owner, mass-source, hydrology, or API calls.

| New control | Quadratic bound, J | Analytic endpoint error upper bound, J |
|---|---:|---:|
| Unequal-area exchange, 1 second | 0.0003363212611 | 0.0002253959195 |
| Same exchange, 0.5 second | 0.00004342415837 | 0.00003062015669 |
| Same exchange, 0.25 second | 0.000005518704828 | 0.000003992127725 |
| Dry radiative cooling, 1 hour | 0.07717282038 | 0.04173727432 |

With the same eight outer leaves, each exchange step halving reduces the bound by more than fivefold. The cooling-hour backward-Euler comparison gives 454.7022163 J. These are local controls with declared parameters and independent exact exponential/cubic-root reference enclosures. They do not predict full-year work or prove phase-transition convergence. The constant-heating phase-crossing control exercises two fallback components and reaches its known endpoint within the fixed tolerance.

The first native run passed 100 of 101 checks and refused the expected stationary case after both physical stages passed. Its output is retained. The correction preserves exact constant subdivision; no fixture, budget, gamma, or work limit changed. All 14 other recorded receipt objects are identical, and both serializer inventories are identical. The corrected run passes all 105 reached checks.

A separate Fraction-based reader reconstructs physical curve bounds, exact Bernstein residuals, stage algebraic residuals, raw stage requests, and formation bridges from the retained operands. It also encloses analytic exchange and cooling endpoints. The first corrected-output audit reached all receipts but failed its own five-mutation requirement: replacing the exact initial zero residual coefficient with [0,0] was a valid tightening. Reader v2 changes only that fixed mutation target to the last coefficient on the same leaf. Its arithmetic is unchanged; all five actual invalid mutations refuse. The final replay passes 26,808 assertions. This post-outcome test correction is preserved and is not described as a first-pass pre-outcome qualification.

## Finite mass routing and the production boundary

The existing production hydrology function cannot simply be called again with seasonal supply. It resets lake/routing state, derives fill from annual precipitation and losses, and updates water depths. Reusing it after a seasonal thermal owner would both spend annual precipitation again and change the terrain/lake geometry against which the thermal context was certified.

The new `SeasonalLiquidRoutingGraph` instead captures canonical cell identity, raw receivers, adjacency, areas, wet classes, and the relevant terrain/depression/conditioning metadata. It validates the entire original graph as a bounded DAG, even for edges that delivery later cuts at a wet boundary. A min-ID priority queue gives a deterministic topological order. Its immutable snapshot can be compared with current Cells independently of the existing thermal-context matcher.

Finite routing requests declare a complete sparse list of source masses with unique identifiers and an explicit liquid density. Sources must be exposed land. Each represented source follows the frozen effective receiver graph and stops at the first marine cell, lake, or dry terminal. A lake marked as overflowing in the annual diagnostic still receives a terminal receipt; propagating through it would require a conserved lake storage/overflow model. This routing has no physical travel-time or downstream-energy certificate.

Every cell receives a throughput table, while delivered mass totals include only terminals. Summing every interior cell's throughput would double-count the same water. The implementation distinguishes the exact sum of represented source masses, ordered binary64 accumulation, terminal aggregation, canonical area conversion, and throughput-equivalent depth conversion. Equivalent depth is not water storage. Positive conversion underflow, overflow, malformed input, or exhausted work refuses with no complete final result. The pure function has no accepted mutable state and does not authenticate an owner event or acknowledge external delivery.

The one fixed routing qualification passes **492 checks** across 30 groups. It makes 21 graph captures (seven accepted and 14 refused), 25 ordinary route requests (12 accepted and 13 refused), and one non-nearest-arithmetic capability refusal. The separate rational reader passes 3515 assertions, reconstructing all seven accepted graphs and 25 ordinary routing receipts, and rejects five deliberately corrupted results. The capability refusal is covered by the native control. No numerical or fixture retry occurs. A missing final namespace brace was corrected during compilation, before any routing execution; original drafts and protocol revisions are retained.

The full native library and both CMake test targets compile successfully in an isolated CPU build; the library resolves all eight V3/V4 generation exports without invoking them. The existing installed native library remains unchanged. The fixed scientific qualifications use their separately pinned strict standalone executables; the CMake targets were built, not rerun as additional experiments.

The source cutover belongs after final cryosphere/terrain stabilization and before soil, biome, resource, landform, watershed, and society descendants. The current finalized-enthalpy readiness marker occurs after descendants, so production needs a separate geometry-ready boundary. The coherent publication unit must include thermal state, source history, liquid outbox, frozen-graph routing, terminal ledger, and acknowledgment together. Precipitation diagnostics and existing annual river fields must retain their declared meanings until a versioned seasonal descendant view replaces them.

## Remaining work and decision order

The next physical step is a conservative layered snow/upper-ice state with separately owned deep ice, explicit initialization, and validated vertical exchange. It needs new admission and remap/error treatment; the existing positive-base-capacity API must not be disguised as that model. The new numerical API then needs owner dispatch, work reservations, and a composite thermal ledger. In particular, adding the two internal BE ledgers would be incorrect: the second stage starts from B, and the represented quadrature uses beta F(Y1)+a F(Y2), with a separate bridge to the physical hS.

A complete precipitation phase/enthalpy policy must consume annual or subannual source information exactly once. Source error needs its own reserve and original-source interpretation. Drainage and refreezing need explicit storage and energy rules. Routing and owner commit need one atomic coordinator, then versioned descendants and public availability metadata. Only after these physical and ownership requirements are met should a new fixed production-year protocol be frozen. Existing annual failures and Earth-profile calibration limits remain unchanged.

## Sources

[^1]: NCAR/ESCOMP, [CTSM technical note: Soil and Snow Temperatures](https://escomp.github.io/CTSM/tech_note/Soil_Snow_Temperatures/CLM50_Tech_Note_Soil_Snow_Temperatures.html), equations 2.6.1–2.6.10; accessed 2026-09-11. Used for layered heat conduction and interface thermal resistance, not numerical defaults.
[^2]: W. J. J. van Pelt et al., [Simulating melt, runoff and refreezing on Nordenskiöldbreen, Svalbard, using a coupled snow and energy balance model](https://tc.copernicus.org/articles/6/641/2012/), The Cryosphere 6, 641–659, 2012. Used for the physical distinction among multilayer thermal state, refreezing and runoff, not parameter calibration.
[^3]: A. Aschwanden et al., [An enthalpy formulation for glaciers and ice sheets](https://www.cambridge.org/core/journals/journal-of-glaciology/article/an-enthalpy-formulation-for-glaciers-and-ice-sheets/605D2EC3DE03B82F2A8289220E76EB27), Journal of Glaciology, 2012. Source review retained in the evidence package; used for spatial enthalpy and boundary-condition scope.
