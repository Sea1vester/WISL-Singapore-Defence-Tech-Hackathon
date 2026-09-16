"""
Render a pre-emptive mission-planning report (see app/preflight_report.py) to PDF.

reportlab is only imported at call time, matching the chart_export.py pattern,
so this module stays importable even before the dependency is installed.

Typography: headings use League Spartan (OFL-licensed, bundled under
app/assets/fonts/ from Google Fonts' official repo). Body text uses Nunito
Sans, also OFL-licensed and bundled the same way -- it stands in for the
brand's requested 'Garet' typeface, which is a paid commercial font with no
legitimate free-to-embed source, so it is not included here. If font
registration fails for any reason, everything falls back to reportlab's
built-in Helvetica family rather than breaking PDF generation.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("pdf_report")

_SEVERITY_LABEL = {"critical": "CRITICAL", "warning": "WARNING", "info": "INFO"}

_FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_FONTS_REGISTERED = False
_HEADING_FONT = "Helvetica-Bold"
_HEADING_FONT_SEMIBOLD = "Helvetica-Bold"
_BODY_FONT = "Helvetica"
_BODY_FONT_BOLD = "Helvetica-Bold"


def _register_fonts() -> None:
    """Register League Spartan (headings) and Nunito Sans (body) once per process.
    Falls back to Helvetica silently if the bundled font files are missing or
    fail to parse -- a font problem should never stop a report from generating.
    """
    global _FONTS_REGISTERED, _HEADING_FONT, _HEADING_FONT_SEMIBOLD, _BODY_FONT, _BODY_FONT_BOLD
    if _FONTS_REGISTERED:
        return
    _FONTS_REGISTERED = True
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        pdfmetrics.registerFont(TTFont("LeagueSpartan", str(_FONTS_DIR / "LeagueSpartan-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("LeagueSpartan-Bold", str(_FONTS_DIR / "LeagueSpartan-Bold.ttf")))
        pdfmetrics.registerFont(TTFont("LeagueSpartan-SemiBold", str(_FONTS_DIR / "LeagueSpartan-SemiBold.ttf")))
        pdfmetrics.registerFont(TTFont("NunitoSans", str(_FONTS_DIR / "NunitoSans-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("NunitoSans-Bold", str(_FONTS_DIR / "NunitoSans-Bold.ttf")))
        pdfmetrics.registerFontFamily("LeagueSpartan", normal="LeagueSpartan", bold="LeagueSpartan-Bold")
        pdfmetrics.registerFontFamily("NunitoSans", normal="NunitoSans", bold="NunitoSans-Bold")
        _HEADING_FONT = "LeagueSpartan-Bold"
        _HEADING_FONT_SEMIBOLD = "LeagueSpartan-SemiBold"
        _BODY_FONT = "NunitoSans"
        _BODY_FONT_BOLD = "NunitoSans-Bold"
    except Exception:
        logger.warning("Could not register League Spartan / Nunito Sans; falling back to Helvetica.", exc_info=True)


def _thumbnail_candidates(camera: dict[str, Any]) -> list[dict[str, Any]]:
    samples = camera.get("quality_samples") or []
    flagged = [s for s in samples if s.get("flags")]
    picks = flagged[:2] if flagged else samples[:1]
    return picks


# ---- Shared visual language ------------------------------------------------
_INK = "#20242C"          # near-black body/heading ink -- softer than pure black
_MUTED = "#5B6472"        # secondary text (subtitles, table labels)
_FAINT = "#818B99"        # disclosures / fine print
_HEADER_BG = "#2B3242"    # table header band
_ROW_ALT = "#F5F6F8"      # alternating table row tint
_RULE = "#E2E5EA"         # hairline dividers
_FRAME_BG = "#F1F4FB"     # orienting-note background
_FRAME_BORDER = "#D8E0F0"


def _build_styles() -> dict[str, Any]:
    _register_fonts()
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    styles = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "WislH1", parent=styles["Heading1"], fontName=_HEADING_FONT, fontSize=21, leading=25,
            textColor=colors.HexColor(_INK), spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "WislH2", parent=styles["Heading2"], fontName=_HEADING_FONT_SEMIBOLD, fontSize=14, leading=18,
            textColor=colors.HexColor(_INK), spaceBefore=20, spaceAfter=10,
        ),
        "sub": ParagraphStyle(
            "WislSub", parent=styles["Normal"], fontName=_BODY_FONT, fontSize=10, leading=14,
            textColor=colors.HexColor(_MUTED),
        ),
        "intro": ParagraphStyle(
            "WislIntro", parent=styles["BodyText"], fontName=_BODY_FONT, fontSize=10, leading=15,
            textColor=colors.HexColor(_INK),
        ),
        "body": ParagraphStyle(
            "WislBody", parent=styles["BodyText"], fontName=_BODY_FONT, fontSize=10.5, leading=16,
            textColor=colors.HexColor(_INK), spaceAfter=8,
        ),
        "disclosure": ParagraphStyle(
            "WislDisclosure", parent=styles["BodyText"], fontName=_BODY_FONT, fontSize=8.75, leading=13,
            textColor=colors.HexColor(_FAINT), spaceBefore=6, spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "WislBullet", parent=styles["BodyText"], fontName=_BODY_FONT, fontSize=10.5, leading=15.5,
            textColor=colors.HexColor(_INK), leftIndent=14, bulletIndent=0, spaceAfter=7,
        ),
        "cell": ParagraphStyle(
            "WislCell", parent=styles["BodyText"], fontName=_BODY_FONT, fontSize=8.5, leading=12,
            textColor=colors.HexColor(_INK), wordWrap="CJK",
        ),
        "cell_header": ParagraphStyle(
            "WislCellHeader", parent=styles["BodyText"], fontName=_BODY_FONT_BOLD, fontSize=8.5, leading=12,
            textColor=colors.white,
        ),
    }


def _rule(styles: dict[str, Any]):
    """A soft hairline divider, used ahead of each major section heading."""
    from reportlab.lib import colors
    from reportlab.platypus import HRFlowable

    return HRFlowable(width="100%", thickness=0.6, color=colors.HexColor(_RULE), spaceBefore=2, spaceAfter=0)


def _section_heading(story: list[Any], text: str, styles: dict[str, Any]) -> None:
    story.append(_rule(styles))
    story.append(Para(text, styles["h2"]))


def Para(text: str, style: Any):  # small alias so the module reads less repetitively below
    from reportlab.platypus import Paragraph

    return Paragraph(text, style)


def _orienting_note(story: list[Any], text: str, styles: dict[str, Any]) -> None:
    """A calm, plain-language framing box near the top of a report, so a
    reader unfamiliar with drone telemetry has context before the technical
    sections and jargon (detector names, triage labels) begin."""
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer, Table, TableStyle

    note_style = styles["intro"]
    table = Table([[Para(text, note_style)]], colWidths=[170 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_FRAME_BG)),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor(_FRAME_BORDER)),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(Spacer(1, 6))
    story.append(table)
    story.append(Spacer(1, 10))


def _styled_table(rows: list[list[Any]], col_widths: list[float], *, font_size: float = 9.5) -> Any:
    """A table with generous cell padding and the shared header/row palette --
    used everywhere a data table appears in these reports, so spacing stays
    consistent instead of being tuned per-callsite.

    Plain-string cells are wrapped in a Paragraph before reaching the Table.
    ReportLab does NOT wrap raw strings placed directly in a cell -- an
    unbroken token like an ISO timestamp ("2026-03-18T22:33:00.000000Z") just
    overflows into the next column instead of wrapping onto a second line.
    Paragraph wrapping (with wordWrap="CJK" so it can break inside a long
    token with no spaces, not just between words) fixes that. A cell that's
    already a flowable (e.g. a caller-built Paragraph) is passed through as-is.
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    header_style = ParagraphStyle(
        "WislTableHeader", fontName=_BODY_FONT_BOLD, fontSize=font_size, leading=font_size + 3.5,
        textColor=colors.white, wordWrap="CJK",
    )
    cell_style = ParagraphStyle(
        "WislTableCell", fontName=_BODY_FONT, fontSize=font_size, leading=font_size + 3.5,
        textColor=colors.HexColor(_INK), wordWrap="CJK",
    )

    def _wrap(value: Any, style: Any) -> Any:
        return Paragraph(str(value), style) if isinstance(value, str) else value

    wrapped_rows = [[_wrap(cell, header_style) for cell in rows[0]]] + [
        [_wrap(cell, cell_style) for cell in row] for row in rows[1:]
    ]

    t = Table(wrapped_rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_HEADER_BG)),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(_RULE)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_ROW_ALT)]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _append_preemptive_sections(story: list[Any], report: dict[str, Any], styles: dict[str, Any]) -> None:
    """Maneuver/link/camera findings and recommendations, shared by the
    pre-emptive-only PDF and the comprehensive PDF."""
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage, Spacer

    from app.visuals import resolve_visual_path

    h2, body, disclosure_style, bullet = styles["h2"], styles["body"], styles["disclosure"], styles["bullet"]

    story.append(Para(
        f"{report['sample_count']} telemetry sample(s) analyzed ({report['sample_origin']}); "
        f"{report['incident_count']} incident(s) detected.",
        body,
    ))
    if report["incident_summary"]:
        rows = [["Incident type", "Count"]] + [
            [k, str(v)] for k, v in sorted(report["incident_summary"].items())
        ]
        story.append(Spacer(1, 4))
        story.append(_styled_table(rows, [100 * mm, 30 * mm]))
        story.append(Spacer(1, 10))

    # ---- Maneuver / failure findings -------------------------------------
    _section_heading(story, "Maneuver &amp; Failure Findings", styles)
    findings = report.get("maneuver_findings") or []
    if findings:
        for f in findings:
            label = _SEVERITY_LABEL.get(f["severity"], f["severity"].upper())
            story.append(Para(f"<b>[{label}] {f['incident_type']}</b> &mdash; {f['narrative']}", body))
    else:
        story.append(Para("No maneuver or physics-threshold incidents were flagged on this flight.", body))

    # ---- Link reliability ---------------------------------------------
    _section_heading(story, "Controller-Link Reliability", styles)
    link = report["link_reliability"]
    story.append(Para(link["narrative"], body))
    if link.get("signal_stats"):
        ss = link["signal_stats"]
        story.append(Para(
            f"Signal strength: min {ss['min']:.0f}%, avg {ss['avg']:.0f}%, max {ss['max']:.0f}% "
            f"({ss['samples']} readings).",
            body,
        ))
    if link.get("keyword_warnings"):
        rows = [["Timestamp", "Warning text"]] + [
            [w["timestamp_utc"], w["text"][:80]] for w in link["keyword_warnings"][:10]
        ]
        story.append(Spacer(1, 2))
        story.append(_styled_table(rows, [45 * mm, 95 * mm], font_size=8.5))
        story.append(Spacer(1, 6))
    story.append(Para(link["disclosure"], disclosure_style))

    # ---- Camera / vision reliability ------------------------------------
    _section_heading(story, "Camera &amp; Vision Reliability", styles)
    camera = report["camera_reliability"]
    story.append(Para(camera["narrative"], body))
    if camera.get("lag_events"):
        rows = [["From", "To", "Gap (s)"]] + [
            [e["from"], e["to"], f"{e['gap_s']:.1f}"] for e in camera["lag_events"][:10]
        ]
        story.append(Spacer(1, 2))
        story.append(_styled_table(rows, [55 * mm, 55 * mm, 25 * mm], font_size=8.5))
        story.append(Spacer(1, 6))

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
            story.append(Spacer(1, 6))
            story.append(RLImage(str(path), width=target_w, height=target_h))
            flags = ", ".join(pick.get("flags") or []) or "no flags"
            story.append(Para(
                f"Frame {pick['recorded_at']} &mdash; brightness {pick['brightness_mean']:.0f}, "
                f"edge variance {pick['edge_variance']:.0f} ({flags})",
                disclosure_style,
            ))
        except Exception:
            logger.warning("Skipping unreadable thumbnail for visual %s", pick["visual_id"])
            continue

    story.append(Para(camera["disclosure"], disclosure_style))

    # ---- Recommendations --------------------------------------------------
    _section_heading(story, "Pre-emptive Recommendations for Next Mission", styles)
    for rec in report["recommendations"]:
        story.append(Para(f"&bull; {rec}", bullet))

    story.append(Spacer(1, 14))
    story.append(Para(report["limitations"], disclosure_style))


