#\!/usr/bin/env python3
"""Final test for room recording with parse_bin fix"""

import subprocess
import time
import os
import signal

print("🧪 Testing Room Recording with Parse Bin Fix")
print("=" * 70)

# First, let's test single stream to confirm it works
print("\n1. Testing single stream recording (baseline)...")
proc1 = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--view', 'tUur6wt',
    '--record', 'single_baseline',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# Monitor for 10 seconds
start = time.time()
single_success = False
while time.time() - start < 10:
    line = proc1.stdout.readline()
    if not line:
        if proc1.poll() is not None:
            break
        continue
    
    if "Recording started" in line or "Video recording configured" in line:
        single_success = True
        print(f"  ✅ {line.strip()}")
        break
    elif "ICE: Connected" in line:
        print(f"  ✅ {line.strip()}")

proc1.terminate()
proc1.wait()

if single_success:
    # Check if file was created
    files = [f for f in os.listdir('.') if f.startswith('single_baseline_') and os.path.isfile(f)]
    if files:
        print(f"  ✅ Recording file created: {files[0]}")
        os.remove(files[0])  # Clean up
    else:
        print("  ❌ No recording file found")
else:
    print("  ❌ Single stream recording failed")

print("\n" + "-" * 70)

# Now test room recording
print("\n2. Testing room recording with parse_bin fix...")
proc2 = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'room_fixed',
    '--record-room',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# Monitor for 15 seconds
start = time.time()
room_success = False
ice_connected = False
pad_added = False
pipeline_created = False

while time.time() - start < 15:
    line = proc2.stdout.readline()
    if not line:
        if proc2.poll() is not None:
            break
        continue
    
    print(f"  {line.strip()}")
    
    if "Pipeline:" in line:
        pipeline_created = True
    elif "New pad added" in line:
        pad_added = True
    elif "ICE: Connected" in line or "ICE connected" in line:
        ice_connected = True
    elif "Recording started" in line:
        room_success = True
        break
    elif "Failed to link recording pipeline" in line:
        print("  ❌ PIPELINE LINKING FAILED\!")
    elif "not-linked" in line:
        print("  ❌ PIPELINE NOT-LINKED ERROR\!")

# Give it a bit more time if we got a pad
if pad_added and not room_success:
    time.sleep(2)

proc2.terminate()
proc2.wait()

# Check for recording files
print("\n" + "-" * 70)
print("RESULTS:")
print(f"  Pipeline created: {'✅' if pipeline_created else '❌'}")
print(f"  ICE connected: {'✅' if ice_connected else '❌'}")  
print(f"  Pad received: {'✅' if pad_added else '❌'}")
print(f"  Recording started: {'✅' if room_success else '❌'}")

# Check for files
files = [f for f in os.listdir('.') if f.startswith('room_fixed_') and os.path.isfile(f)]
if files:
    print(f"\n  ✅ Recording files created:")
    for f in files:
        size = os.path.getsize(f) / 1024
        print(f"     - {f} ({size:.1f} KB)")
        os.remove(f)  # Clean up
else:
    print("\n  ❌ No recording files found")

print("\n" + "=" * 70)
if room_success:
    print("🎉 ROOM RECORDING WORKS\!")
else:
    print("❌ Room recording still has issues")
    if ice_connected and pad_added and not room_success:
        print("   → Pipeline linking problem persists")
    elif not ice_connected:
        print("   → ICE connection failed")
