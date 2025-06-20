#!/usr/bin/env python3
"""Test basic WebRTC connectivity"""

import asyncio
import websockets
import json
import ssl
import uuid
import random

async def test_connection():
    """Test basic WebRTC connection to VDO.Ninja"""
    
    # Connect to VDO.Ninja
    server_url = "wss://wss.vdo.ninja:443"
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    try:
        print(f"Connecting to {server_url}...")
        conn = await websockets.connect(server_url, ssl=ssl_context)
        print("✅ Connected to server")
        
        # Join room
        room_name = "testroom123999999999"
        print(f"\nJoining room: {room_name}")
        await conn.send(json.dumps({"request": "joinroom", "roomid": room_name}))
        
        # Wait for room info
        while True:
            msg = await conn.recv()
            data = json.loads(msg)
            
            if 'request' in data and data['request'] == 'listing':
                room_list = data.get('list', [])
                print(f"\nRoom has {len(room_list)} members:")
                for member in room_list:
                    stream_id = member.get('streamID', 'unknown')
                    uuid = member.get('UUID', 'unknown')
                    print(f"  - Stream: {stream_id} (UUID: {uuid[:8]}...)")
                    
                if room_list:
                    # Try to connect to first stream
                    first_stream = room_list[0]
                    stream_id = first_stream.get('streamID')
                    stream_uuid = str(uuid.uuid4()) if not isinstance(uuid, str) else str(random.randint(10000000, 99999999))
                    
                    print(f"\nRequesting stream: {stream_id}")
                    play_msg = {
                        "request": "play",
                        "streamID": stream_id,
                        "UUID": stream_uuid
                    }
                    await conn.send(json.dumps(play_msg))
                    print("Play request sent")
                    
                    # Wait for offer
                    timeout = 10
                    print(f"Waiting {timeout}s for offer...")
                    try:
                        for i in range(timeout):
                            msg = await asyncio.wait_for(conn.recv(), timeout=1.0)
                            data = json.loads(msg)
                            
                            if 'description' in data:
                                sdp = data.get('description', {}).get('sdp', '')
                                print("\n✅ Received SDP offer!")
                                
                                # Check codec
                                if 'VP8' in sdp:
                                    print("  Codec: VP8")
                                elif 'H264' in sdp:
                                    print("  Codec: H264")
                                elif 'OPUS' in sdp:
                                    print("  Has OPUS audio")
                                    
                                # Check for video/audio
                                if 'm=video' in sdp:
                                    print("  Has video track")
                                if 'm=audio' in sdp:
                                    print("  Has audio track")
                                    
                                # Print a snippet of the SDP
                                lines = sdp.split('\n')
                                for line in lines:
                                    if 'a=rtpmap' in line:
                                        print(f"  RTP Map: {line.strip()}")
                                    elif 'm=video' in line or 'm=audio' in line:
                                        print(f"  Media line: {line.strip()}")
                                    elif 'a=sendonly' in line or 'a=recvonly' in line or 'a=sendrecv' in line:
                                        print(f"  Direction: {line.strip()}")
                                        
                                break
                    except asyncio.TimeoutError:
                        print("❌ Timeout waiting for offer")
                else:
                    print("\n❌ Room is empty")
                    
                break
                
        await conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_connection())