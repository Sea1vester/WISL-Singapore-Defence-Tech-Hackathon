"""Build the WISL final report PDF from the checked-in report content.

This builder deliberately uses fixed body-page boundaries so the DVL ten-page
body budget is auditable: cover, ten body pages, references, appendix.
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
    canvas.drawRightString(A4[0] - doc.rightMargin, 0.30 * inch, f"Body p. {page} of 10" if 1 <= page <= 10 else f"p. {canvas.getPageNumber()}")
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
    meta = "<b>Team</b><br/>Inessa Wong - NUS Mathematics and Computer Science<br/>Sylvester Lim - NUS Computer Science<br/>Isaac Sua - NUS Computer Engineering; DSO research intern<br/><br/><b>Mentor/advisor</b><br/>Unknown at time of submission draft<br/><br/><b>Date</b><br/>13 September 2026"
    s += [P(meta, styles["meta"]), Spacer(1, 0.5*inch), P("ABSTRACT", styles["abstract_label"])]
    abstract = report_abstract()
    s += [P(abstract, styles["abstract"]), Spacer(1, 0.35*inch), band("Scope note: official sources establish context only. No operator outreach, endorsement, procurement intent or field-data access is claimed.", styles, RED), NextPageTemplate("body"), PageBreak()]

    body_page(s, "1. Introduction and problem statement", "PROPOSED USER AND BOUNDED CONTRIBUTION", [
        ("p", "The proposed first user is an Army small-UAS instructor, maintainer or post-flight analyst. MINDEF states that UAVs are becoming part of the soldier's arsenal and that the Army will establish DARE to scale UAV and ground-vehicle operations [1]. The V15 is publicly described as an Army tactical ISR platform, deployable from a confined space; 11 C4I Battalion operated V15s during Exercise Wallaby training [2], [3]. These facts establish context, not demand validation or access."),
        ("p", "After a recorded warning, telemetry gap, anomalous track or maintenance concern, a reviewer can face several raw formats and a manual, flight-by-flight investigation. WISL proposes a post-flight evidence path: preserve raw input, normalise it, link deterministic observations to time and replay, then make comparable stored signatures reviewable. It does not diagnose cause from one warning and does not command an aircraft."),
        ("h", "What changed in the repository"),
        ("p", "Repository history begins on 11 July 2026; there is no repository evidence of a 21 June baseline, so none is asserted. By September, it contains raw-log upload, parser registry, canonical persistence, deterministic incident indexing, Cesium replay, evidence query, mitigation bulletins, privacy/retention primitives and an optional local-model analysis route."),
        ("h", "Competitive landscape"),
        ("p", "PX4 Flight Review plots vehicle condition and ULog is self-describing [9]. ArduPilot Mission Planner downloads, graphs and replays DataFlash/MAVLink telemetry [10]. DJI FlightHub 2 provides operations management, records, alerts and export; its on-premises option can use local storage, while its platform does not connect non-DJI aircraft [11]. DroneLogbook imports diverse telemetry and provides replay, maintenance, inspection and compliance functions [12]. WISL must therefore prove a narrow post-flight evidence workflow, not a new category."),
        ("band", "Positioning: raw provenance + canonical evidence + deterministic observations + time-linked replay + cautious, reviewable pattern analysis."),
    ], styles)

    body_page(s, "2. Technical approach", "RAW-LOG INTAKE AND CANONICAL BOUNDARY", [
        ("h", "Controller-side reliability"),
        ("p", "The edge uploader watches a designated controller log directory. A file is eligible only after its size is stable across scans. It computes SHA-256, records status in a manifest and sends an authorised multipart upload with the digest. This reduces premature transfer of an in-progress log and makes retry/duplicate status inspectable."),
        ("h", "Server-side intake"),
        ("p", "The platform checks extension and size, verifies the declared digest, de-duplicates stored bytes and records provenance before enqueueing server-side parsing. Keeping format parsing server-side keeps the controller extension format-neutral. Supported extensions currently include bin, csv, hex, hermes, json, ros, stanag, syslog, tlog, ulg, ulog, xlsx and xml."),
        ("h", "Explicit support boundary"),
        ("p", "A supported extension means an implementation path exists. It does not mean every vendor export, encrypted artifact, firmware release or malformed input will parse. DJI detail-log use can require authorised export/decryption [11]. The first trial must maintain an acceptance matrix by real export type and report retained, derived and missing fields."),
        ("table", key_table(["Stage", "Evidence retained", "Failure behaviour"], [["Controller watcher", "relative path, size, SHA-256, manifest status", "unstable file skipped; failed delivery remains pending"], ["Raw upload", "filename, digest, size, upload record", "unsupported, oversized or digest-mismatched input rejected"], ["Parser/canonical", "parser identity and L2 records", "processing status/error visible; source retained for review"]], [1.45*inch, 3.05*inch, 2.45*inch], styles)),
    ], styles)

    body_page(s, "3. Technical approach", "L2 EVIDENCE, DETECTORS AND REPLAY", [
        ("p", "Each parsed L1 payload is projected to an L2 canonical series: flight_id; ISO-8601 timestamp_utc; position lat/lon/alt_m (degrees, degrees, metres); attitude roll/pitch/yaw in degrees; battery percent/voltage_v; sensors; and metadata. Local north/east metres are deterministically projected from a configured origin and marked local_ned. The current schema requires numbers and missing numeric fields fall back to 0.0 rather than null. This makes zero ambiguous and is a material field-fidelity limitation to retire before operational use."),
        ("code", '{"flight_id":"f-123","timestamp_utc":"2026-03-18T09:42:30Z",<br/> "position":{"lat":1.3521,"lon":103.8198,"alt_m":38.0},<br/> "attitude":{"roll_deg":0.4,"pitch_deg":-1.2,"yaw_deg":92.1},<br/> "battery":{"percent":72.0,"voltage_v":15.2},"sensors":{"warning":"..."},<br/> "metadata":{"source":"dji_csv","frame":"wgs84"}}'),
        ("h", "Deterministic observations"),
        ("p", "Current categories include low/critical battery, telemetry gap, attitude shock, frozen or last-known position, mission incomplete and operator-warning evidence. Current demo heuristics are: 20%/10% battery, 15 points in 60 s, 25 m altitude step or 20 m/s vertical rate, 120 m/s air or 15 m/s ground speed, 40/70 degree attitude and 15 s gap. These are not platform-validated limits. GPS-weak text or a frozen track does not prove RF jamming."),
        ("h", "Review path"),
        ("p", "An incident stores a timestamp, detector category, signature and records URL. The API exposes canonical record ranges and a visualisation-ready WGS84 path. Cesium replay follows recorded time and overlays indexed incidents. Camera-frame census is a later sidecar join, not onboard inference."),
        ("table", key_table(["Input family", "Normalise to", "Review output"], [["PX4/ArduPilot/vendor/CSV/XLSX exports", "L2: position, attitude, battery, sensors, metadata", "timestamped observations + evidence link"], ["L2 record series", "detector thresholds and warning text", "replay marker + queryable signature"], ["Stored signature", "pattern grouping", "reviewable bulletin; no automatic fix"]], [2.1*inch, 2.55*inch, 2.3*inch], styles)),
        ("band", "Failure posture: missing parser/model/replay assets must surface status and preserve reviewable source evidence; no live fallback command is attempted."),
    ], styles)

    body_page(s, "4. Technical approach", "SEARCH, LOCAL ANALYSIS, MOSA AND DATA CONTROL", [
        ("h", "Evidence query and recurrence"),
        ("p", "`POST /v1/logs/upload` accepts a raw multipart file and optional X-WISL-SHA256, returning upload_id/status/sha256/duplicate. `GET /v1/uploads/{id}` exposes status/error; records and path endpoints expose L2 and WGS84 replay samples. `POST /v1/demo/query` returns deterministic evidence and matching signatures. Raw hashes are globally de-duplicated: matching SHA-256 returns the original upload instead of storing bytes again. Recurrence is category-level patterning, not proof of independent missions or common cause."),
        ("h", "Optional local-only model"),
        ("p", "SQLite records flights -> ingest_events -> canonical_records, plus translation_jobs, raw_uploads, incidents, incident_patterns and normalisation provenance. Local demonstration mode has one in-process worker and SQLite recovery rows; the normal deployment queue is Redis. Parsing and detectors do not call the LLM. The local-only model is invoked only on click, sees at most 100 flight summaries and 50 evidence items, has no tools/SQL/controls, and validates evidence IDs. One corrected four-flight call generated three hypotheses in 68.329 s with valid cited IDs. Semantic quality is unverified: it invented early-morning context and air-density/turbulence explanations absent from data."),
        ("h", "Open interfaces and sovereign deployment work"),
        ("p", "The OpenAPI contract covers upload/status, normalised ingest/status, records, paths, incidents, patterns and mitigation bulletins; canonical JSONL is exportable. This makes WISL a swappable post-flight node rather than a sealed stack. The demo is not accredited as air-gapped: CesiumJS and OpenStreetMap imagery are externally hosted unless cached or self-hosted. Operational deployment must define network boundary, authentication, key custody, retention, encryption, maps/assets and classification controls."),
        ("band", "No vehicle commands. No autonomous fixes. No claim of accredited air-gapped operation or sovereign deployment until a system owner approves the design."),
    ], styles)

    body_page(s, "5. Test methodology", "PRE-SPECIFIED SIMULATOR-CORPUS AUDIT", [
        ("p", "The generated corpus is hazards-only: 90 files across ten scenario cards and nine format skins. The pre-specified audit checks registry parse success; L2 schema projection; parseable/non-decreasing timestamps and finite numerics; expected deterministic incident types from scenario cards; and one isolated raw-upload-to-persistence/replay/query path."),
        ("p", "The audit treats several format exports of one scenario as one simulated mission. It requires two distinct scenario cards before using a signature as recurrence evidence. This is an implementation-path check of injected conditions; it does not confirm real-world causes."),
        ("table", key_table(["Question", "Method", "What it cannot establish"], [["Can bytes enter the evidence path?", "parser registry + canonical schema/integrity audit", "coverage of real vendor versions or encrypted logs"], ["Do injected cases produce expected labels?", "scenario-card versus deterministic detector comparison", "sensitivity, specificity or physical cause"], ["Can a reviewer follow an observation?", "multipart upload through replay/path/query endpoints", "operator time benefit or field robustness"]], [1.75*inch, 2.75*inch, 2.45*inch], styles)),
        ("h", "Deliberate limitations"),
        ("p", "The directory contains no normal/control mission. It does not cover RF contest, GPS denial/spoofing, actual comms loss, weather, low light, clutter, vibration, thermal stress, adversarial inputs or field workflow. Mocked format skins can omit fields; that is a format-fidelity risk requiring reportable audit, not evidence of a platform defect."),
        ("band", "API suite: 158 passed, four deprecation warnings, 9.35 s. Replay Node: 13 passed; UI Node: five passed; parser: 24 passed, four skipped. Full bounded inventory: 70/90 parsed to valid L2; 20 explicit whole-path timeouts (10 PX4 ULG, 10 ArduPilot BIN); 36/90 expected-detection hits. Targeted corrected regression: 10 original DJI hazards + 2 supplemental synthetic missions passed parsing, valid L2, expected detection and bounded processing; two isolated upload/replay/query representatives took 3.044 s. Simulator/software evidence only."),
    ], styles)

    body_page(s, "6. Results and cost", "WHAT THE CURRENT EVIDENCE SUPPORTS", [
        ("h", "Verified qualitative result"),
        ("p", "The repository demonstrates a record-and-review workflow: raw upload, canonical persistence, deterministic observations, incident evidence, replay, deterministic query, optional local analysis and explicit unavailable-model behaviour. The analysis route cannot become a control channel and returns deterministic evidence when unavailable. One corrected four-flight local analysis call generated three hypotheses in 68.329 s and all cited IDs were verified. That proves transport/schema/evidence-reference handling only: the model invented early-morning context and air-density/turbulence explanations absent from data, so no causal-analysis claim is made."),
        ("h", "Regression found and corrected"),
        ("p", "DJI valid zero relative height was previously treated as false and fell back to 180 ft MSL, creating artificial takeoff/landing altitude spikes. The corrected parser retains valid zero; a new takeoff/landing regression fails on the old implementation and passes in this worktree, with six parser tests passing. Prior artificial spikes are not reported as flight failures."),
        ("h", "Claims deliberately withheld"),
        ("p", "No field flight, operator study, normal baseline, accredited security evaluation or reliability estimate is reported. The 90-file corpus is not a 90-flight operational evaluation. Warning labels do not attribute jamming, sabotage, weather or component failure. Broad-signature recurrence does not establish the same defect or independent physical missions."),
        ("h", "Economics"),
        ("p", "One Apple M4/16 GiB local state held four flights, 867 canonical records and three incidents in a 1,847,296-byte SQLite database; the model file was 4,683,075,440 bytes. Five sequential exact-warning queries measured 9.27, 5.82, 9.47, 14.61 and 7.60 ms. This one warm local run is not a scale, throughput or cost-to-serve benchmark. No credible hardware unit cost, analyst-time saving or procurement baseline is available."),
        ("table", key_table(["Evidence now", "Decision not yet supported", "Next measurement"], [["working recorded-log workflow", "field readiness or a formal TRL exit", "authorised shadow-study task completion"], ["deterministic/model-offline fallback", "causal diagnosis", "reviewer agreement on evidence sufficiency"], ["simulator corpus structure", "savings or procurement case", "time, storage and false-review baseline"]], [2.15*inch, 2.35*inch, 2.45*inch], styles)),
    ], styles)

    body_page(s, "7. Primary CONOPS", "ARMY SMALL-UAS TRAINING AND MAINTENANCE REVIEW", [
        ("p", "After a small-UAS training sortie, a designated operator moves the completed controller log into the watched directory. The edge uploader waits for stability, hashes it and transfers it to an authorised endpoint. A reviewer opens the stored flight, sees time-linked rule observations, scrubs replay and opens the recorded evidence."),
        ("p", "For a repeat signature, the reviewer compares permitted cases and may create a mitigation bulletin for human approval. WISL stays silent in flight because it is post-flight only. Upload, parser or model failure must show status and preserve the source for retry/manual review. Training is limited to selecting/uploading logs, reading evidence links and treating all labels/hypotheses as non-diagnostic."),
        ("h", "Secondary contexts"),
        ("p", "RSAF UAV governance/engineering review is plausible because the public UAV Command has governance and maintenance roles [6]. HTX MDOS already aims to unite drone systems and live telemetry [4], [5]; WISL can only be framed as a possible historical-review complement. RSN USV telemetry is a later adjacent extension, not current aerial-drone scope [8]. DIS/DOTC may be an integration stakeholder, not a primary flight operator [7]. Other NATO sovereign buyers are an unvalidated secondary market hypothesis."),
        ("h", "Show-stopper risks"),
        ("p", "Representative authorised log access; data classification/governance; parser drift or encryption; label/LLM over-trust; absence of normal baseline; non-independent recurrence; and externally hosted replay assets can each kill the programme. Every one needs a testable gate."),
    ], styles)

    body_page(s, "8. Defensibility", "MODEST TODAY; EARNED THROUGH GOVERNED INTEGRATION", [
        ("p", "The present defensibility is modest and should not be overstated. Open-source flight tools and commercial fleet-management products already provide visualisation, replay and maintenance. No real-log dataset, accreditation or operator integration moat exists today."),
        ("p", "The defensible direction is an audited integration layer: raw hashes plus canonical evidence, reviewed local deployment controls, deterministic findings accessible without a model, replay-to-evidence links and data/threshold knowledge accumulated under an authorised operator programme. Such a moat exists only if controlled data and workflow evaluation produce durable, governed evidence."),
        ("table", key_table(["Closest alternative", "WISL could differentiate by", "Where WISL does not win by default"], [["PX4/Mission Planner", "cross-source canonical evidence and pattern review", "deep native single-platform diagnostics"], ["DJI FlightHub 2", "authorised cross-source post-flight workflow", "DJI operations management and deployed product breadth"], ["DroneLogbook", "incident-evidence/replay investigation flow", "fleet/compliance/maintenance maturity"]], [1.7*inch, 2.55*inch, 2.7*inch], styles)),
        ("band", "No cost-to-parity estimate is credible without authorised data access and a defined integration/security scope."),
    ], styles)

    body_page(s, "9. Incubation plan", "SIX MONTHS OF GATED EVIDENCE", [
        ("p", "This is a proposed route, not a commitment: ask the DVL programme sponsor to facilitate an introduction to an appropriate Army small-UAS training/maintenance counterpart. No outreach, sponsor support or operator support is claimed. Month 1 gates are discovery, classification/data-flow review and permission to use de-identified representative exports or synthetic material only."),
        ("table", key_table(["Period", "Milestone", "Continuation gate"], [["Month 1", "workflow discovery; data and classification review", "approved representative or synthetic-data route"], ["Months 2-3", "data contract; acceptance matrix; provenance/fidelity report; corrupted/retry/model-offline tests", "field retention/missing-field decisions explicit"], ["Months 4-5", "shadow study with pre-specified tasks and manual comparator", "measured evidence retrievability and review burden"], ["Month 6", "limited-sandbox continuation decision", "security approval, data fidelity, independent mission evidence, workflow value"]], [1.1*inch, 3.55*inch, 2.3*inch], styles)),
        ("p", "The team covers software, ingestion and visualisation. Isaac's research-support role is proposed; no DSO contribution or endorsement is claimed. The immediate asks are operator workflow feedback, an approved test-data route and a test environment. Formal TRL entry/exit is not claimed because the needed field evidence and programme assessment are absent."),
        ("h", "Funding priorities if gates pass"),
        ("p", "Secure local deployment hardening; parser fixtures and fidelity audits; controlled test time; product/security engineering; and an evaluation design with normal controls. Do not spend against a scale or procurement claim until the above gates establish that there is a permitted, measurable workflow."),
    ], styles)

    body_page(s, "10. Decision statement", "A REVIEWABLE POST-FLIGHT NODE, NOT AN AUTONOMOUS SYSTEM", [
        ("p", "WISL's demonstrated scope is recorded-log evidence handling and post-flight review. It can preserve a raw-log chain, present a canonical time series, surface deterministic observations, connect them to replay and let a reviewer compare stored patterns. Local-model output is optional and bounded; deterministic evidence remains available without it."),
        ("p", "The programme should proceed only if an authorised owner can supply a real review workflow and representative permitted logs, and if a controlled evaluation shows sufficient data fidelity and analyst value. Until then, WISL should remain an honest synthetic/SITL demonstration with its limits visible."),
        ("band", "Core sentence: WISL brings recorded drone logs into one searchable view so teams can investigate incidents and review recurring issues across flights."),
    ], styles)

    # references and appendix (excluded from body count)
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
    s += [P("References", styles["section"]), P("IEEE-style web references; accessed 13 September 2026.", styles["kicker"])]
    s += [P(ref, styles["ref"]) for ref in refs]
    s += [PageBreak(), P("Appendix A. Validation artefacts and reproducibility", styles["section"]), P("EXCLUDED FROM THE TEN-PAGE BODY BUDGET", styles["kicker"])]
    s += [P("Independent validation artefacts: docs/submission/corpus-validation.md and output/evidence/corpus-validation/corpus-validation.json. The corpus command is documented in the former. This report's builder is scripts/build_wisl_final_report.py. It uses reportlab and fixed page boundaries: cover, ten body pages, references and appendix.", styles["body"]), band("Interpret all generated corpus scenarios as synthetic/SITL fixtures. No operational field-flight conclusion may be inferred from this appendix. Supplemental synthetic controls remain outside the original corpus denominator.", styles, RED)]
    doc.build(s)


if __name__ == "__main__":
    build()
