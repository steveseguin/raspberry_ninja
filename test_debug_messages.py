#!/usr/bin/env python3
"""
Debug what messages are received in room recording mode
"""

import asyncio
import sys
import time
import json
import subprocess
import glob
import os

room = f"debug{int(time.time())}"

# Start publisher
print(f"Starting publisher in room: {room}")
pub = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "test1",
    "--noaudio", "--h264",
    "--password", "false"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print("Waiting for publisher...")
time.sleep(5)

# Create a debug client
sys.path.insert(0, '.')
from publish import WebRTCClient, printc
import argparse

# Override the loop to see messages
class DebugClient(WebRTCClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.messages = []
        
    async def loop(self):
        """Override to log messages"""
        assert self.conn
        printc("✅ WebSocket ready (DEBUG)", "0F0")
        
        msg_count = 0
        
        while not self._shutdown_requested:
            try:
                # Wait for message with timeout to check shutdown flag
                message = await asyncio.wait_for(self.conn.recv(), timeout=1.0)
                msg_count += 1
                
                msg = json.loads(message)
                self.messages.append(msg)
                
                # Log key messages
                if 'request' in msg:
                    printc(f"[{msg_count}] Request: {msg['request']}", "FF0")
                    if msg['request'] == 'listing':
                        if 'list' in msg:
                            printc(f"   List has {len(msg['list'])} members", "0F0")
                            for m in msg['list']:
                                printc(f"   - {m}", "77F")
                                
                # Continue with normal processing
                await super().loop()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                printc(f"Loop error: {e}", "F00")
                break
                
        return 0

# Create args
args = argparse.Namespace()
args.room = room
args.record = "debug"
args.room_recording = True
args.record_room = True
args.streamin = "room_recording"
args.noaudio = True
args.password = None
args.hostname = "wss://wss.vdo.ninja:443"

# Set all other required attributes
other_attrs = ['streamid', 'view', 'novideo', 'h264', 'vp8', 'vp9', 'av1',
               'pipein', 'filesrc', 'ndiout', 'fdsink', 'framebuffer',
               'midi', 'save', 'socketout', 'aom', 'rotate', 'multiviewer',
               'room_ndi', 'pipeline', 'server', 'puuid', 'stream_filter',
               'bitrate', 'buffer', 'width', 'height', 'framerate',
               'nored', 'noqos', 'test', 'zerolatency', 'noprompt', 'socketport']

for attr in other_attrs:
    setattr(args, attr, None)
    
args.bitrate = 2500
args.buffer = 200
args.width = 1920
args.height = 1080
args.framerate = 30
args.nored = False
args.noqos = False
args.rotate = 0

async def test_debug():
    client = DebugClient(args)
    
    try:
        await client.connect()
        await asyncio.sleep(5)
        
        print(f"\nReceived {len(client.messages)} messages")
        print(f"Multi-peer client: {client.multi_peer_client}")
        print(f"Room recording: {client.room_recording}")
        
    finally:
        await client.cleanup_pipeline()

# Run
asyncio.run(test_debug())

# Cleanup
pub.terminate()