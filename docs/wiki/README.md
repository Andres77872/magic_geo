# magic-geo Wiki

`magic-geo` is a causal planet generator: a Python orchestration layer that owns configuration, validation and file output, wrapped around a C++20 simulation core (`magic_geo_native`) that is loaded through `ctypes` and does all of the mesh, tectonic, crust, climate, hydrologic, erosional, cryospheric, pedologic, biotic, resource and civilization work (`README.md:3-11`). One validated YAML document — `WorldConfig`, nine sections and 44 leaf properties (`src/magic_geo/config.py:458`) — is marshalled across a frozen C ABI, and the single JSON world document that comes back is then mutated by sixty-six Python enrichers called in a fixed order (`src/magic_geo/api.py:200-265`); the natural-systems-only path strips every civilization field first and runs forty-eight of them (`src/magic_geo/api.py:287-375`). Three equivalent front doors expose the same pipeline — fifteen CLI subcommands, the `magic_geo` Python package, and a local self-hosted web workbench started by `magic-geo serve` — and every one of them writes the same schema-2 world in either JSON or the versioned binary `.mgeo` container. The project's most unusual property is epistemic rather than computational: authoritative simulation state, non-authoritative audit shadows and counter-models, and explicitly unresolved physical claims are separated *in the serialized document itself*, so a world carries flags such as `authoritative_for_cell_state: false` (`cpp/src/engine/crust_reservoir_serialization.cpp:181`) and `physical_time_resolved: false` (`cpp/src/engine/process_serialization.cpp:159`) next to the numbers they qualify. This wiki documents all of it at field level, and nowhere upgrades a claim the source hedges.

## On this page

