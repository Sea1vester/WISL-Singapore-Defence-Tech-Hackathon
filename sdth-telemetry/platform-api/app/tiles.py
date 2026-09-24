"""Imagery tile proxy with an on-disk cache so the replay works on a LAN-only demo.

OSM map tiles and Esri World Imagery satellite tiles are cached under
``settings.tile_cache_dir``. When the upstream cannot be reached the proxy
returns a 1x1 transparent PNG with ``X-WISL-Tile: missing`` so the scene still
renders terrain and buildings without imagery.
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.config import settings

logger = logging.getLogger("sdth.tiles")
router = APIRouter(prefix="/tiles", tags=["tiles"])
OSM_UPSTREAM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
SAT_UPSTREAM = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
USER_AGENT = "WISL-replay/1.0 (post-flight review demo; local tile cache)"
MAX_ZOOM = 19
CACHE_HEADERS = {"Cache-Control": "public, max-age=604800"}

# 1x1 fully transparent PNG, returned instead of 502 when upstream fails.
TRANSPARENT_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
_missing_warned_zooms: set[tuple[str, int]] = set()


def _tile_path(source: str, z: int, x: int, y: int, suffix: str) -> Path:
    root = Path(settings.tile_cache_dir)
    if source == "sat":
        return root / "sat" / str(z) / str(x) / f"{y}{suffix}"
    return root / str(z) / str(x) / f"{y}{suffix}"


def _missing_tile(source: str, z: int) -> Response:
    key = (source, z)
    if key not in _missing_warned_zooms:
        _missing_warned_zooms.add(key)
        logger.warning(
            "Tile upstream unavailable for %s zoom %s; serving transparent placeholders",
            source, z,
        )
    return Response(
        content=TRANSPARENT_PNG,
        media_type="image/png",
        headers={**CACHE_HEADERS, "X-WISL-Tile": "missing"},
    )


def _proxy_tile(source: str, z: int, x: int, y: int, suffix: str, upstream: str):
    if z < 0 or z > MAX_ZOOM or x < 0 or y < 0 or x >= 2**z or y >= 2**z:
        raise HTTPException(404, "Tile out of range")
    path = _tile_path(source, z, x, y, suffix)
    media_type = "image/jpeg" if suffix == ".jpg" else "image/png"
    if path.is_file():
        return FileResponse(path, media_type=media_type, headers=CACHE_HEADERS)
    url = upstream.format(z=z, x=x, y=y)
    try:
        with httpx.Client(timeout=10, trust_env=False) as client:
            upstream_response = client.get(url, headers={"User-Agent": USER_AGENT})
        if upstream_response.status_code != 200:
            return _missing_tile(source, z)
    except httpx.HTTPError:
        return _missing_tile(source, z)
    body = upstream_response.content
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return Response(content=body, media_type=media_type, headers=CACHE_HEADERS)


@router.get("/sat/{z}/{x}/{y}.jpg")
def satellite_tile(z: int, x: int, y: int):
    return _proxy_tile("sat", z, x, y, ".jpg", SAT_UPSTREAM)


@router.get("/{z}/{x}/{y}.png")
def tile(z: int, x: int, y: int):
    return _proxy_tile("osm", z, x, y, ".png", OSM_UPSTREAM)
