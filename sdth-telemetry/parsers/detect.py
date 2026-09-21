"""Format detection by extension + header fingerprint."""

from __future__ import annotations

import csv
from pathlib import Path

from .dji_csv import is_dji_csv
from .generic_rows import GENERIC_LAT_KEYS, GENERIC_LON_KEYS


def sniff_csv_fieldnames(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
    if not header:
        return []
    return [h.strip() for h in header]


def detect_format(path: Path) -> str:
    """Return a parser key, e.g. ``dji_csv``, or ``unknown``."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        fields = sniff_csv_fieldnames(path)
        if is_dji_csv(fields):
            return "dji_csv"
        lowered = {field.lower() for field in fields}
        lat_keys = {key.lower() for key in GENERIC_LAT_KEYS}
        lon_keys = {key.lower() for key in GENERIC_LON_KEYS}
        if lowered & lat_keys and lowered & lon_keys:
            return "csv_generic"
        return "csv_unknown"
    if suffix == ".ulg":
        return "px4_ulg"
    if suffix == ".bin":
        return "ardupilot_bin"
    if suffix == ".tlog":
        return "ardupilot_tlog"
    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        try:
            from .excel import read_excel_table

            fields, _ = read_excel_table(path)
            if is_dji_csv(fields):
                return "dji_excel"
            return "excel"
        except Exception:
            return "excel"
    if suffix == ".xls":
        return "excel_xls_unsupported"
    return "unknown"
