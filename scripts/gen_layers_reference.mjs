#!/usr/bin/env node
// Regenerate docs/layers_reference.md from a debug-cache manifest, using the same
// debug_ui/layer_docs.js catalog that powers the in-app docs helper — so the
// reference can never drift from what the UI shows.
//
// Usage:
//   node scripts/gen_layers_reference.mjs [manifest.json] [out.md]
// Defaults:
//   manifest = runs/debug/manifest.json
//   out      = docs/layers_reference.md
//
// Re-run after `magic-geo export-debug` produces a new cache, or after editing
// CURATED / rules in src/magic_geo/debug_ui/layer_docs.js.

import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..');
const manifestPath = resolve(process.argv[2] || resolve(REPO, 'runs/debug/manifest.json'));
const outPath = resolve(process.argv[3] || resolve(REPO, 'docs/layers_reference.md'));

const { describeLayer, docStatus, docsCoverage } =
  await import(resolve(REPO, 'src/magic_geo/debug_ui/layer_docs.js'));

const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
const RETIRED_CELL_LAYERS = new Set([
  'crust_source_remap_event_count',
  'cumulative_numeric_depression_fill_m',
  'initial_crust_age_ma',
  'initial_crust_density',
  'initial_crust_thickness_km',
  'initial_thermal_subsidence_m',
  'last_crust_source_cell_id',
  'numeric_depression_fill_event_count',
  'sediment_production_m',
]);
const layers = manifest.layers.filter((layer) => !RETIRED_CELL_LAYERS.has(layer.name));

