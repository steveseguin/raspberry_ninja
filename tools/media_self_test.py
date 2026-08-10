#!/usr/bin/env python3
"""Low-impact local encode/RTP/decode checks for release and hardware QA."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Dict, List, Optional, Sequence


PROBES: Dict[str, Dict[str, object]] = {
    "x264": {
        "elements": ["x264enc", "h264parse", "rtph264pay", "rtph264depay", "avdec_h264"],
        "pipeline": [
            "videotestsrc", "num-buffers=30", "!",
            "video/x-raw,width=320,height=180,framerate=10/1", "!",
            "videoconvert", "!", "video/x-raw,format=I420", "!",
            "x264enc", "bitrate=300", "speed-preset=ultrafast", "tune=zerolatency", "!",
            "h264parse", "!", "rtph264pay", "!", "rtph264depay", "!",
            "h264parse", "!", "avdec_h264", "!", "fakesink",
        ],
    },
    "openh264": {
        "elements": ["openh264enc", "h264parse", "rtph264pay", "rtph264depay", "avdec_h264"],
        "pipeline": [
            "videotestsrc", "num-buffers=30", "!",
            "video/x-raw,width=320,height=180,framerate=10/1", "!",
            "videoconvert", "!", "video/x-raw,format=I420", "!",
            "openh264enc", "bitrate=300000", "max-bitrate=300000",
            "rate-control=bitrate", "enable-frame-skip=true", "complexity=0", "!",
            "h264parse", "!", "rtph264pay", "!", "rtph264depay", "!",
            "h264parse", "!", "avdec_h264", "!", "fakesink",
        ],
    },
    "vp8": {
        "elements": ["vp8enc", "rtpvp8pay", "rtpvp8depay", "vp8dec"],
        "pipeline": [
            "videotestsrc", "num-buffers=30", "!",
            "video/x-raw,width=320,height=180,framerate=10/1", "!",
            "videoconvert", "!", "video/x-raw,format=I420", "!",
            "vp8enc", "deadline=1", "target-bitrate=300000", "!",
            "rtpvp8pay", "!", "rtpvp8depay", "!", "vp8dec", "!", "fakesink",
        ],
    },
    "vp9": {
        "elements": ["vp9enc", "rtpvp9pay", "rtpvp9depay", "vp9dec"],
        "pipeline": [
            "videotestsrc", "num-buffers=30", "!",
            "video/x-raw,width=320,height=180,framerate=10/1", "!",
            "videoconvert", "!", "video/x-raw,format=I420", "!",
            "vp9enc", "deadline=1", "cpu-used=8", "target-bitrate=300000", "!",
            "rtpvp9pay", "!", "rtpvp9depay", "!", "vp9dec", "!", "fakesink",
        ],
    },
}


def element_available(element: str, *, runner=subprocess.run) -> bool:
    try:
        result = runner(
            ["gst-inspect-1.0", element],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def run_probe(name: str, *, runner=subprocess.run, timeout: int = 30) -> Dict[str, object]:
    definition = PROBES[name]
    missing = [
        element
        for element in definition["elements"]
        if not element_available(str(element), runner=runner)
    ]
    if missing:
        return {"status": "skipped", "missing": missing}

    command = ["gst-launch-1.0", "-q", *definition["pipeline"]]
    try:
        result = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"status": "failed", "reason": "timed out"}
    except OSError as exc:
        return {"status": "failed", "reason": str(exc)}
    if result.returncode:
        error = (result.stderr or result.stdout or "pipeline failed").strip().splitlines()
        return {
            "status": "failed",
            "reason": error[-1] if error else "pipeline failed",
        }
    return {"status": "passed"}


def read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").replace("\x00", "").strip()
    except OSError:
        return "unknown"


def environment_summary() -> Dict[str, str]:
    gst_version = "unknown"
    try:
        result = subprocess.run(
            ["gst-launch-1.0", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
        lines = result.stdout.splitlines()
        if lines:
            gst_version = lines[0].strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {
        "model": read_text("/proc/device-tree/model"),
        "python": platform.python_version(),
        "system": platform.platform(),
        "gstreamer": gst_version,
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local Raspberry Ninja media checks.")
    parser.add_argument("--json", action="store_true", help="print machine-readable results")
    parser.add_argument("--only", choices=tuple(PROBES), action="append")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = create_parser().parse_args(argv)
    names: List[str] = args.only or list(PROBES)
    results = {name: run_probe(name) for name in names}
    report = {"environment": environment_summary(), "probes": results}

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("Raspberry Ninja media check")
        for name, result in results.items():
            status = str(result["status"])
            detail = ""
            if status == "skipped":
                detail = " (not installed)"
            elif status == "failed":
                detail = f" ({result.get('reason', 'failed')})"
            print(f"  {name}: {status}{detail}")

    passed = sum(result["status"] == "passed" for result in results.values())
    failed = any(result["status"] == "failed" for result in results.values())
    return 1 if failed or not passed else 0


if __name__ == "__main__":
    raise SystemExit(main())
