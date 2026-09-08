"""Frame detection: YOLOv8n inference → VisDrone class boxes.

``detect_frame(image) → [{class, conf, xywh}]`` — deterministic given weights.
No tracking IDs. Class names are the 10 VisDrone categories (ignored dropped).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sdth_vision.finetune import DEFAULT_BASE_WEIGHTS, DEFAULT_IMG_SIZE
from sdth_vision.visdrone import VISDRONE_CLASS_NAMES

# Predictor: (image_path, conf, imgsz) → sequence of raw detections.
# Each raw item: (class_index_or_name, conf, xywh_pixels) where xywh is
# center_x, center_y, width, height in image pixels.
Predictor = Callable[[Path, float, int], Sequence[tuple[Any, float, Sequence[float]]]]

DEFAULT_CONF = 0.25


def class_name(cls: int | str) -> str:
    """Map a YOLO class index or name to a VisDrone class string."""
    if isinstance(cls, str):
        if cls not in VISDRONE_CLASS_NAMES:
            raise ValueError(f"unknown VisDrone class name: {cls!r}")
        return cls
    if cls < 0 or cls >= len(VISDRONE_CLASS_NAMES):
        raise ValueError(f"class index out of range for VisDrone (0..9): {cls}")
    return VISDRONE_CLASS_NAMES[cls]


def normalize_detection(
    cls: int | str,
    conf: float,
    xywh: Sequence[float],
) -> dict[str, Any]:
    """Build one detection dict: ``{class, conf, xywh}`` (no track id)."""
    if len(xywh) != 4:
        raise ValueError(f"xywh must have 4 values, got {len(xywh)}")
    return {
        "class": class_name(cls),
        "conf": float(conf),
        "xywh": (float(xywh[0]), float(xywh[1]), float(xywh[2]), float(xywh[3])),
    }


def format_detections(
    rows: Sequence[tuple[Any, float, Sequence[float]]],
) -> list[dict[str, Any]]:
    """Convert raw (cls, conf, xywh) rows into the public detection list."""
    return [normalize_detection(cls, conf, xywh) for cls, conf, xywh in rows]


def _ultralytics_predict(
    image: Path,
    *,
    weights: str | Path,
    conf: float,
    imgsz: int,
) -> list[tuple[int, float, tuple[float, float, float, float]]]:
    try:
        from ultralytics import YOLO  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional heavy dep
        raise RuntimeError(
            "ultralytics is required for detect_frame without an injected predictor; "
            "pip install ultralytics or pass predictor="
        ) from exc

    model = YOLO(str(weights))
    # Override names to VisDrone when the checkpoint still carries COCO names
    # but was fine-tuned / intended for the 10-class VisDrone head.
    if getattr(model, "names", None) is not None and len(model.names) == len(VISDRONE_CLASS_NAMES):
        model.names = {i: name for i, name in enumerate(VISDRONE_CLASS_NAMES)}

    results = model.predict(
        source=str(image),
        conf=conf,
        imgsz=imgsz,
        verbose=False,
    )
    rows: list[tuple[int, float, tuple[float, float, float, float]]] = []
    for result in results:
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            continue
        xywh = boxes.xywh.cpu().tolist()
        confs = boxes.conf.cpu().tolist()
        clss = boxes.cls.cpu().tolist()
        for c, score, box in zip(clss, confs, xywh, strict=True):
            rows.append((int(c), float(score), (float(box[0]), float(box[1]), float(box[2]), float(box[3]))))
    return rows


def detect_frame(
    image: Path | str,
    *,
    weights: str | Path = DEFAULT_BASE_WEIGHTS,
    conf: float = DEFAULT_CONF,
    imgsz: int = DEFAULT_IMG_SIZE,
    predictor: Predictor | None = None,
) -> list[dict[str, Any]]:
    """
    Run detector on one JPEG frame.

    Returns a list of ``{class, conf, xywh}`` with VisDrone class names.
    ``xywh`` is pixel center-x, center-y, width, height. No tracking IDs.

    Pass ``predictor`` to inject a deterministic stub (CI without ultralytics).
    """
    path = Path(image)
    if not path.is_file():
        raise FileNotFoundError(f"image not found: {path}")

    if predictor is not None:
        raw = predictor(path, conf, imgsz)
    else:
        raw = _ultralytics_predict(path, weights=weights, conf=conf, imgsz=imgsz)

    dets = format_detections(raw)
    # Stable order for determinism given the same weights/predictor output.
    dets.sort(key=lambda d: (-d["conf"], d["class"], d["xywh"]))
    return dets


def detections_have_track_ids(dets: Sequence[Mapping[str, Any]]) -> bool:
    """True if any detection carries a tracking id field (must stay False for v1)."""
    return any("track_id" in d or "tracker_id" in d for d in dets)
