"""Build the WISL final report PDF from the checked-in report content.

This builder uses fixed body-page boundaries: cover, five body pages, references, appendix.
The abstract is read from the Markdown companion; the fixed body layout and
body prose live here. Keep body edits aligned with the Markdown companion.
"""
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, KeepTogether,
)
from reportlab.pdfbase.pdfmetrics import stringWidth

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "WISL_FinalReport_v1.pdf"
REPORT_MD = ROOT / "docs" / "submission" / "WISL_FinalReport_v1.md"

NAVY = colors.HexColor("#102A43")
TEAL = colors.HexColor("#007C78")
MINT = colors.HexColor("#E8F4F2")
INK = colors.HexColor("#172B4D")
MUTED = colors.HexColor("#52606D")
RED = colors.HexColor("#B42318")
LINE = colors.HexColor("#C5D2DC")


def clean(text: str) -> str:
    return (text.replace("-", "-").replace("-", "-").replace("-", "-")
                .replace("'", "'").replace("'", "'").replace("\u2011", "-"))


def report_abstract() -> str:
    """Use the editable Markdown abstract verbatim to prevent PDF/MD drift."""
    text = REPORT_MD.read_text(encoding="utf-8")
    match = re.search(r"^## Abstract\s*\n\n(.*?)(?=\n---\n)", text, flags=re.MULTILINE | re.DOTALL)
    if not match:
        raise ValueError("Abstract block not found in report Markdown")
    abstract = re.sub(r"\s+", " ", match.group(1)).strip()
    if len(abstract.split()) != 250:
        raise ValueError(f"Abstract must be exactly 250 whitespace-delimited words, got {len(abstract.split())}")
    return abstract


def on_cover(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, A4[1] - 0.28 * inch, A4[0], 0.28 * inch, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, 0, A4[0], 0.12 * inch, fill=1, stroke=0)
    canvas.restoreState()


def on_body(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, A4[1] - 0.43 * inch, A4[0] - doc.rightMargin, A4[1] - 0.43 * inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, A4[1] - 0.32 * inch, "WISL | Recorded Flight Evidence for Fleet Learning")
    page = canvas.getPageNumber() - 1  # excludes cover from body count
    canvas.drawRightString(A4[0] - doc.rightMargin, 0.30 * inch, f"Body p. {page} of 5" if 1 <= page <= 5 else f"p. {canvas.getPageNumber()}")
    canvas.setStrokeColor(LINE)
    canvas.line(doc.leftMargin, 0.43 * inch, A4[0] - doc.rightMargin, 0.43 * inch)
    canvas.restoreState()


def make_styles():
    styles = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle("CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=30, leading=34, textColor=NAVY, alignment=TA_CENTER, spaceAfter=10),
        "cover_sub": ParagraphStyle("CoverSub", parent=styles["Normal"], fontName="Helvetica", fontSize=12, leading=16, textColor=TEAL, alignment=TA_CENTER),
        "meta": ParagraphStyle("Meta", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK, alignment=TA_CENTER),
        "abstract_label": ParagraphStyle("AbstractLabel", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=TEAL, alignment=TA_LEFT),
        "abstract": ParagraphStyle("Abstract", parent=styles["Normal"], fontName="Times-Roman", fontSize=10.6, leading=13.2, textColor=INK, alignment=TA_LEFT),
        "section": ParagraphStyle("Section", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=NAVY, spaceAfter=3),
        "kicker": ParagraphStyle("Kicker", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.3, leading=10, textColor=TEAL, spaceAfter=14),
        "h2": ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12.2, leading=15, textColor=NAVY, spaceBefore=7, spaceAfter=4),
        "body": ParagraphStyle("Body", parent=styles["Normal"], fontName="Times-Roman", fontSize=11, leading=13.1, textColor=INK, spaceAfter=6),
        "code": ParagraphStyle("Code", parent=styles["Normal"], fontName="Courier", fontSize=9, leading=10.8, textColor=INK, leftIndent=5, rightIndent=5),
        "small": ParagraphStyle("Small", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=10.9, textColor=MUTED),
        "table": ParagraphStyle("Table", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=10.8, textColor=INK),
        "tablehead": ParagraphStyle("TableHead", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=10.8, textColor=colors.white),
        "ref": ParagraphStyle("Ref", parent=styles["Normal"], fontName="Times-Roman", fontSize=9.2, leading=11.3, textColor=INK, leftIndent=12, firstLineIndent=-12, spaceAfter=4),
    }


