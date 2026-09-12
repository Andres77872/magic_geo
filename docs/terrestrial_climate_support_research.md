# Hot-world terrestrial ecology audit

Read-only review, 2026-09-09. The bounded correction below is proposed, not implemented.

The preserved-forcing hot worlds expose a real dependency defect in biological diagnostics. They produce positive terrestrial productivity, biomass, forest growth, mature-canopy histories, and forest renewable resources when the existing temperature-suitability function is exactly zero. The solved temperatures are not the correction target. The immediate correction should declare the empirical model's applicability and propagate unavailable inputs through its biological consumers. A later physiological replacement needs separate calibration and validation.

## Archived evidence

These observations come directly from `runs/seasonal-scenario-migration/{verdant_hothouse,young_volcanic}.world.json.gz`. No regeneration, coefficient adjustment, or payload mutation was performed. The companion extracted observations are `runs/seasonal-scenario-migration/hot_terrestrial_ecology_stats.json`.

“Terrestrial” below excludes both native marine cells and standing lakes, using the existing shared aquatic selector. The reported land forest fractions use the scenario report's nonmarine area convention, which includes lakes in the denominator. These are different denominators for Young volcanic (112 nonmarine cells, 109 terrestrial cells).

| Observation | Verdant hothouse | Young volcanic |
|---|---:|---:|
| Terrestrial cells | 43 | 109 |
| Land area assigned a forest biome label | 100% | 58.1323% |
| Terrestrial annual temperature range, °C | 40.5868–93.8943 | 28.3440–92.4688 |
| Terrestrial cells with annual temperature ≥52°C | 39 | 91 |
| Terrestrial cells with every monthly mean ≥52°C | 37 | 68 |
| Positive primary-productivity estimates at annual temperature ≥52°C | 39 | 91 |
| Positive biomass estimates at annual temperature ≥52°C | 39 | 60 |
| Forest renewable records at annual temperature ≥52°C | 39 | 51 |
| Succession histories at annual temperature ≥52°C | 39 | 54 |

Verdant cell 21 is a compact integration witness: annual temperature **73.7713°C**, monthly means **70.0308–77.3640°C**, rainfall **6563.1536 mm/year**, and `climate_class=Af`. It reports `growing_season_months=12`, `primary_productivity_index=0.632920`, `vegetation_biomass_index=0.736804`, `forest_growth_index=0.625205`, `vegetation_succession_stage=mature_closed_canopy`, and `biome_confidence_index=0.9078`. Its native biome is `tropical_rainforest`.

Young cell 8 supplies a second mesh/planet witness: annual **63.1827°C**, monthly **58.3300–68.2038°C**, rainfall **2836.2076 mm/year**, primary **0.668920**, biomass **0.757504**, forest growth **0.666531**, 12 growing months, and a mature canopy. The current species module also assigns `canopy_tree` as dominant guild to all 39 hot Verdant cells and 53 hot Young cells.

The same mathematical bypass exists at the cold end: all 45 terrestrial cells in the cryogenic artifact are outside the annual thermal function's support and have zero growing months, yet all have positive primary estimates (0.207297–0.344249); four receive succession histories. This does not establish a universal cold-survival cutoff. It confirms that the existing temperature term is not actually a prerequisite for its own production estimate.

## Exact dependency paths

1. **Native biome label and soil fertility:** `cpp/src/engine/environment.cpp:301`, `derive_soils_biomes_resources`. After cold/ice/desert branches, lines 367–372 classify rainforest when annual temperature exceeds 23°C and precipitation exceeds 2100 mm, or seasonal forest above 21°C and 950 mm. There is no upper temperature limit. `climate_soil` at line 336 is a product of clipped precipitation and a monotonically increasing thermal term; it saturates at high temperature rather than representing vegetation viability. Fertility can remain high in the same cells.

2. **Growing season and repeated biome agreement:** `src/magic_geo/biome_dynamics.py:89`, `enrich_world_with_biome_diagnostics`. Lines 116–121 count any month with temperature ≥5°C and precipitation ≥0.25 PET. There is no upper-temperature criterion. `_expected_biome` at line 24 repeats warm/wet forest branches without an upper domain, `_limiting_factor` at line 65 has cold but no heat-applicability state, and the confidence formula at line 148 rewards agreement and moisture. Consequently the label and its “confidence” reinforce two related heuristics; this is not independent evidence of biological forest viability.

