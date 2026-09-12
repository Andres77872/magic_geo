# Downstream availability migration design

The subsequent [prescribed natural activity migration](prescribed_natural_activity_migration.md)
advances fresh generation to ecosystem v5/species v4/fire v6-v7/deposit v4/
commodity v2/worldbuilding v3. The v4-era design and adoption record below remain
historical evidence; their declared contracts are retained for replay.

Adoption status, 2026-09-10: the reviewed ecosystem-v4 parent availability,
species-v3, climate-matched wildfire-v4/v5, resource-deposit-v3/commodity-v1,
and worldbuilding-v2 resource-context changes are now in the main Python
pipeline. Their independent validators, complete-output version checks,
CSV/summary output, and debug display availability handling were adopted
together. The existing API stage order and native climate certificates are
unchanged. Exact historical contracts remain validation/replay paths; a fresh
worldbuilding stage chooses v2, while an explicitly retained own-v1 declaration
keeps its historical meaning.

The [adoption evidence](../runs/ecology-parent-support-adoption/README.md)
records the exact 70-file overlay and baseline/candidate hashes. The design
inventory and isolated witnesses below describe the pre-adoption problem and
the resulting contract decisions; their original line numbers are historical.
The independent agriculture migration has since been adopted; see
[its own contract review](agricultural_availability_review.md). The agriculture
inventory below records the original v1 problem and proposed v2 decisions.
Native soil, fertility, population and settlement applicability remain separate
work. This ecology adoption does not introduce a universal biological temperature limit, a population or
fuel-pool model, or the natural groundwater prototypes.

## Actual order and the hidden dependency

`src/magic_geo/api.py:205` builds physical, soil, biome and water diagnostics.
`_enrich_ecosystems_and_resources` at line 243 then executes ecosystem → reef →
species → wildfire → resource deposits. Full worlds additionally run land-use
at line 285, followed by frontiers/worldbuilding and human histories. Geo-only
worlds omit the land-use/human outputs. Full-world native settlement and route
state already exists before these Python ecology stages.

Within `ecosystem_dynamics.py:233`, the dependency is:

```
annual air + water/soil descriptors → primary → biomass
biomass + earlier fire/aridity/wind → ecosystem wildfire risk → disturbance
primary + biomass + disturbance → forest → succession/forest resource
primary + biomass + ecotone + temperature + moisture → richness
richness/primary/biomass/forest/disturbance → species scores/confidence
primary/biomass/ecosystem wildfire/disturbance + neighboring biomass → final fire
```

The isolated patch gates the first biological chain but deliberately retains
the old richness, ecosystem wildfire-risk and disturbance numbers. The last
two are not independent climate observations: `_disturbance_pressure` at line
104 uses biomass with weight .22 in wildfire risk, then risk with weight .42 in
disturbance. Forest, succession, renewable disturbance/yield, species scores,
endemism, confidence, conservation stress and final fire all consume these.
Availability cannot first appear only in `wildfire_disturbance.py` without
leaving earlier consumers exposed.

There is currently no dynamic fire→ecosystem feedback: ecosystem reads
`fire_frequency_index` from `biome_dynamics.py:161`, not the later simulated
wildfire histories. Keep that distinction. Do not rerun ecosystem from final
fire fields or species from their own ranges; that would introduce feedback
and alter the current acyclic static diagnostic model.

## Independent read-only witnesses after the isolated patch

`/tmp/terrestrial-downstream-design-probe.py` loads the frozen ecosystem module
by absolute importlib path, enriches copies of actual archived solved cells,
then evaluates the unchanged current downstream functions. It changes neither
source tree nor native certificate. Results:

| Cell | Annual C | Primary available | Richness | Canopy score | Alpine score | Composition confidence | Agriculture |
|---|---:|---|---:|---:|---:|---:|---:|
| Verdant 21 | 73.7713 | false | .135800 | .318524 | .205960 | .492914 | .510832 |
| Young 8 | 63.1827 | false | .163700 | .315021 | .214303 | .481344 | .564379 |
| Cryogenic 0 | -53.9266 | false | .042128 | .007722 | .692478 | .417473 | .061396 |

