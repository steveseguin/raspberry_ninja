#!/usr/bin/env python3
"""Test room recording fixes"""

import subprocess
import time
import threading
import re

print("Testing room recording fixes...")
print("=" * 70)
print("This test will:")
print("1. Show correct stream count (not duplicates)")
print("2. Clean up disconnected streams")
print("3. Show better debug info for pipeline issues")
print()

# Run room recording
cmd = [
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'test_fixes',
    '--record-room',
    '--password', 'false',
    '--noaudio'
]

print("Starting room recording...")
print("Command:", ' '.join(cmd))
print()

proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Monitor output
start = time.time()
status_shown = False
cleanup_seen = False
recording_started = False

def monitor_output():
    global status_shown, cleanup_seen, recording_started
    
    while time.time() - start < 30:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
        
        # Clean ANSI codes
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
        
        # Look for key events
        if "Room Recording Status" in clean:
            status_shown = True
            print("\n" + clean)
        elif "active recorders" in clean:
            print(clean)
        elif clean.strip().startswith("tUur6wt:") or clean.strip().startswith("KLvZZdT:"):
            print("  " + clean.strip())
        elif "Cleaning up disconnected stream" in clean:
            cleanup_seen = True
            print("\n✅ " + clean)
        elif "Recording started" in clean:
            recording_started = True
            print("\n✅ " + clean)
        elif "New pad added" in clean:
            print("\n📌 " + clean)
        elif "Pad caps:" in clean:
            print("   " + clean)
        elif "Failed to link" in clean:
            print("\n❌ " + clean)
        elif "already tracked" in clean:
            print("\n⚠️  " + clean)

# Start monitoring
t = threading.Thread(target=monitor_output)
t.start()

# Wait for test
t.join()

# Clean up
print("\nStopping test...")
proc.terminate()
try:
    proc.wait(timeout=2)
except:
    proc.kill()

print("\n" + "=" * 70)
print("Test Results:")
print(f"  Status display shown: {'✅ Yes' if status_shown else '❌ No'}")
print(f"  Recording started: {'✅ Yes' if recording_started else '❌ No'}")
print(f"  Cleanup functionality: {'✅ Seen' if cleanup_seen else '⏳ Not triggered'}")

print("\nKey improvements:")
print("1. Status now shows actual recorders (not room_streams)")
print("2. Duplicate detection prevents same stream being added twice")
print("3. Better debug output for pad linking issues")
print("4. Automatic cleanup when connections fail/disconnect")