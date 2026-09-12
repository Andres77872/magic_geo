# Layered ice thermal model and qualification

The native thermal core now supports an explicitly selected pure-water mode, and a new immutable graph builder separates horizontal cells from thermal layers. Snow and upper ice can retain distinct temperatures without adding artificial mineral or atmospheric heat capacity. The builder also records finite deep ice separately, so a chosen active depth cannot silently discard the remainder or put the entire glacier into the surface heat capacity.

This is an internal, fixed-geometry component. The installed native binary and ordinary-generation dispatch remain unchanged. The new component does not yet evolve precipitation, drainage, layer geometry, deep refill or public glacier fields. Its qualification addresses a necessary physical and numerical foundation for the annual ablation correction.

## Physical model

For each thermal node, let A denote horizontal area, W water mass per area, C prescribed nonwater heat capacity per area, and H complete node enthalpy per area. All nodes share positive water constants: freezing temperature Tf, solid and liquid specific heats ci and cl, and latent heat Lf. Define Cs=C+W ci and Cl=C+W cl. The temperature law is

```
T(H) = Tf + min(H, 0)/Cs + max(H-W Lf, 0)/Cl.
```

Cold solid has negative H, the latent plateau spans 0 through W Lf, and warmer liquid has H above that interval. Solid water at Tf and any declared nonwater capacity at Tf define zero enthalpy. Therefore the top node's H includes atmospheric/mineral energy when its C is positive. An initial cold top temperature must be converted with `(C+W ci)*(T-Tf)`. Supplying only `W ci*(T-Tf)` would describe a different combined-node temperature. Interior and deep records have no nonwater capacity.

The old mesh admission remains the default. `allow_pure_water_columns=true` permits C=0 when W>0 and both outward effective-capacity intervals remain strictly positive and finite. Empty C=W=0 states refuse because they have no defined temperature. No epsilon mass or capacity is inserted. Negative mass or capacity, invalid material constants, unrepresentable latent storage or temperature, below-absolute-zero states and arithmetic failures refuse explicitly. Negative enthalpy remains valid cold content.

The physical lower enthalpy is `-Cs*Tf`. For nonnegative prescribed shortwave S and duration h, a valid uniform upper temperature is

```
Tbar = max(Tf, maximum initial T) + h * maximum [S/min(Cs,Cl)].
```

At that common temperature, graph exchange cancels; each node's enthalpy increase dominates hS and outgoing radiation is nonnegative. This supplies the backward-Euler supersolution. Using only Cs in the denominator is insufficient when the admitted liquid heat capacity is smaller than the solid heat capacity. The implementation retains outward rounding, stage algebraic gates and whole-curve physical checks.

The temperature law remains continuous and monotone. With symmetric positive conductances and nonnegative emissivity on the physical domain, its area-weighted L1 contraction argument still applies. The residual certificate bounds the represented fixed-W, fixed-coefficient ODE in global joules. Allowing pure water changes neither this error norm nor the need to prove every stage and the reconstruction curve physical.

## Horizontal cells and depth nodes

Each input column has one geographic cell ID, one full horizontal area and ordered layers. The builder creates separate thermal node IDs and retains the mapping to cell and layer. Hydrologic receivers and world adjacency remain geographic. Multiple layers with area A contribute distinct energies A H; they represent separate material volumes rather than repeated geographic land.

The current coverage fraction is explicitly one. Mass and enthalpy are per the full column area. A future fractional glacier model must distinguish `W=rho*depth` per ice footprint from `W=f*rho*depth` per full cell area. CTSM makes this snow-area distinction explicitly and computes interlayer heat flux through material interfaces.[^1] This implementation does not infer coverage from diagnostic ice thickness.

For a prescribed density rho, thickness is `dz=W/rho`. Adjacent layers exchange through one shared conductance

```
K = A / [dz1/(2*k1) + dz2/(2*k2)]
```

in W/K. The corresponding watts enter the two nodes with opposite signs. This is the center-to-center resistance for uniform layer conductivities and perfect contact. Its resistance form is consistent with the CTSM interface construction; no CTSM layer count, calibration or solver performance is transferred here.[^1]

Only the top node receives the declared nonwater capacity, emissivity, shortwave forcing and horizontal climate edges. The three explicit top closures are prescribed top energy with C=0, prescribed nonwater capacity with C>0, and a coarse combined surface/atmosphere capacity with C>0. The latter preserves an explicit modeling choice used by the combined-temperature framework; it is not a resolved atmosphere–snow boundary layer.

Material properties are held fixed over the thermal request, including if part of a node melts. Thus fixed density and conductivity remain prescribed coefficients, not a prognostic liquid geometry model. Phase-dependent geometry or material-property changes, compaction, optics, pressure-dependent freezing, turbulent transfer and percolation require additional models before production use.

## Deep storage and accounting

A column may include a finite deep mass, enthalpy and density record. The supported lower thermal boundary is explicitly insulated. Deep storage remains part of the complete initialized mass/energy inventory but is not a thermal node and receives no heat or material exchange during this component's request. An omitted deep record differs from an explicitly empty one; an empty record must have zero enthalpy and positive declared density.

