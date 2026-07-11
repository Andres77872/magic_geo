// Data-driven documentation catalog for the debugger's layers.
//
// The exporter emits ~450 layers per world; hand-writing a paragraph for each is
// neither maintainable nor useful. Instead we resolve documentation in layers of
// decreasing specificity:
//
//   1. CURATED[id]            — exact match on a layer id (the load-bearing fields)
//   2. suffix/prefix rules    — naming conventions the pipeline follows everywhere
//      (`*_id`, `*_index`, `*_mm_y`, `initial_*`, `cumulative_*`, monthly, …)
//   3. SOURCE family docs     — what the containing record family is
//   4. a generated fallback   — kind + inferred unit + value range from manifest stats
//
// Everything here is derived from the field naming conventions used across the
// engine and Python enrichers (elevation_m, *_index in [0,1], *_km3_y fluxes, …),
// so new layers get a sensible description without touching this file. When a
// layer is important enough to warrant prose, add it to CURATED.

// --- Unit inference from field-name suffixes ------------------------------
// Ordered longest-first so `_mm_y` wins over `_m`, `_m3_s` over `_s`, etc.
const UNIT_RULES = [
  ['_km3_y', 'km³/year', 'Volumetric flux (cubic kilometres per year).'],
  ['_m3_s', 'm³/s', 'Volumetric discharge (cubic metres per second).'],
  ['_m_s', 'm/s', 'Speed (metres per second).'],
  ['_mm_y', 'mm/year', 'Annual depth flux (millimetres per year).'],
  ['_m_y', 'm/year', 'Annual rate (metres per year).'],
  ['_w_m2', 'W/m²', 'Energy flux density (watts per square metre).'],
  ['_km2', 'km²', 'Area (square kilometres).'],
  ['_km3', 'km³', 'Volume (cubic kilometres).'],
  ['_km', 'km', 'Distance (kilometres).'],
  ['_hpa', 'hPa', 'Pressure (hectopascals).'],
  ['_kpa', 'kPa', 'Stress/pressure (kilopascals).'],
  ['_pa', 'Pa', 'Stress/pressure (pascals).'],
  ['_ka', 'ka', 'Age (thousands of years before present).'],
  ['_ma', 'Ma', 'Age (millions of years before present).'],
  ['_ph', 'pH', 'Acidity/alkalinity (pH scale, ~0–14).'],
  ['_deg', '°', 'Angle or geographic coordinate (degrees).'],
  ['_c', '°C', 'Temperature (degrees Celsius).'],
  ['_m3', 'm³', 'Volume (cubic metres).'],
  ['_m2', 'm²', 'Area (square metres).'],
  ['_mm', 'mm', 'Depth (millimetres).'],
  ['_m_per_step', 'm/step', 'Rate per simulation step (metres).'],
  ['_years', 'years', 'Duration (years).'],
  ['_months', 'months', 'Count of months (0–12).'],
  ['_count', 'count', 'Integer count.'],
  ['_fraction', 'fraction', 'Dimensionless ratio, normally 0–1.'],
  ['_index', 'index', 'Dimensionless index (usually normalised 0–1; higher = more).'],
  ['_m', 'm', 'Length/elevation/depth (metres).'],
  // Note: no bare `_y` rule — it would mislabel coordinate fields like
  // `position_3d_y` / `s2_like_y` as "per year". Genuine annual fields carry a
  // fuller suffix (`_mm_y`, `_km3_y`, `_m_y`) or are curated individually.
];