3. **Terrestrial primary production:** `src/magic_geo/ecosystem_dynamics.py:32` defines `s(T)=clip(1−|T−18|/34,0,1)`, whose positive support is the open interval **(−16,52)°C**. `_primary_productivity` at line 70 gates only aquatic estimates. The terrestrial result at line 90 is `clip(.26s + .22 water_balance + .18 moisture + .18 fertility + .18 growing − .14 aridity − .18 ice)`. When `s=0`, the positive nonthermal terms can sum to **0.76**. Verdant 21 independently replays as `.22 + .18*.8 + .18*.494 + .18 = .63292`; no temperature contribution is needed.

4. **Biomass, forest growth, and history:** `_vegetation_biomass` at line 93 adds a forest-label bonus of 0.28 and soil/moisture terms. Even merely zeroing primary leaves substantial biomass. `_forest_growth` at line 144 adds biomass, moisture and fertility without a thermal prerequisite. `_succession_stage` at line 116 can then label a mature canopy, `_history_steps` at line 155 fabricates establishment/maturation phases, and lines 263 and 284 emit histories and forest resources based on these scores. Zeroing one scalar cannot fix this chain; availability must propagate.

5. **Dependent claims:** `species_ranges.py:204` adds a 0.24 forest bonus plus primary, biomass, forest-growth and moisture terms for canopy trees; its terrestrial gate currently checks aquatic habitat, not thermal/primary applicability. `wildfire_disturbance.py:78` uses biomass and a forest bonus for fuel. `land_use_zones.py:38` separately adds fertility, moisture and growing-month terms even when its own thermal score is zero. These paths must not consume an unavailable productivity sentinel as established vegetation or agricultural capacity. This audit does not establish a universal animal-survival or wildfire-temperature rule.

6. **Order and validation scope:** `api.py:226–233` publishes soil and biome diagnostics before ecosystem, species and wildfire enrichment at lines 249–252. The current `ecosystem_dynamics_model` v3 declares aquatic support and exclusion policies only. `biome_realism.py:148` checks forest water availability, not heat tolerance: its forest check passes at 1.0 in Verdant and 0.769231 in Young. Passing that specific water check is correct for its narrow statement, but it cannot validate the broader forest biology.

### Native resource and settlement implications

The native stage precedes all Python ecological availability fields: `cpp/src/engine/pipeline.cpp:190` derives soils/biomes/resources and line 203 generates settlements. A Python-only primary-productivity fix therefore cannot retroactively justify already generated native agricultural settlements or their dependent regions/routes.

`environment.cpp:351` builds fertility from lithology, saturated climate-soil, river and slope terms; line 406 can assign resource code 7 (`fertile_alluvium`) from alluvial soil plus fertility. This descriptor may identify nutrient-bearing alluvial material, but cannot by itself establish that crops grow in the current climate. Metals, evaporites, sedimentary fuels and geothermal resources have distinct geologic interpretations and must not disappear merely because current photosynthetic productivity is unavailable.

At lines 412–423, native settlement score is a sum of water access, fertility, a resource bonus and a thermal score `clip(1−|T−17|/31)`. With its own thermal score zero, the other positive terms can still total 0.86 before hazards. `settlements.cpp:25` accepts nonmarine/nonlake candidates with score ≥0.48, and `settlement_type_for_cell` at line 5 can classify an agricultural settlement from fertility >0.66 or `fertile_alluvium`. These are independent additive applicability holes; the primary proxy's (−16,52) interval must not automatically replace this separate model's own domain or become a human-survival limit.

| Consumer | Required treatment in a complete correction |
|---|---|
| Native fertility/alluvium | Separate soil/material potential from currently supported biological/agricultural fertility; do not erase geology or silently relabel it crop productivity. |
| Native settlement score/type | Introduce its own explicit applicability/assumptions before candidate generation, or clearly withhold biological/agricultural/habitability interpretation; preserve a distinction between extractive access and agricultural capability. |
| Python primary → biomass → forest → histories/resources | Propagate independent availability and prevent unsupported parent sentinels or label bonuses from authorizing child claims. |
| Species canopy-tree scores | Require the relevant supported vegetation inputs, and separately define each guild proxy's own applicability; land membership alone is insufficient. |
| Python land use | `_agricultural_potential` needs its own climate/seasonal/parent support before emitting agricultural zones at its numeric threshold. Native fertility and a warm/moist-month descriptor cannot substitute for unavailable crop-model input. |
| Wildfire fuel/spread | Rebuild or mark vegetation-derived fuel availability and history claims consistently. An unsupported live-production estimate is not evidence that existing dead fuel is absent; do not infer physical non-burnability from that flag. |
| Validators and output/UI | Replay declared support independently; show unavailable estimates distinctly; keep geologic descriptors and mathematical climate classes discoverable with their actual scope. |

