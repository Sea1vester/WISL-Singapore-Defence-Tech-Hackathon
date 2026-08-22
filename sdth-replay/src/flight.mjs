export function parseIso8601Utc(timestamp) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d+(?:\.\d+)?)Z$/.exec(String(timestamp));
  if (!match) {
    throw new Error(`Unsupported timestamp (expected ISO-8601 UTC): ${timestamp}`);
  }
  const epochMs = Date.parse(timestamp);
  if (Number.isNaN(epochMs)) {
    throw new Error(`Invalid ISO-8601 timestamp: ${timestamp}`);
  }
  return epochMs / 1000;
}

export function formatIso8601Utc(epochSeconds) {
  return new Date(epochSeconds * 1000).toISOString().replace(/\.\d{3}Z$/, "Z");
}

function optionalNumber(value, key, fallback = 0) {
  if (value[key] == null) {
    return fallback;
  }
  const number = Number(value[key]);
  if (Number.isNaN(number)) {
    throw new Error(`Expected numeric field: ${key}`);
  }
  return number;
}

function nullableNumber(value, key) {
  if (value[key] == null) {
    return null;
  }
  const number = Number(value[key]);
  if (Number.isNaN(number)) {
    throw new Error(`Expected numeric field: ${key}`);
  }
  return number;
}

function optionalString(value, key, fallback = "") {
  return typeof value[key] === "string" ? value[key] : fallback;
}

function mix(from, to, amount) {
  return from + (to - from) * amount;
}

function mixAngle(from, to, amount) {
  const delta = ((((to - from + 540) % 360) + 360) % 360) - 180;
  return from + delta * amount;
}

function mixOptional(from, to, amount) {
  if (from != null && to != null) {
    return mix(from, to, amount);
  }
  return from ?? to;
}

export function isLocalNedFrame(path) {
  return String(path?.frame || "").includes("local_ned");
}

export function globeAltitudeOffsetM(path) {
  if (!path.samples?.length) {
    return 1;
  }
  let minAlt = Infinity;
  for (const sample of path.samples) {
    if (Number.isFinite(sample.alt_m) && sample.alt_m < minAlt) {
      minAlt = sample.alt_m;
    }
  }
  if (!Number.isFinite(minAlt)) {
    return 1;
  }
  return 1 - minAlt;
}

export function globeAltM(path, altM, terrainHeight = 0) {
  const altitude = Number.isFinite(altM) ? altM : 0;
  const terrain = Number.isFinite(terrainHeight) ? terrainHeight : 0;
  return terrain + altitude + globeAltitudeOffsetM(path);
}

export function parseFlightPath(document) {
  if (document == null || typeof document !== "object" || Array.isArray(document)) {
    throw new Error("Flight path must be a JSON object");
  }
  if (!Array.isArray(document.samples)) {
    throw new Error("Flight path is missing a samples array");
  }
  const flightId = optionalString(document, "flight_id");
  if (!flightId) {
    throw new Error("Flight path is missing flight_id");
  }

  const samples = [];
  let previousTime = 0;
  let haveTime = false;
  for (const item of document.samples) {
    if (item == null || typeof item !== "object" || item.lat == null || item.lon == null) {
      throw new Error("Each path sample requires lat and lon");
    }
    const sample = {
      timestamp: optionalString(item, "t"),
      time_s: 0,
      lat: optionalNumber(item, "lat"),
      lon: optionalNumber(item, "lon"),
      alt_m: optionalNumber(item, "alt_m"),
      roll_deg: optionalNumber(item, "roll_deg"),
      pitch_deg: optionalNumber(item, "pitch_deg"),
      yaw_deg: optionalNumber(item, "yaw_deg"),
      battery_pct: nullableNumber(item, "battery_pct"),
      battery_v: nullableNumber(item, "battery_v"),
      flight_mode: optionalString(item, "flight_mode"),
      warning: optionalString(item, "warning"),
      tip: optionalString(item, "tip"),
    };
    if (sample.timestamp) {
      sample.time_s = parseIso8601Utc(sample.timestamp);
      previousTime = sample.time_s;
      haveTime = true;
    } else {
      sample.time_s = haveTime ? previousTime + 1 : samples.length;
      sample.timestamp = formatIso8601Utc(sample.time_s);
      previousTime = sample.time_s;
      haveTime = true;
    }
    samples.push(sample);
  }
  if (samples.length === 0) {
    throw new Error("Flight path has no samples");
  }
  for (let index = 1; index < samples.length; index += 1) {
    if (samples[index].time_s < samples[index - 1].time_s) {
      throw new Error("Flight path timestamps must be ordered");
    }
  }

  return {
    contract_version: optionalString(document, "contract_version", "1.0"),
    flight_id: flightId,
    source: optionalString(document, "source", "unknown"),
    frame: optionalString(document, "frame", "wgs84"),
    data_origin: optionalString(document, "data_origin", "offline_file"),
    mission_summary: optionalString(document, "mission_summary"),
    report_text: optionalString(document, "report") || optionalString(document, "mission_summary"),
    upload_status: optionalString(document, "upload_status", "offline-demo"),
    samples,
    incidents: [],
  };
}

