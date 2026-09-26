// Map navigation: camera placement, gestures and animated moves for the globe
// and the flat projections.
//
// The view is stored geographically: the latitude/longitude at the centre of
// the screen and `span`, the arc of planet surface (radians) visible across the
// viewport height. Globe and flat maps derive their cameras from that one
// state, so switching projection keeps the same place at the same scale, and a
// morph between them keeps the centre fixed on screen.
//
// Frames: the planet frame is z-polar with x toward longitude 0; the render
// frame is y-up, render = (planet.y, planet.z, planet.x). Flat maps lie in the
// render z = 0 plane: x in [-2, 2] and y in [-1, 1] (see MORPH_CHUNK in app.js).

const DEG = Math.PI / 180;
const PLANE_UNITS_PER_RADIAN = 2 / Math.PI;  // 4 plane units per 360°, 2 per 180°
const GLOBE_LAT_LIMIT = 89;
const MAX_GLOBE_ALTITUDE = 6;                  // radii above the surface
const HOME_FILL = 0.84;                         // share of the viewport the fitted world fills
const HOME_FILL_NARROW = 0.72;                  // phones: leave room for the toolbars
const DRAG_CLICK_TOLERANCE_PX = 4;
// Inertia after a drag uses MapLibre GL JS's pan defaults (handler_inertia.ts):
// speed = release velocity × linearity, capped; then a linear deceleration, so
// duration = speed / (deceleration × linearity) and distance = speed × duration / 2.
const INERTIA_LINEARITY = 0.3;
const INERTIA_MAX_SPEED = 1400;                // px/s
const INERTIA_DECELERATION = 2500;             // px/s²
const INERTIA_WINDOW_MS = 60;                  // velocity is measured over the last 60 ms
const WHEEL_SMOOTHING_MS = 90;
const KEY_EASE_MS = 300;
const FLY_SPEED = 1.2;                          // MapLibre flyTo default speed
const FLY_RHO = 1.42;                           // van Wijk & Nuij ρ chosen in their user study

const clamp = (value, lo, hi) => Math.min(hi, Math.max(lo, value));
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const scale = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const lerp3 = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
function normalize(a) {
  const length = Math.hypot(a[0], a[1], a[2]) || 1;
  return [a[0] / length, a[1] / length, a[2] / length];
}
const easeOutCubic = (t) => 1 - (1 - t) ** 3;
const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
const easeOutQuad = (t) => t * (2 - t);

// ---------------------------------------------------------------------------
// Geography helpers

export function wrapLongitude(lon) {
  const wrapped = ((((lon + 180) % 360) + 360) % 360) - 180;
  return wrapped === -180 && lon > 0 ? 180 : wrapped;
}

export function renderVector(latDeg, lonDeg) {
  const lat = latDeg * DEG;
  const lon = lonDeg * DEG;
  return [Math.cos(lat) * Math.sin(lon), Math.sin(lat), Math.cos(lat) * Math.cos(lon)];
}

export function latLonFromVector(vector) {
  const [x, y, z] = normalize(vector);
  return { lat: Math.asin(clamp(y, -1, 1)) / DEG, lon: Math.atan2(x, z) / DEG };
}

// Unit tangent pointing north at (lat, lon); well defined at the poles too.
function northTangent(latDeg, lonDeg) {
  const lat = latDeg * DEG;
  const lon = lonDeg * DEG;
  return [-Math.sin(lat) * Math.sin(lon), Math.cos(lat), -Math.sin(lat) * Math.cos(lon)];
}

// Solve 2θ + sin 2θ = π sin φ for the Mollweide auxiliary angle. Newton's
// derivative vanishes at the poles, so start there from the asymptotic
// solution π/2 − θ ≈ (3π δ² / 8)^(1/3), δ = π/2 − |φ|, and iterate to
// convergence: a fixed 8 steps from θ = φ is 0.1° wrong at 89.9°.
export function mollweideTheta(lat) {
  const half = Math.PI / 2;
  if (Math.abs(lat) >= half - 1e-12) return Math.sign(lat) * half;
  const target = Math.PI * Math.sin(lat);
  const delta = half - Math.abs(lat);
  let theta = Math.abs(lat) > 1.4 ? Math.sign(lat) * (half - Math.cbrt((3 * Math.PI * delta * delta) / 8)) : lat;
  for (let i = 0; i < 50; i += 1) {
    const derivative = 2 + 2 * Math.cos(2 * theta);
    if (derivative < 1e-15) break;
    const step = (2 * theta + Math.sin(2 * theta) - target) / derivative;
    theta = Math.max(-half, Math.min(half, theta - step));
    if (Math.abs(step) < 1e-14) break;
  }
  return theta;
}

