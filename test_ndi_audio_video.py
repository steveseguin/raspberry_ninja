#!/usr/bin/env python3
"""
Test NDI with audio and video multiplexing
"""

import subprocess
import time
import signal
import sys

def test_ndi_room():
    """Test room NDI with audio/video"""
    print("Starting NDI room test with audio/video multiplexing...")
    print("Room: testroom123999999999")
    print("Test URLs:")
    print("  1. https://vdo.ninja/?room=testroom123999999999&push=tUur6fffwt&debug&view")
    print("  2. https://vdo.ninja/?room=testroom123999999999&push=tUur6wt&debug&view")
    print("-" * 70)
    
    # Start the NDI room recorder
    cmd = [
        'python3', 'publish.py',
        '--room', 'testroom123999999999',
        '--room-ndi',
        '--password', 'false',
        '--debug'
    ]
    
    print(f"Running: {' '.join(cmd)}")
    print("-" * 70)
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Monitor output
    start_time = time.time()
    ndi_streams = set()
    subprocess_created = False
    errors = []
    
    def signal_handler(sig, frame):
        print("\n\nShutting down...")
        process.terminate()
        process.wait()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        while True:
            line = process.stdout.readline()
            if not line:
                break
                
            line = line.strip()
            
            # Extract key information
            if 'ndi' in line.lower():
                print(f"[NDI] {line}")
                if 'ndi stream name:' in line.lower():
                    # Extract stream name
                    parts = line.split('ndi stream name:')
                    if len(parts) > 1:
                        stream_name = parts[1].strip()
                        ndi_streams.add(stream_name)
                        
            elif 'subprocess' in line.lower():
                print(f"[SUBPROCESS] {line}")
                if 'creating subprocess' in line.lower():
                    subprocess_created = True
                    
            elif 'error' in line.lower():
                print(f"[ERROR] {line}")
                errors.append(line)
                
            elif any(word in line.lower() for word in ['connected', 'audio', 'video', 'combiner']):
                print(f"[INFO] {line}")
                
            # Show heartbeat every 10 seconds
            if time.time() - start_time > 10:
                print(".", end="", flush=True)
                start_time = time.time()
                
    except KeyboardInterrupt:
        pass
    finally:
        process.terminate()
        process.wait()
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"✓ Subprocess created: {subprocess_created}")
    print(f"✓ NDI streams detected: {len(ndi_streams)}")
    if ndi_streams:
        for stream in ndi_streams:
            print(f"  - {stream}")
    print(f"✗ Errors: {len(errors)}")
    if errors:
        for error in errors[:5]:
            print(f"  - {error}")
    
    print("\nNOTE: Use an NDI viewer (like NDI Studio Monitor) to see the streams")
    print("Each room participant should appear as a separate NDI source")

if __name__ == "__main__":
    test_ndi_room()