// Thematic domains: ordered rules, first match wins; each carries the "how it
// works" narrative (subsystem, producing modules, pipeline stage).
const DOMAINS = [
  ['geometry', 'Mesh & geometry', {
    what: 'Static per-cell geometry of the spherical mesh — cell centres, areas, surface normals, neighbour metrics, and multi-resolution spatial indices (HEALPix-like, S2-like, mesh-LOD tiles). These do not evolve during the simulation; they define the coordinate system every other layer is sampled on.',
    modules: ['`cpp/src/engine/mesh.cpp` (Fibonacci-sphere / geodesic mesh)', '`cell_geometry.py`', '`mesh_lod.py`', '`spherical_index.py`'],
    stage: 'Built once at mesh construction, before any physics.',
    test: (n) => ['id','lat_deg','lon_deg','area_km2'].includes(n) || n.startsWith('position_3d_') || n.startsWith('normal_3d_')
      || n.startsWith('cell_') || n.startsWith('mesh_lod') || n.startsWith('healpix_like') || n.startsWith('s2_like')
      || n.includes('neighbor_edge') || n.includes('neighbor_boundary') || n === 'boundary_vertex_count' }],
  ['tectonics', 'Tectonics & solid earth', {
    what: 'Plate assignment and kinematics, crust type/age/thickness/density, boundary classification (convergent/divergent/transform), fault systems, seismic hazard, and the initial tectonic elevation contributions (ridge, rift, trench, orogenic, volcanic, thermal, isostatic). This is the deepest layer of the model — the feedback loop re-derives elevation from these each stage.',
    modules: ['`cpp/src/engine/tectonics.cpp`', '`fault_systems.py`', '`tectonic_zones.py`', '`geology_realism.py`'],
    stage: 'Initialised at setup (the `initial_*` fields), then updated by the geodynamic feedback loop.',
    test: (n) => n.startsWith('initial_rift') || n.startsWith('initial_volcanic') || n.startsWith('initial_ridge')
      || n.startsWith('initial_trench') || n.startsWith('initial_thermal') || n.startsWith('initial_orogenic')
      || n.startsWith('initial_transform') || n.startsWith('initial_secondary') || n.startsWith('initial_isostatic')
      || n.startsWith('plate_') || n.startsWith('initial_plate') || n.startsWith('crust') || n.startsWith('initial_crust')
      || n.startsWith('boundary_') || n === 'boundary_type' || n.startsWith('tectonic_') || n.startsWith('fault_')
      || n === 'lithology' || n.startsWith('rift') || n.includes('subduction') || n.includes('collision')
      || n.includes('orogen') || n.startsWith('seismic') || n.startsWith('earthquake') || n.includes('transform_fault')
      || n === 'continental_shelf_id' || n.startsWith('dominant_tectonic') || n.includes('ridge_uplift')
      || n.includes('trench') || n.includes('thermal_subsidence') || n.includes('isostatic') || n === 'volcanic_potential_index'
      || n.startsWith('last_crust') || n.startsWith('last_plate') || n.includes('crust_transport') || n.includes('secondary_roughness') }],
  ['geomorphology', 'Elevation & landforms', {
    what: 'The land/sea surface itself — final and initial elevation, depression-filled surface, landform class, landmass and island classification, and local relief. Elevation is the single most-used layer and the default on load.',
    modules: ['`cpp/src/engine/core.cpp` / `environment.cpp`', '`glacial_landforms.py`', '`planet_realism.py`', '`sea_level_diagnostics.py`'],
    stage: 'Elevation co-evolves in the feedback loop; landform/landmass classification is a post-pass enricher.',
    test: (n) => n === 'elevation_m' || n === 'initial_elevation_m' || n === 'filled_elevation_m' || n === 'landform'
      || n === 'island_class' || n === 'landmass_id' || n.startsWith('tectonic_uplift') || n.includes('elevation_change')
      || n === 'erosion_rate' || n.startsWith('glacial_landform') || n === 'local_relief_m' }],
  ['sediment', 'Sediment & stratigraphy', {
    what: 'Erosion, transport, and deposition budgets — hillslope diffusion, fluvial routing (production, deposition, terminal export/capture), sediment thickness, and sequence-stratigraphy inventory. These close the mass balance between the eroding uplands and the depositional basins.',
    modules: ['`sediment_dynamics.py`', '`sediment_routing.py`', '`sedimentary_resource_systems.py`', '`sequence_stratigraphy.py`'],
    stage: 'Runs inside the erosion iterations of the feedback loop.',
    test: (n) => n.startsWith('sediment_') || (n.includes('sediment') && !n.startsWith('glacial')) || n.startsWith('hillslope_sediment')
      || n.startsWith('fluvial_sediment') || n.includes('alluvium') || n.includes('bedrock_erosion')
      || (n.includes('deposition') && !n.startsWith('glacial')) || n === 'sediment_thickness_m' }],
  ['hydrology', 'Surface hydrology & rivers', {
    what: 'Flow routing over the conditioned surface — flow direction and accumulation, drainage basins, depression fill/breach handling, lakes and closed basins, river channels (width/depth/hydraulics), floodplains, and river-network evolution (avulsion, capture). The depression-fill history logs every basin correction as a separate stage.',
    modules: ['`cpp/src/engine/hydrology.cpp`', '`hydrology_dynamics.py`', '`hydrology_realism.py`', '`river_hydraulics.py`', '`river_channel_morphology.py`', '`river_network_evolution.py`', '`watershed_diagnostics.py`'],
    stage: 'Flow routing runs every feedback stage after the surface is conditioned; channel morphology is an enricher on the final network.',
    test: (n) => n.startsWith('flow_') || n === 'flow_to' || n === 'flow_accumulation' || n.startsWith('is_river') || n === 'is_lake'
      || n === 'is_water' || n === 'is_closed_basin' || n === 'basin_id' || n.startsWith('depression_') || n.startsWith('spill')
      || n.startsWith('lake_') || n.startsWith('runoff') || n.startsWith('hydrologic_') || n.startsWith('hydraulic_')
      || n.startsWith('river_') || n.startsWith('channel_') || n.includes('floodplain') || n.startsWith('overflow_channel')
      || n.startsWith('stream_power') || n.startsWith('bankfull') || n === 'froude_number' || n.startsWith('manning')
      || n.startsWith('numeric_depression') || n.includes('watershed') || n.startsWith('baseflow') || n === 'water_body_type'
      || n === 'water_depth_m' || n.startsWith('bed_shear') || n.includes('drainage') || n.startsWith('glacier_flow')
      || n.startsWith('cumulative_numeric_depression') || n.startsWith('breach_') || n.startsWith('fill_depth')
      || n.startsWith('elevation_after_fill') || n.startsWith('elevation_before_fill') || n === 'equal_filled_raw_downhill_rerouted'
      || n === 'navigable_waterway_id' || n === 'is_marine' }],
  ['water_budget', 'Water budget & atmospheric moisture', {
    what: 'The coupled precipitation → evapotranspiration → infiltration → runoff balance and the atmospheric-moisture transport that feeds it (orographic rainout, moisture recycling, vapor budget, water surplus/deficit). The `hydrologic_water_budget_history` (16 stages) is the per-stage snapshot of this solve.',
    modules: ['`cpp/src/engine/climate.cpp`', '`climate_dynamics.py`', '`hydrology_budget.py`'],
    stage: 'Recomputed each feedback stage (16 recomputes over 8 clock stages).',
    test: (n) => n.startsWith('precipitation') || n.includes('evapotranspiration') || n.startsWith('infiltration')
      || n.includes('water_balance') || n.includes('water_deficit') || n.includes('water_surplus') || n.startsWith('moisture')
      || n.startsWith('vapor_') || n.startsWith('humidity') || n.includes('recycling') || n.startsWith('advected_moisture')
      || n.startsWith('orographic') || n.startsWith('rain_shadow') || n === 'water_budget_runoff_mm_y'
      || n.startsWith('precipitation_recycling') || n.includes('rainout') || n === 'residual_mm_y' || n === 'mean_seasonal_wind_speed' }],
  ['groundwater', 'Groundwater, aquifers & karst', {
    what: 'Subsurface water — recharge, hydraulic head, lateral flow between cells, aquifer classification and productivity/quality/storage indices, vadose-zone retention, spring discharge, and karst/cave development potential. Includes mass-balance residual diagnostics for the groundwater solve.',
    modules: ['`groundwater_flow.py`', '`aquifer_resources.py`', '`karst_diagnostics.py`'],
    stage: 'Enricher pass over the final surface-hydrology and climate state.',
    test: (n) => n.startsWith('groundwater') || n.startsWith('aquifer') || n.startsWith('vadose') || n.startsWith('spring')
      || n.startsWith('karst') || n.includes('subterranean') || n.startsWith('cave') || n.includes('infiltration_capacity')
      || n.includes('recharge') }],
  ['climate', 'Climate & atmosphere', {
    what: 'Temperature, Köppen climate class, the atmospheric-circulation cell each cell sits in, winds, the full surface-energy balance (insolation, shortwave/longwave, greenhouse trapping, albedo, radiative-equilibrium temperatures), seasonality (dry/wet/growing/frost month counts, seasonal ranges), continentality, and monsoon indices.',
    modules: ['`cpp/src/engine/climate.cpp`', '`climate_dynamics.py`', '`climate_energy.py`', '`climate_continentality.py`', '`climate_realism.py`'],
    stage: 'Recomputed each feedback stage; energy-balance and seasonality indices are enrichers on the converged climate.',
    test: (n) => n === 'temperature_c' || n === 'climate_class' || n === 'atmospheric_cell' || n.startsWith('wind_')
      || n.includes('insolation') || n.includes('radiative') || n.includes('albedo') || n.includes('greenhouse')
      || n.startsWith('energy_balance') || n.includes('monsoon') || n.startsWith('seasonal_') || n.startsWith('continentality')
      || n === 'continentality_index' || n.startsWith('surface_pressure') || n.startsWith('net_radiative')
      || n.startsWith('absorbed_shortwave') || n.startsWith('outgoing_longwave') || n.startsWith('top_of_atmosphere')
      || n.startsWith('no_greenhouse') || n.startsWith('low_seasonal') || n.startsWith('peak_seasonal')
      || (n.includes('temperature') && !n.includes('ocean_current')) || n.startsWith('vertical_velocity')
      || n.startsWith('wind_divergence') || n.startsWith('climate_energy') || n.startsWith('climate_continentality')
      || n.includes('frost_months') || n.startsWith('dry_season') || n.startsWith('wet_season') || n.startsWith('growing_season')
      || n.startsWith('orbital_insolation') || n.startsWith('upwind_ocean') || n.startsWith('climatic_water') || n === 'cell_monsoon_index' }],
  ['ocean', 'Oceans & coasts', {
    what: 'Ocean surface currents (direction/speed/temperature/regime and transport), heat transport, upwelling, marine influence and regions, continental shelves, coral reefs (growth, bleaching risk, wave exposure, island support), coastal navigability, protected bays, and fisheries.',
    modules: ['`ocean_circulation.py`', '`cpp/src/engine/ocean.cpp`', '`reef_diagnostics.py`', '`sea_level_diagnostics.py`'],
    stage: 'Ocean circulation runs with the climate solve; reef/coast enrichers run on the final state.',
    test: (n) => n.startsWith('ocean_') || n.startsWith('marine_') || n.includes('upwelling') || n.includes('sea_level')
      || n.startsWith('coastal_') || n.startsWith('reef_') || n.includes('fishery') || n.includes('tidal')
      || n === 'continental_shelf_id' || n.startsWith('oceanic_') || n.includes('marine_water') || n.startsWith('protected_bay')
      || (n.includes('chokepoint') && n.startsWith('marine')) }],
  ['cryosphere', 'Cryosphere (ice, glaciers, permafrost)', {
    what: 'Ice sheets and glaciers (thickness, velocity, surface mass balance, flowlines, driving stress, basal sliding), glacial erosion/deposition and sediment transport, moraines, permafrost classes and extent, active-layer depth, and ground-ice content.',
    modules: ['`cryosphere_dynamics.py`', '`cryosphere_flow.py`', '`cryosphere_stability.py`', '`glacial_landforms.py`', '`permafrost_diagnostics.py`'],
    stage: 'Cryosphere dynamics couple into the feedback loop; landform/permafrost classification is a post-pass.',
    test: (n) => n.startsWith('ice_') || n.startsWith('glacial_') || n.startsWith('glacier_') || n.startsWith('permafrost_')
      || n.startsWith('cryosphere') || n.includes('deglaciation') || n.startsWith('moraine') || n.startsWith('active_layer')
      || n.startsWith('ground_ice') || n.startsWith('basal_sliding') || n.startsWith('surface_mass_balance') }],
  ['soil', 'Soils', {
    what: 'Soil profile development — type and texture class, depth, horizon count, pH, organic-matter fraction, drainage, erodibility, salinity, moisture, and derived agronomic fertility / agricultural potential.',
    modules: ['`soil_dynamics.py`', '`land_use_zones.py` (agricultural zoning)'],
    stage: 'Enricher pass over the final climate, hydrology, and lithology.',
    test: (n) => n.startsWith('soil_') || n === 'fertility' || n === 'agricultural_potential_index' || n === 'agricultural_zone_id' }],
  ['ecology', 'Ecology, biomes & disturbance', {
    what: 'Biome classification and ecotones, vegetation succession and biomass, net primary productivity, species richness/endemism/guilds and range fragmentation, wetlands (extent, hydrology, connectivity, type), and disturbance regimes (wildfire ignition/spread/fuel, ecosystem disturbance pressure).',
    modules: ['`biome_dynamics.py`', '`biome_ecotones.py`', '`biome_realism.py`', '`ecosystem_dynamics.py`', '`species_ranges.py`', '`wildfire_disturbance.py`', '`wetland_diagnostics.py`'],
    stage: 'Enricher passes over the final climate/soil/hydrology state.',
    test: (n) => n.startsWith('biome') || n.startsWith('species_') || n.startsWith('vegetation_') || n.startsWith('ecosystem_')
      || n.startsWith('primary_productivity') || n.startsWith('forest_growth') || n.startsWith('wildfire_')
      || n.startsWith('fire_') || n.startsWith('ecotone') || n.startsWith('wetland_') || n === 'dominant_species_guild' }],
  ['resources', 'Resources & economic geology', {
    what: 'Primary resource association per cell plus the systems that generate them — ore genesis (metallogenic fertility, structural control, hydrothermal alteration, placers), petroleum systems (source rock, maturation, migration, traps), mining/land-use zoning, and reserve-potential indices.',
    modules: ['`ore_genesis.py`', '`petroleum_migration.py`', '`commodity_resources.py`', '`resource_dynamics.py`', '`land_use_zones.py`'],
    stage: 'Enricher passes over the final geology, tectonics, and sediment state.',
    test: (n) => n === 'resource' || n.startsWith('ore_') || n.startsWith('petroleum_') || n.startsWith('mining_')
      || n.startsWith('metallogenic') || n.startsWith('placer') || n.startsWith('hydrothermal') || n.startsWith('commodity')
      || n.startsWith('land_use') || n.includes('reserve') || n.startsWith('sedimentary_fuel') }],
  ['human', 'Human & political geography', {
    what: 'The human layer — settlement scoring, ports and harbours, transport routes and corridors, navigability classes, natural frontiers, and cultural / linguistic / political / territorial regions. Region ids partition the map into named entities.',
    modules: ['`settlement_routes.py`', '`port_sites.py`', '`route_corridors.py`', '`navigability_diagnostics.py`', '`cultural_geography.py`', '`political_geography.py`', '`territorial_geography.py`', '`natural_frontiers.py`', '`civilization_geography.py`'],
    stage: 'Final enricher passes; the history/economy models (in `sections.json`, not per-cell layers) build on top.',
    test: (n) => n.startsWith('settlement') || n.startsWith('port_') || n.startsWith('route_') || n.startsWith('navigability')
      || n.startsWith('culture_') || n.startsWith('language_') || n.startsWith('political_') || n.startsWith('territorial')
      || n.startsWith('natural_frontier') || n.startsWith('dynasty') || n.startsWith('demographic') || n.startsWith('mountain_pass')
      || n.startsWith('oasis') || n.startsWith('strait') || n.startsWith('transport_chokepoint') || n.startsWith('harbor')
      || n.startsWith('river_mouth_port') || n.startsWith('coastal_route') || n.startsWith('river_valley_route') }],
];

