#!/usr/bin/env python3
"""
Test room recording methods directly
"""

import asyncio
import sys
import os

sys.path.insert(0, '.')

from publish import WebRTCClient
import argparse

# Create minimal args
args = argparse.Namespace()

# Set all required attributes
attrs = {
    'room': 'testroom123',
    'record': 'test',
    'record_room': True,
    'room_recording': True,
    'streamin': 'room_recording',
    'password': 'false',
    'noaudio': True,
    'server': None,
    'hostname': None,
    'streamid': None,
    'puuid': None,
    'buffer': 200,
    'stream_filter': None,
    'view': None,
    'novideo': None,
    'h264': None,
    'vp8': None,
    'vp9': None,
    'av1': None,
    'test': None,
    'pipein': None,
    'filesrc': None,
    'ndiout': None,
    'fdsink': None,
    'framebuffer': None,
    'midi': None,
    'save': None,
    'socketout': None,
    'aom': None,
    'rotate': 0,
    'multiviewer': None,
    'room_ndi': False,
    'pipeline': None,
    'bitrate': 2500,
    'width': 1920,
    'height': 1080,
    'framerate': 30,
    'nored': False,
    'noqos': False,
    'zerolatency': None,
    'noprompt': None,
    'socketport': None
}

for k, v in attrs.items():
    setattr(args, k, v)

async def test_methods():
    print("Testing room recording methods...")
    
    # Create client
    client = WebRTCClient(args)
    print(f"✅ Client created, room_recording={client.room_recording}")
    
    # Check if methods exist
    methods = ['_add_room_stream', '_create_stream_recorder', '_handle_room_message',
               '_handle_room_offer', '_process_ice_candidates']
    
    for method in methods:
        if hasattr(client, method):
            print(f"✅ Method exists: {method}")
        else:
            print(f"❌ Method missing: {method}")
    
    # Test creating a recorder
    print("\nTesting recorder creation...")
    try:
        recorder = client._create_stream_recorder("test_stream")
        if recorder:
            print("✅ Recorder created successfully")
            print(f"  Has pipe: {recorder.get('pipe') is not None}")
            print(f"  Has webrtc: {recorder.get('webrtc') is not None}")
            
            # Clean up
            if recorder.get('pipe'):
                recorder['pipe'].set_state(0)  # NULL state
        else:
            print("❌ Failed to create recorder")
    except Exception as e:
        print(f"❌ Error creating recorder: {e}")
        import traceback
        traceback.print_exc()

# Run test
asyncio.run(test_methods())