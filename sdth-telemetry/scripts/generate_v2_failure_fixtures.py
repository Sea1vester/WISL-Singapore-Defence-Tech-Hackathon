#!/usr/bin/env python3
"""Generate separately labelled, independent synthetic V2 validation fixtures.

This script never reads or writes the submitted hazards corpus. It uses scenario
cards as ground truth and emits four signal-preserving formats for each selected
failure condition. The ignored local `sdth-synth` source must first receive the
recorded generator-skin patch in output/evidence/corpus-validation-v2.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


DEFAULTS = (
    ("battery_critical", 21),
    ("gps_jamming", 22),
    ("gps_denied_frozen", 23),
    ("motor_fail_recover", 24),
    ("logger_dropout", 25),
    ("lost_airborne", 26),
)
SUPPLEMENTAL_CARDS = (
    ("battery_critical_logger_dropout", 27),
    ("gps_weak_midair_end", 28),
)
FORMATS = ("dji_csv", "dji_excel", "hermes900", "orbiter4")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synth-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--normal-scenario", type=Path, required=True)
    args = parser.parse_args()
    synth_root = args.synth_root.resolve()
    sys.path.insert(0, str(synth_root / "src"))

    from sdth_synth.batch import variant_scenario
    from sdth_synth.cli import emit
    from sdth_synth.core import integrate
    from sdth_synth.gates import gate_generated_dir
    from sdth_synth.scenario import load_scenario

    fixtures: list[dict[str, object]] = []
    cards = synth_root / "scenarios" / "hazards"
    for base_name, index in DEFAULTS:
        base = load_scenario(cards / f"{base_name}.yaml")
        scenario = variant_scenario(base, index)
        flight = integrate(scenario)
        destination = args.out / scenario.name
        manifest = emit(flight, destination, FORMATS, allow_sitl_skip=False, mission_id=scenario.name)
        gate = gate_generated_dir(destination, flight)
        if not gate.ok:
            raise RuntimeError(f"physical-sanity gate failed for {scenario.name}: {gate.issues}")
        fixtures.append(
            {
                "kind": "independent_synthetic_failure_fixture",
                "base_scenario_card": str(cards / f"{base_name}.yaml"),
                "variant_index": index,
                "scenario": asdict(scenario),
                "formats": list(FORMATS),
                "manifest": manifest,
                "physical_sanity_gate": {"passed": gate.ok, "issues": []},
            }
        )

    # These cards deliberately combine independently observable conditions.  The
    # manifest retains both conditions; it makes no claim that one caused the
    # other.
    cards_v2 = ROOT / "output" / "evidence" / "corpus-validation-v2"
    for base_name, index in SUPPLEMENTAL_CARDS:
        base = load_scenario(cards_v2 / f"{base_name}.yaml")
        scenario = variant_scenario(base, index)
        flight = integrate(scenario)
        destination = args.out / scenario.name
        manifest = emit(flight, destination, FORMATS, allow_sitl_skip=False, mission_id=scenario.name)
        gate = gate_generated_dir(destination, flight)
        if not gate.ok:
            raise RuntimeError(f"physical-sanity gate failed for {scenario.name}: {gate.issues}")
        fixtures.append(
            {
                "kind": "independent_synthetic_multi_condition_fixture",
                "base_scenario_card": str(cards_v2 / f"{base_name}.yaml"),
                "variant_index": index,
                "injected_observable_conditions": (
                    ["battery_percent_at_or_below_10", "timestamp_gap_at_least_15_seconds"]
                    if base_name == "battery_critical_logger_dropout"
                    else ["exact_gps_weak_warning", "recording_ends_while_airborne"]
                ),
                "scenario": asdict(scenario),
                "formats": list(FORMATS),
                "manifest": manifest,
                "physical_sanity_gate": {"passed": gate.ok, "issues": []},
            }
        )

    normal = load_scenario(args.normal_scenario.resolve())
    normal_flight = integrate(normal)
    normal_destination = args.out / normal.name
    normal_manifest = emit(normal_flight, normal_destination, FORMATS, allow_sitl_skip=False, mission_id=normal.name)
    normal_gate = gate_generated_dir(normal_destination, normal_flight)
    if not normal_gate.ok:
        raise RuntimeError(f"physical-sanity gate failed for {normal.name}: {normal_gate.issues}")
    fixtures.append(
        {
            "kind": "independent_synthetic_normal_control",
            "base_scenario_card": str(args.normal_scenario.resolve()),
            "scenario": asdict(normal),
            "formats": list(FORMATS),
            "manifest": normal_manifest,
            "physical_sanity_gate": {"passed": normal_gate.ok, "issues": []},
        }
    )
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "fixture-manifest.json").write_text(json.dumps({"fixtures": fixtures}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fixtures": len(fixtures), "formats_per_fixture": len(FORMATS)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
