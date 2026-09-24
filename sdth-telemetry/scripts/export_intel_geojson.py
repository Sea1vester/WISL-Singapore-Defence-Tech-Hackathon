#!/usr/bin/env python3
"""Write the collab GeoJSON overlay from stored rule incidents.

Reads the demo SQLite database and writes one FeatureCollection. Pins and
GPS-degraded zones are remapped onto Singapore training areas so the
tactical map can drop them locally. This is not a log dump.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "sdth-telemetry" / "platform-api"
DEFAULT_DB = ROOT / "data" / "demo-console.db"
DEFAULT_OUT = ROOT / "output" / "collab" / "incidents.geojson"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.intel_geojson import export_intel_geojson  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if not args.database.exists():
        raise SystemExit(f"Database not found: {args.database}")

    conn = sqlite3.connect(args.database)
    conn.row_factory = sqlite3.Row
    try:
        collection = export_intel_geojson(conn)
    finally:
        conn.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(collection, indent=2) + "\n", encoding="utf-8")
    points = sum(1 for f in collection["features"] if f["properties"]["kind"] == "pin")
    zones = sum(1 for f in collection["features"] if f["properties"]["kind"] == "zone")
    print(f"Wrote {args.out} ({points} incident points, {zones} gps-degraded zones)")


if __name__ == "__main__":
    main()
