#!/usr/bin/env python3
"""
Comprehensive test for multi-stream inbound connections and recording.
This test creates multiple publishers and verifies that each inbound stream is recorded separately.
"""

import subprocess
import asyncio
import time
import os
import sys
import json
import signal
from pathlib import Path
from datetime import datetime
import threading
import queue

class MultiStreamRecordingTest:
    """Test multi-stream recording with detailed monitoring"""
    
    def __init__(self):
        self.test_dir = Path("test_multi_stream_recording")
        self.test_dir.mkdir(exist_ok=True)
        self.processes = []
        self.room_name = f"test_multi_{int(time.time())}"
        self.log_queue = queue.Queue()
        self.test_results = {
            "start_time": datetime.now().isoformat(),
            "room_name": self.room_name,
            "publishers": {},
            "recordings": {},
            "errors": [],
            "success": False
        }
        
    def log(self, message, level="INFO"):
        """Thread-safe logging"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        print(log_entry)
        self.log_queue.put(log_entry)
        
    def cleanup(self):
        """Clean up all processes"""
        self.log("Cleaning up processes...", "INFO")
        for proc in self.processes:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
            except:
                pass
    
    def start_publisher(self, stream_id, codec="vp8", video_pattern="ball"):
        """Start a test publisher with specific settings"""
        cmd = [
            sys.executable, "../publish.py",
            "--test",
            "--room", self.room_name,
            "--stream", stream_id,
            "--noaudio",
            f"--{codec}",
            "--bitrate", "800",
            "--framerate", "15"
        ]
        
        # Add different test patterns for visual distinction
        patterns = {
            "ball": "ball",
            "smpte": "smpte",
            "snow": "snow",
            "bars": "smpte100"
        }
        
        if video_pattern in patterns:
            # We'll use different patterns to distinguish streams visually
            # (though this would require modifying the videotestsrc pattern in publish.py)
            pass
        
        self.log(f"Starting publisher: {stream_id} with {codec.upper()}", "INFO")
        
        log_file = self.test_dir / f"publisher_{stream_id}.log"
        with open(log_file, "w") as f:
            proc = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                cwd=str(self.test_dir)
            )
        
        self.processes.append(proc)
        self.test_results["publishers"][stream_id] = {
            "codec": codec,
            "pid": proc.pid,
            "start_time": datetime.now().isoformat(),
            "log_file": str(log_file)
        }
        
        return proc
    
    def start_multi_stream_recorder(self, record_prefix="multi_rec"):
        """Start the recorder that should handle multiple inbound streams"""
        cmd = [
            sys.executable, "../publish.py",
            "--room", self.room_name,
            "--record", record_prefix,
            "--record-room",
            "--noaudio",
            "--bitrate", "2000"
        ]
        
        self.log("Starting multi-stream recorder", "INFO")
        
        # Start recorder with real-time output monitoring
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(self.test_dir),
            universal_newlines=True,
            bufsize=1
        )
        
        self.processes.append(proc)
        
        # Start output monitor thread
        monitor_thread = threading.Thread(
            target=self.monitor_recorder_output,
            args=(proc,)
        )
        monitor_thread.daemon = True
        monitor_thread.start()
        
        return proc
    
    def monitor_recorder_output(self, proc):
        """Monitor recorder output in real-time"""
        while proc.poll() is None:
            try:
                line = proc.stdout.readline()
                if line:
                    line = line.strip()
                    
                    # Log important events
                    if "Will record" in line:
                        self.log(f"Recorder: {line}", "SUCCESS")
                    elif "Creating isolated connection" in line:
                        self.log(f"Recorder: {line}", "INFO")
                    elif "Recording" in line and ("to:" in line or "started" in line):
                        self.log(f"Recorder: {line}", "SUCCESS")
                    elif "session" in line:
                        self.log(f"Recorder: {line}", "INFO")
                    elif "error" in line.lower() or "failed" in line.lower():
                        self.log(f"Recorder: {line}", "ERROR")
                        self.test_results["errors"].append(line)
                    elif "bytes" in line and "📊" in line:
                        # Progress update
                        self.log(f"Progress: {line}", "INFO")
            except:
                break
    
    def verify_recordings(self, expected_streams, record_prefix="multi_rec"):
        """Verify that recordings were created for each stream"""
        self.log("\nVerifying recordings...", "INFO")
        
        # Look for recording files
        recording_patterns = [
            f"{self.room_name}_{stream_id}_*.ts" for stream_id in expected_streams
        ] + [
            f"{self.room_name}_{stream_id}_*.mkv" for stream_id in expected_streams
        ] + [
            f"{record_prefix}_{stream_id}_*.ts" for stream_id in expected_streams
        ] + [
            f"{record_prefix}_{stream_id}_*.mkv" for stream_id in expected_streams
        ] + [
            f"{record_prefix}_*.ts",
            f"{record_prefix}_*.mkv"
        ]
        
        found_recordings = {}
        
        for pattern in recording_patterns:
            matches = list(self.test_dir.glob(pattern))
            for match in matches:
                if match.stat().st_size > 0:
                    # Extract stream ID from filename
                    for stream_id in expected_streams:
                        if stream_id in match.name:
                            if stream_id not in found_recordings:
                                found_recordings[stream_id] = []
                            found_recordings[stream_id].append({
                                "file": match.name,
                                "size": match.stat().st_size,
                                "path": str(match)
                            })
                            break
        
        # Report findings
        success = True
        for stream_id in expected_streams:
            if stream_id in found_recordings:
                total_size = sum(r["size"] for r in found_recordings[stream_id])
                self.log(f"✅ {stream_id}: {len(found_recordings[stream_id])} files, {total_size:,} bytes", "SUCCESS")
                self.test_results["recordings"][stream_id] = found_recordings[stream_id]
            else:
                self.log(f"❌ {stream_id}: No recordings found", "ERROR")
                success = False
        
        return success, found_recordings
    
    def run_test(self, num_streams=3, duration=30):
        """Run the multi-stream recording test"""
        self.log("="*60, "INFO")
        self.log("🎬 Multi-Stream Inbound Recording Test", "INFO")
        self.log("="*60, "INFO")
        self.log(f"Room: {self.room_name}", "INFO")
        self.log(f"Streams: {num_streams}", "INFO")
        self.log(f"Duration: {duration} seconds", "INFO")
        self.log("="*60, "INFO")
        
        try:
            # Step 1: Start multiple publishers
            self.log("\n📡 Step 1: Starting publishers...", "INFO")
            publishers = []
            stream_configs = [
                ("alice", "h264"),
                ("bob", "vp8"),
                ("charlie", "vp8"),
                ("david", "h264"),
                ("eve", "vp8")
            ][:num_streams]
            
            for stream_id, codec in stream_configs:
                proc = self.start_publisher(stream_id, codec)
                publishers.append((stream_id, proc))
                time.sleep(2)  # Stagger starts to avoid overwhelming
            
            # Step 2: Wait for publishers to initialize
            self.log("\n⏳ Step 2: Waiting for publishers to initialize...", "INFO")
            time.sleep(5)
            
            # Verify publishers are running
            all_running = True
            for stream_id, proc in publishers:
                if proc.poll() is not None:
                    self.log(f"❌ Publisher {stream_id} failed to start", "ERROR")
                    all_running = False
                else:
                    self.log(f"✅ Publisher {stream_id} is running (PID: {proc.pid})", "SUCCESS")
            
            if not all_running:
                self.log("Some publishers failed to start", "ERROR")
                return False
            
            # Step 3: Start the multi-stream recorder
            self.log("\n🔴 Step 3: Starting multi-stream recorder...", "INFO")
            recorder = self.start_multi_stream_recorder()
            
            # Give recorder time to connect to all streams
            self.log("\n⏳ Waiting for recorder to connect to all streams...", "INFO")
            time.sleep(10)
            
            # Step 4: Record for specified duration
            self.log(f"\n⏱️  Step 4: Recording for {duration} seconds...", "INFO")
            recording_start = time.time()
            
            while time.time() - recording_start < duration:
                # Check if recorder is still running
                if recorder.poll() is not None:
                    self.log("❌ Recorder stopped unexpectedly!", "ERROR")
                    break
                
                # Progress update every 5 seconds
                elapsed = int(time.time() - recording_start)
                if elapsed % 5 == 0 and elapsed > 0:
                    self.log(f"Recording progress: {elapsed}/{duration} seconds", "INFO")
                
                time.sleep(1)
            
            # Step 5: Stop recording
            self.log("\n🛑 Step 5: Stopping recorder...", "INFO")
            recorder.terminate()
            
            # Wait for graceful shutdown
            try:
                recorder.wait(timeout=10)
                self.log("Recorder stopped gracefully", "SUCCESS")
            except subprocess.TimeoutExpired:
                self.log("Recorder didn't stop gracefully, forcing...", "WARNING")
                recorder.kill()
                recorder.wait()
            
            # Give time for files to be written
            time.sleep(2)
            
            # Step 6: Verify recordings
            self.log("\n📊 Step 6: Verifying recordings...", "INFO")
            expected_streams = [stream_id for stream_id, _ in stream_configs]
            success, recordings = self.verify_recordings(expected_streams)
            
            # Step 7: Validate recordings with GStreamer
            self.log("\n🔍 Step 7: Validating recordings with GStreamer...", "INFO")
            validation_success = True
            validation_results = {}
            
            try:
                from validate_media_file import MediaFileValidator
                validator = MediaFileValidator()
                
                for stream_id, files in recordings.items():
                    self.log(f"\nValidating {stream_id} recordings...", "INFO")
                    stream_valid = True
                    
                    for file_info in files:
                        filepath = file_info["path"]
                        is_valid, info = validator.validate_file(filepath, timeout=5)
                        
                        if is_valid:
                            self.log(f"  ✅ {os.path.basename(filepath)} - Valid ({info.get('frames_decoded', 0)} frames)", "SUCCESS")
                            validation_results[filepath] = {"valid": True, "frames": info.get('frames_decoded', 0)}
                        else:
                            self.log(f"  ❌ {os.path.basename(filepath)} - Invalid: {info.get('error', 'Unknown')}", "ERROR")
                            validation_results[filepath] = {"valid": False, "error": info.get('error', 'Unknown')}
                            stream_valid = False
                            validation_success = False
                    
                    if not stream_valid:
                        success = False
                        
            except ImportError:
                self.log("⚠️  Media validation not available (validate_media_file.py missing)", "WARNING")
                self.log("   Skipping GStreamer validation", "WARNING")
            except Exception as e:
                self.log(f"❌ Validation error: {str(e)}", "ERROR")
                validation_success = False
            
            # Step 8: Generate summary
            self.log("\n📋 Test Summary:", "INFO")
            self.log("="*60, "INFO")
            
            if success and validation_success:
                self.log("✅ TEST PASSED: All streams were recorded and validated successfully!", "SUCCESS")
                self.test_results["success"] = True
                
                # Detailed summary
                total_files = 0
                total_size = 0
                valid_files = 0
                for stream_id, files in recordings.items():
                    total_files += len(files)
                    total_size += sum(f["size"] for f in files)
                    valid_files += sum(1 for f in files if validation_results.get(f["path"], {}).get("valid", False))
                
                self.log(f"\nTotal recordings: {total_files} files", "INFO")
                self.log(f"Valid recordings: {valid_files} files", "INFO")
                self.log(f"Total size: {total_size:,} bytes ({total_size/1024/1024:.1f} MB)", "INFO")
                self.log(f"Average size per stream: {total_size/len(recordings)/1024/1024:.1f} MB", "INFO")
            else:
                self.log("❌ TEST FAILED: Some streams were not recorded", "ERROR")
                self.test_results["success"] = False
            
            # Save detailed results
            self.test_results["end_time"] = datetime.now().isoformat()
            self.test_results["duration_seconds"] = duration
            
            results_file = self.test_dir / "test_results.json"
            with open(results_file, "w") as f:
                json.dump(self.test_results, f, indent=2)
            
            self.log(f"\nDetailed results saved to: {results_file}", "INFO")
            
            return success
            
        except Exception as e:
            self.log(f"Test failed with exception: {str(e)}", "ERROR")
            import traceback
            traceback.print_exc()
            return False
            
        finally:
            # Always cleanup
            time.sleep(2)
            self.cleanup()

    def run_simple_test(self):
        """Run a simpler test with just 2 streams"""
        self.log("\n🧪 Running simplified test with 2 streams for 15 seconds...", "INFO")
        return self.run_test(num_streams=2, duration=15)


def main():
    """Main test entry point"""
    # Set up signal handling
    def signal_handler(sig, frame):
        print("\n\nTest interrupted by user")
        sys.exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create and run test
    tester = MultiStreamRecordingTest()
    
    # Check command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "--simple":
            success = tester.run_simple_test()
        elif sys.argv[1] == "--long":
            success = tester.run_test(num_streams=4, duration=60)
        else:
            try:
                num_streams = int(sys.argv[1])
                duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30
                success = tester.run_test(num_streams=num_streams, duration=duration)
            except:
                print("Usage: python3 test_multi_stream_recording.py [--simple|--long|<num_streams> [duration]]")
                sys.exit(1)
    else:
        # Default test
        success = tester.run_test(num_streams=3, duration=30)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()