// Suffix/pattern documentation — matched after CURATED, before SOURCE docs.
// `test` receives the bare field name (no `source/` prefix).
const PATTERN_RULES = [
  {
    test: (n) => n === 'id',
    role: 'identifier',
    doc: 'Cell id (0…cell_count-1). The primary key every table joins on; also the mesh vertex index.',
  },
  {
    test: (n) => n.endsWith('_id') || n === 'flow_to' || n === 'spill_to' || n === 'glacier_flow_to' || n.endsWith('_cell_id') || n.endsWith('_basin_id'),
    role: 'identifier',
    doc: 'Identifier / graph reference — the integer labels a region, system, or points at another cell. Rendered as a numeric gradient, so neighbouring ids get neighbouring colours: read it as "same colour ≈ same group", not as a magnitude. Percentile stats on ids are not meaningful.',
  },
  {
    test: (n) => n.startsWith('initial_'),
    role: 'provenance',
    doc: 'Initial-condition snapshot captured before the geodynamic feedback loop ran. Compare against the same field without the `initial_` prefix to see net change over the simulation.',
  },
  {
    test: (n) => n.startsWith('cumulative_'),
    role: 'accumulator',
    doc: 'Running total accumulated across all simulation stages (monotonic per cell). The per-stage delta lives in the corresponding stage-history ledger.',
  },
  {
    test: (n) => n.endsWith('_neighbor_edge_count') || n === 'cell_edge_count' || n === 'boundary_vertex_count' || n.endsWith('neighbor_boundary_segment_count'),
    role: 'diagnostic',
    doc: 'Topology count — how many of the cell\'s mesh neighbours/edges meet the named condition (e.g. cross a land/water or biome boundary). A static property of the mesh + classification, not an event tally.',
  },
  {
    test: (n) => n.endsWith('_event_count') || n.endsWith('_transfer_count') || n.endsWith('_path_count') || n.endsWith('_edge_count'),
    role: 'diagnostic',
    doc: 'Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity.',
  },
  {
    test: (n) => n.includes('residual') || n.includes('mass_balance') || n.includes('consistency'),
    role: 'diagnostic',
    doc: 'Conservation residual / mass-balance check. Should sit near zero everywhere; large magnitudes flag a budget that does not close and are a debugging signal rather than terrain.',
  },
  {
    test: (n) => n.endsWith('_class') || n.endsWith('_regime') || n.endsWith('_type') || n.endsWith('_policy') || n.endsWith('_stage'),
    role: 'classification',
    doc: 'Categorical classification. Each colour is one discrete class (see the legend chips); there is no ordering implied between colours.',
  },
  {
    test: (n) => n.endsWith('_index'),
    role: 'index',
    doc: 'Derived index, normally normalised to 0–1 where higher means "more" of the named property. Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement.',
  },
  {
    test: (n) => n.endsWith('_fraction') || n.endsWith('_factor'),
    role: 'ratio',
    doc: 'Dimensionless ratio/multiplier. Fractions are typically 0–1; factors are multipliers around 1.',
  },
  {
    test: (n) => n.endsWith('_months'),
    role: 'seasonal',
    doc: 'Seasonal month count (0–12) derived from the monthly climate series.',
  },
];

