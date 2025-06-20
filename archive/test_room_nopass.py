#!/usr/bin/env python3
"""
Test room recording without password/encryption
"""

import subprocess
import sys
import time
import os
import glob
from validate_media_file import validate_recording

# Clean up
for f in glob.glob("nopass_*.ts") + glob.glob("nopass_*.mkv"):
    os.remove(f)

room = f"nopass{int(time.time())}"
processes = []

try:
    # Start publishers WITHOUT default password
    print(f"Starting publishers in room: {room} (no encryption)")
    
    # Publisher 1
    pub1 = subprocess.Popen([
        sys.executable, "publish.py",
        "--test", "--room", room,
        "--stream", "alice",
        "--noaudio", "--h264",
        "--password", "false"  # Disable password
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    processes.append(pub1)
    print("   Started alice (H264)")
    
    time.sleep(3)
    
    # Publisher 2  
    pub2 = subprocess.Popen([
        sys.executable, "publish.py",
        "--test", "--room", room,
        "--stream", "bob",
        "--noaudio", "--vp8",
        "--password", "false"  # Disable password
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    processes.append(pub2)
    print("   Started bob (VP8)")
    
    # Wait for connection
    print("\nWaiting for publishers to establish...")
    time.sleep(5)
    
    # Start room recorder
    print("\nStarting room recorder...")
    rec_cmd = [
        sys.executable, "publish.py",
        "--room", room,
        "--record", "nopass",
        "--record-room",
        "--noaudio",
        "--password", "false"  # Disable password
    ]
    
    rec = subprocess.Popen(
        rec_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    processes.append(rec)
    
    # Monitor output
    print("\nRecording for 20 seconds...")
    start_time = time.time()
    
    while time.time() - start_time < 20:
        line = rec.stdout.readline()
        if line:
            line = line.rstrip()
            # Print key messages
            if any(key in line for key in ["Room has", "members", "Will record", "Multi-Peer", "Adding recorder", "Recording to:", "Recording started"]):
                print(f"   >>> {line}")
                
    # Stop
    print("\nStopping...")
    rec.terminate()
    
    # Get remaining output
    try:
        remaining, _ = rec.communicate(timeout=2)
        if remaining and "Recording saved" in remaining:
            print("   >>> Found recording saved messages")
    except:
        pass
        
    # Stop publishers
    for p in processes:
        if p.poll() is None:
            p.terminate()
            
    # Wait
    time.sleep(3)
    
    # Find recordings
    print("\nLooking for recordings...")
    recordings = glob.glob("nopass_*.ts") + glob.glob("nopass_*.mkv") + glob.glob(f"{room}_*.ts") + glob.glob(f"{room}_*.mkv")
    
    if recordings:
        print(f"\n✅ Found {len(recordings)} recording(s):")
        
        valid_count = 0
        for f in sorted(recordings):
            size = os.path.getsize(f)
            print(f"\n   {f} ({size:,} bytes)")
            
            # Validate
            is_valid = validate_recording(f, verbose=False)
            if is_valid:
                print(f"   ✅ Valid recording")
                valid_count += 1
            else:
                print(f"   ❌ Invalid recording")
                
        print(f"\nSummary: {valid_count}/{len(recordings)} recordings are valid")
        
        if valid_count >= 2:
            print("\n✅ TEST PASSED: Multiple streams recorded successfully")
        elif valid_count > 0:
            print("\n⚠️ TEST PARTIAL: Some recordings created")
        else:
            print("\n❌ TEST FAILED: No valid recordings")
    else:
        print("\n❌ No recordings found")
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    
finally:
    # Cleanup
    for p in processes:
        if p.poll() is None:
            p.terminate()