import base64
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "docs" / "diagrams"
DOCUMENT = ROOT / "docs" / "architecture-uml.md"
SEQUENCES = ("upload-receive", "upload-canonical", "upload-review")


def render():
    blocks = re.findall(r"^```mermaid\n(.*?)^```", DOCUMENT.read_text(), re.M | re.S)
    if len(blocks) != 6 or not all("\nsequenceDiagram\n" in block for block in blocks[1:4]):
        raise ValueError("Expected interface map, three sequences, data model and lifecycle, in that order")
    env = dict(os.environ, PUPPETEER_SKIP_DOWNLOAD="true")
    if not env.get("PUPPETEER_EXECUTABLE_PATH"):
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            shutil.which("google-chrome"),
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
        ]
        chrome = next((path for path in candidates if path and Path(path).is_file()), None)
        if not chrome:
            raise RuntimeError("Set PUPPETEER_EXECUTABLE_PATH to your Chrome or Chromium executable")
        env["PUPPETEER_EXECUTABLE_PATH"] = chrome
    with tempfile.TemporaryDirectory(prefix="wisl-diagrams-") as directory:
        output = Path(directory) / "diagram.svg"
        subprocess.run(
            ["npx", "--yes", "--package", "@mermaid-js/mermaid-cli@11.12.0", "mmdc",
             "--quiet", "--input", str(DOCUMENT), "--output", str(output), "--width", "1800"],
            env=env, check=True,
        )
        for index in range(1, 7):
            image = output.with_name(f"diagram-{index}.svg")
            svg = ET.parse(image).getroot()
            if svg.tag != "{http://www.w3.org/2000/svg}svg" or "viewBox" not in svg.attrib:
                raise ValueError(f"Invalid SVG for Mermaid block {index}")
        for index, name in enumerate(SEQUENCES, start=2):
            shutil.copyfile(output.with_name(f"diagram-{index}.svg"), ASSETS / f"{name}.svg")
    print("Validated all six Mermaid diagrams; rebuilt three sequence SVGs.")


def export_html():
    diagrams = [
        ("components", "01", "The system, at a glance", "Responsibility layers, not a wall of connections. Read from entry points through the local platform to stored evidence."),
        ("upload-receive", "02A", "Receive & acknowledge", "Authenticate, validate and deduplicate. Only new content enters the local worker queue."),
        ("upload-canonical", "02B", "Create canonical evidence", "Parse vendor logs, apply privacy handling and persist the validated L2 telemetry contract."),
        ("upload-review", "02C", "Detect, finalise & review", "Deterministic rules produce evidence while the console watches for completion. The local model is not on this path."),
    ]
    sections = []
    for name, number, title, description in diagrams:
        image = base64.b64encode((ASSETS / f"{name}.svg").read_bytes()).decode()
        sections.append(f'<section id="{name}"><div class="section-heading"><span>{number}</span>'
                        f'<div><h2>{title}</h2><p>{description}</p></div></div>'
                        f'<figure tabindex="0" aria-label="Scrollable diagram: {title}">'
                        f'<img src="data:image/svg+xml;base64,{image}" alt="{description}" /></figure></section>')
    html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>WISL · Architecture atlas</title>
<style>
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f6f7f9;color:#183047;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif}
header,main,footer{max-width:1328px;margin:auto;padding:48px}header{padding-bottom:28px}.eyebrow{font-size:12px;letter-spacing:2px;font-weight:700}h1{font-size:clamp(32px,5vw,52px);letter-spacing:-1.6px;margin:20px 0 14px;line-height:1.1}header p{max-width:760px;font-size:18px;line-height:1.6;color:#53657a}nav{display:flex;flex-wrap:wrap;gap:10px;margin-top:26px}nav a{color:#183047;text-decoration:none;padding:10px 16px;border:1px solid #d4dde5;background:white;border-radius:8px;font-size:14px}nav a:hover{background:#e4f0fa}a:focus-visible,figure:focus-visible{outline:3px solid #35668b;outline-offset:4px}main{padding-top:0}section{scroll-margin-top:24px;margin-top:42px;min-width:0}.section-heading{display:flex;align-items:flex-start;gap:18px;margin:0 0 22px}.section-heading>span{font-size:12px;letter-spacing:1px;font-weight:700;padding:9px 11px;border-radius:6px;background:#e4f0fa;flex-shrink:0}.section-heading>div{min-width:0}h2{margin:3px 0 10px;font-size:24px;letter-spacing:-.4px}p{margin:0;color:#53657a;line-height:1.6}figure{margin:0;padding:24px;background:#fff;border:1px solid #dce3e9;border-radius:16px;overflow:auto}img{display:block;width:100%;height:auto;min-width:760px}#components img{min-width:900px}#upload-receive .section-heading>span{background:#fae9ac}#upload-review .section-heading>span{background:#dceecf}footer{padding-top:0;font-size:13px;line-height:1.7;color:#53657a}.principle{border-left:3px solid #92b577;padding-left:16px;margin-bottom:18px;color:#294c2d}@media(max-width:700px){header,main,footer{padding-left:20px;padding-right:20px}header{padding-top:30px}figure{padding:12px}h2{font-size:21px}}@media print{body{background:white}header,main,footer{padding:20px}nav{display:none}section{break-before:page}figure{border:0;padding:0;overflow:visible}img,#components img{min-width:0}h1{font-size:36px}}
</style>
</head>
<body>
<header><div class="eyebrow">WISL / ENGINEERING ATLAS</div><h1>From logs to evidence.<br>A clearer view of the system.</h1><p>A layered architecture map and a three-act upload journey. Colour identifies responsibility; numbered phases make the processing order explicit.</p><nav aria-label="Diagram navigation"><a href="#components">01 · Component map</a><a href="#upload-receive">02A · Receive</a><a href="#upload-canonical">02B · Standardise</a><a href="#upload-review">02C · Review</a></nav></header>
<main>""" + "\n".join(sections) + """</main>
<footer><p class="principle">Deterministic by default. Models draft hypotheses; stored evidence remains the source of truth.</p><p>Source: docs/architecture-uml.md and docs/diagrams/components.svg · Local demo configuration.</p><p>On narrow screens, scroll within a diagram for readable labels. All diagrams are embedded in this page; no server, scripts or network connection are needed.</p></footer>
</body></html>
"""
    destination = ROOT / "docs" / "architecture.html"
    destination.write_text(html, encoding="utf-8")
    print(f"Standalone HTML diagrams: {destination}")


if __name__ == "__main__":
    render()
    export_html()
