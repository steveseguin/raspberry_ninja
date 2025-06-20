#!/usr/bin/env python3
"""
Simple room recording test that creates recordings and validates them
"""

import subprocess
import sys
import time
import os
import glob
from validate_media_file import MediaFileValidator


def test_room_recording():
    """Test room recording with validation"""
    print("Room Recording Test with Validation")
    print("="*50)
    
    # Clean up
    patterns = ["room_test_*.ts", "room_test_*.mkv", "roomtest*.ts", "roomtest*.mkv"]
    for pattern in patterns:
        for f in glob.glob(pattern):
            os.remove(f)
            
    room = f"roomtest{int(time.time())}"
    processes = []
    validator = MediaFileValidator()
    
    try:
        # Start 2 publishers
        print(f"\n1. Starting publishers in room: {room}")
        
        # Publisher 1: H264
        pub1 = subprocess.Popen([
            sys.executable, "publish.py",
            "--test", "--room", room,
            "--stream", "alice", "--noaudio", "--h264"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(pub1)
        print("   Started alice (H264)")
        
        time.sleep(2)
        
        # Publisher 2: VP8
        pub2 = subprocess.Popen([
            sys.executable, "publish.py",
            "--test", "--room", room,
            "--stream", "bob", "--noaudio", "--vp8"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(pub2)
        print("   Started bob (VP8)")
        
        # Wait for publishers to connect
        print("\n2. Waiting for publishers to establish...")
        time.sleep(5)
        
        # Start room recorder
        print("\n3. Starting room recorder...")
        rec_cmd = [
            sys.executable, "publish.py",
            "--room", room,
            "--record", "room_test",
            "--record-room",
            "--noaudio"
        ]
        print(f"   Command: {' '.join(rec_cmd)}")
        
        rec = subprocess.Popen(
            rec_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        processes.append(rec)
        
        # Monitor output
        print("\n4. Recording for 15 seconds...")
        print("   Key output:")
        start_time = time.time()
        room_recording_active = False
        multi_peer_active = False
        
        while time.time() - start_time < 15:
            line = rec.stdout.readline()
            if line:
                line = line.rstrip()
                # Print key messages
                if any(key in line for key in ["Room recording mode:", "Multi-Peer", "Will record", "Adding recorder", "Recording started"]):
                    print(f"   >>> {line}")
                    
                if "Room recording mode: True" in line:
                    room_recording_active = True
                elif "Multi-Peer Client" in line:
                    multi_peer_active = True
                    
        # Stop recorder
        print("\n5. Stopping recorder...")
        rec.terminate()
        
        # Get remaining output
        try:
            remaining_output, _ = rec.communicate(timeout=3)
            if "Recording saved" in remaining_output or "SUCCESS" in remaining_output:
                print("   >>> Found success indicators in output")
        except:
            pass
            
        # Stop publishers
        for p in processes:
            if p.poll() is None:
                p.terminate()
                
        # Wait for file finalization
        time.sleep(3)
        
        # Find recordings
        print("\n6. Looking for recordings...")
        all_recordings = []
        search_patterns = [
            "room_test_*.ts", "room_test_*.mkv",
            f"{room}_*.ts", f"{room}_*.mkv",
            "room_test_alice_*.ts", "room_test_bob_*.mkv"
        ]
        
        for pattern in search_patterns:
            found = glob.glob(pattern)
            if found:
                print(f"   Found files matching '{pattern}'")
                all_recordings.extend(found)
                
        # Remove duplicates
        all_recordings = list(set(all_recordings))
        
        if not all_recordings:
            print("   ❌ No recordings found!")
            
            # Debug: list recent files
            print("\n   Recent .ts and .mkv files:")
            for f in sorted(glob.glob("*.ts") + glob.glob("*.mkv"))[-10:]:
                mtime = os.path.getmtime(f)
                age = time.time() - mtime
                if age < 60:  # Files modified in last minute
                    print(f"      - {f} (modified {int(age)}s ago)")
                    
            return False
            
        # Validate recordings
        print(f"\n7. Found {len(all_recordings)} recording(s), validating...")
        
        valid_count = 0
        for recording in sorted(all_recordings):
            print(f"\n   Validating: {recording}")
            is_valid, info = validator.validate_file(recording, timeout=5)
            
            if is_valid:
                size_mb = os.path.getsize(recording) / (1024 * 1024)
                print(f"   ✅ VALID")
                print(f"      Size: {size_mb:.2f} MB")
                print(f"      Frames: {info.get('frames_decoded', 0)}")
                print(f"      Format: {info.get('format', 'unknown')}")
                valid_count += 1
            else:
                print(f"   ❌ INVALID")
                print(f"      Error: {info.get('error', 'Unknown')}")
                
        # Summary
        print(f"\n8. Summary:")
        print(f"   - Room recording mode: {'✅ Active' if room_recording_active else '❓ Unknown'}")
        print(f"   - Multi-peer client: {'✅ Active' if multi_peer_active else '❓ Unknown'}")
        print(f"   - Total recordings: {len(all_recordings)}")
        print(f"   - Valid recordings: {valid_count}")
        
        # Check if we got different streams
        has_alice = any("alice" in f for f in all_recordings)
        has_bob = any("bob" in f for f in all_recordings)
        
        if has_alice and has_bob:
            print(f"   - ✅ Both streams recorded separately")
        elif len(all_recordings) > 1:
            print(f"   - ✅ Multiple files created")
        else:
            print(f"   - ⚠️  Only one file created")
            
        success = valid_count > 0
        
        if success:
            print("\n✅ TEST PASSED: Recordings created and validated")
        else:
            print("\n❌ TEST FAILED: No valid recordings")
            
        return success
        
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Cleanup
        for p in processes:
            if p.poll() is None:
                p.terminate()
                

if __name__ == "__main__":
    success = test_room_recording()
    sys.exit(0 if success else 1)