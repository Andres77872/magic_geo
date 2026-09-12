# Prescribed natural ecosystem and fire activity

Fresh Python enrichment uses ecosystem v5, species v4 and climate-matched fire
v6/v7. These describe a prescribed natural scenario: human activity is outside
the ecosystem/fire model. A cell's prospective `settlement_score` does not
establish occupation, disturbance, ignition or suppression. The score remains
available to the separate historical access and settlement diagnostics.

## Change and preserved meaning

Ecosystem v5 omits the old `0.16 * settlement_score` disturbance term. Fire v6/v7
omit the direct `0.08 * settlement_score` ignition term. Remaining coefficients
are unchanged and are not renormalized. Changed disturbance propagates through
the existing forest, recovery, succession, species and fire equations in API
order. Final fire histories do not feed back into their earlier ecosystem input.

The earlier `fire_frequency_index` is a dimensionless climate/vegetation
susceptibility descriptor. It has no calibrated events-per-year interpretation.
The later ignition and spread indices likewise do not establish lightning,
observed fires, fuel consumption, physical containment or return intervals.
Native-seasonal fire v7 retains the existing exclusion of legacy energy stress;
explicit legacy-climate fire v6 retains that historical diagnostic input.

Separating human fire activity from environmental susceptibility follows the
architectural distinction explored by [WHAM (2024)](https://gmd.copernicus.org/articles/17/3993/2024/gmd-17-3993-2024.html)
and the [INFERNO fire-model work (2021)](https://gmd.copernicus.org/articles/14/6515/2021/index.html).
Those studies do not calibrate these local coefficients or validate the generated
world. The concrete defect and actual retained full/geo differences are recorded
in [the settlement/activity audit](../runs/settlement-activity-dependency-review/README.md).

## Matched stage contracts

| Stage | Fresh model | Required ecological parent |
|---|---|---|
| Ecosystem | `heuristic_ecosystem_climate_support_v5` | explicit physical descriptors |
| Species | `heuristic_species_parent_support_v4` | ecosystem v5 and natural habitat sources |
| Legacy-climate fire | `heuristic_wildfire_prescribed_natural_parent_availability_v6` | ecosystem v5 and legacy climate |
| Native-seasonal fire | `heuristic_wildfire_native_seasonal_prescribed_natural_parent_availability_v7` | ecosystem v5 and audited native climate |
| Deposits | `causal_geologic_resource_deposit_diagnostics_v4` | ecosystem v5 |
| Commodities | `causal_resource_commodity_occurrences_with_parent_support_v2` | deposits v4, ecosystem v5, explicit sedimentary sources |
| Full-world checks | `causal_upstream_evidence_worldbuilding_realism_checks_v3` | deposits v4, ecosystem v5, complete human source collections |

Deposits and commodities retain their material, access, reserve and fishery
equations. Commodity evidence is independently matched to its selected source,
including the volcanic descriptor, unique nonnegative referenced system ID and
four sedimentary potentials. Selection preserves the existing confidence floor
of -1 and last-record tie rule. This validates source evidence; it does not
establish a geochemical transport or calibrated reserve model.

Full generation completes water and human transport/port diagnostics before the
shared ecosystem → reef → species → fire → deposits → ore → sedimentary systems
→ petroleum → commodities sequence. Land use and frontiers precede the five
worldbuilding checks and later human histories. Geography-only generation omits
human stages and the worldbuilding stage. A full summary-only request still
supplies all cells to enrichment and removes cells only from the final response.

## Missing inputs and historical replay

New stages reject missing consumed physical descriptors, malformed types,
incomplete own declarations and mismatched parent versions before publication.
Species additionally requires explicit wetland, reef and aquifer collections,
unique natural-record IDs and reciprocal cell membership/neighbor links. Explicit
empty source collections are meaningful; absent collections do not mean an empty
completed stage. Full-world checks v3 require nonempty cells and explicit
settlements, routes, regions and borders, each of which may be an empty list.

Existing support policies remain distinct from missing-source validation.
Ecosystem's invalid/missing annual temperature remains an unsupported proxy;
species retains its own finite annual-temperature prerequisite. A false support
flag with numeric zero is unavailable, while a true flag can accompany a valid
zero. Range absence, unmodelled fire fronts and omitted fishery records retain
their separate availability meanings. This does not impose a universal survival
temperature on biomes, population, crops or standing fuel.

Exact ecosystem v4/species v3/fire v4-v5/deposit v3/commodity v1/worldbuilding v2
declarations retain their established replay behavior. Known older ecosystem
producer promotions and the explicit worldbuilding v1 exception remain available.
Removing or changing a model name cannot relabel existing outputs as a fresh
contract. A deliberate archive migration must audit the old world, clear every
owned value/record/counter for the changed stages, then rebuild the complete
dependent tail. Public validation rejects partial or mixed families.

## Evidence and limits

Retained 128-cell full/geo replays and two fresh API generations pass their
scope-appropriate CLI validators. Ecosystem, species and fire owned outputs are
exactly equal across the same-input full/geo pair. All unowned outputs, native
climate certificates, 119 deposit records and 196 commodity records match each
scope's baseline. Full and geo resource access are not asserted equal: their
optional human access inputs differ.

CSV, Parquet, JSON, summary text and inspector availability are checked on actual
old/new worlds. Serialized zero/false values stay intact; display support rules
mask unavailable estimates and retain supported zeros. Live browser interaction
was not revalidated in this migration; automated data/JavaScript checks are the
UI evidence. Native seasonal ice physics remains separate ongoing work.
