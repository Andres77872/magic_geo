# Complete water removal and conservative layer reconstruction

Qualified internal component, 2026-09-12 UTC. This document separates the prescribed topology operation from the remaining production ablation policy. Ordinary world generation and the installed native library remain unchanged. [Evidence package](../runs/layered-ablation-topology-review/README.md)

The existing material operator refuses complete withdrawal from a pure-water layer because its calorimeter must invert every post-event state. An empty pure-water state has neither water nor nonwater heat capacity, so its temperature is undefined. The subsequent remap never receives a valid source. Removing only the final graph check would leave the earlier calorimeter inversion unchanged. Adding a small invented water inventory would change mass and energy conservation.

The new operation allocates whole source inventories directly to the final retained stores and export parcels. It constructs the valid source graph and the valid final graph; a removed coordinate is absent from the ideal output map. Existing material, remap, calorimeter and graph-builder admission remain unchanged.

## Physical references and the policy boundary

CTSM treats snow liquid drainage separately from layer combination and subdivision. Its layer changes follow thermal, phase, hydrology and compaction updates; merging combines water, ice and enthalpy, then recomputes temperature and geometry. Its numerical thresholds are choices of that snow model, not universal glacier tolerances. This supports preserving the energy and inventory through layer reconstruction, but does not select our drainage rate, density, thickness threshold or basal boundary. [CTSM snow hydrology technical note, sections 2.8.3 and 2.8.7](https://escomp.github.io/CTSM/tech_note/Snow_Hydrology/CLM50_Tech_Note_Snow_Hydrology.html)

FSM1.0 compares alternative descriptions of processes including conduction, compaction and liquid retention/refreezing. Its alpine-site demonstration does not calibrate this planetary generator. A conservative topology map is one numerical requirement; realistic source, transport and material policies still require independent justification. [Essery, 2015, A factorial snowpack model](https://gmd.copernicus.org/articles/8/3867/2015/)

The equations and software conclusions below are local derivations for the explicitly prescribed column model. They are not accuracy estimates inferred from those publications.

## Conserved energy map

For a source store let A be its area, W its water mass per area, H its complete enthalpy per area, C its stationary nonwater heat capacity per area, and ci, cl, L the water heat capacities and latent heat. The reference is solid water at freezing temperature Tf. C is positive only at the geographic top when the selected closure includes nonwater storage.

For W>0, write

```
qw(H) = W ci/(C + W ci) min(H, 0)
      + clamp(H, 0, W L)
      + W cl/(C + W cl) max(H - W L, 0)
qC(H) = H - qw(H).
```

The existing decomposition evaluates an equivalent expression for qC directly, avoiding avoidable cancellation. For a pure-water source C=0, qw=H and qC=0. A dry positive-C source has qw=0 and qC=H. Water W and qw move together. Every top qC stays at its geographic top even when the original water is completely exported or replaced by a former interior layer.

Each source with positive water is owned exactly once by either a complete within-column remap row or a whole-export selection. Remap fractions are exact normalized nonnegative integer weights. An export selection supplies an event ID, initial donor address and phase; it supplies no substitute mass, temperature or joules. Target descriptors supply the complete canonical layer order and prescribed positive density/conductivity. Empty declared deep stores are constrained to zero water and energy.

On each phase branch both qw and qC are nondecreasing and their slopes sum to one; the same holds continuously across the phase boundaries. Multiplying by A and applying normalized allocations gives an extensive-energy map with induced L1 norm at most one. Existing pending parcels are identity coordinates. Thus a single inherited joint bound E covers the mapped retained stores and old and new parcels together. The removed source coordinate contributes through its destinations, not through a fictitious independent empty-store uncertainty coordinate.

Let Hhat be a final represented retained enthalpy and Jhat a represented new parcel energy. Direct projection defects are measured against the exact ideal map at the canonical source operands:

```
Dret = sum over retained stores A abs(Hhat - Hideal)
Dout = sum over new parcels abs(Jhat - Jideal)
Efinal >= E + Dret + Dout.
```

The implementation uses outward bounds for these sums and admits only a finite Efinal within the caller's unchanged budget. Existing parcel projection bounds are already included in E and are not charged again. Every final active and positive deep store must remain above its absolute-zero enthalpy floor under the full marginal radius Efinal/A, including unchanged stores. An empty deep store is structurally constrained to zero and has no independent energy coordinate.

For a complete phase-labelled export, the entire source error ball must have that phase:

```
solid: A H + E <= 0
liquid: A H - E >= A W L.
```

The implementation proves the conservative interval versions. A state at H=WL with positive E cannot pass the liquid proof. A mixed-phase whole inventory cannot be represented as a single existing liquid or solid parcel. The operation refuses it; it does not claim that endpoint temperature alone proves sufficient withdrawable phase mass.

## Exact whole mass and topology admission

A binary64 source A and W do not necessarily have a binary64 product A W. This first version admits an external whole export only when that exact product is positive, finite and provably representable. It records the original operands and the representability proof result. Rounding A W and then deleting the source would silently change the mass trajectory, so that case refuses. General support needs an explicit exact-product parcel mass representation or a separately owned mass-projection contract extending receiving semantics.

Parcel J is projected directly from A qw, rather than reconstructed from a rounded reported temperature. Its signed projection interval and absolute bound remain in the receipt. Its saved mass and J are compatible with the existing prescribed receiving operation. Temperature and specific enthalpy remain provenance there.

Retained remaps still publish canonical represented W with explicit mass-projection intervals. This is not an original-mass trajectory certificate: subsequent thermal capacities and geometry use that canonical W, and this work does not propagate an earlier mass error through their sensitivity. Density, conductivity and spatial discretization are also prescribed rather than certified by E.

Final graph rules remain explicit. A completely dry column can retain one W=0, C>0 surface with its stationary energy. A C=0 column cannot become entirely empty without a separately defined surface closure. Zero-water conducting interior layers refuse. The current builder also refuses a dry top above positive inactive deep water; this is an existing model admission rule, not a thermodynamic theorem about insulated deep stores. A plan within this version must explicitly refill the top or exhaust the deep inventory too. No epsilon mass, invented heat capacity, hidden deep transfer or threshold clipping is used.

## Atomic ownership and execution order

Owner v3 adds a separate zero-duration topology request, exclusive of movements, ordinary remap, receiving and thermal forcing. It binds the accepted source graph and E internally. Before starting the component it reserves complete pending-parcel and consumed-event capacity and rejects duplicated or previously consumed export IDs. The complete request, including targets, allocations, export phase and limits, participates in replay identity.

Preparation leaves accepted physical state unchanged. Commit publishes the graph, E, parcels, consumed IDs, retained receipt and incremented revision together, retaining the clock. Existing parcels stay unchanged. New parcels store the original donor address, producing revision and geographic cell; a later compacted graph need not contain that historical layer. Receiving resolves the saved transaction/event identity and validates the current recipient, then adds the saved mass and J. Stale geography, changed revision, foreign candidates and competing same-base candidates remain guarded by the owner.

This operation supplies no automatic drainage, travel time, phase-change rate, snow accumulation calendar, basal exchange or external-delivery acknowledgment. A thermal step can establish a sufficiently liquid source; this zero-time map can then export it and rebuild layers; prescribed receiving can incorporate the saved parcel. These dependencies are explicit separate accepted boundaries.

Production evolution still belongs after the final hydrologic stabilizer and before final grounded-ice feedback, soils, landforms, natural artifacts and society. Production must initialize W/H, declare source timing and temperature, choose drainage/basal policies, handle general parcel mass, own routing/acknowledgment, preserve physical fields through later ice-sheet aggregation and rebuild descendants from the accepted state. A warm-season production witness must show retained-solid loss and water/energy accounting through that full order. This component alone does not close the annual ablation defect.

## Qualification

The new native tests and independent rational replay use newly declared manufactured operands. They do not replay historical annual or thermal experiments. Both new targets and the complete native library build in isolation with floating-point contraction disabled. The installed library retains SHA256 `fa17d36b6759b88b524ddcbd822eb025b6454d6356fe585f799fedd11b949731`; no native world/API generation is executed.

The first fixed component execution passes **195 checks** over 43 cases: 13 accepted maps and 30 refusals, with exactly 36 source and 16 output builder calls. There are no calorimeter, ordinary-remap, thermal or world calls. The manufactured water uses Tf=10, ci=2, cl=4 and L=20. These values make the arithmetic inspectable and are not a calibrated water model. For A=1, C=6, W=2 and H=68, complete liquid removal exports mass 2 and J=56 while leaving the dry surface H=12, C=6, T=12. Final E is 0.12500000000004802 J from initial 0.125 J. The corresponding cold case H=-20 exports J=-8 and retains H=-12; it is solid-water removal, not melt drainage.

Other controls remove interior layers, promote surviving water, split finite deep water into a refilled top and retained deep store, exhaust a deep store to constrained zero, preserve unequal column areas and horizontal heat edges, and preserve a complete identity exactly. Refusals include inexact whole-export mass, uncertain phase, duplicate/missing donor ownership, invalid target geometry, unsupported dry/deep shape and exhausted work/error allowances. A thin retained layer whose enlarged final error ball crosses its floor refuses even though its represented center remains admissible.

The first ownership execution passes **41 checks**. A permuted geographic mapping preserves an older parcel with historical donor layer 7, removes current layer 2, and records the new parcel's original address, source revision, mass 4 and J=32. The first commit advances revision 0 to 1 at unchanged time 30, with E=0.2500000000000514 J. Receiving that parcel into current column 1, layer 0 advances revision to 2, gives W=5 and H=30 there, leaves the older parcel unchanged, and yields E=0.250000000000055 J. Native assertions cover stale geography, foreign and same-base competing candidates, exact replay, changed request operands, consumed IDs, mixed operators, outbox capacity and preparation rollback.

The first independent read-only replay passes 24,466 rational/binding assertions and 6,470 geometry assertions across 303 JSONL records. It binds the complete 43-case component inventory, recomputes ideal mass/enthalpy maps and projection enclosures from canonical binary64 operands, checks the rebuilt graph, and verifies prepared owner state and parcel carry. These assertion counts are not separate physical experiments. Sixteen subsequent corruption controls are rejected, including duplicated export certificates, altered graph storage, omitted inherited E, forged domains, missing component receipts and changed historical parcels.

The independent reader's scope is deliberately bounded: commit/replay/rollback rely on the native lifecycle assertions, recorded geographic context is trusted, and refusal prefixes receive partial checks. Reported candidate temperatures, specific enthalpies and intermediate represented arithmetic are checked for finiteness; exact ideal enthalpy/projection fields and final ownership are checked mathematically. No source, input, budget or reader changes follow the first numerical outcomes. Both native processes exit zero with empty stderr and are reaped.
