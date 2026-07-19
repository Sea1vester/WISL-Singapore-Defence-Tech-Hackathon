"""CLI: python -m parsers dji path/to/file.csv -o out.json"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ardupilot import parse_ardupilot_bin_to_l1, parse_ardupilot_tlog_to_l1
from .detect import detect_format
from .dji_csv import parse_dji_csv_to_l1
from .excel import parse_excel_to_l1
from .path_export import path_from_l1_file
from .px4_ulg import DEFAULT_ORIGIN_LAT, DEFAULT_ORIGIN_LON, parse_px4_ulg_to_l1


def _write_payload(payload: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {len(payload['records'])} records → {output} "
        f"(flight_id={payload['flight_id']})",
        file=sys.stderr,
    )


def _write_path(path_doc: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(path_doc, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {path_doc['count']} path samples → {output} "
        f"(flight_id={path_doc['flight_id']})",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize raw drone telemetry to L1 JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    dji = sub.add_parser("dji", help="Parse DJI FlightRecord CSV → L1 JSON")
    dji.add_argument("csv_path", type=Path)
    dji.add_argument("-o", "--output", type=Path, required=True)
    dji.add_argument("--flight-id", default=None)
    dji.add_argument("--source", default="dji-csv")
    dji.add_argument("--keep-zero-gps", action="store_true")
    dji.add_argument("--max-records", type=int, default=None)

    ulg = sub.add_parser("ulg", help="Parse PX4/Auterion ULog → L1 JSON")
    ulg.add_argument("ulg_path", type=Path)
    ulg.add_argument("-o", "--output", type=Path, required=True)
    ulg.add_argument("--flight-id", default=None)
    ulg.add_argument("--source", default="px4-ulg")
    ulg.add_argument("--origin-lat", type=float, default=DEFAULT_ORIGIN_LAT)
    ulg.add_argument("--origin-lon", type=float, default=DEFAULT_ORIGIN_LON)
    ulg.add_argument("--stride", type=int, default=1)
    ulg.add_argument("--max-records", type=int, default=None)

    bin_p = sub.add_parser("bin", help="Parse ArduPilot DataFlash .bin → L1 JSON")
    bin_p.add_argument("bin_path", type=Path)
    bin_p.add_argument("-o", "--output", type=Path, required=True)
    bin_p.add_argument("--flight-id", default=None)
    bin_p.add_argument("--source", default="ardupilot-bin")
    bin_p.add_argument("--stride", type=int, default=1)
    bin_p.add_argument("--max-records", type=int, default=None)

    tlog = sub.add_parser("tlog", help="Parse ArduPilot/MAVLink .tlog → L1 JSON")
    tlog.add_argument("tlog_path", type=Path)
    tlog.add_argument("-o", "--output", type=Path, required=True)
    tlog.add_argument("--flight-id", default=None)
    tlog.add_argument("--source", default="ardupilot-tlog")
    tlog.add_argument("--stride", type=int, default=1)
    tlog.add_argument("--max-records", type=int, default=None)

    xlsx = sub.add_parser("excel", help="Parse Excel .xlsx → L1 JSON (DJI or generic lat/lon)")
    xlsx.add_argument("excel_path", type=Path)
    xlsx.add_argument("-o", "--output", type=Path, required=True)
    xlsx.add_argument("--sheet", default=None, help="Sheet name (default: first sheet)")
    xlsx.add_argument("--flight-id", default=None)
    xlsx.add_argument("--source", default=None)
    xlsx.add_argument("--keep-zero-gps", action="store_true")
    xlsx.add_argument("--max-records", type=int, default=None)

    detect = sub.add_parser("detect", help="Detect telemetry format")
    detect.add_argument("path", type=Path)

    path_cmd = sub.add_parser("path", help="Convert L1 JSON → stable path JSON for 3D viz")
    path_cmd.add_argument("l1_path", type=Path)
    path_cmd.add_argument("-o", "--output", type=Path, required=True)
    path_cmd.add_argument("--stride", type=int, default=1)
    path_cmd.add_argument("--max-samples", type=int, default=None)

    args = parser.parse_args(argv)

    if args.command == "detect":
        print(detect_format(args.path))
        return 0

    if args.command == "path":
        path_doc = path_from_l1_file(
            args.l1_path,
            stride=max(1, args.stride),
            max_samples=args.max_samples,
        )
        _write_path(path_doc, args.output)
        return 0

    if args.command == "dji":
        payload = parse_dji_csv_to_l1(
            args.csv_path,
            flight_id=args.flight_id,
            source=args.source,
            skip_zero_gps=not args.keep_zero_gps,
            max_records=args.max_records,
        )
        _write_payload(payload, args.output)
        return 0

    if args.command == "ulg":
        payload = parse_px4_ulg_to_l1(
            args.ulg_path,
            flight_id=args.flight_id,
            source=args.source,
            origin_lat=args.origin_lat,
            origin_lon=args.origin_lon,
            stride=max(1, args.stride),
            max_records=args.max_records,
        )
        _write_payload(payload, args.output)
        return 0

    if args.command == "bin":
        payload = parse_ardupilot_bin_to_l1(
            args.bin_path,
            flight_id=args.flight_id,
            source=args.source,
            stride=max(1, args.stride),
            max_records=args.max_records,
        )
        _write_payload(payload, args.output)
        return 0

    if args.command == "tlog":
        payload = parse_ardupilot_tlog_to_l1(
            args.tlog_path,
            flight_id=args.flight_id,
            source=args.source,
            stride=max(1, args.stride),
            max_records=args.max_records,
        )
        _write_payload(payload, args.output)
        return 0

    if args.command == "excel":
        payload = parse_excel_to_l1(
            args.excel_path,
            sheet=args.sheet,
            flight_id=args.flight_id,
            source=args.source,
            skip_zero_gps=not args.keep_zero_gps,
            max_records=args.max_records,
        )
        _write_payload(payload, args.output)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
