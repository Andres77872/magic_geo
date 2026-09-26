// Numeric colour scales for the map, the legend and both export paths.
//
// The 256-entry lookup tables below are written by scripts/generate_colormaps.py
// and read verbatim by magic_geo.debug_map_export, so a value is drawn in the
// same colour on screen, in a downloaded PNG and in the CLI reference image.
//
// numericScale() picks a scale the way scientific-visualisation guidance
// recommends (Crameri et al. 2020; Moreland 2009): sequential for magnitudes,
// diverging about zero for signed quantities, a sea-level split for
// elevations, and categorical colours for identifiers, which name things
// rather than measure them. The same rules live in debug_map_export.py.

import { QUALITATIVE_PALETTE } from './palettes.js';

export const COLORMAPS = {
  viridis: { label: 'Viridis', kind: 'sequential', description: 'Sequential and perceptually uniform: lighter means more.' },
  coolwarm: { label: 'Cool–warm', kind: 'diverging', description: 'Diverging about zero: blue below, red above, grey at 0.' },
  terrain: { label: 'Terrain', kind: 'terrain', description: 'Blue below sea level (0 m), green to white above it.' },
};
export const COLORMAP_CHOICES = ['auto', 'viridis', 'coolwarm', 'terrain'];
export const NO_DATA_HEX = '#292e36';   // MISSING_COLOR_HEX in app.js and the CLI export
export const RANGE_CHOICES = ['robust', 'full'];