function domainFor(name) {
  for (const [key, , meta] of DOMAINS) {
    try { if (meta.test(name)) return key; } catch { /* rule threw */ }
  }
  return 'other';
}

const STATUS_LABEL = { curated: 'curated', pattern: 'convention', unit: 'unit', generated: 'generated' };
const esc = (s) => String(s).replace(/\|/g, '\\|').replace(/\n/g, ' ');

const rows = layers.map((layer) => {
  const doc = describeLayer(layer);
  return {
    name: layer.name, kind: layer.kind, unit: doc.unit || '', role: doc.role,
    status: docStatus(layer),
    range: layer.stats ? `${doc.stats.min} … ${doc.stats.max}` : (layer.kind === 'categorical' ? `${layer.categories.length} classes` : '—'),
    categories: layer.kind === 'categorical' ? layer.categories : null,
    stageCount: layer.stage_count || null, monthCount: layer.month_count || null,
    description: doc.description, domain: domainFor(layer.name),
  };
});

function layerRow(r) {
  const kind = r.kind === 'numeric_stage' ? `stage×${r.stageCount}` : r.kind === 'numeric_monthly' ? `month×${r.monthCount}` : r.kind;
  const unit = r.unit ? `\`${r.unit}\`` : '—';
  let desc = r.description;
  if (r.kind === 'categorical') desc += ` **Classes:** ${r.categories.join(', ')}.`;
  return `| \`${esc(r.name)}\` | ${esc(kind)} | ${unit} | ${esc(r.range)} | ${esc(r.role)} | ${STATUS_LABEL[r.status]} | ${esc(desc)} |`;
}

