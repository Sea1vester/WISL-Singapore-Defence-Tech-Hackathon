"""Fine-tune YOLOv8n (COCO) on VisDrone DET YOLO labels.

Ships a CLI even when full GPU training is unavailable. Prefer checking in
eval JSON metrics rather than giant ``.pt`` weight files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sdth_vision.visdrone import VISDRONE_CLASS_NAMES

# Ultralytics COCO-pretrained nano detector (not VisDrone weights).
DEFAULT_BASE_WEIGHTS = "yolov8n.pt"
DEFAULT_PRETRAINED = "coco"
DEFAULT_IMG_SIZE = 640
DEFAULT_EPOCHS = 50
DEFAULT_BATCH = 8

# Checked-in smoke eval artifact (no giant weights in git).
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVAL_PATH = PACKAGE_ROOT / "artifacts" / "finetune_eval.json"


def write_dataset_yaml(
    out_path: Path | str,
    *,
    train_images: Path | str,
    val_images: Path | str | None = None,
) -> Path:
    """Write an Ultralytics data YAML for the 10 VisDrone classes (ignored dropped)."""
    path = Path(out_path)
    train = Path(train_images).resolve()
    val = Path(val_images).resolve() if val_images is not None else train
    names_block = "\n".join(f"  {i}: {name}" for i, name in enumerate(VISDRONE_CLASS_NAMES))
    text = (
        f"path: {train.parent.parent if train.name == 'images' else train.parent}\n"
        f"train: {train}\n"
        f"val: {val}\n"
        f"nc: {len(VISDRONE_CLASS_NAMES)}\n"
        f"names:\n{names_block}\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _smoke_metrics() -> dict[str, Any]:
    """Placeholder metrics when GPU train / ultralytics is skipped."""
    return {
        "mAP50": None,
        "mAP50-95": None,
        "precision": None,
        "recall": None,
        "note": "smoke/dry-run; run without --dry-run when ultralytics+GPU available",
    }


def build_eval_record(
    *,
    base_weights: str = DEFAULT_BASE_WEIGHTS,
    pretrained: str = DEFAULT_PRETRAINED,
    epochs: int = 0,
    imgsz: int = DEFAULT_IMG_SIZE,
    dry_run: bool = True,
    metrics: dict[str, Any] | None = None,
    data_yaml: str | None = None,
) -> dict[str, Any]:
    return {
        "base_weights": base_weights,
        "pretrained": pretrained,
        "nc": len(VISDRONE_CLASS_NAMES),
        "names": list(VISDRONE_CLASS_NAMES),
        "imgsz": imgsz,
        "epochs": epochs,
        "dry_run": dry_run,
        "data_yaml": data_yaml,
        "metrics": metrics if metrics is not None else _smoke_metrics(),
    }


def write_eval_json(record: dict[str, Any], path: Path | str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def _try_ultralytics_train(
    data_yaml: Path,
    *,
    base_weights: str,
    epochs: int,
    imgsz: int,
    batch: int,
    project: Path,
    name: str,
) -> dict[str, Any]:
    try:
        from ultralytics import YOLO  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional heavy dep
        raise RuntimeError(
            "ultralytics is required for real training; re-run with --dry-run "
            "or pip install ultralytics"
        ) from exc

    model = YOLO(base_weights)
    results = model.train(
        data=str(data_yaml),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        project=str(project),
        name=name,
        exist_ok=True,
    )
    metrics: dict[str, Any] = {"note": "ultralytics train completed"}
    # Ultralytics result shapes vary by version; keep best-effort fields.
    box = getattr(results, "box", None) or getattr(results, "results_dict", None)
    if isinstance(box, dict):
        metrics.update(
            {
                "mAP50": box.get("metrics/mAP50(B)", box.get("mAP50")),
                "mAP50-95": box.get("metrics/mAP50-95(B)", box.get("mAP50-95")),
                "precision": box.get("metrics/precision(B)", box.get("precision")),
                "recall": box.get("metrics/recall(B)", box.get("recall")),
            }
        )
    return metrics


def finetune_detector(
    train_images: Path | str,
    *,
    val_images: Path | str | None = None,
    out_dir: Path | str | None = None,
    eval_path: Path | str | None = None,
    base_weights: str = DEFAULT_BASE_WEIGHTS,
    epochs: int = DEFAULT_EPOCHS,
    imgsz: int = DEFAULT_IMG_SIZE,
    batch: int = DEFAULT_BATCH,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Fine-tune YOLOv8n (COCO) on a YOLO-layout VisDrone split.

    ``train_images`` should point at a directory of JPEGs whose sibling
    ``labels/`` holds matching ``.txt`` files (see ``visdrone_det_to_yolo``).

    When ``dry_run`` is True (or ultralytics is missing and dry_run is forced
    by the CLI), writes dataset YAML + eval JSON without training or saving
    large ``.pt`` weights.
    """
    train = Path(train_images)
    if not train.is_dir():
        raise FileNotFoundError(f"train images directory not found: {train}")

    dest = Path(out_dir) if out_dir is not None else train.parent / "finetune_runs"
    dest.mkdir(parents=True, exist_ok=True)
    data_yaml = write_dataset_yaml(
        dest / "visdrone.yaml",
        train_images=train,
        val_images=val_images,
    )

    metrics: dict[str, Any]
    ran_dry = dry_run
    if dry_run:
        metrics = _smoke_metrics()
    else:
        try:
            metrics = _try_ultralytics_train(
                data_yaml,
                base_weights=base_weights,
                epochs=epochs,
                imgsz=imgsz,
                batch=batch,
                project=dest,
                name="yolov8n_visdrone",
            )
        except RuntimeError:
            # Keep CLI usable without GPU stack: fall back to smoke eval.
            ran_dry = True
            metrics = _smoke_metrics()
            metrics["note"] = (
                "ultralytics unavailable; wrote smoke eval JSON (no .pt weights)"
            )

    record = build_eval_record(
        base_weights=base_weights,
        pretrained=DEFAULT_PRETRAINED,
        epochs=0 if ran_dry else epochs,
        imgsz=imgsz,
        dry_run=ran_dry,
        metrics=metrics,
        data_yaml=str(data_yaml),
    )
    out_eval = Path(eval_path) if eval_path is not None else dest / "finetune_eval.json"
    write_eval_json(record, out_eval)
    record["eval_path"] = str(out_eval)
    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finetune_detector",
        description=(
            "Fine-tune YOLOv8n (COCO pretrained) on VisDrone DET YOLO labels. "
            "Use --dry-run to ship CLI/eval JSON without GPU training."
        ),
    )
    parser.add_argument(
        "--train-images",
        type=Path,
        required=True,
        help="Path to YOLO images/ directory (labels/ sibling expected)",
    )
    parser.add_argument(
        "--val-images",
        type=Path,
        default=None,
        help="Optional val images/ directory (defaults to train)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Run directory for data YAML / optional train outputs",
    )
    parser.add_argument(
        "--eval-json",
        type=Path,
        default=None,
        help="Where to write eval metrics JSON (prefer this over checking in .pt)",
    )
    parser.add_argument(
        "--weights",
        default=DEFAULT_BASE_WEIGHTS,
        help=f"Base weights (default: {DEFAULT_BASE_WEIGHTS} COCO)",
    )
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--imgsz", type=int, default=DEFAULT_IMG_SIZE)
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write data YAML + smoke eval JSON without training",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    record = finetune_detector(
        args.train_images,
        val_images=args.val_images,
        out_dir=args.out_dir,
        eval_path=args.eval_json,
        base_weights=args.weights,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        dry_run=args.dry_run,
    )
    print(json.dumps({"eval_path": record["eval_path"], "dry_run": record["dry_run"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
