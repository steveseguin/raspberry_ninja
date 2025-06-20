#\!/usr/bin/env python3
"""Test recording with a simpler setup"""

import subprocess
import time
import sys
import os

# Test with a known public room that has test streams
test_room = "testroom123"  # Common test room
output_dir = "test_recordings"

# Create output directory
os.makedirs(output_dir, exist_ok=True)

print("Starting room recording test...")
print(f"Room: {test_room}")
print(f"Output directory: {output_dir}")

# Run the recording command
cmd = [
    sys.executable, "publish.py",
    "--room", test_room,
    "--record-room",
    "--password", "false",
    "--audio",
    "--record", f"{output_dir}/recording"
]

print(f"\nCommand: {' '.join(cmd)}")
print("\nStarting recording for 30 seconds...")

# Start the process
process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Let it run for 30 seconds
start_time = time.time()
timeout = 30

try:
    while time.time() - start_time < timeout:
        # Read output
        line = process.stdout.readline()
        if line:
            print(line.rstrip())
        elif process.poll() is not None:
            break
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nInterrupted by user")

# Stop the process
print("\nStopping recording...")
process.terminate()
process.wait(timeout=5)

# Check for output files
print("\nChecking for recorded files...")
for root, dirs, files in os.walk(output_dir):
    for file in files:
        filepath = os.path.join(root, file)
        size = os.path.getsize(filepath)
        print(f"  {filepath}: {size} bytes")

# Also check current directory
mkv_files = [f for f in os.listdir(".") if f.endswith(".mkv")]
if mkv_files:
    print("\nMKV files in current directory:")
    for f in mkv_files:
        size = os.path.getsize(f)
        print(f"  {f}: {size} bytes")
