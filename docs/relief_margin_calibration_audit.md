# Relief and continental-margin calibration audit

The canonical Earth's low marine area and excessive positive relief already exist before any maturation transition. The full-gain isostatic and oceanic thermal target differences telescope correctly; this audit found no repeated application of their initial offsets. The strongest concrete model gap is that initialization has continental interiors and oceanic crust but no physically distinct, thinned continental-margin structure. Increasing continental area alone does not fix it and worsens some held-out results.

## Failed targets and scope

The authoritative [post-fix matrix](../runs/review-geo-validation-after.md) reports these five canonical empirical misses:

| Metric | Observed | Existing target interval |
|---|---:|---:|
| Coastal land fraction | 0.3506 | 0.4340–0.5340 |
| Below-sea-level surface fraction | 0.610596 | 0.688984–0.728984 |
| Mean nonnegative surface elevation | 1191.35 m | 637.58–956.37 m |
| Surface elevation span | 17443.55 m | 12201.45–16507.84 m |
| Non-Antarctic endorheic watershed area fraction | 0.274942 | 0.094952–0.254952 |

This audit directly probes the elevation/sea-level causes. It does not establish that a margin implementation will also repair coast topology or endorheic drainage area. Those remain separate acceptance checks.

## Controlled native probes

All cases load `configs/earthlike_seed.yaml`, force `compute.backend=cpu`, `compute.threads=1`, and `output.float_precision=8`, and call `magic_geo.native.generate_geo_world(config_to_native(config))`. The baseline has seed 424242, 4096 Fibonacci cells, 14 plates, six erosion/maturation transitions, and continental target 0.34. Native generation excludes Python enrichment, so these measurements isolate the physical foundation. The existing target values and native coefficient files remain unchanged.

Only the erosion iteration count differs in this first comparison. Initial plate/crust/topography generation is otherwise identical. Each output includes the final cryosphere coupling.

| Iterations | Marine area fraction | Mean nonmarine land elevation | Minimum elevation | Maximum elevation | Span |
|---:|---:|---:|---:|---:|---:|
| 0 | 0.648173 | 1922.46 m | −10843.20 m | 8922.22 m | 19765.42 m |
| 1 | 0.632792 | 1724.42 m | −10479.23 m | 8543.26 m | 19022.50 m |
| 6 | 0.607881 | 1163.10 m | −10143.03 m | 7300.53 m | 17443.55 m |

At the unshifted initial datum, the largest connected below-datum component covers 64.9882% of global area and would hold **1.701982 billion km³** of water, 27.20% more than the configured 1.338 billion km³. This was independently summed from initial elevations, mesh adjacency and cell areas. The initial stabilization therefore shifts the sea-level datum downward by 1098.25 m. Consequently, initially modest continental freeboard becomes high relative to the water surface before erosion starts. Maturation reduces mean land relief and the span, while reducing marine coverage further. `mean_nonnegative_surface_elevation_m` is a different metric from the native mean over nonmarine cells: enclosed land can lie below the ocean datum. This explains the canonical 1191.35 m versus 1163.10 m values; they must not be interchanged.

Across the six canonical transitions, the sums of the global arithmetic means of isostatic and thermal changes are +212.113 m and +106.792 m. Per cell, each sum equals its final minus initial target within **4.55e−13 m**. This directly excludes repeated application of the same target offset as the cause of these runs' excess relief. It does not validate the physical target law itself.

An additional zero-plate-motion run was rejected as a clean motion ablation: setting the motion scale to zero also changes the initial ridge-derived spreading-rate/age field. Its initial sea-level adjustment is −2475.67 m instead of −1098.25 m. Comparing its final surface with the baseline would confound initialization with transport.

## Continental-area intervention: rejected as a standalone fix

The probe value 0.4072 reproduces one published global continental-crust area estimate as an exploratory input. It is **not** a proposed exact preset: observational definitions, uncertainty, and the generator's initial-versus-final distinction must be matched first. The two held-out seeds use 512 cells and the same 14 plates, six transitions, and other baseline inputs; they are not the differently configured matrix scenarios with similar seed labels.

