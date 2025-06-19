#!/usr/bin/env python3
"""
Direct test of multi-peer functionality
"""

import subprocess
import sys
import time
import os
import glob
import asyncio

# Clean up
for f in glob.glob("direct_*.ts") + glob.glob("direct_*.mkv"):
    os.remove(f)

room = f"direct_{int(time.time())}"

# Start one publisher
print(f"Starting publisher in room: {room}")
pub = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "test_stream",
    "--noaudio", "--h264"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

time.sleep(5)

# Test the multi-peer client directly
print("\nTesting multi-peer client directly...")

import argparse
sys.path.insert(0, '.')

# Create proper args
args = argparse.Namespace()

# Set all required attributes with defaults
defaults = {
    'room': room,
    'record': 'direct',
    'record_room': True,
    'room_recording': True,
    'streamin': 'room_recording',
    'streamid': None,
    'view': None,
    'noaudio': True,
    'novideo': False,
    'h264': False,
    'vp8': False,
    'vp9': False,
    'av1': False,
    'pipein': False,
    'filesrc': False,
    'ndiout': False,
    'fdsink': False,
    'framebuffer': False,
    'midi': False,
    'save': False,
    'socketout': False,
    'aom': False,
    'rotate': False,
    'multiviewer': False,
    'room_ndi': False,
    'pipeline': None,
    'server': None,
    'puuid': None,
    'password': None,
    'stream_filter': None,
    'bitrate': 2500,
    'buffer': 200,
    'width': 1920,
    'height': 1080,
    'framerate': 30,
    'nored': False,
    'noqos': False,
    'hostname': "wss://wss.vdo.ninja:443",
    'test': False,
    'zerolatency': False,
    'noprompt': False,
    'socketport': None
}

for key, value in defaults.items():
    setattr(args, key, value)

# Test creating client and recording
try:
    from publish import WebRTCClient
    
    print(f"Creating WebRTCClient with room_recording={args.room_recording}")
    client = WebRTCClient(args)
    
    # Check state
    print(f"Client room_recording: {client.room_recording}")
    print(f"Client multi_peer_client: {client.multi_peer_client}")
    
    # Run for a bit
    async def run_client():
        await client.connect()
        await asyncio.sleep(15)
        await client.cleanup_pipeline()
        
    print("\nRunning client for 15 seconds...")
    asyncio.run(run_client())
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    pub.terminate()
    
# Check for recordings
time.sleep(2)
recordings = glob.glob("direct_*.ts") + glob.glob("direct_*.mkv") + glob.glob(f"{room}_*.ts") + glob.glob(f"{room}_*.mkv")

if recordings:
    print(f"\n✅ Found {len(recordings)} recordings:")
    for f in recordings:
        print(f"   - {f} ({os.path.getsize(f):,} bytes)")
        
    # Validate
    from validate_media_file import validate_recording
    for f in recordings:
        if validate_recording(f, verbose=False):
            print(f"   ✅ {f} is valid")
        else:
            print(f"   ❌ {f} is invalid")
else:
    print("\n❌ No recordings found")
    
    # Debug
    print("\nAll .ts and .mkv files:")
    all_files = glob.glob("*.ts") + glob.glob("*.mkv")
    for f in sorted(all_files)[-5:]:
        print(f"   - {f}")