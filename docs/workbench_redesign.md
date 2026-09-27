# Workbench redesign — September 26, 2026

This record explains why and how the web workbench UI was rebuilt, which
practices it follows, how each screen maps to the API, and what was verified.
For using the workbench, read the [guide](debug_ui_guide.md). For server
contracts, read the [wiki reference](wiki/15-web-workbench.md). Earlier reviews
([generation UX](generation_ux_review.md), [workbench UX](workbench_ux_review.md))
remain valid for the behaviour they describe. This redesign keeps every guarantee
they established:

- request ordering and races
- exact YAML
- revision-checked saves
- honest progress
- staged publication

## Problems found in the previous interface

| Area | Problem |
|---|---|
| Entry point | The app opened on an empty or technical map. Nothing explained the workflow or showed what already existed. |
| Navigation | Five top tabs came in an order unrelated to the task (Map, Data, Config, Operations, API). There was no global search, and Help was only reachable from the map toolbar. |
| Creating a world | Five manual steps were needed: open Config, reset a profile, edit YAML, save, open Operations, review, start. There was no guided path for occasional users. |
| Output collisions | Every generation defaulted to `runs/world.json` and `runs/debug`, so a new world replaced the one on screen. |
| Layer discovery | 474 per-cell fields sat in one alphabetical list under "cells". There were no topics, favourites or type filters, and only raw field names were shown. |
| Categorical colours | Golden-ratio hues ignored meaning. Oceans were drawn orange, and neighbouring classes could look alike. |
| Time series | There was no playback. Month labels showed only an index. |
| Feedback | A finished background job was noticed only by visiting Operations. There were no notifications and no job state in the tab title. |
| Visual system | Dark only, with ad-hoc colours, unicode glyphs for icons, 9–11 px labels and no light theme. |
| Links | A map view could not be shared or restored from the URL. |
| Documentation | The README opened with a storage note. The UI guide described tabs and buttons that no longer exist. There was no product overview page. |

## Practices applied

The research brief drew on the sources listed at the end of this record.

- **Information architecture.**
  - A left navigation rail follows the workflow: Home → Configure → Jobs → Map
    → Data → API. It collapses to a bottom bar on phones.
  - Home is a resume-and-onboard dashboard.
  - Progressive disclosure goes at most two levels deep (advanced fields,
    technical logs, full capability report).
- **Command palette.**
  - <kbd>Ctrl</kbd>/<kbd>⌘</kbd> <kbd>K</kbd> opens an ARIA combobox inside a
    modal dialog. Focus stays in the input while arrow keys move the active
    option.
  - It searches views, actions, layers, worlds, configurations, operations and
    jobs, and shows shortcuts beside actions so they are learned.
- **Empty states** say what is happening, teach, and offer the next action
  (NN/g). Examples: the map without a world, an empty world library, and a job
  with no output.
- **Wizard for new users, editor for experts.**
  - The New world dialog asks for a profile, name, seed and resolution, plus
    optional overrides whose bounds come from the live JSON Schema.
  - The server renders the YAML (`/api/config/render`), so the schema remains
    the single source of truth.
  - Experts keep the exact-text YAML editor, now with syntax colouring, line
    numbers and a step indicator.
- **Map and geo visualization.**
  - Layers are grouped by physical domain, with counts. You can pin favourites,
    filter by type (numeric, classes, over time), and search names, labels,
    units, roles, descriptions and classes.
  - Rows show readable labels and units, while raw ids stay in tooltips, the
    layer card and the legend.
  - Colormaps are perceptually uniform (Viridis) for magnitudes, and — after
    the second pass below — diverging about 0 for signed fields, split at sea
    level for elevations and categorical for identifiers. Categories use a
    qualitative palette with semantic anchors (water blue, deserts tan, forests
    green) and the standard Köppen–Geiger scheme.
  - Legends mark clipped ranges with extend triangles, show units, and keep one
    scale across the time axis.
  - The time bar can play; each step waits for the previous slice.
  - Hover shows details on demand, and click pins them in the inspector.
