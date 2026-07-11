# Layers Reference — every debugger layer, deep

> **Auto-generated** by `scripts/gen_layers_reference.mjs` from the same
> [`debug_ui/layer_docs.js`](../src/magic_geo/debug_ui/layer_docs.js) that powers the in-app docs
> helper, run over a real `export-debug` manifest — so it cannot drift from what the UI shows.
> Regenerate after re-exporting a cache or editing `CURATED`:
> `node scripts/gen_layers_reference.mjs [manifest.json] [out.md]`.
> Companion to [debugger.md](debugger.md), the review in [layers_review.md](layers_review.md),
> and the [configuration reference](configuration_reference.md).

## What a "layer" is

A **layer** is one scalar value per cell that the debugger can colour the globe by. The exporter
discovers layers generically from the world-payload shape ([debug_export.py](../src/magic_geo/debug_export.py)):

- **`numeric`** — an int/float cell field. Coloured with viridis normalised to the p2–p98 range.
- **`categorical`** — a string/bool cell field with ≤ 64 distinct values. One colour per class.
- **`numeric_monthly`** — a 12-element numeric cell field. Scrub the month control (1–12).
- **`numeric_stage`** — a per-cell field inside a record family shaped as `cell_ids` + `*_by_cell`
  parallel arrays. Scrub the stage control; the colour scale is fixed across all stages.

Every layer carries **props** used throughout this doc: its `id` (`source/name`), `kind`, inferred
`unit`, `role` (below), value `range` (min…max), and for stage/monthly layers the stage/month count.
Categorical layers carry the full class list instead of a numeric range.

### Role (how to read the values)

| Role | Meaning |
| --- | --- |
| `measurement` | A physical quantity in the named unit. |
| `index` | Derived, normally normalised 0–1; higher = more of the property. Good for ranking, not absolute. |
| `ratio` | Dimensionless fraction (0–1) or multiplier (around 1). |
| `classification` | Discrete categorical class; colours carry no ordering. |
| `identifier` | An integer label (region/system/graph reference). The gradient is meaningless — same colour ≈ same group. |
| `provenance` | An `initial_*` snapshot captured before the feedback loop; diff against the evolved field. |
| `accumulator` | A `cumulative_*` running total across all stages. |
| `diagnostic` | A conservation residual / mass-balance / count. Residuals should be ~0 — a debug signal, not terrain. |
| `seasonal` | Derived from the monthly climate series (month counts, seasonal ranges). |

### Doc status (the gap tracker)

The **Doc** column records how each description is sourced, most to least specific:

- **curated** — hand-written prose in `layer_docs.js` `CURATED`.
- **convention** — a field-naming rule (`*_id`, `*_index`, `initial_*`, …) or being categorical.
- **unit** — only a unit could be inferred from the suffix; the rest is a template.
- **generated** — pure fallback ("inspect a cell for context"). **These are the documentation gaps.**

## Inventory & coverage

World: **earthlike_mvp** · 32,768 cells · mesh `fibonacci_sphere` · scope `full`.

**446 layers** total — 368 numeric, 47 categorical, 27 per-stage, 4 monthly.

Documentation coverage:

| Tier | Count | Share |
| --- | --: | --: |
| curated | 61 | 13.7% |
| convention | 246 | 55.2% |
| unit | 120 | 26.9% |
| generated | 19 | 4.3% |

Layers by domain (documentation gaps = generated tier):

