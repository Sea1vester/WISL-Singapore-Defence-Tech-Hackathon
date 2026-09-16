"""
Pre-emptive mission-planning report: a deterministic synthesis of one flight's
maneuver/failure correlation, controller<->vehicle link reliability, and
camera/vision reliability, plus data-grounded recommendations for the next
sortie.

This is not a fault diagnosis and not a vehicle command channel -- same
posture as mitigation bulletins (see app/bulletins.py). Two terms need an
explicit reading, because the platform doesn't record what they'd literally
mean:

  - "Audio issues between the controller and the event": this platform has no
    audio channel at all. What it does have is RF telemetry link quality --
    dropout gaps, operator warnings mentioning link/signal loss, and raw
    signal-strength/satellite-count fields where a parser captured them. The
    `link_reliability` section reports exactly that, under that name, and
    never claims to have heard anything.
  - "What cameras work/don't work in certain terrains": there is no terrain
    label anywhere in this platform's telemetry or vision data (see the
    synthetic_telemetry_vision dataset's own README for the same gap). What
    IS measurable is per-frame image quality -- exposure and a coarse blur
    proxy computed directly from the stored JPEG bytes. `camera_reliability`
    reports that, and says plainly that terrain-conditioned guidance needs a
    future GPS+land-cover join this platform doesn't have yet.

No network calls, no LLM dependency -- everything here is computed from
canonical telemetry, detector output, and stored visual/census rows already
on disk. This keeps the report generatable in an offline demo environment.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from app.brands import identify_brand
from app.canonical_series import load_flight_series
from app.census import list_frame_census
from app.detectors import (
    ATTITUDE_WARN_DEG,
    GAP_S,
    _dt_seconds,
    detect_incidents,
    parse_timestamp,
)
from app.incidents import nearest_position
from app.path_export import _num
from app.visuals import list_visuals, resolve_visual_path

MANEUVER_INCIDENT_TYPES = {"attitude_shock", "gps_jump", "altitude_spike"}
UXO_INCIDENT_TYPES = {"mission_incomplete", "last_known_position", "operator_marked_debris"}
LINK_KEYWORDS = ("link", "signal", "weak", "lost", "downlink", "rc signal", "failsafe", "rssi")

# Camera cadence is not asserted anywhere in this platform; this is a stated
# assumption used only to flag unusually large gaps between captured frames,
# not a measured spec.
ASSUMED_FRAME_INTERVAL_S = 5.0
FRAME_LAG_MULTIPLIER = 2.0
MAX_FRAMES_QUALITY_SAMPLED = 10

BRIGHTNESS_OVEREXPOSED = 205.0
BRIGHTNESS_UNDEREXPOSED = 35.0
BLUR_EDGE_VARIANCE_FLOOR = 60.0  # below this, the frame looks unusually flat/blurred


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _describe_maneuver(incident: Any, series: list[dict[str, Any]]) -> dict[str, Any]:
    ev = incident.evidence or {}
    position = nearest_position(series, incident.started_at) or {}
    base = {
        "incident_type": incident.incident_type,
        "severity": incident.severity,
        "started_at": incident.started_at,
        "position": position,
    }
    if incident.incident_type == "attitude_shock":
        attitude = (ev.get("sample") or {}).get("attitude") or {}
        roll = _num(attitude.get("roll_deg")) or 0.0
        pitch = _num(attitude.get("pitch_deg")) or 0.0
        base["narrative"] = (
            f"Roll reached {roll:.1f} deg and pitch {pitch:.1f} deg at {incident.started_at}, "
            f"beyond the {ATTITUDE_WARN_DEG:.0f} deg stable-flight envelope. Consistent with an "
            "aggressive control input, a gust upset, or a momentary loss of control authority -- "
            "not distinguishable from telemetry alone."
        )
        base["values"] = {"roll_deg": roll, "pitch_deg": pitch}
    elif incident.incident_type == "gps_jump":
        distance_m = _num(ev.get("distance_m")) or 0.0
        speed_mps = _num(ev.get("speed_mps")) or 0.0
        limit_mps = _num(ev.get("limit_mps")) or 0.0
        base["narrative"] = (
            f"Position implied a {speed_mps:.1f} m/s displacement ({distance_m:.1f} m in one "
            f"sample) at {incident.started_at}, above the {limit_mps:.0f} m/s plausible-flight "
            "ceiling for this vehicle family. More likely a GPS fix glitch or multipath than an "
            "actual maneuver -- worth a GPS fix-quality/HDOP check if that field is ever captured."
        )
        base["values"] = {"distance_m": distance_m, "speed_mps": speed_mps, "limit_mps": limit_mps}
    elif incident.incident_type == "altitude_spike":
        d_alt_m = _num(ev.get("d_alt_m")) or 0.0
        rate_mps = _num(ev.get("rate_mps")) or 0.0
        base["narrative"] = (
            f"Altitude changed {d_alt_m:.1f} m ({rate_mps:.1f} m/s) between consecutive samples "
            f"at {incident.started_at}, faster than a normal climb/descent rate for this vehicle "
            "family. Consistent with a barometer glitch, a downdraft, or an aggressive throttle "
            "command."
        )
        base["values"] = {"d_alt_m": d_alt_m, "rate_mps": rate_mps}
    else:
        base["narrative"] = incident.summary
        base["values"] = {}
    return base


def _link_reliability(series: list[dict[str, Any]], incidents: list[Any]) -> dict[str, Any]:
    gap_incidents = [i for i in incidents if i.incident_type == "telemetry_gap"]
    dropout_count = len(gap_incidents)
    total_downtime_s = 0.0
    worst_gap_s = 0.0
    for inc in gap_incidents:
        dt = _num((inc.evidence or {}).get("dt_s")) or 0.0
        total_downtime_s += dt
        worst_gap_s = max(worst_gap_s, dt)

    keyword_hits: list[dict[str, str]] = []
    signal_values: list[float] = []
    for sample in series:
        sensors = sample.get("sensors") or {}
        extra = sensors.get("extra") if isinstance(sensors.get("extra"), dict) else {}
        text = " ".join(str(v) for v in (sensors.get("warning"), sensors.get("tip")) if v)
        lowered = text.lower()
        if text and any(k in lowered for k in LINK_KEYWORDS):
            keyword_hits.append({"timestamp_utc": sample.get("timestamp_utc") or "", "text": text})
        sig = _num(extra.get("signal_pct")) if extra else None
        if sig is not None:
            signal_values.append(sig)

    signal_stats = None
    if signal_values:
        signal_stats = {
            "min": min(signal_values),
            "max": max(signal_values),
            "avg": sum(signal_values) / len(signal_values),
            "samples": len(signal_values),
        }

    narrative_parts = []
    if dropout_count:
        narrative_parts.append(
            f"{dropout_count} telemetry dropout(s) totaling {total_downtime_s:.0f}s "
            f"(worst single gap {worst_gap_s:.0f}s, threshold {GAP_S:.0f}s)."
        )
    if keyword_hits:
        narrative_parts.append(f"{len(keyword_hits)} operator warning(s) referenced link/signal issues.")
    if signal_stats and signal_stats["min"] < 50:
        narrative_parts.append(
            f"Reported signal strength dropped as low as {signal_stats['min']:.0f}% during the flight."
        )
    if not narrative_parts:
        narrative_parts.append("No telemetry dropouts, link-related warnings, or low signal readings found.")

    return {
        "dropout_count": dropout_count,
        "total_downtime_s": round(total_downtime_s, 1),
        "worst_gap_s": round(worst_gap_s, 1),
        "keyword_warnings": keyword_hits[:20],
        "signal_stats": signal_stats,
        "narrative": " ".join(narrative_parts),
        "disclosure": (
            "This platform records no audio between operator and controller. This section reports "
            "RF telemetry link reliability -- dropout gaps, link-related operator warnings, and "
            "signal-strength readings where captured -- as the closest measurable proxy."
        ),
    }


def _image_quality(data: bytes) -> dict[str, Any] | None:
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        return None
    try:
        img = Image.open(io.BytesIO(data)).convert("L")
    except Exception:
        return None
    histogram = img.histogram()
    total = sum(histogram) or 1
    brightness_mean = sum(i * count for i, count in enumerate(histogram)) / total

    edges = img.filter(ImageFilter.FIND_EDGES)
    edge_hist = edges.histogram()
    edge_total = sum(edge_hist) or 1
    edge_mean = sum(i * count for i, count in enumerate(edge_hist)) / edge_total
    edge_variance = sum(count * (i - edge_mean) ** 2 for i, count in enumerate(edge_hist)) / edge_total

    flags = []
    if brightness_mean >= BRIGHTNESS_OVEREXPOSED:
        flags.append("overexposed")
    elif brightness_mean <= BRIGHTNESS_UNDEREXPOSED:
        flags.append("underexposed")
    if edge_variance < BLUR_EDGE_VARIANCE_FLOOR:
        flags.append("low-detail / possibly blurred")

    return {
        "brightness_mean": round(brightness_mean, 1),
        "edge_variance": round(edge_variance, 1),
        "flags": flags,
    }


def _camera_reliability(flight_id: str) -> dict[str, Any]:
    visuals = [v for v in list_visuals(flight_id, kind="camera_frame", limit=10_000) if v.get("recorded_at")]
    if not visuals:
        return {
            "available": False,
            "narrative": "No camera_frame visuals recorded for this flight.",
            "disclosure": (
                "This section covers measurable image quality (exposure, a coarse blur proxy) at "
                "captured frames. It does not classify terrain -- no terrain label exists anywhere "
                "in this platform's telemetry or vision data yet."
            ),
        }

    visuals.sort(key=lambda v: v["recorded_at"])
    lag_events: list[dict[str, Any]] = []
    for prev, curr in zip(visuals, visuals[1:]):
        prev_ts = parse_timestamp(prev["recorded_at"])
        curr_ts = parse_timestamp(curr["recorded_at"])
        if not prev_ts or not curr_ts:
            continue
        gap_s = (curr_ts - prev_ts).total_seconds()
        if gap_s > ASSUMED_FRAME_INTERVAL_S * FRAME_LAG_MULTIPLIER:
            lag_events.append({
                "gap_s": round(gap_s, 1),
                "from": prev["recorded_at"],
                "to": curr["recorded_at"],
            })

    sample_targets = visuals[:MAX_FRAMES_QUALITY_SAMPLED]
    quality_samples: list[dict[str, Any]] = []
    for visual in sample_targets:
        path = resolve_visual_path(visual["id"])
        if path is None or not path.exists():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        quality = _image_quality(data)
        if quality is None:
            continue
        quality_samples.append({
            "visual_id": visual["id"],
            "recorded_at": visual["recorded_at"],
            **quality,
        })

    flagged = [q for q in quality_samples if q["flags"]]
    census_rows = list_frame_census(flight_id)
    census_summary = None
    if census_rows:
        totals: dict[str, int] = {}
        for row in census_rows:
            for name, count in (row["census"].get("class_counts") or {}).items():
                totals[name] = totals.get(name, 0) + int(count)
        census_summary = {"frames_with_census": len(census_rows), "class_totals": totals}

    narrative_parts = [f"{len(visuals)} camera frame(s) recorded."]
    if lag_events:
        narrative_parts.append(
            f"{len(lag_events)} gap(s) between frames exceeded "
            f"{ASSUMED_FRAME_INTERVAL_S * FRAME_LAG_MULTIPLIER:.0f}s (assumed nominal cadence "
            f"{ASSUMED_FRAME_INTERVAL_S:.0f}s) -- a possible image-lag or dropped-frame signal."
        )
    if flagged:
        narrative_parts.append(f"{len(flagged)} of {len(quality_samples)} sampled frame(s) flagged for exposure or blur.")
    if not lag_events and not flagged:
        narrative_parts.append("No frame-cadence gaps or image-quality flags found in the sampled frames.")

    return {
        "available": True,
        "total_frames": len(visuals),
        "lag_events": lag_events,
        "quality_samples": quality_samples,
        "flagged_frame_count": len(flagged),
        "census_summary": census_summary,
        "narrative": " ".join(narrative_parts),
        "disclosure": (
            "This section covers measurable image quality (exposure, a coarse blur proxy) and frame "
            "cadence at captured frames. It does not classify terrain -- no terrain label exists "
            "anywhere in this platform's telemetry or vision data yet; a future GPS+land-cover join "
            "would be needed for genuine terrain-conditioned camera guidance."
        ),
    }


def _recommendations(
    incidents: list[Any],
    link: dict[str, Any],
    camera: dict[str, Any],
) -> list[str]:
    types_present = {i.incident_type for i in incidents}
    recs: list[str] = []

    if types_present & {"battery_low", "battery_critical", "battery_plunge"}:
        recs.append(
            "Battery threshold(s) were crossed this flight -- run a preflight cell-resistance / "
            "capacity check before the next sortie, and confirm the RTH battery margin matches this "
            "airframe's actual drain rate rather than a nameplate figure."
        )
    if link["dropout_count"] > 0 or link["keyword_warnings"]:
        recs.append(
            f"Link reliability findings this flight ({link['dropout_count']} dropout(s)) suggest "
            "reviewing antenna placement/orientation and considering a closer standoff distance or "
            "a redundant telemetry radio for the next mission in similar conditions."
        )
    if types_present & MANEUVER_INCIDENT_TYPES:
        recs.append(
            "One or more maneuver/physics-threshold incidents were flagged -- review the marked "
            "timestamps in replay against planned waypoints to confirm whether they were commanded "
            "maneuvers, gusts, or sensor glitches before repeating this flight path."
        )
    if camera.get("lag_events"):
        recs.append(
            "Camera frame cadence showed gap(s) beyond the assumed nominal interval -- check the "
            "video downlink margin and onboard storage write speed before the next flight."
        )
    if camera.get("flagged_frame_count"):
        recs.append(
            "Sampled frames were flagged for exposure or blur -- check gimbal stabilization and "
            "camera exposure settings before flying this route again, particularly around the "
            "flagged timestamps."
        )
    if types_present & UXO_INCIDENT_TYPES:
        recs.append(
            "A possible-loss signature (mission incomplete or frozen last-known-position) was "
            "flagged. Treat the last-known position as a potential hazard area -- warhead/payload "
            "state unknown, do not approach -- and brief this before any recovery attempt."
        )
    if not recs:
        recs.append(
            "No incidents or reliability flags were found on this flight. No preemptive changes are "
            "indicated from this log alone."
        )
    return recs


def build_comprehensive_report(conn, flight_id: str, *, allow_llm: bool = True) -> dict[str, Any]:
    """Combine the evidence-backed incident report, the pre-emptive planning
    findings, and any fleet-wide recurring-pattern matches for one flight into
    a single document. Reuses the three functions already built for mission
    planning (generate_structured_report, build_preemptive_report, list_patterns)
    rather than recomputing anything -- this is a synthesis layer, not a new
    source of findings.
    """
    from app.analytics import generate_structured_report
    from app.incidents import list_patterns

    flight = conn.execute("SELECT id FROM flights WHERE id = ?", (flight_id,)).fetchone()
    if not flight:
        raise KeyError(flight_id)

    incident_report = generate_structured_report(flight_id, allow_llm=allow_llm)
    preemptive = build_preemptive_report(conn, flight_id)

    own_signatures = {
        row["signature"]
        for row in conn.execute(
            """
            SELECT DISTINCT signature FROM incidents
            WHERE flight_id = ? AND detector = 'rule' AND signature IS NOT NULL
            """,
            (flight_id,),
        ).fetchall()
    }
    recurring_pattern_matches = [p for p in list_patterns(min_flights=2) if p["signature"] in own_signatures]

    return {
        "flight_id": flight_id,
        "brand": preemptive["brand"],
        "brand_name": preemptive["brand_name"],
        "generated_at": _iso_now(),
        "incident_report": incident_report,
        "preemptive_findings": preemptive,
        "recurring_pattern_matches": recurring_pattern_matches,
        "limitations": (
            "This document combines the evidence-backed incident report, pre-emptive planning "
            "findings, and any fleet-wide recurring-pattern matches for this flight. Each section "
            "carries its own scope and limitations -- read them individually before acting. A shared "
            "pattern signature is a reason to compare evidence across flights, not proof of a shared "
            "cause."
        ),
    }


def build_preemptive_report(conn, flight_id: str) -> dict[str, Any]:
    """Assemble the full pre-emptive report as a structured dict. No side effects."""
    flight = conn.execute("SELECT id, source FROM flights WHERE id = ?", (flight_id,)).fetchone()
    if not flight:
        raise KeyError(flight_id)

    series, origin = load_flight_series(conn, flight_id)
    brand = identify_brand(series[0] if series else {}, source=flight["source"])
    incidents = detect_incidents(series)

    incident_summary: dict[str, int] = {}
    for inc in incidents:
        incident_summary[inc.incident_type] = incident_summary.get(inc.incident_type, 0) + 1

    maneuver_findings = [
        _describe_maneuver(inc, series) for inc in incidents if inc.incident_type in MANEUVER_INCIDENT_TYPES
    ]
    link = _link_reliability(series, incidents)
    camera = _camera_reliability(flight_id)
    recommendations = _recommendations(incidents, link, camera)

    return {
        "flight_id": flight_id,
        "brand": brand.id,
        "brand_name": brand.name,
        "generated_at": _iso_now(),
        "sample_count": len(series),
        "sample_origin": origin,
        "incident_count": len(incidents),
        "incident_summary": incident_summary,
        "maneuver_findings": maneuver_findings,
        "link_reliability": link,
        "camera_reliability": camera,
        "recommendations": recommendations,
        "limitations": (
            "Generated deterministically from recorded telemetry, detector output, and stored "
            "visual/census rows -- no audio channel, no terrain labels, and no causal fault "
            "diagnosis. Pattern-matched recommendations, not verified root causes. Requires human "
            "review before any operational change."
        ),
    }
