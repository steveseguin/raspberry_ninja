#!/usr/bin/env python3
"""
Inline test that imports and runs the code directly
"""

import asyncio
import sys
import os
import glob
import argparse

# Clean up
for f in glob.glob("inline_*.ts") + glob.glob("inline_*.mkv"):
    try:
        os.remove(f)
    except:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_inline():
    """Test by importing and running directly"""
    print("="*60)
    print("INLINE ROOM RECORDING TEST")
    print("="*60)
    
    # Import the main module
    from publish import WebRTCClient
    
    # Create args
    args = argparse.Namespace()
    
    # Required args
    args.room = 'testroom123'
    args.record = 'inline'
    args.record_room = True
    args.room_ndi = False
    args.password = 'false'
    args.noaudio = True
    args.server = None
    args.hostname = None
    args.streamid = None
    args.puuid = None
    args.buffer = 200
    args.stream_filter = None
    
    # Set up streamin based on record_room
    args.streamin = "room_recording"
    args.room_recording = True
    
    # Other args with defaults
    for attr in ['view', 'novideo', 'h264', 'vp8', 'vp9', 'av1', 'test', 
                 'pipein', 'filesrc', 'ndiout', 'fdsink', 'framebuffer',
                 'midi', 'save', 'socketout', 'aom', 'rotate', 'multiviewer',
                 'pipeline', 'bitrate', 'width', 'height', 'framerate',
                 'nored', 'noqos', 'zerolatency', 'noprompt', 'socketport']:
        setattr(args, attr, None)
    
    args.bitrate = 2500
    args.width = 1920
    args.height = 1080
    args.framerate = 30
    args.rotate = 0
    
    print(f"Args configured:")
    print(f"  room: {args.room}")
    print(f"  record: {args.record}")
    print(f"  record_room: {args.record_room}")
    print(f"  room_recording: {args.room_recording}")
    print(f"  streamin: {args.streamin}")
    
    # Create client
    print("\nCreating WebRTC client...")
    client = WebRTCClient(args)
    
    print(f"  room_recording enabled: {client.room_recording}")
    print(f"  room_name: {client.room_name}")
    
    # Connect
    print("\nConnecting...")
    try:
        await client.connect()
        print("✅ Connected")
        
        # Join room
        print("\nJoining room...")
        await client.sendMessageAsync({
            "request": "joinroom",
            "roomid": client.room_name
        })
        
        # Start the message loop in background
        print("\nStarting message loop...")
        loop_task = asyncio.create_task(client.loop())
        
        # Run for 20 seconds
        print("\nRunning for 20 seconds...")
        await asyncio.sleep(20)
        
        # Cancel the loop
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        print("\nCleaning up...")
        if hasattr(client, 'multi_peer_client') and client.multi_peer_client:
            client.multi_peer_client.cleanup()
        if hasattr(client, 'conn'):
            await client.conn.close()
    
    # Check for files
    print("\n" + "="*60)
    print("RESULTS:")
    files = glob.glob("inline_*.ts") + glob.glob("inline_*.mkv") + \
            glob.glob("testroom123_*.ts") + glob.glob("testroom123_*.mkv")
    
    if files:
        print(f"\n✅ Found {len(files)} files:")
        for f in files:
            print(f"  {f}: {os.path.getsize(f):,} bytes")
    else:
        print("\n❌ No recordings found")
    
    return len(files) > 0

if __name__ == "__main__":
    print("Starting inline test...")
    success = asyncio.run(test_inline())
    print(f"\nTest {'PASSED' if success else 'FAILED'}")