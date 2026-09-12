# Offline initial-buoyancy prototype

The bounded prototype reduces excessive **initial** continental relief on both tested seeds, but it does not establish a safe production correction. Marine coverage changes little, most continental material remains exposed, and one coarse-grid water-loading case cannot satisfy the connected-ocean volume constraint. Production code and presets were not changed. These results extend the [margin calibration audit](relief_margin_calibration_audit.md).

## Scope and physical assumptions

The prototype uses actual native cell areas, adjacency, initial elevations, and crust columns. Initial thickness and density are reconstructed by subtracting exported transition changes from the mature columns; initial categorical arrays come directly from `plate_motion_history[0]`. The canonical world is seed 424242, 4096 cells, 14 plates, six transitions. Held-out seed 42 uses the same configuration at 4096 cells and additionally 512 cells. The native library is identical to the earlier audit.

Only the initialization surface is re-evaluated. The prototype does **not** replay maturation, erosion, climate, lakes, sediment transfer, or societies on that new surface. “Original initial surface” means the exported `initial_elevation_m` produced by `derive_crust_and_topography`, followed only by this independent connected-ocean datum solve. It precedes numeric-depression stabilization and cryosphere coupling. It is therefore distinct from the earlier audit's zero-iteration native result, which already includes both of those processes. For example, canonical raw initial span is 19836.82 m here, while the native zero-iteration post-cryosphere span is 19765.42 m.

“Original mature baseline” means native `elevation_m` after six maturation transitions and the final cryosphere coupling. Those rows exactly reproduce the final calibration metric identities, but provide context, not predictions of the modified model. Using initial statistics to claim that final calibration targets pass would be incorrect.

For continental columns, replace the existing thickness/density proxy by a declared local Airy column balance:

```text
y_i = 500 + 1000 * [(rho_m - rho_i) T_i - (rho_m - 2.72) * 30] / rho_m
```

Here `y_i` is unloaded elevation in metres, `T_i` is actual crust thickness in kilometres, and densities are in g/cm³. Mantle density is assumed homogeneous at `rho_m=3.30`. The existing reference column (30 km, 2.72 g/cm³, 500 m freeboard) is held fixed, not selected from calibration results. The derivative with respect to thickness is about 158–182 m/km for the existing continental densities, rather than the current 12 m/km. The exact variable-density expression is used, rather than independently fitted thickness and density coefficients.

This is a mass-balance approximation, not a universal continental elevation law. [Lamb et al. (2020)](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2020GC009150) derive the local crustal response and water correction, and identify mantle-lithosphere buoyancy as necessary for continental-margin modeling. The missing lithospheric structure therefore remains a material limitation.

The main variant removes the separately prescribed continental `initial_orogenic_uplift_m` while retaining the other exported relief terms. This tests relief supported by the existing thickened crust plus the remaining declared residuals. It does not prove all dynamic mountain support is zero, or that the old full-gain updates repeatedly count their initial targets. An additional variant retains the orogenic term to distinguish those mechanisms.

For coupled water loading, use `rho_w=1.03` and `f=rho_m/(rho_m-rho_w)=1.45374449`. At common sea datum `S`, a marine cell's elevation relative to water is `e_i=f*(y_i-S)`, while a dry cell has `e_i=y_i-S`. This follows equal column pressure with the added water mass, is continuous at emergence, and is checked against explicit column masses. Existing oceanic age-depth/relief values `b_i` are already water-loaded at datum zero, so their unloaded equivalents are `y_i=b_i/f`; the oceanic cooling curve is not applied again.

Sea level is solved over flood intervals using the **largest connected component by area**, matching `cpp/src/engine/ocean.cpp`. The reduced-elevation solve uses volume `V/f`, then reconstructs actual marine depth and verifies `sum(area_km2 * depth_m / 1000)=V`, with the original `V=1,338,000,000 km³`. This is an algebraic loading correction, not a reduction in physical water inventory. Disconnected low cells receive no ocean loading. No cell fractions, water inventory, elevations, or densities are renormalized to make a target pass.

## Results

Marine and submerged continental percentages use cell-area weights. “Submerged continental” means marine water over non-oceanic material, expressed as a percentage of the **whole globe**. The positive-elevation mean uses cells with elevation at least zero, matching the existing calibration extraction. Area-weighted means differ by less than 1.1 m in these cases.

