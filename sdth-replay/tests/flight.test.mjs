import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  alignIncidents,
  bannerState,
  formatIso8601Utc,
  globeAltM,
  globeAltitudeOffsetM,
  interpolate,
  parseFlightPath,
  parseIncidents,
  parseIso8601Utc,
} from "../src/flight.mjs";

const here = dirname(fileURLToPath(import.meta.url));

function pathJson() {
  return {
    contract_version: "1.0",
    flight_id: "test-flight",
    source: "unit-test",
    frame: "wgs84",
    data_origin: "l1_ingest",
    samples: [
      {
        t: "2026-07-11T10:00:00Z",
        lat: 1.3521,
        lon: 103.8198,
        alt_m: 10.0,
        yaw_deg: 350.0,
        battery_pct: 90.0,
        flight_mode: "AUTO",
      },
      {
        t: "2026-07-11T10:00:10Z",
        lat: 1.3531,
        lon: 103.8208,
        alt_m: 30.0,
        yaw_deg: 10.0,
        battery_pct: 70.0,
        warning: "wind",
      },
    ],
  };
}

test("unix epoch parses", () => {
  assert.equal(parseIso8601Utc("1970-01-01T00:00:00Z"), 0);
  assert.equal(formatIso8601Utc(0), "1970-01-01T00:00:00Z");
});

test("json path parsing", () => {
  const path = parseFlightPath(pathJson());
  assert.equal(path.flight_id, "test-flight");
  assert.equal(path.source, "unit-test");
  assert.equal(path.data_origin, "l1_ingest");
  assert.equal(path.samples.length, 2);
  assert.equal(path.samples[0].timestamp, "2026-07-11T10:00:00Z");
  assert.equal(path.samples[0].battery_pct, 90);
  assert.equal(path.samples[1].warning, "wind");
  assert.ok(Math.abs(path.samples[1].time_s - path.samples[0].time_s - 10) < 1e-9);
});

test("timestamp interpolation", () => {
  const path = parseFlightPath(pathJson());
  const pose = interpolate(path, path.samples[0].time_s + 5);
  assert.ok(Math.abs(pose.lat - 1.3526) < 1e-9);
  assert.ok(Math.abs(pose.alt_m - 20) < 1e-9);
  assert.ok(Math.abs(pose.battery_pct - 80) < 1e-9);
  assert.ok(Math.abs((((pose.yaw_deg % 360) + 360) % 360) - 0) < 1e-9);
  assert.equal(pose.lower_sample, 0);
  assert.equal(pose.upper_sample, 1);
  assert.ok(Math.abs(pose.blend - 0.5) < 1e-9);
});

test("incident alignment", () => {
  const path = parseFlightPath(pathJson());
  path.incidents = parseIncidents({
    flight_id: "test-flight",
    count: 1,
    items: [
      {
        id: "incident-1",
        incident_type: "battery_drop",
        severity: "warning",
        detector: "rule",
        started_at: "2026-07-11T10:00:08Z",
        ended_at: "2026-07-11T10:00:09Z",
        summary: "Battery dropped quickly",
        lat: 1.3531,
        lon: 103.8208,
        alt_m: 30.0,
        evidence: { delta: 20 },
      },
    ],
  });
  alignIncidents(path);
  assert.equal(path.incidents.length, 1);
  assert.equal(path.incidents[0].type, "battery_drop");
  assert.equal(path.incidents[0].sample_index, 1);
  assert.equal(path.incidents[0].lat, 1.3531);
  assert.equal(path.incidents[0].lon, 103.8208);
});

test("banner prefers mission summary and shows failure", () => {
  const path = parseFlightPath(pathJson());
  path.mission_summary = "Survey aborted after a GPS warning.";
  path.incidents = parseIncidents({
    items: [
      {
        incident_type: "operator_warning",
        severity: "warning",
        started_at: "2026-07-11T10:00:08Z",
        ended_at: "2026-07-11T10:00:09Z",
        summary: "GPS signal weak",
      },
    ],
  });
  const failed = bannerState(path, path.samples[1].time_s);
  assert.equal(failed.failed, true);
  assert.equal(failed.title, "MISSION FAILURE");
  assert.equal(failed.severity, "warning");
  assert.equal(failed.type, "operator_warning");
  assert.equal(failed.description, "Survey aborted after a GPS warning.");
});

test("banner shows no incidents when none are indexed", () => {
  const path = parseFlightPath(pathJson());
  const idle = bannerState(path, path.samples[0].time_s);
  assert.equal(idle.failed, false);
  assert.equal(idle.title, "NO INCIDENTS");
});

test("bundled demo path is loadable", () => {
  const document = JSON.parse(
    readFileSync(join(here, "../public/assets/demo_path.json"), "utf8"),
  );
  const path = parseFlightPath(document);
  assert.equal(path.flight_id, "offline-demo-alpha");
  assert.ok(path.samples.length >= 8);
  assert.ok(path.mission_summary);
});

test("local NED globe altitude sits 1 m above the lowest sample", () => {
  const path = parseFlightPath({
    flight_id: "ned-flight",
    frame: "wgs84+local_ned",
    samples: [
      { t: "1970-01-01T00:00:00Z", lat: 47.3977, lon: 8.5455, alt_m: 0.12 },
      { t: "1970-01-01T00:00:01Z", lat: 47.3978, lon: 8.5456, alt_m: 17.4 },
      { t: "1970-01-01T00:00:02Z", lat: 47.3978, lon: 8.5456, alt_m: -13.4 },
    ],
  });
  assert.equal(globeAltitudeOffsetM(path), 14.4);
  assert.ok(Math.abs(globeAltM(path, -13.4) - 1) < 1e-9);
  assert.ok(Math.abs(globeAltM(path, 0.12) - 14.52) < 1e-9);
  assert.equal(path.samples[2].alt_m, -13.4);
});

test("WGS84 globe altitude drapes as AGL on the surface", () => {
  const path = parseFlightPath(pathJson());
  assert.equal(globeAltitudeOffsetM(path), -9);
  assert.equal(globeAltM(path, 10), 1);
  assert.equal(globeAltM(path, 30), 21);
  assert.equal(globeAltM(path, 10, 400), 401);
});