// Curated docs for the fields a user actually reaches for first. Keyed by the
// bare field name (matches any source). Kept deliberately tight — the pattern
// and family layers cover the long tail.
const CURATED = {
  elevation_m: 'Surface elevation above the planetary datum, in metres. Negative below sea level. The most-used base layer; the default on load.',
  filled_elevation_m: 'Elevation after depression filling — closed basins raised to their spill level so flow routing has no sinks. Diff against `elevation_m` to see filled depressions.',
  hydrologic_surface_elevation_m: 'Elevation of the hydrologically-conditioned surface used for flow routing (post-fill/breach). The surface the water budget actually runs on.',
  initial_elevation_m: 'Elevation immediately after tectonic/isostatic setup, before erosion and the feedback loop. Diff against `elevation_m` for net landscape change.',
  temperature_c: 'Mean annual surface air temperature in °C. Monthly detail is in the `temperature_monthly_c` monthly layer.',
  precipitation_mm_y: 'Mean annual precipitation, mm/year. Monthly detail in `precipitation_monthly_mm`.',
  flow_accumulation: 'Upstream drainage area (in cell-count units) draining through each cell — the classic river-network signal. Extremely heavy-tailed: a handful of trunk cells dwarf everything, so the p2–p98 default colour scale saturates the main stems (see legend clip markers).',
  flow_to: 'Downstream neighbour each cell drains into (a cell id, or -1 at outlets/oceans). Together with `flow_accumulation` this defines the drainage network.',
  is_water: 'Whether the cell is water (ocean, sea, or lake) rather than land.',
  is_river: 'Whether river discharge through the cell exceeds the channel threshold.',
  is_lake: 'Whether the cell is part of a standing water body (lake).',
  is_closed_basin: 'Whether the cell drains to an internal sink with no path to the ocean (endorheic).',
  biome: 'Whittaker-style biome classification from temperature, moisture, and elevation.',
  climate_class: 'Köppen–Geiger climate class (Af, BWh, Cfb, ET, …). 17 classes on the earthlike run.',
  landform: 'Geomorphic landform class (mountain_belt, coastal_plain, trench, …) from elevation and tectonic context.',
  plate_id: 'Tectonic plate the cell belongs to. Identifier — colour groups plates, magnitude is meaningless.',
  crust_type: 'Crust classification (continental, oceanic, craton, orogen, …).',
  crust_age_ma: 'Age of the crust in millions of years. Oceanic crust is young at ridges and ages toward subduction zones.',
  lithology: 'Dominant rock type (basalt, granite, limestone, …). NOTE: the per-stage history serializes lithology as numeric codes 0–6, while this cell layer uses names; the code order is alphabetical here and may not match the engine enum (see layers_review.md F3).',
  soil_type: 'Soil classification from climate, parent material, and drainage.',
  resource: 'Dominant natural-resource association for the cell (craton_iron_gold, sedimentary_fuels, …).',
  fertility: 'Agronomic fertility score combining soil, climate, and water availability.',
  sediment_thickness_m: 'Accumulated sediment column thickness in metres.',
  ice_thickness_m: 'Ice-sheet / glacier thickness in metres.',
  water_depth_m: 'Water column depth (bathymetry for ocean, lake depth for lakes) in metres.',
  lake_fill_fraction: 'How full a lake basin is, 0–1, at the end of the water-budget solve.',
  basin_id: 'Drainage basin the cell belongs to. Identifier — colour groups a watershed.',
  landmass_id: 'Connected landmass (continent/island) the cell belongs to. Identifier.',
  settlement_score: 'Composite habitability/attractiveness score used to seed settlements.',
  navigability_index: 'How navigable the cell is for water/land transport, 0–1.',
  lat_deg: 'Latitude of the cell centre in degrees (−90…90).',
  lon_deg: 'Longitude of the cell centre in degrees (−180…180).',
  area_km2: 'Geodesic area of the cell in km². Near-uniform on the Fibonacci-sphere mesh.',
  cell_geometry_quality: 'Mesh-quality score for the cell polygon; low values flag distorted or self-overlapping cells worth ignoring in analysis.',
  cell_polygon_area_error_fraction: 'Relative error between the polygon area and the ideal cell area — a mesh-quality debug signal.',
  mean_neighbor_boundary_segment_mismatch_km: 'Average gap between a cell edge and its neighbour\'s matching edge. This is the documented "ring mismatch" that produces visible seams in the 2D projections; use it to judge where the approximate boundary rings disagree.',
  // Vector components — stored as separate east/north (or x/y/z) scalar layers.
  wind_east: 'Eastward (zonal) component of the mean surface wind. Positive = toward the east. Pair with `wind_north` for the full vector.',
  wind_north: 'Northward (meridional) component of the mean surface wind. Positive = toward the north. Pair with `wind_east`.',
  ocean_current_east: 'Eastward component of the surface ocean current. Pair with `ocean_current_north`.',
  ocean_current_north: 'Northward component of the surface ocean current. Pair with `ocean_current_east`.',
  mean_seasonal_wind_speed: 'Mean wind speed over the seasonal cycle (magnitude of the monthly wind vectors).',
  earthquake_recurrence_interval_y: 'Mean interval between large earthquakes, in years. Low values mark seismically active belts.',
  crust_density: 'Bulk crust density (kg/m³ scale); oceanic crust is denser than continental.',
  erosion_rate: 'Local erosion rate from the landscape-evolution solve (model units of depth per step).',
  flow_velocity_m_s: 'Channel flow velocity in m/s from the river-hydraulics solve.',
  froude_number: 'Froude number of channel flow (dimensionless): <1 subcritical, >1 supercritical. Mostly ~0 off the channel network.',
  manning_roughness_n: "Manning's roughness coefficient n for channel flow (dimensionless).",
  tectonic_zone_strength: 'Relative strength/activity of the tectonic zone influencing the cell (dimensionless).',
  is_marine: 'Whether the cell is marine (ocean/sea). In the per-stage ledger this appears as 0/1 rather than a category.',
  // Geometry: unit sphere position + surface normal, split into x/y/z scalars.
  position_3d_x: 'X component of the cell-centre position on the unit sphere (planet frame). Geometry, not a physical field.',
  position_3d_y: 'Y component of the cell-centre position on the unit sphere (planet frame). Geometry, not a physical field.',
  position_3d_z: 'Z component of the cell-centre position on the unit sphere (planet frame). Geometry, not a physical field.',
  normal_3d_x: 'X component of the cell surface normal (planet frame). Geometry, not a physical field.',
  normal_3d_y: 'Y component of the cell surface normal (planet frame). Geometry, not a physical field.',
  normal_3d_z: 'Z component of the cell surface normal (planet frame). Geometry, not a physical field.',
};

