// Layer & UI documentation helper for the magic-geo debugger.
//
// Everything here is derived from three inputs, in priority order:
//   1. LAYER_DOCS   — curated one-liners for canonical field names,
//   2. TOPIC_RULES  — subsystem blurbs matched by field-name prefix,
//   3. UNIT_RULES   — units inferred from the project's suffix conventions.
// Unknown fields still get a useful doc card from rules 2–3, so new engine
// output is documented-by-convention without touching this module.

// ---------------------------------------------------------------------------
// Layer kinds

export const KIND_DOCS = {
  numeric: {
    label: 'numeric',
    doc: 'One static value per cell, colored with the viridis ramp. The legend '
      + 'spans the robust p2–p98 range of the data, so the darkest/brightest '
      + 'colors saturate at the 2nd/98th percentile — outliers are clamped, '
      + 'not hidden (hover a cell to read its exact value).',
  },
  categorical: {
    label: 'categorical',
    doc: 'One category per cell (strings or booleans, at most 64 distinct '
      + 'values), mapped to golden-angle hues. The legend lists every '
      + 'category with its color chip. Cells whose value is missing render '
      + 'as the dark background.',
  },
  numeric_monthly: {
    label: 'monthly',
    doc: 'Twelve values per cell, one per model month. The bottom slider '
      + 'scrubs months (also , and . keys). The legend range covers all 12 '
      + 'months at once so colors stay comparable while scrubbing.',
  },
  numeric_stage: {
    label: 'per-stage',
    doc: 'One value per cell per simulation stage from a stage-history '
      + 'ledger. The bottom slider scrubs stages (also , and . keys); '
      + 'neighboring stages are prefetched. The legend range covers all '
      + 'stages at once so change over time reads as change in color.',
  },
};

// ---------------------------------------------------------------------------
// Units inferred from field-name suffixes (first match wins)

const UNIT_RULES = [
  [/_w_m2$/, 'W/m²', 'energy flux density'],
  [/_m3_s$/, 'm³/s', 'volumetric discharge'],
  [/_m_s$/, 'm/s', 'velocity'],
  [/_m_y$/, 'm/yr', 'rate of change'],
  [/_m_per_step$/, 'm/step', 'rate per simulation step'],
  [/_km3_y$/, 'km³/yr', 'volumetric flux'],
  [/_km3$/, 'km³', 'volume'],
  [/_km2$/, 'km²', 'area'],
  [/_km$/, 'km', 'distance'],
  [/_mm_y$/, 'mm/yr', 'water-equivalent depth per year'],
  [/_mm$/, 'mm', 'water-equivalent depth'],
  [/_kpa$/, 'kPa', 'pressure'],
  [/_hpa$/, 'hPa', 'pressure (anomaly)'],
  [/_pa$/, 'Pa', 'pressure / stress'],
  [/(_c|_monthly_c)$/, '°C', 'temperature'],
  [/_ka$/, 'ka', 'thousand years before present'],
  [/_ma$/, 'Ma', 'million years'],
  [/_y$/, 'years', 'duration / interval'],
  [/_deg$/, 'degrees', 'angle'],
  [/_ph$/, 'pH', 'acidity (≈7 neutral)'],
  [/_m$/, 'm', 'meters'],
  [/_months$/, 'months', 'count of model months'],
  [/_fraction$/, '0–1', 'fraction of a whole'],
  [/_index$/, 'index', 'dimensionless score (higher = stronger expression)'],
  [/_factor$/, 'factor', 'dimensionless multiplier'],
  [/_count$/, 'count', 'integer count'],
  [/_id$/, 'id', 'identifier — colors are arbitrary labels, not magnitudes'],
];

// ---------------------------------------------------------------------------
// Subsystem topics matched by field-name pattern (first match wins).
// Order matters: specific families come before broad ones (e.g. routes and
// ports before general hydrology, so river_mouth_port_index lands in
// Human geography, not Rivers).

