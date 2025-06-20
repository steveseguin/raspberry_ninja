#!/usr/bin/env python3
"""
Simple demonstration of media file validation
Shows how the validation works with actual recordings
"""

import subprocess
import sys
import time
import os
import glob
from validate_media_file import validate_recording, MediaFileValidator


def demo_validation():
    """Demonstrate media file validation"""
    print("🎬 Media File Validation Demo")
    print("="*50)
    
    # Clean up old test files
    for f in glob.glob("demo_*.ts") + glob.glob("demo_*.mkv"):
        os.remove(f)
    
    room = f"demo_{int(time.time())}"
    
    # Start a test publisher
    print(f"\n1. Starting test publisher (H.264)...")
    publisher = subprocess.Popen([
        sys.executable, "publish.py",
        "--test", "--room", room,
        "--stream", "demo_stream",
        "--noaudio", "--h264",
        "--bitrate", "1500"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    time.sleep(3)
    
    # Start recorder
    print("2. Starting recorder...")
    recorder = subprocess.Popen([
        sys.executable, "publish.py",
        "--room", room,
        "--view", "demo_stream",
        "--record", "demo",
        "--noaudio"
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    print("3. Recording for 10 seconds...")
    time.sleep(10)
    
    # Stop recorder
    print("4. Stopping recorder...")
    recorder.terminate()
    recorder.wait(timeout=5)
    time.sleep(2)  # Wait for file finalization
    
    # Stop publisher
    publisher.terminate()
    
    # Find recordings
    recordings = glob.glob("demo_*.ts") + glob.glob("demo_*.mkv")
    
    if not recordings:
        print("\n❌ No recordings found!")
        return False
        
    print(f"\n5. Found {len(recordings)} recording(s):")
    for f in recordings:
        print(f"   - {f} ({os.path.getsize(f):,} bytes)")
        
    # Validate recordings
    print("\n6. Validating recordings with GStreamer:")
    print("-"*50)
    
    validator = MediaFileValidator()
    all_valid = True
    
    for recording in recordings:
        print(f"\nValidating: {recording}")
        is_valid, info = validator.validate_file(recording, timeout=5)
        
        if is_valid:
            print(f"✅ VALID")
            print(f"   Format: {info.get('format', 'unknown')}")
            print(f"   Frames decoded: {info.get('frames_decoded', 0)}")
            if info.get('duration_seconds'):
                print(f"   Duration: {info['duration_seconds']:.2f} seconds")
            print(f"   File size: {info.get('file_size_bytes', 0):,} bytes")
            if info.get('estimated_fps'):
                print(f"   Estimated FPS: {info['estimated_fps']:.1f}")
        else:
            print(f"❌ INVALID")
            print(f"   Error: {info.get('error', 'Unknown error')}")
            all_valid = False
            
    print("\n" + "="*50)
    if all_valid:
        print("✅ All recordings passed validation!")
    else:
        print("❌ Some recordings failed validation")
        
    # Clean up
    print("\n7. Cleaning up test files...")
    for f in recordings:
        os.remove(f)
        
    return all_valid


def test_invalid_file():
    """Test validation of an invalid file"""
    print("\n\n🧪 Testing Invalid File Detection")
    print("="*50)
    
    # Create an invalid file
    invalid_file = "test_invalid.ts"
    print(f"\n1. Creating invalid test file: {invalid_file}")
    with open(invalid_file, "wb") as f:
        f.write(b"This is not a valid MPEG-TS file!\n" * 100)
        
    print(f"   File size: {os.path.getsize(invalid_file)} bytes")
    
    # Try to validate it
    print("\n2. Attempting to validate...")
    is_valid = validate_recording(invalid_file, verbose=True)
    
    if not is_valid:
        print("\n✅ Correctly identified as invalid!")
    else:
        print("\n❌ ERROR: File was incorrectly marked as valid!")
        
    # Clean up
    os.remove(invalid_file)
    
    return not is_valid  # Success if file was invalid


def main():
    """Run validation demos"""
    print("Media File Validation Demo")
    print("This demonstrates how GStreamer validation works\n")
    
    # Check if GStreamer is available
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        Gst.init(None)
    except Exception as e:
        print(f"❌ GStreamer not available: {e}")
        print("Please ensure GStreamer is installed")
        return 1
        
    # Run demos
    success1 = demo_validation()
    success2 = test_invalid_file()
    
    print("\n" + "="*50)
    print("Demo Complete!")
    print(f"Valid file test: {'✅ Passed' if success1 else '❌ Failed'}")
    print(f"Invalid file test: {'✅ Passed' if success2 else '❌ Failed'}")
    
    return 0 if (success1 and success2) else 1


if __name__ == "__main__":
    sys.exit(main())