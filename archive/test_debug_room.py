#!/usr/bin/env python3
"""
Debug room recording to see what messages are received
"""

import subprocess
import sys
import time
import os
import glob
import asyncio
import json

# Clean up
for f in glob.glob("debug_*.ts") + glob.glob("debug_*.mkv"):
    os.remove(f)

room = f"debug_{int(time.time())}"

# Start one publisher
print(f"Starting publisher in room: {room}")
pub = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "test_stream",
    "--noaudio", "--h264"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

time.sleep(5)

# Test with debug output
print("\nTesting room recording with debug output...")

import argparse
sys.path.insert(0, '.')

# Create proper args
args = argparse.Namespace()

# Set all required attributes
defaults = {
    'room': room,
    'record': 'debug',
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

# Patch the client to capture messages
from publish import WebRTCClient

class DebugWebRTCClient(WebRTCClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.messages_received = []
        
    async def loop(self):
        """Override loop to capture messages"""
        assert self.conn
        print("✅ WebSocket ready")
        
        # Count messages
        msg_count = 0
        
        while not self._shutdown_requested:
            try:
                message = await asyncio.wait_for(self.conn.recv(), timeout=1.0)
                msg_count += 1
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                break
                
            try:
                msg = json.loads(message)
                self.messages_received.append(msg)
                
                # Debug output key messages
                if 'request' in msg:
                    request = msg['request']
                    print(f"\n📨 [{msg_count}] Request: {request}")
                    if request == 'listing':
                        print(f"   List: {msg.get('list', 'NO LIST')}")
                        if 'list' in msg:
                            print(f"   Members: {len(msg['list'])}")
                            for member in msg['list']:
                                if 'streamID' in member:
                                    print(f"     - {member['streamID']}")
                    elif request in ['videoaddedtoroom', 'someonejoined', 'joinroom']:
                        print(f"   Stream: {msg.get('streamID', 'none')}")
                        
                # Continue normal processing
                await super().loop.__wrapped__(self)
                
            except Exception as e:
                print(f"Error processing message: {e}")
                
        return 0

# Run debug client
try:
    print(f"\nCreating debug client...")
    client = DebugWebRTCClient(args)
    
    print(f"Client room_recording: {client.room_recording}")
    print(f"Client multi_peer_client: {client.multi_peer_client}")
    
    # Run for a bit
    async def run_client():
        await client.connect()
        await asyncio.sleep(10)
        
        print(f"\n\nReceived {len(client.messages_received)} messages total")
        
        # Check for listing
        listing_msgs = [m for m in client.messages_received if m.get('request') == 'listing']
        if listing_msgs:
            print(f"\n✅ Received {len(listing_msgs)} listing message(s)")
            for msg in listing_msgs:
                if 'list' in msg:
                    print(f"   - List with {len(msg['list'])} members")
        else:
            print("\n❌ No listing messages received")
            
        await client.cleanup_pipeline()
        
    print("\nRunning client...")
    asyncio.run(run_client())
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    pub.terminate()
    
# Check for recordings
time.sleep(2)
recordings = glob.glob("debug_*.ts") + glob.glob("debug_*.mkv")

if recordings:
    print(f"\n✅ Found {len(recordings)} recordings:")
    for f in recordings:
        print(f"   - {f} ({os.path.getsize(f):,} bytes)")
else:
    print("\n❌ No recordings found")