# Rendering and Map Output

[Wiki home](./README.md) > Rendering and Map Output

magic-geo ships two dependency-free world renderers — `render` (SVG) and `render-raster` (binary PPM) — plus a third, separate image path that renders a *debug cache* layer to PNG (`export-debug-map`). All three are symbolic diagnostic renderers, not cartographic products: the world renderers draw each mesh cell as a projected **centroid disc**, never as its `boundary_ring` polygon, and none of them writes a georeferenced raster. This page enumerates every option, projection, palette entry, styling rule, output-file structure, and colour convention actually present in the source, plus a recipe gallery. It also states plainly where the brief's expectations do not match the code: there is **no GeoTIFF export** anywhere in this repository, and no legend is emitted by `render` or `render-raster`.

## On this page

- [Two rendering pipelines](#two-rendering-pipelines)
- [The `render` command](#the-render-command)
- [The `render-raster` command](#the-render-raster-command)
- [Projections](#projections)
- [How a cell gets its colour](#how-a-cell-gets-its-colour)
- [Contour rendering](#contour-rendering)
- [Labelling and point symbols](#labelling-and-point-symbols)
- [Cell decimation and the max-cells control](#cell-decimation-and-the-max-cells-control)
- [SVG output structure and post-processing](#svg-output-structure-and-post-processing)
- [PPM raster format](#ppm-raster-format)
- [Diagnostic PNG output from the debug cache](#diagnostic-png-output-from-the-debug-cache)
- [Colour and legend conventions](#colour-and-legend-conventions)
- [GeoTIFF support](#geotiff-support)
- [Python API](#python-api)
- [Recipe gallery](#recipe-gallery)
- [Exit codes and failure modes](#exit-codes-and-failure-modes)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Two rendering pipelines

Two pipelines, three commands: the two world renderers share one duplicated code lineage, and the debug-cache exporter is a wholly separate one. All three read different inputs.

| Path | Command | Reads | Writes | Implementation | Third-party deps |
|---|---|---|---|---|---|
| Vector world map | `magic-geo render` | a world `.json` / `.mgeo` | SVG 1.1 text | `src/magic_geo/io/svg_map.py:12` `write_svg_map` | none (stdlib `math`, `html`) |
| Raster world map | `magic-geo render-raster` | a world `.json` / `.mgeo` | binary PPM (`P6`) | `src/magic_geo/io/raster_map.py:10` `write_raster_map` | none (stdlib `math`) |
| Diagnostic layer image | `magic-geo export-debug-map` | a **debug cache** directory | 8-bit RGB PNG + Markdown prompt | `src/magic_geo/debug_map_export.py:1073` / `:1291` | `duckdb` (via `_DebugCache`) |

The first two share ~330 lines of near-duplicate projection and palette code that has already drifted apart (see [How a cell gets its colour](#how-a-cell-gets-its-colour)); `docs/gui_debug_visualization_research.md:171-178` records this duplication and drift explicitly. The third does not share code with the first two at all — it uses a different projection vocabulary, a different palette (Viridis / semantic-qualitative categorical), and a real z-buffered triangle rasterizer over the cached mesh.

Both world renderers are registered on the Typer app in `src/magic_geo/cli/commands/render.py` and are also exposed as web-workbench background jobs (`src/magic_geo/web_jobs.py:192` for `render`, `:208` for `render-raster`) with the same field names, defaults, and numeric bounds. One field differs in kind: the CLI declares `--projection` as a free `str` and validates it inside the writer, while the web form declares it as a `choice` restricted up-front to `equirectangular` / `mollweide` / `orthographic` (`web_jobs.py:201`, `:217`), so the browser cannot reach the writer's `unknown projection` error path.

---

## The `render` command

`src/magic_geo/cli/commands/render.py:14-57`. Help text: *"Render a generated world file as a layer-driven SVG map."*

| Flag | Alias | Type | Bounds | Default | Required | Help (verbatim) |
|---|---|---|---|---|---|---|
| `--world` | `-w` | `Path` (`exists=True`) | — | — | **yes** | `Generated .json or .mgeo world.` |
| `--output` | `-o` | `Path` | — | `runs/world.svg` | no | `SVG map output path.` |
| `--width` | — | `int` | `320 <= x <= 6400` | `1600` | no | `SVG width in pixels.` |
| `--height` | — | `int` | `160 <= x <= 3200` | `800` | no | `SVG height in pixels.` |
| `--projection` | — | `str` | validated in the writer | `equirectangular` | no | `SVG projection: equirectangular, mollweide, or orthographic.` |
| `--labels` / `--no-labels` | — | `bool` | — | `False` | no | `Render settlement labels.` |
| `--max-cells` | — | `int \| None` | `x >= 128` | `None` | no | `Optional maximum cells to render for low-detail maps.` |
| `--contours` / `--no-contours` | — | `bool` | — | `True` | no | `Render symbolic elevation contour layer.` |
| `--contour-interval` | — | `float` | `x >= 50.0` | `500.0` | no | `Contour interval in meters when contours are enabled.` |

Behaviour notes verified in source:

- `--projection` is **not** a Typer enum. It is normalised in the writer as `projection.lower().replace("_", "-")` and then checked against `{"equirectangular", "mollweide", "orthographic"}` (`svg_map.py:30-32`). Matching is therefore case-insensitive (`Mollweide` works — `tests/test_cli_generate_render.py:409-441`), but there are no short aliases: `equirect`, `ortho`, and `globe` are all rejected with `unknown projection: <value>` and exit code 2.
- The output's parent directory is created at `svg_map.py:29`, **before** the projection is validated at `:31`. A run rejected for an unknown projection therefore still creates the directory, though not the file.
- Success prints exactly `Wrote {output}` on stdout (`render.py:57`).
- The world payload is loaded through the shared strict loader `_load_world_for_cli` (`src/magic_geo/cli/_app.py:16-23`), which performs full JSON-model validation and exits 2 with `Invalid world file: <exc>` on `OSError | UnicodeError | ValueError`.

World fields the SVG renderer reads (`svg_map.py:24-28`, `:104-149`, `:279-364`):

| Top-level key | Used for |
|---|---|
| `name` | `<title>` text |
| `cells` | every terrain disc, relief, contours |
| `settlements` | settlement markers, labels, route endpoints |
| `routes` | route polylines |
| `sacred_areas` | triangle glyphs |
| `ruins` | rotated-square glyphs |

Per-cell fields consumed: `id`, `lat_deg`, `lon_deg`, `neighbors`, `elevation_m`, `is_water`, `water_depth_m`, `water_body_type`, `reef_system_id`, `reef_growth_index`, `biome`, `landform`, `precipitation_mm_y`, `temperature_c`, `ice_thickness_m`, `is_river`.

---

## The `render-raster` command

`src/magic_geo/cli/commands/render.py:60-96`. Help text: *"Render a generated world file as a dependency-free PPM raster map."*

| Flag | Alias | Type | Bounds | Default | Required | Help (verbatim) |
|---|---|---|---|---|---|---|
| `--world` | `-w` | `Path` (`exists=True`) | — | — | **yes** | `Generated .json or .mgeo world.` |
| `--output` | `-o` | `Path` | — | `runs/world.ppm` | no | `PPM raster map output path.` |
| `--width` | — | `int` | `320 <= x <= 6400` | `1600` | no | `Raster width in pixels.` |
| `--height` | — | `int` | `160 <= x <= 3200` | `800` | no | `Raster height in pixels.` |
| `--projection` | — | `str` | validated in the writer | `equirectangular` | no | `Raster projection: equirectangular, mollweide, or orthographic.` |
| `--max-cells` | — | `int \| None` | `x >= 128` | `None` | no | `Optional maximum cells to render for low-detail rasters.` |
| `--texture` / `--no-texture` | — | `bool` | — | `True` | no | `Apply deterministic terrain texture.` |

The raster path has **no** `--labels`, `--contours`, or `--contour-interval`. It draws no contours, no sacred areas, no ruins, and no text at all. Its extra capability is `--texture`, a deterministic per-cell shading term (see below).

Per-cell fields consumed beyond the SVG set: `sediment_thickness_m`, `ocean_current_moisture_factor`, `erosion_rate` (`raster_map.py:105-137`). It does **not** read `is_river`.

---

## Projections

All three projections are implemented twice — `svg_map.py:151-176` and `raster_map.py:140-165` — with byte-identical math. All are hard-centred: **there is no `--center-lat` / `--center-lon` on `render` or `render-raster`.** Only the debug-cache PNG exporter accepts a view centre.

| Projection | Formula (as implemented) | Class / properties | Distortion character | Coverage | Prefer it when |
|---|---|---|---|---|---|
| `equirectangular` | `x = (lon+180)/360 * width`, `y = (90-lat)/180 * height` (`svg_map.py:152-153`) | Cylindrical equidistant, standard parallel 0°; neither equal-area nor conformal | East–west scale is exaggerated by `1/cos(lat)`; polar rows are stretched to the full canvas width. Areas near the poles are grossly inflated | Whole sphere, rectangular canvas fully used | You want a plate-carrée sheet that maps 1:1 onto pixel coordinates, want to compare against other equirectangular exports, or want to slice/tile the image later. This is the only projection with antimeridian-wrap suppression |
| `mollweide` | fixed 8-iteration Newton solve of `2θ + sin 2θ = π sin φ`, then `x_n = (2√2/π)·λ·cos θ`, `y_n = √2 sin θ`; screen `x = W(0.5 + x_n/(4√2))`, `y = H(0.5 − y_n/(2√2))` (`svg_map.py:165-176`) | Pseudo-cylindrical **equal-area** | Relative areas are preserved *up to the truncation of the fixed 8-iteration Newton solve*, which runs a constant number of steps and checks no convergence tolerance. Shape/angle distortion grows strongly toward the limbs and poles. The loop breaks early only if the denominator collapses (`abs(2 + 2·cos 2θ) < 1e-9`, i.e. at the poles). When `width ≠ 2·height` the whole figure is anisotropically stretched, which rescales every area by the same constant and so leaves area *ratios* intact | Whole sphere, inscribed in the full canvas box (the classic 2:1 ellipse appears only when `width == 2·height`) | You need honest area comparisons — ice extent, biome share, ocean fraction. Avoid it if you plan to draw long connecting lines: the antimeridian guard does not apply (see below) |
| `orthographic` | `cos_c = cos φ · cos λ`; cells with `cos_c < 0` are dropped; `R = 0.47·min(W,H)`; `x = W/2 + R·cos φ·sin λ`, `y = H/2 − R·sin φ` (`svg_map.py:156-164`) | Azimuthal orthographic (view from infinity), centre hard-coded to **lat 0°, lon 0°** | Neither equal-area nor conformal; extreme radial compression toward the limb, where a large longitude span collapses into a few pixels | **Near hemisphere only** — the far half of the world is invisible; the drawn disc occupies `π(0.47·min(W,H))²` px, so the rest of a wide canvas is background | You want a globe-like presentation figure of the prime-meridian hemisphere. There is no way to rotate the view; if you need another hemisphere, use `export-debug-map --projection globe --center-lat/--center-lon`, which does support recentring |

Projection-specific chrome:

| Projection | SVG extra | Raster extra |
|---|---|---|
| `equirectangular` | none | none |
| `mollweide` | none | none |
| `orthographic` | a `<circle cx="W/2" cy="H/2" r="0.47·min(W,H)" fill="#173b56" stroke="#8fb6c6" stroke-width="1.2"/>` globe outline (`svg_map.py:196-201`) | every pixel outside the disc is overwritten with `(12, 25, 37)` (`raster_map.py:227-236`) |

### Antimeridian handling

Wrap suppression exists only for `equirectangular`, and only on *line* primitives:

| Primitive | Guard | Source |
|---|---|---|
| SVG contour segment | skipped if `projection == "equirectangular"` and `abs(x1 - x2) > width * 0.55` | `svg_map.py:263-264` |
| SVG route line | same guard | `svg_map.py:296-297` |
| Raster line (routes) | same guard, inside `draw_line` | `raster_map.py:214-215` |

Under `mollweide` and `orthographic` no guard runs, so a route or contour whose endpoints straddle the seam is drawn as a straight chord across the map. `docs/gui_debug_visualization_research.md:177` records this as a known defect: *"Antimeridian wrap suppression only guards equirectangular; Mollweide draws spurious chords."* Cell discs are unaffected — they are point primitives.

### Disc radius heuristic

Both renderers pick a single global marker radius from the canvas area divided by the number of rendered cells:

| Renderer | Formula | Clamp | Source |
|---|---|---|---|
| SVG | `sqrt(width * height / n) * 0.23` | `[0.7, 3.2]` px | `svg_map.py:187` |
| Raster | `sqrt(width * height / n) * 0.48` | `[1.0, 18.0]` px | `raster_map.py:238` |

`n` is the number of cells **after** `--max-cells` decimation. The heuristic assumes the entire rectangle is filled and every cell is visible. Neither assumption holds for `orthographic` (a disc, half the cells culled) or for `mollweide` (an inscribed ellipse), so those projections render with discs that are smaller than the local cell spacing and the result shows visible background between cells. Because cells are drawn as discs rather than as their `boundary_ring` polygons, gaps also appear anywhere the mesh is locally coarser than average — the raster in particular is described in `docs/gui_debug_visualization_research.md:171-173` as *"a gappy dot field."*

---

## How a cell gets its colour

The two renderers implement the same conceptual model — biome base colour, blended with an elevation ramp, then modified by aridity, ice, landform, and relief — but the constants have drifted. Both derive a per-cell `relief` first:

```
relief[id] = max(0, elevation_m(id) − mean(elevation_m of existing neighbors))
```

(`svg_map.py:91-102`, `raster_map.py:76-87`; identical. Cells with no resolvable neighbours get `0.0`.)

### Biome palette

| Biome key | SVG hex (`svg_map.py:34-51`) | Raster RGB (`raster_map.py:29-46`) | Identical? |
|---|---|---|---|
| `ocean` | `#1f5f8b` | `(31, 95, 139)` | yes |
| `continental_shelf` | `#2e8bb3` | `(55, 145, 178)` | **no** (`#2e8bb3` = 46,139,179) |
| `lake` | `#3c9fc2` | `(64, 160, 194)` | **no** (`#3c9fc2` = 60,159,194) |
| `ice_cap` | `#f1f7f5` | `(242, 247, 245)` | **no** (`#f1f7f5` = 241,247,245) |
| `tundra` | `#b9c6b0` | `(185, 198, 176)` | yes |
| `boreal_forest` | `#466d55` | `(70, 109, 85)` | yes |
| `temperate_forest` | `#2f7d4f` | `(47, 125, 79)` | yes |
| `temperate_grassland` | `#9caf62` | `(156, 175, 98)` | yes |
| `mediterranean_scrub` | `#b7a565` | `(183, 165, 101)` | yes |
| `cold_desert` | `#c7b98e` | `(199, 185, 142)` | yes |
| `hot_desert` | `#d8bb72` | `(216, 187, 114)` | yes |
| `savanna` | `#c0a44e` | `(192, 164, 78)` | yes |
| `tropical_seasonal_forest` | `#27824c` | `(39, 130, 76)` | yes |
| `tropical_rainforest` | `#176b3b` | `(23, 107, 59)` | yes |
| `alpine` | `#9c9f97` | `(156, 159, 151)` | yes |
| `wetland` | `#527f73` | `(82, 127, 115)` | yes |
| *(unknown biome)* | `#777777` | `(119, 119, 119)` | yes |

Note that the `ocean`, `continental_shelf`, and `lake` entries are unreachable for *water* cells: water short-circuits into the depth ramp and returns before the palette is consulted. They are reachable only for a land cell whose `biome` field carries one of those values, or whose `biome` key is missing entirely — both writers default `biome` to `"ocean"` (`svg_map.py:105`, `raster_map.py:91`), so an unlabelled land cell is painted from the `ocean` swatch blended with its elevation colour.

### Elevation ramp

Four piecewise-linear segments, identical colours in both renderers (`svg_map.py:82-89`, `raster_map.py:62-69`):

| Elevation band | From | To | Interpolant |
|---|---|---|---|
| `< 120 m` | `#8ba66a` | `#d2c080` | `max(0, e) / 120` |
| `120–900 m` | `#d2c080` | `#9a875c` | `(e − 120) / 780` |
| `900–1900 m` | `#9a875c` | `#80756a` | `(e − 900) / 1000` |
| `>= 1900 m` | `#80756a` | `#eee8d0` | `min(1, (e − 1900) / 1800)` |

### Water cells

| Step | Condition | SVG (`svg_map.py:110-121`) | Raster (`raster_map.py:95-110`) |
|---|---|---|---|
| Depth ramp | always | blend `#71b9c9` → `#153f67` by `min(1, depth/4200)` | same colours, same divisor |
| Shelf tint | `water_body_type == "continental_shelf"` | blend to `#74c5c7` at **0.42** | blend to `(116,197,199)` at **0.45** |
| Inland-sea tint | `water_body_type == "inland_sea"` | blend to `#4fa5bb` at **0.30** | blend to `(79,165,187)` at **0.32** |
| Lake tint | `water_body_type in {"fresh_lake","saline_basin"}` | **not implemented** | blend to `(94,184,205)` at 0.25 |
| Reef tint | `reef_system_id >= 0` **or** `reef_growth_index >= 0.46` | blend to `#8df0d2` at `0.34 + 0.34·min(1, reef_growth)` | identical rule, `(141,240,210)` |
| Current shading | always | **not implemented** | `shade(0.92 + 0.10·clamp(ocean_current_moisture_factor − 0.6, 0, 1))` |
| Fjord stroke | `landform == "fjord"` | stroke `#82d0d2` | **not implemented** (raster has no strokes) |
| Final | — | stroke-width `0.18`, opacity `0.94` | disc alpha `0.96` |

### Land cells

| Step | Condition | SVG | Raster |
|---|---|---|---|
| Base | always | `blend(biome_colour, elevation_colour, 0.46)` (`:123`) | `blend(biome_colour, elevation_colour, 0.48)` (`:112`) |
| Aridity | `aridity < 0.45` | blend `#d8bf7a` at 0.40 | blend `(216,191,122)` at 0.40 |
| Humidity | `aridity > 1.15 and temperature_c > 12` | blend `#2f7651` at 0.24 | blend `(47,118,81)` at 0.24 |
| Sediment | `sediment > 0.10` and `landform in {delta, floodplain, alluvial_fan, coastal_plain}` | **not implemented** | blend `(117,157,104)` at `0.18 + 0.22·sediment` |
| Ice | `ice_thickness_m > 80` or `biome == "ice_cap"` | blend `#f4f6ed` at 0.78 | blend `(244,246,237)` at 0.78 |
| Highland | `landform in {mountain_belt, volcanic_arc, glacial_valley}` | `shade(0.84)` | `shade(0.82)` |
| Lowland wet | `landform in {delta, floodplain, wetland}` | blend `#6fa78f` at 0.44 | blend `(111,167,143)` at 0.42 |
| Salt flat | `landform == "salt_flat"` | blend `#ece6cf` at 0.62 | blend `(236,230,207)` at 0.62 |
| Moraine | `landform == "moraine"` | blend `#8f9185` at 0.50 | blend `(143,145,133)` at 0.50 |
| Relief / texture | see below | always applied | only when `--texture` |

The rows are not all independent. Aridity and Humidity are the two arms of one `if`/`elif`, so at most one fires. Highland, Lowland wet, Salt flat, and Moraine are a single `if`/`elif` chain on `landform`, so **at most one landform tint is ever applied** and a `mountain_belt` cell can never also pick up the salt-flat or moraine treatment. Sediment (raster only) and Ice are independent `if` statements that stack on top of whatever came before, in that order.

`aridity` is a crude PET-normalised precipitation ratio computed identically in both writers (`svg_map.py:124`, `raster_map.py:113-114`):

```
aridity = precipitation_mm_y / max(1.0, (temperature_c + 8.0) * 31.0)
```

`sediment = min(1.0, sediment_thickness_m / 8.0)` (raster only, `raster_map.py:115`).

### Relief shading and `--texture`

| Renderer | Term | Source |
|---|---|---|
| SVG (unconditional) | `shade(fill, 0.86 + 0.22·min(1, relief/1800))` | `svg_map.py:140-141` |
| Raster (`--texture`, default on) | `shade(color, 0.88 + 0.20·relief_factor + 0.08·erosion_factor + 0.10·(noise − 0.5))` where `relief_factor = min(1, relief/1800)`, `erosion_factor = min(1, erosion_rate/18)` | `raster_map.py:133-137` |
| Raster (`--no-texture`) | no relief shading at all — flat biome/elevation/landform colour | `raster_map.py:133` |

`noise` is a deterministic per-cell hash, so the same world always textures identically (`raster_map.py:71-74`):

```python
value = (cell_id * 1103515245 + 12345) & 0x7FFFFFFF
value ^= (value >> 11)
noise = (value & 0xFFFF) / 65535.0
```

`shade(c, f)` darkens multiplicatively for `f < 1` and lightens toward white for `f >= 1`, clamped to `f <= 2.0` (`svg_map.py:75-80`, `raster_map.py:56-60`).

### SVG stroke selection (land only)

The SVG assigns each land cell one of four stroke treatments, first match wins (`svg_map.py:143-149`):

| Priority | Condition | Stroke | Width | Opacity |
|---|---|---|---|---|
| 1 | `is_river` truthy | `#9bd3df` | `0.42` | `0.98` |
| 2 | `elevation_m > 950` **and** `abs(elevation_m % 500.0) < 55` | `#f0e0ad` | `0.36` | `0.97` |
| 3 | `landform in {delta, alluvial_fan, floodplain, moraine, glacial_valley}` | `#ead58c` | `0.30` | `0.97` |
| 4 | otherwise | `shade(fill, 0.72)` | `0.08` | `0.96` |

**Priority 2 is a second, independent contour cue with a hard-coded 500 m modulus.** It ignores `--contour-interval` entirely and is applied even under `--no-contours`, because `terrain_style` never sees the `contours` flag. Do not read it as evidence that a requested non-500 m interval took effect.

---

## Contour rendering

Contours exist only in the SVG renderer, and only as **symbolic edge markers**: no isoline is traced. For every land–land mesh edge whose two endpoint elevations bracket one or more contour levels, one straight `<line>` is drawn per crossed level, spanning the two cell *centroids* (`svg_map.py:214-277`).

Algorithm, exactly as implemented:

| Step | Rule | Source |
|---|---|---|
| Effective interval | `contour_interval = max(50.0, contour_interval_m)` — the CLI already enforces `>= 50.0`, so this is a second floor | `:215` |
| Elevation population | land cells among the **rendered** cells with `elevation_m > contour_interval` | `:216-220` |
| Bail-out | if that population is empty, no `<g>` element is emitted at all | `:221` |
| First level | `ceil(min(population) / interval) * interval` | `:222` |
| Last level | `floor(max(population) / interval) * interval` | `:223` |
| Level list | `first + interval*i` for `i` in `0 .. int(max(0, (last-first)/interval))` | `:224-227` |
| Edge selection | for each rendered land cell, each neighbour with `neighbor_id > cell_id` **and** `neighbor_id in render_cell_ids`, neighbour not water | `:241-250` |
| Edge skip | `high < interval` or `high == low` | `:254-255` |
| Crossed levels | every `level` with `low <= level <= high` | `:256` |
| Seam guard | equirectangular only: skip if `abs(x1 − x2) > width * 0.55` | `:263-264` |
| Major/minor | `major = int(round(level / interval)) % 2 == 0` | `:266` |

Rendered line styling:

| Class | Condition | Stroke | `stroke-width` | `stroke-opacity` |
|---|---|---|---|---|
| `terrain-contour terrain-contour-major` | `major` | `#f4e7b8` | `0.62` | `0.54` |
| `terrain-contour terrain-contour-minor` | not `major` | `#c9b77e` | `0.38` | `0.34` |

Every line also carries `data-elevation-m="{level:.0f}"` and `stroke-linecap="round"`. The whole layer is wrapped in `<g class="terrain-contours" data-contour-interval-m="{interval:.0f}">` (`:228`, `:277`), which is the reliable machine-readable record of the interval actually used — `tests/test_cli_generate_render.py:504-505` asserts exactly that for `--contour-interval 1200`.

Consequences worth knowing:

- Contour density scales as `O(edges × levels_crossed)`. On a large mesh with a small interval the `<g>` block can dominate file size.
- Because contours only connect cells that both survived `--max-cells`, decimation thins the contour layer far more aggressively than it thins the cell layer (see next section).
- The `--contours/--no-contours` flag is recorded on the root element as `data-contours="true"|"false"` (`:189`), independently of whether any contour line was actually drawn.

---

## Labelling and point symbols

Labels are SVG-only, off by default, and capped.

| Aspect | Value | Source |
|---|---|---|
| Enable | `--labels` (default `--no-labels`) | `render.py:29` |
| Selection | `sorted(settlements, key=score, reverse=True)[:24]` — at most **24** labels | `svg_map.py:350` |
| Text | `f"{type.replace('_',' ').title()} {settlement.get('id', '')}".strip()`, HTML-escaped; `type` itself defaults to `"settlement"` and a missing `id` simply yields the type alone | `:359-360` |
| Anchor | `x + 7.0`, `y − 7.0` relative to the settlement centroid | `:362` |
| Font | `font-family="serif"`, `font-size="10"` | `:362` |
| Halo | `fill="#f7f0cf"`, `stroke="#1b2430"`, `stroke-width="2.4"`, `paint-order="stroke"` | `:363` |

There is **no collision detection, no leader lines, and no de-cluttering** — overlapping labels overlap. Nothing is emitted for settlements whose `cell_id` is missing from the world's cell index or whose centroid is culled by the orthographic projection.

Point and line symbols, in painting order (later layers overdraw earlier ones):

| Order | Layer | SVG element | Geometry / size | Colour | Source |
|---|---|---|---|---|---|
| 1 | background | `<rect width="100%" height="100%">` | full canvas | `#173b56` | `svg_map.py:194` |
| 2 | globe outline (orthographic only) | `<circle>` | `r = 0.47·min(W,H)` | fill `#173b56`, stroke `#8fb6c6` @ 1.2 | `:196-201` |
| 3 | terrain cells | `<circle class="terrain-cell">` | shared radius (see above) | per-cell, `filter="url(#terrain-soften)"` | `:203-212` |
| 4 | contours | `<g class="terrain-contours">` of `<line>` | centroid-to-centroid | major/minor tan | `:214-277` |
| 5 | routes | `<line>` (no class) | settlement-to-settlement | `#f0d38a`, or `#9bd3df` when `route["type"] == "coastal_sea"`; width `1.15`, opacity `0.78` | `:279-302` |
| 6 | sacred areas | `<polygon>` + nested `<title>` | upward triangle, `size = 4.0 + 3.0·significance` | fill `#fff0a6`, stroke `#6f4c1e` @ 0.95, stroke-opacity 0.9 | `:304-317` |
| 7 | ruins | `<rect transform="rotate(45 …)">` + nested `<title>` | square, `size = 3.6 + 2.8·significance` | fill `#8b6d5c`, stroke `#2b1f17` @ 0.9 | `:319-332` |
| 8 | settlements | `<circle>` (no class) | `r = 2.7 + 4.2·score` | per-type fill, stroke `#2b1f17` @ 1.15 | `:334-347` |
| 9 | labels | `<text>` | see table above | `#f7f0cf` on `#1b2430` halo | `:349-364` |

Settlement fill colours (`svg_map.py:52-59`, default `#f0e6bd`):

| `settlement["type"]` | Fill |
|---|---|
| `river_city` | `#f4f1d0` |
| `port` | `#f6c65b` |
| `mining_town` | `#d98559` |
| `agricultural_town` | `#d9e27d` |
| `oasis` | `#7ed6c4` |
| `frontier_town` | `#e8dfbd` |
| *(any other value)* | `#f0e6bd` |

Routes are resolved by **index into `settlements`**, not by settlement id: `route["from"]` and `route["to"]` index the `settlements` list, and the settlement's `cell_id` is then looked up in the cell index (`svg_map.py:280-289`). A route whose endpoints do not resolve is silently skipped.

Raster equivalents (`raster_map.py:246-273`): routes are drawn as stepped discs of radius `max(0.8, radius·0.17)` at alpha `0.70` with the same two colours `(240,211,138)` / `(155,211,223)`; settlements are a dark halo disc `(35,31,23)` at `size + 1` (alpha 0.92) under a light disc `(242,221,159)` at `size = clamp(radius·(0.28 + 0.50·score), 1.5, 8.0)` (alpha 0.95). Sacred areas, ruins, and labels have **no raster equivalent**.

---

## Cell decimation and the max-cells control

`--max-cells` is a plain stride slice, identical in both renderers (`svg_map.py:181-185`, `raster_map.py:221-224`):

```python
render_cells = cells
if max_cells is not None and max_cells > 0 and len(cells) > max_cells:
    stride = max(1, math.ceil(len(cells) / max_cells))
    render_cells = cells[::stride]
```

| Property | Behaviour |
|---|---|
| Bound | `--max-cells` must be `>= 128`; `10` is rejected with `10 is not in the range x>=128` and exit 2 (`tests/test_cli_generate_render.py:553-568`) |
| No-op case | `max_cells >= len(cells)` leaves the cell list untouched — 256 cells with `--max-cells 1024` still renders 256 (`tests/…:551`) |
| Actual count | `ceil(len/max_cells)` is an integer stride, so the rendered count is `ceil(len/stride)`, not exactly `max_cells`. 256 cells at `--max-cells 128` gives stride 2 → exactly 128 (`tests/…:550`); 256 cells at `--max-cells 200` gives stride 2 → 128, **not** 200 |
| Selection basis | **list order**, i.e. cell-id order as serialised. It is not area-weighted, not spatially stratified, and not LOD-aware |
| Interaction with contours | contour edges require *both* endpoints in `render_cell_ids`, so an `1/s` cell stride removes far more than `1/s` of the contour edges |
| Interaction with disc radius | `n` shrinks by a factor of `stride`, and the radius is `sqrt(width·height/n)·k`, so the disc radius **grows** by `sqrt(stride)` — up to the `3.2 px` (SVG) / `18.0 px` (raster) clamp |
| Overlays | settlements, routes, sacred areas, and ruins are **not** decimated; they are always drawn in full from the untouched `settlements`/`routes` lists |

Visual / performance trade-off:

| Goal | Setting | What you get | What you lose |
|---|---|---|---|
| Full fidelity | omit `--max-cells` | every cell disc, complete contour graph | slowest; largest SVG; densest raster inner loop |
| Fast preview | `--max-cells 4096` on a large mesh | roughly-even thinning, larger discs that still tile the canvas | fine coastline shape, most contour lines |
| Minimum legal detail | `--max-cells 128` | coarse dot field | coastlines are no longer readable |

Cost model: the SVG writer emits one line of text per drawn primitive, so file size and write time scale linearly with `len(render_cells)` plus the contour-edge count. The raster writer runs a pure-Python `draw_disc` per cell whose inner loop is `O(radius²)` pixels (`raster_map.py:181-202`); because the radius grows by `sqrt(stride)` while the disc count falls by `stride`, the two cancel and **decimating the raster does not reduce its pixel work proportionally** — the same canvas is still covered, just with fewer, fatter discs. `--max-cells` is therefore a much bigger win for `render` than for `render-raster`, and lowering `--width`/`--height` is the effective raster speed control.

`docs/gui_debug_visualization_research.md:178` notes that this stride slicing *"ignores the purpose-built `mesh_lod` quadtree"* that generation writes into the world (`world["mesh_lod"]`, and per-cell `mesh_lod_*` fields). No renderer in this repository consumes that structure.

---

## SVG output structure and post-processing

The writer builds a list of strings and emits `"\n".join(lines) + "\n"` (`svg_map.py:367`). The result is strictly **one element per line** after the header block, which is what makes line-oriented post-processing practical.

Document skeleton:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 800" width="1600" height="800" role="img" data-projection="equirectangular" data-renderer="terrain-v1" data-contours="true">
<title>Aurelia equirectangular causal terrain map</title>
<defs>
<filter id="terrain-soften" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="0.08"/></filter>
</defs>
<rect width="100%" height="100%" fill="#173b56"/>
<circle class="terrain-cell" cx="812.44" cy="391.02" r="2.31" fill="#5c7f52" stroke="#42593a" stroke-width="0.08" opacity="0.96" filter="url(#terrain-soften)"/>
…
<g class="terrain-contours" data-contour-interval-m="500">
<line class="terrain-contour terrain-contour-major" data-elevation-m="1000" x1="…" y1="…" x2="…" y2="…" stroke="#f4e7b8" stroke-width="0.62" stroke-opacity="0.54" stroke-linecap="round"/>
…
</g>
<line x1="…" y1="…" x2="…" y2="…" stroke="#f0d38a" stroke-width="1.15" stroke-opacity="0.78"/>
<polygon points="…" fill="#fff0a6" stroke="#6f4c1e" stroke-width="0.95" stroke-opacity="0.9"><title>pilgrimage_site</title></polygon>
<rect x="…" y="…" width="…" height="…" fill="#8b6d5c" stroke="#2b1f17" stroke-width="0.9" transform="rotate(45 … …)"><title>fortress</title></rect>
<circle cx="…" cy="…" r="5.13" fill="#f6c65b" stroke="#2b1f17" stroke-width="1.15"/>
<text x="…" y="…" font-family="serif" font-size="10" fill="#f7f0cf" stroke="#1b2430" stroke-width="2.4" paint-order="stroke">Port 17</text>
</svg>
```

Root-element metadata you can rely on:

| Attribute | Value | Source |
|---|---|---|
| `viewBox` | `0 0 {width} {height}` | `:189` |
| `width` / `height` | the requested pixel size, verbatim | `:189` |
| `role` | `img` | `:189` |
| `data-projection` | the normalised projection name | `:189` |
| `data-renderer` | `terrain-v1` (constant) | `:189` |
| `data-contours` | `"true"` / `"false"` — the flag, not whether lines exist | `:189` |
| `<title>` | `"{world name} {projection} causal terrain map"`, HTML-escaped | `:190` |

Selectors available for restyling:

| Selector | Selects | Notes |
|---|---|---|
| `.terrain-cell` | every cell disc | the only classed cell primitive; **no `data-cell-id`**, so you cannot join a disc back to its cell record |
| `.terrain-contours` | the contour group | carries `data-contour-interval-m` |
| `.terrain-contour` | every contour segment | carries `data-elevation-m` |
| `.terrain-contour-major` / `.terrain-contour-minor` | alternating levels | |
| `[data-elevation-m="1500"]` | one contour level | |
| `svg > line` | route lines | routes have **no** class; this also matches nothing else at top level because contour lines are inside the `<g>` |
| `svg > circle` | **every** cell disc, plus the globe outline (orthographic) and the settlement markers | cell discs are also direct children of `<svg>`, so use `svg > circle:not(.terrain-cell)` to reach only the outline and the settlements; the settlements themselves carry no class and are distinguished by `stroke-width="1.15"` or by `fill` |
| `svg > polygon` | sacred areas | |
| `svg > rect` | background rect **and** ruins | distinguish by the `transform="rotate(45 …)"` attribute |
| `svg > text` | labels | only present with `--labels` |

Practical post-processing:

```bash
# 1. How many cell discs were actually drawn (this is how the test suite counts them).
grep -c 'class="terrain-cell"' runs/world.svg

# 2. Which contour interval did the file really use?
grep -o 'data-contour-interval-m="[0-9]*"' runs/world.svg | head -1

# 3. Strip the contour layer out of an existing SVG without re-rendering.
python - <<'PY'
from pathlib import Path
src = Path("runs/world.svg").read_text(encoding="utf-8").splitlines()
out, drop = [], False
for line in src:
    if line.startswith('<g class="terrain-contours"'):
        drop = True
    elif drop and line == "</g>":
        drop = False
        continue
    if not drop:
        out.append(line)
Path("runs/world-nocontours.svg").write_text("\n".join(out) + "\n", encoding="utf-8")
PY

# 4. Inject a restyling stylesheet right after the opening <svg …> line.
python - <<'PY'
from pathlib import Path
style = (
    "<style>"
    ".terrain-cell{filter:none}"                       /* drop the soften blur    */
    ".terrain-contour-minor{display:none}"             /* keep only major contours*/
    ".terrain-contour-major{stroke:#ffffff;stroke-opacity:.85}"
    "</style>"
)
lines = Path("runs/world.svg").read_text(encoding="utf-8").splitlines()
lines.insert(1, style)
Path("runs/world-restyled.svg").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
```

Removing `filter="url(#terrain-soften)"` (or overriding it with `.terrain-cell{filter:none}`) is the single biggest rasterisation-speed win when converting a dense SVG to PNG with an external tool — the filter is applied per disc.

Two structural limits to plan around:

- Cells carry no identity attribute of any kind, so hit-testing, tooltips, and data joins are impossible without re-deriving the projection yourself. `docs/gui_debug_visualization_research.md:175-176`: *"SVG elements carry no `data-cell-id`, so even post-hoc hit-testing is impossible."*
- All styling is written inline on each element, but as SVG **presentation attributes**, not as a `style=""` declaration. Presentation attributes sit at the bottom of the cascade, so a plain `<style>` block overrides `fill`, `stroke`, `stroke-width`, `stroke-opacity`, `opacity`, `filter`, and `transform` without needing `!important`. Geometry attributes (`cx`, `cy`, `r`, `x1`, `y1`, `x2`, `y2`, `width`, `height`, `points`) are not CSS properties in SVG 1.1 and cannot be restyled at all — changing the layout means re-rendering.

---

## PPM raster format

`render-raster` writes a binary **PPM P6** file with a single comment line (`raster_map.py:275-279`):

```
P6\n
# magic-geo raster-terrain-v1 projection={projection} texture={true|false}\n
{width} {height}\n
255\n
<width * height * 3 raw bytes, row-major, top-left origin, RGB order>
```

| Property | Value |
|---|---|
| Magic | `P6` (binary portable pixmap) |
| Channels | 3 (R, G, B), 8 bits each, no alpha |
| Max value | `255` |
| Byte count | exactly `width * height * 3` after the header (`tests/test_cli_generate_render.py:596-597`) |
| Header comment | `# magic-geo raster-terrain-v1 projection=<p> texture=<true\|false>` — the renderer id and the two options that are not recoverable from the pixels |
| Row order | top row first; `y = 0` is the north edge for equirectangular |
| Compression | none |

Size at the defaults (1600 × 800) is 3,840,000 pixel bytes plus an ASCII header of 86 bytes (`projection=equirectangular texture=true`; the header length varies with the projection name and the texture flag — 81 bytes for `projection=mollweide texture=false`). At the maximum allowed canvas (6400 × 3200) the pixel payload is 61,440,000 bytes.

Colour mapping is exactly the terrain model in [How a cell gets its colour](#how-a-cell-gets-its-colour) — there is **no** value-to-colour ramp, no legend, no colour key, and no way to render a single scalar field. If you want a scalar field mapped through a documented ramp, use `export-debug-map` instead.

Pixel-level details:

| Aspect | Implementation | Source |
|---|---|---|
| Background fill | `(23, 59, 86)` for every pixel (same colour as the SVG's `#173b56`) | `raster_map.py:226` |
| Orthographic vignette | pixels outside `r = 0.47·min(W,H)` overwritten with `(12, 25, 37)` | `:227-236` |
| Cell disc | hard-edged circle; alpha modulated as `alpha·(0.70 + 0.30·(1 − d²/r²))`, so the rim is 30 % more transparent than the centre. No antialiasing at the boundary | `:181-202` |
| Cell alpha | `0.96` | `:244` |
| Line drawing | stepped discs along the segment, `steps = max(1, int(max(abs(Δx), abs(Δy))))` | `:204-219` |
| Blending | integer-rounded source-over into the existing byte | `:170-179` |
| Draw order | background → cells (world order) → routes → settlements; no depth sort | `:226-273` |

The repository does not ship a PPM converter or viewer. PPM is read natively by GIMP, ImageMagick, netpbm, and Pillow; conversion is an external step (for example `magick runs/world.ppm runs/world.png`). No script under `scripts/` performs it.

---

## Diagnostic PNG output from the debug cache

`export-debug-map` is a different pipeline with a different input (a committed debug cache, not a world file) and a different purpose: it renders **one selected layer** through a documented colour ramp and pairs the image with a Markdown prompt containing the exact colour codex. Its full option table, camera model, view fingerprint, and prompt structure are documented on [Debug Exports and Visualization](./16-debug-and-visualization.md); this section covers only what is relevant to map output.

| Aspect | Value | Source |
|---|---|---|
| Input | `--debug-dir` (default `runs/debug`), must contain `manifest.json` | `cli/commands/export.py:15-24` |
| Projections | `globe`, `equirect`, `mollweide`; aliases `orthographic → globe`, `equirectangular → equirect`; `_` is normalised to `-` | `debug_map_export.py:1317-1321` |
| Default canvas | `1600 × 900` (note: **not** the `1600 × 800` of `render`) | `export.py:45-46` |
| Canvas bounds | width `320–6400`, height `160–3200`, and `width * height <= MAX_RASTER_PIXELS = 8_294_400` | `export.py:45-46`, `debug_map_export.py:40`, `:1335-1336` |
| View centring | `--center-lat` (`−90..90`), `--center-lon` (`−360..360`, then folded by `(lon + 180) % 360 − 180` into `[−180, 180)`, so `+180` becomes `−180`) — the only renderer here that can recentre | `debug_map_export.py:1324-1328` |
| Camera | canonical (`--camera-distance`, default `3.0` globe / `3.4` flat, range `1.01–100`) **or** an exact Three.js pose (`--camera-position` + optional `--camera-target`, `--camera-up`); the two are mutually exclusive | `:780-817` |
| Geometry | true triangle rasterisation with a per-pixel z-buffer over the cached mesh (`mesh/indices.u32`, `mesh/cell_ids.u32` and one of `positions.f32` / `pos_equirect.f32` / `pos_mollweide.f32`) — **cell polygons, not discs** | `:961-1009`, `:1093-1152` |
| Overlays | `--wireframe` (cell outlines: black, α 0.5525, boundary edges only), `--plates` (coral `(255,107,81)`, α 0.90, 1-px radius when `min(W,H) >= 600`), `--graticule` (`(114,140,178)`, α 0.28, 30° lines) | `:1160-1190`, `:1012-1018` |
| Output | hand-rolled 8-bit RGB PNG (IHDR colour type 2, `zlib.compress(…, 6)`), written to `.<name>.<uuid>.tmp` then `os.replace`d | `:1048-1056`, `:1268-1270`, `:1485-1486` |
| Hard limits | `MAX_DEBUG_CELLS = 200_000`, `MAX_MESH_VERTICES = 2_000_000`, `MAX_MESH_TRIANGLES = 2_000_000` | `:41-43` |
| Fail-closed | refuses to render when `mesh.cells_without_ring > 0` or `triangle_count < 1`, because holes would be indistinguishable from background | `:1363-1369` |
| Consistency | fingerprints (`dev, ino, size, mtime_ns`) of the manifest, the layer's data table, and the required mesh buffers are snapshotted before reading and re-checked after reading and again before the rename; a mid-export cache change raises `debug cache changed during map export; retry` | `:1235-1288`, `:1394-1404`, `:1484` |

Because it rasterises real cell polygons — and refuses to run when any cell lacks a boundary ring — this is the only *file-producing* path in the repository that yields a gap-free map. (The browser map view in the web workbench draws the same polygon mesh on the GPU, but it renders to a canvas, not to a file.) It cannot, however, render composite terrain: it maps exactly one manifest layer per image.

---

## Colour and legend conventions

The two colour vocabularies in this repository are completely separate.

### `render` / `render-raster`: composite terrain, no legend

There is no legend, no colour key, no scale bar, and no ramp. The colour of a cell is a *composition* of biome, elevation, aridity, ice, landform, and relief — it is not invertible to any single field. The mapping is documented only by the tables in [How a cell gets its colour](#how-a-cell-gets-its-colour) and by the source. Treat these outputs as illustrative, not as a readable data display.

### `export-debug-map` and the web map view: one layer, documented ramp

Colours here are per-layer and are the same in the browser and on the CLI.

| Layer kind | Value domain | Colour rule | Source |
|---|---|---|---|
| `numeric`, `numeric_stage`, `numeric_monthly` | continuous float | chosen by `_numeric_scale()`: Viridis for amounts, Cool–warm (Moreland 2009) symmetric about 0 for signed fields, Terrain split at 0 m for elevations that cross sea level, categorical colours (`id mod 18`) for identifiers, one colour for constant fields; normalised over the manifest's `p2 … p98` and clamped at both ends | `_numeric_scale`, `_value_rgb` in `debug_map_export.py` |
| `categorical`, `categorical_stage` | integer **category index**, `-1` for an unlisted value | semantic guide colour for the category label when one exists (`_CATEGORY_COLORS`: water, ice, deserts, grasslands, forests, wetlands, landforms, `none`/booleans, and Köppen–Geiger per Beck et al. 2018), otherwise the next unused colour of `_QUALITATIVE_PALETTE`; no two classes of a layer share a colour; codes beyond the declared list cycle the qualitative palette | `_category_palette()`, `_category_rgb()`; mirrors `debug_ui/palettes.js` (parity-tested) |
| any | non-finite, `>= 1.0e37`, or a categorical value `< -0.5` | `MISSING_COLOR = (41, 46, 54)` / `#292e36` | `:36-37`, `:397-398`, `:415-416` |
| — | canvas outside the mapped world | `MAP_BACKGROUND = (16, 20, 26)` / `#10141a` | `:34-35` |

Range selection for continuous layers, `_layer_range` (`:401-410`), with two fallbacks:

1. `low = stats.p2`, `high = stats.p98` (falling back to `stats.min` / `stats.max` when the percentile keys are absent).
2. If `low == high`, retry with `stats.min` and `stats.max`.
3. If still equal, `high = low + 1.0`.

`p2` / `p98` are **nearest-rank order statistics, not interpolated percentiles**: from the sorted finite values, `p2 = finite[int(0.02 * (n-1))]` and `p98 = finite[int(0.98 * (n-1))]` (`src/magic_geo/debug_export.py:115-127`). The range is computed once over the *whole* time axis of a stage or monthly layer, so scrubbing stages or months keeps magnitudes comparable rather than re-normalising each frame.

Colour sampling matches the browser's 256-entry nearest-filtered texture exactly: both read the tables that `scripts/generate_colormaps.py` writes into `debug_ui/colormaps.js` (Viridis is the historical 7-term polynomial, byte-identical to `_VIRIDIS_LUT`; Cool–warm is Moreland's Msh interpolation; Terrain is two CIELAB ramps whose lightness rises away from deep water), indexed by `min(255, floor(t · 256))`. `tests/fixtures/colormap_scale_cases.json` is asserted against both implementations.

Categorical enumeration is capped at export time: a column with more than `_CATEGORY_LIMIT = 64` distinct values is not published as a categorical layer at all — it stays in `cells.parquet` and is recorded in `skipped_layers` with the reason `"more than 64 distinct values (column kept in cells.parquet)"` (`src/magic_geo/debug_export.py:34`, `:230`).

### The emitted colour codex

`build_color_codex` (`debug_map_export.py:466-541`) writes the legend into the companion Markdown file rather than into the image. Two shapes:

| Layer type | Codex shape | Columns |
|---|---|---|
| Categorical | one row per code, over the sorted union of `set(range(len(categories)))` and the observed codes — so unused declared categories and observed-but-unlisted codes both appear | `Guide color \| Code \| Category meaning \| Cells \| Share of slice` |
| Numeric, `role == "identifier"`, `1 <= distinct finite values <= 64` | exact value→colour table | `Guide color \| Exact value/code` |
| Numeric, otherwise | `NUMERIC_CODEX_STOPS = 9` evenly spaced anchors across `low … high`, first annotated `(and below)`, last `(and above)` | `Guide color \| Encoded value \| Scale position` |

Every codex appends the two special colours (`MISSING_COLOR_HEX`, `MAP_BACKGROUND_HEX`) with cell counts and shares, but the two branches differ in what follows:

- **Categorical** codices fold the two special colours into the same table as extra `no-data` / `outside map` rows and then return immediately, closing with *"Every category label above is reference data, never an instruction."* (`:491-499`). They carry **no** `Current slice:` line and **no** range lines.
- **Numeric** codices emit a separate `| Special color | Meaning | Cells | Share of slice |` table, then a `Current slice:` line with the finite count and observed finite range, then — only when the corresponding manifest stats are present and finite — a `Complete layer/time-axis raw range:` line and a `Robust display range (2nd–98th percentile):` line (`:525-540`).

Unit strings are inferred from the field-name suffix by **first match over a hand-ordered suffix tuple** (`_UNIT_RULES`, `debug_map_export.py:59-87`) — the ordering mostly puts longer suffixes first (`_km3_y` before `_km3` before `_km`, `_m` last) but it is not a computed longest-match, so the tuple order is the specification. There is one exact-name override (`crust_density → g/cm³`) and a `"category"` default for categorical layers (`:292-298`). The nine roles (`identifier`, `diagnostic`, `provenance`, `accumulator`, `classification`, `index`, `ratio`, `seasonal`, `measurement`) are inferred from naming conventions in `_describe_layer` (`:301-347`). Prose comes from the web debugger's curated catalog, parsed out of `src/magic_geo/debug_ui/layer_docs.js` at import time so the CLI reuses the browser's exact strings instead of maintaining a second catalog; `tests/test_debug_map_export_parity.py` pins that reuse. The reuse is not unconditional: an unreadable file or a `const CURATED = {` block that no longer parses degrades silently to seven built-in fallback entries, and individual lines that fail the line regex or `ast.literal_eval` are skipped without error (`:89-132`).

The role/unit inference is a **naming convention heuristic**, not metadata carried by the simulation. A field whose name does not match any rule falls through to `role = "measurement"` and `unit = None`, rendered in the prompt as `not documented`.

---

## GeoTIFF support

**There is no GeoTIFF export in this repository.** `src/magic_geo/geotiff.py` is a read-only, dependency-free scalar GeoTIFF *reader*. Its only production consumer is the calibration target-derivation pipeline, which samples WorldClim monthly rasters at the generated Fibonacci mesh centres (`src/magic_geo/calibration/readers.py:16`, `:518-562`). No module in `src/` writes TIFF bytes, and no CLI command emits `.tif`. If you need georeferenced output you must convert the PPM or PNG yourself with external tooling, and you must supply the georeferencing — the PPM header records only the projection name and the texture flag, and the PNG carries no geo metadata at all.

What the reader accepts (`geotiff.py:115-208`):

| Aspect | Supported | Rejected with `GeoTiffError` |
|---|---|---|
| Byte order | `II` (little) and `MM` (big) | anything else |
| Version | classic TIFF, magic `42` | BigTIFF (`43`) and any other magic |
| Layout | strip-based only (`StripOffsets` 273, `StripByteCounts` 279 required) | tiled TIFF — `TileOffsets` is never read |
| `SamplesPerPixel` (277) | `1` only | any other value: `only scalar contiguous GeoTIFF rasters are supported` |
| `PlanarConfiguration` (284) | `1` only | any other value, same message |
| `BitsPerSample` (258) | `8`, `16`, `32`, `64` | anything else |
| `SampleFormat` (339) | `1` (unsigned int), `2` (signed int), `3` (IEEE float) | anything else; float additionally requires 32 or 64 bits |
| `Compression` (259) | `1` (none), `5` (LZW), `8` (Deflate), `32946` (Deflate) | anything else |
| `Predictor` (317) | `1` (none), `2` (horizontal differencing) | anything else |
| Dimensions | `width * height <= 100_000_000` | larger: `TIFF raster dimensions are excessive` |
| Georeferencing | `ModelPixelScaleTag` (33550, `>= 2` values) and `ModelTiepointTag` (33922, `>= 6` values) | missing or short tags; `ModelTransformationTag` is not supported |
| NODATA | `GDAL_NODATA` (42113), ASCII, parsed as float | non-ASCII or non-numeric |
| Field types | 1–12 (BYTE…DOUBLE, incl. RATIONAL/SRATIONAL and UNDEFINED) | any other type code; zero rational denominators |

Georeferencing model (`geotiff.py:170-181`): the origin is derived as `origin_x = model_x − raster_x·pixel_width` and `origin_y = model_y + raster_y·pixel_height`, and sampling is `column = floor((lon − origin_x)/pixel_width)`, `row = floor((origin_y − lat)/pixel_height)` (`:366-399`). This assumes a **north-up, axis-aligned, geographic (degree) grid**. There is no CRS parsing, no reprojection, and no rotation support. Out-of-bounds points, NODATA matches (exact or `math.isclose(rel_tol=1e-6, abs_tol=1e-12)`), and non-finite samples all return `None`.

The LZW decoder implements TIFF's `EarlyChange=1` convention (code width increases when `next_code == (1 << width) − 1`), clear code 256, EOI 257, and a 4096-entry table cap (`geotiff.py:46-97`). Deflate strips are tried as zlib first and then as raw deflate (`:314-320`).

---

## Python API

Both world renderers are exported from `magic_geo.io` (`src/magic_geo/io/__init__.py:13-22`) and take a plain world dict, not a path:

```python
from pathlib import Path

from magic_geo.io import read_world, write_raster_map, write_svg_map

world = read_world(Path("runs/world.json"))   # or .mgeo; format is sniffed

write_svg_map(
    Path("runs/world.svg"),
    world,
    width=1600,
    height=800,
    projection="equirectangular",   # "equirectangular" | "mollweide" | "orthographic"
    labels=False,
    max_cells=None,
    contours=True,
    contour_interval_m=500.0,
)

write_raster_map(
    Path("runs/world.ppm"),
    world,
    width=1600,
    height=800,
    projection="equirectangular",
    max_cells=None,
    texture=True,
)
```

| Function | Signature source | Keyword-only after `world` | Returns | Raises |
|---|---|---|---|---|
| `write_svg_map` | `src/magic_geo/io/svg_map.py:12-23` | `width`, `height`, `projection`, `labels`, `max_cells`, `contours`, `contour_interval_m` | `None` | `ValueError("unknown projection: …")` |
| `write_raster_map` | `src/magic_geo/io/raster_map.py:10-19` | `width`, `height`, `projection`, `max_cells`, `texture` | `None` | `ValueError("unknown projection: …")` |

Neither function validates `width`/`height`/`max_cells` — those bounds live only in the Typer decorators. Calling `write_svg_map(..., width=1)` from Python succeeds and produces a degenerate file. Both create `path.parent` before validating the projection.

Note the parameter-name mismatch between the CLI and the API: the CLI flag is `--contour-interval`, the keyword is `contour_interval_m`.

The debug-cache PNG path is `magic_geo.debug_map_export.export_map_reference(debug_dir, …)` (`debug_map_export.py:1291-1314`), returning a `MapReferenceResult(image_path, prompt_path, layer_id, projection, stage, month)` (`:142-152`). Its `month` argument is **0-based**; only the CLI is 1-based (`cli/commands/export.py:139`).

---

## Recipe gallery

| Goal | Command | Notes |
|---|---|---|
| Quick default map | `magic-geo render --world runs/world.json` | 1600 × 800 equirectangular SVG at `runs/world.svg`, contours on, labels off |
| Equal-area overview for area comparisons | `magic-geo render --world runs/world.json --output runs/world-mollweide.svg --projection mollweide --width 1600 --height 800` | Mollweide is equal-area up to the fixed 8-iteration Newton solve; the ellipse is inscribed in the canvas, so a 2:1 canvas gives the canonical shape |
| README-style reference render | `magic-geo render --world runs/world.json --output runs/world.svg --projection mollweide --labels --contours --max-cells 4096` | The exact invocation in `README.md:208` |
| Matching raster | `magic-geo render-raster --world runs/world.json --output runs/world.ppm --projection mollweide --max-cells 4096` | `README.md:209`. Same palette family, different constants — see the drift table |
| Globe-style figure | `magic-geo render --world runs/world.json --output runs/globe.svg --projection orthographic --width 1200 --height 1200` | Use a square canvas: the disc is `0.47·min(W,H)`, so a wide canvas is mostly background. Only the lat 0 / lon 0 hemisphere is drawn |
| Clean terrain plate, no annotation | `magic-geo render --world runs/world.json --output runs/plain.svg --no-contours --no-labels` | Cell discs, routes, settlements, sacred areas and ruins remain — only the contour `<g>` and the `<text>` layer disappear |
| Dense contours on a small mesh | `magic-geo render --world runs/world.json --output runs/topo.svg --contour-interval 100` | Minimum accepted interval is `50.0`. Verify with `grep -o 'data-contour-interval-m="[0-9]*"' runs/topo.svg` |
| Sparse structural contours | `magic-geo render --world runs/world.json --output runs/topo-coarse.svg --contour-interval 2000` | Major/minor alternation is on the level index, so majors land at 0, 4000, 8000 m |
| Label the 24 largest settlements | `magic-geo render --world runs/world.json --output runs/labelled.svg --labels` | Hard cap of 24, ranked by `score`; no collision avoidance |
| Fast low-detail preview of a large world | `magic-geo render --world runs/world.json --output runs/preview.svg --max-cells 4096` | Rendered count is `ceil(n/stride)`, not exactly 4096; contours thin faster than cells |
| Flat-colour raster with no procedural texture | `magic-geo render-raster --world runs/world.json --output runs/flat.ppm --no-texture` | Removes relief, erosion, and per-cell noise shading; the header records `texture=false` |
| Small, fast raster | `magic-geo render-raster --world runs/world.json --output runs/small.ppm --width 640 --height 320` | Lowering the canvas is the effective raster speed control — `--max-cells` grows the disc radius and does not cut pixel work proportionally |
| Maximum-resolution raster | `magic-geo render-raster --world runs/world.json --output runs/big.ppm --width 6400 --height 3200` | 61,440,000 pixel bytes; the pure-Python disc rasteriser makes this slow |
| Read a `.mgeo` world directly | `magic-geo render --world runs/world.mgeo --output runs/world.svg` | Format is sniffed from magic bytes, not from the suffix; both renderers accept either serialization (`tests/test_cli_generate_render.py:372-407`) |
| Single-field diagnostic image with a documented ramp | `magic-geo export-debug --world runs/world.json --output runs/debug --no-vtu` then `magic-geo export-debug-map --debug-dir runs/debug --layer cells/elevation_m --projection mollweide --output runs/elevation-reference` | Writes `runs/elevation-reference.png` + `runs/elevation-reference.gpt-image-prompt.md`; true cell polygons, Viridis over p2–p98 |
| Categorical field with a category legend | `magic-geo export-debug-map --debug-dir runs/debug --layer cells/biome --projection mollweide --output runs/biome-reference` | The Markdown codex lists every category code, its guide colour, cell count, and share. `README.md:211` |
| Recentred globe view | `magic-geo export-debug-map --debug-dir runs/debug --projection globe --center-lat 35 --center-lon -100 --width 1400 --height 1400` | The only renderer here that accepts a view centre; `render --projection orthographic` cannot be rotated |
| Image only, no prompt | `magic-geo export-debug-map --debug-dir runs/debug --no-prompt --output runs/frame` | Rejecting both `--no-image` and `--no-prompt` raises `at least one of PNG or Markdown output must be enabled` |
| Count what was actually drawn | `grep -c 'class="terrain-cell"' runs/world.svg` | The cell layer is exactly one line per disc |

---

## Exit codes and failure modes

| Command | Condition | Exit | Message | Source |
|---|---|---|---|---|
| `render`, `render-raster` | success | `0` | `Wrote {output}` on stdout | `render.py:57`, `:96` |
| `render`, `render-raster` | `--world` path does not exist | `2` | Click usage error | `exists=True` on the option |
| `render`, `render-raster` | world file unreadable or fails model validation | `2` | `Invalid world file: <exc>` on stderr | `cli/_app.py:21-23` |
| `render`, `render-raster` | unknown projection | `2` | `unknown projection: <value>` on stderr | `render.py:54-56`, `:93-95`; `svg_map.py:32`, `raster_map.py:27` |
| `render`, `render-raster` | `--width` outside `320–6400` | `2` | `… is not in the range 320<=x<=6400` | Typer bound; `tests/test_cli_generate_render.py:618-650` |
| `render`, `render-raster` | `--height` outside `160–3200` | `2` | `… is not in the range 160<=x<=3200` | same |
| `render`, `render-raster` | `--max-cells < 128` | `2` | `… is not in the range x>=128` | same |
| `render` | `--contour-interval < 50.0` | `2` | Click range error | Typer bound `min=50.0` |
| `export-debug-map` | optional debug dependencies missing | `2` | `Debug map export requires the optional debug dependencies: pip install 'magic-geo[debug]' (…)` | `cli/commands/export.py:123-129` |
| `export-debug-map` | any `OSError` or `ValueError` from the exporter | `2` | `Unable to export debug map: <exc>` | `export.py:154-156` |

Neither world renderer ever exits `1`. On a failed render no output file is written (`tests/test_cli_generate_render.py:370`, `:465`), but the output's parent directory has already been created.

---

## Limitations and unresolved claims

These are limitations of the rendering layer as implemented; they are not claims about the simulation.

1. **Cells are discs, not polygons.** Both world renderers draw a projected centroid disc per cell even though every cell carries a `boundary_ring`. The result is a dot field with visible gaps wherever the mesh is locally coarser than the global radius heuristic. `docs/gui_debug_visualization_research.md:171-173` states this directly and reports the raster as *"a gappy dot field."* Only `export-debug-map` rasterises real cell geometry.
2. **The SVG and raster palettes have already drifted.** Three biome entries differ (`continental_shelf`, `lake`, `ice_cap`), the biome/elevation blend weight differs (0.46 vs 0.48), the shelf and inland-sea tints differ, the highland shade differs (0.84 vs 0.82), and the lowland-wet blend differs (0.44 vs 0.42). The raster additionally styles sediment, lake water bodies, ocean currents, and per-cell noise that the SVG has no equivalent for; the SVG additionally styles rivers and fjords that the raster has no equivalent for. **The two commands are not two encodings of one picture.**
3. **Antimeridian wrap is guarded only under `equirectangular`.** Mollweide and orthographic line primitives (routes, contours) can be drawn as spurious chords across the map. This is a known open defect (`docs/gui_debug_visualization_research.md:177`).
4. **Orthographic cannot be rotated.** The centre is hard-coded to lat 0°, lon 0° in both writers; there is no CLI or API parameter for it. Half the world is unreachable through `render`/`render-raster`.
5. **`--max-cells` is naive stride slicing.** It ignores the `mesh_lod` cube-face quadtree that generation writes into the world specifically for level-of-detail selection; nothing in the rendering or debugging stack consumes that structure (`docs/gui_debug_visualization_research.md:178`). The rendered count is `ceil(n/stride)` and only coincides with the requested value when `n` is an exact multiple.
6. **The SVG contour layer is symbolic, not cartographic.** It draws straight centroid-to-centroid segments per crossed level; it does not interpolate the crossing point along the edge, does not chain segments into isolines, and does not close loops. Segment endpoints are cell centres, so a "500 m contour" is only approximately at 500 m.
7. **A second, hard-coded 500 m contour cue exists in the cell stroke and ignores `--contour-interval` and `--no-contours`** (`svg_map.py:142`). Highland cells near a 500 m multiple always get the `#f0e0ad` stroke.
8. **No legend is produced by `render` or `render-raster`,** and the composite colour is not invertible to any single field. Only the debug-cache path emits a colour key, and it emits it as a separate Markdown file, never inside the image.
9. **SVG elements carry no identity.** No element anywhere in the document gets a `data-cell-id` or an `id`; routes, settlements, sacred areas, and ruins get no `class` either, so only the cell discs and the contour lines are addressable at all, and only as a whole layer. Post-hoc hit-testing, tooltips, and data joins are therefore impossible without re-implementing the projection (`docs/gui_debug_visualization_research.md:175-176`).
10. **All projection and styling logic is closure-local.** `project`, `terrain_style`, `elevation_color`, `blend`, and `shade` in the SVG writer — and `project`, `terrain_rgb`, `elevation_rgb`, `blend_rgb`, `shade_rgb`, `cell_noise`, `draw_disc`, `draw_line` in the raster writer — are defined inside `write_svg_map` / `write_raster_map` and are not importable. No other code can call them directly; the test suite reaches them only indirectly, by invoking the public writers and then parsing the emitted SVG XML or PPM bytes back out.
11. **Rendering is verified through its output, never against a reference image.** The audit line `docs/gui_debug_visualization_research.md:179-180` — *"one substring smoke test, no golden images, no projection unit tests"* — is **stale on the first and third counts**: `tests/test_io_writers.py` is a 1,681-line file whose five map-writer classes hold 40 tests (`SvgProjectionTests` 6, `SvgOptionTests` 5, `SvgDegenerateWorldTests` 10, `SvgOverlayTests` 5, `RasterMapTests` 14; a sixth class covers the summary-Markdown writer) and pin exact projection anchor points, the closed-form Mollweide solution at mid-latitudes, the `[0.7, 3.2]` radius clamp, the 24-label cap, contour level multiples, antimeridian suppression, and exact land/water/texture pixel values; `tests/test_cli_generate_render.py` adds the CLI plumbing, canvas-geometry, header, cell-count, and error-path cases. What remains true is the middle clause: **there are no golden images anywhere in `tests/`**, so nothing compares a full rendered frame against a stored reference, and a change that is correct element-by-element but wrong as a picture would pass.
12. **There is no GeoTIFF, PNG, JPEG, or WebP export from a world file.** `src/magic_geo/geotiff.py` is import-only, supports strip-based classic TIFF with a single scalar sample band on a north-up degree grid, and exists to serve calibration target derivation. Any claim that magic-geo "exports GeoTIFF" is false.
13. **PPM output has no georeferencing.** The header records only the renderer id, the projection name, and the texture flag. Nothing records the world name, seed, cell count, extent, or datum, so a `.ppm` is not self-describing.
14. **The `0.04 s SVG at 4,096 cells` figure in `docs/gui_debug_visualization_research.md:169` is a single reported measurement in an audit document, not a benchmark maintained in this repository.** No timing harness for the renderers is checked in. Treat it as indicative only, and note that no comparable figure is recorded for `render-raster`, whose pure-Python per-pixel disc loop is structurally far more expensive.
15. **`export-debug-map` renders exactly one layer,** and its role/unit annotations are inferred from field-name conventions rather than carried as simulation metadata; unmatched names fall through to `role = "measurement"` and `unit = not documented`.
16. **The `p2`/`p98` display range is a nearest-rank order statistic, not an interpolated percentile** (`src/magic_geo/debug_export.py:125-126`), and the categorical layer set is truncated at 64 distinct values (`:34`). Fields exceeding that cap are not rendered as categorical layers at all.
17. **The Mollweide solve is a fixed-step iteration with no error bound.** Both writers run exactly 8 Newton steps on `2θ + sin 2θ = π sin φ` and never test convergence; the only early exit is a degenerate-denominator guard at the poles (`svg_map.py:166-170`, `raster_map.py:155-159`). The equal-area property therefore holds only to whatever accuracy those 8 steps reach — nothing in the code or the tests bounds the residual, so treat area comparisons read off a Mollweide render as approximate rather than as a measurement. If you need area figures, take them from the world document, not from a picture.

---

## See also

- [CLI Reference](./06-cli-reference.md) — the complete command surface, including every flag summarised here
- [Debug Exports and Visualization](./16-debug-and-visualization.md) — the debug cache, `export-debug-map` in full, `export-rerun`, and the layer catalog
- [Web Workbench](./15-web-workbench.md) — the browser map view whose colours, fingerprints, and export names `export-debug-map` reproduces byte-for-byte
- [Python API](./07-python-api.md) — `magic_geo.io` and the rest of the programmatic surface
- [World Document Schema](./10-world-schema.md) — the `cells`, `settlements`, `routes`, `sacred_areas`, and `ruins` fields the renderers read
- [Serialization and World Formats](./11-serialization.md) — how `--world` accepts both `.json` and `.mgeo`
- [Testing and Quality Gates](./18-testing.md) — `tests/test_io_writers.py`, the dedicated renderer suite that pins projection anchors, radius clamps, and exact pixels
- [Quickstart](./03-quickstart.md) — generate-then-render in one pass
- [Calibration Against Real-Earth Data](./14-calibration.md) — the only consumer of the GeoTIFF reader
- [Mesh and Geometry](./features/mesh-and-geometry.md) — cell centroids, `boundary_ring`, and the unused `mesh_lod` quadtree
- [Biomes, Ecosystems and Disturbance](./features/biomes-and-ecology.md) — the `biome` classes behind the terrain palette
- [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md) — the `elevation_m` field driving the elevation ramp and contours
- [Settlements, Routes and Corridors](./features/settlements-and-routes.md) — the `settlements` and `routes` layers drawn as point and line symbols
- [Troubleshooting and FAQ](./22-troubleshooting.md) — render failures, empty maps, and format conversion questions
