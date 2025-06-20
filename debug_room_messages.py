#!/usr/bin/env python3
"""
Debug room messages to see what we're receiving
"""

import asyncio
import websockets
import json
import ssl

async def debug_room():
    """Connect to room and see what messages we get"""
    # Connect to VDO.Ninja
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    uri = "wss://wss.vdo.ninja:443"
    
    print(f"Connecting to {uri}...")
    
    async with websockets.connect(uri, ssl=ssl_context) as ws:
        print("Connected!")
        
        # Join room
        join_msg = {
            "request": "joinroom",
            "roomid": "testroom123999999999"
        }
        await ws.send(json.dumps(join_msg))
        print(f"Sent: {join_msg}")
        
        # Listen for messages
        for i in range(10):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                
                print(f"\nMessage {i+1}:")
                print(f"  Type: {data.get('request', data.get('type', 'unknown'))}")
                
                # If it's a listing, show the members
                if data.get('request') == 'listing' and 'list' in data:
                    print(f"  Room members: {len(data['list'])}")
                    for j, member in enumerate(data['list']):
                        print(f"    Member {j}: {json.dumps(member)}")
                elif 'streamID' in data:
                    print(f"  StreamID: {data['streamID']}")
                    print(f"  Full: {json.dumps(data, indent=2)}")
                else:
                    # Show first 200 chars
                    msg_str = json.dumps(data)
                    if len(msg_str) > 200:
                        print(f"  Preview: {msg_str[:200]}...")
                    else:
                        print(f"  Full: {msg_str}")
                        
            except asyncio.TimeoutError:
                print("  (timeout waiting for message)")
            except Exception as e:
                print(f"  Error: {e}")
        
        print("\nClosing connection...")

if __name__ == "__main__":
    print("Room Message Debugger")
    print("=" * 50)
    print("Make sure you have streams publishing to the room!")
    print("=" * 50)
    asyncio.run(debug_room())