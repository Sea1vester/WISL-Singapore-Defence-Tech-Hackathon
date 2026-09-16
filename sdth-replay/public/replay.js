window.addEventListener('error', event => console.error('Replay diagnostic', event.error?.stack || event.message));
import { createStreamingTabletop } from './tabletop-stream.mjs?v=stream-3';
import { loadTabletopAtlas, routeContext, atlasHeight, tabletopBounds, createCachedTerrain, createTabletopFinish } from './tabletop-context.mjs?v=stream-4';
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
  replayTimeForPlay,
  replayTimeAtPercent,
  replayTimeForTimestamp,
  sampleEvent,
} from "/replay/lib/flight.mjs?v=stream-3";

const CESIUM_VERSION = "1.125";
const SPEED_VALUES = [0.5, 1, 2, 4, 8, 12];
const DEFAULT_PLAYBACK_SPEED = 12;
const COLORS = ["#4fd8c4", "#e0a95c", "#e0707a", "#7ea0d8", "#a58cd8"];
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
if (params.get("embed") === "1") {
  document.documentElement.classList.add("replay-embed");
  document.body.classList.add("replay-embed");
}
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
  // True while a manual camera-glide animation (see flyOrbitCameraFrom) owns
  // the camera -- the per-tick orbit-follow in applyOrbitCamera() must not
  // fight it by snapping straight to the destination on the very next frame.
  cameraJumpAnimating: false,
  globeDraw: 0,
  layers: {
    paths: true,
    incidents: true,
    hazard: true,
  },
  // Entity groups for layer toggling. `uav` isn't a real toggleable layer
  // (there's no "Aircraft" button, and it should stay visible even when the
  // "Paths" line is hidden) -- it's tracked here purely so clearEntities()'s
  // generic sweep also removes it before a redraw. Without this, re-drawing
  // the same flight (switching away and back, or toggling "All Missions"
  // more than once in one page session) tried to add a second entity with
  // the same `uav-<flight_id>` id, which Cesium rejects -- an uncaught
  // DeveloperError that surfaced as an unrelated-looking exception wherever
  // the enclosing async function's next await happened to be.
  layerEntities: {
    paths: [],
    incidents: [],
    hazard: [],
    uav: [],
    // Same issue as uav: OSM tree entities use plain numeric ids
    // (tree-trunk-0, tree-canopy-0, ...) with no per-flight/per-draw
    // namespacing, and were never removed on redraw either -- so this was
    // actually the *more* reproducible half of the bug, since it fires on
    // almost any flight switch where both the old and new flight have trees
    // near their bounds, not just re-selecting the exact same flight.
    trees: [],
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
  // Both modes open on the 3D tabletop terrain. The standalone viewer used to
  // default to the flat satellite map (mapVisible: embed !== "1") while also
  // hiding the Tabletop/Map toggle outside embed mode -- so anyone opening
  // /replay/ directly got the flat globe with no visible way to reach the 3D
  // view at all. Where a region has no cached terrain, setPresentationMode
  // still falls back to the globe on its own.
  mapVisible: false,
  routeOverview: null,
  atlas: [],
  tabletop: null,
  tabletopFinish: null,
  mapContext: null,
  terrainProgress: null,
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
  severityLegend: document.getElementById("severityLegend"),
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
  resetButton: document.getElementById("resetButton"),
  speeds: document.getElementById("speeds"),
  scrubber: document.getElementById("timeline-scrubber"),
  scrubberProgress: document.getElementById("timeline-progress"),
  scrubberHead: document.getElementById("timeline-head"),
  scrubberIncidents: document.getElementById("timeline-incidents"),
  timelineTime: document.getElementById("timeline-time"),
  transportTelemetry: document.getElementById("transportTelemetry"),
  transportStatus: document.getElementById("transportStatus"),
  orbitalAltitude: document.getElementById("orbitalAltitude"),
  orbitalSpeed: document.getElementById("orbitalSpeed"),
  orbitalBattery: document.getElementById("orbitalBattery"),
  orbitalRecordedTime: document.getElementById("orbitalRecordedTime"),
  routeOverviewPath: document.getElementById("routeOverviewPath"),
  routeOverviewStart: document.getElementById("routeOverviewStart"),
  routeOverviewCurrent: document.getElementById("routeOverviewCurrent"),
  routeOverviewProgress: document.getElementById("routeOverviewProgress"),
  routeOverviewAltPath: document.getElementById("routeOverviewAltPath"),
  routeOverviewAltCurrent: document.getElementById("routeOverviewAltCurrent"),
  routeOverviewAltRange: document.getElementById("routeOverviewAltRange"),
  studioViewButton: document.getElementById("studioViewButton"),
  mapViewButton: document.getElementById("mapViewButton"),
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

async function apiError(path, response) {
  const raw = await response.text().catch(() => "");
  let detail = raw;
  try {
    const parsed = JSON.parse(raw);
    detail = parsed.detail || parsed.message || raw;
  } catch {
    // Not JSON -- keep the raw text.
  }
  const error = new Error(`${path} failed (${response.status}): ${raw}`);
  error.status = response.status;
  error.detail = detail;
  return error;
}

async function apiGet(path, optional = false) {
  const response = await fetch(`${apiBase()}${path}`, { headers: headers() });
  if (optional && (response.status === 404 || response.status === 401)) {
    return null;
  }
  if (!response.ok) {
    throw await apiError(path, response);
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
    throw await apiError(path, response);
  }
  return response.json();
}

// Turns a raw thrown error (often "/v1/path failed (500): {\"detail\":\"...\"}")
// into a calm, plain-language sentence a first-time operator can read, while
// still surfacing the real detail when the backend supplied one.
function friendlyError(error) {
  if (!error) {
    return "Something didn't work. Please try again.";
  }
  const status = error.status;
  const detail = String(error.detail ?? error.message ?? "").trim();
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return "You appear to be offline. Check your connection and try again.";
  }
  if (/failed to fetch|networkerror|load failed/i.test(detail) || /failed to fetch|networkerror/i.test(error.message || "")) {
    return "Could not reach the platform. Check that the local service is running.";
  }
  if (status === 401 || status === 403) {
    return "Your session key wasn't accepted. Reconnect with a valid key.";
  }
  if (status === 404) {
    return detail && !/^\/v1\//.test(detail) ? detail : "That record could not be found.";
  }
  if (typeof status === "number" && status >= 500) {
    return detail ? `The platform ran into a problem: ${detail}` : "The platform ran into a problem processing that. Try again in a moment.";
  }
  if (!detail) {
    return "Something didn't work. Please try again.";
  }
  return /^https?:\/\/|^\/v1\//.test(detail) ? "Something didn't work. Please try again." : detail;
}

