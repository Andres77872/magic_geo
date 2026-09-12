# Native fixed-time residual certification

The explicit terrestrial thermal owner now has an opt-in native endpoint certificate based on a continuous reconstruction of the actual numerical state. The first bounded qualification improves both six-hour enclosures, but the six-hour melt-crossing target is still unproved; native acceptance correctly refuses that step. The change is a prerequisite for practical automatic stepping: the [existing direct Picard endpoint rectangle](terrestrial_fixed_duration_continuation.md) bounds local error, but its width can dominate numerical error and force very short steps. The new certificate changes the physical acceptance proof; the two SDIRK stages and their raw endpoint remain the same.

This is an internal fixed-water, fixed-forcing operation. Ordinary world generation still uses its current climate and annual ice model. A later [automatic continuation overload](terrestrial_automatic_continuation.md) derives tubes and step durations while enforcing cumulative error and work limits. A physically specified source calendar, original-source W/H/Ea accuracy, external conservative water delivery, spatial exchanges and coupled snow/ice feedback remain open. In particular, the annual glacier constructor/ablation incompatibility is not repaired by these numerical increments. [Full current status](current_simulation_review_status.md)

## Research decision

Validated integration literature distinguishes enclosure correctness from useful enclosure width. Dependency and wrapping can cause a rigorous method to demand tiny steps or stop; retaining polynomial dependence can reduce this overestimation.[1] That observation supports replacing the coarse local error enclosure, but does not validate this implementation or supply its nonsmooth phase proof. Our method is a residual certificate for an endpoint reconstruction, not a Taylor integration method applied across a phase kink.

The earlier [exact Hermite helper](../runs/seasonal-cryosphere-phase-segment-review/hermite-certificate/README.md) used a single phase polynomial for its entire trace. That restriction could reject a raw rounded latent-boundary state even when a source-free physical continuation exists. Its stronger offline event result remains separate from native acceptance. The new implementation uses polynomial leaves where a branch is proved and a global phase-law enclosure elsewhere. It neither fits a phase root nor moves the endpoint to a threshold.

## One mathematical curve through the raw endpoints

For the global ideal field F, represented initial state Y0, actual selected endpoint Y1 and exact duration h, define the cubic Bernstein controls

`B0=Y0`, `B1=Y0+h F(Y0)/3`, `B2=Y1−h F(Y1)/3`, `B3=Y1`.

These expressions define one exact real curve using the declared binary64 constants as exact inputs. Native interval arithmetic encloses these expressions, including ideal endpoint fluxes. The first and last controls are the raw singleton states. No separately rounded cubic is substituted, so the curve passes exactly through Y0 and Y1. The residual therefore already includes the numerical endpoint error; the nominal equation allowance is still a separate acceptance gate and is not added again as physical error.

The request declares N in `{1,2,4,8,16,32,64}` before work begins. Repeated outward de Casteljau bisection produces N equal leaves of this same cubic. Each leaf has a complete H/Ea range from its coefficient hull. Its physical temperature domain is checked independently of the original Picard tube. A physical numerical endpoint does not by itself prove a physical interpolating curve.

For W>0 the continuous global temperature identity is

`Ts(H)=Tf+min(H,0)/(Cb+W ci)+max(H−W Lf,0)/(Cb+W cl)`.

For W=0, `Ts=Tf+H/Cb`; for present atmosphere, `Ta=Tf+Ea/Ca`. Airless columns require Ea=a=k=0 throughout. The exact product W·Lf is enclosed outward, without treating its rounded product as a new physical boundary.

## Branch polynomials and crossing leaves

A leaf is polynomial only when its whole H coefficient hull is proved dry, solid, mixed or liquid. On that branch Ts is affine in H or constant; Ta is affine in Ea. Hence the radiative/sensible field along the cubic has degree at most 12. Formal Bernstein multiplication and degree elevation use their exact positive binomial ratios, enclosed outward. Signed polynomial coefficients are retained; they are not clipped because their represented function has nonnegative temperature or fourth power.

On leaf j use its unit coordinate u and δ=h/N. The residual is

`Rj(u)=dYj/du−δ F(Yj(u))`.

