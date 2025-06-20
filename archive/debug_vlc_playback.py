#!/usr/bin/env python3
"""Debug why VLC cannot play the files"""

import subprocess
import glob
import os

def run_command(cmd):
    """Run command and return output"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout, result.stderr, result.returncode

def debug_files():
    print("=== VLC Playback Debug ===\n")
    
    # Get recent files
    video_files = sorted(glob.glob("testroom123999999999_*[!_audio].webm"), 
                        key=os.path.getmtime, reverse=True)[:1]
    audio_files = sorted(glob.glob("testroom123999999999_*_audio.webm"), 
                        key=os.path.getmtime, reverse=True)[:1]
    
    for vf in video_files:
        print(f"VIDEO FILE: {vf}")
        print(f"Size: {os.path.getsize(vf):,} bytes\n")
        
        # Check file structure
        print("1. Checking file structure:")
        stdout, stderr, _ = run_command(f"ffmpeg -v error -i {vf} -f null -")
        if stderr:
            print(f"   ERRORS: {stderr}")
        else:
            print("   No errors detected by ffmpeg")
        
        # Check container format
        print("\n2. Container analysis:")
        stdout, _, _ = run_command(f"ffprobe -v quiet -show_format {vf}")
        print(stdout)
        
        # Check codec details
        print("3. Codec details:")
        stdout, _, _ = run_command(f"ffprobe -v quiet -show_streams -select_streams v:0 {vf}")
        for line in stdout.split('\n'):
            if any(key in line for key in ['codec_name=', 'pix_fmt=', 'width=', 'height=', 'duration=']):
                print(f"   {line}")
        
        # Check for keyframes
        print("\n4. Checking keyframes:")
        stdout, _, _ = run_command(f'ffprobe -v quiet -select_streams v:0 -show_frames -show_entries frame=pict_type -of csv {vf} | head -20')
        keyframes = stdout.count('I')
        total_frames = len(stdout.strip().split('\n'))
        print(f"   First 20 frames: {keyframes} keyframes")
        
        # Try remuxing to fix
        print("\n5. Testing remux to fix issues:")
        output = vf.replace('.webm', '_fixed.webm')
        stdout, stderr, code = run_command(f'ffmpeg -y -i {vf} -c copy -fflags +genpts {output}')
        if code == 0:
            print(f"   ✅ Remuxed successfully to {output}")
            print(f"   New size: {os.path.getsize(output):,} bytes")
            
            # Test if remuxed file has duration
            stdout, _, _ = run_command(f"ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 {output}")
            duration = stdout.strip()
            if duration and duration != 'N/A':
                print(f"   Duration after remux: {duration} seconds")
            else:
                print("   Still no duration after remux")
                
            # Try converting to MP4
            mp4_output = vf.replace('.webm', '_vlc.mp4')
            print(f"\n6. Converting to MP4 for VLC:")
            stdout, stderr, code = run_command(f'ffmpeg -y -i {vf} -c:v libx264 -preset fast -crf 23 -c:a aac {mp4_output}')
            if code == 0:
                print(f"   ✅ Converted to MP4: {mp4_output}")
                print(f"   Size: {os.path.getsize(mp4_output):,} bytes")
            else:
                print(f"   ❌ Conversion failed: {stderr}")
        else:
            print(f"   ❌ Remux failed: {stderr}")
    
    for af in audio_files:
        print(f"\n\nAUDIO FILE: {af}")
        print(f"Size: {os.path.getsize(af):,} bytes\n")
        
        # Check audio stream
        print("1. Audio stream details:")
        stdout, _, _ = run_command(f"ffprobe -v quiet -show_streams -select_streams a:0 {af}")
        for line in stdout.split('\n'):
            if any(key in line for key in ['codec_name=', 'sample_rate=', 'channels=', 'duration=']):
                print(f"   {line}")
        
        # Try converting to MP3
        mp3_output = af.replace('.webm', '_vlc.mp3')
        print(f"\n2. Converting to MP3 for VLC:")
        stdout, stderr, code = run_command(f'ffmpeg -y -i {af} -c:a libmp3lame -b:a 192k {mp3_output}')
        if code == 0:
            print(f"   ✅ Converted to MP3: {mp3_output}")
            print(f"   Size: {os.path.getsize(mp3_output):,} bytes")
        else:
            print(f"   ❌ Conversion failed: {stderr}")
    
    print("\n\n=== Recommendations ===")
    print("1. The WebM files lack duration metadata (common for live streams)")
    print("2. Use the _fixed.webm files after remuxing")
    print("3. For best compatibility, use the .mp4/.mp3 converted files")
    print("4. The issue is likely due to missing timestamps in the WebM container")

if __name__ == "__main__":
    debug_files()