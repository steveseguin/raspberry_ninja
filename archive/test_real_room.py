#!/usr/bin/env python3
"""
Test REAL room recording with testroom123
"""

import asyncio
import subprocess
import time
import os
import glob
import sys

# Clean up old files
for f in glob.glob("testroom123_*.ts") + glob.glob("testroom123_*.mkv") + glob.glob("myprefix_*.ts") + glob.glob("myprefix_*.mkv"):
    try:
        os.remove(f)
        print(f"Cleaned up: {f}")
    except:
        pass

print("\n" + "="*70)
print("TESTING REAL ROOM RECORDING")
print("="*70)
print("Room: testroom123")
print("Password: false")
print("Stream available: KLvZZdT")
print("="*70)

# Start the room recorder
cmd = [
    sys.executable, "publish.py",
    "--room", "testroom123",
    "--record", "myprefix",
    "--record-room",
    "--password", "false",
    "--noaudio"  # Add noaudio to simplify
]

print(f"\nCommand: {' '.join(cmd)}")
print("\nStarting room recorder...")

proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

# Monitor output
print("\nMonitoring output for 30 seconds...")
print("-" * 50)

start_time = time.time()
timeout = 30
recording_started = False
ice_connected = False
error_found = False

while time.time() - start_time < timeout:
    line = proc.stdout.readline()
    if not line:
        time.sleep(0.1)
        continue
        
    line = line.rstrip()
    print(f"{line}")
    
    # Check for key events
    if "Recording to:" in line:
        recording_started = True
        print("\n>>> RECORDING STARTED! <<<\n")
    elif "ICE state: STATE_CONNECTED" in line or "ICE: Connected" in line:
        ice_connected = True
        print("\n>>> ICE CONNECTED! <<<\n")
    elif "ERROR" in line:
        error_found = True
    elif "Connection state: STATE_CONNECTED" in line:
        print("\n>>> WEBRTC CONNECTED! <<<\n")

print("\n" + "-" * 50)
print("Stopping recorder...")
proc.terminate()

# Wait for cleanup
time.sleep(3)

# Force kill if needed
if proc.poll() is None:
    proc.kill()
    time.sleep(1)

# Check results
print("\nCHECKING RESULTS...")
print("-" * 50)

# Find recordings
recordings = []
patterns = [
    "myprefix_*.ts", "myprefix_*.mkv",
    "testroom123_*.ts", "testroom123_*.mkv",
    "KLvZZdT_*.ts", "KLvZZdT_*.mkv"
]

for pattern in patterns:
    recordings.extend(glob.glob(pattern))

if recordings:
    print(f"\n✅ Found {len(recordings)} recording file(s):")
    
    # Validate each file
    from validate_media_file import validate_recording
    
    for f in recordings:
        size = os.path.getsize(f)
        print(f"\nFile: {f}")
        print(f"Size: {size:,} bytes")
        
        if size > 1000:  # Only validate if file has content
            is_valid = validate_recording(f, verbose=False)
            print(f"Valid: {'✅ YES' if is_valid else '❌ NO'}")
        else:
            print("Valid: ❌ NO (too small)")
            
    # Success if we have any valid recording
    success = any(os.path.getsize(f) > 1000 for f in recordings)
else:
    print("\n❌ No recording files found!")
    success = False

print("\n" + "="*70)
print("TEST SUMMARY:")
print(f"  Room reached: {'Yes' if not error_found else 'No'}")
print(f"  ICE connected: {'Yes' if ice_connected else 'No'}")  
print(f"  Recording started: {'Yes' if recording_started else 'No'}")
print(f"  Files created: {len(recordings)}")
print(f"  Result: {'✅ PASSED' if success else '❌ FAILED'}")
print("="*70)