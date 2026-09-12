// magic-geo debugger frontend: three.js globe over the debug-cache API.
//
// Rendering model: one merged indexed BufferGeometry (fan triangulation per
// cell, per-vertex cell_id), per-cell scalar values in an R32F DataTexture
// indexed by cell id in the vertex shader, colormap applied in the fragment
// shader. Projection morph blends vertex positions between the unit sphere
// and precomputed equirectangular/Mollweide plane positions. Picking renders
// encoded cell ids into an offscreen target and reads one pixel.

import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { describeLayer, docsCoverage, layerTooltip, searchTerms, UI_GUIDE, KEY_REFERENCE } from './layer_docs.js';

const MISSING_SENTINEL = 3.0e38;   // NaN replacement survives every GPU driver
const PLANE_SCALE = new THREE.Vector2(2.0, 1.0); // equirect/mollweide plane half-extent
const MAP_BACKGROUND_HEX = '#10141a';
const MISSING_COLOR_HEX = '#292e36';
const NUMERIC_CODEX_STOPS = 9;
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

// ---------------------------------------------------------------------------
// Small utilities

const $ = (selector) => document.querySelector(selector);

function formatValue(value) {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return '—';
    if (Number.isInteger(value)) return String(value);
    const abs = Math.abs(value);
    if (abs !== 0 && (abs >= 1e6 || abs < 1e-3)) return value.toExponential(3);
    return value.toPrecision(6).replace(/\.?0+$/, '');
  }
  return String(value);
}

const ECOLOGY_ESTIMATE_SUPPORT = {
  agricultural_potential_index: 'agricultural_potential_supported',
  mining_potential_index: 'mining_surface_applicable',
  primary_productivity_index: 'primary_productivity_supported',
  vegetation_biomass_index: 'vegetation_biomass_supported',
  forest_growth_index: 'forest_growth_supported',
  species_richness_index: 'species_richness_supported',
  wildfire_spread_risk_index: 'ecosystem_wildfire_spread_risk_supported',
  ecosystem_disturbance_pressure_index: 'ecosystem_disturbance_pressure_supported',
  vegetation_recovery_years: 'vegetation_recovery_supported',
  species_composition_confidence_index: 'species_composition_confidence_supported',
  species_endemism_index: 'species_endemism_supported',
  species_range_fragmentation_index: 'species_record_descriptors_supported',
  wildfire_fuel_continuity_index: 'wildfire_fuel_continuity_supported',
  wildfire_firebreak_index: 'wildfire_firebreak_supported',
  wildfire_ignition_potential_index: 'wildfire_ignition_potential_supported',
};
const PUBLIC_ESTIMATE_SUPPORT = {
  "settlement_score": "settlement_climate_supported",
  "harbor_suitability_index": "harbor_suitability_supported",
  "navigability_index": "navigability_supported",
  "navigability_class": "navigability_classification_supported",
  "navigable_waterway_id": "navigable_waterway_membership_complete",
  "protected_bay_index": "protected_bay_supported",
  "river_mouth_port_index": "river_mouth_port_supported",
  "port_suitability_index": "port_suitability_supported",
  "port_site_id": "port_site_selection_supported",
  "port_site_type": "port_site_selection_supported",
  "coastal_route_index": "coastal_route_supported",
  "route_corridor_id": "route_corridor_membership_complete",
  "route_corridor_type": "route_corridor_membership_complete",
  "route_corridor_index": "route_corridor_membership_complete",
  "mining_potential_index": "mining_potential_supported",
  "mining_zone_id": "mining_zone_membership_supported",
  "accessibility_index": "accessibility_supported",
  "spouse_ruler_id": "alliance_estimate_available",
  "marriage_alliance_id": "alliance_estimate_available",
  "role": "role_available",
  "economic_viability_index": "economic_viability_supported",
  "mean_resource_viability_index": "mean_resource_viability_supported",
  "continuity_index": "continuity_estimate_available",
  "estimated_age_years": "continuity_estimate_available",
  "ruin_count": "ruin_count_available",
  "event_count": "event_count_available",
  "language_event_count": "language_event_count_available",
  "mean_connectivity": "mean_connectivity_available",
  "mean_instability": "mean_instability_available",
  "migration_event_count": "migration_event_count_available",
  "state_event_count": "state_event_count_available",
  "carrying_capacity": "capacity_estimate_available",
  "urbanization_fraction": "capacity_estimate_available",
  "migration_balance": "migration_balance_available",
  "agricultural_capacity_index": "physical_means_available",
  "water_security_index": "physical_means_available",
  "hazard_mortality_index": "physical_means_available",
  "estimated_population": "population_estimate_available",
  "population_pressure": "population_estimate_available",
  "growth_rate_per_year": "population_estimate_available",
  "site_strength_index": "site_strength_available",
  "area_km2": "geometry_estimate_available",
  "stability_index": "geometry_estimate_available",
  "boundary_perimeter_km": "geometry_estimate_available",
  "dissolved_polygon_area_km2": "geometry_estimate_available",
  "polygon_area_error_fraction": "geometry_estimate_available",
  "compactness_index": "geometry_estimate_available",
  "geometry_quality": "geometry_estimate_available",
  "assigned_land_fraction": "geometry_estimate_available",
  "largest_region_area_km2": "geometry_estimate_available",
  "largest_region_id": "geometry_estimate_available",
  "fragmentation_index": "geometry_estimate_available"
};

const SUMMARY_ESTIMATE_SUPPORT = {
  mean_harbor_suitability_index: 'navigability_estimates_complete',
  mean_navigability_index: 'navigability_estimates_complete',
  high_harbor_suitability_cell_count: 'navigability_estimates_complete',
  navigable_cell_count: 'navigable_waterway_selection_complete',
  navigable_waterway_count: 'navigable_waterway_selection_complete',
  navigable_waterway_total_area_km2: 'navigable_waterway_selection_complete',
  navigability_class_counts: 'navigability_estimates_complete',
  mean_route_corridor_index: 'route_corridor_membership_complete',
  mean_coastal_route_index: 'coastal_route_estimates_complete',
  route_corridor_type_counts: 'route_corridor_membership_complete',
  route_feature_coverage_index: 'route_corridor_membership_complete',
  route_corridor_cell_count: 'route_corridor_membership_complete',
  coastal_route_corridor_count: 'route_corridor_diagnostics_complete',
  river_valley_route_corridor_count: 'route_corridor_diagnostics_complete',
  mountain_pass_route_corridor_count: 'route_corridor_diagnostics_complete',
  oasis_route_corridor_count: 'route_corridor_diagnostics_complete',
};

const RECORD_CONTEXT_SUPPORT = {
  route_corridor_id: 'route_path_supported', path_cell_ids: 'route_path_supported',
  route_corridor_type: 'route_corridor_diagnostics_supported', corridor_type: 'route_corridor_diagnostics_supported',
  mean_route_corridor_index: 'route_corridor_membership_complete', max_route_corridor_index: 'route_corridor_membership_complete',
  navigable_waterway_ids: 'navigable_waterway_links_complete', port_site_ids: 'port_site_links_complete',
};

const SPECIES_COMPOSITION_FIELDS = new Set([
  'dominant_species_guild', 'species_habitat_suitability_index', 'species_guild_richness_count',
]);

const GROUNDED_ICE_FIELDS = new Set([
  'ice_thickness_m', 'glacier_flow_to', 'ice_surface_mass_balance_m_y',
  'basal_sliding_index', 'ice_velocity_m_y', 'glacial_erosion_m',
]);

function formatInspectorValue(cell, key, value) {
  const formatted = formatValue(value);
  if (key === 'distance_to_marine_water_km' && value === null && cell.marine_distance_status === 'no_marine_source') {
    return 'No marine source (distance undefined)';
  }
  if (key === 'grounded_ice_diagnostic_thickness_m' && Number.isFinite(value)) {
    const scope = cell.grounded_ice_surface_applicable === false
      ? 'raw grounded-ice authority; m; process inapplicable; lake and sea ice are unmodeled'
      : 'raw grounded-ice thickness authority; m';
    return `${Object.is(value, -0) ? '-0' : String(value)} (${scope})`;
  }
  if (GROUNDED_ICE_FIELDS.has(key) && cell.grounded_ice_surface_applicable === false) {
    return `${formatted} (grounded ice not applicable; lake and sea ice are unmodeled)`;
  }
  if (key === 'ice_sheet_id' && typeof cell.grounded_ice_surface_applicable === 'boolean'
      && Number.isInteger(value) && value >= 0) {
    if (!Number.isFinite(cell.grounded_ice_diagnostic_thickness_m)) {
      return `${formatted} (sheet association; active membership requires raw grounded-ice thickness)`;
    }
    const active = cell.grounded_ice_surface_applicable && cell.grounded_ice_diagnostic_thickness_m > 25;
    return `${formatted} (${active ? 'active grounded-ice member' : 'glacial context association; not an active ice member'})`;
  }
  if (key === 'settlement_score' && typeof cell.settlement_climate_supported === 'boolean') {
    if (cell.is_water === true || cell.is_lake === true) return `${formatted} (structural water contribution; placement not applicable)`;
    if (cell.settlement_climate_supported === false) return 'Unavailable within the annual settlement model';
  }
  if (key === 'mining_potential_index' && cell.mining_surface_applicable === false && typeof cell.mining_potential_supported === 'boolean') {
    return `${formatted} (surface mining not applicable)`;
  }
  const contextualFlag = RECORD_CONTEXT_SUPPORT[key];
  const publicFlag = contextualFlag && typeof cell[contextualFlag] === 'boolean' ? contextualFlag : PUBLIC_ESTIMATE_SUPPORT[key];
  if ((publicFlag && cell[publicFlag] === false)
      || cell.estimate_availability?.[key] === false
      || cell[`estimate_availability.${key}`] === false
      || Object.entries(cell).some(([name, flags]) => (name.endsWith('availability') && flags && typeof flags === 'object' && flags[key] === false)
        || (name.endsWith(`availability.${key}`) && flags === false))) return 'Unavailable';
  const scoreGuild = key.startsWith('species_guild_scores.') ? key.slice('species_guild_scores.'.length) : null;
  const support = scoreGuild ? `species_${scoreGuild}_score_supported` : ECOLOGY_ESTIMATE_SUPPORT[key];
  if ((support && cell[support] === false)
      || (SPECIES_COMPOSITION_FIELDS.has(key) && cell.species_supported_guild_count === 0)) {
    return 'Unavailable';
  }
  if (SPECIES_COMPOSITION_FIELDS.has(key) && cell.species_composition_status === 'partial') {
    return `${formatted} (partial score coverage)`;
  }
  if (key === 'primary_productivity_index'
      && cell.aquatic_climate_proxy_applicable === true
      && cell.aquatic_primary_climate_supported === false) {
    return `${formatted} (estimate unavailable: climate outside model support)`;
  }
  if (key === 'fishery_productivity_index' && cell.fishery_productivity_supported === false) {
    if (cell.fishery_climate_supported === true && cell.aquatic_primary_climate_supported === false) {
      return `${formatted} (estimate unavailable: primary productivity unsupported)`;
    }
    return `${formatted} (estimate unavailable for this water type or climate)`;
  }
  return formatted;
}

function speciesAvailabilityMarkup(cell) {
  if (typeof cell.species_composition_status !== 'string') return '';
  const status = cell.species_composition_status;
  const scoreCount = `${formatValue(cell.species_supported_guild_count)} / ${formatValue(cell.species_applicable_guild_count)}`;
  const records = cell.species_record_descriptors_supported === false
    ? 'Range records unavailable: their common descriptors are not supported.'
    : cell.species_record_descriptors_supported === true
      ? 'Range descriptors are supported. A record still requires a qualifying connected range.'
      : 'Range descriptor availability is undeclared.';
  let markup = '<div class="inspector-section"><h3>Species estimates</h3>'
    + `<p>Score coverage: <strong>${escapeHtml(status)}</strong> (${escapeHtml(scoreCount)} habitat-applicable guilds).</p>`
    + `<p>${escapeHtml(records)} Complete scores do not guarantee range records or establish actual species presence.</p>`;
  if (cell.species_guild_scores && typeof cell.species_guild_scores === 'object' && !Array.isArray(cell.species_guild_scores)) {
    for (const [guild, score] of Object.entries(cell.species_guild_scores)) {
      markup += `<div class="field-row"><span class="k">${escapeHtml(guild.replaceAll('_', ' '))}</span>`
        + `<span class="v">${escapeHtml(formatInspectorValue(cell, `species_guild_scores.${guild}`, score))}</span></div>`;
    }
  }
  return markup + '</div>';
}

function landUseAvailabilityMarkup(cell) {
  if (!cell || typeof cell !== 'object' || Array.isArray(cell)
      || !('agricultural_potential_index' in cell || 'mining_potential_index' in cell)) return '';
  const agriculture = cell.agricultural_potential_supported === false
    ? 'Agriculture estimate unavailable: its habitat, annual air climate or required inputs are outside this model. This does not establish crop failure.'
    : cell.agricultural_potential_supported === true
      ? 'Agriculture estimate available within its annual air-climate model and required inputs. A supported zero is valid; this is not a crop-yield prediction.'
      : 'Agriculture availability is undeclared; a legacy value remains visible.';
  const mining = cell.mining_surface_applicable === false
    ? 'Surface mining is not applicable to water-covered cells. Geological deposits may still be present.'
    : cell.mining_surface_applicable === true
      ? 'The exposed-land surface mining model applies. This flag does not establish complete mining inputs or economic access.'
      : 'Mining surface applicability is undeclared; a legacy value remains visible.';
  const miningInputs = cell.mining_potential_supported === false ? ' The economic estimate is unavailable from its required inputs.'
    : cell.mining_potential_supported === true ? ' Its required economic inputs support an estimate, including zero.' : '';
  return '<div class="inspector-section"><h3>Land use estimates</h3>'
    + `<p>${agriculture}</p><p>${mining}${miningInputs}</p></div>`;
}

function populationScopeMarkup(catalog) {
  const contract = catalog?.estimate_display;
  const nativeModel = contract?.models?.native_social_availability_model;
  const populationModel = contract?.models?.population_region_model;
  if (contract?.schema !== 'typed_estimate_display_v1'
      || contract.scope === 'geo_only' || catalog?.world?.generation_scope === 'geo_only'
      || nativeModel?.model_type !== 'native_settlement_source_complete_social_estimates_v1'
      || populationModel?.model_type !== 'causal_area_weighted_capacity_occupancy_population_regions_v2'
      || populationModel.membership_model !== 'nonwater_political_region_cells_v1') return '';
  return '<div class="notice">Population total sums modeled population regions, whose membership follows political regions. '
    + 'An empty region set has a supported sum of zero; this does not establish that the world is uninhabited. '
    + 'Unavailable member estimates remain unavailable.</div>';
}

function familyAvailabilityMarkup(name, rows, detail = 'full', availability = null) {
  if (name === 'climate_continentality_regions' && rows.length && rows.every((row) =>
    Number.isSafeInteger(row?.cell_count) && row.cell_count > 0
    && Number.isSafeInteger(row.marine_distance_defined_cell_count) && row.marine_distance_defined_cell_count >= 0
    && Number.isSafeInteger(row.no_marine_source_cell_count) && row.no_marine_source_cell_count >= 0
    && row.marine_distance_defined_cell_count + row.no_marine_source_cell_count === row.cell_count)) {
    return '<div class="notice">Marine distance means use cells with defined distances. '
      + 'A region labeled no_marine_source has an undefined mean distance, displayed as —. '
      + 'Rainfall and total humidity are separate outputs.</div>';
  }
  if (availability) {
    const notice = availability.scope === 'field_specific_availability'
      ? 'Record slots are retained. Each estimate has its own availability; an empty record list does not establish a zero estimate.'
      : availability.complete === false
      ? 'Selection incomplete: these are retained supported records. An empty list does not establish absence.'
      : availability.complete === true
        ? 'Selection covers its declared inputs. An empty list means no records selected within that model.'
        : 'Availability is undeclared for this family; retain its historical values without inferring coverage.';
    if (name !== 'wildfire_spread_histories') return `<div class="notice">${notice}</div>`;
  }
  if (name !== 'wildfire_spread_histories' || !rows.some((row) => typeof row?.front_coverage_status === 'string')) return '';
  const partial = rows.filter((row) => row.front_coverage_status === 'partial_unavailable_inputs').length;
  const count = rows.filter((row) => typeof row?.front_coverage_status === 'string').length;
  const coverageHelp = detail === 'full'
    ? 'The steps column contains unmodeled edges and step coverage. Open raw JSON for untruncated details.'
    : 'Select Full nested records for the unmodeled edges and step coverage.';
  return `<div class="notice">${partial} of ${count} histories on this page have partial fronts with unavailable neighboring estimates. `
    + `Containment describes modeled cells only; it does not demonstrate physical containment. ${coverageHelp}</div>`;
}

function viridis(t) {
  const c = [
    [0.2777273272234177, 0.005407344544966578, 0.3340998053353061],
    [0.1050930431085774, 1.404613529898575, 1.384590162594685],
    [-0.3308618287255563, 0.214847559468213, 0.09509516302823659],
    [-4.634230498983486, -5.799100973351585, -19.33244095627987],
    [6.228269936347081, 14.17993336680509, 56.69055260068105],
    [4.776384997670288, -13.74514537774601, -65.35303263337234],
    [-5.435455855934631, 4.645852612178535, 26.3124352495832],
  ];
  const rgb = [0, 0, 0];
  for (let ch = 0; ch < 3; ch += 1) {
    let acc = c[6][ch];
    for (let k = 5; k >= 0; k -= 1) acc = acc * t + c[k][ch];
    rgb[ch] = Math.min(1, Math.max(0, acc));
  }
  return rgb;
}

function categoryColor(index) {
  const hue = (index * 0.61803398875) % 1;
  const color = new THREE.Color();
  color.setHSL(hue, 0.55, 0.55);
  return [color.r, color.g, color.b];
}

function mollweide(latDeg, lonDeg) {
  const lat = (latDeg * Math.PI) / 180;
  const lon = (lonDeg * Math.PI) / 180;
  let theta = lat;
  if (Math.abs(Math.abs(lat) - Math.PI / 2) < 1e-9) {
    theta = Math.sign(lat) * (Math.PI / 2);
  } else {
    for (let i = 0; i < 8; i += 1) {
      const denom = 2 + 2 * Math.cos(2 * theta);
      if (Math.abs(denom) < 1e-12) break;
      theta -= (2 * theta + Math.sin(2 * theta) - Math.PI * Math.sin(lat)) / denom;
    }
  }
  return [(lon / Math.PI) * Math.cos(theta), Math.sin(theta)];
}

function latLonToXyz(latDeg, lonDeg, radius = 1) {
  const lat = (latDeg * Math.PI) / 180;
  const lon = (lonDeg * Math.PI) / 180;
  return [
    radius * Math.cos(lat) * Math.cos(lon),
    radius * Math.cos(lat) * Math.sin(lon),
    radius * Math.sin(lat),
  ];
}

// ---------------------------------------------------------------------------
// Shaders (GLSL3). The morph logic is shared by the fill, wireframe, line and
// pick materials so every drawn element follows the projection transition.

const MORPH_CHUNK = /* glsl */ `
  uniform float uMorph;      // 0 = sphere, 1 = 2D plane
  uniform float uProj2D;     // 0 = equirect, 1 = mollweide
  vec3 morphedPosition(vec3 spherePos, vec2 posEq, vec2 posMo) {
    // Planet frame is z-polar; render frame is y-up (three.js/OrbitControls).
    vec3 oriented = vec3(spherePos.y, spherePos.z, spherePos.x);
    vec2 plane = mix(posEq, posMo, uProj2D);
    vec3 flat3 = vec3(plane.x * ${PLANE_SCALE.x.toFixed(1)}, plane.y * ${PLANE_SCALE.y.toFixed(1)}, 0.0);
    return mix(oriented, flat3, uMorph);
  }
`;

const FILL_VERTEX = /* glsl */ `
  in vec2 aPosEq;
  in vec2 aPosMo;
  in float aCellId;
  uniform highp sampler2D uValues;
  uniform int uTexWidth;
  out float vValue;
  ${MORPH_CHUNK}
  void main() {
    int id = int(aCellId + 0.5);
    ivec2 texel = ivec2(id % uTexWidth, id / uTexWidth);
    vValue = texelFetch(uValues, texel, 0).r;
    vec3 pos = morphedPosition(position, aPosEq, aPosMo);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  }
`;

