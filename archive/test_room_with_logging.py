#!/usr/bin/env python3
"""Test room recording with detailed logging"""

import asyncio
import sys
import os

async def test_with_logging():
    """Run recording with extra debug output"""
    print("Starting room recording with debug logging...")
    
    # Enable debug mode
    env = os.environ.copy()
    env['GST_DEBUG'] = '3'  # Enable GStreamer debug
    
    process = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--room', 'testroom123999999999',
        '--record-room',
        '--audio',
        '--password', 'false',
        '--debug',  # Enable debug mode
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env
    )
    
    print("Recording started with debug mode...")
    print("Monitoring for 90 seconds...\n")
    
    # Track important events
    events = {
        'connection': False,
        'room_joined': False,
        'streams_found': False,
        'offer_received': False,
        'answer_sent': False,
        'ice_connected': False,
        'pad_added': False,
        'recording_started': False,
        'data_received': False
    }
    
    start_time = asyncio.get_event_loop().time()
    timeout = 90  # seconds
    
    while asyncio.get_event_loop().time() - start_time < timeout:
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
            if line:
                decoded = line.decode().strip()
                
                # Check for key events
                if "Connected successfully" in decoded:
                    events['connection'] = True
                elif "joining room" in decoded:
                    events['room_joined'] = True
                elif "Found" in decoded and "streams to record" in decoded:
                    events['streams_found'] = True
                elif "Processing remote offer" in decoded:
                    events['offer_received'] = True
                elif "Sending answer" in decoded:
                    events['answer_sent'] = True
                elif "ICE connection state: connected" in decoded or "WebRTC connection state: GST_WEBRTC_PEER_CONNECTION_STATE_CONNECTED" in decoded:
                    events['ice_connected'] = True
                elif "New pad added" in decoded:
                    events['pad_added'] = True
                    print(f"\n*** IMPORTANT: {decoded} ***\n")
                elif "Recording started" in decoded or "handle_video_pad" in decoded or "handle_audio_pad" in decoded:
                    events['recording_started'] = True
                    print(f"\n*** RECORDING EVENT: {decoded} ***\n")
                elif "bytes written" in decoded or "Data received" in decoded:
                    events['data_received'] = True
                
                # Print important lines
                if any(keyword in decoded for keyword in [
                    "New pad", "handle_", "Recording", "ERROR", "WARNING",
                    "Media offer", "Data-channel-only", "transceiver",
                    "ICE connection", "WebRTC connection", "bytes"
                ]):
                    print(f"[{int(asyncio.get_event_loop().time() - start_time)}s] {decoded}")
                    
        except asyncio.TimeoutError:
            # Print status every 10 seconds
            elapsed = int(asyncio.get_event_loop().time() - start_time)
            if elapsed % 10 == 0:
                print(f"\n--- Status at {elapsed}s ---")
                for event, occurred in events.items():
                    status = "✓" if occurred else "✗"
                    print(f"  {status} {event}")
                print("---\n")
    
    print("\nStopping recording...")
    process.terminate()
    await process.wait()
    
    print("\n=== Final Event Summary ===")
    for event, occurred in events.items():
        status = "✓" if occurred else "✗"
        print(f"  {status} {event}")
    
    print("\n=== Checking Output Files ===")
    import glob
    files = glob.glob("testroom123999999999_*.*")
    
    if not files:
        print("No recording files found!")
    else:
        total_size = 0
        for f in sorted(files):
            size = os.path.getsize(f)
            total_size += size
            print(f"  {f}: {size:,} bytes")
        
        print(f"\nTotal size: {total_size:,} bytes")
        
        # Find the largest file
        if total_size > 0:
            largest = max(files, key=os.path.getsize)
            print(f"\nLargest file: {largest} ({os.path.getsize(largest):,} bytes)")

if __name__ == "__main__":
    asyncio.run(test_with_logging())