#!/usr/bin/env python3
"""Final test of recording with proper timestamps"""

import asyncio
import time
import os
import glob
import json

async def final_test():
    print("=== Final Recording Test with Timestamp Fix ===\n")
    
    # Record for 30 seconds
    print("Starting recording for 30 seconds...")
    process = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--room', 'testroom123999999999',
        '--record-room',
        '--audio',
        '--password', 'false',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL
    )
    
    # Wait for recording to establish
    await asyncio.sleep(30)
    
    print("Stopping recording...")
    process.terminate()
    await process.wait()
    
    print("\n=== Checking Recorded Files ===\n")
    
    # Get all files
    all_files = glob.glob("testroom123999999999_*.webm")
    video_files = [f for f in all_files if "_audio." not in f]
    audio_files = [f for f in all_files if "_audio." in f]
    
    print(f"Found {len(video_files)} video files and {len(audio_files)} audio files\n")
    
    # Check each file
    for vf in sorted(video_files):
        print(f"VIDEO: {vf}")
        size = os.path.getsize(vf)
        print(f"  Size: {size:,} bytes")
        
        # Get duration
        cmd = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', vf,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await cmd.communicate()
        
        try:
            duration = float(stdout.decode().strip())
            print(f"  Duration: {duration:.1f} seconds")
            
            if duration > 0:
                print("  ✅ File has proper duration!")
            else:
                print("  ❌ File still has no duration")
                
                # Try alternative duration check
                cmd = await asyncio.create_subprocess_exec(
                    'ffmpeg', '-i', vf, '-f', 'null', '-',
                    stderr=asyncio.subprocess.PIPE
                )
                _, stderr = await cmd.communicate()
                
                import re
                match = re.search(r'Duration: (\d{2}:\d{2}:\d{2}\.\d{2})', stderr.decode())
                if match:
                    print(f"  Alternative duration: {match.group(1)}")
        except:
            print("  Could not determine duration")
            
        # Test seeking
        cmd = await asyncio.create_subprocess_exec(
            'ffmpeg', '-ss', '00:00:05', '-i', vf, '-vframes', '1',
            '-f', 'null', '-',
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        result = await cmd.communicate()
        
        if cmd.returncode == 0:
            print("  ✅ File is seekable")
        else:
            print("  ❌ File is not seekable")
        print()
    
    for af in sorted(audio_files):
        print(f"AUDIO: {af}")
        size = os.path.getsize(af)
        print(f"  Size: {size:,} bytes")
        
        # Get duration
        cmd = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', af,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await cmd.communicate()
        
        try:
            duration = float(stdout.decode().strip())
            print(f"  Duration: {duration:.1f} seconds")
            
            if duration > 0:
                print("  ✅ File has proper duration!")
            else:
                print("  ❌ File still has no duration")
        except:
            print("  Could not determine duration")
        print()
    
    # Test playback in a media player simulator
    print("\n=== Media Player Compatibility ===")
    
    if video_files:
        test_file = video_files[0]
        
        # Test with VLC-like player simulation
        cmd = await asyncio.create_subprocess_exec(
            'ffplay', '-v', 'quiet', '-autoexit', '-t', '5', test_file,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        try:
            await asyncio.wait_for(cmd.communicate(), timeout=10)
            if cmd.returncode == 0:
                print("✅ Video plays correctly in media player")
            else:
                print("❌ Video playback failed in media player")
        except:
            # ffplay might not be available
            print("⚠️  Could not test with ffplay (not installed)")
            
    # Summary
    print("\n=== SUMMARY ===")
    if len(video_files) >= 2 and len(audio_files) >= 2:
        print("✅ All expected files created (2 video + 2 audio)")
    else:
        print(f"❌ Missing files: {len(video_files)} video, {len(audio_files)} audio")
        
    total_size = sum(os.path.getsize(f) for f in all_files)
    print(f"Total size: {total_size:,} bytes ({total_size/1024/1024:.1f} MB)")

if __name__ == "__main__":
    import sys
    asyncio.run(final_test())