const TOPIC_RULES = [
  [/^(s2_like_|healpix_like_|mesh_lod_)/, 'Spherical indexing',
    'Diagnostic ids from the S2-like / HEALPix-like spherical indexes and the '
    + 'mesh LOD hierarchy. Useful for verifying spatial-index assignment; not '
    + 'physical quantities.'],
  [/^(id$|lat_deg$|lon_deg$|position_3d_|normal_3d_|area_km2$|cell_|boundary_vertex_count$|mean_neighbor_|max_neighbor_|land_water_neighbor_|tectonic_neighbor_|biome_transition_neighbor_)/,
    'Mesh & geometry',
    'Cell-center coordinates, polygon geometry, and mesh-quality metrics. The '
    + 'boundary-segment mismatch metrics quantify the documented ring seams '
    + 'visible between cell polygons.'],
  [/^initial_/, 'Initial terrain components',
    'Additive uplift/subsidence contributions from tectonic initialization '
    + 'that sum into initial_elevation_m — the pre-erosion starting surface.'],
  [/^(plate_|crust_|boundary_(convergent|divergent|transform|type)|collision_zone_|subduction_zone_|rift_zone_|tectonic_|cumulative_tectonic_|cumulative_crust_|oceanic_crust_|last_plate_|last_crust_|earthquake_|seismic_|fault_|volcanic_|hydrothermal_|dominant_tectonic_)/,
    'Tectonics & crust',
    'Plate layout, crust properties, boundary regimes, and seismic/volcanic '
    + 'hazard derived from the plate-kinematic model.'],
  [/^(ice_|glacier_|glacial_|basal_sliding_|moraine_|deglaciation_|permafrost_|active_layer_depth_|ground_ice_)/,
    'Cryosphere',
    'Ice sheets and glaciers: thickness, flow, mass balance, glacial '
    + 'erosion/deposition and landforms, plus permafrost state.'],
  [/^(groundwater_|aquifer_|vadose_|spring_discharge_|subterranean_|baseflow_)/,
    'Groundwater & aquifers',
    'Recharge, storage, lateral flow, and discharge of the groundwater '
    + 'system, plus aquifer classification and productivity.'],
  [/^(karst_|cave_)/, 'Karst',
    'Carbonate dissolution features: karstification potential, cave '
    + 'development, and karst drainage systems.'],
  [/^reef_/, 'Reefs',
    'Reef growth and stress model: growth potential, wave exposure, '
    + 'bleaching and sediment stress, island support.'],
  [/^wetland_/, 'Wetlands',
    'Wetland extent, hydrology, soil saturation, and connectivity.'],
  [/^(wildfire_|fire_frequency_)/, 'Wildfire',
    'Fire regime model: ignition potential, fuel continuity, spread risk, '
    + 'and natural firebreaks.'],
  [/^(sediment_|erosion_rate$|fluvial_sediment_|hillslope_sediment_)/,
    'Erosion & sediment',
    'Sediment production, routing, and deposition budgets (all depths are '
    + 'water-column-equivalent meters over the cell).'],
  [/^(soil_|fertility$)/, 'Soils',
    'Soil development: depth, texture, chemistry, moisture, and fertility.'],
  [/^(resource$|ore_|metallogenic_|mining_|placer_|petroleum_)/,
    'Resources & economic geology',
    'Mineral and petroleum systems: ore genesis, placer concentration, '
    + 'source rocks, migration, traps, and mining potential.'],
  [/^(settlement_|agricultural_|culture_|language_|political_|natural_frontier_|route_|transport_chokepoint_|navigab|navigable_|port_|harbor_|protected_bay_|strait_access_|coastal_route_|river_valley_route_|mountain_pass_route_|oasis_route_|river_mouth_port_|coastal_navigability_|river_navigability_)/,
    'Human geography',
    'Settlement suitability, cultural/political regions, natural frontiers, '
    + 'route corridors, navigability, and port siting.'],
  [/^(ocean_|marine_|fishery_|continental_shelf_|upwind_ocean_fetch_)/,
    'Ocean & marine',
    'Ocean currents and derived transport, marine regions, upwelling, and '
    + 'fishery productivity.'],
  [/^(temperature_|precipitation_|wind_|absorbed_|outgoing_|greenhouse_|net_radiative_|radiative_|no_greenhouse_|energy_balance_|top_of_atmosphere_|peak_seasonal_|low_seasonal_|seasonal_|climate_|climatic_|continentality_|cell_monsoon_|dry_season_|wet_season_|frost_months$|growing_season_|orographic_|rain_shadow_|advected_moisture_|humidity_|moisture_|vapor_|oceanic_humidity_|surface_pressure_|surface_albedo_|orbital_|atmospheric_cell$|mean_seasonal_wind_|wind_divergence_|vertical_velocity_)/,
    'Climate & atmosphere',
    'Energy balance, circulation, temperature, precipitation, and seasonal '
    + 'regime diagnostics from the climate model.'],
  [/^(flow_|runoff_|infiltration_|potential_evapotranspiration_|actual_evapotranspiration_|hydrologic_|is_river$|is_lake$|is_water$|is_closed_basin$|lake_|water_body_|water_budget_|water_depth_|basin_id$|depression_|spill_|equal_filled_|numeric_depression_|cumulative_numeric_depression_|overflow_channel_|river_|bankfull_|froude_|hydraulic_|manning_|bed_shear_|channel_|stream_power_|floodplain_|distance_to_marine_)/,
    'Surface hydrology & rivers',
    'Flow routing on the conditioned surface, water budgets, lakes and '
    + 'depressions, and river-channel hydraulics.'],
  [/^(biome|ecotone_|vegetation_|forest_|primary_productivity_|species_|dominant_species_|ecosystem_)/,
    'Biomes & ecology',
    'Biome classification, ecotones, vegetation dynamics, and species '
    + 'richness/range diagnostics.'],
  [/^(elevation_m$|filled_elevation_m$|landform$|landmass_id$|island_class$)/,
    'Terrain',
    'The elevation surface and derived landform classification.'],
];

