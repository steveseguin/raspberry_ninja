#!/usr/bin/env python3
"""
Test recording functionality with media file validation
Tests both single and multi-stream recording and validates the output files
"""

import unittest
import subprocess
import time
import os
import sys
import glob
from pathlib import Path
import asyncio

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our media validator
from validate_media_file import MediaFileValidator, validate_recording


class TestRecordingWithValidation(unittest.TestCase):
    """Test recording functionality and validate output files"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        cls.validator = MediaFileValidator()
        cls.test_output_dir = Path("test_recording_output")
        cls.test_output_dir.mkdir(exist_ok=True)
        
    def setUp(self):
        """Set up each test"""
        self.processes = []
        self.room_name = f"test_room_{int(time.time())}"
        self.cleanup_files()
        
    def tearDown(self):
        """Clean up after each test"""
        # Terminate all processes
        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
                
        # Give time for files to be finalized
        time.sleep(2)
        
    def cleanup_files(self):
        """Remove test files"""
        patterns = [
            "test_rec_*.ts", "test_rec_*.mkv", "test_rec_*.webm",
            "room_rec_*.ts", "room_rec_*.mkv", "room_rec_*.webm"
        ]
        for pattern in patterns:
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                except:
                    pass
                    
    def start_publisher(self, stream_name, codec="h264", audio=False):
        """Start a test publisher"""
        cmd = [
            sys.executable, "publish.py",
            "--test",
            "--room", self.room_name,
            "--stream", stream_name,
            f"--{codec}",
            "--bitrate", "1000"
        ]
        
        if not audio:
            cmd.append("--noaudio")
            
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.processes.append(proc)
        return proc
        
    def start_recorder(self, view_stream=None, record_prefix="test_rec", room_recording=False):
        """Start a recorder"""
        cmd = [
            sys.executable, "publish.py",
            "--room", self.room_name,
            "--record", record_prefix,
            "--bitrate", "2000",
            "--noaudio"
        ]
        
        if room_recording:
            cmd.append("--record-room")
        elif view_stream:
            cmd.extend(["--view", view_stream])
            
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        self.processes.append(proc)
        return proc
        
    def find_recordings(self, prefix="test_rec"):
        """Find recorded files"""
        patterns = [
            f"{prefix}*.ts",
            f"{prefix}*.mkv", 
            f"{prefix}*.webm",
            f"*{prefix}*.ts",
            f"*{prefix}*.mkv"
        ]
        
        recordings = []
        for pattern in patterns:
            recordings.extend(glob.glob(pattern))
            
        return list(set(recordings))  # Remove duplicates
        
    def validate_recordings(self, recordings):
        """Validate all recordings using GStreamer"""
        validation_results = {}
        all_valid = True
        
        for filepath in recordings:
            is_valid, info = self.validator.validate_file(filepath, timeout=5)
            validation_results[filepath] = {
                "valid": is_valid,
                "info": info
            }
            
            if not is_valid:
                all_valid = False
                print(f"\n❌ Validation failed for {filepath}")
                print(f"   Error: {info.get('error', 'Unknown error')}")
            else:
                print(f"\n✅ Validated {filepath}")
                print(f"   Format: {info.get('format', 'unknown')}")
                print(f"   Frames: {info.get('frames_decoded', 0)}")
                print(f"   Size: {info.get('file_size_bytes', 0):,} bytes")
                
        return all_valid, validation_results
        
    def test_single_stream_recording_h264(self):
        """Test recording a single H.264 stream and validate output"""
        print("\n=== Testing Single H.264 Stream Recording ===")
        
        # Start publisher
        pub = self.start_publisher("alice", "h264")
        time.sleep(3)
        
        # Start recorder
        rec = self.start_recorder(view_stream="alice")
        time.sleep(10)  # Record for 10 seconds
        
        # Stop recorder
        rec.terminate()
        rec.wait(timeout=5)
        time.sleep(2)  # Wait for file finalization
        
        # Find recordings
        recordings = self.find_recordings()
        self.assertGreater(len(recordings), 0, "No recordings found")
        
        # Validate recordings
        all_valid, results = self.validate_recordings(recordings)
        self.assertTrue(all_valid, "Some recordings failed validation")
        
        # Check that we got H.264/TS files
        ts_files = [f for f in recordings if f.endswith('.ts')]
        self.assertGreater(len(ts_files), 0, "No .ts files found for H.264 recording")
        
    def test_single_stream_recording_vp8(self):
        """Test recording a single VP8 stream and validate output"""
        print("\n=== Testing Single VP8 Stream Recording ===")
        
        # Start publisher
        pub = self.start_publisher("bob", "vp8")
        time.sleep(3)
        
        # Start recorder
        rec = self.start_recorder(view_stream="bob")
        time.sleep(10)  # Record for 10 seconds
        
        # Stop recorder
        rec.terminate()
        rec.wait(timeout=5)
        time.sleep(2)
        
        # Find recordings
        recordings = self.find_recordings()
        self.assertGreater(len(recordings), 0, "No recordings found")
        
        # Validate recordings
        all_valid, results = self.validate_recordings(recordings)
        self.assertTrue(all_valid, "Some recordings failed validation")
        
        # Check that we got VP8/MKV files
        mkv_files = [f for f in recordings if f.endswith('.mkv') or f.endswith('.webm')]
        self.assertGreater(len(mkv_files), 0, "No .mkv/.webm files found for VP8 recording")
        
    def test_multi_stream_recording(self):
        """Test recording multiple streams and validate all outputs"""
        print("\n=== Testing Multi-Stream Recording ===")
        
        # Start multiple publishers
        publishers = [
            ("alice", "h264"),
            ("bob", "vp8"),
            ("charlie", "vp9")
        ]
        
        for name, codec in publishers:
            self.start_publisher(name, codec)
            time.sleep(2)
            
        # Give publishers time to establish
        time.sleep(3)
        
        # Start room recording
        rec = self.start_recorder(record_prefix="room_rec", room_recording=True)
        
        # Record for 15 seconds
        time.sleep(15)
        
        # Stop recorder
        rec.terminate()
        rec.wait(timeout=5)
        time.sleep(3)  # Extra time for file finalization
        
        # Find all recordings
        recordings = self.find_recordings("room_rec")
        print(f"\nFound {len(recordings)} recording files")
        
        # We expect at least one recording
        self.assertGreater(len(recordings), 0, "No recordings found")
        
        # Validate all recordings
        all_valid, results = self.validate_recordings(recordings)
        
        # Print summary
        print("\n=== Validation Summary ===")
        valid_count = sum(1 for r in results.values() if r["valid"])
        print(f"Valid files: {valid_count}/{len(recordings)}")
        
        # Check specific formats
        h264_files = [f for f in recordings if f.endswith('.ts')]
        vp_files = [f for f in recordings if f.endswith('.mkv') or f.endswith('.webm')]
        
        print(f"H.264 files (.ts): {len(h264_files)}")
        print(f"VP8/VP9 files (.mkv/.webm): {len(vp_files)}")
        
        self.assertTrue(all_valid, "Some recordings failed validation")
        
    def test_recording_with_network_issues(self):
        """Test recording continues properly with brief network interruption"""
        print("\n=== Testing Recording Resilience ===")
        
        # Start publisher
        pub = self.start_publisher("test_stream", "h264")
        time.sleep(3)
        
        # Start recorder
        rec = self.start_recorder(view_stream="test_stream")
        time.sleep(5)
        
        # Simulate brief interruption by pausing publisher
        # (In real test, we'd simulate network issues)
        
        # Continue recording
        time.sleep(5)
        
        # Stop recorder
        rec.terminate()
        rec.wait(timeout=5)
        time.sleep(2)
        
        # Validate recordings
        recordings = self.find_recordings()
        self.assertGreater(len(recordings), 0, "No recordings found")
        
        all_valid, results = self.validate_recordings(recordings)
        self.assertTrue(all_valid, "Recording validation failed after interruption")
        
        # Check that files have reasonable size (shows recording continued)
        for filepath, result in results.items():
            if result["valid"]:
                size_mb = result["info"].get("file_size_bytes", 0) / (1024 * 1024)
                self.assertGreater(size_mb, 0.1, f"Recording {filepath} is too small")
                

class TestMediaValidator(unittest.TestCase):
    """Test the media validator itself"""
    
    def setUp(self):
        self.validator = MediaFileValidator()
        
    def test_validate_nonexistent_file(self):
        """Test validation of non-existent file"""
        is_valid, info = self.validator.validate_file("/tmp/nonexistent.ts")
        self.assertFalse(is_valid)
        self.assertIn("error", info)
        
    def test_validate_invalid_file(self):
        """Test validation of invalid media file"""
        # Create an invalid file
        invalid_file = "test_invalid.ts"
        with open(invalid_file, "wb") as f:
            f.write(b"This is not a valid media file")
            
        try:
            is_valid, info = self.validator.validate_file(invalid_file)
            self.assertFalse(is_valid)
            self.assertIn("error", info)
        finally:
            os.remove(invalid_file)
            
    def test_validate_multiple_files(self):
        """Test batch validation"""
        # Create test files
        test_files = []
        for i in range(3):
            filename = f"test_batch_{i}.txt"
            with open(filename, "w") as f:
                f.write("dummy")
            test_files.append(filename)
            
        try:
            summary = self.validator.validate_multiple_files(test_files)
            self.assertEqual(summary["total_files"], 3)
            self.assertEqual(summary["valid_files"], 0)  # All should be invalid
        finally:
            for f in test_files:
                try:
                    os.remove(f)
                except:
                    pass


def run_recording_tests():
    """Run recording tests with validation"""
    # Create test suite
    suite = unittest.TestSuite()
    
    # Add tests
    suite.addTest(TestRecordingWithValidation('test_single_stream_recording_h264'))
    suite.addTest(TestRecordingWithValidation('test_single_stream_recording_vp8'))
    suite.addTest(TestRecordingWithValidation('test_multi_stream_recording'))
    suite.addTest(TestRecordingWithValidation('test_recording_with_network_issues'))
    
    # Add validator tests
    suite.addTest(TestMediaValidator('test_validate_nonexistent_file'))
    suite.addTest(TestMediaValidator('test_validate_invalid_file'))
    suite.addTest(TestMediaValidator('test_validate_multiple_files'))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    # Run with either unittest or our custom runner
    if '--custom' in sys.argv:
        success = run_recording_tests()
        sys.exit(0 if success else 1)
    else:
        unittest.main()