export function parseIncidents(document) {
  const items = Array.isArray(document) ? document : document?.items;
  if (!Array.isArray(items)) {
    throw new Error("Incident response must contain an items array");
  }
  return items.map((item) => {
    const evidence = item.evidence && typeof item.evidence === "object" ? item.evidence : {};
    const position = evidence.position && typeof evidence.position === "object" ? evidence.position : {};
    return {
      id: optionalString(item, "id"),
      type: optionalString(item, "incident_type", optionalString(item, "type", "incident")),
      severity: optionalString(item, "severity", "info"),
      detector: optionalString(item, "detector"),
      started_at: optionalString(item, "started_at"),
      ended_at: optionalString(item, "ended_at"),
      summary: optionalString(item, "summary"),
      report: optionalString(evidence, "report"),
      lat: nullableNumber(item, "lat") ?? nullableNumber(evidence, "lat") ?? nullableNumber(position, "lat"),
      lon: nullableNumber(item, "lon") ?? nullableNumber(evidence, "lon") ?? nullableNumber(position, "lon"),
      alt_m: nullableNumber(item, "alt_m") ?? nullableNumber(evidence, "alt_m") ?? nullableNumber(position, "alt_m"),
      sample_index: null,
    };
  });
}

export function interpolate(path, timeS) {
  const { samples } = path;
  if (!samples.length) {
    throw new Error("Cannot interpolate an empty flight path");
  }
  if (timeS <= samples[0].time_s || samples.length === 1) {
    const sample = samples[0];
    return {
      time_s: timeS,
      lat: sample.lat,
      lon: sample.lon,
      alt_m: sample.alt_m,
      roll_deg: sample.roll_deg,
      pitch_deg: sample.pitch_deg,
      yaw_deg: sample.yaw_deg,
      battery_pct: sample.battery_pct,
      battery_v: sample.battery_v,
      flight_mode: sample.flight_mode,
      warning: sample.warning,
      tip: sample.tip,
      lower_sample: 0,
      upper_sample: 0,
      blend: 0,
    };
  }
  if (timeS >= samples[samples.length - 1].time_s) {
    const last = samples.length - 1;
    const sample = samples[last];
    return {
      time_s: timeS,
      lat: sample.lat,
      lon: sample.lon,
      alt_m: sample.alt_m,
      roll_deg: sample.roll_deg,
      pitch_deg: sample.pitch_deg,
      yaw_deg: sample.yaw_deg,
      battery_pct: sample.battery_pct,
      battery_v: sample.battery_v,
      flight_mode: sample.flight_mode,
      warning: sample.warning,
      tip: sample.tip,
      lower_sample: last,
      upper_sample: last,
      blend: 0,
    };
  }
  let upperIndex = samples.findIndex((sample) => timeS < sample.time_s);
  if (upperIndex <= 0) {
    upperIndex = 1;
  }
  const lowerIndex = upperIndex - 1;
  const lower = samples[lowerIndex];
  const high = samples[upperIndex];
  const interval = high.time_s - lower.time_s;
  const blend = interval > 0 ? (timeS - lower.time_s) / interval : 0;
  return {
    time_s: timeS,
    lat: mix(lower.lat, high.lat, blend),
    lon: mix(lower.lon, high.lon, blend),
    alt_m: mix(lower.alt_m, high.alt_m, blend),
    roll_deg: mixAngle(lower.roll_deg, high.roll_deg, blend),
    pitch_deg: mixAngle(lower.pitch_deg, high.pitch_deg, blend),
    yaw_deg: mixAngle(lower.yaw_deg, high.yaw_deg, blend),
    battery_pct: mixOptional(lower.battery_pct, high.battery_pct, blend),
    battery_v: mixOptional(lower.battery_v, high.battery_v, blend),
    flight_mode: lower.flight_mode,
    warning: lower.warning,
    tip: lower.tip,
    lower_sample: lowerIndex,
    upper_sample: upperIndex,
    blend,
  };
}

