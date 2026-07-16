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
const EXACT_UNITS = {
  crust_density: ['g/cm³', 'Bulk density (grams per cubic centimetre).'],
};

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
  ['_index', 'index', 'Dimensionless index (usually 0–1; signed for convergence/divergence-style quantities).'],
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
    // `_edge_count` fields are graph-degree counts (e.g. hillslope sediment
    // routing edges), the same static-topology family as neighbour counts.
    test: (n) => n.endsWith('_edge_count') || n === 'boundary_vertex_count' || n.endsWith('neighbor_boundary_segment_count'),
    role: 'diagnostic',
    doc: 'Topology count — how many of the cell\'s mesh neighbours/edges meet the named condition (e.g. cross a land/water or biome boundary, or carry a routing edge). A static property of the mesh + classification, not an event tally.',
  },
  {
    test: (n) => n.endsWith('_event_count') || n.endsWith('_transfer_count') || n.endsWith('_path_count'),
    role: 'diagnostic',
    doc: 'Bookkeeping counter — how many times an event/transfer/path touched this cell during the simulation. Useful for spotting hot spots and verifying conservation, not a physical quantity.',
  },
  {
    // Deliberately narrow: `mass_balance` alone would misclassify real fluxes
    // like ice_surface_mass_balance_m_y (accumulation − ablation).
    test: (n) => n.includes('residual') || n.includes('consistency'),
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
    doc: 'Derived index — typically normalised 0–1 where higher means "more" of the named property, but convergence/divergence-style indices are signed around 0 (check the value range below). Built by a Python enricher from the physical fields; good for ranking cells, not an absolute measurement.',
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

// Curated docs, keyed by the bare field name (matches any source). The first
// block covers the fields a user reaches for first; the domain catalog below
// it holds the per-subsystem one-liners. Convention-following fields that are
// absent here still resolve through the pattern and unit rules.
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
  crust_age_ma: 'Current procedural crust-state age in Ma after remap and maturation rules. This replay root is serialized with binary64 round-trip precision. It is not a reconstructed geological creation age or proof of a ridge-to-subduction flowline.',
  lithology: 'Dominant rock type (basalt, granite, limestone, …). NOTE: the per-stage history serializes lithology as numeric codes 0–6, while this cell layer uses names; the code order is alphabetical here and may not match the engine enum (see layers_review.md F3).',
  soil_type: 'Soil classification from climate, parent material, and drainage.',
  resource: 'Dominant natural-resource association for the cell (craton_iron_gold, sedimentary_fuels, …).',
  fertility: 'Agronomic fertility score combining soil, climate, and water availability.',
  sediment_thickness_m: 'Accumulated sediment column thickness in metres.',
  ice_thickness_m: 'Ice-sheet / glacier thickness in metres.',
  water_depth_m: 'Water column depth (bathymetry for ocean, lake depth for lakes) in metres. One value represents the entire coarse control volume; it does not resolve subcell shelf, slope, coastline, or strait geometry.',
  lake_fill_fraction: 'How full a lake basin is relative to its spill level at the end of the water-budget solve. Usually 0–1; values above 1 mark transiently overfilled basins.',
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
  crust_density: 'Bulk crust density in g/cm³, serialized with binary64 round-trip precision; oceanic crust is denser than continental.',
  erosion_rate: 'Local stream-power response in depth per 5 Ma reference step; applied incision is timestep-scaled.',
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

  // --- Domain catalog (merged from the retired docs.js module) ---------
  // Terrain
  island_class: 'Size classification of the containing landmass (continent, island, islet, …).',
  distance_to_marine_water_km: 'Great-circle distance to the nearest marine (non-lake) water cell.',
  // Tectonics
  initial_plate_id: 'Plate assignment at initialization, before any plate reorganization events.',
  crust_thickness_km: 'Crustal thickness; thick under orogens, thin under ridges.',
  boundary_type: 'Dominant plate-boundary regime affecting the cell (convergent, divergent, transform, none).',
  boundary_convergent: 'Strength of convergent-boundary influence on this cell.',
  boundary_divergent: 'Strength of divergent-boundary influence on this cell.',
  boundary_transform: 'Strength of transform-boundary influence on this cell.',
  cumulative_tectonic_elevation_change_m: 'Net elevation change contributed by tectonics over the whole run. Each step is the full gain-1 isostatic change plus full gain-1 thermal-target change plus only the bounded dynamic-relief term.',
  initial_isostatic_elevation_m: 'Initial local crustal isostatic-equilibrium elevation contribution. Later changes are applied in full outside the dynamic-relief clamp.',
  thermal_subsidence_target_m: 'Current relative oceanic age–depth equilibrium target. Its full step-to-step change is applied outside the bounded dynamic-relief clamp; the field is not a separately evolved thermal-relief state.',
  continental_shelf_id: 'Identifier for a coarse marine shelf diagnostic component. At Earth reference resolution a cell is roughly 400 km across, so this does not resolve fractional shelf area or a shelf–slope–rise profile.',
  tectonic_uplift_rate_m_per_step: 'Current tectonic uplift (positive) or subsidence (negative) rate.',
  seismic_hazard_index: 'Relative earthquake hazard from boundary proximity and fault slip rates.',
  volcanic_potential_index: 'Relative likelihood of volcanism (subduction arcs, rifts, hotspots).',
  // Climate
  continentality_index: 'How continental (vs maritime) the local climate is; drives seasonal temperature range.',
  orographic_factor: 'Terrain-forced uplift enhancement of precipitation on windward slopes.',
  rain_shadow_factor: 'Precipitation suppression on lee slopes downwind of barriers.',
  top_of_atmosphere_insolation_w_m2: 'Annual-mean solar input before the atmosphere, set by latitude and orbit.',
  absorbed_shortwave_w_m2: 'Solar energy absorbed at the surface after albedo.',
  outgoing_longwave_w_m2: 'Thermal radiation emitted back to space.',
  greenhouse_trapping_w_m2: 'Longwave energy retained by the atmosphere.',
  net_radiative_balance_w_m2: 'Absorbed minus outgoing radiation; the energy the circulation must transport.',
  radiative_equilibrium_temperature_c: 'Temperature the cell would reach from local radiation balance alone.',
  no_greenhouse_equilibrium_temperature_c: 'Radiative equilibrium temperature with the greenhouse effect removed.',
  energy_balance_residual_c: 'Generated temperature minus the separately parameterized radiative-equilibrium temperature, in degrees Celsius. This is a diagnostic model mismatch, not the residual of a solved energy-closure equation and is not expected to be zero.',
  atmospheric_cell: 'Which meridional circulation cell (Hadley / Ferrel / Polar) the cell sits in.',
  cell_monsoon_index: 'Strength of monsoon-like seasonal wind reversal and precipitation contrast.',
  surface_albedo_index: 'Surface reflectivity driven by ice, desert, vegetation, and water.',
  // Ocean
  ocean_current_temperature_c: 'Water temperature carried by the surface current (warm/cold current signature).',
  ocean_current_regime: 'Classification of the local current (gyre limb, boundary current, drift, …).',
  ocean_upwelling_index: 'Upwelling strength; high values mark nutrient-rich coasts.',
  ocean_heat_transport_index: 'Net poleward heat delivery by ocean currents, moderating nearby coasts.',
  fishery_productivity_index: 'Marine biological productivity from upwelling, shelf area, and currents.',
  // Hydrology
  runoff_mm_y: 'Annual runoff generated in the cell (precipitation minus evapotranspiration and infiltration losses).',
  infiltration_mm_y: 'Annual water infiltrating into the subsurface.',
  potential_evapotranspiration_mm_y: 'Atmospheric demand for water (energy-limited evaporation).',
  actual_evapotranspiration_mm_y: 'Realized evapotranspiration (limited by available water).',
  water_body_type: 'Ocean / lake / land classification of the cell.',
  lake_basin_id: 'Lake basin the cell belongs to, when inside a lake system.',
  depression_policy: 'How the depression containing this cell was resolved (preserved, filled, breached, …).',
  depression_depth_m: 'Depth of the enclosing depression below its spill elevation.',
  spill_elevation_m: 'Elevation of the depression\'s outlet sill.',
  bankfull_discharge_m3_s: 'Channel-forming discharge of the river through this cell.',
  river_channel_width_m: 'Modeled bankfull channel width.',
  river_channel_depth_m: 'Modeled bankfull channel depth.',
  bed_shear_stress_pa: 'Shear stress exerted on the channel bed; drives sediment entrainment.',
  stream_power_index: 'Erosive capacity of the flow (slope × discharge).',
  river_capture_risk: 'Likelihood that a neighboring basin captures this drainage in future evolution.',
  river_avulsion_risk: 'Likelihood the channel jumps its banks and reroutes across the floodplain.',
  // Groundwater
  groundwater_recharge_mm_y: 'Annual recharge reaching the water table.',
  groundwater_discharge_mm_y: 'Annual groundwater discharge back to the surface (springs, baseflow).',
  groundwater_hydraulic_head_m: 'Water-table elevation driving lateral groundwater flow.',
  groundwater_flow_to_cell_id: 'Downgradient cell receiving this cell\'s lateral groundwater flow.',
  aquifer_class: 'Aquifer classification from lithology and structure.',
  aquifer_productivity_index: 'How readily the aquifer yields water.',
  baseflow_support_index: 'How strongly groundwater sustains dry-season river flow.',
  karst_potential_index: 'Susceptibility to karstification (carbonate lithology + water).',
  cave_development_index: 'Modeled cave-system development intensity.',
  // Cryosphere
  ice_velocity_m_y: 'Ice surface flow speed.',
  ice_surface_mass_balance_m_y: 'Accumulation minus ablation at the ice surface; positive feeds the glacier.',
  glacier_flow_to: 'Downstream cell receiving this cell\'s ice flux.',
  glacial_erosion_m: 'Total bedrock eroded by ice over the run.',
  moraine_deposition_m: 'Sediment deposited as moraines at ice margins.',
  permafrost_class: 'Continuous / discontinuous / sporadic / absent permafrost classification.',
  active_layer_depth_m: 'Seasonal thaw depth above permafrost.',
  deglaciation_age_ka: 'Model time since the cell became ice-free.',
  // Sediment
  sediment_deposition_m: 'Sediment deposited in the cell.',
  sediment_export_m: 'Sediment leaving the cell downstream.',
  sediment_net_budget_m: 'Deposition minus erosion — positive is net aggradation.',
  fluvial_sediment_marine_deposition_m: 'River sediment delivered to and deposited in marine cells (deltas, shelves).',
  // Soils & ecology
  soil_depth_m: 'Developed soil profile depth.',
  soil_ph: 'Soil acidity/alkalinity.',
  soil_moisture_index: 'Plant-available soil moisture.',
  soil_texture_class: 'Dominant soil texture (sand/silt/clay mixes).',
  biome_confidence_index: 'Model confidence in the biome assignment; low values flag transitional or conflicted cells.',
  ecotone_index: 'How transitional the cell is between neighboring biomes.',
  vegetation_biomass_index: 'Standing vegetation biomass.',
  primary_productivity_index: 'Net primary productivity of the ecosystem.',
  species_richness_index: 'Relative species diversity.',
  species_endemism_index: 'Concentration of range-restricted species.',
  wildfire_spread_risk_index: 'Composite wildfire spread risk from fuel, climate, and wind alignment.',
  fire_frequency_index: 'Expected wildfire recurrence frequency.',
  // Resources
  ore_genesis_potential_index: 'Combined favorability for ore formation from magmatic/hydrothermal/structural controls.',
  metallogenic_fertility_index: 'Crustal endowment favoring metal deposits.',
  petroleum_source_rock_index: 'Quality of organic-rich source rocks.',
  petroleum_accumulation_index: 'Modeled petroleum accumulation after generation, migration, and trapping.',
  mining_potential_index: 'Overall extractive potential combining ore systems and accessibility.',
  // Human geography
  agricultural_potential_index: 'Suitability for agriculture from soils, climate, and terrain.',
  culture_region_id: 'Cultural region the cell belongs to. An id layer — colors are labels.',
  language_region_id: 'Language region the cell belongs to.',
  political_region_id: 'Political region (polity) controlling the cell.',
  natural_frontier_index: 'Strength of natural barriers (mountains, deserts, straits) at this cell.',
  route_corridor_index: 'Suitability of the cell for long-distance route corridors.',
  port_suitability_index: 'Suitability for a port from harbor shelter, access, and hinterland.',
  harbor_suitability_index: 'Physical harbor quality (shelter, depth, coastline shape).',
  // Mesh & geometry
  id: 'The cell\'s own id — a coordinate-free gradient useful for checking mesh ordering.',
  // Monthly
  temperature_monthly_c: 'Monthly near-surface temperature; scrub months to watch the seasonal cycle and hemispheric phase flip.',
  precipitation_monthly_mm: 'Monthly precipitation; scrub to see monsoon bands and storm-track migration.',
  wind_monthly_east: 'Monthly eastward wind component; seasonal reversals mark monsoon circulations.',
  wind_monthly_north: 'Monthly northward wind component.',
  // Stage-history fields (hydrologic water budget)
  water_balance_mm_y: 'Per-stage water balance closure: precipitation minus evapotranspiration, runoff, and storage terms.',
  residual_mm_y: 'Unclosed remainder of the stage water budget — should be near 0; hotspots flag conservation bugs.',
  local_relief_m: 'Relief within the cell\'s neighborhood at that stage.',
  // Stage-history fields (numeric depression fill)
  fill_depth_m: 'Counterfactual Priority-Flood depth for the event cell; retained for correction selection and not applied as material.',
  elevation_before_fill_m: 'Surface elevation before correction and fill-candidate evaluation.',
  elevation_after_fill_m: 'Counterfactual surface elevation under the full-fill candidate; not the applied post-correction terrain.',
  breach_excavation_depth_m: 'Depth excavated through the sill when the policy breached instead of filled.',
  breach_deposition_depth_m: 'Excavated material redeposited downstream of the breach.',
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
  numeric_depression_correction_history: {
    title: 'Depression-correction history',
    doc: 'Fine-grained correction ledger — one stage per bounded breach or explicit temporary-lake deferral. The stage count depends on the generated world. Each stage also retains the non-mutating Priority-Flood fill candidate used for comparison. Scrubbing a long history is many requests; step with `,`/`.` to inspect specific operations.',
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
  const exact = EXACT_UNITS[name];
  if (exact) return { unit: exact[0], gloss: exact[1] };
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
  if (layer.kind?.startsWith('categorical') && role === 'measurement') {
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
      categorical_stage: 'Per-stage categorical field (scrub the stage control)',
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
  if (layer.kind?.endsWith('_stage')) {
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
    unit: unitInfo ? unitInfo.unit : (layer.kind?.startsWith('categorical') ? 'category' : null),
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
    categories: layer.kind?.startsWith('categorical') ? layer.categories : null,
    kind: layer.kind,
    notes,
  };
}

// One-line tooltip for a layer-list entry.
export function layerTooltip(layer) {
  const doc = describeLayer(layer);
  const firstSentence = (doc.description.match(/^.*?\./) || [doc.description])[0];
  return doc.unit ? `${layer.id} [${doc.unit}] — ${firstSentence}` : `${layer.id} — ${firstSentence}`;
}

// Extra text the layer-list filter matches beyond `source name` — the resolved
// docs, unit, role, and (for categoricals) the class names.
export function searchTerms(layer) {
  const doc = describeLayer(layer);
  return [doc.role, doc.unit, doc.family, doc.description, ...(doc.categories || [])]
    .filter(Boolean).join(' ');
}

// Which documentation tier a layer resolves through, most specific first:
//   'curated'   — bespoke prose in CURATED
//   'pattern'   — a naming-convention rule (or being categorical)
//   'unit'      — only a unit could be inferred from the suffix
//   'generated' — pure fallback (kind + "inspect a cell for context")
export function docStatus(layer) {
  if (CURATED[layer.name]) return 'curated';
  if (PATTERN_RULES.some((rule) => rule.test(layer.name)) || layer.kind?.startsWith('categorical')) return 'pattern';
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
    title: 'Export for GPT Image',
    items: [
      ['Export PNG', 'Downloads the current camera view in the final selected projection. Enabled overlays remain visible as spatial guides.'],
      ['Prompt .md', 'Downloads a copy/paste GPT Image prompt paired to the PNG filename, with layer meaning, snapshot metadata, and an adaptive categorical or numeric colour codex.'],
      ['No automatic generation', 'The workbench only creates local PNG and Markdown downloads. It never sends the map to an image-generation API.'],
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
      ['Residuals', 'Fields with <code>residual</code> in the name should be ~0 everywhere; large values flag a budget that does not close.'],
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
