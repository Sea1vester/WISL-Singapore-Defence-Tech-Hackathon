// A deliberately small, physical-looking reading of OSM data.  Coordinates
// are never moved or invented: this only gives the supplied footprints a
// tabletop treatment.  Heights are illustrative and intentionally capped so
// the replay route remains easy to read.

const PALETTE = {
  slab: "#123543",
  slabSide: "#0a202b",
  ground: ["#294f4d", "#2d5550", "#315952", "#28514d"],
  seam: "#285361",
  building: ["#176775", "#1b5d70", "#245a6b", "#34616a"],
  stone: ["#6faeaa", "#80b9ae", "#5f9899", "#8baea6"],
  roof: ["#3f9095", "#397d89", "#4b8991", "#597f85"],
  wall: ["#124a5a", "#155667", "#0e3f52", "#1d5966"],
  trim: "#e28b3b",
  road: "#102b38",
  roadStroke: "#4b9d9e",
  water: "#176d83",
  park: "#315f56",
};

const MAX_FEATURES = 400;
const MAX_POINTS = 80;

export function normalizeBounds(bounds) {
  if (!bounds || typeof bounds !== "object") return null;
  const west = Number(bounds.west), south = Number(bounds.south);
  const east = Number(bounds.east), north = Number(bounds.north);
  if (![west, south, east, north].every(Number.isFinite) || east <= west || north <= south) return null;
  if (west < -180 || east > 180 || south < -90 || north > 90) return null;
  return { west, south, east, north };
}

export function ringFromGeometry(geometry, bounds = null) {
  if (!Array.isArray(geometry) || geometry.length < 4 || geometry.length > MAX_POINTS) return null;
  // OSM polygon ways are closed.  Rejecting an open or out-of-table ring is
  // preferable to joining across a clipped gap and inventing a footprint.
  const first = geometry[0], last = geometry.at(-1);
  if (Number(first?.lon) !== Number(last?.lon) || Number(first?.lat) !== Number(last?.lat)) return null;
  const ring = [];
  for (const point of geometry) {
    const lon = Number(point?.lon), lat = Number(point?.lat);
    if (!Number.isFinite(lon) || !Number.isFinite(lat) || lon < -180 || lon > 180 || lat < -90 || lat > 90) return null;
    if (bounds && (lon < bounds.west || lon > bounds.east || lat < bounds.south || lat > bounds.north)) return null;
    const previous = ring[ring.length - 1];
    if (!previous || previous.lon !== lon || previous.lat !== lat) ring.push({ lon, lat });
  }
  if (ring.length > 1 && ring[0].lon === ring.at(-1).lon && ring[0].lat === ring.at(-1).lat) ring.pop();
  return ring.length >= 3 ? ring : null;
}

export function lineFromGeometry(geometry, bounds = null) {
  return lineSegmentsFromGeometry(geometry, bounds)[0] || null;
}

function clipSegment(a, b, bounds) {
  if (!bounds) return [a, b];
  let t0 = 0, t1 = 1;
  const dx = b.lon - a.lon, dy = b.lat - a.lat;
  for (const [p, q] of [[-dx, a.lon - bounds.west], [dx, bounds.east - a.lon], [-dy, a.lat - bounds.south], [dy, bounds.north - a.lat]]) {
    if (p === 0) { if (q < 0) return null; continue; }
    const r = q / p;
    if (p < 0) { if (r > t1) return null; t0 = Math.max(t0, r); }
    else { if (r < t0) return null; t1 = Math.min(t1, r); }
  }
  return [{ lon: a.lon + dx * t0, lat: a.lat + dy * t0 }, { lon: a.lon + dx * t1, lat: a.lat + dy * t1 }];
}

