#!/usr/bin/env python3
"""Test auto TURN configuration in room recording"""

import subprocess
import sys
import time
import os

print("Testing auto TURN in room recording...")

# Start the process
proc = subprocess.Popen(
    [sys.executable, "publish.py", "--room", "testroom123", "--record-room", 
     "--password", "false", "--noaudio"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True,
    bufsize=1
)

# Read output for 10 seconds
start_time = time.time()
turn_seen = False

try:
    while time.time() - start_time < 10:
        line = proc.stdout.readline()
        if not line:
            break
            
        # Look for TURN configuration messages
        if "Using" in line and "TURN" in line:
            print(f"✅ {line.rstrip()}")
            turn_seen = True
        elif "TURN server configured" in line:
            print(f"✅ {line.rstrip()}")
            turn_seen = True
        elif "auto-enabled" in line:
            print(f"✅ {line.rstrip()}")
            turn_seen = True
                
except KeyboardInterrupt:
    pass

# Stop the process
proc.terminate()
time.sleep(1)
if proc.poll() is None:
    proc.kill()

print(f"\nAuto TURN detected: {'✅ Yes' if turn_seen else '❌ No'}")

proc2 = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'manual',
    '--record-room',
    '--turn-server', 'turn://vdoninja:theyBeSharksHere@turn-usw2.vdo.ninja:3478',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Quick check
custom_turn = False
start2 = time.time()

while time.time() - start2 < 10:
    line = proc2.stdout.readline()
    if not line:
        if proc2.poll() is not None:
            break
        continue
    
    clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
    
    if "Using custom TURN" in clean:
        custom_turn = True
        print(f"✅ {clean}")
        break

proc2.terminate()
proc2.wait()

print(f"\nCustom TURN detected: {'✅ Yes' if custom_turn else '❌ No'}")

# Check for recordings
files = glob.glob("auto_*.ts") + glob.glob("auto_*.mkv") + glob.glob("manual_*.ts") + glob.glob("manual_*.mkv")
print("\n" + "="*70)
if files:
    print(f"✅ SUCCESS! Found {len(files)} recordings:")
    for f in files:
        print(f"  {f}: {os.path.getsize(f):,} bytes")
else:
    print("❌ No recordings created")
    print("\nThis might indicate:")
    print("1. Network issues preventing TURN connectivity")
    print("2. The stream KLvZZdT is no longer available in testroom123")
    print("3. WebRTC negotiation issues despite TURN servers")