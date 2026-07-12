# GUI Visualization & Deep-Debugging Research

> **Historical snapshot — superseded.** This is the research document that led to the debugger;
> the recommendation has since been implemented (see [debugger.md](debugger.md) and
> [debug_ui_guide.md](debug_ui_guide.md)). Codebase measurements below describe the tree as of the
> date line and have drifted: `compute.backend` is now marshaled to the engine and includes `cuda`
> (see [cuda_rtx5090_optimization.md](cuda_rtx5090_optimization.md)), and the CLI has grown past
> nine commands. Read it for the rationale, not for current facts.

Deep review of the magic-geo codebase plus researched options for adding a GUI mechanism to
visualize and deep-debug generated worlds, while keeping the CLI as the generation interface.

- Date: 2026-07-10
- Method: 6 parallel subsystem code reviews (native engine, Python orchestration, CLI/validation,
  data model, rendering, tests/calibration) + 6 parallel technology research passes with live web
  sources (web 3D globe stacks, Python scientific viz, dashboard frameworks, desktop-native GUIs,
  prior art, data-serving architecture) + synthesis. All measurements below were taken against the
  shipped library and the checked-in sample world on this machine.
- Constraint honored: the CLI remains the only generation interface; the GUI is a
  visualization/debugging layer over generated artifacts. This document proposes no code changes;
  it is research and a recommendation.

---

## TL;DR — the recommendation

**Build a local-web debugger: `magic-geo export-debug` (Parquet/JSONL debug cache) +
`magic-geo serve` (FastAPI + native DuckDB, Arrow IPC) + a custom three.js globe frontend in the
system browser.** Precede it with two nearly-free accelerators: a one-day **Rerun** exporter
(instant professional stage-scrubbing) and a **`.vtu`-per-stage + `.pvd` export** (ParaView becomes
a zero-code heavyweight companion viewer). Fix the un-optimized Release build first — it is a
one-line change with a likely multi-fold speedup.

The decisive facts:

1. **~90% of the data a stage-scrubbing, per-cell-drill-down debugger needs already exists in
   `world.json`.** The engine serializes complete per-stage provenance ledgers (17 full per-cell
   arrays per water-budget recompute, per-cell plate/crust provenance per motion step, per-edge
   sediment transfer ledgers, per-event depression-fill records with breach paths). No engine
   changes are required for a v1 post-hoc debugger.
2. **The blocking constraint is the format, not the data.** One pretty-printed JSON blob
   (75.6 MB at 4,096 cells; 1.2 GB at 65k cells) that every consumer `json.loads` wholesale makes
   interactive access impossible above ~16k cells. Any GUI, regardless of frontend, needs a
   columnar cache layer. Once that (Parquet + DuckDB) exists, Arrow-column-to-GPU is the natural
   continuation — which is what tilts the frontend decision toward the web stack.
3. **Every serious prior-art spherical-Voronoi planet viewer (Tectonics.js, Red Blob Games'
   1843-planet-generation, Experilous) independently converged on three.js/raw WebGL.** None chose
   a geo framework (deck.gl GlobeView is still officially experimental and lon/lat-only; CesiumJS
   is Earth-locked; globe.gl collapses at ~20k polygons) and none chose VTK-in-Qt.

Runner-up (pick it only if writing any JavaScript is a dealbreaker): **PySide6 + pyvistaqt**, a
~300-line first prototype living in-process with the validators — but it caps out on scrub
smoothness, provenance browsing, and depends on a small glue library.

---

## Part 1 — Deep project review

### 1.1 Architecture as verified

```text
YAML seed config
  → Pydantic v2 WorldConfig (config.py)
  → 41-field positional ctypes struct (native.py:15-58)
  → ONE blocking native call: magic_geo_generate_json (c_api.cpp)
      cpp/src/engine.cpp — 14,278 lines, single translation unit, 199 functions,
      Cell struct with ~160 fields, hand-rolled JSON of 45 top-level sections
  → json.loads of the returned blob (native.py:85-97)
  → 66 sequential in-place enrichment passes (api.py:81-151)
  → world.json (json.dumps indent=2 sort_keys=True), cells.csv (407 columns), summary.md
```

Measured on this machine (shipped `.so`, 16-thread OpenMP):

| Cells | Generate | world.json size | Validate |
|---|---|---|---|
| 4,096 | 3.0 s | 75.6 MB (215 MB with enrichment) | 17.7 s / 589 MB RSS |
| 16,384 | 13.2 s | 298 MB | — |
| 65,536 | 67.7 s | 1.2 GB | — |

**Important caveat:** the shipped library was built with an empty `CMAKE_BUILD_TYPE` (verified in
`build/CMakeCache.txt`) and `CMakeLists.txt` never sets a default — all numbers above are
effectively `-O0`. A Release build is likely several-fold faster for free.

### 1.2 Subsystem findings

**C++ native core (`cpp/src/engine.cpp`)**

