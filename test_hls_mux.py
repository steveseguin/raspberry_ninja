#!/usr/bin/env python3
"""Test HLS muxing by checking segment contents"""
import os
import glob
import subprocess
import json

def check_segment(filename):
    """Check what streams are in a segment file"""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', filename],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            streams = data.get('streams', [])
            types = [s.get('codec_type') for s in streams]
            codecs = [s.get('codec_name') for s in streams]
            return types, codecs
    except:
        pass
    return [], []

# Find all segments for the test room
pattern = "asdfasfsdfgasdf_*.ts"
files = sorted(glob.glob(pattern))

print(f"Found {len(files)} segment files")
print("\nChecking segment contents:")
print("-" * 60)

# Group by timestamp
timestamps = {}
for f in files:
    # Extract timestamp from filename
    parts = f.split('_')
    if len(parts) >= 3:
        timestamp = parts[2]
        if timestamp not in timestamps:
            timestamps[timestamp] = []
        timestamps[timestamp].append(f)

# Check each timestamp group
for ts, ts_files in sorted(timestamps.items())[-3:]:  # Last 3 timestamps
    print(f"\nTimestamp {ts}:")
    for f in sorted(ts_files)[:5]:  # First 5 segments
        types, codecs = check_segment(f)
        size = os.path.getsize(f)
        if types:
            stream_info = ", ".join([f"{t}:{c}" for t, c in zip(types, codecs)])
            status = "✓ MUXED" if len(types) == 2 else "✗ SINGLE"
        else:
            stream_info = "EMPTY"
            status = "✗ EMPTY"
        print(f"  {os.path.basename(f):40} {size:8} bytes  {status}  [{stream_info}]")