export function lineSegmentsFromGeometry(geometry, bounds = null) {
  if (!Array.isArray(geometry) || geometry.length > MAX_POINTS) return [];
  const line = [];
  for (const point of geometry) {
    const lon = Number(point?.lon), lat = Number(point?.lat);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) return [];
    line.push({ lon, lat });
  }
  const segments = [], current = [];
  for (let i = 1; i < line.length; i += 1) {
    const clipped = clipSegment(line[i - 1], line[i], bounds);
    if (!clipped) { if (current.length > 1) segments.push(current.splice(0)); continue; }
    const junction = line[i - 1];
    const junctionOutside = bounds && (junction.lon < bounds.west || junction.lon > bounds.east || junction.lat < bounds.south || junction.lat > bounds.north);
    if (junctionOutside && current.length > 1) segments.push(current.splice(0));
    const [a, b] = clipped, tail = current.at(-1);
    if (!tail || tail.lon !== a.lon || tail.lat !== a.lat) { if (current.length > 1) segments.push(current.splice(0)); current.push(a); }
    if (current.at(-1).lon !== b.lon || current.at(-1).lat !== b.lat) current.push(b);
  }
  if (current.length > 1) segments.push(current);
  return segments;
}

export function featureKind(tags = {}) {
  if (tags.building && tags.building !== "no") return "building";
  if (tags.highway && tags.highway !== "no") return "road";
  if (tags.historic === "archaeological_site") return "site";
  if (tags.natural === "stone" || tags.historic === "stone") return "stone";
  if (tags.natural === "water" || tags.waterway || tags.water) return "water";
  if (tags.leisure === "park" || tags.landuse === "grass" || tags.landuse === "recreation_ground" || tags.natural === "wood") return "park";
  return null;
}

function numericMetres(value) {
  if (typeof value !== "string" && typeof value !== "number") return null;
  const match = String(value).trim().match(/^([0-9]+(?:\.[0-9]+)?)\s*(m|metres?|ft|feet)?$/i);
  if (!match) return null;
  const n = Number(match[1]);
  return /ft|feet/i.test(match[2] || "") ? n * 0.3048 : n;
}

export function illustrativeBuildingHeight(tags = {}) {
  const explicit = numericMetres(tags.height);
  const levels = Number(tags["building:levels"]);
  const estimated = Number.isFinite(levels) && levels > 0 ? levels * 3.1 : 8;
  // The cap is part of the visual language, rather than a claim about survey data.
  return Math.round(Math.min(24, Math.max(4, explicit ?? estimated)) * 10) / 10;
}

// The values are a readable model scale, not a survey of archaeological remains.
export function illustrativeStoneHeight(tags = {}, id = 0) {
  const stated = numericMetres(tags.height);
  if (stated !== null) return Math.round(Math.min(6, Math.max(3, stated)) * 10) / 10;
  const number = Number.isFinite(Number(id)) ? Math.abs(Number(id)) : 0;
  return 3 + (number % 4);
}

export function elevationHeightAt(elevation, lon, lat) {
  const bounds = normalizeBounds(elevation?.bounds);
  const columns = Math.floor(Number(elevation?.columns));
  const rows = Math.floor(Number(elevation?.rows));
  const heights = elevation?.heights;
  if (!bounds || columns < 2 || rows < 2 || !Array.isArray(heights) || heights.length < columns * rows) return 0;
  const x = Math.max(0, Math.min(columns - 1, (lon - bounds.west) / (bounds.east - bounds.west) * (columns - 1)));
  const y = Math.max(0, Math.min(rows - 1, (lat - bounds.south) / (bounds.north - bounds.south) * (rows - 1)));
  const x0 = Math.floor(x), y0 = Math.floor(y), x1 = Math.min(columns - 1, x0 + 1), y1 = Math.min(rows - 1, y0 + 1);
  const sample = (col, row) => Number(heights[row * columns + col]);
  const a = sample(x0, y0), b = sample(x1, y0), c = sample(x0, y1), d = sample(x1, y1);
  if (![a, b, c, d].every(Number.isFinite)) return 0;
  const fx = x - x0, fy = y - y0;
  return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy;
}

function color(C, value) { return C.Color.fromCssColorString(value); }
function positions(C, points, height) { return points.map((p) => C.Cartesian3.fromDegrees(p.lon, p.lat, Number.isFinite(p.height) ? p.height : height)); }
function instance(C, geometry, css) {
  return new C.GeometryInstance({ geometry, attributes: { color: C.ColorGeometryInstanceAttribute.fromColor(color(C, css)) } });
}

function polygon(C, points, height, extrudedHeight, perPositionHeight = false) {
  return new C.PolygonGeometry({
    polygonHierarchy: new C.PolygonHierarchy(positions(C, points, height)),
    ...(!perPositionHeight ? { height } : {}),
    ...(Number.isFinite(extrudedHeight) ? { extrudedHeight } : {}),
    vertexFormat: C.PerInstanceColorAppearance.VERTEX_FORMAT,
    perPositionHeight,
  });
}

