#!/usr/bin/env python3
"""
Test the integrated room recording in publish.py
"""

import subprocess
import time
import glob
import os
import sys

# Clean up old recordings
patterns = ["test_*.ts", "test_*.mkv", "testroom123_*.ts", "testroom123_*.mkv"]
for pattern in patterns:
    for f in glob.glob(pattern):
        try:
            os.remove(f)
            print(f"Cleaned: {f}")
        except:
            pass

print("="*70)
print("INTEGRATED ROOM RECORDING TEST")
print("Testing with room: testroom123 (stream: KLvZZdT)")
print("="*70)

# Run the integrated room recorder
cmd = [
    sys.executable, 'publish.py',
    '--room', 'testroom123',
    '--record', 'test',
    '--record-room',
    '--password', 'false',
    '--noaudio'
]

print("\nRunning command:")
print(" ".join(cmd))
print("\nOutput:")
print("-"*70)

# Start the process
proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True,
    bufsize=1
)

# Monitor for 30 seconds
start_time = time.time()
important_lines = []

try:
    while time.time() - start_time < 30:
        if proc.poll() is not None:
            print("\nProcess exited early!")
            break
            
        line = proc.stdout.readline()
        if line:
            line = line.rstrip()
            print(line)
            
            # Collect important lines
            if any(x in line for x in ['Adding recorder', 'Answer created', 
                                      'Recording started', 'Connection state',
                                      'ICE', 'ERROR', 'Recording to']):
                important_lines.append(line)
                
except KeyboardInterrupt:
    print("\nInterrupted")
finally:
    proc.terminate()
    time.sleep(2)
    if proc.poll() is None:
        proc.kill()

# Summary
print("\n" + "="*70)
print("KEY EVENTS:")
print("="*70)
for line in important_lines:
    print(line)

# Check results
print("\n" + "="*70)
print("RESULTS:")
print("="*70)

files = []
for pattern in patterns:
    files.extend(glob.glob(pattern))

if files:
    print(f"\n✅ SUCCESS! Found {len(files)} recordings:")
    for f in files:
        size = os.path.getsize(f)
        print(f"  {f}: {size:,} bytes")
        
    # Validate
    try:
        from validate_media_file import validate_recording
        print("\nValidating recordings...")
        for f in files:
            result = validate_recording(f, verbose=False)
            print(f"  {f}: {'✅ Valid' if result else '❌ Invalid'}")
    except Exception as e:
        print(f"\nValidation error: {e}")
else:
    print("\n❌ FAILED - No recordings found")
    print("\nThis indicates:")
    print("1. WebRTC connection failed")
    print("2. ICE candidates not being sent properly") 
    print("3. Pipeline setup failed")

print("\n" + "="*70)