// BEGIN GENERATED LUTS (scripts/generate_colormaps.py)
export const COLORMAP_LUTS = {
  viridis: '46015546025647045747055947075a47085c47095d470b5e470c60470e61470f6247106447126547136647146747166947176a47196b471a6c471b6e471d6f471e70471f71472172472273472374472575472676472777472978472a79472b7a462d7b462e7c462f7c46307d46327e46337f453480453580453781453882443982443a83443b83443d84433e85433f854340864241864242874244874145884146884147884048894049893f4a893f4b8a3f4d8a3e4e8a3e4f8b3d508b3d518b3c528b3c538c3b548c3b558c3a568c3a578c39588c39598d385a8d385b8d375c8d375d8d365e8d355f8d35608d34618d34628d33638d33648e32658e31668e31678e30688e30698e2f6a8e2f6b8e2e6c8e2d6d8e2d6e8e2c6f8e2c708e2b718e2b728d2a738d29748d29758d28768d28778d27788d27798d267a8d267b8d257c8d257d8d247d8d247e8d247f8d23808d23818d22828c22838c22848c21858c21868c21878c20888c20898c208a8c208b8b1f8c8b1f8d8b1f8d8b1f8e8b1f8f8b1f908b1e918a1e928a1e938a1e948a1e958a1e96891e97891f98891f99891f9a881f9b881f9b881f9c88209d87209e87209f8721a08621a18621a28622a38522a48523a58423a68424a78425a78325a88326a98227aa8228ab8128ac8129ad802aae7f2baf7f2cb07e2db07d2eb17d2fb27c30b37b31b47b32b57a34b67935b77836b77738b87639b9763aba753cbb743dbc733fbc7241bd7142be7044bf6f46c06e47c16c49c16b4bc26a4dc3694fc46851c46653c56555c66457c76359c7615bc8605dc95e5fca5d61ca5c64cb5a66cc5968cc576bcd566dce5470cf5372cf5174d05077d04e7ad14c7cd24b7fd24981d34884d44687d44489d5438cd5418fd63f92d63e94d73c97d73a9ad8399dd9379fd936a2da34a5da32a8db31abdb2faedb2eb0dc2cb3dc2bb6dd2ab9dd28bcde27bfde26c1df24c4df23c7df22cae021cde020cfe01fd2e11ed5e11dd7e21ddae21cdce21cdfe31be2e31be4e31be6e41be9e41bebe41bede41befe51bf2e51cf4e51df6e61df8e61ef9e620fbe721',
  coolwarm: '3b4cc03c4ec23d50c33e51c54053c64155c84256c94358cb445acc455cce475dcf485fd14961d24a63d34b64d54d66d64e68d74f69d9506bda526ddb536edd5470de5572df5773e05875e15977e25a78e45c7ae55d7ce65e7de75f7fe86180e96282ea6384eb6585ec6687ed6788ee698aef6a8bef6b8df06d8ef16e90f26f91f37193f37294f47396f57597f67699f6779af7799cf87a9df87b9ff97da0f97ea1fa80a3fa81a4fb82a6fb84a7fc85a8fc87aafc88abfd89acfd8badfd8caffe8db0fe8fb1fe90b2fe92b4fe93b5ff94b6ff96b7ff97b8ff98b9ff9abbff9bbcff9dbdff9ebeff9fbfffa1c0ffa2c1ffa3c2fea5c3fea6c4fea8c5fea9c6feaac7fdacc8fdadc9fdaec9fcb0cafcb1cbfcb2ccfbb3cdfbb5cefab6cefab7cff9b9d0f9bad1f8bbd1f8bcd2f7bed3f6bfd3f6c0d4f5c1d4f4c3d5f4c4d6f3c5d6f2c6d7f1c8d7f1c9d8f0cad8efcbd8eeccd9edcdd9eccedaebd0daead1dae9d2dbe8d3dbe7d4dbe6d5dbe5d6dce4d7dce3d8dce2d9dce1dadce0dbdddedcdddddddcdcdedcdbdfdcd9e1dbd8e2dad6e3dad5e4d9d3e5d9d2e5d8d1e6d8cfe7d7cee8d6cce9d6cbead5c9ebd4c8ebd3c6ecd3c5edd2c3eed1c2eed0c0efcfbfefcebdf0cebcf1cdbaf1ccb8f2cbb7f2cab5f3c9b4f3c8b2f4c7b1f4c6aff4c5aef5c4acf5c3aaf5c1a9f6c0a7f6bfa6f6bea4f6bda2f7bca1f7ba9ff7b99ef7b89cf7b79bf7b599f7b497f7b396f7b294f7b093f7af91f7ad90f7ac8ef7ab8cf7a98bf7a889f7a688f6a586f6a385f6a283f6a081f59f80f59d7ef59c7df49a7bf4997af49778f39577f39475f29274f29072f18f71f18d6ff08b6ef08a6cef886bef8669ee8568ed8366ed8165ec7f63eb7d62ea7c60ea7a5fe9785de8765ce7745ae67259e57058e56f56e46d55e36b53e26952e16751e0654fdf634ede614ddd5f4bdc5d4adb5b49da5947d85646d75445d65243d55042d44e41d34c40d1493ed0473dcf453cce433bcc4039cb3e38ca3b37c83936c73634c63433c43132c32e31c12b30c0282fbf252ebd222cbc1e2bba1a2ab91629b71128b60b27b40426',
  terrain: '0a1a3c0a1b3d0b1c3f0b1c400b1d410b1e430c1f440c20450c20470d21480d22490d234b0e244c0e244d0e254f0e26500f27510f28530f2854102956102a57102b58112c5a112d5b112d5d112e5e122f5f12306112316213326413326513336613346814356914366b14376c15386e15386f153971153a72163b73163c75163d76173e78173f7917407b18417c18427d19437f1a44801a45811b46821b48841c49851c4a861d4b881e4c891e4d8a1f4f8c1f508d20518e20528f215391215492225693225795235896245997245a99255c9a255d9b265e9d265f9e27609f2762a12863a22864a32965a52967a62a68a82a69a92b6aaa2b6bac2c6dad2c6eae2d6fb02e70b12e72b22f73b42f74b53276b73579b9377bba3a7dbc3d7fbe3f82bf4284c14486c34688c4498bc64b8dc84d8fc94f91cb5294cd5496ce5698d0589bd25b9dd45d9fd55fa2d761a4d963a6da65a9dc67abde69addf6eb0e173b3e279b6e47eb9e583bde788c0e88dc3ea92c6eb96c9ec9bcceea0d0efa4d3f1a9d6f22c6a3a2e6b3a306d3b326e3b34703b36723c38733c3a753c3b763d3d783d3f793d417b3e437c3e457e3e477f3f48813f4a823f4c84404e8540508740518940538a41558c41578d41598f425a90425d92435f93446295456596466897466a99476d9a48709c49739d4a759e4b78a04c7ba14d7da34e80a44f83a55085a75188a8528baa538dab5490ac5593ae5695af5898b1599bb25a9db35ba0b55ca2b65da5b85ea7b85fa9b961abba63adbb64afbb66b1bc68b3bd6ab5bd6bb7be6db9bf6fbbbf71bdc072bfc174c0c176c2c277c4c379c6c37bc8c47dcac57eccc580cec682d0c784d2c785d4c887d6c989d7c98bd8ca8dd8ca8fd9cb91d9cb93dacc95dbcc97dbcd99dccd9bdcce9dddce9fddcfa2decfa4ded0a6dfd0a8dfd1aae0d1ace0d2aee1d2b0e1d3b2e2d3b4e2d4b6e3d4b8e3d5bbe3d5bde4d6bfe5d7c1e6d9c3e7dac5e7dbc7e8ddcae9decceae0ceebe1d0ece2d3ede4d5eee5d7efe6d9efe8dbf0e9def1ebe0f2ece2f3eee4f4efe7f5f0e9f5f2ebf6f3edf7f5f0f8f6f2',
};
// END GENERATED LUTS

const LUT_SIZE = 256;
const lutEntries = new Map();