def _append_incident_report_section(story: list[Any], incident_report: dict[str, Any], styles: dict[str, Any]) -> None:
    """Evidence-backed incident summary (see app/analytics.py build_deterministic_report)."""
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer

    h2, body, disclosure_style, bullet = styles["h2"], styles["body"], styles["disclosure"], styles["bullet"]

    _section_heading(story, "Evidence-Backed Incident Summary", styles)
    enrichment = incident_report.get("model_enrichment", "degraded")
    story.append(Para(f"Local model enrichment: <b>{enrichment}</b>.", disclosure_style))
    story.append(Spacer(1, 4))
    story.append(Para(incident_report.get("mission_summary", ""), body))

    timeline = incident_report.get("timeline") or []
    if timeline:
        rows = [["Timestamp", "Event"]] + [
            [item.get("timestamp_utc", ""), (item.get("event") or "")[:110]] for item in timeline
        ]
        story.append(Spacer(1, 4))
        story.append(_styled_table(rows, [48 * mm, 102 * mm], font_size=8.5))
        story.append(Spacer(1, 10))

    factors = incident_report.get("likely_contributing_factors") or []
    if factors:
        story.append(Para("Likely contributing factors:", body))
        for factor in factors:
            story.append(Para(f"&bull; {factor}", bullet))
        story.append(Spacer(1, 4))

    follow_up = incident_report.get("recommended_follow_up") or []
    if follow_up:
        from reportlab.platypus import KeepTogether

        block: list[Any] = [Para("Recommended follow-up:", body)]
        for step in follow_up:
            block.append(Para(f"&bull; {step}", bullet))
        block.append(Spacer(1, 6))
        block.append(Para(incident_report.get("confidence_and_limitations", ""), disclosure_style))
        story.append(KeepTogether(block))
    else:
        story.append(Spacer(1, 6))
        story.append(Para(incident_report.get("confidence_and_limitations", ""), disclosure_style))


