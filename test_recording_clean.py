#!/usr/bin/env python3
"""
Clean recording test with validation
Tests both single stream and multi-stream recording with media validation
"""

import subprocess
import sys
import time
import os
import glob
from validate_media_file import MediaFileValidator


class RecordingTest:
    def __init__(self):
        self.validator = MediaFileValidator()
        self.processes = []
        
    def cleanup(self):
        """Clean up processes and files"""
        # Stop all processes
        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
        self.processes = []
        
        # Clean up files
        patterns = ["test_*.ts", "test_*.mkv", "room_*.ts", "room_*.mkv"]
        for pattern in patterns:
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                except:
                    pass
                    
    def start_publisher(self, room, stream_name, codec="h264"):
        """Start a test publisher"""
        cmd = [
            sys.executable, "publish.py",
            "--test",
            "--room", room,
            "--stream", stream_name,
            "--noaudio",
            f"--{codec}"
        ]
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.processes.append(proc)
        return proc
        
    def start_recorder(self, room, view=None, prefix="test"):
        """Start a recorder"""
        cmd = [
            sys.executable, "publish.py",
            "--room", room,
            "--record", prefix,
            "--noaudio"
        ]
        
        if view:
            cmd.extend(["--view", view])
        else:
            cmd.append("--record-room")
            
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        self.processes.append(proc)
        return proc
        
    def test_single_stream(self):
        """Test single stream recording with validation"""
        print("\n" + "="*60)
        print("TEST 1: Single Stream Recording (H.264)")
        print("="*60)
        
        self.cleanup()
        room = f"test_single_{int(time.time())}"
        
        # Start publisher
        print(f"\n1. Starting H.264 publisher in room: {room}")
        pub = self.start_publisher(room, "alice", "h264")
        time.sleep(3)
        
        # Start recorder
        print("2. Starting recorder...")
        rec = self.start_recorder(room, view="alice", prefix="test_single")
        time.sleep(10)
        
        # Stop recorder
        print("3. Stopping recorder...")
        rec.terminate()
        rec.wait(timeout=5)
        time.sleep(2)
        
        # Find and validate recordings
        print("4. Validating recordings...")
        recordings = glob.glob("test_single_*.ts") + glob.glob("test_single_*.mkv")
        
        if not recordings:
            print("   ❌ No recordings found!")
            return False
            
        success = True
        for recording in recordings:
            is_valid, info = self.validator.validate_file(recording, timeout=5)
            size_mb = os.path.getsize(recording) / (1024 * 1024)
            
            if is_valid:
                print(f"   ✅ {recording}")
                print(f"      Size: {size_mb:.2f} MB")
                print(f"      Frames: {info.get('frames_decoded', 0)}")
                print(f"      Format: {info.get('format', 'unknown')}")
            else:
                print(f"   ❌ {recording} - INVALID")
                print(f"      Error: {info.get('error', 'Unknown')}")
                success = False
                
        return success
        
    def test_multi_stream(self):
        """Test multi-stream recording with validation"""
        print("\n" + "="*60)
        print("TEST 2: Multi-Stream Recording")
        print("="*60)
        
        self.cleanup()
        room = f"test_multi_{int(time.time())}"
        
        # Start multiple publishers
        print(f"\n1. Starting publishers in room: {room}")
        streams = [
            ("alice", "h264"),
            ("bob", "vp8"),
            ("charlie", "vp9")
        ]
        
        for name, codec in streams:
            print(f"   Starting {name} ({codec})...")
            self.start_publisher(room, name, codec)
            time.sleep(2)
            
        # Wait for publishers to establish
        print("\n2. Waiting for publishers to connect...")
        time.sleep(5)
        
        # Start room recorder
        print("3. Starting room recorder...")
        rec = self.start_recorder(room, prefix="room")
        
        # Record for 15 seconds
        print("4. Recording for 15 seconds...")
        time.sleep(15)
        
        # Stop recorder
        print("5. Stopping recorder...")
        rec.terminate()
        
        # Get recorder output
        output, _ = rec.communicate(timeout=5)
        
        # Check output for multi-peer mode
        if "Multi-Peer" in output:
            print("   ✅ Multi-peer mode detected")
        elif "spawn" in output.lower():
            print("   ⚠️  Process spawning mode detected")
        else:
            print("   ❓ Recording mode unclear")
            
        time.sleep(3)
        
        # Find and validate recordings
        print("\n6. Validating recordings...")
        all_recordings = []
        for pattern in ["room_*.ts", "room_*.mkv", f"{room}_*.ts", f"{room}_*.mkv"]:
            all_recordings.extend(glob.glob(pattern))
            
        # Remove duplicates
        all_recordings = list(set(all_recordings))
        
        if not all_recordings:
            print("   ❌ No recordings found!")
            # Print some recorder output for debugging
            print("\nRecorder output (first 500 chars):")
            print("-"*40)
            print(output[:500])
            print("-"*40)
            return False
            
        print(f"\n   Found {len(all_recordings)} recording file(s):")
        
        success = True
        valid_count = 0
        total_frames = 0
        
        for recording in sorted(all_recordings):
            is_valid, info = self.validator.validate_file(recording, timeout=5)
            size_mb = os.path.getsize(recording) / (1024 * 1024)
            
            if is_valid:
                valid_count += 1
                frames = info.get('frames_decoded', 0)
                total_frames += frames
                print(f"\n   ✅ {recording}")
                print(f"      Size: {size_mb:.2f} MB")
                print(f"      Frames: {frames}")
                print(f"      Format: {info.get('format', 'unknown')}")
            else:
                print(f"\n   ❌ {recording} - INVALID")
                print(f"      Error: {info.get('error', 'Unknown')}")
                success = False
                
        print(f"\n   Summary:")
        print(f"   - Total files: {len(all_recordings)}")
        print(f"   - Valid files: {valid_count}")
        print(f"   - Total frames: {total_frames}")
        
        # Check if we got recordings for different streams
        stream_count = 0
        for name, _ in streams:
            if any(name in f for f in all_recordings):
                stream_count += 1
                
        if stream_count > 1:
            print(f"   - Streams recorded: {stream_count}/{len(streams)}")
        elif len(all_recordings) == 1:
            print("   - ⚠️  Only one recording file (might be single WebSocket recording)")
        
        return success and valid_count > 0
        
    def run_all_tests(self):
        """Run all tests"""
        print("\n🎬 Recording Tests with Media Validation")
        print("This will test recording functionality and validate output files\n")
        
        results = []
        
        # Test 1: Single stream
        try:
            result1 = self.test_single_stream()
            results.append(("Single Stream Recording", result1))
        except Exception as e:
            print(f"\n❌ Single stream test failed with error: {e}")
            results.append(("Single Stream Recording", False))
        finally:
            self.cleanup()
            
        # Test 2: Multi-stream
        try:
            result2 = self.test_multi_stream()
            results.append(("Multi-Stream Recording", result2))
        except Exception as e:
            print(f"\n❌ Multi-stream test failed with error: {e}")
            results.append(("Multi-Stream Recording", False))
        finally:
            self.cleanup()
            
        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        all_passed = True
        for test_name, passed in results:
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"{test_name}: {status}")
            if not passed:
                all_passed = False
                
        print("="*60)
        
        return all_passed


def main():
    """Run the tests"""
    tester = RecordingTest()
    
    try:
        success = tester.run_all_tests()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        return 1
    finally:
        tester.cleanup()


if __name__ == "__main__":
    sys.exit(main())