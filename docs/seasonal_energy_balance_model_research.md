# Seasonal energy-balance model: implementation basis

Research note, 2026-09-09. Sections 1–13 record successive model, numerical and integration experiments, including their limits at each stage. The subsequent [explicit C++ seasonal producer](seasonal_climate_native_integration.md) now generates temperatures and retained energy budgets. Default C++ selection, older C ABIs and Python/CLI/web generation retain the legacy model; configuration and consumer migration remain open.

The recommended minimum is a **seasonal, conservative column energy-balance model (EBM)** with astronomical shortwave forcing, explicit thermal storage, outgoing radiation, and horizontal heat transport. This supports a defensible improvement over the native latitude gradient and cosine temperature cycle. It does not establish a general atmosphere model for every value accepted by `PlanetConfig`.

## 1. Define the energy budget before choosing coefficients

Use Kelvin internally and seconds for time. For a zonal benchmark, let `x = sin(latitude)` and solve

\[
C(x)\partial_t T=(1-\alpha)S-I(T)+\partial_x[D(1-x^2)\partial_xT].
\]

Here `C` is J m⁻² K⁻¹, `S` and `I` are W m⁻², and `D` is W m⁻² K⁻¹. `S` is incident top-of-atmosphere (TOA) flux, `α` is effective planetary albedo, and `I` is outgoing TOA flux. This is a combined surface–atmosphere column budget indexed by surface temperature, rather than a skin-temperature budget. The seasonal EBM extends the classic diffusion model of [North and Coakley (1979)](https://faculty.washington.edu/battisti/589paleo2005/Papers/NorthCoakley.pdf); [climlab's implementation](https://climlab.readthedocs.io/en/latest/_modules/climlab/model/ebm.html) provides a reproducible reference.

**Mesh adaptation, derived here:** for area `A_i` and symmetric conductances `G_ij = G_ji ≥ 0`, use

\[
A_i\partial_t E_i=A_i[(1-\alpha_i)S_i-I_i]+
\sum_jG_{ij}(T_j-T_i),\qquad E_i=C_iT_i
\]

for constant capacities. Compute every undirected edge flux once and add opposite signs to its endpoints. Then horizontal transport sums to zero in watts, even with unequal cell areas and land/ocean capacities. An unweighted neighbor-temperature average does not establish this property.

For an orthogonal finite-volume mesh, `G_ij = K_ij L_ij/d_ij`: boundary length and center distance are in metres; the depth-integrated transport coefficient `K` is W K⁻¹. The zonal coefficient is `D = K/R²`. Equivalently, `K = κ C_atm`, with eddy diffusivity `κ` in m² s⁻¹. This distinction is explicit in [Rose, Cronin and Bitz (2017), section 3](https://www.atmos.albany.edu/facstaff/brose/resources/Publications/Rose_Cronin_Bitz_ApJ_accepted.pdf). Storage capacity and transported atmospheric capacity are different quantities; increasing mixed-layer depth must not automatically increase atmospheric conductance.

Use a full sphere: no imposed zero flux at the equator. A 1-D equal-area latitude grid is the cleanest reference implementation. For geographic land/ocean contrasts, use separate spatial columns, or a documented coarse climate grid with conservative transfers to the terrain mesh. Averaging all land and sea into one temperature per latitude loses continental seasonal contrasts. Arbitrary graph edges without consistent physical lengths/areas define a graph model, not a verified spherical diffusion discretization.

## 2. Minimal coefficients and what they mean

The following are reference values and sensitivity intervals, **not universal physical validity ranges**.

| Quantity | Supported reference | Recommended use |
|---|---|---|
| Earth EBM transport `D` | 0.5394, 0.555, 0.6 W m⁻² K⁻¹ occur in the sources below | 0.555 for the reference case; test roughly 0.54–0.60 before larger sensitivity sweeps |
| Linear OLR | `I = 210 + 2 T_C` W m⁻² in climlab | Independent Earth benchmark; do not extrapolate to arbitrary temperatures |
| Effective land column capacity | `5.25e6` J m⁻² K⁻¹ | Historical benchmark only; already represents effective column storage |
| Effective ocean column capacity | `2.10e8` J m⁻² K⁻¹ | Historical 50 m mixed-layer benchmark |
| Ocean mixed-layer depth | 10–50 m in published model configurations | 50 m reference; 10 m sensitivity case; cap by actual water depth |

The effective capacities and `D = 0.5394` are from [Spiegel, Menou and Scharf (2008), section 2.2](https://arxiv.org/pdf/0711.4856). Climlab supplies the linear OLR and `D = 0.555` defaults in its [EBM source](https://climlab.readthedocs.io/en/latest/_modules/climlab/model/ebm.html). The `D = 0.6` benchmark is in [Wagner and Eisenman (2015), table 1](https://eisenman.ucsd.edu/papers/Wagner-Eisenman-2015.pdf). These are alternative model settings, not measured universal constants.

For a **mass-explicit implementation**, use separate terms instead of adding atmosphere to the historical effective capacities:

\[
C_i=C_{atm,i}+C_{surface,i},\quad
C_{atm,i}=c_{p,a}p_i/g,\quad
C_{water,i}=\rho_wc_{p,w}\min(H_{mix},H_{water,i}).
\]

[Climlab's heat-capacity routines](https://climlab.readthedocs.io/en/latest/api/climlab.utils.heat_capacity.html) use dry-air `cp = 1004` J kg⁻¹ K⁻¹ and water `ρ = 1000` kg m⁻³, `cp = 4181.3` J kg⁻¹ K⁻¹. At one bar and Earth gravity the full atmospheric term is about `1.02e7` J m⁻² K⁻¹. Adding this to an already effective land-column value would mix conventions. A dry-air composition and a column that follows surface-temperature changes are assumptions, especially away from Earth conditions.

For land, a transparent reduced slab is `C_land,surface = c_rock H_land`. [CTSM's thermal-property specification](https://escomp.github.io/CTSM/tech_note/Soil_Snow_Temperatures/CLM50_Tech_Note_Soil_Snow_Temperatures.html) uses bedrock `c = 2e6` J m⁻³ K⁻¹ and conductivity `k = 3` W m⁻¹ K⁻¹; mineral soil solids span approximately `2.128e6–2.385e6` in that scheme, before accounting for porosity and water. **Proposed reduction:** use `H_land = 2 m` and test 1–4 m. This depth is a modeling choice, not a published EBM constant. As a scale check, those rock properties give an annual thermal skin depth `sqrt(2k/(cω)) ≈ 3.9 m`. One slab cannot reproduce the full frequency-dependent ground response.

[Williams and Kasting (1997)](https://wwwuser.oats.inaf.it/exobio/climates/WilliamsKasting97.pdf) used a 50 m wind-mixed ocean. [Linsenmeier, Pascale and Lucarini (2015), table 1](https://arxiv.org/pdf/1401.5323) compared 10 and 50 m slabs. Use the actual ocean/lake mask and available depth, including standing inland lakes; ocean-fraction targets are not local storage inputs.

## 3. Radiation and albedo

For the minimal production candidate, I recommend the monotone gray approximation

\[
I(T)=\frac{\sigma T^4}{1+3\tau/4},\qquad \tau\ge0.
\]

Start with **temperature-independent `τ`**, making the radiation law positive and monotone for `T ≥ 0`, and the zero-opacity limit a black surface. `τ = 1` is an explicit published reference choice. [Spiegel et al. (2008)](https://arxiv.org/pdf/0711.4856) also used a temperature-dependent alternative. [Spiegel et al. (2009), equation 2 and table 1](https://arxiv.org/pdf/0807.4180) specify `τ(T) = 0.79(T/273 K)^3`. The latter is a useful sensitivity benchmark, not a water-vapor or runaway-greenhouse model. Neither formulation predicts an infrared radiation limit for a steam atmosphere.

If retaining `greenhouse_factor`, a possible explicit parameter mapping is `τ = τ_ref G (p/p_ref)(g_ref/g)`. The column-mass dependence follows a fixed mass absorption coefficient; identifying `G` with opacity and holding composition/absorption fixed are **new empirical choices**. Pressure alone does not determine greenhouse strength. Record this mapping; do not describe it as calculated CO₂ or humidity. The model must return `τ = 0` at `p = 0` or `G = 0`.

Do not add a greenhouse temperature increment after solving the budget. If a surface emissivity other than unity is included, use the same radiation convention in production, equilibrium calculations and replay. Surface emissivity and atmospheric optical depth are not interchangeable.

Use a documented effective TOA ice-free albedo, initially `α_warm ≈ 0.3`, rather than mixing bare ocean reflectance with a cloudy TOA radiation law. A smooth thermal albedo candidate is

\[
\alpha(T)=\alpha_{warm}+(\alpha_{cold}-\alpha_{warm})
\frac{1-\tanh[(T-T_f)/\Delta T]}2.
\]

Spiegel's published pairs have warm albedos `0.25–0.30`, cold albedos `0.70–0.77`, and a transition centered near `268 K` with `5 K` width. These are empirical planetary albedos; the transition temperature is not a literal water freezing point. Their purpose is an unresolved snow/ice feedback. Cloud/spectral assumptions materially affect outcomes; [Gilmore (2014)](https://academic.oup.com/mnras/article/440/2/1435/1023076) demonstrates the sensitivity to the radiative functions even for Earth.

For a minimum sensible-heat EBM, keep `C` fixed and explicitly label thermal ice fraction as an albedo proxy. If ice mass/thickness is prognostic, use enthalpy and the same ice state for albedo: the ocean/ice formulation `E=C_water(T−T_m)` for open water and `E=−ρ_i L_f h` for ice, with a conductive ice-surface temperature, is described by [Wagner and Eisenman (2015), section 2](https://eisenman.ucsd.edu/papers/Wagner-Eisenman-2015.pdf). Merely switching capacities or inventing ice mass at a temperature threshold omits latent heat. Do not copy their positive global deep-ocean heat source: the paper explicitly identifies it as a simplification. Any ocean redistribution here should conserve global energy.

## 4. Time integration and periodic solution

These are implementation recommendations derived from the budget, not claimed published parameter values:

1. Evaluate astronomical forcing throughout the integration. The existing equal-duration monthly outputs are export bins, not a sufficient nonlinear solver time grid. Average products such as `(1−α(t))S(t)` directly; `mean(α) mean(S)` generally differs.
2. Use finite-volume spatial fluxes and an implicit radiation–diffusion step. With albedo frozen for one nonlinear iterate, the residual has positive radiation derivative and a positive-definite diffusion contribution. Damped Newton/Picard iterations with step rejection are preferable to unchecked Newton steps. [Climlab's diffusion solver](https://climlab.readthedocs.io/en/latest/_modules/climlab/dynamics/meridional_heat_diffusion.html) also uses fully implicit stepping; unconditional diffusion stability does not imply accurate seasonal phase.
3. Restrict both elapsed-time and orbital-angle step size. Near periapsis, resolve true anomaly; near apoapsis, retain adequate time resolution. Exact/accurate integrated solar fluence is useful, but spreading a short pulse across a month still changes nonlinear radiation and ice response. Test timestep halving. Never silently cap eccentricity.
4. Solve for a periodic year. Compare temperatures/enthalpies at the same phases in successive years and check the integrated energy balance. A proposed numerical target is a maximum phase difference below `1e-3 K` plus global annual flux residual below `0.01 W m⁻²`; these tolerances require convergence testing and are not measurement accuracy.
5. Initialize near a steady solution under annual forcing, then spin up the seasonal cycle. For very large capacities, use an accelerated periodic boundary-value/shooting solve or explicitly report failure to converge. A fixed small number of years is insufficient. Small year-to-year temperature change alone can conceal substantial flux imbalance at enormous `C`.
6. With ice feedback, compare warm and cold starts. Distinct converged solutions can be physical model hysteresis; do not force them to agree or select the state that matches terrain targets. Record initialization and convergence status.
7. Export time-weighted monthly means from the converged cycle. Also accumulate ASR, OLR, storage change, transport convergence and area-weighted global residual using the same numerical steps.

## 5. Independent tests, beyond producer replay

The first five tests below follow analytically from the stated equations and can catch shared production/replay mistakes.

| Test | Independent expected result |
|---|---|
| Uniform fixed-albedo gray equilibrium, no transport | `T = [(1−α)S(1+3τ/4)/σ]^(1/4)`; `τ=0` recovers the black-surface case |
| Unforced radiative cooling, constant `τ,C` | With `k=σ/(1+3τ/4)`, `T(t)=[T(0)^−3+3kt/C]^−1/3` |
| Two unequal-capacity cells, radiation disabled | `A1 C1 T1 + A2 C2 T2` conserved; temperature difference decays at rate `G[1/(A1C1)+1/(A2C2)]` |
| Spherical harmonic transport | Constant `D,C`, no radiation: degree `l` decays as `exp[−D l(l+1)t/C]`; a constant field remains constant |
| Linear seasonal forcing | For forcing amplitude `F_l` at frequency `ω`, response amplitude is `F_l/sqrt[(B+D l(l+1))²+(ωC)²]`, with lag `atan2(ωC,B+D l(l+1))` |
| Geometry/orbit power | Area-time averaged incoming flux is `S0 L/[4 a_AU² sqrt(1−e²)]`; assess spatial quadrature as well as orbital quadrature |
| Storage effects | Increasing `C` damps and delays a forced seasonal harmonic; it does not alter the constant-forcing equilibrium |
| Phase and obliquity | Circular orbit, symmetric surface: northern/southern cycles agree after a half-year shift; zero tilt has no seasonal forcing; high tilt can reverse annual transport direction |
| Nonlinear closure | Integrated global ASR minus OLR equals global enthalpy change; transport cancels independently, including mixed areas/capacities |
| Refinement | Halve timestep and refine spatial/orbital quadrature; monthly extrema, phase, global residual and ice fraction converge |
| Boundary contracts | `p=0` gives zero atmospheric storage/transport/opacity but positive ground storage; lakes use water capacity; output filtering does not change the solution |
| Ice, if prognostic | Melting/freezing a prescribed mass consumes/releases `m L_f`; capacity changes preserve continuous enthalpy |

For a source benchmark, [Rose et al. (2017), section 6 and figures 9–10](https://www.atmos.albany.edu/facstaff/brose/resources/Publications/Rose_Cronin_Bitz_ApJ_accepted.pdf) compare full seasonal astronomical forcing against analytical solutions at low and high obliquity. Their deep-water case has `γ=ωC/B=50` (about 90 m water), and their moderate case `γ=5` (about 9 m). Deep-water annual and seasonal solutions agree well; moderate storage can substantially change ice-belt stability. Reproduce a selected published parameter set before treating ice states as verified. Reversal alone is not a quantitative validation. The [Linsenmeier et al. GCM comparison](https://arxiv.org/pdf/1401.5323) finds important EBM discrepancies on eccentric orbits, despite better circular-orbit agreement.

## 6. Accepted configuration versus physical applicability

Current configuration accepts radius `(100,100000] km`, gravity `(0.05,5) g`, day length `(1,10000] h`, obliquity `[0,90]°`, eccentricity `[0,1)`, luminosity `(0.01,100]`, pressure `[0,1000] bar`, and greenhouse multiplier `[0,100]`. No scalar-coefficient EBM is validated over this whole Cartesian product.

- **Calendar:** the schema lacks semimajor axis, stellar mass and year length. State the assumed 1 AU orbit, year in seconds, stellar mass used for that year, and fixed periapsis phase. Changing rotation period must not inadvertently change orbital period by defining a year as 365 planetary days.
- **Daily averaging:** require fast rotation relative to local orbital evolution. From Kepler's law, orbital angle traversed during one rotation is largest at periapsis: `ε_orb = (2π P_rot/P_year) sqrt(1+e)/(1−e)^(3/2)`. It must be small for the frozen-orbit daily average. This is a diagnostic, not a magic eccentricity cutoff. [Paillard (2026), sections 2–3](https://cp.copernicus.org/articles/22/647/2026/) states the fast-rotation assumption and derives the time/angle weighting. Large diurnal thermal excursions also invalidate replacing the daily mean of `T⁴` by the fourth power of a daily-mean temperature.
- **Atmospheric dynamics:** the published scaling `D/D_ref ∝ (p/p_ref)(cp/cp_ref)(m_ref/m)²(Ω_ref/Ω)²` in [Williams and Kasting (1997), equation 9](https://wwwuser.oats.inaf.it/exobio/climates/WilliamsKasting97.pdf) is an idealized transport parameterization, not a universal law. Its unlimited slow-rotation extrapolation is inappropriate. Prefer explicit `κ` or `D` with an Earth reference; if scaled with pressure, gravity or rotation, expose the chosen assumptions. At fixed `κ`, column mass and physical radius imply `D=κ cp p/(gR²)`; do not apply the radius factor twice.
- **Thin atmosphere/terrestrial surface:** very low gravity or small radius can violate `H_atm/R ≪ 1`; extreme rotation can make centrifugal acceleration comparable to gravity. A 100000 km rocky sphere, airless oceans, and arbitrary 1000 bar dry-air columns are not established physical planets merely because parsing succeeds.
- **Radiation and phase:** missing gas composition, clouds, stellar spectrum, pressure broadening, water-vapor feedback, ocean evaporation and atmospheric condensation prevent a general habitability claim. Extreme luminosity/opacity can yield mathematically finite temperatures outside material/phase validity. Report that status instead of clipping temperatures into a plausible-looking interval.
- **Geography and dependency order:** the solver must use a settled physical water/depth mask before biome, hydrology and society consume temperature. Any later change to surface water or elevation requires an explicit climate recomputation policy. Albedo derived from final vegetation needs a deliberate coupled iteration. An empirical ocean-current temperature offset, a temperature recentering, or a post-solve lapse subtraction invalidates an energy budget evaluated at the adjusted temperatures. If lapse downscaling is retained, expose the solved reference temperature and its budget separately; a full vertical temperature/lapse treatment is beyond this minimum EBM.

Recommended metadata includes equation/version, temperature meaning, TOA radiation convention, albedo law, opacity mapping, all capacities and transport units, assumed orbital period, integration resolution/tolerances, periodic convergence and residuals, initialization branch, and physical-applicability flags. Keep numerical convergence and physical applicability as separate claims.

## 7. Native integration map and temperature-contract migration

Integration audit, 2026-09-09. The hooks below describe the current production tree and a proposed migration; they do not claim that the periodic driver is already wired into generation.

**Smallest consistent first integration:** solve a periodic combined-column budget with prescribed coefficients. Construct those coefficients from the current marine mask, geometry and explicitly available mineral class, then keep them fixed throughout the periodic solve. Treat inland water as the prescribed continental column and ignore diagnostic ice in this first model. This deliberately omits lake thermal inertia and lake/ice albedo feedback. It can drive native temperatures without a lake/ice fixed point, provided its exported coefficients are identified as prescribed effective column properties, rather than reflectance or storage inferred from the final surface. The stronger lake/ice requirements in sections 2, 5 and 6 remain requirements for the subsequent surface-coupled model, not properties of this interim model. Bare mineral/ocean reflectance must still be converted through a declared TOA convention; it is not interchangeable with effective planetary albedo.

| Hook in the current tree | Required integration action |
|---|---|
| [`hydrology.cpp::stabilize_numeric_depressions`](../cpp/src/engine/hydrology.cpp), currently `apply_sea_level → label_marine_water_bodies → compute_climate → compute_hydrologic_water_budget → compute_flow_and_rivers` | Retain this order for prescribed coefficients. Each terrain-correction pass supplies a fresh marine mask before the complete periodic solve. Do not treat a recomputation as another year of transient evolution. |
| [`climate.cpp::compute_climate`](../cpp/src/engine/climate.cpp) | Separate circulation descriptors, the thermal solve, and precipitation/evaporation consumers. Populate `Cell::temperature_monthly_c` and `temperature_c` from the converged cycle before PET, vapor evaporation and the downstream water budget read them. Remove the latitude/cosine temperature law and all additive stellar, greenhouse, pressure, current, lapse and global-centering temperature corrections. A retained lapse downscaling needs a separately named reference-temperature budget or a new vertical radiation treatment. |
| [`climate_transport.hpp`](../cpp/src/engine/climate_transport.hpp), [`seasonal_energy_balance.hpp`](../cpp/src/engine/seasonal_energy_balance.hpp) | Build the conservative graph from authoritative control-volume geometry. Use `area_km2 × 1e6`, capacities in J m⁻² K⁻¹, and conductances in W K⁻¹. Geometry can be cached while topology is unchanged; coefficient-dependent conductances must be rebuilt when their inputs change. The periodic wrapper owns astronomical interval forcing, fixed coefficients, spin-up and time-weighted output bins. |
| [`types/core.hpp::Cell`](../cpp/src/engine/types/core.hpp) and native serialization | Retain monthly and annual temperature fields as the authoritative consumer interface. Add solved coefficients, monthly ASR/OLR, transport convergence, storage tendency and residuals, plus initial/final cycle state or equivalent replay evidence. Monthly temperature and flux means must use the same accepted substeps; `mean(σT⁴)` is not `σ(mean(T))⁴`. Store convergence and applicability separately. |
| [`pipeline.cpp::simulate_world_impl`](../cpp/src/engine/pipeline.cpp), final cryosphere block | The existing final stabilization follows glacial sediment transport, so it refreshes climate after the last glacial terrain mutation. `derive_cryosphere_state` then runs again. This is consistent only when final ice is an output diagnostic that does not set the solved coefficients. |
| [`core.cpp::climate_thermal_moisture_temperature_anomaly_c`](../cpp/src/engine/core.cpp) and `process_serialization.cpp::climate_model_json` | The old rainfall multiplier uses `base + old stellar + old greenhouse` as a temperature proxy. Prefer feeding it the solved area-weighted annual temperature relative to its declared reference; this remains an empirical precipitation law. Its serialized factor then needs access to the solved climate result, instead of reconstructing a superseded temperature model from `Params` alone. |
| [`api.py`](../src/magic_geo/api.py), [`climate_energy.py::enrich_world_with_climate_energy_balance`](../src/magic_geo/climate_energy.py) | Make the native solved budget authoritative. The current enricher overwrites albedo, ASR, OLR and residual fields using final biome/lake/ice and a separate greenhouse-temperature formula. Replace this path with aggregation of native evidence, or retain its outputs under clearly separate diagnostic names. It must not overwrite the coefficients or fluxes that produced temperature. |
| [`process_serialization.cpp::climate_model_json`](../cpp/src/engine/process_serialization.cpp), [`geo_validation.py`](../src/magic_geo/geo_validation.py), [`geo_validation_physics.py`](../src/magic_geo/geo_validation_physics.py), [`cli/commands/validate.py`](../src/magic_geo/cli/commands/validate.py) | Version the temperature equation, parameter meanings and replay together. Remove the old imposed-global-mean identity for the new model. Independently replay the discrete energy budget and its time integration; do not validate an energy solution against the old diagnostic radiative-equilibrium temperature. |

**Why final lake/ice coefficients cannot simply be enabled at these hooks:** `apply_sea_level` clears `is_lake`; `compute_flow_and_rivers` reconstructs lakes only after climate and runoff. `derive_cryosphere_state` is absent from initial/maturation climate calls, resets grounded-ice diagnostics when called, skips marine water, and is called again after the last climate solve. Its `ice_thickness_m` is neither prognostic seasonal sea ice nor an enthalpy state. Thus directly reading `is_lake` or `ice_thickness_m` inside the present climate call gives missing or stale feedback.

For subsequent lake/grounded-ice albedo closure, put a bounded **surface-coefficient iteration inside each fixed-topography stabilization pass**, after the marine solve: freeze a surface snapshot; solve its periodic climate; update rainfall, water budget and lake routing; derive the diagnostic grounded-ice state without transporting sediment; form the next coefficient snapshot. Require declared mask/coefficient and temperature convergence, retaining evidence for the accepted state. Keep `apply_sea_level` and numeric terrain corrections outside this inner loop so they do not erase the trial lakes. Run the closure again after glacial terrain transport. Never call `transport_glacial_sediment` repeatedly as a climate convergence operator. This still does not supply seasonal freezing/melting: that requires a prognostic enthalpy/ice state, phase-consistent albedo and storage, and appropriate water/ice inventory accounting. The capped lake `water_depth_m` field also needs an explicit depth interpretation before serving as a physical mixed-layer input.

**Existing user contract:** `ClimateConfig.base_temperature_c` defaults to 15 and accepts −100 to 100. Its schema text says “Global mean sea-level temperature anchor,” while native metadata, README, the climate wiki and regression tests specify the post-adjustment global area mean (plus the existing parameter forcings). All nine gallery seeds set it explicitly; the snowball/hothouse matrix uses −10/35. It is also embedded in native `CConfig` and Python `NativeConfigV1`, and inherited ABI versions. Changing it to an unnoticed initial guess or an opacity knob would silently change stored configurations.

| Migration option | Assessment |
|---|---|
| Preserve the old global mean through a post-solve offset | Reject: the adjusted temperature no longer satisfies the recorded radiation/storage budget. An explicitly imposed extra heat source would be a different model and should not be introduced as a compatibility correction. |
| Rename to an initial/spin-up temperature | Valid only as an initialization control. A unique fixed-coefficient periodic solution should forget it; it is no longer a cold/hot world control. |
| Rename to a homogeneous reference radiative-equilibrium temperature | Mathematically possible if it calibrates opacity once against explicitly fixed reference ASR: `τ_ref = (4/3)[σ(T_ref+273.15)⁴/Q_ref − 1]`. This is a reference experiment, not the generated world's mean. Nonnegative opacity rejects references colder than the blackbody equilibrium; the existing −100 to 100 range cannot be preserved by clipping. |
| **Replace the mean-temperature control with `reference_infrared_optical_depth`** | **Recommended.** A nonnegative dimensionless `τ_ref` has the declared gray-radiation meaning in section 3; `greenhouse_factor` can explicitly scale that opacity. The generated mean is an output. Any spin-up temperature has a different name and no equilibrium-control promise. |

The recommended migration does **not** require keeping the old temperature model as a permanent opt-in/default branch. The new EBM may become the default in a documented breaking configuration/model version, with new named physical controls, migrated built-in configurations and explicit rejection or an explicit migration path for the obsolete `base_temperature_c`. Merely changing the default interpretation of that existing Celsius field and mentioning it in release notes is insufficient. The current `config_schema()` advertises schema v1 but configurations have no version discriminator; a real migration must address stored YAML/direct `WorldConfig` callers as well as that schema metadata. Preserve the layout and declared behavior of existing native C ABI versions, or explicitly reject unsupported legacy generation; add a new ABI version for new controls rather than reusing an old field with a new meaning. There is no scientifically exact automatic conversion from the old world's imposed mean to opacity for the new spatial seasonal model. An explicit homogeneous-reference conversion can be offered as an initial estimate, with its definition and domain recorded, never as seed-specific fitting.

**Integration gates:** retain analytic storage/radiation/transport and solar refinement tests; add complete periodic-cycle and timestep-refinement tests on both meshes; verify that toggling only final lake/ice/biome diagnostics cannot alter the prescribed-coefficient solution; verify that changing the marine mask does rebuild its columns; check final water-budget history temperatures against the accepted native field after glacial transport; test zero precipitation and output-filter independence; verify annual storage closure and global transport cancellation separately; tamper with exported coefficients/fluxes and require independent validation failure. Update `tests/test_smoke_climate.py`'s exact mean/offset assumptions, climate-energy replay tests and configuration/ABI tests to the new contract. Downstream soils, biomes, permafrost, settlements, society and seasonal histories must keep reading the new native temperatures. Do not relax those consumers' behavioral coverage to accommodate a new climate fixture. Lake/ice feedback, a defensible elevation treatment and physical-applicability evidence remain required scientific work after this interim integration.

## 8. Implemented numerical components and measured limits

Four native components now implement the numerical foundation. They are exercised directly by CTest and research probes; `compute_climate` has not yet been replaced. Generated-world metadata must continue to report that native temperatures are uncoupled from the Python solar diagnostic until that integration and its independent validation are complete.

- `solar_insolation`: the same declared equal-time calendar as Python, with daily zenith integration and stable Kepler inversion. The original monthly method retains its independent/Python parity fixtures. A separate integration interface splits each month into 30 equal-time intervals and then limits true-anomaly width to `2π/768`. It uses exact Kepler endpoint durations with stable `M=(1−e)E+e(E−sin E)` evaluation. Declination is evaluated at the angular midpoint: duration weights are exact within floating-point error, while insolation remains an explicitly tested angular quadrature.
- `climate_transport`: symmetric physical conductances on the authoritative mesh. Fibonacci Voronoi cells use shared-boundary length over centre distance. Geodesic cells use the cotangent stiffness of the primal triangles with their existing spherical barycentric areas. A naive shared-boundary formula on that nonorthogonal mesh conserved heat but failed harmonic refinement. Reciprocal segments, spherical area closure, positive conductances and undirected uniqueness are checked; negative weights are rejected, not clipped.
- `seasonal_energy_balance`: a backward-Euler step with positive thermal capacities, gray outgoing radiation and conservative pairwise transport. A prepared system validates fixed geometry once; Newton solves use an area-scaled symmetric positive-definite matrix and conjugate gradients with a diagonal preconditioner. Positivity and actual nonlinear residuals are checked. Exact zero and sub-kelvin equilibria remain unchanged, and nonconvergence is explicit.
- `periodic_energy_balance`: solves a repeatable year of fixed coefficients and interval forcing. Monthly temperatures, fourth-power temperature moments, radiation, transport, storage and residuals all come from the same integration steps. Mean outgoing radiation uses the mean fourth power, not the fourth power of the mean temperature. The accepted phase state, measured annual heating and solver iteration counts remain available.

The periodic iteration is derived here. With year map `P`, initial temperature `T`, phase difference `F=P(T)−T`, actual time-integrated net heating `R`, and annual-mean restoring operator `H=diag(mean(4εσT³))+L`, the unrelaxed candidate correction is `d=F+H⁻¹R`. In the constant-linear problem, `R=C F/year` and each mode has iteration factor `g(x)=exp(−x)(1+1/x)−1/x`, `x>0`. It remains bounded in magnitude by about 0.299 with positive capacities and symmetric diffusion, including unequal cell areas. The backward-Euler period map has the same contraction bound. Line search uses `Σ(A/C)[R²+(C F/year)²]`; per-cell tolerance scaling or a maximum-residual merit can reject every positive correction even in this stable linear case. An independently constructed three-column counterexample is retained as a regression.

The implemented driver subsequently accelerates this correction with a scalar secant relaxation. If `p` is the previous accepted initial-state change and `Δd` the change in raw correction, it estimates `ω=−〈p,Δd〉/(〈Δd,Δd〉)` using weights `A C`, bounded to `[0.5,1]`. The first correction uses one. Positivity and the same measured-merit line search still govern acceptance. A fixed factor near 0.87 improved the reference mesh cases but slowed very large-capacity cases; the secant estimate avoids most of that tradeoff. This is a numerical acceleration of the same periodic boundary condition, not a change to its forcing, equilibrium or convergence criteria.

Both maximum phase error and per-cell annual heating must meet their recorded tolerances. Defaults are `1e−5 K` phase and `1e−5 W/m²` annual flux, with relative allowance `1e−12` and integrated step-solve uncertainty. Phase tolerance measures repetition of a year, not a general bound on temperature error relative to the continuous equations. Entire unforced connected components have the analytically unique nonnegative periodic solution `T=0`; the driver selects that initial root directly instead of treating vanishing radiative restoring as evidence that an arbitrary warm guess has equilibrated.

The step solver records, rather than hides, representational uncertainty. A 1000-bar/0.050001-g column has such large capacity that an hourly temperature ulp represents several micro-W/m². Its flux tolerance therefore includes the local storage/radiative derivative times temperature spacing, pairwise transport spacing and parent-flux arithmetic spacing. An independently solved 240 W/m² case retains its actual `9.387e−7 W/m²` residual. Ordinary monthly cases had representational allowances no larger than `1.08e−11 W/m²` in the review, far below the `1e−7 W/m²` base step tolerance. No balancing heat, recentering or substituted zero residual is applied.

Independent tests cover analytical radiative equilibrium and cooling, unequal-area/capacity conservation, spatial harmonic refinement, seasonal amplitude and phase, temporal first-order convergence, initial-guess independence in the tested forced systems, monthly budget replay and explicit failure paths. Integration probes additionally exercised actual solar intervals with one or two columns over eccentricities 0.016, 0.5, 0.9, 0.999999 and the largest representable value below one. All 20 original and 40 subdivision cases converged numerically. At the last eccentricity, the minimum retained duration was `3.399e−20 s`; after tightening the annual relative tolerance, maximum measured annual heating was `0.000993 W/m²`, below a recorded tolerance up to `0.05163 W/m²`, with phase error at most `2.10e−7 K`. Temperatures can reach `2.41e10 K`: these are mathematical stress cases far outside the material, daily-averaging and atmospheric assumptions of this model.

**Temporal accuracy remains an integration gate.** Holding every original interval's fluence fixed and subdividing only its thermal integration from one to eight steps changes maximum monthly temperature by 0.197 K in reference polar land, 0.386 K for polar land at eccentricity 0.9, 30.7 K in a coupled 0.999999 case and 364.8 K immediately below eccentricity one. In the last case, four-to-eight refinement still changes 76.7 K. These differences are thermal discretization error, not loss of incoming energy. A converged periodic boundary and a closed energy ledger do not establish a temporally converged climate. Thermal adaptivity or a verified higher-order positive method, its cost, and an explicit applicability/accuracy policy must be addressed before advertising this as a generally precise production climate.

## 9. Reproducible real-mesh integration and performance probe

[`scripts/research/periodic_climate_benchmark.cpp`](../scripts/research/periodic_climate_benchmark.cpp) combines the actual native mesh builder, conservative transport, `SolarOrbitForcing` intervals and periodic column solver. It is a **prescribed-coefficient research model**, not a native world producer. The ocean is the spherical cap `position.x > −0.4`, with 70% continuum coverage; no generated terrain/lake/ice state is used. All cases use radius 6371 km, tilt 23.5°, luminosity 1, year `365.2422 × 86400 s`, albedo 0.3, gray emissivity `1/1.75`, `C_atm = 1004 p_Pa / 9.80665`, land storage addition `4e6`, water addition `2.09065e8` J m⁻² K⁻¹, and integrated conductivity `2.2e6 m² s⁻¹ × C_atm`. Initial temperature is uniformly 288.15 K. Pressure changes storage and transport only; opacity stays fixed.

Build outside the default production targets, from the repository root:

```sh
mkdir -p runs/research/periodic_climate
g++ -std=c++20 -O2 -ffp-contract=off -Icpp/include -Icpp/src \
  scripts/research/periodic_climate_benchmark.cpp \
  cpp/src/engine/climate_transport.cpp cpp/src/engine/mesh.cpp \
  cpp/src/engine/core.cpp cpp/src/engine/seasonal_energy_balance.cpp \
  cpp/src/engine/time_integrated_energy.cpp cpp/src/engine/periodic_energy_balance.cpp \
  cpp/src/engine/adaptive_energy_balance.cpp cpp/src/engine/solar_insolation.cpp \
  -o runs/research/periodic_climate/benchmark
runs/research/periodic_climate/benchmark --help
runs/research/periodic_climate/benchmark --backend fibonacci --cells 4096 --warm-replay
runs/research/periodic_climate/benchmark --backend geodesic --cells 4096
```

Each invocation prints one compact JSON record. Use `--pressure-bar 100` or `--eccentricity 0.9` to reproduce the stress cases; `--forcing monthly360` is available solely for comparisons using repeated monthly forcing, and was **not** used in the results below. Generated binaries/output belong under ignored `runs/`.

Measurements on 2026-09-09: single-process standalone GCC 15.2.0, `-O2 -ffp-contract=off`, x86-64 Intel Core i5-14400F; no OpenMP flag. Cases ran sequentially, although other development activity was not controlled. Wall times are local measurements, not portable performance guarantees. Reference eccentricity is 0.016 and actual forcing has 1080 intervals/year. All six reference cases converged in **13 periodic iterations / 14 full-year evaluations**.

| Mesh, actual cells | Solve seconds | Area-mean °C | Annual cell min/max °C | Monthly cell min/max °C | Global ASR−OLR W m⁻² |
|---|---:|---:|---:|---:|---:|
| Fibonacci 128 | 0.807 | 19.24383 | 1.01992 / 27.85970 | −7.91282 / 36.24213 | −1.034e−7 |
| Fibonacci 512 | 3.970 | 19.26131 | 1.03703 / 27.75336 | −4.94146 / 35.49169 | −1.077e−7 |
| Fibonacci 4096 | 57.813 | 19.26695 | 1.02736 / 27.73497 | −4.66900 / 35.35895 | −1.105e−7 |
| Geodesic 162, requested 128 | 1.048 | 19.23698 | 0.55616 / 27.89865 | −7.56391 / 36.19085 | −1.043e−7 |
| Geodesic 642, requested 512 | 5.051 | 19.26958 | 0.91858 / 27.77068 | −3.78853 / 35.08869 | −1.194e−7 |
| Geodesic 4412, requested 4096 | 61.449 | 19.26454 | 1.02734 / 27.73599 | −5.11089 / 35.45180 | −1.086e−7 |

The largest reference phase mismatch is `5.88e−7 K`; largest cell annual net heating is `4.09e−6 W/m²`. Fine-mesh global monthly transport cancellation is below `7.6e−17 W/m²`. Actual point-sampled solar absorption differs from the continuum value `0.7×1361/[4 sqrt(1−e²)]` by −0.000382 W/m² on Fibonacci 4096 and +0.000190 W/m² on geodesic 4412; no forcing normalization was applied. Their sampled ocean fractions are 0.701164 and 0.697876. Scalar temperature agreement is encouraging but does not replace a spatial/timestep convergence study.

The temporal refinement failures recorded in section 8 remain unresolved by these performance measurements. Small energy residuals and periodic boundary mismatch do not bound timestep error; the runtimes here use the unrefined interval schedule and do not establish temporal accuracy.

With profiling counters and the tightened periodic relative tolerance (`1e−10 → 1e−12`, absolute annual tolerance still `1e−5 W/m²`), Fibonacci 4096 repeated in **57.647 s with identical reported temperatures/residuals**. Its final cycle had 1080 integration steps, 2160 Newton iterations and 49024 linear iterations: 22.70 CG iterations per Newton step versus 6.93 at 128 cells. Maximum final-step residual was `2.51e−10 W/m²`. Increased linear-solve work, rather than extra periodic iterations, accounts for part of the scaling. Mesh/transport/forcing setup together cost 0.410 s. Reusing the accepted **phase-boundary state with exactly unchanged inputs** converged after one year evaluation in **4.043 s** (128 cells: 0.057 s). Thus eight independent cold starts would add roughly eight minutes at 4096 cells; preserving a valid phase-boundary starting iterate can reduce recomputation cost. Monthly mean temperatures are not interchangeable with that phase state, and changed geography still requires convergence checks.

Pressure-100-bar stress cases at Fibonacci 128/512 converged in 0.595/3.074 s, with 11 periodic iterations and means 19.67569/19.66665°C; global ASR−OLR was approximately −1.4e−9/−1.2e−9 W/m². These test high storage/conductance while intentionally holding opacity fixed, not physical 100-bar atmospheres. Eccentricity 0.9 at 128 cells converged in 0.732 s using 984 intervals and 14 periodic iterations, with global mean 70.02929°C and monthly cell extrema −17.34328/278.63399°C. Its global ASR−OLR was `6.77e−7 W/m²`; maximum cell annual heating `4.53e−6 W/m²`. Orbital motion near periapsis is about 0.75 radians per 24-hour rotation, undermining the daily-averaging assumption in section 6, and the prescribed liquid-water/material treatment is inapplicable at those temperatures. This is numerical stress evidence only.

Baseline periodic-driver SHA-256 was `348829da79f3e780a8d58ec0c624de2b93179bae543c422cefdbdc7373827025`; the counter/tolerance rerun used `ad888580ef61d5aeb683ac3d4d462d1994f1075d52d23b2961e09229e36b018e`. Both used seasonal-core `d8a26fd2fd17a4124b71bef76c58ae68fca64db099fc1f8e6028dc913e5785a9`, solar `9ca5e99ee969645a853c4cca0663040cdae5b6df89bf3c05fdbbd8f32546c4fe` and transport `9346beb5d9170bcbafc55370af3d94cb89b7aebcc5496870eaf51851a2f695a6`. Timings and iteration counts can change with subsequent numerical-core improvements; the preserved benchmark specifies the experiment independently of those measurements.

An adaptive scalar secant relaxation now reduces repeated-year work: for raw correction `d=F+H⁻¹R`, previous accepted shift `p`, and change `Δd`, choose `ω=clamp(−〈p,Δd〉/(〈Δd,Δd〉),0.5,1)` in the `A*C` inner product, starting with `ω=1`; positivity and the existing merit line search still control acceptance. The authoritative source reproduced Fibonacci 512 at **8 year evaluations / 2.251 s**, versus 14 / 3.979 s in the isolated unrelaxed comparison, and 100-bar 512 at **7 / 1.777 s**, versus 12 / 3.077 s. Maximum cell annual heating was `2.76e−6` and `4.14e−6 W/m²`, respectively. Fixed `ω=0.87` needed 9 and 8 evaluations and slowed a high-capacity scalar near equilibrium from 4 to 8; the adaptive factor retained 4, and retained 6 evaluations for three high-capacity columns (`C=2.04755e11 J/m²/K`). A cold high-capacity scalar needed 10 evaluations versus 9 unrelaxed, so acceleration is case-dependent. The current periodic regression executable, including exact dark-component roots, passed. This changes the nonlinear iteration, without changing the physical equations, timestep schedule or convergence tolerances, and does not resolve temporal discretization error. These measurements used periodic-driver SHA-256 `996af786fc73de36fac1caf718ff82b08985553d2b6b71543f97d7c611437e21` and seasonal-core `275ffc42f154ebd554b89075c7d0e74cf52dd087928b928de37cf3f5e5b34cbb`; the latter also reuses the CG product vector without changing arithmetic.

## 10. Temporal accuracy design and implementation

The design below motivated the implemented adaptive backward Euler (BE) reference and TR-BDF2 candidate. Section 11 records their completed comparisons at the same verification gate. The original 0.197 K reference polar-land difference was between one and eight subdivisions, not an established absolute error. Section 9's approximately 58-second 4096-cell solve made accuracy per unit runtime important.

| Method | Accuracy and work per attempted interval | Positivity and implementation consequence |
|---|---|---|
| BE step doubling | First order; one full step plus two half steps requires three implicit solves before rejection costs. | Accept the two-half-step solution and its ledger. Each solve retains the current nonnegative BE formulation. Richardson extrapolation would discard that guarantee. |
| Two-stage second-order L-stable SDIRK | Two implicit stages; an error estimator is also required. | An implicit stage can have a negative effective right-hand side. L-stability alone does not guarantee positive temperatures. Specify the actual tableau; method names do not determine these properties. |
| TR-BDF2, `γ = 2−sqrt(2)` | Second order; two implicit stages plus the initial explicit evaluation. Both implicit diagonal coefficients are equal, permitting shared approximate Jacobian/preconditioner work. | Check every stage and reject failures. A global BE fallback locally reduces order and still needs error control. |

[Bonaventura and Della Rocca, sections 3–4](https://arxiv.org/pdf/1510.04303), establish TR-BDF2's conditional monotonicity, with absolute-monotonicity radius `1+sqrt(2)`, and analyze hybrids with implicit Euler. This is a restriction relative to the applicable forward-Euler monotonicity bound, not a universal step duration. Their analysis precludes claiming unconditional monotonicity from second-order L-stability. For this coupled mesh, reject or change method for the **whole step**; independently changing each cell's method can destroy cancellation of shared heat transfers.

**Concrete controller.** From one starting state, compute `T_full = BE(h)` and `T_fine = BE(h/2,h/2)` under the same interval-constant source. The first-order local-error estimate is `T_fine−T_full`; accept `T_fine` when `E = max_i |difference_i|/[atol_K + rtol_K max(|T_start,i|,|T_fine,i|)] ≤ 1`, both half steps satisfy their nonlinear ledgers, and temperatures are nonnegative. Discard all trial ledgers on rejection. A proposed controller is `h_new = h × clamp(0.9 E^(−1/2), 0.2, 2)`; these controller constants are engineering choices. [PETSc's error-control documentation](https://petsc.org/release/manual/ts/#error-control-via-variable-time-stepping) describes the corresponding scaled-error acceptance, rejection and bounded step-change pattern. Nonlinear and roundoff uncertainty must be smaller than the requested temporal error budget; otherwise report the limitation. A local tolerance is not a bound on annual/monthly error.

**Second-order stages and ledger.** Write `F(T) = C^−1[Q−I(T)+H(T)]`, with `H_i = Σ_j G_ij(T_j−T_i)/A_i`, prescribed `Q`, and fixed capacities. Set `a = 1−1/sqrt(2)`, `b = 1/(2 sqrt(2))`. TR-BDF2 is

\[
Y=T_n+ah[F(T_n)+F(Y)],\qquad
T_{n+1}=T_n+h[bF(T_n)+bF(Y)+aF(T_{n+1})].
\]

The [SUNDIALS TR-BDF2 tableau](https://sundials.readthedocs.io/en/latest/arkode/Butcher_link.html#c.ARKODE_TRBDF2_3_3_2) supplies these coefficients and an embedded estimator; its higher-order embedding is less stable than the accepted second-order method. Validate the estimator on stiff cooling, not just smooth seasonal forcing. An initially simpler independent error estimate uses step doubling, with `(T_fine−T_full)/3`, at six implicit solves per trial. Never accept an extrapolated or embedded state merely because it has a higher formal order.

Derived from the stage equation, the accepted TR-BDF2 ledger must use weights `(b,b,a)` at `(T_n,Y,T_{n+1})` for **each** of `Q`, `I`, `H`, `T`, and `T⁴`; storage remains `C(T_{n+1}−T_n)`. Since `2b+a=1`, constant-source fluence is exactly `hQ` within arithmetic tolerance. Pairwise transport uses identical weights on both cells and cancels globally. Keep the actual weighted residual and propagated stage-solve uncertainty. Changing only the temperature integrator while retaining BE endpoint radiation would break this identity.

**Periapsis and repeatability.** Initially keep each astronomical interval's prescribed mean flux constant while adaptively splitting its duration: children then preserve parent fluence exactly. This controls thermal error in the prescribed staircase source. Separately refine the angular/time forcing partitions and recompute child astronomical fluences; repeating the parent's mean cannot establish accuracy for the true periapsis pulse. Keep month boundaries exact and retain both existing orbit-angle and elapsed-time limits. Use local interval coordinates so tiny positive durations are not lost by addition to a large absolute clock. Never impose a silent `dt` floor, drop a residual interval, cap eccentricity, or clamp temperature. If subdivision becomes unrepresentable or a work budget expires, fail explicitly with achieved error and remaining duration/fluence. A deterministic common partition during periodic shooting, refined and re-solved after checking the accepted year, avoids changing the numerical period map between trial states.

**Adoption gates:** verify analytic radiative cooling and unequal-area/capacity diffusion decay, nonnegative stages, exact source fluence, pairwise cancellation, and ledger replay after both acceptance and rejection. Demonstrate first-order BE and second-order TR-BDF2 convergence on smooth tests; separately check monthly means, `mean(T⁴)`, extrema and seasonal phase under both thermal and forcing refinement. A proposed reference gate is less than 0.01 K maximum monthly-temperature change across two successive refinements, with independently specified flux tolerances; this is an engineering target requiring evidence. Repeat polar, mixed-capacity and sharp-pulse cases, including explicit exhaustion/precision failures. Compare wall time, accepted/rejected steps, Newton/CG work and periodic evaluations on both real meshes at that same achieved accuracy. A nominal two-stage method is not evidence of a speedup, and numerical refinement cannot restore the extreme orbits' missing physical applicability.

**Implemented controller.** `adaptive_energy_balance.cpp` uses a fixed dyadic subdivision of each immutable astronomical interval for every periodic solve. It replays the accepted fine trajectory, compares each pair of half steps with a discarded full step, and refines/reconverges the whole periodic map when required. It does not use the proposed continuously changing `h_new` schedule within shooting. The error estimate includes endpoint temperature and monthly moment **increments**, scaled by interval duration divided by month duration; treating raw leaf means as local integration errors would assign the wrong convergence order. It retains the two-half-step ledger without extrapolation. After local checks pass, two separately reconverged uniform refinements must pass the monthly temperature, fourth-root-temperature and flux checks. Those checks measure observed refinement changes; they do not certify absolute error against the continuous physical climate.

The integrator exposes an explicit bound on endpoint uncertainty from nonlinear residuals and arithmetic. The controller rounds composite positive bounds upward, charges uncertainty inside the local error budget, and tightens nonlinear tolerances if numerical error consumes too much of that budget. BE's exact discrete map is nonnegative and nonexpansive. Positive TR-BDF2 stages alone do not establish nonexpansiveness: for two half steps the implemented bound propagates first-step uncertainty by `4(b/a)−1`, approximately 3.828427, and requires sufficient positivity margin. Exactly dark, disconnected zero-temperature components are handled analytically. Precision, representability and total-work limits fail explicitly; rejected trial ledgers and partition-dependent shooting history are discarded. The accepted partition and tightened solver options are returned for exact replay.

The integrated native build and all **19 CTest cases passed** after these changes (`runs/review-native-adaptive-energy-tests.log`). This includes analytic order/ledger tests, rejected-trial isolation, independent finer periodic comparisons, exact accepted-map replay, work exhaustion, solver tightening and unattainable-precision tests. World generation still uses its previous temperature producer.

## 11. Adaptive methods at the same monthly verification gate

The prescribed-source thermal methods and adaptive wrapper are now implemented and benchmarked; this supersedes section 10's earlier proposed/unbenchmarked status for those numerical components. The research executable remains separate from the native world temperature producer. Its default is still fixed backward Euler (BE). New options select `--method be|tr-bdf2`, `--adaptive`, local/monthly tolerances, fixed uniform subdivisions, and an independently initialized uniform TR-BDF2 reference comparison. JSON reports the accepted partition histogram, local and numerical error ratios, monthly confirmations, final-cycle Newton/CG counts and **total attempted steps across periodic solves and estimators**, including failed trials. Final-cycle iteration counters are not mislabeled as whole-run totals.

The following comparisons use the section 9 hardware/compiler setup and actual astronomical intervals, with local absolute tolerance `1e−4 K`, monthly temperature tolerance `0.01 K`, monthly OLR/transport tolerance `0.05 W/m²`, and **two successive reconverged monthly refinement confirmations**. Monthly temperature checks include both mean temperature and the fourth root of mean `T⁴`. Error columns below report the larger of those two temperature differences, and the larger OLR/transport difference, against the independent reference. Every uniform reference starts from the experiment's original initial state; it does not reuse the adaptive solution. Its coefficients and astronomical parent fluences are unchanged.

| Experiment / method | Adaptive solve s | Accepted steps/year | Total attempted steps | Temperature comparison K | OLR/transport comparison W/m² | Area-mean °C |
|---|---:|---:|---:|---:|---:|---:|
| Fibonacci 128 / BE | 12.103 | 23560 | 275144 | 0.00135087 | 0.0135575 | 19.24370636 |
| Fibonacci 128 / TR-BDF2 | 6.368 | 8640 | 61560 | 6.734e−7 | 5.301e−6 | 19.24370231 |
| Fibonacci 512 / TR-BDF2 | 23.744 | 8640 | 52920 | 4.454e−6 | 4.573e−5 | 19.26121485 |
| Isolated polar land / BE | 0.467 | 54512 | 493056 | 0.00380259 | 0.00642466 | −35.33351795 |
| Isolated polar land / TR-BDF2 | 0.116 | 8640 | 50760 | 1.508e−6 | 3.224e−6 | −35.33387401 |

For 128 cells, the reference uses uniform 8 and 16 subdivisions per astronomical interval; its own refinement changes temperature by at most `2.70e−7 K` and OLR/transport by `2.71e−6 W/m²`. The TR16 reference mean is **19.24370234°C**. Its two solves cost 18.42–18.46 s separately from the adaptive runtimes in the table. The BE accepted partition has 17 intervals with 8 subdivisions, 662 with 16, and 401 with 32; the TR partition has 8 everywhere. BE needed 1847 failed estimator trials and 25 periodic-year evaluations in total; TR needed no failed trials and 11 evaluations. Neither tightened its nonlinear tolerances. At this same verification gate, TR-BDF2 was about **1.90 times faster** and had smaller measured differences from the uniform reference. This is evidence for these experiments, not a universal speedup.

The bounded 512-cell run compared independent uniform TR4 and TR8 solutions: their refinement changes temperature by `1.01e−6 K` and OLR/transport by `2.74e−5 W/m²`; the reference mean is **19.26121490°C**. Reference computation took 44.165 s, and the complete run including the adaptive solve and setup took **67.942 s**, below its 120-second cap. The accepted adaptive partition and finer reference both have 8 subdivisions, but are independently initialized and converged. Their few-microkelvin difference is consistent with the allowed periodic phase mismatch: the adaptive result's `9.79e−6 K` is close to the `1e−5 K` stopping tolerance. This is not evidence of a finer-than-TR8 reference at 512 cells; the stricter TR8→TR16 comparison was performed at 128 cells. Adaptive 4096-cell cost has not been measured.

The polar experiment reproduces the **exact original** case: one isolated column at +90°, area `2e12 m²`, capacity `1.42377e7 J/m²/K`, emissivity `1/1.75`, initial 288 K and year `365.25 × 86400 s`. Its rounded historical capacity and calendar differ slightly from the mesh experiment and are retained deliberately. Fixed BE1→BE8 still changes monthly mean temperature by **0.196836677 K**, reproducing the earlier 0.197 K finding. Against uniform TR32, fixed BE1 has maximum mean-temperature error **0.225015 K**, and fixed BE8 still has **0.028179 K** error; the latter also differs by `0.051653 W/m²` in OLR. Both fail the selected gate. Adaptive BE and TR-BDF2 pass as shown above. The independent TR16→TR32 reference itself changes temperature by only `3.33e−7 K` and OLR by `6.24e−7 W/m²`, with mean **−35.33387362°C**. Its calculation takes about 0.55 s separately from each adaptive runtime.

All adaptive cases achieved both monthly confirmations. Accepted maximum local error ratios ranged from `6.11e−5` to `0.0657`; maximum numerical error ratios were below `8.5e−7`. Global ASR−OLR magnitude remained below `7.0e−8 W/m²` and maximum cell annual net heating below `6.77e−6 W/m²`. The tests therefore provide both achieved thermal accuracy and physical-ledger evidence for these **fixed staircase-source reference cases**. They do not close astronomical forcing-quadrature error, extreme-eccentricity applicability, lake/ice feedback, elevation treatment, or the native producer/configuration migration. In particular, the extreme-orbit limitations in section 8 have not been revalidated by these bounded reference-planet runs.

Build using the updated section 9 command, then reproduce with:

```sh
runs/research/periodic_climate/benchmark --cells 128 --method be --adaptive --reference-subdivisions 8
runs/research/periodic_climate/benchmark --cells 128 --method tr-bdf2 --adaptive --reference-subdivisions 8
runs/research/periodic_climate/benchmark --cells 512 --method tr-bdf2 --adaptive --reference-subdivisions 4
runs/research/periodic_climate/benchmark --case polar-land --method be --uniform-subdivisions 1 --reference-subdivisions 16
runs/research/periodic_climate/benchmark --case polar-land --method be --uniform-subdivisions 8 --reference-subdivisions 16
runs/research/periodic_climate/benchmark --case polar-land --method be --adaptive --reference-subdivisions 16
runs/research/periodic_climate/benchmark --case polar-land --method tr-bdf2 --adaptive --reference-subdivisions 16
```

These measurements used seasonal-core SHA-256 `b363afd14474f11d0e9c4e37507a6f02ca49812541288b3648de1139e72fea4d`, time-integrator `59594899143251da03a4e58a75014712b3a3a3ecc0cb9d2b384ee48cd6f67d7c`, periodic-driver `df4b787080841382bbb5e57282cf5e3dd1dd4be5f850ceac4caf35c83c3c8c7b`, adaptive-driver `c65ef1e25b9f9143b54c0172cd6ac430da556b0ba89406fa3e669a405d2312ec`, and unchanged solar source `9ca5e99ee969645a853c4cca0663040cdae5b6df89bf3c05fdbbd8f32546c4fe`. The benchmark source fingerprint was `29153607b30218f03ffeccc77aade9a2f8c2d7aecf8acbce27ce36453d789670`. Help, six new invalid-argument cases, strict JSON parsing and the unchanged fixed-BE default were checked in addition to these runs.

## 12. Independent astronomical refinement and local precision

`SolarOrbitForcing` now accepts an explicit integration refinement level 0–10. Each level halves both the maximum elapsed-time interval and maximum true-anomaly step, recomputing the astronomical nodes and fluences. The Python-compatible monthly API remains unchanged. A refinement request outside this declared work range fails explicitly. Refining astronomical forcing changes the prescribed source itself; it is distinct from section 11's thermal subdivision under a fixed parent mean. The research benchmark exposes `--forcing-refinement` and `--reference-forcing-refinement`, and requires an explicit uniform reference subdivision count when a different reference forcing is requested.

The following comparisons use TR-BDF2 with eight thermal subdivisions at the coarse astronomical level, and independently initialized TR4/TR8 reference solves at the next astronomical level. Other coefficients and calendars match sections 9 and 11. The reference's own thermal-refinement change is reported separately. Differences are observed changes, not certified continuous-model error bounds.

| Case / astronomical levels | Max monthly mean-T change K | Max monthly OLR/transport change W/m² | Max monthly ASR change W/m² | Reference TR4→TR8 T change K |
|---|---:|---:|---:|---:|
| Original polar land, 0→1 | 1.60458e−4 | 2.17207e−4 | 9.56544e−4 | 1.33936e−6 |
| Original polar land, 1→2 | 3.35930e−5 | 1.01363e−4 | 4.91757e−4 | 3.33048e−7 |
| Original polar land, 2→3 | 1.65663e−5 | 1.45711e−5 | 5.07626e−5 | 8.50941e−8 |
| Fibonacci 128, 0→1 | 2.18404e−5 | 1.79554e−4 | 4.18486e−4 | 2.69498e−7 |

The larger mean/fourth-root-temperature change at 128 cells is `2.18419e−5 K`. Its complete comparison cost 25.09 seconds, including the 6.65-second coarse solve and both finer-forcing references. These cases satisfy the selected 0.01 K / 0.05 W/m² comparison gates. Twilight transitions and periodic convergence contribute to the measured sequence, so a uniform factor-of-four rate is not claimed. High eccentricity, other inclinations/materials and production worlds have not acquired this accuracy evidence by association.

Reproduce the polar rows by using `L=0,1,2`, `R=L+1` in the following command, or use `--cells 128` instead of `--case polar-land` for the mesh row:

```sh
runs/research/periodic_climate/benchmark --case polar-land --method tr-bdf2 \
  --uniform-subdivisions 8 --forcing-refinement 0 \
  --reference-subdivisions 4 --reference-forcing-refinement 1
```

The completed records are `runs/research/periodic_climate/forcing_refinement_polar.json` and `forcing_refinement_mesh128.json`. They preceded the near-parabolic precision repair below; their eccentricity 0.016 schedules have three angular subdivisions in each time bin and do not enter the repaired single-interval branch.

**A local defect hidden by annual conservation.** At `e=nextafter(1,0)` and refinement level 10, subtracting nearby true anomalies close to π produced an interval mean inverse-square distance factor of **0.248291**, below the physical minimum near 0.25 by **0.68%**. Annual and monthly fluences still appeared correct because the rounded angular differences telescoped. The integration path now computes a short angular width from eccentric-anomaly endpoint vectors using `atan2(cross,dot)`, with a factored half-angle cross product. This avoids subtracting the nearly equal true anomalies. It applies to single-angular-interval bins; resolved multi-interval periapsis partitions retain the existing stable mean-anomaly inversion.

An independent [Decimal oracle](../scripts/research/solar_orbit_reference.py), using independently implemented trigonometry and Kepler bisection, agrees at 80 and 100 digits to more than 60 digits. Its first interval after apoapsis at level 10 has factor `0.25000000000302612994`. The repaired double-precision schedule has worst local excursion below the physical minimum of roughly `2e−11` relative, consistent with eccentric-anomaly endpoint precision. Tests impose a `2e−10` relative local allowance through refinement level 10, compare independent monthly/apoapsis fixtures and retain the analytic annual Kepler identity. The legacy monthly diagnostic is intentionally not used as the high-eccentricity local reference.

The [physical-column composition](seasonal_climate_vertical_model_research.md#implemented-adapter-and-verification) also exposed a replay issue: multiplying absorbed solar power in extended precision and then casting could double-round rare products by one binary64 ulp. Monthly temperatures were identical but retained residuals differed. The accepted source now uses the same single binary64 product as direct-node replay, with separate explicit positive-underflow detection. The combined native build and **22 CTest cases passed** after these repairs. This establishes reproducible numerical evidence for the declared prescribed model; it does not complete the [configuration migration](seasonal_climate_migration_plan.md) or [native output/Python integration](seasonal_climate_output_contract.md).

## 13. Prescribed climate on generated terrain

[`scripts/research/prescribed_climate_benchmark.cpp`](../scripts/research/prescribed_climate_benchmark.cpp) now exercises the composition adapter on an actual terrain artifact from the existing generator: Fibonacci 128, seed 424242, eight plates, one erosion iteration, otherwise reference parameters. It rebuilds the mesh and checks every exported position/area. The original three final lakes, occupying 11,980,141.9 km² at this coarse resolution, are explicitly treated as prescribed land only when `--inland-water-as-land` is supplied. This is a disclosed first-model approximation, not lake coupling. The terrain itself was produced by the legacy climate, so this is not a fully coupled new-model world.

The benchmark uses the prescribed model's defaults: mean pressure 1 bar, gravity 9.80665 m/s², hydrostatic profile 288.15 K, reference optical depth 1, albedo 0.3, atmospheric diffusivity 2.2e6 m²/s, actual marine depth capped at a 50 m slab, and a 365.2422-day year. Each row below performs a separately verified adaptive TR-BDF2 solve with two 0.01 K / 0.05 W/m² monthly confirmations. Astronomical refinement is level zero; these thermal checks do not independently establish forcing accuracy on this terrain.

| Solve | Time s | Total attempted steps | Periodic year evaluations | Global mean °C |
|---|---:|---:|---:|---:|
| Initial annual-radiative starting guess | 6.0679 | 57,240 | 11 | 18.560995602 |
| Unchanged coefficients, accepted phase as starting guess | 4.6138 | 44,280 | 5 | 18.5609956 |
| Changed coastal depth, prior phase as starting guess | 5.5698 | 52,920 | 9 | 18.560780830 |

All accepted cycles have 8,640 steps/year, phase mismatch at most `2.464e−6 K` and maximum cell annual net heating at most `1.588e−6 W/m²`. Final monthly refinement changes are at most approximately `3.311e−6 K` and `2.060e−5 W/m²`. Independent monthly replay agrees with emitted radiation within `6.81e−14 W/m²`, storage within `2.89e−14`, transport within `1.142e−12` and the signed residual within `1.150e−12`. The unchanged warm solution differs in monthly temperature by at most `1.591e−7 K`; a warm initial guess does not bypass verification.

The perturbation changes actual coastal cell 44 from 31.558964522 m to 10 m depth. Its surface capacity consequently falls from **131.957498 to 41.813 MJ/m²/K**. Deep cell 66 is adjusted from 11,882.068062 m to 11,903.635157 m using the two cells' actual area ratio, preserving the configured ocean inventory of **1.338e9 km³** to `1.164e−10 km³`. Its 50 m thermal slab stays unchanged. Exactly one total-capacity column changes; atmospheric pressures, opacity and transport remain identical. The resulting maximum monthly temperature change is **1.4304333 K**, demonstrating an actual seasonal storage response rather than an imposed Celsius adjustment.

Hydrostatic pressures range from 36,821 to 115,619 Pa. Atmospheric mass is `5.2012101167e18 kg`; mean-pressure residual is `3.908e−13 Pa` and mass residual 19.99 kg (`3.84e−18` relative). These are measured floating-point residuals, not balancing corrections.

The source header and `--help` specify the numeric CSV contract and build dependencies. Compile with the same C++20/O2/`-ffp-contract=off` setup as section 9, adding `seasonal_climate.cpp` and `physical_columns.cpp`, then run:

```sh
runs/research/prescribed_climate/benchmark \
  --surface-csv runs/research/prescribed_climate/terrain_128.csv \
  --inland-water-as-land
```

The input world/config/CSV, three final JSON records and compiler/source fingerprints are preserved under `runs/research/prescribed_climate/terrain_128*`; the manifest is `terrain_128_manifest.json`. The composition source fingerprint is `c44207ecf0352be722023c37155c315baf5ff171557b6d47f2f87bf4c1c024eb`. Compilation, help, malformed CLI, omitted lake-approximation flag, mismatched radius and strict JSON checks passed. The unchanged warm solve still costs 4.6 seconds at only 128 cells because it redoes adaptive verification. Passing a warm temperature vector alone does not make repeated producer stages inexpensive.

The subsequent [`PrescribedSeasonalClimateCache`](../cpp/src/engine/seasonal_climate_cache.hpp) owns one immutable verified result and an exact snapshot of every consumed geometry, marine/land and latitude field. Nested physical, source, accuracy and work options participate in the key through defaulted equality. Diagnostic temperatures, biomes and other unused later fields do not invalidate the prescribed model. A hit returns the existing result without numerical work; a miss uses the preceding phase only as an initial iterate and repeats all accuracy checks. Key/result construction finishes before a nonthrowing commit, so failed input validation, numerical work or allocation preserves the preceding result. Changed topology/count is checked; a different cell count starts from the ordinary initial guess.

On the same 128-cell terrain, one initial solve took **6.04420 s**, followed by **1,000 exact hits in 0.002972426 s** (mean **2.972426 µs/hit**). Completed numerical solves remained one and additional step attempts were zero, including changes to ignored diagnostic fields. The record is `runs/research/prescribed_climate/terrain_128_cache_probe.json`. This bounded measurement establishes cheap exact reuse, not unchanged-input reuse across different physics. Tests also change actual shallow-water storage, one-ulp geometry inputs, requested accuracy and owned subdivision vectors; changed problems cannot reuse the old result as their certificate. The shared library built and all **23 CTest cases passed in 30.29 s**, recorded in `runs/review-native-climate-cache-tests.log`. A later subdivision-vector ownership regression passed separately in **18.84 s**, recorded in `runs/review-native-climate-cache-ownership-tests.log`. The cache still requires explicit integration into the world-generation pipeline.