The range threshold is .46, so the cold cell still qualifies for the alpine
range; the two hot canopy scores do not qualify but remain positive resident
suitability diagnostics. The point is unavailable consumed inputs, not proof
that cold alpine life cannot exist. The same probe with no neighbors labels
the hot cells `sparse_fuel` from fuel .059816/.065133: false primary availability
must not become a claim that standing or dead fuel is scarce. Ordinary
Earthlike forest and marine controls are retained in the JSON probe output.

## Model contracts and minimal extensions

### Ecosystem/richness and earlier disturbance

Current metadata is `ecosystem_dynamics_model.model =
heuristic_ecosystem_climate_support_v3`; the frozen patch proposes v4. Before
integration, negotiate an extension of that unreleased contract or a separate
new version, rather than silently adding semantics to an already accepted
dictionary. Add explicit applicability for `species_richness_index`,
`wildfire_spread_risk_index` and `ecosystem_disturbance_pressure_index` with
corresponding supported counts. The policy is availability of the current
input-dependent proxy, not observed richness, fire or ecosystem damage.

Richness has no separate calibrated biological envelope: its current thermal
term is the same open(-16,52) annual-air proxy. Its inputs require supported
primary and biomass where applicable; aquatic biomass is an explicit structural
zero, not a missing terrestrial estimate. Thus do not mechanically AND the
new biomass flag for aquatic cells. On terrestrial cells, unavailable biomass
makes the ecosystem wildfire proxy and hence disturbance unavailable. Preserve
the independent aquatic zero-risk rule and aquatic disturbance's remaining
declared descriptors. Keep zero sentinels only with false flags, not as known
inputs to forest, succession, yield or confidence. Supported numerical zero
still propagates as valid input.

No bound from this contract applies to biome classification, growing-season
phenology, retained soil organic matter, existing standing/dead biomass, crops,
settlements or global habitability. The earlier `fire_frequency_index` is still
an empirical warm/moist/aridity descriptor and requires its own scope statement;
it is not an observed fire rate or an independent fuel pool.

### Species: distinguish habitat, own proxy support and parent availability

Current `species_ranges_model` is `heuristic_species_habitat_support_v2`
(`species_ranges.py:371`, independent mirror `species_habitat_validation.py:22`).
It currently versions five terrestrial habitat exclusions and fish support,
while explicitly retaining three legacy guild score families. Six cell fields
separate terrestrial/freshwater/marine habitat, two fish-score support flags and
river fishery input mode. Do not reinterpret habitat flags as thermal support.

Exact score-parent map (`_guild_scores`, line 162):

| Guild | Consumed biological estimates | Existing own annual-air thermal term |
|---|---|---|
| canopy_tree | primary, biomass, forest, disturbance | triangle center18/halfwidth24: open(-6,42) |
| grassland_grazer | primary, richness, biomass, disturbance | same open(-6,42) |
| desert_specialist | richness | none; do not invent a temperature interval |
| alpine_tundra_specialist | richness | clamp((8-T)/22): positive T<8, no finite lower bound |
| large_predator | richness, biomass, primary, disturbance | none |
| wetland_amphibian | richness | triangle center25/halfwidth14: open(11,39) |
| freshwater_fish | primary, standing fishery when applicable | existing declared open(-10,38) |
| marine_fish | primary, fishery | existing declared open(-11,37) |
| reef_builder | reef growth, fishery | warm triangle open(11,39) |
| mangrove_coastal_bird | richness, disturbance | warm triangle open(11,39) |

The table reports equations, not recommended biological survival ranges.
Applying positive own thermal support as a prerequisite is defensible only as
declared applicability of each existing score; do not make desert/predator
acquire a guessed thermal curve or give alpine a fabricated lower bound. In
particular, annual-primary unavailability at -54 C makes the current alpine
score unsupported through richness, not physically impossible.

