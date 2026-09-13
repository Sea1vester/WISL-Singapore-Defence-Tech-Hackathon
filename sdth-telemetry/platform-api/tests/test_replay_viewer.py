from pathlib import Path

from tests.conftest import AUTH


DEMO_CSV = Path(__file__).resolve().parents[2] / "fixtures" / "demo" / "controller_mission_alpha.csv"
REPLAY_PUBLIC = Path(__file__).resolve().parents[3] / "sdth-replay" / "public"


def test_replay_page_is_public(client):
    response = client.get("/replay/")
    assert response.status_code == 200
    body = response.text
    assert "Cesium" in body
    assert "SDTH" in body
    assert "cesium.com/downloads/cesiumjs" in body
    assert 'id="bannerClose"' in body
    assert "banner-close" in body


def test_replay_assets_and_logic_are_served(client):
    assets = client.get("/replay/assets/demo_path.json")
    assert assets.status_code == 200
    assert assets.json()["flight_id"] == "offline-demo-alpha"
    logic = client.get("/replay/lib/flight.mjs")
    assert logic.status_code == 200
    assert "export function parseFlightPath" in logic.text
    glb = client.get("/replay/assets/drone.glb")
    assert glb.status_code == 200
    assert len(glb.content) > 1000
    css = client.get("/replay/replay.css")
    assert css.status_code == 200
    assert ".banner-close" in css.text
    js = client.get("/replay/replay.js")
    assert js.status_code == 200
    assert "bannerClose" in js.text
    assert "./assets/drone.glb" in js.text
    assert "enableInspectCamera" in js.text
    assert REPLAY_PUBLIC.joinpath("index.html").is_file()
    assert REPLAY_PUBLIC.joinpath("assets", "drone.glb").is_file()


def test_flights_and_datasets_still_require_auth(client):
    assert client.get("/v1/flights").status_code == 401
    assert client.get("/v1/replay/datasets").status_code == 401


def test_dataset_list_and_load(client, tmp_path, monkeypatch):
    from app.config import settings

    from app.worker import process_job, process_raw_upload

    monkeypatch.setattr(settings, "raw_datasets_dir", str(tmp_path))
    queued: list[str] = []
    monkeypatch.setattr("app.worker.enqueue_translation_job", queued.append)
    monkeypatch.setattr(
        "app.worker.translate_with_repair",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("Ollama offline")),
    )

    sample = tmp_path / "controller_mission_alpha.csv"
    sample.write_bytes(DEMO_CSV.read_bytes())

    listed = client.get("/v1/replay/datasets", headers=AUTH)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] >= 1
    assert any(item["path"] == "controller_mission_alpha.csv" for item in body["items"])

    loaded = client.post(
        "/v1/replay/datasets/load",
        headers=AUTH,
        json={"path": "controller_mission_alpha.csv"},
    )
    assert loaded.status_code == 202, loaded.text
    payload = loaded.json()
    assert payload["upload_id"]
    assert payload["status"] == "received"
    assert payload["flight_id"] is None

    process_raw_upload(payload["upload_id"])
    if queued:
        process_job(queued[0])
    status = client.get(f"/v1/uploads/{payload['upload_id']}", headers=AUTH)
    assert status.status_code == 200, status.text
    ready = status.json()
    assert ready["status"] == "ready"
    assert ready["flight_id"]

    path = client.get(f"/v1/flights/{ready['flight_id']}/path", headers=AUTH)
    assert path.status_code == 200
    assert path.json()["count"] >= 8

    again = client.post(
        "/v1/replay/datasets/load",
        headers=AUTH,
        json={"path": "controller_mission_alpha.csv"},
    )
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "ready"
    assert again.json()["flight_id"] == ready["flight_id"]

    blocked = client.post(
        "/v1/replay/datasets/load",
        headers=AUTH,
        json={"path": "../secret.csv"},
    )
    assert blocked.status_code == 400


def test_replay_has_dark_space_theme():
    """Cesium replay retains the existing dark WISL palette."""
    css = REPLAY_PUBLIC.joinpath("replay.css").read_text()
    assert "--signal: #4fd8c4" in css
    assert "--ink: #e9edf5" in css
    assert "background: #0a0e16" in css
    assert "font-family" in css and "monospace" in css