function setStatus(text, isError = false) {
  els.statusLine.textContent = text;
  els.transportStatus.textContent = text;
  els.statusLine.classList.toggle("error", isError);
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

function escapeAttr(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
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
  if (state.atlas.length) return createCachedTerrain(Cesium, state.atlas);
  // The embedded review stage must be immediately useful on an isolated
  // network. The ellipsoid keeps the real WGS84 path and camera while avoiding
  // an unbounded third-party terrain handshake.
  if (params.get("embed") === "1") {
    return new Cesium.EllipsoidTerrainProvider();
  }
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
  // OSM is a proven no-key source in this local console. Tone the imagery at
  // the layer level so labels remain readable under the route.
  const baseMap = new Cesium.OpenStreetMapImageryProvider({
    url: "https://tile.openstreetmap.org/",
  });
  const terrainProvider = new Cesium.EllipsoidTerrainProvider();
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
    baseLayer: new Cesium.ImageryLayer(baseMap, {
      brightness: 0.42,
      contrast: 1.18,
      saturation: 0.18,
      gamma: 0.82,
    }),
    shouldAnimate: false,
    shadows: false,
    terrainShadows: Cesium.ShadowMode.DISABLED,
    // Recorded aircraft must progress without a user gesture. Cesium only
    // ticks its Clock while rendering; a demand-rendered scene can stop after
    // one frame even when shouldAnimate is true.
    requestRenderMode: false,
    targetFrameRate: 30,
  });
  // Dark space environment. This previously built a Cesium.SkyBox with an
  // empty string as the image source for all six cube faces -- Cesium tries
  // to actually fetch/decode those, an empty URL resolves to this HTML
  // document, and decoding that as an image is exactly what threw
  // "InvalidStateError: source image could not be decoded" and halted
  // rendering before the base imagery layer ever loaded. Disabling the
  // skybox outright gets the same dark-space look from backgroundColor
  // below, without a broken image load.
  viewer.scene.skyBox = undefined;
  viewer.scene.skyAtmosphere = undefined;
  viewer.scene.globe.showGroundAtmosphere = false;
  viewer.scene.globe.enableLighting = false;
  viewer.shadows = false;
  viewer.scene.shadowMap.enabled = false;
  viewer.scene.globe.depthTestAgainstTerrain = true;
  viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#061925");
  viewer.scene.fog.enabled = true;
  viewer.scene.fog.density = 0.00015;
  viewer.scene.highDynamicRange = false;
  viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#194452");
  const imageryLayer = viewer.imageryLayers.get(0);
  if (imageryLayer) {
    imageryLayer.brightness = 0.26;
    imageryLayer.contrast = 1.2;
    imageryLayer.saturation = 0.04;
    imageryLayer.gamma = 0.78;
    imageryLayer.hue = 4.2;
    imageryLayer.alpha = 0.7;
    imageryLayer.show = state.mapVisible;
  }
  // This is a Viewer property (rather than a reliable constructor setting in
  // every bundled Cesium build). Recorded paths may advance while imagery and
  // optional visuals are still loading.
  viewer.allowDataSourcesToSuspendAnimation = false;
  viewer.clock.shouldAnimate = false;
  viewer.clock.canAnimate = true;
  viewer.clock.clockStep = Cesium.ClockStep.SYSTEM_CLOCK_MULTIPLIER;
  state.tabletopFinish = createTabletopFinish(viewer, Cesium);
  state.tabletopFinish.enabled = !state.mapVisible;
  viewer.cesiumWidget.creditDisplay.addStaticCredit(new Cesium.Credit(
    '<a href="https://www.openstreetmap.org/copyright" target="_blank">© OpenStreetMap</a> · <a href="https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer" target="_blank">Esri terrain</a>', true));
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
  if (!state.orbit.enabled || !state.viewer || state.cameraJumpAnimating) {
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

function easeInOutQuad(t) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

// Glide the orbit camera from where it was looking to where the aircraft now
// is, instead of snapping there in a single frame. Used when jumping straight
// to an incident's timestamp (seekIncidentAndLoadCamera) -- the underlying
// clock/telemetry/HUD update instantly (that data must be correct right away),
// but a visible camera teleport across a possibly-distant point in the flight
// reads as disorienting. The glide is purely visual and never delays anything
// else from updating.
function flyOrbitCameraFrom(previousTarget, durationMs = 450) {
  const viewer = state.viewer;
  if (!viewer || !state.orbit.enabled || !previousTarget) {
    applyOrbitCamera();
    return;
  }
  const newTarget = getUavWorldPosition();
  if (!newTarget) {
    applyOrbitCamera();
    return;
  }
  // A short hop (e.g. re-triggering the same incident) isn't worth animating.
  if (Cesium.Cartesian3.distance(previousTarget, newTarget) < 5) {
    applyOrbitCamera();
    return;
  }
  const heading = state.orbit.heading;
  const pitch = state.orbit.pitch;
  const range = state.orbit.range;
  const startedAt = performance.now();
  state.cameraJumpAnimating = true;
  const token = (state.cameraJumpToken = (state.cameraJumpToken || 0) + 1);
  const scratch = new Cesium.Cartesian3();
  const step = (now) => {
    if (token !== state.cameraJumpToken) return; // superseded by a newer jump
    const t = Math.min(1, (now - startedAt) / durationMs);
    const eased = easeInOutQuad(t);
    Cesium.Cartesian3.lerp(previousTarget, newTarget, eased, scratch);
    viewer.camera.lookAt(scratch, new Cesium.HeadingPitchRange(heading, pitch, range));
    viewer.scene.requestRender();
    if (t < 1) {
      requestAnimationFrame(step);
    } else {
      state.cameraJumpAnimating = false;
    }
  };
  requestAnimationFrame(step);
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
  state.orbit.pitch = params.get("embed") === "1" ? clamp(viewer.camera.pitch, -1.25, -0.30) : clamp(viewer.camera.pitch, -1.48, 1.48);
  state.orbit.range = params.get("embed") === "1" ? clamp(range, 210, 650) : clamp(range, 4, 30000);
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
      background: rgba(10, 14, 22, 0.96);
      border: 1px solid var(--line);
      color: var(--ink);
      padding: 8px 12px;
      border-radius: var(--radius-sm, 9px);
      box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35);
      font-size: 11px;
      line-height: 1.45;
      font-family: var(--font-body, ui-sans-serif, sans-serif);
      z-index: 1000;
      display: none;
      max-width: 240px;
    `;
    document.body.appendChild(_tooltipEl);
  }
  return _tooltipEl;
}

const SEVERITY_TOOLTIP_COLOR = { critical: "var(--danger)", warning: "var(--warn)" };

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
          tooltip.replaceChildren();
          const severity = String(incident.severity || "notice");
          const label = document.createElement("strong");
          label.textContent = severity.charAt(0).toUpperCase() + severity.slice(1);
          label.style.color = SEVERITY_TOOLTIP_COLOR[severity] || "var(--signal)";
          tooltip.append(label, document.createTextNode(` · ${String(incident.type || "").replaceAll("_", " ")}`));
          if (incident.summary) {
            tooltip.append(document.createElement("br"));
            tooltip.append(document.createTextNode(incident.summary));
          }
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
  const primary = cesiumColor.clone();
  primary.alpha = 0.9;
  // Note: this previously also spread a `pointOuter` property meant as a second,
  // wider glow ring. Cesium's Entity only renders recognized graphics types
  // (point, label, billboard, ...) -- "pointOuter" isn't one, so it was stored on
  // the entity but never rendered. Removed as dead weight, not a behavior change.
  return {
    ...(state.uavModelReady
      ? {
          model: {
            uri: UAV_MODEL_URI,
            minimumPixelSize: params.get("embed") === "1" ? 28 : 24,
            maximumScale: 24,
            color: Cesium.Color.fromCssColorString("#fff1dc"),
            colorBlendMode: Cesium.ColorBlendMode.MIX,
            colorBlendAmount: 0.18,
          },
        }
      : {}),
    point: {
      show: !state.uavModelReady,
      pixelSize: 20,
      color: primary,
      outlineColor: Cesium.Color.fromCssColorString("#e9edf5").withAlpha(0.7),
      outlineWidth: 1.5,
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
      scaleByDistance: new Cesium.NearFarScalar(50, 1.35, 20000, 0.55),
      translucencyByDistance: new Cesium.NearFarScalar(500, 1.0, 20000, 0.5),
    },
    label: {
      text: "RECORDED AIRCRAFT",
      font: "600 11px monospace",
      // Color-matched to this flight's own path/marker/legend swatch. Every
      // aircraft used to show the exact same white label text regardless of
      // which flight it belonged to -- in "All Missions" mode, with several
      // drones on screen at once, that left no way to tell them apart short
      // of spatial guessing. Now the label reads the same color as the
      // flight's row in the sidebar legend.
      fillColor: cesiumColor,
      outlineColor: Cesium.Color.BLACK,
      outlineWidth: 3,
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      showBackground: false,
      pixelOffset: new Cesium.Cartesian2(0, params.get("embed") === "1" ? -24 : -24),
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
      pixelSize: 16,
      color: Cesium.Color.fromCssColorString(color),
      outlineColor: Cesium.Color.fromCssColorString("#e9edf5").withAlpha(0.7),
      outlineWidth: 1.5,
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
  if (state.atlas.length) return lonLats.map(([lon, lat]) => atlasHeight(state.atlas, lon, lat));
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
  // Cesium's EntityCollection exposes `values` as an array property, not a
  // method -- calling it as `.values()` throws, which was aborting
  // clearEntities() (and therefore the whole flight-load path) before the
  // globe ever rendered.
  for (const entity of state.viewer?.entities.values || []) {
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
        outlineColor: Cesium.Color.fromCssColorString("#e8564f"),
        outlineWidth: 1.5,
        extrudedHeight: alt + 1,
      },
      label: {
        text: `UXO hazard zone (${radiusM}m radius)`,
        font: "10px monospace",
        fillColor: Cesium.Color.fromCssColorString("#e8564f"),
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 1.5,
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

    // Cesium.JulianDate has no `totalSeconds` static -- secondsDifference(a, b) is
    // the real API for "a minus b, in seconds".
    const totalDuration = Cesium.JulianDate.secondsDifference(stopTime, startTime);
    const currentSeconds = Cesium.JulianDate.secondsDifference(currentTime, startTime);
    const progress = Math.max(0, Math.min(1, currentSeconds / totalDuration));

    // Fade the full path based on progress (dim ahead of drone)
    const pathAlpha = progress * 0.5;
    const pathColor = Cesium.Color.fromCssColorString(
      params.get("embed") === "1"
        ? "#ff9d4d"
        : COLORS[state.flights.indexOf(state.flights.find((f) => f.flight_id === flightId))] || COLORS[0],
    );
    // A dark casing keeps the line identifiable against any terrain tint it
    // crosses (measured contrast against the tabletop's water tile was only
    // ~2.9:1 for the bare fill color -- below the 3:1 floor for a graphical
    // element -- since the casing is darker than every terrain tone in the
    // palette, it restores a safe margin everywhere, not just over water).
    pathEntity.polyline.material = new Cesium.PolylineOutlineMaterialProperty({
      color: pathColor.withAlpha(Math.max(0.1, pathAlpha)),
      outlineColor: Cesium.Color.fromCssColorString("#0a141c").withAlpha(Math.max(0.35, pathAlpha)),
      outlineWidth: 1,
    });

    // Brighten trail entity (shown behind drone)
    const trailAlpha = 0.8 + 0.2 * (1 - progress);
    const trailColor = Cesium.Color.fromCssColorString(
      params.get("embed") === "1"
        ? "#ff9d4d"
        : COLORS[state.flights.indexOf(state.flights.find((f) => f.flight_id === flightId))] || COLORS[0],
    );
    trailEntity.polyline.material = new Cesium.PolylineOutlineMaterialProperty({
      color: trailColor.withAlpha(trailAlpha),
      outlineColor: Cesium.Color.fromCssColorString("#0a141c").withAlpha(0.6),
      outlineWidth: 1,
    });

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
  const visualColor = params.get("embed") === "1" ? "#ff9d4d" : color;
  const start = Cesium.JulianDate.fromIso8601(flight.samples[0].timestamp);
  const stop = Cesium.JulianDate.fromIso8601(flight.samples[flight.samples.length - 1].timestamp);
  if (track) {
    state.viewer.clock.startTime = start;
    state.viewer.clock.stopTime = stop;
    state.viewer.clock.currentTime = Cesium.JulianDate.clone(start);
    state.viewer.clock.clockRange = Cesium.ClockRange.CLAMPED;
    state.viewer.clock.multiplier = DEFAULT_PLAYBACK_SPEED;
    state.timelineFlightStart = Cesium.JulianDate.clone(start);
    state.timelineFlightStop = Cesium.JulianDate.clone(stop);
  }
  const sampled = new Cesium.SampledPositionProperty();
  const orientations = new Cesium.SampledProperty(Cesium.Quaternion);
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
    const heading = Cesium.Math.toRadians(Number.isFinite(sample.yaw_deg) ? sample.yaw_deg : 0);
    const pitch = Cesium.Math.toRadians(Number.isFinite(sample.pitch_deg) ? sample.pitch_deg : 0);
    const roll = Cesium.Math.toRadians(Number.isFinite(sample.roll_deg) ? sample.roll_deg : 0);
    orientations.addSample(
      time,
      Cesium.Transforms.headingPitchRollQuaternion(
        position,
        new Cesium.HeadingPitchRoll(heading, pitch, roll),
      ),
    );
    positions.push(position);
  }

  // ---- Full path (complete flight trace, dim) ----
  // A dark casing (PolylineOutlineMaterialProperty, not the plain-color fill
  // alone) keeps the line legible over any terrain tint it crosses -- the
  // tabletop's water tile in particular brings the bare fill color's contrast
  // below the 3:1 floor for a graphical element.
  const pathEntity = state.viewer.entities.add({
    id: `path-${flight.flight_id}`,
    polyline: {
      positions,
      width: 3,
      material: new Cesium.PolylineOutlineMaterialProperty({
        color: Cesium.Color.fromCssColorString(visualColor).withAlpha(0.5),
        outlineColor: Cesium.Color.fromCssColorString("#0a141c").withAlpha(0.35),
        outlineWidth: 1,
      }),
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
      width: 4,
      // PolylineGraphics has no outlineColor/outlineWidth of its own -- the
      // outline has to be part of the material (PolylineOutlineMaterialProperty),
      // otherwise Cesium silently ignores it and the line never gets a casing.
      material: new Cesium.PolylineOutlineMaterialProperty({
        color: Cesium.Color.fromCssColorString(visualColor).withAlpha(0.95),
        outlineColor: Cesium.Color.fromCssColorString("#0a141c").withAlpha(0.6),
        outlineWidth: 1,
      }),
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
    orientation: orientations,
    viewFrom: new Cesium.Cartesian3(-40, -32, 24),
    ...uavVisual(visualColor),
    path: {
      leadTime: 0,
      trailTime: 30,
      width: 3,
      material: new Cesium.ColorMaterialProperty(
        Cesium.Color.fromCssColorString(visualColor).withAlpha(0.78),
      ),
    },
  });
  attachModelFallback(uav, visualColor);
  state.layerEntities.uav.push(uav);

  // ---- Incident markers ----
  const markers = [];
  const locatedIncidents = flight.incidents.filter(
    (incident) => incident.lat != null && incident.lon != null,
  );
  const incidentHeights = await sampleTerrainHeights(
    locatedIncidents.map((incident) => [incident.lon, incident.lat]),
  );
  // Incidents that fire from the same telemetry sample (e.g. a hovering
  // drone triggering two detectors at once) share the same lat/lon, so their
  // labels used to render stacked exactly on top of each other -- an
  // unreadable smear of overlapping text. Group by (rounded) position and
  // stagger each subsequent label in the group further up the screen.
  const labelStackCounts = new Map();
  locatedIncidents.forEach((incident, index) => {
    // Severity color, in one place, used for both embed (ring-only) and
    // standalone (filled dot) rendering -- previously the embed ring only
    // branched on "critical" vs everything else, so "info"-severity incidents
    // silently rendered with the "warning" color, contradicting the three-way
    // Critical/Warning/Notice legend shown elsewhere in this same viewer.
    const severityHex =
      incident.severity === "critical" ? "#e8564f" :
      incident.severity === "warning" ? "#f2a93b" : "#4fd8c4";
    // Color alone isn't a safe signal for colorblind viewers (WCAG 1.4.1) --
    // critical incidents also get a visibly larger marker and thicker ring,
    // so severity reads even if the color difference doesn't.
    const basePixelSize = params.get("embed") === "1" ? 18 : 12;
    const pixelSize = incident.severity === "critical" ? Math.round(basePixelSize * 1.3) : basePixelSize;
    const outlineWidth = incident.severity === "critical" ? 2.5 : 1.5;
    const positionKey = `${incident.lat.toFixed(4)},${incident.lon.toFixed(4)}`;
    const stackIndex = labelStackCounts.get(positionKey) || 0;
    labelStackCounts.set(positionKey, stackIndex + 1);
    const marker = state.viewer.entities.add({
      id: `incident-${incident.id || incident.type}-${flight.flight_id}-${index}`,
      position: Cesium.Cartesian3.fromDegrees(
        incident.lon,
        incident.lat,
        globeAltM(flight, incident.alt_m, incidentHeights[index] || 0),
      ),
      point: {
        pixelSize,
        color: params.get("embed") === "1" ? Cesium.Color.TRANSPARENT : Cesium.Color.fromCssColorString(severityHex),
        outlineColor: params.get("embed") === "1" ? Cesium.Color.fromCssColorString(severityHex) : Cesium.Color.fromCssColorString("#e9edf5").withAlpha(0.8),
        outlineWidth,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        scaleByDistance: new Cesium.NearFarScalar(100, 1.0, 10000, 0.5),
      },
      label: {
        text: `${incident.severity} ${incident.type}`,
        // The embedded review lists each incident below the map, so labels
        // stay off there; in standalone mode, incidents sharing a position
        // stack upward (see stackIndex) instead of overlapping illegibly.
        show: params.get("embed") !== "1",
        font: "10px monospace",
        fillColor: Cesium.Color.fromCssColorString("#e8e0d0"),
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        pixelOffset: new Cesium.Cartesian2(0, -22 - stackIndex * 15),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    markers.push(marker);
    state.layerEntities.incidents.push(marker);
  });

  // ---- Trees ----
  const trees = [];
  if (params.get("embed") !== "1") {
    try {
      const osmTrees = await loadOsmTrees(flightBounds(flight));
      osmTrees.forEach((tree, index) => {
        const treeEntities = addTreeToGlobe(tree, index);
        trees.push(...treeEntities);
        state.layerEntities.trees.push(...treeEntities);
      });
    } catch {
      // OSM trees are decorative; a blocked Overpass query should not break replay.
    }
  }

  // ---- Hazard circles ----
  const hazardCircles = await addHazardCircles(flight, incidentHeights);
  for (const hc of hazardCircles) {
    state.layerEntities.hazard.push(hc);
  }

  state.entities.push(pathEntity, uav, ...markers, ...trees, ...hazardCircles);

  // Start trail glow animation
  animateTrailGlow(flight.flight_id, state.viewer);

}

function focusActiveRoute(flight) {
  const viewer = state.viewer;
  const path = viewer?.entities.getById(`path-${flight.flight_id}`);
  if (!viewer || !path) {
    return;
  }
  const positions = path.polyline?.positions?.getValue?.(viewer.clock.currentTime);
  if (positions?.length) {
    viewer.camera.flyToBoundingSphere(Cesium.BoundingSphere.fromPoints(positions), {
      duration: 0,
      offset: new Cesium.HeadingPitchRange(-0.5, -0.72, params.get("embed") === "1" ? 460 : 460),
    });
    startOrbitFromCamera();
    return;
  }
  try {
    void viewer.flyTo(path, {
      duration: 0.8,
      offset: new Cesium.HeadingPitchRange(-0.5, -0.72, params.get("embed") === "1" ? 460 : 460),
    }).then(() => startOrbitFromCamera());
  } catch {
    // An interrupted route fit is harmless; the next selected flight redraws it.
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
  updateSeverityLegend();
  if (state.viewer?.requestRender) state.viewer.requestRender();
}

// ---- Flight legend (color-coded mission list) ----

function updateSeverityLegend() {
  // The side panel (with its incident list) is hidden in embed mode, so the
  // colored marker dots on the globe would otherwise have no on-screen key.
  // Only show the legend when there's a located incident marker actually on
  // screen -- nothing if there are none, or if the Incidents layer is off.
  els.severityLegend.hidden = state.layerEntities.incidents.length === 0 || !state.layers.incidents;
}

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
  els.datasetHint.classList.remove("error");
  const query = els.datasetFilter.value.trim().toLowerCase();
  els.datasetList.innerHTML = "";
  const visible = state.datasets.filter((item) => {
    const haystack = `${item.path} ${item.name}`.toLowerCase();
    return !query || haystack.includes(query);
  });
  if (!visible.length) {
    els.datasetHint.textContent = state.token
      ? "No matching recorded logs found."
      : "Enter your session key to list local recorded logs.";
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

    // Same three-way severity mapping as the incident markers -- "info"
    // incidents get their own tick color instead of silently reading as a
    // "warning" tick, which used to contradict the severity legend.
    const severityClass =
      inc.severity === "critical" ? "critical" :
      inc.severity === "warning" ? "warning" : "info";
    const tick = document.createElement("div");
    tick.className = `timeline-tick ${severityClass}`;
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
  els.scrubber.setAttribute("aria-valuenow", String(Math.round(pct)));

  // Format time
  const totalSeconds = Math.floor(elapsed / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const mins = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  els.timelineTime.textContent =
    `${String(hours).padStart(2, "0")}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  els.scrubber.setAttribute("aria-valuetext", `Elapsed ${els.timelineTime.textContent}`);
}

