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
- **`categorical_stage`** — a string/bool field inside such a record family with ≤ 64 distinct
  values. One colour per class, scrubbed by stage.

Every layer carries **props** used throughout this doc: its `id` (`source/name`; monthly layers
use `monthly/name`), `kind`, inferred
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

World: **earthlike_mvp** · 4,096 cells · mesh `fibonacci_sphere` · scope `full`.

**439 layers** total — 361 numeric, 47 categorical, 27 per-stage, 4 monthly.

Documentation coverage:

| Tier | Count | Share |
| --- | --: | --: |
| curated | 174 | 39.6% |
| convention | 181 | 41.2% |
| unit | 72 | 16.4% |
| generated | 12 | 2.7% |

Layers by domain (documentation gaps = generated tier):

| Domain | Layers | Curated | Generated (gaps) |
| --- | --: | --: | --: |
| [Mesh & geometry](#geometry) | 40 | 14 | 7 |
| [Tectonics & solid earth](#tectonics) | 37 | 20 | 1 |
| [Elevation & landforms](#geomorphology) | 13 | 10 | 0 |
| [Sediment & stratigraphy](#sediment) | 35 | 8 | 0 |
| [Surface hydrology & rivers](#hydrology) | 78 | 34 | 2 |
| [Water budget & atmospheric moisture](#water-budget) | 27 | 14 | 0 |
| [Groundwater, aquifers & karst](#groundwater) | 30 | 8 | 0 |
| [Climate & atmosphere](#climate) | 38 | 19 | 0 |
| [Oceans & coasts](#ocean) | 31 | 8 | 1 |
| [Cryosphere (ice, glaciers, permafrost)](#cryosphere) | 25 | 8 | 0 |
| [Soils](#soil) | 14 | 7 | 0 |
| [Ecology, biomes & disturbance](#ecology) | 35 | 9 | 1 |
| [Resources & economic geology](#resources) | 15 | 6 | 0 |
| [Human & political geography](#human) | 20 | 9 | 0 |

---

## Mesh & geometry

<a id="geometry"></a>

**40 layers** · doc coverage: 14 curated · 12 convention · 7 unit · **7 generated (gaps)**.

**How it works.** Static per-cell geometry of the spherical mesh — cell centres, areas, surface normals, neighbour metrics, and multi-resolution spatial indices (HEALPix-like, S2-like, mesh-LOD tiles). These do not evolve during the simulation; they define the coordinate system every other layer is sampled on.

**Produced by:** `cpp/src/engine/mesh.cpp` (Fibonacci-sphere / geodesic mesh), `cell_geometry.py`, `mesh_lod.py`, `spherical_index.py`.

**Pipeline stage:** Built once at mesh construction, before any physics.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `area_km2` | numeric | `km²` | 1.17e+5 … 1.31e+5 | measurement | curated | Geodesic area of the cell in km². Near-uniform on the Fibonacci-sphere mesh. |
| `cell_geometry_quality` | numeric | — | 0.9421 … 0.9682 | measurement | curated | Mesh-quality score for the cell polygon; low values flag distorted or self-overlapping cells worth ignoring in analysis. |
| `cell_monsoon_index` | numeric | `index` | 5.28e-4 … 0.1533 | index | curated | Strength of monsoon-like seasonal wind reversal and precipitation contrast. |
| `cell_polygon_area_error_fraction` | numeric | `fraction` | 0 … 0 | ratio | curated | Relative error between the polygon area and the ideal cell area — a mesh-quality debug signal. |
| `id` | numeric | — | 0 … 4095 | identifier | curated | The cell's own id — a coordinate-free gradient useful for checking mesh ordering. Cell id (0…cell_count-1). The primary key every table joins on; also the mesh vertex index. |
| `lat_deg` | numeric | `°` | -88.73 … 88.73 | measurement | curated | Latitude of the cell centre in degrees (−90…90). |
| `lon_deg` | numeric | `°` | -180 … 179.9 | measurement | curated | Longitude of the cell centre in degrees (−180…180). |
| `mean_neighbor_boundary_segment_mismatch_km` | numeric | `km` | 0 … 4.50e-5 | measurement | curated | Average gap between a cell edge and its neighbour's matching edge. This is the documented "ring mismatch" that produces visible seams in the 2D projections; use it to judge where the approximate boundary rings disagree. |
| `normal_3d_x` | numeric | — | -0.9999 … 0.9996 | measurement | curated | X component of the cell surface normal (planet frame). Geometry, not a physical field. |
| `normal_3d_y` | numeric | — | -0.9998 … 0.9997 | measurement | curated | Y component of the cell surface normal (planet frame). Geometry, not a physical field. |
| `normal_3d_z` | numeric | — | -0.9998 … 0.9998 | measurement | curated | Z component of the cell surface normal (planet frame). Geometry, not a physical field. |
| `position_3d_x` | numeric | — | -0.9999 … 0.9996 | measurement | curated | X component of the cell-centre position on the unit sphere (planet frame). Geometry, not a physical field. |
| `position_3d_y` | numeric | — | -0.9998 … 0.9997 | measurement | curated | Y component of the cell-centre position on the unit sphere (planet frame). Geometry, not a physical field. |
| `position_3d_z` | numeric | — | -0.9998 … 0.9998 | measurement | curated | Z component of the cell-centre position on the unit sphere (planet frame). Geometry, not a physical field. |
| `biome_transition_neighbor_edge_count` | numeric | `count` | 0 … 8 | diagnostic | convention | Topology count — how many of the cell's mesh neighbours/edges meet the named condition (e.g. cross a land/water or biome boundary, or carry a routing edge). A static property of the mesh + classification, not an event tally. |
| `boundary_vertex_count` | numeric | `count` | 5 … 7 | diagnostic | convention | Topology count — how many of the cell's mesh neighbours/edges meet the named condition (e.g. cross a land/water or biome boundary, or carry a routing edge). A static property of the mesh + classification, not an event tally. |
| `cell_area_km2` | stage×16 | `km²` | 1.17e+5 … 1.31e+5 | measurement | unit | Per-stage numeric field (scrub the stage control). Area (square kilometres). |
| `cell_boundary_perimeter_km` | numeric | `km` | 1319 … 1404 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `cell_edge_count` | numeric | `count` | 7 … 8 | diagnostic | convention | Topology count — how many of the cell's mesh neighbours/edges meet the named condition (e.g. cross a land/water or biome boundary, or carry a routing edge). A static property of the mesh + classification, not an event tally. |
| `cell_polygon_area_km2` | numeric | `km²` | 1.17e+5 … 1.31e+5 | measurement | unit | Continuous per-cell field. Area (square kilometres). |
| `healpix_like_lon_bin` | numeric | — | 0 … 63 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `healpix_like_nside` | numeric | — | 16 … 16 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `healpix_like_pixel_id` | numeric | — | 0 … 3071 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `healpix_like_ring` | numeric | — | 0 … 47 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `land_water_neighbor_edge_count` | numeric | `count` | 0 … 8 | diagnostic | convention | Topology count — how many of the cell's mesh neighbours/edges meet the named condition (e.g. cross a land/water or biome boundary, or carry a routing edge). A static property of the mesh + classification, not an event tally. |
| `max_neighbor_boundary_segment_length_km` | numeric | `km` | 299.2 … 374.5 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `max_neighbor_edge_length_km` | numeric | `km` | 474.1 … 609 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `mean_neighbor_boundary_segment_length_km` | numeric | `km` | 194.2 … 251.5 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `mean_neighbor_boundary_segment_quality` | numeric | — | 1 … 1 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `mean_neighbor_edge_length_km` | numeric | `km` | 403.9 … 440.8 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `mesh_lod_face` | categorical | `category` | 6 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** +x, +y, +z, -x, -y, -z. |
| `mesh_lod_face_id` | numeric | — | 0 … 5 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `mesh_lod_finest_tile_id` | numeric | — | 1 … 6142 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `s2_like_cell_id` | numeric | — | 1 … 6142 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `s2_like_cell_level` | numeric | — | 5 … 5 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `s2_like_face` | categorical | `category` | 6 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** +x, +y, +z, -x, -y, -z. |
| `s2_like_face_id` | numeric | — | 0 … 5 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `s2_like_x` | numeric | — | 0 … 31 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `s2_like_y` | numeric | — | 0 … 31 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `tectonic_neighbor_edge_count` | numeric | `count` | 0 … 7 | diagnostic | convention | Topology count — how many of the cell's mesh neighbours/edges meet the named condition (e.g. cross a land/water or biome boundary, or carry a routing edge). A static property of the mesh + classification, not an event tally. |

> **Gaps in this domain (7):** `healpix_like_lon_bin`, `healpix_like_nside`, `healpix_like_ring`, `mean_neighbor_boundary_segment_quality`, `s2_like_cell_level`, `s2_like_x`, `s2_like_y` — resolved by kind + template only. Add prose to `CURATED` in `layer_docs.js` to close these.

---

## Tectonics & solid earth

<a id="tectonics"></a>

**37 layers** · doc coverage: 20 curated · 15 convention · 1 unit · **1 generated (gaps)**.

**How it works.** Plate assignment and kinematics, crust type/age/thickness/density, boundary classification (convergent/divergent/transform), fault systems, seismic hazard, and the initial tectonic elevation contributions (ridge, rift, trench, orogenic, volcanic, thermal, isostatic). This is the deepest layer of the model — the feedback loop re-derives elevation from these each stage.

**Produced by:** `cpp/src/engine/tectonics.cpp`, `fault_systems.py`, `tectonic_zones.py`, `geology_realism.py`.

**Pipeline stage:** Initialised at setup (the `initial_*` fields), then updated by the geodynamic feedback loop.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `boundary_convergent` | numeric | — | 0 … 0.6364 | measurement | curated | Strength of convergent-boundary influence on this cell. |
| `boundary_divergent` | numeric | — | 0 … 0.6076 | measurement | curated | Strength of divergent-boundary influence on this cell. |
| `boundary_transform` | numeric | — | 0 … 0.7323 | measurement | curated | Strength of transform-boundary influence on this cell. |
| `boundary_type` | categorical | `category` | 5 classes | classification | curated | Dominant plate-boundary regime affecting the cell (convergent, divergent, transform, none). **Classes:** convergent, divergent, interior, mixed, transform. |
| `continental_shelf_id` | numeric | — | -1 … 44 | identifier | curated | Identifier for a coarse marine shelf diagnostic component. At Earth reference resolution a cell is roughly 400 km across, so this does not resolve fractional shelf area or a shelf–slope–rise profile. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `crust_age_ma` | numeric | `Ma` | 0 … 4102 | measurement | curated | Current procedural crust-state age in Ma after remap and maturation rules. This replay root is serialized with binary64 round-trip precision. It is not a reconstructed geological creation age or proof of a ridge-to-subduction flowline. |
| `crust_density` | numeric | `g/cm³` | 2.708 … 3 | measurement | curated | Bulk crust density in g/cm³, serialized with binary64 round-trip precision; oceanic crust is denser than continental. |
| `crust_thickness_km` | numeric | `km` | 4.5 … 76 | measurement | curated | Crustal thickness; thick under orogens, thin under ridges. |
| `crust_type` | categorical | `category` | 9 classes | classification | curated | Crust classification (continental, oceanic, craton, orogen, …). **Classes:** accreted_terrane, continental, craton, oceanic, orogen, rift_basin, sedimentary_basin, transitional, volcanic_arc. |
| `earthquake_recurrence_interval_y` | numeric | — | 0 … 922.8 | measurement | curated | Mean interval between large earthquakes, in years. Low values mark seismically active belts. |
| `initial_isostatic_elevation_m` | numeric | `m` | -2500 … 669 | provenance | curated | Initial local crustal isostatic-equilibrium elevation contribution. Later changes are applied in full outside the dynamic-relief clamp. Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_plate_id` | numeric | — | 0 … 13 | identifier | curated | Plate assignment at initialization, before any plate reorganization events. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `lithology` | categorical | `category` | 7 classes | classification | curated | Dominant rock type (basalt, granite, limestone, …). NOTE: the per-stage history serializes lithology as numeric codes 0–6, while this cell layer uses names; the code order is alphabetical here and may not match the engine enum (see layers_review.md F3). **Classes:** basalt, granite, limestone, metamorphic, sandstone, shale, volcanic. |
| `lithology` | stage×16 | — | 0 … 6 | measurement | curated | Dominant rock type (basalt, granite, limestone, …). NOTE: the per-stage history serializes lithology as numeric codes 0–6, while this cell layer uses names; the code order is alphabetical here and may not match the engine enum (see layers_review.md F3). |
| `plate_id` | numeric | — | 0 … 13 | identifier | curated | Tectonic plate the cell belongs to. Identifier — colour groups plates, magnitude is meaningless. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `seismic_hazard_index` | numeric | `index` | 0.002419 … 0.5966 | index | curated | Relative earthquake hazard from boundary proximity and fault slip rates. |
| `tectonic_uplift_rate_m_per_step` | numeric | `m/step` | 0 … 6.831 | measurement | curated | Current tectonic uplift (positive) or subsidence (negative) rate. |
| `tectonic_zone_strength` | numeric | — | 0 … 0.8203 | measurement | curated | Relative strength/activity of the tectonic zone influencing the cell (dimensionless). |
| `thermal_subsidence_target_m` | numeric | `m` | -3958 … 0 | measurement | curated | Current relative oceanic age–depth equilibrium target. Its full step-to-step change is applied outside the bounded dynamic-relief clamp; the field is not a separately evolved thermal-relief state. |
| `volcanic_potential_index` | numeric | `index` | 0.04 … 0.562 | index | curated | Relative likelihood of volcanism (subduction arcs, rifts, hotspots). |
| `collision_zone_id` | numeric | — | -1 … 8 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `cumulative_crust_transport_distance_km` | numeric | `km` | 51.36 … 2480 | accumulator | convention | Running total accumulated across all simulation stages (monotonic per cell). The per-stage delta lives in the corresponding stage-history ledger. |
| `dominant_tectonic_zone_type` | categorical | `category` | 4 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** collision, none, rift, subduction. |
| `fault_slip_rate_index` | numeric | `index` | 3.40e-5 … 0.6443 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `fault_system_id` | numeric | — | -1 … 10 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `initial_orogenic_uplift_m` | numeric | `m` | 0 … 7733 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_ridge_uplift_m` | numeric | `m` | 0 … 532.1 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_rift_subsidence_m` | numeric | `m` | -495.8 … 0 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_secondary_roughness_m` | numeric | `m` | -731.6 … 794.8 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_transform_fault_relief_m` | numeric | `m` | -218.6 … 0 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_trench_subsidence_m` | numeric | `m` | -6248 … 0 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `initial_volcanic_uplift_m` | numeric | `m` | 0 … 5164 | provenance | convention | Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `last_plate_assignment_change_iteration` | numeric | — | -1 … 6 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `oceanic_crust_subduction_event_count` | numeric | `count` | 0 … 6 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `plate_assignment_change_count` | numeric | `count` | 0 … 3 | measurement | unit | Continuous per-cell field. Integer count. |
| `rift_zone_id` | numeric | — | -1 … 11 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `subduction_zone_id` | numeric | — | -1 … 21 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |

> **Gaps in this domain (1):** `last_plate_assignment_change_iteration` — resolved by kind + template only. Add prose to `CURATED` in `layer_docs.js` to close these.

---

## Elevation & landforms

<a id="geomorphology"></a>

**13 layers** · doc coverage: 10 curated · 3 convention · 0 unit · **0 generated (gaps)**.

**How it works.** The land/sea surface itself — final and initial elevation, depression-filled surface, landform class, landmass and island classification, and local relief. Elevation is the single most-used layer and the default on load.

**Produced by:** `cpp/src/engine/core.cpp` / `environment.cpp`, `glacial_landforms.py`, `planet_realism.py`, `sea_level_diagnostics.py`.

**Pipeline stage:** Elevation co-evolves in the feedback loop; landform/landmass classification is a post-pass enricher.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `cumulative_tectonic_elevation_change_m` | numeric | `m` | -7058 … 7289 | accumulator | curated | Net elevation change contributed by tectonics over the whole run. Each step is the full gain-1 isostatic change plus full gain-1 thermal-target change plus only the bounded dynamic-relief term. Running total accumulated across all simulation stages (monotonic per cell). The per-stage delta lives in the corresponding stage-history ledger. |
| `elevation_m` | numeric | `m` | -10140 … 7301 | measurement | curated | Surface elevation above the planetary datum, in metres. Negative below sea level. The most-used base layer; the default on load. |
| `elevation_m` | stage×16 | `m` | -10890 … 8947 | measurement | curated | Surface elevation above the planetary datum, in metres. Negative below sea level. The most-used base layer; the default on load. |
| `erosion_rate` | numeric | — | 0 … 34.46 | measurement | curated | Local stream-power response in depth per 5 Ma reference step; applied incision is timestep-scaled. |
| `filled_elevation_m` | numeric | `m` | 0 … 7301 | measurement | curated | Elevation after depression filling — closed basins raised to their spill level so flow routing has no sinks. Diff against `elevation_m` to see filled depressions. |
| `initial_elevation_m` | numeric | `m` | -11990 … 7849 | provenance | curated | Elevation immediately after tectonic/isostatic setup, before erosion and the feedback loop. Diff against `elevation_m` for net landscape change. Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation. |
| `island_class` | categorical | `category` | 4 classes | classification | curated | Size classification of the containing landmass (continent, island, islet, …). **Classes:** continent, island, large_island, water. |
| `landform` | categorical | `category` | 17 classes | classification | curated | Geomorphic landform class (mountain_belt, coastal_plain, trench, …) from elevation and tectonic context. **Classes:** coastal_plain, continental_shelf, delta, fjord, floodplain, glacial_lake, ice_field, lacustrine_basin, moraine, mountain_belt, open_ocean, rift_valley, river_valley, salt_flat, stable_lowland, trench, volcanic_arc. |
| `landmass_id` | numeric | — | -1 … 4 | identifier | curated | Connected landmass (continent/island) the cell belongs to. Identifier. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `local_relief_m` | stage×16 | `m` | 0 … 11500 | measurement | curated | Relief within the cell's neighborhood at that stage. |
| `glacial_landform_index` | numeric | `index` | 0.001604 … 0.7602 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `glacial_landform_system_id` | numeric | — | -1 … 40 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `glacial_landform_type` | categorical | `category` | 6 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** fjord, glacial_lake, ice_cap, moraine, mountain_glacier, none. |

---

## Sediment & stratigraphy

<a id="sediment"></a>

**35 layers** · doc coverage: 8 curated · 6 convention · 21 unit · **0 generated (gaps)**.

**How it works.** Erosion, transport, and deposition budgets — hillslope diffusion, fluvial routing (production, deposition, terminal export/capture), sediment thickness, and sequence-stratigraphy inventory. These close the mass balance between the eroding uplands and the depositional basins.

**Produced by:** `sediment_dynamics.py`, `sediment_routing.py`, `sedimentary_resource_systems.py`, `sequence_stratigraphy.py`.

**Pipeline stage:** Runs inside the erosion iterations of the feedback loop.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `breach_deposition_depth_m` | stage×423 | `m` | 26.23 … 49.24 | measurement | curated | Excavated material redeposited downstream of the breach. |
| `fluvial_sediment_marine_deposition_m` | numeric | `m` | 0 … 57.6 | measurement | curated | River sediment delivered to and deposited in marine cells (deltas, shelves). |
| `moraine_deposition_m` | numeric | `m` | 0 … 2.357 | measurement | curated | Sediment deposited as moraines at ice margins. |
| `sediment_deposition_m` | numeric | `m` | 0 … 2248 | measurement | curated | Sediment deposited in the cell. |
| `sediment_export_m` | numeric | `m` | 0 … 422.4 | measurement | curated | Sediment leaving the cell downstream. |
| `sediment_net_budget_m` | numeric | `m` | -2673 … 2248 | measurement | curated | Deposition minus erosion — positive is net aggradation. |
| `sediment_thickness_m` | numeric | `m` | 0 … 2248 | measurement | curated | Accumulated sediment column thickness in metres. |
| `sediment_thickness_m` | stage×16 | `m` | 0 … 2248 | measurement | curated | Accumulated sediment column thickness in metres. |
| `breach_alluvium_entrainment_depth_m` | stage×423 | `m` | 0 … 0 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `breach_bedrock_erosion_depth_m` | stage×423 | `m` | 0 … 0 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `breach_sediment_thickness_before_excavation_m` | stage×423 | `m` | 0 … 1459 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `cumulative_numeric_depression_breach_deposition_m` | numeric | `m` | 0 … 49.24 | accumulator | convention | Running total accumulated across all simulation stages (monotonic per cell). The per-stage delta lives in the corresponding stage-history ledger. |
| `fluvial_sediment_depression_fill_m` | numeric | `m` | 0 … 225.5 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `fluvial_sediment_local_deposition_m` | numeric | `m` | 0 … 229.9 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `fluvial_sediment_local_source_m` | numeric | `m` | 0 … 246.1 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `fluvial_sediment_routed_incoming_m` | numeric | `m` | 0 … 480 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `fluvial_sediment_routed_outgoing_m` | numeric | `m` | 0 … 236.8 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `fluvial_sediment_routing_event_count` | numeric | `count` | 0 … 6 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `fluvial_sediment_terminal_capture_volume_km3` | numeric | `km³` | 0 … 18580 | measurement | unit | Continuous per-cell field. Volume (cubic kilometres). |
| `fluvial_sediment_terminal_export_m` | numeric | `m` | 0 … 422.4 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `fluvial_sediment_terminal_land_deposition_m` | numeric | `m` | 0 … 140.5 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `hillslope_sediment_deposition_m` | numeric | `m` | 0 … 2246 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `hillslope_sediment_incoming_edge_count` | numeric | `count` | 0 … 48 | diagnostic | convention | Topology count — how many of the cell's mesh neighbours/edges meet the named condition (e.g. cross a land/water or biome boundary, or carry a routing edge). A static property of the mesh + classification, not an event tally. |
| `hillslope_sediment_net_m` | numeric | `m` | -2436 … 2246 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `hillslope_sediment_outgoing_edge_count` | numeric | `count` | 0 … 48 | diagnostic | convention | Topology count — how many of the cell's mesh neighbours/edges meet the named condition (e.g. cross a land/water or biome boundary, or carry a routing edge). A static property of the mesh + classification, not an event tally. |
| `hillslope_sediment_production_m` | numeric | `m` | 0 … 2436 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `overflow_channel_sediment_evacuated_km3` | numeric | `km³` | 0 … 0.02565 | measurement | unit | Continuous per-cell field. Volume (cubic kilometres). |
| `reef_sediment_stress_index` | numeric | `index` | 0 … 1 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `sediment_alluvium_entrainment_m` | numeric | `m` | 0 … 503.8 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `sediment_bedrock_erosion_m` | numeric | `m` | 0 … 2674 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `sediment_routing_deposition_m` | numeric | `m` | 0 … 166 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `sediment_routing_export_m` | numeric | `m` | 0 … 364.5 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `sediment_routing_load_m` | numeric | `m` | 0 … 93.39 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `sediment_routing_path_count` | numeric | `count` | 0 … 5 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `sediment_thickness_before_correction_m` | stage×423 | `m` | 0 … 2248 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |

---

## Surface hydrology & rivers

<a id="hydrology"></a>

**78 layers** · doc coverage: 34 curated · 32 convention · 10 unit · **2 generated (gaps)**.

**How it works.** Flow routing over the conditioned surface — flow direction and accumulation, drainage basins, depression correction, lakes and closed basins, river channels (width/depth/hydraulics), floodplains, and river-network evolution (avulsion, capture). The depression-correction history logs every bounded breach or explicit temporary-lake deferral as a separate stage and retains its counterfactual fill candidate.

**Produced by:** `cpp/src/engine/hydrology.cpp`, `hydrology_dynamics.py`, `hydrology_realism.py`, `river_hydraulics.py`, `river_channel_morphology.py`, `river_network_evolution.py`, `watershed_diagnostics.py`.

**Pipeline stage:** Flow routing runs every feedback stage after the surface is conditioned; channel morphology is an enricher on the final network.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `bankfull_discharge_m3_s` | numeric | `m³/s` | 0 … 1965 | measurement | curated | Channel-forming discharge of the river through this cell. |
| `baseflow_support_index` | numeric | `index` | 0 … 1 | index | curated | How strongly groundwater sustains dry-season river flow. |
| `basin_id` | numeric | — | 11 … 4095 | identifier | curated | Drainage basin the cell belongs to. Identifier — colour groups a watershed. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `bed_shear_stress_pa` | numeric | `Pa` | 0 … 31.41 | measurement | curated | Shear stress exerted on the channel bed; drives sediment entrainment. |
| `breach_excavation_depth_m` | stage×423 | `m` | 0 … 6794 | measurement | curated | Depth excavated through the sill when the policy breached instead of filled. |
| `depression_depth_m` | numeric | `m` | 0 … 4594 | measurement | curated | Depth of the enclosing depression below its spill elevation. |
| `depression_policy` | categorical | `category` | 5 classes | classification | curated | How the depression containing this cell was resolved (preserved, filled, breached, …). **Classes:** dry_closed, none, overflow_spill, preserved_geologic, temporary_numeric_lake. |
| `elevation_after_fill_m` | stage×423 | `m` | 7.209 … 1758 | measurement | curated | Counterfactual surface elevation under the full-fill candidate; not the applied post-correction terrain. |
| `elevation_before_fill_m` | stage×423 | `m` | -5933 … 1703 | measurement | curated | Surface elevation before correction and fill-candidate evaluation. |
| `fill_depth_m` | stage×423 | `m` | 0.3587 … 7517 | measurement | curated | Counterfactual Priority-Flood depth for the event cell; retained for correction selection and not applied as material. |
| `flow_accumulation` | numeric | — | 0 … 1.89e+10 | measurement | curated | Upstream drainage area (in cell-count units) draining through each cell — the classic river-network signal. Extremely heavy-tailed: a handful of trunk cells dwarf everything, so the p2–p98 default colour scale saturates the main stems (see legend clip markers). |
| `flow_to` | numeric | — | -1 … 4036 | identifier | curated | Downstream neighbour each cell drains into (a cell id, or -1 at outlets/oceans). Together with `flow_accumulation` this defines the drainage network. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `flow_velocity_m_s` | numeric | `m/s` | 0 … 2.348 | measurement | curated | Channel flow velocity in m/s from the river-hydraulics solve. |
| `froude_number` | numeric | — | 0 … 0.4945 | measurement | curated | Froude number of channel flow (dimensionless): <1 subcritical, >1 supercritical. Mostly ~0 off the channel network. |
| `glacier_flow_to` | numeric | — | -1 … 4036 | identifier | curated | Downstream cell receiving this cell's ice flux. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `hydrologic_surface_elevation_m` | numeric | `m` | 0 … 7301 | measurement | curated | Elevation of the hydrologically-conditioned surface used for flow routing (post-fill/breach). The surface the water budget actually runs on. |
| `is_closed_basin` | categorical | `category` | 2 classes | classification | curated | Whether the cell drains to an internal sink with no path to the ocean (endorheic). **Classes:** False, True. |
| `is_lake` | categorical | `category` | 2 classes | classification | curated | Whether the cell is part of a standing water body (lake). **Classes:** False, True. |
| `is_marine` | stage×16 | — | 0 … 1 | measurement | curated | Whether the cell is marine (ocean/sea). In the per-stage ledger this appears as 0/1 rather than a category. |
| `is_river` | categorical | `category` | 2 classes | classification | curated | Whether river discharge through the cell exceeds the channel threshold. **Classes:** False, True. |
| `is_water` | categorical | `category` | 2 classes | classification | curated | Whether the cell is water (ocean, sea, or lake) rather than land. **Classes:** False, True. |
| `lake_basin_id` | numeric | — | -1 … 66 | identifier | curated | Lake basin the cell belongs to, when inside a lake system. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `lake_fill_fraction` | numeric | `fraction` | 0 … 1.5 | ratio | curated | How full a lake basin is relative to its spill level at the end of the water-budget solve. Usually 0–1; values above 1 mark transiently overfilled basins. |
| `manning_roughness_n` | numeric | — | 0 … 0.062 | measurement | curated | Manning's roughness coefficient n for channel flow (dimensionless). |
| `river_avulsion_risk` | numeric | — | 0 … 0.7308 | measurement | curated | Likelihood the channel jumps its banks and reroutes across the floodplain. |
| `river_capture_risk` | numeric | — | 0 … 0.7523 | measurement | curated | Likelihood that a neighboring basin captures this drainage in future evolution. |
| `river_channel_depth_m` | numeric | `m` | 0 … 3.709 | measurement | curated | Modeled bankfull channel depth. |
| `river_channel_width_m` | numeric | `m` | 0 … 160.6 | measurement | curated | Modeled bankfull channel width. |
| `runoff_mm_y` | numeric | `mm/year` | 0 … 3337 | measurement | curated | Annual runoff generated in the cell (precipitation minus evapotranspiration and infiltration losses). |
| `runoff_mm_y` | stage×16 | `mm/year` | 0 … 3603 | measurement | curated | Annual runoff generated in the cell (precipitation minus evapotranspiration and infiltration losses). |
| `spill_elevation_m` | numeric | `m` | 0 … 7301 | measurement | curated | Elevation of the depression's outlet sill. |
| `stream_power_index` | numeric | `index` | 0 … 0.3596 | index | curated | Erosive capacity of the flow (slope × discharge). |
| `water_body_type` | categorical | `category` | 5 classes | classification | curated | Ocean / lake / land classification of the cell. **Classes:** continental_shelf, fresh_lake, land, ocean, saline_basin. |
| `water_depth_m` | numeric | `m` | 0 … 10140 | measurement | curated | Water column depth (bathymetry for ocean, lake depth for lakes) in metres. One value represents the entire coarse control volume; it does not resolve subcell shelf, slope, coastline, or strait geometry. |
| `breach_elevation_before_m` | stage×423 | `m` | -5605 … 2296 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `breach_target_elevation_m` | stage×423 | `m` | -5605 … 1328 | measurement | unit | Per-stage numeric field (scrub the stage control). Length/elevation/depth (metres). |
| `channel_capacity_index` | numeric | `index` | 0 … 0.9586 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `channel_morphology_class` | categorical | `category` | 5 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** braided_sediment_rich_channel, glacial_outwash_channel, navigable_lowland_channel, non_channel, small_headwater. |
| `channel_slope_index` | numeric | `index` | 0 … 0.05504 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `cumulative_numeric_depression_breach_excavation_m` | numeric | `m` | 0 … 49.24 | accumulator | convention | Running total accumulated across all simulation stages (monotonic per cell). The per-stage delta lives in the corresponding stage-history ledger. |
| `depression_component_id` | numeric | — | -1 … 66 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `depression_sink_cell_id` | numeric | — | -1 … 3900 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `equal_filled_raw_downhill_rerouted` | categorical | `category` | 2 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** False, True. |
| `floodplain_connectivity_index` | numeric | `index` | 0 … 0.9411 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `hydraulic_flow_regime` | categorical | `category` | 2 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** non_channel, subcritical. |
| `hydraulic_navigability_index` | numeric | `index` | 0 … 0.8717 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `hydraulic_radius_m` | numeric | `m` | 0 … 3.544 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `hydrologic_budget_class` | categorical | `category` | 5 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** balanced_budget, evapotranspiration_dominated, marine_budget, runoff_surplus, water_deficit. |
| `hydrologic_budget_region_id` | numeric | — | 0 … 86 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `hydrologic_deficit_mm_y` | numeric | `mm/year` | 0 … 936.6 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `hydrologic_flow_drop_m` | numeric | `m` | 0 … 6590 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `hydrologic_flow_slope` | numeric | — | 0 … 0.01749 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `hydrologic_potential_evapotranspiration_mm_y` | numeric | `mm/year` | 0 … 1211 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `hydrologic_surface_conditioned` | categorical | `category` | 2 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** False, True. |
| `hydrologic_water_balance_mm_y` | numeric | `mm/year` | 0 … 3337 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `lake_overflows` | categorical | `category` | 2 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** False, True. |
| `navigable_waterway_id` | numeric | — | -1 … 70 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `numeric_depression_breach_event_count` | numeric | `count` | 0 … 1 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `numeric_depression_temporary_lake_event_count` | numeric | `count` | 0 … 8 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `overflow_channel_active` | categorical | `category` | 2 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** False, True. |
| `overflow_channel_avulsion_risk` | numeric | — | 0 … 0.4033 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `overflow_channel_incision_m` | numeric | `m` | 0 … 4.844 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `river_capture_divide_relief_m` | numeric | `m` | 0 … 838.6 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `river_capture_target_basin_id` | numeric | — | -1 … 4031 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `river_capture_target_cell_id` | numeric | — | -1 … 4031 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `river_capture_target_distance_km` | numeric | `km` | 0 … 574.1 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `river_channel_system_id` | numeric | — | -1 … 12 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `river_hydraulic_reach_id` | numeric | — | -1 … 12 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `river_mouth_port_index` | numeric | `index` | 0 … 0.7387 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `river_navigability_index` | numeric | `index` | 0 … 0.8573 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `river_network_instability_index` | numeric | `index` | 0 … 0.7523 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `river_valley_route_index` | numeric | `index` | 0 … 1 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `runoff_budget_consistency_index` | numeric | `index` | 1 … 1 | diagnostic | convention | Conservation residual / mass-balance check. Should sit near zero everywhere; large magnitudes flag a budget that does not close and are a debugging signal rather than terrain. |
| `runoff_budget_residual_mm_y` | numeric | `mm/year` | 0 … 0 | diagnostic | convention | Conservation residual / mass-balance check. Should sit near zero everywhere; large magnitudes flag a budget that does not close and are a debugging signal rather than terrain. |
| `runoff_generation_fraction` | numeric | `fraction` | 0 … 1 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `soil_drainage_index` | numeric | `index` | 0 … 0.9156 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `spill_to` | numeric | — | -1 … 4036 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `subterranean_drainage_fraction` | numeric | `fraction` | 0 … 0.5229 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |

> **Gaps in this domain (2):** `hydrologic_flow_slope`, `overflow_channel_avulsion_risk` — resolved by kind + template only. Add prose to `CURATED` in `layer_docs.js` to close these.

---

## Water budget & atmospheric moisture

<a id="water-budget"></a>

**27 layers** · doc coverage: 14 curated · 6 convention · 7 unit · **0 generated (gaps)**.

**How it works.** The coupled precipitation → evapotranspiration → infiltration → runoff balance and the atmospheric-moisture transport that feeds it (orographic rainout, moisture recycling, vapor budget, water surplus/deficit). The `hydrologic_water_budget_history` (16 stages) is the per-stage snapshot of this solve.

**Produced by:** `cpp/src/engine/climate.cpp`, `climate_dynamics.py`, `hydrology_budget.py`.

**Pipeline stage:** Recomputed each feedback stage (16 recomputes over 8 clock stages).

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `actual_evapotranspiration_mm_y` | numeric | `mm/year` | 0 … 578.1 | measurement | curated | Realized evapotranspiration (limited by available water). |
| `actual_evapotranspiration_mm_y` | stage×16 | `mm/year` | 0 … 679.9 | measurement | curated | Realized evapotranspiration (limited by available water). |
| `infiltration_mm_y` | numeric | `mm/year` | 0 … 372.2 | measurement | curated | Annual water infiltrating into the subsurface. |
| `infiltration_mm_y` | stage×16 | `mm/year` | 0 … 372.2 | measurement | curated | Annual water infiltrating into the subsurface. |
| `mean_seasonal_wind_speed` | numeric | — | 0.7968 … 0.9682 | measurement | curated | Mean wind speed over the seasonal cycle (magnitude of the monthly wind vectors). |
| `orographic_factor` | numeric | — | 1 … 1.42 | ratio | curated | Terrain-forced uplift enhancement of precipitation on windward slopes. |
| `potential_evapotranspiration_mm_y` | numeric | `mm/year` | 0 … 1362 | measurement | curated | Atmospheric demand for water (energy-limited evaporation). |
| `potential_evapotranspiration_mm_y` | stage×16 | `mm/year` | 0 … 1246 | measurement | curated | Atmospheric demand for water (energy-limited evaporation). |
| `precipitation_mm_y` | numeric | `mm/year` | 51.93 … 4879 | measurement | curated | Mean annual precipitation, mm/year. Monthly detail in `precipitation_monthly_mm`. |
| `precipitation_mm_y` | stage×16 | `mm/year` | 51.14 … 4879 | measurement | curated | Mean annual precipitation, mm/year. Monthly detail in `precipitation_monthly_mm`. |
| `precipitation_monthly_mm` | month×12 | `mm` | 1.667 … 638.7 | measurement | curated | Monthly precipitation; scrub to see monsoon bands and storm-track migration. |
| `rain_shadow_factor` | numeric | — | 0.52 … 1 | ratio | curated | Precipitation suppression on lee slopes downwind of barriers. |
| `residual_mm_y` | stage×16 | `mm/year` | 0 … 0 | diagnostic | curated | Unclosed remainder of the stage water budget — should be near 0; hotspots flag conservation bugs. |
| `water_balance_mm_y` | stage×16 | `mm/year` | 0 … 3603 | measurement | curated | Per-stage water balance closure: precipitation minus evapotranspiration, runoff, and storage terms. |
| `advected_moisture_factor` | numeric | — | 0.8218 … 1.198 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `climatic_water_deficit_mm_y` | numeric | `mm/year` | 0 … 928 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `climatic_water_surplus_mm_y` | numeric | `mm/year` | 0 … 3545 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `humidity_transport_index` | numeric | `index` | 0.0066 … 1.35 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `infiltration_capacity_index` | numeric | `index` | 0 … 0.7884 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `infiltration_capacity_index` | stage×16 | `index` | 0 … 0.7884 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `moisture_convergence_mm_y` | numeric | `mm/year` | 0 … 4496 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `orographic_rainout_mm_y` | numeric | `mm/year` | 5.00e-4 … 942.5 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `precipitation_recycling_fraction` | numeric | `fraction` | 0.0648 … 0.4782 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `vapor_budget_residual_mm_y` | numeric | `mm/year` | 0 … 0 | diagnostic | convention | Conservation residual / mass-balance check. Should sit near zero everywhere; large magnitudes flag a budget that does not close and are a debugging signal rather than terrain. |
| `vapor_deficit_mm_y` | numeric | `mm/year` | 0 … 960.4 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `vapor_evaporation_mm_y` | numeric | `mm/year` | 0 … 1774 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `water_budget_runoff_mm_y` | numeric | `mm/year` | 0 … 3337 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |

---

## Groundwater, aquifers & karst

<a id="groundwater"></a>

**30 layers** · doc coverage: 8 curated · 12 convention · 10 unit · **0 generated (gaps)**.

**How it works.** Subsurface water — recharge, hydraulic head, lateral flow between cells, aquifer classification and productivity/quality/storage indices, vadose-zone retention, spring discharge, and karst/cave development potential. Includes mass-balance residual diagnostics for the groundwater solve.

**Produced by:** `groundwater_flow.py`, `aquifer_resources.py`, `karst_diagnostics.py`.

**Pipeline stage:** Enricher pass over the final surface-hydrology and climate state.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `aquifer_class` | categorical | `category` | 6 classes | classification | curated | Aquifer classification from lithology and structure. **Classes:** fossil_or_slow_recharge_aquifer, local_fresh_aquifer, major_fresh_aquifer, marine_excluded, perched_recharge_zone, poor_aquifer. |
| `aquifer_productivity_index` | numeric | `index` | 0 … 0.7696 | index | curated | How readily the aquifer yields water. |
| `cave_development_index` | numeric | `index` | 0 … 0.6179 | index | curated | Modeled cave-system development intensity. |
| `groundwater_discharge_mm_y` | numeric | `mm/year` | 0 … 452.8 | measurement | curated | Annual groundwater discharge back to the surface (springs, baseflow). |
| `groundwater_flow_to_cell_id` | numeric | — | -1 … 4049 | identifier | curated | Downgradient cell receiving this cell's lateral groundwater flow. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `groundwater_hydraulic_head_m` | numeric | `m` | -4598 … 7101 | measurement | curated | Water-table elevation driving lateral groundwater flow. |
| `groundwater_recharge_mm_y` | numeric | `mm/year` | 0 … 266.2 | measurement | curated | Annual recharge reaching the water table. |
| `karst_potential_index` | numeric | `index` | 0 … 0.7409 | index | curated | Susceptibility to karstification (carbonate lithology + water). |
| `aquifer_extraction_risk_index` | numeric | `index` | 0 … 0.551 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `aquifer_quality_index` | numeric | `index` | 0 … 0.9197 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `aquifer_storage_index` | numeric | `index` | 0 … 0.908 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `aquifer_system_id` | numeric | — | -1 … 328 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `groundwater_available_volume_km3_y` | numeric | `km³/year` | 0 … 126.2 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `groundwater_discharge_km3_y` | numeric | `km³/year` | 0 … 56.38 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `groundwater_flow_mass_balance_residual_km3_y` | numeric | `km³/year` | 0 … 0 | diagnostic | convention | Conservation residual / mass-balance check. Should sit near zero everywhere; large magnitudes flag a budget that does not close and are a debugging signal rather than terrain. |
| `groundwater_flow_regime` | categorical | `category` | 7 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** discharge_zone, excluded, lowland_discharge, recharge_mound, recharge_throughflow, stagnant_or_low_yield, throughflow. |
| `groundwater_flow_system_id` | numeric | — | -1 … 328 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `groundwater_gradient_index` | numeric | `index` | 0 … 1 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `groundwater_internal_lateral_outflow_km3_y` | numeric | `km³/year` | 0 … 38.6 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `groundwater_lateral_flow_km3_y` | numeric | `km³/year` | 0 … 38.6 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `groundwater_lateral_inflow_km3_y` | numeric | `km³/year` | 0 … 112.1 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `groundwater_recharge_fraction` | numeric | `fraction` | 0 … 0.7489 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `groundwater_recharge_km3_y` | numeric | `km³/year` | 0 … 33.15 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `groundwater_recharge_mass_balance_residual_mm_y` | numeric | `mm/year` | 0 … 0 | diagnostic | convention | Conservation residual / mass-balance check. Should sit near zero everywhere; large magnitudes flag a budget that does not close and are a debugging signal rather than terrain. |
| `groundwater_recharge_source_infiltration_mm_y` | numeric | `mm/year` | 0 … 372.2 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |
| `groundwater_retained_storage_km3_y` | numeric | `km³/year` | 0 … 73.11 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `karst_system_id` | numeric | — | -1 … 13 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `spring_discharge_index` | numeric | `index` | 0 … 0.9954 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `vadose_zone_retention_km3_y` | numeric | `km³/year` | 0 … 19.03 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `vadose_zone_retention_mm_y` | numeric | `mm/year` | 0 … 152.8 | measurement | unit | Continuous per-cell field. Annual depth flux (millimetres per year). |

---

## Climate & atmosphere

<a id="climate"></a>

**38 layers** · doc coverage: 19 curated · 13 convention · 6 unit · **0 generated (gaps)**.

**How it works.** Temperature, Köppen climate class, the atmospheric-circulation cell each cell sits in, winds, the full surface-energy balance (insolation, shortwave/longwave, greenhouse trapping, albedo, radiative-equilibrium temperatures), seasonality (dry/wet/growing/frost month counts, seasonal ranges), continentality, and monsoon indices.

**Produced by:** `cpp/src/engine/climate.cpp`, `climate_dynamics.py`, `climate_energy.py`, `climate_continentality.py`, `climate_realism.py`.

**Pipeline stage:** Recomputed each feedback stage; energy-balance and seasonality indices are enrichers on the converged climate.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `absorbed_shortwave_w_m2` | numeric | `W/m²` | 37.94 … 341.1 | measurement | curated | Solar energy absorbed at the surface after albedo. |
| `atmospheric_cell` | categorical | `category` | 4 classes | classification | curated | Which meridional circulation cell (Hadley / Ferrel / Polar) the cell sits in. **Classes:** midlatitude_westerly, polar_cell, subtropical_high, tropical_ascent. |
| `climate_class` | categorical | `category` | 18 classes | classification | curated | Köppen–Geiger climate class (Af, BWh, Cfb, ET, …). The class set is world-dependent; the classes actually present are listed with the layer. **Classes:** Af, Am, Aw, BSh, BSk, BWh, BWk, Cfa, Cfb, Cfc, Cwa, Cwb, Cwc, Dfa, Dfb, Dfc, EF, ET. |
| `continentality_index` | numeric | `index` | 4.00e-5 … 0.9955 | index | curated | How continental (vs maritime) the local climate is; drives seasonal temperature range. |
| `energy_balance_residual_c` | numeric | `°C` | -7.98 … 71.84 | diagnostic | curated | Generated temperature minus the separately parameterized radiative-equilibrium temperature, in degrees Celsius. This is a diagnostic model mismatch, not the residual of a solved energy-closure equation and is not expected to be zero. |
| `greenhouse_trapping_w_m2` | numeric | `W/m²` | 12.62 … 112.1 | measurement | curated | Longwave energy retained by the atmosphere. |
| `net_radiative_balance_w_m2` | numeric | `W/m²` | -180.8 … 40.04 | measurement | curated | Absorbed minus outgoing radiation; the energy the circulation must transport. |
| `no_greenhouse_equilibrium_temperature_c` | numeric | `°C` | -112.3 … 5.346 | measurement | curated | Radiative equilibrium temperature with the greenhouse effect removed. |
| `outgoing_longwave_w_m2` | numeric | `W/m²` | 167.2 … 475.4 | measurement | curated | Thermal radiation emitted back to space. |
| `radiative_equilibrium_temperature_c` | numeric | `°C` | -97.72 … 27.29 | measurement | curated | Temperature the cell would reach from local radiation balance alone. |
| `surface_albedo_index` | numeric | `index` | 0.1212 … 0.86 | index | curated | Surface reflectivity driven by ice, desert, vegetation, and water. |
| `temperature_c` | numeric | `°C` | -37.74 … 32.54 | measurement | curated | Mean annual surface air temperature in °C. Monthly detail is in the `temperature_monthly_c` monthly layer. |
| `temperature_c` | stage×16 | `°C` | -48.63 … 34.33 | measurement | curated | Mean annual surface air temperature in °C. Monthly detail is in the `temperature_monthly_c` monthly layer. |
| `temperature_monthly_c` | month×12 | `°C` | -50.64 … 34.55 | measurement | curated | Monthly near-surface temperature; scrub months to watch the seasonal cycle and hemispheric phase flip. |
| `top_of_atmosphere_insolation_w_m2` | numeric | `W/m²` | 161.4 … 401.8 | measurement | curated | Annual-mean solar input before the atmosphere, set by latitude and orbit. |
| `wind_east` | numeric | — | -0.9766 … 0.9874 | measurement | curated | Eastward (zonal) component of the mean surface wind. Positive = toward the east. Pair with `wind_north` for the full vector. |
| `wind_monthly_east` | month×12 | — | -0.9637 … 0.9674 | measurement | curated | Monthly eastward wind component; seasonal reversals mark monsoon circulations. |
| `wind_monthly_north` | month×12 | — | -0.5052 … 0.4247 | measurement | curated | Monthly northward wind component. |
| `wind_north` | numeric | — | -0.2334 … 0.2334 | measurement | curated | Northward (meridional) component of the mean surface wind. Positive = toward the north. Pair with `wind_east`. |
| `climate_continentality_region_id` | numeric | — | 0 … 29 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `climate_energy_stress_index` | numeric | `index` | 3.30e-5 … 1 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `dry_season_months` | numeric | `months` | 0 … 12 | seasonal | convention | Seasonal month count (0–12) derived from the monthly climate series. |
| `frost_months` | numeric | `months` | 0 … 12 | seasonal | convention | Seasonal month count (0–12) derived from the monthly climate series. |
| `growing_season_months` | numeric | `months` | 0 … 12 | seasonal | convention | Seasonal month count (0–12) derived from the monthly climate series. |
| `low_seasonal_insolation_w_m2` | numeric | `W/m²` | 117.5 … 396.8 | measurement | unit | Continuous per-cell field. Energy flux density (watts per square metre). |
| `orbital_insolation_variability_index` | numeric | `index` | 0.01607 … 0.5633 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `peak_seasonal_insolation_w_m2` | numeric | `W/m²` | 197.1 … 433.7 | measurement | unit | Continuous per-cell field. Energy flux density (watts per square metre). |
| `seasonal_aridity_index` | numeric | `index` | 0 … 0.916 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `seasonal_humidity_regime` | categorical | `category` | 3 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** arid_seasonal, humid_stable, summer_wet. |
| `seasonal_insolation_range_w_m2` | numeric | `W/m²` | 6.426 … 141.3 | measurement | unit | Continuous per-cell field. Energy flux density (watts per square metre). |
| `seasonal_precipitation_range_mm` | numeric | `mm` | 0.3245 … 612.1 | measurement | unit | Continuous per-cell field. Depth (millimetres). |
| `seasonal_wind_reversal_index` | numeric | `index` | 0 … 0.0166 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `surface_albedo_regime` | categorical | `category` | 8 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** arid_high_albedo, cold_sparse_cover, forest_canopy, ice_albedo, mixed_land, open_ocean, seasonal_grassland, shallow_ocean. |
| `surface_pressure_anomaly_hpa` | numeric | `hPa` | -6.713 … 6.241 | measurement | unit | Continuous per-cell field. Pressure (hectopascals). |
| `upwind_ocean_fetch_km` | numeric | `km` | 0 … 4382 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `vertical_velocity_index` | numeric | `index` | -0.3925 … 0.6421 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wet_season_months` | numeric | `months` | 0 … 12 | seasonal | convention | Seasonal month count (0–12) derived from the monthly climate series. |
| `wind_divergence_index` | numeric | `index` | -0.4563 … 0.4823 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |

---

## Oceans & coasts

<a id="ocean"></a>

**31 layers** · doc coverage: 8 curated · 21 convention · 1 unit · **1 generated (gaps)**.

**How it works.** Ocean surface currents (direction/speed/temperature/regime and transport), heat transport, upwelling, marine influence and regions, continental shelves, coral reefs (growth, bleaching risk, wave exposure, island support), coastal navigability, protected bays, and fisheries.

**Produced by:** `ocean_circulation.py`, `cpp/src/engine/ocean.cpp`, `reef_diagnostics.py`, `sea_level_diagnostics.py`.

**Pipeline stage:** Ocean circulation runs with the climate solve; reef/coast enrichers run on the final state.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `distance_to_marine_water_km` | numeric | `km` | 0 … 3741 | measurement | curated | Great-circle distance to the nearest marine (non-lake) water cell. |
| `fishery_productivity_index` | numeric | `index` | 0 … 0.7711 | index | curated | Marine biological productivity from upwelling, shelf area, and currents. |
| `ocean_current_east` | numeric | — | -1 … 1 | measurement | curated | Eastward component of the surface ocean current. Pair with `ocean_current_north`. |
| `ocean_current_north` | numeric | — | -0.5039 … 0.5039 | measurement | curated | Northward component of the surface ocean current. Pair with `ocean_current_east`. |
| `ocean_current_regime` | categorical | `category` | 10 classes | classification | curated | Classification of the local current (gyre limb, boundary current, drift, …). **Classes:** cold_equatorward_current, cold_poleward_current, cold_zonal_current, neutral_equatorward_current, neutral_poleward_current, neutral_zonal_current, non_marine, warm_equatorward_current, warm_poleward_current, warm_zonal_current. |
| `ocean_current_temperature_c` | numeric | `°C` | -3.088 … 3.085 | measurement | curated | Water temperature carried by the surface current (warm/cold current signature). |
| `ocean_heat_transport_index` | numeric | `index` | -0.02104 … 0.3457 | index | curated | Net poleward heat delivery by ocean currents, moderating nearby coasts. |
| `ocean_upwelling_index` | numeric | `index` | 0 … 0.7913 | index | curated | Upwelling strength; high values mark nutrient-rich coasts. |
| `coastal_navigability_index` | numeric | `index` | 0 … 0.8809 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `coastal_route_index` | numeric | `index` | 0 … 0.9475 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `marine_chokepoint_id` | numeric | — | -1 … 141 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `marine_influence_class` | categorical | `category` | 5 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** coastal, continental_core, interior, marine, maritime_influenced. |
| `marine_region_id` | numeric | — | -1 … 0 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `ocean_current_convergence_index` | numeric | `index` | -1 … 1 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `ocean_current_moisture_factor` | numeric | — | 0.8919 … 1.139 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `ocean_current_poleward_index` | numeric | `index` | -0.5039 … 0.5039 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `ocean_current_speed_index` | numeric | `index` | 0 … 1 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `ocean_current_system_id` | numeric | — | -1 … 47 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `ocean_current_transport_alignment` | numeric | — | 0 … 1 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `ocean_current_transport_distance_km` | numeric | `km` | 0 … 608.6 | measurement | unit | Continuous per-cell field. Distance (kilometres). |
| `ocean_current_transport_target_cell_id` | numeric | — | -1 … 4092 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `oceanic_crust_aging_event_count` | numeric | `count` | 0 … 6 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `oceanic_crust_rejuvenation_event_count` | numeric | `count` | 0 … 6 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `oceanic_humidity_availability_index` | numeric | `index` | 0.07707 … 0.9289 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `protected_bay_index` | numeric | `index` | 0 … 0.7776 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `reef_bleaching_risk_index` | numeric | `index` | 0 … 0.3884 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `reef_growth_index` | numeric | `index` | 0 … 0.7129 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `reef_island_support_index` | numeric | `index` | 0 … 0.5747 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `reef_system_id` | numeric | — | -1 … 27 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `reef_type` | categorical | `category` | 4 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** barrier_reef, cold_water_reef, fringing_reef, none. |
| `reef_wave_exposure_index` | numeric | `index` | 0 … 0.837 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |

> **Gaps in this domain (1):** `ocean_current_transport_alignment` — resolved by kind + template only. Add prose to `CURATED` in `layer_docs.js` to close these.

---

## Cryosphere (ice, glaciers, permafrost)

<a id="cryosphere"></a>

**25 layers** · doc coverage: 8 curated · 12 convention · 5 unit · **0 generated (gaps)**.

**How it works.** Ice sheets and glaciers (thickness, velocity, surface mass balance, flowlines, driving stress, basal sliding), glacial erosion/deposition and sediment transport, moraines, permafrost classes and extent, active-layer depth, and ground-ice content.

**Produced by:** `cryosphere_dynamics.py`, `cryosphere_flow.py`, `cryosphere_stability.py`, `glacial_landforms.py`, `permafrost_diagnostics.py`.

**Pipeline stage:** Cryosphere dynamics couple into the feedback loop; landform/permafrost classification is a post-pass.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `active_layer_depth_m` | numeric | `m` | 0 … 0.5345 | measurement | curated | Seasonal thaw depth above permafrost. |
| `deglaciation_age_ka` | numeric | `ka` | 0 … 82 | measurement | curated | Model time since the cell became ice-free. |
| `glacial_erosion_m` | numeric | `m` | 0 … 85 | measurement | curated | Total bedrock eroded by ice over the run. |
| `ice_surface_mass_balance_m_y` | numeric | `m/year` | 0 … 3.099 | measurement | curated | Accumulation minus ablation at the ice surface; positive feeds the glacier. |
| `ice_thickness_m` | numeric | `m` | 0 … 2133 | measurement | curated | Ice-sheet / glacier thickness in metres. |
| `ice_thickness_m` | stage×16 | `m` | 0 … 2164 | measurement | curated | Ice-sheet / glacier thickness in metres. |
| `ice_velocity_m_y` | numeric | `m/year` | 0 … 216.2 | measurement | curated | Ice surface flow speed. |
| `permafrost_class` | categorical | `category` | 6 classes | classification | curated | Continuous / discontinuous / sporadic / absent permafrost classification. **Classes:** continuous_permafrost, discontinuous_permafrost, ice_cemented_permafrost, no_permafrost, seasonal_frost, sporadic_permafrost. |
| `basal_sliding_index` | numeric | `index` | 0 … 0.88 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `glacial_deposition_index` | numeric | `index` | 0 … 0.95 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `glacial_erosion_intensity_index` | numeric | `index` | 0.00636 … 0.8115 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `glacial_meltwater_index` | numeric | `index` | 0 … 0.94 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `glacial_sediment_deposition_m` | numeric | `m` | 0 … 89.71 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `glacial_sediment_incoming_transfer_count` | numeric | `count` | 0 … 5 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `glacial_sediment_net_m` | numeric | `m` | -23.8 … 89.71 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `glacial_sediment_outgoing_transfer_count` | numeric | `count` | 0 … 1 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `glacial_sediment_production_m` | numeric | `m` | 0 … 23.8 | measurement | unit | Continuous per-cell field. Length/elevation/depth (metres). |
| `ground_ice_content_index` | numeric | `index` | 0 … 0.9067 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `ice_flowline_driving_stress_kpa` | numeric | `kPa` | 0 … 285.5 | measurement | unit | Continuous per-cell field. Stress/pressure (kilopascals). |
| `ice_flowline_flux_km3_y` | numeric | `km³/year` | 0 … 315.2 | measurement | unit | Continuous per-cell field. Volumetric flux (cubic kilometres per year). |
| `ice_flowline_path_count` | numeric | `count` | 0 … 1 | diagnostic | convention | Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity. |
| `ice_flowline_strain_heating_index` | numeric | `index` | 0 … 0.7979 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `ice_sheet_id` | numeric | — | -1 … 9 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `permafrost_extent_index` | numeric | `index` | 0 … 1 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `permafrost_region_id` | numeric | — | -1 … 7 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |

---

## Soils

<a id="soil"></a>

**14 layers** · doc coverage: 7 curated · 6 convention · 1 unit · **0 generated (gaps)**.

**How it works.** Soil profile development — type and texture class, depth, horizon count, pH, organic-matter fraction, drainage, erodibility, salinity, moisture, and derived agronomic fertility / agricultural potential.

**Produced by:** `soil_dynamics.py`, `land_use_zones.py` (agricultural zoning).

**Pipeline stage:** Enricher pass over the final climate, hydrology, and lithology.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `agricultural_potential_index` | numeric | `index` | 0 … 1 | index | curated | Suitability for agriculture from soils, climate, and terrain. |
| `fertility` | numeric | — | 0 … 1 | measurement | curated | Agronomic fertility score combining soil, climate, and water availability. |
| `soil_depth_m` | numeric | `m` | 0 … 3.346 | measurement | curated | Developed soil profile depth. |
| `soil_moisture_index` | numeric | `index` | 0 … 0.9266 | index | curated | Plant-available soil moisture. |
| `soil_ph` | numeric | `pH` | 4.88 … 8.025 | measurement | curated | Soil acidity/alkalinity. |
| `soil_texture_class` | categorical | `category` | 10 classes | classification | curated | Dominant soil texture (sand/silt/clay mixes). **Classes:** alluvial_silt, clay, clay_loam, glacial_till, loam, none, peat, sandy_loam, silt_loam, volcanic_ash. |
| `soil_type` | categorical | `category` | 11 classes | classification | curated | Soil classification from climate, parent material, and drainage. **Classes:** alluvial, arid, boreal, none, saline, temperate, thin_mountain, tropical, tundra, volcanic, wetland. |
| `agricultural_zone_id` | numeric | — | -1 … 32 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `soil_erodibility_index` | numeric | `index` | 0 … 0.7995 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `soil_horizon_count` | numeric | `count` | 0 … 4 | measurement | unit | Continuous per-cell field. Integer count. |
| `soil_organic_matter_fraction` | numeric | `fraction` | 0 … 0.35 | ratio | convention | Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1. |
| `soil_profile_development_index` | numeric | `index` | 0 … 0.8546 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `soil_profile_id` | numeric | — | -1 … 1487 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `soil_salinity_index` | numeric | `index` | 0 … 0.3368 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |

---

## Ecology, biomes & disturbance

<a id="ecology"></a>

**35 layers** · doc coverage: 9 curated · 23 convention · 2 unit · **1 generated (gaps)**.

**How it works.** Biome classification and ecotones, vegetation succession and biomass, net primary productivity, species richness/endemism/guilds and range fragmentation, wetlands (extent, hydrology, connectivity, type), and disturbance regimes (wildfire ignition/spread/fuel, ecosystem disturbance pressure).

**Produced by:** `biome_dynamics.py`, `biome_ecotones.py`, `biome_realism.py`, `ecosystem_dynamics.py`, `species_ranges.py`, `wildfire_disturbance.py`, `wetland_diagnostics.py`.

**Pipeline stage:** Enricher passes over the final climate/soil/hydrology state.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `biome` | categorical | `category` | 15 classes | classification | curated | Whittaker-style biome classification from temperature, moisture, and elevation. **Classes:** alpine, boreal_forest, cold_desert, continental_shelf, hot_desert, ice_cap, lake, ocean, savanna, temperate_forest, temperate_grassland, tropical_rainforest, tropical_seasonal_forest, tundra, wetland. |
| `biome_confidence_index` | numeric | `index` | 0.3685 … 0.971 | index | curated | Model confidence in the biome assignment; low values flag transitional or conflicted cells. |
| `ecotone_index` | numeric | `index` | 0 … 0.9447 | index | curated | How transitional the cell is between neighboring biomes. |
| `fire_frequency_index` | numeric | `index` | 0 … 0.612 | index | curated | Expected wildfire recurrence frequency. |
| `primary_productivity_index` | numeric | `index` | 0.1731 … 0.9295 | index | curated | Net primary productivity of the ecosystem. |
| `species_endemism_index` | numeric | `index` | 0 … 0.8348 | index | curated | Concentration of range-restricted species. |
| `species_richness_index` | numeric | `index` | 0.06864 … 0.8417 | index | curated | Relative species diversity. |
| `vegetation_biomass_index` | numeric | `index` | 0 … 0.9005 | index | curated | Standing vegetation biomass. |
| `wildfire_spread_risk_index` | numeric | `index` | 0 … 0.4294 | index | curated | Composite wildfire spread risk from fuel, climate, and wind alignment. |
| `biome_ecotone_confidence` | numeric | — | 0 … 0.9579 | measurement | generated | Continuous per-cell field. No documented unit for this field — inspect a cell for context. |
| `biome_ecotone_region_id` | numeric | — | -1 … 109 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `biome_ecotone_type` | categorical | `category` | 10 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** alpine_paramo, cloud_forest, cold_desert, cold_steppe, dry_forest, mangrove, mediterranean_scrub, none, swamp, taiga. |
| `biome_transition_zone` | categorical | `category` | 2 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** False, True. |
| `dominant_species_guild` | categorical | `category` | 10 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** alpine_tundra_specialist, canopy_tree, desert_specialist, freshwater_fish, grassland_grazer, large_predator, mangrove_coastal_bird, marine_fish, reef_builder, wetland_amphibian. |
| `ecosystem_disturbance_pressure_index` | numeric | `index` | 0 … 0.554 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `forest_growth_index` | numeric | `index` | 0 … 0.7917 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `species_composition_confidence_index` | numeric | `index` | 0.3986 … 0.7915 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `species_guild_richness_count` | numeric | `count` | 0 … 5 | measurement | unit | Continuous per-cell field. Integer count. |
| `species_habitat_suitability_index` | numeric | `index` | 0.4158 … 1 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `species_range_fragmentation_index` | numeric | `index` | 0 … 1 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `vegetation_recovery_years` | numeric | `years` | 23 … 69 | measurement | unit | Continuous per-cell field. Duration (years). |
| `vegetation_succession_stage` | categorical | `category` | 6 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** aquatic_primary_productivity, barren_ice, early_successional_cover, mature_closed_canopy, mid_successional_cover, pioneer_sparse_cover. |
| `wetland_coastal_flag` | categorical | `category` | 2 classes | classification | convention | Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering. **Classes:** False, True. |
| `wetland_connectivity_index` | numeric | `index` | 0 … 0.655 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wetland_ecotone_index` | numeric | `index` | 0 … 1 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wetland_extent_index` | numeric | `index` | 0 … 0.8814 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wetland_hydrology_index` | numeric | `index` | 0 … 1 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wetland_soil_saturation_index` | numeric | `index` | 0 … 0.8766 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wetland_system_id` | numeric | — | -1 … 73 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `wetland_system_type` | categorical | `category` | 7 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** floodplain_wetland, freshwater_swamp, lacustrine_wetland, mangrove, none, peatland, tidal_marsh. |
| `wildfire_disturbance_regime` | categorical | `category` | 7 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** fragmented_firebreak_mosaic, ice_or_barren_firebreak, low_fire_activity, non_burnable_water, seasonal_surface_fire, sparse_fuel, wind_driven_crown_fire. |
| `wildfire_firebreak_index` | numeric | `index` | 0.1034 … 1 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wildfire_fuel_continuity_index` | numeric | `index` | 0 … 0.6578 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wildfire_ignition_potential_index` | numeric | `index` | 0 … 0.5128 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `wildfire_wind_alignment_index` | numeric | `index` | 0.8821 … 1 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |

> **Gaps in this domain (1):** `biome_ecotone_confidence` — resolved by kind + template only. Add prose to `CURATED` in `layer_docs.js` to close these.

---

## Resources & economic geology

<a id="resources"></a>

**15 layers** · doc coverage: 6 curated · 9 convention · 0 unit · **0 generated (gaps)**.

**How it works.** Primary resource association per cell plus the systems that generate them — ore genesis (metallogenic fertility, structural control, hydrothermal alteration, placers), petroleum systems (source rock, maturation, migration, traps), mining/land-use zoning, and reserve-potential indices.

**Produced by:** `ore_genesis.py`, `petroleum_migration.py`, `commodity_resources.py`, `resource_dynamics.py`, `land_use_zones.py`.

**Pipeline stage:** Enricher passes over the final geology, tectonics, and sediment state.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `metallogenic_fertility_index` | numeric | `index` | 0.01661 … 0.9368 | index | curated | Crustal endowment favoring metal deposits. |
| `mining_potential_index` | numeric | `index` | 0 … 0.7921 | index | curated | Overall extractive potential combining ore systems and accessibility. |
| `ore_genesis_potential_index` | numeric | `index` | 0.06474 … 0.735 | index | curated | Combined favorability for ore formation from magmatic/hydrothermal/structural controls. |
| `petroleum_accumulation_index` | numeric | `index` | 0 … 0.5987 | index | curated | Modeled petroleum accumulation after generation, migration, and trapping. |
| `petroleum_source_rock_index` | numeric | `index` | 0 … 0.9159 | index | curated | Quality of organic-rich source rocks. |
| `resource` | categorical | `category` | 8 classes | classification | curated | Dominant natural-resource association for the cell (craton_iron_gold, sedimentary_fuels, …). **Classes:** coastal_fisheries, craton_iron_gold, evaporites, fertile_alluvium, geothermal, none, sedimentary_fuels, volcanic_arc_metals. |
| `hydrothermal_alteration_index` | numeric | `index` | 0.009706 … 0.7831 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `mining_zone_id` | numeric | — | -1 … 49 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `ore_genesis_system_id` | numeric | — | -1 … 43 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `ore_structural_control_index` | numeric | `index` | 5.31e-4 … 0.6126 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `petroleum_maturation_index` | numeric | `index` | 0 … 0.7202 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `petroleum_migration_path_index` | numeric | `index` | 0 … 0.6467 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `petroleum_system_id` | numeric | — | -1 … 173 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `petroleum_trap_integrity_index` | numeric | `index` | 0 … 0.5141 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `placer_concentration_index` | numeric | `index` | 6.88e-4 … 0.8667 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |

---

## Human & political geography

<a id="human"></a>

**20 layers** · doc coverage: 9 curated · 11 convention · 0 unit · **0 generated (gaps)**.

**How it works.** The human layer — settlement scoring, ports and harbours, transport routes and corridors, navigability classes, natural frontiers, and cultural / linguistic / political / territorial regions. Region ids partition the map into named entities.

**Produced by:** `settlement_routes.py`, `port_sites.py`, `route_corridors.py`, `navigability_diagnostics.py`, `cultural_geography.py`, `political_geography.py`, `territorial_geography.py`, `natural_frontiers.py`, `civilization_geography.py`.

**Pipeline stage:** Final enricher passes; the history/economy models (in `sections.json`, not per-cell layers) build on top.

| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `culture_region_id` | numeric | — | -1 … 4 | identifier | curated | Cultural region the cell belongs to. An id layer — colors are labels. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `harbor_suitability_index` | numeric | `index` | 0 … 0.9035 | index | curated | Physical harbor quality (shelter, depth, coastline shape). |
| `language_region_id` | numeric | — | -1 … 2 | identifier | curated | Language region the cell belongs to. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `natural_frontier_index` | numeric | `index` | 0 … 1 | index | curated | Strength of natural barriers (mountains, deserts, straits) at this cell. |
| `navigability_index` | numeric | `index` | 0 … 0.9035 | index | curated | How navigable the cell is for water/land transport, 0–1. |
| `political_region_id` | numeric | — | -1 … 4 | identifier | curated | Political region (polity) controlling the cell. Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `port_suitability_index` | numeric | `index` | 0 … 0.7474 | index | curated | Suitability for a port from harbor shelter, access, and hinterland. |
| `route_corridor_index` | numeric | `index` | 0 … 1 | index | curated | Suitability of the cell for long-distance route corridors. |
| `settlement_score` | numeric | — | 0 … 1 | measurement | curated | Composite habitability/attractiveness score used to seed settlements. |
| `mountain_pass_route_index` | numeric | `index` | 0 … 1 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `natural_frontier_id` | numeric | — | -1 … 10 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `natural_frontier_type` | categorical | `category` | 6 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** desert, ice, mountain, none, river, terrain_barrier. |
| `navigability_class` | categorical | `category` | 6 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** coastal_corridor, harbor, non_navigable, river_corridor, river_mouth, transport_chokepoint. |
| `oasis_route_index` | numeric | `index` | 0 … 0.6115 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `port_site_id` | numeric | — | -1 … 9 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `port_site_type` | categorical | `category` | 4 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** none, protected_bay_port, river_mouth_port, strait_port. |
| `route_corridor_id` | numeric | — | -1 … 27 | identifier | convention | Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful. |
| `route_corridor_type` | categorical | `category` | 4 classes | classification | convention | Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours. **Classes:** coastal_corridor, mountain_pass_corridor, none, river_valley_corridor. |
| `strait_access_index` | numeric | `index` | 0 … 0.7343 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |
| `transport_chokepoint_index` | numeric | `index` | 0 … 0.757 | index | convention | Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement. |

---

## Status & gaps summary

**Documentation gaps.** 12 of 439 layers (2.7%) fall to the generated tier — coordinate components, a few dimensionless physics quantities, and stage-ledger coordinates. Listed per domain above; each is a one-line addition to `CURATED`.

**Data-model gaps** (from the pipeline review — see [layers_review.md](layers_review.md) for detail):

- **Silent drops:** high-cardinality string fields (`healpix_like_pixel_code`, `s2_like_token`) still become no layer, but the exporter now records each one under the `skipped_layers` manifest key with a reason and keeps the column in `cells.parquet`; values remain reachable via the cell inspector. *(review F2, fixed)*
- **Code/name mismatch:** per-stage `lithology` ships as numeric codes 0–6 while `cells/lithology` uses alphabetical names; no code→name table is emitted. *(review F3)*
- **Identifiers as gradients:** ~30 `*_id` / `*_to` layers render as continuous ramps; flagged with the `identifier` role here and in the UI. *(review F8)*
- **Heavy-tailed scales:** layers like `flow_accumulation` (max ≫ p98) saturate under the p2–p98 ramp; the legend now shows `≥`/`≤` clip markers. *(review F6, fixed)*
- **Degenerate ranges:** 62 layers have p2 == p98 (mass-zero fields); the colour scale silently falls back to min/max. *(review F6)*

**How to close a gap.** Add the field to `CURATED` in [`layer_docs.js`](../src/magic_geo/debug_ui/layer_docs.js) (one line). The docs card, help-overlay coverage box, and this reference all read from that one map, so a new entry propagates everywhere on regeneration.
