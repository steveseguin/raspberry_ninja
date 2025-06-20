#!/usr/bin/env python3
"""Test direct recording from the room"""

import asyncio
import sys
import time

async def test_recording():
    """Test recording with timeout and monitoring"""
    print("Starting room recording test...")
    
    # Run the recording command
    process = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--room', 'testroom123999999999',
        '--record-room',
        '--audio',
        '--password', 'false',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    print("Recording started, waiting 45 seconds for data...")
    
    # Monitor output for 45 seconds
    start_time = time.time()
    while time.time() - start_time < 45:
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
            if line:
                print(line.decode().strip())
        except asyncio.TimeoutError:
            pass
    
    print("\nStopping recording...")
    process.terminate()
    await process.wait()
    
    print("\nRecording stopped. Checking files...")
    
    # Check for output files
    import glob
    files = glob.glob("testroom123999999999_*.mkv")
    
    for f in files:
        import os
        size = os.path.getsize(f)
        print(f"Found: {f} - Size: {size} bytes")
        
        if size > 0:
            print(f"\nTesting playback of {f}...")
            # Try to get media info
            probe = await asyncio.create_subprocess_exec(
                'ffprobe', '-v', 'error', '-show_format', '-show_streams', f,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await probe.communicate()
            
            if probe.returncode == 0:
                print("File appears to be valid!")
                print("Stream info:")
                print(stdout.decode()[:500] + "..." if len(stdout) > 500 else stdout.decode())
            else:
                print(f"Error checking file: {stderr.decode()}")

if __name__ == "__main__":
    asyncio.run(test_recording())