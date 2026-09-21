"""End-to-end frame pipeline: detect → census vs VisDrone boxed GT with count slack.

Used for the DET-val smoke gate (20 frames) and tiny in-repo fixtures for CI.
Does not unzip MOT/SOT/VID. Does not train. Does not call platform ingest.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from sdth_vision.census import census
from sdth_vision.infer import Predictor, detect_frame
from sdth_vision.visdrone import VISDRONE_CLASS_NAMES, jpeg_size

DEFAULT_PIPELINE_LIMIT = 20
DEFAULT_COUNT_SLACK = 2


def parse_visdrone_gt_detections(
    ann_path: Path | str,
    img_w: int,
    img_h: int,
) -> list[dict[str, Any]]:
    """
    Parse VisDrone DET boxes into ``detect_frame``-style detections.

    Drops ignored class 0. ``xywh`` is pixel center-x, center-y, width, height.
    """
    path = Path(ann_path)
    dets: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        parts = [p.strip() for p in text.split(",")]
        if len(parts) < 6:
            raise ValueError(f"malformed VisDrone annotation: {line!r}")
        left, top, w, h = (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
        category = int(parts[5])
        if category == 0:
            continue
        if category < 1 or category > len(VISDRONE_CLASS_NAMES):
            raise ValueError(f"unsupported VisDrone category: {category}")
        if w <= 0 or h <= 0:
            continue
        # Bounds check against image size (soft: still emit box if slightly OOB).
        _ = img_w, img_h
        name = VISDRONE_CLASS_NAMES[category - 1]
        cx = left + w / 2.0
        cy = top + h / 2.0
        dets.append({"class": name, "conf": 1.0, "xywh": (cx, cy, w, h)})
    return dets


def ground_truth_census(ann_path: Path | str, image_path: Path | str) -> dict[str, Any]:
    """Census from VisDrone boxed classes for one frame (ignored class dropped)."""
    img = Path(image_path)
    img_w, img_h = jpeg_size(img)
    return census(parse_visdrone_gt_detections(ann_path, img_w, img_h))


def hud_within_slack(
    predicted: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    slack: int,
) -> bool:
    """True when HUD ``cars`` / ``people`` differ by at most ``slack`` each."""
    if slack < 0:
        raise ValueError("slack must be non-negative")
    pred_cars = int(predicted.get("cars", 0))
    pred_people = int(predicted.get("people", 0))
    exp_cars = int(expected.get("cars", 0))
    exp_people = int(expected.get("people", 0))
    return abs(pred_cars - exp_cars) <= slack and abs(pred_people - exp_people) <= slack


def annotation_predictor(split_dir: Path | str) -> Predictor:
    """
    Deterministic predictor that returns VisDrone GT boxes for the image stem.

    Lets CI exercise detect→census without ultralytics or DET-val on disk.
    """
    split = Path(split_dir)
    anns_dir = split / "annotations"

    def _predict(image: Path, _conf: float, _imgsz: int) -> list[tuple[int, float, tuple[float, float, float, float]]]:
        ann_path = anns_dir / f"{image.stem}.txt"
        if not ann_path.is_file():
            raise FileNotFoundError(f"missing annotation for {image.name}: {ann_path}")
        img_w, img_h = jpeg_size(image)
        rows: list[tuple[int, float, tuple[float, float, float, float]]] = []
        for det in parse_visdrone_gt_detections(ann_path, img_w, img_h):
            cls_idx = VISDRONE_CLASS_NAMES.index(det["class"])
            cx, cy, w, h = det["xywh"]
            rows.append((cls_idx, float(det["conf"]), (cx, cy, w, h)))
        return rows

    return _predict


def list_pipeline_frames(split_dir: Path | str, *, limit: int = DEFAULT_PIPELINE_LIMIT) -> list[Path]:
    """First ``limit`` JPEG paths under ``split_dir/images`` (sorted)."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    images_dir = Path(split_dir) / "images"
    if not images_dir.is_dir():
        raise FileNotFoundError(f"missing images directory: {images_dir}")
    paths = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg"})
    return paths[:limit]


def evaluate_pipeline(
    split_dir: Path | str,
    *,
    predictor: Predictor | None = None,
    slack: int = DEFAULT_COUNT_SLACK,
    limit: int = DEFAULT_PIPELINE_LIMIT,
    weights: str | Path = "yolov8n.pt",
) -> dict[str, Any]:
    """
    Run detect → census on up to ``limit`` frames; compare HUD counts to GT within slack.

    ``predictor`` defaults to annotation-backed GT (CI-safe). Pass a real YOLO
    predictor / omit with ultralytics installed to score DET-val.
    """
    split = Path(split_dir)
    anns_dir = split / "annotations"
    if not anns_dir.is_dir():
        raise FileNotFoundError(f"missing annotations directory: {anns_dir}")

    pred = predictor if predictor is not None else annotation_predictor(split)
    frames = list_pipeline_frames(split, limit=limit)
    if not frames:
        raise FileNotFoundError(f"no JPEG images in {split / 'images'}")

    results: list[dict[str, Any]] = []
    passed = 0
    for image_path in frames:
        ann_path = anns_dir / f"{image_path.stem}.txt"
        if not ann_path.is_file():
            raise FileNotFoundError(f"missing annotation for {image_path.name}: {ann_path}")

        dets = detect_frame(image_path, weights=weights, predictor=pred)
        predicted = census(dets)
        expected = ground_truth_census(ann_path, image_path)
        ok = hud_within_slack(predicted, expected, slack=slack)
        if ok:
            passed += 1
        results.append(
            {
                "image": image_path.name,
                "ok": ok,
                "predicted": {"cars": predicted["cars"], "people": predicted["people"]},
                "expected": {"cars": expected["cars"], "people": expected["people"]},
            }
        )

    return {
        "limit": limit,
        "slack": slack,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "all_ok": passed == len(results),
        "results": results,
    }
