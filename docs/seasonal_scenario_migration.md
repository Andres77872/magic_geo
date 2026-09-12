# Shipped scenario migration to seasonal climate

## Scope and coefficient choice

The ten complete world YAMLs (`earthlike_seed.yaml` and the nine gallery seeds)
now declare `config_version: 2`. Their two obsolete Celsius controls were
removed and replaced with `climate.reference_infrared_optical_depth: 1.0`.
Every other input was compared with the pre-migration snapshot and preserved,
including seed, mesh, compute policy, radius, gravity, orbital forcing, pressure,
greenhouse factor, ocean inventory, tectonics, hydrology and erosion.

The common optical depth is a declared gray-atmosphere baseline, not a fit to an
old target temperature. In the implemented column model,

```text
tau_i = tau_reference * greenhouse_factor * (p_i / 100000 Pa)
        * (9.80665 m/s² / gravity)
epsilon_i = 1 / (1 + 0.75 * tau_i)
```

The hydrostatic column pressures preserve the configured area-mean pressure.
Thus retaining different pressure, gravity and greenhouse-factor inputs retains
different optical depths despite the common reference value. No Celsius-to-tau
conversion is implied. See the [column model](seasonal_climate_vertical_model_research.md)
and [native integration contract](seasonal_climate_native_integration.md).

The matrix's snowball and hothouse overrides received the same replacement.
Its `schema_version: 1` remains the matrix document format; it is separate from
the base world configuration's version 2. No scenario expectations, empirical
targets or comparison thresholds were changed. The full matrix was not rerun
by this bounded migration probe, so this is not a claim that those gates pass.

## Preserved intent and retired controls

Names identify the original scenario intent, not a certification of the new
climate or biological habitability. The old base/lapse values below are retained
only for the explicitly selected V3 comparison in the reproduction script.

| Scenario | Original scientific/worldbuilding intent | Retired base °C / lapse °C/km | Preserved forcing L / pressure bar / greenhouse factor / gravity g |
| --- | --- | ---: | --- |
| Earthlike seed | Curated Earth reference inputs, motion scale 4 and rain scale 0.8 | 15 / 6.5 | 1 / 1 / 1 / 1 |
| Continental realm | Temperate land-rich realm, lower inventory and broad continental crust | 14 / 6.5 | 1 / 1 / 1 / 1 |
| Cryogenic slushball | Cold, weakly forced ice-survival setting | −10 / 6.5 | 0.55 / 0.9 / 0.5 / 1 |
| Glasswind desert | Zero-ocean water scarcity, rain scale 0.08, strong drying | 32 / 7.5 | 1.1 / 0.7 / 1.05 / 0.82 |
| Ironroot Super-Earth | Large high-gravity planet, dense atmosphere, area-scaled inventory | 14 / 6 | 1 / 1.8 / 1.05 / 1.6 |
| Oldstone stagnant | Ancient low-heat surface with zero plate motion and stronger erosion history | 8 / 6.5 | 0.9 / 0.8 / 0.85 / 0.9 |
| Pelagic archipelago | Maritime islands, high ocean inventory and rain | 18 / 6 | 1.02 / 1.25 / 1.08 / 0.95 |
| Solstice extreme | Severe regular seasons from 75° obliquity and eccentricity 0.08 | 12 / 6.5 | 0.98 / 1.1 / 1 / 1 |
| Verdant hothouse | Originally a hot wet jungle/wetland/river premise | 30 / 5.5 | 1.25 / 1.8 / 1.55 / 1.05 |
| Young volcanic | Small young hot-interior planet with rapid motion and strong uplift | 32 / 7 | 1.35 / 1.4 / 1.5 / 0.75 |

The actual default seed is a separate neutral configuration: seed 424242,
14 plates, motion scale 2, precipitation scale 1, and the same reference
optical depth 1. Its probe below uses one erosion iteration.

## Actual generated evidence

