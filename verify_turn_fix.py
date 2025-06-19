#!/usr/bin/env python3
"""Verify TURN fix is working"""

import subprocess
import sys
import time
import re

# Start the process
proc = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'verify_turn',
    '--record-room',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Read output for a few seconds
start = time.time()
turn_url = None
errors = []

while time.time() - start < 5:
    line = proc.stdout.readline()
    if not line:
        break
    
    clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
    
    if "Using VDO.Ninja TURN:" in clean:
        turn_url = clean
        print(f"Found: {clean}")
        
        # Check format
        if "turn://" in clean and "@" in clean:
            print("✅ TURN URL is correctly formatted!")
        else:
            print("❌ TURN URL format is incorrect!")
            
    if "ERROR" in clean and "turn" in clean.lower():
        errors.append(clean)
        print(f"Error: {clean}")

# Kill process
proc.terminate()
proc.wait()

print("\nResults:")
if turn_url:
    print(f"TURN URL: {turn_url}")
else:
    print("❌ No TURN URL found")
    
if errors:
    print("\nErrors found:")
    for err in errors:
        print(f"  - {err}")
else:
    print("✅ No TURN errors detected in first 5 seconds")