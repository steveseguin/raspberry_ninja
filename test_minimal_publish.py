#!/usr/bin/env python3
"""
Minimal test to check if video is being sent
"""

import subprocess
import sys
import time
import signal

def signal_handler(sig, frame):
    print('\nStopping...')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

print("Starting minimal VP8 test...")
print("View at: https://vdo.ninja/?view=5566281&password=false")
print("-" * 60)

# Run with explicit VP8 and debug
cmd = [
    sys.executable, 
    "publish.py",
    "--test",
    "--vp8",  # Force VP8
    "--streamid", "5566281",
    "--password", "false",
    "--bitrate", "1000",  # Lower bitrate for testing
    "--width", "640",
    "--height", "480",
    "--framerate", "30"
]

print(f"Command: {' '.join(cmd)}")
print("-" * 60)

# Run and capture output
process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                         universal_newlines=True, bufsize=1)

# Track some key events
start_time = time.time()
stats_count = 0
connected = False

try:
    for line in iter(process.stdout.readline, ''):
        line = line.strip()
        if line:
            print(line)
            
            # Track key events
            if "Peer connection established" in line:
                connected = True
                print(f"\n*** CONNECTED after {time.time() - start_time:.1f} seconds ***\n")
                
            if "Network quality" in line:
                stats_count += 1
                if stats_count % 10 == 0:
                    print(f"\n*** Stats update #{stats_count} after {time.time() - start_time:.1f} seconds ***\n")
                    
            if "VP8" in line and ("encoder" in line or "target-bitrate" in line):
                print(f"\n*** VP8 INFO: {line} ***\n")
                
except KeyboardInterrupt:
    print("\nInterrupted")
finally:
    process.terminate()
    process.wait()
    
print(f"\nTest ran for {time.time() - start_time:.1f} seconds")
print(f"Connected: {connected}")
print(f"Stats updates: {stats_count}")