import { flightDisplayName, localAnalysisView, modelDisplay, modelStatus, queryText, simulationProvenance } from "./demo-contract.mjs?v=stream-12";

const state = { token: sessionStorage.getItem("wislDemoToken") || "", flights: [], selectedFlight: null, upload: null, pollTimer: null, demoStatus: null, selectionVersion: 0, seedingLibrary: false };
const DEMO_LIBRARY_LOGS = [
  { url: "/demo/fixtures/dji_csv_gps_jamming.csv", name: "dji_csv_gps_jamming.csv", type: "text/csv" },
  { url: "/demo/fixtures/orbiter4_gps_denied_frozen.json", name: "orbiter4_gps_denied_frozen.json", type: "application/json" },
  { url: "/demo/fixtures/dji_csv_v2_normal_control.csv", name: "dji_csv_v2_normal_control.csv", type: "text/csv" },
  { url: "/demo/fixtures/dji_csv_logger_dropout_025.csv", name: "dji_csv_logger_dropout_025.csv", type: "text/csv" },
  { url: "/demo/fixtures/dji_csv_lost_airborne_026.csv", name: "dji_csv_lost_airborne_026.csv", type: "text/csv" },
  { url: "/demo/fixtures/dji_csv_motor_fail_recover_024.csv", name: "dji_csv_motor_fail_recover_024.csv", type: "text/csv" },
  { url: "/demo/fixtures/dji_csv_gps_denied_frozen_023.csv", name: "dji_csv_gps_denied_frozen_023.csv", type: "text/csv" },
  { url: "/demo/fixtures/dji_csv_gps_jamming_022.csv", name: "dji_csv_gps_jamming_022.csv", type: "text/csv" },
  { url: "/demo/fixtures/dji_csv_gps_weak_midair_end_028.csv", name: "dji_csv_gps_weak_midair_end_028.csv", type: "text/csv" },
  { url: "/demo/fixtures/dji_csv_battery_critical_021.csv", name: "dji_csv_battery_critical_021.csv", type: "text/csv" },
  { url: "/demo/fixtures/dji_csv_battery_critical_logger_dropout_027.csv", name: "dji_csv_battery_critical_logger_dropout_027.csv", type: "text/csv" },
  { url: "/demo/fixtures/dji_csv_supplemental_normal_control.csv", name: "dji_csv_supplemental_normal_control.csv", type: "text/csv" },
  { url: "/demo/fixtures/dji_csv_supplemental_gps_weak_recurrence.csv", name: "dji_csv_supplemental_gps_weak_recurrence.csv", type: "text/csv" },
];
const $ = (id) => document.getElementById(id);
const wideLayout = window.matchMedia("(min-width: 760px)");
const els = { apiDot: $("apiDot"), apiState: $("apiState"), authPanel: $("authPanel"), token: $("tokenInput"), uploadMessage: $("uploadMessage"), uploadStatus: $("uploadStatus"), traceDetail: $("traceDetail"), file: $("logFile"), flightList: $("flightList"), flightMeta: $("flightMeta"), selectedFlightTitle: $("selectedFlightTitle"), incidentTitle: $("incidentTitle"), incidentCount: $("incidentCount"), incidentList: $("incidentList"), modelState: $("modelState"), replayEmpty: $("replayEmpty"), replayFrame: $("replayFrame"), openReplay: $("openReplay"), patternList: $("patternList"), bulletinList: $("bulletinList"), analysisAnswer: $("analysisAnswer"), question: $("questionInput"), localAnalysis: $("localAnalysis"), localAnalysisBody: $("localAnalysisBody"), downloadReportButton: $("downloadReportButton") };

