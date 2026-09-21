"""OSM tile proxy with an on-disk cache so the replay works on a LAN-only demo."""
from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.config import settings

router = APIRouter(prefix="/tiles", tags=["tiles"])
OSM_UPSTREAM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USER_AGENT = "WISL-replay/1.0 (post-flight review demo; local tile cache)"
MAX_ZOOM = 17
CACHE_HEADERS = {"Cache-Control": "public, max-age=604800"}


def _tile_path(z: int, x: int, y: int) -> Path:
    return Path(settings.tile_cache_dir) / str(z) / str(x) / f"{y}.png"


@router.get("/{z}/{x}/{y}.png")
def tile(z: int, x: int, y: int):
    if z < 0 or z > MAX_ZOOM or x < 0 or y < 0 or x >= 2**z or y >= 2**z:
        raise HTTPException(404, "Tile out of range")
    path = _tile_path(z, x, y)
    if path.is_file():
        return FileResponse(path, media_type="image/png", headers=CACHE_HEADERS)
    url = OSM_UPSTREAM.format(z=z, x=x, y=y)
    try:
        with httpx.Client(timeout=10, trust_env=False) as client:
            upstream = client.get(url, headers={"User-Agent": USER_AGENT})
        if upstream.status_code != 200:
            raise HTTPException(502, "Upstream tile fetch failed")
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Upstream tile fetch failed") from exc
    body = upstream.content
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return Response(content=body, media_type="image/png", headers=CACHE_HEADERS)
