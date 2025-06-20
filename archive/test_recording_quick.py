#!/usr/bin/env python3
"""Quick test of room recording"""

import subprocess
import sys
import time

print("Starting room recording test...")

# Run publish.py
proc = subprocess.Popen(
    [sys.executable, "publish.py", "--room", "testroom123", "--record-room", 
     "--password", "false", "--noaudio"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True,
    bufsize=1
)

# Read output for 15 seconds
start_time = time.time()
try:
    while time.time() - start_time < 15:
        line = proc.stdout.readline()
        if line:
            # Filter relevant lines
            if any(word in line for word in [
                "Recording", "subprocess", "Routing", "Connection", 
                "Pipeline", "Error", "Room", "Matching", "offer"
            ]):
                print(line.strip())
except KeyboardInterrupt:
    pass

# Cleanup
proc.terminate()
proc.wait()
print("\nTest completed")