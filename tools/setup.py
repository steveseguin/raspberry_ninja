#!/usr/bin/env python3
"""Friendly unattended setup for the common Raspberry Ninja use cases."""

from __future__ import annotations

import argparse
import getpass
import glob
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable, List, Optional, Sequence, Tuple
from urllib.parse import quote

try:
    from tools import install_unattended
except ImportError:  # Running directly as ``python3 tools/setup.py``.
    import install_unattended

try:
    from v4l2_devices import get_v4l2_device_name, is_v4l2_capture_device
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from v4l2_devices import get_v4l2_device_name, is_v4l2_capture_device


STREAM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
ALSA_CAPTURE_RE = re.compile(
    r"card\s+\d+:\s+(?P<card>[^\s]+)\s+\[(?P<label>[^]]+)\],\s+"
    r"device\s+(?P<device>\d+):",
    re.IGNORECASE,
)
CSI_CAMERA_RE = re.compile(r"^\s*\d+\s*:\s*(?P<label>.+)$", re.MULTILINE)
CSI_SOURCE_PREFIX = "csi:"


def ask_choice(
    prompt: str,
    choices: Sequence[str],
    *,
    input_fn: Callable[[str], str] = input,
) -> int:
    while True:
        print(prompt)
        for index, label in enumerate(choices, start=1):
            print(f"  {index}. {label}")
        answer = input_fn("Choice: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return int(answer) - 1
        print("Please enter one of the numbers shown.\n")


def ask_stream_id(*, input_fn: Callable[[str], str] = input) -> str:
    while True:
        value = input_fn("Stream name [home-video]: ").strip() or "home-video"
        if STREAM_ID_RE.fullmatch(value):
            return value
        print("Use only letters, numbers, dashes, or underscores.\n")


def _stable_v4l2_alias(device: str) -> str:
    real_device = os.path.realpath(device)
    for alias in sorted(glob.glob("/dev/v4l/by-id/*")):
        if os.path.realpath(alias) == real_device:
            return alias
    return device


def discover_cameras() -> List[Tuple[str, str]]:
    cameras: List[Tuple[str, str]] = []
    for device in sorted(glob.glob("/dev/video*")):
        if not is_v4l2_capture_device(device):
            continue
        stable_device = _stable_v4l2_alias(device)
        label = get_v4l2_device_name(device) or Path(device).name
        if not any(existing[0] == stable_device for existing in cameras):
            cameras.append((stable_device, label))
    csi_camera = discover_csi_camera()
    if csi_camera:
        cameras.insert(0, csi_camera)
    return cameras


def discover_csi_camera(
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Optional[Tuple[str, str]]:
    backends = (
        ("rpicam", "rpicam-hello", "rpicamsrc"),
        ("libcamera", "libcamera-hello", "libcamerasrc"),
    )
    for backend, camera_tool, source_element in backends:
        try:
            cameras = runner(
                [camera_tool, "--list-cameras"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = f"{cameras.stdout}\n{cameras.stderr}"
            camera_match = CSI_CAMERA_RE.search(output)
            if not camera_match:
                continue
            plugin = runner(
                ["gst-inspect-1.0", source_element],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if plugin.returncode == 0:
            label = camera_match.group("label").split("[")[0].strip()
            return (f"{CSI_SOURCE_PREFIX}{backend}", label or "Raspberry Pi Camera")
    return None


def probe_camera_formats(
    device: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> set[str]:
    try:
        result = runner(
            ["v4l2-ctl", "-d", device, "--list-formats-ext"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()

    output = f"{result.stdout}\n{result.stderr}".upper()
    formats = set()
    if "H264" in output or "H.264" in output:
        formats.add("H264")
    if "MJPG" in output or "MJPEG" in output:
        formats.add("MJPG")
    if "YUYV" in output or "YUY2" in output:
        # V4L2 calls the packed format YUYV; GStreamer calls the same layout YUY2.
        formats.add("YUY2")
    return formats


def choose_camera_format(formats: set[str]) -> Optional[str]:
    for preferred in ("H264", "MJPG", "YUY2"):
        if preferred in formats:
            return preferred
    return None


def discover_alsa_inputs(
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> List[Tuple[str, str]]:
    try:
        result = runner(
            ["arecord", "-l"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    devices: List[Tuple[str, str]] = []
    for match in ALSA_CAPTURE_RE.finditer(result.stdout):
        value = f"hw:{match.group('card')},{match.group('device')}"
        label = match.group("label").strip()
        if not any(existing[0] == value for existing in devices):
            devices.append((value, label))
    return devices


def display_connected() -> bool:
    for status_path in glob.glob("/sys/class/drm/card*-HDMI-A-*/status"):
        try:
            if Path(status_path).read_text(encoding="utf-8").strip() == "connected":
                return True
        except OSError:
            continue
    return False


def build_receiver_arguments(repo: Path, stream_id: str, password: str) -> List[str]:
    return [
        "--repo",
        str(repo),
        "--password",
        password,
        "receiver",
        "--stream-id",
        stream_id,
    ]


def build_view_url(stream_id: str, password: str) -> str:
    return (
        "https://vdo.ninja/?view="
        f"{quote(stream_id, safe='')}&password={quote(password, safe='')}"
    )


def build_sender_arguments(
    repo: Path,
    stream_id: str,
    password: str,
    camera: str,
    camera_format: Optional[str],
    audio_device: Optional[str],
) -> List[str]:
    arguments = [
        "--repo",
        str(repo),
        "--password",
        password,
        "sender",
        "--stream-id",
        stream_id,
    ]
    if camera.startswith(CSI_SOURCE_PREFIX):
        arguments.append(f"--{camera.removeprefix(CSI_SOURCE_PREFIX)}")
    else:
        arguments.extend(["--camera", camera])
    if camera_format:
        arguments.extend(["--format", camera_format])
    if camera_format == "YUY2" and not camera.startswith(CSI_SOURCE_PREFIX):
        arguments.append("--raw")
    if camera_format == "H264":
        arguments.extend(
            ["--width", "1280", "--height", "720", "--framerate", "30", "--bitrate", "1800"]
        )
    if audio_device:
        arguments.extend(["--audio-device", audio_device])
    return arguments


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    input_fn: Callable[[str], str] = input,
    password_fn: Callable[[str], str] = getpass.getpass,
) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--inventory", action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args(list(argv or []))
    if options.inventory:
        print(
            json.dumps(
                {
                    "cameras": discover_cameras(),
                    "audio": discover_alsa_inputs(),
                    "display": display_connected(),
                },
                sort_keys=True,
            )
        )
        return 0

    repo = Path(__file__).resolve().parents[1]
    print("\nRaspberry Ninja setup\n")
    role = ask_choice(
        "What should this Pi do?",
        ("Show video on a TV", "Send camera video"),
        input_fn=input_fn,
    )
    stream_id = ask_stream_id(input_fn=input_fn)
    password = password_fn("Stream password: ").strip()
    if not password:
        print("A password is required.", file=sys.stderr)
        return 2

    if role == 0:
        arguments = build_receiver_arguments(repo, stream_id, password)
        if not display_connected():
            print("\nConnect the TV before the next reboot for the most reliable HDMI detection.")
    else:
        cameras = discover_cameras()
        if not cameras:
            print("\nNo camera was found. Connect it, then run this setup again.", file=sys.stderr)
            return 2
        camera_index = 0
        if len(cameras) > 1:
            camera_index = ask_choice(
                "Which camera should be used?",
                [label for _device, label in cameras],
                input_fn=input_fn,
            )
        camera, _label = cameras[camera_index]
        camera_format = None
        if not camera.startswith(CSI_SOURCE_PREFIX):
            camera_format = choose_camera_format(probe_camera_formats(camera))

        audio_device = None
        audio_inputs = discover_alsa_inputs()
        if audio_inputs:
            use_audio = input_fn("Use a microphone too? [y/N]: ").strip().lower()
            if use_audio in {"y", "yes"}:
                audio_index = 0
                if len(audio_inputs) > 1:
                    audio_index = ask_choice(
                        "Which microphone should be used?",
                        [label for _device, label in audio_inputs],
                        input_fn=input_fn,
                    )
                audio_device = audio_inputs[audio_index][0]

        arguments = build_sender_arguments(
            repo,
            stream_id,
            password,
            camera,
            camera_format,
            audio_device,
        )

    try:
        result = install_unattended.main(arguments)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"\nSetup could not finish: {exc}", file=sys.stderr)
        return 1
    if result:
        return result

    print("\nReady.")
    if role == 0:
        print(f"Leave this Pi on. It will show '{stream_id}' whenever the sender starts.")
    else:
        print(f"View the stream at: {build_view_url(stream_id, password)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