const cov = docsCoverage(layers);
const byRole = cov.byRole;
const byDomain = {};
for (const r of rows) {
  (byDomain[r.domain] ||= { total: 0, curated: 0, pattern: 0, unit: 0, generated: 0, rows: [] });
  byDomain[r.domain].total += 1; byDomain[r.domain][r.status] += 1; byDomain[r.domain].rows.push(r);
}

const out = [];
const P = (...l) => out.push(...l);
P('# Layers Reference — every debugger layer, deep', '');
P('> **Auto-generated** by `scripts/gen_layers_reference.mjs` from the same');
P('> [`debug_ui/layer_docs.js`](../src/magic_geo/debug_ui/layer_docs.js) that powers the in-app docs');
P('> helper, run over a real `export-debug` manifest — so it cannot drift from what the UI shows.');
P('> Regenerate after re-exporting a cache or editing `CURATED`:');
P('> `node scripts/gen_layers_reference.mjs [manifest.json] [out.md]`.');
P('> Companion to [debugger.md](debugger.md), the review in [layers_review.md](layers_review.md),');
P('> and the [configuration reference](configuration_reference.md).', '');
P('## What a "layer" is', '');
P('A **layer** is one scalar value per cell that the debugger can colour the globe by. The exporter');
P('discovers layers generically from the world-payload shape ([debug_export.py](../src/magic_geo/debug_export.py)):', '');
P('- **`numeric`** — an int/float cell field. Coloured with viridis normalised to the p2–p98 range.');
P('- **`categorical`** — a string/bool cell field with ≤ 64 distinct values. One colour per class.');
P('- **`numeric_monthly`** — a 12-element numeric cell field. Scrub the month control (1–12).');
P('- **`numeric_stage`** — a per-cell field inside a record family shaped as `cell_ids` + `*_by_cell`');
P('  parallel arrays. Scrub the stage control; the colour scale is fixed across all stages.', '');
P('Every layer carries **props** used throughout this doc: its `id` (`source/name`), `kind`, inferred');
P('`unit`, `role` (below), value `range` (min…max), and for stage/monthly layers the stage/month count.');
P('Categorical layers carry the full class list instead of a numeric range.', '');
P('### Role (how to read the values)', '');
P('| Role | Meaning |', '| --- | --- |');
P('| `measurement` | A physical quantity in the named unit. |');
P('| `index` | Derived, normally normalised 0–1; higher = more of the property. Good for ranking, not absolute. |');
P('| `ratio` | Dimensionless fraction (0–1) or multiplier (around 1). |');
P('| `classification` | Discrete categorical class; colours carry no ordering. |');
P('| `identifier` | An integer label (region/system/graph reference). The gradient is meaningless — same colour ≈ same group. |');
P('| `provenance` | An `initial_*` snapshot captured before the feedback loop; diff against the evolved field. |');
P('| `accumulator` | A `cumulative_*` running total across all stages. |');
P('| `diagnostic` | A conservation residual / mass-balance / count. Residuals should be ~0 — a debug signal, not terrain. |');
P('| `seasonal` | Derived from the monthly climate series (month counts, seasonal ranges). |', '');
P('### Doc status (the gap tracker)', '');
P('The **Doc** column records how each description is sourced, most to least specific:', '');
P('- **curated** — hand-written prose in `layer_docs.js` `CURATED`.');
P('- **convention** — a field-naming rule (`*_id`, `*_index`, `initial_*`, …) or being categorical.');
P('- **unit** — only a unit could be inferred from the suffix; the rest is a template.');
P('- **generated** — pure fallback ("inspect a cell for context"). **These are the documentation gaps.**', '');
P('## Inventory & coverage', '');
P(`World: **${esc(manifest.world.name)}** · ${manifest.world.cell_count.toLocaleString()} cells · mesh \`${esc(manifest.world.mesh_backend)}\` · scope \`${esc(manifest.world.generation_scope)}\`.`, '');
P(`**${cov.counts.total} layers** total — ${byRole.numeric || 0} numeric, ${byRole.categorical || 0} categorical, ${byRole.numeric_stage || 0} per-stage, ${byRole.numeric_monthly || 0} monthly.`, '');
P('Documentation coverage:', '', '| Tier | Count | Share |', '| --- | --: | --: |');
for (const k of ['curated', 'pattern', 'unit', 'generated']) P(`| ${STATUS_LABEL[k]} | ${cov.counts[k]} | ${(100 * cov.counts[k] / cov.counts.total).toFixed(1)}% |`);
P('', 'Layers by domain (documentation gaps = generated tier):', '', '| Domain | Layers | Curated | Generated (gaps) |', '| --- | --: | --: | --: |');
for (const [key, title] of DOMAINS) { const d = byDomain[key]; if (d) P(`| [${esc(title)}](#${key.replace(/_/g, '-')}) | ${d.total} | ${d.curated} | ${d.generated} |`); }
P('', '---', '');

