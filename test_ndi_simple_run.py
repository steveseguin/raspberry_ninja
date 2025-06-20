#!/usr/bin/env python3
"""Simple test to run room NDI and capture output"""

import subprocess
import threading
import time
import sys

def run_with_timeout():
    cmd = [
        'python3', 'publish.py',
        '--room', 'testroom123999999999',
        '--room-ndi',
        '--password', 'false'
    ]
    
    print(f"Running: {' '.join(cmd)}")
    print("-" * 50)
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Read output for 15 seconds
    start_time = time.time()
    lines = []
    
    def read_output():
        while True:
            line = process.stdout.readline()
            if not line:
                break
            line = line.strip()
            lines.append(line)
            # Print key lines
            if any(word in line.lower() for word in ['error', 'ndi', 'subprocess', 'creating', 'connecting', 'room']):
                print(f"[{time.time()-start_time:.1f}s] {line}")
    
    reader_thread = threading.Thread(target=read_output)
    reader_thread.daemon = True
    reader_thread.start()
    
    # Wait 15 seconds
    time.sleep(15)
    
    # Kill the process
    process.terminate()
    process.wait()
    
    print("\n" + "-" * 50)
    print(f"Captured {len(lines)} lines of output")
    
    # Look for key information
    if not lines:
        print("ERROR: No output captured!")
    else:
        # Check first few lines
        print("\nFirst 10 lines:")
        for line in lines[:10]:
            print(f"  {line}")

if __name__ == "__main__":
    run_with_timeout()