export function colormapEntries(name) {
  const key = COLORMAP_LUTS[name] ? name : 'viridis';
  if (!lutEntries.has(key)) {
    const data = COLORMAP_LUTS[key] || '';
    const entries = [];
    for (let offset = 0; offset + 6 <= data.length; offset += 6) {
      entries.push([0, 2, 4].map((part) => Number.parseInt(data.slice(offset + part, offset + part + 2), 16)));
    }
    lutEntries.set(key, entries);
  }
  return lutEntries.get(key);
}

// RGBA bytes for the 256×1 texture the fill shader samples with nearest filtering.
export function colormapRgba(name) {
  const bytes = new Uint8Array(LUT_SIZE * 4);
  colormapEntries(name).forEach(([r, g, b], index) => bytes.set([r, g, b, 255], index * 4));
  return bytes;
}

// The texel a nearest-filtered 256-wide texture returns for coordinate t.
export function lutIndex(t) {
  const clamped = Number.isFinite(t) ? Math.min(1, Math.max(0, t)) : 0;
  return Math.min(LUT_SIZE - 1, Math.floor(clamped * LUT_SIZE));
}

export function colormapRgb(name, t) {
  return colormapEntries(name)[lutIndex(t)] || [0, 0, 0];
}

export function colormapHex(name, t) {
  return `#${colormapRgb(name, t).map((channel) => channel.toString(16).padStart(2, '0')).join('')}`;
}

// ---------------------------------------------------------------------------
// Choosing a scale

// Same naming rule as the "identifier" role in layer_docs.js and the CLI export.
const IDENTIFIER_POINTERS = new Set(['id', 'flow_to', 'spill_to', 'glacier_flow_to']);
const ELEVATION_NAME = /(^|_)elevation(_|$)/;
const CHANGE_NAME = /(^|_)(change|delta|difference|anomaly|tendency|residual|error)(_|$)/;
const finite = (value) => typeof value === 'number' && Number.isFinite(value);

// Identifiers (plate_id, basin_id, flow_to…) are labels: id 7 is not "more"
// than id 6, so a continuous ramp would invent an order that is not there.
export function isIdentifierLayer(layer) {
  const name = String(layer?.name || '');
  return Boolean(layer) && String(layer.kind || '').startsWith('numeric')
    && (IDENTIFIER_POINTERS.has(name) || name.endsWith('_id'));
}

export function identifierHex(code) {
  const index = Number.isInteger(code) && code >= 0 ? code % QUALITATIVE_PALETTE.length : 0;
  return QUALITATIVE_PALETTE[index];
}

function isSignedLayer(stats) {
  // Both robust bounds straddle zero. A lone -1 "none" sentinel below
  // otherwise non-negative data does not make a field signed.
  return finite(stats.p2) && finite(stats.p98) && stats.p2 < 0 && stats.p98 > 0
    && !(stats.min === -1 && stats.p2 === -1);
}

function robustRange(stats) {
  let lo = stats.p2 ?? stats.min ?? 0;
  let hi = stats.p98 ?? stats.max ?? 1;
  if (lo === hi) { lo = stats.min ?? 0; hi = stats.max ?? lo + 1; }
  if (lo === hi) hi = lo + 1;
  return [lo, hi];
}

export function autoColormap(layer) {
  const stats = layer?.stats || {};
  const name = String(layer?.name || '');
  const [lo, hi] = robustRange(stats);
  if (ELEVATION_NAME.test(name) && !CHANGE_NAME.test(name) && lo < 0 && hi > 0) return 'terrain';
  if (isSignedLayer(stats)) return 'coolwarm';
  return 'viridis';
}

// Resolve how a numeric layer is coloured. The result drives the shader
// uniforms, the legend and both export codices, so they cannot disagree.
//   mode 'linear'     t = (v - lo) / (hi - lo)
//   mode 'two-slope'  lo..pivot fills the lower half, pivot..hi the upper half
//   mode 'constant'   every finite value is the same; drawn at t = 0.5
//   mode 'identifier' qualitative colour per integer id, -1 = none
export function numericScale(layer, { colormap = 'auto', range = 'robust' } = {}) {
  const stats = layer?.stats || {};
  const base = { dataMin: stats.min, dataMax: stats.max, pivot: 0, range };
  if (colormap === 'auto' && isIdentifierLayer(layer)) {
    return { ...base, mode: 'identifier', colormap: null, lo: stats.min ?? 0, hi: stats.max ?? 0, clipLow: false, clipHigh: false, auto: true };
  }
  const name = colormap === 'auto' || !COLORMAPS[colormap] ? autoColormap(layer) : colormap;
  const auto = colormap === 'auto' || !COLORMAPS[colormap];
  if (finite(stats.min) && stats.min === stats.max) {
    const value = stats.min;
    return { ...base, mode: 'constant', colormap: name, lo: value - 1, hi: value + 1, value, clipLow: false, clipHigh: false, auto };
  }
  let [lo, hi] = range === 'full' && finite(stats.min) && finite(stats.max) ? [stats.min, stats.max] : robustRange(stats);
  let mode = 'linear';
  if (name === 'coolwarm') {
    const magnitude = Math.max(Math.abs(lo), Math.abs(hi)) || 1;
    [lo, hi] = [-magnitude, magnitude];
  } else if (name === 'terrain') {
    mode = 'two-slope';
  }
  const tolerance = (value) => Math.abs(value) * 1e-6;
  return {
    ...base, mode, colormap: name, lo, hi, auto,
    clipLow: finite(stats.min) && stats.min < lo - tolerance(lo),
    clipHigh: finite(stats.max) && stats.max > hi + tolerance(hi),
  };
}

