#!/usr/bin/env python3
"""
Print the actual room listing structure
"""

import subprocess
import sys
import time
import os
import asyncio
import json

room = f"listing{int(time.time())}"

# Start publishers
print(f"Starting publishers in room: {room}")

pub1 = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "alice",
    "--noaudio", "--h264"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

time.sleep(2)

pub2 = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "bob", 
    "--noaudio", "--vp8"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

time.sleep(5)

# Connect directly with websockets
async def check_listing():
    import websockets
    import ssl
    
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    async with websockets.connect("wss://wss.vdo.ninja:443", ssl=ssl_context) as ws:
        # Join room
        await ws.send(json.dumps({"request": "joinroom", "roomid": room}))
        print(f"\nJoined room: {room}")
        
        # Get listing
        msg = await ws.recv()
        data = json.loads(msg)
        
        if data.get('request') == 'listing':
            print("\nReceived listing:")
            print(json.dumps(data, indent=2))
            
            if 'list' in data:
                print(f"\n{len(data['list'])} members in room:")
                for i, member in enumerate(data['list']):
                    print(f"\nMember {i}:")
                    for k, v in member.items():
                        print(f"  {k}: {v}")

# Run check
asyncio.run(check_listing())

# Cleanup
pub1.terminate()
pub2.terminate()