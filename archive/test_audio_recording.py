#!/usr/bin/env python3
"""Test audio recording with separate files"""

import asyncio
import sys
import time
import os
import glob

async def test_audio():
    print("Testing room recording with audio (expecting separate audio files)...\n")
    
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
    
    print("Recording started. Monitoring for 45 seconds...\n")
    
    start_time = time.time()
    audio_pads = 0
    video_pads = 0
    audio_files = []
    video_files = []
    
    while time.time() - start_time < 45:
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
            if line:
                decoded = line.decode().strip()
                
                # Count pads
                if "AUDIO STREAM DETECTED" in decoded:
                    audio_pads += 1
                    print(f"✓ Audio stream detected: {decoded}")
                elif "VIDEO STREAM DETECTED" in decoded:
                    video_pads += 1
                    print(f"✓ Video stream detected: {decoded}")
                
                # Track files
                if "Output file:" in decoded and "_audio." in decoded:
                    audio_files.append(decoded.split("Output file:")[-1].strip())
                    print(f"✓ Audio file: {decoded}")
                elif "Output file:" in decoded and "_audio." not in decoded:
                    video_files.append(decoded.split("Output file:")[-1].strip())
                    print(f"✓ Video file: {decoded}")
                
                # Show important messages
                if any(keyword in decoded for keyword in [
                    "RECORDING START", "Audio recording", "Opus", "ERROR"
                ]):
                    print(f"[{int(time.time() - start_time)}s] {decoded}")
                    
        except asyncio.TimeoutError:
            pass
    
    print("\nStopping recording...")
    process.terminate()
    await process.wait()
    
    print("\n=== Recording Summary ===")
    print(f"Audio pads detected: {audio_pads}")
    print(f"Video pads detected: {video_pads}")
    print(f"Audio files created: {len(audio_files)}")
    print(f"Video files created: {len(video_files)}")
    
    print("\n=== Checking Files ===")
    
    # Check all output files
    all_files = glob.glob("testroom123999999999_*.webm") + glob.glob("testroom123999999999_*.mkv")
    video_files = [f for f in all_files if "_audio." not in f]
    audio_files = [f for f in all_files if "_audio." in f]
    
    print(f"\nVideo files found: {len(video_files)}")
    for f in sorted(video_files):
        size = os.path.getsize(f)
        print(f"  {f}: {size:,} bytes")
    
    print(f"\nAudio files found: {len(audio_files)}")
    for f in sorted(audio_files):
        size = os.path.getsize(f)
        print(f"  {f}: {size:,} bytes")
    
    # Test playback of largest files
    if video_files:
        largest_video = max(video_files, key=os.path.getsize)
        print(f"\nChecking video file: {largest_video}")
        
        probe = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'quiet', '-show_streams', '-select_streams', 'v',
            '-print_format', 'default=noprint_wrappers=1:nokey=1',
            largest_video,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await probe.communicate()
        if b"video" in stdout:
            print("✓ Video stream confirmed")
    
    if audio_files:
        largest_audio = max(audio_files, key=os.path.getsize)
        print(f"\nChecking audio file: {largest_audio}")
        
        probe = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'quiet', '-show_streams', '-select_streams', 'a',
            '-print_format', 'default=noprint_wrappers=1:nokey=1',
            largest_audio,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await probe.communicate()
        if b"audio" in stdout:
            print("✓ Audio stream confirmed")
    
    total_files = len(video_files) + len(audio_files)
    print(f"\n{'✓ SUCCESS!' if total_files >= 4 else '✗ FAILED!'} Total files: {total_files} (expected 4: 2 video + 2 audio)")

if __name__ == "__main__":
    asyncio.run(test_audio())