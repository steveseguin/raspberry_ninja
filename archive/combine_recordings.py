#!/usr/bin/env python3
"""
Combine async audio and video recordings intelligently
Handles different start times and durations
"""

import asyncio
import glob
import os
import sys
import json
import time
from pathlib import Path

async def get_file_info(filepath):
    """Get duration and codec info for a media file"""
    cmd = await asyncio.create_subprocess_exec(
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_format', '-show_streams', filepath,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await cmd.communicate()
    
    if cmd.returncode == 0:
        try:
            return json.loads(stdout.decode())
        except:
            pass
    return None

async def combine_files(video_file, audio_file, output_file):
    """Combine video and audio with smart sync handling"""
    print(f"\nCombining:")
    print(f"  Video: {video_file}")
    print(f"  Audio: {audio_file}")
    print(f"  Output: {output_file}")
    
    # Get file info
    video_info = await get_file_info(video_file)
    audio_info = await get_file_info(audio_file)
    
    if not video_info or not audio_info:
        print("  ❌ Failed to get file info")
        return False
    
    # Extract durations (WebM might not have duration, so we estimate)
    video_duration = None
    audio_duration = None
    
    if video_info.get('format', {}).get('duration'):
        video_duration = float(video_info['format']['duration'])
    else:
        # Estimate duration for WebM files
        size = os.path.getsize(video_file)
        # Rough estimate: ~50KB/s for low bitrate video
        video_duration = size / 50000
        print(f"  ⚠️  Video duration estimated: ~{video_duration:.1f}s")
    
    if audio_info.get('format', {}).get('duration'):
        audio_duration = float(audio_info['format']['duration'])
        print(f"  Audio duration: {audio_duration:.1f}s")
    
    # Determine sync strategy based on file timestamps
    video_mtime = os.path.getmtime(video_file)
    audio_mtime = os.path.getmtime(audio_file)
    time_diff = abs(video_mtime - audio_mtime)
    
    print(f"  File creation time difference: {time_diff:.1f}s")
    
    # Build ffmpeg command with sync handling
    cmd = ['ffmpeg', '-y']
    
    # Input files
    cmd.extend(['-i', video_file, '-i', audio_file])
    
    # Sync strategy
    if time_diff < 2.0:
        # Files created close together - simple merge
        print("  Strategy: Simple merge (files created within 2s)")
        cmd.extend([
            '-c:v', 'libx264',  # Re-encode VP8 to H.264 for MP4 compatibility
            '-preset', 'fast',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-shortest'  # Stop when shortest stream ends
        ])
    else:
        # Files have time difference - use complex filter for sync
        print("  Strategy: Complex sync (adjusting for time difference)")
        
        # Adjust audio delay based on file creation times
        if audio_mtime > video_mtime:
            # Audio started later
            delay_ms = int(time_diff * 1000)
            print(f"  Adding {delay_ms}ms delay to audio")
            cmd.extend([
                '-filter_complex', f'[1:a]adelay={delay_ms}|{delay_ms}[delayed]',
                '-map', '0:v',
                '-map', '[delayed]',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '192k'
            ])
        else:
            # Video started later - trim audio start
            trim_start = time_diff
            print(f"  Trimming {trim_start:.1f}s from audio start")
            cmd.extend([
                '-filter_complex', f'[1:a]atrim=start={trim_start}[trimmed]',
                '-map', '0:v',
                '-map', '[trimmed]',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '192k'
            ])
    
    # Output file
    cmd.append(output_file)
    
    # Execute
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    
    if process.returncode == 0:
        size = os.path.getsize(output_file)
        print(f"  ✅ Success! Output size: {size:,} bytes")
        
        # Verify output
        info = await get_file_info(output_file)
        if info:
            duration = info.get('format', {}).get('duration', 'unknown')
            streams = len(info.get('streams', []))
            print(f"  Duration: {duration}s, Streams: {streams}")
            
            # Check if both audio and video are present
            has_video = any(s.get('codec_type') == 'video' for s in info.get('streams', []))
            has_audio = any(s.get('codec_type') == 'audio' for s in info.get('streams', []))
            
            if has_video and has_audio:
                print("  ✅ Both video and audio tracks present")
                return True
            else:
                print(f"  ⚠️  Missing tracks - Video: {has_video}, Audio: {has_audio}")
        
        return True
    else:
        print(f"  ❌ Failed: {stderr.decode()[:200]}")
        return False

async def main():
    """Find and combine matching audio/video pairs"""
    print("=== Combine Audio/Video Recordings ===\n")
    
    # Find all video and audio files
    video_files = glob.glob("testroom123999999999_*[!_audio].webm")
    audio_files = glob.glob("testroom123999999999_*_audio.wav")
    
    if not video_files or not audio_files:
        print("No files to combine!")
        return
    
    print(f"Found {len(video_files)} video and {len(audio_files)} audio files\n")
    
    # Match files by stream ID
    combined_count = 0
    
    for video_file in sorted(video_files):
        # Extract stream ID from video filename
        parts = Path(video_file).stem.split('_')
        if len(parts) < 3:
            continue
            
        stream_id = parts[1]
        timestamp = parts[2]
        
        # Find matching audio file with same or close timestamp (within 2 seconds)
        matching_audio = None
        video_timestamp = int(timestamp)
        
        for audio_file in audio_files:
            # Extract audio timestamp
            if f"_{stream_id}_" in audio_file and "_audio.wav" in audio_file:
                audio_parts = Path(audio_file).stem.split('_')
                if len(audio_parts) >= 3:
                    try:
                        audio_timestamp = int(audio_parts[2])
                        # Match if timestamps are within 2 seconds
                        if abs(audio_timestamp - video_timestamp) <= 2:
                            matching_audio = audio_file
                            break
                    except ValueError:
                        continue
        
        if matching_audio:
            output_file = f"combined_{stream_id}_{timestamp}.mp4"
            
            if os.path.exists(output_file):
                print(f"Skipping {output_file} - already exists")
                continue
                
            success = await combine_files(video_file, matching_audio, output_file)
            if success:
                combined_count += 1
        else:
            print(f"No matching audio for {video_file}")
    
    print(f"\n=== Summary ===")
    print(f"Combined {combined_count} file pairs")
    
    # List combined files
    combined_files = glob.glob("combined_*.mp4")
    if combined_files:
        print("\nCombined files:")
        for cf in sorted(combined_files):
            size = os.path.getsize(cf)
            print(f"  {cf} ({size:,} bytes)")
            
        # Test playback of first combined file
        if combined_files:
            print(f"\nTesting playback of {combined_files[0]}...")
            cmd = await asyncio.create_subprocess_exec(
                'ffplay', '-v', 'quiet', '-autoexit', '-t', '5', combined_files[0],
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            try:
                await asyncio.wait_for(cmd.communicate(), timeout=10)
                print("✅ Playback test passed")
            except:
                print("⚠️  ffplay not available or playback failed")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Allow specific file combination
        if len(sys.argv) == 4:
            asyncio.run(combine_files(sys.argv[1], sys.argv[2], sys.argv[3]))
        else:
            print("Usage: combine_recordings.py [video_file audio_file output_file]")
    else:
        # Auto-combine all matching pairs
        asyncio.run(main())