Its componentwise absolute integral already has units J/m². There is no second multiplication by h or δ. For degree n Bernstein residual coefficients bi,

`∫₀¹ |Rj(u)| du ≤ (Σi |bi|)/(n+1)`.

Native interval coefficient magnitudes and the sum/division are outward bounds. Surface and atmospheric absolute integrals are added, so opposing component errors cannot cancel.

A leaf that straddles or cannot distinguish a latent threshold uses a conservative interval residual. Opposite H/Ea corners bound the ideal field over the physical coefficient rectangle because Fs decreases with H and increases with Ea, while Fa has the reverse signs. The derivative coefficient hull minus δ times that field encloses the leaf residual. Its component absolute maxima bound the unit-coordinate integrals. This handles a phase crossing or contact without assuming differentiability of Ts at a kink. The fallback can be wider and may still fail the requested budget.

## Why the residual bounds endpoint error

For fixed W and coefficients, Ts is continuous and nondecreasing in H. Over nonnegative temperatures the field-difference matrix has nonnegative off-diagonal entries. Its surface column sum is `−(1−a)` times the nonnegative surface-radiation secant; its air column sum is minus a nonnegative air-radiation secant. Thus the physical flow is nonexpansive in the joint L1 energy norm, including phase-crossing secants. The airless case is scalar nonincreasing surface flux.

The original strict global Picard inclusion still proves physical point-start existence through h. The reconstruction is separately proved physical and need not stay inside that Picard rectangle. Applying the L1 residual inequality gives

`|H(h)−Y1,H| + |Ea(h)−Y1,Ea| ≤ ∫₀ʰ ||Y′−F(Y)||₁ dt ≤ U`.

The invariant lower physical faces and the upper bound on total-energy growth give finite physical continuation for the inherited fixed-W reference as well. The existing owner recurrence adds U to inherited E once, then checks the full final uncertainty domain and immutable cumulative budget. No event-time transport term, source-error reset or state clamp is introduced. The scope remains [`canonical_projected_W_prescribed_import_J_reference_v1`](terrestrial_coupled_ownership.md); this does not bound original-source water or energy errors.

## Native contract and work limits

`EndpointCertificate::hermite_residual` is allowed only with `Goal::fixed_duration` and a positive dyadic leaf count no larger than 64. The default `direct_tube` policy requires zero unused leaves and retains the existing v2/v3 request and receipt format. Invalid combinations refuse before any stage call.

Opt-in requests publish v4. The guard retains its original direct Picard endpoint rectangle and a separately available `direct_tube_state_error_j_m2`. The selected `physical_event_state_error_j_m2` is the reconstruction's same-time joint bound U; it is not distance to that unchanged rectangle. The request explicitly chooses the proof basis. There is no post-refusal substitution or promotion of an external proof.

The reconstruction reports whether it started and completed, started leaf count, ordered completed leaf records and separate component integrals. If a leaf fails its domain/arithmetic check, it is counted as started but is not appended as a zero-valued completed proof. Aggregate bounds remain null until completion. Refused phase receipts do not provide an accepted final state, even when diagnostic numerical candidates exist.

The owner validates the complete plan and its aggregate leaf reservation before any mass or thermal call. Reconstruction work is separate from native stage/scalar-flux counts. Fixed arrays have degree at most 12 and at most 64 curves; all subdivision and polynomial loops have source bounds. The maximum configured reservation is 32,768 leaves per owner attempt. A failed attempt spends its observed work while accepted physical state remains unchanged.

The consumer binds a complete native accepted certificate to the selected raw trial, duration, ordered leaf count, component sums and selected error. As with the existing owner, these structural checks are for internally produced typed receipts, not authentication of arbitrary external JSON.

## Qualification

One predeclared launch completed all 13 direct phase requests, two owner phase requests and one standalone reconstruction helper. The new qualification executable recorded **57 checks with one target failure**, exit code 1. The two six-hour policy pairs retain their declared local physical budget of 3340 J/m²; the small controls use 0.01 and the tight-budget refusal uses 1e−30 J/m². The failure is retained; no duration, target or expected result was tuned after execution, and the qualification was not rerun.

