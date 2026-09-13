export function modelStatus(payload) {
  const model = payload?.model || payload?.model_status || payload?.llm || payload?.local_model;
  if (typeof model === "string") return model;
  if (model?.status) return model.status;
  if (payload?.model_enrichment) return payload.model_enrichment;
  return "unavailable";
}

export function modelDisplay(status) {
  return status === "ready" || status === "available"
    ? "Local model enrichment is available for review."
    : "Deterministic evidence remains available; local model enrichment is degraded or offline.";
}

export function isSimulationCorpus(flight) {
  return Boolean(simulationProvenance(flight)) || /controller_mission_(alpha|bravo)|simulation corpus/i.test(`${flight?.source || ""} ${flight?.id || ""}`);
}

export function simulationProvenance(flight) {
  const original = new Set(["flight-1a1b914dc70e6d0c1b45", "flight-b7ee5f98110be03e6576"]);
  const supplemental = new Set(["flight-4fb673922655692b61ac", "flight-eea7a01de29aec8aed1e"]);
  if (original.has(flight?.id)) return "Original simulation corpus";
  if (supplemental.has(flight?.id)) return "Supplemental simulation corpus";
  return "";
}

export function flightDisplayName(flight) {
  const filename = flight?.original_filename || flight?.filename || flight?.upload_filename;
  const knownNames = {
    "flight-1a1b914dc70e6d0c1b45": "GPS-weak mission",
    "flight-b7ee5f98110be03e6576": "Telemetry-dropout mission",
    "flight-4fb673922655692b61ac": "Supplemental GPS-weak mission",
    "flight-eea7a01de29aec8aed1e": "Supplemental normal-control mission",
  };
  if (knownNames[flight?.id]) return knownNames[flight.id];
  if (filename) return String(filename).replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");
  return flight?.source || flight?.id || "Recorded flight";
}

export function queryText(response) {
  const evidence = Array.isArray(response?.evidence) ? response.evidence : [];
  const related = Array.isArray(response?.related_flights) ? response.related_flights : [];
  const itemText = (item) => typeof item === "string" ? item : item?.summary || item?.id || item?.flight_id || "Recorded evidence";
  return `${response?.answer || "No evidence-backed answer was returned."}${evidence.length ? `\n\nEvidence: ${evidence.map(itemText).join(" · ")}` : ""}${related.length ? `\n\nRelated flights: ${related.map(itemText).join(", ")}` : ""}`;
}

export function localAnalysisView(response) {
  if (!response) return null;
  return { status: response.status || "unknown", summary: response.summary || "No local analysis summary returned.", hypotheses: Array.isArray(response.hypotheses) ? response.hypotheses : [], limitations: Array.isArray(response.limitations) ? response.limitations : [], evidence: Array.isArray(response.evidence) ? response.evidence : [], coverage: response.coverage || null };
}
