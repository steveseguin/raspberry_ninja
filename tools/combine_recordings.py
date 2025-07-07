#!/usr/bin/env python3
"""
Combine async audio and video recordings with proper timestamp-based synchronization
"""

import asyncio
import glob
import os
import sys
import json
import subprocess
from pathlib import Path

async def get_stream_start_time(filepath):
    """Get the actual start time of the first frame/sample in a media file"""
    cmd = await asyncio.create_subprocess_exec(
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_entries', 'stream=start_time,start_pts,time_base,codec_type',
        filepath,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await cmd.communicate()
    
    if cmd.returncode == 0:
        try:
            data = json.loads(stdout.decode())
            streams = data.get('streams', [])
            
            # Find the first video or audio stream
            for stream in streams:
                codec_type = stream.get('codec_type')
                if codec_type in ['video', 'audio']:
                    # Get the start time in seconds
                    start_time = stream.get('start_time', '0')
                    return float(start_time)
        except Exception as e:
            print(f"  Warning: Could not parse start time: {e}")
    return 0.0

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
    """Combine video and audio with proper timestamp-based sync"""
    print(f"\nCombining:")
    print(f"  Video: {video_file}")
    print(f"  Audio: {audio_file}")
    print(f"  Output: {output_file}")
    
    # Get stream start times
    video_start = await get_stream_start_time(video_file)
    audio_start = await get_stream_start_time(audio_file)
    
    print(f"  Video start time: {video_start:.3f}s")
    print(f"  Audio start time: {audio_start:.3f}s")
    
    # Calculate the time difference
    time_diff = video_start - audio_start
    
    # Build ffmpeg command
    cmd = ['ffmpeg', '-y']
    
    # Input files
    cmd.extend(['-i', video_file, '-i', audio_file])
    
    # Always use precise sync based on stream timestamps
    if abs(time_diff) < 0.001:  # Less than 1ms difference
        print("  Strategy: Direct merge (streams already in sync)")
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-shortest'
        ])
    elif time_diff > 0:
        # Video starts later than audio - delay the audio
        delay_ms = int(time_diff * 1000)
        print(f"  Strategy: Delaying audio by {delay_ms}ms to sync with video")
        cmd.extend([
            '-filter_complex', f'[1:a]adelay={delay_ms}|{delay_ms}[delayed]',
            '-map', '0:v',
            '-map', '[delayed]',
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-shortest'
        ])
    else:
        # Audio starts later than video - delay the video or trim audio
        delay_ms = int(abs(time_diff) * 1000)
        print(f"  Strategy: Audio starts {delay_ms}ms after video")
        
        # For small delays, we can use setpts to delay video
        if delay_ms < 5000:  # Less than 5 seconds
            video_delay = abs(time_diff)
            print(f"  Delaying video by {video_delay:.3f}s")
            cmd.extend([
                '-filter_complex', 
                f'[0:v]setpts=PTS+{video_delay}/TB[delayed_video]',
                '-map', '[delayed_video]',
                '-map', '1:a',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-shortest'
            ])
        else:
            # For larger delays, trim the beginning of audio
            trim_start = abs(time_diff)
            print(f"  Trimming {trim_start:.3f}s from audio start")
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
                
                # Verify sync by checking if streams start at the same time
                output_start = await get_stream_start_time(output_file)
                print(f"  Output start time: {output_start:.3f}s")
                
                return True
            else:
                print(f"  ⚠️  Missing tracks - Video: {has_video}, Audio: {has_audio}")
        
        return True
    else:
        print(f"  ❌ Failed: {stderr.decode()[:200]}")
        return False

async def main():
    """Find and combine matching audio/video pairs"""
    print("=== Combine Audio/Video Recordings (v2 - Timestamp-based sync) ===\n")
    
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
            output_file = f"combined_v2_{stream_id}_{timestamp}.mp4"
            
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
    combined_files = glob.glob("combined_v2_*.mp4")
    if combined_files:
        print("\nCombined files:")
        for cf in sorted(combined_files):
            size = os.path.getsize(cf)
            print(f"  {cf} ({size:,} bytes)")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Allow specific file combination
        if len(sys.argv) == 4:
            asyncio.run(combine_files(sys.argv[1], sys.argv[2], sys.argv[3]))
        else:
            print("Usage: combine_recordings_v2.py [video_file audio_file output_file]")
    else:
        # Auto-combine all matching pairs
        asyncio.run(main())