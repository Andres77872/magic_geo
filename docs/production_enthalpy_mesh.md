# Combined-temperature enthalpy mesh core

The native core now implements the combined-temperature model selected in the
[production design](production_combined_enthalpy_design.md). It supplies a
physical backward-Euler step and a separate bound on its same-time endpoint
error. It is an internal numerical building block; ordinary generation still
uses its existing climate and annual ice path.

## Model and dependency contract

The caller supplies the existing `SurfaceEnergyColumn` area A, combined sensible
capacity C and effective emissivity, plus the canonical symmetric positive
`EnergyTransportEdge` graph. C includes the prescribed surface and atmospheric
sensible reservoirs. Retained water W contributes its own sensible and latent
storage at that same temperature. There is no additional atmospheric energy
variable. This is an explicit approximation whose realism requires validation.

For one interval, all represented coefficients, W and absorbed shortwave S
are fixed. Inputs require A,C,Tf,ci,cl,Lf,h>0, W,S>=0, emissivity in [0,1],
complete column coverage, and each positive undirected edge exactly once.

```
T_i(H_i) = Tf + min(H_i,0)/(C_i+W_i ci)
              + max(H_i-W_i Lf,0)/(C_i+W_i cl)
F_i(H)   = S_i - epsilon_i sigma T_i(H_i)^4
              + sum_j K_ij(T_j-T_i)/A_i
```

The certificate treats the binary64 sigma value `5.670374419e-8` and all supplied
operands as exact inputs. The latent product W Lf is enclosed outward, so a
rounded phase threshold cannot silently select the wrong branch. Mixed-phase
heat changes H while T stays at Tf. With W=0, the equation reduces to the
existing sensible equation through H=C(T-Tf).

The core validates the physical floor H>=-(C+W ci)Tf. A maximum-temperature
principle provides a noncircular true-flow existence bound:

```
Tmax = max(Tf, max_i T_i(Hinitial_i)) + h max_i(S_i/C_i).
```

The exact uniform-temperature enthalpies at this bound also supply a
backward-Euler supersolution; the zero-temperature physical floors supply a
subsolution. The represented proposal bounds may be wider. Proposal arithmetic
does not establish acceptance.

## Two independent acceptance conditions

Bounded coordinate Gauss–Seidel sweeps use safeguarded scalar Newton/bisection
proposals in H. The local equation is strictly increasing, including on the
latent plateau. Long-double proposal signs and successive-iterate changes are
untrusted numerical aids. There is no finite convergence guarantee; exhausted
work or stagnation causes a typed refusal.

For the actual raw candidate, outward arithmetic evaluates the complete global
field and the backward-Euler residual

```
R_i = Hcandidate_i - Hinitial_i - h F_i(Hcandidate).
E_stage = outward sum_i A_i absmax(R_i).
```

The physical resolvent is nonexpansive in the area-weighted L1 norm, so this
bounds the candidate's distance to the exact physical backward-Euler root.
The signed global energy balance alone cannot supply this bound: opposite
local defects can cancel. Each edge has one watt exchange used with opposite
signs at its endpoints; no balancing heat is inserted.

The second condition bounds the physical time-integration defect. It uses one
exact line Y(s)=Hinitial+s(Hcandidate-Hinitial), partitioned into N uniform
dyadic leaves with outward enclosures of each whole leaf. On leaf k, with local coordinate u in [0,1],

```
J_ki = (Hcandidate_i-Hinitial_i)/N - (h/N) F_i(Y_k([0,1]))
U = outward sum_k sum_i A_i absmax(J_ki).
```

The line is absolutely continuous and physical by convexity of the enthalpy
domain. Mesh contraction bounds the same-time endpoint error by U from the
canonical point start. The derivative comes from the global raw endpoint
difference, not subtraction of independently rounded leaf nodes. The U bound
already includes the actual endpoint's algebraic defect; E_stage is not added
again. Both independently specified budgets must pass before final H exists.

These bounds are total joules over the mesh. A cellwise consequence U/A_i can
be loose on a small cell. Transport does not preserve independent per-cell
error budgets. The core starts from one exact canonical point; the separate
[mesh owner](production_enthalpy_owner.md) carries inherited global error.

## Receipts and finite work