The graph retains active, deep and combined extensive inventories. The active and combined enthalpy totals include the declared top nonwater energy. They must not be labeled ice-only energy. Every original operand is retained, along with outward enclosures for extensive mass and enthalpy, thickness, cumulative depth, series resistance, conductance and represented-minus-ideal conversion differences.

The thermal solver consumes the represented K. Geometry conversion enclosures are reported separately; its integration bound does not cover unknown density/conductivity, spatial discretization or the difference between an ideal geometry-derived conductance and the represented one. Original-source accuracy is explicitly false in both graph and thermal receipts.

An insulated active column is useful for qualifying separation and inventory ownership. It does not establish that the chosen lower boundary is suitable for a real glacier or a full season. A thermally coupled deep profile could affect later surface behavior. Initial thickness also does not supply an equilibrated temperature history.

## Dependency and ownership implications

A complete seasonal implementation must own an explicit layer state before applying layer sources or requesting heat evolution. The existing geographic owner and calorimeter still assume positive nonwater capacity in several admission and source-error paths. The new pure-water thermal flag does not relax those interfaces or automatically dispatch the new graph through them.

The next material operations must move both mass and carried enthalpy. Plateau liquid carries Lf per kilogram; warm liquid additionally carries `cl*(T-Tf)`. Cold solid carries negative specific enthalpy relative to Tf. A deep refill must debit a finite donor with its actual energy; assuming fresh ice at Tf would create or remove heat. Initial withdrawals cannot be funded by heat or imports that occur later in the interval.

Complete withdrawal from a C=0 node creates an undefined empty thermal state. Such an operation must refuse or atomically remove/remap the node and update its graph. A conservative remap must retain more than a global energy sum: otherwise it can erase a meaningful temperature gradient. For a fixed nonnegative parcel allocation matrix whose donor columns sum to one, the extensive-energy map is L1 nonexpansive. Phase- or mass-dependent allocation requires a separate sensitivity argument and cannot reuse that fixed-map proof without qualification.

The production order remains terrain/geometry readiness → explicit initial layer profile and finite sources → thermal evolution and material operations → one committed liquid outbox → geographic routing → hydrology and natural descendants → social/publication descendants. The current finalized-epoch entry occurs after descendants, so production needs an earlier readiness boundary. Later descendants must consume committed seasonal state with explicit versioned parents.

The represented SDIRK2 owner ledger must also use its weighted two-stage fluxes. Adding two backward-Euler stage ledgers would double-count the wrong durations. Represented stage durations and physical interval duration have a recorded rounding difference that must remain in source accounting.

## Qualification evidence

All numerical inputs, call limits, acceptance assertions and reader dependencies were fixed before the associated native launch. Each suite runs with a 30-second wall limit, 20 CPU seconds, 1 GiB address-space limit and 64 MiB output limit. Failed setup or qualification evidence is retained. No historical annual or six-hour experiment was reopened.

The pure-water suite passes **138 native checks** across 16 requests: nine accepted and seven refused, with 26 internal backward-Euler calls. It covers closed pure-ice exchange, unequal mass, latent refreezing, cold-content exhaustion, partial and complete melting, liquid warming, cl<ci, absolute zero, empty/negative capacity, arithmetic refusal, work exhaustion and an unmet endpoint budget. The independent rational reader passes **25,631 assertions**, validates ten complete certificates and 80 reconstruction leaves, and checks exact or bounded analytic references. Its pre-outcome controls include a complete synthetic certificate and eight invalid mutations.

For closed solid exchange, the one-second error bound is 0.000115798 J and the independent true-error upper bound is 0.0000816538 J. At half a second those values are 0.0000147165 J and 0.0000106457 J. The refreezing control bounds error by 0.0000523172 J, enclosing a 0.0000373224 J independent upper bound. Constant heating controls match the exact enthalpy law within their small reported numerical bounds. These are fixed-node thermal checks.

The builder qualification passes **108 checks** over 55 build attempts: three accepted fixtures, 51 declared refusals and one rounding-mode capability refusal. The independent reader passes **1,319 assertions** and rejects five corrupted actual graphs. The first accepted fixture retains exactly 620 kg active water and 1,800,000 kg deep water; active enthalpy is 16,699,400 J and deep enthalpy is −1,800,000,000 J. A second fixture checks nonbinary geometry and conversion enclosures. A single-node pure-water fixture creates no invented deep storage.

The layered thermal qualification passes **23 checks** over two graph builds, two outer SDIRK2 calls and four internal backward-Euler calls. Each request has two geographic columns of area 1 and 2 m², three active layers per column and five total thermal edges. Both advance exactly the declared 900-second interval under fixed top shortwave 300 and 450 W/m², emissivity 0.6 and coarse combined top capacity 10⁷ J/m²/K. Every column has water masses [50, 200, 1000] kg/m² and initial H [0, −420000, −4200000] J/m². Density [300, 917, 917] kg/m³ and conductivity [0.3, 2.29, 2.29] W/m/K remain prescribed.

