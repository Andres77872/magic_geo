// Categorical map colors shared by the browser renderer, the legend, the GPT
// Image color codex and magic_geo.debug_map_export (parity-tested in
// tests/test_debug_map_export_parity.py — keep both tables identical).
//
// Categories are qualitative: hue carries no order. Where a class has a
// widely recognized cartographic color it is used, so an ocean reads as water
// and a desert as dry land at a glance. Köppen–Geiger classes use the standard
// scheme of Beck et al. (2018, Scientific Data 5:180214). Everything else takes
// the next unused color of a Tableau-10–derived qualitative set, which stays
// distinguishable for the common color-vision deficiencies. Within one layer no
// two classes share a color.

export const CATEGORY_COLORS = {
  // Water and coasts
  'ocean': '#2c5d8f',
  'open_ocean': '#2c5d8f',
  'marine': '#2c5d8f',
  'water': '#2c5d8f',
  'continental_shelf': '#5b9bd0',
  'trench': '#1a3558',
  'lake': '#7cc4e8',
  'fresh_lake': '#7cc4e8',
  'lacustrine_basin': '#8fcbe0',
  'saline_basin': '#c9c19a',
  'salt_flat': '#e6dcc0',
  // Cold and ice
  'alpine': '#d9dfe7',
  'tundra': '#a7b8a0',
  // Dry lands and grasslands
  'hot_desert': '#e3c58f',
  'desert': '#e3c58f',
  'arid': '#e3c58f',
  'savanna': '#cfc36a',
  'temperate_grassland': '#b8cf7e',
  // Forests and wetlands
  'tropical_rainforest': '#1e7b3c',
  'tropical_seasonal_forest': '#5a9e3e',
  'temperate_forest': '#3f915e',
  'boreal_forest': '#2c6a5c',
  'taiga': '#2c6a5c',
  'wetland': '#3fa59b',
  'mangrove': '#2e8b6e',
  'swamp': '#3b8f7a',
  // Landforms and crust
  'land': '#b09a6e',
  'continental': '#b09a6e',
  'oceanic': '#2c5d8f',
  'mountain_belt': '#8c6d58',
  'volcanic_arc': '#b24a3c',
  'rift_valley': '#b87952',
  'river_valley': '#78b56e',
  'floodplain': '#93c47d',
  'delta': '#a8d08d',
  'coastal_plain': '#d4c68c',
  'stable_lowland': '#a3bf7e',
  // Neutral and boolean
  'none': '#7b8494',
  'False': '#7b8494',
  'True': '#f5b454',
  // Köppen–Geiger (Beck et al. 2018)
  'Af': '#0000ff',
  'Am': '#0078ff',
  'Aw': '#46aafa',
  'BWh': '#ff0000',
  'BWk': '#ff9696',
  'BSh': '#f5a500',
  'BSk': '#ffdc64',
  'Csa': '#ffff00',
  'Csb': '#c8c800',
  'Csc': '#969600',
  'Cwa': '#96ff96',
  'Cwb': '#64c864',
  'Cwc': '#329632',
  'Cfa': '#c8ff50',
  'Cfb': '#64ff50',
  'Cfc': '#32c800',
  'Dsa': '#ff00ff',
  'Dsb': '#c800c8',
  'Dsc': '#963296',
  'Dsd': '#966496',
  'Dwa': '#aaafff',
  'Dwb': '#5a78dc',
  'Dwc': '#4b50b4',
  'Dwd': '#320087',
  'Dfa': '#00ffff',
  'Dfb': '#37c8ff',
  'Dfc': '#007d7d',
  'Dfd': '#00465f',
  'ET': '#b2b2b2',
  'EF': '#666666',
};

export const QUALITATIVE_PALETTE = [
  '#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948',
  '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac', '#86bcb6', '#d37295',
  '#a0cbe8', '#ffbe7d', '#8cd17d', '#f1ce63', '#d4a6c8', '#fabfd2',
];

// Colors for the declared categories of one layer, in code order.
export function categoryPalette(categories = []) {
  const used = new Set();
  let next = 0;
  const nextQualitative = () => {
    for (let step = 0; step < QUALITATIVE_PALETTE.length; step += 1) {
      const color = QUALITATIVE_PALETTE[(next + step) % QUALITATIVE_PALETTE.length];
      if (!used.has(color)) {
        next = (next + step + 1) % QUALITATIVE_PALETTE.length;
        return color;
      }
    }
    const color = QUALITATIVE_PALETTE[next];
    next = (next + 1) % QUALITATIVE_PALETTE.length;
    return color;
  };
  return (Array.isArray(categories) ? categories : []).map((category) => {
    const semantic = Object.hasOwn(CATEGORY_COLORS, String(category)) ? CATEGORY_COLORS[String(category)] : null;
    const color = semantic && !used.has(semantic) ? semantic : nextQualitative();
    used.add(color);
    return color;
  });
}

// Guide color for one category code. Codes outside the declared list (never
// produced by a valid cache) fall back to the qualitative cycle by code.
export function categoryHex(code, categories = []) {
  const palette = categoryPalette(categories);
  if (Number.isInteger(code) && code >= 0 && code < palette.length) return palette[code];
  const index = Number.isInteger(code) && code >= 0 ? code : 0;
  return QUALITATIVE_PALETTE[index % QUALITATIVE_PALETTE.length];
}

export function hexBytes(hex) {
  const value = String(hex).replace('#', '');
  return [0, 2, 4].map((offset) => Number.parseInt(value.slice(offset, offset + 2), 16));
}
