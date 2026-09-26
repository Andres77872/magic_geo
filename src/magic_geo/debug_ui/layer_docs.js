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
    test: (n) => /^species_.+_score_supported$/.test(n),
    role: 'diagnostic',
    doc: 'Whether this guild score has its required habitat, usable estimates and annual-air climate support. False means the score cannot be used; it does not establish absence of real species.',
  },
  {
    test: (n) => n.startsWith('species_guild_scores.'),
    role: 'diagnostic',
    doc: 'Relative guild score, shown only where its required habitat, inputs and annual-air climate support are available. Zero can be a supported estimate. This is not a population count or a universal survival limit.',
  },
  {
    test: (n) => n === 'id',
    role: 'identifier',
    doc: 'Cell id (0…cell_count-1). The primary key every table joins on; also the mesh vertex index.',
  },
  {
    test: (n) => n.endsWith('_id') || n === 'flow_to' || n === 'spill_to' || n === 'glacier_flow_to' || n.endsWith('_cell_id') || n.endsWith('_basin_id'),
    role: 'identifier',
    doc: 'Identifier / graph reference — the integer labels a region, system, or points at another cell. Drawn with categorical colours (they repeat every 18 ids), so read it as "same colour ≈ same group", never as a magnitude; hover a cell for its exact id. Percentile stats on ids are not meaningful.',
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
  climate_class: 'Köppen–Geiger climate class (Af, BWh, Cfb, ET, …). The class set is world-dependent; the classes actually present are listed with the layer.',
  landform: 'Geomorphic landform class (mountain_belt, coastal_plain, trench, …) from elevation and tectonic context.',
  plate_id: 'Tectonic plate the cell belongs to. Identifier — colour groups plates, magnitude is meaningless.',
  crust_type: 'Crust classification (continental, oceanic, craton, orogen, …).',
  crust_age_ma: 'Current procedural crust-state age in Ma after remap and maturation rules. This replay root is serialized with binary64 round-trip precision. It is not a reconstructed geological creation age or proof of a ridge-to-subduction flowline.',
  lithology: 'Dominant rock type (basalt, granite, limestone, …). NOTE: the per-stage history serializes lithology as numeric codes 0–6, while this cell layer uses names; the code order is alphabetical here and may not match the engine enum (see layers_review.md F3).',
  soil_type: 'Soil classification from climate, parent material, and drainage.',
  resource: 'Dominant natural-resource association for the cell (craton_iron_gold, sedimentary_fuels, …).',
  fertility: 'Agronomic fertility score combining soil, climate, and water availability.',
  sediment_thickness_m: 'Accumulated sediment column thickness in metres.',
  ice_thickness_m: 'Stored ice-thickness diagnostic in metres. With current grounded applicability, it describes annual exposed-land grounded ice; water-cell zero does not establish absence of lake or sea ice. Historical applicability is undeclared.',
  grounded_ice_surface_applicable: 'Whether the native annual grounded-ice diagnostic applies: exposed nonmarine, nonlake surface. False is process inapplicability, not an unavailable estimate or evidence that floating ice is absent.',
  grounded_ice_diagnostic_thickness_m: 'Roundtrip native grounded-ice thickness authority for active-membership replay. Use its strict >25 m test with applicability; rounded display thickness is not the membership authority.',
  ice_sheet_id: 'Ice-sheet reference. Under the current grounded model, active members have true applicability and raw grounded_ice_diagnostic_thickness_m strictly above 25 m; adjacent glacial terrain may retain a contextual association without active ice.',
  water_depth_m: 'Water column depth (bathymetry for ocean, lake depth for lakes) in metres. One value represents the entire coarse control volume; it does not resolve subcell shelf, slope, coastline, or strait geometry.',
  lake_fill_fraction: 'How full a lake basin is relative to its spill level at the end of the water-budget solve. Usually 0–1; values above 1 mark transiently overfilled basins.',
  basin_id: 'Drainage basin the cell belongs to. Identifier — colour groups a watershed.',
  landmass_id: 'Connected landmass (continent/island) the cell belongs to. Identifier.',
  settlement_score: 'Annual placement proxy used to select settlement candidates, not a universal survival limit. With the declared support fields, unsupported dry stored zero is unavailable; water/lake zero is a structural contribution and placement is inapplicable. Legacy absence leaves availability undeclared.',
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
  distance_to_marine_water_km: 'Shortest path along mesh edges to the nearest marine (non-lake) water cell. With no marine source, distance is null rather than zero; the marine-distance status explains the neutral map.',
  marine_distance_status: 'Whether a marine distance source exists. No marine source means distance is undefined and oceanic influence is absent; it does not imply zero rainfall or total humidity.',
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
  continentality_index: 'Geographic continentality descriptor. The native seasonal model solves temperature from its retained thermal columns, radiation and heat transport; this diagnostic does not adjust that solution.',
  orographic_factor: 'Terrain-forced uplift enhancement of precipitation on windward slopes.',
  rain_shadow_factor: 'Precipitation suppression on lee slopes downwind of barriers.',
  top_of_atmosphere_insolation_w_m2: 'Annual-mean solar input before the atmosphere, set by latitude and orbit.',
  absorbed_shortwave_w_m2: 'Legacy post-hoc absorbed-sunlight diagnostic from annual insolation and empirical albedo. Native seasonal output uses annual_absorbed_shortwave_w_m2.',
  outgoing_longwave_w_m2: 'Legacy post-hoc graybody emission calculated from annual temperature. Native seasonal emission instead uses retained monthly temperature fourth moments.',
  greenhouse_trapping_w_m2: 'Legacy post-hoc longwave increment from empirical greenhouse and current-temperature effects; it is not a separately solved atmospheric heat source.',
  net_radiative_balance_w_m2: 'Legacy diagnostic absorbed sunlight plus empirical trapping minus graybody emission. It is not the native solved energy budget.',
  radiative_equilibrium_temperature_c: 'Temperature the cell would reach from local radiation balance alone.',
  no_greenhouse_equilibrium_temperature_c: 'Radiative equilibrium temperature with the greenhouse effect removed.',
  energy_balance_residual_c: 'Generated temperature minus the separately parameterized radiative-equilibrium temperature, in degrees Celsius. This is a diagnostic model mismatch, not the residual of a solved energy-closure equation and is not expected to be zero.',
  effective_toa_albedo: 'Prescribed effective top-of-atmosphere reflectivity retained by the native seasonal solver. Later biome, lake and ice diagnostics do not change this coefficient.',
  effective_longwave_emissivity: 'Effective gray emissivity retained by the native thermal column, derived from its pressure, gravity and prescribed infrared optical depth.',
  annual_absorbed_shortwave_w_m2: 'Duration-weighted annual absorbed sunlight from the native monthly energy budget, in W/m².',
  annual_emitted_longwave_w_m2: 'Duration-weighted annual emitted longwave energy from native temperature fourth moments and gray emissivity, in W/m².',
  annual_net_radiative_flux_w_m2: 'Native annual absorbed shortwave minus emitted longwave, in W/m². Conservative horizontal heat convergence is a separate term.',
  annual_horizontal_heat_convergence_w_m2: 'Native annual horizontal heat convergence per unit area, in W/m². Positive values import heat; area-weighted global exchanges cancel.',
  annual_net_heating_w_m2: 'Native annual absorbed shortwave minus emitted longwave plus horizontal heat convergence, in W/m².',
  annual_heat_storage_tendency_w_m2: 'Duration-weighted change in stored column heat from retained monthly boundary temperatures, in W/m².',
  annual_energy_balance_residual_w_m2: 'Signed native annual storage tendency minus net heating, in W/m². This measures the retained energy-budget numerical residual.',
  annual_mean_abs_energy_balance_residual_w_m2: 'Duration-weighted mean absolute native monthly energy residual, in W/m²; opposite monthly errors cannot cancel here.',
  annual_mean_energy_balance_numerical_allowance_w_m2: 'Duration-weighted native monthly numerical allowance, in W/m². This is a solver tolerance, not a heat source or a climate-accuracy guarantee.',
  reef_bleaching_risk_index: 'Legacy heuristic bleaching proxy. The native seasonal model omits this estimate because it has no independent reference climatology and bleaching time history.',
  atmospheric_cell: 'Which meridional circulation cell (Hadley / Ferrel / Polar) the cell sits in.',
  cell_monsoon_index: 'Strength of monsoon-like seasonal wind reversal and precipitation contrast.',
  surface_albedo_index: 'Surface reflectivity driven by ice, desert, vegetation, and water.',
  // Ocean
  ocean_current_temperature_c: 'Empirical warm/cold surface-current descriptor. It is not a resolved water-temperature profile or an adjustment to the native seasonal temperature solution.',
  ocean_current_regime: 'Classification of the local current (gyre limb, boundary current, drift, …).',
  ocean_upwelling_index: 'Upwelling strength; high values mark nutrient-rich coasts.',
  ocean_heat_transport_index: 'Empirical poleward-current descriptor. Native conservative thermal transport is separately retained in annual_horizontal_heat_convergence_w_m2.',
  fishery_productivity_index: 'Relative fishery estimate from primary productivity, water type, runoff, currents, and annual air climate. A stored zero with fishery_productivity_supported=false means the estimate is unavailable; inspect the support flags.',
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
  // Groundwater — annual empirical diagnostics; field names retain raw contracts.
  groundwater_recharge_mm_y: 'Heuristic annual share of infiltration assigned to groundwater recharge, in mm/year.',
  groundwater_discharge_mm_y: 'Annual diagnostic groundwater-to-surface discharge, in mm/year; seasonal timing is unresolved.',
  groundwater_hydraulic_head_m: 'Diagnostic hydraulic head from terrain elevation and an empirical depth-to-water proxy. No Darcy or transient water-table solve.',
  groundwater_flow_to_cell_id: 'Receiver selected by the declared diagnostic head-drop rule for annual lateral routing.',
  aquifer_class: 'Empirical aquifer classification from geology, recharge, quality and resource diagnostics.',
  aquifer_storage_index: 'Unitless aquifer storage-potential diagnostic; no measured storativity or stored-water volume.',
  aquifer_quality_index: 'Unitless aquifer-quality proxy; no measured potability or geochemical transport.',
  aquifer_productivity_index: 'Unitless annual aquifer-productivity diagnostic from declared resource proxies; no measured or sustainable yield.',
  aquifer_extraction_risk_index: 'Historical v1 aquifer-risk proxy that includes settlement suitability. No simulated pumping or measured extraction risk; absent in natural v2.',
  aquifer_natural_limitation_index: 'Natural limitation proxy (0–1) from aridity, low recharge, salinity, ice and closed-basin setting. Independent of settlement suitability and withdrawals; marine-excluded cells carry structural zero.',
  mean_aquifer_natural_limitation_index: 'Mean of the declared natural aquifer-limitation proxy over the record or summary domain; no human extraction or pumping estimate.',
  high_natural_limitation_cell_count: 'Aquifer-system cells with exported natural-limitation index at least 0.65; a proxy threshold, not observed groundwater stress.',
  high_natural_limitation_aquifer_cell_count: 'Summary cells with raw natural-limitation index at least 0.65; the declared summary convention precedes six-decimal cell serialization.',
  baseflow_support_index: 'Annual diagnostic surface-discharge support index. Dry-season flow reliability is unresolved.',
  groundwater_retained_storage_km3_y: 'Unadvanced annual recharge-partition remainder in km³/year. This flow remainder is not a stored-water stock or a sustainable-yield estimate.',
  total_groundwater_retained_storage_km3_y: 'Sum of the unadvanced annual recharge-partition remainder in km³/year; no transient storage stock is advanced.',
  karst_potential_index: 'Susceptibility to karstification (carbonate lithology + water).',
  cave_development_index: 'Modeled cave-system development intensity.',
  // Cryosphere
  ice_velocity_m_y: 'Annual grounded-ice velocity proxy in metres per year; not an integrated ice trajectory. Current applicability excludes marine and lake cells.',
  ice_surface_mass_balance_m_y: 'Annual precipitation/temperature accumulation-minus-ablation proxy. It does not close seasonal water or energy budgets; the retained annual constructor cannot produce positive ablation where it creates ice.',
  glacier_flow_to: 'Downhill target of the grounded-ice diagnostic, with -1 for no target. It directs bulk glacial sediment transport, not a conserved ice-mass flux. Inapplicable water keeps the raw -1 sentinel.',
  glacial_erosion_m: 'Grounded-ice erosion potential at the final diagnostic state, in metres. Actual bulk sediment removal belongs to the retained pre-transport stage and may differ; this is not accumulated physical-time erosion.',
  moraine_deposition_m: 'Glacial terrain-memory proxy, which may remain on permitted glacial-lake/fjord context. It is not the measured or replayed bulk sediment deposition and does not establish active ice.',
  deglaciation_age_ka: 'Glacial terrain-memory index expressed in ka, not a dated deglaciation. Permitted lake/fjord context may retain it without active grounded ice.',
  permafrost_class: 'Continuous / discontinuous / sporadic / absent permafrost classification.',
  active_layer_depth_m: 'Seasonal thaw depth above permafrost.',
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
  biome_confidence_index: 'Agreement score from related biome rules, neighboring labels and moisture. High agreement leaves biological forest viability unverified, especially in extreme climates.',
  growing_season_months: 'Months with mean temperature at least 5°C and precipitation at least one quarter of estimated PET. This warm/moist-month descriptor has no upper heat limit or physiological dormancy model.',
  ecotone_index: 'How transitional the cell is between neighboring biomes.',
  vegetation_biomass_index: 'Relative biomass estimate from productivity and surface conditions. Check biomass availability: unavailable estimates do not establish an empty standing or dead-fuel supply.',
  forest_growth_index: 'Relative forest-growth estimate from supported productivity, biomass, moisture and fertility. An unavailable value does not establish physical absence of trees.',
  primary_productivity_index: 'Relative productivity estimate using annual air climate and surface conditions. Read it with primary-productivity availability; unavailable zeros are not measured absence of production. Annual climate is not a plant survival limit.',
  aquatic_climate_proxy_applicable: 'Whether this cell uses the aquatic productivity estimate, including standing lakes. Dry saline basins remain terrestrial.',
  aquatic_primary_climate_supported: 'Whether annual air climate lies within the aquatic primary-productivity model support. This does not establish water temperature or biological survival at habitat depth.',
  fishery_climate_supported: 'Whether water type and annual air climate support the fishery temperature proxy. The derived estimate also requires supported primary productivity.',
  fishery_productivity_supported: 'Whether both the fishery climate proxy and its primary-productivity input are supported. False means the stored fishery zero is an unavailable estimate.',
  species_richness_index: 'Heuristic species-richness proxy from cell conditions; no population or species census is simulated.',
  species_endemism_index: 'Heuristic range-restriction proxy from isolation and habitat evidence; it does not simulate evolution or dispersal.',
  species_terrestrial_habitat_eligible: 'Whether the five terrestrial guilds may use this cell. Standing lakes and marine water are excluded; river channels can overlap terrestrial banks within a cell.',
  species_freshwater_habitat_eligible: 'Whether the generic freshwater-fish habitat is identified: a fresh lake or a terrestrial river channel outside saline basins. This is a resident habitat label, not a universal salinity limit.',
  species_marine_habitat_eligible: 'Whether the generic marine-fish habitat is identified as ocean, continental shelf or the native marine inland-sea class.',
  species_freshwater_fish_score_supported: 'Whether the freshwater-fish score has its required habitat, usable inputs and annual air climate inside its existing curve support. False means the score is unavailable or the habitat inapplicable; it does not establish absence of real fish.',
  species_marine_fish_score_supported: 'Whether the marine-fish score has marine habitat, supported primary and fishery inputs, and annual air climate inside its existing curve support. Unsupported upstream zeros cannot produce a range.',
  species_freshwater_fishery_input_mode: 'Standing-water fish scores require the upstream fishery estimate. The separate river score omits that term because the resource model does not estimate river fisheries.',
  wildfire_spread_risk_index: 'Early ecosystem wildfire-risk estimate. Read its availability field before using a zero; this does not observe an actual fire.',
  terrestrial_primary_climate_supported: 'Whether annual air temperature supports the terrestrial productivity estimate. The existing interval is a model limit, not a universal boundary for life.',
  primary_productivity_supported: 'Whether the primary-productivity estimate is available for the cell and annual climate. A supported zero remains a valid estimate.',
  vegetation_biomass_supported: 'Whether a terrestrial biomass estimate can be made from supported productivity. Water cells retain a known structural zero without claiming terrestrial biomass availability.',
  forest_growth_supported: 'Whether forest-growth inputs are available. This does not by itself identify forest habitat or promise positive growth.',
  vegetation_succession_supported: 'Whether the terrestrial succession estimate has usable productivity, biomass and disturbance inputs.',
  species_richness_supported: 'Whether the richness estimate has usable productivity and biomass inputs. It is not a species census.',
  ecosystem_wildfire_spread_risk_supported: 'Whether the early ecosystem fire-risk estimate has usable biomass inputs. Aquatic cells have known zero risk under this model.',
  ecosystem_disturbance_pressure_supported: 'Whether the ecosystem disturbance estimate has supported inputs. Zero with false availability is not observed absence of disturbance.',
  ecosystem_disturbance_pressure_index: 'Relative disturbance estimate. Prescribed natural models exclude human activity; historical models include a settlement-suitability term. Neither is an observed disturbance history.',
  vegetation_recovery_supported: 'Whether the recovery-time estimate has usable productivity, biomass and disturbance inputs.',
  species_composition_confidence_supported: 'Whether the inputs needed to estimate composition confidence are available.',
  species_endemism_supported: 'Whether the inputs needed for the range-restriction estimate are available. This does not simulate evolution or dispersal.',
  species_record_descriptors_supported: 'Whether the common descriptors needed for a species range record are available. Scores may still be supported when these record descriptors are unavailable.',
  species_applicable_guild_count: 'Number of guilds allowed by existing habitat gates. A guild outside its temperature support remains in this count, so missing climate support is visible.',
  species_supported_guild_count: 'Number of habitat-applicable guild scores whose required inputs and annual climate are supported. It does not count species.',
  species_composition_status: 'Complete means all habitat-applicable scores are supported; partial or unavailable means some estimates cannot be made. Range records also need separate supported descriptors. not_applicable is reserved for no applicable habitats.',
  wildfire_fuel_continuity_supported: 'Whether local productivity, biomass, early risk and neighboring terrestrial biomass can support the fuel estimate. Unknown fuel is not an empty fuel supply.',
  wildfire_firebreak_supported: 'Whether the firebreak estimate has usable fuel inputs. Unknown fuel cannot establish a physical barrier.',
  wildfire_ignition_potential_supported: 'Whether fuel, firebreak, early risk and disturbance estimates are usable for the ignition index.',
  wildfire_fuel_continuity_index: 'Relative fuel-continuity estimate. Unavailable values do not establish absence of standing or dead fuel.',
  wildfire_firebreak_index: 'Relative firebreak estimate over modeled conditions. Unavailable values are not physical barriers.',
  wildfire_ignition_potential_index: 'Relative ignition susceptibility over supported inputs. Prescribed natural models omit settlement suitability; historical models include it. This does not observe fire, lightning or human ignition activity.',
  fire_frequency_index: 'Dimensionless fire-susceptibility descriptor from climate and vegetation conditions; no calibrated recurrence interval or event-rate time basis is defined.',
  // Resources
  ore_genesis_potential_index: 'Combined favorability for ore formation from magmatic/hydrothermal/structural controls.',
  metallogenic_fertility_index: 'Crustal endowment favoring metal deposits.',
  petroleum_source_rock_index: 'Quality of organic-rich source rocks.',
  petroleum_accumulation_index: 'Modeled petroleum accumulation after generation, migration, and trapping.',
  mining_potential_index: 'Relative surface-mining potential on exposed land. A false mining_surface_applicable flag excludes underwater extraction; geological deposits remain present. The surface flag does not establish complete mining inputs or economic access. The separate mining_potential_supported flag identifies available economic inputs; false means null, not no geological resource. Legacy values without these flags have undeclared coverage.',
  // Human geography
  settlement_climate_supported: 'Whether the annual air temperature falls strictly inside the settlement placement model range of -14 to 48 °C. A false flag on dry land means the stored zero is unavailable; native water and lake contributions are known structural zero. This is not a universal survival limit.',
  settlement_climate_temperature_c: 'Exact annual air temperature consumed by the native settlement placement model, retained separately from rounded display temperatures.',
  harbor_site_applicable: 'Whether the existing harbor equation applies to this native dry coastal site. Water and noncoastal early returns are known structural zero; the support flag is separate.',
  harbor_suitability_supported: 'Whether the harbor equation has its required inputs. A supported zero is valid; false means the new estimate is null.',
  navigability_supported: 'Whether all components consumed by aggregate navigability are supported. Independent river and coastal components remain available even when the aggregate is not.',
  navigable_waterway_membership_complete: 'Whether waterway components can be selected over the complete required cell domain. Unknown candidates can connect components, so incomplete membership is unavailable.',
  port_site_selection_supported: 'Whether this cell can be evaluated by the local port selection rule. A supported cell may have no port; an unsupported cell has unknown port identity.',
  route_corridor_membership_complete: 'Whether all competing routes and their required diagnostics support complete corridor membership. An unavailable candidate is not a cheap path or a known absent route.',
  mining_potential_supported: 'Whether the surface-mining estimate has its required economic inputs. This is separate from exposed-land applicability; geological formation and deposits remain unchanged.',
  mining_zone_membership_supported: 'Whether connected mining-zone membership can be determined. Unsupported eligible neighbors can change a component; a known noneligible cell retains no-zone identity.',
  agricultural_potential_index: 'Relative agricultural potential from soils, annual air climate, water and terrain, shown only when its required inputs are supported. A supported zero is valid. This is not crop survival or yield; legacy values without a support flag have undeclared availability.',
  agricultural_habitat_applicable: 'Whether the agricultural model applies to exposed land. Standing fresh or saline lakes and marine water are excluded; dry saline basins remain land.',
  agricultural_climate_supported: 'Whether annual air temperature is strictly between -9 and 43 °C, the existing agricultural potential model’s range. This is a model limit, not a universal crop-survival boundary.',
  agricultural_potential_supported: 'Whether exposed-land habitat, the model’s annual air-climate range and all required agricultural inputs are available. A false flag makes the stored zero unavailable, not a measured absence of crop potential.',
  mining_surface_applicable: 'Whether the exposed-land surface-mining model applies. A false flag excludes underwater extraction, without removing geological deposits. It does not certify complete mining inputs or economic access.',
  culture_region_id: 'Cultural region the cell belongs to. An id layer — colors are labels.',
  language_region_id: 'Language region the cell belongs to.',
  political_region_id: 'Political region (polity) controlling the cell.',
  natural_frontier_index: 'Strength of natural barriers (mountains, deserts, straits) at this cell.',
  route_corridor_index: 'Relative corridor membership score. New incomplete competitive paths or diagnostics make membership unavailable; a known empty path is distinct from an unknown path.',
  port_suitability_index: 'Suitability for a port from harbor shelter, access, and hinterland.',
  harbor_suitability_index: 'Composite harbor suitability from physical shelter, depth and coastline plus a settlement-site term. New unsupported site inputs make this estimate unavailable; independent river/coastal transport components can remain known.',
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
  if (layer.availability) {
    notes.push('Unavailable estimates use the missing-data color and are excluded from the color range. Supported zero values remain visible; undeclared legacy availability keeps its original values.');
  }
  if (layer.kind?.endsWith('_stage')) {
    notes.push(`Per-stage layer · ${layer.stage_count} stages · colour scale fixed across all stages.`);
  }
  if (layer.kind === 'numeric_monthly') {
    notes.push(`Monthly layer · ${layer.month_count || 12} months · colour scale fixed across the year.`);
  }
  if (role === 'identifier') {
    notes.push('Values are labels, not magnitudes. Colours repeat every 18 ids; −1 means none and is drawn in the no-data grey.');
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

// --- Topic grouping for the layer panel ------------------------------------
// ~450 per-cell fields are far easier to scan by physical domain than as one
// alphabetical list. Rules run in order; the first match wins, so more specific
// domains (glacial sediment, groundwater, ocean temperature) precede broad ones.
export const LAYER_TOPICS = [
  { id: 'terrain', title: 'Terrain & tectonics' },
  { id: 'climate', title: 'Climate & atmosphere' },
  { id: 'ocean', title: 'Oceans & coasts' },
  { id: 'water', title: 'Rivers, lakes & groundwater' },
  { id: 'ice', title: 'Ice & permafrost' },
  { id: 'sediment', title: 'Erosion & sediment' },
  { id: 'soil', title: 'Soils' },
  { id: 'life', title: 'Biomes & ecology' },
  { id: 'resources', title: 'Resources & land use' },
  { id: 'people', title: 'Settlements & societies' },
  { id: 'mesh', title: 'Mesh & diagnostics' },
  { id: 'other', title: 'Other fields' },
];

const TOPIC_RULES = [
  ['mesh', /^(id|lat_deg|lon_deg|area_km2|atmospheric_cell)$|^(position_3d|normal_3d|healpix|s2_like|mesh_lod)|^cell_(edge|boundary|polygon|geometry)|neighbor_(edge|boundary)|boundary_vertex_count|equal_filled/],
  ['ice', /glac|^ice_|_ice_|ice_sheet|permafrost|moraine|deglaciation|basal_sliding|active_layer|frost_months/],
  ['people', /settlement|route|port_|_port|harbor|political|culture|language|frontier|navigab|transport_chokepoint|mountain_pass|oasis|accessibility|strait_access/],
  ['resources', /agricultur|mining|\bore_|ore_genesis|petroleum|metallogenic|placer|fishery|^resource$|hydrothermal/],
  ['ocean', /ocean|marine|reef|coastal|upwelling|bay_|continental_shelf|island_class|water_depth/],
  ['water', /river|lake|basin|flow_|_flow|runoff|discharge|drainage|depression|spill|water_balance|hydrolog|hydraulic|channel|overflow|groundwater|aquifer|spring|infiltration|vadose|wetland|froude|manning|bankfull|floodplain|stream_power|karst|cave_|subterranean|is_water|water_body|water_budget|closed_basin/],
  ['sediment', /sediment|erosion|erod|alluvium|deposition|hillslope|fluvial|bed_shear/],
  ['soil', /soil|fertility/],
  ['life', /biome|ecotone|vegetation|forest|species|productivity|wildfire|fire_|ecosystem|habitat|succession|guild/],
  ['climate', /temperature|precip|climat|wind|monsoon|humid|moisture|rain|orographic|evapotranspiration|season|albedo|shortwave|longwave|energy|heat|radiative|emissivity|pressure|aridity|continentality|vapor|upwind|advected|vertical_velocity|dry_season|wet_season|growing_season/],
  ['terrain', /elevation|relief|plate|boundary|crust|tectonic|rift|subduction|collision|fault|earthquake|seismic|volcan|orogen|uplift|subsidence|trench|ridge|transform|isostatic|landform|landmass|bedrock|lithology|dominant_tectonic|initial_/],
];

// Physical fields most people reach for first; shown as a "Featured" group.
export const FEATURED_LAYER_NAMES = [
  'elevation_m', 'biome', 'climate_class', 'temperature_c', 'precipitation_mm_y',
  'plate_id', 'landform', 'is_water', 'runoff_mm_y', 'ice_thickness_m',
  'soil_type', 'settlement_score', 'political_region_id',
];

export function layerTopic(layer) {
  if (!layer) return 'other';
  if (layer.source === 'cells_monthly') return 'climate';
  const name = String(layer.name || '');
  for (const [topic, pattern] of TOPIC_RULES) {
    if (pattern.test(name)) return topic;
  }
  return 'other';
}

// Human label: sentence case without the unit suffix (the unit is shown
// separately). The raw field name stays searchable and in the docs card.
export function layerLabel(layer) {
  const name = String(layer?.name || '');
  const unitInfo = inferUnit(name);
  let base = name;
  if (unitInfo) {
    for (const [suffix] of UNIT_RULES) {
      if (base.endsWith(suffix) && !['_index', '_fraction', '_count', '_ph'].includes(suffix)) {
        base = base.slice(0, -suffix.length);
        break;
      }
    }
  }
  const words = base.replace(/\./g, ' · ').replace(/_/g, ' ').replace(/\s+/g, ' ').replace(/\bph$/, 'pH').trim();
  if (!words) return name;
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function layerUnit(layer) {
  const unit = inferUnit(String(layer?.name || ''))?.unit;
  return unit && !['index', 'fraction', 'count', 'pH'].includes(unit) ? unit : '';
}

// Static UI guide shown in the help overlay. Kept here so the docs helper is the
// single source of truth for "how does this thing work".
export const UI_GUIDE = [
  {
    title: 'Getting around',
    items: [
      ['Workflow', 'Home shows the three steps — <b>Configure</b> a world, <b>Generate</b> it as a background job, then <b>Explore</b> it on the Map and in Data.'],
      ['Command palette', 'Press <kbd>Ctrl</kbd> <kbd>K</kbd> (<kbd>⌘</kbd> <kbd>K</kbd> on macOS) to jump to any view, layer, world, configuration, job or action.'],
      ['Switch worlds', 'The world picker in the header lists every prepared world in the workspace. Map and Data follow the selection.'],
      ['Background work', 'A running job shows in the header on every view; select it to follow progress. A notification appears when it finishes.'],
    ],
  },
  {
    title: 'Layers',
    items: [
      ['Pick a layer', 'Layers are grouped by topic — terrain, climate, water, ice, life, people. Click a group title to fold it; ☆ pins a layer to the top.'],
      ['Search', 'Press <kbd>/</kbd> and type. Matches the field name, topic, unit, role, description and class names. The chips narrow to numeric, class or time-varying layers.'],
      ['What am I looking at?', 'The “About this layer” card explains the active layer — unit, role, value range and, for classes, every category. Toggle it with <kbd>d</kbd>.'],
      ['Color scale', 'Chosen from what the field measures: <b>Viridis</b> for amounts, <b>Cool–warm</b> centred on 0 for signed values, <b>Terrain</b> split at sea level for elevations that cross 0 m, and categorical colours for identifiers and classes. The range is the 2nd–98th percentile; triangles at the legend ends mean values beyond it are clipped to the end colour. Change either under “Colour scale” in the legend.'],
      ['Legend', 'Ticks are round numbers. The bars above a ramp show how much of the planet’s surface has each colour, and a caret marks the value under the pointer. For classes, the share of the surface is listed next to each one; select a class to spotlight it (<kbd>Esc</kbd> clears).'],
      ['Missing data', 'Cells without a value render in flat gray — distinct from every colour of the ramp.'],
    ],
  },
  {
    title: 'Stages & months',
    items: [
      ['Time bar', 'Per-stage and monthly layers show a time bar. Drag, type an exact index, step with <kbd>,</kbd> / <kbd>.</kbd>, or press ▶ to play.'],
      ['Fixed scale', 'The color scale spans every stage or month, so what you see moving is real change in the data. Stepping through time cross-fades briefly between slices.'],
      ['Shareable view', 'The address bar keeps the layer, stage, month, projection, overlays and camera position. Copy it to return to exactly the same view.'],
    ],
  },
  {
    title: 'Projection, camera & overlays',
    items: [
      ['Globe / flat', 'Switch with the toolbar or <kbd>1</kbd> globe, <kbd>2</kbd> equirectangular, <kbd>3</kbd> Mollweide. The place in the middle of the screen stays put while the map unrolls.'],
      ['Move', 'Drag to move — the point you grab stays under the pointer. Scroll or pinch to zoom toward the pointer; double-click zooms in (<kbd>Shift</kbd> zooms out). The +, − and fit buttons do the same with one click.'],
      ['Keyboard', 'Select the map, then use the arrow keys to move, <kbd>+</kbd> / <kbd>−</kbd> to zoom (<kbd>Shift</kbd> for bigger steps) and <kbd>0</kbd> to show the whole world.'],
      ['Go anywhere', 'In the command palette type coordinates such as <code>12.5 N 40 W</code>, a cell number such as <code>cell 1234</code>, or the name of a place.'],
      ['Overlays', '<kbd>w</kbd> cell outlines, <kbd>r</kbd> relief shading, <kbd>b</kbd> plate boundaries, <kbd>g</kbd> latitude/longitude grid (it gets finer as you zoom), <kbd>p</kbd> places — settlements, ports, ruins, sacred areas and landmasses.'],
      ['Relief', 'Shades slopes of present-day elevation, lit from the north-west, with the vertical exaggeration shown in the button tooltip. Level ground and water keep their exact colours; it is off by default because shading changes how bright a colour looks.'],
      ['Scale and position', 'The bottom-right corner shows the latitude and longitude under the pointer and a scale bar measured at the map centre. The bar hides on whole-world views, where no single scale is true.'],
      ['More room', 'The panel button at the top-left hides the layer list.'],
    ],
  },
  {
    title: 'Cell inspector',
    items: [
      ['Open', 'Click any cell to see every field for it, with the active layer value on top. The selected cell keeps an amber outline; the target button (or <kbd>c</kbd>) centres the map on it.'],
      ['Histories', 'Per-stage sparklines mark the active stage; monthly series show the seasonal cycle.'],
      ['Neighbours', 'Adjacent cells are listed with edge flags (plate boundary, land/water, biome transition). Click one to jump to it.'],
    ],
  },
  {
    title: 'Export for GPT Image',
    items: [
      ['PNG', 'Downloads the current camera view in the final selected projection. Enabled overlays stay visible as spatial guides; view-only touches — the halo, hover and selection outlines, class spotlight and relief shading — are left out so every colour matches the codex.'],
      ['Prompt', 'Downloads a Markdown prompt paired to the PNG filename, with layer meaning, view metadata and a color codex.'],
      ['Local only', 'The workbench only creates local downloads. It never sends the map to an image-generation service.'],
    ],
  },
  {
    title: 'Reading the data honestly',
    items: [
      ['Identifiers', 'Fields ending in <code>_id</code> (and <code>flow_to</code>/<code>spill_to</code>) are labels, so they are drawn with categorical colours that repeat every 18 ids — read them as “same color ≈ same group”, and hover for the exact id.'],
      ['Constant fields', 'A field with a single value everywhere is drawn in one colour and the legend says so, rather than inventing a 0-to-1 range.'],
      ['Indices vs measurements', 'Fields ending in <code>_index</code> are derived, normally 0–1; fields with unit suffixes (<code>_m</code>, <code>_mm_y</code>, <code>_c</code>…) are physical quantities.'],
      ['Residuals', 'Fields with <code>residual</code> in the name should be ~0 everywhere; large values flag a budget that does not close.'],
      ['Ring seams', 'Gaps between cells in the flat projections are the documented boundary-ring mismatch, not a rendering bug — inspect <code>mean_neighbor_boundary_segment_mismatch_km</code>.'],
    ],
  },
];

export const KEY_REFERENCE = [
  ['Ctrl K / ⌘ K', 'Open the command palette'],
  ['?', 'Toggle this help'],
  ['/', 'Search layers (Map)'],
  ['d', 'Toggle the layer card (Map)'],
  ['1 / 2 / 3', 'Globe / equirectangular / Mollweide'],
  [', / .', 'Previous / next stage or month'],
  ['Space', 'Play or pause the time bar'],
  ['Arrows · + / − · 0', 'Move · zoom · whole world (map selected)'],
  ['Double-click', 'Zoom in at the pointer (Shift: out)'],
  ['w / r / b / g / p', 'Cells / relief / plates / grid / places'],
  ['c', 'Centre on the selected cell'],
  ['Ctrl Enter', 'Validate YAML (Configure)'],
  ['Ctrl S', 'Save YAML (Configure)'],
  ['Esc', 'Close dialogs, help or the inspector; clear a class spotlight'],
];