- Pipeline in `generate_world_json` (engine.cpp:14028-14276): mesh (Fibonacci brute-force O(n²)
  kNN, or geodesic icosahedron with exact spherical-area closure check) → plates → boundaries →
  crust/topography → initial hydro-climate stabilization → erosion loop (plate motion + crust
  back-trace advection, hillslope transport, parallel stream-power erosion, serial topological
  fluvial routing, finite inventory, depression stabilization with up to 16 re-passes) →
  cryosphere + glacial transport → ~25 derived layers → JSON.
- Determinism engineering is exceptional and is the project's crown jewel for debugging:
  order-independent splitmix64 hash noise keyed by `(seed, cell_id)`, `mt19937_64` confined to two
  serial setup calls, min-cell-id tie-breaking in flow routing and union-find, all 18 OpenMP loops
  writing disjoint slots with serial FP reductions — **output is invariant to thread count**.
- 57 defensive throw sites, including a redundant BFS reconstruction cross-check of the sea-level
  union-find result.
- Weaknesses: severe monolith (one TU, 3 exported symbols, nothing unit-testable;
  `summary_json` alone spans ~1,777 lines); the C ABI is a single blocking call with no progress,
  cancellation, streaming, or per-section retrieval (Python transiently holds ≥3 full copies of
  the blob); `num()` (engine.cpp:1385) is locale-sensitive (a host calling `setlocale` corrupts the
  decimal separator — a concrete hazard for embedding the engine in a Qt process) and silently
  rewrites NaN/Inf to 0.0; `float_precision` is overridden by hard floors on geometry/history
  arrays, so output size cannot really be reduced; `include_cells=false` drops only ~24 MB while
  ~50 MB of per-cell history arrays remain unconditional; O(n²) kNN and crust back-trace kernels
  drive superlinear scaling (4.4–5.1× wall time per 4× cells).

**Python orchestration (`api.py`, `native.py`, `config.py`, `io.py`)**

- `api.generate_world(WorldConfig) -> dict` is a clean, pure, in-process composition root — a GUI
  can import it directly, no shell-outs needed. The 66 enrichers are strikingly uniform
  (`enrich_world_with_X(world) -> dict`, guard-clause no-op, in-place mutation) with essentially
  zero import coupling.
- The enrichment order encodes an implicit, unchecked dependency DAG; every read is
  `.get(key, default)`, so reorderings and typos degrade silently. There is no
  `requires`/`provides` metadata, no logging, no progress hook, and no `ENRICHMENT_STEPS` registry.
- Pure Python end to end — zero numpy in `src/`. A 200k-cell world at ~400 fields/cell is multiple
  GB as Python dicts.
- 14 modules hardcode Earth radius 6371 km against a user-configurable `planet.radius_km`.
- `ComputeConfig.backend` (`auto`/`cpu`/`opencl`) is validated but never marshaled to the engine —
  the user's choice is silently ignored (the engine is CPU/OpenMP-only anyway).

**CLI + strict validation (`cli.py`, 30,845 lines)**

- The nine Typer commands are small and well-designed (~350 lines, ~1% of the file). Everything
  else is validation: 18 module-level `_validate_*` replay functions (~8,860 lines) plus
  `validate()` itself — **a single ~21,340-line function** (cli.py:9216-30552) with 15 nested
  `def`s and ~1,094 distinct `failures.append` strings.
- The strictness is real and verified: mutating one cell's `elevation_m` by +0.5 m flips
  validation to FAIL. The validators re-implement every native formula in pure Python against the
  exported provenance ledgers.
- The critical flaw for debugging: **failure reporting collapses precise divergence knowledge into
  coarse flat strings.** `_validate_hydrologic_water_budget` has 19 early-return sites that all
  emit the same string; the verified single-cell mutation produced 3 coarse FAIL lines with no cell
  id, no field, no stage, no expected/actual value — information the code computes at each
  comparison site and then discards. The four sediment validators already return structured
  per-cell expected state (`dict[field -> dict[cell_id -> volume]]`), proving richer signatures fit
  the codebase.
- The 12 `*_validation.py` modules vs cli.py-resident validators split is purely accretional; both
  share the identical pure `payload -> list[str]` contract. The 30 extracted validators are
  verified importable and callable in-process — a GUI can re-run any of them on a loaded world.
- Failure strings are pinned by `tests/test_generation_smoke.py` (exact `assertIn` matches), so a
  structured-divergence refactor needs a string-compat rendering layer.

**Output data model (`io.py`, world.json/cells.csv)**

- Five artifacts, all from io.py: world.json (master), cells.csv (streamable but scalar-only, 407
  hardcoded columns with `extrasaction='ignore'` silently dropping new fields), summary.md, plus
  derived SVG/PPM renders. `geotiff.py` is a reader (calibration ingestion) only.
- No binary/columnar/geospatial output format exists anywhere. No manifest, no per-family split,
  no byte-offset index, no machine-readable schema (schema_version is a bare int), no delta
  encoding for the O(stages × cells) histories.
- Geometry comes three ways, none GPU-ready: `position_3d`/`normal_3d` unit vectors, lat/lon
  degrees, and approximate per-cell `boundary_ring` polygons with per-edge mismatch/quality
  metrics. The README explicitly defers exact native edge polygons — rings do **not** tessellate,
  so a globe renderer must triangulate from `position_3d` + rings itself.