| Seed | Cells | Initial continental target | Marine area fraction | Below-datum cell fraction | Mean nonnegative elevation | Span |
|---:|---:|---:|---:|---:|---:|---:|
| 424242 | 4096 | 0.34 | 0.607881 | 0.610596 | 1191.35 m | 17443.55 m |
| 424242 | 4096 | 0.4072 | 0.547618 | 0.622070 | 746.50 m | 16627.80 m |
| 1234 | 512 | 0.34 | 0.652288 | 0.660156 | 1233.80 m | 11245.28 m |
| 1234 | 512 | 0.4072 | 0.630829 | 0.632813 | 1000.75 m | 11403.37 m |
| 42 | 512 | 0.34 | 0.705116 | 0.705078 | 1104.22 m | 14544.14 m |
| 42 | 512 | 0.4072 | 0.783104 | 0.783203 | 1221.16 m | 14759.92 m |

Marine fractions use native cell-area weights; the below-datum column uses cell counts to match the canonical calibration extraction. Their tiny differences can reflect quadrature, while the large canonical 0.4072 difference reflects disconnected low terrain. The intervention improves one canonical relief metric but worsens ocean coverage and increases both relief metrics on held-out seed 42. It therefore supplies diagnostic evidence, not a validated replacement preset.

In the baseline final canonical state, **area-weighted** non-oceanic crust already covers 42.5071% of the globe, having started near 34%; marine water over non-oceanic crust covers only 3.4905%. The present-day observational total cannot simply be assigned to the initial mask and assumed to persist through transport and categorical rules.

## Concrete code findings

