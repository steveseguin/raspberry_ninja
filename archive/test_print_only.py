#!/usr/bin/env python3
"""
Test that just prints output without waiting
"""

import subprocess
import sys
import time

print("Starting room recorder...")

# Start room recorder
proc = subprocess.Popen([
    sys.executable, "publish.py",
    "--room", "testroom",
    "--record", "test",
    "--record-room",
    "--noaudio",
    "--password", "false"
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Read output for 5 seconds
start = time.time()
while time.time() - start < 5:
    line = proc.stdout.readline()
    if line:
        print(line.rstrip())
    else:
        time.sleep(0.1)

print("\nTerminating...")
proc.terminate()
proc.wait(timeout=2)
print("Done.")