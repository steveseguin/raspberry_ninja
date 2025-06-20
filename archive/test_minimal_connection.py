#!/usr/bin/env python3
"""Minimal test to debug connection issues"""

import subprocess
import sys
import time

print("Testing minimal room connection...")

# Start process and capture first 15 seconds
proc = subprocess.Popen(
    [sys.executable, "publish.py", "--room", "testroom123", "--record-room", 
     "--password", "false", "--noaudio"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True,
    bufsize=1
)

start = time.time()
failed_count = 0
connecting_count = 0

try:
    while time.time() - start < 15:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                print(f"Process exited with code: {proc.poll()}")
                break
            continue
            
        # Count key events
        if "FAILED" in line:
            failed_count += 1
            print(f"❌ FAILURE #{failed_count}: {line.rstrip()}")
        elif "CONNECTING" in line:
            connecting_count += 1
            if connecting_count <= 2:
                print(f"🔄 CONNECTING: {line.rstrip()}")
        elif "CONNECTED" in line and "successfully" in line:
            print(f"✅ SUCCESS: {line.rstrip()}")
        elif "recording started" in line:
            print(f"🎬 RECORDING: {line.rstrip()}")
        elif "ERROR" in line or "error" in line:
            print(f"⚠️  ERROR: {line.rstrip()}")
            
except KeyboardInterrupt:
    pass
finally:
    proc.terminate()
    time.sleep(1)
    if proc.poll() is None:
        proc.kill()

print(f"\nSummary:")
print(f"- Connection attempts: {connecting_count}")
print(f"- Failed connections: {failed_count}")
print(f"- Success rate: {0 if connecting_count == 0 else (connecting_count - failed_count) / connecting_count * 100:.1f}%")