// Documentation for each record-family "source". These describe the whole group
// in the layer panel and back the "family" line in the docs card.
const SOURCE_DOCS = {
  cells: {
    title: 'Per-cell fields',
    doc: 'The wide cells table — one value per cell for the final simulation state. The bulk of the layers live here: tectonics, climate, hydrology, ecology, resources, and human geography, all keyed by cell id.',
  },
  cells_monthly: {
    title: 'Monthly climate series',
    doc: '12-value-per-cell climate series (precipitation, temperature, winds). Scrub the month control to animate the seasonal cycle. Colour scale is fixed across all 12 months so magnitudes stay comparable while scrubbing.',
  },
  hydrologic_water_budget_history: {
    title: 'Water-budget stage history',
    doc: 'Per-stage snapshots of the coupled climate–hydrology solve as the geodynamic feedback loop iterates. Scrub the stage control to watch elevation, precipitation, runoff, and the balance residual co-evolve. The colour scale spans all stages so you can see change, not re-normalisation.',
  },
  numeric_depression_fill_history: {
    title: 'Depression-fill stage history',
    doc: 'Fine-grained log of the depression fill/breach algorithm — one stage per fill or breach operation (1,600 on the earthlike run). Each stage records what a single closed-basin correction did. Scrubbing all stages is many requests; step with `,`/`.` to inspect specific operations.',
  },
};

// Role → short badge label + one-line gloss, shown as a pill on the docs card.
const ROLE_BADGES = {
  identifier: { label: 'ID', hint: 'Identifier / graph reference — colour groups, magnitude is meaningless.' },
  index: { label: 'index', hint: 'Derived index, usually normalised 0–1.' },
  ratio: { label: 'ratio', hint: 'Dimensionless ratio or multiplier.' },
  classification: { label: 'class', hint: 'Discrete categorical class.' },
  provenance: { label: 'initial', hint: 'Initial-condition snapshot before the feedback loop.' },
  accumulator: { label: 'cumulative', hint: 'Running total across all stages.' },
  diagnostic: { label: 'diagnostic', hint: 'Bookkeeping / conservation check, not a physical field.' },
  seasonal: { label: 'seasonal', hint: 'Derived from the monthly climate series.' },
  measurement: { label: 'field', hint: 'Physical measurement.' },
};

function inferUnit(name) {
  for (const [suffix, unit, gloss] of UNIT_RULES) {
    if (name.endsWith(suffix)) return { unit, gloss };
  }
  return null;
}

function formatStat(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (Number.isInteger(value) && Math.abs(value) < 1e6) return String(value);
  const abs = Math.abs(value);
  if (abs !== 0 && (abs >= 1e5 || abs < 1e-3)) return value.toExponential(2);
  return Number(value.toPrecision(4)).toString();
}

