#!/usr/bin/env python3
"""Independently audit an SDTH simulator corpus without changing its inputs.

The audit intentionally tests the deployed parser -> deterministic L2 -> detector
path rather than simulator internals.  It reports scenario labels as injected test
conditions, never as confirmed operational causes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import os
import platform
import signal
import shutil
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "sdth-telemetry" / "platform-api"
PARSERS_ROOT = ROOT / "sdth-telemetry"
SCENARIOS_ROOT = ROOT / "sdth-synth" / "scenarios" / "hazards"

for entry in (str(API_ROOT), str(PARSERS_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from app.canonical_series import series_from_l1_payload  # noqa: E402
from app.detectors import detect_incidents, hazard_label, parse_timestamp  # noqa: E402
from app.schemas import CANONICAL_JSON_SCHEMA  # noqa: E402
from parsers.registry import parse_raw_log  # noqa: E402

try:
    import jsonschema
except ImportError as exc:  # pragma: no cover - prerequisite error is useful
    raise SystemExit("jsonschema is required; run using the repository virtualenv") from exc

_CANONICAL_VALIDATOR_CLASS = jsonschema.validators.validator_for(CANONICAL_JSON_SCHEMA)
_CANONICAL_VALIDATOR_CLASS.check_schema(CANONICAL_JSON_SCHEMA)
CANONICAL_VALIDATOR = _CANONICAL_VALIDATOR_CLASS(CANONICAL_JSON_SCHEMA)


# Expectations are intentionally detector-level, based on the checked-in scenario
# cards.  A warning confirms that the injected record survives conversion; it does
# not independently establish any RF, mechanical, or operational cause.
EXPECTED_DETECTIONS = {
    "battery_critical": {"battery_critical"},
    "battery_low_rth": {"battery_low"},
    "c2_link_lost": {"operator_warning"},
    "compass_error": {"operator_warning"},
    "gps_jamming": {"operator_warning"},
    "gps_denied_frozen": {"last_known_position"},
    "kinetic_tumble_cut": {"attitude_shock", "mission_incomplete"},
    "logger_dropout": {"telemetry_gap"},
    "lost_airborne": {"mission_incomplete"},
    "motor_fail_recover": {"attitude_shock", "operator_warning"},
    # V2-only multi-condition synthetic scenarios.  These are recorded as
    # multiple observable conditions, not a causal attribution.
    "battery_critical_logger_dropout": {"battery_critical", "telemetry_gap"},
    "gps_weak_midair_end": {"operator_warning", "mission_incomplete"},
}

FORMAT_CLASS = {
    "dji_csv": "simulated kinematic format export",
    "dji_excel": "simulated kinematic format export",
    "hermes900": "simulated kinematic format export",
    "orbiter4": "simulated kinematic format export",
    "aunav": "simulated kinematic format export",
    "vendor_hex": "simulated mock/minimal format export",
    "px4_ulg": "SITL log artifact",
    "ardupilot_bin": "SITL log artifact",
    "ardupilot_tlog": "SITL log artifact",
}


def scenario_from_name(path: Path) -> str | None:
    stem = path.stem
    for scenario in sorted(EXPECTED_DETECTIONS, key=len, reverse=True):
        # V2 independent variants append their own numeric suffix, for example
        # dji_csv_gps_jamming_022.  A scenario must still occupy a complete
        # underscore-delimited component, so a partial label cannot match.
        if stem.endswith(f"_{scenario}") or f"_{scenario}_" in stem:
            return scenario
    return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite_numbers(value: Any) -> bool:
    if isinstance(value, dict):
        return all(finite_numbers(item) for item in value.values())
    if isinstance(value, list):
        return all(finite_numbers(item) for item in value)
    return not isinstance(value, float) or math.isfinite(value)


def iso_timestamp(value: str) -> datetime | None:
    return parse_timestamp(value)


class DetectorTimeout(TimeoutError):
    pass


def _timeout_handler(_signum: int, _frame: Any) -> None:
    raise DetectorTimeout("detector exceeded the per-file 15 second audit limit")


def _get_path(value: dict[str, Any], keys: tuple[str, ...]) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _coarse_observable_present(series: list[dict[str, Any]], incident_type: str) -> bool:
    """Whether this log visibly carries a coarse prerequisite of one rule.

    This inventory diagnostic is deliberately not the rule implementation or an
    independent ground-truth measurement. A missing observable is neither a
    negative detector result nor a scenario failure.
    """
    if not series:
        return False
    if incident_type == "operator_warning":
        return any(
            any(str((sample.get("sensors") or {}).get(key) or "").strip() for key in ("warning", "tip"))
            for sample in series
        )
    if incident_type == "battery_critical":
        return any(0 < float((sample.get("battery") or {}).get("percent") or 0) <= 10 for sample in series)
    if incident_type == "battery_low":
        return any(0 < float((sample.get("battery") or {}).get("percent") or 0) <= 20 for sample in series)
    if incident_type == "attitude_shock":
        return any(
            max(
                abs(float((sample.get("attitude") or {}).get("roll_deg") or 0)),
                abs(float((sample.get("attitude") or {}).get("pitch_deg") or 0)),
            ) >= 40
            for sample in series
        )
    if incident_type == "telemetry_gap":
        stamps = [parse_timestamp(sample.get("timestamp_utc")) for sample in series]
        return any(left and right and (right - left).total_seconds() >= 15 for left, right in zip(stamps, stamps[1:]))
    if incident_type == "mission_incomplete":
        final_mode = str((series[-1].get("sensors") or {}).get("flight_mode") or series[-1].get("flight_mode") or "").upper()
        return final_mode in AIRBORNE_MODE_TOKENS
    if incident_type == "last_known_position":
        # Evidence needs an actual stable position with concurrent attitude change,
        # not simply a label or a zero-filled canonical placeholder.
        frozen_start: int | None = None
        for index in range(1, len(series)):
            before, current = series[index - 1], series[index]
            a, b = before.get("position") or {}, current.get("position") or {}
            lat_a, lon_a = a.get("lat"), a.get("lon")
            lat_b, lon_b = b.get("lat"), b.get("lon")
            valid_coordinates = all(isinstance(value, (int, float)) and math.isfinite(value) for value in (lat_a, lon_a, lat_b, lon_b))
            non_default_coordinates = not (lat_a == lon_a == lat_b == lon_b == 0)
            unchanged = valid_coordinates and non_default_coordinates and lat_a == lat_b and lon_a == lon_b
            if unchanged:
                frozen_start = index - 1 if frozen_start is None else frozen_start
                start_ts, now_ts = parse_timestamp(series[frozen_start].get("timestamp_utc")), parse_timestamp(current.get("timestamp_utc"))
                if start_ts and now_ts and (now_ts - start_ts).total_seconds() > 30:
                    att_a, att_b = before.get("attitude") or {}, current.get("attitude") or {}
                    yaw_delta = abs(float(att_b.get("yaw_deg") or 0) - float(att_a.get("yaw_deg") or 0))
                    roll_delta = abs(float(att_b.get("roll_deg") or 0) - float(att_a.get("roll_deg") or 0))
                    if max(yaw_delta, roll_delta) > 2:
                        return True
            else:
                frozen_start = None
        return False
    return False


AIRBORNE_MODE_TOKENS = frozenset({"P-GPS", "ATTI", "LOITER", "ALTHOLD", "RTL", "SMART_RTH", "POSITION", "GUIDED", "AUTO", "ORBIT", "FBWA", "FLIP", "ACRO", "STABILIZE", "SPORT", "MOVIE", "CINE", "TRIP"})


# Canonical-field coverage aliases evaluated against raw L1 records (not L2,
# which back-fills 0.0).  Used by --real runs.
COVERAGE_FIELDS: list[tuple[str, tuple[str, ...]]] = [
    ("position.lat", ("lat",)),
    ("position.lon", ("lon",)),
    ("position.alt_m", ("alt_m", "alt", "alt_msl", "pos_z", "up_m")),
    ("local_ned_inputs", ("north_m", "pos_x")),
    ("attitude.roll_deg", ("roll_deg", "roll")),
    ("attitude.pitch_deg", ("pitch_deg", "pitch")),
    ("attitude.yaw_deg", ("yaw_deg", "yaw", "heading")),
    ("battery.percent", ("battery_pct", "percent")),
    ("battery.voltage_v", ("battery_v", "voltage_v")),
    ("sensors.warning", ("warning",)),
    ("sensors.flight_mode", ("flight_mode",)),
    ("sensors.gps_satellites", ("gps_satellites",)),
]


def l1_field_coverage(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-canonical-field presence across L1 payload records.

    A field is ``observed`` when any alias carries a non-empty value in at
    least half the records, ``partial`` below that, ``absent`` at zero.
    """
    total = len(records)
    row: dict[str, dict[str, Any]] = {}
    for name, aliases in COVERAGE_FIELDS:
        hits = sum(
            1
            for record in records
            if isinstance(record, dict) and any(record.get(alias) not in (None, "") for alias in aliases)
        )
        fraction = hits / total if total else 0.0
        status = "observed" if fraction >= 0.5 else ("partial" if fraction > 0 else "absent")
        row[name] = {"status": status, "fraction": round(fraction, 4)}
    return row