function scrubToPercent(pct) {
  if (!state.timelineFlightStart || !state.timelineFlightStop) return;
  const startMs = Cesium.JulianDate.toDate(state.timelineFlightStart).getTime();
  const stopMs = Cesium.JulianDate.toDate(state.timelineFlightStop).getTime();
  const targetSeconds = replayTimeAtPercent(startMs / 1000, stopMs / 1000, pct);
  if (targetSeconds == null) return;
  state.viewer.clock.shouldAnimate = false;
  if (state.viewer.clockViewModel) {
    state.viewer.clockViewModel.shouldAnimate = false;
  }
  state.viewer.clock.currentTime = Cesium.JulianDate.addSeconds(
    state.timelineFlightStart,
    targetSeconds - startMs / 1000,
    new Cesium.JulianDate(),
  );
  setStatus(`Paused · ${state.viewer.clock.multiplier}×`);
  state.viewer.scene.requestRender();
}

function groundSpeedMps(flight, pose) {
  const lower = flight.samples[pose.lower_sample];
  const upper = flight.samples[pose.upper_sample];
  if (!lower || !upper || upper.time_s <= lower.time_s) return null;
  const toRadians = (value) => value * Math.PI / 180;
  const dLat = toRadians(upper.lat - lower.lat);
  const dLon = toRadians(upper.lon - lower.lon);
  const lat1 = toRadians(lower.lat);
  const lat2 = toRadians(upper.lat);
  const arc = 2 * Math.atan2(
    Math.sqrt(Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2),
    Math.sqrt(1 - (Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2)),
  );
  return 6_371_000 * arc / (upper.time_s - lower.time_s);
}

