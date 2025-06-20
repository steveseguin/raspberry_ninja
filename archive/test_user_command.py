#!/usr/bin/env python3
"""Test the exact user command"""

import subprocess
import time
import threading
import re

print("Running user's exact command...")
print("=" * 70)
print("python3 publish.py --room testroom123 --record myprefix --record-room --password false --noaudio --debug")
print()

proc = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'myprefix',
    '--record-room',
    '--password', 'false',
    '--noaudio',
    '--debug'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Read output in thread
def monitor_output():
    ice_states = []
    connection_states = []
    turn_found = False
    recording_started = False
    
    for i in range(200):  # Read up to 200 lines
        line = proc.stdout.readline()
        if not line:
            break
            
        # Clean ANSI
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
        
        # Print important lines
        if any(kw in clean for kw in ["TURN", "ERROR", "ICE", "Connection", "Recording", "Failed", "CHECKING"]):
            print(clean)
            
        # Track states
        if "Using VDO.Ninja TURN" in clean:
            turn_found = True
        if "ICE connection state:" in clean:
            ice_states.append(clean)
        if "Connection state:" in clean:
            connection_states.append(clean)
        if "Recording started" in clean:
            recording_started = True
            print("\n✅ SUCCESS! Recording started!\n")
            
    print("\n" + "-" * 70)
    print("Summary:")
    print(f"  TURN configured: {'✅ Yes' if turn_found else '❌ No'}")
    print(f"  Recording started: {'✅ Yes' if recording_started else '❌ No'}")
    
    if ice_states:
        print("\n  ICE states seen:")
        for state in ice_states[-3:]:  # Last 3 states
            print(f"    {state}")
            
    if connection_states:
        print("\n  Connection states seen:")
        for state in connection_states[-3:]:  # Last 3 states
            print(f"    {state}")

# Start monitoring
t = threading.Thread(target=monitor_output)
t.start()

# Wait 20 seconds
t.join(timeout=20)

# Clean up
print("\nStopping test...")
proc.terminate()
try:
    proc.wait(timeout=2)
except:
    proc.kill()

print("\nTest complete.")