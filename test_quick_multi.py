#!/usr/bin/env python3
"""Quick test of multi-peer recording"""

import subprocess
import sys
import time
import glob
import os

# Clean up
os.system("rm -f quicktest_*.ts quicktest_*.mkv 2>/dev/null")

room = f"quicktest_{int(time.time())}"
print(f"Room: {room}")

# Start one publisher
print("Starting publisher...")
pub = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room, "--stream", "alice", "--noaudio", "--h264"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

time.sleep(5)

# Start recorder
print("\nStarting recorder with --record-room...")
print("-"*50)

rec = subprocess.Popen([
    sys.executable, "publish.py",
    "--room", room,
    "--record", "quicktest", 
    "--record-room",
    "--noaudio"
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Read output for 10 seconds
start = time.time()
while time.time() - start < 10:
    line = rec.stdout.readline()
    if line:
        # Check for key indicators
        if "Room recording mode:" in line:
            print(f">>> {line.strip()}")
        elif "Multi-Peer" in line:
            print(f">>> {line.strip()}")
        elif "🚀 Using Multi-Peer Client" in line:
            print(f">>> {line.strip()}")
        elif "📹 Adding recorder for stream:" in line:
            print(f">>> {line.strip()}")
        elif "Will record" in line:
            print(f">>> {line.strip()}")

# Stop
rec.terminate()
pub.terminate()
time.sleep(1)

# Check files
print("\nFiles created:")
for f in glob.glob("quicktest_*"):
    print(f" - {f} ({os.path.getsize(f):,} bytes)")

print("\nDone")