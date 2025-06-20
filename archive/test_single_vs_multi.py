#!/usr/bin/env python3
"""Test single stream vs multi-stream recording"""

import subprocess
import time
import sys

print("Testing Single Stream vs Multi-Stream Recording")
print("=" * 70)

# Test 1: Single stream recording
print("\n1. Testing SINGLE stream recording (--view mode)...")
print("-" * 60)

proc1 = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--view', 'tUur6wt',  # Specific stream
    '--record', 'single_test',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# Monitor for 15 seconds
start = time.time()
single_connected = False
single_recording = False

while time.time() - start < 15:
    line = proc1.stdout.readline()
    if not line:
        if proc1.poll() is not None:
            break
        continue
    
    if "ICE: Connected" in line or "CONNECTED" in line:
        single_connected = True
        print(f"  ✅ Connected: {line.strip()}")
    elif "Recording started" in line or "✅ Recording started" in line:
        single_recording = True
        print(f"  ✅ Recording: {line.strip()}")
        break
    elif "FAILED" in line:
        print(f"  ❌ Failed: {line.strip()}")

proc1.terminate()
proc1.wait()

print(f"\nSingle stream result: Connected={single_connected}, Recording={single_recording}")

# Short pause
time.sleep(2)

# Test 2: Multi-stream recording
print("\n\n2. Testing MULTI-stream recording (--record-room mode)...")
print("-" * 60)

proc2 = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'multi_test',
    '--record-room',  # Room recording mode
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# Monitor for 15 seconds
start = time.time()
multi_connected = False
multi_recording = False

while time.time() - start < 15:
    line = proc2.stdout.readline()
    if not line:
        if proc2.poll() is not None:
            break
        continue
    
    if "ICE: Connected" in line or "CONNECTED" in line:
        multi_connected = True
        print(f"  ✅ Connected: {line.strip()}")
    elif "Recording started" in line or "✅ Recording started" in line:
        multi_recording = True
        print(f"  ✅ Recording: {line.strip()}")
        break
    elif "FAILED" in line:
        print(f"  ❌ Failed: {line.strip()}")
    elif "Room Recording Status" in line:
        print(f"  Status: {line.strip()}")

proc2.terminate()
proc2.wait()

print(f"\nMulti-stream result: Connected={multi_connected}, Recording={multi_recording}")

# Summary
print("\n" + "=" * 70)
print("COMPARISON RESULTS:")
print(f"  Single stream: {'✅ WORKS' if single_recording else '❌ FAILS'}")
print(f"  Multi-stream:  {'✅ WORKS' if multi_recording else '❌ FAILS'}")

if single_recording and not multi_recording:
    print("\n🔍 DIAGNOSIS: Multi-stream implementation has issues")
    print("   The difference is in how room recorders are created/configured")
else:
    print("\n🔍 DIAGNOSIS: Both modes have same behavior")