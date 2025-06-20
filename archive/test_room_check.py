#!/usr/bin/env python3
"""
Quick check of room recording
"""

import subprocess
import time
import glob
import os
import sys

# Clean up old files
for f in glob.glob("roomcheck_*.ts") + glob.glob("roomcheck_*.mkv"):
    os.remove(f)

room = "checkroom"

print("Starting 2 publishers in room...")

# Start publishers
p1 = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "alice",
    "--noaudio", "--h264",
    "--password", "false"
])

time.sleep(2)

p2 = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "bob",
    "--noaudio", "--vp8",
    "--password", "false"
])

print("Waiting for publishers to connect...")
time.sleep(5)

print("\nStarting room recorder...")
rec = subprocess.Popen([
    sys.executable, "publish.py",
    "--room", room,
    "--record", "roomcheck",
    "--record-room",
    "--noaudio",
    "--password", "false"
])

print("Recording for 15 seconds...")
time.sleep(15)

print("\nStopping all processes...")
rec.terminate()
p1.terminate()
p2.terminate()
time.sleep(3)

# Check for files
print("\nChecking for recordings...")
files = glob.glob("roomcheck_*.ts") + glob.glob("roomcheck_*.mkv") + glob.glob(f"{room}_*.ts") + glob.glob(f"{room}_*.mkv")

if files:
    print(f"\n✅ Found {len(files)} files:")
    for f in files:
        size = os.path.getsize(f)
        print(f"   {f} - {size:,} bytes")
        
    # Try to validate
    try:
        from validate_media_file import validate_recording
        for f in files:
            if validate_recording(f, verbose=False):
                print(f"   ✅ {f} is valid")
            else:
                print(f"   ❌ {f} is invalid")
    except:
        pass
else:
    print("\n❌ No recordings found")
    
    # Show any recent files
    print("\nRecent .ts and .mkv files:")
    all_files = glob.glob("*.ts") + glob.glob("*.mkv")
    for f in sorted(all_files)[-10:]:
        mtime = os.path.getmtime(f)
        age = time.time() - mtime
        if age < 60:
            print(f"   {f} (created {int(age)}s ago)")