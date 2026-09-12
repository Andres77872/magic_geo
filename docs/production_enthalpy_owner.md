# Combined-temperature enthalpy mesh owner

The internal `EnthalpyMeshOwner` composes explicit snow/rain imports and initial
liquid withdrawals with the [combined-temperature mesh](production_enthalpy_mesh.md).
It advances all thermal cells on one clock, carries an area-weighted global
energy-error bound, and publishes a complete prepared interval atomically.
Ordinary world generation still follows its existing climate/hydrology/ice path.

## Frozen context and state

The owner captures an immutable `TerrestrialSurfaceSnapshot`, full-mesh physical
columns and an explicit symmetric positive graph. Each column's area must equal
the represented surface `area_km2 * 1e6`; capacities and emissivities cover every
cell. Graph validation checks canonical endpoints and uniqueness. Construction
does not derive geometric conductances or bind edges to the surface's neighbor
list; a production adapter still must establish that correspondence.

Each cell carries retained water W and enthalpy H. C is the existing combined
surface/atmospheric sensible capacity. Retained land water adds its phase and
sensible storage at the same temperature. Marine and lake cells require W=0 in
this additional reservoir and retain their supplied sensible capacity, absorbed
sunlight, radiation and graph exchanges. W=0 does not mean those cells contain
no physical water. Marine freezing is outside this model.

A restart contains one revision, elapsed seconds, full W/H arrays, a global
canonical error E in total joules, consumed source IDs and forcing history.
E bounds the area-weighted L1 enthalpy difference for canonical projected W and
recorded import energy. It does not certify the original precipitation mass or
ideal source enthalpy before floating-point representation. The model still
assumes retained land water shares the combined column temperature.

## Initial source operation

Mass events are permitted only on exposed land. Each visible ASCII ID is unique
across imports, withdrawals and committed history. Import phase and temperature
must agree. The owner validates the complete potential thermal work/retention
schedule before starting a source batch. Empty source requests skip A entirely.

For a nonempty batch, the unchanged calorimeter A runs once at the accepted
initial clock, using each exposed cell's area and **combined C**. A's historical
`dry_heat_capacity_j_m2_k` field receives Ctotal in this adapter. No separate air
energy is added. Imports bind to A's recorded carried joules. Withdrawals bind
to initial donor liquid and its actual carried energy; incoming rain or later
melting cannot fund an initial withdrawal. Every returned movement is matched
exactly once to a requested source ID or outbox entry.

The global norm implies the conservative local domain radius

```
e_i = upward(E / A_i).
```

The existing scalar canonical jump helper is used only as an airless mass/error
adapter, with Ctotal in its sensible slot and all air/exchange terms zero. It
checks feasibility over H_i ± e_i and supplies a local jump defect D_i plus
per-withdrawal outbox energy bounds. Its local inherited/final errors are not
summed. The global recurrence is

```
Dglobal = upward sum_i A_i D_i
Epost   = upward(E + Dglobal).
```

Inherited E is charged once. The scalar helper receives the largest finite
admission bound; the owner's global budget B is the policy gate. Local overflow
or failed domain proof still refuses. After Epost passes B, every cell's new
H_i ± upward(Epost/A_i) must lie above its physical floor
`-(C_i + W_i ci) Tf`, including untouched wet cells.

After A changes a diagnostic private H, the old error is unavailable until this
global source proof succeeds. If that global source proof refuses, the private
prefix's `canonical_energy_error_j` is serialized as null. An initial-inventory
A refusal retains the original valid error; a late thermal refusal may retain
a valid error for its accepted private prefix. The accepted restart retains its
original valid E and raw W/H throughout preparation.

## Common-clock automatic stepping

One forcing ID binds exact represented start/end times and the full nonnegative
absorbed-shortwave vector. The requested macro interval must fit inside it.
Reusing an ID requires identical operands; distinct forcing windows cannot
overlap. The owner is caller-driven: it does not derive precipitation phases,
astronomical source averages or a seasonal calendar.

Clock endpoints and trial durations must close exactly on a binary64 lattice
whose quantum is the next representable increment above the requested endpoint.
Integer ticks are bounded by 2^53. A zero minimum-step option means one tick;
maximum step is rounded down to the lattice. This can conservatively refuse
decimal endpoint combinations that lack exact duration closure.

After sources, E0 and the macro duration N ticks remain fixed through every
retry. A trial of n ticks receives the downward allowance

```
headroom = downward(B - E0)
quota    = downward(headroom * downward(n/N)).
```

The trial starts from the entire accepted private W/H mesh, E and common time.
For its inherited reference, the owner proves all component boxes physical and
uses an outward maximum-temperature bound over those boxes:

```
Tref_max = max(Tf, max_i T_i(H_i ± upward(E/A_i)))
           + h max_i(S_i/C_i).
```

The unchanged mesh core separately proves its backward-Euler root residual and
the same-time raw-endpoint defect U from the canonical point. Global thermal
contraction then permits `Enew = upward(E + U)`. The actual charged increment
is the upper endpoint of outward `Enew - E`. It must fit quota and Enew must fit
B. The stage-root bound is not added again; U already includes the algebraic
defect of the actual endpoint. A final all-cell uncertainty-domain check gates
each accepted private step.

