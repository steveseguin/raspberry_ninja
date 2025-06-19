#!/usr/bin/env python3
"""
Test the shared WebSocket multi-peer implementation
"""

import subprocess
import time
import sys
import os
from pathlib import Path


def test_shared_websocket():
    """Test room recording with shared WebSocket"""
    print("🧪 Testing Shared WebSocket Multi-Peer Recording")
    print("="*50)
    
    # Clean up old files
    os.system("rm -f shared_test_*.ts shared_test_*.mkv shared_test_*.log")
    
    # Generate unique room name
    room_name = f"shared_test_{int(time.time())}"
    print(f"Room: {room_name}")
    
    processes = []
    
    try:
        # Start 3 publishers with different codecs
        publishers = [
            ("alice", "h264", "1000"),
            ("bob", "vp8", "1000"),
            ("charlie", "vp9", "1000")
        ]
        
        print("\n1. Starting publishers:")
        for name, codec, bitrate in publishers:
            cmd = [
                sys.executable, "publish.py",
                "--test",
                "--room", room_name,
                "--stream", name,
                "--noaudio",
                f"--{codec}",
                "--bitrate", bitrate
            ]
            
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(proc)
            print(f"   ✅ {name} ({codec.upper()}) - PID: {proc.pid}")
            time.sleep(2)
            
        # Wait for all publishers to connect
        print("\n2. Waiting for publishers to fully connect...")
        time.sleep(10)
        
        # Now use the original room recording approach (not spawning separate processes)
        print("\n3. Starting multi-peer room recorder (single WebSocket)...")
        recorder_cmd = [
            sys.executable, "publish.py",
            "--room", room_name,
            "--record", "shared_test",
            "--record-room",  # This should use multi-peer client
            "--noaudio",
            "--bitrate", "2000"
        ]
        
        print("   Command:", " ".join(recorder_cmd))
        print("\n" + "-"*50)
        print("RECORDER OUTPUT:")
        print("-"*50)
        
        # Run recorder with visible output
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        
        try:
            result = subprocess.run(recorder_cmd, timeout=30, capture_output=False, env=env)
        except subprocess.TimeoutExpired:
            print("\n" + "-"*50)
            print("Recorder timeout (expected after 30s)")
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            
        print("-"*50)
        
        # Give time for files to be finalized
        time.sleep(2)
        
        # Check for recordings
        print("\n4. Checking recordings:")
        
        all_recordings = []
        total_size = 0
        
        # Look for recordings - they should have the room_name_streamID pattern
        for name, codec, _ in publishers:
            # Check different possible patterns
            patterns = [
                f"{room_name}_{name}_*.ts",
                f"{room_name}_{name}_*.mkv",
                f"shared_test_{name}_*.ts", 
                f"shared_test_{name}_*.mkv"
            ]
            
            files = []
            for pattern in patterns:
                files.extend(list(Path(".").glob(pattern)))
            
            if files:
                print(f"\n   Stream '{name}' ({codec}):")
                for f in files:
                    size = f.stat().st_size
                    all_recordings.append((name, f, size))
                    total_size += size
                    print(f"     ✅ {f.name} ({size:,} bytes)")
            else:
                print(f"\n   Stream '{name}' ({codec}):")
                print(f"     ❌ No recordings found")
                
        # Summary
        if all_recordings:
            print(f"\n✅ SUCCESS!")
            print(f"   Total: {len(all_recordings)} files, {total_size:,} bytes")
            print(f"   Average: {total_size // len(all_recordings):,} bytes per file")
            
            # Verify we have separate files for each stream
            streams_recorded = set(name for name, _, _ in all_recordings)
            if len(streams_recorded) == len(publishers):
                print(f"   ✅ All {len(publishers)} streams recorded separately!")
            else:
                print(f"   ⚠️  Only {len(streams_recorded)}/{len(publishers)} streams recorded")
        else:
            print("\n❌ FAILED - No recordings found!")
            
            # Debug: list all files
            print("\nAll files matching patterns:")
            debug_files = list(Path(".").glob("shared_test*"))
            debug_files.extend(list(Path(".").glob(f"{room_name}_*")))
            if debug_files:
                for f in sorted(set(debug_files)):
                    print(f"   - {f.name}")
            else:
                print("   (none found)")
                
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        print("\n5. Cleaning up...")
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
                
        # Force kill after timeout
        time.sleep(2)
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
                
    print("\n" + "="*50)
    print("Test complete!")
    
    # Return success/failure
    return len(all_recordings) > 0 and len(set(name for name, _, _ in all_recordings)) > 1


if __name__ == "__main__":
    success = test_shared_websocket()
    sys.exit(0 if success else 1)