#!/usr/bin/env python3
"""
Debug TURN configuration
"""

import subprocess
import time
import re
import signal
import sys

print("TESTING TURN CONFIGURATION")
print("=" * 70)

# Start the process
proc = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'turn_debug',
    '--record-room',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Monitor output for 15 seconds
start = time.time()
turn_found = False
ice_checking = False
connected = False

def signal_handler(sig, frame):
    print("\nStopping test...")
    proc.terminate()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

try:
    while time.time() - start < 15:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
        
        # Clean ANSI
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
        print(clean)
        
        # Check for TURN usage
        if "Using VDO.Ninja TURN" in clean:
            turn_found = True
            print("\n✅ TURN servers automatically configured!\n")
        elif "ICE connection state" in clean and "CHECKING" in clean:
            ice_checking = True
            print("\n✅ ICE is checking candidates (TURN working)\n")
        elif "Recording started" in clean:
            connected = True
            print("\n✅ Connection established!\n")
            
except KeyboardInterrupt:
    pass

# Clean up
proc.terminate()
proc.wait()

print("\n" + "=" * 70)
print("Results:")
print(f"  TURN auto-configured: {'✅ Yes' if turn_found else '❌ No'}")
print(f"  ICE checking started: {'✅ Yes' if ice_checking else '❌ No'}")
print(f"  Connection established: {'✅ Yes' if connected else '❌ No'}")

if not turn_found:
    print("\n❌ TURN was not automatically configured!")
    print("This means the room_recording flag is not being detected properly.")