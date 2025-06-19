#!/usr/bin/env python3
"""
Test room recording directly
"""

import asyncio
import sys
import time
import argparse
import glob
import os

# Clean up
for f in glob.glob("direct_*.ts") + glob.glob("direct_*.mkv"):
    os.remove(f)

# First, start a publisher in background
import subprocess
room = "directtest"
pub = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "alice",
    "--noaudio", "--password", "false"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print("Waiting for publisher...")
time.sleep(5)

# Now test room recording directly
sys.path.insert(0, '.')
from publish import WebRTCClient

# Create args for room recording
args = argparse.Namespace()
args.room = room
args.record = "direct"
args.record_room = True
args.room_recording = True
args.streamin = "room_recording"
args.streamid = None
args.view = None
args.noaudio = True
args.novideo = False
args.password = None
args.hostname = "wss://wss.vdo.ninja:443"

# Set all other required attributes
attrs = {
    'h264': False, 'vp8': False, 'vp9': False, 'av1': False,
    'pipein': False, 'filesrc': False, 'ndiout': False,
    'fdsink': False, 'framebuffer': False, 'midi': False,
    'save': False, 'socketout': False, 'aom': False,
    'rotate': 0, 'multiviewer': False, 'room_ndi': False,
    'pipeline': None, 'server': None, 'puuid': None,
    'stream_filter': None, 'bitrate': 2500, 'buffer': 200,
    'width': 1920, 'height': 1080, 'framerate': 30,
    'nored': False, 'noqos': False, 'test': False,
    'zerolatency': False, 'noprompt': False, 'socketport': None
}

for k, v in attrs.items():
    setattr(args, k, v)

async def test_room_recording():
    """Test room recording"""
    print("\nCreating WebRTC client for room recording...")
    client = WebRTCClient(args)
    
    print(f"Room recording mode: {client.room_recording}")
    
    try:
        print("Connecting...")
        await client.connect()
        
        # Start the message loop
        print("Starting message loop...")
        loop_task = asyncio.create_task(client.loop())
        
        # Run for a bit
        print("Running for 10 seconds...")
        await asyncio.sleep(10)
        
        # Check state
        if client.multi_peer_client:
            print(f"\n✅ Multi-peer client active")
            print(f"   Recorders: {len(client.multi_peer_client.recorders)}")
            
            stats = client.multi_peer_client.get_all_stats()
            for stat in stats:
                print(f"   {stat['stream_id']}: recording={stat['recording']}, bytes={stat['bytes']}")
        else:
            print("\n❌ No multi-peer client")
            
        # Stop the loop
        client._shutdown_requested = True
        await asyncio.wait_for(loop_task, timeout=2.0)
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.cleanup_pipeline()

# Run test
print("Starting async test...")
asyncio.run(test_room_recording())

# Cleanup
pub.terminate()
time.sleep(2)

# Check files
files = glob.glob("direct_*.ts") + glob.glob("direct_*.mkv") + glob.glob(f"{room}_*.ts") + glob.glob(f"{room}_*.mkv")
if files:
    print(f"\n✅ Found {len(files)} files:")
    for f in files:
        print(f"   {f} ({os.path.getsize(f):,} bytes)")
else:
    print("\n❌ No files found")