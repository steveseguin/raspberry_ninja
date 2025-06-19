#!/usr/bin/env python3
"""
Fix and test room recording
"""

import sys
import os
import time
import subprocess
import glob

# Test 1: Single stream recording (baseline)
print("Test 1: Single stream recording")
print("-" * 40)

# Clean up
for f in glob.glob("test1_*.ts") + glob.glob("test1_*.mkv"):
    os.remove(f)

# Start publisher
pub = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--stream", "stream1",
    "--noaudio", "--password", "false"
])
time.sleep(3)

# Start viewer/recorder
rec = subprocess.Popen([
    sys.executable, "publish.py",
    "--view", "stream1",
    "--record", "test1",
    "--noaudio", "--password", "false"
])
time.sleep(8)

# Stop
rec.terminate()
pub.terminate()
time.sleep(2)

# Check
files = glob.glob("test1_*.ts") + glob.glob("test1_*.mkv")
if files:
    print(f"✅ SUCCESS: Created {files[0]} ({os.path.getsize(files[0]):,} bytes)")
    # Validate
    from validate_media_file import validate_recording
    if validate_recording(files[0], verbose=False):
        print("✅ File is valid")
else:
    print("❌ FAILED: No files created")

# Test 2: Room recording with debugging
print("\n\nTest 2: Room recording")
print("-" * 40)

# Clean up
for f in glob.glob("test2_*.ts") + glob.glob("test2_*.mkv") + glob.glob("room2_*.ts") + glob.glob("room2_*.mkv"):
    os.remove(f)

room = "room2"

# Start publisher in room
print(f"Starting publisher in room '{room}'...")
pub = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "alice",
    "--noaudio", "--password", "false"
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Wait for publisher to be ready
for _ in range(20):
    line = pub.stdout.readline()
    if line and "WebSocket ready" in line:
        print("Publisher connected")
        break

time.sleep(2)

# Start room recorder
print(f"Starting room recorder...")
rec = subprocess.Popen([
    sys.executable, "publish.py",
    "--room", room,
    "--record", "test2",
    "--record-room",
    "--noaudio", "--password", "false"
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Monitor recorder
print("\nMonitoring recorder output:")
start = time.time()
saw_room_list = False
saw_multi_peer = False

while time.time() - start < 15:
    line = rec.stdout.readline()
    if not line:
        continue
    
    line = line.rstrip()
    
    # Print key messages
    if "Room has" in line:
        saw_room_list = True
        print(f"  {line}")
    elif "Multi-Peer" in line:
        saw_multi_peer = True
        print(f"  {line}")
    elif any(x in line for x in ["Will record", "Adding recorder", "Recording to"]):
        print(f"  {line}")
    elif "ERROR" in line:
        print(f"  ERROR: {line}")

# Stop
print("\nStopping...")
rec.terminate()
pub.terminate()
time.sleep(3)

# Results
print("\nResults:")
print(f"  Saw room list: {'✅' if saw_room_list else '❌'}")
print(f"  Multi-peer client created: {'✅' if saw_multi_peer else '❌'}")

# Check files
files = glob.glob("test2_*.ts") + glob.glob("test2_*.mkv") + glob.glob(f"{room}_*.ts") + glob.glob(f"{room}_*.mkv")
if files:
    print(f"\n✅ SUCCESS: Created {len(files)} file(s):")
    for f in files:
        print(f"  - {f} ({os.path.getsize(f):,} bytes)")
        if validate_recording(f, verbose=False):
            print("    ✅ Valid")
        else:
            print("    ❌ Invalid")
else:
    print("\n❌ FAILED: No room recording files created")

print("\nDone.")