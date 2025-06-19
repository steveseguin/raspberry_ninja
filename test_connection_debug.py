#!/usr/bin/env python3
"""Debug WebRTC connection failures"""

import subprocess
import sys
import time
import os
import signal

print("Debugging WebRTC connection failures...")
print("Testing with relay-only policy to force TURN usage")
print("-" * 60)

# Start the process
proc = subprocess.Popen(
    [sys.executable, "publish.py", "--room", "testroom123", "--record-room", 
     "--password", "false", "--noaudio", "--ice-transport-policy", "relay"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True,
    bufsize=1,
    preexec_fn=os.setsid
)

# Read output for 15 seconds
start_time = time.time()
ice_states = []
connection_states = []
relay_candidates = 0
errors = []

try:
    while time.time() - start_time < 15:
        line = proc.stdout.readline()
        if not line:
            break
            
        # Look for relevant messages
        if "ICE state:" in line:
            ice_states.append(line.rstrip())
        elif "Connection state:" in line:
            connection_states.append(line.rstrip())
        elif "relay candidate" in line:
            relay_candidates += 1
            if relay_candidates <= 3:  # Print first few
                print(f"✅ {line.rstrip()}")
        elif "ICE transport policy" in line:
            print(f"📋 {line.rstrip()}")
        elif "Pipeline error" in line or "Failed" in line:
            errors.append(line.rstrip())
            
except KeyboardInterrupt:
    pass

# Stop the process group
print("\nStopping test...")
try:
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
except:
    proc.terminate()

time.sleep(1)
if proc.poll() is None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except:
        proc.kill()

print("\nTest Results:")
print(f"- Relay candidates generated: {relay_candidates}")
print(f"- ICE states seen: {len(ice_states)}")
print(f"- Connection states seen: {len(connection_states)}")

if ice_states:
    print("\nICE State Progression:")
    for state in ice_states[-5:]:  # Last 5 states
        print(f"  {state}")
        
if connection_states:
    print("\nConnection State Progression:")
    for state in connection_states[-5:]:  # Last 5 states
        print(f"  {state}")
        
if errors:
    print("\nErrors:")
    for err in errors[:5]:  # First 5 errors
        print(f"  ❌ {err}")