#!/usr/bin/env python3
"""
Test recording a specific known stream from VDO.Ninja
"""

import subprocess
import time
import re

print("TESTING SPECIFIC STREAM RECORDING")
print("=" * 70)
print("Attempting to record the test stream 'KLvZZdT' from testroom123")
print()

# Try recording the specific stream that was mentioned in the logs
proc = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--view', 'KLvZZdT',  # The specific stream ID from earlier tests
    '--record', 'specific_stream',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Monitor output
start = time.time()
turn_detected = False
ice_checking = False
connected = False
recording = False

while time.time() - start < 30:
    line = proc.stdout.readline()
    if not line:
        if proc.poll() is not None:
            break
        continue
    
    # Clean ANSI
    clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
    
    # Print key events
    if any(keyword in clean.lower() for keyword in ["turn", "ice", "recording", "connected", "failed", "error"]):
        print(clean)
    
    # Check status
    if "Using VDO.Ninja TURN" in clean:
        turn_detected = True
    elif "ICE" in clean and "CHECKING" in clean:
        ice_checking = True
    elif "Connection state" in clean and "CONNECTED" in clean:
        connected = True
    elif "Recording started" in clean:
        recording = True
        print("\n✅ SUCCESS! Recording has started!\n")
        time.sleep(5)  # Let it record for a bit
        break

# Clean up
proc.terminate()
proc.wait()

print("\n" + "=" * 70)
print("Results:")
print(f"  TURN configured: {'✅ Yes' if turn_detected else '❌ No'}")
print(f"  ICE checking: {'✅ Yes' if ice_checking else '❌ No'}")
print(f"  Connected: {'✅ Yes' if connected else '❌ No'}")
print(f"  Recording: {'✅ Yes' if recording else '❌ No'}")

# Check for output files
import glob
files = glob.glob("specific_stream*.ts") + glob.glob("specific_stream*.mkv")
if files:
    print(f"\n✅ Found {len(files)} recorded files:")
    import os
    for f in files:
        size = os.path.getsize(f)
        print(f"  {f}: {size:,} bytes")
else:
    print("\n❌ No recordings created")