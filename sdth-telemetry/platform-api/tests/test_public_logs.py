"""Tests for the public real-log tooling: fetch script staging and the
--real L1 field coverage computation in validate_submission_corpus."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FETCH_SCRIPT = REPO_ROOT / "sdth-telemetry" / "scripts" / "fetch_public_logs.py"
VALIDATOR = REPO_ROOT / "sdth-telemetry" / "scripts" / "validate_submission_corpus.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fetch_script_stages_local_entry(tmp_path):
    datasets = tmp_path / "datasets"
    datasets.mkdir()
    (datasets / "real.bin").write_bytes(b"\x00\x01\x02")
    public = tmp_path / "public"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "id": "local_real",
                    "source": "local",
                    "url": None,
                    "path": "real.bin",
                    "sha256": None,
                    "licence_or_terms": "test",
                    "source_page": "local",
                    "vehicle": "test",
                    "notes": "test",
                }
            ]
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            str(FETCH_SCRIPT),
            "--manifest",
            str(manifest),
            "--datasets-root",
            str(datasets),
            "--public-root",
            str(public),
            "--record-hashes",
            "--no-delay",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    staged = public / "local" / "real.bin"
    assert staged.exists()
    inventory = json.loads((public / "INVENTORY.json").read_text())
    assert [row["id"] for row in inventory] == ["local_real"]
    recorded = json.loads(manifest.read_text())[0]["sha256"]
    assert recorded == inventory[0]["sha256"]

    # Second run skips the already-staged file.
    again = subprocess.run(
        [
            sys.executable,
            str(FETCH_SCRIPT),
            "--manifest",
            str(manifest),
            "--datasets-root",
            str(datasets),
            "--public-root",
            str(public),
            "--no-delay",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert again.returncode == 0, again.stderr
    assert '"skipped": 1' in again.stdout


def test_l1_field_coverage_statuses():
    module = _load_module(VALIDATOR, "validate_submission_corpus")
    records = [
        {"lat": 1.35, "roll_deg": 2.0, "lon": 103.8},
        {"lat": 1.36, "lon": 103.8},
        {"lat": 1.37, "lon": 103.8},
    ]
    coverage = module.l1_field_coverage(records)
    assert coverage["position.lat"] == {"status": "observed", "fraction": 1.0}
    assert coverage["attitude.roll_deg"]["status"] == "partial"
    assert coverage["attitude.roll_deg"]["fraction"] == round(1 / 3, 4)
    assert coverage["sensors.warning"] == {"status": "absent", "fraction": 0.0}