// Flat-map position in render units. `blend` is 0 for equirectangular, 1 for
// Mollweide, matching the uProj2D uniform; strings are accepted for clarity.
export function projectToPlane(latDeg, lonDeg, blend = 0) {
  const mix = blend === 'mollweide' ? 1 : blend === 'equirect' ? 0 : Number(blend) || 0;
  const equirect = [(lonDeg / 180) * 2, latDeg / 90];
  if (mix <= 0) return equirect;
  const theta = mollweideTheta(latDeg * DEG);
  const mollweide = [2 * (lonDeg * DEG / Math.PI) * Math.cos(theta), Math.sin(theta)];
  if (mix >= 1) return mollweide;
  return [equirect[0] + (mollweide[0] - equirect[0]) * mix, equirect[1] + (mollweide[1] - equirect[1]) * mix];
}

// Inverse of projectToPlane for a pure projection; null outside the map.
export function unprojectFromPlane(x, y, projection = 'equirect') {
  if (projection === 'mollweide' || projection === 1) {
    if (Math.abs(y) > 1) return null;
    const theta = Math.asin(y);
    const cosTheta = Math.cos(theta);
    const lon = cosTheta < 1e-9 ? 0 : (Math.PI * (x / 2)) / cosTheta;
    if (Math.abs(lon) > Math.PI + 1e-9) return null;
    const lat = Math.asin(clamp((2 * theta + Math.sin(2 * theta)) / Math.PI, -1, 1));
    return { lat: lat / DEG, lon: clamp(lon / DEG, -180, 180) };
  }
  if (Math.abs(x) > 2 + 1e-9 || Math.abs(y) > 1 + 1e-9) return null;
  return { lat: clamp(y * 90, -90, 90), lon: clamp(x * 90, -180, 180) };
}

export function greatCircleAngle(a, b) {
  // Haversine form: accurate for both tiny and near-antipodal separations.
  const lat1 = a.lat * DEG;
  const lat2 = b.lat * DEG;
  const dLat = lat2 - lat1;
  const dLon = (b.lon - a.lon) * DEG;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * Math.asin(Math.min(1, Math.sqrt(h)));
}

// Point a fraction of the way along the great circle from a to b. Fractions
// outside [0, 1] extrapolate along the same circle.
export function interpolateGreatCircle(a, b) {
  const va = renderVector(a.lat, a.lon);
  const vb = renderVector(b.lat, b.lon);
  const angle = Math.acos(clamp(dot(va, vb), -1, 1));
  if (angle < 1e-9) return () => ({ lat: a.lat, lon: a.lon });
  const sin = Math.sin(angle);
  if (sin < 1e-6) {
    // Antipodal: every great circle qualifies; pass over the nearer pole.
    const via = { lat: a.lat >= 0 ? 90 - Math.abs(a.lat) : -(90 - Math.abs(a.lat)), lon: a.lon };
    const first = interpolateGreatCircle(a, via);
    const second = interpolateGreatCircle(via, b);
    return (f) => (f < 0.5 ? first(f * 2) : second(f * 2 - 1));
  }
  return (fraction) => {
    const wa = Math.sin((1 - fraction) * angle) / sin;
    const wb = Math.sin(fraction * angle) / sin;
    return latLonFromVector(add(scale(va, wa), scale(vb, wb)));
  };
}

// van Wijk & Nuij (2003), "Smooth and efficient zooming and panning": the
// optimal path between views (u = centre, w = visible width) in the same form
// as d3.interpolateZoom. Returns a function of t in [0, 1] plus the path
// length S, which sets the duration so perceived speed is constant.
export function zoomPath([ux0, uy0, w0], [ux1, uy1, w1], rho = FLY_RHO) {
  const rho2 = rho * rho;
  const rho4 = rho2 * rho2;
  const dx = ux1 - ux0;
  const dy = uy1 - uy0;
  const d2 = dx * dx + dy * dy;
  let S;
  let at;
  if (d2 < 1e-12) {
    S = Math.log(w1 / w0) / rho;
    at = (t) => [ux0 + t * dx, uy0 + t * dy, w0 * Math.exp(rho * t * S)];
  } else {
    const d1 = Math.sqrt(d2);
    const b0 = (w1 * w1 - w0 * w0 + rho4 * d2) / (2 * w0 * rho2 * d1);
    const b1 = (w1 * w1 - w0 * w0 - rho4 * d2) / (2 * w1 * rho2 * d1);
    const r0 = Math.log(Math.sqrt(b0 * b0 + 1) - b0);
    const r1 = Math.log(Math.sqrt(b1 * b1 + 1) - b1);
    S = (r1 - r0) / rho;
    at = (t) => {
      const s = t * S;
      const coshr0 = Math.cosh(r0);
      const u = (w0 / (rho2 * d1)) * (coshr0 * Math.tanh(rho * s + r0) - Math.sinh(r0));
      return [ux0 + u * dx, uy0 + u * dy, (w0 * coshr0) / Math.cosh(rho * s + r0)];
    };
  }
  return { at, length: Math.abs(S) };
}