Both requests are accepted with the same **0.05024488296311121 J** canonical endpoint bound, below the predeclared 3340 J allowance. The first independent replay passes 6,479 adapter, 20,550 thermal-arithmetic and 522 geometry assertions. The surface candidates contain approximately 0.289754 and 0.693945 kg/m² liquid; the four lower nodes remain solid at approximately 272.149098 and 271.151498 K. The global bound implies individual enthalpy errors no larger than E/A; those intervals stay strictly inside the stated phase branches. The lower first layer can cool slightly while conducting heat into its colder neighbor, despite surface heating. Summing retained liquid over the two areas gives approximately 1.677644 kg, with uncertainty below 1.51×10⁻⁷ kg from E/Lf charged once globally. Initial liquid was zero. This proves net retained liquid production in the fixed canonical model, not cumulative gross melting, refreezing or drainage.

The active mass is exactly 3750 kg in both cases. Increasing isolated deep mass from 300,000 to 3,000,000 kg and its negative enthalpy by the same factor leaves the complete active request and thermal receipt identical. Its distinct deep inventory remains recorded. This verifies the declared insulated separation; it does not establish irrelevance of physically coupled deep ice.

The native library and all three new CMake test targets build in an isolated CPU tree. All eight V3/V4 exports resolve with zero generator calls. The isolated library hash is `6e0d97cf0195690a0c0b58008a40eaa3f51308cbd795c6dd7e12db217e59e229`; the installed `fa17d36b6759b88b524ddcbd822eb025b6454d6356fe585f799fedd11b949731` library remains unchanged. CMake compilation does not duplicate the qualification runs.

[The complete evidence package](../runs/layered-ice-thermal-review/README.md) retains exact inputs, source dependencies, executable hashes, numerical stdout, independent readers and review results. It also preserves the initial serializer-launch permission error, which occurred before executable entry, and the source/reader corrections made before actual qualification. All three final scientific suites passed their first actual launches without numerical parameter retries.

The geometry reader uses exact rational arithmetic on the original binary64 operands and separately reproduces represented operations. It verifies the complete node map, top-only coefficients, vertical and horizontal edges, extensive inventories and every retained conversion enclosure. Its pre-outcome synthetic controls accept one complete exact graph and reject six altered graphs, including hidden deep cold content and changed thermal coefficients.

The integration reader additionally binds the actual thermal request to the declared graph and fixed options. It reuses the already qualified pure-water certificate reader, verifies both physical stages and the outer residual certificate, and checks that the deep-only variant leaves the complete active request and receipt identical. It does not infer annual validity from those local results.

## Remaining physical qualification

The plateau melting controls exercise the temporal phase law. They do not qualify a moving phase front in space. Tubini, Gruber and Rigon use the Neumann/Stefan problem to compare phase-front position and temperature profiles under spatial and temporal refinement.[^3] A future layered implementation needs a comparable spatial test with explicit boundary flux accounting. A large finite heat-capacity node cannot silently stand in for an infinite fixed-temperature bath.

Melt, runoff and refreezing are distinct processes in coupled glacier snow/energy modeling. The Nordenskiöldbreen study also evaluates model sensitivity and calibration against observations.[^2] The present prescribed local inputs do not adopt its calibration or establish that annual precipitation and temperature moments resolve seasonal weather. Production source timing, initial conditions, basal policy and validation against observations remain separate requirements.

Before an annual generated-world result, the outstanding work is finite drainage/refill/remap with uncertainty propagation; mapped owner and SDIRK2 ledger integration; explicit precipitation and lower-boundary policy; atomic routing acknowledgment; versioned descendant publication; and a new bounded production-year qualification. The installed library's annual glacier ablation issue and Earth-calibration failure remain open. This change advances the thermal representation required to address them.

## Sources

[^1]: NCAR/ESCOMP. [CTSM technical note, Soil and Snow Temperatures](https://escomp.github.io/CTSM/tech_note/Soil_Snow_Temperatures/CLM50_Tech_Note_Soil_Snow_Temperatures.html), equations 2.6.1–2.6.10 and boundary conditions. Accessed 2026-09-11. Used for interface resistance, area semantics and explicit boundaries.
[^2]: W. J. J. van Pelt et al. [Simulating melt, runoff and refreezing on Nordenskiöldbreen, Svalbard, using a coupled snow and energy balance model](https://tc.copernicus.org/articles/6/641/2012/). The Cryosphere 6, 641–659, 2012. Accessed 2026-09-11. Used for process and observational scope, without calibration transfer.
[^3]: N. Tubini, S. Gruber and R. Rigon. [A method for solving heat transfer with phase change in ice or soil that allows for large time steps while guaranteeing energy conservation](https://tc.copernicus.org/articles/15/2541/2021/). The Cryosphere 15, 2541–2568, 2021, section 4.1. Accessed 2026-09-11. Used for the spatial Stefan benchmark distinction.