export function scalePosition(scale, value) {
  if (!scale || !finite(value)) return null;
  if (scale.mode === 'identifier') return null;
  if (scale.mode === 'constant') return 0.5;
  const { lo, hi, pivot } = scale;
  let t;
  if (scale.mode === 'two-slope') {
    if (value <= pivot) t = pivot > lo ? 0.5 * (value - lo) / (pivot - lo) : 0.5;
    else t = hi > pivot ? 0.5 + 0.5 * (value - pivot) / (hi - pivot) : 0.5;
  } else {
    t = (value - lo) / Math.max(hi - lo, 1e-12);
  }
  return Math.min(1, Math.max(0, t));
}

// Inverse of scalePosition: the value drawn at scale position t.
export function scaleValueAt(scale, t) {
  if (!scale || scale.mode === 'identifier') return null;
  if (scale.mode === 'constant') return scale.value;
  const { lo, hi, pivot } = scale;
  if (scale.mode === 'two-slope') {
    if (t < 0.5) return pivot > lo ? lo + (pivot - lo) * (t / 0.5) : pivot;
    return hi > pivot ? pivot + (hi - pivot) * ((t - 0.5) / 0.5) : pivot;
  }
  return lo + (hi - lo) * t;
}

export function scaleHex(scale, value) {
  if (!finite(value)) return NO_DATA_HEX;
  if (scale?.mode === 'identifier') return value < -0.5 ? NO_DATA_HEX : identifierHex(Math.floor(value + 0.5));
  return colormapHex(scale?.colormap || 'viridis', scalePosition(scale, value) ?? 0);
}

// Heckbert's "nice numbers" (Graphics Gems, 1990): 1, 2, 5 × 10^k steps.
function niceNumber(value, round) {
  const exponent = Math.floor(Math.log10(value));
  const fraction = value / 10 ** exponent;
  let nice;
  if (round) nice = fraction < 1.5 ? 1 : fraction < 3 ? 2 : fraction < 7 ? 5 : 10;
  else nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return nice * 10 ** exponent;
}

export function niceTicks(lo, hi, count = 5) {
  if (!finite(lo) || !finite(hi) || hi <= lo || count < 2) return [];
  const step = niceNumber(niceNumber(hi - lo, false) / (count - 1), true);
  const ticks = [];
  const start = Math.ceil(lo / step - 1e-9) * step;
  for (let value = start; value <= hi + step * 1e-9; value += step) {
    ticks.push(Math.abs(value) < step * 1e-9 ? 0 : Number(value.toPrecision(12)));
  }
  return ticks;
}

// Ticks for a legend: nice values in each half of a split scale, always
// including the pivot, so "0 m" is labelled on the terrain ramp.
export function scaleTicks(scale, count = 5) {
  if (!scale || scale.mode === 'identifier') return [];
  if (scale.mode === 'constant') return [scale.value];
  if (scale.mode === 'two-slope' && scale.lo < scale.pivot && scale.hi > scale.pivot) {
    const below = niceTicks(scale.lo, scale.pivot, Math.max(2, Math.floor(count / 2) + 1));
    const above = niceTicks(scale.pivot, scale.hi, Math.max(2, Math.floor(count / 2) + 1));
    return [...new Set([...below, scale.pivot, ...above])].sort((a, b) => a - b);
  }
  return niceTicks(scale.lo, scale.hi, count);
}

export function scaleSummary(scale) {
  if (!scale) return '';
  if (scale.mode === 'identifier') return 'Identifiers — colours name groups, they do not measure anything';
  if (scale.mode === 'constant') return 'Every cell has the same value';
  const map = COLORMAPS[scale.colormap]?.label || scale.colormap;
  const range = scale.colormap === 'coolwarm' ? 'symmetric about 0'
    : scale.range === 'full' ? 'full data range' : '2nd–98th percentile';
  return `${map} · ${range}${scale.mode === 'two-slope' ? ' · split at 0' : ''}`;
}