def test_replay_has_layer_toggles():
    """Layer toggle buttons for paths/incidents/hazard are present."""
    html = REPLAY_PUBLIC.joinpath("index.html").read_text()
    assert 'data-layer="paths"' in html
    assert 'data-layer="incidents"' in html
    assert 'data-layer="hazard"' in html
    assert "layer-toggle" in html


def test_replay_has_timeline_scrubber():
    """Timeline scrubber UI elements are present in the replay page."""
    html = REPLAY_PUBLIC.joinpath("index.html").read_text()
    assert 'id="timeline-scrubber"' in html
    assert 'id="timeline-progress"' in html
    assert 'id="timeline-head"' in html
    assert 'id="timeline-incidents"' in html
    assert 'id="timeline-time"' in html


def test_replay_has_failure_banner_with_jump_buttons():
    """Failure banner includes jump-to buttons for incidents."""
    html = REPLAY_PUBLIC.joinpath("index.html").read_text()
    assert 'id="bannerClose"' in html
    assert 'id="jumpButtons"' in html
    assert "jump-buttons" in html
    assert "banner-close" in html


def test_replay_js_has_camera_follow():
    """Replay JS includes camera follow / orbit functionality."""
    js = REPLAY_PUBLIC.joinpath("replay.js").read_text()
    assert "setupClickToFollow" in js
    assert "startOrbitFromCamera" in js
    assert "trackedEntity" in js
    assert "followEntity" in js
    assert "LEFT_CLICK" in js


def test_replay_js_has_multi_flight_support():
    """Replay JS supports multiple color-coded flights on one globe."""
    js = REPLAY_PUBLIC.joinpath("replay.js").read_text()
    assert "COLORS" in js
    assert "showAllFlights" in js
    assert "uav-" in js
    assert "trail-" in js


def test_replay_has_glowing_drone_markers():
    """Drone markers use glow effects with neon-style points."""
    js = REPLAY_PUBLIC.joinpath("replay.js").read_text()
    assert "uavVisual" in js
    assert "disableDepthTestDistance" in js
    assert "scaleByDistance" in js


def test_replay_css_has_timeline_tick_styles():
    """CSS includes timeline tick styles for incidents and GPS warnings."""
    css = REPLAY_PUBLIC.joinpath("replay.css").read_text()
    assert ".timeline-tick.warning" in css
    assert ".timeline-tick.critical" in css
    assert ".timeline-tick.gps-warning" in css


def test_replay_has_multi_flight_toggle():
    """Multi-flight toggle button is in the replay UI."""
    html = REPLAY_PUBLIC.joinpath("index.html").read_text()
    assert "multiFlightToggle" in html
    assert "All Missions" in html
    css = REPLAY_PUBLIC.joinpath("replay.css").read_text()
    assert ".layer-toggle.multi-toggle" in css


def test_replay_has_flight_legend():
    """Flight legend panel for color-coded missions is present."""
    html = REPLAY_PUBLIC.joinpath("index.html").read_text()
    assert 'id="flightLegend"' in html
    css = REPLAY_PUBLIC.joinpath("replay.css").read_text()
    assert ".flight-legend" in css
    assert ".flight-legend-dot" in css
    assert ".flight-legend-label" in css


def test_replay_js_has_incident_tooltip():
    """Replay JS includes incident hover tooltip functionality."""
    js = REPLAY_PUBLIC.joinpath("replay.js").read_text()
    assert "setupIncidentTooltip" in js
    assert "incident-tooltip" in js


def test_replay_js_has_unified_timeline():
    """Replay JS supports unified multi-flight timeline."""
    js = REPLAY_PUBLIC.joinpath("replay.js").read_text()
    assert "unifiedStart" in js
    assert "unifiedStop" in js
    assert "followFlightId" in js


def test_replay_js_uxo_constant_declared():
    """UXO_INCIDENT_TYPES is a properly declared const."""
    js = REPLAY_PUBLIC.joinpath("replay.js").read_text()
    assert "const UXO_INCIDENT_TYPES" in js


def test_replay_has_hazard_animation_cleanup():
    """Hazard circle animations are properly cleaned up on entity clear."""
    js = REPLAY_PUBLIC.joinpath("replay.js").read_text()
    assert "stopHazardAnimations" in js