- The exported `mesh_lod` (cube_quadtree_v0) and HEALPix/S2-like indices are exactly the right
  scaffolding for LOD/culling, but the cell payload is not partitioned or sorted by tile, so they
  are dead weight until an export layer exploits them.
- The checked-in sample `runs/earthlike/world.json` is badly stale (7 top-level keys, 31 cell
  fields vs the current ~95 record families / ~400 fields) and fails current validation with 550
  errors — it misleads every tool and reader.

**Rendering path (`render`/`render-raster` → `write_svg_map`/`write_raster_map`)**

- Dependency-free, causal, and fast for a CLI (0.04 s SVG at 4,096 cells), with three projections
  (equirectangular, Mollweide 8-iteration Newton-Raphson, orthographic hardcoded to lat 0/lon 0).
- Cells are drawn only as **centroid point discs** — never polygons — even though `boundary_ring`
  exists; verified visually, the raster is a gappy dot field. ~330 lines of projection/palette
  code are duplicated verbatim between the SVG and raster writers and have already drifted (raster
  has sediment/current/noise styling the SVG lacks).
- All projection/styling logic lives as closures inside the two writer functions — nothing is
  importable. SVG elements carry no `data-cell-id`, so even post-hoc hit-testing is impossible.
  Antimeridian wrap suppression only guards equirectangular; Mollweide draws spurious chords.
  `--max-cells` is naive stride slicing that ignores the purpose-built `mesh_lod` quadtree.
- Rendering sits entirely outside the strict-replay validation culture: one substring smoke test,
  no golden images, no projection unit tests.

**Tests + calibration**

- 5 unittest files, 13,688 lines, 58 tests, all passing (91 s for the generation smoke suite).
  Assertion density is unusually deep (~4,899 asserts, ~1,590 mutation-rejection checks), but
  `test_small_generation_smoke` is a single 7,623-line test method, only 14 of ~90 modules are
  imported directly by tests, there is no CI, no coverage tooling, and no C++ unit tests.
- Calibration (`calibration.py`, 2,073 lines) is genuinely rigorous and dependency-free: SHA-256
  pinned Natural Earth / ETOPO / WorldClim / HydroBASINS / HydroRIVERS ingestion with hand-written
  shapefile/DBF/OPeNDAP/LZW-TIFF parsers, sampled at the exact generated Fibonacci mesh. 8/11
  empirical targets pass for the reference seed; the ensemble audit is honest that zero members
  pass all targets.
- Calibration gap relevant to a GUI: per-point Earth samples are discarded after scalar statistics
  — the most natural visualization (Earth vs generated side-by-side on the identical sphere mesh)
  is blocked until sampled values are persisted per cell.
- Environment hazard: the venv's editable install resolves to a **second full copy of the repo**
  (`~/Documents/research/magic-geo`) — currently byte-identical, but divergence would silently test
  stale code.

### 1.3 Strengths (ranked by value to a GUI debugger)

1. **Determinism + provenance depth.** Complete per-stage ledgers with explicit mass-balance
   residuals are already serialized. Determinism means any state is exactly reproducible from
   seed + config — the strict-replay validators effectively *are* a time-travel replay engine.
2. **The Python API layer is GUI-ready.** Pure in-process `generate_world`, 66 uniform re-runnable
   enrichers, 30 importable pure validators, tiny dependency footprint (3 runtime deps).
3. **Mesh/index scaffolding already exported:** `position_3d`, boundary rings, typed adjacency
   edges, quadtree LOD tiles, HEALPix/S2-like ids, five explicit graphs.
4. Strict validation that actually works, and realism/calibration checks already shaped as
   `{metric, value, target, score, passed}` — GUI-dashboard-ready.

### 1.4 Risks / debt (ranked; first four are direct GUI blockers)

1. Shipped `.so` built without optimization (one-line fix, do first).
2. `validate()` as a 21k-line function discarding structured divergence data into flat strings —
   the single highest-leverage refactor for debugging.
3. Single blocking C ABI call, no progress/cancel/streaming (tolerable for post-hoc v1; blocks
   live-generation UX until a stage-boundary callback seam is added).
4. Monolithic pretty-printed JSON output with no columnar/manifest/partial access — forces the
   GUI's columnar cache layer (unavoidable; embrace it as the data spine).
5. engine.cpp monolith; O(n²) kernels.
6. Silent-failure hazards: implicit enrichment DAG, 407 hardcoded CSV columns, no machine-readable
   schema, 41-field positional ctypes struct, `num()` locale sensitivity.
7. Earth-radius hardcoding in 14 modules; stale sample run; duplicated venv target.

---

## Part 2 — What a GUI can consume today vs what must be added

### Already in world.json (consume as-is)

