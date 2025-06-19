#!/usr/bin/env python3
"""Test with relay-only mode"""

import subprocess
import time

print("Testing with relay-only mode (forces TURN usage)...")
print("=" * 70)

# Test with relay-only mode
cmd = [
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'relay_test',
    '--record-room',
    '--password', 'false',
    '--noaudio',
    '--ice-transport-policy', 'relay'  # Force TURN usage
]

print("Command:", ' '.join(cmd))
print()

proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Monitor for 15 seconds
start = time.time()
while time.time() - start < 15:
    line = proc.stdout.readline()
    if not line:
        if proc.poll() is not None:
            break
        continue
    
    # Show relevant lines
    if any(kw in line for kw in ["TURN", "ICE", "relay", "Recording", "Connection", "ERROR"]):
        print(line.rstrip())

proc.terminate()
proc.wait()

print("\nIf this still fails, the TURN server might be unreachable or credentials invalid.")