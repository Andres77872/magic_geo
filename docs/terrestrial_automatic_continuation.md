# Automatic thermal continuation with explicit initial sources

The explicit coupled owner has a `prepare(CoupledAutomaticRequest)` overload. The request contains the accepted revision, a common endpoint, one immutable forcing span, finite work/step options and optional initial precipitation imports and liquid withdrawals. It contains no caller-supplied phase branches, tubes or segment schedule. Ordinary world generation does not call this independent column model.

After any initial source jump, every exposed cell advances privately with fixed raw W and prescribed shortwave. Lake and marine slots remain inactive. The overload uses the existing opaque candidate and atomic commit path; a refusal retains diagnostic trials and spent work while the accepted owner bundle stays unchanged. The actual initial liquid outbox is projected using the existing routine only after all exposed cells reach the common endpoint. With no events, the automatic path skips the mass kernel and preserves its earlier source-free behavior and serialized output.

## Initial source contract

Imports carry explicit IDs, cells, phase, mass and temperature; withdrawals request liquid from the accepted initial inventory. Their physical time is `receipt.initial.elapsed_seconds`, shared by the entire source batch. The final/commit clock is a later common endpoint and does not retime those events. Later precipitation or withdrawals require separate explicit intervals. Monthly precipitation totals alone do not determine source timing, phase or temperature.

The manual and automatic owners call the same initial-source validation and canonical jump implementation. IDs, event counts, source operands and the complete possible thermal work are checked before A. A executes once for a nonempty batch, with the dry substrate heat capacity and actual exposed-cell areas. Imports or later thermal melt cannot fund a withdrawal from the pre-batch inventory. Every actual movement is linked one-to-one to its original source; the outbox retains A's carried joules.

Each exposed column must pass the existing canonical jump certificate, including inherited error, uncertainty-safe initial liquid feasibility, raw post-A W/H, unchanged Ea and both physical domains. Only then is `thermal_initial` retained as a diagnostic post-source snapshot. Its time, revision and histories still equal the accepted initial snapshot; it is not independent restart authority. A failed jump can retain partial diagnostics but cannot start thermal work. The distinct `post_source_allowance_exact_tick_share_v1` marker identifies sourced automatic receipts; empty-source requests retain the older marker.

Thermal retries use the certified post-source W/H/Ea and error without rerunning A. A later refusal leaves the accepted owner and source history unchanged, retaining source work and the private diagnostic prefix. Complete preparation measures storage from the original pre-source state, subtracts A's external net enthalpy exactly once in the ledger, and commits state, error, event IDs, forcing history and outbox/projection together. Projection does not acknowledge delivery to an external river or reservoir.

## Derived tubes and exact clocks

The owner fixes a common quantum `q = ULP(T)` and requires the original start, final endpoint and their exact difference to lie on its binary64 lattice with at most `2^53` ticks. Progress, proposed durations and halving are integer operations. A proposal is capped by the configured maximum and remaining tick count; a refused proposal becomes `floor(n/2)`. After acceptance the next proposal may double, subject to the same limits. Every converted duration must close the represented clock exactly. No selected state, phase boundary or time is projected afterward.

The tube helper derives the incoming branch from raw H and the existing exact comparison against represented W times latent heat. It starts with an outward Euler range from the ideal initial field, pads each active energy range, and makes at most eight Picard proposals. A failed inclusion enlarges the next proposal using its Picard image. The existing physical-domain and strict finite-horizon Picard proof is the acceptance authority. Padding is only a proposal heuristic. Airless Ea stays exactly zero.

Each proposal helper call and each guard pass has a separate work count. These interval computations are distinct from the backend's scalar flux evaluation count. Every solver call reserves its full trial, stage, scalar-flux and reconstruction-leaf maxima before execution; refused calls remain charged. Original skeletons, pass caps, all proposed tubes, guard results, native receipts and allocation decisions are retained.

The configured minimum is either one common tick or a positive exact lattice duration. Padding at a physical floor, an unrepresentable allowance, a stranded final remainder smaller than the minimum, or a work cap can cause a conservative refusal. The algorithm does not guarantee completion for every admissible problem or every feasible partition. The older `CoupledLimits.max_segments_per_cell` applies to manual plans; automatic requests have their own per-cell attempt and accepted-step limits.

## Fixed initial error allocation

For each cell freeze post-source error E0, cumulative limit B and full macro length N ticks. E0 includes the previously accepted canonical error and the actual initial jump defect. Without sources it equals the accepted initial error. It is never reset at phase transitions. For a trial of n ticks compute a downward enclosure of

`quota(n) = (B - E0) n / N`.

The ratio is enclosed before multiplication to avoid unnecessary overflow. A nonpositive representable quota refuses before the solver. The native fixed-duration Hermite residual certificate uses that quota as its local physical target. Its numerical equation-defect gate remains separate.

After an accepted native receipt, the existing coupled consumer computes `Eplus = outward_add(E, U).upper` against the global B, where U is the same-time residual upper bound. Before carrying its raw endpoint the owner also requires

`outward_sub(point(Eplus), point(E)).upper <= quota(n)`.

This charges the actual rounded increase, including rounding in cumulative addition. Checking only U is insufficient. For consecutive accepted steps, the exact increases telescope; each is bounded by its fixed initial share, and their disjoint tick lengths sum to N. Thus the final error is at most B. No remaining-budget recomputation or rounded sum of quotas replaces this proof.