- [Start here](#start-here)
- [Reading paths](#reading-paths)
- [Contents](#contents)
- [How this wiki relates to docs/](#how-this-wiki-relates-to-docs)
- [Conventions](#conventions)
- [See also](#see-also)

## Start here

If you have never run `magic-geo`, read these four pages in order. They take you from "what is this" to a generated, rendered, validated planet on your own machine.

| Page | What it covers |
| --- | --- |
| [Project Overview](./01-overview.md) | What the generator is, the causal-generation philosophy, the three entry points, the two generation scopes, and how to read any output honestly. |
| [Installation and Build](./02-installation-and-build.md) | Python install, the CMake build of the native core, the staging rule that puts the shared library inside the package, and `magic-geo backend` verification. |
| [Quickstart](./03-quickstart.md) | A hands-on first hour: create a config, generate a planet, inspect every artifact, render two maps, run the consistency gate, and open the workbench. |
| [Glossary](./21-glossary.md) | Every domain term with the source location that implements or serializes it — the fastest way to decode an unfamiliar field name in a world document. |

The shortest possible path from a clean checkout to a world, taken verbatim from `README.md:22-30`:

```bash
python -m pip install -e .   # Python CLI + library (editable)
cmake -S . -B build          # configure the C++ simulation core
cmake --build build          # stages libmagic_geo_native.so into src/magic_geo/
magic-geo backend            # verify the native core loads (prints backend info)
magic-geo generate --config configs/earthlike_seed.yaml --output runs/earthlike/world.json --summary runs/earthlike/summary.md --cells-csv runs/earthlike/cells.csv
magic-geo render --world runs/earthlike/world.json --output runs/earthlike/world.svg --projection mollweide --labels
```

For a fast smoke run at reduced mesh resolution (`README.md:35`):

```bash
magic-geo generate --config configs/earthlike_seed.yaml --cells 512 --output /tmp/world.json
```

## Reading paths

Four ordered sequences through the same 42 pages, one per audience. Each is meant to be read in order; later entries assume the earlier ones.

### Worldbuilder — you want interesting, coherent planets

1. [Quickstart](./03-quickstart.md) — get one planet on disk and learn what each artifact is.
2. [Example Seeds and Presets](./20-seed-gallery.md) — nine complete premises you can run unmodified, plus the audited outcomes and known failure boundaries of each.
3. [Configuration Reference](./05-configuration-reference.md) — all 44 properties, what each one physically means, and which stage consumes it.
4. [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md) — where relief actually comes from, so you can predict what a config change does to the map.
5. [Oceans, Currents and Coasts](./features/oceans-and-coasts.md) — how a configured water volume becomes a coastline, and why `ocean_fraction_target` is not the sea-level control.
6. [Climate and Atmosphere](./features/climate-and-atmosphere.md) — the twelve-month climatology every downstream habitability question depends on.
7. [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) — rivers, lakes, watersheds and the water budget that must close.
8. [Biomes, Ecosystems and Disturbance](./features/biomes-and-ecology.md) — the biome cascade and the full class table you will be reading off the map.
9. [Settlements, Routes and Corridors](./features/settlements-and-routes.md) — why a town appears where it appears.
10. [Political, Cultural and Linguistic Geography](./features/political-and-cultural-geography.md) — regions, borders, cultures, languages, sacred sites and ruins.
11. [History, Demography, Economy and Markets](./features/history-demography-and-economy.md) — eras, events, dynasties, population and trade.
12. [Rendering and Map Output](./17-rendering.md) — SVG and raster output, projections, palettes, and what these renderers deliberately are not.
13. [Web Workbench](./15-web-workbench.md) — drive all of the above from a browser instead of a shell.

### Integrator — you want magic-geo inside your own system

1. [Installation and Build](./02-installation-and-build.md) — build, staging, extras, and the packaging gates that govern wheels.
2. [Python API](./07-python-api.md) — the exported package surface, config helpers, the generation entry points, and end-to-end recipes.
3. [Configuration Reference](./05-configuration-reference.md) — the schema you will be constructing programmatically, plus the JSON Schema export and `--set` override grammar.
4. [World Document Schema](./10-world-schema.md) — the field-level contract of everything you will parse.
5. [Serialization and World Formats](./11-serialization.md) — JSON vs `.mgeo`, the key-order and precision contract, and the container's fail-closed limits.
6. [CLI Reference](./06-cli-reference.md) — the fifteen subcommands, their exact options, artifacts and exit codes, for shelling out or scripting.
7. [Debug Exports and Visualization](./16-debug-and-visualization.md) — the columnar debug cache, if you want Parquet/Arrow rather than one large document.
8. [Web Workbench](./15-web-workbench.md) — the REST API at `/api/docs`, the typed job queue, and the security model you must respect.
9. [Docker Deployment](./19-docker-deployment.md) — the all-in-one image, the `.env` surface, and the bind-mount persistence model.
10. [Troubleshooting and FAQ](./22-troubleshooting.md) — every failure mode by layer, with the literal error strings.

### Contributor — you want to change the code

1. [Architecture](./04-architecture.md) — the four layers, the ordered stage sequences on both sides of the boundary, and the determinism contract you must preserve.
2. [Native Engine (C++ Core)](./08-native-engine.md) — directory layout, every translation unit, the result/serialization boundary, the complete C ABI, and the rules for adding a stage.
3. [Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md) — the four selections, the truthfulness rules, deferred automatic selection, and what an accelerator is and is not allowed to decide.
4. [Configuration Reference](./05-configuration-reference.md) — the schema, its bounds, and the config-to-native marshaling boundary.
5. [World Document Schema](./10-world-schema.md) — what your change must keep emitting, in what order.
6. [Serialization and World Formats](./11-serialization.md) — the quantization boundaries the Python replay validators depend on.
7. [Validation](./12-validation.md) — the two gates your change has to survive, and the replay-validator families.
8. [Testing and Quality Gates](./18-testing.md) — the Python and CTest suites, the `slow` marker, the coverage caveats, and the pre-push checklist.
9. [Troubleshooting and FAQ](./22-troubleshooting.md) — the guards and assertions you will trip while iterating.
10. [Glossary](./21-glossary.md) — the vocabulary used in code review and in the model contract blocks.

### Scientist auditing the physics — you want to know what is actually claimed

1. [Project Overview](./01-overview.md) — read the epistemic contract section first; it defines the separation everything else depends on.
2. [Mesh and Geometry](./features/mesh-and-geometry.md) — the finite-volume substrate that makes every later conservation audit meaningful.
3. [Tectonics and Plates](./features/tectonics-and-plates.md) — an explicitly kinematic, procedural plate model: uncalibrated physical time, unresolved subduction polarity, nominal initial seafloor ages.
4. [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md) — exact directed segment geometry and direct unsmoothed Euler kinematics, with subducting/overriding recorded only as *candidates*.
5. [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) — the exact spherical forward-overlap operator, why it stays CPU-authoritative, and the discarded accelerator shadow.
6. [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) — two mass-like bookkeeping structures that are mechanically non-authoritative and enumerate their own non-claims as explicit `false` flags.
7. [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md) — the isostasy relation, the continuity-adjusted Parsons–Sclater curve and its explicit non-claims, and the exact per-step decomposition.
8. [Oceans, Currents and Coasts](./features/oceans-and-coasts.md) — the volume-constrained sea-level solver and the one-elevation-per-cell limitation that colours the whole marine domain.
9. [Climate and Atmosphere](./features/climate-and-atmosphere.md) — a deterministic equilibrium diagnostic, not a transient solver, with `mass_conserving_atmosphere: false`.
10. [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) — the closing annual water budget, priority-flood depression handling, and the authoritative/diagnostic split.
11. [Groundwater, Aquifers and Karst](./features/groundwater-and-karst.md) — four annual diagnostics with no transient storage and no feedback into surface routing.
12. [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) — the coupled transition engine and the nominal geological coordinate it runs on.
13. [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) — the canonical two-field interface, the checked mutation primitives, and the replay tolerance model.
14. [Cryosphere: Ice Sheets, Glaciers and Permafrost](./features/cryosphere.md) — a terminal endpoint operator plus post-hoc diagnostics, with no ice-dynamics solver.
15. [Soils and Weathering](./features/soils.md) — three native fields with no conservation closure, and no chemical weathering anywhere in the codebase.
16. [Resources and Economic Geology](./features/resources-and-economic-geology.md) — bounded-index plausible-pattern generation; no grade, tonnage or geochemical transport.
17. [Validation](./12-validation.md) — what a passing report is: contract integrity, never empirical realism.
18. [Geo Validation Suite](./13-geo-validation-suite.md) — the multi-scenario tier, the paired directional-response gates, and the currently failing external metrics reported as the repository reports them.
19. [Calibration Against Real-Earth Data](./14-calibration.md) — the only subsystem that compares a world to measurements of Earth, and why its verdict is separate from every internal one.

## Contents

Every page in this wiki, once. Forty-two pages: four getting-started, ten reference, twenty feature-domain pages (the domain index plus nineteen domains), four quality and validation, four tooling and deployment.

### Getting started

| Page | What it covers |
| --- | --- |
| [01 — Project Overview](./01-overview.md) | What `magic-geo` is, the causal-generation philosophy, the three equivalent entry points, the full-world vs `--geo-only` scopes, the feature-domain map, and the epistemic contract that separates authoritative state from shadows and unresolved claims. |
| [02 — Installation and Build](./02-installation-and-build.md) | Every prerequisite, every CMake cache option, the rule that stages the shared library into the Python package directory, `magic-geo backend` output, optional-dependency extras, the CUDA/OpenMP detection ladders, and the packaging gates in `setup.py`. |
| [03 — Quickstart](./03-quickstart.md) | A guided first hour: config creation, a full planet, every emitted artifact, two rendered maps, the consistency gate, the geo-only variant, and the local web workbench — with each default quoted from the source that defines it. |
| [22 — Troubleshooting and FAQ](./22-troubleshooting.md) | Failure modes organised by the layer that raises them — CMake/native build, the `ctypes` boundary, Pydantic config, C++ parameter and pipeline guards, backend selection, serialization, validation, the workbench and its job manager, the debug cache, calibration data, and the test suites — with literal error strings. |

### Reference

| Page | What it covers |
| --- | --- |
| [04 — Architecture](./04-architecture.md) | The four layers (validated YAML, native shared library, `ctypes` marshalling, Python enrichment), the exact ordered stage sequences on both sides, why that ordering is load-bearing, and the determinism contract, cited to file and line throughout. |
| [05 — Configuration Reference](./05-configuration-reference.md) | All nine sections and 44 leaf properties of `WorldConfig` with real types, defaults and Pydantic bounds; what each means physically and which stage consumes it; plus profiles, the `--set` override grammar, YAML strictness, JSON Schema export, atomic validated writes, and the config-to-native boundary. |
| [06 — CLI Reference](./06-cli-reference.md) | All fifteen subcommands of the single Typer application: synopsis, complete option tables, exact artifacts, exit-code semantics, worked examples, and end-to-end recipes chaining them together. |
| [07 — Python API](./07-python-api.md) | Embedding `magic-geo` as a library: the exported package surface, every configuration helper, the generation entry points, the shape of the returned world dictionary, JSON/`.mgeo` serialization, the `magic_geo.io` writers, direct enricher invocation and its ordering constraints, backend introspection, and the error types. |
| [08 — Native Engine (C++ Core)](./08-native-engine.md) | The native side in full: directory layout, every translation unit, the simulation/result/serialization boundary, the exact pipeline stage order, the complete C ABI including struct field offsets, the `ctypes` mirror, thread and visibility policy, the native test suite, and the rules for adding a stage. |
| [09 — Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md) | The four backend selections and where they are configured; the truthfulness rules (`cpu` never probes a runtime, explicit accelerators never silently degrade); deferred automatic selection with its thresholds and fallback chain; and the separately named crust-transport shadow reduction whose result is validated and then discarded. |
| [10 — World Document Schema](./10-world-schema.md) | The field-level reference for a generated world: the fixed top-level key emission order, the `summary` object, the per-cell record, the nested entity families, and the declarative model/contract sections whose explicit `false` flags record which physical claims the project does *not* make. |
| [11 — Serialization and World Formats](./11-serialization.md) | Format selection, the JSON key-order and precision contract, the versioned `.mgeo` container with its checksummed header and fail-closed limits, the strict bounded-depth C++ JSON-to-MessagePack transcoder, the native binary transfer ABI, and how to reproduce the checked-in benchmark. |
| [20 — Example Seeds and Presets](./20-seed-gallery.md) | The nine presets in `configs/seeds/` plus `configs/earthlike_seed.yaml`: every property of every preset, the configuration-level physical forcings derived from those numbers, the audited outcomes, and the known failure boundaries as the repository records them. |
| [21 — Glossary](./21-glossary.md) | Every domain term a reader meets in the codebase, with the exact source location where it is implemented or serialized and a link to the page that covers it in depth, preserving the authoritative / non-authoritative / unresolved separation term by term. |

### Feature domains

Ordered roughly by causal dependency: each layer reads the state the layer above it produced.

| Page | What it covers |
| --- | --- |
| [Feature Domains index](./features/README.md) | The domain-index page for this section: the implemented causal order with the pipeline call sites that fix it, the one-line index of all nineteen domain pages, what the `--geo-only` scope removes, and the limitations that apply across every domain rather than to any single one. |
| [Mesh and Geometry](./features/mesh-and-geometry.md) | The spherical finite-volume cell mesh: both native backends, how each one's control volumes are computed and certified, how the geometry is re-derived and closure-checked from the serialized document, and the three deliberately distinct neighbor structures plus two Python-side spatial indices. |
| [Tectonics and Plates](./features/tectonics-and-plates.md) | Plate seeding, nearest-rotated-pole cell assignment, boundary forcing from relative Euler velocities and its smoothing, crust state and initial relief, and the per-iteration Rodrigues rotation / reassignment / reclassification / rule-application / `plate_motion_history` cycle. Explicitly kinematic and procedural. |
| [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md) | The exact, directed, per-step record of every cross-plate reciprocal control-volume segment: canonical orientation rules, segment identity, fail-closed construction guards, same-step crust witnesses, and the subducting/overriding **candidate** pair that is deliberately not a polarity claim. |
| [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) | The exact spherical forward-overlap operator — rigid rotation, gnomonic clipping, destination-major CSR of positive overlap areas — why the geometry stays CPU-authoritative, and the coverage-multiplicity, membership-area-class and candidate-fate diagnostics built on it. |
| [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) | The persistent sparse dry-rock mass shadow and the finite three-reservoir accounting counter-model: packet layout, canonical keys, allocation arithmetic, forward-error bounds, transaction ordering, tie-breaks, operational caps, the serialized schema, and the Python replay validators. Both are non-authoritative by construction. |
| [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md) | The crust equilibrium relation, the continuity-adjusted Parsons–Sclater age-depth curve with its exact branch forms and explicit non-claims, the four-operand per-step decomposition and which single term is clamped, the binary64 round-trip contract, the sea-level solver and its datum-shift primitive, and the replay validator. |
| [Oceans, Currents and Coasts](./features/oceans-and-coasts.md) | The volume-constrained connectivity sea-level solver, what `ocean_fraction_target` actually does, the `sea_level_model` contract block, shelf classification, marine regions, chokepoints, currents, coastal features, reefs and port sites — all under one elevation per cell. |
| [Climate and Atmosphere](./features/climate-and-atmosphere.md) | The deterministic equilibrium climatology: the planetary parameter snapshot, the fixed twelve-month structure, base temperature and area-mean normalization, latitude-band circulation kernels, and four Python enrichers adding continentality, Köppen–Geiger classification, a zero-dimensional radiation budget and plausibility checks. |
| [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) | The native authoritative tier — a per-cell annual water budget that must close, priority-flood depression solve, drainage graph and flow accumulation, percentile river extraction, lake basins and watersheds — plus the non-authoritative Python tier of channel geometry, Manning hydraulics, wetlands, navigability and reorganization trajectories. |
| [Groundwater, Aquifers and Karst](./features/groundwater-and-karst.md) | Four Python enrichers over the native water budget: a mass-conserving recharge partition, a diagnostic aquifer resource classifier, descending-head lateral routing that closes locally per cell, and a karst dissolution classifier — every formula, threshold, emitted record and cell field. |
| [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) | The coupled tectonics–climate–hydrology–erosion transition engine: the maturation coordinator, the nominal timestep, exactly which responses are timestep-scaled, the stage and iteration model, and the one checked material-update primitive that commits all three tendencies per cell. |
| [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) | The canonical bedrock-surface / mobile-thickness interface, the checked mutation primitives, the three transports plus numeric-breach correction, the fluvial routing snapshot and its replay, the alluvium-vs-bedrock source partition, the diagnostic stratigraphy enrichers, and the decimal-quantization tolerance model. |
| [Cryosphere: Ice Sheets, Glaciers and Permafrost](./features/cryosphere.md) | The terminal zero-duration native cryosphere operator and its second recomputation after stabilization, snow/ice mass balance inputs, bulk glacial sediment transfer, and the post-hoc Python diagnostics for ice-sheet histories, stability trajectories, flowlines, permafrost classes and glacial landforms. |
| [Soils and Weathering](./features/soils.md) | The three native per-cell soil fields, the inputs the native stage consumes, the classification vocabulary, and the separate post-hoc Python reconstruction of texture, drainage, pH, organic matter, salinity, erodibility, profile development, horizons and pedogenesis trajectories. |
| [Biomes, Ecosystems and Disturbance](./features/biomes-and-ecology.md) | The authoritative native biome enum from a deterministic threshold cascade, the landform override on floodplains and deltas, the full biome class table with envelopes, and the post-hoc Python layer of biome diagnostics, ecotones, productivity, species ranges, wildfire disturbance and realism checks. |
| [Resources and Economic Geology](./features/resources-and-economic-geology.md) | The native causal chain that puts a resource on a cell, then six Python enrichers — resource dynamics, ore genesis, sedimentary resource systems, petroleum migration, commodity resources, land-use zones — with their record schemas, exact scoring formulas, thresholds, and a commodity-to-precondition cross-reference. |
| [Settlements, Routes and Corridors](./features/settlements-and-routes.md) | The native `settlement_score` field and every term feeding it, the greedy separated site selector, settlement type classification, the endpoint-ranked route network, and the Python enrichers for port sites, feature-weighted Dijkstra route corridors and natural frontiers. Absent entirely from geo-only worlds. |
| [Political, Cultural and Linguistic Geography](./features/political-and-cultural-geography.md) | Political region formation and its record fields, the border segment model, trade flows, cultures, language regions, sacred areas, ruins, era-scaled territorial snapshots, the declaration-only Python model records, the one genuinely generative phonology enricher, and the four downstream consumers. |
| [History, Demography, Economy and Markets](./features/history-demography-and-economy.md) | The fixed four-era partition and seven-type event vocabulary, the native population-region capacity model, the border-pair conflict model, the dynastic lineage chain, and the six Python enrichers projecting those records into population, economy, agent, logistics, campaign and market-clearing trajectories. |

### Quality and validation

| Page | What it covers |
| --- | --- |
| [12 — Validation](./12-validation.md) | The two independent gates: `validate` (monolithic pass/fail consistency over the entire document, civilization included) and `validate-geo` (structured machine-readable audit restricted to natural geography, emitting per-check records, a metric surface, and the 14-layer contract audit of `src/magic_geo/geo_layer_contracts.py:26-314`). |
| [13 — Geo Validation Suite](./13-geo-validation-suite.md) | The multi-scenario tier driven by `magic-geo validate-geo-suite`: the matrix file schema, per-scenario metric envelopes, cross-scenario paired directional-response gates, the determinism rerun, and the checksum-pinned Earth-reference empirical bundle — with the internal and external verdicts kept separate. |
| [14 — Calibration Against Real-Earth Data](./14-calibration.md) | The one subsystem that compares a generated world to measurements of the real Earth: `derive-targets`, `calibrate` and `calibrate-ensemble`, the source-config schema, the supported datasets and their fetch scripts and provenance, and why every shipped tolerance is a model-fit tolerance rather than a confidence interval. |
| [18 — Testing and Quality Gates](./18-testing.md) | Both suites: the `pytest` suite over configuration, the `ctypes` boundary, every replay validator, the CLI, the exporters and the workbench; and the CTest-registered native suite over the simulation core's algorithmic and ABI contracts — plus the `slow` marker, the coverage caveats, `tests/support/`, the optional-extra skip matrix, and a pre-push checklist. |

### Tooling and deployment

| Page | What it covers |
| --- | --- |
| [15 — Web Workbench](./15-web-workbench.md) | The local single-user browser application served by `magic-geo serve`: workspace/host/port resolution, cache discovery, the typed background job queue, the GPU layer explorer, the documented REST API at `/api/docs`, and the trusted-local security model (no authentication, no authorization, no per-user isolation, no TLS). |
| [16 — Debug Exports and Visualization](./16-debug-and-visualization.md) | The three offline export paths — `export-debug` (Parquet tables, JSONL sidecars, GPU-ready mesh buffers, optional ParaView `.vtu`), `export-debug-map` (browserless PNG plus prompt), `export-rerun` (`.rrd`) — with manifest field tables, every Parquet column schema, binary buffer layouts, layer addressing, and the default-path rules that differ between CLI and browser. |
| [17 — Rendering and Map Output](./17-rendering.md) | The two dependency-free world renderers `render` (SVG) and `render-raster` (PPM) plus the separate debug-cache PNG path: every option, projection, palette entry, styling rule and output-file structure. All three are symbolic diagnostic renderers, not cartographic products. |
| [19 — Docker Deployment](./19-docker-deployment.md) | The all-in-one image walked line by line: the builder stage that compiles the native core and ABI-checks a platform wheel, the slim runtime stage, the `.env` and Compose surface with who actually consumes each variable, the bind-mount persistence model, and exactly which GPU claims are backed by the repository. |

## How this wiki relates to docs/

This wiki is the structured, cross-linked entry surface. The documents directly under `docs/` predate it and are kept because each carries something the wiki deliberately does not reproduce: raw measurement transcripts, host-specific engineering evidence, design rationale, review findings, or an auto-generated catalog. Several are explicitly marked historical or superseded by their own authors; where that is the case it is noted below, and you should read them for the analysis rather than for current status.

| Document | What it adds beyond the wiki |
| --- | --- |
| [`docs/configuration_helpers.md`](../configuration_helpers.md) | The task-oriented guide to creating, inspecting, validating, overriding, serializing and saving configuration — the how-to companion to the wiki's property-by-property reference. |
| [`docs/configuration_reference.md`](../configuration_reference.md) | The original per-property reference, including each property's status and gaps notes and its cross-links into the layers reference. |
| [`docs/cuda_rtx5090_optimization.md`](../cuda_rtx5090_optimization.md) | The CUDA implementation record and RTX 5090 calibration: build, kernel, parity, performance, sanitizer and telemetry evidence, declared by the document itself as host-specific engineering evidence rather than universal NVIDIA performance claims. |
| [`docs/debugger.md`](../debugger.md) | The web workbench architecture document — how the server, the job layer and the GPU layer explorer are put together, rather than how to operate them. |
| [`docs/debug_ui_guide.md`](../debug_ui_guide.md) | The end-user UI walkthrough of the workbench: world creation, operations, exported-data browsing, the Three.js map debugger, backend telemetry and live API docs. |
| [`docs/deep_plan.md`](../deep_plan.md) | The implementation plan that executes the `r1.md` review as a CLI-first causal planet generator — the design intent and scope decisions behind the architecture. |
| [`docs/docker_deployment.md`](../docker_deployment.md) | The full deployment guide: `.env` reference, persistence model, GPU notes, and how to expose the unauthenticated workbench safely. |
| [`docs/example_seed_gallery.md`](../example_seed_gallery.md) | The research basis behind each of the nine presets, their intended outcomes and limitations, and the seed-selection workflow. |
| [`docs/geo_generation_maturation_deep_audit.md`](../geo_generation_maturation_deep_audit.md) | The dated scientific audit of natural generation and maturation: the evidence, the scientific interpretation, the layer-by-layer limitations, and the staged definition of done. Civilization layers are out of scope. |
| [`docs/gpu_simulation_audit.md`](../gpu_simulation_audit.md) | Marked by its own header as historical/superseded: preserves the original CPU/OpenCL pipeline audit and the broader determinism analysis, with its backend inventory, selection policy, thresholds and benchmarks superseded by the RTX 5090 audit. |
| [`docs/gui_debug_visualization_research.md`](../gui_debug_visualization_research.md) | Marked as a superseded historical snapshot: the research that led to the debugger, retained for the option analysis. Its codebase measurements are stated to have drifted. |
| [`docs/layers_pipeline_review.md`](../layers_pipeline_review.md) | Marked as a historical snapshot: pipeline review findings with fixed/open marks that describe the tree as of its date. Read for the analysis, not for status. |
| [`docs/layers_reference.md`](../layers_reference.md) | Auto-generated by `scripts/gen_layers_reference.mjs` from the same `layer_docs.js` that powers the in-app docs helper, run over a real `export-debug` manifest — the one document that cannot drift from what the UI shows. |
| [`docs/layers_review.md`](../layers_review.md) | Marked as a historical snapshot: the deep review of the debugger layer pipeline. Its `file:line` anchors are stated to no longer resolve to the quoted code. |
| [`docs/r1_status_audit.md`](../r1_status_audit.md) | Marked as a historical v32/v2 measurement snapshot and explicitly *not* the current transport contract: preserves the exact commands, values, hashes and interpretation measured against the older transport model. |
| [`docs/serialization_review.md`](../serialization_review.md) | The deep review behind the optimized world format: framing, compatibility, safety limits, native transfer APIs, and reproducible measurements. |
| [`docs/web_refactor_review.md`](../web_refactor_review.md) | The repository evidence that drove the workbench refactor, the contracts that were implemented as a result, and the limitations that remain. |

## Conventions

The vocabulary below is not stylistic. It mirrors flags that the engine and the enrichers actually serialize into every world document, and this wiki uses the words with exactly the meaning the source gives them.

| Term | What it means here | Where the source establishes it |
| --- | --- | --- |
| **Authoritative** | The value *is* the simulation state. Downstream stages read it, replay validators reconstruct it, and changing it changes the world. Canonical geometric fields such as the bedrock surface and mobile-sediment thickness are authoritative; the terrain surface is derived from them, never independently written. | `cpp/src/engine/world_serialization.cpp:42` (canonical emission), [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) |
| **Non-authoritative** | A parallel bookkeeping structure — a shadow, a counter-model, or an audit ledger — that is computed alongside authoritative state, made replayable, and then *not* allowed to influence cell state. Its own metadata says so: `authoritative_for_cell_state` is emitted as `false`. | `cpp/src/engine/crust_reservoir_serialization.cpp:181`, `cpp/src/engine/process_serialization.cpp:206` |
| **Shadow** | A specific kind of non-authoritative product: a second computation of something already computed authoritatively, kept for audit and then discarded or reconciled. The accelerator crust-transport reduction is a shadow whose result is validated against CPU bounds and thrown away; the forward spherical overlap stays on the CPU. | [Compute Backends](./09-compute-backends.md), [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) |
| **Counter-model** | A closed numerical accounting system built over an authoritative process to make its implied changes countable, without claiming the physics those changes would imply. The finite three-reservoir dry-rock accounting is the canonical example: its arithmetic closes, and it still emits `physical_source_sink_resolved: false` and `global_crust_cycle_mass_conservation_resolved: false`. | `cpp/src/engine/crust_reservoir_serialization.cpp:182,186` |
| **Diagnostic** | A derived index, classification or trajectory that reads final state and writes a new field, with no feedback into the simulation. Most Python enrichers are diagnostics; many are also `posthoc`, meaning they reconstruct a plausible history from a single final state rather than observing one. | `src/magic_geo/api.py:200-265`, [Architecture](./04-architecture.md) |
| **Unresolved** | A physical claim the project explicitly declines to make, emitted as a `*_resolved: false` flag next to the numbers a reader might otherwise over-interpret. Recurring examples include `physical_time_resolved`, `material_provenance_resolved`, `subducted_slab_reservoir_resolved`, `mass_conserving_atmosphere` and `transient_climate_resolved`. | `cpp/src/engine/process_serialization.cpp:159`, `:443-446`; `cpp/src/engine/crust_reservoir_serialization.cpp:183-185` |
| **Contract passed** | The verdict a validation gate actually returns: required artifacts exist, every declared validator domain supplied evidence, upstream layer contracts passed, and every fatal check assigned to the layer passed. The source states it is "deliberately *not* a claim that the model is empirically realistic". | `src/magic_geo/geo_layer_contracts.py:8-12` |
| **Empirical fit** | A separate, external verdict produced only by the calibration path against checksum-pinned real-Earth datasets. "Earth empirical fit remains a separate calibration verdict from internal contract integrity." | `src/magic_geo/geo_validation.py:40` |
| **Nominal** | A quantity expressed on an uncalibrated coordinate — most often the nominal Ma timestep and the derived nominal plate-motion rates. A nominal rate is a bookkeeping scale, not an observed or calibrated physical rate. | [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md), [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md) |
| **Candidate** | A role assigned by a heuristic that the source refuses to promote to a fact. The boundary ledger records a candidate subducting side and a candidate overriding side while leaving the physical fields `unknown` with source `none` and zero confidence. | [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md) |

Two further rules apply throughout:

- **Tables cite source paths.** Every table that enumerates parameters, fields, flags, thresholds or outputs identifies where the value lives, as an inline code citation of the form `src/magic_geo/config.py:458` or `cpp/src/engine/tectonics.cpp`. If a page states a number, you can open the cited file and see it.
- **Unverified means omitted or labelled.** Where a page could not confirm something from the source it says so explicitly rather than filling the gap, and observed runtime numbers that came from one local run are labelled as single local observations rather than presented as project benchmarks.

## See also

- [Project Overview](./01-overview.md) — the conceptual entry point, and the fullest statement of the epistemic contract summarised above.
- [Glossary](./21-glossary.md) — every term in the codebase, with its implementing source location.
- [Architecture](./04-architecture.md) — how the four layers and their ordered stages fit together.
- [World Document Schema](./10-world-schema.md) — the field-level contract every page ultimately describes.
- [Validation](./12-validation.md) — what a green verdict does and does not assert.
