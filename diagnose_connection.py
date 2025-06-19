#!/usr/bin/env python3
"""Diagnose why room recording isn't connecting"""

import subprocess
import socket
import time

print("Room Recording Connection Diagnostics")
print("=" * 70)

# Test 1: Check if we can reach TURN servers
print("\n1. Testing TURN server connectivity...")
turn_servers = [
    ("turn-cae1.vdo.ninja", 3478),
    ("turn-usw2.vdo.ninja", 3478),
    ("www.turn.obs.ninja", 443)
]

for host, port in turn_servers:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print(f"  ✅ {host}:{port} - Reachable")
        else:
            print(f"  ❌ {host}:{port} - Not reachable (error: {result})")
    except Exception as e:
        print(f"  ❌ {host}:{port} - Error: {e}")

# Test 2: Check what streams are in the room
print("\n2. Checking room contents...")
proc = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--view', 'dummy',  # Just connect to see room list
    '--password', 'false',
    '--noaudio',
    '--novideo'
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# Read output for room members
room_members = []
for _ in range(50):
    line = proc.stdout.readline()
    if not line:
        break
    if "- Stream:" in line:
        room_members.append(line.strip())
    if "Room has" in line:
        print(f"  {line.strip()}")

proc.terminate()
proc.wait()

if room_members:
    print("  Found streams:")
    for member in room_members:
        print(f"    {member}")
else:
    print("  ❌ No streams found in room")

# Test 3: Try connecting with manual TURN
print("\n3. Testing with manual TURN configuration...")
print("  Using: turns://steve:setupYourOwnPlease@www.turn.obs.ninja:443")

proc2 = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'manual_turn_test',
    '--record-room',
    '--turn-server', 'turns://steve:setupYourOwnPlease@www.turn.obs.ninja:443',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# Monitor for 10 seconds
start = time.time()
connection_made = False

while time.time() - start < 10:
    line = proc2.stdout.readline()
    if not line:
        continue
    
    if "Recording started" in line:
        connection_made = True
        print("  ✅ Connection successful with TURNS!")
        break
    elif "CONNECTED" in line:
        print(f"  Progress: {line.strip()}")
    elif "FAILED" in line:
        print(f"  ❌ {line.strip()}")

proc2.terminate()
proc2.wait()

print("\n" + "=" * 70)
print("Diagnosis Summary:")
print("- If TURN servers are unreachable: firewall/network issue")
print("- If no streams in room: need an active publisher")
print("- If TURNS works but TURN doesn't: try using port 443")
print("\nTo publish a test stream to the room:")
print("python3 publish.py --room testroom123 --streamid test_stream --test")