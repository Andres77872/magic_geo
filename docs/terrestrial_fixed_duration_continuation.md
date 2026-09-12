# Fixed-duration continuation through terrestrial phase boundaries

The coupled terrestrial owner needs to carry its actual represented state through a melting or freezing transition. A fitted phase event can return the rounded value of `W*Lf` on the opposite side of the exact latent boundary from the intended outgoing branch. Declaring that state liquid or mixed prematurely fails the existing strict branch guard. Shifting H to the next representable number would introduce an unmodeled energy change.

The new `fixed_duration` goal advances the same fixed-W surface/air equations to a declared time using their global phase law. It proves a same-time endpoint enclosure, without claiming an earliest phase event or an interval free of phase events. The existing `within_branch` and `next_phase_boundary` goals keep their stricter phase interpretations. This is a numerical continuation capability within the [explicit coupled owner](terrestrial_coupled_ownership.md); it does not initialize a production snow reservoir or change the annual glacier model.

## Physical model and why raw enthalpy matters

Snow storage affects both liquid-water availability and surface energy exchange. Detailed land models represent precipitation, phase changes, liquid transfer and thermal exchange as coupled mass and energy processes. GLASS, for example, explicitly retains the heat carried by precipitation and liquid transfers alongside its snow energy balance.[^1] A numerical boundary repair that adds unaccounted heat would undermine this accounting before any downstream hydrology calculation.

For the present, simpler independent-column model, the surface state is freshwater mass density W and reference enthalpy H. Dry substrate heat capacity Cb is strictly positive. The surface temperature is the continuous piecewise function

```
W = 0:       Ts = Tf + H/Cb
W > 0, H<0: Ts = Tf + H/(Cb + W*ci)
0≤H≤W*Lf:   Ts = Tf
H>W*Lf:     Ts = Tf + (H-W*Lf)/(Cb + W*cl)
```

When atmosphere is present, `Ta=Tf+Ea/Ca`. An airless column has exactly zero Ea, atmospheric absorptivity a and sensible exchange k. With prescribed incident sunlight S and surface albedo α, the thermal vector field is

```
Fs = (1-α)*S + a*σ*Ta^4 - σ*Ts^4 - k*(Ts-Ta)
Fa = a*σ*Ts^4 - 2*a*σ*Ta^4 + k*(Ts-Ta)
```

Fa is exactly zero for an airless column. The temperatures must remain nonnegative. These equations omit lateral exchange, moisture/latent atmospheric coupling, evolving optical properties and layered snow conduction. Enthalpy is the appropriate state for retaining sensible and latent energy, but choosing enthalpy alone does not supply those missing physical processes or observational calibration.[^2]

At fixed positive Cb and fixed W, Ts is continuous and locally Lipschitz in H across both phase boundaries. The flux is consequently locally Lipschitz on a bounded physical H/Ea domain. A solution can cross a phase boundary without a discontinuity in stored energy or an externally inserted impulse. Its derivatives need not have the smoothness required to infer high-order convergence across that crossing.

## A priori flow enclosure

This section gives the implementation's sufficient enclosure argument. It is a direct finite-box argument for these equations, not an assertion that a general-purpose validated ODE package or a published snow model certifies this implementation. Validated ODE methods distinguish an a priori existence enclosure from a later tighter endpoint enclosure; conventional numerical convergence alone does not provide both.[^3]

Let `x0=(H0,Ea0)` be the actual represented initial state and B a proposed finite rectangle. Every point in B must have nonnegative surface and air temperature. Temperature is monotone in its own energy coordinate. Surface flux decreases with H and increases with Ea; air flux increases with H and decreases with Ea. Opposite corners therefore bound each flux component, including across the continuous phase-law kinks. Outward interval arithmetic supplies an enclosure F(B).

For a fixed positive duration h, require

`x0 + [0,h]*F(B) ⊂ interior(B)`

in each active coordinate. In the airless case, the inactive air interval and flux are exactly zero; a strict two-dimensional interior is neither required nor claimed. The arithmetic includes the exact represented constants and conservative bounds on the original latent product, rather than silently replacing the physical boundary by its rounded display value.

The strict inclusion contains x0 and excludes a first exit from B: before any proposed exit, integrating the bounded vector field places the solution inside the displayed Picard image, which lies strictly inside B. Local existence and uniqueness follow from the locally Lipschitz field, and boundedness permits continuation through h. Thus the endpoint lies in

`Xh = x0 + h*F(B)`.

This proof precedes numerical stage calls. It does not assume the computed stages are accurate, that the trajectory stays in one phase, or that the surface flux keeps one sign. Failure to prove the physical domain or strict inclusion refuses the request. No state clipping or automatic enlargement of B is performed.

## Numerical endpoint and inherited error

The numerical candidate uses the existing two SDIRK2 thermal stages, including their actual global phase-law evaluations, nonlinear tolerances, represented coefficients and signed second-stage reference. Both stages must be accepted by the existing backend. The original outward bounds on nominal stage/quadrature equation defects remain mandatory. The new goal permits the first stage and endpoint to leave the annotated initial branch, because it does not give them a within-branch interpretation.

For the raw numerical endpoint `y=(Hy,Eay)`, the direct physical endpoint bound is

`e = max(|Hy-Xh.H.lower|, |Hy-Xh.H.upper|)`

`    + max(|Eay-Xh.Ea.lower|, |Eay-Xh.Ea.upper|)`.

