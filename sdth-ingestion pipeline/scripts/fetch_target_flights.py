"""Fetch canonical flight records for target drone platforms from the WISL flight API.

Implements steps 3-6 of the "For Inessa" onboarding doc: list flights, filter down to the
platforms this run cares about, preview canonical record counts, and bulk-export each
matching flight as JSONL. Steps 1-2 (join the tailnet, obtain the API key) are manual
prerequisites -- this script assumes the server is already reachable and a key is available.

Usage:
    export WISL_API_KEY=<key>
    python scripts/fetch_target_flights.py --base-url http://<MyIPAddress>:8000

Output:
    ./flight_exports/<platform-slug>/<flight_id>.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Substring patterns (lowercase) used to match a flight's "source" field to a target
# platform. Add aliases here if the API's naming convention doesn't match a real flight.
# Both segments are targets: cheap/COTS brands for fleet-wide systematic-failure
# detection, and the tactical platforms for the small, expensive fleets where a
# single-airframe loss is worth reconstructing on its own.
TARGET_PLATFORMS: dict[str, list[str]] = {
    "DJI": ["dji", "mavic", "phantom", "mini 4", "air 3", "matrice"],
    "PX4 / Auterion (FPV, DIY, budget autopilot builds)": ["px4", "auterion"],
    "ArduPilot (FPV, DIY, budget autopilot builds)": ["ardupilot", "arducopter", "arduplane"],
    "Elbit Systems Hermes 900": ["hermes 900", "hermes900", "elbit hermes", "elbit systems hermes"],
    "Aeronautics Orbiter 4": ["orbiter 4", "orbiter4", "aeronautics orbiter"],
    "ST Engineering Taurus UGV": ["taurus ugv", "taurus", "st engineering taurus"],
}


def match_platform(source: str) -> str | None:
    source_lower = source.lower()
    for platform, patterns in TARGET_PLATFORMS.items():
        if any(p in source_lower for p in patterns):
            return platform
    return None


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def api_get(base_url: str, path: str, api_key: str, params: dict | None = None) -> dict:
    url = base_url.rstrip("/") + path
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        if query:
            url = f"{url}?{query}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_download(base_url: str, path: str, api_key: str, dest: Path) -> None:
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as f:
        while chunk := resp.read(1 << 16):
            f.write(chunk)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=os.environ.get("WISL_BASE_URL"), help="e.g. http://<MyIPAddress>:8000")
    parser.add_argument("--api-key-env", default="WISL_API_KEY", help="Env var holding the bearer token (default: WISL_API_KEY)")
    parser.add_argument("--out-dir", type=Path, default=Path("flight_exports"))
    parser.add_argument("--from", dest="time_from", default=None, help="ISO8601 start time filter for the records preview")
    parser.add_argument("--to", dest="time_to", default=None, help="ISO8601 end time filter for the records preview")
    parser.add_argument("--dry-run", action="store_true", help="List matching flights without downloading records/exports")
    args = parser.parse_args()

    if not args.base_url:
        parser.error("--base-url is required (or set WISL_BASE_URL)")

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        parser.error(f"API key not found in ${args.api_key_env}. Set it before running (do not pass it as a CLI flag).")

    try:
        flights = api_get(args.base_url, "/v1/flights", api_key)
    except urllib.error.HTTPError as e:
        sys.exit(f"Failed to list flights: HTTP {e.code} {e.reason}. Check the API key.")
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach {args.base_url}: {e.reason}. Check tailnet connectivity.")

    flight_list = flights.get("flights", flights) if isinstance(flights, dict) else flights
    matched = [(f, match_platform(f.get("source", ""))) for f in flight_list]
    matched = [(f, p) for f, p in matched if p is not None]

    if not matched:
        print(
            "No flights matched the target platforms (DJI, PX4/Auterion, ArduPilot, plus the "
            "legacy Hermes 900 / Orbiter 4 / Taurus UGV aliases). If you expect data, check "
            "ingest status with Isaac or confirm the translation worker is running (ask Sylvester)."
        )
        return

    print(f"Matched {len(matched)} flight(s):")
    for f, platform in matched:
        print(f"  {f.get('id')}  [{platform}]  started_at={f.get('started_at')}")

    if args.dry_run:
        return

    for f, platform in matched:
        flight_id = f["id"]
        slug = slugify(platform)

        try:
            records = api_get(
                args.base_url,
                f"/v1/flights/{flight_id}/records",
                api_key,
                params={"from": args.time_from, "to": args.time_to},
            )
            record_count = len(records) if isinstance(records, list) else len(records.get("records", []))
            print(f"  {flight_id}: {record_count} canonical record(s)")
        except urllib.error.HTTPError as e:
            print(f"  {flight_id}: failed to fetch records preview (HTTP {e.code})")

        dest = args.out_dir / slug / f"{flight_id}.jsonl"
        try:
            api_download(args.base_url, f"/v1/export/flights/{flight_id}.jsonl", api_key, dest)
            print(f"  {flight_id}: exported -> {dest}")
        except urllib.error.HTTPError as e:
            print(f"  {flight_id}: export failed (HTTP {e.code})")


if __name__ == "__main__":
    main()
