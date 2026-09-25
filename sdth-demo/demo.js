import { logFilename, workspaceRoute, sidebarWidth, folderTrail, folderPath, folderDestinations, flightDisplayName, localAnalysisView, modelDisplay, modelStatus, modelProgressText, usesDefaultModel, queryText, simulationProvenance } from "./demo-contract.mjs?v=workspace-4";

const state = { token: sessionStorage.getItem("wislDemoToken") || "", flights: [], selectedFlight: null, upload: null, pollTimer: null, demoStatus: null, selectionVersion: 0, seedingLibrary: false, folders: [], flightFolders: {}, folderId: sessionStorage.getItem("wislMissionFolder") || null, libraryReady: false, libraryBusy: false, explorerEdit: null, uploadDestination: null, uploadBusy: false, expandedFolders: new Set(), treeFocusKey: null, treeSelectedKey: null };
const DEMO_LIBRARY_LOGS = [
  { url: "/demo/fixtures/singapore/dji_csv_sg_lck_survey_normal.csv", name: "dji_csv_sg_lck_survey_normal.csv", type: "text/csv" },
  { url: "/demo/fixtures/singapore/dji_csv_sg_lck_survey_gps_weak.csv", name: "dji_csv_sg_lck_survey_gps_weak.csv", type: "text/csv" },
  { url: "/demo/fixtures/singapore/dji_csv_sg_seletar_perimeter_gps_weak.csv", name: "dji_csv_sg_seletar_perimeter_gps_weak.csv", type: "text/csv" },
  { url: "/demo/fixtures/singapore/dji_csv_sg_hillview_inspection_battery_critical.csv", name: "dji_csv_sg_hillview_inspection_battery_critical.csv", type: "text/csv" },
  { url: "/demo/fixtures/singapore/dji_csv_sg_hillview_inspection_dropout.csv", name: "dji_csv_sg_hillview_inspection_dropout.csv", type: "text/csv" },
  { url: "/demo/fixtures/singapore/dji_csv_sg_seletar_ends_airborne.csv", name: "dji_csv_sg_seletar_ends_airborne.csv", type: "text/csv" },
  { url: "/demo/fixtures/dji_csv_gps_jamming.csv", name: "dji_csv_gps_jamming.csv", type: "text/csv" },
  { url: "/demo/fixtures/orbiter4_gps_denied_frozen.json", name: "orbiter4_gps_denied_frozen.json", type: "application/json" },
  { url: "/demo/fixtures/dji_csv_motor_fail_recover_024.csv", name: "dji_csv_motor_fail_recover_024.csv", type: "text/csv" },
  { url: "/demo/fixtures/ardupilot_amesbury_alpha.tlog", name: "ardupilot_amesbury_alpha.tlog", type: "application/octet-stream" },
  { url: "/demo/fixtures/ardupilot_amesbury_alpha.bin", name: "ardupilot_amesbury_alpha.bin", type: "application/octet-stream" },
  { url: "/demo/fixtures/hermes900_amesbury_perimeter.stanag", name: "hermes900_amesbury_perimeter.stanag", type: "text/plain" },
  { url: "/demo/fixtures/aunav_neo_amesbury_patrol.ros", name: "aunav_neo_amesbury_patrol.ros", type: "text/plain" },
];
const $ = (id) => document.getElementById(id);
const wideLayout = window.matchMedia("(min-width: 760px)");
const els = { apiDot: $("apiDot"), apiState: $("apiState"), authPanel: $("authPanel"), token: $("tokenInput"), uploadMessage: $("uploadMessage"), uploadStatus: $("uploadStatus"), traceDetail: $("traceDetail"), file: $("logFile"), flightList: $("flightList"), flightMeta: $("flightMeta"), selectedFlightTitle: $("selectedFlightTitle"), incidentTitle: $("incidentTitle"), incidentCount: $("incidentCount"), incidentList: $("incidentList"), modelState: $("modelState"), replayEmpty: $("replayEmpty"), replayFrame: $("replayFrame"), openReplay: $("openReplay"), patternList: $("patternList"), bulletinList: $("bulletinList"), analysisAnswer: $("analysisAnswer"), question: $("questionInput"), localAnalysis: $("localAnalysis"), localAnalysisBody: $("localAnalysisBody"), downloadReportButton: $("downloadReportButton") };

function authHeaders(json = false) { const headers = state.token ? { Authorization: `Bearer ${state.token}` } : {}; return json ? { ...headers, "Content-Type": "application/json" } : headers; }
function detail(error) { return Array.isArray(error?.detail) ? error.detail.map(item => item.msg || "Invalid request field").join(" · ") : error?.detail || error?.message || "The request could not be completed."; }
const VAGUE_ERRORS = new Set(["", "internal server error", "not found", "unprocessable entity", "bad request", "forbidden", "unauthorized"]);
function friendlyError(message) {
  const text = String(message || "").trim();
  const lower = text.toLowerCase();
  if (!text || VAGUE_ERRORS.has(lower)) return "Something went wrong on the platform side. Please try again in a moment.";
  if (lower.includes("failed to fetch") || lower.includes("networkerror") || lower.includes("connection is unavailable")) return "Could not reach the platform. Check that the local service is running, then try again.";
  return /[.!?]$/.test(text) ? text : `This didn't work: ${text}.`;
}
async function api(path, options = {}) {
  let response;
  try { response = await fetch(path, { ...options, headers: { ...authHeaders(options.json), ...(options.headers || {}) } }); }
  catch { throw new Error("Platform connection is unavailable. Check the local service and session key."); }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(detail(body));
  return body;
}
function setApi(status, text) { els.apiDot.className = `live-dot ${status}`; els.apiState.textContent = text; }
function setMessage(text, kind = "") { els.uploadMessage.textContent = text; els.uploadMessage.className = `notice ${kind}`; }
function fmtTime(value) { if (!value) return "Recorded time unavailable"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }); }
function relativeTime(value) { const then = new Date(value ? value.replace(" ", "T") + (value.includes("Z") || value.includes("+") ? "" : "Z") : NaN); const seconds = (Date.now() - then.getTime()) / 1000; if (Number.isNaN(seconds)) return value || "recently"; if (seconds < 60) return "just now"; if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`; if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`; return `${Math.floor(seconds / 86400)} d ago`; }
function label(value) { return String(value || "unclassified").replaceAll("_", " "); }
function escapeHtml(value) { const div = document.createElement("div"); div.textContent = value ?? ""; return div.innerHTML; }