| Domain | Layers | Curated | Generated (gaps) |
| --- | --: | --: | --: |
| [Mesh & geometry](#geometry) | 40 | 12 | 7 |
| [Tectonics & solid earth](#tectonics) | 42 | 8 | 4 |
| [Elevation & landforms](#geomorphology) | 13 | 7 | 0 |
| [Sediment & stratigraphy](#sediment) | 36 | 2 | 0 |
| [Surface hydrology & rivers](#hydrology) | 80 | 14 | 4 |
| [Water budget & atmospheric moisture](#water-budget) | 27 | 3 | 0 |
| [Groundwater, aquifers & karst](#groundwater) | 30 | 0 | 0 |
| [Climate & atmosphere](#climate) | 38 | 5 | 2 |
| [Oceans & coasts](#ocean) | 31 | 2 | 1 |
| [Cryosphere (ice, glaciers, permafrost)](#cryosphere) | 25 | 2 | 0 |
| [Soils](#soil) | 14 | 2 | 0 |
| [Ecology, biomes & disturbance](#ecology) | 35 | 1 | 1 |
| [Resources & economic geology](#resources) | 15 | 1 | 0 |
| [Human & political geography](#human) | 20 | 2 | 0 |

---

## Mesh & geometry

<a id="geometry"></a>

**40 layers** · doc coverage: 12 curated · 14 convention · 7 unit · **7 generated (gaps)**.

**How it works.** Static per-cell geometry of the spherical mesh — cell centres, areas, surface normals, neighbour metrics, and multi-resolution spatial indices (HEALPix-like, S2-like, mesh-LOD tiles). These do not evolve during the simulation; they define the coordinate system every other layer is sampled on.

**Produced by:** `cpp/src/engine/mesh.cpp` (Fibonacci-sphere / geodesic mesh), `cell_geometry.py`, `mesh_lod.py`, `spherical_index.py`.

**Pipeline stage:** Built once at mesh construction, before any physics.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `area_km2` | numeric | `km²` | 15570 … 15570 | measurement | curated | Geodesic area of the cell in km². Near-uniform on the Fibonacci-sphere mesh. |
| `cell_geometry_quality` | numeric | — | 0.9804 … 0.9929 | measurement | curated | Mesh-quality score for the cell polygon; low values flag distorted or self-overlapping cells worth ignoring in analysis. |
| `cell_polygon_area_error_fraction` | numeric | `fraction` | 0.003443 … 0.01648 | ratio | curated | Relative error between the polygon area and the ideal cell area — a mesh-quality debug signal. |
| `lat_deg` | numeric | `°` | -89.55 … 89.55 | measurement | curated | Latitude of the cell centre in degrees (−90…90). |
| `lon_deg` | numeric | `°` | -180 … 180 | measurement | curated | Longitude of the cell centre in degrees (−180…180). |
| `mean_neighbor_boundary_segment_mismatch_km` | numeric | `km` | 56.07 … 68.64 | measurement | curated | Average gap between a cell edge and its neighbour's matching edge. This is the documented "ring mismatch" that produces visible seams in the 2D projections; use it to judge where the approximate boundary rings disagree. |
| `normal_3d_x` | numeric | — | -1 … 0.9999 | measurement | curated | X component of the cell surface normal (planet frame). Geometry, not a physical field. |
| `normal_3d_y` | numeric | — | -1 … 1 | measurement | curated | Y component of the cell surface normal (planet frame). Geometry, not a physical field. |
| `normal_3d_z` | numeric | — | -1 … 1 | measurement | curated | Z component of the cell surface normal (planet frame). Geometry, not a physical field. |
| `position_3d_x` | numeric | — | -1 … 0.9999 | measurement | curated | X component of the cell-centre position on the unit sphere (planet frame). Geometry, not a physical field. |
| `position_3d_y` | numeric | — | -1 … 1 | measurement | curated | Y component of the cell-centre position on the unit sphere (planet frame). Geometry, not a physical field. |
| `position_3d_z` | numeric | — | -1 … 1 | measurement | curated | Z component of the cell-centre position on the unit sphere (planet frame). Geometry, not a physical field. |
| `biome_transition_neighbor_edge_count` | numeric | `count` | 0 … 15 | diagnostic | convention | Topology count — how many of the cell's mesh neighbours/edges meet the named condition (e.g. cross a land/water or biome boundary). A static property of the mesh + classification, not an event tally. |
| `boundary_vertex_count` | numeric | `count` | 13 … 15 | diagnostic | convention | Topology count — how many of the cell's mesh neighbours/edges meet the named condition (e.g. cross a land/water or biome boundary). A static property of the mesh + classification, not an event tally. |
| `cell_area_km2` | stage×16 | `km²` | 15570 … 15570 | measurement | unit | Per-stage numeric field (scrub the stage control). Area (square kilometres). |
| `cell_boundary_perimeter_km` | numeric | `km` | 444.5 … 446.1 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `cell_edge_count` | numeric | `count` | 13 … 15 | diagnostic | convention | Topology count — how many of the cell's mesh neighbours/edges meet the named condition (e.g. cross a land/water or biome boundary). A static property of the mesh + classification, not an event tally. |
| `cell_monsoon_index` | numeric | `index` | 4.81e-4 … 0.1533 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `cell_polygon_area_km2` | numeric | `km²` | 15310 … 15510 | measurement | unit | Continuous per-cell field. Area (square kilometres). |
| `healpix_like_lon_bin` | numeric | — | 0 … 255 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `healpix_like_nside` | numeric | — | 64 … 64 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `healpix_like_pixel_id` | numeric | — | 0 … 49151 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `healpix_like_ring` | numeric | — | 0 … 191 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `id` | numeric | — | 0 … 32767 | identifier | convention | Cell id (0…cell_count-1). The primary key every table joins on; also the mesh vertex index. |
| `land_water_neighbor_edge_count` | numeric | `count` | 0 … 14 | diagnostic | convention | Topology count — how many of the cell's mesh neighbours/edges meet the named condition (e.g. cross a land/water or biome boundary). A static property of the mesh + classification, not an event tally. |
| `max_neighbor_boundary_segment_length_km` | numeric | `km` | 40.5 … 54.92 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `max_neighbor_edge_length_km` | numeric | `km` | 241.8 … 277 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `mean_neighbor_boundary_segment_length_km` | numeric | `km` | 30.39 … 36.38 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `mean_neighbor_boundary_segment_quality` | numeric | — | 0.3508 … 0.5 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `mean_neighbor_edge_length_km` | numeric | `km` | 185.1 … 199.2 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `mesh_lod_face` | categorical | `category` | 6 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** +x, +y, +z, -x, -y, -z. |
| `mesh_lod_face_id` | numeric | — | 0 … 5 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `mesh_lod_finest_tile_id` | numeric | — | 0 … 24574 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `s2_like_cell_id` | numeric | — | 0 … 24574 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `s2_like_cell_level` | numeric | — | 6 … 6 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `s2_like_face` | categorical | `category` | 6 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** +x, +y, +z, -x, -y, -z. |
| `s2_like_face_id` | numeric | — | 0 … 5 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `s2_like_x` | numeric | — | 0 … 63 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `s2_like_y` | numeric | — | 0 … 63 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `tectonic_neighbor_edge_count` | numeric | `count` | 0 … 12 | diagnostic | convention | Topology count — how many of the cell's mesh neighbours/edges meet the named condition (e.g. cross a land/water or biome boundary). A static property of the mesh + classification, not an event tally. |

> **Gaps in this domain (7):** `healpix_like_lon_bin`, `healpix_like_nside`, `healpix_like_ring`, `mean_neighbor_boundary_segment_quality`, `s2_like_cell_level`, `s2_like_x`, `s2_like_y` — resolved by kind + template only. Add prose to `CURATED` in `layer_docs.js` to close these.

---

## Tectonics & solid earth

<a id="tectonics"></a>

**42 layers** · doc coverage: 8 curated · 27 convention · 3 unit · **4 generated (gaps)**.

**How it works.** Plate assignment and kinematics, crust type/age/thickness/density, boundary classification (convergent/divergent/transform), fault systems, seismic hazard, and the initial tectonic elevation contributions (ridge, rift, trench, orogenic, volcanic, thermal, isostatic). This is the deepest layer of the model — the feedback loop re-derives elevation from these each stage.

**Produced by:** `cpp/src/engine/tectonics.cpp`, `fault_systems.py`, `tectonic_zones.py`, `geology_realism.py`.

**Pipeline stage:** Initialised at setup (the `initial_*` fields), then updated by the geodynamic feedback loop.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `crust_age_ma` | numeric | `Ma` | 1.34 … 4200 | measurement | curated | Age of the crust in millions of years. Oceanic crust is young at ridges and ages toward subduction zones. |
| `crust_density` | numeric | — | 2.683 … 3 | measurement | curated | Bulk crust density (kg/m³ scale); oceanic crust is denser than continental. |
| `crust_type` | categorical | `category` | 9 classes | classification | curated | Crust classification (continental, oceanic, craton, orogen, …). **Classes:** accreted_terrane, continental, craton, oceanic, orogen, rift_basin, sedimentary_basin, transitional, volcanic_arc. |
| `earthquake_recurrence_interval_y` | numeric | — | 0 … 922.8 | measurement | curated | Mean interval between large earthquakes, in years. Low values mark seismically active belts. |
| `lithology` | categorical | `category` | 7 classes | classification | curated | Dominant rock type (basalt, granite, limestone, …). NOTE: the per-stage history serializes lithology as numeric codes 0–6, while this cell layer uses names; the code order is alphabetical here and may not match the engine enum (see layers_review.md F3). **Classes:** basalt, granite, limestone, metamorphic, sandstone, shale, volcanic. |
| `lithology` | stage×16 | — | 0 … 6 | measurement | curated | Dominant rock type (basalt, granite, limestone, …). NOTE: the per-stage history serializes lithology as numeric codes 0–6, while this cell layer uses names; the code order is alphabetical here and may not match the engine enum (see layers_review.md F3). |
| `plate_id` | numeric | — | 0 … 13 | identifier | curated | Tectonic plate the cell belongs to. Identifier — colour groups plates, magnitude is meaningless. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `tectonic_zone_strength` | numeric | — | 0 … 0.7855 | measurement | curated | Relative strength/activity of the tectonic zone influencing the cell (dimensionless). |
| `boundary_convergent` | numeric | — | 0 … 0.6485 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `boundary_divergent` | numeric | — | 0 … 0.6946 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `boundary_transform` | numeric | — | 0 … 0.5796 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `boundary_type` | categorical | `category` | 5 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** convergent, divergent, interior, mixed, transform. |
| `collision_zone_id` | numeric | — | -1 … 18 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `continental_shelf_id` | numeric | — | -1 … 168 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `crust_source_remap_event_count` | numeric | `count` | 0 … 6 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `crust_thickness_km` | numeric | `km` | 5 … 40.27 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `cumulative_crust_transport_distance_km` | numeric | `km` | 1.666 … 1219 | accumulator | convention | Running total accumulated across all simulation stages (monotonic per cell). The per-stage delta lives in the corresponding stage-history ledger. |
| `dominant_tectonic_zone_type` | categorical | `category` | 4 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** collision, none, rift, subduction. |
| `fault_slip_rate_index` | numeric | `index` | 3.00e-6 … 0.5022 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `fault_system_id` | numeric | — | -1 … 27 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `initial_crust_age_ma` | numeric | `Ma` | 54.37 … 4200 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_crust_density` | numeric | — | 2.7 … 3 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_crust_thickness_km` | numeric | `km` | 5 … 43.09 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_isostatic_elevation_m` | numeric | `m` | -3000 … 668.4 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_orogenic_uplift_m` | numeric | `m` | 0 … 8174 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_plate_id` | numeric | — | 0 … 13 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `initial_ridge_uplift_m` | numeric | `m` | 0 … 1816 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_rift_subsidence_m` | numeric | `m` | -545 … 0 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_secondary_roughness_m` | numeric | `m` | -747 … 790.1 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_thermal_subsidence_m` | numeric | `m` | -1138 … 0 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_transform_fault_relief_m` | numeric | `m` | -166.4 … 0 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_trench_subsidence_m` | numeric | `m` | -7627 … 0 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_volcanic_uplift_m` | numeric | `m` | 0 … 5859 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `last_crust_source_cell_id` | numeric | — | 0 … 32767 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `last_plate_assignment_change_iteration` | numeric | — | -1 … 6 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `oceanic_crust_subduction_event_count` | numeric | `count` | 0 … 6 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `plate_assignment_change_count` | numeric | `count` | 0 … 2 | measurement | unit | Continuous per-cell field. Integer count. |
| `rift_zone_id` | numeric | — | -1 … 24 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `seismic_hazard_index` | numeric | `index` | 0.002402 … 0.4643 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `subduction_zone_id` | numeric | — | -1 … 15 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `tectonic_uplift_rate_m_per_step` | numeric | `m/step` | 0 … 6.821 | measurement | unit | Continuous per-cell field. Rate per simulation step (metres). |
| `volcanic_potential_index` | numeric | `index` | 0.04 … 0.5009 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |

> **Gaps in this domain (4):** `boundary_convergent`, `boundary_divergent`, `boundary_transform`, `last_plate_assignment_change_iteration` — resolved by kind + template only. Add prose to `CURATED` in `layer_docs.js` to close these.

---

## Elevation & landforms

<a id="geomorphology"></a>

**13 layers** · doc coverage: 7 curated · 5 convention · 1 unit · **0 generated (gaps)**.

**How it works.** The land/sea surface itself — final and initial elevation, depression-filled surface, landform class, landmass and island classification, and local relief. Elevation is the single most-used layer and the default on load.

**Produced by:** `cpp/src/engine/core.cpp` / `environment.cpp`, `glacial_landforms.py`, `planet_realism.py`, `sea_level_diagnostics.py`.

**Pipeline stage:** Elevation co-evolves in the feedback loop; landform/landmass classification is a post-pass enricher.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `elevation_m` | numeric | `m` | -9971 … 6297 | measurement | curated | Surface elevation above the planetary datum, in metres. Negative below sea level. The most-used base layer; the default on load. |
| `elevation_m` | stage×16 | `m` | -10790 … 8800 | measurement | curated | Surface elevation above the planetary datum, in metres. Negative below sea level. The most-used base layer; the default on load. |
| `erosion_rate` | numeric | — | 0 … 156.3 | measurement | curated | Local erosion rate from the landscape-evolution solve (model units of depth per step). |
| `filled_elevation_m` | numeric | `m` | 0 … 6297 | measurement | curated | Elevation after depression filling — closed basins raised to their spill level so flow routing has no sinks. Diff against `elevation_m` to see filled depressions. |
| `initial_elevation_m` | numeric | `m` | -10840 … 8751 | provenance | curated | Elevation immediately after tectonic/isostatic setup, before erosion and the feedback loop. Diff against `elevation_m` for net landscape change. Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `landform` | categorical | `category` | 18 classes | classification | curated | Geomorphic landform class (mountain_belt, coastal_plain, trench, …) from elevation and tectonic context. **Classes:** coastal_plain, continental_shelf, delta, fjord, floodplain, glacial_lake, glacial_valley, ice_field, lacustrine_basin, moraine, mountain_belt, open_ocean, rift_valley, river_valley, salt_flat, stable_lowland, trench, volcanic_arc. |
| `landmass_id` | numeric | — | -1 … 47 | identifier | curated | Connected landmass (continent/island) the cell belongs to. Identifier. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `cumulative_tectonic_elevation_change_m` | numeric | `m` | -252.3 … 387.4 | accumulator | convention | Running total accumulated across all simulation stages (monotonic per cell). The per-stage delta lives in the corresponding stage-history ledger. |
| `glacial_landform_index` | numeric | `index` | 0.00182 … 0.7357 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `glacial_landform_system_id` | numeric | — | -1 … 86 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `glacial_landform_type` | categorical | `category` | 7 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** fjord, glacial_lake, glacial_valley, ice_cap, moraine, mountain_glacier, none. |
| `island_class` | categorical | `category` | 5 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** continent, island, islet, large_island, water. |
| `local_relief_m` | stage×16 | `m` | 0 … 10100 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |

---

## Sediment & stratigraphy

<a id="sediment"></a>

**36 layers** · doc coverage: 2 curated · 6 convention · 28 unit · **0 generated (gaps)**.

**How it works.** Erosion, transport, and deposition budgets — hillslope diffusion, fluvial routing (production, deposition, terminal export/capture), sediment thickness, and sequence-stratigraphy inventory. These close the mass balance between the eroding uplands and the depositional basins.

**Produced by:** `sediment_dynamics.py`, `sediment_routing.py`, `sedimentary_resource_systems.py`, `sequence_stratigraphy.py`.

**Pipeline stage:** Runs inside the erosion iterations of the feedback loop.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `sediment_thickness_m` | numeric | `m` | 0 … 3358 | measurement | curated | Accumulated sediment column thickness in metres. |
| `sediment_thickness_m` | stage×16 | `m` | 0 … 3358 | measurement | curated | Accumulated sediment column thickness in metres. |
| `breach_alluvium_entrainment_depth_m` | stage×1600 | `m` | 0 … 40.09 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `breach_bedrock_erosion_depth_m` | stage×1600 | `m` | 0 … 17.75 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `breach_deposition_depth_m` | stage×1600 | `m` | 0.6896 … 39.02 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `breach_sediment_thickness_before_excavation_m` | stage×1600 | `m` | 0 … 1691 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `cumulative_numeric_depression_breach_deposition_m` | numeric | `m` | 0 … 39.98 | accumulator | convention | Running total accumulated across all simulation stages (monotonic per cell). The per-stage delta lives in the corresponding stage-history ledger. |
| `fluvial_sediment_depression_fill_m` | numeric | `m` | 0 … 582.4 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `fluvial_sediment_local_deposition_m` | numeric | `m` | 0 … 424.2 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `fluvial_sediment_local_source_m` | numeric | `m` | 0 … 1379 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `fluvial_sediment_marine_deposition_m` | numeric | `m` | 0 … 402.2 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `fluvial_sediment_routed_incoming_m` | numeric | `m` | 0 … 3351 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `fluvial_sediment_routed_outgoing_m` | numeric | `m` | 0 … 1464 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `fluvial_sediment_routing_event_count` | numeric | `count` | 0 … 6 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `fluvial_sediment_terminal_capture_volume_km3` | numeric | `km³` | 0 … 10420 | measurement | unit | Continuous per-cell field. Volume (cubic kilometres). |
| `fluvial_sediment_terminal_export_m` | numeric | `m` | 0 … 2949 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `fluvial_sediment_terminal_land_deposition_m` | numeric | `m` | 0 … 520.9 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `hillslope_sediment_deposition_m` | numeric | `m` | 0 … 3195 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `hillslope_sediment_incoming_edge_count` | numeric | `count` | 0 … 84 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `hillslope_sediment_net_m` | numeric | `m` | -2918 … 3195 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `hillslope_sediment_outgoing_edge_count` | numeric | `count` | 0 … 89 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `hillslope_sediment_production_m` | numeric | `m` | 0 … 2918 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `moraine_deposition_m` | numeric | `m` | 0 … 2.293 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `overflow_channel_sediment_evacuated_km3` | numeric | `km³` | 0 … 0.009424 | measurement | unit | Continuous per-cell field. Volume (cubic kilometres). |
| `reef_sediment_stress_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `sediment_alluvium_entrainment_m` | numeric | `m` | 0 … 482.2 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `sediment_bedrock_erosion_m` | numeric | `m` | 0 … 3971 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `sediment_deposition_m` | numeric | `m` | 0 … 3358 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `sediment_export_m` | numeric | `m` | 0 … 2949 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `sediment_net_budget_m` | numeric | `m` | -3966 … 3358 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `sediment_production_m` | numeric | `m` | 0 … 3986 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `sediment_routing_deposition_m` | numeric | `m` | 0 … 228.7 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `sediment_routing_export_m` | numeric | `m` | 0 … 1188 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `sediment_routing_load_m` | numeric | `m` | 0 … 1188 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `sediment_routing_path_count` | numeric | `count` | 0 … 2 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `sediment_thickness_before_correction_m` | stage×1600 | `m` | 0 … 2029 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |

---

## Surface hydrology & rivers

<a id="hydrology"></a>

**80 layers** · doc coverage: 14 curated · 40 convention · 22 unit · **4 generated (gaps)**.

**How it works.** Flow routing over the conditioned surface — flow direction and accumulation, drainage basins, depression fill/breach handling, lakes and closed basins, river channels (width/depth/hydraulics), floodplains, and river-network evolution (avulsion, capture). The depression-fill history (1,600 stages) logs every basin correction.

**Produced by:** `cpp/src/engine/hydrology.cpp`, `hydrology_dynamics.py`, `hydrology_realism.py`, `river_hydraulics.py`, `river_channel_morphology.py`, `river_network_evolution.py`, `watershed_diagnostics.py`.

**Pipeline stage:** Flow routing runs every feedback stage after the surface is conditioned; channel morphology is an enricher on the final network.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `basin_id` | numeric | — | 40 … 32767 | identifier | curated | Drainage basin the cell belongs to. Identifier — colour groups a watershed. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `flow_accumulation` | numeric | — | 0 … 4.76e+9 | measurement | curated | Upstream drainage area (in cell-count units) draining through each cell — the classic river-network signal. Extremely heavy-tailed: a handful of trunk cells dwarf everything, so the p2–p98 default colour scale saturates the main stems (see legend clip markers). |
| `flow_to` | numeric | — | -1 … 32317 | identifier | curated | Downstream neighbour each cell drains into (a cell id, or -1 at outlets/oceans). Together with `flow_accumulation` this defines the drainage network. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `flow_velocity_m_s` | numeric | `m/s` | 0 … 2.56 | measurement | curated | Channel flow velocity in m/s from the river-hydraulics solve. |
| `froude_number` | numeric | — | 0 … 0.6511 | measurement | curated | Froude number of channel flow (dimensionless): <1 subcritical, >1 supercritical. Mostly ~0 off the channel network. |
| `hydrologic_surface_elevation_m` | numeric | `m` | 0 … 6297 | measurement | curated | Elevation of the hydrologically-conditioned surface used for flow routing (post-fill/breach). The surface the water budget actually runs on. |
| `is_closed_basin` | categorical | `category` | 2 classes | classification | curated | Whether the cell drains to an internal sink with no path to the ocean (endorheic). **Classes:** False, True. |
| `is_lake` | categorical | `category` | 2 classes | classification | curated | Whether the cell is part of a standing water body (lake). **Classes:** False, True. |
| `is_marine` | stage×16 | — | 0 … 1 | measurement | curated | Whether the cell is marine (ocean/sea). In the per-stage ledger this appears as 0/1 rather than a category. |
| `is_river` | categorical | `category` | 2 classes | classification | curated | Whether river discharge through the cell exceeds the channel threshold. **Classes:** False, True. |
| `is_water` | categorical | `category` | 2 classes | classification | curated | Whether the cell is water (ocean, sea, or lake) rather than land. **Classes:** False, True. |
| `lake_fill_fraction` | numeric | `fraction` | 0 … 1.5 | ratio | curated | How full a lake basin is, 0–1, at the end of the water-budget solve. |
| `manning_roughness_n` | numeric | — | 0 … 0.05749 | measurement | curated | Manning's roughness coefficient n for channel flow (dimensionless). |
| `water_depth_m` | numeric | `m` | 0 … 9971 | measurement | curated | Water column depth (bathymetry for ocean, lake depth for lakes) in metres. |
| `bankfull_discharge_m3_s` | numeric | `m³/s` | 0 … 2046 | measurement | unit | Continuous per-cell field. Volumetric discharge (cubic metres per second). |
| `baseflow_support_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `bed_shear_stress_pa` | numeric | `Pa` | 0 … 288 | measurement | unit | Continuous per-cell field. Stress/pressure (pascals). |
| `breach_elevation_before_m` | stage×1600 | `m` | -6418 … 1411 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `breach_excavation_depth_m` | stage×1600 | `m` | 0 … 6170 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `breach_target_elevation_m` | stage×1600 | `m` | -6418 … 315 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `channel_capacity_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `channel_morphology_class` | categorical | `category` | 5 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** braided_sediment_rich_channel, glacial_outwash_channel, navigable_lowland_channel, non_channel, small_headwater. |
| `channel_slope_index` | numeric | `index` | 0 … 0.7106 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `cumulative_numeric_depression_breach_excavation_m` | numeric | `m` | 0 … 73.3 | accumulator | convention | Running total accumulated across all simulation stages (monotonic per cell). The per-stage delta lives in the corresponding stage-history ledger. |
| `cumulative_numeric_depression_fill_m` | numeric | `m` | 0 … 0 | accumulator | convention | Running total accumulated across all simulation stages (monotonic per cell). The per-stage delta lives in the corresponding stage-history ledger. |
| `depression_component_id` | numeric | — | -1 … 190 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `depression_depth_m` | numeric | `m` | 0 … 3759 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `depression_policy` | categorical | `category` | 5 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** dry_closed, none, overflow_spill, preserved_geologic, temporary_numeric_lake. |
| `depression_sink_cell_id` | numeric | — | -1 … 30660 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `elevation_after_fill_m` | stage×1600 | `m` | 0.1361 … 1010 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `elevation_before_fill_m` | stage×1600 | `m` | -5653 … 760.2 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `equal_filled_raw_downhill_rerouted` | categorical | `category` | 2 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** False, True. |
| `fill_depth_m` | stage×1600 | `m` | 0.02532 … 6663 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `floodplain_connectivity_index` | numeric | `index` | 0 … 0.9691 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `glacier_flow_to` | numeric | — | -1 … 32317 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `hydraulic_flow_regime` | categorical | `category` | 3 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** non_channel, subcritical, swift_subcritical. |
| `hydraulic_navigability_index` | numeric | `index` | 0 … 0.9282 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `hydraulic_radius_m` | numeric | `m` | 0 … 3.815 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `hydrologic_budget_class` | categorical | `category` | 5 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** balanced_budget, evapotranspiration_dominated, marine_budget, runoff_surplus, water_deficit. |
| `hydrologic_budget_region_id` | numeric | — | 0 … 225 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `hydrologic_deficit_mm_y` | numeric | `mm/year` | 0 … 977 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `hydrologic_flow_drop_m` | numeric | `m` | 0 … 6113 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `hydrologic_flow_slope` | numeric | — | 0 … 0.03525 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `hydrologic_potential_evapotranspiration_mm_y` | numeric | `mm/year` | 0 … 1177 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `hydrologic_surface_conditioned` | categorical | `category` | 2 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** False, True. |
| `hydrologic_water_balance_mm_y` | numeric | `mm/year` | 0 … 3521 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `lake_basin_id` | numeric | — | -1 … 190 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `lake_overflows` | categorical | `category` | 2 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** False, True. |
| `navigable_waterway_id` | numeric | — | -1 … 54 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `numeric_depression_breach_event_count` | numeric | `count` | 0 … 3 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `numeric_depression_fill_event_count` | numeric | `count` | 0 … 0 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `numeric_depression_temporary_lake_event_count` | numeric | `count` | 0 … 8 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `overflow_channel_active` | categorical | `category` | 2 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** False, True. |
| `overflow_channel_avulsion_risk` | numeric | — | 0 … 0.4845 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `overflow_channel_incision_m` | numeric | `m` | 0 … 3.575 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `river_avulsion_risk` | numeric | — | 0 … 0.7959 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `river_capture_divide_relief_m` | numeric | `m` | 0 … 1940 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `river_capture_risk` | numeric | — | 0 … 0.7728 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `river_capture_target_basin_id` | numeric | — | -1 … 32236 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `river_capture_target_cell_id` | numeric | — | -1 … 32113 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `river_capture_target_distance_km` | numeric | `km` | 0 … 271.9 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `river_channel_depth_m` | numeric | `m` | 0 … 3.984 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `river_channel_system_id` | numeric | — | -1 … 63 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `river_channel_width_m` | numeric | `m` | 0 … 180.7 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `river_hydraulic_reach_id` | numeric | — | -1 … 63 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `river_mouth_port_index` | numeric | `index` | 0 … 0.8864 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `river_navigability_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `river_network_instability_index` | numeric | `index` | 0 … 0.7959 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `river_valley_route_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `runoff_budget_consistency_index` | numeric | `index` | 1 … 1 | diagnostic | convention | Conservation residual / mass-balance check. Should sit near zero everywhere; large magnitudes flag a budget that does not close and are a debugging signal rather than terrain. |
| `runoff_budget_residual_mm_y` | numeric | `mm/year` | 0 … 0 | diagnostic | convention | Conservation residual / mass-balance check. Should sit near zero everywhere; large magnitudes flag a budget that does not close and are a debugging signal rather than terrain. |
| `runoff_generation_fraction` | numeric | `fraction` | 0 … 1 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `runoff_mm_y` | numeric | `mm/year` | 0 … 3521 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `runoff_mm_y` | stage×16 | `mm/year` | 0 … 3821 | measurement | unit | Per-stage numeric field (scrub the stage control). Annual depth flux (millimetres per year). |
| `soil_drainage_index` | numeric | `index` | 0 … 0.9159 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `spill_elevation_m` | numeric | `m` | 0 … 6297 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `spill_to` | numeric | — | -1 … 32223 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `stream_power_index` | numeric | `index` | 0 … 0.4533 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `subterranean_drainage_fraction` | numeric | `fraction` | 0 … 0.6267 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `water_body_type` | categorical | `category` | 5 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** continental_shelf, fresh_lake, land, ocean, saline_basin. |

> **Gaps in this domain (4):** `hydrologic_flow_slope`, `overflow_channel_avulsion_risk`, `river_avulsion_risk`, `river_capture_risk` — resolved by kind + template only. Add prose to `CURATED` in `layer_docs.js` to close these.

---

## Water budget & atmospheric moisture

<a id="water-budget"></a>

**27 layers** · doc coverage: 3 curated · 9 convention · 15 unit · **0 generated (gaps)**.

**How it works.** The coupled precipitation → evapotranspiration → infiltration → runoff balance and the atmospheric-moisture transport that feeds it (orographic rainout, moisture recycling, vapor budget, water surplus/deficit). The `hydrologic_water_budget_history` (16 stages) is the per-stage snapshot of this solve.

**Produced by:** `cpp/src/engine/climate.cpp`, `climate_dynamics.py`, `hydrology_budget.py`.

**Pipeline stage:** Recomputed each feedback stage (16 recomputes over 8 clock stages).

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `mean_seasonal_wind_speed` | numeric | — | 0.7903 … 0.9682 | measurement | curated | Mean wind speed over the seasonal cycle (magnitude of the monthly wind vectors). |
| `precipitation_mm_y` | numeric | `mm/year` | 33.33 … 5007 | measurement | curated | Mean annual precipitation, mm/year. Monthly detail in `precipitation_monthly_mm`. |
| `precipitation_mm_y` | stage×16 | `mm/year` | 30.22 … 5007 | measurement | curated | Mean annual precipitation, mm/year. Monthly detail in `precipitation_monthly_mm`. |
| `actual_evapotranspiration_mm_y` | numeric | `mm/year` | 0 … 622.2 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `actual_evapotranspiration_mm_y` | stage×16 | `mm/year` | 0 … 635.1 | measurement | unit | Per-stage numeric field (scrub the stage control). Annual depth flux (millimetres per year). |
| `advected_moisture_factor` | numeric | — | 0.8209 … 1.198 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `climatic_water_deficit_mm_y` | numeric | `mm/year` | 0 … 929.6 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `climatic_water_surplus_mm_y` | numeric | `mm/year` | 0 … 3776 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `humidity_transport_index` | numeric | `index` | 0.003 … 1.35 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `infiltration_capacity_index` | numeric | `index` | 0 … 0.7884 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `infiltration_capacity_index` | stage×16 | `index` | 0 … 0.7884 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `infiltration_mm_y` | numeric | `mm/year` | 0 … 384.5 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `infiltration_mm_y` | stage×16 | `mm/year` | 0 … 391.3 | measurement | unit | Per-stage numeric field (scrub the stage control). Annual depth flux (millimetres per year). |
| `moisture_convergence_mm_y` | numeric | `mm/year` | 0 … 4645 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `orographic_factor` | numeric | — | 1 … 1.42 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `orographic_rainout_mm_y` | numeric | `mm/year` | 3.00e-4 … 947.6 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `potential_evapotranspiration_mm_y` | numeric | `mm/year` | 0 … 1286 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `potential_evapotranspiration_mm_y` | stage×16 | `mm/year` | 0 … 1191 | measurement | unit | Per-stage numeric field (scrub the stage control). Annual depth flux (millimetres per year). |
| `precipitation_monthly_mm` | month×12 | `mm` | 1.667 … 619 | measurement | unit | Monthly numeric field (scrub the month control). Depth (millimetres). |
| `precipitation_recycling_fraction` | numeric | `fraction` | 0.0632 … 0.4102 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `rain_shadow_factor` | numeric | — | 0.52 … 1 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `residual_mm_y` | stage×16 | `mm/year` | 0 … 0 | diagnostic | convention | Conservation residual / mass-balance check. Should sit near zero everywhere; large magnitudes flag a budget that does not close and are a debugging signal rather than terrain. |
| `vapor_budget_residual_mm_y` | numeric | `mm/year` | 0 … 0 | diagnostic | convention | Conservation residual / mass-balance check. Should sit near zero everywhere; large magnitudes flag a budget that does not close and are a debugging signal rather than terrain. |
| `vapor_deficit_mm_y` | numeric | `mm/year` | 0 … 943 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `vapor_evaporation_mm_y` | numeric | `mm/year` | 0 … 1715 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `water_balance_mm_y` | stage×16 | `mm/year` | 0 … 3821 | measurement | unit | Per-stage numeric field (scrub the stage control). Annual depth flux (millimetres per year). |
| `water_budget_runoff_mm_y` | numeric | `mm/year` | 0 … 3521 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |

---

## Groundwater, aquifers & karst

<a id="groundwater"></a>

**30 layers** · doc coverage: 0 curated · 17 convention · 13 unit · **0 generated (gaps)**.

**How it works.** Subsurface water — recharge, hydraulic head, lateral flow between cells, aquifer classification and productivity/quality/storage indices, vadose-zone retention, spring discharge, and karst/cave development potential. Includes mass-balance residual diagnostics for the groundwater solve.

**Produced by:** `groundwater_flow.py`, `aquifer_resources.py`, `karst_diagnostics.py`.

**Pipeline stage:** Enricher pass over the final surface-hydrology and climate state.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `aquifer_class` | categorical | `category` | 6 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** fossil_or_slow_recharge_aquifer, local_fresh_aquifer, major_fresh_aquifer, marine_excluded, perched_recharge_zone, poor_aquifer. |
| `aquifer_extraction_risk_index` | numeric | `index` | 0 … 0.5584 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `aquifer_productivity_index` | numeric | `index` | 0 … 0.7876 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `aquifer_quality_index` | numeric | `index` | 0 … 0.9597 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `aquifer_storage_index` | numeric | `index` | 0 … 0.908 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `aquifer_system_id` | numeric | — | -1 … 1962 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `cave_development_index` | numeric | `index` | 0 … 0.7303 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `groundwater_available_volume_km3_y` | numeric | `km³/year` | 0 … 21 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `groundwater_discharge_km3_y` | numeric | `km³/year` | 0 … 6.693 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `groundwater_discharge_mm_y` | numeric | `mm/year` | 0 … 430 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `groundwater_flow_mass_balance_residual_km3_y` | numeric | `km³/year` | 0 … 0 | diagnostic | convention | Conservation residual / mass-balance check. Should sit near zero everywhere; large magnitudes flag a budget that does not close and are a debugging signal rather than terrain. |
| `groundwater_flow_regime` | categorical | `category` | 7 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** discharge_zone, excluded, lowland_discharge, recharge_mound, recharge_throughflow, stagnant_or_low_yield, throughflow. |
| `groundwater_flow_system_id` | numeric | — | -1 … 1962 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `groundwater_flow_to_cell_id` | numeric | — | -1 … 32317 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `groundwater_gradient_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `groundwater_hydraulic_head_m` | numeric | `m` | -3267 … 6098 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `groundwater_internal_lateral_outflow_km3_y` | numeric | `km³/year` | 0 … 4.186 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `groundwater_lateral_flow_km3_y` | numeric | `km³/year` | 0 … 4.186 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `groundwater_lateral_inflow_km3_y` | numeric | `km³/year` | 0 … 20.18 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `groundwater_recharge_fraction` | numeric | `fraction` | 0 … 0.7479 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `groundwater_recharge_km3_y` | numeric | `km³/year` | 0 … 4.209 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `groundwater_recharge_mass_balance_residual_mm_y` | numeric | `mm/year` | 0 … 0 | diagnostic | convention | Conservation residual / mass-balance check. Should sit near zero everywhere; large magnitudes flag a budget that does not close and are a debugging signal rather than terrain. |
| `groundwater_recharge_mm_y` | numeric | `mm/year` | 0 … 270.4 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `groundwater_recharge_source_infiltration_mm_y` | numeric | `mm/year` | 0 … 384.5 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `groundwater_retained_storage_km3_y` | numeric | `km³/year` | 0 … 19.44 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `karst_potential_index` | numeric | `index` | 0 … 0.8012 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `karst_system_id` | numeric | — | -1 … 132 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `spring_discharge_index` | numeric | `index` | 0 … 0.9476 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `vadose_zone_retention_km3_y` | numeric | `km³/year` | 0 … 2.53 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `vadose_zone_retention_mm_y` | numeric | `mm/year` | 0 … 162.5 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |

---

## Climate & atmosphere

<a id="climate"></a>

**38 layers** · doc coverage: 5 curated · 17 convention · 14 unit · **2 generated (gaps)**.

**How it works.** Temperature, Köppen climate class, the atmospheric-circulation cell each cell sits in, winds, the full surface-energy balance (insolation, shortwave/longwave, greenhouse trapping, albedo, radiative-equilibrium temperatures), seasonality (dry/wet/growing/frost month counts, seasonal ranges), continentality, and monsoon indices.

**Produced by:** `cpp/src/engine/climate.cpp`, `climate_dynamics.py`, `climate_energy.py`, `climate_continentality.py`, `climate_realism.py`.

**Pipeline stage:** Recomputed each feedback stage; energy-balance and seasonality indices are enrichers on the converged climate.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `climate_class` | categorical | `category` | 17 classes | classification | curated | Köppen–Geiger climate class (Af, BWh, Cfb, ET, …). 17 classes on the earthlike run. **Classes:** Af, Am, Aw, BSh, BSk, BWh, BWk, Cfa, Cfb, Cwa, Cwb, Cwc, Dfa, Dfb, Dfc, EF, ET. |
| `temperature_c` | numeric | `°C` | -59.16 … 30.46 | measurement | curated | Mean annual surface air temperature in °C. Monthly detail is in the `temperature_monthly_c` monthly layer. |
| `temperature_c` | stage×16 | `°C` | -75.4 … 31.24 | measurement | curated | Mean annual surface air temperature in °C. Monthly detail is in the `temperature_monthly_c` monthly layer. |
| `wind_east` | numeric | — | -0.9766 … 0.9874 | measurement | curated | Eastward (zonal) component of the mean surface wind. Positive = toward the east. Pair with `wind_north` for the full vector. |
| `wind_north` | numeric | — | -0.2334 … 0.2334 | measurement | curated | Northward (meridional) component of the mean surface wind. Positive = toward the north. Pair with `wind_east`. |
| `absorbed_shortwave_w_m2` | numeric | `W/m²` | 31.2 … 340.4 | measurement | unit | Continuous per-cell field. Energy flux density (watts per square metre). |
| `atmospheric_cell` | categorical | `category` | 4 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** midlatitude_westerly, polar_cell, subtropical_high, tropical_ascent. |
| `climate_continentality_region_id` | numeric | — | 0 … 64 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `climate_energy_stress_index` | numeric | `index` | 1.20e-5 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `continentality_index` | numeric | `index` | 5.00e-6 … 0.8952 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `dry_season_months` | numeric | `months` | 0 … 12 | seasonal | convention | Seasonal month count (0–12) derived from the monthly climate series. |
| `energy_balance_residual_c` | numeric | `°C` | -8.745 … 71.48 | diagnostic | convention | Conservation residual / mass-balance check. Should sit near zero everywhere; large magnitudes flag a budget that does not close and are a debugging signal rather than terrain. |
| `frost_months` | numeric | `months` | 0 … 12 | seasonal | convention | Seasonal month count (0–12) derived from the monthly climate series. |
| `greenhouse_trapping_w_m2` | numeric | `W/m²` | 9.82 … 112.3 | measurement | unit | Continuous per-cell field. Energy flux density (watts per square metre). |
| `growing_season_months` | numeric | `months` | 0 … 12 | seasonal | convention | Seasonal month count (0–12) derived from the monthly climate series. |
| `low_seasonal_insolation_w_m2` | numeric | `W/m²` | 115 … 396.8 | measurement | unit | Continuous per-cell field. Energy flux density (watts per square metre). |
| `net_radiative_balance_w_m2` | numeric | `W/m²` | -181.9 … 43.51 | measurement | unit | Continuous per-cell field. Energy flux density (watts per square metre). |
| `no_greenhouse_equilibrium_temperature_c` | numeric | `°C` | -120 … 5.202 | measurement | unit | Continuous per-cell field. Temperature (degrees Celsius). |
| `orbital_insolation_variability_index` | numeric | `index` | 0.01607 … 0.5634 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `outgoing_longwave_w_m2` | numeric | `W/m²` | 114.1 … 462.5 | measurement | unit | Continuous per-cell field. Energy flux density (watts per square metre). |
| `peak_seasonal_insolation_w_m2` | numeric | `W/m²` | 192.8 … 433.7 | measurement | unit | Continuous per-cell field. Energy flux density (watts per square metre). |
| `radiative_equilibrium_temperature_c` | numeric | `°C` | -107.4 … 27.51 | measurement | unit | Continuous per-cell field. Temperature (degrees Celsius). |
| `seasonal_aridity_index` | numeric | `index` | 0 … 0.9113 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `seasonal_humidity_regime` | categorical | `category` | 3 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** arid_seasonal, humid_stable, summer_wet. |
| `seasonal_insolation_range_w_m2` | numeric | `W/m²` | 6.426 … 141.3 | measurement | unit | Continuous per-cell field. Energy flux density (watts per square metre). |
| `seasonal_precipitation_range_mm` | numeric | `mm` | 0.2652 … 593.2 | measurement | unit | Continuous per-cell field. Depth (millimetres). |
| `seasonal_wind_reversal_index` | numeric | `index` | 0 … 0.0459 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `surface_albedo_index` | numeric | `index` | 0.1212 … 0.86 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `surface_albedo_regime` | categorical | `category` | 8 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** arid_high_albedo, cold_sparse_cover, forest_canopy, ice_albedo, mixed_land, open_ocean, seasonal_grassland, shallow_ocean. |
| `surface_pressure_anomaly_hpa` | numeric | `hPa` | -6.723 … 6.241 | measurement | unit | Continuous per-cell field. Pressure (hectopascals). |
| `temperature_monthly_c` | month×12 | `°C` | -70.36 … 34.06 | measurement | unit | Monthly numeric field (scrub the month control). Temperature (degrees Celsius). |
| `top_of_atmosphere_insolation_w_m2` | numeric | `W/m²` | 157.9 … 401.8 | measurement | unit | Continuous per-cell field. Energy flux density (watts per square metre). |
| `upwind_ocean_fetch_km` | numeric | `km` | 0 … 2303 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `vertical_velocity_index` | numeric | `index` | -0.3925 … 0.644 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wet_season_months` | numeric | `months` | 0 … 12 | seasonal | convention | Seasonal month count (0–12) derived from the monthly climate series. |
| `wind_divergence_index` | numeric | `index` | -0.4563 … 0.4823 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wind_monthly_east` | month×12 | — | -0.9638 … 0.9675 | measurement | generated | Monthly numeric field (scrub the month control). No documented unit for this field — inspect a cell for context. |
| `wind_monthly_north` | month×12 | — | -0.4722 … 0.6599 | measurement | generated | Monthly numeric field (scrub the month control). No documented unit for this field — inspect a cell for context. |

> **Gaps in this domain (2):** `wind_monthly_east`, `wind_monthly_north` — resolved by kind + template only. Add prose to `CURATED` in `layer_docs.js` to close these.

---

## Oceans & coasts

<a id="ocean"></a>

**31 layers** · doc coverage: 2 curated · 25 convention · 3 unit · **1 generated (gaps)**.

**How it works.** Ocean surface currents (direction/speed/temperature/regime and transport), heat transport, upwelling, marine influence and regions, continental shelves, coral reefs (growth, bleaching risk, wave exposure, island support), coastal navigability, protected bays, and fisheries.

**Produced by:** `ocean_circulation.py`, `cpp/src/engine/ocean.cpp`, `reef_diagnostics.py`, `sea_level_diagnostics.py`.

**Pipeline stage:** Ocean circulation runs with the climate solve; reef/coast enrichers run on the final state.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `ocean_current_east` | numeric | — | -1 … 1 | measurement | curated | Eastward component of the surface ocean current. Pair with `ocean_current_north`. |
| `ocean_current_north` | numeric | — | -0.5039 … 0.5039 | measurement | curated | Northward component of the surface ocean current. Pair with `ocean_current_east`. |
| `coastal_navigability_index` | numeric | `index` | 0 … 0.94 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `coastal_route_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `distance_to_marine_water_km` | numeric | `km` | 0 … 2740 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `fishery_productivity_index` | numeric | `index` | 0 … 0.7544 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `marine_chokepoint_id` | numeric | — | -1 … 1124 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `marine_influence_class` | categorical | `category` | 5 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** coastal, continental_core, interior, marine, maritime_influenced. |
| `marine_region_id` | numeric | — | -1 … 0 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `ocean_current_convergence_index` | numeric | `index` | -1 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `ocean_current_moisture_factor` | numeric | — | 0.8919 … 1.139 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `ocean_current_poleward_index` | numeric | `index` | -0.5039 … 0.5039 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `ocean_current_regime` | categorical | `category` | 10 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** cold_equatorward_current, cold_poleward_current, cold_zonal_current, neutral_equatorward_current, neutral_poleward_current, neutral_zonal_current, non_marine, warm_equatorward_current, warm_poleward_current, warm_zonal_current. |
| `ocean_current_speed_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `ocean_current_system_id` | numeric | — | -1 … 69 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `ocean_current_temperature_c` | numeric | `°C` | -3.088 … 3.088 | measurement | unit | Continuous per-cell field. Temperature (degrees Celsius). |
| `ocean_current_transport_alignment` | numeric | — | 0 … 1 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `ocean_current_transport_distance_km` | numeric | `km` | 0 … 277 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `ocean_current_transport_target_cell_id` | numeric | — | -1 … 32764 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `ocean_heat_transport_index` | numeric | `index` | -0.02105 … 0.3458 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `ocean_upwelling_index` | numeric | `index` | 0 … 0.6613 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `oceanic_crust_aging_event_count` | numeric | `count` | 0 … 6 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `oceanic_crust_rejuvenation_event_count` | numeric | `count` | 0 … 6 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `oceanic_humidity_availability_index` | numeric | `index` | 0.08936 … 0.9052 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `protected_bay_index` | numeric | `index` | 0 … 0.8995 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `reef_bleaching_risk_index` | numeric | `index` | 0 … 0.3396 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `reef_growth_index` | numeric | `index` | 0 … 0.8427 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `reef_island_support_index` | numeric | `index` | 0 … 0.628 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `reef_system_id` | numeric | — | -1 … 196 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `reef_type` | categorical | `category` | 5 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** atoll_reef, barrier_reef, cold_water_reef, fringing_reef, none. |
| `reef_wave_exposure_index` | numeric | `index` | 0 … 0.903 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |

> **Gaps in this domain (1):** `ocean_current_transport_alignment` — resolved by kind + template only. Add prose to `CURATED` in `layer_docs.js` to close these.

---

## Cryosphere (ice, glaciers, permafrost)

<a id="cryosphere"></a>

**25 layers** · doc coverage: 2 curated · 14 convention · 9 unit · **0 generated (gaps)**.

**How it works.** Ice sheets and glaciers (thickness, velocity, surface mass balance, flowlines, driving stress, basal sliding), glacial erosion/deposition and sediment transport, moraines, permafrost classes and extent, active-layer depth, and ground-ice content.

**Produced by:** `cryosphere_dynamics.py`, `cryosphere_flow.py`, `cryosphere_stability.py`, `glacial_landforms.py`, `permafrost_diagnostics.py`.

**Pipeline stage:** Cryosphere dynamics couple into the feedback loop; landform/permafrost classification is a post-pass.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `ice_thickness_m` | numeric | `m` | 0 … 2021 | measurement | curated | Ice-sheet / glacier thickness in metres. |
| `ice_thickness_m` | stage×16 | `m` | 0 … 2039 | measurement | curated | Ice-sheet / glacier thickness in metres. |
| `active_layer_depth_m` | numeric | `m` | 0 … 0.4403 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `basal_sliding_index` | numeric | `index` | 0 … 0.8783 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `deglaciation_age_ka` | numeric | `ka` | 0 … 82 | measurement | unit | Continuous per-cell field. Age (thousands of years before present). |
| `glacial_deposition_index` | numeric | `index` | 0 … 0.95 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `glacial_erosion_intensity_index` | numeric | `index` | 0.007126 … 0.8305 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `glacial_erosion_m` | numeric | `m` | 0 … 85 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `glacial_meltwater_index` | numeric | `index` | 0 … 0.8016 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `glacial_sediment_deposition_m` | numeric | `m` | 0 … 201.5 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `glacial_sediment_incoming_transfer_count` | numeric | `count` | 0 … 11 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `glacial_sediment_net_m` | numeric | `m` | -23.8 … 201.5 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `glacial_sediment_outgoing_transfer_count` | numeric | `count` | 0 … 1 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `glacial_sediment_production_m` | numeric | `m` | 0 … 23.8 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `ground_ice_content_index` | numeric | `index` | 0 … 0.9053 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `ice_flowline_driving_stress_kpa` | numeric | `kPa` | 0 … 336.3 | measurement | unit | Continuous per-cell field. Stress/pressure (kilopascals). |
| `ice_flowline_flux_km3_y` | numeric | `km³/year` | 0 … 31.59 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `ice_flowline_path_count` | numeric | `count` | 0 … 1 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `ice_flowline_strain_heating_index` | numeric | `index` | 0 … 0.9084 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `ice_sheet_id` | numeric | — | -1 … 10 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `ice_surface_mass_balance_m_y` | numeric | `m/year` | 0 … 2.445 | diagnostic | convention | Conservation residual / mass-balance check. Should sit near zero everywhere; large magnitudes flag a budget that does not close and are a debugging signal rather than terrain. |
| `ice_velocity_m_y` | numeric | `m/year` | 0 … 209.6 | measurement | unit | Continuous per-cell field. Annual rate (metres per year). |
| `permafrost_class` | categorical | `category` | 6 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** continuous_permafrost, discontinuous_permafrost, ice_cemented_permafrost, no_permafrost, seasonal_frost, sporadic_permafrost. |
| `permafrost_extent_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `permafrost_region_id` | numeric | — | -1 … 13 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |

---

## Soils

<a id="soil"></a>

**14 layers** · doc coverage: 2 curated · 9 convention · 3 unit · **0 generated (gaps)**.

**How it works.** Soil profile development — type and texture class, depth, horizon count, pH, organic-matter fraction, drainage, erodibility, salinity, moisture, and derived agronomic fertility / agricultural potential.

**Produced by:** `soil_dynamics.py`, `land_use_zones.py` (agricultural zoning).

**Pipeline stage:** Enricher pass over the final climate, hydrology, and lithology.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `fertility` | numeric | — | 0 … 1 | measurement | curated | Agronomic fertility score combining soil, climate, and water availability. |
| `soil_type` | categorical | `category` | 11 classes | classification | curated | Soil classification from climate, parent material, and drainage. **Classes:** alluvial, arid, boreal, none, saline, temperate, thin_mountain, tropical, tundra, volcanic, wetland. |
| `agricultural_potential_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `agricultural_zone_id` | numeric | — | -1 … 97 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `soil_depth_m` | numeric | `m` | 0 … 3.346 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `soil_erodibility_index` | numeric | `index` | 0 … 0.7857 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `soil_horizon_count` | numeric | `count` | 0 … 4 | measurement | unit | Continuous per-cell field. Integer count. |
| `soil_moisture_index` | numeric | `index` | 0 … 0.9295 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `soil_organic_matter_fraction` | numeric | `fraction` | 0 … 0.35 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `soil_ph` | numeric | `pH` | 4.88 … 8.026 | measurement | unit | Continuous per-cell field. Acidity/alkalinity (pH scale, ~0–14). |
| `soil_profile_development_index` | numeric | `index` | 0 … 0.86 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `soil_profile_id` | numeric | — | -1 … 8852 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `soil_salinity_index` | numeric | `index` | 0 … 0.3378 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `soil_texture_class` | categorical | `category` | 10 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** alluvial_silt, clay, clay_loam, glacial_till, loam, none, peat, sandy_loam, silt_loam, volcanic_ash. |

---

## Ecology, biomes & disturbance

<a id="ecology"></a>

**35 layers** · doc coverage: 1 curated · 31 convention · 2 unit · **1 generated (gaps)**.

**How it works.** Biome classification and ecotones, vegetation succession and biomass, net primary productivity, species richness/endemism/guilds and range fragmentation, wetlands (extent, hydrology, connectivity, type), and disturbance regimes (wildfire ignition/spread/fuel, ecosystem disturbance pressure).

**Produced by:** `biome_dynamics.py`, `biome_ecotones.py`, `biome_realism.py`, `ecosystem_dynamics.py`, `species_ranges.py`, `wildfire_disturbance.py`, `wetland_diagnostics.py`.

**Pipeline stage:** Enricher passes over the final climate/soil/hydrology state.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `biome` | categorical | `category` | 15 classes | classification | curated | Whittaker-style biome classification from temperature, moisture, and elevation. **Classes:** alpine, boreal_forest, cold_desert, continental_shelf, hot_desert, ice_cap, lake, ocean, savanna, temperate_forest, temperate_grassland, tropical_rainforest, tropical_seasonal_forest, tundra, wetland. |
| `biome_confidence_index` | numeric | `index` | 0.3658 … 0.9757 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `biome_ecotone_confidence` | numeric | — | 0 … 0.9757 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `biome_ecotone_region_id` | numeric | — | -1 … 250 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `biome_ecotone_type` | categorical | `category` | 9 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** cloud_forest, cold_desert, cold_steppe, dry_forest, mangrove, mediterranean_scrub, none, swamp, taiga. |
| `biome_transition_zone` | categorical | `category` | 2 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** False, True. |
| `dominant_species_guild` | categorical | `category` | 10 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** alpine_tundra_specialist, canopy_tree, desert_specialist, freshwater_fish, grassland_grazer, large_predator, mangrove_coastal_bird, marine_fish, reef_builder, wetland_amphibian. |
| `ecosystem_disturbance_pressure_index` | numeric | `index` | 0 … 0.5814 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `ecotone_index` | numeric | `index` | 0 … 0.9481 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `fire_frequency_index` | numeric | `index` | 0 … 0.6208 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `forest_growth_index` | numeric | `index` | 0 … 0.7947 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `primary_productivity_index` | numeric | `index` | 0.1759 … 0.9091 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `species_composition_confidence_index` | numeric | `index` | 0.4086 … 0.808 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `species_endemism_index` | numeric | `index` | 0 … 0.9459 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `species_guild_richness_count` | numeric | `count` | 0 … 5 | measurement | unit | Continuous per-cell field. Integer count. |
| `species_habitat_suitability_index` | numeric | `index` | 0.4333 … 0.9906 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `species_range_fragmentation_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `species_richness_index` | numeric | `index` | 0.0676 … 0.8222 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `vegetation_biomass_index` | numeric | `index` | 0 … 0.8995 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `vegetation_recovery_years` | numeric | `years` | 25 … 68 | measurement | unit | Continuous per-cell field. Duration (years). |
| `vegetation_succession_stage` | categorical | `category` | 7 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** aquatic_primary_productivity, barren_ice, disturbance_mosaic, early_successional_cover, mature_closed_canopy, mid_successional_cover, pioneer_sparse_cover. |
| `wetland_coastal_flag` | categorical | `category` | 2 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** False, True. |
| `wetland_connectivity_index` | numeric | `index` | 0 … 0.7057 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wetland_ecotone_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wetland_extent_index` | numeric | `index` | 0 … 0.8962 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wetland_hydrology_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wetland_soil_saturation_index` | numeric | `index` | 0 … 0.9065 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wetland_system_id` | numeric | — | -1 … 359 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `wetland_system_type` | categorical | `category` | 8 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** delta_wetland, floodplain_wetland, freshwater_swamp, lacustrine_wetland, mangrove, none, peatland, tidal_marsh. |
| `wildfire_disturbance_regime` | categorical | `category` | 7 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** fragmented_firebreak_mosaic, ice_or_barren_firebreak, low_fire_activity, non_burnable_water, seasonal_surface_fire, sparse_fuel, wind_driven_crown_fire. |
| `wildfire_firebreak_index` | numeric | `index` | 0.09706 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wildfire_fuel_continuity_index` | numeric | `index` | 0 … 0.645 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wildfire_ignition_potential_index` | numeric | `index` | 0 … 0.5298 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wildfire_spread_risk_index` | numeric | `index` | 0 … 0.4391 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wildfire_wind_alignment_index` | numeric | `index` | 0.9615 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |

> **Gaps in this domain (1):** `biome_ecotone_confidence` — resolved by kind + template only. Add prose to `CURATED` in `layer_docs.js` to close these.

---

## Resources & economic geology

<a id="resources"></a>

**15 layers** · doc coverage: 1 curated · 14 convention · 0 unit · **0 generated (gaps)**.

**How it works.** Primary resource association per cell plus the systems that generate them — ore genesis (metallogenic fertility, structural control, hydrothermal alteration, placers), petroleum systems (source rock, maturation, migration, traps), mining/land-use zoning, and reserve-potential indices.

**Produced by:** `ore_genesis.py`, `petroleum_migration.py`, `commodity_resources.py`, `resource_dynamics.py`, `land_use_zones.py`.

**Pipeline stage:** Enricher passes over the final geology, tectonics, and sediment state.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `resource` | categorical | `category` | 8 classes | classification | curated | Dominant natural-resource association for the cell (craton_iron_gold, sedimentary_fuels, …). **Classes:** coastal_fisheries, craton_iron_gold, evaporites, fertile_alluvium, geothermal, none, sedimentary_fuels, volcanic_arc_metals. |
| `hydrothermal_alteration_index` | numeric | `index` | 0.009601 … 0.7571 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `metallogenic_fertility_index` | numeric | `index` | 0.02044 … 0.9514 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `mining_potential_index` | numeric | `index` | 0 … 0.8348 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `mining_zone_id` | numeric | — | -1 … 187 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `ore_genesis_potential_index` | numeric | `index` | 0.0476 … 0.7762 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `ore_genesis_system_id` | numeric | — | -1 … 229 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `ore_structural_control_index` | numeric | `index` | 3.85e-4 … 0.5358 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `petroleum_accumulation_index` | numeric | `index` | 0 … 0.6078 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `petroleum_maturation_index` | numeric | `index` | 0 … 0.709 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `petroleum_migration_path_index` | numeric | `index` | 0 … 0.6569 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `petroleum_source_rock_index` | numeric | `index` | 0 … 0.9274 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `petroleum_system_id` | numeric | — | -1 … 1189 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `petroleum_trap_integrity_index` | numeric | `index` | 0 … 0.5489 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `placer_concentration_index` | numeric | `index` | 8.18e-4 … 0.8599 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |

---

## Human & political geography

<a id="human"></a>

**20 layers** · doc coverage: 2 curated · 18 convention · 0 unit · **0 generated (gaps)**.

**How it works.** The human layer — settlement scoring, ports and harbours, transport routes and corridors, navigability classes, natural frontiers, and cultural / linguistic / political / territorial regions. Region ids partition the map into named entities.

**Produced by:** `settlement_routes.py`, `port_sites.py`, `route_corridors.py`, `navigability_diagnostics.py`, `cultural_geography.py`, `political_geography.py`, `territorial_geography.py`, `natural_frontiers.py`, `civilization_geography.py`.

**Pipeline stage:** Final enricher passes; the history/economy models (in `sections.json`, not per-cell layers) build on top.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `navigability_index` | numeric | `index` | 0 … 1 | index | curated | How navigable the cell is for water/land transport, 0–1. |
| `settlement_score` | numeric | — | 0 … 1 | measurement | curated | Composite habitability/attractiveness score used to seed settlements. |
| `culture_region_id` | numeric | — | -1 … 9 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `harbor_suitability_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `language_region_id` | numeric | — | -1 … 8 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `mountain_pass_route_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `natural_frontier_id` | numeric | — | -1 … 13 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `natural_frontier_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `natural_frontier_type` | categorical | `category` | 6 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** dense_forest, desert, ice, mountain, none, river. |
| `navigability_class` | categorical | `category` | 6 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** coastal_corridor, harbor, non_navigable, river_corridor, river_mouth, transport_chokepoint. |
| `oasis_route_index` | numeric | `index` | 0 … 0.607 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `political_region_id` | numeric | — | -1 … 9 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `port_site_id` | numeric | — | -1 … 926 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `port_site_type` | categorical | `category` | 4 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** none, protected_bay_port, river_mouth_port, strait_port. |
| `port_suitability_index` | numeric | `index` | 0 … 0.9119 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `route_corridor_id` | numeric | — | -1 … 84 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `route_corridor_index` | numeric | `index` | 0 … 1 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `route_corridor_type` | categorical | `category` | 4 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** coastal_corridor, mountain_pass_corridor, none, river_valley_corridor. |
| `strait_access_index` | numeric | `index` | 0 … 0.8331 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `transport_chokepoint_index` | numeric | `index` | 0 … 0.8602 | index | convention | Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |

---

## Status & gaps summary

**Documentation gaps.** 19 of 446 layers (4.3%) fall to the generated tier — coordinate components, a few dimensionless physics quantities, and stage-ledger coordinates. Listed per domain above; each is a one-line addition to `CURATED`.

**Data-model gaps** (from the pipeline review — see [layers_review.md](layers_review.md) for detail):

- **Silent drops:** high-cardinality string fields (`healpix_like_pixel_code`, `s2_like_token`) become no layer *and* no skip record; reachable only via the cell inspector. *(review F2)*
- **Code/name mismatch:** per-stage `lithology` ships as numeric codes 0–6 while `cells/lithology` uses alphabetical names; no code→name table is emitted. *(review F3)*
- **Identifiers as gradients:** ~30 `*_id` / `*_to` layers render as continuous ramps; flagged with the `identifier` role here and in the UI. *(review F8)*
- **Heavy-tailed scales:** layers like `flow_accumulation` (max ≫ p98) saturate under the p2–p98 ramp; the legend now shows `≥`/`≤` clip markers. *(review F6, fixed)*
- **Degenerate ranges:** 62 layers have p2 == p98 (mass-zero fields); the colour scale silently falls back to min/max. *(review F6)*

**How to close a gap.** Add the field to `CURATED` in [`layer_docs.js`](../src/magic_geo/debug_ui/layer_docs.js) (one line). The docs card, help-overlay coverage box, and this reference all read from that one map, so a new entry propagates everywhere on regeneration.
