#!/usr/bin/env python3
"""
Test room recording with inline debugging
"""

import subprocess
import sys
import time

# Insert debug prints into publish.py temporarily
sys.path.insert(0, '.')
from publish import WebRTCClient, printc

# Store original handle_room_listing
original_handle_room_listing = WebRTCClient.handle_room_listing

async def debug_handle_room_listing(self, room_list):
    """Debug version of handle_room_listing"""
    printc(f"DEBUG: handle_room_listing called with {len(room_list) if room_list else 0} members", "F0F")
    printc(f"DEBUG: self.room_recording = {self.room_recording}", "F0F")
    printc(f"DEBUG: self.streamin = {self.streamin}", "F0F")
    
    # Call original
    result = await original_handle_room_listing(self, room_list)
    
    printc(f"DEBUG: After handle_room_listing, multi_peer_client = {self.multi_peer_client}", "F0F")
    return result

# Apply patch
WebRTCClient.handle_room_listing = debug_handle_room_listing

# Now run the test
room = "debugroom"

print("Starting publisher...")
pub = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "alice",
    "--noaudio",
    "--password", "false"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

time.sleep(3)

print("\nStarting room recorder...")
rec = subprocess.Popen([
    sys.executable, "publish.py",
    "--room", room,
    "--record", "debug",
    "--record-room",
    "--noaudio",
    "--password", "false"
])

print("\nRunning for 10 seconds...")
time.sleep(10)

print("\nStopping...")
rec.terminate()
pub.terminate()