import random
import ssl
import websockets
import asyncio
import os
import sys
import json
import argparse
import time
import gi
import threading
import socket
import re
import traceback
import subprocess
import struct
import glob
import signal
from pathlib import Path
from typing import Dict, Any, Optional
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

# Import room recording manager for multi-stream support
try:
    from room_recording_manager import RoomRecordingManager
except ImportError:
    RoomRecordingManager = None
    print("Warning: RoomRecordingManager not available. Room recording will use fallback mode.")

try:
    from gi.repository import GLib
except ImportError:
    pass
    
#os.environ['GST_DEBUG'] = '3,ndisink:7,videorate:5,videoscale:5,videoconvert:5'

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
def check_drm_displays():
    try:
        result = subprocess.run(['drm_info'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            output = result.stdout.strip()
            drm_info = json.loads(output)
            connected_displays = [connector for connector in drm_info['connectors'] if connector['status'] == 'connected']
            if connected_displays:
                print("Display(s) connected:")
                for display in connected_displays:
                    print(display)
                return True
            else:
                print("No display connected.")
                return False
        else:
            print(f"Error running drm_info: {result.stderr}")
            return False
    except Exception as e:
        print(f"Exception occurred: {e}")
        return False

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
                
                <div id="modalContainer"></div>
                
                <h2>Live Logs</h2>
                <div class="logs" id="logs"></div>
            </div>
            
            <script>
                let ws;
                
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
                    delete stats.viewer_details;
                    
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
                fetchSystemStats();
            </script>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
    
    async def get_stats(self, request):
        stats = {
            'status': 'connected' if len(self.client.clients) > 0 else 'idle',
            'viewers': len(self.client.clients),
            'bitrate': f"{self.client.bitrate} kbps",
            'max_bitrate': f"{self.client.max_bitrate} kbps",
            'stream_id': self.client.stream_id or 'N/A',
            'room': self.client.room_name or 'N/A',
            'multiviewer': 'enabled' if self.client.multiviewer else 'disabled',
            'pipeline_state': 'active' if self.client.pipe else 'inactive',
            'recording': 'active' if self.client.record else 'inactive',
            'audio': 'disabled' if self.client.noaudio else 'enabled',
            'video': 'disabled' if self.client.novideo else 'enabled'
        }
        
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
            'bitrate': self.config.get('bitrate', 2500),
        }
        
        # Start subprocess
        script_dir = os.path.dirname(os.path.abspath(__file__))
        subprocess_script = os.path.join(script_dir, 'webrtc_subprocess.py')
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
        
        # Cancel reader task
        if self.reader_task:
            self.reader_task.cancel()
            try:
                await self.reader_task
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
        self.room_name = params.room
        self.room_hashcode = None
        self.multiviewer = params.multiviewer
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
        self.counter = 0
        self.shared_memory = False
        self.trigger_socket = False
        self.processing = False
        self.buffer = params.buffer
        self.password = params.password
        self.hostname = params.hostname
        self.hashcode = ""
        self.salt = ""
        self.aom = params.aom
        self.av1 = params.av1
        self.socketout = params.socketout
        self.socketport = params.socketport
        self.socket = None
        
        # ICE/TURN configuration
        self.stun_server = getattr(params, 'stun_server', None)
        self.turn_server = getattr(params, 'turn_server', None)
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
        self.stream_filter = getattr(params, 'stream_filter', None)
        
        # Subprocess managers for room recording
        self.subprocess_managers = {}  # stream_id -> WebRTCSubprocessManager
        self.room_streams = {}  # Track room streams
        self.room_streams_lock = asyncio.Lock()
        self.stream_id_to_uuid = {}  # Map stream_id to UUID for subprocess routing
        self.session_to_stream = {}  # Map session to stream_id for subprocess routing
        
        # Enable multiviewer when room NDI is active
        if self.room_ndi:
            self.multiviewer = True
        
        # Multi-peer recording state
        self.multi_peer_client = None
        self.room_recorders = {}  # stream_id -> recorder
        self.room_sessions = {}   # session_id -> stream_id
        self.ice_queue = asyncio.Queue()  # Thread-safe ICE queue
        self.ice_processor_task = None
        self.event_loop = None  # Will be set when event loop is available
        
        try:
            if self.password:
                # Use hostname or default
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

    async def connect(self):
        printc("🔌 Connecting to handshake server...", "0FF")
        
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

    def sendMessage(self, msg): # send message to wss
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
   
    def on_incoming_stream(self, webrtc, pad):
        try:
            if Gst.PadDirection.SRC != pad.direction:
                print("pad direction wrong?")
                return
            caps = pad.get_current_caps()
            name = caps.to_string()
            print(f"Incoming stream caps: {name}")
            
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
            if self.ndiout:
                print("NDI OUT")
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
                    print("NDI VIDEO OUT")
                    pad_name = "video"
                    rtp_caps_string = "application/x-rtp,media=(string)video,clock-rate=(int)90000,encoding-name=(string)H264"
                elif "audio" in name:
                    print("NDI AUDIO OUT")
                    pad_name = "audio"
                    rtp_caps_string = "application/x-rtp,media=(string)audio,clock-rate=(int)48000,encoding-name=(string)OPUS"
                else:
                    print("Unsupported media type:", name)
                    return

                # Check if the pad already exists
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
                    elements = [
                        Gst.ElementFactory.make("capsfilter", f"{pad_name}_rtp_caps"),
                        Gst.ElementFactory.make("queue", f"{pad_name}_queue"),
                        Gst.ElementFactory.make("rtph264depay", "h264_depay"),
                        Gst.ElementFactory.make("h264parse", "h264_parse"),
                        Gst.ElementFactory.make("avdec_h264", "h264_decode"),
                        Gst.ElementFactory.make("videoconvert", "video_convert"),
                        Gst.ElementFactory.make("videoscale", "video_scale"),
                        Gst.ElementFactory.make("videorate", "video_rate"),
                        Gst.ElementFactory.make("capsfilter", "video_caps"),
                    ]
                    elements[0].set_property("caps", Gst.Caps.from_string(rtp_caps_string))
                    elements[-1].set_property("caps", Gst.Caps.from_string("video/x-raw,format=UYVY,width=1280,height=720,framerate=30/1"))
                else:  # audio
                    elements = [
                        Gst.ElementFactory.make("capsfilter", f"{pad_name}_rtp_caps"),
                        Gst.ElementFactory.make("queue", f"{pad_name}_queue"),
                        Gst.ElementFactory.make("rtpopusdepay", "opus_depay"),
                        Gst.ElementFactory.make("opusdec", "opus_decode"),
                        Gst.ElementFactory.make("audioconvert", "audio_convert"),
                        Gst.ElementFactory.make("audioresample", "audio_resample"),
                        Gst.ElementFactory.make("capsfilter", "audio_caps"),
                    ]
                    elements[0].set_property("caps", Gst.Caps.from_string(rtp_caps_string))
                    elements[-1].set_property("caps", Gst.Caps.from_string("audio/x-raw,format=F32LE,channels=2,rate=48000,layout=interleaved"))

                if not all(elements):
                    print("Couldn't create all elements")
                    return

                # Create a bin for the elements
                bin_name = f"{pad_name}_bin"
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
                element_bin.sync_state_with_parent()

                # Link the bin to the ndi_combiner
                if not element_bin.link_pads("src", ndi_combiner, target_pad.get_name()):
                    print(f"Failed to link {bin_name} to ndi_combiner:{target_pad.get_name()}")
                    print(f"Bin src caps: {ghost_src.query_caps().to_string()}")
                    print(f"Target pad caps: {target_pad.query_caps().to_string()}")
                    return

                # Link the incoming pad to the bin
                if not pad.link(ghost_sink):
                    print(f"Failed to link incoming pad to {bin_name}")
                    print(f"Incoming pad caps: {pad.query_caps().to_string()}")
                    print(f"Ghost sink pad caps: {ghost_sink.query_caps().to_string()}")
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
                    pad.link(sink)
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
                    pad.link(sink)
                    
                    appsink = self.pipe.get_by_name('appsink')
                    appsink.connect("new-sample", self.on_new_socket_sample)
                elif self.view:
                    # Check if we're in recording mode
                    if self.recording_enabled and "video" in name:
                        if self.setup_recording_pipeline(pad, name):
                            return  # Recording set up successfully
                    
                    # Normal display mode
                    print("DISPLAY OUTPUT MODE BEING SETUP")
                    
                    outsink = "autovideosink"
                    if check_drm_displays():
                        printc('\nThere is at least one connected display.',"00F")
                    else:
                        printc('\n ! No connected displays found. Will try to use glimagesink instead of autovideosink',"F60")
                        outsink = "glimagesink sync=true"
                    
                    if "VP8" in name:
                        out = Gst.parse_bin_from_description(
                            "queue ! rtpvp8depay ! decodebin ! queue max-size-buffers=0 max-size-time=0 ! videoconvert ! video/x-raw,format=RGB ! queue max-size-buffers=0 max-size-time=0 ! "+outsink, True)
                    elif "H264" in name:
                        out = Gst.parse_bin_from_description(
                            "queue ! rtph264depay ! h264parse ! openh264dec ! queue max-size-buffers=0 max-size-time=0 ! videoconvert ! video/x-raw,format=RGB ! queue max-size-buffers=0 max-size-time=0 ! "+outsink, True)
                        
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)      
                    
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
                    printc('VIDEO record setup', "88F")
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
                            # VP8 recording - use videoscale and caps to handle resolution changes
                            out = Gst.parse_bin_from_description(
                                "queue max-size-buffers=0 max-size-time=0 ! "
                                "rtpvp8depay ! "
                                "vp8dec ! "
                                "videoscale ! "
                                "video/x-raw,width=1280,height=720 ! "
                                "vp8enc deadline=1 cpu-used=4 ! "
                                "matroskamux name=mux1 streamable=true ! "
                                "filesink name=filesink location=" + "./" + self.streamin + "_"+str(int(time.time()))+".webm", True)

                        elif "H264" in name:
                            out = Gst.parse_bin_from_description("queue ! rtph264depay ! h264parse ! mpegtsmux name=mux1 ! queue ! "
            + "hlssink name=hlssink max-files=0 "
            + "target-duration=10 playlist-length=0 "
            + "location=" + "./" + self.streamin + "_"+str(int(time.time()))+"_segment_%05d.ts "
            + "playlist-location=" + "./" + self.streamin + "_"+str(int(time.time()))+".video.m3u8 " , True)

                        self.pipe.add(out)
                        out.sync_state_with_parent()
                        sink = out.get_static_pad('sink')
                        pad.link(sink)
                    printc("   ✅ Video recording configured", "0F0")

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
                        printc("   📼 Recording audio to separate file...", "FFF")
                        if "OPUS" in name:
                            out = Gst.parse_bin_from_description("queue ! rtpopusdepay ! opusparse ! audio/x-opus,channel-mapping-family=0,rate=48000 ! mpegtsmux name=mux2 ! queue ! multifilesink name=filesinkaudio sync=true location="+self.streamin+"_"+str(int(time.time()))+"_audio.%02d.ts next-file=5 max-file-duration="+str(10*Gst.SECOND), True)

                        self.pipe.add(out)
                        out.sync_state_with_parent()
                        sink = out.get_static_pad('sink')
                        pad.link(sink)
                        
                printc("   ✅ Audio recording configured", "0F0")

        except Exception as E:
            printc("\n❌ Error during stream setup:", "F00")
            printwarn(get_exception_info(E))

            traceback.print_exc()

        # Add this debugging information at the end of the function
        print("Pipeline state after setup:")
        print(self.pipe.get_state(0))

            
    async def createPeer(self, UUID):

        if UUID in self.clients:
            client = self.clients[UUID]
        else:
            print("peer not yet created; error")
            return

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

            msg = {'description': {'type': 'offer', 'sdp': text}, 'UUID': client['UUID'], 'session': client['session'], 'streamID':self.stream_id+self.hashcode}
            self.sendMessage(msg)

        def on_new_tranceiver(element, trans):
            # New transceiver added
            pass

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
                self.stop_pipeline(client['UUID'])
            elif state == 1:
                printc("🔄 Connecting to peer...", "77F")
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
                self.stop_pipeline(client['UUID'])

        def on_data_channel(webrtc, channel):
            printc("   📡 Data channel event", "FFF")
            if channel is None:
                printc('      └─ No data channel available', "F44")
                return
            else:
                printc('      └─ Data channel setup', "0F0")
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
            stats = promise.get_reply()
            stats = stats.to_string()
            stats = stats.replace("\\", "")
            stats = stats.split("fraction-lost=(double)")
            if (len(stats)>1):
                stats = stats[1].split(",")[0]
                # Only log packet loss if it's significant or changed substantially
                if not hasattr(client, '_last_packet_loss'):
                    client['_last_packet_loss'] = -1
                
                if float(stats) > 0.01 or abs(float(stats) - client['_last_packet_loss']) > 0.005:
                    if float(stats) > 0.01:
                        printc(f"📊 Packet loss: {stats} ⚠️", "F77")
                    elif client['_last_packet_loss'] < 0 or client['_last_packet_loss'] > 0.01:
                        # Only show excellent message when transitioning from bad to good
                        printc(f"📊 Network quality: excellent", "0F0")
                    client['_last_packet_loss'] = float(stats)
                if " vp8enc " in self.pipeline: # doesn't support dynamic bitrates? not sure the property to use at least
                    return
                elif " av1enc " in self.pipeline: # seg-fault if I try to change it currently
                    return
                stats = float(stats)
                if (stats>0.01) and not self.noqos:
                    old_bitrate = self.bitrate
                    bitrate = self.bitrate*0.9
                    if bitrate < self.max_bitrate*0.2:
                        bitrate = self.max_bitrate*0.2
                    elif bitrate > self.max_bitrate*0.8:
                        bitrate = self.bitrate*0.9
                    
                    # Only update and print if bitrate actually changed
                    if int(bitrate) != int(old_bitrate):
                        self.bitrate = bitrate
                        printc(f"   └─ Reducing bitrate to {int(bitrate)} kbps (packet loss detected)", "FF0")
                        self.set_encoder_bitrate(client, int(bitrate))

                elif (stats<0.003) and not self.noqos:
                    old_bitrate = self.bitrate
                    bitrate = self.bitrate*1.05
                    if bitrate>self.max_bitrate:
                        bitrate = self.max_bitrate
                    elif bitrate*2<self.max_bitrate:
                        bitrate = self.bitrate*1.05
                    
                    # Only update and print if bitrate actually changed
                    if int(bitrate) != int(old_bitrate):
                        self.bitrate = bitrate
                        printc(f"   └─ Increasing bitrate to {int(bitrate)} kbps (good connection)", "0F0")
                        self.set_encoder_bitrate(client, int(bitrate))

        printc("🔧 Creating WebRTC pipeline...", "0FF")

        started = True
        if not self.pipe:
            printc("   └─ Loading pipeline configuration...", "FFF")

            if self.streamin:
                self.pipe = Gst.Pipeline.new('decode-pipeline') ## decode or capture
            elif len(self.pipeline)<=1:
                self.pipe = Gst.Pipeline.new('data-only-pipeline')
            else:
                print(self.pipeline)
                try:
                    self.pipe = Gst.parse_launch(self.pipeline)
                except Exception as e:
                    printc(f"Failed to create pipeline: {e}", "F00")
                    return
                
            print(self.pipe)
            started = False
            
        client['qv'] = None
        client['qa'] = None
        client['encoder'] = False
        client['encoder1'] = False
        client['encoder2'] = False
        
        try:
            client['encoder'] = self.pipe.get_by_name('encoder')
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
            except Exception as E:
                pass
            self.pipe.add(client['webrtc'])
           
            if self.vp8:     
                pass
            elif self.h264:
                direction = GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY
                caps = Gst.caps_from_string("application/x-rtp,media=video,encoding-name=H264,payload=102,clock-rate=90000,packetization-mode=(string)1")
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
                self.midi_thread = threading.Thread(target=midi2vdo, args=(self.midi,))
                self.midi_thread.start()
                print(self.midi_thread)
                print("MIDI THREAD STARTED")

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
            client['webrtc'].connect('on-ice-candidate', send_ice_remote_candidate_message)
            client['webrtc'].connect('on-data-channel', on_data_channel)
        else:
            client['webrtc'].connect('on-ice-candidate', send_ice_local_candidate_message)
            client['webrtc'].connect('on-negotiation-needed', on_negotiation_needed)
            client['webrtc'].connect('on-new-transceiver', on_new_tranceiver)

        try:
            if not self.streamin:
                trans = client['webrtc'].emit("get-transceiver",0)
                if trans is not None:
                    try:
                        if not self.nored:
                            trans.set_property("fec-type", GstWebRTC.WebRTCFECType.ULP_RED)
                            print("FEC ENABLED")
                    except Exception as E:
                        pass
                    trans.set_property("do-nack", True)
                    print("SEND NACKS ENABLED")

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
        print("ON ANSWER CREATED")
        promise.wait()
        reply = promise.get_reply()
        answer = reply.get_value('answer')
        if not answer:
            print("Not answer created?")
            return
        promise = Gst.Promise.new()
        client['webrtc'].emit('set-local-description', answer, promise)
        promise.interrupt()
        print("SEND SDP ANSWER")
        text = answer.sdp.as_text()
        msg = {'description': {'type': 'answer', 'sdp': text}, 'UUID': client['UUID'], 'session': client['session']}
        self.sendMessage(msg)

    def handle_offer(self, msg, UUID):
        print("HANDLE SDP OFFER")
        print("-----")
        client = self.clients[UUID]
        if not client or not client['webrtc']:
            return
        if 'sdp' in msg:
            print("INCOMDING OFFER SDP TYPE: "+msg['type'])
            assert(msg['type'] == 'offer')
            sdp = msg['sdp']
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
                    self.stop_pipeline(uid)
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
                
                # Set pipeline to NULL after cleaning up elements
                try:
                    self.pipe.set_state(Gst.State.NULL)
                except Exception as e:
                    printwarn(f"Failed to set pipeline to NULL: {e}")
                self.pipe = None

            await self.createPeer(UUID)

    def stop_pipeline(self, UUID):
        printc("🛑 Stopping pipeline for viewer", "F77")
        with self.pipeline_lock:
            if UUID not in self.clients:
                print(f"Client {UUID} not found in clients list")
                return
            
            # Cancel the ping timer if it exists
            if 'timer' in self.clients[UUID] and self.clients[UUID]['timer'] is not None:
                try:
                    self.clients[UUID]['timer'].cancel()
                    self.clients[UUID]['timer'] = None
                except Exception as e:
                    printwarn(f"Failed to cancel timer: {e}")
                
            if not self.multiviewer:
                if UUID in self.clients:
                    del self.clients[UUID]
            elif UUID in self.clients:
                # In multiviewer mode, unlink from tees
                atee = self.pipe.get_by_name('audiotee')
                vtee = self.pipe.get_by_name('videotee')

                # Unlink elements before cleanup to prevent dangling references
                try:
                    if atee is not None and self.clients[UUID]['qa'] is not None:
                        atee.unlink(self.clients[UUID]['qa'])
                except Exception as e:
                    printwarn(f"Failed to unlink audio queue: {e}")
                    
                try:
                    if vtee is not None and self.clients[UUID]['qv'] is not None:
                        vtee.unlink(self.clients[UUID]['qv'])
                except Exception as e:
                    printwarn(f"Failed to unlink video queue: {e}")

            # CRITICAL: Set elements to NULL state BEFORE removing from pipeline
            # This prevents segfaults during cleanup
            try:
                if self.clients[UUID]['webrtc'] is not None:
                    self.clients[UUID]['webrtc'].set_state(Gst.State.NULL)
                    self.pipe.remove(self.clients[UUID]['webrtc'])
            except Exception as e:
                printwarn(f"Failed to cleanup webrtc element: {e}")
                
            try:
                if self.clients[UUID]['qa'] is not None:
                    self.clients[UUID]['qa'].set_state(Gst.State.NULL)
                    self.pipe.remove(self.clients[UUID]['qa'])
            except Exception as e:
                printwarn(f"Failed to cleanup audio queue: {e}")
                
            try:
                if self.clients[UUID]['qv'] is not None:
                    self.clients[UUID]['qv'].set_state(Gst.State.NULL)
                    self.pipe.remove(self.clients[UUID]['qv'])
            except Exception as e:
                printwarn(f"Failed to cleanup video queue: {e}")
                
            # Always remove from clients dict, even if cleanup failed
            if UUID in self.clients:
                del self.clients[UUID]

        if len(self.clients)==0:
            enableLEDs(0.1)

        if self.pipe:
            if self.save_file:
                pass
            elif len(self.clients)==0:
                # Ensure pipeline is properly cleaned up when no clients remain
                try:
                    self.pipe.set_state(Gst.State.PAUSED)
                    self.pipe.get_state(Gst.SECOND)  # 1 second timeout
                    self.pipe.set_state(Gst.State.NULL)
                    self.pipe.get_state(Gst.SECOND)  # 1 second timeout
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
        elif encoding_name == 'VP9':
            recording_file = f"{self.record}_{stream_id}_{timestamp}.mkv"
            pipeline_str = (
                f"queue ! rtpvp9depay ! matroskamux ! "
                f"filesink name=filesink_{stream_id} location={recording_file}"
            )
        else:
            printc(f"[{stream_id}] Unknown codec: {encoding_name}", "F00")
            return
            
        printc(f"[{stream_id}] Recording to: {recording_file}", "0F0")
        printc(f"[{stream_id}] Pipeline: {pipeline_str}", "77F")
        
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
            printc(f"[{stream_id}] ✅ Recording started", "0F0")
            
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

    async def cleanup_pipeline(self):
        """Safely cleanup pipeline and all resources"""
        async with self.cleanup_lock:
            printc("Cleaning up pipeline and resources...", "FF0")
            
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
                    self.stop_pipeline(uuid)
                except Exception as e:
                    printwarn(f"Error stopping client {uuid}: {e}")
            
            # Clean up main pipeline
            if self.pipe:
                try:
                    # First set to PAUSED to stop data flow
                    self.pipe.set_state(Gst.State.PAUSED)
                    # Wait for state change with timeout (1 second)
                    ret = self.pipe.get_state(Gst.SECOND)
                    if ret[0] != Gst.StateChangeReturn.SUCCESS:
                        printwarn("Pipeline didn't pause cleanly, forcing NULL state")
                    
                    # Then set to NULL to release resources
                    self.pipe.set_state(Gst.State.NULL)
                    # Wait for NULL state with timeout
                    ret = self.pipe.get_state(Gst.SECOND)
                    if ret[0] == Gst.StateChangeReturn.SUCCESS:
                        printc("   └─ ✅ Pipeline cleaned up successfully", "0F0")
                    else:
                        printwarn("Pipeline didn't reach NULL state cleanly")
                except Exception as e:
                    printwarn(f"Error cleaning up pipeline: {e}")
                    # Force cleanup even if state change failed
                    try:
                        self.pipe.set_state(Gst.State.NULL)
                    except:
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
                        # especially for room recording mode
                        if self.room_recording:
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
                                    "original_uuid": UUID
                                }
                            UUID = new_uuid  # Use the new UUID for this session
                        else:
                            print("sessions don't match")
                            continue

                # Handle room recording messages
                if self.room_recording:
                    handled = await self._handle_room_message(msg)
                    if handled:
                        continue
                
                if 'description' in msg:
                    print("description via WSS")
                    
                    # In room recording mode, check if this UUID corresponds to a stream we're tracking
                    original_uuid = self.clients[UUID].get('original_uuid', UUID) if UUID in self.clients else UUID
                    if self.room_recording and original_uuid in self.room_streams:
                        printc(f"Offer for room stream: {self.room_streams[original_uuid]['streamID']}", "7F7")
                    
                    if 'vector' in msg:
                        decryptedJson = decrypt_message(msg['description'], msg['vector'], self.password+self.salt)
                        msg = json.loads(decryptedJson)
                    else:
                        msg = msg['description']
                        
                    if 'type' in msg:
                        if msg['type'] == "offer":
                            # Check if this is for a subprocess recorder
                            if self.room_recording:
                                printc(f"[Room Recording] Received offer for UUID: {UUID}", "77F")
                                session_id = self.clients[UUID].get('session') if UUID in self.clients else None
                                stream_id = None
                                
                                # Primary method: Check if this UUID is already mapped to a stream
                                for sid, uid in self.stream_id_to_uuid.items():
                                    if uid == UUID:
                                        stream_id = sid
                                        printc(f"[Room Recording] Found existing mapping: UUID {UUID} -> stream {stream_id}", "77F")
                                        break
                                
                                # Secondary method: For first offer after play request, match unmapped streams
                                if not stream_id:
                                    printc(f"[Room Recording] No existing UUID mapping, checking {len(self.subprocess_managers)} subprocess managers", "77F")
                                    
                                    # Find subprocesses that don't have a UUID mapping yet
                                    unmapped_streams = []
                                    for sid in self.subprocess_managers.keys():
                                        mapped = False
                                        for mapped_sid, mapped_uid in self.stream_id_to_uuid.items():
                                            if mapped_sid == sid:
                                                mapped = True
                                                break
                                        if not mapped:
                                            unmapped_streams.append(sid)
                                    
                                    if unmapped_streams:
                                        # Use the first unmapped stream
                                        stream_id = unmapped_streams[0]
                                        printc(f"[Room Recording] Matching to unmapped stream: {stream_id}", "77F")
                                    elif len(self.subprocess_managers) == 1:
                                        # If only one subprocess, assume it's for that one
                                        stream_id = list(self.subprocess_managers.keys())[0]
                                        printc(f"[Room Recording] Using only available stream: {stream_id}", "77F")
                                
                                # If we have a stream_id and a subprocess for it
                                if stream_id and stream_id in self.subprocess_managers:
                                    printc(f"[Room Recording] Routing offer to subprocess: {stream_id}", "0F0")
                                    # Update UUID mapping - this is the key!
                                    self.stream_id_to_uuid[stream_id] = UUID
                                    printc(f"[Room Recording] Mapped UUID {UUID} to stream {stream_id}", "0F0")
                                    
                                    # Also map session if available
                                    if session_id:
                                        self.session_to_stream[session_id] = stream_id
                                        printc(f"[Room Recording] Also mapped session {session_id} to stream {stream_id}", "77F")
                                        
                                    # Route to subprocess
                                    await self.handle_subprocess_offer(stream_id, msg['sdp'], session_id or str(time.time()))
                                    continue
                                else:
                                    printc(f"[Room Recording] No subprocess found for offer. UUID: {UUID}, session: {session_id}", "F00")
                            
                            if self.streamin:
                                printc("📥 Incoming connection offer", "0FF")
                                await self.start_pipeline(UUID)
                                self.handle_offer(msg, UUID)
                            else:
                                printc("We don't support two-way video calling yet. ignoring remote offer.", "399")
                                continue
                        elif msg['type'] == "answer":
                            printc("🤝 Connection accepted", "0F0")
                            self.handle_sdp_ice(msg, UUID)
                elif 'candidates' in msg:
                    # Processing ICE candidates bundle via websocket
                    
                    # Check if this is for a subprocess recorder
                    if self.room_recording:
                        session_id = self.clients[UUID].get('session') if UUID in self.clients else None
                        stream_id = None
                        
                        # Primary method: Check UUID mapping
                        for sid, uid in self.stream_id_to_uuid.items():
                            if uid == UUID:
                                stream_id = sid
                                printc(f"[Room Recording] ICE candidates for UUID {UUID} -> stream {stream_id}", "77F")
                                break
                        
                        # Secondary method: Try session mapping if no UUID match
                        if not stream_id and session_id:
                            stream_id = self.session_to_stream.get(session_id)
                            if stream_id:
                                printc(f"[Room Recording] ICE candidates for session {session_id} -> stream {stream_id} (fallback)", "77F")
                        
                        if stream_id and stream_id in self.subprocess_managers:
                            # Validate session if we have one
                            if session_id:
                                expected_session = self.session_to_stream.get(session_id)
                                if expected_session and expected_session != stream_id:
                                    printc(f"[Room Recording] WARNING: Session mismatch - expected stream {expected_session}, got {stream_id}", "F00")
                                    # Continue anyway with UUID-based routing
                                    
                            # Route to subprocess
                            if 'vector' in msg:
                                decryptedJson = decrypt_message(msg['candidates'], msg['vector'], self.password+self.salt)
                                msg['candidates'] = json.loads(decryptedJson)
                            
                            if type(msg['candidates']) is list:
                                printc(f"[Room Recording] Routing {len(msg['candidates'])} ICE candidates to {stream_id}", "0F0")
                                for ice in msg['candidates']:
                                    await self.handle_subprocess_ice(stream_id, ice)
                            continue
                        else:
                            printc(f"[Room Recording] No subprocess found for ICE. UUID: {UUID}, session: {session_id}", "F00")
                            printc(f"[Room Recording] UUID mappings: {self.stream_id_to_uuid}", "F00")
                            printc(f"[Room Recording] Session mappings: {self.session_to_stream}", "F00")
                    
                    if 'vector' in msg:
                        decryptedJson = decrypt_message(msg['candidates'], msg['vector'], self.password+self.salt)
                        msg['candidates'] = json.loads(decryptedJson)
                    
                    if type(msg['candidates']) is list:
                        for ice in msg['candidates']:
                            self.handle_sdp_ice(ice, UUID)
                    else:
                        printc("Warning: Expected a list of candidates","F00")
                elif 'candidate' in msg:
                    # Processing single ICE candidate via websocket
                    
                    # Check if this is for a subprocess recorder
                    if self.room_recording:
                        session_id = self.clients[UUID].get('session') if UUID in self.clients else None
                        stream_id = None
                        
                        # Primary method: Check UUID mapping
                        for sid, uid in self.stream_id_to_uuid.items():
                            if uid == UUID:
                                stream_id = sid
                                break
                        
                        # Secondary method: Try session mapping if no UUID match
                        if not stream_id and session_id:
                            stream_id = self.session_to_stream.get(session_id)
                        
                        if stream_id and stream_id in self.subprocess_managers:
                            # Route to subprocess
                            if 'vector' in msg:
                                decryptedJson = decrypt_message(msg['candidate'], msg['vector'], self.password+self.salt)
                                msg['candidate'] = json.loads(decryptedJson)
                            await self.handle_subprocess_ice(stream_id, msg)
                            continue
                    
                    if 'vector' in msg:
                        decryptedJson = decrypt_message(msg['candidate'], msg['vector'], self.password+self.salt)
                        msg['candidate'] = json.loads(decryptedJson)
                    
                    self.handle_sdp_ice(msg, UUID)
                elif 'request' in msg:
                    if msg['request'] not in ['play', 'offerSDP', 'cleanup', 'bye', 'videoaddedtoroom']:
                        printc(f"📨 Request: {msg['request']}", "77F")
                    if 'offerSDP' in  msg['request']:
                        await self.start_pipeline(UUID)
                    elif msg['request'] == 'cleanup' or msg['request'] == 'bye':
                        # Handle room stream cleanup
                        if self.room_recording and UUID in self.room_streams:
                            await self.cleanup_room_stream(UUID)
                    elif msg['request'] == "play":
                        # Play request received
                        if 'streamID' in msg:
                            if msg['streamID'] == self.stream_id+self.hashcode:
                                await self.start_pipeline(UUID)
                    elif msg['request'] == "videoaddedtoroom":
                        if 'streamID' in msg:
                            if self.room_recording:
                                # New stream added to room
                                stream_id = msg['streamID']
                                # UUID comes from the message context, not the msg dict
                                # In custom websocket mode, this event may not be sent
                                await self.handle_new_room_stream(stream_id, UUID)
                            elif self.streamin:
                                printwout("play stream.")
                                await self.sendMessageAsync({"request":"play","streamID":self.streamin+self.hashcode})
                    elif msg['request'] == 'joinroom':
                        if self.room_recording:
                            # Handle new member joining when we're recording the room
                            if 'streamID' in msg:
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
                        if self.room_recording and 'streamID' in msg:
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
        
        # Debug: print room members
        for member in room_list:
            if 'streamID' in member:
                printc(f"  - Stream: {member.get('streamID', 'unknown')}", "77F")
        
        # In room recording mode, we need to handle this differently
        printc(f"Room recording mode: {self.room_recording}", "FF0")
        if self.room_recording:
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
                    
                    # Apply filter if configured
                    if self.stream_filter and stream_id not in self.stream_filter:
                        continue
                        
                    streams_to_record.append(stream_id)
                    
            printc(f"Found {len(streams_to_record)} streams to record", "7FF")
            
            # Start recording each stream using subprocess architecture
            for stream_id in streams_to_record:
                await self.create_subprocess_recorder(stream_id)
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
    
    async def create_subprocess_recorder(self, stream_id):
        """Create a subprocess recorder for a stream"""
        if stream_id in self.subprocess_managers:
            printc(f"[{stream_id}] Already recording", "FF0")
            return
            
        printc(f"\n📹 Creating subprocess recorder for: {stream_id}", "0F0")
        
        # Configuration for subprocess
        config = {
            'mode': 'view',
            'room': self.room_name,
            'record_file': f"{self.record}_{stream_id}_{int(time.time())}.webm",
            'pipeline': '',  # Will use default receive pipeline
            'bitrate': self.bitrate,
            'stun_server': self.stun_server if hasattr(self, 'stun_server') else 'stun://stun.l.google.com:19302',
            'turn_server': self.turn_server if hasattr(self, 'turn_server') else None,
        }
        
        # Create subprocess manager
        manager = WebRTCSubprocessManager(stream_id, config)
        
        # Set up message handlers
        def on_sdp(msg):
            # Forward SDP to WebSocket
            asyncio.create_task(self.send_subprocess_sdp(stream_id, msg))
            
        def on_ice(msg):
            # Forward ICE to WebSocket
            asyncio.create_task(self.send_subprocess_ice(stream_id, msg))
            
        def on_state(msg):
            # Update connection state
            state = msg.get('state', '')
            printc(f"[{stream_id}] Connection state: {state}", "77F")
            
        manager.on_message('sdp', on_sdp)
        manager.on_message('ice', on_ice)
        manager.on_message('connection_state', on_state)
        manager.on_message('ice_state', lambda msg: printc(f"[{stream_id}] ICE: {msg.get('state')}", "77F"))
        
        # Start subprocess
        if await manager.start():
            self.subprocess_managers[stream_id] = manager
            
            # Tell subprocess to start pipeline
            await manager.send_message({"type": "start", "session_id": stream_id})
            
            # Request stream from server
            play_msg = {
                "request": "play",
                "streamID": stream_id
            }
            # If we have a UUID for this stream already, include it
            for uuid, stream_info in self.room_streams.items():
                if stream_info.get('streamID') == stream_id:
                    play_msg["UUID"] = uuid
                    # Pre-map this for routing
                    self.stream_id_to_uuid[stream_id] = uuid
                    break
                    
            await self.sendMessageAsync(play_msg)
            
            printc(f"[{stream_id}] Subprocess recorder started", "0F0")
        else:
            printc(f"[{stream_id}] Failed to start subprocess", "F00")
            
    async def send_subprocess_sdp(self, stream_id, msg):
        """Send SDP from subprocess to WebSocket"""
        sdp_type = msg.get('sdp_type')
        sdp = msg.get('sdp')
        session_id = msg.get('session_id')
        
        if sdp_type == 'answer':
            # Get the proper UUID for this stream
            uuid = self.stream_id_to_uuid.get(stream_id, stream_id)
            
            # Send answer to server
            await self.sendMessageAsync({
                "description": {
                    "type": "answer",
                    "sdp": sdp
                },
                "UUID": uuid,
                "session": session_id
            })
            
    async def send_subprocess_ice(self, stream_id, msg):
        """Send ICE candidate from subprocess to WebSocket"""
        candidate = msg.get('candidate')
        sdpMLineIndex = msg.get('sdpMLineIndex', 0)
        session_id = msg.get('session_id')
        
        # Get the proper UUID for this stream
        uuid = self.stream_id_to_uuid.get(stream_id, stream_id)
        
        await self.sendMessageAsync({
            "candidates": [{
                "candidate": candidate,
                "sdpMLineIndex": sdpMLineIndex
            }],
            "UUID": uuid,
            "session": session_id,
            "type": "remote"
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
        """Handle a new stream that joined the room"""
        # Check if we should record this stream
        if self.stream_filter and stream_id not in self.stream_filter:
            return
            
        printc(f"New stream joined room: {stream_id}", "7FF")
        
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
                    'stats': {},
                    'client': None  # For future isolated client
                }
        
        if self.room_recording:
            # Use subprocess recorder
            await self.create_subprocess_recorder(stream_id)
    
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
        ndi_name = f"{self.room_name}_{stream_id}"
        
        # Create individual NDI sink for this stream
        ndi_sink_name = f"ndi_sink_{client['UUID']}"
        
        if "video" in name:
            # Create NDI sink combiner for this client if not exists
            ndi_combiner_name = f"ndi_combiner_{client['UUID']}"
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
                printc(f"Created NDI output: {ndi_name}", "7F7")
            
            # Process video for NDI
            if "H264" in name:
                pipeline_str = "queue ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert"
            elif "VP8" in name:
                pipeline_str = "queue ! rtpvp8depay ! vp8dec ! videoconvert"
            else:
                printc(f"Unknown video codec for NDI: {name}", "F00")
                return
            
            out = Gst.parse_bin_from_description(pipeline_str, True)
            self.pipe.add(out)
            out.sync_state_with_parent()
            
            # Link to NDI combiner
            ndi_pad = ndi_combiner.get_request_pad("video")
            if ndi_pad:
                ghost_src = out.get_static_pad("src")
                ghost_src.link(ndi_pad)
            
            sink = out.get_static_pad('sink')
            pad.link(sink)
            
        elif "audio" in name and not self.noaudio:
            # Get existing NDI combiner for this client
            ndi_combiner_name = f"ndi_combiner_{client['UUID']}"
            ndi_combiner = self.pipe.get_by_name(ndi_combiner_name)
            
            if ndi_combiner:
                # Process audio for NDI
                if "OPUS" in name:
                    pipeline_str = "queue ! rtpopusdepay ! opusdec ! audioconvert ! audioresample"
                else:
                    printc(f"Unknown audio codec for NDI: {name}", "F00")
                    return
                
                out = Gst.parse_bin_from_description(pipeline_str, True)
                self.pipe.add(out)
                out.sync_state_with_parent()
                
                # Link to NDI combiner
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
    parser.add_argument('--novideo', action='store_true', help='Disables video input.')
    parser.add_argument('--noaudio', action='store_true', help='Disables audio input.')
    parser.add_argument('--led', action='store_true', help='Enable GPIO pin 12 as an LED indicator light; for Raspberry Pi.')
    parser.add_argument('--pipeline', type=str, help='A full custom pipeline')
    parser.add_argument('--record',  type=str, help='Specify a stream ID to record to disk. System will not publish a stream when enabled.')
    parser.add_argument('--view',  type=str, help='Specify a stream ID to play out to the local display/audio.')
    parser.add_argument('--save', action='store_true', help='Save a copy of the outbound stream to disk. Publish Live + Store the video.')
    parser.add_argument('--record-room', action='store_true', help='Record all streams in a room to separate files. Requires --room parameter.')
    parser.add_argument('--record-streams', type=str, help='Comma-separated list of stream IDs to record from a room. Optional filter for --record-room.')
    parser.add_argument('--room-ndi', action='store_true', help='Relay all room streams to NDI as separate sources. Requires --room parameter.')
    parser.add_argument('--midi', action='store_true', help='Transparent MIDI bridge mode; no video or audio.')
    parser.add_argument('--filesrc', type=str, default=None,  help='Provide a media file (local file location) as a source instead of physical device; it can be a transparent webm or whatever. It will be transcoded, which offers the best results.')
    parser.add_argument('--filesrc2', type=str, default=None,  help='Provide a media file (local file location) as a source instead of physical device; it can be a transparent webm or whatever. It will not be transcoded, so be sure its encoded correctly. Specify if --vp8 or --vp9, else --h264 is assumed.')
    parser.add_argument('--pipein', type=str, default=None, help='Pipe a media stream in as the input source. Pass `auto` for auto-decode,pass codec type for pass-thru (mpegts,h264,vp8,vp9), or use `raw`')
    parser.add_argument('--ndiout',  type=str, help='VDO.Ninja to NDI output; requires the NDI Gstreamer plugin installed')
    parser.add_argument('--fdsink',  type=str, help='VDO.Ninja to the stdout pipe; common for piping data between command line processes')
    parser.add_argument('--framebuffer', type=str, help='VDO.Ninja to local frame buffer; performant and Numpy/OpenCV friendly')
    parser.add_argument('--debug', action='store_true', help='Show added debug information from Gsteamer and other aspects of the app')
    parser.add_argument('--buffer',  type=int, default=200, help='The jitter buffer latency in milliseconds; default is 200ms, minimum is 10ms. (gst +v1.18)')
    parser.add_argument('--password', type=str, nargs='?', default="someEncryptionKey123", required=False, const='', help='Specify a custom password. If setting to false, password/encryption will be disabled.')
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


    args = parser.parse_args()
    
    # Display header
    printc("\n╔═══════════════════════════════════════════════╗", "0FF")
    printc("║          🥷 Raspberry Ninja                   ║", "0FF") 
    printc("║     Multi-Platform WebRTC Publisher           ║", "0FF")
    printc("╚═══════════════════════════════════════════════╝\n", "0FF")
    
    # Validate buffer value to prevent segfaults
    if args.buffer < 10:
        printc("Warning: Buffer values below 10ms can cause segfaults. Setting to minimum of 10ms.", "F77")
        args.buffer = 10

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
        args.streamin = args.framebuffer
    elif args.record_room or args.room_ndi:
        # Room recording mode (check this first before regular record)
        args.streamin = "room_recording"  # Special value to indicate room recording mode
        args.room_recording = True
        
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
        args.streamin = args.record
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
                    # Add leaky queue to handle frame drops and prevent buffer overruns with low latency
                    pipeline_video_input += f' ! v4l2convert{timestampOverlay} ! video/x-raw,format=I420 ! queue max-size-buffers=30 max-size-time=0 leaky=upstream ! vp8enc deadline=1 name="encoder" target-bitrate={args.bitrate}000 {saveVideo} ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=96'
                elif check_plugins('mppvp8enc'):
                    # Rockchip hardware VP8 encoder - ensure NV12 input
                    pipeline_video_input += f'{pipeline_video_converter} ! queue max-size-buffers=4 leaky=upstream ! mppvp8enc qp-init=40 qp-min=10 qp-max=100 gop=30 name="encoder" rc-mode=cbr bps={args.bitrate * 1000} {saveVideo} ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=96'

                else:
                    # Add leaky queue to handle frame drops and prevent buffer overruns with low latency
                    pipeline_video_input += f' ! videoconvert{timestampOverlay} ! queue max-size-buffers=30 max-size-time=0 leaky=upstream ! vp8enc deadline=1 target-bitrate={args.bitrate}000 name="encoder" {saveVideo} ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=96'

            if args.multiviewer:
                pipeline_video_input += ' ! tee name=videotee '
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
            printc(f"\n-> Relaying all streams from room '{args.room}' to NDI", "7FF")
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
    
    # Track if we're already shutting down
    shutdown_count = [0]
    
    def signal_handler(signum, frame):
        shutdown_count[0] += 1
        if shutdown_count[0] == 1:
            printc("\n🛑 Received interrupt signal, shutting down gracefully...", "F70")
            c._shutdown_requested = True
            # Force close the websocket to break out of recv()
            if c.conn:
                asyncio.create_task(c.conn.close())
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
            await c.cleanup_pipeline()
            break
        except Exception as e:
            if c._shutdown_requested:
                break
            printc(f"⚠️  Connection error: {e}", "F77")
            # WebSocket reconnection - peer connections remain active
            await asyncio.sleep(5)
    
    # Ensure cleanup is called
    await c.cleanup_pipeline()
    
    # Stop web server if running
    if webserver:
        await webserver.stop()
    
    # Restore original signal handlers
    signal.signal(signal.SIGINT, original_sigint)
    signal.signal(signal.SIGTERM, original_sigterm)
    
    # Cancel stats task if running
    if stats_task:
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