// ---------------------------------------------------------------------------
// Curated docs for canonical fields (fall back to rules above when absent)

export const LAYER_DOCS = {
  // Terrain
  elevation_m: 'Final surface elevation relative to sea level, after all tectonic, erosion, and feedback stages. The default layer on load.',
  initial_elevation_m: 'Pre-erosion starting surface from tectonic initialization — the sum of the initial_* uplift/subsidence components.',
  filled_elevation_m: 'Elevation after depression filling — the hydrologically conditioned surface used for flow routing. Compare with elevation_m to see filled sinks.',
  hydrologic_surface_elevation_m: 'The exact surface the flow router ran on (filled/breached per the depression policy).',
  water_depth_m: 'Water column depth for ocean and lake cells (0 on land).',
  landform: 'Categorical landform classification (plains, hills, mountains, …) derived from elevation and relief.',
  landmass_id: 'Connected-component id of the landmass this cell belongs to; ocean cells share no landmass.',
  island_class: 'Size classification of the containing landmass (continent, island, islet, …).',
  distance_to_marine_water_km: 'Great-circle distance to the nearest marine (non-lake) water cell.',

  // Tectonics
  plate_id: 'Tectonic plate the cell currently belongs to. Colors are arbitrary plate labels.',
  initial_plate_id: 'Plate assignment at initialization, before any plate reorganization events.',
  crust_type: 'Continental vs oceanic crust.',
  crust_age_ma: 'Crust age in million years; young crust hugs spreading ridges.',
  crust_thickness_km: 'Crustal thickness; thick under orogens, thin under ridges.',
  crust_density: 'Relative crust density driving isostatic elevation.',
  boundary_type: 'Dominant plate-boundary regime affecting the cell (convergent, divergent, transform, none).',
  boundary_convergent: 'Strength of convergent-boundary influence on this cell.',
  boundary_divergent: 'Strength of divergent-boundary influence on this cell.',
  boundary_transform: 'Strength of transform-boundary influence on this cell.',
  cumulative_tectonic_elevation_change_m: 'Net elevation change contributed by tectonics over the whole run.',
  tectonic_uplift_rate_m_per_step: 'Current tectonic uplift (positive) or subsidence (negative) rate.',
  seismic_hazard_index: 'Relative earthquake hazard from boundary proximity and fault slip rates.',
  earthquake_recurrence_interval_y: 'Model estimate of years between significant earthquakes.',
  volcanic_potential_index: 'Relative likelihood of volcanism (subduction arcs, rifts, hotspots).',

  // Climate
  temperature_c: 'Mean annual near-surface air temperature.',
  precipitation_mm_y: 'Mean annual precipitation.',
  wind_east: 'Eastward component of the prevailing near-surface wind.',
  wind_north: 'Northward component of the prevailing near-surface wind.',
  climate_class: 'Köppen-like climate classification from temperature and precipitation seasonality.',
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
  energy_balance_residual_c: 'Difference between the energy-balance temperature and the generated temperature — a model-consistency diagnostic (should be near 0).',
  atmospheric_cell: 'Which meridional circulation cell (Hadley / Ferrel / Polar) the cell sits in.',
  cell_monsoon_index: 'Strength of monsoon-like seasonal wind reversal and precipitation contrast.',
  surface_albedo_index: 'Surface reflectivity driven by ice, desert, vegetation, and water.',

  // Ocean
  ocean_current_east: 'Eastward component of the surface ocean current.',
  ocean_current_north: 'Northward component of the surface ocean current.',
  ocean_current_temperature_c: 'Water temperature carried by the surface current (warm/cold current signature).',
  ocean_current_regime: 'Classification of the local current (gyre limb, boundary current, drift, …).',
  ocean_upwelling_index: 'Upwelling strength; high values mark nutrient-rich coasts.',
  ocean_heat_transport_index: 'Net poleward heat delivery by ocean currents, moderating nearby coasts.',
  fishery_productivity_index: 'Marine biological productivity from upwelling, shelf area, and currents.',

  // Hydrology
  flow_to: 'Cell id of the downhill flow receiver on the conditioned surface. An id layer — use the inspector for exact targets.',
  flow_accumulation: 'Count of upstream cells draining through this cell. Heavily skewed: rivers are the bright filaments; the p2–p98 legend clamp is doing real work here.',
  runoff_mm_y: 'Annual runoff generated in the cell (precipitation minus evapotranspiration and infiltration losses).',
  infiltration_mm_y: 'Annual water infiltrating into the subsurface.',
  potential_evapotranspiration_mm_y: 'Atmospheric demand for water (energy-limited evaporation).',
  actual_evapotranspiration_mm_y: 'Realized evapotranspiration (limited by available water).',
  is_water: 'Water vs land mask (oceans and lakes).',
  is_lake: 'Lake cells (inland water bodies).',
  is_river: 'Cells carrying a mapped river channel.',
  is_closed_basin: 'Endorheic cells: their drainage never reaches the ocean.',
  water_body_type: 'Ocean / lake / land classification of the cell.',
  basin_id: 'Drainage basin the cell drains into. An id layer — colors are labels.',
  lake_basin_id: 'Lake basin the cell belongs to, when inside a lake system.',
  lake_fill_fraction: 'How full the containing depression is relative to its spill level.',
  depression_policy: 'How the depression containing this cell was resolved (preserved, filled, breached, …).',
  depression_depth_m: 'Depth of the enclosing depression below its spill elevation.',
  spill_elevation_m: 'Elevation of the depression\'s outlet sill.',
  bankfull_discharge_m3_s: 'Channel-forming discharge of the river through this cell.',
  river_channel_width_m: 'Modeled bankfull channel width.',
  river_channel_depth_m: 'Modeled bankfull channel depth.',
  flow_velocity_m_s: 'Mean flow velocity at bankfull discharge.',
  froude_number: 'Dimensionless flow regime indicator: <1 subcritical (tranquil), >1 supercritical (rapid).',
  manning_roughness_n: 'Manning\'s n channel roughness coefficient used in the hydraulics solution.',
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
  ice_thickness_m: 'Glacier/ice-sheet thickness.',
  ice_velocity_m_y: 'Ice surface flow speed.',
  ice_surface_mass_balance_m_y: 'Accumulation minus ablation at the ice surface; positive feeds the glacier.',
  glacier_flow_to: 'Downstream cell receiving this cell\'s ice flux.',
  glacial_erosion_m: 'Total bedrock eroded by ice over the run.',
  moraine_deposition_m: 'Sediment deposited as moraines at ice margins.',
  permafrost_class: 'Continuous / discontinuous / sporadic / absent permafrost classification.',
  active_layer_depth_m: 'Seasonal thaw depth above permafrost.',
  deglaciation_age_ka: 'Model time since the cell became ice-free.',

  // Sediment
  erosion_rate: 'Instantaneous bedrock erosion rate from the stream-power law.',
  sediment_thickness_m: 'Accumulated sediment column thickness.',
  sediment_production_m: 'Sediment generated in the cell (hillslope + channel erosion).',
  sediment_deposition_m: 'Sediment deposited in the cell.',
  sediment_export_m: 'Sediment leaving the cell downstream.',
  sediment_net_budget_m: 'Deposition minus erosion — positive is net aggradation.',
  fluvial_sediment_marine_deposition_m: 'River sediment delivered to and deposited in marine cells (deltas, shelves).',

  // Soils & ecology
  soil_depth_m: 'Developed soil profile depth.',
  soil_ph: 'Soil acidity/alkalinity.',
  soil_moisture_index: 'Plant-available soil moisture.',
  soil_texture_class: 'Dominant soil texture (sand/silt/clay mixes).',
  fertility: 'Composite agricultural fertility of the soil.',
  biome: 'Final biome classification from climate, soils, and hydrology.',
  biome_confidence_index: 'Model confidence in the biome assignment; low values flag transitional or conflicted cells.',
  ecotone_index: 'How transitional the cell is between neighboring biomes.',
  vegetation_biomass_index: 'Standing vegetation biomass.',
  primary_productivity_index: 'Net primary productivity of the ecosystem.',
  species_richness_index: 'Relative species diversity.',
  species_endemism_index: 'Concentration of range-restricted species.',
  wildfire_spread_risk_index: 'Composite wildfire spread risk from fuel, climate, and wind alignment.',
  fire_frequency_index: 'Expected wildfire recurrence frequency.',

  // Resources
  resource: 'Dominant discovered resource type in the cell.',
  ore_genesis_potential_index: 'Combined favorability for ore formation from magmatic/hydrothermal/structural controls.',
  metallogenic_fertility_index: 'Crustal endowment favoring metal deposits.',
  petroleum_source_rock_index: 'Quality of organic-rich source rocks.',
  petroleum_accumulation_index: 'Modeled petroleum accumulation after generation, migration, and trapping.',
  mining_potential_index: 'Overall extractive potential combining ore systems and accessibility.',

  // Human geography
  settlement_score: 'Composite habitability/settlement suitability (water, fertility, climate, access).',
  agricultural_potential_index: 'Suitability for agriculture from soils, climate, and terrain.',
  culture_region_id: 'Cultural region the cell belongs to. An id layer — colors are labels.',
  language_region_id: 'Language region the cell belongs to.',
  political_region_id: 'Political region (polity) controlling the cell.',
  natural_frontier_index: 'Strength of natural barriers (mountains, deserts, straits) at this cell.',
  route_corridor_index: 'Suitability of the cell for long-distance route corridors.',
  navigability_index: 'Overall navigability for water transport.',
  port_suitability_index: 'Suitability for a port from harbor shelter, access, and hinterland.',
  harbor_suitability_index: 'Physical harbor quality (shelter, depth, coastline shape).',

  // Mesh & geometry
  id: 'The cell\'s own id — a coordinate-free gradient useful for checking mesh ordering.',
  lat_deg: 'Cell-center latitude.',
  lon_deg: 'Cell-center longitude.',
  area_km2: 'Cell area on the planet sphere.',
  cell_geometry_quality: 'Composite mesh-quality score for the cell polygon (1 = ideal).',
  cell_polygon_area_error_fraction: 'Relative error between the polygon ring area and the true cell area — a direct measure of the documented ring approximation.',
  mean_neighbor_boundary_segment_mismatch_km: 'Mean gap/overlap between this cell\'s ring and its neighbors\' rings — the seam metric for the visible polygon seams.',

  // Monthly
  temperature_monthly_c: 'Monthly near-surface temperature; scrub months to watch the seasonal cycle and hemispheric phase flip.',
  precipitation_monthly_mm: 'Monthly precipitation; scrub to see monsoon bands and storm-track migration.',
  wind_monthly_east: 'Monthly eastward wind component; seasonal reversals mark monsoon circulations.',
  wind_monthly_north: 'Monthly northward wind component.',

  // Stage-history fields (hydrologic water budget)
  water_balance_mm_y: 'Per-stage water balance closure: precipitation minus evapotranspiration, runoff, and storage terms.',
  residual_mm_y: 'Unclosed remainder of the stage water budget — should be near 0; hotspots flag conservation bugs.',
  local_relief_m: 'Relief within the cell\'s neighborhood at that stage.',
  is_marine: 'Marine mask at that stage (sea level and elevation evolve between stages).',

  // Stage-history fields (numeric depression fill)
  fill_depth_m: 'Depth added by this fill event to remove a numeric depression.',
  elevation_before_fill_m: 'Surface elevation at the event cell before the fill event.',
  elevation_after_fill_m: 'Surface elevation at the event cell after the fill event.',
  breach_excavation_depth_m: 'Depth excavated through the sill when the policy breached instead of filled.',
  breach_deposition_depth_m: 'Excavated material redeposited downstream of the breach.',
};

