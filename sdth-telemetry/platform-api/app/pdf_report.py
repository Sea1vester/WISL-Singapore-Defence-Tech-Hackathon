"""
Render a pre-emptive mission-planning report (see app/preflight_report.py) to PDF.

reportlab is only imported at call time, matching the chart_export.py pattern,
so this module stays importable even before the dependency is installed.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("pdf_report")

_SEVERITY_LABEL = {"critical": "CRITICAL", "warning": "WARNING", "info": "INFO"}


def _thumbnail_candidates(camera: dict[str, Any]) -> list[dict[str, Any]]:
    samples = camera.get("quality_samples") or []
    flagged = [s for s in samples if s.get("flags")]
    picks = flagged[:2] if flagged else samples[:1]
    return picks


def render_preemptive_report_pdf(report: dict[str, Any], *, out_path: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image as RLImage,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    from app.visuals import resolve_visual_path

    out_path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("WislH1", parent=styles["Heading1"], fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle("WislH2", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6)
    sub = ParagraphStyle("WislSub", parent=styles["Normal"], textColor=colors.HexColor("#555555"), fontSize=10)
    body = styles["BodyText"]
    disclosure_style = ParagraphStyle(
        "WislDisclosure", parent=styles["BodyText"], fontSize=8.5,
        textColor=colors.HexColor("#666666"), spaceBefore=4, spaceAfter=2,
    )
    bullet = ParagraphStyle("WislBullet", parent=styles["BodyText"], leftIndent=12, bulletIndent=0, spaceAfter=6)

    story: list[Any] = []
    story.append(Paragraph("Pre-emptive Mission Planning Report", h1))
    story.append(Paragraph(
        f"Flight {report['flight_id']} &middot; {report['brand_name']} &middot; "
        f"generated {report['generated_at']}",
        sub,
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        f"{report['sample_count']} telemetry sample(s) analyzed ({report['sample_origin']}); "
        f"{report['incident_count']} incident(s) detected.",
        body,
    ))
    if report["incident_summary"]:
        rows = [["Incident type", "Count"]] + [
            [k, str(v)] for k, v in sorted(report["incident_summary"].items())
        ]
        t = Table(rows, colWidths=[100 * mm, 30 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2A2F3A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F4F4")]),
        ]))
        story.append(Spacer(1, 6))
        story.append(t)

    # ---- Maneuver / failure findings -------------------------------------
    story.append(Paragraph("Maneuver &amp; Failure Findings", h2))
    findings = report.get("maneuver_findings") or []
    if findings:
        for f in findings:
            label = _SEVERITY_LABEL.get(f["severity"], f["severity"].upper())
            story.append(Paragraph(f"<b>[{label}] {f['incident_type']}</b> &mdash; {f['narrative']}", body))
            story.append(Spacer(1, 4))
    else:
        story.append(Paragraph("No maneuver or physics-threshold incidents were flagged on this flight.", body))

    # ---- Link reliability ---------------------------------------------
    story.append(Paragraph("Controller-Link Reliability", h2))
    link = report["link_reliability"]
    story.append(Paragraph(link["narrative"], body))
    if link.get("signal_stats"):
        ss = link["signal_stats"]
        story.append(Paragraph(
            f"Signal strength: min {ss['min']:.0f}%, avg {ss['avg']:.0f}%, max {ss['max']:.0f}% "
            f"({ss['samples']} readings).",
            body,
        ))
    if link.get("keyword_warnings"):
        rows = [["Timestamp", "Warning text"]] + [
            [w["timestamp_utc"], w["text"][:80]] for w in link["keyword_warnings"][:10]
        ]
        t = Table(rows, colWidths=[45 * mm, 95 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2A2F3A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ]))
        story.append(Spacer(1, 4))
        story.append(t)
    story.append(Paragraph(link["disclosure"], disclosure_style))

    # ---- Camera / vision reliability ------------------------------------
    story.append(Paragraph("Camera &amp; Vision Reliability", h2))
    camera = report["camera_reliability"]
    story.append(Paragraph(camera["narrative"], body))
    if camera.get("lag_events"):
        rows = [["From", "To", "Gap (s)"]] + [
            [e["from"], e["to"], f"{e['gap_s']:.1f}"] for e in camera["lag_events"][:10]
        ]
        t = Table(rows, colWidths=[55 * mm, 55 * mm, 25 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2A2F3A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ]))
        story.append(Spacer(1, 4))
        story.append(t)

    for pick in _thumbnail_candidates(camera):
        path = resolve_visual_path(pick["visual_id"])
        if path is None or not path.exists():
            continue
        try:
            from PIL import Image as PILImage

            with PILImage.open(path) as im:
                w, h = im.size
            target_w = 70 * mm
            target_h = target_w * (h / w) if w else 40 * mm
            story.append(Spacer(1, 4))
            story.append(RLImage(str(path), width=target_w, height=target_h))
            flags = ", ".join(pick.get("flags") or []) or "no flags"
            story.append(Paragraph(
                f"Frame {pick['recorded_at']} &mdash; brightness {pick['brightness_mean']:.0f}, "
                f"edge variance {pick['edge_variance']:.0f} ({flags})",
                disclosure_style,
            ))
        except Exception:
            logger.warning("Skipping unreadable thumbnail for visual %s", pick["visual_id"])
            continue

    story.append(Paragraph(camera["disclosure"], disclosure_style))

    # ---- Recommendations --------------------------------------------------
    story.append(Paragraph("Pre-emptive Recommendations for Next Mission", h2))
    for rec in report["recommendations"]:
        story.append(Paragraph(f"&bull; {rec}", bullet))

    story.append(Spacer(1, 12))
    story.append(Paragraph(report["limitations"], disclosure_style))

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Pre-emptive report - {report['flight_id']}",
    )
    doc.build(story)
    return out_path
