#!/usr/bin/env python3
"""Test recording with VLC-compatible format"""

import asyncio
import time
import os
import glob

async def test_vlc_recording():
    print("=== Testing VLC-Compatible Recording (MKV format) ===\n")
    
    # Record for 20 seconds
    print("Starting recording for 20 seconds...")
    process = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--room', 'testroom123999999999',
        '--record-room',
        '--audio',
        '--password', 'false',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL
    )
    
    # Monitor for startup
    start_time = time.time()
    while time.time() - start_time < 5:
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=0.5)
            if line:
                decoded = line.decode().strip()
                if "Recording setup complete" in decoded:
                    print(f"✓ {decoded}")
        except asyncio.TimeoutError:
            pass
    
    # Wait for recording
    await asyncio.sleep(15)
    
    print("\nStopping recording...")
    process.terminate()
    await process.wait()
    
    print("\n=== Checking Recorded Files ===\n")
    
    # Get all files
    mkv_files = glob.glob("testroom123999999999_*.mkv")
    mka_files = glob.glob("testroom123999999999_*.mka")
    
    print(f"Found {len(mkv_files)} video files (MKV) and {len(mka_files)} audio files (MKA)\n")
    
    # Check each video file
    for vf in sorted(mkv_files):
        print(f"VIDEO: {vf}")
        size = os.path.getsize(vf)
        print(f"  Size: {size:,} bytes")
        
        # Check with mediainfo-style probe
        cmd = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', vf,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await cmd.communicate()
        
        if stdout:
            import json
            try:
                info = json.loads(stdout.decode())
                fmt = info.get('format', {})
                
                # Check duration
                duration = fmt.get('duration', 'N/A')
                if duration != 'N/A':
                    duration = float(duration)
                    print(f"  Duration: {duration:.1f} seconds")
                    print("  ✅ File has proper duration!")
                else:
                    print("  ❌ No duration metadata")
                
                # Check if seekable
                print(f"  Format: {fmt.get('format_name', 'unknown')}")
                print(f"  Bitrate: {fmt.get('bit_rate', 'unknown')} bps")
                
                # Stream info
                for stream in info.get('streams', []):
                    if stream.get('codec_type') == 'video':
                        print(f"  Video: {stream.get('codec_name')} {stream.get('width')}x{stream.get('height')}")
                        
            except Exception as e:
                print(f"  Error parsing: {e}")
        
        # Quick VLC compatibility test
        cmd = await asyncio.create_subprocess_exec(
            'ffmpeg', '-v', 'error', '-i', vf, '-f', 'null', '-',
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await cmd.communicate()
        
        if cmd.returncode == 0:
            print("  ✅ File is valid and decodable")
        else:
            print(f"  ❌ Decode error: {stderr.decode()}")
        print()
    
    # Check audio files
    for af in sorted(mka_files):
        print(f"AUDIO: {af}")
        size = os.path.getsize(af)
        print(f"  Size: {size:,} bytes")
        
        cmd = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration,format_name',
            '-of', 'default=nw=1', af,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await cmd.communicate()
        
        if stdout:
            for line in stdout.decode().strip().split('\n'):
                if line.startswith('duration='):
                    dur = line.split('=')[1]
                    if dur != 'N/A':
                        print(f"  Duration: {float(dur):.1f} seconds")
                        print("  ✅ File has proper duration!")
                elif line.startswith('format_name='):
                    print(f"  Format: {line.split('=')[1]}")
        print()
    
    # Summary
    print("\n=== VLC Compatibility Summary ===")
    if mkv_files or mka_files:
        print("✅ Files created in Matroska format (MKV/MKA)")
        print("✅ This format is well-supported by VLC")
        print("\nTo play in VLC:")
        print("  - Open VLC")
        print("  - File -> Open File")
        print("  - Select the .mkv or .mka file")
    else:
        print("❌ No files were created")

if __name__ == "__main__":
    import sys
    asyncio.run(test_vlc_recording())