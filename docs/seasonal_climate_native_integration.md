# Native seasonal climate integration

The [current simulation review](current_simulation_review_status.md) records the
latest adopted dependency corrections and open physics work. The entries below
retain their original verification scope and adoption status at the time of each
review.

Status, 2026-09-09: **the seasonal model is now selected by new Python configurations, built-in profiles, shipped gallery YAML, the web workbench and direct C++ `Params` defaults.** All YAML requires exact integer `config_version: 2`; unversioned files fail with migration guidance. C ABI V1–V3 and explicit `LegacyWorldConfig` retain their original semantics. Python independently checks the retained certificate before returning native output and aggregates annual energy fields without changing its source. Broad default-migration regression work is in progress; earlier explicit-V4 results below do not establish acceptance of every new default scenario. This remains a prescribed thermal model with empirical rainfall and unresolved atmosphere–ocean feedbacks.

The prior explicit-V4 integrated Python run passed **1,206 tests and 878 subtests in 384.25 seconds**, `runs/review-seasonal-v4-integrated-tests.xml`. It covers all native boundary/energy/ecology/packaging tests, versioned configuration and workbench tests, legacy configuration/CLI behavior, insolation/climate smoke cases, reef/wildfire validation, geography contracts/physics/subsystems, biosphere CLI checks, shared enrichment, writers/CSV and UI regressions. No failure expectations or physical tolerances were weakened. The earlier complete Python suite and scientific calibration matrix predate this model; this focused run does not replace their missing new-model rerun.

## Explicit Python and YAML access

[`SeasonalWorldConfig`](../src/magic_geo/seasonal_config.py) requires the exact integer discriminator 2 and strictly validates every section. It rejects numeric strings, boolean numeric controls, integer overflow and nonfinite values before loading native code. Obsolete `base_temperature_c` and `lapse_rate_c_per_km` produce field-specific migration errors; no automatic opacity conversion exists. Shared YAML parsing, overrides and atomic saves preserve the version. `WorldConfig()` deliberately constructs a new version-2 model. Unversioned files are rejected; the parser never selects the explicit `LegacyWorldConfig` compatibility type.

[`configs/seasonal_smoke.yaml`](../configs/seasonal_smoke.yaml) is an explicit 128-cell, zero-erosion integration configuration. Python `api.generate_world` and `api.generate_geo_world` select V4 for this model. The full API retains internal cells until enrichment finishes, including when the caller suppresses final cells. Raw `native.generate_seasonal_world` and `native.generate_seasonal_geo_world` expose independently checked native output before Python enrichment. `serialization="auto"` selects MessagePack.

The standalone V4 ABI has 43 fields, no legacy temperature controls and no model selector. Its natural 64-bit layout is 312 bytes with alignment 8; old ABI layouts are unchanged. All four full/geography JSON/MessagePack routes, all-field conversions, strict flags and allocation/exception boundaries pass, alongside the existing native suite: **27 CTests in 44.10 seconds**, `runs/review-native-v4-tests.log`. The V4 artifact passes **12,036 independent research replay checks**, `runs/review-c-api-v4-energy-replay.json`.

The Python loader requires every V4 symbol and never falls back to an older ABI. It rejects duplicate keys/nonfinite numbers while freeing native buffers, checks model identity and configured physical inputs, then calls the production independent certificate auditor. A raw call explicitly requesting `include_cells=False` checks the retained four-section certificate with a stated lack of cell-display linkage; missing cells in a full request always fail.

The strict configuration, raw routes, actual full/geography and airless low-precision generation, exports and existing configuration/API pipeline regressions passed **178 tests plus 153 subtests in 34.78 seconds**, `runs/review-seasonal-python-integration-tests.xml`. This result predates the final public ecology/CLI migration checks and does not claim those checks are complete.

## C++ selection and physical meaning

```cpp
magic_geo::Params params;
params.temperature_model = magic_geo::ClimateTemperatureModel::prescribed_seasonal;
params.reference_infrared_optical_depth = 1.0;
magic_geo::ComputeOptions compute;
compute.compute_backend = 1; // CPU
std::string world = magic_geo::generate_geo_world_json(params, compute);
```