const FILL_FRAGMENT = /* glsl */ `
  out vec4 outColor;
  in float vValue;
  uniform float uMin;
  uniform float uMax;
  uniform float uCategorical;
  uniform sampler2D uColormap;
  vec3 hsl2rgb(vec3 hsl) {
    vec3 rgb = clamp(abs(mod(hsl.x * 6.0 + vec3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
    float c = (1.0 - abs(2.0 * hsl.z - 1.0)) * hsl.y;
    return hsl.z + c * (rgb - 0.5);
  }
  void main() {
    if (vValue > 1.0e37 || isnan(vValue)) {
      outColor = vec4(0.16, 0.18, 0.21, 1.0);
      return;
    }
    if (uCategorical > 0.5) {
      if (vValue < -0.5) { outColor = vec4(0.16, 0.18, 0.21, 1.0); return; }
      float hue = fract(vValue * 0.61803398875);
      outColor = vec4(hsl2rgb(vec3(hue, 0.55, 0.55)), 1.0);
      return;
    }
    float t = clamp((vValue - uMin) / max(uMax - uMin, 1.0e-12), 0.0, 1.0);
    outColor = vec4(texture(uColormap, vec2(t, 0.5)).rgb, 1.0);
  }
`;

const FLAT_VERTEX = /* glsl */ `
  in vec2 aPosEq;
  in vec2 aPosMo;
  uniform float uLift;
  ${MORPH_CHUNK}
  void main() {
    vec3 pos = morphedPosition(position * (1.0 + uLift), aPosEq, aPosMo);
    pos.z += uLift * 4.0 * uMorph;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  }
`;

const FLAT_FRAGMENT = /* glsl */ `
  out vec4 outColor;
  uniform vec4 uColor;
  void main() { outColor = uColor; }
`;

const PICK_VERTEX = /* glsl */ `
  in vec2 aPosEq;
  in vec2 aPosMo;
  in float aCellId;
  out vec3 vIdColor;
  ${MORPH_CHUNK}
  void main() {
    float id = aCellId;
    vIdColor = vec3(
      mod(id, 256.0) / 255.0,
      mod(floor(id / 256.0), 256.0) / 255.0,
      floor(id / 65536.0) / 255.0
    );
    vec3 pos = morphedPosition(position, aPosEq, aPosMo);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  }
`;

const PICK_FRAGMENT = /* glsl */ `
  out vec4 outColor;
  in vec3 vIdColor;
  void main() { outColor = vec4(vIdColor, 1.0); }
`;

// ---------------------------------------------------------------------------
// Application state

const state = {
  status: null,
  catalog: null,
  cacheAvailable: false,
  activeView: 'map',
  manifest: null,
  meshInfo: null,
  cellCount: 0,
  activeLayer: null,
  stage: 0,
  month: 0,
  projection: 'globe',      // 'globe' | 'equirect' | 'mollweide'
  morph: { value: 0, target: 0, proj2D: 0, proj2DTarget: 0 },
  values: null,             // Float32Array currently displayed
  layerCache: new Map(),    // key -> Float32Array (LRU)
  fetchSeq: 0,              // monotonic activateLayer counter; stale responses bail
  cacheIdentity: null,      // selected cache_dir + revision, pinned across async reads
  cacheEpoch: 0,            // invalidates every cache-derived request on a cache change
  statusRequest: 0,
  catalogRequest: 0,
  catalogLoading: null,
  mapRequest: 0,
  overlays: { wireframe: false, plates: false, graticule: false },
  pickDirty: true,
  hoverCell: -1,
  selectedCell: -1,
  inspectorRequest: 0,     // orders repeated requests, including the same cell
  inspectorSparklines: [], // current panel nodes; refreshed only from committed slices
  docsVisible: true,       // docs card under the layer panel
  docsCollapsed: false,    // card body collapsed but header shown
  helpOpener: null,
  operations: [],
  jobs: [],
  jobsSignature: null,
  selectedJobId: null,
  selectedJobStatus: null,
  jobListRequest: 0,
  jobDetailRequest: 0,
  jobSelectionRequest: 0,  // explicit selection intent, independent of polling
  backendRequest: 0,
  operationSubmitting: false,
  configSchema: null,
  schemaFields: [],
  mapReady: false,
  mapInitializing: null,
  mapEventController: null,
  animationStarted: false,
  layerLoading: false,
  exportSnapshot: null,
  exportBusy: false,
  exportGeneration: 0,
  exportMessage: '',
  lastImageExport: null,
  dataOffset: 0,
  dataTotal: 0,
  dataRequest: 0,
  worldRequest: 0,
  worldSwitching: false,
  worldsSignature: null,  // last-rendered world list; unchanged polls skip the rebuild
  configTemplateRequest: 0,
  configWorkbenchRequest: 0,
  configEditRevision: 0,
  configResultRequest: 0,
  savedConfig: null,
};

const three = {};

// Console access for debugging the debugger itself.
window.__magicGeo = { state, three };

// ---------------------------------------------------------------------------
// Data access

async function fetchBuffer(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return response.arrayBuffer();
}

async function fetchJson(url, options = {}) {
  const request = { ...options, headers: { Accept: 'application/json', ...(options.headers || {}) } };
  if (request.body !== undefined && typeof request.body !== 'string') {
    request.headers['Content-Type'] = 'application/json';
    request.body = JSON.stringify(request.body);
  }
  const response = await fetch(url, request);
  if (!response.ok) {
    let detail = '';
    let errorPayload = null;
    try {
      const payload = await response.json();
      errorPayload = payload;
      detail = payload.detail || payload.message || JSON.stringify(payload);
      if (typeof detail === 'object') detail = detail.message || JSON.stringify(detail);
    } catch (_) {
      detail = await response.text().catch(() => '');
    }
    const error = new Error(`${url}: ${response.status}${detail ? ` — ${detail}` : ''}`);
    error.status = response.status;
    error.payload = errorPayload;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

async function optionalJson(url, options = {}) {
  try {
    return await fetchJson(url, options);
  } catch (error) {
    console.warn(error);
    return null;
  }
}

const isStageLayer = (layer) => Boolean(layer?.kind?.endsWith('_stage'));
const isCategoricalLayer = (layer) => Boolean(layer?.kind?.startsWith('categorical'));

function layerCacheKey(layer, stage, month, identity = state.cacheIdentity) {
  // Only the axis the layer actually varies along participates in the key, so
  // the same buffer is reused no matter what the other axis was when fetched.
  const stageKey = isStageLayer(layer) ? stage : 0;
  const monthKey = layer.kind === 'numeric_monthly' ? month : 0;
  return `${identity ?? 'no-cache'}|${layer.id}|${stageKey}|${monthKey}`;
}

async function fetchLayerValues(layer, stage, month, context = currentCacheContext()) {
  if (!cacheContextIsCurrent(context)) throw new Error('The selected cache changed.');
  const key = layerCacheKey(layer, stage, month, context.identity);
  if (state.layerCache.has(key)) {
    const cached = state.layerCache.get(key);
    state.layerCache.delete(key);
    state.layerCache.set(key, cached);   // refresh LRU position
    return cached;
  }
  const params = new URLSearchParams();
  if (isStageLayer(layer)) params.set('stage', String(stage));
  if (layer.kind === 'numeric_monthly') params.set('month', String(month));
  if (context.revision) params.set('revision', context.revision);
  const encodedLayerId = encodeURIComponent(String(layer.id));
  const buffer = await fetchBuffer(`/api/layer/${encodedLayerId}?${params}`);
  if (!cacheContextIsCurrent(context)) throw new Error('The selected cache changed.');
  const raw = new Float32Array(buffer);
  if (raw.length !== state.cellCount) {
    throw new Error(`Layer has ${raw.length} values; expected ${state.cellCount} cells.`);
  }
  const values = new Float32Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) {
    values[i] = Number.isNaN(raw[i]) ? MISSING_SENTINEL : raw[i];
  }
  state.layerCache.set(key, values);
  while (state.layerCache.size > 48) {
    state.layerCache.delete(state.layerCache.keys().next().value);
  }
  return values;
}

function prefetchNeighborStages(layer, stage) {
  if (!isStageLayer(layer)) return;
  const context = currentCacheContext();
  const count = layer.stage_count || 1;
  for (const delta of [1, -1, 2, -2]) {
    const neighbor = stage + delta;
    if (neighbor >= 0 && neighbor < count
        && !state.layerCache.has(layerCacheKey(layer, neighbor, state.month, context.identity))) {
      fetchLayerValues(layer, neighbor, state.month, context).catch(() => {});
    }
  }
}

// ---------------------------------------------------------------------------
// Scene construction

function decodeMeshBuffers(positions, cellIds, indices, posEq, posMo, cellCount) {
  const decoded = {
    positions: new Float32Array(positions),
    cellIds: new Uint32Array(cellIds),
    indices: new Uint32Array(indices),
    posEq: new Float32Array(posEq),
    posMo: new Float32Array(posMo),
  };
  // cell_ids contains one world-cell reference for EACH render vertex. A
  // polygon contributes its center and ring vertices, so this array is much
  // larger than the number of world cells and must never size the value table.
  const vertexCount = decoded.cellIds.length;
  if (!Number.isSafeInteger(cellCount) || cellCount < 1) {
    throw new Error('The cache must declare a positive world cell count.');
  }
  if (!vertexCount || decoded.positions.length !== vertexCount * 3
      || decoded.posEq.length !== vertexCount * 2 || decoded.posMo.length !== vertexCount * 2
      || !decoded.indices.length || decoded.indices.length % 3 !== 0) {
    throw new Error('The cache mesh buffers have inconsistent vertex or triangle counts.');
  }
  if (decoded.cellIds.some((id) => id >= cellCount)
      || decoded.indices.some((index) => index >= vertexCount)) {
    throw new Error('The cache mesh contains an out-of-range cell or vertex reference.');
  }
  return decoded;
}

async function buildScene(context) {
  const [positions, cellIds, indices, posEq, posMo] = await Promise.all([
    fetchBuffer(cacheRevisionUrl('/mesh/positions.f32', context)),
    fetchBuffer(cacheRevisionUrl('/mesh/cell_ids.u32', context)),
    fetchBuffer(cacheRevisionUrl('/mesh/indices.u32', context)),
    fetchBuffer(cacheRevisionUrl('/mesh/pos_equirect.f32', context)),
    fetchBuffer(cacheRevisionUrl('/mesh/pos_mollweide.f32', context)),
  ]);
  if (!cacheContextIsCurrent(context)) return false;
  const mesh = decodeMeshBuffers(positions, cellIds, indices, posEq, posMo, state.cellCount);

  const canvas = $('#globe');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x10141a);
  const camera = new THREE.PerspectiveCamera(50, 1, 0.01, 100);
  camera.position.set(0, 0, 3.0);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 1.05;
  controls.maxDistance = 12;

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(mesh.positions, 3));
  geometry.setAttribute('aPosEq', new THREE.BufferAttribute(mesh.posEq, 2));
  geometry.setAttribute('aPosMo', new THREE.BufferAttribute(mesh.posMo, 2));
  const idFloats = Float32Array.from(mesh.cellIds);
  geometry.setAttribute('aCellId', new THREE.BufferAttribute(idFloats, 1));
  geometry.setIndex(new THREE.BufferAttribute(mesh.indices, 1));

  // Value texture: square-ish R32F texture indexed by cell id.
  const texWidth = Math.max(1, Math.ceil(Math.sqrt(state.cellCount)));
  const texHeight = Math.max(1, Math.ceil(state.cellCount / texWidth));
  const texData = new Float32Array(texWidth * texHeight).fill(MISSING_SENTINEL);
  const valueTexture = new THREE.DataTexture(texData, texWidth, texHeight, THREE.RedFormat, THREE.FloatType);
  valueTexture.minFilter = THREE.NearestFilter;
  valueTexture.magFilter = THREE.NearestFilter;
  valueTexture.needsUpdate = true;

  const colormapData = new Uint8Array(256 * 4);
  for (let i = 0; i < 256; i += 1) {
    const [r, g, b] = viridis(i / 255);
    colormapData.set([r * 255, g * 255, b * 255, 255], i * 4);
  }
  const colormapTexture = new THREE.DataTexture(colormapData, 256, 1, THREE.RGBAFormat, THREE.UnsignedByteType);
  colormapTexture.needsUpdate = true;

  const sharedUniforms = {
    uMorph: { value: 0 },
    uProj2D: { value: 0 },
  };
  const fillMaterial = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: FILL_VERTEX,
    fragmentShader: FILL_FRAGMENT,
    uniforms: {
      ...sharedUniforms,
      uValues: { value: valueTexture },
      uTexWidth: { value: texWidth },
      uMin: { value: 0 },
      uMax: { value: 1 },
      uCategorical: { value: 0 },
      uColormap: { value: colormapTexture },
    },
    side: THREE.DoubleSide,
  });
  const fillMesh = new THREE.Mesh(geometry, fillMaterial);
  fillMesh.frustumCulled = false;
  scene.add(fillMesh);

  const wireMaterial = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: FLAT_VERTEX,
    fragmentShader: FLAT_FRAGMENT,
    uniforms: { ...sharedUniforms, uLift: { value: 0.001 }, uColor: { value: new THREE.Vector4(1, 1, 1, 0.10) } },
    wireframe: true,
    transparent: true,
    depthWrite: false,
  });
  const wireMesh = new THREE.Mesh(geometry, wireMaterial);
  wireMesh.frustumCulled = false;
  wireMesh.visible = false;
  scene.add(wireMesh);

  const pickMaterial = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: PICK_VERTEX,
    fragmentShader: PICK_FRAGMENT,
    uniforms: { ...sharedUniforms },
    side: THREE.DoubleSide,
  });
  const pickTarget = new THREE.WebGLRenderTarget(1, 1, {
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
  });

  Object.assign(three, {
    renderer, scene, camera, controls, geometry,
    fillMesh, fillMaterial, wireMesh, pickMaterial, pickTarget,
    valueTexture, colormapTexture, texWidth, texHeight,
    plateLines: null, plateLinesLoading: null, plateLinesAbortController: null,
    graticuleLines: null, sharedUniforms,
  });
  resizeRenderer();
  return true;
}

function makeLineSegments(segments, color, opacity, lift) {
  // segments: [[lat1, lon1, lat2, lon2], ...]; endpoints wrapped near each other.
  const positions = new Float32Array(segments.length * 6);
  const posEq = new Float32Array(segments.length * 4);
  const posMo = new Float32Array(segments.length * 4);
  segments.forEach((seg, index) => {
    const [lat1, lon1raw, lat2, lon2raw] = seg;
    const lon1 = lon1raw;
    let lon2 = lon2raw;
    if (Math.abs(lon2 - lon1) > 180) lon2 += lon2 > lon1 ? -360 : 360;
    positions.set(latLonToXyz(lat1, lon1, 1.0), index * 6);
    positions.set(latLonToXyz(lat2, lon2, 1.0), index * 6 + 3);
    posEq.set([lon1 / 180, lat1 / 90, lon2 / 180, lat2 / 90], index * 4);
    posMo.set([...mollweide(lat1, lon1), ...mollweide(lat2, lon2)], index * 4);
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('aPosEq', new THREE.BufferAttribute(posEq, 2));
  geometry.setAttribute('aPosMo', new THREE.BufferAttribute(posMo, 2));
  const material = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: FLAT_VERTEX,
    fragmentShader: FLAT_FRAGMENT,
    uniforms: {
      ...three.sharedUniforms,
      uLift: { value: lift },
      uColor: { value: new THREE.Vector4(...color, opacity) },
    },
    transparent: true,
    depthWrite: false,
  });
  const lines = new THREE.LineSegments(geometry, material);
  lines.frustumCulled = false;
  return lines;
}

function cancelPlateLinesLoad() {
  const controller = three.plateLinesAbortController;
  // Detach the doomed promise immediately so a rapid off/on toggle can start a
  // fresh request instead of reusing the promise that is about to resolve false.
  three.plateLinesLoading = null;
  three.plateLinesAbortController = null;
  if (controller && !controller.signal.aborted) controller.abort();
}

async function ensurePlateLines() {
  if (three.plateLines) return true;
  if (three.plateLinesLoading) return three.plateLinesLoading;

  const context = currentCacheContext();
  const scene = three.scene;
  if (!scene) return false;
  const controller = new AbortController();
  let loading;
  loading = (async () => {
    try {
      const segments = await fetchJson(
        cacheRevisionUrl('/api/plate-boundaries', context),
        { signal: controller.signal },
      );
      if (controller.signal.aborted || !cacheContextIsCurrent(context) || three.scene !== scene) {
        return false;
      }
      // Every caller for this scene shares `loading`, so exactly one object can
      // be attached. The defensive check also protects future alternate callers.
      if (three.plateLines) return true;
      const lines = makeLineSegments(segments, [1.0, 0.42, 0.32], 0.9, 0.004);
      lines.visible = state.overlays.plates;
      scene.add(lines);
      three.plateLines = lines;
      return true;
    } catch (error) {
      if (controller.signal.aborted) return false;
      throw error;
    } finally {
      if (three.plateLinesLoading === loading) three.plateLinesLoading = null;
      if (three.plateLinesAbortController === controller) three.plateLinesAbortController = null;
    }
  })();
  three.plateLinesLoading = loading;
  three.plateLinesAbortController = controller;
  return loading;
}

function buildGraticule() {
  if (three.graticuleLines) return;
  const segments = [];
  for (let lat = -60; lat <= 60; lat += 30) {
    for (let lon = -180; lon < 180; lon += 5) {
      segments.push([lat, lon, lat, lon + 5]);
    }
  }
  for (let lon = -180; lon < 180; lon += 30) {
    for (let lat = -85; lat < 85; lat += 5) {
      segments.push([lat, lon, lat + 5, lon]);
    }
  }
  three.graticuleLines = makeLineSegments(segments, [0.45, 0.55, 0.7], 0.28, 0.002);
  three.graticuleLines.visible = false;
  three.scene.add(three.graticuleLines);
}

// ---------------------------------------------------------------------------
// Rendering loop, morph animation, picking

function resizeRenderer() {
  if (!three.renderer || !three.camera || !three.pickTarget) return;
  const canvas = three.renderer.domElement;
  const width = Math.max(1, canvas.clientWidth || canvas.parentElement.clientWidth || 1);
  const height = Math.max(1, canvas.clientHeight || canvas.parentElement.clientHeight || 1);
  // devicePixelRatio changes with browser zoom and monitor moves; re-apply it
  // here so the canvas stays sharp (it is otherwise captured once at startup).
  three.renderer.setPixelRatio(window.devicePixelRatio);
  three.renderer.setSize(width, height, false);
  three.camera.aspect = width / height;
  three.camera.updateProjectionMatrix();
  three.pickTarget.setSize(
    Math.max(1, Math.floor(width * window.devicePixelRatio)),
    Math.max(1, Math.floor(height * window.devicePixelRatio)),
  );
  state.pickDirty = true;
}

function animate() {
  requestAnimationFrame(animate);
  if (!state.mapReady || !three.sharedUniforms || !three.renderer || !three.scene || !three.camera) return;
  const morph = state.morph;
  const before = `${morph.value.toFixed(4)}|${morph.proj2D.toFixed(4)}`;
  morph.value += (morph.target - morph.value) * 0.12;
  if (Math.abs(morph.target - morph.value) < 0.002) morph.value = morph.target;
  // Only blend the 2D projection choice while flat, otherwise snap.
  if (morph.value < 0.05) {
    morph.proj2D = morph.proj2DTarget;
  } else {
    morph.proj2D += (morph.proj2DTarget - morph.proj2D) * 0.12;
    if (Math.abs(morph.proj2DTarget - morph.proj2D) < 0.002) morph.proj2D = morph.proj2DTarget;
  }
  three.sharedUniforms.uMorph.value = morph.value;
  three.sharedUniforms.uProj2D.value = morph.proj2D;
  if (`${morph.value.toFixed(4)}|${morph.proj2D.toFixed(4)}` !== before) state.pickDirty = true;

  if (state.activeView === 'map') {
    three.controls.update();
    three.renderer.render(three.scene, three.camera);
  }
}

function renderPickBuffer() {
  const { renderer, scene, camera, pickTarget, fillMesh, wireMesh, pickMaterial } = three;
  const overlays = [three.plateLines, three.graticuleLines].filter(Boolean);
  const visibility = overlays.map((line) => line.visible);
  overlays.forEach((line) => { line.visible = false; });
  const wireVisible = wireMesh.visible;
  wireMesh.visible = false;
  const previousMaterial = fillMesh.material;
  fillMesh.material = pickMaterial;
  const previousBackground = scene.background;
  scene.background = new THREE.Color(0xffffff);

  renderer.setRenderTarget(pickTarget);
  renderer.render(scene, camera);
  renderer.setRenderTarget(null);

  fillMesh.material = previousMaterial;
  scene.background = previousBackground;
  wireMesh.visible = wireVisible;
  overlays.forEach((line, index) => { line.visible = visibility[index]; });
  state.pickDirty = false;
}