function primitive(C, instances) {
  if (!instances.length) return null;
  return new C.Primitive({
    geometryInstances: instances,
    appearance: new C.PerInstanceColorAppearance({ flat: true, translucent: false, closed: true }),
    asynchronous: true,
    ...(C.ShadowMode ? { shadows: C.ShadowMode.DISABLED } : {}),
  });
}

function roadWidth(tags) {
  const kind = tags.highway;
  if (["motorway", "trunk", "primary"].includes(kind)) return 11;
  if (["secondary", "tertiary"].includes(kind)) return 8;
  return 5.5;
}

function ribbon(C, line, width, getGround, offset, css) {
  const output = [];
  // Sample long mapped segments so the ribbons follow the same relief as the ground.
  line = line.flatMap((a,i)=>{
    if(i===line.length-1) return [a];
    const b=line[i+1], metres=Math.hypot((b.lon-a.lon)*111320*Math.cos(a.lat*Math.PI/180),(b.lat-a.lat)*110540);
    const steps=Math.min(150,Math.max(1,Math.ceil(metres/12)));
    return Array.from({length:steps},(_,j)=>({lon:a.lon+(b.lon-a.lon)*j/steps,lat:a.lat+(b.lat-a.lat)*j/steps}));
  });
  for (let i = 1; i < line.length; i += 1) {
    const a = line[i - 1], b = line[i];
    const midLat = (a.lat + b.lat) / 2 * Math.PI / 180;
    const dx = (b.lon - a.lon) * 111320 * Math.cos(midLat), dy = (b.lat - a.lat) * 110540;
    const length = Math.hypot(dx, dy);
    if (length < 0.01) continue;
    const east = -dy / length * width / 2, north = dx / length * width / 2;
    const corner = (p, side) => ({ lon: p.lon + side * east / (111320 * Math.cos(midLat)), lat: p.lat + side * north / 110540 });
    const ring = [corner(a, 1), corner(b, 1), corner(b, -1), corner(a, -1)];
    const raised = ring.map((p) => ({ ...p, height: getGround(p.lon, p.lat) + offset }));
    output.push(instance(C, polygon(C, raised, 0, undefined, true), css));
  }
  return output;
}

function groundFunction(data, options) {
  if (typeof options.heightAt === "function") return (lon, lat) => Number(options.heightAt(lon, lat)) || 0;
  const elevation = options.elevation || data?.elevation;
  return (lon, lat) => elevationHeightAt(elevation, lon, lat);
}

function terrainTriangles(C, elevation, getGround, renderBounds) {
  const bounds = normalizeBounds(renderBounds) || normalizeBounds(elevation?.bounds);
  const columns = Math.min(48, Math.floor(Number(elevation?.columns)));
  const rows = Math.min(48, Math.floor(Number(elevation?.rows)));
  if (!bounds || columns < 2 || rows < 2 || !Array.isArray(elevation?.heights)) return [];
  const result = [];
  for (let row = 0; row < rows - 1; row += 1) for (let col = 0; col < columns - 1; col += 1) {
    const point = (x, y) => ({ lon: bounds.west + (bounds.east - bounds.west) * x / (columns - 1), lat: bounds.south + (bounds.north - bounds.south) * y / (rows - 1) });
    const a = point(col, row), b = point(col + 1, row), c = point(col + 1, row + 1), d = point(col, row + 1);
    const triangle = (points, tone) => {
      const elevated = points.map((p) => ({ ...p, height: getGround(p.lon, p.lat) - 0.98 }));
      const geometry = new C.PolygonGeometry({ polygonHierarchy: new C.PolygonHierarchy(elevated.map((p) => C.Cartesian3.fromDegrees(p.lon, p.lat, p.height))), perPositionHeight: true, vertexFormat: C.PerInstanceColorAppearance.VERTEX_FORMAT });
      result.push(instance(C, geometry, PALETTE.ground[tone]));
    };
    const low = Math.abs(getGround(a.lon, a.lat) - getGround(c.lon, c.lat));
    triangle([a, b, c], low > 2 ? 0 : 1);
    triangle([a, c, d], low > 2 ? 2 : 1);
  }
  return result;
}