The reference optical depth is finite and nonnegative. One is the declared initial model default, not a fitted conversion from the old global temperature. Existing planetary controls provide radius, gravity, area-mean surface pressure, greenhouse opacity multiplier, axial tilt, eccentricity and stellar luminosity. Other coefficients are explicitly retained in output: albedo 0.3, a 365.2422-day year, hydrostatic profile 288.15 K, atmospheric diffusivity 2.2e6 m²/s, a 4 MJ/m²/K land slab and marine storage from actual depth capped at 50 m. The [vertical-model note](seasonal_climate_vertical_model_research.md) gives the formulas and limitations.

The new selection ignores obsolete C++ `base_temperature_c` and `lapse_rate_c_per_km` fields. Even NaN/infinity in these unused fields does not enter the seasonal solve or output. This is an internal C++ compatibility rule; explicit version-2 YAML rejects those fields. Legacy selection retains their original validation and meaning. Stable old CConfig layouts remain 304/312/320 bytes, and old C adapters explicitly select legacy behavior.

## Producer order and retained state

`EarthSystemState::climate_cache` owns the last verified cycle. The same cache passes through initial climate/hydrology stabilization, erosion's stabilization passes and the final post-glacial stabilization. Each solve sees freshly applied sea level and marine connectivity before flow routing reconstructs lakes. Terrain iterations are not elapsed climate years: changed physical inputs require a new periodic solve. Exact unchanged inputs reuse the private result; a warm phase alone never waives numerical verification.

The common climate loop reads monthly temperatures directly from accepted mean Kelvin values, subtracting 273.15 for existing cell consumers. Annual temperature uses actual month durations. It applies no subsequent mean centering, latitude curve, pressure/current temperature offset or elevation lapse. PET, evaporation and causal hydrology consume those resulting temperatures in the same pass.

Wind, current and rainfall descriptors remain empirical. Rainfall's existing bounded exponential multiplier now uses the solved area/time mean relative to a fixed 15°C reference: `clamp(exp(0.04*(Tmean−15)), 0.35, 2.25)`. This reference scales rainfall; it does not impose mean temperature. Seasonal-mode zero atmospheric pressure yields exact zero monthly and annual rainfall. Other legacy circulation and evaporation descriptors are not promoted to a solved atmospheric mass or latent-heat budget.

Lakes and ice produced later do not feed back into this first thermal model. Marine storage is prescribed even where later ice diagnostics indicate freezing. Their final labels must not be used to reconstruct a different set of thermal inputs during serialization. Cloud, albedo, latent heat, lake profiles, phase-change energy and three-dimensional circulation remain unresolved physical feedbacks.

## Output and independent evidence

`climate_model.model_type` is `prescribed_seasonal_surface_energy_v1`. The native-owned `climate_energy_model.model` is `native_prescribed_seasonal_energy_v1`; it declares the equation, coefficients, source convention, requested/accepted numerical controls, achieved convergence, work counts and physical scope.

Three companion arrays retain shared astronomical intervals and accepted thermal subdivision counts, undirected conductance edges, and one budget record per cell. Records contain the captured marine/land surface, latitude, area, pressure, storage, opacity, 13 temperature boundaries and 12 mean temperatures, fourth moments, ASR, OLR, transport, storage, residuals and numerical allowances. Every witness uses round-trip binary64 formatting independent of `float_precision`. Numeric formatters explicitly use the classic locale, so decimal-comma/grouping locales cannot corrupt JSON.

The world serializer requires matching options/backend/cell coverage and checks that every native cell's annual/monthly temperature still equals its retained source. A missing or inconsistent cycle fails; it cannot be replaced with legacy metadata. Serialization never re-solves downstream lake/ice state. JSON-to-MessagePack uses the existing binary64-preserving conversion, although the new public pipeline regression currently exercises JSON.

