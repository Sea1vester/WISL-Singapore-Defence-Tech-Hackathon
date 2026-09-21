#!/usr/bin/env python3
"""Fetch public real-world drone logs listed in fixtures/public-logs.manifest.json.

Downloads each entry with a URL into ``raw_telemetry-datasets/public/<source>/<filename>``
(skipping files already present with a matching sha256), verifies sha256 when the
manifest records one, and stages ``local`` entries by symlinking them into
``public/local/`` so one ``--input`` directory covers the whole real corpus.

``--record-hashes`` writes missing sha256 values back into the manifest after a
successful fetch/stage. ``--dry-run`` prints the plan without downloading.
An ``INVENTORY.json`` (id, path, bytes, sha256, fetched_at) is written under
``raw_telemetry-datasets/public/``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "sdth-telemetry" / "fixtures" / "public-logs.manifest.json"
DATASETS_ROOT = ROOT / "raw_telemetry-datasets"
PUBLIC_ROOT = DATASETS_ROOT / "public"

DOWNLOAD_DELAY_S = 1.0
MAX_TOTAL_BYTES = 300 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_local(entry: dict, dest: Path, datasets_root: Path) -> Path:
    """Link the on-disk dataset file into public/local/, copying if needed."""
    source = datasets_root / entry["path"]
    if not source.exists():
        raise FileNotFoundError(f"local entry not found: {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink() or dest.exists():
        if sha256(dest) == sha256(source):
            return dest
        dest.unlink()
    try:
        dest.symlink_to(source.resolve())
    except OSError:
        import shutil

        shutil.copy2(source, dest)
    return dest


def fetch_remote(entry: dict, dest: Path, client: httpx.Client) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with client.stream("GET", entry["url"], follow_redirects=True) as response:
        response.raise_for_status()
        with tmp.open("wb") as handle:
            for chunk in response.iter_bytes(1024 * 256):
                handle.write(chunk)
    tmp.replace(dest)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--public-root", type=Path, default=PUBLIC_ROOT)
    ap.add_argument("--datasets-root", type=Path, default=DATASETS_ROOT)
    ap.add_argument("--record-hashes", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-delay", action="store_true", help="Skip the polite 1 s delay between downloads (tests).")
    args = ap.parse_args()

    manifest_path = args.manifest.resolve()
    public_root = args.public_root.resolve()
    datasets_root = args.datasets_root.resolve()

    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    inventory: list[dict] = []
    changed = False
    total_bytes = 0
    downloaded = staged = skipped = failed = 0

    client = httpx.Client(timeout=httpx.Timeout(120.0), headers={"User-Agent": "wisl-public-log-fetch/1.0"})
    first_download = True
    for entry in entries:
        dest = public_root / entry["source"] / Path(entry["path"]).name
        expected = entry.get("sha256")

        if args.dry_run:
            action = "stage-local" if entry["source"] == "local" else "download"
            if dest.exists() and expected and sha256(dest) == expected:
                action = "skip (present, sha matches)"
            print(f"{action}: {entry['id']} -> {dest}")
            continue

        try:
            if dest.exists() and expected and sha256(dest) == expected:
                skipped += 1
                total_bytes += dest.stat().st_size
            else:
                if entry["source"] == "local":
                    stage_local(entry, dest, datasets_root)
                    staged += 1
                else:
                    if total_bytes >= MAX_TOTAL_BYTES:
                        print(f"skip {entry['id']}: total byte cap reached", file=sys.stderr)
                        continue
                    if not first_download and not args.no_delay:
                        time.sleep(DOWNLOAD_DELAY_S)
                    fetch_remote(entry, dest, client)
                    first_download = False
                    downloaded += 1
                    total_bytes += dest.stat().st_size

            actual = sha256(dest)
            if expected and actual != expected:
                failed += 1
                print(f"sha256 mismatch for {entry['id']}: {actual} != {expected}", file=sys.stderr)
                continue
            if not expected and args.record_hashes:
                entry["sha256"] = actual
                changed = True
            inventory.append(
                {
                    "id": entry["id"],
                    "path": str(dest.relative_to(public_root)),
                    "bytes": dest.stat().st_size,
                    "sha256": actual,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception as exc:
            failed += 1
            print(f"failed {entry['id']}: {type(exc).__name__}: {exc}", file=sys.stderr)

    if not args.dry_run:
        public_root.mkdir(parents=True, exist_ok=True)
        (public_root / "INVENTORY.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
        if changed:
            manifest_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {"downloaded": downloaded, "staged": staged, "skipped": skipped, "failed": failed, "bytes": total_bytes}
            )
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
