#!/usr/bin/env python3
"""Test to see debug output"""

import subprocess
import time

print("Testing room recording with debug output...")
print("=" * 70)

proc = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'debug_turn',
    '--record-room',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# Look for debug output
start = time.time()
debug_found = False
turn_found = False

while time.time() - start < 10:
    line = proc.stdout.readline()
    if not line:
        if proc.poll() is not None:
            break
        time.sleep(0.1)
        continue
    
    print(line.rstrip())
    
    if "DEBUG: room_recording=" in line:
        debug_found = True
    if "Using VDO.Ninja TURN" in line:
        turn_found = True

proc.terminate()
proc.wait()

print("\n" + "=" * 70)
print(f"Debug output found: {'Yes' if debug_found else 'No'}")
print(f"TURN configured: {'Yes' if turn_found else 'No'}")