The library builds and **all 25 CTest cases pass in 57.74 seconds** (`runs/review-native-seasonal-pipeline-tests.log`). New public integration tests use four 128-cell, zero-erosion worlds: seasonal reference, the same input with unusable obsolete temperature fields, legacy reference, and an airless nondefault planet. The first two outputs are byte-identical. Tests verify initial/final hydrology temperatures, actual rainfall response on identical initial terrain, retained monthly/annual means, airless zeros, model validation and frozen C adapters. Separate serialization tests cover both BE and TR-BDF2, all monthly binary64 values, snapshot ownership, and locale independence.

The generated reference, Fibonacci 128, seed 424242 and eight plates, has two physical climate solves. Its final cycle has 8,640 accepted steps/year, 48,600 attempts for that final physical problem, maximum phase difference `2.6459e−6 K`, maximum cell annual net heating `1.02736e−6 W/m²`, and two monthly confirmations with observed changes `2.48077e−6 K` / `2.77870e−5 W/m²`. The solved mean is **18.4826693288°C** and the empirical rainfall factor **1.14947667450**. The CTest witness is `build/seasonal_climate_pipeline_world.json`.

[`verify_seasonal_energy.py`](../scripts/research/verify_seasonal_energy.py) independently reconstructs hydrostatic and slab coefficients, sunlight from published nodes, radiation from fourth moments, graph transport from mean temperatures, storage from boundaries, and monthly/annual identities. The final generated-world pass performed **12,036 checks** over 128 columns, 1,080 nodes and 378 edges, including cell geometry/displayed temperature and planet/model linkage. Maximum graph replay difference was `1.02e−12 W/m²`; ASR/OLR/storage differences were at most `5.69e−14 W/m²`. The largest measured monthly physical residual was `1.73e−8 W/m²`, separately retained rather than replaced by a correction. The archived CTest world and report are `runs/research/prescribed_climate/generated_128_native_world.json` and `generated_128_ctest_replay.json`.

The verifier's **116 tests pass** (`runs/review-native-energy-replay-tests.xml`), including malformed/duplicate/nonfinite JSON, independent coefficient and ledger mutations, excessive declared adaptive error ratios, insufficient confirmations, tilt bounds, valid standalone zero-luminosity equilibria, source/display linkage, and derived arithmetic overflow. The review fixed verifier-only gaps before the final run; an infinite derived magnitude cannot turn a comparison's allowance into infinity. Published numerical tolerances cannot relax the separate algebraic replay comparisons. Both separately solved 12-cell BE/TR-BDF2 witnesses also pass their 1,948-check replays.

[`enrich_world_with_climate_energy_balance`](../src/magic_geo/climate_energy.py) now dispatches complete native envelopes to [`native_climate_energy.py`](../src/magic_geo/native_climate_energy.py). Its independent audit precedes all mutation. Eleven new cell mirrors and 25 summaries use retained month durations and physical areas, with a separate exact enrichment declaration. All five native objects and annual/monthly temperature aliases retain their identities and values on success, repetition and failure. Partial/unknown native envelopes and stale legacy energy aliases fail before mutation. The new aggregation, guard, insolation and legacy climate tests passed **171 tests in 6.36 seconds**; the physical foundation separately passed both real-world tests in **11.69 seconds**, with immutable-source checks after all 36 stages.

The production auditor [`native_climate_energy_validation.py`](../src/magic_geo/native_climate_energy_validation.py) has **141 passing tests** and checked-in genuine 128-cell and both 12-cell integration-method witnesses with deterministic compression and reproduction manifests. Default validation requires full cell linkage. Its exact schemas and bounded errors reject malformed, unknown and unrepresentable evidence; producer tolerances cannot enlarge independent algebraic comparisons.

```sh
cmake --build build -j 4
ctest --test-dir build --output-on-failure
.venv/bin/python scripts/research/verify_seasonal_energy.py \
  build/seasonal_climate_pipeline_world.json
```

