#!/usr/bin/env python3
"""
Debug room recording issue
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# First check if basic import works
try:
    from publish import WebRTCClient
    print("✅ Import successful")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Check room recording parameter parsing
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--room', type=str)
parser.add_argument('--record', type=str)
parser.add_argument('--record-room', action='store_true')
parser.add_argument('--password', type=str)
parser.add_argument('--noaudio', action='store_true')

# Parse test args
args = parser.parse_args(['--room', 'testroom123', '--record', 'test', '--record-room', '--password', 'false', '--noaudio'])

print(f"\nParsed args:")
print(f"  room: {args.room}")
print(f"  record: {args.record}")
print(f"  record_room: {args.record_room}")

# Check parameter logic
if args.record_room:
    print("\n✅ Room recording flag detected")
    args.streamin = "room_recording"
    args.room_recording = True
    
    if not args.record:
        args.record = args.room
        
    print(f"  streamin: {args.streamin}")
    print(f"  room_recording: {hasattr(args, 'room_recording') and args.room_recording}")
else:
    print("\n❌ Room recording flag NOT detected")

# Try creating client
print("\nCreating WebRTC client...")
try:
    # Add other required attributes
    for attr in ['server', 'hostname', 'streamid', 'puuid', 'buffer', 'stream_filter',
                 'view', 'novideo', 'h264', 'vp8', 'vp9', 'av1', 'test', 'pipein',
                 'filesrc', 'ndiout', 'fdsink', 'framebuffer', 'midi', 'save',
                 'socketout', 'aom', 'rotate', 'multiviewer', 'pipeline', 'bitrate',
                 'width', 'height', 'framerate', 'nored', 'noqos', 'zerolatency',
                 'noprompt', 'socketport', 'room_ndi']:
        if not hasattr(args, attr):
            setattr(args, attr, None)
    
    args.bitrate = 2500
    args.width = 1920
    args.height = 1080
    args.framerate = 30
    args.rotate = 0
    
    client = WebRTCClient(args)
    print(f"✅ Client created")
    print(f"  room_recording: {client.room_recording}")
    print(f"  room_name: {client.room_name}")
    
except Exception as e:
    print(f"❌ Failed to create client: {e}")
    import traceback
    traceback.print_exc()