#!/usr/bin/env python3
"""
Manual test for multi-peer recording
"""

import subprocess
import sys
import time

# Generate unique room name
room_name = f"multipeer_test_{int(time.time())}"

print(f"Room: {room_name}")
print("\nStart publishers in separate terminals:")
print(f"\npython3 publish.py --test --room {room_name} --stream alice --noaudio --h264")
print(f"python3 publish.py --test --room {room_name} --stream bob --noaudio --vp8")
print(f"python3 publish.py --test --room {room_name} --stream charlie --noaudio --vp9")

print("\nPress Enter when publishers are running...")
input()

print("\nStarting recorder with multi-peer mode...")
cmd = [
    sys.executable, "publish.py",
    "--room", room_name,
    "--record", "multipeer_test",
    "--record-room",
    "--noaudio",
    "--bitrate", "2000"
]

print("Command:", " ".join(cmd))
print("\nPress Ctrl+C to stop recording\n")
print("-"*60)

# Run with output visible
subprocess.run(cmd)