- **Long-running jobs.**
  - Jobs keep the earlier honest-progress design: phases, measured durations,
    real counts only, and no invented ETA.
  - They now also show state in the header pill, a dot on the Jobs tab, and the
    browser tab title.
  - Completion toasts appear (Carbon: toasts with an action persist) with an
    **Open map** or **View job** action.
  - Each world gets its own output folder.
- **Visual system.**
  - Semantic design tokens for dark and light themes, with pre-paint theme
    application to avoid a flash.
  - A neutral UI palette so data colours stand out.
  - System font stack, tabular numerals for readouts, a 13–14 px base size, and
    a consistent SVG icon sprite.
  - Radii and elevation that step lighter as surfaces are raised.
- **Accessibility (WCAG 2.2 AA).**
  - Contrast of at least 4.5:1 for text in both themes.
  - Visible `:focus-visible` rings and focus-trapped dialogs that restore focus.
  - Polite live regions for status and toasts.
  - Text accompanies every colour state.
  - Reduced-motion support, including instant projection switches.
  - Single-key shortcuts can be turned off (2.1.4).
  - Targets are at least 24 px (28–34 px in practice).
  - Layouts reflow down to 320 px.
- **URL state.**
  - `#map?layer=…&stage=…&month=…&proj=…` is kept current with
    `history.replaceState` and restored on load.
  - The last-used view is remembered.
- **Documentation (Diátaxis).**
  - The README leads with what the project is, a screenshot, key properties
    and a documentation map sorted by need: learn, do, look up, understand.
  - The guide is organized as a tutorial, then per-view how-to and reference
    material, then explanation.
  - UI microcopy is verb-first and sentence case, and errors explain how to
    recover.
- **Landing page** (`/landing.html`). Its sections follow the structure of
  developer-tool pages that perform well:
  - a value proposition, a specific call to action and a real product
    screenshot
  - a capabilities strip
  - benefit-framed features
  - how it works, with a screenshot gallery
  - the pipeline
  - tabbed quickstarts with copy buttons
  - use cases
  - Diátaxis-sorted documentation links
  - a final call to action

  Images are WebP with explicit dimensions, and the page loads no third-party
  scripts or fonts.

## How the UI maps to the API

| UI | Endpoint(s) |
|---|---|
| Header status, Home "Explore" card, storage locations | `GET /api/status` (polled every 5 s) |
| World picker, Home library, palette → Worlds | `GET /api/worlds`, `POST /api/worlds/select` |
| New world dialog | `GET /api/config/profiles`, `GET /api/config/schema` (bounds), `POST /api/config/render`, `POST /api/config/save` |
| Configure | `GET /api/config/files`, `GET /api/config/file`, `GET /api/config/template`, `POST /api/config/validate`, `POST /api/config/save` |
| Jobs launcher and quick picks | `GET /api/operations` |
| Job progress, history, header pill, toasts, tab title | `GET /api/jobs` (polled every 2.5 s while relevant), `GET /api/jobs/{id}` |
| Start, cancel and download | `POST /api/jobs`, `POST /api/jobs/{id}/cancel`, `GET /api/jobs/{id}/artifacts/{n}` |
| Map | `GET /api/manifest`, `GET /mesh/*`, `GET /api/layer/{id}`, `GET /api/plate-boundaries`, `GET /api/cell/{id}` |
| Data | `GET /api/catalog`, `GET /api/family/{name}`, `GET /api/stage-summary/{name}`, `GET /api/section/{name}` |
| API & system, Home "System" | `GET /api/backend`, `/api/docs`, `/api/redoc` |

Every cache-backed read still carries the manifest revision. A read that goes
stale fails with `409` instead of mixing data from two worlds.

No server routes were added or changed. The job-catalog wording in `web_jobs.py`
was rewritten (titles, descriptions and help). *Export browser/ParaView cache*
is now **Prepare browser map**, and the Generate options read **Prepare browser
map** and **Browser map folder**.

## What changed, by file