function pipeline(status, detailText) {
  const stages = ["received", "parsing", "normalizing", "ready"];
  const current = status === "detecting" ? 3 : stages.indexOf(status);
  document.querySelectorAll("#pipelineStages li").forEach((el, index) => el.className = current < 0 ? "" : index < current ? "done" : index === current ? "active" : "");
  const failed = status === "failed";
  els.uploadStatus.textContent = failed ? "Failed" : status === "ready" ? "Ready to review" : status || "Waiting";
  $("uploadTabDot").hidden = !status || status === "ready" || failed;
  els.uploadStatus.className = `status-label ${failed ? "failed" : current < 0 ? "waiting" : ""}`;
  els.traceDetail.textContent = detailText || (failed ? "Something went wrong while processing this log." : `Current step: ${status || "waiting"}.`);
}
function uploadComplete(status) { return status === "ready" || status === "failed"; }
async function pollUpload(uploadId) {
  clearTimeout(state.pollTimer);
  try {
    let upload;
    try { upload = await api(`/v1/uploads/${encodeURIComponent(uploadId)}`); }
    catch (firstError) { upload = await api(`/v1/logs/${encodeURIComponent(uploadId)}/status`).catch(() => { throw firstError; }); }
    state.upload = upload;
    pipeline(upload.status, upload.error || (upload.duplicate ? "Duplicate found: using the earlier result." : `${upload.filename || "Log"} · ${upload.status}`));
    if (upload.status === "failed") { state.uploadBusy = false; setMessage(friendlyError(upload.error) || "The log could not be processed.", "error"); return; }
    if (upload.status === "ready") {
      setMessage(upload.duplicate ? "Duplicate found. The earlier processed log is ready." : "The log has been processed and is ready for review.", "success");
      await refreshFlights();
      const destination = state.uploadDestination;
      if (destination?.uploadId === uploadId) {
        state.uploadDestination = null;
        if (!destination.duplicate && destination.folderId && upload.flight_id) {
          try { await assignMission(upload.flight_id, destination.folderId); }
          catch (error) { setExplorerNotice(`Log processed, but its folder could not be saved. ${friendlyError(error.message)}`, true); }
        }
      }
      if (upload.flight_id) { await selectFlight(upload.flight_id, null, {revealReplay: true}); }
      state.uploadBusy = false;
      return;
    }
    state.pollTimer = setTimeout(() => pollUpload(uploadId), 1400);
  } catch (error) { state.uploadBusy = false; const msg = friendlyError(error.message); setMessage(msg, "error"); pipeline("failed", msg); }
}
async function uploadFile(file) {
  if (!state.token) { setMessage("Add a session key before uploading.", "error"); setAuthPanel(true); return; }
  if (!file) return;
  if (state.uploadBusy) { setMessage("Wait for the current log to finish processing before importing another."); return; }
  if (file.size > 100 * 1024 * 1024) { setMessage("Choose a file smaller than 100 MB.", "error"); return; }
  state.uploadBusy = true;
  const folderId = state.libraryReady ? state.folderId : null;
  const data = new FormData(); data.append("file", file);
  setMessage(`Uploading ${file.name}…`); pipeline("received", "Uploading your log…");
  try {
    const response = await fetch("/v1/logs/upload", { method: "POST", headers: authHeaders(), body: data });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(detail(body));
    state.upload = body;
    state.uploadDestination = {uploadId: body.upload_id, folderId, duplicate: body.duplicate};
    setMessage(body.duplicate ? "A matching log already exists; checking its status…" : "Log accepted. Tracking its progress below.");
    pollUpload(body.upload_id);
  } catch (error) { state.uploadBusy = false; const msg = friendlyError(error.message); setMessage(msg, "error"); pipeline("failed", msg); }
}
function setExplorerNotice(text, error = false) {
  const notice = $("explorerNotice");
  notice.textContent = text; notice.hidden = !text; notice.className = `explorer-notice${error ? " error" : ""}`;
}
function openFolder(folderId) {
  state.folderId = folderId;
  for (const folder of folderTrail(state.folders, folderId)) state.expandedFolders.add(folder.id);
  state.treeFocusKey = state.treeSelectedKey = folderId ? `folder:${folderId}` : null;
  rememberTree();
  sessionStorage.setItem("wislMissionFolder", folderId || "");
  $("missionSearch").value = "";
  setExplorerNotice(""); renderFlights(); els.flightList.scrollTop = 0;
}
function explorerButton(text, title, action, className = "entry-actions") {
  const button = document.createElement("button");
  button.type = "button"; button.className = className; button.textContent = text;
  button.title = title; button.setAttribute("aria-label", title); button.addEventListener("click", action);
  return button;
}
function folderDropTarget(node, folderId) {
  const accepts = event => !state.libraryBusy && state.libraryReady && event.dataTransfer.types.includes("application/x-wisl-flight");
  ["dragenter", "dragover"].forEach(type => node.addEventListener(type, event => {
    if (!accepts(event)) return;
    event.preventDefault(); event.dataTransfer.dropEffect = "move"; node.classList.add("folder-drop");
  }));
  node.addEventListener("dragleave", () => node.classList.remove("folder-drop"));
  node.addEventListener("drop", async event => {
    node.classList.remove("folder-drop");
    if (!accepts(event)) return;
    event.preventDefault();
    const flightId = event.dataTransfer.getData("application/x-wisl-flight");
    if (!state.flights.some(flight => flight.id === flightId)) return;
    state.libraryBusy = true; renderFlights();
    try { await assignMission(flightId, folderId); setExplorerNotice(`Moved to ${folderPath(state.folders, folderId)}.`); }
    catch (error) { setExplorerNotice(friendlyError(error.message), true); }
    finally { state.libraryBusy = false; renderFlights(); }
  });
}
function rememberTree() {
  sessionStorage.setItem("wislExpandedFolders", JSON.stringify([...state.expandedFolders]));
}
function focusTree(key) {
  const nodes = [...els.flightList.querySelectorAll('[role="treeitem"]')];
  const target = nodes.find(node => node.dataset.treeKey === key) || nodes[0];
  if (!target) return;
  state.treeFocusKey = target.dataset.treeKey;
  for (const node of nodes) node.tabIndex = node === target ? 0 : -1;
  target.focus({preventScroll: true}); target.querySelector(".tree-row").scrollIntoView({block: "nearest"});
}
function toggleFolder(id) {
  if (state.expandedFolders.has(id)) state.expandedFolders.delete(id); else state.expandedFolders.add(id);
  state.folderId = id; state.treeFocusKey = state.treeSelectedKey = `folder:${id}`;
  sessionStorage.setItem("wislMissionFolder", id); rememberTree(); renderFlights(); focusTree(state.treeFocusKey);
}
function renderFlights() {
  const previousScroll = els.flightList.scrollTop, hadFocus = els.flightList.contains(document.activeElement);
  if (state.libraryReady && state.folderId && !state.folders.some(folder => folder.id === state.folderId)) state.folderId = null;
  const location = folderPath(state.folders, state.folderId);
  $("uploadFolderHint").textContent = `New uploads go to ${location}. Existing records keep their folder.`;
  $("explorerLocation").textContent = location; $("explorerLocation").title = `New folders and uploads: ${location}`;
  $("newFolder").disabled = !state.libraryReady || state.libraryBusy;
  $("newFolder").title = `Create folder in ${location}`;
  $("folderUp").disabled = !state.folderId;
  els.flightList.replaceChildren(); els.flightList.className = "flight-list";
  $("libraryCount").textContent = String(state.flights.length).padStart(2, "0");
  const search = $("missionSearch").value.trim().toLowerCase();
  const flights = state.flights.filter(flight => !search || `${logFilename(flight)} ${flightDisplayName(flight)} ${flight.source || ""} ${folderPath(state.folders, state.flightFolders[flight.id])}`.toLowerCase().includes(search))
    .sort((a, b) => logFilename(a).localeCompare(logFilename(b), undefined, {numeric: true}));
  const shownFolders = new Set();
  if (search) {
    const ids = [...state.folders.filter(folder => folderPath(state.folders, folder.id).toLowerCase().includes(search)).map(folder => folder.id), ...flights.map(flight => state.flightFolders[flight.id])];
    for (const id of ids) for (const folder of folderTrail(state.folders, id)) shownFolders.add(folder.id);
  }
  const folders = state.folders.filter(folder => !search || shownFolders.has(folder.id)).sort((a, b) => a.name.localeCompare(b.name, undefined, {numeric: true}));
  $("explorerHeading").textContent = search ? "SEARCH RESULTS" : "RECORDED LOGS";
  $("explorerCount").textContent = `${flights.length} ${flights.length === 1 ? "file" : "files"}`;
  function entry(kind, item, depth) {
    const folder = kind === "folder", name = folder ? item.name : logFilename(item), key = `${kind}:${item.id}`;
    const node = document.createElement("div"); node.className = "tree-node"; node.dataset.treeKey = key; node.dataset.kind = kind; node.dataset.id = item.id;
    node.setAttribute("role", "treeitem"); node.setAttribute("aria-level", String(depth + 1)); node.setAttribute("aria-label", name);
    node.setAttribute("aria-selected", String(key === state.treeSelectedKey)); node.tabIndex = key === state.treeFocusKey ? 0 : -1;
    const row = document.createElement("div"); row.className = `tree-row ${folder ? "tree-folder" : "tree-file"}`; row.style.setProperty("--depth", Math.min(depth, 8));
    row.classList.toggle("selected", key === state.treeSelectedKey);
    row.title = folder ? folderPath(state.folders, item.id) : `${folderPath(state.folders, state.flightFolders[item.id])} / ${name}\n${flightDisplayName(item)} · ${fmtTime(item.started_at)}`;
    row.innerHTML = folder ? '<span class="tree-chevron" aria-hidden="true">›</span><svg class="tree-icon" viewBox="0 0 20 20" aria-hidden="true"><path d="M2 6V4h6l2 2h8v11H2Z"/></svg><span class="tree-name"></span>' : '<span class="tree-chevron" aria-hidden="true"></span><svg class="tree-icon" viewBox="0 0 20 24" aria-hidden="true"><path d="M3 2h9l5 5v15H3Zm9 0v6h5M6 12h8m-8 4h8"/></svg><span class="tree-name"></span>';
    row.querySelector(".tree-name").textContent = name;
    if (!folder) row.dataset.extension = name.split(".").at(-1).toLowerCase();
    const action = explorerButton("⋯", folder ? `Rename or move folder ${name}` : `Move ${name}`, event => { event.stopPropagation(); openExplorerDialog(kind, item.id); });
    action.tabIndex = -1; action.disabled = !state.libraryReady || state.libraryBusy;
    row.append(action); node.append(row);
    row.addEventListener("click", event => {
      if (event.target.closest(".entry-actions")) return;
      state.treeFocusKey = state.treeSelectedKey = key;
      if (folder) toggleFolder(item.id); else selectFlight(item.id, null, {revealReplay: true});
    });
    row.addEventListener("contextmenu", event => { event.preventDefault(); openExplorerDialog(kind, item.id); });
    if (folder) {
      node.setAttribute("aria-expanded", String(Boolean(search) || state.expandedFolders.has(item.id)));
      folderDropTarget(row, item.id);
    } else {
      row.draggable = state.libraryReady && !state.libraryBusy;
      row.addEventListener("dragstart", event => { event.dataTransfer.setData("application/x-wisl-flight", item.id); event.dataTransfer.effectAllowed = "move"; });
      row.addEventListener("dragend", () => document.querySelectorAll(".folder-drop").forEach(item => item.classList.remove("folder-drop")));
    }
    return node;
  }
  function level(container, parentId, depth) {
    for (const folder of folders.filter(item => item.parent_id === parentId)) {
      const node = entry("folder", folder, depth); container.append(node);
      if (node.getAttribute("aria-expanded") === "true") {
        const group = document.createElement("div"); group.setAttribute("role", "group"); node.append(group); level(group, folder.id, depth + 1);
      }
    }
    for (const flight of flights.filter(item => (state.flightFolders[item.id] || null) === parentId)) container.append(entry("flight", flight, depth));
  }
  level(els.flightList, null, 0);
  const nodes = [...els.flightList.querySelectorAll('[role="treeitem"]')];
  if (!nodes.some(node => node.tabIndex === 0) && nodes[0]) { nodes[0].tabIndex = 0; state.treeFocusKey = nodes[0].dataset.treeKey; }
  if (!nodes.length) {
    els.flightList.classList.add("empty-state");
    els.flightList.textContent = !state.token ? "Connect a session to open recorded log files." : !state.libraryReady ? "Mission explorer is unavailable. Try refreshing." : search ? "No matching folders or files." : "No files yet. Import a log or create a folder.";
  }
  els.flightList.scrollTop = previousScroll;
  if (hadFocus) focusTree(state.treeFocusKey);
}
function navigateTree(event) {
  if (event.target.closest(".entry-actions")) return;
  const node = event.target.closest('[role="treeitem"]');
  if (!node) return;
  const nodes = [...els.flightList.querySelectorAll('[role="treeitem"]')], index = nodes.indexOf(node);
  const key = event.key, folder = node.dataset.kind === "folder", expanded = node.getAttribute("aria-expanded") === "true";
  if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "Enter", " ", "F2"].includes(key)) return;
  event.preventDefault();
  if (key === "ArrowUp" || key === "ArrowDown") focusTree(nodes[Math.max(0, Math.min(nodes.length - 1, index + (key === "ArrowDown" ? 1 : -1)))].dataset.treeKey);
  else if (key === "Home" || key === "End") focusTree(nodes[key === "Home" ? 0 : nodes.length - 1].dataset.treeKey);
  else if (key === "ArrowRight" && folder) { if (!expanded) toggleFolder(node.dataset.id); else { const child = node.querySelector('[role="group"] > [role="treeitem"]'); if (child) focusTree(child.dataset.treeKey); } }
  else if (key === "ArrowLeft") { if (folder && expanded && !$("missionSearch").value.trim()) toggleFolder(node.dataset.id); else { const parent = node.parentElement.closest('[role="treeitem"]'); if (parent) focusTree(parent.dataset.treeKey); } }
  else if (key === "F2") openExplorerDialog(node.dataset.kind, node.dataset.id);
  else if (key === "Enter" || key === " ") node.querySelector(".tree-row").click();
}
function openExplorerDialog(kind, id = null) {
  if (!state.libraryReady || state.libraryBusy) return;
  state.explorerEdit = {kind, id};
  const folder = state.folders.find(item => item.id === id);
  const flight = state.flights.find(item => item.id === id);
  $("explorerDialogTitle").textContent = kind === "new" ? "New folder" : kind === "folder" ? "Organise folder" : "Move recorded log";
  $("explorerDialogHint").textContent = kind === "flight" ? `${flightDisplayName(flight)}. Only its library location changes; the original log and evidence stay untouched.` : "Create, rename or move folders without changing original log files.";
  $("folderNameField").hidden = kind === "flight";
  $("folderName").disabled = kind === "flight"; $("folderName").required = kind !== "flight";
  $("folderName").value = folder?.name || "";
  const destination = $("folderDestination"); destination.replaceChildren(new Option("Missions (root)", ""));
  for (const item of folderDestinations(state.folders, kind === "folder" ? id : null)) destination.add(new Option(folderPath(state.folders, item.id), item.id));
  destination.value = (kind === "new" ? state.folderId : kind === "folder" ? folder.parent_id : state.flightFolders[id]) || "";
  $("saveExplorer").textContent = kind === "new" ? "Create folder" : kind === "folder" ? "Save changes" : "Move log";
  $("explorerFormError").hidden = true;
  $("explorerDialog").showModal();
  (kind === "flight" ? destination : $("folderName")).focus();
}
async function assignMission(flightId, folderId) {
  await api(`/v1/library/flights/${encodeURIComponent(flightId)}/folder`, {method: "PUT", json: true, body: JSON.stringify({folder_id: folderId})});
  if (folderId) state.flightFolders[flightId] = folderId;
  else delete state.flightFolders[flightId];
}
async function saveExplorer(event) {
  event.preventDefault();
  if (state.libraryBusy) return;
  const {kind, id} = state.explorerEdit, parentId = $("folderDestination").value || null;
  state.libraryBusy = true; $("explorerFields").disabled = true; $("saveExplorer").disabled = true; $("cancelExplorer").disabled = true; $("explorerFormError").hidden = true;
  renderFlights();
  try {
    if (kind === "flight") {
      await assignMission(id, parentId);
      setExplorerNotice(`Log moved to ${folderPath(state.folders, parentId)}.`);
    } else {
      const folder = await api(`/v1/library/folders${kind === "folder" ? `/${encodeURIComponent(id)}` : ""}`, {method: kind === "folder" ? "PUT" : "POST", json: true, body: JSON.stringify({name: $("folderName").value.trim(), parent_id: parentId})});
      state.folders = [...state.folders.filter(item => item.id !== folder.id), folder];
      if (kind === "new") openFolder(folder.id);
      setExplorerNotice(kind === "new" ? "Folder created. Create subfolders here, or move logs in from Missions." : "Folder updated. Its contents are unchanged.");
    }
    $("explorerDialog").close();
  } catch (error) {
    $("explorerFormError").textContent = friendlyError(error.message); $("explorerFormError").hidden = false;
  } finally {
    state.libraryBusy = false; $("explorerFields").disabled = false; $("saveExplorer").disabled = false; $("cancelExplorer").disabled = false; renderFlights();
  }
}
async function allFlights() {
  const items = [];
  for (let offset = 0; ; offset += 200) {
    const page = await api(`/v1/flights?limit=200&offset=${offset}`);
    items.push(...(page.items || []));
    if (!page.items?.length || items.length >= page.total) return items;
  }
}
async function refreshFlights() {
  if (!state.token) { renderFlights(); return; }
  const button = $("refreshFlights"); button.disabled = true;
  try {
    const [flights, library] = await Promise.all([allFlights(), api("/v1/library")]);
    state.flights = flights; state.folders = library.folders; state.flightFolders = library.flight_folders; state.libraryReady = true;
    setExplorerNotice(""); setApi("online", "Session connected"); if (!state.upload) setMessage("Session connected. Choose a recorded log to process.", "success"); renderFlights(); $("emptyHint").textContent = "Choose a flight from the library or import a log.";
    if (!state.selectedFlight && state.flights.length) { const saved = new URL(location.href).searchParams.get("flight") || sessionStorage.getItem("wislSelectedFlight"); const initial = state.flights.find(f => f.id === saved) || state.flights.find(f => f.id === "flight-1a1b914dc70e6d0c1b45") || state.flights[0]; await selectFlight(initial.id); }
  } catch (error) { state.libraryReady = false; setApi("error", "Connection failed"); setExplorerNotice(friendlyError(error.message), true); els.flightMeta.textContent = friendlyError(error.message); renderFlights(); }
  finally { button.disabled = false; }
}
function evidenceText(incident) {
  const evidence = incident.evidence || incident.evidence_json;
  if (typeof evidence === "string") return evidence;
  if (evidence && typeof evidence === "object") {
    const recordedAt = evidence.position?.timestamp_utc || evidence.sample?.timestamp_utc;
    const warning = evidence.sample?.warning;
    const scalarFacts = Object.entries(evidence).filter(([key, value]) => key !== "hazard" && value !== null && typeof value !== "object").slice(0, 2).map(([key, value]) => `${label(key)}: ${value}`);
    return [recordedAt ? `recorded ${fmtTime(recordedAt)}` : null, warning ? `warning: ${warning}` : null, ...scalarFacts].filter(Boolean).join(" · ");
  }
  return incident.started_at ? `Recorded at ${fmtTime(incident.started_at)}` : "Recorded detector evidence";
}
function renderIncidents(items) {
  els.incidentList.replaceChildren(); els.incidentCount.textContent = String(items.length);
  if (!items.length) { els.incidentList.textContent = "No incidents were recorded for this flight."; els.incidentList.className = "incident-list empty-state"; return; }
  els.incidentList.className = "incident-list";
  items.forEach((incident) => {
    const article = document.createElement("article"); article.className = "incident";
    const severity = String(incident.severity || "notice").toLowerCase();
    article.innerHTML = `<div class="incident-top"><span class="severity ${escapeHtml(severity)}">${escapeHtml(severity)}</span><h3>${escapeHtml(label(incident.incident_type || incident.type))}</h3></div><p>${escapeHtml(incident.summary || "Detector event recorded in this log.")}</p><div class="evidence">${escapeHtml(evidenceText(incident))}</div>`;
    if (incident.started_at && (incident.flight_id || state.selectedFlight?.id)) {
      const replay = document.createElement("button");
      replay.type = "button";
      replay.className = "evidence-link";
      replay.textContent = "Replay this observation";
      replay.addEventListener("click", () => selectFlight(incident.flight_id || state.selectedFlight.id, incident.started_at));
      article.append(replay);
    }
    els.incidentList.append(article);
  });
}
function setReplay(flightId, timestamp = null) {
  const key = JSON.stringify([flightId, state.token]);
  if (state.replayKey === key && !timestamp) return;
  state.replayKey = key;
  if (state.replayToken === state.token && els.replayFrame.getAttribute("src")) {
    state.replaySelectionId = (state.replaySelectionId || 0) + 1;
    state.pendingReplaySelection = {type: "wisl:select-flight", flightId, timestamp, selectionId: state.replaySelectionId};
    els.replayFrame.contentWindow?.postMessage(state.pendingReplaySelection, location.origin);
    return;
  }
  state.replayToken = state.token;
  state.pendingReplaySelection = null;
  const frameUrl = new URL("/replay/", window.location.origin);
  frameUrl.searchParams.set("flights", flightId);
  frameUrl.searchParams.set("embed", "1");
  frameUrl.searchParams.set("workspace", workspaceRoute(location.hash).page);
  frameUrl.searchParams.set("v", "stream-25");
  if (state.token) frameUrl.searchParams.set("token", state.token);
  if (timestamp) frameUrl.searchParams.set("timestamp", timestamp);
  els.replayFrame.src = frameUrl.toString(); els.replayFrame.hidden = false; els.replayEmpty.hidden = true; els.openReplay.href = frameUrl.toString(); els.openReplay.classList.remove("disabled");
}
async function selectFlight(flightId, timestamp = null, {revealReplay = false} = {}) {
  if (timestamp || revealReplay) navigateWorkspace("replay");
  const flight = state.flights.find((item) => item.id === flightId) || { id: flightId };
  const version = ++state.selectionVersion;
  state.selectedFlight = flight; state.treeSelectedKey = `flight:${flightId}`;
  for (const folder of folderTrail(state.folders, state.flightFolders[flightId])) state.expandedFolders.add(folder.id);
  if (revealReplay || timestamp) { state.folderId = state.flightFolders[flightId] || null; sessionStorage.setItem("wislMissionFolder", state.folderId || ""); }
  rememberTree();
  state.treeFocusKey ||= state.treeSelectedKey;
  const url = new URL(location.href); url.searchParams.set("flight", flightId); history.replaceState({}, "", url);
  $("analysisFlightTitle").textContent = flightDisplayName(flight);
  $("workspaceTitle").textContent = logFilename(flight); $("workspaceTitle").title = logFilename(flight);
  sessionStorage.setItem("wislSelectedFlight", flightId); renderFlights(); setLibrary(false);
  els.analysisAnswer.textContent = "Ask about this mission or open an observation in replay."; renderLocalAnalysis(null);
  const provenance = simulationProvenance(flight); els.selectedFlightTitle.textContent = flightDisplayName(flight); els.selectedFlightTitle.title = flightDisplayName(flight); els.flightMeta.textContent = `${fmtTime(flight.started_at)}${flight.source ? ` · ${label(flight.source)}` : ""}${provenance ? ` · ${provenance}` : ""}`; els.incidentTitle.textContent = "Loading recorded evidence…"; els.incidentCount.textContent = "…";
  els.downloadReportButton.disabled = false;
  setReplay(flightId, timestamp);
  try {
    const [incidents, report] = await Promise.all([api(`/v1/flights/${encodeURIComponent(flightId)}/incidents`), api(`/v1/flights/${encodeURIComponent(flightId)}/incident-report`).catch(() => null)]);
    if (version !== state.selectionVersion) return;
    renderIncidents(incidents.items || []); els.incidentTitle.textContent = incidents.count === 1 ? "1 recorded incident" : `${incidents.count || 0} recorded incidents`;
    if (!modelConnectionTouched) { const status = modelStatus(state.demoStatus || report); els.modelState.textContent = modelDisplay(status); }
  } catch (error) { if (version !== state.selectionVersion) return; els.incidentTitle.textContent = "Evidence unavailable"; els.incidentList.textContent = friendlyError(error.message); els.incidentList.className = "incident-list empty-state error"; }
}
async function refreshPatterns() {
  if (!state.token) return;
  try {
    const body = await api("/v1/incidents/patterns?min_flights=2"); const items = body.items || []; els.patternList.replaceChildren();
    if (!items.length) { els.patternList.textContent = "No warning pattern currently repeats across two or more recorded flights."; els.patternList.className = "pattern-grid empty-state"; return; }
    els.patternList.className = "pattern-grid";
    for (const pattern of items) {
      const card = document.createElement("article"); card.className = "pattern";
      const affected = pattern.affected_flights || [];
      const shown = affected.slice(0, 4).map((f) => {
        const bits = [f.source_file, f.drone_model && f.aircraft_serial ? `${f.drone_model} S/N ${f.aircraft_serial}` : f.drone_model].filter(Boolean);
        return `<li>${escapeHtml(f.flight_id)}${bits.length ? ` &mdash; ${escapeHtml(bits.join(", "))}` : ""}</li>`;
      }).join("");
      const more = affected.length > 4 ? `<li class="fine-print">+${affected.length - 4} more</li>` : "";
      const flightsBlock = affected.length ? `<ul class="pattern-flights">${shown}${more}</ul>` : "";
      card.innerHTML = `<span class="severity ${escapeHtml(String(pattern.max_severity || "notice").toLowerCase())}">${escapeHtml(pattern.max_severity || "notice")}</span><h3>${escapeHtml(label(pattern.incident_type))}</h3><p>${escapeHtml(pattern.summary || "Recurring warning pattern across stored flights.")}</p><div class="pattern-meta"><span>${pattern.flight_count} flights</span><span>${pattern.incident_count} incidents</span></div>${flightsBlock}<button class="button" type="button">Create review bulletin</button>`;
      card.querySelector("button").addEventListener("click", () => createBulletin(pattern.signature, card.querySelector("button")));
      els.patternList.append(card);
    }
  } catch (error) { els.patternList.textContent = friendlyError(error.message); els.patternList.className = "pattern-grid empty-state error"; }
}
async function createBulletin(signature, button) { if (!signature) return; button.disabled = true; button.textContent = "Creating…"; try { await api("/v1/mitigation-bulletins", { method:"POST", json:true, body:JSON.stringify({ signature }) }); await refreshBulletins(); showView("bulletins"); } catch (error) { button.textContent = friendlyError(error.message); } finally { button.disabled = false; } }
async function refreshBulletins() { if (!state.token) return; try { const body = await api("/v1/mitigation-bulletins"); const items = body.items || []; els.bulletinList.replaceChildren(); if (!items.length) { els.bulletinList.textContent = "No reviewable bulletins have been created from recorded patterns."; els.bulletinList.className = "bulletin-list empty-state"; return; } els.bulletinList.className = "bulletin-list"; for (const bulletin of items) { const card = document.createElement("article"); card.className="bulletin"; const review = (bulletin.recommended_review || []).map((item) => `<li>${escapeHtml(item)}</li>`).join(""); card.innerHTML = `<div class="bulletin-header"><div><p class="eyebrow">${escapeHtml(bulletin.signature || "recorded pattern")}</p><h2>${escapeHtml(label(bulletin.incident_type))}</h2></div><span class="count-pill">${bulletin.flight_count || 0} flights</span></div><p>${escapeHtml(bulletin.evidence_summary || "Evidence from the recorded incident pattern.")}</p><ul>${review}</ul><p class="fine-print">${escapeHtml(bulletin.limitations || "For operator review only. This document does not modify aircraft.")}</p>`; els.bulletinList.append(card); } } catch (error) { els.bulletinList.textContent = friendlyError(error.message); els.bulletinList.className = "bulletin-list empty-state error"; } }
async function loadDemoStatus() {
  if (!state.token) return;
  try {
    state.demoStatus = await api("/v1/demo/status");
    if (!modelConnectionTouched) {
      const model = state.demoStatus.model;
      if (model?.base_url) $("modelUrl").value = model.base_url;
      if (model?.name) $("modelName").value = model.name;
    }
    await checkModelConnection();
  } catch { /* Demo status is optional while the platform endpoint is being added. */ }
}
function renderLocalAnalysis(result) {
  const view = localAnalysisView(result);
  if (!view) { els.localAnalysis.hidden = true; return; }
  const hypotheses = view.hypotheses.map((item) => `<li>${escapeHtml(item.analysis || "Analysis note")}${item.evidence_ids?.length ? ` <span class="evidence">[${escapeHtml(item.evidence_ids.join(", "))}]</span>` : ""}${item.follow_up ? `<br><span class="limitations">Follow up: ${escapeHtml(item.follow_up)}</span>` : ""}</li>`).join("");
  const limits = view.limitations.map((item) => escapeHtml(item)).join(" · ");
  const coverage = view.coverage ? `${view.coverage.included_flights ?? 0}/${view.coverage.total_flights ?? 0} flights · ${view.coverage.included_incidents ?? 0}/${view.coverage.total_incidents ?? 0} incidents` : "";
  const cached = view.cached ? `<p class="evidence">cached · generated ${escapeHtml(relativeTime(view.generated_at))}</p>` : "";
  els.localAnalysisBody.innerHTML = `${view.model ? `<p class="evidence">${escapeHtml(view.provider)} · ${escapeHtml(view.model)}</p>` : ""}${cached}<p>${escapeHtml(view.summary)}</p>${hypotheses ? `<ul>${hypotheses}</ul>` : ""}${limits ? `<p class="limitations">Limits: ${limits}</p>` : ""}${coverage ? `<p class="evidence">Scope: ${escapeHtml(coverage)}</p>` : ""}`;
  appendEvidenceLinks(els.localAnalysisBody, view.evidence);
  els.localAnalysis.hidden = false;
}
function appendEvidenceLinks(container, records = []) {
  const items = records.filter((item) => item && typeof item === "object" && item.flight_id);
  if (!items.length) return;
  const links = document.createElement("div"); links.className = "evidence-links";
  items.forEach((item) => { const link = document.createElement("a"); link.href = "#overview"; link.className = "evidence-link"; link.textContent = `${fmtTime(item.timestamp_utc)} · ${item.id || item.flight_id}`; link.addEventListener("click", (event) => { event.preventDefault(); selectFlight(item.flight_id, item.timestamp_utc); }); links.append(link); });
  container.append(links);
}
async function askQuestion(event) { event.preventDefault(); if (!state.token) { els.analysisAnswer.textContent = "Connect a session key to query recorded evidence."; return; } if (!state.selectedFlight?.id) { els.analysisAnswer.textContent = "Select a recorded flight before asking about what happened or where the evidence is."; return; } const question = els.question.value.trim(); if (!question) return; els.analysisAnswer.textContent = "Checking recorded evidence…"; const body = { question, flight_id: state.selectedFlight.id };
  try { const answer = await api("/v1/demo/query", { method:"POST", json:true, body:JSON.stringify(body) }); els.analysisAnswer.textContent = queryText(answer); appendEvidenceLinks(els.analysisAnswer, answer.evidence); } catch (error) { els.analysisAnswer.textContent = friendlyError(error.message); } }
