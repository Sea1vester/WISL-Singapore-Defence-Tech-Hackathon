from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from .destinations import HttpDestination, NullDestination
from .uploader import LogUploader


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WISL edge uploader: ships completed flight logs from the controller to the cloud"
    )
    parser.add_argument("log_dir", type=Path, help="Directory the flight controller writes logs into")
    parser.add_argument(
        "--endpoint",
        default=None,
        help="Cloud upload endpoint. Omit while undecided: files are tracked as pending, nothing is sent.",
    )
    parser.add_argument("--api-key-env", default="WISL_UPLOAD_KEY", help="Env var holding the upload token")
    parser.add_argument("--watch", action="store_true", help="Keep running and scan on an interval")
    parser.add_argument("--interval", type=float, default=30.0, help="Scan interval in seconds (with --watch)")
    parser.add_argument("--manifest", type=Path, default=None, help="Override manifest path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.endpoint:
        destination = HttpDestination(args.endpoint, api_key=os.environ.get(args.api_key_env))
    else:
        destination = NullDestination()

    uploader = LogUploader(args.log_dir, destination, manifest_path=args.manifest)

    if args.watch:
        uploader.watch(interval_seconds=args.interval)
    else:
        # One-shot mode scans twice so files seen for the first time can pass the
        # stability check (a file is only "stable" once its size repeats between scans).
        uploader.scan_once()
        counts = uploader.scan_once()
        logging.info("Result: %s", counts)


if __name__ == "__main__":
    main()