| Seed / cells | Surface variant | Marine area | Mean nonnegative elevation | Submerged continental area | Relief span |
|---|---|---:|---:|---:|---:|
| 424242 / 4096 | Original initial surface | 64.8173% | 2161.36 m | 0.0000% | 19836.82 m |
| 424242 / 4096 | Remove continental orogen only | 64.8173% | 1588.46 m | 0.0000% | 13295.51 m |
| 424242 / 4096 | Airy, retain orogen, rigid water | 65.2333% | 2048.55 m | 0.2202% | 21550.86 m |
| 424242 / 4096 | Airy, remove orogen, rigid water | 65.2333% | 1468.97 m | 0.2202% | 14778.64 m |
| 424242 / 4096 | Airy, remove orogen, loaded water | 66.0385% | 1202.73 m | 0.9765% | 14427.96 m |
| 424242 / 4096 | Original mature baseline | 60.7881% | 1191.35 m | 3.4905% | 17443.55 m |
| 42 / 4096 | Original initial surface | 65.1595% | 2206.58 m | 0.0000% | 16418.78 m |
| 42 / 4096 | Remove continental orogen only | 65.1595% | 1848.44 m | 0.0000% | 11522.11 m |
| 42 / 4096 | Airy, retain orogen, rigid water | 65.1839% | 2031.95 m | 0.0244% | 17944.49 m |
| 42 / 4096 | Airy, remove orogen, rigid water | 65.1839% | 1673.05 m | 0.0244% | 12631.14 m |
| 42 / 4096 | Airy, remove orogen, loaded water | 65.5740% | 1316.37 m | 0.3657% | 12234.00 m |
| 42 / 4096 | Original mature baseline | 69.6322% | 623.94 m | 24.3685% | 13558.61 m |
| 42 / 512 | Original initial surface | 64.4424% | 2293.27 m | 0.0000% | 15185.80 m |
| 42 / 512 | Airy, remove orogen, rigid water | 64.8339% | 1543.11 m | 0.3915% | 10702.79 m |
| 42 / 512 | Original mature baseline | 70.5116% | 1104.22 m | 21.6865% | 14544.14 m |

All rows in the table preserve ocean volume within `4.1e-6 km³`, about `3.1e-15` relative error. Crust volume and density moments are exactly unchanged by construction: the prototype moves no crust or sediment material and changes no thickness or density.

The **loaded-water seed-42/512 variant is rejected**: the discrete connected flood intervals yield a closest volume of `1,335,668,477.73 km³`, a deficit of `2,331,522.27 km³` (0.174254%). Its apparent statistics—66.2007% marine area, 1306.26 m positive mean, 1.3667% submerged continental area, 10371.08 m span—are not an admissible conservation result. This is a limitation of the offline modified surface and loading solve, not a measured production-native failure: unchanged native seed 42/512 finishes with `1,337,999,999.9999993 km³`. A full coupled implementation would need to resolve this topology/volume incompatibility explicitly, including its stabilization stages, not hide it by scaling water depths.

Changing only the buoyancy law while retaining the old orogenic term **increases** span on both 4096-cell worlds. Removing that term reduces the upper extreme strongly, but cannot by itself create a submerged margin: ocean area is unchanged in that ablation. Even the loaded variant submerges only 2.87% and 1.08% of initial continental area on the canonical and held-out 4096 worlds, respectively.

## Why no margin relabeling or thickening was adopted

The existing initial `transitional` label is an outside-mask neighbor ring containing roughly 7 km of basalt at density 3.0. It is not an exported stretch-history-derived continental layer. Its observed area is unsuitable as a physical margin-width prescription:

| Seed / cells | Existing ring area | Continental mask plus ring | Ring mean thickness | Extra rock if every ring cell were simply thickened to 26 km |
|---|---:|---:|---:|---:|
| 424242 / 4096 | 15.6983% | 49.7082% | 6.8465 km | 1.5336 billion km³, +20.63% total crust volume |
| 42 / 4096 | 28.8055% | 62.8174% | 6.7333 km | 2.8308 billion km³, +38.18% total crust volume |
| 42 / 512 | 37.4786% | 71.4746% | 6.9378 km | 3.6440 billion km³, +48.01% total crust volume |

