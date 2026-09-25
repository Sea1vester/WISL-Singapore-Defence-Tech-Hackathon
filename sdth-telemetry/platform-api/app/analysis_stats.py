"""Deterministic fleet-wide numeric findings for the AI-assisted analysis panel.

Everything here is a plain SQL aggregate or arithmetic over stored incidents --
no model involved. This module exists precisely because it sits next to the
model-drafted hypotheses in the UI: those are read as evidence-linked guesses,
this is read as fact, and the two must not blur together. See docs/ARCHITECTURE.md
("Deterministic detectors, model optional... numbers never come from a model").

Charts are rendered server-side with matplotlib and returned as embedded PNG
data URIs, matching the existing chart_export.py pattern (import-at-call-time,
degrade quietly if matplotlib is unavailable) so the console keeps working
air-gapped and with no frontend build step.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import statistics
from typing import Any

logger = logging.getLogger("analysis_stats")

# Matches the console's own palette (sdth-demo/demo.css): dark ground, signal
# orange as the primary accent, warn/danger for severity-coded bars.
_BG = "#0a1b28"
_INK = "#e9f1f3"
_MUTED = "#8ca4b2"
_LINE = "#233b48"
_SIGNAL = "#ff955f"
_WARN = "#efb96c"
_DANGER = "#e98b8b"
_AQUA = "#91c5c7"
_SEVERITY_COLOR = {"critical": _DANGER, "warning": _WARN, "info": _AQUA}


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _battery_percent(evidence_json: str) -> float | None:
    try:
        evidence = json.loads(evidence_json)
    except (json.JSONDecodeError, TypeError):
        return None
    sample = evidence.get("sample") or {}
    battery = sample.get("battery") or {}
    return _safe_float(battery.get("percent"))


def compute_fleet_stats(conn) -> dict[str, Any]:
    """Aggregate rule-detected incidents into operator-facing numbers.

    Scoped to detector='rule' throughout -- the same scoping every other
    read-only view in this API uses -- so an LLM-drafted report row never
    silently inflates a count that's supposed to be ground truth.
    """
    total_flights = conn.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
    flights_with_incidents = conn.execute(
        "SELECT COUNT(DISTINCT flight_id) FROM incidents WHERE detector='rule'"
    ).fetchone()[0]
    total_incidents = conn.execute(
        "SELECT COUNT(*) FROM incidents WHERE detector='rule'"
    ).fetchone()[0]

    by_type_rows = conn.execute(
        """
        SELECT incident_type, COUNT(*) AS n
        FROM incidents WHERE detector='rule'
        GROUP BY incident_type ORDER BY n DESC, incident_type
        """
    ).fetchall()
    by_type = [
        {
            "incident_type": row["incident_type"],
            "count": row["n"],
            "pct_of_incidents": round(100 * row["n"] / total_incidents, 1) if total_incidents else 0.0,
        }
        for row in by_type_rows
    ]

    by_severity_rows = conn.execute(
        """
        SELECT severity, COUNT(*) AS n
        FROM incidents WHERE detector='rule'
        GROUP BY severity
        """
    ).fetchall()
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    by_severity = sorted(
        ({"severity": row["severity"], "count": row["n"]} for row in by_severity_rows),
        key=lambda item: severity_order.get(item["severity"], 9),
    )

    battery_incident_rows = conn.execute(
        """
        SELECT evidence_json FROM incidents
        WHERE detector='rule' AND incident_type IN ('battery_low', 'battery_critical', 'battery_plunge')
        """
    ).fetchall()
    battery_values = sorted(
        v for v in (_battery_percent(row["evidence_json"]) for row in battery_incident_rows) if v is not None
    )
    battery_at_incident = (
        {
            "count": len(battery_values),
            "min_pct": round(min(battery_values), 1),
            "median_pct": round(statistics.median(battery_values), 1),
            "mean_pct": round(statistics.fmean(battery_values), 1),
            "max_pct": round(max(battery_values), 1),
        }
        if battery_values
        else None
    )

    top_recurring = conn.execute(
        """
        SELECT signature, incident_type, flight_count, incident_count
        FROM incident_patterns
        WHERE flight_count >= 2
        ORDER BY flight_count DESC, incident_count DESC
        LIMIT 5
        """
    ).fetchall()

    return {
        "total_flights": total_flights,
        "flights_with_incidents": flights_with_incidents,
        "incident_rate_pct": round(100 * flights_with_incidents / total_flights, 1) if total_flights else 0.0,
        "total_incidents": total_incidents,
        "by_type": by_type,
        "by_severity": by_severity,
        "battery_at_incident": battery_at_incident,
        # Raw, sorted values behind the summary above -- kept so the caller can
        # hand them straight to render_battery_chart() without a second query.
        # Not part of the public response shape; the endpoint pops it off.
        "_battery_values_pct": battery_values,
        "top_recurring": [dict(row) for row in top_recurring],
    }


def _configure_axes(fig, ax):
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)
    ax.tick_params(colors=_MUTED, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(_LINE)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.label.set_color(_MUTED)
    ax.yaxis.label.set_color(_MUTED)


def _fig_to_data_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")


def render_incident_type_chart(by_type: list[dict]) -> str | None:
    """Horizontal bar chart, most frequent incident type at the top."""
    if not by_type:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not installed; skipping incident-type chart")
        return None

    rows = list(reversed(by_type[:8]))  # top 8, reversed so #1 renders at the top
    labels = [row["incident_type"].replace("_", " ") for row in rows]
    counts = [row["count"] for row in rows]

    fig, ax = plt.subplots(figsize=(6.4, max(1.8, 0.42 * len(rows))))
    _configure_axes(fig, ax)
    bars = ax.barh(labels, counts, color=_SIGNAL, height=0.6)
    ax.set_xlabel("Incidents recorded")
    for bar, count in zip(bars, counts):
        ax.text(bar.get_width() + max(counts) * 0.02, bar.get_y() + bar.get_height() / 2,
                 str(count), va="center", color=_INK, fontsize=9)
    for label in ax.get_yticklabels():
        label.set_color(_INK)
    fig.tight_layout()
    uri = _fig_to_data_uri(fig)
    plt.close(fig)
    return uri


def render_battery_chart(battery_values_pct: list[float]) -> str | None:
    """Histogram of battery % readings at the moment a battery incident fired."""
    if not battery_values_pct:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not installed; skipping battery chart")
        return None

    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    _configure_axes(fig, ax)
    bins = min(10, max(3, len(battery_values_pct)))
    ax.hist(battery_values_pct, bins=bins, color=_DANGER, edgecolor=_BG)
    ax.set_xlabel("Battery % at incident")
    ax.set_ylabel("Incidents")
    median = statistics.median(battery_values_pct)
    ax.axvline(median, color=_INK, linestyle="--", linewidth=1)
    ax.text(median, ax.get_ylim()[1] * 0.95, f" median {median:.0f}%", color=_INK, fontsize=9, va="top")
    fig.tight_layout()
    uri = _fig_to_data_uri(fig)
    plt.close(fig)
    return uri


def render_severity_chart(by_severity: list[dict]) -> str | None:
    """Fallback chart when there isn't enough battery data: severity split."""
    if not by_severity:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not installed; skipping severity chart")
        return None

    labels = [row["severity"] for row in by_severity]
    counts = [row["count"] for row in by_severity]
    colors = [_SEVERITY_COLOR.get(sev, _AQUA) for sev in labels]

    fig, ax = plt.subplots(figsize=(4.2, 3.0))
    _configure_axes(fig, ax)
    bars = ax.bar(labels, counts, color=colors, width=0.55)
    ax.set_ylabel("Incidents")
    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), str(count),
                 ha="center", va="bottom", color=_INK, fontsize=9)
    for label in ax.get_xticklabels():
        label.set_color(_INK)
    fig.tight_layout()
    uri = _fig_to_data_uri(fig)
    plt.close(fig)
    return uri
