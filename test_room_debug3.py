#!/usr/bin/env python3
"""
Debug what's in the room listing
"""

import subprocess
import sys
import time
import os
import glob
import asyncio
import json

room = f"debuglist_{int(time.time())}"

# Start publishers
print(f"Starting publishers in room: {room}")

pub1 = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "alice",
    "--noaudio", "--h264"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

time.sleep(2)

pub2 = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "bob",
    "--noaudio", "--vp8"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

time.sleep(5)

# Create a test client
import argparse
sys.path.insert(0, '.')

args = argparse.Namespace()
defaults = {
    'room': room,
    'record': 'debuglist',
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

# Patch handle_room_listing to debug
from publish import WebRTCClient

original_handle = WebRTCClient.handle_room_listing

async def debug_handle_room_listing(self, room_list):
    print(f"\n🔍 DEBUG: handle_room_listing called")
    print(f"   Room list type: {type(room_list)}")
    print(f"   Room list length: {len(room_list) if room_list else 0}")
    
    if room_list:
        print(f"\n   Members:")
        for i, member in enumerate(room_list):
            print(f"\n   Member {i}:")
            print(f"     Type: {type(member)}")
            if isinstance(member, dict):
                for key, value in member.items():
                    print(f"     {key}: {value}")
            else:
                print(f"     Value: {member}")
    
    # Call original
    await original_handle(self, room_list)

WebRTCClient.handle_room_listing = debug_handle_room_listing

# Run test
try:
    print(f"\nCreating client...")
    client = WebRTCClient(args)
    
    async def run_client():
        await client.connect()
        await asyncio.sleep(10)
        await client.cleanup_pipeline()
        
    asyncio.run(run_client())
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    pub1.terminate()
    pub2.terminate()