The 26 km diagnostic comes from the observed average of rifted continental margins; it is **not** assigned by the prototype. [Mooney (2025)](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2025JB031907) describes approximately 41% global continental crust including margins, with extended continental material in the transition and thinner marginal structure. Those observations support a different structural model, not the creation of the quantities of rock shown above. Reclassifying the ring without thickening would instead change composition without a justified material transformation. Neither operation is a conservative margin simulation.

## Implementation implications and gates

A production investigation would touch [tectonics.cpp](../cpp/src/engine/tectonics.cpp) for initial structure and equilibrium targets; [initial_oceanic_age.cpp](../cpp/src/engine/initial_oceanic_age.cpp) for the oceanic-versus-margin clock; [ocean.cpp](../cpp/src/engine/ocean.cpp) and [pipeline.cpp](../cpp/src/engine/pipeline.cpp) for coupled loading and initial-state ordering; and [crust_transport.cpp](../cpp/src/engine/crust_transport.cpp) for conservatively advected margin material/history. The reference parameters and exported model contract in [constants.hpp](../cpp/src/engine/constants.hpp) and [process_serialization.cpp](../cpp/src/engine/process_serialization.cpp) would need explicit versioning. A mere substitution of the 12 m/km coefficient is insufficient because water loading depends on the solved sea datum.

Independent replay changes would include [oceanic_age_depth_validation.py](../src/magic_geo/oceanic_age_depth_validation.py), [initial_oceanic_crust_age_validation.py](../src/magic_geo/initial_oceanic_crust_age_validation.py), crust process/transport/material/dry-rock validators, [sediment_interface_validation.py](../src/magic_geo/sediment_interface_validation.py), and the initial-relief formula replay in [validate.py](../src/magic_geo/cli/commands/validate.py). [tectonic_zones.py](../src/magic_geo/tectonic_zones.py) also derives an orogenic signal from the initial uplift term and must be given a causal replacement if that term changes meaning.

The temporary script passes analytic connected-ocean, dry/wet column-mass and emergence-continuity checks. Before production adoption, it still needs explicit mantle/rift thermal state, volume-preserving margin formation, a solution to discrete ocean volume gaps, full maturation reruns, cross-resolution behavior, all existing conservation/replay checks, and the unmodified empirical/paired-response matrix. These tests provide evidence to reject a quick scalar or categorical fix, not evidence that the scientific goal is achieved.

## Reproduction

The standalone [research script](../scripts/research/buoyancy_prototype.py) preserves the original formulas and can generate every required native input, including the canonical world. From the repository root, run:

```sh
.venv/bin/python scripts/research/buoyancy_prototype.py \
  --cache-dir runs/research/buoyancy/cache \
  --output-dir runs/research/buoyancy
```

It reuses existing inputs and generates missing ones, with one CPU thread and eight-digit output precision. No temporary-file prerequisites remain. The fixed cases are `canonical_424242_4096`, `heldout_42_512`, and `heldout_42_4096`; repeat `--case NAME` to select a subset. Cache files are named `NAME.json`. Both configurable directories must remain inside the repository's ignored `runs/` tree; generated inputs and results are not source artifacts.

Run `python3 scripts/research/buoyancy_prototype.py --analytic-only` for the column-mass, emergence, and connected-ocean checks without native imports, generation, or files written. Add `--cache-only` to the full command to replay saved inputs and fail if any input is missing. Cached replay also uses only the standard library. `--help` lists the options.

The output directory contains `buoyancy_prototype_results.json` with the full result table and `buoyancy_prototype_manifest.json` with script/input/result hashes, physical constants, analytic-check results, and generation provenance. New input caches record the actual native configuration and native-library/config hashes. Legacy input caches lacking embedded provenance are labeled explicitly; the manifest does not invent their generator identity. Replay against the three original cached inputs reproduced every original numeric result exactly, including the rejected water-volume case.

Original evidence identity is retained in the script and manifests: temporary prototype SHA-256 `e01e6b980e92cac37b259e35fec188fb4a6fc0b820ecc52c4a32f37f3325c793`; native library SHA-256 `b3c113c599eab3c73bacd0c4849d6bfe79e2c01ffbdc837c18e26b9843bddd30`; Earthlike configuration SHA-256 `47ea1f846439ae8dd00b09fb5a687532f7c49150f2c83a50c7f56a44c76875c6`. Generation with a later native library or changed preset is a new experiment, not automatically the original evidence. These tables preserve the historical findings independently of the cache.
