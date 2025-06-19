#!/usr/bin/env python3
"""
Test basic functionality to isolate the issue
"""

print("1. Testing basic imports...")
try:
    from publish import WebRTCClient
    print("   ✓ WebRTCClient imported")
except Exception as e:
    print(f"   ✗ Failed to import: {e}")
    
try:
    from multi_peer_client import MultiPeerClient
    print("   ✓ MultiPeerClient imported")
except Exception as e:
    print(f"   ✗ Failed to import: {e}")

print("\n2. Testing GStreamer...")
try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    Gst.init(None)
    
    # Test creating elements
    pipeline = Gst.Pipeline.new('test')
    webrtc = Gst.ElementFactory.make('webrtcbin', 'test-webrtc')
    
    if pipeline and webrtc:
        print("   ✓ GStreamer working, webrtcbin available")
    else:
        print("   ✗ Failed to create GStreamer elements")
except Exception as e:
    print(f"   ✗ GStreamer error: {e}")

print("\n3. Testing WebSocket connection...")
import asyncio
import websockets
import ssl
import json

async def test_ws():
    try:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        async with websockets.connect("wss://wss.vdo.ninja:443", ssl=ssl_context) as ws:
            print("   ✓ Connected to WebSocket")
            
            # Test joining a room
            await ws.send(json.dumps({"request": "joinroom", "roomid": "test123"}))
            
            # Get response
            response = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(response)
            
            if 'request' in data and data['request'] == 'listing':
                print("   ✓ Received room listing")
            else:
                print(f"   ? Unexpected response: {data}")
                
    except Exception as e:
        print(f"   ✗ WebSocket error: {e}")

asyncio.run(test_ws())

print("\n4. Testing room recording setup...")
import argparse

args = argparse.Namespace()
args.room = "test"
args.record = "test"
args.record_room = True
args.streamin = "room_recording" 
args.room_recording = True
args.password = None

# Set other required attributes
for attr in ['streamid', 'view', 'noaudio', 'novideo', 'h264', 'vp8', 'vp9', 'av1',
             'pipein', 'filesrc', 'ndiout', 'fdsink', 'framebuffer', 'midi',
             'save', 'socketout', 'aom', 'rotate', 'multiviewer', 'room_ndi',
             'pipeline', 'server', 'puuid', 'stream_filter', 'bitrate', 'buffer',
             'width', 'height', 'framerate', 'nored', 'noqos', 'hostname',
             'test', 'zerolatency', 'noprompt', 'socketport']:
    if not hasattr(args, attr):
        setattr(args, attr, None)

args.bitrate = 2500
args.buffer = 200
args.width = 1920
args.height = 1080
args.framerate = 30
args.hostname = "wss://wss.vdo.ninja:443"
args.rotate = 0
args.noaudio = True

try:
    client = WebRTCClient(args)
    if client.room_recording:
        print("   ✓ Room recording mode activated")
    else:
        print("   ✗ Room recording mode not set")
except Exception as e:
    print(f"   ✗ Failed to create client: {e}")
    import traceback
    traceback.print_exc()

print("\nBasic functionality test complete.")