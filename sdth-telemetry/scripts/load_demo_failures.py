#!/usr/bin/env python3
"""Load the separately audited exercise failure fixtures into a running local demo.

These are simulated sorties generated from kinematic scenario cards, not live
operational flights -- the fixtures' own manifest records that provenance, and
the console labels them "Exercise" in the mission library.
"""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import httpx


def main():
    root = Path(__file__).resolve().parents[2]
    evidence = root / "output/evidence/corpus-validation-v2"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    audit = json.loads((evidence / "failure-fixtures-audit/corpus-validation.json").read_text())
    inputs = [item for item in audit["files_detail"] if item.get("parser") == "dji_csv"]
    if not inputs or not all(item.get("detection_expectation_met") for item in inputs):
        raise SystemExit("Run and inspect the failure-fixture audit before loading the demo.")
    key = os.environ.get("INGEST_API_KEY", "dev-key-12345")
    results = []
    with httpx.Client(base_url=args.base_url, headers={"Authorization": f"Bearer {key}"}, timeout=30) as client:
        for item in inputs:
            path = evidence / "failure-fixtures" / item["path"]
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise SystemExit(f"Fixture changed since audit: {path}")
            started = time.monotonic()
            # Upload under the fixture's real on-disk name. The integrity check
            # above hashes file *content*, so the upload name is free to match
            # the file itself -- which also keeps the name shown in patterns,
            # bulletins and the PDF traceable straight back to the fixture.
            response = client.post("/v1/logs/upload", files={"file": (path.name, data, "text/csv")})
            response.raise_for_status()
            upload = response.json()
            deadline = time.monotonic() + 60
            while True:
                response = client.get(f"/v1/uploads/{upload['upload_id']}")
                response.raise_for_status()
                status = response.json()
                if status["status"] in {"ready", "failed"}:
                    break
                if time.monotonic() > deadline:
                    raise SystemExit(f"Processing still pending: {upload['upload_id']}")
                time.sleep(0.3)
            if status["status"] != "ready":
                raise SystemExit(f"Processing failed: {status.get('error')}")
            flight = status["flight_id"]
            response = client.get(f"/v1/flights/{flight}/incidents")
            response.raise_for_status()
            actual = sorted({incident["incident_type"] for incident in response.json()["items"]})
            expected = item["expected_incident_types"]
            passed = set(expected).issubset(actual) if expected else not actual
            results.append({"path": item["path"], "sha256": item["sha256"], "upload_id": upload["upload_id"], "duplicate_reused": bool(upload.get("duplicate")), "flight_id": flight, "expected": expected, "actual": actual, "passed": passed, "elapsed_ms": round((time.monotonic() - started) * 1000)})
            print(f"{'PASS' if passed else 'FAIL'} {path.name}: {', '.join(actual) or 'no incidents'}")
    (evidence / "live-demo-import.json").write_text(json.dumps({"base_url": args.base_url, "simulation_only": True, "results": results}, indent=2) + "\n")
    if not all(item["passed"] for item in results):
        raise SystemExit("At least one live result differed from its audited expectations.")


if __name__ == "__main__":
    main()