| File | Change |
|---|---|
| `debug_ui/index.html` | New shell: navigation rail, header with palette trigger, world picker, theme toggle and help. Adds the Home view, the palette and New world dialogs, the toast region and an SVG icon sprite. |
| `debug_ui/style.css` | Rewritten design system: dark and light tokens, components, and responsive layouts including container queries for the map toolbar. |
| `debug_ui/app.js` | Routing (Home, URL state, last view), grouped and pinnable layer list with type filters, legend units and extend markers, palette texture for classes, time-bar playback, inspector summary, backend summary, notifications, command catalog, world selection helpers |
| `debug_ui/home-workbench.js` | New Home dashboard |
| `debug_ui/command-palette.js` | New command palette |
| `debug_ui/new-world.js` | New guided world creation |
| `debug_ui/ui.js` | New icons, toasts, theme, storage and formatting helpers |
| `debug_ui/palettes.js` | New categorical palette shared with the CLI exporter |
| `debug_ui/config-workbench.js` | YAML highlighting and gutter, step indicator, per-world output defaults, hooks for the New world dialog |
| `debug_ui/operations-workbench.js` | Quick picks, friendly titles, outcome-tinted activity pill, job-change hook |
| `debug_ui/layer_docs.js` | Layer topics, featured layers, labels and units, rewritten help and shortcuts |
| `debug_ui/landing.html`, `landing.css`, `assets/*.webp` | Product landing page and real screenshots |
| `debug_map_export.py` | The CLI exporter uses the same categorical palette |
| `web_jobs.py` | Clearer operation copy |
| `pyproject.toml`, `MANIFEST.in` | Package the WebP assets |
| README, `debug_ui_guide.md`, wiki 03, 15, 16 and 17 | Rewritten or updated for the new interface |

## Verification

**Automated**

- `node tests/test_debug_ui.mjs` gives **110 passed**. This is the 102 earlier
  race and contract tests, plus 8 new ones for:
  - topic classification and labels
  - semantic and unique palettes
  - palette ranking and limits
  - YAML highlighting escaping
  - per-world outputs that keep typed destinations
  - URL state
  - session-only notifications
  - Home ordering and escaping

  The harness now loads every controller and helper module the way the
  browser's module scope would.
- `pytest tests/test_debug_map_export.py tests/test_debug_map_export_parity.py`
  gives **80 passed**. Three new parity tests check that the JS and Python
  palettes are identical, that no guide colour reuses the missing or background
  colour, and that no layer assigns one colour to two classes.
- Four suites give **94 passed**:
  - `tests/test_debug_static_cache.py`, which serves every new asset with
    revalidation headers
  - `tests/test_debug_server.py`, which checks packaging of the new assets
  - `tests/test_generation_progress.py`
  - `tests/test_runtime_paths.py`
- `tests/test_web_jobs.py` gives **64 passed**.
- Final combined run of `test_debug_static_cache`, `test_debug_server`,
  `test_web_jobs`, `test_debug_map_export`, `test_debug_map_export_parity`,
  `test_generation_progress` and `test_runtime_paths`: **238 passed, 402
  subtests passed**.

**Defects found and fixed while verifying**

- **Name fields never validated.** Chromium compiles `pattern` attributes with
  the regex `v` flag, where an unescaped `-` inside a character class is invalid.
  The browser therefore ignored the configuration file-name pattern, a
  pre-existing problem, and the new world-name pattern.

  Both now use `\-`. The browser rejects `bad name!` and accepts
  `good-name.yaml`.
- **Theme choice not restored.** The pre-paint theme script compared the raw
  stored string with `light`/`dark`, but `ui.js` stores JSON (`"light"`). It
  now parses the value, so a saved choice survives reloads.
- **Keyboard handlers could throw.** They assumed an element target and failed
  when a key event targeted the document. They now use `targetWithin()`.

**Real browser** (in-app Chromium, against the repository cache and an isolated
workspace)

- Home, Configure, Jobs, Map, Data and API rendered in the dark and light
  themes. The browser console had no errors.