Expected numerical budget/stagnation failures, rounded-charge failures and
post-step uncertain physical-domain failures may halve the common proposal within the
fixed attempt and minimum-step limits. Accepted steps may double it up to the
maximum. A rejected trial never advances an individual cell, resets E0 or
repeats A. Unsupported/protocol/enclosure failures are terminal.

## Atomic publication and observable limits

Before producing a candidate, the owner prepares W/H, E, time, consumed IDs,
forcing history, liquid outbox, hydrologic projection and a discrete ledger.
The opaque candidate binds both its owner and exact accepted base bundle.
Commit checks those identities and swaps the one prepared immutable bundle.
Foreign or stale candidates refuse. A late preparation failure retains its
private prefix and spent work but leaves accepted state/history unchanged.

The ledger independently encloses total mass/storage changes, recorded external
movements, source projection, absorbed sunlight and backward-Euler endpoint
emission quadrature. The quadrature is a discrete diagnostic, not an exact
continuous radiation integral; signed closure is not the acceptance proof.

The liquid projection partitions the outbox-derived liquid supply using the
frozen surface's baseline temperature and other hydrologic parameters, while
retaining original precipitation diagnostically. It does not update those
inputs from thermal H or deliver the outbox to a live
hydrologic owner. Delivery acknowledgement and downstream rebuilding remain
separate required production work.

The default structural caps include 4,096 cells, 32,768 edges, 128 thermal attempts
and 128 accepted steps per request. Each request also reserves scalar/field work
and retained cell/edge leaves before sources. Cumulative observed work is held
within the current owner instance; restart construction does not restore its
past work totals or committed-interval counter. These limits are not a durable
resource quota, response-size bound or production throughput guarantee.
Allocation failure may throw without producing a terminal receipt.

## First bounded qualification

The single frozen native invocation passes **328 checks** across 23 preparations:
seven candidates and 16 expected preparation refusals. Six commit observations
include four successful publications and the expected foreign/stale refusals.
It starts 11 A calls; ten return receipts and one deliberately refuses the
unfunded initial-liquid withdrawal. All 25 thermal calls return, with 800
reconstruction leaves, 136 sweeps, 274 coordinate starts, 12,166 scalar
evaluations and 961 field evaluations.

| Control | Observed result |
|---|---|
| Combined-capacity donor | The 0.5 kg withdrawal carries exactly 0.75 J; the quarter-step reaches the rational BE root within the fixed 1e-10 J/m² check. |
| Committed source successor | Uses the actual prior restart at 0.25 seconds and finishes at 0.5 seconds; global E grows from 0.0836637 to 0.0969205 J against B=0.25 J. |
| Unequal-area zero-energy imports | E remains exactly 0.125 J through the source interval and an empty-source committed successor. |
| Wet thermal cell | The lake's retained W stays zero while absorbed sunlight and graph exchange change its H. |
| Adaptive sourced interval | Nine rejected proposals and nine accepted steps reach the common endpoint; A runs once. Final E=0.0714545 J fits B=0.1 J. |
| Physical three-cell, 60-second interval | Snow, rain, initial drainage, radiation and transport finish with E=9.92814 J, including inherited 7 J, within B=3340 J. |
| Late attempt-cap refusal | One private quarter-step succeeds, then preparation refuses with no candidate, consumed IDs or accepted-state change. |
| Uncertain source/domain refusals | The post-A raw prefix is retained with unavailable E; no thermal call or complete candidate follows. |

Observed driver time is 0.0652 seconds with 1,335,932 stdout bytes. These are
measurements of the small two/three-cell fixtures, not production performance.
The source, plan, literal inputs, native binary and library remain unchanged
through this one invocation. The rebuilt `a7db0b60…` library loads all eight
declared V3/V4 exports with zero generator calls. No annual study was rerun.

The independent reader was frozen before native execution. Its first actual
audit passes all 23 preparations, six commit records, 25 thermal receipts and
800 completed leaves, matches the ordered 328 native checks, and rejects all
15 altered-record controls. It verifies all 91 exact source snapshots and
reconstructs the global source/domain/quota/error arithmetic, source movements,
discrete ledger, liquid projection and accepted-state history. Historical
Gauss–Seidel proposal iterates and opaque C++ candidate allocations retain their
native-observation scope. The A replay covers normal-range 64-bit-significand
wide arithmetic; it is not a complete x87 exception emulator. The projection
reader uses its existing parent-scale arithmetic windows.

Two pre-outcome reader setup failures remain visible: an incorrect pure-test
refusal-code label and a mistyped launcher digest rejected before reader import.
Their corrections changed no native inputs or reader mathematics. The actual
audit required no correction or repeat. [Frozen sources, run and independent
audit](../runs/production-enthalpy-owner-review/README.md).

## Production integration remaining

The [production dependency contract](../runs/production-seasonal-integration-contract-review/README.md)
still requires a finalized terrain/sea/lake adapter, a physical source calendar,
original-source uncertainty, one-use liquid delivery and matching descendants.
Annual precipitation consumers currently spend precipitation before retained
snow exists; adding this owner without replacing that consumption would count
water twice. Terrain fixed-point retries must not become physical years.
Persistent W can accumulate under periodic forcing, so temperature periodicity
does not establish ice equilibrium. The annual glacier-ablation defect remains
open, and this internal owner does not change public API generation output.
