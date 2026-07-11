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
import { layerDoc, layerTooltip, searchTerms, helpHtml } from './docs.js';

const MISSING_SENTINEL = 3.0e38;   // NaN replacement survives every GPU driver
const PLANE_SCALE = new THREE.Vector2(2.0, 1.0); // equirect/mollweide plane half-extent

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
  overlays: { wireframe: false, plates: false, graticule: false },
  pickDirty: true,
  hoverCell: -1,
  selectedCell: -1,
  docCard: localStorage.getItem('magicGeoDocCard') === '1',
  helpOpen: false,
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

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return response.json();
}

function layerCacheKey(layerId, stage, month) {
  return `${layerId}|${stage}|${month}`;
}

async function fetchLayerValues(layer, stage, month) {
  const key = layerCacheKey(layer.id, stage, month);
  if (state.layerCache.has(key)) {
    const cached = state.layerCache.get(key);
    state.layerCache.delete(key);
    state.layerCache.set(key, cached);   // refresh LRU position
    return cached;
  }
  const params = new URLSearchParams();
  if (layer.kind === 'numeric_stage') params.set('stage', String(stage));
  if (layer.kind === 'numeric_monthly') params.set('month', String(month));
  const buffer = await fetchBuffer(`/api/layer/${layer.id}?${params}`);
  const raw = new Float32Array(buffer);
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
  if (layer.kind !== 'numeric_stage') return;
  const count = layer.stage_count || 1;
  for (const delta of [1, -1, 2, -2]) {
    const neighbor = stage + delta;
    if (neighbor >= 0 && neighbor < count && !state.layerCache.has(layerCacheKey(layer.id, neighbor, 0))) {
      fetchLayerValues(layer, neighbor, 0).catch(() => {});
    }
  }
}

// ---------------------------------------------------------------------------
// Scene construction

async function buildScene() {
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

  const [positions, cellIds, indices, posEq, posMo] = await Promise.all([
    fetchBuffer('/mesh/positions.f32'),
    fetchBuffer('/mesh/cell_ids.u32'),
    fetchBuffer('/mesh/indices.u32'),
    fetchBuffer('/mesh/pos_equirect.f32'),
    fetchBuffer('/mesh/pos_mollweide.f32'),
  ]);

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(positions), 3));
  geometry.setAttribute('aPosEq', new THREE.BufferAttribute(new Float32Array(posEq), 2));
  geometry.setAttribute('aPosMo', new THREE.BufferAttribute(new Float32Array(posMo), 2));
  const idFloats = Float32Array.from(new Uint32Array(cellIds));
  geometry.setAttribute('aCellId', new THREE.BufferAttribute(idFloats, 1));
  geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(indices), 1));

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
    valueTexture, texWidth, texHeight,
    plateLines: null, graticuleLines: null, sharedUniforms,
  });
  resizeRenderer();
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

