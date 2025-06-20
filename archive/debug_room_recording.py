#!/usr/bin/env python3
"""
Debug room recording to understand why it's not creating files
"""

import subprocess
import sys
import time
import os
import glob
import asyncio

def cleanup():
    """Clean up test files"""
    patterns = ["debug_*.ts", "debug_*.mkv", "test_*.ts", "test_*.mkv"]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except:
                pass

def run_debug_test():
    """Run a simple debug test"""
    print("\n" + "="*70)
    print("DEBUG: Room Recording Test")
    print("="*70)
    
    cleanup()
    
    # Step 1: Start a simple publisher
    print("\n1. Starting test publisher...")
    pub_cmd = [
        sys.executable, "publish.py",
        "--test", "--room", "debugroom",
        "--stream", "teststream",
        "--noaudio", "--h264",
        "--password", "false"
    ]
    
    pub = subprocess.Popen(
        pub_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    # Monitor publisher output
    print("   Waiting for publisher to connect...")
    start = time.time()
    connected = False
    while time.time() - start < 10:
        line = pub.stdout.readline()
        if line:
            if "WebSocket ready" in line:
                print("   ✓ Publisher connected")
                connected = True
                break
    
    if not connected:
        print("   ✗ Publisher failed to connect")
        pub.terminate()
        return False
    
    time.sleep(2)
    
    # Step 2: Start room recorder with verbose output
    print("\n2. Starting room recorder...")
    rec_cmd = [
        sys.executable, "publish.py",
        "--room", "debugroom",
        "--record", "debug",
        "--record-room",
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
    
    # Monitor recorder output in detail
    print("\n3. Monitoring room recorder output...")
    start = time.time()
    key_events = []
    
    while time.time() - start < 20:
        line = rec.stdout.readline()
        if line:
            line = line.rstrip()
            # Print ALL output for debugging
            print(f"   REC: {line}")
            
            # Track key events
            if any(x in line for x in ["Room has", "Multi-Peer", "Adding recorder", 
                                       "Creating pipeline", "Recording to:", 
                                       "Recording started", "ERROR", "Failed"]):
                key_events.append(line)
    
    # Let it record for a bit
    print("\n4. Recording for 10 seconds...")
    time.sleep(10)
    
    # Stop recorder
    print("\n5. Stopping recorder...")
    rec.terminate()
    
    # Wait a bit and check for final output
    try:
        remaining, _ = rec.communicate(timeout=3)
        if remaining:
            print("   Final output:")
            for line in remaining.split('\n'):
                if line.strip():
                    print(f"   REC: {line}")
    except:
        pass
    
    # Stop publisher
    print("\n6. Stopping publisher...")
    pub.terminate()
    
    time.sleep(2)
    
    # Check for recordings
    print("\n7. Checking for recordings...")
    recordings = glob.glob("debug_*.ts") + glob.glob("debug_*.mkv") + \
                 glob.glob("debugroom_*.ts") + glob.glob("debugroom_*.mkv")
    
    if recordings:
        print(f"\n✅ Found {len(recordings)} recording(s):")
        for f in recordings:
            size = os.path.getsize(f)
            print(f"   - {f}: {size:,} bytes")
        return True
    else:
        print("\n❌ No recordings found!")
        print("\nKey events captured:")
        for event in key_events:
            print(f"   - {event}")
        return False

if __name__ == "__main__":
    success = run_debug_test()
    
    if not success:
        print("\n" + "="*70)
        print("DEBUGGING SUGGESTIONS:")
        print("="*70)
        print("1. Check if multi_peer_client.py is being imported correctly")
        print("2. Verify WebSocket messages are being routed properly")
        print("3. Check GStreamer pipeline creation in StreamRecorder")
        print("4. Look for any ERROR messages in the output above")
        
    sys.exit(0 if success else 1)