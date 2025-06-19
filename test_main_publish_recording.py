#!/usr/bin/env python3
"""
Test script to verify that recording functionality works in the main publish.py file
"""

import subprocess
import time
import os
import json
import signal
import sys
from datetime import datetime
import glob
import threading

# Test configuration
TEST_STREAM_ID = "test_record_12345"
TEST_DURATION = 15  # seconds
PUBLISHER_STARTUP_TIME = 5  # seconds to wait for publisher to start
RECORDER_STARTUP_TIME = 3   # seconds to wait for recorder to start

def cleanup_test_files():
    """Clean up any existing test recording files"""
    pattern = f"{TEST_STREAM_ID}_*.{'{ts,mkv,webm}'}"
    for file in glob.glob(pattern):
        try:
            os.remove(file)
            print(f"Removed existing test file: {file}")
        except Exception as e:
            print(f"Failed to remove {file}: {e}")

def start_publisher():
    """Start a test video stream publisher"""
    print("\n🎬 Starting test publisher...")
    cmd = [
        "python3", "publish.py",
        "--test",  # Use test sources
        "--streamid", TEST_STREAM_ID,
        "--bitrate", "500"
    ]
    
    # Start publisher process
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1
    )
    
    # Monitor output in a separate thread
    def monitor_output(pipe, prefix):
        for line in pipe:
            print(f"[PUBLISHER {prefix}] {line.strip()}")
    
    stdout_thread = threading.Thread(target=monitor_output, args=(process.stdout, "OUT"))
    stderr_thread = threading.Thread(target=monitor_output, args=(process.stderr, "ERR"))
    stdout_thread.start()
    stderr_thread.start()
    
    return process

def start_recorder():
    """Start recording the test stream"""
    print(f"\n📹 Starting recorder for stream: {TEST_STREAM_ID}")
    cmd = [
        "python3", "publish.py",
        "--record", TEST_STREAM_ID,
        "--view", TEST_STREAM_ID  # Required for recording to work
    ]
    
    # Start recorder process
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1
    )
    
    # Monitor output in a separate thread
    def monitor_output(pipe, prefix):
        for line in pipe:
            print(f"[RECORDER {prefix}] {line.strip()}")
            # Look for recording confirmation
            if "Recording" in line or "record" in line.lower():
                print(f"  ✅ Recording indication found: {line.strip()}")
    
    stdout_thread = threading.Thread(target=monitor_output, args=(process.stdout, "OUT"))
    stderr_thread = threading.Thread(target=monitor_output, args=(process.stderr, "ERR"))
    stdout_thread.start()
    stderr_thread.start()
    
    return process

def check_recording_files():
    """Check if recording files were created"""
    print("\n🔍 Checking for recording files...")
    
    # Look for various file patterns
    patterns = [
        f"{TEST_STREAM_ID}_*.ts",
        f"{TEST_STREAM_ID}_*.mkv",
        f"{TEST_STREAM_ID}_*.webm",
        f"{TEST_STREAM_ID}_*audio*.ts"
    ]
    
    found_files = []
    for pattern in patterns:
        files = glob.glob(pattern)
        found_files.extend(files)
    
    if found_files:
        print(f"\n✅ Recording files found:")
        for file in found_files:
            size = os.path.getsize(file)
            mod_time = datetime.fromtimestamp(os.path.getmtime(file))
            print(f"   - {file}: {size:,} bytes, modified at {mod_time}")
            
            # Check if file is growing (sign of active recording)
            if size > 0:
                print(f"     ✓ File has content")
            else:
                print(f"     ⚠️  File is empty")
    else:
        print("\n❌ No recording files found!")
        print(f"   Expected files matching patterns: {patterns}")
    
    return found_files

def main():
    """Main test function"""
    print("=" * 60)
    print("Recording Functionality Test for publish.py")
    print("=" * 60)
    
    # Clean up any existing test files
    cleanup_test_files()
    
    publisher_process = None
    recorder_process = None
    
    try:
        # Step 1: Start publisher
        publisher_process = start_publisher()
        print(f"\n⏳ Waiting {PUBLISHER_STARTUP_TIME}s for publisher to initialize...")
        time.sleep(PUBLISHER_STARTUP_TIME)
        
        # Step 2: Start recorder
        recorder_process = start_recorder()
        print(f"\n⏳ Waiting {RECORDER_STARTUP_TIME}s for recorder to initialize...")
        time.sleep(RECORDER_STARTUP_TIME)
        
        # Step 3: Let recording run
        print(f"\n⏰ Recording for {TEST_DURATION} seconds...")
        
        # Check for files periodically
        for i in range(TEST_DURATION // 5):
            time.sleep(5)
            files = check_recording_files()
            if files:
                print(f"\n   Progress check {i+1}: Found {len(files)} recording file(s)")
        
        # Final check
        time.sleep(TEST_DURATION % 5)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up processes
        print("\n🧹 Cleaning up...")
        
        if recorder_process:
            print("   Stopping recorder...")
            recorder_process.terminate()
            recorder_process.wait(timeout=5)
        
        if publisher_process:
            print("   Stopping publisher...")
            publisher_process.terminate()
            publisher_process.wait(timeout=5)
        
        # Final file check
        print("\n" + "=" * 60)
        print("FINAL RESULTS:")
        print("=" * 60)
        
        files = check_recording_files()
        
        # Generate test report
        test_results = {
            "test_time": datetime.now().isoformat(),
            "test_duration": TEST_DURATION,
            "stream_id": TEST_STREAM_ID,
            "recording_files_found": len(files),
            "files": []
        }
        
        for file in files:
            test_results["files"].append({
                "name": file,
                "size": os.path.getsize(file),
                "modified": datetime.fromtimestamp(os.path.getmtime(file)).isoformat()
            })
        
        # Save test results
        with open("test_results.json", "w") as f:
            json.dump(test_results, f, indent=2)
        
        if files:
            print(f"\n✅ TEST PASSED: {len(files)} recording file(s) created")
            print("\nTest results saved to: test_results.json")
        else:
            print("\n❌ TEST FAILED: No recording files created")
            print("\nPossible issues:")
            print("  - Recording functionality not properly implemented")
            print("  - WebRTC connection failed")
            print("  - File permissions issue")
            print("  - Check the output above for error messages")
        
        print("\n" + "=" * 60)

if __name__ == "__main__":
    main()