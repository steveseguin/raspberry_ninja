#!/usr/bin/env python3
"""Final test of room recording with audio"""

import asyncio
import sys
import time
import os
import glob

async def test_recording():
    print("Testing room recording with audio (using working subprocess)...\n")
    
    # Start recording
    process = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--room', 'testroom123999999999',
        '--record-room',
        '--audio',
        '--password', 'false',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    print("Recording started. Monitoring for 60 seconds...\n")
    
    start_time = time.time()
    using_glib = False
    ice_connected = False
    pads_added = False
    data_received = False
    
    while time.time() - start_time < 60:
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
            if line:
                decoded = line.decode().strip()
                
                # Check what subprocess is being used
                if "Using standard WebM/MP4 recording" in decoded:
                    using_glib = True
                    print("✓ Using working subprocess (glib)")
                
                # Check for connection
                if "ICE connection state: connected" in decoded or "WebRTC.*CONNECTED" in decoded:
                    ice_connected = True
                    print("✓ ICE connected!")
                
                # Check for media pads
                if "New pad added" in decoded:
                    pads_added = True
                    print(f"✓ Media pad detected: {decoded}")
                
                # Check for data flow
                if "bytes" in decoded and ("written" in decoded or "received" in decoded):
                    data_received = True
                    print(f"✓ Data flowing: {decoded}")
                
                # Print progress every 10 seconds
                elapsed = int(time.time() - start_time)
                if elapsed % 10 == 0 and elapsed > 0:
                    print(f"\n[{elapsed}s] Status: ICE={ice_connected}, Pads={pads_added}, Data={data_received}")
                    
        except asyncio.TimeoutError:
            pass
    
    print("\nStopping recording...")
    process.terminate()
    await process.wait()
    
    print("\n=== Results ===")
    print(f"Using correct subprocess: {using_glib}")
    print(f"ICE connected: {ice_connected}")
    print(f"Media pads added: {pads_added}")
    print(f"Data received: {data_received}")
    
    print("\n=== Output Files ===")
    files = glob.glob("testroom123999999999_*.webm") + glob.glob("testroom123999999999_*.mkv")
    
    if not files:
        print("No files found!")
        return
    
    total_size = 0
    for f in sorted(files)[-5:]:  # Show last 5 files
        size = os.path.getsize(f)
        total_size += size
        mtime = time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(f)))
        print(f"{f}: {size:,} bytes (modified {mtime})")
    
    print(f"\nTotal size: {total_size:,} bytes")
    
    if total_size > 1000:
        print("\n✓ SUCCESS! Recording has data!")
        
        # Test playback
        largest = max(files, key=os.path.getsize)
        print(f"\nTesting playback of {largest}...")
        
        probe = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', largest,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await probe.communicate()
        
        if probe.returncode == 0:
            import json
            try:
                info = json.loads(stdout.decode())
                print(f"Duration: {float(info.get('format', {}).get('duration', 0)):.1f}s")
                print(f"Streams: {len(info.get('streams', []))}")
                for stream in info.get('streams', []):
                    print(f"  - {stream.get('codec_type')}: {stream.get('codec_name')}")
                print("\n✓ File is valid and playable!")
            except:
                print("✓ File appears valid")
        else:
            print("Could not probe file")
    else:
        print("\n✗ Recording files are still empty")

if __name__ == "__main__":
    asyncio.run(test_recording())