function authHeaders(json = false) { const headers = state.token ? { Authorization: `Bearer ${state.token}` } : {}; return json ? { ...headers, "Content-Type": "application/json" } : headers; }
function detail(error) { return error?.detail || error?.message || "The request could not be completed."; }
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
    if (upload.status === "failed") { setMessage(friendlyError(upload.error) || "The log could not be processed.", "error"); return; }
    if (upload.status === "ready") {
      setMessage(upload.duplicate ? "Duplicate found. The earlier processed log is ready." : "The log has been processed and is ready for review.", "success");
      await refreshFlights();
      if (upload.flight_id) { await selectFlight(upload.flight_id); showView("overview"); }
      return;
    }
    state.pollTimer = setTimeout(() => pollUpload(uploadId), 1400);
  } catch (error) { const msg = friendlyError(error.message); setMessage(msg, "error"); pipeline("failed", msg); }
}
async function uploadFile(file) {
  if (!state.token) { setMessage("Add a session key before uploading.", "error"); setAuthPanel(true); return; }
  if (!file) return;
  if (file.size > 100 * 1024 * 1024) { setMessage("Choose a file smaller than 100 MB.", "error"); return; }
  const data = new FormData(); data.append("file", file);
  setMessage(`Uploading ${file.name}…`); pipeline("received", "Uploading your log…");
  try {
    const response = await fetch("/v1/logs/upload", { method: "POST", headers: authHeaders(), body: data });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(detail(body));
    state.upload = body;
    setMessage(body.duplicate ? "A matching log already exists; checking its status…" : "Log accepted. Tracking its progress below.");
    pollUpload(body.upload_id);
  } catch (error) { const msg = friendlyError(error.message); setMessage(msg, "error"); pipeline("failed", msg); }
}
function renderFlights() {
  els.flightList.replaceChildren();
  $("libraryCount").textContent = String(state.flights.length).padStart(2, "0");
  if (!state.flights.length) { els.flightList.textContent = state.token ? "No recorded flights are available yet." : "Connect a session to load recorded flights."; els.flightList.className = "flight-list empty-state"; return; }
  els.flightList.className = "flight-list";
  const search = $("missionSearch").value.trim().toLowerCase();
  const matching = state.flights.filter(flight => `${flightDisplayName(flight)} ${flight.source || ""} ${flight.original_filename || ""}`.toLowerCase().includes(search));
  if (!matching.length) { els.flightList.textContent = "No matching missions. Try a different search."; return; }
  for (const flight of matching) {
    const node = $("flightTemplate").content.firstElementChild.cloneNode(true);
    node.classList.toggle("selected", flight.id === state.selectedFlight?.id);
    node.setAttribute("aria-pressed", String(flight.id === state.selectedFlight?.id));
    node.querySelector(".flight-source").textContent = flightDisplayName(flight);
    node.querySelector(".flight-time").textContent = fmtTime(flight.started_at);
    node.addEventListener("click", () => selectFlight(flight.id));
    els.flightList.append(node);
  }
  if (!search) els.flightList.querySelector(".selected")?.scrollIntoView({block:"nearest"});
}
async function refreshFlights() {
  if (!state.token) { renderFlights(); return; }
  const button = $("refreshFlights"); button.disabled = true;
  try { const result = await api("/v1/flights?limit=50"); state.flights = result.items || []; setApi("online", "Session connected"); if (!state.upload) setMessage("Session connected. Choose a recorded log to process.", "success"); renderFlights(); $("emptyHint").textContent = "Choose a flight from the library or import a log.";
    if (!state.selectedFlight && state.flights.length) { const saved = sessionStorage.getItem("wislSelectedFlight"); const initial = state.flights.find(f => f.id === saved) || state.flights.find(f => f.id === "flight-1a1b914dc70e6d0c1b45") || state.flights[0]; await selectFlight(initial.id); } }
  catch (error) { setApi("error", "Connection failed"); els.flightMeta.textContent = friendlyError(error.message); }
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
  const frameUrl = new URL("/replay/", window.location.origin);
  frameUrl.searchParams.set("flights", flightId);
  frameUrl.searchParams.set("embed", "1");
  frameUrl.searchParams.set("v", "stream-3");
  if (state.token) frameUrl.searchParams.set("token", state.token);
  if (timestamp) frameUrl.searchParams.set("timestamp", timestamp);
  els.replayFrame.src = frameUrl.toString(); els.replayFrame.hidden = false; els.replayEmpty.hidden = true; els.openReplay.href = frameUrl.toString(); els.openReplay.classList.remove("disabled");
}
async function selectFlight(flightId, timestamp = null) {
  const flight = state.flights.find((item) => item.id === flightId) || { id: flightId };
  const version = ++state.selectionVersion;
  state.selectedFlight = flight; sessionStorage.setItem("wislSelectedFlight", flightId); renderFlights(); setLibrary(false);
  els.analysisAnswer.textContent = "Ask about this mission or open an observation in replay."; renderLocalAnalysis(null);
  const provenance = simulationProvenance(flight); els.selectedFlightTitle.textContent = flightDisplayName(flight); els.selectedFlightTitle.title = flightDisplayName(flight); els.flightMeta.textContent = `${fmtTime(flight.started_at)}${flight.source ? ` · ${label(flight.source)}` : ""}${provenance ? ` · ${provenance}` : ""}`; els.incidentTitle.textContent = "Loading recorded evidence…"; els.incidentCount.textContent = "…";
  els.downloadReportButton.disabled = false;
  setReplay(flightId, timestamp);
  try {
    const [incidents, report] = await Promise.all([api(`/v1/flights/${encodeURIComponent(flightId)}/incidents`), api(`/v1/flights/${encodeURIComponent(flightId)}/incident-report`).catch(() => null)]);
    if (version !== state.selectionVersion) return;
    renderIncidents(incidents.items || []); els.incidentTitle.textContent = incidents.count === 1 ? "1 recorded incident" : `${incidents.count || 0} recorded incidents`;
    const status = modelStatus(state.demoStatus || report); els.modelState.textContent = modelDisplay(status);
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
async function loadDemoStatus() { if (!state.token) return; try { state.demoStatus = await api("/v1/demo/status"); els.modelState.textContent = modelDisplay(modelStatus(state.demoStatus)); } catch { /* Demo status is optional while the platform endpoint is being added. */ } }
function renderLocalAnalysis(result) {
  const view = localAnalysisView(result);
  if (!view) { els.localAnalysis.hidden = true; return; }
  const hypotheses = view.hypotheses.map((item) => `<li>${escapeHtml(item.analysis || "Analysis note")}${item.evidence_ids?.length ? ` <span class="evidence">[${escapeHtml(item.evidence_ids.join(", "))}]</span>` : ""}${item.follow_up ? `<br><span class="limitations">Follow up: ${escapeHtml(item.follow_up)}</span>` : ""}</li>`).join("");
  const limits = view.limitations.map((item) => escapeHtml(item)).join(" · ");
  const coverage = view.coverage ? `${view.coverage.included_flights ?? 0}/${view.coverage.total_flights ?? 0} flights · ${view.coverage.included_incidents ?? 0}/${view.coverage.total_incidents ?? 0} incidents` : "";
  els.localAnalysisBody.innerHTML = `<p>${escapeHtml(view.summary)}</p>${hypotheses ? `<ul>${hypotheses}</ul>` : ""}${limits ? `<p class="limitations">Limits: ${limits}</p>` : ""}${coverage ? `<p class="evidence">Scope: ${escapeHtml(coverage)}</p>` : ""}`;
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
async function analyzeFleetRecords() { if (!state.token) { els.localAnalysis.hidden = true; els.analysisAnswer.textContent = "Connect a session key to analyze stored fleet records."; return; } const button = $("fleetAnalysisButton"); const question = els.question.value.trim() || "Summarize recurring patterns and evidence across stored flights."; button.disabled = true; button.textContent = "Analyzing…"; els.localAnalysis.hidden = true; try { const result = await api("/v1/demo/analysis", { method:"POST", json:true, body:JSON.stringify({ question }) }); renderLocalAnalysis(result); } catch (error) { els.analysisAnswer.textContent = friendlyError(error.message); } finally { button.disabled = false; button.textContent = "Analyze fleet records"; } }
function showView(view) {
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
$("sampleButton").addEventListener("click", async () => {
  if (!state.token) { setAuthPanel(true); return; }
  const button = $("sampleButton"); button.disabled = true;
  try { const response = await fetch("/demo/fixtures/dji_csv_gps_jamming.csv"); if (!response.ok) throw new Error("The included sample could not be loaded."); await uploadFile(new File([await response.blob()], "dji_csv_gps_jamming.csv", {type:"text/csv"})); }
  catch (error) { setMessage(friendlyError(error.message), "error"); }
  finally { button.disabled = false; }
});
document.addEventListener("keydown", event => { if (event.key === "Escape") { setLibrary(false); setAuthPanel(false); } });
document.addEventListener("click", event => { if (!$("flightLibrary").hidden && !$("flightLibrary").contains(event.target) && !$("libraryButton").contains(event.target) && event.target !== $("emptyLibraryButton")) setLibrary(false); });
els.file.addEventListener("change", () => { uploadFile(els.file.files[0]); els.file.value = ""; });
["dragenter","dragover"].forEach(type => $("dropzone").addEventListener(type, event => { event.preventDefault(); $("dropzone").classList.add("dragover"); }));
["dragleave","drop"].forEach(type => $("dropzone").addEventListener(type, event => { event.preventDefault(); $("dropzone").classList.remove("dragover"); }));
$("dropzone").addEventListener("drop", event => uploadFile(event.dataTransfer.files[0]));
$("refreshFlights").addEventListener("click", refreshFlights);
$("questionForm").addEventListener("submit", askQuestion);
$("fleetAnalysisButton").addEventListener("click", analyzeFleetRecords);
els.downloadReportButton.addEventListener("click", downloadComprehensiveReport);
document.querySelectorAll(".query-presets button").forEach(button => button.addEventListener("click", () => { els.question.value = button.dataset.query; $("questionForm").requestSubmit(); }));
const tabs = [...document.querySelectorAll(".nav-link")];
tabs.forEach((button,index) => {
  button.addEventListener("click", () => showView(button.dataset.view));
  button.addEventListener("keydown", event => { const target = event.key === "ArrowRight" ? (index+1)%tabs.length : event.key === "ArrowLeft" ? (index+tabs.length-1)%tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length-1 : null; if (target !== null) { event.preventDefault(); tabs[target].focus(); showView(tabs[target].dataset.view); } });
});
setLibrary(false);
els.token.value = state.token; pipeline("", "No log is being processed.");
if (state.token) { setApi("", "Connecting…"); refreshFlights().then(() => Promise.all([refreshPatterns(), refreshBulletins(), loadDemoStatus(), seedDemoLibrary()])); } else renderFlights();