The complete Python API, physical-foundation and export integration tests passed **11 tests in 39.41 seconds**, `runs/review-seasonal-public-api-tests.xml`. Both actual public CLI generation scopes complete in about 11.3 seconds on the 128-cell smoke input, writing full JSON and geo-only MessagePack-container output. Full-world `validate` returns `OK`; generic `validate-geo` returns **151 checks, no errors, no warnings, three not applicable**. The geo report is `runs/review-seasonal-geo-validation.json`. Separate workbench tests cover explicit version-2 validation, structured HTTP 422 errors, saved YAML and both job inputs: **31 tests passed**. These measurements predate default adoption. The migrated schema/default templates and profile renderer now use version 2; all 31 workbench validation/save/render/job regressions pass (`runs/review-default-seasonal-workbench-tests.xml`).

The actual debug cache exports 433 layers and 108 record families. Read-only API/cache probes compare every one of the 1,408 new per-cell values exactly with the source binary64 values, inspect all four certificate sections and verify pagination. The reconstructed certificate and annual mirrors pass 12,036 independent checks; all 178 source/cache files retain their hashes. Map responses correctly round to float32 while tables retain full precision. Legacy stress, Celsius-residual and bleaching layers are absent. The report is `runs/review-seasonal-debug-cache-qa.json`; this checks data transport rather than claiming a new visual-rendering or physical-accuracy benchmark.

Monthly ledger replay does not reconstruct unseen integration stages, prove the accuracy of the astronomical quadrature or rebuild transport edges from geometry. Prior independent thermal/astronomical refinement experiments have their own stated scope in [the numerical research note](seasonal_energy_balance_model_research.md). The new generated reference does not inherit Earth calibration, lake/ice feedback or extreme-planet accuracy merely by closing its ledger. Current consumers now use strict dispatch, and default/gallery source adoption is implemented. Broad default-scenario acceptance, larger/exotic-world coverage and physical feedback development remain required work.

## Default adoption verification, 2026-09-09

All 27 native CTest cases pass after changing the direct C++ default, in 158.90 seconds (`runs/review-native-seasonal-default-tests.log`). The crust-reservoir, sediment-partition and ocean-age integrations retain their original checks and now exercise seasonal temperature. The frozen old C ABI tests still emit their original climate identity.

Current configuration/CLI/strict-seasonal tests pass 76 cases and 81 subtests; combined supported numerical extrema also generate through V4 (one case and eleven subtests). The migrated workbench HTTP suite passes 31 cases; server/jobs pass 115 cases and 200 subtests with an actual seasonal generation-to-cache workflow. Broader Python scientific/downstream regression remains underway and must not be inferred from these focused passes.

A fresh public CLI workflow now materializes the unmodified `smoke` profile, generates its 128-cell full world with one erosion iteration in 16.7 seconds and passes full `validate` (`OK`). JSON, Markdown and 418-column CSV outputs are under `runs/review-seasonal-default-public/`. Its saved `verification.json` carries configuration/world SHA-256 values and an independent certificate replay with 12,038 checks, 1,080 forcing intervals and 378 edges. This is a current default-profile workflow, separate from the earlier explicitly configured zero-erosion example.

The migrated climate smoke suite passes 13 tests in 362.83 seconds. Generic cases exercise current monthly/annual energy replay, the analytic eccentric-orbit fluence ratio, stellar/greenhouse scenarios, pressure, drying, zero and near-zero rainfall; old imposed-mean/posthoc equations use an explicitly named legacy control. The full current clock/tectonics CLI module passes 58 tests and four subtests; early certificate errors and a separate certified-position-preserving normal-vector tamper retain both levels of validation. The 512-cell fixture retains actual campaigns/conflicts/trade. Genuine current 256-cell language-contact and neutral 128-cell frontier fixtures now preserve the changed language and settlement-type branches. Five downstream modules pass 180 tests and 485 subtests against retained, configuration-matched current worlds; their report distinguishes generated controls from isolated stage mutations and constructed classifier inputs (`runs/seasonal-default-fixtures/downstream/README.md`). No production coefficients changed in those fixture corrections.

The matching current geo-only CLI generation completes in 16.5 seconds and passes 151 generic checks with no errors or warnings and four not-applicable checks. All five climate certificate objects and all annual/monthly/current-temperature cell fields are exactly equal to the full-world artifact; both independent audits perform 12,038 checks. The exported full-world browser cache contains 433 layers, one stage history and 105 record families.

