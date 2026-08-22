import {
  alignIncidents,
  bannerState,
  formatIso8601Utc,
  globeAltM,
  interpolate,
  parseFlightPath,
  parseIncidents,
  sampleEvent,
} from "/replay/lib/flight.mjs";

const CESIUM_VERSION = "1.125";
const SPEED_VALUES = [0.25, 0.5, 1, 2, 4];
const COLORS = ["#2463b0", "#c45c16", "#2e8c40", "#7a48a8", "#b8941c"];
const UAV_MODEL_URI = "./assets/drone.glb";
const INGEST_PROGRESS = {
  received: 10,
  parsing: 35,
  normalizing: 65,
  detecting: 85,
  ready: 100,
  failed: 100,
};

const params = new URLSearchParams(window.location.search);
const state = {
  token: params.get("token") || sessionStorage.getItem("sdthReplayToken") || "",
  flights: [],
  active: 0,
  datasets: [],
  ingests: {},
  patterns: [],
  bulletins: [],
  viewer: null,
  entities: [],
  clockListener: null,
  uavModelReady: false,
  bannerClosed: false,
  dismissedIncidentId: null,
  orbit: {
    enabled: false,
    heading: 0,
    pitch: -0.55,
    range: 80,
  },
  globeDraw: 0,
};

const els = {
  tokenInput: document.getElementById("tokenInput"),
  statusLine: document.getElementById("statusLine"),
  playState: document.getElementById("playState"),
  flightMeta: document.getElementById("flightMeta"),
  sourceLine: document.getElementById("sourceLine"),
  timeLine: document.getElementById("timeLine"),
  poseLine: document.getElementById("poseLine"),
  eventLine: document.getElementById("eventLine"),
  flightList: document.getElementById("flightList"),
  datasetList: document.getElementById("datasetList"),
  datasetFilter: document.getElementById("datasetFilter"),
  datasetHint: document.getElementById("datasetHint"),
  incidentList: document.getElementById("incidentList"),
  reportText: document.getElementById("reportText"),
  patternList: document.getElementById("patternList"),
  patternHint: document.getElementById("patternHint"),
  bulletinList: document.getElementById("bulletinList"),
  banner: document.getElementById("banner"),
  bannerClose: document.getElementById("bannerClose"),
  bannerTitle: document.getElementById("bannerTitle"),
  bannerMeta: document.getElementById("bannerMeta"),
  bannerDescription: document.getElementById("bannerDescription"),
  failureChip: document.getElementById("failureChip"),
  playButton: document.getElementById("playButton"),
  speeds: document.getElementById("speeds"),
};

function apiBase() {
  return window.location.origin;
}

function headers() {
  const result = {};
  if (state.token) {
    result.Authorization = `Bearer ${state.token}`;
  }
  return result;
}

async function apiGet(path, optional = false) {
  const response = await fetch(`${apiBase()}${path}`, { headers: headers() });
  if (optional && (response.status === 404 || response.status === 401)) {
    return null;
  }
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${path} failed (${response.status}): ${detail}`);
  }
  return response.json();
}

async function apiPost(path, body) {
  const response = await fetch(`${apiBase()}${path}`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${path} failed (${response.status}): ${detail}`);
  }
  return response.json();
}

function setStatus(text) {
  els.statusLine.textContent = text;
}

function saveToken(token) {
  state.token = token.trim();
  if (state.token) {
    sessionStorage.setItem("sdthReplayToken", state.token);
  } else {
    sessionStorage.removeItem("sdthReplayToken");
  }
}

function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function ingestPercent(status) {
  return INGEST_PROGRESS[status] ?? 10;
}

