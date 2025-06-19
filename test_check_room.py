#!/usr/bin/env python3
"""
Check what's in the test room
"""

import asyncio
import json
import websockets
import ssl

async def check_room():
    """Check room contents"""
    print("Checking room: testroom123")
    print("="*60)
    
    # Connect to VDO.Ninja
    uri = "wss://wss.vdo.ninja:443"
    ssl_context = ssl.create_default_context()
    
    try:
        async with websockets.connect(uri, ssl=ssl_context) as ws:
            print("✅ Connected to server")
            
            # Join room
            await ws.send(json.dumps({
                "request": "joinroom",
                "roomid": "testroom123"
            }))
            print("✅ Sent join request")
            
            # Listen for messages
            messages_received = []
            # Listen for up to 10 seconds
            start_time = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start_time < 10:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    data = json.loads(msg)
                    messages_received.append(data)
                    
                    print(f"\n📨 Message: {data.get('request', data.get('type', 'unknown'))}")
                    
                    if 'list' in data:
                        print(f"   Room members: {len(data['list'])}")
                        for member in data['list']:
                            print(f"     - {member.get('streamID', 'unknown')}")
                            
                    if 'streamID' in data:
                        print(f"   Stream ID: {data['streamID']}")
                        
                except asyncio.TimeoutError:
                    continue  # No message in 1 second, continue
                    
            print("\n⏱️ Timeout reached")
                
    except Exception as e:
        print(f"\n❌ Error: {e}")
        
    print(f"\n📊 Total messages received: {len(messages_received)}")
    
    # Check for stream in room
    has_streams = False
    for msg in messages_received:
        if 'list' in msg and len(msg['list']) > 0:
            has_streams = True
            break
            
    if has_streams:
        print("✅ Room has active streams")
    else:
        print("❌ Room appears to be empty")
        
    return messages_received

if __name__ == "__main__":
    messages = asyncio.run(check_room())
    
    print("\n" + "="*60)
    print("RAW MESSAGES:")
    print("="*60)
    for i, msg in enumerate(messages):
        print(f"\n{i+1}. {json.dumps(msg, indent=2)}")