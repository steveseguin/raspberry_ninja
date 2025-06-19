#!/usr/bin/env python3
"""Simple room recording test"""

import os
import subprocess
import time
import signal

print("Starting simple room recording test...")

# Run for 10 seconds
cmd = ["python3", "publish.py", "--room", "testroom123", "--record-room", "--password", "false", "--noaudio"]
print(f"Running: {' '.join(cmd)}")

proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Read for 10 seconds
start = time.time()
lines_read = 0

while time.time() - start < 10:
    line = proc.stdout.readline()
    if line:
        lines_read += 1
        # Only print important lines
        if any(word in line for word in ["transceiver", "Connection", "Processing", "Adding", "FAILED", "media"]):
            print(line.rstrip())

print(f"\nRead {lines_read} lines in 10 seconds")

# Cleanup
proc.terminate()
proc.wait(timeout=2)
print("Test complete")