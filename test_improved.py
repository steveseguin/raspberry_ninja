#!/usr/bin/env python3
"""
Test improved room recording
"""

import subprocess
import time
import glob
import os
import re

# Clean up
for f in glob.glob("improved_*.ts") + glob.glob("improved_*.mkv"):
    try:
        os.remove(f)
    except:
        pass

print("TESTING IMPROVED ROOM RECORDING")
print("="*70)

# Run the command
proc = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'improved',
    '--record-room',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Capture output
start = time.time()
important_events = []

while time.time() - start < 30:
    line = proc.stdout.readline()
    if not line and proc.poll() is not None:
        break
        
    if line:
        # Clean ANSI codes
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
        
        # Print important lines
        if any(x in clean for x in ['Adding recorder', 'Answer', 'ICE', 'Connection', 
                                    'Recording', 'ERROR', 'STUN', 'gathering']):
            print(clean)
            important_events.append(clean)

# Stop
proc.terminate()
proc.wait()

# Results
print("\n" + "="*70)
print("RESULTS:")

files = glob.glob("improved_*.ts") + glob.glob("improved_*.mkv")
if files:
    print(f"\n✅ Found {len(files)} recordings:")
    for f in files:
        print(f"  {f}: {os.path.getsize(f):,} bytes")
else:
    print("\n❌ No recordings found")
    
    # Analyze failure
    print("\nDIAGNOSTICS:")
    ice_states = [e for e in important_events if 'ICE' in e]
    if ice_states:
        print("\nICE States:")
        for state in ice_states[-5:]:  # Last 5 ICE states
            print(f"  {state}")
    
    connection_states = [e for e in important_events if 'Connection state' in e]
    if connection_states:
        print("\nConnection States:")
        for state in connection_states[-3:]:  # Last 3 connection states
            print(f"  {state}")