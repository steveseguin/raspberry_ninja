#!/usr/bin/env python3
"""
Actually run room recording and show what happens
"""

import subprocess
import sys
import time
import os

cmd = [
    sys.executable, 'publish.py',
    '--room', 'testroom123',
    '--record', 'roomtest',
    '--record-room',
    '--password', 'false',
    '--noaudio'
]

print("="*70)
print("RUNNING ROOM RECORDING")
print("="*70)
print("Command:", ' '.join(cmd))
print("\nStarting in 3 seconds...\n")
time.sleep(3)

# Run and capture output
proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

print("STDOUT:")
print("-"*70)
print(proc.stdout)

print("\nSTDERR:")
print("-"*70)
print(proc.stderr)

print("\nReturn code:", proc.returncode)