Proposed new species version: retain the three habitat flags and river mode;
extend exact per-guild score support to all ten guilds (eight added booleans,
using the existing two fish names), and explicitly declare own-window and
parent-input requirements. Rivers still omit the standing fishery term, but
must require available primary rather than just a finite numeric sentinel.
Standing fish keep their present primary+derived-fishery prerequisites. Do not
leave reef_builder consuming unsupported fishery zero or wetland/mobile guilds
consuming unsupported richness under an “unmigrated” escape clause once the
parent producer is migrated. This is dependency propagation, not a new wetland
or mobile-species survival model; separate habitat improvements can remain out
of scope.

`_cell_confidence` (line324) consumes primary, richness, disturbance and biome
confidence; `_cell_endemism` (line296) consumes disturbance plus reef/wetland
descriptors. All records unconditionally export mean primary/richness,
confidence, disturbance and habitat evidence, and conservation stress consumes
confidence/disturbance. Add applicability to these derived values as well.
For new-version records, either require every actually consumed input or carry
explicit unavailable evidence fields with support flags; do not leave an
unavailable zero inside a supposedly verified numeric mean. The smaller initial
contract is to require the common record inputs for record emission, with a
clear “record unavailable” reason distinct from lack of habitat. Preserve
supported guild scores separately if a common record descriptor is unavailable.

Dominant guild, max score, guild-richness count and connected components must
use only supported scores. Publish supported/applicable guild counts and an
explicit complete/partial/unavailable composition status. `none` with zero
supported guilds means unavailable, not no species. Existing summaries must
declare their available subset and count unsupported cells. Range record IDs,
per-cell inverse links, guild/habitat counts and stress counters are rebuilt
after filtering, never retained from stale output. No coefficient or .46 range
threshold change is necessary.

### Agriculture: separate own applicability, no fake primary dependency

`land_use_zones.py:38` does not consume Python primary/biomass/forest at all.
It consumes native fertility, soil depth/moisture/salinity/erodibility,
temperature, warm/moist month count, runoff/river/recharge, landform/biome,
ice and aridity. Its annual-air triangle is center17/halfwidth26, hence
open(-9,43). Temperature contributes only .14; other terms can authorize .58
agricultural candidates without it. Only `is_water` is currently excluded, so
standing fresh/saline lakes can enter the land branch. The +.16 fresh-lake
water bonus is applied to the cell itself, not to adjacent irrigable land.

Current version is `causal_soil_climate_resource_connected_land_use_zones_v1`
with a full parameter dictionary, mirrored independently in
`human_geography_validation.py:75,137,255`. Propose v2 with separate exact
`agricultural_climate_supported` and `agricultural_potential_supported` fields:
finite annual-air input in the existing own interval, shared terrestrial
habitat, and valid consumed descriptors. Unsupported estimate is zero+false,
zone ID -1, no agricultural candidate/record. This is the current agriculture
proxy's applicability, not crop survival or settlement habitability. Do not
require primary-v4 solely because it is available; there is no mathematical
dependency. Both proxies may independently be unsupported on the same hot cell.

Preserve .58 raw-pre-rounding threshold and .52 mining threshold, component
order, six-decimal serialization and independently replayed records/counters.
Add agricultural available counts/area and explain the mean's denominator.
Mining is a separate geological/access model and must not be suppressed by
annual primary or agricultural climate support. A separate standing-water
mining/extraction policy may be needed but must not be smuggled into this fix.
The native sibling's fertility/settlement assessment may change which material
descriptors can legitimately be consumed; do not declare physical soil/crop
validation from this wrapper alone.

### Wildfire: unavailable fuel estimate is neither empty fuel nor a barrier

Current models are legacy `heuristic_wildfire_aquatic_exclusion_v2` and native
`heuristic_wildfire_native_seasonal_v3`; the native version omits the old energy
stress/lightning term. Preserve that climate dispatch and exact old metadata
in new-version validation. There is no own calibrated temperature domain in
this fire model; do not add primary's interval as a fire-survival condition.

