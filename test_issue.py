#!/usr/bin/env python3
"""
Test to find the actual issue
"""

import subprocess
import sys
import time
import signal

print("Starting publish.py with room recording...")

proc = subprocess.Popen([
    sys.executable, 'publish.py',
    '--room', 'testroom123',
    '--record', 'test',
    '--record-room',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Read output for 20 seconds
start = time.time()
try:
    while time.time() - start < 20:
        line = proc.stdout.readline()
        if line:
            # Filter out ANSI codes for clarity
            import re
            line = re.sub(r'\x1b\[[0-9;]*m', '', line)
            print(line.rstrip())
        
        if proc.poll() is not None:
            print(f"\nProcess exited with code: {proc.returncode}")
            break
except:
    pass

# Stop the process
print("\nStopping process...")
proc.send_signal(signal.SIGTERM)
time.sleep(2)

if proc.poll() is None:
    proc.kill()
    
print("Done.")