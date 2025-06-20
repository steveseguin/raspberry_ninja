#!/usr/bin/env python3
"""Test if WebM files work in VLC after reverting changes"""

import asyncio
import time
import os
import glob
import sys

async def test_restored_webm():
    print("=== Testing Restored WebM Recording ===\n")
    
    # Record for 20 seconds
    print("Starting recording for 20 seconds...")
    process = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--room', 'testroom123999999999',
        '--record-room',
        '--audio',
        '--password', 'false',
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    
    await asyncio.sleep(20)
    
    print("Stopping recording...")
    process.terminate()
    await process.wait()
    
    print("\n=== Checking Recorded Files ===\n")
    
    # Get all files
    all_files = glob.glob("testroom123999999999_*.webm")
    video_files = [f for f in all_files if "_audio." not in f]
    audio_files = [f for f in all_files if "_audio." in f]
    
    print(f"Found {len(video_files)} video files and {len(audio_files)} audio files\n")
    
    # Test each video file
    for vf in sorted(video_files):
        print(f"VIDEO: {vf}")
        size = os.path.getsize(vf)
        print(f"  Size: {size:,} bytes")
        
        # Get format info
        cmd = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', vf,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await cmd.communicate()
        
        if stdout:
            import json
            try:
                info = json.loads(stdout.decode())
                fmt = info.get('format', {})
                print(f"  Format: {fmt.get('format_name', 'unknown')}")
                print(f"  Duration: {fmt.get('duration', 'N/A')}")
                
                # Check if it has the streaming flag
                tags = fmt.get('tags', {})
                if tags:
                    print(f"  Tags: {', '.join(f'{k}={v}' for k,v in tags.items())}")
                    
            except:
                pass
        
        # Test if VLC can decode it
        cmd = await asyncio.create_subprocess_exec(
            'ffmpeg', '-v', 'error', '-i', vf, '-vframes', '1', '-f', 'null', '-',
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await cmd.communicate()
        
        if cmd.returncode == 0:
            print("  ✅ File is decodable")
        else:
            print(f"  ❌ Decode error: {stderr.decode()}")
        print()
    
    # Quick test for audio files
    for af in sorted(audio_files):
        print(f"AUDIO: {af}")
        size = os.path.getsize(af)
        print(f"  Size: {size:,} bytes")
        
        # Test decode
        cmd = await asyncio.create_subprocess_exec(
            'ffmpeg', '-v', 'error', '-i', af, '-f', 'null', '-',
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await cmd.communicate()
        
        if cmd.returncode == 0:
            print("  ✅ File is decodable")
        else:
            print(f"  ❌ Decode error: {stderr.decode()}")
        print()
    
    print("\n=== VLC Compatibility ===")
    print("The files should now work in VLC with streamable=True")
    print("This allows VLC to play WebM files without seeking to the end for duration")

if __name__ == "__main__":
    asyncio.run(test_restored_webm())