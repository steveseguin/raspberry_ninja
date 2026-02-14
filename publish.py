#!/usr/bin/env python3
import random
import ssl
import websockets
import asyncio
import os
import sys
import json
import argparse
import time
import platform
import gi
import threading
import shutil
import socket
import re
import traceback
import subprocess
import struct
import glob
import signal
import weakref
import mmap
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Set, List
from functools import lru_cache
try:
    import hashlib
    from urllib.parse import urlparse, urlencode
    from urllib import request as urllib_request
except Exception as e:
    pass

try:
    import numpy as np
    import multiprocessing
    from multiprocessing import shared_memory
except Exception as e:
    pass

try:
    from aiohttp import web
    import aiohttp
except ImportError:
    web = None
    aiohttp = None
    
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes, padding
    from cryptography.hazmat.backends import default_backend
except ImportError as e:
    raise ImportError("Run `pip install cryptography` to install the dependencies needed for passwords") from e

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp
gi.require_version('GstRtp', '1.0')
from gi.repository import GstRtp


try:
    from gi.repository import GLib
except ImportError:
    pass
    
#os.environ['GST_DEBUG'] = '3,ndisink:7,videorate:5,videoscale:5,videoconvert:5'

def env_flag(name: str) -> bool:
    value = os.environ.get(name)
    if value is None:
        return False
    return value.strip().lower() not in ("0", "false", "no", "off", "")

RN_DISABLE_HW_DECODER = env_flag("RN_DISABLE_HW_DECODER")
RN_FORCE_HW_DECODER = env_flag("RN_FORCE_HW_DECODER")

H264_PROFILE_ALIASES = {
    "baseline": "42001f",
    "constrained-baseline": "42e01f",
    "constrained_baseline": "42e01f",
    "main": "4d0032",
    "high": "640032",
    "high10": "6e0032",
    "high-10": "6e0032",
    "high422": "7a0032",
    "high-422": "7a0032",
    "high444": "f40032",
    "high-444": "f40032",
}

def sanitize_profile_level_id(value: Optional[str]) -> Optional[str]:
    """Normalize a profile-level-id string to lowercase hex without 0x prefix."""
    if not value:
        return None
    cleaned = value.strip().lower()
    if cleaned.startswith("0x"):
        cleaned = cleaned[2:]
    if not re.fullmatch(r"[0-9a-f]{6}", cleaned):
        return None
    return cleaned

_hw_decoder_warning_refs: Set[weakref.ReferenceType] = set()
_gst_log_hook_installed = False


def _hw_decoder_ref_cleanup(ref):
    _hw_decoder_warning_refs.discard(ref)


def _gst_hw_warning_log_hook(
    category,
    level,
    file_,
    function,
    line,
    obj,
    message,
    user_data,
):
    if level < Gst.DebugLevel.WARNING:
        return
    text = ""
    try:
        text = message.get()
    except Exception:
        text = ""
    combined = " ".join(filter(None, (text, file_, function)))
    combined_lower = combined.lower()
    if not any(
        token in combined_lower for token in ("nvv4l2decoder", "gstbufferpool", "v4l2bufferpool")
    ):
        return
    force = level >= Gst.DebugLevel.ERROR
    if bool(os.environ.get("RN_DEBUG_VIEWER")):
        print(
            f"[viewer] GST log hook captured hardware decoder warning (force={force}): {combined.strip()}"
        )
    for ref in list(_hw_decoder_warning_refs):
        inst = ref()
        if not inst:
            _hw_decoder_warning_refs.discard(ref)
            continue
        try:
            inst._handle_hw_decoder_warning(text, combined, force_trigger=force)
        except Exception:
            continue


def _ensure_gst_hw_warning_hook():
    global _gst_log_hook_installed
    if _gst_log_hook_installed:
        return
    try:
        Gst.debug_add_log_function(_gst_hw_warning_log_hook, None)
        _gst_log_hook_installed = True
    except Exception:
        pass


def _register_hw_decoder_warning_listener(instance):
    _ensure_gst_hw_warning_hook()
    if getattr(instance, "_hw_decoder_warning_ref", None):
        return
    ref = weakref.ref(instance, _hw_decoder_ref_cleanup)
    _hw_decoder_warning_refs.add(ref)
    instance._hw_decoder_warning_ref = ref

def generate_unique_ndi_name(base_name):
    return f"{base_name}_{int(time.time())}"
    
def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    print("!!! Unhandled exception !!!")
    print("Type:", exc_type)
    print("Value:", exc_value)
    print("Traceback:", ''.join(traceback.format_tb(exc_traceback)))

    tb = traceback.extract_tb(exc_traceback)
    for frame in tb:
        print(f"File \"{frame.filename}\", line {frame.lineno}, in {frame.name}")
sys.excepthook = handle_unhandled_exception


def get_exception_info(E):
    tb = traceback.extract_tb(E.__traceback__)
    error_line = tb[-1].lineno
    error_file = tb[-1].filename
    
    if len(tb) >= 2:
        caller = tb[-2]
        caller_line = caller.lineno
        caller_file = caller.filename
    else:
        caller_line = "unknown"
        caller_file = "unknown"
    
    return (
        f"{type(E).__name__} at line {error_line} in {error_file}: {E}\n"
        f"Called from line {caller_line} in {caller_file}"
    )

    
def enableLEDs(level=False):
    try:
        GPIO
    except Exception as e:
        return
    global LED_Level, p_R
    if level!=False:
        LED_Level = level
    p_R.start(0)      # Initial duty Cycle = 0(leds off)
    p_R.ChangeDutyCycle(LED_Level)     # Change duty cycle

def disableLEDs():
    try:
        GPIO
    except Exception as e:
        return

    global pin, p_R
    try:
        if 'p_R' in globals() and p_R:
            p_R.stop()
        if 'pin' in globals():
            GPIO.output(pin, GPIO.HIGH)    # Turn off all leds
    except Exception:
        pass
    try:
        GPIO.cleanup()
    except Exception:
        pass

def hex_to_ansi(hex_color):
    hex_color = hex_color.lstrip('#')

    if len(hex_color)==6:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
    elif len(hex_color)==3:
        r = int(hex_color[0:1]+hex_color[0:1], 16)
        g = int(hex_color[1:2]+hex_color[1:2], 16)
        b = int(hex_color[2:3]+hex_color[2:3], 16)
    else:
        return hex_color

    ansi_color = 16 + (36 * int(r / 255 * 5)) + (6 * int(g / 255 * 5)) + int(b / 255 * 5)

    return f"\033[38;5;{ansi_color}m"

# Global webserver reference for logging
_webserver_instance = None

def printc(message, color_code=None):
    reset_color = "\033[0m"

    if color_code is not None:
        color_code = hex_to_ansi(color_code)
        colored_message = f"{color_code}{message}{reset_color}"
        print(colored_message)
    else:
        print(message)
    
    # Send to webserver if available
    if _webserver_instance:
        # Strip ANSI codes for web display
        clean_message = re.sub(r'\033\[[0-9;]*m', '', message)
        _webserver_instance.add_log(clean_message)

def printwin(message):
    printc("<= "+message,"93F")
def printwout(message):
    printc("=> "+message,"9F3")
def printin(message):
    printc("<= "+message,"F6A")
def printout(message):
    printc("=> "+message,"6F6")
def printwarn(message):
    printc(message,"FF0")


def clear_display_surfaces() -> bool:
    """Attempt to clear visible console/framebuffer surfaces before rendering video."""
    ansi_clear = "\033[2J\033[H"
    cleared = False

    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "isatty") and stream.isatty():
                stream.write(ansi_clear)
                stream.flush()
                cleared = True
        except Exception:
            pass

    tty_candidates = [
        os.environ.get("TTY"),
        "/dev/tty",
        "/dev/tty0",
        "/dev/console",
    ]
    for device in [d for d in tty_candidates if d]:
        try:
            with open(device, "w", buffering=1) as tty:
                tty.write(ansi_clear)
                tty.flush()
                cleared = True
                break
        except Exception:
            continue

    framebuffer_candidates = [
        os.environ.get("FRAMEBUFFER"),
        "/dev/fb0",
        "/dev/fb1",
    ]

    def _clear_fb(path: str) -> bool:
        try:
            with open(path, "r+b", buffering=0) as fb:
                size = os.fstat(fb.fileno()).st_size
                if size <= 0:
                    return False
                with mmap.mmap(fb.fileno(), size, access=mmap.ACCESS_WRITE) as mm:
                    mm.seek(0)
                    chunk = b"\x00" * min(1 << 20, size)
                    remaining = size
                    while remaining > 0:
                        write_len = min(len(chunk), remaining)
                        mm.write(chunk[:write_len])
                        remaining -= write_len
                    mm.flush()
                return True
        except Exception:
            return False

    for fb_path in [p for p in framebuffer_candidates if p]:
        if _clear_fb(fb_path):
            cleared = True
            break

    return cleared

@lru_cache(maxsize=1)
def check_drm_displays():
    """Attempt to detect at least one active display using multiple backends."""

    def _print_connected(prefix, connectors):
        if not connectors:
            return
        print(f"{prefix}")
        for connector in connectors:
            print(f"  - {connector}")

    def _check_drm_info():
        if shutil.which("drm_info") is None:
            raise FileNotFoundError

        candidates = [
            ["drm_info", "--json"],
            ["drm_info", "-J"],
            ["drm_info"],
        ]
        for cmd in candidates:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0 or not result.stdout.strip():
                continue

            output = result.stdout.strip()
            try:
                drm_info = json.loads(output)
                connectors = [
                    f"{item.get('name', 'unknown')} ({item.get('connector_type', 'connector')})"
                    for item in drm_info.get('connectors', [])
                    if item.get('status') == 'connected'
                ]
                if connectors:
                    _print_connected("Display(s) detected via drm_info:", connectors)
                    return True
                return False
            except json.JSONDecodeError:
                # Fallback: look for textual matches
                connectors = [
                    line.strip()
                    for line in output.splitlines()
                    if "status" in line.lower() and "connected" in line.lower()
                ]
                if connectors:
                    _print_connected("Display(s) detected via drm_info:", connectors)
                    return True
                # Output wasn't usable as JSON; try next invocation
        return None

    def _check_kmsprint():
        if shutil.which("kmsprint") is None:
            raise FileNotFoundError

        result = subprocess.run(
            ["kmsprint", "-m"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode != 0:
            return None

        connectors = [
            line.strip()
            for line in result.stdout.splitlines()
            if "connected" in line.lower() and "disconnected" not in line.lower()
        ]
        if connectors:
            _print_connected("Display(s) detected via kmsprint:", connectors)
            return True
        return False

    def _check_xrandr():
        if shutil.which("xrandr") is None:
            raise FileNotFoundError

        result = subprocess.run(
            ["xrandr", "--query"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode != 0:
            return None

        connectors = [
            line.strip()
            for line in result.stdout.splitlines()
            if " connected" in line and "disconnected" not in line
        ]
        if connectors:
            _print_connected("Display(s) detected via xrandr:", connectors)
            return True
        return False

    checkers = [
        ("drm_info", _check_drm_info),
        ("kmsprint", _check_kmsprint),
        ("xrandr", _check_xrandr),
    ]

    for label, checker in checkers:
        try:
            result = checker()
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"{label} display probe failed: {e}")
            continue

        if result is True:
            return True
        if result is False:
            return False

    # Last resort: infer from environment variables
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        print("Display probe inconclusive; assuming a display is available based on environment.")
        return True

    print("Unable to detect a connected display. You may need to install drm-tools or ensure an X/Wayland session is active.")
    return False


@lru_cache(maxsize=1)
def is_jetson_device() -> bool:
    """Best-effort detection of NVIDIA Jetson platforms."""
    try:
        model_path = Path("/sys/firmware/devicetree/base/model")
        if model_path.exists():
            model = model_path.read_text(errors="ignore")
            if "NVIDIA Jetson" in model:
                return True
    except Exception:
        pass

    if Path("/etc/nv_tegra_release").exists():
        return True

    try:
        uname = platform.uname()
        if "tegra" in uname.machine.lower() or "tegra" in uname.release.lower():
            return True
        if "jetson" in uname.machine.lower():
            return True
    except Exception:
        pass

    return False


@lru_cache(maxsize=None)
def gst_element_available(name: str) -> bool:
    """Check if a given GStreamer element factory exists."""
    try:
        return Gst.ElementFactory.find(name) is not None
    except Exception:
        return False


@lru_cache(maxsize=None)
def gst_element_supports_property(element_name: str, property_name: str) -> bool:
    """Check whether a GStreamer element exposes a specific property."""
    try:
        element = Gst.ElementFactory.make(element_name)
        if not element:
            return False
        try:
            return element.find_property(property_name) is not None
        finally:
            # Ensure the temporary element is torn down promptly
            element.set_state(Gst.State.NULL)
            del element
    except Exception:
        return False


@lru_cache(maxsize=1)
def get_framebuffer_resolution() -> Optional[Tuple[int, int]]:
    """Best effort detection of framebuffer resolution for direct-display sinks."""
    potential_files = [
        Path("/sys/class/graphics/fb0/virtual_size"),
        Path("/sys/class/graphics/fb0/modes"),
    ]

    for file_path in potential_files:
        if not file_path.exists():
            continue
        try:
            content = file_path.read_text().strip()
        except Exception:
            continue

        if "," in content:
            parts = content.split(",")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return int(parts[0]), int(parts[1])
        if "x" in content:
            # Try to match strings like "1920x1080-60"
            resolution = content.split()[0]  # Take the first token
            dims = resolution.split("x")
            if len(dims) >= 2 and dims[0].isdigit():
                height_part = dims[1].split("-")[0]
                if height_part.isdigit():
                    return int(dims[0]), int(height_part)

    return None


def select_preferred_decoder(
    codec: str,
    fallback: str,
    disable_hw: bool = False,
    force_hw: bool = False,
) -> Tuple[str, Dict[str, Any], bool]:
    """
    Determine the most appropriate decoder element for the given codec.

    Returns a tuple of (factory_name, properties, using_hardware).
    """
    if disable_hw and not force_hw:
        return fallback, {}, False

    if RN_DISABLE_HW_DECODER and not force_hw:
        return fallback, {}, False

    codec_key = codec.upper()

    if is_jetson_device() and gst_element_available("nvv4l2decoder"):
        if codec_key in {"VP8", "H264", "VP9"}:
            # enable-max-performance prefers direct NVDEC usage on Jetson
            return "nvv4l2decoder", {"enable-max-performance": True}, True

    return fallback, {}, False


def clamp_int(value: Any, minimum: int, maximum: int) -> int:
    """Clamp a dynamic value to the inclusive integer range provided."""
    try:
        ivalue = int(value)
    except Exception:
        return minimum
    return max(minimum, min(maximum, ivalue))


def build_publisher_redundancy_fragment(args: Any) -> Tuple[str, Optional[Dict[str, int]]]:
    """
    Construct a pipeline fragment that wraps outgoing RTP with RED + ULPFEC
    when publisher-side redundancy is enabled.
    """
    if getattr(args, "view", False) or getattr(args, "streamin", False):
        return "", None
    if getattr(args, "video_pipeline", None):
        # Custom pipelines are assumed to manage redundancy themselves.
        return "", None
    if getattr(args, "nored", False) or getattr(args, "novideo", False):
        return "", None
    if not getattr(args, "force_red", False):
        # Leave publisher offers untouched unless redundancy is explicitly requested.
        return "", None

    red_pt = clamp_int(getattr(args, "publisher_red_pt", 123), 0, 127)
    fec_pt = clamp_int(getattr(args, "publisher_fec_pt", 125), 0, 127)
    red_distance = max(1, clamp_int(getattr(args, "publisher_red_distance", 1), 0, 4))
    fec_percentage = clamp_int(getattr(args, "publisher_fec_percentage", 20), 0, 100)
    stream_tag = getattr(args, "streamid", "publisher")
    queue_suffix = re.sub(r"[^A-Za-z0-9_]", "_", stream_tag) or "default"
    queue_name = f"publisher_red_queue_{queue_suffix}"
    fec_name = f"publisher_fec_{queue_suffix}"
    red_name = f"publisher_red_{queue_suffix}"
    setattr(args, "_publisher_redundancy_queue_name", queue_name)
    setattr(args, "_publisher_redundancy_fec_name", fec_name)
    setattr(args, "_publisher_redundancy_red_name", red_name)

    caps = (
        f"application/x-rtp,media=video,encoding-name=RED,payload={red_pt},clock-rate=90000"
    )
    fragment = (
        f" ! queue name={queue_name} max-size-buffers=6 max-size-time=60000000 leaky=upstream "
        f"! rtpulpfecenc name={fec_name} pt={fec_pt} percentage={fec_percentage} "
        f"! rtpredenc name={red_name} pt={red_pt} distance={red_distance} "
        f'! capssetter replace=false caps="{caps}" '
    )

    return fragment, {
        "red_pt": red_pt,
        "fec_pt": fec_pt,
        "red_distance": red_distance,
        "fec_percentage": fec_percentage,
        "queue_name": queue_name,
        "fec_name": fec_name,
        "red_name": red_name,
    }


def select_display_sink(default_sink: str = "autovideosink") -> str:
    """Choose the most appropriate local display sink."""
    forced_sink = os.environ.get("RN_FORCE_SINK")
    if forced_sink:
        printc(f"\n ! Forcing display sink via RN_FORCE_SINK={forced_sink}", "0AF")
        return forced_sink

    display_detected = check_drm_displays()
    if display_detected:
        printc('\nThere is at least one connected display.', "00F")
        if is_jetson_device():
            using_wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
            using_x11 = bool(os.environ.get("DISPLAY")) and not using_wayland
            if using_x11:
                if gst_element_available("ximagesink"):
                    printc(" ! Jetson desktop (X11) detected. Using ximagesink with XInput disabled.", "0AF")
                    return "ximagesink handle-events=false sync=false"
                if gst_element_available("gtksink"):
                    printc(" ! Jetson desktop (X11) detected. Using gtksink to embed in a GTK window.", "0AF")
                    return "gtksink sync=false"
                if gst_element_available("glimagesink"):
                    printc(" ! Jetson desktop (X11) detected. Using glimagesink for compositor compatibility.", "0AF")
                    return "glimagesink sync=false"
                if gst_element_available("xvimagesink"):
                    printc(" ! Jetson desktop (X11) detected. Using xvimagesink as fallback.", "0AF")
                    return "xvimagesink sync=false"
        return default_sink

    if is_jetson_device():
        preferred_order = []
        fb_resolution = get_framebuffer_resolution()
        overlay_properties = ""
        if fb_resolution:
            overlay_properties = (
                f" overlay=1 overlay-x=0 overlay-y=0 overlay-w={fb_resolution[0]} overlay-h={fb_resolution[1]}"
            )
        if gst_element_available("nvoverlaysink"):
            preferred_order.append(f"nvoverlaysink sync=false{overlay_properties}")
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and gst_element_available("nvdrmvideosink"):
            preferred_order.append("nvdrmvideosink sync=false")
        if gst_element_available("nv3dsink"):
            preferred_order.append("nv3dsink sync=false")

        if preferred_order:
            jetson_sink = preferred_order[0]
            sink_name = jetson_sink.split()[0]
            printc(f"\n ! No desktop compositor detected. Using Jetson-specific sink `{sink_name}` for direct HDMI output.", "0AF")
            return jetson_sink

    printc('\n ! No connected displays found. Will try to use glimagesink instead of autovideosink', "F60")
    return "glimagesink sync=true"

def replace_ssrc_and_cleanup_sdp(sdp): ## fix for audio-only gstreamer -> chrome
    def generate_ssrc():
        return str(random.randint(0, 0xFFFFFFFF))

    lines = sdp.split('\r\n')

    in_audio_section = False
    new_ssrc = generate_ssrc()

    for i in range(len(lines)):
        if lines[i].startswith('m=audio '):
            in_audio_section = True
        elif lines[i].startswith('m=') and not lines[i].startswith('m=audio '):
            in_audio_section = False
        if in_audio_section and lines[i].startswith('a=ssrc:'):
            lines[i] = re.sub(r'a=ssrc:\d+', f'a=ssrc:{new_ssrc}', lines[i])

    return '\r\n'.join(lines)

def fix_audio_ssrc_for_ohttp_gstreamer(sdp):
    """Fix audio SSRC issues for GStreamer 1.18 and earlier.

    GStreamer 1.18 has bugs where:
    1. ssrc=-1 in rtpopuspay becomes 0xFFFFFFFF (4294967295) in SDP
    2. RTX SSRCs may also have invalid values
    3. ssrc-group:FID may have mismatched SSRCs

    This function replaces all audio SSRCs with valid unique values.
    """
    def generate_valid_ssrc():
        # Generate SSRC that's not 0 and not 0xFFFFFFFF (-1)
        while True:
            ssrc = random.randint(1, 0xFFFFFFFE)
            return str(ssrc)

    lines = sdp.split('\r\n')
    in_audio_section = False
    audio_ssrc_map = {}  # old_ssrc -> new_ssrc

    # First pass: collect all audio SSRCs and generate replacements
    for line in lines:
        if line.startswith('m=audio '):
            in_audio_section = True
        elif line.startswith('m=') and not line.startswith('m=audio '):
            in_audio_section = False

        if in_audio_section:
            # Find SSRCs in a=ssrc: lines
            if line.startswith('a=ssrc:'):
                match = re.match(r'a=ssrc:(\d+)', line)
                if match:
                    old_ssrc = match.group(1)
                    if old_ssrc not in audio_ssrc_map:
                        audio_ssrc_map[old_ssrc] = generate_valid_ssrc()

            # Find SSRCs in a=ssrc-group:FID lines
            if line.startswith('a=ssrc-group:FID'):
                ssrcs = re.findall(r'\d+', line.split('FID')[1] if 'FID' in line else '')
                for old_ssrc in ssrcs:
                    if old_ssrc not in audio_ssrc_map:
                        audio_ssrc_map[old_ssrc] = generate_valid_ssrc()

    # Second pass: replace all SSRCs consistently
    result_lines = []
    in_audio_section = False

    for line in lines:
        if line.startswith('m=audio '):
            in_audio_section = True
        elif line.startswith('m=') and not line.startswith('m=audio '):
            in_audio_section = False

        if in_audio_section:
            new_line = line
            for old_ssrc, new_ssrc in audio_ssrc_map.items():
                # Replace in a=ssrc: lines
                new_line = re.sub(f'a=ssrc:{old_ssrc}\\b', f'a=ssrc:{new_ssrc}', new_line)
                # Replace in a=ssrc-group:FID lines
                new_line = re.sub(f'\\b{old_ssrc}\\b', new_ssrc, new_line) if 'ssrc-group' in new_line else new_line
            result_lines.append(new_line)
        else:
            result_lines.append(line)

    return '\r\n'.join(result_lines)

def strip_audio_from_sdp(sdp):
    """Remove the audio media section from SDP.

    GStreamer 1.18 creates phantom audio transceivers even when no audio
    pipeline is present. This can confuse Chrome which waits for audio data.
    """
    lines = sdp.split('\r\n')
    result_lines = []
    in_audio_section = False
    bundle_line_idx = None

    for i, line in enumerate(lines):
        if line.startswith('m=audio'):
            in_audio_section = True
            continue
        elif line.startswith('m=') and in_audio_section:
            in_audio_section = False

        if in_audio_section:
            continue

        # Track the BUNDLE line for later modification
        if line.startswith('a=group:BUNDLE'):
            bundle_line_idx = len(result_lines)

        result_lines.append(line)

    # Remove audio1 from BUNDLE group
    if bundle_line_idx is not None:
        bundle_line = result_lines[bundle_line_idx]
        # Remove audio1 from "a=group:BUNDLE video0 audio1 application2"
        bundle_line = re.sub(r'\s+audio\d+', '', bundle_line)
        result_lines[bundle_line_idx] = bundle_line

    return '\r\n'.join(result_lines)

def fix_audio_rtcp_fb_for_gstreamer(sdp):
    """Remove video-specific RTCP feedback attributes from audio section.

    GStreamer 1.18 incorrectly adds 'a=rtcp-fb:XX nack' and 'a=rtcp-fb:XX nack pli'
    to audio sections. These are video-specific (for packet loss/keyframe requests)
    and cause some WebRTC stacks to reject the audio description.
    """
    lines = sdp.split('\r\n')
    result_lines = []
    in_audio_section = False

    for line in lines:
        if line.startswith('m=audio'):
            in_audio_section = True
        elif line.startswith('m=') and not line.startswith('m=audio'):
            in_audio_section = False

        # Skip rtcp-fb nack lines in audio section (they're video-specific)
        if in_audio_section and line.startswith('a=rtcp-fb:'):
            if 'nack' in line.lower():
                continue  # Skip nack and nack pli lines for audio

        result_lines.append(line)

    return '\r\n'.join(result_lines)

def strip_audio_rtx_from_sdp(sdp: str) -> str:
    """Strip RTX from the audio m= section.

    Older GStreamer/webrtcbin builds may offer RTX on the audio m-line
    (rtx/48000 + ssrc-group:FID). Chrome/WebRTC implementations can reject such
    offers with errors like "Failed to add remote stream ssrc ... (audio)".
    """
    if not sdp or "m=audio" not in sdp:
        return sdp

    ends_with_crlf = sdp.endswith("\r\n")
    lines = sdp.split("\r\n")
    if ends_with_crlf and lines and lines[-1] == "":
        lines = lines[:-1]

    session_lines: List[str] = []
    media_sections: List[List[str]] = []
    current_section: Optional[List[str]] = None

    for line in lines:
        if line.startswith("m="):
            if current_section is None:
                current_section = [line]
            else:
                media_sections.append(current_section)
                current_section = [line]
        else:
            if current_section is None:
                session_lines.append(line)
            else:
                current_section.append(line)

    if current_section is not None:
        media_sections.append(current_section)

    updated_sections: List[List[str]] = []
    changed = False

    for section in media_sections:
        if not section:
            updated_sections.append(section)
            continue

        m_line = section[0]
        if not m_line.startswith("m=audio"):
            updated_sections.append(section)
            continue

        rtx_pts: Set[str] = set()
        rtx_ssrcs: Set[str] = set()

        for entry in section[1:]:
            if entry.startswith("a=rtpmap:") and " rtx/" in entry.lower():
                try:
                    pt = entry.split(":", 1)[1].split(None, 1)[0].strip()
                except Exception:
                    continue
                if pt:
                    rtx_pts.add(pt)
            if entry.startswith("a=ssrc-group:FID"):
                # Format: a=ssrc-group:FID <primary-ssrc> <rtx-ssrc> ...
                parts = entry.split()
                if len(parts) >= 3:
                    rtx_ssrcs.update(parts[2:])

        if not rtx_pts and not rtx_ssrcs:
            updated_sections.append(section)
            continue

        m_parts = m_line.split()
        if len(m_parts) >= 4 and rtx_pts:
            payloads = [pt for pt in m_parts[3:] if pt not in rtx_pts]
            if payloads != m_parts[3:]:
                m_line = " ".join(m_parts[:3] + payloads)
                changed = True

        filtered: List[str] = [m_line]
        for entry in section[1:]:
            entry_stripped = entry.strip()

            if rtx_pts and entry_stripped.startswith("a=rtpmap:"):
                try:
                    pt = entry_stripped.split(":", 1)[1].split(None, 1)[0].strip()
                except Exception:
                    pt = ""
                if pt in rtx_pts:
                    changed = True
                    continue

            if rtx_pts and entry_stripped.startswith("a=fmtp:"):
                try:
                    pt = entry_stripped.split(":", 1)[1].split(None, 1)[0].strip()
                except Exception:
                    pt = ""
                if pt in rtx_pts:
                    changed = True
                    continue

            if rtx_pts and entry_stripped.startswith("a=rtcp-fb:"):
                try:
                    pt = entry_stripped.split(":", 1)[1].split(None, 1)[0].strip()
                except Exception:
                    pt = ""
                if pt in rtx_pts:
                    changed = True
                    continue

            if entry_stripped.startswith("a=ssrc-group:FID"):
                # Drop RTX SSRC groups from audio.
                changed = True
                continue

            if rtx_ssrcs and entry_stripped.startswith("a=ssrc:"):
                match = re.match(r"a=ssrc:(\d+)\b", entry_stripped)
                if match and match.group(1) in rtx_ssrcs:
                    changed = True
                    continue

            filtered.append(entry)

        updated_sections.append(filtered)

    if not changed:
        return sdp

    output_lines: List[str] = []
    output_lines.extend(session_lines)
    for section in updated_sections:
        output_lines.extend(section)

    out = "\r\n".join(output_lines)
    if ends_with_crlf:
        out += "\r\n"
    return out

def generateHash(input_str, length=None):
    input_bytes = input_str.encode('utf-8')
    sha256_hash = hashlib.sha256(input_bytes).digest()
    if length:
        hash_hex = sha256_hash[:int(length // 2)].hex()
    else:
        hash_hex = sha256_hash.hex()
    return hash_hex

def convert_string_to_bytes(input_str):
    return input_str.encode('utf-8')

def to_hex_string(byte_data):
    return ''.join(f'{b:02x}' for b in byte_data)

def to_byte_array(hex_str):
    return bytes.fromhex(hex_str)

def generate_key(phrase):
    return hashlib.sha256(phrase.encode()).digest()

def pad_message(message):
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(message.encode('utf-8')) + padder.finalize()
    return padded_data

def unpad_message(padded_message):
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    try:
        data = unpadder.update(padded_message) + unpadder.finalize()
        return data
    except ValueError as e:
        print(f"Padding error: {e}")
        return None

def encrypt_message(message, phrase):
    try:
        message = json.dumps(message)
    except Exception as E:
        printwarn(get_exception_info(E))

    key = generate_key(phrase)
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    padded_message = pad_message(message)
    encrypted_message = encryptor.update(padded_message) + encryptor.finalize()
    return to_hex_string(encrypted_message), to_hex_string(iv)

def decrypt_message(encrypted_data, iv, phrase):
    key = generate_key(phrase)
    encrypted_data_bytes = to_byte_array(encrypted_data)
    iv_bytes = to_byte_array(iv)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv_bytes), backend=default_backend())
    decryptor = cipher.decryptor()
    try:
        decrypted_padded_message = decryptor.update(encrypted_data_bytes) + decryptor.finalize()
        unpadded_message = unpad_message(decrypted_padded_message)
        if unpadded_message is not None:
            return unpadded_message.decode('utf-8')
        else:
            return None
    except (UnicodeDecodeError, ValueError) as e:
        print(f"Error decoding message: {e}")
        return None


class WebServer:
    def __init__(self, port, client):
        self.port = port
        self.client = client
        self.app = web.Application()
        self.runner = None
        self.logs = []  # Store recent logs
        self.max_logs = 1000
        
        # Setup routes
        self.app.router.add_get('/', self.index)
        self.app.router.add_get('/api/stats', self.get_stats)
        self.app.router.add_get('/api/logs', self.get_logs)
        self.app.router.add_post('/api/control', self.control)
        self.app.router.add_get('/ws', self.websocket_handler)
        self.app.router.add_get('/api/system', self.get_system_stats)
        self.app.router.add_get('/api/devices', self.get_devices)
        self.app.router.add_get('/api/pipeline', self.get_pipeline_info)
        self.app.router.add_get('/api/ice', self.get_ice_stats)
        self.app.router.add_get('/api/hls', self.get_hls_streams)
        self.app.router.add_get('/hls/{filename}', self.serve_hls_file)
        self.app.router.add_static('/hls/', path='.', name='hls_static')
        
    async def index(self, request):
        html = r"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Raspberry Ninja - Web Interface</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: #1a1a1a;
                    color: #e0e0e0;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                }
                h1 {
                    color: #4CAF50;
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }
                .stats-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                    margin: 20px 0;
                }
                .recording-section {
                    background: #3a2a2a;
                    border: 2px solid #ff4444;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 20px 0;
                    grid-column: 1 / -1;
                }
                .recording-header {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    margin-bottom: 15px;
                }
                .recording-indicator {
                    width: 16px;
                    height: 16px;
                    background: #ff4444;
                    border-radius: 50%;
                    animation: pulse 1.5s infinite;
                }
                @keyframes pulse {
                    0% { opacity: 1; }
                    50% { opacity: 0.5; }
                    100% { opacity: 1; }
                }
                .stat-card {
                    background: #2a2a2a;
                    padding: 20px;
                    border-radius: 8px;
                    border: 1px solid #333;
                }
                .stat-label {
                    color: #888;
                    font-size: 0.9em;
                    margin-bottom: 5px;
                }
                .stat-value {
                    font-size: 1.8em;
                    font-weight: bold;
                    color: #4CAF50;
                }
                .logs {
                    background: #2a2a2a;
                    border: 1px solid #333;
                    border-radius: 8px;
                    padding: 20px;
                    height: 400px;
                    overflow-y: auto;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 0.9em;
                }
                .log-entry {
                    margin: 2px 0;
                    padding: 2px 0;
                }
                .controls {
                    margin: 20px 0;
                    display: flex;
                    gap: 10px;
                }
                button {
                    background: #4CAF50;
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 1em;
                }
                button:hover {
                    background: #45a049;
                }
                button:disabled {
                    background: #666;
                    cursor: not-allowed;
                }
                .status {
                    display: inline-block;
                    width: 10px;
                    height: 10px;
                    border-radius: 50%;
                    margin-right: 5px;
                }
                .status.connected { background: #4CAF50; }
                .status.disconnected { background: #f44336; }
                .quality-graph {
                    background: #2a2a2a;
                    border: 1px solid #333;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 20px 0;
                    height: 200px;
                    position: relative;
                }
                .graph-canvas {
                    width: 100%;
                    height: 100%;
                }
                .modal {
                    display: none;
                    position: fixed;
                    z-index: 1000;
                    left: 0;
                    top: 0;
                    width: 100%;
                    height: 100%;
                    background-color: rgba(0,0,0,0.8);
                }
                .modal-content {
                    background-color: #2a2a2a;
                    margin: 5% auto;
                    padding: 20px;
                    border: 1px solid #444;
                    border-radius: 8px;
                    width: 80%;
                    max-width: 800px;
                    max-height: 80vh;
                    overflow-y: auto;
                }
                .modal-close {
                    color: #aaa;
                    float: right;
                    font-size: 28px;
                    font-weight: bold;
                    cursor: pointer;
                }
                .modal-close:hover {
                    color: #fff;
                }
                pre {
                    background: #1a1a1a;
                    padding: 10px;
                    border-radius: 4px;
                    overflow-x: auto;
                    font-size: 0.9em;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Raspberry Ninja Web Interface</h1>
                
                <div class="stats-grid" id="stats">
                    <div class="stat-card">
                        <div class="stat-label">Status</div>
                        <div class="stat-value"><span class="status disconnected"></span>Connecting...</div>
                    </div>
                </div>
                
                <div class="controls">
                    <button onclick="toggleRecording()">Start Recording</button>
                    <button onclick="adjustBitrate()">Adjust Bitrate</button>
                    <button onclick="takeSnapshot()">Take Snapshot</button>
                    <button onclick="showDevices()">Show Devices</button>
                    <button onclick="showPipeline()">Show Pipeline</button>
                    <button onclick="showICEStats()">ICE Stats</button>
                    <button onclick="clearLogs()">Clear Logs</button>
                    <button onclick="downloadLogs()">Download Logs</button>
                </div>
                
                <div style="margin: 20px 0;">
                    <label style="margin-right: 10px;">Filter logs:</label>
                    <input type="text" id="logFilter" placeholder="Type to filter logs..." 
                           style="padding: 5px; background: #2a2a2a; border: 1px solid #444; color: #e0e0e0;"
                           onkeyup="filterLogs()">
                    <select id="logLevel" onchange="filterLogs()" 
                            style="padding: 5px; background: #2a2a2a; border: 1px solid #444; color: #e0e0e0; margin-left: 10px;">
                        <option value="all">All Levels</option>
                        <option value="error">Errors</option>
                        <option value="warning">Warnings</option>
                        <option value="info">Info</option>
                        <option value="success">Success</option>
                    </select>
                </div>
                
                <h2>Connection Quality</h2>
                <div class="quality-graph">
                    <canvas id="qualityGraph" class="graph-canvas"></canvas>
                </div>
                
                <h2>System Resources</h2>
                <div class="stats-grid" id="systemStats">
                    <div class="stat-card">
                        <div class="stat-label">Loading...</div>
                    </div>
                </div>
                
                <h2>HLS Streams</h2>
                <div class="stats-grid" id="hlsStreams">
                    <div class="stat-card">
                        <div class="stat-label">Loading...</div>
                    </div>
                </div>
                
                <div id="modalContainer"></div>
                
                <h2>HLS Player</h2>
                <div id="hlsPlayerSection" style="display: none; margin: 20px 0;">
                    <video id="hlsVideo" controls style="width: 100%; max-width: 800px; background: #000;"></video>
                    <div style="margin-top: 10px;">
                        <button onclick="closeHLSPlayer()" style="background: #f44336;">Close Player</button>
                        <button onclick="toggleHLSDebug()" style="background: #2196F3; margin-left: 10px;">Toggle Debug</button>
                        <span id="hlsPlayerStatus" style="margin-left: 20px;"></span>
                    </div>
                    <div style="margin-top: 15px; padding: 10px; background: #2a2a2a; border-radius: 4px;">
                        <div style="font-size: 0.9em; color: #888; margin-bottom: 5px;">HLS Manifest URL (for OBS, VLC, etc.):</div>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <input id="hlsManifestUrl" type="text" readonly style="flex: 1; padding: 8px; background: #1a1a1a; border: 1px solid #444; color: #e0e0e0; font-family: monospace; font-size: 0.9em;">
                            <button onclick="copyHLSUrl()" style="padding: 8px 15px; background: #4CAF50;">Copy URL</button>
                        </div>
                        <div id="copyStatus" style="margin-top: 5px; font-size: 0.8em; color: #4CAF50; display: none;">✓ Copied to clipboard!</div>
                    </div>
                </div>
                
                <h2>Live Logs</h2>
                <div class="logs" id="logs"></div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
            <script>
                let ws;
                let hls;
                
                function playHLSStream(url) {
                    const playerSection = document.getElementById('hlsPlayerSection');
                    const video = document.getElementById('hlsVideo');
                    const status = document.getElementById('hlsPlayerStatus');
                    const manifestInput = document.getElementById('hlsManifestUrl');
                    
                    // Generate full URL
                    const fullUrl = window.location.protocol + '//' + window.location.host + url;
                    manifestInput.value = fullUrl;
                    
                    // Reset copy status
                    document.getElementById('copyStatus').style.display = 'none';
                    
                    playerSection.style.display = 'block';
                    playerSection.scrollIntoView({ behavior: 'smooth' });
                    
                    if (hls) {
                        hls.destroy();
                    }
                    
                    if (Hls.isSupported()) {
                        hls = new Hls({
                            debug: true,  // Enable debug logging to console
                            enableWorker: true,
                            lowLatencyMode: true,
                            backBufferLength: 90,
                            liveSyncDurationCount: 3,        // For live streams
                            liveMaxLatencyDurationCount: 10, // Maximum live latency
                            manifestLoadingTimeOut: 10000,   // 10 second timeout
                            manifestLoadingMaxRetry: 3,      // Retry 3 times
                            fragLoadingTimeOut: 20000,       // 20 second timeout for fragments
                            fragLoadingMaxRetry: 6,          // Retry fragments 6 times
                            startLevel: -1,                  // Auto select quality
                            startFragPrefetch: true          // Prefetch next fragment
                        });
                        
                        hls.loadSource(fullUrl);
                        hls.attachMedia(video);
                        
                        hls.on(Hls.Events.MEDIA_ATTACHED, function () {
                            status.textContent = 'Loading stream...';
                            console.log('HLS: Media attached');
                        });
                        
                        hls.on(Hls.Events.MANIFEST_LOADING, function () {
                            status.textContent = 'Loading manifest...';
                            console.log('HLS: Loading manifest from:', fullUrl);
                        });
                        
                        hls.on(Hls.Events.MANIFEST_LOADED, function (event, data) {
                            status.textContent = 'Manifest loaded, parsing...';
                            console.log('HLS: Manifest loaded, details:', data);
                        });
                        
                        hls.on(Hls.Events.MANIFEST_PARSED, function (event, data) {
                            status.textContent = 'Stream loaded, playing...';
                            console.log('HLS: Manifest parsed, levels:', data);
                            video.play().catch(e => {
                                status.textContent = 'Click video to play (autoplay blocked)';
                                console.log('Autoplay failed:', e);
                            });
                        });
                        
                        hls.on(Hls.Events.LEVEL_LOADED, function (event, data) {
                            console.log('HLS: Level loaded, details:', data);
                        });
                        
                        hls.on(Hls.Events.FRAG_LOADING, function (event, data) {
                            console.log('HLS: Loading fragment:', data.frag.url);
                        });
                        
                        hls.on(Hls.Events.ERROR, function (event, data) {
                            console.error('HLS Error:', data);
                            if (data.fatal) {
                                switch(data.type) {
                                    case Hls.ErrorTypes.NETWORK_ERROR:
                                        status.textContent = 'Network Error: ' + data.details;
                                        console.error('Fatal network error encountered, trying to recover...');
                                        hls.startLoad();
                                        break;
                                    case Hls.ErrorTypes.MEDIA_ERROR:
                                        status.textContent = 'Media Error: ' + data.details;
                                        console.error('Fatal media error encountered, trying to recover...');
                                        hls.recoverMediaError();
                                        break;
                                    default:
                                        status.textContent = 'Error: ' + data.details;
                                        console.error('Fatal error, cannot recover');
                                        hls.destroy();
                                        break;
                                }
                            } else {
                                // Non-fatal errors
                                if (data.details === 'fragParsingError') {
                                    // Common with live streams, usually recovers automatically
                                    status.textContent = 'Buffering live stream...';
                                    console.log('Fragment parsing error (common with live streams), will retry...');
                                } else {
                                    status.textContent = 'Non-fatal error: ' + data.details;
                                }
                            }
                        });
                    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                        // Native HLS support (Safari)
                        video.src = fullUrl;
                        video.addEventListener('loadedmetadata', function() {
                            video.play().catch(e => {
                                status.textContent = 'Click video to play';
                            });
                        });
                    } else {
                        status.textContent = 'HLS not supported in this browser';
                    }
                }
                
                function copyHLSUrl() {
                    const manifestInput = document.getElementById('hlsManifestUrl');
                    const copyStatus = document.getElementById('copyStatus');
                    
                    manifestInput.select();
                    manifestInput.setSelectionRange(0, 99999); // For mobile devices
                    
                    try {
                        document.execCommand('copy');
                        copyStatus.style.display = 'block';
                        setTimeout(() => {
                            copyStatus.style.display = 'none';
                        }, 3000);
                    } catch (err) {
                        // Fallback for modern browsers
                        if (navigator.clipboard && navigator.clipboard.writeText) {
                            navigator.clipboard.writeText(manifestInput.value).then(() => {
                                copyStatus.style.display = 'block';
                                setTimeout(() => {
                                    copyStatus.style.display = 'none';
                                }, 3000);
                            }).catch(err => {
                                alert('Failed to copy: ' + err);
                            });
                        } else {
                            alert('Copy not supported. Please select and copy manually.');
                        }
                    }
                }
                
                function toggleHLSDebug() {
                    if (hls && hls.config) {
                        hls.config.debug = !hls.config.debug;
                        const status = document.getElementById('hlsPlayerStatus');
                        status.textContent = 'Debug mode: ' + (hls.config.debug ? 'ON' : 'OFF');
                        console.log('HLS.js debug mode:', hls.config.debug);
                    }
                }
                
                function closeHLSPlayer() {
                    const playerSection = document.getElementById('hlsPlayerSection');
                    const video = document.getElementById('hlsVideo');
                    
                    if (hls) {
                        hls.destroy();
                        hls = null;
                    }
                    
                    video.pause();
                    video.src = '';
                    playerSection.style.display = 'none';
                }
                
                function formatDuration(seconds) {
                    const hours = Math.floor(seconds / 3600);
                    const minutes = Math.floor((seconds % 3600) / 60);
                    const secs = seconds % 60;
                    const parts = [];
                    if (hours > 0) parts.push(hours + 'h');
                    if (minutes > 0) parts.push(minutes + 'm');
                    parts.push(secs + 's');
                    return parts.join(' ');
                }
                
                function connectWebSocket() {
                    ws = new WebSocket('ws://' + window.location.host + '/ws');
                    
                    ws.onmessage = (event) => {
                        const data = JSON.parse(event.data);
                        if (data.type === 'stats') {
                            updateStats(data.stats);
                        } else if (data.type === 'log') {
                            addLog(data.message);
                        }
                    };
                    
                    ws.onclose = () => {
                        setTimeout(connectWebSocket, 5000);
                    };
                }
                
                async function fetchStats() {
                    try {
                        const response = await fetch('/api/stats');
                        const stats = await response.json();
                        updateStats(stats);
                    } catch (error) {
                        console.error('Failed to fetch stats:', error);
                    }
                }
                
                async function fetchLogs() {
                    try {
                        const response = await fetch('/api/logs');
                        const logs = await response.json();
                        const logsDiv = document.getElementById('logs');
                        logsDiv.innerHTML = logs.map(log => 
                            '<div class="log-entry">' + log + '</div>'
                        ).join('');
                    } catch (error) {
                        console.error('Failed to fetch logs:', error);
                    }
                }
                
                function updateStats(stats) {
                    const statsDiv = document.getElementById('stats');
                    const viewerDetails = stats.viewer_details;
                    const recordingInfo = stats.recording;
                    delete stats.viewer_details;
                    delete stats.recording;
                    
                    let html = Object.entries(stats).map(([key, value]) => {
                        // Special formatting for certain fields
                        let displayValue = value;
                        let statusClass = '';
                        
                        if (key === 'status') {
                            statusClass = value === 'connected' ? 'connected' : 'disconnected';
                            displayValue = '<span class="status ' + statusClass + '"></span>' + value;
                        }
                        
                        return '<div class="stat-card">' +
                            '<div class="stat-label">' + key.replace(/_/g, ' ').toUpperCase() + '</div>' +
                            '<div class="stat-value">' + displayValue + '</div>' +
                            '</div>';
                    }).join('');
                    
                    // Add viewer details if any
                    if (viewerDetails && viewerDetails.length > 0) {
                        html += '<div class="stat-card" style="grid-column: span 2;">' +
                            '<div class="stat-label">VIEWER DETAILS</div>' +
                            '<div style="font-size: 0.9em; margin-top: 10px;">' +
                            viewerDetails.map(v => 
                                '<div style="margin: 5px 0;">' +
                                'Viewer ' + v.id + ': ' +
                                (v.has_data_channel ? 'YES' : 'NO') + ' Data Channel | ' +
                                'Ping: ' + v.ping +
                                '</div>'
                            ).join('') +
                            '</div></div>';
                    }
                    
                    // Add recording information if available
                    if (recordingInfo && recordingInfo.enabled) {
                        html += '</div>'; // Close stats-grid
                        html += '<div class="recording-section">' +
                            '<div class="recording-header">' +
                            '<div class="recording-indicator"></div>' +
                            '<h2 style="margin: 0; color: #ff4444;">RECORDING ACTIVE</h2>' +
                            '</div>' +
                            '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">' +
                            '<div><strong>Mode:</strong> ' + recordingInfo.mode.replace(/_/g, ' ').toUpperCase() + '</div>';
                        
                        if (recordingInfo.room_name) {
                            html += '<div><strong>Room:</strong> ' + recordingInfo.room_name + '</div>';
                        }
                        
                        if (recordingInfo.audio_enabled !== undefined) {
                            html += '<div><strong>Audio:</strong> ' + (recordingInfo.audio_enabled ? '✓ Enabled' : '✗ Disabled') + '</div>';
                        }
                        
                        // Only show active recordings count for single stream mode, not room recording
                        if (recordingInfo.mode === 'single_stream' && recordingInfo.active_recordings !== undefined) {
                            html += '<div><strong>Active Recordings:</strong> ' + recordingInfo.active_recordings + '</div>';
                        }
                        
                        html += '</div>'; // Close grid
                        
                        if (recordingInfo.note) {
                            html += '<div style="margin-top: 15px; padding: 10px; background: #1a1a1a; border-radius: 4px; font-style: italic;">' + recordingInfo.note + '</div>';
                        }
                        
                        if (recordingInfo.files && recordingInfo.files.length > 0) {
                            html += '<div style="margin-top: 15px;"><h3 style="margin-bottom: 10px;">Recording Files:</h3>';
                            html += '<div style="background: #1a1a1a; padding: 10px; border-radius: 4px; max-height: 200px; overflow-y: auto;">';
                            recordingInfo.files.forEach(f => {
                                html += '<div style="margin: 5px 0; font-family: monospace;">• ' + f + '</div>';
                            });
                            html += '</div></div>';
                        }
                        html += '</div>'; // Close recording section
                        html += '<div class="stats-grid">'; // Reopen stats-grid for consistency
                    }
                    
                    statsDiv.innerHTML = html;
                }
                
                let allLogs = [];
                
                function addLog(message) {
                    const logsDiv = document.getElementById('logs');
                    const logEntry = document.createElement('div');
                    logEntry.className = 'log-entry';
                    logEntry.textContent = message;
                    logEntry.setAttribute('data-raw', message);
                    
                    // Detect log level
                    if (message.includes('Error') || message.includes('error') || message.includes('Failed')) {
                        logEntry.setAttribute('data-level', 'error');
                    } else if (message.includes('Warning') || message.includes('warning')) {
                        logEntry.setAttribute('data-level', 'warning');
                    } else if (message.includes('success') || message.includes('Success')) {
                        logEntry.setAttribute('data-level', 'success');
                    } else {
                        logEntry.setAttribute('data-level', 'info');
                    }
                    
                    logsDiv.appendChild(logEntry);
                    logsDiv.scrollTop = logsDiv.scrollHeight;
                    
                    // Store in allLogs array
                    allLogs.push(message);
                    
                    // Keep only last 1000 logs
                    while (logsDiv.children.length > 1000) {
                        logsDiv.removeChild(logsDiv.firstChild);
                        allLogs.shift();
                    }
                    
                    // Apply current filter
                    filterLogs();
                }
                
                function clearLogs() {
                    document.getElementById('logs').innerHTML = '';
                    allLogs = [];
                }
                
                function filterLogs() {
                    const filterText = document.getElementById('logFilter').value.toLowerCase();
                    const filterLevel = document.getElementById('logLevel').value;
                    const logEntries = document.querySelectorAll('.log-entry');
                    
                    logEntries.forEach(entry => {
                        const text = entry.textContent.toLowerCase();
                        const level = entry.getAttribute('data-level');
                        
                        const matchesText = !filterText || text.includes(filterText);
                        const matchesLevel = filterLevel === 'all' || level === filterLevel;
                        
                        entry.style.display = (matchesText && matchesLevel) ? 'block' : 'none';
                    });
                }
                
                function downloadLogs() {
                    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
                    const filename = 'raspberry-ninja-logs-' + timestamp + '.txt';
                    const content = allLogs.join('\n');
                    
                    const blob = new Blob([content], { type: 'text/plain' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                }
                
                async function takeSnapshot() {
                    try {
                        const response = await fetch('/api/control', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({action: 'take_snapshot'})
                        });
                        const result = await response.json();
                        
                        if (result.status === 'success') {
                            // Download the snapshot
                            const a = document.createElement('a');
                            a.href = '/api/snapshot';
                            a.download = result.filename;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                            
                            addLog('[SNAPSHOT] ' + result.message);
                        } else {
                            alert('Error: ' + result.message);
                        }
                    } catch (error) {
                        alert('Failed to take snapshot: ' + error.message);
                    }
                }
                
                let isRecording = false;
                
                async function toggleRecording() {
                    try {
                        const response = await fetch('/api/control', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({action: 'toggle_recording'})
                        });
                        const result = await response.json();
                        
                        if (result.status === 'success') {
                            isRecording = result.recording;
                            const btn = event.target;
                            btn.textContent = isRecording ? 'Stop Recording' : 'Start Recording';
                            btn.style.background = isRecording ? '#f44336' : '#4CAF50';
                            
                            if (result.message) {
                                addLog('[RECORDING] ' + result.message);
                            }
                        } else {
                            alert('Error: ' + result.message);
                        }
                    } catch (error) {
                        alert('Failed to toggle recording: ' + error.message);
                    }
                }
                
                async function adjustBitrate() {
                    const bitrate = prompt('Enter new bitrate (kbps):', '2000');
                    if (bitrate) {
                        await fetch('/api/control', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({action: 'set_bitrate', value: parseInt(bitrate)})
                        });
                    }
                }
                
                // Initial fetch and setup
                fetchStats().then(() => {
                    // Check initial recording state from stats
                    fetch('/api/stats')
                        .then(r => r.json())
                        .then(stats => {
                            if (stats.recording === 'active') {
                                isRecording = true;
                                const btn = document.querySelector('button[onclick="toggleRecording()"]');
                                btn.textContent = 'Recording Active';
                                btn.style.background = '#666';
                                btn.disabled = true;
                                btn.title = 'Recording was enabled at startup with --save flag';
                            }
                        });
                });
                fetchLogs();
                connectWebSocket();
                
                // Quality tracking
                const qualityHistory = {
                    bitrate: [],
                    packetLoss: [],
                    timestamps: []
                };
                const maxHistoryPoints = 60; // 2 minutes at 2-second intervals
                
                function updateQualityGraph() {
                    const canvas = document.getElementById('qualityGraph');
                    const ctx = canvas.getContext('2d');
                    const width = canvas.width = canvas.offsetWidth;
                    const height = canvas.height = canvas.offsetHeight;
                    
                    // Clear canvas
                    ctx.fillStyle = '#1a1a1a';
                    ctx.fillRect(0, 0, width, height);
                    
                    if (qualityHistory.bitrate.length < 2) return;
                    
                    // Draw grid
                    ctx.strokeStyle = '#333';
                    ctx.lineWidth = 1;
                    for (let i = 0; i <= 4; i++) {
                        const y = (height / 4) * i;
                        ctx.beginPath();
                        ctx.moveTo(0, y);
                        ctx.lineTo(width, y);
                        ctx.stroke();
                    }
                    
                    // Draw bitrate line
                    ctx.strokeStyle = '#4CAF50';
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    
                    const maxBitrate = Math.max(...qualityHistory.bitrate, 1);
                    qualityHistory.bitrate.forEach((bitrate, i) => {
                        const x = (i / (maxHistoryPoints - 1)) * width;
                        const y = height - (bitrate / maxBitrate) * height * 0.9;
                        if (i === 0) ctx.moveTo(x, y);
                        else ctx.lineTo(x, y);
                    });
                    ctx.stroke();
                    
                    // Draw labels
                    ctx.fillStyle = '#888';
                    ctx.font = '12px monospace';
                    ctx.fillText(maxBitrate + ' kbps', 5, 15);
                    ctx.fillText('0 kbps', 5, height - 5);
                    ctx.fillText('2 min ago', 5, height - 20);
                    ctx.fillText('now', width - 30, height - 20);
                }
                
                async function fetchSystemStats() {
                    try {
                        const response = await fetch('/api/system');
                        const stats = await response.json();
                        
                        if (!stats.error) {
                            const systemDiv = document.getElementById('systemStats');
                            systemDiv.innerHTML = Object.entries(stats).map(([key, value]) => 
                                '<div class="stat-card">' +
                                '<div class="stat-label">' + key.replace(/_/g, ' ').toUpperCase() + '</div>' +
                                '<div class="stat-value">' + value + '</div>' +
                                '</div>'
                            ).join('');
                        }
                    } catch (error) {
                        console.error('Failed to fetch system stats:', error);
                    }
                }
                
                async function fetchHLSStreams() {
                    try {
                        const response = await fetch('/api/hls');
                        const streams = await response.json();
                        
                        const hlsDiv = document.getElementById('hlsStreams');
                        
                        if (streams.length === 0) {
                            hlsDiv.innerHTML = '<div class="stat-card" style="grid-column: span 3;">' +
                                '<div class="stat-label">NO HLS STREAMS</div>' +
                                '<div class="stat-value">No .m3u8 files found</div>' +
                                '</div>';
                            return;
                        }
                        
                        hlsDiv.innerHTML = streams.map(stream => {
                            let status;
                            if (stream.status === 'recording') {
                                status = '<span style="color: #ff4444;">● RECORDING</span>';
                            } else if (stream.status === 'live') {
                                status = '<span style="color: #ff8800;">● LIVE</span>';
                            } else if (stream.status === 'complete' && stream.is_complete) {
                                status = '<span style="color: #4CAF50;">✓ Complete</span>';
                            } else if (stream.status === 'incomplete') {
                                status = '<span style="color: #ff8800;">⚠️ Incomplete (no ENDLIST)</span>';
                            } else if (!stream.has_segments) {
                                status = '<span style="color: #ff4444;">❌ Empty/Invalid</span>';
                            } else {
                                status = '<span style="color: #999;">◐ Unknown</span>';
                            }
                            
                            const modified = new Date(stream.modified * 1000).toLocaleString();
                            
                            return '<div class="stat-card" style="grid-column: span 3; cursor: pointer;" onclick="playHLSStream(\'' + stream.url + '\')">' +
                                '<div style="display: flex; justify-content: space-between; align-items: center;">' +
                                '<div>' +
                                '<div class="stat-label">Stream: ' + (stream.stream_id || 'Unknown') + ' | Room: ' + (stream.room || 'Unknown') + '</div>' +
                                '<div class="stat-value" style="font-size: 0.9em;">' + stream.filename + '</div>' +
                                '<div style="margin-top: 5px; font-size: 0.8em; color: #888;">' +
                                'Segments: ' + stream.segment_count + ' | Modified: ' + modified +
                                '</div>' +
                                '</div>' +
                                '<div style="text-align: right;">' +
                                status +
                                '<div style="margin-top: 5px;">' +
                                '<button onclick="event.stopPropagation(); playHLSStream(\'' + stream.url + '\')" style="padding: 5px 10px; font-size: 0.8em;">Play</button>' +
                                '</div>' +
                                '</div>' +
                                '</div>' +
                                '</div>';
                        }).join('');
                    } catch (error) {
                        console.error('Failed to fetch HLS streams:', error);
                    }
                }
                
                
                // Update fetchStats to track quality
                const originalFetchStats = fetchStats;
                fetchStats = async function() {
                    await originalFetchStats();
                    
                    // Extract bitrate from stats for graph
                    try {
                        const response = await fetch('/api/stats');
                        const stats = await response.json();
                        const bitrateMatch = stats.bitrate.match(/(\d+)/);
                        if (bitrateMatch) {
                            const bitrate = parseInt(bitrateMatch[1]);
                            qualityHistory.bitrate.push(bitrate);
                            qualityHistory.timestamps.push(Date.now());
                            
                            // Trim old data
                            if (qualityHistory.bitrate.length > maxHistoryPoints) {
                                qualityHistory.bitrate.shift();
                                qualityHistory.timestamps.shift();
                            }
                            
                            updateQualityGraph();
                        }
                    } catch (error) {
                        // Ignore errors
                    }
                };
                
                // Modal functions
                function showModal(title, content) {
                    const modal = document.createElement('div');
                    modal.className = 'modal';
                    modal.style.display = 'block';
                    modal.innerHTML = '<div class="modal-content">' +
                        '<span class="modal-close" onclick="this.parentElement.parentElement.remove()">&times;</span>' +
                        '<h2>' + title + '</h2>' +
                        content +
                        '</div>';
                    document.getElementById('modalContainer').appendChild(modal);
                    
                    // Close on outside click
                    modal.onclick = function(event) {
                        if (event.target === modal) {
                            modal.remove();
                        }
                    };
                }
                
                async function showDevices() {
                    try {
                        const response = await fetch('/api/devices');
                        const devices = await response.json();
                        
                        let content = '<h3>Video Devices</h3>';
                        if (devices.video && devices.video.length > 0) {
                            content += '<ul>';
                            devices.video.forEach(dev => {
                                content += '<li><strong>' + dev.name + '</strong><br>';
                                content += 'Path: ' + dev.path + '<br>';
                                content += 'Class: ' + dev.class + '</li>';
                            });
                            content += '</ul>';
                        } else {
                            content += '<p>No video devices found</p>';
                        }
                        
                        content += '<h3>Audio Devices</h3>';
                        if (devices.audio && devices.audio.length > 0) {
                            content += '<ul>';
                            devices.audio.forEach(dev => {
                                content += '<li>' + dev.name + '</li>';
                            });
                            content += '</ul>';
                        } else {
                            content += '<p>No audio devices found</p>';
                        }
                        
                        showModal('Available Devices', content);
                    } catch (error) {
                        alert('Failed to fetch devices: ' + error.message);
                    }
                }
                
                async function showPipeline() {
                    try {
                        const response = await fetch('/api/pipeline');
                        const pipeline = await response.json();
                        
                        let content = '<h3>Pipeline State: ' + pipeline.pipeline_state + '</h3>';
                        content += '<h3>Pipeline Configuration</h3>';
                        content += '<pre>' + pipeline.pipeline_string.replace(/!/g, '!\n    ') + '</pre>';
                        
                        if (pipeline.elements && pipeline.elements.length > 0) {
                            content += '<h3>Pipeline Elements (' + pipeline.elements.length + ')</h3>';
                            content += '<ul>';
                            pipeline.elements.forEach(elem => {
                                content += '<li>' + elem.name + ' (' + elem.type + ')</li>';
                            });
                            content += '</ul>';
                        }
                        
                        showModal('Pipeline Information', content);
                    } catch (error) {
                        alert('Failed to fetch pipeline info: ' + error.message);
                    }
                }
                
                async function showICEStats() {
                    try {
                        const response = await fetch('/api/ice');
                        const ice = await response.json();
                        
                        let content = '<h3>ICE Configuration</h3>';
                        content += '<p><strong>STUN Server:</strong> ' + ice.stun_server + '</p>';
                        content += '<p><strong>TURN Server:</strong> ' + (ice.turn_server || 'Not configured') + '</p>';
                        
                        if (ice.connections && ice.connections.length > 0) {
                            content += '<h3>Active Connections</h3>';
                            ice.connections.forEach(conn => {
                                content += '<div style="margin: 10px 0; padding: 10px; background: #1a1a1a; border-radius: 4px;">';
                                content += '<strong>Viewer ' + conn.viewer_id + '</strong><br>';
                                content += 'ICE State: ' + conn.ice_connection_state + '<br>';
                                content += 'Gathering: ' + conn.ice_gathering_state + '<br>';
                                content += 'Signaling: ' + conn.signaling_state;
                                content += '</div>';
                            });
                        } else {
                            content += '<p>No active connections</p>';
                        }
                        
                        showModal('ICE Connection Statistics', content);
                    } catch (error) {
                        alert('Failed to fetch ICE stats: ' + error.message);
                    }
                }
                
                // Refresh stats every 2 seconds
                setInterval(fetchStats, 2000);
                setInterval(fetchSystemStats, 5000);
                setInterval(fetchHLSStreams, 3000);
                fetchSystemStats();
                fetchHLSStreams();
            </script>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
    
    async def get_stats(self, request):
        # Get real-time stats from the first connected client
        current_bitrate = 0
        packet_loss = 0.0
        video_bytes = 0
        audio_bytes = 0
        
        if self.client.clients:
            # Get stats from the first connected client
            for uuid, client_data in self.client.clients.items():
                if '_last_bitrate_sent' in client_data:
                    current_bitrate = client_data.get('_last_bitrate_sent', 0)
                if '_last_packet_loss' in client_data:
                    packet_loss = client_data.get('_last_packet_loss', 0.0)
                if '_last_video_bytes' in client_data:
                    video_bytes = client_data.get('_last_video_bytes', 0)
                if '_last_audio_bytes' in client_data:
                    audio_bytes = client_data.get('_last_audio_bytes', 0)
                break  # Just get from first client
        
        stats = {
            'status': 'connected' if len(self.client.clients) > 0 else 'idle',
            'viewers': len(self.client.clients),
            'configured_bitrate': f"{self.client.bitrate} kbps",
            'current_bitrate': f"{current_bitrate} kbps" if current_bitrate > 0 else "0 kbps",
            'max_bitrate': f"{self.client.max_bitrate} kbps",
            'packet_loss': f"{packet_loss:.2%}" if packet_loss > 0 else "0%",
            'stream_id': self.client.stream_id or 'N/A',
            'room': self.client.room_name or 'N/A',
            'multiviewer': 'enabled' if self.client.multiviewer else 'disabled',
            'pipeline_state': 'active' if self.client.pipe else 'inactive',
            'audio': 'disabled' if self.client.noaudio else 'enabled',
            'video': 'disabled' if self.client.novideo else 'enabled'
        }
        
        # Enhanced recording information
        recording_info = {
            'enabled': False,
            'mode': 'none',
            'active_recordings': 0,
            'files': []
        }
        
        # Check record_room first as it takes priority
        if self.client.record_room:
            recording_info['enabled'] = True
            recording_info['mode'] = 'room_recording'
            recording_info['room_name'] = self.client.room_name or 'N/A'
            recording_info['audio_enabled'] = not self.client.noaudio
            # Note: Detailed subprocess tracking would require additional implementation
            recording_info['note'] = 'Recording all streams in room to separate files'
        elif self.client.record:
            recording_info['enabled'] = True
            recording_info['mode'] = 'single_stream'
            if hasattr(self.client, 'recording_files'):
                recording_info['files'] = self.client.recording_files
                recording_info['active_recordings'] = len(self.client.recording_files)
        
        stats['recording'] = recording_info
        
        # Add codec information
        if self.client.h264:
            stats['video_codec'] = 'H.264'
        elif self.client.vp8:
            stats['video_codec'] = 'VP8'
        elif self.client.av1:
            stats['video_codec'] = 'AV1'
        else:
            stats['video_codec'] = 'Auto'
        
        # Add viewer-specific stats with more detail
        if self.client.clients:
            viewer_list = []
            for uuid, client_data in self.client.clients.items():
                viewer_info = {
                    'id': uuid[:8],
                    'status': 'connected',
                    'has_data_channel': bool(client_data.get('send_channel')),
                    'ping': client_data.get('ping', 0)
                }
                viewer_list.append(viewer_info)
            stats['viewer_details'] = viewer_list
        
        return web.json_response(stats)
    
    async def get_logs(self, request):
        return web.json_response(self.logs[-100:])  # Return last 100 logs
    
    async def control(self, request):
        try:
            data = await request.json()
            action = data.get('action')
            
            if action == 'set_bitrate':
                new_bitrate = data.get('value')
                if new_bitrate and 100 <= new_bitrate <= 50000:
                    self.client.bitrate = new_bitrate
                    self.client.max_bitrate = new_bitrate
                    # Update all active encoders
                    for client_data in self.client.clients.values():
                        self.client.set_encoder_bitrate(client_data, new_bitrate)
                    return web.json_response({'status': 'success', 'bitrate': new_bitrate})
            
            elif action == 'toggle_recording':
                # Check if we can record
                if self.client.streamin:
                    return web.json_response({
                        'status': 'error', 
                        'message': 'Cannot record while in viewer mode'
                    })
                
                if not self.client.pipe:
                    return web.json_response({
                        'status': 'error', 
                        'message': 'No active pipeline to record'
                    })
                
                # Check if recording was enabled at startup
                if self.client.save_file:
                    return web.json_response({
                        'status': 'info',
                        'recording': True,
                        'message': 'Recording is already active (enabled with --save flag)'
                    })
                else:
                    return web.json_response({
                        'status': 'info',
                        'recording': False,
                        'message': 'Recording must be enabled at startup with --save flag'
                    })
            
            elif action == 'take_snapshot':
                # Take a snapshot of the current frame
                if not self.client.pipe:
                    return web.json_response({
                        'status': 'error',
                        'message': 'No active pipeline'
                    })
                
                timestamp = int(time.time())
                filename = f"snapshot_{self.client.stream_id}_{timestamp}.jpg"
                
                # For now, return a message that this feature requires pipeline modification
                # In a real implementation, we'd use a valve element and jpegenc
                return web.json_response({
                    'status': 'info',
                    'message': 'Snapshot feature coming soon!',
                    'filename': filename
                })
            
            return web.json_response({'status': 'error', 'message': 'Invalid action'})
        except Exception as e:
            return web.json_response({'status': 'error', 'message': str(e)})
    
    async def websocket_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        # TODO: Implement real-time updates via websocket
        
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                # Handle incoming websocket messages
                pass
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print(f'WebSocket error: {ws.exception()}')
        
        return ws
    
    def add_log(self, message):
        """Add a log message to the buffer"""
        timestamp = time.strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
    
    async def get_system_stats(self, request):
        """Get system resource usage"""
        try:
            import psutil
            
            # Get CPU and memory usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            
            # Get process-specific stats
            process = psutil.Process()
            process_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            stats = {
                'cpu_percent': f"{cpu_percent:.1f}%",
                'memory_percent': f"{memory.percent:.1f}%",
                'memory_used': f"{memory.used / 1024 / 1024 / 1024:.1f} GB",
                'memory_total': f"{memory.total / 1024 / 1024 / 1024:.1f} GB",
                'process_memory': f"{process_memory:.1f} MB",
                'uptime': f"{int(time.time() - process.create_time())} seconds"
            }
            
            # Add GStreamer pipeline stats if available
            if self.client.pipe:
                clock = self.client.pipe.get_clock()
                if clock:
                    pipeline_time = clock.get_time() / Gst.SECOND
                    stats['pipeline_time'] = f"{pipeline_time:.1f} seconds"
                    
            return web.json_response(stats)
            
        except ImportError:
            return web.json_response({
                'error': 'psutil not installed',
                'message': 'Install psutil for system stats: pip install psutil'
            })
        except Exception as e:
            return web.json_response({'error': str(e)})
    
    async def get_devices(self, request):
        """Get available video and audio devices"""
        devices = {'video': [], 'audio': []}
        
        try:
            # Get video devices
            monitor = Gst.DeviceMonitor.new()
            monitor.add_filter("Video/Source", None)
            monitor.start()
            
            for device in monitor.get_devices():
                props = device.get_properties()
                device_info = {
                    'name': device.get_display_name(),
                    'path': props.get_string('device.path') if props else 'Unknown',
                    'class': props.get_string('device.class') if props else 'Unknown'
                }
                devices['video'].append(device_info)
            
            monitor.stop()
            
            # Get audio devices using ALSA
            try:
                import subprocess
                result = subprocess.run(['arecord', '-l'], capture_output=True, text=True)
                if result.returncode == 0:
                    lines = result.stdout.split('\n')
                    for line in lines:
                        if 'card' in line:
                            devices['audio'].append({'name': line.strip()})
            except:
                devices['audio'].append({'name': 'Default audio device'})
                
        except Exception as e:
            devices['error'] = str(e)
            
        return web.json_response(devices)
    
    async def get_pipeline_info(self, request):
        """Get current pipeline information"""
        info = {
            'pipeline_state': 'inactive',
            'pipeline_string': self.client.pipeline if hasattr(self.client, 'pipeline') else 'Not available',
            'elements': []
        }
        
        if self.client.pipe:
            state = self.client.pipe.get_state(0)[1]
            info['pipeline_state'] = state.value_name
            
            # Get pipeline elements
            it = self.client.pipe.iterate_elements()
            while True:
                result, elem = it.next()
                if result != Gst.IteratorResult.OK:
                    break
                info['elements'].append({
                    'name': elem.get_name(),
                    'type': elem.__class__.__name__
                })
                
        return web.json_response(info)
    
    async def get_ice_stats(self, request):
        """Get ICE connection statistics"""
        ice_stats = {
            'connections': [],
            'stun_server': 'stun://stun.cloudflare.com:3478',
            'turn_server': None
        }
        
        for uuid, client_data in self.client.clients.items():
            if client_data.get('webrtc'):
                conn_info = {
                    'viewer_id': uuid[:8],
                    'ice_connection_state': 'unknown',
                    'ice_gathering_state': 'unknown',
                    'signaling_state': 'unknown'
                }
                
                try:
                    webrtc = client_data['webrtc']
                    conn_info['ice_connection_state'] = webrtc.get_property('ice-connection-state').value_name
                    conn_info['ice_gathering_state'] = webrtc.get_property('ice-gathering-state').value_name
                    conn_info['signaling_state'] = webrtc.get_property('signaling-state').value_name
                except:
                    pass
                    
                ice_stats['connections'].append(conn_info)
                
        return web.json_response(ice_stats)
    
    async def get_hls_streams(self, request):
        """Get list of available HLS streams"""
        import glob
        hls_streams = []
        
        # Find all .m3u8 files in current directory
        for playlist in glob.glob("*.m3u8"):
            # Get file info
            stat = os.stat(playlist)
            
            # Extract stream info from filename
            # Format: room_streamid_timestamp.m3u8
            parts = playlist.replace('.m3u8', '').split('_')
            
            stream_info = {
                'filename': playlist,
                'url': f'/hls/{playlist}',
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'segments': []
            }
            
            # Try to parse room and stream ID
            if len(parts) >= 3:
                stream_info['room'] = parts[0]
                stream_info['stream_id'] = parts[1]
                stream_info['timestamp'] = parts[2]
            
            # Check if playlist has EXT-X-ENDLIST (is complete)
            try:
                with open(playlist, 'r') as f:
                    content = f.read()
                    stream_info['is_complete'] = '#EXT-X-ENDLIST' in content
                    stream_info['has_segments'] = '#EXTINF:' in content
            except:
                stream_info['is_complete'] = False
                stream_info['has_segments'] = False
            
            # Count segments
            base_name = playlist.replace('.m3u8', '')
            segments = glob.glob(f"{base_name}_*.ts")
            stream_info['segment_count'] = len(segments)
            
            # Check if still recording (recently modified)
            import time
            current_time = time.time()
            
            # Check both playlist and most recent segment modification times
            time_since_playlist_modified = current_time - stat.st_mtime
            
            # Find most recent segment modification time
            most_recent_segment_time = 0
            if segments:
                for segment in segments:
                    sink = None
                    try:
                        seg_mtime = os.stat(segment).st_mtime
                        if seg_mtime > most_recent_segment_time:
                            most_recent_segment_time = seg_mtime
                    except:
                        pass
            
            # Use the most recent modification time (playlist or segment)
            most_recent_activity = max(stat.st_mtime, most_recent_segment_time) if most_recent_segment_time else stat.st_mtime
            time_since_activity = current_time - most_recent_activity
            
            # Determine status based on activity and completion
            if time_since_activity < 10:  # Activity in last 10 seconds
                stream_info['status'] = 'recording'
            elif time_since_activity < 60 and not stream_info['is_complete']:  # Activity in last minute and no ENDLIST
                stream_info['status'] = 'live'
            elif not stream_info['is_complete'] and stream_info['has_segments']:
                # Has segments but no ENDLIST and no recent activity
                stream_info['status'] = 'incomplete'
            else:
                stream_info['status'] = 'complete'
                
            hls_streams.append(stream_info)
            
        # Sort by modification time (newest first)
        hls_streams.sort(key=lambda x: x['modified'], reverse=True)
        
        return web.json_response(hls_streams)
    
    async def serve_hls_file(self, request):
        """Serve HLS files with proper headers"""
        filename = request.match_info['filename']
        
        # Security check - only allow .m3u8 and .ts files
        if not (filename.endswith('.m3u8') or filename.endswith('.ts')):
            return web.Response(status=403, text='Forbidden')
            
        # Check if file exists
        if not os.path.exists(filename):
            return web.Response(status=404, text='Not Found')
            
        # Set appropriate content type
        if filename.endswith('.m3u8'):
            content_type = 'application/vnd.apple.mpegurl'
            # Don't cache playlists
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
        else:  # .ts files
            content_type = 'video/mp2t'
            # Cache segments
            headers = {
                'Cache-Control': 'public, max-age=3600',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
        # Read and serve file
        try:
            with open(filename, 'rb') as f:
                content = f.read()
            return web.Response(body=content, content_type=content_type, headers=headers)
        except Exception as e:
            return web.Response(status=500, text=str(e))
    
    async def start(self):
        """Start the web server"""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '0.0.0.0', self.port)
        await site.start()
        printc(f"🌐 Web interface started on http://0.0.0.0:{self.port}", "0F0")
        printc(f"   └─ Access from browser: http://localhost:{self.port}", "0F0")
    
    async def start_recording(self):
        """Start recording the stream to disk"""
        # For now, return a message that recording must be enabled at startup
        # Dynamic recording would require significant pipeline modifications
        return None
    
    async def stop_recording(self):
        """Stop recording and clean up"""
        # Not implemented for dynamic recording
        return False
    
    async def stop(self):
        """Stop the web server"""
        if self.runner:
            try:
                await asyncio.wait_for(self.runner.cleanup(), timeout=2.0)
                printc("🌐 Web server stopped", "77F")
            except asyncio.TimeoutError:
                printwarn("Web server cleanup timed out")
            except Exception as e:
                printwarn(f"Error stopping web server: {e}")
            finally:
                self.runner = None

class WebRTCSubprocessManager:
    """Manages WebRTC subprocesses with IPC communication"""
    
    def __init__(self, stream_id: str, config: Dict[str, Any]):
        self.stream_id = stream_id
        self.config = config
        self.process = None
        self.stdin = None
        self.stdout = None
        self.reader_task = None
        self.session_id = None
        self.message_handlers = {}
        self.running = False
        
    async def start(self):
        """Start the WebRTC subprocess"""
        # Prepare configuration
        config = {
            'stream_id': self.stream_id,
            'mode': self.config.get('mode', 'view'),
            'room': self.config.get('room'),
            'record_file': self.config.get('record_file'),
            'pipeline': self.config.get('pipeline', ''),
            'stun_server': self.config.get('stun_server', 'stun://stun.l.google.com:19302'),
            'turn_server': self.config.get('turn_server'),
            'ice_transport_policy': self.config.get('ice_transport_policy', 'all'),
            'bitrate': self.config.get('bitrate', 2500),
            'record_audio': self.config.get('record_audio', False),  # Pass audio recording flag
            'use_hls': self.config.get('use_hls', False),  # Pass HLS flag
            'use_splitmuxsink': self.config.get('use_splitmuxsink', False),  # Pass splitmuxsink flag
            'room_ndi': self.config.get('room_ndi', False),  # Pass NDI mode flag
            'ndi_name': self.config.get('ndi_name'),  # Pass NDI stream name
            'ndi_direct': self.config.get('ndi_direct', True),  # Default to direct mode
            'password': self.config.get('password'),  # Pass password for decryption
            'salt': self.config.get('salt', ''),  # Pass salt for decryption
        }
        
        # Start subprocess
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Choose subprocess script based on recording format
        # Choose subprocess based on configuration
        if self.config.get('test_mode', False):
            # Use test subprocess
            printc(f"[{self.stream_id}] Using test subprocess with mux_format={self.config.get('mux_format', 'webm')}", "0F0")
            subprocess_script = os.path.join(script_dir, 'webrtc_subprocess_test.py')
        elif self.config.get('use_mkv', False):
            # Use MKV subprocess only if explicitly requested
            printc(f"[{self.stream_id}] Using MKV recording with audio/video muxing", "0F0")
            subprocess_script = os.path.join(script_dir, 'webrtc_subprocess_mkv.py')
        elif self.config.get('use_hls', False):
            # HLS recording
            printc(f"[{self.stream_id}] Using HLS recording format", "0F0")
            subprocess_script = os.path.join(script_dir, 'webrtc_subprocess_glib.py')
        else:
            printc(f"[{self.stream_id}] Using standard WebM/MP4 recording", "0F0")
            subprocess_script = os.path.join(script_dir, 'webrtc_subprocess_glib.py')
        cmd = [sys.executable, subprocess_script]
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        self.stdin = self.process.stdin
        self.stdout = self.process.stdout
        self.running = True
        
        # Send configuration as first message (expected by subprocess)
        config_line = json.dumps(config) + '\n'
        self.stdin.write(config_line.encode())
        await self.stdin.drain()
        
        # Start reading messages
        self.reader_task = asyncio.create_task(self._read_messages())
        self.stderr_task = asyncio.create_task(self._read_stderr())
        
        # Wait for ready signal
        ready_event = asyncio.Event()
        self.message_handlers['ready'] = lambda msg: ready_event.set()
        
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=5.0)
            printc(f"[{self.stream_id}] Subprocess ready", "0F0")
            return True
        except asyncio.TimeoutError:
            printc(f"[{self.stream_id}] Subprocess failed to start", "F00")
            await self.stop()
            return False
            
    async def send_message(self, msg: Dict[str, Any]):
        """Send message to subprocess"""
        if self.stdin and not self.stdin.is_closing():
            data = json.dumps(msg) + '\n'
            self.stdin.write(data.encode())
            await self.stdin.drain()
            
    async def _read_messages(self):
        """Read messages from subprocess"""
        while self.running and self.stdout:
            try:
                line = await self.stdout.readline()
                if not line:
                    break
                    
                msg = json.loads(line.decode().strip())
                await self._handle_message(msg)
                
            except json.JSONDecodeError:
                continue
            except Exception as e:
                printc(f"[{self.stream_id}] Error reading message: {e}", "F00")
                
    async def _read_stderr(self):
        """Read stderr from subprocess"""
        while self.running and self.process and self.process.stderr:
            try:
                line = await self.process.stderr.readline()
                if not line:
                    break
                error_msg = line.decode().strip()
                if error_msg:
                    printc(f"[{self.stream_id}] STDERR: {error_msg}", "F70")
            except Exception as e:
                printc(f"[{self.stream_id}] Error reading stderr: {e}", "F00")
                
    async def _handle_message(self, msg: Dict[str, Any]):
        """Handle message from subprocess"""
        msg_type = msg.get('type')
        
        # Built-in handlers
        if msg_type == 'log':
            level = msg.get('level', 'info')
            message = msg.get('message', '')
            if level == 'error':
                printc(message, "F00")
            elif level == 'warning':
                printc(message, "FF0")
            else:
                printc(message, "77F")
                
        elif msg_type in self.message_handlers:
            handler = self.message_handlers[msg_type]
            if asyncio.iscoroutinefunction(handler):
                await handler(msg)
            else:
                handler(msg)
            
    def on_message(self, msg_type: str, handler):
        """Register message handler"""
        self.message_handlers[msg_type] = handler
        
    async def stop(self):
        """Stop the subprocess"""
        self.running = False
        
        # Send stop message
        await self.send_message({"type": "stop"})
        
        # Cancel reader tasks
        if self.reader_task:
            self.reader_task.cancel()
            try:
                await self.reader_task
            except asyncio.CancelledError:
                pass
                
        if hasattr(self, 'stderr_task') and self.stderr_task:
            self.stderr_task.cancel()
            try:
                await self.stderr_task
            except asyncio.CancelledError:
                pass
                
        # Terminate process
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
                
        printc(f"[{self.stream_id}] Subprocess stopped", "77F")


class WebRTCClient:
    def _get_gst_property_if_available(self, element, prop_name: str) -> Tuple[Any, bool]:
        """Try to read a GStreamer property; return (value, available_flag)."""
        try:
            return element.get_property(prop_name), True
        except Exception:
            pass

        props = getattr(element, "props", None)
        if props:
            attr_name = prop_name.replace("-", "_")
            if hasattr(props, attr_name):
                try:
                    return getattr(props, attr_name), True
                except Exception:
                    pass
        return None, False

    def _set_gst_property_if_available(self, element, prop_name: str, value: Any) -> bool:
        """Attempt to set a GStreamer property while tolerating missing bindings."""
        try:
            element.set_property(prop_name, value)
            return True
        except Exception:
            pass

        props = getattr(element, "props", None)
        if props:
            attr_name = prop_name.replace("-", "_")
            if hasattr(props, attr_name):
                try:
                    setattr(props, attr_name, value)
                    return True
                except Exception:
                    pass
        return False

    def _apply_loss_controls(
        self,
        client: Dict[str, Any],
        trans,
        *,
        label: str = "transceiver",
        force_fec: bool = False,
        force_rtx: bool = False,
        announce: bool = True,
    ) -> bool:
        """Configure FEC/RTX/NACK on a transceiver, handling legacy and modern APIs."""
        webrtc = client.get("webrtc")
        fec_applied = False
        redundancy_allowed = not self.nored
        auto_redundancy = bool(client.get("_auto_redundancy_active"))
        base_redundancy = (self.force_red or auto_redundancy) and redundancy_allowed
        fec_requested = bool(force_fec) or base_redundancy

        if fec_requested:
            # Legacy GStreamer advertised do-fec; newer releases use fec-type (enum) and percentages.
            if self._set_gst_property_if_available(trans, "do-fec", True):
                fec_applied = True
            else:
                try:
                    trans.set_property("fec-type", GstWebRTC.WebRTCFECType.ULP_RED)
                    fec_applied = True
                except Exception:
                    if self._set_gst_property_if_available(
                        trans, "fec-type", GstWebRTC.WebRTCFECType.ULP_RED
                    ):
                        fec_applied = True
            if force_fec:
                if self._set_gst_property_if_available(trans, "fec-percentage", 100):
                    fec_applied = True
            if webrtc:
                try:
                    webrtc.set_property("preferred-fec-type", GstWebRTC.WebRTCFECType.ULP_RED)
                    fec_applied = True
                except Exception:
                    pass
        else:
            # User explicitly disabled redundancy; try to turn FEC off where supported.
            self._set_gst_property_if_available(trans, "do-fec", False)
            if webrtc:
                try:
                    webrtc.set_property("preferred-fec-type", GstWebRTC.WebRTCFECType.NONE)
                except Exception:
                    pass

        nack_success = self._set_gst_property_if_available(trans, "do-nack", True)
        if announce:
            if nack_success:
                print(f"SEND NACKS ENABLED ({label})")
            else:
                printwarn(f"Failed to enable NACK on {label}: property unavailable")

        rtx_requested = bool(self.force_rtx or force_rtx)
        rtx_success = False
        rtx_via_nack = False
        if rtx_requested:
            rtx_success = self._set_gst_property_if_available(trans, "do-retransmission", True)
            if not rtx_success and nack_success:
                # Modern webrtcbin drives RTX via jitterbuffer do-nack instead of a separate property.
                rtx_success = True
                rtx_via_nack = True
            if rtx_success and announce:
                suffix = ""
                if rtx_via_nack:
                    suffix = " (via jitterbuffer do-nack)"
                elif force_rtx or self.force_rtx:
                    suffix = " (forced)"
                elif not self.nored:
                    suffix = " (auto)"
                print(f"RTX ENABLED ({label}){suffix}")
            elif force_rtx and announce and not self._rtx_support_warned:
                if nack_success:
                    printwarn(
                        f"{label}: RTX not supported by this GStreamer build; continuing with NACK only."
                    )
                else:
                    printwarn(
                        f"{label}: RTX not supported by this GStreamer build; continuing with FEC/PLI only."
                    )
                self._rtx_support_warned = True

        if fec_applied and announce:
            print(f"FEC ENABLED ({label})")
        if force_fec and not fec_applied and self.force_red and announce:
            printwarn(f"{label}: Unable to force FEC on this GStreamer build.")

        return fec_applied or rtx_success

    def _apply_loss_recovery_overrides(self, client: Dict[str, Any]) -> bool:
        """Best-effort attempt to enable redundancy on existing transceivers."""
        webrtc = client.get("webrtc")
        if not webrtc:
            return False

        updated = False
        redundancy_allowed = not self.nored
        auto_redundancy = bool(client.get("_auto_redundancy_active"))
        redundancy_requested = (self.force_red or auto_redundancy) and redundancy_allowed
        if redundancy_requested:
            target_fec_type = GstWebRTC.WebRTCFECType.ULP_RED
            current_fec_type, fec_type_available = self._get_gst_property_if_available(webrtc, "preferred-fec-type")
            needs_update = not fec_type_available or current_fec_type != target_fec_type
            if needs_update:
                try:
                    webrtc.set_property("preferred-fec-type", target_fec_type)
                    updated = True
                except Exception:
                    pass

        index = 0
        while True:
            try:
                trans = webrtc.emit("get-transceiver", index)
            except Exception:
                break
            if not trans:
                break
            force_fec = (self.force_red or auto_redundancy) and redundancy_allowed
            force_rtx = self.force_rtx
            if self._apply_loss_controls(
                client,
                trans,
                label=f"transceiver[{index}]",
                force_fec=force_fec,
                force_rtx=force_rtx,
                announce=False,
            ):
                updated = True
            index += 1
        return updated

    def _install_viewer_rtpbin_overrides(self, webrtc: Optional[Gst.Element]) -> None:
        """Disable webrtcbin FEC handlers so the viewer redundancy wrapper stays authoritative."""
        if not self.view or not webrtc:
            return
        if bool(getattr(webrtc, "_rn_fec_override_installed", False)):
            return
        setattr(webrtc, "_rn_fec_override_installed", True)

        try:
            rtpbin = webrtc.get_child_by_name("rtpbin")
        except Exception as exc:
            if bool(os.environ.get("RN_DEBUG_VIEWER")):
                printwarn(f"[viewer] Unable to inspect webrtcbin RTP bin: {exc}")
            return

        if not rtpbin:
            return

        blocked = 0
        block_mask = GObject.SignalMatchType.ID
        for signal_name in ("request-fec-decoder-full", "request-fec-decoder"):
            signal_id = GObject.signal_lookup(signal_name, rtpbin.__gtype__)
            if not signal_id:
                continue
            blocked += GObject.signal_handlers_block_matched(
                rtpbin,
                block_mask,
                signal_id,
                0,
                None,
                None,
                None,
            )

        if blocked:
            label = "handlers" if blocked != 1 else "handler"
            printc(
                f"Viewer: disabled webrtcbin internal FEC decoders ({blocked} {label})",
                "0AF",
            )
        elif bool(os.environ.get("RN_DEBUG_VIEWER")):
            print("[viewer] No internal FEC handlers were blocked")

    def __init__(self, params):
        self.params = params  # Store params for room recording manager
        self.pipeline = params.pipeline
        self.conn = None
        self.pipe = None
        self.h264 = params.h264
        self.vp8 = params.vp8
        self.vp9 = getattr(params, 'vp9', False)
        self.av1 = getattr(params, 'av1', False)
        self._force_h264_profile_id = sanitize_profile_level_id(
            getattr(params, "force_h264_profile_id", None)
        )
        self._forced_profile_notice_shown = False
        self._remote_h264_profile_id: Optional[str] = None
        self.pipein = params.pipein
        self.bitrate = params.bitrate
        self.max_bitrate = params.bitrate
        self.server = params.server
        self.stream_id = params.streamid
        self.view = params.view
        self.auto_view_buffer = getattr(params, 'auto_view_buffer', False)
        self.room_name = params.room
        self.room_hashcode = None
        self.multiviewer = params.multiviewer
        self.stretch_display = getattr(params, 'stretch_display', False)
        self.cleanup_lock = asyncio.Lock()  # Prevent concurrent cleanup
        self.pipeline_lock = threading.Lock()  # Thread-safe pipeline operations
        self._shutdown_requested = False  # Initialize shutdown flag
        self.record = params.record
        self.streamin = params.streamin
        self.ndiout = params.ndiout
        self.fdsink = params.fdsink
        self.v4l2sink = params.v4l2sink
        self.v4l2sink_width = clamp_int(getattr(params, "v4l2sink_width", 1280), 16, 7680)
        self.v4l2sink_height = clamp_int(getattr(params, "v4l2sink_height", 720), 16, 4320)
        self.v4l2sink_fps = clamp_int(getattr(params, "v4l2sink_fps", 30), 1, 120)
        self.v4l2sink_format = (getattr(params, "v4l2sink_format", "YUY2") or "YUY2").upper()
        self.v4l2sink_device = resolve_v4l2sink_device(self.v4l2sink) if self.v4l2sink else None
        self.v4l2sink_selector = None
        self.v4l2sink_sink_bin = None
        self.v4l2sink_sources = {}
        self.v4l2sink_current_pad = None
        self.v4l2sink_state = None
        self.v4l2sink_remote_map = {}
        self.filesink = None
        self.framebuffer = params.framebuffer
        self.midi = params.midi
        self.nored = params.nored
        self.force_red = getattr(params, 'force_red', False)
        self.force_rtx_requested = getattr(params, 'force_rtx', False)
        self.force_rtx = self.force_rtx_requested or self.force_red
        self._rtx_support_warned = False
        if self.force_red and self.nored:
            printwarn("Both --force-red and --nored specified; honoring --force-red and enabling redundancy")
            self.nored = False
        self.noqos = params.noqos
        self.midi_thread = None
        self.midiout = None
        self.midiout_ports = None
        self.puuid = params.puuid
        self.clients = {}
        self.rotate = int(params.rotate)
        self.save_file = params.save
        self.noaudio = params.noaudio
        self.novideo = params.novideo
        self.audio = getattr(params, 'audio', False)  # Audio recording flag
        self.counter = 0
        self.shared_memory = False
        self.trigger_socket = False

        self.processing = False
        self.buffer = params.buffer
        self.password = params.password
        self.hostname = params.hostname
        self.hashcode = ""
        self.salt = getattr(params, 'salt', None)  # Get salt from params if provided
        self.aom = params.aom
        self.av1 = params.av1
        self.socketout = params.socketout
        self.socketport = params.socketport
        self.socket = None
        self.splashscreen_idle = getattr(params, 'splashscreen_idle', None)
        self.splashscreen_connecting = getattr(params, 'splashscreen_connecting', None)
        self.display_selector = None
        self.display_sink_bin = None
        self.display_sources = {}
        self.display_remote_map = {}
        self.current_display_pad = None
        self._display_chain_config = None
        self._display_surface_cleared = False
        self.display_state = None
        self._display_chain_unavailable = False
        self._display_chain_unavailable_reason = None
        self._display_direct_mode = False
        self._viewer_fec_decoders: Dict[str, Gst.Element] = {}
        self._pending_viewer_fec_decoders: Dict[str, Gst.Element] = {}
        self._viewer_fec_probe_counts: Dict[str, Dict[str, int]] = {}
        self._viewer_fec_probe_aliases: Dict[str, str] = {}
        disable_auto_retry = bool(getattr(params, "no_auto_retry", False))
        self._viewer_restart_enabled = not disable_auto_retry
        self._viewer_restart_pending = False
        self._viewer_restart_timer = None
        self._viewer_restart_attempts = 0
        self._viewer_last_play_request = 0.0
        self._viewer_last_disconnect = 0.0
        initial_delay = float(getattr(params, "viewer_retry_initial", 15.0))
        short_delay = float(getattr(params, "viewer_retry_short", 45.0))
        long_delay = float(getattr(params, "viewer_retry_long", 180.0))
        # Ensure a monotonic progression of retry windows.
        self._viewer_restart_initial_delay = max(0.0, initial_delay)
        self._viewer_restart_short_delay = max(self._viewer_restart_initial_delay, short_delay)
        self._viewer_restart_long_delay = max(self._viewer_restart_short_delay, long_delay)
        self._viewer_redundancy_autodisable = False
        self._viewer_redundancy_info: Optional[Dict[str, Any]] = None
        self._viewer_redundancy_history_ns = 200_000_000  # 200 ms of RTP history for FEC recovery
        self._viewer_pending_idle = False
        self._viewer_enable_fec = bool(getattr(params, "viewer_enable_fec", False))
        self._viewer_fec_runtime_disabled = False
        self._viewer_fec_notice_shown = False
        self._viewer_fec_no_parity_threshold = max(200, int(os.environ.get("RN_FEC_NO_PARITY_THRESHOLD", 320)))
        self._viewer_fec_last_source = None
        self._publisher_fec_probe_id = 0
        self._publisher_fec_probe_pad = None
        self._publisher_fec_probe_counts: Dict[str, int] = {}
        flag_disable_hw = getattr(params, 'disable_hw_decoder', False)
        self._user_disable_hw_decoder = bool(flag_disable_hw)
        self._force_hw_decoder = bool(RN_FORCE_HW_DECODER) and not self._user_disable_hw_decoder
        env_disable = bool(RN_DISABLE_HW_DECODER and not self._force_hw_decoder)
        self._auto_disable_hw_decoder = False
        self.disable_hw_decoder = bool(self._user_disable_hw_decoder or env_disable)
        if self._user_disable_hw_decoder:
            printc("Hardware decoder disabled by --disable-hw-decoder", "FF0")
        elif env_disable:
            printc("Hardware decoder disabled via RN_DISABLE_HW_DECODER", "FF0")
        elif self._force_hw_decoder:
            printc("Hardware decoder forced via RN_FORCE_HW_DECODER", "0AF")
        self._active_hw_decoder_streams: Set[str] = set()
        self._hw_decoder_warning_count = 0
        self._hw_decoder_warning_window = 0.0
        self._pending_hw_decoder_warning: Optional[Dict[str, Any]] = None
        self._pending_hw_decoder_warning_count = 0
        self._pipeline_bus_watch_installed = False
        self._last_viewer_codec = None
        self._loss_hint_shown = False
        self._hw_decoder_warning_ref = None
        if getattr(self, "view", None):
            _register_hw_decoder_warning_listener(self)
        
        # ICE/TURN configuration
        self.stun_server = getattr(params, 'stun_server', None)
        self.turn_server = getattr(params, 'turn_server', None)
        self.auto_turn = getattr(params, 'auto_turn', False)
        self.ice_transport_policy = getattr(params, 'ice_transport_policy', 'all')
        
        # Recording support
        self.recording_files = []
        self.recording_enabled = bool(self.record) and bool(self.view)
        
        if self.recording_enabled:
            print(f"Recording mode enabled")
            print(f"   Stream: {self.view}")
            print(f"   Output prefix: {self.record}")
        
        # Room recording with subprocess managers
        self.room_recording = getattr(params, 'room_recording', False)
        self.record_room = getattr(params, 'record_room', False)
        self.room_ndi = getattr(params, 'room_ndi', False)
        self.room_monitor = getattr(params, 'room_monitor', False)
        self.single_stream_recording = getattr(params, 'single_stream_recording', False)
        # NDI direct mode is now the default, use ndi_combine to opt into the problematic combiner
        self.ndi_combine = getattr(params, 'ndi_combine', False)
        self.ndi_direct = not self.ndi_combine  # Direct mode by default
        self.stream_filter = getattr(params, 'stream_filter', None)

        # Room join notifications (HTTP + notify topic + GPIO pulse)
        self.join_webhook_url = (getattr(params, 'join_webhook', None) or "").strip() or None
        self.join_postapi_url = (getattr(params, 'join_postapi', None) or "").strip() or None
        self.join_notify_topic = (getattr(params, 'join_notify_topic', None) or "").strip() or None
        self.join_notify_url = (getattr(params, 'join_notify_url', "https://notify.vdo.ninja/") or "https://notify.vdo.ninja/").strip()
        self.join_notify_timeout = max(0.2, float(getattr(params, 'join_notify_timeout', 5.0)))
        self.join_gpio_pin = getattr(params, 'join_gpio_pin', None)
        self.join_gpio_pulse = max(0.05, float(getattr(params, 'join_gpio_pulse', 0.4)))
        self.join_gpio_active_low = bool(getattr(params, 'join_gpio_active_low', False))
        self.room_join_notifications_enabled = bool(
            self.join_webhook_url
            or self.join_postapi_url
            or self.join_notify_topic
            or self.join_gpio_pin is not None
        )
        self._background_tasks: Set[asyncio.Task] = set()
        self._room_join_gpio = None
        self._room_join_gpio_ready = False
        self._room_join_gpio_lock = threading.Lock()

        if self.join_gpio_pin is not None:
            self._setup_room_join_gpio()
        
        # HLS recording options
        self.use_hls = getattr(params, 'hls', False)
        self.use_splitmux = getattr(params, 'hls_splitmux', False)
        
        # Subprocess managers for room recording
        self.subprocess_managers = {}  # stream_id -> WebRTCSubprocessManager
        self.room_streams = {}  # Track room streams
        self.room_streams_lock = asyncio.Lock()
        self.uuid_to_stream_id = {} # Maps an incoming peer's UUID to a specific stream_id we requested
        self.stream_id_to_uuid = {} # Reverse mapping: stream_id -> UUID
        self.session_to_stream = {} # Maps session ID to stream ID
        
        # Enable multiviewer when room NDI is active
        if self.room_ndi:
            self.multiviewer = True
        
        # Multi-peer recording state (Legacy - can be removed if only using subprocesses)
        self.multi_peer_client = None
        self.room_recorders = {}  # stream_id -> recorder
        self.room_sessions = {}   # session_id -> stream_id
        self.ice_queue = asyncio.Queue()  # Thread-safe ICE queue
        self.ice_processor_task = None
        self.event_loop = None  # Will be set when event loop is available
        
        try:
            if self.password:
                # Use provided salt or derive from hostname
                if not self.salt:  # Only derive salt if not provided via command line
                    hostname_to_parse = self.hostname if self.hostname else "wss://wss.vdo.ninja:443"
                    parsed_url = urlparse(hostname_to_parse)
                    if parsed_url.hostname:
                        hostname_parts = parsed_url.hostname.split(".")
                        self.salt = ".".join(hostname_parts[-2:])
                    else:
                        self.salt = "vdo.ninja"  # Default salt
                    
                self.hashcode = generateHash(self.password+self.salt, 6)

                if self.room_name:
                    self.room_hashcode = generateHash(self.room_name+self.password+self.salt, 16)
        except Exception as E:
            printwarn(get_exception_info(E))

            
        if self.save_file:
            self.pipe = Gst.parse_launch(self.pipeline)
            self.setup_ice_servers(self.pipe.get_by_name('sendrecv'))
            self.pipe.set_state(Gst.State.PLAYING)
            print("RECORDING TO DISK STARTED")

    def _setup_room_join_gpio(self):
        """Initialize optional GPIO output used for room-join pulses."""
        if self.join_gpio_pin is None:
            return
        try:
            import RPi.GPIO as room_gpio
        except Exception as exc:
            printc(f"⚠️  Join GPIO unavailable: {exc}", "F77")
            self.join_gpio_pin = None
            return

        try:
            room_gpio.setwarnings(False)
            room_gpio.setmode(room_gpio.BOARD)
            room_gpio.setup(self.join_gpio_pin, room_gpio.OUT)
            room_gpio.output(self.join_gpio_pin, self._join_gpio_inactive_state(room_gpio))
            self._room_join_gpio = room_gpio
            self._room_join_gpio_ready = True
            pulse_mode = "active-LOW" if self.join_gpio_active_low else "active-HIGH"
            printc(
                f"🔔 Room-join GPIO armed on BOARD pin {self.join_gpio_pin} ({pulse_mode}, {self.join_gpio_pulse:.2f}s)",
                "0AF",
            )
        except Exception as exc:
            printc(f"⚠️  Failed to initialize join GPIO pin {self.join_gpio_pin}: {exc}", "F77")
            self.join_gpio_pin = None
            self._room_join_gpio = None
            self._room_join_gpio_ready = False

    def _join_gpio_inactive_state(self, room_gpio):
        return room_gpio.HIGH if self.join_gpio_active_low else room_gpio.LOW

    def _join_gpio_active_state(self, room_gpio):
        return room_gpio.LOW if self.join_gpio_active_low else room_gpio.HIGH

    def _queue_background_task(self, coro, label: str):
        """Run a background coroutine and surface failures in logs."""
        try:
            task = asyncio.create_task(coro)
        except RuntimeError:
            return

        self._background_tasks.add(task)

        def _on_done(done_task):
            self._background_tasks.discard(done_task)
            try:
                exc = done_task.exception()
            except asyncio.CancelledError:
                return
            except Exception as check_exc:
                printwarn(f"Background task '{label}' completion check failed: {check_exc}")
                return
            if exc:
                printwarn(f"Background task '{label}' failed: {exc}")

        task.add_done_callback(_on_done)

    def _build_room_join_payload(self, stream_id: str, uuid: str, source: str) -> Dict[str, Any]:
        timestamp_ms = int(time.time() * 1000)
        return {
            "event": "streamAdded",
            "roomEvent": "room_join",
            "streamID": stream_id,
            "room": self.room_name,
            "uuid": uuid,
            "source": source,
            "timestamp": timestamp_ms,
        }

    def _post_json_blocking(self, url: str, payload: Dict[str, Any]) -> int:
        body = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "raspberry-ninja/room-join",
            },
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=self.join_notify_timeout) as resp:
            return getattr(resp, "status", 200)

    def _get_url_blocking(self, url: str) -> int:
        req = urllib_request.Request(
            url,
            headers={"User-Agent": "raspberry-ninja/room-join"},
            method="GET",
        )
        with urllib_request.urlopen(req, timeout=self.join_notify_timeout) as resp:
            return getattr(resp, "status", 200)

    def _pulse_room_join_gpio_blocking(self):
        room_gpio = self._room_join_gpio
        if not room_gpio or not self._room_join_gpio_ready or self.join_gpio_pin is None:
            return

        active_state = self._join_gpio_active_state(room_gpio)
        inactive_state = self._join_gpio_inactive_state(room_gpio)
        with self._room_join_gpio_lock:
            room_gpio.output(self.join_gpio_pin, active_state)
            time.sleep(self.join_gpio_pulse)
            room_gpio.output(self.join_gpio_pin, inactive_state)

    async def _send_room_join_webhook(self, payload: Dict[str, Any]):
        if not self.join_webhook_url:
            return
        try:
            status = await asyncio.to_thread(self._post_json_blocking, self.join_webhook_url, payload)
            printc(f"📣 Room join webhook sent ({status}) for {payload['streamID']}", "0AF")
        except Exception as exc:
            printc(f"⚠️  Room join webhook failed: {exc}", "F77")

    async def _send_room_join_postapi(self, payload: Dict[str, Any]):
        if not self.join_postapi_url:
            return
        message = {
            "update": {
                "streamID": payload.get("streamID"),
                "action": "streamAdded",
                "value": payload,
            }
        }
        try:
            status = await asyncio.to_thread(self._post_json_blocking, self.join_postapi_url, message)
            printc(f"📨 Join postapi sent ({status}) for {payload['streamID']}", "0AF")
        except Exception as exc:
            printc(f"⚠️  Join postapi failed: {exc}", "F77")

    async def _send_room_join_notify_topic(self, payload: Dict[str, Any]):
        if not self.join_notify_topic:
            return
        room_label = self.room_name if self.room_name else "room"
        message = f"Stream {payload['streamID']} joined {room_label}"
        query = urlencode({"notify": self.join_notify_topic, "message": message})
        separator = "&" if "?" in self.join_notify_url else "?"
        notify_url = f"{self.join_notify_url}{separator}{query}"
        try:
            status = await asyncio.to_thread(self._get_url_blocking, notify_url)
            printc(f"🔔 Notify topic triggered ({status}) for {payload['streamID']}", "0AF")
        except Exception as exc:
            printc(f"⚠️  Notify topic trigger failed: {exc}", "F77")

    async def _send_room_join_gpio_pulse(self):
        if not self._room_join_gpio_ready:
            return
        try:
            await asyncio.to_thread(self._pulse_room_join_gpio_blocking)
        except Exception as exc:
            printc(f"⚠️  Join GPIO pulse failed: {exc}", "F77")

    async def _dispatch_room_join_notifications(self, stream_id: str, uuid: str, source: str):
        """Dispatch all configured room-join notifications."""
        if not self.room_join_notifications_enabled:
            return

        payload = self._build_room_join_payload(stream_id, uuid, source)
        await self._send_room_join_postapi(payload)
        await self._send_room_join_webhook(payload)
        await self._send_room_join_notify_topic(payload)
        await self._send_room_join_gpio_pulse()

    def _create_decoder_element(self, codec: str, fallback: str, name: str) -> Tuple[Optional[Gst.Element], bool]:
        """Create a decoder element preferring Jetson hardware when available."""
        disable_hw = getattr(self, "disable_hw_decoder", False)
        force_hw = getattr(self, "_force_hw_decoder", False)
        factory_name, properties, using_hw = select_preferred_decoder(
            codec,
            fallback,
            disable_hw=disable_hw,
            force_hw=force_hw,
        )
        element_name = name
        if using_hw and factory_name != fallback:
            element_name = f"{name}_hw"

        decoder = Gst.ElementFactory.make(factory_name, element_name)

        if not decoder:
            if using_hw and factory_name != fallback:
                printwarn(
                    f"Failed to create hardware decoder `{factory_name}` for {codec}; "
                    f"falling back to `{fallback}`."
                )
                decoder = Gst.ElementFactory.make(fallback, name)
                properties = {}
                using_hw = False
            else:
                printwarn(f"Failed to create decoder element `{factory_name}` for {codec}")
                return None, False

        for prop, value in properties.items():
            try:
                decoder.set_property(prop, value)
            except Exception as exc:
                printwarn(f"Failed to set property {prop} on {factory_name}: {exc}")

        if using_hw:
            printc(f"Using Jetson hardware decoder `{factory_name}` for {codec}", "0AF")
        elif disable_hw and factory_name == fallback:
            printc(f"Hardware decoder disabled; using `{fallback}` for {codec}", "FF0")

        return decoder, using_hw

    def _get_decoder_description(self, codec: str, fallback: str) -> Tuple[str, bool]:
        """Return pipeline description fragment for the preferred decoder."""
        disable_hw = getattr(self, "disable_hw_decoder", False)
        force_hw = getattr(self, "_force_hw_decoder", False)
        factory_name, properties, using_hw = select_preferred_decoder(
            codec,
            fallback,
            disable_hw=disable_hw,
            force_hw=force_hw,
        )
        parts = [factory_name]

        for key, value in properties.items():
            if isinstance(value, bool):
                value = "true" if value else "false"
            parts.append(f"{key}={value}")

        return " ".join(parts), using_hw
            
    def setup_ice_servers(self, webrtc):
        """Configure ICE servers including default VDO.Ninja TURN servers"""
        try:
            # STUN servers
            if hasattr(self, 'stun_server') and self.stun_server:
                webrtc.set_property('stun-server', self.stun_server)
            elif not hasattr(self, 'no_stun') or not self.no_stun:
                # Default STUN servers
                webrtc.set_property('stun-server', 'stun://stun.l.google.com:19302')
                    
            # TURN servers
            turn_url = None
            
            if hasattr(self, 'turn_server') and self.turn_server:
                # User-specified TURN server
                turn_url = self.turn_server
                # If credentials provided, format the URL properly
                if hasattr(self, 'turn_user') and self.turn_user and hasattr(self, 'turn_pass') and self.turn_pass:
                    # Parse and add credentials to URL if not already present
                    if '@' not in turn_url:
                        # TURN URLs use format: turn:host:port or turns:host:port
                        if turn_url.startswith('turn:') or turn_url.startswith('turns:'):
                            # Extract protocol and server parts
                            if turn_url.startswith('turns:'):
                                protocol = 'turns://'
                                server_part = turn_url[6:]  # Remove 'turns:'
                            else:
                                protocol = 'turn://'
                                server_part = turn_url[5:]  # Remove 'turn:'
                            # Format: turn://username:password@host:port
                            turn_url = f"{protocol}{self.turn_user}:{self.turn_pass}@{server_part}"
                printc(f"Using custom TURN server: {turn_url}", "77F")
            elif hasattr(self, 'auto_turn') and self.auto_turn:
                # Use VDO.Ninja's default TURN servers when auto_turn is enabled
                default_turn = self._get_default_turn_server()
                if default_turn:
                    # Format with credentials
                    turn_url = default_turn['url']
                    if '@' not in turn_url:
                        # TURN URLs use format: turn:host:port or turns:host:port
                        if turn_url.startswith('turn:') or turn_url.startswith('turns:'):
                            # Extract protocol and server parts
                            if turn_url.startswith('turns:'):
                                protocol = 'turns://'
                                server_part = turn_url[6:]  # Remove 'turns:'
                            else:
                                protocol = 'turn://'
                                server_part = turn_url[5:]  # Remove 'turn:'
                            # Format: turn://username:password@host:port
                            turn_url = f"{protocol}{default_turn['user']}:{default_turn['pass']}@{server_part}"
                    printc(f"Using VDO.Ninja TURN: {turn_url} (auto-enabled for room recording)", "77F")
            
            if turn_url:
                # Try both methods - property and signal
                webrtc.set_property('turn-server', turn_url)
                try:
                    # Also emit add-turn-server signal for better compatibility
                    webrtc.emit('add-turn-server', turn_url)
                    printc(f"DEBUG: Set TURN server via property and signal: {turn_url}", "0FF")
                except Exception as e:
                    printc(f"DEBUG: Set TURN server via property only: {turn_url} (signal failed: {e})", "0FF")
                
            if hasattr(self, 'ice_transport_policy') and self.ice_transport_policy:
                webrtc.set_property('ice-transport-policy', self.ice_transport_policy)
                printc(f"DEBUG: Set ICE transport policy: {self.ice_transport_policy}", "0FF")
                
        except Exception as E:
            printwarn(get_exception_info(E))
            
    def _get_default_turn_server(self):
        """Get default VDO.Ninja TURN server based on location/preference"""
        # VDO.Ninja's public TURN servers from the backup list
        turn_servers = [
            # North America
            {
                'url': 'turn:turn-cae1.vdo.ninja:3478',
                'user': 'steve',
                'pass': 'setupYourOwnPlease',
                'region': 'na-east'
            },
            {
                'url': 'turn:turn-usw2.vdo.ninja:3478',
                'user': 'vdoninja',
                'pass': 'theyBeSharksHere',
                'region': 'na-west'
            },
            # Europe
            {
                'url': 'turn:turn-eu1.vdo.ninja:3478',
                'user': 'steve',
                'pass': 'setupYourOwnPlease',
                'region': 'eu-central'
            },
            # Secure fallback
            {
                'url': 'turns:www.turn.obs.ninja:443',
                'user': 'steve',
                'pass': 'setupYourOwnPlease',
                'region': 'global'
            }
        ]
        
        # For now, return the first one (could be enhanced to select by region)
        return turn_servers[0]

    @staticmethod
    def _coerce_message_flag(value, default: Optional[bool] = None) -> Optional[bool]:
        """Normalize boolean-like flags coming from mixed-type datachannel JSON."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"false", "0", "no", "off", ""}:
                return False
            if lowered in {"true", "1", "yes", "on"}:
                return True
        return default if default is not None else bool(value)

    async def connect(self):
        printc("🔌 Connecting to handshake server...", "0FF")

        if self.view:
            self._prime_viewer_display()
        
        # Use hostname if server is not specified
        server_url = self.server if self.server else self.hostname
        
        # Default to VDO.Ninja if neither is specified
        if not server_url:
            server_url = "wss://wss.vdo.ninja:443"
            printc("Using default server: wss://wss.vdo.ninja:443", "FF0")
        
        # Convert wss:// to ws:// for no-SSL attempt
        ws_server = server_url.replace('wss://', 'ws://') if server_url.startswith('wss://') else server_url
        
        connection_attempts = [
            (lambda: ssl.create_default_context(), "standard SSL", server_url),
            (lambda: ssl._create_unverified_context(), "unverified SSL", server_url),
            (lambda: None, "no SSL", ws_server)  # Use ws:// URL for no-SSL
        ]
        
        last_exception = None
        for create_ssl_context, context_type, connect_url in connection_attempts:
            try:
                printc(f"   ├─ Trying {context_type} to {connect_url}", "FFF")
                ssl_context = create_ssl_context()
                if ssl_context:
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                
                self.conn = await websockets.connect(
                    connect_url,
                    ssl=ssl_context,
                    ping_interval=None
                )
                printc(f"   └─ ✅ Connected successfully!", "0F0")
                break
            except Exception as e:
                last_exception = e
                printc(f"   ├─ ❌ {context_type} failed: {str(e)}", "F00")
                continue
        
        if not self.conn:
            raise ConnectionError(f"Failed to connect with all SSL options. Last error: {last_exception}")

        if self.room_hashcode:
            if self.streamin:
                await self.sendMessageAsync({"request":"joinroom","roomid":self.room_hashcode})
            else:
                await self.sendMessageAsync({"request":"joinroom","roomid":self.room_hashcode,"streamID":self.stream_id+self.hashcode})
            printwout("joining room (hashed)")
        elif self.room_name:
            if self.streamin:
                await self.sendMessageAsync({"request":"joinroom","roomid":self.room_name})
            else:
                await self.sendMessageAsync({"request":"joinroom","roomid":self.room_name,"streamID":self.stream_id+self.hashcode})
            printwout("joining room")
        elif self.streamin:
            await self.sendMessageAsync({"request":"play","streamID":self.streamin+self.hashcode})
            printwout("requesting stream")
        else:
            await self.sendMessageAsync({"request":"seed","streamID":self.stream_id+self.hashcode})
            printwout("seed start")

    def _inject_viewer_bitrate_hint(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """Attach viewer-requested bitrate to signaling messages when applicable."""
        if not self.view:
            return msg
        if not isinstance(msg, dict):
            return msg
        try:
            bitrate_hint = int(self.max_bitrate)
        except Exception:
            bitrate_hint = 0
        if bitrate_hint <= 0:
            return msg

        if msg.get('request') in {'play', 'seed'}:
            if 'bitrate' not in msg:
                msg['bitrate'] = bitrate_hint
            if 'bandwidth' not in msg:
                msg['bandwidth'] = bitrate_hint
            if 'maxbandwidth' not in msg:
                msg['maxbandwidth'] = bitrate_hint
            if 'maxBandwidth' not in msg:
                msg['maxBandwidth'] = bitrate_hint
            if 'maxBitrate' not in msg:
                msg['maxBitrate'] = bitrate_hint
        return msg

    def _apply_bitrate_constraints_to_sdp(self, sdp_text: str, context: str = "SDP") -> str:
        """Embed bitrate caps into SDP blobs so publishers honor --bitrate."""
        try:
            target_kbps = int(getattr(self, "max_bitrate", 0) or getattr(self, "bitrate", 0))
        except Exception:
            target_kbps = 0

        if target_kbps <= 0 or not sdp_text:
            return sdp_text

        lines = sdp_text.splitlines()
        if not lines:
            return sdp_text

        video_m_index = next((i for i, line in enumerate(lines) if line.startswith("m=video")), None)
        if video_m_index is None:
            return sdp_text

        # Gather payload IDs from the m=video line
        video_parts = lines[video_m_index].split()
        payload_ids = [p for p in video_parts[3:] if p.isdigit()]

        # Inject or update bandwidth lines
        insert_idx = video_m_index + 1
        while insert_idx < len(lines) and lines[insert_idx].startswith("i="):
            insert_idx += 1

        cursor = insert_idx
        b_as_index = None
        b_tias_index = None
        while cursor < len(lines) and lines[cursor].startswith("b="):
            lower = lines[cursor].lower()
            if lower.startswith("b=as:"):
                b_as_index = cursor
            elif lower.startswith("b=tias:"):
                b_tias_index = cursor
            cursor += 1

        as_line = f"b=AS:{target_kbps}"
        tias_line = f"b=TIAS:{max(1, target_kbps) * 1000}"

        if b_as_index is not None:
            lines[b_as_index] = as_line
        else:
            insert_pos = b_tias_index if b_tias_index is not None else cursor
            lines.insert(insert_pos, as_line)
            if b_tias_index is not None:
                b_tias_index += 1
            if insert_pos <= cursor:
                cursor += 1

        if b_tias_index is not None:
            lines[b_tias_index if b_tias_index < len(lines) else len(lines) - 1] = tias_line
        else:
            lines.insert(cursor, tias_line)
            cursor += 1

        # Update / append fmtp line with x-google bitrate hints for each primary payload
        min_kbps = max(150, min(target_kbps, int(target_kbps * 0.6)))
        primary_payloads: List[str] = []
        for payload in payload_ids:
            rtpmap_prefix = f"a=rtpmap:{payload} "
            rtp_line = next((line for line in lines if line.startswith(rtpmap_prefix)), None)
            if not rtp_line:
                continue
            codec_name = rtp_line[len(rtpmap_prefix):].split("/")[0].upper()
            if codec_name in {"RTX", "RED", "ULPFEC", "FLEXFEC"}:
                continue
            primary_payloads.append(payload)

        google_params = [
            f"x-google-max-bitrate={target_kbps}",
            f"x-google-start-bitrate={target_kbps}",
            f"x-google-min-bitrate={min_kbps}",
            f"x-google-bitrate={target_kbps}",
        ]

        for payload in primary_payloads:
            fmtp_prefix = f"a=fmtp:{payload}"
            fmtp_index = next((i for i, line in enumerate(lines) if line.startswith(fmtp_prefix)), None)
            fmtp_header = fmtp_prefix
            fmtp_params: List[str] = []

            if fmtp_index is not None:
                parts = lines[fmtp_index].split(" ", 1)
                fmtp_header = parts[0]
                if len(parts) == 2:
                    fmtp_params = [p.strip() for p in parts[1].split(";") if p.strip()]
            else:
                fmtp_index = None

            fmtp_params = [
                p for p in fmtp_params
                if not p.startswith(("x-google-max-bitrate", "x-google-min-bitrate", "x-google-start-bitrate", "x-google-bitrate"))
            ]

            fmtp_params.extend(google_params)
            fmtp_line = f"{fmtp_header} " + ";".join(fmtp_params)

            if fmtp_index is not None:
                lines[fmtp_index] = fmtp_line
            else:
                rtpmap_index = next((i for i, line in enumerate(lines) if line.startswith(f"a=rtpmap:{payload} ")), None)
                insert_pos = rtpmap_index + 1 if rtpmap_index is not None else cursor
                lines.insert(insert_pos, fmtp_line)

        modified = "\r\n".join(lines)
        if not modified.endswith("\r\n"):
            modified += "\r\n"

        printc(f"   📶 Embedding {target_kbps} kbps cap into {context}", "07F")
        return modified

    def _capture_remote_video_profiles(self, sdp_text: str) -> None:
        """Record the remote offer's video fmtp values so we can mirror them in our answer."""
        if not sdp_text or not self.view:
            self._remote_h264_profile_id = None
            return

        lines = sdp_text.splitlines()
        video_payloads: Set[str] = set()
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("m=video"):
                parts = line.split()
                if len(parts) > 3:
                    video_payloads = {p for p in parts[3:] if p.isdigit()}
                break

        if not video_payloads:
            self._remote_h264_profile_id = None
            return

        payload_to_codec: Dict[str, str] = {}
        payload_to_fmtp: Dict[str, str] = {}

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("a=rtpmap:"):
                try:
                    prefix, codec_info = line.split(None, 1)
                except ValueError:
                    continue
                payload = prefix.split(":")[1]
                if payload not in video_payloads:
                    continue
                codec_name = codec_info.split("/")[0].upper()
                payload_to_codec[payload] = codec_name
            elif line.startswith("a=fmtp:"):
                parts = line.split(" ", 1)
                payload = parts[0].split(":")[1]
                if payload not in video_payloads:
                    continue
                payload_to_fmtp[payload] = parts[1].strip() if len(parts) == 2 else ""

        previous_profile = self._remote_h264_profile_id
        new_profile = None

        for payload, codec_name in payload_to_codec.items():
            if codec_name != "H264":
                continue
            fmtp = payload_to_fmtp.get(payload)
            if not fmtp:
                continue
            profile = self._extract_profile_level_id_from_fmtp(fmtp)
            if profile:
                new_profile = profile
                break

        self._remote_h264_profile_id = new_profile
        if new_profile and new_profile != previous_profile:
            printc(f"   🎯 Remote H264 profile-level-id detected: {new_profile}", "0AF")

    @staticmethod
    def _extract_profile_level_id_from_fmtp(fmtp: str) -> Optional[str]:
        """Return profile-level-id from an fmtp fragment."""
        if not fmtp:
            return None
        for token in fmtp.split(";"):
            if not token:
                continue
            key, _, value = token.partition("=")
            if key.strip().lower() == "profile-level-id":
                return sanitize_profile_level_id(value)
        return None

    def _target_h264_profile_id(self) -> Optional[str]:
        """Decide which profile-level-id we should advertise back to the sender."""
        return self._force_h264_profile_id or self._remote_h264_profile_id

    def _apply_h264_profile_override(self, sdp_text: str, profile_id: str) -> str:
        """Rewrite H264 fmtp lines to use the requested profile-level-id."""
        normalized = sanitize_profile_level_id(profile_id)
        if not sdp_text or not normalized:
            return sdp_text

        lines = sdp_text.splitlines()
        ends_with_crlf = sdp_text.endswith("\r\n")

        h264_payloads: Set[str] = set()
        for raw_line in lines:
            line = raw_line.strip()
            if not line.startswith("a=rtpmap:"):
                continue
            try:
                prefix, codec_info = line.split(None, 1)
            except ValueError:
                continue
            payload = prefix.split(":")[1]
            codec_name = codec_info.split("/")[0].upper()
            if codec_name == "H264":
                h264_payloads.add(payload)

        if not h264_payloads:
            return sdp_text

        changed = False

        for idx, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line.startswith("a=fmtp:"):
                continue
            header_and_payload = raw_line.split(" ", 1)
            header = header_and_payload[0]
            payload = header.split(":")[1]
            if payload not in h264_payloads:
                continue
            params_str = header_and_payload[1] if len(header_and_payload) == 2 else ""
            params = [p.strip() for p in params_str.split(";") if p.strip()]
            replaced = False
            for idx_param, param in enumerate(params):
                key, _, _ = param.partition("=")
                if key.strip().lower() == "profile-level-id":
                    params[idx_param] = f"profile-level-id={normalized}"
                    replaced = True
                    break
            if not replaced:
                params.append(f"profile-level-id={normalized}")
            new_line = header
            if params:
                new_line = f"{header} {';'.join(params)}"
            if new_line != raw_line:
                lines[idx] = new_line
                changed = True

        if not changed:
            return sdp_text

        updated = "\r\n".join(lines)
        if ends_with_crlf and not updated.endswith("\r\n"):
            updated += "\r\n"
        return updated

    def _determine_primary_video_codec(self) -> Optional[Tuple[str, Optional[str]]]:
        """Return the (codec, fmtp) tuple describing the local publisher's primary video codec."""
        if getattr(self.params, "novideo", False) or getattr(self, "novideo", False):
            return None

        def _codec_tuple(name: str, fmtp: Optional[str] = None) -> Tuple[str, Optional[str]]:
            return (name, fmtp)

        if getattr(self, "vp9", False) or getattr(self.params, "vp9", False):
            return _codec_tuple("VP9/90000")
        if getattr(self, "vp8", False) or getattr(self.params, "vp8", False):
            return _codec_tuple("VP8/90000")
        if getattr(self, "av1", False) or getattr(self.params, "av1", False):
            return _codec_tuple("AV1/90000")
        if getattr(self.params, "h265", False) or getattr(self.params, "hevc", False):
            return _codec_tuple("H265/90000")
        if getattr(self, "h264", False) or getattr(self.params, "h264", False):
            return _codec_tuple(
                "H264/90000",
                "packetization-mode=1;profile-level-id=42e01f;level-asymmetry-allowed=1",
            )

        # Default to VP8 - this matches the actual pipeline default behavior
        # (when no codec flag is specified, the pipeline uses vp8enc)
        return _codec_tuple("VP8/90000")

    def _ensure_primary_video_codec_in_sdp(self, sdp_text: str) -> str:
        """Chrome rejects offers missing a base codec. Ensure H264/VP8/etc. exists alongside RED."""
        descriptor = self._determine_primary_video_codec()
        if not descriptor:
            return sdp_text
        target_codec, fmtp_params = descriptor
        codec_label = target_codec.split("/")[0].upper()

        lines = sdp_text.splitlines()
        if not lines:
            return sdp_text
        ends_with_crlf = sdp_text.endswith("\r\n")

        current_media = None
        video_payloads: Set[str] = set()
        rtpmap_entries: Dict[str, Tuple[int, str]] = {}
        fmtp_entries: Dict[str, Tuple[int, str]] = {}
        apt_candidates: List[str] = []

        for idx, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("m="):
                parts = line.split()
                if len(parts) >= 4:
                    current_media = parts[0][2:]
                    if current_media == "video":
                        video_payloads = set(parts[3:])
                    else:
                        video_payloads = set()
                continue

            if current_media != "video":
                continue

            if line.startswith("a=rtpmap:"):
                try:
                    header, codec_desc = line.split(None, 1)
                except ValueError:
                    continue
                pt = header.split(":")[1]
                rtpmap_entries[pt] = (idx, codec_desc.strip())
                continue

            if line.startswith("a=fmtp:"):
                parts = line.split(None, 1)
                header = parts[0]
                params = parts[1] if len(parts) > 1 else ""
                pt = header.split(":")[1]
                fmtp_entries[pt] = (idx, params)
                match = re.search(r"apt=(\d+)", params)
                if match:
                    apt_candidates.append(match.group(1))
                continue

        if not rtpmap_entries:
            return sdp_text

        if any(desc.upper().startswith(codec_label) for _, desc in rtpmap_entries.values()):
            return sdp_text

        primary_pt: Optional[str] = None
        for apt in apt_candidates:
            if apt in rtpmap_entries:
                primary_pt = apt
                break
            if apt in video_payloads:
                primary_pt = apt
                break

        if not primary_pt and video_payloads:
            try:
                primary_pt = sorted(video_payloads, key=lambda value: int(re.sub(r"\D", "", value) or 0))[0]
            except Exception:
                primary_pt = next(iter(video_payloads))

        if not primary_pt or primary_pt not in rtpmap_entries:
            return sdp_text

        rtpmap_idx, _ = rtpmap_entries[primary_pt]
        lines[rtpmap_idx] = f"a=rtpmap:{primary_pt} {target_codec}"

        if fmtp_params:
            fmtp_line = f"a=fmtp:{primary_pt} {fmtp_params}"
            if primary_pt in fmtp_entries:
                fmtp_idx, _ = fmtp_entries[primary_pt]
                lines[fmtp_idx] = fmtp_line
            else:
                lines.insert(rtpmap_idx + 1, fmtp_line)
        elif primary_pt in fmtp_entries:
            # Remove stray apt-only entries that no longer apply.
            fmtp_idx, params = fmtp_entries[primary_pt]
            if params.strip().startswith("apt="):
                lines.pop(fmtp_idx)

        repaired = "\r\n".join(lines)
        if ends_with_crlf and not repaired.endswith("\r\n"):
            repaired += "\r\n"
        return repaired

    def sendMessage(self, msg): # send message to wss
        if isinstance(msg, dict):
            msg = dict(msg)
            msg = self._inject_viewer_bitrate_hint(msg)
        else:
            typeName = type(msg).__name__
            raise TypeError(f"sendMessage expects dict, got {typeName}")

        if self.puuid:
            msg['from'] = self.puuid

        client = None
        if "UUID" in msg and msg['UUID'] in self.clients:
            client = self.clients[msg['UUID']]

        if client and client['send_channel']:
            try:
                msgJSON = json.dumps(msg)
                client['send_channel'].emit('send-string', msgJSON)
                printout("a message was sent via datachannels: "+msgJSON[:60])
            except Exception as e:
                try:
                    if self.password:
                        #printc("Password","0F3")
                        if "candidate" in msg:
                            msg['candidate'], msg['vector'] = encrypt_message(msg['candidate'], self.password+self.salt)
                        if "candidates" in msg:
                            msg['candidates'], msg['vector'] = encrypt_message(msg['candidates'], self.password+self.salt)
                        if "description" in msg:
                            msg['description'], msg['vector'] = encrypt_message(msg['description'], self.password+self.salt)
                
                    msgJSON = json.dumps(msg)
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(self.conn.send(msgJSON))
                    printwout("a message was sent via websockets 2: "+msgJSON[:60])
                except Exception as e:
                    printc(e,"F00")
        else:
            try:
                if self.password:
                   # printc("Password","0F3")
                    if "candidate" in msg:
                        msg['candidate'], msg['vector'] = encrypt_message(msg['candidate'], self.password+self.salt)
                    if "candidates" in msg:
                        msg['candidates'], msg['vector'] = encrypt_message(msg['candidates'], self.password+self.salt)
                    if "description" in msg:
                        msg['description'], msg['vector'] = encrypt_message(msg['description'], self.password+self.salt)
                
                msgJSON = json.dumps(msg)
                loop = asyncio.new_event_loop()        
                loop.run_until_complete(self.conn.send(msgJSON))
                printwout("a message was sent via websockets 1: "+msgJSON[:60])
            except Exception as e:
                printc(e,"F01")
                
                
    async def sendMessageAsync(self, msg): # send message to wss
        if isinstance(msg, dict):
            msg = dict(msg)
            msg = self._inject_viewer_bitrate_hint(msg)
        else:
            typeName = type(msg).__name__
            raise TypeError(f"sendMessageAsync expects dict, got {typeName}")

        if self.puuid:
            msg['from'] = self.puuid

        client = None
        if "UUID" in msg and msg['UUID'] in self.clients:
            client = self.clients[msg['UUID']]

        if client and client['send_channel']:
            try:
                msgJSON = json.dumps(msg)
                client['send_channel'].emit('send-string', msgJSON)
                printout("a message was sent via datachannels: "+msgJSON[:60])
            except Exception as e:
                try:
                    if self.password:
                        if "candidate" in msg:
                            msg['candidate'], msg['vector'] = encrypt_message(msg['candidate'], self.password+self.salt)
                        if "candidates" in msg:
                            msg['candidates'], msg['vector'] = encrypt_message(msg['candidates'], self.password+self.salt)
                        if "description" in msg:
                            msg['description'], msg['vector'] = encrypt_message(msg['description'], self.password+self.salt)
                            
                    msgJSON = json.dumps(msg)
                    await self.conn.send(msgJSON)
                    printwout("a message was sent via websockets 2: "+msgJSON[:60])
                except Exception as e:
                    printwarn(get_exception_info(e))

        else:
            try:
                if self.password:
                    if "candidate" in msg:
                        msg['candidate'], msg['vector'] = encrypt_message(msg['candidate'], self.password+self.salt)
                    if "candidates" in msg:
                        msg['candidates'], msg['vector'] = encrypt_message(msg['candidates'], self.password+self.salt)
                    if "description" in msg:
                        msg['description'], msg['vector'] = encrypt_message(msg['description'], self.password+self.salt)
                        
                msgJSON = json.dumps(msg)
                await self.conn.send(msgJSON)
                printwout("a message was sent via websockets 1: "+msgJSON[:60])
            except Exception as e:
                printwarn(get_exception_info(E))

    def setup_socket(self):
        import socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', int(self.socketport)))
        
    def on_new_socket_sample(self, sink):
        sample = sink.emit("pull-sample")
        if sample:
            buffer = sample.get_buffer()
            caps = sample.get_caps()
            height = caps.get_structure(0).get_value("height")
            width = caps.get_structure(0).get_value("width")
            
            _, map_info = buffer.map(Gst.MapFlags.READ)
            frame_data = map_info.data
            
            # Send frame size
            self.socket.sendto(struct.pack('!III', width, height, len(frame_data)), ('127.0.0.1', int(self.socketport)))
            print("Sending")
            # Send frame data in chunks
            chunk_size = 65507  # Maximum safe UDP packet size
            for i in range(0, len(frame_data), chunk_size):
                chunk = frame_data[i:i+chunk_size]
                self.socket.sendto(chunk, ('127.0.0.1', int(self.socketport)))
            
            buffer.unmap(map_info)
        return Gst.FlowReturn.OK
    
    def new_sample(self, sink):
        if self.processing:
            return False
        self.processing = True
        try :
            sample = sink.emit("pull-sample")
            if sample:
                buffer = sample.get_buffer()
                caps = sample.get_caps()
                height = int(caps.get_structure(0).get_int("height").value)
                width = int(caps.get_structure(0).get_int("width").value)
                frame_data = buffer.extract_dup(0, buffer.get_size())
                np_frame_data = np.frombuffer(frame_data, dtype=np.uint8).reshape(height, width, 3)
                print(np.shape(np_frame_data), np_frame_data[0,0,:])

                frame_shape = (1080 * 1920 * 3)
                frame_buffer = np.ndarray(frame_shape+5, dtype=np.uint8, buffer=self.shared_memory.buf)
                frame_buffer[5:5+width*height*3] = np_frame_data.flatten(order='K') # K means order as how ordered in memory
                frame_buffer[0] = width//255
                frame_buffer[1] = width%255
                frame_buffer[2] = height//255
                frame_buffer[3] = height%255
                frame_buffer[4] = self.counter%255
                self.counter+=1
                self.trigger_socket.sendto(b"update", ("127.0.0.1", 12345))

        except Exception as E:
            printwarn(get_exception_info(E))

        self.processing = False
        return False    
   
    def setup_hls_recording(self):
        """Set up shared HLS sink for audio/video muxing"""
        if hasattr(self, 'hls_sink') and self.hls_sink:
            return  # Already set up
            
        timestamp = str(int(time.time()))
        base_filename = f"{self.streamin}_{timestamp}"
        
        printc("🎬 Setting up HLS recording with audio/video muxing", "0F0")
        
        # Create HLS sink with m3u8 playlist
        self.hls_sink = Gst.ElementFactory.make('hlssink2', 'hlssink')
        if self.hls_sink:
            self.hls_sink.set_property('location', f"{base_filename}_%05d.ts")
            self.hls_sink.set_property('playlist-location', f"{base_filename}.m3u8")
            self.hls_sink.set_property('target-duration', 5)  # 5 second segments
            self.hls_sink.set_property('max-files', 0)  # Keep all segments
            self.hls_sink.set_property('playlist-length', 0)  # Keep all in playlist
            self.hls_sink.set_property('send-keyframe-requests', True)
            self.pipe.add(self.hls_sink)
            self.hls_sink.sync_state_with_parent()
            
            printc(f"   📹 HLS recording configured:", "0F0")
            printc(f"      Playlist: {base_filename}.m3u8", "0F0")
            printc(f"      Segments: {base_filename}_*.ts", "0F0")
            self.hls_base_filename = base_filename
        else:
            printc("❌ Failed to create HLS sink", "F00")

    def _reset_display_chain_state(self):
        """Reset cached viewer display elements."""
        if getattr(self, "display_sources", None):
            for label in list(self.display_sources.keys()):
                try:
                    self._release_display_source(label)
                except Exception:
                    pass

        if getattr(self, "display_selector", None) and self.pipe:
            try:
                self.display_selector.set_state(Gst.State.NULL)
            except Exception:
                pass
            try:
                self.pipe.remove(self.display_selector)
            except Exception:
                pass

        if getattr(self, "display_sink_bin", None) and self.pipe:
            try:
                self.display_sink_bin.set_state(Gst.State.NULL)
            except Exception:
                pass
            try:
                self.pipe.remove(self.display_sink_bin)
            except Exception:
                pass

        self.display_selector = None
        self.display_sink_bin = None
        self.display_sources = {}
        self.display_remote_map = {}
        self.current_display_pad = None
        self._display_chain_config = None
        self.display_state = None
        self._display_direct_mode = False
        self._display_chain_unavailable = False
        self._display_chain_unavailable_reason = None
        self._viewer_pending_idle = False
        self._v4l2sink_chain_config = None
        self._v4l2sink_chain_unavailable = False
        self._v4l2sink_chain_unavailable_reason = None
        self.v4l2sink_state = None
        if hasattr(self, "_active_hw_decoder_streams"):
            self._active_hw_decoder_streams.clear()

        if hasattr(self, "_pipeline_bus_watch_installed"):
            self._pipeline_bus_watch_installed = False
        if hasattr(self, "_pipeline_bus_watch_id") and getattr(self, "_pipeline_bus_watch_id", 0):
            try:
                if self.pipe:
                    bus = self.pipe.get_bus()
                    if bus:
                        bus.remove_watch()
            except Exception:
                pass
            self._pipeline_bus_watch_id = 0

    def _ensure_main_pipeline(self, log: bool = True) -> bool:
        """Ensure the primary Gst.Pipeline exists. Returns True if a new pipeline was created."""
        if self.pipe:
            return False

        pipeline_desc = getattr(self, "pipeline", "")
        try:
            if self.streamin:
                self.pipe = Gst.Pipeline.new("decode-pipeline")
            elif isinstance(pipeline_desc, str) and len(pipeline_desc) > 1:
                if log:
                    print(pipeline_desc)
                self.pipe = Gst.parse_launch(pipeline_desc)
            else:
                self.pipe = Gst.Pipeline.new("data-only-pipeline")
        except Exception as exc:
            printwarn(f"Failed to initialize base pipeline: {exc}")
            self.pipe = None
            return False

        if self.pipe and log:
            print(self.pipe)
        if self.pipe:
            try:
                self._install_pipeline_bus_watch()
            except Exception:
                pass
            try:
                self._install_publisher_fec_probe()
            except Exception as exc:
                printwarn(f"Failed to install TX FEC probe: {exc}")
        return bool(self.pipe)

    def _install_pipeline_bus_watch(self):
        """Listen for pipeline warnings so we can auto-fallback unstable decoders."""
        if getattr(self, "_pipeline_bus_watch_installed", False):
            return
        if not self.pipe:
            return
        try:
            bus = self.pipe.get_bus()
        except Exception:
            bus = None
        if not bus:
            return
        try:
            bus.add_signal_watch()
        except Exception:
            pass
        try:
            bus.connect("message::warning", self._on_pipeline_warning)
            bus.connect("message::error", self._on_pipeline_error)
        except Exception:
            return
        self._pipeline_bus_watch_installed = True

    def _install_publisher_fec_probe(self):
        """Attach a pad probe that records outgoing payload types when tracing is enabled."""
        if self._publisher_fec_probe_id or not os.environ.get("RN_TRACE_TX_FEC"):
            return
        if not self.pipe:
            return
        fec_name = getattr(self.params, "_publisher_redundancy_fec_name", None)
        queue_name = getattr(self.params, "_publisher_redundancy_queue_name", None)

        pad = None
        probe_target = None

        if fec_name:
            fec = self.pipe.get_by_name(fec_name)
            if fec:
                pad = fec.get_static_pad("src")
                probe_target = fec_name
        if not pad and queue_name:
            queue = self.pipe.get_by_name(queue_name)
            if queue:
                pad = queue.get_static_pad("src")
                probe_target = queue_name

        if not pad:
            printwarn("[publish] TX FEC probe could not find a target pad (missing RED/FEC queue)")
            return

        red_pt = clamp_int(getattr(self.params, "publisher_red_pt", 123), 0, 127)
        fec_pt = clamp_int(getattr(self.params, "publisher_fec_pt", 125), 0, 127)
        counts: Dict[str, int] = {"red": 0, "fec": 0, "other": 0}

        def _probe(_pad, info):
            buffer = info.get_buffer()
            if not buffer:
                return Gst.PadProbeReturn.OK
            ok, rtp = GstRtp.RTPBuffer.map(buffer, Gst.MapFlags.READ)
            if not ok:
                return Gst.PadProbeReturn.OK
            try:
                payload_type = rtp.get_payload_type()
            finally:
                GstRtp.RTPBuffer.unmap(rtp)

            if payload_type == red_pt:
                bucket = "red"
            elif payload_type == fec_pt:
                bucket = "fec"
            else:
                bucket = "other"
            counts[bucket] = counts.get(bucket, 0) + 1
            if bucket == "fec" and counts[bucket] == 1:
                printc("[publish] TX FEC probe observed first parity packet", "0AF")
            return Gst.PadProbeReturn.OK

        probe_id = pad.add_probe(Gst.PadProbeType.BUFFER, _probe)
        if probe_id:
            self._publisher_fec_probe_id = probe_id
            self._publisher_fec_probe_pad = pad
            self._publisher_fec_probe_counts = counts
            if probe_target:
                printc(f"[publish] TX FEC probe attached to {probe_target}", "0AF")
            else:
                printc("[publish] TX FEC probe attached", "0AF")

    def _flush_publisher_fec_probe(self):
        """Log and detach the publisher FEC probe if it was installed."""
        if not self._publisher_fec_probe_id:
            return
        counts = self._publisher_fec_probe_counts or {}
        red = counts.get("red", 0)
        fec = counts.get("fec", 0)
        other = counts.get("other", 0)
        printc(
            f"[publish] TX FEC stats: RED={red} packet(s), ULPFEC={fec}, other={other}",
            "77F",
        )
        if self._publisher_fec_probe_pad:
            try:
                self._publisher_fec_probe_pad.remove_probe(self._publisher_fec_probe_id)
            except Exception:
                pass
        self._publisher_fec_probe_id = 0
        self._publisher_fec_probe_pad = None
        self._publisher_fec_probe_counts = {}

    def _on_pipeline_warning(self, bus, message):
        try:
            warning, debug = message.parse_warning()
        except Exception:
            return
        src_name = ""
        try:
            src_name = message.src.get_name()
        except Exception:
            pass
        combined_text = " ".join(
            filter(
                None,
                (str(warning) if warning else "", debug if debug else "", src_name),
            )
        ).lower()
        matches_hw = "nvv4l2decoder" in combined_text or "bug in this gstbufferpool subclass" in combined_text
        if not self._active_hw_decoder_streams:
            if matches_hw:
                self._handle_hw_decoder_warning(str(warning), debug)
            return
        if matches_hw:
            self._handle_hw_decoder_warning(str(warning), debug)

    def _on_pipeline_error(self, bus, message):
        try:
            err, debug = message.parse_error()
        except Exception:
            return
        combined = " ".join(filter(None, (str(err), debug))).lower()
        if "nvv4l2decoder" in combined:
            self._handle_hw_decoder_warning(str(err), debug, force_trigger=True)
            return

        src_name = ""
        try:
            src_name = message.src.get_name()
        except Exception:
            src_name = ""

        if (
            "jetson_display_sink" in combined
            or src_name == "jetson_display_sink"
            or "gstomxvideosink" in combined
        ):
            if "insufficient resources" in combined or "component in error state" in combined:
                self._handle_display_sink_error(str(err), debug)

    def _handle_hw_decoder_warning(
        self,
        warning_text: Optional[str],
        debug_text: Optional[str],
        *,
        force_trigger: bool = False,
    ):
        if self._force_hw_decoder:
            return
        if getattr(self, "_auto_disable_hw_decoder", False):
            return
        if not self._active_hw_decoder_streams:
            pending = self._pending_hw_decoder_warning or {}
            if bool(os.environ.get("RN_DEBUG_VIEWER")):
                print(
                    "[viewer] Queuing hardware decoder warning "
                    f"(force={force_trigger}, count={self._pending_hw_decoder_warning_count + 1})"
                )
            pending["warning"] = warning_text
            pending["debug"] = debug_text
            pending["force"] = bool(pending.get("force")) or bool(force_trigger)
            self._pending_hw_decoder_warning = pending
            self._pending_hw_decoder_warning_count += 1
            return
        now = time.monotonic()
        if not force_trigger:
            window = getattr(self, "_hw_decoder_warning_window", 0.0)
            if not window or (now - window) > 5.0:
                self._hw_decoder_warning_window = now
                self._hw_decoder_warning_count = 0
            self._hw_decoder_warning_count += 1
            if self._hw_decoder_warning_count < 3:
                return
        reason_parts = []
        if warning_text:
            reason_parts.append(str(warning_text))
        if debug_text:
            reason_parts.append(str(debug_text))
        reason = "; ".join(reason_parts).strip()
        if bool(os.environ.get("RN_DEBUG_VIEWER")):
            print(
                "[viewer] Hardware decoder warning "
                f"(force={force_trigger}, count={self._hw_decoder_warning_count}): {reason or 'n/a'}"
            )
        self._trigger_hw_decoder_fallback(reason or "repeated hardware decoder warnings")

    def _trigger_hw_decoder_fallback(self, reason: str):
        if getattr(self, "_auto_disable_hw_decoder", False):
            return
        if not self._active_hw_decoder_streams:
            return
        self._auto_disable_hw_decoder = True
        self.disable_hw_decoder = True
        self._hw_decoder_warning_count = 0
        self._hw_decoder_warning_window = time.monotonic()
        printc(
            "⚠️  Jetson hardware decoder produced repeated warnings; switching viewer to software decoding.",
            "FF0",
        )
        if reason:
            printc(f"   Reason: {reason}", "FF0")
        labels = list(self._active_hw_decoder_streams)

        def _apply_fallback():
            for label in list(labels):
                try:
                    self._switch_stream_to_software(label)
                except Exception as exc:
                    printwarn(f"Failed to rebuild viewer path for {label}: {exc}")
            return False

        if "GLib" in globals():
            GLib.idle_add(_apply_fallback)
        else:
            _apply_fallback()

    def _maybe_process_pending_hw_decoder_warning(self):
        pending = getattr(self, "_pending_hw_decoder_warning", None)
        if not pending or not self._active_hw_decoder_streams:
            return
        self._pending_hw_decoder_warning = None
        count = getattr(self, "_pending_hw_decoder_warning_count", 0)
        self._pending_hw_decoder_warning_count = 0
        if bool(os.environ.get("RN_DEBUG_VIEWER")):
            print(
                "[viewer] Processing pending hardware decoder warnings "
                f"(count={count}, force={pending.get('force')})"
            )
        self._handle_hw_decoder_warning(
            pending.get("warning"),
            pending.get("debug"),
            force_trigger=bool(pending.get("force")) or count >= 3,
        )

    def _switch_stream_to_software(self, remote_label: str):
        source = self.display_sources.get(remote_label)
        if not source:
            return
        remote_pad = source.get("remote_pad")
        pad_name = source.get("pad_name")
        bin_obj = source.get("bin")
        sink_pad = source.get("bin_sink_pad")
        if not remote_pad or not pad_name:
            return
        probe_id = None
        try:
            probe_id = remote_pad.add_probe(
                Gst.PadProbeType.BLOCK_DOWNSTREAM, lambda *args: Gst.PadProbeReturn.OK
            )
        except Exception:
            probe_id = None
        try:
            if sink_pad and remote_pad.is_linked():
                remote_pad.unlink(sink_pad)
        except Exception:
            pass
        try:
            self._release_display_source(remote_label)
        except Exception:
            pass
        if bin_obj:
            try:
                bin_obj.set_state(Gst.State.NULL)
            except Exception:
                pass
            try:
                self.pipe.remove(bin_obj)
            except Exception:
                pass

        if not self.display_sources:
            self._last_viewer_codec = None

        if not self.display_sources:
            self._last_viewer_codec = None
        self._active_hw_decoder_streams.discard(remote_label)
        self.display_remote_map.pop(pad_name, None)
        caps_name = source.get("caps_name")
        if not caps_name:
            try:
                caps = remote_pad.get_current_caps()
                caps_name = caps.to_string() if caps else ""
            except Exception:
                caps_name = ""
        try:
            new_label = self._attach_viewer_video_stream(remote_pad, caps_name)
        finally:
            if probe_id is not None:
                try:
                    remote_pad.remove_probe(probe_id)
                except Exception:
                    pass
        if not new_label:
            printwarn("Hardware decoder fallback failed to rebuild viewer pipeline; display may remain blank.")
        else:
            if pad_name not in self.display_remote_map:
                self.display_remote_map[pad_name] = new_label
            if getattr(self, "display_state", None) != "remote":
                self._set_display_mode("remote", remote_label=new_label)

    def _prime_viewer_display(self):
        """Bring up the idle splash as soon as the viewer starts."""
        if not self.view:
            return

        newly_created = self._ensure_main_pipeline(log=False)
        if not self.pipe:
            return

        try:
            if self.v4l2sink:
                if not self.v4l2sink_device:
                    printwarn("V4L2 sink enabled but no writable device detected.")
                else:
                    self._ensure_v4l2sink_chain()
                    if not self.v4l2sink_sources and self.v4l2sink_state != "idle":
                        self._set_v4l2sink_mode("idle")
            else:
                self._ensure_display_chain()
                if not self.display_remote_map and self.display_state != "idle":
                    self._set_display_mode("idle")
        except Exception as exc:
            printwarn(f"Failed to prepare viewer output: {exc}")

        try:
            state = self.pipe.get_state(0)[1]
        except Exception:
            state = None

        if state not in (Gst.State.PLAYING, Gst.State.PAUSED):
            try:
                self.pipe.set_state(Gst.State.PLAYING)
            except Exception as exc:
                printwarn(f"Failed to start viewer pipeline for splash: {exc}")

    def _ensure_display_chain(self):
        """Ensure viewer display selector and sink are ready."""
        if not self.pipe:
            return None

        if getattr(self, "_display_chain_unavailable", False):
            return None

        selector_name = "viewer_display_selector"
        if self.display_selector and self.pipe.get_by_name(selector_name):
            return self._display_chain_config

        # Clean up any cached state if we lost the pipeline
        self._reset_display_chain_state()

        sink_override = getattr(self, "_display_sink_override", None)
        outsink = sink_override or select_display_sink("autovideosink")
        self._display_sink_last_choice = outsink
        print(f"Selected display sink pipeline: {outsink}")

        sink_base = outsink.split()[0]
        jetson_caps = {
            "nvdrmvideosink": "video/x-raw(memory:NVMM),format=NV12,pixel-aspect-ratio=1/1",
            "nv3dsink": "video/x-raw(memory:NVMM),format=NV12,pixel-aspect-ratio=1/1",
            "nvoverlaysink": "video/x-raw(memory:NVMM),format=NV12,pixel-aspect-ratio=1/1",
        }
        fb_size = get_framebuffer_resolution()
        nvvidconv_has_nvbuf = gst_element_supports_property("nvvidconv", "nvbuf-memory-type")
        needs_system_memory = sink_base not in jetson_caps
        debug_display = bool(os.environ.get("RN_DEBUG_DISPLAY"))

        if sink_base in jetson_caps:
            outsink = outsink.replace(sink_base, f"{sink_base} name=jetson_display_sink", 1)

        if not getattr(self, "_display_surface_cleared", False):
            if clear_display_surfaces():
                printc("🧹 Cleared display surface before viewer output", "66F")
            self._display_surface_cleared = True

        selector_factory_names = ("input-selector", "inputselector")
        self.display_selector = None
        for selector_factory in selector_factory_names:
            selector = Gst.ElementFactory.make(selector_factory, selector_name)
            if selector:
                self.display_selector = selector
                print(f"[display] Using selector factory `{selector_factory}`")
                try:
                    if selector.find_property("cache-buffers"):
                        selector.set_property("cache-buffers", True)
                except Exception:
                    pass
                break
        if not self.display_selector:
            self._display_direct_mode = True
            printwarn(
                "Viewer display fallback active: GStreamer `input-selector` element is unavailable. "
                "Local preview limited to a single stream without splash screens."
            )
        else:
            self.pipe.add(self.display_selector)
            print(f"[display] Input selector initialized")

        sink_desc = "queue max-size-buffers=2 leaky=downstream ! " + outsink
        self.display_sink_bin = Gst.parse_bin_from_description(sink_desc, True)
        self.display_sink_bin.set_name("viewer_display_sink_bin")
        self.pipe.add(self.display_sink_bin)

        if self.display_selector:
            if not Gst.Element.link(self.display_selector, self.display_sink_bin):
                raise RuntimeError("Failed to link display selector to sink pipeline")
            self.display_selector.sync_state_with_parent()
        else:
            sink_pad = self.display_sink_bin.get_static_pad("sink")
            if sink_pad and sink_pad.is_linked():
                peer = sink_pad.get_peer()
                if peer:
                    sink_pad.unlink(peer)
            self.current_display_pad = sink_pad

        self.display_sink_bin.sync_state_with_parent()

        if sink_base in jetson_caps:
            jetson_sink_element = self.pipe.get_by_name("jetson_display_sink")
            if jetson_sink_element and fb_size:
                try:
                    jetson_sink_element.set_property("overlay", 1)
                    jetson_sink_element.set_property("overlay-x", 0)
                    jetson_sink_element.set_property("overlay-y", 0)
                    jetson_sink_element.set_property("overlay-w", fb_size[0])
                    jetson_sink_element.set_property("overlay-h", fb_size[1])
                    if hasattr(jetson_sink_element.props, "window_width"):
                        jetson_sink_element.set_property("window-width", fb_size[0])
                    if hasattr(jetson_sink_element.props, "window_height"):
                        jetson_sink_element.set_property("window-height", fb_size[1])
                except Exception as exc:
                    if debug_display:
                        print(f"Failed to configure overlay geometry: {exc}")

                if jetson_sink_element and 'GLib' in globals():
                    _stats_counter = {"count": 0}

                    def _log_sink_stats():
                        try:
                            stats = jetson_sink_element.get_property("stats")
                            if stats:
                                print(f"Jetson display sink stats: {stats.to_string()}")
                            else:
                                print("Jetson display sink stats: unavailable")
                        except Exception as exc:
                            print(f"Failed to query jetson display sink stats: {exc}")
                            return False
                        _stats_counter["count"] += 1
                        return _stats_counter["count"] < 12

                    GLib.timeout_add_seconds(5, _log_sink_stats)

        def build_conversion_chain(using_hw_decoder: bool) -> str:
            if sink_base in jetson_caps and gst_element_available("nvvidconv"):
                target_caps = jetson_caps[sink_base]
                if fb_size and getattr(self, "stretch_display", False):
                    target_caps += f",width=(int){fb_size[0]},height=(int){fb_size[1]}"
                return f"nvvidconv ! {target_caps}"
            if using_hw_decoder and gst_element_available("nvvidconv"):
                return (
                    "nvvidconv ! "
                    "video/x-raw,format=NV12 ! "
                    "videoconvert ! video/x-raw,format=RGB"
                )
            if sink_base == "xvimagesink":
                return "videoconvert ! video/x-raw,format=I420"
            if sink_base in {"gtksink", "ximagesink"}:
                return "videoconvert ! video/x-raw,format=BGRx"
            if sink_base == "glimagesink":
                return "videoconvert ! video/x-raw,format=RGBA"
            return "videoconvert ! video/x-raw,format=BGRx"

        self._display_chain_config = {
            "sink_base": sink_base,
            "fb_size": fb_size,
            "jetson_caps": jetson_caps,
            "nvvidconv_has_nvbuf": nvvidconv_has_nvbuf,
            "needs_system_memory": needs_system_memory,
            "debug_display": debug_display,
            "build_conversion_chain": build_conversion_chain,
            "direct_mode": self._display_direct_mode,
        }
        self._display_chain_unavailable = False
        self._display_chain_unavailable_reason = None

        if not self._display_direct_mode:
            self._ensure_splash_sources()
        return self._display_chain_config

    def _get_display_sink_base(self, sink_spec: Optional[str]) -> Optional[str]:
        """Extract the element factory name from a sink pipeline snippet."""
        if not sink_spec:
            return None
        sink_spec = sink_spec.strip()
        if not sink_spec:
            return None
        return sink_spec.split()[0]

    def _ensure_v4l2sink_chain(self):
        """Ensure viewer V4L2 sink selector and sink are ready."""
        if not self.pipe:
            return None

        if getattr(self, "_v4l2sink_chain_unavailable", False):
            return None

        selector_name = "viewer_v4l2sink_selector"
        if self.v4l2sink_selector and self.pipe.get_by_name(selector_name):
            return self._v4l2sink_chain_config

        self._reset_v4l2sink_chain_state()

        if not self.v4l2sink_device:
            reason = "No writable V4L2 sink device detected"
            printwarn(reason)
            self._v4l2sink_chain_unavailable = True
            self._v4l2sink_chain_unavailable_reason = reason
            return None

        selector_factory_names = ("input-selector", "inputselector")
        for selector_factory in selector_factory_names:
            selector = Gst.ElementFactory.make(selector_factory, selector_name)
            if selector:
                self.v4l2sink_selector = selector
                print(f"[v4l2sink] Using selector factory `{selector_factory}`")
                try:
                    if selector.find_property("cache-buffers"):
                        selector.set_property("cache-buffers", True)
                except Exception:
                    pass
                break

        if not self.v4l2sink_selector:
            reason = "Viewer V4L2 sink fallback active: GStreamer `input-selector` element is unavailable."
            printwarn(reason)
            self._v4l2sink_chain_unavailable = True
            self._v4l2sink_chain_unavailable_reason = reason
            return None

        self.pipe.add(self.v4l2sink_selector)
        print("[v4l2sink] Input selector initialized")

        caps = (
            f"video/x-raw,format={self.v4l2sink_format},width=(int){self.v4l2sink_width},"
            f"height=(int){self.v4l2sink_height},framerate=(fraction){self.v4l2sink_fps}/1"
        )
        sink_desc = (
            "queue max-size-buffers=2 leaky=downstream ! "
            "videorate ! videoscale ! videoconvert ! "
            f"{caps} ! "
            f"v4l2sink name=viewer_v4l2sink device={self.v4l2sink_device} sync=false"
        )
        self.v4l2sink_sink_bin = Gst.parse_bin_from_description(sink_desc, True)
        self.v4l2sink_sink_bin.set_name("viewer_v4l2sink_sink_bin")
        self.pipe.add(self.v4l2sink_sink_bin)

        if not Gst.Element.link(self.v4l2sink_selector, self.v4l2sink_sink_bin):
            raise RuntimeError("Failed to link V4L2 sink selector to sink pipeline")

        self.v4l2sink_selector.sync_state_with_parent()
        self.v4l2sink_sink_bin.sync_state_with_parent()

        self._v4l2sink_chain_config = {
            "caps": caps,
        }

        self._v4l2sink_chain_unavailable = False
        self._v4l2sink_chain_unavailable_reason = None

        self._ensure_v4l2sink_splash_sources()
        return self._v4l2sink_chain_config

    def _ensure_v4l2sink_splash_sources(self):
        """Create idle/blank sources for V4L2 sink output."""
        if not self.pipe or not self.v4l2sink_selector:
            return

        caps = (
            f"video/x-raw,format={self.v4l2sink_format},width=(int){self.v4l2sink_width},"
            f"height=(int){self.v4l2sink_height},framerate=(fraction){self.v4l2sink_fps}/1"
        )
        if "blank" not in self.v4l2sink_sources:
            try:
                blank_desc = (
                    "videotestsrc pattern=blue is-live=true ! videorate ! videoscale ! videoconvert ! "
                    f"{caps} ! queue max-size-buffers=2 leaky=downstream ! "
                    "identity name=v4l2sink_blank_identity"
                )
                blank_bin = Gst.parse_bin_from_description(blank_desc, True)
                blank_bin.set_name("viewer_v4l2sink_blank")
                self.pipe.add(blank_bin)
                self._link_v4l2sink_bin(blank_bin, "blank")
                print("[v4l2sink] Blank splash linked")
            except Exception as exc:
                printwarn(f"Failed to initialize V4L2 sink blank source: {exc}")

    def _link_v4l2sink_bin(self, bin_obj: Gst.Bin, label: str):
        """Connect a bin's output to the V4L2 sink selector."""
        if not self.v4l2sink_selector:
            raise RuntimeError("V4L2 sink selector is unavailable")

        src_pad = bin_obj.get_static_pad("src")
        if not src_pad:
            last_element = None
            try:
                iterator = bin_obj.iterate_sorted()
                while True:
                    res, elem = iterator.next()
                    if res == Gst.IteratorResult.OK:
                        last_element = elem
                    else:
                        break
            except Exception:
                last_element = None
            if last_element:
                pad = last_element.get_static_pad("src")
                if pad:
                    ghost = Gst.GhostPad.new("src", pad)
                    bin_obj.add_pad(ghost)
                    src_pad = ghost

        if not src_pad:
            raise RuntimeError(f"Failed to obtain src pad for V4L2 sink source '{label}'")

        pad_template = self.v4l2sink_selector.get_pad_template("sink_%u")
        selector_pad = self.v4l2sink_selector.request_pad(pad_template, None, None)
        if not selector_pad:
            raise RuntimeError("Failed to request pad from V4L2 sink selector")

        link_result = src_pad.link(selector_pad)
        if link_result != Gst.PadLinkReturn.OK:
            self.v4l2sink_selector.release_request_pad(selector_pad)
            raise RuntimeError(f"Failed to link V4L2 sink source '{label}': {link_result}")

        self.v4l2sink_sources[label] = {
            "bin": bin_obj,
            "selector_pad": selector_pad,
            "src_pad": src_pad,
        }
        bin_obj.sync_state_with_parent()
        return selector_pad

    def _activate_v4l2sink_source(self, label: str) -> bool:
        """Activate a registered source on the V4L2 sink selector."""
        source = self.v4l2sink_sources.get(label)
        if not source:
            print(f"[v4l2sink] Requested source '{label}' not registered")
            return False

        pad = source["selector_pad"]
        if pad == self.v4l2sink_current_pad:
            return True

        try:
            self.v4l2sink_selector.set_property("active-pad", pad)
            self.v4l2sink_current_pad = pad
            print(f"[v4l2sink] Activated source '{label}'")
            return True
        except Exception as exc:
            printwarn(f"Failed to activate V4L2 sink source '{label}': {exc}")
            return False

    def _set_v4l2sink_mode(self, mode: str, remote_label: Optional[str] = None):
        """Switch to the appropriate V4L2 sink source."""
        if mode == "remote" and remote_label:
            if remote_label in self.v4l2sink_sources:
                self._activate_v4l2sink_source(remote_label)
                self.v4l2sink_state = "remote"
                return
            printwarn(f"V4L2 sink remote source '{remote_label}' not registered")
        if "blank" in self.v4l2sink_sources:
            self._activate_v4l2sink_source("blank")
            self.v4l2sink_state = "idle"

    def _release_v4l2sink_source(self, label: str):
        """Detach and remove a registered V4L2 sink source."""
        source = self.v4l2sink_sources.pop(label, None)
        if not source:
            return

        self.v4l2sink_remote_map = {
            key: value
            for key, value in self.v4l2sink_remote_map.items()
            if value != label
        }

        selector_pad = source.get("selector_pad")
        if selector_pad:
            try:
                self.v4l2sink_selector.release_request_pad(selector_pad)
            except Exception:
                pass
            if selector_pad == self.v4l2sink_current_pad:
                self.v4l2sink_current_pad = None

        bin_obj = source.get("bin")
        if bin_obj:
            try:
                bin_obj.set_state(Gst.State.NULL)
            except Exception:
                pass
            try:
                self.pipe.remove(bin_obj)
            except Exception:
                pass

    def _release_all_v4l2sink_sources(self, include_blank: bool = True) -> None:
        labels = list(self.v4l2sink_sources.keys())
        for label in labels:
            if not include_blank and label == "blank":
                continue
            self._release_v4l2sink_source(label)

    def _reset_v4l2sink_chain_state(self):
        """Reset cached viewer V4L2 sink elements."""
        if getattr(self, "v4l2sink_sources", None):
            self._release_all_v4l2sink_sources()

        if getattr(self, "v4l2sink_selector", None) and self.pipe:
            try:
                self.v4l2sink_selector.set_state(Gst.State.NULL)
            except Exception:
                pass
            try:
                self.pipe.remove(self.v4l2sink_selector)
            except Exception:
                pass

        if getattr(self, "v4l2sink_sink_bin", None) and self.pipe:
            try:
                self.v4l2sink_sink_bin.set_state(Gst.State.NULL)
            except Exception:
                pass
            try:
                self.pipe.remove(self.v4l2sink_sink_bin)
            except Exception:
                pass

        self.v4l2sink_selector = None
        self.v4l2sink_sink_bin = None
        self.v4l2sink_sources = {}
        self.v4l2sink_current_pad = None
        self.v4l2sink_remote_map = {}
        self._v4l2sink_chain_config = None
        self._v4l2sink_chain_unavailable = False
        self._v4l2sink_chain_unavailable_reason = None

    def _select_alternate_display_sink(self, failed_base: Optional[str]) -> Optional[str]:
        """Choose a fallback display sink when the current one fails."""
        failed = set(getattr(self, "_display_sink_failed_bases", set()))
        if failed_base:
            failed.add(failed_base)
        self._display_sink_failed_bases = failed

        env_fallback = os.environ.get("RN_DISPLAY_FALLBACK")
        candidate_specs: List[str] = []
        if env_fallback:
            candidate_specs.extend([item.strip() for item in env_fallback.split(",") if item.strip()])

        if is_jetson_device():
            candidate_specs.extend(
                [
                    "nv3dsink sync=false",
                    "nvdrmvideosink sync=false",
                    "nveglglessink sync=false",
                ]
            )
        candidate_specs.extend(
            [
                "glimagesink sync=false",
                "autovideosink sync=false",
                "fakesink sync=true",
            ]
        )

        for candidate in candidate_specs:
            base = self._get_display_sink_base(candidate)
            if not base or (failed_base and base == failed_base) or base in failed:
                continue
            if base == "fakesink" or gst_element_available(base):
                return candidate
        return None

    def _handle_display_sink_error(self, err_text: Optional[str], debug_text: Optional[str]):
        """Attempt to recover the viewer display after sink resource failures."""
        if getattr(self, "_display_sink_recovery_active", False):
            return

        failed_base = self._get_display_sink_base(getattr(self, "_display_sink_last_choice", None))
        fallback = self._select_alternate_display_sink(failed_base)
        if not fallback:
            reason = (
                "Display sink entered an unrecoverable error state and no fallback sink is available. "
                "Set RN_FORCE_SINK or RN_DISPLAY_FALLBACK to a working sink to restore local preview."
            )
            printwarn(reason)
            self._display_chain_unavailable = True
            self._display_chain_unavailable_reason = reason
            return

        message_parts = ["Viewer display sink failure detected"]
        if err_text:
            message_parts.append(str(err_text))
        if debug_text and debug_text not in message_parts:
            message_parts.append(str(debug_text))
        printwarn(f"{'; '.join(message_parts)}; rebuilding with `{fallback}`")

        existing_sources: List[Tuple[Gst.Pad, str]] = []
        for source in list(getattr(self, "display_sources", {}).values()):
            pad = source.get("remote_pad")
            caps_name = source.get("caps_name") or ""
            if pad:
                existing_sources.append((pad, caps_name))

        self._display_sink_override = fallback
        self._display_sink_recovery_active = True
        try:
            self._reset_display_chain_state()
            self._ensure_display_chain()
            for pad, caps_name in existing_sources:
                try:
                    self._attach_viewer_video_stream(pad, caps_name)
                except Exception as exc:
                    printwarn(f"Failed to relink viewer stream for pad {pad.get_name()}: {exc}")
        finally:
            self._display_sink_recovery_active = False

    def _link_bin_to_display(self, bin_obj: Gst.Bin, label: str):
        """Connect a bin's output to the display selector."""
        if self._display_direct_mode:
            if not self.display_sink_bin:
                raise RuntimeError("Display sink bin is unavailable in direct mode")

            src_pad = bin_obj.get_static_pad("src")
            if not src_pad:
                last_element = None
                try:
                    iterator = bin_obj.iterate_sorted()
                    while True:
                        res, elem = iterator.next()
                        if res == Gst.IteratorResult.OK:
                            last_element = elem
                        else:
                            break
                except Exception:
                    last_element = None

                if last_element:
                    pad = last_element.get_static_pad("src")
                    if pad:
                        ghost = Gst.GhostPad.new("src", pad)
                        bin_obj.add_pad(ghost)
                        src_pad = ghost

            if not src_pad:
                raise RuntimeError(f"Failed to obtain src pad for display source '{label}'")

            sink_pad = self.display_sink_bin.get_static_pad("sink")
            if not sink_pad:
                raise RuntimeError("Display sink bin does not expose a sink pad")

            # Ensure only one source is linked in direct mode
            for existing_label in list(self.display_sources.keys()):
                self._release_display_source(existing_label)

            if sink_pad.is_linked():
                peer = sink_pad.get_peer()
                if peer:
                    sink_pad.unlink(peer)

            link_result = src_pad.link(sink_pad)
            if link_result != Gst.PadLinkReturn.OK:
                raise RuntimeError(f"Failed to link display source '{label}' directly: {link_result}")

            self.display_sources[label] = {
                "bin": bin_obj,
                "selector_pad": None,
                "src_pad": src_pad,
                "sink_pad": sink_pad,
            }
            bin_obj.sync_state_with_parent()
            self.current_display_pad = sink_pad
            return sink_pad

        if not self.display_selector:
            raise RuntimeError("Display selector is not initialized")

        src_pad = bin_obj.get_static_pad("src")
        if not src_pad:
            # Attempt to create a ghost pad from the last element
            last_element = None
            try:
                iterator = bin_obj.iterate_sorted()
                while True:
                    res, elem = iterator.next()
                    if res == Gst.IteratorResult.OK:
                        last_element = elem
                    else:
                        break
            except Exception:
                last_element = None

            if last_element:
                pad = last_element.get_static_pad("src")
                if pad:
                    ghost = Gst.GhostPad.new("src", pad)
                    bin_obj.add_pad(ghost)
                    src_pad = ghost

        if not src_pad:
            raise RuntimeError(f"Failed to obtain src pad for display source '{label}'")

        pad_template = self.display_selector.get_pad_template("sink_%u")
        selector_pad = self.display_selector.request_pad(pad_template, None, None)
        if not selector_pad:
            raise RuntimeError("Failed to request pad from display selector")

        link_result = src_pad.link(selector_pad)
        if link_result != Gst.PadLinkReturn.OK:
            self.display_selector.release_request_pad(selector_pad)
            raise RuntimeError(f"Failed to link display source '{label}': {link_result}")

        self.display_sources[label] = {
            "bin": bin_obj,
            "selector_pad": selector_pad,
            "src_pad": src_pad,
        }
        bin_obj.sync_state_with_parent()
        return selector_pad

    def _ensure_splash_sources(self):
        """Create idle/connecting/blank splashes when needed."""
        if not self.pipe or (not self.display_selector) or self._display_direct_mode:
            return

        if self.v4l2sink:
            return

        conversion_chain = None
        display_config = getattr(self, "_display_chain_config", None)
        fb_size = None
        cpu_caps = "video/x-raw,format=BGRx,framerate=30/1"
        if display_config:
            build_conversion_chain = display_config.get("build_conversion_chain")
            try:
                if callable(build_conversion_chain):
                    conversion_chain = build_conversion_chain(False)
            except Exception as exc:
                if display_config.get("debug_display"):
                    print(f"[display] Failed to build splash conversion chain: {exc}")
            fb_size = display_config.get("fb_size")
        if fb_size and all(isinstance(v, int) and v > 0 for v in fb_size):
            cpu_caps += (
                f",width=(int){fb_size[0]},height=(int){fb_size[1]},"
                "pixel-aspect-ratio=(fraction)1/1"
            )

        def _build_blank_description() -> str:
            parts = [
                "videotestsrc pattern=black is-live=true",
                "videoconvert",
                "videoscale",
                cpu_caps,
            ]
            if conversion_chain:
                parts.append(conversion_chain)
            parts.extend(
                [
                    "queue max-size-buffers=2 leaky=downstream",
                    "identity name=viewer_blank_identity",
                ]
            )
            return " ! ".join(parts)

        if "blank" not in self.display_sources:
            try:
                blank_desc = _build_blank_description()
                blank_bin = Gst.parse_bin_from_description(blank_desc, True)
                blank_bin.set_name("viewer_blank_source")
                self.pipe.add(blank_bin)
                self._link_bin_to_display(blank_bin, "blank")
                print("[display] Blank splash linked")
            except Exception as exc:
                printwarn(f"Failed to initialize blank splash source: {exc}")

        if self.splashscreen_idle and "idle" not in self.display_sources:
            idle_bin = self._create_splash_bin(self.splashscreen_idle, "idle", conversion_chain)
            if idle_bin:
                self.pipe.add(idle_bin)
                try:
                    self._link_bin_to_display(idle_bin, "idle")
                    print("[display] Idle splash linked")
                except Exception as exc:
                    printwarn(f"Failed to link idle splash: {exc}")
                    try:
                        self.pipe.remove(idle_bin)
                    except Exception:
                        pass

        if self.splashscreen_connecting and "connecting" not in self.display_sources:
            connecting_bin = self._create_splash_bin(
                self.splashscreen_connecting, "connecting", conversion_chain
            )
            if connecting_bin:
                self.pipe.add(connecting_bin)
                try:
                    self._link_bin_to_display(connecting_bin, "connecting")
                    print("[display] Connecting splash linked")
                except Exception as exc:
                    printwarn(f"Failed to link connecting splash: {exc}")
                    try:
                        self.pipe.remove(connecting_bin)
                    except Exception:
                        pass

    def _create_splash_bin(
        self, path: str, label: str, conversion_chain: Optional[str] = None
    ) -> Optional[Gst.Bin]:
        """Create a reusable bin that displays a still image."""
        original_path = path
        resolved_path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isfile(resolved_path):
            printwarn(f"Splash image not found for {label}: {original_path} (resolved: {resolved_path})")
            return None

        path = resolved_path
        escaped = path.replace("\\", "\\\\").replace('"', '\\"')
        cpu_caps = "video/x-raw,format=BGRx,framerate=30/1"
        display_config = getattr(self, "_display_chain_config", None)
        fb_size = None
        if display_config:
            fb_size = display_config.get("fb_size")
        if fb_size and all(isinstance(v, int) and v > 0 for v in fb_size):
            cpu_caps += (
                f",width=(int){fb_size[0]},height=(int){fb_size[1]},"
                "pixel-aspect-ratio=(fraction)1/1"
            )

        decoder_chain = "decodebin"
        lowered = path.lower()
        decoder_candidates = [
            ((".jpg", ".jpeg", ".jpe"), "jpegdec"),
            ((".png",), "pngdec"),
            ((".bmp", ".dib"), "bmpdec"),
            ((".gif",), "gifdec"),
            ((".tif", ".tiff"), "tiffdec"),
            ((".webp",), "webpdec"),
        ]
        for suffixes, decoder_name in decoder_candidates:
            if lowered.endswith(suffixes):
                if gst_element_available(decoder_name):
                    decoder_chain = decoder_name
                else:
                    if bool(os.environ.get("RN_DEBUG_DISPLAY")):
                        printwarn(
                            f"[display] Splash decoder `{decoder_name}` unavailable for {label}; "
                            "falling back to decodebin"
                        )
                break

        parts = [
            f'filesrc location="{escaped}"',
            decoder_chain,
            "videoconvert",
            "videoscale",
            "imagefreeze is-live=true",
            cpu_caps,
        ]
        if conversion_chain:
            parts.append(conversion_chain)
        parts.extend(
            [
                "queue max-size-buffers=2 leaky=downstream",
                f"identity name=viewer_{label}_identity",
            ]
        )
        desc = " ! ".join(parts)
        try:
            bin_obj = Gst.parse_bin_from_description(desc, True)
            bin_obj.set_name(f"viewer_{label}_splash")
            return bin_obj
        except Exception as exc:
            printwarn(f"Failed to build splash pipeline for {label} ({path}): {exc}")
            return None

    def _activate_display_source(self, label: str) -> bool:
        """Activate a registered source on the selector."""
        source = self.display_sources.get(label)
        if not source:
            print(f"[display] Requested source '{label}' not registered")
            return False

        if self._display_direct_mode:
            sink_pad = source.get("sink_pad")
            if sink_pad:
                self.current_display_pad = sink_pad
                return True
            return False

        pad = source["selector_pad"]
        if pad == self.current_display_pad:
            print(f"[display] Source '{label}' already active")
            return True

        try:
            self.display_selector.set_property("active-pad", pad)
            self.current_display_pad = pad
            print(f"[display] Activated source '{label}'")
            return True
        except Exception as exc:
            printwarn(f"Failed to activate display source '{label}': {exc}")
            return False

    def _set_display_mode(self, mode: str, remote_label: Optional[str] = None):
        """Switch to the appropriate splash/remote source."""
        print(f"[display] Switching mode -> {mode} (remote={remote_label})")
        if self._display_direct_mode:
            if mode == "remote" and remote_label:
                if self._activate_display_source(remote_label):
                    self.display_state = mode
            return

        if not self.display_selector:
            try:
                self._ensure_display_chain()
            except Exception as exc:
                printwarn(f"Failed to initialize display chain for mode '{mode}': {exc}")
                return
            if not self.display_selector:
                return

        preferred_labels = []
        if mode == "remote" and remote_label:
            preferred_labels = [remote_label]
        elif mode == "connecting":
            preferred_labels = ["connecting", "idle", "blank"]
        elif mode == "idle":
            preferred_labels = ["idle", "blank"]
        else:
            preferred_labels = [mode, "blank"]

        for label in preferred_labels:
            if self._activate_display_source(label):
                self.display_state = mode
                return

        # Fallback if nothing was activated
        if self._activate_display_source("blank"):
            self.display_state = mode

    def _resume_remote_display(self):
        """Return display to the first available remote source."""
        if not self.display_remote_map:
            return
        remote_label = next(iter(self.display_remote_map.values()), None)
        if remote_label:
            self._set_display_mode("remote", remote_label=remote_label)

    def _request_view_stream_restart(self):
        """Reissue a play request for the active viewer stream with controlled backoff."""
        if not self.view:
            return
        base_stream = getattr(self, "streamin", None)
        if not base_stream:
            return
        if getattr(self, "_shutdown_requested", False):
            return
        if not getattr(self, "_viewer_restart_enabled", True):
            return

        last_disconnect = getattr(self, "_viewer_last_disconnect", 0.0)
        if not last_disconnect:
            # Only send play requests if we've observed a disconnect event
            return

        now = time.monotonic()
        initial_delay = float(
            getattr(self, "_viewer_restart_initial_delay", getattr(self, "_viewer_restart_short_delay", 10.0))
        )
        short_delay = float(getattr(self, "_viewer_restart_short_delay", max(initial_delay, 30.0)))
        long_delay = float(getattr(self, "_viewer_restart_long_delay", max(short_delay, 180.0)))
        attempts = int(getattr(self, "_viewer_restart_attempts", 0))
        last_request = float(getattr(self, "_viewer_last_play_request", 0.0))

        if attempts == 0:
            min_gap = initial_delay
        elif attempts == 1:
            min_gap = short_delay
        else:
            min_gap = long_delay

        elapsed = (now - last_request) if last_request else float("inf")
        if elapsed < min_gap:
            remaining = max(1.0, min_gap - elapsed)
            if bool(os.environ.get("RN_DEBUG_DISPLAY")):
                print(f"[display] Viewer restart throttled; retrying play in {remaining:.1f}s")
            self._schedule_viewer_restart_retry(remaining)
            return

        stream_id = f"{base_stream}{self.hashcode or ''}"
        try:
            self.sendMessage({"request": "play", "streamID": stream_id})
            if bool(os.environ.get("RN_DEBUG_DISPLAY")):
                print(f"[display] Re-requested stream playback for '{stream_id}' (attempt {attempts + 1})")
        except Exception as exc:
            printwarn(f"Failed to re-request viewer stream '{stream_id}': {exc}")
            # If we fail to issue the request, retry later using the long delay backoff.
            self._schedule_viewer_restart_retry(long_delay)
            return

        self._viewer_last_play_request = now
        self._viewer_restart_attempts = attempts + 1

        # Schedule the next retry. After the first retry we fall back to a long-period cadence.
        next_delay = short_delay if self._viewer_restart_attempts == 1 else long_delay
        self._schedule_viewer_restart_retry(next_delay)

    def _cancel_viewer_restart_timer(self):
        timer = getattr(self, "_viewer_restart_timer", None)
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass
        self._viewer_restart_timer = None
        self._viewer_restart_pending = False

    def _schedule_viewer_restart_retry(self, delay: Optional[float] = None):
        if getattr(self, "_shutdown_requested", False):
            return
        if not getattr(self, "_viewer_restart_enabled", True):
            return
        if not self.view:
            return
        if delay is None:
            delay = float(getattr(self, "_viewer_restart_long_delay", 180.0))
        try:
            delay = float(delay)
        except (TypeError, ValueError):
            delay = float(getattr(self, "_viewer_restart_long_delay", 180.0))
        delay = max(1.0, delay)

        self._cancel_viewer_restart_timer()

        def _retry(scheduled_delay=delay):
            self._viewer_restart_timer = None
            if getattr(self, "_shutdown_requested", False):
                return
            if not getattr(self, "_viewer_restart_enabled", True):
                return
            self._viewer_restart_pending = False
            if bool(os.environ.get("RN_DEBUG_DISPLAY")):
                print(f"[display] Viewer restart timer fired after {scheduled_delay:.1f}s; retrying play request")
            self._request_view_stream_restart()

        timer = threading.Timer(delay, _retry)
        timer.daemon = True
        self._viewer_restart_timer = timer
        self._viewer_restart_pending = True
        timer.start()

    def _log_viewer_fec_stats(self, label: str, fecdec: Gst.Element) -> None:
        """Print recovered/unrecovered counters for a viewer-side FEC decoder."""
        try:
            recovered = int(fecdec.get_property("recovered"))
            unrecovered = int(fecdec.get_property("unrecovered"))
            color = "0AF" if recovered else "FF0"
            printc(
                f"Viewer FEC stats ({label}): recovered {recovered} packet(s), "
                f"unrecovered {unrecovered}",
                color,
            )
        except Exception as exc:
            if bool(os.environ.get("RN_DEBUG_VIEWER")):
                printwarn(f"[viewer] Failed to read FEC stats for {label}: {exc}")
        self._flush_viewer_fec_probe_counts(label)

    def _viewer_fec_trace_enabled(self) -> bool:
        return bool(os.environ.get("RN_TRACE_FEC"))

    def _viewer_fec_probe_bucket(self, key: str) -> Dict[str, int]:
        bucket = self._viewer_fec_probe_counts.get(key)
        if bucket is None:
            bucket = {"fec": 0, "primary": 0, "other": 0, "total": 0}
            self._viewer_fec_probe_counts[key] = bucket
        return bucket

    def _restart_viewer_for_redundancy_change(self):
        if not self.view:
            return
        base_stream = getattr(self, "streamin", None)
        if not base_stream:
            return
        self._viewer_last_disconnect = time.monotonic()
        self._request_view_stream_restart()

    def _handle_viewer_fec_probe_state(self, label: str, parity_seen: bool, bucket: Dict[str, int]) -> None:
        if not self._viewer_enable_fec:
            return
        if parity_seen:
            self._viewer_fec_last_source = label
            if self._viewer_fec_runtime_disabled:
                self._viewer_fec_runtime_disabled = False
                self._viewer_fec_notice_shown = False
                printc(
                    f"[viewer] ULPFEC parity detected from {label}; re-enabling viewer FEC on next restart.",
                    "0AF",
                )
                self._restart_viewer_for_redundancy_change()
            return

        if self._viewer_fec_runtime_disabled:
            return
        total_packets = bucket.get("total", 0)
        if total_packets < self._viewer_fec_no_parity_threshold:
            return
        if not self._viewer_fec_notice_shown:
            printwarn(
                f"[viewer] No ULPFEC packets observed after {total_packets} RED frames "
                f"(source {label}); disabling viewer FEC until parity appears."
            )
            self._viewer_fec_notice_shown = True
        self._viewer_fec_runtime_disabled = True
        self._viewer_fec_last_source = label
        self._restart_viewer_for_redundancy_change()

    def _record_viewer_fec_packet(
        self,
        pad_key: str,
        payload_type: int,
        ulpfec_pt: Optional[int],
        primary_pt: Optional[int],
        location: str,
        *,
        trace: bool,
    ) -> None:
        alias = self._viewer_fec_probe_aliases.get(pad_key)
        key = alias or pad_key
        bucket = self._viewer_fec_probe_bucket(key)
        bucket["total"] += 1
        parity_seen = False
        if ulpfec_pt is not None and payload_type == ulpfec_pt:
            bucket["fec"] += 1
            parity_seen = True
            if trace and (bucket["fec"] <= 5 or bucket["fec"] % 100 == 0):
                printc(
                    f"[viewer] FEC probe ({location}) observed ULPFEC payload {payload_type} "
                    f"(total parity frames seen: {bucket['fec']})",
                    "0AF",
                )
        elif primary_pt is not None and payload_type == primary_pt:
            bucket["primary"] += 1
        else:
            bucket["other"] += 1
            if trace and ulpfec_pt is not None and bucket["other"] <= 5:
                printc(
                    f"[viewer] FEC probe ({location}) saw payload {payload_type} but no ULPFEC "
                    f"(expected {ulpfec_pt})",
                    "FF0",
                )
        self._handle_viewer_fec_probe_state(alias or pad_key, parity_seen, bucket)

    def _install_viewer_fec_probe(
        self,
        element: Optional[Gst.Element],
        pad_name: Optional[str],
        redundancy_info: Dict[str, Any],
        location: str,
    ) -> None:
        if element is None:
            return
        pad = element.get_static_pad("sink")
        if pad is None:
            return
        pad_key = pad_name or pad.get_name() or element.get_name()
        if pad_key is None:
            return
        ulpfec_pt = redundancy_info.get("ulpfec_pt")
        primary_pt = redundancy_info.get("primary_payload")
        if ulpfec_pt is None and primary_pt is None:
            return

        trace_enabled = self._viewer_fec_trace_enabled()

        def _probe(
            _pad,
            info,
            *,
            pad_key=pad_key,
            ulpfec_pt=ulpfec_pt,
            primary_pt=primary_pt,
            location=location,
            trace_enabled=trace_enabled,
        ):
            buffer = info.get_buffer()
            if buffer is None:
                return Gst.PadProbeReturn.OK
            ok, rtp = GstRtp.RTPBuffer.map(buffer, Gst.MapFlags.READ)
            if not ok:
                return Gst.PadProbeReturn.OK
            try:
                payload_type = rtp.get_payload_type()
            finally:
                GstRtp.RTPBuffer.unmap(rtp)
            self._record_viewer_fec_packet(
                pad_key,
                payload_type,
                ulpfec_pt,
                primary_pt,
                location,
                trace=trace_enabled,
            )
            return Gst.PadProbeReturn.OK

        pad.add_probe(Gst.PadProbeType.BUFFER, _probe)

    def _register_viewer_fec_label(self, pad_name: Optional[str], label: Optional[str]) -> None:
        if not pad_name or not label:
            return
        previous = self._viewer_fec_probe_counts.pop(label, None)
        pad_counts = self._viewer_fec_probe_counts.pop(pad_name, None)
        merged = None
        if previous:
            merged = dict(previous)
        if pad_counts:
            if merged is None:
                merged = dict(pad_counts)
            else:
                for key, value in pad_counts.items():
                    merged[key] = merged.get(key, 0) + int(value)
        if merged:
            self._viewer_fec_probe_counts[label] = merged
        self._viewer_fec_probe_aliases[pad_name] = label

    def _flush_viewer_fec_probe_counts(self, label: str, pad_name: Optional[str] = None) -> None:
        bucket = self._viewer_fec_probe_counts.pop(label, None)
        if not bucket and pad_name:
            bucket = self._viewer_fec_probe_counts.pop(pad_name, None)
        if not bucket:
            return
        color = "0AF" if bucket.get("fec") else "FF0"
        printc(
            f"[viewer] FEC packet totals ({label}): parity={bucket.get('fec', 0)}, "
            f"primary={bucket.get('primary', 0)}, other={bucket.get('other', 0)}, "
            f"total RTP={bucket.get('total', 0)}",
            color,
        )

    def _on_viewer_fec_state_changed(
        self, element: Gst.Element, old_state: Gst.State, new_state: Gst.State, pending: Gst.State
    ) -> None:
        """Log FEC stats when the decoder transitions to NULL during teardown."""
        if new_state != Gst.State.NULL:
            return
        label = getattr(element, "_rn_remote_label", None)
        if not label:
            label = element.get_name() or "viewer_fec"
        self._log_viewer_fec_stats(label, element)

    def _log_fec_stats_for_pad(self, pad_name: str, label: str):
        """Lookup a viewer FEC decoder by pad name and log its stats."""
        if not pad_name or not self.pipe:
            return
        fecdec = self.pipe.get_by_name(f"viewer_rtpulpfecdec_{pad_name}")
        if fecdec:
            self._log_viewer_fec_stats(label, fecdec)

    def _release_display_source(self, label: str):
        """Detach and remove a registered display source."""
        source = self.display_sources.pop(label, None)
        if not source:
            return
        pad_name = source.get("pad_name")
        if source.get("using_hw_decoder"):
            self._active_hw_decoder_streams.discard(label)
        print(f"[display] Releasing source '{label}'")

        fecdec = source.get("fec_decoder")
        bin_obj = source.get("bin")
        if not fecdec and bin_obj is not None:
            fecdec = getattr(bin_obj, "rn_fec_decoder", None)
        if fecdec:
            self._log_viewer_fec_stats(label, fecdec)
        cached = self._viewer_fec_decoders.pop(label, None)
        if cached and cached is not fecdec:
            self._log_viewer_fec_stats(label, cached)
        self._flush_viewer_fec_probe_counts(label, pad_name)

        selector_pad = source.get("selector_pad")
        if selector_pad:
            try:
                self.display_selector.release_request_pad(selector_pad)
            except Exception:
                pass
            if selector_pad == self.current_display_pad:
                self.current_display_pad = None
        elif self._display_direct_mode:
            sink_pad = source.get("sink_pad")
            src_pad = source.get("src_pad")
            if sink_pad and src_pad:
                try:
                    if sink_pad.is_linked() and src_pad.is_linked():
                        src_pad.unlink(sink_pad)
                except Exception:
                    pass
            if sink_pad == self.current_display_pad:
                self.current_display_pad = None

        bin_obj = source.get("bin")
        if bin_obj:
            try:
                bin_obj.set_state(Gst.State.NULL)
            except Exception:
                pass
            try:
                self.pipe.remove(bin_obj)
            except Exception:
                pass

    def _release_all_display_sources(self, include_blank: bool = True) -> None:
        """Release all tracked display sources, optionally skipping the idle splash."""
        labels = list(getattr(self, "display_sources", {}).keys())
        for label in labels:
            if not include_blank and label == "blank":
                continue
            self._release_display_source(label)
        if not self.display_sources:
            self._viewer_fec_probe_counts.clear()
            self._viewer_fec_probe_aliases.clear()

    def _update_viewer_redundancy_from_sdp(self, sdp_text: str) -> None:
        """Parse the remote SDP for RED/ULPFEC payload mappings."""
        if not self.view or not sdp_text:
            return

        info: Dict[str, Any] = {
            "red_pt": None,
            "ulpfec_pt": None,
            "primary_payload": None,
            "primary_codec": None,
            "redundant_payloads": [],
        }

        payload_codecs: Dict[str, str] = {}
        fmtp_map: Dict[str, str] = {}
        in_video = False

        for raw_line in sdp_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("m="):
                in_video = line.lower().startswith("m=video")
                continue
            if not in_video:
                continue
            if line.startswith("a=rtpmap:"):
                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue
                payload_id = parts[0].split(":")[1]
                codec_name = parts[1].split("/")[0].upper()
                payload_codecs[payload_id] = codec_name
            elif line.startswith("a=fmtp:"):
                parts = line.split(None, 1)
                payload_id = parts[0].split(":")[1]
                fmtp_map[payload_id] = parts[1] if len(parts) > 1 else ""

        for payload_id, codec_name in payload_codecs.items():
            if codec_name == "RED" and info["red_pt"] is None:
                info["red_pt"] = int(payload_id)
            elif codec_name in {"ULPFEC", "FLEXFEC"} and info["ulpfec_pt"] is None:
                info["ulpfec_pt"] = int(payload_id)

        red_pt_key = str(info["red_pt"]) if info["red_pt"] is not None else None
        if red_pt_key and red_pt_key in fmtp_map:
            fmtp_value = fmtp_map[red_pt_key]
            payload_tokens: List[int] = []
            for token in re.split(r"[\\s/;,]+", fmtp_value):
                if not token:
                    continue
                if "=" in token:
                    _, rhs = token.split("=", 1)
                    token = rhs
                if token.isdigit():
                    payload_tokens.append(int(token))
            info["redundant_payloads"] = payload_tokens
            for payload in payload_tokens:
                codec_name = payload_codecs.get(str(payload))
                if codec_name and codec_name not in {"RTX", "RED", "ULPFEC", "FLEXFEC"}:
                    info["primary_payload"] = payload
                    info["primary_codec"] = codec_name
                    break
                if (
                    codec_name
                    and codec_name in {"ULPFEC", "FLEXFEC"}
                    and info["ulpfec_pt"] is None
                ):
                    info["ulpfec_pt"] = payload

        previous = getattr(self, "_viewer_redundancy_info", None)
        self._viewer_redundancy_info = info if info["red_pt"] else None
        if self._viewer_redundancy_info:
            if previous != self._viewer_redundancy_info:
                summary = f"Viewer SDP: RED payload {info['red_pt']}"
                if info["primary_codec"]:
                    summary += f" -> {info['primary_codec']} (payload {info['primary_payload']})"
                if info["ulpfec_pt"] is not None:
                    summary += f", ULPFEC payload {info['ulpfec_pt']}"
                printc(summary, "0AF")
        elif info["red_pt"] and not info["primary_codec"]:
            printwarn(
                "Viewer SDP includes RED/ULPFEC but no usable primary payload was detected; "
                "fallback may disable redundancy."
            )

    def _build_viewer_redundancy_bin(
        self,
        pad: Gst.Pad,
        payload_bin: Gst.Bin,
        redundancy_info: Dict[str, Any],
    ) -> Optional[Gst.Bin]:
        """Wrap the payload decoding chain with RED/ULPFEC depayloaders."""
        if not gst_element_available("rtpreddec"):
            printwarn("RED stream received but `rtpreddec` is unavailable in this GStreamer build.")
            return None

        queue = Gst.ElementFactory.make("queue", f"viewer_red_queue_{pad.get_name()}")
        reddec = Gst.ElementFactory.make("rtpreddec", f"viewer_rtpreddec_{pad.get_name()}")
        if not queue or not reddec:
            printwarn("Failed to allocate RED depayloading elements for viewer pipeline.")
            return None

        if redundancy_info.get("red_pt") is not None:
            try:
                reddec.set_property("pt", int(redundancy_info["red_pt"]))
            except Exception:
                pass

        wrapper = Gst.Bin.new(f"viewer_redundancy_wrapper_{pad.get_name()}")
        wrapper.add(queue)
        wrapper.add(reddec)

        input_caps_filter = None
        caps_tokens = ["application/x-rtp", "media=(string)video", "encoding-name=(string)RED"]
        if redundancy_info.get("red_pt") is not None:
            caps_tokens.append(f"payload=(int){int(redundancy_info['red_pt'])}")
        try:
            red_caps = Gst.Caps.from_string(", ".join(caps_tokens))
            input_caps_filter = Gst.ElementFactory.make(
                "capsfilter", f"viewer_red_caps_{pad.get_name()}"
            )
            if input_caps_filter:
                input_caps_filter.set_property("caps", red_caps)
        except Exception as exc:
            input_caps_filter = None
            if bool(os.environ.get("RN_DEBUG_VIEWER")):
                print(f"[viewer] Failed to construct RED caps filter: {exc}")

        current_downstream: Gst.Element = queue

        enable_fec = (
            redundancy_info.get("ulpfec_pt") is not None
            and gst_element_available("rtpulpfecdec")
            and gst_element_available("rtpstorage")
            and bool(getattr(self, "_viewer_enable_fec", False))
            and not getattr(self, "_viewer_fec_runtime_disabled", False)
        )

        storage = None
        jitter = None
        fecdec = None
        if enable_fec:
            self._install_viewer_fec_probe(queue, pad.get_name(), redundancy_info, "viewer_red_queue")
            storage = Gst.ElementFactory.make("rtpstorage", f"viewer_rtpstorage_{pad.get_name()}")
            jitter = Gst.ElementFactory.make("rtpjitterbuffer", f"viewer_rtpjitter_{pad.get_name()}")
            fecdec = Gst.ElementFactory.make("rtpulpfecdec", f"viewer_rtpulpfecdec_{pad.get_name()}")
            if not storage or not jitter or not fecdec:
                printwarn("Failed to allocate FEC recovery elements; continuing with RED only.")
                storage = None
                jitter = None
                fecdec = None
                enable_fec = False
        if enable_fec and storage and fecdec:
            wrapper.add(storage)
            wrapper.add(fecdec)
            if jitter:
                wrapper.add(jitter)
            try:
                storage.set_property("size-time", int(self._viewer_redundancy_history_ns))
            except Exception:
                pass
            try:
                fecdec.set_property("pt", int(redundancy_info["ulpfec_pt"]))
            except Exception:
                pass
            if jitter:
                try:
                    jitter.set_property("do-lost", True)
                except Exception:
                    pass
                try:
                    jitter.set_property("drop-on-late", True)
                except Exception:
                    pass
                try:
                    jitter_latency = getattr(self, "_viewer_redundancy_latency_ms", 200)
                    jitter.set_property("latency", max(150, int(jitter_latency)))
                except Exception:
                    pass

            if not Gst.Element.link(current_downstream, storage):
                printwarn("Failed to insert rtpstorage ahead of FEC decoder; falling back to RED-only.")
                wrapper.remove(storage)
                wrapper.remove(fecdec)
                if jitter:
                    wrapper.remove(jitter)
                    jitter.set_state(Gst.State.NULL)
                storage.set_state(Gst.State.NULL)
                fecdec.set_state(Gst.State.NULL)
                enable_fec = False
            elif jitter and not Gst.Element.link(storage, jitter):
                printwarn("Failed to link rtpstorage to jitterbuffer; falling back to RED-only.")
                wrapper.remove(storage)
                wrapper.remove(fecdec)
                wrapper.remove(jitter)
                storage.set_state(Gst.State.NULL)
                jitter.set_state(Gst.State.NULL)
                fecdec.set_state(Gst.State.NULL)
                enable_fec = False
            elif jitter and not Gst.Element.link(jitter, fecdec):
                printwarn("Failed to link jitterbuffer to rtpulpfecdec; falling back to RED-only.")
                wrapper.remove(storage)
                wrapper.remove(fecdec)
                wrapper.remove(jitter)
                storage.set_state(Gst.State.NULL)
                jitter.set_state(Gst.State.NULL)
                fecdec.set_state(Gst.State.NULL)
                enable_fec = False
            elif not jitter and not Gst.Element.link(storage, fecdec):
                printwarn("Failed to link rtpstorage to rtpulpfecdec; falling back to RED-only.")
                wrapper.remove(storage)
                wrapper.remove(fecdec)
                storage.set_state(Gst.State.NULL)
                fecdec.set_state(Gst.State.NULL)
                enable_fec = False
            else:
                current_downstream = fecdec
                internal_storage = None
                try:
                    internal_storage = storage.get_property("internal-storage")
                except Exception:
                    internal_storage = None
                if internal_storage is not None:
                    try:
                        fecdec.set_property("storage", internal_storage)
                    except Exception:
                        pass
                try:
                    pad_name = pad.get_name()
                except Exception:
                    pad_name = None
                if pad_name:
                    self._pending_viewer_fec_decoders[pad_name] = fecdec
                    if bool(os.environ.get("RN_DEBUG_VIEWER")):
                        print(f"[viewer] Pending FEC decoder registered for pad {pad_name}")
                try:
                    fecdec.connect("state-changed", self._on_viewer_fec_state_changed)
                except Exception:
                    pass
                setattr(wrapper, "rn_fec_decoder", fecdec)

        if not enable_fec:
            if getattr(self, "_viewer_fec_runtime_disabled", False):
                reason = "viewer FEC auto-disabled (no ULPFEC observed)"
            elif redundancy_info.get("ulpfec_pt") is None:
                reason = "no ULPFEC payload advertised"
            elif not bool(getattr(self, "_viewer_enable_fec", False)):
                reason = "viewer-side FEC disabled (run with --viewer-enable-fec to experiment)"
            elif not gst_element_available("rtpulpfecdec") or not gst_element_available("rtpstorage"):
                reason = "required gst-plugins-bad elements missing"
            else:
                reason = "FEC stage unavailable (allocation/link failure)"
            printc(
                f"Viewer: RED stream detected but ULPFEC recovery is unavailable ({reason}); "
                "continuing with RED-only redundancy.",
                "FF0",
            )

        if input_caps_filter:
            wrapper.add(input_caps_filter)
            if Gst.Element.link(current_downstream, input_caps_filter):
                current_downstream = input_caps_filter
            else:
                printwarn("Failed to insert RED caps filter; continuing without it.")
                wrapper.remove(input_caps_filter)
                input_caps_filter = None

        if not Gst.Element.link(current_downstream, reddec):
            printwarn("Failed to link RED decoder into viewer pipeline.")
            return None
        current_downstream = reddec

        output_capssetter = None
        primary_codec = redundancy_info.get("primary_codec")
        primary_payload = redundancy_info.get("primary_payload")
        if primary_codec or primary_payload is not None:
            output_caps_tokens = ["application/x-rtp", "media=(string)video", "clock-rate=(int)90000"]
            if primary_payload is not None:
                output_caps_tokens.append(f"payload=(int){int(primary_payload)}")
            if primary_codec:
                output_caps_tokens.append(f"encoding-name=(string){primary_codec.upper()}")
            try:
                output_caps = Gst.Caps.from_string(", ".join(output_caps_tokens))
                output_capssetter = Gst.ElementFactory.make(
                    "capssetter", f"viewer_redundancy_capssetter_{pad.get_name()}"
                )
                if output_capssetter:
                    output_capssetter.set_property("caps", output_caps)
                    output_capssetter.set_property("replace", True)
                    output_capssetter.set_property("join", False)
            except Exception as exc:
                output_capssetter = None
                if bool(os.environ.get("RN_DEBUG_VIEWER")):
                    print(f"[viewer] Failed to construct capssetter caps: {exc}")

        downstream_output: Gst.Element = current_downstream
        if output_capssetter:
            wrapper.add(output_capssetter)
            if Gst.Element.link(downstream_output, output_capssetter):
                downstream_output = output_capssetter
            else:
                printwarn("Failed to link capssetter after RED decoder; continuing without it.")
                wrapper.remove(output_capssetter)
                output_capssetter = None

        wrapper.add(payload_bin)
        payload_sink = payload_bin.get_static_pad("sink")
        payload_src = payload_bin.get_static_pad("src")
        if not payload_sink or not payload_src:
            printwarn("Viewer payload chain is missing static pads inside redundancy wrapper.")
            return None

        downstream_src = downstream_output.get_static_pad("src")
        if not downstream_src:
            printwarn("Viewer redundancy chain element is missing a src pad.")
            return None

        if downstream_src.link(payload_sink) != Gst.PadLinkReturn.OK:
            printwarn("Failed to link RED decoder output into viewer payload chain.")
            return None

        target_sink_pad = queue.get_static_pad("sink")
        if not target_sink_pad:
            printwarn("Viewer redundancy queue missing sink pad.")
            return None

        ghost_caps_tokens = ["application/x-rtp", "media=(string)video", "encoding-name=(string)RED"]
        if redundancy_info.get("red_pt") is not None:
            ghost_caps_tokens.append(f"payload=(int){int(redundancy_info['red_pt'])}")
        ghost_template = None
        try:
            ghost_caps = Gst.Caps.from_string(", ".join(ghost_caps_tokens))
            ghost_template = Gst.PadTemplate.new(
                f"viewer_red_sink_template_{pad.get_name()}",
                Gst.PadDirection.SINK,
                Gst.PadPresence.ALWAYS,
                ghost_caps,
            )
        except Exception:
            ghost_template = None

        if ghost_template:
            ghost_sink = Gst.GhostPad.new_no_target_from_template("sink", ghost_template)
            ghost_sink.set_target(target_sink_pad)
        else:
            ghost_sink = Gst.GhostPad.new("sink", target_sink_pad)

        if bool(os.environ.get("RN_DEBUG_VIEWER")):
            try:
                caps_debug = target_sink_pad.query_caps(None)
                if caps_debug is not None:
                    print(f"[viewer] redundancy ghost sink caps: {caps_debug.to_string()}")
            except Exception:
                pass
        wrapper.add_pad(ghost_sink)

        ghost_src = Gst.GhostPad.new("src", payload_src)
        wrapper.add_pad(ghost_src)

        message = f"Viewer: enabling RED depayloading (pt {redundancy_info.get('red_pt')})"
        if enable_fec and redundancy_info.get("ulpfec_pt") is not None:
            message += f" with ULPFEC recovery (pt {redundancy_info.get('ulpfec_pt')})"
        printc(message, "0AF")

        return wrapper

    def _maybe_disable_viewer_redundancy(self, caps_name: str) -> bool:
        """Auto-disable RED/ULPFEC when the viewer pipeline cannot unwrap it."""
        if not self.view:
            return False

        if not (self.force_red or not self.nored):
            # Already running without redundancy; nothing to change.
            return False

        if getattr(self, "_viewer_redundancy_autodisable", False):
            printwarn(
                "Viewer still receiving RED/ULPFEC video after redundancy fallback; "
                "display will stay blank until the publisher stops forcing RED."
            )
            return False

        self._viewer_redundancy_autodisable = True
        printwarn(
            "Incoming viewer video stream uses RED/ULPFEC, but the local pipeline "
            "cannot depayload it. Disabling redundancy and retrying without FEC."
        )
        self.force_red = False
        self.force_rtx_requested = False
        self.force_rtx = False
        self.nored = True

        webrtc = getattr(self, "webrtc", None)
        if webrtc:
            try:
                webrtc.set_property("preferred-fec-type", GstWebRTC.WebRTCFECType.NONE)
            except Exception:
                pass

        # Nudge the viewer restart logic so we request the stream again without RED.
        self._viewer_last_disconnect = time.monotonic()
        self._request_view_stream_restart()
        return True

    def _attach_viewer_video_stream(self, pad: Gst.Pad, caps_name: str) -> Optional[str]:
        """Attach incoming video pad to the display selector."""
        display_config = self._ensure_display_chain()
        if not display_config:
            message = (
                getattr(self, "_display_chain_unavailable_reason", None)
                or "Display pipeline not ready; cannot attach viewer stream"
            )
            printwarn(message)
            return None

        self._ensure_splash_sources()
        build_conversion_chain = display_config["build_conversion_chain"]
        needs_system_memory = display_config["needs_system_memory"]
        nvvidconv_has_nvbuf = display_config["nvvidconv_has_nvbuf"]
        debug_display = display_config["debug_display"]

        redundancy_info = getattr(self, "_viewer_redundancy_info", None)
        preferred_view_codec: Optional[str] = None
        if getattr(self, "vp8", False):
            preferred_view_codec = "VP8"
        elif getattr(self, "vp9", False):
            preferred_view_codec = "VP9"
        elif getattr(self, "av1", False):
            preferred_view_codec = "AV1"
        elif getattr(self, "h264", False):
            preferred_view_codec = "H264"
        needs_redundancy_chain = False
        codec_type: Optional[str] = None

        caps = pad.get_current_caps()
        caps_struct = None
        if caps and caps.get_size() > 0:
            try:
                caps_struct = caps.get_structure(0)
            except Exception:
                caps_struct = None

        encoding_name: Optional[str] = None
        if caps_struct and caps_struct.has_field("encoding-name"):
            try:
                encoding_name = caps_struct.get_string("encoding-name")
            except Exception:
                try:
                    value = caps_struct.get_value("encoding-name")
                except Exception:
                    value = None
                if isinstance(value, str):
                    encoding_name = value
        if not encoding_name:
            match = re.search(r"encoding-name=\(string\)([^,]+)", caps_name, flags=re.IGNORECASE)
            if match:
                encoding_name = match.group(1).strip().strip('"')

        encoding_upper = (encoding_name or "").upper()
        if encoding_upper in {"RED", "ULPFEC", "FLEXFEC"}:
            if redundancy_info:
                needs_redundancy_chain = True
                primary = redundancy_info.get("primary_codec")
                if primary:
                    codec_type = str(primary).upper()
                elif preferred_view_codec:
                    codec_type = preferred_view_codec
                    printwarn(
                        "Viewer SDP omitted primary codec details for RED stream; "
                        f"assuming {codec_type} based on viewer preference."
                    )
                    if redundancy_info:
                        redundancy_info = dict(redundancy_info)
                        redundancy_info["primary_codec"] = codec_type
                        self._viewer_redundancy_info = redundancy_info
                if codec_type is None and self._maybe_disable_viewer_redundancy(caps_name):
                    return None
            elif self._maybe_disable_viewer_redundancy(caps_name):
                return None
        else:
            if getattr(self, "_viewer_redundancy_autodisable", False):
                self._viewer_redundancy_autodisable = False
            if encoding_upper:
                codec_type = encoding_upper

        caps_upper = caps_name.upper()
        if codec_type is None:
            if "VP8" in caps_upper:
                codec_type = "VP8"
            elif "H264" in caps_upper:
                codec_type = "H264"
            elif "VP9" in caps_upper:
                codec_type = "VP9"
            elif "AV1" in caps_upper:
                codec_type = "AV1"

        using_hw_decoder = False
        if codec_type == "VP8":
            fallback_decoder = "vp8dec"
            decoder_desc, using_hw_decoder = self._get_decoder_description("VP8", fallback_decoder)
            if using_hw_decoder and needs_system_memory and not nvvidconv_has_nvbuf:
                printwarn(
                    "Jetson hardware VP8 decoder requires nvvidconv nvbuf-memory-type support "
                    "for desktop display sinks; falling back to software decoding."
                )
                decoder_desc = fallback_decoder
                using_hw_decoder = False
            if using_hw_decoder:
                decoder_name = decoder_desc.split()[0]
                printc(f"Using Jetson hardware decoder `{decoder_name}` for VP8", "0AF")
            conversion_chain = build_conversion_chain(using_hw_decoder)
            pipeline_desc = (
                "queue ! rtpvp8depay ! "
                f"{decoder_desc} ! "
                "queue max-size-buffers=0 max-size-time=0 ! "
                f"{conversion_chain} ! "
                "queue max-size-buffers=0 max-size-time=0 ! "
                f"identity name=view_identity_{pad.get_name()}"
            )
        elif codec_type == "H264":
            fallback_decoder = "openh264dec"
            decoder_desc, using_hw_decoder = self._get_decoder_description("H264", fallback_decoder)
            if using_hw_decoder and needs_system_memory and not nvvidconv_has_nvbuf:
                printwarn(
                    "Jetson hardware H264 decoder requires nvvidconv nvbuf-memory-type support "
                    "for desktop display sinks; falling back to software decoding."
                )
                decoder_desc = fallback_decoder
                using_hw_decoder = False
            if using_hw_decoder:
                decoder_name = decoder_desc.split()[0]
                printc(f"Using Jetson hardware decoder `{decoder_name}` for H264", "0AF")
            conversion_chain = build_conversion_chain(using_hw_decoder)
            pipeline_desc = (
                "queue ! rtph264depay ! h264parse ! "
                f"{decoder_desc} ! "
                "queue max-size-buffers=0 max-size-time=0 ! "
                f"{conversion_chain} ! "
                "queue max-size-buffers=0 max-size-time=0 ! "
                f"identity name=view_identity_{pad.get_name()}"
            )
        elif codec_type == "VP9":
            if not gst_element_available("rtpvp9depay"):
                printwarn(
                    "VP9 stream received but `rtpvp9depay` is unavailable. Install gst-plugins-bad 1.16+."
                )
                return None
            fallback_decoder = "vp9dec"
            decoder_desc, using_hw_decoder = self._get_decoder_description("VP9", fallback_decoder)
            if using_hw_decoder and needs_system_memory and not nvvidconv_has_nvbuf:
                printwarn(
                    "Jetson hardware VP9 decoder requires nvvidconv nvbuf-memory-type support "
                    "for desktop display sinks; falling back to software decoding."
                )
                decoder_desc = fallback_decoder
                using_hw_decoder = False
            if using_hw_decoder:
                decoder_name = decoder_desc.split()[0]
                printc(f"Using Jetson hardware decoder `{decoder_name}` for VP9", "0AF")
            conversion_chain = build_conversion_chain(using_hw_decoder)
            pipeline_desc = (
                "queue ! rtpvp9depay ! "
                f"{decoder_desc} ! "
                "queue max-size-buffers=0 max-size-time=0 ! "
                f"{conversion_chain} ! "
                "queue max-size-buffers=0 max-size-time=0 ! "
                f"identity name=view_identity_{pad.get_name()}"
            )
        elif codec_type == "AV1":
            if not gst_element_available("rtpav1depay"):
                printwarn(
                    "AV1 stream received but `rtpav1depay` is unavailable. Install gst-plugins-bad 1.24+ or gst-plugins-rs."
                )
                return None
            if not gst_element_available("av1parse"):
                printwarn("AV1 stream received but `av1parse` is unavailable. Install gst-plugins-rs or gst-plugins-bad.")
                return None
            fallback_decoder = "av1dec"
            decoder_desc, using_hw_decoder = self._get_decoder_description("AV1", fallback_decoder)
            if using_hw_decoder and needs_system_memory and not nvvidconv_has_nvbuf:
                printwarn(
                    "Selected AV1 hardware decoder requires nvvidconv nvbuf-memory-type support; falling back to software."
                )
                decoder_desc = fallback_decoder
                using_hw_decoder = False
            decoder_factory = decoder_desc.split()[0]
            if not gst_element_available(decoder_factory):
                printwarn(
                    f"AV1 decoder `{decoder_factory}` not found. Install gst-libav (av1dec) or another AV1 decoder plugin."
                )
                return None
            conversion_chain = build_conversion_chain(using_hw_decoder)
            pipeline_desc = (
                "queue ! rtpav1depay ! av1parse ! "
                f"{decoder_desc} ! "
                "queue max-size-buffers=0 max-size-time=0 ! "
                f"{conversion_chain} ! "
                "queue max-size-buffers=0 max-size-time=0 ! "
                f"identity name=view_identity_{pad.get_name()}"
            )
        else:
            printc(f"Unsupported video codec for viewer: {caps_name}", "F70")
            return None

        try:
            payload_bin = Gst.parse_bin_from_description(pipeline_desc, True)
        except Exception as exc:
            printwarn(f"Failed to build viewer video pipeline: {exc}")
            return None

        out = payload_bin
        if needs_redundancy_chain and redundancy_info:
            wrapper = self._build_viewer_redundancy_bin(pad, payload_bin, redundancy_info)
            if wrapper is None:
                if self._maybe_disable_viewer_redundancy(caps_name):
                    return None
            else:
                out = wrapper

        out.set_name(f"viewer_video_bin_{pad.get_name()}")
        self.pipe.add(out)

        sink_pad = out.get_static_pad("sink")
        if not sink_pad:
            printwarn("Viewer video bin does not expose a sink pad")
            self.pipe.remove(out)
            return None

        link_result = pad.link(sink_pad)
        if link_result != Gst.PadLinkReturn.OK:
            reason = link_result.value_nick if hasattr(link_result, "value_nick") else link_result
            src_caps = pad.get_current_caps() or pad.query_caps(None)
            sink_caps = None
            try:
                sink_caps = sink_pad.get_current_caps() or sink_pad.query_caps(None)
            except Exception:
                sink_caps = None
            if src_caps is not None:
                printwarn(f"Viewer video pad caps: {src_caps.to_string()}")
            if sink_caps is not None:
                printwarn(f"Viewer pipeline sink caps: {sink_caps.to_string()}")
            printwarn(f"Failed to link incoming video pad to viewer pipeline: {reason}")
            self.pipe.remove(out)
            return None

        remote_label = f"remote_{pad.get_name()}"
        if bool(os.environ.get("RN_DEBUG_VIEWER")):
            print(f"[viewer] Attaching pad {pad.get_name()} -> {remote_label}")
        try:
            self._link_bin_to_display(out, remote_label)
            self.display_remote_map[pad.get_name()] = remote_label
            self._register_viewer_fec_label(pad.get_name(), remote_label)
        except Exception as exc:
            printwarn(f"Failed to attach viewer video bin to display: {exc}")
            try:
                self.pipe.remove(out)
            except Exception:
                pass
            return None

        source_info = self.display_sources.get(remote_label)
        if source_info is not None:
            source_info.update(
                {
                    "bin": out,
                    "bin_sink_pad": sink_pad,
                    "remote_pad": pad,
                    "pad_name": pad.get_name(),
                    "caps_name": caps_name,
                    "codec": codec_type,
                    "using_hw_decoder": using_hw_decoder,
                }
            )
        try:
            fecdec = self._pending_viewer_fec_decoders.pop(pad.get_name(), None)
        except Exception:
            fecdec = None
        else:
            if fecdec and bool(os.environ.get("RN_DEBUG_VIEWER")):
                print(f"[viewer] Matched pending FEC decoder for {pad.get_name()}")
        if not fecdec:
            fecdec = getattr(out, "rn_fec_decoder", None)
        if fecdec:
            if source_info is not None:
                source_info["fec_decoder"] = fecdec
            self._viewer_fec_decoders[remote_label] = fecdec
            try:
                setattr(fecdec, "_rn_remote_label", remote_label)
            except Exception:
                pass
            if bool(os.environ.get("RN_DEBUG_VIEWER")):
                print(f"[viewer] Tracking FEC decoder for {remote_label}")
        if using_hw_decoder:
            self._active_hw_decoder_streams.add(remote_label)
            self._maybe_process_pending_hw_decoder_warning()
        else:
            self._active_hw_decoder_streams.discard(remote_label)

        if getattr(self, "_viewer_pending_idle", False):
            if debug_display:
                print("[display] Applying deferred idle splash after remote attachment")
            self._set_display_mode("idle")
            self._viewer_pending_idle = False

        if debug_display:
            print("Linked incoming video pad to display selector (viewer path)")

        if codec_type:
            self._last_viewer_codec = codec_type

        return remote_label

    def _attach_v4l2sink_video_stream(self, pad: Gst.Pad, caps_name: str) -> Optional[str]:
        """Attach incoming video pad to the V4L2 sink selector."""
        sink_config = self._ensure_v4l2sink_chain()
        if not sink_config:
            message = (
                getattr(self, "_v4l2sink_chain_unavailable_reason", None)
                or "V4L2 sink pipeline not ready; cannot attach viewer stream"
            )
            printwarn(message)
            return None

        self._ensure_v4l2sink_splash_sources()

        redundancy_info = getattr(self, "_viewer_redundancy_info", None)
        preferred_view_codec: Optional[str] = None
        if getattr(self, "vp8", False):
            preferred_view_codec = "VP8"
        elif getattr(self, "vp9", False):
            preferred_view_codec = "VP9"
        elif getattr(self, "av1", False):
            preferred_view_codec = "AV1"
        elif getattr(self, "h264", False):
            preferred_view_codec = "H264"
        needs_redundancy_chain = False
        codec_type: Optional[str] = None

        caps = pad.get_current_caps()
        caps_struct = None
        if caps and caps.get_size() > 0:
            try:
                caps_struct = caps.get_structure(0)
            except Exception:
                caps_struct = None

        encoding_name: Optional[str] = None
        if caps_struct and caps_struct.has_field("encoding-name"):
            try:
                encoding_name = caps_struct.get_string("encoding-name")
            except Exception:
                try:
                    value = caps_struct.get_value("encoding-name")
                except Exception:
                    value = None
                if isinstance(value, str):
                    encoding_name = value
        if not encoding_name:
            match = re.search(r"encoding-name=\(string\)([^,]+)", caps_name, flags=re.IGNORECASE)
            if match:
                encoding_name = match.group(1).strip().strip('"')

        encoding_upper = (encoding_name or "").upper()
        if encoding_upper in {"RED", "ULPFEC", "FLEXFEC"}:
            if redundancy_info:
                needs_redundancy_chain = True
                primary = redundancy_info.get("primary_codec")
                if primary:
                    codec_type = str(primary).upper()
                elif preferred_view_codec:
                    codec_type = preferred_view_codec
                    printwarn(
                        "Viewer SDP omitted primary codec details for RED stream; "
                        f"assuming {codec_type} based on viewer preference."
                    )
                    if redundancy_info:
                        redundancy_info = dict(redundancy_info)
                        redundancy_info["primary_codec"] = codec_type
                        self._viewer_redundancy_info = redundancy_info
                if codec_type is None and self._maybe_disable_viewer_redundancy(caps_name):
                    return None
            elif self._maybe_disable_viewer_redundancy(caps_name):
                return None
        else:
            if getattr(self, "_viewer_redundancy_autodisable", False):
                self._viewer_redundancy_autodisable = False
            if encoding_upper:
                codec_type = encoding_upper

        caps_upper = caps_name.upper()
        if codec_type is None:
            if "VP8" in caps_upper:
                codec_type = "VP8"
            elif "H264" in caps_upper:
                codec_type = "H264"
            elif "VP9" in caps_upper:
                codec_type = "VP9"
            elif "AV1" in caps_upper:
                codec_type = "AV1"

        fallback_pipeline = (
            "queue ! decodebin ! "
            "videoconvert ! videoscale ! videorate ! "
            f"video/x-raw,format={self.v4l2sink_format},width=(int){self.v4l2sink_width},"
            f"height=(int){self.v4l2sink_height},framerate=(fraction){self.v4l2sink_fps}/1 ! "
            f"identity name=v4l2sink_identity_{pad.get_name()}"
        )

        pipeline_desc = None
        if codec_type == "VP8":
            pipeline_desc = (
                "queue ! rtpvp8depay ! vp8dec ! videoconvert ! videoscale ! videorate ! "
                f"video/x-raw,format={self.v4l2sink_format},width=(int){self.v4l2sink_width},"
                f"height=(int){self.v4l2sink_height},framerate=(fraction){self.v4l2sink_fps}/1 ! "
                f"identity name=v4l2sink_identity_{pad.get_name()}"
            )
        elif codec_type == "H264":
            pipeline_desc = (
                "queue ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! videoscale ! videorate ! "
                f"video/x-raw,format={self.v4l2sink_format},width=(int){self.v4l2sink_width},"
                f"height=(int){self.v4l2sink_height},framerate=(fraction){self.v4l2sink_fps}/1 ! "
                f"identity name=v4l2sink_identity_{pad.get_name()}"
            )
        elif codec_type == "VP9":
            if not gst_element_available("rtpvp9depay"):
                printwarn(
                    "VP9 stream received but `rtpvp9depay` is unavailable. Install gst-plugins-bad 1.16+."
                )
                pipeline_desc = fallback_pipeline
            else:
                pipeline_desc = (
                    "queue ! rtpvp9depay ! vp9dec ! videoconvert ! videoscale ! videorate ! "
                    f"video/x-raw,format={self.v4l2sink_format},width=(int){self.v4l2sink_width},"
                    f"height=(int){self.v4l2sink_height},framerate=(fraction){self.v4l2sink_fps}/1 ! "
                    f"identity name=v4l2sink_identity_{pad.get_name()}"
                )
        elif codec_type == "AV1":
            if not gst_element_available("rtpav1depay") or not gst_element_available("av1parse"):
                printwarn(
                    "AV1 stream received but AV1 depay/parse plugins are unavailable. Using decodebin fallback."
                )
                pipeline_desc = fallback_pipeline
            else:
                pipeline_desc = (
                    "queue ! rtpav1depay ! av1parse ! av1dec ! videoconvert ! videoscale ! videorate ! "
                    f"video/x-raw,format={self.v4l2sink_format},width=(int){self.v4l2sink_width},"
                    f"height=(int){self.v4l2sink_height},framerate=(fraction){self.v4l2sink_fps}/1 ! "
                    f"identity name=v4l2sink_identity_{pad.get_name()}"
                )
        else:
            printc(f"Unsupported video codec for V4L2 sink: {caps_name}", "F70")
            pipeline_desc = fallback_pipeline

        try:
            payload_bin = Gst.parse_bin_from_description(pipeline_desc, True)
        except Exception as exc:
            printwarn(f"Failed to build V4L2 sink video pipeline: {exc}")
            return None

        out = payload_bin
        if needs_redundancy_chain and redundancy_info:
            wrapper = self._build_viewer_redundancy_bin(pad, payload_bin, redundancy_info)
            if wrapper is None:
                if self._maybe_disable_viewer_redundancy(caps_name):
                    return None
            else:
                out = wrapper

        out.set_name(f"viewer_v4l2sink_bin_{pad.get_name()}")
        self.pipe.add(out)

        sink_pad = out.get_static_pad("sink")
        if not sink_pad:
            printwarn("V4L2 sink video bin does not expose a sink pad")
            self.pipe.remove(out)
            return None

        link_result = pad.link(sink_pad)
        if link_result != Gst.PadLinkReturn.OK:
            reason = link_result.value_nick if hasattr(link_result, "value_nick") else link_result
            src_caps = pad.get_current_caps() or pad.query_caps(None)
            sink_caps = None
            try:
                sink_caps = sink_pad.get_current_caps() or sink_pad.query_caps(None)
            except Exception:
                sink_caps = None
            if src_caps is not None:
                printwarn(f"V4L2 sink video pad caps: {src_caps.to_string()}")
            if sink_caps is not None:
                printwarn(f"V4L2 sink pipeline sink caps: {sink_caps.to_string()}")
            printwarn(f"Failed to link incoming video pad to V4L2 sink pipeline: {reason}")
            self.pipe.remove(out)
            return None

        remote_label = f"remote_{pad.get_name()}"
        try:
            self._link_v4l2sink_bin(out, remote_label)
            self.v4l2sink_remote_map[pad.get_name()] = remote_label
        except Exception as exc:
            printwarn(f"Failed to attach V4L2 sink video bin: {exc}")
            try:
                self.pipe.remove(out)
            except Exception:
                pass
            return None

        source_info = self.v4l2sink_sources.get(remote_label)
        if source_info is not None:
            source_info.update(
                {
                    "bin": out,
                    "bin_sink_pad": sink_pad,
                    "remote_pad": pad,
                    "pad_name": pad.get_name(),
                    "caps_name": caps_name,
                    "codec": codec_type,
                }
            )

        if codec_type:
            self._last_viewer_codec = codec_type

        return remote_label

    def _sink_viewer_aux_pad(self, pad: Gst.Pad, caps_name: str, label: str) -> bool:
        """Link auxiliary RTP pads (such as RTX) to a drop sink so they don't disturb the viewer display."""
        if not self.pipe:
            return False
        try:
            aux_bin = Gst.parse_bin_from_description(
                "queue leaky=downstream max-size-buffers=0 max-size-time=0 max-size-bytes=0 ! "
                "fakesink sync=false async=false",
                True,
            )
        except Exception as exc:
            printwarn(f"Viewer: failed to build auxiliary {label} sink: {exc}")
            return False

        aux_bin.set_name(f"viewer_aux_bin_{pad.get_name()}")
        try:
            self.pipe.add(aux_bin)
            aux_bin.sync_state_with_parent()
        except Exception as exc:
            printwarn(f"Viewer: failed to add auxiliary {label} bin: {exc}")
            try:
                aux_bin.set_state(Gst.State.NULL)
            except Exception:
                pass
            return False

        sink_pad = aux_bin.get_static_pad("sink")
        if not sink_pad:
            printwarn("Viewer auxiliary bin does not expose a sink pad; cannot attach auxiliary stream.")
            try:
                self.pipe.remove(aux_bin)
            except Exception:
                pass
            return False

        result = pad.link(sink_pad)
        if result != Gst.PadLinkReturn.OK:
            reason = result.value_nick if hasattr(result, "value_nick") else result
            printwarn(f"Viewer: failed to link auxiliary {label} pad ({pad.get_name()}): {reason}")
            try:
                aux_bin.set_state(Gst.State.NULL)
            except Exception:
                pass
            try:
                self.pipe.remove(aux_bin)
            except Exception:
                pass
            return False

        aux_bins = getattr(self, "_viewer_aux_pad_bins", None)
        if aux_bins is None:
            aux_bins = {}
            self._viewer_aux_pad_bins = aux_bins
        aux_bins[pad.get_name()] = aux_bin
        printc(f"[viewer] Ignoring auxiliary {label} stream ({caps_name})", "777")
        return True

    def on_remote_pad_removed(self, webrtc, pad: Gst.Pad):
        """Handle removal of remote pads for viewer mode."""
        pad_name = pad.get_name()
        aux_bins = getattr(self, "_viewer_aux_pad_bins", None)
        if aux_bins:
            aux_bin = aux_bins.pop(pad_name, None)
            if aux_bin:
                print(f"[viewer] Auxiliary pad removed: {pad_name}")
                try:
                    aux_bin.set_state(Gst.State.NULL)
                except Exception:
                    pass
                try:
                    self.pipe.remove(aux_bin)
                except Exception:
                    pass
                return
        if self.v4l2sink:
            label = self.v4l2sink_remote_map.pop(pad_name, None)
            print(f"[v4l2sink] Remote pad removed: {pad_name} -> {label}")
            if not label:
                return
            self._release_v4l2sink_source(label)
            if self.v4l2sink_remote_map:
                next_label = next(iter(self.v4l2sink_remote_map.values()))
                self._set_v4l2sink_mode("remote", remote_label=next_label)
            else:
                self._set_v4l2sink_mode("idle")
            return

        remote_map = getattr(self, "display_remote_map", None)
        if remote_map is None:
            print(f"[display] Remote pad removed but display map missing: {pad_name}")
            return

        label = remote_map.pop(pad_name, None)
        print(f"[display] Remote pad removed: {pad_name} -> {label}")
        self._viewer_fec_probe_aliases.pop(pad_name, None)
        self._viewer_pending_idle = False
        if not label:
            return

        self._release_display_source(label)
        if self._display_direct_mode:
            self.display_state = "idle"
            return
        if not self.display_selector:
            return
        if remote_map:
            next_label = next(iter(remote_map.values()))
            self._set_display_mode("remote", remote_label=next_label)
        else:
            self._set_display_mode("idle")

    def on_incoming_stream(self, webrtc, pad):
        global time  # Ensure time refers to the global module
        try:
            if Gst.PadDirection.SRC != pad.direction:
                # Wrong pad direction, skip silently
                return
            caps = pad.get_current_caps()
            name = caps.to_string()

            detected_width = None
            detected_height = None
            encoding_name = None
            if caps is not None and caps.get_size() > 0:
                try:
                    structure = caps.get_structure(0)
                except Exception:
                    structure = None
                if structure:
                    if structure.has_field("width"):
                        detected_width = structure.get_value("width")
                    elif structure.has_field("video-width"):
                        detected_width = structure.get_value("video-width")
                    if structure.has_field("height"):
                        detected_height = structure.get_value("height")
                    elif structure.has_field("video-height"):
                        detected_height = structure.get_value("video-height")
                    if structure.has_field("encoding-name"):
                        try:
                            encoding_name = structure.get_string("encoding-name")
                        except Exception:
                            try:
                                value = structure.get_value("encoding-name")
                            except Exception:
                                value = None
                            if isinstance(value, str):
                                encoding_name = value
            if isinstance(detected_width, (int, float)) and isinstance(detected_height, (int, float)):
                detected_width = int(detected_width)
                detected_height = int(detected_height)
                if detected_width > 0 and detected_height > 0:
                    for client_data in self.clients.values():
                        if client_data and client_data.get("direction") == "receive":
                            client_data["_last_video_width"] = detected_width
                            client_data["_last_video_height"] = detected_height
                    if getattr(self, "_last_viewer_codec", None):
                        printc(f"📺 Remote video: {detected_width}x{detected_height} ({self._last_viewer_codec})", "0F0")
                    else:
                        printc(f"📺 Remote video: {detected_width}x{detected_height}", "0F0")

            # Parse codec info from caps
            if not encoding_name and "encoding-name=" in name:
                codec = name.split("encoding-name=(string)")[1].split(",")[0].split(")")[0]
                encoding_name = codec
            codec_info = f" [{encoding_name}]" if encoding_name else ""
            print(f"Incoming stream{codec_info}: {name}")
            encoding_upper = (encoding_name or "").upper()
            
            # In room recording mode, find the client from webrtc element
            if self.room_recording:
                # Find which client this webrtc belongs to
                client = None
                client_uuid = None
                for uuid, c in self.clients.items():
                    if c.get('webrtc') == webrtc:
                        client = c
                        client_uuid = uuid
                        break
                
                if client and client_uuid:
                    # Add streamID to client if not present
                    if 'streamID' not in client and client_uuid in self.room_streams:
                        client['streamID'] = self.room_streams[client_uuid]['streamID']
                    
                    self.on_new_stream_room(client, pad)
                    return
                else:
                    printc("Warning: Could not find client for webrtc element", "F00")
                    if self.puuid:
                        printc("This may occur with custom websocket servers that don't provide proper stream metadata", "F77")
            
            # Skip all recording logic if using subprocess mode
            if self.single_stream_recording:
                printc("   ⏭️  Skipping main process recording (handled by subprocess)", "77F")
                return
                
            if self.ndiout:
                print("NDI OUT")
                
                # Use direct mode (separate audio/video streams) to avoid combiner freezing
                use_direct_ndi = True  # Default to direct mode
                
                if use_direct_ndi:
                    # Direct NDI mode - separate audio/video sinks
                    if "video" in name:
                        ndi_element_name = "ndi_video_sink"
                        ndi_stream_suffix = "_video"
                    else:  # audio
                        ndi_element_name = "ndi_audio_sink"
                        ndi_stream_suffix = "_audio"
                        
                    ndi_sink = self.pipe.get_by_name(ndi_element_name)
                    if not ndi_sink:
                        print(f"Creating new NDI sink for {ndi_element_name}")
                        ndi_sink = Gst.ElementFactory.make("ndisink", ndi_element_name)
                        if not ndi_sink:
                            print("Failed to create ndisink element")
                            print("Make sure gst-plugin-ndi is installed:")
                            print("  - For Ubuntu/Debian: sudo apt install gstreamer1.0-plugins-bad")
                            print("  - Or download from: https://ndi.tv/tools/")
                            return
                        unique_ndi_name = self.ndiout + ndi_stream_suffix
                        ndi_sink.set_property("ndi-name", unique_ndi_name)
                        self.pipe.add(ndi_sink)
                        ndi_sink.sync_state_with_parent()
                        print(f"NDI sink name: {unique_ndi_name}")
                else:
                    # Combiner mode (has freezing issues)
                    ndi_combiner = self.pipe.get_by_name("ndi_combiner")
                    ndi_sink = self.pipe.get_by_name("ndi_sink")
                    
                    if not ndi_combiner:
                        print("Creating new NDI sink combiner")
                        ndi_combiner = Gst.ElementFactory.make("ndisinkcombiner", "ndi_combiner")
                    if not ndi_combiner:
                        print("Failed to create ndisinkcombiner element")
                        return
                    
                    # Set properties
                    ndi_combiner.set_property("latency", 800_000_000)  # 800ms
                    ndi_combiner.set_property("min-upstream-latency", 1_000_000_000)  # 1000ms
                    ndi_combiner.set_property("start-time-selection", 1)  # 1 corresponds to "first"

                    self.pipe.add(ndi_combiner)
                    ndi_combiner.sync_state_with_parent()
                    
                    ret = ndi_combiner.set_state(Gst.State.PLAYING)
                    if ret == Gst.StateChangeReturn.FAILURE:
                        print("Failed to set ndi_combiner to PLAYING state")
                        return
                
                    if not ndi_sink:
                        print("Creating new NDI sink")
                        ndi_sink = Gst.ElementFactory.make("ndisink", "ndi_sink")
                        if not ndi_sink:
                            print("Failed to create ndisink element")
                            return
                        unique_ndi_name = generate_unique_ndi_name(self.ndiout)
                        ndi_sink.set_property("ndi-name", unique_ndi_name)
                        self.pipe.add(ndi_sink)
                        ndi_sink.sync_state_with_parent()
                        print(f"NDI sink name: {ndi_sink.get_property('ndi-name')}")
                    
                    # Link ndi_combiner to ndi_sink
                    if not ndi_combiner.link(ndi_sink):
                        print("Failed to link ndi_combiner to ndi_sink")
                        return

                if "video" in name:
                    pad_name = "video"
                    # Detect video codec from caps
                    if "VP8" in name:
                        video_codec = "VP8"
                    elif "H264" in name:
                        video_codec = "H264"
                    elif "VP9" in name:
                        video_codec = "VP9"
                    else:
                        print(f"Unknown video codec in caps: {name}")
                        video_codec = "VP8"  # Default fallback
                    
                    if use_direct_ndi:
                        printc(f"   🎥 NDI VIDEO OUTPUT (Direct Mode) [{video_codec}]", "0F0")
                        printc(f"   🔄 Transcoding {video_codec} → UYVY for NDI", "FF0")
                        printc(f"   📐 Output: UYVY @ 30fps", "77F")
                        printc(f"   🎯 NDI Name: {self.ndiout}", "0FF")
                        printc(f"   ✅ No freezing issues in direct mode", "0F0")
                    else:
                        printc(f"   🎥 NDI VIDEO OUTPUT (Combiner Mode) [{video_codec}]", "FF0")
                        printc(f"   🔄 Transcoding {video_codec} → UYVY for NDI", "FF0")
                        printc(f"   📐 Output: UYVY @ 30fps", "77F")
                        printc(f"   🎯 NDI Name: {self.ndiout}", "0FF")
                        printc(f"   ⚠️  WARNING: Combiner mode freezes after ~1500-2000 buffers", "F00")
                        
                elif "audio" in name:
                    pad_name = "audio"
                    if use_direct_ndi:
                        printc(f"   🎤 NDI AUDIO OUTPUT (Direct Mode)", "0F0")
                        printc(f"   🔄 Transcoding OPUS → F32LE for NDI", "FF0")
                        printc(f"   📐 Output: 48kHz, 2ch, F32LE", "77F")
                    else:
                        printc(f"   🎤 NDI AUDIO OUTPUT (Combiner Mode)", "FF0")
                        printc(f"   🔄 Transcoding OPUS → F32LE for NDI", "FF0")
                        printc(f"   📐 Output: 48kHz, 2ch, F32LE", "77F")
                else:
                    print("Unsupported media type:", name)
                    return

                if not use_direct_ndi:
                    # Combiner mode - get pad from combiner
                    target_pad = ndi_combiner.get_static_pad(pad_name)
                    if target_pad:
                        print(f"{pad_name.capitalize()} pad already exists, using existing pad")
                    else:
                        target_pad = ndi_combiner.request_pad(ndi_combiner.get_pad_template(pad_name), None, None)
                        if target_pad is None:
                            print(f"Failed to get {pad_name} pad from ndi_combiner")
                            print("Available pad templates:")
                            for template in ndi_combiner.get_pad_template_list():
                                print(f"  {template.name_template}: {template.direction.value_name}")
                            print("Current pads:")
                            for pad in ndi_combiner.pads:
                                print(f"  {pad.get_name()}: {pad.get_direction().value_name}")
                            return

                    print(f"Got {pad_name} pad: {target_pad.get_name()}")

                # Create elements based on media type
                if pad_name == "video":
                    # Create codec-specific elements
                    if video_codec == "VP8":
                        depay = Gst.ElementFactory.make("rtpvp8depay", "vp8_depay")
                        decoder, _ = self._create_decoder_element("VP8", "vp8dec", "vp8_decode")
                        parser = None
                    elif video_codec == "H264":
                        depay = Gst.ElementFactory.make("rtph264depay", "h264_depay")
                        parser = Gst.ElementFactory.make("h264parse", "h264_parse")
                        decoder, _ = self._create_decoder_element("H264", "avdec_h264", "h264_decode")
                    elif video_codec == "VP9":
                        depay = Gst.ElementFactory.make("rtpvp9depay", "vp9_depay")
                        decoder, _ = self._create_decoder_element("VP9", "vp9dec", "vp9_decode")
                        parser = None
                    else:
                        print(f"Unsupported video codec: {video_codec}")
                        return
                        
                    # Start with depay (which accepts RTP caps), then queue
                    elements = [depay]
                    if parser:
                        elements.append(parser)
                    elements.extend([
                        decoder,
                        Gst.ElementFactory.make("queue", f"{pad_name}_queue"),
                        Gst.ElementFactory.make("videoconvert", "video_convert"),
                        Gst.ElementFactory.make("videoscale", "video_scale"),
                        Gst.ElementFactory.make("videorate", "video_rate"),
                        Gst.ElementFactory.make("capsfilter", "video_caps"),
                    ])
                    # Use UYVY for best NDI performance
                    elements[-1].set_property("caps", Gst.Caps.from_string("video/x-raw,format=UYVY,framerate=30/1"))
                else:  # audio
                    # Start with depay (which accepts RTP caps), then queue
                    elements = [
                        Gst.ElementFactory.make("rtpopusdepay", "opus_depay"),
                        Gst.ElementFactory.make("opusdec", "opus_decode"),
                        Gst.ElementFactory.make("queue", f"{pad_name}_queue"),
                        Gst.ElementFactory.make("audioconvert", "audio_convert"),
                        Gst.ElementFactory.make("audioresample", "audio_resample"),
                        Gst.ElementFactory.make("capsfilter", "audio_caps"),
                    ]
                    elements[-1].set_property("caps", Gst.Caps.from_string("audio/x-raw,format=F32LE,channels=2,rate=48000,layout=interleaved"))

                if not all(elements):
                    print("Couldn't create all elements")
                    for i, elem in enumerate(elements):
                        if not elem:
                            print(f"  Element {i} is None")
                    return

                # Create a bin for the elements with unique name
                import time
                bin_name = f"{pad_name}_bin_{int(time.time() * 1000)}"
                element_bin = Gst.Bin.new(bin_name)
                for element in elements:
                    element_bin.add(element)

                # Link elements within the bin
                for i in range(len(elements) - 1):
                    if not elements[i].link(elements[i+1]):
                        print(f"Failed to link {elements[i].get_name()} to {elements[i+1].get_name()}")
                        return

                # Add ghost pads to the bin
                sink_pad = elements[0].get_static_pad("sink")
                ghost_sink = Gst.GhostPad.new("sink", sink_pad)
                element_bin.add_pad(ghost_sink)

                src_pad = elements[-1].get_static_pad("src")
                ghost_src = Gst.GhostPad.new("src", src_pad)
                element_bin.add_pad(ghost_src)

                # Add the bin to the pipeline
                self.pipe.add(element_bin)
                
                # Set to NULL first to ensure clean state
                element_bin.set_state(Gst.State.NULL)
                element_bin.sync_state_with_parent()

                # Link the bin to NDI output
                if use_direct_ndi:
                    # Direct mode - link directly to NDI sink
                    if not element_bin.link(ndi_sink):
                        print(f"Failed to link {bin_name} to NDI sink")
                        print(f"Bin src caps: {ghost_src.query_caps().to_string()}")
                        return
                else:
                    # Combiner mode - link to combiner
                    if not element_bin.link_pads("src", ndi_combiner, target_pad.get_name()):
                        print(f"Failed to link {bin_name} to ndi_combiner:{target_pad.get_name()}")
                        print(f"Bin src caps: {ghost_src.query_caps().to_string()}")
                        print(f"Target pad caps: {target_pad.query_caps().to_string()}")
                        return

                # Link the incoming pad to the bin
                print(f"Attempting to link incoming pad to {bin_name}")
                
                # Debug caps before linking
                incoming_caps = pad.get_current_caps()
                if incoming_caps:
                    print(f"Incoming pad current caps: {incoming_caps.to_string()}")
                else:
                    print("Incoming pad has no current caps")
                    
                # Check if caps are compatible
                ghost_sink_caps = ghost_sink.query_caps()
                print(f"Ghost sink accepts caps: {ghost_sink_caps.to_string()[:200]}...")
                
                if incoming_caps and not ghost_sink_caps.can_intersect(incoming_caps):
                    print("WARNING: Caps are not compatible!")
                
                link_result = pad.link(ghost_sink)
                if link_result != Gst.PadLinkReturn.OK:
                    print(f"Failed to link incoming pad to {bin_name}: {link_result}")
                    print(f"Link error code: {link_result.value_name if hasattr(link_result, 'value_name') else link_result}")
                    
                    # More detailed debugging
                    print(f"Incoming pad name: {pad.get_name()}")
                    print(f"Ghost sink name: {ghost_sink.get_name()}")
                    print(f"Element bin state: {element_bin.get_state(0)}")
                    
                    # Check first element caps specifically
                    first_elem_sink = elements[0].get_static_pad("sink")
                    if first_elem_sink:
                        print(f"First element ({elements[0].get_name()}) sink caps: {first_elem_sink.query_caps().to_string()[:200]}...")
                    
                    return

                print(f"NDI {pad_name} pipeline set up successfully")

                # Set the bin to PLAYING state
                ret = element_bin.set_state(Gst.State.PLAYING)
                if ret == Gst.StateChangeReturn.FAILURE:
                    print(f"Failed to set {bin_name} to PLAYING state")
                    return

                print(f"All elements in {bin_name} set to PLAYING state")

            elif "video" in name:
                if self.novideo:
                    printc('Ignoring incoming video track', "F88")
                    out = Gst.parse_bin_from_description("queue ! fakesink", True)
                    
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    if not sink:
                        print("Display bin has no sink pad; cannot link incoming video pad (novideo path)")
                        return
                    try:
                        sink_parent = sink.get_parent()
                        parent_name = sink_parent.get_name() if sink_parent else 'None'
                    except Exception as exc:
                        parent_name = f"error: {exc}"
                    print(f"Display bin sink pad parent (view path): {parent_name}", flush=True)
                    try:
                        sink_parent = sink.get_parent()
                        parent_name = sink_parent.get_name() if sink_parent else 'None'
                    except Exception as exc:
                        parent_name = f"error: {exc}"
                    print(f"Display bin sink pad parent (view path): {parent_name}")

                    sink_caps = sink.query_caps(None)
                    print(f"Display bin sink caps (novideo path): {sink_caps.to_string() if sink_caps else 'unknown'}")
                    link_result = pad.link(sink)
                    if link_result != Gst.PadLinkReturn.OK:
                        reason = link_result.value_nick if hasattr(link_result, "value_nick") else link_result
                        print(f"Failed to link incoming video pad to display bin (novideo path): {reason}")
                    else:
                        print("Linked incoming video pad to display bin successfully (novideo path)")
                    return

                if self.ndiout:
                   # I'm handling this on elsewhere now
                   pass
                elif self.socketout:
                    print("SOCKET VIDEO OUT")
                    out = Gst.parse_bin_from_description(
                        "queue ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR ! appsink name=appsink emit-signals=true", True)
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    link_result = pad.link(sink)
                    if link_result != Gst.PadLinkReturn.OK:
                        reason = link_result.value_nick if hasattr(link_result, "value_nick") else link_result
                        print(f"Failed to link incoming video pad to display bin (socketout path): {reason}")
                    else:
                        print("Linked incoming video pad to display bin successfully (socketout path)")
                    
                    appsink = self.pipe.get_by_name('appsink')
                    appsink.connect("new-sample", self.on_new_socket_sample)
                elif (self.view or self.v4l2sink) and "video" in name.lower():
                    if encoding_upper == "RTX":
                        if self._sink_viewer_aux_pad(pad, name, "RTX"):
                            return
                        printwarn("Failed to attach auxiliary RTX pad; stream may continue without retransmissions.")
                        return
                    if self.v4l2sink_device:
                        remote_label = self._attach_v4l2sink_video_stream(pad, name)
                        if remote_label:
                            self._set_v4l2sink_mode("remote", remote_label=remote_label)
                        else:
                            self._set_v4l2sink_mode("idle")
                        return

                    print("DISPLAY OUTPUT MODE BEING SETUP")
                    if self.recording_enabled and "video" in name:
                        if self.setup_recording_pipeline(pad, name):
                            return  # Recording set up successfully

                    remote_label = self._attach_viewer_video_stream(pad, name)
                    if remote_label:
                        self._set_display_mode("remote", remote_label=remote_label)
                    else:
                        self._set_display_mode("connecting")
                    return

                elif self.fdsink:
                    print("FD SINK OUT")
                    queue = Gst.ElementFactory.make("queue", "fd_queue")
                    depay = None
                    parse = None
                    decode = None
                    convert = Gst.ElementFactory.make("videoconvert", "fd_convert")
                    scale = Gst.ElementFactory.make("videoscale", "fd_scale")
                    caps_filter = Gst.ElementFactory.make("capsfilter", "fd_caps")
                    sink = Gst.ElementFactory.make("fdsink", "fd_sink")

                    if "VP8" in name:
                        depay = Gst.ElementFactory.make("rtpvp8depay", "vp8_depay")
                        decode = Gst.ElementFactory.make("vp8dec", "vp8_decode")
                    elif "H264" in name:
                        depay = Gst.ElementFactory.make("rtph264depay", "h264_depay")
                        parse = Gst.ElementFactory.make("h264parse", "h264_parse")
                        decode = Gst.ElementFactory.make("avdec_h264", "h264_decode")
                    else:
                        print("Unsupported video codec:", name)
                        return

                    if not all([queue, depay, decode, convert, scale, caps_filter, sink]):
                        print("Failed to create all elements")
                        return

                    # Set to raw video format, you can adjust based on your needs
                    caps_filter.set_property("caps", Gst.Caps.from_string("video/x-raw,format=RGB"))
                    
                    self.pipe.add(queue)
                    self.pipe.add(depay)
                    if parse:
                        self.pipe.add(parse)
                    self.pipe.add(decode)
                    self.pipe.add(convert)
                    self.pipe.add(scale)
                    self.pipe.add(caps_filter)
                    self.pipe.add(sink)

                    # Link elements
                    if not queue.link(depay):
                        print("Failed to link queue and depay")
                        return
                    if parse:
                        if not depay.link(parse) or not parse.link(decode):
                            print("Failed to link depay, parse, and decode")
                            return
                    else:
                        if not depay.link(decode):
                            print("Failed to link depay and decode")
                            return
                    if not decode.link(convert):
                        print("Failed to link decode and convert")
                        return
                    if not convert.link(scale):
                        print("Failed to link convert and scale")
                        return
                    if not scale.link(caps_filter):
                        print("Failed to link scale and caps_filter")
                        return
                    if not caps_filter.link(sink):
                        print("Failed to link caps_filter and sink")
                        return

                    # Link the incoming pad to our queue
                    pad.link(queue.get_static_pad("sink"))

                    # Sync states
                    queue.sync_state_with_parent()
                    depay.sync_state_with_parent()
                    if parse:
                        parse.sync_state_with_parent()
                    decode.sync_state_with_parent()
                    convert.sync_state_with_parent()
                    scale.sync_state_with_parent()
                    caps_filter.sync_state_with_parent()
                    sink.sync_state_with_parent()

                    print("FD sink video pipeline set up successfully")
                    
                elif self.framebuffer: ## send raw data to ffmpeg or something I guess, using the stdout?
                    print("APP SINK OUT")
                    if "VP8" in name:
                        out = Gst.parse_bin_from_description("queue ! rtpvp8depay ! queue max-size-buffers=0 max-size-time=0 ! decodebin ! videoconvert ! video/x-raw,format=BGR ! queue max-size-buffers=2 leaky=downstream ! appsink name=appsink", True)
                    elif "H264" in name:
                        out = Gst.parse_bin_from_description("queue ! rtph264depay ! h264parse ! queue max-size-buffers=0 max-size-time=0 ! openh264dec ! videoconvert ! video/x-raw,format=BGR ! queue max-size-buffers=2 leaky=downstream ! appsink name=appsink", True)
                    
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                    
                else:
                    if self.pipe.get_by_name('filesink'):
                        print("VIDEO setup")
                        if "VP8" in name:
                            out = Gst.parse_bin_from_description("queue ! rtpvp8depay", True)
                        elif "H264" in name:
                            out = Gst.parse_bin_from_description("queue ! rtph264depay ! h264parse", True)
                            
                        self.pipe.add(out)
                        out.sync_state_with_parent()
                        sink = out.get_static_pad('sink')
                        out.link(self.pipe.get_by_name('filesink'))
                        pad.link(sink)
                    else:
                        if "VP8" in name:
                            if self.use_hls:
                                # For HLS with VP8, transcode to H264 and use shared HLS sink
                                printc("   🔄 Transcoding VP8 → H264 for HLS recording", "FF0")
                                printc("   📐 Output resolution: 1280x720", "77F")
                                self.setup_hls_recording()
                                out = Gst.parse_bin_from_description(
                                    "queue max-size-buffers=0 max-size-time=0 ! "
                                    "rtpvp8depay ! vp8dec ! videoscale ! "
                                    "video/x-raw,width=1280,height=720 ! "
                                    "x264enc tune=zerolatency ! h264parse ! queue name=video_queue", True)
                                
                                self.pipe.add(out)
                                out.sync_state_with_parent()
                                
                                # Get the source pad from the bin
                                src_pad = out.get_static_pad('src')
                                if not src_pad:
                                    # For bins, we might need to get the ghost pad
                                    video_queue = out.get_by_name('video_queue')
                                    if video_queue:
                                        src_pad = video_queue.get_static_pad('src')
                                
                                if src_pad:
                                    # Request video pad from HLS sink
                                    video_pad = self.hls_sink.request_pad_simple('video')
                                    if video_pad:
                                        if src_pad.link(video_pad) == Gst.PadLinkReturn.OK:
                                            sink = out.get_static_pad('sink')
                                            pad.link(sink)
                                            printc("   ✅ Video connected to HLS muxer", "0F0")
                                        else:
                                            printc("   ❌ Failed to link video to HLS sink", "F00")
                                    else:
                                        printc("   ❌ Failed to get video pad from HLS sink", "F00")
                                else:
                                    printc("   ❌ Failed to get source pad from video pipeline", "F00")
                            else:
                                # VP8 recording to WebM - direct copy without re-encoding
                                printc("   📦 Direct VP8 → WebM (no transcoding)", "0F0")
                                filename = f"./{self.streamin}_{str(int(time.time()))}.webm"
                                out = Gst.parse_bin_from_description(
                                    "queue ! "
                                    "rtpvp8depay ! "
                                    "matroskamux name=mux1 streamable=true ! "
                                    f"filesink name=filesink location={filename}", True)
                                printc(f"   📁 Output: {filename}", "77F")

                        elif "H264" in name:
                            if self.use_hls:
                                # For HLS with H264, use shared HLS sink
                                printc("   ✅ Direct H264 → HLS (no transcoding)", "0F0")
                                self.setup_hls_recording()
                                out = Gst.parse_bin_from_description(
                                    "queue ! rtph264depay ! h264parse ! queue name=video_queue", True)
                                
                                self.pipe.add(out)
                                out.sync_state_with_parent()
                                
                                # Get the source pad from the bin
                                src_pad = out.get_static_pad('src')
                                if not src_pad:
                                    # For bins, we might need to get the ghost pad
                                    video_queue = out.get_by_name('video_queue')
                                    if video_queue:
                                        src_pad = video_queue.get_static_pad('src')
                                
                                if src_pad:
                                    # Request video pad from HLS sink
                                    video_pad = self.hls_sink.request_pad_simple('video')
                                    if video_pad:
                                        if src_pad.link(video_pad) == Gst.PadLinkReturn.OK:
                                            sink = out.get_static_pad('sink')
                                            pad.link(sink)
                                            printc("   ✅ Video connected to HLS muxer", "0F0")
                                        else:
                                            printc("   ❌ Failed to link video to HLS sink", "F00")
                                    else:
                                        printc("   ❌ Failed to get video pad from HLS sink", "F00")
                                else:
                                    printc("   ❌ Failed to get source pad from video pipeline", "F00")
                            else:
                                # For non-HLS mode, save as MP4
                                printc("   ✅ Direct H264 → MP4 (no transcoding)", "0F0")
                                filename = f"./{self.streamin}_{str(int(time.time()))}.mp4"
                                out = Gst.parse_bin_from_description(
                                    "queue ! rtph264depay ! h264parse ! mp4mux name=mux1 ! "
                                    f"filesink name=filesink location={filename}", True)
                                printc(f"   📁 Output: {filename}", "77F")

                        self.pipe.add(out)
                        out.sync_state_with_parent()
                        sink = out.get_static_pad('sink')
                        pad.link(sink)
                    printc("   ✅ Video recording configured", "0F0")
                    
                    # Show recording status after a short delay
                    if not hasattr(self, '_recording_status_shown'):
                        self._recording_status_shown = True
                        def show_recording_status():
                            if self.use_hls and hasattr(self, 'hls_base_filename'):
                                printc(f"\n🔴 RECORDING ACTIVE (HLS)", "F00")
                                printc(f"   📁 Files: {self.hls_base_filename}.m3u8 + segments", "77F")
                            else:
                                printc(f"\n🔴 RECORDING ACTIVE", "F00")
                            return False
                        GLib.timeout_add(1000, show_recording_status)

                if self.framebuffer:
                    frame_shape = (1080, 1920, 3)
                    size = np.prod(frame_shape) + 5  # frame bytes + 5-byte header
                    self.shared_memory = shared_memory.SharedMemory(create=True, size=size, name='psm_raspininja_streamid')
                    self.trigger_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # we don't bind, as the reader will be binding
                    print("*************")
                    print(self.shared_memory)
                    appsink = self.pipe.get_by_name('appsink')
                    appsink.set_property("emit-signals", True)
                    appsink.connect("new-sample", self.new_sample)

            elif "audio" in name:
                if self.noaudio:
                    printc('Ignoring incoming audio track', "F88")
                    
                    out = Gst.parse_bin_from_description("queue ! fakesink", True)
                    
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                    return

                if self.ndiout:
                    # I'm handling this on elsewhere now
                    pass
                elif self.view:
                   # if "OPUS" in name:
                    print("decode and play out the incoming audio")
                    out = Gst.parse_bin_from_description("queue ! rtpopusdepay ! opusparse ! opusdec ! audioconvert ! audioresample ! audio/x-raw,format=S16LE,rate=48000 ! autoaudiosink", True)
                    
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                elif self.fdsink:
                    #if "OPUS" in name:
                    out = Gst.parse_bin_from_description("queue ! rtpopusdepay ! opusparse ! opusdec ! audioconvert ! audioresample ! audio/x-raw,format=S16LE,rate=48000 ! fdsink", True)
                    
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                    
                elif self.framebuffer:
                    out = Gst.parse_bin_from_description("queue ! fakesink", True)
                    
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                    
                else:
                
                    # Check if we have a muxer already (video came first)
                    mux = self.pipe.get_by_name('mux1')
                    if mux:
                        printc("   📼 Checking muxer compatibility...", "FFF")
                        mux_name = mux.get_factory().get_name()
                        
                        if "OPUS" in name:
                            if mux_name == 'webmmux':
                                # WebM can handle Opus directly
                                out = Gst.parse_bin_from_description("queue ! rtpopusdepay ! opusparse", True)
                                self.pipe.add(out)
                                out.sync_state_with_parent()
                                
                                # Get source pad from audio pipeline
                                src_pad = out.get_static_pad('src')
                                # WebM uses audio_%u for audio pads
                                audio_pad = mux.get_request_pad('audio_%u')
                                if audio_pad:
                                    src_pad.link(audio_pad)
                                    sink = out.get_static_pad('sink')
                                    pad.link(sink)
                                    printc("   ✅ Audio muxed with video in WebM file", "0F0")
                                    return  # Important: return after successful muxing
                                else:
                                    print("Failed to get audio pad from WebM muxer")
                                    self.pipe.remove(out)
                                    mux = None  # Fall through to separate file
                            elif mux_name == 'mpegtsmux':
                                # MPEG-TS needs AAC audio, not Opus
                                # For now, create separate audio file for H264/HLS
                                printc("      └─ H264/HLS detected - audio will record separately", "FF0")
                                mux = None  # Fall through to separate file
                            else:
                                print(f"Unknown muxer type: {mux_name} - creating separate audio file")
                                mux = None  # Fall through to separate file
                    
                    if not mux:  # No muxer or incompatible muxer
                        if "OPUS" in name:
                            if self.use_hls:
                                # For HLS mode, transcode to AAC and connect to shared HLS sink
                                printc("   🔄 Transcoding OPUS → AAC for HLS", "FF0")
                                self.setup_hls_recording()
                                out = Gst.parse_bin_from_description(
                                    "queue ! rtpopusdepay ! opusdec ! audioconvert ! audioresample ! "
                                    "avenc_aac ! aacparse ! queue name=audio_queue", True)
                                
                                self.pipe.add(out)
                                out.sync_state_with_parent()
                                
                                # Get the source pad from the bin
                                src_pad = out.get_static_pad('src')
                                if not src_pad:
                                    # For bins, we might need to get the ghost pad
                                    audio_queue = out.get_by_name('audio_queue')
                                    if audio_queue:
                                        src_pad = audio_queue.get_static_pad('src')
                                
                                if src_pad:
                                    # Request audio pad from HLS sink
                                    audio_pad = self.hls_sink.request_pad_simple('audio')
                                    if audio_pad:
                                        if src_pad.link(audio_pad) == Gst.PadLinkReturn.OK:
                                            sink = out.get_static_pad('sink')
                                            pad.link(sink)
                                            printc("   ✅ Audio connected to HLS muxer", "0F0")
                                            return  # Important: return to avoid falling through
                                        else:
                                            printc("   ❌ Failed to link audio to HLS sink", "F00")
                                    else:
                                        printc("   ❌ Failed to get audio pad from HLS sink", "F00")
                                else:
                                    printc("   ❌ Failed to get source pad from audio pipeline", "F00")
                            else:
                                # For non-HLS mode, save OPUS in WebM container without transcoding
                                printc("   📦 Direct OPUS → WebM (no transcoding)", "0F0")
                                filename = f"{self.streamin}_{str(int(time.time()))}_audio.webm"
                                out = Gst.parse_bin_from_description(
                                    "queue ! rtpopusdepay ! opusparse ! "
                                    "webmmux ! "
                                    f"filesink name=filesinkaudio location={filename}", True)
                                printc(f"   📁 Output: {filename}", "77F")

                        self.pipe.add(out)
                        out.sync_state_with_parent()
                        sink = out.get_static_pad('sink')
                        pad.link(sink)
                        
                printc("   ✅ Audio recording configured", "0F0")

        except Exception as E:
            printc("\n❌ Error during stream setup:", "F00")
            printwarn(get_exception_info(E))

            traceback.print_exc()


            
    async def createPeer(self, UUID):

        if UUID in self.clients:
            client = self.clients[UUID]
        else:
            print("peer not yet created; error")
            return
        client['direction'] = "receive" if self.view else "send"
        if self.view:
            self._cancel_viewer_restart_timer()
            self._viewer_restart_pending = False
            self._viewer_restart_attempts = 0
            self._viewer_last_play_request = 0.0
            self._viewer_last_disconnect = 0.0

        configured_transceivers: Set[int] = set()

        def configure_transceiver(trans, index: Optional[int] = None):
            if not trans:
                return
            trans_id = id(trans)
            if trans_id in configured_transceivers:
                return
            configured_transceivers.add(trans_id)
            label = f"transceiver[{index}]" if index is not None else "transceiver"

            force_fec = self.force_red or client.get("_auto_redundancy_active")
            force_rtx = self.force_rtx
            self._apply_loss_controls(
                client,
                trans,
                label=label,
                force_fec=force_fec,
                force_rtx=force_rtx,
                announce=True,
            )

            def _hook_receiver(transceiver):
                receiver_obj = getattr(transceiver.props, 'receiver', None)
                if receiver_obj is None:
                    return False

                def _receiver_pad_added(recv, pad):
                    caps = pad.get_current_caps()
                    caps_str = caps.to_string() if caps else 'None'
                    print(f"[webrtc] Receiver pad added ({label}): {pad.get_name()} caps={caps_str}")
                    self.on_incoming_stream(client['webrtc'], pad)

                try:
                    receiver_obj.connect('pad-added', _receiver_pad_added)
                    return True
                except Exception as exc:
                    printwarn(f"Failed to attach pad handler for {label}: {exc}")
                    return False

            if not _hook_receiver(trans):
                handler_id = None

                def _on_receiver_notify(transceiver, _pspec):
                    nonlocal handler_id
                    if _hook_receiver(transceiver) and handler_id is not None:
                        try:
                            transceiver.disconnect(handler_id)
                        except Exception:
                            pass

                try:
                    handler_id = trans.connect('notify::receiver', _on_receiver_notify)
                except Exception as exc:
                    printwarn(f"Failed to monitor receiver changes for {label}: {exc}")

        def configure_existing_transceivers():
            index = 0
            while True:
                try:
                    trans = client['webrtc'].emit("get-transceiver", index)
                except Exception as exc:
                    printwarn(f"Failed to access transceiver[{index}]: {exc}")
                    break
                if not trans:
                    break
                configure_transceiver(trans, index=index)
                index += 1

        def on_offer_created(promise, _, __):
            # Offer created, sending to peer
            promise.wait()
            reply = promise.get_reply()
            offer = reply.get_value('offer')
            printc("📤 Sending connection offer...", "77F")
            original_text = offer.sdp.as_text()
            text = original_text
            if ("96 96 96 96 96" in text):
                printc("Patching SDP due to Gstreamer webRTC bug - none-unique line values","A6F")
                text = text.replace(" 96 96 96 96 96", " 96 96 97 98 96")
                text = text.replace("a=rtpmap:96 red/90000\r\n","a=rtpmap:97 red/90000\r\n")
                text = text.replace("a=rtpmap:96 ulpfec/90000\r\n","a=rtpmap:98 ulpfec/90000\r\n")
                text = text.replace("a=rtpmap:96 rtx/90000\r\na=fmtp:96 apt=96\r\n","")
            elif self.nored and (" 96 96" in text): ## fix for older gstreamer is using --nored
                printc("Patching SDP due to Gstreamer webRTC bug - issue with nored","A6F")
                text = text.replace(" 96 96", " 96 97")
                text = text.replace("a=rtpmap:96 ulpfec/90000\r\n","a=rtpmap:97 ulpfec/90000\r\n")
                text = text.replace("a=rtpmap:96 rtx/90000\r\na=fmtp:96 apt=96\r\n","")

            gst_ver = Gst.version()
            if self.novideo and not self.noaudio and gst_ver.major == 1 and gst_ver.minor < 20: # impacts audio and video as well, but chrome / firefox seems to handle it
                printc("Patching SDP due to Gstreamer webRTC bug - audio-only issue", "A6F") # just chrome doesn't handle this
                text = replace_ssrc_and_cleanup_sdp(text)

            # Fix audio SDP issues for GStreamer < 1.20 (1.18 has known SDP bugs Chrome rejects)
            if not self.noaudio and gst_ver.major == 1 and gst_ver.minor < 20:
                if 'm=audio' in text:
                    printc("Patching audio SDP for GStreamer 1.18 compatibility", "A6F")
                    text = fix_audio_ssrc_for_ohttp_gstreamer(text)
                    text = fix_audio_rtcp_fb_for_gstreamer(text)
                    text = strip_audio_rtx_from_sdp(text)
            elif self.noaudio and gst_ver.major == 1 and gst_ver.minor < 20:
                if 'm=audio' in text:
                    printc("Stripping phantom audio section from SDP (GStreamer 1.18 bug)", "A6F")
                    text = strip_audio_from_sdp(text)

            text = self._ensure_primary_video_codec_in_sdp(text)

            dump_offer_path = os.environ.get("RN_DUMP_OFFER_SDP")
            if dump_offer_path:
                try:
                    Path(dump_offer_path).write_text(text)
                    printc(f"[debug] Wrote modified offer SDP to {dump_offer_path}", "0AF")
                except Exception as exc:
                    printwarn(f"Failed to write offer SDP to {dump_offer_path}: {exc}")

            if self.view:
                text = self._apply_bitrate_constraints_to_sdp(text, context="outgoing offer")

            offer_to_set = offer
            if text != original_text:
                try:
                    res, sdpmsg = GstSdp.SDPMessage.new()
                    GstSdp.sdp_message_parse_buffer(bytes(text.encode()), sdpmsg)
                    offer_to_set = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.OFFER, sdpmsg)
                except Exception as exc:
                    printwarn(f"Failed to rebuild modified offer SDP: {exc}")
                    text = original_text
                    offer_to_set = offer

            promise = Gst.Promise.new()
            client['webrtc'].emit('set-local-description', offer_to_set, promise)
            promise.interrupt()

            msg = {'description': {'type': 'offer', 'sdp': text}, 'UUID': client['UUID'], 'session': client['session'], 'streamID':self.stream_id+self.hashcode}
            self.sendMessage(msg)

        def on_new_tranceiver(element, trans):
            # New transceiver added
            configure_transceiver(trans)

        def on_negotiation_needed(element):
            # Negotiation needed, creating offer
            promise = Gst.Promise.new_with_change_func(on_offer_created, element, None)
            element.emit('create-offer', None, promise)

        def send_ice_local_candidate_message(_, mlineindex, candidate):
            if " TCP " in candidate: ##  I Can revisit another time, but for now, this isn't needed: TODO: optimize
                return
            icemsg = {'candidates': [{'candidate': candidate, 'sdpMLineIndex': mlineindex}], 'session':client['session'], 'type':'local', 'UUID':client['UUID']}
            self.sendMessage(icemsg)

        def send_ice_remote_candidate_message(_, mlineindex, candidate):
            icemsg = {'candidates': [{'candidate': candidate, 'sdpMLineIndex': mlineindex}], 'session':client['session'], 'type':'remote', 'UUID':client['UUID']}
            self.sendMessage(icemsg)

        def on_signaling_state(p1, p2):
            # Signaling state changed
            pass

        def on_ice_connection_state(p1, p2):
            state = client['webrtc'].get_property(p2.name)
            if state == 1:
                printc("🔍 ICE: Checking connectivity...", "77F")
            elif state == 2:
                printc("✅ ICE: Connected", "0F0")
            elif state == 3:
                printc("🎯 ICE: Connection established", "0F0")
            elif state > 3:
                printc("❌ ICE: Connection failed", "F44")

        def on_connection_state(p1, p2):
            state = client['webrtc'].get_property(p2.name)
            
            if state == 2: # connected
                printc("\n🎬 Peer connection established!", "0F0")
                printc("   └─ Viewer connected successfully\n", "0F0")
                self._loss_hint_shown = False
                if self.view:
                    try:
                        self._set_display_mode("connecting")
                    except Exception as exc:
                        printwarn(f"Failed to update display state: {exc}")
                promise = Gst.Promise.new_with_change_func(on_stats, client['webrtc'], None) # check stats
                client['webrtc'].emit('get-stats', None, promise)

                if not self.streamin and not client['send_channel']:
                    channel = client['webrtc'].emit('create-data-channel', 'sendChannel', None)
                    on_data_channel(client['webrtc'], channel)

                if client['timer'] == None:
                    client['ping'] = 0
                    client['timer'] = threading.Timer(3, pingTimer)
                    client['timer'].start()
                    self.clients[client["UUID"]] = client

            elif state >= 4: # closed/failed
                printc("\n🚫 Peer disconnected", "F77")
                if self.view:
                    try:
                        self._set_display_mode("idle")
                    except Exception as exc:
                        printwarn(f"Failed to update display state: {exc}")
                self.stop_pipeline(client['UUID'])
            elif state == 1:
                printc("🔄 Connecting to peer...", "77F")
                if self.view:
                    try:
                        self._set_display_mode("connecting")
                    except Exception as exc:
                        printwarn(f"Failed to update display state: {exc}")
        def print_trans(p1,p2):
            print("trans:  {}".format(client['webrtc'].get_property(p2.name)))

        def pingTimer():
            # Check if client still exists before proceeding
            if client["UUID"] not in self.clients:
                print(f"Client {client['UUID']} no longer exists, stopping pingTimer")
                return

            if not client['send_channel']:
                client['timer'] = threading.Timer(3, pingTimer)
                client['timer'].start()
                print("data channel not setup yet")
                return

            if "ping" not in client:
                client['ping'] = 0

            if client['ping'] < 10:
                client['ping'] += 1
                # Only update if client still exists
                if client["UUID"] in self.clients:
                    self.clients[client["UUID"]] = client
                try:
                    client['send_channel'].emit('send-string', '{"ping":"'+str(time.time())+'"}')
                    if client.get('_last_ping_logged', 0) < time.time() - 30:
                        printc("💓 Connection healthy (ping/pong active)", "666")
                        client['_last_ping_logged'] = time.time()
                except Exception as e:
                    printwarn(get_exception_info(e))

                    print("PING FAILED")
                client['timer'] = threading.Timer(3, pingTimer)
                client['timer'].start()

                promise = Gst.Promise.new_with_change_func(on_stats, client['webrtc'], None) # check stats
                client['webrtc'].emit('get-stats', None, promise)

            else:
                printc("NO HEARTBEAT", "F44")
                if self.view:
                    print("Viewer heartbeat timeout; restarting peer connection")
                    client['ping'] = 0
                    self.stop_pipeline(client['UUID'])
                    return
                else:
                    self.stop_pipeline(client['UUID'])

        def on_data_channel(webrtc, channel):
            printc("   📡 Data channel event", "FFF")
            if channel is None:
                printc('      └─ No data channel available', "F44")
                return
            else:
                pass
            channel.connect('on-open', on_data_channel_open)
            channel.connect('on-error', on_data_channel_error)
            channel.connect('on-close', on_data_channel_close)
            channel.connect('on-message-string', on_data_channel_message)

        def on_data_channel_error(arg1, arg2):
            printc('❌ Data channel error', "F44")

        def on_data_channel_open(channel):
            # Don't print, already shown in connection message
            client['send_channel'] = channel
            self.clients[client["UUID"]] = client
            if self.streamin:
                if self.noaudio:
                    msg = {"audio":False, "video":True, "UUID": client["UUID"]} ## You must edit the SDP instead if you want to force a particular codec
                elif self.novideo:
                    msg = {"audio":True, "video":False, "UUID": client["UUID"]} ## You must edit the SDP instead if you want to force a particular codec
                else:
                    msg = {"audio":True, "video":True, "UUID": client["UUID"]} ## You must edit the SDP instead if you want to force a particular codec
                
                self.sendMessage(msg)
            elif self.midi:
                msg = {"audio":False, "video":False, "allowmidi":True, "UUID": client["UUID"]} ## You must edit the SDP instead if you want to force a particular codec
                self.sendMessage(msg)
            elif self.rotate:
                msg = {"info":{"rotate_video":self.rotate}, "UUID": client["UUID"]}
                self.sendMessage(msg)
            elif self.view:
                try:
                    bitrate_hint = int(self.max_bitrate)
                except Exception:
                    bitrate_hint = 0
                if bitrate_hint > 0:
                    try:
                        bitrate_payload = {
                            "bitrate": bitrate_hint,
                            "bandwidth": bitrate_hint,
                            "maxbandwidth": bitrate_hint,
                            "maxBandwidth": bitrate_hint,
                            "maxBitrate": bitrate_hint,
                        }
                        remote_uuid = client.get("UUID")
                        if remote_uuid:
                            bitrate_payload["UUID"] = remote_uuid
                        channel.emit('send-string', json.dumps(bitrate_payload))
                        printc(f"   📶 Requested {bitrate_hint} kbps from source", "07F")
                    except Exception as exc:
                        printwarn(f"Failed to send bitrate request: {exc}")

        def on_data_channel_close(channel):
            printc('🔌 Data channel closed', "F77")

        def on_data_channel_message(channel, msg_raw): 
            try:
                msg = json.loads(msg_raw)
            except:
                # Invalid JSON in data channel message
                return
            if 'candidates' in msg:
                # Processing ICE candidates bundle
                
                if 'vector' in msg:
                    try:
                        decryptedJson = decrypt_message(msg['candidates'], msg['vector'], self.password+self.salt)
                        msg['candidates'] = json.loads(decryptedJson)
                    except Exception as E:
                        printwarn(get_exception_info(E))

                
                for ice in msg['candidates']:
                    self.handle_sdp_ice(ice, client["UUID"])
            elif 'candidate' in msg:
                # Processing single ICE candidate
                
                if 'vector' in msg:
                    try:
                        decryptedJson = decrypt_message(msg['candidate'], msg['vector'], self.password+self.salt)
                        msg['candidate'] = json.loads(decryptedJson)
                    except Exception as E:
                        printwarn(get_exception_info(E))

                
                self.handle_sdp_ice(msg, client["UUID"])
            elif 'pong' in msg: # Supported in v19 of VDO.Ninja
                # Don't print individual pongs, handled by periodic health message
                client['ping'] = 0
                self.clients[client["UUID"]] = client
            elif 'bye' in msg: ## v19 of VDO.Ninja
                printc("👋 Peer disconnected gracefully", "77F")
                if self.view:
                    self._set_display_mode("idle")
                    uuid = client.get("UUID")
                    if uuid and uuid in self.clients:
                        self.stop_pipeline(uuid)
            elif self.view and ('video' in msg or 'videoMuted' in msg):
                debug_display = bool(os.environ.get("RN_DEBUG_DISPLAY"))
                if 'video' in msg:
                    video_enabled = self._coerce_message_flag(msg['video'])
                    if debug_display:
                        print(
                            f"[display] Data channel `video` flag: raw={msg['video']!r} -> enabled={video_enabled}"
                        )
                    if video_enabled is False:
                        if self.display_remote_map:
                            self._viewer_pending_idle = False
                            self._set_display_mode("idle")
                        else:
                            self._viewer_pending_idle = True
                            if debug_display:
                                print("[display] Idle requested before remote video attached; deferring")
                    elif video_enabled is True:
                        self._viewer_pending_idle = False
                        self._resume_remote_display()
                else:
                    video_muted = self._coerce_message_flag(msg['videoMuted'])
                    if debug_display:
                        print(
                            f"[display] Data channel `videoMuted` flag: raw={msg['videoMuted']!r} -> muted={video_muted}"
                        )
                    if video_muted:
                        if self.display_remote_map:
                            self._viewer_pending_idle = False
                            self._set_display_mode("idle")
                        else:
                            self._viewer_pending_idle = True
                            if debug_display:
                                print("[display] Video muted before remote video attached; deferring")
                    elif video_muted is False:
                        self._viewer_pending_idle = False
                        self._resume_remote_display()
            elif 'description' in msg:
                printc("📥 Receiving connection details...", "77F")
                
                if 'vector' in msg:
                    try:
                        decryptedJson = decrypt_message(msg['description'], msg['vector'], self.password+self.salt)
                        msg['description'] = json.loads(decryptedJson)
                    except Exception as E:
                        printwarn(get_exception_info(E))

                
                if msg['description']['type'] == "offer":
                    self.handle_offer(msg['description'], client['UUID'])
            elif 'midi' in msg:
                printin("midi msg")
                vdo2midi(msg['midi'])
            elif 'bitrate' in msg:
                printin("bitrate msg")
                if msg['bitrate']:
                    print("Trying to change bitrate...")
                    # VDO.Ninja sends bitrate in kbps
                    self.set_encoder_bitrate(client, int(msg['bitrate']))
            else:
                # Silently handle misc data channel messages
                return

        def vdo2midi(midi):
            try:
                if self.midiout == None:
                    self.midiout = rtmidi.MidiOut()

                new_out_port = self.midiout.get_ports() # a bit inefficient, but safe
                if new_out_port != self.midiout_ports:
                    print("New MIDI Out device(s) initializing...")
                    self.midiout_ports = new_out_port
                    try:
                        self.midiout.close_port()
                    except:
                        pass

                    for i in range(len(self.midiout_ports)):
                        if "Midi Through" in self.midiout_ports[i]:
                            continue
                        break
                    if i < len(self.midiout_ports):
                        self.midiout.open_port(i)
                        print(i) ## midi output device
                    else:
                        return ## no MIDI out found; skipping

                self.midiout.send_message(midi['d'])
            except Exception as E:
                printwarn(get_exception_info(E))

        def sendMIDI(data, template):
            if data:
                 template['midi']['d'] = data[0]
                 data = json.dumps(template)
                 for client in self.clients:
                      if self.clients[client]['send_channel']:
                           try:
                               self.clients[client]['send_channel'].emit('send-string', data)
                           except:
                               pass

        def midi2vdo(midi):
            in_ports = None
            self.midiin = rtmidi.MidiIn()
            while True:
                in_ports_new = self.midiin.get_ports()
                if in_ports_new != in_ports:
                    in_ports = in_ports_new
                    if self.midiin:
                        print("New MIDI Input device(s) initializing...")
                        try:
                            self.midiin.close_port()
                        except:
                            pass
                    while True:
                        print(in_ports)
                        for i in range(len(in_ports)):
                            if "Midi Through" in in_ports[i]:
                                continue
                            break
                        if i < len(in_ports):
                            self.midiin.open_port(i)
                            print(i) ## midi input device
                            break
                        else:
                            time.sleep(0.5)
                            in_ports = self.midiin.get_ports()

                    template = {}
                    template['midi'] = {}
                    template['midi']['d'] = []
                    if self.puuid:
                        template['from'] = self.puuid
                    self.midiin.cancel_callback()
                    self.midiin.set_callback(sendMIDI, template)
                else:
                    time.sleep(4)

        def on_stats(promise, abin, data):
            promise.wait()
            stats_reply = promise.get_reply()
            stats_text = stats_reply.to_string()
            stats_text = stats_text.replace("\\", "")

            is_receive = client.get("direction") == "receive"
            current_time = time.time()

            if "_last_full_stats_log" not in client:
                client["_last_full_stats_log"] = 0

            def extract_counter(text: str, token: str) -> Optional[int]:
                if not text:
                    return None
                if token in text:
                    try:
                        segment = text.split(token, 1)[1]
                        return int(segment.split(",")[0].split(";")[0].strip())
                    except Exception:
                        pass
                base_key = token.split("=", 1)[0] if "=" in token else token
                if base_key:
                    pattern = rf"{re.escape(base_key)}\s*=\s*\([^)]*\)\s*(\d+)"
                    match = re.search(pattern, text)
                    if match:
                        try:
                            return int(match.group(1))
                        except Exception:
                            pass
                    fallback_pattern = rf"{re.escape(base_key)}\s*=\s*(\d+)"
                    match = re.search(fallback_pattern, text)
                    if match:
                        try:
                            return int(match.group(1))
                        except Exception:
                            pass
                return None

            def extract_section(text: str, patterns) -> str:
                for pattern in patterns:
                    if pattern in text:
                        try:
                            return text.split(pattern, 1)[1].split("rtp-", 1)[0]
                        except Exception:
                            return ""
                return ""

            def extract_counter_from_section(section: str, tokens) -> Optional[int]:
                if not section:
                    return None
                for token in tokens:
                    value = extract_counter(section, token)
                    if value is not None:
                        return value
                return None

            def extract_int_from_section(section: str, pattern: str) -> Optional[int]:
                if not section:
                    return None
                match = re.search(pattern, section)
                if match:
                    try:
                        return int(match.group(1))
                    except Exception:
                        return None
                return None

            def extract_float_value(text: str, token: str) -> Optional[float]:
                if not text:
                    return None
                patterns = []
                if "=" in token:
                    patterns.append(rf"{re.escape(token)}\s*([0-9]+(?:\.[0-9]+)?)")
                    base_key = token.split("=", 1)[0]
                else:
                    base_key = token
                if base_key:
                    patterns.extend(
                        [
                            rf"{re.escape(base_key)}\s*=\s*\([^)]*\)\s*([0-9]+(?:\.[0-9]+)?)",
                            rf"{re.escape(base_key)}\s*=\s*([0-9]+(?:\.[0-9]+)?)",
                        ]
                    )
                for pattern in patterns:
                    match = re.search(pattern, text)
                    if match:
                        try:
                            return float(match.group(1))
                        except Exception:
                            continue
                return None

            video_patterns = [
                "kind=(string)video",
                "kind = (string) video",
                "kind=(string) video",
                "kind =(string)video",
                "media-type=\"video\"",
                "media-type='video'",
            ]
            audio_patterns = [
                "kind=(string)audio",
                "kind = (string) audio",
                "kind=(string) audio",
                "kind =(string)audio",
                "media-type=\"audio\"",
                "media-type='audio'",
            ]
            counter_tokens = ["bytes-received=(guint64)", "bytes-sent=(guint64)"]

            video_section = extract_section(stats_text, video_patterns)
            audio_section = extract_section(stats_text, audio_patterns)
            video_bytes_total = extract_counter_from_section(video_section, counter_tokens)
            audio_bytes_total = extract_counter_from_section(audio_section, counter_tokens)

            frame_width = extract_int_from_section(video_section, r"frame-width=\(gint\)\s*(\d+)")
            if frame_width is None:
                frame_width = extract_int_from_section(video_section, r"frame_width=\(gint\)\s*(\d+)")
            if frame_width is None:
                match = re.search(r"frame[-_]width=\([^)]*\)\s*(\d+)", stats_text)
                if match:
                    try:
                        frame_width = int(match.group(1))
                    except Exception:
                        frame_width = None

            frame_height = extract_int_from_section(video_section, r"frame-height=\(gint\)\s*(\d+)")
            if frame_height is None:
                frame_height = extract_int_from_section(video_section, r"frame_height=\(gint\)\s*(\d+)")
            if frame_height is None:
                match = re.search(r"frame[-_]height=\([^)]*\)\s*(\d+)", stats_text)
                if match:
                    try:
                        frame_height = int(match.group(1))
                    except Exception:
                        frame_height = None

            bytes_token = "bytes-received=(guint64)" if is_receive else "bytes-sent=(guint64)"
            packets_token = "packets-received=(guint64)" if is_receive else "packets-sent=(guint64)"
            bytes_total = extract_counter(stats_text, bytes_token)
            if bytes_total is None:
                alt_bytes = "bytes-sent=(guint64)" if bytes_token.startswith("bytes-received") else "bytes-received=(guint64)"
                bytes_total = extract_counter(stats_text, alt_bytes)
            if bytes_total is None:
                bytes_total = 0

            packets_total = extract_counter(stats_text, packets_token)
            if packets_total is None:
                alt_packets = "packets-sent=(guint64)" if packets_token.startswith("packets-received") else "packets-received=(guint64)"
                packets_total = extract_counter(stats_text, alt_packets)
            if packets_total is None:
                packets_total = 0

            bytes_field = "_last_bytes_recv" if is_receive else "_last_bytes_sent"
            time_field = "_last_bytes_recv_time" if is_receive else "_last_bytes_time"
            packets_field = "_last_packets_recv" if is_receive else "_last_packets_sent"

            prev_bytes = client.get(bytes_field, 0)
            prev_time = client.get(time_field, current_time)
            if bytes_field not in client:
                client[bytes_field] = bytes_total
                client[time_field] = current_time
                prev_bytes = bytes_total
                prev_time = current_time

            time_diff = current_time - prev_time if prev_time else 0.0
            bitrate_calc = 0
            if bytes_total > prev_bytes and time_diff > 0:
                bitrate_calc = int(((bytes_total - prev_bytes) * 8) / (time_diff * 1000))

            packet_rate = 0.0
            prev_packets = client.get(packets_field, 0)
            if packets_field not in client:
                client[packets_field] = packets_total
                prev_packets = packets_total
            if packets_total > prev_packets and time_diff > 0:
                packet_rate = (packets_total - prev_packets) / time_diff

            if bytes_total < prev_bytes:
                client[bytes_field] = bytes_total
                client[time_field] = current_time
                prev_bytes = bytes_total
            else:
                client[bytes_field] = bytes_total
                client[time_field] = current_time

            if packets_total < prev_packets:
                client[packets_field] = packets_total
                prev_packets = packets_total
            else:
                client[packets_field] = packets_total

            bitrate_cache_key = "_last_bitrate_recv" if is_receive else "_last_bitrate_sent"
            bitrate_time_key = f"{bitrate_cache_key}_time"
            if bitrate_calc > 0:
                client[bitrate_cache_key] = bitrate_calc
                client[bitrate_time_key] = current_time
            else:
                cached_bitrate = client.get(bitrate_cache_key)
                cached_time = client.get(bitrate_time_key, 0)
                if cached_bitrate and (current_time - cached_time) <= 6:
                    bitrate_calc = cached_bitrate

            client["_last_video_bytes"] = video_bytes_total
            client["_last_audio_bytes"] = audio_bytes_total

            if is_receive:
                if packet_rate > 0:
                    client["_last_packet_rate"] = packet_rate
                    client["_last_packet_rate_time"] = current_time
                else:
                    cached_rate = client.get("_last_packet_rate")
                    cached_rate_time = client.get("_last_packet_rate_time", 0)
                    if cached_rate and (current_time - cached_rate_time) <= 6:
                        packet_rate = cached_rate

                if isinstance(frame_width, int) and frame_width > 0:
                    client["_last_video_width"] = frame_width
                else:
                    frame_width = client.get("_last_video_width")

                if isinstance(frame_height, int) and frame_height > 0:
                    client["_last_video_height"] = frame_height
                else:
                    frame_height = client.get("_last_video_height")
            else:
                if isinstance(frame_width, int) and frame_width > 0:
                    client["_last_video_width"] = frame_width
                else:
                    frame_width = client.get("_last_video_width")
                if isinstance(frame_height, int) and frame_height > 0:
                    client["_last_video_height"] = frame_height
                else:
                    frame_height = client.get("_last_video_height")

            if current_time - client["_last_full_stats_log"] > 30:
                if (
                    not is_receive
                    and video_bytes_total is not None
                    and audio_bytes_total is not None
                    and video_bytes_total == 0
                    and audio_bytes_total > 0
                    and bitrate_calc > 0
                ):
                    printc("⚠️ WARNING: Video stream not sending data (audio-only stream detected)", "F70")
                client["_last_full_stats_log"] = current_time

            loss_value = None
            lost_packets_total = None
            recv_packets_total = None
            rtcp_loss_fraction = None
            counter_loss_fraction = None
            recovery_counter = None
            raw_fraction: Optional[float] = None
            residual_fraction: Optional[float] = None

            fraction_tokens = [
                "fraction-lost=(double)",
                "fraction_lost=(double)",
                "fractionLost=(double)",
                "fraction-lost",
            ]
            for token in fraction_tokens:
                rtcp_loss_fraction = extract_float_value(video_section, token)
                if rtcp_loss_fraction is not None:
                    break
            if rtcp_loss_fraction is None:
                for token in fraction_tokens:
                    rtcp_loss_fraction = extract_float_value(stats_text, token)
                    if rtcp_loss_fraction is not None:
                        break

            loss_tokens = [
                "packets-lost=(guint64)",
                "packets_lost=(guint64)",
                "packetsLost=(guint64)",
                "packets-lost",
            ]
            recv_tokens = [
                "packets-received=(guint64)",
                "packets_received=(guint64)",
                "packetsReceived=(guint64)",
                "packets-received",
            ]

            lost_packets_total = extract_counter_from_section(video_section, loss_tokens)
            recv_packets_total = extract_counter_from_section(video_section, recv_tokens)
            if lost_packets_total is None:
                lost_packets_total = extract_counter(stats_text, "packets-lost=(guint64)")
                if lost_packets_total is None:
                    lost_packets_total = extract_counter(stats_text, "packets-lost")
            if recv_packets_total is None:
                recv_packets_total = extract_counter(stats_text, "packets-received=(guint64)")
                if recv_packets_total is None:
                    recv_packets_total = extract_counter(stats_text, "packets-received")

            if (
                isinstance(lost_packets_total, int)
                and isinstance(recv_packets_total, int)
                and lost_packets_total >= 0
                and recv_packets_total >= 0
            ):
                total_packets = lost_packets_total + recv_packets_total
                if total_packets > 0:
                    counter_loss_fraction = lost_packets_total / total_packets

            if rtcp_loss_fraction is not None:
                loss_value = rtcp_loss_fraction
                client["_last_raw_loss"] = rtcp_loss_fraction
            if counter_loss_fraction is not None:
                if loss_value is None:
                    loss_value = counter_loss_fraction
                client["_last_counter_loss"] = counter_loss_fraction

            def _extract_int(pattern: str) -> Optional[int]:
                match = re.search(pattern, stats_text)
                if match:
                    try:
                        return int(match.group(1))
                    except Exception:
                        return None
                return None

            repaired_total = _extract_int(r"packets-repaired\s*=\s*\([^)]*\)\s*(\d+)")
            fec_total = _extract_int(r"fec-packets-recovered\s*=\s*\([^)]*\)\s*(\d+)")
            if fec_total is None:
                fec_total = _extract_int(r"fec-recovered-packets\s*=\s*\([^)]*\)\s*(\d+)")
            rtx_total = _extract_int(r"retransmitted-packets-received\s*=\s*\([^)]*\)\s*(\d+)")

            fec_delta = None
            if isinstance(fec_total, int):
                client["_fec_seen"] = True
                prev_fec_total = client.get("_prev_fec_total")
                if isinstance(prev_fec_total, int) and fec_total >= prev_fec_total:
                    fec_delta = fec_total - prev_fec_total
                elif prev_fec_total is None:
                    fec_delta = fec_total
                client["_prev_fec_total"] = fec_total
            rtx_delta = None
            if isinstance(rtx_total, int):
                client["_rtx_seen"] = True
                prev_rtx_total = client.get("_prev_rtx_total")
                if isinstance(prev_rtx_total, int) and rtx_total >= prev_rtx_total:
                    rtx_delta = rtx_total - prev_rtx_total
                elif prev_rtx_total is None:
                    rtx_delta = rtx_total
                client["_prev_rtx_total"] = rtx_total
            if isinstance(fec_delta, int) and fec_delta > 0:
                client["_fec_active"] = True
            elif "_fec_active" not in client:
                client["_fec_active"] = None
            if isinstance(rtx_delta, int) and rtx_delta > 0:
                client["_rtx_active"] = True
            elif "_rtx_active" not in client:
                client["_rtx_active"] = None

            if repaired_total is not None:
                recovery_counter = repaired_total
            else:
                recovered_components = [value for value in (fec_total, rtx_total) if isinstance(value, int)]
                if recovered_components:
                    recovery_counter = sum(recovered_components)

            if lost_packets_total is not None and recv_packets_total is not None:
                prev_lost = client.get("_prev_loss_counter_lost")
                prev_recv = client.get("_prev_loss_counter_recv")
                interval_lost = client.get("_interval_loss_lost", 0)
                interval_total = client.get("_interval_loss_total", 0)

                if (
                    isinstance(prev_lost, int)
                    and isinstance(prev_recv, int)
                    and lost_packets_total >= prev_lost
                    and recv_packets_total >= prev_recv
                ):
                    delta_lost = lost_packets_total - prev_lost
                    delta_recv = recv_packets_total - prev_recv
                    if delta_lost >= 0 and delta_recv >= 0:
                        interval_lost += delta_lost
                        interval_total += delta_lost + delta_recv
                else:
                    interval_lost = 0
                    interval_total = 0

                client["_prev_loss_counter_lost"] = lost_packets_total
                client["_prev_loss_counter_recv"] = recv_packets_total
                client["_interval_loss_lost"] = interval_lost
                client["_interval_loss_total"] = interval_total
            else:
                client.setdefault("_interval_loss_lost", 0)
                client.setdefault("_interval_loss_total", 0)

            if recovery_counter is not None:
                prev_recovered = client.get("_prev_loss_counter_recovered")
                interval_recovered = client.get("_interval_loss_recovered", 0)
                if (
                    isinstance(prev_recovered, int)
                    and recovery_counter >= prev_recovered
                ):
                    delta_recovered = recovery_counter - prev_recovered
                    if delta_recovered >= 0:
                        interval_recovered += delta_recovered
                else:
                    interval_recovered = 0
                client["_prev_loss_counter_recovered"] = recovery_counter
                client["_interval_loss_recovered"] = interval_recovered
            elif "_interval_loss_recovered" not in client:
                client["_interval_loss_recovered"] = 0

            if "_last_bitrate_log" not in client:
                client["_last_bitrate_log"] = 0

            raw_fraction = rtcp_loss_fraction
            if raw_fraction is None:
                raw_fraction = client.get("_last_raw_loss")
            if raw_fraction is not None:
                client["_last_raw_loss"] = raw_fraction

            residual_fraction = counter_loss_fraction
            if residual_fraction is None:
                residual_fraction = client.get("_last_counter_loss")
            if residual_fraction is not None:
                client["_last_counter_loss"] = residual_fraction

            if "_last_interval_loss" not in client:
                client["_last_interval_loss"] = None

            interval_fraction_for_use = client.get("_last_interval_loss")

            log_interval = 5 if is_receive else 10
            if current_time - client["_last_bitrate_log"] > log_interval:
                interval_loss_value = None
                interval_lost = client.get("_interval_loss_lost", 0)
                interval_total = client.get("_interval_loss_total", 0)
                interval_recovered = client.get("_interval_loss_recovered", 0)
                if interval_total > 0:
                    interval_loss_value = interval_lost / interval_total
                elif (
                    interval_total == 0
                    and interval_lost == 0
                    and client.get("_prev_loss_counter_lost") is not None
                    and client.get("_prev_loss_counter_recv") is not None
                ):
                    interval_loss_value = 0.0
                if interval_loss_value is not None:
                    residual_fraction = interval_loss_value
                    client["_last_counter_loss"] = residual_fraction
                elif counter_loss_fraction is not None:
                    residual_fraction = counter_loss_fraction
                    client["_last_counter_loss"] = residual_fraction
                elif residual_fraction is None:
                    residual_fraction = client.get("_last_counter_loss")

                if interval_loss_value is not None:
                    interval_fraction_for_use = interval_loss_value
                    client["_last_interval_loss"] = interval_loss_value
                else:
                    interval_fraction_for_use = client.get("_last_interval_loss")

                if is_receive:
                    summary_parts = []
                    if bitrate_calc > 0:
                        summary_parts.append(f"{bitrate_calc} kbps")
                    if packet_rate > 0:
                        summary_parts.append(f"{packet_rate:.0f} pps")
                    effective_width = (
                        frame_width
                        if isinstance(frame_width, int) and frame_width > 0
                        else client.get("_last_video_width")
                    )
                    effective_height = (
                        frame_height
                        if isinstance(frame_height, int) and frame_height > 0
                        else client.get("_last_video_height")
                    )
                    if effective_width and effective_height:
                        summary_parts.append(f"{effective_width}x{effective_height}")
                    codec_label = getattr(self, "_last_viewer_codec", None)
                    if codec_label:
                        summary_parts.append(f"codec {codec_label}")
                    denom_for_raw = interval_total + max(interval_recovered, 0)
                    residual_for_summary = interval_fraction_for_use
                    if residual_for_summary is None:
                        residual_for_summary = residual_fraction
                    if residual_for_summary is None:
                        residual_for_summary = client.get("_last_counter_loss")
                    raw_loss_pct = raw_fraction * 100.0 if raw_fraction is not None else None
                    residual_pct = residual_for_summary * 100.0 if residual_for_summary is not None else None
                    recovered_pct = None
                    if interval_recovered and denom_for_raw > 0:
                        recovered_pct = (interval_recovered / denom_for_raw) * 100.0
                    loss_summary = ""
                    if raw_loss_pct is not None and residual_pct is not None:
                        loss_summary = f"loss {raw_loss_pct:.2f}% raw → {residual_pct:.2f}%"
                        if recovered_pct is not None and recovered_pct > 0:
                            loss_summary += f" (recovered {recovered_pct:.2f}%)"
                    elif residual_pct is not None:
                        loss_summary = f"loss raw unknown → {residual_pct:.2f}% (post-repair)"
                        if recovered_pct is not None and recovered_pct > 0:
                            loss_summary += f" (recovered {recovered_pct:.2f}%)"
                    elif raw_loss_pct is not None:
                        loss_summary = f"loss {raw_loss_pct:.2f}% raw"
                    if loss_summary:
                        if residual_pct is not None and residual_pct >= 1.0:
                            loss_summary += " ⚠️"
                        summary_parts.append(loss_summary)
                    if summary_parts:
                        summary_text = f"📥 Receiving {' • '.join(summary_parts)}"
                        summary_color = "07F"
                        summary_state = {
                            "bitrate": bitrate_calc,
                            "packet_rate": int(round(packet_rate)) if packet_rate > 0 else 0,
                            "resolution": (
                                effective_width if effective_width else 0,
                                effective_height if effective_height else 0,
                            ),
                            "codec": codec_label or "",
                            "loss": loss_summary,
                        }
                    else:
                        summary_text = "📥 Waiting for viewer data..."
                        summary_color = "F70"
                        summary_state = None

                    last_summary = client.get("_last_receive_summary")
                    last_summary_time = client.get("_last_receive_summary_ts", 0.0)
                    last_state = client.get("_last_receive_summary_state")
                    should_emit_summary = False
                    if summary_state is not None:
                        if not last_state:
                            should_emit_summary = True
                        else:
                            bitrate_prev = last_state.get("bitrate", 0)
                            bitrate_delta = abs(summary_state["bitrate"] - bitrate_prev)
                            bitrate_threshold = max(300, int(bitrate_prev * 0.15))

                            pps_prev = last_state.get("packet_rate", 0)
                            pps_delta = abs(summary_state["packet_rate"] - pps_prev)
                            pps_threshold = max(15, int(pps_prev * 0.2))

                            resolution_changed = summary_state["resolution"] != last_state.get("resolution")
                            codec_changed = summary_state["codec"] != last_state.get("codec")
                            loss_changed = summary_state["loss"] != last_state.get("loss")

                            if (
                                bitrate_prev == 0
                                or bitrate_delta >= bitrate_threshold
                                or pps_delta >= pps_threshold
                                or resolution_changed
                                or codec_changed
                                or loss_changed
                            ):
                                should_emit_summary = True
                        if not should_emit_summary and (current_time - last_summary_time) >= 30:
                            should_emit_summary = True
                    else:
                        should_emit_summary = summary_text != last_summary or (current_time - last_summary_time) >= 30
                    if should_emit_summary:
                        printc(summary_text, summary_color)
                        client["_last_receive_summary"] = summary_text
                        client["_last_receive_summary_ts"] = current_time
                        client["_last_receive_summary_state"] = summary_state
                    if (
                        (self.force_red or client.get("_auto_redundancy_active"))
                        and not client.get("_fec_active")
                        and not client.get("_fec_codec_warning_shown")
                    ):
                        codec_label_upper = (codec_label or "").upper()
                        if codec_label_upper == "H264":
                            printwarn(
                                "Remote sender is H264 without RED/FEC. Chrome typically omits FEC for H264, so sustained loss will still stutter unless RTX is available (requires GStreamer ≥1.24)."
                            )
                            client["_fec_codec_warning_shown"] = True
                    loss_for_hint = raw_loss_pct if raw_loss_pct is not None else residual_pct
                    if (
                        self.view
                        and self.auto_view_buffer
                        and loss_for_hint is not None
                        and loss_for_hint >= 2.0
                        and client.get("webrtc")
                    ):
                        current_latency = client.get("_latency_applied", max(self.buffer, 10))
                        target_latency = current_latency
                        if loss_for_hint >= 10.0:
                            target_latency = max(target_latency, 2000)
                        elif loss_for_hint >= 5.0:
                            target_latency = max(target_latency, 1500)
                        elif loss_for_hint >= 2.0:
                            target_latency = max(target_latency, 1000)
                        last_raise = client.get("_latency_last_raise", 0.0)
                        if (
                            target_latency > current_latency
                            and (current_time - last_raise) >= 10.0
                        ):
                            try:
                                client["webrtc"].set_property("latency", int(target_latency))
                                client["_latency_applied"] = int(target_latency)
                                client["_latency_last_raise"] = current_time
                                printc(
                                    f"   🔄 Increasing jitter buffer to {int(target_latency)} ms (loss ≈ {loss_for_hint:.2f}%)",
                                    "0FF",
                                )
                            except Exception as exc:
                                printwarn(f"Failed to raise jitter buffer latency: {exc}")
                    suppress_hint = False
                    if (
                        loss_for_hint is not None
                        and loss_for_hint >= 5.0
                        and not self.force_red
                        and not self.nored
                        and client.get("_fec_active") is not True
                        and not client.get("_auto_redundancy_active")
                    ):
                        attempts = client.get("_auto_redundancy_attempts", 0)
                        last_auto = client.get("_auto_redundancy_last", 0.0)
                        if attempts < 2 and (current_time - last_auto) >= 10:
                            success = self._apply_loss_recovery_overrides(client)
                            client["_auto_redundancy_last"] = current_time
                            if success:
                                client["_auto_redundancy_attempts"] = attempts + 1
                                suppress_hint = True
                                client["_auto_redundancy_active"] = True
                                printc("   ⚙️ Attempting to enable redundancy automatically (high loss detected)", "0FF")
                                try:
                                    on_negotiation_needed(client['webrtc'])
                                except Exception as exc:
                                    printwarn(f"Failed to trigger renegotiation for redundancy: {exc}")
                            else:
                                client["_auto_redundancy_attempts"] = attempts + 1
                    if (
                        not suppress_hint
                        and not self._loss_hint_shown
                        and loss_for_hint is not None
                        and loss_for_hint >= 2.0
                    ):
                        suggestions = []
                        fec_active = client.get("_fec_active")
                        fec_seen = client.get("_fec_seen", False)
                        rtx_state = client.get("_rtx_active")
                        rtx_seen = client.get("_rtx_seen", False)
                        auto_redundancy = client.get("_auto_redundancy_active", False)
                        rtx_active = (rtx_state is True) or self.force_rtx
                        if self.nored and not self.force_red:
                            suggestions.append("removing `--nored` to restore FEC")
                        elif fec_active is False and not self.force_red and not auto_redundancy:
                            suggestions.append("adding `--force-red` to embed redundancy when the publisher allows it")
                        elif fec_active is None and fec_seen and not self.force_red and not auto_redundancy:
                            suggestions.append("adding `--force-red` to override peers that refuse redundancy")
                        if (rtx_state is False or (rtx_seen and rtx_state is not True)) and not rtx_active and not self._rtx_support_warned:
                            suggestions.append("adding `--force-rtx`")
                        if getattr(self, "buffer", 0) < 500:
                            suggestions.append("raising the jitter buffer (e.g. `--buffer 800`)")
                        if suggestions:
                            if len(suggestions) == 1:
                                suggestion_text = suggestions[0]
                            else:
                                suggestion_text = ", ".join(suggestions[:-1]) + f", or {suggestions[-1]}"
                            printc(f"   💡 Consider {suggestion_text} to improve recovery under loss.", "FF0")
                            self._loss_hint_shown = True
                else:
                    if bitrate_calc > 0:
                        printc(f"📊 Streaming at {bitrate_calc} kbps", "07F")
                    elif current_time - client.get("_connection_time", current_time) < 5:
                        pass
                    else:
                        printc("📊 Waiting for stream data...", "F70")
                client["_last_bitrate_log"] = current_time
                client["_interval_loss_lost"] = 0
                client["_interval_loss_total"] = 0
                client["_interval_loss_recovered"] = 0
                if interval_loss_value is not None:
                    loss_value = interval_loss_value
                elif residual_fraction is not None:
                    loss_value = residual_fraction

            quality_loss_value = None
            quality_basis = None
            if raw_fraction is not None:
                quality_loss_value = raw_fraction
                quality_basis = "raw"
            else:
                residual_for_quality = interval_fraction_for_use
                if residual_for_quality is None:
                    residual_for_quality = residual_fraction
                if residual_for_quality is None:
                    residual_for_quality = client.get("_last_counter_loss")
                if residual_for_quality is not None:
                    quality_loss_value = residual_for_quality
                    quality_basis = "post-repair"
            if quality_loss_value is None and loss_value is not None:
                quality_loss_value = loss_value

            packet_loss_display = None
            packet_loss_basis = None
            if raw_fraction is not None:
                packet_loss_display = raw_fraction
                packet_loss_basis = "raw"
            else:
                packet_display_candidate = interval_fraction_for_use
                if packet_display_candidate is None:
                    packet_display_candidate = residual_fraction
                if packet_display_candidate is None:
                    packet_display_candidate = client.get("_last_counter_loss")
                if packet_display_candidate is not None:
                    packet_loss_display = packet_display_candidate
                    packet_loss_basis = "post-repair"
            if packet_loss_display is None and loss_value is not None:
                packet_loss_display = loss_value
                if packet_loss_basis is None:
                    packet_loss_basis = "post-repair"

            if quality_loss_value is not None:
                previous_quality = client.get("_last_packet_loss", -1.0)
                previous_label = client.get("_last_quality_label")
                quality_pct = None
                try:
                    quality_pct = quality_loss_value * 100.0
                except Exception:
                    quality_pct = None

                prev_display = client.get("_last_packet_loss_display", -1.0)
                display_pct = None
                significant_display_change = False
                should_log_display = False
                if packet_loss_display is not None:
                    try:
                        display_pct = packet_loss_display * 100.0
                    except Exception:
                        display_pct = None
                    significant_display_change = abs(packet_loss_display - prev_display) > 0.005
                    if prev_display < 0 and packet_loss_display >= 0:
                        should_log_display = True
                    elif packet_loss_display > 0.01 and significant_display_change:
                        should_log_display = True
                    elif packet_loss_display <= 0.01 and prev_display > 0.01:
                        should_log_display = True

                def _classify_loss(loss_percent: Optional[float]) -> Tuple[str, str]:
                    if loss_percent is None:
                        return ("unknown", "F77")
                    if loss_percent >= 20.0:
                        return ("unusable", "F00")
                    if loss_percent >= 10.0:
                        return ("poor", "F60")
                    if loss_percent >= 5.0:
                        return ("degraded", "FA0")
                    if loss_percent >= 2.0:
                        return ("fair", "CF0")
                    if loss_percent > 0.0:
                        return ("good", "6F0")
                    return ("excellent", "0F0")

                quality_label, quality_color = _classify_loss(quality_pct)
                if raw_fraction is None and quality_basis != "raw":
                    quality_label, quality_color = ("unknown", "888")
                significant_quality_change = abs(quality_loss_value - previous_quality) > 0.005
                should_log_quality = (
                    previous_quality < 0
                    or previous_label != quality_label
                    or significant_quality_change
                )

                if should_log_display or should_log_quality:
                    detail_parts = []
                    loss_basis = packet_loss_basis or quality_basis or "observed"
                    quality_display_label = quality_label
                    if isinstance(quality_label, str) and quality_label.lower() not in ("excellent", "good", "unknown"):
                        quality_display_label = f"{quality_label} ⚠️"
                    quality_label = quality_display_label
                    if raw_fraction is None and (loss_basis or "").startswith("post-repair"):
                        loss_basis = "post-repair (raw unavailable)"
                    if display_pct is not None:
                        detail_parts.append(f"{loss_basis} loss {display_pct:.2f}%")
                    elif quality_pct is not None:
                        detail_parts.append(f"{loss_basis} loss {quality_pct:.2f}%")
                    if bitrate_calc > 0:
                        detail_parts.append(f"bitrate {bitrate_calc} kbps")
                    detail_suffix = f" ({', '.join(detail_parts)})" if detail_parts else ""
                    icon_map = {
                        "unusable": "🛑",
                        "poor": "⚠️",
                        "degraded": "⚠️",
                        "fair": "⚠️",
                        "unknown": "⚠️",
                    }
                    icon = icon_map.get(quality_label, "")
                    label_with_icon = f"{quality_label}{' ' + icon if icon else ''}"
                    printc(f"📊 Network quality: {label_with_icon}{detail_suffix}", quality_color)
                    client["_last_quality_label"] = quality_label
                    if packet_loss_display is not None:
                        client["_last_packet_loss_display"] = packet_loss_display
                elif significant_display_change and packet_loss_display is not None:
                    client["_last_packet_loss_display"] = packet_loss_display

                client["_last_packet_loss"] = quality_loss_value
                if (
                    client.get("_last_packet_loss_display", -1.0) < 0
                    and packet_loss_display is not None
                ):
                    client["_last_packet_loss_display"] = packet_loss_display

            if loss_value is not None and not is_receive:
                skip_bitrate_adjustment = False
                if " vp8enc " in self.pipeline:
                    skip_bitrate_adjustment = True
                elif " av1enc " in self.pipeline:
                    skip_bitrate_adjustment = True

                if not skip_bitrate_adjustment and not self.noqos:
                    if loss_value > 0.01:
                        old_bitrate = self.bitrate
                        bitrate = self.bitrate * 0.9
                        if bitrate < self.max_bitrate * 0.2:
                            bitrate = self.max_bitrate * 0.2
                        elif bitrate > self.max_bitrate * 0.8:
                            bitrate = self.bitrate * 0.9

                        if int(bitrate) != int(old_bitrate):
                            self.bitrate = bitrate
                            printc(f"   └─ Reducing bitrate to {int(bitrate)} kbps (packet loss detected)", "FF0")
                            self.set_encoder_bitrate(client, int(bitrate))

                    elif loss_value < 0.003:
                        old_bitrate = self.bitrate
                        bitrate = self.bitrate * 1.05
                        if bitrate > self.max_bitrate:
                            bitrate = self.max_bitrate
                        elif bitrate * 2 < self.max_bitrate:
                            bitrate = self.bitrate * 1.05

                        if int(bitrate) != int(old_bitrate):
                            self.bitrate = bitrate
                            printc(f"   └─ Increasing bitrate to {int(bitrate)} kbps (good connection)", "0F0")
                            self.set_encoder_bitrate(client, int(bitrate))

        # Debug encoder setup for VP8
        if " vp8enc " in self.pipeline:
            printc("   └─ VP8 encoder detected in pipeline", "77F")
            
        printc("🔧 Creating WebRTC pipeline...", "0FF")

        started = True
        if not self.pipe:
            printc("   └─ Loading pipeline configuration...", "FFF")
        pipeline_created = self._ensure_main_pipeline(log=True)
        if not self.pipe:
            printwarn("Viewer pipeline is unavailable; aborting peer setup")
            return
        if pipeline_created:
            started = False
            
        client['qv'] = None
        client['qa'] = None
        client['encoder'] = False
        client['encoder1'] = False
        client['encoder2'] = False
        
        try:
            client['encoder'] = self.pipe.get_by_name('encoder')
            if client['encoder'] and " vp8enc " in self.pipeline:
                # Debug VP8 encoder properties
                printc(f"   └─ VP8 encoder found: {client['encoder'].get_name()}", "77F")
                try:
                    target_br = client['encoder'].get_property('target-bitrate')
                    printc(f"   └─ VP8 target-bitrate: {target_br}", "77F")
                except:
                    printc("   └─ Could not read VP8 target-bitrate property", "F77")
        except:
            try:
                client['encoder1'] = self.pipe.get_by_name('encoder1')
            except:
                try:
                    client['encoder2'] = self.pipe.get_by_name('encoder2')
                except:
                    pass

        if self.streamin:
            client['webrtc'] = Gst.ElementFactory.make("webrtcbin", client['UUID'])
            client['webrtc'].set_property('bundle-policy', "max-bundle")
            self.setup_ice_servers(client['webrtc'])
            
            try:
                # Ensure minimum latency to prevent crashes
                buffer_ms = max(self.buffer, 10)
                client['webrtc'].set_property('latency', buffer_ms)
                client['webrtc'].set_property('async-handling', True)
                client["_latency_applied"] = buffer_ms
            except Exception as E:
                pass
            self.pipe.add(client['webrtc'])
            if self.view:
                self._install_viewer_rtpbin_overrides(client['webrtc'])
                try:
                    self._ensure_display_chain()
                    self._set_display_mode("idle")
                except Exception as exc:
                    printwarn(f"Display initialization failed: {exc}")
           
            if self.vp8 or self.vp9 or self.av1 or self.h264:
                direction = GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY
                codec_label = None
                preferred_caps: List[str] = []
                if self.vp8:
                    codec_label = "VP8"
                    preferred_caps.append(
                        "application/x-rtp,media=video,encoding-name=VP8,clock-rate=90000"
                    )
                elif self.vp9:
                    codec_label = "VP9"
                    preferred_caps.extend(
                        [
                            "application/x-rtp,media=video,encoding-name=VP9,clock-rate=90000",
                            "application/x-rtp,media=video,encoding-name=VP9X,clock-rate=90000",
                            "application/x-rtp,media=video,encoding-name=VP9-DRAFT-IETF-01,clock-rate=90000",
                        ]
                    )
                elif self.av1:
                    codec_label = "AV1"
                    preferred_caps.extend(
                        [
                            "application/x-rtp,media=video,encoding-name=AV1,clock-rate=90000",
                            "application/x-rtp,media=video,encoding-name=AV1X,clock-rate=90000",
                        ]
                    )
                elif self.h264:
                    codec_label = "H264"
                    preferred_caps.append(
                        "application/x-rtp,media=video,encoding-name=H264,clock-rate=90000,packetization-mode=(string)1"
                    )

                base_caps = None
                try:
                    base_caps = Gst.Caps.from_string("application/x-rtp,media=video")
                except Exception as exc:
                    printwarn(f"Failed to construct generic video caps for transceiver: {exc}")

                tcvr = client['webrtc'].emit('add-transceiver', direction, base_caps)
                if tcvr:
                    if preferred_caps and Gst.version().minor > 18:
                        unique_caps: List[str] = []
                        for entry in preferred_caps:
                            if entry not in unique_caps:
                                unique_caps.append(entry)
                        if "application/x-rtp,media=video" not in unique_caps:
                            unique_caps.append("application/x-rtp,media=video")
                        try:
                            tcvr.set_property(
                                "codec-preferences",
                                Gst.Caps.from_string(";".join(unique_caps)),
                            )
                        except Exception as exc:
                            printwarn(f"Failed to set codec preference for {codec_label}: {exc}")
                    if codec_label:
                        display_label = codec_label if codec_label not in {"AV1X"} else "AV1"
                        printc(f"   🎯 Preferring {display_label} for incoming video (fallback enabled)", "0AF")

        elif not self.multiviewer:
            client['webrtc'] = self.pipe.get_by_name('sendrecv')
            self.setup_ice_servers(client['webrtc'])
            pass
        else:
            client['webrtc'] = Gst.ElementFactory.make("webrtcbin", client['UUID'])
            client['webrtc'].set_property('bundle-policy', 'max-bundle')
            self.setup_ice_servers(client['webrtc'])
            
            try:
                # Ensure minimum latency to prevent crashes
                buffer_ms = max(self.buffer, 10)
                client['webrtc'].set_property('latency', buffer_ms)
                client['webrtc'].set_property('async-handling', True)
                client["_latency_applied"] = buffer_ms
            except Exception as E:
                pass
            self.pipe.add(client['webrtc'])
            if self.view:
                self._install_viewer_rtpbin_overrides(client['webrtc'])

            atee = self.pipe.get_by_name('audiotee')
            vtee = self.pipe.get_by_name('videotee')

            if vtee is not None:
                qv = Gst.ElementFactory.make('queue', f"qv-{client['UUID']}")
                self.pipe.add(qv)
                if not Gst.Element.link(vtee, qv):
                    return
                if not Gst.Element.link(qv, client['webrtc']):
                    return
                if qv is not None: qv.sync_state_with_parent()
                client['qv'] = qv

            if atee is not None:
                qa = Gst.ElementFactory.make('queue', f"qa-{client['UUID']}")
                self.pipe.add(qa)
                if not Gst.Element.link(atee, qa):
                    return
                if not Gst.Element.link(qa, client['webrtc']):
                    return
                if qa is not None: qa.sync_state_with_parent()
                client['qa'] = qa

            if self.midi and (self.midi_thread == None):
                self.midi_thread = threading.Thread(target=midi2vdo, args=(self.midi,), daemon=True)
                self.midi_thread.start()
                print(self.midi_thread)
                print("MIDI THREAD STARTED")

        if client.get('webrtc') and self.force_red:
            target_fec_type = GstWebRTC.WebRTCFECType.ULP_RED
            current_fec_type, fec_type_available = self._get_gst_property_if_available(
                client['webrtc'], "preferred-fec-type"
            )
            if not fec_type_available or current_fec_type != target_fec_type:
                try:
                    client['webrtc'].set_property('preferred-fec-type', target_fec_type)
                    print("PREFERRED FEC TYPE set to ULP_RED")
                except Exception:
                    # Older GStreamer builds (≤1.22) do not expose preferred-fec-type; fall back silently
                    pass

        try:
            client['webrtc'].connect('notify::ice-connection-state', on_ice_connection_state)
            client['webrtc'].connect('notify::connection-state', on_connection_state)
            client['webrtc'].connect('notify::signaling-state', on_signaling_state)

        except Exception as e:
            printwarn(get_exception_info(E))

            pass

        if self.streamin:
            # For room recording or viewer mode, attach incoming pads to processing pipeline
            def _on_pad_added(webrtc_element, pad):
                print(f"[webrtc] Pad added: {pad.get_name()} caps={pad.get_current_caps().to_string() if pad.get_current_caps() else 'None'}")
                self.on_incoming_stream(webrtc_element, pad)

            client['webrtc'].connect('pad-added', _on_pad_added)
            client['webrtc'].connect('pad-removed', self.on_remote_pad_removed)
            client['webrtc'].connect('on-ice-candidate', send_ice_remote_candidate_message)
            client['webrtc'].connect('on-data-channel', on_data_channel)
            client['webrtc'].connect('on-new-transceiver', on_new_tranceiver)

            def _attach_existing_src_pads():
                for pad in client['webrtc'].pads:
                    try:
                        if pad.get_direction() == Gst.PadDirection.SRC:
                            self.on_incoming_stream(client['webrtc'], pad)
                    except Exception as exc:
                        printwarn(f"Failed to process existing pad {pad.get_name()}: {exc}")
                return False

            GLib.idle_add(_attach_existing_src_pads)
        else:
            client['webrtc'].connect('on-ice-candidate', send_ice_local_candidate_message)
            client['webrtc'].connect('on-negotiation-needed', on_negotiation_needed)
            client['webrtc'].connect('on-new-transceiver', on_new_tranceiver)

        try:
            configure_existing_transceivers()
        except Exception as E:
            printwarn(get_exception_info(E))

        if not started and self.pipe.get_state(0)[1] is not Gst.State.PLAYING:
            self.pipe.set_state(Gst.State.PLAYING)
            
        client['webrtc'].sync_state_with_parent()

        if not self.streamin and not client['send_channel']:
            channel = client['webrtc'].emit('create-data-channel', 'sendChannel', None)
            on_data_channel(client['webrtc'], channel)
            
        self.clients[client["UUID"]] = client
        
    
    def setup_recording_pipeline(self, pad, name):
        """Set up proper recording pipeline for incoming stream"""
        print("RECORDING MODE ACTIVATED")
        timestamp = str(int(time.time()))
        
        try:
            # Determine codec and create appropriate pipeline
            if "VP8" in name or "vp8" in name.lower():
                # VP8 recording - decode and re-encode to handle resolution changes
                filename = f"{self.record}_{timestamp}.webm"
                pipeline_str = (
                    "queue name=rec_queue max-size-buffers=0 max-size-time=0 ! "
                    "rtpvp8depay ! "
                    "vp8dec ! "
                    "videoscale ! "
                    "video/x-raw,width=1280,height=720 ! "
                    "vp8enc deadline=1 cpu-used=4 ! "
                    "matroskamux name=mux streamable=true ! "
                    f"filesink location={filename}"
                )
                print(f"Recording VP8 to: {filename} (flexible resolution)")
                
            elif "H264" in name or "h264" in name.lower():
                # H264 can go directly to MPEG-TS
                filename = f"{self.record}_{timestamp}.ts"
                pipeline_str = (
                    "queue name=rec_queue ! "
                    "rtph264depay ! "
                    "h264parse ! "
                    "mpegtsmux ! "
                    f"filesink location={filename}"
                )
                print(f"Recording H264 to: {filename}")
                
            elif "VP9" in name or "vp9" in name.lower():
                # VP9 to MKV
                filename = f"{self.record}_{timestamp}.mkv"
                pipeline_str = (
                    "queue name=rec_queue ! "
                    "rtpvp9depay ! "
                    "matroskamux ! "
                    f"filesink location={filename}"
                )
                print(f"Recording VP9 to: {filename}")
                
            else:
                print(f"Unsupported codec: {name}")
                return False
            
            # Create recording bin
            recording_bin = Gst.parse_bin_from_description(pipeline_str, True)
            
            # Add to pipeline
            self.pipe.add(recording_bin)
            
            # Sync state
            recording_bin.sync_state_with_parent()
            
            # Link pad to recording bin
            sink_pad = recording_bin.get_static_pad('sink')
            if not sink_pad:
                print("Failed to get sink pad from recording bin")
                return False
                
            link_result = pad.link(sink_pad)
            if link_result != Gst.PadLinkReturn.OK:
                print(f"Failed to link pad: {link_result}")
                return False
            
            # Track recording file
            self.recording_files.append(filename)
            print(f"Recording pipeline set up successfully")
            
            # Set up status monitoring
            self.setup_recording_monitor(filename)
            
            return True
            
        except Exception as e:
            print(f"Error setting up recording pipeline: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def setup_recording_monitor(self, filename):
        """Monitor recording progress"""
        def check_file():
            if os.path.exists(filename):
                size = os.path.getsize(filename)
                print(f"Recording progress: {filename} ({size:,} bytes)")
            return True  # Continue monitoring
        
        # Check file size periodically
        GLib.timeout_add_seconds(5, check_file)

    def handle_sdp_ice(self, msg, UUID):
        client = self.clients[UUID]
        if not client or not client['webrtc']:
            print("! CLIENT NOT FOUND OR INVALID")
            return
        if 'sdp' in msg:
            print("INCOMING ANSWER SDP TYPE: "+msg['type'])
            assert(msg['type'] == 'answer')
            sdp = msg['sdp']
            if self.view:
                try:
                    sdp = self._apply_bitrate_constraints_to_sdp(sdp, context="incoming answer")
                except Exception as exc:
                    printwarn(f"Failed to apply bitrate constraints to remote SDP: {exc}")
            res, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(bytes(sdp.encode()), sdpmsg)
            answer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg)
            promise = Gst.Promise.new()
            client['webrtc'].emit('set-remote-description', answer, promise)
            promise.interrupt()
        elif 'candidate' in msg:
            # Silently handle ICE candidates
            candidate = msg['candidate']
            sdpmlineindex = msg['sdpMLineIndex']
            client['webrtc'].emit('add-ice-candidate', sdpmlineindex, candidate)
        else:
            print(msg)
            print("UNEXPECTED INCOMING")

    def on_answer_created(self, promise, _, client):
        promise.wait()
        reply = promise.get_reply()
        answer = reply.get_value('answer')
        if not answer:
            print("Not answer created?")
            return
        text = answer.sdp.as_text()
        if self.view:
            rebuild_answer = False
            try:
                modified_text = self._apply_bitrate_constraints_to_sdp(text, context="outgoing answer")
            except Exception as exc:
                printwarn(f"Failed to apply bitrate constraints to answer SDP: {exc}")
            else:
                if modified_text != text:
                    text = modified_text
                    rebuild_answer = True
            target_profile = self._target_h264_profile_id()
            if target_profile:
                updated_text = self._apply_h264_profile_override(text, target_profile)
                if updated_text != text:
                    text = updated_text
                    rebuild_answer = True
                    if self._force_h264_profile_id and not getattr(self, "_forced_profile_notice_shown", False):
                        printc(f"   🎛 Forcing H264 profile-level-id {target_profile}", "0AF")
                        self._forced_profile_notice_shown = True
            if rebuild_answer:
                try:
                    res, sdpmsg = GstSdp.SDPMessage.new()
                    GstSdp.sdp_message_parse_buffer(bytes(text.encode()), sdpmsg)
                    answer = GstWebRTC.WebRTCSessionDescription.new(
                        GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg
                    )
                except Exception as exc:
                    printwarn(f"Failed to rebuild SDP with viewer constraints: {exc}")
                    text = answer.sdp.as_text()
        promise = Gst.Promise.new()
        client['webrtc'].emit('set-local-description', answer, promise)
        promise.interrupt()
        msg = {'description': {'type': 'answer', 'sdp': text}, 'UUID': client['UUID'], 'session': client['session']}
        self.sendMessage(msg)

    def prefer_codec(self, sdp: str, codec: str = 'h264') -> str:
        """Reorder codecs in SDP to prefer a specific codec"""
        if self.use_hls and codec == 'h264':
            printc("   🔄 Reordering SDP to prefer H264 codec", "0F0")
        
        lines = sdp.split('\n')
        video_line_index = -1
        video_codecs = []
        
        # Find video m= line
        for i, line in enumerate(lines):
            if line.startswith('m=video'):
                video_line_index = i
                parts = line.split()
                if len(parts) > 3:
                    video_codecs = parts[3:]  # Get codec numbers
                break
        
        if video_line_index < 0 or not video_codecs:
            return sdp
            
        # Find codec details from rtpmap lines
        codec_map = {}
        for line in lines:
            if line.startswith('a=rtpmap:'):
                parts = line.split()
                if len(parts) >= 2:
                    codec_num = parts[0].split(':')[1]
                    codec_details = parts[1]
                    if 'VP8/90000' in codec_details:
                        codec_map['vp8'] = codec_num
                    elif 'VP9/90000' in codec_details:
                        codec_map['vp9'] = codec_num
                    elif 'H264/90000' in codec_details:
                        codec_map['h264'] = codec_num
                    elif 'AV1/90000' in codec_details or 'AV1X/90000' in codec_details:
                        codec_map['av1'] = codec_num
        
        # If we found the video line and the preferred codec
        if video_line_index >= 0 and codec.lower() in codec_map and video_codecs:
            preferred_codec = codec_map[codec.lower()]
            
            # Reorder codecs to put preferred first
            if preferred_codec in video_codecs:
                video_codecs.remove(preferred_codec)
                video_codecs.insert(0, preferred_codec)
                
                # Rebuild the m= line
                m_parts = lines[video_line_index].split()
                m_parts[3:] = video_codecs
                lines[video_line_index] = ' '.join(m_parts)
                
                if self.use_hls:
                    printc(f"   ✅ H264 codec moved to preferred position", "0F0")
        
        return '\n'.join(lines)

    def handle_offer(self, msg, UUID):
        client = self.clients[UUID]
        if not client or not client['webrtc']:
            return
        if 'sdp' in msg:
            assert(msg['type'] == 'offer')
            sdp = msg['sdp']

            try:
                sdp = self._apply_bitrate_constraints_to_sdp(sdp, context="incoming offer")
            except Exception as exc:
                printwarn(f"Failed to apply bitrate constraints to incoming offer: {exc}")
            
            # Reorder codecs in the remote offer to match local preferences
            preferred_codec = None
            if self.vp8:
                preferred_codec = 'vp8'
            elif self.vp9:
                preferred_codec = 'vp9'
            elif self.av1:
                preferred_codec = 'av1'
            elif self.h264:
                preferred_codec = 'h264'
            elif self.use_hls:
                preferred_codec = 'h264'

            if preferred_codec:
                sdp = self.prefer_codec(sdp, preferred_codec)
            if self.view:
                self._capture_remote_video_profiles(sdp)
                try:
                    self._update_viewer_redundancy_from_sdp(sdp)
                except Exception as exc:
                    printwarn(f"Failed to parse redundancy info from remote SDP: {exc}")
            
            res, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(bytes(sdp.encode()), sdpmsg)
            offer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.OFFER, sdpmsg)
            promise = Gst.Promise.new()
            client['webrtc'].emit('set-remote-description', offer, promise)
            promise.interrupt()
            promise2 = Gst.Promise.new_with_change_func(self.on_answer_created, client['webrtc'], client)
            client['webrtc'].emit('create-answer', None, promise2)
        else:
            print("No SDP as expected")

    async def start_pipeline(self, UUID):
        printc("\n🎬 Starting video pipeline...", "0FF")
        enableLEDs(100)
        if self.multiviewer:
            await self.createPeer(UUID)
        else:
            for uid in self.clients:
                if uid != UUID:
                    printc("⚠️  New viewer replacing previous one (use --multiviewer for multiple viewers)", "F70")
                    self.stop_pipeline(uid, wait=True)
                    break
            if self.save_file:
                pass
            elif self.pipe:
                print("setting pipe to null")
                
                if UUID in self.clients:
                    print("Resetting existing pipe and p2p connection.")
                    # Save session before cleanup
                    session = self.clients[UUID]["session"] if "session" in self.clients[UUID] else None

                    # Cancel timer if exists
                    if 'timer' in self.clients[UUID] and self.clients[UUID]['timer']:
                        try:
                            self.clients[UUID]['timer'].cancel()
                            print("stop previous ping/pong timer")
                        except:
                            pass
                    
                    # Clean up webrtc element if it exists
                    if 'webrtc' in self.clients[UUID] and self.clients[UUID]['webrtc']:
                        try:
                            self.clients[UUID]['webrtc'].set_state(Gst.State.NULL)
                        except:
                            pass

                    # Reset client data
                    self.clients[UUID] = {}
                    self.clients[UUID]["UUID"] = UUID
                    self.clients[UUID]["session"] = session
                    self.clients[UUID]["send_channel"] = None
                    self.clients[UUID]["timer"] = None
                    self.clients[UUID]["ping"] = 0
                    self.clients[UUID]["webrtc"] = None
                    self.clients[UUID]["direction"] = "receive" if self.view else "send"
                
                # Set pipeline to NULL after cleaning up elements
                try:
                    self.pipe.set_state(Gst.State.NULL)
                except Exception as e:
                    printwarn(f"Failed to set pipeline to NULL: {e}")
                self.pipe = None

            await self.createPeer(UUID)

    def stop_pipeline(self, UUID, wait=False):
        if wait:
            self._stop_pipeline_internal(UUID)
        else:
            threading.Thread(target=self._stop_pipeline_internal, args=(UUID,), daemon=True).start()

    def _stop_pipeline_internal(self, UUID):
        printc("🛑 Stopping pipeline for viewer", "F77")
        if getattr(self, "_shutdown_requested", False):
            self._viewer_restart_enabled = False
            self._viewer_restart_pending = False
            self._cancel_viewer_restart_timer()
            self._viewer_restart_attempts = 0
            self._viewer_last_play_request = 0.0
            self._viewer_last_disconnect = 0.0
        restart_display = False
        with self.pipeline_lock:
            client = self.clients.get(UUID)
            if not client:
                print(f"Client {UUID} not found in clients list")
                return
            should_restart = (
                bool(self.view)
                and not getattr(self, "_shutdown_requested", False)
                and bool(self._viewer_restart_enabled)
            )
            
            # Cancel the ping timer if it exists
            timer = client.get('timer')
            if timer is not None:
                try:
                    timer.cancel()
                except Exception as e:
                    printwarn(f"Failed to cancel timer: {e}")
                client['timer'] = None
                
            if self.multiviewer:
                # In multiviewer mode, unlink from tees
                atee = self.pipe.get_by_name('audiotee') if self.pipe else None
                vtee = self.pipe.get_by_name('videotee') if self.pipe else None

                # Unlink elements before cleanup to prevent dangling references
                try:
                    qa = client.get('qa')
                    if atee is not None and qa is not None:
                        atee.unlink(qa)
                except Exception as e:
                    printwarn(f"Failed to unlink audio queue: {e}")
                    
                try:
                    qv = client.get('qv')
                    if vtee is not None and qv is not None:
                        vtee.unlink(qv)
                except Exception as e:
                    printwarn(f"Failed to unlink video queue: {e}")

            # CRITICAL: Set elements to NULL state BEFORE removing from pipeline
            # This prevents segfaults during cleanup
            try:
                webrtc = client.get('webrtc')
                if webrtc is not None:
                    webrtc.set_state(Gst.State.NULL)
                    if self.pipe:
                        self.pipe.remove(webrtc)
            except Exception as e:
                printwarn(f"Failed to cleanup webrtc element: {e}")
                
            try:
                qa = client.get('qa')
                if qa is not None:
                    qa.set_state(Gst.State.NULL)
                    if self.pipe:
                        self.pipe.remove(qa)
            except Exception as e:
                printwarn(f"Failed to cleanup audio queue: {e}")
                
            try:
                qv = client.get('qv')
                if qv is not None:
                    qv.set_state(Gst.State.NULL)
                    if self.pipe:
                        self.pipe.remove(qv)
            except Exception as e:
                printwarn(f"Failed to cleanup video queue: {e}")
                
            # Always remove from clients dict, even if cleanup failed
            self.clients.pop(UUID, None)

            if self.view:
                if self.display_remote_map:
                    for pad_name, label in list(self.display_remote_map.items()):
                        self._log_fec_stats_for_pad(pad_name, label or pad_name)
                        try:
                            self._release_display_source(label)
                        except Exception:
                            pass
                    self.display_remote_map.clear()
                if self.display_sources:
                    self._release_all_display_sources(include_blank=False)
                if self.pipe:
                    try:
                        iterator = self.pipe.iterate_elements()
                        while True:
                            res, element = iterator.next()
                            if res == Gst.IteratorResult.OK and element:
                                name = element.get_name() or ""
                                if name.startswith("viewer_rtpulpfecdec"):
                                    self._log_viewer_fec_stats(name, element)
                            elif res == Gst.IteratorResult.DONE:
                                break
                    except Exception:
                        pass
                if self._viewer_fec_decoders:
                    if bool(os.environ.get("RN_DEBUG_VIEWER")):
                        print(
                            f"[viewer] Releasing {len(self._viewer_fec_decoders)} cached FEC decoder(s)"
                        )
                    for label, fecdec in list(self._viewer_fec_decoders.items()):
                        self._log_viewer_fec_stats(label, fecdec)
                        if bool(os.environ.get("RN_DEBUG_VIEWER")):
                            print(f"[viewer] Flushed cached FEC stats for {label}")
                    self._viewer_fec_decoders.clear()
                if self._pending_viewer_fec_decoders:
                    self._pending_viewer_fec_decoders.clear()

            if should_restart and len(self.clients) == 0:
                restart_display = True

        if len(self.clients)==0:
            enableLEDs(0.1)
            if should_restart:
                self._viewer_last_disconnect = time.monotonic()
                self._viewer_restart_attempts = 0
                self._viewer_last_play_request = 0.0
                self._cancel_viewer_restart_timer()
                self._viewer_restart_pending = False
                self._request_view_stream_restart()

        if self.pipe:
            if self.save_file:
                pass
            elif len(self.clients)==0:
                if restart_display:
                    try:
                        self._set_display_mode("idle")
                        self.pipe.set_state(Gst.State.PLAYING)
                    except Exception as e:
                        printwarn(f"Failed to keep display idle after disconnect: {e}")
                else:
                    # Ensure pipeline is properly cleaned up when no clients remain
                    try:
                        self._reset_display_chain_state()
                        self._display_surface_cleared = False
                        pause_result = self.pipe.set_state(Gst.State.PAUSED)
                        if pause_result == Gst.StateChangeReturn.FAILURE:
                            printwarn("Error pausing pipeline during viewer cleanup")
                        null_result = self.pipe.set_state(Gst.State.NULL)
                        if null_result == Gst.StateChangeReturn.FAILURE:
                            printwarn("Error setting pipeline to NULL during viewer cleanup")
                    except Exception as e:
                        printwarn(f"Error setting pipeline to NULL: {e}")
                        # Force cleanup even if state change failed
                        try:
                            self.pipe.set_state(Gst.State.NULL)
                        except:
                            pass
                    finally:
                        # Always clear the pipeline reference to prevent reuse
                        self.pipe = None
    async def _add_room_stream(self, stream_id):
        """Add a stream for room recording"""
        if stream_id in self.room_recorders:
            printc(f"Stream {stream_id} already being recorded", "FF0")
            return
            
        printc(f"\n📹 Adding recorder for stream: {stream_id}", "0F0")
        
        # Create recorder
        recorder = self._create_stream_recorder(stream_id)
        if not recorder:
            return
            
        self.room_recorders[stream_id] = recorder
        
        # Request to play this stream
        printc(f"[{stream_id}] Requesting stream playback", "77F")
        await self.sendMessageAsync({
            "request": "play",
            "streamID": stream_id
        })
    
    def _create_stream_recorder(self, stream_id):
        """Create a recorder for a single stream"""
        # Ensure GStreamer is initialized
        if not Gst.is_initialized():
            Gst.init(None)
            
        recorder = {
            'stream_id': stream_id,
            'session_id': None,
            'pipe': None,
            'webrtc': None,
            'filesink': None,
            'recording': False,
            'recording_file': None,
            'start_time': None,
            'ice_candidates': []  # Store candidates to send later
        }
        
        # Create pipeline
        pipe = Gst.Pipeline.new(f'pipe_{stream_id}')
        webrtc = Gst.ElementFactory.make('webrtcbin', 'webrtc')
        
        if not webrtc:
            printc(f"[{stream_id}] ERROR: Failed to create webrtcbin", "F00")
            return None
            
        # Configure webrtcbin
        webrtc.set_property('bundle-policy', GstWebRTC.WebRTCBundlePolicy.MAX_BUNDLE)
        webrtc.set_property('latency', 0)
        
        # Use the same ICE server configuration as main connection
        # First ensure we have the attributes setup_ice_servers expects
        if not hasattr(self, 'stun_server'):
            self.stun_server = None
        if not hasattr(self, 'turn_server'):
            self.turn_server = None
        if not hasattr(self, 'no_stun'):
            self.no_stun = False
        if not hasattr(self, 'ice_transport_policy'):
            self.ice_transport_policy = None
            
        self.setup_ice_servers(webrtc)
        
        pipe.add(webrtc)
        
        # Don't add transceivers here - wait for the offer to determine what's needed
        # This matches how single-stream recording works
        printc(f"[{stream_id}] WebRTC element created, waiting for offer...", "77F")
        
        # Connect signals
        webrtc.connect('on-ice-candidate', self._on_room_ice_candidate, recorder)
        webrtc.connect('pad-added', self._on_room_pad_added, recorder)
        webrtc.connect('notify::connection-state', self._on_room_connection_state, recorder)
        webrtc.connect('notify::ice-connection-state', self._on_room_ice_connection_state, recorder)
        webrtc.connect('notify::ice-gathering-state', self._on_room_ice_gathering_state, recorder)
        
        # Add data channel support (VDO.Ninja uses this for signaling)
        webrtc.connect('on-data-channel', self._on_room_data_channel, recorder)
        
        # Start pipeline
        ret = pipe.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            printc(f"[{stream_id}] ERROR: Failed to start pipeline", "F00")
            return None
        
        # Wait for pipeline to reach PLAYING state
        ret = pipe.get_state(Gst.SECOND)
        if ret[0] != Gst.StateChangeReturn.SUCCESS:
            printc(f"[{stream_id}] WARNING: Pipeline didn't reach PLAYING state", "FF0")
            
        recorder['pipe'] = pipe
        recorder['webrtc'] = webrtc
        
        printc(f"[{stream_id}] Pipeline created successfully (state: {pipe.get_state(0)[1].value_name})", "0F0")
        return recorder
    
    def _on_room_ice_candidate(self, webrtc, mlineindex, candidate, recorder):
        """Handle ICE candidate for room recording"""
        # Queue the candidate
        recorder['ice_candidates'].append((candidate, mlineindex))
        # Put in async queue for sending using thread-safe method
        if self.event_loop:
            asyncio.run_coroutine_threadsafe(
                self.ice_queue.put((recorder['stream_id'], recorder['session_id'], candidate, mlineindex)),
                self.event_loop
            )
        else:
            # Fallback: just store it
            printc(f"[{recorder['stream_id']}] Warning: No event loop for ICE candidate", "FF0")
    
    def _on_room_pad_added(self, webrtc, pad, recorder):
        """Handle new pad for room recording"""
        stream_id = recorder['stream_id']
        printc(f"[{stream_id}] New pad added: {pad.get_name()}", "77F")
        
        caps = pad.get_current_caps()
        if not caps:
            printc(f"[{stream_id}] No caps on pad yet", "FF0")
            return
            
        printc(f"[{stream_id}] Pad caps: {caps.to_string()}", "77F")
        
        structure = caps.get_structure(0)
        name = structure.get_name()
        
        if name.startswith('application/x-rtp'):
            media = structure.get_string('media')
            printc(f"[{stream_id}] Media type: {media}", "77F")
            
            if media != 'video':
                printc(f"[{stream_id}] Ignoring non-video media", "77F")
                return
                
            encoding_name = structure.get_string('encoding-name')
            printc(f"[{stream_id}] Video codec: {encoding_name}", "0F0")
            
            self._setup_room_recording(pad, encoding_name, recorder)
        else:
            printc(f"[{stream_id}] Ignoring non-RTP pad: {name}", "77F")
    
    def _on_room_connection_state(self, webrtc, pspec, recorder):
        """Monitor connection state for room recording"""
        state = webrtc.get_property('connection-state')
        stream_id = recorder['stream_id']
        printc(f"[{stream_id}] Connection state: {state.value_name}", "77F")
        
        if state == GstWebRTC.WebRTCPeerConnectionState.FAILED:
            ice_state = webrtc.get_property('ice-connection-state')
            ice_gathering_state = webrtc.get_property('ice-gathering-state')
            printc(f"[{stream_id}] ICE connection state: {ice_state.value_name}", "F00")
            printc(f"[{stream_id}] ICE gathering state: {ice_gathering_state.value_name}", "F00")
            printc(f"[{stream_id}] Connection failed - check STUN/TURN connectivity", "F00")
            # Schedule cleanup using the stored event loop
            if hasattr(self, 'event_loop') and self.event_loop:
                asyncio.run_coroutine_threadsafe(
                    self._cleanup_room_stream(stream_id),
                    self.event_loop
                )
            else:
                printc(f"[{stream_id}] Warning: Cannot cleanup - no event loop", "FF0")
        elif state == GstWebRTC.WebRTCPeerConnectionState.DISCONNECTED:
            printc(f"[{stream_id}] Peer disconnected", "F77")
            # Schedule cleanup using the stored event loop
            if hasattr(self, 'event_loop') and self.event_loop:
                asyncio.run_coroutine_threadsafe(
                    self._cleanup_room_stream(stream_id),
                    self.event_loop
                )
        elif state == GstWebRTC.WebRTCPeerConnectionState.CLOSED:
            printc(f"[{stream_id}] Connection closed", "F77")
            # Schedule cleanup using the stored event loop
            if hasattr(self, 'event_loop') and self.event_loop:
                asyncio.run_coroutine_threadsafe(
                    self._cleanup_room_stream(stream_id),
                    self.event_loop
                )
    
    def _on_room_ice_connection_state(self, webrtc, pspec, recorder):
        """Monitor ICE connection state"""
        state = webrtc.get_property('ice-connection-state')
        stream_id = recorder['stream_id']
        printc(f"[{stream_id}] ICE connection state: {state.value_name}", "77F")
        
        # More debugging for NEW state
        if state == GstWebRTC.WebRTCICEConnectionState.NEW:
            # Get more details
            ice_agent = webrtc.get_property('ice-agent')
            if ice_agent:
                gathering_state = webrtc.get_property('ice-gathering-state')
                printc(f"[{stream_id}] ICE gathering state: {gathering_state.value_name}", "FF0")
                
                # Check if we have local/remote descriptions
                local_desc = webrtc.get_property('local-description')
                remote_desc = webrtc.get_property('remote-description')
                printc(f"[{stream_id}] Has local desc: {local_desc is not None}, Has remote desc: {remote_desc is not None}", "FF0")
                
                # Check ICE agent state
                if hasattr(ice_agent, 'get_property'):
                    try:
                        # Try to get more ICE agent info
                        controlling = ice_agent.get_property('controlling-mode')
                        printc(f"[{stream_id}] ICE controlling mode: {controlling}", "FF0")
                    except:
                        pass
        
        # Debug why ICE might be stuck in NEW state
        if state == GstWebRTC.WebRTCICEConnectionState.NEW:
            # Check if we have remote description
            remote_desc = webrtc.get_property('remote-description')
            local_desc = webrtc.get_property('local-description')
            printc(f"[{recorder['stream_id']}] Has remote desc: {remote_desc is not None}, Has local desc: {local_desc is not None}", "FF0")
    
    def _on_room_ice_gathering_state(self, webrtc, pspec, recorder):
        """Monitor ICE gathering state"""
        state = webrtc.get_property('ice-gathering-state')
        printc(f"[{recorder['stream_id']}] ICE gathering state: {state.value_name}", "77F")
    
    def _on_room_data_channel(self, webrtc, channel, recorder):
        """Handle data channel for room recording"""
        stream_id = recorder['stream_id']
        printc(f"[{stream_id}] Data channel received: {channel.get_property('label')}", "0F0")
        
        # Connect to data channel signals for debugging
        channel.connect('on-open', lambda ch: printc(f"[{stream_id}] Data channel opened", "0F0"))
        channel.connect('on-close', lambda ch: printc(f"[{stream_id}] Data channel closed", "F77"))
        channel.connect('on-message-string', lambda ch, msg: printc(f"[{stream_id}] Data message: {msg}", "77F"))
        channel.connect('on-error', lambda ch: printc(f"[{stream_id}] Data channel error", "F00"))
    
    def _setup_room_recording(self, pad, encoding_name, recorder):
        """Set up recording pipeline for a room stream"""
        if recorder['recording']:
            return
            
        stream_id = recorder['stream_id']
        
        # Generate filename
        timestamp = int(time.time())
        
        # Create recording pipeline using parse_bin_from_description (like single-stream does)
        if encoding_name == 'H264':
            recording_file = f"{self.record}_{stream_id}_{timestamp}.ts"
            # Match single-stream H264 recording pattern
            pipeline_str = (
                f"queue ! rtph264depay ! h264parse ! mpegtsmux ! "
                f"filesink name=filesink_{stream_id} location={recording_file}"
            )
            printc(f"[{stream_id}] 🎥 ROOM VIDEO RECORDING [{encoding_name}]", "0F0")
            printc(f"[{stream_id}]    📦 Direct copy (no transcoding)", "0F0")
            printc(f"[{stream_id}]    📁 Output: {recording_file}", "0FF")
            printc(f"[{stream_id}]    📐 Format: MPEG-TS container", "77F")
        elif encoding_name == 'VP8':
            # VP8 recording - decode and re-encode to handle resolution changes
            recording_file = f"{self.record}_{stream_id}_{timestamp}.webm"
            pipeline_str = (
                f"queue max-size-buffers=0 max-size-time=0 ! "
                f"rtpvp8depay ! "
                f"vp8dec ! "
                f"videoscale ! "
                f"video/x-raw,width=1280,height=720 ! "
                f"vp8enc deadline=1 cpu-used=4 ! "
                f"matroskamux streamable=true ! "
                f"filesink name=filesink_{stream_id} location={recording_file}"
            )
            printc(f"[{stream_id}] 🎥 ROOM VIDEO RECORDING [{encoding_name}]", "0F0")
            printc(f"[{stream_id}]    🔄 Transcoding VP8 → VP8 (for resolution stability)", "FF0")
            printc(f"[{stream_id}]    📁 Output: {recording_file}", "0FF")
            printc(f"[{stream_id}]    📐 Resolution: 1280x720", "77F")
            printc(f"[{stream_id}]    📐 Format: WebM container", "77F")
        elif encoding_name == 'VP9':
            recording_file = f"{self.record}_{stream_id}_{timestamp}.mkv"
            pipeline_str = (
                f"queue ! rtpvp9depay ! matroskamux ! "
                f"filesink name=filesink_{stream_id} location={recording_file}"
            )
            printc(f"[{stream_id}] 🎥 ROOM VIDEO RECORDING [{encoding_name}]", "0F0")
            printc(f"[{stream_id}]    📦 Direct copy (no transcoding)", "0F0")
            printc(f"[{stream_id}]    📁 Output: {recording_file}", "0FF")
            printc(f"[{stream_id}]    📐 Format: Matroska (MKV) container", "77F")
        else:
            printc(f"[{stream_id}] Unknown codec: {encoding_name}", "F00")
            return
        
        # Create bin from description
        try:
            out = Gst.parse_bin_from_description(pipeline_str, True)
            if not out:
                printc(f"[{stream_id}] ❌ Failed to create recording bin", "F00")
                return
        except Exception as e:
            printc(f"[{stream_id}] ❌ Error creating recording bin: {e}", "F00")
            return
            
        # Add to pipeline
        pipe = recorder['pipe']
        pipe.add(out)
        out.sync_state_with_parent()
        
        # Get the sink pad from the bin
        sink = out.get_static_pad('sink')
        if not sink:
            printc(f"[{stream_id}] ❌ Failed to get sink pad from recording bin", "F00")
            return
            
        # Check if pad is already linked
        if pad.is_linked():
            printc(f"[{stream_id}] ⚠️  Pad already linked", "FF0")
            return
            
        # Link pad to bin
        link_result = pad.link(sink)
        
        if link_result == Gst.PadLinkReturn.OK:
            recorder['recording'] = True
            recorder['recording_file'] = recording_file
            recorder['filesink'] = pipe.get_by_name(f'filesink_{stream_id}')
            recorder['start_time'] = time.time()
            printc(f"[{stream_id}] ✅ Recording active - writing to disk", "0F0")
            
            # Update room_streams to show recording status
            async def update_status():
                async with self.room_streams_lock:
                    for uuid, stream_info in self.room_streams.items():
                        if stream_info.get('streamID') == stream_id:
                            stream_info['recording'] = True
                            break
            asyncio.create_task(update_status())
        else:
            printc(f"[{stream_id}] ❌ Failed to link recording pipeline: {link_result}", "F00")
            # Debug info
            pad_caps = pad.get_current_caps()
            sink_caps = sink.get_pad_template_caps()
            printc(f"[{stream_id}] Pad caps: {pad_caps.to_string() if pad_caps else 'None'}", "F00")
            printc(f"[{stream_id}] Sink caps: {sink_caps.to_string() if sink_caps else 'None'}", "F00")
    
    async def _cleanup_room_stream(self, stream_id):
        """Clean up a disconnected room stream"""
        printc(f"[{stream_id}] 🧹 Cleaning up disconnected stream", "F77")
        
        # Remove from room_recorders
        if stream_id in self.room_recorders:
            recorder = self.room_recorders[stream_id]
            
            # Stop the pipeline if it exists
            if recorder.get('pipe'):
                printc(f"[{stream_id}] Stopping pipeline", "F77")
                recorder['pipe'].set_state(Gst.State.NULL)
            
            # Remove from recorders
            del self.room_recorders[stream_id]
            printc(f"[{stream_id}] Removed from recorders", "F77")
        
        # Remove from room_streams
        async with self.room_streams_lock:
            # Find UUID by stream_id
            uuid_to_remove = None
            for uuid, stream_info in self.room_streams.items():
                if stream_info.get('streamID') == stream_id:
                    uuid_to_remove = uuid
                    break
            
            if uuid_to_remove:
                del self.room_streams[uuid_to_remove]
                printc(f"[{stream_id}] Removed from room streams", "F77")
    
    async def _process_ice_candidates(self):
        """Process ICE candidates from room recorders"""
        while True:
            try:
                stream_id, session_id, candidate, mlineindex = await self.ice_queue.get()
                
                # If no session yet, get it from recorder
                if not session_id and stream_id in self.room_recorders:
                    session_id = self.room_recorders[stream_id].get('session_id')
                
                if session_id:  # Only send if we have a session
                    await self.sendMessageAsync({
                        'candidates': [{
                            'candidate': candidate,
                            'sdpMLineIndex': mlineindex
                        }],
                        'session': session_id,
                        'type': 'local',  # We're sending OUR candidates, so type is 'local'
                        'UUID': self.puuid
                    })
                    printc(f"[{stream_id}] Sent ICE candidate with session {session_id[:10]}...", "77F")
                else:
                    # Re-queue if no session yet
                    printc(f"[{stream_id}] No session yet, re-queueing ICE candidate", "FF0")
                    await asyncio.sleep(0.1)
                    await self.ice_queue.put((stream_id, session_id, candidate, mlineindex))
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                printwarn(f"Error processing ICE candidate: {e}")
    
    async def _handle_room_message(self, msg):
        """Handle messages for room recording"""
        # Debug what message types we're getting
        msg_type = None
        if 'description' in msg:
            msg_type = f"description/{msg['description'].get('type', 'unknown')}"
        elif 'candidates' in msg:
            msg_type = f"candidates({len(msg['candidates'])})"
        elif 'candidate' in msg:
            msg_type = "single-candidate"
        elif 'request' in msg:
            msg_type = f"request/{msg['request']}"
        else:
            msg_type = "unknown"
            
        if msg_type not in ['request/ping', 'unknown']:  # Don't log pings
            printc(f"[Room Recording] Handling message type: {msg_type}, session: {msg.get('session', 'none')[:20]}...", "77F")
        
        # Check if this is an offer for a room stream
        if 'description' in msg and msg['description'].get('type') == 'offer':
            session = msg.get('session')
            # Find which stream this is for
            stream_id = None
            
            # Check by session
            if session in self.room_sessions:
                stream_id = self.room_sessions[session]
            else:
                # Check by matching to recorder without session
                for sid, recorder in self.room_recorders.items():
                    if not recorder['session_id']:
                        stream_id = sid
                        break
            
            if stream_id:
                answer_sdp = await self._handle_room_offer(
                    msg['description']['sdp'],
                    session,
                    stream_id
                )
                
                if answer_sdp:
                    await self.sendMessageAsync({
                        'description': {
                            'type': 'answer',
                            'sdp': answer_sdp
                        },
                        'session': session,
                        'UUID': self.puuid
                    })
                return True
        
        # Handle ICE candidates
        elif 'candidates' in msg:
            session = msg.get('session')
            stream_id = None
            
            # Try to find stream by session
            if session in self.room_sessions:
                stream_id = self.room_sessions[session]
            else:
                # Try to match by 'from' field or other identifiers
                from_id = msg.get('from')
                if from_id:
                    for sid, recorder in self.room_recorders.items():
                        # Match if session matches or if this is the only active recorder
                        if (recorder.get('session_id') == session or 
                            (not recorder.get('session_id') and len(self.room_recorders) == 1)):
                            stream_id = sid
                            # Update session mapping
                            if session and not recorder.get('session_id'):
                                recorder['session_id'] = session
                                self.room_sessions[session] = sid
                            break
            
            if stream_id:
                recorder = self.room_recorders.get(stream_id)
                if recorder and recorder['webrtc']:
                    added_count = 0
                    for candidate in msg['candidates']:
                        if 'candidate' in candidate:
                            try:
                                # Debug candidate format
                                cand_str = candidate['candidate']
                                mline = candidate.get('sdpMLineIndex', 0)
                                
                                # Add the candidate
                                recorder['webrtc'].emit('add-ice-candidate', mline, cand_str)
                                added_count += 1
                                
                                # Log TURN candidates specifically
                                if 'typ relay' in cand_str:
                                    printc(f"[{stream_id}] Added TURN candidate: {cand_str[:60]}...", "0F0")
                            except Exception as e:
                                printc(f"[{stream_id}] Error adding ICE candidate: {e}", "F00")
                                printc(f"[{stream_id}] Candidate was: {candidate}", "F00")
                    printc(f"[{stream_id}] Added {added_count}/{len(msg['candidates'])} remote ICE candidates", "77F")
                    return True
            else:
                printc(f"Warning: Received ICE candidates for unknown session: {session}", "FF0")
                return True
        
        # Handle single ICE candidate (some implementations send one at a time)
        elif 'candidate' in msg:
            session = msg.get('session')
            stream_id = None
            
            # Try to find stream by session
            if session in self.room_sessions:
                stream_id = self.room_sessions[session]
            else:
                # For single recorder, assume it's for that one
                if len(self.room_recorders) == 1:
                    stream_id = list(self.room_recorders.keys())[0]
                    
            if stream_id:
                recorder = self.room_recorders.get(stream_id)
                if recorder and recorder['webrtc']:
                    try:
                        recorder['webrtc'].emit('add-ice-candidate',
                                              msg.get('sdpMLineIndex', 0),
                                              msg['candidate'])
                        printc(f"[{stream_id}] Added single remote ICE candidate", "77F")
                    except Exception as e:
                        printc(f"[{stream_id}] Error adding single ICE candidate: {e}", "F00")
                    return True
        
        return False
    
    async def _handle_room_offer(self, offer_sdp, session_id, stream_id):
        """Handle SDP offer for room recording"""
        recorder = self.room_recorders.get(stream_id)
        if not recorder:
            printc(f"[{stream_id}] No recorder found for offer", "F00")
            return None
            
        recorder['session_id'] = session_id
        self.room_sessions[session_id] = stream_id
        
        webrtc = recorder['webrtc']
        if not webrtc:
            return None
            
        printc(f"[{stream_id}] Setting remote description", "77F")
        
        # Parse SDP
        res, sdp_msg = GstSdp.SDPMessage.new_from_text(offer_sdp)
        if res != GstSdp.SDPResult.OK:
            printc(f"[{stream_id}] ERROR: Failed to parse SDP", "F00")
            return None
            
        offer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.OFFER,
            sdp_msg
        )
        
        # Ensure pipeline is playing before negotiation
        pipe = recorder.get('pipe')
        if pipe:
            state = pipe.get_state(0)[1]
            if state != Gst.State.PLAYING:
                printc(f"[{stream_id}] WARNING: Pipeline not in PLAYING state before negotiation: {state.value_name}", "FF0")
        
        # Set remote description (match main handler pattern)
        promise = Gst.Promise.new()
        webrtc.emit('set-remote-description', offer, promise)
        promise.interrupt()  # Don't wait, let it complete asynchronously
        
        # Create answer with callback
        answer_ready = asyncio.Event()
        answer_sdp = None
        
        def on_answer_ready(promise, webrtc):
            nonlocal answer_sdp
            promise.wait()
            reply = promise.get_reply()
            if reply:
                answer = reply.get_value('answer')
                if answer:
                    # Set local description
                    promise2 = Gst.Promise.new()
                    webrtc.emit('set-local-description', answer, promise2)
                    promise2.interrupt()
                    
                    answer_sdp = answer.sdp.as_text()
                    printc(f"[{stream_id}] Answer created successfully", "0F0")
                else:
                    printc(f"[{stream_id}] ERROR: No answer in reply", "F00")
            else:
                printc(f"[{stream_id}] ERROR: No reply when creating answer", "F00")
            answer_ready.set()
        
        # Create answer with callback
        promise = Gst.Promise.new_with_change_func(on_answer_ready, webrtc)
        webrtc.emit('create-answer', None, promise)
        
        # Wait for answer to be ready
        await answer_ready.wait()
        
        if not answer_sdp:
            return None
        
        # Send any pending ICE candidates now that we have a session
        pending = recorder.get('ice_candidates', [])
        if pending:
            printc(f"[{stream_id}] Sending {len(pending)} pending ICE candidates", "77F")
            for candidate, mlineindex in pending:
                if self.event_loop:
                    asyncio.run_coroutine_threadsafe(
                        self.ice_queue.put((stream_id, session_id, candidate, mlineindex)),
                        self.event_loop
                    )
            # Clear the pending list
            recorder['ice_candidates'] = []
        
        return answer_sdp

    async def _await_state_change(
        self,
        element,
        label: str,
        timeout_secs: float = 1.0,
    ) -> Gst.StateChangeReturn:
        """Poll a Gst.Element state change without blocking the event loop."""
        if not element:
            return Gst.StateChangeReturn.SUCCESS

        deadline = time.monotonic() + max(timeout_secs, 0.0)
        last_result = Gst.StateChangeReturn.ASYNC

        while True:
            try:
                last_result, current, pending = element.get_state(0)
            except Exception as exc:
                printwarn(f"Error checking {label} state: {exc}")
                return Gst.StateChangeReturn.FAILURE

            if last_result in (
                Gst.StateChangeReturn.SUCCESS,
                Gst.StateChangeReturn.NO_PREROLL,
                Gst.StateChangeReturn.FAILURE,
            ):
                return last_result

            if time.monotonic() >= deadline:
                return last_result

            await asyncio.sleep(0.05)

    async def cleanup_pipeline(self):
        """Safely cleanup pipeline and all resources"""
        async with self.cleanup_lock:
            printc("Cleaning up pipeline and resources...", "FF0")
            self._viewer_restart_enabled = False
            self._viewer_restart_pending = False
            self._cancel_viewer_restart_timer()

            if getattr(self, "ice_processor_task", None):
                task = self.ice_processor_task
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                self.ice_processor_task = None

            if self._background_tasks:
                for task in list(self._background_tasks):
                    task.cancel()
                for task in list(self._background_tasks):
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        printwarn(f"Background task shutdown error: {exc}")
                self._background_tasks.clear()
            
            # Stop subprocess managers if active
            if self.subprocess_managers:
                printc("Stopping subprocess recorders...", "77F")
                await self.cleanup_subprocess_managers()
            
            # Report recorded files if any
            if self.recording_files:
                print("\n" + "="*60)
                print("Recording Summary:")
                total_size = 0
                for f in self.recording_files:
                    if os.path.exists(f):
                        size = os.path.getsize(f)
                        total_size += size
                        print(f"  - {f} ({size:,} bytes)")
                    else:
                        print(f"  - {f} (not found)")
                print(f"\n  Total size: {total_size:,} bytes")
                print("="*60)
            
            # Stop all client connections first
            client_uuids = list(self.clients.keys())
            for uuid in client_uuids:
                try:
                    self.stop_pipeline(uuid, wait=True)
                except Exception as e:
                    printwarn(f"Error stopping client {uuid}: {e}")
            
            # Clean up main pipeline
            if self.pipe:
                self._flush_publisher_fec_probe()
                try:
                    pause_result = self.pipe.set_state(Gst.State.PAUSED)
                    if pause_result == Gst.StateChangeReturn.ASYNC:
                        pause_result = await self._await_state_change(
                            self.pipe, "pipeline pause", timeout_secs=1.0
                        )
                    if pause_result not in (
                        Gst.StateChangeReturn.SUCCESS,
                        Gst.StateChangeReturn.NO_PREROLL,
                    ):
                        printwarn("Pipeline didn't pause cleanly, forcing NULL state")

                    null_result = self.pipe.set_state(Gst.State.NULL)
                    if null_result == Gst.StateChangeReturn.ASYNC:
                        null_result = await self._await_state_change(
                            self.pipe, "pipeline shutdown", timeout_secs=1.5
                        )

                    if null_result in (
                        Gst.StateChangeReturn.SUCCESS,
                        Gst.StateChangeReturn.NO_PREROLL,
                    ):
                        printc("   └─ ✅ Pipeline cleaned up successfully", "0F0")
                    else:
                        printwarn("Pipeline didn't reach NULL state cleanly")
                except Exception as e:
                    printwarn(f"Error cleaning up pipeline: {e}")
                    # Force cleanup even if state change failed
                    try:
                        self.pipe.set_state(Gst.State.NULL)
                    except Exception:
                        pass
                finally:
                    # Always clear the pipeline reference to prevent reuse
                    self.pipe = None
            
            # Close websocket connection with timeout
            if self.conn:
                try:
                    await asyncio.wait_for(self.conn.close(), timeout=2.0)
                    self.conn = None
                except (asyncio.TimeoutError, Exception) as e:
                    printwarn(f"Error closing websocket: {e}")
                    self.conn = None

            if self._room_join_gpio_ready and self._room_join_gpio and self.join_gpio_pin is not None:
                try:
                    inactive_state = self._join_gpio_inactive_state(self._room_join_gpio)
                    self._room_join_gpio.output(self.join_gpio_pin, inactive_state)
                except Exception:
                    pass

    async def loop(self):
        assert self.conn
        printc("✅ WebSocket ready", "0F0")
        
        # Check for shutdown periodically
        while not self._shutdown_requested:
            try:
                # Wait for message with timeout to check shutdown flag
                message = await asyncio.wait_for(self.conn.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                # Check shutdown flag periodically
                continue
            except websockets.exceptions.ConnectionClosed:
                break
                
            try:
                msg = json.loads(message)
                if 'from' in msg:
                    if self.puuid==None:
                        self.puuid = str(random.randint(10000000,99999999999))
                    if msg['from'] == self.puuid:
                        continue
                    UUID = msg['from']
                    if ('UUID' in msg) and (msg['UUID'] != self.puuid):
                        continue
                elif 'UUID' in msg:
                    if (self.puuid != None) and (self.puuid != msg['UUID']):
                        print("PUUID NOT  SAME")
                        continue
                    UUID = msg['UUID']
                else:
                    if self.room_name:
                        if 'request' in msg:
                            if msg['request'] == 'listing':
                                # Handle room listing
                                if 'list' in msg:
                                    await self.handle_room_listing(msg['list'])
                                
                                if self.room_recording:
                                    # In room recording mode, we'll connect to streams after processing the list
                                    if not msg.get('list'):
                                        printc("Warning: Room recording requires a server that provides room listings", "F77")
                                        printc("Custom websocket servers may not support this feature", "F77")
                                elif self.streamin:
                                    printwout("play stream")
                                    await self.sendMessageAsync({"request":"play","streamID":self.streamin+self.hashcode})
                                else:
                                    printwout("seed start")
                                    await self.sendMessageAsync({"request":"seed","streamID":self.stream_id+self.hashcode})
                        continue
                    else:
                        # For other requests without UUID, we might need to handle them
                        # especially for room recording mode (only if not using subprocess architecture)
                        if self.room_recording and not self.subprocess_managers:
                            await self._handle_room_message(msg)
                    continue

                if UUID not in self.clients:
                    self.clients[UUID] = {}
                    self.clients[UUID]["UUID"] = UUID
                    self.clients[UUID]["session"] = None
                    self.clients[UUID]["send_channel"] = None
                    self.clients[UUID]["timer"] = None
                    self.clients[UUID]["ping"] = 0
                    self.clients[UUID]["webrtc"] = None
                    self.clients[UUID]["direction"] = "receive" if self.view else "send"

                if 'session' in msg:
                    if not self.clients[UUID]['session']:
                        self.clients[UUID]['session'] = msg['session']
                        # In room recording mode, update session mapping
                        if self.room_recording and msg['session']:
                            # Check if this session should be mapped to a stream
                            for stream_id in self.subprocess_managers.keys():
                                if self.stream_id_to_uuid.get(stream_id) == UUID:
                                    self.session_to_stream[msg['session']] = stream_id
                                    printc(f"[Room Recording] Mapped session {msg['session']} to stream {stream_id} (from client session update)", "77F")
                                    break
                    elif self.clients[UUID]['session'] != msg['session']:
                        # In room recording mode, different streams may have different sessions
                        if self.room_recording:
                            # Accept different sessions for different streams
                            print(f"New session for room recording: {msg['session']}")
                            # Create a new UUID entry for this session to avoid conflicts
                            new_uuid = f"{UUID}_{msg['session']}"
                            if new_uuid not in self.clients:
                                self.clients[new_uuid] = {
                                    "UUID": new_uuid,
                                    "session": msg['session'],
                                    "send_channel": None,
                                    "timer": None,
                                    "ping": 0,
                                    "webrtc": None,
                                    "direction": "receive" if self.view else "send",
                                    "original_uuid": UUID
                                }
                            UUID = new_uuid  # Use the new UUID for this session
                        else:
                            print("sessions don't match")
                            continue

                # Handle room recording messages (only if not using subprocess architecture)
                if self.room_recording and not self.subprocess_managers:
                    handled = await self._handle_room_message(msg)
                    if handled:
                        continue
                
                if 'description' in msg:
                    # Description (SDP Offer/Answer) received from WebSocket
                    if 'vector' in msg:
                        decrypted_json = decrypt_message(msg['description'], msg['vector'], self.password + self.salt)
                        sdp_data = json.loads(decrypted_json)
                    else:
                        sdp_data = msg['description']

                    if sdp_data.get('type') == "offer":
                        # This is an offer from a new peer wanting to send video to us.
                        if self.room_recording:
                            # In room recording mode, this offer is for a stream we requested.
                            # We need to route it to the correct subprocess.
                            stream_id = self.uuid_to_stream_id.get(UUID)
                            # Get session ID from message or from client data
                            session_id = msg.get('session') or self.clients.get(UUID, {}).get('session')

                            if stream_id and stream_id in self.subprocess_managers:
                                printc(f"[Subprocess] Routing offer for UUID {UUID} to stream {stream_id} (session: {session_id})", "0F0")
                                await self.handle_subprocess_offer(stream_id, sdp_data['sdp'], session_id)
                                continue # Message handled, skip further processing
                            else:
                                printc(f"[Subprocess] ⚠️ Received offer from UUID {UUID}, but no stream mapping found.", "F70")

                        elif self.single_stream_recording:
                            # Single-stream recording mode - use subprocess
                            printc("📥 Incoming connection offer (subprocess recording)", "0FF")
                            
                            # Create subprocess for recording
                            stream_id = self.record  # Use the record parameter as stream ID
                            config = {
                                'mode': 'record',
                                'stream_id': stream_id,
                                'room': None,  # No room for single stream
                                'record_file': self.record,
                                'record_audio': not self.noaudio,
                                'use_hls': self.use_hls,
                                'use_splitmuxsink': self.use_splitmux,
                                'password': self.password if self.password else None,
                                'salt': self.salt if self.salt else ''
                            }
                            
                            # Create and start subprocess
                            await self.create_recording_subprocess(stream_id, UUID)
                            
                            # Map UUID to stream for routing
                            self.uuid_to_stream_id[UUID] = stream_id
                            self.stream_id_to_uuid[stream_id] = UUID
                            
                            # Route the offer to subprocess
                            if stream_id in self.subprocess_managers:
                                printc(f"[Subprocess] Routing offer to recording subprocess for {stream_id}", "0F0")
                                await self.handle_subprocess_sdp(stream_id, sdp_data)
                                
                        elif self.streamin:
                            # Standard viewer mode
                            printc("📥 Incoming connection offer", "0FF")
                            await self.start_pipeline(UUID)
                            self.handle_offer(sdp_data, UUID)

                        else:
                            printc("We don't support two-way video calling yet. ignoring remote offer.", "399")
                            continue

                    elif sdp_data.get('type') == "answer":
                        # This is an answer to our offer (when we are publishing).
                        printc("🤝 Connection accepted", "0F0")
                        self.handle_sdp_ice(sdp_data, UUID)
                elif 'candidates' in msg or 'candidate' in msg:
                    # Processing ICE candidates (single or bundled)
                    if 'vector' in msg:
                        key = 'candidates' if 'candidates' in msg else 'candidate'
                        decrypted_json = decrypt_message(msg[key], msg['vector'], self.password + self.salt)
                        candidates = json.loads(decrypted_json)
                    else:
                        candidates = msg.get('candidates') or [msg]
                    
                    if not isinstance(candidates, list):
                        candidates = [candidates]

                    if self.room_recording or self.single_stream_recording:
                        stream_id = self.uuid_to_stream_id.get(UUID)
                        if stream_id and stream_id in self.subprocess_managers:
                            # Route to the correct subprocess
                            printc(f"[Subprocess] Routing {len(candidates)} ICE candidate(s) for UUID {UUID} to stream {stream_id}", "77F")
                            for ice in candidates:
                                await self.handle_subprocess_ice(stream_id, ice)
                            continue # Message handled
                        else:
                            printc(f"[Subprocess] ⚠️ Received ICE from UUID {UUID}, but no stream mapping found.", "F70")

                    # Fallback to legacy/single-stream handling
                    for ice in candidates:
                        self.handle_sdp_ice(ice, UUID)
                elif 'request' in msg:
                    if msg['request'] not in ['play', 'offerSDP', 'cleanup', 'bye', 'videoaddedtoroom']:
                        printc(f"📨 Request: {msg['request']}", "77F")
                    if 'offerSDP' in  msg['request']:
                        if not self.single_stream_recording:  # Skip for subprocess recording
                            await self.start_pipeline(UUID)
                    elif msg['request'] == 'cleanup' or msg['request'] == 'bye':
                        # Handle cleanup for recording
                        if (self.room_recording or self.room_ndi or self.room_monitor) and UUID in self.room_streams:
                            await self.cleanup_room_stream(UUID)
                        elif self.single_stream_recording and UUID in self.uuid_to_stream_id:
                            # Clean up single-stream recording subprocess
                            stream_id = self.uuid_to_stream_id[UUID]
                            printc(f"🧹 Cleaning up single-stream recording for {stream_id}", "F77")
                            if stream_id in self.subprocess_managers:
                                manager = self.subprocess_managers[stream_id]
                                await manager.stop()
                                del self.subprocess_managers[stream_id]
                            if UUID in self.uuid_to_stream_id:
                                del self.uuid_to_stream_id[UUID]
                            if stream_id in self.stream_id_to_uuid:
                                del self.stream_id_to_uuid[stream_id]
                    elif msg['request'] == "play":
                        # Play request received
                        if 'streamID' in msg:
                            if msg['streamID'] == self.stream_id+self.hashcode:
                                if not self.single_stream_recording:  # Skip for subprocess recording
                                    await self.start_pipeline(UUID)
                    elif msg['request'] == "videoaddedtoroom":
                        if 'streamID' in msg:
                            printc(f"📹 Video added to room: {msg['streamID']}", "0FF")
                            if self.room_recording or self.room_ndi or self.room_monitor:
                                # This event tells us a new stream is in the room.
                                # Try to get the UUID from various possible fields
                                peer_uuid = msg.get('from') or msg.get('UUID') or UUID
                                if peer_uuid:
                                    printc(f"  UUID found: {peer_uuid}", "77F")
                                    await self.handle_new_room_stream(msg['streamID'], peer_uuid, source="videoaddedtoroom")
                                else:
                                    printc(f"[{msg['streamID']}] ⚠️ videoaddedtoroom event missing peer UUID", "F70")
                                    printc(f"  Message keys: {list(msg.keys())}", "F77")
                            elif self.streamin:
                                printwout("play stream.")
                                await self.sendMessageAsync({"request":"play","streamID":self.streamin+self.hashcode})
                    elif msg['request'] == 'joinroom':
                        if self.room_recording or self.room_ndi or self.room_monitor:
                            # Handle new member joining in room-monitor/room-record/room-ndi modes
                            if 'streamID' in msg:
                                printc(f"👤 Member joined room with stream: {msg['streamID']}", "0FF")
                                peer_uuid = msg.get('from') or msg.get('UUID') or UUID
                                await self.handle_new_room_stream(msg['streamID'], peer_uuid, source="joinroom")
                        elif self.streamin and self.streamID and (self.streamin+self.hashcode == self.streamID):
                            if self.room_hashcode:
                                printwout("play stream..")
                                await self.sendMessageAsync({"request":"play","streamID":self.streamin+self.hashcode,"roomid":self.room_hashcode, "UUID":UUID})
                            elif self.room_name:
                                printwout("play stream...")
                                await self.sendMessageAsync({"request":"play","streamID":self.streamin+self.hashcode,"roomid":self.room_name, "UUID":UUID})
                        else:
                            printwout("seed start")
                            await self.sendMessageAsync({"request":"seed", "streamID":self.stream_id+self.hashcode, "UUID":UUID})
                    elif msg['request'] == 'someonejoined':
                        # Handle someone joining the room
                        if (self.room_recording or self.room_ndi or self.room_monitor) and 'streamID' in msg:
                            printc(f"🆕 Someone joined with stream: {msg['streamID']}", "0FF")
                            peer_uuid = msg.get('from') or msg.get('UUID') or UUID
                            await self.handle_new_room_stream(msg['streamID'], peer_uuid, source="someonejoined")
                            
                            
            except KeyboardInterrupt:
                printc("\n👋 Shutting down gracefully...", "0FF")
                break

            except websockets.ConnectionClosed:
                printc("⚠️  WebSocket connection lost - reconnecting in 5s...", "F77")
                # WebSocket closed - exit the message loop but keep peer connections
                await asyncio.sleep(5)
                break
            except Exception as E:
                printwarn(get_exception_info(E))


        return 0
    
    async def handle_room_listing(self, room_list):
        """Handle the initial room listing when joining"""
        if not room_list:
            printc("Warning: Empty room list received. Room recording may not work properly.", "F77")
            if self.puuid:
                printc("This appears to be a custom websocket server that doesn't provide room listings.", "F77")
            return
            
        printc(f"Room has {len(room_list)} members", "7F7")
        
        # Print raw room list for debugging
        import json
        printc(f"Raw room list: {json.dumps(room_list, indent=2)}", "77F")
        
        # Debug: print room members
        for i, member in enumerate(room_list):
            if isinstance(member, dict):
                uuid = member.get('UUID', 'no-uuid')
                stream_id = member.get('streamID', 'no-streamid')
                # Show members with streamIDs in green, others in yellow
                if 'streamID' in member:
                    printc(f"  - Member {i}: UUID={uuid}, streamID={stream_id} ✓", "0F0")
                else:
                    printc(f"  - Member {i}: UUID={uuid}, streamID={stream_id} (not publishing)", "FF0")
                # Show all keys for debugging non-publishing members
                if not 'streamID' in member:
                    printc(f"    Keys: {list(member.keys())}", "F77")
            else:
                printc(f"  - Member {i}: Not a dict: {type(member)}", "F00")
        
        # In room recording mode, we need to handle this differently
        printc(
            f"Room recording mode: {self.room_recording}, Room NDI: {self.room_ndi}, Room monitor: {self.room_monitor}",
            "FF0",
        )
        if self.room_recording or self.room_ndi:
            printc("🚀 Room recording mode - will record all streams", "0F0")
            
            # Start ICE processor if not running
            if not self.ice_processor_task:
                # Store event loop reference
                try:
                    self.event_loop = asyncio.get_running_loop()
                except RuntimeError:
                    self.event_loop = None
                    
                if self.event_loop:
                    self.ice_processor_task = asyncio.create_task(self._process_ice_candidates())
            
            # Add streams to record
            streams_to_record = []
            for member in room_list:
                if 'streamID' in member:
                    stream_id = member['streamID']
                    uuid = member.get('UUID')  # Get UUID if available
                    
                    # Apply filter if configured
                    if self.stream_filter and stream_id not in self.stream_filter:
                        continue
                        
                    streams_to_record.append((stream_id, uuid))
                    
            printc(f"Found {len(streams_to_record)} streams to record", "7FF")
            
            # Start recording each stream using subprocess architecture
            for stream_id, uuid in streams_to_record:
                await self.create_subprocess_recorder(stream_id, uuid)
        elif self.room_monitor:
            printc("👀 Room monitor mode - tracking room join/leave events", "0AF")
            tracked = 0
            async with self.room_streams_lock:
                for member in room_list:
                    if 'streamID' not in member:
                        continue
                    stream_id = member['streamID']
                    uuid = member.get('UUID') or f"room_member_{stream_id}"

                    if stream_id in [s['streamID'] for s in self.room_streams.values()]:
                        continue
                    self.room_streams[uuid] = {'streamID': stream_id, 'recording': False}
                    tracked += 1

            printc(f"Room monitor primed with {tracked} currently active stream(s)", "77F")
        else:
            # Original single-stream handling
            for member in room_list:
                if 'UUID' in member and 'streamID' in member:
                    stream_id = member['streamID']
                    uuid = member['UUID']
                    
                    # Check if we should record this stream
                    if self.stream_filter and stream_id not in self.stream_filter:
                        continue
                        
                    # Track this stream (thread-safe)
                    async with self.room_streams_lock:
                        # Check if stream already exists
                        existing_stream = False
                        for existing_uuid, stream_info in self.room_streams.items():
                            if stream_info.get('streamID') == stream_id:
                                printc(f"⚠️  Stream {stream_id} already tracked (uuid: {existing_uuid})", "FF0")
                                existing_stream = True
                                break
                        
                        if not existing_stream:
                            self.room_streams[uuid] = {
                                'streamID': stream_id,
                                'recording': False,
                                'stats': {}
                            }
                    
                    # For non-room-recording mode, just play the first stream
                    if self.streamin and not self.room_recording:
                        printc(f"Found stream to play: {stream_id}", "7FF")
                        await self.sendMessageAsync({
                            "request": "play",
                            "streamID": stream_id
                        })
                        break
    
    async def create_isolated_connection(self, stream_id, stream_uuid):
        """Create an isolated WebRTC connection for a specific stream in room recording mode"""
        printc(f"Creating isolated connection for stream: {stream_id}", "7FF")
        
        # For now, we'll request each stream sequentially
        # In a future enhancement, we could spawn separate WebRTC instances
        await self.sendMessageAsync({
            "request": "play",
            "streamID": stream_id
        })
        
        # Mark this stream as pending connection
        async with self.room_streams_lock:
            if stream_uuid in self.room_streams:
                self.room_streams[stream_uuid]['connection_requested'] = True
    
    async def create_subprocess_recorder(self, stream_id, uuid=None):
        """Create a subprocess recorder for a stream. The UUID is the key for routing."""
        if stream_id in self.subprocess_managers:
            printc(f"[{stream_id}] Subprocess manager already exists.", "FF0")
            return

        printc(f"\n📹 Creating subprocess recorder for stream: {stream_id}", "0F0")
        
        # This mapping is crucial. It links the peer's UUID from the websocket
        # to the stream we are about to request. When the peer sends its offer,
        # we'll know which subprocess to route it to.
        if uuid:
             self.uuid_to_stream_id[uuid] = stream_id
             self.stream_id_to_uuid[stream_id] = uuid  # Add reverse mapping
             printc(f"[Subprocess] Mapping UUID {uuid} to stream {stream_id}", "77F")
             
             # Also map the stream ID without hash suffix for encrypted messages
             # Stream IDs in encrypted messages often come without the hash suffix
             if len(stream_id) > 8:  # Likely has a hash suffix
                 base_stream_id = stream_id[:-6] if len(stream_id) > 12 else stream_id[:8]
                 self.stream_id_to_uuid[base_stream_id] = uuid
                 printc(f"[Subprocess] Also mapping base stream ID {base_stream_id} to UUID {uuid}", "77F")
        
        default_turn = self._get_default_turn_server()
        if default_turn:
            turn_info = default_turn
            turn_url = turn_info['url']
            if '@' not in turn_url and turn_url.startswith('turn'):
                if turn_url.startswith('turns:'):
                    protocol = 'turns://'
                    server_part = turn_url[6:]  # Skip "turns:"
                else:
                    protocol = 'turn://'
                    server_part = turn_url[5:]  # Skip "turn:"
                default_turn_url = f"{protocol}{turn_info['user']}:{turn_info['pass']}@{server_part}"
            else:
                default_turn_url = turn_url
            printc(f"[{stream_id}] Using default TURN server for subprocess.", "77F")
        else:
            default_turn_url = None

        config = {
            'mode': 'view',
            'stream_id': stream_id,
            'room': self.record,  # Room name prefix for files
            'record_file': f"{self.record}_{stream_id}_{int(time.time())}.webm",
            'stun_server': self.stun_server or 'stun://stun.cloudflare.com:3478',
            'turn_server': self.turn_server or default_turn_url,
            'ice_transport_policy': self.ice_transport_policy,
            'record_audio': True if not self.noaudio else False,  # Default to recording audio unless --noaudio is set
            'use_mkv': False,  # Don't use MKV subprocess for now as it has issues
            'use_hls': self.use_hls if hasattr(self, 'use_hls') else False,  # Use HLS recording
            'use_splitmuxsink': self.use_splitmux if hasattr(self, 'use_splitmux') else False,  # Use splitmuxsink
            'mux_format': getattr(self, 'mux_format', 'webm'),  # Default to webm
            'test_mode': getattr(self, 'test_mode', False),  # Enable test mode
            'room_ndi': self.room_ndi,  # Pass NDI mode flag
            'ndi_direct': self.ndi_direct if hasattr(self, 'ndi_direct') else True,  # Default to direct mode
            'ndi_name': f"{self.room_name}_{stream_id}" if self.room_ndi else None,  # NDI stream name
            'password': self.password,  # Pass password for decryption
            'salt': self.salt,  # Pass salt for decryption
        }
        printc(f"[{stream_id}] DEBUG: Creating subprocess with record_audio={True if not self.noaudio else False} (noaudio={self.noaudio})", "77F")
        if self.password:
            printc(f"[{stream_id}] DEBUG: Password will be passed to subprocess (length: {len(self.password)})", "77F")
        if self.use_hls:
            printc(f"[{stream_id}] Using HLS recording format (audio+video muxing)", "0FF")

        manager = WebRTCSubprocessManager(stream_id, config)
        manager.on_message('sdp', lambda msg: asyncio.create_task(self.send_subprocess_sdp(stream_id, msg)))
        manager.on_message('ice', lambda msg: asyncio.create_task(self.send_subprocess_ice(stream_id, msg)))
        manager.on_message('connection_state', lambda msg: printc(f"[{stream_id}] State: {msg.get('state', 'N/A')}", "77F"))
        manager.on_message('ice_state', lambda msg: printc(f"[{stream_id}] ICE: {msg.get('state', 'N/A')}", "77F"))
        
        if await manager.start():
            self.subprocess_managers[stream_id] = manager
            # Immediately request to play the stream.
            # The server will then connect us to the peer, which will send an offer.
            # The 'uuid' parameter here is the websocket 'from' field of the peer we want to connect to.
            play_request = {"request": "play", "streamID": stream_id}
            if uuid:
                play_request["UUID"] = uuid
            
            await self.sendMessageAsync(play_request)
            printc(f"[{stream_id}] Subprocess started. Sent play request for UUID {uuid or 'any'}.", "0F0")
        else:
            printc(f"[{stream_id}] ❌ Failed to start subprocess.", "F00")
            if uuid and uuid in self.uuid_to_stream_id:
                del self.uuid_to_stream_id[uuid] # Clean up failed mapping
                if stream_id in self.stream_id_to_uuid:
                    del self.stream_id_to_uuid[stream_id] # Clean up reverse mapping
            
    async def send_subprocess_sdp(self, stream_id, msg):
        """Send SDP (answer) from a subprocess back to the WebSocket peer."""
        sdp_type = msg.get('sdp_type')
        sdp = msg.get('sdp')
        session_id = msg.get('session_id')
        
        uuid = None
        for u, sid in self.uuid_to_stream_id.items():
            if sid == stream_id:
                uuid = u
                break

        if not uuid:
            printc(f"[{stream_id}] ❌ Cannot send SDP answer. No UUID mapping found.", "F00")
            return

        if sdp_type == 'answer':
            printc(f"[{stream_id}] Sending SDP answer back to peer {uuid} (session: {session_id})", "0F0")
            # Include session at root level for VDO.Ninja compatibility
            message = {
                "description": {"type": "answer", "sdp": sdp},
                "UUID": uuid
            }
            if session_id:
                message["session"] = session_id
                printc(f"[{stream_id}] Answer message includes session: {session_id}", "77F")
            else:
                printc(f"[{stream_id}] WARNING: No session ID for answer!", "F70")
            await self.sendMessageAsync(message)
            
    async def send_subprocess_ice(self, stream_id, msg):
        """Send an ICE candidate from a subprocess back to the WebSocket peer."""
        candidate = msg.get('candidate')
        sdp_m_line_index = msg.get('sdpMLineIndex', 0)
        session_id = msg.get('session_id')
        
        uuid = None
        for u, sid in self.uuid_to_stream_id.items():
            if sid == stream_id:
                uuid = u
                break
        
        if not uuid:
            printc(f"[{stream_id}] ❌ Cannot send ICE. No UUID mapping found.", "F00")
            return

        #printc(f"[{stream_id}] Sending ICE candidate to peer {uuid}", "77F")
        await self.sendMessageAsync({
            "candidates": [{
                "candidate": candidate,
                "sdpMLineIndex": sdp_m_line_index
            }],
            "UUID": uuid,
            "session": session_id,
            "type": "remote" # This might need to be 'local' depending on server expectation
        })
        
    async def handle_subprocess_offer(self, stream_id, offer_sdp, session_id):
        """Forward offer to subprocess"""
        manager = self.subprocess_managers.get(stream_id)
        if not manager:
            printc(f"[{stream_id}] No subprocess manager found", "F00")
            return
            
        # Store session ID
        manager.session_id = session_id
        
        # Send offer to subprocess
        await manager.send_message({
            "type": "sdp",
            "sdp_type": "offer",
            "sdp": offer_sdp,
            "session_id": session_id
        })
        
    async def handle_subprocess_ice(self, stream_id, candidate_data):
        """Forward ICE candidate to subprocess"""
        manager = self.subprocess_managers.get(stream_id)
        if not manager:
            return
            
        await manager.send_message({
            "type": "ice",
            "candidate": candidate_data.get('candidate'),
            "sdpMLineIndex": candidate_data.get('sdpMLineIndex', 0)
        })
        
    async def cleanup_subprocess_managers(self):
        """Stop all subprocess managers"""
        for stream_id, manager in self.subprocess_managers.items():
            printc(f"Stopping subprocess: {stream_id}", "77F")
            await manager.stop()
        self.subprocess_managers.clear()
    
    async def handle_new_room_stream(self, stream_id, uuid, source="event"):
        """Handle a new stream that has joined the room by starting a recorder for it."""
        if self.stream_filter and stream_id not in self.stream_filter:
            return # Skip streams not in our filter
        
        # The 'uuid' here is the websocket peer ID of the new member. This is crucial.
        if not uuid:
            printc(f"[{stream_id}] ⚠️ New stream joined but had no UUID. Cannot record.", "F70")
            return

        printc(f"New peer '{uuid}' with stream '{stream_id}' joined room via {source}.", "7FF")
        
        async with self.room_streams_lock:
            if stream_id in [s['streamID'] for s in self.room_streams.values()]:
                 printc(f"[{stream_id}] ⚠️ Already tracking this stream. Ignoring.", "FF0")
                 return
            self.room_streams[uuid] = {'streamID': stream_id, 'recording': False}

        if self.room_join_notifications_enabled:
            self._queue_background_task(
                self._dispatch_room_join_notifications(stream_id, uuid, source),
                f"room join notify {stream_id}",
            )

        if self.room_recording or self.room_ndi:
            await self.create_subprocess_recorder(stream_id, uuid)
    
    def on_new_stream_room(self, client, pad):
        """Handle new stream pad for room recording"""
        try:
            caps = pad.get_current_caps()
            if not caps:
                printc(f"No caps available for pad yet", "F77")
                return
            name = caps.get_structure(0).get_name()
            print(f"New stream pad for {client.get('streamID', 'unknown')}: {name}")
            
            if self.room_ndi:
                # Setup NDI output for this stream
                self.setup_room_ndi(client, pad, name)
            elif "video" in name:
                self.setup_room_video_recording(client, pad, name)
            elif "audio" in name:
                if not self.noaudio:
                    self.setup_room_audio_recording(client, pad, name)
        except Exception as e:
            printc(f"Error handling new stream pad: {e}", "F00")
            import traceback
            traceback.print_exc()
    
    def setup_room_video_recording(self, client, pad, name):
        """Setup video recording pipeline for a room stream"""
        stream_id = client['streamID']
        timestamp = str(int(time.time()))
        
        # Create recording pipeline without transcoding
        if "h264" in name.lower():
            # Direct mux H264 to MPEG-TS
            # Add counter to prevent file collisions
            filename = f"{self.room_name}_{stream_id}_{timestamp}_{client['UUID'][:8]}.ts"
            pipeline_str = (
                f"queue ! rtph264depay ! h264parse ! "
                f"mpegtsmux name=mux_{client['UUID']} ! "
                f"filesink location={filename}"
            )
            printc(f"Recording H264 video to: {filename}", "7F7")
        elif "vp8" in name.lower():
            # Direct mux VP8 to MPEG-TS
            # Add counter to prevent file collisions
            filename = f"{self.room_name}_{stream_id}_{timestamp}_{client['UUID'][:8]}.ts"
            pipeline_str = (
                f"queue ! rtpvp8depay ! "
                f"mpegtsmux name=mux_{client['UUID']} ! "
                f"filesink location={filename}"
            )
            printc(f"Recording VP8 video to: {filename}", "7F7")
        else:
            printc(f"Unknown video codec: {name}", "F00")
            return
            
        out = Gst.parse_bin_from_description(pipeline_str, True)
        self.pipe.add(out)
        out.sync_state_with_parent()
        sink = out.get_static_pad('sink')
        pad.link(sink)
        
        client['video_recording'] = True
        # Update room stream status (no async context in sync function)
        # This is OK since GStreamer callbacks are serialized
        if client['UUID'] in self.room_streams:
            self.room_streams[client['UUID']]['recording'] = True
        printc(f"Recording video for stream {stream_id}", "7F7")
    
    def setup_room_audio_recording(self, client, pad, name):
        """Setup audio recording pipeline for a room stream"""
        if "OPUS" in name:
            # Check if we already have a mux for this client
            mux_name = f"mux_{client['UUID']}"
            mux = self.pipe.get_by_name(mux_name)
            
            if mux:
                # Add audio to existing mux
                pipeline_str = "queue ! rtpopusdepay ! opusparse ! audio/x-opus,channel-mapping-family=0,rate=48000"
                out = Gst.parse_bin_from_description(pipeline_str, True)
                self.pipe.add(out)
                out.sync_state_with_parent()
                
                # Get source pad from the audio pipeline
                src_pad = out.get_static_pad('src')
                # Get audio sink pad from mux
                audio_pad = mux.get_request_pad('sink_%d')
                if audio_pad:
                    src_pad.link(audio_pad)
                    # Link incoming pad to our pipeline
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                else:
                    printc(f"Failed to get audio pad from mux for stream {client['streamID']}", "F00")
                    return
                printc(f"Added audio to recording for stream {client['streamID']}", "7F7")
            else:
                # Create standalone audio recording
                stream_id = client['streamID']
                timestamp = str(int(time.time()))
                # Add UUID to prevent file collisions
                filename = f"{self.room_name}_{stream_id}_{timestamp}_{client['UUID'][:8]}_audio.ts"
                pipeline_str = (
                    f"queue ! rtpopusdepay ! opusparse ! audio/x-opus,channel-mapping-family=0,rate=48000 ! "
                    f"mpegtsmux ! filesink location={filename}"
                )
                out = Gst.parse_bin_from_description(pipeline_str, True)
                self.pipe.add(out)
                out.sync_state_with_parent()
                sink = out.get_static_pad('sink')
                pad.link(sink)
                printc(f"Recording audio only for stream {client['streamID']}", "7F7")
    
    def setup_room_ndi(self, client, pad, name):
        """Setup NDI output for a room stream"""
        stream_id = client['streamID']
        
        # Check if we should use direct mode (default) or combiner mode
        use_direct_ndi = not (hasattr(self.args, 'ndi_combine') and self.args.ndi_combine)
        
        if use_direct_ndi:
            # Direct NDI mode - separate audio/video sinks
            if "video" in name:
                ndi_element_name = f"ndi_video_sink_{client['UUID']}"
                ndi_stream_suffix = "_video"
            else:  # audio
                ndi_element_name = f"ndi_audio_sink_{client['UUID']}"
                ndi_stream_suffix = "_audio"
                
            ndi_name = f"{self.room_name}_{stream_id}{ndi_stream_suffix}"
            
            # Check if NDI sink already exists
            ndi_sink = self.pipe.get_by_name(ndi_element_name)
            if not ndi_sink:
                ndi_sink = Gst.ElementFactory.make("ndisink", ndi_element_name)
                if not ndi_sink:
                    print("Failed to create ndisink element")
                    print("Make sure gst-plugin-ndi is installed")
                    return
                
                ndi_sink.set_property("ndi-name", ndi_name)
                self.pipe.add(ndi_sink)
                ndi_sink.sync_state_with_parent()
                printc(f"Created NDI output: {ndi_name}", "7F7")
        else:
            # Combiner mode - use ndisinkcombiner (has freezing issues)
            ndi_name = f"{self.room_name}_{stream_id}"
            ndi_combiner_name = f"ndi_combiner_{client['UUID']}"
            ndi_sink_name = f"ndi_sink_{client['UUID']}"
            
            if "video" in name:
                # Create NDI sink combiner for this client if not exists
                ndi_combiner = self.pipe.get_by_name(ndi_combiner_name)
                
                if not ndi_combiner:
                    ndi_combiner = Gst.ElementFactory.make("ndisinkcombiner", ndi_combiner_name)
                    if not ndi_combiner:
                        print("Failed to create ndisinkcombiner element")
                        return
                    
                    # Create NDI sink for this stream
                    ndi_sink = Gst.ElementFactory.make("ndisink", ndi_sink_name)
                    if not ndi_sink:
                        print("Failed to create ndisink element")
                        return
                    
                    ndi_sink.set_property("ndi-name", ndi_name)
                    
                    self.pipe.add(ndi_combiner)
                    self.pipe.add(ndi_sink)
                    
                    ndi_combiner.link(ndi_sink)
                    ndi_combiner.sync_state_with_parent()
                    ndi_sink.sync_state_with_parent()
                    
                    client['ndi_combiner'] = ndi_combiner
                    client['ndi_sink'] = ndi_sink
                    printc(f"Created NDI output (combiner): {ndi_name}", "7F7")
        
        # Process video
        if "video" in name:
            # Detect video codec
            if "H264" in name:
                pipeline_str = "queue ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! videoscale ! videorate ! capsfilter name=vcaps"
            elif "VP8" in name:
                pipeline_str = "queue ! rtpvp8depay ! vp8dec ! videoconvert ! videoscale ! videorate ! capsfilter name=vcaps"
            elif "VP9" in name:
                pipeline_str = "queue ! rtpvp9depay ! vp9dec ! videoconvert ! videoscale ! videorate ! capsfilter name=vcaps"
            else:
                printc(f"Unknown video codec for NDI: {name}", "F00")
                return
            
            out = Gst.parse_bin_from_description(pipeline_str, True)
            self.pipe.add(out)
            
            # Set caps for NDI optimal format
            vcaps = out.get_by_name("vcaps")
            if vcaps:
                vcaps.set_property("caps", Gst.Caps.from_string("video/x-raw,format=UYVY,framerate=30/1"))
            
            out.sync_state_with_parent()
            
            # Link to appropriate sink
            if use_direct_ndi:
                # Direct link to NDI sink
                out.link(ndi_sink)
            else:
                # Link to combiner
                ndi_combiner = self.pipe.get_by_name(ndi_combiner_name)
                if ndi_combiner:
                    ndi_pad = ndi_combiner.get_request_pad("video")
                    if ndi_pad:
                        ghost_src = out.get_static_pad("src")
                        ghost_src.link(ndi_pad)
            
            sink = out.get_static_pad('sink')
            pad.link(sink)
            
        elif "audio" in name and not self.noaudio:
            # Process audio
            if "OPUS" in name:
                pipeline_str = "queue ! rtpopusdepay ! opusdec ! audioconvert ! audioresample ! capsfilter name=acaps"
            else:
                printc(f"Unknown audio codec for NDI: {name}", "F00")
                return
            
            out = Gst.parse_bin_from_description(pipeline_str, True)
            self.pipe.add(out)
            
            # Set caps for NDI optimal format
            acaps = out.get_by_name("acaps")
            if acaps:
                acaps.set_property("caps", Gst.Caps.from_string("audio/x-raw,format=F32LE,channels=2,rate=48000,layout=interleaved"))
            
            out.sync_state_with_parent()
            
            # Link to appropriate sink
            if use_direct_ndi:
                # Direct link to NDI sink
                out.link(ndi_sink)
            else:
                # Link to combiner
                ndi_combiner = self.pipe.get_by_name(ndi_combiner_name)
                if ndi_combiner:
                    ndi_pad = ndi_combiner.get_request_pad("audio")
                    if ndi_pad:
                        ghost_src = out.get_static_pad("src")
                        ghost_src.link(ndi_pad)
            
            sink = out.get_static_pad('sink')
            pad.link(sink)
    
    async def display_room_stats(self):
        """Periodically display stats for all room streams"""
        while True:
            await asyncio.sleep(10)  # Update every 10 seconds
            
            # Check if we're still connected
            if not hasattr(self, 'conn') or not self.conn or self.conn.closed:
                break
                
            if not self.room_recording or not self.room_recorders:
                continue
                
            print("\n" + "="*60)
            printc(f"Room Recording Status - {len(self.room_recorders)} active recorders", "7FF")
            print("="*60)
            
            for stream_id, recorder in self.room_recorders.items():
                # Determine status
                if recorder['recording']:
                    duration = int(time.time() - recorder['start_time'])
                    status = f"Recording ({duration}s)"
                    
                    # Get file size if available
                    if recorder.get('recording_file') and os.path.exists(recorder['recording_file']):
                        size = os.path.getsize(recorder['recording_file'])
                        status += f" - {size:,} bytes"
                else:
                    status = "Connecting..."
                
                # Show connection state
                if recorder.get('webrtc'):
                    conn_state = recorder['webrtc'].get_property('connection-state')
                    ice_state = recorder['webrtc'].get_property('ice-connection-state')
                    if conn_state == GstWebRTC.WebRTCPeerConnectionState.CONNECTED:
                        if not recorder['recording']:
                            status = "Connected (waiting for video)"
                    else:
                        status += f" [{conn_state.value_name}]"
                
                print(f"  {stream_id}: {status}")
            
            print("="*60 + "\n")
    
    def set_encoder_bitrate(self, client, bitrate):
        """Set bitrate for various encoder types with proper error handling
        
        Args:
            client: The client dictionary containing encoder references
            bitrate: The target bitrate in kbps (kilobits per second)
        """
        try:
            # Try to re-fetch encoder elements if they're not set or are False
            if (not client.get('encoder') or client.get('encoder') is False) and \
               (not client.get('encoder1') or client.get('encoder1') is False) and \
               (not client.get('encoder2') or client.get('encoder2') is False):
                try:
                    enc = self.pipe.get_by_name('encoder')
                    if enc:
                        client['encoder'] = enc
                except:
                    pass
                try:
                    enc1 = self.pipe.get_by_name('encoder1')
                    if enc1:
                        client['encoder1'] = enc1
                except:
                    pass
                try:
                    enc2 = self.pipe.get_by_name('encoder2')
                    if enc2:
                        client['encoder2'] = enc2
                except:
                    pass
            # Check each encoder type and use the appropriate property/method
            if self.aom:
                if client['encoder']:
                    client['encoder'].set_property('target-bitrate', int(bitrate))
                else:
                    print("AOM encoder not found")
                    
            elif " mpph265enc " in self.pipeline or (client['encoder'] and hasattr(client['encoder'], 'get_name') and client['encoder'].get_name() and client['encoder'].get_name().startswith('mpph265enc')):
                # For mpph265enc, use bps instead of bitrate
                if client['encoder']:
                    client['encoder'].set_property('bps', int(bitrate*1000))
                    
            elif " mppvp8enc " in self.pipeline or (client['encoder'] and hasattr(client['encoder'], 'get_name') and client['encoder'].get_name() and client['encoder'].get_name().startswith('mppvp8enc')):
                # For mppvp8enc, use bps instead of bitrate
                if client['encoder']:
                    client['encoder'].set_property('bps', int(bitrate*1000))
                    
            elif " x265enc " in self.pipeline or (client['encoder'] and hasattr(client['encoder'], 'get_name') and client['encoder'].get_name() and client['encoder'].get_name().startswith('x265enc')):
                if client['encoder']:
                    # x265enc uses kbps
                    client['encoder'].set_property('bitrate', int(bitrate))
                    
            elif " x264enc " in self.pipeline:
                if client.get('encoder1') and client['encoder1'] is not False:
                    # x264enc uses kbps
                    client['encoder1'].set_property('bitrate', int(bitrate))
                    printc(f"Set x264enc bitrate to {bitrate} kbps", "0F0")
                else:
                    printc("x264enc detected in pipeline but encoder1 element not found", "F77")
                    
            elif client['encoder2']:
                # v4l2h264enc uses extra-controls, not direct property
                encoder_name = ""
                try:
                    if hasattr(client['encoder2'], 'get_name'):
                        encoder_name = client['encoder2'].get_name() or ""
                except:
                    pass
                    
                if "v4l2h264enc" in encoder_name or "v4l2h264enc" in self.pipeline:
                    # v4l2h264enc doesn't support dynamic bitrate changes via properties
                    # It requires setting extra-controls at creation time
                    printc("Warning: v4l2h264enc does not support dynamic bitrate changes", "F77")
                    printc(f"To change bitrate, restart with --bitrate {int(bitrate)}", "F77")
                else:
                    # Try generic bitrate property for unknown encoder2 types
                    try:
                        client['encoder2'].set_property('bitrate', int(bitrate*1000))
                    except:
                        # Try kbps if bps fails
                        client['encoder2'].set_property('bitrate', int(bitrate))
                        
            elif client['encoder']:
                # Generic encoder - try bitrate in bps first
                try:
                    client['encoder'].set_property('bitrate', int(bitrate*1000))
                except:
                    # Fallback to kbps
                    try:
                        client['encoder'].set_property('bitrate', int(bitrate))
                    except Exception as e:
                        printc(f"Failed to set bitrate on encoder: {e}", "F00")
                        
            elif client['encoder1']:
                # encoder1 typically uses kbps
                client['encoder1'].set_property('bitrate', int(bitrate))
                
            else:
                # More informative message about encoder state
                encoder_info = []
                if 'encoder' in client:
                    encoder_info.append(f"encoder={client.get('encoder', 'not found')}")
                if 'encoder1' in client:
                    encoder_info.append(f"encoder1={client.get('encoder1', 'not found')}")
                if 'encoder2' in client:
                    encoder_info.append(f"encoder2={client.get('encoder2', 'not found')}")
                
                if encoder_info:
                    printc(f"No valid encoder found to set bitrate. Encoder state: {', '.join(encoder_info)}", "F77")
                else:
                    printc("No encoder elements found in client object", "F77")
                
        except Exception as E:
            printwarn(f"Failed to set encoder bitrate: {get_exception_info(E)}")
            # Don't crash - just log the error
    
    async def cleanup_room_stream(self, uuid):
        """Clean up resources for a disconnected room stream"""
        async with self.room_streams_lock:
            if uuid not in self.room_streams:
                return
                
            stream_info = self.room_streams[uuid]
            stream_id = stream_info['streamID']
            printc(f"Cleaning up stream {stream_id}", "F77")
            
            # Remove from tracking
            del self.room_streams[uuid]
            
        # Clean up any recording pipelines
        if uuid in self.clients:
            client = self.clients[uuid]

            if self.pipe:
                # Remove any mux elements
                mux_name = f"mux_{uuid}"
                mux = self.pipe.get_by_name(mux_name)
                if mux:
                    mux.set_state(Gst.State.NULL)
                    self.pipe.remove(mux)

                # Remove any NDI elements
                if self.room_ndi:
                    ndi_combiner_name = f"ndi_combiner_{uuid}"
                    ndi_sink_name = f"ndi_sink_{uuid}"

                    ndi_combiner = self.pipe.get_by_name(ndi_combiner_name)
                    if ndi_combiner:
                        ndi_combiner.set_state(Gst.State.NULL)
                        self.pipe.remove(ndi_combiner)

                    ndi_sink = self.pipe.get_by_name(ndi_sink_name)
                    if ndi_sink:
                        ndi_sink.set_state(Gst.State.NULL)
                        self.pipe.remove(ndi_sink)

                # Close the webrtc connection
                if 'webrtc' in client and client['webrtc']:
                    client['webrtc'].set_state(Gst.State.NULL)
                    self.pipe.remove(client['webrtc'])
            elif 'webrtc' in client and client['webrtc']:
                try:
                    client['webrtc'].set_state(Gst.State.NULL)
                except Exception:
                    pass

            # Remove from clients
            del self.clients[uuid]

def check_plugins(needed, require=False):
    if isinstance(needed, str):
        needed = [needed]
    missing = list(filter(lambda p: (Gst.Registry.get().find_plugin(p) is None and not Gst.ElementFactory.find(p)), needed))
    if len(missing):
        if require:
            print('Missing gstreamer plugin/element:', missing)
        return False
    return True

def get_raspberry_pi_model():
    """Detect Raspberry Pi model. Returns model number (1,2,3,4,5) or 0 if not a Pi"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            
        # Check if it's a Raspberry Pi
        if 'Raspberry Pi' not in cpuinfo:
            return 0
            
        # Extract model information
        for line in cpuinfo.split('\n'):
            if 'Model' in line and ':' in line:
                model_info = line.split(':')[1].strip()
                if 'Raspberry Pi 5' in model_info:
                    return 5
                elif 'Raspberry Pi 4' in model_info:
                    return 4
                elif 'Raspberry Pi 3' in model_info:
                    return 3
                elif 'Raspberry Pi 2' in model_info:
                    return 2
                elif 'Raspberry Pi' in model_info:
                    return 1
                    
        # Alternative method using revision codes
        for line in cpuinfo.split('\n'):
            if line.startswith('Revision'):
                revision = line.split(':')[1].strip()
                # RPi5 revision codes start with c04170, d04170, etc
                if revision.startswith(('c04170', 'd04170')):
                    return 5
                # RPi4 revision codes
                elif revision.startswith(('a03111', 'b03111', 'c03111', 'a03112', 'b03112', 'c03112', 'd03114', 'c03114')):
                    return 4
                    
    except (IOError, FileNotFoundError):
        pass
        
    return 0

def on_message(bus: Gst.Bus, message: Gst.Message, loop):
    mtype = message.type

    if not loop:
        try:
            loop = GLib.MainLoop
        except:
            loop = GObject.MainLoop

    if mtype == Gst.MessageType.EOS:
        print("End of stream")
        loop.quit()

    elif mtype == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        
        # Check for GStreamer 1.18 jitterbuffer error
        if "on_rtpbin_new_jitterbuffer" in str(debug) and "code should not be reached" in str(err):
            printc("\n❌ KNOWN GSTREAMER 1.18 BUG DETECTED ❌", "F00")
            printc("━" * 60, "F00")
            printc("This error occurs with GStreamer 1.18 when using --framebuffer mode.", "F70")
            printc("", "")
            printc("SOLUTION:", "0F0")
            printc("1. Upgrade to GStreamer 1.20 or newer (recommended)", "0F0")
            printc("   - Ubuntu 22.04+ has GStreamer 1.20+", "07F")
            printc("   - Debian 12+ has GStreamer 1.22+", "07F")
            printc("", "")
            printc("2. Use Docker with Ubuntu 22.04 on Debian 11:", "0F0")
            printc("   docker run -it ubuntu:22.04 bash", "07F")
            printc("", "")
            printc("3. Use a different output mode instead of --framebuffer", "0F0")
            printc("   - Try --filesink or --fdsink", "07F")
            printc("━" * 60, "F00")
            printc("See: https://gitlab.freedesktop.org/gstreamer/gst-plugins-bad/-/issues/1326", "77F")
        else:
            print(err, debug)
        
        loop.quit()

    elif mtype == Gst.MessageType.WARNING:
        err, debug = message.parse_warning()
        print(err, debug)

    elif mtype == Gst.MessageType.LATENCY:  # needs self. scope added
        print("LATENCY")

    elif mtype == Gst.MessageType.ELEMENT:
        print("ELEMENT")

    return True

def supports_resolution_and_format(device, width, height, framerate=None):
    supported_formats = []
    if framerate is not None:
        framerate = str(framerate)+"/1"

    if device and device.get_caps():
        for structure in device.get_caps().to_string().split(';'):
            if 'video/x-raw' in structure and 'width=(int)' + str(width) in structure and 'height=(int)' + str(height) in structure:
                if framerate and 'framerate=' in structure:
                    if framerate in structure:
                        format_type = structure.split('format=(string)')[1].split(',')[0]  # Extract the format
                        supported_formats.append(format_type)
                else:
                    format_type = structure.split('format=(string)')[1].split(',')[0]  # Extract the format
                    supported_formats.append(format_type)
            elif 'jpeg' in structure:
                 supported_formats.append('JPEG')
            elif '264' in structure:
                 supported_formats.append('H264')
    priority_order = ['JPEG', 'I420', 'YVYU','YUY2','NV12', 'NV21', 'UYVY', 'RGB', 'BGR', 'BGRx', 'RGBx']
    return sorted(supported_formats, key=lambda x: priority_order.index(x) if x in priority_order else len(priority_order))

class WHIPClient:
    def __init__(self, pipeline_desc, args):
        self.pipeline_desc = pipeline_desc
        self.args = args
        self.pipe = None
        self.loop = None
        
    def setup_pipeline(self):
        # Configure WHIP elements
        whip_props = [
            'whipsink name=sendrecv',
            f'whip-endpoint="{self.args.whip}"'
        ]
        
        # Add STUN servers
        if self.args.stun_server:
            if self.args.stun_server not in ["0", "false", "null"]:
                whip_props.append(f'stun-server="{self.args.stun_server}"')
        else:
            whip_props.append('stun-server="stun://stun.cloudflare.com:3478"')
            whip_props.append('stun-server="stun://stun.l.google.com:19302"')
        
        # Add TURN servers    
        if self.args.turn_server:
            if self.args.turn_server not in ["0", "false", "null"]:
                whip_props.append(f'turn-server="{self.args.turn_server}"')
        else:
            whip_props.append('turn-server="turn://vdoninja:IchBinSteveDerNinja@www.turn.vdo.ninja:3478"')
        
        whip_props.append(f'ice-transport-policy={self.args.ice_transport_policy}')
        
        # Build complete pipeline
        pipeline_segments = [self.pipeline_desc]
        pipeline_segments.append(' '.join(whip_props))
        complete_pipeline = ' '.join(pipeline_segments)
        
        print('gst-launch-1.0 ' + complete_pipeline.replace('(', '\\(').replace(')', '\\)'))
        
        self.pipe = Gst.parse_launch(complete_pipeline)
        return self.pipe

    def on_state_changed(self, bus, message):
        if message.type == Gst.MessageType.STATE_CHANGED:
            if message.src == self.pipe:
                old, new, pending = message.parse_state_changed()
                print(f"Pipeline state changed from {old} to {new}")
                if new == Gst.State.NULL:
                    printwarn("Pipeline stopped unexpectedly")
                    GLib.timeout_add_seconds(30, self.reconnect)

    def reconnect(self):
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
        self.setup_pipeline()
        self.pipe.set_state(Gst.State.PLAYING)
        return False

    def start(self):
        if not check_plugins('whipsink'):
            print("WHIP SINK not installed. Please install (build if needed) the gst-plugins-rs webrtchttp plugin for your specific version of Gstreamer; 1.22 or newer required")
            return False
            
        self.setup_pipeline()
        bus = self.pipe.get_bus()
        bus.add_signal_watch()
        bus.connect('message::state-changed', self.on_state_changed)
        
        self.pipe.set_state(Gst.State.PLAYING)
        
        try:
            self.loop = GLib.MainLoop()
        except:
            self.loop = GObject.MainLoop()
            
        try:
            self.loop.run()
        except Exception as E:
            printwarn(get_exception_info(E))
            if self.loop:
                self.loop.quit()
            return False
            
        return True

    def stop(self):
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
        if self.loop:
            self.loop.quit()
            
def find_hardware_converter():
    """
    Checks for the availability of hardware-accelerated format conversion elements
    specific to Rockchip or other platforms.
    
    Returns:
        tuple: (converter_element_name, is_hardware_converter)
    """
    # Check for Rockchip-specific hardware converters
    rockchip_converters = [
        "rkvideoconvert",     # Rockchip general converter
        "mppvideoconvert",    # Possible MPP-based converter
        "rkvideosink",        # Might include conversion capabilities
        "rkmppvideoconvert"   # Another possible naming
    ]
    
    for converter in rockchip_converters:
        if check_plugins(converter):
            print(f"Found hardware video converter: {converter}")
            return converter, True
    
    # If no hardware converter found, fall back to software
    print("No hardware video converter found, will use software videoconvert")
    return "videoconvert", False

def get_conversion_pipeline(src_format, dst_format="NV12", hw_converter=None):
    """
    Creates the appropriate conversion pipeline segment based on 
    source and destination formats and available hardware converters.
    
    Args:
        src_format: Source pixel format (e.g., "NV16", "BGR")
        dst_format: Destination pixel format (usually "NV12" for encoders)
        hw_converter: Name of hardware converter element if available
        
    Returns:
        str: Pipeline string segment for conversion
    """
    # If formats are identical, no conversion needed
    if src_format == dst_format:
        return ""
    
    # If we have a hardware converter, use it
    if hw_converter and hw_converter != "videoconvert":
        # Hardware converters often need specific elements or parameters
        if hw_converter == "rkvideoconvert":
            # Some hardware converters might need additional parameters
            return f" ! {hw_converter} ! video/x-raw,format={dst_format}"
        else:
            # Generic hardware converter usage
            return f" ! {hw_converter} ! video/x-raw,format={dst_format}"
    else:
        # Default to software conversion with videoconvert
        # Add a queue to prevent blocking the capture (makes it more real-time)
        return f" ! queue max-size-buffers=2 leaky=upstream ! videoconvert ! video/x-raw,format={dst_format}"

def detect_best_formats(device):
    """
    Detects the best formats available on the device for efficient encoding.
    Returns a list of preferred formats in order of efficiency.
    """
    # Get device capabilities
    properties = device.get_properties()
    
    # Check if this is a known Rockchip device (like Orange Pi 5 Plus)
    is_rockchip = False
    try:
        if 'rockchip' in properties.get_value("device.bus_path").lower() or 'rk_' in device.get_display_name().lower():
            is_rockchip = True
    except:
        pass

    # Preferred format order for various platforms
    if is_rockchip and check_plugins('rockchipmpp'):
        # Rockchip MPP prefers these formats for hardware acceleration
        return ["NV12", "NV16", "NV24", "I420", "YV12", "BGR", "RGB"]
    else:
        # Generic order of preference for most platforms
        return ["I420", "NV12", "YUY2", "UYVY", "NV16", "NV24", "BGR", "RGB"]

def get_supported_formats(device, width, height, framerate):
    """
    Gets a list of formats that are supported by the device at given resolution.
    """
    try:
        caps = device.get_caps()
        supported_formats = []
        
        # Iterate through all caps structures
        for i in range(caps.get_size()):
            structure = caps.get_structure(i)
            name = structure.get_name()
            
            # Only look at raw video formats
            if not name.startswith('video/x-raw'):
                continue
                
            # Check if format is specified
            if structure.has_field('format'):
                format_value = structure.get_value('format')
                
                # Check if width/height match or are flexible
                width_match = structure.has_field('width') and check_resolution_match(structure, 'width', width)
                height_match = structure.has_field('height') and check_resolution_match(structure, 'height', height)
                framerate_match = structure.has_field('framerate') and check_framerate_match(structure, 'framerate', framerate)
                
                if width_match and height_match and framerate_match:
                    # If it's a string, add it directly
                    if isinstance(format_value, str):
                        supported_formats.append(format_value)
                    # If it's a list of options (like from a GstValueList)
                    else:
                        try:
                            for j in range(format_value.n_values()):
                                supported_formats.append(format_value.get_string(j))
                        except:
                            # If we can't iterate, try to convert to string
                            supported_formats.append(str(format_value))
        
        return supported_formats
    except Exception as e:
        print(f"Error getting supported formats: {e}")
        return []

def check_resolution_match(structure, field, target_value):
    """
    Checks if the structure supports the target resolution value.
    Handles both exact values and ranges.
    """
    try:
        field_value = structure.get_value(field)
        # If it's a range
        if hasattr(field_value, 'get_type_name') and field_value.get_type_name() == 'GstIntRange':
            min_val = field_value.get_int_range_min()
            max_val = field_value.get_int_range_max()
            return min_val <= target_value <= max_val
        # If it's an exact value
        else:
            return field_value == target_value
    except:
        # If we can't determine, assume it's supported
        return True

def check_framerate_match(structure, field, target_value):
    """
    Checks if the structure supports the target framerate.
    Handles both exact values and ranges.
    """
    try:
        field_value = structure.get_value(field)
        # If it's a fraction range
        if hasattr(field_value, 'get_type_name') and field_value.get_type_name() == 'GstFractionRange':
            min_num = field_value.get_fraction_range_min().num
            min_denom = field_value.get_fraction_range_min().denom
            max_num = field_value.get_fraction_range_max().num
            max_denom = field_value.get_fraction_range_max().denom
            
            min_rate = min_num / min_denom
            max_rate = max_num / max_denom
            
            return min_rate <= target_value <= max_rate
        # If it's an exact fraction
        elif hasattr(field_value, 'get_type_name') and field_value.get_type_name() == 'GstFraction':
            return field_value.num / field_value.denom == target_value
        # If it's a list of fractions
        elif hasattr(field_value, 'n_values'):
            for i in range(field_value.n_values()):
                val = field_value.get_value(i)
                if val.num / val.denom == target_value:
                    return True
            return False
        else:
            return field_value == target_value
    except:
        # If we can't determine, assume it's supported
        return True

def find_best_format(device, width, height, framerate, encoder_type="auto"):
    """
    Find the best format for the given device, resolution, and encoder type.
    
    Args:
        device: GstDevice object
        width: desired width
        height: desired height
        framerate: desired framerate
        encoder_type: "vp8", "h264", "auto" or other encoder types
        
    Returns:
        The best format string or None if no suitable format found
    """
    # Get supported formats at this resolution
    supported_formats = get_supported_formats(device, width, height, framerate)
    
    if not supported_formats:
        print(f"No formats supported at {width}x{height}@{framerate}fps. Using default format.")
        return None
        
    # Get preferred formats in ideal order
    preferred_formats = detect_best_formats(device)
    
    # For rockchip hardware encoders
    if check_plugins('rockchipmpp'):
        if encoder_type == "vp8" or encoder_type == "auto":
            # mppvp8enc works best with NV12
            for fmt in ["NV12", "NV16", "I420"]:
                if fmt in supported_formats:
                    return fmt
                    
        elif encoder_type == "h264":
            # mpph264enc works best with NV12
            for fmt in ["NV12", "NV16", "I420"]:
                if fmt in supported_formats:
                    return fmt
    
    # For general cases, find the first match in our preferred order
    for fmt in preferred_formats:
        if fmt in supported_formats:
            return fmt
            
    # If no preferred format matches, return the first supported format
    return supported_formats[0] if supported_formats else None
    
def optimize_pipeline_for_device(device, width, height, framerate, iomode, formatspace, encoder_type="auto"):
    """
    Creates an optimized pipeline section for a specific device and desired output.
    
    Args:
        device: Video device path (e.g., "/dev/video0")
        width: Desired output width
        height: Desired output height
        framerate: Desired output framerate
        encoder_type: Type of encoder being used ("vp8", "h264", etc.)
        
    Returns:
        tuple: (input_pipeline, converter_pipeline, best_format)
    """
    # Set up device monitor to get device capabilities
    video_monitor = Gst.DeviceMonitor.new()
    video_monitor.add_filter("Video/Source", None)
    videodevices = video_monitor.get_devices()
    
    # Find our target device
    target_device = None
    for dev in videodevices:
        props = dev.get_properties()
        if props.get_value("device.path") == device:
            target_device = dev
            break
    
    if not target_device:
        print(f"Warning: Could not find detailed capabilities for {device}")
        if videodevices:
            print("Using first available device for capabilities")
            target_device = videodevices[0]
        else:
            print("No video devices found")
            return None, None, None
    
    # Find hardware converter if available
    hw_converter, is_hw_converter = find_hardware_converter()
    
    # Find best format for device
    best_format = formatspace or find_best_format(target_device, width, height, framerate, encoder_type)
    
    if not best_format:
        print(f"Warning: Could not determine optimal format for {device}")
        # Use a safe default based on platform
        if check_plugins('rockchipmpp'):
            best_format = "NV16"  # Common fallback for Rockchip
        else:
            best_format = "I420"  # Generic fallback
    
    # Create source pipeline segment with specific format
    input_pipeline = f'v4l2src device={device} io-mode={str(iomode)} ! queue max-size-buffers=2 leaky=upstream ! video/x-raw,format={best_format},width=(int){width},height=(int){height},framerate=(fraction){framerate}/1'
    
    # Create conversion pipeline segment if needed
    target_format = "NV12"  # Most hardware encoders prefer NV12
    converter_pipeline = get_conversion_pipeline(best_format, target_format, hw_converter) 
    
    print(f"Optimized pipeline:")
    print(f"- Source: {input_pipeline}")
    print(f"- Converter: {converter_pipeline}")
    print(f"- Using hardware converter: {is_hw_converter}")
    
    return input_pipeline, converter_pipeline, best_format


def resolve_v4l2sink_device(device: Optional[str], default_index: int = 0) -> Optional[str]:
    """Resolve a writable V4L2 output device for v4l2sink."""
    candidate = None
    if device:
        text = str(device).strip()
        if text.isdigit():
            candidate = f"/dev/video{int(text)}"
        elif text.startswith("/dev/video"):
            candidate = text
        elif text.startswith("video") and text[5:].isdigit():
            candidate = f"/dev/{text}"
        else:
            candidate = text
    else:
        candidate = f"/dev/video{default_index}"

    if candidate and os.path.exists(candidate) and os.access(candidate, os.W_OK):
        return candidate

    if candidate:
        printc(
            f"V4L2 output device {candidate} unavailable or not writable; scanning for alternatives.",
            "F77",
        )

    for path in sorted(glob.glob("/dev/video*")):
        if os.path.exists(path) and os.access(path, os.W_OK):
            printc(f"Using first writable V4L2 output: {path}", "7F7")
            return path

    return None


WSS="wss://wss.vdo.ninja:443"

async def main():

    error = False
    parser = argparse.ArgumentParser()
    parser.add_argument('--streamid', type=str, default=str(random.randint(1000000,9999999)), help='Stream ID of the peer to connect to')
    parser.add_argument('--room', type=str, default=None, help='optional - Room name of the peer to join')
    parser.add_argument('--rtmp', type=str, default=None, help='Use RTMP instead; pass the rtmp:// publishing address here to use')
    parser.add_argument('--whip', type=str, default=None, help='Use WHIP output instead; pass the https://whip.publishing/address here to use')
    parser.add_argument('--bitrate', type=int, default=2500, help='Sets the video bitrate; kbps. If error correction (red) is on, the total bandwidth used may be up to 2X higher than the bitrate')
    parser.add_argument('--audiobitrate', type=int, default=64, help='Sets the audio bitrate; kbps.')
    parser.add_argument('--width', type=int, default=1920, help='Sets the video width. Make sure that your input supports it.')
    parser.add_argument('--height', type=int, default=1080, help='Sets the video height. Make sure that your input supports it.')
    parser.add_argument('--framerate', type=int, default=30, help='Sets the video framerate. Make sure that your input supports it.')
    parser.add_argument('--server', type=str, default=None, help='Handshake server to use, eg: "wss://wss.vdo.ninja:443"')
    parser.add_argument('--puuid',  type=str, default=None, help='Specify a custom publisher UUID value; not required')
    parser.add_argument('--test', action='store_true', help='Use test sources.')
    parser.add_argument('--hdmi', action='store_true', help='Try to setup a HDMI dongle')
    parser.add_argument('--camlink', action='store_true', help='Try to setup an Elgato Cam Link')
    parser.add_argument('--z1', action='store_true', help='Try to setup a Theta Z1 360 camera')
    parser.add_argument('--z1passthru', action='store_true', help='Try to setup a Theta Z1 360 camera, but do not transcode')
    parser.add_argument('--apple', type=str, action=None, help='Sets Apple Video Foundation media device; takes a device index value (0,1,2,3,etc)')
    parser.add_argument('--v4l2', type=str, default=None, help='Sets the V4L2 input device.')
    parser.add_argument('--iomode', type=int, default=2, help='Sets a custom V4L2 I/O Mode')
    parser.add_argument('--libcamera', action='store_true',  help='Use libcamera as the input source')
    parser.add_argument('--rpicam', action='store_true', help='Sets the RaspberryPi CSI input device. If this fails, try --rpi --raw or just --raw instead.')
    parser.add_argument('--format', type=str, default=None, help='The capture format type: YUYV, I420, BGR, or even JPEG/H264')
    parser.add_argument('--rotate', type=int, default=0, help='Rotates the camera in degrees; 0 (default), 90, 180, 270 are possible values.')
    parser.add_argument('--nvidiacsi', action='store_true', help='Sets the input to the nvidia csi port.')
    parser.add_argument('--alsa', type=str, default=None, help='Use alsa audio input.')
    parser.add_argument('--pulse', type=str, help='Use pulse audio (or pipewire) input.')
    parser.add_argument('--zerolatency', action='store_true', help='A mode designed for the lowest audio output latency')
    parser.add_argument('--lowlatency', action='store_true', help='Enable low latency mode with leaky queues. May drop frames under load but reduces latency.')
    parser.add_argument('--raw', action='store_true', help='Opens the V4L2 device with raw capabilities.')
    parser.add_argument('--bt601', action='store_true', help='Use colormetery bt601 mode; enables raw mode also')
    parser.add_argument('--h264', action='store_true', help='Prioritize h264 over vp8')
    parser.add_argument('--x264', action='store_true', help='Prioritizes x264 encoder over hardware encoder')
    parser.add_argument('--openh264', action='store_true', help='Prioritizes OpenH264 encoder over hardware encoder')
    parser.add_argument('--force-h264-profile', type=str, default=None, help='Viewer: force a named H264 profile (baseline, constrained-baseline, main, high, high10, high422, high444) instead of mirroring the sender')
    parser.add_argument('--force-h264-profile-id', type=str, default=None, help='Viewer: force a custom H264 profile-level-id (hex, e.g. 42001f). Overrides --force-h264-profile.')
    parser.add_argument('--vp8', action='store_true', help='Prioritizes vp8 codec over h264; software encoder')
    parser.add_argument('--vp9', action='store_true', help='Prioritizes vp9 codec over h264; software encoder')
    parser.add_argument('--aom', action='store_true', help='Prioritizes AV1-AOM codec; software encoder')
    parser.add_argument('--av1', action='store_true', help='Auto selects an AV1 codec for encoding; hardware or software')
    parser.add_argument('--rav1e', action='store_true', help='rav1e AV1 encoder used')
    parser.add_argument('--qsv', action='store_true', help='Intel quicksync AV1 encoder used')
    parser.add_argument('--omx', action='store_true', help='Try to use the OMX driver for encoding video; not recommended')
    parser.add_argument('--vorbis', action='store_true', help='Try to use the OMX driver for encoding video; not recommended')
    parser.add_argument('--nvidia', action='store_true', help='Creates a pipeline optimised for nvidia hardware.')
    parser.add_argument('--rpi', action='store_true', help='Creates a pipeline optimised for raspberry pi hardware encoder. Note: RPi5 has no hardware encoder and will automatically fall back to software encoding (x264).')
    parser.add_argument('--multiviewer', action='store_true', help='Allows for multiple viewers to watch a single encoded stream; will use more CPU and bandwidth.')
    parser.add_argument('--webserver', type=int, metavar='PORT', help='Enable web interface on specified port (e.g., --webserver 8080) for monitoring stats, logs, and controls.')
    parser.add_argument('--noqos', action='store_true', help='Do not try to automatically reduce video bitrate if packet loss gets too high. The default will reduce the bitrate if needed.')
    parser.add_argument('--nored', action='store_true', help='Disable error correction redundency for transmitted video. This may reduce the bandwidth used by half, but it will be more sensitive to packet loss')
    parser.add_argument('--force-red', action='store_true', help='Force negotiation of RED/ULPFEC/RTX redundancy when supported by the remote peer (H264/VP8/AV1). Increases bandwidth but improves resilience to packet loss.')
    parser.add_argument('--publisher-fec-percentage', type=int, default=20, metavar='PCT', help='FEC overhead percentage to use for the built-in publisher RED/ULPFEC chain (0-100).')
    parser.add_argument('--publisher-red-distance', type=int, default=1, metavar='DIST', help='Number of prior RTP packets to embed as RED redundancy (minimum 1).')
    parser.add_argument('--publisher-red-pt', type=int, default=123, metavar='PT', help='Payload type ID reserved for RED when the publisher redundancy chain is enabled.')
    parser.add_argument('--publisher-fec-pt', type=int, default=125, metavar='PT', help='Payload type ID reserved for ULPFEC packets when the publisher redundancy chain is enabled.')
    parser.add_argument('--force-rtx', action='store_true', help='Force-enable RTX retransmissions when supported by the local GStreamer build (verified with GStreamer 1.26+).')
    parser.add_argument('--novideo', action='store_true', help='Disables video input.')
    parser.add_argument('--noaudio', action='store_true', help='Disables audio input.')
    parser.add_argument('--led', action='store_true', help='Enable GPIO pin 12 as an LED indicator light; for Raspberry Pi.')
    parser.add_argument('--pipeline', type=str, help='A full custom pipeline')
    parser.add_argument('--record',  type=str, help='Specify a stream ID to record to disk. System will not publish a stream when enabled.')
    parser.add_argument('--view',  type=str, help='Specify a stream ID to play out to the local display/audio.')
    parser.add_argument('--no-auto-retry', action='store_true', help='Viewer mode: disable automatic reconnect attempts when the remote peer disconnects.')
    parser.add_argument('--viewer-retry-initial', type=float, default=15.0, help='Viewer mode: seconds to wait before the first automatic reconnect attempt after a disconnect (default 15s).')
    parser.add_argument('--viewer-retry-short', type=float, default=45.0, help='Viewer mode: seconds to wait before the second reconnect attempt (default 45s).')
    parser.add_argument('--viewer-retry-long', type=float, default=180.0, help='Viewer mode: seconds to wait between subsequent reconnect attempts (default 180s).')
    parser.add_argument('--viewer-enable-fec', action='store_true', help='Enable experimental viewer-side ULPFEC recovery. This currently requires manual testing and may destabilize the viewer; disabled by default.')
    parser.add_argument('--stretch-display', action='store_true', help='Scale viewer output to fill the detected framebuffer/display when possible.')
    parser.add_argument('--splashscreen-idle', type=str, default=None, help='Path to an image displayed when the viewer is idle or no stream is active.')
    parser.add_argument('--splashscreen-connecting', type=str, default=None, help='Path to an image displayed while the viewer is connecting to a stream.')
    parser.add_argument('--disable-hw-decoder', action='store_true', help='Force software decoding for incoming streams even if hardware decoders are available.')
    parser.add_argument('--save', action='store_true', help='Save a copy of the outbound stream to disk. Publish Live + Store the video.')
    parser.add_argument('--record-room', action='store_true', help='Record all streams in a room to separate files. Requires --room parameter.')
    parser.add_argument('--record-streams', type=str, help='Comma-separated list of stream IDs to record from a room. Optional filter for --record-room.')
    parser.add_argument('--room-monitor', action='store_true', help='Join a room in monitor-only mode (no play/publish). Useful for room-join alerts.')
    parser.add_argument('--join-webhook', type=str, help='POST room-join events as JSON to this webhook URL.')
    parser.add_argument('--join-postapi', type=str, help='POST room-join events using VDO.Ninja postapi format ({update:{...}}).')
    parser.add_argument('--join-notify-topic', type=str, help='Trigger VDO.Ninja notify API on room joins using this notify topic.')
    parser.add_argument('--join-notify-url', type=str, default='https://notify.vdo.ninja/', help='Base URL for notify-topic triggers (default: https://notify.vdo.ninja/).')
    parser.add_argument('--join-notify-timeout', type=float, default=5.0, help='Timeout in seconds for join notification HTTP calls.')
    parser.add_argument('--join-gpio-pin', type=int, help='Pulse this BOARD-mode GPIO pin when a room join event is detected (Raspberry Pi).')
    parser.add_argument('--join-gpio-pulse', type=float, default=0.4, help='GPIO pulse duration in seconds for --join-gpio-pin (default: 0.4s).')
    parser.add_argument('--join-gpio-active-low', action='store_true', help='Use active-low pulses for --join-gpio-pin.')
    parser.add_argument('--audio', action='store_true', help='Deprecated flag (audio recording is now enabled by default). Use --noaudio to disable audio recording.')
    parser.add_argument('--hls', action='store_true', help='Use HLS format for recording instead of WebM/MP4. Includes audio+video muxing and creates .m3u8 playlists.')
    parser.add_argument('--hls-splitmux', action='store_true', help='Use splitmuxsink for HLS recording (recommended) instead of hlssink.')
    parser.add_argument('--room-ndi', action='store_true', help='Relay all room streams to NDI as separate sources. Requires --room parameter. Uses direct mode by default (separate audio/video streams).')
    parser.add_argument('--ndi-combine', action='store_true', help='Use NDI combiner for audio/video muxing (WARNING: Known to freeze after ~1500 buffers). Default is direct mode with separate streams.')
    parser.add_argument('--midi', action='store_true', help='Transparent MIDI bridge mode; no video or audio.')
    parser.add_argument('--filesrc', type=str, default=None,  help='Provide a media file (local file location) as a source instead of physical device; it can be a transparent webm or whatever. It will be transcoded, which offers the best results.')
    parser.add_argument('--filesrc2', type=str, default=None,  help='Provide a media file (local file location) as a source instead of physical device; it can be a transparent webm or whatever. It will not be transcoded, so be sure its encoded correctly. Specify if --vp8 or --vp9, else --h264 is assumed.')
    parser.add_argument('--pipein', type=str, default=None, help='Pipe a media stream in as the input source. Pass `auto` for auto-decode,pass codec type for pass-thru (mpegts,h264,vp8,vp9), or use `raw`')
    parser.add_argument('--ndiout',  type=str, help='VDO.Ninja to NDI output; requires the NDI Gstreamer plugin installed')
    parser.add_argument('--fdsink',  type=str, help='VDO.Ninja to the stdout pipe; common for piping data between command line processes')
    parser.add_argument('--framebuffer', type=str, help='VDO.Ninja to local frame buffer; performant and Numpy/OpenCV friendly')
    parser.add_argument('--v4l2sink', type=str, default=None, help='Viewer output to V4L2 device; requires --view STREAMID (accepts device index or path)')
    parser.add_argument('--v4l2sink-width', type=int, default=1280, help='V4L2 sink output width (default: 1280)')
    parser.add_argument('--v4l2sink-height', type=int, default=720, help='V4L2 sink output height (default: 720)')
    parser.add_argument('--v4l2sink-fps', type=int, default=30, help='V4L2 sink output framerate (default: 30)')
    parser.add_argument('--v4l2sink-format', type=str, default='YUY2', help='V4L2 sink output format (default: YUY2)')
    parser.add_argument('--debug', action='store_true', help='Show added debug information from Gsteamer and other aspects of the app')
    parser.add_argument('--buffer',  type=int, default=200, help='The jitter buffer latency in milliseconds; default is 200ms, minimum is 10ms. (gst +v1.18)')
    parser.add_argument('--auto-view-buffer', action='store_true', help='Viewer mode: dynamically raise jitter buffer latency when packet loss is detected (opt-in).')
    parser.add_argument('--password', type=str, nargs='?', default="someEncryptionKey123", required=False, const='', help='Specify a custom password. If setting to false, password/encryption will be disabled.')
    parser.add_argument('--salt', type=str, default=None, help='Specify a custom salt for encryption. If not provided, will be derived from hostname (default: vdo.ninja)')
    parser.add_argument('--hostname', type=str, default='https://vdo.ninja/', help='Your URL for vdo.ninja, if self-hosting the website code')
    parser.add_argument('--video-pipeline', type=str, default=None, help='Custom GStreamer video source pipeline')
    parser.add_argument('--audio-pipeline', type=str, default=None, help='Custom GStreamer audio source pipeline')
    parser.add_argument('--timestamp', action='store_true',  help='Add a timestamp to the video output, if possible')
    parser.add_argument('--clockstamp', action='store_true',  help='Add a clock overlay to the video output, if possible')
    parser.add_argument('--socketport', type=str, default=12345, help='Output video frames to a socket; specify the port number')
    parser.add_argument('--socketout', type=str, help='Output video frames to a socket; specify the stream ID')
    parser.add_argument('--stun-server', type=str, help='STUN server URL (stun://hostname:port)')
    parser.add_argument('--turn-server', type=str, help='TURN server URL (turn(s)://username:password@host:port)')
    parser.add_argument('--ice-transport-policy', type=str, choices=['all', 'relay'], default='all', help='ICE transport policy (all or relay)')
    parser.add_argument('--h265', action='store_true', help='Prioritize h265/hevc encoding over h264')
    parser.add_argument('--hevc', action='store_true', help='Prioritize h265/hevc encoding over h264 (same as --h265)')
    parser.add_argument('--x265', action='store_true', help='Prioritizes x265 software encoder over hardware encoders')
    parser.add_argument('--config', type=str, default=None, help='Path to JSON configuration file')


    parser.add_argument('--soft-jpeg', action='store_true', help='Force software JPEG decoding (bypass v4l2jpegdec) on Raspberry Pi')
    
    args = parser.parse_args()
    
    # Load config file if specified
    if args.config:
        config_path = os.path.expanduser(args.config)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                
                # Override args with config values (but command line args take precedence)
                for key, value in config.items():
                    if hasattr(args, key) and getattr(args, key) == parser.get_default(key):
                        # Only override if the current value is the default
                        if key == 'audio_enabled' and value is False:
                            setattr(args, 'noaudio', True)
                        elif key == 'video_source':
                            if value == 'test':
                                setattr(args, 'test', True)
                            elif value == 'libcamera':
                                setattr(args, 'libcamera', True)
                            elif value == 'v4l2':
                                setattr(args, 'v4l2', '/dev/video0')
                            elif value == 'custom' and 'custom_video_pipeline' in config:
                                setattr(args, 'video_pipeline', config['custom_video_pipeline'])
                        elif key != 'platform' and key != 'auto_start' and key != 'audio_enabled' and key != 'video_source' and key != 'custom_video_pipeline':
                            setattr(args, key, value)
                
                print(f"Loaded configuration from: {config_path}")
            except Exception as e:
                print(f"Error loading config file: {e}")
        else:
            print(f"Config file not found: {config_path}")
    
    if args.force_h264_profile and not args.force_h264_profile_id:
        alias = args.force_h264_profile.strip().lower()
        mapped = H264_PROFILE_ALIASES.get(alias)
        if mapped:
            args.force_h264_profile_id = mapped
        else:
            known = ", ".join(sorted({k.replace("_", "-") for k in H264_PROFILE_ALIASES.keys()}))
            printc(f"Warning: Unknown --force-h264-profile value '{args.force_h264_profile}'. Known values: {known}", "FF0")
    if args.force_h264_profile_id:
        sanitized_profile = sanitize_profile_level_id(args.force_h264_profile_id)
        if sanitized_profile:
            args.force_h264_profile_id = sanitized_profile
        else:
            printc(f"Warning: Ignoring invalid --force-h264-profile-id '{args.force_h264_profile_id}'. Expected 6 hex characters.", "FF0")
            args.force_h264_profile_id = None

    # Normalize splash screen paths if provided
    for attr in ('splashscreen_idle', 'splashscreen_connecting'):
        path = getattr(args, attr, None)
        if path:
            expanded = os.path.abspath(os.path.expanduser(path))
            if not os.path.isfile(expanded):
                printc(f"Warning: Splash screen image not found: {expanded}", "FF0")
                setattr(args, attr, None)
            else:
                setattr(args, attr, expanded)
    
    gst_version = Gst.version()
    args.gst_version = gst_version

    # Display header
    printc("\n╔═══════════════════════════════════════════════╗", "0FF")
    printc("║          🥷 Raspberry Ninja                   ║", "0FF") 
    printc("║     Multi-Platform WebRTC Publisher           ║", "0FF")
    printc("╚═══════════════════════════════════════════════╝\n", "0FF")

    if args.view:
        gst_major, gst_minor, gst_micro, gst_nano = gst_version
        printc("Viewer connection tips:", "0AF")
        printc("  • For unstable links try `--buffer 1500` or `--buffer 2000`.", "0AF")
        printc("  • Opt in to automatic buffer scaling with `--auto-view-buffer` when stutter appears.", "0AF")
        if gst_major > 1 or (gst_major == 1 and gst_minor >= 24):
            printc("  • RTX is available; pair `--force-red` with `--force-rtx` when the sender supports it.", "0AF")
        else:
            printc("  • This build is FEC-only; `--force-red` plus a higher buffer helps with heavy loss.", "0AF")
        if getattr(args, "no_auto_retry", False):
            printc("  • Auto-retry disabled (`--no-auto-retry`); restart manually if the peer drops.", "0AF")
        else:
            printc(
                f"  • Auto-retry waits {args.viewer_retry_initial:.0f}s before the first reconnect, "
                f"{max(args.viewer_retry_short, args.viewer_retry_initial):.0f}s before the second, "
                f"then every {max(args.viewer_retry_long, args.viewer_retry_short):.0f}s.",
                "0AF",
            )
        print()
    
    # Validate buffer value to prevent segfaults
    if args.buffer < 10:
        printc("Warning: Buffer values below 10ms can cause segfaults. Setting to minimum of 10ms.", "F77")
        args.buffer = 10
    
    # Notify about low latency mode
    if args.lowlatency:
        printc("⚡ Low latency mode enabled - frames may be dropped under load", "FF0")

    Gst.init(None)

    if args.debug:
        Gst.debug_set_active(True)
        Gst.debug_set_default_threshold(3)  # More verbose
        # Also set specific categories for WebRTC debugging
        Gst.debug_set_threshold_for_name("webrtcbin", 5)
        Gst.debug_set_threshold_for_name("webrtcice", 5)
        Gst.debug_set_threshold_for_name("nice", 4)
        printc("🐛 GStreamer debug output enabled", "FF0")
    else:
        Gst.debug_set_active(False)
        Gst.debug_set_default_threshold(0)
    if args.led:
        try:
            import RPi.GPIO as GPIO
            global LED_Level, p_R, pin
            GPIO.setwarnings(False)
            pin = 12  # pins is a dict
            GPIO.setmode(GPIO.BOARD)       # Numbers GPIOs by physical location
            LED_Level = 0.1 # 0.1 to 100
            GPIO.setup(pin, GPIO.OUT)   # Set pins' mode is output
            GPIO.output(pin, GPIO.HIGH) # Set pins to high(+3.3V) to off led
            p_R = GPIO.PWM(pin, 120)  # set Frequece to 2KHzi
            enableLEDs(0.1)
        except Exception as E:
            pass

    timestampOverlay = ''
    if args.timestamp:
        timestampOverlay = ' ! timeoverlay valignment=bottom halignment=right font-desc="Sans, 36"'
    elif args.clockstamp:
        timestampOverlay = ' ! clockoverlay valignment=bottom halignment=right font-desc="Sans, 36"'

    if args.password == None:
        pass
    elif args.password.lower() in ["", "true", "1", "on"]:
        args.password = "someEncryptionKey123"
    elif args.password.lower() in ["false", "0", "off"]:
        args.password = None

    PIPELINE_DESC = ""
    pipeline_video_converter = ""

    needed = ["rtp", "rtpmanager"]
    if not args.rtmp:
        needed += ["webrtc","nice", "sctp", "dtls", "srtp"]
    if not check_plugins(needed, True):
        sys.exit(1)
    needed = []

    if args.v4l2sink and not args.view:
        printc("Error: --v4l2sink requires --view STREAMID", "F00")
        sys.exit(1)
    if args.v4l2sink:
        needed += ["video4linux2"]

    join_alert_requested = bool(
        args.join_webhook
        or args.join_postapi
        or args.join_notify_topic
        or args.join_gpio_pin is not None
    )

    if args.ndiout:
        needed += ['ndi']
        if not args.record:
            args.streamin = args.ndiout
        else:
            args.streamin = args.record
    elif args.view:
        args.streamin = args.view

    elif args.fdsink:
        args.streamin = args.fdsink
    elif args.socketout:
        args.streamin = args.socketout
    elif args.framebuffer:
        if not np:
            print("You must install Numpy for this to work.\npip3 install numpy")
            sys.exit()
        
        # Check for GStreamer 1.18 bug with framebuffer mode
        gst_version = Gst.version()
        if gst_version.major == 1 and gst_version.minor == 18:
            printc("\n⚠️  WARNING: GStreamer 1.18 detected with --framebuffer mode", "F70")
            printc("━" * 60, "F70")
            printc("GStreamer 1.18 has a known bug that causes crashes in framebuffer mode.", "F70")
            printc("You may encounter: 'ERROR:gstwebrtcbin.c:5657:on_rtpbin_new_jitterbuffer'", "F70")
            printc("", "")
            printc("RECOMMENDED SOLUTIONS:", "0F0")
            printc("1. Upgrade to GStreamer 1.20 or newer", "0F0")
            printc("   - Ubuntu 22.04+ has GStreamer 1.20+", "07F")
            printc("   - Debian 12+ has GStreamer 1.22+", "07F")
            printc("2. Use Docker: docker run -it ubuntu:22.04", "0F0")
            printc("3. Use --filesink or --fdsink instead of --framebuffer", "0F0")
            printc("━" * 60, "F70")
            printc("Press Ctrl+C to exit or wait 5 seconds to continue anyway...", "F70")
            try:
                time.sleep(5)
            except KeyboardInterrupt:
                printc("\nExiting due to GStreamer 1.18 compatibility issue.", "F00")
                sys.exit(1)
        
        args.streamin = args.framebuffer
    elif args.record_room or args.room_ndi:
        # Room recording mode (check this first before regular record)
        args.streamin = "room_recording"  # Special value to indicate room recording mode
        args.room_recording = True
        args.auto_turn = True  # Automatically use default TURN servers for room recording
        
        # Validate room parameter
        if not args.room:
            printc("Error: --record-room and --room-ndi require --room parameter", "F00")
            sys.exit(1)
            
        # Warn about custom websocket limitations
        if args.puuid:
            printc("Warning: Room recording may not work with custom websocket servers", "F77")
            printc("This feature requires a server that tracks room membership and sends notifications", "F77")
            
        # If --record is also specified, use it as the prefix
        if not args.record:
            args.record = args.room  # Default to room name if no prefix specified
            
        # Parse stream filter if provided
        if args.record_streams:
            args.stream_filter = [s.strip() for s in args.record_streams.split(',')]
        else:
            args.stream_filter = None
    elif args.room_monitor or join_alert_requested:
        # Room monitor mode for join notifications without recording/NDI.
        args.room_monitor = True
        args.streamin = "room_monitor"
        args.room_recording = False

        if not args.room:
            printc("Error: --room-monitor and join notification options require --room", "F00")
            sys.exit(1)

        if args.puuid:
            printc("Warning: Room monitor may not work with custom websocket servers", "F77")
            printc("This feature requires a server that tracks room membership and sends notifications", "F77")
    elif args.record:
        # Single-stream recording mode - use subprocess like room recording
        args.streamin = "single_stream_recording"  # Special value to indicate subprocess recording
        args.single_stream_recording = True
        args.room_recording = False  # Not room recording, but use subprocess
        args.auto_turn = True  # Automatically use default TURN servers for recording
        printc(f"📹 Recording mode: {args.record} (using subprocess)", "0FF")
    else:
        args.streamin = False

    # Ensure stream_filter is always defined
    if not hasattr(args, 'stream_filter'):
        args.stream_filter = None

    audiodevices = []
    if not (args.test or args.noaudio or args.streamin):
        monitor = Gst.DeviceMonitor.new()
        monitor.add_filter("Audio/Source", None)
        audiodevices = monitor.get_devices()

    if not args.alsa and not args.noaudio and not args.pulse and not args.test and not args.pipein and not args.streamin:
        default = [d for d in audiodevices if d.get_properties().get_value("is-default") is True]
        args.alsa = "default"
        aname = "default"

        if len(default) > 0:
            device = default[0]
            args.alsa = 'hw:'+str(device.get_properties().get_value("alsa.card"))+',0'
            print(" >> Default audio device selected: %s, via '%s'" % (device.get_display_name(), 'alsasrc device="hw:'+str(device.get_properties().get_value("alsa.card"))+',0"'))
        elif len(audiodevices)==0:
            args.noaudio = True
            print("\nNo microphone or audio source found; disabling audio.")
        else:
            try:
                print("\nDetected audio sources:")
                for i, d in enumerate(audiodevices):
                    print("  - ",audiodevices[i].get_display_name(), audiodevices[i].get_property("internal-name"), audiodevices[i].get_properties().get_value("alsa.card"), audiodevices[i].get_properties().get_value("is-default"))
                    args.alsa = 'hw:'+str(audiodevices[i].get_properties().get_value("alsa.card"))+',0'
                print()
                default = None
                for d in audiodevices:
                    props = d.get_properties()
                    for e in range(int(props.n_fields())):
                        if (props.nth_field_name(e) == "device.api" and props.get_value(props.nth_field_name(e)) == "alsa"):
                            default = d
                            break
                    if default:
                        print(" >> Selected the audio device: %s, via '%s'" % (default.get_display_name(), 'alsasrc device="hw:'+str(default.get_properties().get_value("alsa.card"))+',0"'))
                        args.alsa = 'hw:'+str(default.get_properties().get_value("alsa.card"))+',0'
                        break
                if not default:
                    args.noaudio = True
                    print("\nNo audio source selected; disabling audio.")
            except Exception as e:
                print(f"Error accessing properties for audio device {i}: {e}")
        print()

    if check_plugins("rpicamsrc"):
        args.rpi=True
    elif check_plugins("nvvidconv"):
        args.nvidia=True
        if check_plugins("nvarguscamerasrc"):
            if not args.nvidiacsi and not args.record:
                print("\nTip: If using the Nvidia CSI camera, you'll want to use --nvidiacsi to enable it.\n")
    
    # Detect Raspberry Pi model for optimal defaults
    pi_model = get_raspberry_pi_model()
    
    # Auto-adjust resolution for Raspberry Pi models if using defaults
    # Only apply to software encoding scenarios (when NOT using --rpi)
    if pi_model > 0 and pi_model <= 4 and args.width == 1920 and args.height == 1080 and not args.rpi:
        # RPi 4 and older struggle with 1080p30 in SOFTWARE encoding
        args.width = 1280
        args.height = 720
        printc(f"\n📺 Raspberry Pi {pi_model} detected (software encoding mode)", "0FF")
        printc("   ├─ Defaulting to 720p (1280x720) for better performance", "FF0")
        printc("   ├─ Software encoding struggles with 1080p on RPi 4 and older", "FFF")
        printc("   ├─ Override with: --width 1920 --height 1080", "FFF")
        printc("   └─ Or use --rpi for hardware encoding at 1080p", "0F0")
        print("")  # Add spacing
    
    # Check if we're on a Raspberry Pi 5 and handle --rpi parameter
    if args.rpi:
        if pi_model == 5:
            print("\n⚠️  WARNING: Raspberry Pi 5 detected!")
            print("The Raspberry Pi 5 does not have hardware video encoding (no v4l2h264enc or omxh264enc).")
            print("Falling back to software encoding. This may impact performance.")
            print("Consider using --x264 or --openh264 for better software encoder control.\n")
            # Force software encoding
            args.x264 = True
            # Don't disable args.rpi entirely as it may affect other pipeline choices

    if args.rpicam:
        print("Please note: If rpicamsrc cannot be found, use --libcamera instead")
        if not check_plugins('rpicamsrc'):
            print("rpicamsrc was not found. using just --rpi instead")
            print()
            args.raw = True
            args.rpi = True
            args.rpicam = False

    if args.aom:
        if not check_plugins(['aom','videoparsersbad','rsrtp'], True):
            print("You'll probably need to install gst-plugins-rs to use AV1 (av1enc, av1parse, av1pay)")
            print("ie: https://github.com/steveseguin/raspberry_ninja/blob/6873b97af02f720b9dc2e5c3ae2e9f02d486ba52/raspberry_pi/installer.sh#L347")
            sys.exit()
        else:
            args.av1 = True
        if args.rpi:
            print("A Raspberry Pi 4 can only handle like 640x360 @ 2 fps when using AV1; not recommended")
    elif args.av1:
        if args.rpi:
            print("A Raspberry Pi 4 can only handle like 640x360 @ 2 fps when using AV1; not recommended")
        if check_plugins(['qsv','videoparsersbad','rsrtp']):
            args.qsv = True
            print("Intel Quick Sync AV1 encoder selected")
        elif check_plugins(['aom','videoparsersbad','rsrtp']):
            args.aom = True
            print("AOM AV1 encoder selected")
        elif check_plugins(['rav1e','videoparsersbad','rsrtp']):
            args.rav1e = True
            print("rav1e AV1 encoder selected; see: https://github.com/xiph/rav1e")
        elif not check_plugins(['videoparsersbad','rsrtp'], True):
            print("You'll probably need to install gst-plugins-rs to use AV1 (av1parse, av1pay)")
            print("ie: https://github.com/steveseguin/raspberry_ninja/blob/6873b97af02f720b9dc2e5c3ae2e9f02d486ba52/raspberry_pi/installer.sh#L347")
            sys.exit()
        else:
            print("No AV1 encoder found")
            sys.exit()

    if args.apple:
        if not check_plugins(['applemedia'], True):
            print("Required media source plugin, applemedia, was not found")
            sys.exit()

        monitor = Gst.DeviceMonitor.new()
        monitor.add_filter("Video/Source", None)
        devices = monitor.get_devices()
        index = -1
        camlook = args.apple.lower()
        appleidx = -1
        appledev = None
        for d in devices:
            index += 1
            cam = d.get_display_name().lower()
            if camlook in cam:
                print("Video device found: "+cam)
                appleidx = index
                appledev = d
                break
        print("")

    elif args.rpi and not args.v4l2 and not args.hdmi and not args.rpicam and not args.z1:
        gst_ver = Gst.version()

        # On older GStreamer builds (notably 1.18), libcamerasrc can be unstable with some
        # USB/UVC capture devices (eg MacroSilicon HDMI dongles). Prefer v4l2src in that case.
        if gst_ver.major == 1 and gst_ver.minor < 20 and not args.libcamera:
            for i in range(10):
                candidate = f"/dev/video{i}"
                if not os.path.exists(candidate) or not os.access(candidate, os.R_OK):
                    continue
                name = None
                try:
                    with open(f"/sys/class/video4linux/video{i}/name", "r", encoding="utf-8") as f:
                        name = f.read().strip()
                except Exception:
                    pass
                if not name:
                    continue
                name_l = name.lower()
                if "uvc" in name_l or "usb vid" in name_l or "macrosilicon" in name_l or "ms2109" in name_l:
                    args.v4l2 = candidate
                    print(f"Auto-selected video device: {candidate} ({name})")
                    break

        if not args.v4l2 and check_plugins(['libcamera']):
            args.libcamera = True

        monitor = Gst.DeviceMonitor.new()
        monitor.add_filter("Video/Source", None)
        devices = monitor.get_devices()
        for d in devices:
            cam = d.get_display_name()
            if "-isp" in cam:
                continue
            print("Video device found: "+d.get_display_name())
        print("")

        camlink = [d for d in devices if "Cam Link" in  d.get_display_name()]

        if len(camlink):
            args.camlink = True

        picam = [d for d in devices if "Raspberry Pi Camera Module" in  d.get_display_name()]

        if len(picam):
            args.rpicam = True

    elif not args.v4l2:
        args.v4l2 = '/dev/video0'

    if args.format:
        args.format = args.format.upper()

    if args.pipeline is not None:
        PIPELINE_DESC = args.pipeline
        print('We assume you have tested your custom pipeline with: gst-launch-1.0 ' + args.pipeline.replace('(', '\\(').replace('(', '\\)'))
    elif args.midi:
        try:
            import rtmidi
        except:
            print("You must install RTMIDI first; pip3 install python-rtmidi")
            sys.exit()
        args.multiviewer = True
        pass
    else:
        # Helper function for queue configuration
        def get_queue_config(lowlatency=False):
            """Return queue configuration based on latency mode"""
            if lowlatency:
                # Low latency configuration with minimal buffering
                # Only buffer 2 frames to reduce latency
                return "queue max-size-buffers=2"
            else:
                return "queue max-size-buffers=10"
        
        pipeline_video_input = ''
        pipeline_audio_input = ''

        if args.bt601:
            args.raw = True

        if args.zerolatency:
            args.novideo = True

        if args.nvidia or args.rpi or args.x264 or args.openh264 or args.omx or args.apple:
            args.h264 = True

        if args.vp8:
            args.h264 = False

        if args.av1:
            args.h264 = False
            
        if args.rtmp and not args.h264:
            args.h264 = True
            
        if args.hevc:
            args.h265 = True

        if args.x265:
            args.h265 = True

        h264 = None
        if args.omx and check_plugins('omxh264enc'):
            h264 = 'omxh264enc'
        if args.omx and check_plugins('avenc_h264_omx'):
            h264 = 'avenc_h264_omx'
        elif args.x264 and check_plugins('x264enc'):
            h264 = 'x264enc'
        elif args.openh264 and check_plugins('openh264enc'):
            h264 = 'openh264enc'
        elif args.apple and check_plugins('vtenc_h264_hw'):
            h264 = 'vtenc_h264_hw'
        elif args.h264:
            if check_plugins('v4l2h264enc'):
                h264 = 'v4l2h264enc'
            elif check_plugins('mpph264enc'):
                h264 = 'mpph264enc'
            elif check_plugins('vtenc_h264_hw'):
                h264 = 'vtenc_h264_hw'
            elif check_plugins('omxh264enc'):
                h264 = 'omxh264enc'
            elif check_plugins('x264enc'):
                h264 = 'x264enc'
            elif check_plugins('openh264enc'):
                h264 = 'openh264enc'
            elif check_plugins('avenc_h264_omx'):
                h264 = 'avenc_h264_omx'
            else:
                print("Couldn't find an h264 encoder")
        elif args.omx or args.x264 or args.openh264 or args.h264:
            print("Couldn't find the h264 encoder")
            
        if h264:
            print("H264 encoder that we will try to use: "+h264)
       
        h265 = None
        if args.h265:
            if args.x265 and check_plugins('x265enc'):
                h265 = 'x265enc'
            elif check_plugins('mpph265enc'):
                h265 = 'mpph265enc'
            elif check_plugins('x265enc'):
                h265 = 'x265enc'
            else:
                print("Couldn't find an h265 encoder, falling back to h264")
                args.h264 = True  # Fallback to h264 if no h265 encoder found
            
            if h265:
                print("H265 encoder that we will try to use: "+h265)
                
        if args.hdmi:
            args.alsa = 'hw:MS2109'
            
            # Better detection - scan all devices and check capabilities
            monitor = Gst.DeviceMonitor.new()
            monitor.add_filter("Video/Source", None)
            devices = monitor.get_devices()
            hdmi_device = None
            
            print("Scanning for HDMI capture devices...")
            for d in devices:
                device_name = d.get_display_name()
                props = d.get_properties()
                
                # Skip devices with no properties
                if not props:
                    continue
                    
                # Get the path if available
                path = None
                if props.has_field('device.path'):
                    path = props.get_string('device.path')
                else:
                    continue  # Skip devices without a path
                    
                # Check for HDMI devices by various indicators
                if ('MACROSILICON' in device_name or 
                    'MS2109' in device_name or 
                    (props.has_field('device.vendor.name') and 'MACROSILICON' in props.get_string('device.vendor.name')) or
                    (props.has_field('device.serial') and 'MACROSILICON' in props.get_string('device.serial'))):
                    
                    # Verify it's a capture device by checking caps
                    caps = d.get_caps()
                    if caps and caps.to_string() and ('image/jpeg' in caps.to_string() or 'video/x-raw' in caps.to_string()):
                        hdmi_device = d
                        args.v4l2 = path
                        print(f"Found HDMI capture device: {device_name} at {path}")
                        break
                    
            if not hdmi_device:
                print("No MACROSILICON HDMI capture device found. Trying alternative detection method...")
                # Try to find by checking all video devices
                for i in range(20):  # Check video0 through video19
                    device_path = f"/dev/video{i}"
                    if os.path.exists(device_path):
                        # Test if this device works with v4l2-ctl
                        try:
                            result = subprocess.run(['v4l2-ctl', '-d', device_path, '--list-formats-ext'], 
                                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
                            if result.returncode == 0 and ('JPEG' in result.stdout or 'MJPG' in result.stdout):
                                args.v4l2 = device_path
                                print(f"Found potential HDMI device: {device_path}")
                                break
                        except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                            continue
                
                if not args.v4l2:
                    print("No usable video devices found!")
                    sys.exit(1)
                    
            if args.raw:
                args.width = 1280
                args.height = 720
                args.framerate = 10

        if args.camlink:
            # Better Camlink detection - similar approach
            monitor = Gst.DeviceMonitor.new()
            monitor.add_filter("Video/Source", None)
            devices = monitor.get_devices()
            camlink_device = None
            
            print("Scanning for Cam Link devices...")
            for d in devices:
                device_name = d.get_display_name()
                props = d.get_properties()
                
                # Skip devices with no properties
                if not props:
                    continue
                    
                # Get the path if available
                path = None
                if props.has_field('device.path'):
                    path = props.get_string('device.path')
                else:
                    continue  # Skip devices without a path
                    
                # Check for Cam Link devices
                if ('Cam Link' in device_name or 
                    'Elgato' in device_name or 
                    (props.has_field('device.vendor.name') and 'Elgato' in props.get_string('device.vendor.name'))):
                    
                    # Verify it's a capture device by checking caps
                    caps = d.get_caps()
                    if caps and caps.to_string() and ('image/jpeg' in caps.to_string() or 'video/x-raw' in caps.to_string()):
                        camlink_device = d
                        args.v4l2 = path
                        print(f"Found Cam Link device: {device_name} at {path}")
                        break
                    
            if not camlink_device:
                print("No specific Cam Link device found. Checking all video devices...")
                # Try to find by checking all video devices
                for i in range(10):  # Check video0 through video9
                    device_path = f"/dev/video{i}"
                    if os.path.exists(device_path):
                        try:
                            result = subprocess.run(['v4l2-ctl', '-d', device_path, '--list-formats-ext'], 
                                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
                            if result.returncode == 0:
                                args.v4l2 = device_path
                                print(f"Using device: {device_path}")
                                break
                        except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                            continue
                
                if not args.v4l2:
                    args.v4l2 = '/dev/video0'
                    print(f"Falling back to default: {args.v4l2}")

        if args.save:
            args.multiviewer = True

        saveAudio = ""
        saveVideo = ""
        if args.save:
            saveAudio = ' ! tee name=saveaudiotee ! queue ! mux.audio_0 saveaudiotee.'
            saveVideo = ' ! tee name=savevideotee ! queue ! mux.video_0 savevideotee.'

        if not args.novideo:

            if args.rpicam:
                needed += ['rpicamsrc']
            elif args.nvidia:
                needed += ['omx', 'nvvidconv']
                if not args.raw:
                    needed += ['nvjpeg']
            elif args.rpi and not args.rpicam:
                needed += ['video4linux2']
                if not args.raw:
                    needed += ['jpeg']

            if args.streamin:
                pass
            elif args.video_pipeline:
                pipeline_video_input = args.video_pipeline
            elif args.test:
                needed += ['videotestsrc']
                pipeline_video_input = 'videotestsrc'
                if args.nvidia:
                    pipeline_video_input = f'videotestsrc ! video/x-raw,width=(int){args.width},height=(int){args.height},format=(string){args.format or "NV12"},framerate=(fraction){args.framerate}/1'
                else:
                    pipeline_video_input = f'videotestsrc ! video/x-raw,width=(int){args.width},height=(int){args.height},type=video,framerate=(fraction){args.framerate}/1'
            elif args.filesrc:
                pipeline_video_input = f'filesrc location="{args.filesrc}" ! decodebin'
            elif args.filesrc2:
                if args.vp9:
                    pipeline_video_input = f'filesrc location="{args.filesrc2}" ! matroskademux ! rtpvp9pay'
                elif args.vp8:
                    pipeline_video_input = f'filesrc location="{args.filesrc2}" ! matroskademux ! rtpvp8pay'
                else:
                    pipeline_video_input = f'filesrc location="{args.filesrc2}" ! qtdemux ! h264parse ! rtph264pay'
            elif args.z1:
                needed += ['thetauvc']
                if args.width>1920 or args.height>960:
                    pipeline_video_input = f'thetauvcsrc mode=4K ! queue ! h264parse ! decodebin'
                else:
                    pipeline_video_input = f'thetauvcsrc mode=2K ! queue ! h264parse ! decodebin'
            elif args.z1passthru:
                needed += ['thetauvc']
                if args.width>1920 or args.height>960:
                    pipeline_video_input = f'thetauvcsrc mode=4K ! queue ! h264parse ! rtph264pay config-interval=-1 aggregate-mode=zero-latency ! application/x-rtp,media=video,encoding-name=H264,payload=96'
                else:
                    pipeline_video_input = f'thetauvcsrc mode=2K ! queue ! h264parse ! rtph264pay config-interval=-1 aggregate-mode=zero-latency ! application/x-rtp,media=video,encoding-name=H264,payload=96'
            elif args.pipein:
                if args.pipein=="auto":
                    pipeline_video_input = f'fdsrc ! decodebin name=ts ts.'
                elif args.pipein=="raw":
                    pipeline_video_input = f'fdsrc ! video/x-raw,format={args.format or "NV12"}'
                elif args.pipein=="vp9":
                    pipeline_video_input = f'fdsrc ! matroskademux ! rtpvp9pay'
                elif args.pipein=="vp8":
                    pipeline_video_input = f'fdsrc ! matroskademux ! rtpvp8pay'
                elif args.pipein=="h264":
                    pipeline_video_input = f'fdsrc  ! h264parse ! rtph264pay config-interval=-1 aggregate-mode=zero-latency ! application/x-rtp,media=video,encoding-name=H264,payload=96'
                elif args.pipein=="mpegts":
                    pipeline_video_input = f'fdsrc ! tsdemux name=ts ts. ! h264parse ! rtph264pay config-interval=-1 aggregate-mode=zero-latency ! application/x-rtp,media=video,encoding-name=H264,payload=96'

                else:
                    pipeline_video_input = f'fdsrc ! decodebin'
            elif args.camlink:
                needed += ['video4linux2']
                if args.rpi:
                    pipeline_video_input = f'v4l2src device={args.v4l2} io-mode={str(args.iomode)} ! videorate max-rate=30 ! capssetter caps="video/x-raw,format={args.format or "YUY2"},colorimetry=(string)2:4:5:4"'
                else:
                    pipeline_video_input = f'v4l2src device={args.v4l2} io-mode={str(args.iomode)} ! capssetter caps="video/x-raw,format={args.format or "YUY2"},colorimetry=(string)2:4:5:4"'

            elif args.rpicam:
                needed += ['rpicamsrc']
                args.rpi = True

                rotate = ""
                if args.rotate:
                    rotate = " rotation="+str(int(args.rotate))
                    args.rotate = 0
                pipeline_video_input = f'rpicamsrc bitrate={args.bitrate}000{rotate} ! video/x-h264,profile=constrained-baseline,width={args.width},height={args.height},framerate=(fraction){args.framerate}/1,level=3.0 ! queue max-size-time=1000000000  max-size-bytes=10000000000 max-size-buffers=1000000 '

            elif args.nvidiacsi:
                needed += ['nvarguscamerasrc']
                args.nvidia = True
                pipeline_video_input = f'nvarguscamerasrc ! video/x-raw(memory:NVMM),width=(int){args.width},height=(int){args.height},format=(string){args.format or "NV12"},framerate=(fraction){args.framerate}/1'
            elif args.apple:
                needed += ['applemedia']
                pipeline_video_input = f'avfvideosrc device-index={appleidx} do-timestamp=true ! video/x-raw'

                if appledev and (args.format is None):
                    formats = supports_resolution_and_format(appledev, args.width, args.height, args.framerate)
                    print(formats)
            elif args.libcamera:

                print("Detecting video devices")
                video_monitor = Gst.DeviceMonitor.new()
                video_monitor.add_filter("Video/Source", None)
                videodevices = video_monitor.get_devices()
                print("devices", videodevices)

                if len(videodevices) > 0:
                    print("\nDetected video sources:")
                    for device in videodevices:
                        print("Device Name:", device.get_display_name())
                    if args.format is None:
                        formats = supports_resolution_and_format(videodevices[0], args.width, args.height, args.framerate)
                        print(formats)
                        if len(formats):
                            args.format = formats[0]
                        elif args.aom:
                            args.format = "I420"
                        else:
                            args.format = "UYVY"

                    print(f"\n >> Default video device selected : {videodevices[0]} /w  {args.format}")

                    needed += ['libcamera']
                    pipeline_video_input = f'libcamerasrc'

                    if args.format == "JPEG":
                        # Check if on Raspberry Pi and recommend --rpi flag
                        if not args.rpi and get_raspberry_pi_model() is not None:
                            printc("Tip: You're on a Raspberry Pi. Using --rpi flag can improve JPEG decoding performance and reduce errors.", "7F7")
                        pipeline_video_input += f' ! image/jpeg,width=(int){args.width},height=(int){args.height},type=video,framerate=(fraction){args.framerate}/1'
                        # Add queue before decoder to handle bursty/corrupted frames from USB adapters
                        if args.nvidia:
                            pipeline_video_input += ' ! queue ! jpegparse ! nvjpegdec ! video/x-raw'
                        elif args.rpi:
                            pipeline_video_input += ' ! queue ! jpegparse ! v4l2jpegdec '
                        else:
                            # Add jpegparse for better error handling of corrupted JPEG frames
                            pipeline_video_input += ' ! queue ! jpegparse ! jpegdec'

                    elif args.format == "H264": # Not going to try to support this right now
                        print("Not support h264 at the moment as an input")
                        pipeline_video_input += f' ! video/x-raw,width=(int){args.width},height=(int){args.height},format=(string){args.format or "YUY2"},framerate=(fraction){args.framerate}/1'
                    else:
                        pipeline_video_input += f' ! video/x-raw,width=(int){args.width},height=(int){args.height},format=(string){args.format},framerate=(fraction){args.framerate}/1'

                elif len(videodevices) == 0:
                    args.novideo = True
                    print("\nNo camera or video source found; disabling video.")

            elif args.v4l2:
                needed += ['video4linux2']
                
                if not os.path.exists(args.v4l2):
                    print(f"The video input {args.v4l2} does not exist.")
                    error = True
                elif not os.access(args.v4l2, os.R_OK):
                    print(f"The video input {args.v4l2} exists, but no permissions to read.")
                    error = True
                
                # Legacy Raspberry Pi (GStreamer < 1.20) USB/UVC capture quirks
                #
                # - Some MacroSilicon/MS2109 HDMI dongles produce MJPEG streams that v4l2jpegdec
                #   fails to decode reliably, while jpegdec succeeds.
                # - The device also supports only discrete capture sizes; requesting an unsupported
                #   size results in "not-negotiated (-4)" from v4l2src.
                #
                # Prefer resiliency over acceleration for these older stacks, while keeping
                # modern GStreamer behavior unchanged.
                if args.rpi and not error:
                    gst_ver = Gst.version()
                    if gst_ver.major == 1 and gst_ver.minor < 20:
                        v4l2_device_name = None
                        try:
                            video_node = os.path.basename(args.v4l2)
                            with open(f"/sys/class/video4linux/{video_node}/name", "r", encoding="utf-8") as f:
                                v4l2_device_name = f.read().strip()
                        except Exception:
                            pass

                        if v4l2_device_name:
                            v4l2_device_name_l = v4l2_device_name.lower()
                            is_macrosilicon = (
                                ("macrosilicon" in v4l2_device_name_l)
                                or ("ms2109" in v4l2_device_name_l)
                                or (re.search(r"\((?:345f|534d):2109\)", v4l2_device_name_l) is not None)
                            )

                            # Default to software JPEG decoding for known-problematic dongles.
                            if is_macrosilicon and (not args.raw) and (not args.soft_jpeg):
                                args.soft_jpeg = True
                                printc("Auto-enabled --soft-jpeg for MacroSilicon/MS2109 capture device (GStreamer < 1.20)", "FA0")

                            # If the requested MJPEG capture size isn't supported, choose the nearest.
                            if is_macrosilicon and (not args.raw):
                                try:
                                    result = subprocess.run(
                                        ['v4l2-ctl', '-d', args.v4l2, '--list-formats-ext'],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True,
                                        timeout=2,
                                    )
                                except (subprocess.SubprocessError, subprocess.TimeoutExpired, FileNotFoundError):
                                    result = None

                                if result and result.returncode == 0:
                                    current_format = None
                                    sizes = set()
                                    for line in result.stdout.splitlines():
                                        m = re.match(r"\s*\[\d+\]:\s*'(\w+)'", line)
                                        if m:
                                            current_format = m.group(1)
                                            continue
                                        m = re.match(r"\s*Size:\s*Discrete\s*(\d+)x(\d+)", line)
                                        if m and current_format == "MJPG":
                                            sizes.add((int(m.group(1)), int(m.group(2))))

                                    if sizes and (args.width, args.height) not in sizes:
                                        target_ratio = (args.width / args.height) if args.height else 0.0
                                        target_area = args.width * args.height

                                        def _score(size):
                                            w, h = size
                                            ratio = (w / h) if h else 0.0
                                            return (abs(ratio - target_ratio), abs((w * h) - target_area))

                                        best_w, best_h = min(sizes, key=_score)
                                        printc(
                                            f"Requested {args.width}x{args.height} not supported by {args.v4l2} ({v4l2_device_name}); using {best_w}x{best_h}",
                                            "FA0",
                                        )
                                        args.width, args.height = best_w, best_h

                if error:
                    pipeline_video_input = f'v4l2src device={args.v4l2} io-mode={str(args.iomode)}'
                    pipeline_video_converter = ""  # Add this line
                elif args.raw:
                    # Determine encoder type based on arguments
                    encoder_type = "auto"
                    if args.h264 or args.x264 or args.openh264 or args.nvidia or args.rpi or args.h265 or args.hevc or args.x265:
                        encoder_type = "h264"
                    elif args.vp8 or args.vp9:
                        encoder_type = "vp8"
                    elif args.aom or args.av1 or args.rav1e or args.qsv:
                        encoder_type = "av1"
                    
                    # Get optimized pipeline sections
                    try:
                        input_section, converter_section, best_format = optimize_pipeline_for_device(
                            args.v4l2, args.width, args.height, args.framerate, args.iomode, args.format, encoder_type
                        )
                        
                        if input_section and best_format:
                            pipeline_video_input = input_section
                            pipeline_video_converter = converter_section  # Fixed assignment here
                            
                            # Store selected format for later use in encoder selection
                            args.format = best_format
                            
                            # If we need to add a timestamp/clockstamp overlay, do it after conversion
                            if timestampOverlay and converter_section:
                                pipeline_video_converter += timestampOverlay
                        else:
                            # Fallback if optimization failed
                            print("Format detection failed, using default pipeline")
                            pipeline_video_input = f'v4l2src device={args.v4l2} io-mode={str(args.iomode)} ! video/x-raw,width=(int){args.width},height=(int){args.height},framerate=(fraction){args.framerate}/1'
                            pipeline_video_converter = f' ! videoconvert{timestampOverlay} ! video/x-raw,format={args.format or "NV12"}'
                    except Exception as e:
                        print(f"Error during pipeline optimization: {e}")
                        # Fallback with generic pipeline
                        pipeline_video_input = f'v4l2src device={args.v4l2} io-mode={str(args.iomode)} ! video/x-raw,width=(int){args.width},height=(int){args.height},framerate=(fraction){args.framerate}/1'
                        pipeline_video_converter = f' ! videoconvert{timestampOverlay} ! video/x-raw,format={args.format or "NV12"}'
                else:
                    # Non-raw mode (JPEG capture)
                    pipeline_video_input = f'v4l2src device={args.v4l2} io-mode={str(args.iomode)} ! image/jpeg,width=(int){args.width},height=(int){args.height},framerate=(fraction){args.framerate}/1'
                    pipeline_video_converter = ""  # Add this line
                    if args.nvidia:
                        pipeline_video_input += ' ! jpegparse ! nvjpegdec ! video/x-raw'
                    elif args.rpi:
                        if args.soft_jpeg:
                             # Force software decoding
                             pipeline_video_input += ' ! jpegparse ! jpegdec'
                        else:
                             # Try hardware first
                             pipeline_video_input += ' ! jpegparse ! ' + ('v4l2jpegdec' if check_plugins('v4l2jpegdec') else 'jpegdec') + ' '
                    else:
                        # Add jpegparse for better error handling of corrupted JPEG frames
                        pipeline_video_input += ' ! jpegparse ! jpegdec'

            if args.filesrc2:
                pass
            elif args.z1passthru:
                pass
            elif args.pipein and args.pipein != "auto" and args.pipein != "raw": # We are doing a pass-thru with this pip # We are doing a pass-thru with this pipee
                pass
            elif args.h264:
                print("h264 preferred codec is ", h264)
                if h264 == "vtenc_h264_hw":
                    pipeline_video_input += f'{pipeline_video_converter} ! autovideoconvert ! vtenc_h264_hw name="encoder" qos=true bitrate={args.bitrate}realtime=true allow-frame-reordering=false ! video/x-h264'
                elif args.nvidia:
                    pipeline_video_input += f'{pipeline_video_converter} ! nvvidconv ! video/x-raw(memory:NVMM) ! omxh264enc bitrate={args.bitrate}000 control-rate="constant" name="encoder" qos=true ! video/x-h264,stream-format=(string)byte-stream'
                elif args.rpicam:
                    pass
                elif h264 == "mpph264enc" and check_plugins('rockchipmpp'):
                    # For Rockchip MPP encoder, ensure we have NV12 input
                    # The pipeline_video_converter should handle this if needed
                    pipeline_video_input += f'{pipeline_video_converter} ! queue max-size-buffers=4 leaky=upstream ! {h264} qp-init=26 qp-min=10 qp-max=51 gop=30 name="encoder" rc-mode=cbr bps={args.bitrate * 1000} ! video/x-h264,stream-format=(string)byte-stream'
               
                elif h264 == "omxh264enc" and args.rpi and get_raspberry_pi_model() != 5:
                    pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420{timestampOverlay} ! omxh264enc name="encoder" target-bitrate={args.bitrate}000 qos=true control-rate="constant" ! video/x-h264,stream-format=(string)byte-stream' ## Good for a RPI Zero I guess?
                elif h264 == "x264enc" and args.rpi:
                    pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420{timestampOverlay} ! queue max-size-buffers=10 ! x264enc  name="encoder1" bitrate={args.bitrate} speed-preset=1 tune=zerolatency qos=true ! video/x-h264,profile=constrained-baseline,stream-format=(string)byte-stream'
                elif h264 == "openh264enc" and args.rpi:
                    pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420{timestampOverlay} ! queue max-size-buffers=10 ! openh264enc  name="encoder" bitrate={args.bitrate}000 complexity=0 ! video/x-h264,profile=constrained-baseline,stream-format=(string)byte-stream'
                elif check_plugins("v4l2h264enc") and args.rpi and get_raspberry_pi_model() != 5:
                    if args.format in ["I420", "YV12", "NV12", "NV21", "RGB16", "RGB", "BGR", "RGBA", "BGRx", "BGRA", "YUY2", "YVYU", "UYVY"]:
                        pipeline_video_input += f' ! v4l2convert ! videorate ! video/x-raw{timestampOverlay} ! v4l2h264enc extra-controls="controls,video_bitrate={args.bitrate}000;" qos=true name="encoder2" ! video/x-h264,level=(string)4'
                    else:
                        pipeline_video_input += f' ! v4l2convert ! videorate ! video/x-raw,format=I420{timestampOverlay} ! v4l2h264enc extra-controls="controls,video_bitrate={args.bitrate}000;" qos=true name="encoder2" ! video/x-h264,level=(string)4' ## v4l2h264enc only supports 30fps max @ 1080p on most rpis, and there might be a spike or skipped frame causing the encode to fail; videorating it seems to fix it though
                elif h264=="mpph264enc":
                    pipeline_video_input += f' ! videoconvert{timestampOverlay} ! videorate max-rate=30 ! {h264} rc-mode=cbr gop=30 profile=high name="encoder" bps={args.bitrate * 1000} ! video/x-h264,stream-format=(string)byte-stream'
                elif h264=="x264enc":
                    pipeline_video_input += f' ! videoconvert{timestampOverlay} ! queue max-size-buffers=10 ! x264enc bitrate={args.bitrate} name="encoder1" speed-preset=1 tune=zerolatency key-int-max=60 qos=true ! video/x-h264,profile=constrained-baseline,stream-format=(string)byte-stream'
                elif h264=="avenc_h264_omx":
                    pipeline_video_input += f' ! videoconvert{timestampOverlay} ! queue max-size-buffers=10 ! avenc_h264_omx bitrate={args.bitrate}000 name="encoder" ! video/x-h264,profile=constrained-baseline'
                elif check_plugins("v4l2convert") and check_plugins("omxh264enc") and get_raspberry_pi_model() != 5:
                    pipeline_video_input += f' ! v4l2convert{timestampOverlay} ! video/x-raw,format=I420 ! omxh264enc name="encoder" target-bitrate={args.bitrate}000 qos=true control-rate=1 ! video/x-h264,stream-format=(string)byte-stream' ## Good for a RPI Zero I guess?
                elif check_plugins("v4l2convert"):
                    if h264 == "v4l2h264enc":
                        pipeline_video_input += f' ! v4l2convert{timestampOverlay} ! video/x-raw,format=I420 ! v4l2h264enc extra-controls="controls,video_bitrate={args.bitrate}000;" qos=true name="encoder2" ! video/x-h264,level=(string)4'
                    else:
                        pipeline_video_input += f' ! v4l2convert{timestampOverlay} ! video/x-raw,format=I420 ! {h264} name="encoder" bitrate={args.bitrate}000 ! video/x-h264,stream-format=(string)byte-stream' ## Good for a RPI Zero I guess?
                else:
                    if h264 == "v4l2h264enc":
                        pipeline_video_input += f' ! videoconvert{timestampOverlay} ! video/x-raw,format=I420 ! v4l2h264enc extra-controls="controls,video_bitrate={args.bitrate}000;" qos=true name="encoder2" ! video/x-h264,level=(string)4'
                    else:
                        pipeline_video_input += f' ! videoconvert{timestampOverlay} ! video/x-raw,format=I420 ! {h264} name="encoder" bitrate={args.bitrate}000 ! video/x-h264,stream-format=(string)byte-stream' ## Good for a RPI Zero I guess?
                    
                if args.rtmp:
                    pipeline_video_input += f' ! queue ! h264parse'
                else:
                    pipeline_video_input += f' ! queue max-size-time=1000000000  max-size-bytes=10000000000 max-size-buffers=1000000 ! h264parse {saveVideo} ! rtph264pay config-interval=-1 aggregate-mode=zero-latency ! application/x-rtp,media=video,encoding-name=H264,payload=96'

            elif args.aom:
                pipeline_video_input += f' ! videoconvert{timestampOverlay} ! av1enc cpu-used=8 target-bitrate={args.bitrate} name="encoder" usage-profile=realtime qos=true ! av1parse ! rtpav1pay'
            elif args.rav1e:
                pipeline_video_input += f' ! videoconvert{timestampOverlay} ! rav1enc bitrate={args.bitrate}000 name="encoder" low-latency=true error-resilient=true speed-preset=10 qos=true ! av1parse ! rtpav1pay'
            elif args.qsv:
                pipeline_video_input += f' ! videoconvert{timestampOverlay} ! qsvav1enc gop-size=60 bitrate={args.bitrate} name="encoder1" ! av1parse ! rtpav1pay'
            elif args.h265 and h265:
                if h265 == "mpph265enc":
                    # mpph265enc uses bps (bits per second) instead of bitrate
                    # bps takes value in bits per second, so multiply bitrate (kbps) by 1000
                   pipeline_video_input += f' ! videoconvert{timestampOverlay} ! {h265} name="encoder" bps={args.bitrate * 1000} qos=true gop=30 header-mode=1 qp-init=30 qp-max=40 qp-min=18 qp-max-i=35 qp-min-i=18 rc-mode=1 ! video/x-h265,stream-format=(string)byte-stream'

                elif h265 == "x265enc":
                    # x265enc uses bitrate in kbps
                    pipeline_video_input += f' ! videoconvert{timestampOverlay} ! queue max-size-buffers=10 ! {h265} bitrate={args.bitrate} speed-preset=superfast tune=zerolatency key-int-max=30 name="encoder" ! video/x-h265,profile=main,stream-format=byte-stream'
                
                if args.rtmp:
                    pipeline_video_input += f' ! queue ! h265parse'
                else:
                    pipeline_video_input += f' ! queue max-size-time=1000000000 max-size-bytes=10000000000 max-size-buffers=1000000 ! h265parse {saveVideo} ! rtph265pay config-interval=-1 ! application/x-rtp,media=video,encoding-name=H265,payload=96'
            else:
                if args.nvidia:
                    pipeline_video_input += f' ! nvvidconv ! video/x-raw(memory:NVMM) ! omxvp8enc bitrate={args.bitrate}000 control-rate="constant" name="encoder" qos=true ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=96'
                elif args.rpi:
                    # Keep normal queue before encoder
                    pipeline_video_input += f' ! v4l2convert{timestampOverlay} ! video/x-raw,format=I420 ! queue max-size-buffers=10 ! vp8enc deadline=1 name="encoder" target-bitrate={args.bitrate}000 {saveVideo} ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=96'
                elif check_plugins('mppvp8enc'):
                    # Rockchip hardware VP8 encoder - ensure NV12 input
                    pipeline_video_input += f'{pipeline_video_converter} ! queue max-size-buffers=4 leaky=upstream ! mppvp8enc qp-init=40 qp-min=10 qp-max=100 gop=30 name="encoder" rc-mode=cbr bps={args.bitrate * 1000} {saveVideo} ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=96'

                else:
                    # Keep normal queue before encoder
                    pipeline_video_input += f' ! videoconvert{timestampOverlay} ! queue max-size-buffers=10 ! vp8enc deadline=1 target-bitrate={args.bitrate}000 name="encoder" {saveVideo} ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=96'

            redundancy_fragment, redundancy_config = build_publisher_redundancy_fragment(args)
            if redundancy_fragment:
                if redundancy_config and not getattr(args, "_publisher_redundancy_noted", False):
                    args._publisher_redundancy_noted = True
                    printc(
                        "   ↺ Enabling publisher RED/ULPFEC "
                        f"(pt={redundancy_config['red_pt']}/{redundancy_config['fec_pt']}, "
                        f"distance={redundancy_config['red_distance']}, "
                        f"FEC={redundancy_config['fec_percentage']}%)",
                        "0AF",
                    )
                pipeline_video_input += redundancy_fragment

            if args.multiviewer:
                pipeline_video_input += ' ! tee name=videotee '
            else:
                if args.lowlatency:
                    # Apply low latency configuration to the final queue
                    pipeline_video_input += ' ! queue max-size-buffers=2 max-size-time=50000000 leaky=upstream ! sendrecv. '
                else:
                    pipeline_video_input += ' ! queue ! sendrecv. '

        # GStreamer 1.18 and earlier don't handle ssrc=-1 properly (passes 0xFFFFFFFF to SDP)
        # Newer versions interpret -1 as "auto-generate", so we only use it on >= 1.20
        gst_major, gst_minor = args.gst_version[0], args.gst_version[1]
        audio_ssrc_param = " ssrc=-1" if (gst_major > 1 or (gst_major == 1 and gst_minor >= 20)) else ""

        if not args.noaudio:
            if args.audio_pipeline:
                pipeline_audio_input = args.audio_pipeline
            elif args.pipein:
                pipeline_audio_input += 'ts. ! queue ! decodebin'
            elif args.test:
                needed += ['audiotestsrc']
                pipeline_audio_input += 'audiotestsrc is-live=true wave=red-noise'

            elif args.pulse:
                needed += ['pulseaudio']
                pipeline_audio_input += f'pulsesrc device={args.pulse}'

            else:
                needed += ['alsa']
                pipeline_audio_input += f'alsasrc device={args.alsa} use-driver-timestamps=TRUE'

            if args.rtmp:
               if check_plugins('fdkaacenc'):
                  pipeline_audio_input += f' ! queue ! audioconvert dithering=0 ! audio/x-raw,rate=48000,channel=1 ! fdkaacenc bitrate=65536 {saveAudio} ! audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 '
               elif check_plugins('voaacenc'):
                  pipeline_audio_input += f' ! queue ! audioconvert dithering=0 ! audio/x-raw,rate=48000,channel=1 ! voaacenc bitrate=65536 {saveAudio} ! audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 '
               elif check_plugins('avenc_aac'):
                  pipeline_audio_input += f' ! queue ! audioconvert dithering=0 ! audio/x-raw,rate=48000,channel=1 ! avenc_aac bitrate=65536 {saveAudio} ! audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 '
               else:
                  pipeline_audio_input = ""
                  printwarn("No AAC encoder found. Will not be encoding audio")
            elif args.zerolatency:
               pipeline_audio_input += f' ! queue max-size-buffers=2 leaky=downstream ! audioconvert ! audioresample quality=0 resample-method=0 ! opusenc bitrate-type=0 bitrate=16000 inband-fec=false audio-type=2051 frame-size=20 {saveAudio} ! rtpopuspay pt=100{audio_ssrc_param} ! application/x-rtp,media=audio,encoding-name=OPUS,payload=100'
            elif args.vorbis:
               pipeline_audio_input += f' ! queue max-size-buffers=3 leaky=downstream ! audioconvert ! audioresample quality=0 resample-method=0 ! vorbisenc bitrate={args.audiobitrate}000 {saveAudio} ! rtpvorbispay pt=100{audio_ssrc_param} ! application/x-rtp,media=audio,encoding-name=VORBIS,payload=100'
            else:
               pipeline_audio_input += f' ! queue ! audioconvert ! audioresample quality=0 resample-method=0 ! opusenc bitrate-type=1 bitrate={args.audiobitrate}000 inband-fec=true {saveAudio} ! rtpopuspay pt=100{audio_ssrc_param} ! application/x-rtp,media=audio,encoding-name=OPUS,payload=100'

            if args.multiviewer: # a 'tee' element may use more CPU or cause extra stuttering, so by default not enabled, but needed to support multiple viewers
                pipeline_audio_input += ' ! tee name=audiotee '
            else:
                pipeline_audio_input += ' ! queue ! sendrecv. '

        pipeline_save = ""
        if args.save:
           pipeline_save = " matroskamux name=mux ! queue ! filesink sync=true location="+str(int(time.time()))+".mkv "

        pipeline_rtmp = ""
        if args.rtmp:
        
            if args.save:
                pipeline_video_input += 'tee name=videotee ! queue ! sendrecv. videotee. ! queue ! '
                saveVideo = f'matroskamux name=mux ! filesink location=saved_video_{int(time.time())}.mkv '

                if not args.noaudio:
                    pipeline_audio_input += 'tee name=audiotee ! queue ! sendrecv. audiotee. ! queue ! mux. '

                
            pipeline_rtmp = "flvmux name=sendrecv ! rtmpsink location='"+args.rtmp+" live=1'"
            PIPELINE_DESC = f'{pipeline_video_input} {pipeline_audio_input} {pipeline_rtmp}'
            print('gst-launch-1.0 ' + PIPELINE_DESC.replace('(', '\\(').replace(')', '\\)'))
            pipe = Gst.parse_launch(PIPELINE_DESC)

            bus = pipe.get_bus()

            bus.add_signal_watch()

            pipe.set_state(Gst.State.PLAYING)

            try:
                loop = GLib.MainLoop()
            except:
                loop = GObject.MainLoop()

            bus.connect("message", on_message, loop)
            try:
                loop.run()
            except:
                loop.quit()

            pipe.set_state(Gst.State.NULL)
            sys.exit(1)
        elif args.whip:
            # Build video and audio pipeline segments
            pipeline_segments = []
            if not args.novideo:
                pipeline_segments.append(pipeline_video_input)
            if not args.noaudio:
                pipeline_segments.append(pipeline_audio_input)
                
            pipeline_desc = ' '.join(pipeline_segments)
            
            whip_client = WHIPClient(pipeline_desc, args)
            if whip_client.start():
                whip_client.stop()
            sys.exit(1)

        elif args.streamin:
            args.h264 = True
            pass
        elif not args.multiviewer:
            if Gst.version().minor >= 18:
                PIPELINE_DESC = f'webrtcbin name=sendrecv latency={args.buffer} async-handling=true bundle-policy=max-bundle {pipeline_video_input} {pipeline_audio_input} {pipeline_save}'
                PIPELINE_DESC = f'webrtcbin name=sendrecv latency={args.buffer} async-handling=true stun-server=stun://stun.cloudflare.com:3478 bundle-policy=max-bundle {pipeline_video_input} {pipeline_audio_input} {pipeline_save}'
            else: ## oldvers v1.16 options  non-advanced options
                PIPELINE_DESC = f'webrtcbin name=sendrecv stun-server=stun://stun.cloudflare.com:3478 bundle-policy=max-bundle {pipeline_video_input} {pipeline_audio_input} {pipeline_save}'
            printc('\ngst-launch-1.0 ' + PIPELINE_DESC.replace('(', '\\(').replace(')', '\\)'), "FFF")
        else:
            PIPELINE_DESC = f'{pipeline_video_input} {pipeline_audio_input} {pipeline_save}'
            printc('\ngst-launch-1.0 ' + PIPELINE_DESC.replace('(', '\\(').replace(')', '\\)'), "FFF")

        if not check_plugins(needed) or error:
            sys.exit(1)

    if args.server:
        server = "&wss="+args.server.split("wss://")[-1]
        args.server = "wss://"+args.server.split("wss://")[-1]
        args.puuid = str(random.randint(10000000,99999999999))
    else:
        args.server = WSS
        server = ""

    if not args.hostname.endswith("/"):
        args.hostname = args.hostname+"/"

    watchURL = args.hostname
    if args.password:
        if args.password == "someEncryptionKey123":
            watchURL += "?"
        else:
            watchURL += "?password="+args.password+"&"
    else:
        watchURL += "?password=false&"

    bold_color = hex_to_ansi("FAF")

    if args.streamin:
        if args.record_room:
            printc(f"\n-> Recording all streams from room: {bold_color}{args.room}", "7FF")
            if args.stream_filter:
                printc(f"   Filter: {', '.join(args.stream_filter)}", "77F")
            printc(f"   Files will be saved as: {args.room}_<streamID>_<timestamp>.ts", "77F")
        elif args.room_ndi:
            if not hasattr(args, 'ndi_combine') or not args.ndi_combine:
                printc(f"\n-> Relaying all streams from room '{args.room}' to NDI (DIRECT MODE)", "0FF")
                printc(f"   ✅ Using direct NDI mode (default) - no freezing issues", "0F0")
                printc(f"   📹 Video streams: {args.room}_<streamID>_video", "77F")
                printc(f"   🔊 Audio streams: {args.room}_<streamID>_audio", "77F")
            else:
                printc(f"\n-> Relaying all streams from room '{args.room}' to NDI (COMBINER MODE)", "FF0")
                printc(f"   ⚠️  WARNING: Combiner mode may freeze after ~1500 buffers!", "F70")
            if args.stream_filter:
                printc(f"   Filter: {', '.join(args.stream_filter)}", "77F")
        elif getattr(args, 'room_monitor', False):
            printc(f"\n👀 Room Monitor Mode (Room: {args.room})", "0AF")
            if args.join_postapi:
                printc(f"   ├─ postapi: {args.join_postapi}", "77F")
            if args.join_webhook:
                printc(f"   ├─ webhook: {args.join_webhook}", "77F")
            if args.join_notify_topic:
                printc(f"   ├─ notify topic: {args.join_notify_topic}", "77F")
            if args.join_gpio_pin is not None:
                level_mode = "active-LOW" if args.join_gpio_active_low else "active-HIGH"
                printc(f"   └─ GPIO pin {args.join_gpio_pin} ({level_mode}, {args.join_gpio_pulse:.2f}s)", "77F")
        elif not args.room:
            printc(f"\n📹 Recording Mode", "0FF")
            printc(f"   └─ Publish to: {bold_color}{watchURL}push={args.streamin}{server}", "77F")
        else:
            printc(f"\n📹 Recording Mode (Room: {args.room})", "0FF")
            printc(f"   └─ Publish to: {bold_color}{watchURL}push={args.streamin}{server}&room={args.room}", "77F")
        if getattr(args, 'room_monitor', False):
            print("\nUse --join-webhook/--join-postapi/--join-notify-topic/--join-gpio-pin for room-join alerts.")
        else:
            print("\nAvailable options include --noaudio, --ndiout, --record and --server. See --help for more options.")
    else:
        print("\nAvailable options include --streamid, --bitrate, and --server. See --help for more options. Default video bitrate is 2500 (kbps)")
        if not args.nored and not args.novideo:
            print("Note: Redundant error correction is enabled (default). This will double the sending video bitrate, but handle packet loss better. Use --nored to disable this.")
        if args.room:
            printc(f"\n📡 Stream Ready!", "0FF")
            printc(f"   └─ View at: {bold_color}{watchURL}view={args.streamid}&room={args.room}&scene{server}\n", "7FF")
        else:
            printc(f"\n📡 Stream Ready!", "0FF")
            printc(f"   └─ View at: {bold_color}{watchURL}view={args.streamid}{server}\n", "7FF")

    args.pipeline = PIPELINE_DESC
    
    # For room recording, use the new subprocess architecture
    if args.record_room and args.room:
        printc("\n🎬 Room Recording Mode (WebRTC Subprocess Architecture)", "0F0")
        printc("   Using single WebSocket connection with subprocess WebRTC handlers", "0F0")
        printc("   This provides proper signaling coordination between streams", "77F")
        
        # Enable room recording mode
        args.room_recording = True
        args.auto_turn = True  # Automatically use default TURN servers for room recording
        args.streamin = False  # Not receiving directly
        args.record = args.record or args.room  # Default prefix
        
        # Continue with normal client creation below
        # The WebRTCClient will handle room recording with subprocess managers
    
    c = WebRTCClient(args)
    
    # Set the event loop reference for thread-safe operations
    c.event_loop = asyncio.get_running_loop()
    
    if args.socketout:
        c.setup_socket()
    
    # Stats display task removed - room recording now uses subprocess approach
    
    # Start web server if requested
    webserver = None
    if hasattr(args, 'webserver') and args.webserver:
        if web is None:
            printc("⚠️  Web server requires aiohttp: pip install aiohttp", "F77")
        else:
            webserver = WebServer(args.webserver, c)
            await webserver.start()
            # Set global reference for logging
            global _webserver_instance
            _webserver_instance = webserver
    
    # Setup signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()
    loop = c.event_loop
    force_exit_handle = [None]

    async def _close_connection():
        conn = c.conn
        if not conn:
            return
        try:
            await conn.close()
        except Exception as exc:
            printwarn(f"Error closing websocket: {exc}")
        finally:
            if c.conn is conn:
                c.conn = None

    async def _sleep_or_shutdown(timeout: float):
        if timeout <= 0:
            return
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    def _schedule_shutdown():
        if not c._shutdown_requested:
            c._shutdown_requested = True

        if loop and loop.is_running():
            loop.call_soon_threadsafe(shutdown_event.set)

            if c.conn:
                def _async_close():
                    if c.conn:
                        asyncio.create_task(_close_connection())
                loop.call_soon_threadsafe(_async_close)
        else:
            shutdown_event.set()

    def _force_exit_due_to_timeout():
        printc("\n❌ Shutdown timeout reached, forcing exit.", "F00")
        os._exit(1)

    # Track if we're already shutting down
    shutdown_count = [0]
    
    def signal_handler(signum, frame):
        shutdown_count[0] += 1
        if shutdown_count[0] == 1:
            printc("\n🛑 Received interrupt signal, shutting down gracefully...", "F70")
            _schedule_shutdown()
            if force_exit_handle[0] is None:
                timer = threading.Timer(8.0, _force_exit_due_to_timeout)
                timer.daemon = True
                timer.start()
                force_exit_handle[0] = timer
        elif shutdown_count[0] == 2:
            printc("\n⚠️  Second interrupt, forcing shutdown...", "F00")
            os._exit(1)
        else:
            printc("\n❌ Force exiting...", "F00")
            os._exit(1)
    
    # Set up signal handlers
    original_sigint = signal.signal(signal.SIGINT, signal_handler)
    original_sigterm = signal.signal(signal.SIGTERM, signal_handler)
    
    # Also handle SIGTSTP (Ctrl+Z) to prevent suspension with camera locked
    def sigtstp_handler(signum, frame):
        printc("\n⚠️  Process suspension (Ctrl+Z) not recommended with active camera!", "F70")
        printc("   Use Ctrl+C for graceful shutdown instead.", "F70")
        # Still allow suspension but warn the user
        signal.signal(signal.SIGTSTP, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTSTP)
    
    signal.signal(signal.SIGTSTP, sigtstp_handler)
    
    # Add shutdown flag to client
    c._shutdown_requested = False
    
    while not c._shutdown_requested:
        try:
            await c.connect()
            res = await c.loop()
        except KeyboardInterrupt:
            printc("\n👋 Shutting down gracefully...", "0FF")
            _schedule_shutdown()
            break
        except Exception as e:
            if c._shutdown_requested:
                break
            printc(f"⚠️  Connection error: {e}", "F77")
            # WebSocket reconnection - peer connections remain active
            await _sleep_or_shutdown(5)
    shutdown_event.set()
    
    # Ensure cleanup is called
    try:
        await asyncio.wait_for(c.cleanup_pipeline(), timeout=10)
    except asyncio.TimeoutError:
        printc("\n❌ Cleanup timed out; forcing exit.", "F00")
        os._exit(1)
    
    # Stop web server if running
    if webserver:
        await webserver.stop()

    # Restore original signal handlers
    signal.signal(signal.SIGINT, original_sigint)
    signal.signal(signal.SIGTERM, original_sigterm)
    if force_exit_handle[0] is not None:
        try:
            force_exit_handle[0].cancel()
        except Exception:
            pass
        force_exit_handle[0] = None
    
    # Cancel stats task if running (if it exists)
    if 'stats_task' in locals() and stats_task:
        stats_task.cancel()
        try:
            await stats_task
        except asyncio.CancelledError:
            pass
    
    # Web server already stopped above
    
    disableLEDs()
    if c.shared_memory:
        c.shared_memory.close()
        c.shared_memory.unlink()
    sys.exit(0)
    return

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        printc("\n🛑 Process interrupted", "F70")
        sys.exit(0)
    except Exception as e:
        printc(f"\n❌ Fatal error: {e}", "F00")
        sys.exit(1)
