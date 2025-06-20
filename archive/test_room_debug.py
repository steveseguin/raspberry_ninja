#!/usr/bin/env python3
"""
Debug test for room recording with detailed output
"""

import subprocess
import sys
import time
import os
import glob

print("="*70)
print("ROOM RECORDING DEBUG TEST")
print("="*70)

# Clean up
for f in glob.glob("roomdebug_*.ts") + glob.glob("roomdebug_*.mkv"):
    try:
        os.remove(f)
    except:
        pass

# Step 1: Start publishers
print("\n1. Starting publishers...")
pub1 = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", "debugroom",
    "--stream", "alice",
    "--noaudio", "--h264",
    "--password", "false"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

time.sleep(2)

pub2 = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", "debugroom",
    "--stream", "bob", 
    "--noaudio", "--vp8",
    "--password", "false"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print("   ✓ Publishers started (alice with H264, bob with VP8)")
time.sleep(3)

# Step 2: Start room recorder with full output
print("\n2. Starting room recorder with debugging...")
rec = subprocess.Popen([
    sys.executable, "publish.py",
    "--room", "debugroom",
    "--record", "roomdebug",
    "--record-room",
    "--noaudio",
    "--password", "false"
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Monitor output
print("\n3. Room recorder output:")
print("-" * 50)
start = time.time()
lines = []

while time.time() - start < 30:  # 30 seconds
    line = rec.stdout.readline()
    if line:
        line = line.rstrip()
        lines.append(line)
        # Print all lines for debugging
        print(f"{line}")
        
        # Check for successful recording
        if "Recording to:" in line and ".ts" in line:
            print(f"\n>>> RECORDING STARTED: {line}")
        elif "Recording started" in line:
            print(f"\n>>> CONFIRMED: {line}")

print("\n4. Terminating processes...")
rec.terminate()
pub1.terminate()
pub2.terminate()

# Give processes time to finish writing
time.sleep(3)

# Check results
print("\n5. RESULTS:")
print("-" * 50)

recordings = glob.glob("roomdebug_*.ts") + glob.glob("roomdebug_*.mkv") + \
             glob.glob("debugroom_*.ts") + glob.glob("debugroom_*.mkv")

if recordings:
    print(f"✅ Found {len(recordings)} recording(s):")
    for f in sorted(recordings):
        size = os.path.getsize(f)
        print(f"   - {f}: {size:,} bytes")
        
        # Try to identify the stream
        if "alice" in f:
            print("     └─ Stream: alice (H264)")
        elif "bob" in f:
            print("     └─ Stream: bob (VP8)")
else:
    print("❌ No recordings found!")
    
    # Print key lines from output
    print("\nKey events from output:")
    key_phrases = ["Room has", "Multi-Peer", "Adding recorder", "ERROR", 
                   "Creating pipeline", "Requesting stream", "Handling message",
                   "Recording to:", "Failed"]
    
    for line in lines:
        if any(phrase in line for phrase in key_phrases):
            print(f"   {line}")

print("\n" + "="*70)