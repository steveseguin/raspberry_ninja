#!/usr/bin/env python3
"""Test actual playback duration and content"""

import asyncio
import glob
import os

async def test_playback():
    """Test if files actually contain playable content"""
    
    print("=== Testing Actual Playback ===\n")
    
    # Get most recent files
    video_files = sorted(glob.glob("testroom123999999999_*[!_audio].webm"), 
                        key=os.path.getmtime, reverse=True)[:2]
    audio_files = sorted(glob.glob("testroom123999999999_*_audio.webm"), 
                        key=os.path.getmtime, reverse=True)[:2]
    
    # Test video files by extracting frames
    print("VIDEO PLAYBACK TEST:")
    for vf in video_files:
        size = os.path.getsize(vf)
        print(f"\n📹 Testing {vf} ({size:,} bytes)")
        
        # Count frames
        cmd = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-count_packets', '-show_entries', 'stream=nb_read_packets',
            '-of', 'csv=p=0', vf,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await cmd.communicate()
        
        try:
            frame_count = int(stdout.decode().strip())
            print(f"   Frame count: {frame_count}")
        except:
            frame_count = 0
            print("   Could not count frames")
        
        # Extract some frames
        for i in [1, 10, 50]:
            output = f'frame_{i}.jpg'
            cmd = await asyncio.create_subprocess_exec(
                'ffmpeg', '-y', '-i', vf, '-vf', f'select=eq(n\\,{i})',
                '-vframes', '1', output,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await cmd.communicate()
            
            if os.path.exists(output) and os.path.getsize(output) > 0:
                print(f"   ✅ Frame {i} extracted successfully")
                os.remove(output)
            else:
                if i <= frame_count:
                    print(f"   ❌ Failed to extract frame {i}")
        
        # Try to play for actual duration
        cmd = await asyncio.create_subprocess_exec(
            'ffmpeg', '-i', vf, '-f', 'null', '-',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await cmd.communicate()
        
        # Parse actual duration from ffmpeg output
        stderr_text = stderr.decode()
        if 'time=' in stderr_text:
            import re
            time_match = re.search(r'time=(\d{2}:\d{2}:\d{2}\.\d{2})', stderr_text)
            if time_match:
                time_str = time_match.group(1)
                h, m, s = time_str.split(':')
                duration = int(h) * 3600 + int(m) * 60 + float(s)
                print(f"   Actual playback duration: {duration:.1f} seconds")
                
                if duration > 0:
                    print(f"   ✅ Video contains {duration:.1f}s of playable content")
                else:
                    print("   ⚠️  Video has no duration")
    
    # Test audio files
    print("\n\nAUDIO PLAYBACK TEST:")
    for af in audio_files:
        size = os.path.getsize(af)
        print(f"\n🎵 Testing {af} ({size:,} bytes)")
        
        # Get audio stats
        cmd = await asyncio.create_subprocess_exec(
            'ffmpeg', '-i', af, '-af', 'astats', '-f', 'null', '-',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await cmd.communicate()
        
        stderr_text = stderr.decode()
        
        # Parse duration
        if 'time=' in stderr_text:
            import re
            time_match = re.search(r'time=(\d{2}:\d{2}:\d{2}\.\d{2})', stderr_text)
            if time_match:
                time_str = time_match.group(1)
                h, m, s = time_str.split(':')
                duration = int(h) * 3600 + int(m) * 60 + float(s)
                print(f"   Actual playback duration: {duration:.1f} seconds")
                
                if duration > 0:
                    print(f"   ✅ Audio contains {duration:.1f}s of playable content")
                else:
                    print("   ⚠️  Audio has no duration")
        
        # Check if audio has actual sound (not silence)
        if 'RMS level dB' in stderr_text:
            print("   ✅ Audio contains actual sound (not silence)")
    
    # Test if files can be opened by media players
    print("\n\nCOMPATIBILITY TEST:")
    test_video = video_files[0] if video_files else None
    test_audio = audio_files[0] if audio_files else None
    
    if test_video:
        # Convert to MP4 for compatibility test
        output = 'test_compat_video.mp4'
        cmd = await asyncio.create_subprocess_exec(
            'ffmpeg', '-y', '-i', test_video, '-c:v', 'libx264', 
            '-preset', 'fast', '-crf', '23', output,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await cmd.communicate()
        
        if os.path.exists(output) and os.path.getsize(output) > 0:
            print("✅ Video can be converted to MP4 (compatible with all players)")
            os.remove(output)
        else:
            print("❌ Video conversion to MP4 failed")
    
    if test_audio:
        # Convert to MP3 for compatibility test
        output = 'test_compat_audio.mp3'
        cmd = await asyncio.create_subprocess_exec(
            'ffmpeg', '-y', '-i', test_audio, '-c:a', 'libmp3lame',
            '-b:a', '192k', output,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await cmd.communicate()
        
        if os.path.exists(output) and os.path.getsize(output) > 0:
            print("✅ Audio can be converted to MP3 (compatible with all players)")
            os.remove(output)
        else:
            print("❌ Audio conversion to MP3 failed")

if __name__ == "__main__":
    asyncio.run(test_playback())