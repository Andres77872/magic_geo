# Elevation in the seasonal column climate model

Research/design decision, 2026-09-09. **The prescribed-column adapter and explicit C++ seasonal producer are implemented and tested; Python/configuration integration remains open.** See the [native integration record](seasonal_climate_native_integration.md). This note does not describe validated mountain temperatures or a completed coupled atmosphere. The numerical energy foundation and its integration gates are described in [the seasonal energy-balance research note](seasonal_energy_balance_model_research.md).

## Recommended first model

Use a prescribed hydrostatic pressure distribution to determine each column's atmospheric mass, infrared opacity and atmospheric transport coefficient. Keep diffusion in **actual temperature** for the first implementation. Solve radiation, storage and transport at that same temperature, with no subsequent lapse subtraction, current offset or temperature recentering.

This models a pressure-mediated part of the elevation response. It does not solve the vertical atmospheric temperature profile, convection or the environmental lapse rate. Hydrostatic balance states that surface pressure measures the weight of the overlying atmospheric column; an exponential pressure profile additionally assumes constant gravity and an isothermal ideal gas. [Beirle et al. (2022), section 2.3 and Appendix A](https://amt.copernicus.org/articles/15/987/2022/amt-15-987-2022.html) describe these distinctions.

Let `A_i` be the authoritative control-volume area, `z_i` the air–surface interface elevation in metres, `g` the configured gravity in m/s², and `T_profile > 0` a prescribed reference-profile temperature. With dry-air gas constant `R_d`, define

\[
x_i=-\frac{g z_i}{R_d T_{profile}},\qquad
w_i=e^{x_i},\qquad
p_i=\bar p\,\frac{w_i}{\sum_j A_jw_j/\sum_j A_j}.
\]

**Preserve the existing pressure semantics.** `PlanetConfig.atmosphere_pressure_bar` currently specifies mean surface pressure. Thus `p̄ = 100000 × atmosphere_pressure_bar` is the area-weighted mean in pascals, and

\[
\sum_i A_i p_i=\bar p\sum_i A_i,\qquad
M_{atm}=\frac{\bar p\sum_i A_i}{g}.
\]

This normalization enforces the prescribed atmospheric mass for fixed area and gravity. It is not a temperature adjustment. Holding a sea-level `p_ref` fixed instead would change atmospheric mass whenever terrain changes and would silently change the configuration field's meaning. A separate reference-elevation-pressure control is possible only with an explicit schema change; the implied `p_ref` can instead be a derived diagnostic.

A common shift of every interface elevation multiplies all weights by the same factor and leaves every `p_i` unchanged. This **datum invariance** is useful both physically and numerically. A physical change in sea level or flooding changes the interfaces and masks; it is not merely a coordinate shift.

Use `z_i = 0` on the marine water surface, never the seabed. Use the actual exposed land elevation, including below-sea-level continental basins. A later lake-aware model must use lake water-surface elevation. The first prescribed marine/continental model must retain its explicit limitation that inland water is not yet a thermally coupled lake surface. Freeze the geometry, masks and coefficients for each periodic solve; rebuild them after relevant terrain or water-surface changes.

## Coefficients and numerical domain

Proposed dry-air constants are `R_d = 287.05 J kg⁻¹ K⁻¹` and `cp = 1004 J kg⁻¹ K⁻¹`. Use a declared positive `T_profile`, with approximately 288 K as an initial Earth reference choice. Extending that value isothermally is a modeling choice, not a universal atmospheric profile or a promised surface temperature. [ECMWF's reference-profile documentation, section 1.3.1](https://www.ecmwf.int/sites/default/files/elibrary/2014/9201-part-i-observation-processing.pdf), illustrates the distinction between prescribed profiles and model temperature: its reference atmosphere has separate tropospheric and stratospheric temperature laws.

For the existing combined-column approximation, use

\[
C_i=C_{surface,i}+c_p\frac{p_i}{g},\qquad
\tau_i=\tau_*G\frac{p_i}{p_*}\frac{g_*}{g},\qquad
I_i(T_i)=\frac{\sigma T_i^4}{1+3\tau_i/4}.
\]

`C_surface,i` must remain positive and use the declared land or marine slab convention. [Climlab's heat-capacity routines](https://climlab.readthedocs.io/en/latest/api/climlab.utils.heat_capacity.html) provide the atmospheric `cp Δp/g` convention. The opacity law assumes fixed absorption per atmospheric mass; mapping the existing greenhouse multiplier `G` to that absorption is an explicit model choice. Pressure alone does not establish greenhouse composition or spectroscopy. `τ_* = 1` at the chosen `p_*,g_*` is a reference experiment, not a calibration to generated terrain.

The effective outgoing-radiation coefficient is `ε_i = 1/(1+3τ_i/4)`. It represents this gray atmospheric reduction, not the emissivity of the surface material.

Atmospheric integrated conductivity can follow `K_i = κ cp p_i/g`, in W/K. Construct **symmetric** edge conductances from these local coefficients and the verified mesh geometry. For equal half-edge resistance lengths, the harmonic interface mean `2K_iK_j/(K_i+K_j)` follows from adding the two conductive resistances; this is an interface discretization choice. Handle two zero coefficients explicitly and omit zero-conductance edges. Keep any separately modeled ocean transport distinct.

Evaluate pressure weights by subtracting their maximum exponent before summation, using area weighting and adequate accumulation precision. Do not compute huge exponentials and normalize afterward. For `p̄=0`, return exactly zero atmospheric pressure, storage, opacity and atmospheric conductance without taking `log(0)`. Positive surface storage and black-surface outgoing radiation remain. For positive `p̄`, mathematical pressures are positive; if a required value underflows or a derived coefficient is unrepresentable, report the numerical limitation explicitly rather than silently inserting a pressure floor or dropping atmospheric mass. Local pressure may exceed the configuration's bound on **mean** pressure; these are different quantities.

Constant gravity and a thin spherical surface are approximations. Record `max |z|/R` and atmospheric scale height `R_d T_profile/(gR)` as applicability diagnostics. The accepted radius/gravity ranges include cases where these ratios are not small. Arbitrary extreme terrain, unusual composition, very high pressure, evaporation, atmospheric condensation and large differences between actual climate and the reference profile are not validated by this model. No exponential law can supply that missing physics.

## Transport alternatives

| Treatment | Conservation and numerical consequences | Recommendation |
|---|---|---|
| Flat columns with actual-temperature diffusion | Retains the present positive energy operator but has no direct elevation response. | Keep as an analytic comparison, not a claim of mountain-climate realism. |
| Hydrostatic coefficients with actual-temperature diffusion | Preserves the current energy ledger and monotone radiation/diffusion structure. Pressure affects the solution through coefficients. | First production candidate, with the partial-physics limitation stated above. |
| Dry-static-temperature flux `G Δ(T+gz/cp)` | Pairwise watts cancel, and prescribed `z` leaves the temperature Jacobian unchanged. The terrain offset adds a signed forcing and breaks positivity. | Do not insert into the present surface model. |
| Potential-temperature flux `G Δθ` | Can preserve actual energy and positivity, but requires transformed coefficients, a different numerical audit and an explicit airless branch. | Candidate for subsequent research. |

The dry-static failure is direct: two unforced cells at `T=0` but different heights exchange energy under `G Δ(T+gz/cp)` solely because of their height difference. The higher cell immediately acquires negative temperature. Pairwise energy conservation alone does not prevent this. Dry static energy has a physical role in vertical atmospheric convection, where the column structure and surface flux must also be modeled. [Held's radiative-convective formulation](https://www.gfdl.noaa.gov/blog_held/19-radiative-convective-equilibrium/) and [Climlab's conservative convective adjustment](https://climlab.readthedocs.io/en/latest/api/climlab.convection.convadj.html) describe that fuller setting.

For potential temperature, let `Π_i = (p_i/p_*)^(R_d/cp)` and `θ_i = T_i/Π_i`. [Climlab's thermodynamic implementation](https://climlab.readthedocs.io/en/latest/_modules/climlab/utils/thermo.html) supplies this transformation. Choosing horizontal watts proportional to `Δθ` remains a new transport closure. In actual-temperature variables the resulting matrix loses the current area-weighted symmetry. In θ variables the conservative equation becomes

\[
C_i\Pi_i\dot\theta_i=Q_i-\epsilon_i\sigma\Pi_i^4\theta_i^4
+\frac1{A_i}\sum_jG_{ij}(\theta_j-\theta_i).
\]

For fixed positive `Π_i`, symmetric diffusion and positive transformed storage restore the relevant implicit structure. Omitting `Π_i` from storage would conserve the wrong energy. Radiation and exported temperatures must still use `T_i=Π_iθ_i`. The transformed radiation coefficient is not a physical emissivity constrained to at most one; existing kernel validation cannot simply be reused. `p=0`, extreme pressure ratios, conditioning and error bounds expressed in actual kelvin all require new handling.

## Independent numerical example

This is an isolated constant-forcing calculation with **reference pressure** `p(0)=1 bar`, not a generated world with mean pressure fixed to one bar. Set `T_profile=288.15 K`, `g=9.80665 m/s²`, `R_d=287.05`, `τ(0)=1`, albedo 0.3, and `Q=0.7×1361/4=238.175 W/m²`. Then

\[
H=8434.425\ \mathrm{m},\quad
\tau(z)=e^{-z/H},\quad
T_{eq}(z)=\left[\frac{Q(1+3\tau(z)/4)}\sigma\right]^{1/4}.
\]

With `σ=5.670374419e−8 W m⁻² K⁻⁴`, the derived temperatures are 292.806 K at zero elevation and 277.637 K at 5 km. The initial gradient is

\[
\frac{dT_{eq}}{dz}=-\frac{T_{eq}}{4H}\frac{3\tau/4}{1+3\tau/4}
=-3.720\ \mathrm{K/km}\quad(z=0).
\]

At zero opacity the equilibrium height gradient vanishes. Thus this model does not reproduce a prescribed 6.5 K/km lapse rate, and seasonal or transported temperatures need not be monotone functions of elevation. The calculation is a verification target for the equations, not a value to force onto the world.

## Configuration migration and acceptance tests

Remove `lapse_rate_c_per_km` from the new solved-climate contract with explicit migration handling. Its old meaning cannot silently become a hydrostatic reference temperature, opacity parameter or diffusion offset. Preserve the existing mean-pressure meaning, and identify any new profile-temperature parameter as a fixed structural assumption. Report local pressure, atmospheric/surface capacity, opacity, interface elevation and the actual-temperature budget used by the solver.

Required acceptance tests before production integration:

1. Verify hydrostatic pressure ratios and the area-weighted mean/mass constraint, including unequal cell areas and negative land elevations.
2. Apply a common datum shift to every interface and require invariant local pressures and coefficients.
3. Change marine seabed depth without changing its water surface and require unchanged atmospheric pressure; test exposed land and future lake interfaces separately.
4. Verify exact airless limits, positive residual surface storage, and explicit underflow/overflow handling without invented mass or coefficient floors.
5. Reproduce the isolated gray-equilibrium example and its analytic elevation derivative; retain the flat, zero-opacity and zero-height limits.
6. Retain pairwise transport cancellation and independent monthly radiation/storage replay at the actual solved temperature.
7. Rebuild coefficients after terrain/mask changes, preserve atmospheric mass, and require a fresh converged periodic cycle.
8. Reject obsolete lapse controls explicitly; do not preserve the old imposed temperature pattern through seed-dependent fitting.

Successful tests would verify this reduced model and its implementation. A vertical radiative-convective model, atmospheric composition, cloud and moisture physics, boundary-layer behavior and quantitative mountain-climate validation would still remain separate scientific work.

## Implemented adapter and verification

[`physical_columns.cpp`](../cpp/src/engine/physical_columns.cpp) now implements the prescribed model above. Its pure interface accepts explicit surface elevations, areas and surface capacities. It normalizes hydrostatic pressure with area-weighted logarithmic sums, preserves the exact flat-column and airless branches, and reports actual mean-pressure and atmospheric-mass residuals without correcting an individual column. Every required positive coefficient must be representable; unrepresentable pressure, opacity, storage or transport fails explicitly.

The separate native-cell adapter requires fresh sea-level/marine state: marine labels 1–3 with positive depth exactly equal to minus elevation, or exposed land label 0 with zero water depth. Stale lake flags/codes are rejected. Marine storage is `4.1813e6 × min(actual_depth_m, 50)` J/m²/K by default, while exposed land has `4e6` J/m²/K. Thus shallow water is not silently assigned a 50 m slab. Marine atmospheric height stays zero regardless of seabed depth. No later biome, ice or precipitation field enters these coefficients.

[`climate_transport.cpp`](../cpp/src/engine/climate_transport.cpp) implements the variable coefficient on each geometry: harmonic interface conductivity on spherical Voronoi faces, and the arithmetic nodal conductivity integrated separately over each piecewise-linear geodesic triangle. It preserves the old scalar path exactly for a uniform coefficient vector. A heterogeneous cotangent sum can become negative on an otherwise valid mesh; the builder rejects that case instead of clipping it. An independently constructed distorted mesh exercises this failure. For `T=z`, `K=2+0.5z` on a unit sphere, the analytic operator is `0.5(1−z²)−2z(2+0.5z)`. Its relative area-L2 error falls from **0.01790 to 0.001633** on Fibonacci and **0.03953 to 0.008107** on geodesic meshes as requested resolution increases from 128 to 2048. This demonstrates convergence for the tested smooth field, not a universal pointwise rate or a proof for arbitrary coefficient jumps.

[`seasonal_climate.cpp`](../cpp/src/engine/seasonal_climate.cpp) composes fresh cells, physical columns, mesh transport, actual astronomical intervals and the adaptive periodic solver. It checks mesh area against the requested radius, checks latitude against cell position, reports thin-atmosphere/relief applicability ratios, and retains owned input snapshots and accepted numerical evidence. A supplied phase state is only a starting iterate; changed coefficients still receive new convergence and monthly refinement checks. The tests replay monthly radiation, transport and storage independently, then reproduce the accepted discrete solution from its shared astronomical nodes, initial phase and partition. They also verify the airless analytic limit on both meshes and a changed shallow-water column.

All **22 native CTest cases passed** at the component integration stage (`runs/review-native-prescribed-climate-tests.log`, 14.17 s). The subsequent [explicit C++ producer integration](seasonal_climate_native_integration.md) passes 25 CTest cases and serializes the retained temperature/energy source. Python configuration and pipeline dispatch, production validators, and lake/ice coupling remain separate required work.