The 2026-09-09 run requested 128 cells and zero erosion iterations for each
shipped YAML. Plate counts and all other controls were preserved. The declared
geodesic backend for Continental realm resolves that request to 162 cells;
the other nine remain Fibonacci 128. The additional default-seed run uses 128
cells and one erosion iteration. These are actual V4 native generations, not
synthetic columns or a replay of legacy temperatures.

Each raw native artifact passed the independent native energy audit, then the
public geo enrichment pipeline consumed that same state. Patching only the
native call's return in this research driver avoids generating the world a
second time; the public configuration dispatch and enrichers still run. The
paired V3 generation uses the same reduced configuration, with the explicitly
retired controls restored. It is a separate legacy realization: temperature
changes can also change later cryosphere/surface state.

Means below are area-weighted from the serialized cell temperatures (four
decimal places). Ocean fractions and precipitation are from generic validation.
The prior gallery's declared-resolution legacy audit is superseded; these
results do not certify the migrated 2,048/2,562/4,096-cell worlds or their full
erosion histories.

| Scenario | Cells | Paired V3 mean °C | Seasonal mean °C | Ocean area fraction | Land rain mm/y | Generic errors / warnings | Native seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Earthlike seed | 128 | 15.010 | 17.383 | 0.547 | 977 | 0 / 0 | 11.41 |
| Continental realm | 162 | 13.998 | 18.433 | 0.452 | 1,651 | 0 / 0 | 13.74 |
| Cryogenic slushball | 128 | −21.239 | −37.742 | 0.648 | 349 | 0 / 1 | 8.73 |
| Glasswind desert | 128 | 31.872 | 20.980 | 0.000 | 60 | 1 / 1 | 17.77 |
| Ironroot Super-Earth | 128 | 17.205 | 22.427 | 0.562 | 3,032 | 0 / 0 | 10.77 |
| Oldstone stagnant | 128 | 4.368 | 3.308 | 0.305 | 546 | 0 / 2 | 13.05 |
| Pelagic archipelago | 128 | 20.083 | 32.678 | 0.742 | 5,077 | 0 / 0 | 11.01 |
| Solstice extreme | 128 | 12.248 | 19.439 | 0.523 | 2,058 | 0 / 0 | 6.10 |
| Verdant hothouse | 128 | 40.886 | 76.355 | 0.664 | 9,015 | 0 / 1 | 5.38 |
| Young volcanic | 128 | 41.985 | 69.632 | 0.125 | 1,381 | 0 / 2 | 9.75 |
| Neutral default, one iteration | 128 | — | 17.653 | 0.523 | 1,304 | 0 / 0 | 17.19 |

Ten of the eleven runs passed all 14 generic layer contracts. The dry Glasswind
run has no ocean, lake or runoff. Its single generic error is
`acyclic_downhill_drainage`: 27 dry terminal cells and no watershed basin
records. Links are adjacent and downhill, there are no cycles, and accumulation
residual is zero. Seven dependent layer contracts consequently fail. This is
reported for targeted producer/validator investigation, not hidden by lowering
a threshold or changing the preset. These figures record the original probe
before any subsequent correction to dry-terminal validation.

## Numerical acceptance and its limits