function pickCell(clientX, clientY) {
  const rect = three.renderer.domElement.getBoundingClientRect();
  const x = Math.floor((clientX - rect.left) * window.devicePixelRatio);
  const y = Math.floor((rect.bottom - clientY) * window.devicePixelRatio);
  if (x < 0 || y < 0 || x >= three.pickTarget.width || y >= three.pickTarget.height) return -1;
  if (state.pickDirty) renderPickBuffer();
  const pixel = new Uint8Array(4);
  three.renderer.readRenderTargetPixels(three.pickTarget, x, y, 1, 1, pixel);
  const id = pixel[0] + pixel[1] * 256 + pixel[2] * 65536;
  return id >= state.cellCount ? -1 : id;
}

// ---------------------------------------------------------------------------
// Layer activation and legend

function uploadValues(values) {
  state.values = values;
  const data = three.valueTexture.image.data;
  data.fill(MISSING_SENTINEL);
  data.set(values.subarray(0, Math.min(values.length, data.length)));
  three.valueTexture.needsUpdate = true;
}

function updateLegend(layer) {
  $('#legend-title').textContent = layer ? `${layer.source} / ${layer.name}${layer.applicability?.field === 'grounded_ice_surface_applicable' ? ' · grounded ice only' : ''}${layer.applicability ? ` · ${layer.unavailable_cell_count || 0} unavailable · ${layer.inapplicable_cell_count || 0} inapplicable` : ''}` : 'no layer';
  const ramp = $('#legend-ramp');
  const categoriesBox = $('#legend-categories');
  categoriesBox.innerHTML = '';
  if (!layer) { ramp.style.display = 'none'; return; }
  if (layer.marine_distance && !layer.stats) {
    ramp.style.display = 'none';
    $('#legend-min').textContent = 'No marine source';
    $('#legend-max').textContent = '';
    $('#legend-min').title = 'Distance is undefined, not zero. Rainfall and total humidity are separate fields.';
    $('#legend-max').title = '';
    return;
  }
  if ((layer.availability || layer.applicability) && (isCategoricalLayer(layer) ? !(layer.categories || []).length : !layer.stats)) {
    ramp.style.display = 'none';
    $('#legend-min').textContent = 'No available estimates';
    $('#legend-max').textContent = '';
    $('#legend-min').title = '';
    $('#legend-max').title = '';
    return;
  }
  if (isCategoricalLayer(layer)) {
    ramp.style.display = 'none';
    $('#legend-min').textContent = '';
    $('#legend-max').textContent = '';
    (layer.categories || []).forEach((category, index) => {
      const [r, g, b] = categoryColor(index);
      const chip = document.createElement('div');
      chip.className = 'legend-chip';
      chip.innerHTML = `<i style="background: rgb(${r * 255 | 0},${g * 255 | 0},${b * 255 | 0})"></i><span></span>`;
      chip.lastChild.textContent = category;
      categoriesBox.appendChild(chip);
    });
    return;
  }
  ramp.style.display = 'block';
  const context = ramp.getContext('2d');
  for (let x = 0; x < ramp.width; x += 1) {
    const [r, g, b] = viridis(x / (ramp.width - 1));
    context.fillStyle = `rgb(${r * 255 | 0},${g * 255 | 0},${b * 255 | 0})`;
    context.fillRect(x, 0, 1, ramp.height);
  }
  const [lo, hi] = layerRange(layer);
  const stats = layer.stats || {};
  // Mark ends that clip data: the ramp normalises to p2–p98, so a true min/max
  // beyond the ramp end is compressed into the end colour. Without this cue a
  // heavy-tailed layer (e.g. flow_accumulation) looks like it tops out at p98.
  const loClip = stats.min !== undefined && stats.min < lo - Math.abs(lo) * 1e-6;
  const hiClip = stats.max !== undefined && stats.max > hi + Math.abs(hi) * 1e-6;
  const minEl = $('#legend-min');
  const maxEl = $('#legend-max');
  minEl.textContent = (loClip ? '≤ ' : '') + formatValue(lo);
  maxEl.textContent = (hiClip ? '≥ ' : '') + formatValue(hi);
  minEl.title = loClip ? `clipped — true min ${formatValue(stats.min)}` : '';
  maxEl.title = hiClip ? `clipped — true max ${formatValue(stats.max)}` : '';
}

function layerRange(layer) {
  const stats = layer.stats || {};
  let lo = stats.p2 ?? stats.min ?? 0;
  let hi = stats.p98 ?? stats.max ?? 1;
  if (lo === hi) { lo = stats.min ?? 0; hi = stats.max ?? lo + 1; }
  if (lo === hi) hi = lo + 1;
  return [lo, hi];
}

// ---------------------------------------------------------------------------
// Current-map export

function filenameSlug(value, fallback) {
  const normalized = String(value ?? '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
  const slug = normalized
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
  return slug || fallback;
}

function exactViewNumber(value) {
  if (!Number.isFinite(value)) throw new Error('The map camera contains a non-finite value.');
  return Object.is(value, -0) ? '0' : Number(value).toString();
}

function fnv1a64(value) {
  let hash = 0xcbf29ce484222325n;
  for (const byte of new TextEncoder().encode(value)) {
    hash ^= BigInt(byte);
    hash = BigInt.asUintN(64, hash * 0x100000001b3n);
  }
  return hash.toString(16).padStart(16, '0');
}

function cameraPoseSnapshot() {
  const camera = three.camera;
  const controls = three.controls;
  if (!camera || !controls) throw new Error('The map camera is not ready.');
  return {
    position: [camera.position.x, camera.position.y, camera.position.z],
    target: [controls.target.x, controls.target.y, controls.target.z],
    up: [camera.up.x, camera.up.y, camera.up.z],
    verticalFovDegrees: camera.fov,
  };
}

function mapViewFingerprint(snapshot, view) {
  const pose = view.cameraPose;
  const components = [
    'magic-geo-map-view-v1',
    snapshot.cacheIdentity,
    snapshot.layer?.id,
    snapshot.stage,
    snapshot.month,
    view.projection,
    view.overlays.wireframe ? 1 : 0,
    view.overlays.plates ? 1 : 0,
    view.overlays.graticule ? 1 : 0,
    view.width,
    view.height,
    ...pose.position.map(exactViewNumber),
    ...pose.target.map(exactViewNumber),
    ...pose.up.map(exactViewNumber),
    exactViewNumber(pose.verticalFovDegrees),
  ].map((component) => String(component));
  const canonical = components.map((component) => `${component.length}:${component}`).join('');
  return fnv1a64(canonical);
}

function mapExportBaseName(snapshot, projection = state.projection, viewFingerprint = null) {
  const world = filenameSlug(snapshot?.world?.name, 'world');
  const layer = filenameSlug(snapshot?.layer?.id, 'layer');
  const parts = [world, layer, filenameSlug(projection, 'map')];
  if (isStageLayer(snapshot?.layer)) parts.push(`stage-${snapshot.stage}`);
  if (snapshot?.layer?.kind === 'numeric_monthly') parts.push(`month-${snapshot.month + 1}`);
  if (viewFingerprint) parts.push(`view-${filenameSlug(viewFingerprint, 'view')}`);
  return parts.join('--');
}

function mapExportFileNames(snapshot, projection, viewFingerprint) {
  const base = mapExportBaseName(snapshot, projection, viewFingerprint);
  return {
    image: `${base}.png`,
    prompt: `${base}.gpt-image-prompt.md`,
  };
}

function rgbBytes(rgb) {
  return rgb.map((channel) => Math.max(0, Math.min(255, Math.floor(channel * 255))));
}

function rgbHex(rgb) {
  return `#${rgbBytes(rgb).map((channel) => channel.toString(16).padStart(2, '0')).join('')}`;
}

function markdownInline(value) {
  return String(value ?? '')
    .replace(/[\r\n\t]+/g, ' ')
    .replace(/\\/g, '\\\\')
    .replace(/([|`*_{}\[\]<>])/g, '\\$1')
    .trim();
}

function isRenderedValue(value) {
  return Number.isFinite(value) && value < 1.0e37;
}

function exportSnapshotMatchesState(snapshot = state.exportSnapshot) {
  if (!snapshot || !state.mapReady || state.layerLoading) return false;
  return snapshot.cacheIdentity === state.cacheIdentity
    && snapshot.layer === state.activeLayer
    && snapshot.values === state.values
    && snapshot.stage === state.stage
    && snapshot.month === state.month;
}

function exportSnapshotIsCurrent(snapshot = state.exportSnapshot) {
  return !state.exportBusy && exportSnapshotMatchesState(snapshot);
}

function exportGenerationIsCurrent(generation) {
  return generation === state.exportGeneration;
}

function exportOperationMatchesState(generation, snapshot) {
  return exportGenerationIsCurrent(generation) && exportSnapshotMatchesState(snapshot);
}

function exportMeshIssue(snapshot = state.exportSnapshot) {
  if (!snapshot) return null;
  const mesh = snapshot.manifest?.mesh || {};
  const cellsWithoutRing = Number(mesh.cells_without_ring || 0);
  if (cellsWithoutRing > 0) {
    return `${cellsWithoutRing} cells have no boundary ring; exporting would mislabel their holes as outside-map background.`;
  }
  if (Number(mesh.triangle_count || 0) < 1) return 'The debug mesh contains no renderable triangles.';
  return null;
}

function updateExportControls() {
  const issue = exportMeshIssue();
  const disabled = !exportSnapshotIsCurrent() || Boolean(issue);
  const titles = {
    'export-map-image': 'Export the current map reference as PNG',
    'export-image-prompt': 'Export a GPT Image prompt and color codex as Markdown',
  };
  for (const id of Object.keys(titles)) {
    const button = $(`#${id}`);
    if (!button) continue;
    button.disabled = disabled;
    button.title = issue ? `Export unavailable: ${issue}` : titles[id];
  }
}

function requireExportSnapshot() {
  const issue = exportMeshIssue();
  if (issue) throw new Error(issue);
  if (!exportSnapshotIsCurrent()) {
    throw new Error('Wait for the current map layer to finish loading before exporting.');
  }
  return state.exportSnapshot;
}

function snapshotView(snapshot, { width, height } = {}) {
  const projection = state.projection;
  const canvas = three.renderer?.domElement;
  const view = {
    cacheIdentity: snapshot.cacheIdentity,
    layer: snapshot.layer,
    stage: snapshot.stage,
    month: snapshot.month,
    values: snapshot.values,
    projection,
    overlays: { ...state.overlays },
    width: width ?? canvas?.width ?? 0,
    height: height ?? canvas?.height ?? 0,
    cameraPose: cameraPoseSnapshot(),
  };
  view.viewFingerprint = mapViewFingerprint(snapshot, view);
  const names = mapExportFileNames(snapshot, projection, view.viewFingerprint);
  view.imageFilename = names.image;
  view.promptFilename = names.prompt;
  return view;
}

function lastImageViewFor(snapshot) {
  const view = state.lastImageExport;
  if (!view) return null;
  // Prefer the last PNG that was actually handed to the browser for this data
  // slice. Camera damping or later view edits must not make the Markdown invent
  // a current-view companion filename that the user never downloaded.
  return view.cacheIdentity === snapshot.cacheIdentity
    && view.layer === snapshot.layer
    && view.stage === snapshot.stage
    && view.month === snapshot.month
    && view.values === snapshot.values
    ? view : null;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function setExportMessage(message, clearAfterMs = 0, generation = state.exportGeneration) {
  if (!exportGenerationIsCurrent(generation)) return;
  state.exportMessage = message;
  updateStatus();
  if (clearAfterMs > 0) {
    window.setTimeout(() => {
      if (!exportGenerationIsCurrent(generation) || state.exportMessage !== message) return;
      state.exportMessage = '';
      updateStatus();
    }, clearAfterMs);
  }
}

async function captureMapCanvas(snapshot, generation) {
  if (state.overlays.plates) {
    const ready = await ensurePlateLines();
    if (!ready) throw new Error('Plate boundaries could not be prepared for export.');
    if (three.plateLines) three.plateLines.visible = state.overlays.plates;
  }
  if (!exportOperationMatchesState(generation, snapshot)) {
    throw new Error('The selected map changed while the export was being prepared.');
  }

  resizeRenderer();
  const { renderer, scene, camera, sharedUniforms } = three;
  const source = renderer.domElement;
  if (!source.width || !source.height) throw new Error('The map canvas has no drawable size.');

  // Snap the morph out of any in-flight transition. The OrbitControls camera
  // pose only matches the projection once the morph reaches its target, so
  // exporting mid-transition would otherwise bake a globe camera onto the
  // flat plane and silently produce a clipped/offset PNG.
  const morph = state.morph;
  morph.value = morph.target;
  morph.proj2D = morph.proj2DTarget;
  state.pickDirty = true;

  const priorTarget = renderer.getRenderTarget();
  const priorMorph = sharedUniforms.uMorph.value;
  const priorProjection = sharedUniforms.uProj2D.value;
  const targetMorph = state.projection === 'globe' ? 0 : 1;
  const targetProjection = state.projection === 'mollweide' ? 1 : 0;

  // Render the selected projection's final state synchronously. Copying it to
  // a 2D canvas immediately avoids depending on preserveDrawingBuffer and also
  // prevents an in-progress globe/flat morph from leaking into the PNG.
  let exported;
  try {
    renderer.setRenderTarget(null);
    sharedUniforms.uMorph.value = targetMorph;
    sharedUniforms.uProj2D.value = targetProjection;
    three.controls.update();
    renderer.render(scene, camera);

    exported = document.createElement('canvas');
    exported.width = source.width;
    exported.height = source.height;
    const context = exported.getContext('2d', { alpha: false });
    if (!context) throw new Error('The browser could not create an export canvas.');
    context.drawImage(source, 0, 0);
  } finally {
    sharedUniforms.uMorph.value = priorMorph;
    sharedUniforms.uProj2D.value = priorProjection;
    renderer.setRenderTarget(null);
    renderer.render(scene, camera);
    renderer.setRenderTarget(priorTarget);
  }

  return {
    canvas: exported,
    view: snapshotView(snapshot, { width: exported.width, height: exported.height }),
  };
}

function canvasToBlob(canvas, type) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error(`The browser could not encode ${type}.`));
    }, type);
  });
}

function layerSliceSummary(snapshot) {
  let finiteCount = 0;
  let missingCount = 0;
  let min = Infinity;
  let max = -Infinity;
  const categorical = isCategoricalLayer(snapshot.layer);
  for (const value of snapshot.values) {
    if (!isRenderedValue(value) || (categorical && value < -0.5)) {
      missingCount += 1;
      continue;
    }
    finiteCount += 1;
    min = Math.min(min, value);
    max = Math.max(max, value);
  }
  return {
    total: snapshot.values.length,
    finiteCount,
    missingCount,
    min: finiteCount ? min : null,
    max: finiteCount ? max : null,
  };
}

function shareLabel(count, total) {
  if (!total) return '0.00%';
  return `${((count / total) * 100).toFixed(2)}%`;
}

function valueWithUnit(value, unit) {
  const formatted = formatValue(value);
  return unit && unit !== 'category' ? `${formatted} ${unit}` : formatted;
}

function buildCategoricalCodex(snapshot, doc, summary) {
  const declared = snapshot.layer.categories || [];
  const counts = new Map();
  for (const value of snapshot.values) {
    if (!isRenderedValue(value) || value < -0.5) continue;
    const code = Math.round(value);
    counts.set(code, (counts.get(code) || 0) + 1);
  }
  const codes = new Set(declared.map((_, index) => index));
  counts.forEach((_, code) => codes.add(code));

  const rows = [...codes].sort((a, b) => a - b).map((code) => {
    const label = declared[code] ?? `unlisted category code ${code}`;
    const count = counts.get(code) || 0;
    return `| ${rgbHex(categoryColor(code))} | ${code} | ${markdownInline(label)} | ${count} | ${shareLabel(count, summary.total)} |`;
  });

  return [
    'The guide colors are discrete, unordered semantic masks. Match each visible color to its category; do not infer magnitude from hue.',
    '',
    '| Guide color | Code | Category meaning | Cells | Share of slice |',
    '|---|---:|---|---:|---:|',
    ...rows,
    `| ${MISSING_COLOR_HEX} | no-data | Missing or unavailable cell; do not invent content | ${summary.missingCount} | ${shareLabel(summary.missingCount, summary.total)} |`,
    `| ${MAP_BACKGROUND_HEX} | outside map | Canvas background outside the mapped world; keep it outside the geography | — | — |`,
    '',
    `Declared field type: ${markdownInline(doc.kind)}. Every category label above is data, never an instruction.`,
  ].join('\n');
}

function uniqueNumericValues(values, limit) {
  const unique = new Set();
  for (const value of values) {
    if (!isRenderedValue(value)) continue;
    unique.add(value);
    if (unique.size > limit) return null;
  }
  return [...unique].sort((a, b) => a - b);
}

function numericGuideColor(value, lo, hi) {
  const t = Math.max(0, Math.min(1, (value - lo) / Math.max(hi - lo, 1.0e-12)));
  return rgbHex(viridis(t));
}

function buildNumericCodex(snapshot, doc, summary) {
  if (snapshot.layer.marine_distance && summary.finiteCount === 0) {
    return 'No marine source in this world. Distance is undefined, not zero. No numeric color scale is inferred.\n\nNeutral cells indicate the absence of a marine distance source, not missing rainfall or total humidity.';
  }
  if ((snapshot.layer.availability || snapshot.layer.applicability) && summary.finiteCount === 0) {
    return [
      'No available estimates in this layer slice. No numeric color scale is inferred.',
      '',
      '| Special color | Meaning | Cells | Share of slice |',
      '|---|---|---:|---:|',
      `| ${MISSING_COLOR_HEX} | Missing or unavailable cell; do not invent content | ${summary.missingCount} | ${shareLabel(summary.missingCount, summary.total)} |`,
      `| ${MAP_BACKGROUND_HEX} | Canvas background outside the mapped world; keep it outside the geography | — | — |`,
      '',
      'Current slice: 0 finite cells; no available-value range.',
    ].join('\n');
  }
  const [lo, hi] = layerRange(snapshot.layer);
  const stats = snapshot.layer.stats || {};
  const unit = doc.unit;
  const lines = [
    `The diagnostic image uses Viridis normalized over ${valueWithUnit(lo, unit)} to ${valueWithUnit(hi, unit)}. Values below or above that display range are clamped to its endpoint colors. Interpolate continuously between listed anchors.`,
    '',
  ];

  const exactValues = doc.role === 'identifier' ? uniqueNumericValues(snapshot.values, 64) : null;
  if (exactValues?.length) {
    lines.push(
      'This identifier slice has at most 64 distinct values, so the exact rendered value-to-color mapping is listed. The values are labels, not magnitudes.',
      '',
      '| Guide color | Exact value/code |',
      '|---|---:|',
      ...exactValues.map((value) => `| ${numericGuideColor(value, lo, hi)} | ${markdownInline(valueWithUnit(value, unit))} |`),
    );
  } else {
    lines.push(
      '| Guide color | Encoded value | Scale position |',
      '|---|---:|---:|',
    );
    for (let index = 0; index < NUMERIC_CODEX_STOPS; index += 1) {
      const t = index / (NUMERIC_CODEX_STOPS - 1);
      const value = lo + (hi - lo) * t;
      const boundary = index === 0 ? ' (and below)' : index === NUMERIC_CODEX_STOPS - 1 ? ' (and above)' : '';
      lines.push(`| ${rgbHex(viridis(t))} | ${markdownInline(valueWithUnit(value, unit))}${boundary} | ${(t * 100).toFixed(1)}% |`);
    }
  }

  lines.push(
    '',
    '| Special color | Meaning | Cells | Share of slice |',
    '|---|---|---:|---:|',
    `| ${MISSING_COLOR_HEX} | Missing or unavailable cell; do not invent content | ${summary.missingCount} | ${shareLabel(summary.missingCount, summary.total)} |`,
    `| ${MAP_BACKGROUND_HEX} | Canvas background outside the mapped world; keep it outside the geography | — | — |`,
    '',
    `Current slice: ${summary.finiteCount} finite cells; finite range ${valueWithUnit(summary.min, unit)} to ${valueWithUnit(summary.max, unit)}.`,
  );
  if (Number.isFinite(stats.min) && Number.isFinite(stats.max)) {
    const scope = snapshot.layer.availability ? 'available-value' : 'raw';
    lines.push(`Complete layer/time-axis ${scope} range: ${valueWithUnit(stats.min, unit)} to ${valueWithUnit(stats.max, unit)}.`);
  }
  if (Number.isFinite(stats.p2) && Number.isFinite(stats.p98)) {
    lines.push(`Robust display range (2nd–98th percentile): ${valueWithUnit(stats.p2, unit)} to ${valueWithUnit(stats.p98, unit)}.`);
  }
  return lines.join('\n');
}