## Climate classification versus biology

The separate `climate_dynamics.classify_koppen_geiger` implementation at line 69 operates on monthly temperature and precipitation. Beck et al.'s classification assigns tropical A when the coldest monthly temperature is at least 18°C after the arid-class test; Af additionally requires at least 60 mm in the driest month. Those criteria contain no upper tropical-temperature boundary. An Af result can therefore be arithmetically correct for an extreme synthetic climate while providing no physiological validation for living rainforest. The published map was constructed and evaluated for Earth's climatic datasets, not arbitrary high-temperature planets.[^1]

The native `biome` is a different annual heuristic, not a synonym for this Köppen result. Its label should be explicitly described as an empirical potential climate/vegetation class wherever retained. Its agreement score should not be presented as a probability of forest survival or productive canopy cover. A new biological applicability status must be visible in summaries and maps; otherwise retaining a literal forest label and a 100% “forest” headline recreates the misleading claim after numerical growth is suppressed.

## Primary ecological evidence and limits

Doughty et al. report an average tropical-tree leaf threshold near **46.7°C** for the beginning of photosynthetic machinery failure, using leaf and canopy measurements and warming experiments. They also emphasize uncertainty in acclimation, threshold variation, and the transition from leaf failure to tree mortality. This is a leaf-temperature result, not a universal annual-air-temperature cutoff. It supports rejecting claims of verified tropical forest function under 70–77°C monthly means, but does **not** justify inserting 46.7 into an annual-temperature gate or claiming that every organism dies there.[^2]

LPJmL4 computes daily photosynthesis from absorbed photosynthetically active radiation, temperature, daylength and canopy conductance. Its equations include plant-functional-type-specific high/low temperature inhibition and couple production to water and carbon processes. This provides a model-design precedent for actual limiting processes and temporal integration rather than compensating for absent thermal photosynthetic support with additive fertility or a vegetation label. Its coefficients are not plug-compatible with this project's dimensionless annual indices.[^3]

Jolly et al.'s phenology index combines minimum-temperature, vapor-pressure-deficit and photoperiod constraints multiplicatively and evaluates temporal greenness against observations. It is a phenology model, not a universal hot-forest survival test. The study does not license converting a monthly Tmin-style threshold into biological “growing season” at arbitrary temperatures, nor does it imply that cold dormant months make a seasonal forest ineligible year-round.[^4]

## Proposed bounded correction

**Immediate model-scope correction, without changing solved temperatures or inventing new physiological thresholds:** version the terrestrial empirical contract. Declare finite numeric annual-temperature applicability and distinguish a supported numerical zero from an unavailable estimate. Reusing the existing open (−16,52) support is defensible only as the domain of the current annual thermal proxy, explicitly **not** as plant survival limits or an empirically validated forest envelope. The label should communicate “existing heuristic applicable,” not “forest viable.” This would expose the current zero-temperature-term bypass without fitting a new cutoff to Verdant or Young.

Require that applicability through primary, biomass, forest growth, canopy/succession history, and renewable forest-resource production. If compatibility requires numeric zero sentinels, pair them with false support/availability flags and prevent all dependent records and biological bonuses from consuming them. Metadata must specify source variable, time aggregation, domain, unsupported policy and downstream relationship. Unknown/partial model declarations must fail validation; absent declarations retain explicit legacy interpretation.

Treat the current growing-month result as a warm/moist-month **descriptor**, not a biological prediction. Its producer is Python `biome_dynamics.py`, not native code. Preserve its math only under an explicit descriptive name and contract, or mark the biological growing-season estimate unavailable outside a separately justified declared model domain. **The primary proxy's (−16,52) interval does not automatically define biome, phenology, crop, fuel, or settlement applicability.** Do not simply impose a literature leaf-temperature number on monthly means. A new monthly activity model needs its own published parameterization and validation.