/** Create a removable Cesium primitive collection for an OSM tabletop. */
export function createTabletop(viewer, data, options = {}) {
  const C = options.Cesium || globalThis.Cesium;
  const bounds = normalizeBounds(options.bounds) || normalizeBounds(data?.bounds);
  if (!viewer?.scene?.primitives || !C || !bounds) return inertTabletop();
  const collection = new C.PrimitiveCollection();
  collection.show = options.show !== false;
  viewer.scene.primitives.add(collection);
  const add = (instances) => { const p = primitive(C, instances); if (p) collection.add(p); };
  const ground = groundFunction(data, options);
  const elevation = options.elevation || data?.elevation;

  // A finite resin slab beneath the sampled ground, independent of the globe.
  const slab = [
    { lon: bounds.west, lat: bounds.south }, { lon: bounds.east, lat: bounds.south },
    { lon: bounds.east, lat: bounds.north }, { lon: bounds.west, lat: bounds.north },
  ];
  const elevationHeights = Array.isArray(elevation?.heights) ? elevation.heights.map(Number).filter(Number.isFinite) : [];
  const baseHeight = Number.isFinite(Number(options.baseHeight)) ? Number(options.baseHeight) : (elevationHeights.length ? Math.min(...elevationHeights) - 8 : -9);
  if (elevation?.heights) {
    add(terrainTriangles(C, elevation, ground, bounds));
    // A continuous, opaque resin edge holds the sampled terrain above its finite base.
    const corners = slab;
    const edgeWalls = [];
    for (let i = 0; i < corners.length; i += 1) {
      const a=corners[i], b=corners[(i+1)%corners.length];
      const edge=Array.from({length:33},(_,j)=>({lon:a.lon+(b.lon-a.lon)*j/32,lat:a.lat+(b.lat-a.lat)*j/32}));
      edgeWalls.push(instance(C, new C.WallGeometry({
        positions: positions(C, edge, 0), minimumHeights: edge.map(()=>baseHeight),
        maximumHeights: edge.map((p) => ground(p.lon, p.lat) - 0.98),
        vertexFormat: C.PerInstanceColorAppearance.VERTEX_FORMAT,
      }), i%2 ? '#183b49' : PALETTE.slabSide));
      edgeWalls.push(instance(C, new C.WallGeometry({
        positions:positions(C,edge,0),minimumHeights:edge.map(()=>baseHeight),maximumHeights:edge.map(()=>baseHeight+1.1),
        vertexFormat:C.PerInstanceColorAppearance.VERTEX_FORMAT,
      }), '#42767e'));
    }
    add(edgeWalls);
  }
  else add([instance(C, polygon(C, slab, ground((bounds.west + bounds.east) / 2, (bounds.south + bounds.north) / 2) - 1, baseHeight), PALETTE.slab)]);

  const buildings = [], walls = [], roofs = [], trims = [], roads = [], strokes = [], surfaces = [], seams = [], siteLines = [];
  const centerLon=(bounds.west+bounds.east)/2, centerLat=(bounds.south+bounds.north)/2;
  const distance=element=>Math.min(...(element.geometry||[]).map(p=>(p.lon-centerLon)**2+(p.lat-centerLat)**2));
  const elements = Array.isArray(data?.elements) ? data.elements.filter(element =>
    element.geometry?.some(p=>p.lon>=bounds.west&&p.lon<=bounds.east&&p.lat>=bounds.south&&p.lat<=bounds.north)
  ).sort((a,b)=>distance(a)-distance(b)).slice(0, MAX_FEATURES) : [];
  let buildingIndex = 0;
  for (const element of elements) {
    const tags = element?.tags || {};
    const kind = featureKind(tags);
    if (!kind) continue;
    if (kind === "road") {
      const lines = lineSegmentsFromGeometry(element.geometry, bounds);
      if (!lines.length) continue;
      const width = roadWidth(tags);
      for (const line of lines) {
        roads.push(...ribbon(C, line, width, ground, -0.90, PALETTE.road));
        strokes.push(...ribbon(C, line, Math.min(1.2, width * 0.16), ground, -0.86, tags.highway === "primary" ? PALETTE.trim : PALETTE.roadStroke));
      }
      continue;
    }
    const ring = ringFromGeometry(element.geometry, bounds);
    if (!ring) continue;
    const surfaceRing = ring.map((p) => ({ ...p, height: ground(p.lon, p.lat) - 0.87 }));
    if (kind === "water" || kind === "park" || kind === "site") {
      const geometry = new C.PolygonGeometry({ polygonHierarchy: new C.PolygonHierarchy(surfaceRing.map((p) => C.Cartesian3.fromDegrees(p.lon, p.lat, p.height))), perPositionHeight: true, vertexFormat: C.PerInstanceColorAppearance.VERTEX_FORMAT });
      surfaces.push(instance(C, geometry, kind === "water" ? PALETTE.water : PALETTE.park));
      if (kind === "site") siteLines.push(...ribbon(C, [...ring, ring[0]], 0.45, ground, -0.82, PALETTE.seam));
      continue;
    }
    const height = kind === "stone" ? illustrativeStoneHeight(tags, element.id) : illustrativeBuildingHeight(tags);
    const baseAt = (p) => ground(p.lon, p.lat) - 0.84;
    const base = baseAt(ring[0]);
    const tone = buildingIndex++ % PALETTE.building.length;
    // Roof and each wall are separate, with directional wall tones that read as hand-painted facets.
    const roofRing = ring.map((p) => ({ ...p, height: baseAt(p) + height }));
    buildings.push(instance(C, polygon(C, ring, base, base - 0.18), kind === "stone" ? PALETTE.stone[tone] : PALETTE.building[tone]));
    const roofGeometry = new C.PolygonGeometry({ polygonHierarchy: new C.PolygonHierarchy(roofRing.map((p) => C.Cartesian3.fromDegrees(p.lon, p.lat, p.height))), perPositionHeight: true, vertexFormat: C.PerInstanceColorAppearance.VERTEX_FORMAT });
    roofs.push(instance(C, roofGeometry, kind === "stone" ? PALETTE.stone[(tone + 1) % PALETTE.stone.length] : PALETTE.roof[tone]));
    for (let i = 0; i < ring.length; i += 1) {
      const edge = [ring[i], ring[(i + 1) % ring.length]];
      walls.push(instance(C, new C.WallGeometry({ positions: positions(C, edge, 0), minimumHeights: edge.map(baseAt), maximumHeights: edge.map((p) => baseAt(p) + height), vertexFormat: C.PerInstanceColorAppearance.VERTEX_FORMAT }), kind === "stone" ? PALETTE.stone[(tone + i) % PALETTE.stone.length] : PALETTE.wall[(tone + i) % PALETTE.wall.length]));
    }
    // Sparse orange roof rims provide the only accent, every fourth feature.
    if (kind === "building" && buildingIndex % 4 === 0) {
      const trimLine = [...roofRing, roofRing[0]];
      trims.push(...ribbon(C, trimLine, 0.65, (lon, lat) => ground(lon, lat) + height, -0.79, PALETTE.trim));
    }
  }
  // Grid seams are constrained to the supplied rectangular tabletop, never geography.
  for (let i = 1; i < 5; i += 1) {
    const lon = bounds.west + (bounds.east - bounds.west) * i / 5;
    const lat = bounds.south + (bounds.north - bounds.south) * i / 5;
    const vertical = [{ lon, lat: bounds.south }, { lon, lat: bounds.north }];
    const horizontal = [{ lon: bounds.west, lat }, { lon: bounds.east, lat }];
    seams.push(...ribbon(C, vertical, 0.45, ground, -0.82, PALETTE.seam));
    seams.push(...ribbon(C, horizontal, 0.45, ground, -0.82, PALETTE.seam));
  }
  add(surfaces); add(siteLines); add(roads); add(strokes); add(buildings); add(walls); add(roofs); add(trims); add(seams);

  return {
    get show() { return collection.show; },
    set show(value) { collection.show = Boolean(value); },
    setVisible(value) { collection.show = Boolean(value); },
    destroy() { if (!collection.isDestroyed?.()) viewer.scene.primitives.remove(collection); },
  };
}

function inertTabletop() {
  let visible = false;
  return { get show() { return visible; }, set show(value) { visible = Boolean(value); }, setVisible(value) { visible = Boolean(value); }, destroy() {} };
}