- End-to-end with the smoke profile in an isolated workspace:
  1. **New world → Create & generate** saved `configs/vale.yaml` and queued the
     job with `vale/world.json` and `vale/debug`.
  2. Phase updates appeared in the header, the tab title and the Jobs tab dot.
  3. The job succeeded in 22 s.
  4. The **World ready** toast's **Open map** action showed the new 128-cell
     world.
- Command palette: `precip` ranked *Precipitation* first. Enter opened the
  monthly layer, the URL became `#map?layer=…&month=1`, and playback advanced to
  month 5 and paused.
- A deep link `#map?layer=cells%2Ftemperature_c&proj=mollweide` restored the
  layer and projection on a fresh load.
- Pinning, the *Over time* filter and the inspector summary
  (`Temperature 30.0156 °C` with latitude and longitude) behaved as designed.
- At 375 px wide the bottom tab bar appeared, the document and view widths both
  measured 375 px (no horizontal overflow), and the map toolbar was compact.
- The biome and Köppen maps read naturally with the new palette. The
  screenshots in `debug_ui/assets/` were captured headlessly from the running
  workbench.

**Not established**

- No screen-reader session with dedicated software. ARIA structure and keyboard
  operation were checked.
- No measured contrast audit with a tool. The contrast ratios in the token
  comments were calculated from the hex values.
- The palette's colour-vision safety relies on the Tableau-derived set and on
  semantic anchors. It was not simulated.
- One unrelated fixture error was seen in
  `tests/test_prescribed_natural_current_exports.py`, during world setup in
  `resource_access_validation.py`, before any UI code runs.

## Second pass: the world view

A second review focused on the map itself: how it is drawn with three.js, how
people move around the world, and whether what it shows is precise.

### What was wrong

| Area | Problem | Why it mattered |
|---|---|---|
| Navigation | Stock `OrbitControls`: constant-angle orbit, and in flat projections a drag *rotated* the plane in 3D | The globe slid under the pointer near the limb, and flat maps tilted instead of panning |
| Projection switch | The camera jumped to a fixed pose | You lost the place you were looking at |
| Selection | No visible hovered or selected cell | You could not tell which cell the readout described |
| Rendering | The loop redrew every frame even when nothing moved; device pixel ratio uncapped | Constant GPU and battery load; 9× the pixels on 3× screens |
| Mesh overlay | The wireframe drew the fan triangulation (spokes and diagonals), not cell borders | It showed an artefact of the renderer, not the cells |
| Identifiers | About 55 `*_id` / `flow_to` layers were drawn with the Viridis ramp | A ramp implies order: plate 7 looked "more" than plate 6 |
| Signed and elevation fields | Everything used Viridis | Sea level and zero were invisible; ocean and land read the same |
| Constant fields | `min == max` was drawn as the bottom of an invented `v … v+1` range | The legend promised a range that does not exist |
| Mollweide | A fixed 8-step Newton solve stalled next to the poles | 0.1° latitude error at 89.9°, in the mesh cache and both renderers |
| Keyboard | No way to move or zoom the map without a pointer | WCAG 2.1.1 and 2.5.7 |
| Stale size | Layout changes that were not window resizes left the camera aspect stale | Squashed, off-centre globe on first load at phone size |

### What the research recommended, and what was done

