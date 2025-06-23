#!/usr/bin/env python3
import os
import time

# Check latest HLS files
m3u8_file = "asdfasfsdfgasdf_YAPCDUE808d64_1750667561.m3u8"
if os.path.exists(m3u8_file):
    print(f"✓ M3U8 file exists: {m3u8_file}")
    print(f"  Size: {os.path.getsize(m3u8_file)} bytes")
    print(f"  Modified: {time.ctime(os.path.getmtime(m3u8_file))}")
    
    # Read content
    with open(m3u8_file, 'r') as f:
        content = f.read()
    
    # Count segments
    segments = [line for line in content.split('\n') if line.endswith('.ts')]
    print(f"  Segments: {len(segments)}")
    
    # Check each segment
    print("\nSegment status:")
    for seg in segments[:5]:  # Check first 5
        if os.path.exists(seg):
            size = os.path.getsize(seg)
            print(f"  ✓ {seg}: {size:,} bytes")
        else:
            print(f"  ✗ {seg}: NOT FOUND")
            
    # Check for ENDLIST
    if '#EXT-X-ENDLIST' in content:
        print("\n✓ Stream is complete (has ENDLIST)")
    else:
        print("\n⚠ Stream is live (no ENDLIST)")
else:
    print(f"✗ M3U8 file not found: {m3u8_file}")

# Test with ffprobe
print("\nTesting with ffprobe:")
import subprocess
try:
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_format', m3u8_file], 
                          capture_output=True, text=True)
    if result.returncode == 0:
        print("✓ ffprobe can read the playlist")
    else:
        print(f"✗ ffprobe error: {result.stderr}")
except Exception as e:
    print(f"✗ ffprobe not available: {e}")