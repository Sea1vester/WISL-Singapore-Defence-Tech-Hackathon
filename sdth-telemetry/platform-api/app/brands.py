"""Identify the hardware brand that produced a log / ingest source.

Catalog is derived from parsers and datasets currently in this repo, not from
vendor marketing names guessed at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Brand:
    id: str
    name: str
    family: str
    log_formats: tuple[str, ...]
    source_markers: tuple[str, ...]
    model_markers: tuple[str, ...]


# Order matters: first match wins. More specific markers before generic ones.
# Cheap/COTS brands lead the catalog — that's the fleet we're actually sized for.
# The two tactical-platform entries stay for format coverage and backward-compat with
# already-ingested test flights, but are no longer the headline target segment.
BRANDS: tuple[Brand, ...] = (
    Brand(
        id="dji",
        name="DJI",
        family="multirotor",
        log_formats=("FlightRecord CSV", "Excel FlightRecord"),
        source_markers=("dji-csv", "dji-excel"),
        model_markers=("dji", "mini 4", "mavic", "phantom", "air 3", "matrice"),
    ),
    Brand(
        id="px4",
        name="PX4 / Auterion",
        family="autopilot",
        log_formats=("ULog .ulg", ".ulog"),
        source_markers=("px4-ulg", "px4", "auterion"),
        model_markers=("px4", "auterion"),
    ),
    Brand(
        id="ardupilot",
        name="ArduPilot",
        family="autopilot",
        log_formats=("DataFlash .bin", "MAVLink .tlog"),
        source_markers=("ardupilot-bin", "ardupilot-tlog", "ardupilot"),
        model_markers=("ardupilot", "arducopter", "arduplane"),
    ),
    Brand(
        id="hermes900",
        name="Elbit Hermes 900",
        family="fixed_wing_uav",
        log_formats=("STANAG 4586 syslog", ".stanag", ".hermes"),
        source_markers=("hermes", "stanag"),
        model_markers=("hermes 900", "hermes900"),
    ),
    Brand(
        id="orbiter4",
        name="Aeronautics Orbiter 4",
        family="fixed_wing_uav",
        log_formats=("Orbiter JSON", "Orbiter CSV"),
        source_markers=("orbiter",),
        model_markers=("orbiter 4", "orbiter4"),
    ),
    Brand(
        id="aunav",
        name="aunav.NEO HD (ST Engineering Taurus UGV)",
        family="ugv",
        log_formats=("ROS console", ".ros", ".aunav"),
        source_markers=("aunav", "taurus"),
        model_markers=("aunav", "neo hd", "taurus"),
    ),
)

GENERIC = Brand(
    id="generic",
    name="Unknown / generic",
    family="unknown",
    log_formats=(),
    source_markers=(),
    model_markers=(),
)


def _haystack(canonical_or_meta: dict[str, Any], *, source: str | None = None) -> str:
    parts: list[str] = []
    if source:
        parts.append(str(source))
    parts.append(str(canonical_or_meta.get("source") or ""))
    metadata = canonical_or_meta.get("metadata") if isinstance(canonical_or_meta.get("metadata"), dict) else {}
    sensors = canonical_or_meta.get("sensors") if isinstance(canonical_or_meta.get("sensors"), dict) else {}
    extra = sensors.get("extra") if isinstance(sensors.get("extra"), dict) else {}
    for value in (
        metadata.get("source"),
        metadata.get("drone_model"),
        metadata.get("brand"),
        sensors.get("drone_model"),
        extra.get("drone_model"),
        extra.get("_source_format"),
        canonical_or_meta.get("drone_model"),
        canonical_or_meta.get("_source_format"),
    ):
        if value:
            parts.append(str(value))
    return " ".join(parts).lower()


def identify_brand(canonical_or_meta: dict[str, Any] | None = None, *, source: str | None = None) -> Brand:
    text = _haystack(canonical_or_meta or {}, source=source)
    if not text.strip():
        return GENERIC
    for brand in BRANDS:
        if any(marker in text for marker in brand.source_markers):
            return brand
        if any(marker in text for marker in brand.model_markers):
            return brand
    return GENERIC


def brand_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": brand.id,
            "name": brand.name,
            "family": brand.family,
            "log_formats": list(brand.log_formats),
        }
        for brand in (*BRANDS, GENERIC)
    ]