| Data | GUI use |
|---|---|
| 160–400 per-cell fields (elevation, monthly climate, hydrology with `flow_to`/accumulation, sediment, cryosphere, soils/biomes, political/culture/language ids) | Dozens of choropleth layers, zero new computation |
| `hydrologic_water_budget_history` (17 per-cell arrays × 16 recomputes), `plate_motion_history` (per-cell plate/crust provenance per step), hillslope/fluvial/glacial per-edge ledgers, depression-fill events with breach paths, `earth_system_feedback_history` (~110 scalars/stage) | Stage/time scrubbing, per-cell ledger drill-down, convergence sparklines |
| `position_3d`/`normal_3d`, boundary rings + quality metrics, 24-field adjacency edges, watershed/territorial boundary polylines | 3D globe geometry, edge/boundary overlays |
| `mesh_lod` quadtree tiles, HEALPix/S2-like indices | LOD/culling scaffolding at scale |
| Five graphs (plate/river/watershed/trade/political), settlements/routes/dynasties/cultures/markets/campaigns with self-describing model-provenance records | Node-link views, entity pages, "why is this here" panels |
| Realism/calibration checks (`{metric, value, target, score, passed}`) | Pass/fail dashboards, target-vs-generated bullets |
| In-process Python: 30 pure validators, 66 enrichers, reference projection math in io.py | Replay-on-demand, layer recompute, projection spec |

### Must be added (in build order)

1. **Columnar debug cache** (`magic-geo export-debug`): pyarrow Parquet per record family (wide
   cells table, long per-stage ledger tables partitioned by stage, graph edge lists) + JSONL for
   provenance/event families. Non-optional — the 1.2 GB JSON blob rules out direct interactive use.
2. **A watertight triangulated mesh asset.** Boundary rings don't tessellate; a one-time Python
   triangulation (fan per cell around its site, per-vertex `cell_id` attribute, plus precomputed
   equirectangular/Mollweide 2D positions as a second attribute set) becomes the static GPU asset.
3. **Stage-snapshot manifest.** Per-stage state is scattered across heterogeneous histories
   (elevation in the water-budget history, plates in plate_motion, ice in the glacial history);
   the join logic exists only implicitly inside the `_validate_*` replays — codify it once at
   export as "stage N full cell state".
4. **Structured validation divergence records** — refactor `validate()`'s early-return sites to
   `{model, stage_id, cell_id, field, expected, actual, tolerance}` objects with a compat renderer
   back to the pinned legacy strings. This unlocks replay-divergence overlays on the map — the
   debugger's most differentiated feature.
5. **Machine-readable schema/manifest** (field catalog, units, dtypes, legend hints).
6. **Later (engine work):** C-ABI progress/cancel callback + per-section retrieval; per-stage
   monthly climate and staged human layers (currently final-only); persisted per-cell calibration
   samples for Earth-vs-generated difference maps.

---

## Part 3 — GUI options research

### 3.1 Requirements

Single local user, Linux-first, solo developer, Python + C++ codebase. The GUI must provide:
layer toggling over hundreds of per-cell fields on a **true spherical mesh** (4k → 1M cells),
per-cell drill-down into ~100-field records and their per-stage ledger slices, stage/time
scrubbing over `coupled_geodynamic_stage_clock_v12`, provenance/ledger inspection, run-to-run
diffing, and validation-divergence display. Generation stays in the CLI.

### 3.2 Prior art — UX patterns worth copying

- **World Orogen** (orogen.studio): the closest UI-shape prior art — an "Inspect" dropdown with 26
  debug layers grouped by category (geology/atmosphere/climate/ocean) over a drag/zoom globe.
- **Azgaar's Fantasy Map Generator** (active, v1.124): the reference **layer grammar** — hotkeyed
  toggles, drag-to-reorder z-order, named layer presets (political/cultural/biomes/heightmap),
  per-layer opacity for onion-skinning, hover cell-inspector; per-cell drill-down UI on a Voronoi
  mesh at exactly magic-geo's default scale.
- **Dwarf Fortress Legends viewers** (LegendsViewer-Next, Legends Browser 2): **the** template for
  the non-raster half — a separate local web app parses the exported dump into a hyperlinked wiki
  of entity pages (figures, sites, wars) with filterable tables, timelines, and maps. Proven at
  multi-GB scale. Maps 1:1 onto magic-geo's settlements/dynasties/campaigns/ledgers.
- **GPlates**: the gold-standard geological **time control** — three synchronized controls
  (slider + exact-value field + single-step buttons with shortcuts).
- **Songs of the Eons**: per-subsystem map modes, with the motivating observation quoted verbatim
  in its devlog: visual map modes exist because "it's much easier to notice issues with the model
  when we don't need to analyze state of a tile with over a hundred numbers."
- **mapgen4 / Red Blob Games**: build debug overlays for **the mesh topology itself** (neighbors,
  triangulation, boundary rings, LOD seams) — bugs hide in whichever representation you have no
  debug view for.
- **Landlab / FastScape / xarray-simlab / ipyfastscape**: the scientific reference for stage
  scrubbing — snapshot "clock" coordinates in zarr, time-player widgets, linked side-by-side run
  comparison (`AppLinker`). ipyfastscape itself is stale (2023); treat it as a design donor.
- **Panoply** (NASA, active): variable-tree browsing + built-in array differencing = the run-diff
  interaction model. **Marquez/OpenLineage**: DAG + per-run detail panels = the provenance
  inspection model. **MLflow compare-runs**: hide-identical-params diff tables = the config/metric
  diff model. **rr/Undo time-travel debugging**: determinism + seeds means the GUI only needs
  sparse checkpoints + replay — magic-geo's strict-replay validators already are that engine.
