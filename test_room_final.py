#\!/usr/bin/env python3
"""
Final test of room recording
"""

import subprocess
import time
import sys
import os
import glob

# Clean up
for f in glob.glob("room_*.ts") + glob.glob("room_*.mkv"):
    os.remove(f) if os.path.exists(f) else None

print("ROOM RECORDING TEST")
print("="*60)
print("Command: python3 publish.py --room testroom123 --record room --record-room --password false --noaudio")
print()

# Run with real-time output
proc = subprocess.Popen([
    sys.executable, 'publish.py',
    '--room', 'testroom123', 
    '--record', 'room',
    '--record-room',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

start = time.time()
duration = 30

# Read output
while time.time() - start < duration:
    line = proc.stdout.readline()
    if line:
        print(line.rstrip())
    
    if proc.poll() is not None:
        break

# Stop
proc.terminate()
proc.wait()

# Results
print("\n" + "="*60)
files = glob.glob("room_*.ts") + glob.glob("room_*.mkv")
if files:
    print(f"✅ SUCCESS - Found {len(files)} recordings:")
    for f in files:
        print(f"  {f}: {os.path.getsize(f):,} bytes")
else:
    print("❌ FAILED - No recordings found")
EOF < /dev/null
