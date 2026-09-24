"""Build a map-ready GeoJSON FeatureCollection from stored rule incidents.

This is derived intel for an external tactical map: incident points plus
GPS-degraded zone polygons when the same pattern appears on 2+ flights.
It is not a log export. Properties stay small so the file cannot leak
raw telemetry series, serials, or vendor rows.
"""

from __future__ import annotations

import math
from typing import Any

from app.incidents import _incident_row

EARTH_RADIUS_M = 6_371_000.0
CLUSTER_RADIUS_M = 1_500.0
ZONE_PAD_M = 250.0
MIN_ZONE_FLIGHTS = 2
HOME_RADIUS_M = 50_000.0
# Collab overlay sites. Original demo logs sit on UK test homes; relative
# offsets inside each home are kept so pins and zones still match.
SINGAPORE_SITES = (
    (1.4050, 103.7000),  # Lim Chu Kang
    (1.3350, 103.6750),  # Pasir Laba
    (1.4120, 104.0280),  # Pulau Tekong
)
GPS_JUMP_TYPE = "gps_jump"
LAST_KNOWN_TYPE = "last_known_position"
OPERATOR_WARNING_TYPE = "operator_warning"
GPS_DEGRADED_HAZARD = "gps_degraded"
_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}
_WHAT = {
    (OPERATOR_WARNING_TYPE, GPS_DEGRADED_HAZARD): "GPS signal degraded",
    (OPERATOR_WARNING_TYPE, None): "Operator warning",
    (LAST_KNOWN_TYPE, GPS_DEGRADED_HAZARD): "Position froze here",
    (LAST_KNOWN_TYPE, None): "Position froze here",
    (GPS_JUMP_TYPE, None): "GPS position jumped",
    ("telemetry_gap", None): "Telemetry dropped out",
    ("battery_low", None): "Battery low",
    ("battery_critical", None): "Battery critical",
    ("attitude_shock", "mechanical_failure"): "Sudden attitude spike",
    ("attitude_shock", None): "Sudden attitude spike",
    ("mission_incomplete", "kinetic_loss"): "Mission ended without landing",
    ("mission_incomplete", None): "Mission ended without landing",
}


def public_hazard(raw: str | None) -> str | None:
    """Map internal triage labels onto the public overlay vocabulary."""
    if raw == "jamming":
        return GPS_DEGRADED_HAZARD
    return raw


def is_gps_degraded(incident: dict[str, Any]) -> bool:
    incident_type = incident.get("incident_type")
    if incident_type in {LAST_KNOWN_TYPE, GPS_JUMP_TYPE}:
        return True
    if incident_type != OPERATOR_WARNING_TYPE:
        return False
    evidence = incident.get("evidence") or {}
    return public_hazard(evidence.get("hazard")) == GPS_DEGRADED_HAZARD


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def _pad_degrees(lat: float, pad_m: float) -> tuple[float, float]:
    dlat = pad_m / 111_320.0
    cos_lat = math.cos(math.radians(lat))
    dlon = pad_m / (111_320.0 * max(0.2, abs(cos_lat)))
    return dlat, dlon


def _max_severity(values: list[str]) -> str:
    return max(values, key=lambda item: _SEVERITY_RANK.get(item, 0), default="info")


def _what(incident_type: str | None, hazard: str | None) -> str:
    if incident_type is None:
        return "Event"
    return _WHAT.get((incident_type, hazard)) or _WHAT.get((incident_type, None)) or incident_type.replace("_", " ")


def _positioned(incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    located: list[dict[str, Any]] = []
    for item in incidents:
        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            continue
        located.append(item)
    return located


def _incident_feature(item: dict[str, Any]) -> dict[str, Any]:
    evidence = item.get("evidence") or {}
    hazard = public_hazard(evidence.get("hazard"))
    incident_type = item.get("incident_type")
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [float(item["lon"]), float(item["lat"])],
        },
        "properties": {
            "kind": "pin",
            "what": _what(incident_type, hazard),
            "how_serious": item.get("severity") or "info",
            "start_time": item.get("started_at"),
            "end_time": item.get("ended_at"),
            "source": "wisl",
        },
    }


