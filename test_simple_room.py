#!/usr/bin/env python3
"""
Simple test that runs room recording with the test room
"""

import subprocess
import sys
import time
import os
import glob
import signal

# Clean up old files
for pattern in ["myprefix_*.ts", "myprefix_*.mkv", "testroom123_*.ts", "testroom123_*.mkv"]:
    for f in glob.glob(pattern):
        try:
            os.remove(f)
            print(f"Cleaned up: {f}")
        except:
            pass

print("="*70)
print("ROOM RECORDING TEST - Using testroom123")
print("="*70)

# Run the room recorder
print("\nStarting room recorder...")
print("Command: python3 publish.py --room testroom123 --record myprefix --record-room --password false --noaudio")
print()

rec = subprocess.Popen([
    sys.executable, "publish.py",
    "--room", "testroom123",
    "--record", "myprefix",
    "--record-room",
    "--password", "false",
    "--noaudio"
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Monitor output for 30 seconds
start_time = time.time()
duration = 30

try:
    while time.time() - start_time < duration:
        if rec.poll() is not None:
            print("\nProcess exited early!")
            break
            
        # Read output line by line
        line = rec.stdout.readline()
        if line:
            print(line.rstrip())
            
        time.sleep(0.1)
        
except KeyboardInterrupt:
    print("\nInterrupted by user")

finally:
    # Stop the recorder
    print(f"\nStopping after {int(time.time() - start_time)} seconds...")
    rec.send_signal(signal.SIGTERM)
    
    # Wait for clean shutdown
    try:
        rec.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print("Force killing...")
        rec.kill()
        rec.wait()

# Check for recordings
print("\n" + "="*70)
print("RESULTS:")
print("="*70)

files = []
for pattern in ["myprefix_*.ts", "myprefix_*.mkv", "testroom123_*.ts", "testroom123_*.mkv"]:
    files.extend(glob.glob(pattern))

if files:
    print(f"\n✅ Found {len(files)} recordings:")
    for f in files:
        size = os.path.getsize(f)
        print(f"   {f} ({size:,} bytes)")
        
    # Try to validate
    try:
        from validate_media_file import validate_recording
        print("\nValidating files...")
        for f in files:
            result = validate_recording(f)
            print(f"   {f}: {'✅ Valid' if result else '❌ Invalid'}")
    except:
        pass
else:
    print("\n❌ No recordings found")
    print("\nThis likely means:")
    print("1. WebRTC connection failed (check ICE/STUN connectivity)")
    print("2. No streams in the room")
    print("3. Pipeline setup failed")