export function alignIncidentToPath(incident, path) {
  if (!path.samples.length || !incident.started_at) {
    return null;
  }
  const target = parseIso8601Utc(incident.started_at);
  let upperIndex = path.samples.findIndex((sample) => sample.time_s >= target);
  if (upperIndex <= 0) {
    return 0;
  }
  if (upperIndex === -1) {
    return path.samples.length - 1;
  }
  const lowerIndex = upperIndex - 1;
  return target - path.samples[lowerIndex].time_s <= path.samples[upperIndex].time_s - target
    ? lowerIndex
    : upperIndex;
}

export function alignIncidents(path) {
  for (const incident of path.incidents) {
    incident.sample_index = alignIncidentToPath(incident, path);
  }
  return path;
}

export function severityRank(severity) {
  if (severity === "critical") {
    return 3;
  }
  if (severity === "warning") {
    return 2;
  }
  return 1;
}

export function incidentActive(incident, timeS) {
  if (!incident.started_at) {
    return false;
  }
  try {
    const start = parseIso8601Utc(incident.started_at);
    const end = incident.ended_at ? parseIso8601Utc(incident.ended_at) : start + 4;
    return timeS >= start && timeS <= end;
  } catch {
    return false;
  }
}

export function bannerIncident(path, timeS) {
  if (!path.incidents?.length) {
    return null;
  }
  let current = null;
  let strongest = path.incidents[0];
  for (const incident of path.incidents) {
    if (incidentActive(incident, timeS) && current == null) {
      current = incident;
    }
    if (severityRank(incident.severity) > severityRank(strongest.severity)) {
      strongest = incident;
    }
  }
  return current ?? strongest;
}

export function incidentDescription(path, incident) {
  if (path.mission_summary) {
    return path.mission_summary;
  }
  if (incident?.summary) {
    return incident.summary;
  }
  if (path.report_text) {
    return path.report_text;
  }
  if (incident?.report) {
    return incident.report;
  }
  return "Indexed telemetry incident with no additional narrative.";
}

export function bannerState(path, timeS) {
  const incident = bannerIncident(path, timeS);
  if (!incident) {
    return {
      failed: false,
      title: "NO INCIDENTS",
      severity: "",
      type: "",
      description: "Telemetry replay. No indexed mission failure.",
    };
  }
  return {
    failed: true,
    title: "MISSION FAILURE",
    severity: incident.severity,
    type: incident.type,
    description: incidentDescription(path, incident),
    incident,
  };
}

export function sampleEvent(path, index) {
  const sample = path.samples[index];
  if (!sample) {
    return "No event at current sample";
  }
  if (sample.warning) {
    return sample.warning;
  }
  if (sample.tip) {
    return sample.tip;
  }
  return "No event at current sample";
}