export function formatLatLon(lat, lon, digits = 2) {
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return '';
  const part = (value, positive, negative) => {
    const rounded = Number(Math.abs(value).toFixed(digits));
    const hemisphere = rounded === 0 ? '' : ` ${value >= 0 ? positive : negative}`;
    return `${rounded.toFixed(digits)}°${hemisphere}`;
  };
  return `${part(lat, 'N', 'S')}, ${part(wrapLongitude(lon), 'E', 'W')}`;
}

// Largest 1/2/5 × 10^k not above maxValue, for scale bars.
export function niceDistance(maxValue) {
  if (!Number.isFinite(maxValue) || maxValue <= 0) return 0;
  const exponent = Math.floor(Math.log10(maxValue));
  const base = 10 ** exponent;
  const fraction = maxValue / base;
  return (fraction >= 5 ? 5 : fraction >= 2 ? 2 : 1) * base;
}

export function formatDistance(km) {
  if (!Number.isFinite(km)) return '';
  if (km >= 1) return `${Number(km.toPrecision(6)).toLocaleString('en-US')} km`;
  return `${Number((km * 1000).toPrecision(6)).toLocaleString('en-US')} m`;
}

// ---------------------------------------------------------------------------
// Direction interpolation for the globe <-> flat camera blend

function slerpDirection(a, b, t) {
  if (t <= 0) return a;
  if (t >= 1) return b;
  const cosine = clamp(dot(a, b), -1, 1);
  if (cosine > 0.9995) return normalize(lerp3(a, b, t));
  if (cosine < -0.9995) {
    const ortho = normalize(cross(a, Math.abs(a[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0]));
    return t < 0.5 ? slerpDirection(a, ortho, t * 2) : slerpDirection(ortho, b, t * 2 - 1);
  }
  const angle = Math.acos(cosine);
  const sin = Math.sin(angle);
  return add(scale(a, Math.sin((1 - t) * angle) / sin), scale(b, Math.sin(t * angle) / sin));
}

// ---------------------------------------------------------------------------
// Navigator

export function createMapNavigator({
  element,
  camera,
  getMorph = () => ({ value: 0, proj2D: 0 }),
  cellCount = 0,
  reducedMotion = () => false,
  now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now()),
} = {}) {
  const listeners = { change: new Set(), end: new Set(), start: new Set() };
  const view = { lat: 0, lon: 0, span: 2 };
  const pose = {
    position: [0, 0, 3], target: [0, 0, 0], forward: [0, 0, -1], right: [1, 0, 0], up: [0, 1, 0], distance: 3,
  };
  const target = { x: 0, y: 0, z: 0 };  // OrbitControls-compatible, read by map exports
  let projection = 'globe';
  let animation = null;
  // True while the view is a fitted whole-world view nobody has moved since:
  // a resize then refits instead of leaving the world cropped or tiny.
  let fitted = false;
  let dirty = true;
  let moving = false;
  let endTimer = 0;
  let lastPoseKey = '';
  const pointers = new Map();
  let drag = null;
  let pinch = null;
  let abort = null;

  const emit = (type) => listeners[type]?.forEach((listener) => { try { listener({ type }); } catch (error) { console.error(error); } });
  const tanHalfFov = () => Math.tan(((camera?.fov ?? 50) * DEG) / 2);
  const rect = () => element?.getBoundingClientRect?.() ?? { left: 0, top: 0, width: 1, height: 1 };
  const viewportSize = () => {
    const box = rect();
    return { width: Math.max(1, box.width || element?.clientWidth || 1), height: Math.max(1, box.height || element?.clientHeight || 1) };
  };
  const morph = () => {
    const current = getMorph() || {};
    return { value: clamp(Number(current.value) || 0, 0, 1), proj2D: clamp(Number(current.proj2D) || 0, 0, 1) };
  };
  const flat = () => projection !== 'globe';
  const planeBlend = () => (projection === 'mollweide' ? 1 : 0);

  // -- limits ---------------------------------------------------------------

  const cellSpacing = () => (cellCount > 0 ? Math.sqrt((4 * Math.PI) / cellCount) : 0.05);
  function fitSpan(forProjection = projection) {
    const { width, height } = viewportSize();
    const aspect = width / height;
    const tanH = tanHalfFov();
    const fill = width < 600 ? HOME_FILL_NARROW : HOME_FILL;
    if (forProjection === 'globe') {
      // Globe angular radius asin(1 / (1 + a)) should fill `fill` of the
      // shorter viewport side: tan(radius) = fill · tan(fov/2) · min(1, aspect).
      const k = fill * tanH * Math.min(1, aspect);
      const altitude = Math.sqrt(1 + k * k) / k - 1;
      return 2 * altitude * tanH;
    }
    const distance = Math.max(1, 2 / aspect) / (tanH * fill);
    return (distance * 2 * tanH) / PLANE_UNITS_PER_RADIAN;
  }
  const minSpan = () => Math.max(0.002, 2 * cellSpacing());
  const maxSpan = () => (flat() ? fitSpan(projection) * 1.8 : 2 * MAX_GLOBE_ALTITUDE * tanHalfFov());
  const clampSpan = (span) => clamp(span, minSpan(), Math.max(minSpan(), maxSpan()));
  const altitudeFor = (span) => span / (2 * tanHalfFov());
  const planeDistanceFor = (span) => (span * PLANE_UNITS_PER_RADIAN) / (2 * tanHalfFov());

  function clampView() {
    view.span = clampSpan(view.span);
    view.lon = wrapLongitude(view.lon);
    view.lat = clamp(view.lat, flat() ? -90 : -GLOBE_LAT_LIMIT, flat() ? 90 : GLOBE_LAT_LIMIT);
  }

  // -- camera pose ---------------------------------------------------------

  function computePose() {
    const { value: m, proj2D } = morph();
    const surface = renderVector(view.lat, view.lon);
    const [px, py] = projectToPlane(view.lat, view.lon, proj2D);
    const center = lerp3(surface, [px, py, 0], m);
    const direction = normalize(slerpDirection(surface, [0, 0, 1], m));
    const altitude = altitudeFor(view.span);
    const planeDistance = planeDistanceFor(view.span);
    const distance = altitude + (planeDistance - altitude) * m;
    const upHint = normalize(slerpDirection(northTangent(view.lat, view.lon), [0, 1, 0], m));
    const forward = scale(direction, -1);
    let right = cross(forward, upHint);
    if (Math.hypot(...right) < 1e-9) right = [1, 0, 0];
    right = normalize(right);
    const up = normalize(cross(right, forward));
    Object.assign(pose, { position: add(center, scale(direction, distance)), target: center, forward, right, up, distance });
  }

  function applyPose() {
    computePose();
    Object.assign(target, { x: pose.target[0], y: pose.target[1], z: pose.target[2] });
    if (!camera) return;
    camera.position?.set?.(...pose.position);
    camera.up?.set?.(...pose.up);
    camera.lookAt?.(...pose.target);
    // Keep the depth range tight around what is visible for precision.
    const near = Math.max(1e-4, pose.distance * 0.05);
    const far = pose.distance + 4;
    if (Math.abs((camera.near ?? 0) - near) > near * 0.05 || Math.abs((camera.far ?? 0) - far) > 0.05) {
      camera.near = near;
      camera.far = far;
      camera.updateProjectionMatrix?.();
    }
  }

  // -- screen <-> world ----------------------------------------------------

  function rayAt(clientX, clientY) {
    const box = rect();
    const width = Math.max(1, box.width);
    const height = Math.max(1, box.height);
    const ndcX = ((clientX - box.left) / width) * 2 - 1;
    const ndcY = 1 - ((clientY - box.top) / height) * 2;
    const tanH = tanHalfFov();
    const direction = normalize(add(pose.forward, add(scale(pose.right, ndcX * tanH * (width / height)), scale(pose.up, ndcY * tanH))));
    return { origin: pose.position, direction };
  }

  function globeHit(ray) {
    const b = dot(ray.origin, ray.direction);
    const c = dot(ray.origin, ray.origin) - 1;
    const discriminant = b * b - c;
    if (discriminant < 0) return null;
    const t = -b - Math.sqrt(discriminant);
    return t > 0 ? add(ray.origin, scale(ray.direction, t)) : null;
  }

  function planeHit(ray) {
    if (Math.abs(ray.direction[2]) < 1e-9) return null;
    const t = -ray.origin[2] / ray.direction[2];
    return t > 0 ? add(ray.origin, scale(ray.direction, t)) : null;
  }

  // Geographic point under a client position, or null off the map and while
  // a projection morph is in flight (the surface is between shapes then).
  function screenToLatLon(clientX, clientY) {
    const { value: m } = morph();
    const ray = rayAt(clientX, clientY);
    if (m <= 0.001) {
      const hit = globeHit(ray);
      return hit ? latLonFromVector(hit) : null;
    }
    if (m >= 0.999) {
      const hit = planeHit(ray);
      return hit ? unprojectFromPlane(hit[0], hit[1], projection === 'mollweide' ? 'mollweide' : 'equirect') : null;
    }
    return null;
  }

  // Client position of a geographic point; `visible` is false behind the
  // globe's horizon or off screen.
  function latLonToScreen(lat, lon) {
    const { value: m, proj2D } = morph();
    const surface = renderVector(lat, lon);
    const [px, py] = projectToPlane(lat, lon, proj2D);
    const point = lerp3(surface, [px, py, 0], m);
    const relative = sub(point, pose.position);
    const depth = dot(relative, pose.forward);
    const box = rect();
    if (depth <= 1e-6) return { x: 0, y: 0, visible: false, depth };
    const tanH = tanHalfFov();
    const aspect = Math.max(1, box.width) / Math.max(1, box.height);
    const ndcX = dot(relative, pose.right) / (depth * tanH * aspect);
    const ndcY = dot(relative, pose.up) / (depth * tanH);
    const x = ((ndcX + 1) / 2) * box.width;
    const y = ((1 - ndcY) / 2) * box.height;
    const facing = m >= 0.5 || dot(surface, sub(pose.position, surface)) > 0;
    const onScreen = ndcX >= -1.05 && ndcX <= 1.05 && ndcY >= -1.05 && ndcY <= 1.05;
    return { x, y, visible: facing && onScreen, depth };
  }

  // -- view changes ---------------------------------------------------------

  function markChanged() {
    dirty = true;
  }

  function setPlaneCenter(x, y) {
    const bound = unprojectFromPlane(clamp(x, -2, 2), clamp(y, -1, 1), projection === 'mollweide' ? 'mollweide' : 'equirect');
    if (bound) {
      view.lat = bound.lat;
      view.lon = bound.lon;
      return;
    }
    // Outside the Mollweide ellipse: keep latitude, pin longitude to the rim.
    const lat = clamp(y, -1, 1) * 90;
    const edge = unprojectFromPlane(0, Math.sin(mollweideTheta(lat * DEG)), 'mollweide');
    view.lat = edge ? edge.lat : lat;
    view.lon = x >= 0 ? 180 : -180;
  }

  function panByPixels(dx, dy) {
    const { height } = viewportSize();
    if (!flat()) {
      const radiansPerPixel = view.span / height;
      const cosLat = Math.max(Math.cos(view.lat * DEG), 0.05);
      view.lon = wrapLongitude(view.lon - (dx * radiansPerPixel) / DEG / cosLat);
      view.lat = clamp(view.lat + (dy * radiansPerPixel) / DEG, -GLOBE_LAT_LIMIT, GLOBE_LAT_LIMIT);
    } else {
      const unitsPerPixel = (view.span * PLANE_UNITS_PER_RADIAN) / height;
      const [x, y] = projectToPlane(view.lat, view.lon, planeBlend());
      setPlaneCenter(x - dx * unitsPerPixel, y + dy * unitsPerPixel);
    }
    markChanged();
  }

  // Keep the surface point under `from` under `to` (a "grab" drag).
  function dragBetween(from, to) {
    const { value: m } = morph();
    if (m > 0.001 && m < 0.999) return;
    if (m <= 0.001) {
      const a = globeHit(rayAt(from.x, from.y));
      const b = globeHit(rayAt(to.x, to.y));
      if (a && b) {
        const pa = latLonFromVector(a);
        const pb = latLonFromVector(b);
        if (Math.abs(pa.lat) < 80 && Math.abs(pb.lat) < 80) {
          view.lon = wrapLongitude(view.lon - clamp(wrapLongitude(pb.lon - pa.lon), -20, 20));
          view.lat = clamp(view.lat - clamp(pb.lat - pa.lat, -20, 20), -GLOBE_LAT_LIMIT, GLOBE_LAT_LIMIT);
          markChanged();
          computePose();
          return;
        }
      }
    }
    panByPixels(to.x - from.x, to.y - from.y);
    computePose();
  }

  // Zoom by `factor` (span multiplier) keeping the geography under the client
  // point `anchor` fixed on screen when one is given.
  function zoomAround(factor, anchor = null) {
    const before = view.span;
    const next = clampSpan(before * factor);
    if (next === before) return;
    const point = anchor ? screenToLatLon(anchor.x, anchor.y) : null;
    if (point && flat()) {
      const blend = planeBlend();
      const [ax, ay] = projectToPlane(point.lat, point.lon, blend);
      const [cx, cy] = projectToPlane(view.lat, view.lon, blend);
      const ratio = next / before;
      view.span = next;
      setPlaneCenter(ax + (cx - ax) * ratio, ay + (cy - ay) * ratio);
    } else {
      view.span = next;
      if (point) {
        computePose();
        const moved = latLonToScreen(point.lat, point.lon);
        if (moved.depth > 0) {
          const box = rect();
          dragBetween({ x: moved.x + box.left, y: moved.y + box.top }, anchor);
        }
      }
    }
    markChanged();
  }

  function stopAnimation() {
    if (animation) animation = null;
  }

  function scheduleEnd(delay = 0) {
    if (endTimer) clearTimeout(endTimer);
    const finish = () => {
      endTimer = 0;
      if (drag || pinch || animation) return;
      if (moving) {
        moving = false;
        emit('end');
      }
    };
    if (delay > 0 && typeof setTimeout === 'function') endTimer = setTimeout(finish, delay);
    else finish();
  }

  function beginMove() {
    fitted = false;
    if (endTimer) { clearTimeout(endTimer); endTimer = 0; }
    if (!moving) {
      moving = true;
      emit('start');
    }
  }

  // -- animations ----------------------------------------------------------

  function animateTo(to, { duration = 300, easing = easeOutCubic } = {}) {
    const goal = { lat: to.lat ?? view.lat, lon: wrapLongitude(to.lon ?? view.lon), span: clampSpan(to.span ?? view.span) };
    beginMove();
    if (reducedMotion() || duration <= 0) {
      Object.assign(view, goal);
      clampView();
      markChanged();
      animation = null;
      scheduleEnd();
      return;
    }
    const along = interpolateGreatCircle(view, goal);
    const from = { ...view };
    animation = {
      start: now(), duration, step(t) {
        const f = easing(t);
        const point = along(f);
        view.lat = point.lat;
        view.lon = point.lon;
        view.span = from.span * (goal.span / from.span) ** f;
      },
    };
  }

  function flyTo(to, { maxDuration = 3500 } = {}) {
    const goal = { lat: to.lat ?? view.lat, lon: wrapLongitude(to.lon ?? view.lon), span: clampSpan(to.span ?? view.span) };
    beginMove();
    if (reducedMotion()) {
      Object.assign(view, goal);
      clampView();
      markChanged();
      animation = null;
      scheduleEnd();
      return;
    }
    const { width, height } = viewportSize();
    const aspect = width / height;
    const from = { ...view };
    let path;
    let step;
    if (!flat()) {
      // Globe: u is arc length along the great circle, w the visible width.
      const angle = greatCircleAngle(from, goal);
      const along = interpolateGreatCircle(from, goal);
      path = zoomPath([0, 0, from.span * aspect], [angle, 0, goal.span * aspect]);
      step = (t) => {
        const [u, , w] = path.at(t);
        const point = angle > 1e-9 ? along(u / angle) : goal;
        view.lat = point.lat;
        view.lon = point.lon;
        view.span = w / aspect;
      };
    } else {
      const blend = planeBlend();
      const [x0, y0] = projectToPlane(from.lat, from.lon, blend);
      const [x1, y1] = projectToPlane(goal.lat, goal.lon, blend);
      path = zoomPath(
        [x0, y0, from.span * PLANE_UNITS_PER_RADIAN * aspect],
        [x1, y1, goal.span * PLANE_UNITS_PER_RADIAN * aspect],
      );
      step = (t) => {
        const [x, y, w] = path.at(t);
        setPlaneCenter(x, y);
        view.span = w / (PLANE_UNITS_PER_RADIAN * aspect);
      };
    }
    const duration = clamp((1000 * path.length) / FLY_SPEED, 350, maxDuration);
    animation = {
      start: now(), duration, step(t) { step(easeInOutCubic(t)); },
      finish() { Object.assign(view, goal); },
    };
  }

  function startInertia(vx, vy) {
    // vx, vy: release velocity in px/ms.
    const speed = Math.min(Math.hypot(vx, vy) * 1000 * INERTIA_LINEARITY, INERTIA_MAX_SPEED);
    if (speed < 20 || reducedMotion()) return false;
    const duration = (speed / (INERTIA_DECELERATION * INERTIA_LINEARITY)) * 1000;
    const distance = (speed * duration) / 2000;
    const direction = [vx, vy].map((component) => component / Math.hypot(vx, vy));
    let travelled = 0;
    animation = {
      start: now(), duration, inertia: true, step(t) {
        const along = distance * easeOutCubic(t);
        const delta = along - travelled;
        travelled = along;
        panByPixels(direction[0] * delta, direction[1] * delta);
      },
    };
    return true;
  }

  function smoothZoom(factor, anchor) {
    if (reducedMotion()) {
      beginMove();
      zoomAround(factor, anchor);
      scheduleEnd(200);
      return;
    }
    const pending = animation?.wheel ? animation : null;
    const goalSpan = clampSpan((pending?.goalSpan ?? view.span) * factor);
    beginMove();
    animation = {
      wheel: true, goalSpan, anchor, last: now(), start: now(), duration: Infinity,
      tick(time) {
        const dt = Math.max(0, time - this.last);
        this.last = time;
        const k = 1 - Math.exp(-dt / WHEEL_SMOOTHING_MS);
        const ratio = (this.goalSpan / view.span) ** k;
        zoomAround(ratio, this.anchor);
        return Math.abs(Math.log(this.goalSpan / view.span)) > 1e-3;
      },
      finish() { zoomAround(this.goalSpan / view.span, this.anchor); },
    };
  }

  // Advance animations and push the pose to the camera. Returns true when the
  // camera moved, so the caller knows a new frame is needed.
  function update(time = now()) {
    if (animation) {
      const active = animation;
      let running;
      if (active.tick) {
        running = active.tick(time);
      } else {
        const t = active.duration > 0 ? clamp((time - active.start) / active.duration, 0, 1) : 1;
        active.step(t);
        running = t < 1;
      }
      if (!running && animation === active) {
        active.finish?.();
        animation = null;
        clampView();
        scheduleEnd(active.wheel ? 120 : 0);
      }
      markChanged();
    }
    const { value: m, proj2D } = morph();
    const key = `${m}|${proj2D}`;
    if (key !== lastPoseKey) {
      lastPoseKey = key;
      dirty = true;
    }
    if (!dirty) return false;
    dirty = false;
    applyPose();
    emit('change');
    return true;
  }

  // -- input ----------------------------------------------------------------

  function localPoint(event) {
    return { x: event.clientX, y: event.clientY };
  }

  function onPointerDown(event) {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    element.setPointerCapture?.(event.pointerId);
    pointers.set(event.pointerId, localPoint(event));
    stopAnimation();
    if (pointers.size === 1) {
      drag = { last: localPoint(event), origin: localPoint(event), samples: [], moved: false };
      pinch = null;
    } else if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = { distance: Math.hypot(a.x - b.x, a.y - b.y) || 1, mid: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 } };
      drag = null;
    }
  }

  function onPointerMove(event) {
    if (!pointers.has(event.pointerId)) return;
    const point = localPoint(event);
    pointers.set(event.pointerId, point);
    if (pinch && pointers.size >= 2) {
      const [a, b] = [...pointers.values()];
      const distance = Math.hypot(a.x - b.x, a.y - b.y) || 1;
      const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
      beginMove();
      dragBetween(pinch.mid, mid);
      zoomAround(pinch.distance / distance, mid);
      pinch = { distance, mid };
      return;
    }
    if (!drag) return;
    const time = now();
    if (!drag.moved && Math.hypot(point.x - drag.origin.x, point.y - drag.origin.y) < DRAG_CLICK_TOLERANCE_PX) return;
    if (!drag.moved) {
      drag.moved = true;
      element.classList?.add?.('is-dragging');
      beginMove();
    }
    drag.samples.push({ time, dx: point.x - drag.last.x, dy: point.y - drag.last.y });
    while (drag.samples.length && time - drag.samples[0].time > INERTIA_WINDOW_MS * 3) drag.samples.shift();
    dragBetween(drag.last, point);
    drag.last = point;
  }

  function onPointerUp(event) {
    if (!pointers.has(event.pointerId)) return;
    pointers.delete(event.pointerId);
    element.releasePointerCapture?.(event.pointerId);
    if (pinch) {
      pinch = null;
      if (pointers.size === 1) {
        const [remaining] = pointers.values();
        drag = { last: remaining, origin: remaining, samples: [], moved: true };
      } else {
        scheduleEnd();
      }
      return;
    }
    if (!drag) return;
    const finished = drag;
    drag = null;
    element.classList?.remove?.('is-dragging');
    if (!finished.moved) return;
    // Holding still before letting go leaves no recent samples, so no glide.
    const time = now();
    const recent = finished.samples.filter((sample) => time - sample.time <= INERTIA_WINDOW_MS);
    if (event.type === 'pointerup' && recent.length >= 2) {
      const elapsed = Math.max(16, time - recent[0].time);
      const dx = recent.reduce((sum, sample) => sum + sample.dx, 0);
      const dy = recent.reduce((sum, sample) => sum + sample.dy, 0);
      if (startInertia(dx / elapsed, dy / elapsed)) return;
    }
    scheduleEnd();
  }

  function onWheel(event) {
    event.preventDefault();
    let delta = event.deltaY;
    if (event.deltaMode === 1) delta *= 40;
    else if (event.deltaMode === 2) delta *= 800;
    // A mouse wheel sends large, whole-number steps; trackpads and pinch
    // gestures (ctrlKey in Chromium/Firefox) send many small ones.
    const wheelLike = !event.ctrlKey && Math.abs(delta) >= 50 && Number.isInteger(delta);
    const levels = -delta * (wheelLike ? 1 / 300 : 1 / 100);
    smoothZoom(2 ** -clamp(levels, -2, 2), localPoint(event));
  }

  function onDoubleClick(event) {
    event.preventDefault();
    const factor = event.shiftKey ? 2 : 0.5;
    const anchor = localPoint(event);
    if (reducedMotion()) {
      beginMove();
      zoomAround(factor, anchor);
      scheduleEnd();
      return;
    }
    const goalSpan = clampSpan(view.span * factor);
    const startSpan = view.span;
    beginMove();
    animation = {
      start: now(), duration: 320, step(t) {
        const f = easeOutCubic(t);
        zoomAround((startSpan * (goalSpan / startSpan) ** f) / view.span, anchor);
      },
    };
  }

  function onKeyDown(event) {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
    // MapLibre's KeyboardHandler bindings: arrows pan 100 px (Shift: 300),
    // +/- zoom one level (Shift: two), each eased over 300 ms with t(2 - t).
    const step = event.shiftKey ? 300 : 100;
    const levels = event.shiftKey ? 2 : 1;
    const ease = { duration: KEY_EASE_MS, easing: easeOutQuad };
    // An arrow reveals what lies in its direction (ArrowRight shows the east),
    // which moves the map content the opposite way to a drag.
    const pan = (dx, dy) => {
      const saved = { ...view };
      panByPixels(-dx, -dy);
      const goal = { ...view };
      Object.assign(view, saved);
      animateTo(goal, ease);
    };
    switch (event.key) {
      case 'ArrowLeft': pan(-step, 0); break;
      case 'ArrowRight': pan(step, 0); break;
      case 'ArrowUp': pan(0, -step); break;
      case 'ArrowDown': pan(0, step); break;
      case '+': case '=': animateTo({ span: view.span / 2 ** levels }, ease); break;
      case '-': case '_': animateTo({ span: view.span * 2 ** levels }, ease); break;
      case '0': case 'Home': flyTo(home()); fitted = true; break;
      default: return;
    }
    event.preventDefault();
    event.stopPropagation();
  }

  function attach() {
    if (!element?.addEventListener || typeof AbortController === 'undefined') return;
    abort = new AbortController();
    const options = { signal: abort.signal };
    element.addEventListener('pointerdown', onPointerDown, options);
    element.addEventListener('pointermove', onPointerMove, options);
    element.addEventListener('pointerup', onPointerUp, options);
    element.addEventListener('pointercancel', onPointerUp, options);
    element.addEventListener('lostpointercapture', onPointerUp, options);
    element.addEventListener('wheel', onWheel, { ...options, passive: false });
    element.addEventListener('dblclick', onDoubleClick, options);
    element.addEventListener('keydown', onKeyDown, options);
  }

  // -- public API ------------------------------------------------------------

  function home(forProjection = projection) {
    return { lat: 0, lon: 0, span: fitSpan(forProjection) };
  }

  const api = {
    target,
    get view() { return { ...view }; },
    get projection() { return projection; },
    get pose() { return { ...pose }; },
    addEventListener(type, listener) { listeners[type]?.add(listener); },
    removeEventListener(type, listener) { listeners[type]?.delete(listener); },
    update,
    screenToLatLon,
    latLonToScreen,
    fitSpan,
    home,
    minSpan,
    maxSpan,
    isMoving: () => Boolean(drag?.moved || pinch || animation),
    isDragging: () => Boolean(drag?.moved || pinch),
    setCellCount(count) { cellCount = Number(count) || 0; clampView(); markChanged(); },
    // Keep the place and scale when zoomed in. From a whole-world view, show
    // the new projection's whole world instead (the globe overview is only
    // half the height of a flat map), easing alongside the morph.
    setProjection(next, { animate = true } = {}) {
      const previous = projection;
      const overview = view.span >= fitSpan(previous) * 0.8;
      projection = next === 'equirect' || next === 'mollweide' ? next : 'globe';
      if (animation?.inertia || animation?.wheel) animation = null;
      if (overview && previous !== projection) {
        const goal = projection === 'globe' ? { lat: view.lat, lon: view.lon, span: fitSpan('globe') } : home(projection);
        if (animate) animateTo(goal, { duration: 650, easing: easeInOutCubic });
        else Object.assign(view, goal);
        fitted = true;
      }
      clampView();
      markChanged();
    },
    setView(next = {}, { animate = false } = {}) {
      if (animate) { flyTo(next); return; }
      stopAnimation();
      fitted = Boolean(next.fit);
      if (Number.isFinite(next.lat)) view.lat = next.lat;
      if (Number.isFinite(next.lon)) view.lon = next.lon;
      if (Number.isFinite(next.span) && next.span > 0) view.span = next.span;
      clampView();
      markChanged();
    },
    flyTo,
    easeTo: animateTo,
    zoomBy(factor, { animate = true } = {}) {
      if (animate) animateTo({ span: view.span * factor }, { duration: KEY_EASE_MS, easing: easeOutQuad });
      else { zoomAround(factor); markChanged(); }
    },
    panBy(dx, dy) { panByPixels(dx, dy); },
    reset({ animate = true } = {}) {
      if (animate) { flyTo(home()); fitted = true; } else api.setView({ ...home(), fit: true });
    },
    stop() { stopAnimation(); },
    resize() {
      if (fitted && !drag && !pinch) {
        const goal = projection === 'globe' ? { span: fitSpan('globe') } : home(projection);
        if (animation && !animation.inertia && !animation.wheel) {
          animation.finish?.();
          animation = null;
        }
        Object.assign(view, goal);
      }
      clampView();
      markChanged();
    },
    // Kilometres per CSS pixel along the screen's horizontal through the
    // centre, measured on the planet between two nearby screen points, so it
    // is exact for every projection at the view centre.
    kilometresPerPixel(radiusKm) {
      const box = rect();
      const cx = box.left + box.width / 2;
      const cy = box.top + box.height / 2;
      const half = Math.min(40, box.width / 4);
      const a = screenToLatLon(cx - half, cy);
      const b = screenToLatLon(cx + half, cy);
      if (!a || !b || !(radiusKm > 0)) return null;
      return (greatCircleAngle(a, b) * radiusKm) / (2 * half);
    },
    dispose() {
      abort?.abort();
      abort = null;
      if (endTimer) clearTimeout(endTimer);
      animation = null;
      listeners.change.clear();
      listeners.end.clear();
      listeners.start.clear();
    },
  };
  clampView();
  attach();
  applyPose();
  return api;
}
