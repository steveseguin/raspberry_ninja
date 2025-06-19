#!/usr/bin/env python3
"""
Comprehensive test showing all recording capabilities
"""

import subprocess
import time
import glob
import os
import sys
from validate_media_file import validate_recording

def cleanup_files(prefix):
    """Clean up files with given prefix"""
    for f in glob.glob(f"{prefix}*.ts") + glob.glob(f"{prefix}*.mkv"):
        try:
            os.remove(f)
        except:
            pass

def test_single_stream_recording():
    """Test single stream recording"""
    print("\n" + "="*60)
    print("TEST 1: SINGLE STREAM RECORDING")
    print("="*60)
    
    cleanup_files("single_")
    results = []
    
    # Test different codecs
    codecs = [
        ("h264", "--h264", ".ts"),
        ("vp8", "--vp8", ".mkv"),
        ("vp9", "--vp9", ".mkv")
    ]
    
    for codec_name, codec_flag, expected_ext in codecs:
        print(f"\nTesting {codec_name.upper()} recording...")
        
        # Start publisher
        pub = subprocess.Popen([
            sys.executable, "publish.py",
            "--test", "--stream", f"single_{codec_name}",
            "--noaudio", codec_flag, "--password", "false"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        time.sleep(3)
        
        # Start recorder
        rec = subprocess.Popen([
            sys.executable, "publish.py",
            "--view", f"single_{codec_name}",
            "--record", f"single_{codec_name}",
            "--noaudio", "--password", "false"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print(f"  Recording for 8 seconds...")
        time.sleep(8)
        
        # Stop
        rec.terminate()
        pub.terminate()
        time.sleep(3)
        
        # Check files
        files = glob.glob(f"single_{codec_name}_*{expected_ext}")
        if files:
            f = files[0]
            size = os.path.getsize(f)
            valid = validate_recording(f, verbose=False)
            
            result = {
                'codec': codec_name.upper(),
                'file': f,
                'size': size,
                'valid': valid,
                'status': '✅' if valid else '❌'
            }
            results.append(result)
            
            print(f"  {result['status']} Created: {f} ({size:,} bytes)")
        else:
            print(f"  ❌ No file created")
            
    # Summary
    print("\nSingle Stream Recording Summary:")
    print("-" * 40)
    for r in results:
        print(f"{r['codec']:6} - {r['status']} {r['file']} ({r['size']:,} bytes)")
    
    return results

def test_multiple_stream_recording():
    """Test recording multiple streams simultaneously"""
    print("\n" + "="*60)
    print("TEST 2: MULTIPLE SIMULTANEOUS RECORDINGS")
    print("="*60)
    
    cleanup_files("multi_")
    
    # Start 3 publishers
    publishers = []
    streams = [
        ("stream1", "--h264"),
        ("stream2", "--vp8"),
        ("stream3", "--vp9")
    ]
    
    print("\nStarting 3 publishers...")
    for name, codec in streams:
        pub = subprocess.Popen([
            sys.executable, "publish.py",
            "--test", "--stream", f"multi_{name}",
            "--noaudio", codec, "--password", "false"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        publishers.append(pub)
        print(f"  Started {name} ({codec})")
        time.sleep(2)
    
    time.sleep(2)
    
    # Start 3 recorders
    recorders = []
    print("\nStarting 3 recorders...")
    for name, codec in streams:
        rec = subprocess.Popen([
            sys.executable, "publish.py",
            "--view", f"multi_{name}",
            "--record", f"multi_{name}",
            "--noaudio", "--password", "false"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        recorders.append(rec)
        print(f"  Recording {name}")
    
    print("\nRecording all streams for 10 seconds...")
    time.sleep(10)
    
    # Stop all
    print("\nStopping all processes...")
    for r in recorders:
        r.terminate()
    time.sleep(2)
    for p in publishers:
        p.terminate()
    time.sleep(2)
    
    # Check results
    files = glob.glob("multi_*.ts") + glob.glob("multi_*.mkv")
    
    print(f"\nCreated {len(files)} recordings:")
    for f in sorted(files):
        size = os.path.getsize(f)
        valid = validate_recording(f, verbose=False)
        status = '✅' if valid else '❌'
        print(f"  {status} {f} ({size:,} bytes)")
    
    return len(files)

def test_room_recording_attempt():
    """Attempt room recording and show what happens"""
    print("\n" + "="*60)
    print("TEST 3: ROOM RECORDING ATTEMPT")
    print("="*60)
    
    cleanup_files("room_")
    cleanup_files("testroom_")
    
    room = "testroom"
    
    # Start 2 publishers in a room
    print(f"\nStarting 2 publishers in room '{room}'...")
    
    pub1 = subprocess.Popen([
        sys.executable, "publish.py",
        "--test", "--room", room,
        "--stream", "alice",
        "--noaudio", "--h264", "--password", "false"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    time.sleep(3)
    
    pub2 = subprocess.Popen([
        sys.executable, "publish.py",
        "--test", "--room", room,
        "--stream", "bob",
        "--noaudio", "--vp8", "--password", "false"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    print("  Publishers started: alice (H264) and bob (VP8)")
    time.sleep(5)
    
    # Try room recording
    print(f"\nStarting room recorder...")
    rec = subprocess.Popen([
        sys.executable, "publish.py",
        "--room", room,
        "--record", "room",
        "--record-room",
        "--noaudio", "--password", "false"
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    # Monitor output
    print("\nMonitoring recorder output for 10 seconds...")
    start = time.time()
    key_events = []
    
    while time.time() - start < 10:
        line = rec.stdout.readline()
        if line:
            line = line.rstrip()
            if any(x in line for x in ["Room has", "Multi-Peer", "Will record", "Recording"]):
                key_events.append(line)
                print(f"  >>> {line}")
    
    # Stop
    print("\nStopping all processes...")
    rec.terminate()
    pub1.terminate()
    pub2.terminate()
    time.sleep(3)
    
    # Check files
    files = glob.glob("room_*.ts") + glob.glob("room_*.mkv") + glob.glob(f"{room}_*.ts") + glob.glob(f"{room}_*.mkv")
    
    print(f"\nRoom recording results:")
    print(f"  Key events seen: {len(key_events)}")
    print(f"  Files created: {len(files)}")
    
    if files:
        for f in files:
            size = os.path.getsize(f)
            print(f"    - {f} ({size:,} bytes)")
    
    return len(files)

def main():
    """Run all tests and show results"""
    print("COMPREHENSIVE RECORDING TEST SUITE")
    print("="*60)
    
    # Test 1: Single stream recording
    single_results = test_single_stream_recording()
    
    # Test 2: Multiple simultaneous recordings
    multi_count = test_multiple_stream_recording()
    
    # Test 3: Room recording
    room_count = test_room_recording_attempt()
    
    # Final summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    
    # Count all files
    all_files = glob.glob("single_*.ts") + glob.glob("single_*.mkv") + \
                glob.glob("multi_*.ts") + glob.glob("multi_*.mkv") + \
                glob.glob("room_*.ts") + glob.glob("room_*.mkv") + \
                glob.glob("testroom_*.ts") + glob.glob("testroom_*.mkv")
    
    print(f"\nTotal files created: {len(all_files)}")
    print(f"  Single stream recordings: {len(single_results)} codecs tested")
    print(f"  Multiple stream recordings: {multi_count} files")
    print(f"  Room recordings: {room_count} files")
    
    # List all files with sizes
    if all_files:
        print(f"\nAll recording files:")
        total_size = 0
        for f in sorted(all_files):
            if os.path.exists(f):
                size = os.path.getsize(f)
                total_size += size
                print(f"  {f:40} {size:10,} bytes")
        
        print(f"\nTotal size: {total_size:,} bytes ({total_size/1024/1024:.2f} MB)")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    main()