function updateRouteOverview(flight, pose) {
  if (params.get("embed") !== "1" || !flight.samples.length) return;
  if (state.routeOverview?.flightId !== flight.flight_id) {
    const width = 240;
    const height = 132;
    const pad = 12;
    const meanLat = flight.samples.reduce((sum, sample) => sum + sample.lat, 0) / flight.samples.length;
    const refLat = flight.samples[0].lat;
    const refLon = flight.samples[0].lon;
    const cosLat = Math.cos(meanLat * Math.PI / 180);
    const local = flight.samples.map((sample) => [
      (sample.lon - refLon) * cosLat,
      sample.lat - refLat,
    ]);
    const minX = Math.min(...local.map(([x]) => x));
    const maxX = Math.max(...local.map(([x]) => x));
    const minY = Math.min(...local.map(([, y]) => y));
    const maxY = Math.max(...local.map(([, y]) => y));
    const scale = Math.min((width - 2 * pad) / (maxX - minX || 1), (height - 2 * pad) / (maxY - minY || 1));
    const project = (lat, lon) => [
      pad + (((lon - refLon) * cosLat - minX) * scale),
      height - pad - ((lat - refLat - minY) * scale),
    ];
    const points = flight.samples.map((sample) => project(sample.lat, sample.lon));
    els.routeOverviewPath.setAttribute("d", points.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" "));

    // ---- Altitude sparkline (time on X, altitude on Y) ----
    const altWidth = 240;
    const altHeight = 40;
    const altPadX = 4;
    const altPadTop = 5;
    const altPadBottom = 3;
    const startedAt = flight.samples[0].time_s;
    const duration = flight.samples.at(-1).time_s - startedAt;
    const alts = flight.samples.map((sample) => sample.alt_m);
    const minAlt = Math.min(...alts, 0); // include 0 so a short hop near the ground doesn't look mid-air
    const maxAlt = Math.max(...alts);
    const altSpan = maxAlt - minAlt || 1;
    const projectAlt = (timeS, altM) => [
      altPadX + (duration > 0 ? ((timeS - startedAt) / duration) * (altWidth - 2 * altPadX) : 0),
      altHeight - altPadBottom - ((altM - minAlt) / altSpan) * (altHeight - altPadTop - altPadBottom),
    ];
    const altPoints = flight.samples.map((sample) => projectAlt(sample.time_s, sample.alt_m));
    els.routeOverviewAltPath.setAttribute(
      "d",
      altPoints.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" "),
    );
    els.routeOverviewAltRange.textContent = `${minAlt.toFixed(0)}–${maxAlt.toFixed(0)} m`;

    state.routeOverview = {
      flightId: flight.flight_id,
      project,
      start: points[0],
      duration,
      startedAt,
      projectAlt,
    };
  }
  const [startX, startY] = state.routeOverview.start;
  const [currentX, currentY] = state.routeOverview.project(pose.lat, pose.lon);
  els.routeOverviewStart.setAttribute("cx", startX.toFixed(1));
  els.routeOverviewStart.setAttribute("cy", startY.toFixed(1));
  els.routeOverviewCurrent.setAttribute("cx", currentX.toFixed(1));
  els.routeOverviewCurrent.setAttribute("cy", currentY.toFixed(1));
  const [altCurrentX, altCurrentY] = state.routeOverview.projectAlt(pose.time_s, pose.alt_m);
  els.routeOverviewAltCurrent.setAttribute("cx", altCurrentX.toFixed(1));
  els.routeOverviewAltCurrent.setAttribute("cy", altCurrentY.toFixed(1));
  const progress = state.routeOverview.duration > 0
    ? (pose.time_s - state.routeOverview.startedAt) / state.routeOverview.duration
    : 0;
  els.routeOverviewProgress.textContent = `${Math.round(clamp(progress, 0, 1) * 100)}%`;
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
  els.transportTelemetry.textContent = `${formatIso8601Utc(pose.time_s).slice(11, 19)} UTC · ${pose.alt_m.toFixed(0)} m`;
  if (params.get("embed") === "1") {
    const speed = groundSpeedMps(flight, pose);
    els.orbitalAltitude.textContent = pose.alt_m.toFixed(1);
    els.orbitalSpeed.textContent = speed == null ? "—" : speed.toFixed(1);
    els.orbitalBattery.textContent = Number.isFinite(pose.battery_pct) ? pose.battery_pct.toFixed(0) : "—";
    els.orbitalRecordedTime.textContent = formatIso8601Utc(pose.time_s).slice(11, 19);
    updateRouteOverview(flight, pose);
  }
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
      const severity = String(item.severity || "notice");
      const kind = String(item.type || "").replaceAll("_", " ");
      row.innerHTML = `<strong>${escapeAttr(severity.charAt(0).toUpperCase() + severity.slice(1))}</strong> &middot; ${escapeAttr(kind)}<br />${escapeAttr(item.summary || "")}`;
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
  state.tabletop?.destroy();
  state.tabletop = null;
  state.terrainProgress = null;
  state.mapContext = routeContext(state.atlas, flight.samples);
  if (state.mapContext) {
    state.tabletop = createStreamingTabletop(state.viewer, state.mapContext, {
      bounds: tabletopBounds(state.mapContext, flight.samples),
      show: !state.mapVisible,
      onProgress: progress => {
        if(drawId!==state.globeDraw)return;
        state.terrainProgress=progress;
        updateTerrainContext();
      },
    });
  }
  setPresentationMode(state.mapVisible);
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
  updateLayerVisibility();
  focusActiveRoute(flight);
  if (drawId !== state.globeDraw) {
    return;
  }
  const pausedAtEvidence = seekRequestedReplayTime(flight);
  if (!pausedAtEvidence) {
    setPlaying(true);
    renderHud(flight, interpolate(flight, flight.samples[0].time_s));
    updateTimelineUI();
  }
  setStatus(pausedAtEvidence ? "Evidence timestamp selected" : `Recorded playback ready · ${DEFAULT_PLAYBACK_SPEED}×`);
}

