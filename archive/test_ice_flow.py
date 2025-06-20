#!/usr/bin/env python3
"""
Test ICE candidate flow in room recording
"""

import subprocess
import time
import re

print("Testing ICE candidate flow...")
print("="*60)

# Run the command
proc = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'test',
    '--record-room',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Track events
events = []
start = time.time()

# Read for 15 seconds
while time.time() - start < 15:
    line = proc.stdout.readline()
    if not line:
        if proc.poll() is not None:
            break
        continue
        
    # Clean line
    clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
    
    # Track key events
    if any(x in clean for x in ['Answer created', 'candidates', 'ICE', 'session', 'Connection state']):
        timestamp = time.time() - start
        events.append((timestamp, clean))
        print(f"{timestamp:5.1f}s: {clean}")

proc.terminate()
proc.wait()

# Analyze
print("\n" + "="*60)
print("ANALYSIS:")

# Check sequence
answer_time = None
ice_send_times = []
session_refs = []

for t, event in events:
    if 'Answer created' in event:
        answer_time = t
    elif 'candidates' in event and 'message was sent' in event:
        ice_send_times.append(t)
    if 'session' in event:
        # Extract session ID
        import re
        match = re.search(r'"session":\s*"([^"]*)"', event)
        if match:
            session_refs.append((t, match.group(1)))

print(f"\nAnswer created at: {answer_time:.1f}s" if answer_time else "No answer created")
print(f"ICE candidates sent at: {[f'{t:.1f}s' for t in ice_send_times]}")

if session_refs:
    print("\nSession IDs:")
    for t, sid in session_refs[:5]:
        print(f"  {t:.1f}s: {sid[:20]}...")

# Check for issues
if answer_time and ice_send_times:
    if any(t < answer_time for t in ice_send_times):
        print("\n⚠️  ERROR: ICE candidates sent before answer!")