// Resolve full documentation for one manifest layer object.
// Returns { title, unit, role, roleBadge, description, family, familyDoc,
//           stats, categories, kind, notes }.
export function describeLayer(layer) {
  if (!layer) return null;
  const name = layer.name;
  const source = layer.source;
  const unitInfo = inferUnit(name);

  // Resolve role + primary description, most specific first.
  let role = 'measurement';
  const descriptionParts = [];

  const curated = CURATED[name];
  if (curated) {
    descriptionParts.push(curated);
  }

  let patternDoc = null;
  for (const rule of PATTERN_RULES) {
    if (rule.test(name)) {
      role = rule.role;
      patternDoc = rule.doc;
      break;
    }
  }
  if (layer.kind === 'categorical' && role === 'measurement') {
    role = 'classification';
    patternDoc = patternDoc
      || 'Categorical classification. Each colour is one discrete class (see legend chips); colours carry no ordering.';
  }
  if (!curated && patternDoc) {
    descriptionParts.push(patternDoc);
  } else if (curated && patternDoc && role !== 'measurement') {
    // Curated prose leads; append the convention note only if it adds something.
    if (role === 'identifier' || role === 'provenance' || role === 'accumulator') {
      descriptionParts.push(patternDoc);
    }
  }

  if (!descriptionParts.length) {
    // Pure generated fallback.
    const kindWord = {
      numeric: 'Continuous per-cell field',
      categorical: 'Categorical per-cell classification',
      numeric_stage: 'Per-stage numeric field (scrub the stage control)',
      numeric_monthly: 'Monthly numeric field (scrub the month control)',
    }[layer.kind] || 'Layer';
    descriptionParts.push(
      unitInfo
        ? `${kindWord}. ${unitInfo.gloss}`
        : `${kindWord}. No documented unit for this field — inspect a cell for context.`,
    );
  } else if (unitInfo && role === 'measurement' && !curated) {
    // Pattern fallback that also has a unit hint.
    descriptionParts.push(unitInfo.gloss);
  }

  const family = SOURCE_DOCS[source];

  const notes = [];
  if (layer.kind === 'numeric_stage') {
    notes.push(`Per-stage layer · ${layer.stage_count} stages · colour scale fixed across all stages.`);
  }
  if (layer.kind === 'numeric_monthly') {
    notes.push(`Monthly layer · ${layer.month_count || 12} months · colour scale fixed across the year.`);
  }
  if (role === 'identifier') {
    notes.push('Values are labels, not magnitudes — expect a noisy gradient.');
  }

  return {
    title: name,
    unit: unitInfo ? unitInfo.unit : (layer.kind === 'categorical' ? 'category' : null),
    role,
    roleBadge: ROLE_BADGES[role] || ROLE_BADGES.measurement,
    description: descriptionParts.join(' '),
    family: family ? family.title : source,
    familyDoc: family ? family.doc : null,
    stats: layer.stats
      ? {
          min: formatStat(layer.stats.min),
          max: formatStat(layer.stats.max),
          p2: formatStat(layer.stats.p2),
          p98: formatStat(layer.stats.p98),
        }
      : null,
    categories: layer.kind === 'categorical' ? layer.categories : null,
    kind: layer.kind,
    notes,
  };
}

export function sourceDoc(source) {
  return SOURCE_DOCS[source] || { title: source, doc: null };
}

// Which documentation tier a layer resolves through, most specific first:
//   'curated'   — bespoke prose in CURATED
//   'pattern'   — a naming-convention rule (or being categorical)
//   'unit'      — only a unit could be inferred from the suffix
//   'generated' — pure fallback (kind + "inspect a cell for context")
export function docStatus(layer) {
  if (CURATED[layer.name]) return 'curated';
  if (PATTERN_RULES.some((rule) => rule.test(layer.name)) || layer.kind === 'categorical') return 'pattern';
  if (inferUnit(layer.name)) return 'unit';
  return 'generated';
}

// Coverage report over a manifest's layers — how many resolve to curated /
// pattern / unit / generated docs. Surfaced in the help overlay so it is
// obvious when new engine output has no bespoke docs yet.
export function docsCoverage(layers) {
  const counts = { curated: 0, pattern: 0, unit: 0, generated: 0, total: layers.length };
  const byRole = {};
  for (const layer of layers) {
    byRole[layer.kind] = (byRole[layer.kind] || 0) + 1;
    counts[docStatus(layer)] += 1;
  }
  return { counts, byRole };
}