function seekRequestedReplayTime(flight) {
  const timeS = replayTimeForTimestamp(flight, params.get("timestamp"));
  if (timeS == null || !state.viewer) {
    return false;
  }
  state.viewer.clock.currentTime = Cesium.JulianDate.fromDate(new Date(timeS * 1000));
  state.viewer.clock.shouldAnimate = false;
  renderHud(flight, interpolate(flight, timeS));
  state.viewer.scene.requestRender();
  return true;
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
  // Captured before the clock jumps, so it reflects where the camera was
  // actually looking a moment ago -- the glide's starting point.
  const previousTarget = state.orbit.enabled ? getUavWorldPosition() : undefined;
  const targetTime = Cesium.JulianDate.fromIso8601(targetIso);
  state.viewer.clock.currentTime = targetTime;
  const timeS = Date.parse(targetIso.endsWith("Z") ? targetIso : `${targetIso}Z`) / 1000;
  const pose = interpolate(flight, timeS);
  const frame =
    cameraFrameForIncident(flight.cameraFrames || [], incident) ||
    cameraFrameAt(flight.cameraFrames || [], pose.time_s);
  updateCameraPip(frame);
  renderHud(flight, pose);
  if (previousTarget) {
    flyOrbitCameraFrom(previousTarget);
  }
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
    const complete =
      clock.shouldAnimate && Cesium.JulianDate.compare(clock.currentTime, clock.stopTime) >= 0;
    if (complete) {
      clock.shouldAnimate = false;
      if (state.viewer.clockViewModel) {
        state.viewer.clockViewModel.shouldAnimate = false;
      }
    }
    renderHud(flight, interpolate(flight, getPoseFromClock(clock).time_s));
    updateTimelineUI();
    applyOrbitCamera();
    if (clock.shouldAnimate) {
      els.transportStatus.textContent = `Playing · ${clock.multiplier}×`;
      state.viewer.scene.requestRender();
    } else if (complete) {
      els.transportStatus.textContent = "Replay complete";
    }
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
  const path = await fetch("./assets/demo_path.json?v=stream-4").then((response) => response.json());
  const incidents = await fetch("./assets/demo_incidents.json?v=stream-4").then((response) => response.json());
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
    els.datasetHint.textContent = friendlyError(error);
    els.datasetHint.classList.add("error");
  }
}