async function downloadComprehensiveReport() {
  if (!state.token) { setAuthPanel(true); return; }
  const flightId = state.selectedFlight?.id;
  if (!flightId) return;
  const button = els.downloadReportButton;
  const originalText = button.textContent;
  button.disabled = true; button.textContent = "Building PDF…";
  try {
    const created = await api(`/v1/flights/${encodeURIComponent(flightId)}/comprehensive-report`, { method: "POST" });
    const response = await fetch(`/v1/comprehensive-reports/${encodeURIComponent(created.id)}/file`, { headers: authHeaders() });
    if (!response.ok) throw new Error("The comprehensive PDF could not be downloaded.");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = `${flightId}-comprehensive-report.pdf`;
    document.body.append(link); link.click(); link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    setMessage(friendlyError(error.message), "error");
  } finally {
    button.disabled = false; button.textContent = originalText;
  }
}
let modelConnectionTouched = false, modelConnectionChecking = false, analysisController = null;
function modelConnection() {
  return { provider: $("modelProvider").value, base_url: $("modelUrl").value.trim(), model: $("modelName").value.trim(), api_key: $("modelApiKey").value };
}
function rememberModelConnection() {
  const { api_key, ...connection } = modelConnection();
  sessionStorage.setItem("wislModelConnection", JSON.stringify(connection));
}
async function checkModelConnection(event) {
  event?.preventDefault();
  if (!state.token) { setAuthPanel(true); return; }
  if (modelConnectionChecking || analysisController) return;
  const fields = $("modelConnectionFields"), button = $("checkModelButton");
  const connection = modelConnection();
  const useDefault = usesDefaultModel(connection, state.demoStatus?.model);
  modelConnectionTouched = true; modelConnectionChecking = true;
  fields.disabled = true; button.textContent = "Connecting…"; $("fleetAnalysisButton").disabled = true;
  $("modelConnectionStatus").textContent = useDefault ? "Connecting the laptop's default model. Starting Ollama and loading the model if needed…" : "Contacting the local server…";
  try {
    const result = useDefault
      ? await api("/v1/demo/model/connect", { method: "POST" })
      : await api("/v1/demo/model/check", { method: "POST", json: true, body: JSON.stringify(connection) });
    $("modelOptions").replaceChildren(...(result.models || []).map(name => { const option = document.createElement("option"); option.value = name; return option; }));
    if (!connection.model && result.models?.length) $("modelName").value = result.models[0];
    const available = result.status === "ready" || result.status === "available";
    $("modelConnectionStatus").textContent = result.warmed ? result.message : available ? `Connected · ${result.models.length} model(s) listed. Selected: ${$("modelName").value}.` : result.status === "missing" && connection.model ? `Server reachable, but "${connection.model}" is not listed. Choose a listed model or load it in your server.` : result.message;
    els.modelState.textContent = available ? "Local model connected. Output still requires human review." : "Model connection needs attention; recorded evidence is unaffected.";
    rememberModelConnection();
  } catch (error) { $("modelConnectionStatus").textContent = friendlyError(error.message); }
  finally { modelConnectionChecking = false; fields.disabled = false; button.textContent = "Check connection & list models"; $("fleetAnalysisButton").disabled = false; }
}
function setModelProgress(stage) {
  $("modelProgress").hidden = false;
  $("modelProgressText").textContent = modelProgressText(stage);
}
async function streamFleetAnalysis(question, signal) {
  const response = await fetch("/v1/demo/analysis/stream", { method: "POST", headers: authHeaders(true), signal,
    body: JSON.stringify({ question, connection: modelConnection(), fresh: $("freshAnalysis").checked }) });
  if (!response.ok) throw new Error(detail(await response.json().catch(() => ({}))));
  if (!response.body) throw new Error("This browser did not provide an analysis stream. Try another browser.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "", raw = "", final = null;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop();
      if (done && buffer.trim()) parts.push(buffer);
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        const payload = JSON.parse(line.slice(5));
        if (payload.stage) setModelProgress(payload.stage);
        if (payload.delta) { raw += payload.delta; $("modelDraft").hidden = false; $("modelDraftText").textContent = raw; }
        if (payload.final) final = payload.final;
      }
      if (done) break;
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
  if (!final) throw new Error("The stream ended without a validated answer. Check the model server and retry.");
  return final;
}
async function analyzeFleetRecords() {
  if (!state.token) { setAuthPanel(true); return; }
  if (!$("modelConnectionForm").reportValidity()) return;
  if (!$("modelName").value.trim()) { $("modelConnectionStatus").textContent = "Check the connection and choose a model first."; $("modelName").focus(); return; }
  if (analysisController) return;
  const button = $("fleetAnalysisButton");
  const question = els.question.value.trim() || "Summarize recurring patterns and evidence across stored flights.";
  analysisController = new AbortController();
  const started = Date.now();
  let timedOut = false;
  const elapsed = () => { $("modelElapsed").textContent = `${Math.floor((Date.now() - started) / 1000)}s elapsed`; };
  elapsed();
  const timer = setInterval(elapsed, 1000);
  const deadline = setTimeout(() => { timedOut = true; analysisController?.abort(); }, ((state.demoStatus?.analysis_timeout_seconds || 120) + 15) * 1000);
  button.disabled = true; button.textContent = "Analyzing…";
  $("modelConnectionFields").disabled = true; $("cancelAnalysisButton").hidden = false;
  $("modelProgress").querySelector("progress").hidden = false;
  els.localAnalysis.hidden = true; $("modelDraft").hidden = true; $("modelDraftText").textContent = "";
  setModelProgress("connecting"); rememberModelConnection();
  try {
    const result = await streamFleetAnalysis(question, analysisController.signal);
    renderLocalAnalysis(result);
    setModelProgress(result.cached ? "cached" : result.status === "generated" ? "complete" : "unavailable");
    if (result.status !== "generated") { $("modelDraft").hidden = true; $("modelDraftText").textContent = ""; }
  } catch (error) {
    $("modelProgressText").textContent = error.name === "AbortError" ? (timedOut ? "Timed out waiting for the model. Try a smaller model or check the server." : "Stopped waiting. Your model server may still be finishing its request.") : friendlyError(error.message);
    $("modelDraft").hidden = true; $("modelDraftText").textContent = "";
  } finally {
    clearInterval(timer); clearTimeout(deadline); analysisController = null;
    $("modelConnectionFields").disabled = false; $("cancelAnalysisButton").hidden = true;
    $("modelProgress").querySelector("progress").hidden = true;
    button.disabled = false; button.textContent = "Analyze fleet records";
  }
}
function navigateWorkspace(page, tab = "overview") {
  const route = page === "analysis" ? `#/analysis/${tab}` : "#/replay";
  if (location.hash !== route) history.pushState({}, "", route);
  renderWorkspaceRoute();
}
function notifyReplayVisibility() {
  els.replayFrame.contentWindow?.postMessage({type: "wisl:workspace-visibility", visible: workspaceRoute(location.hash).page === "replay"}, location.origin);
}
function renderWorkspaceRoute() {
  const route = workspaceRoute(location.hash), previous = document.body.dataset.workspacePage;
  document.body.dataset.workspacePage = route.page;
  $("analysisPage").hidden = route.page !== "analysis";
  const replay = document.querySelector(".replay-stage");
  replay.inert = route.page === "analysis"; replay.setAttribute("aria-hidden", String(replay.inert));
  if (route.page === "analysis") showView(route.tab, false);
  const requested = new URL(location.href).searchParams.get("flight");
  if (state.libraryReady && requested && requested !== state.selectedFlight?.id && state.flights.some(flight => flight.id === requested)) void selectFlight(requested);
  notifyReplayVisibility();
  if (previous !== route.page) {
    if (route.page === "analysis") $(`tab-${route.tab}`).focus({preventScroll: true});
    else if (!els.replayFrame.hidden) els.replayFrame.focus({preventScroll: true});
  }
}
function showView(view, changeRoute = true) {
  if (changeRoute) { navigateWorkspace("analysis", view); return; }
  document.querySelectorAll(".view").forEach(el => { const active = el.id === `${view}View`; el.classList.toggle("active", active); el.hidden = !active; });
  document.querySelectorAll(".nav-link").forEach(el => { const active = el.dataset.view === view; el.classList.toggle("active", active); el.setAttribute("aria-selected", String(active)); el.tabIndex = active ? 0 : -1; });
  document.querySelector(".dock-content").scrollTop = 0;
  if (view === "patterns") refreshPatterns();
  if (view === "bulletins") refreshBulletins();
}
function setLibrary(open) { const visible = open || wideLayout.matches; $("flightLibrary").hidden = !visible; $("libraryButton").setAttribute("aria-expanded", String(visible)); if (open) { setAuthPanel(false); $("missionSearch").focus(); } }
wideLayout.addEventListener("change", () => setLibrary(false));
function setAuthPanel(open) { $("authPanel").hidden = !open; $("authButton").setAttribute("aria-expanded", String(open)); if (open) { setLibrary(false); els.token.focus(); } }
async function waitForUpload(uploadId) {
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    let upload;
    try { upload = await api(`/v1/uploads/${encodeURIComponent(uploadId)}`); }
    catch { upload = await api(`/v1/logs/${encodeURIComponent(uploadId)}/status`); }
    if (uploadComplete(upload.status)) return upload;
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  throw new Error("Demo log processing timed out.");
}

