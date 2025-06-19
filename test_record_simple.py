#!/usr/bin/env python3
"""
Simple test of room recording
"""

import subprocess
import time
import sys
import glob
import os

# Clean up
for f in glob.glob("stest_*.ts") + glob.glob("stest_*.mkv"):
    os.remove(f)

# Start a single stream recorder (not room mode) to verify basic functionality
print("Testing single stream recording first...")
p1 = subprocess.Popen([sys.executable, "publish.py", "--test", "--stream", "test1", "--noaudio", "--password", "false"])
time.sleep(3)

p2 = subprocess.Popen([sys.executable, "publish.py", "--view", "test1", "--record", "stest", "--noaudio", "--password", "false"])
time.sleep(8)

p2.terminate()
p1.terminate()
time.sleep(2)

files = glob.glob("stest*.ts") + glob.glob("stest*.mkv")
if files:
    print(f"✅ Single stream recording works: {files[0]} ({os.path.getsize(files[0]):,} bytes)")
else:
    print("❌ Single stream recording failed")

# Now test room recording
print("\nTesting room recording...")
room = "roomtest"

# Start publisher
p1 = subprocess.Popen([
    sys.executable, "publish.py", 
    "--test", "--room", room, "--stream", "alice",
    "--noaudio", "--password", "false"
])
time.sleep(3)

# Start room recorder - capture output
p2 = subprocess.Popen([
    sys.executable, "publish.py",
    "--room", room, "--record", "stest", "--record-room",
    "--noaudio", "--password", "false"
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Monitor for 10 seconds
start = time.time()
while time.time() - start < 10:
    line = p2.stdout.readline()
    if line and any(x in line for x in ["Room has", "Multi-Peer", "Will record", "ERROR"]):
        print(f">>> {line.rstrip()}")

p2.terminate()
p1.terminate()
time.sleep(2)

# Check files
room_files = glob.glob(f"{room}_*.ts") + glob.glob(f"{room}_*.mkv") + glob.glob("stest_*.ts") + glob.glob("stest_*.mkv")
if room_files:
    print(f"\n✅ Room recording created files:")
    for f in room_files:
        print(f"   {f}")
else:
    print("\n❌ No room recording files created")