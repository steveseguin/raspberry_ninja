#!/usr/bin/env python3
"""Test room recording with relay-only mode"""

import subprocess
import time
import re

print("Testing room recording with relay-only mode (forces TURN)...")
print("=" * 70)

cmd = [
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'relay_test',
    '--record-room',
    '--password', 'false',
    '--noaudio',
    '--ice-transport-policy', 'relay',  # Force TURN
    '--debug'
]

print("Command:", ' '.join(cmd))
print("\nThis forces all traffic through TURN servers...\n")

proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Monitor for 20 seconds
start = time.time()
ice_states = []
pad_events = []
recording = False

while time.time() - start < 20:
    line = proc.stdout.readline()
    if not line:
        if proc.poll() is not None:
            break
        continue
    
    # Clean ANSI
    clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
    
    # Track important events
    if "ICE connection state:" in clean:
        ice_states.append(clean)
        print(f"ICE: {clean}")
    elif "ICE transport policy:" in clean:
        print(f"Policy: {clean}")
    elif "New pad added:" in clean:
        pad_events.append(clean)
        print(f"PAD: {clean}")
    elif "Recording started" in clean:
        recording = True
        print(f"✅ {clean}")
    elif "Failed" in clean or "ERROR" in clean:
        print(f"❌ {clean}")
    elif "Room Recording Status" in clean:
        print(f"\nSTATUS: {clean}")
    elif "tUur6wt:" in clean or "KLvZZdT:" in clean:
        print(f"  {clean}")

proc.terminate()
proc.wait()

print("\n" + "=" * 70)
print("Results:")
print(f"  Recording started: {'✅ Yes' if recording else '❌ No'}")
print(f"  Pads received: {len(pad_events)}")

if ice_states:
    print("\nICE state progression:")
    for state in ice_states[-5:]:  # Last 5 states
        print(f"  - {state}")

if not recording and "NEW" in str(ice_states):
    print("\n⚠️  ICE stuck in NEW state - TURN servers not reachable")
    print("Possible solutions:")
    print("1. Check firewall - ensure outbound UDP 3478 is allowed")
    print("2. Try TURNS on port 443: --turn-server 'turns://steve:setupYourOwnPlease@www.turn.obs.ninja:443'")
    print("3. The stream might not exist in the room anymore")