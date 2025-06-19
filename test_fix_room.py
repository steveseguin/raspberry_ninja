#!/usr/bin/env python3
"""
Test room recording with a fix
"""

import subprocess
import sys
import time
import os
import glob

# Clean up old recordings
for f in glob.glob("fix_*.ts") + glob.glob("fix_*.mkv"):
    os.remove(f)

room = f"fix{int(time.time())}"

# Start publishers first
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

# Apply a temporary fix to publish.py
import sys
sys.path.insert(0, '.')
from publish import WebRTCClient

# Store original loop
original_loop = WebRTCClient.loop

async def fixed_loop(self):
    """Fixed loop that properly routes messages to multi-peer client"""
    assert self.conn
    print("✅ WebSocket ready")
    
    while not self._shutdown_requested:
        try:
            message = await asyncio.wait_for(self.conn.recv(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        except websockets.exceptions.ConnectionClosed:
            break
            
        try:
            msg = json.loads(message)
            
            # FIRST: Always give multi-peer client a chance to handle messages if active
            if self.multi_peer_client and self.room_recording:
                # Send all messages to multi-peer client for room recording
                await self.multi_peer_client.handle_message(msg)
                
                # For room recording, skip main processing for WebRTC-related messages
                if any(key in msg for key in ['description', 'candidates', 'candidate']):
                    continue
                    
                # Also skip if this is an offer response to our play request
                if 'from' in msg and 'description' in msg:
                    continue
            
            # Normal message processing
            if 'from' in msg:
                if self.puuid==None:
                    self.puuid = str(random.randint(10000000,99999999999))
                if msg['from'] == self.puuid:
                    continue
                UUID = msg['from']
                if ('UUID' in msg) and (msg['UUID'] != self.puuid):
                    continue
            elif 'UUID' in msg:
                if (self.puuid != None) and (self.puuid != msg['UUID']):
                    continue
                UUID = msg['UUID']
            else:
                if self.room_name:
                    if 'request' in msg:
                        if msg['request'] == 'listing':
                            if 'list' in msg:
                                await self.handle_room_listing(msg['list'])
                            if self.room_recording:
                                if not msg.get('list'):
                                    print("Warning: Empty room list")
                            elif self.streamin:
                                await self.sendMessageAsync({"request":"play","streamID":self.streamin+self.hashcode})
                continue
                
            # Create client entry if needed (but not for room recording)
            if not self.room_recording and UUID not in self.clients:
                self.clients[UUID] = {
                    "UUID": UUID,
                    "session": None,
                    "send_channel": None,
                    "timer": None,
                    "ping": 0,
                    "webrtc": None
                }
                
            # Rest of processing...
            
        except Exception as e:
            print(f"Error in loop: {e}")
            import traceback
            traceback.print_exc()
            
    return 0

# Apply fix
import asyncio
import json
import random
import websockets
WebRTCClient.loop = fixed_loop

# Now start recorder
print("\nStarting room recorder with fix...")
rec = subprocess.Popen([
    sys.executable, "publish.py",
    "--room", room,
    "--record", "fix",
    "--record-room",
    "--noaudio"
])

# Let it run
print("Recording for 20 seconds...")
time.sleep(20)

# Stop everything
print("\nStopping...")
rec.terminate()
pub1.terminate()
pub2.terminate()

time.sleep(3)

# Check recordings
recordings = glob.glob("fix_*.ts") + glob.glob("fix_*.mkv") + glob.glob(f"{room}_*.ts") + glob.glob(f"{room}_*.mkv")

if recordings:
    print(f"\n✅ Found {len(recordings)} recordings:")
    for f in recordings:
        print(f"   - {f} ({os.path.getsize(f):,} bytes)")
        
    # Validate
    from validate_media_file import validate_recording
    valid = 0
    for f in recordings:
        if validate_recording(f, verbose=False):
            print(f"   ✅ {f} is valid")
            valid += 1
        else:
            print(f"   ❌ {f} is invalid")
            
    print(f"\n{valid}/{len(recordings)} recordings are valid")
else:
    print("\n❌ No recordings found")