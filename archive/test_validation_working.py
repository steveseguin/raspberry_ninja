#!/usr/bin/env python3
"""
Test that confirms recording and validation work with --view mode
"""

import subprocess
import sys
import time
import os
import glob
from validate_media_file import MediaFileValidator, validate_recording


def test_view_mode_recording():
    """Test recording with --view mode and validation"""
    print("Recording and Validation Test (View Mode)")
    print("="*50)
    
    # Clean up
    for f in glob.glob("view_test_*.ts") + glob.glob("view_test_*.mkv"):
        os.remove(f)
        
    room = f"viewtest{int(time.time())}"
    validator = MediaFileValidator()
    
    # Test different codecs
    codecs = [
        ("h264", "ts"),
        ("vp8", "mkv")
    ]
    
    all_passed = True
    
    for codec, expected_ext in codecs:
        print(f"\n--- Testing {codec.upper()} ---")
        
        # Start publisher
        print(f"1. Starting {codec} publisher...")
        pub = subprocess.Popen([
            sys.executable, "publish.py",
            "--test", "--room", room,
            "--stream", f"test_{codec}",
            "--noaudio", f"--{codec}"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        time.sleep(3)
        
        # Start recorder
        print("2. Recording for 8 seconds...")
        rec = subprocess.Popen([
            sys.executable, "publish.py",
            "--room", room,
            "--view", f"test_{codec}",
            "--record", f"view_test_{codec}",
            "--noaudio"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        time.sleep(8)
        
        # Stop
        rec.terminate()
        rec.wait(timeout=5)
        pub.terminate()
        pub.wait(timeout=5)
        time.sleep(2)
        
        # Find recordings
        recordings = glob.glob(f"view_test_{codec}_*.{expected_ext}")
        
        if not recordings:
            print(f"   ❌ No {expected_ext} recordings found!")
            all_passed = False
            continue
            
        # Validate
        print("3. Validating recording...")
        for recording in recordings:
            is_valid, info = validator.validate_file(recording, timeout=5)
            
            if is_valid:
                print(f"   ✅ {recording}")
                print(f"      Size: {os.path.getsize(recording):,} bytes")
                print(f"      Frames: {info.get('frames_decoded', 0)}")
                print(f"      Format: {info.get('format', 'unknown')}")
                
                # Additional validation
                if info.get('frames_decoded', 0) < 10:
                    print(f"      ⚠️  Warning: Very few frames decoded")
                    
                if expected_ext != info.get('format', ''):
                    print(f"      ⚠️  Warning: Expected {expected_ext}, got {info.get('format', 'unknown')}")
            else:
                print(f"   ❌ {recording} - INVALID")
                print(f"      Error: {info.get('error', 'Unknown')}")
                all_passed = False
                
        # Clean up recordings
        for f in recordings:
            os.remove(f)
            
    print("\n" + "="*50)
    if all_passed:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
        
    return all_passed


def test_invalid_detection():
    """Test that validator correctly identifies invalid files"""
    print("\n\nInvalid File Detection Test")
    print("="*50)
    
    # Create various invalid files
    test_files = [
        ("empty.ts", b""),
        ("text.ts", b"This is just text, not video"),
        ("random.mkv", os.urandom(1000)),
        ("partial.ts", b"\x47" * 188)  # TS sync byte but no content
    ]
    
    validator = MediaFileValidator()
    all_correct = True
    
    for filename, content in test_files:
        print(f"\nTesting {filename}...")
        
        # Create file
        with open(filename, "wb") as f:
            f.write(content)
            
        # Validate
        is_valid, info = validator.validate_file(filename, timeout=2)
        
        if not is_valid:
            print(f"   ✅ Correctly identified as invalid")
            print(f"      Error: {info.get('error', 'Unknown')[:50]}...")
        else:
            print(f"   ❌ ERROR: File incorrectly marked as valid!")
            all_correct = False
            
        # Clean up
        os.remove(filename)
        
    return all_correct


def main():
    print("Media Validation Test Suite")
    print("Testing recording and validation functionality\n")
    
    # Test 1: View mode recording with validation
    test1_passed = test_view_mode_recording()
    
    # Test 2: Invalid file detection
    test2_passed = test_invalid_detection()
    
    # Summary
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    print(f"View mode recording: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Invalid file detection: {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    
    return 0 if (test1_passed and test2_passed) else 1


if __name__ == "__main__":
    sys.exit(main())