// ---------------------------------------------------------------------------
// Source (record family) docs

export const SOURCE_DOCS = {
  cells: 'Static per-cell fields from the final world state — one value per cell, no time axis.',
  cells_monthly: 'Per-cell monthly climatology (12 values per cell) for seasonal fields.',
  hydrologic_water_budget_history: 'Per-stage snapshots of the coupled water-budget recompute: climate inputs and hydrologic outputs at each feedback stage.',
  numeric_depression_fill_history: 'One record per depression fill/breach event during hydrologic conditioning. Stages here are individual events, so the slider steps through the conditioning sequence — expect most cells to be empty at any one stage.',
};

// ---------------------------------------------------------------------------
// Lookup API

export function unitOf(name) {
  for (const [pattern, unit, meaning] of UNIT_RULES) {
    if (pattern.test(name)) return { unit, meaning };
  }
  return null;
}

export function topicOf(name) {
  for (const [pattern, topic, doc] of TOPIC_RULES) {
    if (pattern.test(name)) return { topic, doc };
  }
  return null;
}

// Structured documentation for one manifest layer entry.
export function layerDoc(layer) {
  const unit = unitOf(layer.name);
  const topic = topicOf(layer.name);
  const kind = KIND_DOCS[layer.kind] || null;
  return {
    id: layer.id,
    name: layer.name,
    source: layer.source,
    summary: LAYER_DOCS[layer.name] || null,
    unit: unit ? unit.unit : null,
    unitMeaning: unit ? unit.meaning : null,
    topic: topic ? topic.topic : null,
    topicDoc: topic ? topic.doc : null,
    kindLabel: kind ? kind.label : layer.kind,
    kindDoc: kind ? kind.doc : null,
    sourceDoc: SOURCE_DOCS[layer.source] || null,
  };
}

