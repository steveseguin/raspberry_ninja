#!/usr/bin/env python3
"""Test recording with WAV audio output"""

import asyncio
import sys
import time
import os
import glob

async def test_wav():
    print("=== Testing Recording with WAV Audio ===\n")
    
    # Record for 20 seconds
    print("Recording for 20 seconds...")
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
    
    print("\n=== Checking Files ===\n")
    
    # Get all files
    video_files = glob.glob("testroom123999999999_*.webm")
    audio_files = glob.glob("testroom123999999999_*_audio.wav")
    
    print(f"Found {len(video_files)} video (.webm) and {len(audio_files)} audio (.wav) files\n")
    
    # Test video files
    for vf in sorted(video_files):
        print(f"VIDEO: {vf}")
        size = os.path.getsize(vf)
        print(f"  Size: {size:,} bytes")
        
        if size > 0:
            # Quick ffmpeg test
            cmd = await asyncio.create_subprocess_exec(
                'ffmpeg', '-v', 'error', '-i', vf, '-f', 'null', '-',
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await cmd.communicate()
            
            if cmd.returncode == 0:
                print("  ✅ Video is playable")
            else:
                print(f"  ❌ Error: {stderr.decode()[:100]}")
        print()
    
    # Test audio files
    for af in sorted(audio_files):
        print(f"AUDIO: {af}")
        size = os.path.getsize(af)
        print(f"  Size: {size:,} bytes")
        
        if size > 0:
            # Test with ffmpeg
            cmd = await asyncio.create_subprocess_exec(
                'ffmpeg', '-v', 'error', '-i', af, '-f', 'null', '-',
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await cmd.communicate()
            
            if cmd.returncode == 0:
                print("  ✅ Audio is playable")
                
                # Get duration
                cmd = await asyncio.create_subprocess_exec(
                    'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1', af,
                    stdout=asyncio.subprocess.PIPE
                )
                stdout, _ = await cmd.communicate()
                
                if stdout:
                    try:
                        duration = float(stdout.decode().strip())
                        print(f"  Duration: {duration:.1f} seconds")
                    except:
                        pass
                        
                # Test with gst-launch
                cmd = await asyncio.create_subprocess_exec(
                    'gst-launch-1.0', 'filesrc', f'location={af}', '!',
                    'wavparse', '!', 'audioconvert', '!', 'fakesink',
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await cmd.communicate()
                
                if cmd.returncode == 0:
                    print("  ✅ Playable with gst-launch")
            else:
                print(f"  ❌ Error: {stderr.decode()[:100]}")
        else:
            print("  ❌ Empty file")
        print()
    
    # Test combining
    if video_files and audio_files and all(os.path.getsize(f) > 0 for f in audio_files[:1]):
        print("=== Testing Muxing ===")
        vf = video_files[0]
        af = audio_files[0]
        output = 'muxed_output.mp4'
        
        cmd = await asyncio.create_subprocess_exec(
            'ffmpeg', '-y', '-i', vf, '-i', af,
            '-c:v', 'copy', '-c:a', 'aac', output,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await cmd.communicate()
        
        if cmd.returncode == 0 and os.path.exists(output):
            size = os.path.getsize(output)
            print(f"✅ Successfully muxed to {output} ({size:,} bytes)")
            os.remove(output)
        else:
            print("❌ Muxing failed")

if __name__ == "__main__":
    asyncio.run(test_wav())