`_fuel_continuity` (line78) consumes own biomass/primary/ecosystem wildfire
risk, aridity/wetland/ice/biome bonuses and the fraction of all neighbors whose
terrestrial biomass is >=.20. `_firebreak` (107) includes (1-fuel)*.18;
ignition (119) consumes fuel, risk, disturbance, firebreak, wind and settlement.
Spread (157) consumes target ignition/fuel/firebreak, source fuel, pair wind,
biome match and relative elevation. Therefore making unknown fuel numeric zero
without support would falsely increase a firebreak and still allow additive
ignition/spread.

Propose explicit supported flags for ecosystem risk/disturbance (upstream),
final fuel, firebreak and ignition, and a regime such as
`fuel_proxy_unavailable`. Keep wind alignment independently available. Fuel
requires own consumed inputs and every terrestrial neighbor's biomass input;
aquatic neighbors are known excluded zero contributions, and the original
denominator is retained. Do not silently drop unknown neighbors and renormalize.
This availability is one-hop on **biomass**, not recursively on neighbors'
fuel flags, avoiding a spurious all-component loss of support.

Unsupported fuel/firebreak/ignition sentinels never authorize seed events or
spread source/target edges. An edge lacking inputs is unmodelled, not assigned
physical probability zero. Record histories must declare domain coverage and
unavailable adjacent cell IDs / truncated fronts; otherwise a stopped modeled
front looks like verified containment. Exact water exclusions remain the
`non_burnable_water` rule. Do not map unavailable land to water, sparse fuel,
or a new physical firebreak. Preserve independently declared existing ice
regime semantics without deriving ice/nonburnability from the primary flag.
No standing/dead fuel pool exists in this model; a later pool model is needed
to make claims about its persistence or combustion.

Counters (ignition .28, fuel .35, firebreak .55) must continue to use rounded
published values but only supported estimates. Spread threshold .30 and event
limits 96/6/96 remain unchanged. Rebuild history IDs, inverse links, burned
area and regime counts; summaries disclose supported coverage and history
truncation. The independent validator must replay support at both endpoints,
the neighbor denominator, excluded unknown fronts and these counters.

## Public validation and output propagation

- CLI `cli/commands/validate.py`: early malformed numeric preflight at line147;
  ecosystem at15318–15615, species15620–15910, fire15915–16180, land-use17495
  onward. Add exact-version availability handling before eager consumption;
  keep actionable old diagnostics and absent-only legacy dispatch. The v4
  recovery-year zero needs its exact unavailable branch (currently >=1).
  Change expected record coverage as well as scalar bounds. Do not simply
  permit zero everywhere, require flags, or trust a model-supplied tolerance.
- Geo `geo_validation_subsystems.py:_validate_ecosystems` at2110 uses the three
  independent helpers and generic numeric/record checks. Extend its support
  messages and counters to match the new scopes. `geo_layer_contracts.py`
  biomes_ecosystems phase11 already permits empty species/fire/history lists;
  do not require life on an unsupported world. Retain “rule replay without
  population evolution,” not a physical biology verification label.
- Independent helpers: extend `aquatic_climate_validation.py`,
  `species_habitat_validation.py`, `wildfire_aquatic_validation.py`, and
  `human_geography_validation.py` with explicit old/new metadata branches.
  Producer dependency helpers may centralize support state; independent
  validators must mirror prerequisites without importing those functions.
- API: preserve the existing order, full canonical cells before enrichment,
  then suppress `cells` only for requested summary-only output. Add producer
  preflight of known parent contracts before mutation. In geo/full pipelines,
  same-state repeated enrichment must not silently use stale flags. JSON and
  MessagePack retain booleans/metadata generically; no native C ABI fields or
  certificate changes are needed for Python ecological additions.
- CSV: append new scalar flags/statuses in `io/cells_csv.py` without reordering
  existing columns; preserve true/false versus absent legacy blank. Add
  supported counts and explicit denominator descriptions in
  `io/summary_markdown.py:1148,1179,1239`. Numeric zero alone must not imply
  observed ecological absence. Do not replace unknown physical quantities with
  invented new values in summaries or all-world forest percentages.