function buildColorCodex(snapshot) {
  const doc = describeLayer(snapshot.layer);
  const groundedScope = snapshot.layer.applicability?.field === 'grounded_ice_surface_applicable'
    ? 'Grounded ice applies only to exposed nonmarine, nonlake cells. Lake and sea ice are unmodeled; their neutral color does not establish absence of floating ice.\n\n' : '';
  const scope = snapshot.layer.applicability
    ? `Surface applicability is separate from unavailable inputs: ${snapshot.layer.inapplicable_cell_count || 0} inapplicable cells; ${snapshot.layer.unavailable_cell_count || 0} unavailable estimates. Both use the neutral color; supported zero remains numeric.\n\n` : '';
  const summary = layerSliceSummary(snapshot);
  return groundedScope + scope + (isCategoricalLayer(snapshot.layer)
    ? buildCategoricalCodex(snapshot, doc, summary)
    : buildNumericCodex(snapshot, doc, summary));
}

function projectionLabel(projection) {
  return {
    globe: 'Globe — preserve the captured hemisphere, rotation, camera angle, and crop',
    equirect: 'Equirectangular — preserve the rectangular longitude/latitude layout and crop',
    mollweide: 'Mollweide — preserve the oval equal-area layout, orientation, and crop',
  }[projection] || projection;
}

function timeContextLines(snapshot) {
  if (isStageLayer(snapshot.layer)) {
    const history = snapshot.manifest?.stage_histories?.[snapshot.layer.source] || {};
    const meta = history.stages?.[snapshot.stage] || {};
    const details = [`stage index ${snapshot.stage}`];
    if (meta.stage !== undefined) details.push(`stage ${markdownInline(meta.stage)}`);
    if (meta.erosion_iteration !== undefined) details.push(`erosion iteration ${markdownInline(meta.erosion_iteration)}`);
    return [`- Time slice: ${details.join(' · ')}`];
  }
  if (snapshot.layer.kind === 'numeric_monthly') {
    return [`- Time slice: month ${snapshot.month + 1} (${MONTH_NAMES[snapshot.month] || 'monthly index'})`];
  }
  return ['- Time slice: static layer'];
}

function overlayPrompt(view) {
  const lines = [];
  if (view.overlays.wireframe) lines.push('White cell/triangle wireframe lines are diagnostic geometry: remove them completely in the final image.');
  if (view.overlays.plates) lines.push('Coral plate-boundary lines are structural guides: they may inform terrain transitions, but remove the literal lines in the final image.');
  if (view.overlays.graticule) lines.push('Blue-gray latitude/longitude grid lines are alignment guides: remove them completely in the final image.');
  if (!lines.length) lines.push('No diagnostic overlays are enabled in the reference image.');
  return lines.map((line) => `- ${line}`).join('\n');
}

function buildImagePromptMarkdown(snapshot, view = snapshotView(snapshot)) {
  const doc = describeLayer(snapshot.layer);
  const familyContext = doc.familyDoc ? `${doc.family}: ${doc.familyDoc}` : doc.family;
  const mappedField = [
    `- Layer: \`${markdownInline(snapshot.layer.id)}\``,
    `- Meaning: ${markdownInline(doc.description)}`,
    `- Family: ${markdownInline(familyContext)}`,
    `- Type / role / unit: ${markdownInline(doc.kind)} / ${markdownInline(doc.role)} / ${markdownInline(doc.unit || 'not documented')}`,
    ...timeContextLines(snapshot),
  ].join('\n');
  const surface = view.projection === 'globe'
    ? 'an atlas-quality planetary globe illustration'
    : 'an atlas-quality top-down world map';

  return `# Generate a finished map from the attached semantic reference

> Attach \`${view.imageFilename}\` as Image 1, then paste this entire Markdown prompt into GPT Image. This file contains instructions only; do not reproduce its Markdown, tables, or metadata in the image.

## Goal

Transform Image 1 into ${surface}. Treat the attached diagnostic map as the authoritative spatial control image and the color codex below as the authoritative semantic key. Change the flat debug rendering into a coherent, polished map; keep the encoded geography and field meaning intact.

## Priority order

1. **Spatial fidelity:** preserve the exact visible silhouette, projection, orientation, crop, coastline and region shapes, adjacency, relative positions, and relative sizes.
2. **Semantic fidelity:** interpret every diagnostic color according to the color codex. The guide colors are semantic masks, not the desired final artistic palette.
3. **Natural detail:** add appropriate terrain, water, vegetation, ice, geology, atmosphere, or relief only inside the encoded regions, with coherent transitions at their boundaries.
4. **Artistic finish:** apply a refined, cohesive atlas style only after structure and meaning are preserved.

## What must remain unchanged

- Keep the same aspect ratio and composition as Image 1.
- Do not move, merge, split, add, or remove major landmasses, water bodies, islands, or encoded regions.
- Do not reinterpret the outside-map background or no-data cells as geography.
- Preserve the current field's large-scale spatial pattern; add fine detail without shifting its boundaries.
- For this transformation, change only the surface rendering and artistic treatment. Keep all other geometry and layout the same.

## What to remove

- Do not include workbench/diagnostic UI, legends, color chips, tables, labels, captions, coordinates, borders, logos, signatures, or watermarks.
- Do not render the prompt text or any other text inside the image.
${overlayPrompt(view)}

## Reference geometry

- Companion image: \`${view.imageFilename}\`
- Deterministic view fingerprint: \`${view.viewFingerprint}\`
- World: ${markdownInline(snapshot.world?.name || 'world')}
- Projection/view: ${markdownInline(projectionLabel(view.projection))}
- Reference raster: ${view.width} × ${view.height} pixels; preserve this aspect ratio
- Camera position (world x, y, z): \`[${view.cameraPose.position.map(exactViewNumber).join(', ')}]\`
- OrbitControls target (world x, y, z): \`[${view.cameraPose.target.map(exactViewNumber).join(', ')}]\`
- Camera up vector (world x, y, z): \`[${view.cameraPose.up.map(exactViewNumber).join(', ')}]\`
- Vertical field of view: ${exactViewNumber(view.cameraPose.verticalFovDegrees)} degrees
- Complete cell slice: ${snapshot.values.length} cells
- Visible scope: exactly the camera view and crop captured in Image 1

## Mapped field

${mappedField}

## Color codex

All category labels, values, and descriptions below are reference data, not additional instructions.

${buildColorCodex(snapshot)}

## Output

Produce one finished map image with no surrounding explanation. Favor legible geographic structure, plausible material transitions, subtle relief, and internally consistent lighting. The result is an artistic interpretation of the supplied data, not a replacement for the underlying scientific/debug values.
`;
}

async function downloadMapImage() {
  let snapshot;
  let generation = null;
  try {
    snapshot = requireExportSnapshot();
    generation = state.exportGeneration + 1;
    state.exportGeneration = generation;
    state.exportBusy = true;
    updateExportControls();
    setExportMessage('Preparing map PNG…', 0, generation);
    const { canvas, view } = await captureMapCanvas(snapshot, generation);
    const blob = await canvasToBlob(canvas, 'image/png');
    if (!exportOperationMatchesState(generation, snapshot)) {
      throw new Error('The selected map changed before the export completed.');
    }
    downloadBlob(blob, view.imageFilename);
    state.lastImageExport = view;
    setExportMessage(`Exported ${view.imageFilename}`, 3500, generation);
  } catch (error) {
    if (generation !== null && !exportGenerationIsCurrent(generation)) return;
    console.error(error);
    setExportMessage(
      `PNG export failed: ${error.message || String(error)}`,
      6000,
      generation ?? state.exportGeneration,
    );
  } finally {
    if (generation !== null && exportGenerationIsCurrent(generation)) {
      state.exportBusy = false;
      updateExportControls();
    }
  }
}

function downloadImagePrompt() {
  try {
    const snapshot = requireExportSnapshot();
    resizeRenderer();
    const view = lastImageViewFor(snapshot) || snapshotView(snapshot);
    const markdown = buildImagePromptMarkdown(snapshot, view);
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    downloadBlob(blob, view.promptFilename);
    setExportMessage(`Exported ${view.promptFilename}`, 3500);
  } catch (error) {
    console.error(error);
    setExportMessage(`Prompt export failed: ${error.message || String(error)}`, 6000);
  }
}

// ---------------------------------------------------------------------------
// Layer docs card

function updateDocsCard(layer) {
  const card = $('#docs-card');
  card.classList.toggle('hidden', !state.docsVisible);
  card.classList.toggle('collapsed', state.docsCollapsed);
  const toggle = $('#docs-card-toggle');
  toggle.textContent = state.docsCollapsed ? '▸' : '▾';
  toggle.setAttribute('aria-expanded', String(!state.docsCollapsed));
  toggle.title = state.docsCollapsed ? 'Expand layer documentation' : 'Collapse layer documentation';
  if (!state.docsVisible) return;

  const doc = describeLayer(layer);
  const body = $('#docs-card-body');
  if (!doc) {
    body.innerHTML = '<div class="docs-desc">Select a layer to see its documentation.</div>';
    return;
  }

  const parts = [];
  parts.push(`<div class="docs-name">${escapeHtml(doc.title)}</div>`);

  const pills = [];
  if (doc.roleBadge) {
    pills.push(`<span class="docs-pill role" title="${escapeHtml(doc.roleBadge.hint)}">${escapeHtml(doc.roleBadge.label)}</span>`);
  }
  if (doc.unit) pills.push(`<span class="docs-pill unit">${escapeHtml(doc.unit)}</span>`);
  const kindLabel = {
    numeric: 'numeric', categorical: 'categorical',
    numeric_stage: 'per-stage', categorical_stage: 'per-stage categorical', numeric_monthly: 'monthly',
  }[doc.kind] || doc.kind;
  pills.push(`<span class="docs-pill kind">${escapeHtml(kindLabel)}</span>`);
  parts.push(`<div class="docs-meta">${pills.join('')}</div>`);

  parts.push(`<div class="docs-desc">${escapeHtml(doc.description)}</div>`);

  if (doc.stats) {
    parts.push('<div class="docs-range">'
      + `<span class="rk">min / max</span><span class="rv">${escapeHtml(doc.stats.min)} … ${escapeHtml(doc.stats.max)}</span>`
      + `<span class="rk">colour scale</span><span class="rv">${escapeHtml(doc.stats.p2)} … ${escapeHtml(doc.stats.p98)} (p2–p98)</span>`
      + '</div>');
  }

  if (doc.categories) {
    parts.push('<div class="docs-cats">');
    doc.categories.forEach((category, index) => {
      const [r, g, b] = categoryColor(index);
      parts.push(`<span class="docs-cat"><i style="background: rgb(${r * 255 | 0},${g * 255 | 0},${b * 255 | 0})"></i>${escapeHtml(category)}</span>`);
    });
    parts.push('</div>');
  }

  for (const note of doc.notes) {
    parts.push(`<div class="docs-note">${escapeHtml(note)}</div>`);
  }

  if (doc.familyDoc) {
    parts.push(`<div class="docs-family"><b>${escapeHtml(doc.family)}</b> — ${escapeHtml(doc.familyDoc)}</div>`);
  }

  body.innerHTML = parts.join('');
}

function setDocsVisible(visible) {
  state.docsVisible = visible;
  if (visible) state.docsCollapsed = false;
  const infoButton = $('#legend-info');
  infoButton.setAttribute('aria-pressed', String(visible));
  infoButton.classList.toggle('active', visible);
  updateDocsCard(state.activeLayer);
}

// ---------------------------------------------------------------------------
// Help overlay

function buildHelpOverlay() {
  const body = $('#help-body');
  const parts = [];

  parts.push('<h3>Keyboard</h3><div class="help-keygrid">');
  for (const [key, description] of KEY_REFERENCE) {
    const keys = key.split(' / ').map((k) => `<kbd>${escapeHtml(k)}</kbd>`).join(' / ');
    parts.push(`<div class="help-row"><span class="hk">${keys}</span><span class="hv">${escapeHtml(description)}</span></div>`);
  }
  parts.push('</div>');

  for (const section of UI_GUIDE) {
    parts.push(`<h3>${escapeHtml(section.title)}</h3><div class="help-cols">`);
    for (const [label, text] of section.items) {
      // `text` intentionally carries inline <kbd>/<code> markup from layer_docs.
      parts.push(`<div class="help-row"><span class="hk">${escapeHtml(label)}</span><span class="hv">${text}</span></div>`);
    }
    parts.push('</div>');
  }

  if (state.manifest) {
    const { counts, byRole } = docsCoverage(state.manifest.layers);
    const kindBits = Object.entries(byRole)
      .map(([kind, n]) => `${n}&nbsp;${escapeHtml(kind)}`)
      .join(' · ');
    parts.push('<h3>Docs coverage</h3>');
    parts.push('<div class="help-cov">'
      + `<b>${counts.total}</b> layers documented — `
      + `<b>${counts.curated}</b> curated, `
      + `<b>${counts.pattern}</b> by naming convention, `
      + `<b>${counts.unit}</b> by unit inference, `
      + `<b>${counts.generated}</b> generated fallback.<br>`
      + `Layer kinds: ${kindBits}.`
      + '</div>');
  }

  body.innerHTML = parts.join('');
}

function setHelpVisible(visible) {
  const overlay = $('#help-overlay');
  if (visible) {
    try {
      buildHelpOverlay();
    } catch (error) {
      console.error(error);
      $('#help-body').innerHTML = '<div class="notice warning">The help content could not be built. Keyboard shortcuts: <kbd>?</kbd> toggles this panel, <kbd>Esc</kbd> closes it.</div>';
    }
    state.helpOpener = document.activeElement;
  }
  overlay.classList.toggle('hidden', !visible);
  $('#workbench-header').inert = visible;
  $('#workbench').inert = visible;
  $('#toggle-help').classList.toggle('active', visible);
  $('#toggle-help').setAttribute('aria-expanded', String(visible));
  if (visible) $('#help-close').focus();
  else if (state.helpOpener instanceof HTMLElement && document.contains(state.helpOpener)) {
    state.helpOpener.focus();
    state.helpOpener = null;
  }
}

async function activateLayer(layer, { stage = null, month = null } = {}) {
  const context = currentCacheContext();
  if (!cacheContextIsCurrent(context)) return;
  // The active selection may belong to an older request still in flight.
  // Roll back to the last uploaded slice, whose labels and values committed
  // together, rather than to that uncommitted selection.
  const displayed = state.exportSnapshot;
  const previous = displayed && displayed.cacheIdentity === context.identity
    && displayed.cacheRevision === context.revision && displayed.values === state.values
    ? { layer: displayed.layer, stage: displayed.stage, month: displayed.month }
    : { layer: null, stage: 0, month: 0 };
  state.activeLayer = layer;
  if (stage !== null) state.stage = stage;
  if (month !== null) state.month = month;
  if (isStageLayer(layer)) {
    state.stage = Math.min(state.stage, (layer.stage_count || 1) - 1);
  }
  const requestedStage = state.stage;
  const requestedMonth = state.month;
  state.layerLoading = true;
  updateExportControls();
  updateStatus();
  document.querySelectorAll('.layer-item').forEach((item) => {
    const active = item.dataset.layerId === layer.id;
    item.classList.toggle('active', active);
    if (active) item.setAttribute('aria-current', 'true');
    else item.removeAttribute('aria-current');
  });

  const requestSeq = ++state.fetchSeq;
  let values;
  try {
    values = await fetchLayerValues(layer, requestedStage, requestedMonth, context);
  } catch (error) {
    if (requestSeq === state.fetchSeq && cacheContextIsCurrent(context)) {
      state.activeLayer = previous.layer;
      state.stage = previous.stage;
      state.month = previous.month;
      state.layerLoading = false;
      document.querySelectorAll('.layer-item').forEach((item) => {
        const active = item.dataset.layerId === previous.layer?.id;
        item.classList.toggle('active', active);
        if (active) item.setAttribute('aria-current', 'true');
        else item.removeAttribute('aria-current');
      });
      setExportMessage(`Layer load failed: ${error.message || String(error)}`, 6000);
      updateLegend(previous.layer);
      updateDocsCard(previous.layer);
      updateStageBar();
      updateExportControls();
    }
    return;
  }
  if (requestSeq !== state.fetchSeq || !cacheContextIsCurrent(context)) return;
  // Superseded because the layer, stage, month, or selected cache changed.
  uploadValues(values);

  const [lo, hi] = layerRange(layer);
  three.fillMaterial.uniforms.uMin.value = lo;
  three.fillMaterial.uniforms.uMax.value = hi;
  three.fillMaterial.uniforms.uCategorical.value = isCategoricalLayer(layer) ? 1 : 0;
  state.layerLoading = false;
  state.exportSnapshot = Object.freeze({
    cacheIdentity: context.identity,
    cacheRevision: context.revision,
    manifest: state.manifest,
    world: { ...(state.manifest?.world || {}) },
    cellCount: state.cellCount,
    layer,
    stage: requestedStage,
    month: requestedMonth,
    values,
  });
  updateInspectorStageMarkers();
  updateLegend(layer);
  updateDocsCard(layer);
  updateStageBar();
  prefetchNeighborStages(layer, requestedStage);
  updateExportControls();
  updateStatus();
}

// ---------------------------------------------------------------------------
// Stage / month control

function stageBarConfig() {
  const layer = state.activeLayer;
  if (!layer) return null;
  if (isStageLayer(layer)) {
    const history = (state.manifest?.stage_histories || {})[layer.source] || {};
    return {
      max: (layer.stage_count || 1) - 1,
      value: state.stage,
      label: (value = state.stage) => {
        const meta = (history.stages || [])[value] || {};
        const bits = [`stage_idx ${value}`];
        if (meta.stage !== undefined) bits.push(`stage ${meta.stage}`);
        if (meta.erosion_iteration !== undefined) bits.push(`iter ${meta.erosion_iteration}`);
        return bits.join(' · ');
      },
      set: (value) => activateLayer(layer, { stage: value }),
    };
  }
  if (layer.kind === 'numeric_monthly') {
    return {
      max: (layer.month_count || 12) - 1,
      value: state.month,
      label: (value = state.month) => `month ${value + 1}`,
      set: (value) => activateLayer(layer, { month: value }),
    };
  }
  return null;
}

function updateStageBar() {
  const config = stageBarConfig();
  const bar = $('#stagebar');
  bar.classList.toggle('hidden', !config);
  if (!config) return;
  const slider = $('#stage-slider');
  const number = $('#stage-number');
  slider.max = String(config.max);
  number.max = String(config.max);
  // Don't move the thumb or overwrite the number field while the user is
  // interacting with it (mid-drag or typing); the debounced fetch lands shortly.
  if (document.activeElement !== slider) slider.value = String(config.value);
  if (document.activeElement !== number) number.value = String(config.value);
  $('#stage-label').textContent = config.label();
}

function stepStage(delta) {
  const config = stageBarConfig();
  if (!config) return;
  const next = Math.min(config.max, Math.max(0, config.value + delta));
  if (next !== config.value) config.set(next);
}

// ---------------------------------------------------------------------------
// Layer list panel

function buildLayerList() {
  const container = $('#layer-list');
  container.innerHTML = '';
  const groups = new Map();
  for (const layer of state.manifest.layers) {
    if (!groups.has(layer.source)) groups.set(layer.source, []);
    groups.get(layer.source).push(layer);
  }
  const kindBadge = { numeric_stage: 'stages', categorical_stage: 'stage cat', numeric_monthly: 'monthly', categorical: 'cat' };
  const kindBadgeTitle = {
    numeric_stage: 'varies by stage', categorical_stage: 'categorical, varies by stage',
    numeric_monthly: 'varies by month', categorical: 'categorical',
  };
  let groupIndex = 0;
  for (const [source, layers] of groups) {
    const title = document.createElement('button');
    title.type = 'button';
    title.className = 'layer-group-title';
    title.textContent = `${source} (${layers.length})`;
    container.appendChild(title);
    const body = document.createElement('div');
    body.id = `layer-group-${groupIndex}`;
    groupIndex += 1;
    title.setAttribute('aria-controls', body.id);
    title.setAttribute('aria-expanded', 'true');
    container.appendChild(body);
    title.addEventListener('click', () => {
      const collapsed = !body.hidden;
      body.hidden = collapsed;
      title.setAttribute('aria-expanded', String(!collapsed));
    });
    for (const layer of layers) {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'layer-item';
      item.dataset.layerId = layer.id;
      item.dataset.search = `${layer.source} ${layer.name} ${searchTerms(layer)}`.toLowerCase();
      item.title = layerTooltip(layer);
      item.textContent = layer.name;
      if (kindBadge[layer.kind]) {
        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = kindBadge[layer.kind];
        badge.title = kindBadgeTitle[layer.kind];
        item.appendChild(badge);
      }
      item.addEventListener('click', () => activateLayer(layer));
      body.appendChild(item);
    }
  }
}