def _append_recurring_patterns_section(story: list[Any], patterns: list[dict[str, Any]], styles: dict[str, Any]) -> None:
    """Fleet-wide recurring-pattern signatures this flight shares with other flights."""
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer

    h2, body, disclosure_style, cell_style = styles["h2"], styles["body"], styles["disclosure"], styles["cell"]

    _section_heading(story, "Fleet-Wide Recurring Pattern Matches", styles)
    if not patterns:
        story.append(Para(
            "This flight's incident signature(s) do not currently recur on two or more recorded flights.",
            body,
        ))
        return

    for pattern in patterns:
        story.append(Para(
            f"<b>{pattern.get('incident_type')}</b> &mdash; {pattern.get('flight_count')} flights, "
            f"{pattern.get('incident_count')} incidents, max severity {pattern.get('max_severity')}",
            body,
        ))
        if pattern.get("summary"):
            story.append(Para(pattern["summary"], body))
        affected = pattern.get("affected_flights") or []
        if affected:
            rows = [["Flight", "Source log", "Airframe"]] + [
                [
                    Para(f.get("flight_id", ""), cell_style),
                    Para(f.get("source_file") or "", cell_style),
                    Para(
                        " ".join(x for x in [f.get("drone_model"), f.get("aircraft_serial") and f"S/N {f['aircraft_serial']}"] if x),
                        cell_style,
                    ),
                ]
                for f in affected
            ]
            story.append(Spacer(1, 4))
            story.append(_styled_table(rows, [42 * mm, 70 * mm, 38 * mm], font_size=8.5))
        story.append(Spacer(1, 12))

    story.append(Para(
        "A shared signature is a reason to compare evidence across flights, not proof of a shared cause.",
        disclosure_style,
    ))


