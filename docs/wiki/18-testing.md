# Testing and Quality Gates

[Wiki home](./README.md) > Testing and Quality Gates

`magic-geo` has two independent test suites that gate two independent artifacts: a Python suite run by `pytest` (85 modules, 1,868 collected tests) covering configuration, the ctypes boundary, every replay validator, the CLI, the exporters and the web workbench; and a C++ suite registered with CTest by the same CMake build (13 tests on a 64-bit host without CUDA, 14 with CUDA) covering the native simulation core's algorithmic and ABI contracts. The Python suite is split by a single `slow` marker into a tight development loop and an exhaustive `validate`-CLI tier; coverage is deliberately opt-in and deliberately branch-aware. This page enumerates the run commands, the marker system, the coverage caveats, the full grouped test inventory, the `tests/support/` fixture model, every native CTest executable, the optional-extra skip matrix, and a pre-push checklist.

### Where a claim belongs

The suite has one rule that decides which module a new assertion goes in, and it is the rule that keeps the inventory below from growing a second copy of itself:

| Claim | Where it belongs | Why not elsewhere |
| --- | --- | --- |
| A replay validator rejects a specific tampered field | The module that owns the validator — `tests/test_*_validation.py`, `tests/test_*_validators.py` — calling it directly | A direct call names the field that diverged and can assert that undoing the tamper replays clean again. Through the CLI the same tamper collapses into one shared verdict line that a dozen branches can print, and costs a world serialization plus a full validation pass. |
| Every violation branch of the `validate` command is reported | The `slow` tier, `tests/test_validate_cli_*.py` | This is the tier that exists for it, with the whole-line `FAIL` matching, reported-not-raised guard and tamper-actually-tampered guard that a hand-rolled `assertIn` on `result.output` does not have. |
| `validate` reaches and reports a subsystem at all (wiring) | One test in the owning `tests/test_smoke_*.py` module: one tamper per verdict, one command pass | This is the only claim the direct-call modules structurally cannot make. It needs one invocation, not one per tampered field. |
| A generated world satisfies an invariant | `tests/test_smoke_*.py` | — |
| A shipped asset's *content* matches a doc or a JS literal | Nowhere | Grepping a source file for a string literal asserts no behaviour: every refactor breaks it and no bug that leaves the literal intact fails it. Cross-implementation *parity* between two live code paths — `tests/test_debug_map_export_parity.py` comparing the CLI's `_describe_layer` against the web `CURATED` table — is a real claim and does belong. |

## On this page