function filterLayerList(query) {
  const needle = query.trim().toLowerCase();
  let totalMatches = 0;
  document.querySelectorAll('#layer-list > .layer-group-title').forEach((title) => {
    const body = title.nextElementSibling;
    if (needle && title.dataset.preSearchExpanded === undefined) {
      title.dataset.preSearchExpanded = title.getAttribute('aria-expanded') || 'true';
    } else if (!needle && title.dataset.preSearchExpanded !== undefined) {
      title.setAttribute('aria-expanded', title.dataset.preSearchExpanded);
      delete title.dataset.preSearchExpanded;
    }
    const items = [...body.querySelectorAll('.layer-item')];
    let matches = 0;
    items.forEach((item) => {
      const visible = !needle || item.dataset.search.includes(needle);
      item.hidden = !visible;
      if (visible) matches += 1;
    });
    totalMatches += matches;
    title.hidden = Boolean(needle) && matches === 0;
    body.hidden = Boolean(needle) ? matches === 0 : title.getAttribute('aria-expanded') === 'false';
    if (needle && matches) title.setAttribute('aria-expanded', 'true');
  });
  const empty = $('#layer-list > .layer-list-empty');
  if (needle && totalMatches === 0) {
    if (!empty) {
      const row = document.createElement('div');
      row.className = 'layer-list-empty';
      row.textContent = 'No layers match this filter.';
      $('#layer-list').appendChild(row);
    }
  } else {
    empty?.remove();
  }
}

// ---------------------------------------------------------------------------
// Cell inspector

function inspectorLedgerMarker(historyName) {
  const displayed = state.exportSnapshot;
  return displayed && displayed.cacheIdentity === state.cacheIdentity
    && displayed.cacheRevision === (state.status?.cache_revision ?? null)
    && displayed.values === state.values && isStageLayer(displayed.layer)
    && displayed.layer.source === historyName ? displayed.stage : -1;
}

function updateInspectorStageMarkers() {
  for (const { node, historyName, values } of state.inspectorSparklines) {
    node.innerHTML = sparklineSvg(values, { marker: inspectorLedgerMarker(historyName) });
  }
}

function sparklineSvg(values, { width = 290, height = 30, marker = -1 } = {}) {
  const finite = values.filter((value) => typeof value === 'number' && Number.isFinite(value));
  if (!finite.length) return '';
  const lo = Math.min(...finite);
  const hi = Math.max(...finite);
  const span = hi - lo || 1;
  const step = width / Math.max(values.length - 1, 1);
  const points = values.map((value, index) => {
    const y = typeof value === 'number' && Number.isFinite(value)
      ? height - 3 - ((value - lo) / span) * (height - 6)
      : height - 3;
    return `${(index * step).toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  let markerCircle = '';
  if (marker >= 0 && marker < values.length && Number.isFinite(values[marker])) {
    const mx = (marker * step).toFixed(1);
    const my = (height - 3 - ((values[marker] - lo) / span) * (height - 6)).toFixed(1);
    markerCircle = `<circle cx="${mx}" cy="${my}" r="2.5" fill="#ffb454"/>`;
  }
  return `<svg class="sparkline" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`
    + `<polyline points="${points}" fill="none" stroke="#4da3ff" stroke-width="1.2"/>`
    + markerCircle
    + `</svg>`;
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));
}

async function openInspector(cellId) {
  const context = currentCacheContext();
  if (!cacheContextIsCurrent(context)) return;
  const requestId = ++state.inspectorRequest;
  state.inspectorSparklines = [];
  state.selectedCell = cellId;
  const inspector = $('#inspector');
  // Remember whether focus lives inside the panel: the innerHTML re-render
  // below destroys the focused element, and keyboard users would otherwise
  // be dropped back to <body> on every cell hop.
  const focusWasInside = inspector.contains(document.activeElement);
  inspector.classList.remove('hidden');
  $('#inspector-title').textContent = `Cell ${cellId}`;
  $('#inspector-body').innerHTML = '<em>loading…</em>';
  resizeRenderer();
  let record;
  try {
    record = await fetchJson(
      cacheRevisionUrl(`/api/cell/${cellId}`, context),
    );
  } catch (error) {
    if (requestId !== state.inspectorRequest || state.selectedCell !== cellId
        || !cacheContextIsCurrent(context)) return;
    $('#inspector-body').innerHTML = `<div class="notice warning">The cell record could not be loaded. ${escapeHtml(error.message || String(error))}</div>`;
    return;
  }
  if (requestId !== state.inspectorRequest || state.selectedCell !== cellId
      || !cacheContextIsCurrent(context)) return;

  const cell = record.cell || {};
  const parts = [];
  const ledgerSparklines = [];
  parts.push('<input id="inspector-filter" type="search" placeholder="Filter fields…" aria-label="Filter fields">');
  parts.push(speciesAvailabilityMarkup(cell));
  parts.push(landUseAvailabilityMarkup(cell));

  parts.push('<div class="inspector-section"><h3>Ledger slices (per stage)</h3>');
  for (const [historyName, ledger] of Object.entries(record.ledgers || {})) {
    parts.push(`<div class="spark-row"><span class="k">${escapeHtml(historyName)}</span></div>`);
    for (const [field, values] of Object.entries(ledger.fields)) {
      const numeric = values.filter((value) => typeof value === 'number');
      if (!numeric.length) continue;
      const marker = inspectorLedgerMarker(historyName);
      const index = ledgerSparklines.push({ historyName, values }) - 1;
      parts.push(`<div class="spark-row"><span class="k">${escapeHtml(field)}</span><span data-inspector-ledger="${index}">${sparklineSvg(values, { marker })}</span></div>`);
    }
  }
  parts.push('</div>');

  const monthlyEntries = Object.entries(record.monthly || {});
  if (monthlyEntries.length) {
    parts.push('<div class="inspector-section"><h3>Monthly</h3>');
    for (const [field, values] of monthlyEntries) {
      parts.push(`<div class="spark-row"><span class="k">${escapeHtml(field)}</span>${sparklineSvg(values)}</div>`);
    }
    parts.push('</div>');
  }

  parts.push('<div class="inspector-section"><h3>Fields</h3><div id="inspector-fields">');
  for (const [key, value] of Object.entries(cell)) {
    parts.push(
      `<div class="field-row" data-search="${escapeHtml(key.toLowerCase())}">`
      + `<span class="k" title="${escapeHtml(key)}">${escapeHtml(key)}</span>`
      + `<span class="v">${escapeHtml(formatInspectorValue(cell, key, value))}</span></div>`,
    );
  }
  parts.push('</div></div>');

  const edges = record.adjacency_edges || [];
  parts.push(`<div class="inspector-section"><h3>Adjacency (${edges.length} edges)</h3>`);
  for (const edge of edges) {
    const other = edge.cell_a_id === cellId ? edge.cell_b_id : edge.cell_a_id;
    const otherNumber = Number(other);
    const validOther = Number.isInteger(otherNumber) && otherNumber >= 0 && otherNumber < state.cellCount;
    const otherLabel = escapeHtml(formatValue(other));
    const flags = ['plate_boundary', 'land_water_transition', 'biome_transition']
      .filter((flag) => edge[flag]).join(', ');
    parts.push(
      `<div class="field-row"><span class="k">→ ${validOther ? `<a href="#" data-cell="${otherNumber}" class="cell-link">cell ${otherLabel}</a>` : `cell ${otherLabel}`}`
      + `${flags ? ` <span class="edge-flags">${escapeHtml(flags)}</span>` : ''}</span>`
      + `<span class="v">${escapeHtml(formatValue(edge.great_circle_distance_km))} km</span></div>`,
    );
  }
  parts.push('</div>');

  const body = $('#inspector-body');
  body.innerHTML = parts.join('');
  state.inspectorSparklines = ledgerSparklines.map((entry, index) => ({
    ...entry, node: body.querySelector(`[data-inspector-ledger="${index}"]`),
  })).filter((entry) => entry.node);
  body.querySelector('#inspector-filter').addEventListener('input', (event) => {
    const needle = event.target.value.trim().toLowerCase();
    body.querySelectorAll('#inspector-fields .field-row').forEach((row) => {
      row.style.display = !needle || row.dataset.search.includes(needle) ? '' : 'none';
    });
  });
  body.querySelectorAll('a[data-cell]').forEach((anchor) => {
    anchor.addEventListener('click', (event) => {
      event.preventDefault();
      openInspector(Number(anchor.dataset.cell));
    });
  });
  if (focusWasInside) {
    const title = $('#inspector-title');
    title.setAttribute('tabindex', '-1');
    title.focus({ preventScroll: true });
  }
}

// ---------------------------------------------------------------------------
// Status bar

function updateStatus() {
  const status = $('#status');
  if (state.exportMessage) {
    status.textContent = state.exportMessage;
  } else if (state.layerLoading) {
    status.textContent = 'Loading layer…';
  } else {
    status.textContent = '';
  }
  const layer = state.activeLayer;
  const bits = [];
  if (layer) bits.push(`${layer.source}/${layer.name}`);
  if (state.hoverCell >= 0) {
    bits.push(`cell ${state.hoverCell}`);
    if (state.values && layer) {
      const value = state.values[state.hoverCell];
      if (value !== undefined && value < 1e37) {
        bits.push(isCategoricalLayer(layer)
          ? (layer.categories?.[Math.round(value)] ?? `code ${Math.round(value)}`)
          : formatValue(value));
      } else {
        bits.push('—');
      }
    }
  }
  $('#map-hover').textContent = bits.join('  ·  ');
}

// ---------------------------------------------------------------------------
// Workbench shell and generic data rendering

function jsonText(value) {
  return JSON.stringify(value, null, 2);
}

function jsonPreview(value, limit = 100000) {
  const text = jsonText(value);
  return text.length > limit ? `${text.slice(0, limit)}\n… (${text.length - limit} characters omitted; open raw JSON)` : text;
}

function displayCell(value) {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') {
    const text = JSON.stringify(value);
    return text.length > 600 ? `${text.slice(0, 600)}… (${text.length - 600} chars omitted)` : text;
  }
  return formatValue(value);
}

function tableMarkup(rows, explicitColumns = null) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return '<div class="notice">No records.</div>';
  }
  const normalized = rows.map((row) => {
    if (Array.isArray(row) && explicitColumns) return Object.fromEntries(explicitColumns.map((key, index) => [key, row[index]]));
    if (row && typeof row === 'object' && !Array.isArray(row)) return row;
    return { value: row };
  });
  const columns = explicitColumns || [...new Set(normalized.flatMap((row) => Object.keys(row)))];
  const head = columns.map((column) => `<th scope="col">${escapeHtml(column)}</th>`).join('');
  const body = normalized.map((row) => `<tr>${columns.map((column) => (
    `<td>${escapeHtml(typeof row[column] === 'object' && row[column] !== null ? displayCell(row[column]) : formatInspectorValue(row, column, row[column]))}</td>`
  )).join('')}</tr>`).join('');
  return `<div class="data-table-wrap"><table class="data-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function objectTableMarkup(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return `<pre>${escapeHtml(jsonText(value))}</pre>`;
  }
  const flags = Object.fromEntries(Object.entries(value).filter(([key, item]) => key.includes('availability') && item && typeof item === 'object' && !Array.isArray(item)).flatMap(([, item]) => Object.entries(item).filter(([, flag]) => typeof flag === 'boolean')));
  return tableMarkup(Object.entries(value).map(([key, entry]) => ({ key,
    value: entry === null && (flags[key] === false || value[key.replace(/_index$/, '_supported')] === false || value[SUMMARY_ESTIMATE_SUPPORT[key]] === false)
      ? 'Unavailable' : entry })), ['key', 'value']);
}

function collectionNames(collection) {
  if (Array.isArray(collection)) {
    return collection.map((entry) => {
      if (typeof entry === 'string') return entry;
      return entry?.id ?? entry?.name ?? entry?.key;
    }).filter(Boolean).map(String).sort();
  }
  if (collection && typeof collection === 'object') return Object.keys(collection).sort();
  return [];
}

function collectionCount(collection) {
  if (Array.isArray(collection)) return collection.length;
  if (collection && typeof collection === 'object') return Object.keys(collection).length;
  return 0;
}

function setView(name, { updateHash = true } = {}) {
  const valid = ['map', 'data', 'config', 'operations', 'api'];
  const view = valid.includes(name) ? name : 'map';
  state.activeView = view;
  document.querySelectorAll('[data-view-panel]').forEach((panel) => { panel.hidden = panel.dataset.viewPanel !== view; });
  document.querySelectorAll('.view-tab').forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
    button.tabIndex = active ? 0 : -1;
  });
  // User-initiated switches push a history entry so Back/Forward navigates
  // views; hashchange-driven sync (initial load, Back/Forward) skips this.
  if (updateHash && window.location.hash !== `#${view}`) history.pushState(null, '', `#${view}`);
  if (view === 'map' && state.mapReady) requestAnimationFrame(resizeRenderer);
  if (view === 'data' && state.catalog) loadDataSelection(false);
  if (view === 'operations') refreshJobs();
  if (view === 'api') loadBackend();
}

function applyServerStatus(status) {
  state.status = status || {};
  state.cacheAvailable = Boolean(status?.cache_available);
  const badge = $('#cache-state');
  badge.className = `state-pill ${state.cacheAvailable ? 'available' : 'unavailable'}`;
  badge.textContent = state.cacheAvailable ? 'Cache ready' : 'No cache';
  badge.removeAttribute('title');
  const context = [status?.cache_dir ? `cache ${status.cache_dir}` : null, status?.workspace ? `workspace ${status.workspace}` : null];
  if (status?.cache_error) context.push(`error: ${status.cache_error}`);
  if (status?.version) context.push(`v${status.version}`);
  $('#workspace-state').textContent = context.filter(Boolean).join(' · ');
  $('#workspace-state').title = context.filter(Boolean).join('\n');
  $('#app').classList.toggle('cacheless', !state.cacheAvailable);
  $('#map-empty').classList.toggle('hidden', state.cacheAvailable);
  $('#data-unavailable').classList.toggle('hidden', state.cacheAvailable);
  $('#data-workspace').classList.toggle('hidden', !state.cacheAvailable);
}

function cacheIdentityFor(status) {
  return JSON.stringify([
    Boolean(status?.cache_available),
    status?.cache_dir ?? null,
    status?.cache_revision ?? null,
  ]);
}

function currentCacheContext() {
  return {
    identity: state.cacheIdentity,
    epoch: state.cacheEpoch,
    revision: state.status?.cache_revision ?? null,
  };
}

function cacheContextIsCurrent(context) {
  return Boolean(context)
    && context.identity === state.cacheIdentity
    && context.epoch === state.cacheEpoch
    && context.revision === (state.status?.cache_revision ?? null)
    && state.cacheAvailable;
}

function cacheRevisionUrl(url, context = currentCacheContext()) {
  const parsed = new URL(url, window.location.href);
  if (context?.revision) parsed.searchParams.set('revision', context.revision);
  return `${parsed.pathname}${parsed.search}${parsed.hash}`;
}

function disposeMapScene() {
  state.mapEventController?.abort();
  state.mapEventController = null;
  cancelPlateLinesLoad();
  three.controls?.dispose?.();
  const geometries = new Set();
  const materials = new Set();
  three.scene?.traverse?.((object) => {
    if (object.geometry) geometries.add(object.geometry);
    const objectMaterials = Array.isArray(object.material) ? object.material : [object.material];
    objectMaterials.filter(Boolean).forEach((material) => materials.add(material));
  });
  geometries.forEach((geometry) => geometry.dispose?.());
  materials.forEach((material) => material.dispose?.());
  three.pickMaterial?.dispose?.();
  three.valueTexture?.dispose?.();
  three.colormapTexture?.dispose?.();
  three.pickTarget?.dispose?.();
  three.renderer?.dispose?.();
  Object.keys(three).forEach((key) => { delete three[key]; });
}

// The empty-state copy is rewritten when map initialization fails. Capture the
// default text once so a later no-cache state never shows a stale error.
let mapEmptyDefaultCopy = null;
function mapEmptyElements() {
  const empty = $('#map-empty');
  const title = empty.querySelector('h2');
  const detail = empty.querySelector('p');
  if (!mapEmptyDefaultCopy) {
    mapEmptyDefaultCopy = { title: title.textContent, detail: detail.textContent };
  }
  return { title, detail };
}

