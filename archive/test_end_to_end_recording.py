#!/usr/bin/env python3
"""End-to-end test: publish a test stream and record it"""

import asyncio
import sys
import time
import os
import glob

async def run_test():
    """Run publisher and recorder together"""
    
    # Clean up old test files
    for f in glob.glob("e2e_test_room_*.mkv") + glob.glob("e2e_test_room_*.webm"):
        try:
            os.remove(f)
        except:
            pass
    
    print("=== End-to-End Room Recording Test ===\n")
    
    # Start publisher first
    print("1. Starting test publisher...")
    publisher = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--room', 'e2e_test_room',
        '--streamid', 'test_stream_001',
        '--test',  # Use test pattern
        '--password', 'false',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    # Wait for publisher to be ready
    print("   Waiting for publisher to connect...")
    start_time = time.time()
    publisher_ready = False
    
    while time.time() - start_time < 20:
        try:
            line = await asyncio.wait_for(publisher.stdout.readline(), timeout=1.0)
            if line:
                decoded = line.decode().strip()
                if "seed start" in decoded or "publishing" in decoded.lower():
                    publisher_ready = True
                    print("   ✓ Publisher ready!\n")
                    break
        except asyncio.TimeoutError:
            pass
    
    if not publisher_ready:
        print("   ✗ Publisher failed to start")
        publisher.terminate()
        await publisher.wait()
        return
    
    # Give it a moment to stabilize
    await asyncio.sleep(2)
    
    # Start recorder
    print("2. Starting room recorder...")
    recorder = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--room', 'e2e_test_room',
        '--record-room',
        '--audio',
        '--password', 'false',
        '--debug',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    print("   Monitoring recording for 60 seconds...\n")
    
    # Monitor recorder output
    record_start = time.time()
    events = {
        'room_joined': False,
        'stream_found': False,
        'offer_received': False,
        'media_detected': False,
        'pad_added': False,
        'recording_active': False
    }
    
    while time.time() - record_start < 60:
        try:
            line = await asyncio.wait_for(recorder.stdout.readline(), timeout=1.0)
            if line:
                decoded = line.decode().strip()
                
                # Check for key events
                if "joining room" in decoded:
                    events['room_joined'] = True
                elif "Found 1 streams to record" in decoded:
                    events['stream_found'] = True
                elif "Processing remote offer" in decoded:
                    events['offer_received'] = True
                elif "Media offer received" in decoded:
                    events['media_detected'] = True
                    print(f"   *** MEDIA DETECTED: {decoded} ***")
                elif "New pad added" in decoded:
                    events['pad_added'] = True
                    print(f"   *** PAD ADDED: {decoded} ***")
                elif "Recording started" in decoded or "handle_video_pad" in decoded:
                    events['recording_active'] = True
                    print(f"   *** RECORDING ACTIVE: {decoded} ***")
                
                # Print important messages
                if any(keyword in decoded for keyword in [
                    "ERROR", "WARNING", "Media", "pad", "Recording",
                    "Data-channel-only", "ICE connection", "bytes"
                ]):
                    elapsed = int(time.time() - record_start)
                    print(f"   [{elapsed}s] {decoded}")
                    
        except asyncio.TimeoutError:
            # Status update every 15 seconds
            elapsed = int(time.time() - record_start)
            if elapsed % 15 == 0:
                print(f"\n   --- Status at {elapsed}s ---")
                for event, status in events.items():
                    print(f"   {'✓' if status else '✗'} {event}")
                print()
    
    print("\n3. Stopping recording and publisher...")
    recorder.terminate()
    publisher.terminate()
    
    await recorder.wait()
    await publisher.wait()
    
    print("\n=== Test Results ===")
    
    # Check events
    print("\nEvent Summary:")
    success_count = 0
    for event, status in events.items():
        print(f"  {'✓' if status else '✗'} {event}")
        if status:
            success_count += 1
    
    # Check output files
    print("\nOutput Files:")
    files = glob.glob("e2e_test_room_*.mkv") + glob.glob("e2e_test_room_*.webm") + glob.glob("e2e_test_room_*.ts")
    
    if not files:
        print("  No recording files found!")
    else:
        total_size = 0
        for f in sorted(files):
            size = os.path.getsize(f)
            total_size += size
            print(f"  {f}: {size:,} bytes")
        
        print(f"\nTotal recorded: {total_size:,} bytes")
        
        if total_size > 1000:
            print("\n✓ SUCCESS: Recording produced data!")
            
            # Test playback of largest file
            largest = max(files, key=os.path.getsize)
            print(f"\nTesting playback of {largest}...")
            
            probe = await asyncio.create_subprocess_exec(
                'ffprobe', '-v', 'error', '-show_format', '-show_streams',
                largest,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await probe.communicate()
            
            if probe.returncode == 0:
                print("✓ File is valid and playable!")
            else:
                print(f"✗ Playback test failed: {stderr.decode()}")
        else:
            print("\n✗ FAILED: Recording files are empty")
    
    print(f"\n=== Test Complete ({success_count}/6 events successful) ===")

if __name__ == "__main__":
    asyncio.run(run_test())