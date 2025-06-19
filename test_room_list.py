#!/usr/bin/env python3
"""Test if we can see streams in the room"""

import subprocess
import time
import re
import json

print("CHECKING ROOM FOR ACTIVE STREAMS")
print("=" * 70)

# First, let's publish a test stream to the room
print("\n1. Publishing test stream to room 'testroom123'...")
publisher = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--view', 'test_publisher',
    '--streamid', 'test_stream_001',
    '--password', 'false',
    '--noaudio',
    '--novideo'  # Just presence, no actual media
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Wait for publisher to connect
time.sleep(3)

# Now try room recording
print("\n2. Starting room recording to see available streams...")
recorder = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'room_test',
    '--record-room',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Monitor recorder output
start = time.time()
streams_found = []
empty_room = False

while time.time() - start < 10:
    line = recorder.stdout.readline()
    if not line:
        if recorder.poll() is not None:
            break
        continue
    
    # Clean ANSI
    clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
    
    # Print interesting lines
    if any(keyword in clean for keyword in ["room", "stream", "peer", "Empty", "Found"]):
        print(f"RECORDER: {clean}")
    
    if "Empty room" in clean:
        empty_room = True
    elif "Found stream" in clean or "New stream" in clean:
        streams_found.append(clean)

# Clean up
print("\n3. Cleaning up...")
recorder.terminate()
publisher.terminate()
recorder.wait()
publisher.wait()

print("\n" + "=" * 70)
print("Results:")
print(f"  Room was empty: {'Yes' if empty_room else 'No'}")
print(f"  Streams found: {len(streams_found)}")
if streams_found:
    for s in streams_found:
        print(f"    - {s}")