Requests and receipts are internal C++ interfaces with JSON observability.
Refusals retain available raw candidates, completed proof fields and started
work counts, while `final_enthalpy_j_m2` remains null. A partial sweep invalidates
the previous candidate's stage certificate. Each reconstruction leaf has a
completion flag; unavailable proof values serialize null. Historical sweep
norms lack historical raw iterates and are diagnostic rather than replayable
certificates. Allocation failure can throw without a terminal receipt.

Structural caps are 16,384 cells, 131,072 edges, 512 sweeps, 64 coordinate
iterations, 16,777,216 scalar evaluations and 64 dyadic leaves. Those maxima
can retain hundreds of MiB before JSON serialization. They are not a process
memory, response-size or production throughput guarantee. The first test driver
uses at most three cells and two edges with much smaller explicit work limits.

## First bounded qualification

The single frozen 19-request run passes **143 checks**, with nine acceptances
and ten expected typed refusals. It performs 55 started sweeps, 111 coordinate
starts, 3,444 scalar evaluations, 706 field evaluations and 640 reconstruction
leaves. The unchanged sensible solver is called once for the dry comparison.
Observed driver time is 0.0171 seconds with 619,020 stdout bytes; these are
measurements of this small test, not production performance guarantees.

| Control | Observed result |
|---|---|
| Heat into a mixed cell from its neighbor | H changes from 0.25 to 0.45 while T remains at Tf; neighbor H falls from 1 to 0.8. |
| Refreeze through mesh cooling | Initial H=(0.1,-0.5) reaches approximately (-0.12,-0.28), crossing the water-bearing column into the solid branch. |
| Unequal-area rational BE root | H approximately (0.6,0.2), with area-weighted total approximately 1; stage bound 2.13e-12 J, same-time bound 0.609375 J. |
| Same root, tighter temporal request | Refuses the 0.1 J endpoint budget despite passing the 1e-11 J algebraic budget. |
| Physical three-column wet mesh, 60 s | Stage bound 1.53e-9 J and same-time bound 2.86250 J pass the fixed 0.001/3340 J budgets. |
| Dry three-column equivalence, 60 s | Maximum temperature difference from the existing solver is 7.99e-11 K, below the fixed 1e-8 K test threshold. |
| Two-evaluation cap | Retains the changed first coordinate and refuses at the second, with the stale stage proof unavailable. |

The frozen independent Fraction reader passes on its first actual audit. It
accounts for all 19 receipts and 143 checks, verifies 87 exact source snapshots,
reconstructs all 640 completed leaves, and rejects ten altered records. Native
assertions about input immutability and work history retain their explicitly
limited observation scope; historical scalar iterates are not replayed. This
offline audit makes no producer or reference-trajectory call.

The native library `de637d5b…` builds and loads all eight declared V3/V4
generator exports with zero generator calls. An initial probe used incorrect
export names; that failed lookup is retained alongside the corrected
source-derived probe. No earlier annual study or closed target was rerun.
[Frozen implementation, run and independent audit](../runs/production-enthalpy-mesh-review/README.md)

## Research basis and remaining integration

Energy–enthalpy formulations retain phase-change storage and avoid conservation
problems associated with some temperature formulations. Tubini, Gruber and
Rigon analyze an implicit finite-volume formulation with an NCZ solver. Their
convergence theorem applies to their formulation; this implementation uses a
separately derived mesh residual certificate and does not inherit that theorem.
[Primary paper](https://tc.copernicus.org/articles/15/2541/2021/)

The [mesh owner](production_enthalpy_owner.md) now supplies a caller-driven
common clock, explicit source transactions and globally propagated canonical
error around this core. Production integration still needs an explicit finalized
terrain/sea/lake adapter, source calendar, original-source uncertainty and
conservative one-use liquid handoff. Terrain
fixed-point retries must not advance physical water time. Changing lakes and
flow require rebuilding affected descendants before publication. Persistent W
can accumulate over repeated climate periods; sensible periodicity alone does
not prove an ice equilibrium. Marine freezing and the annual glacier-ablation
defect remain open. Constant represented absorbed source accuracy is distinct
from accuracy for the astronomical forcing that it approximates.

Signed TR-BDF2 intermediate references do not satisfy this physical BE proof.
The separate surface/air W/H/Ea owner likewise cannot be relabeled as this
combined-temperature model. The new mesh owner carries this model's global
joule error and uses C consistently during mass events.