Real browser QA confirmed current schema/profile rendering, smoke reset and YAML validation, exact maximum-uint64 seed saving and rejection of the next integer, unsaved-edit generation blocking, and the saved-config handoff into the generation form. It found and corrected rounded large-integer schema display: exact decimal display metadata supplements unchanged numeric JSON Schema constraints. Stable workbench assets now revalidate with `Cache-Control: no-cache` on both 200 and 304 responses. These transport/UI checks do not establish climate calibration or biological validity.

The initial broad migration run was stopped after an asynchronous file-response wait; its progress and diagnostic stack are retained in `runs/review-default-seasonal-broad-tests.log`. The exact artifact-endpoint test independently reproduces the wait inside the execution sandbox and passes outside it. That unfinished run produced no complete JUnit result and must not be cited as a full pass; a replacement sweep must use the required execution permissions and durable per-test reporting.

The replacement durable sweep (`runs/review-default-seasonal-sweep-03/`) completed
2,231 passing tests and 3,889 passing subtests before its limit of 50 failed
reports, in 12,124.47 seconds. Those failures belong to 26 test nodes; this is
not a full-suite pass. All nine discovered cached worlds were archived without
errors, including the genuine 1,280/3,015 and 2,048/1,234 civilization witnesses.
The shipped downscaled seed catalog and iteration-driven maturation matrix both
passed in this sweep. Remaining uncompleted nodes run separately, with their
selection recorded in `runs/review-default-seasonal-remaining-selection.json`.

The two large civilization worlds independently replay cleanly; their stale
expected outcomes were corrected with explicit current branch preconditions.
The complete civilization replay module now passes 23 tests and 113 subtests
against configuration/hash-checked archives without regeneration. A separately
scoped downstream route-removal control preserves the trade-decline priority
branch (`runs/seasonal-default-fixtures/civilization-large/README.md`).

Nine corrected API/geo/report tests and 27 subtests pass against retained current
worlds. Two API unit tests had patched the legacy native entry point and
accidentally generated default-size seasonal worlds; patching the actual
entry point restores the intended early-boundary checks. Native energy
diagnostics, temperature linkage and actual cold sheet membership now exercise
the current contracts (`runs/seasonal-default-fixtures/root-geo/README.md`).
The downscaled Earth scenario still fails its unchanged Earthlike ice-cell
envelope (observed 0.0, required [0.005,0.45]); generic integrity and aggregate
calibration-fraction passes do not establish full Earth realism. That diagnostic
failure is retained explicitly, pending physical-model work.

Separately, the isolated settlement-applicability prototype compiles against
the full current native tree and passes all 27 CTest cases in 197.42 seconds,
including C ABI V1–V4 (`/tmp/settlement-native-integration/ctest.xml`). Its
independent Python review now passes 82 cases after closing contradictory
legacy/native identity and malformed-input boundaries. It has not been adopted
into the shared source and does not resolve population, agriculture or economic
access availability.

### Combined ecology consumer acceptance (isolated, 2026-09-10)

The combined parent-v4, species-v3, native-fire-v5, biological-deposit-v3 and
commodity-v1 candidate now passes actual public API generation with the
unchanged main native library. Full generation takes 16.684 seconds and passes
the complete CLI validator; geography-only generation takes 16.5 seconds and
passes generic geo validation. All five climate objects and nine selected raw
temperature/material/terrain fields equal the retained baseline exactly in
both scopes. Python source hashes are identical before and after the probe.
Evidence and complete compressed generated worlds are retained under
`runs/ecology-consumer-public-acceptance/`.

Integration review closed two classes of validation defects. New parent/species
cell flags and summary mirrors now require their exact own model even when
only one such field is injected into a historical world. Current biological
threshold counts use independent raw-source replay, without a contradictory
second check against rounded display values. The parent/species/fire/resource
suite passes 899 cases; the version-marker and public geo suite passes another
102 cases. These are separate focused groups, not a claim that the entire
repository regression suite is green.

