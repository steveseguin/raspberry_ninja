#!/usr/bin/env python3
"""Test ICE routing in room recording"""

import subprocess
import sys
import time
import os
import signal

print("Testing ICE routing in room recording...")

# Start the process
proc = subprocess.Popen(
    [sys.executable, "publish.py", "--room", "testroom123", "--record-room", 
     "--password", "false", "--noaudio"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True,
    bufsize=1,
    preexec_fn=os.setsid  # Create new process group
)

# Read output for 25 seconds
start_time = time.time()
ice_routing_seen = False
connection_established = False

try:
    while time.time() - start_time < 25:
        line = proc.stdout.readline()
        if not line:
            break
            
        # Filter for relevant messages
        if any(phrase in line for phrase in [
            "ICE candidates for UUID",
            "Routing", "candidates to",
            "Connection state:",
            "WebRTC connected",
            "recording started",
            "Warning", "unknown session"
        ]):
            print(line.rstrip())
            
            if "Routing" in line and "ICE candidates to" in line:
                ice_routing_seen = True
            if "WebRTC connected" in line or "Connection state: GST_WEBRTC_PEER_CONNECTION_STATE_CONNECTED" in line:
                connection_established = True
                
except KeyboardInterrupt:
    pass

# Stop the process group
print("\nStopping test...")
try:
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
except:
    proc.terminate()

time.sleep(1)
if proc.poll() is None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except:
        proc.kill()

print("\nTest Results:")
print(f"- ICE routing seen: {'✅ Yes' if ice_routing_seen else '❌ No'}")
print(f"- WebRTC connection established: {'✅ Yes' if connection_established else '❌ No'}")

# Check for recordings
import glob
files = glob.glob("testroom123_*.webm") + glob.glob("testroom123_*.ts") + glob.glob("*.webm")
recent_files = [f for f in files if os.path.getmtime(f) > start_time]
if recent_files:
    print(f"\nRecordings created: ✅ {len(recent_files)} files")
    for f in recent_files:
        size = os.path.getsize(f)
        print(f"  - {f} ({size:,} bytes)")
else:
    print("\nRecordings created: ❌ No")