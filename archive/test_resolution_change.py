#!/usr/bin/env python3
"""Test recording with resolution changes"""

import subprocess
import time
import os

print("Testing VP8 recording with potential resolution changes...")
print("=" * 70)

# Start recording
proc = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--view', 'tUur6wt',
    '--record', 'res_change_test',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Monitor output
start = time.time()
errors = []
success = False

print("Monitoring for 30 seconds...")
while time.time() - start < 30:
    line = proc.stdout.readline()
    if not line:
        if proc.poll() is not None:
            break
        continue
    
    # Print important lines
    if any(x in line for x in ['error:', 'ERROR', 'WARN', 'Failed', 'not-negotiated', 
                                'Caps changes', 'Recording', 'configured', 'ICE']):
        print(f"[{time.time()-start:.1f}s] {line.strip()}")
        
    if "Caps changes are not supported" in line:
        errors.append("Resolution change error detected")
    elif "not-negotiated" in line:
        errors.append("Pipeline negotiation failed")
    elif "Recording started" in line or "Video recording configured" in line:
        success = True

proc.terminate()
proc.wait()

print("\n" + "=" * 70)
print("RESULTS:")
print(f"  Recording started: {'✅' if success else '❌'}")
print(f"  Errors detected: {'❌ ' + ', '.join(errors) if errors else '✅ None'}")

# Check for files
files = []
for pattern in ['res_change_test*.mkv', 'res_change_test*.webm', 
                 'res_change_test*.m3u8', 'res_change_test*.ts']:
    files.extend([f for f in os.listdir('.') if f.startswith('res_change_test')])

if files:
    print(f"\n  Files created:")
    for f in set(files):
        size = os.path.getsize(f) / 1024
        print(f"    - {f} ({size:.1f} KB)")
        
    # Validate the largest file
    largest = max(files, key=os.path.getsize)
    print(f"\n  Validating {largest}...")
    result = subprocess.run(['python3', 'validate_media_file.py', largest], 
                          capture_output=True, text=True)
    print(f"  {result.stdout.strip()}")