- Negative lessons: **worldengine** (CLI-only, batch PNG per layer, near-dead) proves static
  contact-sheet images never satisfy debugging; **Tectonics.js/Experilous** prove watch-only sims
  without ledgers/scrubbing dead-end.

### 3.3 Candidates by category (condensed survey)

**Web 3D globe stacks**

| Option | Verdict |
|---|---|
| **three.js custom BufferGeometry** (r185, monthly releases) | **Best fit.** Consumes `position_3d` natively — no lon/lat detour. One merged indexed BufferGeometry + per-cell scalars in a DataTexture renders millions of triangles at 60fps; stage scrub = one Float32 buffer swap; picking = documented id-buffer pattern (a few hundred lines); sphere↔Mollweide morph = ~50-line vertex shader over a second precomputed position attribute. Every prior-art planet viewer converged here. |
| deck.gl v9.3 GlobeView | Built-in picking/tooltips are seductive, but GlobeView has been officially experimental for 5+ years, is lon/lat-only (lossy detour), has no Mollweide, and CPU-tessellates irregular polygons at load. |
| CesiumJS | Earth-locked (WGS84 assumptions everywhere), 23 MB bundle for the ~10% you'd use; its excellent Timeline doesn't justify fighting the ellipsoid for a fictional planet. |
| globe.gl | Dies architecturally at ~20k polygons (per-polygon THREE.Mesh). Prototype-only. |
| Babylon.js | Capable, best WebGPU story, but no advantage for this workload and a game-oriented ecosystem. |
| regl / raw WebGL | Proven by Red Blob's 1843 demo, but maintenance-mode; three.js gives the same architecture with helpers. |
| three.js WebGPURenderer/TSL | "Via three.js, later, not instead" — write shaders in TSL where practical so WebGPU (compute-based diffing) is an upgrade, not a rewrite; ship v1 on WebGL2. |
| d3-geo(-voronoi) | Not the renderer; the cheapest correct companion for publication-grade 2D projected exports. |

**Python-native scientific viz**

| Option | Verdict |
|---|---|
| **PyVista + pyvistaqt** (PyVista 0.48.x, pyvistaqt 0.12.0 Jul 2026) | **Best Python-only fit.** PolyData accepts true polygonal cells + `cell_data` per-cell scalars directly from world.json; `enable_cell_picking` gives drill-down; ~300-line first prototype. Caveats: scrubbing is hand-rolled array swaps; pyvistaqt is a small glue project; VTK full recolor at 1M cells is scrub-and-inspect, not video. |
| **ParaView** (via `.vtu`/`.pvd` export) | Not a tool you build — a capability you unlock with one exporter. Free VCR stage-stepping, any-field coloring, spreadsheet cell inspection. Wrong as the primary (generic UI, no provenance model), excellent as the zero-code companion. |
| vedo | Legitimate lighter PyVista alternative, same VTK engine; loses on Qt bridge, docs, bus factor. |
| napari | Image-viewer data model (per-vertex triangles only, no cell_data); its automatic time sliders don't compensate. |
| matplotlib + cartopy | Report-grade projected snapshots only; seconds-per-frame repaint at 100k+ polygons. |
| pyqtgraph | Not for the globe (no colormap/picking in GL module, documented leak on mesh updates); ideal for the 2D ledger/time-series panels inside a Qt app. |
| Mayavi | Maintenance-only legacy; strictly dominated by PyVista. |

**Dashboard frameworks (as the shell)**

| Option | Verdict |
|---|---|
| Panel (HoloViz) | Strongest pure-Python shell: Datashader's trimesh rasterizer is built for large irregular meshes; linked brushing and DynamicMap stage scrubbing are free. Fatal flaw here: the 3D globe pane is display-only (no picking) — interaction confined to 2D projections. Best choice only if refusing all JS forever. |
| marimo | Strong momentum, DAG reactivity mirrors the project's causal philosophy; a fine debugging *workbench*, weaker as a multi-pane cockpit; pre-1.0. |
| NiceGUI | Real three.js scene + native-feel mode, but cell-level picking at scale needs custom JS anyway — at which point the plain web app is less framework in the way. |
| Streamlit / Dash / Gradio / Solara / raw Bokeh | Rejected: rerun model fights deep stateful drill-down (Streamlit); highest ceremony + stateless callbacks (Dash); ML-demo shape (Gradio); tiny community + dormant 3D widget ecosystem (Solara); dominated by Panel (Bokeh). |

**Desktop-native**

