#!/usr/bin/env python3
"""
Debug room recording - simpler version
"""

import subprocess
import sys
import time
import os
import glob

# Clean up
for f in glob.glob("debug2_*.ts") + glob.glob("debug2_*.mkv"):
    os.remove(f)

room = f"debug2_{int(time.time())}"

# Start publishers
print(f"Starting 2 publishers in room: {room}")

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

# Start room recorder with verbose output
print("\nStarting room recorder...")
rec_cmd = [
    sys.executable, "publish.py",
    "--room", room,
    "--record", "debug2",
    "--record-room",
    "--noaudio"
]

# Patch publish.py temporarily to add debug output
import sys
sys.path.insert(0, '.')
from publish import WebRTCClient, printc

# Store original loop method
original_loop = WebRTCClient.loop

async def debug_loop(self):
    """Patched loop with debug output"""
    assert self.conn
    printc("✅ WebSocket ready (DEBUG)", "0F0")
    
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
            
            # Debug output
            if 'request' in msg:
                printc(f"[MSG {msg_count}] Request: {msg['request']}", "FF0")
                if msg['request'] == 'listing':
                    if 'list' in msg:
                        printc(f"  -> Room has {len(msg['list'])} members", "0F0")
                        for m in msg['list']:
                            if 'streamID' in m:
                                printc(f"     - {m['streamID']}", "77F")
                                
            # Process normally
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
                            # Handle room listing
                            if 'list' in msg:
                                await self.handle_room_listing(msg['list'])
                            
                            if self.room_recording:
                                # In room recording mode
                                if not msg.get('list'):
                                    printc("Warning: Empty room list", "F77")
                            elif self.streamin:
                                await self.sendMessageAsync({"request":"play","streamID":self.streamin+self.hashcode})
                        continue
                else:
                    continue
                    
            # Rest of normal processing...
            if 'description' in msg:
                self.handle_sdp_ice(msg, UUID)
            elif 'candidates' in msg:
                self.handle_sdp_ice(msg, UUID)
            elif 'request' in msg:
                if msg['request'] == 'offerSDP':
                    await self.start_pipeline(UUID)
                elif msg['request'] == 'cleanup' or msg['request'] == 'bye':
                    if self.room_recording and UUID in self.room_streams:
                        await self.cleanup_room_stream(UUID)
                        
        except Exception as e:
            printc(f"Error in message loop: {e}", "F00")
            import traceback
            traceback.print_exc()
            
    return 0

# Apply patch
import asyncio
import json
import random
import websockets

WebRTCClient.loop = debug_loop

# Now run the recorder
print(f"\nRunning: {' '.join(rec_cmd)}")
rec = subprocess.Popen(rec_cmd)

# Let it run
print("\nRecording for 15 seconds...")
time.sleep(15)

# Stop
print("\nStopping...")
rec.terminate()
pub1.terminate()
pub2.terminate()

# Wait
time.sleep(3)

# Check recordings
recordings = glob.glob("debug2_*.ts") + glob.glob("debug2_*.mkv") + glob.glob(f"{room}_*.ts") + glob.glob(f"{room}_*.mkv")

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