def P(text, style):
    return Paragraph(clean(text), style)


def band(label, styles, color=TEAL):
    t = Table([[P(label, styles["small"])]], colWidths=[6.95 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MINT),
        ("BOX", (0, 0), (-1, -1), 0.5, color),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def key_table(headers, rows, widths, styles):
    data = [[P(h, styles["tablehead"]) for h in headers]]
    data += [[P(c, styles["table"]) for c in row] for row in rows]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
    ]))
    return t


def body_page(story, title, kicker, blocks, styles):
    story.append(P(title, styles["section"]))
    story.append(P(kicker, styles["kicker"]))
    for kind, value in blocks:
        if kind == "p": story.append(P(value, styles["body"]))
        elif kind == "code": story.append(P(value, styles["code"])); story.append(Spacer(1, 6))
        elif kind == "h": story.append(P(value, styles["h2"]))
        elif kind == "band": story.append(band(value, styles)); story.append(Spacer(1, 8))
        elif kind == "table": story.append(value); story.append(Spacer(1, 8))
    story.append(PageBreak())


def build():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    styles = make_styles()
    doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=0.65*inch, rightMargin=0.65*inch, topMargin=0.62*inch, bottomMargin=0.58*inch)
    cover_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="cover")
    body_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates([PageTemplate(id="cover", frames=cover_frame, onPage=on_cover), PageTemplate(id="body", frames=body_frame, onPage=on_body)])
    s = []

    s += [Spacer(1, 1.0*inch), P("WISL", styles["cover_title"]), P("Recorded Flight Evidence for Fleet Learning", styles["cover_sub"]), Spacer(1, 0.45*inch)]
    meta = "<b>Team</b><br/>Inessa Wong - NUS Mathematics and Computer Science<br/>Sylvester Lim - NUS Computer Science<br/><br/><b>Date</b><br/>20 September 2026"
    s += [P(meta, styles["meta"]), Spacer(1, 0.5*inch), P("ABSTRACT", styles["abstract_label"])]
    abstract = report_abstract()
    s += [P(abstract, styles["abstract"]), NextPageTemplate("body"), PageBreak()]

    body_page(s, "1. Problem and contribution", "MIXED FLEETS, FRAGMENTED LOGS, ONE EVIDENCE PATH", [
        ("p", "Small unmanned aircraft are entering routine land operations. MINDEF has stated that UAVs are becoming part of the soldier's arsenal and that the Army will establish DARE to scale UAV and ground-vehicle use [1]. The V15 mini-UAV is described as a tactical ISR platform that can be launched from a confined space; 11 C4I Battalion operated V15s during Exercise Wallaby [2], [3]. Those facts set the operational setting in which post-flight review will occur."),
        ("p", "The practical difficulty is format fragmentation. A completed sortie can leave a PX4 ULog, an ArduPilot DataFlash or MAVLink log, a DJI FlightRecord export or another vendor dump, each readable only in its native analyser. PX4 Flight Review plots vehicle condition against a self-describing ULog [9]. Mission Planner downloads, graphs and replays DataFlash and MAVLink telemetry [10]. DJI FlightHub 2 records operations, alerts and exports, and can store data on premises, while remaining a DJI-only platform [11]. DroneLogbook imports mixed telemetry for replay, maintenance and compliance [12]. Each of these tools is effective inside its intended stack. None of them, on the evidence of their public descriptions, give a reviewer one hashed raw file, one canonical time series, one timestamped observation and a search across other stored flights that share the same signature."),
        ("p", "WISL was built to close that gap for a first user who already reviews completed small-UAS sorties: an Army instructor, maintainer or post-flight analyst. Work on the repository began on 11 July 2026. By September the system ingested raw logs, parsed them through a server-side registry, persisted a canonical L2 series, indexed deterministic observations, replayed recorded tracks, answered evidence queries and emitted reviewable bulletins when a signature recurred. That is the contribution: a working post-flight evidence path across the formats the parsers already accept."),
        ("band", "Contribution: hashed raw intake, canonical L2 series, deterministic observations, recorded-time replay, evidence query and reviewable recurrence bulletins."),
    ], styles)

    body_page(s, "2. What was built", "INTAKE, CANONICAL SERIES AND DETECTORS", [
        ("p", "A controller-side watcher observes a designated log directory. A file becomes eligible only after its size is stable across scans, which avoids capturing a log that is still being written. The watcher computes SHA-256, records status in a manifest and sends an authorised multipart upload with the digest. The platform checks extension and size, verifies the digest, de-duplicates stored bytes and records provenance before enqueueing parse. Parsing lives on the server so the watcher stays format-neutral. The registry currently accepts .bin, .csv, .hex, .hermes, .json, .ros, .stanag, .syslog, .tlog, .ulg, .ulog, .xlsx and .xml."),
        ("p", "Each parsed L1 payload is projected to an L2 record with flight_id, ISO-8601 timestamp_utc, WGS84 position, attitude in degrees, battery percent and volts, a sensors object and metadata. Local north/east metres are projected from a configured origin and marked local_ned. Missing numeric fields currently fall back to 0.0, which makes a true zero indistinguishable from an absent value and is the main schema limitation carried into later work."),
        ("p", "Deterministic detectors then run on L2 rather than on vendor opcodes. Indexed categories are battery low and critical, battery plunge, telemetry gap, attitude shock, GPS jump, last-known or frozen position, mission incomplete and operator-warning text. Working thresholds for the demonstration are 20% and 10% battery, 15 points in 60 s, a 25 m altitude step or 20 m/s vertical rate, 120 m/s implied air speed or 15 m/s on the ground, 40/70 degrees of attitude, and a 15 s gap. Incident rows store time, category, signature and a pointer back to the canonical records. Replay follows recorded time on a WGS84 path and overlays those observations."),
        ("table", key_table(["Stage", "Input", "Output"], [["Watcher", "size-stable controller log", "SHA-256, manifest, multipart upload"], ["Registry", "raw bytes in a supported extension", "L1 then L2 canonical series"], ["Detectors", "L2 time series", "timestamped observations and signatures"], ["Review", "stored flight and incidents", "replay, query answers, recurrence bulletin"]], [1.35*inch, 2.5*inch, 3.1*inch], styles)),
    ], styles)

    body_page(s, "2. What was built", "QUERIES, MODEL USE AND DESIGN CHOICES", [
        ("p", "POST /v1/demo/query returns stored evidence and matching signatures. When a signature appears on two or more flights, the patterns endpoint and a mitigation bulletin summarise the affected records for a human reviewer. The demonstration queries are fixed: what happened on this flight, where the evidence sits in the record, and which other stored flights share the same warning text. Hash de-duplication is global: a repeated SHA-256 returns the existing upload rather than a second raw object. Persistence uses SQLite tables for flights, ingest events, canonical records, raw uploads, incidents, patterns and normalisation provenance; local demonstration mode runs one in-process worker, while the queued deployment uses Redis."),
        ("p", "Two alternatives were considered and set aside. On-controller parsing would have required every ground station to carry vendor-specific logic; a server-side registry was chosen so one acceptance matrix can be maintained. Using a language model as the normaliser was rejected: numeric series and detector thresholds remain deterministic, and the local model is invoked only on an explicit analysis click, sees at most 100 flight summaries and 50 evidence items, and has its cited identifiers checked. One four-flight analysis call returned three hypotheses in 68.329 s with valid cited IDs; the text also invented context that was not in the supplied samples, so the model is treated as a drafting aid on top of the deterministic path. The public OpenAPI contract covers upload, status, records, path, incidents, patterns and bulletins; canonical JSONL is exportable."),
        ("p", "The working path is one completed log. An operator drops the file in the watched directory or uploads it. WISL then returns a canonical time series, timestamped observations, a replay of the recorded track, and a bulletin if the same signature already exists on other stored flights. A GPS-weak warning or a frozen track appears as an observation at a time on that path, ready to inspect. Replay uses cached or hosted map imagery."),
        ("band", "Numeric series and detectors run without the model. The model drafts; the record remains the evidence."),
    ], styles)

    body_page(s, "3. Testing and results", "PREDECLARED CORPUS AUDIT AND SOFTWARE MEASUREMENTS", [
        ("p", "Criteria were declared before the corpus audit: registry parse success; L2 schema projection; parseable, non-decreasing timestamps and finite numerics; scenario-card injected conditions reaching the matching detector type; and one representative multipart upload followed through persistence, replay path and incident query. Multiple format skins of one scenario card count as one simulated mission. Two distinct scenario cards are required before a signature is treated as recurrence evidence."),
        ("p", "The original inventory is hazards-only: 90 files from ten scenario cards and nine format skins. All 90 projected to non-null, finite, schema-valid L2 and completed the detector path within a 30-second bound, with no whole-path timeouts. Forty of 90 files met their scenario-card detector expectations. By format, DJI CSV and DJI Excel met 10/10; several text skins met 4/10; PX4 ULG and ArduPilot TLOG met 0/10 because those native artefacts did not retain the injected conditions. The original directory contains no normal control and only one exact GPS-weak mission."),
        ("p", "A second, physically gated set was therefore generated: eight independently seeded failure missions and one normal control, each in four signal-preserving exports (36 files). All 36 parsed, met L2 integrity checks, finished within the bound and met declared detector expectations. The four normal-control exports produced no incidents. The fixture gate checks battery-voltage consistency, ground-altitude coupling, route novelty, parser round-trip and normal-cadence velocity. An isolated upload of one GPS-warning CSV and one frozen-position JSON reached ready status in 1.223 s, persisted 225 canonical records and returned the expected operator_warning and last_known_position observations."),
        ("p", "The application suite passed 161 tests in 5.92 s; replay tests passed 15; UI tests passed 5; parser tests passed 28 in 0.73 s. During validation, DJI valid zero relative height had been treated as false and replaced with 180 ft MSL, which created artificial altitude-spike observations around takeoff and landing. The parser now retains valid zero, and a regression that fails on the old implementation is in the suite. On one Apple M4, 16 GiB machine, four flights, 867 canonical records and three incidents occupied 1,847,296 bytes of SQLite; five sequential exact-warning queries measured 9.27, 5.82, 9.47, 14.61 and 7.60 ms."),
        ("band", "Constructed logs hashed, parsed, indexed, replayed and queried. Normal control silent. Parser defect found and closed. Original 90-file expectation rate 40/90 because several native skins dropped the injected event."),
    ], styles)

    body_page(s, "4. Use and next steps", "POST-SORTIE REVIEW AND A SIX-MONTH EVALUATION", [
        ("p", "In the intended thread, a designated operator places a completed controller log in the watched directory after a small-UAS training sortie. The watcher hashes and transfers it. A reviewer opens the stored flight, inspects time-linked observations, scrubs the recorded track and compares any recurring signature before issuing a bulletin for human approval. RSAF UAV Command's published governance and engineering role [6], and HTX work to unite Home Team drone systems [4], [5], are adjacent settings in which the same post-flight path could be tried. RSN unmanned surface-vessel telemetry is a later transfer, not present scope [8]."),
        ("p", "The main unknowns are access to representative authorised logs, classification and retention rules, parser drift on real firmware, and whether reviewers actually retrieve evidence faster than they do today. Over the next six months the priority is a gated evaluation. Month 1 is a discovery session and a data-flow review, with permission to use de-identified exports or to remain on synthetic material. Months 2-3 produce a format acceptance matrix and a provenance report of retained, derived and missing fields, plus tests for corruption, duplicate upload and model-offline behaviour. Months 4-5 run a shadow review on a small authorised set against the current manual workflow, measuring completion time, retrievability and false-review burden. Month 6 decides on a limited sandbox from those measurements."),
        ("table", key_table(["Period", "Work", "Decision"], [["Month 1", "discovery and data-flow review", "de-identified exports or remain synthetic"], ["Months 2-3", "acceptance matrix, provenance report, fault tests", "retained vs missing fields explicit"], ["Months 4-5", "shadow review vs current manual workflow", "time, retrievability, false-review burden"], ["Month 6", "sandbox continuation", "security, fidelity, reviewer value"]], [1.2*inch, 3.15*inch, 2.6*inch], styles)),
        ("p", "The immediate request is an introduction to an Army small-UAS training or maintenance counterpart, an approved test-data route and a named reviewer workflow."),
    ], styles)

    refs = [
        "[1] MINDEF, 'Speech by Minister for Defence, Dr Ng Eng Hen, at The Committee of Supply 2025 on 3 March 2025,' 4 Mar. 2025. https://www.mindef.gov.sg/news-and-events/latest-releases/04mar25_speech3/",
        "[2] MINDEF, 'Fact Sheet: Latest Suite of Headquarters Sense and Strike Platforms,' 30 Jun. 2021. https://www.mindef.gov.sg/news-and-events/latest-releases/30jun21_fs2/",
        "[3] MINDEF, 'Fact Sheet: Exercise Wallaby 2023,' 9 Oct. 2023. https://www.mindef.gov.sg/news-and-events/latest-releases/09oct23_fs/",
        "[4] HTX, 'Robotics, Automation and Unmanned Systems,' updated 10 Sep. 2026. https://www.htx.gov.sg/who-we-are/what-we-do/our-expertise/robots-automation-and-unmanned-systems",
        "[5] HTX, 'Unity in flight: Transforming drone control through MDOS,' 2024. https://www.htx.gov.sg/whats-happening/all-news---events/all-news/2024/featured-news--unity-in-flight--transforming-drone-control-through-mdos",
        "[6] RSAF, 'Unmanned Aerial Vehicle Command,' updated 19 Jan. 2026. https://www.rsaf.gov.sg/rsaf-forces/commands/unmanned-aerial-vehicle-command/",
        "[7] MINDEF, 'Fact Sheet: The Digital and Intelligence Service,' 28 Oct. 2022. https://www.mindef.gov.sg/news-and-events/latest-releases/28oct22_fs/",
        "[8] MINDEF, 'The Republic of Singapore Navy's Unmanned Surface Vessels Progressively Operationalised to Enhance Maritime Security,' 4 Feb. 2025. https://www.mindef.gov.sg/news-and-events/latest-releases/04feb25_fs/",
        "[9] PX4 Autopilot, 'Log Analysis using Flight Review' and 'ULog File Format.' https://docs.px4.io/v1.15/en/log/flight_review ; https://docs.px4.io/main/en/dev_log/ulog_file_format",
        "[10] ArduPilot, 'Downloading and Analyzing Data Logs in Mission Planner' and 'Telemetry Logs.' https://ardupilot.org/planner/docs/common-downloading-and-analyzing-data-logs-in-mission-planner.html ; https://ardupilot.org/planner/docs/mission-planner-telemetry-logs.html",
        "[11] DJI Enterprise, 'DJI FlightHub 2'; 'DJI FlightHub 2 On-Premises - FAQ'; DJI Developer, 'Cloud API: Log Export,' 19 Mar. 2025. https://enterprise.dji.com/flighthub-2 ; https://enterprise.dji.com/fh2-on-premises/faq ; https://developer.dji.com/doc/cloud-api-tutorial/en/debug/log-export.html",
        "[12] DroneLogbook, 'Features - DroneLogbook - Simplifying Drone Operations.' https://www.dronelogbook.com/hp/1/features.html",
    ]
    s += [P("References", styles["section"]), P("Accessed September 2026.", styles["kicker"])]
    s += [P(ref, styles["ref"]) for ref in refs]
    s += [PageBreak(), P("Appendix A. Validation artefacts", styles["section"]), P("EXCLUDED FROM THE FIVE-PAGE BODY", styles["kicker"])]
    s += [P("Frozen artefacts: output/evidence/corpus-validation-v2/original90/corpus-validation.json and output/evidence/corpus-validation-v2/failure-fixtures-audit/corpus-validation.json. They record the original hazards-only corpus and the gated failure-plus-control set. The PDF is produced by scripts/build_wisl_final_report.py with cover, five body pages, references and this appendix.", styles["body"])]
    doc.build(s)


if __name__ == "__main__":
    build()
