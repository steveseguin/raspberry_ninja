#!/usr/bin/env python3
"""
Final test of multi-peer recording with shared WebSocket
"""

import subprocess
import sys
import time
import os
import glob

def cleanup_files(prefix):
    """Clean up old test files"""
    patterns = [f"{prefix}_*.ts", f"{prefix}_*.mkv", f"{prefix}_*.webm", f"{prefix}_*.m3u8"]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except:
                pass

def main():
    print("🧪 Multi-Peer Recording Test (Shared WebSocket)")
    print("="*60)
    
    # Clean up
    cleanup_files("multipeer")
    
    # Generate room name
    room_name = f"multipeer_{int(time.time())}"
    print(f"Room: {room_name}")
    
    publishers = []
    
    try:
        # Start 3 publishers
        streams = [
            ("alice", "h264", "1500"),
            ("bob", "vp8", "1000"),
            ("charlie", "vp9", "1000")
        ]
        
        print("\n1. Starting publishers:")
        for name, codec, bitrate in streams:
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
            publishers.append((name, proc))
            print(f"   ✅ {name} ({codec.upper()}) - PID: {proc.pid}")
            time.sleep(2)
            
        print("\n2. Waiting for publishers to establish connections...")
        time.sleep(5)
        
        # Start recorder
        print("\n3. Starting multi-peer recorder (single WebSocket)...")
        recorder_cmd = [
            sys.executable, "publish.py",
            "--room", room_name,
            "--record", "multipeer",
            "--record-room",
            "--noaudio",
            "--bitrate", "2000"
        ]
        
        print("   Command:", " ".join(recorder_cmd))
        print("\n" + "-"*60)
        print("RECORDER OUTPUT:")
        print("-"*60)
        
        # Run recorder with visible output
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        
        recorder_proc = subprocess.Popen(
            recorder_cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            text=True,
            env=env
        )
        
        # Monitor for 20 seconds
        start_time = time.time()
        while time.time() - start_time < 20:
            line = recorder_proc.stdout.readline()
            if line:
                print(line.rstrip())
            if recorder_proc.poll() is not None:
                break
            time.sleep(0.1)
            
        # Stop recorder
        if recorder_proc.poll() is None:
            recorder_proc.terminate()
            time.sleep(1)
            if recorder_proc.poll() is None:
                recorder_proc.kill()
                
        print("-"*60)
        
        # Give time for files to finalize
        time.sleep(2)
        
        # Check results
        print("\n4. Checking recordings:")
        
        all_recordings = []
        found_streams = set()
        
        # Look for recordings with various patterns
        patterns = [
            "multipeer_*.ts",
            "multipeer_*.mkv", 
            "multipeer_*.webm",
            f"{room_name}_*.ts",
            f"{room_name}_*.mkv",
            "room_recording_*.ts",
            "room_recording_*.mkv"
        ]
        
        for pattern in patterns:
            for f in glob.glob(pattern):
                all_recordings.append(f)
                # Try to extract stream name
                for stream_name in ["alice", "bob", "charlie"]:
                    if stream_name in f:
                        found_streams.add(stream_name)
                        
        if all_recordings:
            print(f"\n✅ Found {len(all_recordings)} recording files:")
            for f in sorted(set(all_recordings)):
                size = os.path.getsize(f)
                print(f"   - {f} ({size:,} bytes)")
                
            # Validate the recordings
            print("\n5. Validating recordings with GStreamer...")
            try:
                from validate_media_file import MediaFileValidator
                validator = MediaFileValidator()
                
                valid_count = 0
                for recording in all_recordings:
                    is_valid, info = validator.validate_file(recording, timeout=5)
                    if is_valid:
                        print(f"   ✅ {os.path.basename(recording)} - Valid ({info.get('frames_decoded', 0)} frames)")
                        valid_count += 1
                    else:
                        print(f"   ❌ {os.path.basename(recording)} - Invalid: {info.get('error', 'Unknown error')}")
                        
                print(f"\nValidation: {valid_count}/{len(all_recordings)} files are valid")
                
                if valid_count == len(all_recordings) and len(found_streams) > 1:
                    print(f"\n✅ SUCCESS! Recorded and validated {len(found_streams)} different streams: {', '.join(sorted(found_streams))}")
                elif valid_count == len(all_recordings):
                    print(f"\n✅ All recordings are valid")
                else:
                    print(f"\n⚠️  Some recordings failed validation")
                    
            except ImportError:
                print("\n⚠️  Media validation not available (validate_media_file.py not found)")
                if len(found_streams) > 1:
                    print(f"\n✅ SUCCESS! Recorded {len(found_streams)} different streams: {', '.join(sorted(found_streams))}")
                elif len(all_recordings) > 1:
                    print(f"\n⚠️  Multiple files but couldn't identify different streams")
                else:
                    print(f"\n⚠️  Only one recording file found")
        else:
            print("\n❌ No recordings found!")
            
            # Debug: check if recorder created any files at all
            print("\nAll files in current directory:")
            recent_files = []
            for f in os.listdir("."):
                if os.path.isfile(f):
                    mtime = os.path.getmtime(f)
                    if time.time() - mtime < 60:  # Files modified in last minute
                        recent_files.append(f)
                        
            if recent_files:
                print("Recent files:", ", ".join(recent_files[:10]))
            else:
                print("No recent files found")
                
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        print("\n5. Cleaning up...")
        for name, proc in publishers:
            if proc.poll() is None:
                proc.terminate()
                print(f"   Stopped {name}")
                
        time.sleep(1)
        for name, proc in publishers:
            if proc.poll() is None:
                proc.kill()
                
    print("\n" + "="*60)
    print("Test complete!")
    
    # Return success if we found recordings
    return len(all_recordings) > 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)