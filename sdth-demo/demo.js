import { flightDisplayName, localAnalysisView, modelDisplay, modelStatus, queryText, simulationProvenance } from "./demo-contract.mjs?v=studio-5";

const state = { token: sessionStorage.getItem("wislDemoToken") || "", flights: [], selectedFlight: null, upload: null, pollTimer: null, demoStatus: null, selectionVersion: 0 };
const $ = (id) => document.getElementById(id);
const els = { apiDot: $("apiDot"), apiState: $("apiState"), authPanel: $("authPanel"), token: $("tokenInput"), uploadMessage: $("uploadMessage"), uploadStatus: $("uploadStatus"), traceDetail: $("traceDetail"), file: $("logFile"), flightList: $("flightList"), flightMeta: $("flightMeta"), selectedFlightTitle: $("selectedFlightTitle"), incidentTitle: $("incidentTitle"), incidentCount: $("incidentCount"), incidentList: $("incidentList"), modelState: $("modelState"), replayEmpty: $("replayEmpty"), replayFrame: $("replayFrame"), openReplay: $("openReplay"), patternList: $("patternList"), bulletinList: $("bulletinList"), analysisAnswer: $("analysisAnswer"), question: $("questionInput"), localAnalysis: $("localAnalysis"), localAnalysisBody: $("localAnalysisBody") };

function authHeaders(json = false) { const headers = state.token ? { Authorization: `Bearer ${state.token}` } : {}; return json ? { ...headers, "Content-Type": "application/json" } : headers; }
function detail(error) { return error?.detail || error?.message || "The request could not be completed."; }
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
function fmtTime(value) { if (!value) return "Recorded time unavailable"; const date = new Date(value); return Number.isNaN(date) ? value : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }); }
function label(value) { return String(value || "unclassified").replaceAll("_", " "); }
function escapeHtml(value) { const div = document.createElement("div"); div.textContent = value ?? ""; return div.innerHTML; }

