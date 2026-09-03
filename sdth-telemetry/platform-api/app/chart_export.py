"""
Sensor chart export using matplotlib.

Generates PNG charts for a flight's canonical records and stores them as
visual_records (kind='sensor_chart'). Called eagerly from the worker after
canonical records are ready (ingest pipeline done state).

Charts generated per flight:
  - altitude_m    (position.alt_m over time)
  - battery_pct   (battery.percent over time)
  - attitude      (roll, pitch, yaw over time - combined)

matplotlib is only imported at call time so the module is safe to import
even if matplotlib is not installed; the export simply logs a warning.
"""
from __future__ import annotations

import io
import logging
from typing import Any

logger = logging.getLogger("chart_export")


def _fetch_canonical_records(conn, flight_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT recorded_at, canonical_json
        FROM canonical_records
        WHERE flight_id = ?
        ORDER BY recorded_at ASC
        """,
        (flight_id,),
    ).fetchall()
    import json

    return [
        {"recorded_at": r["recorded_at"], **json.loads(r["canonical_json"])}
        for r in rows
    ]


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_series(records: list[dict]) -> dict[str, list]:
    """
    Extract numeric series from canonical records.
    Returns a dict of series_name -> list of (timestamp_s, value) tuples.
    """
    import datetime

    def to_epoch(ts: str) -> float | None:
        try:
            return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except (ValueError, AttributeError):
            return None

    alt: list[tuple[float, float]] = []
    bat: list[tuple[float, float]] = []
    roll: list[tuple[float, float]] = []
    pitch: list[tuple[float, float]] = []
    yaw: list[tuple[float, float]] = []

    for rec in records:
        ts = to_epoch(rec.get("recorded_at") or rec.get("timestamp_utc", ""))
        if ts is None:
            continue
        pos = rec.get("position", {}) or {}
        bat_d = rec.get("battery", {}) or {}
        att = rec.get("attitude", {}) or {}

        v = _safe_float(pos.get("alt_m"))
        if v is not None:
            alt.append((ts, v))
        v = _safe_float(bat_d.get("percent"))
        if v is not None:
            bat.append((ts, v))
        v = _safe_float(att.get("roll_deg"))
        if v is not None:
            roll.append((ts, v))
        v = _safe_float(att.get("pitch_deg"))
        if v is not None:
            pitch.append((ts, v))
        v = _safe_float(att.get("yaw_deg"))
        if v is not None:
            yaw.append((ts, v))

    return {"altitude_m": alt, "battery_pct": bat, "roll_deg": roll, "pitch_deg": pitch, "yaw_deg": yaw}


def _render_chart(
    title: str,
    series: dict[str, list[tuple[float, float]]],
    ylabel: str,
    colors: list[str] | None = None,
) -> bytes | None:
    """Render a matplotlib chart and return PNG bytes, or None on error."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless backend
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import datetime
    except ImportError:
        logger.warning("matplotlib not installed; skipping chart export")
        return None

    fig, ax = plt.subplots(figsize=(10, 3.5))
    color_cycle = colors or ["#2463b0", "#c45c16", "#2e8c40", "#7a48a8"]

    plotted = False
    for i, (name, points) in enumerate(series.items()):
        if not points:
            continue
        xs = [datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc) for t, _ in points]
        ys = [v for _, v in points]
        ax.plot(xs, ys, label=name, color=color_cycle[i % len(color_cycle)], linewidth=1.2)
        plotted = True

    if not plotted:
        plt.close(fig)
        return None

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.autofmt_xdate(rotation=30, ha="right")
    ax.set_title(title, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(True, alpha=0.3)
    if len(series) > 1:
        ax.legend(fontsize=8)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def export_charts_for_flight(flight_id: str) -> int:
    """
    Generate and save sensor charts for a flight.
    Returns the number of charts saved.

    Called from the worker after canonical records are ready.
    Safe to call multiple times - existing charts are not duplicated
    (checks for existing 'sensor_chart' visuals for this flight first).
    """
    try:
        from app.db import db_session
        from app.visuals import list_visuals, save_visual
    except ImportError as exc:
        logger.error("chart_export: import failed: %s", exc)
        return 0

    with db_session() as conn:
        # Skip if charts already exist for this flight
        existing = list_visuals(flight_id, kind="sensor_chart")
        if existing:
            logger.debug("Charts already exist for flight %s, skipping", flight_id)
            return 0

        records = _fetch_canonical_records(conn, flight_id)

    if not records:
        logger.debug("No canonical records for flight %s; skipping chart export", flight_id)
        return 0

    series = _extract_series(records)
    # Use the first recorded_at as the anchor timestamp for the chart
    recorded_at = records[0].get("recorded_at") or records[0].get("timestamp_utc", "")
    saved = 0

    # Chart 1: Altitude
    png = _render_chart(
        f"Altitude - flight {flight_id[:8]}",
        {"alt_m": series["altitude_m"]},
        ylabel="Altitude (m)",
    )
    if png:
        save_visual(
            flight_id=flight_id,
            recorded_at=recorded_at,
            kind="sensor_chart",
            data=png,
            mime_type="image/png",
            caption="Altitude over time",
            source="worker",
        )
        saved += 1

    # Chart 2: Battery
    png = _render_chart(
        f"Battery - flight {flight_id[:8]}",
        {"battery_pct": series["battery_pct"]},
        ylabel="Battery (%)",
        colors=["#c45c16"],
    )
    if png:
        save_visual(
            flight_id=flight_id,
            recorded_at=recorded_at,
            kind="sensor_chart",
            data=png,
            mime_type="image/png",
            caption="Battery percentage over time",
            source="worker",
        )
        saved += 1

    # Chart 3: Attitude (roll / pitch / yaw combined)
    att_series = {k: series[k] for k in ("roll_deg", "pitch_deg", "yaw_deg") if series[k]}
    if att_series:
        png = _render_chart(
            f"Attitude - flight {flight_id[:8]}",
            att_series,
            ylabel="Degrees",
            colors=["#2e8c40", "#7a48a8", "#b8941c"],
        )
        if png:
            save_visual(
                flight_id=flight_id,
                recorded_at=recorded_at,
                kind="sensor_chart",
                data=png,
                mime_type="image/png",
                caption="Roll / Pitch / Yaw over time",
                source="worker",
            )
            saved += 1

    logger.info("chart_export: saved %d charts for flight %s", saved, flight_id)
    return saved
