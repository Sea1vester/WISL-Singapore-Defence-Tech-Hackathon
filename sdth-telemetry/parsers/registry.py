"""Single raw-log parser registry producing the WISL L1 ingest contract."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .detect import detect_format
from .dji_csv import parse_dji_csv_to_l1

Parser = Callable[[Path, str, str], dict[str, Any]]

_HERMES_LINE = re.compile(
    r"^<\d+>\d+\s+(?P<timestamp>\S+)\s+(?P<hostname>\S+)\s+\S+\s+\S+\s+\S+\s+\S+\s+"
    r"\[(?P<tag>[^\]]+)\]\s+(?P<message_type>\S+)\s+(?P<kv>.*)$"
)
_AUNAV_LINE = re.compile(
    r"^\[ROS_INFO\]\s+\[(?P<timestamp>[\d.]+)\]\s+(?P<topic>\S+)\s+(?P<kv>.*)$"
)


class UnsupportedLogFormat(ValueError):
    pass


def _coerce(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return float(value)
    except ValueError:
        return value


def _kv(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for token in text.split():
        key, separator, value = token.partition("=")
        if separator:
            fields[key] = _coerce(value)
    return fields


def _payload(
    *,
    flight_id: str,
    event_id: str,
    source: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    if not records:
        raise ValueError(f"No usable telemetry records in {source} log")
    return {
        "flight_id": flight_id,
        "timestamp_utc": records[0]["timestamp_utc"],
        "source": source,
        "event_id": event_id,
        "records": records,
    }


def _parse_hermes(path: Path, flight_id: str, event_id: str) -> dict[str, Any]:
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _HERMES_LINE.match(line.strip())
        if not match:
            continue
        record = _kv(match.group("kv"))
        record.update(
            {
                "timestamp_utc": match.group("timestamp"),
                "drone_model": "Hermes 900",
                "message_type": match.group("message_type"),
            }
        )
        records.append(record)
    return _payload(
        flight_id=flight_id,
        event_id=event_id,
        source="hermes900-stanag",
        records=records,
    )


def _orbiter_record(item: dict[str, Any]) -> dict[str, Any]:
    record = dict(item)
    timestamp_ms = record.pop("timestamp_ms", None)
    if timestamp_ms is not None:
        timestamp = datetime.fromtimestamp(float(timestamp_ms) / 1000, tz=timezone.utc)
        record["timestamp_utc"] = timestamp.isoformat().replace("+00:00", "Z")
    elif not record.get("timestamp_utc"):
        raise ValueError("Orbiter record is missing timestamp_ms or timestamp_utc")
    for key in ("lat", "lon", "alt_m", "roll_deg", "pitch_deg", "yaw_deg", "battery_pct"):
        if key in record and record[key] not in (None, ""):
            record[key] = float(record[key])
    record["drone_model"] = "Orbiter 4"
    return record


def _parse_orbiter(path: Path, flight_id: str, event_id: str) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        loaded = json.loads(path.read_text(encoding="utf-8"))
        items = loaded if isinstance(loaded, list) else [loaded]
    else:
        with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            items = list(csv.DictReader(handle))
    records = [_orbiter_record(item) for item in items if isinstance(item, dict)]
    return _payload(
        flight_id=flight_id,
        event_id=event_id,
        source="orbiter4-json",
        records=records,
    )


def _parse_aunav(path: Path, flight_id: str, event_id: str) -> dict[str, Any]:
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _AUNAV_LINE.match(line.strip())
        if not match:
            continue
        timestamp = datetime.fromtimestamp(float(match.group("timestamp")), tz=timezone.utc)
        record = _kv(match.group("kv"))
        record.update(
            {
                "timestamp_utc": timestamp.isoformat().replace("+00:00", "Z"),
                "drone_model": "aunav.NEO HD",
                "topic": match.group("topic"),
            }
        )
        records.append(record)
    return _payload(
        flight_id=flight_id,
        event_id=event_id,
        source="aunav-ros",
        records=records,
    )


def _parse_hex(path: Path, flight_id: str, event_id: str) -> dict[str, Any]:
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        timestamp, separator, code = line.partition(",")
        if not separator:
            continue
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        code = code.strip()
        records.append(
            {
                "timestamp_utc": timestamp,
                "hex_code": code,
                "warning": f"Vendor error code {code}",
            }
        )
    return _payload(
        flight_id=flight_id,
        event_id=event_id,
        source="vendor-hex",
        records=records,
    )


def detect_registry_format(path: Path, *, original_name: str | None = None) -> str:
    name = (original_name or path.name).lower()
    suffix = Path(name).suffix
    if suffix in {".stanag", ".syslog", ".hermes"}:
        return "hermes900"
    if suffix in {".ros", ".xml", ".aunav"}:
        return "aunav"
    if suffix == ".hex":
        return "vendor_hex"
    if suffix == ".json":
        return "orbiter4"
    if suffix == ".csv" and name.startswith("orbiter"):
        return "orbiter4"
    return detect_format(path)


def stable_identifiers(sha256: str) -> tuple[str, str]:
    token = sha256.lower()[:20]
    return f"flight-{token}", f"upload-{sha256.lower()}"


def parse_raw_log(
    path: Path,
    *,
    sha256: str,
    original_name: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Parse one uploaded file and return `(L1 payload, parser key)`."""
    parser_key = detect_registry_format(path, original_name=original_name)
    flight_id, event_id = stable_identifiers(sha256)

    if parser_key == "dji_csv":
        payload = parse_dji_csv_to_l1(path, flight_id=flight_id, event_id=event_id)
    elif parser_key == "csv_generic":
        from .generic_rows import _parse_generic_rows_to_l1

        with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            rows = list(csv.DictReader(handle))
        payload = _parse_generic_rows_to_l1(
            rows,
            flight_id=flight_id,
            source="csv-generic",
            event_id=event_id,
            stem=path.stem,
        )
    elif parser_key in {"dji_excel", "excel"}:
        from .excel import parse_excel_to_l1

        payload = parse_excel_to_l1(path, flight_id=flight_id, event_id=event_id)
    elif parser_key == "px4_ulg":
        from .px4_ulg import parse_px4_ulg_to_l1

        payload = parse_px4_ulg_to_l1(path, flight_id=flight_id, event_id=event_id)
    elif parser_key == "ardupilot_bin":
        from .ardupilot import parse_ardupilot_bin_to_l1

        payload = parse_ardupilot_bin_to_l1(path, flight_id=flight_id, event_id=event_id)
    elif parser_key == "ardupilot_tlog":
        from .ardupilot import parse_ardupilot_tlog_to_l1

        payload = parse_ardupilot_tlog_to_l1(path, flight_id=flight_id, event_id=event_id)
    elif parser_key == "hermes900":
        payload = _parse_hermes(path, flight_id, event_id)
    elif parser_key == "orbiter4":
        payload = _parse_orbiter(path, flight_id, event_id)
    elif parser_key == "aunav":
        payload = _parse_aunav(path, flight_id, event_id)
    elif parser_key == "vendor_hex":
        payload = _parse_hex(path, flight_id, event_id)
    else:
        raise UnsupportedLogFormat(f"No parser registered for {original_name or path.name}")

    return payload, parser_key
