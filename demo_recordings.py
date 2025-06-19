#!/usr/bin/env python3
"""
Demonstrate recording functionality
"""

import subprocess
import time
import glob
import os
import sys
from validate_media_file import validate_recording

print("="*60)
print("RECORDING DEMONSTRATION")
print("="*60)

# Clean up old demo files
for f in glob.glob("demo_*.ts") + glob.glob("demo_*.mkv"):
    os.remove(f)

# Test 1: Single H264 stream
print("\n1. Recording single H264 stream...")
print("-" * 40)

pub1 = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--stream", "demo_h264",
    "--noaudio", "--h264", "--password", "false"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

time.sleep(2)

rec1 = subprocess.Popen([
    sys.executable, "publish.py",
    "--view", "demo_h264",
    "--record", "demo_h264",
    "--noaudio", "--password", "false"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print("Recording for 5 seconds...")
time.sleep(5)

rec1.terminate()
pub1.terminate()
time.sleep(2)

# Test 2: Single VP8 stream
print("\n2. Recording single VP8 stream...")
print("-" * 40)

pub2 = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--stream", "demo_vp8",
    "--noaudio", "--vp8", "--password", "false"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

time.sleep(2)

rec2 = subprocess.Popen([
    sys.executable, "publish.py",
    "--view", "demo_vp8",
    "--record", "demo_vp8",
    "--noaudio", "--password", "false"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print("Recording for 5 seconds...")
time.sleep(5)

rec2.terminate()
pub2.terminate()
time.sleep(2)

# Show results
print("\n" + "="*60)
print("RESULTS")
print("="*60)

all_files = glob.glob("demo_*.ts") + glob.glob("demo_*.mkv")

if all_files:
    print(f"\nCreated {len(all_files)} recording file(s):\n")
    
    for f in sorted(all_files):
        size = os.path.getsize(f)
        print(f"File: {f}")
        print(f"  Size: {size:,} bytes ({size/1024/1024:.2f} MB)")
        
        # Validate
        is_valid = validate_recording(f, verbose=False)
        if is_valid:
            print(f"  Status: ✅ Valid recording")
            
            # Identify format
            if f.endswith('.ts'):
                print(f"  Format: MPEG-TS (H.264)")
            elif f.endswith('.mkv'):
                print(f"  Format: Matroska (VP8)")
        else:
            print(f"  Status: ❌ Invalid recording")
            
        print()
else:
    print("\n❌ No files created")

# Summary
h264_files = [f for f in all_files if 'h264' in f]
vp8_files = [f for f in all_files if 'vp8' in f]

print("Summary:")
print(f"  H.264 recordings: {len(h264_files)}")
print(f"  VP8 recordings: {len(vp8_files)}")
print(f"  Total recordings: {len(all_files)}")

# Test room recording setup
print("\n" + "="*60)
print("ROOM RECORDING STATUS")
print("="*60)

print("\nChecking room recording configuration...")

# Test if room recording mode can be activated
try:
    import argparse
    args = argparse.Namespace()
    args.room = "testroom"
    args.record = "test"
    args.record_room = True
    args.room_recording = True
    args.streamin = "room_recording"
    
    # Set other required attributes
    for attr in ['streamid', 'view', 'noaudio', 'novideo', 'h264', 'vp8', 'vp9', 'av1',
                 'pipein', 'filesrc', 'ndiout', 'fdsink', 'framebuffer', 'midi',
                 'save', 'socketout', 'aom', 'rotate', 'multiviewer', 'room_ndi',
                 'pipeline', 'server', 'puuid', 'password', 'stream_filter',
                 'bitrate', 'buffer', 'width', 'height', 'framerate',
                 'nored', 'noqos', 'hostname', 'test', 'zerolatency', 
                 'noprompt', 'socketport']:
        setattr(args, attr, None)
        
    args.bitrate = 2500
    args.buffer = 200
    args.width = 1920
    args.height = 1080
    args.framerate = 30
    args.hostname = "wss://wss.vdo.ninja:443"
    args.rotate = 0
    args.noaudio = True
    
    from publish import WebRTCClient
    client = WebRTCClient(args)
    
    if client.room_recording:
        print("✅ Room recording mode: ACTIVE")
        print("✅ Multi-peer client support: AVAILABLE")
    else:
        print("❌ Room recording mode: NOT ACTIVE")
        
except Exception as e:
    print(f"❌ Error checking room recording: {e}")

print("\n" + "="*60)