| Practice | Source | Implementation |
|---|---|---|
| Grab the surface when dragging, orbit off the globe; north stays up | MapLibre GL JS (`versorSetLocationAtPoint`), CesiumJS `ScreenSpaceCameraController` | `map-navigation.js`: difference of the latitude/longitude under the pointer, with a pixel-rate fallback |
| Release inertia | MapLibre `handler_inertia.ts`: linearity 0.3, 1400 px/s cap, 2500 px/s² | Same constants, 60 ms velocity window |
| Zoom toward the pointer; pinch; double-click ±1 level | MapLibre scroll, click and touch handlers | Exact on flat maps, re-grabbed on the globe |
| Smooth long moves | van Wijk & Nuij (2003); d3 `interpolateZoom`; MapLibre `flyTo` (ρ = 1.42, speed 1.2) | `zoomPath()` along the great circle |
| Keep the centre across projections | MapLibre/Mapbox globe ↔ Mercator share one camera centre | One geographic view (centre + span) drives both cameras; the camera follows the morph |
| Map keyboard, focus-scoped | MapLibre `KeyboardHandler`; WCAG 2.1.1, 2.1.4, 2.5.7 | Arrows 100 px, `+`/`-` one level, `0` fit, 300 ms `t(2 − t)`; buttons for single-pointer zoom |
| Render on demand, cap DPR at 2 | three.js manual *Rendering on demand*; react-three-fiber default `dpr [1, 2]` | `requestRender()`; idle map draws 0 frames (was ~60/s) |
| GPU picking with asynchronous readback | three.js manual *Picking*; `readRenderTargetPixelsAsync` (r165) | Full-size ID target per camera change, async hover reads |
| Constant-width outlines and highlight in the shader | Bærentzen et al. (2006) single-pass wireframe | Distance-to-boundary from one fan attribute; amber selection, white hover |
| Colour by data type: sequential, diverging about a meaningful 0, split at sea level, categorical for labels | Crameri, Shephard & Heron (2020); Moreland (2009); Kovesi (2015) | `colormaps.js` + `scripts/generate_colormaps.py`, mirrored in the CLI exporter |
| Robust range with extend triangles; one scale across time | xarray `robust=True`; matplotlib `extend` | Kept, with triangles in the ramp's own end colours |
| Nice ticks; histogram under the colour bar | Heckbert (1990); PySAL legendgram; ArcGIS ColorSlider | Area-weighted histogram, hovered-value caret |
| Keep quantitative colours unlit; offer shading as a toggle | Moreland; Kovesi; Ware (2025) | Relief is off by default and normalised so level ground is exact |
| Hillshade light from 315°, 45° | Esri *How Hillshade works* | Same, with data-driven vertical exaggeration |
| Scale bar measured between two screen points | MapLibre `ScaleControl` | Measured on the planet at the centre; hidden on whole-world views |
| Coordinates latitude first, precision matched to the data | ISO 6709; decimal-degree precision | 1 dp for a 350 km mesh, 2 dp below ~110 km |

### How it was verified

- **Picking matches geometry.** For 500 random screen points per projection, the
  GPU-picked cell was compared with the nearest cell centre to the
  ray-intersected latitude/longitude (on a spherical Voronoi mesh they must
  agree). Globe 366/375 exact, equirectangular 487/500, Mollweide 489/498. All
  other samples but two lay within 0.23° of a cell boundary (pixel
  quantisation). The two exceptions (0.3° and 0.5°) come from cell edges drawn as
  straight lines near the pole on the flat map and near the globe's limb.
- **The planet is consistent.** The 4,096 cell areas sum to 4πR² with
  R = 6371.000001 km against the declared 6371 km (2·10⁻¹⁰ relative), shown as
  `R 6,371 km ✓` in the layer panel.
- **Mollweide.** The new solver's latitude round trip is within 1.7·10⁻¹¹°
  over −90…90° in JavaScript and Python (was 0.17° at 89.99°).
- **Browser and CLI draw the same colours.** `tests/fixtures/colormap_scale_cases.json`
  (ten cases, 30 sampled colours) passes against `colormaps.js` and
  `debug_map_export.py`. A further test regenerates the tables and checks they
  match `colormaps.js`, and another checks their lightness ordering.
- **Legend caret.** The caret for a hovered −4401 m cell sat at 15.4 %, which is
  0.5·(−4401 + 6360)/6360 on the terrain scale.
- **Render on demand.** 0 frames drawn in 1.5 s of idle.
- **Tests.** 118 UI tests, and the export, parity, server and mesh suites, pass.

## Follow-ups worth considering

- Compare several pinned cells side by side in the inspector.
- Show typical runtimes per profile from past jobs (as ranges, never ETAs).
- Persist job history across server restarts.
- Tell *not applicable* apart from *unavailable* on the map, for example with a
  hatch. The value texture currently carries a single missing sentinel.
- Draw cell edges as great-circle arcs in flat projections near the poles, and
  apply the new Mollweide solver to `render` / `render-raster` (`svg_map.py`,
  `raster_map.py`), which still use the fixed 8-step solve.