| Option | Verdict |
|---|---|
| PySide6 + pyvistaqt + pyqtgraph | The runner-up architecture (scored below). In-process with validators/enrichers; QTreeView ledger browsers; QSlider stage scrub. Note the engine's locale-sensitive `num()` makes embedding the *engine* in a Qt process hazardous (Qt commonly calls `setlocale`). |
| imgui-bundle (Python Dear ImGui) + moderngl globe | The genuine game-industry sim-debugger pattern (per Dear ImGui's own positioning; Undiscovered Worlds proves the stack on procedural planets): ImPlot for ledgers, node editor for causal/plate/trade graphs. Pays a one-time ~1–2 week renderer tax; data-dense trees/tables are more manual. Strong if you love immediate mode. |
| C++ ImGui linked against engine.cpp | The only option enabling *live stepping of native state below the JSON boundary*. Wrong now (forfeits the entire Python layer); right later, coexisting with — not replacing — the main GUI. |
| Rerun (v0.34.1, Jul 2026) | Not a framework — a ready-made Arrow-native time-scrubbing viewer with a Python SDK. An afternoon of `rr.log` calls (Mesh3D per stage + ledger time series + graphs) buys world-class timeline scrubbing. Can't do SQL drill-down, ledger wikis, or first-class run diffing. **Adopt as v0 and keep forever; never the endgame.** |
| Tauri (Linux) | Rejected: WebKitGTK's documented WebGL context-loss/NVIDIA DMABUF instability is exactly this workload on exactly this platform. |
| Electron | Rejected: three runtimes and 200–300 MB idle RAM to serve one local user; serving the same JS app from a Python HTTP server into the system browser needs none of it. |
| Godot / egui | Capable existence proofs, wrong center of gravity (data-dense inspection) or wrong language for a solo Python+C++ dev. |

**Data/serving spine**

| Option | Verdict |
|---|---|
| **Parquet (pyarrow) + native DuckDB + Arrow IPC over FastAPI** | **The spine.** DuckDB 1.5 (GEOMETRY in core, LTS line); scrub = `SELECT field FROM ledger WHERE stage_idx=?` returning one Arrow column swapped as a GPU attribute (~4 MB per scrub step at 1M cells over localhost); run diff = joins across two run dirs. |
| JSONL per record family | The provenance-ledger tier: human-greppable, append-friendly, directly queryable by DuckDB. |
| Static triangulated mesh asset + binary column streaming | The rendering half of the spine (Rerun/lonboard's proven Arrow-to-GPU pipeline, minus their constraints). |
| DuckDB-WASM | Later static-hosting toggle, not the primary (bundle size, 4 GB WASM memory, parity gaps). |
| GeoArrow/GeoParquet + lonboard | Strong for a projected 2D companion view; planar assumptions make it wrong for the true sphere. |
| PMTiles/vector tiles, FlatGeobuf, msgpack | Rejected for the core: Mercator-projected/per-stage tile explosion; remote-static-hosting tools; no zero-copy. PMTiles worth revisiting later as a pretty 2D export beside the SVG renderer. |
| LOD at 1M cells | Defer entirely below ~200k cells; past that, the already-exported `cube_quadtree_v0` tile paths and HEALPix/S2 ids turn LOD into a DuckDB `GROUP BY` (HiPS / Cesium quantized-mesh blueprints). Never re-bin to H3 — it destroys causal cell identity. |

### 3.4 Scored comparison

Dimensions scored 1–10 by the synthesis pass: spherical-mesh rendering, debugging depth, dev
effort for a solo dev (higher = less effort), scalability to 1M cells, reuse of existing code,
longevity.

| Candidate | Sphere | Debug | Effort | Scale | Reuse | Longevity | **Total** |
|---|---|---|---|---|---|---|---|
| **Local web app: FastAPI + Parquet/DuckDB + custom three.js globe** | 10 | 9 | 5 | 10 | 8 | 9 | **51** |
| PySide6 + pyvistaqt desktop app (+ pyqtgraph panels) | 9 | 8 | 8 | 7 | 10 | 6 | **48** |
| Rerun viewer (Python SDK exporter) | 7 | 5 | 10 | 7 | 9 | 8 | **46** |
| imgui-bundle + moderngl globe | 7 | 8 | 5 | 9 | 9 | 7 | **45** |
| Panel (HoloViz) + Datashader trimesh (2D-interactive) | 5 | 8 | 7 | 7 | 10 | 7 | **44** |
| deck.gl v9 GlobeView | 6 | 7 | 6 | 6 | 7 | 8 | **40** |

---

## Part 4 — Recommended architecture and plan

### 4.1 The architecture

```text
                     CLI (unchanged)                        GUI (new, read-mostly)
 seed.yaml ──▶ magic-geo generate ──▶ world.json ──▶ magic-geo export-debug
                                      (canonical,       ├─ Parquet per record family (pyarrow)
                                       validated,       │    cells.parquet (wide), per-stage ledgers
                                       unchanged)       │    (long, partitioned by stage_idx), graphs
                                                        ├─ JSONL per provenance/event family
                                                        ├─ triangulated mesh asset (Float32 positions,
                                                        │    fan indices, per-vertex cell_id, precomputed
                                                        │    equirect + Mollweide 2D positions)
                                                        └─ (byproduct) .vtu per stage + .pvd → ParaView

               magic-geo serve  =  FastAPI + native DuckDB (same process family as the package:
                                   can call the 30 pure validators and re-run enrichers)
                                   ├─ scalar column for stage N  → Arrow IPC
                                   ├─ cell record + its ledger slices by cell_id → JSON
                                   └─ entity / graph / event / diff queries → JSON

               Frontend (system browser — no Electron, no webview):
                 three.js WebGL2, ONE merged indexed BufferGeometry
                 ├─ per-cell scalars via cell-id-indexed DataTexture (colormap in shader)
                 ├─ GPU id-buffer picking → cell inspector panel
                 ├─ sphere ↔ Mollweide/equirect morph in the vertex shader (~50 lines)
                 ├─ Azgaar-style layer panel (hotkeys, presets, per-layer opacity)
                 ├─ GPlates-style triple time control (slider + exact stage + step buttons)
                 ├─ mesh-topology debug overlays (wireframe, adjacency, plate edges, LOD seams)
                 └─ provenance wiki: hyperlinked entity pages (DF LegendsViewer pattern)
                 (shaders in TSL where practical → WebGPU is an upgrade, not a rewrite)
```

Why this beats the Qt runner-up:

1. **The columnar cache is required regardless of frontend** (the 1.2 GB JSON reality) — once
   Parquet + DuckDB exists, Arrow-to-GPU is the natural continuation, and it is the only
   architecture where stage scrubbing and in-shader run diffing stay video-smooth at 65k–1M cells.
2. **The non-spatial half of deep debugging** — ledger wikis, filterable event tables,
   realism-check dashboards, config diffs — is strictly better in HTML than in Qt trees.
3. **Longevity:** three.js + FastAPI + DuckDB will outlive a small Qt glue library; and the
   engine's locale-sensitive JSON makes embedding it in a Qt process actively hazardous.
4. **Precedent:** every prior-art spherical-Voronoi planet viewer independently chose
   three.js/raw WebGL.

Pick **PySide6 + pyvistaqt instead only if** writing any JavaScript is a dealbreaker — it reaches
a useful inspector fastest (~300 lines) but caps out on scrub smoothness, provenance browsing, and
ecosystem risk. Either way the export layer is the same work, which erodes most of Qt's
time-to-value advantage.

### 4.2 Phased build plan

**v0 — one week, mostly non-GUI leverage**

1. Set `CMAKE_BUILD_TYPE=Release` default + `-O2` in CMakeLists.txt; verify determinism against a
   pinned world hash. Free multi-fold speedup on every future iteration loop.
2. **Rerun exporter (1–2 days):** walk world.json + stage histories; `rr.log` Mesh3D with
   per-stage vertex colors on a "stage" timeline, feedback-ledger scalars as time series, the five
   graphs. Professional stage scrubbing this week; validates the whole UX cheaply; kept forever as
   a second screen.
3. **`magic-geo export-debug` (2–3 days):** Parquet families + JSONL ledgers + triangulated mesh
   binary (with precomputed 2D projection positions). Emit `.vtu`-per-stage + `.pvd` as a near-free
   byproduct → ParaView becomes a zero-code heavyweight companion immediately.
4. Regenerate `runs/earthlike` with the current schema (the stale sample misleads every tool).

**v1 — the debugger proper (~4–8 solo weeks)**

1. `magic-geo serve`: FastAPI + native DuckDB; endpoints for stage-N scalar columns (Arrow IPC),
   cell record + per-stage ledger slices by cell_id, entity/graph/event queries.
2. three.js globe: merged BufferGeometry, DataTexture colormaps, id-buffer picking, orbit camera,
   sphere↔2D projection morph, and **mesh-topology overlays** (wireframe, adjacency, plate
   boundaries, LOD seams — mapgen4's lesson).
3. Debugger shell: Azgaar-style layer panel with presets/opacity; GPlates triple time control with
   ±2-stage column prefetch; click-a-cell inspector showing the full field record plus that cell's
   water-budget/plate/sediment/depression ledger entries per stage.
4. **Structured-divergence refactor, staged inside v1:** convert `_validate_*` early-return sites
   (start with the hydrologic water budget's 19) to divergence objects
   `{model, stage_id, cell_id, field, expected, actual, tolerance}` with a renderer back to the
   legacy strings so the smoke test stays green. The GUI renders divergences as overlay layers —
   replay debugging on the sphere, the tool's most differentiated feature.

**v2 — differential and live debugging**

1. **Run diffing:** DuckDB joins across two run directories → signed-colormap diff layers
   (A−B per field per stage) + MLflow-style hide-identical config/summary/realism diff tables +
   linked side-by-side viewports (ipyfastscape's `AppLinker` pattern).
2. **Provenance wiki:** hyperlinked entity pages over the JSONL families (LegendsViewer pattern) +
   a Marquez-style stage→transition→ledger DAG view.
3. **Scale:** past ~200k cells, LOD via `GROUP BY` on the already-exported `cube_quadtree_v0` tile
   paths (representative cells far, raw cells near — HiPS/quantized-mesh blueprint), with the LOD
   boundary explicit in the UI so aggregates are never mistaken for true state.
4. **Engine seams (first C++ changes):** progress + cancellation callback registered through the
   C ABI at stage boundaries; per-section/per-stage retrieval; fix `num()` locale + NaN masking.
   Enables a "Generate" button with live stage streaming into the same viewer.
5. Optional: three.js WebGPURenderer/TSL compute for on-GPU stage diffing when Linux WebGPU
   stabilizes; an `ENRICHMENT_STEPS` registry so the GUI can re-run/invalidate individual layers.

### 4.3 Key tradeoffs (accepted deliberately)

1. **Web frontend vs pure-Python desktop.** three.js costs a second language and ~1–2 weeks of
   renderer plumbing that pyvistaqt waives; in exchange: smooth scrubbing/diffing at 1M cells,
   HTML-native provenance wikis, no small-glue-project dependency, no Qt-locale hazard, longer-
   lived stack. If ambitions are firmly capped at ≤65k cells and inspect-not-scrub, Qt wins on
   time-to-value.
2. **Second data format vs single source of truth.** The Parquet cache duplicates world.json and
   could drift. Accepted because interactive access to the blob is impossible; mitigated by
   generating both from the same in-memory dict and an exporter round-trip test. world.json stays
   the only *validated* artifact.
3. **Post-hoc viewer vs live debugging.** v0/v1 debug completed artifacts only — zero C++ changes,
   and stage ledgers make post-hoc scrubbing nearly as good as live. Determinism means anything
   missed live is exactly reproducible offline.
4. **Buy vs build for scrubbing.** Rerun gives the best scrub UX for one day of work but can't do
   SQL drill-down, ledger wikis, or run diffing (custom panels = unstable Rust API). Buy Rerun as
   v0 and keep it; build the custom tool for precisely what Rerun can't host. Same logic for
   ParaView.
5. **Refactor `validate()` now vs later.** Exact failure strings are pinned by 12k lines of tests;
   doing it validator-by-validator with a string-compat shim (the sediment validators already
   prove richer return types fit) keeps v1 shippable while unlocking divergence overlays.
6. **Whole-mesh rendering vs LOD.** Below ~200k cells one merged geometry wins; the hedge is
   already paid for (quadtree + HEALPix/S2 ids ship in the data), so LOD later is a `GROUP BY`,
   not a redesign.
7. **Approximate rings vs exact mesh.** Triangulating from centroids + approximate boundary rings
   inherits documented per-edge mismatch; seams are acceptable for a debugger, and the mismatch
   metrics themselves become a debug layer. Exact native edge geometry (declared future work in
   the README) slots in later without changing the pipeline shape.

---

## Appendix A — Explicitly rejected options (and why)

| Option | Reason |
|---|---|
| deck.gl GlobeView | Officially experimental for 5+ years, lon/lat-only, no Mollweide, CPU-tessellates irregular polygons |
| CesiumJS | Earth/WGS84-locked engine for a fictional planet; 23 MB bundle for the fraction used |
| globe.gl | Per-polygon THREE.Mesh architecture collapses at ~20k cells |
| Tauri (Linux) | WebKitGTK's documented WebGL context-loss/NVIDIA DMABUF instability — exactly this workload on exactly this platform |
| Electron | Three runtimes for one local user; the system browser + Python server needs none of it |
| Streamlit / Dash / Gradio / Solara / raw Bokeh | Rerun-model or callback-shape mismatch with deep stateful drill-down; or niche/dormant ecosystems |
| napari / Mayavi / matplotlib-cartopy (as primary) | Data-model mismatch (per-vertex triangles), legacy maintenance, repaint cost respectively |
| PMTiles / FlatGeobuf / msgpack (as core formats) | Solve remote distribution problems this local tool doesn't have; no zero-copy; Mercator assumptions |
| H3 re-binning for LOD | Destroys causal cell identity; use the exported cube_quadtree_v0/HEALPix-like ids instead |
| C++ ImGui tool linked to engine.cpp (now) | Forfeits the entire Python layer; becomes attractive later for live native-state stepping, alongside the main GUI |

## Appendix B — Quick-reference: highest-leverage fixes surfaced by the review

Independent of the GUI, in rough order of value:

1. Default `CMAKE_BUILD_TYPE=Release` (+`-O2`) in CMakeLists.txt — likely multi-fold speedup.
2. Decompose `validate()` (21,340 lines) into the same pure `payload -> failures` contract as the
   30 extracted validators; emit structured divergence records with a legacy-string renderer.
3. Regenerate the stale `runs/earthlike` sample (current one fails validation with 550 errors).
4. Extract projection/styling closures from `write_svg_map`/`write_raster_map` into an importable
   module and de-duplicate the ~330 drifted lines; add `data-cell-id` to SVG cells.
5. Add an `ENRICHMENT_STEPS` registry with `requires`/`provides` metadata in api.py (progress,
   selective re-run, DAG validation).
6. Marshal `ComputeConfig.backend` across the ABI or remove the silently-ignored option; make the
   41-field ctypes struct keyword-constructed with a field-count/version handshake.
7. Fix `num()` locale sensitivity and NaN→0.0 masking in engine.cpp JSON output.
8. Parameterize the 14 modules hardcoding Earth radius 6371 km on `planet.radius_km`.
9. Fix the venv editable install pointing at a second repo copy (`~/Documents/research/magic-geo`).
10. Persist per-cell calibration samples (Earth values on the generated mesh) to enable
    Earth-vs-generated difference maps.
