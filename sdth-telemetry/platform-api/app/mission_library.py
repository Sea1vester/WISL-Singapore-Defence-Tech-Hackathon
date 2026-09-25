import sqlite3
import unicodedata
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.auth import require_api_key
from app.db import db_session

router = APIRouter(prefix="/v1/library", tags=["mission-library"], dependencies=[Depends(require_api_key)])


class FolderWrite(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parent_id: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        value = unicodedata.normalize("NFC", value.strip())
        if not value or value in {".", ".."} or any(c in "/\\" or unicodedata.category(c).startswith("C") for c in value):
            raise ValueError("Use a folder name without slashes or control characters.")
        return value


class FlightFolderWrite(BaseModel):
    folder_id: str | None = Field(default=None, min_length=1, max_length=100)


def require_folder(conn, folder_id: str | None) -> None:
    if folder_id is not None and not conn.execute("SELECT 1 FROM mission_folders WHERE id = ?", (folder_id,)).fetchone():
        raise HTTPException(404, "Folder no longer exists. Refresh the mission explorer.")


def validate_tree(conn, folder_id: str, parent_id: str | None) -> None:
    parents = dict(conn.execute("SELECT id, parent_id FROM mission_folders").fetchall())
    parents[folder_id] = parent_id
    for current in parents:
        visited = set()
        while current is not None:
            if current in visited:
                raise HTTPException(409, "A folder cannot be moved inside itself or one of its subfolders.")
            visited.add(current)
            if len(visited) > 16:
                raise HTTPException(409, "Folders can be nested up to 16 levels deep.")
            current = parents[current]


@router.get("")
def get_library() -> dict:
    with db_session() as conn:
        folders = conn.execute("SELECT id, parent_id, name FROM mission_folders ORDER BY name_key, id").fetchall()
        entries = conn.execute("SELECT flight_id, folder_id FROM mission_folder_entries").fetchall()
    return {"folders": [dict(row) for row in folders], "flight_folders": dict(entries)}


def save_folder(body: FolderWrite, folder_id: str | None = None) -> dict:
    creating = folder_id is None
    folder_id = folder_id or str(uuid4())
    with db_session() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not creating:
            require_folder(conn, folder_id)
        require_folder(conn, body.parent_id)
        if creating and conn.execute("SELECT COUNT(*) FROM mission_folders").fetchone()[0] >= 500:
            raise HTTPException(409, "The mission library supports up to 500 folders.")
        validate_tree(conn, folder_id, body.parent_id)
        try:
            if creating:
                conn.execute("INSERT INTO mission_folders (id, parent_id, name, name_key) VALUES (?, ?, ?, ?)",
                             (folder_id, body.parent_id, body.name, body.name.casefold()))
            else:
                conn.execute("UPDATE mission_folders SET parent_id = ?, name = ?, name_key = ? WHERE id = ?",
                             (body.parent_id, body.name, body.name.casefold(), folder_id))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "A folder with this name already exists in that location.") from exc
    return {"id": folder_id, "parent_id": body.parent_id, "name": body.name}


@router.post("/folders", status_code=201)
def create_folder(body: FolderWrite) -> dict:
    return save_folder(body)


@router.put("/folders/{folder_id}")
def update_folder(folder_id: str, body: FolderWrite) -> dict:
    return save_folder(body, folder_id)


@router.put("/flights/{flight_id}/folder")
def move_flight(flight_id: str, body: FlightFolderWrite) -> dict:
    with db_session() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT 1 FROM flights WHERE id = ?", (flight_id,)).fetchone():
            raise HTTPException(404, "Recorded flight not found.")
        require_folder(conn, body.folder_id)
        if body.folder_id is None:
            conn.execute("DELETE FROM mission_folder_entries WHERE flight_id = ?", (flight_id,))
        else:
            conn.execute("INSERT INTO mission_folder_entries (flight_id, folder_id) VALUES (?, ?) "
                         "ON CONFLICT(flight_id) DO UPDATE SET folder_id = excluded.folder_id", (flight_id, body.folder_id))
    return {"flight_id": flight_id, "folder_id": body.folder_id}
