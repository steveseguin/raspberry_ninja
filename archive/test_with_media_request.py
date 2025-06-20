#!/usr/bin/env python3
"""Test recording with explicit media request"""

import asyncio
import sys
import time
import json

async def test_recording_with_media():
    """Test recording with media constraints"""
    print("Starting room recording test with media constraints...")
    
    # Create a modified publish.py command that requests media
    process = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--room', 'testroom123999999999',
        '--record-room',
        '--audio',
        '--video',  # Explicitly request video
        '--password', 'false',
        '--bitrate', '4000',  # Set bitrate to ensure quality
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    print("Recording started, waiting 60 seconds for media data...")
    
    # Monitor output
    start_time = time.time()
    pad_found = False
    recording_started = False
    
    while time.time() - start_time < 60:
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
            if line:
                decoded = line.decode().strip()
                print(decoded)
                
                # Look for important messages
                if "New pad added" in decoded:
                    pad_found = True
                    print("\n*** MEDIA PAD DETECTED! ***\n")
                elif "Recording started" in decoded or "handle_video_pad" in decoded:
                    recording_started = True
                    print("\n*** RECORDING STARTED! ***\n")
                    
        except asyncio.TimeoutError:
            pass
    
    print(f"\nPad found: {pad_found}, Recording started: {recording_started}")
    print("\nStopping recording...")
    process.terminate()
    await process.wait()
    
    print("\nRecording stopped. Checking files...")
    
    # Check for output files
    import glob
    import os
    
    # Look for all recording files
    patterns = ["testroom123999999999_*.mkv", "testroom123999999999_*.webm", "testroom123999999999_*.ts"]
    all_files = []
    
    for pattern in patterns:
        files = glob.glob(pattern)
        all_files.extend(files)
    
    if not all_files:
        print("No recording files found!")
        return
        
    # Sort by modification time
    all_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    # Check recent files
    print(f"\nFound {len(all_files)} recording files:")
    for f in all_files[:10]:  # Show only 10 most recent
        size = os.path.getsize(f)
        mtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(f)))
        print(f"  {f} - Size: {size:,} bytes - Modified: {mtime}")
        
        if size > 1000:  # More than 1KB
            print(f"\n  Testing playback of {f}...")
            # Try to get media info
            probe = await asyncio.create_subprocess_exec(
                'ffprobe', '-v', 'error', '-show_format', '-show_streams', 
                '-print_format', 'json', f,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await probe.communicate()
            
            if probe.returncode == 0:
                try:
                    info = json.loads(stdout.decode())
                    print(f"  Format: {info.get('format', {}).get('format_name', 'unknown')}")
                    print(f"  Duration: {info.get('format', {}).get('duration', 'unknown')} seconds")
                    print(f"  Streams: {len(info.get('streams', []))}")
                    for i, stream in enumerate(info.get('streams', [])):
                        print(f"    Stream {i}: {stream.get('codec_type', 'unknown')} - {stream.get('codec_name', 'unknown')}")
                except:
                    pass
            else:
                print(f"  Error checking file: {stderr.decode()}")

if __name__ == "__main__":
    asyncio.run(test_recording_with_media())