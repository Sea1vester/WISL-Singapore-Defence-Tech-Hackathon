import assert from "node:assert/strict";
import test from "node:test";
import { folderTrail, folderPath, folderDestinations, flightDisplayName, isSimulationCorpus, localAnalysisView, modelDisplay, modelStatus, modelProgressText, usesDefaultModel, queryText, simulationProvenance } from "../demo-contract.mjs";

test("folder paths and move destinations respect nested ancestry", () => {
  const folders = [{id: "a", parent_id: null, name: "Singapore"}, {id: "b", parent_id: "a", name: "Hillview"}, {id: "c", parent_id: null, name: "UK"}];
  assert.equal(folderPath(folders, "b"), "Missions / Singapore / Hillview");
  assert.equal(folderPath(folders, null), "Missions");
  assert.equal(folderPath(folders, "missing"), "Missions");
  assert.deepEqual(folderDestinations(folders, "a").map(folder => folder.id), ["c"]);
  assert.deepEqual(folderDestinations(folders, "b").map(folder => folder.id), ["a", "c"]);
  assert.equal(folderTrail([{id: "a", parent_id: "a", name: "Broken"}], "a").length, 1);
});

test("handles the documented local model status shape", () => {
  assert.equal(modelStatus({ model: { status: "ready", local: true } }), "ready");
  assert.match(modelDisplay("ready"), /available/);
  assert.match(modelDisplay("offline"), /degraded or offline/);
});
test("automatic connection uses laptop defaults without replacing a judge's provider", () => {
  const model = {name: "qwen2.5:7b-instruct", base_url: "http://127.0.0.1:11434"};
  const connection = {provider: "ollama", model: model.name, base_url: model.base_url + "/", api_key: ""};
  assert.equal(usesDefaultModel(null, model), true);
  assert.equal(usesDefaultModel(connection, model), true);
  assert.equal(usesDefaultModel({...connection, provider: "openai"}, model), false);
  assert.equal(usesDefaultModel({...connection, model: "another-model"}, model), false);
  assert.equal(usesDefaultModel({...connection, base_url: "http://localhost:1234"}, model), false);
  assert.equal(usesDefaultModel({...connection, api_key: "server-token"}, model), false);
});

test("model progress separates waiting, reported reasoning and validated completion", () => {
  assert.match(modelProgressText("loading"), /Waiting/);
  assert.match(modelProgressText("thinking"), /reports reasoning/);
  assert.match(modelProgressText("validating"), /evidence references/);
  assert.match(modelProgressText("cached"), /previously generated/);
  assert.match(modelProgressText("unavailable"), /No validated answer/);
  assert.match(modelProgressText("unknown"), /Waiting/);
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
  assert.equal(flightDisplayName({ original_filename: "dji_csv_gps_jamming.csv", source: "dji-csv" }), "GPS-weak warning · DJI CSV");
  assert.equal(flightDisplayName({ original_filename: "orbiter4_gps_denied_frozen.json", source: "orbiter4" }), "Frozen position · Orbiter JSON");
  assert.equal(flightDisplayName({ original_filename: "dji_csv_supplemental_normal_control.csv" }), "Supplemental normal-control mission");
  assert.equal(flightDisplayName({ original_filename: "dji_csv_supplemental_gps_weak_recurrence.csv" }), "Supplemental GPS-weak mission");
  assert.equal(simulationProvenance({ original_filename: "dji_csv_supplemental_gps_weak_recurrence.csv" }), "Supplemental simulation corpus");
  assert.equal(flightDisplayName({ id: "flight-eea7a01de29aec8aed1e" }), "Supplemental normal-control mission");
});
