"""SDTH vision sidecar (camera frames, VisDrone YOLO, census)."""

from sdth_vision.census import census
from sdth_vision.client import attach_census, ingest_camera_frames
from sdth_vision.finetune import finetune_detector
from sdth_vision.infer import detect_frame
from sdth_vision.pipeline import evaluate_pipeline
from sdth_vision.visdrone import visdrone_det_to_yolo

__all__ = [
    "ingest_camera_frames",
    "attach_census",
    "visdrone_det_to_yolo",
    "finetune_detector",
    "detect_frame",
    "census",
    "evaluate_pipeline",
]