function renderPatterns() {
  els.patternList.innerHTML = "";
  els.patternHint.classList.remove("error");
  if (!state.patterns.length) {
    els.patternHint.textContent = state.token
      ? "No warning has repeated across 2 or more flights yet."
      : "Enter your session key to see patterns shared across flights.";
    return;
  }
  els.patternHint.textContent = "Seen on 2 or more flights — worth comparing before treating any one as a one-off.";
  for (const pattern of state.patterns) {
    const row = document.createElement("div");
    row.className = "dataset-row";
    const label = document.createElement("p");
    const severity = String(pattern.max_severity || "notice").replace(/^./, (c) => c.toUpperCase());
    const kind = String(pattern.incident_type || "").replaceAll("_", " ");
    label.innerHTML = `<strong>${escapeAttr(severity)} &middot; ${escapeAttr(kind)}</strong><br />${escapeAttr(pattern.summary || "")}`;
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
    setStatus(friendlyError(error), true);
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
    els.patternHint.textContent = friendlyError(error);
    els.patternHint.classList.add("error");
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
    const message = friendlyError(error);
    setIngest(path, {
      busy: false,
      status: "failed",
      percent: ingestPercent("failed"),
      error: message,
    });
    setStatus(message, true);
  }
}

function setPlaying(playing) {
  const viewer = state.viewer;
  const clock = viewer.clock;
  if (playing) {
    const flight = state.flights[state.active];
    const currentTime = Cesium.JulianDate.toDate(clock.currentTime).getTime() / 1000;
    const restartTime = replayTimeForPlay(flight, currentTime);
    if (restartTime != null) {
      clock.currentTime = Cesium.JulianDate.fromDate(new Date(restartTime * 1000));
    }
  }
  clock.canAnimate = true;
  clock.shouldAnimate = playing;
  if (viewer.clockViewModel) {
    viewer.clockViewModel.shouldAnimate = playing;
  }
  viewer.trackedEntity = undefined;
  if (playing && !state.orbit.enabled) {
    startOrbitFromCamera();
  }
  viewer.scene.requestRender();
}