- Add a cyclic colour map for angle layers if the world ever exports one.

## Sources

- NN/g — [empty states](https://www.nngroup.com/articles/empty-state-interface-design/), [progress indicators](https://www.nngroup.com/articles/progress-indicators/), [wizards](https://www.nngroup.com/articles/wizards/), [progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/)
- Grafana Saga — [navigation patterns](https://grafana.com/developers/saga/patterns/navigation)
- W3C — [WCAG 2.2](https://www.w3.org/TR/WCAG22/), [character key shortcuts](https://www.w3.org/WAI/WCAG21/Understanding/character-key-shortcuts)
- Carbon — [notifications](https://carbondesignsystem.com/components/notification/usage/)
- matplotlib — [choosing colormaps](https://matplotlib.org/stable/users/explain/colors/colormaps.html); Crameri et al., [The misuse of colour in science communication](https://www.nature.com/articles/s41467-020-19160-7)
- Beck et al. (2018), [Present and future Köppen-Geiger climate classification maps](https://www.nature.com/articles/sdata2018214)
- Evil Martians — [100 dev-tool landing pages](https://evilmartians.com/chronicles/we-studied-100-devtool-landing-pages-here-is-what-actually-works-in-2025)
- [Diátaxis](https://diataxis.fr/), [Make a README](https://www.makeareadme.com/), [Google developer style guide](https://developers.google.com/style)
- van Wijk & Nuij (2003), [Smooth and efficient zooming and panning](https://research.tue.nl/en/publications/smooth-and-efficient-zooming-and-panning/); d3 [`interpolateZoom`](https://github.com/d3/d3-interpolate/blob/main/src/zoom.js); Reach & North (2018), [Smooth, efficient, and interruptible zooming and panning](https://arxiv.org/abs/1801.09358)
- MapLibre GL JS source — [handlers](https://github.com/maplibre/maplibre-gl-js/tree/main/src/ui/handler) (inertia, keyboard, scroll, click, touch), [`camera.ts`](https://github.com/maplibre/maplibre-gl-js/blob/main/src/ui/camera.ts), [`scale_control.ts`](https://github.com/maplibre/maplibre-gl-js/blob/main/src/ui/control/scale_control.ts)
- CesiumJS — [ScreenSpaceCameraController](https://cesium.com/learn/cesiumjs/ref-doc/ScreenSpaceCameraController.html); globe.gl / [three-globe](https://github.com/vasturiano/three-globe) atmosphere
- three.js manual — [Rendering on demand](https://threejs.org/manual/#en/rendering-on-demand), [Picking](https://threejs.org/manual/#en/picking), [Color management](https://threejs.org/manual/#en/color-management), [Disposing](https://threejs.org/manual/#en/how-to-dispose-of-objects); [r165 release notes](https://github.com/mrdoob/three.js/releases/tag/r165)
- Bærentzen et al. (2006), [Single-pass wireframe rendering](https://dl.acm.org/doi/10.1145/1179849.1180035)
- Moreland (2009), [Diverging color maps for scientific visualization](https://www.kennethmoreland.com/color-maps/); Kovesi (2015), [Good colour maps](https://arxiv.org/abs/1509.03700); Nuñez et al. (2018), [cividis](https://doi.org/10.1371/journal.pone.0199239); Ware (2025), [colour and shape](https://doi.org/10.1109/TVCG.2024.3383336)
- Heckbert (1990), *Nice numbers for graph labels*, Graphics Gems; [PySAL legendgram](https://github.com/pysal/legendgram)
- Esri — [How Hillshade works](https://pro.arcgis.com/en/pro-app/latest/tool-reference/3d-analyst/how-hillshade-works.htm)
- W3C — [Keyboard](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html), [Dragging movements](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html); [Maps for HTML WCAG evaluation](https://github.com/Malvoz/web-maps-wcag-evaluation)
- ISO 6709 (coordinate representation); [PROJ eqc](https://proj.org/en/stable/operations/projections/eqc.html) (equirectangular scale)