async function seedDemoLibrary() {
  if (!state.token || state.seedingLibrary) return;
  const already = new Set(state.flights.flatMap((flight) => [flight.original_filename, flight.filename, flight.upload_filename].filter(Boolean)));
  const pending = DEMO_LIBRARY_LOGS.filter((item) => !already.has(item.name));
  if (!pending.length) return;
  state.seedingLibrary = true;
  setApi("", "Loading demo missions…");
  try {
    let firstId = null;
    for (const item of pending) {
      const response = await fetch(item.url);
      if (!response.ok) throw new Error(`The demo log ${item.name} could not be loaded.`);
      const data = new FormData();
      data.append("file", new File([await response.blob()], item.name, { type: item.type }));
      const uploaded = await fetch("/v1/logs/upload", { method: "POST", headers: authHeaders(), body: data });
      const body = await uploaded.json().catch(() => ({}));
      if (!uploaded.ok) throw new Error(detail(body));
      const ready = await waitForUpload(body.upload_id);
      if (ready.status === "failed") throw new Error(ready.error || `${item.name} could not be processed.`);
      if (ready.flight_id && !firstId) firstId = ready.flight_id;
    }
    await refreshFlights();
    if (firstId && !state.selectedFlight) await selectFlight(firstId);
    setApi("online", "Demo missions ready");
  } catch (error) {
    setApi("error", friendlyError(error.message));
  } finally {
    state.seedingLibrary = false;
  }
}

