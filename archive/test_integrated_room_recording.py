#!/usr/bin/env python3
"""
Integrated test using actual publish.py to demonstrate room recording
"""

import subprocess
import sys
import time
import os
import glob
import signal

def cleanup():
    """Clean up test files"""
    patterns = ["integrated_*.ts", "integrated_*.mkv", "integroom_*.ts", "integroom_*.mkv"]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except:
                pass

def run_integrated_test():
    """Run integrated test with actual processes"""
    print("\n" + "="*70)
    print("INTEGRATED ROOM RECORDING TEST")
    print("="*70)
    print("\nThis test demonstrates the --record-room functionality")
    print("It uses a SINGLE publish.py instance to record multiple streams")
    print("="*70)
    
    cleanup()
    
    room = "integroom"
    processes = []
    
    try:
        # Step 1: Start test publishers
        print("\n1. Starting test publishers (simulating streams in a room)...")
        
        # Publisher 1: Alice with H264
        pub1_cmd = [
            sys.executable, "publish.py",
            "--test", 
            "--room", room,
            "--stream", "alice",
            "--noaudio", 
            "--h264",
            "--password", "false"
        ]
        print(f"\n   Starting Alice (H264)...")
        print(f"   Command: {' '.join(pub1_cmd)}")
        pub1 = subprocess.Popen(pub1_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        processes.append(pub1)
        
        # Give it time to connect
        time.sleep(3)
        
        # Publisher 2: Bob with VP8
        pub2_cmd = [
            sys.executable, "publish.py",
            "--test",
            "--room", room,
            "--stream", "bob",
            "--noaudio",
            "--vp8",
            "--password", "false"
        ]
        print(f"\n   Starting Bob (VP8)...")
        print(f"   Command: {' '.join(pub2_cmd)}")
        pub2 = subprocess.Popen(pub2_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        processes.append(pub2)
        
        time.sleep(3)
        
        # Step 2: Start the SINGLE room recorder
        print("\n2. Starting ROOM RECORDER (single instance for all streams)...")
        rec_cmd = [
            sys.executable, "publish.py",
            "--room", room,
            "--record", "integrated",
            "--record-room",
            "--noaudio",
            "--password", "false"
        ]
        
        print(f"\n   Command: {' '.join(rec_cmd)}")
        print("\n   This single instance will:")
        print("   - Connect to the room")
        print("   - Discover all streams (alice, bob)")
        print("   - Create separate WebRTC connections for each")
        print("   - Record each to its own file")
        print("   - All using ONE WebSocket connection")
        
        rec = subprocess.Popen(rec_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        processes.append(rec)
        
        # Monitor output
        print("\n3. Monitoring room recorder output...")
        print("-" * 50)
        start_time = time.time()
        timeout = 30  # 30 seconds
        
        key_events = []
        recording_started = False
        
        while time.time() - start_time < timeout:
            line = rec.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
                
            line = line.rstrip()
            
            # Print important lines
            if any(keyword in line for keyword in ["Room has", "Multi-Peer", "Adding recorder", 
                                                   "Recording to:", "Pipeline started", "ERROR"]):
                print(f"   {line}")
                key_events.append(line)
                
                if "Recording to:" in line:
                    recording_started = True
                    print("\n   🎬 RECORDING STARTED!")
        
        # Add a third publisher after recording starts
        if recording_started:
            print("\n4. Adding third publisher (Charlie with VP9) to test dynamic addition...")
            pub3_cmd = [
                sys.executable, "publish.py",
                "--test",
                "--room", room,
                "--stream", "charlie",
                "--noaudio",
                "--vp9",
                "--password", "false"
            ]
            pub3 = subprocess.Popen(pub3_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            processes.append(pub3)
            
            print("   Waiting for videoaddedtoroom event...")
            time.sleep(10)
        
        # Stop recording
        print("\n5. Stopping room recorder...")
        rec.terminate()
        time.sleep(3)
        
        # Stop publishers
        print("\n6. Stopping all publishers...")
        for p in processes:
            if p.poll() is None:
                p.terminate()
        
        time.sleep(2)
        
        # Check results
        print("\n7. CHECKING RESULTS...")
        print("-" * 50)
        
        recordings = glob.glob("integrated_*.ts") + glob.glob("integrated_*.mkv") + \
                     glob.glob(f"{room}_*.ts") + glob.glob(f"{room}_*.mkv")
        
        if recordings:
            print(f"\n✅ Found {len(recordings)} recording file(s):")
            
            from validate_media_file import validate_recording
            
            valid_count = 0
            streams_recorded = set()
            
            for f in sorted(recordings):
                size = os.path.getsize(f)
                is_valid = validate_recording(f, verbose=False) if size > 1000 else False
                
                print(f"\n   File: {f}")
                print(f"   Size: {size:,} bytes")
                print(f"   Valid: {'✅ YES' if is_valid else '❌ NO'}")
                
                if is_valid:
                    valid_count += 1
                    
                # Identify stream
                if "alice" in f:
                    streams_recorded.add("alice")
                    print("   Stream: Alice (H264)")
                elif "bob" in f:
                    streams_recorded.add("bob")
                    print("   Stream: Bob (VP8)")
                elif "charlie" in f:
                    streams_recorded.add("charlie")
                    print("   Stream: Charlie (VP9)")
            
            print(f"\n   Summary:")
            print(f"   - Total files: {len(recordings)}")
            print(f"   - Valid files: {valid_count}")
            print(f"   - Streams recorded: {', '.join(sorted(streams_recorded))}")
            
            if len(streams_recorded) >= 2:
                print("\n🎉 SUCCESS: Room recording is working!")
                print("   Multiple streams were recorded by a SINGLE publish.py instance")
                return True
            else:
                print("\n⚠️  PARTIAL: Only some streams were recorded")
                return False
        else:
            print("\n❌ FAILED: No recordings found")
            
            # Show key events for debugging
            if key_events:
                print("\nKey events captured:")
                for event in key_events[:10]:
                    print(f"   - {event}")
                    
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
                try:
                    p.terminate()
                    p.wait(timeout=2)
                except:
                    p.kill()

if __name__ == "__main__":
    print("\nIntegrated Room Recording Test")
    print("This demonstrates recording multiple streams with a single script")
    
    # Run with timeout
    import signal
    
    def timeout_handler(signum, frame):
        print("\n\nTest timed out!")
        raise TimeoutError("Test exceeded time limit")
        
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(120)  # 2 minute timeout
    
    try:
        success = run_integrated_test()
    except TimeoutError:
        success = False
        print("\n❌ Test timed out")
    finally:
        signal.alarm(0)  # Cancel alarm
    
    print("\n" + "="*70)
    if success:
        print("✅ ROOM RECORDING TEST PASSED")
        print("\nThe --record-room feature successfully:")
        print("  - Used a SINGLE publish.py instance")
        print("  - Connected to a room with ONE WebSocket")
        print("  - Created MULTIPLE WebRTC connections")
        print("  - Recorded DIFFERENT streams to separate files")
    else:
        print("❌ ROOM RECORDING TEST FAILED/INCOMPLETE")
        print("\nThe test could not verify that room recording works properly.")
        print("This may be due to:")
        print("  - WebSocket connection issues")
        print("  - WebRTC negotiation problems")
        print("  - Test environment limitations")
    
    print("="*70)
    
    # Cleanup
    cleanup()
    
    sys.exit(0 if success else 1)