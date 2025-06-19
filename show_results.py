#!/usr/bin/env python3
"""
Show recording test results
"""

import glob
import os
from validate_media_file import MediaFileValidator

print("="*60)
print("RECORDING TEST RESULTS")
print("="*60)

# Get all recording files
all_files = []
patterns = ["*.ts", "*.mkv"]
for pattern in patterns:
    files = glob.glob(pattern)
    # Exclude scripts
    files = [f for f in files if not f.endswith('.py')]
    all_files.extend(files)

# Remove duplicates and sort
all_files = sorted(list(set(all_files)))

if not all_files:
    print("\nNo recording files found")
else:
    print(f"\nFound {len(all_files)} recording files:\n")
    
    # Group by test type
    single_stream = [f for f in all_files if f.startswith('single_')]
    multi_stream = [f for f in all_files if f.startswith('multi_')]
    demo_files = [f for f in all_files if f.startswith('demo_')]
    room_files = [f for f in all_files if 'room' in f.lower()]
    other_files = [f for f in all_files if f not in single_stream + multi_stream + demo_files + room_files]
    
    validator = MediaFileValidator()
    
    # Single stream recordings
    if single_stream:
        print("SINGLE STREAM RECORDINGS:")
        print("-" * 40)
        for f in sorted(single_stream):
            size = os.path.getsize(f)
            is_valid, info = validator.validate_file(f, timeout=5)
            
            print(f"\n{f}")
            print(f"  Size: {size:,} bytes ({size/1024/1024:.2f} MB)")
            print(f"  Valid: {'✅ YES' if is_valid else '❌ NO'}")
            
            if is_valid:
                print(f"  Format: {info.get('format', 'unknown')}")
                print(f"  Frames: {info.get('frames_decoded', 0)}")
                
                # Identify codec
                if 'h264' in f:
                    print(f"  Codec: H.264")
                elif 'vp8' in f:
                    print(f"  Codec: VP8")
                elif 'vp9' in f:
                    print(f"  Codec: VP9")
    
    # Multi stream recordings
    if multi_stream:
        print("\n\nMULTIPLE STREAM RECORDINGS:")
        print("-" * 40)
        for f in sorted(multi_stream):
            size = os.path.getsize(f)
            is_valid, info = validator.validate_file(f, timeout=5)
            
            print(f"\n{f}")
            print(f"  Size: {size:,} bytes ({size/1024/1024:.2f} MB)")
            print(f"  Valid: {'✅ YES' if is_valid else '❌ NO'}")
            
            if is_valid:
                print(f"  Format: {info.get('format', 'unknown')}")
                print(f"  Frames: {info.get('frames_decoded', 0)}")
                
                # Identify stream
                if 'stream1' in f:
                    print(f"  Stream: stream1 (H.264)")
                elif 'stream2' in f:
                    print(f"  Stream: stream2 (VP8)")
                elif 'stream3' in f:
                    print(f"  Stream: stream3 (VP9)")
    
    # Room recordings
    if room_files:
        print("\n\nROOM RECORDINGS:")
        print("-" * 40)
        for f in sorted(room_files):
            size = os.path.getsize(f)
            is_valid, info = validator.validate_file(f, timeout=5)
            
            print(f"\n{f}")
            print(f"  Size: {size:,} bytes ({size/1024/1024:.2f} MB)")
            print(f"  Valid: {'✅ YES' if is_valid else '❌ NO'}")
            
            if is_valid:
                print(f"  Format: {info.get('format', 'unknown')}")
                print(f"  Frames: {info.get('frames_decoded', 0)}")
    
    # Summary
    print("\n\nSUMMARY:")
    print("="*60)
    
    total_size = sum(os.path.getsize(f) for f in all_files)
    valid_count = 0
    
    for f in all_files:
        is_valid, _ = validator.validate_file(f, timeout=5)
        if is_valid:
            valid_count += 1
    
    print(f"Total files: {len(all_files)}")
    print(f"Valid files: {valid_count}")
    print(f"Invalid files: {len(all_files) - valid_count}")
    print(f"Total size: {total_size:,} bytes ({total_size/1024/1024:.2f} MB)")
    
    print("\nBy codec:")
    h264_files = [f for f in all_files if f.endswith('.ts')]
    vp8_files = [f for f in all_files if f.endswith('.mkv') and ('vp8' in f or 'stream2' in f)]
    vp9_files = [f for f in all_files if f.endswith('.mkv') and ('vp9' in f or 'stream3' in f)]
    
    print(f"  H.264 (.ts): {len(h264_files)} files")
    print(f"  VP8 (.mkv): {len(vp8_files)} files")
    print(f"  VP9 (.mkv): {len(vp9_files)} files")
    
    print("\nBy test type:")
    print(f"  Single stream: {len(single_stream)} files")
    print(f"  Multi stream: {len(multi_stream)} files")
    print(f"  Room recording: {len(room_files)} files")
    
    # Check room recording status
    if len(room_files) == 0:
        print("\n⚠️  Note: No room recording files found.")
        print("   Room recording requires multiple streams in a room.")
        print("   The multi-peer client needs WebSocket message loop fixes.")

print("\n" + "="*60)