async function connect() {
  state.token = els.token.value.trim();
  if (!state.token) return;
  sessionStorage.setItem("wislDemoToken", state.token); setAuthPanel(false); setApi("", "Connecting…");
  await Promise.all([refreshFlights(), refreshPatterns(), refreshBulletins(), loadDemoStatus()]);
  await seedDemoLibrary();
}
// ---- Resizable file explorer --------------------------------------------
// The explorer's width drives a CSS variable on the workspace; replay takes
// whatever is left, so moving the divider resizes the visualisation instead
// of pushing it off-screen. Width is remembered for the browser session.
const SIDEBAR_DEFAULT_W = 280, SIDEBAR_KEY = "wislSidebarWidth";
const workspaceEl = document.querySelector(".workspace");
function currentSidebarWidth() { return parseInt(workspaceEl.style.getPropertyValue("--sidebar-w"), 10) || SIDEBAR_DEFAULT_W; }
function setSidebarWidth(px, persist = true) {
  const viewport = wideLayout.matches ? window.innerWidth : 1200;
  const width = sidebarWidth(px, viewport);
  workspaceEl.style.setProperty("--sidebar-w", `${width}px`);
  $("sidebarResizer").setAttribute("aria-valuenow", String(width));
  $("sidebarResizer").setAttribute("aria-valuemax", String(sidebarWidth(520, viewport)));
  if (persist) { try { sessionStorage.setItem(SIDEBAR_KEY, String(width)); } catch { /* private mode */ } }
}
(function initSidebarResizer() {
  const handle = $("sidebarResizer");
  handle.setAttribute("aria-valuemin", "190");
  const saved = Number(sessionStorage.getItem(SIDEBAR_KEY));
  setSidebarWidth(Number.isFinite(saved) && saved > 0 ? saved : SIDEBAR_DEFAULT_W, false);

  let startX = 0, startWidth = 0;
  const onMove = event => setSidebarWidth(startWidth + event.clientX - startX);
  const onUp = event => {
    handle.releasePointerCapture?.(event.pointerId);
    document.body.classList.remove("sidebar-resizing");
    handle.removeEventListener("pointermove", onMove);
    handle.removeEventListener("pointerup", onUp);
    handle.removeEventListener("pointercancel", onUp);
  };
  handle.addEventListener("pointerdown", event => {
    if (event.button !== 0) return;
    event.preventDefault(); startX = event.clientX; startWidth = currentSidebarWidth();
    // Pointer capture keeps events coming to the handle even as the cursor
    // crosses the replay iframe, which would otherwise swallow them.
    handle.setPointerCapture?.(event.pointerId);
    document.body.classList.add("sidebar-resizing");
    handle.addEventListener("pointermove", onMove);
    handle.addEventListener("pointerup", onUp);
    handle.addEventListener("pointercancel", onUp);
  });
  handle.addEventListener("dblclick", () => setSidebarWidth(SIDEBAR_DEFAULT_W));
  handle.addEventListener("keydown", event => {
    const step = event.shiftKey ? 64 : 16;
    const actions = {
      ArrowRight: () => setSidebarWidth(currentSidebarWidth() + step),
      ArrowLeft: () => setSidebarWidth(currentSidebarWidth() - step),
      Home: () => setSidebarWidth(190),
      End: () => setSidebarWidth(520),
    };
    if (actions[event.key]) { event.preventDefault(); actions[event.key](); }
  });
  // Re-clamp if the window shrinks so the explorer never crowds out the stage.
  window.addEventListener("resize", () => { if (wideLayout.matches) setSidebarWidth(currentSidebarWidth(), false); });
})();

