#!/usr/bin/env python3
"""Test TURN configuration directly"""

import subprocess
import time
import sys

# First test: Regular recording to see baseline behavior
print("TEST 1: Regular recording (should NOT use TURN by default)")
print("=" * 70)

proc1 = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--view', 'somestream',
    '--record', 'regular_test',
    '--password', 'false',
    '--noaudio',
    '--novideo'
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# Read first 30 lines
for i in range(30):
    line = proc1.stdout.readline()
    if not line:
        break
    if "TURN" in line or "turn" in line:
        print(f"  Found: {line.rstrip()}")

proc1.terminate()
proc1.wait()

print("\n\nTEST 2: Room recording (SHOULD use TURN automatically)")
print("=" * 70)

proc2 = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'room_test',
    '--record-room',  # This should trigger automatic TURN
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# Read first 50 lines looking for TURN
found_turn = False
for i in range(50):
    line = proc2.stdout.readline()
    if not line:
        break
    if "TURN" in line or "turn" in line or "Room recording mode" in line:
        print(f"  Found: {line.rstrip()}")
        if "Using VDO.Ninja TURN" in line:
            found_turn = True

proc2.terminate()
proc2.wait()

print("\n" + "=" * 70)
if found_turn:
    print("✅ SUCCESS: Automatic TURN is working for room recording!")
else:
    print("❌ FAIL: TURN was not automatically configured for room recording")