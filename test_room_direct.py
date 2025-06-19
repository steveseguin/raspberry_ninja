#!/usr/bin/env python3
"""
Direct test of room recording functionality
"""

import subprocess
import time
import os
import sys
import glob

def test_room_recording():
    """Test room recording with debug output"""
    
    # Clean up old files
    patterns = ["myprefix_*.ts", "myprefix_*.mkv", "testroom123_*.ts", "testroom123_*.mkv"]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
                print(f"Cleaned: {f}")
            except:
                pass
    
    print("="*70)
    print("ROOM RECORDING TEST")
    print("Testing room: testroom123")
    print("Expected stream: KLvZZdT") 
    print("="*70)
    
    # Set environment for better debugging
    env = os.environ.copy()
    env['GST_DEBUG'] = '3'  # Moderate debugging
    env['GST_DEBUG_NO_COLOR'] = '1'
    
    cmd = [
        sys.executable, 'publish.py',
        '--room', 'testroom123',
        '--record', 'myprefix',
        '--record-room',
        '--password', 'false',
        '--noaudio'
    ]
    
    print("\nCommand:", ' '.join(cmd))
    print("\nOutput:")
    print("-"*70)
    
    # Start the process
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
        env=env
    )
    
    start_time = time.time()
    important_lines = []
    
    try:
        while time.time() - start_time < 30:  # Run for 30 seconds
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
                
            if line:
                line = line.rstrip()
                print(line)
                
                # Collect important lines
                if any(x in line for x in ['ERROR', 'WARNING', 'Connection state', 
                                          'ICE', 'Answer', 'Recording', 'Stream',
                                          'Failed', 'Success', 'members']):
                    important_lines.append(line)
                    
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        proc.terminate()
        time.sleep(2)
        if proc.poll() is None:
            proc.kill()
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY OF IMPORTANT EVENTS:")
    print("="*70)
    for line in important_lines[-20:]:  # Last 20 important lines
        print(line)
    
    # Check results
    print("\n" + "="*70)
    print("RESULTS:")
    print("="*70)
    
    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern))
    
    if files:
        print(f"\n✅ Found {len(files)} recordings:")
        for f in files:
            size = os.path.getsize(f)
            print(f"  {f}: {size:,} bytes")
            
        # Validate
        try:
            from validate_media_file import validate_recording
            print("\nValidating...")
            for f in files:
                result = validate_recording(f)
                print(f"  {f}: {'✅ Valid' if result else '❌ Invalid'}")
        except Exception as e:
            print(f"\nValidation error: {e}")
    else:
        print("\n❌ No recordings found")
        print("\nPossible issues:")
        print("1. WebRTC connection failed")
        print("2. No stream in room")
        print("3. ICE/STUN connectivity issues")
        print("4. Pipeline setup failed")
    
    return len(files) > 0

if __name__ == "__main__":
    success = test_room_recording()
    sys.exit(0 if success else 1)