| Scenario | Final steps/year | Physical solves | Max phase difference K | Max annual net heating W/m² | Final monthly refinement ΔT K / Δflux W/m² |
| --- | ---: | ---: | ---: | ---: | --- |
| Earthlike seed | 8,640 | 2 | 2.71e−6 | 9.74e−7 | 4.73e−6 / 1.90e−5 |
| Continental realm | 8,640 | 2 | 1.78e−6 | 1.47e−6 | 3.14e−6 / 3.41e−5 |
| Cryogenic slushball | 8,640 | 2 | 4.00e−6 | 2.17e−6 | 3.49e−7 / 5.28e−6 |
| Glasswind desert | 7,808 | 4 | 2.71e−6 | 9.51e−7 | 3.92e−6 / 1.61e−5 |
| Ironroot Super-Earth | 8,640 | 2 | 3.30e−6 | 9.04e−7 | 1.61e−6 / 6.19e−6 |
| Oldstone stagnant | 8,640 | 3 | 5.90e−6 | 2.79e−6 | 4.78e−7 / 6.06e−6 |
| Pelagic archipelago | 8,640 | 2 | 7.93e−7 | 8.01e−7 | 6.36e−6 / 5.69e−5 |
| Solstice extreme | 7,504 | 1 | 4.43e−7 | 2.75e−7 | 6.43e−6 / 9.33e−5 |
| Verdant hothouse | 8,640 | 1 | 6.51e−6 | 4.74e−6 | 6.13e−7 / 5.04e−6 |
| Young volcanic | 7,312 | 2 | 4.90e−6 | 2.77e−6 | 1.97e−6 / 3.54e−5 |
| Neutral default, one iteration | 8,640 | 3 | 2.63e−6 | 9.89e−7 | 4.80e−6 / 1.91e−5 |

All runs retained two monthly refinement confirmations, with the unchanged
0.01 K / 0.05 W/m² monthly gates, local/numerical acceptance gates and
periodic phase/annual-energy gates. Independent audits passed 11,748–14,886
algebraic checks per world; the largest actual monthly ledger residual was
3.70e−8 W/m². No work-limit, precision, or native generation failure occurred.
Elapsed times are observations on an Intel i5-14400F, Linux x86-64, current
Release native library, with other development jobs running. Gallery presets
kept CPU/one-thread policy; Earthlike/default kept auto/zero threads. Native
seconds include native binding decoding and its upstream audit. Complete
per-case work including enrichment, validation and optional V3 comparison took
6.28–18.62 seconds. These are not declared-resolution performance estimates.

The independent audit checks published forcing nodes, hydrostatic/slab
coefficients, transport ledger identities, display linkage and phase/annual
gates. It does not independently regenerate orbital quadrature nodes, reconstruct
mesh conductances, or recover unexported time-integration trajectories and
refinement history. Its green result is not an Earth-calibration result.

The fixed-albedo, prescribed-column model has no closed lake/ice/cloud feedback.
Precipitation, wind, biomes and much ecology remain empirical. In particular:

- The cryogenic world's mean is −37.742°C, but marine classification and liquid
  inventory are not an equilibrium sea-ice coverage calculation. “Slushball”
  does not certify liquid refugia.
- Solstice's mean land seasonal range is 44.576°C and its hottest serialized
  monthly cell reaches 77.967°C. Monthly surface temperature is not an observed
  daily maximum, marine SST climatology, or organism exposure history.
- Verdant's mean is 76.355°C and Young volcanic's is 69.632°C. The current biome
  classifier still labels 100% and 58% of their land as forest, respectively.
  Those labels do not establish terrestrial forest viability; the original
  jungle/frontier premise is unverified under the preserved forcing. The
  migration does not cool these worlds by fitting opacity to their names. The
  [terrestrial dependency audit](terrestrial_climate_support_research.md) identifies
  actual positive productivity, biomass and forest-resource claims outside the
  current thermal proxy support, and specifies the correction still required.

## Reproduction

From the repository root, after building the current native library:

```bash
.venv/bin/python scripts/research/scenario_migration_probe.py \
  --output runs/seasonal-scenario-migration-replay --compare-legacy
.venv/bin/python -m pytest tests/test_seasonal_scenario_migration.py -q
```

Use `--only glasswind_desert` or `--only default_seed_128_iteration_1` for a
bounded repeat. No `/tmp` input or prior generated data is needed. The original
run artifacts are under `runs/seasonal-scenario-migration/`: each case has its
exact `.config.json`, compact `.result.json`, raw `.native.json.gz`, enriched
`.world.json.gz`, and `.validation.json.gz`. Generated data remains ignored.
The focused migration module passes 11 tests: ten explicit V4 mappings plus
the complete matrix's compatibility with the migrated reference configuration.
