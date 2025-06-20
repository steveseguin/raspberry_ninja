#!/usr/bin/env python3
"""Validate that recorded files are actually playable"""

import asyncio
import glob
import os
import json

async def validate_media_files():
    """Test all recorded files for playability"""
    
    print("=== Media File Validation ===\n")
    
    # Find all recent recording files
    video_files = sorted(glob.glob("testroom123999999999_*[!_audio].webm"))[-4:]
    audio_files = sorted(glob.glob("testroom123999999999_*_audio.webm"))[-4:]
    
    if not video_files and not audio_files:
        print("No recording files found!")
        return
    
    # Test video files
    print("VIDEO FILES:")
    for vf in video_files:
        if not os.path.exists(vf):
            continue
            
        size = os.path.getsize(vf)
        print(f"\n📹 {vf} ({size:,} bytes)")
        
        # Get detailed info with ffprobe
        cmd = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'error', '-print_format', 'json',
            '-show_format', '-show_streams', vf,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await cmd.communicate()
        
        if cmd.returncode != 0:
            print(f"   ❌ ERROR: {stderr.decode()}")
            continue
            
        try:
            info = json.loads(stdout.decode())
            
            # Check format
            fmt = info.get('format', {})
            duration = float(fmt.get('duration', 0))
            bitrate = int(fmt.get('bit_rate', 0))
            
            print(f"   Format: {fmt.get('format_name', 'unknown')}")
            print(f"   Duration: {duration:.1f} seconds")
            print(f"   Bitrate: {bitrate:,} bps")
            
            # Check streams
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video':
                    print(f"   Video: {stream.get('codec_name')} {stream.get('width')}x{stream.get('height')} @ {stream.get('avg_frame_rate', 'unknown')} fps")
                    
            # Try to extract a frame to verify it's decodable
            frame_cmd = await asyncio.create_subprocess_exec(
                'ffmpeg', '-i', vf, '-vframes', '1', '-f', 'null', '-',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, frame_err = await frame_cmd.communicate()
            
            if frame_cmd.returncode == 0:
                print("   ✅ Video is decodable and playable")
            else:
                print("   ❌ Video decode test failed")
                
        except Exception as e:
            print(f"   ❌ Error parsing info: {e}")
    
    # Test audio files
    print("\n\nAUDIO FILES:")
    for af in audio_files:
        if not os.path.exists(af):
            continue
            
        size = os.path.getsize(af)
        print(f"\n🎵 {af} ({size:,} bytes)")
        
        # Get detailed info
        cmd = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'error', '-print_format', 'json',
            '-show_format', '-show_streams', af,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await cmd.communicate()
        
        if cmd.returncode != 0:
            print(f"   ❌ ERROR: {stderr.decode()}")
            continue
            
        try:
            info = json.loads(stdout.decode())
            
            # Check format
            fmt = info.get('format', {})
            duration = float(fmt.get('duration', 0))
            bitrate = int(fmt.get('bit_rate', 0))
            
            print(f"   Format: {fmt.get('format_name', 'unknown')}")
            print(f"   Duration: {duration:.1f} seconds")
            print(f"   Bitrate: {bitrate:,} bps")
            
            # Check streams
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'audio':
                    print(f"   Audio: {stream.get('codec_name')} @ {stream.get('sample_rate')} Hz, {stream.get('channels')} channels")
                    
            # Try to decode audio to verify it's playable
            audio_cmd = await asyncio.create_subprocess_exec(
                'ffmpeg', '-i', af, '-f', 'null', '-',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, audio_err = await audio_cmd.communicate()
            
            if audio_cmd.returncode == 0:
                print("   ✅ Audio is decodable and playable")
            else:
                print("   ❌ Audio decode test failed")
                
        except Exception as e:
            print(f"   ❌ Error parsing info: {e}")
    
    # Test muxing audio and video together
    print("\n\nMUXING TEST:")
    if video_files and audio_files:
        # Find matching pairs
        for vf in video_files[:1]:  # Just test one
            base = vf.replace('.webm', '')
            # Try to find matching audio
            matching_audio = None
            for af in audio_files:
                if base.replace(vf.split('_')[-1], '') in af:
                    matching_audio = af
                    break
                    
            if matching_audio:
                output = 'test_muxed_output.mp4'
                print(f"\nTesting mux of:")
                print(f"  Video: {vf}")
                print(f"  Audio: {matching_audio}")
                print(f"  Output: {output}")
                
                # Try to mux them
                mux_cmd = await asyncio.create_subprocess_exec(
                    'ffmpeg', '-y', '-i', vf, '-i', matching_audio,
                    '-c:v', 'copy', '-c:a', 'aac', output,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                _, mux_err = await mux_cmd.communicate()
                
                if mux_cmd.returncode == 0 and os.path.exists(output):
                    size = os.path.getsize(output)
                    print(f"  ✅ Successfully muxed! Output size: {size:,} bytes")
                    
                    # Verify muxed file
                    verify_cmd = await asyncio.create_subprocess_exec(
                        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                        '-show_entries', 'stream=codec_type', '-of', 'default=nw=1:nk=1',
                        output,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    v_out, _ = await verify_cmd.communicate()
                    
                    verify_cmd = await asyncio.create_subprocess_exec(
                        'ffprobe', '-v', 'error', '-select_streams', 'a:0',
                        '-show_entries', 'stream=codec_type', '-of', 'default=nw=1:nk=1',
                        output,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    a_out, _ = await verify_cmd.communicate()
                    
                    has_video = b'video' in v_out
                    has_audio = b'audio' in a_out
                    
                    print(f"  Muxed file has video: {has_video}")
                    print(f"  Muxed file has audio: {has_audio}")
                    
                    if has_video and has_audio:
                        print("  ✅ Muxed file is valid with both audio and video!")
                    
                    # Clean up
                    os.remove(output)
                else:
                    print(f"  ❌ Muxing failed")

if __name__ == "__main__":
    asyncio.run(validate_media_files())