Every operation is enclosed outward. Acceptance requires the upper bound to meet the caller's unchanged physical energy budget. The same-time error is independent of a phase-hit locator, so physical time error is exactly zero. The bound is valid even if the direct rectangle is loose; a loose result must refuse an unmet budget. It supplies no automatic efficiency or convergence-order guarantee.

The owner's fixed-W canonical-reference contract carries a joint inherited energy bound E. Its existing L1 nonexpansivity argument gives `Enew ≤ E + e`, with the same pre/post uncertainty-domain checks and immutable cumulative policy. There is no event-time transport term for this fixed-time step, and E is not reset at a phase boundary. The separate original-source W/energy uncertainty extension remains unimplemented: a fixed-time primitive does not turn canonical-reference accuracy into original-source accuracy.

## Interface, state ownership and evidence

`Goal::fixed_duration` is an explicit caller choice. `incoming_branch` must still contain the raw initial H and agree with dry versus positive-W status; it is an initial-state annotation in this mode. The new goal omits outgoing-direction and stage/endpoint branch restrictions. It must return the exact planned duration, end time and zero remainder on the owner's common binary64 lattice. A physical forcing boundary cannot be crossed.

With the default `direct_tube` certificate, the phase receipt identifies these semantics as `terrestrial_phase_segment_receipt_v3` and records `fixed_time_endpoint_proved`. First-hit and no-hit proof flags remain false. In that default mode, the shared `physical_event_state` and `physical_event_state_error_j_m2` fields hold the fixed-time endpoint enclosure and error; their historical names do not imply an event. Old goals retain their v2 receipt format. The error consumer requires an accepted native fixed-duration receipt and its fixed-time proof flag; changing a diagnostic label cannot turn a refused component into an accepted owner candidate.

The owner continues to prepare all cells privately. It publishes state, inherited errors, source history, liquid outbox and hydrology projection only after complete common-time coverage. A late projection failure, insufficient work reservation or failed error budget leaves accepted state unchanged. The capability does not consume additional water, alter an import, or acknowledge external liquid delivery.

The [focused continuation evidence](../runs/seasonal-fixed-duration-continuation-review/README.md) records the fixed inventory, implementation, actual receipts and independent checks. The decisive changed plan starts again from the original initial state, fits its melt event, carries the actual event output through fixed-duration continuation, and then attempts an ordinary liquid segment from the new accepted endpoint. The previously refused owner bundle is not promoted into a committed state.

The declared launch passes all 159 checks: 14 preparations produce five candidates and nine refusals, and three commit attempts produce two commits and one stale-candidate refusal. It performs 11 phase calls, 52 stages and 150 scalar flux evaluations, with no mass calls. The full plan retains the event's H=`1.2100000000000002` at t=`0.17750000251544407`, reaches H=`1.4999999845115706` at t=0.25 through the new goal, and then reaches H=`1.7499999771752737` at t=0.3125 through the ordinary liquid goal. The inherited error grows from the event's approximately `9.8326e-9` to `1.91796e-8` J/m² at the final endpoint; it is never reset.

The independent exact retained-data audit verifies the complete 14-preparation/three-commit output, including all 11 phase records, 44 duration trials and 52 stages. It rejects all 11 tampered records and independently matches the five helper-semantic controls. The audit performs no new solver or reference integration. The enabled and unavailable legacy pipeline controls retain byte-identical output, and the rebuilt native library loads through both existing Python API versions without generation calls.

Further controls cover lower-boundary crossing, a latent-boundary tube without a proved flux direction, unchanged rejection of a false initial branch, exact endpoint coverage, work and error limits, and late refusal without publication. These are bounded synthetic-column controls. They do not resolve seasonal source scheduling, continuous precipitation, annual glacier ablation, snow albedo feedback, mesh exchange or performance over a year.

A later explicit [native reconstruction option](terrestrial_native_residual_certificate.md) retains these v3 direct-tube semantics by default and introduces a v4 residual basis when requested. It preserves the same global stages and raw endpoint, with bounded dyadic polynomial/global leaves. Its six-hour dry target passes, while the single-step melt target remains unproved. The subsequent [automatic continuation](terrestrial_automatic_continuation.md) privately derives tubes and partitions the same melt interval into accepted steps; that separate scheduling qualification preserves this fixed-duration contract and the earlier failed target.

## Sources

[^1]: Zorzetto, E., Malyshev, S., Ginoux, P., and Shevliakova, E. [A global–land snow scheme (GLASS) v1.0 for the GFDL Earth System Model: formulation and evaluation at instrumented sites](https://gmd.copernicus.org/articles/17/7219/2024/gmd-17-7219-2024.html). *Geoscientific Model Development* 17, 7219–7244, 7 October 2024. Sections 2.2–3 and Figure 1 describe phase inventories and heat carried by water transfers. Accessed 11 September 2026; no implementation code imported.
[^2]: PISM Authors. [Modeling conservation of energy](https://www.pism.io/docs/manual/modeling-choices/dynamics/energy-balance.html). PISM 2.3.2 documentation, accessed 11 September 2026. Enthalpy treatment of sensible and latent energy provides physical context; PISM is not a validation authority for this independent-column solver.
[^3]: Nedialkov, N. S., Jackson, K. R., and Corliss, G. F. [Validated solutions of initial value problems for ordinary differential equations](https://www.sciencedirect.com/science/article/pii/S0096300398100838). *Applied Mathematics and Computation* 105(1), 21–68, October 1999. Sections 4–5 distinguish a priori existence enclosures from endpoint enclosure construction. The paper's Taylor-series algorithms are not imported or claimed to apply unchanged to a nonsmooth phase law.