// Plain-language terrain/map status for a first-time viewer -- the engineering
// detail (tile counts) stays available but de-emphasized, not the headline.
function updateTerrainContext() {
  const note=document.getElementById('terrainContext');
  if(!note)return;
  const p=state.terrainProgress;
  note.textContent=!state.mapContext ? 'Showing a simplified globe — detailed terrain is not available for this area.'
    : state.mapVisible ? 'Satellite map view · terrain preloaded'
    : p && !p.complete ? `Loading terrain… (${p.terrain}/${p.terrainTotal})`
    : p?.failed ? 'Terrain ready — a few map details could not be loaded.'
    : 'Offline terrain model · approximate elevation and building outlines';
}

function setPresentationMode(mapVisible) {
  state.mapVisible = mapVisible;
  const viewer = state.viewer;
  const imageryLayer = viewer?.imageryLayers.get(0);
  if (imageryLayer) {
    imageryLayer.show = mapVisible;
    imageryLayer.alpha = mapVisible ? 1 : 0;
    imageryLayer.brightness = mapVisible ? 0.70 : 0.26;
    imageryLayer.contrast = mapVisible ? 1 : 1.2;
    imageryLayer.saturation = mapVisible ? 1 : 0.04;
    imageryLayer.hue = mapVisible ? 0 : 4.2;
  }
  state.tabletop?.setVisible(!mapVisible);
  if (state.tabletopFinish) state.tabletopFinish.enabled = !mapVisible;
  updateTerrainContext();
  if (viewer) {
    viewer.scene.globe.show = mapVisible || !state.tabletop;
    viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString(mapVisible ? "#111b22" : "#194452");
    viewer.scene.requestRender();
  }
  els.studioViewButton.setAttribute("aria-pressed", String(!mapVisible));
  els.mapViewButton.setAttribute("aria-pressed", String(mapVisible));
}

