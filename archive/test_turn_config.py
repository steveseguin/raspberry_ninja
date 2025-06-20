#!/usr/bin/env python3
"""Test TURN server configuration in subprocess"""

import subprocess
import sys
import time
import signal
import os

print("Testing TURN server configuration...")

# Start the process with relay-only policy
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
turn_config_seen = False
relay_candidates_seen = False

try:
    while time.time() - start_time < 15:
        line = proc.stdout.readline()
        if not line:
            break
            
        # Filter for TURN-related messages
        if any(phrase in line for phrase in [
            "TURN server configured",
            "Using default TURN server",
            "ICE transport policy",
            "Generated.*relay candidate",
            "RELAY only",
            "turn-cae1.vdo.ninja"
        ]):
            print(line.rstrip())
            
            if "TURN server configured" in line or "Using default TURN server" in line:
                turn_config_seen = True
            if "relay candidate" in line:
                relay_candidates_seen = True
                
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
print(f"- TURN server configured: {'✅ Yes' if turn_config_seen else '❌ No'}")
print(f"- Relay candidates generated: {'✅ Yes' if relay_candidates_seen else '❌ No'}")