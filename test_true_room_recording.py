#!/usr/bin/env python3
"""
Test TRUE room recording - recording ALL different streams in a room
"""

import subprocess
import sys
import time
import os
import glob
from validate_media_file import validate_recording

def cleanup_room_files():
    """Clean up all room-related files"""
    patterns = [
        "trueroom_*.ts", "trueroom_*.mkv",
        "roomtest_*.ts", "roomtest_*.mkv",
        "alice_*.ts", "alice_*.mkv",
        "bob_*.ts", "bob_*.mkv",
        "charlie_*.ts", "charlie_*.mkv"
    ]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except:
                pass

def test_room_recording_all_streams():
    """Test recording ALL streams in a room"""
    print("\n" + "="*70)
    print("TRUE ROOM RECORDING TEST - ALL STREAMS IN A ROOM")
    print("="*70)
    
    cleanup_room_files()
    
    room = "roomtest"
    processes = []
    
    try:
        # Step 1: Start first publisher (Alice)
        print("\n1. Starting first publisher (Alice with H264)...")
        pub1 = subprocess.Popen([
            sys.executable, "publish.py",
            "--test", "--room", room,
            "--stream", "alice",
            "--noaudio", "--h264",
            "--password", "false"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(pub1)
        
        time.sleep(3)
        
        # Step 2: Start second publisher (Bob)
        print("2. Starting second publisher (Bob with VP8)...")
        pub2 = subprocess.Popen([
            sys.executable, "publish.py",
            "--test", "--room", room,
            "--stream", "bob",
            "--noaudio", "--vp8",
            "--password", "false"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(pub2)
        
        time.sleep(3)
        
        # Step 3: Start room recorder
        print("\n3. Starting ROOM RECORDER (should record both Alice and Bob)...")
        rec_cmd = [
            sys.executable, "publish.py",
            "--room", room,
            "--record", "trueroom",
            "--record-room",  # This is the key flag!
            "--noaudio",
            "--password", "false"
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
        print("\n4. Monitoring room recorder output...")
        start = time.time()
        key_events = []
        
        while time.time() - start < 5:
            line = rec.stdout.readline()
            if line:
                line = line.rstrip()
                if any(x in line for x in ["Room has", "members", "Multi-Peer", "Will record", 
                                          "Adding recorder", "Recording to:", "Recording started"]):
                    key_events.append(line)
                    print(f"   >>> {line}")
        
        # Step 4: Add third publisher AFTER recorder started
        print("\n5. Adding third publisher (Charlie with VP9) - should trigger 'videoaddedtoroom'...")
        pub3 = subprocess.Popen([
            sys.executable, "publish.py",
            "--test", "--room", room,
            "--stream", "charlie",
            "--noaudio", "--vp9",
            "--password", "false"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(pub3)
        
        # Continue recording
        print("\n6. Recording all streams for 15 seconds...")
        time.sleep(15)
        
        # Stop recorder first
        print("\n7. Stopping room recorder...")
        rec.terminate()
        
        # Get any final output
        try:
            remaining, _ = rec.communicate(timeout=2)
            if remaining and "Recording saved" in remaining:
                for line in remaining.split('\n'):
                    if "saved" in line or "bytes" in line:
                        print(f"   >>> {line}")
        except:
            pass
        
        time.sleep(3)
        
        # Stop all publishers
        print("8. Stopping all publishers...")
        for p in processes:
            if p.poll() is None:
                p.terminate()
        
        time.sleep(2)
        
        # Step 5: Check results
        print("\n9. CHECKING RECORDINGS...")
        print("-" * 50)
        
        # Find all recordings
        all_recordings = []
        search_patterns = [
            "trueroom_*.ts", "trueroom_*.mkv",
            f"{room}_*.ts", f"{room}_*.mkv",
            "alice_*.ts", "alice_*.mkv",
            "bob_*.ts", "bob_*.mkv",  
            "charlie_*.ts", "charlie_*.mkv"
        ]
        
        for pattern in search_patterns:
            found = glob.glob(pattern)
            all_recordings.extend(found)
        
        # Remove duplicates
        all_recordings = list(set(all_recordings))
        
        if all_recordings:
            print(f"\n✅ Found {len(all_recordings)} recording file(s):")
            
            # Analyze each file
            streams_recorded = set()
            valid_count = 0
            
            for f in sorted(all_recordings):
                size = os.path.getsize(f)
                is_valid = validate_recording(f, verbose=False)
                
                print(f"\n   File: {f}")
                print(f"   Size: {size:,} bytes ({size/1024/1024:.2f} MB)")
                print(f"   Valid: {'✅ YES' if is_valid else '❌ NO'}")
                
                if is_valid:
                    valid_count += 1
                    
                # Identify which stream
                if "alice" in f:
                    streams_recorded.add("alice")
                    print("   Stream: Alice (H264)")
                elif "bob" in f:
                    streams_recorded.add("bob")
                    print("   Stream: Bob (VP8)")
                elif "charlie" in f:
                    streams_recorded.add("charlie")
                    print("   Stream: Charlie (VP9)")
                else:
                    # Try to identify from filename pattern
                    print("   Stream: Unknown")
            
            # Summary
            print(f"\n10. SUMMARY:")
            print("-" * 50)
            print(f"   Total files: {len(all_recordings)}")
            print(f"   Valid files: {valid_count}")
            print(f"   Streams recorded: {', '.join(sorted(streams_recorded))}")
            
            # Success criteria
            expected_streams = {"alice", "bob", "charlie"}
            if streams_recorded == expected_streams:
                print(f"\n🎉 SUCCESS: ALL {len(expected_streams)} streams were recorded!")
                print("   ✅ Alice (H264) - recorded")
                print("   ✅ Bob (VP8) - recorded")
                print("   ✅ Charlie (VP9) - recorded")
                return True
            else:
                missing = expected_streams - streams_recorded
                print(f"\n⚠️  PARTIAL SUCCESS: Only {len(streams_recorded)}/3 streams recorded")
                for stream in missing:
                    print(f"   ❌ {stream} - NOT recorded")
                return False
        else:
            print("\n❌ FAILED: No recordings found")
            print("\nDebugging info:")
            print(f"   Key events captured: {len(key_events)}")
            if key_events:
                print("   Events:")
                for event in key_events[:5]:
                    print(f"     - {event}")
            
            return False
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Ensure cleanup
        for p in processes:
            if p.poll() is None:
                p.terminate()

if __name__ == "__main__":
    print("TRUE ROOM RECORDING TEST")
    print("This test verifies that --record-room records ALL streams in a room")
    print("="*70)
    
    success = test_room_recording_all_streams()
    
    print("\n" + "="*70)
    if success:
        print("✅ TEST PASSED: Room recording works correctly!")
        print("   All different streams in the room were recorded to separate files.")
    else:
        print("❌ TEST FAILED: Room recording is not working properly.")
        print("   Not all streams in the room were recorded.")
    
    sys.exit(0 if success else 1)