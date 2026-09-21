"""Parse Excel (.xlsx/.xls) telemetry tables into L1 ingest JSON."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dji_csv import is_dji_csv, parse_dji_rows_to_l1
from .generic_rows import (
    GENERIC_ALT_KEYS,
    GENERIC_LAT_KEYS,
    GENERIC_LON_KEYS,
    _parse_generic_rows_to_l1,
)

__all__ = [
    "GENERIC_ALT_KEYS",
    "GENERIC_LAT_KEYS",
    "GENERIC_LON_KEYS",
    "parse_excel_to_l1",
    "read_excel_table",
]


def _require_openpyxl():
    try:
        import openpyxl  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "openpyxl is required for Excel parsing. "
            "Install with: pip install openpyxl  (or use sdth-telemetry/.venv)"
        ) from exc


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return str(value).strip()


def read_excel_table(
    path: Path | str,
    *,
    sheet: str | int | None = None,
) -> tuple[list[str], list[dict[str, str]]]:
    """Return (fieldnames, rows) from the first non-empty sheet (or a named sheet)."""
    _require_openpyxl()
    from openpyxl import load_workbook

    path = Path(path)
    if path.suffix.lower() not in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        # .xls (legacy) needs xlrd; keep a clear error.
        if path.suffix.lower() == ".xls":
            raise ValueError(
                "Legacy .xls is not supported here. Re-save as .xlsx, or convert to CSV first."
            )
        raise ValueError(f"Expected an Excel workbook, got {path.suffix}")

    wb = load_workbook(filename=str(path), read_only=True, data_only=True)
    try:
        if sheet is None:
            ws = wb[wb.sheetnames[0]]
        elif isinstance(sheet, int):
            ws = wb[wb.sheetnames[sheet]]
        else:
            ws = wb[sheet]

        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        if not header_row:
            raise ValueError(f"Excel sheet is empty: {path}")

        fieldnames = [_cell_str(h) for h in header_row]
        # Drop trailing empty headers
        while fieldnames and not fieldnames[-1]:
            fieldnames.pop()
        if not any(fieldnames):
            raise ValueError(f"Excel sheet has no header row: {path}")

        rows: list[dict[str, str]] = []
        for values in rows_iter:
            if values is None:
                continue
            if all(v is None or _cell_str(v) == "" for v in values[: len(fieldnames)]):
                continue
            row = {
                fieldnames[i]: _cell_str(values[i] if i < len(values) else None)
                for i in range(len(fieldnames))
                if fieldnames[i]
            }
            rows.append(row)
        return fieldnames, rows
    finally:
        wb.close()


def parse_excel_to_l1(
    path: Path | str,
    *,
    sheet: str | int | None = None,
    flight_id: str | None = None,
    source: str | None = None,
    event_id: str | None = None,
    skip_zero_gps: bool = True,
    max_records: int | None = None,
) -> dict[str, Any]:
    """
    Convert an Excel workbook sheet into L1 JSON.

    Routing:
    1. DJI FlightRecord headers → DJI mapper
    2. Else generic lat/lon(/alt) columns → generic mapper
    """
    path = Path(path)
    fieldnames, rows = read_excel_table(path, sheet=sheet)

    if is_dji_csv(fieldnames):
        return parse_dji_rows_to_l1(
            rows,
            flight_id=flight_id,
            source=source or "dji-excel",
            event_id=event_id,
            skip_zero_gps=skip_zero_gps,
            max_records=max_records,
            stem=path.stem,
        )

    return _parse_generic_rows_to_l1(
        rows,
        flight_id=flight_id,
        source=source or "excel-generic",
        event_id=event_id,
        skip_zero_gps=skip_zero_gps,
        max_records=max_records,
        stem=path.stem,
    )