Rejected trials preserve carried W/H/Ea, E and accepted ticks. Only the proposal and work/diagnostics change. Halving is permitted for failed Picard/physical-domain proposals, numerical or local physical budget failure, stage refusal, rounded-charge failure, and a coupled consumer's final-domain or cumulative-budget refusal after its starting domain has passed. Invalid requests, source identities, protocol evidence, capability and exhausted work stop preparation.

## Earlier source-free qualification

The frozen eight-prepare suite passes 289 checks. The main control has one dry, one melting and one inactive lake cell, a six-hour common endpoint and a 3340 J/m² cumulative limit. Both exposed columns begin with inherited error 7 J/m². The dry cell accepts one six-hour step and ends with error bound 110.69465239473823 J/m². The melt cell rejects the six-hour and three-hour proposals, then accepts durations 5400, 10800 and 5400 seconds; its final cumulative bound is 770.7629373751752 J/m². The same raw melt operands and original target are retained. These are certified upper bounds, not measured trajectory errors.

The suite uses 11 actual thermal calls, 22 stages, 69 scalar flux evaluations and 704 reconstruction leaves. All 11 owner tubes prove inclusion on their first pass; three additional helper-only raw-branch controls also take one pass each. Thus this launch exercises duration reduction after physical-budget refusals, but does not empirically exercise multi-pass tube expansion, retry after tube refusal or automatic intervals starting at nonzero time. Cap, minimum-step, late-cell allowance, source identity, invalid policy, stale revision, foreign/stale commit and raw restart-reconstruction controls pass. The arithmetic-only discriminator confirms that fitting U and final B can still overspend a step's rounded charge.

The three unchanged compatibility controls retain byte-identical output with 159/18/5 checks. That qualification’s `1817cc07…` library loads V3/V4 symbols with no generator calls. The independent exact retained-data audit passes on its first run, checking all 11 phase receipts, 22 stages, 704 reconstruction leaves, 14 tube passes and eight preparations. All 289 source-bound assertions match; eight altered records are rejected. The unchanged earlier residual mathematical core is reused, while the automatic quota, clock, carry and tube reader was frozen before receiving outcomes. Opaque-token internals remain covered by source review and actual driver assertions; the offline reader checks their retained before/after observations.

The [complete evidence package](../runs/seasonal-automatic-owner-review/README.md) retains original inputs, all trials, source/binary snapshots, the pre-outcome design and reader, actual execution, independent review and prior file/library versions. No reference ODE or annual trajectory is run by this qualification.

## Initial-source and physical-clock qualification

The separate frozen source suite passes **375 checks** over 14 preparations and six commit attempts. Two complete sourced candidates commit; twelve requested preparations refuse as declared. The three-cell six-hour case imports 1 kg of snow at 263.15 K into cell 0 and .25 kg of liquid at 273.15 K into cell 1, and withdraws .1 kg of cell 1's initial liquid. Its actual jump raises the thermal error anchors from 7 to 7.000000014901162 and 7.0000000009313235 J/m². Final bounds are 107.27318769217135 and 770.7132715013338 J/m², below the unchanged 3340 limit.

Using that same committed owner, stale-revision and consumed-source requests refuse without new physical work. A subsequent explicit source batch at 21600 seconds imports .125 kg of snow at 268.15 K and withdraws .2 kg of initial liquid; it advances to 21660 seconds, retaining the prior errors and new jump charges. Its final bounds are 107.27329732376414 and 770.7133170011346 J/m². This supplies the nonzero-start automatic coverage absent from the earlier source-free qualification.

The suite starts five mass calls (four return), nine thermal calls, 18 stages, 52 scalar flux evaluations and 576 residual leaves. It retains two refused six-hour/three-hour melt trials, a true pre-batch liquid shortage at A, an uncertainty-safe liquid refusal after A, and a later-cell thermal allowance refusal after a completed earlier-cell prefix. All source validation and complete-work preflight cases reject before A. There is no empty A call in the automatic compatibility control.

The five unchanged controls pass with **byte-identical output**: source-free automatic (289 checks), manual source-owner (240), fixed-duration (159), pipeline (18), and unavailable backend (5). The new `8b74006b…` library loads V3/V4 symbols without generator calls. The [source-continuation evidence package](../runs/seasonal-automatic-source-review/README.md) retains the one native execution and its prelaunch inputs, bounds, sources, binaries and source reviews. No production, annual or reference-ODE run was launched.

The independent exact audit passes on the retained single run, matching all 375 source-bound checks, canonical A movements and jump certificates, both committed intervals, all nine phase receipts and 576 leaves. Thirteen altered records refuse. Two adapter failures are preserved: a local/module name collision before math, then an omitted expected mass-refusal exception in the tamper wrapper after actual records passed. Separate corrected reader versions complete the same unchanged data; no native run was repeated, and no mathematical core or target was changed. The initial pure synthetic quota witness and its correction are also retained. All new tube proposals pass on their first guard pass, so this extension does not add empirical coverage of multi-pass tube expansion.

## Scope

The error is relative to the canonical projected fixed-W reference with exact represented prescribed coefficients. It does not bound original water/source-energy representation uncertainty, event timing, spatial transport or downstream liquid delivery. The production climate model has a different temperature and atmosphere parameterization; this interface does not silently map between the models. The caller can now declare successive initial source batches on the physical clock. Deriving a production source calendar, snow/ice feedback and correcting the production annual glacier-ablation defect remain separate work. The [production dependency contract](../runs/production-seasonal-integration-contract-review/README.md) retains the incompatible climate-model assumptions and required hydrology cutover.

The earlier six-hour fixed-step melt qualification remains a closed failed target. An automatic test of the same physical interval is a new scheduling mechanism; it must preserve the original operands and cumulative target, record every retry, and cannot relabel that older failure.
