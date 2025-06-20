#!/usr/bin/env python3
"""
Test NDI with streams already publishing in the room
"""

import subprocess
import time
import threading
import sys
import os

def run_publisher(stream_id, room):
    """Run a publisher in the background"""
    cmd = [
        'python3', 'publish.py',
        '--test',
        '--room', room,
        '--streamid', stream_id,
        '--password', 'false'
    ]
    
    print(f"Starting publisher: {stream_id}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Monitor for successful connection
    for line in iter(proc.stdout.readline, ''):
        if 'Room has' in line or 'WebSocket ready' in line:
            print(f"  [{stream_id}] Connected to room")
        if 'seed start' in line:
            print(f"  [{stream_id}] Publishing stream")
            break
    
    return proc

def run_ndi_recorder(room):
    """Run the NDI recorder and capture output"""
    cmd = [
        'python3', 'publish.py',
        '--room', room,
        '--room-ndi', 
        '--password', 'false'
    ]
    
    print(f"\nStarting NDI recorder...")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    return proc

def main():
    room = 'testroom_ndi_' + str(int(time.time()))
    
    print("=" * 70)
    print("NDI Test with Pre-existing Streams")
    print("=" * 70)
    print(f"Room: {room}")
    print("=" * 70)
    
    # Start publishers first
    print("\n1. Starting publishers...")
    publishers = []
    pub1 = run_publisher('test_stream_1', room)
    publishers.append(pub1)
    time.sleep(3)
    
    pub2 = run_publisher('test_stream_2', room) 
    publishers.append(pub2)
    time.sleep(3)
    
    print("\n2. Publishers should now be active in the room")
    print("   Waiting 5 seconds to ensure they're fully connected...")
    time.sleep(5)
    
    # Now start NDI recorder
    print("\n3. Starting NDI recorder (streams already in room)...")
    ndi_proc = run_ndi_recorder(room)
    
    # Monitor NDI output
    start_time = time.time()
    found_streams = False
    ndi_streams = []
    
    while time.time() - start_time < 20:
        line = ndi_proc.stdout.readline()
        if not line:
            break
            
        line = line.strip()
        
        # Remove ANSI codes for cleaner output
        import re
        clean_line = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])').sub('', line)
        
        # Print key lines
        if any(phrase in clean_line for phrase in ['Room has', 'Member', 'Found', 'streams to record', 'Creating subprocess', 'NDI']):
            print(f"  [NDI] {clean_line}")
            
        if 'Found' in clean_line and 'streams to record' in clean_line:
            if '2 streams to record' in clean_line:
                found_streams = True
                
        if 'NDI stream name' in clean_line:
            ndi_streams.append(clean_line)
    
    # Results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"✓ Publishers started: 2")
    print(f"✓ Found existing streams in room: {'YES' if found_streams else 'NO'}")
    print(f"✓ NDI streams created: {len(ndi_streams)}")
    
    if not found_streams:
        print("\n❌ ISSUE: The NDI recorder did not detect the existing streams!")
        print("   The room listing should have included streamIDs for active publishers.")
    
    # Cleanup
    print("\nCleaning up...")
    for proc in publishers + [ndi_proc]:
        try:
            proc.terminate()
        except:
            pass

if __name__ == "__main__":
    main()