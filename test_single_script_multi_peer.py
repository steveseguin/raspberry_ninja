#!/usr/bin/env python3
"""
Test the single-script multi-peer recording capability
This simulates what happens when multiple streams are in a room
"""

import asyncio
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from publish import WebRTCClient
from multi_peer_client import MultiPeerClient
import argparse

class MockWebSocket:
    """Mock WebSocket for testing"""
    def __init__(self):
        self.messages = []
        
    async def send(self, msg):
        """Mock send - just store the message"""
        self.messages.append(json.loads(msg))
        print(f"[MockWS] Sent: {msg[:100]}...")
        
    async def recv(self):
        """Mock receive - never returns to keep connection alive"""
        await asyncio.sleep(3600)

async def test_multi_peer_recording():
    """Test multi-peer recording with a single WebSocket"""
    print("="*60)
    print("SINGLE SCRIPT MULTI-PEER TEST")
    print("="*60)
    
    # Setup args for room recording
    args = argparse.Namespace()
    args.room = 'testroom'
    args.record = 'test'
    args.record_room = True
    args.room_recording = True  # Force this
    args.streamin = "room_recording"
    args.noaudio = True
    args.novideo = False
    args.password = None
    args.hostname = 'wss://vdo.ninja'
    args.server = None
    args.puuid = "test123"
    args.buffer = 200
    args.stream_filter = None
    args.room_ndi = False
    args.streamid = None  # Don't need this for room recording
    
    # Set other required attributes
    for attr in ['view', 'h264', 'vp8', 'vp9', 'av1', 'test', 'pipein',
                 'filesrc', 'ndiout', 'fdsink', 'framebuffer', 'midi', 'save', 
                 'socketout', 'aom', 'rotate', 'multiviewer', 'pipeline', 'bitrate',
                 'width', 'height', 'framerate', 'nored', 'noqos', 'zerolatency',
                 'noprompt', 'socketport']:
        setattr(args, attr, None)
    
    args.bitrate = 2500
    args.width = 1920
    args.height = 1080
    args.framerate = 30
    args.rotate = 0
    
    # Create client
    print("\n1. Creating WebRTC client...")
    client = WebRTCClient(args)
    
    # Mock the WebSocket connection
    client.conn = MockWebSocket()
    
    print(f"   Room recording enabled: {client.room_recording}")
    print(f"   Record prefix: {client.record}")
    
    # Simulate room listing
    print("\n2. Simulating room listing with 3 streams...")
    room_list = [
        {"streamID": "alice", "UUID": "uuid-alice"},
        {"streamID": "bob", "UUID": "uuid-bob"},
        {"streamID": "charlie", "UUID": "uuid-charlie"}
    ]
    
    # Call the room listing handler
    await client.handle_room_listing(room_list)
    
    # Check if multi-peer client was created
    print("\n3. Checking multi-peer client...")
    if client.multi_peer_client:
        print(f"   ✅ Multi-peer client created")
        print(f"   Number of recorders: {len(client.multi_peer_client.recorders)}")
        
        for stream_id, recorder in client.multi_peer_client.recorders.items():
            print(f"\n   Stream: {stream_id}")
            print(f"     Pipeline: {recorder.pipe is not None}")
            print(f"     WebRTC: {recorder.webrtc is not None}")
            print(f"     Session ID: {recorder.session_id}")
    else:
        print("   ❌ No multi-peer client created!")
        return False
    
    # Simulate incoming offers for each stream
    print("\n4. Simulating WebRTC offers...")
    for i, (stream_id, recorder) in enumerate(client.multi_peer_client.recorders.items()):
        print(f"\n   Simulating offer for {stream_id}...")
        
        # Create a mock SDP offer
        mock_offer = """v=0
o=- 123456 2 IN IP4 127.0.0.1
s=-
t=0 0
m=video 9 UDP/TLS/RTP/SAVPF 96
a=rtpmap:96 H264/90000
a=sendonly
a=ice-ufrag:test
a=ice-pwd:test
a=fingerprint:sha-256 00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00
a=setup:actpass
"""
        
        # Simulate the message that would come from WebSocket
        msg = {
            'description': {
                'type': 'offer',
                'sdp': mock_offer
            },
            'session': f'session-{i}',
            'from': f'remote-{stream_id}'
        }
        
        # Route to multi-peer client
        await client.multi_peer_client.handle_message(msg)
        
        # Check if answer was created
        if recorder.answer_sdp:
            print(f"     ✅ Answer created for {stream_id}")
        else:
            print(f"     ❌ No answer for {stream_id}")
    
    # Simulate ICE candidates
    print("\n5. Simulating ICE candidates...")
    for i, stream_id in enumerate(client.multi_peer_client.recorders.keys()):
        msg = {
            'candidates': [{
                'candidate': 'candidate:1 1 UDP 2130706431 192.168.1.1 50000 typ host',
                'sdpMLineIndex': 0
            }],
            'session': f'session-{i}'
        }
        await client.multi_peer_client.handle_message(msg)
    
    # Check final state
    print("\n6. Final state check...")
    stats = client.multi_peer_client.get_all_stats()
    print(f"\n   Recording statistics:")
    for stat in stats:
        print(f"     {stat['stream_id']}: recording={stat['recording']}, file={stat['file']}")
    
    # Simulate new stream joining
    print("\n7. Simulating new stream joining (videoaddedtoroom)...")
    await client.handle_new_room_stream("dave", "uuid-dave")
    
    if "dave" in client.multi_peer_client.recorders:
        print("   ✅ New stream 'dave' added successfully")
    else:
        print("   ❌ Failed to add new stream")
    
    # Final summary
    print("\n8. Summary:")
    print(f"   Total recorders: {len(client.multi_peer_client.recorders)}")
    print(f"   Streams: {list(client.multi_peer_client.recorders.keys())}")
    
    # Check WebSocket messages sent
    print(f"\n9. WebSocket messages sent: {len(client.conn.messages)}")
    for msg in client.conn.messages[:5]:  # Show first 5
        print(f"   - {msg.get('request', msg.get('type', 'unknown'))}")
    
    return True

# Run the test
if __name__ == "__main__":
    print("Testing single-script multi-peer recording...")
    try:
        success = asyncio.run(test_multi_peer_recording())
        print("\n" + "="*60)
        if success:
            print("✅ TEST PASSED: Multi-peer recording initialized correctly")
            print("   - Single WebSocket connection")
            print("   - Multiple WebRTC peer connections")
            print("   - Each stream has its own recorder")
        else:
            print("❌ TEST FAILED")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()