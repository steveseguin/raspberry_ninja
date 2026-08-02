from __future__ import annotations

import glob
import os
import struct
import time
from typing import Callable, Optional, Tuple

try:
    import fcntl
except ImportError:  # pragma: no cover - V4L2 is Linux-only
    fcntl = None


VIDIOC_QUERYCAP = 0x80685600
V4L2_CAP_VIDEO_CAPTURE = 0x00000001
V4L2_CAP_VIDEO_OUTPUT = 0x00000002
V4L2_CAP_VIDEO_CAPTURE_MPLANE = 0x00001000
V4L2_CAP_VIDEO_OUTPUT_MPLANE = 0x00002000
V4L2_CAP_DEVICE_CAPS = 0x80000000


def query_v4l2_capabilities(path: str) -> Optional[int]:
    """Return effective V4L2 capability flags, or None when they cannot be queried."""
    if fcntl is None:
        return None

    flags = os.O_NONBLOCK | os.O_RDWR
    try:
        descriptor = os.open(path, flags)
    except OSError:
        try:
            descriptor = os.open(path, os.O_NONBLOCK | os.O_RDONLY)
        except OSError:
            return None

    try:
        capability_buffer = bytearray(104)
        fcntl.ioctl(descriptor, VIDIOC_QUERYCAP, capability_buffer, True)
        capabilities = struct.unpack_from("I", capability_buffer, 84)[0]
        device_capabilities = struct.unpack_from("I", capability_buffer, 88)[0]
        if capabilities & V4L2_CAP_DEVICE_CAPS:
            return device_capabilities
        return capabilities
    except OSError:
        return None
    finally:
        os.close(descriptor)


def is_v4l2_capture_device(path: str) -> bool:
    capabilities = query_v4l2_capabilities(path)
    if capabilities is None:
        return False
    capture_flags = V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_VIDEO_CAPTURE_MPLANE
    return bool(capabilities & capture_flags)


def is_v4l2_output_device(path: str) -> bool:
    capabilities = query_v4l2_capabilities(path)
    if capabilities is None:
        return False
    output_flags = V4L2_CAP_VIDEO_OUTPUT | V4L2_CAP_VIDEO_OUTPUT_MPLANE
    return bool(capabilities & output_flags)


def _device_sort_key(path: str) -> Tuple[int, str]:
    suffix = path.removeprefix("/dev/video")
    return (int(suffix), path) if suffix.isdigit() else (2**31 - 1, path)


def resolve_v4l2_input_device(
    device: str,
    wait_attempts: int = 6,
    wait_seconds: float = 1.0,
    log: Callable[[str], None] = print,
) -> Tuple[str, bool]:
    """Resolve a readable capture-capable V4L2 node and return (path, error)."""
    original = device
    if not os.path.exists(device):
        log(f"Waiting for {device} to appear...")
        for _attempt in range(wait_attempts):
            time.sleep(wait_seconds)
            if os.path.exists(device):
                log(f"Found {device}")
                break

    usable = (
        os.path.exists(device)
        and os.access(device, os.R_OK)
        and is_v4l2_capture_device(device)
    )
    if usable:
        return device, False

    log(f"The video input {device} is unavailable or not capture-capable. Scanning for alternatives...")
    for candidate in sorted(glob.glob("/dev/video*"), key=_device_sort_key):
        if not os.path.exists(candidate) or not os.access(candidate, os.R_OK):
            continue
        if not is_v4l2_capture_device(candidate):
            continue
        name_path = f"/sys/class/video4linux/{os.path.basename(candidate)}/name"
        try:
            with open(name_path, "r", encoding="utf-8") as name_file:
                device_name = name_file.read().strip()
        except OSError:
            device_name = "V4L2 capture device"
        log(f"Using {candidate} ({device_name}) instead of {original}")
        return candidate, False

    log("No alternative video capture device found.")
    return original, True


def normalize_v4l2_device(device: Optional[str], default_index: int = 0) -> str:
    if not device:
        return f"/dev/video{default_index}"
    text = str(device).strip()
    if text.isdigit():
        return f"/dev/video{int(text)}"
    if text.startswith("video") and text[5:].isdigit():
        return f"/dev/{text}"
    return text


def resolve_v4l2_output_device(
    device: Optional[str],
    default_index: int = 0,
    log: Callable[[str], None] = print,
) -> Optional[str]:
    """Resolve a writable output-capable V4L2 node."""
    candidate = normalize_v4l2_device(device, default_index)
    if (
        os.path.exists(candidate)
        and os.access(candidate, os.W_OK)
        and is_v4l2_output_device(candidate)
    ):
        return candidate

    log(f"V4L2 output device {candidate} unavailable or not output-capable; scanning for alternatives.")
    for path in sorted(glob.glob("/dev/video*"), key=_device_sort_key):
        if not os.path.exists(path) or not os.access(path, os.W_OK):
            continue
        if is_v4l2_output_device(path):
            log(f"Using first V4L2 output device: {path}")
            return path
    return None
