import pytest

from app.config import settings

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_tile_serves_cached_file_without_network(client, tmp_path, monkeypatch):
    cache = tmp_path / "tiles"
    tile = cache / "10" / "511" / "340.png"
    tile.parent.mkdir(parents=True)
    tile.write_bytes(PNG_1X1)
    monkeypatch.setattr(settings, "tile_cache_dir", str(cache))

    def no_network(*args, **kwargs):
        raise AssertionError("network fetch attempted for a cached tile")

    monkeypatch.setattr("app.tiles.httpx.Client", no_network)
    response = client.get("/tiles/10/511/340.png")
    assert response.status_code == 200
    assert response.content == PNG_1X1
    assert response.headers["cache-control"] == "public, max-age=604800"


def test_tile_502_when_upstream_fails(client, tmp_path, monkeypatch):
    cache = tmp_path / "tiles"
    monkeypatch.setattr(settings, "tile_cache_dir", str(cache))

    class FailingClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs):
            import httpx
            raise httpx.ConnectError("offline")

    monkeypatch.setattr("app.tiles.httpx.Client", FailingClient)
    response = client.get("/tiles/10/511/340.png")
    assert response.status_code == 502
    assert not (cache / "10" / "511" / "340.png").exists()
