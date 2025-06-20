#!/usr/bin/env python3
"""Test transceiver setup"""

import subprocess
import sys
import time

print("Testing transceiver setup in room recording...")

# Start the process
proc = subprocess.Popen(
    [sys.executable, "publish.py", "--room", "testroom123", "--record-room", 
     "--password", "false", "--noaudio", "--debug"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True,
    bufsize=1
)

# Read output for 10 seconds
start_time = time.time()
found_transceiver = False
found_sdp = False

try:
    while time.time() - start_time < 10:
        line = proc.stdout.readline()
        if not line:
            break
            
        # Look for key messages
        if "Processing SDP" in line:
            found_sdp = True
            print(f"✅ SDP: {line.rstrip()}")
        elif "Adding" in line and "transceiver" in line:
            found_transceiver = True
            print(f"✅ TRANSCEIVER: {line.rstrip()}")
        elif "media sections" in line:
            print(f"📋 MEDIA: {line.rstrip()}")
        elif "Connection state:" in line and "FAILED" in line:
            print(f"❌ FAILED: {line.rstrip()}")
                
except KeyboardInterrupt:
    pass

# Stop the process
proc.terminate()
time.sleep(1)
if proc.poll() is None:
    proc.kill()

print(f"\nResults:")
print(f"- SDP processing seen: {'✅ Yes' if found_sdp else '❌ No'}")
print(f"- Transceiver setup seen: {'✅ Yes' if found_transceiver else '❌ No'}")