Actual browser inspection of retained current worlds verifies unavailable map
layers without fabricated color ramps, partial species-score coverage, and
fire-front scope/edge details. The instruction banner now reflects whether
full nested records are already selected. Browser evidence is retained under
`/tmp/ecology-browser-qa/`; no world generation was substituted by UI fixtures.

The settlement candidate's Python fixtures are now self-contained and its new
focused native target passes from the normal isolated CMake tree. Its 82 Python
cases pass without temporary build/base paths, and the CTest's emitted unit
worlds exactly match the retained cases. This still does not resolve the
downstream settlement/population consumers.

The separate agricultural-v2 candidate passed independent review after fixing
six missing graph/source-link checks: 210 focused cases and all eleven retained
scenario replays pass. Full versus geography-only groundwater differences were
also traced to a preexisting settlement-score input in natural aquifer risk.
That defect and its scientific interpretation are documented in
[`groundwater_dependency_review.md`](groundwater_dependency_review.md); a
versioned natural-groundwater correction remains in isolated development.
The ecology, agriculture and settlement candidates described here have not yet
been adopted into main production source.

For future regression runs, the durable sweep runner optionally accepts
`--archive-failure-worlds`. It retains world-shaped locals from an ordinary
failed test before teardown, without intercepting generation. Such snapshots
are explicitly failure-time values that may contain test mutations, with no
invented generation/configuration provenance. A real subprocess test verifies
durability and duplicate-object handling before a deliberately paused teardown.
This option is not retroactively active in the already-running remaining sweep.

### Fishery worldbuilding and natural-groundwater follow-through

The isolated ecology integration now includes the versioned worldbuilding
fishery check and its independent human-geography validator. Fresh actual full
and geography-only API generation passes in 16.863 and 16.791 seconds,
respectively. The full world passes CLI validation and the geo world passes
generic validation; both preserve the five native climate objects and nine raw
physical/material fields exactly against the same baseline. The combined
worldbuilding/human suite passes 99 cases, and the migrated aquatic compatibility
tests pass 124 cases. Complete generated worlds, hashes and reports are retained
in `runs/ecology-worldbuilding-public-acceptance/`. This remains an isolated
candidate and includes no settlement, agriculture or groundwater prototype.

The fifth worldbuilding check now counts fishery deposits only where independently
validated parent support exists, including freshwater lakes. Its denominator is
the emitted deposit set. An empty denominator is explicitly conditional evidence;
it does not establish global resource availability. The first four checks and
all material-source predicates retain their original equations.

Main smoke-test corrections retain meaningful physical witnesses. The exact
4,096-cell historical Earth snapshot now explicitly uses its original legacy
configuration and passes unchanged numeric assertions in 15.40 seconds. Current
seasonal ocean-ledger tests remain separate. Real cold-world glacier tests pass
with 23 transfers on a geodesic mesh, including 18 between unequal-area cells,
and 19 transfers on the coupled 128-cell mesh. The warm geodesic control has zero
transport. All original volume/depth conservation checks remain; the three
glacier cases pass in 58.62 seconds. Evidence is in
`runs/seasonal-default-fixtures/legacy-earth-reference/` and
`runs/seasonal-default-fixtures/cryosphere-smoke/`.

The natural-groundwater correction now has a frozen first batch, retained in
`runs/natural-groundwater-batch1-review/`: 214 focused cases plus thirteen complete
archive replays. Its aquifer and groundwater outputs are identical between the
original full/geo pair after deliberate version upgrade. It reconstructs natural
limitation from raw physical inputs, excludes settlement suitability, and requires
actual standing water for surface-water bonuses. Annual partition equations and
legacy v1 outputs remain explicit. Downstream river/karst dependencies, public
validation and exports are being integrated separately; this evidence does not
claim public acceptance of that incomplete chain or calibrated groundwater
physics. The later integration and baseline-sweep result is recorded below.

### Natural-water geography API acceptance and completed baseline sweep

