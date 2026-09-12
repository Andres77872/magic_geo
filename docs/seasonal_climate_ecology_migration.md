# Seasonal climate: ecology diagnostic migration

Status: **native reef/wildfire branches and their independent validators are implemented and used by explicit version-2 generation.** The earlier reef, aquatic proxy support, standing-water ecosystem/wildfire and species habitat corrections remain in place. This note separates implemented model consistency from unresolved physical habitat/bleaching/ignition calibration. It complements the [native output contract](seasonal_climate_output_contract.md) and [vertical model research](seasonal_climate_vertical_model_research.md).

## 1. Existing dependency and exact legacy formulas

[`api.py`](../src/magic_geo/api.py) runs climate-energy enrichment in the physical foundation, then ecosystem dynamics, reefs, species ranges and wildfire disturbance. Only [`reef_diagnostics.py`](../src/magic_geo/reef_diagnostics.py) and [`wildfire_disturbance.py`](../src/magic_geo/wildfire_disturbance.py) directly consume `climate_energy_stress_index` for ecology. CSV, summary writers and validators also expose or check it.

Write `c(x)=max(0,min(1,x))`. The legacy post-hoc graybody diagnostic computes

```text
E = c(abs(Tannual - Tequilibrium)/28 K
      + abs(ASR + greenhouse_trapping - OLR)/(220 W m^-2)).
```

`Tequilibrium` and `greenhouse_trapping` come from the separately declared `posthoc_empirical_graybody_surface_diagnostic_v2` model. Thus `E` measures disagreement with an empirical diagnostic; it is neither ecological damage nor the numerical residual of a temperature-producing energy solve.

The current reef bleaching proxy is exactly

```text
Blegacy = c(0.44*c((Tannual - 29 C)/7 K)
            + 0.24*E
            + 0.16*c(seasonal_aridity_index)
            + 0.16*c(ocean_current_temperature_c/5 K)).
```

Let `S` be the existing annual-temperature suitability, `Sh` shallow-water suitability, `Sb` shelf bonus, `J` island support, `W` wave-window suitability, `F` fishery productivity, `D` sediment stress, and `Ireef=c(ice_thickness_m/60 m)`. The non-bleaching growth expression is

```text
N = 0.26*S + 0.25*Sh + Sb + 0.15*J + 0.10*W + 0.08*F
    - 0.22*D - 0.54*Ireef.
Glegacy = c(N - 0.16*Blegacy).
```

An energy-stress change from zero to one can therefore reduce unsaturated reef growth by `0.16*0.24=0.0384`; it can change the `G >= 0.46` membership decision.

For wildfire, let `Wfire`, `Ffuel`, `A`, `Dfire`, `Wal`, `Ssettle`, and `Bbreak` denote the already clamped spread-risk, fuel-continuity, aridity, disturbance-pressure, wind-alignment, settlement-score, and firebreak indices. Let `Ifire=c(ice_thickness_m/500 m)`. On non-water cells:

```text
R = 0.34*Wfire + 0.28*Ffuel + 0.16*A + 0.10*Dfire
    + 0.08*Wal + 0.08*Ssettle - 0.18*Bbreak - 0.18*Ifire.
IgnitionLegacy = c(R + 0.06*E).
```

Water-cell ignition is zero. The energy term can move a cell across the existing `0.28` ignition threshold. Missing stress currently defaults to zero in both consumers, so removing the field without an explicit branch silently changes ecology.

## 2. Implemented native-model branches

The shared [`climate_model_dispatch.py`](../src/magic_geo/climate_model_dispatch.py) requires known climate identifiers and exact upstream annual-energy enrichment metadata before selecting the native branch. It checks the dependency contract without repeating the physical audit owned by energy enrichment. Unknown/partial native envelopes fail before producer mutation. Legacy climate retains the preceding calculations. Published native models are `heuristic_coastal_reef_native_seasonal_v3` and `heuristic_wildfire_native_seasonal_v3`.

For native seasonal climate, remove the unsupported lightning contribution:

```text
WildfireNative = 0                         on water
WildfireNative = c(R)                      otherwise.
lightning_model = "not_modelled"
```

