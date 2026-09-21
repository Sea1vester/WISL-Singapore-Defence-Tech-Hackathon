"""Tests for finetune_detector CLI: YOLOv8n COCO base, 10 VisDrone classes, eval JSON."""
from __future__ import annotations

import json
from pathlib import Path

from sdth_vision.finetune import (
    DEFAULT_BASE_WEIGHTS,
    DEFAULT_EVAL_PATH,
    DEFAULT_PRETRAINED,
    build_parser,
    finetune_detector,
    main,
    write_dataset_yaml,
)
from sdth_vision.visdrone import VISDRONE_CLASS_NAMES, visdrone_det_to_yolo

FIXTURE_SPLIT = Path(__file__).parent / "fixtures" / "visdrone_det"


def test_checked_in_eval_json_is_yolov8n_coco_ten_classes():
    assert DEFAULT_EVAL_PATH.is_file()
    record = json.loads(DEFAULT_EVAL_PATH.read_text(encoding="utf-8"))
    assert record["base_weights"] == "yolov8n.pt"
    assert record["pretrained"] == "coco"
    assert record["nc"] == 10
    assert record["names"] == list(VISDRONE_CLASS_NAMES)
    assert "metrics" in record
    # Do not check in giant weight files next to the smoke eval.
    assert not (DEFAULT_EVAL_PATH.parent / "yolov8n_visdrone.pt").exists()


def test_write_dataset_yaml_lists_ten_visdrone_classes(tmp_path: Path):
    train = tmp_path / "images"
    train.mkdir()
    yaml_path = write_dataset_yaml(tmp_path / "data.yaml", train_images=train)
    text = yaml_path.read_text(encoding="utf-8")
    assert "nc: 10" in text
    for i, name in enumerate(VISDRONE_CLASS_NAMES):
        assert f"{i}: {name}" in text


def test_finetune_detector_dry_run_writes_eval_json(tmp_path: Path):
    yolo = visdrone_det_to_yolo(FIXTURE_SPLIT, tmp_path / "yolo")
    eval_path = tmp_path / "out" / "finetune_eval.json"
    record = finetune_detector(
        yolo / "images",
        out_dir=tmp_path / "runs",
        eval_path=eval_path,
        dry_run=True,
    )
    assert record["base_weights"] == DEFAULT_BASE_WEIGHTS
    assert record["pretrained"] == DEFAULT_PRETRAINED
    assert record["dry_run"] is True
    assert record["nc"] == 10
    assert eval_path.is_file()
    loaded = json.loads(eval_path.read_text(encoding="utf-8"))
    assert loaded["names"] == list(VISDRONE_CLASS_NAMES)
    assert (tmp_path / "runs" / "visdrone.yaml").is_file()


def test_cli_dry_run_main(tmp_path: Path):
    yolo = visdrone_det_to_yolo(FIXTURE_SPLIT, tmp_path / "yolo")
    eval_path = tmp_path / "cli_eval.json"
    code = main(
        [
            "--train-images",
            str(yolo / "images"),
            "--out-dir",
            str(tmp_path / "runs"),
            "--eval-json",
            str(eval_path),
            "--dry-run",
        ]
    )
    assert code == 0
    assert eval_path.is_file()
    parser = build_parser()
    assert parser.prog == "finetune_detector"