The isolated natural-water candidate now completes actual geography-only API
generation in 16.744 seconds and passes generic geo validation. Aquifer and
groundwater v2 feed matching channel/hydraulic v2 outputs and the first declared
karst model. Independent public replay checks the full parent chain before
numeric consumers and requires the final infiltration summary to match the
audited recharge source. All five native climate objects and nine selected raw
physical/material fields still match the baseline exactly; source hashes remain
stable during generation. The complete world and reports are retained in
`runs/natural-water-geo-public-acceptance/`.

Focused verification passes 393 natural producer/replay cases, 164 public-chain
and existing CLI/geo compatibility cases, and 62 export cases plus 13 subtests.
All thirteen complete retained source archives pass the final source-summary
check with zero difference. CSV preserves historical risk and new natural
limitation without aliasing; UI descriptions distinguish annual diagnostic
flows from stored-water stock, measured productivity and seasonal reliability.
Full-world navigation, port and corridor version migration remains separate.

The remaining baseline sweep completed all 675 selected nodes in 6,133.70
seconds, with zero archive errors. There were 664 fully passing nodes and eleven
nodes with failed reports. Pytest reports 666 passed, 589 passing subtests and
eleven failures because two otherwise-passing parent tests contain failed
subtests. Together with sweep03, all 2,920 originally selected nodes have run;
this is not a fresh all-green run of the current worktree. The failure-to-rerun
mapping is retained in
`runs/review-default-seasonal-failure-reconciliation-in-progress.json`.

All 37 failed nodes from the combined sweeps now have passing focused
main-worktree evidence. The two treasury regressions retain the exact historical
Earth configuration, whose opening treasury remains above all later balances.
Both checks plus an unchanged current seasonal full CLI control pass in 1.62
seconds, without a validator bypass; their generated fixture and provenance are
in `runs/seasonal-default-fixtures/economy-opening-peak/`. The latest
water-validator module passes 24 cases and 91 subtests against exact retained
archives. Its volume mutation now exceeds the preserved historical relative
tolerance, while the zero-area case retains both direct groundwater guards and
expects the earlier native geometry rejection at the public CLI. The remaining
Earth ice-envelope discrepancy is still recorded as a physical calibration
limitation, regardless of successful regression checks.


### Main ecology adoption and full natural-water acceptance

The reviewed ecology/worldbuilding batch is now adopted into main production:
70 explicit source/test/fixture paths, each checked against its recorded baseline
before application and its reviewed result hash afterward. Its complete binary
patch excludes generated caches. Independent review found no further dependency
dispatch defect; unrelated main fixes and the treasury test are preserved.
Pre-adoption verification includes actual full/geo public API acceptance and
three treasury compatibility cases. Post-application main verification passes
1,763 focused tests, 31 JavaScript assertions, 72 biosphere CLI tests with 390
subtests, and nine smoke tests with nine subtests. Exact retained inputs were
replayed in current dependency order without native regeneration. The checks
and artifact manifest are retained in
`runs/ecology-parent-support-adoption/`. Native, groundwater, agriculture and
settlement candidate sources were not included in this batch.

The separate natural-water candidate now generates an actual full world in
17.106 seconds and passes full CLI validation. Matching navigation, ports and
corridors v2 follow the five natural stages; reef links, ecology, resources and
societal evidence are then computed in public API order. All five native climate
objects and nine selected raw physical/material fields exactly match the
baseline, and source hashes are stable during generation.

Aquifer, groundwater, channel, hydraulic and karst outputs match the earlier
actual geography-only world exactly across 128 comparisons covering every owned
cell field, root record/model and summary field. The geography-only output
retains human-stage absence. This directly verifies that requested human output
scope no longer changes natural water for the retained physical configuration.
It does not establish calibrated hydraulic heads or a groundwater withdrawal
budget. Complete full output, source hashes, comparison evidence and CLI report
are in `runs/natural-water-full-public-acceptance/`.

The combined natural producer, public, export and existing ecology CLI/geo
suite passes 678 tests; its public water subset contains 76 tests. Independent
reviews pass 94
natural public-contract probes and 288 human water-transport probes. Historical
river and human transport arithmetic remains in private legacy helpers with
byte-for-byte relocation evidence. Natural/human water adoption has since
completed the compatibility migration and main checks recorded below. Settlement
and agricultural applicability remain separate work.


