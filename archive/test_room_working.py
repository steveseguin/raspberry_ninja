#!/usr/bin/env python3
"""
Working room recording test with proper timing
"""

import subprocess
import sys
import time
import os
import glob
from validate_media_file import validate_recording

def test_room_recording():
    """Test room recording with proper timing"""
    print("Room Recording Test")
    print("="*50)
    
    # Clean up
    for f in glob.glob("room_*.ts") + glob.glob("room_*.mkv"):
        os.remove(f)
        
    room = f"room{int(time.time())}"
    processes = []
    
    try:
        # Start publishers FIRST
        print(f"\n1. Starting publishers in room: {room}")
        
        # Publisher 1: H264
        pub1 = subprocess.Popen([
            sys.executable, "publish.py",
            "--test", "--room", room,
            "--stream", "alice", "--noaudio", "--h264"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(pub1)
        print("   Started alice (H264)")
        
        time.sleep(3)
        
        # Publisher 2: VP8
        pub2 = subprocess.Popen([
            sys.executable, "publish.py",
            "--test", "--room", room,
            "--stream", "bob", "--noaudio", "--vp8"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(pub2)
        print("   Started bob (VP8)")
        
        # Wait for publishers to be fully connected
        print("\n2. Waiting for publishers to establish...")
        time.sleep(5)
        
        # NOW start room recorder
        print("\n3. Starting room recorder...")
        rec_cmd = [
            sys.executable, "publish.py",
            "--room", room,
            "--record-room",
            "--record", "room",
            "--noaudio"
        ]
        
        rec = subprocess.Popen(
            rec_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        processes.append(rec)
        
        # Monitor for key messages
        print("\n4. Recording for 20 seconds...")
        start_time = time.time()
        saw_listing = False
        saw_multi_peer = False
        saw_recording = False
        
        while time.time() - start_time < 20:
            if rec.poll() is not None:
                break
                
            line = rec.stdout.readline()
            if line:
                line = line.rstrip()
                
                # Check for key indicators
                if "Room has" in line and "members" in line:
                    saw_listing = True
                    print(f"   ✓ {line}")
                elif "Multi-Peer" in line:
                    saw_multi_peer = True
                    print(f"   ✓ {line}")
                elif "Recording to:" in line or "Recording started" in line:
                    saw_recording = True
                    print(f"   ✓ {line}")
                elif "Will record" in line:
                    print(f"   ✓ {line}")
                elif "Adding recorder" in line:
                    print(f"   ✓ {line}")
                    
        # Stop recorder
        print("\n5. Stopping recorder...")
        rec.terminate()
        
        # Get remaining output
        try:
            remaining, _ = rec.communicate(timeout=2)
            if remaining:
                for line in remaining.split('\n'):
                    if "Recording saved" in line or "bytes" in line:
                        print(f"   ✓ {line}")
        except:
            pass
            
        # Stop publishers
        for p in processes:
            if p.poll() is None:
                p.terminate()
                
        # Wait for files
        time.sleep(3)
        
        # Find recordings
        print("\n6. Looking for recordings...")
        recordings = []
        patterns = [
            "room_*.ts", "room_*.mkv",
            f"{room}_*.ts", f"{room}_*.mkv"
        ]
        
        for pattern in patterns:
            found = glob.glob(pattern)
            recordings.extend(found)
            
        # Remove duplicates
        recordings = list(set(recordings))
        
        # Validate
        if recordings:
            print(f"\n7. Found {len(recordings)} recording(s):")
            
            valid_count = 0
            for f in sorted(recordings):
                size = os.path.getsize(f)
                print(f"\n   {f} ({size:,} bytes)")
                
                # Validate
                is_valid = validate_recording(f, verbose=False)
                if is_valid:
                    print(f"   ✅ Valid recording")
                    valid_count += 1
                    
                    # Check which stream
                    if "alice" in f:
                        print(f"   → Alice's stream (H264)")
                    elif "bob" in f:
                        print(f"   → Bob's stream (VP8)")
                else:
                    print(f"   ❌ Invalid recording")
                    
            # Summary
            print(f"\n8. Summary:")
            print(f"   - Saw room listing: {'✅' if saw_listing else '❌'}")
            print(f"   - Multi-peer active: {'✅' if saw_multi_peer else '❌'}")
            print(f"   - Saw recording messages: {'✅' if saw_recording else '❌'}")
            print(f"   - Total recordings: {len(recordings)}")
            print(f"   - Valid recordings: {valid_count}")
            
            if valid_count >= 2:
                print("\n✅ TEST PASSED: Multiple valid recordings created")
                return True
            elif valid_count > 0:
                print("\n⚠️ TEST PARTIAL: Some recordings created")
                return False
            else:
                print("\n❌ TEST FAILED: No valid recordings")
                return False
        else:
            print("   ❌ No recordings found!")
            print(f"\n   Debug info:")
            print(f"   - Saw listing: {saw_listing}")
            print(f"   - Multi-peer active: {saw_multi_peer}")
            print(f"   - Saw recording: {saw_recording}")
            return False
            
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