// One-line tooltip for the layer list.
export function layerTooltip(layer) {
  const doc = layerDoc(layer);
  const bits = [];
  if (doc.unit) bits.push(`[${doc.unit}]`);
  if (doc.summary) bits.push(doc.summary);
  else if (doc.topic) bits.push(`${doc.topic}.`);
  if (doc.unitMeaning && !doc.summary) bits.push(`(${doc.unitMeaning})`);
  return bits.join(' ');
}

// Extra search terms so the layer filter matches docs, units, and topics.
export function searchTerms(layer) {
  const doc = layerDoc(layer);
  return [doc.unit, doc.topic, doc.summary].filter(Boolean).join(' ');
}

// ---------------------------------------------------------------------------
// Help overlay content

const SHORTCUTS = [
  ['1 / 2 / 3', 'Globe / Equirectangular / Mollweide projection (animated morph)'],
  ['w', 'Toggle mesh wireframe overlay'],
  ['b', 'Toggle plate-boundary overlay'],
  ['g', 'Toggle graticule overlay'],
  [', / .', 'Step stage or month backward / forward'],
  ['/', 'Focus the layer search box'],
  ['i', 'Toggle the layer doc card'],
  ['? or h', 'Toggle this help overlay'],
  ['Esc', 'Close help, doc card, or inspector'],
];