async function ensurePlateLines() {
  if (three.plateLines) return;
  const segments = await fetchJson('/api/plate-boundaries');
  three.plateLines = makeLineSegments(segments, [1.0, 0.42, 0.32], 0.9, 0.004);
  three.plateLines.visible = false;
  three.scene.add(three.plateLines);
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
  const canvas = three.renderer.domElement;
  const width = canvas.clientWidth || canvas.parentElement.clientWidth;
  const height = canvas.clientHeight || canvas.parentElement.clientHeight;
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

  three.controls.update();
  three.renderer.render(three.scene, three.camera);
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
  $('#legend-title').textContent = layer ? `${layer.source} / ${layer.name}` : 'no layer';
  const ramp = $('#legend-ramp');
  const categoriesBox = $('#legend-categories');
  categoriesBox.innerHTML = '';
  if (!layer) { ramp.style.display = 'none'; return; }
  if (layer.kind === 'categorical') {
    ramp.style.display = 'none';
    $('#legend-min').textContent = '';
    $('#legend-max').textContent = '';
    layer.categories.forEach((category, index) => {
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
  $('#legend-min').textContent = formatValue(lo);
  $('#legend-max').textContent = formatValue(hi);
}

// ---------------------------------------------------------------------------
// Docs helper: per-layer doc card + help overlay (content from docs.js)

function renderLayerDoc(layer) {
  const card = $('#layer-doc');
  card.classList.toggle('hidden', !state.docCard || !layer);
  $('#legend-info').classList.toggle('active', state.docCard);
  if (!state.docCard || !layer) return;
  const doc = layerDoc(layer);
  const parts = [];
  parts.push(`<h4>${escapeHtml(doc.id)}</h4>`);
  const topicBits = [doc.topic, doc.kindLabel].filter(Boolean);
  if (doc.unit) topicBits.push(`unit: <span class="doc-unit">${escapeHtml(doc.unit)}</span>`);
  parts.push(`<div class="doc-topic">${topicBits.join(' · ')}</div>`);
  if (doc.summary) parts.push(`<p>${escapeHtml(doc.summary)}</p>`);
  else if (doc.unitMeaning) parts.push(`<p class="doc-dim">${escapeHtml(doc.unitMeaning)}.</p>`);
  if (layer.stats) {
    const stats = layer.stats;
    parts.push('<table>'
      + `<tr><td>min / max</td><td>${formatValue(stats.min)} … ${formatValue(stats.max)}</td></tr>`
      + `<tr><td>legend (p2 / p98)</td><td>${formatValue(stats.p2)} … ${formatValue(stats.p98)}</td></tr>`
      + '</table>');
  }
  if (layer.kind === 'categorical') {
    parts.push(`<p class="doc-dim">${layer.categories.length} categories — see legend chips.</p>`);
  }
  if (doc.topicDoc) parts.push(`<p class="doc-dim">${escapeHtml(doc.topicDoc)}</p>`);
  if (doc.sourceDoc) parts.push(`<p class="doc-dim">${escapeHtml(doc.sourceDoc)}</p>`);
  card.innerHTML = parts.join('');
}

function toggleDocCard(force) {
  state.docCard = force !== undefined ? force : !state.docCard;
  localStorage.setItem('magicGeoDocCard', state.docCard ? '1' : '0');
  renderLayerDoc(state.activeLayer);
}

function toggleHelp(force) {
  state.helpOpen = force !== undefined ? force : !state.helpOpen;
  const overlay = $('#help-overlay');
  if (state.helpOpen && !overlay.dataset.built) {
    $('#help-body').innerHTML = helpHtml(state.manifest);
    overlay.dataset.built = '1';
  }
  overlay.classList.toggle('hidden', !state.helpOpen);
  $('#toggle-help').classList.toggle('active', state.helpOpen);
}

function layerRange(layer) {
  const stats = layer.stats || {};
  let lo = stats.p2 ?? stats.min ?? 0;
  let hi = stats.p98 ?? stats.max ?? 1;
  if (lo === hi) { lo = stats.min ?? 0; hi = stats.max ?? lo + 1; }
  if (lo === hi) hi = lo + 1;
  return [lo, hi];
}

async function activateLayer(layer, { stage = null, month = null } = {}) {
  state.activeLayer = layer;
  if (stage !== null) state.stage = stage;
  if (month !== null) state.month = month;
  if (layer.kind === 'numeric_stage') {
    state.stage = Math.min(state.stage, (layer.stage_count || 1) - 1);
  }
  document.querySelectorAll('.layer-item').forEach((item) => {
    item.classList.toggle('active', item.dataset.layerId === layer.id);
  });

  const values = await fetchLayerValues(layer, state.stage, state.month);
  if (state.activeLayer !== layer) return;   // superseded while fetching
  uploadValues(values);

  const [lo, hi] = layerRange(layer);
  three.fillMaterial.uniforms.uMin.value = lo;
  three.fillMaterial.uniforms.uMax.value = hi;
  three.fillMaterial.uniforms.uCategorical.value = layer.kind === 'categorical' ? 1 : 0;
  updateLegend(layer);
  renderLayerDoc(layer);
  updateStageBar();
  prefetchNeighborStages(layer, state.stage);
  updateStatus();
}

// ---------------------------------------------------------------------------
// Stage / month control

function stageBarConfig() {
  const layer = state.activeLayer;
  if (!layer) return null;
  if (layer.kind === 'numeric_stage') {
    const history = state.manifest.stage_histories[layer.source] || {};
    return {
      max: (layer.stage_count || 1) - 1,
      value: state.stage,
      label: () => {
        const meta = (history.stages || [])[state.stage] || {};
        const bits = [`stage_idx ${state.stage}`];
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
      label: () => `month ${state.month + 1}`,
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
  slider.value = String(config.value);
  number.value = String(config.value);
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
  const kindBadge = { numeric_stage: 'stages', numeric_monthly: 'monthly', categorical: 'cat' };
  for (const [source, layers] of groups) {
    const title = document.createElement('div');
    title.className = 'layer-group-title';
    title.textContent = `${source} (${layers.length})`;
    container.appendChild(title);
    const body = document.createElement('div');
    container.appendChild(body);
    title.addEventListener('click', () => {
      body.style.display = body.style.display === 'none' ? '' : 'none';
    });
    for (const layer of layers) {
      const item = document.createElement('div');
      item.className = 'layer-item';
      item.dataset.layerId = layer.id;
      item.dataset.search = `${layer.source} ${layer.name} ${searchTerms(layer)}`.toLowerCase();
      item.title = layerTooltip(layer);
      item.textContent = layer.name;
      if (kindBadge[layer.kind]) {
        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = kindBadge[layer.kind];
        item.appendChild(badge);
      }
      item.addEventListener('click', () => activateLayer(layer));
      body.appendChild(item);
    }
  }
}

function filterLayerList(query) {
  const needle = query.trim().toLowerCase();
  document.querySelectorAll('.layer-item').forEach((item) => {
    item.style.display = !needle || item.dataset.search.includes(needle) ? '' : 'none';
  });
}

// ---------------------------------------------------------------------------
// Cell inspector

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
  return `<svg class="sparkline" width="${width}" height="${height}">`
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
  state.selectedCell = cellId;
  const inspector = $('#inspector');
  inspector.classList.remove('hidden');
  $('#inspector-title').textContent = `Cell ${cellId}`;
  $('#inspector-body').innerHTML = '<em>loading…</em>';
  resizeRenderer();
  let record;
  try {
    record = await fetchJson(`/api/cell/${cellId}`);
  } catch (error) {
    $('#inspector-body').textContent = String(error);
    return;
  }
  if (state.selectedCell !== cellId) return;

  const cell = record.cell;
  const parts = [];
  parts.push('<input id="inspector-filter" type="search" placeholder="Filter fields…">');

  parts.push('<div class="inspector-section"><h3>Ledger slices (per stage)</h3>');
  for (const [historyName, ledger] of Object.entries(record.ledgers || {})) {
    parts.push(`<div class="spark-row"><span class="k">${escapeHtml(historyName)}</span></div>`);
    for (const [field, values] of Object.entries(ledger.fields)) {
      const numeric = values.filter((value) => typeof value === 'number');
      if (!numeric.length) continue;
      const marker = state.activeLayer && state.activeLayer.source === historyName ? state.stage : -1;
      parts.push(`<div class="spark-row"><span class="k">${escapeHtml(field)}</span>${sparklineSvg(values, { marker })}</div>`);
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
      + `<span class="v">${escapeHtml(formatValue(value))}</span></div>`,
    );
  }
  parts.push('</div></div>');

  parts.push(`<div class="inspector-section"><h3>Adjacency (${record.adjacency_edges.length} edges)</h3>`);
  for (const edge of record.adjacency_edges) {
    const other = edge.cell_a_id === cellId ? edge.cell_b_id : edge.cell_a_id;
    const flags = ['plate_boundary', 'land_water_transition', 'biome_transition']
      .filter((flag) => edge[flag]).join(', ');
    parts.push(
      `<div class="field-row"><span class="k">→ <a href="#" data-cell="${other}" style="color:#4da3ff">cell ${other}</a>`
      + `${flags ? ` <span style="color:#ffb454">${escapeHtml(flags)}</span>` : ''}</span>`
      + `<span class="v">${formatValue(edge.great_circle_distance_km)} km</span></div>`,
    );
  }
  parts.push('</div>');

  const body = $('#inspector-body');
  body.innerHTML = parts.join('');
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
}

// ---------------------------------------------------------------------------
// Status bar

function updateStatus() {
  const status = $('#status');
  const layer = state.activeLayer;
  const bits = [];
  if (layer) bits.push(`${layer.source}/${layer.name}`);
  if (state.hoverCell >= 0) {
    bits.push(`cell ${state.hoverCell}`);
    if (state.values && layer) {
      const value = state.values[state.hoverCell];
      if (value !== undefined && value < 1e37) {
        bits.push(layer.kind === 'categorical'
          ? (layer.categories[Math.round(value)] ?? '—')
          : formatValue(value));
      } else {
        bits.push('—');
      }
    }
  }
  status.textContent = bits.join('  ·  ');
}

// ---------------------------------------------------------------------------
// Interaction wiring

function setProjection(projection) {
  state.projection = projection;
  document.querySelectorAll('#projection-controls button').forEach((button) => {
    button.classList.toggle('active', button.dataset.proj === projection);
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

function wireEvents() {
  window.addEventListener('resize', resizeRenderer);

  document.querySelectorAll('#projection-controls button').forEach((button) => {
    button.addEventListener('click', () => setProjection(button.dataset.proj));
  });

  $('#toggle-wireframe').addEventListener('click', () => {
    state.overlays.wireframe = !state.overlays.wireframe;
    three.wireMesh.visible = state.overlays.wireframe;
    $('#toggle-wireframe').classList.toggle('active', state.overlays.wireframe);
  });
  $('#toggle-plates').addEventListener('click', async () => {
    state.overlays.plates = !state.overlays.plates;
    $('#toggle-plates').classList.toggle('active', state.overlays.plates);
    await ensurePlateLines();
    three.plateLines.visible = state.overlays.plates;
  });
  $('#toggle-graticule').addEventListener('click', () => {
    state.overlays.graticule = !state.overlays.graticule;
    $('#toggle-graticule').classList.toggle('active', state.overlays.graticule);
    buildGraticule();
    three.graticuleLines.visible = state.overlays.graticule;
  });

  $('#layer-search').addEventListener('input', (event) => filterLayerList(event.target.value));

  $('#toggle-help').addEventListener('click', () => toggleHelp());
  $('#help-close').addEventListener('click', () => toggleHelp(false));
  $('#help-overlay').addEventListener('click', (event) => {
    if (event.target === $('#help-overlay')) toggleHelp(false);
  });
  $('#legend-info').addEventListener('click', () => toggleDocCard());

  const slider = $('#stage-slider');
  const number = $('#stage-number');
  slider.addEventListener('input', () => {
    const config = stageBarConfig();
    if (config) config.set(Number(slider.value));
  });
  number.addEventListener('change', () => {
    const config = stageBarConfig();
    if (config) config.set(Math.min(Number(number.max), Math.max(0, Number(number.value))));
  });
  $('#stage-back').addEventListener('click', () => stepStage(-1));
  $('#stage-fwd').addEventListener('click', () => stepStage(1));

  $('#inspector-close').addEventListener('click', () => {
    $('#inspector').classList.add('hidden');
    state.selectedCell = -1;
    resizeRenderer();
  });

  const canvas = three.renderer.domElement;
  let lastMove = 0;
  let downAt = null;
  canvas.addEventListener('pointerdown', (event) => { downAt = [event.clientX, event.clientY]; });
  canvas.addEventListener('pointerup', (event) => {
    if (!downAt) return;
    const dx = event.clientX - downAt[0];
    const dy = event.clientY - downAt[1];
    downAt = null;
    if (dx * dx + dy * dy > 16) return;   // drag, not click
    const cell = pickCell(event.clientX, event.clientY);
    if (cell >= 0) openInspector(cell);
  });
  canvas.addEventListener('pointermove', (event) => {
    const now = performance.now();
    if (now - lastMove < 40) return;
    lastMove = now;
    state.hoverCell = pickCell(event.clientX, event.clientY);
    updateStatus();
  });
  three.controls.addEventListener('change', () => { state.pickDirty = true; });

  window.addEventListener('keydown', (event) => {
    if (event.target.tagName === 'INPUT') return;
    switch (event.key) {
      case ',': stepStage(-1); break;
      case '.': stepStage(1); break;
      case '1': setProjection('globe'); break;
      case '2': setProjection('equirect'); break;
      case '3': setProjection('mollweide'); break;
      case 'w': $('#toggle-wireframe').click(); break;
      case 'b': $('#toggle-plates').click(); break;
      case 'g': $('#toggle-graticule').click(); break;
      case 'i': toggleDocCard(); break;
      case '?': case 'h': toggleHelp(); break;
      case 'Escape':
        if (state.helpOpen) { toggleHelp(false); break; }
        if (state.docCard) { toggleDocCard(false); break; }
        if (state.selectedCell >= 0) $('#inspector-close').click();
        break;
      case '/': event.preventDefault(); $('#layer-search').focus(); break;
      default: break;
    }
  });
}

// ---------------------------------------------------------------------------
// Boot

async function main() {
  state.manifest = await fetchJson('/api/manifest');
  state.cellCount = state.manifest.world.cell_count;
  const world = state.manifest.world;
  $('#world-meta').innerHTML = [
    `${escapeHtml(world.name ?? 'world')} · ${world.cell_count} cells`,
    `${escapeHtml(world.mesh_backend ?? '')} · scope ${escapeHtml(world.generation_scope ?? 'full')}`,
    `${state.manifest.layers.length} layers · ${Object.keys(state.manifest.stage_histories).length} stage histories`,
  ].join('<br>');

  await buildScene();
  buildLayerList();
  wireEvents();
  animate();

  const initial = state.manifest.layers.find((layer) => layer.id === 'cells/elevation_m')
    || state.manifest.layers.find((layer) => layer.kind === 'numeric')
    || state.manifest.layers[0];
  if (initial) await activateLayer(initial);
}

main().catch((error) => {
  document.body.innerHTML = `<pre style="color:#ff6b6b; padding: 20px">${escapeHtml(error.stack || String(error))}</pre>`;
});
