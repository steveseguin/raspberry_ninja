#!/usr/bin/env python3
"""
Test WebSocket message flow directly
"""

import asyncio
import websockets
import json
import ssl
import time

room = f"wstest{int(time.time())}"

async def test_websocket():
    """Connect to VDO.Ninja and join a room to see messages"""
    
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    print(f"Connecting to wss://wss.vdo.ninja:443")
    
    async with websockets.connect(
        "wss://wss.vdo.ninja:443",
        ssl=ssl_context
    ) as websocket:
        print("Connected!")
        
        # Send join room request
        join_msg = {"request": "joinroom", "roomid": room}
        await websocket.send(json.dumps(join_msg))
        print(f"\nSent: {join_msg}")
        
        # Listen for messages
        print("\nListening for messages...")
        msg_count = 0
        
        try:
            while True:
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                msg_count += 1
                
                try:
                    msg = json.loads(message)
                    print(f"\n[{msg_count}] Received:")
                    print(json.dumps(msg, indent=2))
                except:
                    print(f"\n[{msg_count}] Raw message: {message}")
                    
        except asyncio.TimeoutError:
            print("\nNo more messages (timeout)")

# Run the test
asyncio.run(test_websocket())