for (const [key, title, meta] of DOMAINS) {
  const d = byDomain[key];
  if (!d) continue;
  P(`## ${title}`, '', `<a id="${key.replace(/_/g, '-')}"></a>`, '');
  P(`**${d.total} layers** · doc coverage: ${d.curated} curated · ${d.pattern} convention · ${d.unit} unit · **${d.generated} generated (gaps)**.`, '');
  P('**How it works.** ' + meta.what, '');
  P('**Produced by:** ' + meta.modules.join(', ') + '.', '');
  P('**Pipeline stage:** ' + meta.stage, '');
  const sorted = d.rows.slice().sort((a, b) => {
    const sa = a.status === 'curated' ? 0 : 1, sb = b.status === 'curated' ? 0 : 1;
    return sa !== sb ? sa - sb : a.name.localeCompare(b.name);
  });
  P('| Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is |', '| --- | --- | --- | --- | --- | --- | --- |');
  for (const r of sorted) P(layerRow(r));
  P('');
  if (d.generated > 0) {
    P(`> **Gaps in this domain (${d.generated}):** ${sorted.filter((r) => r.status === 'generated').map((r) => `\`${r.name}\``).join(', ')} — resolved by kind + template only. Add prose to \`CURATED\` in \`layer_docs.js\` to close these.`, '');
  }
  P('---', '');
}