The later natural-water compatibility review adds six complete archive-to-CLI
controls spanning 128–512 cells, including the original legacy climate path.
All retain exact configuration/world hashes and unchanged native physics after
ordered current water/human/ecology replay. A separate actual non-Earth world
(radius 3,200 km, gravity 0.4 g) generates in 12.754 seconds and passes independent
native energy, geometric scaling and full CLI checks. The three treasury tests
also pass under the new natural water chain. These artifacts are included in
`runs/natural-water-full-public-acceptance/`; this acceptance predates the main
adoption recorded below.

The remaining Earth ice-profile discrepancy now has a seven-world audit in
`runs/earth-ice-calibration-review/`. The failing coarse Earth world is an exact
result of the existing annual heuristic, and its independent native energy
certificate passes. A concrete model limitation is that positive generated
land ice requires an annual temperature below -3 degrees C, while the same
constructor's melt term requires a temperature above -1.5 degrees C. Thus its
melt term cannot be positive where that constructor creates ice, even in the
retained controls with warm summers. A separate seasonal mass/enthalpy prototype
is under review; the current calibration bounds and failing physical diagnosis
remain unchanged.

### Main natural-water adoption and independent ice-kernel review

The natural-water chain is now adopted through an exact 77-path patch: 28
production files and 49 test/fixture paths. Independent review confirms the
changed-file set, matching current-main baselines, reconstructed result hashes
and unchanged historical CLI equation blocks. Fresh combined verification passes
848 tests and 612 subtests in 429.65 seconds. It uses complete config/hash-checked
archives, including the actual non-Earth and two custom 512-cell generations;
unexpected native generation is prohibited. Historical numeric diagnostics
retain complete v1 fixtures, while current corruption tests exercise the new
declaration and source checks without bypassing public validators.

All applied main hashes match the reviewed candidate, 541 unrelated existing
files are preserved, and the native library is unchanged. Post-application main
checks pass 92 Python tests and eight JavaScript checks. Exact inputs, patch,
preservation evidence and reports are retained in
`runs/natural-water-main-adoption/`. This completes the diagnosed full/geo
groundwater dependency correction; it does not establish calibrated groundwater
physics or repair separate population and agricultural applicability issues.

The freshwater/mineral-slab enthalpy kernel remains isolated research. Its
standalone tests pass 259 assertions, including sanitizer verification, and an
independent Decimal oracle passes 181 external cases, 11 analytic assertions
and nine audit-mutation checks. The source and portable reproduction package
are in `runs/seasonal-cryosphere-kernel-review/`. This verifies the declared
scalar calorimeter and represented transfer ledger. Surface/atmosphere coupling,
precipitation and melt-water budgets, physical time integration and a new climate
certificate are not implemented by that kernel; the Earth ice diagnosis remains
open.

### Agricultural availability and complete input publication

The independent agricultural-v2 stage is now adopted with its public validation
and display contract. The exact 28-path patch contains 12 production and 16
test/fixture files. It retains the existing equations and raw thresholds, adds
explicit annual-proxy/habitat support, excludes standing-water surface mining,
and requires complete reciprocal mesh and source-record inputs before atomic
publication. Exact historical v1 behavior remains available through its own
declaration; current full output must declare its version.

One actual fresh full 128 world generated in 16.721 seconds and passed native,
natural/human-water, human-geography and full CLI validation with both land-use
and worldbuilding v2. Every unowned world/cell/summary value matches the prior
complete full-world baseline exactly. The final combined tests, main boundary
checks, UI QA and hash/preservation records are in
[`runs/agricultural-main-adoption`](../runs/agricultural-main-adoption/README.md).
See [the contract review](agricultural_availability_review.md) for the four cell
flags, six summary metrics and unavailable-versus-supported-zero behavior.

The [settlement/activity audit](../runs/settlement-activity-dependency-review/README.md)
records remaining natural disturbance/fire and human accessibility dependencies.
Native regional population agriculture is independent of these Python zones and
remains separate work, as does physical seasonal ice coupling.
