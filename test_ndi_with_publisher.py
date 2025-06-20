#!/usr/bin/env python3
"""
Test NDI with a publisher in the room
"""

import subprocess
import time
import threading
import sys

def run_publisher():
    """Run a test publisher to the room"""
    print("Starting test publisher...")
    cmd = [
        'python3', 'publish.py',
        '--test',  # Use test pattern
        '--room', 'testroom123999999999',
        '--streamid', 'test_publisher',
        '--password', 'false'
    ]
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    # Let it run
    for line in iter(proc.stdout.readline, ''):
        if line:
            print(f"[PUBLISHER] {line.strip()}")
    
    return proc

def run_ndi_recorder():
    """Run the NDI room recorder"""
    print("Starting NDI recorder...")
    time.sleep(5)  # Give publisher time to connect
    
    cmd = [
        'python3', 'publish.py',
        '--room', 'testroom123999999999',
        '--room-ndi',
        '--password', 'false'
    ]
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    # Monitor output
    ndi_streams = []
    subprocess_created = False
    
    start_time = time.time()
    while time.time() - start_time < 30:
        line = proc.stdout.readline()
        if not line:
            continue
            
        line = line.strip()
        
        # Print key lines
        if any(word in line.lower() for word in ['ndi', 'subprocess', 'creating', 'stream', 'error', 'combiner']):
            print(f"[NDI-RECORDER] {line}")
            
        if 'ndi stream name' in line.lower():
            ndi_streams.append(line)
        if 'creating subprocess' in line.lower():
            subprocess_created = True
    
    return proc, ndi_streams, subprocess_created

def main():
    print("=" * 70)
    print("NDI Room Test with Publisher")
    print("=" * 70)
    print("This test will:")
    print("1. Start a test video publisher to the room")
    print("2. Start NDI recording of the room")
    print("3. Monitor for NDI stream creation")
    print("=" * 70)
    
    # Start publisher in thread
    publisher_thread = threading.Thread(target=run_publisher)
    publisher_thread.daemon = True
    publisher_thread.start()
    
    # Run NDI recorder
    try:
        ndi_proc, ndi_streams, subprocess_created = run_ndi_recorder()
        
        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70)
        print(f"✓ Subprocess created: {subprocess_created}")
        print(f"✓ NDI streams detected: {len(ndi_streams)}")
        for stream in ndi_streams:
            print(f"  - {stream}")
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Cleanup
        subprocess.run(['pkill', '-f', 'publish.py'])

if __name__ == "__main__":
    main()