const MOUSE = [
  ['Drag', 'Rotate the globe (pan in 2D projections)'],
  ['Wheel', 'Zoom'],
  ['Hover', 'Show cell id and layer value in the status bar'],
  ['Click a cell', 'Open the inspector: all fields, per-stage sparklines, monthly series, adjacency'],
  ['Click a neighbor link', 'Jump the inspector to that cell'],
];

function esc(text) {
  return String(text).replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));
}

function keyTable(rows) {
  return `<table class="help-table">${rows.map(([key, doc]) => (
    `<tr><td><kbd>${esc(key)}</kbd></td><td>${esc(doc)}</td></tr>`
  )).join('')}</table>`;
}

export function helpHtml(manifest) {
  const layers = manifest.layers || [];
  const counts = {};
  for (const layer of layers) counts[layer.kind] = (counts[layer.kind] || 0) + 1;
  const histories = Object.entries(manifest.stage_histories || {});
  const kindRows = Object.entries(KIND_DOCS).map(([kind, doc]) => (
    `<tr><td><span class="badge">${esc(doc.label)}</span><br><small>${counts[kind] || 0} layers</small></td>`
    + `<td>${esc(doc.doc)}</td></tr>`
  )).join('');
  const historyRows = histories.map(([name, history]) => (
    `<tr><td>${esc(name)}</td><td>${history.stage_count} stages · ${(history.per_cell_fields || []).length} fields`
    + `${SOURCE_DOCS[name] ? `<br><small>${esc(SOURCE_DOCS[name])}</small>` : ''}</td></tr>`
  )).join('');

  return `
  <h2>magic-geo debugger — help</h2>
  <p>${layers.length} layers over ${esc(String(manifest.world.cell_count))} cells.
  Pick a layer on the left, scrub time at the bottom when the layer has a time axis,
  and click any cell to inspect all of its fields. Press <kbd>i</kbd> for docs on the
  active layer. The full guide lives in <code>docs/debug_ui_guide.md</code>.</p>

  <h3>Keyboard</h3>
  ${keyTable(SHORTCUTS)}

  <h3>Mouse</h3>
  ${keyTable(MOUSE)}

  <h3>Kinds of layers</h3>
  <table class="help-table">${kindRows}</table>

  <h3>Stage histories</h3>
  <table class="help-table">${historyRows}</table>

  <h3>Reading the legend</h3>
  <p>Numeric legends span the <b>p2–p98</b> percentile range, not min–max: the extreme
  2% of values on each side render saturated. This keeps skewed layers (like
  flow_accumulation) readable; hover a cell for its exact value. Dark background
  cells hold no value for the current layer/stage/month. Layers ending in
  <code>_id</code> are labels — color similarity means nothing there.</p>

  <h3>Data pipeline</h3>
  <p><code>magic-geo generate</code> → <code>world.json</code> →
  <code>magic-geo export-debug</code> → <code>debug/</code> cache (Parquet + mesh +
  manifest) → <code>magic-geo serve</code> → this UI. Every layer is one column
  served as a Float32 buffer from <code>/api/layer/&lt;id&gt;</code>; the mesh is
  loaded once and layer switches only swap that buffer.</p>

  <h3>Known quirks</h3>
  <ul>
    <li>Visible seams between cell polygons are the documented boundary-ring
    approximation; the <code>mean_neighbor_boundary_segment_mismatch_km</code> layer
    measures them.</li>
    <li>Scrubbing very long stage histories can briefly show a stale stage while
    fetches catch up; the stage label always reflects the requested stage.</li>
    <li>Values are fetched per stage/month on demand and cached (48 buffers);
    revisiting a recent stage is instant.</li>
  </ul>`;
}