function resetPlayback() {
  const flight = state.flights[state.active];
  if (!flight || !state.viewer) {
    return;
  }
  const start = flight.samples[0]?.time_s;
  if (!Number.isFinite(start)) {
    return;
  }
  state.viewer.clock.currentTime = Cesium.JulianDate.fromDate(new Date(start * 1000));
  setPlaying(false);
  renderHud(flight, interpolate(flight, start));
  updateTimelineUI();
  state.viewer.scene.requestRender();
}

function bindControls() {
  setPresentationMode(state.mapVisible);
  els.studioViewButton.addEventListener("click", () => setPresentationMode(false));
  els.mapViewButton.addEventListener("click", () => setPresentationMode(true));
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
    setStatus(
      state.viewer.clock.shouldAnimate
        ? `Playing · ${state.viewer.clock.multiplier}×`
        : `Paused · ${state.viewer.clock.multiplier}×`,
    );
  });
  els.resetButton.addEventListener("click", resetPlayback);
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
    if (value === DEFAULT_PLAYBACK_SPEED) {
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

  els.scrubber.addEventListener("keydown", (event) => {
    const current = Number(els.scrubber.getAttribute("aria-valuenow") || 0);
    const change = event.key === "PageUp" ? 10 : event.key === "PageDown" ? -10 :
      event.key === "ArrowRight" || event.key === "ArrowUp" ? 2 :
        event.key === "ArrowLeft" || event.key === "ArrowDown" ? -2 : null;
    let target = change == null ? null : current + change;
    if (event.key === "Home") target = 0;
    if (event.key === "End") target = 100;
    if (target == null) return;
    event.preventDefault();
    scrubToPercent(clamp(target, 0, 100));
    updateTimelineUI();
  });

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
    const atlasReady=loadTabletopAtlas();
    const modelReady=probeUavModel();
    state.viewer = await createViewer();
    bindControls();
    attachClock();
    setupClickToFollow(state.viewer);
    setupIncidentTooltip(state.viewer);
    state.atlas=await atlasReady;
    state.viewer.terrainProvider=await createTerrainProvider();
    await modelReady;
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
    if (state.token && params.get("embed") !== "1") {
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
    setStatus(friendlyError(error), true);
    if (!state.flights.length) {
      state.flights = await loadOfflineDemo();
      await showActiveFlight();
    }
  }
}

void bootstrap();
void CESIUM_VERSION;