def _cluster_by_distance(incidents: list[dict[str, Any]], radius_m: float) -> list[list[dict[str, Any]]]:
    remaining = list(incidents)
    clusters: list[list[dict[str, Any]]] = []
    while remaining:
        seed = remaining.pop(0)
        cluster = [seed]
        changed = True
        while changed:
            changed = False
            keep: list[dict[str, Any]] = []
            for item in remaining:
                if any(
                    _haversine_m(item["lat"], item["lon"], other["lat"], other["lon"]) <= radius_m
                    for other in cluster
                ):
                    cluster.append(item)
                    changed = True
                else:
                    keep.append(item)
            remaining = keep
        clusters.append(cluster)
    return clusters


def _cluster_gps_incidents(incidents: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    return _cluster_by_distance(incidents, CLUSTER_RADIUS_M)


def _local_metres(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    north = (lat - origin_lat) * 111_320.0
    east = (lon - origin_lon) * 111_320.0 * math.cos(math.radians(origin_lat))
    return north, east


def _from_local_metres(north: float, east: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    lat = origin_lat + north / 111_320.0
    lon = origin_lon + east / (111_320.0 * max(0.2, abs(math.cos(math.radians(origin_lat)))))
    return lat, lon


def remap_incidents_to_singapore(incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Move each original home cluster onto a Singapore training area."""
    located = _positioned(incidents)
    if not located:
        return []
    clusters = _cluster_by_distance(located, HOME_RADIUS_M)
    clusters.sort(key=lambda cluster: (-len(cluster), cluster[0].get("started_at") or ""))
    remapped: list[dict[str, Any]] = []
    for index, cluster in enumerate(clusters):
        site_lat, site_lon = SINGAPORE_SITES[index % len(SINGAPORE_SITES)]
        extra_east = (index // len(SINGAPORE_SITES)) * 1_500.0
        origin_lat = sum(float(item["lat"]) for item in cluster) / len(cluster)
        origin_lon = sum(float(item["lon"]) for item in cluster) / len(cluster)
        for item in cluster:
            north, east = _local_metres(float(item["lat"]), float(item["lon"]), origin_lat, origin_lon)
            lat, lon = _from_local_metres(north, east + extra_east, site_lat, site_lon)
            moved = dict(item)
            moved["lat"] = lat
            moved["lon"] = lon
            remapped.append(moved)
    return remapped


def _zone_feature(cluster: list[dict[str, Any]]) -> dict[str, Any] | None:
    flight_ids = {item.get("flight_id") for item in cluster if item.get("flight_id")}
    if len(flight_ids) < MIN_ZONE_FLIGHTS:
        return None
    flight_count = len(flight_ids)
    lats = [float(item["lat"]) for item in cluster]
    lons = [float(item["lon"]) for item in cluster]
    mid_lat = sum(lats) / len(lats)
    dlat, dlon = _pad_degrees(mid_lat, ZONE_PAD_M)
    min_lat, max_lat = min(lats) - dlat, max(lats) + dlat
    min_lon, max_lon = min(lons) - dlon, max(lons) + dlon
    ring = [
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
        [min_lon, min_lat],
    ]
    started = min((item.get("started_at") or "") for item in cluster)
    ended_values = [item.get("ended_at") or item.get("started_at") or "" for item in cluster]
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {
            "kind": "zone",
            "what": "GPS degraded area",
            "how_serious": _max_severity([item.get("severity") or "info" for item in cluster]),
            "start_time": started or None,
            "end_time": max(ended_values) or None,
            "flights_that_saw_this": flight_count,
            "source": "wisl",
        },
    }


def build_feature_collection(incidents: list[dict[str, Any]]) -> dict[str, Any]:
    """Turn rule-incident dicts (list_flight_incidents shape) into GeoJSON."""
    located = _positioned(incidents)
    features = [_incident_feature(item) for item in located]
    gps_hits = [item for item in located if is_gps_degraded(item)]
    for cluster in _cluster_gps_incidents(gps_hits):
        zone = _zone_feature(cluster)
        if zone is not None:
            features.append(zone)
    return {
        "type": "FeatureCollection",
        "name": "wisl_incidents",
        "features": features,
    }


def incidents_from_connection(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, flight_id, source, brand, incident_type, severity, detector,
               started_at, ended_at, signature, summary, evidence_json, created_at
        FROM incidents
        WHERE detector = 'rule'
        ORDER BY started_at ASC
        """
    ).fetchall()
    return [_incident_row(row) for row in rows]


def export_intel_geojson(conn) -> dict[str, Any]:
    return build_feature_collection(remap_incidents_to_singapore(incidents_from_connection(conn)))