def write_coverage_matrix(results: list[dict[str, Any]], out: Path) -> None:
    """Emit coverage-matrix.json and coverage-matrix.md for --real audits."""
    rows = [
        {
            "file": item["path"],
            "parser": item.get("parser") or "unparsed",
            "records": item.get("l1_records", 0),
            "fields": item.get("coverage") or {},
            "incident_types": item.get("detected_incident_types") or [],
        }
        for item in results
    ]
    (out / "coverage-matrix.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    names = [name for name, _ in COVERAGE_FIELDS]
    marks = {"observed": "O", "partial": "p", "absent": "-"}
    lines = [
        "| file | " + " | ".join(names) + " | incidents |",
        "|---|" + "---|" * len(names) + "---|",
    ]
    last_parser: str | None = None
    for row in sorted(rows, key=lambda r: (r["parser"], r["file"])):
        if row["parser"] != last_parser:
            last_parser = row["parser"]
            lines.append(f"| **{last_parser}** |" + " |" * (len(names) + 1))
        cells = []
        for name in names:
            field = row["fields"].get(name) or {}
            cells.append(f"{marks.get(field.get('status'), '?')} {field.get('fraction', 0):.2f}")
        lines.append(f"| `{row['file']}` | " + " | ".join(cells) + f" | {', '.join(row['incident_types']) or '-'} |")
    (out / "coverage-matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def audit_one(path: Path, root: Path, real: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    item: dict[str, Any] = {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "scenario": scenario_from_name(path),
        "parse_ok": False,
        "canonical_schema_valid": False,
        "canonical_required_fields_non_null": False,
        "timestamps_monotonic": False,
        "canonical_numeric_fields_finite": False,
        "detection_expectation_met": None if real else False,
    }
    try:
        parse_started = time.perf_counter()
        payload, parser = parse_raw_log(path, sha256=item["sha256"], original_name=path.name)
        item["parse_elapsed_ms"] = round((time.perf_counter() - parse_started) * 1000, 1)
        canonical_started = time.perf_counter()
        series = series_from_l1_payload(payload)
        item["canonical_elapsed_ms"] = round((time.perf_counter() - canonical_started) * 1000, 1)
        item.update(
            parser=parser,
            classification=FORMAT_CLASS.get(parser, "unclassified"),
            parse_ok=True,
            l1_records=len(payload.get("records") or []),
            canonical_records=len(series),
            source=payload.get("source"),
        )
        schema_errors = []
        for sample in series:
            try:
                CANONICAL_VALIDATOR.validate(sample)
            except jsonschema.ValidationError as exc:
                schema_errors.append(exc.message)
        item["canonical_schema_valid"] = not schema_errors
        if schema_errors:
            item["schema_errors"] = schema_errors[:3]

        required_paths = (
            ("flight_id",), ("timestamp_utc",), ("position", "lat"), ("position", "lon"),
            ("position", "alt_m"), ("attitude", "roll_deg"), ("attitude", "pitch_deg"),
            ("attitude", "yaw_deg"), ("battery", "percent"), ("battery", "voltage_v"),
        )
        item["canonical_required_fields_non_null"] = all(
            all(_get_path(sample, keys) is not None for keys in required_paths) for sample in series
        )
        timestamps = [iso_timestamp(str(sample.get("timestamp_utc") or "")) for sample in series]
        item["invalid_timestamp_count"] = sum(ts is None for ts in timestamps)
        item["timestamps_monotonic"] = bool(series) and not item["invalid_timestamp_count"] and all(
            left <= right for left, right in zip(timestamps, timestamps[1:]) if left and right
        )
        item["canonical_numeric_fields_finite"] = all(finite_numbers(sample) for sample in series)
        if real:
            item["coverage"] = l1_field_coverage(payload.get("records") or [])
        expected = EXPECTED_DETECTIONS.get(item["scenario"], set())
        item["expected_incident_types"] = sorted(expected)
        if not real:
            item["coarse_observable_expected_types"] = sorted(
                incident for incident in expected if _coarse_observable_present(series, incident)
            )
            item["coarse_observable_missing_expected_types"] = sorted(
                expected - set(item["coarse_observable_expected_types"])
            )
        detected: list[str] = []
        detector_started = time.perf_counter()
        # SIGALRM/setitimer are POSIX-only; this whole per-file audit already runs
        # inside its own mp.Process with a hard --timeout-s boundary (see main()),
        # which is cross-platform and covers the same "one pathological file can't
        # hang the audit" concern. On platforms with SIGALRM, keep the tighter
        # 15-second inner bound as defense in depth; elsewhere, rely on the outer
        # process boundary alone rather than fabricate a new timeout mechanism.
        has_sigalrm = hasattr(signal, "SIGALRM")
        previous_handler = signal.signal(signal.SIGALRM, _timeout_handler) if has_sigalrm else None
        try:
            if has_sigalrm:
                signal.setitimer(signal.ITIMER_REAL, 15.0)
            incidents = detect_incidents(series)
            detected = sorted({incident.incident_type for incident in incidents})
            labels = sorted(
                {
                    label
                    for incident in incidents
                    if (label := hazard_label(incident, series, incidents)) is not None
                }
            )
            item["detector_completed"] = True
            item["detected_incident_types"] = detected
            item["derived_hazard_labels"] = labels
        except DetectorTimeout as exc:
            item["detector_completed"] = False
            item["detector_error"] = str(exc)
            item["detected_incident_types"] = []
            item["derived_hazard_labels"] = []
        finally:
            if has_sigalrm:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous_handler)
        item["detector_elapsed_ms"] = round((time.perf_counter() - detector_started) * 1000, 1)
        if not real:
            item["missing_expected_incident_types"] = sorted(expected - set(detected))
            item["detection_expectation_met"] = not item["missing_expected_incident_types"]
    except Exception as exc:  # Record all parser failures rather than stop corpus accounting.
        item["error"] = f"{type(exc).__name__}: {exc}"
    item["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return item


def _audit_child(path_string: str, root_string: str, queue: Any, real: bool = False) -> None:
    """Run one complete parser/L2/detector pass in a killable child process."""
    try:
        queue.put(audit_one(Path(path_string), Path(root_string), real=real))
    except BaseException as exc:  # pragma: no cover - child crash accounting
        queue.put({"path": str(Path(path_string).relative_to(root_string)), "parse_ok": False, "error": f"child {type(exc).__name__}: {exc}"})


def run_isolated_e2e(paths: list[Path], output_dir: Path) -> dict[str, Any]:
    """Exercise multipart upload, worker parsing, L2 persistence, indexing and replay query.

    This writes only an isolated temporary SQLite database and upload spool under
    the evidence directory.  Queue and LLM calls are replaced locally so the test
    remains deterministic and does not contact Redis/Ollama.
    """
    from fastapi.testclient import TestClient

    temp_dir = Path(tempfile.mkdtemp(prefix="submission-e2e-", dir=output_dir))
    try:
        from app.config import settings
        from app.db import db_session
        from app.main import app
        import app.ingest as ingest
        import app.worker as worker

        settings.database_path = str(temp_dir / "audit.db")
        settings.raw_upload_dir = str(temp_dir / "uploads")
        settings.ingest_api_keys = "corpus-audit-key"
        # Newer app revisions expose this switch; keep the audit independent of
        # optional model enrichment either way.
        if hasattr(settings, "ingest_model_enrichment"):
            settings.ingest_model_enrichment = False
        queued: list[str] = []
        ingest.enqueue_raw_upload = lambda _job: None
        ingest.enqueue_translation_job = queued.append
        worker.enqueue_translation_job = queued.append
        worker.translate_with_repair = lambda _payload: (_ for _ in ()).throw(RuntimeError("audit: LLM disabled"))
        outcomes: list[dict[str, Any]] = []
        began = time.perf_counter()
        with TestClient(app) as client:
            for path in paths:
                response = client.post(
                    "/v1/logs/upload",
                    files={"file": (path.name, path.read_bytes())},
                    headers={"Authorization": "Bearer corpus-audit-key"},
                )
                outcome: dict[str, Any] = {"path": path.name, "upload_status_code": response.status_code}
                if response.status_code == 202:
                    upload_id = response.json()["upload_id"]
                    worker.process_raw_upload(upload_id)
                    if queued:
                        worker.process_job(queued.pop(0))
                    status = client.get(f"/v1/uploads/{upload_id}", headers={"Authorization": "Bearer corpus-audit-key"})
                    outcome["upload"] = status.json()
                    flight_id = status.json().get("flight_id")
                    if flight_id:
                        path_response = client.get(f"/v1/flights/{flight_id}/path", headers={"Authorization": "Bearer corpus-audit-key"})
                        incident_response = client.get(f"/v1/flights/{flight_id}/incidents", headers={"Authorization": "Bearer corpus-audit-key"})
                        outcome["replay_path_status_code"] = path_response.status_code
                        outcome["replay_sample_count"] = path_response.json().get("count") if path_response.status_code == 200 else None
                        outcome["incident_query_status_code"] = incident_response.status_code
                        outcome["incident_types"] = sorted({row["incident_type"] for row in incident_response.json().get("items", [])}) if incident_response.status_code == 200 else []
                        with db_session() as conn:
                            outcome["canonical_record_count"] = conn.execute("SELECT count(*) FROM canonical_records WHERE flight_id = ?", (flight_id,)).fetchone()[0]
                outcomes.append(outcome)
        return {
            "performed": True,
            "isolated_db": True,
            "representatives": outcomes,
            "elapsed_ms": round((time.perf_counter() - began) * 1000, 1),
        }
    except Exception as exc:
        return {"performed": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--e2e", action="store_true")
    parser.add_argument(
        "--real",
        action="store_true",
        help="Audit real recorded logs: skip scenario-card expectations and emit an L1 field coverage matrix.",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=30.0,
        help="Whole parser-to-detector subprocess limit per file (default: 30 seconds).",
    )
    args = parser.parse_args()
    root = args.input.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    metadata_names = {"manifest.json", "fixture-manifest.json", "corpus_manifest.json", "INVENTORY.json"}
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name not in metadata_names)
    began = time.perf_counter()
    results: list[dict[str, Any]] = []
    # The application parser/detector path handles large binary streams.  Put a
    # hard process boundary around each member so one pathological member cannot
    # make the audit itself unbounded.  A timeout is retained as an outcome.
    for path in files:
        queue: Any = mp.Queue()
        child = mp.Process(target=_audit_child, args=(str(path), str(root), queue, args.real))
        child.start()
        child.join(args.timeout_s)
        if child.is_alive():
            child.terminate()
            child.join()
            item = {
                "path": str(path.relative_to(root)), "bytes": path.stat().st_size,
                "sha256": sha256(path), "scenario": scenario_from_name(path),
                "parse_ok": False, "canonical_schema_valid": False,
                "canonical_required_fields_non_null": False, "timestamps_monotonic": False,
                "canonical_numeric_fields_finite": False, "detection_expectation_met": None if args.real else False,
                "audit_timeout": True,
                "error": f"parser/L2/detector path exceeded chosen {args.timeout_s:g} second per-file limit",
            }
        else:
            try:
                item = queue.get(timeout=1.0)
            except Exception:
                item = {
                    "path": str(path.relative_to(root)), "bytes": path.stat().st_size,
                    "sha256": sha256(path), "scenario": scenario_from_name(path),
                    "parse_ok": False, "canonical_schema_valid": False,
                    "canonical_required_fields_non_null": False, "timestamps_monotonic": False,
                    "canonical_numeric_fields_finite": False, "detection_expectation_met": None if args.real else False,
                    "error": f"audit child exited {child.exitcode} without a result",
                }
        results.append(item)
        (out / "corpus-validation-progress.json").write_text(
            json.dumps({"completed": len(results), "total": len(files), "files_detail": results}, indent=2) + "\n",
            encoding="utf-8",
        )
    by_parser = Counter(item.get("parser", "unparsed") for item in results)
    by_scenario: dict[str, dict[str, Any]] = {}
    for scenario in sorted(EXPECTED_DETECTIONS):
        members = [item for item in results if item.get("scenario") == scenario]
        by_scenario[scenario] = {
            "format_exports": len(members),
            "parse_successes": sum(item["parse_ok"] for item in members),
            "expectation_met": sum(item["detection_expectation_met"] for item in members),
            "expected_incident_types": sorted(EXPECTED_DETECTIONS[scenario]),
        }
    # One generator run per scenario card, represented by multiple skins.  The
    # inference follows filename+scenario structure and is not a provenance claim.
    unique_scenarios = sorted({item["scenario"] for item in results if item.get("scenario")})
    report: dict[str, Any] = {
        "audit_name": "WISL submission corpus independent validation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": str(root),
        "criteria": {
            "parse_success": "parse_raw_log returns an L1 payload",
            "canonical_schema": "each parser record projects to L2 and validates against CANONICAL_JSON_SCHEMA",
            "integrity": "required canonical scalar fields are non-null; timestamps parse and are non-decreasing; all canonical numeric fields are finite",
            "scenario_expectations": "scenario-card injected conditions are compared with detector types; results do not prove real-world causes",
            "coarse_observable_inventory": "coarse record-input diagnostic only; it is not a detector predicate, independent ground truth, or detector-accuracy measure",
            "independence": "format skins of the same scenario are counted as one simulated mission, not recurrence evidence",
        },
        "environment": {"python": sys.version, "platform": platform.platform(), "cwd": os.getcwd()},
        "totals": {
            "files": len(results),
            "parse_successes": sum(item["parse_ok"] for item in results),
            "schema_valid_files": sum(item["canonical_schema_valid"] for item in results),
            "non_null_canonical_files": sum(item["canonical_required_fields_non_null"] for item in results),
            "monotonic_timestamp_files": sum(item["timestamps_monotonic"] for item in results),
            "finite_numeric_files": sum(item["canonical_numeric_fields_finite"] for item in results),
            "detection_expectations_met": sum(1 for item in results if item.get("detection_expectation_met")),
            "detector_completed_files": sum(item.get("detector_completed", False) for item in results),
            "detector_timeout_files": sum("detector_error" in item for item in results),
            "whole_path_timeout_files": sum(item.get("audit_timeout", False) for item in results),
            "expected_types_with_coarse_observable": sum(len(item.get("coarse_observable_expected_types", [])) for item in results),
            "expected_types_missing_coarse_observable": sum(len(item.get("coarse_observable_missing_expected_types", [])) for item in results),
            "unique_simulated_scenarios": len(unique_scenarios),
            "normal_control_present": any("normal_control" in item["path"] for item in results),
        },
        "format_parser_counts": dict(sorted(by_parser.items())),
        "scenario_summary": by_scenario,
        "independence": {
            "inferred_unique_missions": unique_scenarios,
            "format_exports_per_scenario": {scenario: by_scenario[scenario]["format_exports"] for scenario in unique_scenarios},
            "qualified_same_signature_recurrence_pair": None,
            "comparison_pair_not_recurrence_evidence": ["gps_jamming", "gps_denied_frozen"],
            "reason": "Only gps_jamming injects a GPS-weak warning. gps_denied_frozen is a distinct card but has a last_known_position signature, so this corpus cannot demonstrate recurrence of one GPS-weak detector signature.",
        },
        "limitations": [
            "All corpus members are simulator-generated; kinematic skins are format exports and three binary families are SITL artifacts, not field-flight evidence.",
            "No normal/control mission was found in this hazards-only directory.",
            "The `gps_jamming` label denotes an injected GPS-weak warning; the audit does not infer RF jamming from GPS telemetry or warning text.",
            "The detector's `jamming` display label can also arise from a frozen-position heuristic; it remains a triage label, not a causal finding.",
            f"A chosen {args.timeout_s:g}-second subprocess bound is applied to the complete parser/L2/detector path, and a 15-second nested detector bound is retained. Timeouts are reported as processing-performance failures, not silent negative detections.",
            "Root manifest.json names one PX4 file only and does not inventory or checksum this 90-file corpus.",
        ],
        "elapsed_ms": round((time.perf_counter() - began) * 1000, 1),
        "files_detail": results,
    }
    if args.e2e:
        representatives = [
            next((path for path in files if path.name.startswith("dji_csv_gps_jamming")), None),
            next(
                (
                    path
                    for path in files
                    if path.name.startswith("dji_csv_gps_denied_frozen")
                    or path.name.startswith("orbiter4_gps_denied_frozen")
                ),
                None,
            ),
        ]
        report["isolated_upload_processing_e2e"] = run_isolated_e2e([path for path in representatives if path], out)
    (out / "corpus-validation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.real:
        write_coverage_matrix(results, out)
    print(json.dumps(report["totals"], sort_keys=True))
    return 0 if report["totals"]["parse_successes"] == len(files) else 1


if __name__ == "__main__":
    raise SystemExit(main())
