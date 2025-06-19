#!/usr/bin/env python3
"""
Debug test for room recording
"""

import subprocess
import sys
import time
import os
import glob

def test_room_recording():
    """Test room recording with debug output"""
    print("Room Recording Debug Test")
    print("="*50)
    
    # Clean up
    for f in glob.glob("room_debug_*.ts") + glob.glob("room_debug_*.mkv"):
        os.remove(f)
        
    room = f"roomdebug{int(time.time())}"
    
    # Start publisher
    print(f"\n1. Starting publisher in room: {room}")
    pub = subprocess.Popen([
        sys.executable, "publish.py",
        "--test", "--room", room,
        "--stream", "alice", "--noaudio", "--h264"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    time.sleep(5)
    
    # Start room recorder with visible output
    print(f"\n2. Starting room recorder...")
    rec_cmd = [
        sys.executable, "publish.py",
        "--room", room,
        "--record", "room_debug",
        "--record-room",
        "--noaudio"
    ]
    print(f"   Command: {' '.join(rec_cmd)}")
    print("\n3. Recorder output:")
    print("-"*50)
    
    rec = subprocess.Popen(
        rec_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    # Read output for 10 seconds
    start_time = time.time()
    while time.time() - start_time < 10:
        line = rec.stdout.readline()
        if line:
            print(line.rstrip())
            # Check for key indicators
            if "Room recording mode: True" in line:
                print("\n>>> GOOD: Room recording mode is True!")
            elif "Room recording mode: False" in line:
                print("\n>>> BAD: Room recording mode is False!")
            elif "Using Multi-Peer Client" in line:
                print("\n>>> GOOD: Multi-peer client activated!")
            elif "Will record" in line:
                print(f"\n>>> INFO: {line.rstrip()}")
                
    # Stop
    print("\n" + "-"*50)
    print("\n4. Stopping recorder...")
    rec.terminate()
    rec.wait(timeout=5)
    pub.terminate()
    
    time.sleep(2)
    
    # Check for recordings
    print("\n5. Checking for recordings...")
    recordings = []
    patterns = ["room_debug_*.ts", "room_debug_*.mkv", f"{room}_*.ts", f"{room}_*.mkv"]
    for pattern in patterns:
        recordings.extend(glob.glob(pattern))
        
    if recordings:
        print(f"   ✅ Found {len(recordings)} recording(s):")
        for f in recordings:
            print(f"      - {f} ({os.path.getsize(f):,} bytes)")
            
        # Try to validate
        try:
            from validate_media_file import validate_recording
            print("\n6. Validating recordings...")
            for f in recordings:
                if validate_recording(f, verbose=False):
                    print(f"   ✅ {f} is valid")
                else:
                    print(f"   ❌ {f} is invalid")
        except:
            print("\n6. Validation module not available")
    else:
        print("   ❌ No recordings found!")
        
        # List all files to debug
        print("\n   Current directory files:")
        for f in os.listdir("."):
            if os.path.isfile(f) and (f.endswith('.ts') or f.endswith('.mkv')):
                print(f"      - {f}")

if __name__ == "__main__":
    test_room_recording()