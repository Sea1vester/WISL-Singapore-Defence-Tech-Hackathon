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
  const filename = flight?.original_filename || flight?.filename || flight?.upload_filename || "";
  if (original.has(flight?.id) || filename === "dji_csv_gps_jamming.csv" || filename === "dji_csv_logger_dropout.csv") return "Original simulation corpus";
  if (supplemental.has(flight?.id) || filename.startsWith("dji_csv_supplemental_")) return "Supplemental simulation corpus";
  return "";
}

export function flightDisplayName(flight) {
  const filename = flight?.original_filename || flight?.filename || flight?.upload_filename;
  // "Exercise" rather than "Synthetic" -- reads naturally to a military
  // audience and still states plainly that these are not live operational
  // sorties, which the provenance label and the fixtures' own manifest
  // continue to record.
  // Keyed on the fixtures' real on-disk filenames. Older uploads carried a
  // "synthetic_" prefix added at upload time; both spellings are mapped so a
  // library loaded before that change still resolves to a friendly name.
  const exerciseNames = {
    "dji_csv_battery_critical_021.csv": "Exercise · Critical battery",
    "dji_csv_battery_critical_logger_dropout_027.csv": "Exercise · Low battery + recording gap",
    "dji_csv_gps_denied_frozen_023.csv": "Exercise · Frozen reported position",
    "dji_csv_gps_jamming_022.csv": "Exercise · GPS-weak warning",
    "dji_csv_gps_weak_midair_end_028.csv": "Exercise · GPS warning + airborne ending",
    "dji_csv_logger_dropout_025.csv": "Exercise · Recording gap",
    "dji_csv_lost_airborne_026.csv": "Exercise · Recording ends airborne",
    "dji_csv_motor_fail_recover_024.csv": "Exercise · Attitude excursion + warning",
    "dji_csv_v2_normal_control.csv": "Exercise · Normal control",
    "dji_csv_sg_lck_survey_normal.csv": "Lim Chu Kang · Survey · Normal control",
    "dji_csv_sg_lck_survey_gps_weak.csv": "Lim Chu Kang · Survey · GPS-weak",
    "dji_csv_sg_seletar_perimeter_gps_weak.csv": "Seletar · Perimeter · GPS-weak",
    "dji_csv_sg_hillview_inspection_battery_critical.csv": "Hillview · Inspection · Battery critical",
    "dji_csv_sg_hillview_inspection_dropout.csv": "Hillview · Inspection · Telemetry dropout",
    "dji_csv_sg_seletar_ends_airborne.csv": "Seletar · Recording ends airborne",
  };
  if (typeof filename === "string" && filename.startsWith("synthetic_")) {
    const legacy = exerciseNames[filename.slice("synthetic_".length)];
    if (legacy) return legacy;
  }
  if (exerciseNames[filename]) return exerciseNames[filename];
  const knownNames = {
    "dji_csv_gps_jamming.csv": "GPS-weak warning · DJI CSV",
    "orbiter4_gps_denied_frozen.json": "Frozen position · Orbiter JSON",
    "dji_csv_supplemental_gps_weak_recurrence.csv": "Supplemental GPS-weak mission",
    "dji_csv_supplemental_normal_control.csv": "Supplemental normal-control mission",
    "flight-1a1b914dc70e6d0c1b45": "GPS-weak mission",
    "flight-b7ee5f98110be03e6576": "Telemetry-dropout mission",
    "flight-4fb673922655692b61ac": "Supplemental GPS-weak mission",
    "flight-eea7a01de29aec8aed1e": "Supplemental normal-control mission",
  };
  if (knownNames[filename]) return knownNames[filename];
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
  return { status: response.status || "unknown", summary: response.summary || "No local analysis summary returned.", hypotheses: Array.isArray(response.hypotheses) ? response.hypotheses : [], limitations: Array.isArray(response.limitations) ? response.limitations : [], evidence: Array.isArray(response.evidence) ? response.evidence : [], coverage: response.coverage || null, cached: response.cached === true, generated_at: response.generated_at || null };
}