$("authButton").addEventListener("click", () => setAuthPanel($("authPanel").hidden));
$("saveToken").addEventListener("click", connect);
els.token.addEventListener("keydown", event => { if (event.key === "Enter") connect(); });
$("clearToken").addEventListener("click", () => { sessionStorage.removeItem("wislDemoToken"); sessionStorage.removeItem("sdthReplayToken"); sessionStorage.removeItem("wislSelectedFlight"); window.location.reload(); });
$("libraryButton").addEventListener("click", () => setLibrary($("flightLibrary").hidden));
$("emptyLibraryButton").addEventListener("click", () => state.token ? setLibrary(true) : setAuthPanel(true));
$("closeLibrary").addEventListener("click", () => setLibrary(false));
function openImport() { setLibrary(false); showView("logs"); $("dropzone").scrollIntoView({block:"nearest",behavior:"smooth"}); }
$("importButton").addEventListener("click", openImport);
$("sidebarImport").addEventListener("click", openImport);
$("missionSearch").addEventListener("input", renderFlights);
$("newFolder").addEventListener("click", () => openExplorerDialog("new"));
$("folderUp").addEventListener("click", () => openFolder(state.folders.find(folder => folder.id === state.folderId)?.parent_id || null));
$("explorerRoot").addEventListener("click", () => openFolder(null));
folderDropTarget($("explorerRoot"), null);
els.flightList.addEventListener("keydown", navigateTree);
$("backToReplay").addEventListener("click", () => navigateWorkspace("replay"));
els.replayFrame.addEventListener("load", notifyReplayVisibility);
window.addEventListener("popstate", renderWorkspaceRoute);
window.addEventListener("hashchange", renderWorkspaceRoute);
window.addEventListener("message", event => {
  if (event.origin !== location.origin || event.source !== els.replayFrame.contentWindow) return;
  if (event.data?.type === "wisl:open-analysis") { setLibrary(false); navigateWorkspace("analysis"); }
  if (event.data?.type === "wisl:replay-ready") notifyReplayVisibility();
  if (event.data?.type === "wisl:replay-initialized") {
    if (state.pendingReplaySelection) els.replayFrame.contentWindow.postMessage(state.pendingReplaySelection, location.origin);
    notifyReplayVisibility();
  }
  if (event.data?.type === "wisl:replay-error" && event.data.selectionId === state.pendingReplaySelection?.selectionId) {
    state.replayKey = null; setExplorerNotice(friendlyError(event.data.message), true);
  }
});
$("explorerForm").addEventListener("submit", saveExplorer);
$("cancelExplorer").addEventListener("click", () => $("explorerDialog").close());
$("explorerDialog").addEventListener("cancel", event => { if (state.libraryBusy) event.preventDefault(); });
$("sampleButton").addEventListener("click", async () => {
  if (!state.token) { setAuthPanel(true); return; }
  const button = $("sampleButton"); button.disabled = true;
  try { const response = await fetch("/demo/fixtures/dji_csv_gps_jamming.csv"); if (!response.ok) throw new Error("The included sample could not be loaded."); await uploadFile(new File([await response.blob()], "dji_csv_gps_jamming.csv", {type:"text/csv"})); }
  catch (error) { setMessage(friendlyError(error.message), "error"); }
  finally { button.disabled = false; }
});
document.addEventListener("keydown", event => { if (event.key === "Escape" && !$("explorerDialog").open) { setLibrary(false); setAuthPanel(false); } });
document.addEventListener("click", event => {
  const path = event.composedPath();
  if (!$("explorerDialog").open && !$("flightLibrary").hidden && ![$("explorerDialog"), $("flightLibrary"), $("libraryButton"), $("emptyLibraryButton")].some(node => path.includes(node))) setLibrary(false);
});
els.file.addEventListener("change", () => { uploadFile(els.file.files[0]); els.file.value = ""; });
["dragenter","dragover"].forEach(type => $("dropzone").addEventListener(type, event => { event.preventDefault(); $("dropzone").classList.add("dragover"); }));
["dragleave","drop"].forEach(type => $("dropzone").addEventListener(type, event => { event.preventDefault(); $("dropzone").classList.remove("dragover"); }));
$("dropzone").addEventListener("drop", event => uploadFile(event.dataTransfer.files[0]));
$("refreshFlights").addEventListener("click", refreshFlights);
$("questionForm").addEventListener("submit", askQuestion);
$("fleetAnalysisButton").addEventListener("click", analyzeFleetRecords);
$("modelConnectionForm").addEventListener("submit", checkModelConnection);
$("defaultModelButton").addEventListener("click", async () => {
  if (!state.token) { setAuthPanel(true); return; }
  modelConnectionTouched = false;
  sessionStorage.removeItem("wislModelConnection");
  $("modelProvider").value = "ollama"; $("modelApiKey").value = "";
  await loadDemoStatus();
});
$("modelConnectionForm").addEventListener("input", () => { modelConnectionTouched = true; els.modelState.textContent = "Connection settings changed. Check the connection before analyzing."; });
$("modelProvider").addEventListener("change", () => {
  $("modelUrl").value = $("modelProvider").value === "ollama" ? "http://127.0.0.1:11434" : "http://127.0.0.1:1234/v1";
  $("modelName").value = ""; $("modelApiKey").value = ""; $("modelOptions").replaceChildren();
  $("modelConnectionStatus").textContent = "Enter your server URL, then check the connection.";
});
$("cancelAnalysisButton").addEventListener("click", () => analysisController?.abort());
try {
  const saved = JSON.parse(sessionStorage.getItem("wislModelConnection"));
  if (saved && ["ollama", "openai"].includes(saved.provider) && typeof saved.base_url === "string") {
    $("modelProvider").value = saved.provider; $("modelUrl").value = saved.base_url; $("modelName").value = saved.model || "";
    modelConnectionTouched = true;
    els.modelState.textContent = "Saved connection restored. Check it to confirm the model is available.";
  }
} catch { sessionStorage.removeItem("wislModelConnection"); }
els.downloadReportButton.addEventListener("click", downloadComprehensiveReport);
document.querySelectorAll(".query-presets button").forEach(button => button.addEventListener("click", () => { els.question.value = button.dataset.query; $("questionForm").requestSubmit(); }));
const tabs = [...document.querySelectorAll(".nav-link")];
tabs.forEach((button,index) => {
  button.addEventListener("click", () => showView(button.dataset.view));
  button.addEventListener("keydown", event => { const target = event.key === "ArrowRight" ? (index+1)%tabs.length : event.key === "ArrowLeft" ? (index+tabs.length-1)%tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length-1 : null; if (target !== null) { event.preventDefault(); tabs[target].focus(); showView(tabs[target].dataset.view); } });
});
try {
  const expanded = JSON.parse(sessionStorage.getItem("wislExpandedFolders") || "[]");
  if (Array.isArray(expanded)) state.expandedFolders = new Set(expanded.filter(id => typeof id === "string"));
} catch {}
setLibrary(false);
renderWorkspaceRoute();
els.token.value = state.token; pipeline("", "No log is being processed.");
if (state.token) { setApi("", "Connecting…"); refreshFlights().then(() => Promise.all([refreshPatterns(), refreshBulletins(), loadDemoStatus(), seedDemoLibrary()])); } else renderFlights();
