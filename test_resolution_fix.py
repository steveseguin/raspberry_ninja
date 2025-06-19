#!/usr/bin/env python3
"""Test if resolution change fix works"""

import subprocess
import time
import os

print("Testing VP8 recording with resolution change fix...")
print("=" * 70)

# Start recording
proc = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--view', 'tUur6wt', 
    '--record', 'resolution_fix_test',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Monitor for errors
start = time.time()
errors = []
warnings = []
recording_started = False
last_size = 0
file_path = None

print("Recording for 45 seconds to test resolution changes...")

while time.time() - start < 45:
    line = proc.stdout.readline()
    if not line:
        if proc.poll() is not None:
            print(f"\n[{time.time()-start:.1f}s] Process terminated")
            break
        continue
    
    # Track important events
    if "Recording VP8 to:" in line:
        recording_started = True
        # Extract filename
        if ".webm" in line:
            file_path = line.split("Recording VP8 to: ")[-1].strip()
            file_path = file_path.split(" ")[0]  # Remove any trailing text
        print(f"[{time.time()-start:.1f}s] {line.strip()}")
    elif "error:" in line.lower() or "ERROR" in line:
        errors.append(f"[{time.time()-start:.1f}s] {line.strip()}")
        print(f"[{time.time()-start:.1f}s] ERROR: {line.strip()}")
    elif "WARN" in line or "not-negotiated" in line or "Caps changes" in line:
        warnings.append(f"[{time.time()-start:.1f}s] {line.strip()}")
        print(f"[{time.time()-start:.1f}s] WARN: {line.strip()}")
    elif "ICE" in line and "Connected" in line:
        print(f"[{time.time()-start:.1f}s] {line.strip()}")
    elif "NO HEARTBEAT" in line or "Stopping pipeline" in line:
        print(f"[{time.time()-start:.1f}s] {line.strip()}")
        
    # Check file growth every 5 seconds
    if file_path and os.path.exists(file_path) and int(time.time() - start) % 5 == 0:
        size = os.path.getsize(file_path)
        if size > last_size:
            print(f"[{time.time()-start:.1f}s] File growing: {size/1024:.1f} KB")
            last_size = size

print("\nTerminating recording...")
proc.terminate()
proc.wait()

print("\n" + "=" * 70)
print("TEST RESULTS:")
print(f"  Recording started: {'✅' if recording_started else '❌'}")
print(f"  Errors: {len(errors)}")
print(f"  Warnings: {len(warnings)}")

if errors:
    print("\n  Errors detected:")
    for err in errors[:5]:  # Show first 5
        print(f"    {err}")

# Check final file
if file_path and os.path.exists(file_path):
    size = os.path.getsize(file_path)
    duration = time.time() - start
    expected_size = duration * 50 * 1024  # ~50KB/s for low quality VP8
    
    print(f"\n  Final file: {file_path}")
    print(f"  Size: {size/1024:.1f} KB")
    print(f"  Expected minimum: {expected_size/1024:.1f} KB")
    
    if size > expected_size * 0.7:  # Allow 30% variance
        print("  ✅ File size indicates continuous recording")
    else:
        print("  ❌ File size too small - recording may have stopped")
    
    # Validate
    print("\n  Validating file...")
    result = subprocess.run(['python3', 'validate_media_file.py', file_path],
                          capture_output=True, text=True)
    print(f"  {result.stdout.strip()}")
else:
    print("\n  ❌ No recording file found")

print("\n" + "=" * 70)
if not errors and recording_started and size > expected_size * 0.7:
    print("✅ RESOLUTION CHANGE HANDLING WORKS!")
else:
    print("❌ Issues detected with resolution change handling")