For stronger biological predictions, replace the annual additive production heuristic with a separately versioned seasonal, co-limited plant-functional-type model that includes heat inhibition, light, water, respiration, and persistent biomass. Evaluate active-season carbon gain and dormancy separately from thermal damage. In particular, do not require every month to be within a warm photosynthesis window: that would eliminate ordinary dormant boreal/deciduous forests. Conversely, an acceptable annual mean must not hide biologically unsupported hot-month claims (the Solstice artifact provides such a test family).

Leave Köppen classification, native seasonal coefficients, forcing nodes, monthly ledgers and climate temperatures unchanged. Retained empirical biome labels and water-alignment checks should remain discoverable with narrow scope; forest-cover reporting and all downstream biological displays must use the new availability contract. Soil organic pools or past biomass are not automatically zero merely because present production is unavailable; their separate heuristic/state assumptions need explicit treatment rather than guessed instantaneous sterilization.

The complete producer/consumer migration map is in [Terrestrial ecology dependency migration](terrestrial_ecology_dependency_migration.md). It includes the earlier biomass-dependent disturbance and richness estimates, species, neighboring fuel inputs, the separate agricultural curve and public availability displays. These interfaces remain under isolated development; the public pipeline is not yet migrated.

## Validation witnesses

- **Unmodified real integration:** reproduce Verdant 21 and Young 8 from shipped scenario configs through the public pipeline. Verify identical native certificate/temperatures before and after ecology enrichment and explicit unavailable biological estimates/records under the new declared proxy domain. Avoid changing temperature fields inside a solved certificate.
- **Independent formula witness:** use Verdant 21's nonthermal terms to pin the present .63292 additive result, then prove those terms cannot authorize biological output when thermal support is false. Mutate each downstream flag, positive scalar, forest record and succession record independently; zeroing primary alone must not make the test pass.
- **Domain boundaries and input types:** both existing proxy endpoints −16 and 52, neighboring representable floats, NaN/Inf, enormous integers, bool/string/missing annual input. Assert declared availability, not universal biological mortality.
- **Seasonality:** matched annual means with ordinary cold dormancy versus persistent extreme hot months; retain valid seasonal forests, distinguish unavailable annual proxy from a later supported seasonal model, and never borrow reef's every-month-positive-temperature rule.
- **Classification separation:** an extreme wet profile may continue to compute Af, while no forest-resource or mature-canopy claim is authorized solely by Af/native forest labels. Forest-map/summary availability must agree with cell and record flags.
- **Dependency/state replay:** prefilled stale primary/biomass/forest/history records must be rebuilt consistently; repeated enrichment is idempotent. Separate unknown metadata from absent legacy metadata. Preserve genuine old-model controls without converting every new-world fixture to legacy.
- **Cold control:** the existing cryogenic artifact demonstrates the symmetric additive bypass. A new annual-proxy support gate may mark it unavailable; a future seasonal model must independently justify any active-season or refuge claims rather than infer them from annual means.

## Sources

[^1]: Hylke E. Beck et al., “Present and future Köppen-Geiger climate classification maps at 1-km resolution,” *Scientific Data* 5, 180214 (2018), Table 2. [Publisher](https://www.nature.com/articles/sdata2018214); [NOAA-hosted article](https://repository.library.noaa.gov/view/noaa/24183/noaa_24183_DS1.pdf).

[^2]: Christopher E. Doughty et al., “Tropical forests are approaching critical temperature thresholds,” *Nature* 621, 105–111 (2023). [Publisher/DOI](https://doi.org/10.1038/s41586-023-06391-z); [author-institution abstract](https://researchonline.jcu.edu.au/80369/).

[^3]: Sibyll Schaphoff et al., “LPJmL4 – a dynamic global vegetation model with managed land – Part 1: Model description,” *Geoscientific Model Development* 11, 1343–1375 (2018), section 2.2, equations 28–34. [Article](https://gmd.copernicus.org/articles/11/1343/2018/); [full text](https://gmd.copernicus.org/articles/11/1343/2018/gmd-11-1343-2018.pdf).

[^4]: William M. Jolly, Ramakrishna Nemani and Steven W. Running, “A generalized, bioclimatic index to predict foliar phenology in response to climate,” *Global Change Biology* 11, 619–632 (2005). [Publisher/DOI](https://doi.org/10.1111/j.1365-2486.2005.00930.x); [FRAMES-hosted article](https://www.frames.gov/documents/catalog/spa/jolly_nemani_running_2005.pdf).