1. [Initial category assignment](../cpp/src/engine/tectonics.cpp#L225) builds continental interiors at `29 + 17*convergence - 8*divergence + noise` km. An outside-mask cell adjacent to a continental cell is tagged `transitional`, but it receives basalt lithology, 3.00 g/cm³ density, and the same 4.5–14 km thickness range as oceanic crust. The [oceanic predicate](../cpp/src/engine/tectonics.cpp#L513) treats transitional basalt as oceanic. Adjacency thus changes its label without creating a thinned continental margin.
2. The [continental mask](../cpp/src/engine/tectonics.cpp#L331) is ranked by cell count, not cumulative area. Fibonacci cells have nearly equal weights, so this is not the main canonical error; other meshes require an area-aware target definition.
3. [Initial topography](../cpp/src/engine/tectonics.cpp#L436) assigns those margin cells the −2500 m oceanic ridge baseline and oceanic age-depth subsidence. The [initial age solver](../cpp/src/engine/initial_oceanic_age.cpp#L50) also includes them in its ridge-distance oceanic field. The [Parsons–Sclater relation](https://doi.org/10.1029/JB082i005p00803) describes ocean-floor cooling depth; applying it to a genuinely continental margin requires a different thermal history, not merely changing a categorical name.
4. The [isostatic proxy](../cpp/src/engine/tectonics.cpp#L574) gives only 12 m per kilometre of continental thickness change. Meanwhile [independent initial relief terms](../cpp/src/engine/tectonics.cpp#L467) provide `20000*convergence²` m continental uplift and large trench/volcanic offsets. These terms are not derived from a crustal buoyancy balance. Example: final cell 518 remains at 7272.99 m with 28.30 km crust; 7101.59 m of its initial surface came from the separate orogenic term. This is evidence of decoupled relief support, not proof that every mountain must satisfy local Airy equilibrium.
5. [Full equilibrium updates](../cpp/src/engine/tectonics.cpp#L1577) correctly subtract the previous **local** target before adding the new target, consistent with terrain remaining on fixed cells. The empirical boundary increment is bounded separately. Initial mountain/trench relief is not itself advected with crust or explicitly relaxed toward a force-balanced target; it survives until erosion or other terrain changes remove it. This explains why correcting target differences alone cannot establish physically supported final relief.
6. [Conservative remapping](../cpp/src/engine/crust_transport.cpp#L1672) preserves crust volume and density/age moments, but selects category pairs by dominant incoming volume. Thick continental material can win a mixed cell's category over a larger area of thin oceanic material. Geological area, material inventory, and winning category are therefore different observables; all must be measured before attributing the growth of non-oceanic area to physical crust creation.

## Source definitions and proposed next implementation

[Mooney (2025)](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2025JB031907) distinguishes continental crust above sea level from continents **including rifted margins**: about 30.8% versus 40.7% of global area. Margins occupy about a quarter of continental area; they have roughly 26 km mean crust and a 15–30 km thickness tail. The paper distinguishes unweighted seismic-sample thickness means from area-weighted totals. These definitions support adding a margin structure, not fitting the emergent land mask to 41%. [Cogley (1984)](https://doi.org/10.1029/RG022i002p00101) independently mapped continental crust including submerged regions at about 41% of Earth.

Implement a versioned continental-interior → stretched continental-margin → oceanic transition before initial age and sea-level generation:

- Define total continental **material area** separately from exposed land and interior area. Allocate an explicit transition using physical distances or stretch history, and integrate area weights. A one-neighbor ring must not change physical width with resolution.
- Derive marginal thickness from continental stretching or a declared observed structural distribution. Preserve continental composition/density until explicit magmatic addition or oceanic creation occurs. A margin does not become 3.00 g/cm³ basalt solely because it touches an oceanic cell.
- Replace the disconnected thickness/freeboard proxy with one declared column-buoyancy calculation, including water loading across emergence/submergence. For fixed-density, dry columns, the Airy thickness response follows `(1-rho_crust/rho_mantle)*delta_thickness` in consistent units; submerged columns need water-column compensation. Do not add a second independent orogenic buoyancy term for the same thickening. [USGS isostatic-model parameters](https://www.usgs.gov/publications/isostatic-residual-gravity-and-crustal-geology-united-states) provide an example of explicit reference thickness and density contrast, not universal constants for every planet.
- Keep oceanic crust creation age separate from continental basement age and time since rifting. Continental extension can cause mechanical and thermal subsidence, while magmatic addition can offset it; [White and McKenzie (1989)](https://doi.org/10.1029/JB094iB06p07685) explicitly model these distinct mechanisms. A first bounded implementation may declare unmodeled thermal effects, but must not substitute old basement age into an ocean-floor cooling curve.
- Preserve/remap the appropriate material and relief state through later plate motion. Record mechanical, thermal, loading, dynamic-relief and sediment effects separately so each is applied once and can be replayed.

This is a proposed causal model correction. It requires implementation and validation before claiming any calibration improvement.

## Required gates before adopting that implementation

- Analytic column tests for density/thickness units, dry and submerged load balance, emergence continuity, and the oceanic zero-age intercept; no repeated cooling or buoyancy offset.
- Source-state tests proving continental margins retain their material identity, basement age and distinct thermal clock, while true oceanic creation has the appropriate age.
- Area and volume accounting across interiors, margins and oceanic material before/after remap; report mixed-cell fractions separately from display categories.
- Resolution checks for physical margin width/area and coastal connectivity on both supported mesh backends; compare elevation statistics at matched spatial support.
- Preserve current deterministic CPU/accelerator contracts, sediment-interface closure, ocean inventory, hydrology topology, and all stage replay checks. A passing empirical metric must not hide a conservation regression.
- Re-run all 22 pinned empirical targets and all diverse-planet paired response gates, plus several held-out seeds and resolutions. Specifically track the five misses above, coastal continental area, disconnected below-datum area, initial/evolved hypsometry, and extreme-cell crustal support. Do not loosen target intervals or select a favorable seed.

## Reproduction and evidence identity

The [offline buoyancy follow-up](relief_buoyancy_prototype.md) evaluates actual initial columns with a local Airy response, explicit water loading, and the unchanged ocean inventory on the canonical world and held-out seed 42 at both 4096 and 512 cells. It lowers initial relief but does not produce enough submerged continental material to establish a margin correction. The follow-up distinguishes raw initial-surface metrics from the post-cryosphere final metrics above, and rejects its 512-cell loaded-water case because that **offline modified surface** has no exact connected-ocean flood-interval solution. The unchanged production world conserves its configured water volume. No production or preset adoption follows from the prototype.

The probe scripts were `/tmp/magic_geo_relief_probe.py` and `/tmp/magic_geo_crust_area_probe.py`; raw numeric results were `/tmp/magic_geo_relief_probe.jsonl` and `/tmp/magic_geo_crust_area_probe.jsonl`. Reproduce using the native API and overrides described above; derive the span as `max(elevation_m)-min(elevation_m)` and nonnegative mean from cells with `elevation_m >= 0`. For the gain check, sum each cell's `*_equilibrium_change_m` over `plate_motion_history[1:]` and compare with final minus initial `post_process_local_*` target arrays.

The inspected `tectonics.cpp` SHA-256 was `cb112e0ac4afca7e24d29979d360ec18bf5ee6f5a7bd7188d2b4ae0a475de51a`; native library SHA-256 was `b3c113c599eab3c73bacd0c4849d6bfe79e2c01ffbdc837c18e26b9843bddd30`. The markdown tables preserve the results if temporary probe files are later removed.
