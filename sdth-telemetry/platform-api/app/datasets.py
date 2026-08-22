from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.auth import require_api_key
from app.config import settings
from app.db import db_session
from app.queue import enqueue_raw_upload
from app.schemas import new_id
from parsers.detect import detect_format
from parsers.registry import detect_registry_format

router = APIRouter(prefix="/v1/replay", tags=["replay"])

LOG_SUFFIXES = {
    ".bin",
    ".csv",
    ".hex",
    ".hermes",
    ".json",
    ".log",
    ".ros",
    ".stanag",
    ".syslog",
    ".tlog",
    ".ulg",
    ".ulog",
    ".xlsx",
    ".xml",
}
SKIP_DIR_NAMES = {".git", ".wfw", "__pycache__", "node_modules", ".venv"}


class DatasetItem(BaseModel):
    path: str
    name: str
    size_bytes: int
    parser_hint: str


class DatasetListResponse(BaseModel):
    root: str
    items: list[DatasetItem]
    total: int


class LoadDatasetRequest(BaseModel):
    path: str = Field(min_length=1)


class LoadDatasetResponse(BaseModel):
    flight_id: str | None
    upload_id: str
    status: str
    duplicate: bool = False
    error: str | None = None


def datasets_root() -> Path:
    root = Path(settings.raw_datasets_dir).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset directory not found: {root}",
        )
    return root


def resolve_dataset_path(relative_path: str) -> Path:
    root = datasets_root()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path is outside the dataset directory")
    if not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset file not found")
    return candidate


def _parser_hint(path: Path) -> str:
    try:
        return detect_registry_format(path, original_name=path.name)
    except Exception:
        return detect_format(path)


@router.get("/datasets", response_model=DatasetListResponse)
def list_datasets(
    q: str | None = Query(default=None),
    _: str = Depends(require_api_key),
) -> DatasetListResponse:
    root = datasets_root()
    needle = (q or "").strip().lower()
    items: list[DatasetItem] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIR_NAMES and not name.startswith(".")]
        for filename in filenames:
            if filename.startswith("."):
                continue
            path = Path(dirpath) / filename
            if path.suffix.lower() not in LOG_SUFFIXES:
                continue
            relative = path.relative_to(root).as_posix()
            if needle and needle not in relative.lower():
                continue
            items.append(
                DatasetItem(
                    path=relative,
                    name=filename,
                    size_bytes=path.stat().st_size,
                    parser_hint=_parser_hint(path),
                )
            )
            if len(items) >= 400:
                break
        if len(items) >= 400:
            break
    items.sort(key=lambda item: item.path.lower())
    return DatasetListResponse(root=str(root), items=items, total=len(items))


@router.post("/datasets/load", response_model=LoadDatasetResponse)
def load_dataset(
    body: LoadDatasetRequest,
    response: Response,
    _: str = Depends(require_api_key),
) -> LoadDatasetResponse:
    path = resolve_dataset_path(body.path)
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    duplicate = False
    should_enqueue = False
    upload_id = new_id()
    current_status = "received"
    current_flight: str | None = None
    with db_session() as conn:
        existing = conn.execute(
            "SELECT id, status, flight_id FROM raw_uploads WHERE sha256 = ?",
            (sha256,),
        ).fetchone()
        if existing and existing["flight_id"] and existing["status"] == "ready":
            return LoadDatasetResponse(
                flight_id=existing["flight_id"],
                upload_id=existing["id"],
                status=existing["status"],
                duplicate=True,
            )
        if existing:
            duplicate = True
            upload_id = existing["id"]
            current_status = existing["status"]
            current_flight = existing["flight_id"]
            if existing["status"] == "failed":
                conn.execute(
                    "UPDATE raw_uploads SET status = 'received', error = NULL WHERE id = ?",
                    (upload_id,),
                )
                current_status = "received"
                current_flight = None
                should_enqueue = True
        else:
            conn.execute(
                """
                INSERT INTO raw_uploads (
                  id, sha256, original_name, stored_path, size_bytes, status,
                  provenance_json
                ) VALUES (?, ?, ?, ?, ?, 'received', ?)
                """,
                (
                    upload_id,
                    sha256,
                    path.name,
                    str(path),
                    path.stat().st_size,
                    '{"transport":"local-dataset"}',
                ),
            )
            should_enqueue = True

    if should_enqueue:
        enqueue_raw_upload(upload_id)

    response.status_code = status.HTTP_202_ACCEPTED
    return LoadDatasetResponse(
        flight_id=current_flight,
        upload_id=upload_id,
        status=current_status,
        duplicate=duplicate,
    )