P('## Status & gaps summary', '');
P(`**Documentation gaps.** ${cov.counts.generated} of ${cov.counts.total} layers (${(100 * cov.counts.generated / cov.counts.total).toFixed(1)}%) fall to the generated tier — coordinate components, a few dimensionless physics quantities, and stage-ledger coordinates. Listed per domain above; each is a one-line addition to \`CURATED\`.`, '');
P('**Data-model gaps** (from the pipeline review — see [layers_review.md](layers_review.md) for detail):', '');
P('- **Silent drops:** high-cardinality string fields (`healpix_like_pixel_code`, `s2_like_token`) become no layer *and* no skip record; reachable only via the cell inspector. *(review F2)*');
P('- **Code/name mismatch:** per-stage `lithology` ships as numeric codes 0–6 while `cells/lithology` uses alphabetical names; no code→name table is emitted. *(review F3)*');
P('- **Identifiers as gradients:** ~30 `*_id` / `*_to` layers render as continuous ramps; flagged with the `identifier` role here and in the UI. *(review F8)*');
P('- **Heavy-tailed scales:** layers like `flow_accumulation` (max ≫ p98) saturate under the p2–p98 ramp; the legend now shows `≥`/`≤` clip markers. *(review F6, fixed)*');
P('- **Degenerate ranges:** 62 layers have p2 == p98 (mass-zero fields); the colour scale silently falls back to min/max. *(review F6)*', '');
P('**How to close a gap.** Add the field to `CURATED` in [`layer_docs.js`](../src/magic_geo/debug_ui/layer_docs.js) (one line). The docs card, help-overlay coverage box, and this reference all read from that one map, so a new entry propagates everywhere on regeneration.', '');

writeFileSync(outPath, out.join('\n'));
const otherCount = (byDomain.other?.total) || 0;
console.log(`wrote ${outPath} — ${cov.counts.total} layers, ${Object.keys(byDomain).length} domains, ${otherCount} unclassified`);
if (otherCount) console.log('  unclassified:', byDomain.other.rows.map((r) => r.name).join(', '));