- Debug export currently discovers bool fields as categorical layers and all
  model dictionaries generically. `debug_export.py:_layer_entry` stores boolean
  categories as strings `False`/`True`; code0 is not invariably false (an
  all-true layer has category0=`True`). Any mask must decode the category table.
  Raw numeric stats currently include sentinel zeros. Keep raw serialized
  values intact, but attach an explicit support-field relation and separate
  supported display statistics/counts; otherwise auto color ranges mix unknown
  with known zero. Do not change exported scientific values to fit the map.
- UI `debug_ui/app.js:42` only explains aquatic primary/fishery unavailability
  in the inspector. Extend this to the new exact flags/statuses. Main layer
  rendering at `activateLayer` line1478 currently colors raw sentinel zero.
  Fetch the paired support layer with the same cache revision, verify lengths,
  decode booleans, and mask only a copied display buffer; preserve cached raw
  arrays. Existing fetchSeq/cache-identity checks must encompass both requests
  and every export snapshot. If support is missing from a declared new model,
  show a contract error/unavailable layer, never a legacy fallback. Help and
  legends distinguish unsupported estimate, known zero and undeclared legacy.
  `layer_docs.js` must replace root's current limitation text only with the
  exact completed model scope. Keep biome/growing-month help descriptive.

## Smallest coordinated integration batches and suggested ownership

1. **Parent availability contract and core ecosystem**: agree the unreleased
   v4 extension for richness/earlier risk/disturbance and supported summaries;
   integrate frozen primary patch plus this explicitly reviewed extension.
   Python producer agent owns `ecosystem_dynamics.py` and new producer tests;
   validator agent owns independent helper/tests. This is a preparation commit,
   not a releasable full-pipeline biological correction by itself.
2. **Species and fire consumers, same release boundary as batch1**: species
   producer agent owns `species_ranges.py`; separate fire agent owns
   `wildfire_disturbance.py`, both use frozen parent contracts. Independent
   validator agent owns their two helpers and scoped mutation suites. Root
   serializes edits to the shared CLI/geo blocks. Both can develop in parallel
   after batch1 freezes, but public enablement waits for both. This closes the
   current primary→consumer dependency without introducing a feedback loop.
3. **Independent agriculture domain/water gate**: land-use producer+
   `human_geography_validation.py` replay owned together by the native/human
   geography agent after his descriptor audit; independent mutation review by
   validator agent. No dependency on final wildfire or species is introduced.
   It can proceed beside batch2 but must not claim native settlement/fertility
   adoption if those separate contracts are still pending.
4. **Public release integration**: root owns `api.py`, shared CLI blocks and
   geo layer contract decisions. UI/export agent owns `io/cells_csv.py`,
   `io/summary_markdown.py`, `debug_export.py`, `debug_ui/app.js/layer_docs.js`,
   related export/schema/JS tests after field names freeze. Enable new current
   metadata only when full/geo validation and availability presentation agree.
   Source-native certificate equality is a release invariant throughout.

Bounded verification should include the 144 frozen primary tests; the current
species producer/helper modules; aquatic and standing-lake wildfire modules;
`test_validate_cli_biosphere_resources.py` and relevant
`test_geo_validation_subsystems.py`; `test_human_geography_validation.py` and
`test_validate_cli_resources_culture.py`; `test_ecology_csv_support.py`, export
and debug-cache/JS tests. Do not update healthy fixtures to blanket legacy.

New meaningful witnesses: all existing proxy boundaries/nextafter; unavailable
parent with positive biome/environment bonuses; supported physical zero;
fish river support without standing fishery; unknown neighbor fuel without
renormalization; unknown source and target spread; stale flags/records then
idempotent rerun; agriculture at -9/43 with nonthermal score above .58; fresh
and saline standing lakes versus dry saline land; exact old/new metadata;
summary-only API counts; CSV false/true/blank; bool category0=`True`; paired
support requests racing a cache switch; actual unchanged hot/cold native
worlds through full and geo pipelines. Existing generic geometry/climate
certificate tests should reject arbitrary temperature tampering; mutate
downstream declarations or generate genuine forcing cases instead.