| Six-hour control | Direct bound (J/m²) | Reconstruction bound (J/m²) | Native outcome at 3340 J/m² |
| --- | ---: | ---: | --- |
| Dry radiative/sensible column | 275997.9769669578 | 103.69465239473821 | Accepted with reconstruction |
| Melt-crossing column | 488490.7372019022 | 12195.388728155807 | Refused with either certificate |

A structural review of the saved melt receipt attributes about 11,716 J/m² of its sufficient bound to the 63 polynomial leaves and 479 J/m² to the single global crossing leaf. Refining only that crossing leaf therefore does not address most of this bound. These contributions do not distinguish actual endpoint error from the reconstruction or enclosure overestimate; no such inference is made.

The numerical H/Ea endpoints are exactly identical across each policy pair. The melt reconstruction completes all 64 leaves, including one global fallback leaf, but cannot certify the requested target. Its upper bound does not establish that the actual endpoint error exceeds the target; no new ODE reference was run. The qualification executable and registered CTest retain that failing target assertion. This is not an all-green numerical qualification or automatic-stepping result.

The small raw 1.1×1.1 threshold and lower-crossing controls accept with at least one global fallback leaf and no energy adjustment. The undirected equilibrium also accepts without an event-time claim. The tight budget and all five invalid policy/count combinations refuse. Seven helper-only corruptions of the actual accepted dry receipt are rejected by the coupled consumer.

The standalone undershoot helper has physical endpoints but a nonphysical reconstructed interior. It refuses after two started leaves and one completed leaf; aggregate residual bounds remain unavailable. It is a proposed mathematical curve, not a phase call or an exact ODE solution.

A separate two-step dry owner plan reaches 43,200 seconds with raw H/Ea carry and commits atomically. Its inherited joint error grows from 7 to 110.69465239473823 to 208.34697564950065 J/m². A 127-leaf aggregate reservation refuses before physical work; the accepted two-step plan reserves and completes 128 leaves. Stale replay refuses in the driver assertion. The private token and a separate pre-stale restart frame are not serialized, so the exact offline audit does not independently replay that token check. No mass/source operation is invoked.

The new executable observed 15 phase receipts, 20 stages, 57 scalar flux evaluations and 514 started reconstruction leaves, including the helper's partial prefix. Its measured process time was 0.01699 seconds on this build; this is a local observation, not an annual performance claim. All 84 frozen source paths remained unchanged across execution.

The separately executed existing fixed-duration, pipeline and unavailable controls pass 159, 18 and 5 checks respectively. Their complete stdout bytes exactly match the previous frozen package. The independent reconstruction core and seven pure algebra controls were frozen before the native launch; the final independent exact rational audit validates all 15 phase receipts, 20 stages and 513 completed reconstruction leaves, including the helper's partial prefix, and rejects all ten tampered retained records. It also verifies the owner's raw carry, inherited error, atomic publication and both identical endpoint pairs. The 514 started leaves include the one domain-refused leaf. No solver or reference was rerun by this audit.

Two reader failures are preserved before the successful offline replay. The first reader incorrectly demanded that every predeclared qualification target pass; its revised adapter reports the failed target separately and requires the driver failure count to be fully explained. The second reader passed a list where the existing outward arithmetic helper expects a tuple, bypassing its exact-zero shortcut for airless sums. A one-site tuple conversion and two pure regressions corrected that adapter dispatch. These are post-outcome reader corrections, with each version frozen before its replay. The native output, target, source and previously frozen mathematical core are unchanged. The final offline replay took 3.1131 seconds and does not convert the native qualification into a pass.

No annual, original-source reference or world-generation run was executed. At this closed qualification, automatic duration/tube selection was the next requirement, especially around melt crossings. The later [automatic continuation](terrestrial_automatic_continuation.md) now supplies that bounded fixed-water mechanism. The broad production limitations above remain unchanged.

[1]: https://www.cs.toronto.edu/pub/reports/na/Taylor_Models_ODES_2006.pdf "Neher, Jackson and Nedialkov, On Taylor Model Based Integration of ODEs, revised 2006; SIAM J. Numer. Anal. 45(1), 236–262 (2007), sections 1–3"
