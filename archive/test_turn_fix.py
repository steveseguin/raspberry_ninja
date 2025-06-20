#!/usr/bin/env python3
"""Test TURN fix"""

import subprocess
import time
import re

print("Testing TURN server fix for room recording...")
print("=" * 70)

proc = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'turn_fix_test',
    '--record-room',
    '--password', 'false',
    '--noaudio',
    '--debug'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Monitor output
start = time.time()
turn_formatted = False
no_username_error = False
ice_checking = False
connection_success = False

print("\nMonitoring output for 30 seconds...")
print("-" * 70)

while time.time() - start < 30:
    line = proc.stdout.readline()
    if not line:
        if proc.poll() is not None:
            break
        continue
    
    # Clean ANSI codes
    clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
    
    # Show key lines
    if any(keyword in clean for keyword in ["TURN", "turn", "ERROR", "ICE", "Recording started", "Connection state"]):
        print(clean)
    
    # Check for proper TURN formatting
    if "Using VDO.Ninja TURN:" in clean and "@" in clean:
        turn_formatted = True
        print("\n✅ TURN URL is properly formatted with credentials!\n")
    
    # Check for errors
    if "No username specified" in clean:
        no_username_error = True
        print("\n❌ ERROR: TURN server still missing username\n")
    
    # Check ICE states
    if "ICE_CONNECTION_STATE_CHECKING" in clean:
        ice_checking = True
        print("\n✅ ICE is checking candidates (TURN working)\n")
    
    # Check success
    if "Recording started" in clean:
        connection_success = True
        print("\n✅ SUCCESS! Recording has started!\n")
        time.sleep(3)  # Let it record a bit
        break

# Clean up
proc.terminate()
proc.wait()

print("\n" + "=" * 70)
print("Test Results:")
print(f"  TURN URL formatted correctly: {'✅ Yes' if turn_formatted else '❌ No'}")
print(f"  Username error: {'❌ Yes (BAD)' if no_username_error else '✅ No (GOOD)'}")
print(f"  ICE checking state: {'✅ Yes' if ice_checking else '❌ No'}")
print(f"  Recording started: {'✅ Yes' if connection_success else '❌ No'}")

if turn_formatted and not no_username_error:
    print("\n✅ TURN configuration is fixed!")
else:
    print("\n❌ TURN configuration still has issues")