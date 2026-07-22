# Mesh and Geometry

[Wiki home](../README.md) > Features > Mesh and Geometry

The magic-geo world is a spherical **cell mesh**: an unstructured finite-volume partition of the unit sphere, scaled by the configured planet radius, not a latitude/longitude raster. Every later stage — plates, crust transport, climate, hydrology, sediment, biomes — reads and writes state on those cells and conserves quantities across their control-volume boundaries, so the mesh is the substrate that makes the conservation audits in the rest of the pipeline meaningful at all. This page is the complete reference for how the mesh is constructed by both native backends, how each backend's control volumes are computed and certified, how the geometry is re-derived and closure-checked from the serialized document, and how the three deliberately distinct neighbor structures and the two Python-side spatial indices are laid out.

## On this page

- [Why a spherical cell mesh and not a raster](#why-a-spherical-cell-mesh-and-not-a-raster)
- [Where the mesh is built and what it produces](#where-the-mesh-is-built-and-what-it-produces)
- [Backend 1: `fibonacci_sphere`](#backend-1-fibonacci_sphere)
- [Backend 2: `geodesic_icosahedron`](#backend-2-geodesic_icosahedron)
- [Control-volume area and the sphere-closure check](#control-volume-area-and-the-sphere-closure-check)
- [Area replay from stored vertices](#area-replay-from-stored-vertices)
- [Three neighbor structures, deliberately distinct](#three-neighbor-structures-deliberately-distinct)
- [High-precision per-cell vectors](#high-precision-per-cell-vectors)
- [The spherical spatial index](#the-spherical-spatial-index)
- [The mesh LOD index](#the-mesh-lod-index)
- [The display boundary ring](#the-display-boundary-ring)
- [Configuration reference for mesh sizing](#configuration-reference-for-mesh-sizing)
- [Summary keys produced by the mesh and geometry layers](#summary-keys-produced-by-the-mesh-and-geometry-layers)
- [Validation coverage](#validation-coverage)
- [Worked examples](#worked-examples)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Why a spherical cell mesh and not a raster

The engine never materializes a rectangular grid. `build_mesh` produces a `std::vector<Cell>`, and every cell carries a genuine spherical polygon (`control_volume_vertices`) plus the identity of the cell across each of its polygon edges (`control_volume_edge_neighbor_ids`) — see `cpp/src/engine/types/core.hpp:35-50`. The consequences are structural, not cosmetic:

| Property | Raster (lat/lon grid) | magic-geo spherical cell mesh |
| --- | --- | --- |
| Cell area | Varies by `cos(lat)`; degenerate at the poles | Near-uniform; measured per cell and stored as `area_km2` |
| Pole handling | Singular; requires special-casing | No singularity — sites and control volumes are ordinary polygons everywhere |
| Antimeridian | Requires wrap logic in every algorithm | Not represented in the simulation; only appears in 2D display projections |
| Conservation | Flux across grid edges needs metric corrections | Flux crosses an explicit shared great-circle segment with a reciprocal partner (`cpp/src/engine/mesh.cpp:711-761`) |
| Total area closure | Approximate | Checked against `4·π·radius_km²` to a relative tolerance of `2.0e-10` (`cpp/src/engine/mesh.cpp:764-771`) |
| Neighbor count | Fixed 4/8 | Backend-dependent; Voronoi degree 5–7 observed at n = 128, or icosahedral degree 5/6 |

Because the control volumes are an exact partition (reciprocal shared edges, areas summing to the sphere), later stages can state a conservation residual rather than assume one. That is what makes the crust-transport closure errors, the hydrologic water-budget residuals, and the sediment-partition audits reportable numbers instead of hand-waving. The control-volume polygons are consumed directly by the forward-overlap crust transport (`cpp/src/engine/crust_transport.cpp`, serialized as `crust_transport_model = "forward_spherical_control_volume_overlap_v1"`) and by the directed cross-plate boundary-segment ledger (`cpp/src/engine/plate_boundary_segments.cpp`), which is why the source comment at `types/core.hpp:41` calls them "Authoritative finite-volume geometry" rather than a display artifact. What that word certifies is the geometry, not the physics computed on it — the transport, mass-provenance, and boundary-polarity claims are scoped on their own pages.

The mesh is also **static**. `build_mesh` runs once, at the top of the pipeline, and the cell partition never changes afterwards; only the state carried on the cells evolves. The geo layer contract classifies the mesh with `temporal_class = "static_simulation_domain"` and `evidence_class = "independent_geometry_replay"` (`src/magic_geo/geo_layer_contracts.py:40-55`).

## Where the mesh is built and what it produces

`build_mesh(params)` is stage 1 of the simulation pipeline, before anything else exists:

```cpp
// cpp/src/engine/pipeline.cpp:12-15
earth.cells = build_mesh(params);
if (params.plate_count >= static_cast<int>(earth.cells.size())) {
    throw std::runtime_error("plate_count must be smaller than generated mesh cell count");
}
```

Dispatch is a single branch (`cpp/src/engine/mesh.cpp:1047-1052`):

```cpp
std::vector<Cell> build_mesh(const Params& params) {
    if (params.mesh_backend == MESH_BACKEND_GEODESIC_ICOSAHEDRON) {
        return build_geodesic_icosahedron_mesh(params);
    }
    return build_fibonacci_mesh(params);
}
```

Backend identifiers are `MESH_BACKEND_FIBONACCI = 0` and `MESH_BACKEND_GEODESIC_ICOSAHEDRON = 1` (`cpp/src/engine/constants.hpp:98-99`); the Python side mirrors them in `MESH_BACKEND_IDS` in `src/magic_geo/native.py`.

### Mesh fields on `Cell`

These are the fields `build_mesh` populates; everything else on `Cell` is filled by later stages.

| Field | Type | Meaning | Source |
| --- | --- | --- | --- |
| `id` | `int` | Dense index, `0 .. cells.size()-1`; also the array position | `types/core.hpp:36` |
| `p` | `Vec3` | Unit-sphere site position (cell center) | `types/core.hpp:37` |
| `lat` | `double` | Latitude in **radians**, `asin(p.z)` | `types/core.hpp:38` |
| `lon` | `double` | Longitude in **radians**, `atan2(p.y, p.x)` | `types/core.hpp:39` |
| `area_km2` | `double` | Control-volume area = steradians × `radius_km²` | `types/core.hpp:40` |
| `control_volume_vertices` | `std::vector<Vec3>` | Closed spherical polygon, counter-clockwise seen from outside | `types/core.hpp:48` |
| `control_volume_edge_neighbor_ids` | `std::vector<int>` | Entry `i` is the cell across the great-circle edge from vertex `i` to vertex `(i+1) % n` | `types/core.hpp:49` |
| `neighbors` | `std::vector<int>` | Process stencil — **not** the same set as the edge neighbors | `types/core.hpp:50` |

The comment block at `cpp/src/engine/types/core.hpp:41-47` states the contract verbatim, including the geodesic-specific caveat that "a geodesic barycentric dual can have two consecutive edge segments with the same neighboring cell because the shared dual boundary bends at the primal-edge midpoint."

### Backend identity in the serialized document

Two top-level keys record the backend and its area model, emitted by `serialize_world` at `cpp/src/engine/world_serialization.cpp:52-53` and mirrored into `summary` at `cpp/src/engine/summary.cpp:1320-1321`:

| `mesh_backend` | `cell_area_model` | Set by |
| --- | --- | --- |
| `fibonacci_sphere` | `spherical_voronoi_control_volume_v1` | `cpp/src/engine/core.cpp:104-124` |
| `geodesic_icosahedron` | `spherical_barycentric_control_volume_v2` | `cpp/src/engine/core.cpp:104-124` |
| `unknown` | `unknown` | Default branch only; unreachable in practice because `validate_params` rejects any other backend id (`cpp/src/engine/core.cpp:290-293`) |

The Python replay hard-codes the same pairing in `CONTROL_VOLUME_AREA_MODELS` (`src/magic_geo/control_volume_geometry.py:8-11`) and fails the inspection if the two keys disagree (`src/magic_geo/control_volume_geometry.py:66-68`).

---

## Backend 1: `fibonacci_sphere`

`build_fibonacci_mesh` (`cpp/src/engine/mesh.cpp:776-838`) is the default. It produces **exactly `params.cell_count` cells** and a genuine spherical Voronoi tessellation of them.

### Step 1 — Site placement (`mesh.cpp:779-788`)

```cpp
const double golden_angle = PI * (3.0 - std::sqrt(5.0));
for (int i = 0; i < n; ++i) {
    const double z = 1.0 - 2.0 * (static_cast<double>(i) + 0.5) / static_cast<double>(n);
    const double r = std::sqrt(std::max(0.0, 1.0 - z * z));
    const double theta = golden_angle * static_cast<double>(i);
    cells[i].id = i;
    cells[i].p = {std::cos(theta) * r, std::sin(theta) * r, z};
    cells[i].lat = std::asin(z);
    cells[i].lon = std::atan2(cells[i].p.y, cells[i].p.x);
}
```

The `+ 0.5` offset centers the z-band sampling so no site lands exactly on a pole. `PI` is the 36-digit literal at `cpp/src/engine/constants.hpp:5`. This is deterministic and seed-independent: the site set and the control volumes derived from it are a pure function of `cell_count` (and `radius_km` for the area scaling), and `neighbors` additionally depends on `neighbor_count`. Nothing in `build_mesh` reads `params.seed`.

### Step 2 — Process-stencil neighbors via a bounded kd-tree

A 3-D kd-tree over the sites (`FibonacciKdTree`, `mesh.cpp:86-294`) answers a *k*-nearest query per cell, where *k* = `params.neighbor_count`:

```cpp
// mesh.cpp:790-795
const int k = params.neighbor_count;
const FibonacciKdTree index(cells);
#pragma omp parallel for schedule(static)
for (int i = 0; i < n; ++i) {
    cells[static_cast<std::size_t>(i)].neighbors = index.nearest_neighbor_ids(i, k);
}
```

Details that matter for determinism:

| Mechanism | Location | Behavior |
| --- | --- | --- |
| Similarity metric | `mesh.cpp:36-39` | Dot product of unit vectors — larger is closer |
| Tree split | `mesh.cpp:135-156` | `nth_element` on axis `depth % 3`, with `left_id < right_id` as the exact tie-break |
| Pruning bound | `mesh.cpp:193-216` | Axis-aligned-bounding-box maximum dot product, computed in `long double`, inflated by `128 · DBL_EPSILON · (1 + Σ|term|)` so pruning stays conservative under a few-ULP-different `dot()` |
| Order canonicalization | `mesh.cpp:102-107` | The retained superset of visited ids is **sorted ascending** before final selection, so the tree's traversal order cannot change the result relative to the ascending-id reference |
| Deficiency guard | `mesh.cpp:62-67` | Throws `Fibonacci nearest-neighbor search returned too few candidates` if fewer than `min(k, n-1)` are retained |
| Brute-force gate | `mesh.cpp:296-299`, `797-806` | With environment variable `MAGIC_GEO_VALIDATE_FIBONACCI_KNN=1`, every cell's kd-tree result is compared against `brute_force_neighbor_ids`; a mismatch throws `optimized Fibonacci nearest-neighbor search diverged from brute-force reference`. Registered as the separate CTest name `magic_geo_fibonacci_knn_reference` |

**Ordering of `neighbors`.** `select_neighbor_ids` returns `best` sorted ascending by `(dot_product, id)` — that is, **farthest first, nearest last**. Then symmetrization appends back-links:

```cpp
// mesh.cpp:807-814
for (int i = 0; i < n; ++i) {
    for (int j : cells[i].neighbors) {
        auto& back = cells[j].neighbors;
        if (std::find(back.begin(), back.end(), i) == back.end()) {
            back.push_back(i);
        }
    }
}
```

So the final list is: the *k* nearest ordered farthest→nearest, followed by any symmetrizing back-links in ascending source-cell order. Back-links are appended without re-sorting, so they are typically farther than every entry before them. Observed on the `smoke` profile (n = 128, k = 7), cell 30's `neighbors` is `[9, 25, 51, 38, 22, 17, 43, 35, 64]` with dot products `0.888, 0.889, 0.930, 0.943, 0.949, 0.952, 0.956, 0.877, 0.845` — the ascending run of seven, then two farther back-links. Do not assume `neighbors` is sorted by anything.

### Step 3 — Voronoi control volume in a gnomonic chart

`build_fibonacci_control_volume` (`mesh.cpp:520-679`) computes the exact spherical Voronoi cell of each site. The construction is a half-plane clip in a gnomonic (central) projection tangent at the site, which is valid because the spherical Voronoi inequality `⟨v, p⟩ ≥ ⟨v, q⟩` becomes a **linear** half-plane constraint in that chart.

| # | Step | Location | Detail |
| --- | --- | --- | --- |
| 1 | Tangent basis | `mesh.cpp:325-336` | Reference axis is `(0,0,1)` when `|p.z| < 0.8`, otherwise `(1,0,0)`; two orthonormal tangent vectors are derived by `checked_normalize(cross(...))` |
| 2 | Seed constraints | `mesh.cpp:527-531` | The `min(24, n-1)` nearest sites (a `std::set<int>`, i.e. iterated in ascending id order) |
| 3 | Start polygon | `mesh.cpp:534, 537-542` | The square `[-16, 16]²` in chart coordinates |
| 4 | Clip | `mesh.cpp:406-439, 543-552` | Sutherland–Hodgman clipping against `a·u + b·v ≤ c` with `a = ⟨e₁, q⟩`, `b = ⟨e₂, q⟩`, `c = 1 − ⟨p, q⟩`, all in `long double` |
| 5 | Inside predicate | `mesh.cpp:347-360` | `value ≤ 256 · DBL_EPSILON · scale`. The comment is explicit: "Sites are binary64 inputs. Long-double arithmetic reduces cancellation, but it cannot justify predicates tighter than the input precision." |
| 6 | Degeneracy prune | `mesh.cpp:379-404` | Consecutive/wrap-around duplicate chart vertices closer than `1.0e-15` (squared tolerance `1.0e-30`) are dropped |
| 7 | Boundedness check | `mesh.cpp:553-558` | Any surviving vertex with `\|u\|` or `\|v\| ≥ 15.84` (`16 × 0.99`) throws `spherical Voronoi cell remained unbounded in tangent projection` |
| 8 | Certificate loop | `mesh.cpp:560-581` | Each chart vertex is lifted to the sphere and passed to `nearest_cell_id`. Any site that beats the owner by more than `2.0e-13` is added to the constraint set and the whole polygon is re-clipped from scratch. Up to 64 iterations |
| 9 | Termination | `mesh.cpp:574-584` | Empty violation set → `verified = true`. A fixpoint with violations, or 64 exhausted iterations, throws `spherical Voronoi cell did not pass nearest-site verification` |

The comment at `mesh.cpp:640-643` states why vertex-only certification is sufficient: "each spherical Voronoi inequality becomes a linear half-plane in this gnomonic chart, so if every vertex satisfies every site constraint, the whole convex polygon does too."

### Step 4 — Edge-neighbor attribution (`mesh.cpp:596-621`)

For every polygon edge `(start, end)` the generating site is recovered by minimizing the scale-normalized half-plane residual over the constraint set:

```
residual(q) = max(|f(start, q)|, |f(end, q)|) / (1 + |a| + |b| + |c|)
```

The set is iterated in ascending id order, so the lowest id wins an exact tie. If the best residual exceeds `1.0e-10`, `spherical Voronoi edge has no generating neighbor` is thrown.

### Step 5 — Canonical vertices (`mesh.cpp:493-518, 623-638`)

Each polygon vertex is then **replaced** by a canonical recomputation from its three generating sites, so all three incident cells emit a bit-identical vertex:

```cpp
std::array<int, 3> ids = {first_id, second_id, third_id};
std::sort(ids.begin(), ids.end());
...
Vec3 result = checked_normalize(cross(sub(first, second), sub(first, third)), ...);
const Vec3 site_sum = add(add(first, second), third);
const double orientation = dot(result, site_sum);
if (orientation < 0.0 || (orientation == 0.0 && dot(result, approximate) < 0.0)) {
    result = mul(result, -1.0);
}
```

Sorting the three ids makes the expression order independent of which cell asks; the orientation flip picks the hemisphere containing the generating sites, with the pre-canonical approximate vertex only as a last-resort tie-break. This is the mechanism that makes the reciprocal-endpoint check downstream pass exactly (observed `maximum_shared_endpoint_error = 0.0`).

### Step 6 — Final certification (`mesh.cpp:644-678`)

Every edge of the canonical polygon must pass four checks:

| Check | Threshold | Error message |
| --- | --- | --- |
| No duplicate consecutive vertices | `‖start − end‖ > 1.0e-12` | `spherical Voronoi polygon has a duplicate vertex` |
| Counter-clockwise winding | `⟨p, start × end⟩ > 0` | `spherical Voronoi polygon is not counter-clockwise` |
| Both endpoints nearest-site owned | `⟨v, p_nearest⟩ ≤ ⟨v, p⟩ + 2.0e-11` | `canonical spherical Voronoi vertex failed nearest-site verification` |
| Both endpoints on the bisector | `\|⟨v, p − p_neighbor⟩\| ≤ 2.0e-11` | `canonical spherical Voronoi edge left its bisector` |

### Parallelism and error propagation (`mesh.cpp:816-835`)

Control volumes are built under `#pragma omp parallel for schedule(static)`, but exceptions cannot cross an OpenMP region, so each iteration catches into a per-cell `std::vector<std::string>` and the serial loop afterwards rethrows the **lowest-indexed** failure as `Fibonacci control-volume cell <i>: <message>`. The failure reported is therefore deterministic regardless of thread count.

### Fibonacci topology invariants

For *n* sites in general position, the Voronoi diagram is dual to a sphere triangulation, giving exact Euler counts that `control_volume_geometry.py:232-243` asserts:

| Quantity | Formula | Observed at n = 128 |
| --- | --- | --- |
| Undirected control-volume edge pairs | `3n − 6` | 378 |
| Distinct Voronoi vertices | `2n − 4` | 252 |
| Incidence per Voronoi vertex | exactly 3 | 3 |
| Sum of per-cell vertex counts | `3 · (2n − 4)` | 756 |
| Mean control-volume edges per cell | `6 − 12/n` | 5.90625 |
| Per-cell edge-neighbor ids | all distinct | verified |

---

## Backend 2: `geodesic_icosahedron`

`build_geodesic_icosahedron_mesh` (`cpp/src/engine/mesh.cpp:890-1045`) subdivides an icosahedron and uses its **vertices** as cells. Its control volume is the *barycentric* dual (edge midpoints plus face centroids), not a Voronoi diagram.

### Step 1 — Frequency selection (`mesh.cpp:840-844`)

```cpp
int geodesic_frequency_for_target(int cell_count) {
    const double target = static_cast<double>(std::max(12, cell_count));
    const double raw = std::sqrt(std::max(0.0, (target - 2.0) / 10.0));
    return std::max(1, static_cast<int>(std::ceil(raw - 1.0e-9)));
}
```

This inverts the vertex count of a frequency-*f* geodesic sphere, `10f² + 2`, and rounds up. **The generated mesh is therefore almost never the requested size.**

| Requested `mesh.cell_count` | Frequency *f* | Generated cells `10f²+2` | Triangles `20f²` | Primal edges `30f²` |
| --- | --- | --- | --- | --- |
| 128 | 4 | 162 | 320 | 480 |
| 512 | 8 | 642 | 1,280 | 1,920 |
| 1,024 | 11 | 1,212 | 2,420 | 3,630 |
| 2,048 | 15 | 2,252 | 4,500 | 6,750 |
| 4,096 | 21 | 4,412 | 8,820 | 13,230 |
| 8,192 | 29 | 8,412 | 16,820 | 25,230 |
| 20,000 | 45 | 20,252 | 40,500 | 60,750 |
| 200,000 | 142 | 201,642 | 403,280 | 604,920 |

The 128 → 162 and 4096 → 4412 rows were confirmed by generation; the rest are computed from the same source expression. Downstream consumers that care about actual size read the generated count: the `plate_count` guard at `cpp/src/engine/pipeline.cpp:13`, the `summary.cell_count` emitted from `cells.size()` at `cpp/src/engine/summary.cpp:1322`, and automatic compute-backend eligibility, which is driven by `ensure_auto_backend(actual_cell_count)` at `cpp/src/opencl_compute.cpp:952` against the thresholds `OPENCL_AUTO_MIN_CELL_COUNT = 32768`, `CUDA_SM_120_AUTO_MIN_CELL_COUNT = 8192`, `CUDA_UNCALIBRATED_AUTO_MIN_CELL_COUNT = 32768` (`cpp/src/opencl_compute.cpp:99-101`).

### Step 2 — Base icosahedron (`mesh.cpp:891-905`)

Twelve normalized vertices built from `t = (1 + √5) / 2` on the three orthogonal golden rectangles, and a fixed table of 20 triangular faces. Both arrays are literal and identical on every run.

### Step 3 — Face subdivision (`mesh.cpp:916-946`)

Each of the 20 faces is walked on a triangular lattice with barycentric integer weights `(k, i, j)` summing to *f*:

```cpp
const Vec3 point = add(add(mul(a, (double)k), mul(b, (double)i)), mul(c, (double)j));
```

Points are inserted through `add_geodesic_vertex` (`mesh.cpp:846-867`), which deduplicates across face boundaries by quantizing each normalized component with `llround(component * 1e9)` into a `std::array<long long, 3>` map key. Two triangles are emitted per lattice cell (the second only when `j < frequency − i − 1`), and each triangle inserts three undirected edges into per-vertex `std::set<int>` neighbor sets.

Because the key is a rounded 1e-9 lattice, coincident vertices from adjacent faces merge exactly; this is a quantization, not a tolerance test, so a pair of genuinely distinct points closer than half a lattice step would also merge. No such case arises for the frequencies reachable from the validated `cell_count` range, but the mechanism is a rounding rule and is stated as such.

### Step 4 — Cells (`mesh.cpp:948-959`)

`lat = asin(clamp(p.z, -1, 1))`, `lon = atan2(p.y, p.x)`, and `neighbors` is assigned straight from the `std::set<int>` — so for this backend `neighbors` **is** the primal triangulation adjacency, in ascending id order, with exactly 12 vertices of degree 5 (the original icosahedron corners) and every other vertex of degree 6. `params.neighbor_count` is ignored entirely by this backend. Across the whole native tree it appears exactly three times: `cpp/src/c_api.cpp:31` copies it out of the config struct, `cpp/src/engine/core.cpp:302-303` range-checks it, and `cpp/src/engine/mesh.cpp:790` is the only place it changes any output — the Fibonacci *k*-NN stencil.

### Step 5 — Barycentric control volume (`mesh.cpp:961-1042`)

Two families of control points are collected per cell:

| Family | Construction | Tag |
| --- | --- | --- |
| Primal-edge midpoint | `normalize(p_cell + p_neighbor)` | `midpoint_neighbor_id = neighbor`, `face_id = -1` |
| Primal-face centroid | `normalize(p₀ + p₁ + p₂)` of each incident triangle | `midpoint_neighbor_id = -1`, `face_id = face` |

Both go through `checked_normalize` with the contexts `"geodesic primal-edge midpoint"` and `"geodesic primal-face center"`, which throws `... is geometrically degenerate` if the squared norm is non-finite or `≤ 1.0e-28`.

The combined list is sorted by tangent-plane angle `atan2(⟨q, e₂⟩, ⟨q, e₁⟩)` ascending, with `midpoint_neighbor_id` then `face_id` as exact tie-breaks (`mesh.cpp:1002-1019`). The sorted ring must strictly alternate midpoint / face-centroid; otherwise `geodesic barycentric control-volume vertices do not alternate` is thrown (`mesh.cpp:1030-1034`). Each edge takes its neighbor id from whichever of its two endpoints is a midpoint (`mesh.cpp:1035-1039`).

The alternation therefore forces **every primal neighbor to appear exactly twice** in `control_volume_edge_neighbor_ids` — the dual boundary bends at the midpoint. Verified on a generated 162-cell world, cell 0 (a degree-5 icosahedron corner):

```
neighbors                        = [1, 5, 15, 25, 35]              (5 entries)
control_volume_vertices_3d       = 10 vertices
control_volume_edge_neighbor_ids = [25, 25, 35, 35, 5, 5, 1, 1, 15, 15]
```

| Vertex degree | Control-volume vertices | Control-volume edges | Distinct edge neighbors |
| --- | --- | --- | --- |
| 5 (12 cells, always) | 10 | 10 | 5, each twice |
| 6 (all others) | 12 | 12 | 6, each twice |

`control_volume_geometry.py:244-250` encodes exactly this as the geodesic topology assertion: the multiset of edge neighbors must equal the `neighbors` set with every count equal to 2.

There is **no** nearest-site certification for this backend. A barycentric dual is not a Voronoi diagram, so no Voronoi predicate applies; the guarantees it does carry are reciprocity and closure, checked by the shared partition validator below. `control_volume_geometry.py:184-225` correspondingly runs the bisector and nearest-site tests only when `mesh_backend == "fibonacci_sphere"`.

---

## Control-volume area and the sphere-closure check

### Per-cell area (`mesh.cpp:455-491`)

`control_volume_area_steradians` fans the polygon from the site and sums spherical excess with a Kahan compensation:

```
determinant = ⟨p, vᵢ × vᵢ₊₁⟩                      (signed triple product, long double)
denominator = 1 + ⟨p, vᵢ⟩ + ⟨vᵢ, vᵢ₊₁⟩ + ⟨vᵢ₊₁, p⟩
triangle    = 2 · atan2(determinant, denominator)
```

Two properties are load-bearing:

- The determinant is **signed**, so the routine is orientation-sensitive. It throws `control-volume polygon is not finite and counter-clockwise` if the accumulated area is non-finite or `≤ 0`. This is deliberately *not* the `abs()`-taking `spherical_triangle_area_steradians` in `cpp/src/engine/core.cpp:98-102`.
- The Kahan compensation (`mesh.cpp:480-483`) bounds the accumulated rounding across many small triangles.

`area_km2 = steradians × radius_km²` at `mesh.cpp:821-823` (Fibonacci) and `mesh.cpp:1041` (geodesic).

### Shared partition validator (`mesh.cpp:681-772`)

`validate_control_volume_partition` runs once per backend with a `backend_name` label of `"Fibonacci Voronoi"` or `"geodesic barycentric"`. Every message is prefixed with that label.

| Check | Condition | Message suffix |
| --- | --- | --- |
| Polygon completeness | `≥ 3` vertices, vertex count == edge-neighbor count, `area_km2` finite and `> 0` | `control-volume geometry is incomplete` |
| Neighbor id validity | `0 ≤ id < cells.size()` and `id != cell.id` | `control-volume edge neighbor is invalid` |
| Shared-edge multiplicity | count of `neighbor` in this cell's edge list == count of `cell.id` in the neighbor's edge list | `control-volume shared-edge multiplicity is not reciprocal` |
| Shared-edge endpoints | some reverse segment satisfies `‖start − reverse_end‖ ≤ 1.0e-10` **and** `‖end − reverse_start‖ ≤ 1.0e-10` | `control-volume shared-edge endpoints are not reciprocal` |
| Sphere closure | `\|Σ area_km2 − 4·π·radius_km²\| ≤ 4·π·radius_km² · 2.0e-10` | `control-volume areas do not close to the sphere` |

The endpoint test requires *reversed* orientation — cell A traverses the shared edge one way and cell B the other — which is the direct consequence of both polygons being counter-clockwise from outside.

The relative closure tolerance of `2.0e-10` is the strictest of the three sphere-closure gates described on this page — the native builder's `2.0e-10`, the Python replay's `2.0e-10` / `2.0e-9` pair, and `validate-geo`'s `2.0e-6`. It is a closure tolerance, not a claim about every area comparison in the tree (`crust_transport.cpp:1621`, for example, uses a `1.0e-13` relative *negligible-piece* threshold for a different purpose). The Python replay reuses the same constant for the emitted totals (`src/magic_geo/control_volume_geometry.py:263`).

---

## Area replay from stored vertices

`inspect_control_volume_geometry(world)` (`src/magic_geo/control_volume_geometry.py:60-286`) re-derives every control-volume area from nothing but the serialized `position_3d`, `control_volume_vertices_3d`, `control_volume_edge_neighbor_ids`, and `planet_parameters.radius_km`. It never reads `area_km2` except to compare against it. It is the evidence behind the `native_cell_area_model_replay` gate.

### Replay procedure

1. Check `mesh_backend` ↔ `cell_area_model` pairing against `CONTROL_VOLUME_AREA_MODELS`.
2. Require a finite positive `planet_parameters.radius_km`.
3. Per cell: `id == array index`, no duplicate ids, `≥ 3` vertices, vertex count == neighbor count, finite positive `area_km2`.
4. Unit-norm error of the position and every vertex.
5. Area by `math.fsum` of `_triangle_area_steradians(position, vᵢ, vᵢ₊₁)` × `radius_km²` — note this Python helper uses `abs()` on the triple product (`control_volume_geometry.py:49-57`), so orientation is checked separately.
6. Winding: count edges with `⟨p, start × end⟩ < −2.0e-12`.
7. Vertex incidence tally on components rounded to 10 decimals.
8. Directed segment map `(cell, neighbor) → [(start, end), ...]`.

### Replay tolerance table

| Check | Tolerance | Failure string | Line |
| --- | --- | --- | --- |
| Unit norm of position and vertices | `≤ 5.0e-9` | `per-cell control-volume geometry is invalid` | `control_volume_geometry.py:131` |
| Per-cell area replay | `≤ max(0.001 km², area_km2 × 2.0e-9)` | `per-cell control-volume geometry is invalid` | `:146` |
| Counter-clockwise winding | `⟨p, s×e⟩ ≥ −2.0e-12` | `control-volume vertices are not counter-clockwise` | `:161-167` |
| Reciprocal edge topology | reverse pair exists, equal segment multiplicity, `neighbor != cell` | `control-volume edge-neighbor topology is invalid` | `:174-205` |
| Reciprocal endpoints | `dist(start, rev_end) + dist(end, rev_start) ≤ 5.0e-9` | `reciprocal control-volume edge endpoints do not match` | `:202-207` |
| Voronoi bisector (Fibonacci only) | `\|⟨v,p⟩ − ⟨v,q⟩\| ≤ 2.0e-9` | `Fibonacci control-volume edges are not Voronoi bisectors` | `:208-209` |
| Nearest-site ownership (Fibonacci, **only when `n ≤ 512`**) | `max_q⟨v,q⟩ − ⟨v,p⟩ ≤ 2.0e-9` | `Fibonacci control-volume vertex is outside its nearest-site cell` | `:210-225` |
| Fibonacci Euler topology | `3n−6` edge pairs, `2n−4` vertices, incidence 3, distinct per-cell neighbors | `control-volume topology does not match its declared mesh model` | `:232-243` |
| Geodesic dual topology | edge-neighbor multiset == `neighbors` set with every count `== 2` | same | `:244-250` |
| Emitted total area closure | `\|Σ area_km2 − 4πR²\| ≤ max(0.01 km², 4πR² × 2.0e-10)` | `control-volume areas do not close to the spherical surface` | `:263` |
| Replayed total area closure | `\|Σ replayed − 4πR²\| ≤ max(0.01 km², 4πR² × 2.0e-9)` | same | `:264` |

The nearest-site brute force is `O(n²)` and is therefore gated at 512 cells. Above that threshold the replay checks bisector membership and topology but **not** global nearest-site ownership — an intentional cost cut, and a real reduction in coverage for production-sized meshes.

### Returned metrics

`inspect_control_volume_geometry` returns `{"passed": bool, "failures": [...], "metrics": {...}}`. Measured values below are from a `smoke`-profile `fibonacci_sphere` world (n = 128, `radius_km = 6371`).

| Metric | Meaning | Observed (n = 128) |
| --- | --- | --- |
| `cell_count` | Length of the `cells` array | 128 |
| `control_volume_vertex_count` | Sum of per-cell vertex counts | 756 |
| `control_volume_segment_count` | Directed segment total / 2 | 378 |
| `control_volume_edge_pair_count` | Distinct undirected `(min, max)` pairs | 378 |
| `maximum_area_replay_error_km2` | Worst per-cell replay difference | 2.33e-9 |
| `surface_closure_error_km2` | `\|Σ area_km2 − 4πR²\|` | 0.0 |
| `replayed_surface_closure_error_km2` | `\|Σ replayed − 4πR²\|` | 5.96e-8 |
| `maximum_unit_norm_error` | Worst `\|‖v‖ − 1\|` over positions and vertices | 2.22e-16 |
| `maximum_voronoi_bisector_error` | Fibonacci only; `0.0` for geodesic | 1.11e-16 |
| `maximum_nearest_site_violation` | Fibonacci and `n ≤ 512` only | 1.11e-16 |
| `maximum_shared_endpoint_error` | Worst reciprocal endpoint mismatch | 0.0 |

`maximum_shared_endpoint_error = 0.0` is the direct consequence of the canonical-vertex recomputation in step 5 of the Fibonacci construction: all three incident cells compute the same vertex from the same sorted site triple, so the stored doubles are bit-identical.

---

## Three neighbor structures, deliberately distinct

Three different adjacency notions exist in a magic-geo world, and conflating them is the single most common way to misread the document.

| | `cells[].neighbors` | `cells[].control_volume_edge_neighbor_ids` | `cell_adjacency_edges` |
| --- | --- | --- | --- |
| Name in source | process stencil | edge-aligned control-volume neighbors | adjacency edge list |
| Produced by | `mesh.cpp:790-814` (Fibonacci), `mesh.cpp:955-958` (geodesic) | `mesh.cpp:596-621` (Fibonacci), `mesh.cpp:1025-1040` (geodesic) | `src/magic_geo/cell_geometry.py:358-503` |
| Layer | native C++ | native C++ | Python enricher |
| Semantics | "cells this cell exchanges with in stencil operators" | "cell across control-volume edge *i*" | undirected edge records with measured geometry |
| Cardinality (Fibonacci) | `≥ neighbor_count`, more after symmetrization | Voronoi degree; all ids distinct | one record per undirected pair in `neighbors` |
| Cardinality (geodesic) | 5 or 6 | 10 or 12; every id appears exactly twice | one record per undirected pair in `neighbors` |
| Order | *k* nearest farthest→nearest, then back-links (Fibonacci); ascending id (geodesic) | ring order, aligned 1:1 with `control_volume_vertices_3d` | insertion order of the `id` field |
| Built from | *k*-NN by dot product / primal triangulation | polygon edges | `neighbors`, **not** the control-volume edges |
| Used for | diffusion, flow routing, flood fill, connectivity | flux geometry, plate-boundary segments, crust overlap | Python graph and boundary diagnostics |

### Why they are not the same set

For `fibonacci_sphere`, *k*-nearest-neighbor adjacency and Voronoi adjacency are different relations. Measured on the `smoke` profile (n = 128, `neighbor_count = 7`):

| Set | Undirected edge count |
| --- | --- |
| Control-volume (Voronoi) edges | 378 (= `3n − 6`) |
| Process-stencil edges (`neighbors`, symmetrized) | 482 |
| Voronoi edges absent from the stencil | 0 |
| Stencil edges that are not Voronoi edges | 104 |

So at this configuration the stencil is a strict superset — but that is an *observation at n = 128, k = 7*, not an invariant the source establishes. Nothing in `mesh.cpp` guarantees that every Voronoi neighbor is among the *k* nearest sites; a large-degree Voronoi cell with a small `neighbor_count` could lose an edge from the stencil. Treat "stencil ⊇ Voronoi" as unverified in general.

For `geodesic_icosahedron` the stencil and the primal triangulation coincide exactly (both are the `std::set` neighbor sets), and the control-volume edge list is a doubled version of it. Observed at 162 cells: 480 adjacency-edge records = `30f²` = 30 × 16.

### The `cell_adjacency_edges` record

Written to the top-level key `cell_adjacency_edges` by `enrich_world_with_cell_geometry`. 22 fields per record (`src/magic_geo/cell_geometry.py:423-459`), all floats rounded to 6 decimals:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | int | Dense index into `cell_adjacency_edges` |
| `cell_a_id` | int | `min(cell, neighbor)` |
| `cell_b_id` | int | `max(cell, neighbor)` |
| `edge_class` | str | One of the six classes below |
| `great_circle_distance_km` | float | Central angle between centers × `radius_km` |
| `midpoint_lat_deg` / `midpoint_lon_deg` | float | Normalized midpoint of the two center vectors |
| `bearing_a_to_b_deg` / `bearing_b_to_a_deg` | float | Compass bearings in each cell's local east/north basis, in `[0, 360)` |
| `elevation_delta_m` | float | `elevation_m(b) − elevation_m(a)` |
| `plate_boundary` | bool | `plate_id` differs |
| `land_water_transition` | bool | `is_water` differs |
| `biome_transition` | bool | `biome` string differs |
| `boundary_segment_start_lat_deg` / `_lon_deg` | float | Shared-boundary segment start |
| `boundary_segment_end_lat_deg` / `_lon_deg` | float | Shared-boundary segment end |
| `boundary_segment_length_km` | float | Central angle of that segment × `radius_km` |
| `cell_a_boundary_segment_length_km` | float | Length of A's own segment, or the shared length when A has none |
| `cell_b_boundary_segment_length_km` | float | Length of B's own segment, or the shared length when B has none |
| `boundary_segment_mismatch_km` | float | Half the summed endpoint separation between A's and B's segments |
| `boundary_segment_quality` | float | `clamp(1 − 0.65·mismatch_ratio − 0.35·length_ratio_error, 0, 1)` |

`edge_class` is assigned by first match in this fixed priority order (`src/magic_geo/cell_geometry.py:91-102`):

| Priority | `edge_class` | Condition |
| --- | --- | --- |
| 1 | `land_water_transition` | `is_water` differs |
| 2 | `tectonic_plate_edge` | `plate_id` differs |
| 3 | `water_body_transition` | `water_body_type` differs |
| 4 | `biome_transition` | `biome` differs |
| 5 | `open_water_adjacency` | both water |
| 6 | `interior_land_adjacency` | otherwise |

The three boolean flags are computed **independently** of `edge_class`, so a plate boundary that also separates land from water is classed `land_water_transition` while still setting `plate_boundary = true`. Do not derive one from the other.

### Segment reconstruction, and where it silently degrades

`cell_geometry.py` builds a per-directed-pair segment map only under a strict condition (`src/magic_geo/cell_geometry.py:333-343`):

```python
if (
    use_native_control_volume
    and cell_id >= 0
    and len(set(int(value) for value in native_edge_neighbor_ids))
    == len(native_edge_neighbor_ids)
):
```

`fibonacci_sphere` satisfies the uniqueness requirement, so its shared boundary segments are the true control-volume edges. `geodesic_icosahedron` never satisfies it — every neighbor appears twice — and the `elif` fallback at line 344 requires `len(ring_xyz) == len(neighbor_records)`, which is also false for the doubled geodesic ring. **The segment map is therefore completely empty for geodesic worlds**, and every edge falls back to `_fallback_boundary_segment` (`src/magic_geo/cell_geometry.py:207-217`): a synthetic segment centered on the great-circle midpoint with half-length `clamp(0.18 × central_angle, 0.0001, 0.08)` radians.

The consequence is measurable and easy to misread. On a generated 162-cell geodesic world, every one of the 480 edges has `boundary_segment_length_km / great_circle_distance_km = 0.36` to 9 significant figures, `boundary_segment_mismatch_km = 0.0`, and `boundary_segment_quality = 1.0`. The quality of `1.0` is **vacuous**: both sides fell back to the same synthetic segment, so there is nothing to disagree. The same vacuity applies to the 104 stencil-only edges of the n = 128 Fibonacci run.

Reinforcing this, `summary["cell_boundary_segment_geometry"]` is the hard-coded literal `"approx_neighbor_sector_v0"` at `src/magic_geo/cell_geometry.py:524` — it never advertises native segments even when they were used. For exact shared-edge geometry, read `control_volume_vertices_3d` and `control_volume_edge_neighbor_ids` directly, or use the native plate-boundary segment ledger.

### Downstream consumers of the control-volume edges

| Consumer | File | Uses |
| --- | --- | --- |
| Directed cross-plate boundary segments | `cpp/src/engine/plate_boundary_segments.cpp` | Exact reciprocal edge identity and geometry; caps at `MAX_CONTROL_VOLUME_SEGMENTS_PER_CELL = 64` and `MAX_RECIPROCAL_MESH_SEGMENTS_PER_CELL = 8` (`plate_boundary_segments.cpp:7-8`) |
| Forward spherical control-volume overlap crust transport | `cpp/src/engine/crust_transport.cpp` | Rotated source polygons intersected against destination control volumes; `build_forward_overlap_crust_transport_plan` at `:1490` |
| Coverage geometry replay | `src/magic_geo/crust_coverage_geometry_replay.py:659` | Independent Python re-derivation of overlap areas |
| Plate-boundary edge validation | `src/magic_geo/plate_boundary_edge_validation.py:520-545` | Vertex/neighbor unit-length and integer checks |

Those two caps are explicitly **fail-closed numerical memory-safety limits, not physical claims**.

---

## High-precision per-cell vectors

Mesh geometry is serialized at a precision floor well above the configured display precision, because it is replay input rather than presentation. From `cells_json` (`cpp/src/engine/entity_serialization.cpp:110-132`):

```cpp
const int geometry_precision = std::max(std::numeric_limits<double>::max_digits10, precision);
```

| Serialized field | Emitted from | Precision argument | Effective decimal places |
| --- | --- | --- | --- |
| `position_3d` | `cell.p` | `geometry_precision` | `max(17, float_precision)` |
| `normal_3d` | `cell.p` (**identical value**, an alias) | `geometry_precision` | `max(17, float_precision)` |
| `lat_deg` | `cell.lat * DEG` | `geometry_precision` | `max(17, float_precision)` |
| `lon_deg` | `cell.lon * DEG` | `geometry_precision` | `max(17, float_precision)` |
| `area_km2` | `cell.area_km2` | `geometry_precision` | `max(17, float_precision)` |
| `control_volume_vertices_3d` | `cell.control_volume_vertices` | `geometry_precision` | `max(17, float_precision)` |
| `control_volume_edge_neighbor_ids` | `cell.control_volume_edge_neighbor_ids` | — | integers, exact |
| `neighbors` | `cell.neighbors` | — | integers, exact |

`DEG = 180.0 / PI` (`cpp/src/engine/constants.hpp:6`), so `lat_deg` and `lon_deg` are degrees while the in-memory `Cell::lat` / `Cell::lon` are radians.

**Read the precision semantics carefully.** `num(value, precision)` uses `std::fixed` with `precision` **decimal places**, not significant digits (`cpp/src/engine/core.cpp:168-176`). For unit-vector components and areas this is far more than sufficient — the measured `maximum_unit_norm_error` over a generated world is `2.22e-16`, i.e. one ULP — but 17 fixed decimals is *not* the same guarantee as the `roundtrip_num` exact-binary64 path used for `crust_age_ma`, `elevation_m`, and `water_depth_m` (`cpp/src/engine/numeric_serialization.cpp`). A component whose magnitude is far below `1e-17` would be flattened. The replay tolerances in `control_volume_geometry.py` (`5.0e-9` unit norm, `2.0e-9` relative area) are set to accommodate exactly this quantization, not to certify bit-exactness.

`num()` also throws `attempted to serialize a non-finite simulation value` on any NaN or infinity, so no non-finite geometry can appear in the document.

---

## The spherical spatial index

`enrich_world_with_spherical_index(world)` (`src/magic_geo/spherical_index.py:102-235`) is enricher #2 in both `generate_world` and `generate_geo_world` (`src/magic_geo/api.py:200-201`, `:308-309`). It runs before `cell_geometry` and is pure indexing — it adds **no physics**, only spatial keys, and returns `world` unchanged when `cells` is absent or empty.

It publishes the top-level key `spherical_spatial_index` with `index = "healpix_s2_compat_v0"` and this self-describing `description`:

> "Dependency-free HEALPix-inspired equal-area latitude/longitude pixels and S2-inspired cube-face tokens over generated cell centroids; metadata only, not a native HEALPix or S2 mesh backend."

### What it accelerates

Both families are **bucketings of the existing cell set by centroid**, not alternative meshes. They accelerate:

| Query | Mechanism |
| --- | --- |
| Latitude-band / ring selection | `healpix_like_ring` is a monotone function of `sin(lat)`; a band is a contiguous ring range |
| Longitude-sector selection | `healpix_like_lon_bin` partitions `[−180, 180)` into `4·nside` equal bins |
| Polar vs equatorial regime split | `zone` ∈ `north_polar` / `equatorial` / `south_polar` |
| Coarse region-of-interest lookup | `s2_like_cell_id` / `s2_like_token` give a cube-face quadtree address |
| Prefix-based hierarchical filtering | `s2_like_token` is `F<face>-<base-4 digits>`; a truncated digit string is a coarser tile |
| Cross-system joins | `healpix_like_pixel_code` and `s2_like_token` are stable strings for external tooling |
| Occupancy statistics | Per-bucket `cell_count`, `area_km2`, `centroid_lat_deg`, `centroid_lon_deg`, `representative_cell_id` |

There is no ordering guarantee stronger than the id arithmetic below — in particular the S2-like digit path is a **Morton (Z-order) interleave**, `digit = 2·(y bit) + (x bit)` (`src/magic_geo/spherical_index.py:87-89`), not a Hilbert curve, so it does not carry Hilbert's locality property.

### HEALPix-like resolution and pixel id

| Quantity | Expression | Source |
| --- | --- | --- |
| `nside` | `_power_of_two_near(sqrt(max(1, cells/12)), 64)` — a power of two, capped at 64 | `:46-54` |
| `ring_count` | `3 · nside` | `:108` |
| `lon_bin_count` | `4 · nside` | `:109` |
| `pixel_count` | `ring_count · lon_bin_count` = `12 · nside²` | `:110` |
| `ring` | `clamp(int((1 − sin(lat)) · 0.5 · ring_count), 0, ring_count−1)` | `:67-68` |
| `lon_bin` | `clamp(int(((lon + 180) mod 360) / 360 · lon_bin_count), 0, lon_bin_count−1)` | `:69-70` |
| `pixel_id` | `ring · lon_bin_count + lon_bin` | `:71` |
| `pixel_code` | `f"H{nside}R{ring}C{lon_bin}"` | `:78` |
| `zone` | `north_polar` if `ring < nside`; `south_polar` if `ring ≥ 2·nside`; else `equatorial` | `:72-77` |

`_power_of_two_near` uses `int(round(log2(value)))`, which is Python's banker's rounding at an exact half — a boundary case, not a documented policy.

### S2-like resolution and cell id

| Quantity | Expression | Source |
| --- | --- | --- |
| `s2_like_level` | `clamp(round(log2(sqrt(max(1, cells/6)))), 0, 12)` | `:57-61` |
| `scale` | `1 << level` | `:82` |
| `s2_like_cell_count` | `6 · scale²` | `:113` |
| `x` | `clamp(int((u + 1) · 0.5 · scale), 0, scale−1)` | `:83` |
| `y` | `clamp(int((v + 1) · 0.5 · scale), 0, scale−1)` | `:84` |
| `cell_id` | `face · scale² + y · scale + x` | `:85` |
| `token` | `f"F{face}"` plus `"-"` and the base-4 Morton digits from bit `level−1` down to 0 (omitted entirely at level 0) | `:86-90` |

The cube-face projection `_cube_face_uv` (`src/magic_geo/spherical_index.py:29-43`) is byte-for-byte the same function as the one in `src/magic_geo/mesh_lod.py:24-38`:

| `face_id` | `face` | Selected when | `u` | `v` |
| --- | --- | --- | --- | --- |
| 0 | `+x` | `\|x\| ≥ \|y\|, \|z\|` and `x ≥ 0` | `y/\|x\|` | `z/\|x\|` |
| 1 | `-x` | `\|x\| ≥ \|y\|, \|z\|` and `x < 0` | `−y/\|x\|` | `z/\|x\|` |
| 2 | `+y` | `\|y\| ≥ \|x\|, \|z\|` and `y ≥ 0` | `−x/\|y\|` | `z/\|y\|` |
| 3 | `-y` | `\|y\| ≥ \|x\|, \|z\|` and `y < 0` | `x/\|y\|` | `z/\|y\|` |
| 4 | `+z` | otherwise and `z ≥ 0` | `y/\|z\|` | `−x/\|z\|` |
| 5 | `-z` | otherwise and `z < 0` | `y/\|z\|` | `x/\|z\|` |

`FACE_NAMES = ("+x", "-x", "+y", "-y", "+z", "-z")` (`src/magic_geo/spherical_index.py:7`).

Because the face projection and the id arithmetic are identical to the LOD module's, `s2_like_cell_id` **numerically equals** `mesh_lod_tile_ids[s2_like_cell_level]` whenever `s2_like_cell_level ≤ mesh_lod.max_level`. Verified on a generated 128-cell world: cell 0 has `s2_like_cell_id = 70` and `mesh_lod_tile_ids = [4, 17, 70, 284]`.

### Per-cell fields added

| Field | Type | Example (128-cell smoke world, cell 0) |
| --- | --- | --- |
| `healpix_like_nside` | int | `4` |
| `healpix_like_ring` | int | `0` |
| `healpix_like_lon_bin` | int | `8` |
| `healpix_like_pixel_id` | int | `8` |
| `healpix_like_pixel_code` | str | `"H4R0C8"` |
| `s2_like_face` | str | `"+z"` |
| `s2_like_face_id` | int | `4` |
| `s2_like_cell_level` | int | `2` |
| `s2_like_x` | int | `2` |
| `s2_like_y` | int | `1` |
| `s2_like_cell_id` | int | `70` |
| `s2_like_token` | str | `"F4-12"` |

### `spherical_spatial_index` object layout

Keys in emission order (`src/magic_geo/spherical_index.py:204-222`):

| Key | Type | Meaning |
| --- | --- | --- |
| `index` | str | Always `"healpix_s2_compat_v0"` |
| `description` | str | The metadata-only disclaimer quoted above |
| `healpix_like_nside` | int | Resolution parameter |
| `healpix_like_ring_count` | int | `3 · nside` |
| `healpix_like_lon_bin_count` | int | `4 · nside` |
| `healpix_like_pixel_count` | int | `12 · nside²`, the full grid |
| `healpix_like_occupied_pixel_count` | int | Pixels containing at least one cell |
| `healpix_like_pixels` | list | Occupied pixel records, ascending `pixel_id` |
| `s2_like_level` | int | Quadtree level |
| `s2_like_cell_count` | int | `6 · (1<<level)²`, the full grid |
| `s2_like_occupied_cell_count` | int | Occupied tiles |
| `s2_like_face_summaries` | list | Exactly 6 records, one per face, in `FACE_NAMES` order |
| `s2_like_cells` | list | Occupied tile records, ascending `cell_id` |

Occupied HEALPix-like pixel record — 10 fields (`:128-140`, finalized at `:94-99`):

| Field | Type |
| --- | --- |
| `pixel_id`, `ring`, `lon_bin`, `cell_count`, `representative_cell_id` | int |
| `pixel_code`, `zone` | str |
| `area_km2`, `centroid_lat_deg`, `centroid_lon_deg` | float, rounded to 6 decimals |

Occupied S2-like cell record — 12 fields (`:152-166`):

| Field | Type |
| --- | --- |
| `cell_id`, `level`, `face_id`, `x`, `y`, `cell_count`, `representative_cell_id` | int |
| `token`, `face` | str |
| `area_km2`, `centroid_lat_deg`, `centroid_lon_deg` | float, rounded to 6 decimals |

Face summary record — 5 fields (`:194-201`): `face`, `face_id`, `occupied_cell_count`, `cell_count`, `area_km2`.

`representative_cell_id` is simply the **first** cell encountered in `cells` order that landed in that bucket, not a centroid-nearest choice. The `centroid_*` values are the normalized vector sum of member centroids (`_finalize_record`, `:94-99`), i.e. a chord-space mean re-projected to the sphere — not an area-weighted spherical centroid.

---

## The mesh LOD index

`enrich_world_with_mesh_lod(world)` (`src/magic_geo/mesh_lod.py:72-183`) is enricher #1 in both scopes — the first thing that touches a native world. It publishes the top-level key `mesh_lod` with `index = "cube_quadtree_v0"` and the description "Dependency-free spherical cube-face quadtree over generated cell centroids."

Like the spatial index, it returns `world` untouched when `cells` is missing or empty, and it assigns tiles by **cell centroid** only. A tile's `area_km2` is the sum of its members' `area_km2`; it is not the tile's own spherical area.

### Level selection

```python
# src/magic_geo/mesh_lod.py:10-14
def _max_lod_level(cell_count: int) -> int:
    if cell_count <= 0:
        return 0
    nominal = max(1.0, cell_count / 6.0)
    return max(1, min(6, int(math.ceil(math.log(nominal, 4.0)))))
```

`max_level = clamp(ceil(log₄(cells / 6)), 1, 6)`, and levels `0 .. max_level` are all materialized, so `level_count = max_level + 1`.

| Generated cells | `max_level` | Level count | Nominal tiles at finest level `6·4^L` |
| --- | --- | --- | --- |
| 128 | 3 | 4 | 384 |
| 162 | 3 | 4 | 384 |
| 512 | 4 | 5 | 1,536 |
| 1,024 | 4 | 5 | 1,536 |
| 2,048 | 5 | 6 | 6,144 |
| 4,096 | 5 | 6 | 6,144 |
| 8,192 | 6 | 7 | 24,576 |
| 200,000 | 6 | 7 | 24,576 |

The clamp at 6 means high-resolution meshes stop refining: at 200,000 cells the finest level has only 24,576 nominal tiles, so it averages **at least** ~8 cells per occupied tile rather than 1 (`mean_cells_per_tile` divides by *occupied* tiles, which is never more than the nominal count).

### Tile addressing

| Quantity | Expression | Source |
| --- | --- | --- |
| face, `u`, `v` | `_cube_face_uv(x, y, z)` — identical to the spatial index's | `:24-38` |
| `scale` | `1 << level` | `:42` |
| tile `x` | `clamp(int((u + 1) · 0.5 · scale), 0, scale−1)` | `:43` |
| tile `y` | `clamp(int((v + 1) · 0.5 · scale), 0, scale−1)` | `:44` |
| `tile_id` | `face · scale² + y · scale + x` | `:48-50` |
| `tile_code` | `f"L{level}F{face}X{x}Y{y}"` | `:53-54` |
| `parent_tile_id` | `_tile_id(level−1, face, x // 2, y // 2)`; `−1` at level 0 | `:90-91` |

Because the same `(u, v)` is re-binned at every level, a cell's tile path is a strict quadtree ancestry: the level-`L` tile's `(x, y)` is exactly `(x_finest >> (max_level − L), y_finest >> (max_level − L))`.

### Per-cell fields added

| Field | Type | Example (128-cell smoke world, cell 0) |
| --- | --- | --- |
| `mesh_lod_face` | str | `"+z"` |
| `mesh_lod_face_id` | int | `4` |
| `mesh_lod_tile_ids` | list[int] | `[4, 17, 70, 284]` — one entry per level, coarse to fine |
| `mesh_lod_codes` | list[str] | `["L0F4X0Y0", "L1F4X1Y0", "L2F4X2Y1", "L3F4X4Y3"]` |
| `mesh_lod_finest_tile_id` | int | `284` (always `mesh_lod_tile_ids[-1]`) |

### `mesh_lod` object layout

Keys in emission order (`src/magic_geo/mesh_lod.py:166-173`):

| Key | Type | Meaning |
| --- | --- | --- |
| `index` | str | Always `"cube_quadtree_v0"` |
| `description` | str | The dependency-free disclaimer |
| `max_level` | int | Finest level index |
| `root_face_count` | int | Always `6` (`len(FACE_NAMES)`) |
| `level_summaries` | list | Exactly `max_level + 1` records, ascending level |
| `tiles` | list | All occupied tiles at all levels, sorted by `(level, tile_id)` |

Tile record — 14 fields (`:95-111`, finalized at `:136-144`):

| Field | Type | Notes |
| --- | --- | --- |
| `level` | int | 0 = one of six cube faces |
| `tile_id` | int | Unique within a level |
| `tile_code` | str | `L{level}F{face}X{x}Y{y}` |
| `parent_tile_id` | int | `−1` at level 0 |
| `face` | str | From `FACE_NAMES` |
| `face_id` | int | 0–5 |
| `x`, `y` | int | `0 .. 2^level − 1` |
| `cell_count` | int | Members at this level |
| `child_tile_count` | int | Occupied children only, tallied at `:127-131` |
| `representative_cell_id` | int | First member encountered in `cells` order |
| `area_km2` | float | Sum of member `area_km2`, rounded to 6 decimals |
| `centroid_lat_deg`, `centroid_lon_deg` | float | Normalized member vector sum, rounded to 6 decimals |

Level summary record — 7 fields (`:154-163`):

| Field | Meaning |
| --- | --- |
| `level` | Level index |
| `nominal_tile_count` | `6 · 4^level` — the full grid, occupied or not |
| `occupied_tile_count` | Tiles with at least one member |
| `cell_count` | Total members at this level; equals the world cell count at every level |
| `mean_cells_per_tile` | `cell_count / occupied_tile_count`, 6 decimals |
| `max_cells_per_tile` | Largest tile population |
| `mean_tile_area_km2` | Mean summed member area per occupied tile, 6 decimals |

Observed on a 128-cell Fibonacci world: level 0 has all 6 faces occupied with `mean_cells_per_tile = 21.333333` and `max_cells_per_tile = 23`; level 3 has 128 occupied tiles of 384 nominal, `mean_cells_per_tile = 1.0`, `max_cells_per_tile = 1`, `mean_tile_area_km2 = 3984878.686795` — exactly `summary.mean_cell_area_km2`, because each finest tile holds one cell.

---

## The display boundary ring

`enrich_world_with_cell_geometry(world)` (`src/magic_geo/cell_geometry.py:249-534`) is enricher #3 in both scopes. Its per-cell `boundary_ring` is the closed spherical polygon in lat/lon that renderers and debug exporters draw.

### Two ring sources

| Path | Condition (`cell_geometry.py:296-302`) | Ring content |
| --- | --- | --- |
| Native control volume | `control_volume_vertices_3d` is a list of ≥ 3 three-component lists **and** its length equals `len(control_volume_edge_neighbor_ids)` | The native vertices, re-normalized, converted to `[lat_deg, lon_deg]` |
| Approximate neighbor sector | otherwise | A synthetic ring from neighbor bearings and an area-matched radius (`:128-173`) |

Both native backends satisfy the native condition, so in practice every generated world takes the native path. `summary["cell_geometry_index"]` is set to `"native_spherical_control_volume_v1"` only when **every** ring came from the native path, otherwise `"approx_neighbor_bearing_v0"` (`:507-511`); the `magic-geo validate` gate hard-requires the native value (`src/magic_geo/cli/commands/validate.py:6486-6488`).

The approximate fallback is not dead code but it is not exercised by native worlds. Its parameters — `_vertex_angles_from_bearings` (midpoint bearings between angularly sorted neighbors), `_target_radius_rad` (`clamp(min(area-matched circumradius, 0.58 × median neighbor distance, 0.72 × nearest neighbor distance), 0.0001, 0.35)` radians) — apply only to worlds whose cells lack control-volume geometry.

### Per-cell fields added

| Field | Type | Definition |
| --- | --- | --- |
| `boundary_ring` | list of `[lat_deg, lon_deg]` | Ring vertices, each coordinate rounded to **6 decimals** (`:318`) |
| `boundary_vertex_count` | int | `len(boundary_ring)` |
| `cell_boundary_perimeter_km` | float | Σ central angles around the ring × `radius_km` (`:176-182`) |
| `cell_polygon_area_km2` | float | Σ `_triangle_area_steradians(center, vᵢ, vᵢ₊₁)` × `radius_km²` (`:185-195`) |
| `cell_polygon_area_error_fraction` | float | `\|polygon_area − area_km2\| / area_km2` |
| `cell_geometry_quality` | float | `clamp(0.72 · (1 − min(1, area_error)) + 0.28 · compactness, 0, 1)`, where `compactness = clamp(4π·A / max(1, P²), 0, 1)` (`:322-323`) |
| `cell_adjacency_edge_ids` | list[int] | Ids of incident `cell_adjacency_edges` records |
| `cell_edge_count` | int | Length of that list |
| `mean_neighbor_edge_length_km` / `max_neighbor_edge_length_km` | float | Over incident edges |
| `mean_neighbor_boundary_segment_length_km` / `max_...` | float | Over incident edges |
| `mean_neighbor_boundary_segment_mismatch_km` | float | Over incident edges |
| `mean_neighbor_boundary_segment_quality` | float | Over incident edges |
| `tectonic_neighbor_edge_count` | int | Incident edges with `plate_boundary` |
| `land_water_neighbor_edge_count` | int | Incident edges with `land_water_transition` |
| `biome_transition_neighbor_edge_count` | int | Incident edges with `biome_transition` |

`area_km2` is floored at `1.0` before use as the reference denominator (`:293`), so the error fraction is not meaningful for hypothetical sub-1 km² cells.

Observed on a 128-cell Fibonacci world: `cell_geometry_mean_area_error_fraction = 0.0` and `cell_geometry_max_area_error_fraction = 0.0` (native vertices reproduce the native area to well within the 6-decimal rounding), while `cell_geometry_mean_quality = 0.963731` — the shortfall is entirely the compactness term, since a Voronoi polygon is not a disc.

### Display consumers

| Consumer | Location | How the ring is used |
| --- | --- | --- |
| Debug binary mesh asset | `src/magic_geo/debug_export.py:599-671` | Triangle fan from the cell center to consecutive ring vertices; writes `positions.f32`, `cell_ids.u32`, `indices.u32`, `pos_equirect.f32`, `pos_mollweide.f32` plus `mesh.json`. Cells with a ring shorter than 3 are skipped and counted in `cells_without_ring` |
| ParaView `.vtu` stage export | `src/magic_geo/debug_export.py:685-700` | Rings converted back to XYZ per hydrologic-water-budget stage |
| Rerun `.rrd` recording | `src/magic_geo/debug_rerun.py:70-81` | Same fan triangulation, per-vertex colored |
| Per-cell CSV | `src/magic_geo/io/cells_csv.py:20-30` | `boundary_vertex_count`, perimeter, polygon area, error fraction, quality |
| Validation | `src/magic_geo/cli/commands/validate.py:6499-6527` | Requires ≥ 3 points, `boundary_vertex_count` match, `lat ∈ [−90, 90]`, `lon ∈ [−180, 180]` |

Antimeridian wrapping is **not** handled in `boundary_ring` itself — the ring is stored as raw lat/lon. Only the debug export's 2D projections apply `_wrap_lon_near` (`src/magic_geo/debug_export.py:596-597`) when building equirectangular and Mollweide coordinates. Any consumer drawing the ring in a flat projection must handle the seam itself.

---

## Configuration reference for mesh sizing

All three properties live in the `mesh` section of the YAML config (`src/magic_geo/config.py:235-255`). The section model is `MeshConfig`, with `extra="forbid"` and `allow_inf_nan=False`.

| YAML path | Type | Default | Range / enum | Native struct field | Description string (verbatim) | Line |
| --- | --- | --- | --- | --- | --- | --- |
| `mesh.backend` | `Literal["fibonacci_sphere", "geodesic_icosahedron"]` | `"fibonacci_sphere"` | exactly those two | `mesh_backend` (`c_int`, via `MESH_BACKEND_IDS`) | "Spherical mesh construction algorithm used for world control volumes." | `config.py:240` |
| `mesh.cell_count` | `int` | `4096` | `ge=128`, `le=200_000` | `cell_count` (`c_int`) | "Requested number of spherical cells; controls spatial resolution and cost." | `config.py:244` |
| `mesh.neighbor_count` | `int` | `7` | `ge=4`, `le=16` | `neighbor_count` (`c_int`) | "Target process-stencil neighbour count for the Fibonacci mesh backend." | `config.py:250` |

Cross-section constraints and native re-validation:

| Constraint | Where | Message |
| --- | --- | --- |
| `tectonics.plate_count < mesh.cell_count` | `src/magic_geo/config.py:500` (`validate_plate_density`) | `plate_count must be smaller than mesh.cell_count` |
| `128 ≤ cell_count ≤ 200000` | `cpp/src/engine/core.cpp:287-289` | `cell_count must be between 128 and 200000` |
| backend id ∈ {0, 1} | `cpp/src/engine/core.cpp:290-293` | `unknown mesh backend` |
| `2 ≤ plate_count ≤ 256` and `plate_count < cell_count` | `cpp/src/engine/core.cpp:295-301` | `plate_count must be between 2 and 256 and smaller than cell_count` |
| `4 ≤ neighbor_count ≤ 16` | `cpp/src/engine/core.cpp:302-304` | `neighbor_count must be between 4 and 16` |
| `plate_count < generated cell count` | `cpp/src/engine/pipeline.cpp:13-15` | `plate_count must be smaller than generated mesh cell count` |

The Python and native ranges are duplicated literals, kept in agreement manually. The pipeline guard is the one that matters for `geodesic_icosahedron`, because it tests the *generated* count.

Profiles that touch mesh sizing (`src/magic_geo/config.py:513`):

| Profile | `mesh.cell_count` | `mesh.backend` | `mesh.neighbor_count` |
| --- | --- | --- | --- |
| `default` | 4096 | `fibonacci_sphere` | 7 |
| `earthlike` | 4096 | `fibonacci_sphere` | 7 |
| `smoke` | **128** | `fibonacci_sphere` | 7 |

No built-in profile selects `geodesic_icosahedron`; it must be set explicitly.

CLI override: `magic-geo generate --cells N` rewrites `mesh.cell_count` before validation, with `min=128` at the Typer layer and the pydantic upper bound still applying (`src/magic_geo/cli/commands/generate.py:27-29, 47-51`). Note the progress line prints the *requested* `world_config.mesh.cell_count` while the final line prints the *generated* `summary.cell_count` — for `geodesic_icosahedron` these differ.

### Resolution and cost

Mean cell area is `4·π·radius_km² / cell_count` by construction. At the Earth default `radius_km = 6371.0`:

| `cell_count` | Mean cell area (km²) | Approximate nominal cell "diameter" (km) |
| --- | --- | --- |
| 128 | 3,984,879 | ≈ 2,250 |
| 4,096 | 124,527 | ≈ 400 |
| 20,000 | 25,503 | ≈ 180 |
| 200,000 | 2,550 | ≈ 57 |

The 128 and 4,096 mean areas follow from `510,064,471.909789 / n`; the 128-cell figure `3,984,878.686795` was confirmed against a generated world's `summary.mean_cell_area_km2`. The diameter column is a rough `2·sqrt(area/π)` reading aid, not a source-derived quantity.

Observed area uniformity, from generated worlds at `radius_km = 6371`:

| Backend | Cells | `min_cell_area_km2` | `max_cell_area_km2` | `cell_area_coefficient_of_variation` |
| --- | --- | --- | --- | --- |
| `fibonacci_sphere` | 128 | 3,750,104.70551 | 4,197,173.831461 | 0.015881 |
| `geodesic_icosahedron` | 162 | 2,081,306.891337 | 3,439,246.495987 | 0.118261 |

In the 162-cell geodesic world all twelve degree-5 cells share the identical area `2081306.8913368087` km² (icosahedral symmetry), which is also the global minimum; the 150 degree-6 cells span `2957937.1214663144` – `3439246.4959872887` km². The Fibonacci mesh has no such bimodality, which is why its coefficient of variation is an order of magnitude smaller here.

The Fibonacci lattice is markedly more area-uniform at these sizes; the geodesic dual's spread reflects the pentagon/hexagon mix and the projected-triangle distortion near the icosahedron corners. `cell_area_coefficient_of_variation` is computed as `sqrt(max(0, E[A²] − E[A]²)) / E[A]` at `cpp/src/engine/summary.cpp:1310-1318`.

---

## Summary keys produced by the mesh and geometry layers

### Native (`cpp/src/engine/summary.cpp`)

| Key | Type | Precision | Line |
| --- | --- | --- | --- |
| `mesh_backend` | str | — | `:1320` |
| `cell_area_model` | str | — | `:1321` |
| `cell_count` | int | — | `:1322` (from `cells.size()`, the **generated** count) |
| `surface_area_km2` | float | `max(6, float_precision)` | `:1360` |
| `mean_cell_area_km2` | float | `max(6, float_precision)` | `:1361` |
| `min_cell_area_km2` | float | `max(6, float_precision)` | `:1362-1363` (emits `0.0` for an empty mesh) |
| `max_cell_area_km2` | float | `max(6, float_precision)` | `:1364` |
| `cell_area_coefficient_of_variation` | float | `max(6, float_precision)` | `:1365-1366` |

### Mesh LOD (`src/magic_geo/mesh_lod.py:175-181`)

`mesh_lod_index`, `mesh_lod_max_level`, `mesh_lod_level_count`, `mesh_lod_tile_count`, `mesh_lod_finest_tile_count`, `mesh_lod_mean_finest_tile_cell_count`.

### Spherical index (`src/magic_geo/spherical_index.py:224-233`)

`spherical_spatial_index`, `healpix_like_nside`, `healpix_like_pixel_count`, `healpix_like_occupied_pixel_count`, `healpix_like_mean_cells_per_occupied_pixel`, `s2_like_cell_level`, `s2_like_cell_count`, `s2_like_occupied_cell_count`, `s2_like_mean_cells_per_occupied_cell`.

### Cell geometry (`src/magic_geo/cell_geometry.py:507-533`)

`cell_geometry_index`, `cell_geometry_ring_count`, `cell_geometry_total_area_km2`, `cell_geometry_reference_area_km2`, `cell_geometry_mean_vertex_count`, `cell_geometry_mean_perimeter_km`, `cell_geometry_mean_area_error_fraction`, `cell_geometry_max_area_error_fraction`, `cell_geometry_mean_quality`, `cell_adjacency_edge_count`, `mean_cell_adjacency_edge_length_km`, `max_cell_adjacency_edge_length_km`, `cell_boundary_segment_geometry`, `cell_boundary_segment_count`, `mean_cell_boundary_segment_length_km`, `max_cell_boundary_segment_length_km`, `mean_cell_boundary_segment_mismatch_km`, `mean_cell_boundary_segment_quality`, `tectonic_adjacency_edge_count`, `land_water_adjacency_edge_count`, `biome_transition_adjacency_edge_count`, `cell_adjacency_edge_class_counts`.

The Markdown summary export mirrors these in two different places. `mesh_backend`, `cell_area_model`, and `cell_count` are in the leading scalar field list at `src/magic_geo/io/summary_markdown.py:22-24`; the area, LOD, spherical-index, cell-geometry, and adjacency-edge scalars are at `:44-84`. `cell_adjacency_edge_class_counts` is **not** in the scalar list — it is a dict-valued key and is rendered by the counts-section loop that begins at `:1268`, where it is entry `:1275`.

---

## Validation coverage

### `magic-geo validate-geo` — `mesh` domain

Seven checks in `src/magic_geo/geo_validation.py`:

| Check `name` | Assertion | Tolerance | Line |
| --- | --- | --- | --- |
| `unique_cell_ids` | Every cell is an object with a unique non-bool integer `id` | exact | `:963` |
| `spherical_surface_area_closure` | All `area_km2 > 0` and `\|Σ − 4πR²\| / max(1, 4πR²) ≤ 2.0e-6` | `2.0e-6` relative | `:1059` |
| `unit_sphere_positions` | `\|‖position_3d‖ − 1\| ≤ 1.0e-6` | `1.0e-6` | `:1102` |
| `coordinate_position_consistency` | `lat_deg`/`lon_deg` in range, reconstruct `position_3d` to `≤ 2.0e-6` per component, and all positions distinct at 12-decimal rounding | `2.0e-6` | `:1112` |
| `adjacency_graph_integrity` | `neighbors` valid, self-loop free, **symmetric**, and the whole mesh one connected component | exact | `:1152` |
| `native_cell_area_model_replay` | `inspect_control_volume_geometry(world)["passed"]` | see the replay tolerance table | `:1181` |
| `configured_radius_distance_scaling` | Every `cell_adjacency_edges` record exists exactly once, matches the `neighbors` edge set, and `great_circle_distance_km` reproduces `central_angle × radius_km` | `max(0.001 km, 1.0e-4 relative)` | `:1255` |

The `2.0e-6` area tolerance here is far looser than the native `2.0e-10` gate and the replay's `2.0e-10` / `2.0e-9` pair; it is the outermost of three nested checks, not the tightest.

### `magic-geo validate-geo-suite` — `geometry_indices` domain

`_validate_geometry_indices` (`src/magic_geo/geo_validation_subsystems.py:303-450`) emits two checks:

| Check `name` | Assertion |
| --- | --- |
| `mesh_lod_membership_and_summaries` | Every cell has `max_level + 1` tile ids and matching codes; `mesh_lod_finest_tile_id == tile_ids[-1]`; every referenced tile exists; every tile's `cell_count` equals its member tally exactly and its `area_km2` matches the member area sum under `_close`; every level's `occupied_tile_count` and `cell_count` match; `summary` mirrors `mesh_lod_index`, `mesh_lod_max_level`, `mesh_lod_level_count`, `mesh_lod_tile_count` |
| `spherical_index_membership_and_summaries` | No duplicate occupied bucket ids; every cell's `healpix_like_pixel_id` and `s2_like_cell_id` resolve to an existing record; per-cell `healpix_like_nside` and `s2_like_cell_level` mirror the index-level values; every bucket's `cell_count` matches exactly and its `area_km2` under `_close`; `summary` mirrors `spherical_spatial_index`, `healpix_like_occupied_pixel_count`, `s2_like_occupied_cell_count`, `s2_like_cell_level` |

Both aggregate comparisons go through `_close` (`src/magic_geo/geo_validation_subsystems.py:84-89`), which is `math.isclose(rel_tol=5.0e-6, abs_tol=1.0e-4)` — a tolerance, not bit equality. Integer counts are compared exactly.

The `spherical_mesh` layer contract (`src/magic_geo/geo_layer_contracts.py:40-55`) requires `cells` (non-empty), `cell_area_model` (non-empty string), `mesh_lod` (dict), `spherical_spatial_index` (dict), and `cell_adjacency_edges` (list); its `validator_domains` are `("mesh", "geometry_indices", "natural_graphs")`.

### `magic-geo validate` — full world gate

`src/magic_geo/cli/commands/validate.py` additionally requires `mesh_backend ∈ {fibonacci_sphere, geodesic_icosahedron}` and matching `summary.mesh_backend` (`:123-129`), `summary.cell_count == len(cells)` (`:139-140`), `summary.cell_geometry_index == "native_spherical_control_volume_v1"` (`:6486-6487`), a full re-derivation of all nine `cell_geometry_*` summary aggregates from the cells (`:6539-6559`), and the presence of all thirteen `cell_adjacency_edges` summary keys (`:6562-6577`).

### Native C++ tests

The executable `magic_geo_native_api_test` (`cpp/tests/native_api_test.cpp`) is registered as **two** CTest tests from the same binary (`CMakeLists.txt:469-473`): `magic_geo_native_api`, and `magic_geo_fibonacci_knn_reference`, which sets `ENVIRONMENT "MAGIC_GEO_VALIDATE_FIBONACCI_KNN=1"` so the run re-executes with the brute-force *k*-NN comparison enabled.

### Python tests

| Test | File | Covers |
| --- | --- | --- |
| `SmokeCoreMeshTests.test_mesh_lod` | `tests/test_smoke_core_mesh.py:179` | `mesh_lod` tile records, ancestry, and level summaries |
| `SmokeCoreMeshTests.test_cell_adjacency_edges` | `tests/test_smoke_core_mesh.py:328` | `cell_adjacency_edges` record shape and summary aggregates |
| `SmokeCoreMeshTests.test_geodesic_mesh_backend_smoke` | `tests/test_smoke_core_mesh.py:806` | The geodesic backend end to end at `cell_count = 162` (the fixed point where request and generated size coincide), asserting `cell_area_model`, `cell_count == 162`, closure of Σ`area_km2` to `4πR²` within 1 km², and `cell_area_coefficient_of_variation > 0.1` |
| `test_native_control_volumes_close_and_share_exact_reciprocal_edges` | `tests/test_geo_validation.py:142` | The replay's closure and reciprocal-endpoint metrics on a generated world |
| `test_control_volume_replay_rejects_edge_and_area_corruption` | `tests/test_geo_validation.py:157` | That the replay actually fails on mutated vertices/areas |

Note what these do **not** cover: there is no test that generates the same configuration under both backends and compares any physical result. The geodesic path has a single smoke test at one size.

---

## Worked examples

### Generate and inspect a small Fibonacci world

```bash
magic-geo generate --config magic-geo.yaml --cells 128 --geo-only --output runs/smoke.json
magic-geo validate --world runs/smoke.json
magic-geo validate-geo --world runs/smoke.json --profile generic
```

### Switch backends from Python

```python
from magic_geo.api import generate_geo_world
from magic_geo.config import create_config

config = create_config("smoke", {"mesh.backend": "geodesic_icosahedron"})
world = generate_geo_world(config)

print(world["mesh_backend"])                 # geodesic_icosahedron
print(world["cell_area_model"])              # spherical_barycentric_control_volume_v2
print(config.mesh.cell_count)                # 128  (requested)
print(world["summary"]["cell_count"])        # 162  (generated: 10 * 4**2 + 2)
```

### Replay the control-volume geometry independently

```python
from magic_geo.control_volume_geometry import inspect_control_volume_geometry
from magic_geo.serialization import read_world

world = read_world("runs/smoke.json")
report = inspect_control_volume_geometry(world)
print(report["passed"], report["failures"])
for key, value in report["metrics"].items():
    print(f"{key}: {value}")
```

### Compare the two neighbor relations for yourself

```python
cells = world["cells"]

control_volume_pairs = {
    (min(int(cell["id"]), int(nb)), max(int(cell["id"]), int(nb)))
    for cell in cells
    for nb in cell["control_volume_edge_neighbor_ids"]
}
stencil_pairs = {
    (min(int(cell["id"]), int(nb)), max(int(cell["id"]), int(nb)))
    for cell in cells
    for nb in cell["neighbors"]
}

print(len(control_volume_pairs), len(stencil_pairs))
print(len(control_volume_pairs - stencil_pairs), len(stencil_pairs - control_volume_pairs))
```

On the 128-cell Fibonacci world this prints `378 482` then `0 104`.

### Bucket cells by spatial index

```python
from collections import defaultdict

by_pixel = defaultdict(list)
for cell in world["cells"]:
    by_pixel[cell["healpix_like_pixel_code"]].append(int(cell["id"]))

index = world["spherical_spatial_index"]
print(index["healpix_like_nside"], index["healpix_like_pixel_count"],
      index["healpix_like_occupied_pixel_count"])

# Coarsen an S2-like token by truncating its base-4 digit path.
face, _, digits = world["cells"][0]["s2_like_token"].partition("-")
print(face, digits, face + "-" + digits[:1])   # e.g. F4 12 F4-1
```

### Walk the LOD ancestry of a cell

```python
lod = world["mesh_lod"]
tiles = {(int(t["level"]), int(t["tile_id"])): t for t in lod["tiles"]}

cell = world["cells"][0]
for level, tile_id in enumerate(cell["mesh_lod_tile_ids"]):
    tile = tiles[(level, tile_id)]
    print(level, tile["tile_code"], tile["cell_count"], tile["child_tile_count"],
          tile["parent_tile_id"])
```

---

## Limitations and unresolved claims

**The two backends do not produce comparable meshes.** `fibonacci_sphere` yields exactly `cell_count` cells with a true spherical Voronoi partition and low area variance; `geodesic_icosahedron` yields `10f² + 2` cells with a barycentric dual and roughly 7× the area coefficient of variation at comparable sizes (0.118 vs 0.016 in the runs above). Results generated with different backends are not directly comparable, and no cross-backend parity harness for the mesh exists in the tree.

**`mesh.cell_count` is a request, not a promise, for the geodesic backend.** Anything that reasons about resolution or cost must read the generated `summary.cell_count`, not the configured value. The CLI's own progress line prints the requested value.

**`mesh.neighbor_count` only affects `fibonacci_sphere`.** `cpp/src/engine/mesh.cpp:790` is the only place it changes an output; its other two native occurrences are plumbing (`cpp/src/c_api.cpp:31`) and range validation (`cpp/src/engine/core.cpp:302-303`). Setting it under `geodesic_icosahedron` changes nothing; the config still validates it in `[4, 16]`, which can read as false control.

**Nearest-site certification of stored vertices is not replayed above 512 cells.** `src/magic_geo/control_volume_geometry.py:210` gates the `O(n²)` global nearest-site scan at `n ≤ 512`. Production meshes are checked for bisector membership, reciprocity, Euler topology, and closure, but the global Voronoi-ownership property of every stored vertex is verified only inside the native builder, not independently.

**The geodesic control volume carries no Voronoi guarantee at all**, by construction. Its edges are not perpendicular bisectors and its vertices are not equidistant from three sites, so `maximum_voronoi_bisector_error` and `maximum_nearest_site_violation` are reported as `0.0` for that backend simply because the checks do not run.

**`cell_adjacency_edges` boundary-segment geometry is approximate, and its quality metric can be vacuous.** `summary["cell_boundary_segment_geometry"]` is the hard-coded literal `"approx_neighbor_sector_v0"` regardless of what actually happened. For `geodesic_icosahedron` **every** edge uses the synthetic fallback (`0.36 × great_circle_distance_km`, mismatch `0.0`, quality `1.0`) because the segment map is never populated for duplicated edge-neighbor ids. For `fibonacci_sphere`, the subset of stencil edges that are not Voronoi edges — 104 of 482 in the n = 128 run — takes the same fallback. A `boundary_segment_quality` of `1.0` therefore means "both sides agreed", which is trivially true when both sides are the same synthetic construct. It is not evidence of geometric accuracy.

**Stencil ⊇ Voronoi is an observation, not an invariant.** No source expression guarantees that every Voronoi neighbor appears among a cell's `k` nearest sites. The equality held at n = 128, k = 7; it is unverified in general, particularly at small `neighbor_count`.

**The spatial index and the LOD index are metadata, not meshes.** The module's own description says so: "metadata only, not a native HEALPix or S2 mesh backend." Neither the HEALPix-like pixels nor the S2-like cells are equal-area in the way real HEALPix pixels are; they are a `sin(lat)`-ring × longitude-bin product and a gnomonic cube-face quadtree respectively, and cells are assigned by centroid only. A tile's `area_km2` is the sum of member cell areas, never the tile's own spherical area. Do not feed these ids to a real HEALPix or S2 library.

**The S2-like digit path is Morton, not Hilbert.** `digit = 2·(y bit) + (x bit)` at `src/magic_geo/spherical_index.py:87-89`. Truncating the token gives a valid coarser tile, but the ordering does not have Hilbert-curve locality.

**Bucket centroids are chord-space means.** `_finalize_record` and `_centroid_from_xyz` normalize the vector sum of member centroids; that is not an area-weighted spherical centroid and will be biased for large or elongated buckets. `representative_cell_id` is whichever member appeared first in `cells` order, with no geometric meaning.

**Geodesic vertex deduplication is a fixed quantization.** `add_geodesic_vertex` keys on `llround(component × 1e9)` (`cpp/src/engine/mesh.cpp:853-857`). This is a rounding rule, not a tolerance test; two genuinely distinct points inside the same 1e-9 lattice cell would merge. No such case arises for the frequencies reachable from the validated `cell_count` range, but the property is a quantization artifact and is stated as one.

**Geometry precision is 17 fixed decimal places, not exact binary64 round-trip.** `num()` uses `std::fixed` (`cpp/src/engine/core.cpp:168-176`), unlike the `roundtrip_num` path used for the replay-critical crust and elevation fields. The measured worst unit-norm error over a generated world is one ULP, but "exact round-trip" is not the contract for `position_3d`, `control_volume_vertices_3d`, `lat_deg`, `lon_deg`, or `area_km2`.

**`boundary_ring` is rounded to 6 decimals** (`src/magic_geo/cell_geometry.py:318`) — roughly 0.11 m at the equator on an Earth-radius planet. It is a display product. Never use it as replay geometry; use `control_volume_vertices_3d`.

**Antimeridian handling is a renderer's problem.** `boundary_ring` stores raw lat/lon with no seam handling; only the debug export's equirectangular and Mollweide buffers apply `_wrap_lon_near`.

**The per-cell segment caps are numerical safety limits, not physics.** `MAX_CONTROL_VOLUME_SEGMENTS_PER_CELL = 64` and `MAX_RECIPROCAL_MESH_SEGMENTS_PER_CELL = 8` (`cpp/src/engine/plate_boundary_segments.cpp:7-8`) exist to bound memory and fail closed, and carry no claim about physical plate geometry.

**Automatic compute-backend selection keys on the generated mesh size**, not the requested one (`cpp/src/opencl_compute.cpp:952`). A `geodesic_icosahedron` request near a threshold can therefore select a different backend than the same `cell_count` under `fibonacci_sphere`. Accelerator parity with the CPU path is separately unresolved and is covered on the compute-backends page; nothing on this page should be read as a parity claim.

**Neither the mesh construction nor the indices carry any time semantics.** The mesh is `temporal_class = "static_simulation_domain"`. Nothing here calibrates physical time, process rates, or spatial scale against a real planet; `radius_km` is a configured boundary condition, and all "km" figures are that configuration propagated through exact spherical geometry.

---

## See also

- [Architecture](../04-architecture.md) — where `build_mesh` sits in the full stage ordering
- [Native Engine (C++ Core)](../08-native-engine.md) — translation units, invariants, and the C ABI
- [Configuration Reference](../05-configuration-reference.md) — every config property, including the full `mesh` section
- [World Document Schema](../10-world-schema.md) — the complete per-cell field list and top-level key order
- [Serialization and World Formats](../11-serialization.md) — precision contracts and the `.mgeo` container
- [Validation](../12-validation.md) — the `magic-geo validate` full-world gate
- [Geo Validation Suite](../13-geo-validation-suite.md) — the `mesh` and `geometry_indices` check domains
- [Compute Backends (CPU, OpenCL, CUDA)](../09-compute-backends.md) — generated-mesh-size eligibility thresholds
- [Debug Exports and Visualization](../16-debug-and-visualization.md) — the boundary-ring mesh asset and Rerun recording
- [Rendering and Map Output](../17-rendering.md) — projecting cells and rings to raster maps
- [Tectonics and Plates](tectonics-and-plates.md) — the first consumer of the mesh
- [Plate Boundary Segment Ledger](plate-boundary-ledger.md) — exact reciprocal control-volume segments
- [Crust Transport and Forward Overlap](crust-transport-and-overlap.md) — spherical overlap against control-volume polygons
- [Glossary](../21-glossary.md) — control volume, process stencil, edge neighbor, LOD tile
