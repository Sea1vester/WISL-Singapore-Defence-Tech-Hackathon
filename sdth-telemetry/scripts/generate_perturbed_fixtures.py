#!/usr/bin/env python3
"""Generate perturbed synthetic DJI CSV fixtures for the judges' unhappy-path test.

Each base scenario card is shifted north by --north-m metres (dataclasses.replace
+ sdth_synth.geo.offset_latlon, the same mechanism batch.variant_scenario uses),
integrated and emitted as a DJI FlightRecord CSV, then deterministically
subsampled: --drop-frac of the data rows are removed at random (first and last
rows are always kept). For the gps_jamming variant a third file is emitted with
an additional contiguous telemetry gap of --gap-s seconds cut from mid-cruise.

The ignored local `sdth-synth` source is imported via --synth-root, exactly like
generate_v2_failure_fixtures.py. With --input, synthesis is skipped entirely and
the shift + drop post-processing (plus an optional mid-cruise gap via --cut-gap)
is applied to an arbitrary existing DJI CSV.

Not auto-imported: sdth-demo/demo.js hardcodes its fixture list, so files under
sdth-demo/fixtures/perturbed/ are never offered in the console.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
import tempfile
from collections import Counter
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "sdth-telemetry" / "platform-api"
PARSERS_ROOT = ROOT / "sdth-telemetry"
NORMAL_CONTROL_CARD = (
    ROOT / "output" / "evidence" / "corpus-validation-v2" / "normal_control_v2.yaml"
)
FORMATS = ("dji_csv",)


def _load_detectors():
    for entry in (str(API_ROOT), str(PARSERS_ROOT)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    from app.canonical_series import series_from_l1_payload
    from app.detectors import detect_incidents
    from parsers.registry import parse_raw_log

    return parse_raw_log, series_from_l1_payload, detect_incidents


def _observed_detectors(path: Path) -> dict[str, int]:
    """Run the platform rule detectors on one emitted file, as `parsers detect` does."""
    parse_raw_log, series_from_l1_payload, detect_incidents = _load_detectors()
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    payload, _parser = parse_raw_log(path, sha256=sha256, original_name=path.name)
    incidents = detect_incidents(series_from_l1_payload(payload))
    return dict(sorted(Counter(item.incident_type for item in incidents).items()))


def _read_dji_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    return rows[0], rows[1:]


def _write_dji_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _drop_rows(header: list[str], rows: list[list[str]], drop_frac: float, seed: int):
    """Randomly drop drop_frac of the data rows; first and last rows always kept."""
    rng = random.Random(seed)
    kept = [rows[0]] + [r for r in rows[1:-1] if rng.random() >= drop_frac] + [rows[-1]]
    return header, kept


def _shift_rows(header: list[str], rows: list[list[str]], north_m: float):
    """Shift every latitude column north by north_m (pure northward shift)."""
    delta_deg = north_m / 111_320.0
    lat_cols = [i for i, name in enumerate(header) if "latitude" in name.lower()]
    shifted = []
    for row in rows:
        row = list(row)
        for i in lat_cols:
            if i < len(row) and row[i] not in ("", None):
                row[i] = f"{float(row[i]) + delta_deg:.8f}"
        shifted.append(row)
    return header, shifted


def _cut_gap(header: list[str], rows: list[list[str]], gap_s: float):
    """Remove a contiguous block covering gap_s seconds around 50% of the flight."""
    ts_col = header.index("timestamps")
    t0 = float(rows[0][ts_col])
    tn = float(rows[-1][ts_col])
    centre = t0 + 0.5 * (tn - t0)
    start, end = centre - gap_s / 2.0, centre + gap_s / 2.0
    kept = [r for r in rows if not (start <= float(r[ts_col]) <= end)]
    return header, kept


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_relative(path: Path) -> str:
    path = path.resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _record(out_path: Path, rows_before, rows_after, source_card, params, gate):
    return {
        "file": out_path.name,
        "sha256": _sha256(out_path),
        "source_card": _repo_relative(Path(source_card)),
        "perturbation": {
            **params,
            "rows_before": rows_before,
            "rows_after": rows_after,
        },
        "gate": gate,
        "observed_detectors": _observed_detectors(out_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synth-root", type=Path, default=ROOT / "sdth-synth")
    parser.add_argument("--out", type=Path, default=ROOT / "sdth-demo" / "fixtures" / "perturbed")
    parser.add_argument("--input", type=Path, default=None,
                        help="Existing DJI CSV: skip synthesis, apply shift + drop "
                             "post-processing; writes <stem>_perturbed.csv plus a "
                             "<stem>_perturbed.manifest.json sidecar")
    parser.add_argument("--cut-gap", action="store_true",
                        help="With --input: also cut a --gap-s block from mid-cruise")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--north-m", type=float, default=2000.0)
    parser.add_argument("--drop-frac", type=float, default=0.10)
    parser.add_argument("--gap-s", type=float, default=20.0)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []

    if args.input is not None:
        source = args.input.resolve()
        header, rows = _read_dji_csv(source)
        rows_before = len(rows)
        _, rows = _shift_rows(header, rows, args.north_m)
        _, rows = _drop_rows(header, rows, args.drop_frac, args.seed)
        if args.cut_gap:
            _, rows = _cut_gap(header, rows, args.gap_s)
        out_path = args.out / f"{source.stem}_perturbed.csv"
        _write_dji_csv(out_path, header, rows)
        record = _record(out_path, rows_before, len(rows), str(source),
                         {"north_m": args.north_m, "drop_frac": args.drop_frac,
                          "gap_s": args.gap_s if args.cut_gap else None,
                          "seed": args.seed, "input": _repo_relative(source)}, None)
        sidecar = out_path.with_suffix(".manifest.json")
        sidecar.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({record["file"]: record["observed_detectors"]}, indent=2))
        return 0

    params = {"north_m": args.north_m, "drop_frac": args.drop_frac, "seed": args.seed}
    synth_root = args.synth_root.resolve()
    sys.path.insert(0, str(synth_root / "src"))
    from sdth_synth.cli import emit
    from sdth_synth.core import integrate
    from sdth_synth.gates import gate_generated_dir
    from sdth_synth.geo import offset_latlon
    from sdth_synth.scenario import ScenarioError, load_scenario, validate_geography

    bases = [
        ("normal_control", NORMAL_CONTROL_CARD, "dji_csv_perturbed_normal_control_north2km_drop10.csv"),
        ("gps_weak", synth_root / "scenarios" / "hazards" / "gps_jamming.yaml",
         "dji_csv_perturbed_gps_weak_north2km_drop10.csv"),
    ]
    for index, (label, card, out_name) in enumerate(bases):
        base = load_scenario(card)
        lat, lon = offset_latlon(base.home_lat, base.home_lon, args.north_m, 0.0)
        scenario = replace(
            base,
            name=f"{base.name}_perturbed",
            seed=args.seed + index,
            home_lat=lat,
            home_lon=lon,
        )
        geography_gate = "passed"
        try:
            validate_geography(scenario)
        except ScenarioError as exc:
            geography_gate = f"skipped: {exc}"

        flight = integrate(scenario, validate_home=False)
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / scenario.name
            emit(flight, destination, FORMATS, allow_sitl_skip=False, mission_id=scenario.name)
            gate = gate_generated_dir(destination, flight)
            gate_result = {"passed": gate.ok, "issues": list(gate.issues),
                           "geography_gate": geography_gate}
            csv_path = destination / json.loads(
                (destination / "manifest.json").read_text(encoding="utf-8")
            )["dji_csv"].split(str(destination) + "/", 1)[-1]
            header, rows = _read_dji_csv(csv_path)

            _, kept = _drop_rows(header, rows, args.drop_frac, args.seed + index)
            out_path = args.out / out_name
            _write_dji_csv(out_path, header, kept)
            records.append(_record(out_path, len(rows), len(kept),
                                   str(card), {**params, "gap_s": None}, gate_result))

            if label == "gps_weak":
                gap_header, gap_rows = _cut_gap(header, kept, args.gap_s)
                gap_path = args.out / "dji_csv_perturbed_gps_weak_north2km_drop10_gap20s.csv"
                _write_dji_csv(gap_path, gap_header, gap_rows)
                records.append(_record(gap_path, len(kept), len(gap_rows),
                                       str(card), {**params, "gap_s": args.gap_s}, gate_result))

    (args.out / "manifest.json").write_text(
        json.dumps({"generated_for": "judges_unhappy_path_test", "files": records}, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.out / "README.md").write_text(
        "# Perturbed fixtures\n\n"
        "Synthetic DJI FlightRecord logs perturbed for the judges' unhappy-path test: "
        "home shifted north and ~10% of observations removed at random "
        "(`*_gap20s.csv` also has a 20 s telemetry block cut mid-cruise). "
        "They are NOT auto-imported into the Mission library — the console fixture "
        "list is hardcoded in `sdth-demo/demo.js`. Upload them via the console's "
        "\"Import log\" dropzone (Logs view) or `POST /v1/logs/upload` — both hit "
        "the same endpoint.\n\n"
        "To perturb a judge-supplied DJI CSV (shift + drop, optionally a gap):\n\n"
        "```\n"
        ".venv/bin/python sdth-telemetry/scripts/generate_perturbed_fixtures.py "
        "--input their_log.csv --out fixtures/perturbed [--cut-gap]\n"
        "```\n\n"
        "This writes `<stem>_perturbed.csv` plus a `<stem>_perturbed.manifest.json` "
        "sidecar; it never touches this directory's `manifest.json`.\n\n"
        "Regenerate:\n\n"
        "```\n"
        ".venv/bin/python sdth-telemetry/scripts/generate_perturbed_fixtures.py\n"
        "```\n\n"
        "See `manifest.json` for per-file perturbation parameters, gate results, and "
        "the incident types the platform detectors observed.\n",
        encoding="utf-8",
    )
    print(json.dumps({r["file"]: r["observed_detectors"] for r in records}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
