import assert from "node:assert/strict";
import test from "node:test";
import { flightDisplayName, isSimulationCorpus, localAnalysisView, modelDisplay, modelStatus, queryText, simulationProvenance } from "../demo-contract.mjs";

test("handles the documented local model status shape", () => {
  assert.equal(modelStatus({ model: { status: "ready", local: true } }), "ready");
  assert.match(modelDisplay("ready"), /available/);
  assert.match(modelDisplay("offline"), /degraded or offline/);
});
test("formats only returned operator evidence", () => {
  assert.equal(queryText({ answer: "A warning was indexed.", evidence: [{ id: "inc-7", summary: "Warning at 10:32Z" }], related_flights: [{ flight_id: "flight-bravo" }] }), "A warning was indexed.\n\nEvidence: Warning at 10:32Z\n\nRelated flights: flight-bravo");
});
test("preserves local analysis scope and exposes unavailable model output", () => {
  assert.equal(localAnalysisView({ status: "unavailable", summary: "Model did not return a response." }).status, "unavailable");
  const view = localAnalysisView({ status: "generated", summary: "A recurring signature appears.", hypotheses: [{ analysis: "Review missions.", evidence_ids: ["inc-7"] }], limitations: ["Recorded logs only."], coverage: { total_flights: 4, included_flights: 2, raw_samples_in_prompt: false } });
  assert.equal(view.coverage.included_flights, 2);
  assert.equal(view.coverage.raw_samples_in_prompt, false);
});
test("only recognizes explicitly known simulation corpus sources", () => {
  assert.equal(isSimulationCorpus({ id: "flight-1a1b914dc70e6d0c1b45", source: "dji-csv" }), true);
  assert.equal(simulationProvenance({ id: "flight-4fb673922655692b61ac" }), "Supplemental simulation corpus");
  assert.equal(isSimulationCorpus({ source: "controller_mission_alpha.csv" }), true);
  assert.equal(isSimulationCorpus({ source: "operator-upload-2026.csv" }), false);
});
test("uses upload provenance for a human-readable flight title", () => {
  assert.equal(flightDisplayName({ original_filename: "dji_csv_gps_jamming.csv", source: "dji-csv" }), "dji csv gps jamming");
  assert.equal(flightDisplayName({ id: "flight-eea7a01de29aec8aed1e" }), "Supplemental normal-control mission");
});
