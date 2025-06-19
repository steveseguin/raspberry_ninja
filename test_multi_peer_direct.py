#!/usr/bin/env python3
"""
Direct test of the multi-peer client
"""

import asyncio
import subprocess
import time
import sys
import os
from pathlib import Path


async def test_multi_peer():
    """Test multi-peer client directly"""
    print("🧪 Testing Multi-Peer Client")
    print("="*50)
    
    # Start publishers first
    room = f"multipeer_{int(time.time())}"
    publishers = []
    
    print(f"Room: {room}\n")
    
    # Start alice (H264)
    print("Starting alice (H264)...")
    p1 = subprocess.Popen([
        sys.executable, "publish.py",
        "--test", "--room", room, "--stream", "alice", "--noaudio", "--h264"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    publishers.append(p1)
    
    await asyncio.sleep(2)
    
    # Start bob (VP8)
    print("Starting bob (VP8)...")
    p2 = subprocess.Popen([
        sys.executable, "publish.py",
        "--test", "--room", room, "--stream", "bob", "--noaudio", "--vp8"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    publishers.append(p2)
    
    print("\nWaiting for publishers to connect...")
    await asyncio.sleep(8)
    
    # Now test the multi-peer client directly
    print("\nTesting multi-peer client...")
    print("-"*50)
    
    # Import and test
    sys.path.insert(0, '.')
    from publish import WebRTCClient
    import argparse
    
    # Create args for room recording mode
    args = argparse.Namespace()
    args.room = room
    args.record = "multipeer_test"
    args.streamin = "room_recording"  # This triggers viewing mode
    args.room_recording = True  # This activates multi-peer mode
    args.noaudio = True
    args.bitrate = 2000
    args.server = None
    args.puuid = None
    args.pipeline = None
    args.test = False
    args.buffer = 200
    args.nored = False
    args.noqos = False
    args.hostname = "wss://wss.vdo.ninja:443"
    args.password = None
    args.stream_filter = None
    args.streamid = None  # Add missing streamid
    
    # Fill in other required attributes
    for attr in ['h264', 'vp8', 'vp9', 'av1', 'pipein', 'filesrc', 'ndiout', 
                 'fdsink', 'framebuffer', 'midi', 'save', 'socketout', 'aom',
                 'rotate', 'novideo', 'multiviewer', 'view', 'room_ndi']:
        setattr(args, attr, False)
        
    args.socketport = None
    
    # Create client
    print("Creating WebRTC client...")
    client = WebRTCClient(args)
    
    # Connect and run for a while
    print("Connecting...")
    await client.connect()
    
    print("\nRecording for 20 seconds...")
    start_time = time.time()
    
    # Run the event loop
    recording_task = asyncio.create_task(client.loop())
    
    # Monitor for a while
    while time.time() - start_time < 20:
        await asyncio.sleep(1)
        
        # Display progress if multi-peer client exists
        if hasattr(client, 'multi_peer_client') and client.multi_peer_client:
            client.multi_peer_client.display_progress()
            
    print("\nStopping...")
    client._shutdown_requested = True
    
    # Cancel the recording task
    recording_task.cancel()
    try:
        await recording_task
    except asyncio.CancelledError:
        pass
        
    # Cleanup
    await client.cleanup_pipeline()
    
    print("-"*50)
    
    # Stop publishers
    for p in publishers:
        p.terminate()
        
    # Check results
    print("\nChecking recordings...")
    recordings = list(Path(".").glob(f"{room}_*.ts"))
    recordings.extend(list(Path(".").glob(f"{room}_*.mkv")))
    recordings.extend(list(Path(".").glob("multipeer_test_*.ts")))
    recordings.extend(list(Path(".").glob("multipeer_test_*.mkv")))
    
    if recordings:
        print(f"\n✅ Found {len(recordings)} recordings:")
        for r in sorted(recordings):
            size = r.stat().st_size
            print(f"  - {r.name} ({size:,} bytes)")
            
        # Check if we have multiple streams
        stream_names = set()
        for r in recordings:
            if "alice" in r.name:
                stream_names.add("alice")
            elif "bob" in r.name:
                stream_names.add("bob")
                
        if len(stream_names) > 1:
            print(f"\n✅ SUCCESS! Recorded {len(stream_names)} different streams")
        else:
            print("\n⚠️  Only one stream recorded")
    else:
        print("\n❌ No recordings found")
        
    return len(recordings) > 0


if __name__ == "__main__":
    success = asyncio.run(test_multi_peer())
    sys.exit(0 if success else 1)