#!/usr/bin/env python3
"""Test MPEG-TS recording format"""

import asyncio
import sys
import time
import os
import glob

async def test_mpegts():
    print("=== Testing MPEG-TS Recording ===\n")
    
    # Record for 20 seconds
    print("Starting recording (MPEG-TS format)...")
    process = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--room', 'testroom123999999999',
        '--record-room',
        '--audio',
        '--password', 'false',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    # Monitor startup
    print("\nMonitoring startup...")
    start_time = time.time()
    while time.time() - start_time < 5:
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=0.5)
            if line:
                decoded = line.decode().strip()
                if any(word in decoded for word in ["Output file:", "ERROR", "Failed"]):
                    print(f"  {decoded}")
        except asyncio.TimeoutError:
            pass
    
    print("\nRecording for 15 more seconds...")
    await asyncio.sleep(15)
    
    print("Stopping recording...")
    process.terminate()
    await process.wait()
    
    print("\n=== Checking Recorded Files ===\n")
    
    # Look for TS files
    video_files = glob.glob("testroom123999999999_*[!_audio].ts")
    audio_files = glob.glob("testroom123999999999_*_audio.ts")
    
    print(f"Found {len(video_files)} video files and {len(audio_files)} audio files\n")
    
    # Test each video file
    for vf in sorted(video_files):
        print(f"VIDEO: {vf}")
        size = os.path.getsize(vf)
        print(f"  Size: {size:,} bytes")
        
        if size > 0:
            # Test with ffprobe
            cmd = await asyncio.create_subprocess_exec(
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_streams', vf,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await cmd.communicate()
            
            if stdout:
                import json
                try:
                    info = json.loads(stdout.decode())
                    streams = info.get('streams', [])
                    print(f"  Streams: {len(streams)}")
                    for s in streams:
                        print(f"    - {s.get('codec_type')}: {s.get('codec_name')} {s.get('width', '')}x{s.get('height', '')}")
                except:
                    pass
            
            # Test playback with ffmpeg
            cmd = await asyncio.create_subprocess_exec(
                'ffmpeg', '-v', 'error', '-i', vf, '-f', 'null', '-',
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await cmd.communicate()
            
            if cmd.returncode == 0:
                print("  ✅ File is playable with ffmpeg")
            else:
                print(f"  ❌ ffmpeg error: {stderr.decode()}")
                
            # Test with gst-launch
            cmd = await asyncio.create_subprocess_exec(
                'gst-launch-1.0', 'filesrc', f'location={vf}', '!',
                'tsdemux', '!', 'fakesink',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await cmd.communicate()
            
            if cmd.returncode == 0:
                print("  ✅ File is playable with gst-launch")
            else:
                print("  ❌ gst-launch failed")
        else:
            print("  ❌ File is empty")
        print()
    
    # Test audio files
    for af in sorted(audio_files):
        print(f"AUDIO: {af}")
        size = os.path.getsize(af)
        print(f"  Size: {size:,} bytes")
        
        if size > 0:
            # Test with ffprobe
            cmd = await asyncio.create_subprocess_exec(
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_streams', af,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await cmd.communicate()
            
            if stdout:
                import json
                try:
                    info = json.loads(stdout.decode())
                    streams = info.get('streams', [])
                    for s in streams:
                        if s.get('codec_type') == 'audio':
                            print(f"  Audio: {s.get('codec_name')} @ {s.get('sample_rate')} Hz")
                except:
                    pass
            
            # Test playback
            cmd = await asyncio.create_subprocess_exec(
                'ffmpeg', '-v', 'error', '-i', af, '-f', 'null', '-',
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await cmd.communicate()
            
            if cmd.returncode == 0:
                print("  ✅ File is playable with ffmpeg")
            else:
                print(f"  ❌ ffmpeg error: {stderr.decode()}")
        else:
            print("  ❌ File is empty")
        print()
    
    # Test combining audio and video
    if video_files and audio_files:
        print("\n=== Testing Audio/Video Sync ===")
        vf = video_files[0]
        af = audio_files[0]
        output = 'combined_output.mp4'
        
        print(f"Combining {os.path.basename(vf)} + {os.path.basename(af)}")
        
        cmd = await asyncio.create_subprocess_exec(
            'ffmpeg', '-y', '-i', vf, '-i', af,
            '-c:v', 'copy', '-c:a', 'copy',
            '-map', '0:v', '-map', '1:a',
            output,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await cmd.communicate()
        
        if cmd.returncode == 0 and os.path.exists(output):
            size = os.path.getsize(output)
            print(f"✅ Successfully combined! Output: {output} ({size:,} bytes)")
            os.remove(output)
        else:
            print(f"❌ Combination failed: {stderr.decode()}")

if __name__ == "__main__":
    asyncio.run(test_mpegts())