function pipeline(status, detailText) {
  const stages = ["received", "parsing", "normalizing", "ready"];
  const current = status === "detecting" ? 3 : stages.indexOf(status);
  document.querySelectorAll("#pipelineStages li").forEach((el, index) => el.className = current < 0 ? "" : index < current ? "done" : index === current ? "active" : "");
  const failed = status === "failed";
  els.uploadStatus.textContent = failed ? "Failed" : status === "ready" ? "Record normalized" : status || "Waiting";
  $("uploadTabDot").hidden = !status || status === "ready" || failed;
  els.uploadStatus.className = `status-label ${failed ? "failed" : current < 0 ? "waiting" : ""}`;
  els.traceDetail.textContent = detailText || (failed ? "Processing ended with an error." : `Current record state: ${status || "waiting"}.`);
}
function uploadComplete(status) { return status === "ready" || status === "failed"; }
async function pollUpload(uploadId) {
  clearTimeout(state.pollTimer);
  try {
    let upload;
    try { upload = await api(`/v1/uploads/${encodeURIComponent(uploadId)}`); }
    catch (firstError) { upload = await api(`/v1/logs/${encodeURIComponent(uploadId)}/status`).catch(() => { throw firstError; }); }
    state.upload = upload;
    pipeline(upload.status, upload.error || (upload.duplicate ? "Duplicate record: using the original processing result." : `${upload.filename || "Log"} · ${upload.status}`));
    if (upload.status === "failed") { setMessage(upload.error || "The log could not be processed.", "error"); return; }
    if (upload.status === "ready") {
      setMessage(upload.duplicate ? "Duplicate found. The original normalized record is ready." : "Normalized record is ready for review.", "success");
      await refreshFlights();
      if (upload.flight_id) { await selectFlight(upload.flight_id); showView("overview"); }
      return;
    }
    state.pollTimer = setTimeout(() => pollUpload(uploadId), 1400);
  } catch (error) { setMessage(error.message, "error"); pipeline("failed", error.message); }
}
async function uploadFile(file) {
  if (!state.token) { setMessage("Add a session key before uploading.", "error"); setAuthPanel(true); return; }
  if (!file) return;
  if (file.size > 100 * 1024 * 1024) { setMessage("Choose a file smaller than 100 MB.", "error"); return; }
  const data = new FormData(); data.append("file", file);
  setMessage(`Uploading ${file.name}…`); pipeline("received", "Sending recorded bytes to the processing service.");
  try {
    const response = await fetch("/v1/logs/upload", { method: "POST", headers: authHeaders(), body: data });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(detail(body));
    state.upload = body;
    setMessage(body.duplicate ? "A matching recorded log already exists; checking its status…" : "Log accepted. Tracking its actual processing state.");
    pollUpload(body.upload_id);
  } catch (error) { setMessage(error.message, "error"); pipeline("failed", error.message); }
}
function renderFlights() {
  els.flightList.replaceChildren();
  if (!state.flights.length) { els.flightList.textContent = state.token ? "No recorded flights are available yet." : "Connect a session to load recorded flights."; els.flightList.className = "flight-list empty-state"; return; }
  els.flightList.className = "flight-list";
  for (const flight of state.flights) {
    const node = $("flightTemplate").content.firstElementChild.cloneNode(true);
    node.classList.toggle("selected", flight.id === state.selectedFlight?.id);
    const provenance = simulationProvenance(flight);
    node.querySelector(".flight-source").textContent = `${flightDisplayName(flight)}${provenance ? ` · ${provenance}` : ""}`;
    node.querySelector(".flight-time").textContent = fmtTime(flight.started_at);
    node.addEventListener("click", () => selectFlight(flight.id));
    els.flightList.append(node);
  }
}
async function refreshFlights() {
  if (!state.token) { renderFlights(); return; }
  const button = $("refreshFlights"); button.disabled = true;
  try { const result = await api("/v1/flights?limit=20"); state.flights = result.items || []; setApi("online", "Session connected"); if (!state.upload) setMessage("Session connected. Choose a recorded log to process.", "success"); renderFlights(); $("emptyHint").textContent = "Choose a flight from the library or import a log.";
    if (!state.selectedFlight && state.flights.length) { const saved = sessionStorage.getItem("wislSelectedFlight"); const initial = state.flights.find(f => f.id === saved) || state.flights.find(f => f.id === "flight-1a1b914dc70e6d0c1b45") || state.flights[0]; await selectFlight(initial.id); } }
  catch (error) { setApi("error", "Connection failed"); els.flightMeta.textContent = error.message; }
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
  return incident.started_at ? `Recorded at ${fmtTime(incident.started_at)}` : "Indexed detector evidence";
}
function renderIncidents(items) {
  els.incidentList.replaceChildren(); els.incidentCount.textContent = String(items.length);
  if (!items.length) { els.incidentList.textContent = "No indexed incidents were found for this recorded flight."; els.incidentList.className = "incident-list empty-state"; return; }
  els.incidentList.className = "incident-list";
  items.forEach((incident) => {
    const article = document.createElement("article"); article.className = "incident";
    const severity = String(incident.severity || "notice").toLowerCase();
    article.innerHTML = `<div class="incident-top"><span class="severity ${escapeHtml(severity)}">${escapeHtml(severity)}</span><h3>${escapeHtml(label(incident.incident_type || incident.type))}</h3></div><p>${escapeHtml(incident.summary || "Detector event indexed from the recorded log.")}</p><div class="evidence">${escapeHtml(evidenceText(incident))}</div>`;
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
  const fullUrl = new URL("/replay/", window.location.origin); fullUrl.searchParams.set("flights", flightId); if (state.token) fullUrl.searchParams.set("token", state.token);
  const frameUrl = new URL(fullUrl); frameUrl.searchParams.set("embed", "1"); frameUrl.searchParams.set("v", "studio-5"); if (timestamp) { fullUrl.searchParams.set("timestamp", timestamp); frameUrl.searchParams.set("timestamp", timestamp); }
  els.replayFrame.src = frameUrl.toString(); els.replayFrame.hidden = false; els.replayEmpty.hidden = true; els.openReplay.href = fullUrl.toString(); els.openReplay.classList.remove("disabled");
}
async function selectFlight(flightId, timestamp = null) {
  const flight = state.flights.find((item) => item.id === flightId) || { id: flightId };
  const version = ++state.selectionVersion;
  state.selectedFlight = flight; sessionStorage.setItem("wislSelectedFlight", flightId); renderFlights(); setLibrary(false);
  els.analysisAnswer.textContent = "Ask about this mission or open an observation in replay."; renderLocalAnalysis(null);
  const provenance = simulationProvenance(flight); els.selectedFlightTitle.textContent = flightDisplayName(flight); els.flightMeta.textContent = `${fmtTime(flight.started_at)} · ${flight.id}${provenance ? ` · ${provenance}` : ""}`; els.incidentTitle.textContent = "Loading indexed evidence…"; els.incidentCount.textContent = "…";
  setReplay(flightId, timestamp);
  try {
    const [incidents, report] = await Promise.all([api(`/v1/flights/${encodeURIComponent(flightId)}/incidents`), api(`/v1/flights/${encodeURIComponent(flightId)}/incident-report`).catch(() => null)]);
    if (version !== state.selectionVersion) return;
    renderIncidents(incidents.items || []); els.incidentTitle.textContent = incidents.count === 1 ? "1 indexed incident" : `${incidents.count || 0} indexed incidents`;
    const status = modelStatus(state.demoStatus || report); els.modelState.textContent = modelDisplay(status);
  } catch (error) { if (version !== state.selectionVersion) return; els.incidentTitle.textContent = "Evidence unavailable"; els.incidentList.textContent = error.message; els.incidentList.className = "incident-list empty-state"; }
}
async function refreshPatterns() {
  if (!state.token) return;
  try {
    const body = await api("/v1/incidents/patterns?min_flights=2"); const items = body.items || []; els.patternList.replaceChildren();
    if (!items.length) { els.patternList.textContent = "No signature currently recurs across two or more recorded flights."; els.patternList.className = "pattern-grid empty-state"; return; }
    els.patternList.className = "pattern-grid";
    for (const pattern of items) { const card = document.createElement("article"); card.className = "pattern"; card.innerHTML = `<span class="severity ${escapeHtml(String(pattern.max_severity || "notice").toLowerCase())}">${escapeHtml(pattern.max_severity || "notice")}</span><h3>${escapeHtml(label(pattern.incident_type))}</h3><p>${escapeHtml(pattern.summary || "Recurring detector signature in stored flights.")}</p><div class="pattern-meta"><span>${pattern.flight_count} flights</span><span>${pattern.incident_count} incidents</span></div><button class="button" type="button">Create review bulletin</button>`; card.querySelector("button").addEventListener("click", () => createBulletin(pattern.signature, card.querySelector("button"))); els.patternList.append(card); }
  } catch (error) { els.patternList.textContent = error.message; els.patternList.className = "pattern-grid empty-state"; }
}
async function createBulletin(signature, button) { if (!signature) return; button.disabled = true; button.textContent = "Creating…"; try { await api("/v1/mitigation-bulletins", { method:"POST", json:true, body:JSON.stringify({ signature }) }); await refreshBulletins(); showView("bulletins"); } catch (error) { button.textContent = error.message; } finally { button.disabled = false; } }
async function refreshBulletins() { if (!state.token) return; try { const body = await api("/v1/mitigation-bulletins"); const items = body.items || []; els.bulletinList.replaceChildren(); if (!items.length) { els.bulletinList.textContent = "No reviewable bulletins have been created from recorded patterns."; els.bulletinList.className = "bulletin-list empty-state"; return; } els.bulletinList.className = "bulletin-list"; for (const bulletin of items) { const card = document.createElement("article"); card.className="bulletin"; const review = (bulletin.recommended_review || []).map((item) => `<li>${escapeHtml(item)}</li>`).join(""); card.innerHTML = `<div class="bulletin-header"><div><p class="eyebrow">${escapeHtml(bulletin.signature || "recorded pattern")}</p><h2>${escapeHtml(label(bulletin.incident_type))}</h2></div><span class="count-pill">${bulletin.flight_count || 0} flights</span></div><p>${escapeHtml(bulletin.evidence_summary || "Evidence from the recorded incident signature.")}</p><ul>${review}</ul><p class="fine-print">${escapeHtml(bulletin.limitations || "For operator review only. This document does not modify aircraft.")}</p>`; els.bulletinList.append(card); } } catch (error) { els.bulletinList.textContent = error.message; els.bulletinList.className = "bulletin-list empty-state"; } }
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
  try { const answer = await api("/v1/demo/query", { method:"POST", json:true, body:JSON.stringify(body) }); els.analysisAnswer.textContent = queryText(answer); appendEvidenceLinks(els.analysisAnswer, answer.evidence); } catch (error) { els.analysisAnswer.textContent = `Evidence query unavailable: ${error.message}`; } }
async function analyzeFleetRecords() { if (!state.token) { els.localAnalysis.hidden = true; els.analysisAnswer.textContent = "Connect a session key to analyze stored fleet records."; return; } const button = $("fleetAnalysisButton"); const question = els.question.value.trim() || "Summarize recurring patterns and evidence across stored flights."; button.disabled = true; button.textContent = "Analyzing…"; els.localAnalysis.hidden = true; try { const result = await api("/v1/demo/analysis", { method:"POST", json:true, body:JSON.stringify({ question }) }); renderLocalAnalysis(result); } catch (error) { els.analysisAnswer.textContent = `Local analysis unavailable: ${error.message}`; } finally { button.disabled = false; button.textContent = "Analyze fleet records"; } }
function showView(view) {
  document.querySelectorAll(".view").forEach(el => { const active = el.id === `${view}View`; el.classList.toggle("active", active); el.hidden = !active; });
  document.querySelectorAll(".nav-link").forEach(el => { const active = el.dataset.view === view; el.classList.toggle("active", active); el.setAttribute("aria-selected", String(active)); el.tabIndex = active ? 0 : -1; });
  document.querySelector(".dock-content").scrollTop = 0;
  if (view === "patterns") refreshPatterns();
  if (view === "bulletins") refreshBulletins();
}
function setLibrary(open) { $("flightLibrary").hidden = !open; $("libraryButton").setAttribute("aria-expanded", String(open)); if (open) setAuthPanel(false); }
function setAuthPanel(open) { $("authPanel").hidden = !open; $("authButton").setAttribute("aria-expanded", String(open)); if (open) { setLibrary(false); els.token.focus(); } }
async function connect() {
  state.token = els.token.value.trim();
  if (!state.token) return;
  sessionStorage.setItem("wislDemoToken", state.token); setAuthPanel(false); setApi("", "Connecting…");
  await Promise.all([refreshFlights(), refreshPatterns(), refreshBulletins(), loadDemoStatus()]);
}
$("authButton").addEventListener("click", () => setAuthPanel($("authPanel").hidden));
$("saveToken").addEventListener("click", connect);
els.token.addEventListener("keydown", event => { if (event.key === "Enter") connect(); });
$("clearToken").addEventListener("click", () => { sessionStorage.removeItem("wislDemoToken"); sessionStorage.removeItem("sdthReplayToken"); sessionStorage.removeItem("wislSelectedFlight"); window.location.reload(); });
$("libraryButton").addEventListener("click", () => setLibrary($("flightLibrary").hidden));
$("emptyLibraryButton").addEventListener("click", () => state.token ? setLibrary(true) : setAuthPanel(true));
$("closeLibrary").addEventListener("click", () => setLibrary(false));
$("importButton").addEventListener("click", () => { setLibrary(false); showView("logs"); $("dropzone").scrollIntoView({block:"nearest",behavior:"smooth"}); });
$("sampleButton").addEventListener("click", async () => {
  if (!state.token) { setAuthPanel(true); return; }
  const button = $("sampleButton"); button.disabled = true;
  try { const response = await fetch("/demo/fixtures/dji_csv_gps_jamming.csv"); if (!response.ok) throw new Error("The included sample could not be loaded."); await uploadFile(new File([await response.blob()], "dji_csv_gps_jamming.csv", {type:"text/csv"})); }
  catch (error) { setMessage(error.message, "error"); }
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
document.querySelectorAll(".query-presets button").forEach(button => button.addEventListener("click", () => { els.question.value = button.dataset.query; $("questionForm").requestSubmit(); }));
const tabs = [...document.querySelectorAll(".nav-link")];
tabs.forEach((button,index) => {
  button.addEventListener("click", () => showView(button.dataset.view));
  button.addEventListener("keydown", event => { const target = event.key === "ArrowRight" ? (index+1)%tabs.length : event.key === "ArrowLeft" ? (index+tabs.length-1)%tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length-1 : null; if (target !== null) { event.preventDefault(); tabs[target].focus(); showView(tabs[target].dataset.view); } });
});
els.token.value = state.token; pipeline("", "No log is being processed.");
if (state.token) { setApi("", "Connecting…"); refreshFlights(); refreshPatterns(); refreshBulletins(); loadDemoStatus(); } else renderFlights();
