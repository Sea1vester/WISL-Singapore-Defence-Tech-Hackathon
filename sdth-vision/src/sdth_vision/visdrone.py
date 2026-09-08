"""VisDrone DET annotation conversion for YOLO fine-tuning."""
from __future__ import annotations

import shutil
import struct
from pathlib import Path
from typing import Iterable

# VisDrone object categories 1..10 (category 0 = ignored regions, dropped).
VISDRONE_CLASS_NAMES: tuple[str, ...] = (
    "pedestrian",
    "people",
    "bicycle",
    "car",
    "van",
    "truck",
    "tricycle",
    "awning-tricycle",
    "bus",
    "motor",
)

# HUD roll-ups (product census): cars = car+van+truck+bus; people = pedestrian+people.
CARS_CLASSES: frozenset[str] = frozenset({"car", "van", "truck", "bus"})
PEOPLE_CLASSES: frozenset[str] = frozenset({"pedestrian", "people"})


def jpeg_size(path: Path) -> tuple[int, int]:
    """Return (width, height) from a JPEG SOF marker without heavy deps."""
    data = path.read_bytes()
    if len(data) < 4 or data[0:2] != b"\xff\xd8":
        raise ValueError(f"not a JPEG: {path}")
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7):
            i += 2
            continue
        if i + 3 >= len(data):
            break
        length = struct.unpack(">H", data[i + 2 : i + 4])[0]
        # SOF0..SOF3, SOF5..SOF7, SOF9..SOF11, SOF13..SOF15
        if marker in (
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        ):
            height, width = struct.unpack(">HH", data[i + 5 : i + 9])
            return int(width), int(height)
        i += 2 + length
    raise ValueError(f"JPEG size not found: {path}")


def visdrone_box_to_yolo(
    left: float,
    top: float,
    width: float,
    height: float,
    category: int,
    img_w: int,
    img_h: int,
) -> tuple[int, float, float, float, float] | None:
    """
    Convert one VisDrone box to YOLO ``cls cx cy w h`` (normalized).

    Drops ignored category 0. Remaps VisDrone 1..10 -> YOLO 0..9.
    Returns None when the box should be skipped.
    """
    if category == 0:
        return None
    if category < 1 or category > len(VISDRONE_CLASS_NAMES):
        raise ValueError(f"unsupported VisDrone category: {category}")
    if img_w <= 0 or img_h <= 0:
        raise ValueError("image dimensions must be positive")
    if width <= 0 or height <= 0:
        return None

    yolo_cls = category - 1
    cx = (left + width / 2.0) / img_w
    cy = (top + height / 2.0) / img_h
    nw = width / img_w
    nh = height / img_h
    return yolo_cls, cx, cy, nw, nh


def parse_visdrone_annotation_line(
    line: str,
    img_w: int,
    img_h: int,
) -> tuple[int, float, float, float, float] | None:
    """Parse ``left,top,w,h,score,class,trunc,occ`` into a YOLO label or None."""
    text = line.strip()
    if not text:
        return None
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 6:
        raise ValueError(f"malformed VisDrone annotation: {line!r}")
    left, top, w, h = (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
    category = int(parts[5])
    return visdrone_box_to_yolo(left, top, w, h, category, img_w, img_h)


def convert_annotation_file(
    ann_path: Path,
    img_w: int,
    img_h: int,
) -> list[tuple[int, float, float, float, float]]:
    """Convert a VisDrone .txt annotation file to YOLO rows (class 0 dropped)."""
    rows: list[tuple[int, float, float, float, float]] = []
    for line in ann_path.read_text(encoding="utf-8").splitlines():
        converted = parse_visdrone_annotation_line(line, img_w, img_h)
        if converted is not None:
            rows.append(converted)
    return rows


def format_yolo_label(rows: Iterable[tuple[int, float, float, float, float]]) -> str:
    lines = [
        f"{cls} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for cls, cx, cy, w, h in rows
    ]
    return ("\n".join(lines) + "\n") if lines else ""


def visdrone_det_to_yolo(
    split_dir: Path | str,
    out_dir: Path | str | None = None,
    *,
    copy_images: bool = True,
) -> Path:
    """
    Convert a VisDrone DET split (``images/`` + ``annotations/``) to YOLO layout.

    Writes ``out_dir/images`` and ``out_dir/labels`` with matching stems.
    Drops VisDrone class 0 (ignored regions). Stores 10 classes as YOLO 0..9.
    """
    split = Path(split_dir)
    images_dir = split / "images"
    anns_dir = split / "annotations"
    if not images_dir.is_dir():
        raise FileNotFoundError(f"missing images directory: {images_dir}")
    if not anns_dir.is_dir():
        raise FileNotFoundError(f"missing annotations directory: {anns_dir}")

    dest = Path(out_dir) if out_dir is not None else split / "yolo"
    dest_images = dest / "images"
    dest_labels = dest / "labels"
    dest_images.mkdir(parents=True, exist_ok=True)
    dest_labels.mkdir(parents=True, exist_ok=True)

    image_paths = sorted(
        p for p in images_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg"}
    )
    if not image_paths:
        raise FileNotFoundError(f"no JPEG images in {images_dir}")

    for image_path in image_paths:
        ann_path = anns_dir / f"{image_path.stem}.txt"
        if not ann_path.is_file():
            raise FileNotFoundError(f"missing annotation for {image_path.name}: {ann_path}")

        img_w, img_h = jpeg_size(image_path)
        rows = convert_annotation_file(ann_path, img_w, img_h)
        (dest_labels / f"{image_path.stem}.txt").write_text(
            format_yolo_label(rows),
            encoding="utf-8",
        )

        target = dest_images / image_path.name
        if copy_images:
            shutil.copy2(image_path, target)
        elif not target.exists():
            target.symlink_to(image_path.resolve())

    (dest / "classes.txt").write_text(
        "\n".join(VISDRONE_CLASS_NAMES) + "\n",
        encoding="utf-8",
    )
    return dest
