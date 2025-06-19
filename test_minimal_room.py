#!/usr/bin/env python3
"""
Minimal test to debug multi-peer WebRTC connection
"""

import asyncio
import sys
import time
import json
import subprocess
import glob
import os

# Clean up
for f in glob.glob("minimal_*.ts") + glob.glob("minimal_*.mkv"):
    os.remove(f)

room = f"minimal{int(time.time())}"

# Start ONE publisher
print(f"Starting publisher in room: {room}")
pub = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "test1",
    "--noaudio", "--h264",
    "--password", "false"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print("Waiting for publisher to establish...")
time.sleep(5)

# Now test multi-peer client directly
print("\nTesting multi-peer client...")

sys.path.insert(0, '.')
from publish import WebRTCClient
from multi_peer_client import MultiPeerClient
import argparse

# Create minimal args
args = argparse.Namespace()
args.room = room
args.record = "minimal"
args.room_recording = True
args.streamin = "room_recording"
args.noaudio = True
args.password = None
args.hostname = "wss://wss.vdo.ninja:443"
args.server = None
args.puuid = None
args.buffer = 200
args.stream_filter = None

# Add all other required attributes with defaults
other_attrs = ['streamid', 'view', 'novideo', 'h264', 'vp8', 'vp9', 'av1', 
               'pipein', 'filesrc', 'ndiout', 'fdsink', 'framebuffer', 
               'midi', 'save', 'socketout', 'aom', 'rotate', 'multiviewer',
               'room_ndi', 'pipeline', 'bitrate', 'width', 'height', 
               'framerate', 'nored', 'noqos', 'test', 'zerolatency', 
               'noprompt', 'socketport', 'record_room']

for attr in other_attrs:
    setattr(args, attr, None)
    
args.record_room = True
args.bitrate = 2500
args.width = 1920
args.height = 1080
args.framerate = 30
args.nored = False
args.noqos = False
args.rotate = 0  # Fix rotate parameter

async def test_connection():
    """Test multi-peer connection"""
    client = WebRTCClient(args)
    
    try:
        print("Connecting to server...")
        await client.connect()
        
        # Wait for room listing
        print("Waiting for room listing...")
        await asyncio.sleep(3)
        
        # Check if multi-peer client was created
        if client.multi_peer_client:
            print(f"✅ Multi-peer client created")
            print(f"   Recorders: {len(client.multi_peer_client.recorders)}")
            
            # Check recorder states
            for stream_id, recorder in client.multi_peer_client.recorders.items():
                print(f"\n   Stream: {stream_id}")
                print(f"     Pipeline: {recorder.pipe}")
                print(f"     WebRTC: {recorder.webrtc}")
                print(f"     Recording: {recorder.recording}")
                
            # Wait a bit more
            print("\nWaiting for connections...")
            await asyncio.sleep(10)
            
            # Check again
            print("\nFinal state:")
            stats = client.multi_peer_client.get_all_stats()
            for stat in stats:
                print(f"   {stat['stream_id']}: recording={stat['recording']}, bytes={stat['bytes']}")
                
        else:
            print("❌ No multi-peer client created")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.cleanup_pipeline()

# Run test
print("\nRunning async test...")
asyncio.run(test_connection())

# Cleanup
pub.terminate()
time.sleep(2)

# Check for files
files = glob.glob("minimal_*.ts") + glob.glob("minimal_*.mkv")
if files:
    print(f"\n✅ Found {len(files)} files")
    for f in files:
        print(f"   {f} ({os.path.getsize(f)} bytes)")
else:
    print("\n❌ No files created")