// Static UI guide shown in the help overlay. Kept here so the docs helper is the
// single source of truth for "how does this thing work".
export const UI_GUIDE = [
  {
    title: 'Layers',
    items: [
      ['Pick a layer', 'Click any entry in the left panel. Layers are grouped by source family; click a group title to collapse it.'],
      ['Search', 'Press <kbd>/</kbd> or click the filter box, then type. Matches any part of the source or field name.'],
      ['What am I looking at?', 'The docs card under the layer panel explains the active layer — unit, role, value range, and (for categoricals) the class list. Toggle it with <kbd>d</kbd>.'],
      ['Colour scale', 'Numeric layers use viridis normalised to the 2nd–98th percentile (robust to outliers). The legend shows the scale; <kbd>≥</kbd>/<kbd>≤</kbd> markers mean values beyond the ends are clipped to the end colour. Categorical layers use one colour per class.'],
      ['Missing data', 'Cells with no value render as flat grey — distinct from both ends of the colour ramp.'],
    ],
  },
  {
    title: 'Stage & month scrubbing',
    items: [
      ['Stage layers', 'Per-stage layers show a stage bar. Drag the slider, type an exact stage, or step with <kbd>,</kbd> / <kbd>.</kbd>. Neighbouring stages are prefetched.'],
      ['Monthly layers', 'Monthly climate layers show a month control (1–12) instead; the colour scale is fixed across the year so you compare, not re-normalise.'],
      ['Fixed scale', 'For both, the colour scale spans all stages/months, so what you see moving is real change in the data.'],
    ],
  },
  {
    title: 'Projection & camera',
    items: [
      ['Globe / flat', 'Switch with the top-left buttons or <kbd>1</kbd> (globe), <kbd>2</kbd> (equirectangular), <kbd>3</kbd> (Mollweide). Transitions animate in the vertex shader.'],
      ['Orbit', 'Drag to rotate, scroll to zoom, right-drag to pan (globe mode).'],
    ],
  },
  {
    title: 'Overlays',
    items: [
      ['Wireframe', '<kbd>w</kbd> — the cell mesh edges.'],
      ['Plate boundaries', '<kbd>b</kbd> — tectonic plate boundary segments.'],
      ['Graticule', '<kbd>g</kbd> — lat/lon grid lines.'],
    ],
  },
  {
    title: 'Cell inspector',
    items: [
      ['Open', 'Click any cell to open the inspector on the right with every field for that cell.'],
      ['Ledgers & monthly', 'Per-stage ledger sparklines (with a marker at the active stage) and the monthly series are drawn per cell.'],
      ['Adjacency', 'Neighbouring cells are listed with edge flags (plate boundary, land/water, biome transition); click a neighbour to jump to it.'],
      ['Filter fields', 'The filter box narrows the ~400 fields by name.'],
    ],
  },
  {
    title: 'Reading the data honestly',
    items: [
      ['Identifiers', 'Fields ending in <code>_id</code> (and <code>flow_to</code>/<code>spill_to</code>) are labels. The gradient is meaningless — read it as "same colour ≈ same group".'],
      ['Indices vs measurements', 'Fields ending in <code>_index</code> are derived, normally 0–1; fields with unit suffixes (<code>_m</code>, <code>_mm_y</code>, <code>_c</code>…) are physical quantities.'],
      ['Residuals', 'Fields with <code>residual</code> / <code>mass_balance</code> should be ~0 everywhere; large values flag a budget that does not close.'],
      ['Ring seams', 'Visible gaps between cells in the flat projections are the documented boundary-ring mismatch, not a rendering bug — inspect <code>mean_neighbor_boundary_segment_mismatch_km</code>.'],
    ],
  },
];

export const KEY_REFERENCE = [
  ['/', 'Focus the layer search'],
  ['d', 'Toggle the layer docs card'],
  ['?', 'Toggle this help overlay'],
  ['1 / 2 / 3', 'Globe / equirectangular / Mollweide'],
  [', / .', 'Previous / next stage (or month)'],
  ['w / b / g', 'Wireframe / plate boundaries / graticule'],
  ['Esc', 'Close help or the cell inspector'],
];
