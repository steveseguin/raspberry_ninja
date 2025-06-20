#!/usr/bin/env python3
"""
Test WebSocket connection directly
"""

import asyncio
import websockets
import json
import ssl
import time
import subprocess
import sys

room = f"wstest{int(time.time())}"

# Start publisher
print(f"Starting publisher in room: {room}")
pub = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "alice",
    "--noaudio",
    "--password", "false"
])

print("Waiting for publisher to connect...")
time.sleep(5)

async def test_ws():
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    async with websockets.connect("wss://wss.vdo.ninja:443", ssl=ssl_context) as ws:
        print("\nConnected to WebSocket")
        
        # Join room
        await ws.send(json.dumps({"request": "joinroom", "roomid": room}))
        print(f"Sent join request for room: {room}")
        
        # Listen for messages
        msg_count = 0
        while msg_count < 5:
            try:
                msg_raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                msg = json.loads(msg_raw)
                msg_count += 1
                
                print(f"\n[{msg_count}] Received:")
                if 'request' in msg:
                    print(f"   Request: {msg['request']}")
                    if msg['request'] == 'listing' and 'list' in msg:
                        print(f"   List has {len(msg['list'])} members:")
                        for member in msg['list']:
                            print(f"      {member}")
                else:
                    print(f"   {json.dumps(msg, indent=2)}")
                    
            except asyncio.TimeoutError:
                print("   (timeout)")
                break

# Run test
asyncio.run(test_ws())

# Cleanup
pub.terminate()
print("\nDone")