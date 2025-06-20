#!/usr/bin/env python3
"""
Test room timing - wait longer for publishers
"""

import subprocess
import sys
import time
import os
import asyncio
import json

room = f"timing{int(time.time())}"

# Start publishers with explicit parameters
print(f"Starting publishers in room: {room}")

pub1_cmd = [
    sys.executable, "publish.py",
    "--room", room,
    "--stream", "alice",
    "--noaudio", 
    "--test"  # test video source
]
print(f"Publisher 1: {' '.join(pub1_cmd)}")

pub1 = subprocess.Popen(pub1_cmd)

print("Waiting 10 seconds for first publisher...")
time.sleep(10)

# Check room now
async def check_room():
    import websockets
    import ssl
    
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    async with websockets.connect("wss://wss.vdo.ninja:443", ssl=ssl_context) as ws:
        # Join room
        await ws.send(json.dumps({"request": "joinroom", "roomid": room}))
        
        # Get listing
        msg = await ws.recv()
        data = json.loads(msg)
        
        if data.get('request') == 'listing':
            print(f"\nRoom listing: {len(data.get('list', []))} members")
            for member in data.get('list', []):
                print(f"  Member: {member}")

print("\nChecking room status...")
asyncio.run(check_room())

# Now add second publisher
pub2_cmd = [
    sys.executable, "publish.py",
    "--room", room,
    "--stream", "bob",
    "--noaudio",
    "--test"
]
print(f"\nPublisher 2: {' '.join(pub2_cmd)}")

pub2 = subprocess.Popen(pub2_cmd)

print("Waiting 10 more seconds...")
time.sleep(10)

# Check again
print("\nChecking room status again...")
asyncio.run(check_room())

# Now try room recording
print("\n\nStarting room recorder...")
rec = subprocess.Popen([
    sys.executable, "publish.py",
    "--room", room,
    "--record", "timing",
    "--record-room",
    "--noaudio"
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Monitor output
print("\nMonitoring recorder output...")
start = time.time()
while time.time() - start < 15:
    line = rec.stdout.readline()
    if line and any(x in line for x in ["members", "Will record", "Multi-Peer", "streamID"]):
        print(f">>> {line.rstrip()}")

# Cleanup
rec.terminate()
pub1.terminate()
pub2.terminate()

time.sleep(2)

# Check files
recordings = glob.glob("timing_*.ts") + glob.glob("timing_*.mkv")
if recordings:
    print(f"\n✅ Found {len(recordings)} recordings")
else:
    print("\n❌ No recordings found")