- [Test tiers and how to run them](#test-tiers-and-how-to-run-them)
- [Configuration: pytest and coverage](#configuration-pytest-and-coverage)
- [The `slow` marker and the exhaustive `validate` tier](#the-slow-marker-and-the-exhaustive-validate-tier)
- [Coverage: opt-in, branch-aware, and partially blind](#coverage-opt-in-branch-aware-and-partially-blind)
- [Python test inventory](#python-test-inventory)
- [`tests/support/` and the world-caching fixture model](#testssupport-and-the-world-caching-fixture-model)
- [The native CTest suite](#the-native-ctest-suite)
- [Optional extras and the skip matrix](#optional-extras-and-the-skip-matrix)
- [Contributor checklist before pushing](#contributor-checklist-before-pushing)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

## Test tiers and how to run them

The Python suite requires the `test` extra (`pyproject.toml:25-28`: `pytest>=9,<10`, `pytest-cov>=7`). The optional `debug` extra (`pyproject.toml:19-24`: `pyarrow>=19`, `duckdb>=1.2`, `fastapi>=0.115`, `uvicorn[standard]>=0.34`) unlocks the exporter and workbench modules; without it those modules skip themselves rather than fail.

```bash
pip install -e ".[test]"          # add ",debug" to also run the workbench/server tests
python -m pytest                  # full suite (~29 min)
python -m pytest -m "not slow"    # ~13 min: skips the exhaustive validate-command tier
python -m pytest -m "slow"        # ~16 min: exhaustive validate-command tier only
python -m pytest --cov --cov-report=term-missing   # full branch coverage (~2 h)
python -m pytest --cov --cov-report=html           # same report, browsable in htmlcov/
```

That block is reproduced verbatim from `README.md:238-245`. The native suite is a separate build-tree command; the last two lines below are `README.md:267-268` verbatim, and the first is the one-off configure step they assume (`BUILD_TESTING` defaults to `ON`, `README.md:264`):

```bash
cmake -S . -B build                          # configure once; BUILD_TESTING defaults to ON
cmake --build build                          # builds the test executables too
ctest --test-dir build --output-on-failure   # 13 native tests, ~5 s
```

| Tier | Command | Tests | Documented runtime | Source of the runtime figure |
| --- | --- | ---: | --- | --- |
| Full Python suite | `python -m pytest` | 1,868 collected | ~29 min | `README.md:240` |
| Fast tier (development loop) | `python -m pytest -m "not slow"` | 1,482 selected / 386 deselected | ~13 min | `README.md:241` |
| Slow tier (`validate` CLI) | `python -m pytest -m "slow"` | 386 selected / 1,482 deselected | ~16 min | `README.md:242` |
| Full suite under coverage | `python -m pytest --cov --cov-report=term-missing` | 1,868 | ~2 h ("roughly four times its normal runtime") | `README.md:243`, `README.md:255-256` |
| Native CTest suite | `ctest --test-dir build --output-on-failure` | 13 (14 with CUDA) | ~5 s | `README.md:268` |

The selection counts above were confirmed against this checkout with `pytest --collect-only -q`, `-m slow` and `-m "not slow"`. The wall-clock figures are the README's own documented numbers on unspecified hardware; they are not a reproducible guarantee. The native suite on this checkout reported `100% tests passed, 0 tests failed out of 13`, with `Total Test time (real)` landing between `5.3` and `5.4 sec` across repeated runs — consistent with the documented `~5 s`, but a single-host measurement that varies run to run, not a fixed constant.

Useful narrowing commands, all using the real surface as configured:

```bash
python -m pytest tests/test_smoke_core_mesh.py -q            # one module
python -m pytest tests/test_geo_validation.py -k contract    # one keyword slice
python -m pytest -m "not slow" -x -q                         # fast tier, stop at first failure
ctest --test-dir build -N                                    # list native tests without running
ctest --test-dir build -R magic_geo_native_api --output-on-failure   # one native test
```

## Configuration: pytest and coverage

Everything is declared in `pyproject.toml`; there is no `conftest.py` anywhere in the repository, and `tests/` has no `__init__.py` (both verified by `find`/`ls`). Shared fixtures were consolidated out of `conftest.py` into `tests/support/` (commit `11b16b9`), which is why test modules import `from support import worlds` — pytest's rootdir-prepend import mode puts `tests/` on `sys.path`, and `tests/support/__init__.py` makes `support` a package.

| Setting | Value | Location | Effect |
| --- | --- | --- | --- |
| `testpaths` | `["tests"]` | `pyproject.toml:48` | A bare `python -m pytest` collects only `tests/`. |
| `norecursedirs` | `[".claude", "build", "cmake-build-debug", "cpp", "worlds", "runs"]` | `pyproject.toml:49` | Keeps collection out of build trees, the C++ source tree, and generated output directories. |
| `markers` | `slow: exhaustive CLI validate-command coverage; deselect with -m "not slow"` | `pyproject.toml:50-52` | The only registered marker. |
| `[tool.coverage.run] source` | `["magic_geo"]` | `pyproject.toml:57` | An **import name**, not a path, "so the editable install resolves to `src/magic_geo` and stale worktree copies are never measured" (`pyproject.toml:55-56`). |
| `[tool.coverage.run] branch` | `true` | `pyproject.toml:58` | Branch coverage, not just statement coverage. |
| `[tool.coverage.run] omit` | `["*/magic_geo/debug_ui/*", "*.egg-info/*"]` | `pyproject.toml:59-62` | The browser UI assets are JS/CSS/HTML, not measurable Python. |
| `[tool.coverage.report] show_missing` | `true` | `pyproject.toml:65` | Adds the `Missing` column of uncovered line ranges. |
| `[tool.coverage.report] precision` | `1` | `pyproject.toml:66` | One decimal place in the `Cover` column. |
| `[tool.coverage.report] exclude_also` | `["if TYPE_CHECKING:", "raise NotImplementedError", 'if __name__ == "__main__":']` | `pyproject.toml:67-71` | Three unreachable-by-design patterns excluded on top of coverage's defaults. |
| `[tool.coverage.paths] magic_geo` | `["src/magic_geo", "*/site-packages/magic_geo"]` | `pyproject.toml:73-74` | Remaps an installed copy onto the source tree so combined reports do not double-count. |

No linter, formatter, type-checker or pre-commit configuration exists in the repository (no `[tool.ruff]`/`[tool.black]`/`[tool.mypy]` in `pyproject.toml`, no `.ruff.toml`, `.flake8`, `mypy.ini` or `.pre-commit-config.yaml`). No CI workflow directory exists either (`.github/` is absent). The gates on this page are the ones a contributor runs by hand.

## The `slow` marker and the exhaustive `validate` tier

`slow` is applied as a module-level `pytestmark = pytest.mark.slow` in exactly eight modules — never per test, never per class:

| Module | `pytestmark` line | Tests | Canonical world | Slice covered |
| --- | --- | ---: | --- | --- |
| `tests/test_validate_cli_natural_systems.py` | `:84` | 95 | `replay_128` | Plate-motion summary roll-up, mesh LOD hierarchy, spherical spatial index, cell geometry and adjacency edges, tectonic zones, fault systems, lake basins and overflow histories, watersheds and cell-edge boundaries, hydrologic water budget. |
| `tests/test_validate_cli_biosphere_resources.py` | `:53` | 69 | `replay_128`, `mid_512` | Biosphere and resource record contracts. |
| `tests/test_validate_cli_climate_cryosphere.py` | `:50` | 59 | `replay_128` | Climate, ocean and cryosphere gates. |
| `tests/test_validate_cli_clock_tectonics.py` | `:40` | 57 | `replay_128` | Clocks, cells and plate motion. |
| `tests/test_validate_cli_resources_culture.py` | `:70` | 38 | `replay_128`, `small_smoke` | Resources, culture and population. |
| `tests/test_validate_cli_natural_records.py` | `:43` | 32 | `replay_128`, `mid_512` | Natural record contracts. |
| `tests/test_validate_cli_core_hydrology.py` | `:55` | 21 | `replay_128` | Core schema and hydrology gates. |
| `tests/test_validate_cli_history_economy.py` | `:45` | 15 | `small_smoke` | History, economy and graph gates. |

Totals: 386 tests, 20.7% of the 1,868 collected — the README's "21% of the tests but the majority of the runtime". The runtime dominance has a structural cause: *every* case in the tier invokes the real `validate` command end-to-end over a serialized world, so each test pays a full JSON write plus a full validation pass, and the tier's ~16 min against the fast tier's ~13 min is that cost multiplied 386 times.

### Why the tier exists and what a case actually asserts

The `validate` command accumulates every complaint into one list and prints it at a gate — an early gate after the schema checks, then a final gate covering everything else — so a healthy generated world only ever exercises the *passing* side of each check (`tests/test_validate_cli_natural_systems.py:3-9`). The slow tier drives the *reporting* side: it deep-copies the canonical world, breaks one derived quantity, and asserts the exact `FAIL` line the command owes that quantity.

The harness in `tests/test_validate_cli_natural_systems.py:235-307` encodes four defences that make the assertion meaningful:

| Defence | Implementation | Why |
| --- | --- | --- |
| Fixture-is-clean proof | `test_untampered_world_validates` (`:252-257`) runs the untampered world in every class and requires exit code 0, zero `FAIL` lines and an `OK` in the output | Each tampered assertion carries proof that the baseline is not already failing. |
| Reported-not-raised | `assert_reported_not_raised` (`:259-278`) inspects `result.exception` and fails on any `Exception` | `CliRunner` turns an uncaught exception into `exit_code == 1` with *empty* output and no traceback text, so `assertNotIn("Traceback", result.output)` can never fail and is not a crash guard. `typer.Exit` raises `SystemExit`, which is not an `Exception`; anything else means a check raised instead of reporting. The same reasoning is captured for reuse in `tests/support/cli.py:1-9`. |
| Tamper-actually-tampered | `invoke_tampered` (`:280-293`) asserts `payload != self.world` before writing | A hard-coded value that happens to equal the generated one cannot pass as a tamper. |
| Whole-line matching | `assert_reports` (`:295-307`) matches `f"FAIL {message}"` against whole reported lines from `fail_lines` (`:92-98`) | A check whose message merely *contains* the expected one cannot stand in for the check under test. `fail_lines` reads `result.output` because the early gate prints to stdout and the final gate to stderr. |

A worked example — `tests/test_validate_cli_natural_systems.py:316-323` proves the summary roll-ups are checked against the replayed history rather than trusted:

```python
def test_motion_summary_roll_ups_are_checked_against_history(self) -> None:
    def mutate(payload: Payload) -> None:
        metrics = summary(payload)
        metrics["plate_motion_history_step_count"] += 1
        metrics["total_aged_oceanic_event_count"] += 1
        metrics["mean_plate_cumulative_rotation_deg"] += 1.0

    self.assert_reports(mutate, MOTION_FAILURE)
```

where `MOTION_FAILURE = "plate kinematic model or motion history invalid"` (`:310`).

The tier is explicit about what it *cannot* prove. Several record families fold a dozen branches into one verdict line; a `subTest` table against such a verdict proves each branch is reachable and reported, but "the assertion still cannot name the branch: disable the branch a case targets and a later one sets the same flag and prints the same line. Those tables say so, and none of them claims more" (`tests/test_validate_cli_natural_systems.py:28-37`). Three checks in the natural-systems slice are documented as not assertable through the CLI at all (`:44-61`): `watershed fitted Hack relation invalid` (its three raise paths are all unreachable through a serialized world), a `None` zone family (measured with `len` by a later check, so the command raises before its gate), and two cell-field conversion guards shadowed by unguarded conversions elsewhere.

## Coverage: opt-in, branch-aware, and partially blind

Coverage is **not** wired into `addopts` — `pyproject.toml` has no `addopts` key at all. It is opt-in because instrumenting a generation-heavy suite "takes roughly four times its normal runtime" (`README.md:255-256`), i.e. roughly 2 h against 29 min. Turning it on for every local run would make the fast tier unusable as a development loop.

Branch coverage is on (`pyproject.toml:58`) for a domain-specific reason stated in `README.md:253-255`: **"a validator's rejection path matters as much as its happy path."** Most of `src/magic_geo` is validators, replay checks and schema gates whose entire job is to reject; a statement-only report would score a validator as covered when only its success arm ever ran. On this checkout the measured package holds 47,166 statements and 17,110 branches — the branch count is over a third of the statement count, which is why the distinction is not cosmetic here.

A full instrumented run of the whole suite on this host reported **97.4%** combined statement+branch coverage: 830 statements never executed and 795 partially exercised branches. The least-covered module above 20 statements was `src/magic_geo/settlement_routes.py` at 85.2%; nothing in the package sits in a coverage hole. Read that number the way the rest of this page reads it — it says those lines ran, never that the assertion around them was strong, and it says nothing at all about `libmagic_geo_native.so`.

### Two documented caveats when reading a report

Both are stated in `README.md:256-259` and are carried forward here unchanged:

| Caveat | What it means for a report | Consequence |
| --- | --- | --- |
| **Only Python is measured.** The C++ simulation core in `libmagic_geo_native.so` never appears. | The report describes the Python layer only: configuration, orchestration, enrichment, validators, serialization, exporters, CLI. Everything in `cpp/src/` — mesh construction, tectonics, transport, climate, hydrology — is invisible regardless of how much of it the suite exercises. | A high Python coverage percentage says nothing about native-core coverage. The native core's gates are the CTest suite and the Python-side *replay* validators that reconstruct native results independently, not `coverage`. |
| **Generated worlds are cached per process** by `tests/support/worlds.py`, so parallel runners pay one generation per worker. | The `_cache` dict in `tests/support/worlds.py:45` is module-global and per interpreter process. Under a serial run each canonical world is generated at most once. Under any parallel runner each worker regenerates the worlds it needs. | Wall-clock scaling under parallelism is sublinear, and a coverage run distributed over workers multiplies the generation cost by the worker count. |

### Reading a `term-missing` report

```bash
python -m pytest -m "not slow" --cov --cov-report=term-missing
```

The report block is titled `coverage: platform linux, python <version>` and its columns are:

| Column | Meaning | Configured by |
| --- | --- | --- |
| `Name` | Path of the measured module, remapped onto `src/magic_geo` | `[tool.coverage.paths]` (`pyproject.toml:73-74`) |
| `Stmts` | Executable statements in the module | — |
| `Miss` | Statements never executed | — |
| `Branch` | Branch destinations tracked | `branch = true` (`pyproject.toml:58`) |
| `BrPart` | Partially exercised branches — taken one way but never the other | `branch = true` |
| `Cover` | Combined statement+branch percentage, one decimal | `precision = 1` (`pyproject.toml:66`) |
| `Missing` | Uncovered line ranges, and `N->M` arrows for missing branch destinations | `show_missing = true` (`pyproject.toml:65`) |

`BrPart` is the column that matters most for this codebase: a validator with `BrPart > 0` has a rejection arm that no test reaches. Lines matching `if TYPE_CHECKING:`, `raise NotImplementedError` and `if __name__ == "__main__":` are excluded from the denominator (`pyproject.toml:67-71`). The HTML variant (`--cov-report=html`) writes to `htmlcov/` and colours partial branches distinctly from missed statements.

A coverage number is a reachability statistic, not a correctness claim: it records that a line ran, never that the assertion around it was strong. The slow tier's own docstrings are explicit that coverage showing a branch was taken does not let the test *name* the branch when several branches share one verdict line.

## Python test inventory

85 modules, 1,868 collected tests. Every module uses `unittest.TestCase` classes with pytest as the runner — verified by grep: all 85 files reference `unittest` and `TestCase`, almost always as `from unittest import TestCase` (79 files) or `from unittest import SkipTest, TestCase` (7 files); the plain `import unittest` form appears in only five files, so grepping for it is the wrong probe. Counts below are per-module collected test counts from `pytest --collect-only -q`.

| Group | Files | What they protect |
| --- | --- | --- |
| **`validate` CLI exhaustive tier** (all `slow`) — 8 files, 386 tests | `test_validate_cli_natural_systems` (95), `test_validate_cli_biosphere_resources` (69), `test_validate_cli_climate_cryosphere` (59), `test_validate_cli_clock_tectonics` (57), `test_validate_cli_resources_culture` (38), `test_validate_cli_natural_records` (32), `test_validate_cli_core_hydrology` (21), `test_validate_cli_history_economy` (15) | Every violation branch of the public `validate` command, driven through the real CLI over a serialized generated world. Each case tampers one derived quantity and asserts the exact `FAIL` line, with a clean-fixture control per class and a reported-not-raised guard per invocation. |
| **Geo validation framework** — 7 files, 225 tests | `test_geo_validation` (54), `test_geo_validation_subsystems` (46), `test_geo_evolution_provenance` (34), `test_geo_validation_physics` (31), `test_geo_layer_contracts` (28), `test_geo_validation_suite` (26), `test_geo_empirical_calibration` (6) | `validate-geo` check-record shape, domain composition, profile gates, realism-evidence integrity; the 14 layer contracts and their dependency/scope adaptation; the suite's matrix schema, expectations, cross-scenario relations, determinism fingerprints and empirical-calibration policy; the geo-evolution provenance registry. |
| **Solid-earth replay validators** — 15 files, 215 tests | `test_crust_dry_rock_accounting_validation` (32), `test_crust_material_shadow_validation` (26), `test_sediment_validators` (22), `test_crust_transport_validation` (21), `test_plate_boundary_edge_validation` (19), `test_oceanic_age_depth_validation` (18), `test_crust_coverage_geometry_replay` (17), `test_sediment_interface_validation` (16), `test_crust_overlap_candidate_fate_validation` (11), `test_sediment_source_partition_validation` (11), `test_initial_oceanic_crust_age_validation` (7), `test_crust_process_validation` (6), `test_maturation_timestep` (6), `test_moving_domain_timestep_diagnostic` (2), `test_young_planet_crust_age` (1) | The Python-side independent replays of native crust/tectonics/sediment results: exact directed boundary-segment reconstruction, forward overlap CSR closure, membership-class crosswalk, persistent material shadow, the three-reservoir dry-rock counter-model, bedrock/mobile-sediment interface identity, alluvium-before-bedrock partitioning, initial oceanic age graph, Parsons–Sclater subsidence targets, and the bounded O(N²) geometry replay. |
| **Human, cultural and economic replay validators** — 13 files, 198 tests | `test_human_validators` (33), `test_logistics_history` (27), `test_civilization_geography_validation` (22), `test_cultural_geography_validation` (21), `test_human_geography_validation` (18), `test_market_clearing_validation` (13), `test_history_economy_validation` (11), `test_logistics_exchange_validation` (11), `test_demographic_agents_validation` (10), `test_territorial_geography_validation` (10), `test_historical_geography_validation` (8), `test_dynasty_genealogy_validation` (7), `test_phonology_history_validation` (7) | Causal-replay validators for the civilization layers: population/conflict/dynasty models, cultural and territorial geography, logistics networks and market exchange, deterministic market clearing, demographic agents and life events, historical event timelines, phonological history. These layers are explicitly outside `validate-geo`'s declared scope. |
| **Debug exports and web workbench** — 6 files, 231 tests | `test_debug_map_export` (73), `test_web_jobs` (58), `test_debug_server` (57), `test_debug_export` (30), `test_debug_rerun` (9), `test_debug_map_export_parity` (4) | The columnar debug-cache exporter and its manifest, the raster/map export path and its layer-description parity with the in-app catalog, the FastAPI server routes and cache-revision semantics, the job manager and operation catalog (staging/publish, cancellation, artifact snapshots, workspace confinement), and the Rerun `.rrd` exporter. The parity module compares the CLI's `_describe_layer` against the web `CURATED` table, i.e. two live code paths — not a file's text against a doc's text. |
| **IO, serialization, native boundary and config** — 6 files, 161 tests | `test_native_boundary` (55), `test_io_writers` (41), `test_geotiff` (31), `test_config` (19), `test_serialization` (12), `test_native_messagepack` (3) | Error paths at the ctypes/native boundary and in the `.mgeo` container; the map writers' rendering tail; the hand-rolled GeoTIFF reader against synthetic byte-exact files; `WorldConfig` validation; JSON/msgpack round trips including the numeric and unicode edge cases. |
| **Enrichers** — 2 files, 111 tests | `test_enrichers_terrain_biome` (77), `test_enrichers_routes_frontiers` (34) | The four terrain/biome enrichers and three route/frontier enrichers: error, degenerate and classification paths. |
| **Calibration and scaling** — 5 files, 100 tests | `test_calibration` (61), `test_ensemble_calibration` (21), `test_planet_scaling` (10), `test_resource_scaling` (4), `test_scaling` (4) | Source-config loading, per-format readers and samplers, tolerance policy, target derivation and provenance hashing, the coverage-versus-fit separation in the calibration report; ensemble manifests, grouped fit arithmetic and reader guards; power-law and planet/resource scaling helpers. |
| **Smoke suites (subsystem end-to-end)** — 13 files, 78 tests | `test_smoke_society_economy` (11), `test_smoke_climate` (11), `test_smoke_coast_ocean` (9), `test_smoke_core_mesh` (9), `test_smoke_hydrology` (8), `test_smoke_culture_history` (6), `test_smoke_tectonics` (6), `test_smoke_settlements_routes` (6), `test_smoke_biosphere` (5), `test_smoke_sediment` (5), `test_smoke_resources` (4), `test_smoke_cryosphere` (2), `test_smoke_exports` (2) | Assertions over an actually generated world, one module per subsystem: mesh/schema/planet scale, plate tectonics and crust, climate energy balance, coasts and ocean circulation, lakes/rivers/groundwater/water budgets, sediment routing and stratigraphy, cryosphere, soils/biomes/disturbance, resources and land use, settlements/routes/ports/politics, cultures/languages/records, population/economy/markets/dynasties, and the calibration/artifact exports. Plus, per subsystem, exactly one wiring test that tampers one field per verdict and asserts every resulting `FAIL` line in a single `validate` pass — see [Where a claim belongs](#where-a-claim-belongs). |
| **Climate, hydrology and water dynamics** — 5 files, 83 tests | `test_climate_dynamics` (34), `test_water_validators` (24), `test_hydrology_dynamics` (18), `test_hydrology_realism` (6), `test_climate_classification` (1) | Behavioural tests of the climate dynamics module, the hydrology dynamics and realism modules, the Köppen-style classifier, and focused branch coverage of the water replay validators. |
| **CLI commands (non-`validate`)** — 5 files, 74 tests | `test_cli_export_serve` (27), `test_cli_validate_geo_calibrate` (19), `test_cli_generate_render` (15), `test_debug_cli` (7), `test_config_cli` (6) | The CLI surfaces of `export-debug`, `export-debug-map`, `export-rerun`, `serve`; `validate-geo`, `validate-geo-suite`, `calibrate`, `calibrate-ensemble`, `derive-targets`; `generate`, `render`, `render-raster`; and the config subcommands — error paths, option validation, and optional-dependency branches. |

`tests/test_cli_export_serve.py:1-14` documents the mechanism used for the optional-dependency branches: the commands are always exercised through `magic_geo.cli.app` and their bodies are never imported directly, with the *import site* poisoned in `sys.modules` (setting an entry to `None` makes `import` raise `ImportError`) rather than the module being patched.

## `tests/support/` and the world-caching fixture model

Five modules under `tests/support/`. There is no `conftest.py`; `tests/support/__init__.py` is a one-line package marker (`"""Shared helpers for the magic-geo test suite."""`).

| Module | Public surface | Used by | Purpose |
| --- | --- | ---: | --- |
| `worlds.py` | `REPO_ROOT`, `EARTHLIKE_CONFIG`, `CANONICAL`, `build_config()`, `canonical_config()`, `cached_world_readonly()`, `cached_world()` | 49 modules | Canonical configurations and the per-process generation cache. |
| `cli.py` | `assert_no_cli_crash(testcase, result, *, command="command")` (`:18-23`) | 17 modules | Requires that the CLI *reported* a failure rather than raising, by inspecting `result.exception` for a non-`SystemExit` exception and formatting the original traceback into the failure message. |
| `builders.py` | `sample_world()` (`:10`), `pack_lzw_literals()` (`:33`), `apply_horizontal_predictor()` (`:62`), `build_geotiff()` (`:93`) | 4 modules | A serialization edge-case payload (unicode with an embedded control character, `None`/`True`, `2**64 - 1`, `-(2**63)`, `-0.0`, `math.nextafter(0.0, 1.0)`, `1.7976931348623157e308`, empty containers, nested records) and a hand-rolled single-strip single-band GeoTIFF writer supporting compression 1/5/8, raw deflate (`wbits=-15`), big-endian layout, TIFF Predictor=2, tag overrides and deliberate truncation. |
| `nativestub.py` | `patch_generation_payload(library, payload)` (`:13-25`), `patch_loaded_library(library, *, path=Path("incomplete.so"))` (`:28-39`) | 4 modules | Stands in for the native library. The first patches `native._load_library`, `native._consume_json_pointer` and `native._consume_msgpack_pointer` so both transports return a chosen payload — "used to drive the schema-gating branches that a healthy native library can never produce". The second patches `native._library_path` and `native.ctypes.CDLL` to simulate an incomplete or missing shared object. |
| `shapefiles.py` | `write_vector_shapefile()` (`:14`), `write_polyline_shapefile()` (`:38`), `write_polygon_shapefile()` (`:42`), `write_dbf()` (`:46`), `write_dbf_table()` (`:71`), `write_opendap_ascii_grid()` (`:109`) | 2 modules | Byte-exact synthetic ESRI shapefile, DBF and OPeNDAP ASCII grid fixtures. The module docstring gives the reason: "The calibration readers parse these formats by hand, so the tests build the smallest byte-exact files that exercise each reader instead of shipping binary fixtures." |

### The canonical worlds

`CANONICAL` (`tests/support/worlds.py:25-43`) declares five named configurations as dotted overrides on `configs/earthlike_seed.yaml` (`EARTHLIKE_CONFIG`, `:21`). The base seed is 4,096 cells / 14 plates / 6 erosion iterations (`configs/earthlike_seed.yaml:21`, `:25`, `:46`); unset fields inherit those values.

| Key | `mesh.cell_count` | `tectonics.plate_count` | `erosion.iterations` | Modules referencing the key |
| --- | ---: | ---: | ---: | ---: |
| `small_smoke` | 256 | 8 | 2 | 20 |
| `mid_512` | 512 | 8 | 1 | 10 |
| `routed_512` | 512 | inherited (14) | inherited (6) | 2 |
| `coupled_128` | 128 | 8 | 1 | 5 |
| `replay_128` | 128 | inherited (14) | inherited (6) | 30 |

The comment above the dict states the policy: "Configurations shared by more than one test, as dotted overrides on the earthlike seed. One-off configurations stay inline in their own test" (`:23-24`).

### The caching contract

```python
_cache: dict[str, dict[str, Any]] = {}          # tests/support/worlds.py:45

def cached_world_readonly(key: str) -> dict[str, Any]:
    """The shared generated world for ``key``. Callers must never mutate it."""
    if key not in _cache:
        _cache[key] = generate_world(canonical_config(key))
    return _cache[key]

def cached_world(key: str) -> dict[str, Any]:
    """A private deep copy of the generated world for ``key``."""
    return copy.deepcopy(cached_world_readonly(key))
```

| Accessor | Returns | Contract | Modules using it |
| --- | --- | --- | ---: |
| `cached_world_readonly(key)` | The shared object from `_cache` | Read-only. "mutating it corrupts every later test in the process" (`tests/support/worlds.py:7-8`). | 41 |
| `cached_world(key)` | `copy.deepcopy` of the shared object | Free to mutate — this is what every tamper-style test uses. | 36 |
| `canonical_config(key)` | A freshly built `WorldConfig` | For tests that need to generate with a variation rather than reuse a cached world. | 6 |
| `build_config(**dotted)` | A `WorldConfig` from the earthlike seed with dotted-key overrides applied through `model_dump` / `model_validate` | For one-off configurations that do not belong in `CANONICAL`. | 4 |

The rationale is stated in the module docstring (`tests/support/worlds.py:3-5`): "Generating a world runs the native simulation core plus the full enrichment pipeline, so each canonical configuration is generated at most once per process." The slow tier leans on this hard — `ValidateSliceCase.setUpClass` calls `worlds.cached_world(WORLD_KEY)` once per class and writes one on-disk baseline, then each case deep-copies in memory (`tests/test_validate_cli_natural_systems.py:238-246`).

## The native CTest suite

`include(CTest)` at `CMakeLists.txt:5` introduces `BUILD_TESTING`, which defaults to `ON`; the entire test block is `if(BUILD_TESTING)` at `CMakeLists.txt:223-528`. The Docker builder stage deliberately configures with `-DBUILD_TESTING=OFF`, so the image build does not compile them.

On this checkout (`MAGIC_GEO_ENABLE_CUDA:BOOL=OFF`, 64-bit host) `ctest -N` lists exactly the 13 tests below in this order, and a full run reported `100% tests passed, 0 tests failed out of 13` in `5.40 sec`.

| # | CTest test name | Executable | Contract it protects |
| ---: | --- | --- | --- |
| 1 | `magic_geo_initial_oceanic_age` | `magic_geo_initial_oceanic_age_test` | The initial oceanic crust-age graph algorithm in isolation: `bilateral_distance_over_half_rate_is_exact`, `length_weighted_global_rate_is_used`, `zero_motion_and_disconnected_components_use_explicit_ceiling`, `planet_age_ceiling_and_invalid_rate_are_enforced` (`cpp/tests/initial_oceanic_age_test.cpp:105,158,192,249`). It re-implements minimal production-equivalent dependencies so the unit test stays focused on the graph-age algorithm "without linking the monolithic native engine" (`:10-11`). |
| 2 | `magic_geo_oceanic_age_depth` | `magic_geo_oceanic_age_depth_test` | The Parsons–Sclater thermal-subsidence curve: `analytic_checkpoints_match`, `transition_is_c0_continuous_and_monotone`, `non_oceanic_and_domain_guards_are_exact` (`cpp/tests/oceanic_age_depth_test.cpp:39,62,110`). The reference formula is `-350·√age` below 70 Ma and `-(350·√70 + 3200·(e^(-70/62.8) − e^(-age/62.8)))` above, with agreement checked against a ULP bound (`:19-37`). |
| 3 | `magic_geo_oceanic_age_depth_integration` | `magic_geo_oceanic_age_depth_integration_test` | `schema_and_serialized_checkpoints_are_consistent` (`:161`): the serialized `oceanic_age_depth_model` must declare `model = "continuity_adjusted_parsons_sclater_relative_basement_subsidence_v1"`, `authority_scope = "relative_oceanic_thermal_subsidence_target_curve_only"`, `continuity_at_transition_resolved: true` **and** `derivative_continuity_at_transition_resolved: false`; and it must keep twelve flags explicitly `false` — `absolute_basement_depth_calibrated`, `physical_crust_creation_age_provenance`, `ridge_age_distance_consistency`, `thermal_structure_represented`, `heat_flow_represented`, `dynamic_topography_represented`, `flexure_represented`, `physical_dynamics_represented`, `authoritative_for_realized_thermal_relief_component`, `realized_thermal_relief_state_tracked`, `thermal_relaxation_timescale_calibrated`, `unapplied_thermal_tendency_residual_carried_forward` (`:204-220`), while four `..._replayed` / `..._resolved` flags must be `true` (`:221-229`). The test is a guard against a hedged model being silently promoted to a physical claim. |
| 4 | `magic_geo_crust_overlap_shadow` | `magic_geo_crust_overlap_shadow_test` | The CPU continuous-moment overlap shadow: exact replay validates with `maximum_error_to_bound_ratio == 0.0`; an empty destination retains zero incoming volume, zero thickness, zero age and its *source-snapshot* density; a raw gap row must **not** be destination-normalized; a 24-way overlap row must produce transported thickness; and `std::numeric_limits<double>::max()` areas stay finite-safe (`cpp/tests/crust_overlap_shadow_test.cpp`, `main`). |
| 5 | `magic_geo_serialization_roundtrip` | `magic_geo_serialization_roundtrip_test` | Seven contracts (`:27,64,78,90,127,148,185`): strictly-positive area arrays and scalars round-trip binary64 exactly (including `denorm_min`, `DBL_MIN`, `DBL_MAX`); non-finite values remain fail-closed; MessagePack scalars use lossless standard encodings; MessagePack strings and containers are valid; malformed JSON→MessagePack fails closed; FFI diagnostic UTF-8 is preserved or sanitized. Its own registration block (`CMakeLists.txt:320-336`) carries no `-ffp-contract=off` guard — one of four test targets whose test translation unit is compiled without it (see the build-composition table below); the other three all link `magic_geo_native`, which *is* built with the flag. |
| 6 | `magic_geo_plate_boundary_segments` | `magic_geo_plate_boundary_segments_test` | Four contracts (`:145,271,456,619`): canonical geometry/kinematics/polarity exactness, analytic Euler modes and invariances, radius and canonical-orientation invariances, reciprocal matching and fail-closed guards. Polarity is asserted *as unresolved*: convergent segments carry `polarity_candidate_status == "left_oceanic_only"` while `physical_polarity_status == "unknown_unresolved"`, `physical_polarity_source == "none"` and `physical_polarity_confidence == 0.0` (`:243-264`), and a missing opening crust state yields `"unresolved_missing_opening_crust_state"` (`:699-708`). |
| 7 | `magic_geo_crust_overlap_candidate_fate` | `magic_geo_crust_overlap_candidate_fate_test` | Six contracts (`:196,260,297,326,360,377`): sparse status precedence with a closing partition, priority of resolved physical evidence, mixed/conflicting evidence blocking the heuristic fallback, pair-wide (not per-fragment) heuristic unavailability and conflict, preservation of identity steps and tiny positive areas, and fail-closed handling of malformed inputs. |
| 8 | `magic_geo_crust_reservoir` | `magic_geo_crust_reservoir_test` | Six contracts (`:139,166,208,248,289,315`): exact mantle exhaustion closes; an empty surface can be explicitly reseeded; mantle depletion does not fan out returned origins; insufficient mantle rejects *without publishing*; age-only reason mass is rejected; the surface owner cap rejects without publishing. |
| 9 | `magic_geo_crust_reservoir_integration` | `magic_geo_crust_reservoir_integration_test` | Three contracts (`:103,162,174`). `schema_flags_and_empty_slab_are_truthful` pins the serialized counter-model's honesty flags: `model_type = "finite_three_reservoir_dry_rock_accounting_v1"`, `closed_three_reservoir_dry_rock_accounting: true`, and `physical_source_sink_resolved`, `material_provenance_resolved`, `subducted_slab_reservoir_resolved`, `mantle_origin_packets_homogenized`, `mantle_spatial_transport_resolved`, `operational_safety_limits_are_physical_flux_limits` all `false`, with `instantaneous_global_mantle_mixing_assumed: true`, caps `1024` / `1000000` / `1000000`, empty slab tables and `physical_basis_resolved: [false…]`. `accounting_history_is_thread_exact` requires byte-identical history at 1 and 4 threads. `capacity_scales_with_surface_area` requires the 6400 km / 3200 km capacity ratio to equal 4 within `2.0e-14`. |
| 10 | `magic_geo_sediment_partition` | `magic_geo_sediment_partition_test` | Three contracts (`:198,269,536`): synthetic invariants over valid/zero/invalid cases, synthetic interface transitions covering material and datum changes, and `generated_histories_reconstruct_and_are_thread_exact` — which also pins `per_cell_source_partition_audit_present: true` alongside `source_partition_audit_is_mass_claim: false` and `source_partition_audit_is_provenance_claim: false`, and requires identical output at 1 and 4 threads. |
| 11 | `magic_geo_native_api` | `magic_geo_native_api_test` (default env) | Eight contracts, dispatched from `main` (`:1564-1582`): `thread_configuration_is_generation_scoped` (`:1090`), `conversion_preserves_every_field` (`:117`), `public_api_is_usable` (`:217`), `geodesic_physics_uses_actual_mesh_size` (`:1132`), `half_turn_crust_shadow_accepts_fully_uncovered_destinations` (`:1242`), `concurrent_generation_sessions_are_isolated` (`:1203`), `backend_selection_fallback_and_opencl_parity` (`:742`), `cuda_backend_failure_and_parity` (`:969`). The two backend contracts branch on runtime availability rather than skipping: with `compute_backend = 1` they require `requested_backend`/`selected_backend` = `cpu`, `opencl_probe_performed`/`cuda_probe_performed` false, `*_capability_status = "not_probed"`, zero dispatch counts, `crust_transport_execution_backend = "cpu"`, and the shadow flags `crust_overlap_continuous_shadow_only: true` with `..._authoritative` and `..._result_used_for_state` false. When CUDA is unavailable, an explicit `compute_backend = 3` request must produce an error containing `explicit CUDA backend requested` — never a silent fallback. |
| 12 | `magic_geo_fibonacci_knn_reference` | the **same** `magic_geo_native_api_test` binary, re-registered with `ENVIRONMENT "MAGIC_GEO_VALIDATE_FIBONACCI_KNN=1"` (`CMakeLists.txt:470-474`) | `reference_scale_membership_area_classes_close` (`:1151-1201`), the intentionally expensive 4,096-cell reference check, kept as a separate CTest responsibility "instead of rerunning the complete API suite in the reference process" (`:1565-1571`). It generates seed `424242`, 4,096 cells, 14 plates, and requires `total_coverage_arrangement_fragment_count > 100000`, `total_coverage_membership_area_class_count > 4096`, class count `< fragments / 10`, `maximum_coverage_membership_area_class_count <= 32`, and on the class ledger `source_membership_resolved: true` with `connected_fragment_topology_resolved: false`. |
| 13 | `magic_geo_c_api_v1_client` | `magic_geo_c_api_v1_client_test` — registered **only** when `CMAKE_SIZEOF_VOID_P EQUAL 8` (`CMakeLists.txt:513`) | The frozen 64-bit C ABI. `cpp/tests/c_api_v1_layout.hpp` declares the v1 `CConfig` field list *independently of the public header* and `static_assert`s `sizeof(CConfig) == 304`, `alignof(CConfig) == 8`, and the exact type and `offsetof` of all 41 fields (`:63-71`). The client then calls `magic_geo_generate_json` and requires no `"error"`, `"schema_version":2`, the echoed name, `"planet_parameters":{"radius_km":6200`, `"requested_backend":"cpu"` and `"opencl_probe_performed":false` (`:58-64`). |
| (14) | `magic_geo_cuda_compute` | `magic_geo_cuda_compute_test` — registered **only** when `MAGIC_GEO_CUDA_ENABLED` (`CMakeLists.txt:475-512`) | See the dedicated subsection below. |

### Build composition of the native tests

| CTest test | Extra sources beyond the test TU | Links the shared library | `-ffp-contract=off` | Registration lines |
| --- | --- | --- | --- | --- |
| `magic_geo_initial_oceanic_age` | `cpp/src/engine/initial_oceanic_age.cpp` | no | yes | `CMakeLists.txt:224-244` |
| `magic_geo_oceanic_age_depth` | `cpp/src/engine/oceanic_age_depth.cpp` | no | yes | `:246-266` |
| `magic_geo_oceanic_age_depth_integration` | — | yes (+ `Threads::Threads`, `OpenMP::OpenMP_CXX` when found) | yes | `:268-296` |
| `magic_geo_crust_overlap_shadow` | `cpp/src/crust_overlap_shadow.cpp` | no | yes | `:298-318` |
| `magic_geo_serialization_roundtrip` | `cpp/src/engine/messagepack.cpp`, `cpp/src/engine/numeric_serialization.cpp` | no | **no** | `:320-336` |
| `magic_geo_plate_boundary_segments` | `cpp/src/engine/plate_boundary_segments.cpp` | no | yes | `:338-358` |
| `magic_geo_crust_overlap_candidate_fate` | `cpp/src/engine/crust_overlap_candidate_fate.cpp` | no | yes | `:360-380` |
| `magic_geo_crust_reservoir` | `cpp/src/engine/crust_reservoir.cpp` | no | yes | `:382-398` |
| `magic_geo_crust_reservoir_integration` | — | yes (+ Threads, OpenMP) | **no** | `:400-424` |
| `magic_geo_sediment_partition` | `cpp/src/engine/sediment_partition.cpp` | yes (+ Threads, OpenMP) | yes | `:426-457` |
| `magic_geo_native_api` / `magic_geo_fibonacci_knn_reference` | — | yes (+ Threads, OpenMP) | **no** | `:459-474` |
| `magic_geo_cuda_compute` | `cpp/src/cuda_compute.cu`, `cpp/src/crust_overlap_shadow.cpp` (+ `CUDAToolkit_INCLUDE_DIRS`) | no | yes on C++ TUs; CUDA TUs get `--fmad=false --ftz=false --prec-div=true --prec-sqrt=true -lineinfo` | `:475-512` |
| `magic_geo_c_api_v1_client` | — | yes | not applied | `:513-527` |

The `-ffp-contract=off` policy exists to keep FMA contraction from introducing avoidable backend drift; the CMake comment states that "cross-compiler/GPU parity is validated with numeric tolerances and physical invariants rather than byte hashes" (`CMakeLists.txt:134-136`). Four test targets — `magic_geo_serialization_roundtrip`, `magic_geo_crust_reservoir_integration`, `magic_geo_native_api`/`magic_geo_fibonacci_knn_reference` and `magic_geo_c_api_v1_client` — have no `-ffp-contract=off` block of their own. The flag is applied to the `magic_geo_native` target itself (`CMakeLists.txt:137-141`), so the three of those four that link the shared library still exercise a contraction-stable engine; only the test-side arithmetic in the test TU is unconstrained.

### The CUDA test and its skip code

`magic_geo_cuda_compute` is registered only when the CUDA ladder in `CMakeLists.txt:21-69` succeeds (NVIDIA `nvcc` ≥ 12.8 **and** `find_package(CUDAToolkit 12.8 QUIET)` found). It carries a single CTest property:

```cmake
add_test(NAME magic_geo_cuda_compute COMMAND magic_geo_cuda_compute_test)
set_tests_properties(
  magic_geo_cuda_compute
  PROPERTIES SKIP_RETURN_CODE 77
)
```

(`CMakeLists.txt:507-511`.) The executable itself decides. `cpp/tests/cuda_compute_test.cpp` constructs a `CudaComputeSession` and, if `!session.available()`, prints `CUDA kernel test skipped: <telemetry error>` and `return 77` — which CTest then reports as **Skipped**, not Failed. A compiled-but-GPU-less host therefore builds the CUDA test and reports it skipped rather than red. When a device *is* present the test asserts, among other things, that session construction does not change the caller's current CUDA device, bitwise equality against ordered CPU references for plate assignment and scalar/fused smoothing, exact telemetry dispatch counts (`plate_assignment_dispatch_count == 1`, `smoothing_kernel_dispatch_count == 10`, `batched_smoothing_kernel_dispatch_count == 5`, `crust_overlap_continuous_shadow_dispatch_count == 1`), `last_threads_per_block == 256`, and that an out-of-range explicit CUDA ordinal fails with a non-empty error.

## Optional extras and the skip matrix

Most skips are raised at **import time** (module level) by a `try: … except ImportError as exc: raise SkipTest(...)` guard, so the whole module is skipped as a unit. Five module-level guards work that way. The rest do not: one is raised inside a `setUpClass` (so it skips a single class, not the module), and four are raised inside individual test methods.

| Test module | Skips unless | Skip trigger | Source |
| --- | --- | --- | --- |
| `tests/test_debug_export.py` | `magic-geo[debug]` (`pyarrow.parquet` + `magic_geo.debug_export`) | module import | `:23-43` — `raise SkipTest(f"debug export tests require magic-geo[debug]: {exc}")` |
| `tests/test_debug_map_export.py` | `magic-geo[debug]` (`duckdb`, `magic_geo.debug_map_export`) | module import | `:17-63` |
| `tests/test_debug_map_export_parity.py` | `magic_geo.debug_map_export` importable | module import | `:8-11` |
| `tests/test_debug_server.py` | `magic-geo[debug]` (`pyarrow`, `pyarrow.ipc`, `pyarrow.parquet`, `fastapi`) | module import | `:21-28` |
| `tests/test_debug_rerun.py` | `rerun-sdk` — "an undeclared, optional visualisation extra" (comment at `:24`) | module import | `:22-25` |
| `tests/test_cli_export_serve.py` | `magic-geo[debug]` — only the class whose `setUpClass` builds a cache | `setUpClass`, and only if the CLI output contains `requires the optional debug dependencies`; any other failure is re-raised as `AssertionError` ("a real regression, not a reason to skip") | `:314-319` |
| `tests/test_web_jobs.py::DebugCachePublicationTests::test_debug_cache_validation_rejects_incomplete_exports` | `magic_geo.debug_export` importable | single test | `:1798-1802` |
| `tests/test_web_jobs.py` — two cancellation tests | POSIX (`os.name == "posix"`) | single tests | `:1410-1411`, `:1490-1491` — "process-group cancellation is asserted on POSIX only" |
| `tests/test_debug_export.py::…::test_unusable_output_locations_surface_the_os_error` | non-root user (`os.geteuid() != 0`) | single test | `:1164-1166` — "root bypasses directory permission bits" |

`rerun-sdk` is **not** declared in `pyproject.toml` under any extra — it is genuinely optional and undeclared.

The practical consequence: `pip install -e ".[test]"` alone silently reduces the effective suite by the debug-gated modules (`test_debug_export` 30, `test_debug_map_export` 73, `test_debug_map_export_parity` 4, `test_debug_server` 57 — 164 tests) plus `test_debug_rerun` (9) unless `rerun-sdk` is present. Install `.[test,debug]` when a change touches the exporters, the map export, the cache format, or the workbench.

## Contributor checklist before pushing

The README's instruction is direct: "Deselect them for a tight local loop; run everything before pushing" (`README.md:250-251`).

| # | Step | Command | When |
| ---: | --- | --- | --- |
| 1 | Install with the extras your change touches | `pip install -e ".[test,debug]"` | Once, and again after `pyproject.toml` changes. |
| 2 | Rebuild the native core if any `cpp/` file changed | `cmake --build build` | Any C++ change. The build stages `libmagic_geo_native.so` into `src/magic_geo/`, which is the library the Python suite loads. |
| 3 | Run the native suite | `ctest --test-dir build --output-on-failure` | Any C++ change. ~5 s — cheap enough to run always. |
| 4 | Verify the library loads | `magic-geo backend` | After any rebuild or reinstall. |
| 5 | Tight loop while developing | `python -m pytest -m "not slow" -x -q` | Every iteration. ~13 min. |
| 6 | Targeted slow-tier run if `validate` or any validator changed | `python -m pytest -m "slow" -k <slice>` | When the change touches `magic_geo/cli` validators or a record family the slow tier asserts. |
| 7 | **Full suite before pushing** | `python -m pytest` | Always, per `README.md:250-251`. ~29 min. |
| 8 | Branch coverage when adding or changing a validator | `python -m pytest --cov --cov-report=term-missing` (or `--cov-report=html`) | When you need to prove the new rejection arm is reached. ~2 h; check `BrPart` and the `N->M` arrows in `Missing`, not just `Cover`. |
| 9 | Regenerate the layer reference if layer docs changed | `node scripts/gen_layers_reference.mjs` | After `magic-geo export-debug` or after editing `src/magic_geo/debug_ui/layer_docs.js`. |

There is no automated CI in this repository to catch a skipped step: `.github/` does not exist, and there is no `Makefile`, `tox.ini` or `noxfile.py` target that chains these. Steps 3 and 7 are the two that cannot be substituted for each other — the Python suite never compiles or exercises the C++ unit contracts, and the CTest suite never touches the Python layer.

## Limitations and unresolved claims

- **The documented runtimes are not reproducible guarantees.** `~29 min`, `~13 min`, `~16 min`, `~2 h` and `~5 s` come from `README.md:238-268` on unspecified hardware with unspecified thread counts. The only figures independently measured for this page are the native suite's `5.3-5.4 sec` and the coverage totals (`47,166` statements / `17,110` branches), both on one CPU-only Linux host with one Python version; neither is a portable constant. The `21% of the tests but 54% of the runtime` split (`README.md:248-249`) is a documented observation; only the 20.5% test-count side of it was re-verified here.
- **Coverage cannot see the C++ core.** `libmagic_geo_native.so` never appears in any report (`README.md:256-257`). A Python coverage percentage is not evidence about native-core execution, and no native-side coverage instrumentation is configured anywhere in the tree.
- **Coverage cannot see assertion strength.** Branch coverage records that an arm ran, never that the test around it asserted anything specific. The slow tier documents exactly this gap for shared verdict lines: "the assertion still cannot name the branch" (`tests/test_validate_cli_natural_systems.py:34-37`).
- **Three `validate` checks are documented as unassertable through the CLI** in the natural-systems slice alone (`tests/test_validate_cli_natural_systems.py:44-61`): the fitted-Hack-relation raise path, a `None` zone family, and two shadowed cell-field conversion guards. Those branches are untested through the public command by construction, not by oversight.
- **The native suite asserts hedged flags, not physical truth.** `magic_geo_oceanic_age_depth_integration` requires twelve capability flags to stay `false` (`cpp/tests/oceanic_age_depth_integration_test.cpp:204-220`), `magic_geo_crust_reservoir_integration` requires `physical_source_sink_resolved`, `material_provenance_resolved`, `subducted_slab_reservoir_resolved`, `mantle_origin_packets_homogenized` and `mantle_spatial_transport_resolved` to stay `false`, and `magic_geo_plate_boundary_segments` requires `physical_polarity_status == "unknown_unresolved"` with zero confidence. **Subduction polarity, mass provenance, physical time calibration and absolute basement depth are unresolved in the model, and the tests exist to keep them declared unresolved** — passing them is evidence of honest bookkeeping, never of physical validity.
- **Accelerator parity is conditionally tested at best.** `magic_geo_native_api` branches on runtime availability: with no CUDA device it only asserts that an explicit CUDA request errors out rather than silently falling back (`cpp/tests/native_api_test.cpp:989-994`). `magic_geo_cuda_compute` is not even registered unless CUDA compiles, and skips with exit code 77 when no device is present. On a CPU-only host the suite provides **no device-run evidence**, and the README records the same limitation for the accelerator shadow at `README.md:347`: the bounded continuous-moment shadow "is reconciled against CPU CSR moments and discarded, but this host provides no device-run evidence, while geometry, coverage, membership classes, categories, production state, scientific state, and complete accelerator parity remain outside the shadow and CPU-authoritative".
- **The independent geometry replay is capped below reference scale.** `DEFAULT_MAX_CELL_COUNT = 1_024` (`src/magic_geo/crust_coverage_geometry_replay.py:33`), and the routine fixtures are 128/162 cells. `README.md:347` states plainly: "Scaling that independent pair discovery to the 4,096-cell reference remains a validation-evidence blocker."
- **Suite-level results are not all green, and the tests do not claim they are.** `README.md:234` records the checked-in geo-validation matrix at 19/21 internal and overall scenario policies, one fatal error (`earth_seed_3` ocean fraction `0.542985`, below the `0.55` earthlike gate), seven warning deviations, external empirical coverage complete at 22/22 with fit at 17/22, and the conclusion "Internal closure and replay therefore do not substitute for the remaining Earth-fit gaps." A green `pytest` run and a green `ctest` run do not imply a green validation matrix.
- **Per-process world caching changes what parallelism costs, and mutation of a shared world is unenforced.** `cached_world_readonly` returns the shared object and relies on caller discipline; nothing freezes it. A test that mutates it "corrupts every later test in the process" (`tests/support/worlds.py:7-8`) — the failure would surface as an unrelated later test failing, not as a message at the mutation site.
- **No static analysis gate exists.** There is no linter, formatter, type-checker or pre-commit configuration in the repository, so style and typing are not machine-enforced and this page does not claim otherwise.
- **The inventory groupings on this page are editorial.** The file-to-group assignment is a reading aid constructed for this page; nothing in the repository declares these groups. Per-module test counts and the group totals (summing to 1,868) were taken from `pytest --collect-only -q` on this checkout and will drift as tests are added.

## See also

- [Installation and Build](./02-installation-and-build.md) — prerequisites, CMake cache options, `BUILD_TESTING`, library staging, and the wheel ABI-symbol gate.
- [Native Engine (C++ Core)](./08-native-engine.md) — the translation units the CTest executables link against and the simulation/result/serialization boundary.
- [Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md) — backend selection, telemetry fields, and the parity claims the native API test conditionally exercises.
- [Validation](./12-validation.md) — the `validate` command whose every violation branch the slow tier drives.
- [Geo Validation Suite](./13-geo-validation-suite.md) — the scenario matrix, layer contracts and determinism reruns exercised by the geo-validation test group.
- [Calibration Against Real-Earth Data](./14-calibration.md) — the readers and target bundles exercised by `tests/support/shapefiles.py` and `tests/support/builders.py`.
- [Serialization and World Formats](./11-serialization.md) — the JSON/`.mgeo` round trips pinned by `magic_geo_serialization_roundtrip` and `tests/test_serialization.py`.
- [Python API](./07-python-api.md) — `generate_world`, the entry point behind every cached canonical world.
- [Debug Exports and Visualization](./16-debug-and-visualization.md) — the exporters gated behind the `debug` extra and `rerun-sdk`.
- [Web Workbench](./15-web-workbench.md) — the FastAPI server and job manager covered by the debug-gated test group.
- [Docker Deployment](./19-docker-deployment.md) — the builder stage that configures with `-DBUILD_TESTING=OFF`.
- [Troubleshooting and FAQ](./22-troubleshooting.md) — what to check when the native library fails to load or a test module skips unexpectedly.
