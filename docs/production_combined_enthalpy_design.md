# Candidate production enthalpy model: preserve the existing mesh

Status: revised source-based mathematical design, 2026-09-11. Revision 2 states the regularity and finite-operand assumptions identified by independent review; its original frozen drafts are retained. A new [physical backward-Euler mesh core](production_enthalpy_mesh.md) now implements the fixed-W combined-temperature option below. That core has separate algebraic and same-time residual gates; production cutover and calibration remain open. The independent two-temperature owner remains a separate model.

## Why this candidate

Production currently combines surface and hydrostatic atmospheric sensible heat capacity in one temperature, uses a prescribed effective TOA emissivity and albedo, and exchanges heat over symmetric positive mesh edges. A new enthalpy state can preserve these declared assumptions without inventing a two-temperature absorptivity or sensible-exchange coefficient. It adds a new explicit approximation: retained ground water shares the combined column temperature. This may underresolve actual snow-surface/air temperature differences and needs its own scientific validation.

Snowpack energy, moisture and atmospheric transport must be accounted together in a production model. ZEMBA explicitly evolves snow coverage from accumulation and surface-energy ablation while including atmospheric heat/moisture transport; its more elaborate radiative and hydrological assumptions do not establish parameters for this repository. [ZEMBA v1.0, sections 2–2.2](https://gmd.copernicus.org/articles/18/2479/2025/index.html)

## Declared fixed-source thermal problem

For a fixed finalized mesh, require finite positive ci, cl and Lf, finite Tf>=0, and prescribed bounded/integrable nonnegative insolation. Prescribe finite cell area A_i>0, combined non-water sensible capacity C_i>0, represented water W_i>=0, emissivity epsilon_i>=0, albedo alpha_i in [0,1], and each undirected conductance K_ij=K_ji>=0 exactly once. Keep the existing physical-column atmosphere and geometry construction. Do not interpret the combined capacity as a separately evolving atmospheric reservoir. H_i is enthalpy density relative to frozen water at Tf, with the combined non-water sensible term referenced at Tf.

For exposed land, define the global phase law

T_i(H_i) = Tf + min(H_i,0)/(C_i+W_i ci)
                 + max(H_i-W_i Lf,0)/(C_i+W_i cl).

This includes the dry W=0 limit and the mixed-phase plateau. The physical domain requires H_i >= -(C_i+W_i ci)Tf. For existing sensible-only marine cells, use W_i=0 in this new retained-ground-water reservoir and keep the current effective ocean mixed-layer capacity within C_i. Their marine water is not zero physically; it remains a distinct existing sensible-only compartment. This candidate does not yet model marine freezing. Lakes need an explicit final-mask/restart contract rather than being silently treated as land or marine during terrain retries.

The thermal equation would be

A_i dH_i/dt = A_i[(1-alpha_i)S_i(t)-epsilon_i sigma T_i(H_i)^4]
             + sum_j K_ij[T_j(H_j)-T_i(H_i)].

The S_i(t) source must retain the production astronomical forcing interpretation and exact intervals. Prescribed constant interval averages define a different forcing problem from the true time-varying insolation; their temporal approximation cannot be hidden in a solver residual. Source W, coefficients and graph stay fixed during this equation's certified thermal interval. A changing albedo, conductivity, atmospheric pressure, geometry or water inventory creates a new explicitly modeled source/parameter boundary and needs additional analysis.

When every retained W_i=0, H_i=C_i(T_i-Tf), this equation reduces algebraically to the existing combined-temperature mesh equation. That identity is a compatibility target, not an assertion that separately rounded endpoints will be bitwise identical.

## Weighted contraction and a possible certificate

The following argument is a derivation for the equation above, not a claim imported from ZEMBA. On T>=0 every T_i(H_i) is continuous, monotone and globally Lipschitz; its piecewise slopes lie between 0 and 1/C_i. At smooth points write d_i=T_i'(H_i)>=0 and use total energy variables X_i=A_i H_i. The Jacobian has off-diagonal entries

J_ij = K_ij d_j/A_j >=0

and diagonal

J_jj = -4 epsilon_j sigma T_j^3 d_j - sum_i K_ij d_j/A_j.

Every column sum is -4 epsilon_j sigma T_j^3 d_j<=0. Thus the induced 1-norm logarithmic bound is nonpositive. Across phase kinks, secant slopes remain nonnegative; the same pairwise monotonicity argument yields contraction in the area-weighted norm ||delta H||_A=sum_i A_i |delta H_i|. This requires the symmetric prescribed graph and the same source/parameters for both compared trajectories.

For an absolutely continuous reconstructed path Y_i(t) (for example continuous piecewise-C1), with integrable residual r_i=dY_i/dt-F_i(Y,t), the resulting candidate same-time bound is

E_A(t1) <= E_A(t0) + integral(sum_i A_i |r_i(t)|) dt.

The original design required exact/outward curve construction, true-flow existence and domain bounds over the complete mesh, nonlinear-stage error accounting, conservative edge arithmetic and a fully retained residual enclosure. The new core supplies these for its represented fixed-W, constant-source interval; full production composition remains open. Local independent-column Picard boxes and previously certified two-temperature radiative polynomials cannot be relabeled as this proof. During the mixed plateau, heat still changes H even though T' is zero; an algorithm that evolves temperature alone loses this storage.

A global joule bound does not automatically give useful per-cell accuracy. E_A/A_i is valid but can be excessively large for a small cell; a claimed uniform J/m2 or phase-mass target needs a separately designed componentwise error propagation or explicit area-weighted publication scope. Off-diagonal transport can move error between cells, so per-cell error may grow even while the global norm contracts. Independent per-cell budgets cannot simply be reused.

## Sources and cutover obligations

The [combined-temperature mesh owner](production_enthalpy_owner.md) now supplies a canonical initial-inventory A source operation with capacity explicitly C_i. It carries one area-weighted global error through source events and common-clock mesh steps. Initial liquid withdrawal feasibility remains pre-batch; imported rain or later melt cannot fund it. Original-source mass and joule uncertainty remain separate from canonical closure. The independently implemented two-temperature owner remains a different model.

A complete production cutover must start after a validated terrain/sea/lake context, preserve physical time across real intervals, and avoid advancing physical snow or water during depression/erosion retries. It must partition precipitation once, retain snow, deliver liquid once, rebuild changed lakes/flow and all dependent natural/social records, then publish matching provenance. Persistent W need not become periodic: accumulation or prescribed drainage can cause a secular mass trend even under periodic climate forcing. A periodic sensible-temperature convergence test alone cannot certify a water/ice equilibrium.

The first core explicitly chooses the combined-temperature reduction and a global area-weighted joule error norm. Its small fixed-W qualification covers zero-water equivalence, conservative edge exchange and latent storage. The mesh owner implements globally composed explicit source transactions; its separate qualification and scope are recorded in the linked contract. Source calendars, original-source error and the terrain fixed-point versus physical-time cutover still need implementation and qualification. This note authorizes no repeat of closed annual studies and claims no fixed annual glacier ablation.
