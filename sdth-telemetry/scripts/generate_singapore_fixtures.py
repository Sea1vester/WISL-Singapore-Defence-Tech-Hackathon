#!/usr/bin/env python3
"""Generate the six Singapore demo mission fixtures (DJI CSV).

Scenario cards live in sdth-synth/scenarios/singapore/ (tracked copies in
sdth-demo/fixtures/singapore/cards/). Singapore homes sit inside the 50 km
BANNED_HOMES_ALWAYS radius, so the geography gate is bypassed deliberately
(integrate(validate_home=False)) and recorded as such in the manifest; the
physical-sanity gate still runs and must pass. Emits dji_csv only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "sdth-telemetry" / "platform-api"
PARSERS_ROOT = ROOT / "sdth-telemetry"
FORMATS = ("dji_csv",)
GEOGRAPHY_NOTE = "bypassed: Singapore demo region, inside BANNED_HOMES_ALWAYS radius"

MISSIONS = (
    ("sg_lck_survey_normal", "lim-chu-kang"),
    ("sg_lck_survey_gps_weak", "lim-chu-kang"),
    ("sg_seletar_perimeter_gps_weak", "seletar"),
    ("sg_hillview_inspection_battery_critical", "hillview"),
    ("sg_hillview_inspection_dropout", "hillview"),
    ("sg_seletar_ends_airborne", "seletar"),
)


def _observed_detectors(path: Path) -> dict[str, int]:
    for entry in (str(API_ROOT), str(PARSERS_ROOT)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    from app.canonical_series import series_from_l1_payload
    from app.detectors import detect_incidents
    from parsers.registry import parse_raw_log

    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    payload, _parser = parse_raw_log(path, sha256=sha256, original_name=path.name)
    incidents = detect_incidents(series_from_l1_payload(payload))
    return dict(sorted(Counter(item.incident_type for item in incidents).items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synth-root", type=Path, default=ROOT / "sdth-synth")
    parser.add_argument("--out", type=Path, default=ROOT / "sdth-demo" / "fixtures" / "singapore")
    args = parser.parse_args()

    synth_root = args.synth_root.resolve()
    sys.path.insert(0, str(synth_root / "src"))
    from sdth_synth.cli import emit
    from sdth_synth.core import integrate
    from sdth_synth.gates import gate_generated_dir
    from sdth_synth.scenario import load_scenario

    args.out.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    for name, region in MISSIONS:
        card = synth_root / "scenarios" / "singapore" / f"{name}.yaml"
        scenario = load_scenario(card)
        flight = integrate(scenario, validate_home=False)
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / scenario.name
            manifest = emit(flight, destination, FORMATS, allow_sitl_skip=False, mission_id=scenario.name)
            gate = gate_generated_dir(destination, flight)
            if not gate.ok:
                raise RuntimeError(f"physical-sanity gate failed for {scenario.name}: {gate.issues}")
            emitted = Path(manifest["dji_csv"])
            out_path = args.out / f"dji_csv_{name}.csv"
            out_path.write_bytes(emitted.read_bytes())
        entries.append(
            {
                "file": out_path.name,
                "sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
                "source": f"Singapore synthetic mission; scenario card scenarios/singapore/{name}.yaml",
                "provenance": "synthetic kinematic simulator export; not an operational drone flight",
                "parser": "dji_csv",
                "region": region,
                "scenario_card": f"sdth-demo/fixtures/singapore/cards/{name}.yaml",
                "geography_gate": GEOGRAPHY_NOTE,
                "physical_sanity_gate": {"passed": gate.ok, "issues": []},
                "observed_detectors": _observed_detectors(out_path),
            }
        )
        print(f"{out_path.name}: {entries[-1]['observed_detectors']}")

    (args.out / "manifest.json").write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