function capitalizeStatus(status) {
  if (!status) {
    return "";
  }
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function incidentKey(banner) {
  if (!banner.failed) {
    return "__ok__";
  }
  const incident = banner.incident;
  return incident?.id || `${incident?.type || "incident"}:${incident?.started_at || ""}`;
}

async function probeUavModel() {
  try {
    const response = await fetch(UAV_MODEL_URI, { method: "HEAD" });
    if (response.ok) {
      state.uavModelReady = true;
      return;
    }
  } catch {
    // HEAD is not always available; fall through to GET.
  }
  try {
    const response = await fetch(UAV_MODEL_URI);
    state.uavModelReady = response.ok;
  } catch {
    state.uavModelReady = false;
  }
}

async function createTerrainProvider() {
  const url =
    "https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer";
  try {
    if (Cesium.ArcGISTiledElevationTerrainProvider?.fromUrl) {
      return await Cesium.ArcGISTiledElevationTerrainProvider.fromUrl(url);
    }
    if (Cesium.ArcGISTiledElevationTerrainProvider) {
      return new Cesium.ArcGISTiledElevationTerrainProvider({ url });
    }
  } catch {
    // Fall through to a smooth ellipsoid if world terrain is blocked.
  }
  return new Cesium.EllipsoidTerrainProvider();
}

async function createViewer() {
  if (window.Cesium?.Ion) {
    window.Cesium.Ion.defaultAccessToken = "";
  }
  const osm = new Cesium.OpenStreetMapImageryProvider({
    url: "https://tile.openstreetmap.org/",
  });
  const terrainProvider = await createTerrainProvider();
  const viewer = new Cesium.Viewer("cesiumContainer", {
    animation: true,
    timeline: true,
    baseLayerPicker: false,
    geocoder: false,
    homeButton: true,
    sceneModePicker: true,
    navigationHelpButton: true,
    fullscreenButton: true,
    vrButton: false,
    terrainProvider,
    baseLayer: new Cesium.ImageryLayer(osm),
    shouldAnimate: false,
  });
  viewer.scene.globe.enableLighting = true;
  viewer.scene.globe.depthTestAgainstTerrain = true;
  viewer.scene.fog.enabled = true;
  viewer.clock.shouldAnimate = false;
  enableInspectCamera(viewer);
  return viewer;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function getUavWorldPosition() {
  const flight = state.flights[state.active];
  if (!flight || !state.viewer) {
    return undefined;
  }
  const uav = state.viewer.entities.getById(`uav-${flight.flight_id}`);
  if (!uav?.position) {
    return undefined;
  }
  return uav.position.getValue(state.viewer.clock.currentTime);
}

function applyOrbitCamera() {
  if (!state.orbit.enabled || !state.viewer) {
    return;
  }
  const target = getUavWorldPosition();
  if (!target) {
    return;
  }
  state.viewer.camera.lookAt(
    target,
    new Cesium.HeadingPitchRange(state.orbit.heading, state.orbit.pitch, state.orbit.range),
  );
}

function setGlobeCollision(controller, enabled) {
  controller.enableCollisionDetection = enabled;
  controller.minimumZoomDistance = enabled ? 2 : 0.5;
}

function setOrbitEnabled(enabled) {
  const viewer = state.viewer;
  const controller = viewer.scene.screenSpaceCameraController;
  state.orbit.enabled = enabled;
  controller.enableRotate = !enabled;
  controller.enableTilt = !enabled;
  controller.enableLook = !enabled;
  setGlobeCollision(controller, false);
  if (!enabled) {
    viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
    return;
  }
  applyOrbitCamera();
}

function startOrbitFromCamera() {
  const viewer = state.viewer;
  const target = getUavWorldPosition();
  if (!viewer || !target) {
    return;
  }
  const range = Cesium.Cartesian3.distance(viewer.camera.positionWC, target);
  state.orbit.heading = viewer.camera.heading;
  state.orbit.pitch = clamp(viewer.camera.pitch, -1.48, 1.48);
  state.orbit.range = clamp(range, 4, 30000);
  setOrbitEnabled(true);
}

function zoomCamera(viewer, relative) {
  if (!relative) {
    return;
  }
  if (state.orbit.enabled) {
    const factor = relative > 0 ? 1 + Math.min(relative, 0.45) : 1 / (1 + Math.min(-relative, 0.45));
    state.orbit.range = clamp(state.orbit.range * factor, 4, 30000);
    if (state.orbit.range >= 28000) {
      setOrbitEnabled(false);
      viewer.camera.zoomOut(viewer.camera.positionCartographic.height * 0.15);
      return;
    }
    applyOrbitCamera();
    return;
  }
  const height = Math.max(viewer.camera.positionCartographic.height, 2);
  const amount = height * Math.min(Math.abs(relative), 0.45);
  if (relative > 0) {
    viewer.camera.zoomOut(amount);
  } else {
    viewer.camera.zoomIn(amount);
    if (viewer.camera.positionCartographic.height < 4000) {
      startOrbitFromCamera();
    }
  }
}

function enableInspectCamera(viewer) {
  const root = document.getElementById("cesiumContainer");
  const controller = viewer.scene.screenSpaceCameraController;
  controller.enableZoom = true;
  controller.enableTilt = true;
  controller.enableRotate = true;
  controller.enableLook = true;
  controller.inertiaZoom = 0.85;
  controller.inertiaSpin = 0.8;
  controller.inertiaTranslate = 0.8;
  controller.maximumZoomDistance = 40_000_000;
  controller.zoomEventTypes = [
    Cesium.CameraEventType.WHEEL,
    Cesium.CameraEventType.PINCH,
    Cesium.CameraEventType.RIGHT_DRAG,
  ];
  setGlobeCollision(controller, false);
  viewer.camera.constrainedAxis = undefined;

  const onGlobe = (event) => {
    const target = event.target;
    return Boolean(root && target instanceof Node && (target === root || root.contains(target)));
  };

  const onWheel = (event) => {
    if (!onGlobe(event)) {
      return;
    }
    if (event.ctrlKey || state.orbit.enabled) {
      event.preventDefault();
      event.stopPropagation();
      const units = event.deltaMode === 1 ? event.deltaY * 0.08 : event.deltaY * 0.0025;
      zoomCamera(viewer, units);
    }
  };

  let lastScale = 1;
  const onGestureStart = (event) => {
    if (!onGlobe(event)) {
      return;
    }
    event.preventDefault();
    lastScale = event.scale || 1;
  };
  const onGestureChange = (event) => {
    if (!onGlobe(event)) {
      return;
    }
    event.preventDefault();
    const scale = event.scale || 1;
    zoomCamera(viewer, lastScale / scale - 1);
    lastScale = scale;
  };
  const onGestureEnd = (event) => {
    if (!onGlobe(event)) {
      return;
    }
    event.preventDefault();
  };

  document.addEventListener("wheel", onWheel, { passive: false, capture: true });
  document.addEventListener("gesturestart", onGestureStart, { passive: false, capture: true });
  document.addEventListener("gesturechange", onGestureChange, { passive: false, capture: true });
  document.addEventListener("gestureend", onGestureEnd, { passive: false, capture: true });

  const handler = new Cesium.ScreenSpaceEventHandler(viewer.canvas);
  let dragging = false;
  handler.setInputAction(() => {
    if (!getUavWorldPosition()) {
      return;
    }
    if (!state.orbit.enabled) {
      startOrbitFromCamera();
    }
    dragging = state.orbit.enabled;
  }, Cesium.ScreenSpaceEventType.LEFT_DOWN);
  handler.setInputAction((movement) => {
    if (!dragging || !state.orbit.enabled) {
      return;
    }
    const dx = movement.endPosition.x - movement.startPosition.x;
    const dy = movement.endPosition.y - movement.startPosition.y;
    state.orbit.heading -= dx * 0.005;
    state.orbit.pitch = clamp(state.orbit.pitch + dy * 0.005, -1.48, 1.48);
    applyOrbitCamera();
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
  handler.setInputAction(() => {
    dragging = false;
  }, Cesium.ScreenSpaceEventType.LEFT_UP);

  if (viewer.homeButton?.viewModel?.command?.beforeExecute) {
    viewer.homeButton.viewModel.command.beforeExecute.addEventListener((event) => {
      event.cancel = true;
      setOrbitEnabled(false);
      const flight = state.flights[state.active];
      const path = flight ? viewer.entities.getById(`path-${flight.flight_id}`) : undefined;
      if (path) {
        viewer.flyTo(path, { duration: 1.0 }).then(() => startOrbitFromCamera());
      }
    });
  }
}

function clearEntities() {
  for (const entity of state.entities) {
    state.viewer.entities.remove(entity);
  }
  state.entities = [];
}

function uavVisual(color) {
  const cesiumColor = Cesium.Color.fromCssColorString(color);
  const marker = {
    point: {
      pixelSize: 14,
      color: cesiumColor,
      outlineColor: Cesium.Color.WHITE,
      outlineWidth: 2,
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
    },
    label: {
      text: "UAV",
      font: "12px sans-serif",
      showBackground: true,
      pixelOffset: new Cesium.Cartesian2(0, -28),
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
    },
  };
  if (!state.uavModelReady) {
    return marker;
  }
  return {
    ...marker,
    model: {
      uri: UAV_MODEL_URI,
      scale: 0.012,
      minimumPixelSize: 64,
      color: cesiumColor,
      colorBlendMode: Cesium.ColorBlendMode.MIX,
      colorBlendAmount: 0.45,
      silhouetteColor: Cesium.Color.WHITE,
      silhouetteSize: 1.5,
    },
  };
}

function attachModelFallback(entity, color) {
  const graphics = entity.model;
  if (!graphics) {
    return;
  }
  const fallback = () => {
    entity.model = undefined;
    entity.point = new Cesium.PointGraphics({
      pixelSize: 16,
      color: Cesium.Color.fromCssColorString(color),
      outlineColor: Cesium.Color.WHITE,
      outlineWidth: 2,
    });
  };
  const promise = graphics.readyPromise;
  if (promise && typeof promise.catch === "function") {
    promise.catch(fallback);
  }
}

async function sampleTerrainHeights(lonLats) {
  if (!lonLats.length) {
    return [];
  }
  const provider = state.viewer.terrainProvider;
  const cartographics = lonLats.map(([lon, lat]) => Cesium.Cartographic.fromDegrees(lon, lat));
  if (!provider || provider instanceof Cesium.EllipsoidTerrainProvider) {
    return cartographics.map(() => 0);
  }
  const heights = [];
  const batchSize = 256;
  for (let index = 0; index < cartographics.length; index += batchSize) {
    const batch = cartographics.slice(index, index + batchSize);
    try {
      const sampled = await Cesium.sampleTerrainMostDetailed(provider, batch);
      for (const point of sampled) {
        heights.push(Number.isFinite(point?.height) ? point.height : 0);
      }
    } catch {
      try {
        const sampled = await Cesium.sampleTerrain(provider, 12, batch);
        for (const point of sampled) {
          heights.push(Number.isFinite(point?.height) ? point.height : 0);
        }
      } catch {
        for (let i = 0; i < batch.length; i += 1) {
          heights.push(0);
        }
      }
    }
  }
  return heights;
}

function flightBounds(flight, pad = 0.002) {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const sample of flight.samples) {
    west = Math.min(west, sample.lon);
    east = Math.max(east, sample.lon);
    south = Math.min(south, sample.lat);
    north = Math.max(north, sample.lat);
  }
  return {
    west: west - pad,
    south: south - pad,
    east: east + pad,
    north: north + pad,
  };
}

async function loadOsmTrees(bounds, limit = 80) {
  const query = `[out:json][timeout:12];node["natural"="tree"](${bounds.south},${bounds.west},${bounds.north},${bounds.east});out ${limit};`;
  const url = `https://overpass-api.de/api/interpreter?data=${encodeURIComponent(query)}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error("OSM tree query failed");
  }
  const body = await response.json();
  const trees = [];
  for (const element of body.elements || []) {
    if (element.type === "node" && Number.isFinite(element.lat) && Number.isFinite(element.lon)) {
      trees.push({ lat: element.lat, lon: element.lon });
    }
    if (trees.length >= limit) {
      break;
    }
  }
  return trees;
}

function addTreeToGlobe(tree, index) {
  const trunk = state.viewer.entities.add({
    id: `tree-trunk-${index}`,
    position: Cesium.Cartesian3.fromDegrees(tree.lon, tree.lat, 2.1),
    heightReference: Cesium.HeightReference.RELATIVE_TO_GROUND,
    cylinder: {
      length: 4.2,
      topRadius: 0.18,
      bottomRadius: 0.32,
      material: Cesium.Color.fromCssColorString("#6b4423"),
    },
  });
  const canopy = state.viewer.entities.add({
    id: `tree-canopy-${index}`,
    position: Cesium.Cartesian3.fromDegrees(tree.lon, tree.lat, 6.4),
    heightReference: Cesium.HeightReference.RELATIVE_TO_GROUND,
    ellipsoid: {
      radii: new Cesium.Cartesian3(3.2, 3.2, 3.6),
      material: Cesium.Color.fromCssColorString("#2f7a3e"),
    },
  });
  return [trunk, canopy];
}

async function addFlightToGlobe(flight, color, track) {
  const start = Cesium.JulianDate.fromIso8601(flight.samples[0].timestamp);
  const stop = Cesium.JulianDate.fromIso8601(flight.samples[flight.samples.length - 1].timestamp);
  if (track) {
    state.viewer.clock.startTime = start;
    state.viewer.clock.stopTime = stop;
    state.viewer.clock.currentTime = Cesium.JulianDate.clone(start);
    state.viewer.clock.clockRange = Cesium.ClockRange.CLAMPED;
    state.viewer.clock.multiplier = state.viewer.clock.multiplier || 1;
    state.viewer.timeline.zoomTo(start, stop);
  }
  const sampled = new Cesium.SampledPositionProperty();
  const positions = [];
  const sampleHeights = await sampleTerrainHeights(
    flight.samples.map((sample) => [sample.lon, sample.lat]),
  );
  for (let index = 0; index < flight.samples.length; index += 1) {
    const sample = flight.samples[index];
    const time = Cesium.JulianDate.fromIso8601(sample.timestamp);
    const position = Cesium.Cartesian3.fromDegrees(
      sample.lon,
      sample.lat,
      globeAltM(flight, sample.alt_m, sampleHeights[index] || 0),
    );
    sampled.addSample(time, position);
    positions.push(position);
  }
  const pathEntity = state.viewer.entities.add({
    id: `path-${flight.flight_id}`,
    polyline: {
      positions,
      width: 3.5,
      material: Cesium.Color.fromCssColorString(color),
    },
  });
  const uav = state.viewer.entities.add({
    id: `uav-${flight.flight_id}`,
    availability: new Cesium.TimeIntervalCollection([
      new Cesium.TimeInterval({
        start,
        stop,
      }),
    ]),
    position: sampled,
    orientation: new Cesium.VelocityOrientationProperty(sampled),
    viewFrom: new Cesium.Cartesian3(-40, -32, 24),
    ...uavVisual(color),
    path: {
      leadTime: 0,
      trailTime: 90,
      width: 3,
      material: Cesium.Color.fromCssColorString(color).withAlpha(0.55),
    },
  });
  attachModelFallback(uav, color);
  const markers = [];
  const locatedIncidents = flight.incidents.filter(
    (incident) => incident.lat != null && incident.lon != null,
  );
  const incidentHeights = await sampleTerrainHeights(
    locatedIncidents.map((incident) => [incident.lon, incident.lat]),
  );
  locatedIncidents.forEach((incident, index) => {
    const marker = state.viewer.entities.add({
      id: `incident-${incident.id || incident.type}-${flight.flight_id}-${index}`,
      position: Cesium.Cartesian3.fromDegrees(
        incident.lon,
        incident.lat,
        globeAltM(flight, incident.alt_m, incidentHeights[index] || 0),
      ),
      point: {
        pixelSize: 14,
        color:
          incident.severity === "critical"
            ? Cesium.Color.RED
            : incident.severity === "warning"
              ? Cesium.Color.ORANGE
              : Cesium.Color.GOLD,
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 2,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
      label: {
        text: `${incident.severity} ${incident.type}`,
        font: "14px sans-serif",
        showBackground: true,
        pixelOffset: new Cesium.Cartesian2(0, -22),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    markers.push(marker);
  });
  const trees = [];
  try {
    const osmTrees = await loadOsmTrees(flightBounds(flight));
    osmTrees.forEach((tree, index) => {
      trees.push(...addTreeToGlobe(tree, index));
    });
  } catch {
    // OSM trees are decorative; a blocked Overpass query should not break replay.
  }
  state.entities.push(pathEntity, uav, ...markers, ...trees);
  if (track) {
    state.viewer.trackedEntity = undefined;
    state.viewer.flyTo(pathEntity, { duration: 1.2 }).then(() => {
      startOrbitFromCamera();
    });
  }
}

function renderFlightList() {
  els.flightList.innerHTML = "";
  state.flights.forEach((flight, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = index === state.active ? "active" : "";
    button.textContent = flight.flight_id;
    button.addEventListener("click", () => {
      state.active = index;
      void showActiveFlight();
    });
    els.flightList.append(button);
  });
}

function renderDatasets() {
  const query = els.datasetFilter.value.trim().toLowerCase();
  els.datasetList.innerHTML = "";
  const visible = state.datasets.filter((item) => {
    const haystack = `${item.path} ${item.name}`.toLowerCase();
    return !query || haystack.includes(query);
  });
  if (!visible.length) {
    els.datasetHint.textContent = state.token
      ? "No matching files in raw_telemetry-datasets."
      : "Enter the API token to list local datasets.";
    return;
  }
  els.datasetHint.textContent = `${visible.length} file(s) available to parse and replay.`;
  for (const item of visible.slice(0, 80)) {
    const ingest = state.ingests[item.path];
    const row = document.createElement("div");
    row.className = ingest?.busy ? "dataset-row busy" : "dataset-row";
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${item.path} (${item.parser_hint})`;
    button.disabled = Boolean(ingest?.busy);
    button.addEventListener("click", () => loadDataset(item.path));
    row.append(button);
    if (ingest) {
      const bar = document.createElement("div");
      bar.className = "progress";
      const fill = document.createElement("span");
      fill.style.width = `${ingest.percent}%`;
      bar.append(fill);
      const label = document.createElement("p");
      label.className = "progress-label";
      label.textContent = ingest.error
        ? ingest.error
        : `${capitalizeStatus(ingest.status)}  ${ingest.percent}%`;
      row.append(bar, label);
    }
    els.datasetList.append(row);
  }
}

function renderHud(flight, pose) {
  const banner = bannerState(flight, pose.time_s);
  const key = incidentKey(banner);
  const hideBanner = state.bannerClosed && state.dismissedIncidentId === key;
  els.banner.className = banner.failed ? "banner fail" : "banner ok";
  els.banner.hidden = hideBanner;
  els.bannerTitle.textContent = banner.title;
  els.bannerMeta.textContent = banner.failed ? `${banner.severity}  ·  ${banner.type}` : "";
  els.bannerDescription.textContent = banner.description;
  els.failureChip.hidden = !banner.failed;
  els.playState.textContent = state.viewer.clock.shouldAnimate ? "PLAYING" : "PAUSED";
  els.playButton.textContent = state.viewer.clock.shouldAnimate ? "Pause" : "Play";
  els.playButton.className = state.viewer.clock.shouldAnimate ? "active" : "";
  els.flightMeta.textContent = `Flight ${state.active + 1}/${state.flights.length}  ${flight.flight_id}`;
  els.sourceLine.textContent = `${flight.source} · ${flight.data_origin}`;
  els.timeLine.textContent = `${formatIso8601Utc(pose.time_s)}   alt ${pose.alt_m.toFixed(1)} m`;
  els.poseLine.textContent = `${pose.lat.toFixed(6)}, ${pose.lon.toFixed(6)}`;
  els.eventLine.textContent = sampleEvent(flight, pose.lower_sample);
  els.incidentList.innerHTML = flight.incidents.length
    ? flight.incidents
        .slice(0, 6)
        .map((item) => `<p>[${item.severity}] ${item.type}<br />${item.summary || ""}</p>`)
        .join("")
    : "<p>No indexed incidents</p>";
  els.reportText.textContent = flight.mission_summary || flight.report_text || "No report yet.";
}

async function showActiveFlight() {
  const flight = state.flights[state.active];
  if (!flight) {
    return;
  }
  const drawId = (state.globeDraw += 1);
  state.bannerClosed = false;
  state.dismissedIncidentId = null;
  clearEntities();
  renderFlightList();
  const pose = interpolate(flight, flight.samples[0].time_s);
  renderHud(flight, pose);
  setStatus("Draping path on terrain...");
  await addFlightToGlobe(flight, COLORS[state.active % COLORS.length], true);
  if (drawId !== state.globeDraw) {
    return;
  }
  setStatus(flight.upload_status || "ready");
}

function attachClock() {
  if (state.clockListener) {
    state.clockListener();
  }
  state.clockListener = state.viewer.clock.onTick.addEventListener((clock) => {
    const flight = state.flights[state.active];
    if (!flight) {
      return;
    }
    const iso = Cesium.JulianDate.toIso8601(clock.currentTime, 0);
    const timeS = Date.parse(iso.endsWith("Z") ? iso : `${iso}Z`) / 1000;
    renderHud(flight, interpolate(flight, timeS));
    applyOrbitCamera();
  });
}

async function hydrateFlight(document, extras = {}) {
  const flight = parseFlightPath(document);
  if (extras.incidents) {
    flight.incidents = parseIncidents(extras.incidents);
  } else if (document.incidents) {
    flight.incidents = parseIncidents(document.incidents);
  }
  if (extras.mission_summary) {
    flight.mission_summary = extras.mission_summary;
  }
  if (extras.report_text) {
    flight.report_text = extras.report_text;
  }
  if (!flight.report_text) {
    flight.report_text = flight.mission_summary;
  }
  alignIncidents(flight);
  return flight;
}

async function loadLiveFlight(flightId) {
  setStatus(`Loading ${flightId}...`);
  const path = await apiGet(`/v1/flights/${flightId}/path`);
  const incidents = await apiGet(`/v1/flights/${flightId}/incidents`, true);
  const report = await apiGet(`/v1/flights/${flightId}/incident-report`, true);
  const flight = await hydrateFlight(path, {
    incidents,
    mission_summary: report?.mission_summary,
    report_text: report?.report || report?.mission_summary,
  });
  flight.upload_status = "ready";
  return flight;
}

async function loadOfflineDemo() {
  const path = await fetch("./assets/demo_path.json").then((response) => response.json());
  const incidents = await fetch("./assets/demo_incidents.json").then((response) => response.json());
  const flight = await hydrateFlight(path, { incidents });
  return [flight];
}

async function refreshFlightsFromApi(selectedIds) {
  const ids = [...selectedIds];
  if (params.get("latest") === "1") {
    const listed = await apiGet("/v1/flights?limit=5");
    if (listed.items?.[0]?.id) {
      ids.push(listed.items[0].id);
    }
  }
  const unique = [...new Set(ids.filter(Boolean))];
  const flights = [];
  for (const flightId of unique) {
    flights.push(await loadLiveFlight(flightId));
  }
  return flights;
}

async function refreshDatasets() {
  if (!state.token) {
    state.datasets = [];
    renderDatasets();
    return;
  }
  try {
    const body = await apiGet("/v1/replay/datasets");
    state.datasets = body.items || [];
    renderDatasets();
  } catch (error) {
    els.datasetHint.textContent = error.message;
  }
}

function renderPatterns() {
  els.patternList.innerHTML = "";
  if (!state.patterns.length) {
    els.patternHint.textContent = state.token
      ? "No signature yet recurs across 2+ flights."
      : "Enter the API token to see fleet-wide patterns.";
    return;
  }
  els.patternHint.textContent = "Signatures recurring across 2+ flights — the fleet-wide payoff.";
  for (const pattern of state.patterns) {
    const row = document.createElement("div");
    row.className = "dataset-row";
    const label = document.createElement("p");
    label.innerHTML = `<strong>[${pattern.max_severity}] ${pattern.incident_type}</strong><br />${pattern.summary || ""}`;
    row.append(label);
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Generate mitigation bulletin";
    button.addEventListener("click", () => createBulletin(pattern.signature, button));
    row.append(button);
    els.patternList.append(row);
  }
}

function renderBulletins() {
  els.bulletinList.innerHTML = "";
  if (!state.bulletins.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "No bulletins generated yet.";
    els.bulletinList.append(empty);
    return;
  }
  for (const bulletin of state.bulletins) {
    const row = document.createElement("div");
    row.className = "dataset-row";
    const review = (bulletin.recommended_review || []).map((item) => `&bull; ${item}`).join("<br />");
    row.innerHTML = `<strong>${bulletin.incident_type}</strong> (${bulletin.flight_count} flights)<br />${bulletin.evidence_summary || ""}<br />${review}`;
    els.bulletinList.append(row);
  }
}

async function createBulletin(signature, button) {
  button.disabled = true;
  button.textContent = "Generating...";
  try {
    await apiPost("/v1/mitigation-bulletins", { signature });
    await refreshBulletins();
  } catch (error) {
    setStatus(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Generate mitigation bulletin";
  }
}

async function refreshPatterns() {
  if (!state.token) {
    state.patterns = [];
    renderPatterns();
    return;
  }
  try {
    const body = await apiGet("/v1/incidents/patterns?min_flights=2");
    state.patterns = body.items || [];
    renderPatterns();
  } catch (error) {
    els.patternHint.textContent = error.message;
  }
}

async function refreshBulletins() {
  if (!state.token) {
    state.bulletins = [];
    renderBulletins();
    return;
  }
  try {
    const body = await apiGet("/v1/mitigation-bulletins");
    state.bulletins = body.items || [];
    renderBulletins();
  } catch {
    // Bulletins are supplementary; a failed fetch just leaves the list empty.
  }
}

function setIngest(path, patch) {
  state.ingests[path] = { ...state.ingests[path], ...patch };
  renderDatasets();
}

async function applyLoadedFlight(flightId) {
  const flight = await loadLiveFlight(flightId);
  const existing = state.flights.findIndex((item) => item.flight_id === flight.flight_id);
  if (existing >= 0) {
    state.flights[existing] = flight;
    state.active = existing;
  } else {
    state.flights.push(flight);
    state.active = state.flights.length - 1;
  }
  setStatus(`Ready: ${flight.flight_id}`);
  await showActiveFlight();
  await refreshPatterns();
  await refreshBulletins();
}

async function pollUpload(path, uploadId) {
  while (true) {
    const status = await apiGet(`/v1/uploads/${uploadId}`);
    setIngest(path, {
      uploadId,
      busy: status.status !== "ready" && status.status !== "failed",
      status: status.status,
      percent: ingestPercent(status.status),
      error: status.error || null,
    });
    setStatus(`${capitalizeStatus(status.status)}: ${path}`);
    if (status.status === "ready") {
      if (!status.flight_id) {
        throw new Error("Ingest finished without a flight id");
      }
      await applyLoadedFlight(status.flight_id);
      return;
    }
    if (status.status === "failed") {
      setStatus(status.error || `Failed to ingest ${path}`);
      return;
    }
    await sleep(400);
  }
}

async function loadDataset(path) {
  setIngest(path, {
    busy: true,
    status: "received",
    percent: ingestPercent("received"),
    error: null,
  });
  setStatus(`Queuing ${path}...`);
  try {
    const result = await apiPost("/v1/replay/datasets/load", { path });
    if (result.status === "ready" && result.flight_id) {
      setIngest(path, {
        busy: false,
        status: "ready",
        percent: ingestPercent("ready"),
        uploadId: result.upload_id,
        error: null,
      });
      await applyLoadedFlight(result.flight_id);
      return;
    }
    await pollUpload(path, result.upload_id);
  } catch (error) {
    setIngest(path, {
      busy: false,
      status: "failed",
      percent: ingestPercent("failed"),
      error: error.message,
    });
    setStatus(error.message);
  }
}

function setPlaying(playing) {
  const viewer = state.viewer;
  const clock = viewer.clock;
  if (playing && Cesium.JulianDate.compare(clock.currentTime, clock.stopTime) >= 0) {
    clock.currentTime = Cesium.JulianDate.clone(clock.startTime);
  }
  clock.shouldAnimate = playing;
  if (viewer.clockViewModel) {
    viewer.clockViewModel.shouldAnimate = playing;
  }
  viewer.trackedEntity = undefined;
  if (playing && !state.orbit.enabled) {
    startOrbitFromCamera();
  }
}

function bindControls() {
  els.tokenInput.value = state.token;
  els.tokenInput.addEventListener("change", async () => {
    saveToken(els.tokenInput.value);
    await bootstrap(false);
  });
  els.datasetFilter.addEventListener("input", renderDatasets);
  els.bannerClose.addEventListener("click", () => {
    const flight = state.flights[state.active];
    if (!flight) {
      els.banner.hidden = true;
      return;
    }
    const iso = Cesium.JulianDate.toIso8601(state.viewer.clock.currentTime, 0);
    const timeS = Date.parse(iso.endsWith("Z") ? iso : `${iso}Z`) / 1000;
    const banner = bannerState(flight, timeS);
    state.bannerClosed = true;
    state.dismissedIncidentId = incidentKey(banner);
    els.banner.hidden = true;
  });
  els.failureChip.addEventListener("click", () => {
    state.bannerClosed = false;
    const flight = state.flights[state.active];
    if (!flight) {
      return;
    }
    const iso = Cesium.JulianDate.toIso8601(state.viewer.clock.currentTime, 0);
    const timeS = Date.parse(iso.endsWith("Z") ? iso : `${iso}Z`) / 1000;
    renderHud(flight, interpolate(flight, timeS));
  });
  els.playButton.addEventListener("click", () => {
    setPlaying(!state.viewer.clock.shouldAnimate);
    const flight = state.flights[state.active];
    if (flight) {
      const iso = Cesium.JulianDate.toIso8601(state.viewer.clock.currentTime, 0);
      const timeS = Date.parse(iso.endsWith("Z") ? iso : `${iso}Z`) / 1000;
      renderHud(flight, interpolate(flight, timeS));
    }
  });
  for (const value of SPEED_VALUES) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${value}x`;
    button.addEventListener("click", () => {
      state.viewer.clock.multiplier = value;
      for (const child of els.speeds.children) {
        child.classList.toggle("active", child === button);
      }
    });
    if (value === 1) {
      button.className = "active";
    }
    els.speeds.append(button);
  }
}

async function bootstrap(create = true) {
  if (create) {
    await probeUavModel();
    state.viewer = await createViewer();
    bindControls();
    attachClock();
  }
  const requested = (params.get("flights") || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  try {
    if (state.token && (requested.length || params.get("latest") === "1")) {
      state.flights = await refreshFlightsFromApi(requested);
    } else if (!state.flights.length) {
      state.flights = await loadOfflineDemo();
    }
    if (state.token) {
      const listed = await apiGet("/v1/flights?limit=20", true);
      if (listed?.items) {
        for (const item of listed.items) {
          if (!state.flights.some((flight) => flight.flight_id === item.id)) {
            try {
              state.flights.push(await loadLiveFlight(item.id));
            } catch {
              // Skip flights that do not yet have a path.
            }
          }
        }
      }
    }
    setStatus(state.flights[0]?.upload_status || "ready");
    await showActiveFlight();
    await refreshDatasets();
    await refreshPatterns();
    await refreshBulletins();
  } catch (error) {
    setStatus(error.message);
    if (!state.flights.length) {
      state.flights = await loadOfflineDemo();
      await showActiveFlight();
    }
  }
}

void bootstrap();
void CESIUM_VERSION;