function resetCacheDerivedState() {
  if (!$('#help-overlay').classList.contains('hidden')) setHelpVisible(false);
  state.cacheEpoch += 1;
  state.catalogRequest += 1;
  state.mapRequest += 1;
  state.dataRequest += 1;
  state.fetchSeq += 1;
  state.inspectorRequest += 1;
  state.inspectorSparklines = [];
  state.manifest = null;
  state.catalog = null;
  state.catalogLoading = null;
  state.meshInfo = null;
  state.cellCount = 0;
  state.activeLayer = null;
  state.stage = 0;
  state.month = 0;
  state.values = null;
  state.layerCache.clear();
  state.mapReady = false;
  state.mapInitializing = null;
  state.layerLoading = false;
  state.exportSnapshot = null;
  state.exportGeneration += 1;
  state.exportBusy = false;
  state.exportMessage = '';
  state.lastImageExport = null;
  state.dataOffset = 0;
  state.dataTotal = 0;
  state.selectedCell = -1;
  state.hoverCell = -1;
  state.overlays = { wireframe: false, plates: false, graticule: false };
  state.projection = 'globe';
  Object.assign(state.morph, { value: 0, target: 0, proj2D: 0, proj2DTarget: 0 });
  disposeMapScene();

  $('#world-meta').textContent = '';
  $('#layer-list').replaceChildren();
  $('#layer-search').value = '';
  $('#stagebar').classList.add('hidden');
  $('#inspector').classList.add('hidden');
  $('#data-output').replaceChildren();
  $('#data-raw-link').classList.add('hidden');
  $('#data-raw-link').removeAttribute('href');
  $('#data-loading').classList.add('hidden');
  document.querySelectorAll('#projection-controls button').forEach((button) => {
    const active = button.dataset.proj === 'globe';
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  for (const id of ['toggle-wireframe', 'toggle-plates', 'toggle-graticule']) {
    $(`#${id}`).classList.remove('active');
    $(`#${id}`).setAttribute('aria-pressed', 'false');
  }
  const mapEmpty = mapEmptyElements();
  mapEmpty.title.textContent = mapEmptyDefaultCopy.title;
  mapEmpty.detail.textContent = mapEmptyDefaultCopy.detail;
  updatePager();
  updateLegend(null);
  updateDocsCard(null);
  updateExportControls();
  updateStatus();
}

function showStatusRefreshFailure(error) {
  const badge = $('#cache-state');
  badge.className = 'state-pill failed';
  badge.textContent = 'Status unavailable';
  badge.title = `Keeping the last known cache state. ${error.message || String(error)}`;
}

function beginCacheTransition(cacheDir) {
  resetCacheDerivedState();
  state.cacheIdentity = null;
  applyServerStatus({
    ...(state.status || {}),
    cache_available: false,
    cache_dir: cacheDir,
    cache_revision: null,
    cache_error: null,
  });
  const badge = $('#cache-state');
  badge.className = 'state-pill pending';
  badge.textContent = 'Switching cache…';
  // A cache exists — it is loading, not missing. Keep the central CTA honest.
  const mapEmpty = mapEmptyElements();
  mapEmpty.title.textContent = 'Switching cache…';
  mapEmpty.detail.textContent = `Loading the debug cache for ${cacheDir}. The map appears as soon as it is ready.`;
}

async function refreshWorlds({ force = false } = {}) {
  const requestId = ++state.worldRequest;
  const payload = await optionalJson('/api/worlds');
  // A poll may discover another cache while selection is still being applied.
  // Keep the pending destination visible and its control locked until it settles.
  if (requestId !== state.worldRequest || (state.worldSwitching && !force)) return;
  const select = $('#world-select');
  // A transient poll failure must not wipe a previously good list; only show
  // the "unavailable" placeholder when no list was ever loaded.
  if (payload === null && state.worldsSignature !== null) return;
  const worlds = Array.isArray(payload?.worlds) ? payload.worlds : [];
  const current = state.status?.cache_dir ?? '';
  const signature = JSON.stringify([payload === null, current, worlds.map((world) => [
    String(world.cache_dir ?? world.id ?? ''), String(world.name ?? ''), world.cell_count ?? null,
  ])]);
  // Rebuilding the options closes the native dropdown and resets the pending
  // selection, so skip while the user is interacting with it or when the list
  // has not actually changed since the last render.
  if (!force && (document.activeElement === select || signature === state.worldsSignature)) return;
  state.worldsSignature = signature;
  select.innerHTML = '';

  if (current && !worlds.some((world) => String(world.cache_dir ?? world.id) === current)) {
    const option = new Option(`Current · ${current}`, current);
    select.appendChild(option);
  }
  for (const world of worlds) {
    const value = String(world.cache_dir ?? world.id ?? '');
    if (!value || [...select.options].some((option) => option.value === value)) continue;
    const name = String(world.name ?? value);
    const cells = world.cell_count === null || world.cell_count === undefined
      ? ''
      : ` · ${world.cell_count} cells`;
    select.appendChild(new Option(`${name}${cells}`, value));
  }
  if (!select.options.length) {
    select.appendChild(new Option(payload ? 'No workspace caches' : 'Cache list unavailable', ''));
  }
  if (current && [...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
  select.disabled = state.worldSwitching || worlds.length === 0;
}

async function switchWorld() {
  if (state.worldSwitching) return;
  const select = $('#world-select');
  const cacheDir = select.value;
  if (!cacheDir || cacheDir === state.status?.cache_dir) return;
  state.worldSwitching = true;
  select.disabled = true;
  try {
    await fetchJson('/api/worlds/select', {
      method: 'POST',
      body: { cache_dir: cacheDir },
    });
    // The server has switched already; invalidate old mesh/layer requests before
    // asking for the new revision so they cannot commit against the new cache.
    beginCacheTransition(cacheDir);
    await loadServerStatus();
  } catch (error) {
    const badge = $('#cache-state');
    badge.className = 'state-pill failed';
    badge.textContent = 'Switch failed';
    badge.title = error.message || String(error);
    // Rebuild the option list first, then restore the displayed selection to
    // the still-current cache; restoring before the rebuild would be wiped.
    await refreshWorlds({ force: true });
    select.value = state.status?.cache_dir ?? '';
  } finally {
    state.worldSwitching = false;
    // Mirror refreshWorlds: keep the select disabled when it holds only a
    // placeholder option (no switchable caches).
    select.disabled = ![...select.options].some((option) => option.value);
  }
}

async function loadServerStatus() {
  const requestId = ++state.statusRequest;
  let status;
  try {
    status = await fetchJson('/api/status');
  } catch (error) {
    if (requestId !== state.statusRequest) return state.status;
    showStatusRefreshFailure(error);
    return state.status;
  }
  if (requestId !== state.statusRequest) return state.status;

  const nextIdentity = cacheIdentityFor(status);
  if (nextIdentity !== state.cacheIdentity) {
    resetCacheDerivedState();
    state.cacheIdentity = nextIdentity;
  }
  applyServerStatus(status);
  void refreshWorlds();

  if (state.cacheAvailable) {
    const context = currentCacheContext();
    void Promise.allSettled([
      loadCatalog(false, context),
      initializeMap(context),
    ]);
  }
  return status;
}

function validateDisplayMetadata(manifest) {
  const count = manifest.world?.cell_count;
  for (const layer of manifest.layers || []) {
    if ('marine_distance' in layer) {
      const rule = layer.marine_distance;
      if (layer.id !== 'cells/distance_to_marine_water_km' || layer.source !== 'cells'
          || layer.name !== 'distance_to_marine_water_km' || layer.kind !== 'numeric'
          || !rule || typeof rule !== 'object' || Array.isArray(rule)
          || Object.keys(rule).sort().join(',') !== 'no_source_cell_count,status_field'
          || rule.status_field !== 'marine_distance_status' || !Number.isSafeInteger(count)
          || !Number.isSafeInteger(rule.no_source_cell_count) || rule.no_source_cell_count < 0
          || rule.no_source_cell_count > count
          || (rule.no_source_cell_count === count) !== !Object.hasOwn(layer, 'stats')) throw new Error('Invalid marine distance display metadata');
    }
    if ('availability' in layer) {
      const rule = layer.availability;
      if (!rule || typeof rule !== 'object' || Array.isArray(rule)
          || Object.keys(rule).sort().join(',') !== 'field,unavailable_when'
          || typeof rule.field !== 'string' || !['false', 'zero'].includes(rule.unavailable_when)) {
        throw new Error('Invalid layer availability metadata');
      }
    }
    if ('applicability' in layer) {
      const rule = layer.applicability;
      const valid = rule && typeof rule === 'object' && !Array.isArray(rule)
        && ((rule.kind === 'native_exposed_land_v1' && Object.keys(rule).join(',') === 'kind')
            || (rule.kind === 'boolean_field_v1' && ['mining_surface_applicable', 'grounded_ice_surface_applicable'].includes(rule.field)
                && Object.keys(rule).sort().join(',') === 'field,kind'));
      const values = [layer.inapplicable_cell_count, layer.unavailable_cell_count];
      if (!valid || !Number.isSafeInteger(count) || values.some(value => !Number.isSafeInteger(value) || value < 0 || value > count)
          || values[0] + values[1] > count) throw new Error('Invalid layer applicability metadata or counts');
    }
  }
}

async function initializeMap(context = currentCacheContext()) {
  if (!cacheContextIsCurrent(context) || state.mapReady || state.mapInitializing !== null) return;
  const requestId = ++state.mapRequest;
  state.mapInitializing = requestId;
  try {
    const manifest = state.manifest
      || await fetchJson(cacheRevisionUrl('/api/manifest', context));
    if (requestId !== state.mapRequest || !cacheContextIsCurrent(context)) return;
    validateDisplayMetadata(manifest);
    state.manifest = manifest;
    state.cellCount = Number(manifest.world?.cell_count ?? 0);
    const world = manifest.world || {};
  $('#world-meta').innerHTML = [
      `${escapeHtml(world.name ?? 'world')} · ${state.cellCount} cells`,
      `${escapeHtml(world.mesh_backend ?? '')} · scope ${escapeHtml(world.generation_scope ?? 'full')}`,
      `${(manifest.layers || []).length} layers · ${Object.keys(manifest.stage_histories || {}).length} stage histories`,
    ].join('<br>');

    if (!await buildScene(context)) return;
    if (requestId !== state.mapRequest || !cacheContextIsCurrent(context)) return;
    buildLayerList();
    wireMapEvents();
    updateDocsCard(null);
    state.mapReady = true;
    if (!state.animationStarted) {
      state.animationStarted = true;
      animate();
    }

    const initial = manifest.layers?.find((layer) => layer.id === 'cells/elevation_m')
      || manifest.layers?.find((layer) => layer.kind === 'numeric')
      || manifest.layers?.[0];
    if (initial) await activateLayer(initial);
  } catch (error) {
    if (requestId !== state.mapRequest || !cacheContextIsCurrent(context)) return;
    state.mapReady = false;
    $('#map-empty').classList.remove('hidden');
    const mapEmpty = mapEmptyElements();
    mapEmpty.title.textContent = 'The debug cache could not be opened';
    mapEmpty.detail.textContent = `Repair the cache or select another one, then retry. Details: ${error.message || String(error)}`;
  } finally {
    if (state.mapInitializing === requestId) state.mapInitializing = null;
  }
}

// ---------------------------------------------------------------------------
// Complete debug-cache data browser

async function loadCatalog(force = false, context = currentCacheContext()) {
  if (!cacheContextIsCurrent(context)) return null;
  if (state.catalog && !force) return state.catalog;
  if (state.catalogLoading !== null && !force) return null;
  const requestId = ++state.catalogRequest;
  const dataRequest = state.dataRequest;
  state.catalogLoading = requestId;
  try {
    const catalog = await fetchJson(cacheRevisionUrl('/api/catalog', context));
    if (requestId !== state.catalogRequest || !cacheContextIsCurrent(context)) return null;
    validateDisplayMetadata(catalog);
    state.catalog = catalog;
    if (!state.manifest && catalog?.layers) {
      // The layer help can still describe catalog entries before the map manifest is loaded.
      state.manifest = catalog;
    }
    populateDataResources();
    await loadDataSelection(true, context);
    return catalog;
  } catch (error) {
    if (requestId !== state.catalogRequest || !cacheContextIsCurrent(context)) return null;
    // A newer data selection owns the panel even if this refresh is still the
    // latest catalog request. Its pending or committed result must stay intact.
    if (dataRequest === state.dataRequest) {
      $('#data-output').innerHTML = `<div class="notice warning">${escapeHtml(error.message || String(error))}</div>`;
    }
    return null;
  } finally {
    if (state.catalogLoading === requestId) state.catalogLoading = null;
  }
}

function resourcesForKind(kind) {
  const catalog = state.catalog || {};
  if (kind === 'stages') return collectionNames(catalog.stage_histories);
  if (kind === 'families') return collectionNames(catalog.families);
  if (kind === 'sections') return collectionNames(catalog.sections);
  return [];
}

function populateDataResources() {
  const kind = $('#data-kind').value;
  const names = resourcesForKind(kind);
  const resource = $('#data-resource');
  const previous = resource.value;
  resource.innerHTML = '';
  for (const name of names) {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    resource.appendChild(option);
  }
  if (names.includes(previous)) resource.value = previous;
  $('#data-resource-wrap').classList.toggle('hidden', names.length === 0);
  $('#family-detail-wrap').classList.toggle('hidden', kind !== 'families');
  $('#data-page-controls').classList.toggle('hidden', kind !== 'families');
}

function catalogOverviewMarkup(catalog) {
  const metrics = [
    ['Layers', collectionCount(catalog.layers)],
    ['Stage histories', collectionCount(catalog.stage_histories)],
    ['Families', collectionCount(catalog.families)],
    ['Sections', collectionCount(catalog.sections)],
    ['Scalars', collectionCount(catalog.scalars)],
    ['Skipped outputs', collectionCount(catalog.skipped_sections)],
  ];
  const cards = metrics.map(([label, value]) => `<div class="metric-card"><span>${escapeHtml(label)}</span><strong>${value}</strong></div>`).join('');
  const names = collectionNames(catalog.families).slice(0, 40);
  const familyList = names.map((name) => {
    const entry = !Array.isArray(catalog.families) ? catalog.families?.[name] : null;
    const rowCount = entry?.row_count !== undefined
      ? ` · ${escapeHtml(entry.row_count)} rows`
      : '';
    return `<div class="catalog-item"><strong>${escapeHtml(name)}</strong><small>${escapeHtml(entry?.kind ?? 'record family')}${rowCount}</small></div>`;
  }).join('');
  return `<div class="metric-grid">${cards}</div><p class="eyebrow">Record families</p><div class="catalog-list">${familyList || '<p class="muted">No record families.</p>'}</div>`;
}

function setDataTitle(eyebrow, title) {
  $('#data-eyebrow').textContent = eyebrow;
  $('#data-title').textContent = title;
}

function updatePager() {
  const limit = Number($('#data-limit').value || 10);
  const start = state.dataTotal ? state.dataOffset + 1 : 0;
  const end = Math.min(state.dataOffset + limit, state.dataTotal);
  $('#data-page-label').textContent = `${start}–${end} of ${state.dataTotal}`;
  $('#data-prev').disabled = state.dataOffset <= 0;
  $('#data-next').disabled = state.dataOffset + limit >= state.dataTotal;
}

async function loadDataSelection(resetOffset = true, context = currentCacheContext(), requestedOffset = null) {
  if (!state.catalog || !cacheContextIsCurrent(context)) return;
  const requestId = ++state.dataRequest;
  const requestOffset = resetOffset ? 0 : (requestedOffset ?? state.dataOffset);
  const kind = $('#data-kind').value;
  const name = $('#data-resource').value;
  const output = $('#data-output');
  const rawLink = $('#data-raw-link');
  $('#data-loading').classList.remove('hidden');
  try {
    let markup = '';
    let rawUrl = null;
    let dataTotal = 0;
    let eyebrow = 'Catalog';
    let title = 'Overview';
    if (kind === 'overview') {
      markup = catalogOverviewMarkup(state.catalog);
    } else if (kind === 'scalars') {
      eyebrow = 'World metadata';
      title = 'Scalars';
      markup = objectTableMarkup(state.catalog.scalars || {});
    } else if (kind === 'skipped') {
      eyebrow = 'Export diagnostics';
      title = 'Skipped outputs';
      const stageSkips = {};
      for (const [history, metadata] of Object.entries(state.catalog.stage_histories || {})) {
        if (Object.keys(metadata.skipped_layers || {}).length) stageSkips[`${history}.layers`] = metadata.skipped_layers;
        if (Object.keys(metadata.skipped_per_cell_fields || {}).length) stageSkips[`${history}.per_cell_fields`] = metadata.skipped_per_cell_fields;
        if (Object.keys(metadata.skipped_summary_fields || {}).length) stageSkips[`${history}.summary_fields`] = metadata.skipped_summary_fields;
      }
      const skipped = {
        sections: state.catalog.skipped_sections || {},
        cell_fields: state.catalog.cells?.skipped_fields || {},
        cell_layers: state.catalog.cells?.skipped_layers || {},
        monthly_layers: state.catalog.monthly?.skipped_layers || {},
        stage_histories: stageSkips,
      };
      markup = `<pre>${escapeHtml(jsonPreview(skipped))}</pre>`;
    } else if (kind === 'layers') {
      title = 'Layers';
      markup = tableMarkup(state.catalog.layers || []);
    } else if (kind === 'cells') {
      title = 'Cell schema';
      markup = `<pre>${escapeHtml(jsonPreview(state.catalog.cells || {}))}</pre>`;
    } else if (kind === 'sections') {
      eyebrow = 'Model section';
      title = name || 'Sections';
      const url = name
        ? cacheRevisionUrl(`/api/section/${encodeURIComponent(name)}`, context)
        : null;
      const payload = url ? await fetchJson(url) : {};
      rawUrl = url;
      markup = (name === 'summary' ? populationScopeMarkup(state.catalog) : '')
        + `<pre>${escapeHtml(jsonPreview(payload))}</pre>`;
    } else if (kind === 'stages') {
      eyebrow = 'Stage history';
      title = name || 'Stage summaries';
      const url = name
        ? cacheRevisionUrl(`/api/stage-summary/${encodeURIComponent(name)}`, context)
        : null;
      const payload = url ? await fetchJson(url) : { rows: [] };
      rawUrl = url;
      const rows = payload.rows || [];
      markup = tableMarkup(rows.slice(0, 500), payload.columns || null)
        + (rows.length > 500 ? `<div class="notice">Showing 500 of ${rows.length} stages. Open raw JSON for all rows.</div>` : '');
      const extras = Array.isArray(payload.extras) ? payload.extras : [];
      if (extras.length) {
        markup += `<h3>Retained stage extras</h3>${tableMarkup(extras)}`;
      }
      dataTotal = payload.stage_count ?? payload.rows?.length ?? 0;
    } else if (kind === 'families') {
      const limit = Number($('#data-limit').value || 10);
      const detail = $('#family-detail').value;
      title = name || 'Record families';
      const params = new URLSearchParams({
        limit: String(limit), offset: String(requestOffset), detail,
      });
      const url = name
        ? cacheRevisionUrl(`/api/family/${encodeURIComponent(name)}?${params}`, context)
        : null;
      const payload = url ? await fetchJson(url) : { rows: [], total: 0 };
      const returnedDetail = ['full', 'scalars'].includes(payload.detail) ? payload.detail : detail;
      eyebrow = returnedDetail === 'full' ? 'Full nested family' : 'Scalar family view';
      rawUrl = url;
      markup = (name === 'population_regions' ? populationScopeMarkup(state.catalog) : '')
        + familyAvailabilityMarkup(name, payload.rows || [], returnedDetail, payload.availability) + tableMarkup(payload.rows || []);
      dataTotal = Number(payload.total ?? payload.row_count ?? payload.rows?.length ?? 0);
    }
    if (requestId !== state.dataRequest || !cacheContextIsCurrent(context)) return;
    state.dataOffset = requestOffset;
    state.dataTotal = dataTotal;
    setDataTitle(eyebrow, title);
    rawLink.classList.toggle('hidden', !rawUrl);
    if (rawUrl) rawLink.href = rawUrl;
    else rawLink.removeAttribute('href');
    output.innerHTML = markup;
    updatePager();
  } catch (error) {
    if (requestId === state.dataRequest && cacheContextIsCurrent(context)) {
      rawLink.classList.add('hidden');
      rawLink.removeAttribute('href');
      state.dataOffset = requestOffset;
      state.dataTotal = 0;
      updatePager();
      output.innerHTML = `<div class="notice warning">${escapeHtml(error.message || String(error))}</div>`;
    }
  } finally {
    if (requestId === state.dataRequest && cacheContextIsCurrent(context)) $('#data-loading').classList.add('hidden');
  }
}

// ---------------------------------------------------------------------------
// YAML configuration editor and schema reference

async function fetchTemplate(profile) {
  const version = state.configSchema?.['x-magic-geo']?.schema_version;
  if (version !== 2) throw new Error('The current configuration schema is unavailable. Reload the workbench before resetting a profile.');
  const payload = await fetchJson(`/api/config/template?${new URLSearchParams({ profile })}`);
  if (payload?.profile !== profile || payload?.config?.config_version !== version
      || typeof payload?.yaml !== 'string' || !payload.yaml.trim()) {
    throw new Error('The profile template does not match configuration schema 2. Reload the workbench; your YAML has been kept.');
  }
  return payload.yaml;
}

function normalizeProfiles(payload) {
  const source = Array.isArray(payload) ? payload : payload?.profiles ?? payload ?? [];
  if (Array.isArray(source)) return source.map((entry) => (
    typeof entry === 'string' ? { id: entry, label: entry } : {
      id: String(entry.id ?? entry.name ?? entry.profile),
      label: String(entry.label ?? entry.title ?? entry.name ?? entry.id),
    }
  )).filter((entry) => entry.id && entry.id !== 'undefined');
  if (source && typeof source === 'object') return Object.entries(source).map(([id, entry]) => ({
    id,
    label: typeof entry === 'string' ? entry : entry?.label ?? entry?.title ?? id,
  }));
  return [];
}

function resolveSchemaNode(node, root) {
  if (!node?.$ref || !node.$ref.startsWith('#/')) return node || {};
  const resolved = node.$ref.slice(2).split('/').reduce((value, part) => value?.[part.replace(/~1/g, '/').replace(/~0/g, '~')], root);
  if (!resolved) return node;
  const { $ref, ...overrides } = node;
  return { ...resolved, ...overrides };
}

function flattenSchema(schema) {
  const fields = [];
  const seen = new Set();
  function visit(rawNode, path, required = new Set(), depth = 0) {
    const node = resolveSchemaNode(rawNode, schema);
    if (!node || depth > 12) return;
    const properties = node.properties || {};
    const nodeRequired = new Set(node.required || []);
    for (const [name, rawChild] of Object.entries(properties)) {
      const child = resolveSchemaNode(rawChild, schema);
      const fieldPath = path ? `${path}.${name}` : name;
      const key = `${fieldPath}:${child?.title || ''}`;
      if (seen.has(key)) continue;
      seen.add(key);
      let type = child.type;
      if (!type && child.anyOf) type = child.anyOf.map((entry) => resolveSchemaNode(entry, schema).type).filter(Boolean).join(' | ');
      if (!type && child.$ref) type = child.$ref.split('/').at(-1);
      fields.push({
        path: fieldPath,
        type: type || (child.properties ? 'object' : 'value'),
        required: nodeRequired.has(name) || required.has(name),
        description: child.description || child.title || '',
        help: fieldPath === 'climate.reference_infrared_optical_depth'
          ? 'Infrared opacity (tau_ref), a dimensionless column parameter. The seasonal energy budget determines temperature.' : '',
        default: child.default,
        enum: child.enum,
        constant: child.const,
        minimum: child.minimum,
        maximum: child.maximum,
        exclusiveMinimum: child.exclusiveMinimum,
        exclusiveMaximum: child.exclusiveMaximum,
        exactIntegers: child['x-magic-geo-integer-display'],
      });
      if (child.properties || child.$ref) visit(child, fieldPath, nodeRequired, depth + 1);
      const item = child.items ? resolveSchemaNode(child.items, schema) : null;
      if (item?.properties) visit(item, `${fieldPath}[]`, new Set(item.required || []), depth + 1);
    }
  }
  visit(schema, '');
  return fields;
}

function schemaValueText(field, key, value) {
  const exact = field.exactIntegers?.[key];
  if (typeof value === 'number' && Number.isInteger(value) && !Number.isSafeInteger(value)) {
    if (typeof exact === 'string' && /^-?(0|[1-9]\d*)$/.test(exact) && Number(exact) === value) return exact;
    if (field.type === 'integer' || exact !== undefined) return 'exact integer unavailable';
  }
  return key === 'default' || key === 'const' ? displayCell(value) : String(value);
}

function renderSchemaDocs(query = '') {
  const needle = query.trim().toLowerCase();
  const matches = state.schemaFields.filter((field) => !needle || `${field.path} ${field.type} ${field.description} ${field.help || ''}`.toLowerCase().includes(needle));
  $('#schema-docs').innerHTML = matches.map((field) => {
    const defaultText = field.default !== undefined ? `Default: ${schemaValueText(field, 'default', field.default)}` : '';
    const enumText = field.enum ? `Choices: ${field.enum.join(', ')}` : '';
    const constraints = [
      field.constant !== undefined ? `Fixed value: ${schemaValueText(field, 'const', field.constant)}` : '',
      field.minimum !== undefined ? `Minimum: ${schemaValueText(field, 'minimum', field.minimum)} (inclusive)` : '',
      field.maximum !== undefined ? `Maximum: ${schemaValueText(field, 'maximum', field.maximum)} (inclusive)` : '',
      field.exclusiveMinimum !== undefined ? `Greater than: ${schemaValueText(field, 'exclusiveMinimum', field.exclusiveMinimum)}` : '',
      field.exclusiveMaximum !== undefined ? `Less than: ${schemaValueText(field, 'exclusiveMaximum', field.exclusiveMaximum)}` : '',
    ];
    return `<article class="schema-field"><div><code>${escapeHtml(field.path)}</code><span class="schema-meta">${escapeHtml(field.type)}${field.required ? ' · required' : ''}</span></div>`
      + `<p>${escapeHtml(field.description || 'No field description provided.')}</p>`
      + (field.help ? `<p>${escapeHtml(field.help)}</p>` : '')
      + `<small>${escapeHtml([defaultText, enumText, ...constraints].filter(Boolean).join(' · '))}</small></article>`;
  }).join('') || '<p class="muted">No schema fields match this filter.</p>';
}

async function resetConfigTemplate() {
  const profile = $('#config-profile').value;
  if (!profile) return;
  if (state.configEditRevision > 0
      && !window.confirm('Replace the current YAML with the profile template?')) return;
  const requestId = ++state.configTemplateRequest;
  const resultRequest = ++state.configResultRequest;
  const editor = $('#config-yaml');
  const editRevision = state.configEditRevision;
  const editorValue = editor.value;
  $('#config-result').className = 'validation-result';
  $('#config-result').textContent = `Loading ${profile} template…`;
  try {
    const template = await fetchTemplate(profile);
    if (requestId !== state.configTemplateRequest || $('#config-profile').value !== profile) return;
    if (state.configEditRevision !== editRevision || editor.value !== editorValue) {
      if (resultRequest === state.configResultRequest) {
        $('#config-result').textContent = `The ${profile} template was not applied because the YAML changed while it loaded. Choose Reset from profile to replace it.`;
      }
      return;
    }
    editor.value = template;
    state.configEditRevision = 0;
    // Applying a template changes the editor even if validation or saving was
    // started while it loaded. Those earlier YAML results are now obsolete.
    state.configResultRequest += 1;
    updateSavedConfigControls();
    $('#config-result').className = 'validation-result';
    $('#config-result').textContent = `Loaded the ${profile} template. Validate after making changes.`;
  } catch (error) {
    if (requestId !== state.configTemplateRequest || resultRequest !== state.configResultRequest || $('#config-profile').value !== profile) return;
    $('#config-result').className = 'validation-result invalid';
    $('#config-result').textContent = error.message || String(error);
  }
}

function validationErrorMarkup(payload) {
  const detail = payload?.detail ?? payload?.errors ?? payload ?? [];
  const errors = (!Array.isArray(detail) && Array.isArray(detail?.issues) && detail.issues.length)
    ? detail.issues : detail;
  const list = Array.isArray(errors) ? errors : [errors];
  return list.filter(Boolean).map((error) => {
    if (typeof error === 'string') return `<li>${escapeHtml(error)}</li>`;
    const location = Array.isArray(error.loc) ? error.loc.join('.')
      : Array.isArray(error.location) ? error.location.join('.')
        : error.path ?? error.field ?? '';
    const sourceLocation = error.line !== undefined
      ? `${error.source ?? 'YAML'}:${error.line}${error.column !== undefined ? `:${error.column}` : ''}` : '';
    const prefix = [sourceLocation, location].filter(Boolean).join(' · ');
    return `<li>${prefix ? `<code>${escapeHtml(prefix)}</code>: ` : ''}${escapeHtml(error.msg ?? error.message ?? JSON.stringify(error))}</li>`;
  }).join('');
}

async function validateConfig() {
  const result = $('#config-result');
  const button = $('#config-validate');
  const requestId = ++state.configResultRequest;
  const yaml = $('#config-yaml').value;
  button.disabled = true;
  result.className = 'validation-result';
  result.textContent = 'Validating…';
  try {
    const payload = await fetchJson('/api/config/validate', { method: 'POST', body: { yaml } });
    if (requestId !== state.configResultRequest || yaml !== $('#config-yaml').value) return false;
    const valid = payload?.valid ?? payload?.ok ?? payload?.errors?.length === 0;
    result.className = `validation-result ${valid ? 'valid' : 'invalid'}`;
    result.innerHTML = valid
      ? `✓ ${escapeHtml(payload?.message ?? 'Configuration is valid.')}`
      : `<strong>Configuration is not valid.</strong><ul>${validationErrorMarkup(payload)}</ul>`;
    return valid;
  } catch (error) {
    if (requestId !== state.configResultRequest || yaml !== $('#config-yaml').value) return false;
    const detail = error.payload?.detail;
    result.className = 'validation-result invalid';
    result.innerHTML = detail
      ? `<strong>Configuration is not valid.</strong><ul>${validationErrorMarkup({ detail })}</ul>`
      : escapeHtml(error.message || String(error));
    return false;
  } finally {
    button.disabled = false;
  }
}

function configNameRaw() {
  return $('#config-name').value.trim() || 'world';
}

function configFilename() {
  const safe = configNameRaw().replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^[-.]+/, '') || 'world';
  return safe.endsWith('.yaml') || safe.endsWith('.yml') ? safe : `${safe}.yaml`;
}

function downloadConfig() {
  downloadBlob(new Blob([$('#config-yaml').value], { type: 'text/yaml;charset=utf-8' }), configFilename());
}

function updateSavedConfigControls() {
  const saved = state.savedConfig;
  const current = saved && saved.yaml === $('#config-yaml').value && saved.name === configNameRaw();
  $('#config-generate').disabled = !current;
  $('#config-saved-status').textContent = saved
    ? `Saved ${saved.path}.${current ? ' Ready to generate.' : ' Save the current edits to generate them.'}`
    : 'Save a configuration to use it in generation.';
}

function configEdited(yamlChanged = true) {
  if (yamlChanged) state.configEditRevision += 1;
  state.configResultRequest += 1;
  $('#config-result').className = 'validation-result';
  $('#config-result').textContent = 'Configuration changed. Validate to check the current YAML.';
  updateSavedConfigControls();
}

function generateFromSavedConfig() {
  if (!state.savedConfig || $('#config-generate').disabled) return;
  $('#operation-select').value = 'generate';
  renderOperationForm();
  const config = $('#operation-fields').querySelector('[name="config"]');
  if (!config) return;
  config.value = state.savedConfig.path;
  setView('operations');
  config.focus();
  $('#operation-result').textContent = `Using ${state.savedConfig.path}. Review the output paths and start the job.`;
}

async function saveConfig() {
  const result = $('#config-result');
  const nameInput = $('#config-name');
  if (!nameInput.checkValidity()) {
    nameInput.reportValidity();
    return;
  }
  const button = $('#config-save');
  const requestId = ++state.configResultRequest;
  // Retries must save exactly the name and text whose overwrite was reviewed.
  const snapshot = { yaml: $('#config-yaml').value, name: configNameRaw() };
  button.disabled = true;
  result.className = 'validation-result';
  result.textContent = 'Saving…';
  const submit = async (force) => fetchJson('/api/config/save', {
    method: 'POST',
    body: {
      ...snapshot,
      force,
    },
  });
  const showSaved = (payload, replaced = false) => {
    if (payload?.path) state.savedConfig = { ...snapshot, path: payload.path };
    updateSavedConfigControls();
    if (requestId !== state.configResultRequest) return;
    result.className = 'validation-result valid';
    result.textContent = `${replaced ? 'Replaced' : 'Saved'} ${payload?.path ?? snapshot.name}.`;
  };
  try {
    const payload = await submit(false);
    showSaved(payload);
  } catch (error) {
    if (requestId !== state.configResultRequest) return;
    if (error.status === 409 && window.confirm(`The configuration "${snapshot.name}" already exists. Replace it with the submitted YAML?`)) {
      try {
        const payload = await submit(true);
        showSaved(payload, true);
        return;
      } catch (overwriteError) {
        error = overwriteError;
      }
    }
    if (requestId !== state.configResultRequest) return;
    result.className = 'validation-result invalid';
    result.textContent = error.message || String(error);
  } finally {
    button.disabled = false;
  }
}

async function loadConfigWorkbench() {
  const requestId = ++state.configWorkbenchRequest;
  state.configTemplateRequest += 1;
  const editRevisionAtStart = state.configEditRevision;
  const resultRequestAtStart = state.configResultRequest;
  const editorValueAtStart = $('#config-yaml').value;
  const select = $('#config-profile');
  const previousProfile = select.value;
  select.disabled = true;
  $('#config-reset').disabled = true;
  state.configSchema = null;
  state.schemaFields = [];
  select.innerHTML = '';
  $('#config-schema-status').textContent = 'Loading the current configuration schema…';
  $('#schema-docs').innerHTML = '';
  try {
    const [schemaPayload, profilePayload] = await Promise.all([
      fetchJson('/api/config/schema'),
      fetchJson('/api/config/profiles'),
    ]);
    if (requestId !== state.configWorkbenchRequest) return;
    const schema = schemaPayload?.schema ?? schemaPayload;
    const metadata = schema?.['x-magic-geo'];
    const profiles = normalizeProfiles(profilePayload);
    const declaredProfiles = metadata?.profiles;
    if (metadata?.schema_version !== 2 || schema?.properties?.config_version?.const !== 2
        || !Array.isArray(declaredProfiles) || !declaredProfiles.length
        || declaredProfiles.some((profile) => profile?.values?.config_version !== 2)
        || !profiles.length || new Set(profiles.map((profile) => profile.id)).size !== profiles.length
        || profiles.length !== declaredProfiles.length
        || profiles.some((profile) => !declaredProfiles.some((entry) => entry.name === profile.id))
        || !profiles.some((profile) => profile.id === profilePayload?.default)) {
      throw new Error('Configuration schema and profiles must declare the current version 2. Reload the workbench; your YAML has been kept.');
    }
    state.configSchema = schema;
    state.schemaFields = flattenSchema(schema);
    renderSchemaDocs($('#schema-search').value);
    for (const profile of profiles) {
      const option = document.createElement('option');
      option.value = profile.id;
      option.textContent = profile.label;
      option.title = declaredProfiles.find((entry) => entry.name === profile.id)?.description || '';
      select.appendChild(option);
    }
    select.value = profiles.some((profile) => profile.id === previousProfile) ? previousProfile : profilePayload.default;
    select.disabled = false;
    $('#config-reset').disabled = false;
    $('#config-schema-status').textContent = 'Schema 2 · Seasonal energy model · config_version: 2 is required.';
    if (!editorValueAtStart && state.configEditRevision === editRevisionAtStart
        && $('#config-yaml').value === editorValueAtStart && state.configResultRequest === resultRequestAtStart) {
      await resetConfigTemplate();
    } else if (state.configResultRequest === resultRequestAtStart) {
      $('#config-result').textContent = 'Profiles loaded. Your YAML was kept; use Reset from profile to replace it.';
    }
  } catch (error) {
    if (requestId !== state.configWorkbenchRequest) return;
    $('#config-schema-status').textContent = 'Current schema and profiles are unavailable.';
    $('#schema-docs').innerHTML = `<div class="notice warning">${escapeHtml(error.message || String(error))}</div>`;
    if (state.configResultRequest === resultRequestAtStart) {
      $('#config-result').className = 'validation-result invalid';
      $('#config-result').textContent = 'Profile loading failed. Your YAML was kept; validation, saving and downloading remain available.';
    }
  }
}

// ---------------------------------------------------------------------------
// Generic operations and background jobs

function normalizeOperations(payload) {
  const source = Array.isArray(payload) ? payload : payload?.operations ?? payload ?? [];
  if (Array.isArray(source)) return source.map((entry) => (
    typeof entry === 'string' ? { name: entry, title: entry } : {
      ...entry,
      name: String(entry.name ?? entry.id ?? entry.operation),
      title: String(entry.title ?? entry.label ?? entry.name ?? entry.id ?? entry.operation),
    }
  )).filter((entry) => entry.name && entry.name !== 'undefined');
  if (source && typeof source === 'object') return Object.entries(source).map(([name, entry]) => ({
    ...(typeof entry === 'object' ? entry : {}), name,
    title: typeof entry === 'string' ? entry : entry?.title ?? entry?.label ?? name,
  }));
  return [];
}

function operationArguments(operation) {
  const schema = operation?.arguments ?? operation?.parameters ?? operation?.options ?? operation?.fields ?? operation?.schema ?? {};
  if (Array.isArray(schema)) return schema.map((argument) => ({
    ...argument,
    name: String(argument.name ?? argument.id ?? argument.key),
    type: argument.type ?? argument.kind ?? 'string',
    required: Boolean(argument.required),
  }));
  const properties = schema.properties ?? schema;
  const required = new Set(schema.required || operation?.required || []);
  if (!properties || typeof properties !== 'object') return [];
  return Object.entries(properties).map(([name, descriptor]) => ({
    ...(descriptor && typeof descriptor === 'object' ? descriptor : { type: descriptor }),
    name,
    type: descriptor?.type ?? descriptor?.kind ?? 'string',
    required: required.has(name) || Boolean(descriptor?.required),
  }));
}

function renderOperationForm() {
  const operation = state.operations.find((entry) => entry.name === $('#operation-select').value);
  const unavailable = operation && operation.available === false;
  $('#operation-description').textContent = `${operation?.description ?? operation?.help ?? 'No description supplied.'}${unavailable ? ` This operation is unavailable${operation.dependency ? ` until ${operation.dependency} is installed` : ''}.` : ''}`;
  $('#operation-form').querySelector('button[type="submit"]').disabled = state.operationSubmitting || !operation || unavailable;
  const fields = $('#operation-fields');
  fields.innerHTML = '';
  for (const argument of operationArguments(operation)) {
    const wrapper = document.createElement('div');
    wrapper.className = `operation-field ${['object', 'array', 'path_list'].includes(argument.type) ? 'full' : ''}`;
    const id = `operation-arg-${argument.name.replace(/[^A-Za-z0-9_-]/g, '-')}`;
    const label = document.createElement('label');
    label.htmlFor = id;
    label.innerHTML = `${escapeHtml(argument.label ?? argument.title ?? argument.name)}${argument.required ? ' <small>required</small>' : ''}`;
    wrapper.appendChild(label);
    const choices = argument.enum ?? argument.choices;
    let input;
    if (Array.isArray(choices)) {
      input = document.createElement('select');
      if (!argument.required) input.appendChild(new Option('—', ''));
      choices.forEach((choice) => input.appendChild(new Option(String(choice), String(choice))));
    } else if (argument.type === 'boolean' || typeof argument.default === 'boolean') {
      input = document.createElement('select');
      input.appendChild(new Option('Default', ''));
      input.appendChild(new Option('Yes', 'true'));
      input.appendChild(new Option('No', 'false'));
    } else if (argument.type === 'object' || argument.type === 'array' || argument.type === 'path_list') {
      input = document.createElement('textarea');
      input.placeholder = argument.type === 'path_list' ? 'One path per line' : argument.type === 'array' ? '["value"]' : '{"key": "value"}';
    } else {
      input = document.createElement('input');
      input.type = ['integer', 'number'].includes(argument.type) ? 'number' : 'text';
      if (argument.type === 'integer') input.step = '1';
      if (argument.type === 'number') input.step = 'any';
      if (argument.minimum !== undefined) input.min = String(argument.minimum);
      if (argument.maximum !== undefined) input.max = String(argument.maximum);
      input.placeholder = argument.placeholder ?? '';
    }
    input.id = id;
    input.name = argument.name;
    input.dataset.valueType = argument.type ?? typeof argument.default ?? 'string';
    input.required = Boolean(argument.required);
    if (argument.default !== undefined && argument.default !== null) {
      input.value = typeof argument.default === 'object' ? JSON.stringify(argument.default, null, 2) : String(argument.default);
    }
    wrapper.appendChild(input);
    if (argument.description ?? argument.help) {
      const help = document.createElement('span');
      help.className = 'field-help';
      help.textContent = argument.description ?? argument.help;
      wrapper.appendChild(help);
    }
    fields.appendChild(wrapper);
  }
}

function collectOperationArguments() {
  const argumentsObject = {};
  for (const input of $('#operation-fields').querySelectorAll('[name]')) {
    const raw = input.value.trim();
    if (!raw) continue;
    const type = input.dataset.valueType;
    if (type === 'integer') argumentsObject[input.name] = Number(raw);
    else if (type === 'number') argumentsObject[input.name] = Number(raw);
    else if (type === 'boolean') argumentsObject[input.name] = raw === 'true';
    else if (type === 'array' || type === 'object') {
      try {
        argumentsObject[input.name] = JSON.parse(raw);
      } catch (error) {
        throw new Error(`${input.name}: invalid JSON — ${error.message}`);
      }
    }
    else if (type === 'path_list') argumentsObject[input.name] = raw.split(/\r?\n/).map((value) => value.trim()).filter(Boolean);
    else argumentsObject[input.name] = raw;
  }
  return argumentsObject;
}

async function submitOperation(event) {
  event.preventDefault();
  if (state.operationSubmitting) return;
  const result = $('#operation-result');
  const submitButton = $('#operation-form').querySelector('button[type="submit"]');
  const selectionRequest = state.jobSelectionRequest;
  state.operationSubmitting = true;
  submitButton.disabled = true;
  result.textContent = 'Starting job…';
  try {
    const payload = await fetchJson('/api/jobs', {
      method: 'POST',
      body: { operation: $('#operation-select').value, arguments: collectOperationArguments() },
    });
    const submittedJobId = String(payload?.id ?? payload?.job_id ?? '');
    result.textContent = `Started job ${submittedJobId}.`;
    await refreshJobs();
    if (submittedJobId && selectionRequest === state.jobSelectionRequest) {
      await selectJob(submittedJobId, { automatic: true });
    }
  } catch (error) {
    result.innerHTML = `<div class="notice warning">The job could not be started. ${escapeHtml(error.message || String(error))}</div>`;
  } finally {
    state.operationSubmitting = false;
    const operation = state.operations.find((entry) => entry.name === $('#operation-select').value);
    submitButton.disabled = !operation || operation.available === false;
  }
}

function normalizeJobs(payload) {
  const jobs = Array.isArray(payload) ? payload : payload?.jobs ?? [];
  return jobs.map((job) => ({ ...job, id: String(job.id ?? job.job_id) }));
}

function jobStatus(job) {
  return String(job?.status ?? job?.state ?? 'unknown').toLowerCase();
}

function jobIsActive(job) {
  return ['pending', 'queued', 'running', 'cancelling', 'canceling'].includes(jobStatus(job));
}

function renderJobs() {
  const list = $('#jobs-list');
  // Re-rendering replaces every row node, so skip it while the visible
  // selection/id/status shape is unchanged: polling must not drop keyboard
  // focus or swap a node out from under a click.
  const signature = `${state.selectedJobId}|${state.jobs.map((job) => `${job.id}:${jobStatus(job)}`).join('|')}`;
  if (signature === state.jobsSignature) return;
  state.jobsSignature = signature;
  if (!state.jobs.length) {
    list.innerHTML = '<p class="muted">No jobs have been submitted.</p>';
    return;
  }
  list.innerHTML = '';
  for (const job of state.jobs) {
    const button = document.createElement('button');
    button.type = 'button';
    const isSelected = state.selectedJobId === job.id;
    button.className = `job-row ${isSelected ? 'active' : ''}`;
    const operation = job.operation ?? job.name ?? 'job';
    const status = jobStatus(job);
    // Concise accessible name; the grid layout stays purely visual.
    button.setAttribute('aria-label', `${operation}, status ${status}`);
    if (isSelected) button.setAttribute('aria-current', 'true');
    button.innerHTML = `<strong>${escapeHtml(operation)}</strong><span class="state-pill ${escapeHtml(status)}">${escapeHtml(status)}</span>`
      + `<small>${escapeHtml(job.id)}</small><small>${escapeHtml(job.created_at ?? job.started_at ?? '')}</small>`;
    button.addEventListener('click', () => selectJob(job.id));
    list.appendChild(button);
  }
}

function artifactMarkup(artifacts, jobId) {
  const list = Array.isArray(artifacts) ? artifacts : artifacts && typeof artifacts === 'object'
    ? Object.entries(artifacts).map(([name, value]) => (typeof value === 'object' ? { name, ...value } : { name, path: value }))
    : [];
  if (!list.length) return '';
  return '<div class="artifact-list"><p class="eyebrow">Artifacts</p>' + list.map((artifact, index) => {
    const name = artifact.name ?? artifact.label ?? artifact.path ?? 'artifact';
    const url = artifact.url ?? artifact.download_url ?? artifact.href
      ?? (artifact.available && jobId ? `/api/jobs/${encodeURIComponent(jobId)}/artifacts/${index}` : null);
    // Only allow same-origin paths and http(s) URLs: escapeHtml neutralizes
    // markup in the href but not a javascript: scheme from server data.
    if (url && (/^\//.test(url) || /^https?:\/\//i.test(url))) {
      return `<a href="${escapeHtml(url)}" download>${escapeHtml(name)} ↓</a>`;
    }
    return `<div class="catalog-item"><strong>${escapeHtml(name)}</strong><small>${escapeHtml(artifact.path ?? artifact.kind ?? '')}</small></div>`;
  }).join('') + '</div>';
}

function renderJobDetail(job) {
  if (!job) return;
  const status = jobStatus(job);
  $('#job-detail-title').textContent = `${job.operation ?? job.name ?? 'Job'} · ${job.id ?? job.job_id}`;
  const reportedProgress = job.progress ?? job.progress_fraction ?? undefined;
  const progressRaw = Number(reportedProgress ?? (['succeeded', 'completed'].includes(status) ? 1 : 0));
  const progress = progressRaw <= 1 ? progressRaw * 100 : progressRaw;
  // The server reports no progress field for active jobs; a bar pinned at 0%
  // would imply no work has happened, so render an indeterminate bar instead.
  const progressMarkup = jobIsActive(job) && reportedProgress === undefined
    ? '<progress class="job-progress" max="100"></progress>'
    : `<progress class="job-progress" max="100" value="${Math.max(0, Math.min(100, progress || 0))}">${formatValue(progress)}%</progress>`;
  const logs = Array.isArray(job.logs) ? job.logs.join('\n') : job.logs ?? job.log ?? job.message ?? '';
  const meta = [
    ['Status', status], ['Created', job.created_at], ['Started', job.started_at],
    ['Finished', job.finished_at ?? job.completed_at], ['Error', job.error],
  ].filter(([, value]) => value !== undefined && value !== null && value !== '');
  $('#job-detail').innerHTML = `<span class="state-pill ${escapeHtml(status)}">${escapeHtml(status)}</span>`
    + progressMarkup
    + `<dl class="job-meta">${meta.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(displayCell(value))}</dd>`).join('')}</dl>`
    + `<p class="eyebrow">Arguments</p><pre class="json-block">${escapeHtml(jsonText(job.arguments ?? {}))}</pre>`
    + `<p class="eyebrow" style="margin-top:12px">Logs</p><pre class="job-log">${escapeHtml(String(logs || 'No log output.'))}</pre>`
    + artifactMarkup(job.artifacts ?? job.outputs, job.id ?? job.job_id);
  $('#job-cancel').classList.toggle('hidden', !jobIsActive(job));
}

async function selectJob(id, { preserveScroll = false, automatic = false } = {}) {
  if (!automatic) state.jobSelectionRequest += 1;
  const changingJob = state.selectedJobId !== String(id);
  state.selectedJobId = String(id);
  const requestId = ++state.jobDetailRequest;
  const oldLog = $('#job-detail').querySelector('.job-log');
  const oldScroll = oldLog?.scrollTop ?? 0;
  const wasAtBottom = oldLog ? oldLog.scrollHeight - oldLog.clientHeight - oldScroll < 8 : true;
  if (changingJob) {
    state.selectedJobStatus = null;
    $('#job-cancel').classList.add('hidden');
    $('#job-detail-title').textContent = `Loading job ${id}…`;
    $('#job-detail').textContent = 'Loading job details…';
  }
  renderJobs();
  try {
    const job = await fetchJson(`/api/jobs/${encodeURIComponent(id)}`);
    if (requestId !== state.jobDetailRequest || state.selectedJobId !== String(id)) return;
    state.selectedJobStatus = jobStatus(job);
    renderJobDetail({ ...job, id: String(job.id ?? job.job_id ?? id) });
    if (preserveScroll) {
      const newLog = $('#job-detail').querySelector('.job-log');
      if (newLog) newLog.scrollTop = wasAtBottom ? newLog.scrollHeight : oldScroll;
    }
  } catch (error) {
    if (requestId !== state.jobDetailRequest || state.selectedJobId !== String(id)) return;
    $('#job-detail').innerHTML = `<div class="notice warning">${escapeHtml(error.message || String(error))}</div>`;
  }
}

async function refreshJobs() {
  const requestId = ++state.jobListRequest;
  let payload;
  try {
    payload = await fetchJson('/api/jobs');
  } catch (error) {
    if (requestId === state.jobListRequest) {
      $('#jobs-poll-state').className = 'state-pill failed';
      $('#jobs-poll-state').textContent = 'Offline';
      $('#jobs-poll-state').title = error.message || String(error);
    }
    return;
  }
  if (requestId !== state.jobListRequest) return;
  $('#jobs-poll-state').className = 'state-pill available';
  $('#jobs-poll-state').textContent = 'Live';
  $('#jobs-poll-state').title = '';
  state.jobs = normalizeJobs(payload);
  renderJobs();
  if (state.selectedJobId) {
    const selected = state.jobs.find((job) => job.id === state.selectedJobId);
    if (!selected) {
      // The job vanished server-side (restart or pruning); drop the stale
      // detail view instead of offering a Cancel button that would 404.
      state.selectedJobId = null;
      state.selectedJobStatus = null;
      $('#job-detail-title').textContent = 'No job selected';
      $('#job-detail').innerHTML = '<div class="notice warning">The selected job is no longer available — it was removed from the server.</div>';
      $('#job-cancel').classList.add('hidden');
      state.jobsSignature = null;
      renderJobs();
    } else if (jobIsActive(selected) || jobStatus(selected) !== state.selectedJobStatus) {
      await selectJob(selected.id, { preserveScroll: true, automatic: true });
    }
  }
}

async function cancelSelectedJob() {
  if (!state.selectedJobId) return;
  const jobId = state.selectedJobId;
  if (!window.confirm('Cancel this job?')) return;
  const button = $('#job-cancel');
  button.disabled = true;
  try {
    await fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });
    await refreshJobs();
    if (state.selectedJobId === jobId) await selectJob(jobId, { automatic: true });
  } catch (error) {
    if (state.selectedJobId === jobId) {
      $('#job-detail').insertAdjacentHTML('afterbegin', `<div class="notice warning">${escapeHtml(error.message || String(error))}</div>`);
    }
  } finally {
    button.disabled = false;
  }
}

async function loadOperations() {
  const payload = await optionalJson('/api/operations');
  state.operations = normalizeOperations(payload);
  const select = $('#operation-select');
  select.innerHTML = '';
  for (const operation of state.operations) {
    const option = document.createElement('option');
    option.value = operation.name;
    option.textContent = operation.title;
    select.appendChild(option);
  }
  if (!state.operations.length) {
    select.appendChild(new Option('No operations available', ''));
    $('#operation-form').querySelector('button[type="submit"]').disabled = true;
  }
  renderOperationForm();
  await refreshJobs();
}

// ---------------------------------------------------------------------------
// Backend/API view and workbench event wiring

async function loadBackend() {
  const requestId = ++state.backendRequest;
  const output = $('#backend-output');
  output.innerHTML = '<span class="state-pill pending">Loading…</span>';
  try {
    const payload = await fetchJson('/api/backend');
    if (requestId !== state.backendRequest) return;
    output.innerHTML = `<pre>${escapeHtml(jsonText(payload))}</pre>`;
  } catch (error) {
    if (requestId !== state.backendRequest) return;
    output.innerHTML = `<div class="notice warning">${escapeHtml(error.message || String(error))}</div>`;
  }
}

function wireWorkbenchEvents() {
  document.querySelectorAll('.view-tab').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
  $('#view-tabs').addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const tabs = [...document.querySelectorAll('.view-tab')];
    const current = Math.max(0, tabs.indexOf(document.activeElement));
    const next = event.key === 'Home' ? 0
      : event.key === 'End' ? tabs.length - 1
        : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    tabs[next].focus();
    tabs[next].click();
  });
  document.querySelectorAll('[data-go-view]').forEach((button) => button.addEventListener('click', () => {
    setView(button.dataset.goView);
    document.querySelector(`.view-tab[data-view="${button.dataset.goView}"]`)?.focus();
  }));
  window.addEventListener('hashchange', () => setView(window.location.hash.slice(1), { updateHash: false }));
  $('#brand').addEventListener('click', (event) => { event.preventDefault(); setView('map'); });
  $('#world-select').addEventListener('change', switchWorld);

  // Help is reachable without a cache, so it is wired here rather than in
  // wireMapEvents(), which only runs after a successful map initialization.
  $('#toggle-help').addEventListener('click', () => setHelpVisible($('#help-overlay').classList.contains('hidden')));
  $('#docs-help-open').addEventListener('click', () => setHelpVisible(true));
  $('#help-close').addEventListener('click', () => setHelpVisible(false));
  $('#help-overlay').addEventListener('click', (event) => {
    if (event.target === $('#help-overlay')) setHelpVisible(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !$('#help-overlay').classList.contains('hidden')) {
      setHelpVisible(false);
      event.stopPropagation();
      return;
    }
    if (event.key !== '?' || event.target.closest('input, textarea, select')) return;
    event.preventDefault();
    setHelpVisible($('#help-overlay').classList.contains('hidden'));
  });

  $('#data-refresh').addEventListener('click', () => loadCatalog(true));
  $('#data-kind').addEventListener('change', () => { populateDataResources(); loadDataSelection(true); });
  $('#data-resource').addEventListener('change', () => loadDataSelection(true));
  $('#family-detail').addEventListener('change', () => loadDataSelection(true));
  $('#data-limit').addEventListener('change', () => loadDataSelection(true));
  $('#data-prev').addEventListener('click', () => {
    const offset = Math.max(0, state.dataOffset - Number($('#data-limit').value || 10));
    loadDataSelection(false, currentCacheContext(), offset);
  });
  $('#data-next').addEventListener('click', () => {
    const offset = state.dataOffset + Number($('#data-limit').value || 10);
    loadDataSelection(false, currentCacheContext(), offset);
  });

  $('#config-profile').addEventListener('change', () => {
    // Selecting a source profile is non-destructive. Only the explicit Reset
    // button is allowed to replace YAML that may contain unsaved edits.
    state.configTemplateRequest += 1;
    state.configResultRequest += 1;
    const profile = $('#config-profile').value;
    $('#config-result').className = 'validation-result';
    $('#config-result').textContent = `Selected ${profile}. Choose Reset from profile to replace the editor.`;
  });
  $('#config-reset').addEventListener('click', resetConfigTemplate);
  $('#config-validate').addEventListener('click', validateConfig);
  $('#config-save').addEventListener('click', saveConfig);
  $('#config-download').addEventListener('click', downloadConfig);
  $('#config-generate').addEventListener('click', generateFromSavedConfig);
  $('#config-name').addEventListener('input', () => configEdited(false));
  $('#schema-search').addEventListener('input', (event) => renderSchemaDocs(event.target.value));
  $('#config-yaml').addEventListener('input', configEdited);
  $('#config-yaml').addEventListener('keydown', (event) => {
    if (event.key !== 'Tab') return;
    event.preventDefault();
    const field = event.target;
    const start = field.selectionStart;
    field.setRangeText('  ', start, field.selectionEnd, 'end');
    configEdited();
  });

  $('#operation-select').addEventListener('change', renderOperationForm);
  $('#operation-form').addEventListener('submit', submitOperation);
  $('#jobs-refresh').addEventListener('click', refreshJobs);
  $('#job-cancel').addEventListener('click', cancelSelectedJob);
  $('#backend-refresh').addEventListener('click', loadBackend);
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Tab' || $('#help-overlay').classList.contains('hidden')) return;
    const focusable = [...$('#help-panel').querySelectorAll('button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
      .filter((element) => !element.disabled && element.getClientRects().length > 0);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault(); first.focus();
    }
  });
}

// ---------------------------------------------------------------------------
// Interaction wiring

function setProjection(projection) {
  state.projection = projection;
  document.querySelectorAll('#projection-controls button').forEach((button) => {
    const active = button.dataset.proj === projection;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  state.morph.target = projection === 'globe' ? 0 : 1;
  if (projection === 'equirect') state.morph.proj2DTarget = 0;
  if (projection === 'mollweide') state.morph.proj2DTarget = 1;
  if (projection !== 'globe') {
    three.controls.target.set(0, 0, 0);
    three.camera.position.set(0, 0, 3.4);
  }
  state.pickDirty = true;
}

function wireMapEvents() {
  state.mapEventController?.abort();
  const controller = new AbortController();
  state.mapEventController = controller;
  const bind = (target, type, listener) => target.addEventListener(type, listener, { signal: controller.signal });
  let resizeFrame = 0;
  controller.signal.addEventListener('abort', () => cancelAnimationFrame(resizeFrame));
  bind(window, 'resize', () => {
    // Drag-resize fires a burst of events and each full resize reallocates the
    // GPU pick target, so coalesce to one resize per frame.
    if (resizeFrame) return;
    resizeFrame = requestAnimationFrame(() => {
      resizeFrame = 0;
      resizeRenderer();
    });
  });

  document.querySelectorAll('#projection-controls button').forEach((button) => {
    bind(button, 'click', () => setProjection(button.dataset.proj));
  });

  bind($('#toggle-wireframe'), 'click', () => {
    state.overlays.wireframe = !state.overlays.wireframe;
    three.wireMesh.visible = state.overlays.wireframe;
    $('#toggle-wireframe').classList.toggle('active', state.overlays.wireframe);
    $('#toggle-wireframe').setAttribute('aria-pressed', String(state.overlays.wireframe));
  });
  bind($('#toggle-plates'), 'click', async () => {
    state.overlays.plates = !state.overlays.plates;
    $('#toggle-plates').classList.toggle('active', state.overlays.plates);
    $('#toggle-plates').setAttribute('aria-pressed', String(state.overlays.plates));
    if (!state.overlays.plates) {
      cancelPlateLinesLoad();
      if (three.plateLines) three.plateLines.visible = false;
      return;
    }
    try {
      const ready = await ensurePlateLines();
      if (ready && three.plateLines) three.plateLines.visible = state.overlays.plates;
    } catch (error) {
      console.error(error);
      if (!state.overlays.plates) return;
      state.overlays.plates = false;
      $('#toggle-plates').classList.remove('active');
      $('#toggle-plates').setAttribute('aria-pressed', 'false');
      setExportMessage(`Plate overlay failed: ${error.message || String(error)}`, 6000);
    }
  });
  bind($('#toggle-graticule'), 'click', () => {
    state.overlays.graticule = !state.overlays.graticule;
    $('#toggle-graticule').classList.toggle('active', state.overlays.graticule);
    $('#toggle-graticule').setAttribute('aria-pressed', String(state.overlays.graticule));
    buildGraticule();
    three.graticuleLines.visible = state.overlays.graticule;
  });

  bind($('#export-map-image'), 'click', () => { void downloadMapImage(); });
  bind($('#export-image-prompt'), 'click', downloadImagePrompt);

  bind($('#layer-search'), 'input', (event) => filterLayerList(event.target.value));

  bind($('#legend-info'), 'click', () => setDocsVisible(!state.docsVisible));

  const slider = $('#stage-slider');
  const number = $('#stage-number');
  let stageFetchTimer = 0;
  controller.signal.addEventListener('abort', () => {
    if (stageFetchTimer) window.clearTimeout(stageFetchTimer);
  });
  bind(slider, 'input', () => {
    const config = stageBarConfig();
    if (!config) return;
    const value = Number(slider.value);
    // Scrub feedback is immediate; the expensive layer fetch is coalesced so
    // dragging across N stages issues one request instead of N.
    number.value = String(value);
    $('#stage-label').textContent = config.label(value);
    const layer = state.activeLayer;
    const selectionSeq = state.fetchSeq;
    window.clearTimeout(stageFetchTimer);
    stageFetchTimer = window.setTimeout(() => {
      stageFetchTimer = 0;
      // A newer number, arrow or layer request owns the selection, even when
      // it selects the same layer and its values have not arrived yet.
      if (state.activeLayer === layer && state.fetchSeq === selectionSeq) config.set(value);
    }, 120);
  });
  bind(number, 'change', () => {
    const config = stageBarConfig();
    if (config) config.set(Math.min(Number(number.max), Math.max(0, Number(number.value))));
  });
  bind($('#stage-back'), 'click', () => stepStage(-1));
  bind($('#stage-fwd'), 'click', () => stepStage(1));

  bind($('#inspector-close'), 'click', () => {
    $('#inspector').classList.add('hidden');
    state.inspectorRequest += 1;
    state.inspectorSparklines = [];
    state.selectedCell = -1;
    resizeRenderer();
  });

  bind($('#docs-card-toggle'), 'click', () => {
    state.docsCollapsed = !state.docsCollapsed;
    updateDocsCard(state.activeLayer);
  });

  const canvas = three.renderer.domElement;
  let lastMove = 0;
  let downAt = null;
  bind(canvas, 'pointerdown', (event) => { downAt = [event.clientX, event.clientY]; });
  bind(canvas, 'pointerup', (event) => {
    if (!downAt) return;
    const dx = event.clientX - downAt[0];
    const dy = event.clientY - downAt[1];
    downAt = null;
    if (dx * dx + dy * dy > 16) return;   // drag, not click
    const cell = pickCell(event.clientX, event.clientY);
    if (cell >= 0) openInspector(cell);
  });
  bind(canvas, 'pointermove', (event) => {
    // Touch drags rotate the globe; a hover readout nobody can see is wasted
    // pick-buffer renders.
    if (event.pointerType === 'touch') return;
    const now = performance.now();
    if (now - lastMove < 40) return;
    lastMove = now;
    state.hoverCell = pickCell(event.clientX, event.clientY);
    updateStatus();
  });
  bind(canvas, 'pointerleave', () => {
    state.hoverCell = -1;
    updateStatus();
  });
  three.controls.addEventListener('change', () => { state.pickDirty = true; });

  bind(window, 'keydown', (event) => {
    // Esc closes overlays even from within an input. The help overlay itself
    // closes through the cache-independent binding in wireWorkbenchEvents().
    if (event.key === 'Escape') {
      if (!$('#inspector').classList.contains('hidden')) { $('#inspector-close').click(); return; }
      const field = event.target.closest('input, textarea, select');
      if (field) field.blur();
      return;
    }
    if (state.activeView !== 'map') return;
    if (event.target.closest('input, textarea, select')) return;
    if (!$('#help-overlay').classList.contains('hidden')) return;   // help open: swallow shortcuts
    switch (event.key) {
      case ',': stepStage(-1); break;
      case '.': stepStage(1); break;
      case '1': setProjection('globe'); break;
      case '2': setProjection('equirect'); break;
      case '3': setProjection('mollweide'); break;
      case 'w': $('#toggle-wireframe').click(); break;
      case 'b': $('#toggle-plates').click(); break;
      case 'g': $('#toggle-graticule').click(); break;
      case 'd': setDocsVisible(!state.docsVisible); break;
      case '/': event.preventDefault(); $('#layer-search').focus(); break;
      default: break;
    }
  });
}

// ---------------------------------------------------------------------------
// Boot

async function main() {
  wireWorkbenchEvents();
  setView(window.location.hash.slice(1) || 'map', { updateHash: false });

  // Jobs and a cache created by a job can change while the page is open.
  window.setInterval(() => {
    if (document.hidden) return;
    // Nothing surfaces job state outside the Operations view, so once no job
    // is active there is nothing to poll for until the view is opened again
    // (entering it triggers refreshJobs via setView).
    if (state.activeView !== 'operations' && !state.jobs.some(jobIsActive)) return;
    refreshJobs();
  }, 2500);
  window.setInterval(() => {
    if (!document.hidden) loadServerStatus();
  }, 5000);

  await Promise.allSettled([
    loadServerStatus(),
    loadConfigWorkbench(),
    loadOperations(),
    loadBackend(),
  ]);
}

main().catch((error) => {
  const badge = $('#cache-state');
  badge.className = 'state-pill failed';
  badge.textContent = 'Startup error';
  $('#workspace-state').textContent = error.message || String(error);
  console.error(error);
});