def render_preemptive_report_pdf(report: dict[str, Any], *, out_path: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Spacer

    out_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _build_styles()

    story: list[Any] = []
    story.append(Para("Pre-emptive Mission Planning Report", styles["h1"]))
    story.append(Para(
        f"Flight {report['flight_id']} &middot; {report['brand_name']} &middot; "
        f"generated {report['generated_at']}",
        styles["sub"],
    ))
    _orienting_note(
        story,
        "How to read this: this report is generated automatically from recorded flight data and "
        "threshold-based checks -- it is not a certified investigation or a diagnosis. It is meant to "
        "help a reviewer decide what is worth a closer look before the next flight.",
        styles,
    )
    story.append(Spacer(1, 4))
    _append_preemptive_sections(story, report, styles)

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
        title=f"Pre-emptive report - {report['flight_id']}",
    )
    doc.build(story)
    return out_path


def render_comprehensive_report_pdf(report: dict[str, Any], *, out_path: Path) -> Path:
    """Render the combined report from app.preflight_report.build_comprehensive_report:
    evidence-backed incident summary + pre-emptive planning findings + recurring
    fleet-wide pattern matches, in one downloadable PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer

    out_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _build_styles()

    story: list[Any] = []
    story.append(Para("Comprehensive Mission Report", styles["h1"]))
    story.append(Para(
        f"Flight {report['flight_id']} &middot; {report['brand_name']} &middot; "
        f"generated {report['generated_at']}",
        styles["sub"],
    ))
    _orienting_note(
        story,
        "How to read this: this report combines an automated incident summary, pre-emptive planning "
        "findings, and any fleet-wide recurring patterns for this flight -- all generated from recorded "
        "data and threshold-based checks, not a certified investigation. Technical terms (like "
        "detector names and triage labels) are explained where they first appear; each section also "
        "states its own confidence and limits.",
        styles,
    )
    story.append(Spacer(1, 4))

    _append_incident_report_section(story, report["incident_report"], styles)
    story.append(PageBreak())
    _append_preemptive_sections(story, report["preemptive_findings"], styles)
    story.append(PageBreak())
    _append_recurring_patterns_section(story, report["recurring_pattern_matches"], styles)

    story.append(Spacer(1, 14))
    story.append(Para(report["limitations"], styles["disclosure"]))

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
        title=f"Comprehensive report - {report['flight_id']}",
    )
    doc.build(story)
    return out_path
