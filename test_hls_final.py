#!/usr/bin/env python3
"""Final HLS test after state management fixes"""
import subprocess
import time
import os
import glob
import json

# Clean up old test files
old_files = glob.glob("asdfasfsdfgasdf_*_test_*.ts") + glob.glob("asdfasfsdfgasdf_*_test_*.m3u8")
for f in old_files:
    try:
        os.remove(f)
    except:
        pass

print("Starting HLS test with fixed state management...")
start_time = time.time()

# Start the process
proc = subprocess.Popen(
    ['python3', 'publish.py', '--record-room', '--hls', '--room', 'asdfasfsdfgasdf', '--debug', '--stream', 'test'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)

# Monitor output for 30 seconds
output_lines = []
key_lines = []
try:
    end_time = time.time() + 30
    while time.time() < end_time:
        if proc.poll() is not None:
            print(f"Process ended early with code: {proc.returncode}")
            break
        
        # Non-blocking read
        line = proc.stdout.readline()
        if line:
            line = line.rstrip()
            output_lines.append(line)
            
            # Check for key messages
            if any(word in line for word in ['Splitmuxsink state', 'New HLS segment', 'connected to HLS', 'HLS recording started']):
                key_lines.append(line)
                print(f"KEY: {line}")
                
except Exception as e:
    print(f"Error during monitoring: {e}")
finally:
    proc.terminate()
    proc.wait()

# Check for created files
ts_files = glob.glob("asdfasfsdfgasdf_*test_*.ts")
m3u8_files = glob.glob("asdfasfsdfgasdf_*test*.m3u8")

print(f"\n=== Results ===")
print(f"TS segments created: {len(ts_files)}")
print(f"M3U8 playlists created: {len(m3u8_files)}")

if ts_files:
    print("\nSegment files:")
    for f in sorted(ts_files)[-5:]:
        size = os.path.getsize(f)
        print(f"  {f}: {size:,} bytes")
        
    # Check content of first segment
    if len(ts_files) >= 1:
        first_seg = sorted(ts_files)[0]
        print(f"\nChecking first segment: {first_seg}")
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', first_seg],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                streams = data.get('streams', [])
                print(f"  Streams: {len(streams)}")
                for s in streams:
                    print(f"    - {s.get('codec_type')}: {s.get('codec_name')}")
            except:
                print("  Failed to parse ffprobe output")

if m3u8_files:
    print(f"\nChecking playlist: {m3u8_files[0]}")
    with open(m3u8_files[0], 'r') as f:
        content = f.read()
        segment_count = content.count('.ts')
        print(f"  Segments in playlist: {segment_count}")

print("\nKey events from log:")
for line in key_lines[-10:]:
    print(f"  {line}")