Do not renormalize the remaining weights or substitute temperature amplitude, orbital variability, or an energy residual. Existing fuel, aridity, wind and human-pressure inputs still define a **heuristic susceptibility**, not a calibrated probability of a lightning ignition. Generated disturbance histories need that scenario interpretation. Observational dry-lightning research uses precipitation and upper-air stability/moisture measurements; operational ignition estimates combine observed lightning density with fuel-dependent ignition efficiency. None of these are numerical energy-balance errors. [Rorig and Ferguson, 1999](https://research.fs.usda.gov/treesearch/5123), [Sopko, Latham and Grenfell, 2007](https://research.fs.usda.gov/treesearch/28599)

For reefs, retain actual-temperature suitability and the habitat gate from section 3, but retire the entire unsupported bleaching proxy in the native branch:

```text
ReefGrowthNative = H * c(N).
bleaching_model = "not_modelled_no_reference_climatology"
```

Native cells omit `reef_bleaching_risk_index`; reef-system records and summaries omit `mean_reef_bleaching_risk_index`. The model declares `bleaching_estimate_available=False`, and the Markdown summary explicitly reports the missing reference climatology/history. CSV leaves the old field blank; it does not export zero as an estimated absence of risk. Independent small validators and CLI/subsystem consumers enforce the version and omissions. This changes the ecological model intentionally; no claim is made that reef membership remains identical.

NOAA Coral Reef Watch accumulates temperature anomalies relative to an independent local maximum-monthly-mean climatology, with an exposure threshold and a rolling time window. A future branch could reproduce the declared method:

```text
HS(t) = max(Twater(t) - MMMreference, 0)
DHW(t) = integral from t-84 days to t of
         HS(s) * indicator(HS(s) >= 1 K) ds / (7 days).
```

The units are degree-Celsius weeks. The integrand retains the full hotspot when it meets the threshold; it is not `max(HS-1 K,0)`. Deriving `MMMreference` from the same twelve repeating monthly values would erase the required interannual anomaly rather than establish safety. Require an independently declared baseline and adequate temperature/exposure resolution before implementing this diagnostic. [NOAA Coral Reef Watch methodology](https://coralreefwatch.noaa.gov/product/5km/tutorial/crw10a_dhw_product.php)

Cold-water corals require separate treatment: NOAA's observed deep-water corals lack the symbiotic algae implicated in tropical bleaching. The present surface-climate proxy is not a deep-water temperature measurement. [NOAA Ocean Exploration](https://oceanexplorer.noaa.gov/ocean-fact/coral-water/)

## 3. Current reef thermal correction — implemented

The old additive growth expression produced eligible reefs despite zero thermal suitability. A favorable shallow island coast at `100 C` produced growth `0.7268`; at `-100 C`, `0.7972`. Both exceeded `0.46`.

`reef_diagnostics.py` now declares `reef_diagnostics_model.model = "heuristic_coastal_reef_v2"` and applies

```text
H = 1 if annual T is finite and 4 < Tannual < 39 C,
        and every supplied monthly mean is finite and inside the same interval;
    0 otherwise.
ReefGrowthCurrent = H * c(N - 0.16*Blegacy).
```

The monthly field, when present, must be a list of twelve numeric non-boolean values. Empty, malformed and nonfinite series are ineligible. Only an absent monthly field permits the annual-only compatibility path. The marine-water and neighboring-land prerequisites remain. Other reef diagnostics, including the legacy energy-stress contribution to bleaching, are unchanged.

The open `(4,39) C` bounds are **the existing empirical curve's positive support**, not newly fitted or universal species survival limits. NOAA describes cold-water corals around `4–12 C`, many shallow corals growing best around `23–29 C`, and tolerance near `40 C` only for brief exposure. Those observations support a bounded thermal prerequisite, but do not establish this particular model's exact thresholds or turn monthly surface means into habitat-depth measurements. [NOAA coral distribution guidance](https://oceanservice.noaa.gov/education/tutorial_corals/coral05_distribution.html)

[`test_reef_thermal_habitat.py`](../tests/test_reef_thermal_habitat.py) covers cold/hot vetoes despite strong nonthermal bonuses, valid annual means hiding an invalid season, supported cold/warm seasonal habitats, invalid monthly inputs, annual-only compatibility, unchanged legacy stress effects, and stale-membership removal. The corresponding preexisting test now separately verifies the zero unsupported baseline and unchanged supported thermal/nonthermal weights. The focused two-module run passed **99 tests plus 176 subtests**. Independent subsystem and public CLI validators also enforce exact model metadata and thermal eligibility, with absent-model legacy compatibility; their combined thermal/subsystem/CLI regression run passed **150 tests plus 395 subtests**. These counts do not assert that the native ecology migration is implemented.

## 4. Native migration verification

The five-module native ecology run passed **203 tests in 10.58 seconds**. New [`test_native_seasonal_ecology.py`](../tests/test_native_seasonal_ecology.py) covers the exact removed weights without renormalization, bleaching omissions, legacy behavior, thermal gates, standing-water barriers and history rebuilding, unknown/partial input refusal before mutation, and invariant output when solver residual/work metadata changes. A genuine 128-cell native witness preserves all retained model/budget/temperature objects. The actual public full-world and geo-only generation paths also succeed; the full CLI consistency gate returns `OK`, and generic geography validation reports 151 checks with no errors or warnings. These are model-consistency results, not new ecological calibration.

The following implemented checks remain regression requirements. The future DHW portion of item 4 remains conditional on a new physical data model:

1. Changing solver residuals, iteration counts or tolerances while keeping the accepted ecological climate inputs fixed must leave ecological outputs unchanged.
2. Explicit legacy fixtures retain the `0.24*E` reef and `0.06*E` wildfire contributions; native fixtures do not read `E` even if a stale legacy field remains.
3. Unknown/inconsistent native model declarations cannot invoke a missing-field-to-zero or legacy fallback.
4. Missing reference climatology means unavailable bleaching diagnosis; it must not become zero estimated risk. A future DHW test must distinguish `HS*indicator(HS>=1)` from `max(HS-1,0)` and test expiration from the rolling window.
5. Reefs outside the declared thermal support remain ineligible independently of shelf, wave, island and fishery bonuses. Cold-water classifications must not claim tropical bleaching physiology.
6. Replay cell, record and summary fields under their declared versions, including exports and re-enrichment. Updating ecological weights or names must not rewrite native physical coefficients or budgets.

## 5. Aquatic proxy-support correction — implemented

[`ecosystem_dynamics.py`](../src/magic_geo/ecosystem_dynamics.py) has the same additive-baseline issue. Its existing response supports are

```text
SP(T) = c(1 - abs(T-18 C)/34 K), positive only for -16 < T < 52 C.
SF(T) = c(1 - abs(T-12 C)/32 K), positive only for -20 < T < 44 C.
Paquatic = c(0.12 + shelf_bonus + 0.24*SP + 0.22*nutrient + 0.12*current).
Fishery = c(shelf + 0.34*P + 0.20*runoff_nutrient + 0.14*current_mixing + 0.12*SF).
```

Before the correction, at `temperature_c=100 C`, a shelf cell with no additional nutrient/current inputs received `P=0.32`, `Fishery=0.4088`, and an actual renewable fishery record because the threshold is `0.35`. Its computed sustainable yield was `0.292928`. This promoted a baseline into a resource even after its own thermal response had no support.

The published `temperature_c` is currently a **surface-air climate descriptor**. The bounded correction limits this empirical proxy's applicability; it does not diagnose universal biological extinction or measure water at depth. On aquatic cells:

```text
DP = finite(Tannual) and -16 < Tannual < 52 C
DF = finite(Tannual) and -20 < Tannual < 44 C
DFestimate = DF and DP
Pcorrected = Pexisting              for terrestrial cells or supported aquatic inputs
Pcorrected = 0                      for aquatic inputs with DP=false
FisheryCorrected = FisheryExisting(Pcorrected) if water type qualifies and DFestimate=true,
                    0 otherwise.
```

The composed dependency is necessary: at `-18 C`, the fishery's own climate curve has support but primary productivity does not. Its sentinel zero cannot be consumed as a known physical zero. Conversely, a valid primary estimate of zero at a supported temperature remains a usable numeric input to the fishery formula. This is an input-dependency rule, not an additional species temperature limit.

The producer exports `aquatic_climate_proxy_applicable`, `aquatic_primary_climate_supported`, `fishery_climate_supported` and `fishery_productivity_supported` as booleans. This support contract was introduced as `ecosystem_dynamics_model.model="heuristic_ecosystem_climate_support_v2"` and is retained by the current `heuristic_ecosystem_climate_support_v3` model, whose additional standing-water policy is described in section 6. Metadata declares the source, exclusive limits, composed dependency, monthly-input policy, and zero/record semantics. Unsupported estimates are exported as finite numeric zero for the current downstream numeric contract, with false support flags; unsupported fisheries produce no renewable record. Invalid, missing, boolean, nonnumeric or nonfinite annual temperatures cannot acquire support by numeric coercion.

Aquatic applicability is `is_water OR is_lake OR water_body_type in {ocean, continental_shelf, inland_sea, fresh_lake}`. This includes fresh lakes with `is_water=false` and wet saline lakes through `is_lake=true`. The native hydrology can label a **dry** geologic depression `saline_basin` without `is_lake`; that case is not silently reclassified as standing water. Saline lakes remain outside the existing generic fishery water-type list. The support-only v2 guard preserved the within-support branch selection and weights; v3 also corrects the lake branch selection without changing those weights. Neither version imposes the reef's all-month persistence gate on annual aquatic production: seasonal production, dormancy, migration and under-ice refuges require a different model.

Do not add a `0 C` surface-air cutoff or assume that sea ice eliminates production. Chief-scientist observations from ICESCAPE found a large phytoplankton bloom developing under more than a meter of sea ice, supported by transmitted light. [Arrigo, ICESCAPE 2011 cruise report, pages 1–3](https://seabass.gsfc.nasa.gov/archive/USC/BENITEZ_NELSON/ICESCAPE2011/documents/Icescape_2011_cruise_report.pdf) USGS lake-profile observations show that water under ice can remain near `0–4 C` while air conditions differ, and that deep summer water differs from surface water. [Perrey and Corbett, 1956](https://www.usgs.gov/publications/hydrology-indiana-lakes) Fish tolerances also vary by species and life stage; observations and experiments summarized by the original investigators do not justify a universal fish cutoff at the code's `44 C`. [Dahlke et al., 2020, authors' research account](https://www.awi.de/en/about-us/service/press/single-view/steigende-wassertemperaturen-bedrohen-vermehrung-vieler-fischarten.html)

The implemented guard is an interim consistency repair. A physical aquatic model needs identified water temperature at the relevant depth/season, liquid-water/ice state, light, nutrients, oxygen and a specified biological response. A new native marine surface column improves the temperature source but does not supply lake or deep-water profiles. Numeric positive support does not prove real habitat suitability, and unsupported proxy inputs do not prove absence of life below the surface.

[`test_aquatic_climate_support.py`](../tests/test_aquatic_climate_support.py) verifies exact-zero unsupported estimates/no fishery records, nonthermal bonuses unable to bypass support, supported cold/temperate/warm formulas, freshwater/saline lake classification, malformed annual inputs, cold seasonal controls, separate own-climate and composed-support flags, known physical zero inputs, and re-enrichment/record/summary consistency. The initial aquatic/biosphere run passed **59 tests**, and the initial independent subsystem/public CLI validation of the four flags and composed dependency passed **51 new tests**. The v3 extension's newer evidence is listed below. Direct and downstream follow-up modules include `test_validate_cli_biosphere_resources.py`, `test_geo_validation_subsystems.py`, `test_smoke_coast_ocean.py`, `test_smoke_hydrology.py`, `test_smoke_resources.py`, and `test_maturation_timestep.py`.

## 6. Standing-water ecosystem classification — implemented v3

The native `is_water` mask describes marine water; standing lakes can have `is_water=false` and `is_lake=true`. Before this correction, a fresh lake at `18 C` with `soil_moisture_index=1`, zero fertility, annual precipitation `600 mm`, PET `1000 mm`, nine growing months and aridity `0.2` received terrestrial primary productivity `0.679`, biomass `0.51308`, wildfire spread risk `0.156878`, and a terrestrial succession history. Those outputs resulted from choosing the land branch, not from a modeled lake vegetation or disturbance process.

The v3 producer factors the same aquatic selector used by the support flags and declares

```text
aquatic_ecology_policy = "shared_aquatic_selector_for_primary_and_terrestrial_exclusion"
```

All selected aquatic cells now use the existing aquatic primary-productivity equation when supported. Its bonus remains `0.20` for shelf water, `0.12` for fresh lakes/inland seas, and `0.04` for other aquatic cells, including standing saline lakes. Within-support marine and terrestrial equations and their coefficients are unchanged. Aquatic cells export zero `vegetation_biomass_index`, `forest_growth_index` and `wildfire_spread_risk_index`; their stage is `aquatic_primary_productivity`. They produce no terrestrial succession histories or forest renewable records, even with a stale forest biome. The existing renewable resource water-dependency bonus of `0.30` applies to lakes as well as marine water. Re-enrichment replaces stale terrestrial records after inundation. Dry saline basins retain land classification and formulas.

This is a consistent distinction between standing water and terrestrial canopy/fuel in the existing coarse cell model. It does not rule out aquatic plants or emergent shoreline vegetation, estimate aquatic disturbance or species composition, or transform air temperature into water temperature. General ecosystem disturbance and species-richness heuristics are not zeroed or represented as solved aquatic processes.

[`test_standing_lake_ecology.py`](../tests/test_standing_lake_ecology.py) adds 14 cases covering fresh/saline standing lakes, each selector path, independent aquatic formula reconstruction, stale forest/fire inputs, dry saline controls, resource water dependence, marine-mask independence, inundation and idempotence. The combined standing-lake/aquatic-support/biosphere run passed **73 tests**. The six existing freshwater numeric references were updated to the existing aquatic lake formula; the marine and land controls retain their original values. Independent subsystem and public CLI validators strictly distinguish known v2 support-only metadata from v3 terrestrial exclusions; **68 validation tests** passed, including actual CLI lake-biomass tampering and legacy/current metadata cases. Missing model metadata retains the separate legacy validation path; unknown or malformed present metadata fails.

The later wildfire and species consumers had their own habitat predicates. Corrected ecosystem numeric zeros alone were insufficient to enforce their habitat distinctions. The wildfire and bounded species habitat corrections are implemented below; other guilds retain their declared legacy scope.

## 7. Standing-water wildfire exclusion — implemented

Before the downstream correction, after the v3 ecosystem producer a fresh lake at `18 C`, runoff `900 mm/y`, aridity `1`, and eastward wind `1`, next to vegetated land, had zero ecosystem biomass/fire risk but received later wildfire fuel `0.372`, ignition `0.335813`, firebreak `0.11304`, a `seasonal_surface_fire` regime and an actual lake-containing spread history. Aquatic primary productivity and neighbor fuel bypassed the terrestrial distinction in `wildfire_disturbance.py`.

That module now imports the exact shared aquatic selector from the ecosystem module. Every selected aquatic cell has fuel and ignition zero, firebreak one, regime `non_burnable_water`, and no wildfire history membership. Both the source and target of a spread edge must be terrestrial. A neighbor's stale positive biomass cannot count as terrestrial fuel if that neighbor is aquatic, while the water-neighbor firebreak fraction includes standing lakes. Dry saline basins remain land. Metadata declares:

```text
wildfire_disturbance_model = {
  model: "heuristic_wildfire_aquatic_exclusion_v2",
  aquatic_selector: "is_water_or_is_lake_or_fishery_water_body_type",
  aquatic_fire_policy: "zero_fuel_ignition_and_spread_non_burnable_no_history",
  neighbor_fuel_policy: "terrestrial_biomass_neighbors",
  ignition_model: "legacy_energy_aridity_fuel_wind_settlement_proxy_v1"
}
```

All other empirical coefficients, thresholds and the legacy `0.06*E` ignition contribution are unchanged. This correction restricts the existing terrestrial surface-fire graph; it does not model aquatic combustion, emergent vegetation, windborne embers crossing open water, or a new lightning process. In particular, declaring a water cell nonburnable does not assert that real fires cannot spot across a lake; spotting is absent from this edge-neighbor model.

[`test_standing_lake_wildfire.py`](../tests/test_standing_lake_wildfire.py) adds 17 cases. A three-cell graph burns through a dry saline bridge from cell 0 to 1 to 2; inundating the bridge leaves only cell 0 burned, with the far shore below independent ignition threshold. Tests also cover wet fresh/saline selectors, both spread endpoints with stale diagnostics, neighbor fuel/firebreak terms, the actual ecosystem-to-wildfire regression, exact land coefficients and legacy energy contribution, marine controls, inundation cleanup, metadata and idempotence. The combined wildfire/lake-ecology/aquatic-support/biosphere run passed **90 tests**. No preexisting wildfire fixture required adjustment.

[`wildfire_aquatic_validation.py`](../src/magic_geo/wildfire_aquatic_validation.py) independently recomputes the aquatic classification without importing producer constants or helpers. Both subsystem and public CLI wildfire checks require the exact known five-field metadata; only an absent declaration retains legacy structural validation. The new version enforces aquatic fuel/ignition zero, firebreak one, the nonburnable regime and empty inverse history IDs. It checks the ignition cell, affected-cell list, newly burned lists and active fronts independently, including a water front omitted from the history's affected list. There are no explicit spread-edge, severity or burned-fraction fields in this version, and the validation does not invent them or require unrelated aquatic wind/general disturbance to be zero. [`test_wildfire_aquatic_validation.py`](../tests/test_wildfire_aquatic_validation.py) and one existing CLI wildfire range-check case passed **60 tests plus 8 subtests**, including current/legacy public CLI baselines, malformed/unknown metadata, and lake ignition/history/front tampering. Broader integration remains separately coordinated.

## 8. Species habitat and input-support gates — implemented v2

Before correction, `species_ranges.py` used an incomplete terrestrial gate and marine-only water fraction. An isolated fresh lake at `18 C`, runoff `900 mm/y`, soil moisture `1` and aridity `0.45` received a `grassland_grazer` range with suitability `0.62228` and reported water fraction `0`. It also received a `marine_fish` range at `0.477677`; the freshwater range scored `0.681983`.

The producer now declares `species_ranges_model.model="heuristic_species_habitat_support_v2"`. Its five terrestrial guilds—`canopy_tree`, `grassland_grazer`, `desert_specialist`, `alpine_tundra_specialist`, and `large_predator`—use `not shared_aquatic_selector`. The coefficients within terrestrial habitat are unchanged. This excludes standing fresh/saline lakes and prevents a terrestrial range from connecting through a lake. Dry saline basins remain land. Rivers remain mixed land/channel cells: NOAA distinguishes river channels, vegetated riparian banks and intermittently flooded floodplains, with distinct habitat and life-stage roles. This supports the coarse distinction without proving cell-scale habitat composition. [NOAA Fisheries river habitat and restoration](https://www.fisheries.noaa.gov/national/habitat-conservation/river-habitat)

Native `ocean.cpp::label_marine_water_bodies` assigns `water_body=3` to smaller connected components of the marine mask; `schema_names.hpp` names this `inland_sea`. The corrected fish taxonomy therefore uses:

```text
MarineHabitat = water_body_type in {ocean, continental_shelf, inland_sea}
RiverHabitat = is_river AND NOT shared_aquatic_selector
               AND water_body_type != saline_basin
FreshwaterHabitat = water_body_type == fresh_lake OR RiverHabitat
```

An unclassified lake or saline basin does not establish a fresh or marine resident-fish habitat. False eligibility is an unsupported model classification, not evidence of fish absence. Moving `inland_sea` from the freshwater bonus to the marine bonus intentionally changes its fish scores. These coarse categories do not represent universal salinity tolerances: NOAA follows Atlantic salmon and other diadromous fish between rivers and the sea. Migratory guilds would need connected habitat and life-stage inputs. [NOAA Northeast Fisheries Science Center, Atlantic salmon research](https://www.fisheries.noaa.gov/new-england-mid-atlantic/endangered-species-conservation/atlantic-salmon-ecosystems-research)

Standing-water fish scores require exact-true upstream `aquatic_primary_climate_supported` and `fishery_productivity_supported`, finite primary/fishery indices in `[0,1]`, and annual climate in the existing upstream composed open `(-16,44) C` support. Thus an unsupported zero cannot become a known primary/fishery input, while a valid numeric zero remains usable. Missing support flags do not authorize a new v2 standing-water score.

Each fish score also requires positive support from its own existing temperature window: freshwater uses center `14 C`, half-width `24 K`, hence open `(-10,38) C`; marine uses center `13 C`, half-width `24 K`, hence open `(-11,37) C`. The freshwater requirement also applies to river scores. Without it, habitat/channel/productivity bonuses could still produce river-fish ranges at `-100 C` or `100 C` after the temperature term became zero. These are declared annual surface-air proxy applicability limits, not newly fitted water-temperature or universal survival thresholds. Outside them, the score is unavailable and cannot supply a range; the model does not infer absence of real fish or resolve refuges at depth.

The separate river score retains its `0.22` river bonus, channel width/depth, primary-productivity and temperature terms within the freshwater curve's support, while omitting `0.30*fishery_productivity_index` regardless of a stale upstream number. The current resource model does not estimate river fisheries. A usable primary index is still required. Metadata identifies `habitat_evidence.mean_fishery_productivity_index` as an upstream numeric diagnostic; that aggregate does not mean a river resource estimate was consumed.

Six per-cell fields expose these distinctions:

| Field | Meaning |
| --- | --- |
| `species_terrestrial_habitat_eligible` | Habitat for the five terrestrial guilds is available. |
| `species_freshwater_habitat_eligible` | A fresh lake or eligible terrestrial river is identified. |
| `species_marine_habitat_eligible` | A known marine water type is identified. |
| `species_freshwater_fish_score_supported` | Freshwater habitat and the branch's required inputs are usable. |
| `species_marine_fish_score_supported` | Marine habitat and standing-water inputs are usable. |
| `species_freshwater_fishery_input_mode` | `standing_water_required`, `river_inapplicable_omitted`, or `not_applicable`. |

Unsupported fish scores remain numeric zero with false score-support flags, producing neither fish range membership nor a dominant fish guild. Range membership, dominant guild, guild richness, summaries and water habitat evidence are recomputed. The range threshold `0.46` and dominant floor `0.25` remain unchanged. Invalid annual temperature is rejected before mutation because every range exports a climate envelope. A present primary/fishery index must also be finite numeric and non-boolean before mutation; absent indices retain the legacy diagnostics' zero default while remaining unavailable to the new fish score. Finite out-of-range indices retain the legacy clamped diagnostic behavior but cannot support the new fish score. The explicit `productivity_input_policy` distinguishes malformed inputs from finite unsupported sentinels.

Wetland amphibians, mobile coastal birds and reef builders retain explicit legacy scores. The amphibian's old inland-sea/river bonus is kept separately; correcting resident-fish taxonomy does not certify amphibian salinity suitability. Reef-builder eligibility still needs an independent valid upstream reef habitat/membership check. Endemism, composition confidence and upstream biome diagnostics also retain their separate limitations. This correction does not implement population dynamics, dispersal, migration or aquatic depth temperatures. The later native reef/wildfire branches in section 2 do not resolve those separate gaps.

[`species_habitat_validation.py`](../src/magic_geo/species_habitat_validation.py) independently checks exact versioned metadata, raw habitat and input support, all six cell declarations, dominant guilds, every range member and shared-water evidence. Both subsystem and public CLI species blocks invoke it. An absent model retains legacy structural validation; an unknown or malformed present model fails. Its stated scope is prerequisite validation, not a complete independent replay of every guild coefficient.

A public CLI probe additionally found that `primary_productivity_index: null` raised an unhandled `TypeError` in an earlier ecosystem aggregate, before the new species check could report the bad input. An initial CLI preflight now rejects malformed present primary/fishery values before eager consumers. It preserves the generic `ecosystem dynamic cell fields invalid` diagnostic and adds the cell and field; it does not coerce values, substitute zeros or mutate the payload. Nonfinite and oversized JSON numbers retain the strict loader's existing error path. The final focused species-validator module passed **157 tests in 17.38 seconds**, including 21 public CLI preflight/loader regressions.

CSV export appends the four ecosystem support flags and all six species fields after the original 397 columns. Existing positions remain stable. A false flag, a supported numeric zero, and an absent legacy declaration (empty CSV field) stay distinguishable. The UI exposes the new flags as discoverable layers and explains their model scope. Focused CSV and existing export tests passed **4 tests in 0.62 seconds** (`runs/review-ecology-csv-support-tests.xml`); all **14 JavaScript regressions** passed.

The final species/CLI/export/generation/writer/UI integration passed **434 tests and 491 subtests in 208.96 seconds** (`runs/review-species-habitat-integration-fixed-tests.xml`). Two prior mutation-fixture expectations were expanded to assert their newly correct species cascades when changing marine or river habitat; no production tolerances were relaxed. The [main coherence report](simulation_coherence_research.md) records the exact scope and preserves the earlier full-suite/scientific-matrix results separately. Numerical model support and graph consistency do not establish biological calibration.
