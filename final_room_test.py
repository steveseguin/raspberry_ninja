#!/usr/bin/env python3
"""
Final comprehensive test for room recording
"""

import subprocess
import sys
import time
import os
import glob
from validate_media_file import validate_recording

def cleanup():
    """Clean up test files"""
    patterns = ["final_*.ts", "final_*.mkv", "finalroom_*.ts", "finalroom_*.mkv"]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except:
                pass

def run_final_test():
    """Run the final comprehensive test"""
    print("\n" + "="*70)
    print("FINAL ROOM RECORDING TEST")
    print("="*70)
    
    cleanup()
    
    room = "finalroom"
    processes = []
    
    try:
        # Step 1: Start 2 publishers
        print("\n1. Starting publishers...")
        
        # Alice with H264
        pub1 = subprocess.Popen([
            sys.executable, "publish.py",
            "--test", "--room", room,
            "--stream", "alice",
            "--noaudio", "--h264",
            "--password", "false"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(pub1)
        print("   ✓ Alice started (H264)")
        
        time.sleep(2)
        
        # Bob with VP8
        pub2 = subprocess.Popen([
            sys.executable, "publish.py",
            "--test", "--room", room,
            "--stream", "bob",
            "--noaudio", "--vp8",
            "--password", "false"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(pub2)
        print("   ✓ Bob started (VP8)")
        
        time.sleep(3)
        
        # Step 2: Start room recorder
        print("\n2. Starting room recorder...")
        rec_cmd = [
            sys.executable, "publish.py",
            "--room", room,
            "--record", "final",
            "--record-room",
            "--noaudio",
            "--password", "false"
        ]
        
        print(f"   Command: {' '.join(rec_cmd)}")
        
        # Run with output to see what happens
        rec = subprocess.Popen(
            rec_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        processes.append(rec)
        
        # Monitor for key events
        print("\n3. Monitoring recorder (30 seconds)...")
        start = time.time()
        recording_started = False
        
        while time.time() - start < 30:
            try:
                line = rec.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                    
                line = line.rstrip()
                
                # Print key lines
                if any(x in line for x in ["Room has", "Multi-Peer", "Recording to:", 
                                           "ERROR", "Adding recorder", "Pipeline started"]):
                    print(f"   >>> {line}")
                    
                if "Recording to:" in line:
                    recording_started = True
                    print("\n   🎬 RECORDING STARTED!")
                    
            except:
                break
        
        # Let it record more
        if recording_started:
            print("\n4. Recording for additional 10 seconds...")
            time.sleep(10)
        
        # Stop recorder
        print("\n5. Stopping recorder...")
        rec.terminate()
        
        # Wait for cleanup
        time.sleep(3)
        
        # Stop publishers
        print("6. Stopping publishers...")
        for p in processes:
            if p.poll() is None:
                p.terminate()
        
        time.sleep(2)
        
        # Check results
        print("\n7. RESULTS:")
        print("-" * 50)
        
        # Find all recordings
        recordings = glob.glob("final_*.ts") + glob.glob("final_*.mkv") + \
                     glob.glob(f"{room}_*.ts") + glob.glob(f"{room}_*.mkv")
        
        if recordings:
            print(f"\n✅ Found {len(recordings)} recording file(s):")
            
            valid_count = 0
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
                    print("   Stream: Alice (H264)")
                elif "bob" in f:
                    print("   Stream: Bob (VP8)")
                    
            print(f"\n   Total valid recordings: {valid_count}")
            
            # Success check
            if valid_count >= 2:
                print("\n🎉 SUCCESS: Room recording is working!")
                return True
            else:
                print("\n⚠️  PARTIAL: Some recordings may have failed")
                return False
        else:
            print("\n❌ FAILED: No recordings found")
            
            # Diagnosis
            if not recording_started:
                print("\nDiagnosis: Recording never started. Possible issues:")
                print("  - WebSocket connection failed")
                print("  - Room listing not received")
                print("  - Multi-peer client initialization failed")
            
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
                
        # Final cleanup after a delay
        time.sleep(2)
        for p in processes:
            if p.poll() is None:
                p.kill()

if __name__ == "__main__":
    print("Starting final room recording test...")
    print("This will test recording multiple streams in a room")
    
    success = run_final_test()
    
    print("\n" + "="*70)
    if success:
        print("✅ ROOM RECORDING TEST PASSED")
        print("The --record-room feature is working correctly!")
    else:
        print("❌ ROOM RECORDING TEST FAILED")
        print("Check the output above for error messages")
    
    sys.exit(0 if success else 1)