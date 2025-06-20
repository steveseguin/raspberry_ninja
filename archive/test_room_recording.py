#!/usr/bin/env python3
"""Test room recording and capture output"""

import subprocess
import sys
import time
import signal

print("Starting room recording test...")

# Start the process
proc = subprocess.Popen(
    [sys.executable, "publish.py", "--room", "testroom123", "--record-room", 
     "--password", "false", "--noaudio"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True,
    bufsize=1
)

# Read output for 20 seconds
start_time = time.time()
try:
    while time.time() - start_time < 20:
        line = proc.stdout.readline()
        if line:
            print(line.rstrip())
except KeyboardInterrupt:
    pass

# Stop the process
print("\nStopping test...")
proc.send_signal(signal.SIGINT)
time.sleep(2)
if proc.poll() is None:
    proc.terminate()
    time.sleep(1)
    if proc.poll() is None:
        proc.kill()

print("Test completed")

# Check for any created files
import glob
files = glob.glob("testroom123_*.webm") + glob.glob("testroom123_*.ts") + glob.glob("testroom123_*.mkv")
if files:
    print("\nRecorded files:")
    for f in files:
        print(f"  - {f}")
else:
    print("\nNo recording files created")