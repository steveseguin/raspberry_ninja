#!/usr/bin/env python3
"""
Combine async audio and video recordings with proper timestamp-based synchronization
"""

import asyncio
import os
import sys
import json
from pathlib import Path


VIDEO_EXTENSIONS = {'.ts', '.webm', '.mkv'}
AUDIO_EXTENSIONS = {'.webm', '.wav', '.ts', '.mka'}


def recording_identity(filepath, audio=False):
    """Return a timestamp-independent recording identity for a generated filename."""
    path = Path(filepath)
    stem = path.stem
    if audio:
        if not stem.endswith('_audio') or path.suffix.lower() not in AUDIO_EXTENSIONS:
            return None
        stem = stem[:-len('_audio')]
    elif stem.endswith('_audio') or path.suffix.lower() not in VIDEO_EXTENSIONS:
        return None

    parts = stem.split('_')
    timestamp_index = None
    for index in range(len(parts) - 1, -1, -1):
        try:
            int(parts[index])
        except ValueError:
            continue
        timestamp_index = index
        break

    if timestamp_index is None:
        return None
    timestamp = int(parts[timestamp_index])
    identity_parts = parts[:timestamp_index] + parts[timestamp_index + 1:]
    identity = '_'.join(identity_parts)
    if not identity:
        return None
    return identity, timestamp


def discover_recording_pairs(directory='.', tolerance_seconds=5):
    """Find current and legacy video/audio recording pairs in a directory."""
    directory = Path(directory)
    videos = []
    audio_files = []
    for path in directory.iterdir():
        if not path.is_file() or path.name.startswith('combined_'):
            continue
        video_info = recording_identity(path, audio=False)
        if video_info:
            videos.append((path, *video_info))
        audio_info = recording_identity(path, audio=True)
        if audio_info:
            audio_files.append((path, *audio_info))

    pairs = []
    used_audio = set()
    for video_path, video_identity, video_timestamp in sorted(videos):
        candidates = [
            (abs(audio_timestamp - video_timestamp), audio_path)
            for audio_path, audio_identity, audio_timestamp in audio_files
            if audio_path not in used_audio
            and audio_identity == video_identity
            and abs(audio_timestamp - video_timestamp) <= tolerance_seconds
        ]
        if not candidates:
            continue
        _, audio_path = min(candidates, key=lambda candidate: (candidate[0], str(candidate[1])))
        used_audio.add(audio_path)
        pairs.append((video_path, audio_path))
    return pairs

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

async def main(directory='.'):
    """Find and combine matching audio/video pairs"""
    print("=== Combine Audio/Video Recordings (v2 - Timestamp-based sync) ===\n")

    pairs = discover_recording_pairs(directory)
    if not pairs:
        print("No files to combine!")
        return 0

    print(f"Found {len(pairs)} matching audio/video pair(s)\n")

    combined_count = 0
    directory = Path(directory)
    for video_file, audio_file in pairs:
        output_file = directory / f"combined_{video_file.stem}.mp4"
        if output_file.exists():
            print(f"Skipping {output_file} - already exists")
            continue
        success = await combine_files(video_file, audio_file, output_file)
        if success:
            combined_count += 1

    print(f"\n=== Summary ===")
    print(f"Combined {combined_count} file pairs")

    # List combined files
    combined_files = sorted(directory.glob("combined_*.mp4"))
    if combined_files:
        print("\nCombined files:")
        for cf in combined_files:
            size = os.path.getsize(cf)
            print(f"  {cf} ({size:,} bytes)")
    return combined_count

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
