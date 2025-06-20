#!/usr/bin/env python3
"""
Test the fixed room recording
"""

import subprocess
import sys
import time
import glob
import os
import signal

# Clean up
for f in glob.glob("fixed_*.ts") + glob.glob("fixed_*.mkv"):
    try:
        os.remove(f)
    except:
        pass

print("="*70)
print("TESTING FIXED ROOM RECORDING")
print("="*70)

proc = subprocess.Popen([
    sys.executable, 'publish.py',
    '--room', 'testroom123',
    '--record', 'fixed',
    '--record-room',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

# Monitor for 30 seconds
start_time = time.time()
lines = []

try:
    while time.time() - start_time < 30:
        # Read stdout
        line = proc.stdout.readline()
        if line:
            # Remove ANSI codes
            import re
            clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
            if any(x in clean_line for x in ['Room', 'Adding recorder', 'Answer', 
                                             'Recording', 'Connection', 'ICE', 
                                             'ERROR', 'Stream']):
                lines.append(clean_line)
                print(clean_line)
        
        # Check if process died
        if proc.poll() is not None:
            print(f"\nProcess exited with code: {proc.returncode}")
            # Get any remaining output
            remaining = proc.stdout.read()
            if remaining:
                print(remaining)
            break
            
except KeyboardInterrupt:
    print("\nInterrupted")

finally:
    # Stop the process
    proc.send_signal(signal.SIGTERM)
    time.sleep(2)
    if proc.poll() is None:
        proc.kill()

# Check for recordings
print("\n" + "="*70)
print("RESULTS:")
print("="*70)

files = glob.glob("fixed_*.ts") + glob.glob("fixed_*.mkv")
if files:
    print(f"\n✅ Found {len(files)} recordings:")
    for f in files:
        size = os.path.getsize(f)
        print(f"  {f}: {size:,} bytes")
else:
    print("\n❌ No recordings found")
    
print("\nKey events captured:")
for line in lines[-10:]:  # Last 10 important lines
    print(f"  {line}")