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
import mmap
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Set, List
from functools import lru_cache
try:
    import hashlib
    from urllib.parse import urlparse
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
    global LED_Level, P_R
    if level!=False:
        LED_Level = level
    p_R.start(0)      # Initial duty Cycle = 0(leds off)
    p_R.ChangeDutyCycle(LED_Level)     # Change duty cycle

def disableLEDs():
    try:
        GPIO
    except Exception as e:
        return

    global pin, P_R
    p_R.stop()
    GPIO.output(pin, GPIO.HIGH)    # Turn off all leds
    GPIO.cleanup()

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
        if codec_key in {"VP8", "H264"}:
            # enable-max-performance prefers direct NVDEC usage on Jetson
            return "nvv4l2decoder", {"enable-max-performance": True}, True

    return fallback, {}, False


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

    def _apply_loss_recovery_overrides(self, client: Dict[str, Any]) -> bool:
        """Best-effort attempt to enable redundancy on existing transceivers."""
        webrtc = client.get("webrtc")
        if not webrtc:
            return False

        updated = False
        if not self.nored:
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
            if not self.nored:
                current_fec, fec_available = self._get_gst_property_if_available(trans, "do-fec")
                if fec_available and bool(current_fec):
                    pass
                elif self._set_gst_property_if_available(trans, "do-fec", True):
                    updated = True
            current_rtx, rtx_available = self._get_gst_property_if_available(trans, "do-retransmission")
            if rtx_available and bool(current_rtx):
                pass
            elif self._set_gst_property_if_available(trans, "do-retransmission", True):
                updated = True
            index += 1
        return updated

    def __init__(self, params):
        self.params = params  # Store params for room recording manager
        self.pipeline = params.pipeline
        self.conn = None
        self.pipe = None
        self.h264 = params.h264
        self.vp8 = params.vp8
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
        self._viewer_restart_enabled = True
        self._viewer_restart_pending = False
        self._viewer_restart_timer = None
        self._viewer_restart_attempts = 0
        self._viewer_last_play_request = 0.0
        self._viewer_last_disconnect = 0.0
        self._viewer_restart_short_delay = 30.0
        self._viewer_restart_long_delay = 180.0
        self._viewer_pending_idle = False
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
        self._pipeline_bus_watch_installed = False
        self._last_viewer_codec = None
        self._loss_hint_shown = False
        
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
        self.single_stream_recording = getattr(params, 'single_stream_recording', False)
        # NDI direct mode is now the default, use ndi_combine to opt into the problematic combiner
        self.ndi_combine = getattr(params, 'ndi_combine', False)
        self.ndi_direct = not self.ndi_combine  # Direct mode by default
        self.stream_filter = getattr(params, 'stream_filter', None)
        
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

                frame_shape = (720 * 1280 * 3)
                frame_buffer = np.ndarray(frame_shape+5, dtype=np.uint8, buffer=self.shared_memory.buf)
                frame_buffer[5:5+width*height*3] = np_frame_data.flatten(order='K') # K means order as how ordered in memory
                frame_buffer[0] = width/255
                frame_buffer[1] = width%255
                frame_buffer[2] = height/255
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
        if hasattr(self, "_active_hw_decoder_streams"):
            self._active_hw_decoder_streams.clear()

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

    def _on_pipeline_warning(self, bus, message):
        if not self._active_hw_decoder_streams:
            return
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
        if "nvv4l2decoder" in combined_text or "bug in this gstbufferpool subclass" in combined_text:
            self._handle_hw_decoder_warning(str(warning), debug)

    def _on_pipeline_error(self, bus, message):
        if not self._active_hw_decoder_streams:
            return
        try:
            err, debug = message.parse_error()
        except Exception:
            return
        combined = " ".join(filter(None, (str(err), debug))).lower()
        if "nvv4l2decoder" in combined:
            self._handle_hw_decoder_warning(str(err), debug, force_trigger=True)

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
            self._ensure_display_chain()
            if not self.display_remote_map and self.display_state != "idle":
                self._set_display_mode("idle")
        except Exception as exc:
            printwarn(f"Failed to prepare viewer display: {exc}")

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

        outsink = select_display_sink("autovideosink")
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
        short_delay = float(getattr(self, "_viewer_restart_short_delay", 30.0))
        long_delay = float(getattr(self, "_viewer_restart_long_delay", 180.0))
        attempts = int(getattr(self, "_viewer_restart_attempts", 0))
        last_request = float(getattr(self, "_viewer_last_play_request", 0.0))

        if attempts == 0:
            min_gap = 0.0
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

    def _release_display_source(self, label: str):
        """Detach and remove a registered display source."""
        source = self.display_sources.pop(label, None)
        if not source:
            return
        if source.get("using_hw_decoder"):
            self._active_hw_decoder_streams.discard(label)
        print(f"[display] Releasing source '{label}'")

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

        codec_type = None
        caps_upper = caps_name.upper()
        if "VP8" in caps_upper:
            codec_type = "VP8"
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
        elif "H264" in caps_upper:
            codec_type = "H264"
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
        elif "AV1" in caps_upper:
            codec_type = "AV1"
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
            out = Gst.parse_bin_from_description(pipeline_desc, True)
        except Exception as exc:
            printwarn(f"Failed to build viewer video pipeline: {exc}")
            return None

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
            printwarn(f"Failed to link incoming video pad to viewer pipeline: {reason}")
            self.pipe.remove(out)
            return None

        remote_label = f"remote_{pad.get_name()}"
        try:
            self._link_bin_to_display(out, remote_label)
            self.display_remote_map[pad.get_name()] = remote_label
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
        if using_hw_decoder:
            self._active_hw_decoder_streams.add(remote_label)
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

    def on_remote_pad_removed(self, webrtc, pad: Gst.Pad):
        """Handle removal of remote pads for viewer mode."""
        pad_name = pad.get_name()
        remote_map = getattr(self, "display_remote_map", None)
        if remote_map is None:
            print(f"[display] Remote pad removed but display map missing: {pad_name}")
            return

        label = remote_map.pop(pad_name, None)
        print(f"[display] Remote pad removed: {pad_name} -> {label}")
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
            codec_info = ""
            if "encoding-name=" in name:
                codec = name.split("encoding-name=(string)")[1].split(",")[0].split(")")[0]
                codec_info = f" [{codec}]"
            print(f"Incoming stream{codec_info}: {name}")
            
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
                elif self.view and "video" in name.lower():
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
                    frame_shape = (720, 1280, 3)
                    size = np.prod(frame_shape) * 3  # Total size in bytes
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

            if not self.nored:
                try:
                    trans.set_property("fec-type", GstWebRTC.WebRTCFECType.ULP_RED)
                    print(f"FEC ENABLED ({label})")
                except Exception as exc:
                    printwarn(f"Failed to enable FEC on {label}: {exc}")
            force_fec = self.force_red or client.get("_auto_redundancy_active")
            if force_fec:
                if not self._set_gst_property_if_available(trans, "do-fec", True):
                    if self.force_red:
                        printwarn(f"{label}: Unable to force FEC (property unsupported)")
            rtx_supported = False
            force_rtx = self.force_rtx or client.get("_auto_redundancy_active")
            if force_rtx:
                rtx_supported = self._set_gst_property_if_available(trans, "do-retransmission", True)
                if not rtx_supported and self.force_rtx and not self._rtx_support_warned:
                    printwarn(
                        f"{label}: RTX not supported by this GStreamer build; continuing with FEC only. Upgrade to GStreamer 1.24+ to enable retransmissions."
                    )
                    self._rtx_support_warned = True
                elif self.force_rtx and rtx_supported:
                    print(f"RTX ENABLED ({label})")
            try:
                trans.set_property("do-nack", True)
                print(f"SEND NACKS ENABLED ({label})")
            except Exception as exc:
                printwarn(f"Failed to enable NACK on {label}: {exc}")

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
            promise = Gst.Promise.new()
            client['webrtc'].emit('set-local-description', offer, promise)
            promise.interrupt()
            printc("📤 Sending connection offer...", "77F")
            text = offer.sdp.as_text()
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

            if self.novideo and not self.noaudio: # impacts audio and video as well, but chrome / firefox seems to handle it
                printc("Patching SDP due to Gstreamer webRTC bug - audio-only issue", "A6F") # just chrome doesn't handle this
                text = replace_ssrc_and_cleanup_sdp(text)

            if self.view:
                text = self._apply_bitrate_constraints_to_sdp(text, context="outgoing offer")

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
                try:
                    self._ensure_display_chain()
                    self._set_display_mode("idle")
                except Exception as exc:
                    printwarn(f"Display initialization failed: {exc}")
           
            if self.vp8:     
                pass
            elif self.h264:
                direction = GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY
                caps = Gst.caps_from_string("application/x-rtp,media=video,encoding-name=H264,clock-rate=90000,packetization-mode=(string)1")
                tcvr = client['webrtc'].emit('add-transceiver', direction, caps)
                if Gst.version().minor > 18:
                    tcvr.set_property("codec-preferences",caps) ## supported as of around June 2021 in gstreamer for answer side?

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
            # For room recording, we need to be able to map webrtc back to client
            # Use a lambda to pass the client UUID
            client['webrtc'].connect('pad-added', lambda webrtc, pad: self.on_incoming_stream(webrtc, pad))
            client['webrtc'].connect('pad-removed', self.on_remote_pad_removed)
            client['webrtc'].connect('on-ice-candidate', send_ice_remote_candidate_message)
            client['webrtc'].connect('on-data-channel', on_data_channel)
            client['webrtc'].connect('on-new-transceiver', on_new_tranceiver)
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
            try:
                modified_text = self._apply_bitrate_constraints_to_sdp(text, context="outgoing answer")
            except Exception as exc:
                printwarn(f"Failed to apply bitrate constraints to answer SDP: {exc}")
            else:
                if modified_text != text:
                    text = modified_text
                    try:
                        res, sdpmsg = GstSdp.SDPMessage.new()
                        GstSdp.sdp_message_parse_buffer(bytes(text.encode()), sdpmsg)
                        answer = GstWebRTC.WebRTCSessionDescription.new(
                            GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg
                        )
                    except Exception as exc:
                        printwarn(f"Failed to rebuild SDP with bitrate constraints: {exc}")
                        text = answer.sdp.as_text()
                else:
                    text = modified_text
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
            elif self.av1:
                preferred_codec = 'av1'
            elif self.h264:
                preferred_codec = 'h264'
            elif self.use_hls:
                preferred_codec = 'h264'

            if preferred_codec:
                sdp = self.prefer_codec(sdp, preferred_codec)
            
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

            if should_restart and len(self.clients) == 0:
                restart_display = True
                if self.display_remote_map:
                    for label in list(self.display_remote_map.values()):
                        try:
                            self._release_display_source(label)
                        except Exception:
                            pass
                    self.display_remote_map.clear()

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
                        if self.room_recording and UUID in self.room_streams:
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
                            if self.room_recording or self.room_ndi:
                                # This event tells us a new stream is in the room.
                                # Try to get the UUID from various possible fields
                                peer_uuid = msg.get('from') or msg.get('UUID') or UUID
                                if peer_uuid:
                                    printc(f"  UUID found: {peer_uuid}", "77F")
                                    await self.handle_new_room_stream(msg['streamID'], peer_uuid)
                                else:
                                    printc(f"[{msg['streamID']}] ⚠️ videoaddedtoroom event missing peer UUID", "F70")
                                    printc(f"  Message keys: {list(msg.keys())}", "F77")
                            elif self.streamin:
                                printwout("play stream.")
                                await self.sendMessageAsync({"request":"play","streamID":self.streamin+self.hashcode})
                    elif msg['request'] == 'joinroom':
                        if self.room_recording or self.room_ndi:
                            # Handle new member joining when we're recording the room
                            if 'streamID' in msg:
                                printc(f"👤 Member joined room with stream: {msg['streamID']}", "0FF")
                                await self.handle_new_room_stream(msg['streamID'], UUID)
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
                        if (self.room_recording or self.room_ndi) and 'streamID' in msg:
                            printc(f"🆕 Someone joined with stream: {msg['streamID']}", "0FF")
                            await self.handle_new_room_stream(msg['streamID'], UUID)
                            
                            
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
        printc(f"Room recording mode: {self.room_recording}, Room NDI: {self.room_ndi}", "FF0")
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
    
    async def handle_new_room_stream(self, stream_id, uuid):
        """Handle a new stream that has joined the room by starting a recorder for it."""
        if self.stream_filter and stream_id not in self.stream_filter:
            return # Skip streams not in our filter
        
        # The 'uuid' here is the websocket peer ID of the new member. This is crucial.
        if not uuid:
            printc(f"[{stream_id}] ⚠️ New stream joined but had no UUID. Cannot record.", "F70")
            return

        printc(f"New peer '{uuid}' with stream '{stream_id}' joined room.", "7FF")
        
        async with self.room_streams_lock:
            if stream_id in [s['streamID'] for s in self.room_streams.values()]:
                 printc(f"[{stream_id}] ⚠️ Already tracking this stream. Ignoring.", "FF0")
                 return
            self.room_streams[uuid] = {'streamID': stream_id, 'recording': False}
        
        if self.room_recording:
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
    parser.add_argument('--force-rtx', action='store_true', help='Force-enable RTX retransmissions when supported by the local GStreamer build (requires webrtcbin from GStreamer 1.24 or newer).')
    parser.add_argument('--novideo', action='store_true', help='Disables video input.')
    parser.add_argument('--noaudio', action='store_true', help='Disables audio input.')
    parser.add_argument('--led', action='store_true', help='Enable GPIO pin 12 as an LED indicator light; for Raspberry Pi.')
    parser.add_argument('--pipeline', type=str, help='A full custom pipeline')
    parser.add_argument('--record',  type=str, help='Specify a stream ID to record to disk. System will not publish a stream when enabled.')
    parser.add_argument('--view',  type=str, help='Specify a stream ID to play out to the local display/audio.')
    parser.add_argument('--stretch-display', action='store_true', help='Scale viewer output to fill the detected framebuffer/display when possible.')
    parser.add_argument('--splashscreen-idle', type=str, default=None, help='Path to an image displayed when the viewer is idle or no stream is active.')
    parser.add_argument('--splashscreen-connecting', type=str, default=None, help='Path to an image displayed while the viewer is connecting to a stream.')
    parser.add_argument('--disable-hw-decoder', action='store_true', help='Force software decoding for incoming streams even if hardware decoders are available.')
    parser.add_argument('--save', action='store_true', help='Save a copy of the outbound stream to disk. Publish Live + Store the video.')
    parser.add_argument('--record-room', action='store_true', help='Record all streams in a room to separate files. Requires --room parameter.')
    parser.add_argument('--record-streams', type=str, help='Comma-separated list of stream IDs to record from a room. Optional filter for --record-room.')
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
            global LED_Level, P_R, pin
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
        if check_plugins(['libcamera']):
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

        usbcam = [d for d in devices if "USB Vid" in  d.get_display_name()]

        if len(usbcam) and not args.v4l2:
            args.v4l2 = "/dev/video0"

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
                    pipeline_video_input = f'v4l2src device={args.v4l2} io-mode={str(args.iomode)} ! image/jpeg,width=(int){args.width},height=(int){args.height},type=video,framerate=(fraction){args.framerate}/1'
                    pipeline_video_converter = ""  # Add this line
                    if args.nvidia:
                        pipeline_video_input += ' ! jpegparse ! nvjpegdec ! video/x-raw'
                    elif args.rpi:
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

            if args.multiviewer:
                pipeline_video_input += ' ! tee name=videotee '
            else:
                if args.lowlatency:
                    # Apply low latency configuration to the final queue
                    pipeline_video_input += ' ! queue max-size-buffers=2 max-size-time=50000000 leaky=upstream ! sendrecv. '
                else:
                    pipeline_video_input += ' ! queue ! sendrecv. '

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
               pipeline_audio_input += f' ! queue max-size-buffers=2 leaky=downstream ! audioconvert ! audioresample quality=0 resample-method=0 ! opusenc bitrate-type=0 bitrate=16000 inband-fec=false audio-type=2051 frame-size=20 {saveAudio} ! rtpopuspay pt=100 ssrc=-1 ! application/x-rtp,media=audio,encoding-name=OPUS,payload=100'
            elif args.vorbis:
               pipeline_audio_input += f' ! queue max-size-buffers=3 leaky=downstream ! audioconvert ! audioresample quality=0 resample-method=0 ! vorbisenc bitrate={args.audiobitrate}000 {saveAudio} ! rtpvorbispay pt=100 ssrc=-1 ! application/x-rtp,media=audio,encoding-name=VORBIS,payload=100'
            else:
               pipeline_audio_input += f' ! queue ! audioconvert ! audioresample quality=0 resample-method=0 ! opusenc bitrate-type=1 bitrate={args.audiobitrate}000 inband-fec=true {saveAudio} ! rtpopuspay pt=100 ssrc=-1 ! application/x-rtp,media=audio,encoding-name=OPUS,payload=100'

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
        elif not args.room:
            printc(f"\n📹 Recording Mode", "0FF")
            printc(f"   └─ Publish to: {bold_color}{watchURL}push={args.streamin}{server}", "77F")
        else:
            printc(f"\n📹 Recording Mode (Room: {args.room})", "0FF")
            printc(f"   └─ Publish to: {bold_color}{watchURL}push={args.streamin}{server}&room={args.room}", "77F")
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
