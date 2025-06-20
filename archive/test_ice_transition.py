#!/usr/bin/env python3
"""Test to understand why ICE stays in NEW state"""

import subprocess
import time
import re
import sys

print("Debugging ICE Connection State")
print("=" * 70)

# Enable GStreamer debugging for ICE
env = {
    'GST_DEBUG': 'webrtcice:5,webrtcbin:4',
    'PATH': '/usr/bin:/bin'
}

proc = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'ice_test',
    '--record-room',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)

# Monitor for specific ICE events
start = time.time()
ice_events = []

while time.time() - start < 10:
    line = proc.stdout.readline()
    if not line:
        if proc.poll() is not None:
            break
        continue
    
    # Look for ICE-related messages
    if 'ice' in line.lower() or 'ICE' in line:
        # Clean ANSI
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
        ice_events.append(clean)
        
        # Print key events
        if any(keyword in clean for keyword in ['NEW', 'CHECKING', 'CONNECTED', 'FAILED', 'add_stream']):
            print(clean)

proc.terminate()
proc.wait()

print("\n" + "=" * 70)
print(f"Found {len(ice_events)} ICE-related events")
print("\nKey observations:")

# Check for common issues
if any('add_stream' in event for event in ice_events):
    print("✓ ICE agent received stream")
else:
    print("✗ No add_stream event - ICE agent might not be initialized properly")

if any('remote_candidate' in event.lower() for event in ice_events):
    print("✓ Remote candidates received")
else:
    print("✗ No remote candidates processed")

if any('CHECKING' in event for event in ice_events):
    print("✓ ICE moved to CHECKING state")
else:
    print("✗ ICE never started checking - likely TURN/STUN issue")