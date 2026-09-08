import {
  alignIncidents,
  bannerState,
  cameraFrameAt,
  cameraFrameForIncident,
  censusAt,
  formatCensusLine,
  formatIso8601Utc,
  globeAltM,
  interpolate,
  parseCameraFrames,
  parseCensusList,
  parseFlightPath,
  parseIncidents,
  sampleEvent,
} from "/replay/lib/flight.mjs";

const CESIUM_VERSION = "1.125";
const SPEED_VALUES = [0.25, 0.5, 1, 2, 4, 8, 15, 30, 60];
const COLORS = ["#c9a227", "#3ecfc2", "#e06070", "#6a8fff", "#a070e0"];
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
  layers: {
    paths: true,
    incidents: true,
    hazard: true,
  },
  // Entity groups for layer toggling
  layerEntities: {
    paths: [],
    incidents: [],
    hazard: [],
  },
  // Camera follow
  followEntity: null,
  followOffset: new Cesium.Cartesian3(-40, -32, 24),
  followFlightId: null,
  // Multi-flight display
  showAllFlights: false,
  // Unified multi-flight timeline
  unifiedStart: null,
  unifiedStop: null,
  // Timeline scrubber
  scrubbing: false,
  timelineFlightStart: null,
  timelineFlightStop: null,
  // Camera-frame PiP (blob URL cache)
  pipVisualId: null,
  pipRequestId: null,
  pipObjectUrl: null,
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
  censusLine: document.getElementById("censusLine"),
  cameraPip: document.getElementById("cameraPip"),
  cameraPipImg: document.getElementById("cameraPipImg"),
  cameraPipCap: document.getElementById("cameraPipCap"),
  flightList: document.getElementById("flightList"),
  flightLegend: document.getElementById("flightLegend"),
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
  jumpButtons: document.getElementById("jumpButtons"),
  failureChip: document.getElementById("failureChip"),
  playButton: document.getElementById("playButton"),
  speeds: document.getElementById("speeds"),
  scrubber: document.getElementById("timeline-scrubber"),
  scrubberProgress: document.getElementById("timeline-progress"),
  scrubberHead: document.getElementById("timeline-head"),
  scrubberIncidents: document.getElementById("timeline-incidents"),
  timelineTime: document.getElementById("timeline-time"),
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
  const response = fetch(`${apiBase()}${path}`, {
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
  // Dark basemap: use a dark OSM-style approach
  const osm = new Cesium.OpenStreetMapImageryProvider({
    url: "https://tile.openstreetmap.org/",
  });
  const terrainProvider = await createTerrainProvider();
  const viewer = new Cesium.Viewer("cesiumContainer", {
    animation: false,
    timeline: false,
    baseLayerPicker: false,
    geocoder: false,
    homeButton: true,
    sceneModePicker: false,
    navigationHelpButton: true,
    fullscreenButton: true,
    vrButton: false,
    terrainProvider,
    baseLayer: new Cesium.ImageryLayer(osm),
    shouldAnimate: false,
    requestRenderMode: true,
  });
  // Dark space environment
  viewer.scene.skyBox = new Cesium.SkyBox({
    sources: {
      positiveX: "",
      negativeX: "",
      positiveY: "",
      negativeY: "",
      positiveZ: "",
      negativeZ: "",
    },
  });
  viewer.scene.skyAtmosphere = new Cesium.SkyAtmosphere();
  viewer.scene.globe.enableLighting = false;
  viewer.scene.globe.depthTestAgainstTerrain = true;
  viewer.scene.backgroundColor = new Cesium.Color(0.039, 0.039, 0.071, 1.0);
  viewer.scene.fog.enabled = true;
  viewer.scene.fog.density = 0.00015;
  viewer.scene.highDynamicRange = true;
  viewer.clock.shouldAnimate = false;
  enableInspectCamera(viewer);
  return viewer;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function getUavWorldPosition() {
  const flightId = state.followFlightId || (state.flights[state.active]?.flight_id);
  if (!flightId || !state.viewer) {
    return undefined;
  }
  const uav = state.viewer.entities.getById(`uav-${flightId}`);
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
  if (state.viewer.requestRender) {
    state.viewer.requestRender();
  }
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

// ---- Click-to-follow drone (single unified handler) ----

function clearClickHandler() {
  if (state._clickHandler) {
    state._clickHandler.destroy();
    state._clickHandler = null;
  }
}

function setupClickToFollow(viewer) {
  clearClickHandler();
  state._clickHandler = new Cesium.ScreenSpaceEventHandler(viewer.canvas);
  state._clickHandler.setInputAction((click) => {
    const picked = viewer.scene.pick(click.position);
    if (!Cesium.defined(picked) || !picked.id) return;
    const id = picked.id.id || picked.id;
    // Check if clicked entity is a uav entity
    if (id && id.startsWith("uav-")) {
      const flightId = id.replace("uav-", "");
      const flightIdx = state.flights.findIndex((f) => f.flight_id === flightId);
      if (flightIdx >= 0) {
        state.active = flightIdx;
        showActiveFlight();
        // Enable smooth camera follow using Cesium trackedEntity + orbit blend
        const uavEntity = viewer.entities.getById(id);
        if (uavEntity) {
          state.followEntity = uavEntity;
          state.followFlightId = flightId;
          // Use Cesium's built-in trackedEntity for smooth following
          viewer.trackedEntity = uavEntity;
          // Switch to orbit mode after a short delay for smooth transition
          setTimeout(() => {
            if (state.followFlightId === flightId) {
              viewer.trackedEntity = undefined;
              startOrbitFromCamera();
            }
          }, 800);
        }
        return;
      }
    }
    // Incident marker: select flight (if needed) and load nearest camera_frame into PiP
    if (id && id.startsWith("incident-")) {
      for (const flight of state.flights) {
        for (let index = 0; index < flight.incidents.length; index += 1) {
          const incident = flight.incidents[index];
          const key = `incident-${incident.id || incident.type}-${flight.flight_id}-${index}`;
          if (key !== id) {
            continue;
          }
          const flightIdx = state.flights.indexOf(flight);
          if (flightIdx >= 0 && flightIdx !== state.active) {
            state.active = flightIdx;
            showActiveFlight().then(() => seekIncidentAndLoadCamera(flight, incident));
            return;
          }
          seekIncidentAndLoadCamera(flight, incident);
          return;
        }
      }
    }
    // Path markers: select the flight
    if (id && id.startsWith("path-")) {
      const flightIdMatch = id.match(/-(flight-[a-f0-9-]+)$/);
      if (flightIdMatch) {
        const flightId = flightIdMatch[1];
        const flightIdx = state.flights.findIndex((f) => f.flight_id === flightId);
        if (flightIdx >= 0 && flightIdx !== state.active) {
          state.active = flightIdx;
          showActiveFlight();
          return;
        }
      }
    }
    // Click on empty space: unfollow
    if (state.orbit.enabled || state.followEntity) {
      state.followFlightId = null;
      state.followEntity = null;
      viewer.trackedEntity = undefined;
      state.orbit.enabled = false;
    }
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
}

// ---- Incident hover tooltip ----
let _tooltipEl = null;

function getOrCreateTooltip() {
  if (!_tooltipEl) {
    _tooltipEl = document.createElement("div");
    _tooltipEl.className = "incident-tooltip";
    _tooltipEl.style.cssText = `
      position: fixed;
      pointer-events: none;
      background: rgba(15, 15, 20, 0.95);
      border: 1px solid var(--gold);
      color: var(--ink);
      padding: 6px 10px;
      border-radius: 4px;
      font-size: 10px;
      font-family: "SF Mono", "Cascadia Code", "Fira Code", "Consolas", monospace;
      z-index: 1000;
      display: none;
      max-width: 220px;
      box-shadow: 0 0 12px rgba(201, 162, 39, 0.3);
    `;
    document.body.appendChild(_tooltipEl);
  }
  return _tooltipEl;
}

function setupIncidentTooltip(viewer) {
  const tooltip = getOrCreateTooltip();
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.canvas);
  handler.setInputAction((movement) => {
    const picked = viewer.scene.pick(movement.position);
    if (!Cesium.defined(picked) || !picked.id) {
      tooltip.style.display = "none";
      return;
    }
    const id = picked.id.id || picked.id;
    if (id && id.startsWith("incident-")) {
      // Find the matching incident data
      for (const flight of state.flights) {
        const incident = flight.incidents.find((inc) => {
          const key = `incident-${inc.id || inc.type}-${flight.flight_id}-${flight.incidents.indexOf(inc)}`;
          return key === id || id.includes(flight.flight_id);
        });
        if (incident) {
          tooltip.textContent = `[${incident.severity}] ${incident.type}${incident.summary ? " · " + incident.summary : ""}`;
          tooltip.style.display = "block";
          tooltip.style.left = movement.position.x + 16 + "px";
          tooltip.style.top = movement.position.y - 10 + "px";
          return;
        }
      }
    }
    tooltip.style.display = "none";
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
  state._tooltipHandler = handler;
}

function clearTooltip() {
  if (state._tooltipHandler) {
    state._tooltipHandler.destroy();
    state._tooltipHandler = null;
  }
  if (_tooltipEl) {
    _tooltipEl.style.display = "none";
  }
}

function clearEntities() {
  _trailAnimationCancel = true;
  stopHazardAnimations();
  clearClickHandler();
  clearTooltip();
  // Track entities by layer before clearing
  for (const layer of Object.keys(state.layerEntities)) {
    for (const entity of state.layerEntities[layer]) {
      if (entity && state.viewer) {
        state.viewer.entities.remove(entity);
      }
    }
    state.layerEntities[layer] = [];
  }
  state.entities = [];
}

function uavVisual(color) {
  const cesiumColor = Cesium.Color.fromCssColorString(color);
  // Primary glow point
  const primaryGlow = cesiumColor.clone();
  primaryGlow.alpha = 0.9;
  // Outer halo - wider, dimmer
  const haloColor = Cesium.Color.fromCssColorString("#c9a227").clone();
  haloColor.alpha = 0.3;
  return {
    point: {
      pixelSize: 22,
      color: primaryGlow,
      outlineColor: Cesium.Color.fromCssColorString("#c9a227"),
      outlineWidth: 3,
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
      scaleByDistance: new Cesium.NearFarScalar(50, 1.2, 20000, 0.3),
      translucencyByDistance: new Cesium.NearFarScalar(500, 1.0, 20000, 0.5),
    },
    // Secondary outer glow ring
    pointOuter: {
      pixelSize: 40,
      color: haloColor,
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
      scaleByDistance: new Cesium.NearFarScalar(50, 1.5, 20000, 0.2),
      translucencyByDistance: new Cesium.NearFarScalar(500, 0.8, 20000, 0.15),
    },
    label: {
      text: "UAV",
      font: "10px monospace",
      fillColor: Cesium.Color.fromCssColorString("#c9a227"),
      outlineColor: Cesium.Color.BLACK,
      outlineWidth: 2,
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      showBackground: false,
      pixelOffset: new Cesium.Cartesian2(0, -36),
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
      scaleByDistance: new Cesium.NearFarScalar(100, 1.0, 5000, 0.5),
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
      pixelSize: 22,
      color: Cesium.Color.fromCssColorString(color),
      outlineColor: Cesium.Color.fromCssColorString("#c9a227"),
      outlineWidth: 3,
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
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

const UXO_INCIDENT_TYPES = new Set(["mission_incomplete", "last_known_position", "operator_marked_debris"]);

let _hazardAnimations = new Set();

function _animateHazardCircle(hazardCircle, flightRef) {
  const material = hazardCircle.ellipse.material;
  const startTime = performance.now();
  const duration = 3000;
  let cancelled = false;
  _hazardAnimations.add(cancelled);

  function tick() {
    if (cancelled) {
      _hazardAnimations.delete(cancelled);
      return;
    }
    const elapsed = (performance.now() - startTime) % duration;
    const t = elapsed / duration;
    const pulse = 0.45 + 0.55 * (0.5 + 0.5 * Math.sin(t * Math.PI * 2));
    if (material.color) {
      material.color.alpha = pulse * 0.65;
    }
    if (material.outline) {
      const outlineAlpha = 0.5 + 0.5 * pulse;
      material.outlineAlpha = outlineAlpha;
    }
    const refFlight = flightRef || state.flights[state.active];
    if (refFlight) {
      hazardCircle.ellipse.extrudedHeight = globeAltM(
        refFlight,
        hazardCircle.altOffset || 0,
        0,
      ) + pulse * 2;
    }
    if (state.viewer?.requestRender) state.viewer.requestRender();
    const animId = requestAnimationFrame(tick);
    hazardCircle._animFrame = animId;
  }
  const animId = requestAnimationFrame(tick);
  hazardCircle._animFrame = animId;
}

function stopHazardAnimations() {
  for (const entity of state.viewer?.entities.values() || []) {
    if (entity._animFrame != null) {
      cancelAnimationFrame(entity._animFrame);
      entity._animFrame = null;
    }
  }
}

function _makePulsingHazardMaterial() {
  return new Cesium.ColorMaterialProperty(
    new Cesium.Color(0.85, 0.05, 0.05, 0.45),
  );
}

async function addHazardCircles(flight, incidentHeights) {
  const hazards = flight.incidents.filter(
    (incident) =>
      incident.lat != null &&
      incident.lon != null &&
      UXO_INCIDENT_TYPES.has(incident.type),
  );
  if (!hazards.length) return [];
  const circleEntities = [];
  const radiusM = 50;
  for (const hazard of hazards) {
    const alt = globeAltM(flight, hazard.alt_m, incidentHeights[0] || 0);
    const center = Cesium.Cartesian3.fromDegrees(hazard.lon, hazard.lat, alt);
    const circle = state.viewer.entities.add({
      id: `hazard-${hazard.id || hazard.type}-${flight.flight_id}`,
      position: center,
      ellipse: {
        semiMinorAxis: radiusM,
        semiMajorAxis: radiusM,
        height: alt,
        material: _makePulsingHazardMaterial(),
        outline: true,
        outlineColor: Cesium.Color.fromCssColorString("#ff1a1a"),
        outlineWidth: 2,
        extrudedHeight: alt + 1,
      },
      label: {
        text: `UXO hazard zone (${radiusM}m radius)`,
        font: "10px monospace",
        fillColor: Cesium.Color.RED,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        pixelOffset: new Cesium.Cartesian2(0, -radiusM - 10),
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    circleEntities.push(circle);
  }
  for (const circle of circleEntities) {
    _animateHazardCircle(circle, flight);
  }
  return circleEntities;
}

// ---- Trail animation: fade trail behind drone, bright ahead ----

let _trailAnimationCancel = false;

function animateTrailGlow(flightId, viewer) {
  const trailEntity = viewer.entities.getById(`trail-${flightId}`);
  const pathEntity = viewer.entities.getById(`path-${flightId}`);
  if (!trailEntity || !pathEntity) return;
  _trailAnimationCancel = false;

  function tick() {
    if (_trailAnimationCancel || !viewer) return;
    const currentTime = viewer.clock.currentTime;
    const startTime = viewer.clock.startTime;
    const stopTime = viewer.clock.stopTime;
    if (!startTime || !stopTime) return;

    const totalDuration = Cesium.JulianDate.totalSeconds(stopTime) - Cesium.JulianDate.totalSeconds(startTime);
    const currentSeconds = Cesium.JulianDate.totalSeconds(currentTime) - Cesium.JulianDate.totalSeconds(startTime);
    const progress = Math.max(0, Math.min(1, currentSeconds / totalDuration));

    // Fade the full path based on progress (dim ahead of drone)
    const pathAlpha = progress * 0.5;
    const pathColor = Cesium.Color.fromCssColorString(COLORS[state.flights.indexOf(state.flights.find((f) => f.flight_id === flightId))] || COLORS[0]);
    pathEntity.polyline.material = new Cesium.ColorMaterialProperty(
      pathColor.withAlpha(Math.max(0.1, pathAlpha)),
    );

    // Brighten trail entity (shown behind drone)
    const trailAlpha = 0.8 + 0.2 * (1 - progress);
    const trailColor = Cesium.Color.fromCssColorString(COLORS[state.flights.indexOf(state.flights.find((f) => f.flight_id === flightId))] || COLORS[0]);
    trailEntity.polyline.material = new Cesium.ColorMaterialProperty(
      trailColor.withAlpha(trailAlpha),
    );

    if (viewer.requestRender) viewer.requestRender();
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
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
    state.timelineFlightStart = Cesium.JulianDate.clone(start);
    state.timelineFlightStop = Cesium.JulianDate.clone(stop);
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

  // ---- Full path (complete flight trace, dim) ----
  const pathEntity = state.viewer.entities.add({
    id: `path-${flight.flight_id}`,
    polyline: {
      positions,
      width: 2,
      material: new Cesium.ColorMaterialProperty(
        Cesium.Color.fromCssColorString(color).withAlpha(0.35),
      ),
    },
  });
  state.layerEntities.paths.push(pathEntity);

  // ---- Animated glow trail (visible portion ahead of drone) ----
  const trailSampled = new Cesium.SampledPositionProperty();
  const trailTimes = [];
  for (let idx = 0; idx < flight.samples.length; idx += 1) {
    const s = flight.samples[idx];
    const t = Cesium.JulianDate.fromIso8601(s.timestamp);
    trailSampled.addSample(t, positions[idx]);
    trailTimes.push(t);
  }

  const trailEntity = state.viewer.entities.add({
    id: `trail-${flight.flight_id}`,
    availability: new Cesium.TimeIntervalCollection([
      new Cesium.TimeInterval({ start, stop }),
    ]),
    position: trailSampled,
    polyline: {
      width: 3,
      material: new Cesium.ColorMaterialProperty(
        Cesium.Color.fromCssColorString(color).withAlpha(0.85),
      ),
      outlineColor: Cesium.Color.fromCssColorString("#c9a227"),
      outlineWidth: 1,
    },
  });
  state.layerEntities.paths.push(trailEntity);

  // ---- UAV marker with glow ----
  const uav = state.viewer.entities.add({
    id: `uav-${flight.flight_id}`,
    availability: new Cesium.TimeIntervalCollection([
      new Cesium.TimeInterval({ start, stop }),
    ]),
    position: sampled,
    orientation: new Cesium.VelocityOrientationProperty(sampled),
    viewFrom: new Cesium.Cartesian3(-40, -32, 24),
    ...uavVisual(color),
    path: {
      leadTime: 0,
      trailTime: 30,
      width: 3,
      material: new Cesium.ColorMaterialProperty(
        Cesium.Color.fromCssColorString(color).withAlpha(0.6),
      ),
    },
  });
  attachModelFallback(uav, color);

  // ---- Incident markers ----
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
        pixelSize: 12,
        color:
          incident.severity === "critical"
            ? Cesium.Color.fromCssColorString("#dc3545")
            : incident.severity === "warning"
              ? Cesium.Color.fromCssColorString("#c9a227")
              : Cesium.Color.fromCssColorString("#3ecfc2"),
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 2,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        scaleByDistance: new Cesium.NearFarScalar(100, 1.0, 10000, 0.5),
      },
      label: {
        text: `${incident.severity} ${incident.type}`,
        font: "10px monospace",
        fillColor: Cesium.Color.fromCssColorString("#e8e0d0"),
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        pixelOffset: new Cesium.Cartesian2(0, -22),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    markers.push(marker);
    state.layerEntities.incidents.push(marker);
  });

  // ---- Trees ----
  const trees = [];
  try {
    const osmTrees = await loadOsmTrees(flightBounds(flight));
    osmTrees.forEach((tree, index) => {
      trees.push(...addTreeToGlobe(tree, index));
    });
  } catch {
    // OSM trees are decorative; a blocked Overpass query should not break replay.
  }

  // ---- Hazard circles ----
  const hazardCircles = await addHazardCircles(flight, incidentHeights);
  for (const hc of hazardCircles) {
    state.layerEntities.hazard.push(hc);
  }

  state.entities.push(pathEntity, uav, ...markers, ...trees, ...hazardCircles);

  // Start trail glow animation
  animateTrailGlow(flight.flight_id, state.viewer);

  if (track) {
    state.viewer.trackedEntity = undefined;
    state.viewer.flyTo(pathEntity, { duration: 1.2 }).then(() => {
      startOrbitFromCamera();
    });
  }
}

function updateLayerVisibility() {
  for (const [layer, visible] of Object.entries(state.layers)) {
    const entities = state.layerEntities[layer] || [];
    for (const entity of entities) {
      if (entity) {
        entity.show = visible;
      }
    }
  }
  if (state.viewer?.requestRender) state.viewer.requestRender();
}

// ---- Flight legend (color-coded mission list) ----

function renderFlightLegend() {
  els.flightLegend.innerHTML = "";
  if (state.flights.length < 2) return;
  for (let i = 0; i < state.flights.length; i++) {
    const flight = state.flights[i];
    const color = COLORS[i % COLORS.length];
    const row = document.createElement("div");
    row.className = `flight-legend-row${i === state.active ? " active" : ""}`;
    row.innerHTML = `<span class="flight-legend-dot" style="background:${color};color:${color};"></span><span class="flight-legend-label">${flight.flight_id}</span>`;
    row.addEventListener("click", () => {
      state.active = i;
      showActiveFlight();
    });
    els.flightLegend.append(row);
  }
}

function renderFlightList() {
  els.flightList.innerHTML = "";
  state.flights.forEach((flight, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = index === state.active ? "active" : "";
    const color = COLORS[index % COLORS.length];
    button.innerHTML = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px;vertical-align:middle;"></span>${flight.flight_id}`;
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

function renderTimelineTicks(flight) {
  els.scrubberIncidents.innerHTML = "";
  if (!state.timelineFlightStart || !state.timelineFlightStop) return;

  const startTime = Cesium.JulianDate.toDate(state.timelineFlightStart).getTime();
  const stopTime = Cesium.JulianDate.toDate(state.timelineFlightStop).getTime();
  const duration = stopTime - startTime;

  // Incident-based ticks
  const incidents = flight.incidents.filter((inc) => inc.sample_index != null && inc.sample_index >= 0);
  for (const inc of incidents) {
    const flightSample = flight.samples[inc.sample_index];
    if (!flightSample) continue;
    const incTime = Cesium.JulianDate.toDate(
      Cesium.JulianDate.fromIso8601(flightSample.timestamp)
    ).getTime();
    const pct = ((incTime - startTime) / duration) * 100;
    if (pct < 0 || pct > 100) continue;

    const tick = document.createElement("div");
    tick.className = `timeline-tick ${inc.severity === "critical" ? "critical" : "warning"}`;
    tick.style.left = `${pct}%`;
    tick.title = `[${inc.severity}] ${inc.type}`;
    els.scrubberIncidents.appendChild(tick);
  }

  // GPS warning ticks from flight samples
  const seenWarnings = new Set();
  for (let i = 0; i < flight.samples.length; i++) {
    const sample = flight.samples[i];
    if (sample.warning && !seenWarnings.has(sample.warning)) {
      seenWarnings.add(sample.warning);
      const sampleTime = Cesium.JulianDate.toDate(
        Cesium.JulianDate.fromIso8601(sample.timestamp)
      ).getTime();
      const pct = ((sampleTime - startTime) / duration) * 100;
      if (pct < 0 || pct > 100) continue;

      const tick = document.createElement("div");
      tick.className = "timeline-tick gps-warning";
      tick.style.left = `${pct}%`;
      tick.title = `GPS: ${sample.warning}`;
      els.scrubberIncidents.appendChild(tick);
    }
  }
}

function updateTimelineUI() {
  if (!state.timelineFlightStart || !state.timelineFlightStop) return;
  const currentTime = state.viewer.clock.currentTime;
  const startMs = Cesium.JulianDate.toDate(state.timelineFlightStart).getTime();
  const stopMs = Cesium.JulianDate.toDate(state.timelineFlightStop).getTime();
  const currentMs = Cesium.JulianDate.toDate(currentTime).getTime();
  const total = stopMs - startMs;
  const elapsed = Math.max(0, Math.min(total, currentMs - startMs));
  const pct = total > 0 ? (elapsed / total) * 100 : 0;

  els.scrubberProgress.style.width = `${pct}%`;
  els.scrubberHead.style.left = `${pct}%`;

  // Format time
  const totalSeconds = Math.floor(elapsed / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const mins = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  els.timelineTime.textContent =
    `${String(hours).padStart(2, "0")}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function scrubToPercent(pct) {
  if (!state.timelineFlightStart || !state.timelineFlightStop) return;
  const startMs = Cesium.JulianDate.toDate(state.timelineFlightStart).getTime();
  const stopMs = Cesium.JulianDate.toDate(state.timelineFlightStop).getTime();
  const total = stopMs - startMs;
  const targetMs = startMs + (total * pct / 100);
  const targetDate = new Date(targetMs);
  state.viewer.clock.currentTime = Cesium.GregorianDate.toJulianDate(targetDate);
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
  if (els.censusLine) {
    const nearest = censusAt(flight.census || [], pose.time_s);
    els.censusLine.textContent = nearest
      ? formatCensusLine(nearest.cars, nearest.people)
      : formatCensusLine(0, 0);
  }
  updateCameraPip(cameraFrameAt(flight.cameraFrames || [], pose.time_s));
  els.incidentList.innerHTML = "";
  if (!flight.incidents.length) {
    const empty = document.createElement("p");
    empty.textContent = "No indexed incidents";
    els.incidentList.append(empty);
  } else {
    for (const item of flight.incidents.slice(0, 6)) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "incident-jump";
      row.innerHTML = `[${item.severity}] ${item.type}<br />${item.summary || ""}`;
      row.addEventListener("click", () => seekIncidentAndLoadCamera(flight, item));
      els.incidentList.append(row);
    }
  }
  els.reportText.textContent = flight.mission_summary || flight.report_text || "No report yet.";

  // Jump-to buttons for incidents in banner
  if (banner.failed && banner.incident) {
    const jumpContainer = els.jumpButtons;
    if (!jumpContainer.children.length) {
      jumpContainer.hidden = false;
      const btn = document.createElement("button");
      btn.className = "jump-btn";
      btn.textContent = `Jump to [${banner.incident.type}]`;
      btn.addEventListener("click", () => {
        seekIncidentAndLoadCamera(flight, banner.incident);
      });
      jumpContainer.appendChild(btn);
    }
  } else {
    els.jumpButtons.hidden = true;
    els.jumpButtons.innerHTML = "";
  }

  // Render timeline ticks
  renderTimelineTicks(flight);

  // Auto-capture a screenshot the first time each incident becomes visible
  const isoTimestamp = formatIso8601Utc(pose.time_s);
  maybeCaptureIncidentScreenshot(flight, banner, isoTimestamp);
}

async function showActiveFlight() {
  const flight = state.flights[state.active];
  if (!flight) {
    return;
  }
  const drawId = (state.globeDraw += 1);
  state.bannerClosed = false;
  state.dismissedIncidentId = null;
  state.followEntity = null;
  state.followFlightId = null;
  clearEntities();
  renderFlightList();
  renderFlightLegend();
  const pose = interpolate(flight, flight.samples[0].time_s);
  renderHud(flight, pose);
  setStatus("Draping path on terrain...");

  // Compute unified timeline when showing all missions
  if (state.showAllFlights && state.flights.length > 1) {
    let earliestStart = null;
    let latestStop = null;
    for (let i = 0; i < state.flights.length; i++) {
      const f = state.flights[i];
      const s = Cesium.JulianDate.fromIso8601(f.samples[0].timestamp);
      const st = Cesium.JulianDate.fromIso8601(f.samples[f.samples.length - 1].timestamp);
      if (!earliestStart || Cesium.JulianDate.compare(s, earliestStart) < 0) earliestStart = s;
      if (!latestStop || Cesium.JulianDate.compare(st, latestStop) > 0) latestStop = st;
    }
    state.unifiedStart = Cesium.JulianDate.clone(earliestStart);
    state.unifiedStop = Cesium.JulianDate.clone(latestStop);
  }

  // Check if multiple flights should be rendered together
  const showAll = state.showAllFlights && state.flights.length > 1;
  if (showAll) {
    setStatus("Draping all missions on globe...");
    for (let i = 0; i < state.flights.length; i++) {
      const f = state.flights[i];
      await addFlightToGlobe(f, COLORS[i % COLORS.length], i === 0);
    }
    // Apply unified timeline
    if (state.unifiedStart && state.unifiedStop) {
      state.viewer.clock.startTime = Cesium.JulianDate.clone(state.unifiedStart);
      state.viewer.clock.stopTime = Cesium.JulianDate.clone(state.unifiedStop);
      state.viewer.clock.currentTime = Cesium.JulianDate.clone(state.unifiedStart);
      state.timelineFlightStart = Cesium.JulianDate.clone(state.unifiedStart);
      state.timelineFlightStop = Cesium.JulianDate.clone(state.unifiedStop);
    }
  } else {
    state.unifiedStart = null;
    state.unifiedStop = null;
    await addFlightToGlobe(flight, COLORS[state.active % COLORS.length], true);
  }
  if (drawId !== state.globeDraw) {
    return;
  }
  setStatus(flight.upload_status || "ready");
  updateLayerVisibility();
}

// ---------------------------------------------------------------------------
// Visual records: screenshot capture
// ---------------------------------------------------------------------------

const _capturedIncidents = new Set();

async function captureAndUploadScreenshot(flightId, isoTimestamp, incidentId, caption) {
  if (!state.token) return;
  try {
    state.viewer.scene.render();
    const dataUrl = await new Promise((resolve, reject) => {
      state.viewer.scene.canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error("Canvas toBlob returned null"))),
        "image/png",
      );
    });
    const params = new URLSearchParams({
      kind: "cesium_screenshot",
      recorded_at: isoTimestamp,
      source: "replay",
      caption,
      ...(incidentId ? { incident_id: incidentId } : {}),
    });
    await fetch(`${apiBase()}/v1/flights/${flightId}/visuals?${params}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${state.token}` },
      body: (() => {
        const fd = new FormData();
        fd.append("file", dataUrl, "screenshot.png");
        return fd;
      })(),
    });
  } catch {
    // Silent
  }
}

function maybeCaptureIncidentScreenshot(flight, banner, isoTimestamp) {
  if (!banner.failed) return;
  const incidentId = banner.incident?.id || null;
  const dedupeKey = incidentId || `${banner.type}:${isoTimestamp}`;
  if (_capturedIncidents.has(dedupeKey)) return;
  _capturedIncidents.add(dedupeKey);
  const caption = `[${banner.severity}] ${banner.type} at ${isoTimestamp}`;
  requestAnimationFrame(() =>
    captureAndUploadScreenshot(flight.flight_id, isoTimestamp, incidentId, caption),
  );
}

function clearCameraPip() {
  if (!els.cameraPip || !els.cameraPipImg) {
    return;
  }
  els.cameraPip.hidden = true;
  if (state.pipObjectUrl) {
    URL.revokeObjectURL(state.pipObjectUrl);
    state.pipObjectUrl = null;
  }
  state.pipVisualId = null;
  state.pipRequestId = null;
  els.cameraPipImg.removeAttribute("src");
  if (els.cameraPipCap) {
    els.cameraPipCap.textContent = "camera frame";
  }
}

async function updateCameraPip(frame) {
  if (!els.cameraPip || !els.cameraPipImg) {
    return;
  }
  if (!frame) {
    clearCameraPip();
    return;
  }
  els.cameraPip.hidden = false;
  if (els.cameraPipCap) {
    els.cameraPipCap.textContent = frame.caption || formatIso8601Utc(frame.time_s);
  }
  if (state.pipVisualId === frame.id) {
    return;
  }
  const requestedId = frame.id;
  state.pipRequestId = requestedId;
  if (!state.token) {
    if (frame.file_url && !frame.file_url.startsWith("/v1/")) {
      state.pipVisualId = requestedId;
      els.cameraPipImg.src = frame.file_url;
    }
    return;
  }
  try {
    const response = await fetch(`${apiBase()}${frame.file_url}`, { headers: headers() });
    if (!response.ok || state.pipRequestId !== requestedId) {
      return;
    }
    const blob = await response.blob();
    if (state.pipRequestId !== requestedId) {
      return;
    }
    if (state.pipObjectUrl) {
      URL.revokeObjectURL(state.pipObjectUrl);
    }
    state.pipVisualId = requestedId;
    state.pipObjectUrl = URL.createObjectURL(blob);
    els.cameraPipImg.src = state.pipObjectUrl;
  } catch {
    // Leave prior frame visible on transient fetch errors.
  }
}

/** Seek fake clock to incident time and load nearest camera_frame into PiP. */
function seekIncidentAndLoadCamera(flight, incident) {
  if (!flight || !incident || !state.viewer) {
    return;
  }
  let targetIso = incident.started_at;
  if (!targetIso && incident.sample_index != null && flight.samples[incident.sample_index]) {
    targetIso = flight.samples[incident.sample_index].timestamp;
  }
  if (!targetIso) {
    return;
  }
  const targetTime = Cesium.JulianDate.fromIso8601(targetIso);
  state.viewer.clock.currentTime = targetTime;
  const timeS = Date.parse(targetIso.endsWith("Z") ? targetIso : `${targetIso}Z`) / 1000;
  const pose = interpolate(flight, timeS);
  const frame =
    cameraFrameForIncident(flight.cameraFrames || [], incident) ||
    cameraFrameAt(flight.cameraFrames || [], pose.time_s);
  updateCameraPip(frame);
  renderHud(flight, pose);
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
    renderHud(flight, interpolate(flight, getPoseFromClock(clock).time_s));
    updateTimelineUI();
    applyOrbitCamera();
  });
}

function getPoseFromClock(clock) {
  const iso = Cesium.JulianDate.toIso8601(clock.currentTime, 0);
  const timeS = Date.parse(iso.endsWith("Z") ? iso : `${iso}Z`) / 1000;
  return interpolate(state.flights[state.active], timeS);
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
  flight.census = parseCensusList(extras.census || document.census || []);
  flight.cameraFrames = parseCameraFrames(
    extras.camera_frames || document.camera_frames || extras.visuals || document.visuals || [],
  );
  alignIncidents(flight);
  return flight;
}

async function loadLiveFlight(flightId) {
  setStatus(`Loading ${flightId}...`);
  const path = await apiGet(`/v1/flights/${flightId}/path`);
  const incidents = await apiGet(`/v1/flights/${flightId}/incidents`, true);
  const report = await apiGet(`/v1/flights/${flightId}/incident-report`, true);
  const census = await apiGet(`/v1/flights/${flightId}/census`, true);
  const visuals = await apiGet(
    `/v1/flights/${flightId}/visuals?kind=camera_frame&limit=500`,
    true,
  );
  const flight = await hydrateFlight(path, {
    incidents,
    mission_summary: report?.mission_summary,
    report_text: report?.report || report?.mission_summary,
    census,
    camera_frames: visuals,
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

async function refreshFlightsFromApi(requested) {
  const ids = [...requested];
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
    state.bannerClosed = true;
    const iso = Cesium.JulianDate.toIso8601(state.viewer.clock.currentTime, 0);
    const timeS = Date.parse(iso.endsWith("Z") ? iso : `${iso}Z`) / 1000;
    const banner = bannerState(flight, timeS);
    state.dismissedIncidentId = incidentKey(banner);
    els.banner.hidden = true;
  });
  els.failureChip.addEventListener("click", () => {
    state.bannerClosed = false;
    const flight = state.flights[state.active];
    if (!flight) {
      return;
    }
    els.jumpButtons.innerHTML = "";
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

  // ---- Layer toggles ----
  document.querySelectorAll(".layer-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const layer = btn.dataset.layer;
      // Multi-flight toggle
      if (btn.id === "multiFlightToggle") {
        state.showAllFlights = btn.classList.toggle("active");
        void showActiveFlight();
        return;
      }
      if (layer && state.layers[layer] !== undefined) {
        state.layers[layer] = !state.layers[layer];
        btn.classList.toggle("active", state.layers[layer]);
        updateLayerVisibility();
      }
    });
  });

  // ---- Timeline scrubber ----
  function handleScrub(clientX) {
    const rect = els.scrubber.getBoundingClientRect();
    const pct = clamp((clientX - rect.left) / rect.width, 0, 1) * 100;
    scrubToPercent(pct);
    updateTimelineUI();
  }

  els.scrubber.addEventListener("mousedown", (e) => {
    state.scrubbing = true;
    handleScrub(e.clientX);
  });
  document.addEventListener("mousemove", (e) => {
    if (state.scrubbing) {
      handleScrub(e.clientX);
    }
  });
  document.addEventListener("mouseup", () => {
    state.scrubbing = false;
  });

  // Touch support for scrubber
  els.scrubber.addEventListener("touchstart", (e) => {
    state.scrubbing = true;
    handleScrub(e.touches[0].clientX);
  }, { passive: true });
  document.addEventListener("touchmove", (e) => {
    if (state.scrubbing) {
      handleScrub(e.touches[0].clientX);
    }
  }, { passive: true });
  document.addEventListener("touchend", () => {
    state.scrubbing = false;
  });
}

async function bootstrap(create = true) {
  if (create) {
    await probeUavModel();
    state.viewer = await createViewer();
    bindControls();
    attachClock();
    setupClickToFollow(state.viewer);
    setupIncidentTooltip(state.viewer);
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
