from __future__ import annotations

import json
from pathlib import Path

from parsers.dji_csv import parse_dji_csv_to_l1


FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "demo"


def test_demo_fixtures_match_recorded_outcomes():
    expected = json.loads((FIXTURE_DIR / "expected_outcomes.json").read_text())

    for mission in expected["missions"]:
        payload = parse_dji_csv_to_l1(
            FIXTURE_DIR / mission["file"],
            flight_id=Path(mission["file"]).stem,
            event_id=f"event-{Path(mission['file']).stem}",
        )

        assert payload["source"] == mission["source"]
        assert len(payload["records"]) == mission["path_samples"]
        warnings = [record.get("warning", "") for record in payload["records"]]
        assert mission["evidence_contains"] in warnings
        assert payload["records"][0].get("home_lat")
        assert payload["records"][0].get("home_lon")


def test_demo_fixtures_have_distinct_paths_for_pattern_demo():
    alpha = parse_dji_csv_to_l1(FIXTURE_DIR / "controller_mission_alpha.csv")
    bravo = parse_dji_csv_to_l1(FIXTURE_DIR / "controller_mission_bravo.csv")

    alpha_start = (alpha["records"][0]["lat"], alpha["records"][0]["lon"])
    bravo_start = (bravo["records"][0]["lat"], bravo["records"][0]["lon"])
    assert alpha_start != bravo_start
