import argparse
import base64
import json
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


def table_rows(markdown, heading, fields):
    section = markdown.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]
    lines = [line for line in section.splitlines() if line.startswith("|")][2:]
    rows = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != len(fields):
            raise ValueError(f"Unexpected columns in {heading}: {line}")
        rows.append(dict(zip(fields, cells)))
    if not rows:
        raise ValueError(f"No table rows found in {heading}")
    return rows


def replace_region(html, pattern, content):
    html, count = re.subn(pattern, lambda match: match[1] + content + match[2], html, flags=re.S)
    if count != 1:
        raise ValueError(f"Expected one HTML build region, found {count}: {pattern}")
    return html


def export_html():
    destination = ROOT / "docs" / "architecture.html"
    html = destination.read_text(encoding="utf-8")
    markdown = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    data = {
        "packages": table_rows(markdown, "Packages", ("name", "role", "files")),
        "decisions": table_rows(markdown, "Key technical decisions and trade-offs", ("decision", "why", "tradeoff")),
    }
    encoded = json.dumps(data, ensure_ascii=False, indent=2).replace("<", "\\u003c")
    html = replace_region(html, r'(<script type="application/json" id="architecture-data">).*?(</script>)', "\n" + encoded + "\n")
    names = [("components", "Detailed component map"), ("upload-receive", "Upload sequence · receive"),
             ("upload-canonical", "Upload sequence · standardise"), ("upload-review", "Upload sequence · review")]
    images = []
    for name, title in names:
        image = base64.b64encode((ASSETS / f"{name}.svg").read_bytes()).decode()
        images.append(f'<section><h3>{title}</h3><img alt="{title}" src="data:image/svg+xml;base64,{image}" loading="lazy" /></section>')
    html = replace_region(html, r'(<div id="reference-diagrams">).*?(</div>)', "\n" + "\n".join(images) + "\n")
    svg = re.search(r'<svg id="backend-map".*?</svg>', html, re.S).group()
    svg = svg.replace('role="group"', 'role="img"', 1)
    svg = re.sub(r' (?:data-node|tabindex|aria-pressed|aria-controls)="[^"]*"', "", svg)
    svg = svg.replace(' role="button"', "")
    ET.fromstring(svg)
    (ASSETS / "backend-data.svg").write_text(svg + "\n", encoding="utf-8")
    destination.write_text(html, encoding="utf-8")
    print(f"Built interactive HTML + backend SVG; embedded {len(data['packages'])} packages and {len(data['decisions'])} decisions.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the WISL architecture diagrams and interactive backend page")
    parser.add_argument("--html-only", action="store_true", help="Refresh the backend page and SVG without invoking Mermaid")
    args = parser.parse_args()
    if not args.html_only:
        render()
    export_html()
