#!/usr/bin/env python3
"""
Simple debug to test basic message flow
"""

import subprocess
import sys
import time
import os
import glob
import asyncio
import json

# Clean up
for f in glob.glob("simple_*.ts") + glob.glob("simple_*.mkv"):
    os.remove(f)

room = f"simpletest{int(time.time())}"

# Start publisher
print(f"Starting publisher in room: {room}")
pub = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "test_stream",
    "--noaudio", "--h264"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

time.sleep(5)

# Start regular viewer (not room recording)
print("\nStarting viewer...")
rec_cmd = [
    sys.executable, "publish.py",
    "--room", room,
    "--view", "test_stream",
    "--record", "simple",
    "--noaudio"
]

print(f"Command: {' '.join(rec_cmd)}")

rec = subprocess.Popen(
    rec_cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)

# Monitor output
print("\nMonitoring output for 10 seconds...")
start_time = time.time()

while time.time() - start_time < 10:
    line = rec.stdout.readline()
    if line:
        line = line.rstrip()
        # Print key messages
        if any(key in line for key in ["Request:", "recording", "Recording", "saved", "bytes"]):
            print(f">>> {line}")

# Stop
rec.terminate()
pub.terminate()

# Wait
time.sleep(3)

# Check recordings
recordings = glob.glob("simple*.ts") + glob.glob("simple*.mkv")

if recordings:
    print(f"\n✅ Found {len(recordings)} recordings:")
    for f in recordings:
        print(f"   - {f} ({os.path.getsize(f):,} bytes)")
        
    # Validate
    from validate_media_file import validate_recording
    for f in recordings:
        if validate_recording(f, verbose=False):
            print(f"   ✅ {f} is valid")
        else:
            print(f"   ❌ {f} is invalid")
else:
    print("\n❌ No recordings found")