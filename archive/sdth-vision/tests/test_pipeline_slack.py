"""Pipeline smoke: 20 frames, detect → census within count slack (CI fixtures)."""
from __future__ import annotations

from pathlib import Path

import pytest

from sdth_vision.census import census
from sdth_vision.pipeline import (
    DEFAULT_COUNT_SLACK,
    DEFAULT_PIPELINE_LIMIT,
    annotation_predictor,
    evaluate_pipeline,
    ground_truth_census,
    hud_within_slack,
    list_pipeline_frames,
    parse_visdrone_gt_detections,
)

FIXTURE_SPLIT = Path(__file__).parent / "fixtures" / "pipeline20"


def test_pipeline_fixtures_have_twenty_frames():
    frames = list_pipeline_frames(FIXTURE_SPLIT, limit=DEFAULT_PIPELINE_LIMIT)
    assert len(frames) == 20
    assert DEFAULT_PIPELINE_LIMIT == 20
    assert all(p.suffix.lower() == ".jpg" for p in frames)


def test_ground_truth_drops_ignored_and_rolls_hud():
    # frame_04: 1 pedestrian + car+van+truck+bus (ignored region present)
    image = FIXTURE_SPLIT / "images" / "frame_04.jpg"
    ann = FIXTURE_SPLIT / "annotations" / "frame_04.txt"
    gt = ground_truth_census(ann, image)
    assert gt["people"] == 1
    assert gt["cars"] == 4
    assert "ignored" not in gt["class_counts"]
    dets = parse_visdrone_gt_detections(ann, 64, 48)
    assert all(d["class"] != "ignored" for d in dets)


def test_hud_within_slack_bounds():
    expected = {"cars": 5, "people": 3}
    assert hud_within_slack({"cars": 5, "people": 3}, expected, slack=0)
    assert hud_within_slack({"cars": 7, "people": 1}, expected, slack=2)
    assert not hud_within_slack({"cars": 8, "people": 3}, expected, slack=2)
    assert not hud_within_slack({"cars": 5, "people": 0}, expected, slack=2)
    with pytest.raises(ValueError, match="slack"):
        hud_within_slack(expected, expected, slack=-1)


def test_pipeline_twenty_frames_match_gt_within_slack():
    """CI gate: annotation-backed predictor on 20 tiny fixtures, slack=0 exact."""
    report = evaluate_pipeline(
        FIXTURE_SPLIT,
        predictor=annotation_predictor(FIXTURE_SPLIT),
        slack=0,
        limit=20,
    )
    assert report["total"] == 20
    assert report["passed"] == 20
    assert report["failed"] == 0
    assert report["all_ok"] is True
    assert report["slack"] == 0


def test_pipeline_default_slack_allows_small_hud_error():
    """A one-count HUD miss is accepted when slack is the product default."""
    assert DEFAULT_COUNT_SLACK == 2

    def noisy_predictor(image: Path, conf: float, imgsz: int):
        rows = annotation_predictor(FIXTURE_SPLIT)(image, conf, imgsz)
        # Inject one extra car detection so HUD cars is +1 vs GT.
        rows = list(rows)
        rows.append((3, 0.5, (1.0, 1.0, 2.0, 2.0)))  # class 3 = car
        return rows

    tight = evaluate_pipeline(FIXTURE_SPLIT, predictor=noisy_predictor, slack=0, limit=20)
    assert tight["failed"] == 20
    assert tight["all_ok"] is False

    loose = evaluate_pipeline(
        FIXTURE_SPLIT,
        predictor=noisy_predictor,
        slack=DEFAULT_COUNT_SLACK,
        limit=20,
    )
    assert loose["passed"] == 20
    assert loose["all_ok"] is True


def test_pipeline_census_schema_on_each_fixture_frame():
    pred = annotation_predictor(FIXTURE_SPLIT)
    for image in list_pipeline_frames(FIXTURE_SPLIT, limit=20):
        from sdth_vision.infer import detect_frame

        dets = detect_frame(image, predictor=pred)
        blob = census(dets)
        assert set(blob.keys()) == {"class_counts", "cars", "people"}
        assert len(blob["class_counts"]) == 10
