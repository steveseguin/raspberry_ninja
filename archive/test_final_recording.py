#!/usr/bin/env python3
"""Final test of recording with proper playback"""

import asyncio
import sys
import time
import os
import glob
import json

async def test_final():
    print("=== Final Recording Test ===\n")
    
    # Record for 30 seconds
    print("Recording for 30 seconds...")
    process = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--room', 'testroom123999999999',
        '--record-room',
        '--audio',
        '--password', 'false',
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    
    await asyncio.sleep(30)
    
    print("Stopping recording...")
    process.terminate()
    await process.wait()
    
    print("\n=== Testing Recorded Files ===\n")
    
    # Get all files
    all_files = glob.glob("testroom123999999999_*.webm")
    video_files = [f for f in all_files if "_audio." not in f]
    audio_files = [f for f in all_files if "_audio." in f]
    
    print(f"Found {len(video_files)} video and {len(audio_files)} audio files\n")
    
    # Test video files
    for vf in sorted(video_files):
        print(f"VIDEO: {vf}")
        size = os.path.getsize(vf)
        print(f"  Size: {size:,} bytes")
        
        if size > 0:
            # Test with ffmpeg
            print("  Testing with ffmpeg...")
            cmd = await asyncio.create_subprocess_exec(
                'ffmpeg', '-v', 'error', '-i', vf, '-f', 'null', '-',
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await cmd.communicate()
            
            if cmd.returncode == 0:
                print("    ✅ Playable with ffmpeg")
            else:
                print(f"    ❌ Error: {stderr.decode()[:100]}")
            
            # Test with gst-launch
            print("  Testing with gst-launch...")
            cmd = await asyncio.create_subprocess_exec(
                'gst-launch-1.0', 'filesrc', f'location={vf}', '!',
                'decodebin', '!', 'fakesink', 'sync=false',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            await cmd.communicate()
            
            if cmd.returncode == 0:
                print("    ✅ Playable with gst-launch")
            else:
                print("    ❌ Failed with gst-launch")
                
            # Get codec info
            cmd = await asyncio.create_subprocess_exec(
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_streams', '-select_streams', 'v:0', vf,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await cmd.communicate()
            
            if stdout:
                try:
                    info = json.loads(stdout.decode())
                    stream = info['streams'][0] if info.get('streams') else {}
                    print(f"  Codec: {stream.get('codec_name', 'unknown')}")
                    print(f"  Resolution: {stream.get('width', '?')}x{stream.get('height', '?')}")
                except:
                    pass
        else:
            print("  ❌ Empty file")
        print()
    
    # Test audio files
    for af in sorted(audio_files):
        print(f"AUDIO: {af}")
        size = os.path.getsize(af)
        print(f"  Size: {size:,} bytes")
        
        if size > 0:
            # Test with ffmpeg
            print("  Testing with ffmpeg...")
            cmd = await asyncio.create_subprocess_exec(
                'ffmpeg', '-v', 'error', '-i', af, '-f', 'null', '-',
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await cmd.communicate()
            
            if cmd.returncode == 0:
                print("    ✅ Playable with ffmpeg")
            else:
                print(f"    ❌ Error: {stderr.decode()[:100]}")
                
            # Get audio info
            cmd = await asyncio.create_subprocess_exec(
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_streams', '-select_streams', 'a:0', af,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await cmd.communicate()
            
            if stdout:
                try:
                    info = json.loads(stdout.decode())
                    stream = info['streams'][0] if info.get('streams') else {}
                    print(f"  Codec: {stream.get('codec_name', 'unknown')}")
                    print(f"  Sample rate: {stream.get('sample_rate', '?')} Hz")
                except:
                    pass
        else:
            print("  ❌ Empty file")
        print()
    
    # Create metadata file
    if video_files or audio_files:
        print("\n=== Creating Metadata File ===")
        metadata = {
            "recording_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "room": "testroom123999999999",
            "streams": {}
        }
        
        # Match video and audio files by stream ID
        for vf in video_files:
            # Extract stream ID from filename
            parts = os.path.basename(vf).split('_')
            if len(parts) >= 3:
                stream_id = parts[1]
                metadata["streams"][stream_id] = {
                    "video": vf,
                    "video_size": os.path.getsize(vf)
                }
        
        for af in audio_files:
            # Extract stream ID from filename
            parts = os.path.basename(af).split('_')
            if len(parts) >= 3:
                stream_id = parts[1]
                if stream_id in metadata["streams"]:
                    metadata["streams"][stream_id]["audio"] = af
                    metadata["streams"][stream_id]["audio_size"] = os.path.getsize(af)
                else:
                    metadata["streams"][stream_id] = {
                        "audio": af,
                        "audio_size": os.path.getsize(af)
                    }
        
        # Save metadata
        metadata_file = f"recording_metadata_{int(time.time())}.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"✅ Metadata saved to {metadata_file}")
        
        # Display metadata
        print("\nStream pairs:")
        for stream_id, files in metadata["streams"].items():
            print(f"  Stream {stream_id}:")
            if "video" in files:
                print(f"    Video: {files['video']} ({files['video_size']:,} bytes)")
            if "audio" in files:
                print(f"    Audio: {files['audio']} ({files['audio_size']:,} bytes)")

if __name__ == "__main__":
    asyncio.run(test_final())