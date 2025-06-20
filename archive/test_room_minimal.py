#!/usr/bin/env python3
"""
Minimal test to debug room recording
"""

import subprocess
import time
import sys
import os

# Just test if processes start correctly
print("Testing if publish.py can start...")

# Test 1: Basic publisher
print("\n1. Testing basic publisher...")
p1 = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--stream", "test1",
    "--noaudio", "--password", "false"
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Read a few lines
for i in range(10):
    line = p1.stdout.readline()
    if line:
        print(f"   {line.rstrip()}")
    if "WebSocket ready" in line:
        print("   ✓ Publisher started successfully")
        break

p1.terminate()
time.sleep(1)

# Test 2: Room recorder command
print("\n2. Testing room recorder command...")
p2 = subprocess.Popen([
    sys.executable, "publish.py",
    "--room", "testroom",
    "--record", "test",
    "--record-room",
    "--noaudio",
    "--password", "false"
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Read output
for i in range(15):
    line = p2.stdout.readline()
    if line:
        print(f"   {line.rstrip()}")
    if "Room recording mode" in line:
        print("   ✓ Room recording mode activated")
    if "WebSocket ready" in line:
        print("   ✓ Connected to WebSocket")
        break

p2.terminate()
time.sleep(1)

print("\nBasic tests completed.")